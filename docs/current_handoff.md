# Current Handoff

## D2E-F1 channel-scoped subscription identity

The first owner-controlled post-D2E Real5M stopped fail-closed after separate
public-channel acknowledgments used orderbook SID `1` and trade SID `2`. The
D2B rebuilder had treated both control frames as one segment-wide identity, so
the trade acknowledgment invalidated the later valid orderbook snapshot.

D2E-F1 keeps subscription generation, binding ID, acknowledgment state, and
native SID scoped by channel. Only the `orderbook_delta` binding can establish
D2B identity; trade control/data rows remain durable D2C evidence without
mutating orderbook state. An unexpected orderbook SID is excluded and cannot
silently create a new segment; only explicit orderbook resubscription does so.
Raw v2 rows written before these optional provenance fields remain readable.
Runtime and validator summaries independently expose the channel bindings.
The post-review correction adds an explicit identity-model marker, validates
coherent binding IDs/generations for new runtime rows, matches acknowledgments
to their native request ID, and rejects a plural-channel acknowledgment that
ambiguously carries one SID. Historical unmarked rows remain compatibility
evidence only.

This fix is fixture-only until a separately authorized post-fix Real5M. It does
not weaken thresholds, use credentials or market network, or add any order
path. Public live trading remains disabled.

## Round 8J-B discovery reliability

Demo discovery now performs bounded market pagination before deduplicated,
batched core-event hydration. It caches events per run, uses single-event
fallback only for missing batch members, bounds retryable failures, and marks
incomplete coverage explicitly. Core event completeness is category plus title;
the official event schema does not require `event_type`. The canary lifecycle
rules themselves remain unchanged.

## Round 8J-A canary profile

The public lifecycle selector now distinguishes `smoke`, `canary`, and
`seven_day` profiles. A 1,800-second canary uses a 3,600-second safety buffer,
requires complete event metadata, rejects sports/match-like and early-close
markets, and persists profile provenance in the manifest. This remains Kalshi
Demo read-only with the public live gate disabled and no order-write behavior.

## D2E runtime integration notice

D2E closes the fail-closed runtime assembly gap found by the owner-controlled
Real5M preflight. New `kalshi-ws-smoke` and `kalshi-ws-campaign` runs select
`edmn.kalshi.ws.runtime.v2`, route D2A envelopes through D2B/D2C, persist exact
runtime records through D2D, and expose independent timing, freshness,
sequence, rebuild, lifecycle, durability, and safety dimensions to the
validator and monitor. Legacy `v2.readonly_campaign.v1` remains readable but
is not selected for new WebSocket runs.

The D2 validator derives critical counts and dimensions from append-chained
runtime records, the monitor blocks on validator failure, subscription
acknowledgment is connection-local across reconnects, and excluded markets
cannot refresh selected-market freshness. Runtime artifacts also preserve the
evaluated smoke/canary/seven-day selection record.

Fresh review correction round 2 additionally requires every applicable
connection segment to carry its own sequence/rebuild evidence, binds channel
acknowledgment to command `1` and both public channels, supports detached-HEAD
deployment provenance, preserves blocked-discovery policy metadata, and makes
crash-recovered artifacts validator/monitor consumable without relaunch.
Correction round 3 also cross-checks checkpoint counts/offsets, validates the
exact threshold policy, rate-limits failed lifecycle polling attempts, and
rejects nested private account/order/fill fields before persistence.
The continuation pass also reconciles complete crash-tail rows, independently
replays D2B during validation, applies the lifecycle limiter at shutdown, and
records nested subscription errors as typed rejections.
Runtime timing includes startup/final disconnect boundaries and start-to-first
freshness gaps, while persisted HTTP(S) Git provenance strips credential-bearing
URL components.
The latest adversarial correction also makes evidence callback failures
terminal, binds D2A rows to ordered per-connection acknowledgments, rejects
nonempty run roots and private metadata, collects provenance from the imported
repository, and recovers finalization-to-manifest crash windows.
Runtime memory and open-status writes are bounded: per-frame hashes stay in the
chain while summaries keep only an aggregate/latest hash, and open metadata is
updated on checkpoints, segment changes, or 60-second intervals. Split channel
acknowledgments and rotation crashes before successor creation are covered.
The durable launch checkpoint binds market selection, lifecycle deadline,
channels, code provenance, and explicit pricing semantics. Validation derives
subscription PASS from persisted raw acknowledgments, keeps trade SIDs from
resetting orderbook state, streams terminal/recovery replay under the 100k
memory gate, and reports no-book freshness as unknown.
Typed connection acknowledgment cannot substitute for durable raw channel
frames or precede them. Segment paths are root-contained, every distinct nested
segment artifact is inventoried, partial rotation successors block recovery
before mutation, and running monitor snapshots expose and act on observed
transport, lifecycle, sequence, and rebuild state.

This checkpoint is software-only. Tests use mocked WebSocket and lifecycle
transports. No VPS, credential, campaign, private raw data, production endpoint,
order path, or real market network was used. Replay qualification remains
unknown/false and the public live gate remains disabled.

## D2D classifier and durability notice

As of 2026-07-10, Phase 0A has passed and `origin/main` remains the authoritative
public source state. D2B and D2C passed independent review and merged as PRs
#121 and #122. The owner-authorized D2D delivery adds orthogonal evidence
classification, timestamp-derived duration, incremental append chains, atomic
checkpoints/summaries, close hashing, rotation, crash recovery, and a mandatory
100k synthetic performance gate.

The bounded VPS snapshot smoke proves transport snapshot receipt only. It does
not prove native sequence continuity, real-stream rebuild integrity, replay
qualification, or duration evidence. Generic monitor `OK_PAPER`,
`campaign_evidence_valid`, and legacy `gap_count=0` values are not overall
evidence gates. D2D never promotes transport into sequence/rebuild/duration or
replay evidence. Open segments expose checkpoint-bounded integrity only;
closed-file hashes appear only at close/recovery; recovered history never
enters a fresh snapshot-required segment. No market network, campaign,
credential, private raw data, retention deletion, or private-live action is
part of this checkpoint. Older conflicting text is historical and noncanonical.

## Current project state

The repository contains a Python 3.12 package for a demo-first,
risk-controlled event-driven prediction-market research platform. Current
implemented code includes exchange-agnostic core models, Kalshi-style
fixed-point orderbook normalization, a guarded read-only Kalshi Demo REST
client, local fixtures, mocked HTTP tests, Decimal-safe JSONL snapshot storage,
deterministic offline replay metrics, a fair-value/quote-engine dry run,
risk-gated fake-adapter demo execution smoke infrastructure, a finite Stage 6
market-maker replay workflow, an offline Stage 7 research report workflow, a
fixture-first Polymarket US public market-data adapter, a fixture-first SEC
EDGAR public fundamentals adapter, and an offline Stage 10 paper research
report pack with a Stage 11 local source inventory section and Stage 12 local
report-input manifest support, plus Stage 13 local run-comparison report-input
metadata, Stage 14 local validation-summary report-input metadata, and Stage
15 local review-notes report-input metadata, Stage 16 local methodology-notes
report-input metadata, Stage 17 local data-dictionary report-input metadata,
Stage 18 local citation-index report-input metadata, and Stage 19 local
term-glossary report-input metadata, plus Stage 20 local assumption-register
report-input metadata and Stage 21 local coverage-matrix report-input
metadata, plus Stage 22 local reproducibility-checklist report-input metadata
and Stage 23 local risk-review report-input metadata, plus Stage 24 local
data-rights-review report-input metadata, plus Stage 25 local
artifact-inventory report-input metadata, plus Stage 26 local appendix-index
report-input metadata, plus Stage 27 local limitation-register report-input
metadata, plus Stage 28 local open-questions report-input metadata, plus Stage
29 local decision-log report-input metadata, plus Stage 30 local follow-up
register report-input metadata, plus Stage 31 local version-notes report-input
metadata and Stage 32 local distribution-checklist report-input metadata.
Stage 33 local handoff-notes report-input metadata is implemented.
Stage 34 local archive-notes report-input metadata is implemented.
The active product direction has been redirected from continued report-input
metadata expansion to narrow same-market YES/NO complement parity research.
The repository now includes `docs/ARBITRAGE_ROADMAP.md`, the first offline
Decimal-only complement candidate model under `src/edmn_trader/arb/`, and a
Stage 37 venue fee estimate scaffold under `src/edmn_trader/fees/`, plus a
Stage 38 offline complement scanner that emits deterministic JSONL and
Markdown research reports from local fixture/snapshot-style inputs, plus a
Stage 39 live-event schema and local mocked WebSocket-style recorder harness,
plus a Stage 40 guarded Kalshi Demo read-only recorder, plus a Stage 41
guarded Polymarket US market-channel recorder, plus Stage 42 order book
rebuild and replay consistency, plus Stage 43 taker fill, slippage, and
failed-leg simulation, plus Stage 44 paper complement proposal engine, plus
Stage 45 paper ledger state machine, plus Stage 46 risk engine v2, plus Stage
47 manual approval workflow, plus Stage 48 monitoring and daily validation
report, plus Stage 49 guarded Kalshi Demo connector previews and Demo
submit-path coverage mocked in tests, plus Stage 50 local Kalshi Demo
reconciliation replay,
plus Stage 51 offline rolling paper/demo validation framework, plus Stage 52
private live gate design and disabled public guard. Round 8B adds public
read-only campaign lifecycle gates: market metadata now records status and
close/expiration fields, seven-day WebSocket campaign planning rejects missing
market metadata, finalized/closed/settled markets invalidate campaign evidence,
and the monitor surfaces market lifecycle plus separate liveness fields. Round
8C-D1 corrects Demo market discovery by normalizing API status values such as
`active`, following bounded cursor pagination, prioritizing current quoted
liquidity before orderbook probes, preserving raw status metadata, and emitting
distinct HTTP, parse, no-open-market, and no-eligible-market blockers. The
five-minute profile uses a 15-minute safety buffer; the seven-day profile keeps
the campaign duration plus 24-hour buffer. D2A adds the versioned raw envelope,
and D2B adds fixture-only native incremental rebuild and canonical YES frames.
D2C adds fixture-only public trade, lifecycle, and connection evidence. D2D
adds fixture-only classifier, durability, recovery, rotation, and performance
gates.

## Last completed stage

D2A-D2D are merged. D2E integrates those contracts into the reviewed read-only
runtime entrypoint with mocked end-to-end coverage and retains the disabled-live
boundary. Deployment and any Real5M authorization remain separate owner gates.

## Current delivery checkpoint

D2D adds a narrow fixture-only software evidence layer. Twelve dimensions stay
orthogonal; actual duration comes from timestamps; exact serialized records use
an O(1) append chain; checkpoints and summaries use flush/fsync/atomic replace;
close computes one full-file hash; 64 MiB/one-hour rotation records metadata;
and crash recovery validates complete tails, removes only a partial final row,
and requires a fresh segment/snapshot. It adds no real replay qualification,
network, credential, campaign, deletion, or order behavior.

