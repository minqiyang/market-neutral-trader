# V2 Lifecycle Gate

The canary and seven-day read-only profiles use a conservative lifecycle
deadline rather than `close_time` alone. The reviewed field trust matrix is:

| Field | Contract meaning | Selection use |
| --- | --- | --- |
| `close_time` | Scheduled or actual trading stop; may move earlier when `can_close_early=true`. | Required prospective deadline. |
| `expected_expiration_time` | Forecast time when the outcome is expected to be known. | Required prospective deadline. |
| `can_close_early` | Signals that the trading stop can move earlier. | Fail closed unless reviewed metadata provides an explicit early-close deadline beyond the required end. |
| `occurrence_datetime` | Officially the recorded time when the event occurred; Demo has also returned a future value equal to close and expected expiration. | Dual-interpretation bound; never sole evidence and never relaxes another deadline. |
| `latest_expiration_time` | Latest possible expiration. | Telemetry only; cannot override an earlier bound. |

Sources were reviewed at `2026-07-12T20:59:11Z`: Kalshi's
[market lifecycle](https://docs.kalshi.com/getting_started/market_lifecycle),
[market list](https://docs.kalshi.com/api-reference/market/get-markets),
[single market](https://docs.kalshi.com/api-reference/market/get-market),
[event list](https://docs.kalshi.com/api-reference/events/get-events),
[single event](https://docs.kalshi.com/api-reference/events/get-event),
[AsyncAPI](https://docs.kalshi.com/asyncapi.yaml), and
[April 16, 2026 changelog entry](https://docs.kalshi.com/changelog).

```text
campaign_required_end = selected_at_utc + duration_seconds + safety_buffer_seconds
lifecycle_deadline = min(close_time, expected_expiration_time,
                         explicit_early_close_deadline,
                         future_occurrence_safety_bound)
```

Profile v4 resolves the observed occurrence contradiction without guessing its
meaning. Missing occurrence may pass only when complete event metadata,
`can_close_early=false`, and independently safe close and expected-expiration
deadlines exist. An occurrence at or before selection plus the named 60-second
clock-skew tolerance is treated as already occurred and rejected. A later value
is classified `AMBIGUOUS_FUTURE_OCCURRENCE`, included only as an additional
minimum bound, and must exceed the required end while close and expected
expiration independently pass. Malformed values reject. Equality with close or
expected expiration is anomaly telemetry, not a global stop. This policy is
safe whether the field is retrospective metadata or a prospective Demo alias.

`latest_expiration_time` remains telemetry only. Occurrence cannot substitute
for missing close, expected-expiration, or explicit early-close guarantees.
The long-horizon gate also rejects missing event metadata and sports/match
markets. The manifest preserves raw occurrence, semantic classification,
inclusion and equality flags, component deadlines, dual-interpretation result,
normalized status, required end, and structured rejection reason.

Selection is explicit across three profiles. Smoke uses a 900-second buffer.
The 1,800-second canary uses a 3,600-second buffer, requires complete event
category/title metadata from the core event endpoint and rejects sports and
match-like events. Canary and seven-day profiles fail closed on early-close
risk unless an explicit safe deadline exists; missing occurrence still cannot
pass with early-close risk. Seven-day selection uses at least an 86,400-second
buffer. Smoke remains intentionally separate. None of these profiles implies
seven-day evidence before the corresponding bounded run completes.

Discovery fetches at most 100 market pages before event hydration, deduplicates
markets and event tickers, and excludes multivariate markets because the
documented core event list excludes multivariate events. It then exhausts the
documented `status=open` event cursor with at most 100 pages of 200 events. Only
events referenced by the market set are cached. `coverage_complete=true`
requires both final cursors to be empty. Reaching either page cap with a cursor
remaining returns a typed incomplete-coverage blocker and cannot authorize a
candidate. Missing event members may use at most 1,000 candidate-local exact-
event requests; an exact-event 404 or schema failure rejects only that
candidate, while the fallback cap, a global list failure, or an exhausted rate
limit fails the scan. Rate limits and transient server/transport failures
receive at most three attempts. Complete results include pagination provenance,
a versioned profile hash, primary and multi-label rejection totals,
distinct/duplicate counts, and up to 100 hashed near-miss summaries without raw
market payloads.

Runtime selection and complete eligibility auditing are separate bounds.
Authenticated smoke/campaign launch paths still exhaust the market cursor and
evaluate every market's lifecycle metadata, but stop orderbook probing once the
requested eligible market count is reached. They issue at most 100 logical
orderbook probes, each under the existing three-attempt request policy. If the
cap is reached before an eligible market is found, selection fails closed as
`DEMO_MARKET_DISCOVERY_ORDERBOOK_PROBE_LIMIT`; it never reports
`DEMO_NO_ELIGIBLE_MARKET` from a partial orderbook scan. Diagnostics distinguish
`coverage_complete` for cursor/lifecycle coverage from
`orderbook_candidate_scan_complete` and `eligible_count_complete`; a successful
early selection reports the observed eligible count as a lower bound. Direct
discovery audits retain exhaustive orderbook evaluation when no runtime limit
is supplied.

## Activity-aware bounded measurement selection

The optional activity-aware profile uses the official market field
`volume_24h_fp`, documented as 24-hour market volume in contracts. A candidate
must carry a finite positive fixed-point string from that field. A non-empty
book, quoted size, open interest, deprecated liquidity, or metadata update time
is not treated as recent trading activity.

Activity-aware candidates are ordered deterministically by descending 24-hour
volume, then the existing conservative lifecycle order, current-quote presence,
and ticker as a final stable tie-break. Discovery can return a bounded ordered
candidate set so the bounded controller can pin each pre-authorized probe
without silently substituting a market.

A shared request-budget object can cover discovery and every pinned
revalidation. Request limits, consumed values, and attempt controls require
exact integers (Booleans and fractional values reject), and control evidence is
persisted with private discovery/revalidation records. The bounded Phase 0F
profile sets one request attempt, so rate-limit, server, timeout, and connection
failures stop rather than retry. Immediately before a pinned probe or
measurement, the original exact market and event identity, positive activity
signal, lifecycle horizon, and orderbook are revalidated. The selection horizon
must cover the complete requested runtime; pinned calls default to at least the
1,800-second canary profile and cannot fall back to smoke selection. Pinned
runtime calls never perform substituting discovery and use zero WebSocket
reconnects. These controls remain Demo-only and read-only.

The dedicated `scripts/phase0f_activity_measurement.py` controller composes
these primitives into one fail-closed operation. Its explicit
`--demo-readonly-opt-in` authorizes only the fixed bounded sequence already
approved by the owner; it cannot extend, retry, or add a runtime. It also
requires a new absolute non-symlink owner-private output root outside Git and a
credential-load preflight before discovery. It performs one
activity-aware discovery cycle under a shared 1,000-request ceiling and
retains at most two ranked candidates. Only a typed candidate-local
revalidation rejection or a controlled, artifact-valid probe with explicitly
zero admitted deltas may advance to candidate two; authorization, transport,
budget, integrity, or other global failures stop immediately. The first
qualifying probe alone advances to one 1,800-second measurement, and the
controller never starts another measurement. The post-run assessor
requires controlled bounded exit, required duration, connection and channel
ACK, valid lifecycle, snapshot plus delta admission, no known sequence gap,
valid snapshot-first native rebuild, independent artifact validation, closed
segments, and disabled production/order state. Sequence `UNKNOWN` is safe only
for measurement retention; replay semantics require explicit sequence and
rebuild `PASS`, and full replay qualification additionally remains blocked
until private backup/catalog gates pass. Terminal output is categorical and
Boolean-only; detailed identities, counters, payloads, manifests, and paths stay
under the private output root.

Validation reports separate `DATA_INTEGRITY_PASS` from
`CAMPAIGN_EVIDENCE_INVALID_MARKET_LIFECYCLE`; clean JSONL/hash/artifact
integrity cannot turn a closed or resolved market into valid long-horizon
evidence. The public live gate remains disabled and no order-write path is
introduced.
