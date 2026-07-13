# Changelog

All notable project milestones are recorded here. This project follows the
spirit of Keep a Changelog, with stage-oriented entries instead of release
numbers while the repository is still in early research scaffolding.

## Unreleased

- Bounded runtime market selection independently from complete discovery
  auditing. Smoke and campaign launches now stop after the requested eligible
  market count, cap logical orderbook probes at 100, and fail closed with an explicit
  probe-limit blocker when no eligible market is found within that bound.
  Cursor exhaustion and all-market lifecycle diagnostics remain complete, while
  orderbook-scan and eligible-count completeness are reported separately. No
  credential, production, or order-write behavior changed.
- Added D2E-F3 run-scoped WebSocket request evidence and strict subscription
  identity. New runtime writes allocate unique positive command IDs per channel
  across reconnects, advance channel generations across connection epochs,
  persist pending/send outcomes before trusting ACKs, and independently replay
  request/ACK/SID bindings. Invalid IDs and channels fail before mutation;
  legacy v1 binding evidence remains readable. No production or order path was
  added.
- Corrected rejection replay across reconnects. A valid next-generation request
  may terminate rejected without conflicting with the prior connection, while
  ACK/rejection contradictions within one complete request identity conflict and
  duplicate rejections remain idempotent.
- Correlated documented channel-less WebSocket error responses through the
  run-unique native command ID. Unknown or old-connection errors remain raw,
  fail monitor trust, and cannot mutate a current binding.
- Added D2E-F2 native-envelope coherence and binding-state fail-close behavior.
  Conflicting top-level/nested `type`, `channel`, `id`, or `sid` values and
  Boolean identifiers are typed exclusions; exact duplicate ACKs are
  idempotent, contradictory ACKs conflict only their channel, and pre-ACK data
  remains raw but cannot enter D2B/D2C. Runtime, monitor, terminal summary, and
  independent validator replay now agree on binding failures. No network,
  credential, production, or order-write behavior was added.
- Corrected D2E subscription identity to be channel-scoped. Split public
  acknowledgments may now bind distinct orderbook and trade SIDs under one
  command without trade evidence invalidating D2B. D2A records optional
  generation/binding/state provenance, runtime and validator expose the same
  per-channel summary, and unexpected orderbook SIDs remain fail-closed until
  explicit resubscription. An identity-model marker distinguishes new formal
  rows from readable historical rows; native command IDs are matched to the
  active generation, and ambiguous plural-channel ACKs with one SID do not
  satisfy acknowledgment, including nested SIDs. New public data rows require
  acknowledged bindings, and wrong-SID trades are quarantined from D2C without
  affecting D2B. Native type/channel contradictions are excluded, and the first
  SID after a supported no-SID ACK binds that channel. This is a fixture-only
  correction with no threshold, credential, network, production, or
  order-write change.
- Replaced the Round 8J4 global `occurrence_datetime` hard stop with selection
  profile v4's dual-interpretation policy. Canary and seven-day candidates now
  require independently safe close and expected-expiration deadlines;
  historical/current and malformed occurrence values reject, while a future
  value is only an additional conservative bound. Missing occurrence may pass
  only without early-close risk. Manifests and discovery diagnostics record
  semantic/equality, component-deadline, dual-pass, overlap, and near-miss
  evidence. Smoke remains separate, and no live, production, or write path was
  added.
- Corrected Round 8J discovery completeness and lifecycle semantics. Market
  scans now report complete only after cursor exhaustion, fail closed at a
  100-page bound, deduplicate markets before eligibility counting, evaluate all
  usable lifecycle candidates, and emit versioned profile hashes, multi-label
  rejection totals, and hashed near-miss margins. Official documentation calls
  `occurrence_datetime` retrospective while Demo returned it as a future value,
  so profile v3 retains the field as a conservative deadline and blocks live
  progression pending clarification. Canary early-close, Sports/match, event
  metadata, expected-expiration, orderbook, Demo-only, and disabled-live gates
  remain intact.
