"""Rebuild order books from recorded read-only market-data events."""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

from edmn_trader.data.book_rebuild import (
    BookRebuildReport,
    rebuild_orderbooks_from_events,
    write_rebuild_frames,
    write_rebuild_markdown_summary,
    write_rebuild_snapshots,
)
from edmn_trader.data.live_events import read_live_events


def run(
    *,
    events_path: Path,
    snapshots_output_path: Path,
    frames_output_path: Path,
    markdown_output_path: Path,
    max_staleness_seconds: int = 30,
) -> BookRebuildReport:
    report = rebuild_orderbooks_from_events(
        read_live_events(events_path),
        max_staleness=timedelta(seconds=max_staleness_seconds),
    )
    write_rebuild_snapshots(snapshots_output_path, report.frames)
    write_rebuild_frames(frames_output_path, report.frames)
    write_rebuild_markdown_summary(markdown_output_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, type=Path, help="Recorded live-event JSONL.")
    parser.add_argument(
        "--snapshots-output",
        required=True,
        type=Path,
        help="Rebuilt normalized snapshot JSONL.",
    )
    parser.add_argument(
        "--frames-output",
        required=True,
        type=Path,
        help="Rebuild frame JSONL with deterministic book hashes.",
    )
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Markdown rebuild consistency summary.",
    )
    parser.add_argument(
        "--max-staleness-seconds",
        default=30,
        type=int,
        help="Maximum allowed received_at minus observed_at lag before stale flagging.",
    )
    args = parser.parse_args()

    report = run(
        events_path=args.events,
        snapshots_output_path=args.snapshots_output,
        frames_output_path=args.frames_output,
        markdown_output_path=args.markdown_output,
        max_staleness_seconds=args.max_staleness_seconds,
    )
    print(
        "rebuilt "
        f"{report.frames_rebuilt} frame(s); "
        f"sequence_gaps={report.sequence_gap_count}; "
        f"stale={report.stale_count}; "
        f"out_of_order={report.out_of_order_count}"
    )


if __name__ == "__main__":
    main()
