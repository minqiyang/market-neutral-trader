"""Polymarket US market-channel recorder guarded by explicit opt-in."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edmn_trader.adapters.polymarket_us.client import (
    POLYMARKET_US_PUBLIC_BASE_URL,
    PolymarketUSConfigurationError,
    PolymarketUSMarketDataClient,
)
from edmn_trader.adapters.polymarket_us.orderbook import normalize_polymarket_us_market_book
from edmn_trader.data.live_events import LiveMarketDataEvent, write_live_events
from edmn_trader.data.snapshots import MarketDataSnapshot, write_snapshots


class PolymarketUSReadOnlyOptInRequired(PolymarketUSConfigurationError):
    """Raised when market-channel recording is requested without explicit opt-in."""


@dataclass(frozen=True, slots=True)
class PolymarketUSMarketRecorderConfig:
    """Config for one guarded Polymarket US market-channel capture."""

    slug: str
    events_output_path: Path
    snapshots_output_path: Path
    live_readonly_opt_in: bool = False
    environment: str = "us_public"
    base_url: str = POLYMARKET_US_PUBLIC_BASE_URL

    def __post_init__(self) -> None:
        if not self.slug:
            msg = "slug is required"
            raise ValueError(msg)
        if self.environment != "us_public":
            msg = "Polymarket US market recorder environment must be us_public"
            raise PolymarketUSConfigurationError(msg)
        if self.base_url.rstrip("/") != POLYMARKET_US_PUBLIC_BASE_URL:
            msg = (
                "Polymarket US market recorder is restricted to the public base URL: "
                f"{POLYMARKET_US_PUBLIC_BASE_URL}"
            )
            raise PolymarketUSConfigurationError(msg)


@dataclass(frozen=True, slots=True)
class PolymarketUSMarketRecorderResult:
    """Summary of one market-channel recorder capture."""

    events_written: int
    snapshots_written: int
    data_quality_flags: tuple[str, ...]


def record_polymarket_us_market_channel(
    config: PolymarketUSMarketRecorderConfig,
    *,
    client: PolymarketUSMarketDataClient | None = None,
) -> PolymarketUSMarketRecorderResult:
    """Record one Polymarket US market-channel book into event and snapshot JSONL."""

    if not config.live_readonly_opt_in:
        msg = "Polymarket US market recorder requires --live-readonly-opt-in"
        raise PolymarketUSReadOnlyOptInRequired(msg)

    owns_client = client is None
    active_client = client or PolymarketUSMarketDataClient(base_url=config.base_url)
    try:
        raw_payload = active_client.get_market_book(config.slug)
    finally:
        if owns_client:
            active_client.close()

    now = datetime.now(UTC)
    normalized_book = normalize_polymarket_us_market_book(raw_payload)
    flags = _data_quality_flags(raw_payload=raw_payload, normalized_book=normalized_book)

    write_live_events(
        config.events_output_path,
        [
            LiveMarketDataEvent(
                venue="polymarket_us",
                channel="market",
                market_id=config.slug,
                event_type="market_book_snapshot",
                sequence=1,
                observed_at=now,
                received_at=now,
                payload=raw_payload,
                source_type="polymarket_us_market_channel",
                tags=("stage41", "polymarket_us", "market_channel", "read_only", *flags),
            )
        ],
    )
    write_snapshots(
        config.snapshots_output_path,
        [
            MarketDataSnapshot(
                exchange="polymarket_us",
                ticker=config.slug,
                observed_at=now,
                recorded_at=now,
                normalized_orderbook=normalized_book,
                source_type="rest",
                raw_payload=raw_payload,
                notes="Recorded by guarded Polymarket US market-channel recorder.",
                tags=("stage41", "polymarket_us", "market_channel", "read_only", *flags),
            )
        ],
    )
    return PolymarketUSMarketRecorderResult(
        events_written=1,
        snapshots_written=1,
        data_quality_flags=flags,
    )


def _data_quality_flags(
    *,
    raw_payload: dict[str, Any],
    normalized_book,
) -> tuple[str, ...]:
    flags: list[str] = []
    if normalized_book.best_bid is None or normalized_book.best_ask is None:
        flags.append("one_sided_book")

    market_data = raw_payload.get("marketData")
    if isinstance(market_data, dict) and market_data.get("state") != "OPEN":
        flags.append("non_open_market")

    return tuple(flags)
