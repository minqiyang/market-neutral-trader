from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edmn_trader.adapters.kalshi import (
    KalshiDemoConnectorConfig,
    KalshiDemoConnectorError,
    KalshiDemoReconciliationError,
    append_kalshi_demo_reconciliation_jsonl,
    preview_or_submit_kalshi_demo,
    reconcile_kalshi_demo_events,
    require_demo_reconciliation_submit_eligible,
)
from edmn_trader.data.jsonl import read_jsonl_records, write_jsonl_records
from edmn_trader.scripts.kalshi_demo_reconciliation import run

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
PROPOSAL_ID = "p" * 64
CANDIDATE_HASH = "c" * 64
APPROVAL_ID = "a" * 64


def test_reconciles_accepted_rejected_cancel_error_timeout_and_backfill() -> None:
    audit = _audit_record(
        "accepted-yes",
        "rejected-no",
        "cancel-yes",
        "error-no",
        "timeout-yes",
        "backfill-no",
    )
    events = [
        _event("evt-accepted", "accepted", "accepted-yes", side="yes"),
        _event("evt-rejected", "rejected", "rejected-no", side="no"),
        _event("evt-cancel-accepted", "accepted", "cancel-yes", side="yes"),
        _event("evt-cancel", "cancel", "cancel-yes", side="yes"),
        _event("evt-error", "error", "error-no", side="no"),
        _event("evt-timeout", "timeout", "timeout-yes", side="yes"),
        _event(
            "evt-backfill",
            "backfill",
            "backfill-no",
            side="no",
            resolved_event_type="rejected",
        ),
    ]

    state = reconcile_kalshi_demo_events(audit, events)

    assert state.submit_eligible is True
    assert state.mismatch_count == 0
    assert state.accepted_count == 2
    assert state.rejected_count == 2
    assert state.cancel_count == 1
    assert state.error_count == 1
    assert state.timeout_count == 1
    assert state.backfill_count == 1
    assert state.audit_record_hash
    assert state.to_record()["executable_order_intent"] is False


def test_duplicate_fills_are_idempotent_and_decimal_precise() -> None:
    audit = _audit_record("fill-yes")
    partial = _event(
        "evt-partial",
        "partial_fill",
        "fill-yes",
        side="yes",
        quantity="0.4",
        price="0.47",
    )
    full = _event(
        "evt-full",
        "full_fill",
        "fill-yes",
        side="yes",
        quantity="0.6",
        price="0.48",
    )

    state = reconcile_kalshi_demo_events(
        audit,
        [_event("evt-accepted", "accepted", "fill-yes", side="yes"), partial, partial, full],
    )

    assert state.duplicate_event_count == 1
    assert state.partial_fill_count == 1
    assert state.full_fill_count == 1
    assert state.mismatch_count == 0
    [order] = state.orders
    assert order.filled_quantity.as_tuple().exponent == -1
    assert str(order.filled_quantity) == "1.0"
    assert str(order.average_fill_price) == "0.476"
    assert order.fully_filled is True


def test_missing_and_conflicting_events_create_mismatches() -> None:
    audit = _audit_record("known-yes", "missing-no")
    first = _event("evt-dup", "accepted", "known-yes", side="yes")
    conflict = {**first, "event_type": "rejected"}

    state = reconcile_kalshi_demo_events(audit, [first, conflict])

    reasons = {mismatch.reason for mismatch in state.mismatches}
    assert "conflicting_duplicate_event" in reasons
    assert "missing_demo_event" in reasons
    assert state.submit_eligible is False


def test_mismatch_state_blocks_future_demo_submit_preview(tmp_path: Path) -> None:
    state = reconcile_kalshi_demo_events(_audit_record("known-yes", "missing-no"), [])

    with pytest.raises(KalshiDemoReconciliationError, match="blocks"):
        require_demo_reconciliation_submit_eligible(state.to_record())
    with pytest.raises(KalshiDemoConnectorError, match="blocks"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(),
            config=KalshiDemoConnectorConfig(),
            audit_log_path=tmp_path / "audit.jsonl",
            demo_reconciliation_state_record=state.to_record(),
            now=NOW,
        )


def test_reconciliation_output_is_append_only_jsonl(tmp_path: Path) -> None:
    state = reconcile_kalshi_demo_events(
        _audit_record("known-yes"),
        [_event("evt-accepted", "accepted", "known-yes", side="yes")],
    )
    output = tmp_path / "reconciliation.jsonl"

    append_kalshi_demo_reconciliation_jsonl(output, state)
    append_kalshi_demo_reconciliation_jsonl(output, state)

    records = list(read_jsonl_records(output))
    assert len(records) == 2
    assert records[0] == records[1]
    assert records[0]["record_type"] == "kalshi_demo_reconciliation_state"
    assert records[0]["submit_eligible"] is True


