# Current Handoff

## Current project state

The repository contains a Python 3.12 package for a demo-first,
risk-controlled event-driven prediction-market research platform. Current
implemented code includes exchange-agnostic core models, Kalshi-style
fixed-point orderbook normalization, a guarded read-only Kalshi Demo REST
client, local fixtures, mocked HTTP tests, Decimal-safe JSONL snapshot storage,
and deterministic offline replay metrics.

## Last completed stage

Stage 3: Local replay simulator and read-only data recorder.

## Stage plan status

`docs/STAGE_PLAN.md` now contains the full Stage 3 specification: snapshot
schema requirements, Decimal-safe JSONL recorder requirements, deterministic
replay behavior, fixture recording and replay scripts, offline tests,
out-of-scope boundaries, validation commands, and the Stage 4 boundary.

`docs/STAGE_PLAN.md` also contains the full Stage 4 specification: fair-value
baseline requirements, quote generation, inventory-aware skew, spread and
tick/price boundary handling, dry-run-only intent output, replay dry-run script,
offline deterministic tests, validation commands, non-goals, and the Stage 5
boundary.

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
- `scripts/02_record_fixture_snapshots.py`: converts local fixtures to JSONL
  snapshots.
- `scripts/03_replay_snapshots.py`: replays JSONL snapshots and prints a
  concise metrics table.
- `tests/test_kalshi_client.py`: mocked HTTP coverage for the Stage 2 client.
- `tests/test_kalshi_orderbook.py`: normalizer coverage.
- `tests/test_snapshots_jsonl.py`: snapshot/JSONL coverage.
- `tests/test_replay_snapshots.py`: replay and fixture-conversion coverage.

## Commands that currently pass

```bash
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage3_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage3_snapshots.jsonl
```

Optional environment validation:

```bash
python -m pip install -e ".[dev]"
```

## Known issues

- The repository has no remote configured by design.
- The Kalshi Demo client is tested with mocked HTTP and local fixtures; no live
  network smoke script exists.
- Replay currently exposes book metrics only. No fill simulation, strategy,
  execution engine, WebSocket ingestion, or production trading path exists.

## Safety boundaries

- Do not add credentials or secrets.
- Do not implement order placement.
- Do not implement WebSocket ingestion.
- Do not implement strategies in Stage 4 unless limited to dry-run quote
  objects and explicitly scoped.
- Do not add fill simulation before a dedicated simulation stage.
- Do not enable live or production trading.
- Do not make profitability claims.
- Keep Kalshi-specific code under `src/edmn_trader/adapters/kalshi`.

## Next recommended stage

Stage 4: Fair-value and quote engine dry-run, consuming normalized/replayed
books and emitting quote objects only.

## Exact next prompt suggestion

Implement Stage 4 for `event-driven-market-neutral-trader`: fair-value and
quote engine dry-run. First read `AGENTS.md`, `docs/current_handoff.md`,
`docs/repo_map.md`, `docs/codex_long_running_controller.md`, and
`docs/STAGE_PLAN.md`. Consume normalized/replayed books and emit dry-run quote
objects only. Do not implement order placement, WebSocket, credentials,
production endpoints, fill simulation, strategy optimization, profitability
claims, or live trading.

## Last updated timestamp

2026-06-11 17:06:31 -07:00
