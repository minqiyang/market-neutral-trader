"""Evaluate local complement risk v2 checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from edmn_trader.arb.risk import (
    ComplementRiskDecision,
    evaluate_complement_risk,
    risk_input_from_record,
    write_complement_risk_jsonl,
    write_complement_risk_markdown,
)


def run(
    *,
    input_path: Path,
    jsonl_output_path: Path,
    markdown_output_path: Path,
) -> tuple[ComplementRiskDecision, ...]:
    checks = _read_checks(input_path)
    decisions = tuple(evaluate_complement_risk(risk_input_from_record(check)) for check in checks)
    write_complement_risk_jsonl(jsonl_output_path, decisions)
    write_complement_risk_markdown(markdown_output_path, decisions)
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local risk-check fixture JSON.")
    parser.add_argument("--jsonl-output", required=True, type=Path, help="Risk decision JSONL.")
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Risk decision Markdown summary.",
    )
    args = parser.parse_args()

    decisions = run(
        input_path=args.input,
        jsonl_output_path=args.jsonl_output,
        markdown_output_path=args.markdown_output,
    )
    print(f"wrote {len(decisions)} complement risk decision(s)")


def _read_checks(path: Path) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("checks"), list):
        checks = payload["checks"]
    else:
        checks = [payload]
    if not all(isinstance(check, dict) for check in checks):
        msg = "risk fixture checks must be objects"
        raise ValueError(msg)
    return tuple(checks)


if __name__ == "__main__":
    main()
