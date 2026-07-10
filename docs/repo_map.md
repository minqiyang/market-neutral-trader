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
- `docs/visual_overview.md`: GitHub-rendered Mermaid diagrams for the post-PR
  #109 workflow, six-layer architecture, safety gate, and public/private
  boundary.
- `docs/roadmap_conformance_audit.md`: Stage 35-52 roadmap-to-implementation
  audit and follow-up notes for stale documentation.
- `docs/end_to_end_conformance_audit.md`: end-to-end trace audit from
  fixture/live-readonly data through the disabled private-live gate.
- `docs/portfolio_summary.md`: concise reviewer-facing project summary,
  architecture, safety boundary, validation status, and takeaway.
- `docs/release_notes_stage_52.md`: draft GitHub Release title/body and
  Stage 52 public release scope.
- `docs/resume_bullets_stage_52.md`: resume-ready bullets for the completed
  Stage 52 public research platform.
- `docs/v2_readonly_recorder_campaign.md`: V2 seven-day read-only campaign
  lifecycle gate and evidence boundary.
- `docs/v2_ws_raw_event_schema.md`: D2A Kalshi WebSocket native envelope,
  payload hash, sequence/segment semantics, snapshot prerequisite, legacy
  compatibility, and evidence limitations.
- `docs/v2_ws_native_orderbook_rebuild.md`: D2B native state, snapshot/delta,
  price-scale, invalidation/recovery, canonical YES frame, and semantic-hash
  contract plus its sequence/replay evidence limits.
- `docs/v2_monitor_contract.md`: V2 monitor lifecycle, liveness, and stale
  semantics contract.
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
- `docs/private_live_execution_gate.md`: Stage 52 disabled private live gate
  design and unmet private-live prerequisites.
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
- `src/edmn_trader/adapters/kalshi/readonly_recorder.py`: Stage 40 guarded
  Kalshi Demo read-only recorder with explicit opt-in and mocked-testable
  client injection.
- `src/edmn_trader/adapters/kalshi/ws_auth.py`: Demo-only authenticated
  WebSocket header construction and credential preflight boundary.
- `src/edmn_trader/adapters/kalshi/ws_events.py`: D2A versioned native raw
  event envelope, deterministic parsed-payload hash, conservative sequence
  tracker, segment/snapshot admission state, and explicit legacy parser.
- `src/edmn_trader/adapters/kalshi/ws_book_rebuild.py`: D2B fixture-only
  incremental native snapshot/delta rebuild, Decimal price-scale conversion,
  typed quarantine/invalidation, canonical YES frames, and semantic hashes.
- `src/edmn_trader/adapters/kalshi/ws_recorder.py`: read-only Kalshi Demo
  WebSocket recorder. It emits D2A envelopes without additional subscriptions
  or orderbook rebuild behavior.
- `src/edmn_trader/adapters/kalshi/demo_connector.py`: Stage 49 guarded
  Kalshi Demo request preview and Demo submit path mocked in tests. Read for
  manual approval, risk, paper ledger, Demo allowlist, and audit-redaction
  behavior.
- `src/edmn_trader/adapters/kalshi/demo_reconciliation.py`: Stage 50 local
  Kalshi Demo reconciliation replay. Read for accepted/rejected/fill/cancel/
  error/timeout/backfill event replay, duplicate handling, mismatch detection,
  and Demo submit eligibility blocking.
- `src/edmn_trader/adapters/polymarket_us/client.py`: guarded read-only
  Polymarket US public market-data client.
- `src/edmn_trader/adapters/polymarket_us/orderbook.py`: Polymarket US
  market-book normalizer. Read for Stage 8 parsing only.
- `src/edmn_trader/adapters/polymarket_us/market_recorder.py`: Stage 41
  guarded Polymarket US market-channel recorder with explicit opt-in and
  mocked-testable client injection.
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
- `src/edmn_trader/arb/fill_simulation.py`: Stage 43 offline taker fill,
  slippage, latency shock, and failed-leg reserve simulator.
- `src/edmn_trader/arb/paper_engine.py`: Stage 44 paper-only complement
  proposal engine with locked candidate/simulation source hashes.
- `src/edmn_trader/arb/paper_ledger.py`: Stage 45 paper ledger state machine
  for local proposal, fill, settlement, position, fee, PnL, and mismatch replay.
- `src/edmn_trader/arb/risk.py`: Stage 46 paper-only complement risk engine
  v2 for blocker checks and manual-review-required decisions.
- `src/edmn_trader/arb/approval.py`: Stage 47 local manual approval workflow
  for pending files, expiring approvals, hash checks, and single-use records.
- `src/edmn_trader/arb/monitoring.py`: Stage 48 offline daily validation
  report aggregation for local monitoring/research records.