- Aligned D2B snapshots with Kalshi's official AsyncAPI omitted-side contract.
  A single omitted `yes_dollars_fp` or `no_dollars_fp` field now becomes an
  explicit empty native side when the opposite side is valid; both omitted,
  null, wrong-type, and malformed sides remain fail-closed. Frame/state schemas
  advance to v2, frame evidence records source presence, normalized terminal
  hashes are representation-independent, and the validator independently
  rebuilds the same result. No production or order-write behavior was added.
- Corrected D2B subscription identity to be channel-scoped within each
  connection/segment generation. Distinct `orderbook_delta` and public `trade`
  SIDs no longer cross-invalidate native book state, while true same-channel
  SID changes still fail closed. Deterministic runtime tests cover trades
  before/after snapshot, cross-channel sequence reuse, frame/state hashes, and
  independent validator replay. No schema, production, credential, or
  order-write behavior was added.
- Reworked Demo candidate discovery to fetch market pages before event
  hydration, deduplicate and batch core event requests, cache event records,
  bound retryable 429/5xx/transport failures, distinguish incomplete coverage,
  and avoid treating a non-authoritative `event_type` field as required core
  metadata. No production, credential, or order-write behavior was added.
- Added an explicit 30-minute read-only canary selection profile with a
  one-hour safety buffer, complete event metadata, non-sports/match screening,
  conservative early-close rejection, structured reasons, and manifest
  provenance. Smoke and seven-day behavior remain separate; Demo-only and
  disabled-live-gate boundaries are unchanged.
- Wired D2A-D2D into the reviewed Kalshi read-only WebSocket runtime. New smoke
  and campaign runs emit `edmn.kalshi.ws.runtime.v2` artifacts with D2A
  admission, D2B rebuild hashes, D2C public/lifecycle/connection evidence, D2D
  append-chain durability, timestamp-derived timing, threshold provenance,
  independently derived validator dimensions, command/channel-bound
  per-connection subscription acknowledgment, selection-policy provenance,
  admitted selected-market freshness, all-segment classification, detached
  provenance, checkpoint count/offset validation, exact threshold-policy
  validation, independent D2B replay validation, bounded lifecycle retries,
  recursive private-account field rejection, typed nested subscription
  rejection, monitor fail-closed behavior, rotation, and tail-reconciling crash
  recovery. Full timing and terminal disposition are bound into the append
  chain, including an evidence-only recovery terminal segment. Boundary
  disconnect/freshness intervals are counted, and persisted HTTP(S) Git remote
  provenance strips credential-bearing URL components. Durable callbacks fail
  terminally, D2A rows are connection/acknowledgment-bound with contiguous
  indices, run roots are no-overwrite, private runtime metadata is rejected,
  imported-package provenance replaces current-directory provenance, and
  finalized-before-manifest crash windows are recoverable. Split channel
  acknowledgments validate correctly, connection windows are interval-bound,
  frame-hash summary memory is constant-size, and open-status writes are
  checkpoint/segment/interval bounded. Launch selection and explicit pricing
  are checkpoint-bound, channel acknowledgments are raw-grounded, trade SIDs
  cannot reset orderbook state, terminal/recovery validation streams under a
  100k memory gate, and missing orderbook freshness remains unknown. Typed-only
  acknowledgments fail, manifest paths are root-contained, segment artifacts
  are recursively inventoried by path, partial rotation successors fail closed,
  and running monitor snapshots retain observed critical evidence without
  allowing stale keepalive or late raw acknowledgment to pass.
  The monitor revalidates completed D2 roots without rewriting the report,
  rejects unsafe fixed metadata, and recovery records bind partial-tail counts
  to pre/post file sizes while preflighting all manifested symlink paths.
  Nested private fields, control-frame pricing contradictions, and noncanonical
  launch provenance now fail closed before evidence can be presented as valid.
  Legacy v1 artifacts remain readable but are not selected for new WebSocket
  runs. Tests are mocked and public live trading remains disabled.
