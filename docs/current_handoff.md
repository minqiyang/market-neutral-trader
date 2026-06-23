# Current Handoff

## Current project state

The repository contains a Python 3.12 package for a demo-first,
risk-controlled event-driven prediction-market research platform. Current
implemented code includes exchange-agnostic core models, Kalshi-style
fixed-point orderbook normalization, a guarded read-only Kalshi Demo REST
client, local fixtures, mocked HTTP tests, Decimal-safe JSONL snapshot storage,
deterministic offline replay metrics, a fair-value/quote-engine dry run,
risk-gated fake-adapter demo execution smoke infrastructure, and a finite
Stage 6 market-maker replay workflow.

## Last completed stage

Stage 6: Inventory-aware demo market maker in dry-run/demo only.

## Stage plan status

`docs/STAGE_PLAN.md` contains a completed-stage record ledger for Stages 0,
1, 1.5, 2, 3, 4, 5, and 6. The ledger records purpose, known commit hashes,
files/modules added, validation commands, status, next-stage boundary, and
safety status for each completed stage.

`docs/STAGE_PLAN.md` now contains the full Stage 3 specification: snapshot
schema requirements, Decimal-safe JSONL recorder requirements, deterministic
replay behavior, fixture recording and replay scripts, offline tests,
out-of-scope boundaries, validation commands, and the Stage 4 boundary.

`docs/STAGE_PLAN.md` also contains the full Stage 4 specification: fair-value
baseline requirements, quote generation, inventory-aware skew, spread and
tick/price boundary handling, dry-run-only intent output, replay dry-run script,
offline deterministic tests, validation commands, non-goals, and the Stage 5
boundary.

`docs/STAGE_PLAN.md` now contains the full Stage 5 specification: risk checks,
blocked-path tests, execution log format, demo-only smoke constraints,
offline/fake-adapter test requirements, validation commands, non-goals, and the
Stage 6 boundary.

`docs/STAGE_PLAN.md` now contains the full Stage 6 specification: finite
replay-driven dry-run/demo workflow behavior, inventory-aware quoting
requirements, Stage 5 risk-gate reuse, structured JSONL logging and run summary
requirements, explicit quote lifecycle handling, max-position/max-open-orders/
max-notional/max-loss/kill-switch controls, offline tests, validation commands,
explicit non-goals, and the Stage 7 boundary.

Stage 6 is now implemented as a finite replay workflow. It remains dry-run by
default, uses only fake-adapter demo submissions after explicit opt-in and risk
approval, and does not infer fills, PnL, profitability, or production readiness.

## Important files

- `AGENTS.md`: repo rules and first-read instructions.
- `PROJECT_SPEC.md`: stable project and module specification.
- `CHANGELOG.md`: external-facing milestone log.
- `docs/repo_map.md`: context-budget map for targeted reads.
- `docs/codex_long_running_controller.md`: staged continuation rules.
- `docs/STAGE_PLAN.md`: staged roadmap and non-goals.
- `docs/engineering_log.md`: narrative engineering record.
- `src/edmn_trader/core/models.py`: exchange-agnostic core models.
- `src/edmn_trader/adapters/kalshi/client.py`: guarded read-only Kalshi Demo
  REST client for markets and orderbooks.
- `src/edmn_trader/adapters/kalshi/orderbook.py`: Kalshi orderbook normalizer.
- `src/edmn_trader/data/snapshots.py`: snapshot model and snapshot JSONL
  persistence helpers.
- `src/edmn_trader/data/jsonl.py`: Decimal-safe JSONL helpers.
- `src/edmn_trader/data/replay.py`: deterministic replay session and metrics.
- `src/edmn_trader/research/fair_value.py`: deterministic baseline fair-value
  model.
- `src/edmn_trader/research/quotes.py`: non-executable dry-run quote engine and
  quote intents.
- `src/edmn_trader/execution/demo.py`: Stage 5 risk decisions, fake adapter,
  execution boundary, and JSONL audit logging.
- `scripts/02_record_fixture_snapshots.py`: converts local fixtures to JSONL
  snapshots.
- `scripts/03_replay_snapshots.py`: replays JSONL snapshots and prints a
  concise metrics table.
- `scripts/04_quote_replay_dry_run.py`: replays JSONL snapshots through the
  dry-run quote engine and prints fair value and quote metrics.
- `scripts/05_demo_execution_smoke.py`: runs a local fake-adapter Stage 5
  smoke check with explicit demo opt-in support.
- `src/edmn_trader/scripts/market_maker_replay.py`: importable Stage 6 finite
  replay workflow for quote lifecycle, risk gates, logs, and run summaries.
- `scripts/06_market_maker_replay.py`: root wrapper for Stage 6 replay.
- `tests/test_kalshi_client.py`: mocked HTTP coverage for the Stage 2 client.
- `tests/test_kalshi_orderbook.py`: normalizer coverage.
- `tests/test_snapshots_jsonl.py`: snapshot/JSONL coverage.
- `tests/test_replay_snapshots.py`: replay and fixture-conversion coverage.
- `tests/test_quote_engine.py`: fair-value and dry-run quote-engine coverage.
- `tests/test_quote_replay_dry_run.py`: replay-based quote script coverage.
- `tests/test_demo_execution.py`: Stage 5 risk gate, blocked path, fake
  adapter, and audit log coverage.
