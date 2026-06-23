# Stage 9 U.S. Equities Readiness Note

## Outcome

Stage 9 is ready only as a fixture-first SEC EDGAR public fundamentals adapter.
Do not implement broker integration, live equities orders, real-time quote
feeds, paid-vendor market data, credentials, portfolio/account data, or trading
signals.

## Current source check

- SEC EDGAR APIs provide JSON-formatted filing and XBRL data through
  `data.sec.gov` and do not require authentication or API keys:
  <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>.
- SEC EDGAR fair-access guidance limits automated access and currently lists a
  maximum request rate of 10 requests per second:
  <https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>.
- `data.sec.gov` states that automated access must comply with SEC.gov privacy
  and security policy:
  <https://data.sec.gov/>.

## Implemented slice

- Added an SEC EDGAR equities fundamentals adapter under
  `src/edmn_trader/adapters/sec_edgar`.
- Added committed local fixtures and offline tests.
- Parsed public companyfacts JSON into `EquityFundamentalFact`.
- Kept the HTTP client unauthenticated and restricted to `https://data.sec.gov`.
- Required an explicit identifying User-Agent for the HTTP client.
- Deferred live HTTP smoke until fair-access behavior, caching, and request
  pacing are reviewed.

## Stop conditions

- Any need for broker credentials, API keys, account data, portfolio data,
  private holdings, live quote feeds, exchange proprietary data, paid-vendor
  feeds, or order placement.
- Any uncertainty about data redistribution rights or whether a source is public
  SEC EDGAR data.
- Any change that creates execution, trading-signal, strategy-optimization, or
  production-readiness claims.
