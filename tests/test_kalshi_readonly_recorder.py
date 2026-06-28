from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from edmn_trader.adapters.kalshi import (
    KalshiConfigurationError,
    KalshiDemoMarketDataClient,
    KalshiReadOnlyOptInRequired,
    KalshiReadOnlyRecorderConfig,
    record_kalshi_readonly_orderbook,
)
from edmn_trader.data import read_live_events, read_snapshots

FIXTURES = Path(__file__).parent / "fixtures"


def test_kalshi_readonly_recorder_requires_opt_in_before_http(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: requests.append(request) or httpx.Response(200, json={})
            )
        )
    )

    with pytest.raises(KalshiReadOnlyOptInRequired, match="--live-readonly-opt-in"):
        record_kalshi_readonly_orderbook(
            _config(tmp_path, live_readonly_opt_in=False),
            client=client,
        )

    assert requests == []


def test_kalshi_readonly_recorder_rejects_production_boundary(tmp_path: Path) -> None:
    with pytest.raises(KalshiConfigurationError, match="Demo"):
        _config(
            tmp_path,
            live_readonly_opt_in=True,
            base_url="https://external-api.kalshi.com/trade-api/v2",
        )

    with pytest.raises(KalshiConfigurationError, match="environment"):
        _config(tmp_path, live_readonly_opt_in=True, environment="production")


def test_kalshi_readonly_recorder_writes_raw_event_and_snapshot(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    payload = _load_fixture("kalshi_orderbook_response.json")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    client = KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    result = record_kalshi_readonly_orderbook(
        _config(tmp_path, live_readonly_opt_in=True),
        client=client,
    )

    assert result.events_written == 1
    assert result.snapshots_written == 1
    assert result.data_quality_flags == ()
    assert requests[0].method == "GET"
    assert "authorization" not in requests[0].headers

    [event] = read_live_events(tmp_path / "events.jsonl")
    assert event.source_type == "kalshi_demo_rest"
    assert event.payload["market_ticker"] == "DEMO-EVENT-MARKET"
    assert event.to_record().get("execution_mode") is None
    assert event.to_record().get("order_intent") is None

    [snapshot] = read_snapshots(tmp_path / "snapshots.jsonl")
    assert snapshot.exchange == "kalshi_demo"
    assert snapshot.ticker == "DEMO-EVENT-MARKET"
    assert snapshot.normalized_orderbook.best_bid_price is not None
    assert snapshot.raw_payload is not None
    assert snapshot.raw_payload["market_ticker"] == "DEMO-EVENT-MARKET"


def _config(
    tmp_path: Path,
    *,
    live_readonly_opt_in: bool,
    base_url: str | None = None,
    environment: str = "demo",
) -> KalshiReadOnlyRecorderConfig:
    kwargs: dict[str, Any] = {}
    if base_url is not None:
        kwargs["base_url"] = base_url
    return KalshiReadOnlyRecorderConfig(
        ticker="DEMO-EVENT-MARKET",
        events_output_path=tmp_path / "events.jsonl",
        snapshots_output_path=tmp_path / "snapshots.jsonl",
        live_readonly_opt_in=live_readonly_opt_in,
        environment=environment,
        **kwargs,
    )


def _load_fixture(name: str) -> dict[str, Any]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{name} must contain an object"
        raise TypeError(msg)
    return payload
