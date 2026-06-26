# Stage Plan

## Completed stage record

These records summarize the locally completed stages through Stage 20. They are
intended as a durable audit map; implementation details remain in the source,
tests, changelog, engineering log, and handoff archive.

### Stage 0: Repository foundation

- Status: complete.
- Commit: `1d74236` (co-committed with Stage 1 and Stage 1.5 foundation work).
- Purpose: establish the Python package, public positioning, tooling, docs, and
  safety boundary.
- Files/modules added: `README.md`, `AGENTS.md`, `pyproject.toml`,
  `.env.example`, package/test structure, project charter, roadmap, risk
  policy, resume narrative, and supporting docs.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, and `python scripts/01_replay_orderbook_fixture.py`.
- Next-stage boundary: Stage 1 may add local fixture-based orderbook
  normalization only.
- Safety status: no profitability claims, no production/live trading claims, no
  credentials, and no execution path.

### Stage 1: Kalshi-style orderbook normalization

- Status: complete.
- Commit: `1d74236` (same foundation commit).
- Purpose: normalize Kalshi-style YES/NO orderbooks into canonical YES-side
  bid/ask books.
- Files/modules added: `src/edmn_trader/core/models.py`,
  `src/edmn_trader/adapters/kalshi/orderbook.py`,
  `scripts/01_replay_orderbook_fixture.py`, local Kalshi fixture, and
  normalizer/core-model tests.
- Validation commands: `pytest`, `ruff check .`, and
  `python scripts/01_replay_orderbook_fixture.py`.
- Next-stage boundary: Stage 1.5 adds continuity docs and workflow governance,
  not new trading behavior.
- Safety status: no live API calls, no authenticated requests, no WebSocket, no
  order placement, no production/live trading claims, and no profitability
  claims.

### Stage 1.5: Long-running controller and memory layer

- Status: complete.
- Commit: `1d74236` for the controller/memory foundation; later workflow
  governance commits include `7a341aa` for conservative auto-merge policy and
  `6fefc35` for CI bootstrap.
- Purpose: make the repository safe to continue across Codex sessions,
  branches, machines, and future `/goal` runs.
- Files/modules added: `PROJECT_SPEC.md`, `docs/current_handoff.md`,
  `docs/repo_map.md`, `docs/codex_long_running_controller.md`,
  `docs/STAGE_PLAN.md`, `docs/DECISION_LOG.md`, `docs/engineering_log.md`,
  `CHANGELOG.md`, handoff archive guidance, and the project-specific Skill.
- Validation commands: `pytest`, `ruff check .`, and
  `python scripts/01_replay_orderbook_fixture.py`.
- Next-stage boundary: Stage 2 may add a read-only Kalshi Demo market-data
  client only.
- Safety status: no REST trading client, no order placement, no WebSocket, no
  strategies, no production/live trading claims, and no profitability claims.

### Stage 2: Read-only Kalshi Demo market-data client

- Status: complete.
- Commit: `08b1c17`.
- Purpose: add a guarded read-only Kalshi Demo REST client for public market
  metadata and orderbooks.
- Files/modules added: `src/edmn_trader/adapters/kalshi/client.py`, local
  Kalshi response fixtures, mocked HTTP tests, and docs/log updates.
- Validation commands: `pytest`, `ruff check .`, and
  `python scripts/01_replay_orderbook_fixture.py`.
- Next-stage boundary: Stage 3 may add offline snapshots and deterministic
  replay; it must not add execution or WebSocket behavior.
- Safety status: no credentials, no authenticated trading, no production
  endpoint, no order placement, no WebSocket, no production/live trading
  claims, and no profitability claims.

### Stage 3: Local replay simulator and snapshot recorder

- Status: complete.
- Commit: `2d26522`; Stage 3 plan clarification commit: `19a8754`.
- Purpose: add deterministic offline market-data snapshots and replay metrics
  so future research can run without live API state.
- Files/modules added: `src/edmn_trader/data/snapshots.py`,
  `src/edmn_trader/data/jsonl.py`, `src/edmn_trader/data/replay.py`,
  `scripts/02_record_fixture_snapshots.py`,
  `scripts/03_replay_snapshots.py`, snapshot/replay tests, and handoff archive.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage3_snapshots.jsonl`,
  and `python scripts/03_replay_snapshots.py --input /tmp/edmn_stage3_snapshots.jsonl`.
- Next-stage boundary: Stage 4 may consume replayed books for fair-value and
  dry-run quote output only.
- Safety status: no network requirement, no order placement, no WebSocket, no
  fill simulation, no production/live trading claims, no secrets, and no
  profitability claims.

### Stage 4: Fair-value and quote engine dry-run

- Status: complete.
- Commit: `7bf2aa4`; Stage 4 plan clarification commit: `394c63f`.
- Purpose: estimate baseline fair value from normalized/replayed books and emit
  inventory-aware dry-run quote candidates.
- Files/modules added: `src/edmn_trader/research/fair_value.py`,
  `src/edmn_trader/research/quotes.py`,
  `scripts/04_quote_replay_dry_run.py`, quote-engine tests, replay dry-run
  script tests, and handoff archive.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage4_snapshots.jsonl`,
  `python scripts/03_replay_snapshots.py --input /tmp/edmn_stage4_snapshots.jsonl`,
  and `python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage4_snapshots.jsonl`.
- Next-stage boundary: Stage 5 may add a risk-gated demo execution smoke test
  only after explicit risk checks, blocked-path tests, and logging requirements
  are in place.
- Safety status: quote outputs are `dry_run_only`; no adapter execution calls,
  no authentication, no order placement, no cancellation/modification, no fill
  simulation, no production/live trading claims, and no profitability claims.

### Stage 5: Risk-gated demo execution smoke test

- Status: complete.
- Commit: pending on the Stage 5 PR branch.
- Purpose: prove demo execution attempts are blocked unless explicit demo
  opt-in, demo endpoint, risk limits, and structured logging are present.
- Files/modules added: `src/edmn_trader/execution/demo.py`,
  `src/edmn_trader/execution/__init__.py`,
  `src/edmn_trader/scripts/demo_execution_smoke.py`,
  `scripts/05_demo_execution_smoke.py`, demo execution tests, smoke script
  tests, and CI validation for the smoke script.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage5_snapshots.jsonl`,
  `python scripts/03_replay_snapshots.py --input /tmp/edmn_stage5_snapshots.jsonl`,
  `python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage5_snapshots.jsonl`,
  and `python scripts/05_demo_execution_smoke.py --log-output /tmp/edmn_stage5_execution_smoke.jsonl`.
- Next-stage boundary: Stage 6 may connect normalized books, fair value,
  quote generation, risk gates, and dry-run/demo loop behavior. It must still
  avoid production trading and broad strategy deployment.
- Safety status: execution paths are fake/offline for tests and local smoke,
  `LIVE_DISABLED` blocks place/cancel/modify, production endpoints and missing
  demo opt-in are rejected, all attempts are logged, no credentials are needed,
  and no live network, WebSocket, strategy optimization, fill simulation,
  production endpoint, live-trading claim, or profitability claim is added.

### Stage 6: Inventory-aware demo market maker in dry-run/demo only

- Status: complete.
- Commit: `3f6633e`.
- Purpose: connect replayed books, baseline fair value, dry-run quote
  generation, quote lifecycle decisions, Stage 5 risk gates, and fake-adapter
  demo submissions in a finite offline workflow.
- Files/modules added: `src/edmn_trader/scripts/market_maker_replay.py`,
  `scripts/06_market_maker_replay.py`, Stage 6 market-maker replay tests, and
  package script entry point.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage6_snapshots.jsonl`,
  `python scripts/03_replay_snapshots.py --input /tmp/edmn_stage6_snapshots.jsonl`,
  `python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage6_snapshots.jsonl`,
  `python scripts/05_demo_execution_smoke.py --log-output /tmp/edmn_stage6_execution_smoke.jsonl`,
  `python scripts/05_demo_execution_smoke.py --demo-opt-in --log-output /tmp/edmn_stage6_execution_smoke_approved.jsonl`,
  `python scripts/06_market_maker_replay.py --input /tmp/edmn_stage6_snapshots.jsonl --log-output /tmp/edmn_stage6_market_maker.jsonl`,
  and `python scripts/06_market_maker_replay.py --input /tmp/edmn_stage6_snapshots.jsonl --demo-opt-in --log-output /tmp/edmn_stage6_market_maker_demo.jsonl`.
