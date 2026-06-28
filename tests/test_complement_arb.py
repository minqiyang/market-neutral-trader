from decimal import Decimal

import pytest

from edmn_trader.arb import (
    ComplementArbDecision,
    ComplementArbInput,
    compute_canonical_yes_side_cross_candidate,
    compute_kalshi_complement_candidate,
)


def _input(
    *,
    best_yes_bid: Decimal,
    best_no_bid: Decimal,
    yes_bid_size: Decimal = Decimal("10"),
    no_bid_size: Decimal = Decimal("7"),
    estimated_fee_per_contract: Decimal | None = Decimal("0"),
    estimated_slippage_per_contract: Decimal = Decimal("0"),
    failed_leg_reserve_per_contract: Decimal = Decimal("0"),
    minimum_net_edge_per_contract: Decimal = Decimal("0"),
    stale_book: bool = False,
) -> ComplementArbInput:
    return ComplementArbInput(
        venue="kalshi_demo",
        market_id="DEMO-MARKET",
        best_yes_bid=best_yes_bid,
        best_no_bid=best_no_bid,
        yes_bid_size=yes_bid_size,
        no_bid_size=no_bid_size,
        estimated_fee_per_contract=estimated_fee_per_contract,
        estimated_slippage_per_contract=estimated_slippage_per_contract,
        failed_leg_reserve_per_contract=failed_leg_reserve_per_contract,
        minimum_net_edge_per_contract=minimum_net_edge_per_contract,
        stale_book=stale_book,
    )


def test_no_edge_when_yes_bid_plus_no_bid_is_below_one() -> None:
    candidate = compute_kalshi_complement_candidate(
        _input(best_yes_bid=Decimal("0.4800"), best_no_bid=Decimal("0.4900"))
    )

    assert candidate.yes_ask == Decimal("0.5100")
    assert candidate.no_ask == Decimal("0.5200")
    assert candidate.gross_edge_per_contract == Decimal("-0.0300")
    assert candidate.decision is ComplementArbDecision.REJECT
    assert "crossed_book" not in candidate.flags
    assert "locked_book" not in candidate.flags
    assert "manual_review_required" in candidate.flags


def test_locked_book_when_gross_edge_is_zero() -> None:
    candidate = compute_kalshi_complement_candidate(
        _input(best_yes_bid=Decimal("0.5000"), best_no_bid=Decimal("0.5000"))
    )

    assert candidate.gross_edge_per_contract == Decimal("0.0000")
    assert candidate.net_edge_per_contract == Decimal("0.0000")
    assert candidate.decision is ComplementArbDecision.REJECT
    assert "locked_book" in candidate.flags
    assert "manual_review_required" in candidate.flags


def test_crossed_complement_candidate_when_gross_edge_is_positive() -> None:
    candidate = compute_kalshi_complement_candidate(
        _input(
            best_yes_bid=Decimal("0.5300"),
            best_no_bid=Decimal("0.5200"),
            estimated_fee_per_contract=Decimal("0.0100"),
            estimated_slippage_per_contract=Decimal("0.0050"),
            failed_leg_reserve_per_contract=Decimal("0.0050"),
            minimum_net_edge_per_contract=Decimal("0.0100"),
        )
    )

    assert candidate.yes_ask == Decimal("0.4800")
    assert candidate.no_ask == Decimal("0.4700")
    assert candidate.gross_edge_per_contract == Decimal("0.0500")
    assert candidate.candidate_size == Decimal("7")
    assert candidate.net_edge_per_contract == Decimal("0.0300")
    assert candidate.total_estimated_net_edge == Decimal("0.2100")
    assert candidate.decision is ComplementArbDecision.PAPER_CANDIDATE
    assert "crossed_book" in candidate.flags
    assert "manual_review_required" in candidate.flags


def test_net_edge_rejected_after_fees_slippage_and_failed_leg_reserve() -> None:
    candidate = compute_kalshi_complement_candidate(
        _input(
            best_yes_bid=Decimal("0.5200"),
            best_no_bid=Decimal("0.5100"),
            estimated_fee_per_contract=Decimal("0.0200"),
            estimated_slippage_per_contract=Decimal("0.0100"),
            failed_leg_reserve_per_contract=Decimal("0.0100"),
        )
    )

    assert candidate.gross_edge_per_contract == Decimal("0.0300")
    assert candidate.net_edge_per_contract == Decimal("-0.0100")
    assert candidate.decision is ComplementArbDecision.REJECT
    assert "crossed_book" in candidate.flags


