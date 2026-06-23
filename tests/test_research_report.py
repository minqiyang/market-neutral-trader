from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from edmn_trader.data.jsonl import write_jsonl_records
from edmn_trader.scripts.research_report import (
    ResearchReportInput,
    generate_research_report,
    main,
)


def test_research_report_handles_stage_6_log_with_no_fills(tmp_path: Path) -> None:
    log_path = _write_stage_6_log(tmp_path)
    report_path = tmp_path / "report.md"

    report = generate_research_report(
        ResearchReportInput(
            market_maker_logs=(log_path,),
            output_path=report_path,
        )
    )

    assert report.supplied_fills == 0
    assert report.realized_net_pnl == Decimal("0")
    text = report_path.read_text(encoding="utf-8")
    assert "Observed Stage 6 Counts" in text
    assert "frames | 1" in text
    assert "adapter submissions | 1" in text
    assert "no fills supplied" in text
    assert "not inferred from fake/demo adapter submissions" in text
    assert "does not claim profitability or production readiness" in text


def test_research_report_attributes_explicit_fills_only(tmp_path: Path) -> None:
    log_path = _write_stage_6_log(tmp_path)
    fills_path = tmp_path / "fills.jsonl"
    write_jsonl_records(
        fills_path,
        [
            {
                "instrument_id": "FED-TEST",
                "side": "buy",
                "price": "0.4000",
                "quantity": "1.50",
                "fee": "0.0100",
                "observed_at": "2026-06-22T10:00:00+00:00",
                "assumption_note": "local explicit fill assumption",
            },
            {
                "instrument_id": "FED-TEST",
                "side": "sell",
                "price": "0.4500",
                "quantity": "1.00",
                "fee": "0.0100",
                "observed_at": "2026-06-22T10:05:00+00:00",
                "assumption_note": "local explicit fill assumption",
            },
        ],
    )

    report = generate_research_report(
        ResearchReportInput(
            market_maker_logs=(log_path,),
            fills_path=fills_path,
            output_path=tmp_path / "report.md",
        )
    )

    assert report.supplied_fills == 2
    assert report.total_fees == Decimal("0.0200")
    assert report.realized_gross_pnl == Decimal("0.0500")
    assert report.realized_net_pnl == Decimal("0.0300")
    assert report.ending_inventory == Decimal("0.50")
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "supplied fills | 2" in text
    assert "realized gross PnL | 0.0500" in text
    assert "realized net PnL | 0.0300" in text
    assert "ending inventory | 0.50" in text
    assert "local explicit fill assumption" in text


def test_research_report_rejects_secret_like_fill_fields(tmp_path: Path) -> None:
    log_path = _write_stage_6_log(tmp_path)
    fills_path = tmp_path / "fills.jsonl"
    write_jsonl_records(
        fills_path,
        [
            {
                "instrument_id": "FED-TEST",
                "side": "buy",
                "price": "0.4000",
                "quantity": "1.00",
                "fee": "0.0100",
                "observed_at": "2026-06-22T10:00:00+00:00",
                "assumption_note": "local explicit fill assumption",
                "api_key": "should-not-be-read",
            }
        ],
    )

    with pytest.raises(ValueError, match="secret-like fill field"):
        generate_research_report(
            ResearchReportInput(
                market_maker_logs=(log_path,),
                fills_path=fills_path,
                output_path=tmp_path / "report.md",
            )
        )


def test_research_report_cli_writes_markdown(tmp_path: Path, capsys, monkeypatch) -> None:
    log_path = _write_stage_6_log(tmp_path)
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "research_report",
            "--market-maker-log",
            str(log_path),
            "--output",
            str(report_path),
        ],
    )

    main()

    assert report_path.exists()
    output = capsys.readouterr().out
    assert "report_output=" in output
    assert "supplied_fills=0" in output


def _write_stage_6_log(tmp_path: Path) -> Path:
    log_path = tmp_path / "market_maker.jsonl"
    write_jsonl_records(
        log_path,
        [
            {"record_type": "frame", "sequence": 1, "observed_at": "2026-06-22T10:00:00+00:00"},
            {
                "record_type": "quote_candidate",
                "sequence": 1,
                "instrument_id": "FED-TEST",
                "side": "buy",
                "price": "0.4100",
                "quantity": "1.00",
            },
            {
                "record_type": "quote_candidate",
                "sequence": 1,
                "instrument_id": "FED-TEST",
                "side": "sell",
                "price": "0.4400",
                "quantity": "1.00",
            },
            {
                "record_type": "risk_decision",
                "sequence": 1,
                "approved": True,
                "reason": "approved",
            },
            {
                "record_type": "risk_decision",
                "sequence": 1,
                "approved": False,
                "reason": "missing demo opt-in",
            },
            {
                "record_type": "lifecycle_intent",
                "sequence": 1,
                "result_status": "skipped",
                "reason": "max_open_orders would be exceeded",
            },
            {
                "record_type": "adapter_submission",
                "sequence": 1,
                "adapter_called": True,
            },
            {"record_type": "adapter_error", "sequence": 1, "error_reason": "fake failure"},
            {"record_type": "run_summary", "frame_count": 1, "quote_count": 2},
        ],
    )
    return log_path
