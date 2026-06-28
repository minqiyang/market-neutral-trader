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
- `docs/ARBITRAGE_ROADMAP.md`: active same-market YES/NO complement parity
  roadmap, six-layer architecture, and report-input maintenance boundary.
- `docs/stage8_polymarket_readiness.md`: Stage 8 compliance/readiness note.
  Read before any Polymarket US adapter work.
- `docs/stage9_equities_readiness.md`: Stage 9 SEC EDGAR equities readiness
  note. Read before any U.S. equities adapter work.
- `docs/stage11_report_sections_readiness.md`: Stage 11 readiness note for
  local/offline report-section expansion.
- `docs/stage12_report_inputs_readiness.md`: Stage 12 readiness note for a
  local/offline report-input manifest.
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
- `src/edmn_trader/adapters/polymarket_us/client.py`: guarded read-only
  Polymarket US public market-data client.
- `src/edmn_trader/adapters/polymarket_us/orderbook.py`: Polymarket US
  market-book normalizer. Read for Stage 8 parsing only.
- `src/edmn_trader/adapters/sec_edgar/client.py`: guarded read-only SEC EDGAR
  public companyfacts client.
- `src/edmn_trader/adapters/sec_edgar/companyfacts.py`: SEC companyfacts
  normalizer. Read for Stage 9 parsing only.
- `src/edmn_trader/arb/complement.py`: offline Decimal-only same-market
  YES/NO complement-parity candidate model. Read for arbitrage roadmap, fee
  model, or offline scanner work.
- `src/edmn_trader/arb/scanner.py`: Stage 38 offline complement scanner for
  local fixture JSON and existing snapshot JSONL inputs. Read for scanner
  output, rejection reason, and data-quality flag behavior.
- `src/edmn_trader/fees/base.py`: venue-neutral fee estimate status and
  Decimal fee assumption model. Read for fee-model work.
- `src/edmn_trader/fees/kalshi.py`: Kalshi fee estimate scaffold with explicit
  supplied/missing/unknown assumptions only.
- `src/edmn_trader/fees/polymarket_us.py`: Polymarket US fee estimate scaffold
  with explicit supplied/missing/unknown assumptions only.
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
- `src/edmn_trader/research/equities.py`: exchange-agnostic equities research
  fact model for SEC fundamentals.
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
- `src/edmn_trader/scripts/scan_complement_arb.py`: importable Stage 38
  offline complement scanner CLI entry point.
- `src/edmn_trader/scripts/research_report.py`: importable Stage 7 offline
  report generator for Stage 6 logs and explicit fill assumptions.
- `src/edmn_trader/scripts/paper_report_pack.py`: importable Stage
  10/12/13/14/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34
  offline report-pack generator combining Stage 7 attribution with local SEC
  companyfacts fixtures, local report-section metadata, optional manifest input
  metadata, local run-comparison metadata, and local validation-summary
  metadata, local review-notes metadata, local methodology-notes metadata, and
  local data-dictionary metadata, local citation-index metadata, and local
  term-glossary metadata, local assumption-register metadata, and local
  coverage-matrix metadata, local reproducibility-checklist metadata, local
  risk-review metadata, local data-rights-review metadata, local
  artifact-inventory metadata, local appendix-index metadata, and local
  limitation-register metadata, local open-questions metadata, and local
  decision-log metadata, local follow-up-register metadata, local
  version-notes metadata, local distribution-checklist metadata, local
  handoff-notes metadata, and local archive-notes metadata.
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
- `scripts/23_scan_complement_arb.py`: runs the offline complement scanner
  against local fixture JSON or existing snapshot JSONL and writes JSONL plus
  Markdown research reports.
- `scripts/07_research_report.py`: writes a local/offline Markdown attribution
  report from Stage 6 JSONL logs and optional explicit fill fixtures.
