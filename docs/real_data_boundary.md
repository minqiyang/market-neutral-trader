# Real-Data Boundary

Policy: `edmn.market_data_boundary.v1`

Git contains code, declared synthetic fixtures, generic governance, software
provenance, and Boolean safety results only. Real venue-derived payloads,
identifiers, counters, timestamps, hashes, manifests, books, replay material,
account/order data, and anything that can identify or reconstruct a real stream
remain outside every Git repository and GitHub surface.

The rule is forward-only. Existing history is preserved as legacy; it is not a
claim that old history is evidence-free. Legacy evidence paths are frozen and
must not be regenerated, updated, renamed, copied, or deleted by a new commit.

## Git-safe receipt

A receipt may contain only the policy ID, a software commit, Boolean validator
and safety outcomes, the `OWNER_LOCAL_ONLY` storage classification, and false
production/order-write outcomes. It must not contain a local evidence reference
or detailed result.

## Contributor and automation rules

- Do not paste real evidence into commits, pull requests, issues, reviews,
  releases, Actions logs, or workflow artifacts.
- Put new synthetic data under `tests/synthetic_fixtures/` and declare
  `"provenance": "SYNTHETIC"` or `"synthetic": true`.
- Run the staged scanner before committing:

  ```bash
  python scripts/check_forward_only_data_boundary.py \
    --repo . \
    --policy .github/forward_only_data_boundary.json \
    --expected-profile public \
    --mode staged-diff
  ```

- CI remains authoritative and reviews ambiguous content fail closed.
- CI does not replay or publish reports from frozen legacy fixtures. Validation
  commands suppress detailed stdout/stderr and emit Boolean pass/fail labels so
  failures cannot copy fixture content into Actions logs.

Production endpoints and order-writing remain disabled. Demo order-writing
requires a separate explicit owner authorization.
