# Current Handoff

## Current project state

The repository contains a Python 3.12 package for a demo-first,
risk-controlled event-driven prediction-market research platform. Current
implemented code includes exchange-agnostic core models, Kalshi-style
fixed-point orderbook normalization, a guarded read-only Kalshi Demo REST
client, local fixtures, mocked HTTP tests, Decimal-safe JSONL snapshot storage,
deterministic offline replay metrics, and a fair-value/quote-engine dry run.

## Last completed stage

Stage 4: Fair-value and quote engine dry-run.

## Stage plan status

`docs/STAGE_PLAN.md` contains a completed-stage record ledger for Stages 0,
1, 1.5, 2, 3, and 4. The ledger records purpose, known commit hashes,
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
- `scripts/02_record_fixture_snapshots.py`: converts local fixtures to JSONL
  snapshots.
- `scripts/03_replay_snapshots.py`: replays JSONL snapshots and prints a
  concise metrics table.
- `scripts/04_quote_replay_dry_run.py`: replays JSONL snapshots through the
  dry-run quote engine and prints fair value and quote metrics.
- `tests/test_kalshi_client.py`: mocked HTTP coverage for the Stage 2 client.
- `tests/test_kalshi_orderbook.py`: normalizer coverage.
- `tests/test_snapshots_jsonl.py`: snapshot/JSONL coverage.
- `tests/test_replay_snapshots.py`: replay and fixture-conversion coverage.
- `tests/test_quote_engine.py`: fair-value and dry-run quote-engine coverage.
- `tests/test_quote_replay_dry_run.py`: replay-based quote script coverage.

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
  `6fefc3554bfff484d59c55262f89c47bb900daf5` during the Stage 5 readiness
  record audit.
- `.github/workflows/ci.yml` exists, and the latest observed GitHub Actions CI
  run on `main` completed successfully.
- GitHub reports branch `main` is not protected. Under the conservative
  auto-merge policy, Codex must not enable auto-merge until branch protection
  and required checks/reviews are configured and verifiable.
- The Kalshi Demo client is tested with mocked HTTP and local fixtures; no live
  network smoke script exists.
- Quote dry-runs emit non-executable intents only. No fill simulation,
  execution engine, WebSocket ingestion, or production trading path exists.

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
- Do not implement order placement.
- Do not implement WebSocket ingestion.
- Do not implement Stage 5 demo smoke execution until risk checks and
  blocked-path tests are explicit.
- Do not add fill simulation before a dedicated simulation stage.
- Do not enable live or production trading.
- Do not make profitability claims.
- Keep Kalshi-specific code under `src/edmn_trader/adapters/kalshi`.

## Next recommended stage

Stage 5: Risk-gated demo execution smoke test, with explicit risk checks and
blocked-path tests before any demo action.

## Exact next prompt suggestion

Implement Stage 5 from `docs/STAGE_PLAN.md`: add risk-gated demo execution
smoke-test infrastructure with explicit risk checks, blocked-path tests,
structured execution logging, demo-only constraints, and no production trading.
Use local deterministic tests and stop at the Stage 5 boundary.

## Last updated timestamp

2026-06-11 22:20:15 -07:00