def test_paper_candidate_requires_net_edge_above_threshold() -> None:
    at_threshold = compute_kalshi_complement_candidate(
        _input(
            best_yes_bid=Decimal("0.5400"),
            best_no_bid=Decimal("0.5000"),
            estimated_fee_per_contract=Decimal("0.0100"),
            estimated_slippage_per_contract=Decimal("0.0050"),
            failed_leg_reserve_per_contract=Decimal("0.0050"),
            minimum_net_edge_per_contract=Decimal("0.0200"),
        )
    )
    above_threshold = compute_kalshi_complement_candidate(
        _input(
            best_yes_bid=Decimal("0.5401"),
            best_no_bid=Decimal("0.5000"),
            estimated_fee_per_contract=Decimal("0.0100"),
            estimated_slippage_per_contract=Decimal("0.0050"),
            failed_leg_reserve_per_contract=Decimal("0.0050"),
            minimum_net_edge_per_contract=Decimal("0.0200"),
        )
    )

    assert at_threshold.net_edge_per_contract == Decimal("0.0200")
    assert at_threshold.decision is ComplementArbDecision.REJECT
    assert above_threshold.net_edge_per_contract == Decimal("0.0201")
    assert above_threshold.decision is ComplementArbDecision.PAPER_CANDIDATE


def test_decimal_precision_is_preserved() -> None:
    candidate = compute_kalshi_complement_candidate(
        _input(
            best_yes_bid=Decimal("0.3333"),
            best_no_bid=Decimal("0.6668"),
            yes_bid_size=Decimal("3"),
            no_bid_size=Decimal("5"),
        )
    )

    assert candidate.gross_edge_per_contract == Decimal("0.0001")
    assert candidate.net_edge_per_contract == Decimal("0.0001")
    assert candidate.total_estimated_net_edge == Decimal("0.0003")


def test_invalid_negative_prices_are_rejected() -> None:
    with pytest.raises(ValueError, match="best_yes_bid must be between 0 and 1"):
        _input(best_yes_bid=Decimal("-0.0100"), best_no_bid=Decimal("0.5000"))


def test_prices_above_one_are_rejected() -> None:
    with pytest.raises(ValueError, match="best_no_bid must be between 0 and 1"):
        _input(best_yes_bid=Decimal("0.5000"), best_no_bid=Decimal("1.0100"))


def test_missing_fee_model_cannot_become_paper_candidate() -> None:
    candidate = compute_kalshi_complement_candidate(
        _input(
            best_yes_bid=Decimal("0.5300"),
            best_no_bid=Decimal("0.5200"),
            estimated_fee_per_contract=None,
        )
    )

    assert candidate.net_edge_per_contract == Decimal("0.0500")
    assert candidate.decision is ComplementArbDecision.AUDIT_ONLY
    assert "missing_fee_model" in candidate.flags
    assert "manual_review_required" in candidate.flags


def test_canonical_yes_side_cross_candidate_derives_no_bid_from_yes_ask() -> None:
    candidate = compute_canonical_yes_side_cross_candidate(
        venue="kalshi_demo",
        market_id="DEMO-MARKET",
        best_yes_bid=Decimal("0.5300"),
        best_yes_ask=Decimal("0.4800"),
        yes_bid_size=Decimal("10"),
        yes_ask_size=Decimal("7"),
        estimated_fee_per_contract=Decimal("0.0100"),
        estimated_slippage_per_contract=Decimal("0.0050"),
        failed_leg_reserve_per_contract=Decimal("0.0050"),
        minimum_net_edge_per_contract=Decimal("0.0100"),
    )

    assert candidate.best_no_bid == Decimal("0.5200")
    assert candidate.yes_ask == Decimal("0.4800")
    assert candidate.gross_edge_per_contract == Decimal("0.0500")
    assert candidate.decision is ComplementArbDecision.PAPER_CANDIDATE
