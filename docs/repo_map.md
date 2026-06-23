# Repo Map

## Minimal first-pass context

Read these files before broad exploration:

1. `AGENTS.md`
2. `docs/current_handoff.md`
3. `docs/repo_map.md`

## Targeted reads only

Avoid reading the whole repository by default. Start with the minimal first-pass
context, then read only the files needed for the requested stage. Use `rg` and
`rg --files` for focused discovery.

## Root files

- `AGENTS.md`: rules for Codex sessions, safety boundaries, and required first
  reads. Read this for every task.
- `PROJECT_SPEC.md`: product and technical specification. Read when scope,
  modules, acceptance standards, or non-goals are unclear.
- `CHANGELOG.md`: external-facing milestone log. Update after stage-sized
  changes.
- `README.md`: public project overview, setup, scope, and workflow links. Read
  when changing user-facing positioning.
- `pyproject.toml`: Python package, runtime dependencies, pytest, and Ruff
  configuration. Read when changing dependencies, tooling, package layout, or
  entry points.
- `.env.example`: non-secret local defaults. Read when environment variables
  are relevant.

## Docs

- `docs/current_handoff.md`: compact latest state and next step. Read after
  `AGENTS.md` in future sessions.
- `docs/codex_long_running_controller.md`: staged workflow rules, stop gates,
  checks, logging, and final report format. Read before long-running stage work.
- `docs/STAGE_PLAN.md`: staged roadmap from foundation through later research
  adapters. Read when planning or validating stage boundaries.
- `docs/stage8_polymarket_readiness.md`: Stage 8 compliance/readiness note.
  Read before any Polymarket US adapter work.
- `docs/DECISION_LOG.md`: architecture and product decisions. Read before
  reversing or expanding a foundational decision.
- `docs/engineering_log.md`: human-readable narrative for interviews and
  project reflection. Update after stage-sized work.
- `docs/PROJECT_CHARTER.md`: mission, positioning, and initial stage boundary.
- `docs/ROADMAP.md`: compact roadmap. Use `docs/STAGE_PLAN.md` for detailed
  staged acceptance checks.
- `docs/RISK_POLICY.md`: non-negotiable safety and execution constraints.
- `docs/RESUME_NARRATIVE.md`: portfolio framing and concise project story.
- `docs/handoff_archive/README.md`: process for archiving old handoffs.

## Source

- `src/edmn_trader/core/models.py`: exchange-agnostic dataclasses and
  `ExecutionMode`. Read when changing core trading concepts.
- `src/edmn_trader/adapters/kalshi/client.py`: guarded read-only Kalshi Demo
  REST client for public markets and orderbooks. Read for Stage 2 client
  behavior, error handling, or endpoint path changes.
- `src/edmn_trader/adapters/kalshi/orderbook.py`: Kalshi fixed-point
  orderbook normalizer. Read for Kalshi orderbook parsing only.
- `src/edmn_trader/data/snapshots.py`: offline market-data snapshot model and
  snapshot JSONL persistence helpers. Read for recorded data schema changes.
- `src/edmn_trader/data/jsonl.py`: Decimal-safe JSONL read/write/append helpers.
  Read for storage behavior and malformed JSONL handling.
- `src/edmn_trader/data/replay.py`: deterministic replay session and book
  metrics. Read for replay ordering or metric changes.
- `src/edmn_trader/research/fair_value.py`: baseline fair-value model. Read for
  midpoint and one-sided fair-value behavior.
- `src/edmn_trader/research/quotes.py`: dry-run quote engine, inventory skew,
  tick/price boundaries, and non-executable quote intents. Read for Stage 4
  quote behavior.
- `src/edmn_trader/execution/demo.py`: Stage 5 risk-gated fake/demo execution
  boundary, risk decisions, fake adapter, and JSONL audit logging. Read for
  execution smoke behavior.
- `src/edmn_trader/scripts/replay_orderbook_fixture.py`: importable fixture
  replay entry point.
