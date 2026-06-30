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
from edmn_trader.adapters.kalshi.demo_connector import (
    KalshiDemoConnectorConfig,
    KalshiDemoConnectorError,
    KalshiDemoConnectorResult,
    KalshiDemoRequestPreview,
    load_kalshi_demo_auth_headers_from_env,
    preview_or_submit_kalshi_demo,
    write_kalshi_demo_result_jsonl,
)
from edmn_trader.adapters.kalshi.demo_reconciliation import (
    KalshiDemoOrderState,
    KalshiDemoReconciliationError,
    KalshiDemoReconciliationMismatch,
    KalshiDemoReconciliationState,
    append_kalshi_demo_reconciliation_jsonl,
    reconcile_kalshi_demo_events,
    require_demo_reconciliation_submit_eligible,
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
    "KalshiDemoConnectorConfig",
    "KalshiDemoConnectorError",
    "KalshiDemoConnectorResult",
    "KalshiDemoMarketDataClient",
    "KalshiDemoOrderState",
    "KalshiDemoRequestPreview",
    "KalshiDemoReconciliationError",
    "KalshiDemoReconciliationMismatch",
    "KalshiDemoReconciliationState",
    "KalshiEmptyOrderBookError",
    "KalshiHTTPError",
    "KalshiReadOnlyOptInRequired",
    "KalshiReadOnlyRecorderConfig",
    "KalshiReadOnlyRecorderResult",
    "KalshiResponseError",
    "append_kalshi_demo_reconciliation_jsonl",
    "load_kalshi_demo_auth_headers_from_env",
    "normalize_kalshi_orderbook_fp",
    "preview_or_submit_kalshi_demo",
    "reconcile_kalshi_demo_events",
    "record_kalshi_readonly_orderbook",
    "require_demo_reconciliation_submit_eligible",
    "write_kalshi_demo_result_jsonl",
]
