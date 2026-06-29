"""Create paper-only complement order proposals from offline records."""

from __future__ import annotations

import argparse
from pathlib import Path

from edmn_trader.arb.paper_engine import (
    PaperOrderProposal,
    propose_paper_order,
    write_paper_order_markdown,
    write_paper_order_proposals,
)
from edmn_trader.data.jsonl import read_jsonl_records


def run(
    *,
    candidates_path: Path,
    simulations_path: Path,
    jsonl_output_path: Path,
    markdown_output_path: Path,
) -> tuple[PaperOrderProposal, ...]:
    simulations = {
        (_field(record, "venue"), _field(record, "market_id")): record
        for record in read_jsonl_records(simulations_path)
    }
    proposals = tuple(
        propose_paper_order(
            candidate,
            simulations[(_field(candidate, "venue"), _field(candidate, "market_id"))],
        )
        for candidate in read_jsonl_records(candidates_path)
    )
    write_paper_order_proposals(jsonl_output_path, proposals)
    write_paper_order_markdown(markdown_output_path, proposals)
    return proposals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path, help="Scanner candidate JSONL.")
    parser.add_argument("--simulations", required=True, type=Path, help="Fill simulation JSONL.")
    parser.add_argument("--jsonl-output", required=True, type=Path, help="Proposal JSONL output.")
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Proposal Markdown summary output.",
    )
    args = parser.parse_args()

    proposals = run(
        candidates_path=args.candidates,
        simulations_path=args.simulations,
        jsonl_output_path=args.jsonl_output,
        markdown_output_path=args.markdown_output,
    )
    print(f"wrote {len(proposals)} paper complement proposal(s)")


def _field(record: dict[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return value


if __name__ == "__main__":
    main()