- Next-stage boundary: Stage 7 may add PnL attribution and research reporting
  only after Stage 6 run summaries make explicit that fills and PnL are not
  inferred.
- Safety status: finite replay only, dry-run by default, fake adapter only
  after explicit demo opt-in and Stage 5 risk approval, no authenticated order
  placement, no production endpoint, no WebSocket, no live market-making loop,
  no fill simulation, no strategy optimization, no secrets, and no
  profitability claim.

### Stage 7: PnL attribution and research report

- Status: complete.
- Commit: pending on the Stage 7 implementation branch.
- Purpose: generate offline research reports from Stage 6 decision logs and
  optional explicit local fill assumptions.
- Files/modules added: `src/edmn_trader/scripts/research_report.py`,
  `scripts/07_research_report.py`, Stage 7 report tests, package script entry
  point, and CI validation for report generation.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage7_snapshots.jsonl`,
  `python scripts/06_market_maker_replay.py --input /tmp/edmn_stage7_snapshots.jsonl --log-output /tmp/edmn_stage7_market_maker.jsonl`,
  `python scripts/06_market_maker_replay.py --input /tmp/edmn_stage7_snapshots.jsonl --demo-opt-in --log-output /tmp/edmn_stage7_market_maker_demo.jsonl`,
  and `python scripts/07_research_report.py --market-maker-log /tmp/edmn_stage7_market_maker.jsonl --output /tmp/edmn_stage7_report.md`.
- Next-stage boundary: Stage 8 may add additional research data adapters or
  richer reporting only after compliance and source-data boundaries are
  reviewed.
- Safety status: local/offline only, explicit fill assumptions only, no fill
  inference from fake/demo adapter submissions, no network calls, no
  authenticated execution, no production endpoints, no WebSocket ingestion, no
  strategy optimization, no secrets, and no profitability claim.

### Stage 8: Polymarket US market-data research adapter

- Status: complete.
- Commit: pending on the Stage 8 implementation branch.
- Purpose: prove a second prediction-market adapter can remain fixture-first,
  public-market-data only, read-only, and exchange-contained.
- Files/modules added: `src/edmn_trader/adapters/polymarket_us/client.py`,
  `src/edmn_trader/adapters/polymarket_us/orderbook.py`,
  `src/edmn_trader/adapters/polymarket_us/__init__.py`, local Polymarket US
  market-book fixture, adapter tests, and readiness documentation.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, and `python scripts/01_replay_orderbook_fixture.py`.
- Next-stage boundary: Stage 9 may add U.S. equities research data only after
  Stage 8 remains read-only, fixture-tested, exchange-contained, and
  compliance-bound.
- Safety status: Polymarket US public market-data only, no international
  Polymarket endpoints, no trading path, no wallet, no private key, no API key,
  no authenticated endpoint, no account data, no WebSocket, no live HTTP smoke
  by default, no geoblock or platform-rule bypass, no production execution, and
  no profitability claim.

### Stage 9: U.S. equities research adapter, paper/research only

- Status: complete.
- Commit: pending on the Stage 9 implementation branch.
- Purpose: prove U.S. equities research data ingestion can remain
  fixture-first, SEC-public-fundamentals only, read-only, and credential-free.
- Files/modules added: `src/edmn_trader/adapters/sec_edgar/client.py`,
  `src/edmn_trader/adapters/sec_edgar/companyfacts.py`,
  `src/edmn_trader/adapters/sec_edgar/__init__.py`,
  `src/edmn_trader/research/equities.py`, local SEC companyfacts fixture,
  adapter tests, and readiness documentation.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, and `python scripts/01_replay_orderbook_fixture.py`.
- Next-stage boundary: a later stage may add richer paper/research reporting
  only after SEC fundamentals ingestion remains read-only, fixture-tested, and
  credential-free.
- Safety status: SEC EDGAR public fundamentals only, no broker integration, no
  credentials, no account or portfolio data, no live quote feed, no paid-vendor
  market data, no proprietary exchange data, no live HTTP smoke by default, no
  order placement, no strategy optimization, no production execution, and no
  profitability claim.

### Stage 10: Paper research report pack

- Status: complete.
- Commit: pending on the Stage 10 implementation branch.
- Purpose: combine existing offline attribution outputs and local SEC
  fundamentals fixtures into a descriptive paper/research report pack.
- Files/modules added: `src/edmn_trader/scripts/paper_report_pack.py`,
  `scripts/10_paper_report_pack.py`, report-pack tests, CI validation, and
  documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage10_snapshots.jsonl`,
  `python scripts/06_market_maker_replay.py --input /tmp/edmn_stage10_snapshots.jsonl --log-output /tmp/edmn_stage10_market_maker.jsonl`,
  and `python scripts/10_paper_report_pack.py --market-maker-log /tmp/edmn_stage10_market_maker.jsonl --sec-companyfacts tests/fixtures/sec_companyfacts_aapl.json --output-dir /tmp/edmn_stage10_report_pack`.
- Next-stage boundary: later stages may add additional report sections only
  after the report pack keeps all data local/offline, assumption-labeled, and
  non-executable.
- Safety status: local/offline report output only, no broker integration, no
  credentials, no account or portfolio data, no live quote feed, no paid-vendor
  market data, no order placement, no ranking, no allocation advice, no
  strategy optimization, no production execution, and no profitability claim.

### Stage 11: Additional report sections, local/offline only

- Status: complete.
- Commit: pending on the Stage 11 implementation branch.
- Purpose: extend the Stage 10 report pack with a descriptive local source
  inventory section.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, and `python scripts/01_replay_orderbook_fixture.py`.
- Next-stage boundary: later stages may add new report inputs only after their
  data-source rights, offline fixture behavior, and non-executable report
  boundaries are clarified first.
- Safety status: local/offline descriptive report sections only, no new data
  adapters, no broker integration, no credentials, no account or portfolio
  data, no live quote feed, no paid-vendor market data, no WebSocket, no order
  placement, no ranking, no allocation advice, no strategy optimization, no
  production execution, and no profitability claim.

### Stage 12: Report input manifest, local/offline only

- Status: complete.
- Commit: pending on the Stage 12 implementation branch.
- Purpose: add a descriptive local manifest for optional report-pack inputs.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, and `python scripts/01_replay_orderbook_fixture.py`.
- Next-stage boundary: later stages may add concrete new input kinds only after
  each input kind's data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline descriptive manifest only, no new data adapters,
  no broker integration, no credentials, no account or portfolio data, no live
  quote feed, no paid-vendor market data, no WebSocket, no remote fetch, no
  order placement, no ranking, no allocation advice, no executable advice, no
  strategy optimization, no production execution, no unsupported redistribution,
  and no profitability claim.

