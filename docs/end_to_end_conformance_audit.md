# End-to-End Conformance Audit

## Scope

Audit date: 2026-07-02. Updated by PR #108 follow-up on 2026-07-02.

Original audit baseline: `origin/main` at `b3e556f` (`Clarify demo connector
risk policy boundary (#107)`). Follow-up baseline: `origin/main` at `6e581f7`
(`Add end-to-end conformance audit (#108)`).

This audit checks whether the implemented Stage 35-52 mainline still matches
the intended same-market YES/NO complement-parity research roadmap from
fixture/live-readonly market data through the disabled private-live gate.

## Executive Answer

Did implementation diverge from the roadmap mainline? No high-severity
implementation divergence was found. The mainline is aligned end to end as a
disabled-live, risk-gated research workflow. PR #108 review found three
follow-up issues: stale-doc evidence was incomplete, Stage 49 mocked-submit
wording was imprecise, and Demo submit opt-in did not require a provided Demo
reconciliation state. This follow-up fixes those issues.

Mainline status counts:

| Status | Count |
| --- | ---: |
| aligned | 12 |
| partial | 0 |
| drift | 0 |
| overreach | 0 |
| stale-doc | 1 |
| needs-human-review | 0 |

## Mainline Trace Table

| Flow step | Planned artifact | Observed source | Observed tests | Observed script | Observed docs | Status | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Fixture/live-readonly market data | Read-only market-data capture with explicit opt-in and no credentials by default | `src/edmn_trader/data/live_events.py`; `src/edmn_trader/adapters/kalshi/readonly_recorder.py`; `src/edmn_trader/adapters/polymarket_us/market_recorder.py` | `tests/test_live_event_recorder.py`; `tests/test_kalshi_readonly_recorder.py`; `tests/test_polymarket_market_recorder.py` | `scripts/39_mock_live_event_recorder.py`; `scripts/40_kalshi_readonly_recorder.py`; `scripts/41_polymarket_market_recorder.py` | `docs/ARBITRAGE_ROADMAP.md`; `docs/STAGE_PLAN.md`; README | aligned | Low. Guarded read-only path; no order-placement imports found in recorder code. |
| Normalized/recorded order book | Raw events and normalized snapshots with deterministic replay metadata | `src/edmn_trader/data/snapshots.py`; `src/edmn_trader/data/book_rebuild.py`; `src/edmn_trader/adapters/kalshi/orderbook.py` | `tests/test_kalshi_orderbook.py`; `tests/test_snapshots_jsonl.py`; `tests/test_book_rebuild.py` | `scripts/01_replay_orderbook_fixture.py`; `scripts/42_rebuild_orderbooks.py` | `docs/STAGE_PLAN.md`; `docs/repo_map.md` | aligned | Low. Gap/stale/out-of-order flags are explicit. |
| Complement candidate scanner | Same-market YES/NO complement candidates as audit/paper research records | `src/edmn_trader/arb/complement.py`; `src/edmn_trader/arb/scanner.py` | `tests/test_complement_arb.py`; `tests/test_complement_scanner.py` | `scripts/23_scan_complement_arb.py` | `docs/ARBITRAGE_ROADMAP.md`; `docs/complement_scanner.md`; README | aligned | Low. Records are non-executable and Decimal-backed. |
| Fee/slippage/failed-leg simulation | Explicit fees, slippage, latency shock, failed-leg reserve | `src/edmn_trader/fees/base.py`; `src/edmn_trader/fees/kalshi.py`; `src/edmn_trader/arb/fill_simulation.py` | `tests/test_fee_models.py`; `tests/test_fill_simulation.py` | `scripts/43_simulate_taker_fill.py` | `docs/ARBITRAGE_ROADMAP.md`; `docs/STAGE_PLAN.md` | aligned | Low. Missing/unknown fees block paper candidates. |
| Paper proposal | Paper-only two-leg proposal linking candidate and simulation hashes | `src/edmn_trader/arb/paper_engine.py` | `tests/test_paper_engine.py` | `scripts/44_paper_complement_engine.py` | `docs/STAGE_PLAN.md`; README | aligned | Low. No venue submission or executable intent. |
| Paper ledger replay | Deterministic local ledger from proposal/fill/settlement records | `src/edmn_trader/arb/paper_ledger.py` | `tests/test_paper_ledger.py` | `scripts/45_replay_paper_ledger.py` | `docs/STAGE_PLAN.md`; README | aligned | Low. Reconciliation mismatches are recorded instead of ignored. |
| Risk decision | Reject stale/gap/missing-fee/edge/exposure/open-order/loss/mismatch/kill-switch blockers; otherwise manual review required | `src/edmn_trader/arb/risk.py` | `tests/test_complement_risk.py` | `scripts/46_complement_risk.py` | `docs/ARBITRAGE_ROADMAP.md`; `docs/RISK_POLICY.md`; README | aligned | Low. Clear decisions still require manual approval. |
| Manual approval | Expiring, hash-bound, single-use local approval records | `src/edmn_trader/arb/approval.py` | `tests/test_manual_approval.py` | `scripts/47_manual_approval.py` | `docs/STAGE_PLAN.md`; README | aligned | Low. Approval records are paper manual-review metadata. |
| Kalshi Demo dry-run/guarded connector | Demo-only dry-run preview by default; submit opt-in requires credentials, injected HTTP client, risk/approval/ledger gates, and a provided clean Demo reconciliation state | `src/edmn_trader/adapters/kalshi/demo_connector.py` | `tests/test_kalshi_demo_connector.py` | `scripts/49_kalshi_demo_connector.py` | `docs/RISK_POLICY.md`; `docs/ARBITRAGE_ROADMAP.md`; README | aligned | Low/medium. Authenticated Demo boundary exists but remains Demo-only, dry-run default, and mocked through HTTP tests. |
| Demo reconciliation | Append-only local/mock event replay linked to connector audit hash; missing or mismatched reconciliation blocks Demo submit opt-in while dry-run preview remains available | `src/edmn_trader/adapters/kalshi/demo_reconciliation.py` | `tests/test_kalshi_demo_reconciliation.py`; `tests/test_kalshi_demo_connector.py` | `scripts/50_kalshi_demo_reconciliation.py` | `docs/STAGE_PLAN.md`; README | aligned | Low. Submit eligibility is false on mismatch and submit opt-in now requires a clean reconciliation record. |
| Rolling validation report | Local 7/30/90-day paper/demo summaries with unmet private-live prerequisites | `src/edmn_trader/arb/monitoring.py`; `src/edmn_trader/arb/long_term_validation.py` | `tests/test_daily_validation_report.py`; `tests/test_long_term_validation.py` | `scripts/48_daily_validation_report.py`; `scripts/51_long_term_validation.py` | `docs/STAGE_PLAN.md`; README | aligned | Low. Reports do not mark production readiness. |
| Disabled private-live gate | Public placeholder fails closed; no production endpoint/order code | `src/edmn_trader/execution/private_live_gate.py` | `tests/test_private_live_gate.py` | Importable function only: `attempt_private_live_execution()` | `docs/private_live_execution_gate.md`; `docs/RISK_POLICY.md`; README | aligned | Low. Public live execution remains disabled. |

