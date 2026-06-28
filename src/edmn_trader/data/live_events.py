"""Schema and mocked recorder harness for live market-data events."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from edmn_trader.data.jsonl import read_jsonl_records, write_jsonl_records
from edmn_trader.data.payload_safety import validate_no_secret_payload

LIVE_EVENT_SCHEMA_VERSION = 1
LiveEventSourceType = Literal[
    "mock_websocket",
    "kalshi_demo_rest",
    "polymarket_us_market_channel",
]


@dataclass(frozen=True, slots=True)
class LiveMarketDataEvent:
    """One read-only market-data event record from a mocked live stream."""

    venue: str
    channel: str
    market_id: str
    event_type: str
    sequence: int
    observed_at: datetime
    received_at: datetime
    payload: Mapping[str, Any]
    source_type: LiveEventSourceType = "mock_websocket"
    tags: tuple[str, ...] = field(default_factory=tuple)
    schema_version: int = LIVE_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_EVENT_SCHEMA_VERSION:
            msg = f"unsupported live event schema_version: {self.schema_version}"
            raise ValueError(msg)
        for field_name in ("venue", "channel", "market_id", "event_type"):
            if not getattr(self, field_name):
                msg = f"{field_name} is required"
                raise ValueError(msg)
        if self.sequence <= 0:
            msg = "sequence must be positive"
            raise ValueError(msg)
        _require_aware_datetime(self.observed_at, field_name="observed_at")
        _require_aware_datetime(self.received_at, field_name="received_at")
        if self.source_type not in {
            "mock_websocket",
            "kalshi_demo_rest",
            "polymarket_us_market_channel",
        }:
            msg = (
                "source_type must be mock_websocket, kalshi_demo_rest, "
                "or polymarket_us_market_channel"
            )
            raise ValueError(msg)
        validate_no_secret_payload(self.payload)
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "tags", tuple(self.tags))

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> LiveMarketDataEvent:
        return cls(
            schema_version=_expect_int(record, "schema_version"),
            venue=_expect_str(record, "venue"),
            channel=_expect_str(record, "channel"),
            market_id=_expect_str(record, "market_id"),
            event_type=_expect_str(record, "event_type"),
            sequence=_expect_int(record, "sequence"),
            observed_at=_parse_datetime(_expect_str(record, "observed_at"), "observed_at"),
            received_at=_parse_datetime(_expect_str(record, "received_at"), "received_at"),
            payload=_expect_mapping(record, "payload"),
            source_type=_expect_str(record, "source_type"),  # type: ignore[arg-type]
            tags=tuple(_optional_str_list(record, "tags")),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "venue": self.venue,
            "channel": self.channel,
            "market_id": self.market_id,
            "event_type": self.event_type,
            "sequence": self.sequence,
            "observed_at": self.observed_at.isoformat(),
            "received_at": self.received_at.isoformat(),
            "source_type": self.source_type,
            "payload": dict(self.payload),
            "tags": list(self.tags),
        }


class MockWebSocketEventSource:
    """Finite local event source with WebSocket-like iteration semantics."""

    def __init__(self, events: Iterable[LiveMarketDataEvent]) -> None:
        self._events = tuple(events)

    def __iter__(self) -> Iterator[LiveMarketDataEvent]:
        return iter(self._events)


def read_live_events(path: Path) -> list[LiveMarketDataEvent]:
    return [LiveMarketDataEvent.from_record(record) for record in read_jsonl_records(path)]


def write_live_events(path: Path, events: Iterable[LiveMarketDataEvent]) -> None:
    write_jsonl_records(path, (event.to_record() for event in events))


def record_mock_websocket_events(source: MockWebSocketEventSource, output_path: Path) -> int:
    events = list(source)
    write_live_events(output_path, events)
    return len(events)


def _require_aware_datetime(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)


def _expect_mapping(record: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = record.get(field_name)
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be an object"
        raise ValueError(msg)
    return value


def _expect_str(record: Mapping[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ValueError(msg)
    return value


def _expect_int(record: Mapping[str, Any], field_name: str) -> int:
    value = record.get(field_name)
    if not isinstance(value, int):
        msg = f"{field_name} must be an integer"
        raise ValueError(msg)
    return value


def _optional_str_list(record: Mapping[str, Any], field_name: str) -> list[str]:
    value = record.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{field_name} must be a string list when present"
        raise ValueError(msg)
    return value


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"{field_name} must be an ISO datetime"
        raise ValueError(msg) from exc
    _require_aware_datetime(parsed, field_name=field_name)
    return parsed