## Stage plan status

`docs/STAGE_PLAN.md` contains a completed-stage record ledger for Stages 0,
1, 1.5, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, Stage 35 arbitrage
roadmap reset, Stage 36 complement candidate schema, Stage 37 venue fee model
scaffold, Stage 38 offline complement scanner, and Stage 39 live event schema
with mocked WebSocket harness, and Stage 40 guarded Kalshi Demo read-only
recorder, Stage 41 guarded Polymarket US market-channel recorder, and Stage
42 order book rebuild and replay consistency, and Stage 43 taker fill,
slippage, and failed-leg simulator, and Stage 44 paper complement arbitrage
engine, Stage 45 paper ledger state machine, Stage 46 risk engine v2, and
Stage 47 manual approval workflow, Stage 48 monitoring and daily validation
report, Stage 49 Kalshi Demo authenticated connector, and Stage 50 demo
reconciliation, Stage 51 long-term paper/demo validation framework, and Stage
52 private live gate design and disabled public guard. The
ledger records purpose, known commit hashes, files/modules
added, validation commands, status, next-stage boundary, and safety status for
each completed stage. Stage 35-52 and D2A-D2D are complete. D2E is the active
separate delivery and mandatory stop boundary for the autonomous software
program. No seven-day recorder launch is authorized by this handoff.

Report-input metadata expansion from Stages 11 through 34 is now
maintenance-only. The previously clarified local delivery-notes report input is
preserved as maintenance backlog, not the active next product checkpoint.

`docs/ARBITRAGE_ROADMAP.md` is now the active long-range roadmap for
same-market YES/NO complement parity research through the private live gate
design boundary. The first model is deterministic and offline:
`ComplementArbInput`, `ComplementArbCandidate`, `ComplementArbDecision`,
`compute_kalshi_complement_candidate`, and
`compute_canonical_yes_side_cross_candidate`.

Stage 37 adds `FeeEstimateStatus`, `FeeEstimate`, Kalshi fee estimate helpers,
and Polymarket US fee estimate helpers. Fee assumptions must be explicit,
Decimal-only, and source-noted. Missing or unknown fee status blocks
`paper_candidate`.

Stage 38 adds `src/edmn_trader/arb/scanner.py` and
`scripts/23_scan_complement_arb.py` for offline-only fixture/snapshot scans.
The scanner writes deterministic JSONL and Markdown summaries with candidate,
audit, reject, fee-status, rejection-reason, and data-quality counts. Scanner
records are research metadata only and never executable order intents.

Stage 39 adds `src/edmn_trader/data/live_events.py` and
`scripts/39_mock_live_event_recorder.py` for a read-only live-event envelope
and local mocked WebSocket-style recorder harness. It writes deterministic
JSONL from fixture events only and opens no real network connection.

Stage 40 adds `src/edmn_trader/adapters/kalshi/readonly_recorder.py` and
`scripts/40_kalshi_readonly_recorder.py` for guarded Kalshi Demo read-only
orderbook recording. It requires explicit `--live-readonly-opt-in`, rejects
non-Demo boundaries, writes raw event JSONL plus normalized snapshot JSONL,
and is covered by mocked HTTP tests only.

Stage 41 adds `src/edmn_trader/adapters/polymarket_us/market_recorder.py` and
`scripts/41_polymarket_market_recorder.py` for guarded Polymarket US
market-channel recording. It requires explicit `--live-readonly-opt-in`,
rejects non-US-public boundaries, writes raw event JSONL plus normalized
snapshot JSONL, and is covered by mocked network tests only. It does not add
user channels, wallets, signing, credentials, authenticated requests, order
placement imports, executable advice, strategy optimization, production
readiness claims, or profitability claims.

Stage 42 adds `src/edmn_trader/data/book_rebuild.py` and
`scripts/42_rebuild_orderbooks.py` for offline recorded-event order book
rebuilds. It normalizes Stage 40/41 read-only event payloads into snapshots,
emits deterministic book-state hashes, and reports sequence-gap, stale-event,
out-of-order, and one-sided-book flags. It does not add live connections,
credentials, user channels, wallets, signing, order placement, strategy
optimization, advice, production-readiness claims, or profitability claims.

Stage 43 adds `src/edmn_trader/arb/fill_simulation.py` and
`scripts/43_simulate_taker_fill.py` for offline two-leg taker-fill
simulation. It consumes explicit local scenario inputs, stresses FOK/IOC-like
fill policy assumptions, partial fills, slippage, latency shock, and
failed-leg reserve, and emits deterministic JSONL/Markdown audit records. It
does not add live connections, credentials, user channels, wallets, signing,
order placement, strategy optimization, executable advice, production-readiness
claims, or profitability claims.

Stage 44 adds `src/edmn_trader/arb/paper_engine.py` and
`scripts/44_paper_complement_engine.py` for paper-only two-leg proposal
records. It consumes Stage 38 candidate JSONL and Stage 43 simulation JSONL,
preserves locked SHA-256 hashes of both source records, emits YES/NO paper
legs from simulated fill prices and completed size, and records conservative
risk-preview reasons. It does not add live connections, credentials, user
channels, wallets, signing, order placement, venue submission, strategy
optimization, executable advice, production-readiness claims, or profitability
claims.

Stage 45 adds `src/edmn_trader/arb/paper_ledger.py` and
`scripts/45_replay_paper_ledger.py` for deterministic paper ledger replay.
It consumes local paper proposal, fill, and settlement records from zero,
preserves proposal candidate/simulation hashes, tracks open positions, fees,
realized gross/net PnL, and reconciliation mismatch states, and emits
paper-only JSONL/Markdown state. It does not add live connections,
credentials, user channels, wallets, signing, order placement, venue
submission, strategy optimization, executable advice, production-readiness
claims, or profitability claims.

Stage 46 adds `src/edmn_trader/arb/risk.py` and
`scripts/46_complement_risk.py` for paper-only complement risk decisions. It
rejects stale data, data gaps, missing or unknown fees, insufficient net edge,
exposure/open-order/daily-loss breaches, reconciliation mismatch, and active
kill switch while still requiring manual approval for all non-rejected
records. It does not add live connections, credentials, user channels,
wallets, signing, order placement, venue submission, strategy optimization,
executable advice, production-readiness claims, or profitability claims.

Stage 47 adds `src/edmn_trader/arb/approval.py` and
`scripts/47_manual_approval.py` for local manual approval records. It creates
deterministic pending approval files, verifies expiring approval records
against proposal and candidate hashes, rejects already-used approvals, and
marks verified approvals as single-use paper manual-review metadata. It does
not add live connections, credentials, user channels, wallets, signing, order
placement, venue submission, strategy optimization, executable advice,
production-readiness claims, or profitability claims.

Stage 48 adds `src/edmn_trader/arb/monitoring.py` and
`scripts/48_daily_validation_report.py` for offline daily validation reports.
It aggregates local records for recorder uptime, data lag, gap count,
candidate counts, rejection reasons, paper/demo outcomes, fees, slippage,
failed-leg incidents, reconciliation health, and kill-switch events. It does
not add live connections, credentials, user channels, wallets, signing, order
placement, venue submission, strategy optimization, executable advice,
production-readiness claims, or profitability claims.

Stage 49 adds `src/edmn_trader/adapters/kalshi/demo_connector.py` and
`scripts/49_kalshi_demo_connector.py` for guarded Kalshi Demo request previews
and Demo submit-path coverage mocked in tests. It consumes a hash-bound,
non-expired, single-use manual approval record, a clear manual-review-required
risk decision, and a reconciled paper ledger state before building tiny FOK/IOC
Demo request previews. Dry-run preview is the default and works without
credentials or reconciliation state. The submit path requires explicit opt-in,
an injected HTTP client in this stage, environment-loaded auth headers,
Demo-only base URL validation, a provided clean Demo reconciliation state, and
append-only local audit logs with auth-like values redacted. It does not
execute a real order during validation, add production endpoints, store
credentials, add wallets, add Polymarket execution, add an LLM trading agent,
optimize strategy, provide investment advice, emit executable advice, claim
production readiness, or claim profitability.

Stage 50 adds `src/edmn_trader/adapters/kalshi/demo_reconciliation.py` and
`scripts/50_kalshi_demo_reconciliation.py` for local Kalshi Demo reconciliation
replay. It reads one Stage 49 connector audit record plus local/mock event
JSONL, rebuilds accepted, rejected, partial fill, full fill, cancel, error,
timeout, and backfill-style state, and appends reconciliation records linked
to the connector audit hash. Duplicate events are idempotent when their
contents match. Missing events, conflicting duplicate ids, source-hash
mismatches, fill-before-acceptance, overfill, and terminal-state conflicts
produce mismatches. Any mismatch sets `submit_eligible` false. The Stage 49
connector keeps dry-run preview available without reconciliation state, while
actual Demo submit opt-in requires a provided clean Demo reconciliation state
and rejects missing or mismatched reconciliation. Stage 50 uses local/mock
records only and does not add venue connections, production endpoints, real
Demo order execution during Codex validation, credentials, wallets, Polymarket
execution, live user-order channels, broker integration, LLM trading agents,
strategy optimization, investment advice, executable advice,
production-readiness claims, or profitability claims.

Stage 51 adds `src/edmn_trader/arb/long_term_validation.py` and
`scripts/51_long_term_validation.py` for offline rolling paper/demo validation
summaries. It reads local JSONL research artifacts from scanner/candidate,
simulation, paper proposal, paper ledger, risk, manual approval, Demo connector
audit, Demo reconciliation, and daily validation stages, then emits
deterministic JSONL, JSON, and Markdown reports for 7/30/90-day windows. It
tracks candidate, paper-candidate, Demo order, fill-rate, failed-leg, edge,
paper/demo PnL, drawdown, mismatch, data-gap, kill-switch, and
false-positive-style rejection metrics where local records provide them. It
marks validation as not completed and lists unmet private-live prerequisites:
missing real 30-90 day live-readonly data, missing 30+ day paper trading
history, unresolved mismatch status when present, unvalidated fee/slippage
assumptions, and missing legal/platform review. Stage 51 uses local/mock inputs
only and does not add venue connections, production endpoints, real Demo order
execution during Codex validation, credentials, wallets, Polymarket execution,
live user-order channels, broker integration, LLM trading agents, strategy
optimization, investment advice, executable advice, production-readiness
claims, or profitability claims.

