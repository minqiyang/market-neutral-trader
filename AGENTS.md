# AGENTS.md

## Project identity

This repository is `event-driven-market-neutral-trader`.

It is a demo-first, risk-controlled trading research platform for event-driven
prediction markets. The first target is Kalshi-style binary prediction markets.
The long-term architecture should support additional market-data and execution
adapters, but production trading is not enabled by default.

This is not a guaranteed-profit trading bot.

## Skill-first workflow

Before making non-trivial changes, check whether a relevant Skill exists. Use
the project-specific Skill at `.agents/skills/event-driven-market-neutral-trader`
for implementation, review, documentation, risk-policy, adapter, and testing
work in this repository.

For staged work, use `docs/codex_long_running_controller.md` for optional
skill and preset-command orchestration; optional skills should not block the
checkpoint when the equivalent checklist is clear.

For continuous staged autopilot, compact governance audits after every three
completed checkpoints are mandatory but non-terminal when they pass. Continue
after a passing audit once `main` validation, local sync, clean state, and the
updated handoff are verified.

## First-read workflow

For future Codex runs, read these before broad exploration:

1. `AGENTS.md`
2. `docs/current_handoff.md`
3. `docs/repo_map.md`

Use targeted reads after that. Do not dump the whole repository into context
unless the task truly requires it.

## PR and merge policy

Use `docs/codex_long_running_controller.md` for PR, auto-merge, and
owner-direct fast-path workflow rules. Codex must not bypass branch protection,
force push, use admin override, or direct-merge/push to `main` unless every
owner-direct fast-path condition in the controller is satisfied. GitHub
auto-merge may be enabled only for clearly low-risk small PRs that meet the
controller policy. Passing governance audits do not by themselves require a
final report or pause.

## Continuity docs

- `PROJECT_SPEC.md`: stable product and technical spec.
- `docs/current_handoff.md`: latest compact project handoff.
- `docs/repo_map.md`: context-budget map and targeted read guide.
- `docs/codex_long_running_controller.md`: long-running staged workflow rules.
- `docs/STAGE_PLAN.md`: staged roadmap, deliverables, checks, and non-goals.
- `docs/engineering_log.md`: human-readable engineering narrative.
- `CHANGELOG.md`: external-facing milestone log.

## Core rules

1. Do not make profitability claims.
2. Do not implement production trading unless explicitly requested in a later,
   separately reviewed stage.
3. Do not store credentials, API keys, private keys, wallet keys, tokens, or
   secrets.
4. Do not bypass platform rules, rate limits, regional restrictions, KYC, or
   compliance requirements.
5. Do not implement manipulative trading behavior.
6. Do not place orders unless:
   - the task explicitly asks for demo/paper execution,
   - the risk engine exists,
   - execution mode is not `LIVE_DISABLED`,
   - all risk checks pass,
   - and the code path is covered by tests.
7. Always keep exchange-specific code inside `src/edmn_trader/adapters`.
8. Keep core trading models exchange-agnostic.
9. Use `Decimal` for prices, quantities, cash, fees, and PnL.
10. Add or update tests for every functional change.

## Development commands

Use Python 3.12.

Recommended commands:

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

Prefer small, reviewable changes and run tests after changes.
