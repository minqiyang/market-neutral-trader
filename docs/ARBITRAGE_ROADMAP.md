# Complement Arbitrage Roadmap

## Primary target

The near-term trading-research target is same-market YES/NO complement parity
for Kalshi-style binary markets. This is narrower than directional prediction
or broad market making. It asks whether a single market's YES and NO sides are
temporarily inconsistent after explicit fees, slippage, liquidity, stale-book,
and failed-leg assumptions are applied.

For a Kalshi-style book:

```text
yes_ask = 1 - best_no_bid
no_ask = 1 - best_yes_bid
gross_edge = 1 - yes_ask - no_ask
gross_edge = best_yes_bid + best_no_bid - 1
```

In canonical YES-side form, a positive gross edge is equivalent to a crossed or
negative spread condition. The repository treats those states as audit
candidates or data-quality anomalies until later stages prove replay,
simulation, fee, and risk controls. They are not guaranteed profits.

## Why this is not prediction

Complement-parity research does not try to forecast the event outcome. It
checks whether two mutually complementary legs in the same market imply an
inconsistent price relationship. That still does not make the opportunity
risk-free: fees, queue position, latency, partial fills, stale data,
cancellations, market halts, settlement rules, liquidity limits, and platform
rules can erase or reverse the apparent edge.

## Six-layer architecture

1. Live data recorder: read-only market-data capture with timestamps,
   raw-to-normalized traceability, and no trading credentials.
2. Replay/simulator: deterministic offline replay of recorded books, explicit
   fees, slippage, stale-book handling, and liquidity assumptions.
3. Paper ledger/reconciliation: paper-only accounting for candidate decisions,
   hypothetical leg outcomes, assumptions, and reconciliation gaps.
4. Risk/manual approval/kill switch: explicit risk limits, manual review,
   blocked states, and a kill switch before any demo execution path.
5. Demo authenticated execution: separately reviewed demo-only authenticated
   connector work, still gated by risk controls and never enabled by default.
6. Private live gate: a future private review boundary for any live access.
   Production trading remains out of scope for this repository state.

## Report-input maintenance boundary

Stages 11 through 34 expanded local/offline report-input metadata for research
report packs. That work remains valid and useful for documentation hygiene,
but it is now maintenance-only. New product work should not keep adding
report-input kinds unless a later maintenance task explicitly requires it.

## Next stages

- Complement candidate schema: deterministic Decimal-only candidate model for
  same-market YES/NO parity checks.
- Fee model: explicit venue fee assumptions without hard-coding hidden or
  stale schedules.
- Offline scanner: local/replay-only candidate detection over fixture or
  recorded snapshots.
- Live read-only recorder: unauthenticated or explicitly reviewed read-only
  data capture with no order placement.
- Simulator: replay execution assumptions for fees, slippage, queue position,
  partial fills, stale books, and failed-leg reserves.
- Paper ledger: paper-only decision records and reconciliation reports.
- Risk/manual approval: limits, manual review, blocked states, and kill switch.
- Demo connector: separately reviewed authenticated demo execution only.
- Long-term validation: durable replay evidence, limitations, and audit
  reports before any broader claim.

## Out of scope

Production trading is out of scope. This roadmap does not authorize live
orders, authenticated production endpoints, WebSockets, credentials, wallets,
broker integration, strategy optimization, investment advice, or profitability
claims.
