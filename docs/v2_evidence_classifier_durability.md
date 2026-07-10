# V2 Evidence Classifier And Durability

## Scope

D2D adds fixture-only evidence classification, append-chain durability,
recovery, rotation, and a synthetic performance gate. It consumes no private
market data and opens no market connection. It does not deploy a recorder,
qualify a real campaign, delete retained data, enable live execution, or emit
`REPLAY_QUALIFIED` from D2A-D2D fixture success.

## Orthogonal classifier

`EvidenceDimensions` records each claim independently:

- artifact integrity;
- transport connectivity;
- transport keepalive;
- subscription status;
- sequence integrity;
- rebuild integrity;
- market lifecycle validity;
- duration evidence;
- process liveness;
- supervisor liveness;
- backup integrity;
- replay qualification.

Each dimension is `PASS`, `FAIL`, or `UNKNOWN`. Any failed dimension produces
overall `FAIL`; any unknown dimension prevents overall pass and produces
`INCOMPLETE`; overall `PASS` requires every dimension to pass. The serialized
classification always includes every dimension, so an overall label cannot
hide unknown or failed evidence.

A WebSocket snapshot/delta transport pass does not promote sequence, rebuild,
duration, backup, or replay evidence.

## Timing and threshold provenance

`build_evidence_timing` derives actual elapsed time from `started_at_utc` and a
terminal or checkpoint timestamp. Configured duration is never substituted for
elapsed evidence. Connected elapsed time is actual elapsed time minus explicit
disconnect duration, using exact `Decimal` seconds.

The record includes configured, actual, and connected duration; first snapshot,
last event, checkpoint, and end timestamps; terminal reason; stop-requested
state; disconnect time; current and window-maximum values for transport
keepalive, lifecycle age, and orderbook quiet interval; and threshold policy
version, source commit, and effective timestamp.

A completed short run fails duration evidence. An in-progress short checkpoint
remains unknown. A run passes duration only when timestamp-derived actual
elapsed time reaches the configured duration. Threshold policy must have a
hexadecimal source commit and be effective no later than the evidence window
start. A terminal reason is valid only with an end timestamp, and a recorded
first snapshot cannot be later than the last recorded event.

## Exact append chain

Every segment has a deterministic genesis hash. For each exact serialized UTF-8
JSONL record, D2D computes:

```text
H_i = SHA256(H_(i-1) || uint64_be(record_length) || record_bytes)
```

The newline is part of `record_bytes`. Appends update only the current hash,
offset, and row index. No append callback reads or hashes the existing file.

## Atomic checkpoints

Checkpoints contain schema version, segment ID, segment creation time, last
committed local row index, byte offset, chain hash, UTC checkpoint timestamp,
and monotonic checkpoint timestamp. Before checkpoint replacement, the data
file is flushed and fsynced. The checkpoint is written to a same-directory
temporary file, flushed and fsynced, atomically replaced, and followed by a
directory fsync.

Segment creation persists a genesis checkpoint before the first append, so a
crash before the periodic checkpoint interval still has a recovery boundary.
Open-segment status reports only the last persisted checkpoint. It does not
claim uncheckpointed tail bytes or a closed-file hash. Open status, closed
summary, and fresh-segment start metadata use distinct versioned schemas.

## Segment close, rotation, and backup metadata

Closing a segment writes a final checkpoint and computes the full-file SHA-256
once. The atomic close summary records creation/close metadata, terminal and
rotation reasons, genesis and terminal chain hashes, closed-file hash, backup
verification state, and retention/deletion eligibility.

Default provisional rotation is 64 MiB or one hour, whichever occurs first.
Rotation closes the old segment with a typed byte/time reason and creates the
next segment. Backup state defaults to `NOT_VERIFIED`; deletion eligibility
remains false. A rotation reason is accepted only with the typed `rotation`
terminal reason. D2D performs no retention deletion.

## Crash recovery

Recovery requires an unterminated segment and its last atomic checkpoint. It
trusts the checkpoint boundary, validates each complete JSON record after the
checkpoint, advances the exact append chain, and removes only a partial final
record. A malformed complete record fails recovery without being discarded.

The recovered segment is finalized with terminal reason `crash_recovered` and
one closed-file SHA-256. D2D atomically writes next-segment metadata requiring a
connection reset and fresh snapshot, with inherited book state false. Recovery
never fills missing history or carries admitted book state into the new
segment. Those three recovery safety claims are fixed result fields rather than
caller-overridable values.

## Synthetic performance gate

`run_evidence_benchmark` streams 100,000 synthetic records, checkpoints every
1,000 records, closes and verifies the chain, and exercises partial-tail crash
recovery. The merge gates are:

- completion at or below 600 seconds;
- peak RSS at or below 512 MiB within the declared 1 GiB profile budget;
- checkpoint p95 at or below one second;
- no out-of-memory failure;
- no full-file work in event callbacks;
- valid chain/closed-file evidence and crash recovery.

The aggregate benchmark result derives its pass state from these gates and
requires at least 100,000 events with checkpoints no less frequent than every
1,000 records; callers cannot supply or override a pass label.

The 1,000,000-event benchmark remains pending and is mandatory before any
30-day collection decision.

## Safety boundary

D2D produces software and synthetic-fixture evidence only. It does not prove a
real recorder's duration, transport, lifecycle, backup, sequence, rebuild, or
replay quality. Public live execution remains disabled. Network campaigns,
credentials, production endpoints, account/order channels, retention deletion,
and real-money trading remain outside this delivery and require later external
owner gates.
