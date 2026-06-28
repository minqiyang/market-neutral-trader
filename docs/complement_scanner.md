# Offline Complement Scanner

Stage 38 adds an offline scanner for same-market YES/NO complement-parity
research records. It reads only local fixture JSON or existing snapshot JSONL
files, uses the Stage 36 candidate model and Stage 37 fee estimate scaffold,
and writes deterministic JSONL plus Markdown summaries.

The scanner output is audit/paper research metadata only. It is not a trade
recommendation and it contains no executable order intent.

## Fixture Format

Fixture JSON may be an object with a `markets` list:

```json
{
  "source": "local-fixture",
  "fee_status": "supplied",
  "fee_per_contract": "0.0100",
  "fee_source_note": "operator supplied local paper assumption",
  "markets": [
    {
      "venue": "kalshi_demo",
      "market_id": "DEMO-MARKET",
      "best_yes_bid": "0.5300",
      "best_no_bid": "0.5200",
      "yes_bid_size": "10",
      "no_bid_size": "7",
      "estimated_slippage_per_contract": "0.0050",
      "failed_leg_reserve_per_contract": "0.0050",
      "minimum_net_edge_per_contract": "0.0100",
      "data_quality_flags": []
    }
  ]
}
```

Decimal fields must be strings. Each market row may override the top-level fee
fields. Missing or unknown fee status blocks `paper_candidate`. Stale or
invalid book flags also block `paper_candidate`.

## CLI

```bash
python scripts/23_scan_complement_arb.py \
  --input /tmp/complement_fixture.json \
  --jsonl-output /tmp/complement_candidates.jsonl \
  --markdown-output /tmp/complement_summary.md
```

The CLI defaults to local fixture mode. It does not accept credentials, live
endpoint arguments, WebSocket options, wallets, or order-placement parameters.

For existing local snapshot JSONL, use:

```bash
python scripts/23_scan_complement_arb.py \
  --input-kind snapshot-jsonl \
  --input /tmp/edmn_stage3_snapshots.jsonl \
  --jsonl-output /tmp/complement_candidates.jsonl \
  --markdown-output /tmp/complement_summary.md
```

Snapshot scans default to missing fee status, so any crossed condition would
remain audit-only unless an explicit local fee assumption is supplied.
