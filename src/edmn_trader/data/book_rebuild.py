"""Rebuild normalized order books from recorded read-only market-data events."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from edmn_trader.adapters.kalshi.orderbook import normalize_kalshi_orderbook_fp
from edmn_trader.adapters.polymarket_us.orderbook import normalize_polymarket_us_market_book
from edmn_trader.core.models import NormalizedOrderBook
from edmn_trader.data.jsonl import write_jsonl_records
from edmn_trader.data.live_events import LiveMarketDataEvent
from edmn_trader.data.snapshots import MarketDataSnapshot, write_snapshots

DEFAULT_MAX_STALENESS = timedelta(seconds=30)


class UnsupportedLiveEventError(ValueError):
    """Raised when a recorded event cannot be rebuilt into an order book."""


@dataclass(frozen=True, slots=True)
class BookRebuildFrame:
    """One rebuilt book with deterministic state hash and consistency flags."""

    event: LiveMarketDataEvent
    snapshot: MarketDataSnapshot
    book_hash: str
    data_quality_flags: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "venue": self.event.venue,
            "channel": self.event.channel,
            "market_id": self.event.market_id,
            "event_sequence": self.event.sequence,
            "observed_at": self.event.observed_at.isoformat(),
            "received_at": self.event.received_at.isoformat(),
            "book_hash": self.book_hash,
            "data_quality_flags": list(self.data_quality_flags),
        }


@dataclass(frozen=True, slots=True)
class BookRebuildReport:
    """Summary of a recorded-event rebuild pass."""

    frames: tuple[BookRebuildFrame, ...]

    @property
    def events_read(self) -> int:
        return len(self.frames)

    @property
    def frames_rebuilt(self) -> int:
        return len(self.frames)

    @property
    def sequence_gap_count(self) -> int:
        return _flag_count(self.frames, "sequence_gap")

    @property
    def stale_count(self) -> int:
        return _flag_count(self.frames, "stale_event")

    @property
    def out_of_order_count(self) -> int:
        return _flag_count(self.frames, "out_of_order")


def rebuild_orderbooks_from_events(
    events: list[LiveMarketDataEvent],
    *,
    max_staleness: timedelta = DEFAULT_MAX_STALENESS,
) -> BookRebuildReport:
    """Rebuild full-book event payloads into snapshots and consistency frames."""

    frames: list[BookRebuildFrame] = []
    last_sequence_by_book: dict[tuple[str, str, str], int] = {}
    last_observed_by_book: dict[tuple[str, str, str], datetime] = {}

    for event in events:
        key = (event.venue, event.channel, event.market_id)
        flags = _consistency_flags(
            event=event,
            last_sequence=last_sequence_by_book.get(key),
            last_observed=last_observed_by_book.get(key),
            max_staleness=max_staleness,
        )
        snapshot = _snapshot_from_event(event, flags=flags)
        frames.append(
            BookRebuildFrame(
                event=event,
                snapshot=snapshot,
                book_hash=hash_orderbook(snapshot.normalized_orderbook),
                data_quality_flags=flags,
            )
        )
        last_sequence_by_book[key] = event.sequence
        last_observed_by_book[key] = event.observed_at

    return BookRebuildReport(frames=tuple(frames))


def write_rebuild_frames(path: Path, frames: tuple[BookRebuildFrame, ...]) -> None:
    write_jsonl_records(path, (frame.to_record() for frame in frames))


def write_rebuild_snapshots(path: Path, frames: tuple[BookRebuildFrame, ...]) -> None:
    write_snapshots(path, (frame.snapshot for frame in frames))


def write_rebuild_markdown_summary(path: Path, report: BookRebuildReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown_summary(report), encoding="utf-8")


def hash_orderbook(book: NormalizedOrderBook) -> str:
    record = {
        "instrument_id": book.instrument_id,
        "source": book.source,
        "bids": [
            {"price": str(level.price), "quantity": str(level.quantity)} for level in book.bids
        ],
        "asks": [
            {"price": str(level.price), "quantity": str(level.quantity)} for level in book.asks
        ],
    }
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _snapshot_from_event(
    event: LiveMarketDataEvent,
    *,
    flags: tuple[str, ...],
) -> MarketDataSnapshot:
    if event.source_type == "kalshi_demo_rest":
        book = normalize_kalshi_orderbook_fp(dict(event.payload))
        exchange = "kalshi_demo"
    elif event.source_type == "polymarket_us_market_channel":
        book = normalize_polymarket_us_market_book(dict(event.payload))
        exchange = "polymarket_us"
    elif event.source_type == "mock_websocket" and event.venue == "kalshi_demo":
        book = normalize_kalshi_orderbook_fp(dict(event.payload))
        exchange = "kalshi_demo"
    elif event.source_type == "mock_websocket" and event.venue == "polymarket_us":
        book = normalize_polymarket_us_market_book(dict(event.payload))
        exchange = "polymarket_us"
    else:
        msg = f"unsupported live event source_type for rebuild: {event.source_type}"
        raise UnsupportedLiveEventError(msg)

    book_flags = (*flags, *_book_flags(book))
    return MarketDataSnapshot(
        exchange=exchange,
        ticker=event.market_id,
        observed_at=event.observed_at,
        recorded_at=event.received_at,
        normalized_orderbook=book,
        source_type="rest",
        raw_payload=event.payload,
        notes="Rebuilt from recorded read-only market-data event.",
        tags=("stage42", "book_rebuild", *book_flags),
    )


def _consistency_flags(
    *,
    event: LiveMarketDataEvent,
    last_sequence: int | None,
    last_observed: datetime | None,
    max_staleness: timedelta,
) -> tuple[str, ...]:
    flags: list[str] = []
    if last_sequence is not None and event.sequence != last_sequence + 1:
        flags.append("sequence_gap")
    if last_observed is not None and event.observed_at < last_observed:
        flags.append("out_of_order")
    if event.received_at - event.observed_at > max_staleness:
        flags.append("stale_event")
    return tuple(flags)


def _book_flags(book: NormalizedOrderBook) -> tuple[str, ...]:
    if book.best_bid is None or book.best_ask is None:
        return ("one_sided_book",)
    return ()


def _flag_count(frames: tuple[BookRebuildFrame, ...], flag: str) -> int:
    return sum(1 for frame in frames if flag in frame.data_quality_flags)


def _markdown_summary(report: BookRebuildReport) -> str:
    return "\n".join(
        [
            "# Order Book Rebuild Summary",
            "",
            "Records are audit/replay research records only, not executable order intents.",
            "",
            f"- events_read: {report.events_read}",
            f"- frames_rebuilt: {report.frames_rebuilt}",
            f"- sequence_gap_count: {report.sequence_gap_count}",
            f"- stale_count: {report.stale_count}",
            f"- out_of_order_count: {report.out_of_order_count}",
            "",
        ]
    )
