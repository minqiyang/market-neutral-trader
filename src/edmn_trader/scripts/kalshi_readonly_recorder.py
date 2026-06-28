"""Guarded Kalshi Demo read-only recorder."""

from __future__ import annotations

import argparse
from pathlib import Path

from edmn_trader.adapters.kalshi import (
    KALSHI_DEMO_REST_BASE_URL,
    KalshiReadOnlyRecorderConfig,
    record_kalshi_readonly_orderbook,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Kalshi Demo market ticker.")
    parser.add_argument("--events-output", required=True, type=Path, help="Raw event JSONL path.")
    parser.add_argument(
        "--snapshots-output",
        required=True,
        type=Path,
        help="Normalized snapshot JSONL path.",
    )
    parser.add_argument("--depth", type=int, default=None, help="Optional orderbook depth.")
    parser.add_argument(
        "--base-url",
        default=KALSHI_DEMO_REST_BASE_URL,
        help="Kalshi Demo REST base URL only.",
    )
    parser.add_argument(
        "--live-readonly-opt-in",
        action="store_true",
        help="Required before any read-only live Demo request can run.",
    )
    args = parser.parse_args()

    result = record_kalshi_readonly_orderbook(
        KalshiReadOnlyRecorderConfig(
            ticker=args.ticker,
            events_output_path=args.events_output,
            snapshots_output_path=args.snapshots_output,
            live_readonly_opt_in=args.live_readonly_opt_in,
            base_url=args.base_url,
            depth=args.depth,
        )
    )
    print(
        "wrote "
        f"{result.events_written} raw event(s) and "
        f"{result.snapshots_written} normalized snapshot(s)"
    )


if __name__ == "__main__":
    main()
