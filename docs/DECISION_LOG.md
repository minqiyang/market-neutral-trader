# Decision Log

## 2026-06-10: Use demo-first architecture

Decision: build the project around demo, paper, simulation, and research
workflows before any execution work.

Rationale: trading-system quality depends on safe boundaries, reproducibility,
and risk checks before market access.

## 2026-06-10: Reject guaranteed-profit framing

Decision: state clearly that the project is not a guaranteed-profit trading bot.

Rationale: event-driven trading faces fees, adverse selection, liquidity,
latency, and compliance constraints. The repository should demonstrate
engineering quality, not promise outcomes.

## 2026-06-10: Start with Kalshi-style binary markets

Decision: use Kalshi-style binary prediction markets as the first target.

Rationale: the market structure creates a concrete and explainable orderbook
normalization problem while keeping the first external target in a demo context.

## 2026-06-10: Normalize YES/NO orderbooks before strategy work

Decision: implement canonical YES-side orderbook normalization before fair
value, quote generation, simulation, or strategy work.

Rationale: downstream trading logic should consume one trusted data shape rather
than duplicate venue-specific assumptions.

## 2026-06-10: Keep exchange-specific code in adapters

Decision: keep Kalshi-specific logic under `src/edmn_trader/adapters/kalshi`.

Rationale: the core workflow should stay portable to future prediction-market
and equities research adapters.

## 2026-06-10: Use Decimal for prices and quantities

Decision: use `Decimal` for prices, quantities, cash, fees, and PnL.

Rationale: financial math should avoid binary floating-point surprises and
preserve fixture precision.

## 2026-06-10: Disable live trading by default

Decision: expose `LIVE_DISABLED` as the only live-related execution mode.

Rationale: future execution work must be explicitly staged, risk-gated, logged,
and tested before it can act.

## 2026-06-11: Add long-running handoff files before API expansion

Decision: add project memory, handoff, repo map, stage plan, and controller docs
before implementing the Kalshi Demo REST client.

Rationale: future Codex sessions need compact, durable context and stop gates
before the project touches networked market-data workflows.

## 2026-06-11: Use injectable httpx client for read-only Kalshi Demo REST

Decision: implement Stage 2 with `httpx.Client` and injectable transport,
restricted to the configured Kalshi Demo REST base URL.

Rationale: injectable transport keeps tests deterministic and network-free while
still exercising realistic HTTP request construction, status handling, JSON
decoding, and response validation.

## 2026-06-11: Store offline snapshots as Decimal-safe JSONL

Decision: use append-friendly JSONL snapshot files with Decimal values
serialized as strings and strict replay ordered by observed timestamp.

Rationale: future research stages need deterministic, inspectable, and
replayable market-data inputs that preserve price and quantity precision without
depending on live API state.

## 2026-06-11: Keep quote engine output non-executable

Decision: implement Stage 4 quote output as `dry_run_only` inspection objects
instead of reusing executable order-intent paths.

Rationale: fair-value and quote research should be testable from replayed local
data before any risk-gated execution smoke test exists.

## 2026-06-22: Limit Stage 8 to Polymarket US public market data

Decision: target only Polymarket US public market-data sources for Stage 8 and
avoid international Polymarket endpoints, trading endpoints, wallets,
authentication, WebSockets, and region bypass.

Rationale: Polymarket US documents a public market-data API and regulated U.S.
exchange context, while international Polymarket materials include geographic
restrictions for the United States. A fixture-first, read-only adapter keeps
the checkpoint useful without crossing compliance or execution boundaries.

## 2026-06-22: Limit Stage 9 to SEC EDGAR public fundamentals

Decision: target SEC EDGAR public JSON fundamentals for the first U.S. equities
research adapter and avoid broker APIs, live quote feeds, paid-vendor market
data, account data, credentials, and order paths.

Rationale: SEC EDGAR provides public unauthenticated filing and XBRL data with
published fair-access limits. That keeps Stage 9 useful for equities research
without crossing trading, proprietary market-data, or credential boundaries.

## 2026-06-28: Prioritize same-market complement parity research

Decision: redirect active product work from continued report-input metadata
expansion to same-market YES/NO complement parity research, with report-input
Stages 11 through 34 preserved as maintenance-only infrastructure.

Rationale: complement parity is a narrower and more concrete first
trading-research target than directional prediction or broad market making. It
can start with deterministic offline candidate metadata while keeping fees,
slippage, stale data, failed legs, manual review, and production trading
boundaries explicit.
