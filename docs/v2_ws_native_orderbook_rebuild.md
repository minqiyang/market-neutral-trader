# Kalshi WebSocket Native Orderbook Rebuild

## Scope

D2B consumes `edmn.kalshi.ws.raw.v2` envelopes produced by D2A and rebuilds a
native Kalshi orderbook from admitted `orderbook_snapshot` and
`orderbook_delta` rows. It is an offline, fixture-tested adapter boundary. It
does not connect to a venue, read private campaign data, persist raw streams,
qualify replay evidence, or authorize paper, Demo, production, or real-money
orders.

## State and admission

`KalshiWsBookRebuilder` owns one `NativeBookState` for each
`(market_ticker, connection_id, segment_id)` key. A state records market and
subscription identity, pricing mode, snapshot status, native YES and NO maps,
last D2A row and native sequence metadata, validity, invalidation reason, and
emitted-frame count. Native maps are exact `Decimal` price-to-aggregate-quantity
mappings.

Only D2A rows with `admission_status=ADMITTED` and no `exclusion_reason` can
mutate a book. D2A-excluded duplicate, out-of-order, controlled-gap,
delta-before-snapshot, missing-market, and unrequested-market rows remain
excluded. Their native payload evidence stays in D2A; D2B does not reinterpret
or apply it. State never crosses a market, connection, segment, market-id, or
subscription/SID binding.

Unsupported future schema versions are returned as typed quarantines with the
record preserved. Unversioned legacy rows are also quarantined because their
local sequence and identity fields cannot prove the D2A admission contract.
Legacy local sequence is never promoted to native sequence.

## Pricing modes

D2B never infers the price scale from observed prices.

| Mode | Native YES level | Native NO level | Canonical YES ask |
| --- | --- | --- | --- |
| `LEGACY_SIDE_PRICE` | YES scale | NO scale | `Decimal("1") - native_no_price` |
| `UNIFIED_YES_PRICE` | YES scale | YES-leg scale | `native_no_price` |

An explicit Boolean `use_yes_price` value in D2A subscription metadata selects
the mode. Unknown or contradictory values quarantine and invalidate the
segment. The current reviewed recorder omits `use_yes_price`; for that exact
compatibility case D2B records `RECORDER_DEFAULT_ASSUMPTION` and uses the
recorder's reviewed venue-default behavior, `LEGACY_SIDE_PRICE`. D2B does not
change the live subscription payload.

Canonical asks retain both `native_side="no"` and the exact
`native_reported_price`, so the source representation remains auditable after
conversion.

## Snapshot and delta rules

A valid snapshot reads `yes_dollars_fp` and `no_dollars_fp` levels, validates
every level before mutation, omits exact-zero quantities, and atomically
replaces both native maps. A same-segment resnapshot is labeled explicitly. A
valid snapshot can recover a D2B-invalid state and records
`RECOVERY_AFTER_INVALIDATION`.

A valid delta reads `side`, `price_dollars`, and signed `delta_fp`. Positive
deltas add quantity; negative deltas subtract it; an exact-zero result removes
the level. A delta is rejected before a valid snapshot. A result below zero,
including a negative delta against a missing level, invalidates the segment
without clamping or partially mutating the book. Later deltas remain excluded
until a fresh admitted snapshot recovers the state.

Prices and quantities accept exact JSON-compatible scalars and are converted
directly to finite `Decimal` values. Booleans and binary floats are rejected.
Prices must remain in the binary contract domain `[0, 1]`; snapshot quantities
must be nonnegative; duplicate numeric snapshot prices are rejected rather
than silently aggregated.

## Canonical YES frame

Each accepted snapshot or delta emits a `KalshiWsBookFrame` containing sorted
native levels and a canonical YES-side view:

- YES bids are native YES levels in descending price order.
- YES asks are derived from native NO levels and sorted in ascending price
  order.
- Quantities and source prices remain exact.
- Empty, bid-only, ask-only, two-sided, locked, and crossed books have distinct
  typed states.

Locked and crossed frames are reported, not repaired. A successfully derived
frame is not automatically execution-quality or replay-qualified.

## Semantic hashes

Every emitted frame has a deterministic SHA-256 semantic hash. The frame hash
covers schema and identity fields, local and native sequence metadata, pricing
mode and assumption, sorted native and canonical levels, validity, reset
reason, and frame count. The terminal-state hash covers the corresponding
native state, including last progress metadata and invalidation state.

Hash input uses UTF-8 JSON with sorted keys, compact separators, Unicode
preserved, and non-finite values forbidden. Decimal prices and quantities are
serialized as normalized base-10 strings; no binary float enters state,
canonical conversion, or hash input. These hashes prove deterministic semantic
rebuild output for the same accepted inputs. They are not wire hashes, raw-file
chains, closed-file hashes, or D2D durability evidence.

## Integrity boundary

D2B preserves D2A `sequence_state` in each frame. `SEQUENCE_NOT_OBSERVED`,
`SEQUENCE_PRESENT_SEMANTICS_UNKNOWN`, and `SEQUENCE_OBSERVED_MONOTONIC` remain
exactly those states; rebuild success does not promote them to sequence
continuity evidence. D2B therefore establishes deterministic application rules
for D2A-admitted fixture rows, not `SEQUENCE_INTEGRITY_PASS` or
`REPLAY_QUALIFIED`.

The existing REST/full-book normalizer and Stage 42 fixture replay remain
unchanged. Future scanner or replay integration may consume the narrow D2B
frame API only after separate review. D2C channels, D2D artifact durability,
network campaigns, credential use, order paths, and live execution are outside
this delivery. Public live execution remains disabled, and real-money trading
is a strict no-go.
