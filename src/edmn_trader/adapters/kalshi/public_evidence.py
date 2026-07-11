"""Fixture-first public trade, lifecycle, and connection evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import ceil
from pathlib import Path
from typing import Any

from edmn_trader.adapters.kalshi.client import normalize_kalshi_market_metadata
from edmn_trader.adapters.kalshi.ws_events import (
    KalshiWsRawEvent,
    KalshiWsSchemaCompatibilityError,
    LegacyKalshiWsRawEvent,
    parse_kalshi_ws_raw_record,
)
from edmn_trader.data.jsonl import write_jsonl_records
from edmn_trader.data.payload_safety import (
    validate_no_private_account_payload,
    validate_no_secret_payload,
)

PUBLIC_TRADE_SCHEMA_VERSION = "edmn.kalshi.public_trade.v1"
LIFECYCLE_SCHEMA_VERSION = "edmn.kalshi.rest_lifecycle.v1"
CONNECTION_EVIDENCE_SCHEMA_VERSION = "edmn.kalshi.connection_evidence.v1"
FRESHNESS_SCHEMA_VERSION = "edmn.kalshi.public_evidence_freshness.v1"
class PublicTradeStreamStatus(StrEnum):
    OBSERVED = "OBSERVED"
    QUIET_NO_PUBLIC_TRADES = "QUIET_NO_PUBLIC_TRADES"
    QUARANTINED_INPUT = "QUARANTINED_INPUT"


class LifecycleSource(StrEnum):
    REST_FALLBACK = "REST_FALLBACK"


class LifecycleStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    SETTLED = "SETTLED"
    PAUSED = "PAUSED"
    UNOPENED = "UNOPENED"
    UNKNOWN = "UNKNOWN"


class LifecycleValidity(StrEnum):
    VALID = "VALID"
    STALE = "STALE"
    UNKNOWN_STATUS = "UNKNOWN_STATUS"
    MVE_UNSUPPORTED = "MVE_UNSUPPORTED"


class ConnectionEvidenceType(StrEnum):
    CONNECTION_OPEN = "CONNECTION_OPEN"
    CONNECTION_CLOSE = "CONNECTION_CLOSE"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    RECONNECT = "RECONNECT"
    RESUBSCRIPTION = "RESUBSCRIPTION"
    SUBSCRIPTION_ACKNOWLEDGED = "SUBSCRIPTION_ACKNOWLEDGED"
    SUBSCRIPTION_REJECTED = "SUBSCRIPTION_REJECTED"


class ConnectionEvidenceSource(StrEnum):
    RECORDER_OBSERVATION = "RECORDER_OBSERVATION"


class KeepaliveStatus(StrEnum):
    OBSERVED = "OBSERVED"
    UNKNOWN_NOT_OBSERVED = "UNKNOWN_NOT_OBSERVED"


@dataclass(frozen=True, slots=True)
class KalshiPublicTradeEvidence:
    campaign_id: str
    market_ticker: str
    connection_id: str
    segment_id: str
    local_row_index: int
    received_at_utc: datetime
    payload_sha256: str
    native_trade_id: str | int
    native_sid: str | int | None
    native_seq: str | int | None
    native_exchange_ts: str | int | float | None
    native_exchange_ts_ms: int | None
    native_trade_payload: Mapping[str, Any]
    channel: str = field(default="trade", init=False)
    is_account_fill: bool = field(default=False, init=False)
    schema_version: str = field(default=PUBLIC_TRADE_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_aware(self.received_at_utc, "received_at_utc")
        if (
            not self.campaign_id
            or not self.market_ticker
            or not self.connection_id
            or not self.segment_id
            or self.local_row_index < 1
            or isinstance(self.native_trade_id, bool)
            or not isinstance(self.native_trade_id, str | int)
        ):
            raise ValueError("public trade identity fields are invalid")
        copied = deepcopy(dict(self.native_trade_payload))
        validate_no_secret_payload(copied)
        validate_no_private_account_payload(copied)
        if (
            copied.get("trade_id") != self.native_trade_id
            or copied.get("market_ticker") != self.market_ticker
        ):
            raise ValueError("public trade payload identity does not match evidence")
        object.__setattr__(self, "native_trade_payload", copied)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "record_type": "kalshi_public_market_trade",
            "campaign_id": self.campaign_id,
            "market_ticker": self.market_ticker,
            "connection_id": self.connection_id,
            "segment_id": self.segment_id,
            "local_row_index": self.local_row_index,
            "received_at_utc": self.received_at_utc.isoformat(),
            "payload_sha256": self.payload_sha256,
            "channel": self.channel,
            "native_trade_id": self.native_trade_id,
            "native_sid": self.native_sid,
            "native_seq": self.native_seq,
            "native_exchange_ts": self.native_exchange_ts,
            "native_exchange_ts_ms": self.native_exchange_ts_ms,
            "native_trade_payload": deepcopy(dict(self.native_trade_payload)),
            "is_account_fill": self.is_account_fill,
        }


@dataclass(frozen=True, slots=True)
class PublicTradeEvidenceStream:
    selected_market_tickers: tuple[str, ...]
    trades: tuple[KalshiPublicTradeEvidence, ...]
    filtered_nonselected_count: int
    ignored_nontrade_count: int
    quarantined_count: int
    status: PublicTradeStreamStatus

    def __post_init__(self) -> None:
        selected = tuple(self.selected_market_tickers)
        trades = tuple(self.trades)
        if not selected or len(set(selected)) != len(selected):
            raise ValueError("selected market tickers must be unique and non-empty")
        if any(count < 0 for count in self._counts()):
            raise ValueError("public trade stream counts must be non-negative")
        if any(trade.market_ticker not in selected for trade in trades):
            raise ValueError("public trade stream contains a nonselected market")
        expected_status = _public_trade_stream_status(trades, self.quarantined_count)
        if PublicTradeStreamStatus(self.status) is not expected_status:
            raise ValueError("public trade stream status contradicts its contents")
        object.__setattr__(self, "selected_market_tickers", selected)
        object.__setattr__(self, "trades", trades)
        object.__setattr__(self, "status", expected_status)

    def _counts(self) -> tuple[int, int, int]:
        return (
            self.filtered_nonselected_count,
            self.ignored_nontrade_count,
            self.quarantined_count,
        )

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    def to_records(self) -> list[dict[str, object]]:
        return [trade.to_record() for trade in self.trades]


@dataclass(frozen=True, slots=True)
class KalshiRestLifecycleEvidence:
    market_ticker: str
    observed_at_utc: datetime
    evaluated_at_utc: datetime
    raw_status: str | None
    normalized_status: str | None
    lifecycle_status: LifecycleStatus
    validity: LifecycleValidity
    observation_age_seconds: int
    max_age_seconds: int
    mve_unsupported: bool
    source: LifecycleSource = field(default=LifecycleSource.REST_FALLBACK, init=False)
    proves_websocket_transport: bool = field(default=False, init=False)
    schema_version: str = field(default=LIFECYCLE_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_aware(self.observed_at_utc, "observed_at_utc")
        _require_aware(self.evaluated_at_utc, "evaluated_at_utc")
        if not self.market_ticker or self.max_age_seconds < 0:
            raise ValueError("lifecycle market and maximum age are invalid")
        expected_age = _age_seconds(
            self.evaluated_at_utc,
            self.observed_at_utc,
            "observed_at_utc",
        )
        if self.observation_age_seconds != expected_age:
            raise ValueError("lifecycle observation age contradicts its timestamps")
        status = LifecycleStatus(self.lifecycle_status)
        normalized_from_raw = normalize_kalshi_market_metadata(
            {"status": self.raw_status}
        ).get("status")
        if normalized_from_raw != self.normalized_status:
            raise ValueError("lifecycle raw and normalized status contradict")
        if _lifecycle_status(self.normalized_status) is not status:
            raise ValueError("lifecycle status contradicts normalized status")
        expected_validity = _lifecycle_validity(
            status,
            expected_age,
            self.max_age_seconds,
            self.mve_unsupported,
        )
        if LifecycleValidity(self.validity) is not expected_validity:
            raise ValueError("lifecycle validity contradicts status or age")
        object.__setattr__(self, "lifecycle_status", status)
        object.__setattr__(self, "validity", expected_validity)

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "record_type": "kalshi_selected_market_lifecycle",
            "market_ticker": self.market_ticker,
            "observed_at_utc": self.observed_at_utc.isoformat(),
            "evaluated_at_utc": self.evaluated_at_utc.isoformat(),
            "raw_status": self.raw_status,
            "normalized_status": self.normalized_status,
            "lifecycle_status": self.lifecycle_status,
            "validity": self.validity,
            "observation_age_seconds": self.observation_age_seconds,
            "max_age_seconds": self.max_age_seconds,
            "mve_unsupported": self.mve_unsupported,
            "source": self.source,
            "proves_websocket_transport": self.proves_websocket_transport,
        }


@dataclass(frozen=True, slots=True)
class ConnectionEvidenceEvent:
    event_type: ConnectionEvidenceType
    observed_at_utc: datetime
    connection_id: str
    segment_id: str
    reason: str
    previous_connection_id: str | None = None
    previous_segment_id: str | None = None
    source: ConnectionEvidenceSource = field(
        default=ConnectionEvidenceSource.RECORDER_OBSERVATION,
        init=False,
    )
    schema_version: str = field(
        default=CONNECTION_EVIDENCE_SCHEMA_VERSION,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", ConnectionEvidenceType(self.event_type))
        _require_aware(self.observed_at_utc, "observed_at_utc")
        if not self.connection_id or not self.segment_id or not self.reason:
            raise ValueError("connection_id, segment_id, and reason are required")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "record_type": "kalshi_connection_evidence",
            "event_type": self.event_type,
            "observed_at_utc": self.observed_at_utc.isoformat(),
            "connection_id": self.connection_id,
            "segment_id": self.segment_id,
            "previous_connection_id": self.previous_connection_id,
            "previous_segment_id": self.previous_segment_id,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class EvidenceFreshness:
    evaluated_at_utc: datetime
    transport_keepalive_status: KeepaliveStatus
    transport_keepalive_source: str | None
    transport_keepalive_age_seconds: int | None
    lifecycle_observation_age_seconds: int | None
    orderbook_event_quiet_interval_seconds: int | None
    schema_version: str = field(default=FRESHNESS_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_aware(self.evaluated_at_utc, "evaluated_at_utc")
        ages = (
            self.transport_keepalive_age_seconds,
            self.lifecycle_observation_age_seconds,
            self.orderbook_event_quiet_interval_seconds,
        )
        if any(age is not None and age < 0 for age in ages):
            raise ValueError("freshness ages must be non-negative")
        observed = self.transport_keepalive_status is KeepaliveStatus.OBSERVED
        if observed != (
            self.transport_keepalive_source is not None
            and self.transport_keepalive_age_seconds is not None
        ):
            raise ValueError("keepalive status, source, and age are inconsistent")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "evaluated_at_utc": self.evaluated_at_utc.isoformat(),
            "transport_keepalive_status": self.transport_keepalive_status,
            "transport_keepalive_source": self.transport_keepalive_source,
            "transport_keepalive_age_seconds": self.transport_keepalive_age_seconds,
            "lifecycle_observation_age_seconds": (
                self.lifecycle_observation_age_seconds
            ),
            "orderbook_event_quiet_interval_seconds": (
                self.orderbook_event_quiet_interval_seconds
            ),
        }


def build_public_trade_stream(
    records: Iterable[Mapping[str, Any] | KalshiWsRawEvent],
    *,
    selected_market_tickers: tuple[str, ...],
) -> PublicTradeEvidenceStream:
    if not selected_market_tickers:
        raise ValueError("selected_market_tickers must not be empty")
    selected = frozenset(selected_market_tickers)
    trades: list[KalshiPublicTradeEvidence] = []
    filtered = ignored = quarantined = 0
    for record in records:
        try:
            event = (
                record
                if isinstance(record, KalshiWsRawEvent)
                else parse_kalshi_ws_raw_record(record)
            )
        except (KalshiWsSchemaCompatibilityError, TypeError, ValueError):
            quarantined += 1
            continue
        if isinstance(event, LegacyKalshiWsRawEvent):
            quarantined += 1
            continue
        if event.native_type != "trade":
            ignored += 1
            continue
        if not event.native_market_ticker or event.channel != "trade":
            quarantined += 1
            continue
        if event.native_market_ticker not in selected:
            filtered += 1
            continue
        payload = _native_message(event.original_payload)
        try:
            validate_no_private_account_payload(payload)
        except ValueError:
            quarantined += 1
            continue
        trade_id = payload.get("trade_id")
        if (
            not event.native_market_ticker
            or event.native_market_ticker not in event.requested_market_tickers
            or not isinstance(trade_id, str | int)
            or isinstance(trade_id, bool)
        ):
            quarantined += 1
            continue
        try:
            trade = KalshiPublicTradeEvidence(
                campaign_id=event.campaign_id,
                market_ticker=event.native_market_ticker,
                connection_id=event.connection_id,
                segment_id=event.segment_id,
                local_row_index=event.local_row_index,
                received_at_utc=event.received_at_utc,
                payload_sha256=event.payload_sha256,
                native_trade_id=trade_id,
                native_sid=event.native_sid,
                native_seq=event.native_seq,
                native_exchange_ts=event.native_exchange_ts,
                native_exchange_ts_ms=event.native_exchange_ts_ms,
                native_trade_payload=payload,
            )
        except (TypeError, ValueError):
            quarantined += 1
            continue
        trades.append(trade)
    return PublicTradeEvidenceStream(
        selected_market_tickers=tuple(selected_market_tickers),
        trades=tuple(trades),
        filtered_nonselected_count=filtered,
        ignored_nontrade_count=ignored,
        quarantined_count=quarantined,
        status=_public_trade_stream_status(tuple(trades), quarantined),
    )


def record_rest_lifecycle(
    market_metadata: Mapping[str, object],
    *,
    selected_market_ticker: str,
    observed_at_utc: datetime,
    evaluated_at_utc: datetime,
    max_age_seconds: int,
) -> KalshiRestLifecycleEvidence:
    validate_no_secret_payload(market_metadata)
    _require_aware(observed_at_utc, "observed_at_utc")
    _require_aware(evaluated_at_utc, "evaluated_at_utc")
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    ticker = market_metadata.get("market_ticker") or market_metadata.get("ticker")
    if ticker != selected_market_ticker:
        raise ValueError("lifecycle observation must match the selected market")
    age = _age_seconds(evaluated_at_utc, observed_at_utc, "observed_at_utc")
    raw_status_value = market_metadata.get("raw_status")
    if not isinstance(raw_status_value, str):
        raw_status_value = market_metadata.get("status")
    normalized = normalize_kalshi_market_metadata({"status": raw_status_value})
    normalized_status = normalized.get("status")
    status = _lifecycle_status(normalized_status)
    mve_unsupported = _is_mve(market_metadata)
    validity = _lifecycle_validity(status, age, max_age_seconds, mve_unsupported)
    return KalshiRestLifecycleEvidence(
        market_ticker=selected_market_ticker,
        observed_at_utc=observed_at_utc,
        evaluated_at_utc=evaluated_at_utc,
        raw_status=raw_status_value if isinstance(raw_status_value, str) else None,
        normalized_status=(
            normalized_status if isinstance(normalized_status, str) else None
        ),
        lifecycle_status=status,
        validity=validity,
        observation_age_seconds=age,
        max_age_seconds=max_age_seconds,
        mve_unsupported=mve_unsupported,
    )


def write_public_trade_evidence(
    path: Path,
    stream: PublicTradeEvidenceStream,
) -> int:
    write_jsonl_records(path, stream.to_records())
    return stream.trade_count


def evaluate_evidence_freshness(
    *,
    evaluated_at_utc: datetime,
    transport_keepalive_observed_at_utc: datetime | None = None,
    transport_keepalive_source: str | None = None,
    lifecycle_observed_at_utc: datetime | None = None,
    orderbook_event_at_utc: datetime | None = None,
) -> EvidenceFreshness:
    _require_aware(evaluated_at_utc, "evaluated_at_utc")
    if (transport_keepalive_observed_at_utc is None) != (
        transport_keepalive_source is None
    ):
        raise ValueError("keepalive timestamp and source must be supplied together")
    keepalive_age = _optional_age(
        evaluated_at_utc,
        transport_keepalive_observed_at_utc,
        "transport_keepalive_observed_at_utc",
    )
    return EvidenceFreshness(
        evaluated_at_utc=evaluated_at_utc,
        transport_keepalive_status=(
            KeepaliveStatus.OBSERVED
            if keepalive_age is not None
            else KeepaliveStatus.UNKNOWN_NOT_OBSERVED
        ),
        transport_keepalive_source=transport_keepalive_source,
        transport_keepalive_age_seconds=keepalive_age,
        lifecycle_observation_age_seconds=_optional_age(
            evaluated_at_utc,
            lifecycle_observed_at_utc,
            "lifecycle_observed_at_utc",
        ),
        orderbook_event_quiet_interval_seconds=_optional_age(
            evaluated_at_utc,
            orderbook_event_at_utc,
            "orderbook_event_at_utc",
        ),
    )


def _native_message(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    message = payload.get("msg")
    return deepcopy(dict(message if isinstance(message, Mapping) else payload))


def _lifecycle_status(value: object) -> LifecycleStatus:
    return {
        "open": LifecycleStatus.OPEN,
        "closed": LifecycleStatus.CLOSED,
        "settled": LifecycleStatus.SETTLED,
        "paused": LifecycleStatus.PAUSED,
        "unopened": LifecycleStatus.UNOPENED,
    }.get(value, LifecycleStatus.UNKNOWN)


def _lifecycle_validity(
    status: LifecycleStatus,
    age_seconds: int,
    max_age_seconds: int,
    mve_unsupported: bool,
) -> LifecycleValidity:
    if mve_unsupported:
        return LifecycleValidity.MVE_UNSUPPORTED
    if age_seconds > max_age_seconds:
        return LifecycleValidity.STALE
    if status is LifecycleStatus.UNKNOWN:
        return LifecycleValidity.UNKNOWN_STATUS
    return LifecycleValidity.VALID


def _public_trade_stream_status(
    trades: tuple[KalshiPublicTradeEvidence, ...],
    quarantined_count: int,
) -> PublicTradeStreamStatus:
    if quarantined_count:
        return PublicTradeStreamStatus.QUARANTINED_INPUT
    if trades:
        return PublicTradeStreamStatus.OBSERVED
    return PublicTradeStreamStatus.QUIET_NO_PUBLIC_TRADES


def _is_mve(market_metadata: Mapping[str, object]) -> bool:
    return (
        market_metadata.get("is_mve") is True
        or str(market_metadata.get("market_type") or "").lower() == "mve"
        or bool(market_metadata.get("mve_collection_ticker"))
    )


def _optional_age(
    evaluated_at_utc: datetime,
    observed_at_utc: datetime | None,
    field_name: str,
) -> int | None:
    if observed_at_utc is None:
        return None
    _require_aware(observed_at_utc, field_name)
    return _age_seconds(evaluated_at_utc, observed_at_utc, field_name)


def _age_seconds(
    evaluated_at_utc: datetime,
    observed_at_utc: datetime,
    field_name: str,
) -> int:
    age = evaluated_at_utc - observed_at_utc
    total_seconds = age.total_seconds()
    if total_seconds < 0:
        raise ValueError(f"{field_name} must not be in the future")
    return ceil(total_seconds)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
