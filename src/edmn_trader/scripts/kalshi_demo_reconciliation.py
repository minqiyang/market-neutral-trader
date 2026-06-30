"""Replay local Kalshi Demo reconciliation events."""

from __future__ import annotations

import argparse
from pathlib import Path

from edmn_trader.adapters.kalshi import (
    KalshiDemoReconciliationState,
    append_kalshi_demo_reconciliation_jsonl,
    reconcile_kalshi_demo_events,
)
from edmn_trader.data.jsonl import read_jsonl_records


def run(
    *,
    audit_jsonl_path: Path,
    events_jsonl_path: Path,
    output_path: Path,
) -> KalshiDemoReconciliationState:
    audit_records = tuple(read_jsonl_records(audit_jsonl_path))
    if len(audit_records) != 1:
        msg = "audit JSONL must contain exactly one Stage 49 connector audit record"
        raise ValueError(msg)
    state = reconcile_kalshi_demo_events(
        audit_records[0],
        tuple(read_jsonl_records(events_jsonl_path)),
    )
    append_kalshi_demo_reconciliation_jsonl(output_path, state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-jsonl",
        required=True,
        type=Path,
        help="Local Stage 49 connector audit JSONL with exactly one record.",
    )
    parser.add_argument(
        "--events-jsonl",
        required=True,
        type=Path,
        help="Local/mock Kalshi Demo reconciliation events JSONL.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Append-only reconciliation state JSONL.",
    )
    args = parser.parse_args()

    state = run(
        audit_jsonl_path=args.audit_jsonl,
        events_jsonl_path=args.events_jsonl,
        output_path=args.output,
    )
    print(
        "wrote Kalshi Demo reconciliation state: "
        f"orders={len(state.orders)} mismatches={state.mismatch_count} "
        f"submit_eligible={state.submit_eligible}"
    )


if __name__ == "__main__":
    main()
