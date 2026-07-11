# Engineering Log

## Why this project exists

This project exists to demonstrate professional trading-system engineering in a
portfolio-friendly way. The emphasis is not on claims of profit. The emphasis is
on correctness, staged delivery, risk boundaries, deterministic tests, and the
ability to explain how a trading research platform is built from safe
foundations.

## Round 8J-A canary selection profile

The bounded 30-minute canary now has an explicit profile rather than inheriting
short-smoke selection. It requires complete event metadata, rejects sports and
match-like events, uses a one-hour safety buffer, rejects early-close markets,
and records its profile and conservative deadline in campaign evidence. The
change reuses the existing selector, discovery, manifest, validator, and Demo
WebSocket path without adding an execution path or a second framework.

## Round 8J-B discovery reliability

The first canary scan exposed an event-hydration N+1 path and a schema mismatch:
the official core event response supplies category and title but not the
locally assumed `event_type`. Hundreds of per-event requests also occurred
between market pages, so a later page failure made the partial scan
non-authoritative. Discovery now pages markets first, deduplicates and batches
event tickers, caches core events, bounds retries, and explicitly reports
incomplete coverage. Auxiliary image metadata remains outside lifecycle
completeness.

## D2E runtime integration

D2A-D2D originally merged as independently verified software contracts, while
the operational `kalshi-ws-smoke` entrypoint still wrote the historical
campaign schema. D2E fixes that assembly gap rather than weakening the Real5M
evidence gate.

The recorder now exposes D2A events and typed connection observations to one
runtime session. Each event is admitted once, rebuilt once, checked for public
trade evidence once, and appended once to a segment-local D2D chain. This keeps
event callbacks O(1) with respect to file size. Terminal validation is allowed
to scan closed files to verify chain, checkpoint, nested D2A schema, and
closed-file hash.

Runtime timing comes from UTC evidence boundaries and connection windows, not
the requested duration. Lifecycle fallback is periodically refreshed through
an injectable selected-market provider; tests use only local mocks. Sequence,
rebuild, lifecycle, keepalive, duration, process, supervisor, backup, and replay
dimensions remain independent. A quiet book can warn without becoming a
transport failure, and unknown keepalive or sequence semantics cannot become
an overall pass.

The legacy campaign reader remains for historical inspection. New WebSocket
runs use the versioned D2 runtime writer, including preflight-blocked runs, so a
future operator cannot silently fall back to `v2.readonly_campaign.v1`.

The first independent adversarial review found three correctness issues and two
coverage/provenance gaps. Correction round 1 made acknowledgments
connection-local, prevented excluded markets from refreshing selected-market
evidence, made the validator rederive critical counts and dimensions from the
append chain, made monitor health honor validator failure, preserved the
evaluated selection policy, and added mocked reconnect, canary, nested-secret,
wrong-market, and summary-tamper regressions. The dead legacy WebSocket writer
was removed; the historical reader remains.

Correction round 2 followed a fresh detached-worktree review. Provenance now
names detached HEAD explicitly; subscription acknowledgment proves the command
and full public channel set; sequence and rebuild aggregation cannot inherit a
historical pass across an unknown current segment; blocked discovery preserves
selection policy; and crash recovery emits synchronized, validator-consumable
terminal artifacts without restart. Each correction has a focused regression.

## D2D evidence classification, durability, and performance

D2D turns the D2A-D2C fixture contracts into an explicit software evidence
model. Twelve dimensions remain orthogonal, so a transport snapshot cannot
silently become sequence, rebuild, duration, backup, or replay evidence.
Duration uses timestamps and exact disconnect arithmetic rather than configured
duration. Threshold policy version, commit, and effective time remain attached
to each timing record.

The durability path hashes exact canonical JSONL bytes incrementally with a
length prefix. Checkpoints flush and fsync data before atomic replacement and
directory fsync. Open segments expose only persisted checkpoint scope. Close
computes one full-file hash and records rotation, backup, and retention
metadata. Default rotation is 64 MiB or one hour.

Crash recovery resumes from the last checkpoint, validates complete tail rows,
removes only a partial final row, finalizes the old segment, and writes fresh
segment metadata requiring a new connection/snapshot without inherited book
state. A streaming 100k synthetic benchmark exercises checkpoints, close/hash
verification, and crash recovery without credentials, market network, private
data, campaign operation, deletion, or order behavior.

## D2C public trade, lifecycle, and connection evidence

D2C completes the fixture-tested public evidence surface without adding an
account or order path. The selected-market subscription payload now includes
the public `trade` channel. A narrow adapter consumes D2A envelopes, filters
nonselected markets, rejects account-like fields, preserves native trade
identifiers/prices/quantities/timestamps without conversion, and writes only
accepted public trades. Zero trades remains a valid quiet-market state.

Lifecycle evidence uses an already-observed selected-market REST metadata
fixture. It records raw and normalized status, source, observation time and
age, but explicitly cannot prove WebSocket transport. Stale, unknown, and MVE
observations stay typed and non-valid rather than being promoted.

Connection evidence has explicit open, close, error, reconnect, and
resubscription records. Transport keepalive, lifecycle observation age, and
orderbook quiet interval remain independent. Ping/Pong is
`UNKNOWN_NOT_OBSERVED` unless directly supplied. All tests are local fixtures;
D2C adds no global lifecycle subscription, credential use, market network,
replay qualification, or execution behavior.

## D2B native incremental orderbook rebuild

D2B adds the first consumer of the D2A native WebSocket envelope. The adapter
maintains exact native YES and NO price-to-quantity maps independently for each
market, connection, and integrity segment. Admitted snapshots replace state
atomically; admitted signed deltas update one level; exact-zero levels are
removed; malformed values, identity drift, and negative resulting quantities
invalidate rather than partially mutate or clamp the book. A fresh admitted
snapshot can recover an invalid state with an explicit reset reason.

The main modeling choice is to keep venue-native state before deriving the
canonical YES view. In legacy side-price mode, native NO bids become YES asks
through `1 - no_price`; in unified YES-price mode, reported NO-side prices are
already on the YES scale. Explicit D2A metadata selects the mode. Because the
reviewed recorder currently omits `use_yes_price`, the compatibility path names
and records its legacy/default assumption rather than guessing from prices.

Frames preserve source side/price, D2A sequence state, one-sided/locked/crossed
labels, and deterministic semantic hashes built without binary floats. The
implementation and synthetic tests open no network connection and inspect no
private data. Existing REST/full-book replay stays unchanged. D2B does not
claim sequence continuity, replay qualification, durability evidence, or any
authorization for D2C, D2D, campaigns, credentials, or order paths.

## D2A raw WebSocket schema and transport integrity

D2A fixes an evidence-modeling ambiguity in the first read-only WebSocket
recorder: its old top-level `sequence` was only `len(rows) + 1`, while any
venue-native SID, sequence, timestamp, and unknown fields remained buried in
the payload. That shape could be mistaken for exchange ordering and could not
express connection, subscription, snapshot, or resynchronization boundaries.

The new `edmn.kalshi.ws.raw.v2` envelope keeps native values unchanged under
explicit `native_*` fields and preserves the complete parsed payload. Local
append order is now `local_row_index`. A deterministic canonical-JSON payload
hash protects each parsed native payload without adding whole-file durability
work. Secret-like payload keys remain fail-closed.

An integrity tracker assigns connection and segment identities, begins every
orderbook segment in `RESYNC_REQUIRED`, excludes deltas until a snapshot, and
starts fresh history after a supported-policy gap, duplicate, out-of-order
observation, SID change, reconnect, or resubscription. Default sequence
semantics remain unknown: increasing values are observations, not proof of
contiguous delivery. Legacy rows parse through a typed local-sequence-only view
and cannot masquerade as native sequence evidence.

Snapshot admission is market-specific inside a segment: one requested market's
snapshot cannot admit another requested market's deltas. Missing and
unrequested market tickers remain preserved but excluded.