## Transition Evidence

### 1. Fixture/Live-Readonly Market Data -> Normalized/Recorded Order Book

- Planned intent: capture fixture or explicitly opted-in read-only market data,
  then preserve raw-to-normalized traceability.
- Source-code entry points: `LiveMarketDataEvent`,
  `record_mock_websocket_events`, `record_kalshi_readonly_orderbook`,
  `rebuild_orderbooks_from_events`.
- Data model / record shape: `live_market_data_event`, normalized snapshot
  JSONL, rebuild frame records with `book_hash`, `sequence`, and
  `data_quality_flags`.
- Script or CLI entry point: `scripts/39_mock_live_event_recorder.py`,
  `scripts/40_kalshi_readonly_recorder.py`, `scripts/42_rebuild_orderbooks.py`.
- Tests proving the transition: recorder opt-in and production-boundary tests,
  snapshot roundtrip tests, rebuild gap/stale/out-of-order tests.
- Docs that describe the transition: Stage 39-42 records in
  `docs/STAGE_PLAN.md`, `docs/ARBITRAGE_ROADMAP.md`, README workflow diagram.
- Conformance status: aligned.
- Recommendation: no code change. Keep live-readonly scripts opt-in and mocked
  by default in validation.

### 2. Normalized/Recorded Order Book -> Complement Candidate Scanner

- Planned intent: scan local fixture/snapshot books for same-market YES/NO
  complement parity without executable order intent.
- Source-code entry points: `compute_kalshi_complement_candidate`,
  `compute_canonical_yes_side_cross_candidate`, `scan_fixture_file`,
  `scan_snapshot_jsonl_file`.
