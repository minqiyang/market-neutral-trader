"""Offline daily validation reports for complement research records."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from edmn_trader.core.models import ZERO
from edmn_trader.data.jsonl import write_jsonl_records


@dataclass(frozen=True, slots=True)
class DailyValidationReport:
    report_date: str
    input_source: str
    recorder_uptime_count: int
    recorder_downtime_count: int
    max_data_lag_seconds: Decimal
    gap_count: int
    candidate_count: int
    paper_candidate_count: int
    audit_only_count: int
    reject_count: int
    rejection_reason_counts: dict[str, int]
    paper_outcome_count: int
    demo_outcome_count: int
    total_fees: Decimal
    slippage_incident_count: int
    failed_leg_incident_count: int
    reconciliation_mismatch_count: int
    kill_switch_event_count: int
    record_type: str = "daily_validation_report"
    research_use: str = "monitoring_research_record_only"
    executable_order_intent: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "report_date": self.report_date,
            "input_source": self.input_source,
            "recorder_uptime_count": self.recorder_uptime_count,
            "recorder_downtime_count": self.recorder_downtime_count,
            "max_data_lag_seconds": str(self.max_data_lag_seconds),
            "gap_count": self.gap_count,
            "candidate_count": self.candidate_count,
            "paper_candidate_count": self.paper_candidate_count,
            "audit_only_count": self.audit_only_count,
            "reject_count": self.reject_count,
            "rejection_reason_counts": dict(sorted(self.rejection_reason_counts.items())),
            "paper_outcome_count": self.paper_outcome_count,
            "demo_outcome_count": self.demo_outcome_count,
            "total_fees": str(self.total_fees),
            "slippage_incident_count": self.slippage_incident_count,
            "failed_leg_incident_count": self.failed_leg_incident_count,
            "reconciliation_mismatch_count": self.reconciliation_mismatch_count,
            "kill_switch_event_count": self.kill_switch_event_count,
        }


def build_daily_validation_report(
    records: Iterable[Mapping[str, object]],
    *,
    report_date: str,
    input_source: str,
) -> DailyValidationReport:
    """Build a deterministic monitoring report from local records only."""

    uptime_count = 0
    downtime_count = 0
    max_lag = ZERO
    gap_count = 0
    candidate_count = 0
    paper_candidate_count = 0
    audit_only_count = 0
    reject_count = 0
    rejection_reasons: Counter[str] = Counter()
    paper_outcome_count = 0
    demo_outcome_count = 0
    total_fees = ZERO
    slippage_incident_count = 0
    failed_leg_incident_count = 0
    reconciliation_mismatch_count = 0
    kill_switch_event_count = 0

    for record in records:
        record_type = _optional_str(record, "record_type")
        flags = _str_sequence(record.get("flags", ())) + _str_sequence(
            record.get("data_quality_flags", ())
        )
        reasons = _str_sequence(record.get("reasons", ()))
        if record_type == "recorder_status":
            if record.get("up") is True:
                uptime_count += 1
            elif record.get("up") is False:
                downtime_count += 1
            if "data_lag_seconds" in record:
                max_lag = max(max_lag, _non_negative_decimal(record, "data_lag_seconds"))
        if "sequence_gap" in flags or "data_gap" in flags:
            gap_count += 1
        if "gap_count" in record:
            gap_count += _non_negative_int(record, "gap_count")
        if record_type == "offline_complement_research_candidate":
            candidate_count += 1
            decision = _optional_str(record, "decision")
            if decision == "paper_candidate":
                paper_candidate_count += 1
            elif decision == "audit_only":
                audit_only_count += 1
            elif decision == "reject":
                reject_count += 1
                rejection_reasons.update(_str_sequence(record.get("rejection_reasons", ())))
        if record_type == "paper_ledger_state":
            total_fees += _non_negative_decimal(record, "total_fees")
            reconciliation_mismatch_count += _non_negative_int(
                record,
                "reconciliation_mismatch_count",
            )
        if record_type == "offline_taker_fill_simulation":
            if _non_negative_decimal(record, "failed_leg_quantity") > ZERO:
                failed_leg_incident_count += 1
            if "slippage_applied" in flags:
                slippage_incident_count += 1
        if record_type == "manual_approval_decision":
            paper_outcome_count += 1
        if record_type == "demo_outcome":
            demo_outcome_count += 1
        if "kill_switch_active" in reasons or record_type == "kill_switch_event":
            kill_switch_event_count += 1

    return DailyValidationReport(
        report_date=report_date,
        input_source=input_source,
        recorder_uptime_count=uptime_count,
        recorder_downtime_count=downtime_count,
        max_data_lag_seconds=max_lag,
        gap_count=gap_count,
        candidate_count=candidate_count,
        paper_candidate_count=paper_candidate_count,
        audit_only_count=audit_only_count,
        reject_count=reject_count,
        rejection_reason_counts=dict(rejection_reasons),
        paper_outcome_count=paper_outcome_count,
        demo_outcome_count=demo_outcome_count,
        total_fees=total_fees,
        slippage_incident_count=slippage_incident_count,
        failed_leg_incident_count=failed_leg_incident_count,
        reconciliation_mismatch_count=reconciliation_mismatch_count,
        kill_switch_event_count=kill_switch_event_count,
    )


def write_daily_validation_jsonl(path: Path, report: DailyValidationReport) -> None:
    write_jsonl_records(path, [report.to_record()])


def write_daily_validation_markdown(path: Path, report: DailyValidationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown_summary(report), encoding="utf-8")


def _markdown_summary(report: DailyValidationReport) -> str:
    return "\n".join(
        [
            "# Daily Validation Report",
            "",
            "Records are monitoring research records only, not executable order intents.",
            "",
            f"- record_type: {report.record_type}",
            f"- report_date: {report.report_date}",
            f"- input_source: {report.input_source}",
            f"- recorder_uptime_count: {report.recorder_uptime_count}",
            f"- recorder_downtime_count: {report.recorder_downtime_count}",
            f"- max_data_lag_seconds: {report.max_data_lag_seconds}",
            f"- gap_count: {report.gap_count}",
            f"- candidate_count: {report.candidate_count}",
            f"- paper_candidate_count: {report.paper_candidate_count}",
            f"- audit_only_count: {report.audit_only_count}",
            f"- reject_count: {report.reject_count}",
            f"- paper_outcome_count: {report.paper_outcome_count}",
            f"- demo_outcome_count: {report.demo_outcome_count}",
            f"- total_fees: {report.total_fees}",
            f"- slippage_incident_count: {report.slippage_incident_count}",
            f"- failed_leg_incident_count: {report.failed_leg_incident_count}",
            f"- reconciliation_mismatch_count: {report.reconciliation_mismatch_count}",
            f"- kill_switch_event_count: {report.kill_switch_event_count}",
            "",
        ]
    )


def _optional_str(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if value is None:
        return ""
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ValueError(msg)
    return value


def _non_negative_decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string"
        raise ValueError(msg)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ValueError(msg) from exc
    if parsed < ZERO:
        msg = f"{field_name} must be non-negative"
        raise ValueError(msg)
    return parsed


def _non_negative_int(record: Mapping[str, object], field_name: str) -> int:
    value = record.get(field_name)
    if not isinstance(value, int) or value < 0:
        msg = f"{field_name} must be a non-negative integer"
        raise ValueError(msg)
    return value


def _str_sequence(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        msg = "expected a list of strings"
        raise ValueError(msg)
    if not all(isinstance(item, str) for item in value):
        msg = "expected a list of strings"
        raise ValueError(msg)
    return tuple(value)
