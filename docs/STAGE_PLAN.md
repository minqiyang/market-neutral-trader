# Stage Plan

## Completed stage record

These records summarize the locally completed stages before Stage 6. They are
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
- Avoid aggressive liquidity behavior; no quote stuffing, spoofing-like
  behavior, self-trading, wash trading, or misleading liquidity.

Risk and execution-gate requirements:

- Every candidate action must pass through the Stage 5 risk decision before any
  adapter method can run.
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

## Stage 8: Polymarket US market-data research adapter, if compliant and available

Purpose: explore a second prediction-market data adapter for research only.

Deliverables: compliance review note, market-data adapter, fixtures, parser
tests, and docs on availability and limitations.

Acceptance checks: no trading path exists, adapter stays separate from core, and
use is compliant with availability and platform rules.

Explicit non-goals: no Polymarket trading, no bypassing restrictions, no wallet
integration, and no production execution.

## Stage 9: U.S. equities research adapter, paper/research only

Purpose: extend the research architecture toward equities data without enabling
live equities trading.

Deliverables: equities research adapter, local fixtures, parser tests, and
paper/research documentation.

Acceptance checks: no live execution path exists, data assumptions are
documented, and core workflow remains exchange-agnostic.

Explicit non-goals: no live equities orders, no broker integration for
production trading, no credentials in repo, and no claims of guaranteed
performance.
