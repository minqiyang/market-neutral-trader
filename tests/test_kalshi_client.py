import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from edmn_trader.adapters.kalshi import (
    KALSHI_DEMO_REST_BASE_URL,
    KalshiClientError,
    KalshiConfigurationError,
    KalshiDemoMarketDataClient,
    KalshiEmptyOrderBookError,
    KalshiHTTPError,
    KalshiResponseError,
    normalize_kalshi_market_metadata,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_client_defaults_to_kalshi_demo_base_url() -> None:
    client = KalshiDemoMarketDataClient(http_client=httpx.Client(transport=_json_transport({})))

    assert client.base_url == KALSHI_DEMO_REST_BASE_URL


def test_client_rejects_non_demo_base_url() -> None:
    with pytest.raises(KalshiConfigurationError, match="restricted"):
        KalshiDemoMarketDataClient(base_url="https://external-api.kalshi.com/trade-api/v2")


def test_list_markets_uses_read_only_get_markets_endpoint() -> None:
    requests: list[httpx.Request] = []
    payload = _load_fixture("kalshi_markets_response.json")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    response = client.list_markets(limit=25, status="open", mve_filter="exclude")

    assert response == payload
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/trade-api/v2/markets"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].url.params["status"] == "open"
    assert requests[0].url.params["mve_filter"] == "exclude"
    assert "authorization" not in requests[0].headers


def test_list_markets_rejects_unknown_multivariate_filter() -> None:
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=_json_transport({}))
    )

    with pytest.raises(ValueError, match="mve_filter"):
        client.list_markets(mve_filter="unknown")


@pytest.mark.parametrize(
    "identity",
    (
        "",
        " TEST-TICKER",
        "TEST-TICKER ",
        "\tTEST-TICKER",
        "TEST-TICKER\n",
        "\u00a0TEST-TICKER",
        "TEST-TICKER\u2003",
        "TEST-TICKER\u200b",
        "\ufeffTEST-TICKER",
        "TEST-TICKER\x00",
        True,
        1,
        None,
    ),
)
@pytest.mark.parametrize(
    "method_name",
    ("get_market", "get_event", "get_market_orderbook", "get_normalized_orderbook"),
)
def test_exact_resource_requests_reject_noncanonical_identity_before_url_construction(
    identity: object,
    method_name: str,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("invalid identity must fail before a request")

    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(ValueError, match="exact non-whitespace string"):
        getattr(client, method_name)(identity)

    assert requests == []


def test_get_market_uses_read_only_market_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"market": {"ticker": "DEMO-EVENT-MARKET"}})

    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    response = client.get_market("DEMO-EVENT-MARKET")

    assert response["ticker"] == "DEMO-EVENT-MARKET"
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/trade-api/v2/markets/DEMO-EVENT-MARKET"
    assert "authorization" not in requests[0].headers


def test_get_event_uses_read_only_event_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"event": {"event_ticker": "DEMO-EVENT"}})

    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    response = client.get_event("DEMO-EVENT")

    assert response["event_ticker"] == "DEMO-EVENT"
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/trade-api/v2/events/DEMO-EVENT"
    assert "authorization" not in requests[0].headers


def test_list_events_uses_documented_read_only_pagination_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "events": [
                    {"event_ticker": "DEMO-A"},
                    {"event_ticker": "DEMO-B"},
                ],
                "cursor": "",
            },
        )

    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    response = client.list_events(limit=100, cursor="next-page", status="open")

    assert len(response["events"]) == 2
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/trade-api/v2/events"
    assert requests[0].url.params["limit"] == "100"
    assert requests[0].url.params["cursor"] == "next-page"
    assert requests[0].url.params["status"] == "open"
    assert "tickers" not in requests[0].url.params
    assert "authorization" not in requests[0].headers


@pytest.mark.parametrize("resource", ("markets", "events"))
def test_paginated_list_response_requires_an_explicit_cursor(resource: str) -> None:
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(
            transport=_json_transport({resource: []})
        )
    )

    with pytest.raises(KalshiResponseError, match="cursor"):
        if resource == "markets":
            client.list_markets()
        else:
            client.list_events()


def test_get_market_orderbook_uses_read_only_orderbook_endpoint() -> None:
    requests: list[httpx.Request] = []
    payload = _load_fixture("kalshi_orderbook_response.json")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    response = client.get_market_orderbook("DEMO-EVENT-MARKET", depth=10)

    assert response == payload
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/trade-api/v2/markets/DEMO-EVENT-MARKET/orderbook"
    assert requests[0].url.params["depth"] == "10"
    assert "authorization" not in requests[0].headers


