# Codex Long-running Controller

## Objective

Keep `event-driven-market-neutral-trader` safe to continue across Codex
sessions, computers, branches, and future `/goal` runs while preserving the
demo-first, risk-controlled stage plan.

## Context-budget policy

- Read `AGENTS.md`, `docs/current_handoff.md`, and `docs/repo_map.md` first.
- Prefer targeted reads over broad file dumps.
- Use `rg` and `rg --files` for discovery.
- Read implementation files only when the requested stage needs them.
- Keep final reports concise and evidence-backed.

## Skill orchestration policy

- Apply this controller's stage boundary, stop gates, context-budget and
  token-budget rules, and final-report rules on every checkpoint.
- Read only the active `docs/STAGE_PLAN.md` stage section unless a stop gate or
  missing context requires more; do not reread old logs by default.
- Treat optional skills and preset commands as accelerators, not dependencies.
  If a skill is unavailable, uninstalled, renamed, or noisy to invoke, use the
  equivalent checklist and keep moving.
- Limit optional skill use to at most one planning skill before implementation
  and one review skill before PR unless a stop gate triggers deeper review.
- Use Ponytail only for implementation PRs, mainly as a pre-PR
  over-engineering review; skip it for readiness checks and documentation-only
  changes.
- Use Matt Pocock `grill-me` only for ambiguous or high-risk design stages;
  skip it when `docs/STAGE_PLAN.md` already gives complete acceptance criteria.
- Use TDD-style workflow for implementation stages that add behavior.
- Use handoff or compaction only when context is large, before switching
  sessions, or when a stop gate requires preserving state.

## Stage progression policy

- Work on one stage-sized change at a time.
- Confirm the requested stage and stop at that boundary.
- Do not begin the next stage in the same run unless explicitly requested.
- Update handoff and logs before reporting completion.

## PR-sized / commit-sized work policy

- Keep commits reviewable and scoped to the requested stage.
- Avoid unrelated refactors.
- For code changes, include tests in the same stage-sized change.
- For documentation-only stages, do not touch behavior unless required by a
  failing check.

## Conservative auto-merge policy

Codex may not direct-merge to `main`, bypass branch protection, or use admin
override.

Codex may create a pull request and enable GitHub auto-merge only for low-risk
small PRs. A low-risk small PR must be narrow, in scope, fully validated
locally, and free of credentials, production endpoints, order placement,
WebSocket work, strategy optimization, large generated files, dependency
surprises, and compliance ambiguity.

When required GitHub checks or reviews are pending, Codex may enable auto-merge
only if the PR is low-risk and branch protection is clear. GitHub must perform
the final merge only after all required checks and reviews pass.

Codex must not enable auto-merge, and must stop for human review, when any of
these apply:

- no required checks are configured;
- branch protection is absent or unclear;
- merge conflicts exist;
- CI is failing;
- scope is unclear;
- the change is medium or high risk;
- human judgment is needed.

## Stop gates

Stop and report clearly when any of these occur:

- Dirty worktree with unexpected user changes.
- Failing tests that cannot be safely fixed within scope.
- High or medium risk issue.
- Scope conflict.
- Need for credentials, secrets, production endpoint, or external trading
  access.
- Destructive command.
- Live or production trading request.
- Unclear compliance boundary.
- Auto-merge is requested but the PR is not clearly low-risk, protected, and
  locally validated.
- Completion of one stage-sized change.

## Required checks

Run these before final handoff when the environment supports them:

```bash
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
```

For packaging or dependency changes, also run:

```bash
python -m pip install -e ".[dev]"
```

## Logging requirements

- Update `CHANGELOG.md` for stage milestones.
- Update `docs/engineering_log.md` with durable engineering narrative, not raw
  command logs.
- Update `docs/DECISION_LOG.md` when making or changing architectural or product
  decisions.

## Handoff update requirements

Before final handoff for a stage-sized change:

- Update `docs/current_handoff.md`.
- Keep it compact and current.
- Archive the previous handoff only after major stages, following
  `docs/handoff_archive/README.md`.
- Include the next recommended stage and exact next prompt suggestion.

## Final report format

Return:

- Stage completed.
- Git status.
- Branch.
- Commit hash if created.
- Files created.
- Files changed.
- Checks run and results.
- Any issues or assumptions.
- Exact recommended next prompt.
- Risk classification.
- Auto-merge status.

## What not to do

- Do not make profitability claims.
- Do not add credentials or secrets.
- Do not direct-merge to `main`, bypass branch protection, or use admin
  override.
- Do not implement authenticated Kalshi requests before the read-only client
  stage is explicitly requested.
- Do not implement order placement, WebSocket ingestion, strategies, or
  production trading unless a later stage explicitly requests the appropriate
  reviewed work.
- Do not mix exchange-specific adapter code into core models.
- Do not skip tests after functional changes.