- `scripts/10_paper_report_pack.py`: writes a local/offline Markdown report
  pack from Stage 6/7 attribution inputs, optional local SEC companyfacts
  fixtures, the Stage 11 local source inventory section, and optional Stage 12
  manifest input metadata including Stage 13 local run-comparison descriptors
  Stage 14 local validation-summary descriptors, and Stage 15 local
  review-notes descriptors, Stage 16 local methodology-notes descriptors, and
  Stage 17 local data-dictionary descriptors, Stage 18 local citation-index
  descriptors, Stage 19 local term-glossary descriptors, and Stage 20 local
  assumption-register descriptors, and Stage 21 local coverage-matrix
  descriptors, Stage 22 local reproducibility-checklist descriptors, and Stage
  23 local risk-review descriptors, Stage 24 local data-rights-review
  descriptors, Stage 25 local artifact-inventory descriptors, Stage 26 local
  appendix-index descriptors, and Stage 27 local limitation-register
  descriptors, Stage 28 local open-questions descriptors, and Stage 29 local
  decision-log descriptors, Stage 30 local follow-up-register descriptors, and
  Stage 31 local version-notes descriptors, Stage 32 local
  distribution-checklist descriptors, Stage 33 local handoff-notes
  descriptors, and Stage 34 local archive-notes descriptors.

## Tests and fixtures

- `tests/test_core_models.py`: execution-mode and core safety checks.
- `tests/test_kalshi_client.py`: mocked HTTP tests for the guarded read-only
  Kalshi Demo REST client.
- `tests/test_kalshi_orderbook.py`: deterministic normalizer coverage.
- `tests/test_complement_arb.py`: offline complement-parity candidate coverage
  for gross/net edge, locked/crossed states, fee assumptions, Decimal
  precision, and manual-review flags.
- `tests/test_fee_models.py`: Stage 37 fee estimate coverage for explicit
  supplied assumptions, missing/unknown fee status, candidate blocking, and
  Decimal validation.
- `tests/test_complement_scanner.py`: Stage 38 scanner coverage for
  deterministic JSONL/Markdown output, audit/reject counts, fee blocking,
  invalid local input, non-executable records, and Decimal preservation.
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
- `tests/test_polymarket_us_adapter.py`: Stage 8 Polymarket US fixture
  normalization, guarded public client, and malformed-book coverage.
- `tests/test_sec_edgar_adapter.py`: Stage 9 SEC companyfacts normalization,
  guarded public client, explicit User-Agent, and malformed-value coverage.
- `tests/test_paper_report_pack.py`: Stage 10/12/13/14/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34 offline report-pack coverage
  for observed metrics, source inventory, not-supplied optional inputs, local
  SEC facts, manifest input metadata, local run-comparison metadata, unsafe
  manifest/comparison rejection, local validation-summary metadata, unsafe
  validation-summary rejection, local review-notes metadata, unsafe
  review-notes rejection, local methodology-notes metadata, unsafe
  methodology-notes rejection, local data-dictionary metadata, unsafe
  data-dictionary rejection, local citation-index metadata, unsafe
  citation-index rejection, local term-glossary metadata, unsafe
  term-glossary rejection, local assumption-register metadata, unsafe
  assumption-register rejection, local coverage-matrix metadata, unsafe
  coverage-matrix rejection, local reproducibility-checklist metadata, unsafe
  reproducibility-checklist rejection, local risk-review metadata, unsafe
  risk-review rejection, local data-rights-review metadata, unsafe
  data-rights-review rejection, local artifact-inventory metadata, unsafe
  artifact-inventory rejection, local appendix-index metadata, unsafe
  appendix-index rejection, local limitation-register metadata, unsafe
  limitation-register rejection, local open-questions metadata, unsafe
  open-questions rejection, local decision-log metadata, unsafe decision-log
  rejection, local follow-up-register metadata, unsafe follow-up-register
  rejection, local version-notes metadata, unsafe version-notes rejection,
  local distribution-checklist metadata, unsafe distribution-checklist
  rejection, local handoff-notes metadata, unsafe handoff-notes rejection,
  local archive-notes metadata, unsafe archive-notes rejection, and CLI output.
- `tests/fixtures/kalshi_orderbook_fp_basic.json`: basic local Kalshi-style
  fixture used by the replay script.
- `tests/fixtures/sec_companyfacts_aapl.json`: local SEC companyfacts fixture
  for Stage 9 adapter tests.
- `tests/fixtures/polymarket_us_market_book.json`: local Polymarket US
  market-book fixture for Stage 8 adapter tests.
- `tests/fixtures/kalshi_markets_response.json`: local markets response fixture
  for Stage 2 client tests.
- `tests/fixtures/kalshi_orderbook_response.json`: local orderbook response
  fixture for Stage 2 client tests.

## Project Skill

- `.agents/skills/event-driven-market-neutral-trader/SKILL.md`: reusable
  project-specific Codex guidance. Read for non-trivial repo work and update
  only with verified lessons.
