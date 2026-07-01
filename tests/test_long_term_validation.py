from __future__ import annotations

from decimal import Decimal

import pytest

from edmn_trader.arb.long_term_validation import (
    build_rolling_validation_report,
    write_rolling_validation_json,
    write_rolling_validation_jsonl,
    write_rolling_validation_markdown,
)
from edmn_trader.data.jsonl import read_jsonl_records, write_jsonl_records
from edmn_trader.scripts.long_term_validation import run


def test_rolling_validation_summarizes_7_30_90_day_windows() -> None:
    report = build_rolling_validation_report(
        _records(),
        as_of_date="2026-01-31",
        input_source="local_fixture",
    )

    seven, thirty, ninety = report.windows
    assert seven.window_days == 7
    assert seven.candidate_count == 2
    assert seven.paper_candidate_count == 1
    assert seven.demo_order_count == 2
    assert seven.fill_success_rate == Decimal("0.5")
    assert seven.partial_fill_rate == Decimal("0.5")
    assert seven.failed_leg_incident_count == 1
    assert seven.gross_edge == Decimal("0.0500")
    assert seven.net_edge_after_cost == Decimal("0.0350")
    assert seven.paper_pnl == Decimal("0.25")
    assert seven.demo_pnl == Decimal("-0.05")
    assert seven.max_drawdown == Decimal("0.05")
    assert seven.reconciliation_mismatch_count == 1
    assert seven.data_gap_count == 2
    assert seven.kill_switch_event_count == 1
    assert seven.false_positive_style_rejection_count == 1
    assert thirty.candidate_count == 3
    assert ninety.candidate_count == 4


def test_report_marks_framework_implemented_without_claiming_validation_complete() -> None:
    report = build_rolling_validation_report(
        _records(),
        as_of_date="2026-01-31",
        input_source="local_fixture",
    )

    record = report.to_record()
    assert record["framework_status"] == "implemented"
    assert record["validation_completed"] is False
    assert record["executable_order_intent"] is False
    assert "order_intent" not in record
    assert "production_ready" not in record
    assert "profitability" not in str(record).lower()
    assert report.private_live_prerequisites_unmet == (
        "missing real 30-90 day live-readonly data",
        "missing 30+ day paper trading history",
        "unresolved reconciliation mismatch status",
        "unvalidated fee/slippage assumptions",
        "missing legal/platform review",
    )


def test_outputs_are_deterministic_jsonl_json_and_markdown(tmp_path) -> None:
    report = build_rolling_validation_report(
        _records(),
        as_of_date="2026-01-31",
        input_source="local_fixture",
    )
    jsonl_path = tmp_path / "rolling.jsonl"
    json_path = tmp_path / "rolling.json"
    markdown_path = tmp_path / "rolling.md"

    write_rolling_validation_jsonl(jsonl_path, report)
    first_jsonl = jsonl_path.read_text(encoding="utf-8")
    write_rolling_validation_jsonl(jsonl_path, report)
    assert jsonl_path.read_text(encoding="utf-8") == first_jsonl

    write_rolling_validation_json(json_path, report)
    first_json = json_path.read_text(encoding="utf-8")
    write_rolling_validation_json(json_path, report)
    assert json_path.read_text(encoding="utf-8") == first_json

    [record] = list(read_jsonl_records(jsonl_path))
    assert record["record_type"] == "rolling_validation_report"
    assert record["windows"][0]["net_edge_after_cost"] == "0.0350"

    write_rolling_validation_markdown(markdown_path, report)
    summary = markdown_path.read_text(encoding="utf-8")
    assert "Framework implemented; validation is not completed." in summary
    assert "not trade recommendations" in summary
    assert "missing real 30-90 day live-readonly data" in summary
    assert "7-day window" in summary
    assert "90-day window" in summary


def test_cli_reads_multiple_local_jsonl_inputs(tmp_path) -> None:
    first_input = tmp_path / "scanner-and-paper.jsonl"
    second_input = tmp_path / "demo-and-monitoring.jsonl"
    jsonl_path = tmp_path / "rolling.jsonl"
    json_path = tmp_path / "rolling.json"
    markdown_path = tmp_path / "rolling.md"
    records = _records()
    write_jsonl_records(first_input, records[:7])
    write_jsonl_records(second_input, records[7:])

    report = run(
        input_paths=[first_input, second_input],
        as_of_date="2026-01-31",
        input_source="local_fixture",
        jsonl_output_path=jsonl_path,
        json_output_path=json_path,
        markdown_output_path=markdown_path,
    )

    assert report.windows[0].candidate_count == 2
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["artifact_counts"]["kalshi_demo_submission_preview"] == 1
    assert "rolling_validation_report" in json_path.read_text(encoding="utf-8")
    assert "paper_demo_validation_framework_only" in markdown_path.read_text(
        encoding="utf-8"
    )


