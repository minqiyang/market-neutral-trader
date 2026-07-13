"""Read-only Kalshi Demo REST market-data client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self
from urllib.parse import quote

import httpx

from edmn_trader.adapters.kalshi.orderbook import normalize_kalshi_orderbook_fp
from edmn_trader.core.models import NormalizedOrderBook

KALSHI_DEMO_REST_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"
_USER_AGENT = "edmn-trader/0.1 read-only-demo-client"
_MARKET_STATUS_MAP = {
    "initialized": "unopened",
    "active": "open",
    "inactive": "paused",
    "closed": "closed",
    "determined": "closed",
    "disputed": "closed",
    "amended": "closed",
    "finalized": "settled",
}


class KalshiClientError(Exception):
    """Base class for Kalshi adapter client errors."""


class KalshiConfigurationError(KalshiClientError):
    """Raised when client configuration would leave the allowed demo boundary."""


class KalshiHTTPError(KalshiClientError):
    """Raised for non-success HTTP status codes from Kalshi Demo."""

    def __init__(self, *, status_code: int, path: str, body: str) -> None:
        self.status_code = status_code
        self.path = path
        self.body = body
        super().__init__(f"Kalshi Demo GET {path} returned HTTP {status_code}: {body}")


class KalshiResponseError(KalshiClientError):
    """Raised when a Kalshi Demo response cannot be decoded or validated."""


class KalshiEmptyOrderBookError(KalshiResponseError):
    """Raised when a read-only orderbook response contains no YES or NO levels."""


class KalshiDemoMarketDataClient:
    """Guarded read-only client for public Kalshi Demo market-data endpoints."""

    def __init__(
        self,
        *,
        base_url: str = KALSHI_DEMO_REST_BASE_URL,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        _validate_demo_base_url(self.base_url)

        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client when this instance owns it."""

        if self._owns_client:
            self._client.close()

    def list_markets(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        status: str | None = None,
        mve_filter: str | None = None,
    ) -> dict[str, Any]:
        """Return public Kalshi Demo market metadata."""

        if limit <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        if mve_filter not in {None, "only", "exclude"}:
            raise ValueError("mve_filter must be only or exclude")

        payload = self._get_json(
            "/markets",
            params={
                "limit": limit,
                "cursor": cursor,
                "status": status,
                "mve_filter": mve_filter,
            },
        )
        _validate_markets_payload(payload)
        return payload

    def get_market(self, ticker: str) -> dict[str, Any]:
        """Return one public Kalshi Demo market record."""

        clean_ticker = _validate_ticker(ticker)
        payload = self._get_json(f"/markets/{quote(clean_ticker, safe='')}", params={})
        return _object_payload(payload, key="market", resource="market")

    def get_event(self, event_ticker: str) -> dict[str, Any]:
        """Return one public Kalshi Demo event record."""

        clean_ticker = _validate_ticker(event_ticker)
        payload = self._get_json(f"/events/{quote(clean_ticker, safe='')}", params={})
        return _object_payload(payload, key="event", resource="event")

    def list_events(
        self,
        *,
        limit: int = 200,
        cursor: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Return one documented page of public Demo event metadata."""

        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        payload = self._get_json(
            "/events",
            params={"limit": limit, "cursor": cursor, "status": status},
        )
        _validate_events_payload(payload)
        return payload

    def get_market_orderbook(self, ticker: str, *, depth: int | None = None) -> dict[str, Any]:
        """Return the raw fixed-point orderbook for one Kalshi Demo market."""

        clean_ticker = _validate_ticker(ticker)
        if depth is not None and depth < 0:
            msg = "depth must be non-negative"
            raise ValueError(msg)

        payload = self._get_json(
            f"/markets/{quote(clean_ticker, safe='')}/orderbook",
            params={"depth": depth},
        )
        _validate_orderbook_payload(payload, ticker=clean_ticker)
        return payload

    def get_normalized_orderbook(
        self,
        ticker: str,
        *,
        depth: int | None = None,
    ) -> NormalizedOrderBook:
        """Return a canonical YES-side orderbook for one Kalshi Demo market."""

        clean_ticker = _validate_ticker(ticker)
        payload = self.get_market_orderbook(clean_ticker, depth=depth)
        payload_with_ticker = dict(payload)
        payload_with_ticker.setdefault("market_ticker", clean_ticker)
        return normalize_kalshi_orderbook_fp(payload_with_ticker)

    def _get_json(self, path: str, *, params: Mapping[str, object | None]) -> dict[str, Any]:
        clean_params = {key: value for key, value in params.items() if value is not None}
        url = f"{self.base_url}{path}"

        try:
            response = self._client.get(url, params=clean_params)
        except httpx.HTTPError as exc:
            msg = f"Kalshi Demo GET {path} failed before a response was received: {exc}"
            raise KalshiClientError(msg) from exc

        if response.status_code >= 400:
            raise KalshiHTTPError(
                status_code=response.status_code,
                path=path,
                body=_short_body(response.text),
            )

        try:
            payload = response.json()
        except ValueError as exc:
            msg = f"Kalshi Demo GET {path} returned malformed JSON"
            raise KalshiResponseError(msg) from exc

        if not isinstance(payload, dict):
            msg = f"Kalshi Demo GET {path} returned a non-object JSON payload"
            raise KalshiResponseError(msg)

        return payload


def normalize_kalshi_market_metadata(
    market: Mapping[str, object],
) -> dict[str, object]:
    """Normalize REST lifecycle status while preserving the exchange value."""

    normalized = dict(market)
    raw_status = str(market.get("status") or "").strip().lower()
    normalized["raw_status"] = raw_status or None
    normalized["status"] = _MARKET_STATUS_MAP.get(raw_status, raw_status or None)
    return normalized


def _normalize_base_url(base_url: str) -> str:
    clean_url = base_url.rstrip("/")
    if not clean_url:
        msg = "base_url is required"
        raise KalshiConfigurationError(msg)
    return clean_url


def _validate_demo_base_url(base_url: str) -> None:
    if base_url != KALSHI_DEMO_REST_BASE_URL:
        msg = (
            "Kalshi client is restricted to the configured Demo REST base URL: "
            f"{KALSHI_DEMO_REST_BASE_URL}"
        )
        raise KalshiConfigurationError(msg)


def _validate_ticker(ticker: str) -> str:
    clean_ticker = ticker.strip()
    if not clean_ticker:
        msg = "ticker is required"
        raise ValueError(msg)
    return clean_ticker


def _validate_markets_payload(payload: dict[str, Any]) -> None:
    markets = payload.get("markets")
    if not isinstance(markets, list):
        msg = "Kalshi markets response must contain a markets list"
        raise KalshiResponseError(msg)
    cursor = payload.get("cursor")
    if not isinstance(cursor, str):
        msg = "Kalshi markets response must contain a cursor string"
        raise KalshiResponseError(msg)


def _validate_events_payload(payload: dict[str, Any]) -> None:
    events = payload.get("events")
    if not isinstance(events, list):
        raise KalshiResponseError("Kalshi events response must contain an events list")
    cursor = payload.get("cursor")
    if not isinstance(cursor, str):
        raise KalshiResponseError("Kalshi events response must contain a cursor string")


def _object_payload(payload: dict[str, Any], *, key: str, resource: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        msg = f"Kalshi {resource} response must contain a {key} object"
        raise KalshiResponseError(msg)
    return value


def _validate_orderbook_payload(payload: dict[str, Any], *, ticker: str) -> None:
    orderbook = payload.get("orderbook_fp")
    if not isinstance(orderbook, dict):
        msg = "Kalshi orderbook response must contain an orderbook_fp object"
        raise KalshiResponseError(msg)

    yes_dollars = orderbook.get("yes_dollars")
    no_dollars = orderbook.get("no_dollars")
    if not isinstance(yes_dollars, list) or not isinstance(no_dollars, list):
        msg = "Kalshi orderbook_fp must contain yes_dollars and no_dollars lists"
        raise KalshiResponseError(msg)

    if not yes_dollars and not no_dollars:
        msg = f"Kalshi orderbook for {ticker} contains no YES or NO levels"
        raise KalshiEmptyOrderBookError(msg)


def _short_body(body: str, *, max_chars: int = 300) -> str:
    clean_body = body.strip()
    if len(clean_body) <= max_chars:
        return clean_body
    return f"{clean_body[:max_chars]}..."
