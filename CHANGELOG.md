# Changelog

All notable project milestones are recorded here. This project follows the
spirit of Keep a Changelog, with stage-oriented entries instead of release
numbers while the repository is still in early research scaffolding.

## Unreleased

- Stage 5 is expected to add risk checks before any demo execution smoke test.
- Order placement beyond explicitly risk-gated demo smoke tests, WebSocket
  ingestion, production trading, and profitability claims remain out of scope
  until separately reviewed.

## Stage 4 - Fair-value and quote engine dry-run - 2026-06-11

### Added

- Baseline midpoint fair-value model with deterministic one-sided book
  fallbacks.
- Dry-run quote engine that combines fair value, current orderbook spread,
  tick/price boundaries, quantity, and bounded inventory skew.
- Non-executable dry-run order-intent objects labeled `dry_run_only`.
- Replay-based dry-run quote script for Stage 3 JSONL snapshots.
- Offline deterministic tests for fair value, one-sided fallbacks, quote
  generation, inventory skew, tick/price boundaries, dry-run intent safety, and
  replay-script output.

### Safety

- Quote outputs are inspection-only and do not call adapters, authenticate,
  place orders, cancel orders, modify orders, simulate fills, or claim
  profitability.

### Validation

- Required checks include `pytest`, `ruff check .`,
  `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage4_snapshots.jsonl`,
  `python scripts/03_replay_snapshots.py --input /tmp/edmn_stage4_snapshots.jsonl`,
  and `python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage4_snapshots.jsonl`.

## Stage 3 - Local replay simulator and read-only data recorder - 2026-06-11

### Added

- Offline `MarketDataSnapshot` model for recorded market/orderbook data with
  exchange, ticker, observed timestamp, local recorded timestamp, source type,
  schema version, normalized orderbook, optional raw payload, notes, and tags.
- Decimal-safe JSONL read/write/append helpers for deterministic snapshot
  storage.
- Replay session and cursor metrics for best bid, best ask, spread, mid, depth,
  and level counts.
- Local fixture-to-snapshot recorder script and JSONL replay summary script.
- Offline tests for JSONL roundtrip, Decimal precision, malformed JSONL,
  append behavior, strict replay ordering, replay metrics, and fixture
  conversion.

### Safety

- Snapshot validation rejects raw payload keys that look like credentials,
  headers, signatures, tokens, or secrets.
- No network calls, order placement, WebSocket ingestion, strategy
  optimization, production endpoint, or live trading path.

### Validation

- Required checks include `pytest`, `ruff check .`,
  `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage3_snapshots.jsonl`,
  and `python scripts/03_replay_snapshots.py --input /tmp/edmn_stage3_snapshots.jsonl`.

## Stage 2 - Read-only Kalshi Demo market-data client - 2026-06-11

### Added

- Guarded `httpx`-based Kalshi Demo REST client for public read-only market
  metadata and market orderbook endpoints.
- Demo-only base URL guard using
  `https://external-api.demo.kalshi.co/trade-api/v2`.
- Local response fixtures and mocked HTTP tests for markets, orderbooks,
  normalized orderbook output, HTTP status failures, transport failures,
  malformed JSON, malformed response shapes, and empty orderbooks.

### Safety

- No credentials, authentication headers, order placement, WebSocket ingestion,
  strategy logic, production endpoint, or live trading path.

### Validation

- Required checks remain `pytest`, `ruff check .`, and
  `python scripts/01_replay_orderbook_fixture.py`.

## Stage 1.5 - Long-running controller and project memory - 2026-06-11

### Added

- Project memory and continuity docs for staged Codex work.
- Compact current handoff, repo map, long-running controller, decision log,
  staged plan, engineering narrative, and handoff archive guidance.
- Root project specification for product scope, module boundaries, non-goals,
  and acceptance standards.

### Safety

- Reaffirmed demo-first operation, no credentials, no live trading, no order
  placement, no WebSocket, and no strategy implementation in this stage.

### Validation

- Required checks remain `pytest`, `ruff check .`, and
  `python scripts/01_replay_orderbook_fixture.py`.

## Stage 1 - Kalshi-style orderbook normalization with fixtures - 2026-06-10

### Added

- Exchange-agnostic core models using `Decimal`.
- Kalshi fixed-point orderbook normalization from local fixtures.
- Deterministic tests for basic YES/NO conversion, empty sides, multiple
  levels, Decimal precision, invalid prices, and locked or crossed books.
- Local replay script for the included orderbook fixture.

### Safety

- No live API calls, authenticated requests, WebSocket ingestion, or order
  placement.

## Stage 0 - Repository foundation - 2026-06-10

### Added

- Initial Python 3.12 project structure, package metadata, test/lint setup, and
  source/test directories.
- README, AGENTS guidance, risk policy, roadmap, project charter, and resume
  narrative.
- `.env.example` with demo endpoint defaults and no secrets.

### Safety

- Rejected guaranteed-profit framing and established live trading as disabled
  by default.
