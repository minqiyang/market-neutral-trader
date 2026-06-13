# Engineering Log

## Why this project exists

This project exists to demonstrate professional trading-system engineering in a
portfolio-friendly way. The emphasis is not on claims of profit. The emphasis is
on correctness, staged delivery, risk boundaries, deterministic tests, and the
ability to explain how a trading research platform is built from safe
foundations.

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
