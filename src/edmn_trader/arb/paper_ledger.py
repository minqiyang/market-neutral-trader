"""Event-sourced paper ledger replay for complement research records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from edmn_trader.core.models import ONE, ZERO
from edmn_trader.data.jsonl import write_jsonl_records


@dataclass(frozen=True, slots=True)
class PaperLedgerSourceHash:
    proposal_id: str
    candidate_hash: str
    simulation_hash: str

    def to_record(self) -> dict[str, str]:
        return {
            "proposal_id": self.proposal_id,
            "candidate_hash": self.candidate_hash,
            "simulation_hash": self.simulation_hash,
        }


@dataclass(frozen=True, slots=True)
class PaperLedgerPosition:
    proposal_id: str
    side: Literal["yes", "no"]
    quantity: Decimal
    average_price: Decimal
    fees_paid: Decimal

    def to_record(self) -> dict[str, str]:
        return {
            "proposal_id": self.proposal_id,
            "side": self.side,
            "quantity": str(self.quantity),
            "average_price": str(self.average_price),
            "fees_paid": str(self.fees_paid),
        }


@dataclass(frozen=True, slots=True)
class PaperLedgerMismatch:
    proposal_id: str
    reason: str

    def to_record(self) -> dict[str, str]:
        return {
            "proposal_id": self.proposal_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PaperLedgerState:
    paper_order_count: int
    paper_fill_count: int
    settlement_count: int
    total_fees: Decimal
    realized_gross_pnl: Decimal
    realized_net_pnl: Decimal
    positions: tuple[PaperLedgerPosition, ...]
    source_hashes: tuple[PaperLedgerSourceHash, ...]
    reconciliation_mismatches: tuple[PaperLedgerMismatch, ...]
    record_type: str = "paper_ledger_state"
    research_use: str = "paper_research_record_only"
    executable_order_intent: bool = False

    @property
    def reconciliation_mismatch_count(self) -> int:
        return len(self.reconciliation_mismatches)

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "paper_order_count": self.paper_order_count,
            "paper_fill_count": self.paper_fill_count,
            "settlement_count": self.settlement_count,
            "total_fees": str(self.total_fees),
            "realized_gross_pnl": str(self.realized_gross_pnl),
            "realized_net_pnl": str(self.realized_net_pnl),
            "reconciliation_mismatch_count": self.reconciliation_mismatch_count,
            "source_hashes": [source.to_record() for source in self.source_hashes],
            "positions": [position.to_record() for position in self.positions],
            "reconciliation_mismatches": [
                mismatch.to_record() for mismatch in self.reconciliation_mismatches
            ],
        }


@dataclass(slots=True)
class _MutablePosition:
    proposal_id: str
    side: Literal["yes", "no"]
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    fees_paid: Decimal = ZERO

    @property
    def average_price(self) -> Decimal:
        if self.quantity <= ZERO:
            return ZERO
        return self.cost_basis / self.quantity

    def to_position(self) -> PaperLedgerPosition:
        return PaperLedgerPosition(
            proposal_id=self.proposal_id,
            side=self.side,
            quantity=self.quantity,
            average_price=self.average_price,
            fees_paid=self.fees_paid,
        )


def replay_paper_ledger(records: Iterable[Mapping[str, object]]) -> PaperLedgerState:
    """Replay paper order, fill, and settlement records from zero."""

    proposals: dict[str, PaperLedgerSourceHash] = {}
    positions: dict[tuple[str, str], _MutablePosition] = {}
    mismatches: list[PaperLedgerMismatch] = []
    paper_order_count = 0
    paper_fill_count = 0
    settlement_count = 0
    total_fees = ZERO
    realized_gross_pnl = ZERO

    for record in records:
        record_type = _expect_str(record, "record_type")
        _validate_paper_record(record)
        if record_type == "paper_complement_order_proposal":
            source = _source_hash(record)
            proposals[source.proposal_id] = source
            paper_order_count += 1
        elif record_type == "paper_fill":
            paper_fill_count += 1
            fee = _apply_fill(
                record=record,
                proposals=proposals,
                positions=positions,
                mismatches=mismatches,
            )
            total_fees += fee
        elif record_type == "paper_settlement":
            settlement_count += 1
            realized_gross_pnl += _apply_settlement(
                record=record,
                proposals=proposals,
                positions=positions,
                mismatches=mismatches,
            )
        else:
            msg = f"unsupported paper ledger record_type: {record_type}"
            raise ValueError(msg)

    return PaperLedgerState(
        paper_order_count=paper_order_count,
        paper_fill_count=paper_fill_count,
        settlement_count=settlement_count,
        total_fees=total_fees,
        realized_gross_pnl=realized_gross_pnl,
        realized_net_pnl=realized_gross_pnl - total_fees,
        positions=tuple(position.to_position() for position in positions.values()),
        source_hashes=tuple(proposals.values()),
        reconciliation_mismatches=tuple(mismatches),
    )


def write_paper_ledger_jsonl(path: Path, state: PaperLedgerState) -> None:
    write_jsonl_records(path, [state.to_record()])


def write_paper_ledger_markdown(path: Path, state: PaperLedgerState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown_summary(state), encoding="utf-8")


def _apply_fill(
    *,
    record: Mapping[str, object],
    proposals: Mapping[str, PaperLedgerSourceHash],
    positions: dict[tuple[str, str], _MutablePosition],
    mismatches: list[PaperLedgerMismatch],
) -> Decimal:
    proposal_id = _expect_str(record, "proposal_id")
    source = proposals.get(proposal_id)
    if source is None:
        mismatches.append(PaperLedgerMismatch(proposal_id, "unknown_proposal"))
        return ZERO
    if _expect_str(record, "candidate_hash") != source.candidate_hash:
        mismatches.append(PaperLedgerMismatch(proposal_id, "candidate_hash_mismatch"))
        return ZERO
    if _expect_str(record, "simulation_hash") != source.simulation_hash:
        mismatches.append(PaperLedgerMismatch(proposal_id, "simulation_hash_mismatch"))
        return ZERO

    side = _side(record)
    price = _decimal(record, "price")
    quantity = _non_negative_decimal(record, "quantity")
    fee = _non_negative_decimal(record, "fee")
    position = positions.setdefault(
        (proposal_id, side),
        _MutablePosition(proposal_id=proposal_id, side=side),
    )
    position.quantity += quantity
    position.cost_basis += price * quantity
    position.fees_paid += fee
    return fee


def _apply_settlement(
    *,
    record: Mapping[str, object],
    proposals: Mapping[str, PaperLedgerSourceHash],
    positions: dict[tuple[str, str], _MutablePosition],
    mismatches: list[PaperLedgerMismatch],
) -> Decimal:
    proposal_id = _expect_str(record, "proposal_id")
    if proposal_id not in proposals:
        mismatches.append(PaperLedgerMismatch(proposal_id, "unknown_proposal"))
        return ZERO

    side = _side(record)
    quantity = _non_negative_decimal(record, "quantity")
    payout = _probability_decimal(record, "payout_per_contract")
    position = positions.get((proposal_id, side))
    if position is None or position.quantity < quantity:
        mismatches.append(PaperLedgerMismatch(proposal_id, "settlement_exceeds_position"))
        return ZERO

    average_price = position.average_price
    position.quantity -= quantity
    position.cost_basis -= average_price * quantity
    if position.quantity == ZERO:
        position.cost_basis = ZERO
    return (payout - average_price) * quantity


def _source_hash(record: Mapping[str, object]) -> PaperLedgerSourceHash:
    return PaperLedgerSourceHash(
        proposal_id=_expect_str(record, "proposal_id"),
        candidate_hash=_expect_str(record, "candidate_hash"),
        simulation_hash=_expect_str(record, "simulation_hash"),
    )


def _markdown_summary(state: PaperLedgerState) -> str:
    return "\n".join(
        [
            "# Paper Ledger Replay Summary",
            "",
            "Records are paper ledger research records only, not executable order intents.",
            "",
            f"- paper_order_count: {state.paper_order_count}",
            f"- paper_fill_count: {state.paper_fill_count}",
            f"- settlement_count: {state.settlement_count}",
            f"- total_fees: {state.total_fees}",
            f"- realized_gross_pnl: {state.realized_gross_pnl}",
            f"- realized_net_pnl: {state.realized_net_pnl}",
            f"- open_position_count: {len(state.positions)}",
            f"- reconciliation_mismatch_count: {state.reconciliation_mismatch_count}",
            "",
        ]
    )


def _validate_paper_record(record: Mapping[str, object]) -> None:
    if record.get("executable_order_intent") is not False:
        msg = "paper ledger records must not be executable"
        raise ValueError(msg)


def _side(record: Mapping[str, object]) -> Literal["yes", "no"]:
    side = _expect_str(record, "side")
    if side not in {"yes", "no"}:
        msg = "side must be yes or no"
        raise ValueError(msg)
    return side


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


def _non_negative_decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = _decimal(record, field_name)
    if value < ZERO:
        msg = f"{field_name} must be non-negative"
        raise ValueError(msg)
    return value


def _probability_decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = _non_negative_decimal(record, field_name)
    if value > ONE:
        msg = f"{field_name} must be between 0 and 1"
        raise ValueError(msg)
    return value
