from __future__ import annotations

from decimal import Decimal

import pytest

from edmn_trader.core.models import NormalizedOrderBook, OrderBookLevel
from edmn_trader.research import (
    DRY_RUN_LIMITATION,
    DryRunOrderIntent,
    DryRunQuoteEngine,
    MidpointFairValueModel,
    QuoteEngineConfig,
)


def test_midpoint_fair_value_for_two_sided_book() -> None:
    fair_value = MidpointFairValueModel().estimate(_book())

    assert fair_value == Decimal("0.4300")


def test_one_sided_fair_value_fallbacks_are_deterministic() -> None:
    model = MidpointFairValueModel(one_sided_offset=Decimal("0.0100"))

    assert model.estimate(_book(asks=())) == Decimal("0.4300")
    assert model.estimate(_book(bids=())) == Decimal("0.4300")


def test_empty_book_has_no_fair_value() -> None:
    with pytest.raises(ValueError, match="empty orderbook"):
        MidpointFairValueModel().estimate(_book(bids=(), asks=()))


def test_quote_generation_from_fair_value_and_orderbook_state() -> None:
    engine = DryRunQuoteEngine(
        config=QuoteEngineConfig(order_quantity=Decimal("2.00")),
    )

    result = engine.quote(_book())

    assert result.fair_value == Decimal("0.4300")
    assert result.adjusted_fair_value == Decimal("0.4300")
    assert result.bid_price == Decimal("0.4200")
    assert result.ask_price == Decimal("0.4400")
    assert result.target_spread == Decimal("0.0200")
    assert result.bid_intent.quantity == Decimal("2.00")
    assert result.ask_intent.quantity == Decimal("2.00")
    assert result.limitations == (DRY_RUN_LIMITATION,)


def test_inventory_skew_moves_quotes_to_reduce_inventory_pressure() -> None:
    engine = DryRunQuoteEngine()

    long_inventory_quote = engine.quote(_book(), inventory=Decimal("10"))
    short_inventory_quote = engine.quote(_book(), inventory=Decimal("-10"))

    assert long_inventory_quote.inventory_skew == Decimal("0.0100")
    assert long_inventory_quote.adjusted_fair_value == Decimal("0.4200")
    assert long_inventory_quote.bid_price == Decimal("0.4100")
    assert long_inventory_quote.ask_price == Decimal("0.4300")
    assert short_inventory_quote.inventory_skew == Decimal("-0.0100")
    assert short_inventory_quote.adjusted_fair_value == Decimal("0.4400")
    assert short_inventory_quote.bid_price == Decimal("0.4300")
    assert short_inventory_quote.ask_price == Decimal("0.4500")


def test_inventory_skew_is_bounded() -> None:
    engine = DryRunQuoteEngine(
        config=QuoteEngineConfig(max_inventory_skew=Decimal("0.0050")),
    )

    result = engine.quote(_book(), inventory=Decimal("100"))

    assert result.inventory_skew == Decimal("0.0050")


def test_quote_engine_enforces_tick_and_price_boundaries() -> None:
    engine = DryRunQuoteEngine(
        config=QuoteEngineConfig(
            tick_size=Decimal("0.0100"),
            min_spread=Decimal("0.0100"),
            default_spread=Decimal("0.1000"),
        )
    )
    book = _book(
        bids=(OrderBookLevel(price=Decimal("0.0100"), quantity=Decimal("1")),),
        asks=(OrderBookLevel(price=Decimal("0.0200"), quantity=Decimal("1")),),
    )

    result = engine.quote(book)

    assert result.bid_price == Decimal("0")
    assert result.ask_price == Decimal("0.0700")
    assert result.bid_price < result.ask_price


def test_quote_engine_rounds_to_tick() -> None:
    engine = DryRunQuoteEngine(
        config=QuoteEngineConfig(
            tick_size=Decimal("0.0100"),
            min_spread=Decimal("0.0100"),
            default_spread=Decimal("0.0200"),
        )
    )
    book = _book(
        bids=(OrderBookLevel(price=Decimal("0.4233"), quantity=Decimal("1")),),
        asks=(OrderBookLevel(price=Decimal("0.4433"), quantity=Decimal("1")),),
    )

    result = engine.quote(book)

    assert result.fair_value == Decimal("0.4333")
    assert result.bid_price == Decimal("0.4200")
    assert result.ask_price == Decimal("0.4500")


def test_dry_run_intents_are_non_executable() -> None:
    result = DryRunQuoteEngine().quote(_book())

    assert result.bid_intent.dry_run is True
    assert result.bid_intent.execution_policy == "dry_run_only"
    assert result.ask_intent.dry_run is True
    assert result.ask_intent.execution_policy == "dry_run_only"

    with pytest.raises(ValueError, match="non-executable"):
        DryRunOrderIntent(
            instrument_id="DEMO",
            side="buy",
            price=Decimal("0.4200"),
            quantity=Decimal("1"),
            reason="invalid executable-like intent",
            dry_run=False,
        )


def _book(
    *,
    bids: tuple[OrderBookLevel, ...] = (
        OrderBookLevel(price=Decimal("0.4200"), quantity=Decimal("13.00")),
    ),
    asks: tuple[OrderBookLevel, ...] = (
        OrderBookLevel(price=Decimal("0.4400"), quantity=Decimal("17.00")),
    ),
) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        instrument_id="DEMO-EVENT-MARKET",
        bids=bids,
        asks=asks,
        source="test",
    )
