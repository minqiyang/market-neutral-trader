# Roadmap Conformance Audit

Audit date: 2026-07-01

Scope: completed Stage 35-52 roadmap work, the six-layer architecture, public
README/Risk/Roadmap claims, handoff continuity docs, changelog, scripts, tests,
and source layout.

This audit is documentation-only. It does not change runtime behavior, add
trading functionality, enable live trading, introduce credentials, or make
profitability, investment-advice, or production-readiness claims.

## Summary

| Area | Aligned | Partial | Drift | Overreach | Stale-doc | Needs human review |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stages 35-52 | 9 | 0 | 0 | 0 | 9 | 0 |
| Six architecture layers | 6 | 0 | 0 | 0 | 0 | 0 |
| High-severity findings | 0 | 0 | 0 | 0 | 0 | 0 |

Final judgment: roadmap/code conformance is partially aligned because the source,
tests, scripts, and safety boundary match the Stage 35-52 intent, while
`docs/STAGE_PLAN.md` still has stale "pending on branch" commit metadata for
Stages 35-39, 48, and 50-52. A follow-up resolved the old `docs/RISK_POLICY.md`
"No order placement in the current stage" wording because it was ambiguous
after Stage 49's guarded Kalshi Demo connector.

## Status Key

- Aligned: implementation, tests, scripts, and docs match the roadmap intent.
- Partial: roadmap intent is mostly met, with non-blocking implementation or
  evidence gaps.
- Drift: observed behavior conflicts with the roadmap or public safety boundary.
- Overreach: implementation goes beyond the authorized stage boundary.
- Stale-doc: behavior and safety are aligned, but a continuity document has
  stale metadata or wording.
- Needs human review: evidence is insufficient or private evidence is required.

## Stage Audit

