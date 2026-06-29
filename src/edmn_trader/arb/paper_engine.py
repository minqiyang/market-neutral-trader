"""Paper-only complement order proposals from candidate and simulation records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from edmn_trader.core.models import ZERO
from edmn_trader.data.jsonl import write_jsonl_records


@dataclass(frozen=True, slots=True)
class PaperOrderLeg:
    """One non-executable paper proposal leg."""

    side: Literal["yes", "no"]
    limit_price: Decimal
    quantity: Decimal

    def to_record(self) -> dict[str, str]:
        return {
            "side": self.side,
            "limit_price": str(self.limit_price),
            "quantity": str(self.quantity),
        }


@dataclass(frozen=True, slots=True)
class PaperRiskPreview:
    """Preview reasons before later risk/manual approval stages exist."""

    allowed_for_paper: bool
    reasons: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "allowed_for_paper": self.allowed_for_paper,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class PaperOrderProposal:
    """Paper research proposal only; never a venue submission payload."""

    proposal_id: str
    venue: str
    market_id: str
    candidate_hash: str
    simulation_hash: str
    legs: tuple[PaperOrderLeg, ...]
    risk_preview: PaperRiskPreview
    record_type: str = "paper_complement_order_proposal"
    research_use: str = "paper_research_record_only"
    executable_order_intent: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "proposal_id": self.proposal_id,
            "venue": self.venue,
            "market_id": self.market_id,
            "candidate_hash": self.candidate_hash,
            "simulation_hash": self.simulation_hash,
            "legs": [leg.to_record() for leg in self.legs],
            "risk_preview": self.risk_preview.to_record(),
        }


def propose_paper_order(
    candidate_record: Mapping[str, object],
    simulation_record: Mapping[str, object],
) -> PaperOrderProposal:
    """Build a deterministic paper-only two-leg proposal from offline records."""

    _validate_record(candidate_record, "offline_complement_research_candidate")
    _validate_record(simulation_record, "offline_taker_fill_simulation")

    venue = _expect_str(candidate_record, "venue")
    market_id = _expect_str(candidate_record, "market_id")
    if venue != _expect_str(simulation_record, "venue"):
        msg = "candidate and simulation venue must match"
        raise ValueError(msg)
    if market_id != _expect_str(simulation_record, "market_id"):
        msg = "candidate and simulation market_id must match"
        raise ValueError(msg)

    candidate_hash = hash_record(candidate_record)
    simulation_hash = hash_record(simulation_record)
    preview = _risk_preview(candidate_record, simulation_record)
    completed_pair_size = _decimal(simulation_record, "completed_pair_size")
    legs: tuple[PaperOrderLeg, ...] = ()
    if completed_pair_size > ZERO:
        legs = (
            PaperOrderLeg(
                side="yes",
                limit_price=_decimal(simulation_record, "yes_fill_price"),
                quantity=completed_pair_size,
            ),
            PaperOrderLeg(
                side="no",
                limit_price=_decimal(simulation_record, "no_fill_price"),
                quantity=completed_pair_size,
            ),
        )

    return PaperOrderProposal(
        proposal_id=hash_record(
            {
                "candidate_hash": candidate_hash,
                "simulation_hash": simulation_hash,
                "venue": venue,
                "market_id": market_id,
            }
        ),
        venue=venue,
        market_id=market_id,
        candidate_hash=candidate_hash,
        simulation_hash=simulation_hash,
        legs=legs,
        risk_preview=preview,
    )


def write_paper_order_proposals(
    path: Path,
    proposals: Iterable[PaperOrderProposal],
) -> None:
    write_jsonl_records(path, (proposal.to_record() for proposal in proposals))


def write_paper_order_markdown(path: Path, proposals: Iterable[PaperOrderProposal]) -> None:
    records = tuple(proposals)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown_summary(records), encoding="utf-8")


def hash_record(record: Mapping[str, object]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _risk_preview(
    candidate_record: Mapping[str, object],
    simulation_record: Mapping[str, object],
) -> PaperRiskPreview:
    reasons = ["manual_approval_required"]
    if _expect_str(candidate_record, "decision") != "paper_candidate":
        reasons.append("candidate_not_paper_candidate")
    if _decimal(simulation_record, "completed_pair_size") <= ZERO:
        reasons.append("simulation_not_complete")
    if _decimal(simulation_record, "simulated_net_edge_per_pair") <= ZERO:
        reasons.append("non_positive_simulated_edge")
    if _decimal(simulation_record, "failed_leg_quantity") > ZERO:
        reasons.append("partial_fill_requires_review")
    return PaperRiskPreview(
        allowed_for_paper=False,
        reasons=tuple(reasons),
    )


def _markdown_summary(proposals: tuple[PaperOrderProposal, ...]) -> str:
    allowed = sum(proposal.risk_preview.allowed_for_paper for proposal in proposals)
    blocked = len(proposals) - allowed
    return "\n".join(
        [
            "# Paper Complement Order Proposal Summary",
            "",
            "Records are paper research proposals only, not executable order intents.",
            "",
            f"- proposals: {len(proposals)}",
            f"- allowed_for_paper: {allowed}",
            f"- blocked_by_preview: {blocked}",
            "",
        ]
    )


def _validate_record(record: Mapping[str, object], record_type: str) -> None:
    if record.get("record_type") != record_type:
        msg = f"record_type must be {record_type}"
        raise ValueError(msg)
    if record.get("executable_order_intent") is not False:
        msg = "source record must not be executable"
        raise ValueError(msg)


def _expect_str(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return value


def _decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string"
        raise ValueError(msg)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ValueError(msg) from exc