This checkpoint is fixture-only and does not add subscriptions, venue calls,
book reconstruction, campaign qualification, execution behavior, or trading
evidence. The existing summary `gap_count=0` remains unmeasured until a later,
separately authorized integrity/classification stage.

The merge review retained the parsed-payload hash contract and added explicit
UTF-8, non-finite-number, and mutation checks. It also made non-object frames
fail closed and extended secret-key rejection through nested sequences and all
Kalshi authentication-header names.

## Round 8C-D1 Demo market discovery

The first VPS WebSocket smoke stopped with `NO_ACTIVE_DEMO_MARKET`, but a
bounded REST diagnostic found thousands of `status=open` results. Kalshi REST
returned `active` in each market record, the first 20 results all had empty
orderbooks, and later results contained non-empty books. The old selector read
only those first 20 records, did not follow the cursor, and collapsed HTTP,
parse, and eligibility failures into one blocker.

The corrected selector follows at most five 1,000-market pages, maps REST
statuses into the lifecycle gate while preserving the raw value, prioritizes
current quote-size indicators before bounded orderbook probes, and emits
structured blockers. A five-minute smoke uses a 900-second safety buffer;
seven-day selection retains the strict 86,400-second buffer. No production or
order-write behavior is added.

## Round 8B public lifecycle gates

Round 8B tightened the public read-only campaign boundary after private ops
evidence showed that a finalized market can make a long recorder run stale
without producing useful seven-day evidence. The public campaign helper now
evaluates market status, close/expiration time, a 24-hour safety buffer, and
known empty orderbooks before a long WebSocket campaign can be considered
selectable.

The validator keeps raw artifact integrity separate from campaign evidence
validity: finalized, closed, settled, resolved, or expired markets produce
`MARKET_CLOSED_OR_FINALIZED_ENDS_CAMPAIGN_EVIDENCE` instead of a generic stale
condition. The monitor now shows the subscribed market, lifecycle status,
close time, time since close, and separate liveness fields for supervisor,
campaign process, WebSocket freshness, market lifecycle, and exchange heartbeat
observation. The exchange heartbeat remains `UNKNOWN` unless a recorder
actually writes it.

## Why start with Kalshi-style binary orderbooks

Kalshi-style binary prediction markets are a useful first target because they
are event-driven, have a concrete demo environment, and expose an orderbook
shape that requires careful normalization. The venue returns YES bids and NO
bids, not a traditional YES bid/ask book. That forces the first implementation
to solve a real market-data modeling problem before any strategy work can begin.

## Why Stage 0 and Stage 1 focused on normalization

Stage 0 created the repository, package, safety docs, and test/lint structure.
Stage 1 added the core exchange-agnostic models and a Kalshi fixed-point
orderbook normalizer backed by local fixtures. This kept the first functional
slice deterministic and reviewable. It also avoided a common trading-system
mistake: building strategy or execution code before the market-data contract is
well understood.

The key tradeoff was intentionally narrow scope. The project did not add a REST
client, WebSocket ingestion, execution engine, optimizer, or strategy. That
slows visible feature growth, but it gives the platform a safer foundation.

## Why Stage 1.5 exists

Stage 1.5 creates the continuity layer needed for long-running Codex work. The
project is expected to continue across sessions, machines, branches, and future
goal-driven runs. Without a compact handoff, repo map, stage plan, decision log,
and controller policy, future sessions would waste context rediscovering the
same constraints or might accidentally exceed the stage boundary.

## Tradeoffs made in Stage 1.5

- Added documentation and governance files instead of new trading behavior.
- Kept `AGENTS.md` concise and moved detailed continuation policy into docs.
- Preserved the existing normalizer and tests because this stage is about
  continuity, not market-data feature work.
- Initialized Git locally because the folder was not yet a repository, but did
  not add a remote or push.

## Stage 2 read-only market-data client

Stage 2 added a narrow Kalshi Demo REST client for public market metadata and
market orderbooks. The client uses `httpx` with injectable transport so tests
can mock every HTTP response and avoid network access, credentials, and
environment assumptions. The default and only accepted base URL is the Kalshi
Demo REST base URL documented for this project.

The client deliberately exposes only read-only market and orderbook methods.
It does not include authentication, order placement, WebSocket subscriptions,
strategy hooks, or production endpoint configuration. Error handling is explicit
for HTTP status failures, transport failures, malformed JSON, malformed response
shape, and empty orderbooks.

The main tradeoff was adding a real HTTP dependency before live API use. That
is acceptable here because the dependency is exercised through mocked tests and
establishes the client seam needed for later optional live-read smoke checks.

## Stage 3 offline snapshots and replay

Stage 3 added deterministic offline infrastructure so future quote engines,
strategy tests, and PnL attribution can work from replayable market-data
snapshots instead of live API calls. The new snapshot format records the
exchange, ticker, observed timestamp, local recorded timestamp, source type,
schema version, normalized orderbook, optional raw payload, notes, and tags.

The project uses JSONL because it is simple to append, inspect, diff, and stream
one record at a time. Decimal values are serialized as strings so price and
quantity precision survives roundtrips. Replay strict mode fails on
out-of-order observed timestamps by default; non-strict mode can sort and warn
for exploratory use.

The main tradeoff was keeping replay limited to book metrics. There is no fill
simulation, no strategy loop, and no execution action. That preserves Stage 3 as
an offline data layer and leaves quote generation, simulation assumptions, and
PnL attribution for later stages.

## Stage 4 fair-value and dry-run quotes

Stage 4 added the first quote-generation layer, but kept it explicitly offline
and non-executable. The baseline fair-value model uses the normalized book
midpoint when both sides are present and deterministic one-sided fallbacks when
only one side is available. The quote engine combines fair value, observed book
spread, tick and price boundaries, quantity, and bounded inventory skew to emit
dry-run bid and ask candidates.

The important boundary is that these are not executable orders. They are
inspection objects labeled `dry_run_only`, and the replay script prints them as
research output from local JSONL snapshots. Stage 4 does not authenticate, call
execution adapters, place or cancel orders, simulate fills, optimize strategy
parameters, or make any performance claim.

The main tradeoff was choosing a simple midpoint baseline instead of a more
ambitious model. That keeps the implementation explainable and testable while
creating the interface future research stages can replace with richer models.

## Stage 5 risk-gated demo execution smoke

Stage 5 added the first execution-boundary infrastructure, but kept it local,
fake-adapter based, and risk-gated. The new request model can represent blocked
attempts such as `LIVE_DISABLED` so rejections are still auditable. Every
request is checked against explicit execution mode, demo opt-in, Kalshi Demo
base URL, price, quantity, notional, position, inventory, and daily-loss limits
before any adapter method can run.

The execution audit log is JSONL so approved attempts, rejected attempts, and
adapter errors can be inspected without raw command logs or secret-bearing
payloads. The local smoke script is disabled by default through missing demo
opt-in and uses a fake adapter even when opt-in is supplied.

The main tradeoff was not adding authenticated Kalshi order placement yet. That
keeps Stage 5 focused on the safety contract: execution actions are blocked
unless risk approval and audit logging are present. A later stage can connect
the same boundary to broader dry-run/demo workflows only after this guardrail is
merged and reviewed.

## Stage 6 plan clarification

The Stage 6 readiness check found that the roadmap heading identified the next
checkpoint, but the specification was too compact to implement safely. The
clarified plan keeps Stage 6 finite, replay-driven, and dry-run by default. It
requires Stage 4 fair-value and quote generation to feed Stage 5 risk-gated
execution requests, with fake/demo adapter access only after explicit opt-in
and risk approval.

The clarification also makes the accounting boundary explicit: Stage 6 may
count quote candidates, risk approvals, rejections, skipped actions, and adapter
submissions, but it must not infer fills, PnL, profitability, or production
readiness. That keeps Stage 7 responsible for attribution and research
reporting assumptions.