| Stage | Planned intent | Expected artifacts | Source-code evidence | Test evidence | Script/CLI evidence | Documentation evidence | Status | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | Reset the roadmap around narrow same-market YES/NO complement parity. | Roadmap update only. | No source behavior expected. | No test behavior expected. | No script behavior expected. | `docs/ARBITRAGE_ROADMAP.md`, `docs/STAGE_PLAN.md`, `docs/engineering_log.md`, `CHANGELOG.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |
| 36 | Add deterministic complement candidate schema. | Candidate model and focused tests. | `src/edmn_trader/arb/complement.py`, `src/edmn_trader/arb/__init__.py`. | `tests/test_complement_arb.py`. | No standalone CLI expected. | `docs/STAGE_PLAN.md`, `docs/ARBITRAGE_ROADMAP.md`, `docs/current_handoff.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |
| 37 | Add venue fee model scaffold without trading. | Fee protocols, Kalshi/Polymarket fee estimates, candidate fee fields. | `src/edmn_trader/fees/base.py`, `src/edmn_trader/fees/kalshi.py`, `src/edmn_trader/fees/polymarket_us.py`, `src/edmn_trader/fees/__init__.py`, `src/edmn_trader/arb/complement.py`. | `tests/test_fee_models.py`. | No standalone CLI expected. | `docs/STAGE_PLAN.md`, `docs/engineering_log.md`, `CHANGELOG.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |
| 38 | Add offline complement scanner. | Scanner module, root wrapper, package entry point, scanner docs. | `src/edmn_trader/arb/scanner.py`, `src/edmn_trader/scripts/scan_complement_arb.py`. | `tests/test_complement_scanner.py`. | `scripts/23_scan_complement_arb.py`. | `docs/complement_scanner.md`, `docs/STAGE_PLAN.md`, `docs/engineering_log.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |
| 39 | Add live-event schema and mocked recorder harness only. | Normalized event records, payload redaction, mocked recorder CLI. | `src/edmn_trader/data/live_events.py`, `src/edmn_trader/data/payload_safety.py`, `src/edmn_trader/scripts/mock_live_event_recorder.py`. | `tests/test_live_event_recorder.py`. | `scripts/39_mock_live_event_recorder.py`. | `docs/STAGE_PLAN.md`, `docs/engineering_log.md`, `docs/current_handoff.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |
| 40 | Add guarded Kalshi Demo read-only recorder. | Demo-only read-only adapter, explicit opt-in, normalized/raw output. | `src/edmn_trader/adapters/kalshi/readonly_recorder.py`, `src/edmn_trader/scripts/kalshi_readonly_recorder.py`. | `tests/test_kalshi_readonly_recorder.py`. | `scripts/40_kalshi_readonly_recorder.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |
| 41 | Add Polymarket public market recorder. | Public market-channel recorder and normalized output. | `src/edmn_trader/adapters/polymarket_us/market_recorder.py`, `src/edmn_trader/scripts/polymarket_market_recorder.py`. | `tests/test_polymarket_market_recorder.py`. | `scripts/41_polymarket_market_recorder.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |
| 42 | Rebuild order books from recorded events. | Deterministic book rebuild logic and replay CLI. | `src/edmn_trader/data/book_rebuild.py`, `src/edmn_trader/scripts/rebuild_orderbooks.py`. | `tests/test_book_rebuild.py`. | `scripts/42_rebuild_orderbooks.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |
| 43 | Add fill/slippage/failed-leg simulation. | Non-executing simulator for candidate stress tests. | `src/edmn_trader/arb/fill_simulation.py`, `src/edmn_trader/scripts/simulate_taker_fill.py`. | `tests/test_fill_simulation.py`. | `scripts/43_simulate_taker_fill.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/engineering_log.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |
| 44 | Add paper proposal engine. | Paper candidate workflow from scanner/simulator output. | `src/edmn_trader/arb/paper_engine.py`, `src/edmn_trader/scripts/paper_complement_engine.py`. | `tests/test_paper_engine.py`. | `scripts/44_paper_complement_engine.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/engineering_log.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |
| 45 | Add append-only paper ledger. | Local ledger replay, snapshots, realized/unrealized paper accounting. | `src/edmn_trader/arb/paper_ledger.py`, `src/edmn_trader/scripts/paper_ledger.py`. | `tests/test_paper_ledger.py`. | `scripts/45_replay_paper_ledger.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/engineering_log.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |
| 46 | Add risk engine v2 and kill-switch style controls. | Paper/demo risk decisions, exposure/loss/data-health checks. | `src/edmn_trader/arb/risk.py`, `src/edmn_trader/scripts/complement_risk.py`. | `tests/test_complement_risk.py`. | `scripts/46_complement_risk.py`. | `docs/RISK_POLICY.md`, `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |
| 47 | Add manual approval record path. | Manual approval metadata for paper/demo review, not execution. | `src/edmn_trader/arb/approval.py`, `src/edmn_trader/scripts/manual_approval.py`. | `tests/test_manual_approval.py`. | `scripts/47_manual_approval.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/engineering_log.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |
| 48 | Add monitoring and daily validation report. | Local observational validation report and health summary. | `src/edmn_trader/arb/monitoring.py`, `src/edmn_trader/scripts/daily_validation_report.py`. | `tests/test_daily_validation_report.py`. | `scripts/48_daily_validation_report.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |
| 49 | Add guarded Kalshi Demo connector preview path. | Demo-only dry-run default, Demo submit path mocked in tests, audit record output. | `src/edmn_trader/adapters/kalshi/demo_connector.py`, `src/edmn_trader/scripts/kalshi_demo_connector.py`. | `tests/test_kalshi_demo_connector.py`. | `scripts/49_kalshi_demo_connector.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Aligned | Prefer "Kalshi Demo dry-run connector" in future public summaries to avoid executable-trading ambiguity. |
| 50 | Add local Kalshi Demo reconciliation replay. | Reconcile mocked/local Demo connector outcomes and block later eligibility on mismatches. | `src/edmn_trader/adapters/kalshi/demo_reconciliation.py`, `src/edmn_trader/scripts/kalshi_demo_reconciliation.py`. | `tests/test_kalshi_demo_reconciliation.py`. | `scripts/50_kalshi_demo_reconciliation.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |
| 51 | Add long-term paper/demo validation framework. | Rolling validation aggregation with unmet private-live prerequisites. | `src/edmn_trader/arb/long_term_validation.py`, `src/edmn_trader/scripts/long_term_validation.py`. | `tests/test_long_term_validation.py`. | `scripts/51_long_term_validation.py`. | `docs/STAGE_PLAN.md`, `docs/repo_map.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |
| 52 | Add disabled private-live gate design and public guard. | Disabled placeholder, explicit false live flags, private evidence checklist. | `src/edmn_trader/execution/private_live_gate.py`. | `tests/test_private_live_gate.py`. | No standalone root wrapper expected. | `docs/private_live_execution_gate.md`, `docs/RISK_POLICY.md`, `README.md`, `docs/STAGE_PLAN.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Stale-doc | Keep behavior unchanged; replace stale pending commit metadata in `docs/STAGE_PLAN.md`. |

