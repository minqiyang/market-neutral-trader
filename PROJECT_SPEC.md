# Project Specification

## Mission

`event-driven-market-neutral-trader` is a demo-first, risk-controlled,
event-driven market-neutral trading research platform. It is designed to
demonstrate professional trading-system engineering, simulation discipline,
execution safety, and staged workflow control.

The project is not a guaranteed-profit trading bot.

## First market

The first market type is Kalshi-style binary prediction markets. These markets
require venue-specific orderbook normalization because YES bids and NO bids must
be converted into canonical YES-side bid/ask structures before research,
simulation, quoting, or risk checks can use them safely.

## Long-term expansion

The architecture should later support:

- Polymarket US market-data research adapters, if compliant and available.
- U.S. equities research adapters for paper or research workflows.
- Market-neutral simulation, quote generation, risk controls, and observability
  without changing the core workflow for each venue.

## Non-goals

- No guaranteed-profit claims.
- No production trading by default.
- No bypassing platform rules, KYC, regional restrictions, compliance
  boundaries, or rate limits.
- No manipulative trading behavior.
- No order placement until a later, separately reviewed stage with tests and a
  risk engine.
- No live equities execution.
- No credentials, private keys, tokens, wallet keys, or API keys in the repo.

## Core modules

- `core`: exchange-agnostic models and primitives such as instruments,
  normalized orderbooks, quotes, order intents, positions, risk limits, and risk
  decisions.
- `adapters`: venue-specific parsing and integration code. Kalshi-specific code
  belongs under `src/edmn_trader/adapters/kalshi`.
- `research`: future analysis notebooks or scripts that consume normalized data
  without depending on one venue.
- `strategy`: future dry-run strategy logic that emits candidate quotes or order
  intents, never direct execution actions.
- `execution`: future demo or paper execution workflow, gated by risk checks and
  logging. Production live trading is not enabled.
- `risk`: future pre-trade and portfolio-level risk checks.
- `data`: future local fixture, replay, recording, and storage utilities.
- `observability`: future structured logs, metrics, run summaries, and audit
  trails.

## Current stage

Stage 4 added a fair-value and quote engine dry-run. It consumes normalized or
replayed books, estimates deterministic baseline fair value, applies bounded
inventory-aware quote skew, and emits non-executable dry-run quote intents.

## Next stage

Stage 5 should add explicit risk checks before any demo execution smoke test.
It must keep production trading disabled, cover blocked paths with tests, and
avoid broad strategy deployment.

## Acceptance standards

- Keep changes small and reviewable.
- Read `AGENTS.md`, `docs/current_handoff.md`, and `docs/repo_map.md` before
  broad exploration.
- Preserve the adapter/core boundary.
- Use `Decimal` for prices, quantities, cash, fees, and PnL.
- Add deterministic tests for functional changes.
- Run `pytest`, `ruff check .`, and relevant fixture scripts before handoff.
- Update `docs/current_handoff.md`, `docs/engineering_log.md`, and
  `CHANGELOG.md` after each stage-sized change.
- Stop at the requested stage boundary.
