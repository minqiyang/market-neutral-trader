"""Guarded Polymarket US market-channel recorder."""

from __future__ import annotations

import argparse
from pathlib import Path

from edmn_trader.adapters.polymarket_us import (
    POLYMARKET_US_PUBLIC_BASE_URL,
    PolymarketUSMarketRecorderConfig,
    record_polymarket_us_market_channel,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, help="Polymarket US market slug.")
    parser.add_argument("--events-output", required=True, type=Path, help="Raw event JSONL path.")
    parser.add_argument(
        "--snapshots-output",
        required=True,
        type=Path,
        help="Normalized snapshot JSONL path.",
    )
    parser.add_argument(
        "--base-url",
        default=POLYMARKET_US_PUBLIC_BASE_URL,
        help="Polymarket US public base URL only.",
    )
    parser.add_argument(
        "--live-readonly-opt-in",
        action="store_true",
        help="Required before any read-only market-channel request can run.",
    )
    args = parser.parse_args()

    result = record_polymarket_us_market_channel(
        PolymarketUSMarketRecorderConfig(
            slug=args.slug,
            events_output_path=args.events_output,
            snapshots_output_path=args.snapshots_output,
            live_readonly_opt_in=args.live_readonly_opt_in,
            base_url=args.base_url,
        )
    )
    print(
        "wrote "
        f"{result.events_written} raw event(s) and "
        f"{result.snapshots_written} normalized snapshot(s)"
    )


if __name__ == "__main__":
    main()
