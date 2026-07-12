from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from edmn_trader.adapters.kalshi.public_evidence import ConnectionEvidenceType
from edmn_trader.adapters.kalshi.ws_auth import KalshiWsAuthConfig
from edmn_trader.adapters.kalshi.ws_events import (
    KALSHI_WS_RAW_SCHEMA_VERSION,
    AdmissionStatus,
    ExclusionReason,
    SegmentBoundaryReason,
)
from edmn_trader.adapters.kalshi.ws_recorder import (
    EvidenceCallbackError,
    KalshiWsRecorderConfig,
    _loads,
    record_kalshi_demo_ws_orderbook,
    subscription_ack_channels,
)


@pytest.mark.parametrize("sid_location", ["top", "nested"])
def test_plural_channel_ack_with_one_sid_is_ambiguous_and_not_accepted(
    sid_location: str,
) -> None:
    payload = {
        "type": "subscribed",
        "id": 1,
        "msg": {"channels": ["orderbook_delta", "trade"]},
    }
    target = payload if sid_location == "top" else payload["msg"]
    target["sid"] = 7

    assert subscription_ack_channels(payload, "subscribed") == set()


def test_ws_recorder_writes_snapshot_and_delta_raw_private_events(tmp_path: Path) -> None:
    key_path = _fake_private_key_path(tmp_path)
    websocket = _FakeWebSocket(
        [
            {
                "type": "subscribed",
                "id": 1,
                "sid": 11,
                "msg": {"channel": "orderbook_delta"},
            },
            {
                "type": "subscribed",
                "id": 2,
                "sid": 22,
                "msg": {"channel": "trade"},
            },
            {
                "type": "orderbook_snapshot",
                "sid": 11,
                "seq": 901,
                "market_ticker": "DEMO-MARKET",
            },
            {
                "type": "orderbook_delta",
                "sid": 11,
                "seq": 902,
                "market_ticker": "DEMO-MARKET",
            },
        ]
    )

    result = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id="c1",
            market_tickers=("DEMO-MARKET",),
            raw_events_path=tmp_path / "raw.jsonl",
            duration_seconds=1,
            max_events=4,
        ),
        KalshiWsAuthConfig(api_key_id="fake", private_key_path=key_path),
        websocket_factory=lambda *_args, **_kwargs: websocket,
        now=lambda: datetime(2026, 7, 3, 20, 0, tzinfo=UTC),
    )

    assert result.status == "ok"
    assert result.subscription_acknowledged is True
    assert result.event_count == 4
    assert result.snapshot_count == 1
    assert result.delta_count == 1
    assert result.raw_event_sha256
    raw_text = (tmp_path / "raw.jsonl").read_text(encoding="utf-8")
    records = [json.loads(line) for line in raw_text.splitlines()]
    assert [record["schema_version"] for record in records] == [
        KALSHI_WS_RAW_SCHEMA_VERSION
    ] * 4
    assert [record["local_row_index"] for record in records] == [1, 2, 3, 4]
    assert [record["native_seq"] for record in records] == [None, None, 901, 902]
    assert records[2]["native_sid"] == 11
    assert records[2]["subscription_command_id"] == 1
    assert records[2]["admission_status"] == AdmissionStatus.ADMITTED
    assert records[3]["admission_status"] == AdmissionStatus.ADMITTED
    assert records[3]["original_payload"]["type"] == "orderbook_delta"
    assert [json.loads(item) for item in websocket.sent] == [
        {
            "id": 1,
            "cmd": "subscribe",
            "params": {
                    "channels": ["orderbook_delta"],
                    "market_tickers": ["DEMO-MARKET"],
                    "use_yes_price": False,
            },
        },
        {
            "id": 2,
            "cmd": "subscribe",
            "params": {
                    "channels": ["trade"],
                    "market_tickers": ["DEMO-MARKET"],
                    "use_yes_price": False,
            },
        },
    ]
    assert "KALSHI-ACCESS" not in raw_text