Stage 52 adds `docs/private_live_execution_gate.md` and
`src/edmn_trader/execution/private_live_gate.py` for a disabled private live
gate design and public placeholder. The placeholder returns status `disabled`,
sets `production_trading_enabled` and `executable_order_intent` to false, and
lists the private-live prerequisites still unmet: 30-90 days live read-only
data, 30+ days paper trading history, zero unresolved reconciliation
mismatches, validated fee/slippage assumptions, successful demo lifecycle
coverage, kill-switch and manual approval drills, and legal/platform
compliance review. Stage 52 does not add production endpoints, production
order code, real-money execution, credentials, wallets, broker integration,
live user-order channels, Polymarket execution, LLM trading agents, strategy
optimization, investment advice, executable advice, production-readiness
claims, or profitability claims.

After Stage 52, the public README was refreshed as the main repository landing
page. It now summarizes the current workflow, architecture layers, local
commands, validation status, safety boundary, disabled private-live gate, and
unmet private-live prerequisites without changing code behavior.

The post-PR #109 visual documentation refresh keeps GitHub-rendered Mermaid
diagrams in `README.md` and `docs/visual_overview.md` aligned with the current
public boundary: scanner/simulation, paper proposal, paper ledger, risk
decision, manual approval, Kalshi Demo dry-run/guarded Demo submit boundary,
Demo reconciliation, rolling validation, and the disabled private-live gate. It
adds no SVG assets, generated images, hosted assets, source behavior changes,
credentials, production endpoints, live execution paths, strategy optimization,
production-readiness claims, or profitability claims.

The release and portfolio packaging pass adds `docs/release_notes_stage_52.md`,
`docs/portfolio_summary.md`, and `docs/resume_bullets_stage_52.md`. These docs
provide GitHub Release title/body copy, reviewer-facing portfolio framing, and
resume-ready bullets for the completed Stage 52 public state. They add no
source behavior changes, credentials, endpoints, wallets, live execution paths,
strategy optimization, investment advice, executable advice,
production-readiness claims, positive-expectancy claims, or profitability
claims.

The roadmap and end-to-end conformance audits are complete in
`docs/roadmap_conformance_audit.md` and
`docs/end_to_end_conformance_audit.md`. PR #109 tightened the Stage 49/50 Demo
boundary so dry-run preview remains available without credentials or
reconciliation state, while Demo submit opt-in requires a provided clean Demo
reconciliation state and remains covered by mocked HTTP tests.

`docs/STAGE_PLAN.md` now contains the full Stage 3 specification: snapshot
schema requirements, Decimal-safe JSONL recorder requirements, deterministic
replay behavior, fixture recording and replay scripts, offline tests,
out-of-scope boundaries, validation commands, and the Stage 4 boundary.

`docs/STAGE_PLAN.md` also contains the full Stage 4 specification: fair-value
baseline requirements, quote generation, inventory-aware skew, spread and
tick/price boundary handling, dry-run-only intent output, replay dry-run script,
offline deterministic tests, validation commands, non-goals, and the Stage 5
boundary.

`docs/STAGE_PLAN.md` now contains the full Stage 5 specification: risk checks,
blocked-path tests, execution log format, demo-only smoke constraints,
offline/fake-adapter test requirements, validation commands, non-goals, and the
Stage 6 boundary.

`docs/STAGE_PLAN.md` now contains the full Stage 6 specification: finite
replay-driven dry-run/demo workflow behavior, inventory-aware quoting
requirements, Stage 5 risk-gate reuse, structured JSONL logging and run summary
requirements, explicit quote lifecycle handling, max-position/max-open-orders/
max-notional/max-loss/kill-switch controls, offline tests, validation commands,
explicit non-goals, and the Stage 7 boundary.

Stage 6 is now implemented as a finite replay workflow. It remains dry-run by
default, uses only fake-adapter demo submissions after explicit opt-in and risk
approval, and does not infer fills, PnL, profitability, or production readiness.

`docs/STAGE_PLAN.md` now contains the full Stage 7 specification: offline
research report inputs, optional explicit fill assumptions, Decimal-safe
attribution requirements, no-fill report behavior, Markdown report script,
offline tests, validation commands, non-goals, and the Stage 8 boundary.

Stage 7 is now implemented as an offline Markdown research report workflow. It
consumes Stage 6 JSONL logs and optional explicit local fill fixtures, separates
observed counts from supplied assumptions, rejects secret-like fill fields, and
does not infer fills from fake/demo adapter submissions.

`docs/STAGE_PLAN.md` now contains the clarified Stage 8 specification and
`docs/stage8_polymarket_readiness.md` records the readiness review. Stage 8 is
ready only for a fixture-first Polymarket US public market-data adapter. It
must not use international Polymarket endpoints, trading endpoints, wallets,
authentication, WebSockets, region bypass, live HTTP smoke by default, or
production execution.

Stage 8 is now implemented as a Polymarket US public market-data adapter. It
normalizes local market-book fixtures into `NormalizedOrderBook` and includes a
guarded read-only client restricted to the documented Polymarket US public base
URL. Tests use local fixtures and mocked HTTP only.

## Compact governance audit

Policy update: compact governance audits after every three completed
checkpoints are mandatory but non-terminal when they pass. A passing audit must
be published under the controller policy, followed by `main` `Validate`, local
sync, clean-state verification, checkpoint-counter reset, and a fresh read of
this handoff before continuing. Stop only when the audit finds a real stop gate.

Audit after three completed checkpoints: Stage 7 implementation, Stage 8
readiness clarification, and Stage 8 implementation. Local `main` is synced
with `origin/main` at `cbfce85`, the worktree is clean, there are no open pull
requests, and the latest observed `main` CI run `28006884201` passed
`Validate`. The next checkpoint remains Stage 9 readiness only.

Audit after three more completed checkpoints: Stage 9 readiness clarification,
Stage 9 implementation, and Stage 10 plan clarification. Local `main` is synced
with `origin/main` at `7ef2a2f`, the worktree is clean, there are no open pull
requests, and the latest observed `main` CI run `28007536118` passed
`Validate`. The next checkpoint is Stage 10 implementation only.

Audit after three more completed checkpoints: Stage 10 implementation, Stage
11 readiness clarification, and Stage 11 implementation. Local `main` is synced
with `origin/main` at `2d38dd1`, the worktree is clean, there are no open pull
requests, and the latest observed `main` CI run `28073147659` passed
`Validate`. The next checkpoint is report-input readiness clarification only.

Audit after three more completed checkpoints: non-terminal governance audit
policy update, Stage 12 readiness clarification, and Stage 12 implementation.
Local `main` is synced with `origin/main` at `de2810f`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, and the latest observed `main` CI run `28149424687` passed
`Validate`. The handoff and stage plan agree on the next checkpoint, and no
risk drift, compliance drift, token/context drift, or user-judgment stop gate
was found. The next checkpoint is report-input-kind readiness clarification
only.

Audit after three more completed checkpoints: Stage 13 readiness
clarification, Stage 13 implementation, and Stage 14 readiness clarification.
Local `main` is synced with `origin/main` at `e9052b8`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, force pushes and branch deletion are disabled, and the latest
observed `main` CI run `28150107155` passed `Validate`. The handoff and stage
plan agree on the next checkpoint, and no risk drift, compliance drift,
token/context drift, or user-judgment stop gate was found. The next checkpoint
is Stage 14 implementation only.

Audit after three more completed checkpoints: Stage 14 implementation, Stage
15 readiness clarification, and Stage 15 implementation. Local `main` is
synced with `origin/main` at `3afcc05`, the worktree is clean, there are no
open pull requests, branch protection still requires strict `Validate`, force
pushes and branch deletion are disabled, and the latest observed `main` CI run
`28150877741` passed `Validate`. The handoff and stage plan agree on the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found. The next checkpoint is report-input-kind
readiness clarification only.

Audit after three more completed checkpoints: Stage 16 readiness
clarification, Stage 16 implementation, and Stage 17 readiness clarification.
Local `main` is synced with `origin/main` at `8cc025d`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, force pushes and branch deletion are disabled, and the latest
observed `main` CI run `28151563023` passed `Validate`. The handoff and stage
plan agree on the next checkpoint, and no risk drift, compliance drift,
token/context drift, or user-judgment stop gate was found. The next checkpoint
is Stage 17 implementation only.

Audit after three more completed checkpoints: Stage 17 implementation, Stage
18 readiness clarification, and Stage 18 implementation. Local `main` is
synced with `origin/main` at `bd7ef4b`, the worktree is clean, there are no
open pull requests, branch protection still requires strict `Validate`, force
pushes and branch deletion are disabled, and the latest observed `main` CI run
`28219436065` passed `Validate`. The handoff and stage plan agree on the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found. The next checkpoint is report-input-kind
readiness clarification only.

Audit after three more completed checkpoints: Stage 19 readiness
clarification, Stage 19 implementation, and Stage 20 readiness clarification.
Local `main` is synced with `origin/main` at `f5347f1`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, force pushes and branch deletion are disabled, and the latest
observed `main` CI run `28220077298` passed `Validate`. The handoff and stage
plan agree on the next checkpoint, and no risk drift, compliance drift,
token/context drift, or user-judgment stop gate was found. The next checkpoint
is Stage 20 implementation only.

Audit after three more completed checkpoints: Stage 20 implementation, Stage
21 readiness clarification, and Stage 21 implementation. Local `main` is
synced with `origin/main` at `a8a63ee`, the worktree is clean, there are no
open pull requests, branch protection still requires strict `Validate`, force
pushes and branch deletion are disabled, and the latest observed `main` CI run
`28220874376` passed `Validate`. The handoff and stage plan agree on the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found. The next checkpoint is report-input-kind
readiness clarification only.

Audit after three more completed checkpoints: Stage 22 readiness
clarification, Stage 22 implementation, and Stage 23 readiness clarification.
Local `main` is synced with `origin/main` at `30bbcde`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, force pushes and branch deletion are disabled, and the latest
observed `main` CI run `28221429772` passed `Validate`. The handoff and stage
plan agree on the next checkpoint, and no risk drift, compliance drift,
token/context drift, or user-judgment stop gate was found. The next checkpoint
is Stage 23 implementation only.

Audit after three more completed checkpoints: Stage 23 implementation, Stage
24 readiness clarification, and Stage 24 implementation. Local `main` is
synced with `origin/main` at `4e836ad`, the worktree is clean, there are no
open pull requests, branch protection still requires strict `Validate`, force
pushes and branch deletion are disabled, and the latest observed `main` CI run
`28264580562` passed `Validate`. The handoff and stage plan agree on the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found. The next checkpoint is report-input-kind
readiness clarification only.

Audit after three more completed checkpoints: Stage 25 readiness
clarification, Stage 25 implementation, and Stage 26 readiness clarification.
Local `main` is synced with `origin/main` at `6ff33f2`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, force pushes and branch deletion are disabled, and the latest
observed `main` CI run `28265376072` passed `Validate`. The handoff and stage
plan agree on the next checkpoint, and no risk drift, compliance drift,
token/context drift, or user-judgment stop gate was found. The next checkpoint
is Stage 26 implementation only.

