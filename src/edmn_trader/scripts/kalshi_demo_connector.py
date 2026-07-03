"""Build guarded Kalshi Demo request previews from local paper records."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from edmn_trader.adapters.kalshi import (
    KalshiDemoConnectorConfig,
    KalshiDemoConnectorResult,
    preview_or_submit_kalshi_demo,
    write_kalshi_demo_result_jsonl,
)


def run(
    *,
    input_path: Path,
    jsonl_output_path: Path,
    audit_log_path: Path,
    time_in_force: str = "fok",
    submit_opt_in: bool = False,
) -> KalshiDemoConnectorResult:
    payload = _read_payload(input_path)
    result = preview_or_submit_kalshi_demo(
        proposal_record=_dict(payload, "proposal"),
        risk_decision_record=_dict(payload, "risk_decision"),
        pending_approval_record=_dict(payload, "pending_approval"),
        approval_decision_record=_dict(payload, "approval_decision"),
        paper_ledger_state_record=_dict(payload, "paper_ledger_state"),
        config=KalshiDemoConnectorConfig(
            time_in_force=_time_in_force(time_in_force),
            submit_opt_in=submit_opt_in,
            max_order_quantity=Decimal("1"),
            max_total_notional=Decimal("1"),
        ),
        audit_log_path=audit_log_path,
        demo_reconciliation_state_record=_optional_dict(payload, "demo_reconciliation_state"),
        now=_datetime_or_none(payload.get("now")),
    )
    write_kalshi_demo_result_jsonl(jsonl_output_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local Stage 49 fixture JSON.")
    parser.add_argument(
        "--jsonl-output",
        required=True,
        type=Path,
        help="Deterministic preview/submission result JSONL.",
    )
    parser.add_argument(
        "--audit-log",
        required=True,
        type=Path,
        help="Append-only local audit JSONL path.",
    )
    parser.add_argument(
        "--time-in-force",
        choices=("fok", "ioc"),
        default="fok",
        help="Kalshi Demo request preview time-in-force.",
    )
    parser.add_argument(
        "--submit-opt-in",
        action="store_true",
        help=(
            "Attempt Demo submit path; input must include clean "
            "demo_reconciliation_state. Dry-run preview is the default."
        ),
    )
    args = parser.parse_args()

    result = run(
        input_path=args.input,
        jsonl_output_path=args.jsonl_output,
        audit_log_path=args.audit_log,
        time_in_force=args.time_in_force,
        submit_opt_in=args.submit_opt_in,
    )
    print(
        "wrote Kalshi Demo "
        f"{result.status} record(s) for {len(result.request_previews)} request preview(s)"
    )


def _read_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = "Stage 49 fixture must contain a JSON object"
        raise ValueError(msg)
    return payload


def _dict(payload: dict[str, Any], field_name: str) -> dict[str, object]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        msg = f"{field_name} must be an object"
        raise ValueError(msg)
    return value


def _optional_dict(payload: dict[str, Any], field_name: str) -> dict[str, object] | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, dict):
        msg = f"{field_name} must be an object"
        raise ValueError(msg)
    return value


def _datetime_or_none(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = "now must be an ISO datetime string"
        raise ValueError(msg)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        msg = "now must be timezone-aware"
        raise ValueError(msg)
    return parsed


def _time_in_force(value: str):
    if value not in {"fok", "ioc"}:
        msg = "time_in_force must be fok or ioc"
        raise ValueError(msg)
    return value


if __name__ == "__main__":
    main()