A follow-up readiness audit tightened the Stage 6 specification around quote
lifecycle and risk controls. The implementation checkpoint must model open
quote state, compare desired quotes with prior quotes, emit place, replace,
cancel, or hold intents, and audit those decisions before any adapter access.
It also must enforce max position, max open orders, max notional exposure, max
loss, and a kill switch in deterministic offline tests.

## Stage 6 finite market-maker replay

Stage 6 connected the previously separate offline pieces into one bounded
workflow. The replay runner consumes JSONL snapshots, uses the Stage 4 quote
engine to generate bid and ask candidates with bounded inventory skew, compares
those desired quotes with an in-memory open quote state, and emits explicit
place, replace, cancel, or hold lifecycle decisions.

The execution boundary remains deliberately narrow. Dry-run mode is the
default and never calls an adapter. Demo opt-in still uses only the fake adapter
and only after Stage 5 risk approval. The runner logs frames, quote candidates,
lifecycle decisions, risk decisions, adapter submissions or errors, and a run
summary that separates quotes, approvals, rejections, skipped actions, and
adapter calls. It does not infer fills or PnL.

The main tradeoff was keeping the market-maker loop finite and script-driven
instead of adding a daemon or live event loop. That gives Stage 7 enough audited
state for attribution/reporting work while preserving the no-production,
no-WebSocket, no-live-market-making boundary.

## Stage 7 plan clarification

The Stage 7 heading identified PnL attribution and research reporting as the
next checkpoint, but the original text was too compact to implement safely. The
clarified plan keeps Stage 7 offline and evidence-bound: reports may consume
Stage 6 decision logs and optional local fill fixtures, but they must not infer
fills from fake/demo adapter submissions.

The core accounting boundary is explicit. Observed Stage 6 counts and supplied
fill assumptions must be reported separately, and every fill, fee, mark,
slippage, or adverse-selection calculation must be labeled as an assumption or
approximation. Empty/no-fill runs still produce a report, but with zero supplied
fills and zero realized PnL.

The main tradeoff is postponing richer reporting and adapter work. Stage 7 is
only allowed to prove deterministic offline attribution and disclosure hygiene;
production endpoints, WebSockets, optimization, and profitability framing remain
out of scope.

## Stage 7 offline research reports

Stage 7 added a Markdown research report generator that consumes structured
Stage 6 market-maker replay logs and, optionally, an explicit local fill JSONL
fixture. The report separates observed decision counts from hypothetical fill
assumptions so fake/demo adapter submissions never become implied fills.

The attribution is deliberately small and auditable: explicit fills produce
FIFO-style realized gross PnL, total fees, net PnL, and ending inventory using
`Decimal`. Empty/no-fill runs still produce a valid report with zero supplied
fills and zero realized PnL. Fill fixtures reject secret-like field names so
account or credential-bearing data does not become part of the reporting path.

The main tradeoff was avoiding richer charts, mark-to-market assumptions, and
adverse-selection metrics until explicit input data exists for those
calculations. Stage 7 proves the reporting boundary and disclosure hygiene
without adding live data access, production endpoints, strategy optimization,
or profitability framing.

## Stage 8 readiness clarification

The Stage 8 readiness check found that "Polymarket" is not one uniform target.
The safe implementation boundary is Polymarket US public market data only, with
local fixtures first and no trading, authentication, wallets, WebSockets, or
international Polymarket endpoint usage.

The main tradeoff is postponing live HTTP smoke and any richer market-data
surface until terms, rate limits, and endpoint stability are reviewed again.
That keeps the next implementation useful while avoiding region-bypass and
execution ambiguity.

## Stage 8 Polymarket US public market-data adapter

Stage 8 added the second prediction-market adapter, scoped to Polymarket US
public market data. The implementation normalizes a public market-book fixture
into the existing `NormalizedOrderBook` model and exposes a guarded read-only
client for the documented Polymarket US public base URL.

The important boundary is what was not added. The adapter does not use the
international Polymarket endpoint, authentication, wallets, account data,
WebSockets, trading endpoints, live HTTP smoke by default, or execution paths.
Tests use local fixtures and mocked HTTP only.

## Stage 9 readiness clarification

The Stage 9 readiness check narrowed "U.S. equities research adapter" to SEC
EDGAR public fundamentals. That avoids the ambiguous and higher-risk meanings
of equities data: broker APIs, live quote feeds, paid vendor feeds,
proprietary exchange data, account data, or trading signals.

The next implementation should be fixture-first and read-only. Future live SEC
HTTP access must identify itself with an explicit User-Agent, obey SEC
fair-access limits, and remain outside the first implementation slice.

## Stage 9 SEC EDGAR fundamentals adapter

Stage 9 added a fixture-first SEC EDGAR adapter for public companyfacts data.
The parser normalizes SEC JSON into an exchange-agnostic
`EquityFundamentalFact`, and the guarded client is restricted to
`https://data.sec.gov` with an explicit User-Agent.

The implementation does not add broker integration, account or portfolio data,
live quote feeds, paid-vendor data, proprietary exchange data, order placement,
strategy optimization, or production execution. Tests use local fixtures and
mocked HTTP only.

## Stage 10 plan clarification

After Stage 9, the next useful step is reporting, not another data source.
Stage 10 is scoped as an offline paper research report pack that can combine
existing Stage 7 attribution outputs with Stage 9 SEC fundamentals.

The boundary stays narrow: reports may summarize observed metrics and public
fundamentals, but they must not rank securities, emit trading signals, optimize
strategies, or imply production readiness or profitability.

## Stage 10 paper research report pack

Stage 10 added a local Markdown report-pack generator. It reuses the Stage 7
research report path for observed replay metrics and explicit fill assumptions,
then adds a separate SEC fundamentals section from local companyfacts fixtures.

The report pack labels missing optional inputs as not supplied and keeps
limitations visible in the output. It does not add broker integration, account
data, live feeds, order paths, ranking, allocation advice, strategy
optimization, production execution, or profitability claims.

## Stage 11 readiness clarification

After Stage 10, the safe next step is adding descriptive report sections, not
new data access or advice. The clarified Stage 11 boundary keeps additional
sections local/offline and requires each section to identify its local source,
label missing optional inputs as not supplied, and stay separate from observed
metrics, supplied assumptions, fundamentals, and limitations.

The main tradeoff is deliberately postponing richer data sourcing, dashboards,
recommendations, and optimization. Stage 11 should improve report readability
without changing the project into a ranking or allocation system.

## Stage 11 local report-section expansion

Stage 11 added a source inventory section to the existing Stage 10 report pack.
The implementation stays inside the report-pack generator and uses only local
paths already supplied to the command.

Missing fills or SEC companyfacts inputs are shown as not supplied instead of
being inferred. The report remains descriptive and non-executable; it does not
add new data adapters, live feeds, ranking, allocation advice, optimization, or
profitability framing.

## Stage 12 readiness clarification

After Stage 11, the safe next input expansion is a local manifest rather than a
new data adapter. The clarified Stage 12 boundary lets the report pack describe
additional local inputs with path, label, rights note, assumption scope, and
required/optional status.

The main tradeoff is keeping the manifest descriptive. Stage 12 should make
source rights and missing-input behavior explicit without reading private data
contents, fetching remote data, ranking assets, recommending allocations, or
creating executable advice.

## Stage 12 local report-input manifest

Stage 12 added an optional local JSON manifest for the paper report pack. The
manifest describes local report inputs by path, kind, display label,
rights/redistribution note, assumption scope, and required/optional status.

The report renders those entries in a separate Markdown section and reports a
missing manifest as not supplied. Manifest parsing rejects secret-like field
names and remote URLs, and it does not fetch data, add adapters, rank assets,
recommend allocations, or create executable advice.

## Stage 13 readiness clarification

After Stage 12, the next concrete input kind should use data the project
already knows how to produce. The clarified Stage 13 boundary is a local
run-comparison report input that can describe multiple existing project outputs
without creating a new market-data adapter or fetching remote data.

