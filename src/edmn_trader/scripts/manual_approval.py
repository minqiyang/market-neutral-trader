"""Create and verify local manual approval records."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from edmn_trader.arb.approval import (
    ManualApprovalDecision,
    create_pending_approval,
    verify_manual_approval,
    write_approval_markdown,
    write_approval_records_jsonl,
    write_pending_approval_file,
)


def run(
    *,
    input_path: Path,
    pending_output_path: Path,
    jsonl_output_path: Path,
    markdown_output_path: Path,
) -> tuple[ManualApprovalDecision, ...]:
    payload = _read_payload(input_path)
    pending = create_pending_approval(
        _dict(payload, "risk_decision"),
        requested_at=_datetime(payload, "requested_at"),
        expires_at=_datetime(payload, "expires_at"),
    )
    write_pending_approval_file(pending_output_path, pending)

    decisions: tuple[ManualApprovalDecision, ...] = ()
    approval = payload.get("approval")
    if isinstance(approval, dict):
        approval.setdefault("approval_id", pending.approval_id)
        approval.setdefault("proposal_id", pending.proposal_id)
        approval.setdefault("candidate_hash", pending.candidate_hash)
        decisions = (
            verify_manual_approval(
                pending,
                approval,
                now=_datetime(payload, "now"),
            ),
        )
    write_approval_records_jsonl(jsonl_output_path, decisions)
    write_approval_markdown(markdown_output_path, decisions)
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local approval fixture JSON.")
    parser.add_argument(
        "--pending-output",
        required=True,
        type=Path,
        help="Pending approval JSON output.",
    )
    parser.add_argument("--jsonl-output", required=True, type=Path, help="Approval JSONL output.")
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Approval Markdown summary output.",
    )
    args = parser.parse_args()

    decisions = run(
        input_path=args.input,
        pending_output_path=args.pending_output,
        jsonl_output_path=args.jsonl_output,
        markdown_output_path=args.markdown_output,
    )
    print(f"wrote {len(decisions)} manual approval decision(s)")


def _read_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = "manual approval fixture must contain a JSON object"
        raise ValueError(msg)
    return payload


def _dict(payload: dict[str, Any], field_name: str) -> dict[str, object]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        msg = f"{field_name} must be an object"
        raise ValueError(msg)
    return value


def _datetime(payload: dict[str, Any], field_name: str) -> datetime:
    value = payload.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be an ISO datetime string"
        raise ValueError(msg)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)
    return parsed


if __name__ == "__main__":
    main()
