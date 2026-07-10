# D2D 100k Synthetic Benchmark

- run_time_utc: `2026-07-10T19:26:38Z`
- source_commit: `338dc4eb4af801e3d5d0c1113fb541230e765c5f`
- event_count: `100000`
- checkpoint_every_records: `1000`
- declared_memory_profile_bytes: `1073741824`
- Python: `3.12.13`
- platform: `macOS-27.0-arm64-arm-64bit`
- elapsed_seconds: `1.0306553340051323`
- peak_rss_mib: `35.625`
- checkpoint_count: `102`
- checkpoint_p95_seconds: `0.0002971089881611988`
- no_oom: `true`
- no_full_file_callback_work: `true`
- valid_hashes: `true`
- crash_recovery_valid: `true`
- classification: `PASS`

## Gates

| Gate | Limit | Result |
| --- | ---: | ---: |
| Completion | <= 600 s | 1.0307 s |
| Peak RSS | <= 512 MiB | 35.6250 MiB |
| Checkpoint p95 | <= 1 s | 0.000297 s |
| OOM | none | none |
| Full-file callback work | none | none |
| Hash verification | pass | pass |
| Partial-tail recovery | pass | pass |

The benchmark streamed records and retained no event list. It used a declared
1 GiB profile budget and passed the stricter 512 MiB measured-RSS gate. The
local Darwin host did not provide an enforceable cgroup/VM memory cap, so the
profile is a measured budget gate rather than an OS hard limit. No credential,
market network, VPS, campaign, or private raw data was used.

The 1,000,000-event benchmark remains pending and is mandatory before any
30-day collection decision.