The tradeoff is intentionally limiting comparison output to descriptive local
metadata and observed facts. Stage 13 may make report packs easier to compare
across local runs, but it must not rank securities, choose a best run, optimize
strategy parameters, recommend allocations, emit executable advice, or claim
profitability.

## Stage 13 local run-comparison input

Stage 13 added support for `local_run_comparison` manifest entries in the
existing paper report pack. The implementation reads a local comparison
descriptor as metadata, renders a separate Markdown section, reports missing
optional comparison descriptors as not supplied, and rejects secret-like fields
or remote URLs.

The descriptor does not cause the report pack to ingest raw private data or
fetch referenced outputs. It gives the report a controlled way to summarize
local run labels, file paths, observed decision counts, not-supplied inputs, and
limitation notes while avoiding ranking, allocation advice, optimization,
executable advice, or profitability framing.

## Stage 14 readiness clarification

After Stage 13, the next safe report-input kind is validation metadata, not new
data access. The clarified Stage 14 boundary allows a local validation-summary
descriptor to record checks the user already ran and artifacts the report pack
already produced.

The key boundary is that report inputs are descriptive data, not instructions.
Stage 14 may render command labels, statuses, artifact paths, timestamps, and
limitation notes, but it must not execute commands, fetch remote data, imply
production readiness, optimize strategies, produce advice, or claim
profitability.

## Stage 14 local validation-summary input

Stage 14 added support for `local_validation_summary` manifest entries in the
paper report pack. The implementation reads a local validation descriptor as
metadata, renders a separate Markdown section, reports missing optional
validation descriptors as not supplied, and rejects secret-like fields or
remote URLs.

The report pack still does not execute commands from report inputs. Validation
summaries describe checks and artifacts supplied by the user, which keeps the
report useful for local review without turning it into a production-readiness
claim or advice system.

## Stage 15 readiness clarification

After Stage 14, the next safe report-input kind is human review metadata. The
clarified Stage 15 boundary allows a local review-notes descriptor to record
reviewer-supplied notes, caveats, source paths, follow-up questions, and
limitations.

The boundary stays narrow: review notes are not a way to ingest private data or
produce recommendations. Stage 15 should render local notes as descriptive
context while avoiding command execution, remote fetching, ranking, allocation
advice, production-readiness claims, and profitability framing.

## Stage 15 local review-notes input

Stage 15 added support for `local_review_notes` manifest entries in the paper
report pack. The implementation reads a local review-notes descriptor as
metadata, renders a separate Markdown section, reports missing optional review
descriptors as not supplied, and rejects secret-like fields or remote URLs.

The report pack still does not read private note files referenced by the
descriptor. It renders reviewer-supplied labels, source paths, note text,
follow-up questions, and limitation notes as descriptive context without
turning those notes into recommendations or production-readiness claims.

## Stage 16 readiness clarification

After Stage 15, the next safe report-input kind is methodology metadata. The
clarified Stage 16 boundary allows a local methodology-notes descriptor to
record reviewer-supplied method context, assumption descriptions, local source
paths, and caveats.

The boundary stays descriptive. Stage 16 should make methodology context
visible in the report pack without reading private files, fetching remote data,
ranking runs, optimizing strategies, producing advice, or implying production
readiness.

## Stage 16 local methodology-notes input

Stage 16 added support for `local_methodology_notes` manifest entries in the
paper report pack. The implementation reads a local methodology-notes
descriptor as metadata, renders a separate Markdown section, reports missing
optional methodology descriptors as not supplied, and rejects secret-like
fields or remote URLs.

The report pack still does not read private methodology files referenced by the
descriptor. It renders reviewer-supplied method labels, source paths,
methodology text, assumption scope, and limitation notes as descriptive context
without turning methodology notes into advice or production-readiness claims.

After Stage 16, the next safe report-input kind is a data dictionary. The
clarified Stage 17 boundary allows a local data-dictionary descriptor to record
reviewer-supplied field labels, data type labels, units, definitions, local
source paths, rights/sensitivity labels, and caveats.

The boundary stays descriptive. Stage 17 should make field metadata visible in
the report pack without reading raw private data contents, fetching remote
data, ranking fields or sources, optimizing strategies, producing advice, or
implying production readiness.

## Stage 17 local data-dictionary input

Stage 17 added support for `local_data_dictionary` manifest entries in the
paper report pack. The implementation reads a local data-dictionary descriptor
as metadata, renders a separate Markdown section, reports missing optional
data-dictionary descriptors as not supplied, and rejects secret-like fields or
remote URLs.

The report pack still does not read raw local data files referenced by the
descriptor. It renders reviewer-supplied field labels, source paths, data type
labels, units, definitions, rights/sensitivity labels, and limitation notes as
descriptive context without turning field metadata into ranking, advice, or
production-readiness claims.

After Stage 17, the next safe report-input kind is a citation index. The
clarified Stage 18 boundary allows a local citation-index descriptor to record
reviewer-supplied citation labels, local source paths, citation purpose,
rights notes, and limitation notes.

The boundary stays descriptive. Stage 18 should make source attribution
metadata visible in the report pack without reading source contents, embedding
private or proprietary excerpts, fetching remote data, ranking sources,
producing advice, or implying production readiness.

## Stage 18 local citation-index input

Stage 18 added support for `local_citation_index` manifest entries in the
paper report pack. The implementation reads a local citation-index descriptor
as metadata, renders a separate Markdown section, reports missing optional
citation-index descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read source files referenced by the descriptor.
It renders reviewer-supplied citation labels, source paths, citation purpose,
rights notes, and limitation notes as descriptive context without embedding
private/proprietary excerpts or turning source metadata into ranking, advice,
or production-readiness claims.

After Stage 18, the next safe report-input kind is a term glossary. The
clarified Stage 19 boundary allows a local term-glossary descriptor to record
reviewer-supplied terms, definitions, local source paths, usage scope, and
limitation notes.

The boundary stays descriptive. Stage 19 should make terminology visible in
the report pack without reading source contents, embedding private or
proprietary excerpts, fetching remote data, ranking terms, producing advice, or
implying production readiness.

## Stage 19 local term-glossary input

Stage 19 added support for `local_term_glossary` manifest entries in the paper
report pack. The implementation reads a local term-glossary descriptor as
metadata, renders a separate Markdown section, reports missing optional
term-glossary descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read source files referenced by the descriptor.
It renders reviewer-supplied terms, source paths, definitions, usage scope, and
limitation notes as descriptive context without embedding private/proprietary
excerpts or turning terminology metadata into ranking, advice, or
production-readiness claims.

After Stage 19, the next safe report-input kind is an assumption register. The
clarified Stage 20 boundary allows a local assumption-register descriptor to
record reviewer-supplied assumption labels, rationale, local source paths,
scope, and limitation notes.

The boundary stays descriptive. Stage 20 should make assumption metadata
visible in the report pack without reading source contents, embedding private
or proprietary excerpts, fetching remote data, ranking assumptions, producing
advice, or implying production readiness.

## Stage 20 local assumption-register input

Stage 20 added support for `local_assumption_register` manifest entries in the
paper report pack. The implementation reads a local assumption-register
descriptor as metadata, renders a separate Markdown section, reports missing
optional assumption-register descriptors as not supplied, and rejects
secret-like fields, source-content or excerpt fields, and remote URLs.

The report pack still does not read source files referenced by the descriptor.
It renders reviewer-supplied assumption labels, source paths, rationale, scope,
and limitation notes as descriptive context without embedding
private/proprietary excerpts or turning assumption metadata into ranking,
advice, or production-readiness claims.

After Stage 20, the next safe report-input kind is a coverage matrix. The
clarified Stage 21 boundary allows a local coverage-matrix descriptor to record
reviewer-supplied mappings between report sections, local input descriptors,
validation labels, source paths, coverage notes, and limitation notes.

The boundary stays descriptive. Stage 21 should make coverage metadata visible
in the report pack without executing checks, reading source contents, fetching
remote data, scoring coverage, producing advice, or implying production
readiness.

