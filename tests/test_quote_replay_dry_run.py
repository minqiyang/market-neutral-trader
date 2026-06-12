from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from edmn_trader.data import ReplaySession, write_snapshots
from edmn_trader.research import DryRunQuoteEngine
from edmn_trader.scripts.quote_replay_dry_run import QuoteReplayRow, render_quote_dry_run_table
from edmn_trader.scripts.record_fixture_snapshots import build_fixture_snapshots

FIXTURES = Path(__file__).parent / "fixtures"


def test_replay_quote_dry_run_table_uses_snapshot_books(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshots.jsonl"
    observed_at = datetime(2026, 6, 11, 0, 0, tzinfo=UTC)
    snapshots = build_fixture_snapshots(
        fixtures_dir=FIXTURES,
        observed_at=observed_at,
        recorded_at=observed_at,
    )
    write_snapshots(snapshot_path, snapshots)

    engine = DryRunQuoteEngine()
    [frame] = ReplaySession.from_path(snapshot_path).frames()
    quote = engine.quote(frame.snapshot.normalized_orderbook, inventory=Decimal("0"))
    table = render_quote_dry_run_table(
        [QuoteReplayRow(sequence=frame.sequence, frame=frame, quote=quote)]
    )

    assert "DEMO-EVENT-MARKET" in table
    assert "0.4300" in table
    assert "0.4200" in table
    assert "0.4400" in table
    assert "dry-run only; no execution or order placement" in table
