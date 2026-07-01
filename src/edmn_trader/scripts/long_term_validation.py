"""Build offline rolling validation reports from local research JSONL artifacts."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from edmn_trader.arb.long_term_validation import (
    RollingValidationReport,
    build_rolling_validation_report,
    write_rolling_validation_json,
    write_rolling_validation_jsonl,
    write_rolling_validation_markdown,
)
from edmn_trader.data.jsonl import read_jsonl_records


def run(
    *,
    input_paths: Sequence[Path],
    as_of_date: str,
    input_source: str,
    jsonl_output_path: Path,
    json_output_path: Path,
    markdown_output_path: Path,
    live_readonly_data_days: int = 0,
    paper_history_days: int = 0,
    fee_slippage_assumptions_validated: bool = False,
    legal_platform_review_complete: bool = False,
) -> RollingValidationReport:
    records = []
    for input_path in input_paths:
        records.extend(read_jsonl_records(input_path))
    report = build_rolling_validation_report(
        records,
        as_of_date=as_of_date,
        input_source=input_source,
        live_readonly_data_days=live_readonly_data_days,
        paper_history_days=paper_history_days,
        fee_slippage_assumptions_validated=fee_slippage_assumptions_validated,
        legal_platform_review_complete=legal_platform_review_complete,
    )
    write_rolling_validation_jsonl(jsonl_output_path, report)
    write_rolling_validation_json(json_output_path, report)
    write_rolling_validation_markdown(markdown_output_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        action="append",
        type=Path,
        help="Local JSONL research artifact. Repeat for multiple files.",
    )
    parser.add_argument("--as-of-date", required=True, help="Report as-of date.")
    parser.add_argument("--input-source", required=True, help="Input source label.")
    parser.add_argument("--jsonl-output", required=True, type=Path, help="JSONL output.")
    parser.add_argument("--json-output", required=True, type=Path, help="JSON output.")
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Markdown output.",
    )
    parser.add_argument(
        "--live-readonly-data-days",
        type=int,
        default=0,
        help="Documented private live-readonly history days available.",
    )
    parser.add_argument(
        "--paper-history-days",
        type=int,
        default=0,
        help="Documented paper trading history days available.",
    )
    parser.add_argument(
        "--fee-slippage-assumptions-validated",
        action="store_true",
        help="Mark fee/slippage assumptions as reviewed in private artifacts.",
    )
    parser.add_argument(
        "--legal-platform-review-complete",
        action="store_true",
        help="Mark legal/platform review as completed in private artifacts.",
    )
    args = parser.parse_args()

    report = run(
        input_paths=args.input,
        as_of_date=args.as_of_date,
        input_source=args.input_source,
        jsonl_output_path=args.jsonl_output,
        json_output_path=args.json_output,
        markdown_output_path=args.markdown_output,
        live_readonly_data_days=args.live_readonly_data_days,
        paper_history_days=args.paper_history_days,
        fee_slippage_assumptions_validated=args.fee_slippage_assumptions_validated,
        legal_platform_review_complete=args.legal_platform_review_complete,
    )
    print(f"wrote rolling validation report for {report.as_of_date}")


if __name__ == "__main__":
    main()
