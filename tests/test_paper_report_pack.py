from __future__ import annotations

from pathlib import Path

from edmn_trader.data.jsonl import write_jsonl_records
from edmn_trader.scripts.paper_report_pack import (
    PaperReportPackInput,
    generate_paper_report_pack,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_paper_report_pack_combines_stage_7_metrics_and_sec_facts(tmp_path: Path) -> None:
    log_path = _write_stage_6_log(tmp_path)
    output_dir = tmp_path / "pack"

    pack = generate_paper_report_pack(
        PaperReportPackInput(
            market_maker_logs=(log_path,),
            sec_companyfacts=(FIXTURES / "sec_companyfacts_aapl.json",),
            output_dir=output_dir,
        )
    )

    assert pack.stage7_report.supplied_fills == 0
    assert pack.sec_fact_count == 2
    text = (output_dir / "report_pack.md").read_text(encoding="utf-8")
    assert "Observed Stage 7 Attribution" in text
    assert "frames | 1" in text
    assert "Fill assumptions | not supplied" in text
    assert "SEC Fundamentals" in text
    assert "Apple Inc." in text
    assert "Revenues" in text
    assert "does not rank securities" in text
    assert "does not claim profitability" in text
    assert "trading signal" not in text.lower()


def test_paper_report_pack_marks_missing_sec_fundamentals_not_supplied(tmp_path: Path) -> None:
    output_dir = tmp_path / "pack"

    generate_paper_report_pack(
        PaperReportPackInput(
            market_maker_logs=(_write_stage_6_log(tmp_path),),
            output_dir=output_dir,
        )
    )

    text = (output_dir / "report_pack.md").read_text(encoding="utf-8")
    assert "SEC fundamentals | not supplied" in text
    assert "missing optional inputs are reported as not supplied" in text


def test_paper_report_pack_cli_writes_markdown(tmp_path: Path, capsys, monkeypatch) -> None:
    output_dir = tmp_path / "pack"
    monkeypatch.setattr(
        "sys.argv",
        [
            "paper_report_pack",
            "--market-maker-log",
            str(_write_stage_6_log(tmp_path)),
            "--sec-companyfacts",
            str(FIXTURES / "sec_companyfacts_aapl.json"),
            "--output-dir",
            str(output_dir),
        ],
    )

    main()

    assert (output_dir / "report_pack.md").exists()
    output = capsys.readouterr().out
    assert "report_pack_output=" in output
    assert "sec_facts=2" in output


def _write_stage_6_log(tmp_path: Path) -> Path:
    log_path = tmp_path / "market_maker.jsonl"
    write_jsonl_records(
        log_path,
        [
            {"record_type": "frame", "sequence": 1, "observed_at": "2026-06-24T00:00:00+00:00"},
            {
                "record_type": "quote_candidate",
                "sequence": 1,
                "instrument_id": "FED-TEST",
                "side": "buy",
                "price": "0.4100",
                "quantity": "1.00",
            },
            {"record_type": "risk_decision", "sequence": 1, "approved": True},
            {"record_type": "run_summary", "frame_count": 1, "quote_count": 1},
        ],
    )
    return log_path
