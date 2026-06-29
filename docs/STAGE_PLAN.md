# Stage Plan

## Completed stage record

These records summarize the locally completed stages through Stage 37 venue
fee model scaffold. They are intended as a durable audit map;
implementation details remain in the source, tests, changelog, engineering
log, and handoff archive.

Report-input metadata expansion from Stages 11 through 34 remains preserved as
maintenance-only documentation/report-pack work. The active product direction
is now narrow same-market YES/NO complement parity research, not continued
addition of small report-input metadata kinds.

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
- Commit: `59467cdaca11735b3bb1c64d5207c8252def3846` on `main`.
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

### Stage 21: Local coverage-matrix report input, local/offline only

- Status: complete.
- Commit: `a8a63eef772bb934a7b030b4cbae92c9ff5d1b80` on `main`.
- Purpose: add local reviewer-supplied mappings between report sections, local
  inputs, validation labels, source paths, coverage notes, and limitations.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline coverage-matrix metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  source-content reads, no raw private data reads, no private/proprietary
  excerpts, no new data adapters, no broker integration, no credentials, no
  account or portfolio data, no live quote feed, no paid-vendor market data,
  no WebSocket, no remote fetch, no order placement, no coverage/source/security
  ranking, no allocation advice, no executable advice, no strategy
  optimization, no production-readiness claim, no unsupported redistribution,
  and no profitability claim.

### Stage 22: Local reproducibility-checklist report input, local/offline only

- Status: complete.
- Commit: `5a20668a021400de15c3aaf30e8ea7f1889f79a1` on `main`.
- Purpose: add local reviewer-supplied reproduction step labels, artifact
  paths, command labels, environment labels, expected output labels, and
  limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline reproducibility metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  artifact-content reads, no source-content reads, no raw private data reads,
  no private/proprietary excerpts, no local environment verification, no output
  verification, no new data adapters, no broker integration, no credentials, no
  account or portfolio data, no live quote feed, no paid-vendor market data,
  no WebSocket, no remote fetch, no order placement, no reproducibility/
  coverage/source/security ranking, no allocation advice, no executable advice,
  no strategy optimization, no production-readiness claim, no unsupported
  redistribution, and no profitability claim.

### Stage 23: Local risk-review report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 23 implementation branch.
- Purpose: add local reviewer-supplied risk-control labels, boundary labels,
  mitigation notes, review status labels, local evidence paths, and limitation
  metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline risk-review metadata only, no command execution
  from report inputs, no validation execution from report inputs, no policy
  evaluation, no risk-check execution, no order placement, no evidence-content
  reads, no source-content reads, no raw private data reads, no
  private/proprietary excerpts, no local environment verification, no output
  verification, no new data adapters, no broker integration, no credentials, no
  account or portfolio data, no live quote feed, no paid-vendor market data,
  no WebSocket, no remote fetch, no risk/reproducibility/coverage/source/
  security ranking, no allocation advice, no executable advice, no strategy
  optimization, no production-readiness claim, no unsupported redistribution,
  and no profitability claim.

### Stage 24: Local data-rights-review report input, local/offline only

