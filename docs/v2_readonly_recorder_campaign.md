# V2 Read-Only Recorder Campaign

Seven-day read-only campaigns must select only Demo/read-only markets whose
status is `open` or `trading`.

Selection blocks:

- `MARKET_STATUS_UNOPENED`
- `MARKET_STATUS_PAUSED`
- `MARKET_STATUS_CLOSED`
- `MARKET_STATUS_SETTLED`
- `MARKET_STATUS_FINALIZED`
- `MARKET_STATUS_UNKNOWN`
- `TIME_TO_CLOSE_TOO_SHORT`
- `MISSING_CLOSE_TIME`
- `MISSING_MARKET_METADATA`
- `EMPTY_ORDERBOOK`

For seven-day evidence, `close_time` or an equivalent expiration field must be
later than campaign duration plus at least 24 hours. Finalized, closed,
settled, resolved, or expired markets end campaign usefulness even when raw
artifact integrity still validates. Raw WebSocket data stays outside the public
repo, and real-money trading remains disabled.

Demo discovery uses `GET /markets?status=open` without timestamp filters and
follows at most 100 cursor pages of up to 1,000 records each. A scan is complete
only when the final cursor is empty; reaching the cap with a cursor remaining
fails closed. Markets are deduplicated before event hydration and eligibility
counting. REST response statuses are normalized for the lifecycle gate while
the raw status is retained in campaign metadata. Discovery failures are
distinct:

- `DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR`
- `DEMO_MARKET_DISCOVERY_INCOMPLETE_PAGE_LIMIT`
- `DEMO_NO_OPEN_MARKETS`
- `DEMO_NO_ELIGIBLE_MARKET`

Complete results retain cursor-exhaustion evidence, distinct and duplicate
counts, a versioned profile hash, primary and multi-label rejection totals, and
hashed near-miss lifecycle margins. These diagnostics contain no raw payloads
and do not weaken candidate gates.

Bounded five-minute smoke selection uses a 900-second safety buffer. It does not
reuse or weaken the seven-day duration plus 24-hour safety requirement.

## Lifecycle gate v2

The seven-day gate now uses the earliest conservative lifecycle deadline from
`close_time`, `expected_expiration_time`, `occurrence_datetime`, any explicit
early-close deadline, and settlement-time metadata when present. It requires that deadline to exceed
`campaign_required_end`, which is the selected time plus campaign duration and
the safety buffer. `latest_expiration_time` is metadata only and cannot
override an earlier expected expiration.

`occurrence_datetime` remains contract-ambiguous. Kalshi documents it as the
recorded time when the event occurred, while Demo independently returned a
future value equal to close and expected expiration. The selector therefore
retains it as a conservative deadline and does not authorize a live canary from
that ambiguous interpretation.

`can_close_early=true` requires expected-expiration or explicit early-close
deadline metadata. Long-horizon selection also fetches event metadata, rejects
sports/match markets by default, and preserves lifecycle fields and structured
rejection reasons in the manifest. Validation reports data integrity separately
from invalid market-lifecycle evidence. The bounded smoke/canary profiles stay
separate and do not count as seven-day evidence.