- Data model / record shape: `offline_complement_research_candidate` with
  `research_use: audit_or_paper_research_record_only`, Decimal string fields,
  `decision`, `flags`, and `rejection_reasons`.
- Script or CLI entry point: `scripts/23_scan_complement_arb.py`.
- Tests proving the transition: scanner consumes snapshot JSONL, preserves
  Decimal precision, blocks missing/unknown fees, and avoids executable order
  intents.
- Docs that describe the transition: `docs/complement_scanner.md`,
  `docs/ARBITRAGE_ROADMAP.md`, Stage 36-38 records in `docs/STAGE_PLAN.md`.
- Conformance status: aligned.
- Recommendation: no code change.

### 3. Complement Candidate Scanner -> Fee/Slippage/Failed-Leg Simulation

- Planned intent: keep candidate eligibility conservative after explicit fee,
  slippage, liquidity, latency, and failed-leg assumptions.
- Source-code entry points: `FeeEstimate`, Kalshi/Polymarket fee helpers,
  `FillSimulationInput`, `simulate_taker_fill`.
- Data model / record shape: `offline_taker_fill_simulation` with filled sizes,
  completed pair size, failed-leg quantity, simulated edge, and flags.
- Script or CLI entry point: `scripts/43_simulate_taker_fill.py`.
- Tests proving the transition: fee-model tests for supplied/missing/unknown
  status and fill-simulation tests for FOK, IOC, partial fill, slippage,
  latency, failed-leg reserve, determinism, and negative input rejection.
- Docs that describe the transition: Stage 37 and Stage 43 records in
  `docs/STAGE_PLAN.md`; roadmap fee and simulator stages.
- Conformance status: aligned.
- Recommendation: no code change.

### 4. Fee/Slippage/Failed-Leg Simulation -> Paper Proposal

- Planned intent: convert only local candidate/simulation records into
  non-executable paper proposal records with locked source hashes.
- Source-code entry points: `propose_paper_order`, `hash_record`.
- Data model / record shape: `paper_complement_order_proposal` with
  `proposal_id`, `candidate_hash`, `simulation_hash`, YES/NO `legs`, and
  `risk_preview`.
- Script or CLI entry point: `scripts/44_paper_complement_engine.py`.
- Tests proving the transition: paper-engine tests verify hash preservation,
  non-paper candidate blocking in risk preview, missing completed-pair blocking,
  deterministic output, and CLI pairing.
- Docs that describe the transition: Stage 44 record in `docs/STAGE_PLAN.md`;
  README paper workflow.
- Conformance status: aligned.
- Recommendation: no code change.

### 5. Paper Proposal -> Paper Ledger Replay

- Planned intent: replay paper proposal/fill/settlement events from zero and
  expose mismatch state.
- Source-code entry points: `replay_paper_ledger`.
- Data model / record shape: `paper_ledger_state` with `source_hashes`,
  `positions`, Decimal PnL/fee totals, and `reconciliation_mismatch_count`.
- Script or CLI entry point: `scripts/45_replay_paper_ledger.py`.
- Tests proving the transition: ledger tests cover fills, fees, settlement,
  mismatch reasons, deterministic JSONL/Markdown, CLI, and Decimal precision.
- Docs that describe the transition: Stage 45 record in `docs/STAGE_PLAN.md`;
  README.
- Conformance status: aligned.
- Recommendation: no code change.

### 6. Paper Ledger Replay -> Risk Decision

- Planned intent: block stale data, data gaps, missing/unknown fee, insufficient
  edge, exposure/open-order/daily-loss breaches, reconciliation mismatches, and
  kill switch; do not directly approve execution.
- Source-code entry points: `ComplementRiskInput`, `evaluate_complement_risk`.
- Data model / record shape: `complement_risk_decision_v2` with
  `decision: reject|manual_review_required`, `approved: false`,
  `manual_approval_required: true`, `reasons`, and Decimal exposure fields.
- Script or CLI entry point: `scripts/46_complement_risk.py`.
- Tests proving the transition: risk tests cover all named blockers, clear
  manual-review path, Decimal precision, deterministic output, CLI, and
  negative limit rejection.
- Docs that describe the transition: Stage 46 in `docs/STAGE_PLAN.md`,
  `docs/RISK_POLICY.md`, roadmap.
- Conformance status: aligned.
- Recommendation: no code change.