- Added D2D orthogonal evidence classification, timestamp-derived duration,
  exact UTF-8 append chains, atomic fsynced checkpoints/summaries, closed-file
  hashing, byte/time rotation, partial-tail crash recovery, fresh-segment reset
  metadata, and a streaming 100k synthetic benchmark. Unknown critical
  dimensions cannot produce overall pass, and no callback rehashes the full
  file. No private data, market network, retention deletion, replay
  qualification, credential, or order behavior was added.
- Added D2C fixture-first public evidence contracts for selected-market public
  trades, selected-market REST lifecycle fallback, typed connection events,
  and independent keepalive/lifecycle/orderbook freshness dimensions. The
  recorder subscription includes the public `trade` channel, while account
  fills, nonselected trades, stale/unknown lifecycle, and MVE metadata remain
  filtered or fail-closed. No market network, global lifecycle subscription,
  credential, replay-qualification, or order behavior was added.
- Added D2B native incremental Kalshi WebSocket orderbook rebuild for admitted
  D2A snapshot/delta envelopes. The fixture-only adapter keeps independent
  Decimal state per market/connection/segment, handles explicit legacy and
  unified price scales, invalidates underflow or malformed segments, derives
  canonical YES frames, and emits deterministic semantic frame/state hashes.
  It does not establish sequence integrity or replay qualification and adds no
  network, campaign, persistence, credential, or order behavior.
- Added D2A Kalshi WebSocket raw evidence schema v2 with preserved native
  SID/sequence/timestamps and payloads, separate local append order, explicit
  connection and integrity segments, conservative sequence states,
  per-market snapshot-before-delta admission, deterministic parsed-payload
  hashes, and a typed legacy path. Non-object frames fail closed, and
  auth-header or deeply nested secret-like keys are rejected. This adds no
  subscriptions, rebuild, campaign, or order behavior; public live trading
  remains disabled.
- Added lifecycle gate v2 for long-horizon read-only campaigns: conservative
  deadline selection uses expected expiration, occurrence, and early-close
  metadata; event metadata is fetched for seven-day discovery; sports/match and
  unsafe early-close markets are rejected; manifests preserve lifecycle fields;
  and validation separates data integrity from invalid market-lifecycle
  evidence. The live gate remains disabled.
- Corrected Kalshi Demo market discovery for bounded read-only WebSocket runs:
  paginate `status=open` results, normalize REST lifecycle statuses, preserve
  raw status metadata, separate discovery HTTP/parse failures from empty or
  ineligible results, and keep the five-minute and seven-day time buffers
  distinct. Production and order-write paths remain unavailable.
- Added public Round 8B lifecycle gates for read-only recorder campaigns:
  market status and time-to-close checks, manifest lifecycle metadata,
  finalized/closed-market evidence invalidation, and monitor lifecycle/liveness
  display. Live trading remains disabled.
- Refreshed README and `docs/visual_overview.md` Mermaid diagrams for the
  post-PR #109 Demo dry-run/guarded submit boundary and public/private
  separation while preserving the disabled-live public boundary.
- Tightened the Stage 49/50 Demo boundary: dry-run previews remain available
  without credentials or reconciliation state, while Demo submit opt-in now
  requires a provided clean Demo reconciliation state and remains covered by
  mocked HTTP tests.
- Added Stage 52 release and portfolio packaging docs with GitHub Release copy,
  reviewer-facing project summary, and resume-ready bullets while preserving
  the disabled-live public boundary.
- Added GitHub-rendered Mermaid diagrams to the README and
  `docs/visual_overview.md` for the Stage 52 workflow, six-layer architecture,
  safety gate, and public/private boundary.
- Upgraded the public README into a Stage 52 landing page with system workflow,
  architecture layers, local commands, validation status, safety boundaries,
  and private-live gate prerequisites.
