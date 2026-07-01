# Risk Policy

## Scope

This policy governs the repository's demo, paper, simulation, and future
execution-safety work. It does not authorize live trading.

## Non-negotiable controls

- No production trading by default.
- No credentials, tokens, private keys, API keys, or wallet keys in the repo.
- No order placement in the current stage.
- No manipulative trading behavior, including spoofing, wash trading,
  self-trading, quote stuffing, or misleading liquidity.
- No attempts to bypass platform rules, KYC, regional restrictions, rate
  limits, or compliance boundaries.

## Execution mode policy

The core execution modes are:

- `BACKTEST`
- `PAPER`
- `DEMO`
- `LIVE_DISABLED`

There is no enabled live mode. Future execution code must reject or avoid any
path that would place a live order unless a later, separately reviewed stage
explicitly changes the policy and adds full risk checks, logging, and tests.
The Stage 52 private live gate design is documented in
`docs/private_live_execution_gate.md`; the public repository gate remains
disabled and does not add production order code.
The safety-gate diagram in `docs/visual_overview.md` is a visual summary of
the same disabled-live policy.

## Risk engine expectations

Before any future execution engine exists, the project must define and test
limits for position size, order quantity, notional exposure, cash usage, and
loss controls. Every strategy output must produce an auditable risk decision
before it can become an execution action.

## Simulation expectations

Every backtest or simulation must include:

- Fees.
- Slippage or fill assumptions.
- Liquidity assumptions.
- Known limitations.
- Separation between simulated and observed performance.

Simulation results must not be described as guaranteed future profits.