### Stage 13: Local run-comparison report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 13 implementation branch.
- Purpose: add the first concrete new report-input kind after the Stage 12
  manifest: local run-comparison metadata for already generated project
  outputs.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline comparison metadata only, no new data adapters,
  no broker integration, no credentials, no account or portfolio data, no live
  quote feed, no paid-vendor market data, no WebSocket, no remote fetch, no
  order placement, no ranking, no allocation advice, no executable advice, no
  strategy optimization, no production execution, no unsupported redistribution,
  and no profitability claim.

### Stage 14: Local validation-summary report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 14 implementation branch.
- Purpose: add local validation-summary metadata for already-run local checks
  and generated artifacts.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline validation metadata only, no command execution
  from report inputs, no new data adapters, no broker integration, no
  credentials, no account or portfolio data, no live quote feed, no paid-vendor
  market data, no WebSocket, no remote fetch, no order placement, no ranking,
  no allocation advice, no executable advice, no strategy optimization, no
  production-readiness claim, no unsupported redistribution, and no
  profitability claim.

### Stage 15: Local review-notes report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 15 implementation branch.
- Purpose: add local reviewer-supplied notes, caveats, source paths, follow-up
  questions, and limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline review metadata only, no command execution from
  report inputs, no private data reads, no new data adapters, no broker
  integration, no credentials, no account or portfolio data, no live quote
  feed, no paid-vendor market data, no WebSocket, no remote fetch, no order
  placement, no ranking, no allocation advice, no executable advice, no
  strategy optimization, no production-readiness claim, no unsupported
  redistribution, and no profitability claim.

### Stage 16: Local methodology-notes report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 16 implementation branch.
- Purpose: add local reviewer-supplied methodology context, assumption
  descriptions, source paths, and caveat metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline methodology metadata only, no command execution
  from report inputs, no private data reads, no new data adapters, no broker
  integration, no credentials, no account or portfolio data, no live quote
  feed, no paid-vendor market data, no WebSocket, no remote fetch, no order
  placement, no ranking, no allocation advice, no executable advice, no
  strategy optimization, no production-readiness claim, no unsupported
  redistribution, and no profitability claim.

### Stage 17: Local data-dictionary report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 17 implementation branch.
- Purpose: add local reviewer-supplied field definitions, units, source paths,
  rights/sensitivity labels, and caveat metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline data-dictionary metadata only, no command
  execution from report inputs, no raw private data reads, no new data
  adapters, no broker integration, no credentials, no account or portfolio
  data, no live quote feed, no paid-vendor market data, no WebSocket, no
  remote fetch, no order placement, no ranking, no allocation advice, no
  executable advice, no strategy optimization, no production-readiness claim,
  no unsupported redistribution, and no profitability claim.

### Stage 18: Local citation-index report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 18 implementation branch.
- Purpose: add local reviewer-supplied citation labels, local source paths,
  citation purpose, rights notes, and limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline citation-index metadata only, no command
  execution from report inputs, no source-content reads, no raw private data
  reads, no private/proprietary excerpts, no new data adapters, no broker
  integration, no credentials, no account or portfolio data, no live quote
  feed, no paid-vendor market data, no WebSocket, no remote fetch, no order
  placement, no source or security ranking, no allocation advice, no
  executable advice, no strategy optimization, no production-readiness claim,
  no unsupported redistribution, and no profitability claim.

### Stage 19: Local term-glossary report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 19 implementation branch.
- Purpose: add local reviewer-supplied terms, definitions, source paths, usage
  scope, and limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline term-glossary metadata only, no command
  execution from report inputs, no source-content reads, no raw private data
  reads, no private/proprietary excerpts, no new data adapters, no broker
  integration, no credentials, no account or portfolio data, no live quote
  feed, no paid-vendor market data, no WebSocket, no remote fetch, no order
  placement, no term/source/security ranking, no allocation advice, no
  executable advice, no strategy optimization, no production-readiness claim,
  no unsupported redistribution, and no profitability claim.

### Stage 20: Local assumption-register report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 20 implementation branch.
- Purpose: add local reviewer-supplied assumption labels, rationale, source
  paths, scope, and limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline assumption-register metadata only, no command
  execution from report inputs, no source-content reads, no raw private data
  reads, no private/proprietary excerpts, no new data adapters, no broker
  integration, no credentials, no account or portfolio data, no live quote
  feed, no paid-vendor market data, no WebSocket, no remote fetch, no order
  placement, no assumption/term/source/security ranking, no allocation advice,
  no executable advice, no strategy optimization, no production-readiness
  claim, no unsupported redistribution, and no profitability claim.

## Stage 0: Repository foundation

Purpose: establish the package, public positioning, tooling, and safety
boundary.

Deliverables: README, AGENTS guidance, package structure, pytest/Ruff setup,
risk policy, charter, roadmap, and resume narrative.

Acceptance checks: editable install works, `pytest` passes, `ruff check .`
passes, and no credentials or live trading paths exist.

Explicit non-goals: no API clients, no execution, no strategies, no WebSocket,
and no profitability claims.

## Stage 1: Kalshi-style orderbook normalization with fixtures

Purpose: normalize Kalshi-style YES/NO books into canonical YES-side bid/ask
books.

Deliverables: exchange-agnostic core models, Kalshi normalizer, local fixture,
replay script, and deterministic tests.

Acceptance checks: tests cover basic conversion, empty sides, multiple levels,
precision, invalid prices, and locked or crossed books.

Explicit non-goals: no live API calls, no authenticated requests, no order
placement, no WebSocket, and no strategy logic.

## Stage 1.5: Long-running controller and project memory

Purpose: make the repository safe to continue across sessions, branches,
computers, and future `/goal` runs.

Deliverables: changelog, project spec, current handoff, engineering log, repo
map, long-running controller, stage plan, decision log, handoff archive
guidance, and concise AGENTS/README references.

Acceptance checks: required docs exist, `pytest` passes, `ruff check .` passes,
fixture replay works, and Git is initialized on `main` if it was absent.

Explicit non-goals: no REST client, no order placement, no WebSocket, no
strategies, and no normalizer changes except minimal check fixes.

## Stage 2: Read-only Kalshi Demo market-data client

Purpose: add a safe read-only client boundary for Kalshi Demo market data.

Deliverables: local response fixtures, parsing tests, read-only client module,
configuration for demo base URL, error handling, and no secret storage.

Acceptance checks: tests pass without network or credentials, live network use
is optional or explicitly separated, and rate-limit/failure behavior is
documented.

Explicit non-goals: no authenticated trading, no order placement, no WebSocket,
no strategies, and no production endpoints.

## Stage 3: Local replay simulator and data recorder

Purpose: build deterministic offline research infrastructure so future quote
engines, strategy tests, and PnL attribution can run on replayable snapshots
instead of live API calls.

Deliverables: snapshot model, Decimal-safe JSONL read/write/append helpers,
replay session, local fixture-to-snapshot recorder, snapshot replay summary
script, fixture coverage, and limitation notes.

Snapshot schema requirements:

- `schema_version`.
- `exchange`.
- `ticker`.
- observed market-data timestamp.
- local recorded timestamp.
- normalized orderbook.
- source type.
- optional raw payload.
- optional notes and tags.
- no credentials, headers, signatures, tokens, private keys, or secrets.

Recorder requirements:

- Store snapshots as JSONL.
- Preserve `Decimal` price and quantity precision across roundtrips.
- Support write and append behavior.
- Use local fixtures only for fixture conversion.
- Do not commit large generated snapshot files.

Replay requirements:

- Load JSONL snapshots deterministically.
- Strict mode fails on out-of-order observed timestamps.
- Non-strict mode may sort out-of-order snapshots and warn.
- Expose best bid, best ask, spread, mid, bid depth, ask depth, bid level count,
  and ask level count.
- Do not add fill simulation in this stage.

Required scripts:

- `scripts/02_record_fixture_snapshots.py --output <path>` converts committed
  local Kalshi fixtures into JSONL snapshots.
- `scripts/03_replay_snapshots.py --input <path>` reads JSONL snapshots and
  prints a concise metrics table.

Acceptance checks: offline deterministic tests cover JSONL roundtrip, Decimal
precision, malformed JSONL, append behavior, strict replay ordering, replay
metrics, and fixture-to-snapshot conversion. Data output format is documented
and no execution actions are possible.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage3_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage3_snapshots.jsonl
```

Explicit non-goals: no live trading, no strategy optimization, no hidden network
dependencies, no order placement, no authenticated trading, no production
endpoint, no WebSocket, no profitability claims, no secrets, no fill simulation,
and no unsupported data redistribution.

Next-stage boundary: Stage 4 may consume normalized/replayed books to produce
fair-value and dry-run quote objects only. It must not add order placement,
fill simulation, production endpoints, or live trading.

## Stage 4: Fair-value and quote engine dry-run

Purpose: estimate fair value from normalized/replayed orderbook state and
generate inventory-aware dry-run quotes without creating executable orders or
placing trades.

Deliverables: fair-value baseline model, quote engine, inventory-aware quote
skew, spread and tick/price boundary handling, dry-run order-intent objects,
replay-based dry-run script, offline deterministic tests, and limitation notes.

Fair-value baseline requirements:

- Consume a `NormalizedOrderBook` or replay frame.
- Produce a `Decimal` fair value.
- Use deterministic baseline behavior such as midpoint fair value when both
  sides exist.
- Define deterministic fallback behavior for one-sided books.
- Avoid predictive, optimized, or profitability-framed modeling.

Quote generation requirements:

- Generate bid and ask quote candidates from fair value and current orderbook
  state.
- Use `Decimal` for prices, quantities, spread, tick size, inventory, and
  limits.
- Enforce spread constraints.
- Enforce tick/price boundaries inside the binary contract range.
- Keep quote outputs as dry-run objects only.

Inventory-aware skew requirements:

- Accept current inventory or position inputs.
- Skew quotes deterministically to reduce inventory pressure.
- Keep skew bounded and explainable.
- Do not create execution actions.

Dry-run order-intent requirements:

- Produce dry-run candidate intents or quote objects for inspection and tests.
- Do not call any adapter execution method.
- Do not send authenticated requests.
- Do not place, cancel, or modify orders.
- Clearly label outputs as dry-run.

Replay script requirements:

- Add a replay-based dry-run script that reads Stage 3 JSONL snapshots.
- Print a concise table with fair value, quote prices, spread/skew inputs, and
  safety/limitation notes.
- Require local input only; no network calls.

Acceptance checks: offline deterministic tests cover midpoint fair value,
one-sided fallback behavior, quote generation, inventory skew, tick and price
boundary handling, dry-run-only intent output, replay-script behavior, and
out-of-scope execution guards. All prices and quantities use `Decimal`, and
limitations are documented.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage4_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage4_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage4_snapshots.jsonl
```

Explicit non-goals: no order placement, no live execution, no profitability
claims, no optimizer that implies guaranteed performance, no fill simulation,
no PnL attribution, no authenticated trading, no production endpoint, no
WebSocket, and no credentials or secrets.

Next-stage boundary: Stage 5 may add a risk-gated demo execution smoke test
only after the risk checks and blocked-path tests are explicit. Stage 4 must
stop at dry-run quote/intention output.

## Stage 5: Risk-gated demo execution smoke test

Purpose: prove that demo execution actions cannot occur without explicit risk
approval and logging.

Deliverables: risk checks, execution log format, demo-only smoke test path,
blocked-path tests, explicit opt-in configuration, and limitation notes.

Risk-check requirements:

- Every execution candidate must pass a pre-execution risk decision before any
  adapter action can run.
- Risk checks must consume explicit execution mode, instrument or ticker,
  side/action, price, quantity, current position or inventory, and risk limits.
- `LIVE_DISABLED` must reject every execution action.
- Production or non-demo endpoints must be rejected.
- Missing explicit demo opt-in must reject every demo action.
- Size, price-boundary, notional, position, and inventory limits must be
  enforced with `Decimal` values.
- Rejections must be deterministic and explainable through `RiskDecision`
  reasons.
- Risk-approved actions still require structured execution logging.

Blocked-path test requirements:

- Tests must prove `LIVE_DISABLED` cannot place, cancel, or modify orders.
- Tests must prove failed risk limits block execution.
- Tests must prove production endpoints are rejected.
- Tests must prove missing demo opt-in or missing required demo configuration
  blocks execution.
- Tests must prove every attempted execution action is logged, including
  rejected actions.
- Tests must use fake or mocked adapters; no live network calls, credentials, or
  real orders are allowed in unit tests.

Execution log format requirements:

- Logs must be structured and append-friendly, preferably JSONL.
- Each log entry must include timestamp, execution mode, exchange, ticker or
  instrument, requested action, order-intent fields, risk decision, result
  status, error or rejection reason, and a demo/smoke-test marker.
- Logs must not include credentials, headers, signatures, tokens, private keys,
  or raw secret-bearing payloads.
- Every execution attempt, approval, rejection, adapter call, and adapter error
  must be auditable.

Demo-only smoke constraints:

- Any demo execution smoke script must be explicit opt-in and disabled by
  default.
- Demo smoke code must use the Kalshi Demo base URL only.
- Demo smoke code must not support production trading.
- Demo smoke code must not run in tests unless fully mocked.
- Demo smoke output must describe limitations and avoid performance or
  profitability claims.

Required scripts:

- If a script is added, use a Stage 5 script such as
  `scripts/05_demo_execution_smoke.py` with an explicit opt-in flag and safe
  dry-run or fake-adapter mode for local validation.