- Added Stage 52 private live gate design and disabled public guard. The public
  placeholder always returns disabled status, exposes no endpoint, credential,
  wallet, broker, live user-order channel, or order payload, and keeps all
  private-live prerequisites marked unmet.
- Added Stage 51 offline rolling paper/demo validation framework. It aggregates
  local research JSONL artifacts into deterministic 7/30/90-day JSONL, JSON,
  and Markdown reports, tracks paper/demo validation metrics where available,
  marks validation as not completed, and lists unmet private-live prerequisites.
- Added Stage 50 local Kalshi Demo reconciliation replay for accepted,
  rejected, fill, cancel, error, timeout, and backfill-style mock events. The
  replay links Stage 49 connector audit records to append-only reconciliation
  state, treats duplicate events idempotently, reports mismatches, and blocks
  later Demo submit eligibility when mismatches exist.
- Added Stage 49 guarded Kalshi Demo connector previews and mocked submit
  coverage. The connector consumes hash-bound manual approval, passing risk,
  and healthy paper ledger records, defaults to dry-run, rejects production
  URLs, limits FOK/IOC Demo requests to tiny size, and redacts auth-like values
  in local audit logs.
- Added Stage 48 offline daily validation reporting for recorder uptime, data
  lag, gap count, candidate counts, rejection reasons, paper/demo outcomes,
  fees, slippage, failed-leg incidents, reconciliation health, and kill-switch
  events.
- Added Stage 47 local manual approval workflow with deterministic pending
  approval files, expiring approvals, proposal/candidate hash verification,
  and single-use approval enforcement.
- Added Stage 46 complement risk engine v2 that blocks stale data, data gaps,
  missing/unknown fees, insufficient net edge, exposure/open-order/daily-loss
  breaches, reconciliation mismatch, and active kill switch while still
  requiring manual approval.
- Added Stage 45 paper ledger replay that consumes local paper proposal, fill,
  and settlement records, preserves source hashes, tracks positions, fees,
  PnL, and reconciliation mismatches, and emits paper-only JSONL/Markdown
  state.
- Added Stage 44 paper-only complement proposal generation that locks scanner
  candidate and fill-simulation source hashes, emits deterministic JSONL and
  Markdown research records, and keeps manual approval required without
  executable order intents.
- Added Stage 43 offline taker fill/slippage/failed-leg simulation that
  stresses FOK/IOC-like two-leg assumptions, partial fills, latency shock, and
  failed-leg reserve from explicit local fixtures without executable order
  intents.
- Added Stage 42 offline order book rebuild and replay consistency tooling
  that reads recorded event JSONL, writes normalized snapshots, emits
  deterministic book hashes, and reports gap/stale/out-of-order flags without
  live connections or executable order intents.
- Added a Stage 41 guarded Polymarket US market-channel recorder that requires
  explicit live-readonly opt-in, rejects non-US-public boundaries, writes raw
  event and normalized snapshot JSONL, and is covered by mocked HTTP tests
  only.
- Added a Stage 40 guarded Kalshi Demo read-only recorder that requires
  explicit live-readonly opt-in, rejects non-Demo boundaries, writes raw event
  and normalized snapshot JSONL, and is covered by mocked HTTP tests only.
- Added a Stage 39 live market-data event schema and local mocked
  WebSocket-style recorder harness with deterministic JSONL output and
  payload secret-key rejection, without real live connections or credentials.
- Added a Stage 38 offline complement scanner that reads local fixture JSON or
  existing snapshot JSONL, applies explicit fee assumptions, and emits
  deterministic JSONL plus Markdown audit/paper research reports without
  executable order intents.
- Redirected the active roadmap from continued report-input metadata expansion
  to same-market YES/NO complement parity research, added
  `docs/ARBITRAGE_ROADMAP.md` as the long-range Stage 35-52 roadmap, and
  marked Stages 11-34 report-input expansion as maintenance-only.