@pytest.mark.parametrize("method_name", ("get_market_orderbook", "get_normalized_orderbook"))
@pytest.mark.parametrize(
    ("location", "identity_fields"),
    (
        ("top", {"ticker": "TEST-OTHER-MARKET"}),
        (
            "top",
            {
                "ticker": "TEST-EVENT-MARKET",
                "market_ticker": "TEST-OTHER-MARKET",
            },
        ),
        ("top", {"instrument_id": "TEST-OTHER-MARKET"}),
        ("nested", {"ticker": "TEST-OTHER-MARKET"}),
        ("nested", {"market_ticker": "TEST-EVENT-MARKET\u200b"}),
        ("nested", {"instrument_id": None}),
    ),
)
def test_orderbook_response_rejects_unverified_market_identity(
    method_name: str,
    location: str,
    identity_fields: dict[str, object],
) -> None:
    payload = _load_fixture("kalshi_orderbook_response.json")
    target = payload if location == "top" else payload["orderbook_fp"]
    target.update(identity_fields)
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=_json_transport(payload))
    )

    with pytest.raises(KalshiResponseError, match="identity"):
        getattr(client, method_name)("TEST-EVENT-MARKET")


def test_get_normalized_orderbook_accepts_only_matching_response_identities() -> None:
    payload = _load_fixture("kalshi_orderbook_response.json")
    payload.update(
        {
            "ticker": "TEST-EVENT-MARKET",
            "market_ticker": "TEST-EVENT-MARKET",
            "instrument_id": "TEST-EVENT-MARKET",
        }
    )
    payload["orderbook_fp"].update(
        {
            "ticker": "TEST-EVENT-MARKET",
            "market_ticker": "TEST-EVENT-MARKET",
            "instrument_id": "TEST-EVENT-MARKET",
        }
    )
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=_json_transport(payload))
    )

    book = client.get_normalized_orderbook("TEST-EVENT-MARKET")

    assert book.instrument_id == "TEST-EVENT-MARKET"


def test_get_normalized_orderbook_returns_canonical_yes_book() -> None:
    payload = _load_fixture("kalshi_orderbook_response.json")
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=_json_transport(payload))
    )

    book = client.get_normalized_orderbook("DEMO-EVENT-MARKET")

    assert book.instrument_id == "DEMO-EVENT-MARKET"
    assert book.best_bid_price == Decimal("0.4200")
    assert book.best_ask_price == Decimal("0.4400")
    assert book.spread == Decimal("0.0200")
    assert book.mid == Decimal("0.4300")


def test_http_status_errors_are_explicit() -> None:
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(429, text="rate limit"))
        )
    )

    with pytest.raises(KalshiHTTPError) as exc_info:
        client.list_markets()

    assert exc_info.value.status_code == 429
    assert exc_info.value.path == "/markets"


def test_transport_errors_are_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(KalshiClientError, match="failed before a response"):
        client.list_markets()


def test_malformed_json_is_rejected() -> None:
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=b"not-json")
            )
        )
    )

    with pytest.raises(KalshiResponseError, match="malformed JSON"):
        client.list_markets()


def test_malformed_markets_payload_is_rejected() -> None:
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=_json_transport({"not_markets": []}))
    )

    with pytest.raises(KalshiResponseError, match="markets list"):
        client.list_markets()


def test_malformed_orderbook_payload_is_rejected() -> None:
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=_json_transport({"orderbook_fp": {"yes_dollars": []}}))
    )

    with pytest.raises(KalshiResponseError, match="yes_dollars and no_dollars"):
        client.get_market_orderbook("DEMO-EVENT-MARKET")


def test_empty_orderbook_is_rejected() -> None:
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(
            transport=_json_transport({"orderbook_fp": {"yes_dollars": [], "no_dollars": []}})
        )
    )

    with pytest.raises(KalshiEmptyOrderBookError, match="no YES or NO levels"):
        client.get_market_orderbook("DEMO-EVENT-MARKET")


def test_market_metadata_normalizes_api_lifecycle_status_and_preserves_raw() -> None:
    active = normalize_kalshi_market_metadata({"ticker": "ACTIVE", "status": "active"})
    finalized = normalize_kalshi_market_metadata(
        {"ticker": "FINALIZED", "status": "finalized"}
    )

    assert active["status"] == "open"
    assert active["raw_status"] == "active"
    assert finalized["status"] == "settled"
    assert finalized["raw_status"] == "finalized"


def _json_transport(payload: dict[str, Any]) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))


def _load_fixture(name: str) -> dict[str, Any]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{name} must contain a JSON object"
        raise TypeError(msg)
    return payload
