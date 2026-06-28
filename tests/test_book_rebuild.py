from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from edmn_trader.data import LiveMarketDataEvent, read_snapshots, write_live_events
from edmn_trader.data.book_rebuild import (
    UnsupportedLiveEventError,
    rebuild_orderbooks_from_events,
    write_rebuild_frames,
    write_rebuild_markdown_summary,
)
from edmn_trader.data.jsonl import read_jsonl_records

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_rebuilds_polymarket_event_into_snapshot_with_stable_hash() -> None:
    event = _polymarket_event(sequence=1)

    report = rebuild_orderbooks_from_events([event])

    assert report.events_read == 1
    assert report.frames_rebuilt == 1
    assert report.sequence_gap_count == 0
    frame = report.frames[0]
    assert frame.snapshot.exchange == "polymarket_us"
    assert frame.snapshot.ticker == "will-fed-cut-rates-in-september"
    assert frame.book_hash == rebuild_orderbooks_from_events([event]).frames[0].book_hash
    assert len(frame.book_hash) == 64
    assert frame.data_quality_flags == ()


def test_rebuilds_mock_websocket_kalshi_event() -> None:
    event = LiveMarketDataEvent(
        venue="kalshi_demo",
        channel="orderbook_snapshot",
        market_id="DEMO-EVENT-MARKET",
        event_type="orderbook_snapshot",
        sequence=1,
        observed_at=NOW,
        received_at=NOW,
        payload=_load_fixture("kalshi_orderbook_fp_basic.json"),
        source_type="mock_websocket",
    )

    report = rebuild_orderbooks_from_events([event])

    assert report.frames_rebuilt == 1
    assert report.frames[0].snapshot.exchange == "kalshi_demo"
    assert report.frames[0].snapshot.normalized_orderbook.best_bid_price is not None


def test_rebuild_report_detects_gap_stale_and_out_of_order_events() -> None:
    events = [
        _polymarket_event(sequence=1, observed_at=NOW),
        _polymarket_event(
            sequence=3,
            observed_at=NOW + timedelta(seconds=10),
            received_at=NOW + timedelta(seconds=90),
        ),
        _polymarket_event(sequence=2, observed_at=NOW + timedelta(seconds=5)),
    ]

    report = rebuild_orderbooks_from_events(
        events,
        max_staleness=timedelta(seconds=30),
    )

    assert report.events_read == 3
    assert report.frames_rebuilt == 3
    assert report.sequence_gap_count == 2
    assert report.stale_count == 1
    assert report.out_of_order_count == 1
    assert report.frames[1].data_quality_flags == ("sequence_gap", "stale_event")
    assert report.frames[2].data_quality_flags == ("sequence_gap", "out_of_order")


def test_rebuild_writes_deterministic_jsonl_and_markdown(tmp_path: Path) -> None:
    report = rebuild_orderbooks_from_events([_polymarket_event(sequence=1)])
    frames_output = tmp_path / "frames.jsonl"
    markdown_output = tmp_path / "summary.md"

    write_rebuild_frames(frames_output, report.frames)
    first = frames_output.read_text(encoding="utf-8")
    write_rebuild_frames(frames_output, report.frames)

    assert frames_output.read_text(encoding="utf-8") == first
    [record] = list(read_jsonl_records(frames_output))
    assert record["book_hash"] == report.frames[0].book_hash
    assert record["data_quality_flags"] == []

    write_rebuild_markdown_summary(markdown_output, report)
    summary = markdown_output.read_text(encoding="utf-8")
    assert "events_read: 1" in summary
    assert "frames_rebuilt: 1" in summary
    assert "sequence_gap_count: 0" in summary
    assert "audit/replay research records only" in summary


def test_rebuild_cli_writes_snapshots_frames_and_summary(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    snapshots_path = tmp_path / "snapshots.jsonl"
    frames_path = tmp_path / "frames.jsonl"
    summary_path = tmp_path / "summary.md"
    write_live_events(events_path, [_polymarket_event(sequence=1)])

    from edmn_trader.scripts.rebuild_orderbooks import run

    report = run(
        events_path=events_path,
        snapshots_output_path=snapshots_path,
        frames_output_path=frames_path,
        markdown_output_path=summary_path,
    )

    assert report.frames_rebuilt == 1
    [snapshot] = read_snapshots(snapshots_path)
    assert snapshot.exchange == "polymarket_us"
    assert list(read_jsonl_records(frames_path))[0]["book_hash"] == report.frames[0].book_hash
    assert "frames_rebuilt: 1" in summary_path.read_text(encoding="utf-8")


def test_rebuild_rejects_unsupported_live_event_safely() -> None:
    event = LiveMarketDataEvent(
        venue="unknown",
        channel="market",
        market_id="UNKNOWN",
        event_type="market_book_snapshot",
        sequence=1,
        observed_at=NOW,
        received_at=NOW,
        payload={"book": {}},
    )

    with pytest.raises(UnsupportedLiveEventError, match="unsupported live event"):
        rebuild_orderbooks_from_events([event])


def _polymarket_event(
    *,
    sequence: int,
    observed_at: datetime = NOW,
    received_at: datetime | None = None,
) -> LiveMarketDataEvent:
    return LiveMarketDataEvent(
        venue="polymarket_us",
        channel="market",
        market_id="will-fed-cut-rates-in-september",
        event_type="market_book_snapshot",
        sequence=sequence,
        observed_at=observed_at,
        received_at=received_at or observed_at,
        payload=_load_fixture("polymarket_us_market_book.json"),
        source_type="polymarket_us_market_channel",
    )


def _load_fixture(name: str) -> dict[str, Any]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{name} must contain an object"
        raise TypeError(msg)
    return payload