Audit after three more completed checkpoints: Stage 26 implementation, Stage
27 readiness clarification, and Stage 27 implementation. Local `main` is
synced with `origin/main` at `3188bd0`, the worktree is clean, there are no
open pull requests, branch protection still requires strict `Validate`, force
pushes and branch deletion are disabled, and the latest observed `main` CI run
`28266218418` passed `Validate`. The handoff and stage plan agree on the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found. The next checkpoint is report-input-kind
readiness clarification only.

Audit after three more completed checkpoints: Stage 28 readiness
clarification, Stage 28 implementation, and Stage 29 readiness clarification.
Local `main` is synced with `origin/main` at `5240f62`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, force pushes and branch deletion are disabled, and the latest
observed `main` CI run `28267200873` passed `Validate`. The handoff and stage
plan agree on the next checkpoint, and no risk drift, compliance drift,
token/context drift, or user-judgment stop gate was found. The next checkpoint
is Stage 29 implementation only.

Audit after three more completed checkpoints: Stage 29 implementation, Stage
30 readiness clarification, and Stage 30 implementation. Local `main` is
synced with `origin/main` at `6cb9a79`, the worktree is clean, there are no
open pull requests, branch protection still requires strict `Validate`, force
pushes and branch deletion are disabled, and the latest observed `main` CI run
`28267987734` passed `Validate`. The handoff and stage plan agree on the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found. The next checkpoint is report-input-kind
readiness clarification only.

Audit after three more completed checkpoints: Stage 31 readiness
clarification, Stage 31 implementation, and Stage 32 readiness clarification.
Local `main` is synced with `origin/main` at `676b4bd`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, force pushes and branch deletion are disabled, and the latest
observed `main` CI run `28268711448` passed `Validate`. The handoff and stage
plan agree on the next checkpoint, and no risk drift, compliance drift,
token/context drift, or user-judgment stop gate was found. The next checkpoint
is Stage 32 implementation only.

Audit after three more completed checkpoints: Stage 32 implementation, Stage
33 readiness clarification, and Stage 33 implementation. Local `main` is
synced with `origin/main` at `1395484`, the worktree is clean, there are no
open pull requests, branch protection still requires strict `Validate`, force
pushes and branch deletion are disabled, and the latest observed `main` CI run
`28269488815` passed `Validate`. The handoff and stage plan agree on the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found. The next checkpoint is
report-input-kind readiness clarification only.

Audit after three more completed checkpoints: Stage 34 readiness
clarification, Stage 34 implementation, and Stage 35 readiness clarification.
Local `main` is synced with `origin/main` at `f59fda1`, the worktree is clean,
there are no open pull requests, branch protection still requires strict
`Validate`, force pushes and branch deletion are disabled, and the latest
observed `main` CI run `28270211447` passed `Validate`. The handoff and stage
plan agree on the next checkpoint, and no risk drift, compliance drift,
token/context drift, or user-judgment stop gate was found. The next checkpoint
was Stage 35 implementation only at the time; it has since been superseded by
the Stage 35-37 arbitrage roadmap, candidate schema, and fee scaffold delivery
units, and the active next checkpoint is Stage 38 offline complement scanner
only. Stage 38 is now complete, so the active next checkpoint is Stage 39 live
event schema plus mocked WebSocket recorder harness only.

Audit after three more completed checkpoints: Stage 39 live event schema and
mocked WebSocket harness, Stage 40 Kalshi live read-only recorder, and Stage
41 Polymarket market-channel recorder. Local work started from synced
`origin/main` at `a195dab`, there were no open pull requests before Stage 41
publish, branch protection still requires strict `Validate`, and the latest
observed `main` CI run `28338107808` passed `Validate`. The handoff and stage
plan agree on Stage 42 as the next checkpoint, and no risk drift, compliance
drift, token/context drift, or user-judgment stop gate was found.

Audit after three more completed checkpoints: Stage 42 order book rebuild,
Stage 43 taker fill simulation, and Stage 44 paper complement proposal engine.
Local work started from synced `origin/main` at `05fb58e`, there were no open
pull requests before Stage 44 publish, branch protection still requires strict
`Validate`, and the latest observed `main` CI run `28338842369` passed
`Validate`. The handoff and stage plan agree on Stage 45 as the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found.

Audit after three more completed checkpoints: Stage 45 paper ledger state
machine, Stage 46 risk engine v2, and Stage 47 manual approval workflow.
Local work started from synced `origin/main` at `352fffc`, there were no open
pull requests before Stage 47 publish, branch protection still requires strict
`Validate`, and the latest observed `main` CI run `28391058622` passed
`Validate`. The handoff and stage plan agree on Stage 48 as the next
checkpoint, and no risk drift, compliance drift, token/context drift, or
user-judgment stop gate was found.

Audit after three more completed checkpoints: Stage 48 monitoring and daily
validation report, Stage 49 Kalshi Demo authenticated connector, and Stage 50
demo reconciliation. Stage 50 work started from synced `origin/main` at
`eab1d7d`, there were no open pull requests before Stage 50 publish, branch
protection still requires strict `Validate`, and the latest observed `main` CI
run `28413491937` passed `Validate`. The handoff and stage plan agree on Stage
51 as the next checkpoint, and no risk drift, compliance drift, token/context
drift, or user-judgment stop gate was found.

`docs/STAGE_PLAN.md` now contains the clarified Stage 9 specification and
`docs/stage9_equities_readiness.md` records the readiness review. Stage 9 is
ready only for a fixture-first SEC EDGAR public fundamentals adapter. It must
not add broker integration, credentials, account data, portfolio data, live
quote feeds, paid-vendor market data, order placement, strategy optimization,
production execution, or profitability claims.

Stage 9 is now implemented as an SEC EDGAR public fundamentals adapter. It
normalizes local companyfacts fixtures into `EquityFundamentalFact` and
includes a guarded read-only client restricted to `https://data.sec.gov` with
explicit User-Agent configuration. Tests use local fixtures and mocked HTTP
only.

`docs/STAGE_PLAN.md` now contains the full Stage 10 specification: offline
paper research report pack inputs, Markdown output, separation of observed
metrics, supplied assumptions, SEC fundamentals and limitations, offline tests,
validation commands, non-goals, and the next-stage boundary.

Stage 10 is now implemented as an offline paper research report pack. It reuses
the Stage 7 attribution workflow, adds local SEC companyfacts fixtures, labels
missing optional inputs as not supplied, and does not add ranking, allocation
advice, live feeds, broker integration, execution, strategy optimization, or
profitability claims.

`docs/STAGE_PLAN.md` now contains the full Stage 11 specification and
`docs/stage11_report_sections_readiness.md` records the readiness review.
Stage 11 is ready only for local/offline descriptive report-section expansion
of the Stage 10 pack. It must not add new data adapters, live feeds, broker
integration, credentials, account or portfolio data, ranking, allocation
advice, strategy optimization, execution, or profitability claims.

Stage 11 is now implemented as a local/offline report-section expansion. It
adds a source inventory section to the paper report pack, labels missing fills
or SEC companyfacts as not supplied, and does not add new data adapters, live
feeds, ranking, allocation advice, executable advice, strategy optimization,
execution, or profitability claims.

`docs/STAGE_PLAN.md` now contains the full Stage 12 specification and
`docs/stage12_report_inputs_readiness.md` records the readiness review. Stage
12 is ready only for a local/offline report-input manifest. It must not add new
data adapters, remote fetching, broker integration, credentials, account or
portfolio data, live feeds, ranking, allocation advice, executable advice,
strategy optimization, unsupported redistribution, production endpoints, or
profitability claims.

Stage 12 is now implemented as an optional local/offline report-input manifest
for the paper report pack. It renders manifest entries in a separate Markdown
section, reports missing manifests as not supplied, rejects secret-like fields
and remote URLs, and does not add new data adapters, remote fetching,
unsupported redistribution, executable advice, ranking, allocation advice,
strategy optimization, execution, or profitability claims.

`docs/STAGE_PLAN.md` now contains the full Stage 13 readiness specification for
a local/offline `local_run_comparison` report-input kind. Stage 13 may compare
only already generated local project outputs and must not add new adapters,
remote fetching, account or portfolio data, live feeds, paid-vendor data,
ranking, allocation advice, strategy optimization, executable advice,
unsupported redistribution, production endpoints, or profitability claims.

Stage 13 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local comparison descriptor referenced by the
manifest, renders a separate descriptive comparison section, reports missing
optional comparison descriptors as not supplied, rejects secret-like fields and
remote URLs, and does not read private data contents, add adapters, fetch
remote data, rank securities, recommend allocations, optimize strategies, emit
executable advice, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 14 readiness specification for
a local/offline `local_validation_summary` report-input kind. Stage 14 may
describe only already-run local checks and generated artifacts, and it must not
execute commands, fetch remote data, add adapters, read account or portfolio
data, use live feeds, rank securities, recommend allocations, optimize
strategies, emit executable advice, imply production readiness, or claim
profitability.

Stage 14 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local validation descriptor referenced by the
manifest, renders a separate descriptive validation section, reports missing
optional validation descriptors as not supplied, rejects secret-like fields and
remote URLs, and does not execute commands, read private data contents, add
adapters, fetch remote data, rank securities, recommend allocations, optimize
strategies, emit executable advice, imply production readiness, or claim
profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 15 readiness specification for
a local/offline `local_review_notes` report-input kind. Stage 15 may describe
only reviewer-supplied notes, caveats, local source paths, follow-up questions,
and limitation notes, and it must not execute commands, read private data
contents, fetch remote data, add adapters, use account or portfolio data, use
live feeds, rank securities, recommend allocations, optimize strategies, emit
executable advice, imply production readiness, or claim profitability.

Stage 15 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local review-notes descriptor referenced by the
manifest, renders a separate descriptive review-notes section, reports missing
optional review-notes descriptors as not supplied, rejects secret-like fields
and remote URLs, and does not execute commands, read private data contents, add
adapters, fetch remote data, rank securities, recommend allocations, optimize
strategies, emit executable advice, imply production readiness, or claim
profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 16 readiness specification for
a local/offline `local_methodology_notes` report-input kind. Stage 16 may
describe only reviewer-supplied methodology context, assumption descriptions,
local source paths, and limitation notes, and it must not execute commands,
read private data contents, fetch remote data, add adapters, use account or
portfolio data, use live feeds, rank securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

Stage 16 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local methodology-notes descriptor referenced by
the manifest, renders a separate descriptive methodology section, reports
missing optional methodology descriptors as not supplied, rejects secret-like
fields and remote URLs, and does not execute commands, read private data
contents, add adapters, fetch remote data, rank securities, recommend
allocations, optimize strategies, emit executable advice, imply production
readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 17 readiness specification for
a local/offline `local_data_dictionary` report-input kind. Stage 17 may
describe only reviewer-supplied field labels, local source paths, data type
labels, units, definitions, rights/sensitivity labels, and limitation notes,
and it must not execute commands, read raw private data contents, fetch remote
data, add adapters, use account or portfolio data, use live feeds, rank
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