Acceptance checks: every execution action passes risk checks before adapter
access, `LIVE_DISABLED` cannot place orders, logs are auditable, blocked-path
tests cover rejection paths, tests remain offline and deterministic, and
documentation states demo-only limitations.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage5_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage5_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage5_snapshots.jsonl
```

Explicit non-goals: no production trading, no broad strategy deployment, no
credential storage, no compliance bypass, no WebSocket ingestion, no strategy
optimization, no fill simulation, no PnL attribution, no production endpoint,
no live-trading claims, and no profitability claims.

Next-stage boundary: Stage 6 may connect normalized books, fair value, quote
generation, risk gates, and dry-run/demo loop behavior after Stage 5 proves
execution actions are risk-gated, logged, and blocked when unsafe. Stage 5 must
not implement a market-making loop or broad strategy deployment.

## Stage 6: Inventory-aware demo market maker in dry-run/demo only

Purpose: connect normalized books, fair value, quote generation, risk checks,
and demo/paper execution boundaries in a controlled, finite workflow.

Deliverables: inventory-aware quote adjustments, finite replay-driven
dry-run/demo loop, risk-gated execution request conversion, structured decision
logs, run summaries, offline tests, and limitation notes.

Workflow requirements:

- Consume Stage 3 JSONL snapshots or committed local fixtures by default.
- Reuse Stage 4 fair-value and quote generation; do not add predictive model
  optimization.
- Convert dry-run quote intents into Stage 5 demo execution requests only after
  explicit mode and risk configuration are supplied.
- Process a finite number of replay frames; no daemon, scheduler, infinite
  loop, or live market-making process.
- Keep dry-run mode as the default. Dry-run mode must not call any execution
  adapter.
- Demo mode must require explicit opt-in and must use the Kalshi Demo base URL.
- In this checkpoint, demo execution must remain fake-adapter or mocked unless
  a later separately reviewed stage adds authenticated Demo order placement.
- Do not infer fills from accepted fake/demo requests. Run summaries must
  separate quote candidates, risk approvals, adapter submissions, rejections,
  and fills or PnL assumptions.

Inventory and quoting requirements:

- Accept initial inventory, current position, and risk limits explicitly.
- Use `Decimal` for inventory, position, prices, quantities, limits, and
  notional calculations.
- Apply bounded inventory-aware quote skew through the Stage 4 quote engine.
- Respect binary price bounds, tick-size behavior, minimum spread, and
  configured quote size.
- Maintain an explicit in-memory open-quote state for the finite replay run so
  desired quote candidates can be compared with prior quote state.
- Quote lifecycle decisions must be explicit: generate desired quote
  candidates, compare them with current open quote state, then emit
  place/replace/cancel/hold intents for audit and risk review.
- Replace and cancel intents must remain intent records until they pass the
  Stage 5 risk gate; dry-run mode must never call an adapter.
- Quote churn controls must be deterministic, such as minimum price-change or
  quote-change thresholds before replacement intents are emitted.
- Avoid aggressive liquidity behavior; no quote stuffing, spoofing-like
  behavior, self-trading, wash trading, or misleading liquidity.

Risk and execution-gate requirements:

- Every candidate action must pass through the Stage 5 risk decision before any
  adapter method can run.
- Stage 6 must add or configure explicit run-level controls for maximum
  absolute position, maximum open orders, maximum notional exposure, maximum
  loss, and a kill switch.
- The kill switch must block new place/replace actions, prevent adapter access,
  and log skipped or cancel-intent decisions deterministically.
- The maximum open-orders limit must count both sides of the maintained
  open-quote state and reject or skip additional quote intents when the limit
  would be exceeded.
- `LIVE_DISABLED`, non-demo endpoints, missing demo opt-in, price-boundary,
  size, notional, position, inventory, and daily-loss checks must remain
  enforced.
- Risk rejections must be deterministic and auditable.
- Adapter calls must be impossible in dry-run mode and impossible before risk
  approval in demo mode.
- No credentials, headers, signatures, private keys, tokens, or secret-bearing
  payloads may be logged or required.

Logging and summary requirements:

- Emit structured JSONL records for each frame, quote candidate, risk decision,
  skipped action, rejection, fake/demo adapter submission, and adapter error.
- Include run-level summary output with frame count, quote count, approved
  actions, rejected actions, skipped actions, adapter calls, and limitation
  notes.
- Default generated logs must go to user-provided paths or safe temporary paths
  and must not be committed.
- Logs and summaries must avoid performance or profitability claims.

Required script:

- Add a replay-driven script such as `scripts/06_market_maker_replay.py`.
- Required input: `--input <snapshots.jsonl>`.
- Required output option: `--log-output <path>` with a safe temp default.
- Default behavior: dry-run only, no adapter access.
- Optional fake/demo behavior: an explicit flag such as `--demo-opt-in` may run
  the fake adapter through the Stage 5 risk gate.
- The script must print concise run metrics and safety limitations.

Offline deterministic tests:

- Default dry-run never calls an adapter.
- Explicit demo opt-in can call only a fake or mocked adapter after risk
  approval.
- Missing demo opt-in, `LIVE_DISABLED`, non-demo endpoint, and failed risk
  limits block adapter access and are logged.
- Quote lifecycle tests cover generate, compare, place-intent, replace-intent,
  cancel-intent, hold, and audit-log output.
- Maximum position, maximum open orders, maximum notional, maximum loss, and
  kill-switch controls block unsafe intents deterministically.
- Inventory skew changes quote candidates deterministically.
- Run summaries count frames, quotes, approvals, rejections, skipped actions,
  and adapter calls.
- Tests remain offline with local fixtures or temporary JSONL snapshots; no
  live API calls, credentials, or real orders.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage6_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage6_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage6_snapshots.jsonl
python scripts/05_demo_execution_smoke.py --log-output /tmp/edmn_stage6_execution_smoke.jsonl
python scripts/05_demo_execution_smoke.py --demo-opt-in --log-output /tmp/edmn_stage6_execution_smoke_approved.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage6_snapshots.jsonl --log-output /tmp/edmn_stage6_market_maker.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage6_snapshots.jsonl --demo-opt-in --log-output /tmp/edmn_stage6_market_maker_demo.jsonl
```

Explicit non-goals: no production deployment, no authenticated Kalshi order
placement, no production endpoints, no WebSocket ingestion, no live
market-making daemon, no strategy optimization, no fill simulation, no PnL
attribution, no aggressive liquidity behavior, no spoofing-like behavior, no
self-trading or wash trading, no credentials, no performance guarantees, and no
profitability claims.

Next-stage boundary: Stage 7 may add PnL attribution and research reporting
only after Stage 6 produces bounded run summaries with explicit assumptions.
Stage 6 must not claim fills, PnL, profitability, or production readiness.

## Stage 7: PnL attribution and research report

Purpose: explain simulated or demo results with fees, fills, spread capture,
inventory, and adverse-selection proxies.

Deliverables: attribution model, report template, charts or tables, and
assumption disclosures.

Acceptance checks: reports separate observed results from assumptions, include
fees/slippage/fill limitations, and avoid profitability guarantees.

Explicit non-goals: no marketing claims, no cherry-picked conclusions, and no
production trading.

Scope: consume Stage 6 JSONL decision logs and, optionally, a separately
provided local fill-assumption JSONL fixture. Stage 7 may compute hypothetical
attribution only from explicit assumptions. It must never infer fills from
accepted fake/demo adapter submissions.

Input requirements:

- Required input: one or more Stage 6 market-maker replay JSONL logs.
- Optional input: a local fills/fees fixture with explicit instrument, side,
  price, quantity, fee, observed timestamp, and assumption notes.
- Inputs must be local files only; no network calls, API credentials, exchange
  authentication, or private account data.
- Missing fills must be reported as "no fills supplied"; do not synthesize or
  backfill fills from quote candidates or adapter submissions.
- Use `Decimal` for prices, quantities, fees, cash, notional, and PnL.

Attribution requirements:

- Separate observed Stage 6 counts from hypothetical attribution assumptions:
  frames, quote candidates, risk approvals, rejections, skipped actions,
  adapter submissions, adapter errors, supplied fills, fees, realized PnL,
  inventory, and mark assumptions.
- Attribute PnL components only when explicit input data supports them:
  gross trade PnL, fees, net PnL, inventory change, quoted spread context, and
  simple adverse-selection proxy versus replayed midpoint when available.
- Reports must label all supplied fills, marks, slippage, and adverse-selection
  calculations as assumptions or approximations.
- Reports must avoid profitability guarantees, performance marketing, Sharpe
  ratios, annualization, strategy optimization, ranking, or cherry-picked
  conclusions.
- Empty/no-fill runs must still produce a valid report showing zero supplied
  fills, zero realized PnL, Stage 6 decision counts, and limitation notes.

Required script:

- Add a report script such as `scripts/07_research_report.py`.
- Required input: `--market-maker-log <path>`; allow repeated inputs if simple.
- Optional input: `--fills <fills.jsonl>`.
- Required output option: `--output <path>` for a Markdown report.
- Default behavior must be local/offline and must not call adapters or APIs.
- The report must include limitation notes and must not claim production
  readiness or profitability.