- `src/edmn_trader/scripts/record_fixture_snapshots.py`: importable Stage 3
  fixture-to-snapshot recorder logic.
- `src/edmn_trader/scripts/replay_snapshots.py`: importable Stage 3 snapshot
  replay table renderer.
- `src/edmn_trader/scripts/quote_replay_dry_run.py`: importable Stage 4 replay
  dry-run quote script and table renderer.
- `src/edmn_trader/scripts/demo_execution_smoke.py`: importable Stage 5
  fake-adapter demo execution smoke script.
- `src/edmn_trader/scripts/market_maker_replay.py`: importable Stage 6 finite
  replay workflow for quote lifecycle, risk gates, logs, and run summaries.
- `src/edmn_trader/scripts/research_report.py`: importable Stage 7 offline
  report generator for Stage 6 logs and explicit fill assumptions.
- `src/edmn_trader/**/__init__.py`: package exports.

## Scripts

- `scripts/01_replay_orderbook_fixture.py`: root-level wrapper for replaying the
  local Kalshi fixture. Run after normalization-related changes.
- `scripts/02_record_fixture_snapshots.py`: converts committed local fixtures
  into JSONL snapshots. Requires `--output`.
- `scripts/03_replay_snapshots.py`: reads JSONL snapshots and prints book
  metrics. Requires `--input`.
- `scripts/04_quote_replay_dry_run.py`: reads JSONL snapshots and prints
  fair-value and dry-run quote metrics. Requires `--input`.
- `scripts/05_demo_execution_smoke.py`: runs a local fake-adapter Stage 5
  execution smoke check and appends JSONL audit logs. Use `--demo-opt-in` only
  for fake-adapter approved-path validation.
- `scripts/06_market_maker_replay.py`: runs the finite Stage 6 replay workflow
  and writes structured JSONL logs.
- `scripts/07_research_report.py`: writes a local/offline Markdown attribution
  report from Stage 6 JSONL logs and optional explicit fill fixtures.

## Tests and fixtures

- `tests/test_core_models.py`: execution-mode and core safety checks.
- `tests/test_kalshi_client.py`: mocked HTTP tests for the guarded read-only
  Kalshi Demo REST client.
- `tests/test_kalshi_orderbook.py`: deterministic normalizer coverage.
- `tests/test_snapshots_jsonl.py`: JSONL roundtrip, Decimal precision,
  malformed JSONL, append behavior, and snapshot raw-payload safety coverage.
- `tests/test_replay_snapshots.py`: replay ordering, replay metrics, and
  fixture-to-snapshot conversion coverage.
- `tests/test_quote_engine.py`: midpoint fair value, one-sided fallback, quote
  generation, inventory skew, tick/price boundary, and dry-run intent coverage.
- `tests/test_quote_replay_dry_run.py`: replay-based dry-run quote script
  coverage.
- `tests/test_demo_execution.py`: Stage 5 risk gate, blocked path, fake
  adapter, and execution audit log coverage.
- `tests/test_demo_execution_smoke.py`: Stage 5 smoke script coverage.
- `tests/test_market_maker_replay.py`: Stage 6 dry-run/demo, lifecycle,
  run-control, adapter-error, and script-summary coverage.
- `tests/test_research_report.py`: Stage 7 report generation, explicit fill
  attribution, secret-like fill field rejection, and CLI coverage.
- `tests/fixtures/kalshi_orderbook_fp_basic.json`: basic local Kalshi-style
  fixture used by the replay script.
- `tests/fixtures/kalshi_markets_response.json`: local markets response fixture
  for Stage 2 client tests.
- `tests/fixtures/kalshi_orderbook_response.json`: local orderbook response
  fixture for Stage 2 client tests.

## Project Skill

- `.agents/skills/event-driven-market-neutral-trader/SKILL.md`: reusable
  project-specific Codex guidance. Read for non-trivial repo work and update
  only with verified lessons.