Stage 17 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local data-dictionary descriptor referenced by
the manifest, renders a separate descriptive data-dictionary section, reports
missing optional data-dictionary descriptors as not supplied, rejects
secret-like fields and remote URLs, and does not execute commands, read raw
private data contents, add adapters, fetch remote data, rank securities,
recommend allocations, optimize strategies, emit executable advice, imply
production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 18 readiness specification for
a local/offline `local_citation_index` report-input kind. Stage 18 may
describe only reviewer-supplied citation labels, local source paths, citation
purpose, rights notes, and limitation notes, and it must not execute commands,
read source contents, read raw private data contents, fetch remote data, add
adapters, use account or portfolio data, use live feeds, rank sources or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

Stage 18 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local citation-index descriptor referenced by the
manifest, renders a separate descriptive citation-index section, reports
missing optional citation-index descriptors as not supplied, rejects
secret-like fields, source-content/excerpt fields, and remote URLs, and does
not execute commands, read source contents, read raw private data contents,
embed private or proprietary excerpts, add adapters, fetch remote data, rank
sources or securities, recommend allocations, optimize strategies, emit
executable advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 19 readiness specification for
a local/offline `local_term_glossary` report-input kind. Stage 19 may describe
only reviewer-supplied term labels, local source paths, definitions, usage
scope, and limitation notes, and it must not execute commands, read source
contents, read raw private data contents, fetch remote data, add adapters, use
account or portfolio data, use live feeds, rank terms, sources, or securities,
recommend allocations, optimize strategies, emit executable advice, imply
production readiness, or claim profitability.

Stage 19 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local term-glossary descriptor referenced by the
manifest, renders a separate descriptive term-glossary section, reports missing
optional term-glossary descriptors as not supplied, rejects secret-like fields,
source-content/excerpt fields, and remote URLs, and does not execute commands,
read source contents, read raw private data contents, embed private or
proprietary excerpts, add adapters, fetch remote data, rank terms, sources, or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 20 readiness specification for
a local/offline `local_assumption_register` report-input kind. Stage 20 may
describe only reviewer-supplied assumption labels, local source paths,
rationale, scope, and limitation notes, and it must not execute commands, read
source contents, read raw private data contents, fetch remote data, add
adapters, use account or portfolio data, use live feeds, rank assumptions,
terms, sources, or securities, recommend allocations, optimize strategies,
emit executable advice, imply production readiness, or claim profitability.

Stage 20 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local assumption-register descriptor referenced by
the manifest, renders a separate descriptive assumption-register section,
reports missing optional assumption-register descriptors as not supplied,
rejects secret-like fields, source-content/excerpt fields, and remote URLs, and
does not execute commands, read source contents, read raw private data
contents, embed private or proprietary excerpts, add adapters, fetch remote
data, rank assumptions, terms, sources, or securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 21 readiness specification for
a local/offline `local_coverage_matrix` report-input kind. Stage 21 may
describe only reviewer-supplied report section labels, local source paths,
input labels, validation labels, coverage notes, and limitation notes, and it
must not execute commands, run checks from report inputs, read source contents,
read raw private data contents, fetch remote data, add adapters, use account
or portfolio data, use live feeds, score or rank coverage, sources, or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

Stage 21 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local coverage-matrix descriptor referenced by the
manifest, renders a separate descriptive coverage-matrix section, reports
missing optional coverage-matrix descriptors as not supplied, rejects
secret-like fields, source-content/excerpt fields, and remote URLs, and does
not execute commands, run checks from report inputs, read source contents, read
raw private data contents, embed private or proprietary excerpts, add adapters,
fetch remote data, score or rank coverage, sources, or securities, recommend
allocations, optimize strategies, emit executable advice, imply production
readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 22 readiness specification for
a local/offline `local_reproducibility_checklist` report-input kind. Stage 22
may describe only reviewer-supplied reproduction step labels, local artifact
paths, command labels, environment labels, expected output labels, and
limitation notes, and it must not execute commands, run checks from report
inputs, read artifact or source contents, read raw private data contents, fetch
remote data, add adapters, verify local environments or outputs, use account
or portfolio data, use live feeds, score or rank reproducibility, coverage,
sources, or securities, recommend allocations, optimize strategies, emit
executable advice, imply production readiness, or claim profitability.

Stage 22 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local reproducibility-checklist descriptor
referenced by the manifest, renders a separate descriptive reproducibility
section, reports missing optional reproducibility-checklist descriptors as not
supplied, rejects secret-like fields, source-content/excerpt fields, and remote
URLs, and does not execute commands, run checks from report inputs, read
artifact contents, read source contents, read raw private data contents, embed
private or proprietary excerpts, verify local environments or outputs, add
adapters, fetch remote data, score or rank reproducibility, coverage, sources,
or securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 23 readiness specification for
a local/offline `local_risk_review` report-input kind. Stage 23 may describe
only reviewer-supplied risk-control labels, boundary labels, mitigation notes,
review status labels, local evidence paths, and limitation notes, and it must
not execute commands, run checks from report inputs, evaluate policies, run
risk checks, place orders, read evidence or source contents, read raw private
data contents, fetch remote data, add adapters, verify local environments or
outputs, use account or portfolio data, use live feeds, score or rank risk,
reproducibility, coverage, sources, or securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

Stage 23 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local risk-review descriptor referenced by the
manifest, renders a separate descriptive risk-review section, reports missing
optional risk-review descriptors as not supplied, rejects secret-like fields,
source-content/excerpt fields, and remote URLs, and does not execute commands,
run checks from report inputs, evaluate policies, run risk checks, place
orders, read evidence contents, read source contents, read raw private data
contents, embed private or proprietary excerpts, verify local environments or
outputs, add adapters, fetch remote data, score or rank risk, reproducibility,
coverage, sources, or securities, recommend allocations, optimize strategies,
emit executable advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 24 readiness specification for
a local/offline `local_data_rights_review` report-input kind. Stage 24 may
describe only reviewer-supplied data labels, rights status labels,
permitted-use notes, restriction notes, local evidence paths, and limitation
notes, and it must not execute commands, run checks from report inputs,
determine legal rights, verify licenses, decide redistribution permissions,
evaluate policies, read evidence or source contents, read raw private data
contents, fetch remote data, add adapters, verify local environments or
outputs, use account or portfolio data, use live feeds, score or rank rights
status, risk, reproducibility, coverage, sources, or securities, recommend
allocations, optimize strategies, emit executable advice, imply production
readiness, or claim profitability.

Stage 24 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local data-rights-review descriptor referenced by
the manifest, renders a separate descriptive data-rights section, reports
missing optional data-rights-review descriptors as not supplied, rejects
secret-like fields, source-content/excerpt fields, and remote URLs, and does
not execute commands, run checks from report inputs, determine legal rights,
verify licenses, decide redistribution permissions, evaluate policies, read
evidence contents, read source contents, read raw private data contents, embed
private or proprietary excerpts, verify local environments or outputs, add
adapters, fetch remote data, score or rank rights status, risk,
reproducibility, coverage, sources, or securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 25 readiness specification for
a local/offline `local_artifact_inventory` report-input kind. Stage 25 may
describe only reviewer-supplied generated artifact labels, artifact type
labels, local paths, generation-source labels, intended report-use notes, and
limitation notes, and it must not execute commands, run checks from report
inputs, read artifact contents, verify outputs, verify local environments, read
evidence or source contents, read raw private data contents, fetch remote data,
add adapters, use account or portfolio data, use live feeds, score or rank
artifacts, rights status, risk, reproducibility, coverage, sources, or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

Stage 25 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local artifact-inventory descriptor referenced by
the manifest, renders a separate descriptive artifact-inventory section,
reports missing optional artifact-inventory descriptors as not supplied,
rejects secret-like fields, source-content/excerpt fields, and remote URLs,
and does not execute commands, run checks from report inputs, read artifact
contents, verify outputs, verify local environments, read evidence contents,
read source contents, read raw private data contents, embed private or
proprietary excerpts, add adapters, fetch remote data, score or rank artifacts,
rights status, risk, reproducibility, coverage, sources, or securities,
recommend allocations, optimize strategies, emit executable advice, imply
production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 26 readiness specification for
a local/offline `local_appendix_index` report-input kind. Stage 26 may
describe only reviewer-supplied appendix entry labels, report section labels,
local artifact paths, appendix purpose notes, and limitation notes, and it must
not execute commands, run checks from report inputs, read artifact contents,
verify outputs, verify local environments, approve distribution, read evidence
or source contents, read raw private data contents, fetch remote data, add
adapters, use account or portfolio data, use live feeds, score or rank appendix
entries, artifacts, rights status, risk, reproducibility, coverage, sources, or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

Stage 26 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local appendix-index descriptor referenced by the
manifest, renders a separate descriptive appendix-index section, reports
missing optional appendix-index descriptors as not supplied, rejects
secret-like fields, source-content/excerpt fields, and remote URLs, and does
not execute commands, run checks from report inputs, read artifact contents,
verify outputs, verify local environments, approve distribution, read evidence
contents, read source contents, read raw private data contents, embed private
or proprietary excerpts, add adapters, fetch remote data, score or rank
appendix entries, artifacts, rights status, risk, reproducibility, coverage,
sources, or securities, recommend allocations, optimize strategies, emit
executable advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 27 readiness specification for
a local/offline `local_limitation_register` report-input kind. Stage 27 may
describe only reviewer-supplied limitation labels, affected report section
labels, local evidence or artifact paths, scope notes, mitigation notes, and
limitation notes, and it must not execute commands, run checks from report
inputs, read artifact/evidence/source contents, verify outputs, verify local
environments, approve distribution, read raw private data contents, fetch
remote data, add adapters, use account or portfolio data, use live feeds, score
or rank limitations, appendix entries, artifacts, rights status, risk,
reproducibility, coverage, sources, or securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

Stage 27 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local limitation-register descriptor referenced by
the manifest, renders a separate descriptive limitation-register section,
reports missing optional limitation-register descriptors as not supplied,
rejects secret-like fields, source-content/excerpt fields, and remote URLs,
and does not execute commands, run checks from report inputs, read
artifact/evidence/source contents, verify outputs, verify local environments,
approve distribution, read raw private data contents, embed private or
proprietary excerpts, add adapters, fetch remote data, score or rank
limitations, appendix entries, artifacts, rights status, risk, reproducibility,
coverage, sources, or securities, recommend allocations, optimize strategies,
emit executable advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 28 readiness specification for
a local/offline `local_open_questions` report-input kind. Stage 28 may describe
only reviewer-supplied open question labels, affected report section labels,
local reference paths, owner labels, status labels, and limitation notes, and
it must not execute commands, run checks from report inputs, read artifact/
evidence/source contents, verify outputs, verify local environments, approve
decisions, read raw private data contents, fetch remote data, add adapters, use
account or portfolio data, use live feeds, score or rank open questions,
limitations, appendix entries, artifacts, rights status, risk, reproducibility,
coverage, sources, or securities, recommend allocations, optimize strategies,
emit executable advice, imply production readiness, or claim profitability.