- Status: complete.
- Commit: `7c0d3e9` (merged via PR #53 at `4e836ad`).
- Purpose: add local reviewer-supplied data labels, rights status labels,
  permitted-use notes, restriction notes, local evidence paths, and limitation
  metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its data-source rights, offline fixture behavior, and
  non-executable report boundaries are clarified first.
- Safety status: local/offline data-rights metadata only, no command execution
  from report inputs, no validation execution from report inputs, no legal
  advice, no legal-rights determination, no license verification, no
  redistribution decision, no policy evaluation, no evidence-content reads, no
  source-content reads, no raw private data reads, no private/proprietary
  excerpts, no local environment verification, no output verification, no new
  data adapters, no broker integration, no credentials, no account or portfolio
  data, no live quote feed, no paid-vendor market data, no WebSocket, no remote
  fetch, no rights/risk/reproducibility/coverage/source/security ranking, no
  allocation advice, no executable advice, no strategy optimization, no
  production-readiness claim, no unsupported redistribution, and no
  profitability claim.

### Stage 25: Local artifact-inventory report input, local/offline only

- Status: complete.
- Commit: `dabd479` (merged via PR #56 at `4378902`).
- Purpose: add local reviewer-supplied generated artifact labels, artifact type
  labels, local paths, generation-source labels, intended report-use notes, and
  limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries, and
  artifact/source-content handling are clarified first.
- Safety status: local/offline artifact-inventory metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  artifact-content reads, no output verification, no local environment
  verification, no evidence-content reads, no source-content reads, no raw
  private data reads, no private/proprietary excerpts, no new data adapters, no
  broker integration, no credentials, no account or portfolio data, no live
  quote feed, no paid-vendor market data, no WebSocket, no remote fetch, no
  artifact/rights/risk/reproducibility/coverage/source/security ranking, no
  allocation advice, no executable advice, no strategy optimization, no
  production-readiness claim, no unsupported redistribution, and no
  profitability claim.

### Stage 26: Local appendix-index report input, local/offline only

- Status: complete.
- Commit: `2e13507` (merged via PR #59 at `f532486`).
- Purpose: add local reviewer-supplied appendix entry labels, report section
  labels, local artifact paths, appendix purpose notes, and limitation
  metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries, and
  artifact/source-content handling are clarified first.
- Safety status: local/offline appendix-index metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  artifact-content reads, no output verification, no local environment
  verification, no distribution approval, no evidence-content reads, no
  source-content reads, no raw private data reads, no private/proprietary
  excerpts, no new data adapters, no broker integration, no credentials, no
  account or portfolio data, no live quote feed, no paid-vendor market data, no
  WebSocket, no remote fetch, no appendix/artifact/rights/risk/reproducibility/
  coverage/source/security ranking, no allocation advice, no executable
  advice, no strategy optimization, no production-readiness claim, no
  unsupported redistribution, and no profitability claim.

### Stage 27: Local limitation-register report input, local/offline only

- Status: complete.
- Commit: `efdfe86` (merged via PR #61 at `3188bd0`).
- Purpose: add local reviewer-supplied limitation labels, affected report
  section labels, local evidence or artifact paths, scope notes, mitigation
  notes, and limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries, and
  artifact/evidence/source-content handling are clarified first.
- Safety status: local/offline limitation-register metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  artifact-content reads, no evidence-content reads, no source-content reads,
  no output verification, no local environment verification, no distribution
  approval, no raw private data reads, no private/proprietary excerpts, no new
  data adapters, no broker integration, no credentials, no account or portfolio
  data, no live quote feed, no paid-vendor market data, no WebSocket, no remote
  fetch, no limitation/appendix/artifact/rights/risk/reproducibility/coverage/
  source/security ranking, no allocation advice, no executable advice, no
  strategy optimization, no production-readiness claim, no unsupported
  redistribution, and no profitability claim.

### Stage 28: Local open-questions report input, local/offline only

- Status: complete.
- Commit: `c9934f4` (merged via PR #64 at `5cf9281`).
- Purpose: add local reviewer-supplied open question labels, affected report
  section labels, local reference paths, owner labels, status labels, and
  limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries, and
  artifact/evidence/source-content handling are clarified first.
- Safety status: local/offline open-question metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  artifact-content reads, no evidence-content reads, no source-content reads,
  no output verification, no local environment verification, no decision
  approval, no raw private data reads, no private/proprietary excerpts, no new
  data adapters, no broker integration, no credentials, no account or portfolio
  data, no live quote feed, no paid-vendor market data, no WebSocket, no remote
  fetch, no question/limitation/appendix/artifact/rights/risk/reproducibility/
  coverage/source/security ranking, no allocation advice, no executable
  advice, no strategy optimization, no production-readiness claim, no
  unsupported redistribution, and no profitability claim.

### Stage 29: Local decision-log report input, local/offline only

- Status: complete.
- Commit: `2261ca4` (merged via PR #67 at `eedd089`).
- Purpose: add local reviewer-supplied decision labels, decision context
  labels, local reference paths, owner labels, status labels, rationale notes,
  and limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries, and
  artifact/evidence/source-content handling are clarified first.
- Safety status: local/offline decision-log metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  artifact-content reads, no evidence-content reads, no source-content reads,
  no output verification, no local environment verification, no decision
  approval, no raw private data reads, no private/proprietary excerpts, no new
  data adapters, no broker integration, no credentials, no account or portfolio
  data, no live quote feed, no paid-vendor market data, no WebSocket, no remote
  fetch, no decision/question/limitation/appendix/artifact/rights/risk/
  reproducibility/coverage/source/security ranking, no allocation advice, no
  executable advice, no strategy optimization, no production-readiness claim,
  no unsupported redistribution, and no profitability claim.

### Stage 30: Local follow-up register report input, local/offline only

- Status: complete.
- Commit: `220b21e` (merged via PR #69 at `6cb9a79`).
- Purpose: add local reviewer-supplied follow-up labels, related report
  section labels, local reference paths, owner labels, status labels, tracking
  notes, and limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries, and
  artifact/evidence/source-content handling are clarified first.
- Safety status: local/offline follow-up metadata only, no command execution
  from report inputs, no validation execution from report inputs, no follow-up
  execution, no artifact-content reads, no evidence-content reads, no
  source-content reads, no output verification, no local environment
  verification, no decision approval, no raw private data reads, no
  private/proprietary excerpts, no new data adapters, no broker integration, no
  credentials, no account or portfolio data, no live quote feed, no paid-vendor
  market data, no WebSocket, no remote fetch, no follow-up/decision/question/
  limitation/appendix/artifact/rights/risk/reproducibility/coverage/source/
  security ranking, no allocation advice, no executable advice, no strategy
  optimization, no production-readiness claim, no unsupported redistribution,
  and no profitability claim.

### Stage 31: Local version-notes report input, local/offline only

- Status: complete.
- Commit: `edf1110` (merged via PR #72 at `1baf281`).
- Purpose: add local reviewer-supplied report version labels, local artifact
  paths, change-summary labels, owner labels, status labels, and limitation
  metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries, and
  artifact/evidence/source-content handling are clarified first.
- Safety status: local/offline version-note metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  follow-up execution, no artifact-content reads, no evidence-content reads, no
  source-content reads, no output verification, no local environment
  verification, no distribution approval, no decision approval, no raw private
  data reads, no private/proprietary excerpts, no new data adapters, no broker
  integration, no credentials, no account or portfolio data, no live quote
  feed, no paid-vendor market data, no WebSocket, no remote fetch, no version/
  follow-up/decision/question/limitation/appendix/artifact/rights/risk/
  reproducibility/coverage/source/security ranking, no allocation advice, no
  executable advice, no strategy optimization, no production-readiness claim,
  no unsupported redistribution, and no profitability claim.

### Stage 32: Local distribution-checklist report input, local/offline only

- Status: complete.
- Commit: `04a378e` (merged via PR #75 at `85d06af`).
- Purpose: add local reviewer-supplied distribution item labels, related
  artifact paths, readiness status labels, owner labels, review notes, and
  limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries,
  distribution/rights boundaries, and artifact/evidence/source-content
  handling are clarified first.
- Safety status: local/offline distribution-checklist metadata only, no
  command execution from report inputs, no validation execution from report
  inputs, no follow-up execution, no artifact-content reads, no
  evidence-content reads, no source-content reads, no output verification, no
  local environment verification, no distribution approval, no rights or
  license verification, no decision approval, no raw private data reads, no
  private/proprietary excerpts, no new data adapters, no broker integration,
  no credentials, no account or portfolio data, no live quote feed, no
  paid-vendor market data, no WebSocket, no remote fetch, no distribution/
  version/follow-up/decision/question/limitation/appendix/artifact/rights/
  risk/reproducibility/coverage/source/security ranking, no allocation advice,
  no executable advice, no strategy optimization, no production-readiness
  claim, no unsupported redistribution, and no profitability claim.

### Stage 33: Local handoff-notes report input, local/offline only

- Status: complete.
- Commit: `3dbf631` (merged via PR #77 at `1395484`).
- Purpose: add local reviewer-supplied handoff labels, related artifact paths,
  recipient or owner labels, status labels, handoff notes, and limitation
  metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: compact governance audit is due after this third
  completed checkpoint since the last audit.
- Safety status: local/offline handoff-note metadata only, no command execution
  from report inputs, no validation execution from report inputs, no follow-up
  execution, no artifact-content reads, no evidence-content reads, no
  source-content reads, no output verification, no local environment
  verification, no distribution approval, no rights or license verification,
  no decision approval, no raw private data reads, no private/proprietary
  excerpts, no new data adapters, no broker integration, no credentials, no
  account or portfolio data, no live quote feed, no paid-vendor market data,
  no WebSocket, no remote fetch, no handoff/distribution/version/follow-up/
  decision/question/limitation/appendix/artifact/rights/risk/reproducibility/
  coverage/source/security ranking, no allocation advice, no executable
  advice, no strategy optimization, no production-readiness claim, no
  unsupported redistribution, and no profitability claim.

### Stage 34: Local archive-notes report input, local/offline only

- Status: complete.
- Commit: pending on the Stage 34 implementation branch.
- Purpose: add local reviewer-supplied archive labels, related artifact paths,
  archive status labels, owner labels, archive notes, and limitation metadata.
- Files/modules changed: `src/edmn_trader/scripts/paper_report_pack.py`,
  `tests/test_paper_report_pack.py`, and documentation updates.
- Validation commands: `pytest tests/test_paper_report_pack.py`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: later stages may add another concrete report-input kind
  only after its offline behavior, non-executable report boundaries, file
  operation boundaries, retention-policy boundaries, and
  artifact/evidence/source-content handling are clarified first.
- Safety status: local/offline archive-note metadata only, no command
  execution from report inputs, no validation execution from report inputs, no
  follow-up execution, no file movement or deletion, no retention-policy
  decision, no artifact-content reads, no evidence-content reads, no
  source-content reads, no output verification, no local environment
  verification, no distribution approval, no rights or license verification,
  no decision approval, no raw private data reads, no private/proprietary
  excerpts, no new data adapters, no broker integration, no credentials, no
  account or portfolio data, no live quote feed, no paid-vendor market data,
  no WebSocket, no remote fetch, no archive/handoff/distribution/version/
  follow-up/decision/question/limitation/appendix/artifact/rights/risk/
  reproducibility/coverage/source/security ranking, no allocation advice, no
  executable advice, no strategy optimization, no production-readiness claim,
  no unsupported redistribution, and no profitability claim.

### Stage 35: Arbitrage roadmap reset

- Status: complete.
- Commit: pending on the complement-arbitrage candidate branch.
- Purpose: redirect the active product roadmap from report-input metadata
  expansion to same-market YES/NO complement parity research.
- Files/modules changed: `docs/ARBITRAGE_ROADMAP.md` and documentation
  updates.
- Validation commands: `pytest`, `ruff check .`, and `git diff --check`.
- Next-stage boundary: Stage 36 may add deterministic offline complement
  candidate schema and tests only.
- Safety status: roadmap/docs-only reset, no live API calls, no authenticated
  requests, no WebSockets, no credentials, no order placement, no production
  execution, no broker integration, no strategy optimization, no investment
  advice, and no profitability claims.

### Stage 36: Complement arbitrage candidate schema

- Status: complete.
- Commit: pending on the complement-arbitrage candidate branch.
- Purpose: add the first deterministic offline candidate model for
  same-market YES/NO complement parity research.
- Files/modules changed: `src/edmn_trader/arb/complement.py`,
  `src/edmn_trader/arb/__init__.py`, `tests/test_complement_arb.py`, and
  documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, and `git diff --check`.
- Next-stage boundary: Stage 37 may add a venue fee model scaffold only; it
  must not add live data, WebSockets, credentials, authenticated requests,
  order placement, wallets, production endpoints, strategy optimization,
  investment advice, or profitability claims.
- Safety status: Decimal-only offline candidate metadata, no live API calls,
  no authenticated requests, no WebSockets, no credentials, no order
  placement, no production execution, no broker integration, no strategy
  optimization, no investment advice, and no profitability claims.

### Stage 37: Venue fee model scaffold

- Status: complete.
- Commit: pending on the Stage 37 fee model branch.
- Purpose: make complement-arbitrage fee assumptions explicit,
  venue-specific, Decimal-only, and conservative before any scanner work.
- Files/modules changed: `src/edmn_trader/fees/base.py`,
  `src/edmn_trader/fees/kalshi.py`,
  `src/edmn_trader/fees/polymarket_us.py`,
  `src/edmn_trader/fees/__init__.py`,
  `src/edmn_trader/arb/complement.py`, `tests/test_fee_models.py`, and
  documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/01_replay_orderbook_fixture.py`, and
  `git diff --check`.
- Next-stage boundary: Stage 38 may add an offline complement scanner only; it
  must not add live data, WebSockets, credentials, authenticated requests,
  order placement, wallets, production endpoints, strategy optimization,
  investment advice, executable advice, or profitability claims.
- Safety status: offline fee estimate metadata only, no live fee lookup, no
  network calls, no WebSockets, no credentials, no authenticated requests, no
  wallets, no order placement, no production endpoints, no LLM trading agent,
  no strategy optimization, no investment advice, and no profitability claims.

### Stage 38: Offline complement scanner

- Status: complete.
- Commit: pending on the Stage 38 offline scanner branch.
- Purpose: scan safe local fixture or existing snapshot-style orderbook inputs
  through the Stage 36 complement candidate model and Stage 37 fee estimate
  scaffold, then emit deterministic JSONL and Markdown research reports.
- Files/modules changed: `src/edmn_trader/arb/scanner.py`,
  `src/edmn_trader/scripts/scan_complement_arb.py`,
  `scripts/23_scan_complement_arb.py`, `tests/test_complement_scanner.py`,
  `docs/complement_scanner.md`, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/23_scan_complement_arb.py --input
  /tmp/edmn_stage38_fixture.json --jsonl-output
  /tmp/edmn_stage38_candidates.jsonl --markdown-output
  /tmp/edmn_stage38_summary.md`, `python
  scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: Stage 39 may add a live event schema and mocked
  WebSocket recorder harness only; it must not add real network connections,
  credentials, authenticated requests, wallets, order placement, production
  endpoints, strategy optimization, investment advice, or profitability claims.
- Safety status: offline scanner and report writer only, no live fee lookup,
  no network calls, no WebSockets, no credentials, no authenticated requests,
  no wallets, no order placement, no production endpoints, no LLM trading
  agent, no strategy optimization, no investment advice, no executable order
  intents, and no profitability claims.

### Stage 39: Live event schema and mocked WebSocket harness

- Status: complete.
- Commit: pending on the Stage 39 mocked recorder branch.
- Purpose: define a durable read-only live market-data event schema and a
  mocked WebSocket-style recorder harness before any real live connection code.
- Files/modules changed: `src/edmn_trader/data/live_events.py`,
  `src/edmn_trader/data/payload_safety.py`,
  `src/edmn_trader/scripts/mock_live_event_recorder.py`,
  `scripts/39_mock_live_event_recorder.py`, `tests/test_live_event_recorder.py`,
  and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/39_mock_live_event_recorder.py --input
  /tmp/edmn_stage39_events.json --output /tmp/edmn_stage39_events.jsonl`,
  `python scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: Stage 40 may add the Kalshi live read-only recorder
  implementation only. It must default disabled/offline, require explicit
  `--live-readonly-opt-in`, use mocked tests, and must not execute real live
  venue connections during validation.
- Safety status: schema and mocked recorder harness only, no real network
  connection, no credentials, no credential prompts, no authenticated requests,
  no user-order channel, no order placement imports, no production endpoints,
  no strategy optimization, no investment advice, and no profitability claims.

### Stage 40: Kalshi live read-only recorder

- Status: complete.
- Commit: `a195dab` (merged via PR #90).
- Purpose: add a guarded Kalshi Demo read-only orderbook recorder that writes
  raw live-event JSONL and normalized snapshot JSONL through mocked-testable
  code paths.
- Files/modules changed: `src/edmn_trader/adapters/kalshi/readonly_recorder.py`,
  `src/edmn_trader/scripts/kalshi_readonly_recorder.py`,
  `scripts/40_kalshi_readonly_recorder.py`,
  `tests/test_kalshi_readonly_recorder.py`, Stage 39 live-event source-type
  support, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/40_kalshi_readonly_recorder.py --help`,
  `python scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: Stage 41 may add the Polymarket market-channel recorder
  only. It must be market channel only, default disabled/offline, require
  explicit `--live-readonly-opt-in`, use mocked tests, and must not add user
  channel, wallet, signing, or execution behavior.
- Safety status: guarded read-only Demo recorder only, no validation-time live
  connection execution, no credentials, no credential prompts, no authenticated
  requests, no user-order channel, no order placement imports, no production
  endpoints, no strategy optimization, no investment advice, and no
  profitability claims.

### Stage 41: Polymarket market-channel recorder

- Status: complete.
- Commit: `33b4b5a` (merged via PR #91).
- Purpose: add a guarded Polymarket US market-channel recorder that writes raw
  live-event JSONL and normalized snapshot JSONL through mocked-testable code
  paths.
- Files/modules changed:
  `src/edmn_trader/adapters/polymarket_us/market_recorder.py`,
  `src/edmn_trader/scripts/polymarket_market_recorder.py`,
  `scripts/41_polymarket_market_recorder.py`,
  `tests/test_polymarket_market_recorder.py`, Stage 39 live-event source-type
  support, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/41_polymarket_market_recorder.py --help`,
  `python scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: Stage 42 may add order book rebuild and replay
  consistency only. It must rebuild from recorded events, hash state, detect
  gaps/staleness/out-of-order input, and must not add execution, credentials,
  live venue connections, wallets, or strategy optimization.
- Safety status: guarded Polymarket US public market-channel recorder only, no
  validation-time live connection execution, no credentials, no credential
  prompts, no authenticated requests, no user channel, no wallet, no signing,
  no order placement imports, no production trading endpoint, no strategy
  optimization, no investment advice, and no profitability claims.

### Stage 42: Order book rebuild and replay consistency

- Status: complete.
- Commit: `96e2097` (merged via PR #92).
- Purpose: rebuild normalized order books from recorded read-only events,
  compute deterministic book-state hashes, and report replay consistency flags.
- Files/modules changed: `src/edmn_trader/data/book_rebuild.py`,
  `src/edmn_trader/scripts/rebuild_orderbooks.py`,
  `scripts/42_rebuild_orderbooks.py`, `tests/test_book_rebuild.py`, data
  exports, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/42_rebuild_orderbooks.py --help`,
  `python scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: Stage 43 may add taker fill, slippage, and failed-leg
  simulation only. It must stress two-leg assumptions offline, keep outputs as
  audit/paper research records, and must not add order placement, credentials,
  live venue connections, wallets, user channels, or strategy optimization.
- Safety status: offline rebuild/replay consistency only, no live venue
  connection execution, no credentials, no credential prompts, no
  authenticated requests, no user channel, no wallet, no signing, no order
  placement imports, no production trading endpoint, no strategy optimization,
  no investment advice, and no profitability claims.

### Stage 43: Taker fill, slippage, and failed-leg simulator

- Status: complete.
- Commit: `05fb58e` (merged via PR #93).
- Purpose: simulate offline two-leg taker-fill assumptions for complement
  candidates, including FOK/IOC-like policies, partial fills, slippage,
  latency shock, and failed-leg reserve.
- Files/modules changed: `src/edmn_trader/arb/fill_simulation.py`,
  `src/edmn_trader/scripts/simulate_taker_fill.py`,
  `scripts/43_simulate_taker_fill.py`, `tests/test_fill_simulation.py`,
  arbitrage exports, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/43_simulate_taker_fill.py --help`,
  `python scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: stop for human architecture review before Stage 44.
  Stage 44 may add a paper complement arbitrage engine only after review of
  the Stage 39-43 live-data/replay/simulation foundation.
- Safety status: offline simulation records only, no live venue connection
  execution, no credentials, no credential prompts, no authenticated requests,
  no user channel, no wallet, no signing, no order placement imports, no
  production trading endpoint, no strategy optimization, no investment advice,
  no executable advice, and no profitability claims.

### Stage 44: Paper complement arbitrage engine

- Status: complete.
- Commit: `1d191a5` (merged via PR #94).
- Purpose: convert offline candidate and fill-simulation records into
  deterministic paper-only two-leg proposal records with locked candidate and
  simulation hashes plus conservative risk-preview reasons.
- Files/modules changed: `src/edmn_trader/arb/paper_engine.py`,
  `src/edmn_trader/scripts/paper_complement_engine.py`,
  `scripts/44_paper_complement_engine.py`, `tests/test_paper_engine.py`,
  arbitrage exports, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/44_paper_complement_engine.py --help`,
  `python scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: Stage 45 may add an event-sourced paper ledger state
  machine only. It must replay paper orders, paper fills, positions, fees,
  PnL, settlements, and reconciliation mismatch states from local records.
- Safety status: paper proposal records only, no live venue connection
  execution, no credentials, no credential prompts, no authenticated requests,
  no user channel, no wallet, no signing, no order placement imports, no
  venue submission, no production trading endpoint, no strategy optimization,
  no investment advice, no executable advice, and no profitability claims.

### Stage 45: Paper ledger state machine

- Status: complete.
- Commit: `a06bdf5` (merged via PR #95).
- Purpose: replay paper proposal, fill, and settlement records from zero into
  deterministic paper ledger state with positions, fees, PnL, source hashes,
  and reconciliation mismatch states.
- Files/modules changed: `src/edmn_trader/arb/paper_ledger.py`,
  `src/edmn_trader/scripts/paper_ledger.py`,
  `scripts/45_replay_paper_ledger.py`, `tests/test_paper_ledger.py`,
  arbitrage exports, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/45_replay_paper_ledger.py --help`,
  `python scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: Stage 46 may add risk engine v2 only. It must reject
  stale data, data gaps, missing fees, insufficient net edge, exposure/open
  order/daily-loss breaches, reconciliation mismatch, and active kill switch
  while still requiring manual approval.
- Safety status: paper ledger research records only, no live venue connection
  execution, no credentials, no credential prompts, no authenticated requests,
  no user channel, no wallet, no signing, no order placement imports, no
  venue submission, no production trading endpoint, no strategy optimization,
  no investment advice, no executable advice, and no profitability claims.

### Stage 46: Risk engine v2

- Status: complete.
- Commit: pending on the Stage 46 risk engine branch.
- Purpose: evaluate paper complement risk blockers for stale data, data gaps,
  missing or unknown fees, insufficient net edge, exposure/open-order/daily-loss
  breaches, reconciliation mismatch, and active kill switch while still
  requiring manual approval.
- Files/modules changed: `src/edmn_trader/arb/risk.py`,
  `src/edmn_trader/scripts/complement_risk.py`,
  `scripts/46_complement_risk.py`, `tests/test_complement_risk.py`,
  arbitrage exports, and documentation updates.
- Validation commands: `python -m pip install -e ".[dev]"`, `pytest`,
  `ruff check .`, `python scripts/46_complement_risk.py --help`,
  `python scripts/01_replay_orderbook_fixture.py`, and `git diff --check`.
- Next-stage boundary: Stage 47 may add a manual approval workflow only.
  It must use pending approval files, expiring approvals, candidate hash
  verification, and no reusable approvals.
- Safety status: paper risk-decision records only, no live venue connection
  execution, no credentials, no credential prompts, no authenticated requests,
  no user channel, no wallet, no signing, no order placement imports, no
  venue submission, no production trading endpoint, no strategy optimization,
  no investment advice, no executable advice, and no profitability claims.

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

## Stage 22: Local reproducibility-checklist report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 21: a local
reproducibility-checklist input that records reviewer-supplied reproduction
step labels, local artifact paths, command labels, environment labels, expected
output labels, and limitation notes without executing commands, reading
artifact contents, fetching remote data, verifying outputs, ranking coverage,
or producing executable advice.

Deliverables: Stage 22 implementation may add a `local_reproducibility_checklist`
input kind to the report-input manifest, parse a local reproducibility
descriptor, render a descriptive report section, add offline tests, and update
limitation notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied reproducibility metadata, not as a
  script runner, environment verifier, artifact reader, validation executor,
  scoring system, or recommendation engine.
- Describe only reproduction step labels, local artifact paths, command labels,
  environment labels, expected output labels, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, and limitations.
- Label missing optional reproducibility-checklist inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs, read
  secrets, read artifact contents, read source contents, read raw private data
  contents, read account data, read portfolio data, fetch remote data, use live
  feeds, inspect paid-vendor or proprietary datasets, verify local environment
  state, or infer private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  reproducibility steps, coverage, sources, or securities, recommend
  allocations, optimize strategies, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional reproducibility-checklist inputs produce explicit
  not-supplied text instead of inferred values.
- Tests use local descriptors and generated project artifacts only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no artifact-content reads, no source-content
reads, no raw private data reads, no private/proprietary excerpts, no local
environment verification, no output verification, no new market-data adapters,
no remote fetching, no broker integration, no credentials, no account or
portfolio data, no live quote feeds, no paid-vendor market data, no WebSockets,
no production endpoints, no strategy optimization, no reproducibility scoring,
no coverage scoring, no security ranking, no source ranking, no allocation
advice, no executable advice, no production readiness claim, no unsupported
data redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local reproducibility-checklist
input kind only within the local/offline report-pack path and must not add
command execution, validation execution, artifact-content reads,
source-content reads, raw local data reads, local environment verification,
remote fetches, new adapters, production endpoints, ranking, allocation,
optimization, executable advice, or production-readiness claims.

## Stage 23: Local risk-review report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 22: a local
risk-review input that records reviewer-supplied risk-control labels, boundary
labels, mitigation notes, review status labels, local evidence paths, and
limitation notes without executing checks, reading evidence contents, fetching
remote data, scoring risk, placing orders, or producing executable advice.

Deliverables: Stage 23 implementation may add a `local_risk_review` input kind
to the report-input manifest, parse a local risk-review descriptor, render a
descriptive report section, add offline tests, and update limitation notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied risk-review metadata, not as a risk
  engine, policy evaluator, evidence reader, validation executor, scoring
  system, or recommendation engine.
- Describe only risk-control labels, boundary labels, mitigation notes, review
  status labels, local evidence paths, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata, and
  limitations.
- Label missing optional risk-review inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  evaluate policies, run risk checks, place orders, read secrets, read evidence
  contents, read source contents, read raw private data contents, read account
  data, read portfolio data, fetch remote data, use live feeds, inspect
  paid-vendor or proprietary datasets, verify local environment state, or infer
  private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank risk
  controls, reproducibility steps, coverage, sources, or securities, recommend
  allocations, optimize strategies, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional risk-review inputs produce explicit not-supplied text
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
execution from report inputs, no policy evaluation, no risk-check execution, no
order placement, no evidence-content reads, no source-content reads, no raw
private data reads, no private/proprietary excerpts, no local environment
verification, no output verification, no new market-data adapters, no remote
fetching, no broker integration, no credentials, no account or portfolio data,
no live quote feeds, no paid-vendor market data, no WebSockets, no production
endpoints, no strategy optimization, no risk scoring, no reproducibility
scoring, no coverage scoring, no security ranking, no source ranking, no
allocation advice, no executable advice, no production readiness claim, no
unsupported data redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local risk-review input kind
only within the local/offline report-pack path and must not add command
execution, validation execution, policy evaluation, risk-check execution, order
placement, evidence-content reads, source-content reads, raw local data reads,
local environment verification, remote fetches, new adapters, production
endpoints, ranking, allocation, optimization, executable advice, or
production-readiness claims.

## Stage 24: Local data-rights-review report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 23: a local
data-rights-review input that records reviewer-supplied data labels, rights
status labels, permitted-use notes, restriction notes, local evidence paths,
and limitation notes without reading evidence contents, determining legal
rights, fetching remote data, scoring rights status, or producing executable
advice.

Deliverables: Stage 24 implementation may add a `local_data_rights_review`
input kind to the report-input manifest, parse a local data-rights descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied data-rights metadata, not as legal
  advice, license verification, evidence reading, policy evaluation, validation
  execution, scoring, or a redistribution decision.
- Describe only data labels, rights status labels, permitted-use notes,
  restriction notes, local evidence paths, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, and limitations.
- Label missing optional data-rights-review inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  evaluate policies, determine legal rights, verify licenses, decide
  redistribution permissions, place orders, read secrets, read evidence
  contents, read source contents, read raw private data contents, read account
  data, read portfolio data, fetch remote data, use live feeds, inspect
  paid-vendor or proprietary datasets, verify local environment state, or infer
  private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  rights status, risk controls, reproducibility steps, coverage, sources, or
  securities, recommend allocations, optimize strategies, emit executable
  advice, imply production readiness, or claim profitability.
- Missing optional data-rights-review inputs produce explicit not-supplied text
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
execution from report inputs, no legal advice, no legal-rights determination,
no license verification, no redistribution decision, no policy evaluation, no
risk-check execution, no order placement, no evidence-content reads, no
source-content reads, no raw private data reads, no private/proprietary
excerpts, no local environment verification, no output verification, no new
market-data adapters, no remote fetching, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no WebSockets, no production endpoints, no strategy optimization,
no rights scoring, no risk scoring, no reproducibility scoring, no coverage
scoring, no security ranking, no source ranking, no allocation advice, no
executable advice, no production readiness claim, no unsupported data
redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local data-rights-review input
kind only within the local/offline report-pack path and must not add command
execution, validation execution, legal-rights determination, license
verification, redistribution decisions, policy evaluation, risk-check
execution, order placement, evidence-content reads, source-content reads, raw
local data reads, local environment verification, remote fetches, new adapters,
production endpoints, ranking, allocation, optimization, executable advice, or
production-readiness claims.

## Stage 25: Local artifact-inventory report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 24: a local
artifact-inventory input that records reviewer-supplied generated artifact
labels, artifact type labels, local paths, generation-source labels, intended
report-use notes, and limitation notes without reading artifact contents,
verifying outputs, fetching remote data, ranking artifacts, or producing
executable advice.

Deliverables: Stage 25 implementation may add a `local_artifact_inventory`
input kind to the report-input manifest, parse a local artifact-inventory
descriptor, render a descriptive report section, add offline tests, and update
limitation notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied artifact metadata, not as artifact
  content, output verification, environment verification, validation
  execution, ranking, scoring, or production-readiness evidence.
- Describe only generated artifact labels, artifact type labels, local paths,
  generation-source labels, intended report-use notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata, and limitations.
- Label missing optional artifact-inventory inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  verify local environments, verify outputs, place orders, read secrets, read
  artifact contents, read evidence contents, read source contents, read raw
  private data contents, read account data, read portfolio data, fetch remote
  data, use live feeds, inspect paid-vendor or proprietary datasets, or infer
  private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  artifacts, rights status, risk controls, reproducibility steps, coverage,
  sources, or securities, recommend allocations, optimize strategies, emit
  executable advice, imply production readiness, or claim profitability.
- Missing optional artifact-inventory inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no artifact-content reads, no output
verification, no local environment verification, no evidence-content reads, no
source-content reads, no raw private data reads, no private/proprietary
excerpts, no risk-check execution, no order placement, no new market-data
adapters, no remote fetching, no broker integration, no credentials, no
account or portfolio data, no live quote feeds, no paid-vendor market data, no
WebSockets, no production endpoints, no strategy optimization, no artifact
scoring, no rights scoring, no risk scoring, no reproducibility scoring, no
coverage scoring, no security ranking, no source ranking, no allocation
advice, no executable advice, no production readiness claim, no unsupported
data redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local artifact-inventory input
kind only within the local/offline report-pack path and must not add command
execution, validation execution, artifact-content reads, output verification,
local environment verification, evidence-content reads, source-content reads,
raw local data reads, remote fetches, new adapters, production endpoints,
ranking, allocation, optimization, executable advice, or production-readiness
claims.

## Stage 26: Local appendix-index report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 25: a local
appendix-index input that records reviewer-supplied appendix entry labels,
report section labels, local artifact paths, appendix purpose notes, and
limitation notes without reading artifact contents, verifying outputs, fetching
remote data, ranking appendix entries, or producing executable advice.

Deliverables: Stage 26 implementation may add a `local_appendix_index` input
kind to the report-input manifest, parse a local appendix-index descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied appendix metadata, not as artifact
  content, output verification, environment verification, validation
  execution, ranking, scoring, distribution approval, or production-readiness
  evidence.
- Describe only appendix entry labels, report section labels, local artifact
  paths, appendix purpose notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, and limitations.
- Label missing optional appendix-index inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  verify local environments, verify outputs, place orders, read secrets, read
  artifact contents, read evidence contents, read source contents, read raw
  private data contents, read account data, read portfolio data, fetch remote
  data, use live feeds, inspect paid-vendor or proprietary datasets, or infer
  private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  appendix entries, artifacts, rights status, risk controls, reproducibility
  steps, coverage, sources, or securities, recommend allocations, optimize
  strategies, emit executable advice, imply production readiness, or claim
  profitability.
- Missing optional appendix-index inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no artifact-content reads, no output
verification, no local environment verification, no evidence-content reads, no
source-content reads, no raw private data reads, no private/proprietary
excerpts, no distribution approval, no risk-check execution, no order
placement, no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no WebSockets, no production endpoints, no
strategy optimization, no appendix scoring, no artifact scoring, no rights
scoring, no risk scoring, no reproducibility scoring, no coverage scoring, no
security ranking, no source ranking, no allocation advice, no executable
advice, no production readiness claim, no unsupported data redistribution, and
no profitability claims.

Next-stage boundary: implementation may add the local appendix-index input kind
only within the local/offline report-pack path and must not add command
execution, validation execution, artifact-content reads, output verification,
local environment verification, evidence-content reads, source-content reads,
raw local data reads, remote fetches, new adapters, production endpoints,
ranking, allocation, optimization, executable advice, or production-readiness
claims.

## Stage 27: Local limitation-register report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 26: a local
limitation-register input that records reviewer-supplied limitation labels,
affected report section labels, local evidence or artifact paths, scope notes,
mitigation notes, and limitation notes without reading referenced contents,
verifying outputs, fetching remote data, scoring limitations, or producing
executable advice.

Deliverables: Stage 27 implementation may add a `local_limitation_register`
input kind to the report-input manifest, parse a local limitation-register
descriptor, render a descriptive report section, add offline tests, and update
limitation notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied limitation metadata, not as
  artifact content, evidence content, output verification, environment
  verification, validation execution, ranking, scoring, distribution approval,
  or production-readiness evidence.
- Describe only limitation labels, affected report section labels, local
  evidence or artifact paths, scope notes, mitigation notes, and limitation
  notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, and limitations.
- Label missing optional limitation-register inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  verify local environments, verify outputs, place orders, read secrets, read
  artifact contents, read evidence contents, read source contents, read raw
  private data contents, read account data, read portfolio data, fetch remote
  data, use live feeds, inspect paid-vendor or proprietary datasets, or infer
  private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  limitations, appendix entries, artifacts, rights status, risk controls,
  reproducibility steps, coverage, sources, or securities, recommend
  allocations, optimize strategies, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional limitation-register inputs produce explicit not-supplied
  text instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no artifact-content reads, no evidence-content
reads, no source-content reads, no output verification, no local environment
verification, no raw private data reads, no private/proprietary excerpts, no
distribution approval, no risk-check execution, no order placement, no new
market-data adapters, no remote fetching, no broker integration, no
credentials, no account or portfolio data, no live quote feeds, no paid-vendor
market data, no WebSockets, no production endpoints, no strategy optimization,
no limitation scoring, no appendix scoring, no artifact scoring, no rights
scoring, no risk scoring, no reproducibility scoring, no coverage scoring, no
security ranking, no source ranking, no allocation advice, no executable
advice, no production readiness claim, no unsupported data redistribution, and
no profitability claims.

Next-stage boundary: implementation may add the local limitation-register input
kind only within the local/offline report-pack path and must not add command
execution, validation execution, artifact-content reads, evidence-content
reads, source-content reads, output verification, local environment
verification, raw local data reads, remote fetches, new adapters, production
endpoints, ranking, allocation, optimization, executable advice, or
production-readiness claims.

## Stage 28: Local open-questions report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 27: a local
open-questions input that records reviewer-supplied open question labels,
affected report section labels, local reference paths, owner labels, status
labels, and limitation notes without reading referenced contents, verifying
outputs, fetching remote data, scoring questions, or producing executable
advice.

Deliverables: Stage 28 implementation may add a `local_open_questions` input
kind to the report-input manifest, parse a local open-questions descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied open-question metadata, not as
  artifact content, evidence content, output verification, environment
  verification, validation execution, ranking, scoring, decision approval, or
  production-readiness evidence.
- Describe only open question labels, affected report section labels, local
  reference paths, owner labels, status labels, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, open-question
  metadata, and limitations.
- Label missing optional open-questions inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  verify local environments, verify outputs, place orders, read secrets, read
  artifact contents, read evidence contents, read source contents, read raw
  private data contents, read account data, read portfolio data, fetch remote
  data, use live feeds, inspect paid-vendor or proprietary datasets, or infer
  private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank open
  questions, limitations, appendix entries, artifacts, rights status, risk
  controls, reproducibility steps, coverage, sources, or securities, recommend
  allocations, optimize strategies, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional open-questions inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no artifact-content reads, no evidence-content
reads, no source-content reads, no output verification, no local environment
verification, no raw private data reads, no private/proprietary excerpts, no
decision approval, no distribution approval, no risk-check execution, no order
placement, no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no WebSockets, no production endpoints, no
strategy optimization, no question scoring, no limitation scoring, no appendix
scoring, no artifact scoring, no rights scoring, no risk scoring, no
reproducibility scoring, no coverage scoring, no security ranking, no source
ranking, no allocation advice, no executable advice, no production readiness
claim, no unsupported data redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local open-questions input
kind only within the local/offline report-pack path and must not add command
execution, validation execution, artifact-content reads, evidence-content
reads, source-content reads, output verification, local environment
verification, raw local data reads, remote fetches, new adapters, production
endpoints, ranking, allocation, optimization, executable advice, or
production-readiness claims.

## Stage 29: Local decision-log report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 28: a local
decision-log input that records reviewer-supplied decision labels, decision
context labels, local reference paths, owner labels, status labels, rationale
notes, and limitation notes without reading referenced contents, approving
decisions, fetching remote data, scoring decisions, or producing executable
advice.

Deliverables: Stage 29 implementation may add a `local_decision_log` input
kind to the report-input manifest, parse a local decision-log descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied decision metadata, not as artifact
  content, evidence content, source content, output verification, environment
  verification, validation execution, ranking, scoring, decision approval, or
  production-readiness evidence.
- Describe only decision labels, decision context labels, local reference
  paths, owner labels, status labels, rationale notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, open-question
  metadata, decision-log metadata, and limitations.
- Label missing optional decision-log inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  verify local environments, verify outputs, place orders, read secrets, read
  artifact contents, read evidence contents, read source contents, read raw
  private data contents, read account data, read portfolio data, fetch remote
  data, use live feeds, inspect paid-vendor or proprietary datasets, approve
  decisions, or infer private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  decisions, open questions, limitations, appendix entries, artifacts, rights
  status, risk controls, reproducibility steps, coverage, sources, or
  securities, recommend allocations, optimize strategies, emit executable
  advice, imply production readiness, or claim profitability.
- Missing optional decision-log inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no artifact-content reads, no evidence-content
reads, no source-content reads, no output verification, no local environment
verification, no raw private data reads, no private/proprietary excerpts, no
decision approval, no distribution approval, no risk-check execution, no order
placement, no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no WebSockets, no production endpoints, no
strategy optimization, no decision scoring, no question scoring, no limitation
scoring, no appendix scoring, no artifact scoring, no rights scoring, no risk
scoring, no reproducibility scoring, no coverage scoring, no security ranking,
no source ranking, no allocation advice, no executable advice, no production
readiness claim, no unsupported data redistribution, and no profitability
claims.

Next-stage boundary: implementation may add the local decision-log input kind
only within the local/offline report-pack path and must not add command
execution, validation execution, artifact-content reads, evidence-content
reads, source-content reads, output verification, local environment
verification, decision approval, raw local data reads, remote fetches, new
adapters, production endpoints, ranking, allocation, optimization, executable
advice, or production-readiness claims.

## Stage 30: Local follow-up register report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 29: a local
follow-up register that records reviewer-supplied follow-up labels, related
report section labels, local reference paths, owner labels, status labels,
tracking notes, and limitation notes without reading referenced contents,
executing follow-ups, fetching remote data, scoring follow-ups, or producing
executable advice.

Deliverables: Stage 30 implementation may add a `local_follow_up_register`
input kind to the report-input manifest, parse a local follow-up descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied follow-up metadata, not as
  artifact content, evidence content, source content, output verification,
  environment verification, validation execution, task execution, ranking,
  scoring, decision approval, or production-readiness evidence.
- Describe only follow-up labels, related report section labels, local
  reference paths, owner labels, status labels, tracking notes, and limitation
  notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, open-question
  metadata, decision-log metadata, follow-up metadata, and limitations.
- Label missing optional follow-up-register inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  execute follow-ups, verify local environments, verify outputs, place orders,
  read secrets, read artifact contents, read evidence contents, read source
  contents, read raw private data contents, read account data, read portfolio
  data, fetch remote data, use live feeds, inspect paid-vendor or proprietary
  datasets, approve decisions, or infer private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  follow-ups, decisions, open questions, limitations, appendix entries,
  artifacts, rights status, risk controls, reproducibility steps, coverage,
  sources, or securities, recommend allocations, optimize strategies, emit
  executable advice, imply production readiness, or claim profitability.
- Missing optional follow-up-register inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no follow-up execution, no artifact-content
reads, no evidence-content reads, no source-content reads, no output
verification, no local environment verification, no raw private data reads, no
private/proprietary excerpts, no decision approval, no distribution approval,
no risk-check execution, no order placement, no new market-data adapters, no
remote fetching, no broker integration, no credentials, no account or
portfolio data, no live quote feeds, no paid-vendor market data, no
WebSockets, no production endpoints, no strategy optimization, no follow-up
scoring, no decision scoring, no question scoring, no limitation scoring, no
appendix scoring, no artifact scoring, no rights scoring, no risk scoring, no
reproducibility scoring, no coverage scoring, no security ranking, no source
ranking, no allocation advice, no executable advice, no production readiness
claim, no unsupported data redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local follow-up-register input
kind only within the local/offline report-pack path and must not add command
execution, validation execution, follow-up execution, artifact-content reads,
evidence-content reads, source-content reads, output verification, local
environment verification, decision approval, raw local data reads, remote
fetches, new adapters, production endpoints, ranking, allocation,
optimization, executable advice, or production-readiness claims.

## Stage 31: Local version-notes report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 30: local
version notes that record reviewer-supplied report version labels, local
artifact paths, change-summary labels, owner labels, status labels, and
limitation notes without reading artifact contents, approving distribution,
fetching remote data, scoring versions, or producing executable advice.

Deliverables: Stage 31 implementation may add a `local_version_notes` input
kind to the report-input manifest, parse a local version-notes descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied version metadata, not as artifact
  content, evidence content, source content, output verification, environment
  verification, validation execution, distribution approval, ranking, scoring,
  decision approval, or production-readiness evidence.
- Describe only report version labels, local artifact paths, change-summary
  labels, owner labels, status labels, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, open-question
  metadata, decision-log metadata, follow-up metadata, version-note metadata,
  and limitations.
- Label missing optional version-notes inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  execute follow-ups, verify local environments, verify outputs, place orders,
  approve distribution, read secrets, read artifact contents, read evidence
  contents, read source contents, read raw private data contents, read account
  data, read portfolio data, fetch remote data, use live feeds, inspect
  paid-vendor or proprietary datasets, approve decisions, or infer private
  values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  versions, follow-ups, decisions, open questions, limitations, appendix
  entries, artifacts, rights status, risk controls, reproducibility steps,
  coverage, sources, or securities, recommend allocations, optimize
  strategies, emit executable advice, imply production readiness, or claim
  profitability.
- Missing optional version-notes inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no follow-up execution, no artifact-content
reads, no evidence-content reads, no source-content reads, no output
verification, no local environment verification, no raw private data reads, no
private/proprietary excerpts, no distribution approval, no decision approval,
no risk-check execution, no order placement, no new market-data adapters, no
remote fetching, no broker integration, no credentials, no account or
portfolio data, no live quote feeds, no paid-vendor market data, no
WebSockets, no production endpoints, no strategy optimization, no version
scoring, no follow-up scoring, no decision scoring, no question scoring, no
limitation scoring, no appendix scoring, no artifact scoring, no rights
scoring, no risk scoring, no reproducibility scoring, no coverage scoring, no
security ranking, no source ranking, no allocation advice, no executable
advice, no production readiness claim, no unsupported data redistribution, and
no profitability claims.

Next-stage boundary: implementation may add the local version-notes input kind
only within the local/offline report-pack path and must not add command
execution, validation execution, follow-up execution, artifact-content reads,
evidence-content reads, source-content reads, output verification, local
environment verification, distribution approval, decision approval, raw local
data reads, remote fetches, new adapters, production endpoints, ranking,
allocation, optimization, executable advice, or production-readiness claims.

## Stage 32: Local distribution-checklist report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 31: a local
distribution checklist that records reviewer-supplied distribution item labels,
related artifact paths, readiness status labels, owner labels, review notes,
and limitation notes without reading artifact contents, approving
distribution, verifying rights, fetching remote data, scoring checklist items,
or producing executable advice.

Deliverables: Stage 32 implementation may add a
`local_distribution_checklist` input kind to the report-input manifest, parse a
local distribution-checklist descriptor, render a descriptive report section,
add offline tests, and update limitation notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied distribution-checklist metadata,
  not as artifact content, evidence content, source content, output
  verification, environment verification, validation execution, distribution
  approval, rights verification, ranking, scoring, decision approval, or
  production-readiness evidence.
- Describe only distribution item labels, related artifact paths, readiness
  status labels, owner labels, review notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, open-question
  metadata, decision-log metadata, follow-up metadata, version-note metadata,
  distribution-checklist metadata, and limitations.
- Label missing optional distribution-checklist inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  execute follow-ups, verify local environments, verify outputs, place orders,
  approve distribution, verify rights or licenses, read secrets, read artifact
  contents, read evidence contents, read source contents, read raw private data
  contents, read account data, read portfolio data, fetch remote data, use live
  feeds, inspect paid-vendor or proprietary datasets, approve decisions, or
  infer private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  distribution items, versions, follow-ups, decisions, open questions,
  limitations, appendix entries, artifacts, rights status, risk controls,
  reproducibility steps, coverage, sources, or securities, recommend
  allocations, optimize strategies, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional distribution-checklist inputs produce explicit not-supplied
  text instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no follow-up execution, no artifact-content
reads, no evidence-content reads, no source-content reads, no output
verification, no local environment verification, no raw private data reads, no
private/proprietary excerpts, no distribution approval, no rights or license
verification, no decision approval, no risk-check execution, no order
placement, no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no WebSockets, no production endpoints, no
strategy optimization, no distribution scoring, no version scoring, no
follow-up scoring, no decision scoring, no question scoring, no limitation
scoring, no appendix scoring, no artifact scoring, no rights scoring, no risk
scoring, no reproducibility scoring, no coverage scoring, no security ranking,
no source ranking, no allocation advice, no executable advice, no production
readiness claim, no unsupported data redistribution, and no profitability
claims.

Next-stage boundary: implementation may add the local distribution-checklist
input kind only within the local/offline report-pack path and must not add
command execution, validation execution, follow-up execution,
artifact-content reads, evidence-content reads, source-content reads, output
verification, local environment verification, distribution approval, rights
verification, decision approval, raw local data reads, remote fetches, new
adapters, production endpoints, ranking, allocation, optimization, executable
advice, or production-readiness claims.

## Stage 33: Local handoff-notes report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 32: local
handoff notes that record reviewer-supplied handoff labels, related artifact
paths, recipient or owner labels, status labels, handoff notes, and limitation
notes without reading artifact contents, approving distribution, verifying
rights, fetching remote data, scoring handoffs, or producing executable
advice.

Deliverables: Stage 33 implementation may add a `local_handoff_notes` input
kind to the report-input manifest, parse a local handoff-notes descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied handoff metadata, not as artifact
  content, evidence content, source content, output verification, environment
  verification, validation execution, distribution approval, rights
  verification, ranking, scoring, decision approval, or production-readiness
  evidence.
- Describe only handoff labels, related artifact paths, recipient or owner
  labels, status labels, handoff notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, open-question
  metadata, decision-log metadata, follow-up metadata, version-note metadata,
  distribution-checklist metadata, handoff-note metadata, and limitations.
- Label missing optional handoff-notes inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  execute follow-ups, verify local environments, verify outputs, place orders,
  approve distribution, verify rights or licenses, read secrets, read artifact
  contents, read evidence contents, read source contents, read raw private data
  contents, read account data, read portfolio data, fetch remote data, use live
  feeds, inspect paid-vendor or proprietary datasets, approve decisions, or
  infer private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  handoffs, distribution items, versions, follow-ups, decisions, open
  questions, limitations, appendix entries, artifacts, rights status, risk
  controls, reproducibility steps, coverage, sources, or securities, recommend
  allocations, optimize strategies, emit executable advice, imply production
  readiness, or claim profitability.
- Missing optional handoff-notes inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no follow-up execution, no artifact-content
reads, no evidence-content reads, no source-content reads, no output
verification, no local environment verification, no raw private data reads, no
private/proprietary excerpts, no distribution approval, no rights or license
verification, no decision approval, no risk-check execution, no order
placement, no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no WebSockets, no production endpoints, no
strategy optimization, no handoff scoring, no distribution scoring, no version
scoring, no follow-up scoring, no decision scoring, no question scoring, no
limitation scoring, no appendix scoring, no artifact scoring, no rights
scoring, no risk scoring, no reproducibility scoring, no coverage scoring, no
security ranking, no source ranking, no allocation advice, no executable
advice, no production readiness claim, no unsupported data redistribution, and
no profitability claims.

Next-stage boundary: implementation may add the local handoff-notes input kind
only within the local/offline report-pack path and must not add command
execution, validation execution, follow-up execution, artifact-content reads,
evidence-content reads, source-content reads, output verification, local
environment verification, distribution approval, rights verification, decision
approval, raw local data reads, remote fetches, new adapters, production
endpoints, ranking, allocation, optimization, executable advice, or
production-readiness claims.

## Stage 34: Local archive-notes report input, local/offline only

Purpose: clarify the next concrete report-input kind after Stage 33: local
archive notes that record reviewer-supplied archive labels, related artifact
paths, archive status labels, owner labels, archive notes, and limitation
notes without reading artifact contents, moving or deleting files, approving
distribution, verifying rights, deciding retention policy, fetching remote
data, scoring archive readiness, or producing executable advice.

Deliverables: Stage 34 implementation may add a `local_archive_notes` input
kind to the report-input manifest, parse a local archive-notes descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied archive metadata, not as artifact
  content, evidence content, source content, output verification, environment
  verification, validation execution, file operation, retention-policy
  decision, distribution approval, rights verification, ranking, scoring,
  decision approval, or production-readiness evidence.
- Describe only archive labels, related artifact paths, archive status labels,
  owner labels, archive notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, open-question
  metadata, decision-log metadata, follow-up metadata, version-note metadata,
  distribution-checklist metadata, handoff-note metadata, archive-note
  metadata, and limitations.
- Label missing optional archive-notes inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  execute follow-ups, verify local environments, verify outputs, place orders,
  move files, delete files, decide retention policy, approve distribution,
  verify rights or licenses, read secrets, read artifact contents, read
  evidence contents, read source contents, read raw private data contents, read
  account data, read portfolio data, fetch remote data, use live feeds, inspect
  paid-vendor or proprietary datasets, approve decisions, or infer private
  values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  archive readiness, handoffs, distribution items, versions, follow-ups,
  decisions, open questions, limitations, appendix entries, artifacts, rights
  status, risk controls, reproducibility steps, coverage, sources, or
  securities, recommend allocations, optimize strategies, emit executable
  advice, imply production readiness, or claim profitability.
- Missing optional archive-notes inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no follow-up execution, no file movement or
deletion, no retention-policy decision, no artifact-content reads, no
evidence-content reads, no source-content reads, no output verification, no
local environment verification, no raw private data reads, no
private/proprietary excerpts, no distribution approval, no rights or license
verification, no decision approval, no risk-check execution, no order
placement, no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no WebSockets, no production endpoints, no
strategy optimization, no archive scoring, no handoff scoring, no distribution
scoring, no version scoring, no follow-up scoring, no decision scoring, no
question scoring, no limitation scoring, no appendix scoring, no artifact
scoring, no rights scoring, no risk scoring, no reproducibility scoring, no
coverage scoring, no security ranking, no source ranking, no allocation
advice, no executable advice, no production readiness claim, no unsupported
data redistribution, and no profitability claims.

Next-stage boundary: implementation may add the local archive-notes input kind
only within the local/offline report-pack path and must not add command
execution, validation execution, follow-up execution, file movement or
deletion, retention-policy decisions, artifact-content reads, evidence-content
reads, source-content reads, output verification, local environment
verification, distribution approval, rights verification, decision approval,
raw local data reads, remote fetches, new adapters, production endpoints,
ranking, allocation, optimization, executable advice, or production-readiness
claims.

## Maintenance backlog: Local delivery-notes report input, local/offline only

Purpose: preserve the previously clarified local delivery-notes report-input
idea as a maintenance-only backlog item. It is no longer the active next
product checkpoint. If a later maintenance task resumes it, the scope remains
local/offline delivery notes that record reviewer-supplied delivery labels,
related artifact paths, recipient labels, delivery status labels, delivery
notes, and limitation notes without transferring files, approving
distribution, verifying rights, fetching remote data, scoring delivery
readiness, or producing executable advice.

Deliverables: a future maintenance task may add a `local_delivery_notes` input
kind to the report-input manifest, parse a local delivery-notes descriptor,
render a descriptive report section, add offline tests, and update limitation
notes.

Allowed scope:

- Use a local descriptor file only.
- Treat the descriptor as reviewer-supplied delivery metadata, not as artifact
  content, evidence content, source content, output verification, environment
  verification, validation execution, file transfer, distribution approval,
  rights verification, ranking, scoring, decision approval, or
  production-readiness evidence.
- Describe only delivery labels, related artifact paths, recipient labels,
  delivery status labels, delivery notes, and limitation notes.
- Reject remote URLs, secret-like fields, and source-content/excerpt fields.
- Preserve separation between observed report metrics, supplied assumptions,
  fundamentals, manifest metadata, comparison metadata, validation metadata,
  review notes, methodology notes, data-dictionary metadata, citation-index
  metadata, term-glossary metadata, assumption-register metadata,
  coverage-matrix metadata, reproducibility metadata, risk-review metadata,
  data-rights-review metadata, artifact-inventory metadata,
  appendix-index metadata, limitation-register metadata, open-question
  metadata, decision-log metadata, follow-up metadata, version-note metadata,
  distribution-checklist metadata, handoff-note metadata, archive-note
  metadata, delivery-note metadata, and limitations.
- Label missing optional delivery-notes inputs as not supplied.

Acceptance checks:

- The implementation remains local/offline and deterministic.
- The report pack does not execute commands, run tests from report inputs,
  execute follow-ups, verify local environments, verify outputs, place orders,
  move files, delete files, transfer files, decide retention policy, approve
  distribution, verify rights or licenses, read secrets, read artifact
  contents, read evidence contents, read source contents, read raw private data
  contents, read account data, read portfolio data, fetch remote data, use live
  feeds, inspect paid-vendor or proprietary datasets, approve decisions, or
  infer private values from referenced files.
- The output does not include private/proprietary excerpts, score or rank
  delivery readiness, archive readiness, handoffs, distribution items,
  versions, follow-ups, decisions, open questions, limitations, appendix
  entries, artifacts, rights status, risk controls, reproducibility steps,
  coverage, sources, or securities, recommend allocations, optimize
  strategies, emit executable advice, imply production readiness, or claim
  profitability.
- Missing optional delivery-notes inputs produce explicit not-supplied text
  instead of inferred values.
- Tests use local descriptors and generated project artifact references only.

Validation commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

Explicit non-goals: no command execution from report inputs, no validation
execution from report inputs, no follow-up execution, no file movement,
deletion, or transfer, no retention-policy decision, no artifact-content
reads, no evidence-content reads, no source-content reads, no output
verification, no local environment verification, no raw private data reads, no
private/proprietary excerpts, no distribution approval, no rights or license
verification, no decision approval, no risk-check execution, no order
placement, no new market-data adapters, no remote fetching, no broker
integration, no credentials, no account or portfolio data, no live quote
feeds, no paid-vendor market data, no WebSockets, no production endpoints, no
strategy optimization, no delivery scoring, no archive scoring, no handoff
scoring, no distribution scoring, no version scoring, no follow-up scoring, no
decision scoring, no question scoring, no limitation scoring, no appendix
scoring, no artifact scoring, no rights scoring, no risk scoring, no
reproducibility scoring, no coverage scoring, no security ranking, no source
ranking, no allocation advice, no executable advice, no production readiness
claim, no unsupported data redistribution, and no profitability claims.

Maintenance boundary: a future maintenance task may add the local
delivery-notes input kind only within the local/offline report-pack path and
must not add command execution, validation execution, follow-up execution, file
movement, deletion, or transfer, retention-policy decisions, artifact-content
reads, evidence-content reads, source-content reads, output verification,
local environment verification, distribution approval, rights verification,
decision approval, raw local data reads, remote fetches, new adapters,
production endpoints, ranking, allocation, optimization, executable advice, or
production-readiness claims. The active next product checkpoint is Stage 38
offline complement scanner.
