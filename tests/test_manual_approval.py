from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from edmn_trader.arb.approval import (
    create_pending_approval,
    verify_manual_approval,
    write_approval_markdown,
    write_approval_records_jsonl,
    write_pending_approval_file,
)
from edmn_trader.data.jsonl import read_jsonl_records
from edmn_trader.scripts.manual_approval import run

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_pending_approval_preserves_hashes_and_is_not_reusable() -> None:
    pending = create_pending_approval(
        _risk_decision_record(),
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )

    assert pending.record_type == "manual_approval_pending"
    assert pending.proposal_id == "proposal-1"
    assert pending.candidate_hash == "c" * 64
    assert pending.reusable is False
    assert pending.executable_order_intent is False
    assert len(pending.approval_id) == 64


def test_manual_approval_verifies_one_time_matching_hash() -> None:
    pending = create_pending_approval(
        _risk_decision_record(),
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )

    decision = verify_manual_approval(
        pending,
        _approval_record(pending),
        now=NOW + timedelta(minutes=1),
    )

    assert decision.status == "approved_for_paper_once"
    assert decision.approved is True
    assert decision.reusable is False
    assert decision.reasons == ("manual_approval_verified", "single_use_only")
    assert decision.to_record()["executable_order_intent"] is False
    assert "order_intent" not in decision.to_record()
    assert "execution_mode" not in decision.to_record()


def test_manual_approval_rejects_expired_approval() -> None:
    pending = create_pending_approval(
        _risk_decision_record(),
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )

    decision = verify_manual_approval(
        pending,
        _approval_record(pending),
        now=NOW + timedelta(minutes=6),
    )

    assert decision.approved is False
    assert decision.status == "reject"
    assert "approval_expired" in decision.reasons


def test_manual_approval_rejects_hash_mismatch_and_reuse() -> None:
    pending = create_pending_approval(
        _risk_decision_record(),
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )

    decision = verify_manual_approval(
        pending,
        {
            **_approval_record(pending),
            "candidate_hash": "d" * 64,
            "used": True,
        },
        now=NOW,
    )

    assert decision.status == "reject"
    assert "candidate_hash_mismatch" in decision.reasons
    assert "approval_already_used" in decision.reasons


def test_rejected_risk_decision_cannot_create_pending_approval() -> None:
    with pytest.raises(ValueError, match="risk decision must require manual review"):
        create_pending_approval(
            {**_risk_decision_record(), "decision": "reject"},
            requested_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )


def test_manual_approval_outputs_are_deterministic(tmp_path) -> None:
    pending = create_pending_approval(
        _risk_decision_record(),
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    decision = verify_manual_approval(pending, _approval_record(pending), now=NOW)
    pending_path = tmp_path / "pending.json"
    jsonl_path = tmp_path / "approval.jsonl"
    markdown_path = tmp_path / "approval.md"

    write_pending_approval_file(pending_path, pending)
    first_pending = pending_path.read_text(encoding="utf-8")
    write_pending_approval_file(pending_path, pending)
    assert pending_path.read_text(encoding="utf-8") == first_pending

    write_approval_records_jsonl(jsonl_path, [decision])
    first = jsonl_path.read_text(encoding="utf-8")
    write_approval_records_jsonl(jsonl_path, [decision])
    assert jsonl_path.read_text(encoding="utf-8") == first
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["record_type"] == "manual_approval_decision"

    write_approval_markdown(markdown_path, [decision])
    summary = markdown_path.read_text(encoding="utf-8")
    assert "paper manual-review records only" in summary
    assert "approved_for_paper_once_count: 1" in summary


def test_manual_approval_cli_reads_local_fixture_only(tmp_path) -> None:
    input_path = tmp_path / "approval_fixture.json"
    pending_path = tmp_path / "pending.json"
    jsonl_path = tmp_path / "approval.jsonl"
    markdown_path = tmp_path / "approval.md"
    input_path.write_text(
        json.dumps(
            {
                "risk_decision": _risk_decision_record(),
                "requested_at": NOW.isoformat(),
                "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
                "approval": {
                    "approved": True,
                    "used": False,
                },
                "now": NOW.isoformat(),
            }
        ),
        encoding="utf-8",
    )

    decisions = run(
        input_path=input_path,
        pending_output_path=pending_path,
        jsonl_output_path=jsonl_path,
        markdown_output_path=markdown_path,
    )

    assert len(decisions) == 1
    assert json.loads(pending_path.read_text(encoding="utf-8"))["reusable"] is False
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["status"] == "approved_for_paper_once"


def _risk_decision_record() -> dict[str, object]:
    return {
        "record_type": "complement_risk_decision_v2",
        "research_use": "paper_risk_research_record_only",
        "executable_order_intent": False,
        "proposal_id": "proposal-1",
        "candidate_hash": "c" * 64,
        "decision": "manual_review_required",
        "approved": False,
        "manual_approval_required": True,
        "reasons": ["manual_approval_required"],
    }


def _approval_record(pending) -> dict[str, object]:
    return {
        "approval_id": pending.approval_id,
        "proposal_id": pending.proposal_id,
        "candidate_hash": pending.candidate_hash,
        "approved": True,
        "used": False,
    }
