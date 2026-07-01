"""Offline rolling validation summaries for complement research artifacts."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from edmn_trader.core.models import ZERO
from edmn_trader.data.jsonl import write_jsonl_records

WINDOW_DAYS = (7, 30, 90)


@dataclass(frozen=True, slots=True)
class RollingValidationWindow:
    window_days: int
    start_date: str
    end_date: str
    candidate_count: int
    paper_candidate_count: int
    demo_order_count: int
    fill_success_rate: Decimal
    partial_fill_rate: Decimal
    failed_leg_incident_count: int
    gross_edge: Decimal
    net_edge_after_cost: Decimal
    paper_pnl: Decimal
    demo_pnl: Decimal
    max_drawdown: Decimal
    reconciliation_mismatch_count: int
    data_gap_count: int
    kill_switch_event_count: int
    false_positive_style_rejection_count: int
    undated_record_count: int

    def to_record(self) -> dict[str, object]:
        return {
            "window_days": self.window_days,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "candidate_count": self.candidate_count,
            "paper_candidate_count": self.paper_candidate_count,
            "demo_order_count": self.demo_order_count,
            "fill_success_rate": str(self.fill_success_rate),
            "partial_fill_rate": str(self.partial_fill_rate),
            "failed_leg_incident_count": self.failed_leg_incident_count,
            "gross_edge": str(self.gross_edge),
            "net_edge_after_cost": str(self.net_edge_after_cost),
            "paper_pnl": str(self.paper_pnl),
            "demo_pnl": str(self.demo_pnl),
            "max_drawdown": str(self.max_drawdown),
            "reconciliation_mismatch_count": self.reconciliation_mismatch_count,
            "data_gap_count": self.data_gap_count,
            "kill_switch_event_count": self.kill_switch_event_count,
            "false_positive_style_rejection_count": (
                self.false_positive_style_rejection_count
            ),
            "undated_record_count": self.undated_record_count,
        }


@dataclass(frozen=True, slots=True)
class RollingValidationReport:
    as_of_date: str
    input_source: str
    windows: tuple[RollingValidationWindow, ...]
    artifact_counts: dict[str, int]
    private_live_prerequisites_unmet: tuple[str, ...]
    validation_completed: bool = False
    record_type: str = "rolling_validation_report"
    framework_status: str = "implemented"
    research_use: str = "paper_demo_validation_framework_only"
    executable_order_intent: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "framework_status": self.framework_status,
            "validation_completed": self.validation_completed,
            "as_of_date": self.as_of_date,
            "input_source": self.input_source,
            "artifact_counts": dict(sorted(self.artifact_counts.items())),
            "private_live_prerequisites_unmet": list(
                self.private_live_prerequisites_unmet
            ),
            "windows": [window.to_record() for window in self.windows],
        }


def build_rolling_validation_report(
    records: Iterable[Mapping[str, object]],
    *,
    as_of_date: str,
    input_source: str,
    live_readonly_data_days: int = 0,
    paper_history_days: int = 0,
    fee_slippage_assumptions_validated: bool = False,
    legal_platform_review_complete: bool = False,
) -> RollingValidationReport:
    """Build deterministic 7/30/90-day validation summaries from local records."""

    parsed_as_of = _parse_date_label(as_of_date)
    record_list = tuple(records)
    windows = tuple(
        _build_window(record_list, as_of=parsed_as_of, window_days=days)
        for days in WINDOW_DAYS
    )
    artifact_counts: Counter[str] = Counter(
        _optional_str(record, "record_type") for record in record_list
    )
    prerequisites = _unmet_prerequisites(
        windows,
        live_readonly_data_days=live_readonly_data_days,
        paper_history_days=paper_history_days,
        fee_slippage_assumptions_validated=fee_slippage_assumptions_validated,
        legal_platform_review_complete=legal_platform_review_complete,
    )
    return RollingValidationReport(
        as_of_date=as_of_date,
        input_source=input_source,
        windows=windows,
        artifact_counts=dict(artifact_counts),
        private_live_prerequisites_unmet=prerequisites,
    )


def write_rolling_validation_jsonl(path: Path, report: RollingValidationReport) -> None:
    write_jsonl_records(path, [report.to_record()])


def write_rolling_validation_json(path: Path, report: RollingValidationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_record(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_rolling_validation_markdown(path: Path, report: RollingValidationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_rolling_validation_markdown(report), encoding="utf-8")


def render_rolling_validation_markdown(report: RollingValidationReport) -> str:
    lines = [
        "# Rolling Paper/Demo Validation Report",
        "",
        "Framework implemented; validation is not completed.",
        "Records are local paper/demo research infrastructure only, not trade recommendations.",
        "",
        f"- record_type: {report.record_type}",
        f"- research_use: {report.research_use}",
        f"- framework_status: {report.framework_status}",
        f"- validation_completed: {report.validation_completed}",
        f"- as_of_date: {report.as_of_date}",
        f"- input_source: {report.input_source}",
        "",
        "## Private-Live Prerequisites Still Unmet",
        "",
    ]
    lines.extend(f"- {item}" for item in report.private_live_prerequisites_unmet)
    lines.extend(["", "## Windows", ""])
    for window in report.windows:
        lines.extend(
            [
                f"### {window.window_days}-day window",
                "",
                f"- start_date: {window.start_date}",
                f"- end_date: {window.end_date}",
                f"- candidate_count: {window.candidate_count}",
                f"- paper_candidate_count: {window.paper_candidate_count}",
                f"- demo_order_count: {window.demo_order_count}",
                f"- fill_success_rate: {window.fill_success_rate}",
                f"- partial_fill_rate: {window.partial_fill_rate}",
                f"- failed_leg_incident_count: {window.failed_leg_incident_count}",
                f"- gross_edge: {window.gross_edge}",
                f"- net_edge_after_cost: {window.net_edge_after_cost}",
                f"- paper_pnl: {window.paper_pnl}",
                f"- demo_pnl: {window.demo_pnl}",
                f"- max_drawdown: {window.max_drawdown}",
                (
                    "- reconciliation_mismatch_count: "
                    f"{window.reconciliation_mismatch_count}"
                ),
                f"- data_gap_count: {window.data_gap_count}",
                f"- kill_switch_event_count: {window.kill_switch_event_count}",
                (
                    "- false_positive_style_rejection_count: "
                    f"{window.false_positive_style_rejection_count}"
                ),
                f"- undated_record_count: {window.undated_record_count}",
                "",
            ]
        )
    return "\n".join(lines)


def _build_window(
    records: Sequence[Mapping[str, object]],
    *,
    as_of: date,
    window_days: int,
) -> RollingValidationWindow:
    start = as_of - timedelta(days=window_days - 1)
    window_records = tuple(
        record for record in records if _record_in_window(record, start=start, end=as_of)
    )
    demo_orders = sum(_demo_order_count(record) for record in window_records)
    reconciled_demo_orders = sum(_reconciled_demo_order_count(record) for record in window_records)
    fill_denominator = demo_orders or reconciled_demo_orders
    full_fills = sum(_optional_int_field(record, "full_fill_count") for record in window_records)
    partial_fills = sum(
        _optional_int_field(record, "partial_fill_count") for record in window_records
    )
    pnl_points = _pnl_points(window_records, start=start)
    return RollingValidationWindow(
        window_days=window_days,
        start_date=start.isoformat(),
        end_date=as_of.isoformat(),
        candidate_count=sum(
            _record_type(record) == "offline_complement_research_candidate"
            for record in window_records
        ),
        paper_candidate_count=sum(
            _record_type(record) == "offline_complement_research_candidate"
            and record.get("decision") == "paper_candidate"
            for record in window_records
        ),
        demo_order_count=demo_orders,
        fill_success_rate=_rate(full_fills, fill_denominator),
        partial_fill_rate=_rate(partial_fills, fill_denominator),
        failed_leg_incident_count=sum(
            _failed_leg_incident_count(record) for record in window_records
        ),
        gross_edge=sum((_gross_edge(record) for record in window_records), ZERO),
        net_edge_after_cost=sum(
            (_net_edge_after_cost(record) for record in window_records),
            ZERO,
        ),
        paper_pnl=sum((_paper_pnl(record) for record in window_records), ZERO),
        demo_pnl=sum((_demo_pnl(record) for record in window_records), ZERO),
        max_drawdown=_max_drawdown(pnl_points),
        reconciliation_mismatch_count=sum(
            _reconciliation_mismatch_count(record) for record in window_records
        ),
        data_gap_count=sum(_data_gap_count(record) for record in window_records),
        kill_switch_event_count=sum(
            _kill_switch_event_count(record) for record in window_records
        ),
        false_positive_style_rejection_count=sum(
            _false_positive_style_rejection_count(record) for record in window_records
        ),
        undated_record_count=sum(_record_date(record) is None for record in window_records),
    )


def _unmet_prerequisites(
    windows: Sequence[RollingValidationWindow],
    *,
    live_readonly_data_days: int,
    paper_history_days: int,
    fee_slippage_assumptions_validated: bool,
    legal_platform_review_complete: bool,
) -> tuple[str, ...]:
    items = []
    if live_readonly_data_days < 90:
        items.append("missing real 30-90 day live-readonly data")
    if paper_history_days < 30:
        items.append("missing 30+ day paper trading history")
    if any(window.reconciliation_mismatch_count > 0 for window in windows):
        items.append("unresolved reconciliation mismatch status")
    if not fee_slippage_assumptions_validated:
        items.append("unvalidated fee/slippage assumptions")
    if not legal_platform_review_complete:
        items.append("missing legal/platform review")
    return tuple(items)


def _record_in_window(record: Mapping[str, object], *, start: date, end: date) -> bool:
    record_date = _record_date(record)
    return record_date is None or start <= record_date <= end


def _record_date(record: Mapping[str, object]) -> date | None:
    for field_name in (
        "report_date",
        "observed_at",
        "timestamp",
        "created_at",
        "submitted_at",
        "resolved_at",
        "occurred_at",
        "recorded_at",
        "date",
    ):
        value = record.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            msg = f"{field_name} must be a date or datetime string"
            raise ValueError(msg)
        return _parse_date_label(value)
    return None


def _parse_date_label(value: str) -> date:
    if not value:
        msg = "date label is required"
        raise ValueError(msg)
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        msg = f"invalid date label: {value}"
        raise ValueError(msg) from exc


def _record_type(record: Mapping[str, object]) -> str:
    return _optional_str(record, "record_type")


def _optional_str(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if value is None:
        return ""
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ValueError(msg)
    return value


def _demo_order_count(record: Mapping[str, object]) -> int:
    if _record_type(record) != "kalshi_demo_submission_preview":
        return 0
    if record.get("dry_run") is not False:
        return 0
    previews = record.get("request_previews", ())
    if not isinstance(previews, Sequence) or isinstance(previews, str | bytes | bytearray):
        msg = "request_previews must be a list"
        raise ValueError(msg)
    return len(previews)


def _reconciled_demo_order_count(record: Mapping[str, object]) -> int:
    if _record_type(record) != "kalshi_demo_reconciliation_state":
        return 0
    orders = record.get("orders", ())
    if not isinstance(orders, Sequence) or isinstance(orders, str | bytes | bytearray):
        msg = "orders must be a list"
        raise ValueError(msg)
    return len(orders)


def _failed_leg_incident_count(record: Mapping[str, object]) -> int:
    if "failed_leg_incident_count" in record:
        return _int_field(record, "failed_leg_incident_count")
    if _record_type(record) == "offline_taker_fill_simulation":
        return int(_decimal_field(record, "failed_leg_quantity") > ZERO)
    return 0


def _gross_edge(record: Mapping[str, object]) -> Decimal:
    if "gross_edge" in record:
        return _decimal_field(record, "gross_edge")
    if "total_estimated_gross_edge" in record:
        return _decimal_field(record, "total_estimated_gross_edge")
    if _record_type(record) == "offline_complement_research_candidate":
        return _decimal_field(record, "gross_edge_per_contract") * _decimal_field(
            record,
            "candidate_size",
        )
    return ZERO


def _net_edge_after_cost(record: Mapping[str, object]) -> Decimal:
    for field_name in (
        "net_edge_after_cost",
        "total_estimated_net_edge",
        "simulated_total_net_edge",
    ):
        if field_name in record:
            return _decimal_field(record, field_name)
    return ZERO


def _paper_pnl(record: Mapping[str, object]) -> Decimal:
    for field_name in ("paper_pnl", "realized_net_pnl"):
        if field_name in record:
            return _decimal_field(record, field_name)
    return ZERO


def _demo_pnl(record: Mapping[str, object]) -> Decimal:
    if "demo_pnl" in record:
        return _decimal_field(record, "demo_pnl")
    return ZERO


def _reconciliation_mismatch_count(record: Mapping[str, object]) -> int:
    if "mismatch_count" in record:
        return _int_field(record, "mismatch_count")
    if "reconciliation_mismatch_count" in record:
        return _int_field(record, "reconciliation_mismatch_count")
    return 0


def _data_gap_count(record: Mapping[str, object]) -> int:
    count = _int_field(record, "gap_count") if "gap_count" in record else 0
    flags = set(_str_sequence(record.get("flags", ()))) | set(
        _str_sequence(record.get("data_quality_flags", ()))
    )
    if "sequence_gap" in flags or "data_gap" in flags:
        count += 1
    return count


def _kill_switch_event_count(record: Mapping[str, object]) -> int:
    if "kill_switch_event_count" in record:
        return _int_field(record, "kill_switch_event_count")
    reasons = set(_str_sequence(record.get("reasons", ())))
    if _record_type(record) == "kill_switch_event" or "kill_switch_active" in reasons:
        return 1
    return 0


def _false_positive_style_rejection_count(record: Mapping[str, object]) -> int:
    if record.get("false_positive_style_rejection") is True:
        return 1
    if record.get("rejection_outcome") == "false_positive_style":
        return 1
    return 0


def _pnl_points(
    records: Sequence[Mapping[str, object]],
    *,
    start: date,
) -> tuple[tuple[date, Decimal], ...]:
    points = []
    for record in records:
        pnl = _paper_pnl(record) + _demo_pnl(record)
        if pnl != ZERO:
            points.append((_record_date(record) or start, pnl))
    return tuple(sorted(points, key=lambda item: item[0]))


def _max_drawdown(points: Sequence[tuple[date, Decimal]]) -> Decimal:
    peak = ZERO
    equity = ZERO
    drawdown = ZERO
    for _, pnl in points:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return ZERO
    return Decimal(numerator) / Decimal(denominator)


def _int_field(record: Mapping[str, object], field_name: str) -> int:
    value = record.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = f"{field_name} must be a non-negative integer"
        raise ValueError(msg)
    return value


def _optional_int_field(record: Mapping[str, object], field_name: str) -> int:
    if field_name not in record:
        return 0
    return _int_field(record, field_name)


def _decimal_field(record: Mapping[str, object], field_name: str) -> Decimal:
    value: Any = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string"
        raise ValueError(msg)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ValueError(msg) from exc


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
