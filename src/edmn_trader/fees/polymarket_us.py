"""Polymarket US fee estimate scaffold.

This stage does not implement a fee formula. It only supports explicit Decimal
assumptions or a blocking missing/unknown status.
"""

from __future__ import annotations

from decimal import Decimal

from edmn_trader.fees.base import FeeEstimate, missing_fee_estimate, supplied_fee_estimate
from edmn_trader.fees.base import unknown_fee_estimate as base_unknown_fee_estimate

POLYMARKET_US_VENUE = "polymarket_us"


def polymarket_us_supplied_fee_estimate(
    fee_per_contract: Decimal,
    *,
    source_note: str,
    venue: str = POLYMARKET_US_VENUE,
) -> FeeEstimate:
    return supplied_fee_estimate(
        venue=venue,
        fee_per_contract=fee_per_contract,
        source_note=source_note,
    )


def polymarket_us_missing_fee_estimate(*, venue: str = POLYMARKET_US_VENUE) -> FeeEstimate:
    return missing_fee_estimate(venue=venue, source_note="Polymarket US fee model not supplied")


def polymarket_us_unknown_fee_estimate(
    *,
    source_note: str,
    venue: str = POLYMARKET_US_VENUE,
) -> FeeEstimate:
    return base_unknown_fee_estimate(venue=venue, source_note=source_note)