def test_reconciliation_cli_reads_local_jsonl_only(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    events = tmp_path / "events.jsonl"
    output = tmp_path / "reconciliation.jsonl"
    write_jsonl_records(audit, [_audit_record("known-yes")])
    write_jsonl_records(events, [_event("evt-accepted", "accepted", "known-yes", side="yes")])

    state = run(audit_jsonl_path=audit, events_jsonl_path=events, output_path=output)

    assert state.submit_eligible is True
    [record] = list(read_jsonl_records(output))
    assert record["accepted_count"] == 1
    assert record["audit_record_hash"] == state.audit_record_hash


def _audit_record(*client_order_ids: str) -> dict[str, object]:
    return {
        "record_type": "kalshi_demo_submission_preview",
        "research_use": "demo_paper_research_infrastructure_only",
        "executable_order_intent": False,
        "manual_review_required": True,
        "proposal_id": PROPOSAL_ID,
        "candidate_hash": CANDIDATE_HASH,
        "approval_id": APPROVAL_ID,
        "status": "submitted",
        "dry_run": False,
        "request_previews": [
            {
                "method": "POST",
                "path": "/portfolio/orders",
                "body": {
                    "client_order_id": client_order_id,
                    "ticker": "DEMO-MARKET",
                    "action": "buy",
                    "type": "limit",
                    "side": "yes" if client_order_id.endswith("yes") else "no",
                    "count": 1,
                    "time_in_force": "fok",
                    "research_label": "demo_paper_research_infrastructure_not_trading_advice",
                },
                "credential_headers": "[REDACTED]",
                "executable_order_intent": False,
            }
            for client_order_id in client_order_ids
        ],
        "response_records": [{"status_code": 201, "body": {"status": "accepted"}}],
        "error_reason": None,
    }


def _event(
    event_id: str,
    event_type: str,
    client_order_id: str,
    *,
    side: str,
    quantity: str | None = None,
    price: str | None = None,
    resolved_event_type: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "record_type": "kalshi_demo_event",
        "research_use": "demo_paper_research_reconciliation_only",
        "executable_order_intent": False,
        "event_id": event_id,
        "event_type": event_type,
        "proposal_id": PROPOSAL_ID,
        "candidate_hash": CANDIDATE_HASH,
        "approval_id": APPROVAL_ID,
        "client_order_id": client_order_id,
        "side": side,
        "occurred_at": NOW.isoformat(),
    }
    if quantity is not None:
        record["quantity"] = quantity
    if price is not None:
        record["price"] = price
    if resolved_event_type is not None:
        record["resolved_event_type"] = resolved_event_type
    return record


def _connector_kwargs() -> dict[str, object]:
    return {
        "proposal_record": {
            "record_type": "paper_complement_order_proposal",
            "research_use": "paper_research_record_only",
            "executable_order_intent": False,
            "proposal_id": PROPOSAL_ID,
            "venue": "kalshi_demo",
            "market_id": "DEMO-MARKET",
            "candidate_hash": CANDIDATE_HASH,
            "simulation_hash": "s" * 64,
            "legs": [
                {"side": "yes", "limit_price": "0.47", "quantity": "1"},
                {"side": "no", "limit_price": "0.48", "quantity": "1"},
            ],
            "risk_preview": {
                "allowed_for_paper": False,
                "reasons": ["manual_approval_required"],
            },
        },
        "risk_decision_record": {
            "record_type": "complement_risk_decision_v2",
            "research_use": "paper_risk_research_record_only",
            "executable_order_intent": False,
            "proposal_id": PROPOSAL_ID,
            "candidate_hash": CANDIDATE_HASH,
            "decision": "manual_review_required",
            "approved": False,
            "manual_approval_required": True,
            "reasons": ["manual_approval_required"],
            "projected_exposure": "1",
        },
        "pending_approval_record": {
            "record_type": "manual_approval_pending",
            "research_use": "paper_manual_review_record_only",
            "executable_order_intent": False,
            "approval_id": APPROVAL_ID,
            "proposal_id": PROPOSAL_ID,
            "candidate_hash": CANDIDATE_HASH,
            "requested_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
            "reusable": False,
        },
        "approval_decision_record": {
            "record_type": "manual_approval_decision",
            "research_use": "paper_manual_review_record_only",
            "executable_order_intent": False,
            "approval_id": APPROVAL_ID,
            "proposal_id": PROPOSAL_ID,
            "candidate_hash": CANDIDATE_HASH,
            "status": "approved_for_paper_once",
            "approved": True,
            "reusable": False,
            "reasons": ["manual_approval_verified", "single_use_only"],
        },
        "paper_ledger_state_record": {
            "record_type": "paper_ledger_state",
            "research_use": "paper_research_record_only",
            "executable_order_intent": False,
            "reconciliation_mismatch_count": 0,
            "source_hashes": [
                {
                    "proposal_id": PROPOSAL_ID,
                    "candidate_hash": CANDIDATE_HASH,
                    "simulation_hash": "s" * 64,
                }
            ],
        },
    }