def test_invalid_decimal_input_is_rejected_safely() -> None:
    bad_record = {
        "record_type": "offline_complement_research_candidate",
        "observed_at": "2026-01-31T00:00:00Z",
        "decision": "paper_candidate",
        "gross_edge_per_contract": 0.01,
        "candidate_size": "1",
    }

    with pytest.raises(ValueError, match="gross_edge_per_contract must be a decimal string"):
        build_rolling_validation_report(
            [bad_record],
            as_of_date="2026-01-31",
            input_source="local_fixture",
        )


def test_decimal_precision_is_preserved() -> None:
    report = build_rolling_validation_report(
        [
            {
                "record_type": "offline_complement_research_candidate",
                "observed_at": "2026-01-31T00:00:00Z",
                "decision": "paper_candidate",
                "gross_edge_per_contract": "0.000000000000000003",
                "candidate_size": "2",
                "total_estimated_net_edge": "0.000000000000000001",
            }
        ],
        as_of_date="2026-01-31",
        input_source="local_fixture",
    )

    window = report.windows[0]
    assert window.gross_edge == Decimal("0.000000000000000006")
    assert window.net_edge_after_cost == Decimal("0.000000000000000001")
    assert window.to_record()["gross_edge"] == "6E-18"
    assert window.to_record()["net_edge_after_cost"] == "1E-18"


def _records() -> list[dict[str, object]]:
    return [
        {
            "record_type": "offline_complement_research_candidate",
            "observed_at": "2026-01-30T12:00:00Z",
            "decision": "paper_candidate",
            "gross_edge_per_contract": "0.0200",
            "candidate_size": "2",
            "total_estimated_net_edge": "0.0200",
        },
        {
            "record_type": "offline_complement_research_candidate",
            "observed_at": "2026-01-25T12:00:00Z",
            "decision": "reject",
            "gross_edge_per_contract": "0.0100",
            "candidate_size": "1",
            "total_estimated_net_edge": "0",
            "false_positive_style_rejection": True,
        },
        {
            "record_type": "offline_complement_research_candidate",
            "observed_at": "2026-01-10T12:00:00Z",
            "decision": "audit_only",
            "gross_edge_per_contract": "0.0100",
            "candidate_size": "1",
            "total_estimated_net_edge": "0",
        },
        {
            "record_type": "offline_complement_research_candidate",
            "observed_at": "2025-12-15T12:00:00Z",
            "decision": "paper_candidate",
            "gross_edge_per_contract": "0.0100",
            "candidate_size": "1",
            "total_estimated_net_edge": "0.0010",
        },
        {
            "record_type": "offline_taker_fill_simulation",
            "observed_at": "2026-01-30T12:05:00Z",
            "failed_leg_quantity": "1",
            "simulated_total_net_edge": "0.0150",
        },
        {
            "record_type": "paper_complement_order_proposal",
            "created_at": "2026-01-30T12:10:00Z",
        },
        {
            "record_type": "paper_ledger_state",
            "report_date": "2026-01-30",
            "realized_net_pnl": "0.25",
            "reconciliation_mismatch_count": 0,
        },
        {
            "record_type": "complement_risk_decision_v2",
            "observed_at": "2026-01-30T12:15:00Z",
            "decision": "reject",
            "reasons": ["manual_approval_required", "kill_switch_active"],
        },
        {
            "record_type": "manual_approval_decision",
            "created_at": "2026-01-30T12:20:00Z",
            "status": "approved_for_paper_once",
        },
        {
            "record_type": "kalshi_demo_submission_preview",
            "observed_at": "2026-01-30T12:25:00Z",
            "status": "submitted",
            "dry_run": False,
            "request_previews": [{"side": "yes"}, {"side": "no"}],
        },
        {
            "record_type": "kalshi_demo_reconciliation_state",
            "observed_at": "2026-01-30T12:30:00Z",
            "mismatch_count": 1,
            "full_fill_count": 1,
            "partial_fill_count": 1,
            "demo_pnl": "-0.05",
            "orders": [{"client_order_id": "one"}, {"client_order_id": "two"}],
        },
        {
            "record_type": "daily_validation_report",
            "report_date": "2026-01-31",
            "gap_count": 2,
            "candidate_count": 2,
            "paper_candidate_count": 1,
        },
    ]
