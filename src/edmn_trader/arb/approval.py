"""Local manual approval records for paper complement research."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from edmn_trader.data.jsonl import write_jsonl_records

ApprovalStatus = Literal["approved_for_paper_once", "reject"]


@dataclass(frozen=True, slots=True)
class PendingManualApproval:
    approval_id: str
    proposal_id: str
    candidate_hash: str
    requested_at: datetime
    expires_at: datetime
    reusable: bool = False
    record_type: str = "manual_approval_pending"
    research_use: str = "paper_manual_review_record_only"
    executable_order_intent: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "approval_id": self.approval_id,
            "proposal_id": self.proposal_id,
            "candidate_hash": self.candidate_hash,
            "requested_at": self.requested_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "reusable": self.reusable,
        }


@dataclass(frozen=True, slots=True)
class ManualApprovalDecision:
    approval_id: str
    proposal_id: str
    candidate_hash: str
    status: ApprovalStatus
    approved: bool
    reusable: bool
    reasons: tuple[str, ...]
    record_type: str = "manual_approval_decision"
    research_use: str = "paper_manual_review_record_only"
    executable_order_intent: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "approval_id": self.approval_id,
            "proposal_id": self.proposal_id,
            "candidate_hash": self.candidate_hash,
            "status": self.status,
            "approved": self.approved,
            "reusable": self.reusable,
            "reasons": list(self.reasons),
        }


def create_pending_approval(
    risk_decision_record: Mapping[str, object],
    *,
    requested_at: datetime,
    expires_at: datetime,
) -> PendingManualApproval:
    """Create a deterministic pending approval record from a clear risk decision."""

    _validate_risk_decision(risk_decision_record)
    _validate_time_window(requested_at=requested_at, expires_at=expires_at)
    proposal_id = _expect_str(risk_decision_record, "proposal_id")
    candidate_hash = _expect_str(risk_decision_record, "candidate_hash")
    return PendingManualApproval(
        approval_id=_approval_id(
            proposal_id=proposal_id,
            candidate_hash=candidate_hash,
            requested_at=requested_at,
            expires_at=expires_at,
        ),
        proposal_id=proposal_id,
        candidate_hash=candidate_hash,
        requested_at=requested_at,
        expires_at=expires_at,
    )


def verify_manual_approval(
    pending: PendingManualApproval,
    approval_record: Mapping[str, object],
    *,
    now: datetime,
) -> ManualApprovalDecision:
    """Verify one local approval record without making it reusable."""

    if now.tzinfo is None:
        msg = "now must be timezone-aware"
        raise ValueError(msg)

    reasons: list[str] = []
    if _expect_str(approval_record, "approval_id") != pending.approval_id:
        reasons.append("approval_id_mismatch")
    if _expect_str(approval_record, "proposal_id") != pending.proposal_id:
        reasons.append("proposal_id_mismatch")
    if _expect_str(approval_record, "candidate_hash") != pending.candidate_hash:
        reasons.append("candidate_hash_mismatch")
    if approval_record.get("approved") is not True:
        reasons.append("approval_not_granted")
    if approval_record.get("used") is True:
        reasons.append("approval_already_used")
    if now > pending.expires_at:
        reasons.append("approval_expired")

    if reasons:
        return ManualApprovalDecision(
            approval_id=pending.approval_id,
            proposal_id=pending.proposal_id,
            candidate_hash=pending.candidate_hash,
            status="reject",
            approved=False,
            reusable=False,
            reasons=tuple(reasons),
        )
    return ManualApprovalDecision(
        approval_id=pending.approval_id,
        proposal_id=pending.proposal_id,
        candidate_hash=pending.candidate_hash,
        status="approved_for_paper_once",
        approved=True,
        reusable=False,
        reasons=("manual_approval_verified", "single_use_only"),
    )


def write_pending_approval_file(path: Path, pending: PendingManualApproval) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_object(pending.to_record()), encoding="utf-8")


def write_approval_records_jsonl(
    path: Path,
    decisions: Iterable[ManualApprovalDecision],
) -> None:
    write_jsonl_records(path, (decision.to_record() for decision in decisions))


def write_approval_markdown(
    path: Path,
    decisions: Iterable[ManualApprovalDecision],
) -> None:
    records = tuple(decisions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown_summary(records), encoding="utf-8")


def _validate_risk_decision(record: Mapping[str, object]) -> None:
    if record.get("record_type") != "complement_risk_decision_v2":
        msg = "risk decision record_type must be complement_risk_decision_v2"
        raise ValueError(msg)
    if record.get("executable_order_intent") is not False:
        msg = "risk decision must not be executable"
        raise ValueError(msg)
    if record.get("decision") != "manual_review_required":
        msg = "risk decision must require manual review"
        raise ValueError(msg)
    if record.get("approved") is not False:
        msg = "risk decision must not already be approved"
        raise ValueError(msg)
    if record.get("manual_approval_required") is not True:
        msg = "risk decision must require manual approval"
        raise ValueError(msg)


def _validate_time_window(*, requested_at: datetime, expires_at: datetime) -> None:
    if requested_at.tzinfo is None or expires_at.tzinfo is None:
        msg = "approval timestamps must be timezone-aware"
        raise ValueError(msg)
    if expires_at <= requested_at:
        msg = "expires_at must be after requested_at"
        raise ValueError(msg)


def _approval_id(
    *,
    proposal_id: str,
    candidate_hash: str,
    requested_at: datetime,
    expires_at: datetime,
) -> str:
    payload = {
        "candidate_hash": candidate_hash,
        "expires_at": expires_at.isoformat(),
        "proposal_id": proposal_id,
        "requested_at": requested_at.isoformat(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _markdown_summary(decisions: tuple[ManualApprovalDecision, ...]) -> str:
    approved_count = sum(
        decision.status == "approved_for_paper_once" for decision in decisions
    )
    reject_count = sum(decision.status == "reject" for decision in decisions)
    return "\n".join(
        [
            "# Manual Approval Summary",
            "",
            "Records are paper manual-review records only, not executable order intents.",
            "",
            f"- approval_decision_count: {len(decisions)}",
            f"- approved_for_paper_once_count: {approved_count}",
            f"- reject_count: {reject_count}",
            "",
        ]
    )


def _expect_str(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return value


def _json_object(record: Mapping[str, object]) -> str:
    return f"{json.dumps(record, sort_keys=True, separators=(',', ':'))}\n"