Offline deterministic tests:

- Report generation works for a Stage 6 log with no fills.
- Supplied fill fixture produces deterministic gross/net PnL and fee totals.
- Malformed or secret-like fill fields are rejected.
- Missing fills are not inferred from adapter submissions.
- Report text separates observed counts from assumptions and includes explicit
  limitations.
- Decimal precision is preserved in attribution outputs.
- Tests remain offline and use local temporary JSONL/Markdown files only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage7_snapshots.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage7_snapshots.jsonl --log-output /tmp/edmn_stage7_market_maker.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage7_snapshots.jsonl --demo-opt-in --log-output /tmp/edmn_stage7_market_maker_demo.jsonl
python scripts/07_research_report.py --market-maker-log /tmp/edmn_stage7_market_maker.jsonl --output /tmp/edmn_stage7_report.md
```

Next-stage boundary: Stage 8 may add additional research data adapters or richer
reporting only after Stage 7 proves offline attribution reports with explicit
assumptions. Stage 7 must not add live trading, authenticated execution,
production endpoints, WebSocket ingestion, strategy optimization, or
profitability claims.

## Stage 8: Polymarket US market-data research adapter, if compliant and available

Purpose: explore a second prediction-market data adapter for research only.

Readiness status: clarified for a future fixture-first Polymarket US public
market-data adapter. See `docs/stage8_polymarket_readiness.md`.

Deliverables: compliance/readiness note, Polymarket US public market-data
adapter, local fixtures, parser tests, and docs on availability and limitations.

Allowed scope:

- Use Polymarket US public market-data documentation and local fixtures only.
- Keep any adapter under `src/edmn_trader/adapters/polymarket_us`.
- Keep the adapter read-only, unauthenticated, and market-data only.
- Restrict any future HTTP base URL to the documented Polymarket US public API.
- Convert public market/orderbook-style data into existing exchange-agnostic
  core or replay structures without changing execution behavior.
- Keep tests offline and deterministic.

Acceptance checks:

- No trading path exists.
- No wallet, private key, API key, authenticated endpoint, or account data is
  introduced.
- The international Polymarket endpoint is not used for a U.S. workflow.
- No geoblock, region, platform-rule, or rate-limit bypass exists.
- Adapter code stays separate from core and exchange-specific logic stays under
  `src/edmn_trader/adapters`.
- Docs state availability, compliance assumptions, data-source limits, and
  remaining non-goals.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no Polymarket trading, no bypassing restrictions, no wallet
integration, no authenticated API calls, no WebSocket ingestion, no production
execution, no international Polymarket adapter, no live HTTP smoke by default,
and no profitability claims.

Next-stage boundary: Stage 9 may add U.S. equities research data only after
Stage 8 proves a second prediction-market adapter can remain read-only,
fixture-tested, exchange-contained, and compliance-bound.

## Stage 9: U.S. equities research adapter, paper/research only

Purpose: extend the research architecture toward equities data without enabling
live equities trading.

Readiness status: clarified for a future fixture-first SEC EDGAR public
fundamentals adapter. See `docs/stage9_equities_readiness.md`.

Deliverables: readiness note, SEC EDGAR equities fundamentals adapter, local
fixtures, parser tests, and paper/research documentation.

Allowed scope:

- Use SEC EDGAR public JSON data and local fixtures only.
- Keep any adapter under `src/edmn_trader/adapters/sec_edgar`.
- Keep the adapter read-only, unauthenticated, and fundamentals-only.
- Restrict any future HTTP base URL to `https://data.sec.gov`.
- Require explicit identifying User-Agent configuration for future live HTTP
  access.
- Convert public company facts or company concept data into exchange-agnostic
  research structures.
- Keep tests offline and deterministic.

Acceptance checks:

- No live execution path exists.
- No broker integration, account data, portfolio data, API key, or credential
  is introduced.
- No live quote feed, paid-vendor feed, or proprietary exchange data is used.
- No data redistribution assumption is hidden.
- Adapter code stays separate from core and exchange/source-specific logic
  stays under `src/edmn_trader/adapters`.
- Docs state SEC fair-access assumptions, data-source limits, and remaining
  non-goals.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no live equities orders, no broker integration for
production trading, no credentials in repo, no account or portfolio data, no
live quote feeds, no paid-vendor market data, no strategy optimization, no
production execution, and no claims of guaranteed performance.

Next-stage boundary: a later stage may add richer paper/research reporting only
after Stage 9 proves SEC fundamentals ingestion remains fixture-tested,
read-only, and credential-free.

## Stage 10: Paper research report pack

Purpose: combine existing offline Stage 7 attribution reports and Stage 9 SEC
fundamentals into a paper/research report pack without introducing trading
signals, execution, live feeds, or performance marketing.

Deliverables: report-pack generator, local fixtures, Markdown output, tests,
and limitation notes.

Allowed scope:

- Use local Stage 7 Markdown/JSONL outputs and local SEC fundamentals fixtures
  only.
- Produce an offline Markdown report pack or directory of Markdown files.
- Separate observed run metrics, supplied assumptions, and SEC fundamentals.
- Include source/limitation notes for SEC EDGAR data and any supplied fill
  assumptions.
- Keep all calculations deterministic and `Decimal`-safe when money or numeric
  fundamentals are used.
- Keep tests offline and deterministic.

Acceptance checks:

- Reports do not rank securities, optimize strategies, emit trading signals,
  or claim profitability.
- Reports do not use broker APIs, credentials, account data, portfolio data,
  live quote feeds, paid-vendor feeds, proprietary exchange data, WebSockets, or
  production endpoints.
- Missing optional inputs produce explicit "not supplied" sections instead of
  inferred data.
- Output separates observed facts from assumptions and limitations.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no live equities orders, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no strategy optimization, no security ranking, no allocation
advice, no production execution, and no profitability claims.

Next-stage boundary: later stages may add additional report sections only after
the report pack keeps all data local/offline, assumption-labeled, and
non-executable.

## Stage 11: Additional report sections, local/offline only

Purpose: extend the Stage 10 report pack with additional descriptive Markdown
sections while preserving local/offline inputs, assumption labeling, and
non-executable output.

Deliverables: report-section extension, offline tests, updated Markdown output,
and limitation notes.

Allowed scope:

- Use existing local Stage 6/7/10 outputs, explicit local fill assumptions, and
  committed fixtures only.
- Add descriptive sections such as source inventory, assumption appendix, or
  local-run comparison tables.
- Identify the local source for every new section.
- Label missing optional inputs as not supplied.
- Keep observed metrics, supplied assumptions, SEC fundamentals, and
  limitations separate.

Acceptance checks:

- Reports do not rank securities, recommend allocations, optimize strategies,
  emit executable advice, or claim profitability.
- Reports do not use broker APIs, credentials, account data, portfolio data,
  live quote feeds, paid-vendor feeds, proprietary exchange data, WebSockets, or
  production endpoints.
- New sections are optional-input safe: missing inputs produce explicit
  not-supplied text instead of inferred values.
- Tests remain offline and deterministic.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no new market-data adapters, no live equities orders, no
broker integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no strategy optimization, no security
ranking, no allocation advice, no production execution, and no profitability
claims.

Next-stage boundary: later stages may add new report inputs only after their
data-source rights, offline fixture behavior, and non-executable report
boundaries are clarified first.

## Stage 12: Report input manifest, local/offline only

Purpose: add a local manifest that describes additional report inputs for the
paper report pack without adding new data adapters, remote fetching, or
executable advice.

Deliverables: optional manifest input, Markdown manifest section, offline tests,
and limitation notes.

Allowed scope:

