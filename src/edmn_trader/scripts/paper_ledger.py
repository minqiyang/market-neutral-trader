"""Replay local paper ledger events into a paper-only ledger state."""

from __future__ import annotations

import argparse
from pathlib import Path

from edmn_trader.arb.paper_ledger import (
    PaperLedgerState,
    replay_paper_ledger,
    write_paper_ledger_jsonl,
    write_paper_ledger_markdown,
)
from edmn_trader.data.jsonl import read_jsonl_records


def run(
    *,
    events_path: Path,
    jsonl_output_path: Path,
    markdown_output_path: Path,
) -> PaperLedgerState:
    state = replay_paper_ledger(read_jsonl_records(events_path))
    write_paper_ledger_jsonl(jsonl_output_path, state)
    write_paper_ledger_markdown(markdown_output_path, state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--events",
        required=True,
        type=Path,
        help="Local paper ledger event JSONL.",
    )
    parser.add_argument(
        "--jsonl-output",
        required=True,
        type=Path,
        help="Ledger state JSONL output.",
    )
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Ledger Markdown summary output.",
    )
    args = parser.parse_args()

    state = run(
        events_path=args.events,
        jsonl_output_path=args.jsonl_output,
        markdown_output_path=args.markdown_output,
    )
    print(f"replayed {state.paper_order_count} paper order(s)")


if __name__ == "__main__":
    main()
