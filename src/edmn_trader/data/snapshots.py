"""Snapshot models and JSONL persistence for offline market-data replay."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from edmn_trader.core.models import NormalizedOrderBook, OrderBookLevel
from edmn_trader.data.jsonl import (
    append_jsonl_record,
    append_jsonl_records,
    read_jsonl_records,
    write_jsonl_records,
)
from edmn_trader.data.payload_safety import validate_no_secret_payload

SNAPSHOT_SCHEMA_VERSION = 1
SourceType = Literal["fixture", "rest", "manual"]


@dataclass(frozen=True, slots=True)
class MarketDataSnapshot:
    """One recorded market-data snapshot for deterministic offline replay."""

    exchange: str
    ticker: str
    observed_at: datetime
    recorded_at: datetime
    normalized_orderbook: NormalizedOrderBook
    source_type: SourceType
    raw_payload: Mapping[str, Any] | None = None
    notes: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    schema_version: int = SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SNAPSHOT_SCHEMA_VERSION:
            msg = f"unsupported snapshot schema_version: {self.schema_version}"
            raise ValueError(msg)
        if not self.exchange:
            msg = "exchange is required"
            raise ValueError(msg)
        if not self.ticker:
            msg = "ticker is required"
            raise ValueError(msg)
        _require_aware_datetime(self.observed_at, field_name="observed_at")
        _require_aware_datetime(self.recorded_at, field_name="recorded_at")
        if self.source_type not in {"fixture", "rest", "manual"}:
            msg = "source_type must be fixture, rest, or manual"
            raise ValueError(msg)
        if self.raw_payload is not None:
            validate_no_secret_payload(self.raw_payload, path="raw_payload")
        object.__setattr__(self, "tags", tuple(self.tags))

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> MarketDataSnapshot:
        """Build a snapshot from one JSON object record."""

        return cls(
            schema_version=_expect_int(record, "schema_version"),
            exchange=_expect_str(record, "exchange"),
            ticker=_expect_str(record, "ticker"),
            observed_at=_parse_datetime(_expect_str(record, "observed_at"), "observed_at"),
            recorded_at=_parse_datetime(_expect_str(record, "recorded_at"), "recorded_at"),
            normalized_orderbook=_orderbook_from_record(
                _expect_mapping(record, "normalized_orderbook")
            ),
            source_type=_expect_str(record, "source_type"),  # type: ignore[arg-type]
            raw_payload=_optional_mapping(record, "raw_payload"),
            notes=_optional_str(record, "notes"),
            tags=tuple(_optional_str_list(record, "tags")),
        )

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot record."""

        return {
            "schema_version": self.schema_version,
            "exchange": self.exchange,
            "ticker": self.ticker,
            "observed_at": self.observed_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "source_type": self.source_type,
            "normalized_orderbook": _orderbook_to_record(self.normalized_orderbook),
            "raw_payload": dict(self.raw_payload) if self.raw_payload is not None else None,
            "notes": self.notes,
            "tags": list(self.tags),
        }


def read_snapshots(path: Path) -> list[MarketDataSnapshot]:
    """Read all market-data snapshots from a JSONL file."""

    return [MarketDataSnapshot.from_record(record) for record in read_jsonl_records(path)]


def write_snapshots(path: Path, snapshots: Iterable[MarketDataSnapshot]) -> None:
    """Write snapshots to a JSONL file, replacing any existing file."""

    write_jsonl_records(path, (snapshot.to_record() for snapshot in snapshots))


def append_snapshot(path: Path, snapshot: MarketDataSnapshot) -> None:
    """Append one snapshot to a JSONL file."""

    append_jsonl_record(path, snapshot.to_record())


def append_snapshots(path: Path, snapshots: Iterable[MarketDataSnapshot]) -> None:
    """Append snapshots to a JSONL file."""

    append_jsonl_records(path, (snapshot.to_record() for snapshot in snapshots))


def _orderbook_to_record(book: NormalizedOrderBook) -> dict[str, Any]:
    return {
        "instrument_id": book.instrument_id,
        "source": book.source,
        "bids": [_level_to_record(level) for level in book.bids],
        "asks": [_level_to_record(level) for level in book.asks],
    }


def _level_to_record(level: OrderBookLevel) -> dict[str, str]:
    return {"price": str(level.price), "quantity": str(level.quantity)}


def _orderbook_from_record(record: Mapping[str, Any]) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        instrument_id=_expect_str(record, "instrument_id"),
        source=_expect_str(record, "source"),
        bids=tuple(_level_from_record(level) for level in _expect_mapping_list(record, "bids")),
        asks=tuple(_level_from_record(level) for level in _expect_mapping_list(record, "asks")),
    )


def _level_from_record(record: Mapping[str, Any]) -> OrderBookLevel:
    return OrderBookLevel(
        price=_parse_decimal(_expect_str(record, "price"), "price"),
        quantity=_parse_decimal(_expect_str(record, "quantity"), "quantity"),
    )


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


def _optional_mapping(record: Mapping[str, Any], field_name: str) -> Mapping[str, Any] | None:
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be an object when present"
        raise ValueError(msg)
    return value


def _expect_mapping_list(record: Mapping[str, Any], field_name: str) -> list[Mapping[str, Any]]:
    value = record.get(field_name)
    if not isinstance(value, list):
        msg = f"{field_name} must be a list"
        raise ValueError(msg)
    if not all(isinstance(item, Mapping) for item in value):
        msg = f"{field_name} must contain only objects"
        raise ValueError(msg)
    return value


def _expect_str(record: Mapping[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ValueError(msg)
    return value


def _optional_str(record: Mapping[str, Any], field_name: str) -> str | None:
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{field_name} must be a string when present"
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


def _expect_int(record: Mapping[str, Any], field_name: str) -> int:
    value = record.get(field_name)
    if not isinstance(value, int):
        msg = f"{field_name} must be an integer"
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


def _parse_decimal(value: str, field_name: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ValueError(msg) from exc