- Use a local manifest file only.
- Manifest entries may describe local paths, input kind, display label,
  rights/redistribution note, assumption scope, and required/optional status.
- Keep the manifest descriptive and non-executable.
- Reject secret-like fields and unsupported remote URLs.
- Label missing optional manifest inputs as not supplied.
- Keep observed metrics, supplied assumptions, SEC fundamentals, source
  inventory, manifest inputs, and limitations separate.

Acceptance checks:

- Reports do not rank securities, recommend allocations, optimize strategies,
  emit executable advice, or claim profitability.
- Reports do not use broker APIs, credentials, account data, portfolio data,
  live quote feeds, paid-vendor feeds, proprietary exchange data, WebSockets,
  production endpoints, or unsupported redistribution.
- Manifest parsing is offline and deterministic.
- Missing optional manifest inputs produce explicit not-supplied text instead
  of inferred values.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no new market-data adapters, no live equities orders, no
broker integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no WebSockets, no production endpoints, no
strategy optimization, no security ranking, no allocation advice, no executable
advice, no unsupported data redistribution, and no profitability claims.

Next-stage boundary: later stages may add concrete new input kinds only after
each input kind's data-source rights, offline fixture behavior, and
non-executable report boundaries are clarified first.

## Stage 13: Local run-comparison report input, local/offline only

Purpose: clarify the first concrete new report-input kind after the Stage 12
manifest: a local run-comparison input that describes multiple already
generated project outputs without fetching data, ranking assets, optimizing
strategies, or producing executable advice.

Deliverables: Stage 13 implementation may add a `local_run_comparison` input
kind to the report-input manifest, parse a local comparison descriptor, render
a descriptive report section, add offline tests, and update limitation notes.

Allowed scope:

- Use local files generated by existing project scripts only, such as Stage 6
  market-maker replay logs, Stage 7 research reports, Stage 10/12 report-pack
  outputs, or a local comparison descriptor that points to those files.
- Treat the comparison descriptor as metadata about local outputs, not as a
  remote data source or private-data ingestion path.
- Compare only descriptive run metadata and observed local-output facts, such
  as supplied input labels, run names, generated file paths, observed decision
  counts, not-supplied inputs, and limitation text.
- Preserve separation between observed counts, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, and limitations.
- Label missing optional comparison inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The comparison input does not read secrets, account data, portfolio data,
  private brokerage exports, raw private datasets, live quote feeds,
  paid-vendor data, proprietary exchange data, or production endpoints.
- The output does not rank securities, recommend allocations, optimize
  strategies, select a best run, emit executable advice, or claim
  profitability.
- Missing optional comparison inputs produce explicit not-supplied text instead
  of inferred values.
- Tests use local fixtures or locally generated project outputs only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote feeds,
no paid-vendor market data, no WebSockets, no production endpoints, no strategy
optimization, no security ranking, no allocation advice, no executable advice,
no unsupported data redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local run-comparison input kind
only within the local/offline report-pack path and must not add any new data
adapter, remote fetch, trading endpoint, ranking, allocation, optimization, or
executable-advice behavior.

## Stage 14: Local validation-summary report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 13: a local
validation-summary input that describes already-run local checks and generated
artifacts for a report pack without running commands, fetching data, ranking
runs, or producing executable advice.

Deliverables: Stage 14 implementation may add a `local_validation_summary`
input kind to the report-input manifest, parse a local validation descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as metadata about checks the user already ran, not as an
  instruction to execute commands or inspect private data contents.
- Describe only command labels, pass/fail/skipped status, local artifact paths,
  observed timestamps, and limitation notes.
- Reject remote URLs and secret-like fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  and limitations.
- Label missing optional validation-summary inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, open subprocesses, read secrets,
  read account data, read portfolio data, fetch remote data, use live feeds, or
  inspect paid-vendor/proprietary datasets.
- The output does not rank securities, recommend allocations, optimize
  strategies, select a best run, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional validation-summary inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no new
market-data adapters, no remote fetching, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no WebSockets, no production endpoints, no strategy optimization,
no security ranking, no allocation advice, no executable advice, no production
readiness claim, no unsupported data redistribution, and no profitability
claims.

Next-stage boundary: implementation may add the local validation-summary input
kind only within the local/offline report-pack path and must not add command
execution, remote fetches, new adapters, production endpoints, ranking,
allocation, optimization, executable advice, or production-readiness claims.

## Stage 15: Local review-notes report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 14: a local
review-notes input that records human review notes, caveats, and follow-up
questions for a report pack without reading private data contents, fetching
data, ranking runs, or producing executable advice.

Deliverables: Stage 15 implementation may add a `local_review_notes` input kind
to the report-input manifest, parse a local review-notes descriptor, render a
descriptive report section, add offline tests, and update limitation notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied metadata, not as a data-ingestion
  or recommendation path.
- Describe only note labels, local source paths, note text, optional follow-up
  questions, and limitation notes.
- Reject remote URLs and secret-like fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, and limitations.
- Label missing optional review-notes inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, read secrets, read account data,
  read portfolio data, fetch remote data, use live feeds, inspect paid-vendor
  or proprietary datasets, or infer private data from referenced files.
- The output does not rank securities, recommend allocations, optimize
  strategies, select a best run, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional review-notes inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no new
market-data adapters, no remote fetching, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no WebSockets, no production endpoints, no strategy optimization,
no security ranking, no allocation advice, no executable advice, no production
readiness claim, no unsupported data redistribution, and no profitability
claims.

Next-stage boundary: implementation may add the local review-notes input kind
only within the local/offline report-pack path and must not add command
execution, remote fetches, new adapters, production endpoints, ranking,
allocation, optimization, executable advice, or production-readiness claims.

## Stage 16: Local methodology-notes report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 15: a local
methodology-notes input that records reviewer-supplied methodology context,
assumption descriptions, and known caveats for a report pack without reading
private data contents, fetching data, ranking runs, or producing executable
advice.

Deliverables: Stage 16 implementation may add a `local_methodology_notes` input
kind to the report-input manifest, parse a local methodology-notes descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied methodology metadata, not as a data
  ingestion, validation, or recommendation path.
- Describe only method labels, local source paths, methodology text,
  assumption scope, and limitation notes.
- Reject remote URLs and secret-like fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, and limitations.
- Label missing optional methodology-notes inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, read secrets, read account data,
  read portfolio data, fetch remote data, use live feeds, inspect paid-vendor
  or proprietary datasets, or infer private data from referenced files.
- The output does not rank securities, recommend allocations, optimize
  strategies, select a best run, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional methodology-notes inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no new
market-data adapters, no remote fetching, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no WebSockets, no production endpoints, no strategy optimization,
no security ranking, no allocation advice, no executable advice, no production
readiness claim, no unsupported data redistribution, and no profitability
claims.

Next-stage boundary: implementation may add the local methodology-notes input
kind only within the local/offline report-pack path and must not add command
execution, remote fetches, new adapters, production endpoints, ranking,
allocation, optimization, executable advice, or production-readiness claims.

## Stage 17: Local data-dictionary report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 16: a local
data-dictionary input that records reviewer-supplied field definitions, units,
source paths, rights/sensitivity labels, and caveats for report-pack inputs
without reading raw local data contents, fetching data, ranking fields, or
producing executable advice.

Deliverables: Stage 17 implementation may add a `local_data_dictionary` input
kind to the report-input manifest, parse a local data-dictionary descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied field metadata, not as raw data
  ingestion, schema enforcement, validation execution, or recommendation logic.
- Describe only field labels, local source paths, data type labels, units,
  definitions, rights/sensitivity labels, and limitation notes.
