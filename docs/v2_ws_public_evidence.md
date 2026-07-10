# Kalshi Public Trade, Lifecycle, And Connection Evidence

## Scope

D2C adds fixture-tested public evidence contracts around the D2A/D2B boundary.
It adds the public `trade` channel to the selected-market subscription payload,
extracts selected-market public trades, represents selected-market REST
lifecycle fallback, and defines typed connection and freshness evidence. It
does not add account fills, user/order channels, credentials, market network
tests, global lifecycle subscriptions, replay qualification, or order paths.

## Public trade evidence

`build_public_trade_stream` consumes `edmn.kalshi.ws.raw.v2` rows. Only native
`type=trade` events whose market ticker is in the explicit selected-market set
enter the public trade stream. Nonselected trades are counted and filtered;
other event types are ignored. A native trade carrying account-only fields such
as `fill_id` or `order_id` is quarantined rather than treated as public market
evidence.

Each accepted record preserves the D2A connection, segment, local row, native
SID/sequence, exchange timestamps, payload hash, trade identifier, and an exact
copy of the native trade message. Prices and quantities are not converted or
rounded. `is_account_fill` is always false. `write_public_trade_evidence`
writes only the accepted selected-market records.

Zero accepted trades is the valid typed state `QUIET_NO_PUBLIC_TRADES`; it is
not an ingestion failure. If any input is quarantined, the stream is instead
`QUARANTINED_INPUT`, even when another public trade was accepted, so malformed
evidence cannot be hidden by a quiet or observed label.

The recorder subscription payload now requests `orderbook_delta` and the
public `trade` channel for the same selected market list. Tests use only finite
fake WebSocket fixtures and never open a market connection.

## REST lifecycle fallback

`record_rest_lifecycle` accepts an already-observed selected-market metadata
fixture. It performs no HTTP request. The record preserves:

- source `REST_FALLBACK`;
- observation and evaluation timestamps;
- exact raw status and normalized status;
- open, closed, settled, paused, unopened, or unknown lifecycle state;
- observation age and the supplied maximum age;
- validity `VALID`, `STALE`, `UNKNOWN_STATUS`, or `MVE_UNSUPPORTED`.

The fallback explicitly sets `proves_websocket_transport=false`. A fresh REST
status can prove only its lifecycle observation. It cannot prove WebSocket/L2
transport, sequence, rebuild, or duration evidence. A nonselected market is
rejected, stale or unknown status is not promoted to valid, and MVE metadata is
excluded as unsupported.

No global `market_lifecycle_v2` subscription is included in D2C.

## Connection evidence

`ConnectionEvidenceEvent` provides typed fixture records for connection open,
connection close, connection error, reconnect, and resubscription. Every record
requires an observation timestamp, current connection and segment identity,
reason code, and recorder-observation source. Previous connection/segment IDs
may be retained for transitions.

This contract does not infer a transition from supervisor liveness or generic
message activity. Durable connection-stream persistence remains D2D work.

## Independent freshness dimensions

`evaluate_evidence_freshness` keeps these dimensions independent:

- `transport_keepalive_age_seconds`;
- `lifecycle_observation_age_seconds`;
- `orderbook_event_quiet_interval_seconds`.

Transport keepalive becomes `OBSERVED` only when both an explicit observation
timestamp and source such as `PING_PONG` are supplied. Otherwise it is
`UNKNOWN_NOT_OBSERVED`. Orderbook message age, lifecycle age, process
heartbeat, and supervisor heartbeat never substitute for transport keepalive.

## Evidence boundary

D2C leaves D2A admission and D2B rebuild contracts unchanged. A public trade
is not an account fill. REST lifecycle is not WebSocket evidence. Connection
metadata is not duration evidence. No D2C record is `REPLAY_QUALIFIED`.
Public live execution remains disabled, and real-money trading remains a
strict no-go.
