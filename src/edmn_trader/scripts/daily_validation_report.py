"""Build an offline daily validation report from local records."""

from __future__ import annotations

import argparse
from pathlib import Path

from edmn_trader.arb.monitoring import (
    DailyValidationReport,
    build_daily_validation_report,
    write_daily_validation_jsonl,
    write_daily_validation_markdown,
)
from edmn_trader.data.jsonl import read_jsonl_records


def run(
    *,
    input_path: Path,
    report_date: str,
    input_source: str,
    jsonl_output_path: Path,
    markdown_output_path: Path,
) -> DailyValidationReport:
    report = build_daily_validation_report(
        read_jsonl_records(input_path),
        report_date=report_date,
        input_source=input_source,
    )
    write_daily_validation_jsonl(jsonl_output_path, report)
    write_daily_validation_markdown(markdown_output_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local monitoring JSONL.")
    parser.add_argument("--report-date", required=True, help="Report date label.")
    parser.add_argument("--input-source", required=True, help="Input source label.")
    parser.add_argument("--jsonl-output", required=True, type=Path, help="Report JSONL output.")
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Report Markdown output.",
    )
    args = parser.parse_args()

    report = run(
        input_path=args.input,
        report_date=args.report_date,
        input_source=args.input_source,
        jsonl_output_path=args.jsonl_output,
        markdown_output_path=args.markdown_output,
    )
    print(f"wrote daily validation report for {report.report_date}")


if __name__ == "__main__":
    main()
