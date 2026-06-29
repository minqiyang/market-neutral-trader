"""Paper-only complement risk decisions for Stage 46."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from edmn_trader.core.models import ZERO
from edmn_trader.data.jsonl import write_jsonl_records

RiskDecisionLabel = Literal["reject", "manual_review_required"]


@dataclass(frozen=True, slots=True)
class ComplementRiskInput:
    proposal_id: str
    candidate_hash: str
    fee_status: str
    net_edge_per_contract: Decimal
    minimum_net_edge_per_contract: Decimal
    projected_exposure: Decimal
    max_exposure: Decimal
    open_order_count: int
    max_open_orders: int
    daily_loss: Decimal
    max_daily_loss: Decimal
    data_quality_flags: tuple[str, ...] = ()
    reconciliation_mismatch_count: int = 0
    kill_switch_active: bool = False

    def __post_init__(self) -> None:
        if not self.proposal_id:
            msg = "proposal_id is required"
            raise ValueError(msg)
        if not self.candidate_hash:
            msg = "candidate_hash is required"
            raise ValueError(msg)
        if self.fee_status not in {"supplied", "missing", "unknown"}:
            msg = "fee_status must be supplied, missing, or unknown"
            raise ValueError(msg)
        for field_name in (
            "net_edge_per_contract",
            "minimum_net_edge_per_contract",
            "projected_exposure",
            "max_exposure",
            "daily_loss",
            "max_daily_loss",
        ):
            _require_non_negative_decimal(getattr(self, field_name), field_name=field_name)
        for field_name in ("open_order_count", "max_open_orders", "reconciliation_mismatch_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value < 0:
                msg = f"{field_name} must be a non-negative integer"
                raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ComplementRiskDecision:
    proposal_id: str
    candidate_hash: str
    decision: RiskDecisionLabel
    reasons: tuple[str, ...]
    projected_exposure: Decimal
    approved: bool = False
    manual_approval_required: bool = True
    record_type: str = "complement_risk_decision_v2"
    research_use: str = "paper_risk_research_record_only"
    executable_order_intent: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "proposal_id": self.proposal_id,
            "candidate_hash": self.candidate_hash,
            "decision": self.decision,
            "approved": self.approved,
            "manual_approval_required": self.manual_approval_required,
            "reasons": list(self.reasons),
            "projected_exposure": str(self.projected_exposure),
        }


def evaluate_complement_risk(risk_input: ComplementRiskInput) -> ComplementRiskDecision:
    """Evaluate Stage 46 blockers while keeping manual approval required."""

    reasons = ["manual_approval_required"]
    flags = set(risk_input.data_quality_flags)
    if "stale_book" in flags or "stale_event" in flags:
        reasons.append("stale_data")
    if "sequence_gap" in flags or "data_gap" in flags:
        reasons.append("data_gap")
    if risk_input.fee_status == "missing":
        reasons.append("missing_fee_model")
    elif risk_input.fee_status == "unknown":
        reasons.append("unknown_fee_model")
    if risk_input.net_edge_per_contract < risk_input.minimum_net_edge_per_contract:
        reasons.append("insufficient_net_edge")
    if risk_input.projected_exposure > risk_input.max_exposure:
        reasons.append("exposure_limit_breach")
    if risk_input.open_order_count > risk_input.max_open_orders:
        reasons.append("open_order_limit_breach")
    if risk_input.daily_loss > risk_input.max_daily_loss:
        reasons.append("daily_loss_limit_breach")
    if risk_input.reconciliation_mismatch_count > 0:
        reasons.append("reconciliation_mismatch")
    if risk_input.kill_switch_active:
        reasons.append("kill_switch_active")

    decision: RiskDecisionLabel = "manual_review_required"
    if len(reasons) > 1:
        decision = "reject"
    return ComplementRiskDecision(
        proposal_id=risk_input.proposal_id,
        candidate_hash=risk_input.candidate_hash,
        decision=decision,
        reasons=tuple(reasons),
        projected_exposure=risk_input.projected_exposure,
    )


def write_complement_risk_jsonl(
    path: Path,
    decisions: Iterable[ComplementRiskDecision],
) -> None:
    write_jsonl_records(path, (decision.to_record() for decision in decisions))


def write_complement_risk_markdown(
    path: Path,
    decisions: Iterable[ComplementRiskDecision],
) -> None:
    records = tuple(decisions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown_summary(records), encoding="utf-8")


def risk_input_from_record(record: dict[str, object]) -> ComplementRiskInput:
    return ComplementRiskInput(
        proposal_id=_expect_str(record, "proposal_id"),
        candidate_hash=_expect_str(record, "candidate_hash"),
        fee_status=_expect_str(record, "fee_status"),
        net_edge_per_contract=_decimal(record, "net_edge_per_contract"),
        minimum_net_edge_per_contract=_decimal(record, "minimum_net_edge_per_contract"),
        data_quality_flags=_str_tuple(record.get("data_quality_flags", [])),
        projected_exposure=_decimal(record, "projected_exposure"),
        max_exposure=_decimal(record, "max_exposure"),
        open_order_count=_int(record, "open_order_count"),
        max_open_orders=_int(record, "max_open_orders"),
        daily_loss=_decimal(record, "daily_loss"),
        max_daily_loss=_decimal(record, "max_daily_loss"),
        reconciliation_mismatch_count=_int(record, "reconciliation_mismatch_count"),
        kill_switch_active=_bool(record, "kill_switch_active"),
    )


def _markdown_summary(decisions: tuple[ComplementRiskDecision, ...]) -> str:
    reject_count = sum(decision.decision == "reject" for decision in decisions)
    manual_count = sum(
        decision.decision == "manual_review_required" for decision in decisions
    )
    return "\n".join(
        [
            "# Complement Risk V2 Summary",
            "",
            "Records are paper risk research records only, not executable order intents.",
            "",
            f"- risk_decision_count: {len(decisions)}",
            f"- reject_count: {reject_count}",
            f"- manual_review_required_count: {manual_count}",
            "",
        ]
    )


def _require_non_negative_decimal(value: Decimal, *, field_name: str) -> None:
    if not isinstance(value, Decimal):
        msg = f"{field_name} must be a Decimal"
        raise TypeError(msg)
    if value < ZERO:
        msg = f"{field_name} must be non-negative"
        raise ValueError(msg)


def _expect_str(record: dict[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return value


def _decimal(record: dict[str, object], field_name: str) -> Decimal:
    value = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string"
        raise ValueError(msg)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ValueError(msg) from exc


def _int(record: dict[str, object], field_name: str) -> int:
    value = record.get(field_name)
    if not isinstance(value, int) or value < 0:
        msg = f"{field_name} must be a non-negative integer"
        raise ValueError(msg)
    return value


def _bool(record: dict[str, object], field_name: str) -> bool:
    value = record.get(field_name)
    if not isinstance(value, bool):
        msg = f"{field_name} must be a boolean"
        raise ValueError(msg)
    return value


def _str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        msg = "data_quality_flags must be a list of strings"
        raise ValueError(msg)
    if not all(isinstance(item, str) for item in value):
        msg = "data_quality_flags must be a list of strings"
        raise ValueError(msg)
    return tuple(value)