## Stage 21 local coverage-matrix input

Stage 21 added support for `local_coverage_matrix` manifest entries in the
paper report pack. The implementation reads a local coverage-matrix descriptor
as metadata, renders a separate Markdown section, reports missing optional
coverage-matrix descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not execute checks or read source files referenced
by the descriptor. It renders reviewer-supplied section labels, source paths,
input labels, validation labels, coverage notes, and limitation notes as
descriptive context without scoring coverage or turning coverage metadata into
ranking, advice, or production-readiness claims.

After Stage 21, the next safe report-input kind is a reproducibility
checklist. The clarified Stage 22 boundary allows a local reproducibility
descriptor to record reviewer-supplied reproduction step labels, local artifact
paths, command labels, environment labels, expected output labels, and
limitation notes.

The boundary stays descriptive. Stage 22 should make reproducibility metadata
visible in the report pack without executing commands, reading artifact or
source contents, verifying local environments or outputs, fetching remote data,
scoring reproducibility, producing advice, or implying production readiness.

## Stage 22 local reproducibility-checklist input

Stage 22 added support for `local_reproducibility_checklist` manifest entries
in the paper report pack. The implementation reads a local reproducibility
descriptor as metadata, renders a separate Markdown section, reports missing
optional reproducibility-checklist descriptors as not supplied, and rejects
secret-like fields, source-content or excerpt fields, and remote URLs.

The report pack still does not execute commands or read artifact/source files
referenced by the descriptor. It renders reviewer-supplied reproduction step
labels, artifact paths, command labels, environment labels, expected output
labels, and limitation notes as descriptive context without verifying outputs,
scoring reproducibility, producing advice, or implying production readiness.

After Stage 22, the next safe report-input kind is a risk review. The
clarified Stage 23 boundary allows a local risk-review descriptor to record
reviewer-supplied risk-control labels, boundary labels, mitigation notes,
review status labels, local evidence paths, and limitation notes.

The boundary stays descriptive. Stage 23 should make risk-review metadata
visible in the report pack without executing checks, reading evidence contents,
evaluating policies, placing orders, scoring risk, producing advice, or
implying production readiness.

## Stage 23 local risk-review input

Stage 23 added support for `local_risk_review` manifest entries in the paper
report pack. The implementation reads a local risk-review descriptor as
metadata, renders a separate Markdown section, reports missing optional
risk-review descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not execute checks, evaluate policies, run risk
checks, place orders, or read evidence/source files referenced by the
descriptor. It renders reviewer-supplied risk-control labels, boundary labels,
mitigation notes, review status labels, evidence paths, and limitation notes as
descriptive context without scoring risk, producing advice, or implying
production readiness.

After Stage 23, the next safe report-input kind is a data-rights review. The
clarified Stage 24 boundary allows a local data-rights descriptor to record
reviewer-supplied data labels, rights status labels, permitted-use notes,
restriction notes, local evidence paths, and limitation notes.

The boundary stays descriptive. Stage 24 should make data-rights metadata
visible in the report pack without reading evidence contents, determining legal
rights, verifying licenses, deciding redistribution permissions, scoring
rights status, producing advice, or implying production readiness.

## Stage 24 local data-rights-review input

Stage 24 added support for `local_data_rights_review` manifest entries in the
paper report pack. The implementation reads a local data-rights descriptor as
metadata, renders a separate Markdown section, reports missing optional
data-rights-review descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read evidence/source files referenced by the
descriptor, determine legal rights, verify licenses, decide redistribution
permissions, or evaluate policies. It renders reviewer-supplied data labels,
rights status labels, permitted-use notes, restriction notes, evidence paths,
and limitation notes as descriptive context without scoring rights status,
producing advice, or implying production readiness.

After Stage 24, the next safe report-input kind is an artifact inventory. The
clarified Stage 25 boundary allows a local artifact-inventory descriptor to
record reviewer-supplied generated artifact labels, artifact type labels,
local paths, generation-source labels, intended report-use notes, and
limitation notes.

The boundary stays descriptive. Stage 25 should make artifact-inventory
metadata visible in the report pack without reading artifact contents,
verifying outputs, verifying local environments, ranking artifacts, producing
advice, or implying production readiness.

## Stage 25 local artifact-inventory input

Stage 25 added support for `local_artifact_inventory` manifest entries in the
paper report pack. The implementation reads a local artifact-inventory
descriptor as metadata, renders a separate Markdown section, reports missing
optional artifact-inventory descriptors as not supplied, and rejects
secret-like fields, source-content or excerpt fields, and remote URLs.

The report pack still does not read artifact/source files referenced by the
descriptor, verify outputs, or verify local environments. It renders
reviewer-supplied generated artifact labels, artifact type labels, local paths,
generation-source labels, intended report-use notes, and limitation notes as
descriptive context without ranking artifacts, producing advice, or implying
production readiness.

After Stage 25, the next safe report-input kind is an appendix index. The
clarified Stage 26 boundary allows a local appendix-index descriptor to record
reviewer-supplied appendix entry labels, report section labels, local artifact
paths, appendix purpose notes, and limitation notes.

The boundary stays descriptive. Stage 26 should make appendix-index metadata
visible in the report pack without reading artifact contents, verifying
outputs, approving distribution, ranking appendix entries, producing advice, or
implying production readiness.

## Stage 26 local appendix-index input

Stage 26 added support for `local_appendix_index` manifest entries in the
paper report pack. The implementation reads a local appendix-index descriptor
as metadata, renders a separate Markdown section, reports missing optional
appendix-index descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read artifact/source files referenced by the
descriptor, verify outputs, verify local environments, or approve
distribution. It renders reviewer-supplied appendix entry labels, report
section labels, local artifact paths, appendix purpose notes, and limitation
notes as descriptive context without ranking appendix entries, producing
advice, or implying production readiness.

After Stage 26, the next safe report-input kind is a limitation register. The
clarified Stage 27 boundary allows a local limitation-register descriptor to
record reviewer-supplied limitation labels, affected report section labels,
local evidence or artifact paths, scope notes, mitigation notes, and limitation
notes.

The boundary stays descriptive. Stage 27 should make limitation-register
metadata visible in the report pack without reading referenced contents,
verifying outputs, scoring limitations, producing advice, or implying
production readiness.

## Stage 27 local limitation-register input

Stage 27 added support for `local_limitation_register` manifest entries in the
paper report pack. The implementation reads a local limitation-register
descriptor as metadata, renders a separate Markdown section, reports missing
optional limitation-register descriptors as not supplied, and rejects
secret-like fields, source-content or excerpt fields, and remote URLs.

The report pack still does not read artifact/evidence/source files referenced
by the descriptor, verify outputs, verify local environments, or approve
distribution. It renders reviewer-supplied limitation labels, affected report
section labels, local evidence or artifact paths, scope notes, mitigation
notes, and limitation notes as descriptive context without scoring limitations,
producing advice, or implying production readiness.

After Stage 27, the next safe report-input kind is an open-questions register.
The clarified Stage 28 boundary allows a local open-questions descriptor to
record reviewer-supplied open question labels, affected report section labels,
local reference paths, owner labels, status labels, and limitation notes.

The boundary stays descriptive. Stage 28 should make open-question metadata
visible in the report pack without reading referenced contents, verifying
outputs, scoring questions, approving decisions, producing advice, or implying
production readiness.

## Stage 28 local open-questions input

Stage 28 added support for `local_open_questions` manifest entries in the
paper report pack. The implementation reads a local open-questions descriptor
as metadata, renders a separate Markdown section, reports missing optional
open-questions descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read artifact/evidence/source files referenced
by the descriptor, verify outputs, verify local environments, or approve
decisions. It renders reviewer-supplied open question labels, affected report
section labels, local reference paths, owner labels, status labels, and
limitation notes as descriptive context without scoring questions, producing
advice, or implying production readiness.