- Added an offline Decimal-only complement-arbitrage candidate model with
  explicit fee, slippage, failed-leg reserve, depth, stale-book, missing-fee,
  locked/crossed-book, and manual-review handling. The model emits audit or
  paper-candidate metadata only and does not place orders or claim risk-free
  profit.
- Completed the compact governance audit after Stage 35 readiness, confirming
  synced `main`, passing `Validate`, branch protection, no open PRs, and no
  drift before continuing to Stage 35 implementation.
- Clarified Stage 35 readiness for a local/offline `local_delivery_notes`
  report-input kind that records delivery labels, related artifact paths,
  recipient labels, delivery status labels, delivery notes, and limitations
  without transferring files, approving distribution, verifying rights, scoring
  delivery readiness, or producing advice.
- Added Stage 34 local/offline `local_archive_notes` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 34 readiness for a local/offline `local_archive_notes`
  report-input kind that records archive labels, related artifact paths,
  archive status labels, owners, archive notes, and limitations without
  reading artifact contents, moving or deleting files, deciding retention
  policy, scoring archive readiness, or producing advice.
- Completed the compact governance audit after Stage 33 implementation,
  confirming synced `main`, passing `Validate`, branch protection, no open PRs,
  and no drift before continuing to the next readiness checkpoint.
- Added Stage 33 local/offline `local_handoff_notes` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 33 readiness for a local/offline `local_handoff_notes`
  report-input kind that records handoff labels, related artifact paths,
  recipient or owner labels, status labels, handoff notes, and limitations
  without reading artifact contents, approving distribution, verifying rights,
  scoring handoffs, or producing advice.
- Added Stage 32 local/offline `local_distribution_checklist` report-input
  support to the paper report pack, with descriptor Markdown output,
  missing-input disclosure, and rejection of secret-like fields,
  source-content/excerpt fields, and remote URLs.
- Completed the compact governance audit after Stage 32 readiness, confirming
  synced `main`, passing `Validate`, branch protection, no open PRs, and no
  drift before continuing to Stage 32 implementation.
- Clarified Stage 32 readiness for a local/offline
  `local_distribution_checklist` report-input kind that records distribution
  item labels, related artifact paths, readiness status labels, owners, review
  notes, and limitations without reading artifact contents, approving
  distribution, verifying rights, scoring checklist items, or producing advice.
- Added Stage 31 local/offline `local_version_notes` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 31 readiness for a local/offline `local_version_notes`
  report-input kind that records report version labels, local artifact paths,
  change-summary labels, owner/status labels, and limitations without reading
  artifact contents, approving distribution, scoring versions, or producing
  advice.
- Completed the compact governance audit after Stage 30 implementation,
  confirming synced `main`, passing `Validate`, branch protection, no open PRs,
  and no drift before continuing to the next readiness checkpoint.
- Added Stage 30 local/offline `local_follow_up_register` report-input support
  to the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 30 readiness for a local/offline
  `local_follow_up_register` report-input kind that records follow-up labels,
  related report section labels, local reference paths, owner/status labels,
  tracking notes, and limitations without reading referenced contents,
  executing follow-ups, scoring follow-ups, or producing advice.
- Added Stage 29 local/offline `local_decision_log` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Completed the compact governance audit after Stage 29 readiness, confirming
  synced `main`, passing `Validate`, branch protection, no open PRs, and no
  drift before continuing to Stage 29 implementation.
- Clarified Stage 29 readiness for a local/offline `local_decision_log`
  report-input kind that records decision labels, decision context labels,
  local reference paths, owner/status labels, rationale notes, and limitations
  without reading referenced contents, approving decisions, scoring decisions,
  or producing advice.
- Added Stage 28 local/offline `local_open_questions` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 28 readiness for a local/offline `local_open_questions`
  report-input kind that records open question labels, affected report
  sections, local reference paths, owner/status labels, and limitations without
  reading referenced contents, scoring questions, or producing advice.
- Added Stage 27 local/offline `local_limitation_register` report-input
  support to the paper report pack, with descriptor Markdown output,
  missing-input disclosure, and rejection of secret-like fields,
  source-content/excerpt fields, and remote URLs.