- `src/edmn_trader/arb/long_term_validation.py`: Stage 51 offline rolling
  paper/demo validation reports over local research artifacts.
- `src/edmn_trader/fees/base.py`: venue-neutral fee estimate status and
  Decimal fee assumption model. Read for fee-model work.
- `src/edmn_trader/fees/kalshi.py`: Kalshi fee estimate scaffold with explicit
  supplied/missing/unknown assumptions only.
- `src/edmn_trader/fees/polymarket_us.py`: Polymarket US fee estimate scaffold
  with explicit supplied/missing/unknown assumptions only.
- `src/edmn_trader/data/snapshots.py`: offline market-data snapshot model and
  snapshot JSONL persistence helpers. Read for recorded data schema changes.
- `src/edmn_trader/data/live_events.py`: Stage 39 read-only live market-data
  event schema and mocked WebSocket-style recorder harness.
- `src/edmn_trader/data/book_rebuild.py`: Stage 42 recorded-event order book
  rebuild, deterministic book hashing, and replay consistency flags.
- `src/edmn_trader/data/payload_safety.py`: shared raw-payload secret-key
  rejection helper for recorded market-data payloads.
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
- `src/edmn_trader/execution/private_live_gate.py`: Stage 52 disabled public
  live execution gate placeholder. Read before any private-live gate work.
- `src/edmn_trader/cli/monitor.py`: read-only terminal monitor over local
  summaries/JSONL artifacts. Read for lifecycle, stale-data, and liveness
  display changes.
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
- `src/edmn_trader/scripts/mock_live_event_recorder.py`: importable Stage 39
  local mocked WebSocket recorder CLI entry point.
- `src/edmn_trader/scripts/kalshi_readonly_recorder.py`: importable Stage 40
  guarded Kalshi Demo read-only recorder CLI entry point.
- `src/edmn_trader/scripts/polymarket_market_recorder.py`: importable Stage 41
  guarded Polymarket US market-channel recorder CLI entry point.
- `src/edmn_trader/scripts/rebuild_orderbooks.py`: importable Stage 42
  recorded-event rebuild CLI entry point.
- `src/edmn_trader/scripts/simulate_taker_fill.py`: importable Stage 43
  offline taker fill simulation CLI entry point.
- `src/edmn_trader/scripts/paper_complement_engine.py`: importable Stage 44
  paper-only complement proposal CLI entry point.
- `src/edmn_trader/scripts/paper_ledger.py`: importable Stage 45 paper ledger
  replay CLI entry point.
- `src/edmn_trader/scripts/complement_risk.py`: importable Stage 46
  complement risk v2 CLI entry point.
- `src/edmn_trader/scripts/manual_approval.py`: importable Stage 47 local
  manual approval CLI entry point.
- `src/edmn_trader/scripts/daily_validation_report.py`: importable Stage 48
  daily validation report CLI entry point.
- `src/edmn_trader/scripts/v2_readonly_campaign.py`: V2 read-only campaign
  planning, paginated Demo market discovery, smoke, validation, manifest,
  lifecycle gate, and evidence classification helper. Read before any recorder
  campaign gate work.
- `src/edmn_trader/scripts/kalshi_demo_connector.py`: importable Stage 49
  guarded Kalshi Demo connector preview CLI entry point.
- `src/edmn_trader/scripts/kalshi_demo_reconciliation.py`: importable Stage 50
  local Kalshi Demo reconciliation replay CLI entry point.
- `src/edmn_trader/scripts/long_term_validation.py`: importable Stage 51
  rolling paper/demo validation report CLI entry point.
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
- `scripts/39_mock_live_event_recorder.py`: runs the local-only Stage 39
  mocked WebSocket recorder fixture harness.
- `scripts/40_kalshi_readonly_recorder.py`: runs the guarded Kalshi Demo
  read-only recorder; defaults disabled without `--live-readonly-opt-in`.
- `scripts/41_polymarket_market_recorder.py`: runs the guarded Polymarket US
  market-channel recorder; defaults disabled without `--live-readonly-opt-in`.
- `scripts/42_rebuild_orderbooks.py`: rebuilds normalized order books from
  recorded event JSONL and writes snapshots, frame hashes, and a Markdown
  consistency summary.
- `scripts/43_simulate_taker_fill.py`: runs local/offline two-leg taker fill
  simulations from explicit fixture assumptions.
- `scripts/44_paper_complement_engine.py`: writes paper-only complement
  proposal JSONL/Markdown from scanner candidate and fill simulation JSONL.
- `scripts/45_replay_paper_ledger.py`: replays local paper proposal, fill,
  and settlement records into paper ledger JSONL/Markdown state.
- `scripts/46_complement_risk.py`: evaluates local complement risk-check
  fixtures into paper risk-decision JSONL/Markdown records.