## Six-Layer Architecture Audit

| Layer | Planned intent | Expected artifacts | Source-code evidence | Test evidence | Script/CLI evidence | Documentation evidence | Status | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1. Live/read-only market data recorder foundation | Capture public/read-only market data into normalized local records without trading credentials. | Mocked recorder, guarded Kalshi Demo read-only recorder, Polymarket public recorder, payload safety. | `src/edmn_trader/data/live_events.py`, `src/edmn_trader/data/payload_safety.py`, `src/edmn_trader/adapters/kalshi/readonly_recorder.py`, `src/edmn_trader/adapters/polymarket_us/market_recorder.py`. | `tests/test_live_event_recorder.py`, `tests/test_kalshi_readonly_recorder.py`, `tests/test_polymarket_market_recorder.py`. | `scripts/39_mock_live_event_recorder.py`, `scripts/40_kalshi_readonly_recorder.py`, `scripts/41_polymarket_market_recorder.py`. | `docs/ARBITRAGE_ROADMAP.md`, `README.md`, `docs/repo_map.md`, `docs/current_handoff.md`. | Aligned | No follow-up needed. |
| 2. Replay + simulator | Rebuild books and simulate fills/slippage/failed legs offline. | Order-book rebuild and fill simulation modules with deterministic tests. | `src/edmn_trader/data/book_rebuild.py`, `src/edmn_trader/arb/fill_simulation.py`, `src/edmn_trader/scripts/simulate_taker_fill.py`. | `tests/test_book_rebuild.py`, `tests/test_fill_simulation.py`. | `scripts/42_rebuild_orderbooks.py`, `scripts/43_simulate_taker_fill.py`. | `docs/ARBITRAGE_ROADMAP.md`, `README.md`, `docs/repo_map.md`, `docs/engineering_log.md`. | Aligned | No follow-up needed. |
| 3. Paper ledger + reconciliation | Convert candidates into paper proposals, append paper ledger records, and reconcile local Demo outcomes. | Paper engine, paper ledger, local Demo reconciliation. | `src/edmn_trader/arb/paper_engine.py`, `src/edmn_trader/arb/paper_ledger.py`, `src/edmn_trader/adapters/kalshi/demo_reconciliation.py`. | `tests/test_paper_engine.py`, `tests/test_paper_ledger.py`, `tests/test_kalshi_demo_reconciliation.py`. | `scripts/44_paper_complement_engine.py`, `scripts/45_replay_paper_ledger.py`, `scripts/50_kalshi_demo_reconciliation.py`. | `docs/ARBITRAGE_ROADMAP.md`, `README.md`, `docs/repo_map.md`, `docs/current_handoff.md`. | Aligned | No follow-up needed. |
| 4. Risk engine + kill switch + manual approval + monitoring | Gate paper/demo research through risk checks, manual approval metadata, and observational validation. | Risk engine, approval records, monitoring reports. | `src/edmn_trader/arb/risk.py`, `src/edmn_trader/arb/approval.py`, `src/edmn_trader/arb/monitoring.py`. | `tests/test_complement_risk.py`, `tests/test_manual_approval.py`, `tests/test_daily_validation_report.py`. | `scripts/46_complement_risk.py`, `scripts/47_manual_approval.py`, `scripts/48_daily_validation_report.py`. | `docs/RISK_POLICY.md`, `docs/ARBITRAGE_ROADMAP.md`, `README.md`, `docs/repo_map.md`. | Aligned | No follow-up needed. |
| 5. Kalshi Demo connector + demo reconciliation | Keep Demo connector behavior dry-run by default, Demo-only, and mocked in tests; reconcile outcomes locally. | Guarded Demo connector, audit records, local reconciliation blocker. | `src/edmn_trader/adapters/kalshi/demo_connector.py`, `src/edmn_trader/adapters/kalshi/demo_reconciliation.py`. | `tests/test_kalshi_demo_connector.py`, `tests/test_kalshi_demo_reconciliation.py`. | `scripts/49_kalshi_demo_connector.py`, `scripts/50_kalshi_demo_reconciliation.py`. | `README.md`, `docs/ARBITRAGE_ROADMAP.md`, `docs/RISK_POLICY.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Aligned | Prefer public wording that emphasizes dry-run default and mocked HTTP submit-path tests. |
| 6. Private-live disabled gate | Preserve public/private boundary and keep all live execution disabled in the public repo. | Disabled gate object, false live flags, private evidence checklist. | `src/edmn_trader/execution/private_live_gate.py`. | `tests/test_private_live_gate.py`. | No execution CLI expected. | `docs/private_live_execution_gate.md`, `docs/RISK_POLICY.md`, `README.md`, `docs/current_handoff.md`, `CHANGELOG.md`. | Aligned | No follow-up needed. |

## Drift Checks

| Check | Result | Evidence | Severity | Recommendation |
| --- | --- | --- | --- | --- |
| Implemented behavior not described in docs | No high-severity drift found. Stage 35-52 behavior is mapped in `docs/repo_map.md`, `docs/current_handoff.md`, `docs/engineering_log.md`, and `CHANGELOG.md`. | Source/test/script evidence above. | None | No runtime change. |
| Documented claims not backed by code/tests | No high-severity drift found. Each completed implementation stage has matching source and test evidence. | Stage and layer audit tables above. | None | No runtime change. |
| Stale README, roadmap, or risk text | README, roadmap, risk docs, and private gate docs now match the disabled-live boundary. `docs/STAGE_PLAN.md` still has stale "pending on branch" commit metadata for Stages 35-39, 48, and 50-52. | `README.md`, `docs/ARBITRAGE_ROADMAP.md`, `docs/RISK_POLICY.md`, `docs/private_live_execution_gate.md`, `docs/STAGE_PLAN.md`. | Low | Follow up with a docs-only metadata refresh. |
| Public/private boundary ambiguity | No high-severity ambiguity found. A follow-up clarified that production/private-live order placement remains prohibited, while the Stage 49 Kalshi Demo connector is demo/paper research infrastructure, dry-run by default, explicit opt-in, Demo-only, and not real-money execution. | `README.md`, `docs/private_live_execution_gate.md`, `docs/RISK_POLICY.md`, `docs/current_handoff.md`. | Resolved low | No runtime change. |
| Production/live trading leakage | No high-severity leakage found. Public gate is disabled and live flags remain false. | `src/edmn_trader/execution/private_live_gate.py`, `tests/test_private_live_gate.py`, `docs/private_live_execution_gate.md`. | None | No runtime change. |
| Credential, wallet, broker, production endpoint, or order-placement leakage | No high-severity leakage found in the audited Stage 35-52 surfaces. The Demo connector remains guarded and tested with mocked/local paths. | `src/edmn_trader/adapters/kalshi/demo_connector.py`, `tests/test_kalshi_demo_connector.py`, `docs/RISK_POLICY.md`. | None | No runtime change. |
| Profitability, investment-advice, or production-readiness overclaim | No high-severity overclaim found. Public docs repeat that this is not a guaranteed-profit system, investment-advice product, or production trading system. | `README.md`, `docs/ARBITRAGE_ROADMAP.md`, `docs/RISK_POLICY.md`, `docs/private_live_execution_gate.md`. | None | No runtime change. |
| Naming that implies executable trading where the system is paper/demo/dry-run | Non-blocking wording risk remains around "Kalshi Demo authenticated connector" in historical stage labels. Current README already says "Kalshi Demo dry-run connector." | `docs/ARBITRAGE_ROADMAP.md`, `docs/STAGE_PLAN.md`, `README.md`. | Low | Prefer "Kalshi Demo dry-run connector" in future public-facing summaries. |

Resolved stale/ambiguous boundary note: the old `docs/RISK_POLICY.md` sentence
"No order placement in the current stage" could be read as conflicting with
Stage 49's guarded Kalshi Demo connector. The policy now distinguishes
prohibited production/private-live order placement from the allowed Stage 49
demo/paper research connector path.

## Recommended Follow-Up PRs

1. Docs-only metadata refresh: replace stale "pending on branch" commit entries
   in `docs/STAGE_PLAN.md` for Stages 35-39, 48, and 50-52 with merged
   commit/PR references.
2. Optional public wording polish: standardize public-facing summaries on
   "Kalshi Demo dry-run connector" while preserving internal implementation
   names where they are already established.

## Audit Boundary Confirmation

This audit found no high-severity drift, no production endpoint addition, no
credential/wallet/broker integration, no live order placement, no new trading
feature, no strategy optimization, no investment advice, and no profitability
claim. The public repo remains a disabled-live, risk-gated research platform
for same-market YES/NO complement parity.
