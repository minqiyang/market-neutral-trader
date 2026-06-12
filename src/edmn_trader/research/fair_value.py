"""Deterministic baseline fair-value models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from edmn_trader.core.models import NormalizedOrderBook

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class MidpointFairValueModel:
    """Baseline fair value from normalized orderbook state.

    This model is deterministic and descriptive. It is not predictive and does
    not imply profitability.
    """

    one_sided_offset: Decimal = Decimal("0.0100")

    def __post_init__(self) -> None:
        if not isinstance(self.one_sided_offset, Decimal):
            msg = "one_sided_offset must be a Decimal"
            raise TypeError(msg)
        if self.one_sided_offset <= ZERO:
            msg = "one_sided_offset must be positive"
            raise ValueError(msg)

    def estimate(self, book: NormalizedOrderBook) -> Decimal:
        """Estimate fair value from a normalized book."""

        if book.mid is not None:
            return book.mid
        if book.best_bid_price is not None:
            return _clamp_probability(book.best_bid_price + self.one_sided_offset)
        if book.best_ask_price is not None:
            return _clamp_probability(book.best_ask_price - self.one_sided_offset)

        msg = "cannot estimate fair value from an empty orderbook"
        raise ValueError(msg)


def _clamp_probability(value: Decimal) -> Decimal:
    return min(max(value, ZERO), ONE)
