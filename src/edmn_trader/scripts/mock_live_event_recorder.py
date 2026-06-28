"""Write mocked WebSocket market-data events from a local fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from edmn_trader.data.live_events import (
    LIVE_EVENT_SCHEMA_VERSION,
    LiveMarketDataEvent,
    MockWebSocketEventSource,
    record_mock_websocket_events,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local mock-event fixture JSON.")
    parser.add_argument("--output", required=True, type=Path, help="Output JSONL event path.")
    args = parser.parse_args()

    count = run_mock_recorder(args.input, args.output)
    print(f"wrote {count} mocked live event(s) to {args.output}")


def run_mock_recorder(input_path: Path, output_path: Path) -> int:
    events = _load_fixture_events(input_path)
    return record_mock_websocket_events(MockWebSocketEventSource(events), output_path)


def _load_fixture_events(path: Path) -> list[LiveMarketDataEvent]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = "mock event fixture root must be an object"
        raise ValueError(msg)
    records = payload.get("events")
    if not isinstance(records, list):
        msg = "mock event fixture must contain an events list"
        raise ValueError(msg)
    return [_event_from_record(record) for record in records]


def _event_from_record(record: Any) -> LiveMarketDataEvent:
    if not isinstance(record, dict):
        msg = "mock event records must be objects"
        raise ValueError(msg)
    return LiveMarketDataEvent.from_record(
        {
            "schema_version": LIVE_EVENT_SCHEMA_VERSION,
            "source_type": "mock_websocket",
            "tags": [],
            **record,
        }
    )


if __name__ == "__main__":
    main()