After Stage 28, the next safe report-input kind is a decision log. The
clarified Stage 29 boundary allows a local decision-log descriptor to record
reviewer-supplied decision labels, decision context labels, local reference
paths, owner labels, status labels, rationale notes, and limitation notes.

The boundary stays descriptive. Stage 29 should make decision-log metadata
visible in the report pack without reading referenced contents, approving
decisions, scoring decisions, producing advice, or implying production
readiness.

## Compact governance audit after Stage 29 readiness

The mandatory audit after Stage 28 readiness, Stage 28 implementation, and
Stage 29 readiness passed. Local `main` was synced with `origin/main`, the
latest `main` `Validate` run passed, branch protection still required strict
`Validate`, there were no open pull requests, and the handoff continued to
point at Stage 29 implementation only.

## Stage 29 local decision-log input

Stage 29 added support for `local_decision_log` manifest entries in the paper
report pack. The implementation reads a local decision-log descriptor as
metadata, renders a separate Markdown section, reports missing optional
decision-log descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read artifact/evidence/source files referenced
by the descriptor, verify outputs, verify local environments, or approve
decisions. It renders reviewer-supplied decision labels, decision context
labels, local reference paths, owner labels, status labels, rationale notes,
and limitation notes as descriptive context without scoring decisions,
producing advice, or implying production readiness.

After Stage 29, the next safe report-input kind is a follow-up register. The
clarified Stage 30 boundary allows a local follow-up descriptor to record
reviewer-supplied follow-up labels, related report section labels, local
reference paths, owner labels, status labels, tracking notes, and limitation
notes.

The boundary stays descriptive. Stage 30 should make follow-up metadata visible
in the report pack without reading referenced contents, executing follow-ups,
scoring follow-ups, producing advice, or implying production readiness.

## Stage 30 local follow-up register input

Stage 30 added support for `local_follow_up_register` manifest entries in the
paper report pack. The implementation reads a local follow-up-register
descriptor as metadata, renders a separate Markdown section, reports missing
optional follow-up descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read artifact/evidence/source files referenced
by the descriptor, verify outputs, verify local environments, execute
follow-ups, or approve decisions. It renders reviewer-supplied follow-up
labels, related report section labels, local reference paths, owner labels,
status labels, tracking notes, and limitation notes as descriptive context
without scoring follow-ups, producing advice, or implying production
readiness.

## Compact governance audit after Stage 30 implementation

The mandatory audit after Stage 29 implementation, Stage 30 readiness, and
Stage 30 implementation passed. Local `main` was synced with `origin/main`, the
latest `main` `Validate` run passed, branch protection still required strict
`Validate`, there were no open pull requests, and the handoff reset to the
next report-input-kind readiness clarification.

After Stage 30, the next safe report-input kind is version notes. The
clarified Stage 31 boundary allows a local version-notes descriptor to record
reviewer-supplied report version labels, local artifact paths,
change-summary labels, owner labels, status labels, and limitation notes.

The boundary stays descriptive. Stage 31 should make version-note metadata
visible in the report pack without reading artifact contents, approving
distribution, scoring versions, producing advice, or implying production
readiness.

## Stage 31 local version-notes input

Stage 31 added support for `local_version_notes` manifest entries in the paper
report pack. The implementation reads a local version-notes descriptor as
metadata, renders a separate Markdown section, reports missing optional
version-notes descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read artifact/evidence/source files referenced
by the descriptor, verify outputs, verify local environments, approve
distribution, or approve decisions. It renders reviewer-supplied report
version labels, local artifact paths, change-summary labels, owner labels,
status labels, and limitation notes as descriptive context without scoring
versions, producing advice, or implying production readiness.

After Stage 31, the next safe report-input kind is a distribution checklist.
The clarified Stage 32 boundary allows a local distribution-checklist
descriptor to record reviewer-supplied distribution item labels, related
artifact paths, readiness status labels, owner labels, review notes, and
limitation notes.

The boundary stays descriptive. Stage 32 should make distribution-checklist
metadata visible in the report pack without reading artifact contents,
approving distribution, verifying rights, scoring checklist items, producing
advice, or implying production readiness.

## Compact governance audit after Stage 32 readiness

The mandatory audit after Stage 31 readiness, Stage 31 implementation, and
Stage 32 readiness passed. Local `main` was synced with `origin/main`, the
latest `main` `Validate` run passed, branch protection still required strict
`Validate`, there were no open pull requests, and the handoff continued to
point at Stage 32 implementation only.

## Stage 32 local distribution-checklist input

Stage 32 added support for `local_distribution_checklist` manifest entries in
the paper report pack. The implementation reads a local distribution-checklist
descriptor as metadata, renders a separate Markdown section, reports missing
optional descriptors as not supplied, and rejects secret-like fields,
source-content or excerpt fields, and remote URLs.

The report pack still does not read artifact/evidence/source files referenced
by the descriptor, verify outputs, verify local environments, approve
distribution, verify rights, or approve decisions. It renders reviewer-supplied
distribution item labels, related artifact paths, readiness status labels,
owner labels, review notes, and limitation notes as descriptive context without
scoring checklist items, producing advice, or implying production readiness.

## Stage 33 readiness clarification

After Stage 32, the next safe report-input kind is handoff notes. The clarified
Stage 33 boundary allows a local handoff-notes descriptor to record
reviewer-supplied handoff labels, related artifact paths, recipient or owner
labels, status labels, handoff notes, and limitation notes.

The boundary stays descriptive. Stage 33 should make handoff-note metadata
visible in the report pack without reading artifact contents, approving
distribution, verifying rights, scoring handoffs, producing advice, or implying
production readiness.

## Stage 33 local handoff-notes input

Stage 33 added support for `local_handoff_notes` manifest entries in the paper
report pack. The implementation reads a local handoff-notes descriptor as
metadata, renders a separate Markdown section, reports missing optional
descriptors as not supplied, and rejects secret-like fields, source-content or
excerpt fields, and remote URLs.

The report pack still does not read artifact/evidence/source files referenced
by the descriptor, verify outputs, verify local environments, approve
distribution, verify rights, or approve decisions. It renders reviewer-supplied
handoff labels, related artifact paths, recipient labels, status labels,
handoff notes, and limitation notes as descriptive context without scoring
handoffs, producing advice, or implying production readiness.

## Compact governance audit after Stage 33 implementation

The mandatory audit after Stage 32 implementation, Stage 33 readiness, and
Stage 33 implementation passed. Local `main` was synced with `origin/main`, the
latest `main` `Validate` run passed, branch protection still required strict
`Validate`, there were no open pull requests, and the handoff reset to the
next report-input-kind readiness clarification.

## Stage 34 readiness clarification

After Stage 33, the next safe report-input kind is archive notes. The clarified
Stage 34 boundary allows a local archive-notes descriptor to record
reviewer-supplied archive labels, related artifact paths, archive status
labels, owner labels, archive notes, and limitation notes.

The boundary stays descriptive. Stage 34 should make archive-note metadata
visible in the report pack without reading artifact contents, moving or
deleting files, deciding retention policy, scoring archive readiness, producing
advice, or implying production readiness.

## Stage 34 local archive-notes input

Stage 34 added support for `local_archive_notes` manifest entries in the paper
report pack. The implementation reads a local archive-notes descriptor as
metadata, renders a separate Markdown section, reports missing optional
descriptors as not supplied, and rejects secret-like fields, source-content or
excerpt fields, and remote URLs.

The report pack still does not read artifact/evidence/source files referenced
by the descriptor, verify outputs, verify local environments, move or delete
files, decide retention policy, approve distribution, verify rights, or approve
decisions. It renders reviewer-supplied archive labels, related artifact paths,
archive status labels, owner labels, archive notes, and limitation notes as
descriptive context without scoring archive readiness, producing advice, or
implying production readiness.

## Stage 35 readiness clarification

After Stage 34, the next safe report-input kind is delivery notes. The
clarified Stage 35 boundary allows a local delivery-notes descriptor to record
reviewer-supplied delivery labels, related artifact paths, recipient labels,
delivery status labels, delivery notes, and limitation notes.