### 7. Risk Decision -> Manual Approval

- Planned intent: create and verify local manual approvals only after a clear
  manual-review-required risk decision; keep approvals expiring and single-use.
- Source-code entry points: `create_pending_approval`,
  `verify_manual_approval`.
- Data model / record shape: `manual_approval_pending` and
  `manual_approval_decision` with `approval_id`, `proposal_id`,
  `candidate_hash`, `approved`, `reusable: false`, and reason codes.
- Script or CLI entry point: `scripts/47_manual_approval.py`.
- Tests proving the transition: manual-approval tests cover hash preservation,
  one-time approval, expiry, hash mismatch, reuse, rejected-risk blocking,
  deterministic output, and CLI.
- Docs that describe the transition: Stage 47 in `docs/STAGE_PLAN.md`; README.
- Conformance status: aligned.
- Recommendation: no code change.

### 8. Manual Approval -> Kalshi Demo Dry-Run/Guarded Connector

- Planned intent: require proposal/risk/approval/ledger consistency before
  Demo preview or Demo submit; default to dry-run; reject production URL.
  Actual Demo submit opt-in additionally requires a provided clean Demo
  reconciliation state. Submit-path tests use mocked HTTP.
- Source-code entry points: `KalshiDemoConnectorConfig`,
  `preview_or_submit_kalshi_demo`, `_validate_risk_decision`,
  `_validate_manual_approval`, `_validate_ledger_state`.
- Data model / record shape: `kalshi_demo_submission_preview` with
  `proposal_id`, `candidate_hash`, `approval_id`, `dry_run`,
  request previews, redacted credential markers, and status.
- Script or CLI entry point: `scripts/49_kalshi_demo_connector.py`.
- Tests proving the transition: demo-connector tests cover dry-run without
  credentials or reconciliation state, production URL rejection, FOK/IOC limit,
  tiny limits, risk gate, approval expiry/reuse/hash mismatch, ledger
  reconciliation gate, submit opt-in rejection when reconciliation is missing
  or mismatched, clean reconciliation for mocked HTTP submit, submit
  success/reject/error/timeout logging, redaction, and CLI.
- Docs that describe the transition: Stage 49 in `docs/STAGE_PLAN.md`,
  `docs/RISK_POLICY.md`, README.
- Conformance status: aligned.
- Recommendation: no code change.

### 9. Kalshi Demo Dry-Run/Guarded Connector -> Demo Reconciliation

- Planned intent: replay local/mock Demo lifecycle events and block Demo submit
  opt-in when reconciliation is missing or mismatched.
- Source-code entry points: `reconcile_kalshi_demo_events`,
  `require_demo_reconciliation_submit_eligible`.
- Data model / record shape: `kalshi_demo_reconciliation_state` with
  `audit_record_hash`, `proposal_id`, `candidate_hash`, `approval_id`,
  `submit_eligible`, `mismatch_count`, order states, and mismatch records.
- Script or CLI entry point: `scripts/50_kalshi_demo_reconciliation.py`.
- Tests proving the transition: reconciliation tests cover accepted/rejected/
  cancel/error/timeout/backfill states, idempotent duplicate fills, missing and
  conflicting events, mismatch blocking, append-only JSONL, and CLI.
  Connector tests additionally prove dry-run remains available without
  reconciliation state and submit opt-in requires clean reconciliation.
- Docs that describe the transition: Stage 50 in `docs/STAGE_PLAN.md`; README.
- Conformance status: aligned.
- Recommendation: no code change.

### 10. Demo Reconciliation -> Rolling Validation Report

- Planned intent: aggregate local paper/demo records into 7/30/90-day reports
  while marking private-live prerequisites unmet.
- Source-code entry points: `build_daily_validation_report`,
  `build_rolling_validation_report`.
- Data model / record shape: `daily_validation_report` and
  `rolling_validation_report` with research-use labels, counts, Decimal
  metrics, mismatch/gap/kill-switch counts, and unmet prerequisites.
- Script or CLI entry point: `scripts/48_daily_validation_report.py`,
  `scripts/51_long_term_validation.py`.
- Tests proving the transition: daily and rolling validation tests cover local
  aggregation, deterministic JSONL/JSON/Markdown, no production-ready claim,
  CLI, invalid input rejection, and Decimal precision.
- Docs that describe the transition: Stage 48 and Stage 51 in
  `docs/STAGE_PLAN.md`; README.
- Conformance status: aligned.
- Recommendation: no code change.