- Clarified Stage 27 readiness for a local/offline
  `local_limitation_register` report-input kind that records limitation labels,
  affected report sections, local evidence or artifact paths, scope notes,
  mitigation notes, and limitations without reading referenced contents,
  scoring limitations, or producing advice.
- Added Stage 26 local/offline `local_appendix_index` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 26 readiness for a local/offline `local_appendix_index`
  report-input kind that records appendix entry labels, report section labels,
  local artifact paths, appendix purpose notes, and limitations without reading
  artifact contents, verifying outputs, ranking appendix entries, or producing
  advice.
- Added Stage 25 local/offline `local_artifact_inventory` report-input support
  to the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 25 readiness for a local/offline
  `local_artifact_inventory` report-input kind that records generated artifact
  labels, artifact type labels, local paths, generation-source labels,
  intended report-use notes, and limitations without reading artifact
  contents, verifying outputs, ranking artifacts, or producing advice.
- Added Stage 24 local/offline `local_data_rights_review` report-input support
  to the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 24 readiness for a local/offline
  `local_data_rights_review` report-input kind that records data labels,
  rights status labels, permitted-use notes, restriction notes, evidence paths,
  and limitations without reading evidence contents, determining legal rights,
  verifying licenses, deciding redistribution permissions, scoring rights
  status, or producing advice.
- Added Stage 23 local/offline `local_risk_review` report-input support to the
  paper report pack, with descriptor Markdown output, missing-input disclosure,
  and rejection of secret-like fields, source-content/excerpt fields, and
  remote URLs.
- Clarified Stage 23 readiness for a local/offline `local_risk_review`
  report-input kind that records risk-control labels, boundary labels,
  mitigation notes, review status labels, evidence paths, and limitations
  without executing checks, reading evidence contents, evaluating policies,
  scoring risk, placing orders, or producing advice.
- Added Stage 22 local/offline `local_reproducibility_checklist`
  report-input support to the paper report pack, with descriptor Markdown
  output, missing-input disclosure, and rejection of secret-like fields,
  source-content/excerpt fields, and remote URLs.
- Clarified Stage 22 readiness for a local/offline
  `local_reproducibility_checklist` report-input kind that records
  reproduction step labels, artifact paths, command labels, environment labels,
  expected output labels, and limitations without executing commands, reading
  artifact contents, verifying environments or outputs, fetching remote data,
  scoring reproducibility, or producing advice.
- Added Stage 21 local/offline `local_coverage_matrix` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 21 readiness for a local/offline `local_coverage_matrix`
  report-input kind that records report-section/input/check coverage metadata
  without executing checks, reading source contents, fetching remote data,
  scoring coverage, or producing advice.
- Added Stage 20 local/offline `local_assumption_register` report-input
  support to the paper report pack, with descriptor Markdown output,
  missing-input disclosure, and rejection of secret-like fields,
  source-content/excerpt fields, and remote URLs.
- Clarified Stage 20 readiness for a local/offline
  `local_assumption_register` report-input kind that records assumption labels,
  rationale, source paths, scope, and limitations without reading source
  contents, fetching remote data, ranking assumptions, or producing advice.
- Added Stage 19 local/offline `local_term_glossary` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 19 readiness for a local/offline `local_term_glossary`
  report-input kind that records terms, definitions, source paths, usage scope,
  and limitations without reading source contents, fetching remote data,
  ranking terms, or producing advice.
- Added Stage 18 local/offline `local_citation_index` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields, source-content/excerpt
  fields, and remote URLs.
- Clarified Stage 18 readiness for a local/offline `local_citation_index`
  report-input kind that records citation labels, source paths, citation
  purpose, rights notes, and limitations without reading source contents,
  embedding private/proprietary excerpts, fetching remote data, or producing
  advice.