- Reject remote URLs and secret-like fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, and limitations.
- Label missing optional data-dictionary inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, read secrets, read raw private
  data contents, read account data, read portfolio data, fetch remote data, use
  live feeds, inspect paid-vendor or proprietary datasets, or infer private
  values from referenced files.
- The output does not rank securities, recommend allocations, optimize
  strategies, select a best field/source/run, emit executable advice, imply
  production readiness, or claim profitability.
- Missing optional data-dictionary inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no raw private
data reads, no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote feeds,
no paid-vendor market data, no WebSockets, no production endpoints, no strategy
optimization, no security ranking, no allocation advice, no executable advice,
no production readiness claim, no unsupported data redistribution, and no
profitability claims.

Next-stage boundary: implementation may add the local data-dictionary input
kind only within the local/offline report-pack path and must not add command
execution, raw local data reads, remote fetches, new adapters, production
endpoints, ranking, allocation, optimization, executable advice, or
production-readiness claims.

## Stage 18: Local citation-index report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 17: a local
citation-index input that records reviewer-supplied citation labels, local
source paths, citation purpose, rights notes, and limitation notes for report
packs without reading source contents, embedding private/proprietary excerpts,
fetching remote data, ranking sources, or producing executable advice.

Deliverables: Stage 18 implementation may add a `local_citation_index` input
kind to the report-input manifest, parse a local citation-index descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied citation metadata, not as document
  ingestion, source-content extraction, validation execution, or
  recommendation logic.
- Describe only citation labels, local source paths, citation purpose,
  rights notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, and limitations.
- Label missing optional citation-index inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, read secrets, read source
  contents, read raw private data contents, read account data, read portfolio
  data, fetch remote data, use live feeds, inspect paid-vendor or proprietary
  datasets, or infer private values from referenced files.
- The output does not include private/proprietary excerpts, rank sources or
  securities, recommend allocations, optimize strategies, select a best
  field/source/run, emit executable advice, imply production readiness, or
  claim profitability.
- Missing optional citation-index inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no source-content
reads, no raw private data reads, no private/proprietary excerpts, no new
market-data adapters, no remote fetching, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no WebSockets, no production endpoints, no strategy optimization,
no security ranking, no source ranking, no allocation advice, no executable
advice, no production readiness claim, no unsupported data redistribution, and
no profitability claims.

Next-stage boundary: implementation may add the local citation-index input
kind only within the local/offline report-pack path and must not add command
execution, source-content reads, raw local data reads, remote fetches, new
adapters, production endpoints, ranking, allocation, optimization, executable
advice, or production-readiness claims.

## Stage 19: Local term-glossary report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 18: a local
term-glossary input that records reviewer-supplied terms, definitions, source
paths, usage scope, and limitation notes for report packs without reading
source contents, fetching remote data, ranking terms, or producing executable
advice.

Deliverables: Stage 19 implementation may add a `local_term_glossary` input
kind to the report-input manifest, parse a local term-glossary descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied terminology metadata, not as source
  ingestion, ontology enforcement, validation execution, or recommendation
  logic.
- Describe only term labels, local source paths, definitions, usage scope, and
  limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, and limitations.
- Label missing optional term-glossary inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, read secrets, read source
  contents, read raw private data contents, read account data, read portfolio
  data, fetch remote data, use live feeds, inspect paid-vendor or proprietary
  datasets, or infer private values from referenced files.
- The output does not include private/proprietary excerpts, rank terms,
  sources, or securities, recommend allocations, optimize strategies, emit
  executable advice, imply production readiness, or claim profitability.
- Missing optional term-glossary inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no source-content
reads, no raw private data reads, no private/proprietary excerpts, no new
market-data adapters, no remote fetching, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no WebSockets, no production endpoints, no strategy optimization,
no security ranking, no source ranking, no term ranking, no allocation advice,
no executable advice, no production readiness claim, no unsupported data
redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local term-glossary input kind
only within the local/offline report-pack path and must not add command
execution, source-content reads, raw local data reads, remote fetches, new
adapters, production endpoints, ranking, allocation, optimization, executable
advice, or production-readiness claims.

## Stage 20: Local assumption-register report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 19: a local
assumption-register input that records reviewer-supplied assumption labels,
rationale, source paths, scope, and limitation notes for report packs without
reading source contents, fetching remote data, ranking assumptions, or
producing executable advice.

Deliverables: Stage 20 implementation may add a `local_assumption_register`
input kind to the report-input manifest, parse a local assumption-register
descriptor, render a descriptive report section, add offline tests, and update
limitation notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied assumption metadata, not as source
  ingestion, model configuration, validation execution, or recommendation
  logic.
- Describe only assumption labels, local source paths, rationale, scope, and
  limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata, and
  limitations.
- Label missing optional assumption-register inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, read secrets, read source
  contents, read raw private data contents, read account data, read portfolio
  data, fetch remote data, use live feeds, inspect paid-vendor or proprietary
  datasets, or infer private values from referenced files.
- The output does not include private/proprietary excerpts, rank assumptions,
  terms, sources, or securities, recommend allocations, optimize strategies,
  emit executable advice, imply production readiness, or claim profitability.
- Missing optional assumption-register inputs produce explicit not-supplied
  text instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no source-content
reads, no raw private data reads, no private/proprietary excerpts, no new
market-data adapters, no remote fetching, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no WebSockets, no production endpoints, no strategy optimization,
no security ranking, no source ranking, no term ranking, no assumption ranking,
no allocation advice, no executable advice, no production readiness claim, no
unsupported data redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local assumption-register input
kind only within the local/offline report-pack path and must not add command
execution, source-content reads, raw local data reads, remote fetches, new
adapters, production endpoints, ranking, allocation, optimization, executable
advice, or production-readiness claims.

## Stage 21: Local coverage-matrix report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 20: a local
coverage-matrix input that records reviewer-supplied mappings between report
sections, local input descriptors, validation labels, source paths, and
limitation notes without executing checks, reading source contents, fetching
remote data, ranking coverage, or producing executable advice.

Deliverables: Stage 21 implementation may add a `local_coverage_matrix` input
kind to the report-input manifest, parse a local coverage-matrix descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied coverage metadata, not as source
  ingestion, test execution, validation enforcement, scoring, or recommendation
  logic.
- Describe only report section labels, local source paths, input labels,
  validation labels, coverage notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, and limitations.
- Label missing optional coverage-matrix inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs, read
  secrets, read source contents, read raw private data contents, read account
  data, read portfolio data, fetch remote data, use live feeds, inspect
  paid-vendor or proprietary datasets, or infer private values from referenced
  files.
- The output does not include private/proprietary excerpts, score or rank
  coverage, assumptions, terms, sources, or securities, recommend allocations,
  optimize strategies, emit executable advice, imply production readiness, or
  claim profitability.
- Missing optional coverage-matrix inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no source-content reads, no raw private data
reads, no private/proprietary excerpts, no new market-data adapters, no remote
fetching, no broker integration, no credentials, no account or portfolio data,
no live quote feeds, no paid-vendor market data, no WebSockets, no production
endpoints, no strategy optimization, no coverage scoring, no security ranking,
no source ranking, no allocation advice, no executable advice, no production
readiness claim, no unsupported data redistribution, and no profitability
claims.

Next-stage boundary: implementation may add the local coverage-matrix input
kind only within the local/offline report-pack path and must not add command
execution, validation execution, source-content reads, raw local data reads,
remote fetches, new adapters, production endpoints, ranking, allocation,
optimization, executable advice, or production-readiness claims.