Stage 28 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local open-questions descriptor referenced by the
manifest, renders a separate descriptive open-questions section, reports
missing optional open-questions descriptors as not supplied, rejects
secret-like fields, source-content/excerpt fields, and remote URLs, and does
not execute commands, run checks from report inputs, read artifact/evidence/
source contents, verify outputs, verify local environments, approve decisions,
read raw private data contents, embed private or proprietary excerpts, add
adapters, fetch remote data, score or rank open questions, limitations,
appendix entries, artifacts, rights status, risk, reproducibility, coverage,
sources, or securities, recommend allocations, optimize strategies, emit
executable advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 29 readiness specification for
a local/offline `local_decision_log` report-input kind. Stage 29 may describe
only reviewer-supplied decision labels, decision context labels, local
reference paths, owner labels, status labels, rationale notes, and limitation
notes, and it must not execute commands, run checks from report inputs, read
artifact/evidence/source contents, verify outputs, verify local environments,
approve decisions, read raw private data contents, fetch remote data, add
adapters, use account or portfolio data, use live feeds, score or rank
decisions, open questions, limitations, appendix entries, artifacts, rights
status, risk, reproducibility, coverage, sources, or securities, recommend
allocations, optimize strategies, emit executable advice, imply production
readiness, or claim profitability.

Stage 29 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local decision-log descriptor referenced by the
manifest, renders a separate descriptive decision-log section, reports missing
optional decision-log descriptors as not supplied, rejects secret-like fields,
source-content/excerpt fields, and remote URLs, and does not execute commands,
run checks from report inputs, read artifact/evidence/source contents, verify
outputs, verify local environments, approve decisions, read raw private data
contents, embed private or proprietary excerpts, add adapters, fetch remote
data, score or rank decisions, open questions, limitations, appendix entries,
artifacts, rights status, risk, reproducibility, coverage, sources, or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 30 readiness specification for
a local/offline `local_follow_up_register` report-input kind. Stage 30 may
describe only reviewer-supplied follow-up labels, related report section
labels, local reference paths, owner labels, status labels, tracking notes, and
limitation notes, and it must not execute commands, run checks from report
inputs, execute follow-ups, read artifact/evidence/source contents, verify
outputs, verify local environments, approve decisions, read raw private data
contents, fetch remote data, add adapters, use account or portfolio data, use
live feeds, score or rank follow-ups, decisions, open questions, limitations,
appendix entries, artifacts, rights status, risk, reproducibility, coverage,
sources, or securities, recommend allocations, optimize strategies, emit
executable advice, imply production readiness, or claim profitability.

Stage 30 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local follow-up-register descriptor referenced by
the manifest, renders a separate descriptive follow-up section, reports
missing optional follow-up-register descriptors as not supplied, rejects
secret-like fields, source-content/excerpt fields, and remote URLs, and does
not execute commands, run checks from report inputs, execute follow-ups, read
artifact/evidence/source contents, verify outputs, verify local environments,
approve decisions, read raw private data contents, embed private or proprietary
excerpts, add adapters, fetch remote data, score or rank follow-ups,
decisions, open questions, limitations, appendix entries, artifacts, rights
status, risk, reproducibility, coverage, sources, or securities, recommend
allocations, optimize strategies, emit executable advice, imply production
readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 31 readiness specification for
a local/offline `local_version_notes` report-input kind. Stage 31 may describe
only reviewer-supplied report version labels, local artifact paths,
change-summary labels, owner labels, status labels, and limitation notes, and
it must not execute commands, run checks from report inputs, execute
follow-ups, approve distribution, read artifact/evidence/source contents,
verify outputs, verify local environments, approve decisions, read raw private
data contents, fetch remote data, add adapters, use account or portfolio data,
use live feeds, score or rank versions, follow-ups, decisions, open questions,
limitations, appendix entries, artifacts, rights status, risk,
reproducibility, coverage, sources, or securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

Stage 31 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local version-notes descriptor referenced by the
manifest, renders a separate descriptive version-notes section, reports
missing optional version-notes descriptors as not supplied, rejects secret-like
fields, source-content/excerpt fields, and remote URLs, and does not execute
commands, run checks from report inputs, execute follow-ups, approve
distribution, read artifact/evidence/source contents, verify outputs, verify
local environments, approve decisions, read raw private data contents, embed
private or proprietary excerpts, add adapters, fetch remote data, score or rank
versions, follow-ups, decisions, open questions, limitations, appendix entries,
artifacts, rights status, risk, reproducibility, coverage, sources, or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 32 readiness specification for
a local/offline `local_distribution_checklist` report-input kind. Stage 32 may
describe only reviewer-supplied distribution item labels, related artifact
paths, readiness status labels, owner labels, review notes, and limitation
notes, and it must not execute commands, run checks from report inputs, execute
follow-ups, approve distribution, verify rights or licenses, read artifact/
evidence/source contents, verify outputs, verify local environments, approve
decisions, read raw private data contents, fetch remote data, add adapters, use
account or portfolio data, use live feeds, score or rank distribution items,
versions, follow-ups, decisions, open questions, limitations, appendix entries,
artifacts, rights status, risk, reproducibility, coverage, sources, or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

Stage 32 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local distribution-checklist descriptor referenced
by the manifest, renders a separate descriptive distribution-checklist section,
reports missing optional descriptors as not supplied, rejects secret-like
fields, source-content/excerpt fields, and remote URLs, and does not execute
commands, run checks from report inputs, execute follow-ups, approve
distribution, verify rights or licenses, read artifact/evidence/source
contents, verify outputs, verify local environments, approve decisions, read
raw private data contents, embed private or proprietary excerpts, add adapters,
fetch remote data, score or rank distribution items, versions, follow-ups,
decisions, open questions, limitations, appendix entries, artifacts, rights
status, risk, reproducibility, coverage, sources, or securities, recommend
allocations, optimize strategies, emit executable advice, imply production
readiness, or claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 33 readiness specification for
a local/offline `local_handoff_notes` report-input kind. Stage 33 may describe
only reviewer-supplied handoff labels, related artifact paths, recipient or
owner labels, status labels, handoff notes, and limitation notes, and it must
not execute commands, run checks from report inputs, execute follow-ups,
approve distribution, verify rights or licenses, read artifact/evidence/source
contents, verify outputs, verify local environments, approve decisions, read
raw private data contents, fetch remote data, add adapters, use account or
portfolio data, use live feeds, score or rank handoffs, distribution items,
versions, follow-ups, decisions, open questions, limitations, appendix entries,
artifacts, rights status, risk, reproducibility, coverage, sources, or
securities, recommend allocations, optimize strategies, emit executable
advice, imply production readiness, or claim profitability.

Stage 33 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local handoff-notes descriptor referenced by the
manifest, renders a separate descriptive handoff-notes section, reports missing
optional descriptors as not supplied, rejects secret-like fields,
source-content/excerpt fields, and remote URLs, and does not execute commands,
run checks from report inputs, execute follow-ups, approve distribution, verify
rights or licenses, read artifact/evidence/source contents, verify outputs,
verify local environments, approve decisions, read raw private data contents,
embed private or proprietary excerpts, add adapters, fetch remote data, score
or rank handoffs, distribution items, versions, follow-ups, decisions, open
questions, limitations, appendix entries, artifacts, rights status, risk,
reproducibility, coverage, sources, or securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

`docs/STAGE_PLAN.md` now contains the full Stage 34 readiness specification for
a local/offline `local_archive_notes` report-input kind. Stage 34 may describe
only reviewer-supplied archive labels, related artifact paths, archive status
labels, owner labels, archive notes, and limitation notes, and it must not
execute commands, run checks from report inputs, move or delete files, decide
retention policy, approve distribution, verify rights or licenses, read
artifact/evidence/source contents, verify outputs, verify local environments,
approve decisions, read raw private data contents, fetch remote data, add
adapters, use account or portfolio data, use live feeds, score or rank archive
readiness, handoffs, distribution items, versions, follow-ups, decisions, open
questions, limitations, appendix entries, artifacts, rights status, risk,
reproducibility, coverage, sources, or securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

Stage 34 is now implemented as a local/offline report-input kind for the paper
report pack. It reads only a local archive-notes descriptor referenced by the
manifest, renders a separate descriptive archive-notes section, reports missing
optional descriptors as not supplied, rejects secret-like fields,
source-content/excerpt fields, and remote URLs, and does not execute commands,
run checks from report inputs, execute follow-ups, move or delete files, decide
retention policy, approve distribution, verify rights or licenses, read
artifact/evidence/source contents, verify outputs, verify local environments,
approve decisions, read raw private data contents, embed private or
proprietary excerpts, add adapters, fetch remote data, score or rank archive
readiness, handoffs, distribution items, versions, follow-ups, decisions, open
questions, limitations, appendix entries, artifacts, rights status, risk,
reproducibility, coverage, sources, or securities, recommend allocations,
optimize strategies, emit executable advice, imply production readiness, or
claim profitability.

`docs/STAGE_PLAN.md` now contains separate Stage 35 arbitrage roadmap reset
and Stage 36 complement candidate schema records. The old local delivery-notes
report-input idea is preserved as maintenance backlog, not the active next
checkpoint. Complement-parity work must stay deterministic and offline until
later reviewed stages add fee models, scanners, recorders, simulators, paper
ledgers, risk/manual approval, or demo connector boundaries.

Roadmap note: Stage 35-52 is now complete. The active next action is human
review of the disabled private-live gate design and private evidence
collection outside the public repo.

## Important files

- `AGENTS.md`: repo rules and first-read instructions.
- `PROJECT_SPEC.md`: stable project and module specification.
- `CHANGELOG.md`: external-facing milestone log.
- `docs/repo_map.md`: context-budget map for targeted reads.
- `docs/codex_long_running_controller.md`: staged continuation rules.
- `docs/STAGE_PLAN.md`: staged roadmap and non-goals.
- `docs/ARBITRAGE_ROADMAP.md`: active complement-parity roadmap and
  maintenance boundary for report-input expansion.
- `docs/complement_scanner.md`: Stage 38 offline scanner fixture format,
  CLI, and safety notes.
- `docs/stage8_polymarket_readiness.md`: Stage 8 readiness note and source
  links for the Polymarket US public market-data boundary.