### 11. Rolling Validation Report -> Disabled Private-Live Gate

- Planned intent: keep public live gate disabled until private prerequisites
  and reviews exist outside the public repo.
- Source-code entry points: `attempt_private_live_execution`,
  `PrivateLiveGateDecision`.
- Data model / record shape: `private_live_execution_gate` with
  `status: disabled`, `production_trading_enabled: false`,
  `executable_order_intent: false`, and unmet prerequisites.
- Script or CLI entry point: no root CLI; importable public placeholder only.
- Tests proving the transition: private-live tests verify disabled status,
  unmet prerequisites, fail-closed behavior, and absence of endpoint,
  credential, or order payload fields.
- Docs that describe the transition: `docs/private_live_execution_gate.md`,
  `docs/RISK_POLICY.md`, README.
- Conformance status: aligned.
- Recommendation: no code change.

## Core Invariant Checks

| Invariant | Evidence | Status | Recommendation |
| --- | --- | --- | --- |
| Same-market YES/NO complement parity remains the main strategy target | Roadmap primary target; `ComplementArbInput` requires `market_id`, YES/NO best bids; scanner produces complement records. | aligned | No change. |
| Candidates are audit/paper research records, not trade recommendations | Scanner emits `research_use: audit_or_paper_research_record_only`; tests assert no executable order intent. | aligned | No change. |
| Missing/unknown fee blocks `paper_candidate` | `complement.py` and scanner add `missing_fee_model` / `unknown_fee_model`; fee and scanner tests cover both. | aligned | No change. |
| Stale/data-gap/mismatch conditions block forward progress where intended | Scanner flags stale/invalid books; rebuild flags gaps/staleness; risk rejects stale/gap/mismatch; missing or mismatched Demo reconciliation blocks submit opt-in. | aligned | No change. |
| Decimal is used for money/probability logic | Core arb, fee, simulation, ledger, risk, connector, reconciliation, monitoring, and rolling validation modules import/use `Decimal`; tests preserve precision. | aligned | No change. |
| Candidate/proposal/manual-approval/audit/reconciliation hashes or immutable references remain linked | Paper proposals lock candidate/simulation hashes; ledger carries source hashes; manual approvals bind `proposal_id`/`candidate_hash`; connector validates matching hashes; reconciliation stores `audit_record_hash`. | aligned | No change. |
| Manual approval is required before Demo submit path | Connector validates `manual_approval_pending` and `manual_approval_decision` before preview/submit. | aligned | No change. |
| Demo connector remains dry-run default and demo-only | `KalshiDemoConnectorConfig.submit_opt_in` defaults false; Demo base URL validation rejects production URL; dry-run tests need no credentials or reconciliation state; submit tests use mocked HTTP and require clean reconciliation. | aligned | No change. |
| Production URL is rejected | `KalshiDemoConnectorConfig` and Kalshi read-only recorder tests reject production boundaries. | aligned | No change. |
| Secrets are not logged | Demo connector loads auth from environment, stores redacted credential markers, and redacts secret-like keys; payload safety rejects secret-like market-data payload keys. | aligned | No change. |
| Private-live gate remains disabled | `attempt_private_live_execution()` always returns disabled with `production_trading_enabled: false`. | aligned | No change. |
| No production endpoint, wallet, broker integration, real-money execution, live order placement, investment advice, or profitability claim exists | README, roadmap, risk policy, and private gate docs all state public disabled-live boundary; targeted source review found no wallet/broker/production execution path. | aligned | Keep wording conservative. |

## PR #106 Risk-Policy Recheck

Concern rechecked: whether `docs/RISK_POLICY.md` order-placement wording is now
precise or still stale/ambiguous after Stage 49.

Finding: precise after this follow-up. The policy now says Stage 49 is allowed
only as demo/paper research infrastructure, dry-run by default, explicit opt-in
for its guarded Demo-only submit path, mocked HTTP tests during validation,
required clean Demo reconciliation state for submit, Demo-only base URL, no
production endpoint, and no real-money execution. That matches
`KalshiDemoConnectorConfig`, `preview_or_submit_kalshi_demo`, and
`tests/test_kalshi_demo_connector.py`.

Status: aligned.

Recommendation: no follow-up needed for PR #106 wording.

## PR #108 Review Resolution

