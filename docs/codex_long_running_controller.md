# Codex Long-running Controller

## Objective

Keep `event-driven-market-neutral-trader` safe to continue across Codex
sessions, computers, branches, and future `/goal` runs while preserving the
demo-first, risk-controlled stage plan.

## Context-budget policy

- Read `AGENTS.md`, `docs/current_handoff.md`, and `docs/repo_map.md` first.
- After those first reads, read only this controller, the project Skill, and
  the active `docs/STAGE_PLAN.md` stage section before staged work.
- Prefer targeted reads over broad file dumps.
- Use `rg` and `rg --files` for discovery.
- Read implementation files only when the requested stage needs them.
- Do not read old logs unless the handoff is incomplete or a stop gate requires
  historical evidence.
- Keep final reports concise and evidence-backed.

## Skill orchestration policy

- Apply this controller's stage boundary, stop gates, context-budget and
  token-budget rules, and final-report rules on every checkpoint.
- Use the project Skill for repository-specific staged work before optional
  skills.
- Keep optional skills token-efficient: project Skill and token-budget rules
  always apply, TDD applies to behavior changes, Ponytail review applies before
  publish for implementation diffs, and Matt Pocock `grill-me` applies only for
  ambiguous or high-risk design.
- Treat optional skills and preset commands as accelerators, not dependencies.
  If a skill is unavailable, uninstalled, renamed, or noisy to invoke, use the
  equivalent checklist and keep moving.
- Limit optional skill use to at most one planning skill before implementation
  and one review skill before final merge or PR unless a stop gate triggers
  deeper review.
- Use Ponytail review only for implementation diffs, mainly before final
  merge/push or PR to catch over-engineering; skip it for readiness checks and
  documentation-only changes.
- Use Matt Pocock `grill-me` only for ambiguous or high-risk design stages;
  skip it for simple readiness/docs work and when `docs/STAGE_PLAN.md` already
  gives complete acceptance criteria.
- Use TDD-style workflow for implementation stages that add behavior.
- Use handoff or compaction only when context is large, before switching
  sessions, or when a stop gate requires preserving state.

## Stage progression policy

- Work on one stage-sized change at a time.
- Confirm the requested stage and stop at that boundary.
- In continuous autopilot runs, continue to the next checkpoint after a
  successful publish and clean post-merge verification.
- Outside continuous autopilot runs, do not begin the next stage in the same
  run unless explicitly requested.
- Update handoff and logs before reporting completion.

## Governance audit cadence

- After every three completed checkpoints, run a compact governance audit.
- The audit must check clean/synced `main`, latest `main` CI, open PRs, branch
  protection, required `Validate`, handoff accuracy, stage-plan continuity,
  risk drift, and token/context drift.
- Publish the audit under this controller's publish policy.
- After the audit PR/merge or owner-direct publish completes, wait for `main`
  `Validate`, sync local `main`, verify a clean worktree, reset the checkpoint
  counter, read the updated `docs/current_handoff.md`, and continue to the next
  checkpoint.
- A passing audit is mandatory but non-terminal. Do not emit the final report
  after a passing audit.
- Stop only when the audit finds a real stop gate: high or unclear risk,
  compliance ambiguity, CI failure, unclear branch protection or required
  `Validate`, open PR conflict, merge conflict, remote divergence, stale or
  contradictory handoff that cannot be safely fixed, secrets/credentials or
  production endpoint need, context too large to continue safely, or user
  judgment required.

## PR-sized / commit-sized work policy

- Keep commits reviewable and scoped to the requested stage.
- Avoid unrelated refactors.
- For code changes, include tests in the same stage-sized change.
- For documentation-only stages, do not touch behavior unless required by a
  failing check.

## Publish policy

Default to branch + PR for staged work. Codex may enable GitHub auto-merge only
for low-risk small PRs that are narrow, locally validated, protected by clear
required checks, and free of credentials, production endpoints, order
placement, WebSocket work, live market-making loops, strategy optimization,
large generated files, dependency surprises, and compliance ambiguity.

Codex may skip PR creation and use an owner-direct fast path only when every
condition below is true:

- `gh` is authenticated as `minqiyang`.
- `origin` points to `minqiyang/market-neutral-trading-research`.
- Work starts from a clean local branch synced with `origin/main`.
- Work is done on a `codex/` branch, not directly on `main`.
- Local validation passes.
- Branch `Validate` CI passes, or the repo clearly supports equivalent
  pre-main validation.
- Risk is low or medium, never high or unclear.
- The change has no secrets, production endpoints, WebSocket work, live
  market-making loop, strategy optimization, large generated files, dependency
  surprises, or compliance ambiguity.
- There is no open PR for the branch and no remote divergence or merge
  conflict.
- The final merge to `main` is a normal push only: no force push, no admin
  override, and no branch-protection bypass command.

If any owner-direct condition is false, Codex must create a PR or stop for
human review. High-risk or unclear work must always stop for human review.

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
- High-risk or unclear work.
- Owner-direct fast path is requested but any required condition is false.
- Auto-merge is requested but the PR is not clearly low-risk, protected, and
  locally validated.
- Completion of one stage-sized change only when the run is not explicitly in
  continuous autopilot mode.

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

Emit a final report only when Codex actually stops. Do not emit a final report
after a passing non-terminal governance audit.

Return:

- Stage completed.
- Git status.
- Branch.
- Commit hash if created.
- PR URL if created.
- Merge or push status.
- Files created.
- Files changed.
- Checks run and results.
- CI status when applicable.
- Any issues or assumptions.
- Exact recommended next prompt.
- Risk classification.
- Auto-merge or owner-direct fast-path status.

## What not to do

- Do not make profitability claims.
- Do not add credentials or secrets.
- Do not bypass branch protection, force push, or use admin override.
- Do not direct-merge or push to `main` unless every owner-direct fast-path
  condition is satisfied.
- Do not implement authenticated Kalshi requests before the read-only client
  stage is explicitly requested.
- Do not implement order placement, WebSocket ingestion, strategies, or
  production trading unless a later stage explicitly requests the appropriate
  reviewed work.
- Do not mix exchange-specific adapter code into core models.
- Do not skip tests after functional changes.
