# V2 Lifecycle Gate

The seven-day read-only recorder uses a conservative lifecycle deadline rather
than `close_time` alone.

```text
campaign_required_end = selected_at_utc + duration_seconds + safety_buffer_seconds
lifecycle_deadline = min(close_time, expected_expiration_time,
                         occurrence_datetime, explicit_early_close_deadline)
```

`latest_expiration_time` is retained as metadata but is never the sole safety
deadline. A market must be `open` or `trading`, and every applicable
conservative deadline must exceed `campaign_required_end`.

The long-horizon gate rejects early-close markets without expected-expiration
or explicit early-close deadline metadata, early expected expiration or event
occurrence, missing event metadata, and sports/match markets unless an explicit
future configuration allows that category. The manifest preserves the raw
lifecycle fields, normalized status, event metadata, lifecycle deadline,
required end, and structured rejection reason.

Selection is explicit across three profiles. Smoke uses a 900-second buffer.
The 1,800-second canary uses a 3,600-second buffer, requires complete event
category/title metadata from the core event endpoint, rejects sports and
match-like events, and rejects any
`can_close_early=true` candidate. Seven-day selection uses at least an
86,400-second buffer and retains the stricter long-horizon rules. The manifest
records the selected profile and buffer. None of these profiles implies
seven-day evidence before the corresponding bounded run completes.

Discovery fetches bounded market pages before event hydration, deduplicates
event tickers, hydrates core events in bounded batches, and caches them for the
run. Missing batch members may use a candidate-local single-event fallback.
Rate limits and transient server/transport failures receive at most three
attempts; an exhausted page or batch marks coverage incomplete rather than
claiming that no eligible market exists.

Validation reports separate `DATA_INTEGRITY_PASS` from
`CAMPAIGN_EVIDENCE_INVALID_MARKET_LIFECYCLE`; clean JSONL/hash/artifact
integrity cannot turn a closed or resolved market into valid long-horizon
evidence. The public live gate remains disabled and no order-write path is
introduced.
