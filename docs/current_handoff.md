# Current Handoff

## Current project state

The repository contains a Python 3.12 package for a demo-first,
risk-controlled event-driven prediction-market research platform. Current
implemented code includes exchange-agnostic core models, Kalshi-style
fixed-point orderbook normalization, a guarded read-only Kalshi Demo REST
client, local fixtures, mocked HTTP tests, Decimal-safe JSONL snapshot storage,
deterministic offline replay metrics, a fair-value/quote-engine dry run, and
risk-gated fake-adapter demo execution smoke infrastructure.

## Last completed stage

Stage 5: Risk-gated demo execution smoke test.

## Stage plan status

`docs/STAGE_PLAN.md` contains a completed-stage record ledger for Stages 0,
1, 1.5, 2, 3, 4, and 5. The ledger records purpose, known commit hashes,
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
- `tests/test_kalshi_client.py`: mocked HTTP coverage for the Stage 2 client.
- `tests/test_kalshi_orderbook.py`: normalizer coverage.
- `tests/test_snapshots_jsonl.py`: snapshot/JSONL coverage.
- `tests/test_replay_snapshots.py`: replay and fixture-conversion coverage.
- `tests/test_quote_engine.py`: fair-value and dry-run quote-engine coverage.
- `tests/test_quote_replay_dry_run.py`: replay-based quote script coverage.
- `tests/test_demo_execution.py`: Stage 5 risk gate, blocked path, fake
  adapter, and audit log coverage.
- `tests/test_demo_execution_smoke.py`: Stage 5 smoke script coverage.

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
```

Optional environment validation:

```bash
python -m pip install -e ".[dev]"
```

## Known issues

- GitHub remote `origin` is configured for
  `https://github.com/minqiyang/market-neutral-trading-research.git`; do not
  push unless the user explicitly asks or the active workflow requires it.
- Local `main` and `origin/main` matched at
  `3bdd691cad5858aa57dc3268e801ac4e6642cdce` before the Stage 5 branch was
  created.
- `.github/workflows/ci.yml` exists, and the latest observed GitHub Actions CI
  run on `main` completed successfully.
- GitHub branch protection is enabled on `main` and requires the `Validate`
  status check.
- The Kalshi Demo client is tested with mocked HTTP and local fixtures; no live
  network smoke script exists.
- Quote dry-runs emit non-executable intents. Stage 5 converts those boundaries
  into fake-adapter demo execution requests only after explicit risk approval;
  no fill simulation, WebSocket ingestion, production trading path, or live
  market-making loop exists.

## PR workflow policy

`docs/codex_long_running_controller.md` now contains a conservative auto-merge
policy: no direct merges to `main`, no branch-protection bypass or admin
override, and GitHub auto-merge only for clearly low-risk small PRs that are
narrow, locally validated, protected by required checks/reviews, and free of
credentials, production endpoints, order placement, WebSocket work, strategy
optimization, large generated files, dependency surprises, or compliance
ambiguity.

## Safety boundaries

- Do not add credentials or secrets.
- Do not implement production order placement.
- Do not implement WebSocket ingestion.
- Do not add fill simulation before a dedicated simulation stage.
- Do not enable live or production trading.
- Do not make profitability claims.
- Keep Kalshi-specific code under `src/edmn_trader/adapters/kalshi`.

## Next recommended stage

Stage 6: Inventory-aware demo market maker in dry-run/demo only, after the
Stage 5 PR is merged.

## Exact next prompt suggestion

After the Stage 5 PR is merged, implement Stage 6 from `docs/STAGE_PLAN.md`:
connect normalized books, fair value, quote generation, risk gates, and
dry-run/demo loop behavior without production trading or broad strategy
deployment.

## Last updated timestamp

2026-06-12 14:10:41 -07:00