- `docs/stage9_equities_readiness.md`: Stage 9 readiness note and source links
  for the SEC EDGAR public fundamentals boundary.
- `docs/stage11_report_sections_readiness.md`: Stage 11 readiness note for
  local/offline report-section expansion.
- `docs/stage12_report_inputs_readiness.md`: Stage 12 readiness note for a
  local/offline report-input manifest.
- `docs/engineering_log.md`: narrative engineering record.
- `src/edmn_trader/core/models.py`: exchange-agnostic core models.
- `src/edmn_trader/adapters/kalshi/client.py`: guarded read-only Kalshi Demo
  REST client for markets and orderbooks.
- `src/edmn_trader/adapters/kalshi/orderbook.py`: Kalshi orderbook normalizer.
- `src/edmn_trader/adapters/kalshi/readonly_recorder.py`: Stage 40 guarded
  Kalshi Demo read-only recorder.
- `src/edmn_trader/adapters/kalshi/demo_connector.py`: Stage 49 guarded
  Kalshi Demo request preview and Demo submit path mocked in tests.
- `src/edmn_trader/adapters/kalshi/demo_reconciliation.py`: Stage 50 local
  Kalshi Demo reconciliation replay and submit-eligibility blocker.
- `src/edmn_trader/adapters/polymarket_us/client.py`: guarded read-only
  Polymarket US public market-data client.
- `src/edmn_trader/adapters/polymarket_us/orderbook.py`: Polymarket US
  market-book normalizer.
- `src/edmn_trader/adapters/polymarket_us/market_recorder.py`: Stage 41
  guarded Polymarket US market-channel recorder.
- `src/edmn_trader/adapters/sec_edgar/client.py`: guarded read-only SEC EDGAR
  public companyfacts client.
- `src/edmn_trader/adapters/sec_edgar/companyfacts.py`: SEC companyfacts
  normalizer.
- `src/edmn_trader/data/snapshots.py`: snapshot model and snapshot JSONL
  persistence helpers.
- `src/edmn_trader/data/jsonl.py`: Decimal-safe JSONL helpers.
- `src/edmn_trader/data/replay.py`: deterministic replay session and metrics.
- `src/edmn_trader/data/live_events.py`: Stage 39 live-event schema and
  mocked recorder harness.
- `src/edmn_trader/data/book_rebuild.py`: Stage 42 recorded-event order book
  rebuild, deterministic hash, and consistency flag helpers.
- `src/edmn_trader/data/payload_safety.py`: shared secret-key rejection helper
  for raw payload persistence.
- `src/edmn_trader/arb/complement.py`: offline complement-parity candidate
  model.
- `src/edmn_trader/arb/scanner.py`: offline scanner for local fixture JSON and
  existing snapshot JSONL reports.
- `src/edmn_trader/arb/fill_simulation.py`: Stage 43 offline taker fill,
  slippage, latency shock, and failed-leg reserve simulator.
- `src/edmn_trader/arb/paper_engine.py`: Stage 44 paper-only complement
  proposal engine with locked candidate/simulation hashes.
- `src/edmn_trader/arb/paper_ledger.py`: Stage 45 paper ledger replay for
  local proposal, fill, settlement, position, fee, PnL, and mismatch state.
- `src/edmn_trader/arb/risk.py`: Stage 46 paper-only complement risk engine
  v2 for blocker checks and manual-review-required decisions.
- `src/edmn_trader/arb/approval.py`: Stage 47 local manual approval workflow
  for pending files, expiring approvals, hash checks, and single-use records.
- `src/edmn_trader/arb/monitoring.py`: Stage 48 offline daily validation
  report aggregation for local monitoring/research records.
- `src/edmn_trader/fees/`: explicit supplied/missing/unknown fee estimate
  scaffolds.
- `src/edmn_trader/research/fair_value.py`: deterministic baseline fair-value
  model.
- `src/edmn_trader/research/quotes.py`: non-executable dry-run quote engine and
  quote intents.
- `src/edmn_trader/research/equities.py`: exchange-agnostic equities
  fundamentals fact model.
- `src/edmn_trader/execution/demo.py`: Stage 5 risk decisions, fake adapter,
  execution boundary, and JSONL audit logging.
- `scripts/02_record_fixture_snapshots.py`: converts local fixtures to JSONL
  snapshots.
- `scripts/03_replay_snapshots.py`: replays JSONL snapshots and prints a
  concise metrics table.
- `scripts/04_quote_replay_dry_run.py`: replays JSONL snapshots through the
  dry-run quote engine and prints fair value and quote metrics.
- `scripts/05_demo_execution_smoke.py`: runs a local fake-adapter Stage 5
  smoke check with explicit demo opt-in support.
- `src/edmn_trader/scripts/market_maker_replay.py`: importable Stage 6 finite
  replay workflow for quote lifecycle, risk gates, logs, and run summaries.
- `scripts/06_market_maker_replay.py`: root wrapper for Stage 6 replay.
- `scripts/23_scan_complement_arb.py`: root wrapper for Stage 38 offline
  complement scanner.
- `scripts/39_mock_live_event_recorder.py`: root wrapper for the Stage 39
  local mocked WebSocket recorder harness.
- `scripts/40_kalshi_readonly_recorder.py`: root wrapper for the Stage 40
  guarded Kalshi Demo read-only recorder.
- `scripts/41_polymarket_market_recorder.py`: root wrapper for the Stage 41
  guarded Polymarket US market-channel recorder.
- `scripts/42_rebuild_orderbooks.py`: root wrapper for the Stage 42 offline
  recorded-event order book rebuild.
- `scripts/43_simulate_taker_fill.py`: root wrapper for the Stage 43 offline
  taker fill simulator.
- `scripts/44_paper_complement_engine.py`: root wrapper for the Stage 44
  paper-only complement proposal engine.
- `scripts/45_replay_paper_ledger.py`: root wrapper for the Stage 45 paper
  ledger replay.
- `scripts/46_complement_risk.py`: root wrapper for the Stage 46 complement
  risk v2 checks.
- `scripts/47_manual_approval.py`: root wrapper for the Stage 47 local manual
  approval workflow.
- `scripts/48_daily_validation_report.py`: root wrapper for the Stage 48
  offline daily validation report.
- `src/edmn_trader/scripts/kalshi_demo_connector.py`: importable Stage 49
  guarded Kalshi Demo connector preview CLI entry point.
- `scripts/49_kalshi_demo_connector.py`: root wrapper for the Stage 49 guarded
  Kalshi Demo connector preview.
- `src/edmn_trader/scripts/kalshi_demo_reconciliation.py`: importable Stage 50
  local Kalshi Demo reconciliation replay CLI entry point.
- `scripts/50_kalshi_demo_reconciliation.py`: root wrapper for the Stage 50
  local Kalshi Demo reconciliation replay.
- `src/edmn_trader/scripts/research_report.py`: importable Stage 7 offline
  Markdown report generator for Stage 6 logs and explicit fill assumptions.
- `scripts/07_research_report.py`: root wrapper for Stage 7 reporting.
- `src/edmn_trader/scripts/paper_report_pack.py`: importable Stage
  10/12/13/14/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34 offline paper research report-pack generator.
- `scripts/10_paper_report_pack.py`: root wrapper for Stage 10/12/13/14/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34
  report packs.
- `tests/test_kalshi_client.py`: mocked HTTP coverage for the Stage 2 client.
- `tests/test_kalshi_orderbook.py`: normalizer coverage.
- `tests/test_snapshots_jsonl.py`: snapshot/JSONL coverage.
- `tests/test_replay_snapshots.py`: replay and fixture-conversion coverage.
- `tests/test_quote_engine.py`: fair-value and dry-run quote-engine coverage.
- `tests/test_quote_replay_dry_run.py`: replay-based quote script coverage.
- `tests/test_demo_execution.py`: Stage 5 risk gate, blocked path, fake
  adapter, and audit log coverage.
- `tests/test_demo_execution_smoke.py`: Stage 5 smoke script coverage.
- `tests/test_market_maker_replay.py`: Stage 6 dry-run/demo, lifecycle,
  run-control, adapter-error, and script-summary coverage.
- `tests/test_research_report.py`: Stage 7 no-fill report, explicit fill
  attribution, secret-like fill rejection, and CLI coverage.
- `tests/test_polymarket_us_adapter.py`: Stage 8 Polymarket US fixture
  normalization, guarded public client, and malformed-book coverage.
- `tests/test_sec_edgar_adapter.py`: Stage 9 SEC companyfacts normalization,
  guarded public client, explicit User-Agent, and malformed-value coverage.
- `tests/test_live_event_recorder.py`: Stage 39 live-event schema and mocked
  recorder coverage.
- `tests/test_kalshi_readonly_recorder.py`: Stage 40 Kalshi read-only recorder
  guardrail coverage.
- `tests/test_polymarket_market_recorder.py`: Stage 41 Polymarket US
  market-channel recorder guardrail coverage.
- `tests/test_book_rebuild.py`: Stage 42 order book rebuild, deterministic
  hash, consistency flag, CLI, and unsupported-event coverage.
- `tests/test_fill_simulation.py`: Stage 43 FOK/IOC-like fill policy,
  partial-fill, slippage, latency shock, failed-leg reserve, output, and CLI
  coverage.
- `tests/test_paper_engine.py`: Stage 44 paper proposal, source-hash,
  risk-preview, deterministic output, and CLI coverage.
- `tests/test_paper_ledger.py`: Stage 45 paper ledger replay, position, fee,
  PnL, mismatch, output, and CLI coverage.
- `tests/test_complement_risk.py`: Stage 46 risk v2 blocker,
  manual-review-required, output, and CLI coverage.
- `tests/test_manual_approval.py`: Stage 47 pending approval, expiry,
  hash-check, single-use, output, and CLI coverage.
- `tests/test_daily_validation_report.py`: Stage 48 daily validation report
  metrics aggregation, output, and CLI coverage.
- `tests/test_kalshi_demo_connector.py`: Stage 49 connector preview, guardrail,
  reconciliation-required submit, mocked HTTP submit, and audit-redaction
  coverage.
- `tests/test_kalshi_demo_reconciliation.py`: Stage 50 reconciliation replay,
  duplicate, mismatch, submit-blocking, append-only output, and CLI coverage.
