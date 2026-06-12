"""Run the dry-run quote engine over JSONL replay snapshots."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from edmn_trader.data.replay import ReplayFrame, ReplaySession
from edmn_trader.research import DRY_RUN_LIMITATION, DryRunQuoteEngine, QuoteEngineConfig
from edmn_trader.research.quotes import DryRunQuoteResult


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Input JSONL snapshot path.")
    parser.add_argument(
        "--inventory",
        default="0",
        help="Current YES inventory used for deterministic quote skew.",
    )
    parser.add_argument("--tick-size", default="0.0001", help="Quote tick size.")
    parser.add_argument("--quantity", default="1.00", help="Dry-run quote quantity.")
    parser.add_argument(
        "--default-spread",
        default="0.0200",
        help="Minimum default quote spread when book spread is unavailable or tighter.",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Sort out-of-order snapshots by observed timestamp instead of failing.",
    )
    args = parser.parse_args()

    engine = DryRunQuoteEngine(
        config=QuoteEngineConfig(
            tick_size=Decimal(args.tick_size),
            order_quantity=Decimal(args.quantity),
            default_spread=Decimal(args.default_spread),
            min_spread=Decimal(args.tick_size),
        )
    )
    session = ReplaySession.from_path(args.input, strict=not args.no_strict)
    rows = [
        QuoteReplayRow(
            sequence=frame.sequence,
            frame=frame,
            quote=engine.quote(
                frame.snapshot.normalized_orderbook,
                inventory=Decimal(args.inventory),
            ),
        )
        for frame in session.frames()
    ]
    print(render_quote_dry_run_table(rows))


class QuoteReplayRow:
    """One replay row with its dry-run quote output."""

    def __init__(self, *, sequence: int, frame: ReplayFrame, quote: DryRunQuoteResult) -> None:
        self.sequence = sequence
        self.frame = frame
        self.quote = quote


def render_quote_dry_run_table(rows: list[QuoteReplayRow]) -> str:
    """Render a concise dry-run quote table."""

    if not rows:
        return "no snapshots"

    headers = [
        "seq",
        "observed_at",
        "ticker",
        "fair",
        "adj_fair",
        "inventory",
        "skew",
        "bid",
        "ask",
        "qty",
        "spread",
        "note",
    ]
    table_rows = [
        [
            str(row.sequence),
            row.frame.snapshot.observed_at.isoformat(),
            row.frame.snapshot.ticker,
            str(row.quote.fair_value),
            str(row.quote.adjusted_fair_value),
            str(row.quote.inventory),
            str(row.quote.inventory_skew),
            str(row.quote.bid_price),
            str(row.quote.ask_price),
            str(row.quote.bid_intent.quantity),
            str(row.quote.target_spread),
            DRY_RUN_LIMITATION,
        ]
        for row in rows
    ]

    widths = [
        max(len(row[index]) for row in [headers, *table_rows])
        for index in range(len(headers))
    ]
    lines = [
        " | ".join(cell.ljust(width) for cell, width in zip(headers, widths, strict=True)),
        "-+-".join("-" * width for width in widths),
    ]
    lines.extend(
        " | ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        for row in table_rows
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
