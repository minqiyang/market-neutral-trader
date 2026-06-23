from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from edmn_trader.adapters.sec_edgar import (
    SecEdgarCompanyFactsClient,
    SecEdgarConfigurationError,
    SecEdgarResponseError,
    normalize_sec_company_facts,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_sec_companyfacts_fixture_normalizes_to_research_facts() -> None:
    facts = normalize_sec_company_facts(_load_fixture("sec_companyfacts_aapl.json"))

    assert len(facts) == 2
    assert facts[0].cik == "0000320193"
    assert facts[0].entity_name == "Apple Inc."
    assert facts[0].taxonomy == "us-gaap"
    assert facts[0].concept == "Revenues"
    assert facts[0].unit == "USD"
    assert facts[0].value == Decimal("383285000000")
    assert facts[0].fiscal_year == 2023
    assert facts[0].form == "10-K"


def test_sec_client_uses_public_companyfacts_endpoint_with_user_agent() -> None:
    requests: list[httpx.Request] = []
    payload = _load_fixture("sec_companyfacts_aapl.json")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    client = SecEdgarCompanyFactsClient(
        user_agent="edmn-trader tests contact@example.com",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    facts = client.get_company_facts("320193")

    assert facts[0].concept == "Revenues"
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.host == "data.sec.gov"
    assert requests[0].url.path == "/api/xbrl/companyfacts/CIK0000320193.json"
    assert requests[0].headers["user-agent"] == "edmn-trader tests contact@example.com"
    assert "authorization" not in requests[0].headers


def test_sec_client_rejects_non_sec_base_url() -> None:
    with pytest.raises(SecEdgarConfigurationError, match="SEC EDGAR data base URL"):
        SecEdgarCompanyFactsClient(
            base_url="https://example.com",
            user_agent="edmn-trader tests contact@example.com",
        )


def test_sec_client_requires_explicit_user_agent() -> None:
    with pytest.raises(SecEdgarConfigurationError, match="user_agent is required"):
        SecEdgarCompanyFactsClient(user_agent="")


def test_sec_companyfacts_rejects_malformed_value() -> None:
    payload = _load_fixture("sec_companyfacts_aapl.json")
    payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["val"] = "not-decimal"

    with pytest.raises(SecEdgarResponseError, match="value"):
        normalize_sec_company_facts(payload)


def _load_fixture(name: str) -> dict[str, Any]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{name} must contain a JSON object"
        raise TypeError(msg)
    return payload
