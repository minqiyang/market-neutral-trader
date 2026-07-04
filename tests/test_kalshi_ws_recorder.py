from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from edmn_trader.adapters.kalshi.ws_auth import KalshiWsAuthConfig
from edmn_trader.adapters.kalshi.ws_recorder import (
    KalshiWsRecorderConfig,
    record_kalshi_demo_ws_orderbook,
)


def test_ws_recorder_writes_snapshot_and_delta_raw_private_events(tmp_path: Path) -> None:
    key_path = _fake_private_key_path(tmp_path)
    websocket = _FakeWebSocket(
        [
            {"type": "subscribed", "id": 1},
            {"type": "orderbook_snapshot", "market_ticker": "DEMO-MARKET"},
            {"type": "orderbook_delta", "market_ticker": "DEMO-MARKET"},
        ]
    )

    result = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id="c1",
            market_tickers=("DEMO-MARKET",),
            raw_events_path=tmp_path / "raw.jsonl",
            duration_seconds=1,
            max_events=3,
        ),
        KalshiWsAuthConfig(api_key_id="fake", private_key_path=key_path),
        websocket_factory=lambda *_args, **_kwargs: websocket,
        now=lambda: datetime(2026, 7, 3, 20, 0, tzinfo=UTC),
    )

    assert result.status == "ok"
    assert result.subscription_acknowledged is True
    assert result.event_count == 3
    assert result.snapshot_count == 1
    assert result.delta_count == 1
    assert result.raw_event_sha256
    assert "orderbook_delta" in (tmp_path / "raw.jsonl").read_text(encoding="utf-8")
    assert "KALSHI-ACCESS" not in (tmp_path / "raw.jsonl").read_text(encoding="utf-8")


def test_ws_recorder_reconnects_after_read_failure_with_existing_rows(
    tmp_path: Path,
) -> None:
    key_path = _fake_private_key_path(tmp_path)
    websockets = [
        _FailingWebSocket([{"type": "subscribed", "id": 1}]),
        _FakeWebSocket([{"type": "orderbook_delta", "market_ticker": "DEMO-MARKET"}]),
    ]

    result = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id="c1",
            market_tickers=("DEMO-MARKET",),
            raw_events_path=tmp_path / "raw.jsonl",
            duration_seconds=5,
            max_events=2,
            max_reconnects=1,
        ),
        KalshiWsAuthConfig(api_key_id="fake", private_key_path=key_path),
        websocket_factory=lambda *_args, **_kwargs: websockets.pop(0),
        now=lambda: datetime(2026, 7, 3, 20, 0, tzinfo=UTC),
    )

    assert result.status == "ok"
    assert result.subscription_acknowledged is True
    assert result.event_count == 2
    assert result.delta_count == 1
    assert result.reconnect_count == 1
    assert "orderbook_delta" in (tmp_path / "raw.jsonl").read_text(encoding="utf-8")


class _FakeWebSocket:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.messages = [json.dumps(message) for message in messages]
        self.sent: list[str] = []

    def __enter__(self) -> _FakeWebSocket:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self, *, timeout: float | None = None) -> str:
        if not self.messages:
            raise TimeoutError
        return self.messages.pop(0)


class _FailingWebSocket(_FakeWebSocket):
    def recv(self, *, timeout: float | None = None) -> str:
        if self.messages:
            return self.messages.pop(0)
        raise ConnectionError("read failed")


def _fake_private_key_path(tmp_path: Path) -> Path:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "fake.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return key_path
