"""Pure offline candidate model for YES/NO complement parity research."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from edmn_trader.core.models import ONE, ZERO
from edmn_trader.fees.base import FeeEstimate, FeeEstimateStatus


class ComplementArbDecision(StrEnum):
    """Offline review decision for a complement-parity candidate."""

    REJECT = "reject"
    AUDIT_ONLY = "audit_only"
    PAPER_CANDIDATE = "paper_candidate"


@dataclass(frozen=True, slots=True)
class ComplementArbInput:
    """Best YES/NO bid snapshot plus explicit cost assumptions."""

    venue: str
    market_id: str
    best_yes_bid: Decimal
    best_no_bid: Decimal
    yes_bid_size: Decimal
    no_bid_size: Decimal
    estimated_fee_per_contract: Decimal | None = None
    estimated_slippage_per_contract: Decimal = ZERO
    failed_leg_reserve_per_contract: Decimal = ZERO
    minimum_net_edge_per_contract: Decimal = ZERO
    fee_estimate: FeeEstimate | None = None
    stale_book: bool = False

    def __post_init__(self) -> None:
        if not self.venue:
            msg = "venue is required"
            raise ValueError(msg)
        if not self.market_id:
            msg = "market_id is required"
            raise ValueError(msg)

        _require_decimal(self.best_yes_bid, field_name="best_yes_bid")
        _require_decimal(self.best_no_bid, field_name="best_no_bid")
        _require_decimal(self.yes_bid_size, field_name="yes_bid_size")
        _require_decimal(self.no_bid_size, field_name="no_bid_size")
        _require_decimal(
            self.estimated_slippage_per_contract,
            field_name="estimated_slippage_per_contract",
        )
        _require_decimal(
            self.failed_leg_reserve_per_contract,
            field_name="failed_leg_reserve_per_contract",
        )
        _require_decimal(
            self.minimum_net_edge_per_contract,
            field_name="minimum_net_edge_per_contract",
        )
        if self.estimated_fee_per_contract is not None:
            _require_decimal(
                self.estimated_fee_per_contract,
                field_name="estimated_fee_per_contract",
            )
        if self.fee_estimate is not None and not isinstance(self.fee_estimate, FeeEstimate):
            msg = "fee_estimate must be a FeeEstimate"
            raise TypeError(msg)
        if self.fee_estimate is not None and self.estimated_fee_per_contract is not None:
            msg = "use fee_estimate or estimated_fee_per_contract, not both"
            raise ValueError(msg)
        if self.fee_estimate is not None and self.fee_estimate.venue != self.venue:
            msg = "fee_estimate venue must match input venue"
            raise ValueError(msg)

        _validate_probability_price(self.best_yes_bid, field_name="best_yes_bid")
        _validate_probability_price(self.best_no_bid, field_name="best_no_bid")
        _validate_non_negative(self.yes_bid_size, field_name="yes_bid_size")
        _validate_non_negative(self.no_bid_size, field_name="no_bid_size")
        _validate_optional_non_negative(
            self.estimated_fee_per_contract,
            field_name="estimated_fee_per_contract",
        )
        _validate_non_negative(
            self.estimated_slippage_per_contract,
            field_name="estimated_slippage_per_contract",
        )
        _validate_non_negative(
            self.failed_leg_reserve_per_contract,
            field_name="failed_leg_reserve_per_contract",
        )
        _validate_non_negative(
            self.minimum_net_edge_per_contract,
            field_name="minimum_net_edge_per_contract",
        )


@dataclass(frozen=True, slots=True)
class ComplementArbCandidate:
    """Offline candidate summary; not an execution instruction."""

    venue: str
    market_id: str
    best_yes_bid: Decimal
    best_no_bid: Decimal
    yes_ask: Decimal
    no_ask: Decimal
    gross_edge_per_contract: Decimal
    candidate_size: Decimal
    estimated_fee_per_contract: Decimal | None
    fee_status: FeeEstimateStatus
    estimated_slippage_per_contract: Decimal
    failed_leg_reserve_per_contract: Decimal
    net_edge_per_contract: Decimal
    total_estimated_net_edge: Decimal
    decision: ComplementArbDecision
    flags: tuple[str, ...]


def compute_kalshi_complement_candidate(snapshot: ComplementArbInput) -> ComplementArbCandidate:
    """Compute a same-market YES/NO complement-parity candidate.

    The result is offline research metadata only. It is never an order intent
    and it does not assert that any edge is risk-free or executable.
    """

    yes_ask = ONE - snapshot.best_no_bid
    no_ask = ONE - snapshot.best_yes_bid
    gross_edge_per_contract = snapshot.best_yes_bid + snapshot.best_no_bid - ONE
    candidate_size = min(snapshot.yes_bid_size, snapshot.no_bid_size)
    fee, fee_status = _resolve_fee(snapshot)
    net_edge_per_contract = (
        gross_edge_per_contract
        - fee
        - snapshot.estimated_slippage_per_contract
        - snapshot.failed_leg_reserve_per_contract
    )
    total_estimated_net_edge = net_edge_per_contract * candidate_size

    flags = _candidate_flags(snapshot, gross_edge_per_contract, candidate_size)
    decision = _candidate_decision(
        gross_edge_per_contract=gross_edge_per_contract,
        net_edge_per_contract=net_edge_per_contract,
        minimum_net_edge_per_contract=snapshot.minimum_net_edge_per_contract,
        flags=flags,
    )

    return ComplementArbCandidate(
        venue=snapshot.venue,
        market_id=snapshot.market_id,
        best_yes_bid=snapshot.best_yes_bid,
        best_no_bid=snapshot.best_no_bid,
        yes_ask=yes_ask,
        no_ask=no_ask,
        gross_edge_per_contract=gross_edge_per_contract,
        candidate_size=candidate_size,
        estimated_fee_per_contract=fee if fee_status is FeeEstimateStatus.SUPPLIED else None,
        fee_status=fee_status,
        estimated_slippage_per_contract=snapshot.estimated_slippage_per_contract,
        failed_leg_reserve_per_contract=snapshot.failed_leg_reserve_per_contract,
        net_edge_per_contract=net_edge_per_contract,
        total_estimated_net_edge=total_estimated_net_edge,
        decision=decision,
        flags=flags,
    )


def compute_canonical_yes_side_cross_candidate(
    *,
    venue: str,
    market_id: str,
    best_yes_bid: Decimal,
    best_yes_ask: Decimal,
    yes_bid_size: Decimal,
    yes_ask_size: Decimal,
    estimated_fee_per_contract: Decimal | None = None,
    estimated_slippage_per_contract: Decimal = ZERO,
    failed_leg_reserve_per_contract: Decimal = ZERO,
    minimum_net_edge_per_contract: Decimal = ZERO,
    fee_estimate: FeeEstimate | None = None,
    stale_book: bool = False,
) -> ComplementArbCandidate:
    """Compute the equivalent candidate from canonical YES-side best bid/ask."""

    _require_decimal(best_yes_ask, field_name="best_yes_ask")
    _validate_probability_price(best_yes_ask, field_name="best_yes_ask")
    return compute_kalshi_complement_candidate(
        ComplementArbInput(
            venue=venue,
            market_id=market_id,
            best_yes_bid=best_yes_bid,
            best_no_bid=ONE - best_yes_ask,
            yes_bid_size=yes_bid_size,
            no_bid_size=yes_ask_size,
            estimated_fee_per_contract=estimated_fee_per_contract,
            estimated_slippage_per_contract=estimated_slippage_per_contract,
            failed_leg_reserve_per_contract=failed_leg_reserve_per_contract,
            minimum_net_edge_per_contract=minimum_net_edge_per_contract,
            fee_estimate=fee_estimate,
            stale_book=stale_book,
        )
    )


def _candidate_flags(
    snapshot: ComplementArbInput,
    gross_edge_per_contract: Decimal,
    candidate_size: Decimal,
) -> tuple[str, ...]:
    flags = ["manual_review_required"]
    if snapshot.stale_book:
        flags.append("stale_book")
    if candidate_size <= ZERO:
        flags.append("insufficient_depth")
    fee_status = _fee_status(snapshot)
    if fee_status is FeeEstimateStatus.MISSING:
        flags.append("missing_fee_model")
    elif fee_status is FeeEstimateStatus.UNKNOWN:
        flags.append("unknown_fee_model")
    if gross_edge_per_contract > ZERO:
        flags.append("crossed_book")
    elif gross_edge_per_contract == ZERO:
        flags.append("locked_book")
    return tuple(flags)


def _candidate_decision(
    *,
    gross_edge_per_contract: Decimal,
    net_edge_per_contract: Decimal,
    minimum_net_edge_per_contract: Decimal,
    flags: tuple[str, ...],
) -> ComplementArbDecision:
    if gross_edge_per_contract <= ZERO:
        return ComplementArbDecision.REJECT
    if "stale_book" in flags or "insufficient_depth" in flags or "missing_fee_model" in flags:
        return ComplementArbDecision.AUDIT_ONLY
    if "unknown_fee_model" in flags:
        return ComplementArbDecision.AUDIT_ONLY
    if net_edge_per_contract > minimum_net_edge_per_contract:
        return ComplementArbDecision.PAPER_CANDIDATE
    return ComplementArbDecision.REJECT


def _resolve_fee(snapshot: ComplementArbInput) -> tuple[Decimal, FeeEstimateStatus]:
    if snapshot.fee_estimate is not None:
        if snapshot.fee_estimate.status is FeeEstimateStatus.SUPPLIED:
            if snapshot.fee_estimate.fee_per_contract is None:
                msg = "supplied fee estimate requires fee_per_contract"
                raise ValueError(msg)
            return snapshot.fee_estimate.fee_per_contract, snapshot.fee_estimate.status
        return ZERO, snapshot.fee_estimate.status
    if snapshot.estimated_fee_per_contract is not None:
        return snapshot.estimated_fee_per_contract, FeeEstimateStatus.SUPPLIED
    return ZERO, FeeEstimateStatus.MISSING


def _fee_status(snapshot: ComplementArbInput) -> FeeEstimateStatus:
    return _resolve_fee(snapshot)[1]


def _require_decimal(value: Decimal, *, field_name: str) -> None:
    if not isinstance(value, Decimal):
        msg = f"{field_name} must be a Decimal"
        raise TypeError(msg)


def _validate_probability_price(value: Decimal, *, field_name: str) -> None:
    if value < ZERO or value > ONE:
        msg = f"{field_name} must be between 0 and 1"
        raise ValueError(msg)


def _validate_non_negative(value: Decimal, *, field_name: str) -> None:
    if value < ZERO:
        msg = f"{field_name} must be non-negative"
        raise ValueError(msg)


def _validate_optional_non_negative(value: Decimal | None, *, field_name: str) -> None:
    if value is not None:
        _validate_non_negative(value, field_name=field_name)