def test_ws_recorder_reconnects_after_read_failure_with_existing_rows(
    tmp_path: Path,
) -> None:
    key_path = _fake_private_key_path(tmp_path)
    websockets = [
        _FailingWebSocket(
            [
                {
                    "type": "subscribed",
                    "id": 1,
                    "sid": 11,
                    "msg": {"channel": "orderbook_delta"},
                }
            ]
        ),
        _FakeWebSocket(
            [{"type": "orderbook_delta", "sid": 11, "market_ticker": "DEMO-MARKET"}]
        ),
    ]
    connection_events = []

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
        connection_callback=connection_events.append,
    )

    assert result.status == "ok"
    assert result.subscription_acknowledged is False
    assert result.event_count == 2
    assert result.delta_count == 1
    assert result.reconnect_count == 1
    records = [
        json.loads(line)
        for line in (tmp_path / "raw.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert records[1]["connection_id"] != records[0]["connection_id"]
    assert records[1]["segment_id"] != records[0]["segment_id"]
    assert records[1]["segment_boundary_reason"] == SegmentBoundaryReason.RESUBSCRIPTION
    assert records[1]["admission_status"] == AdmissionStatus.EXCLUDED
    assert records[1]["exclusion_reason"] == ExclusionReason.PRE_ACKNOWLEDGMENT_DATA
    assert [event.event_type for event in connection_events] == [
        ConnectionEvidenceType.CONNECTION_OPEN,
        ConnectionEvidenceType.CONNECTION_ERROR,
        ConnectionEvidenceType.CONNECTION_CLOSE,
        ConnectionEvidenceType.RECONNECT,
        ConnectionEvidenceType.RESUBSCRIPTION,
        ConnectionEvidenceType.CONNECTION_CLOSE,
    ]
    assert connection_events[4].previous_connection_id == connection_events[0].connection_id


def test_stale_rejection_does_not_emit_global_subscription_rejection(
    tmp_path: Path,
) -> None:
    websocket = _FakeWebSocket(
        [
            {
                "type": "subscribed",
                "id": 1,
                "sid": 11,
                "msg": {"channel": "orderbook_delta"},
            },
            {
                "type": "subscribed",
                "id": 2,
                "sid": 22,
                "msg": {"channel": "trade"},
            },
            {
                "type": "error",
                "id": 999,
                "msg": {"channel": "trade", "message": "stale"},
            },
        ]
    )
    connection_events = []

    record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id="stale-rejection",
            market_tickers=("DEMO-MARKET",),
            raw_events_path=tmp_path / "raw.jsonl",
            duration_seconds=1,
            max_events=3,
        ),
        KalshiWsAuthConfig(
            api_key_id="fake",
            private_key_path=_fake_private_key_path(tmp_path),
        ),
        websocket_factory=lambda *_args, **_kwargs: websocket,
        now=lambda: datetime(2026, 7, 3, 20, 0, tzinfo=UTC),
        connection_callback=connection_events.append,
    )

    assert ConnectionEvidenceType.SUBSCRIPTION_REJECTED not in {
        event.event_type for event in connection_events
    }


def test_ws_recorder_does_not_promote_partial_or_unbound_subscription_ack(
    tmp_path: Path,
) -> None:
    websocket = _FakeWebSocket(
        [
            {
                "type": "subscribed",
                "id": 99,
                "msg": {"channels": ["orderbook_delta", "trade"]},
            },
            {
                "type": "subscribed",
                "id": 1,
                "msg": {"channel": "orderbook_delta"},
            },
        ]
    )

    result = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id="c1",
            market_tickers=("DEMO-MARKET",),
            raw_events_path=tmp_path / "raw.jsonl",
            duration_seconds=1,
            max_events=2,
        ),
        KalshiWsAuthConfig(
            api_key_id="fake",
            private_key_path=_fake_private_key_path(tmp_path),
        ),
        websocket_factory=lambda *_args, **_kwargs: websocket,
        now=lambda: datetime(2026, 7, 3, 20, 0, tzinfo=UTC),
    )

    assert result.subscription_acknowledged is False


