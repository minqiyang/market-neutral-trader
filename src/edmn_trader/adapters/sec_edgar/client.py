"""Read-only SEC EDGAR public fundamentals client."""

from __future__ import annotations

from typing import Any, Self

import httpx

from edmn_trader.adapters.sec_edgar.companyfacts import (
    SecEdgarResponseError,
    normalize_sec_company_facts,
)
from edmn_trader.research.equities import EquityFundamentalFact

SEC_EDGAR_DATA_BASE_URL = "https://data.sec.gov"


class SecEdgarClientError(Exception):
    """Base class for SEC EDGAR adapter client errors."""


class SecEdgarConfigurationError(SecEdgarClientError):
    """Raised when client configuration leaves the public fundamentals boundary."""


class SecEdgarHTTPError(SecEdgarClientError):
    """Raised for non-success HTTP status codes from SEC EDGAR."""

    def __init__(self, *, status_code: int, path: str, body: str) -> None:
        self.status_code = status_code
        self.path = path
        self.body = body
        super().__init__(f"SEC EDGAR GET {path} returned HTTP {status_code}: {body}")


class SecEdgarCompanyFactsClient:
    """Guarded read-only client for SEC EDGAR companyfacts endpoints."""

    def __init__(
        self,
        *,
        user_agent: str,
        base_url: str = SEC_EDGAR_DATA_BASE_URL,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        _validate_base_url(self.base_url)
        clean_user_agent = _validate_user_agent(user_agent)

        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._user_agent = clean_user_agent

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client when this instance owns it."""

        if self._owns_client:
            self._client.close()

    def get_company_facts(self, cik: str) -> tuple[EquityFundamentalFact, ...]:
        """Return normalized public SEC companyfacts for one CIK."""

        payload = self._get_json(f"/api/xbrl/companyfacts/CIK{_format_cik(cik)}.json")
        return normalize_sec_company_facts(payload)

    def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"

        try:
            response = self._client.get(url, headers={"User-Agent": self._user_agent})
        except httpx.HTTPError as exc:
            msg = f"SEC EDGAR GET {path} failed before a response was received: {exc}"
            raise SecEdgarClientError(msg) from exc

        if response.status_code >= 400:
            raise SecEdgarHTTPError(
                status_code=response.status_code,
                path=path,
                body=_short_body(response.text),
            )

        try:
            payload = response.json()
        except ValueError as exc:
            msg = f"SEC EDGAR GET {path} returned malformed JSON"
            raise SecEdgarResponseError(msg) from exc

        if not isinstance(payload, dict):
            msg = f"SEC EDGAR GET {path} returned a non-object JSON payload"
            raise SecEdgarResponseError(msg)
        return payload


def _normalize_base_url(base_url: str) -> str:
    clean_url = base_url.rstrip("/")
    if not clean_url:
        msg = "base_url is required"
        raise SecEdgarConfigurationError(msg)
    return clean_url


def _validate_base_url(base_url: str) -> None:
    if base_url != SEC_EDGAR_DATA_BASE_URL:
        msg = f"SEC EDGAR client is restricted to the SEC EDGAR data base URL: {base_url}"
        raise SecEdgarConfigurationError(msg)


def _validate_user_agent(user_agent: str) -> str:
    clean_user_agent = user_agent.strip()
    if not clean_user_agent:
        msg = "user_agent is required for SEC EDGAR fair-access identification"
        raise SecEdgarConfigurationError(msg)
    return clean_user_agent


def _format_cik(cik: str) -> str:
    try:
        return f"{int(cik):010d}"
    except ValueError as exc:
        msg = "cik must be integer-compatible"
        raise ValueError(msg) from exc


def _short_body(body: str, *, max_chars: int = 300) -> str:
    clean_body = body.strip()
    if len(clean_body) <= max_chars:
        return clean_body
    return f"{clean_body[:max_chars]}..."