PR #108 review finding: include stale `docs/STAGE_PLAN.md` evidence.
Resolution: this audit now records the stale pending-commit metadata for Stages
35-39, 48, and 50-52. `docs/STAGE_PLAN.md` now classifies those pending lines
as historical stage-branch metadata, not implementation drift.

PR #108 review finding: qualify reconciliation hard stop.
Resolution: actual Demo submit opt-in now requires a provided clean Demo
reconciliation state and rejects missing or mismatched reconciliation. Dry-run
preview still works without credentials or reconciliation state.

PR #108 review finding: mark mocked-submit wording as stale.
Resolution: Stage 49 wording now says the submit path is Kalshi Demo-only and
mocked in tests; it is no longer described as a generally mocked path.

## Drift Register

### High Severity

None.

### Medium Severity

None.

### Low Severity

None.

### Stale-Doc Only

1. `docs/STAGE_PLAN.md` still contains historical `Commit: pending on ...`
   branch metadata for completed Stages 35-39, 48, and 50-52.
   - Roadmap/doc claim: completed-stage records list those stages as complete
     but preserve old pending branch metadata.
   - Code or test evidence: merged PR history, source modules, tests, scripts,
     handoff, changelog, and `docs/roadmap_conformance_audit.md` all show
     Stage 35-52 implementation is complete.
   - Mismatch: metadata is stale if read as current commit status.
   - Recommended remediation: no runtime change. This follow-up adds a
     `docs/STAGE_PLAN.md` commit metadata note classifying those lines as
     historical stage-branch notes, not implementation drift.

Resolved in this follow-up:

- `PROJECT_SPEC.md` no longer says the repository is at Stage 4/5; it now
  describes the completed Stage 52 public state and the next human review
  boundary.
- Stage 49 wording now distinguishes the Demo-only submit path from the mocked
  HTTP tests used to validate it.
- Demo submit opt-in now rejects missing or mismatched reconciliation state,
  while dry-run preview remains available without credentials or
  reconciliation state.

### No-Fix-Needed Observations

- `docs/RISK_POLICY.md` Stage 49 wording is now aligned with the guarded Demo
  connector boundary.
- The Stage 52 public private-live gate is intentionally an importable disabled
  placeholder, not a full CLI.
- Demo submit-path validation uses mocked HTTP tests; the path itself remains
  Kalshi Demo-only, opt-in, risk/manual approval/ledger/reconciliation gated,
  and outside production/private-live execution.

## Validation Evidence

Current follow-up validation run:

- `/opt/homebrew/bin/python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"`:
  passed.
- `PYTHONPATH=src .venv/bin/pytest tests/test_kalshi_demo_connector.py -q`:
  passed, 14 tests.
- `PYTHONPATH=src .venv/bin/pytest`: passed, 257 tests.
- `PYTHONPATH=src .venv/bin/ruff check .`: passed.
- `git diff --check`: passed.
- `PYTHONPATH=src .venv/bin/python scripts/01_replay_orderbook_fixture.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python scripts/49_kalshi_demo_connector.py --help`:
  passed.

Original PR #108 representative smoke chain retained as audit context:

- fixture snapshot/replay: `.venv/bin/python scripts/01_replay_orderbook_fixture.py`
- complement scanner: `.venv/bin/python scripts/23_scan_complement_arb.py ...`
- taker simulation: `.venv/bin/python scripts/43_simulate_taker_fill.py ...`
- paper engine: `.venv/bin/python scripts/44_paper_complement_engine.py ...`
- paper ledger replay: `.venv/bin/python scripts/45_replay_paper_ledger.py ...`
- risk check: `.venv/bin/python scripts/46_complement_risk.py ...`
- manual approval workflow: `.venv/bin/python scripts/47_manual_approval.py ...`
- Kalshi Demo connector dry-run:
  `.venv/bin/python scripts/49_kalshi_demo_connector.py ...`
- demo reconciliation:
  `.venv/bin/python scripts/50_kalshi_demo_reconciliation.py ...`
- rolling validation:
  `.venv/bin/python scripts/51_long_term_validation.py ...`
- private-live disabled gate check:
  `.venv/bin/python -c "from edmn_trader.execution.private_live_gate import attempt_private_live_execution; d=attempt_private_live_execution(); assert d.status == 'disabled' and d.production_trading_enabled is False and d.executable_order_intent is False"`

Smoke result: `candidate=paper_candidate`, `demo_dry_run=True`,
`reconciliation=True`.

## Follow-Up PRs Recommended

None for PR #108 review feedback.
