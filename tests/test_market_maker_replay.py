from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from edmn_trader.core import ExecutionMode
from edmn_trader.data import write_snapshots
from edmn_trader.data.jsonl import read_jsonl_records
from edmn_trader.execution import FakeDemoExecutionAdapter
from edmn_trader.scripts.market_maker_replay import (
    MarketMakerReplayConfig,
    OpenQuote,
    main,
    run_market_maker_replay,
)
from edmn_trader.scripts.record_fixture_snapshots import build_fixture_snapshots

FIXTURES = Path(__file__).parent / "fixtures"


def test_market_maker_replay_defaults_to_dry_run_without_adapter_calls(tmp_path: Path) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)
    log_path = tmp_path / "market_maker.jsonl"
    adapter = FakeDemoExecutionAdapter()

    summary = run_market_maker_replay(
        input_path=snapshot_path,
        log_output=log_path,
        adapter=adapter,
    )

    assert adapter.calls == []
    assert summary.frame_count == 1
    assert summary.quote_count == 2
    assert summary.adapter_calls == 0
    records = list(read_jsonl_records(log_path))
    assert "frame" in {record["record_type"] for record in records}
    assert "quote_candidate" in {record["record_type"] for record in records}
    assert records[-1]["record_type"] == "run_summary"
    assert records[-1]["adapter_calls"] == 0
    assert records[-1]["fills_assumed"] == "0"


def test_market_maker_replay_demo_opt_in_uses_fake_adapter_after_risk(tmp_path: Path) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)
    log_path = tmp_path / "market_maker.jsonl"
    adapter = FakeDemoExecutionAdapter()

    summary = run_market_maker_replay(
        input_path=snapshot_path,
        log_output=log_path,
        config=MarketMakerReplayConfig(demo_opt_in=True),
        adapter=adapter,
    )

    assert [call[0] for call in adapter.calls] == ["place", "place"]
    assert summary.approved_actions == 2
    assert summary.adapter_calls == 2
    records = list(read_jsonl_records(log_path))
    assert [record["approved"] for record in records if record["record_type"] == "risk_decision"]
    assert [record["record_type"] for record in records].count("adapter_submission") == 2


@pytest.mark.parametrize(
    ("config", "limit_name"),
    [
        (
            MarketMakerReplayConfig(demo_opt_in=True, execution_mode=ExecutionMode.LIVE_DISABLED),
            "execution_mode",
        ),
        (
            MarketMakerReplayConfig(
                demo_opt_in=True,
                base_url="https://api.elections.example.invalid/trade-api/v2",
            ),
            "base_url",
        ),
        (MarketMakerReplayConfig(demo_opt_in=True, max_position_abs=Decimal("0")), "max_position"),
        (MarketMakerReplayConfig(demo_opt_in=True, max_notional=Decimal("0.01")), "max_notional"),
        (
            MarketMakerReplayConfig(
                demo_opt_in=True,
                current_daily_loss=Decimal("5.01"),
                max_loss=Decimal("5.00"),
            ),
            "max_daily_loss",
        ),
    ],
)
def test_market_maker_replay_risk_controls_block_adapter_access(
    tmp_path: Path,
    config: MarketMakerReplayConfig,
    limit_name: str,
) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)
    adapter = FakeDemoExecutionAdapter()

    summary = run_market_maker_replay(
        input_path=snapshot_path,
        log_output=tmp_path / "market_maker.jsonl",
        config=config,
        adapter=adapter,
    )

    assert adapter.calls == []
    assert summary.rejected_actions == 2
    records = list(read_jsonl_records(tmp_path / "market_maker.jsonl"))
    limit_names = {
        record["limit_name"] for record in records if record["record_type"] == "risk_decision"
    }
    assert any(limit_name in str(name) for name in limit_names)


def test_market_maker_replay_max_open_orders_skips_extra_quotes(tmp_path: Path) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)
    adapter = FakeDemoExecutionAdapter()

    summary = run_market_maker_replay(
        input_path=snapshot_path,
        log_output=tmp_path / "market_maker.jsonl",
        config=MarketMakerReplayConfig(demo_opt_in=True, max_open_orders=1),
        adapter=adapter,
    )

    assert len(adapter.calls) == 1
    assert summary.skipped_actions == 1
    records = list(read_jsonl_records(tmp_path / "market_maker.jsonl"))
    assert any(
        record.get("reason") == "max_open_orders would be exceeded" for record in records
    )


