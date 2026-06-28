from decimal import Decimal

import pytest

from edmn_trader.arb import ComplementArbDecision, ComplementArbInput
from edmn_trader.arb.complement import compute_kalshi_complement_candidate
from edmn_trader.fees import (
    FeeEstimateStatus,
    kalshi_missing_fee_estimate,
    kalshi_supplied_fee_estimate,
    kalshi_unknown_fee_estimate,
    polymarket_us_missing_fee_estimate,
    polymarket_us_supplied_fee_estimate,
)


def test_kalshi_supplied_fee_assumption_can_support_paper_candidate() -> None:
    candidate = compute_kalshi_complement_candidate(
        ComplementArbInput(
            venue="kalshi_demo",
            market_id="DEMO-MARKET",
            best_yes_bid=Decimal("0.5300"),
            best_no_bid=Decimal("0.5200"),
            yes_bid_size=Decimal("10"),
            no_bid_size=Decimal("7"),
            fee_estimate=kalshi_supplied_fee_estimate(
                Decimal("0.0100"),
                source_note="operator supplied conservative demo fee assumption",
            ),
            estimated_slippage_per_contract=Decimal("0.0050"),
            failed_leg_reserve_per_contract=Decimal("0.0050"),
            minimum_net_edge_per_contract=Decimal("0.0100"),
        )
    )

    assert candidate.fee_status is FeeEstimateStatus.SUPPLIED
    assert candidate.estimated_fee_per_contract == Decimal("0.0100")
    assert candidate.net_edge_per_contract == Decimal("0.0300")
    assert candidate.decision is ComplementArbDecision.PAPER_CANDIDATE


@pytest.mark.parametrize(
    "fee_estimate",
    [
        kalshi_missing_fee_estimate(),
        kalshi_unknown_fee_estimate(source_note="market-specific schedule not supplied"),
    ],
)
def test_kalshi_missing_or_unknown_fee_blocks_paper_candidate(fee_estimate) -> None:
    candidate = compute_kalshi_complement_candidate(
        ComplementArbInput(
            venue="kalshi_demo",
            market_id="DEMO-MARKET",
            best_yes_bid=Decimal("0.5300"),
            best_no_bid=Decimal("0.5200"),
            yes_bid_size=Decimal("10"),
            no_bid_size=Decimal("7"),
            fee_estimate=fee_estimate,
        )
    )

    assert candidate.fee_status is fee_estimate.status
    assert candidate.estimated_fee_per_contract is None
    assert candidate.decision is ComplementArbDecision.AUDIT_ONLY
    assert "missing_fee_model" in candidate.flags or "unknown_fee_model" in candidate.flags


def test_candidate_rejects_conflicting_fee_inputs() -> None:
    with pytest.raises(ValueError, match="use fee_estimate or estimated_fee_per_contract"):
        ComplementArbInput(
            venue="kalshi_demo",
            market_id="DEMO-MARKET",
            best_yes_bid=Decimal("0.5300"),
            best_no_bid=Decimal("0.5200"),
            yes_bid_size=Decimal("10"),
            no_bid_size=Decimal("7"),
            estimated_fee_per_contract=Decimal("0.0100"),
            fee_estimate=kalshi_supplied_fee_estimate(
                Decimal("0.0100"),
                source_note="operator supplied",
            ),
        )


def test_candidate_rejects_fee_estimate_for_different_venue() -> None:
    with pytest.raises(ValueError, match="fee_estimate venue must match input venue"):
        ComplementArbInput(
            venue="kalshi_demo",
            market_id="DEMO-MARKET",
            best_yes_bid=Decimal("0.5300"),
            best_no_bid=Decimal("0.5200"),
            yes_bid_size=Decimal("10"),
            no_bid_size=Decimal("7"),
            fee_estimate=polymarket_us_supplied_fee_estimate(
                Decimal("0.0200"),
                source_note="operator supplied",
            ),
        )


def test_supplied_fee_assumption_requires_decimal_and_source_note() -> None:
    with pytest.raises(TypeError, match="fee_per_contract must be a Decimal"):
        kalshi_supplied_fee_estimate("0.0100", source_note="operator supplied")

    with pytest.raises(ValueError, match="source_note is required"):
        kalshi_supplied_fee_estimate(Decimal("0.0100"), source_note="")


def test_negative_supplied_fee_is_rejected() -> None:
    with pytest.raises(ValueError, match="fee_per_contract must be non-negative"):
        kalshi_supplied_fee_estimate(Decimal("-0.0100"), source_note="operator supplied")


def test_polymarket_us_scaffold_is_explicit_or_missing_only() -> None:
    supplied = polymarket_us_supplied_fee_estimate(
        Decimal("0.0200"),
        source_note="operator supplied local paper assumption",
    )
    missing = polymarket_us_missing_fee_estimate()

    assert supplied.venue == "polymarket_us"
    assert supplied.status is FeeEstimateStatus.SUPPLIED
    assert supplied.fee_per_contract == Decimal("0.0200")
    assert not supplied.blocks_paper_candidate
    assert missing.status is FeeEstimateStatus.MISSING
    assert missing.fee_per_contract is None
    assert missing.blocks_paper_candidate