- Added Stage 17 local/offline `local_data_dictionary` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields and remote URLs.
- Clarified Stage 17 readiness for a local/offline `local_data_dictionary`
  report-input kind that records field definitions, units, source paths,
  rights/sensitivity labels, and caveats without reading raw private data
  contents, fetching remote data, or producing advice.
- Added Stage 16 local/offline `local_methodology_notes` report-input support
  to the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields and remote URLs.
- Clarified Stage 16 readiness for a local/offline `local_methodology_notes`
  report-input kind that records methodology context, assumptions, and caveats
  without reading private data contents, fetching remote data, or producing
  advice.
- Added Stage 15 local/offline `local_review_notes` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields and remote URLs.
- Clarified Stage 15 readiness for a local/offline `local_review_notes`
  report-input kind that records reviewer notes, caveats, and follow-up
  questions without reading private data contents, fetching remote data, or
  producing advice.
- Added Stage 14 local/offline `local_validation_summary` report-input support
  to the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields and remote URLs.
- Clarified Stage 14 readiness for a local/offline `local_validation_summary`
  report-input kind that describes already-run local checks and artifacts
  without executing commands, fetching remote data, adding adapters, implying
  production readiness, or producing advice.
- Added Stage 13 local/offline `local_run_comparison` report-input support to
  the paper report pack, with descriptor Markdown output, missing-input
  disclosure, and rejection of secret-like fields and remote URLs.
- Clarified Stage 13 readiness for a local/offline `local_run_comparison`
  report-input kind that compares already generated project outputs without
  adding remote fetching, new adapters, ranking, allocation advice, executable
  advice, unsupported redistribution, or profitability claims.
- Added Stage 12 local/offline report-input manifest support for the paper
  report pack, with manifest Markdown output, missing-input disclosure, and
  rejection of secret-like fields and remote URLs.
- Clarified Stage 12 readiness for a local/offline report-input manifest that
  records source rights, assumption scope, and required/optional status without
  adding new data adapters or executable advice.
- Added Stage 11 local/offline report-section expansion to the paper report
  pack, including a source inventory section that labels missing inputs as not
  supplied.
- Clarified Stage 11 readiness for local/offline report-section expansion of
  the Stage 10 paper report pack, with no new data adapters, live feeds,
  security ranking, allocation advice, strategy optimization, execution paths,
  or profitability claims.
- Added Stage 10 offline paper research report-pack generation from local
  Stage 6/7 attribution inputs and local SEC companyfacts fixtures, with
  Markdown output, explicit not-supplied sections, and limitation notes.
- Added `scripts/10_paper_report_pack.py` and the `edmn-paper-report-pack`
  package entry point. The report pack remains descriptive, non-executable,
  offline, and free of security ranking, allocation advice, live feeds,
  execution, and profitability claims.
- Clarified Stage 10 as an offline paper research report pack that may combine
  Stage 7 attribution outputs and Stage 9 SEC fundamentals, while excluding
  trading signals, security ranking, broker integration, live feeds, and
  profitability claims.
- Added a fixture-first SEC EDGAR public fundamentals adapter under
  `src/edmn_trader/adapters/sec_edgar`.
- Added an exchange-agnostic `EquityFundamentalFact` research model and local
  SEC companyfacts fixture coverage for normalized public fundamentals,
  explicit User-Agent behavior, guarded `data.sec.gov` access, and malformed
  value rejection.
- Clarified Stage 9 readiness: future work may target only SEC EDGAR public
  fundamentals with local fixtures and a read-only adapter; broker integration,
  credentials, account data, live quote feeds, paid-vendor data, trading, and
  strategy optimization remain out of scope.
- Added a fixture-first Polymarket US public market-data adapter under
  `src/edmn_trader/adapters/polymarket_us`.
- Added local Polymarket US market-book fixture coverage for normalization into
  the exchange-agnostic `NormalizedOrderBook`, guarded public base URL
  enforcement, read-only unauthenticated GET behavior, and malformed/empty book
  rejection.
