from __future__ import annotations

from decimal import Decimal

import pytest

from edmn_trader.arb.monitoring import (
    build_daily_validation_report,
    write_daily_validation_jsonl,
    write_daily_validation_markdown,
)
from edmn_trader.data.jsonl import read_jsonl_records, write_jsonl_records
from edmn_trader.scripts.daily_validation_report import run


def test_daily_report_summarizes_local_monitoring_records() -> None:
    report = build_daily_validation_report(
        _records(),
        report_date="2026-01-01",
        input_source="local_fixture",
    )

    assert report.record_type == "daily_validation_report"
    assert report.recorder_uptime_count == 1
    assert report.recorder_downtime_count == 1
    assert report.max_data_lag_seconds == Decimal("12.5")
    assert report.gap_count == 2
    assert report.candidate_count == 3
    assert report.paper_candidate_count == 1
    assert report.audit_only_count == 1
    assert report.reject_count == 1
    assert report.rejection_reason_counts["missing_fee_model"] == 1
    assert report.paper_outcome_count == 1
    assert report.demo_outcome_count == 1
    assert report.total_fees == Decimal("0.0123")
    assert report.slippage_incident_count == 1
    assert report.failed_leg_incident_count == 1
    assert report.reconciliation_mismatch_count == 2
    assert report.kill_switch_event_count == 1


def test_daily_report_output_is_research_only_and_not_executable() -> None:
    report = build_daily_validation_report(
        _records(),
        report_date="2026-01-01",
        input_source="local_fixture",
    )

    record = report.to_record()
    assert record["executable_order_intent"] is False
    assert record["research_use"] == "monitoring_research_record_only"
    assert "order_intent" not in record
    assert "execution_mode" not in record


def test_daily_report_writes_deterministic_jsonl_and_markdown(tmp_path) -> None:
    report = build_daily_validation_report(
        _records(),
        report_date="2026-01-01",
        input_source="local_fixture",
    )
    jsonl_path = tmp_path / "daily.jsonl"
    markdown_path = tmp_path / "daily.md"

    write_daily_validation_jsonl(jsonl_path, report)
    first = jsonl_path.read_text(encoding="utf-8")
    write_daily_validation_jsonl(jsonl_path, report)
    assert jsonl_path.read_text(encoding="utf-8") == first
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["record_type"] == "daily_validation_report"
    assert record["total_fees"] == "0.0123"

    write_daily_validation_markdown(markdown_path, report)
    summary = markdown_path.read_text(encoding="utf-8")
    assert "monitoring research records only" in summary
    assert "candidate_count: 3" in summary
    assert "kill_switch_event_count: 1" in summary


def test_daily_report_cli_reads_local_jsonl_only(tmp_path) -> None:
    input_path = tmp_path / "monitoring.jsonl"
    jsonl_path = tmp_path / "daily.jsonl"
    markdown_path = tmp_path / "daily.md"
    write_jsonl_records(input_path, _records())

    report = run(
        input_path=input_path,
        report_date="2026-01-01",
        input_source="local_fixture",
        jsonl_output_path=jsonl_path,
        markdown_output_path=markdown_path,
    )

    assert report.candidate_count == 3
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["report_date"] == "2026-01-01"
    assert "daily_validation_report" in markdown_path.read_text(encoding="utf-8")


def test_daily_report_rejects_negative_data_lag() -> None:
    with pytest.raises(ValueError, match="data_lag_seconds must be non-negative"):
        build_daily_validation_report(
            [{"record_type": "recorder_status", "up": True, "data_lag_seconds": "-1"}],
            report_date="2026-01-01",
            input_source="local_fixture",
        )


def _records() -> list[dict[str, object]]:
    return [
        {
            "record_type": "recorder_status",
            "up": True,
            "data_lag_seconds": "12.5",
            "data_quality_flags": ["sequence_gap"],
        },
        {
            "record_type": "recorder_status",
            "up": False,
            "data_lag_seconds": "2",
            "gap_count": 1,
        },
        {
            "record_type": "offline_complement_research_candidate",
            "decision": "paper_candidate",
            "flags": ["manual_review_required"],
        },
        {
            "record_type": "offline_complement_research_candidate",
            "decision": "audit_only",
            "flags": ["manual_review_required"],
        },
        {
            "record_type": "offline_complement_research_candidate",
            "decision": "reject",
            "rejection_reasons": ["missing_fee_model"],
        },
        {
            "record_type": "paper_ledger_state",
            "total_fees": "0.0123",
            "reconciliation_mismatch_count": 2,
        },
        {
            "record_type": "offline_taker_fill_simulation",
            "failed_leg_quantity": "1",
            "flags": ["slippage_applied"],
        },
        {
            "record_type": "manual_approval_decision",
            "status": "approved_for_paper_once",
        },
        {
            "record_type": "demo_outcome",
            "status": "blocked",
        },
        {
            "record_type": "complement_risk_decision_v2",
            "reasons": ["manual_approval_required", "kill_switch_active"],
        },
    ]
