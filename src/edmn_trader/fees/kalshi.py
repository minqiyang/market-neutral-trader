"""Kalshi fee estimate scaffold.

No venue fee schedule is hard-coded here. Callers must supply an explicit
Decimal assumption, or the fee estimate blocks paper-candidate decisions.
"""

from __future__ import annotations

from decimal import Decimal

from edmn_trader.fees.base import FeeEstimate, missing_fee_estimate, supplied_fee_estimate
from edmn_trader.fees.base import unknown_fee_estimate as base_unknown_fee_estimate

KALSHI_DEMO_VENUE = "kalshi_demo"


def kalshi_supplied_fee_estimate(
    fee_per_contract: Decimal,
    *,
    source_note: str,
    venue: str = KALSHI_DEMO_VENUE,
) -> FeeEstimate:
    return supplied_fee_estimate(
        venue=venue,
        fee_per_contract=fee_per_contract,
        source_note=source_note,
    )


def kalshi_missing_fee_estimate(*, venue: str = KALSHI_DEMO_VENUE) -> FeeEstimate:
    return missing_fee_estimate(venue=venue, source_note="Kalshi fee model not supplied")


def kalshi_unknown_fee_estimate(
    *,
    source_note: str,
    venue: str = KALSHI_DEMO_VENUE,
) -> FeeEstimate:
    return base_unknown_fee_estimate(venue=venue, source_note=source_note)
