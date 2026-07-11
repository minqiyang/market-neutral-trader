"""Read-only V2 terminal monitor over local research artifacts."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from edmn_trader.adapters.kalshi.ws_runtime import (
    D2_RUNTIME_SCHEMA_VERSION,
    validate_d2_runtime_artifacts,
)
from edmn_trader.data.evidence_policy import V2_THRESHOLD_POLICY
from edmn_trader.data.payload_safety import (
    validate_no_private_account_payload,
    validate_no_secret_payload,
)
from edmn_trader.execution.private_live_gate import attempt_private_live_execution

MonitorFormat = Literal["json", "markdown", "table"]
SUMMARY_FILES = (
    "run_info.json",
    "recorder_summary.json",
    "replay_summary.json",
    "venue_status.json",
    "paper_summary.json",
    "risk_summary.json",
    "reconciliation_summary.json",
    "validation_summary.json",
    "evidence_summary.json",
    "campaign_summary.json",
    "campaign_validation.json",
)
SECRET_KEYS = (
    "authorization",
    "credential",
    "key",
    "pass",
    "private_key",
    "secret",
    "signature",
    "token",
)
STALE_SECONDS = 15 * 60
RUNNING_CAMPAIGN_STATUSES = {"running", "websocket_campaign_running"}
COMPLETED_WS_CAMPAIGN_STATUSES = {"websocket_campaign_complete", "websocket_smoke_complete"}


def build_monitor_snapshot(input_dir: Path, *, now: datetime | None = None) -> dict[str, object]:
    """Build one fail-safe operator snapshot from local files only."""

    generated_at = now or datetime.now(UTC)
    warnings: list[str] = []
    records = _read_records(input_dir, warnings)
    summaries = _read_summaries(input_dir, warnings) if input_dir.exists() else {}
    summaries = _refresh_d2_validation(input_dir, summaries, warnings)
    live_gate = attempt_private_live_execution().to_record()

    run_info = _run_info(input_dir, generated_at, summaries)
    venues = _venue_rows(records, summaries, generated_at, warnings)
    positions = _position_rows(records, summaries)
    orders = _order_rows(records)
    candidates = _candidate_rows(records)
    risk = _risk_status(records, summaries)
    reconciliation = _reconciliation_status(records, summaries)
    evidence = _evidence_status(records, summaries)
    campaign = _campaign_status(summaries, generated_at)
    if campaign.get("market_warning"):
        warnings.append(str(campaign["market_warning"]))
    data_status = _data_status(records, summaries, venues)
    health = _health(
        input_dir=input_dir,
        records=records,
        summaries=summaries,
        warnings=warnings,
        risk=risk,
        reconciliation=reconciliation,
        data_status=data_status,
        campaign_snapshot=campaign,
    )

    return {
        "run_info": {
            **run_info,
            "health": health,
            "live_gate": {
                "status": live_gate["status"],
                "production_trading_enabled": live_gate["production_trading_enabled"],
                "strict_verdict": "STRICT NO-GO",
            },
            "trading_mode": "READ_ONLY/PAPER_ONLY",
            "warnings": warnings,
        },
        "venue_status": venues,
        "data_status": data_status,
        "positions": positions,
        "orders": orders,
        "candidates": candidates,
        "risk": risk,
        "reconciliation": reconciliation,
        "evidence": evidence,
        "campaign": campaign,
        "system": {
            "mode": "read_only_monitor",
            "input_dir": str(input_dir),
            "generated_at_utc": generated_at.isoformat(),
            "health": health,
            "live_gate_status": live_gate["status"],
            "warnings": warnings,
        },
        "validation": _validation_status(records, summaries),
    }


def _refresh_d2_validation(
    input_dir: Path,
    summaries: Mapping[str, Mapping[str, object]],
    warnings: list[str],
) -> dict[str, dict[str, object]]:
    campaign = summaries.get("campaign_summary.json", {})
    if not campaign and any(
        warning.startswith("CORRUPT_SUMMARY: campaign_summary.json")
        for warning in warnings
    ):
        warnings.append("D2_RUNTIME_VALIDATION_FAILED: campaign summary is unavailable")
        refreshed = dict(summaries)
        refreshed["campaign_summary.json"] = {
            "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "status": "d2_runtime_corrupt",
        }
        refreshed["campaign_validation.json"] = {
            **summaries.get("campaign_validation.json", {}),
            "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "status": "fail",
            "overall_evidence_classification": "FAIL",
            "failures": ["campaign_summary.json is unavailable or unsafe"],
            "strict_verdict": "STRICT NO-GO",
        }
        return refreshed
    if (
        campaign.get("runtime_schema_version") != D2_RUNTIME_SCHEMA_VERSION
        or campaign.get("status") == "d2_runtime_running"
    ):
        if campaign.get("status") == "d2_runtime_running":
            failures: list[str] = []
            try:
                validate_no_secret_payload(campaign, path="campaign_summary")
                validate_no_private_account_payload(campaign, path="campaign_summary")
            except ValueError as exc:
                failures.append(str(exc))
            for field, expected in (
                ("live_gate_status", "disabled"),
                ("production_trading_enabled", False),
                ("executable_order_intent", False),
                ("production_endpoint_used", False),
                ("submit_attempts", 0),
                ("real_money_trading", False),
                ("replay_qualified", False),
            ):
                if campaign.get(field) != expected:
                    failures.append(f"running campaign safety field invalid: {field}")
            if failures:
                warnings.extend(
                    f"CORRUPT_SUMMARY: campaign_summary.json: {failure}" for failure in failures
                )
                refreshed = dict(summaries)
                refreshed["campaign_summary.json"] = {
                    "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
                    "status": "d2_runtime_corrupt",
                }
                refreshed["campaign_validation.json"] = {
                    **summaries.get("campaign_validation.json", {}),
                    "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
                    "status": "fail",
                    "overall_evidence_classification": "FAIL",
                    "failures": failures,
                    "strict_verdict": "STRICT NO-GO",
                }
                return refreshed
        return dict(summaries)
    try:
        validation = validate_d2_runtime_artifacts(input_dir, persist=False)
    except Exception as exc:  # The monitor must fail closed at this boundary.
        validation = {
            "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "status": "fail",
            "overall_evidence_classification": "FAIL",
            "failures": [f"runtime validation raised {type(exc).__name__}: {exc}"],
            "strict_verdict": "STRICT NO-GO",
        }
    if validation.get("status") in {"fail", "blocked"}:
        warnings.append("D2_RUNTIME_VALIDATION_FAILED: persisted evidence was revalidated")
    refreshed = dict(summaries)
    refreshed["campaign_validation.json"] = {
        **summaries.get("campaign_validation.json", {}),
        **validation,
    }
    return refreshed


def render_snapshot(
    snapshot: Mapping[str, object],
    output_format: MonitorFormat,
    *,
    include_evidence: bool = False,
) -> str:
    if output_format == "json":
        return json.dumps(snapshot, indent=2, sort_keys=True)
    if output_format == "markdown":
        return _render_markdown(snapshot, include_evidence=include_evidence)
    return _render_table(snapshot, include_evidence=include_evidence)


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    while True:
        snapshot = build_monitor_snapshot(args.input_dir)
        rendered = render_snapshot(
            snapshot,
            args.format,
            include_evidence=args.include_evidence,
        )
        if args.export_json:
            args.export_json.parent.mkdir(parents=True, exist_ok=True)
            args.export_json.write_text(
                json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(rendered)
        if not args.watch:
            return
        time.sleep(args.interval)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only V2 terminal monitor")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Render one snapshot and exit")
    mode.add_argument("--watch", action="store_true", help="Refresh until interrupted")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "markdown", "table"), default="table")
    parser.add_argument("--export-json", type=Path)
    parser.add_argument(
        "--include-evidence",
        action="store_true",
        help="Include Layer 0-7 evidence checklist status in table/markdown output.",
    )
    return parser


def _read_summaries(input_dir: Path, warnings: list[str]) -> dict[str, dict[str, object]]:
    summaries: dict[str, dict[str, object]] = {}
    for name in SUMMARY_FILES:
        try:
            path = _safe_input_path(input_dir, name)
            if not path.exists():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            warnings.append(f"CORRUPT_SUMMARY: {name}: {exc}")
            continue
        if isinstance(payload, dict):
            if name == "campaign_summary.json":
                try:
                    validate_no_secret_payload(payload, path=name)
                    validate_no_private_account_payload(payload, path=name)
                except ValueError as exc:
                    warnings.append(f"CORRUPT_SUMMARY: {name}: {exc}")
                    continue
            summaries[name] = _redact_mapping(payload)
        else:
            warnings.append(f"CORRUPT_SUMMARY: {name}: expected JSON object")
    return summaries


def _safe_input_path(input_dir: Path, name: str) -> Path:
    root = input_dir.resolve()
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("summary path must be relative to the input directory")
    candidate = root / relative
    resolved = candidate.resolve(strict=False)
    if resolved == root or root not in resolved.parents:
        raise ValueError("summary path escapes the input directory")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"summary path must not be a symlink: {name}")
    return candidate


def _read_records(input_dir: Path, warnings: list[str]) -> list[dict[str, object]]:
    if not input_dir.exists():
        return []
    records: list[dict[str, object]] = []
    for candidate in sorted(input_dir.glob("*.jsonl")):
        try:
            path = _safe_input_path(input_dir, candidate.name)
        except (OSError, ValueError) as exc:
            warnings.append(f"CORRUPT_JSONL: {candidate.name}: {exc}")
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            warnings.append(f"CORRUPT_JSONL: {path.name}: {exc}")
            continue
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(f"CORRUPT_JSONL: {path.name}:{index}: {exc.msg}")
                continue
            if isinstance(payload, dict):
                records.append(_redact_mapping(payload))
            else:
                warnings.append(f"CORRUPT_JSONL: {path.name}:{index}: expected JSON object")
    return records


def _run_info(
    input_dir: Path,
    generated_at: datetime,
    summaries: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    run_info = summaries.get("run_info.json", {})
    return {
        "generated_at_utc": str(run_info.get("generated_at_utc") or generated_at.isoformat()),
        "input_dir": str(input_dir),
        "schema_version": str(run_info.get("schema_version") or "v2.monitor.v1"),
    }


def _venue_rows(
    records: list[dict[str, object]],
    summaries: Mapping[str, Mapping[str, object]],
    generated_at: datetime,
    warnings: list[str],
) -> list[dict[str, object]]:
    venue_summary = summaries.get("venue_status.json", {})
    source = _as_list(venue_summary.get("venues"))
    if not source and venue_summary:
        source = [venue_summary]
    if not source:
        campaign = summaries.get("campaign_summary.json", {})
        validation = summaries.get("campaign_validation.json", {})
        venue = (
            campaign.get("venue")
            or summaries.get("recorder_summary.json", {}).get("venue")
            or _first_value(records, "venue")
        )
        if venue:
            source = [
                {
                    "venue": venue,
                    "mode": "read_only",
                    "connectivity": "unknown",
                    "last_event_ts": campaign.get("last_event_time")
                    or validation.get("last_event_time")
                    or _last_value(records, "received_at")
                    or _last_value(records, "observed_at"),
                    "gap_count": campaign.get("gap_count")
                    or validation.get("gap_count")
                    or _count_flag(records, "sequence_gap"),
                    "warning_count": 0,
                }
            ]

    rows: list[dict[str, object]] = []
    for item in source:
        if not isinstance(item, Mapping):
            warnings.append("CORRUPT_SUMMARY: venue_status.json: venue row must be object")
            continue
        row = {
            "venue": item.get("venue"),
            "mode": item.get("mode") or "read_only",
            "connectivity": item.get("connectivity") or "unknown",
            "last_event_ts": item.get("last_event_ts") or item.get("last_event_time"),
            "data_staleness_seconds": item.get("data_staleness_seconds"),
            "gap_count": item.get("gap_count") or 0,
            "warning_count": item.get("warning_count") or 0,
        }
        if row["data_staleness_seconds"] is None:
            row["data_staleness_seconds"] = _staleness_seconds(row["last_event_ts"], generated_at)
        campaign = summaries.get("campaign_summary.json", {})
        completed_campaign = _completed_bounded_campaign(campaign) or _completed_ws_canary_ok(
            summaries
        )
        if _is_stale(row["data_staleness_seconds"]) and not completed_campaign:
            warnings.append(f"STALE_DATA: {row['venue']} staleness={row['data_staleness_seconds']}")
        rows.append(row)
    return rows


def _data_status(
    records: list[dict[str, object]],
    summaries: Mapping[str, Mapping[str, object]],
    venues: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    recorder = summaries.get("recorder_summary.json", {})
    replay = summaries.get("replay_summary.json", {})
    campaign = summaries.get("campaign_summary.json", {})
    events = [record for record in records if _is_market_data_record(record)]
    completed_campaign = _completed_bounded_campaign(campaign) or _completed_ws_canary_ok(summaries)
    stale_status = recorder.get("stale_status") or (
        "COMPLETE"
        if completed_campaign
        else (
            "STALE"
            if any(_is_stale(row.get("data_staleness_seconds")) for row in venues)
            else _flag_status(records, "stale")
        )
    )
    return {
        "venue": recorder.get("venue") or _first_mapping_value(venues, "venue"),
        "market_count": recorder.get("market_count")
        or replay.get("market_count")
        or _count_distinct(events, "market_id"),
        "event_count": recorder.get("event_count") or len(events),
        "last_event_time": recorder.get("ended_at_utc")
        or _first_mapping_value(venues, "last_event_ts")
        or _last_value(events, "observed_at"),
        "stale_status": stale_status,
        "gap_count": recorder.get("gap_count")
        or replay.get("gap_count")
        or sum(_int_or_zero(row.get("gap_count")) for row in venues)
        or _count_flag(records, "sequence_gap"),
        "reconnect_count": recorder.get("reconnect_count"),
        "book_rebuild_status": replay.get("book_rebuild_status") or replay.get("status"),
    }


def _candidate_rows(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for record in records:
        if record.get("record_type") != "offline_complement_research_candidate":
            continue
        rows.append(
            {
                "venue": record.get("venue"),
                "market_ticker": record.get("market_ticker") or record.get("market_id"),
                "strategy": record.get("strategy") or "same_market_complement",
                "edge_before_fees": record.get("gross_edge_per_contract")
                or record.get("gross_edge"),
                "expected_fees": record.get("estimated_fee_per_contract")
                or record.get("fee_estimate"),
                "edge_after_fees": record.get("net_edge_per_contract") or record.get("net_edge"),
                "liquidity": record.get("candidate_size"),
                "stale": "stale_book" in str(record.get("data_quality_flags", ())),
                "rejected_reason": record.get("rejection_reasons")
                or record.get("rejection_reason"),
                "risk_decision": record.get("decision"),
            }
        )
    return rows


def _position_rows(
    records: list[dict[str, object]],
    summaries: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    paper = summaries.get("paper_summary.json", {})
    positions_summary = _as_list(paper.get("positions"))
    source = positions_summary or _as_list(
        _first_record(records, "paper_ledger_state", {}).get("positions")
    )
    if not source:
        source = [
            record
            for record in records
            if record.get("record_type") in {"paper_position", "market_position"}
        ]
    rows = []
    for item in source:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "venue": item.get("venue") or "paper",
                "market_id": item.get("market_id") or item.get("market") or item.get("proposal_id"),
                "market_ticker": item.get("market_ticker")
                or item.get("market")
                or item.get("proposal_id"),
                "market_title": item.get("market_title"),
                "currency": item.get("currency") or "USD",
                "instrument_type": item.get("instrument_type")
                or item.get("type")
                or "binary_prediction",
                "side": item.get("side"),
                "quantity": item.get("quantity"),
                "average_price": item.get("average_price"),
                "mark_price": item.get("mark_price"),
                "notional": item.get("notional"),
                "exposure": item.get("exposure") or item.get("notional"),
                "realized_pnl": item.get("realized_pnl"),
                "unrealized_pnl": item.get("unrealized_pnl"),
                "fees": item.get("fees") or item.get("fees_paid"),
                "source": item.get("source") or "paper_ledger",
            }
        )
    return rows


def _order_rows(records: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    seen: set[str] = set()
    for record in records:
        record_type = record.get("record_type")
        if record_type not in {
            "paper_complement_order_proposal",
            "kalshi_demo_submission_preview",
            "open_order",
            "proposed_order",
        }:
            continue
        order_id = record.get("order_id") or record.get("proposal_id")
        dedupe_key = str(order_id) if order_id else json.dumps(record, sort_keys=True)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        legs = _as_list(record.get("legs"))
        first_leg = legs[0] if legs and isinstance(legs[0], Mapping) else {}
        price = record.get("price") or record.get("limit_price") or first_leg.get("limit_price")
        quantity = record.get("quantity") or record.get("size") or first_leg.get("quantity")
        rows.append(
            {
                "order_id": order_id,
                "proposal_hash": record.get("proposal_hash") or record.get("candidate_hash"),
                "venue": record.get("venue") or "kalshi_demo",
                "market_ticker": record.get("market_ticker") or record.get("market_id"),
                "side": record.get("side") or first_leg.get("side"),
                "action": record.get("action") or "paper_propose",
                "price": price,
                "quantity": quantity,
                "notional": record.get("notional") or _decimal_product(price, quantity),
                "status": record.get("status") or "paper",
                "reason": record.get("rejection_reason") or record.get("reason"),
                "approval_required": _approval_required(record),
                "risk_decision": record.get("risk_decision")
                or _nested(record, "risk_preview", "reasons"),
                "source": record_type,
            }
        )
    return rows


def _risk_status(
    records: list[dict[str, object]],
    summaries: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    risk = summaries.get("risk_summary.json", {})
    decision = _first_record(records, "complement_risk_decision_v2")
    reasons = _as_list(risk.get("warnings")) + _as_list(decision.get("reasons"))
    kill_switch = risk.get("kill_switch")
    if kill_switch is None:
        kill_switch = risk.get("kill_switch_status") == "active" or "kill_switch_active" in reasons
    return {
        "kill_switch": bool(kill_switch),
        "manual_approval_required": bool(
            risk.get("manual_approval_required")
            if "manual_approval_required" in risk
            else decision.get("manual_approval_required", True)
        ),
        "stale_data": bool(risk.get("stale_data") or "stale_data" in reasons),
        "data_gap": bool(risk.get("data_gap") or "data_gap" in reasons),
        "fee_missing": bool(risk.get("fee_missing") or "missing_fee_model" in reasons),
        "edge_insufficient": bool(
            risk.get("edge_insufficient") or "insufficient_net_edge" in reasons
        ),
        "exposure_limit": bool(
            risk.get("exposure_limit") or "exposure_limit_breach" in reasons
        ),
        "daily_loss_limit": bool(
            risk.get("daily_loss_limit") or "daily_loss_limit_breach" in reasons
        ),
        "reconciliation_mismatch": bool(
            risk.get("reconciliation_mismatch") or "reconciliation_mismatch" in reasons
        ),
        "decision": risk.get("decision") or decision.get("decision"),
        "warnings": reasons,
    }


def _reconciliation_status(
    records: list[dict[str, object]],
    summaries: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    summary = summaries.get("reconciliation_summary.json", {})
    ledger = _first_record(records, "paper_ledger_state")
    demo = _first_record(records, "kalshi_demo_reconciliation_state")
    mismatch_count = (
        summary.get("mismatch_count")
        or ledger.get("reconciliation_mismatch_count")
        or demo.get("mismatch_count")
        or 0
    )
    return {
        "status": summary.get("status")
        or ("mismatch" if _int_or_zero(mismatch_count) else "clean"),
        "mismatch_count": mismatch_count,
        "last_reconciled_at": summary.get("last_reconciled_at"),
        "unresolved_items": summary.get("unresolved_items") or [],
    }


def _evidence_status(
    records: list[dict[str, object]],
    summaries: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    campaign = summaries.get("campaign_summary.json", {})
    if campaign.get("runtime_schema_version") == "edmn.kalshi.ws.runtime.v2":
        dimensions = campaign.get("independent_evidence_classifications")
        return {
            "runtime_schema_version": campaign.get("runtime_schema_version"),
            "overall_classification": campaign.get("overall_evidence_classification"),
            "dimensions": dict(dimensions) if isinstance(dimensions, Mapping) else {},
            "artifact_integrity_summary": campaign.get("artifact_integrity_summary"),
            "sequence_summaries": campaign.get("sequence_summaries") or [],
            "rebuild_summaries": campaign.get("rebuild_summaries") or [],
            "freshness_dimensions": campaign.get("freshness_dimensions") or {},
            "replay_qualified": False,
            "strict_verdict": "STRICT NO-GO",
        }
    summary = summaries.get("evidence_summary.json", {})
    layers = summary.get("layers")
    if not isinstance(layers, Mapping):
        layers = {
            "Layer 0 schema/audit": "pass" if records else "missing",
            "Layer 1 recorder": "pass"
            if any(_is_market_data_record(record) for record in records)
            else "missing",
            "Layer 2 replay/simulator": "pass"
            if _has_record(records, "offline_taker_fill_simulation")
            or any(_is_replay_frame(record) for record in records)
            else "missing",
            "Layer 3 ledger/reconciliation": "pass"
            if _has_record(records, "paper_ledger_state")
            else "missing",
            "Layer 4 risk/manual approval/kill switch": "pass"
            if _has_record(records, "complement_risk_decision_v2")
            else "missing",
            "Layer 5 demo/paper authenticated execution": "mocked/demo-only",
            "Layer 6 private live gate": "disabled/fail-closed",
            "Layer 7 monitor/reporting": "pass",
        }
    missing_required = summary.get("missing_required_artifacts")
    if not isinstance(missing_required, list):
        missing_required = [
            "30-90 day read-only dataset",
            "30+ day paper/demo history",
            "fee/slippage validation",
            "zero unexplained reconciliation mismatch",
            "kill-switch/manual approval drill",
            "legal/platform review",
        ]
    return {
        "recorder_days": summary.get("recorder_days", 0),
        "paper_days": summary.get("paper_days", 0),
        "last_validation_report": summary.get("last_validation_report"),
        "private_artifacts_present": bool(summary.get("private_artifacts_present", False)),
        "missing_required_artifacts": missing_required,
        "layers": dict(layers),
        "strict_verdict": "STRICT NO-GO",
    }


def _validation_status(
    records: list[dict[str, object]],
    summaries: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    campaign_validation = summaries.get("campaign_validation.json", {})
    if campaign_validation.get("runtime_schema_version") == "edmn.kalshi.ws.runtime.v2":
        return {
            "runtime_schema_version": campaign_validation.get("runtime_schema_version"),
            "status": campaign_validation.get("status"),
            "overall_evidence_classification": campaign_validation.get(
                "overall_evidence_classification"
            ),
            "artifact_integrity": campaign_validation.get("artifact_integrity"),
            "failures": campaign_validation.get("failures") or [],
        }
    validation = summaries.get("validation_summary.json", {})
    daily = _first_record(records, "daily_validation_report")
    return {
        "one_day": validation.get("one_day") or daily.get("report_date"),
        "seven_day": validation.get("seven_day"),
        "thirty_day": validation.get("thirty_day"),
        "ninety_day": validation.get("ninety_day"),
        "reconciliation_mismatch_count": validation.get("reconciliation_mismatch_count")
        or daily.get("reconciliation_mismatch_count"),
        "fee_slippage_model_status": validation.get("fee_slippage_model_status"),
        "paper_trade_count": validation.get("paper_trade_count")
        or daily.get("paper_outcome_count"),
        "blocked_trade_count": validation.get("blocked_trade_count") or daily.get("reject_count"),
    }


def _campaign_status(
    summaries: Mapping[str, Mapping[str, object]],
    generated_at: datetime,
) -> dict[str, object]:
    campaign = _refresh_running_freshness(
        summaries.get("campaign_summary.json", {}), generated_at
    )
    validation = summaries.get("campaign_validation.json", {})
    source_type = campaign.get("source_type") or validation.get("source_type")
    event_count = campaign.get("event_count") or validation.get("event_count") or 0
    validation_status = validation.get("status") or campaign.get("validation_status")
    submit_attempts = campaign.get("submit_attempts", campaign.get("submit_attempt_count", 0))
    completion_status = _campaign_completion_status(campaign, validation, generated_at)
    market_status = campaign.get("market_status") or campaign.get("status_at_launch")
    close_time = campaign.get("close_time") or campaign.get("expected_expiration")
    market_closed = _is_closed_market_status(market_status)
    return {
        "runtime_schema_version": campaign.get("runtime_schema_version"),
        "campaign_id": campaign.get("campaign_id"),
        "status": _campaign_monitor_status(campaign, validation),
        "completion_status": completion_status,
        "run_status": campaign.get("status"),
        "source_type": source_type,
        "venue": campaign.get("venue"),
        "market": campaign.get("market"),
        "market_tickers": campaign.get("market_tickers") or [],
        "subscribed_market_ticker": campaign.get("market_ticker") or campaign.get("market"),
        "event_ticker": campaign.get("event_ticker"),
        "market_title": campaign.get("title") or campaign.get("name"),
        "market_status": market_status,
        "close_time": close_time,
        "expected_expiration": campaign.get("expected_expiration"),
        "time_to_close_at_launch_seconds": campaign.get("time_to_close_at_launch_seconds"),
        "time_since_close_seconds": _seconds_since(close_time, generated_at)
        if market_closed
        else None,
        "market_lifecycle_status": validation.get("market_lifecycle_status")
        or campaign.get("market_lifecycle_status")
        or ("CLOSED_OR_FINALIZED" if market_closed else "UNKNOWN"),
        "market_evidence_valid": validation.get("campaign_evidence_valid", not market_closed),
        "evidence_validity_classification": validation.get(
            "evidence_validity_classification"
        ),
        "lifecycle_deadline": campaign.get("lifecycle_deadline"),
        "campaign_required_end_utc": campaign.get("campaign_required_end_utc"),
        "can_close_early": campaign.get("can_close_early"),
        "event_category": campaign.get("event_category"),
        "market_warning": "MARKET_CLOSED_OR_FINALIZED" if market_closed else None,
        "selection_gate_result": campaign.get("selection_gate_result"),
        "selection_gate_rejection_reason": campaign.get("selection_gate_rejection_reason"),
        "supervisor_liveness_status": campaign.get("supervisor_liveness_status") or "UNKNOWN",
        "campaign_process_liveness_status": campaign.get("campaign_process_liveness_status")
        or "UNKNOWN",
        "websocket_message_freshness_status": campaign.get("websocket_message_freshness_status")
        or "UNKNOWN",
        "exchange_heartbeat_status": campaign.get("exchange_heartbeat_status") or "UNKNOWN",
        "market_count": campaign.get("market_count"),
        "duration_seconds": campaign.get("duration_seconds"),
        "configured_duration_seconds": campaign.get("configured_duration_seconds"),
        "actual_elapsed_seconds": campaign.get("actual_elapsed_seconds"),
        "connected_elapsed_seconds": campaign.get("connected_elapsed_seconds"),
        "connection_coverage": campaign.get("connection_coverage"),
        "threshold_policy_version": campaign.get("threshold_policy_version"),
        "freshness_dimensions": campaign.get("freshness_dimensions"),
        "artifact_integrity_summary": campaign.get("artifact_integrity_summary"),
        "independent_evidence_classifications": campaign.get(
            "independent_evidence_classifications"
        ),
        "sequence_summaries": campaign.get("sequence_summaries") or [],
        "rebuild_summaries": campaign.get("rebuild_summaries") or [],
        "event_count": event_count,
        "snapshot_count": campaign.get("snapshot_count") or validation.get("snapshot_count") or 0,
        "delta_count": campaign.get("delta_count") or validation.get("delta_count") or 0,
        "trade_count": campaign.get("trade_count") or validation.get("trade_count") or 0,
        "status_update_count": campaign.get("status_update_count")
        or validation.get("status_update_count")
        or 0,
        "heartbeat_count": campaign.get("heartbeat_count"),
        "disconnect_count": campaign.get("disconnect_count")
        or validation.get("disconnect_count")
        or 0,
        "reconnect_count": campaign.get("reconnect_count")
        or validation.get("reconnect_count")
        or 0,
        "gap_count": campaign.get("gap_count") or validation.get("gap_count") or 0,
        "last_event_time": campaign.get("last_event_time") or validation.get("last_event_time"),
        "stale_seconds": campaign.get("stale_seconds") or validation.get("stale_seconds"),
        "recorder_event_count": campaign.get("recorder_event_count"),
        "rebuild_frame_count": campaign.get("rebuild_frame_count"),
        "validation_status": validation_status,
        "evidence_classification": validation.get("evidence_classification")
        or campaign.get("evidence_classification"),
        "connection_established": campaign.get("connection_established"),
        "subscription_acknowledged": campaign.get("subscription_acknowledged"),
        "blocker_code": campaign.get("blocker_code") or validation.get("blocker_code"),
        "live_gate_status": campaign.get("live_gate_status"),
        "submit_attempts": submit_attempts,
        "submit_attempt_count": submit_attempts,
        "manifest_path": campaign.get("manifest_path"),
        "validation_report_path": campaign.get("validation_report_path"),
        "raw_event_path": campaign.get("raw_event_path"),
        "raw_data_path_redacted": campaign.get("raw_data_path_redacted"),
        "blocker": campaign.get("blocker") or validation.get("blocker"),
    }


def _refresh_running_freshness(
    source: Mapping[str, object],
    generated_at: datetime,
) -> dict[str, object]:
    campaign = dict(source)
    if campaign.get("status") != "d2_runtime_running":
        return campaign
    raw = campaign.get("freshness_dimensions")
    if not isinstance(raw, Mapping):
        return campaign
    freshness = dict(raw)
    elapsed = _staleness_seconds(freshness.get("evaluated_at_utc"), generated_at)
    if elapsed is not None:
        for field in (
            "transport_keepalive_age_seconds",
            "lifecycle_observation_age_seconds",
            "orderbook_event_quiet_interval_seconds",
        ):
            age = freshness.get(field)
            if isinstance(age, int | float) and not isinstance(age, bool):
                freshness[field] = int(age) + elapsed
    campaign["freshness_dimensions"] = freshness
    dimensions = campaign.get("independent_evidence_classifications")
    if isinstance(dimensions, Mapping):
        refreshed_dimensions = dict(dimensions)
        keepalive_age = freshness.get("transport_keepalive_age_seconds")
        if isinstance(keepalive_age, int | float) and keepalive_age > (
            V2_THRESHOLD_POLICY.maximum_transport_keepalive_age_seconds
        ):
            refreshed_dimensions["transport_keepalive"] = "FAIL"
        lifecycle_age = freshness.get("lifecycle_observation_age_seconds")
        if isinstance(lifecycle_age, int | float) and lifecycle_age > (
            V2_THRESHOLD_POLICY.maximum_lifecycle_age_seconds
        ):
            refreshed_dimensions["market_lifecycle_validity"] = "FAIL"
        campaign["independent_evidence_classifications"] = refreshed_dimensions
    orderbook_age = freshness.get("orderbook_event_quiet_interval_seconds")
    if isinstance(orderbook_age, int | float):
        campaign["websocket_message_freshness_status"] = (
            "QUIET_WARNING"
            if orderbook_age > V2_THRESHOLD_POLICY.orderbook_quiet_warning_seconds
            else "FRESH"
        )
    return campaign


def _campaign_monitor_status(
    campaign: Mapping[str, object],
    validation: Mapping[str, object],
) -> str | None:
    if not campaign.get("campaign_id"):
        return None
    if campaign.get("runtime_schema_version") == "edmn.kalshi.ws.runtime.v2":
        if campaign.get("blocker_code"):
            return (
                "WEBSOCKET_AUTH_BLOCKED"
                if campaign.get("blocker_code")
                in {"NO_WS_CREDENTIALS", "WS_CREDENTIAL_STORAGE_UNSAFE", "WS_AUTH_FAILED"}
                else "D2_RUNTIME_BLOCKED"
            )
        dimensions = campaign.get("independent_evidence_classifications")
        if isinstance(dimensions, Mapping) and any(
            dimensions.get(field) == "FAIL"
            for field in (
                "artifact_integrity",
                "transport_connectivity",
                "subscription_status",
                "rebuild_integrity",
                "market_lifecycle_validity",
                "transport_keepalive",
                "sequence_integrity",
                "duration_evidence",
                "process_liveness",
            )
        ):
            return "D2_RUNTIME_EVIDENCE_FAILED"
        if campaign.get("status") == "d2_runtime_running":
            return "D2_RUNTIME_RUNNING"
        return (
            "D2_RUNTIME_COMPLETE"
            if validation.get("status") == "pass"
            else "D2_RUNTIME_VALIDATION_FAILED"
        )
    if _is_closed_market_status(campaign.get("market_status") or campaign.get("status_at_launch")):
        return "MARKET_CLOSED_OR_FINALIZED"
    if (
        validation.get("evidence_validity_classification")
        == "CAMPAIGN_EVIDENCE_INVALID_MARKET_LIFECYCLE"
    ):
        return "MARKET_LIFECYCLE_INVALID"
    source_type = campaign.get("source_type") or validation.get("source_type")
    validation_status = validation.get("status") or campaign.get("validation_status")
    classification = validation.get("evidence_classification") or campaign.get(
        "evidence_classification"
    )
    if classification in {
        "NO_WS_CREDENTIALS",
        "WS_CREDENTIAL_STORAGE_UNSAFE",
        "WS_AUTH_FAILED",
        "LAYER1_WS_AUTH_BLOCKED",
    }:
        return "WEBSOCKET_AUTH_BLOCKED"
    event_count = _int_or_zero(campaign.get("event_count") or validation.get("event_count"))
    if event_count <= 0:
        return "NO_DATA"
    if source_type == "SYNTHETIC":
        return "SYNTHETIC_SMOKE"
    if source_type == "REST":
        return "REST_SMOKE"
    if source_type in {"WEBSOCKET_SNAPSHOT", "WEBSOCKET_DELTA"}:
        duration_seconds = _int_or_zero(campaign.get("duration_seconds"))
        if classification == "LAYER1_WS_CAMPAIGN_INCOMPLETE":
            return "CAMPAIGN_INCOMPLETE"
        if campaign.get("status") in RUNNING_CAMPAIGN_STATUSES:
            return "WEBSOCKET_CAMPAIGN_RUNNING"
        if (
            validation_status == "pass"
            and duration_seconds >= 604_800
            and campaign.get("status") == "websocket_campaign_complete"
            and classification == "LAYER1_WS_CAMPAIGN_PASS_7D"
        ):
            return "WEBSOCKET_CAMPAIGN_VALIDATED"
        if classification == "LAYER1_WS_DELTA_SMOKE_PASS":
            return "WEBSOCKET_DELTA_SMOKE"
        if classification == "LAYER1_WS_SNAPSHOT_ONLY_EXTENDED":
            return "WEBSOCKET_SNAPSHOT_EXTENDED"
        if classification == "LAYER1_WS_SNAPSHOT_SMOKE_PASS":
            return "WEBSOCKET_SNAPSHOT_SMOKE"
        return "NO_DATA"
    return "NO_DATA"


def _completed_ws_canary_ok(summaries: Mapping[str, Mapping[str, object]]) -> bool:
    return _campaign_completion_status(
        summaries.get("campaign_summary.json", {}),
        summaries.get("campaign_validation.json", {}),
        None,
    ) in {"CANARY_COMPLETED_OK", "CANARY_COMPLETED_QUIET_MARKET_NO_RECENT_EVENT"}


def _campaign_completion_status(
    campaign: Mapping[str, object],
    validation: Mapping[str, object],
    generated_at: datetime | None,
) -> str | None:
    if campaign.get("status") not in COMPLETED_WS_CAMPAIGN_STATUSES:
        return None
    if not _completed_ws_campaign_has_safe_evidence(campaign, validation):
        return "COMPLETED_WITH_MONITOR_STALE_METADATA_WARNING"
    last_event_time = campaign.get("last_event_time") or validation.get("last_event_time")
    stale_seconds = _staleness_seconds(last_event_time, generated_at) if generated_at else None
    if _is_stale(stale_seconds):
        return "CANARY_COMPLETED_QUIET_MARKET_NO_RECENT_EVENT"
    return "CANARY_COMPLETED_OK"


def _completed_ws_campaign_has_safe_evidence(
    campaign: Mapping[str, object],
    validation: Mapping[str, object],
) -> bool:
    classification = validation.get("evidence_classification") or campaign.get(
        "evidence_classification"
    )
    event_count = _int_or_zero(campaign.get("event_count") or validation.get("event_count"))
    snapshot_count = _int_or_zero(
        campaign.get("snapshot_count") or validation.get("snapshot_count")
    )
    delta_count = _int_or_zero(campaign.get("delta_count") or validation.get("delta_count"))
    gap_count = _int_or_zero(campaign.get("gap_count") or validation.get("gap_count"))
    submit_attempts = _int_or_zero(
        campaign.get("submit_attempts") or campaign.get("submit_attempt_count")
    )
    return (
        (validation.get("status") or campaign.get("validation_status")) == "pass"
        and classification
        in {
            "LAYER1_WS_DELTA_SMOKE_PASS",
            "LAYER1_WS_SNAPSHOT_ONLY_EXTENDED",
            "LAYER1_WS_SNAPSHOT_SMOKE_PASS",
        }
        and campaign.get("blocker_code") in {None, ""}
        and validation.get("blocker_code") in {None, ""}
        and campaign.get("connection_established") is True
        and campaign.get("subscription_acknowledged") is True
        and event_count > 0
        and snapshot_count + delta_count > 0
        and gap_count == 0
        and campaign.get("live_gate_status") == "disabled"
        and submit_attempts == 0
    )


def _health(
    *,
    input_dir: Path,
    records: list[dict[str, object]],
    summaries: Mapping[str, Mapping[str, object]],
    warnings: Sequence[str],
    risk: Mapping[str, object],
    reconciliation: Mapping[str, object],
    data_status: Mapping[str, object],
    campaign_snapshot: Mapping[str, object] | None = None,
) -> str:
    if not input_dir.exists():
        warnings.append("NO_DATA: input directory does not exist")
        return "NO_DATA"
    if not records and not summaries:
        warnings.append("NO_DATA: no monitor artifacts found")
        return "NO_DATA"
    campaign = campaign_snapshot or summaries.get("campaign_summary.json", {})
    if campaign.get("runtime_schema_version") == "edmn.kalshi.ws.runtime.v2":
        validation = summaries.get("campaign_validation.json", {})
        if validation.get("status") in {"fail", "blocked"}:
            return "BLOCKED"
        dimensions = campaign.get("independent_evidence_classifications")
        if not isinstance(dimensions, Mapping):
            warnings.append("D2_RUNTIME_VALIDATION_FAILED: evidence dimensions are unavailable")
            return "BLOCKED"
        if any(value == "FAIL" for value in dimensions.values()):
            return "BLOCKED"
        if any(value == "UNKNOWN" for value in dimensions.values()):
            return "WARNING"
        if campaign.get("status") in {"d2_runtime_running", "D2_RUNTIME_RUNNING"}:
            return "WARNING"
    if (
        risk.get("kill_switch")
        or risk.get("decision") == "reject"
        or risk.get("reconciliation_mismatch")
        or _int_or_zero(reconciliation.get("mismatch_count")) > 0
        or reconciliation.get("status") == "mismatch"
    ):
        return "BLOCKED"
    if warnings or data_status.get("stale_status") == "STALE":
        return "WARNING"
    return "OK_PAPER"


def _redact_mapping(value: Mapping[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, item in value.items():
        lowered = key.lower()
        if any(part in lowered for part in SECRET_KEYS):
            redacted[key] = "[REDACTED]"
        elif isinstance(item, dict):
            redacted[key] = _redact_mapping(item)
        elif isinstance(item, list):
            redacted[key] = [_redact_mapping(x) if isinstance(x, dict) else x for x in item]
        else:
            redacted[key] = item
    return redacted


def _first_record(
    records: list[dict[str, object]],
    record_type: str,
    default: dict[str, object] | None = None,
) -> dict[str, object]:
    return next(
        (record for record in records if record.get("record_type") == record_type),
        default or {},
    )


def _has_record(records: list[dict[str, object]], record_type: str) -> bool:
    return bool(_first_record(records, record_type))


def _is_market_data_record(record: Mapping[str, object]) -> bool:
    if record.get("record_type") in {"live_market_data_event", "market_data_snapshot"}:
        return True
    return all(key in record for key in ("venue", "market_id", "observed_at", "event_type"))


def _is_replay_frame(record: Mapping[str, object]) -> bool:
    return "book_hash" in record and "event_sequence" in record and "market_id" in record


def _first_value(records: list[dict[str, object]], field: str) -> object:
    return next((record[field] for record in records if field in record), None)


def _last_value(records: list[dict[str, object]], field: str) -> object:
    return next((record[field] for record in reversed(records) if field in record), None)


def _first_mapping_value(records: Sequence[Mapping[str, object]], field: str) -> object:
    return next((record[field] for record in records if field in record), None)


def _count_distinct(records: list[dict[str, object]], field: str) -> int:
    return len({record[field] for record in records if field in record})


def _flag_status(records: list[dict[str, object]], prefix: str) -> str:
    return (
        "WARN"
        if any(prefix in str(record.get("data_quality_flags", ())) for record in records)
        else "OK"
    )


def _count_flag(records: list[dict[str, object]], flag: str) -> int:
    return sum(
        flag in str(record.get("data_quality_flags", ())) or flag in str(record.get("flags", ()))
        for record in records
    )


def _nested(record: Mapping[str, object], parent: str, child: str) -> object:
    value = record.get(parent)
    if isinstance(value, Mapping):
        return value.get(child)
    return None


def _approval_required(record: Mapping[str, object]) -> bool:
    preview = record.get("risk_preview")
    if isinstance(preview, Mapping):
        return "manual_approval_required" in str(preview.get("reasons", ()))
    return True


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _decimal_product(left: object, right: object) -> str | None:
    try:
        return str(Decimal(str(left)) * Decimal(str(right)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _staleness_seconds(value: object, generated_at: datetime) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0, math.ceil((generated_at - parsed.astimezone(UTC)).total_seconds()))


def _seconds_since(value: object, generated_at: datetime) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0, int((generated_at - parsed.astimezone(UTC)).total_seconds()))


def _is_closed_market_status(value: object) -> bool:
    return str(value or "").strip().lower() in {
        "closed",
        "settled",
        "finalized",
        "resolved",
        "expired",
    }


def _is_stale(value: object) -> bool:
    if isinstance(value, int | float):
        return value > STALE_SECONDS
    if isinstance(value, str):
        try:
            return float(value) > STALE_SECONDS
        except ValueError:
            return False
    return False


def _completed_bounded_campaign(campaign: Mapping[str, object]) -> bool:
    return campaign.get("status") in {
        "smoke_complete",
        "recorder_smoke_complete",
        "websocket_smoke_complete",
        "d2_runtime_complete",
    }


def _render_table(snapshot: Mapping[str, object], *, include_evidence: bool) -> str:
    run = _mapping(snapshot, "run_info")
    data = _mapping(snapshot, "data_status")
    risk = _mapping(snapshot, "risk")
    reconciliation = _mapping(snapshot, "reconciliation")
    lines = [
        "V2 Monitor",
        f"LIVE GATE: {str(_mapping(run, 'live_gate').get('status')).upper()}",
        f"TRADING MODE: {run['trading_mode']}",
        f"HEALTH: {run['health']}",
        (
            f"DATA: venue={data.get('venue')} latest={data.get('last_event_time')} "
            f"stale={data.get('stale_status')} gaps={data.get('gap_count')}"
        ),
        _campaign_line(snapshot),
        "POSITIONS:",
    ]
    positions = _rows(snapshot, "positions")
    lines.extend(_position_line(row) for row in positions)
    if not positions:
        lines.append("  none")
    lines.append("ORDERS:")
    orders = _rows(snapshot, "orders")
    lines.extend(_order_line(row) for row in orders)
    if not orders:
        lines.append("  none")
    lines.extend(
        [
            (
                "RISK: "
                f"decision={risk.get('decision')} "
                f"kill_switch={risk.get('kill_switch')} "
                f"manual_approval_required={risk.get('manual_approval_required')} "
                f"warnings={risk.get('warnings')}"
            ),
            (
                "RECONCILIATION: "
                f"status={reconciliation.get('status')} "
                f"mismatches={reconciliation.get('mismatch_count')}"
            ),
        ]
    )
    if include_evidence:
        lines.extend(_evidence_lines(snapshot))
    warnings = _as_list(run.get("warnings"))
    if warnings:
        lines.append("WARNINGS:")
        lines.extend(f"  {warning}" for warning in warnings)
    return "\n".join(lines)


def _render_markdown(snapshot: Mapping[str, object], *, include_evidence: bool) -> str:
    run = _mapping(snapshot, "run_info")
    lines = [
        "# V2 Monitor Snapshot",
        "",
        f"- LIVE GATE: {str(_mapping(run, 'live_gate').get('status')).upper()}",
        f"- TRADING MODE: {run['trading_mode']}",
        f"- HEALTH: {run['health']}",
        f"- input_dir: `{run['input_dir']}`",
        "",
        "## Positions",
        "",
        (
            "| venue | market_ticker | type | currency | side | qty | avg | mark | "
            "notional | exposure | realized_pnl | unrealized_pnl | fees |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in _rows(snapshot, "positions"):
        lines.append(
            (
                "| {venue} | {market_ticker} | {instrument_type} | {currency} | "
                "{side} | {quantity} | {average_price} | {mark_price} | {notional} | "
                "{exposure} | {realized_pnl} | {unrealized_pnl} | {fees} |"
            ).format(**_stringified(row))
        )
    if not _rows(snapshot, "positions"):
        lines.append(
            "| none | none | none | none | none | none | none | none | none | "
            "none | none | none | none |"
        )
    lines.extend(
        [
            "",
            "## Orders",
            "",
            (
                "| venue | market_ticker | side | action | price | quantity | "
                "notional | status | approval_required | risk_decision |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in _rows(snapshot, "orders"):
        lines.append(
            (
                "| {venue} | {market_ticker} | {side} | {action} | {price} | "
                "{quantity} | {notional} | {status} | {approval_required} | "
                "{risk_decision} |"
            ).format(**_stringified(row))
        )
    if not _rows(snapshot, "orders"):
        lines.append(
            "| none | none | none | none | none | none | none | none | "
            "none | none |"
        )
    lines.extend(
        [
            "",
            "## Risk And Reconciliation",
            "",
            "```json",
            json.dumps(
                {
                    "campaign": snapshot["campaign"],
                    "risk": snapshot["risk"],
                    "reconciliation": snapshot["reconciliation"],
                    "data_status": snapshot["data_status"],
                },
                indent=2,
                sort_keys=True,
            ),
            "```",
        ]
    )
    if include_evidence:
        lines.extend(["", "## Evidence", "", *_evidence_lines(snapshot)])
    return "\n".join(lines)


def _mapping(record: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = record.get(key)
    return value if isinstance(value, Mapping) else {}


def _rows(record: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = record.get(key)
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _position_line(row: Mapping[str, object]) -> str:
    return (
        "  {venue} {market_ticker} {instrument_type} {currency} {side} "
        "qty={quantity} avg={average_price} mark={mark_price} notional={notional} "
        "exposure={exposure} realized_pnl={realized_pnl} unrealized_pnl={unrealized_pnl} "
        "fees={fees}"
    ).format(**_stringified(row))


def _campaign_line(snapshot: Mapping[str, object]) -> str:
    campaign = _mapping(snapshot, "campaign")
    if not campaign.get("campaign_id"):
        return "CAMPAIGN: none"
    return (
        "CAMPAIGN: id={campaign_id} status={status} source_type={source_type} "
        "venue={venue} market={subscribed_market_ticker} event_ticker={event_ticker} "
        "market_status={market_status} close_time={close_time} "
        "time_to_close_at_launch={time_to_close_at_launch_seconds} "
        "time_since_close={time_since_close_seconds} "
        "market_evidence_valid={market_evidence_valid} markets={market_count} "
        "tickers={market_tickers} completion={completion_status} "
        "events={event_count} snapshots={snapshot_count} "
        "deltas={delta_count} trades={trade_count} status_updates={status_update_count} "
        "heartbeats={heartbeat_count} disconnects={disconnect_count} "
        "reconnects={reconnect_count} gaps={gap_count} last_event={last_event_time} "
        "stale_seconds={stale_seconds} rebuild_frames={rebuild_frame_count} "
        "supervisor_liveness={supervisor_liveness_status} "
        "campaign_process_liveness={campaign_process_liveness_status} "
        "ws_freshness={websocket_message_freshness_status} "
        "exchange_heartbeat={exchange_heartbeat_status} "
        "validation={validation_status} connection={connection_established} "
        "subscription={subscription_acknowledged} live_gate={live_gate_status} "
        "submit_attempts={submit_attempts} manifest={manifest_path} "
        "validation_report={validation_report_path}"
    ).format(**_stringified(campaign))


def _order_line(row: Mapping[str, object]) -> str:
    return (
        "  {venue} {market_ticker} {side} {action} price={price} qty={quantity} "
        "notional={notional} status={status} approval_required={approval_required} "
        "risk_decision={risk_decision}"
    ).format(**_stringified(row))


def _evidence_lines(snapshot: Mapping[str, object]) -> list[str]:
    evidence = _mapping(snapshot, "evidence")
    lines = ["EVIDENCE:"]
    layers = evidence.get("layers")
    if isinstance(layers, Mapping):
        lines.extend(f"  {name}: {status}" for name, status in layers.items())
    lines.append(
        "  Required private evidence missing: "
        + ", ".join(str(item) for item in _as_list(evidence.get("missing_required_artifacts")))
    )
    lines.append(f"  Verdict: {evidence.get('strict_verdict')}")
    return lines


def _stringified(row: Mapping[str, object]) -> dict[str, str]:
    return {key: "" if value is None else str(value) for key, value in row.items()}


if __name__ == "__main__":
    main()