def test_ws_recorder_records_nested_subscription_rejection(tmp_path: Path) -> None:
    connection_events = []
    result = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id="c1",
            market_tickers=("DEMO-MARKET",),
            raw_events_path=tmp_path / "raw.jsonl",
            duration_seconds=1,
            max_events=1,
        ),
        KalshiWsAuthConfig(
            api_key_id="fake",
            private_key_path=_fake_private_key_path(tmp_path),
        ),
        websocket_factory=lambda *_args, **_kwargs: _FakeWebSocket(
            [
                {
                    "type": "error",
                    "id": 1,
                    "msg": {
                        "channel": "orderbook_delta",
                        "code": "invalid_subscription",
                    },
                }
            ]
        ),
        now=lambda: datetime(2026, 7, 3, 20, 0, tzinfo=UTC),
        connection_callback=connection_events.append,
    )

    assert result.subscription_acknowledged is False
    assert ConnectionEvidenceType.SUBSCRIPTION_REJECTED in {
        event.event_type for event in connection_events
    }


def test_ws_recorder_does_not_reconnect_after_evidence_callback_failure(
    tmp_path: Path,
) -> None:
    factory_calls = 0

    def factory(*_args, **_kwargs):
        nonlocal factory_calls
        factory_calls += 1
        return _FakeWebSocket(
            [
                {
                    "type": "subscribed",
                    "id": 1,
                    "msg": {"channels": ["orderbook_delta", "trade"]},
                }
            ]
        )

    def fail_persistence(_event) -> None:
        raise OSError("synthetic durable write failure")

    with pytest.raises(EvidenceCallbackError, match="OSError"):
        record_kalshi_demo_ws_orderbook(
            KalshiWsRecorderConfig(
                campaign_id="c1",
                market_tickers=("DEMO-MARKET",),
                raw_events_path=tmp_path / "unused.jsonl",
                duration_seconds=5,
                max_events=1,
                max_reconnects=3,
                persist_legacy_raw_events=False,
            ),
            KalshiWsAuthConfig(
                api_key_id="fake",
                private_key_path=_fake_private_key_path(tmp_path),
            ),
            websocket_factory=factory,
            now=lambda: datetime(2026, 7, 3, 20, 0, tzinfo=UTC),
            event_callback=fail_persistence,
        )

    assert factory_calls == 1


def test_subscription_ack_event_is_not_persisted_before_completing_raw_frame(
    tmp_path: Path,
) -> None:
    persisted_events = 0
    connection_events = []

    def fail_on_second_raw(_event) -> None:
        nonlocal persisted_events
        persisted_events += 1
        if persisted_events == 2:
            raise OSError("synthetic second acknowledgment write failure")

    with pytest.raises(EvidenceCallbackError, match="OSError"):
        record_kalshi_demo_ws_orderbook(
            KalshiWsRecorderConfig(
                campaign_id="split-ack-failure",
                market_tickers=("DEMO-MARKET",),
                raw_events_path=tmp_path / "unused.jsonl",
                duration_seconds=5,
                max_events=2,
                persist_legacy_raw_events=False,
            ),
            KalshiWsAuthConfig(
                api_key_id="fake",
                private_key_path=_fake_private_key_path(tmp_path),
            ),
            websocket_factory=lambda *_args, **_kwargs: _FakeWebSocket(
                [
                    {
                        "type": "subscribed",
                        "id": 1,
                        "msg": {"channel": "orderbook_delta"},
                    },
                    {"type": "subscribed", "id": 2, "msg": {"channel": "trade"}},
                ]
            ),
            now=lambda: datetime(2026, 7, 3, 20, 0, tzinfo=UTC),
            event_callback=fail_on_second_raw,
            connection_callback=connection_events.append,
        )

    assert ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED not in {
        event.event_type for event in connection_events
    }


@pytest.mark.parametrize("raw", ["[]", "null", "1"])
def test_ws_payload_loader_rejects_non_object_json(raw: str) -> None:
    with pytest.raises(ValueError, match="JSON object"):
        _loads(raw)


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
