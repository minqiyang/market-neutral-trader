"""Kalshi Demo read-only recorder guarded by explicit opt-in."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from edmn_trader.adapters.kalshi.client import (
    KALSHI_DEMO_REST_BASE_URL,
    KalshiConfigurationError,
    KalshiDemoMarketDataClient,
)
from edmn_trader.adapters.kalshi.orderbook import normalize_kalshi_orderbook_fp
from edmn_trader.data.live_events import LiveMarketDataEvent, write_live_events
from edmn_trader.data.snapshots import MarketDataSnapshot, write_snapshots


class KalshiReadOnlyOptInRequired(KalshiConfigurationError):
    """Raised when live read-only recording is requested without explicit opt-in."""


@dataclass(frozen=True, slots=True)
class KalshiReadOnlyRecorderConfig:
    """Config for one guarded Kalshi Demo read-only orderbook capture."""

    ticker: str
    events_output_path: Path
    snapshots_output_path: Path
    live_readonly_opt_in: bool = False
    environment: str = "demo"
    base_url: str = KALSHI_DEMO_REST_BASE_URL
    depth: int | None = None

    def __post_init__(self) -> None:
        if not self.ticker:
            msg = "ticker is required"
            raise ValueError(msg)
        if self.environment != "demo":
            msg = "Kalshi read-only recorder environment must be demo"
            raise KalshiConfigurationError(msg)
        if self.base_url.rstrip("/") != KALSHI_DEMO_REST_BASE_URL:
            msg = "Kalshi read-only recorder is restricted to the Demo REST base URL"
            raise KalshiConfigurationError(msg)
        if self.depth is not None and self.depth < 0:
            msg = "depth must be non-negative"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class KalshiReadOnlyRecorderResult:
    """Summary of one read-only recorder capture."""

    events_written: int
    snapshots_written: int
    data_quality_flags: tuple[str, ...]


def record_kalshi_readonly_orderbook(
    config: KalshiReadOnlyRecorderConfig,
    *,
    client: KalshiDemoMarketDataClient | None = None,
) -> KalshiReadOnlyRecorderResult:
    """Record one Kalshi Demo orderbook into raw event and normalized snapshot JSONL."""

    if not config.live_readonly_opt_in:
        msg = "Kalshi read-only recorder requires --live-readonly-opt-in"
        raise KalshiReadOnlyOptInRequired(msg)

    owns_client = client is None
    active_client = client or KalshiDemoMarketDataClient(base_url=config.base_url)
    try:
        raw_payload = active_client.get_market_orderbook(config.ticker, depth=config.depth)
    finally:
        if owns_client:
            active_client.close()

    raw_payload = dict(raw_payload)
    raw_payload.setdefault("market_ticker", config.ticker)
    now = datetime.now(UTC)
    normalized_book = normalize_kalshi_orderbook_fp(raw_payload)
    flags = _data_quality_flags(normalized_book=normalized_book)

    write_live_events(
        config.events_output_path,
        [
            LiveMarketDataEvent(
                venue="kalshi_demo",
                channel="orderbook_snapshot",
                market_id=config.ticker,
                event_type="orderbook_snapshot",
                sequence=1,
                observed_at=now,
                received_at=now,
                payload=raw_payload,
                source_type="kalshi_demo_rest",
                tags=("stage40", "kalshi_demo", "read_only", *flags),
            )
        ],
    )
    write_snapshots(
        config.snapshots_output_path,
        [
            MarketDataSnapshot(
                exchange="kalshi_demo",
                ticker=config.ticker,
                observed_at=now,
                recorded_at=now,
                normalized_orderbook=normalized_book,
                source_type="rest",
                raw_payload=raw_payload,
                notes="Recorded by guarded Kalshi Demo read-only recorder.",
                tags=("stage40", "kalshi_demo", "read_only", *flags),
            )
        ],
    )
    return KalshiReadOnlyRecorderResult(
        events_written=1,
        snapshots_written=1,
        data_quality_flags=flags,
    )


def _data_quality_flags(*, normalized_book) -> tuple[str, ...]:
    flags: list[str] = []
    if normalized_book.best_bid is None or normalized_book.best_ask is None:
        flags.append("one_sided_book")
    return tuple(flags)
