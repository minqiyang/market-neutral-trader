# Stage 8 Polymarket US Readiness Note

## Outcome

Stage 8 is ready only as a fixture-first, public-market-data implementation for
Polymarket US. Do not implement trading, authenticated requests, wallet flows,
WebSocket streaming, production execution, or use of the international
Polymarket endpoint.

## Current source check

- Polymarket US describes itself as a CFTC-regulated Designated Contract Market
  and links developer resources for institutional participants:
  <https://www.polymarketexchange.com/>.
- Polymarket US documentation separates an authenticated trading API from a
  public API and says the public API is for browsing markets, events, order
  books, and search without an API key:
  <https://docs.polymarket.us/api-reference/introduction>.
- International Polymarket market-data docs describe unauthenticated public
  endpoints, but those are not the Stage 8 target:
  <https://docs.polymarket.com/market-data/overview>.
- Polymarket's geographic restriction help page lists the United States as
  restricted for the international platform and prohibits VPN bypass:
  <https://help.polymarket.com/en/articles/13364163-geographic-restrictions>.
- The CFTC's 2022 Polymarket order is still relevant context for why this stage
  must stay market-data only and avoid unregistered/off-exchange trading paths:
  <https://www.cftc.gov/PressRoom/PressReleases/8478-22>.

## Allowed next implementation slice

- Add a Polymarket US market-data adapter under
  `src/edmn_trader/adapters/polymarket_us`.
- Use committed local fixtures for tests.
- Parse only public market/orderbook-style data into exchange-agnostic core or
  replay structures.
- Keep any HTTP client unauthenticated and restricted to the documented
  Polymarket US public API base URL.
- Keep live HTTP smoke optional and out of scope until rate limits, terms, and
  endpoint stability are reviewed again.

## Stop conditions

- Any need for API keys, wallets, private account data, authenticated endpoints,
  trading endpoints, WebSockets, or region bypass.
- Any uncertainty about whether a data source is Polymarket US public market
  data rather than international Polymarket trading infrastructure.
- Any change that would create executable orders, wallet integration, or
  production readiness claims.