The boundary stays descriptive. Stage 35 should make delivery-note metadata
visible in the report pack without transferring files, approving distribution,
verifying rights, reading artifact contents, scoring delivery readiness,
producing advice, or implying production readiness.

## Compact governance audit after Stage 35 readiness

The mandatory audit after Stage 34 readiness, Stage 34 implementation, and
Stage 35 readiness passed. Local `main` was synced with `origin/main`, the
latest `main` `Validate` run passed, branch protection still required strict
`Validate`, force pushes and branch deletion were disabled, and there were no
open pull requests.

The handoff and stage plan agree on the next checkpoint. No risk drift,
compliance drift, token/context drift, or user-judgment stop gate was found, so
the checkpoint counter resets and the next checkpoint is Stage 35
implementation only.

## Stage 35-36 arbitrage roadmap reset and candidate schema

Stage 35 redirects the active roadmap away from adding more local report-input
metadata and toward narrow same-market YES/NO complement parity research.
Stages 11 through 34 remain useful as maintenance/report-pack infrastructure,
but the next product work is no longer another metadata kind.

Stage 36 adds the first implementation, intentionally offline and
deterministic:
`ComplementArbInput`, `ComplementArbCandidate`, `ComplementArbDecision`,
`compute_kalshi_complement_candidate`, and
`compute_canonical_yes_side_cross_candidate`. The model uses `Decimal`, keeps
fees, slippage, and failed-leg reserves as explicit inputs, treats missing fee
models as audit-only, and always requires manual review. It does not fetch live
data, authenticate, place orders, optimize strategy, or describe candidates as
risk-free.

## Stage 37-38 fee scaffold and offline scanner

Stage 37 makes fee assumptions explicit before scanner output can be labeled
as a paper candidate. The fee scaffold supports supplied, missing, and unknown
statuses with `Decimal` fee values and source notes. Missing or unknown fees
block `paper_candidate` and keep the record audit-only.

Stage 38 adds a thin offline scanner over local fixture JSON and existing
snapshot JSONL. It reuses the complement candidate model and fee scaffold,
preserves Decimal strings in deterministic JSONL output, and writes a Markdown
summary with candidate, audit, reject, fee-status, rejection-reason, and
data-quality counts. Scanner records are audit/paper research metadata only:
there is no live lookup, credential input, network call, order intent,
strategy optimization, investment advice, or profitability claim.

## Stage 39 live event schema and mocked recorder

Stage 39 adds the live-event envelope and recorder behavior without adding a
real network connection. `LiveMarketDataEvent` records venue, channel, market,
event type, sequence, timestamps, raw payload, source type, and tags. Payloads
reuse a shared secret-key rejection helper before JSONL persistence.

The mocked recorder is intentionally local and finite. It reads fixture events,
writes deterministic JSONL, and gives Stage 40 and Stage 41 a recorder contract
to target. It does not open sockets, prompt for credentials, subscribe to live
venues, authenticate, place orders, or describe output as advice.

## Stage 40 guarded Kalshi read-only recorder

Stage 40 adds the first venue-specific live-readonly recorder path, but keeps
the safety controls in front of the network call. The Kalshi recorder requires
explicit `--live-readonly-opt-in`, accepts only the Kalshi Demo REST base URL
and demo environment, and is tested with `httpx.MockTransport`.

One successful mocked capture writes both a raw `LiveMarketDataEvent` JSONL
record and a normalized `MarketDataSnapshot` JSONL record. The code does not
accept credentials, prompt for credentials, import order placement, touch user
channels, use production endpoints, or run a real live connection in
validation.

## Stage 41 guarded Polymarket market-channel recorder

Stage 41 adds the matching Polymarket US market-channel recorder path. It
requires explicit `--live-readonly-opt-in`, accepts only the guarded
Polymarket US public market-data boundary, and is tested with
`httpx.MockTransport`.

One successful mocked capture writes both a raw `LiveMarketDataEvent` JSONL
record and a normalized `MarketDataSnapshot` JSONL record. The code does not
accept credentials, prompt for credentials, add user channels, wallets,
signing, order placement imports, executable advice, strategy optimization,
production-readiness claims, or profitability claims. The due compact
governance audit for Stages 39-41 was folded into the Stage 41 delivery
branch and found no stop gate.

## Stage 42 order book rebuild and replay consistency

Stage 42 turns recorded read-only events into replayable normalized book
records. The rebuild path consumes existing live-event JSONL, normalizes
Kalshi Demo and Polymarket US full-book payloads, writes snapshot JSONL, and
emits deterministic SHA-256 book-state hashes for audit comparison.

The consistency layer stays deliberately narrow: it reports sequence gaps,
stale received-vs-observed lag, out-of-order observations, and one-sided books.
The output is audit/replay research metadata only. It does not connect to live
venues, authenticate, place orders, optimize strategy, or present replayed
state as advice or profitability evidence.

## Stage 43 taker fill, slippage, and failed-leg simulator

Stage 43 adds the first explicit two-leg taker-fill stress model for complement
research. It consumes local scenario fixtures, computes a complement candidate,
and simulates FOK/IOC-like fill policy assumptions, available depth after
latency, leg-level slippage, latency shock, and failed-leg reserve.

The simulator emits deterministic JSONL and Markdown audit records. It records
completed pair size, partial-fill exposure, failed-leg reserve totals, and
simulated net edge under the supplied assumptions. It does not create order
intents, connect to a venue, authenticate, optimize strategy, recommend trades,
or claim the simulated results are executable or profitable.

## Stage 44 paper complement proposal engine

Stage 44 converts offline scanner candidates and taker-fill simulation records
into paper-only complement proposal records. Each proposal preserves locked
SHA-256 hashes of the raw candidate and simulation inputs, carries YES/NO paper
legs derived from simulated fill prices and completed pair size, and emits
deterministic JSONL plus Markdown summaries.

The risk preview is deliberately conservative: manual approval is always
required and Stage 44 does not mark any proposal as approved for paper use.
The engine does not create executable order intents, connect to venues,
authenticate, submit orders, optimize strategy, offer investment advice, or
claim profitability.

## Stage 45 paper ledger state machine

Stage 45 adds a deterministic event-sourced paper ledger. It replays local
paper proposal, fill, and settlement records from zero, preserves candidate
and simulation source hashes, and computes paper positions, average prices,
fees, realized gross PnL, realized net PnL, and reconciliation mismatch states.

The ledger remains an accounting and reconciliation research surface only.
It rejects malformed records, records hash and proposal mismatches explicitly,
and emits paper-only JSONL plus Markdown summaries. It does not create order
intents, connect to venues, authenticate, submit orders, optimize strategy,
offer investment advice, or claim profitability.

## Stage 46 risk engine v2

Stage 46 adds a paper-only complement risk-decision layer. It evaluates local
risk-check fixtures for stale data, sequence/data gaps, missing or unknown fee
status, insufficient net edge, exposure limit breaches, open-order limit
breaches, daily-loss limit breaches, reconciliation mismatches, and active
kill switch.

The engine never approves execution. If no blocker is present, it returns a
manual-review-required paper risk record. If any blocker is present, it returns
a reject record with deterministic reasons. It does not create order intents,
connect to venues, authenticate, submit orders, optimize strategy, offer
investment advice, or claim profitability.

## Stage 47 manual approval workflow

Stage 47 adds a local manual-review workflow on top of the Stage 46
manual-review-required risk state. It creates deterministic pending approval
files, verifies approval records against proposal and candidate hashes, checks
expiration, and rejects already-used approvals so approvals cannot be reused.

The workflow emits paper manual-review records only. A verified approval is
single-use paper metadata, not an executable order, adapter call, live venue
submission, strategy recommendation, or profitability claim. The compact
governance audit for Stages 45-47 was folded into this delivery branch and
found no stop gate.

## Stage 48 monitoring and daily validation report

