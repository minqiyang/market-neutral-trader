"""Kalshi Demo adapter helpers."""

from edmn_trader.adapters.kalshi.client import (
    KALSHI_DEMO_REST_BASE_URL,
    KalshiClientError,
    KalshiConfigurationError,
    KalshiDemoMarketDataClient,
    KalshiEmptyOrderBookError,
    KalshiHTTPError,
    KalshiResponseError,
)
from edmn_trader.adapters.kalshi.orderbook import normalize_kalshi_orderbook_fp
from edmn_trader.adapters.kalshi.readonly_recorder import (
    KalshiReadOnlyOptInRequired,
    KalshiReadOnlyRecorderConfig,
    KalshiReadOnlyRecorderResult,
    record_kalshi_readonly_orderbook,
)

__all__ = [
    "KALSHI_DEMO_REST_BASE_URL",
    "KalshiClientError",
    "KalshiConfigurationError",
    "KalshiDemoMarketDataClient",
    "KalshiEmptyOrderBookError",
    "KalshiHTTPError",
    "KalshiReadOnlyOptInRequired",
    "KalshiReadOnlyRecorderConfig",
    "KalshiReadOnlyRecorderResult",
    "KalshiResponseError",
    "normalize_kalshi_orderbook_fp",
    "record_kalshi_readonly_orderbook",
]
