"""Dry-run quote generation from fair value and replayed orderbooks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Literal

from edmn_trader.core.models import NormalizedOrderBook
from edmn_trader.research.fair_value import MidpointFairValueModel

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")
DRY_RUN_LIMITATION = "dry-run only; no execution or order placement"


@dataclass(frozen=True, slots=True)
class QuoteEngineConfig:
    """Deterministic dry-run quote engine parameters."""

    tick_size: Decimal = Decimal("0.0001")
    default_spread: Decimal = Decimal("0.0200")
    min_spread: Decimal = Decimal("0.0001")
    order_quantity: Decimal = Decimal("1.00")
    inventory_skew_per_unit: Decimal = Decimal("0.0010")
    max_inventory_skew: Decimal = Decimal("0.0500")
    min_price: Decimal = ZERO
    max_price: Decimal = ONE

    def __post_init__(self) -> None:
        for field_name in (
            "tick_size",
            "default_spread",
            "min_spread",
            "order_quantity",
            "inventory_skew_per_unit",
            "max_inventory_skew",
            "min_price",
            "max_price",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                msg = f"{field_name} must be a Decimal"
                raise TypeError(msg)

        if self.tick_size <= ZERO:
            msg = "tick_size must be positive"
            raise ValueError(msg)
        if self.default_spread <= ZERO:
            msg = "default_spread must be positive"
            raise ValueError(msg)
        if self.min_spread <= ZERO:
            msg = "min_spread must be positive"
            raise ValueError(msg)
        if self.order_quantity <= ZERO:
            msg = "order_quantity must be positive"
            raise ValueError(msg)
        if self.inventory_skew_per_unit < ZERO:
            msg = "inventory_skew_per_unit must be non-negative"
            raise ValueError(msg)
        if self.max_inventory_skew < ZERO:
            msg = "max_inventory_skew must be non-negative"
            raise ValueError(msg)
        if self.min_price < ZERO or self.max_price > ONE or self.min_price >= self.max_price:
            msg = "price boundaries must be within [0, 1] and min_price < max_price"
            raise ValueError(msg)
        if self.min_spread < self.tick_size:
            msg = "min_spread must be at least one tick"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DryRunOrderIntent:
    """Non-executable order candidate for dry-run inspection."""

    instrument_id: str
    side: Literal["buy", "sell"]
    price: Decimal
    quantity: Decimal
    reason: str
    dry_run: bool = True
    execution_policy: str = "dry_run_only"

    def __post_init__(self) -> None:
        if self.side not in {"buy", "sell"}:
            msg = "side must be buy or sell"
            raise ValueError(msg)
        for field_name in ("price", "quantity"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                msg = f"{field_name} must be a Decimal"
                raise TypeError(msg)
        if self.price < ZERO or self.price > ONE:
            msg = "price must be within [0, 1]"
            raise ValueError(msg)
        if self.quantity <= ZERO:
            msg = "quantity must be positive"
            raise ValueError(msg)
        if not self.dry_run or self.execution_policy != "dry_run_only":
            msg = "dry-run intents must remain non-executable"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DryRunQuoteResult:
    """Dry-run quote result and diagnostics for one book."""

    instrument_id: str
    fair_value: Decimal
    adjusted_fair_value: Decimal
    inventory: Decimal
    inventory_skew: Decimal
    target_spread: Decimal
    bid_intent: DryRunOrderIntent
    ask_intent: DryRunOrderIntent
    limitations: tuple[str, ...]

    @property
    def bid_price(self) -> Decimal:
        return self.bid_intent.price

    @property
    def ask_price(self) -> Decimal:
        return self.ask_intent.price


class DryRunQuoteEngine:
    """Generate non-executable quote candidates from normalized orderbooks."""

    def __init__(
        self,
        *,
        config: QuoteEngineConfig | None = None,
        fair_value_model: MidpointFairValueModel | None = None,
    ) -> None:
        self.config = config or QuoteEngineConfig()
        self.fair_value_model = fair_value_model or MidpointFairValueModel()

    def quote(self, book: NormalizedOrderBook, *, inventory: Decimal = ZERO) -> DryRunQuoteResult:
        """Generate a dry-run two-sided quote for a normalized orderbook."""

        if not isinstance(inventory, Decimal):
            msg = "inventory must be a Decimal"
            raise TypeError(msg)

        fair_value = self.fair_value_model.estimate(book)
        inventory_skew = self._inventory_skew(inventory)
        adjusted_fair_value = _clamp(fair_value - inventory_skew, self.config)
        target_spread = self._target_spread(book)
        half_spread = target_spread / TWO

        bid_price = _floor_to_tick(adjusted_fair_value - half_spread, self.config)
        ask_price = _ceil_to_tick(adjusted_fair_value + half_spread, self.config)
        bid_price, ask_price = _enforce_two_sided_boundary(bid_price, ask_price, self.config)

        reason = (
            "dry-run quote from baseline fair value, current orderbook spread, "
            "and bounded inventory skew"
        )
        return DryRunQuoteResult(
            instrument_id=book.instrument_id,
            fair_value=fair_value,
            adjusted_fair_value=adjusted_fair_value,
            inventory=inventory,
            inventory_skew=inventory_skew,
            target_spread=ask_price - bid_price,
            bid_intent=DryRunOrderIntent(
                instrument_id=book.instrument_id,
                side="buy",
                price=bid_price,
                quantity=self.config.order_quantity,
                reason=reason,
            ),
            ask_intent=DryRunOrderIntent(
                instrument_id=book.instrument_id,
                side="sell",
                price=ask_price,
                quantity=self.config.order_quantity,
                reason=reason,
            ),
            limitations=(DRY_RUN_LIMITATION,),
        )

    def _inventory_skew(self, inventory: Decimal) -> Decimal:
        raw_skew = inventory * self.config.inventory_skew_per_unit
        return min(max(raw_skew, -self.config.max_inventory_skew), self.config.max_inventory_skew)

    def _target_spread(self, book: NormalizedOrderBook) -> Decimal:
        observed_spread = book.spread if book.spread is not None else self.config.default_spread
        return max(observed_spread, self.config.default_spread, self.config.min_spread)


def _floor_to_tick(value: Decimal, config: QuoteEngineConfig) -> Decimal:
    clamped = _clamp(value, config)
    ticks = (clamped / config.tick_size).to_integral_value(rounding=ROUND_FLOOR)
    return _clamp(ticks * config.tick_size, config)


def _ceil_to_tick(value: Decimal, config: QuoteEngineConfig) -> Decimal:
    clamped = _clamp(value, config)
    ticks = (clamped / config.tick_size).to_integral_value(rounding=ROUND_CEILING)
    return _clamp(ticks * config.tick_size, config)


def _enforce_two_sided_boundary(
    bid_price: Decimal,
    ask_price: Decimal,
    config: QuoteEngineConfig,
) -> tuple[Decimal, Decimal]:
    if bid_price < ask_price:
        return bid_price, ask_price

    if ask_price + config.tick_size <= config.max_price:
        return bid_price, ask_price + config.tick_size
    if bid_price - config.tick_size >= config.min_price:
        return bid_price - config.tick_size, ask_price

    msg = "price boundaries cannot support a two-sided dry-run quote"
    raise ValueError(msg)


def _clamp(value: Decimal, config: QuoteEngineConfig) -> Decimal:
    return min(max(value, config.min_price), config.max_price)
