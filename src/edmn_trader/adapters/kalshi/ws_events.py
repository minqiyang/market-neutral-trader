"""Versioned native evidence envelopes for Kalshi WebSocket messages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from edmn_trader.data.payload_safety import (
    validate_no_private_account_payload,
    validate_no_secret_payload,
)

KALSHI_WS_RAW_SCHEMA_VERSION = "edmn.kalshi.ws.raw.v2"
KALSHI_WS_RECORD_TYPE = "kalshi_demo_ws_message"
CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION = (
    "edmn.kalshi.ws.subscription_identity.v1"
)


class SequenceState(StrEnum):
    SEQUENCE_NOT_OBSERVED = "SEQUENCE_NOT_OBSERVED"
    SEQUENCE_PRESENT_SEMANTICS_UNKNOWN = "SEQUENCE_PRESENT_SEMANTICS_UNKNOWN"
    SEQUENCE_OBSERVED_MONOTONIC = "SEQUENCE_OBSERVED_MONOTONIC"
    SEQUENCE_CONTIGUITY_VERIFIED = "SEQUENCE_CONTIGUITY_VERIFIED"
    SEQUENCE_GAP_DETECTED = "SEQUENCE_GAP_DETECTED"
    SEQUENCE_OUT_OF_ORDER = "SEQUENCE_OUT_OF_ORDER"
    SEQUENCE_DUPLICATE = "SEQUENCE_DUPLICATE"
    RESYNC_REQUIRED = "RESYNC_REQUIRED"
    RESYNCED_WITH_SNAPSHOT = "RESYNCED_WITH_SNAPSHOT"
    UNRECOVERED_GAP = "UNRECOVERED_GAP"


class SequenceContinuityPolicy(StrEnum):
    UNKNOWN = "UNKNOWN"
    CONTIGUOUS_INCREMENT = "CONTIGUOUS_INCREMENT"


class AdmissionStatus(StrEnum):
    ADMITTED = "ADMITTED"
    EXCLUDED = "EXCLUDED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SubscriptionBindingState(StrEnum):
    UNKNOWN = "UNKNOWN"
    REQUESTED = "REQUESTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    REQUEST_MISMATCH = "REQUEST_MISMATCH"


class ExclusionReason(StrEnum):
    DELTA_BEFORE_SNAPSHOT = "DELTA_BEFORE_SNAPSHOT"
    MISSING_MARKET_TICKER = "MISSING_MARKET_TICKER"
    UNREQUESTED_MARKET_TICKER = "UNREQUESTED_MARKET_TICKER"
    SEQUENCE_DUPLICATE = "SEQUENCE_DUPLICATE"
    SEQUENCE_OUT_OF_ORDER = "SEQUENCE_OUT_OF_ORDER"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    SUBSCRIPTION_IDENTITY_MISMATCH = "SUBSCRIPTION_IDENTITY_MISMATCH"


class ResyncState(StrEnum):
    RESYNC_REQUIRED = "RESYNC_REQUIRED"
    RESYNCED_WITH_SNAPSHOT = "RESYNCED_WITH_SNAPSHOT"


class SegmentBoundaryReason(StrEnum):
    INITIAL_CONNECTION = "INITIAL_CONNECTION"
    RECONNECTION = "RECONNECTION"
    NEW_SUBSCRIPTION = "NEW_SUBSCRIPTION"
    RESUBSCRIPTION = "RESUBSCRIPTION"
    SID_CHANGE = "SID_CHANGE"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"


class LegacyCompatibilityStatus(StrEnum):
    LEGACY_LOCAL_SEQUENCE_ONLY = "LEGACY_LOCAL_SEQUENCE_ONLY"


class KalshiWsSchemaCompatibilityError(ValueError):
    """Raised when a raw row uses an unsupported explicit schema."""


@dataclass(frozen=True, slots=True)
class KalshiWsRawEvent:
    campaign_id: str
    requested_market_tickers: tuple[str, ...]
    local_row_index: int
    connection_id: str
    segment_id: str
    segment_boundary_reason: SegmentBoundaryReason
    received_at_utc: datetime
    received_monotonic_ns: int
    payload_sha256: str
    channel: str
    subscription_id: str | int | None
    subscription_sid: str | int | None
    subscription_command_id: str | int | None
    admission_status: AdmissionStatus
    exclusion_reason: ExclusionReason | None
    sequence_continuity_policy: SequenceContinuityPolicy
    sequence_state: SequenceState
    resync_state: ResyncState
    native_type: str | None
    native_sid: str | int | None
    native_seq: str | int | None
    native_market_ticker: str | None
    native_market_id: str | None
    native_exchange_ts: str | int | float | None
    native_exchange_ts_ms: int | None
    original_payload: Mapping[str, Any]
    subscription_generation: int | None = None
    subscription_binding_id: str | None = None
    subscription_binding_state: SubscriptionBindingState = SubscriptionBindingState.UNKNOWN
    subscription_identity_model: str | None = None
    schema_version: str = KALSHI_WS_RAW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != KALSHI_WS_RAW_SCHEMA_VERSION:
            msg = f"unsupported Kalshi WebSocket raw schema: {self.schema_version}"
            raise KalshiWsSchemaCompatibilityError(msg)
        if not self.campaign_id or not self.connection_id or not self.segment_id:
            raise ValueError("campaign_id, connection_id, and segment_id are required")
        if not self.requested_market_tickers:
            raise ValueError("requested_market_tickers must not be empty")
        if self.local_row_index < 1:
            raise ValueError("local_row_index must be positive")
        if self.received_at_utc.tzinfo is None or self.received_at_utc.utcoffset() is None:
            raise ValueError("received_at_utc must be timezone-aware")
        if self.received_monotonic_ns < 0:
            raise ValueError("received_monotonic_ns must be non-negative")
        copied_payload = deepcopy(dict(self.original_payload))
        validate_no_private_account_payload(copied_payload, path="original_payload")
        if self.payload_sha256 != payload_sha256(copied_payload):
            raise ValueError("payload_sha256 does not match original_payload")
        native_type = _native_str(copied_payload, "type")
        expected_native_fields = {
            "native_type": native_type,
            "native_sid": _native_identifier(copied_payload, "sid"),
            "native_seq": _native_identifier(copied_payload, "seq"),
            "native_market_ticker": _native_str(copied_payload, "market_ticker"),
            "native_market_id": _native_str(copied_payload, "market_id"),
            "native_exchange_ts": _native_scalar(
                copied_payload,
                ("exchange_ts", "timestamp", "ts"),
            ),
            "native_exchange_ts_ms": _native_int(
                copied_payload,
                ("exchange_ts_ms", "timestamp_ms", "ts_ms"),
            ),
            "subscription_id": _native_identifier(copied_payload, "id"),
            "channel": _native_channel(copied_payload, native_type),
        }
        for field_name, expected in expected_native_fields.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} does not match original_payload")
        if self.native_sid is not None and self.subscription_sid != self.native_sid:
            raise ValueError("subscription_sid does not match native_sid")
        if self.subscription_identity_model not in {
            None,
            CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION,
        }:
            raise ValueError("unsupported subscription identity model")
        if (self.subscription_generation is None) != (
            self.subscription_binding_id is None
        ):
            raise ValueError("subscription generation and binding ID must appear together")
        if self.subscription_generation is not None and self.subscription_generation < 1:
            raise ValueError("subscription_generation must be positive")
        if self.sequence_state in {
            SequenceState.SEQUENCE_CONTIGUITY_VERIFIED,
            SequenceState.SEQUENCE_GAP_DETECTED,
        } and self.sequence_continuity_policy is not SequenceContinuityPolicy.CONTIGUOUS_INCREMENT:
            raise ValueError("continuity state requires CONTIGUOUS_INCREMENT policy")
        object.__setattr__(self, "requested_market_tickers", tuple(self.requested_market_tickers))
        object.__setattr__(self, "original_payload", copied_payload)

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> KalshiWsRawEvent:
        schema_version = _expect_str(record, "schema_version")
        if schema_version != KALSHI_WS_RAW_SCHEMA_VERSION:
            msg = f"unsupported Kalshi WebSocket raw schema: {schema_version}"
            raise KalshiWsSchemaCompatibilityError(msg)
        if _expect_str(record, "record_type") != KALSHI_WS_RECORD_TYPE:
            raise ValueError("record_type must identify a Kalshi Demo WebSocket message")
        if _expect_str(record, "venue") != "kalshi_demo":
            raise ValueError("venue must be kalshi_demo")

        original_payload = _expect_mapping(record, "original_payload")
        recorded_payload_hash = _expect_str(record, "payload_sha256")

        return cls(
            schema_version=schema_version,
            campaign_id=_expect_str(record, "campaign_id"),
            requested_market_tickers=tuple(
                _expect_str_list(record, "requested_market_tickers")
            ),
            local_row_index=_expect_int(record, "local_row_index"),
            connection_id=_expect_str(record, "connection_id"),
            segment_id=_expect_str(record, "segment_id"),
            segment_boundary_reason=_expect_enum(
                record,
                "segment_boundary_reason",
                SegmentBoundaryReason,
            ),
            received_at_utc=_parse_datetime(
                _expect_str(record, "received_at_utc"),
                "received_at_utc",
            ),
            received_monotonic_ns=_expect_int(record, "received_monotonic_ns"),
            payload_sha256=recorded_payload_hash,
            channel=_expect_str(record, "channel"),
            subscription_id=_optional_identifier(record, "subscription_id"),
            subscription_sid=_optional_identifier(record, "subscription_sid"),
            subscription_command_id=_optional_identifier(
                record,
                "subscription_command_id",
            ),
            admission_status=_expect_enum(record, "admission_status", AdmissionStatus),
            exclusion_reason=_optional_enum(record, "exclusion_reason", ExclusionReason),
            sequence_continuity_policy=_expect_enum(
                record,
                "sequence_continuity_policy",
                SequenceContinuityPolicy,
            ),
            sequence_state=_expect_enum(record, "sequence_state", SequenceState),
            resync_state=_expect_enum(record, "resync_state", ResyncState),
            native_type=_optional_str(record, "native_type"),
            native_sid=_optional_identifier(record, "native_sid"),
            native_seq=_optional_identifier(record, "native_seq"),
            native_market_ticker=_optional_str(record, "native_market_ticker"),
            native_market_id=_optional_str(record, "native_market_id"),
            native_exchange_ts=_optional_scalar(record, "native_exchange_ts"),
            native_exchange_ts_ms=_optional_int(record, "native_exchange_ts_ms"),
            original_payload=original_payload,
            subscription_generation=_optional_int(record, "subscription_generation"),
            subscription_binding_id=_optional_str(record, "subscription_binding_id"),
            subscription_binding_state=(
                _expect_enum(
                    record,
                    "subscription_binding_state",
                    SubscriptionBindingState,
                )
                if "subscription_binding_state" in record
                else SubscriptionBindingState.UNKNOWN
            ),
            subscription_identity_model=_optional_str(
                record,
                "subscription_identity_model",
            ),
        )

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "record_type": KALSHI_WS_RECORD_TYPE,
            "campaign_id": self.campaign_id,
            "venue": "kalshi_demo",
            "requested_market_tickers": list(self.requested_market_tickers),
            "local_row_index": self.local_row_index,
            "connection_id": self.connection_id,
            "segment_id": self.segment_id,
            "segment_boundary_reason": self.segment_boundary_reason,
            "received_at_utc": self.received_at_utc.isoformat(),
            "received_monotonic_ns": self.received_monotonic_ns,
            "payload_sha256": self.payload_sha256,
            "channel": self.channel,
            "subscription_id": self.subscription_id,
            "subscription_sid": self.subscription_sid,
            "subscription_command_id": self.subscription_command_id,
            "subscription_generation": self.subscription_generation,
            "subscription_binding_id": self.subscription_binding_id,
            "subscription_binding_state": self.subscription_binding_state,
            "subscription_identity_model": self.subscription_identity_model,
            "admission_status": self.admission_status,
            "exclusion_reason": self.exclusion_reason,
            "sequence_continuity_policy": self.sequence_continuity_policy,
            "sequence_state": self.sequence_state,
            "resync_state": self.resync_state,
            "native_type": self.native_type,
            "native_sid": self.native_sid,
            "native_seq": self.native_seq,
            "native_market_ticker": self.native_market_ticker,
            "native_market_id": self.native_market_id,
            "native_exchange_ts": self.native_exchange_ts,
            "native_exchange_ts_ms": self.native_exchange_ts_ms,
            "original_payload": deepcopy(dict(self.original_payload)),
        }


@dataclass(frozen=True, slots=True)
class LegacyKalshiWsRawEvent:
    """Explicit compatibility view for pre-v2 rows with local-only ordering."""

    campaign_id: str
    requested_market_tickers: tuple[str, ...]
    local_row_index: int
    received_at_utc: datetime
    legacy_message_type: str | None
    original_payload: Mapping[str, Any]
    compatibility_status: LegacyCompatibilityStatus = (
        LegacyCompatibilityStatus.LEGACY_LOCAL_SEQUENCE_ONLY
    )
    native_type: None = None
    native_seq: None = None
    native_sequence_evidence_eligible: bool = False
    sequence_state: SequenceState = SequenceState.SEQUENCE_NOT_OBSERVED

    def __post_init__(self) -> None:
        if not self.campaign_id or not self.requested_market_tickers:
            raise ValueError("legacy campaign and market tickers are required")
        if self.local_row_index < 1:
            raise ValueError("legacy local_row_index must be positive")
        if self.received_at_utc.tzinfo is None or self.received_at_utc.utcoffset() is None:
            raise ValueError("legacy received_at_utc must be timezone-aware")
        if (
            self.native_type is not None
            or self.native_seq is not None
            or self.native_sequence_evidence_eligible
            or self.sequence_state is not SequenceState.SEQUENCE_NOT_OBSERVED
        ):
            raise ValueError("legacy local sequence cannot become native sequence evidence")
        copied_payload = deepcopy(dict(self.original_payload))
        validate_no_secret_payload(copied_payload)
        validate_no_private_account_payload(copied_payload)
        object.__setattr__(self, "requested_market_tickers", tuple(self.requested_market_tickers))
        object.__setattr__(self, "original_payload", copied_payload)


def parse_kalshi_ws_raw_record(
    record: Mapping[str, Any],
) -> KalshiWsRawEvent | LegacyKalshiWsRawEvent:
    """Parse v2 rows or expose legacy rows without inventing native sequence data."""

    if "schema_version" in record:
        schema_version = record.get("schema_version")
        if schema_version != KALSHI_WS_RAW_SCHEMA_VERSION:
            msg = f"unsupported Kalshi WebSocket raw schema: {schema_version}"
            raise KalshiWsSchemaCompatibilityError(msg)
        return KalshiWsRawEvent.from_record(record)

    if record.get("record_type") != KALSHI_WS_RECORD_TYPE:
        raise KalshiWsSchemaCompatibilityError(
            "unversioned row is not a recognized legacy Kalshi WebSocket record"
        )
    if record.get("venue") != "kalshi_demo":
        raise KalshiWsSchemaCompatibilityError(
            "unversioned row is not a Kalshi Demo WebSocket record"
        )
    payload = _expect_mapping(record, "payload")
    validate_no_secret_payload(payload)
    validate_no_private_account_payload(payload)
    return LegacyKalshiWsRawEvent(
        campaign_id=_expect_str(record, "campaign_id"),
        requested_market_tickers=tuple(_expect_str_list(record, "market_tickers")),
        local_row_index=_expect_int(record, "sequence"),
        received_at_utc=_parse_datetime(
            _expect_str(record, "received_at"),
            "received_at",
        ),
        legacy_message_type=_optional_str(record, "message_type"),
        original_payload=payload,
    )


@dataclass(slots=True)
class _SubscriptionBinding:
    channel: str
    command_id: str | int
    generation: int
    binding_id: str
    sid: str | int | None = None
    state: SubscriptionBindingState = SubscriptionBindingState.REQUESTED


class KalshiWsIntegrityTracker:
    """Assign local transport context without asserting native continuity."""

    def __init__(
        self,
        *,
        campaign_id: str,
        requested_market_tickers: tuple[str, ...],
        continuity_policy: SequenceContinuityPolicy = SequenceContinuityPolicy.UNKNOWN,
    ) -> None:
        if not campaign_id:
            raise ValueError("campaign_id is required")
        if not requested_market_tickers:
            raise ValueError("requested_market_tickers must not be empty")
        self.campaign_id = campaign_id
        self.requested_market_tickers = tuple(requested_market_tickers)
        self.continuity_policy = SequenceContinuityPolicy(continuity_policy)
        self._connection_number = 0
        self._segment_number = 0
        self._connection_id: str | None = None
        self._segment_id: str | None = None
        self._segment_boundary_reason = SegmentBoundaryReason.INITIAL_CONNECTION
        self._binding_generations: dict[str, int] = {}
        self._bindings: dict[str, _SubscriptionBinding] = {}
        self._snapshot_market_tickers: set[str] = set()
        self._last_native_seq: int | None = None

    @property
    def connection_id(self) -> str:
        if self._connection_id is None:
            raise RuntimeError("no active connection")
        return self._connection_id

    @property
    def segment_id(self) -> str:
        if self._segment_id is None:
            raise RuntimeError("no active segment")
        return self._segment_id

    def start_connection(self) -> None:
        self._connection_number += 1
        reason = (
            SegmentBoundaryReason.INITIAL_CONNECTION
            if self._connection_number == 1
            else SegmentBoundaryReason.RECONNECTION
        )
        self._connection_id = f"{self.campaign_id}:connection:{self._connection_number:04d}"
        self._start_segment(reason)
        self._bindings.clear()

    def bind_subscription(
        self,
        *,
        command_id: str | int,
        channels: tuple[str, ...] = ("orderbook_delta",),
    ) -> None:
        if self._connection_id is None:
            raise RuntimeError("start_connection must be called before bind_subscription")
        if not channels:
            raise ValueError("channels must not be empty")
        if "orderbook_delta" in channels:
            reason = (
                SegmentBoundaryReason.RESUBSCRIPTION
                if self._binding_generations.get("orderbook_delta", 0) > 0
                else SegmentBoundaryReason.NEW_SUBSCRIPTION
            )
            self._start_segment(reason)
        for channel in channels:
            generation = self._binding_generations.get(channel, 0) + 1
            self._binding_generations[channel] = generation
            self._bindings[channel] = _SubscriptionBinding(
                channel=channel,
                command_id=command_id,
                generation=generation,
                binding_id=(
                    f"{self.connection_id}:subscription:{channel}:{generation:04d}"
                ),
            )

    def record(
        self,
        payload: Mapping[str, Any],
        *,
        local_row_index: int,
        received_at_utc: datetime,
        received_monotonic_ns: int,
    ) -> KalshiWsRawEvent:
        if self._connection_id is None or self._segment_id is None:
            raise RuntimeError("start_connection must be called before record")
        if local_row_index < 1:
            raise ValueError("local_row_index must be positive")
        if received_at_utc.tzinfo is None or received_at_utc.utcoffset() is None:
            raise ValueError("received_at_utc must be timezone-aware")
        if received_monotonic_ns < 0:
            raise ValueError("received_monotonic_ns must be non-negative")
        validate_no_secret_payload(payload)
        validate_no_private_account_payload(payload)

        native_type = _native_str(payload, "type")
        channel = _native_channel(payload, native_type)
        binding = self._bindings.get(channel)
        native_market_ticker = _native_str(payload, "market_ticker")
        is_orderbook = native_type in {"orderbook_snapshot", "orderbook_delta"}
        has_requested_market = native_market_ticker in self.requested_market_tickers
        native_sid = _native_identifier(payload, "sid")
        native_command_id = _native_identifier(payload, "id")
        native_channels = _native_channels(payload)
        if (
            binding is None
            and native_type in {"subscribed", "ack", "ok"}
            and len(native_channels) > 1
            and native_sid is None
        ):
            for acknowledged_channel in native_channels:
                acknowledged_binding = self._bindings.get(acknowledged_channel)
                if (
                    acknowledged_binding is not None
                    and native_command_id == acknowledged_binding.command_id
                ):
                    acknowledged_binding.state = SubscriptionBindingState.ACKNOWLEDGED
        if binding is not None and native_type in {"subscribed", "ack", "ok"}:
            if native_command_id != binding.command_id:
                binding.state = SubscriptionBindingState.REQUEST_MISMATCH
            else:
                binding.state = SubscriptionBindingState.ACKNOWLEDGED
                if native_sid is not None and binding.sid is None:
                    binding.sid = native_sid
        elif binding is not None and native_type in {"error", "rejected"}:
            binding.state = (
                SubscriptionBindingState.REJECTED
                if native_command_id == binding.command_id
                else SubscriptionBindingState.REQUEST_MISMATCH
            )
        elif is_orderbook and binding is not None and binding.sid is None:
            binding.sid = native_sid
        native_seq = _native_identifier(payload, "seq")
        if (
            native_type == "orderbook_snapshot"
            and has_requested_market
            and not self._snapshot_market_tickers
        ):
            self._last_native_seq = None
        sequence_state = self._sequence_state(
            native_seq,
            continuity_eligible=is_orderbook and has_requested_market,
        )
        admission_status = AdmissionStatus.NOT_APPLICABLE
        exclusion_reason = _sequence_exclusion_reason(sequence_state)
        integrity_failure = exclusion_reason is not None
        if (
            native_type in {"orderbook_snapshot", "orderbook_delta", "trade"}
            and binding is not None
            and binding.sid is not None
            and native_sid is not None
            and native_sid != binding.sid
        ):
            exclusion_reason = ExclusionReason.SUBSCRIPTION_IDENTITY_MISMATCH
            integrity_failure = True
        resync_state = ResyncState.RESYNC_REQUIRED
        if integrity_failure:
            admission_status = AdmissionStatus.EXCLUDED
        elif is_orderbook and native_market_ticker is None:
            admission_status = AdmissionStatus.EXCLUDED
            exclusion_reason = ExclusionReason.MISSING_MARKET_TICKER
        elif is_orderbook and not has_requested_market:
            admission_status = AdmissionStatus.EXCLUDED
            exclusion_reason = ExclusionReason.UNREQUESTED_MARKET_TICKER
        elif native_type == "orderbook_snapshot":
            admission_status = AdmissionStatus.ADMITTED
            self._snapshot_market_tickers.add(native_market_ticker)
            resync_state = ResyncState.RESYNCED_WITH_SNAPSHOT
        elif native_type == "orderbook_delta":
            if native_market_ticker in self._snapshot_market_tickers:
                admission_status = AdmissionStatus.ADMITTED
                resync_state = ResyncState.RESYNCED_WITH_SNAPSHOT
            else:
                admission_status = AdmissionStatus.EXCLUDED
                exclusion_reason = ExclusionReason.DELTA_BEFORE_SNAPSHOT
                self._last_native_seq = None

        original_payload = deepcopy(dict(payload))
        event = KalshiWsRawEvent(
            campaign_id=self.campaign_id,
            requested_market_tickers=self.requested_market_tickers,
            local_row_index=local_row_index,
            connection_id=self._connection_id,
            segment_id=self._segment_id,
            segment_boundary_reason=self._segment_boundary_reason,
            received_at_utc=received_at_utc,
            received_monotonic_ns=received_monotonic_ns,
            payload_sha256=payload_sha256(original_payload),
            channel=channel,
            subscription_id=native_command_id,
            subscription_sid=native_sid,
            subscription_command_id=(binding.command_id if binding is not None else None),
            admission_status=admission_status,
            exclusion_reason=exclusion_reason,
            sequence_continuity_policy=self.continuity_policy,
            sequence_state=sequence_state,
            resync_state=resync_state,
            native_type=native_type,
            native_sid=native_sid,
            native_seq=native_seq,
            native_market_ticker=native_market_ticker,
            native_market_id=_native_str(payload, "market_id"),
            native_exchange_ts=_native_scalar(payload, ("exchange_ts", "timestamp", "ts")),
            native_exchange_ts_ms=_native_int(
                payload,
                ("exchange_ts_ms", "timestamp_ms", "ts_ms"),
            ),
            original_payload=original_payload,
            subscription_generation=(binding.generation if binding is not None else None),
            subscription_binding_id=(binding.binding_id if binding is not None else None),
            subscription_binding_state=(
                binding.state if binding is not None else SubscriptionBindingState.UNKNOWN
            ),
            subscription_identity_model=CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION,
        )
        if (
            integrity_failure
            and exclusion_reason is not ExclusionReason.SUBSCRIPTION_IDENTITY_MISMATCH
            and is_orderbook
        ):
            self._start_segment(SegmentBoundaryReason.INTEGRITY_FAILURE)
        return event

    def _start_segment(self, reason: SegmentBoundaryReason) -> None:
        self._segment_number += 1
        self._segment_id = f"{self.campaign_id}:segment:{self._segment_number:04d}"
        self._segment_boundary_reason = reason
        self._snapshot_market_tickers.clear()
        self._last_native_seq = None

    def _sequence_state(
        self,
        native_seq: str | int | None,
        *,
        continuity_eligible: bool,
    ) -> SequenceState:
        if native_seq is None:
            return SequenceState.SEQUENCE_NOT_OBSERVED
        if not continuity_eligible or not isinstance(native_seq, int):
            return SequenceState.SEQUENCE_PRESENT_SEMANTICS_UNKNOWN
        if self._last_native_seq is None:
            self._last_native_seq = native_seq
            return SequenceState.SEQUENCE_PRESENT_SEMANTICS_UNKNOWN
        if native_seq == self._last_native_seq:
            return SequenceState.SEQUENCE_DUPLICATE
        if native_seq < self._last_native_seq:
            return SequenceState.SEQUENCE_OUT_OF_ORDER
        previous = self._last_native_seq
        self._last_native_seq = native_seq
        if self.continuity_policy is SequenceContinuityPolicy.CONTIGUOUS_INCREMENT:
            if native_seq == previous + 1:
                return SequenceState.SEQUENCE_CONTIGUITY_VERIFIED
            return SequenceState.SEQUENCE_GAP_DETECTED
        return SequenceState.SEQUENCE_OBSERVED_MONOTONIC


def payload_sha256(payload: Mapping[str, Any]) -> str:
    """Hash canonical UTF-8 JSON for the exact parsed native payload."""

    validate_no_secret_payload(payload)
    validate_no_private_account_payload(payload)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence_exclusion_reason(sequence_state: SequenceState) -> ExclusionReason | None:
    return {
        SequenceState.SEQUENCE_DUPLICATE: ExclusionReason.SEQUENCE_DUPLICATE,
        SequenceState.SEQUENCE_OUT_OF_ORDER: ExclusionReason.SEQUENCE_OUT_OF_ORDER,
        SequenceState.SEQUENCE_GAP_DETECTED: ExclusionReason.SEQUENCE_GAP,
    }.get(sequence_state)


def _native_object(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = payload.get("msg")
    return nested if isinstance(nested, Mapping) else {}


def _native_scalar(
    payload: Mapping[str, Any],
    keys: tuple[str, ...],
) -> str | int | float | None:
    nested = _native_object(payload)
    for source in (payload, nested):
        for key in keys:
            value = source.get(key)
            if isinstance(value, str | int | float) and not isinstance(value, bool):
                return value
    return None


def _native_identifier(payload: Mapping[str, Any], key: str) -> str | int | None:
    value = _native_scalar(payload, (key,))
    return value if isinstance(value, str | int) else None


def _native_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = _native_scalar(payload, (key,))
    return value if isinstance(value, str) else None


def _native_int(payload: Mapping[str, Any], keys: tuple[str, ...]) -> int | None:
    value = _native_scalar(payload, keys)
    return value if isinstance(value, int) else None


def _native_channel(payload: Mapping[str, Any], native_type: str | None) -> str:
    channel = _native_str(payload, "channel")
    if channel is not None:
        return channel
    if native_type in {"orderbook_snapshot", "orderbook_delta"}:
        return "orderbook_delta"
    return native_type or "unknown"


def _native_channels(payload: Mapping[str, Any]) -> tuple[str, ...]:
    nested = _native_object(payload)
    values = nested.get("channels", payload.get("channels"))
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, str))


def _expect_mapping(record: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = record.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _expect_str(record: Mapping[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _optional_str(record: Mapping[str, Any], field_name: str) -> str | None:
    value = record.get(field_name)
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{field_name} must be a string or null")


def _expect_int(record: Mapping[str, Any], field_name: str) -> int:
    value = record.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _optional_int(record: Mapping[str, Any], field_name: str) -> int | None:
    value = record.get(field_name)
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be an integer or null")


def _optional_identifier(
    record: Mapping[str, Any],
    field_name: str,
) -> str | int | None:
    value = record.get(field_name)
    if value is None:
        return None
    if isinstance(value, str | int) and not isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a string, integer, or null")


def _optional_scalar(
    record: Mapping[str, Any],
    field_name: str,
) -> str | int | float | None:
    value = record.get(field_name)
    if value is None:
        return None
    if isinstance(value, str | int | float) and not isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a scalar or null")


def _expect_str_list(record: Mapping[str, Any], field_name: str) -> list[str]:
    value = record.get(field_name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a string list")
    return value


def _expect_enum[
    EnumType: StrEnum
](record: Mapping[str, Any], field_name: str, enum_type: type[EnumType]) -> EnumType:
    value = record.get(field_name)
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} has an unsupported value") from exc


def _optional_enum[
    EnumType: StrEnum
](
    record: Mapping[str, Any],
    field_name: str,
    enum_type: type[EnumType],
) -> EnumType | None:
    if record.get(field_name) is None:
        return None
    return _expect_enum(record, field_name, enum_type)


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed
