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

## Stage plan

- Stage 35: arbitrage roadmap reset. Add this roadmap, mark Stages 11-34
  report-input metadata expansion as maintenance-only, and update handoff/repo
  map/README context. No code behavior change is required.
- Stage 36: complement candidate schema. Add deterministic Decimal-only
  `ComplementArbInput`, `ComplementArbCandidate`, `ComplementArbDecision`,
  `compute_kalshi_complement_candidate`, and
  `compute_canonical_yes_side_cross_candidate`, with offline tests.
- Stage 37: venue fee model scaffold. Make fee assumptions explicit,
  Decimal-only, venue-specific, and conservative. Missing or unknown fee models
  must block `paper_candidate`; no fee schedule is hard-coded without an
  explicit documented assumption.
- Stage 38: offline complement scanner. Scan fixture or snapshot inputs and
  emit JSONL plus Markdown candidate reports without executable order intents.
- Stage 39: live event schema and mocked WebSocket harness. Prepare recorder
  behavior with no actual network connection or credentials.
- Stage 40: Kalshi live read-only recorder. Require explicit
  `--live-readonly-opt-in`, environment allowlists, raw/normalized JSONL, and
  data-quality reporting. No order placement imports.
- Stage 41: Polymarket market-channel recorder. Market channel only; no user
  channel, wallet, signing, or execution.
- Stage 42: order book rebuild and replay consistency. Rebuild order books
  from recorded events, hash book state, and detect gaps/staleness/out-of-order
  inputs.
- Stage 43: taker fill, slippage, and failed-leg simulator. Stress
  FOK/IOC-like two-leg assumptions, partial fills, latency shock, and
  failed-leg reserve.
- Stage 44: paper complement arbitrage engine. Convert candidates to proposed
  paper two-leg orders only, with risk preview and locked candidate hashes.
- Stage 45: paper ledger state machine. Replay paper orders, fills, positions,
  fees, PnL, settlements, and reconciliation mismatch states from zero.
- Stage 46: risk engine v2. Reject stale data, data gaps, missing fees,
  insufficient net edge, exposure/open-order/daily-loss breaches,
  reconciliation mismatch, and active kill switch; still require manual
  approval.
- Stage 47: manual approval workflow. Pending approval files, expiring
  approvals, candidate hash verification, and no reusable approvals.
- Stage 48: monitoring and daily validation report. Report recorder uptime,
  data lag, gap count, candidate counts, rejection reasons, paper/demo
  outcomes, fees, slippage, failed-leg incidents, reconciliation health, and
  kill-switch events.
- Stage 49: Kalshi Demo authenticated connector. Demo-only tiny FOK/IOC orders
  after manual approval, risk approval, reconciliation health, dry-run preview,
  and full audit logging.
- Stage 50: demo reconciliation. Reconcile accepted, rejected, fill, cancel,
  and backfill events; mismatch hard-stops new submissions.
- Stage 51: long-term paper/demo validation framework. Produce deterministic
  local 7/30/90-day rolling reports and keep validation marked incomplete
  until 30+ days of paper trading, 30-90 days of live read-only data, fee/
  slippage review, reconciliation health, and legal/platform review exist.
- Stage 52: private live gate design only. Public repo may document a disabled
  live gate, but must not add production order code.

## Governance

- Read only the current handoff, repo map, stage plan, risk policy, README when
  touched, and files needed for the checkpoint.
- Keep each checkpoint as one coherent delivery unit: spec, implementation,
  tests, docs, handoff, audit note when due, and one PR.
- Stop on unexpected divergence, unfixable validation failure, unclear live
  trading boundary, required credentials, production endpoint request,
  executable strategy output without risk/manual approval, or a missing fee
  model that would otherwise be labeled tradable.
- Use `Decimal` for all prices, quantities, fees, cash, and PnL.
- No floats for money or probability.
- Every candidate is audit or paper metadata, not advice.
- Manual approval remains required until a later private live gate explicitly
  changes that rule.
- Every live or network script must default to disabled/offline.

## Out of scope

Production trading is out of scope. This roadmap does not authorize live
orders, authenticated production endpoints, WebSockets, credentials, wallets,
broker integration, strategy optimization, investment advice, or profitability
claims.
