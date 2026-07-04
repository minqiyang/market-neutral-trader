"""Read-only Kalshi Demo WebSocket orderbook recorder."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edmn_trader.adapters.kalshi.ws_auth import (
    KALSHI_DEMO_WS_URL,
    KalshiWsAuthBlocked,
    KalshiWsAuthConfig,
    build_kalshi_ws_headers,
)
from edmn_trader.data.jsonl import append_jsonl_record, write_jsonl_records

WebSocketFactory = Callable[..., Any]
ProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class KalshiWsRecorderConfig:
    campaign_id: str
    market_tickers: tuple[str, ...]
    raw_events_path: Path
    duration_seconds: int
    max_events: int = 500
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
        return "WEBSOCKET_DELTA" if self.delta_count else "WEBSOCKET_SNAPSHOT"


def record_kalshi_demo_ws_orderbook(
    config: KalshiWsRecorderConfig,
    auth: KalshiWsAuthConfig,
    *,
    websocket_factory: WebSocketFactory | None = None,
    now: Callable[[], datetime] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> KalshiWsRecorderResult:
    clock = now or (lambda: datetime.now(UTC))
    timestamp_ms = int(clock().timestamp() * 1000)
    try:
        headers = build_kalshi_ws_headers(auth, timestamp_ms=timestamp_ms)
    except KalshiWsAuthBlocked as exc:
        return _blocked(config, exc.code)

    factory = websocket_factory or _websockets_connect
    rows: list[dict[str, object]] = []
    subscription_acknowledged = False
    write_jsonl_records(config.raw_events_path, [])
    try:
        with factory(config.url, additional_headers=headers, open_timeout=10) as websocket:
            websocket.send(_subscription_payload(config.market_tickers))
            deadline = time.monotonic() + config.duration_seconds
            while len(rows) < config.max_events and time.monotonic() < deadline:
                try:
                    raw = websocket.recv(timeout=min(30.0, max(0.1, deadline - time.monotonic())))
                except TimeoutError:
                    continue
                received_at = clock()
                payload = _loads(raw)
                message_type = _message_type(payload)
                subscription_acknowledged = subscription_acknowledged or _is_subscription_ack(
                    payload,
                    message_type,
                )
                row = {
                    "record_type": "kalshi_demo_ws_message",
                    "campaign_id": config.campaign_id,
                    "venue": "kalshi_demo",
                    "market_tickers": list(config.market_tickers),
                    "sequence": len(rows) + 1,
                    "received_at": received_at.isoformat(),
                    "message_type": message_type,
                    "payload": payload,
                }
                rows.append(row)
                append_jsonl_record(config.raw_events_path, row)
                if progress_callback is not None:
                    progress_callback(
                        _progress(
                            rows,
                            acknowledged=subscription_acknowledged,
                            raw_events_path=config.raw_events_path,
                        )
                    )
    except KalshiWsAuthBlocked as exc:
        return _blocked(config, exc.code)
    except Exception as exc:
        code = "SUBSCRIPTION_REJECTED" if rows else "AUTH_SIGNATURE_FAILED"
        if str(exc):
            code = "WEBSOCKET_READ_FAILED" if rows else code
        return _write_result(
            config,
            rows,
            blocker_code=code,
            acknowledged=subscription_acknowledged,
        )

    if not rows:
        return _write_result(config, rows, blocker_code="NO_MESSAGES_RECEIVED", acknowledged=False)
    return _write_result(config, rows, blocker_code=None, acknowledged=subscription_acknowledged)


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
                "channels": ["orderbook_delta"],
                "market_tickers": list(market_tickers),
            },
        },
        sort_keys=True,
    )


def _loads(raw: object) -> dict[str, object]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = json.loads(str(raw))
    return payload if isinstance(payload, dict) else {"message": payload}


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


def _write_result(
    config: KalshiWsRecorderConfig,
    rows: list[dict[str, object]],
    *,
    blocker_code: str | None,
    acknowledged: bool,
) -> KalshiWsRecorderResult:
    if not config.raw_events_path.exists():
        write_jsonl_records(config.raw_events_path, rows)
    sha = _sha256(config.raw_events_path) if rows else None
    counts = [
        _message_type(row["payload"])
        for row in rows
        if isinstance(row.get("payload"), Mapping)
    ]
    last_event = str(rows[-1]["received_at"]) if rows else None
    return KalshiWsRecorderResult(
        status="blocked" if blocker_code else "ok",
        blocker_code=blocker_code,
        connection_established=bool(rows) or blocker_code == "NO_MESSAGES_RECEIVED",
        subscription_acknowledged=acknowledged,
        event_count=len(rows),
        snapshot_count=sum("orderbook_snapshot" in item for item in counts),
        delta_count=sum("orderbook_delta" in item for item in counts),
        trade_count=sum("trade" in item for item in counts),
        status_update_count=sum("status" in item for item in counts),
        heartbeat_count=sum("heartbeat" in item for item in counts),
        error_count=sum("error" in item for item in counts) + (1 if blocker_code else 0),
        disconnect_count=0,
        reconnect_count=0,
        gap_count=0,
        last_event_time=last_event,
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
    rows: list[dict[str, object]],
    *,
    acknowledged: bool,
    raw_events_path: Path,
) -> dict[str, object]:
    counts = [
        _message_type(row["payload"])
        for row in rows
        if isinstance(row.get("payload"), Mapping)
    ]
    return {
        "connection_established": True,
        "subscription_acknowledged": acknowledged,
        "event_count": len(rows),
        "snapshot_count": sum("orderbook_snapshot" in item for item in counts),
        "delta_count": sum("orderbook_delta" in item for item in counts),
        "trade_count": sum("trade" in item for item in counts),
        "status_update_count": sum("status" in item for item in counts),
        "heartbeat_count": sum("heartbeat" in item for item in counts),
        "error_count": sum("error" in item for item in counts),
        "last_event_time": str(rows[-1]["received_at"]) if rows else None,
        "source_type": "WEBSOCKET_DELTA"
        if any("orderbook_delta" in item for item in counts)
        else "WEBSOCKET_SNAPSHOT",
        "raw_event_path": str(raw_events_path),
        "raw_event_sha256": _sha256(raw_events_path) if rows else None,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