- Clarified Stage 8 readiness: future work may target only Polymarket US public
  market data with local fixtures and an unauthenticated read-only adapter;
  international endpoints, trading, wallets, WebSockets, and region bypass
  remain out of scope.
- Added Stage 7 offline research report generation from Stage 6 logs and
  optional explicit local fill fixtures, with Decimal-safe realized PnL, fee,
  and inventory attribution.
- Added `scripts/07_research_report.py` and the `edmn-research-report` package
  entry point. Reports separate observed Stage 6 counts from supplied fill
  assumptions, reject secret-like fill fields, and do not infer fills from
  fake/demo adapter submissions.
- Added offline tests and CI validation for no-fill reports, explicit fill
  attribution, secret-like fill field rejection, and report CLI output.
- Clarified the Stage 7 plan for offline PnL attribution and research reports:
  local Stage 6 logs as required input, explicit optional fill assumptions,
  no fill inference from fake/demo submissions, Decimal-safe attribution,
  Markdown report output, limitation notes, offline tests, and validation
  commands.
- Added Stage 6 finite market-maker replay workflow that consumes JSONL
  snapshots, generates inventory-aware quote candidates, compares them with
  in-memory open quote state, emits place/replace/cancel/hold lifecycle
  decisions, applies Stage 5 risk gates, and writes structured JSONL logs plus
  run summaries.
- Added `scripts/06_market_maker_replay.py` and the
  `edmn-market-maker-replay` package entry point. Default mode remains
  dry-run/fake-adapter only; explicit `--demo-opt-in` is required before fake
  adapter submissions can occur.
- Added offline tests for dry-run adapter blocking, explicit demo opt-in, quote
  lifecycle decisions, max position, max open orders, max notional, max loss,
  kill switch, non-demo endpoints, `LIVE_DISABLED`, adapter errors, and script
  summary output.
- Clarified the Stage 6 plan for a finite replay-driven inventory-aware demo
  market-maker workflow, including dry-run defaults, explicit demo opt-in,
  Stage 5 risk-gate reuse, structured JSONL logs, run summaries, offline tests,
  validation commands, and out-of-scope boundaries.
- Tightened Stage 6 readiness requirements for quote lifecycle decisions,
  replace/cancel/hold intents, max open orders, max notional, max loss, and
  kill-switch controls.
- Order placement beyond explicitly risk-gated demo smoke tests, WebSocket
  ingestion, production trading, and profitability claims remain out of scope
  until separately reviewed.

## Stage 5 - Risk-gated demo execution smoke test - 2026-06-12

### Added

- Stage 5 execution boundary with deterministic pre-execution risk decisions.
- Explicit demo opt-in guard and Kalshi Demo base URL guard before any adapter
  action can run.
- Fake/offline execution adapter for local tests and smoke checks.
- Structured JSONL execution audit logging for approved, rejected, and adapter
  error paths.
- Local smoke script at `scripts/05_demo_execution_smoke.py`.
- Offline tests for `LIVE_DISABLED`, cancel/modify blocked paths, failed risk
  limits, production endpoint rejection, missing demo opt-in, adapter call
  logging, and adapter error logging.

### Safety

- Stage 5 uses fake/offline adapter behavior only in tests and local smoke
  validation. It adds no credentials, live network execution, production
  endpoint support, WebSocket ingestion, fill simulation, market-making loop,
  strategy optimization, or profitability claim.

### Validation

- Required checks include `pytest`, `ruff check .`,
  `python scripts/01_replay_orderbook_fixture.py`,
  `python scripts/02_record_fixture_snapshots.py --output /tmp/edmn_stage5_snapshots.jsonl`,
  `python scripts/03_replay_snapshots.py --input /tmp/edmn_stage5_snapshots.jsonl`,
  `python scripts/04_quote_replay_dry_run.py --input /tmp/edmn_stage5_snapshots.jsonl`,
  and `python scripts/05_demo_execution_smoke.py --log-output /tmp/edmn_stage5_execution_smoke.jsonl`.

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