- `tests/test_paper_report_pack.py`: Stage 10/12/13/14/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34 report-pack coverage
  for observed metrics, source inventory, missing optional inputs, local SEC
  facts, manifest metadata, local run-comparison metadata, unsafe
  manifest/comparison rejection, local validation-summary metadata, unsafe
  validation-summary rejection, local review-notes metadata, unsafe
  review-notes rejection, local methodology-notes metadata, unsafe
  methodology-notes rejection, local data-dictionary metadata, unsafe
  data-dictionary rejection, local citation-index metadata, unsafe
  citation-index rejection, local term-glossary metadata, unsafe
  term-glossary rejection, local assumption-register metadata, unsafe
  assumption-register rejection, local coverage-matrix metadata, unsafe
  coverage-matrix rejection, local reproducibility-checklist metadata, unsafe
  reproducibility-checklist rejection, local risk-review metadata, unsafe
  risk-review rejection, local data-rights-review metadata, unsafe
  data-rights-review rejection, local artifact-inventory metadata, unsafe
  artifact-inventory rejection, local appendix-index metadata, unsafe
  appendix-index rejection, local limitation-register metadata, unsafe
  limitation-register rejection, local open-questions metadata, unsafe
  open-questions rejection, local decision-log metadata, unsafe decision-log
  rejection, local follow-up-register metadata, unsafe follow-up-register
  rejection, local version-notes metadata, unsafe version-notes rejection,
  local distribution-checklist metadata, unsafe distribution-checklist
  rejection, local handoff-notes metadata, unsafe handoff-notes rejection,
  local archive-notes metadata, unsafe archive-notes rejection, and CLI output.

## Commands that currently pass

```bash
pytest
ruff check .
python scripts/01_replay_orderbook_fixture.py
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage3_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage3_snapshots.jsonl
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage4_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage4_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage4_snapshots.jsonl
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage5_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage5_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage5_snapshots.jsonl
python scripts/05_demo_execution_smoke.py --log-output /tmp/edmn_stage5_execution_smoke.jsonl
python scripts/05_demo_execution_smoke.py --demo-opt-in --log-output /tmp/edmn_stage5_execution_smoke_approved.jsonl
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage6_snapshots.jsonl
python scripts/03_replay_snapshots.py --input /tmp/edmn_stage6_snapshots.jsonl
python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage6_snapshots.jsonl
python scripts/05_demo_execution_smoke.py --log-output /tmp/edmn_stage6_execution_smoke.jsonl
python scripts/05_demo_execution_smoke.py --demo-opt-in --log-output /tmp/edmn_stage6_execution_smoke_approved.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage6_snapshots.jsonl --log-output /tmp/edmn_stage6_market_maker.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage6_snapshots.jsonl --demo-opt-in --log-output /tmp/edmn_stage6_market_maker_demo.jsonl
python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage7_snapshots.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage7_snapshots.jsonl --log-output /tmp/edmn_stage7_market_maker.jsonl
python scripts/06_market_maker_replay.py --input /tmp/edmn_stage7_snapshots.jsonl --demo-opt-in --log-output /tmp/edmn_stage7_market_maker_demo.jsonl
python scripts/07_research_report.py --market-maker-log /tmp/edmn_stage7_market_maker.jsonl --output /tmp/edmn_stage7_report.md
python scripts/10_paper_report_pack.py --market-maker-log /tmp/edmn_stage7_market_maker.jsonl --sec-companyfacts tests/fixtures/sec_companyfacts_aapl.json --output-dir /tmp/edmn_stage10_report_pack
pytest tests/test_polymarket_us_adapter.py
pytest tests/test_sec_edgar_adapter.py
pytest tests/test_paper_report_pack.py
```

Optional environment validation:

```bash
python -m pip install -e ".[dev]"
```

## Known issues

- GitHub remote `origin` is configured for
  `https://github.com/minqiyang/market-neutral-trader.git`; do not
  push unless the user explicitly asks or the active workflow requires it.
- PR #1 merged Stage 5 into `main` at
  `6cd1d536fa41e721a998f23eab19d7129938c3da`.
- PR #2 merged the Stage 6 plan clarification into `main` at
  `a322310c7c9d1ab82c0307a35b8db79e704b9274`.
- Local `main` was fast-forwarded to `origin/main` after the PR #1 merge, and
  post-merge validation passed before this handoff update.
- A prior handoff-only update was pushed directly to `main` and GitHub reported
  branch-rule bypass warnings. Future staged work should default to branch +
  PR flow unless every owner-direct fast-path condition in
  `docs/codex_long_running_controller.md` is satisfied.
- `.github/workflows/ci.yml` exists, and the latest observed GitHub Actions CI
  run on `main` completed successfully. CI now runs `Validate` for pushes to
  `main`, pull requests to `main`, and pushes to `codex/**` branches, including
  the Stage 7 research report and Stage 10 report-pack commands.
- GitHub branch protection is enabled on `main` and requires the `Validate`
  status check.
- The Kalshi Demo client has mocked coverage and bounded read-only Demo network
  smoke evidence. The latest accepted VPS result is snapshot-only transport
  evidence and is not sequence, rebuild, replay, or duration evidence.
- Quote dry-runs emit non-executable intents. Stage 6 can convert those
  boundaries into fake-adapter demo execution requests only after explicit
  opt-in and Stage 5 risk approval. Offline fill simulation and bounded
  read-only WebSocket ingestion exist, but production trading and live
  market-making remain disabled.
- On the migrated Mac environment, root wrapper scripts may still need the
  repo fallback `PYTHONPATH=src` despite a passing editable install. The direct
  `python scripts/01_replay_orderbook_fixture.py` wrapper failed with
  `ModuleNotFoundError: No module named 'edmn_trader'` during Stage 41
  validation, while `PYTHONPATH=src python scripts/01_replay_orderbook_fixture.py`
  passed.

## PR workflow policy

`docs/codex_long_running_controller.md` now contains the publish policy for
future staged work. Default to branch + PR. An owner-direct fast path may skip
PR creation only when `gh` is authenticated as `minqiyang`, `origin` is
`minqiyang/market-neutral-trader`, work starts from clean synced
`origin/main`, work occurs on a `codex/` branch, local validation and branch
`Validate` pass, risk is low or medium, the change avoids all listed safety and
compliance hazards, no PR/divergence conflict exists, and the final update to
`main` is a normal push with no force, admin override, or branch-protection
bypass command. If any condition is false, create a PR or stop for human
review. High-risk or unclear work always stops for human review.

GitHub auto-merge may still be enabled only for clearly low-risk small PRs that
are narrow, locally validated, protected by required checks/reviews, and free of
credentials, production endpoints, order placement, WebSocket work, live
market-making loops, strategy optimization, large generated files, dependency
surprises, or compliance ambiguity.

`docs/codex_long_running_controller.md` also contains the compact
skill-orchestration policy for future staged work: use long-session governance
and token-budget rules on every checkpoint, read only the current handoff, repo
map, controller, active stage section, and project Skill first, treat optional
skills as accelerators rather than blockers, reserve Ponytail, TDD, grill-me,
and handoff for the narrow cases named there, and keep skill use bounded unless
a stop gate is triggered.

`docs/codex_long_running_controller.md` now uses delivery-unit batching for
staged publishes. Internal checkpoints are not publish checkpoints. Codex
should work on one `codex/` branch per coherent delivery unit and publish only
after the unit is complete, validated, risk-classified, reviewed when needed,
and the docs/logs/handoff are updated. Readiness clarification, implementation,
tests, docs/log/changelog updates, handoff updates, and due passing audit notes
may be folded into the same delivery branch when they are one coherent unit.
Do not create PRs for every small docs, handoff, or audit edit, and do not create
standalone handoff-only or audit-only PRs unless the controller risk/stop rules
or lack of an active delivery branch require them.

For merge-gated continuation, an open previous checkpoint PR is no longer an
automatic stop. Codex must first evaluate whether the PR can be safely
auto-merged: local validation, CI, clean mergeability, clean worktree, scoped
files, no forbidden trading/secrets/profitability changes, and README/risk/
handoff no-live-trading consistency must all pass. If they pass, merge the PR,
sync `origin/main`, create a fresh `codex/` branch, and continue. If any gate
fails, stop and report the failed gate.

The controller now also has a token-economical optional-skill policy. The
project Skill and token-budget rules stay default; TDD is for behavior changes;
Ponytail review is for final publish of implementation diffs; Matt Pocock
`grill-with-docs` is only for ambiguous/high-risk design or domain terminology
drift; EDD/eval-before-ship style is used only if installed and useful, or by
the equivalent checklist; and Skill Maker / skill-creator is reserved for
workflows that have repeated at least twice. If an optional skill is missing,
renamed, or noisy, use the equivalent checklist instead of debugging the skill.

## Safety boundaries

- Do not add credentials or secrets.
- Do not implement production order placement.
- Do not treat D2B fixture success as sequence-verified, replay-qualified, or
  real-stream rebuild evidence.
- Do not treat a public trade, REST lifecycle observation, or orderbook message
  as account-fill, WebSocket keepalive, sequence, duration, or replay evidence.
- Do not treat synthetic classifier, chain, recovery, or benchmark success as
  real campaign, backup, duration, sequence, rebuild, or replay qualification.
- Do not extend live complement-arbitrage scanning from unqualified recorder
  evidence.
- Keep fill simulation offline and based only on explicitly qualified inputs.
- Do not enable live or production trading.
- Do not make profitability claims.
- Keep Kalshi-specific code under `src/edmn_trader/adapters/kalshi`.
- Treat complement-parity outputs as audit/paper-candidate metadata only, not
  executable order intents or risk-free opportunities.

## Next recommended action

After D2E-F1 review, merge, merged-main verification, and Phase 0B software-only
VPS refresh, stop. The next task may only be a separately owner-authorized
post-fix Real5M. Do not reuse the consumed authorization or retry from this
task.

## Exact next prompt suggestion

Authorize one bounded post-D2E-F1 Real5M only after confirming the reviewed
public commit and Phase 0B software-only VPS acceptance evidence. Keep Demo,
read-only, raw-private, disabled-live-gate, and zero-submit boundaries.

## Last updated timestamp

2026-07-11 21:05:44 -07:00

## Round 8G lifecycle gate v2 checkpoint

Round 8G confirmed that the VPS Demo market
`KXWTACHALLENGERMATCH-26JUL10STEMAR-MAR` finalized with result `yes` after an
early-close sports match, before the planned seven-day evidence end. The
campaign and watcher were deliberately finalized with their private
root-specific supervisors; raw data remains under the private-data root and
was not copied into the public repository.

Public follow-up is on branch `codex/round8g-lifecycle-gate-v2-impl` from the
clean current-main checkout. The gate now uses conservative lifecycle
deadlines, fetches event metadata for seven-day discovery, rejects unsafe
early-close and sports/match candidates by default, preserves lifecycle fields
in manifests, and separates data integrity from market-lifecycle evidence
validity. Validation remains Demo/read-only with the public live gate disabled.

## D2E next boundary

After D2E merge and clean merged-main verification, the next task is a fresh
Phase 0B deployment-governance run for the merged D2E commit. It may deploy and
run software-only validation/benchmarks, but must stop before credentials or
market network. Any future Real5M requires a new explicit owner authorization;
the prior authorization was not consumed.

Exact next prompt title:
`Phase 0B-Resume D2E Deployment Governance and VPS Synthetic Acceptance`.
