# event-driven-market-neutral-trader

`event-driven-market-neutral-trader` is a demo-first, risk-controlled trading
research platform for event-driven prediction markets. The current research
priority is narrow same-market YES/NO complement parity for Kalshi-style binary
contracts, with a core architecture intended to remain portable across future
market-data and research adapters.

The project is designed for simulation, execution safety, and workflow
engineering. It is not a guaranteed-profit trading bot, and it intentionally
rejects that framing. Market making and event-driven trading involve adverse
selection, fees, latency, incomplete information, fill uncertainty, liquidity
constraints, and compliance boundaries. The purpose of this repository is to
demonstrate professional system design, not to promise trading outcomes.

## Why orderbook normalization comes first

Prediction-market venues do not always expose orderbooks in the same shape as
traditional equities or futures markets. Kalshi-style binary orderbooks expose
YES bids and NO bids rather than direct YES asks. Before quoting, simulation,
risk checks, or PnL attribution can be trusted, the venue-specific book must be
converted into a canonical YES-side bid/ask representation:

```text
best_yes_bid = max(yes_dollars)
implied_yes_ask = 1 - max(no_dollars)
yes_spread = implied_yes_ask - best_yes_bid
yes_mid = (best_yes_bid + implied_yes_ask) / 2
```

That normalization layer is the first implemented adapter boundary in this
repo. It is covered by deterministic local-fixture tests and does not require
credentials or live API access.

## Why complement parity is first

Complement-parity research checks whether the YES and NO sides of one binary
market imply an inconsistent same-market relationship:

```text
gross_edge = best_yes_bid + best_no_bid - 1
```

This is not directional prediction, market making, investment advice, or a
guaranteed-profit claim. Apparent candidates still require explicit fees,
slippage, liquidity, stale-book handling, failed-leg reserves, replay evidence,
and manual risk review before they can become even paper candidates.

## Why Kalshi Demo is first

Kalshi Demo is the initial integration target because it provides a realistic
prediction-market API shape while keeping the first external workflow in a
non-production environment. The configured demo REST base URL is:

```text
https://external-api.demo.kalshi.co/trade-api/v2
```

The demo WebSocket endpoint is documented for later stages, but WebSocket
support is intentionally not implemented in the current foundation:

```text
wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2
```

## Live trading is disabled by default

The only live-related execution mode in the core model is `LIVE_DISABLED`.
There is no production order-placement path in this stage. Any future execution
work must be separately reviewed, must pass through a risk engine, must be
covered by tests, and must comply with venue rules and applicable regulations.

## Extensibility

The core package keeps trading-domain models exchange-agnostic, while
venue-specific parsing lives under `src/edmn_trader/adapters`. That boundary is
intended to support later research extensions such as:

- Polymarket US market-data adapters, without implementing Polymarket trading.
- U.S. equities research adapters, without implementing live equities trading.
- Backtests and simulations with explicit fees, slippage, fill assumptions, and
  limitations.

## Local setup

Use Python 3.12.

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

Replay the included local Kalshi-style fixture:

```bash
python scripts/01_replay_orderbook_fixture.py
```

The replay script prints the canonical YES-side best bid, implied ask, spread,
mid, and aggregate bid/ask depth.

Record and replay deterministic offline snapshots from local fixtures:

```bash
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage3_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage3_snapshots.jsonl
```

Run the dry-run quote engine over replayed snapshots:

```bash
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage4_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage4_snapshots.jsonl
```

## Project workflow and logs

Long-running project continuity is tracked in:

- `PROJECT_SPEC.md`
- `CHANGELOG.md`
- `docs/current_handoff.md`
- `docs/repo_map.md`
- `docs/codex_long_running_controller.md`
- `docs/STAGE_PLAN.md`
- `docs/DECISION_LOG.md`
- `docs/engineering_log.md`

## Current scope

Implemented:

- Initial Python package and documentation foundation.
- Exchange-agnostic core dataclasses using `Decimal`.
- Kalshi fixed-point orderbook normalization from local fixtures.
- Guarded read-only Kalshi Demo REST client for public markets and orderbooks,
  tested with mocked HTTP transport.
- Decimal-safe JSONL snapshot storage and deterministic replay metrics for
  offline research workflows.
- Baseline fair-value model and inventory-aware dry-run quote engine over
  normalized/replayed books.
- Offline Decimal-only complement-parity candidate model for same-market YES
  and NO best bids, with explicit fee/slippage/reserve assumptions and manual
  review flags.
- Unit tests for normal conversion, empty sides, multiple levels, precision,
  invalid prices, locked or crossed book detection, client response validation,
  client error handling, snapshot roundtrips, replay ordering, fair value, and
  dry-run quote generation, plus offline complement-candidate decisions.

Not implemented:

- Authenticated Kalshi requests.
- Order placement.
- WebSocket ingestion.
- Strategy optimization.
- Fill simulation and PnL attribution.
- Live complement-arbitrage scanning.
- Executable order intents.
- Production trading.