- `scripts/47_manual_approval.py`: creates pending approval JSON and verifies
  local single-use manual approval records.
- `scripts/48_daily_validation_report.py`: builds offline daily validation
  report JSONL/Markdown from local monitoring records.
- `scripts/49_kalshi_demo_connector.py`: builds guarded Kalshi Demo dry-run
  request previews from local paper, risk, approval, and ledger records.
- `scripts/50_kalshi_demo_reconciliation.py`: replays local/mock Kalshi Demo
  event JSONL against one Stage 49 connector audit record and appends
  reconciliation state.
- `scripts/51_long_term_validation.py`: builds offline rolling 7/30/90-day
  validation reports from local paper/demo research JSONL artifacts.
- `scripts/v2_readonly_campaign.py`: root wrapper for V2 read-only campaign
  plan/smoke/validate commands. Do not use it to launch real campaigns without
  the explicit owner-run boundary.
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
- `tests/test_live_event_recorder.py`: Stage 39 live-event schema and mocked
  recorder coverage for JSONL roundtrip, payload safety, deterministic output,
  local fixture CLI behavior, and timezone validation.
- `tests/test_kalshi_readonly_recorder.py`: Stage 40 Kalshi Demo read-only
  recorder guardrail coverage for opt-in, Demo-only config, mocked HTTP
  recording, raw event JSONL, normalized snapshot JSONL, and non-executable
  records.
- `tests/test_kalshi_ws_events.py`: synthetic D2A envelope, payload hash,
  native/local sequence, segment, snapshot admission, resync, and legacy
  compatibility tests.
- `tests/test_kalshi_ws_book_rebuild.py`: synthetic D2B coverage for native
  snapshots/deltas, isolation, pricing modes, invalidation/recovery, canonical
  books, exact Decimal values, deterministic hashes, and compatibility gates.
- `tests/test_kalshi_ws_recorder.py`: fixture-only recorder integration tests
  for v2 envelope output, connection/segment boundaries, and pre-snapshot
  delta exclusion.
- `tests/test_polymarket_market_recorder.py`: Stage 41 Polymarket US
  market-channel recorder guardrail coverage for opt-in, US-public-only config,
  mocked HTTP recording, raw event JSONL, normalized snapshot JSONL, and
  non-executable records.
- `tests/test_book_rebuild.py`: Stage 42 order book rebuild coverage for
  deterministic hashes, gap/stale/out-of-order flags, JSONL/Markdown output,
  CLI behavior, and unsupported-event rejection.
- `tests/test_fill_simulation.py`: Stage 43 fill simulator coverage for
  FOK/IOC-like policy assumptions, partial fills, slippage, latency shock,
  failed-leg reserve, deterministic output, and local fixture CLI behavior.
- `tests/test_paper_engine.py`: Stage 44 paper proposal coverage for source
  hashes, conservative risk preview, deterministic output, and CLI behavior.
- `tests/test_paper_ledger.py`: Stage 45 paper ledger coverage for local
  replay, positions, fees, PnL, mismatches, deterministic output, and CLI
  behavior.
- `tests/test_complement_risk.py`: Stage 46 risk v2 coverage for blockers,
  manual-review-required decisions, deterministic output, and CLI behavior.
- `tests/test_manual_approval.py`: Stage 47 manual approval coverage for
  pending files, expiry, hash checks, single-use enforcement, output, and CLI
  behavior.
- `tests/test_daily_validation_report.py`: Stage 48 daily validation report
  coverage for local metrics aggregation, deterministic output, and CLI
  behavior.
- `tests/test_kalshi_demo_connector.py`: Stage 49 connector coverage for
  dry-run previews, Demo URL rejection, risk/manual approval/ledger/
  reconciliation gates, mocked HTTP submit success/reject/error paths, and
  audit redaction.
- `tests/test_kalshi_demo_reconciliation.py`: Stage 50 reconciliation coverage
  for accepted/rejected/fill/cancel/error/timeout/backfill events, duplicate
  idempotency, mismatches, submit blocking, append-only output, and CLI
  behavior.
- `tests/test_long_term_validation.py`: Stage 51 rolling validation coverage
  for 7/30/90-day summaries, deterministic JSONL/JSON/Markdown output,
  unmet private-live prerequisites, invalid input rejection, and Decimal
  precision.
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
- `tests/test_private_live_gate.py`: Stage 52 disabled live gate coverage for
  unmet prerequisites, fail-closed status, and no endpoint/credential/order
  payload exposure.
- `tests/test_v2_readonly_campaign.py`: V2 read-only campaign smoke,
  lifecycle selection gate, finalized-market evidence invalidation, monitor
  lifecycle display, and disabled live gate coverage.
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
