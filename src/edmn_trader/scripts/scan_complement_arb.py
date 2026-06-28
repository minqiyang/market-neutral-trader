"""Scan offline complement-arbitrage fixtures and snapshots."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from edmn_trader.arb.scanner import (
    render_markdown_summary,
    scan_fixture_file,
    scan_snapshot_jsonl_file,
    write_jsonl_report,
    write_markdown_summary,
)
from edmn_trader.fees import FeeEstimateStatus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local fixture or snapshot path.")
    parser.add_argument(
        "--input-kind",
        choices=["fixture", "snapshot-jsonl"],
        default="fixture",
        help="Input format. Defaults to local fixture JSON.",
    )
    parser.add_argument(
        "--jsonl-output",
        required=True,
        type=Path,
        help="Output JSONL path for offline research records.",
    )
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Output Markdown path for the deterministic summary.",
    )
    parser.add_argument(
        "--fee-status",
        choices=[status.value for status in FeeEstimateStatus],
        default=FeeEstimateStatus.MISSING.value,
        help="Snapshot JSONL fee status. Fixture files carry their own fee fields.",
    )
    parser.add_argument(
        "--fee-per-contract",
        type=_decimal_arg,
        default=None,
        help="Explicit Decimal fee assumption for snapshot JSONL when fee-status is supplied.",
    )
    parser.add_argument(
        "--fee-source-note",
        default="scanner CLI fee assumption",
        help="Local note describing the fee assumption source.",
    )
    args = parser.parse_args()

    if args.input_kind == "fixture":
        report = scan_fixture_file(args.input)
    else:
        report = scan_snapshot_jsonl_file(
            args.input,
            fee_status=FeeEstimateStatus(args.fee_status),
            fee_per_contract=args.fee_per_contract,
            fee_source_note=args.fee_source_note,
        )

    write_jsonl_report(args.jsonl_output, report)
    write_markdown_summary(args.markdown_output, report)
    print(render_markdown_summary(report))


def _decimal_arg(value: str) -> Decimal:
    return Decimal(value)


if __name__ == "__main__":
    main()