def test_market_maker_replay_kill_switch_blocks_adapter_access(tmp_path: Path) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)
    adapter = FakeDemoExecutionAdapter()

    summary = run_market_maker_replay(
        input_path=snapshot_path,
        log_output=tmp_path / "market_maker.jsonl",
        config=MarketMakerReplayConfig(demo_opt_in=True, kill_switch=True),
        adapter=adapter,
    )

    assert adapter.calls == []
    assert summary.skipped_actions == 2
    records = list(read_jsonl_records(tmp_path / "market_maker.jsonl"))
    assert all(
        "kill_switch" in record["reason"]
        for record in records
        if record["record_type"] == "lifecycle_intent"
    )


def test_market_maker_replay_holds_or_replaces_existing_quotes(tmp_path: Path) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)
    adapter = FakeDemoExecutionAdapter()

    summary = run_market_maker_replay(
        input_path=snapshot_path,
        log_output=tmp_path / "market_maker.jsonl",
        config=MarketMakerReplayConfig(demo_opt_in=True),
        adapter=adapter,
        initial_open_quotes=(
            OpenQuote(side="buy", price=Decimal("0.4200"), quantity=Decimal("1.00")),
            OpenQuote(side="sell", price=Decimal("0.4300"), quantity=Decimal("1.00")),
        ),
    )

    assert [call[0] for call in adapter.calls] == ["modify"]
    assert summary.approved_actions == 1
    assert summary.skipped_actions == 1
    records = list(read_jsonl_records(tmp_path / "market_maker.jsonl"))
    lifecycle_actions = [
        record["lifecycle_action"]
        for record in records
        if record["record_type"] == "lifecycle_intent"
    ]
    assert lifecycle_actions == ["hold", "replace"]


def test_market_maker_replay_kill_switch_emits_cancel_intents_for_open_quotes(
    tmp_path: Path,
) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)
    adapter = FakeDemoExecutionAdapter()

    summary = run_market_maker_replay(
        input_path=snapshot_path,
        log_output=tmp_path / "market_maker.jsonl",
        config=MarketMakerReplayConfig(demo_opt_in=True, kill_switch=True),
        adapter=adapter,
        initial_open_quotes=(
            OpenQuote(side="buy", price=Decimal("0.4200"), quantity=Decimal("1.00")),
            OpenQuote(side="sell", price=Decimal("0.4400"), quantity=Decimal("1.00")),
        ),
    )

    assert adapter.calls == []
    assert summary.skipped_actions == 2
    records = list(read_jsonl_records(tmp_path / "market_maker.jsonl"))
    assert [
        record["lifecycle_action"]
        for record in records
        if record["record_type"] == "lifecycle_intent"
    ] == ["cancel", "cancel"]


def test_market_maker_replay_logs_adapter_errors_after_risk_approval(tmp_path: Path) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)

    summary = run_market_maker_replay(
        input_path=snapshot_path,
        log_output=tmp_path / "market_maker.jsonl",
        config=MarketMakerReplayConfig(demo_opt_in=True),
        adapter=FakeDemoExecutionAdapter(fail_actions={"place"}),
    )

    assert summary.approved_actions == 2
    assert summary.adapter_calls == 2
    records = list(read_jsonl_records(tmp_path / "market_maker.jsonl"))
    assert [record["record_type"] for record in records].count("adapter_error") == 2


def test_market_maker_replay_script_prints_summary(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    snapshot_path = _write_fixture_snapshots(tmp_path)
    log_path = tmp_path / "market_maker.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        [
            "market_maker_replay",
            "--input",
            str(snapshot_path),
            "--log-output",
            str(log_path),
        ],
    )

    main()

    output = capsys.readouterr().out
    assert "frames=1" in output
    assert "adapter_calls=0" in output
    assert "no fills, PnL, live trading, or profitability claims" in output


def _write_fixture_snapshots(tmp_path: Path) -> Path:
    snapshot_path = tmp_path / "snapshots.jsonl"
    observed_at = datetime(2026, 6, 11, 0, 0, tzinfo=UTC)
    write_snapshots(
        snapshot_path,
        build_fixture_snapshots(
            fixtures_dir=FIXTURES,
            observed_at=observed_at,
            recorded_at=observed_at,
        ),
    )
    return snapshot_path