Stage 48 adds an offline daily validation report over local monitoring records.
It summarizes recorder uptime and downtime, maximum data lag, gap counts,
candidate counts, rejection reasons, paper/demo outcome counts, fees, slippage
incidents, failed-leg incidents, reconciliation mismatches, and kill-switch
events.

The report is intentionally local and observational. It does not open venue
connections, authenticate, place orders, optimize strategy, recommend action,
claim production readiness, or make profitability claims. With Stage 48
complete, the next roadmap item is Stage 49 Kalshi Demo authenticated connector
work, which required explicit review/authorization before implementation.

## Stage 49 Kalshi Demo authenticated connector

Stage 49 adds a guarded Kalshi Demo connector boundary for request previews and
Demo submit-path coverage mocked in tests. The connector consumes a paper proposal, clear
manual-review-required risk decision, non-expired single-use manual approval,
and reconciled paper ledger state before it can build tiny FOK/IOC Demo request
previews.

Dry-run preview is the default and works without credentials. The submit path
requires explicit opt-in, an injected HTTP client in this stage, environment-
loaded auth headers, Demo-only base URL validation, and append-only local audit
records with auth-like fields redacted. This stage does not place real orders
during validation, add production endpoints, implement wallets, optimize
strategy, offer trading advice, or make profitability claims.

## Stage 50 demo reconciliation

Stage 50 adds local Kalshi Demo reconciliation replay for connector outcomes.
It reads Stage 49 connector audit records plus local/mock Demo events, rebuilds
accepted, rejected, partial fill, full fill, cancel, error, timeout, and
backfill-style state, and appends reconciliation records that link back to the
connector audit hash.

Duplicate events are idempotent when their contents match. Missing events,
conflicting duplicate event ids, source-hash mismatches, fill-before-acceptance
cases, and terminal-state conflicts produce reconciliation mismatches. Any
mismatch marks the state as not eligible for later Demo submission. This stage
uses local fixtures and mocked records only; it does not connect to venues,
place orders, store credentials, optimize strategy, offer trading advice, or
make profitability claims. The compact governance audit for Stages 48-50 was
folded into this delivery branch and found no stop gate.

## Stage 51 long-term paper/demo validation framework

Stage 51 adds an offline rolling validation framework over existing local
paper/demo research artifacts. It consumes JSONL records from scanner,
simulation, paper proposal, paper ledger, risk decision, manual approval, Demo
connector audit, Demo reconciliation, and daily validation stages, then emits
deterministic JSONL, JSON, and Markdown summaries for 7/30/90-day windows.

The report tracks candidate counts, paper-candidate counts, Demo order counts,
fill rates, partial fill rates, failed-leg incidents, gross edge, net edge
after cost, paper/demo PnL, max drawdown, reconciliation mismatches, data gaps,
kill-switch events, and false-positive-style rejection outcomes where records
provide those fields. It deliberately marks validation as not completed and
lists unmet private-live prerequisites, including missing real 30-90 day
live-readonly data, missing 30+ day paper trading history, unresolved mismatch
status when present, unvalidated fee/slippage assumptions, and missing
legal/platform review. It does not connect to venues, place orders, store
credentials, optimize strategy, offer trading advice, claim production
readiness, or make profitability claims.

## Stage 52 private live gate design

Stage 52 adds the private live execution gate document and a disabled public
placeholder. The placeholder returns a `disabled` gate decision, marks
production trading and executable order intent false, and lists the private
evidence still missing before any future private work could be considered.

The public repo still has no production endpoint, production order code,
credential loader, wallet, broker integration, live user-order channel, or
order payload. The Stage 35-52 complement-arbitrage roadmap is complete, and
the next action is human review of the private gate design plus private
evidence collection outside this repository. This stage does not connect to
venues, place orders, store credentials, optimize strategy, offer trading
advice, claim production readiness, or make profitability claims.

## Public repository presentation refresh

After Stage 52, the README was rewritten as a public landing page for technical
reviewers and future maintainers. It now presents the same-market YES/NO
complement-parity workflow from fixture/read-only market data through
normalization, scanning, simulation, paper ledger, risk, manual approval, Demo
dry-run/reconciliation, rolling validation, and the disabled private-live gate.

The public positioning remains intentionally conservative: production/live
trading is disabled, private-live prerequisites are still unmet, and the repo
does not claim positive expectancy, production readiness, investment advice, or
profitability.

The visual documentation pass keeps that same boundary and adds Mermaid
diagrams for the workflow, architecture layers, safety gate, and public/private
split. No SVGs, generated images, hosted assets, behavior changes, or diagram
service dependencies were added.

The release and portfolio packaging pass adds reviewer-facing release notes,
portfolio framing, and resume bullets for the Stage 52 public repo state. It
does not change source behavior or relax the disabled-live boundary.

## Conformance audits and Demo boundary fix

The roadmap conformance audit and end-to-end conformance audit verify the
Stage 35-52 implementation against the public roadmap, README, risk policy,
private-live gate, handoff, repo map, changelog, engineering log, scripts,
tests, and source layout. The audits found no high-severity drift from the
disabled-live research boundary.

The PR #109 follow-up tightened the Stage 49/50 Demo boundary: dry-run previews
remain available without credentials or reconciliation state, while Demo submit
opt-in requires a provided clean Demo reconciliation state and remains covered
by mocked HTTP tests.

## Post-PR #109 visual documentation refresh

This docs-only pass updates the README and visual overview Mermaid diagrams to
show the current Kalshi Demo dry-run/guarded Demo submit boundary, Demo
reconciliation, rolling validation, and disabled private-live gate. The README
now includes a compact public/private boundary diagram in addition to the
workflow, architecture, and safety diagrams.

The refresh adds no SVGs, hosted assets, generated images, source behavior
changes, production endpoints, credentials, wallets, broker integration, live
order placement, strategy optimization, investment advice, production-readiness
claims, or profitability claims.

## PR #110 hidden Unicode follow-up

GitHub's PR #110 files page included hidden/bidirectional Unicode warning
templates for each touched Markdown file: `CHANGELOG.md`, `README.md`,
`docs/current_handoff.md`, `docs/engineering_log.md`, `docs/repo_map.md`, and
`docs/visual_overview.md`. A local scan of those files and the PR #110 diff
found no bidi controls, zero-width characters, non-breaking spaces, or unusual
invisible whitespace, so no content replacement was needed. The Mermaid fences
remain unchanged.

## Interview narrative

A concise way to explain the current project:

> I built the project from the safety boundary inward. First I defined the
> non-goals and risk constraints, then I modeled a venue-agnostic orderbook and
> normalized Kalshi-style YES/NO books into a canonical bid/ask representation.
> I then added a long-running project control layer and a guarded read-only Demo
> market-data client with mocked tests, keeping execution and strategy work out
> of scope. Next, I added Decimal-safe snapshot JSONL and deterministic replay
> metrics so later quote engines and reports can run from reproducible offline
> data instead of live API state. The first quote layer then used those replayed
> books to produce dry-run fair values and inventory-aware quote candidates
> without creating any executable order path. I then added a fake-adapter Stage
> 5 execution boundary that proves execution attempts are risk-gated, logged,
> and blocked when unsafe before any real adapter is introduced.

## Round 8G lifecycle verification and gate v2

The selected Demo market was independently verified through the read-only REST
market and event endpoints after the recorder stopped receiving valid ongoing
evidence. REST reported a finalized sports match with a populated result,
expected expiration and occurrence before the planned seven-day end, and an
early-close condition. The run's JSONL integrity remained clean, but the market
lifecycle made the campaign evidence invalid; the campaign and watcher were
terminated with their root-specific supervisors using bounded TERM handling.

The public lifecycle gate now treats `close_time` as insufficient when earlier
expected-expiration, occurrence, or early-close metadata exists. It fetches
event metadata for long-horizon discovery, rejects unsafe early-close and
sports/match markets by default, records the conservative deadline in the
manifest, and separates data-integrity status from market-lifecycle evidence
validity. The public live gate remains disabled.
