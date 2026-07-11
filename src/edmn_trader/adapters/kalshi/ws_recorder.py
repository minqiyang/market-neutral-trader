"""Read-only Kalshi Demo selected-market WebSocket recorder."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edmn_trader.adapters.kalshi.public_evidence import (
    ConnectionEvidenceEvent,
    ConnectionEvidenceType,
)
from edmn_trader.adapters.kalshi.ws_auth import (
    KALSHI_DEMO_WS_URL,
    KalshiWsAuthBlocked,
    KalshiWsAuthConfig,
    build_kalshi_ws_headers,
)
from edmn_trader.adapters.kalshi.ws_events import KalshiWsIntegrityTracker, KalshiWsRawEvent
from edmn_trader.data.jsonl import append_jsonl_record, write_jsonl_records

WebSocketFactory = Callable[..., Any]
ProgressCallback = Callable[[dict[str, object]], None]
EventCallback = Callable[[KalshiWsRawEvent], None]
ConnectionCallback = Callable[[ConnectionEvidenceEvent], None]
TickCallback = Callable[[datetime], None]


@dataclass(frozen=True, slots=True)
class KalshiWsRecorderConfig:
    campaign_id: str
    market_tickers: tuple[str, ...]
    raw_events_path: Path
    duration_seconds: int
    max_events: int = 500
    max_reconnects: int = 0
    persist_legacy_raw_events: bool = True
    url: str = KALSHI_DEMO_WS_URL

    def __post_init__(self) -> None:
        if self.url != KALSHI_DEMO_WS_URL:
            raise KalshiWsAuthBlocked("NON_DEMO_WS_ENDPOINT_REJECTED")
        if not self.market_tickers:
            raise ValueError("market_tickers must contain at least one ticker")
        if self.duration_seconds < 1:
            raise ValueError("duration_seconds must be positive")
        if self.max_events < 1:
            raise ValueError("max_events must be positive")
        if self.max_reconnects < 0:
            raise ValueError("max_reconnects must be non-negative")
        if not isinstance(self.persist_legacy_raw_events, bool):
            raise ValueError("persist_legacy_raw_events must be Boolean")


@dataclass(frozen=True, slots=True)
class KalshiWsRecorderResult:
    status: str
    blocker_code: str | None
    connection_established: bool
    subscription_acknowledged: bool
    event_count: int
    snapshot_count: int
    delta_count: int
    trade_count: int
    status_update_count: int
    heartbeat_count: int
    error_count: int
    disconnect_count: int
    reconnect_count: int
    gap_count: int
    last_event_time: str | None
    stale_seconds: int | None
    raw_event_path: str
    raw_event_sha256: str | None

    @property
    def source_type(self) -> str:
        return _source_type(self.snapshot_count, self.delta_count, self.trade_count)


def record_kalshi_demo_ws_orderbook(
    config: KalshiWsRecorderConfig,
    auth: KalshiWsAuthConfig,
    *,
    websocket_factory: WebSocketFactory | None = None,
    now: Callable[[], datetime] | None = None,
    progress_callback: ProgressCallback | None = None,
    event_callback: EventCallback | None = None,
    connection_callback: ConnectionCallback | None = None,
    tick_callback: TickCallback | None = None,
    monotonic: Callable[[], float] | None = None,
    monotonic_ns: Callable[[], int] | None = None,
) -> KalshiWsRecorderResult:
    clock = now or (lambda: datetime.now(UTC))
    monotonic_clock = monotonic or time.monotonic
    monotonic_ns_clock = monotonic_ns or time.monotonic_ns
    if not config.persist_legacy_raw_events and event_callback is None:
        raise ValueError("D2 runtime persistence requires an event callback")
    timestamp_ms = int(clock().timestamp() * 1000)
    try:
        headers = build_kalshi_ws_headers(auth, timestamp_ms=timestamp_ms)
    except KalshiWsAuthBlocked as exc:
        return _blocked(config, exc.code)

    factory = websocket_factory or _websockets_connect
    event_count = 0
    type_counts: Counter[str] = Counter()
    last_event_time: str | None = None
    all_subscriptions_acknowledged = True
    current_subscription_acknowledged = False
    reconnect_count = 0
    integrity_tracker = KalshiWsIntegrityTracker(
        campaign_id=config.campaign_id,
        requested_market_tickers=config.market_tickers,
    )
    deadline = monotonic_clock() + config.duration_seconds
    if config.persist_legacy_raw_events:
        write_jsonl_records(config.raw_events_path, [])
    previous_connection_id: str | None = None
    previous_segment_id: str | None = None
    while event_count < config.max_events and monotonic_clock() < deadline:
        opened = False
        try:
            headers = build_kalshi_ws_headers(auth, timestamp_ms=int(clock().timestamp() * 1000))
            with factory(config.url, additional_headers=headers, open_timeout=10) as websocket:
                integrity_tracker.start_connection()
                opened = True
                current_subscription_acknowledged = False
                _emit_connection(
                    connection_callback,
                    event_type=(
                        ConnectionEvidenceType.CONNECTION_OPEN
                        if reconnect_count == 0
                        else ConnectionEvidenceType.RECONNECT
                    ),
                    observed_at_utc=clock(),
                    tracker=integrity_tracker,
                    reason="initial_connect" if reconnect_count == 0 else "read_reconnect",
                    previous_connection_id=previous_connection_id,
                    previous_segment_id=previous_segment_id,
                )
                websocket.send(_subscription_payload(config.market_tickers))
                integrity_tracker.bind_subscription(command_id=1)
                if reconnect_count:
                    _emit_connection(
                        connection_callback,
                        event_type=ConnectionEvidenceType.RESUBSCRIPTION,
                        observed_at_utc=clock(),
                        tracker=integrity_tracker,
                        reason="subscription_rebound_after_reconnect",
                        previous_connection_id=previous_connection_id,
                        previous_segment_id=previous_segment_id,
                    )
                while event_count < config.max_events and monotonic_clock() < deadline:
                    if tick_callback is not None:
                        tick_callback(clock())
                    try:
                        raw = websocket.recv(
                            timeout=min(30.0, max(0.1, deadline - monotonic_clock()))
                        )
                    except TimeoutError:
                        continue
                    received_at = clock()
                    received_monotonic_ns = monotonic_ns_clock()
                    payload = _loads(raw)
                    message_type = _message_type(payload)
                    acknowledged = _is_subscription_ack(payload, message_type)
                    rejected = _is_subscription_rejection(payload, message_type)
                    if acknowledged and not current_subscription_acknowledged:
                        current_subscription_acknowledged = True
                        _emit_connection(
                            connection_callback,
                            event_type=ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
                            observed_at_utc=received_at,
                            tracker=integrity_tracker,
                            reason="selected_market_channels_acknowledged",
                            previous_connection_id=previous_connection_id,
                            previous_segment_id=previous_segment_id,
                        )
                    if rejected:
                        _emit_connection(
                            connection_callback,
                            event_type=ConnectionEvidenceType.SUBSCRIPTION_REJECTED,
                            observed_at_utc=received_at,
                            tracker=integrity_tracker,
                            reason="selected_market_channels_rejected",
                            previous_connection_id=previous_connection_id,
                            previous_segment_id=previous_segment_id,
                        )
                    event = integrity_tracker.record(
                        payload,
                        local_row_index=event_count + 1,
                        received_at_utc=received_at,
                        received_monotonic_ns=received_monotonic_ns,
                    )
                    row = event.to_record()
                    event_count += 1
                    type_counts[message_type] += 1
                    last_event_time = _row_received_at(row)
                    if config.persist_legacy_raw_events:
                        append_jsonl_record(config.raw_events_path, row)
                    if event_callback is not None:
                        event_callback(event)
                    if progress_callback is not None:
                        progress_callback(
                            _progress(
                                event_count=event_count,
                                type_counts=type_counts,
                                last_event_time=last_event_time,
                                acknowledged=(
                                    all_subscriptions_acknowledged
                                    and current_subscription_acknowledged
                                ),
                                raw_events_path=config.raw_events_path,
                                reconnect_count=reconnect_count,
                                include_raw_hash=config.persist_legacy_raw_events,
                            )
                        )
        except KalshiWsAuthBlocked as exc:
            return _blocked(config, exc.code)
        except Exception as exc:
            if opened:
                _emit_connection(
                    connection_callback,
                    event_type=ConnectionEvidenceType.CONNECTION_ERROR,
                    observed_at_utc=clock(),
                    tracker=integrity_tracker,
                    reason=type(exc).__name__,
                    previous_connection_id=previous_connection_id,
                    previous_segment_id=previous_segment_id,
                )
            if event_count and reconnect_count < config.max_reconnects:
                previous_connection_id = integrity_tracker.connection_id
                previous_segment_id = integrity_tracker.segment_id
                reconnect_count += 1
                time.sleep(min(5.0, reconnect_count))
                continue
            code = "SUBSCRIPTION_REJECTED" if event_count else "AUTH_SIGNATURE_FAILED"
            if str(exc):
                code = "WEBSOCKET_READ_FAILED" if event_count else code
            return _write_result(
                config,
                event_count=event_count,
                type_counts=type_counts,
                last_event_time=last_event_time,
                blocker_code=code,
                acknowledged=(
                    all_subscriptions_acknowledged
                    and current_subscription_acknowledged
                ),
                reconnect_count=reconnect_count,
            )
        finally:
            if opened:
                _emit_connection(
                    connection_callback,
                    event_type=ConnectionEvidenceType.CONNECTION_CLOSE,
                    observed_at_utc=clock(),
                    tracker=integrity_tracker,
                    reason="connection_context_closed",
                    previous_connection_id=previous_connection_id,
                    previous_segment_id=previous_segment_id,
                )
                all_subscriptions_acknowledged &= current_subscription_acknowledged

    if not event_count:
        return _write_result(
            config,
            event_count=0,
            type_counts=type_counts,
            last_event_time=None,
            blocker_code="NO_MESSAGES_RECEIVED",
            acknowledged=False,
        )
    return _write_result(
        config,
        event_count=event_count,
        type_counts=type_counts,
        last_event_time=last_event_time,
        blocker_code=None,
        acknowledged=all_subscriptions_acknowledged,
        reconnect_count=reconnect_count,
    )


def _websockets_connect(*args: object, **kwargs: object) -> object:
    try:
        from websockets.sync.client import connect
    except ImportError as exc:
        raise KalshiWsAuthBlocked("WEBSOCKET_LIBRARY_MISSING") from exc
    return connect(*args, **kwargs)


def _subscription_payload(market_tickers: tuple[str, ...]) -> str:
    return json.dumps(
        {
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta", "trade"],
                "market_tickers": list(market_tickers),
            },
        },
        sort_keys=True,
    )


def _loads(raw: object) -> dict[str, object]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = json.loads(str(raw))
    if not isinstance(payload, dict):
        raise ValueError("Kalshi WebSocket payload must be a JSON object")
    return payload


def _message_type(payload: Mapping[str, object]) -> str:
    nested = payload.get("msg")
    if isinstance(nested, Mapping):
        for key in ("type", "event_type"):
            if nested.get(key):
                return str(nested[key])
    for key in ("type", "event_type", "channel"):
        if payload.get(key):
            return str(payload[key])
    return "unknown"


def _is_subscription_ack(payload: Mapping[str, object], message_type: str) -> bool:
    lowered = message_type.lower()
    if "subscribed" in lowered or lowered in {"ack", "ok"}:
        return True
    return str(payload.get("cmd") or "").lower() == "subscribe" and not payload.get("error")


def _is_subscription_rejection(payload: Mapping[str, object], message_type: str) -> bool:
    lowered = message_type.lower()
    return (
        "reject" in lowered
        or lowered == "error" and bool(payload.get("error"))
        or str(payload.get("cmd") or "").lower() == "subscribe" and bool(payload.get("error"))
    )


def _write_result(
    config: KalshiWsRecorderConfig,
    *,
    event_count: int,
    type_counts: Mapping[str, int],
    last_event_time: str | None,
    blocker_code: str | None,
    acknowledged: bool,
    reconnect_count: int = 0,
) -> KalshiWsRecorderResult:
    if config.persist_legacy_raw_events and not config.raw_events_path.exists():
        write_jsonl_records(config.raw_events_path, [])
    sha = (
        _sha256(config.raw_events_path)
        if event_count and config.persist_legacy_raw_events
        else None
    )
    return KalshiWsRecorderResult(
        status="blocked" if blocker_code else "ok",
        blocker_code=blocker_code,
        connection_established=bool(event_count) or blocker_code == "NO_MESSAGES_RECEIVED",
        subscription_acknowledged=acknowledged,
        event_count=event_count,
        snapshot_count=_matching_count(type_counts, "orderbook_snapshot"),
        delta_count=_matching_count(type_counts, "orderbook_delta"),
        trade_count=type_counts.get("trade", 0),
        status_update_count=_matching_count(type_counts, "status"),
        heartbeat_count=_matching_count(type_counts, "heartbeat"),
        error_count=_matching_count(type_counts, "error") + (1 if blocker_code else 0),
        disconnect_count=0,
        reconnect_count=reconnect_count,
        gap_count=0,
        last_event_time=last_event_time,
        stale_seconds=None,
        raw_event_path=str(config.raw_events_path),
        raw_event_sha256=sha,
    )


def _blocked(config: KalshiWsRecorderConfig, code: str) -> KalshiWsRecorderResult:
    return KalshiWsRecorderResult(
        status="blocked",
        blocker_code=code,
        connection_established=False,
        subscription_acknowledged=False,
        event_count=0,
        snapshot_count=0,
        delta_count=0,
        trade_count=0,
        status_update_count=0,
        heartbeat_count=0,
        error_count=1,
        disconnect_count=0,
        reconnect_count=0,
        gap_count=0,
        last_event_time=None,
        stale_seconds=None,
        raw_event_path=str(config.raw_events_path),
        raw_event_sha256=None,
    )


def _progress(
    *,
    event_count: int,
    type_counts: Mapping[str, int],
    last_event_time: str | None,
    acknowledged: bool,
    raw_events_path: Path,
    reconnect_count: int = 0,
    include_raw_hash: bool = True,
) -> dict[str, object]:
    return {
        "connection_established": True,
        "subscription_acknowledged": acknowledged,
        "event_count": event_count,
        "snapshot_count": _matching_count(type_counts, "orderbook_snapshot"),
        "delta_count": _matching_count(type_counts, "orderbook_delta"),
        "trade_count": type_counts.get("trade", 0),
        "status_update_count": _matching_count(type_counts, "status"),
        "heartbeat_count": _matching_count(type_counts, "heartbeat"),
        "error_count": _matching_count(type_counts, "error"),
        "reconnect_count": reconnect_count,
        "last_event_time": last_event_time,
        "source_type": _source_type(
            _matching_count(type_counts, "orderbook_snapshot"),
            _matching_count(type_counts, "orderbook_delta"),
            type_counts.get("trade", 0),
        ),
        "raw_event_path": str(raw_events_path),
        "raw_event_sha256": (
            _sha256(raw_events_path) if include_raw_hash and event_count else None
        ),
    }


def _emit_connection(
    callback: ConnectionCallback | None,
    *,
    event_type: ConnectionEvidenceType,
    observed_at_utc: datetime,
    tracker: KalshiWsIntegrityTracker,
    reason: str,
    previous_connection_id: str | None,
    previous_segment_id: str | None,
) -> None:
    if callback is None:
        return
    callback(
        ConnectionEvidenceEvent(
            event_type=event_type,
            observed_at_utc=observed_at_utc,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason=reason,
            previous_connection_id=previous_connection_id,
            previous_segment_id=previous_segment_id,
        )
    )


def _matching_count(counts: Mapping[str, int], pattern: str) -> int:
    return sum(count for message_type, count in counts.items() if pattern in message_type)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_payload(row: Mapping[str, object]) -> Mapping[str, object] | None:
    payload = row.get("original_payload", row.get("payload"))
    return payload if isinstance(payload, Mapping) else None


def _row_received_at(row: Mapping[str, object]) -> str | None:
    value = row.get("received_at_utc", row.get("received_at"))
    return str(value) if value is not None else None


def _source_type(snapshot_count: int, delta_count: int, trade_count: int) -> str:
    if delta_count:
        return "WEBSOCKET_DELTA"
    if snapshot_count:
        return "WEBSOCKET_SNAPSHOT"
    if trade_count:
        return "WEBSOCKET_PUBLIC_TRADE"
    return "WEBSOCKET_NO_ORDERBOOK"
