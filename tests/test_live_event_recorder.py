from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edmn_trader.data.live_events import (
    LiveMarketDataEvent,
    MockWebSocketEventSource,
    read_live_events,
    record_mock_websocket_events,
    write_live_events,
)
from edmn_trader.scripts.mock_live_event_recorder import run_mock_recorder


def test_live_event_jsonl_roundtrip_preserves_payload(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = _event(payload={"yes": [["0.42", "10"]], "no": [["0.56", "7"]]})

    write_live_events(path, [event])

    assert read_live_events(path) == [event]
    assert '"observed_at":"2026-06-28T12:00:00+00:00"' in path.read_text(encoding="utf-8")


def test_live_event_rejects_secret_like_payload() -> None:
    with pytest.raises(ValueError, match="credentials"):
        _event(payload={"headers": {"authorization": "do-not-store"}})


def test_mock_websocket_recorder_writes_deterministic_events(tmp_path: Path) -> None:
    path = tmp_path / "mock.jsonl"
    events = [_event(sequence=2), _event(sequence=1)]

    count = record_mock_websocket_events(MockWebSocketEventSource(events), path)

    assert count == 2
    assert [event.sequence for event in read_live_events(path)] == [2, 1]
    first = path.read_text(encoding="utf-8")
    record_mock_websocket_events(MockWebSocketEventSource(events), path)
    assert path.read_text(encoding="utf-8") == first


def test_mock_recorder_cli_reads_local_fixture_only(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    output = tmp_path / "events.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "venue": "kalshi_demo",
                        "channel": "orderbook_delta",
                        "market_id": "DEMO-MARKET",
                        "event_type": "book_delta",
                        "sequence": 1,
                        "observed_at": "2026-06-28T12:00:00+00:00",
                        "received_at": "2026-06-28T12:00:01+00:00",
                        "payload": {"yes": [["0.42", "10"]]},
                        "tags": ["mock"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    count = run_mock_recorder(fixture, output)

    assert count == 1
    [event] = read_live_events(output)
    assert event.source_type == "mock_websocket"
    assert event.tags == ("mock",)


def test_live_event_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValueError, match="observed_at must be timezone-aware"):
        _event(observed_at=datetime(2026, 6, 28, 12, 0))


def _event(
    *,
    sequence: int = 1,
    observed_at: datetime = datetime(2026, 6, 28, 12, 0, tzinfo=UTC),
    payload: dict[str, object] | None = None,
) -> LiveMarketDataEvent:
    return LiveMarketDataEvent(
        venue="kalshi_demo",
        channel="orderbook_delta",
        market_id="DEMO-MARKET",
        event_type="book_delta",
        sequence=sequence,
        observed_at=observed_at,
        received_at=datetime(2026, 6, 28, 12, 0, 1, tzinfo=UTC),
        payload=payload or {"yes": [["0.42", "10"]]},
    )
