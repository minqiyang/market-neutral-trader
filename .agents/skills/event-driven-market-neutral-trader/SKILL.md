---
name: event-driven-market-neutral-trader
description: Use for implementation, review, or documentation work in the event-driven-market-neutral-trader repo, especially core trading models, prediction-market orderbook normalization, risk policy, and demo-first execution safety.
---

# Event Driven Market Neutral Trader

## When to use

Use this Skill for changes in this repository that affect project scaffolding, trading-domain models, adapters, risk policy, simulations, execution workflow, tests, or public-facing documentation.

## Desired outcome

Produce small, reviewable changes that support a demo-first, risk-controlled trading research platform for event-driven prediction markets without enabling production trading.

## Success criteria

- No profitability guarantees or claims.
- No credentials, private keys, API keys, tokens, or secrets.
- No authenticated API calls or live order placement unless explicitly requested in a later reviewed stage.
- Exchange-specific logic stays under `src/edmn_trader/adapters`.
- Core models stay exchange-agnostic.
- Prices, quantities, cash, fees, and PnL use `Decimal`.
- Functional changes include deterministic tests.
- `pytest` and `ruff check .` pass before handoff when the local environment supports them.

## Inputs and context to collect

- Read `AGENTS.md` first.
- Identify the requested stage and stop at the requested boundary.
- Check existing package layout and tests before adding new abstractions.
- Confirm whether the task permits live API use; default to local fixtures only.

## Workflow guidance

Start with the safety boundary, then implement the narrowest foundation needed for the requested stage. Keep adapters thin and explicit, normalize exchange-specific inputs into canonical core objects, and prefer deterministic fixtures over external services.

Use `docs/codex_long_running_controller.md` for long-session governance,
token-budget discipline, publish rules, and optional skill orchestration. Treat
this project Skill as the required repository-specific skill for staged work;
use optional Matt Pocock, TDD, Ponytail, and handoff/compaction skills only in
the cases named by the controller, and fall back to the equivalent checklist if
an optional skill is unavailable or renamed.

In continuous autopilot, compact governance audits after every three completed
checkpoints are mandatory but non-terminal when they pass. After a passing audit
publish, wait for `main` `Validate`, sync local `main`, verify a clean state,
read the updated handoff, reset the checkpoint counter, and continue.

For Kalshi-style binary orderbooks, normalize YES-side books from local data by treating YES bids as canonical bids and NO bids as implied YES asks using `1 - no_price`.

For staged project work, read `docs/current_handoff.md` and `docs/repo_map.md` before broad exploration. After a stage-sized change, update `docs/current_handoff.md`, `docs/engineering_log.md`, and `CHANGELOG.md` with concise durable context.

## Known pitfalls

- Kalshi-style binary orderbooks expose YES bids and NO bids, not traditional YES asks.
- A V2 `side` value of `bid` means buy YES, while `ask` means sell YES.
- Stage 0 and the first Stage 1 slice must not place orders, open WebSockets, or call live APIs in tests.

## Tools and deterministic operations

- Install locally for validation: `python -m pip install -e ".[dev]"`.
- Run tests: `pytest`.
- Run lint: `ruff check .`.
- Use local JSON fixtures for orderbook normalization tests and replay scripts.
- The Stage 1 fixture replay path is `scripts/01_replay_orderbook_fixture.py`,
  backed by `tests/fixtures/kalshi_orderbook_fp_basic.json` and the importable
  entry point `edmn_trader.scripts.replay_orderbook_fixture:main`.
- The Stage 2 read-only client lives at
  `src/edmn_trader/adapters/kalshi/client.py`; tests use `httpx.MockTransport`
  in `tests/test_kalshi_client.py` and local fixtures under `tests/fixtures/`.
- The Stage 3 offline data layer lives under `src/edmn_trader/data/`; scripts
  are `scripts/02_record_fixture_snapshots.py` and
  `scripts/03_replay_snapshots.py`. Replay is strict by default and sorts only
  when `--no-strict` is explicitly requested.
- The Stage 4 dry-run quote layer lives under `src/edmn_trader/research/`;
  `scripts/04_quote_replay_dry_run.py` must remain local/replay-only and must
  emit non-executable `dry_run_only` quote intents.
- The Stage 5 execution smoke layer lives under `src/edmn_trader/execution/`;
  `scripts/05_demo_execution_smoke.py` must remain fake-adapter/local by
  default, require explicit `--demo-opt-in` for approved fake execution, and log
  every attempt as JSONL.
- The Stage 6 finite market-maker replay lives at
  `src/edmn_trader/scripts/market_maker_replay.py`; the root script is
  `scripts/06_market_maker_replay.py`. It must remain finite, dry-run by
  default, fake-adapter only after explicit `--demo-opt-in`, and must not infer
  fills, PnL, profitability, or production readiness.
- The Stage 7 offline research report lives at
  `src/edmn_trader/scripts/research_report.py`; the root script is
  `scripts/07_research_report.py`. It consumes Stage 6 logs and optional
  explicit local fill fixtures only, rejects secret-like fill fields, and must
  not infer fills from adapter submissions or claim profitability.
- The Stage 8 Polymarket US adapter lives under
  `src/edmn_trader/adapters/polymarket_us/`. It must stay public-market-data
  only, fixture-tested by default, restricted to the Polymarket US public base
  URL, and free of international endpoints, auth, wallets, WebSockets, trading,
  execution paths, and profitability claims.
- The Stage 9 SEC EDGAR adapter lives under
  `src/edmn_trader/adapters/sec_edgar/`, with normalized equities facts in
  `src/edmn_trader/research/equities.py`. It must stay public-fundamentals
  only, fixture-tested by default, restricted to `https://data.sec.gov`, and
  free of broker APIs, credentials, account data, live quote feeds, paid-vendor
  data, orders, strategy optimization, execution paths, and profitability
  claims.
- The Stage 10 paper report pack lives at
  `src/edmn_trader/scripts/paper_report_pack.py`; the root script is
  `scripts/10_paper_report_pack.py`. It must stay local/offline, reuse Stage 7
  attribution and Stage 9 SEC fixtures, separate observed metrics, supplied
  assumptions, fundamentals, and limitations, and avoid rankings, allocation
  advice, execution, live feeds, and profitability claims.
- Stage 11 extends that same report pack with a local source inventory section
  only; it must continue to use local files and fixtures, label missing inputs
  as not supplied, and avoid new data adapters or executable advice.

## Verification

Check that the requested stage boundary was not exceeded, tests cover normal and edge cases, and docs clearly describe demo-first scope, risk controls, live-trading restrictions, and extension plans.

For the Stage 0 and Stage 1 foundation, the verified local command set is:
`python -m pip install -e ".[dev]"`, `pytest`, `ruff check .`, and
`python scripts/01_replay_orderbook_fixture.py`.

## Update policy

After each use, update this Skill only with reusable lessons verified in that run. Keep updates concise and specific to this repository.
