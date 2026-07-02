# Portfolio Summary

`event-driven-market-neutral-trader` is a Python 3.12 research platform for
same-market YES/NO complement-parity workflows in prediction markets. It is
built to demonstrate trading-systems engineering discipline without enabling
production trading.

## What It Demonstrates

- Exchange-agnostic core models using `Decimal` for price, quantity, cash, fee,
  and PnL values.
- Kalshi-style YES/NO order book normalization into a canonical YES-side book.
- Local-first replay and JSONL workflows for deterministic research artifacts.
- Complement-parity candidate scanning with explicit fees, slippage,
  failed-leg reserve assumptions, and data-quality blockers.
- Paper-only proposal, ledger, risk, manual approval, monitoring, Demo dry-run,
  reconciliation, and rolling validation layers.
- A documented Stage 52 private-live gate that remains disabled in the public
  repository.

## Architecture

The public architecture is layered from safe observation toward guarded review:

1. Recorder: local fixtures and guarded read-only market-data capture.
2. Replay/simulator: deterministic order book rebuilds, fill assumptions,
   slippage, stale-data handling, and failed-leg scenarios.
3. Paper ledger/reconciliation: source-hashed paper records and mismatch
   tracking.
4. Risk/manual approval/monitoring: risk decisions, single-use manual approvals,
   kill-switch state, and daily validation reports.
5. Kalshi Demo dry-run: Demo request previews and local/mock reconciliation.
6. Disabled private-live gate: public placeholder that returns disabled status.

## Safety Boundary

The repository is not a production trading system, prediction bot, LLM trader,
investment-advice product, or guaranteed-profit system. It contains no
production endpoints, credentials, wallets, broker integration, live
user-order channel, production order path, auto-trading loop, or live order
placement.

The private-live gate remains disabled until private evidence exists outside
the public repo: 30-90 days live read-only data, 30+ days paper history, zero
unresolved reconciliation mismatches, validated fee/slippage assumptions,
successful demo lifecycle coverage, kill-switch and manual approval drills,
and legal/platform compliance review.

## Validation Status

The public test suite covers the implemented workflow through Stage 52. Stage
51 adds rolling 7/30/90-day validation summaries over local paper/demo
artifacts, but the public repository still marks validation incomplete because
the required private evidence is not present.

## Reviewer Takeaway

The project demonstrates staged system design, bounded adapters,
deterministic replay, risk-first workflow design, auditability, and clear
public/private boundaries for trading research infrastructure.