- `tests/test_demo_execution_smoke.py`: Stage 5 smoke script coverage.
- `tests/test_market_maker_replay.py`: Stage 6 dry-run/demo, lifecycle,
  run-control, adapter-error, and script-summary coverage.

## Commands that currently pass

```bash
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage3_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage3_snapshots.jsonl
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage4_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage4_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage4_snapshots.jsonl
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage5_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage5_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage5_snapshots.jsonl
python scripts/05_demo_execution_smoke.py --log-output /tmp/edmn_stage5_execution_smoke.jsonl
python scripts/05_demo_execution_smoke.py --demo-opt-in --log-output /tmp/edmn_stage5_execution_smoke_approved.jsonl
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage6_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage6_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage6_snapshots.jsonl
python scripts/05_demo_execution_smoke.py --log-output /tmp/edmn_stage6_execution_smoke.jsonl
python scripts/05_demo_execution_smoke.py --demo-opt-in --log-output /tmp/edmn_stage6_execution_smoke_approved.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage6_snapshots.jsonl --log-output /tmp/edmn_stage6_market_maker.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage6_snapshots.jsonl --demo-opt-in --log-output /tmp/edmn_stage6_market_maker_demo.jsonl
```

Optional environment validation:

```bash
python -m pip install -e ".[dev]"
```

## Known issues

- GitHub remote `origin` is configured for
  `https://github.com/minqiyang/market-neutral-trading-research.git`; do not
  push unless the user explicitly asks or the active workflow requires it.
- PR #1 merged Stage 5 into `main` at
  `6cd1d536fa41e721a998f23eab19d7129938c3da`.
- PR #2 merged the Stage 6 plan clarification into `main` at
  `a322310c7c9d1ab82c0307a35b8db79e704b9274`.
- Local `main` was fast-forwarded to `origin/main` after the PR #1 merge, and
  post-merge validation passed before this handoff update.
- A prior handoff-only update was pushed directly to `main` and GitHub reported
  branch-rule bypass warnings. Future staged work should default to branch +
  PR flow unless every owner-direct fast-path condition in
  `docs/codex_long_running_controller.md` is satisfied.
- `.github/workflows/ci.yml` exists, and the latest observed GitHub Actions CI
  run on `main` completed successfully. CI now runs `Validate` for pushes to
  `main`, pull requests to `main`, and pushes to `codex/**` branches.
- GitHub branch protection is enabled on `main` and requires the `Validate`
  status check.
- The Kalshi Demo client is tested with mocked HTTP and local fixtures; no live
  network smoke script exists.
- Quote dry-runs emit non-executable intents. Stage 6 can convert those
  boundaries into fake-adapter demo execution requests only after explicit
  opt-in and Stage 5 risk approval; no fill simulation, WebSocket ingestion,
  production trading path, or live market-making loop exists.

## PR workflow policy

`docs/codex_long_running_controller.md` now contains the publish policy for
future staged work. Default to branch + PR. An owner-direct fast path may skip
PR creation only when `gh` is authenticated as `minqiyang`, `origin` is
`minqiyang/market-neutral-trading-research`, work starts from clean synced
`origin/main`, work occurs on a `codex/` branch, local validation and branch
`Validate` pass, risk is low or medium, the change avoids all listed safety and
compliance hazards, no PR/divergence conflict exists, and the final update to
`main` is a normal push with no force, admin override, or branch-protection
bypass command. If any condition is false, create a PR or stop for human
review. High-risk or unclear work always stops for human review.

GitHub auto-merge may still be enabled only for clearly low-risk small PRs that
are narrow, locally validated, protected by required checks/reviews, and free of
credentials, production endpoints, order placement, WebSocket work, live
market-making loops, strategy optimization, large generated files, dependency
surprises, or compliance ambiguity.

`docs/codex_long_running_controller.md` also contains the compact
skill-orchestration policy for future staged work: use long-session governance
and token-budget rules on every checkpoint, read only the current handoff, repo
map, controller, active stage section, and project Skill first, treat optional
skills as accelerators rather than blockers, reserve Ponytail, TDD, grill-me,
and handoff for the narrow cases named there, and keep skill use bounded unless
a stop gate is triggered.

## Safety boundaries

- Do not add credentials or secrets.
- Do not implement production order placement.
- Do not implement WebSocket ingestion.
- Do not add fill simulation before a dedicated simulation stage.
- Do not enable live or production trading.
- Do not make profitability claims.
- Keep Kalshi-specific code under `src/edmn_trader/adapters/kalshi`.

## Next recommended stage

Stage 7: PnL attribution and research reporting. Start only after reconfirming
clean synced `main`, CI, branch protection, required `Validate` status, local
validation, and whether the owner-direct fast path or PR path applies.

## Exact next prompt suggestion

Use Codex Long Session Governance. Start Stage 7 planning from only the Stage 7
section of `docs/STAGE_PLAN.md`; if the Stage 7 spec is incomplete, create a
docs-only clarification checkpoint and stop. Do not add authenticated/live
trading, WebSocket ingestion, production endpoints, or profitability claims.

## Last updated timestamp

2026-06-22 22:13:11 -07:00
