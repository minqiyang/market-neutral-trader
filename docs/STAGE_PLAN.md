# Stage Plan

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

Deliverables: risk checks, execution log format, demo-only smoke test path, and
blocked-path tests.

Acceptance checks: every execution action passes risk checks, `LIVE_DISABLED`
cannot place orders, logs are auditable, and tests cover rejection paths.

Explicit non-goals: no production trading, no broad strategy deployment, no
credential storage, and no compliance bypass.

## Stage 6: Inventory-aware demo market maker in dry-run/demo only

Purpose: connect normalized books, fair value, quote generation, risk checks,
and demo/paper execution in a controlled workflow.

Deliverables: inventory-aware quote adjustments, dry-run/demo loop, risk gates,
structured logs, and run summaries.

Acceptance checks: dry-run works without credentials, demo mode is explicitly
configured, risk checks gate all actions, and limitations are reported.

Explicit non-goals: no production deployment, no aggressive liquidity behavior,
no spoofing-like behavior, and no performance guarantees.

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
