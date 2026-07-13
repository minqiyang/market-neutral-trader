"""V2 read-only campaign runner and validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx

from edmn_trader.adapters.kalshi import (
    KalshiClientError,
    KalshiDemoMarketDataClient,
    KalshiEmptyOrderBookError,
    KalshiHTTPError,
    KalshiReadOnlyRecorderConfig,
    KalshiResponseError,
    KalshiWsAuthBlocked,
    load_kalshi_ws_auth_config_from_env,
    normalize_kalshi_market_metadata,
    record_kalshi_readonly_orderbook,
)
from edmn_trader.adapters.kalshi.ws_runtime import (
    D2_RUNTIME_SCHEMA_VERSION,
    collect_runtime_code_provenance,
    run_d2_kalshi_ws_runtime,
    validate_d2_runtime_artifacts,
    write_d2_runtime_preflight_block,
)
from edmn_trader.data.jsonl import read_jsonl_records, write_jsonl_records
from edmn_trader.scripts.daily_validation_report import run as run_daily_validation_report
from edmn_trader.scripts.rebuild_orderbooks import run as run_rebuild_orderbooks

MAX_SMOKE_SECONDS = 1_800
EXTENDED_WS_SMOKE_SECONDS = 900
CANARY_SECONDS = 1_800
SEVEN_DAY_SECONDS = 604_800
SCHEMA_VERSION = "v2.readonly_campaign.v1"
SOURCE_TYPES = {"SYNTHETIC", "REST", "WEBSOCKET_SNAPSHOT", "WEBSOCKET_DELTA"}
WEBSOCKET_SOURCE_TYPES = {"WEBSOCKET_SNAPSHOT", "WEBSOCKET_DELTA"}
DEFAULT_SELECTION_SAFETY_BUFFER_SECONDS = 86_400
SMOKE_SELECTION_SAFETY_BUFFER_SECONDS = 900
CANARY_SELECTION_SAFETY_BUFFER_SECONDS = 3_600
MARKET_DISCOVERY_PAGE_LIMIT = 1_000
MAX_MARKET_DISCOVERY_PAGES = 100
EVENT_DISCOVERY_PAGE_LIMIT = 200
MAX_EVENT_DISCOVERY_PAGES = 100
MAX_EVENT_FALLBACK_REQUESTS = 100
DISCOVERY_PROTOCOL_VERSION = "edmn.kalshi.discovery_protocol.v1"
DISCOVERY_SELECTION_DIAGNOSTIC_FIELDS = {
    "market_discovery_protocol_version": "discovery_protocol_version",
    "market_discovery_event_page_requests": "event_page_requests",
    "market_discovery_event_pages_completed": "event_pages_completed",
    "market_discovery_event_pagination_complete": "event_pagination_complete",
    "market_discovery_event_fallback_requests": "single_event_fallback_requests",
    "market_discovery_max_event_fallback_requests": "max_event_fallback_requests",
    "market_discovery_event_fallback_limit_reached": (
        "event_fallback_request_limit_reached"
    ),
    "market_discovery_market_mve_filter": "market_mve_filter",
}
DISCOVERY_MAX_ATTEMPTS = 3
DISCOVERY_NEAR_MISS_LIMIT = 100
RUNTIME_MARKET_SELECTION_MAX_ORDERBOOK_PROBES = 100
OCCURRENCE_CLOCK_SKEW_TOLERANCE_SECONDS = 60
SELECTION_PROFILE_VERSION = "edmn.kalshi.selection_profile.v4"
OPEN_MARKET_STATUSES = {"open", "trading"}
MARKET_STATUS_REJECTION_REASONS = {
    "initialized": "MARKET_STATUS_UNOPENED",
    "unopened": "MARKET_STATUS_UNOPENED",
    "inactive": "MARKET_STATUS_PAUSED",
    "paused": "MARKET_STATUS_PAUSED",
    "closed": "MARKET_STATUS_CLOSED",
    "settled": "MARKET_STATUS_SETTLED",
    "determined": "MARKET_STATUS_DETERMINED",
    "disputed": "MARKET_STATUS_DISPUTED",
    "amended": "MARKET_STATUS_AMENDED",
    "finalized": "MARKET_STATUS_FINALIZED",
    "resolved": "MARKET_STATUS_FINALIZED",
    "expired": "MARKET_STATUS_CLOSED",
}
CLOSED_OR_FINAL_STATUSES = {
    "closed",
    "settled",
    "finalized",
    "resolved",
    "expired",
    "determined",
    "disputed",
    "amended",
}
CONSERVATIVE_LIFECYCLE_TIME_FIELDS = (
    "close_time",
    "expected_expiration_time",
    "expected_expiration",
    "early_close_deadline",
    "early_close_time",
    "early_close_condition_deadline",
)
EXPECTED_EXPIRATION_FIELDS = ("expected_expiration_time", "expected_expiration")
OCCURRENCE_FIELDS = ("occurrence_datetime", "occurrence_time")
EARLY_CLOSE_DEADLINE_FIELDS = (
    "early_close_deadline",
    "early_close_time",
    "early_close_condition_deadline",
)
SECRET_KEY_PARTS = (
    "api_key",
    "authorization",
    "credential",
    "private_key",
    "secret",
    "token",
    "wallet",
)
ALLOWED_SECRET_LIKE_KEYS = {"credential_presence"}
PUBLIC_REPO_ROOT = Path(__file__).resolve().parents[3]


class SelectionProfile(StrEnum):
    SMOKE = "smoke"
    CANARY = "canary"
    SEVEN_DAY = "seven_day"


def selection_profile_for_duration(duration_seconds: int) -> SelectionProfile:
    if duration_seconds == CANARY_SECONDS:
        return SelectionProfile.CANARY
    if duration_seconds >= SEVEN_DAY_SECONDS:
        return SelectionProfile.SEVEN_DAY
    return SelectionProfile.SMOKE


def selection_safety_buffer_seconds(profile: SelectionProfile) -> int:
    if profile is SelectionProfile.CANARY:
        return CANARY_SELECTION_SAFETY_BUFFER_SECONDS
    if profile is SelectionProfile.SEVEN_DAY:
        return DEFAULT_SELECTION_SAFETY_BUFFER_SECONDS
    return SMOKE_SELECTION_SAFETY_BUFFER_SECONDS


def selection_profile_hash(
    profile: SelectionProfile,
    *,
    duration_seconds: int,
    safety_buffer_seconds: int,
) -> str:
    policy = {
        "version": SELECTION_PROFILE_VERSION,
        "profile": profile.value,
        "duration_seconds": duration_seconds,
        "safety_buffer_seconds": safety_buffer_seconds,
        "conservative_lifecycle_time_fields": CONSERVATIVE_LIFECYCLE_TIME_FIELDS,
        "occurrence_policy": "dual_interpretation_no_relaxation",
        "occurrence_fields": OCCURRENCE_FIELDS,
        "occurrence_clock_skew_tolerance_seconds": (
            OCCURRENCE_CLOCK_SKEW_TOLERANCE_SECONDS
        ),
        "complete_event_metadata_required": profile is not SelectionProfile.SMOKE,
        "early_close_rule": "require_authoritative_explicit_deadline_beyond_required_end",
        "can_close_early_must_be_explicit": profile is not SelectionProfile.SMOKE,
        "close_time_must_exceed_required_end": profile is not SelectionProfile.SMOKE,
        "expected_expiration_must_exceed_required_end": True,
        "earliest_deadline_must_exceed_required_end": True,
        "reject_sports_or_match": profile is not SelectionProfile.SMOKE,
        "require_non_empty_orderbook": True,
    }
    encoded = json.dumps(policy, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _blocked_ws_selection_record(
    profile: SelectionProfile,
    discovery: Mapping[str, object] | None = None,
) -> dict[str, object]:
    discovery = discovery or {}
    raw_diagnostics = discovery.get("diagnostics")
    diagnostics = raw_diagnostics if isinstance(raw_diagnostics, Mapping) else {}
    record = {
        "selection_profile": profile.value,
        "selection_safety_buffer_seconds": selection_safety_buffer_seconds(profile),
        "selection_gate_result": "reject",
        "selection_gate_rejection_reason": discovery.get("blocker_code")
        or "PRE_DISCOVERY_BLOCKED",
        "market_discovery_pages": discovery.get("pages_fetched", 0),
        "market_discovery_count": discovery.get("markets_seen", 0),
        "market_discovery_rejection_counts": discovery.get("rejection_counts", {}),
        "market_discovery_cursor_remaining": discovery.get("cursor_remaining"),
        "market_discovery_coverage_complete": discovery.get("coverage_complete"),
    }
    optional_fields = {
        "market_discovery_orderbook_requests": ("orderbook_requests", diagnostics),
        "market_discovery_orderbook_candidate_count": (
            "orderbook_candidate_count",
            diagnostics,
        ),
        "market_discovery_orderbook_candidate_scan_complete": (
            "orderbook_candidate_scan_complete",
            diagnostics,
        ),
        "market_discovery_eligible_count": ("eligible_count", discovery),
        "market_discovery_eligible_count_complete": (
            "eligible_count_complete",
            diagnostics,
        ),
        "market_discovery_eligible_count_is_lower_bound": (
            "eligible_count_is_lower_bound",
            diagnostics,
        ),
        "market_discovery_eligible_market_limit": (
            "eligible_market_limit",
            diagnostics,
        ),
        "market_discovery_max_orderbook_probes": (
            "max_orderbook_probes",
            diagnostics,
        ),
        "market_discovery_orderbook_probe_limit_reached": (
            "orderbook_probe_limit_reached",
            diagnostics,
        ),
    }
    record.update(
        {
            output_key: source[source_key]
            for output_key, (source_key, source) in optional_fields.items()
            if source_key in source
        }
    )
    record.update(_discovery_selection_diagnostics(diagnostics))
    return record


def _discovery_selection_diagnostics(
    diagnostics: Mapping[str, object],
) -> dict[str, object]:
    return {
        output_key: diagnostics[source_key]
        for output_key, source_key in DISCOVERY_SELECTION_DIAGNOSTIC_FIELDS.items()
        if source_key in diagnostics
    }


def evaluate_market_selection(
    market_metadata: Mapping[str, object] | None,
    *,
    selected_at_utc: datetime,
    duration_seconds: int,
    safety_buffer_seconds: int | None = None,
    selection_reason: str = "read_only_campaign_selection",
    require_non_empty_orderbook: bool = True,
    require_event_metadata: bool = False,
    allow_sports_long_horizon: bool = False,
    selection_profile: SelectionProfile | str | None = None,
) -> dict[str, object]:
    profile = (
        SelectionProfile(selection_profile)
        if selection_profile is not None
        else selection_profile_for_duration(duration_seconds)
    )
    effective_safety_buffer = (
        safety_buffer_seconds
        if safety_buffer_seconds is not None
        else selection_safety_buffer_seconds(profile)
    )
    if market_metadata is None:
        return _market_lifecycle_record(
            {},
            selected_at_utc=selected_at_utc,
            duration_seconds=duration_seconds,
            safety_buffer_seconds=effective_safety_buffer,
            selection_reason=selection_reason,
            result="reject",
            reason="MISSING_MARKET_METADATA",
            selection_profile=profile,
        )

    campaign_required_end = selected_at_utc + timedelta(
        seconds=duration_seconds + effective_safety_buffer
    )
    reasons = _market_selection_rejection_reasons(
        market_metadata,
        selected_at_utc=selected_at_utc,
        campaign_required_end=campaign_required_end,
        profile=profile,
        require_non_empty_orderbook=require_non_empty_orderbook,
        require_event_metadata=require_event_metadata,
        allow_sports_long_horizon=allow_sports_long_horizon,
    )
    reason = reasons[0] if reasons else None

    return _market_lifecycle_record(
        market_metadata,
        selected_at_utc=selected_at_utc,
        duration_seconds=duration_seconds,
        safety_buffer_seconds=effective_safety_buffer,
        selection_reason=selection_reason,
        result="pass" if reason is None else "reject",
        reason=reason,
        selection_profile=profile,
    )


def _lifecycle_policy_evidence(
    market_metadata: Mapping[str, object],
    *,
    selected_at_utc: datetime,
    campaign_required_end: datetime,
    profile: SelectionProfile,
) -> dict[str, Any]:
    close_time = _parse_time(market_metadata.get("close_time"))
    expected_expiration = _first_metadata_time(
        market_metadata, *EXPECTED_EXPIRATION_FIELDS
    )
    early_close_deadline = _first_metadata_time(
        market_metadata, *EARLY_CLOSE_DEADLINE_FIELDS
    )
    early_close_deadline_authoritative = (
        market_metadata.get("early_close_deadline_authoritative") is True
    )
    occurrence_raw = _first_metadata_value(market_metadata, *OCCURRENCE_FIELDS)
    occurrence_time = _parse_time(occurrence_raw)
    occurrence_included = False

    if occurrence_raw is None:
        occurrence_semantics = "MISSING"
    elif occurrence_time is None:
        occurrence_semantics = "INVALID"
    elif profile is SelectionProfile.SMOKE:
        occurrence_semantics = "SMOKE_UNINTERPRETED_OCCURRENCE"
        occurrence_included = True
    elif occurrence_time <= selected_at_utc + timedelta(
        seconds=OCCURRENCE_CLOCK_SKEW_TOLERANCE_SECONDS
    ):
        occurrence_semantics = "HISTORICAL_OR_ALREADY_OCCURRED"
    else:
        occurrence_semantics = "AMBIGUOUS_FUTURE_OCCURRENCE"
        occurrence_included = True

    components = {
        "close_time": close_time,
        "expected_expiration_time": expected_expiration,
        "early_close_deadline": early_close_deadline,
        "occurrence_safety_bound": occurrence_time if occurrence_included else None,
    }
    deadlines = [value for value in components.values() if value is not None]
    conservative_deadline = min(deadlines) if deadlines else None
    can_close_early = _as_optional_bool(market_metadata.get("can_close_early"))
    dual_interpretation_pass: bool | None = None
    if profile is not SelectionProfile.SMOKE:
        trusted_deadlines_safe = (
            close_time is not None
            and close_time > campaign_required_end
            and expected_expiration is not None
            and expected_expiration > campaign_required_end
        )
        occurrence_safe = occurrence_semantics == "MISSING" or (
            occurrence_semantics == "AMBIGUOUS_FUTURE_OCCURRENCE"
            and occurrence_time is not None
            and occurrence_time > campaign_required_end
        )
        early_close_safe = can_close_early is False or (
            can_close_early is True
            and occurrence_semantics != "MISSING"
            and early_close_deadline_authoritative
            and early_close_deadline is not None
            and early_close_deadline > campaign_required_end
        )
        dual_interpretation_pass = (
            trusted_deadlines_safe and occurrence_safe and early_close_safe
        )

    raw_text = (
        occurrence_raw.isoformat()
        if isinstance(occurrence_raw, datetime)
        else occurrence_raw
    )
    return {
        **components,
        "conservative_lifecycle_deadline": conservative_deadline,
        "early_close_deadline_authoritative": early_close_deadline_authoritative,
        "occurrence_raw_value": raw_text,
        "occurrence_semantic_classification": occurrence_semantics,
        "occurrence_included_as_safety_bound": occurrence_included,
        "occurrence_equals_close_time": (
            occurrence_time is not None and occurrence_time == close_time
        ),
        "occurrence_equals_expected_expiration_time": (
            occurrence_time is not None and occurrence_time == expected_expiration
        ),
        "dual_interpretation_pass": dual_interpretation_pass,
    }


def _market_selection_rejection_reasons(
    market_metadata: Mapping[str, object],
    *,
    selected_at_utc: datetime,
    campaign_required_end: datetime,
    profile: SelectionProfile,
    require_non_empty_orderbook: bool,
    require_event_metadata: bool,
    allow_sports_long_horizon: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    status = str(market_metadata.get("status") or "").strip().lower()
    status_reason = MARKET_STATUS_REJECTION_REASONS.get(status)
    if not status:
        reasons.append("MARKET_STATUS_UNKNOWN")
    elif status not in OPEN_MARKET_STATUSES:
        reasons.append(status_reason or "MARKET_STATUS_UNKNOWN")

    event_metadata_required = require_event_metadata or profile is not SelectionProfile.SMOKE
    if event_metadata_required and not _event_category(market_metadata):
        reasons.append("EVENT_CATEGORY_MISSING")
    if event_metadata_required and not _event_metadata_fetched(market_metadata):
        reasons.append(
            "EVENT_METADATA_INCOMPLETE"
            if profile is SelectionProfile.CANARY
            else "EVENT_METADATA_MISSING"
        )

    policy = _lifecycle_policy_evidence(
        market_metadata,
        selected_at_utc=selected_at_utc,
        campaign_required_end=campaign_required_end,
        profile=profile,
    )
    close_time = policy["close_time"]
    expected_expiration = policy["expected_expiration_time"]
    early_close_deadline = policy["early_close_deadline"]
    lifecycle_deadline = policy["conservative_lifecycle_deadline"]
    can_close_early = _as_optional_bool(market_metadata.get("can_close_early"))
    if profile is not SelectionProfile.SMOKE and can_close_early is None:
        reasons.append("CAN_CLOSE_EARLY_STATUS_UNKNOWN")
    if profile is not SelectionProfile.SMOKE and can_close_early is True and (
        policy["early_close_deadline_authoritative"] is not True
        or early_close_deadline is None
        or early_close_deadline <= campaign_required_end
    ):
        reasons.append(
            "CAN_CLOSE_EARLY_UNSAFE_FOR_CANARY"
            if profile is SelectionProfile.CANARY
            else "CAN_CLOSE_EARLY_UNSAFE_FOR_DURATION"
        )
    if profile is not SelectionProfile.SMOKE:
        if close_time is None:
            reasons.append("MISSING_CLOSE_TIME")
        elif close_time <= campaign_required_end:
            reasons.append("TIME_TO_CLOSE_TOO_SHORT")
        if expected_expiration is None:
            reasons.append("MISSING_EXPECTED_EXPIRATION_TIME")
        elif expected_expiration <= campaign_required_end:
            reasons.append("EXPECTED_EXPIRATION_TOO_SHORT")

        occurrence_semantics = policy["occurrence_semantic_classification"]
        if occurrence_semantics == "INVALID":
            reasons.append("OCCURRENCE_DATETIME_INVALID")
        elif occurrence_semantics == "HISTORICAL_OR_ALREADY_OCCURRED":
            reasons.append("OCCURRENCE_ALREADY_OCCURRED_UNSAFE")
        elif (
            occurrence_semantics == "AMBIGUOUS_FUTURE_OCCURRENCE"
            and policy["occurrence_safety_bound"] <= campaign_required_end
        ):
            reasons.append("OCCURRENCE_SAFETY_BOUND_TOO_SHORT")
        if can_close_early is True and occurrence_semantics == "MISSING":
            reasons.append(
                "CAN_CLOSE_EARLY_UNSAFE_FOR_CANARY"
                if profile is SelectionProfile.CANARY
                else "CAN_CLOSE_EARLY_UNSAFE_FOR_DURATION"
            )
    if lifecycle_deadline is None:
        if profile is SelectionProfile.SMOKE:
            reasons.append("MISSING_CLOSE_TIME")
    elif lifecycle_deadline <= campaign_required_end:
        if profile is SelectionProfile.CANARY:
            reasons.append("CANARY_LIFECYCLE_DEADLINE_TOO_SHORT")
        elif (
            close_time == lifecycle_deadline
            and expected_expiration is None
            and early_close_deadline is None
        ):
            reasons.append("TIME_TO_CLOSE_TOO_SHORT")
        else:
            reasons.append("CONSERVATIVE_LIFECYCLE_DEADLINE_TOO_SHORT")

    sports = _is_sports_market(market_metadata)
    match = _is_match_event(market_metadata)
    if profile is SelectionProfile.CANARY and sports:
        reasons.append("SPORTS_UNSUITABLE_FOR_CANARY")
    if profile is SelectionProfile.CANARY and match:
        reasons.append("MATCH_EVENT_UNSUITABLE_FOR_CANARY")
    if profile is SelectionProfile.SEVEN_DAY and not allow_sports_long_horizon:
        if sports or match:
            reasons.append("SPORTS_MATCH_UNSUITABLE_FOR_LONG_CAMPAIGN")
    if require_non_empty_orderbook and _is_empty_orderbook(market_metadata):
        reasons.append("EMPTY_ORDERBOOK")
    return tuple(dict.fromkeys(reasons))


def plan_campaign(
    *,
    root: Path,
    campaign_id: str,
    venue: str,
    market: str,
    duration_seconds: int,
    interval_seconds: int,
    source_type: str = "SYNTHETIC",
    now: datetime | None = None,
    market_metadata: Mapping[str, object] | None = None,
    selection_reason: str = "bounded_smoke",
) -> dict[str, object]:
    _validate_duration(duration_seconds, allow_seven_day=False)
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be at least 1")
    if venue not in {"kalshi_demo", "polymarket_us"}:
        raise ValueError("venue must be kalshi_demo or polymarket_us")
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            "source_type must be SYNTHETIC, REST, WEBSOCKET_SNAPSHOT, or WEBSOCKET_DELTA"
        )
    generated_at = now or datetime.now(UTC)
    lifecycle = (
        evaluate_market_selection(
            market_metadata,
            selected_at_utc=generated_at,
            duration_seconds=duration_seconds,
            selection_reason=selection_reason,
        )
        if market_metadata is not None
        else _default_lifecycle_record(market, generated_at, duration_seconds)
    )
    root.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "status": "planned",
        "artifact_root": str(root),
        "venue": venue,
        "market": market,
        "market_count": 1,
        "source_type": source_type,
        "generated_at_utc": generated_at.isoformat(),
        "planned_end_utc": (generated_at + timedelta(seconds=duration_seconds)).isoformat(),
        "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "mode": "read_only",
        "live_gate_status": "disabled",
        "production_endpoint_used": False,
        "submit_attempt_count": 0,
        "submit_attempts": 0,
        "real_money_trading": False,
        "event_count": 0,
        "snapshot_count": 0,
        "delta_count": 0,
        "trade_count": 0,
        "status_update_count": 0,
        "heartbeat_count": 0,
        "disconnect_count": 0,
        "reconnect_count": 0,
        "gap_count": 0,
        "last_event_time": None,
        "stale_seconds": None,
        "rebuild_frame_count": 0,
        "validation_status": "planned",
        "manifest_path": str(root / "campaign_manifest.json"),
        "validation_report_path": str(root / "campaign_validation.json"),
        "raw_data_path_redacted": f"[LOCAL_PRIVATE_DATA_ROOT]/{root.name}",
        **lifecycle,
        "supervisor_liveness_status": "UNKNOWN",
        "campaign_process_liveness_status": "UNKNOWN",
        "websocket_message_freshness_status": "NOT_OBSERVED",
        "exchange_heartbeat_status": "UNKNOWN",
        "expected_files": [
            "campaign_summary.json",
            "campaign_heartbeat.jsonl",
            "campaign_validation.json",
            "campaign_manifest.json",
            "run_metadata.json",
        ],
    }
    _write_json(root / "campaign_summary.json", summary)
    _write_campaign_manifest(root, summary, validation=None)
    _write_run_metadata(root, summary, validation=None)
    _write_json(
        root / "venue_status.json",
        {
            "venues": [
                {
                    "venue": venue,
                    "mode": "read_only",
                    "connectivity": "planned",
                    "last_event_ts": generated_at.isoformat(),
                    "data_staleness_seconds": 0,
                    "gap_count": 0,
                    "warning_count": 0,
                }
            ]
        },
    )
    return summary


def run_smoke(
    *,
    output_dir: Path,
    campaign_id: str,
    venue: str,
    market: str,
    duration_seconds: int,
    interval_seconds: int,
    sleep: bool = False,
    now: datetime | None = None,
) -> dict[str, object]:
    summary = plan_campaign(
        root=output_dir,
        campaign_id=campaign_id,
        venue=venue,
        market=market,
        duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        now=now,
    )
    started_at = datetime.fromisoformat(str(summary["generated_at_utc"]))
    heartbeat_count = max(1, duration_seconds // interval_seconds)
    rows = []
    for index in range(heartbeat_count):
        observed_at = started_at + timedelta(seconds=index * interval_seconds)
        rows.append(
            {
                "record_type": "campaign_heartbeat",
                "campaign_id": campaign_id,
                "venue": venue,
                "market": market,
                "sequence": index + 1,
                "observed_at": observed_at.isoformat(),
                "received_at": observed_at.isoformat(),
                "live_gate_status": "disabled",
                "submit_attempt": False,
                "production_endpoint_used": False,
                "status": "ok",
            }
        )
        if sleep and index + 1 < heartbeat_count:
            time.sleep(interval_seconds)
    write_jsonl_records(output_dir / "campaign_heartbeat.jsonl", rows)
    summary = {**summary, "status": "smoke_complete", "heartbeat_count": len(rows)}
    _write_json(output_dir / "campaign_summary.json", summary)
    validation = validate_campaign(input_dir=output_dir)
    summary = {**summary, "validation_status": validation["status"]}
    _write_json(output_dir / "campaign_summary.json", summary)
    _write_campaign_manifest(output_dir, summary, validation=validation)
    _write_run_metadata(output_dir, summary, validation=validation)
    return {
        "campaign_id": campaign_id,
        "artifact_root": str(output_dir),
        "heartbeat_count": len(rows),
        "validation_status": validation["status"],
        "live_gate_status": "disabled",
        "submit_attempt_count": 0,
    }


def run_kalshi_rest_smoke(
    *,
    output_dir: Path,
    campaign_id: str,
    market: str,
    duration_seconds: int,
    interval_seconds: int,
    live_readonly_opt_in: bool,
    depth: int | None = None,
    client: KalshiDemoMarketDataClient | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    summary = plan_campaign(
        root=output_dir,
        campaign_id=campaign_id,
        venue="kalshi_demo",
        market=market,
        duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        source_type="REST",
        now=now,
    )
    observed_at = datetime.fromisoformat(str(summary["generated_at_utc"]))
    events_path = output_dir / "kalshi_readonly_events.jsonl"
    snapshots_path = output_dir / "kalshi_readonly_snapshots.jsonl"
    rebuild_snapshots_path = output_dir / "rebuild_snapshots.jsonl"
    rebuild_frames_path = output_dir / "rebuild_frames.jsonl"
    daily_validation_path = output_dir / "daily_validation.jsonl"

    recorder = record_kalshi_readonly_orderbook(
        KalshiReadOnlyRecorderConfig(
            ticker=market,
            events_output_path=events_path,
            snapshots_output_path=snapshots_path,
            live_readonly_opt_in=live_readonly_opt_in,
            depth=depth,
        ),
        client=client,
    )
    rebuild = run_rebuild_orderbooks(
        events_path=events_path,
        snapshots_output_path=rebuild_snapshots_path,
        frames_output_path=rebuild_frames_path,
        markdown_output_path=output_dir / "rebuild.md",
    )
    daily = run_daily_validation_report(
        input_path=rebuild_frames_path,
        report_date=observed_at.date().isoformat(),
        input_source="kalshi_demo_readonly_rebuild",
        jsonl_output_path=daily_validation_path,
        markdown_output_path=output_dir / "daily_validation.md",
    )
    write_jsonl_records(
        output_dir / "campaign_heartbeat.jsonl",
        [
            {
                "record_type": "campaign_heartbeat",
                "campaign_id": campaign_id,
                "venue": "kalshi_demo",
                "market": market,
                "sequence": 1,
                "observed_at": observed_at.isoformat(),
                "received_at": datetime.now(UTC).isoformat(),
                "live_gate_status": "disabled",
                "submit_attempt": False,
                "production_endpoint_used": False,
                "status": "recorder_smoke_complete",
                "event_count": recorder.events_written,
                "rebuild_frame_count": rebuild.frames_rebuilt,
                "gap_count": rebuild.sequence_gap_count,
            }
        ],
    )
    summary = {
        **summary,
        "status": "recorder_smoke_complete",
        "heartbeat_count": 1,
        "source_type": "REST",
        "event_count": recorder.events_written,
        "snapshot_count": recorder.snapshots_written,
        "delta_count": 0,
        "trade_count": 0,
        "status_update_count": 0,
        "recorder_event_count": recorder.events_written,
        "recorder_snapshot_count": recorder.snapshots_written,
        "rebuild_frame_count": rebuild.frames_rebuilt,
        "gap_count": rebuild.sequence_gap_count,
        "last_event_time": observed_at.isoformat(),
        "stale_seconds": 0,
        "daily_validation_report_date": daily.report_date,
    }
    _write_json(output_dir / "campaign_summary.json", summary)
    validation = validate_campaign(input_dir=output_dir)
    summary = {**summary, "validation_status": validation["status"]}
    _write_json(output_dir / "campaign_summary.json", summary)
    _write_campaign_manifest(output_dir, summary, validation=validation)
    _write_run_metadata(output_dir, summary, validation=validation)
    return {
        "campaign_id": campaign_id,
        "artifact_root": str(output_dir),
        "recorder_event_count": recorder.events_written,
        "rebuild_frame_count": rebuild.frames_rebuilt,
        "daily_validation_count": validation["daily_validation_count"],
        "validation_status": validation["status"],
        "live_gate_status": "disabled",
        "submit_attempt_count": 0,
    }


def run_kalshi_ws_smoke(
    *,
    output_dir: Path,
    campaign_id: str,
    duration_seconds: int,
    max_markets: int,
    now: datetime | None = None,
    use_yes_price: bool = False,
) -> dict[str, object]:
    """Run the bounded authenticated read-only Kalshi WS smoke, or block safely."""

    _validate_duration(duration_seconds, allow_seven_day=False)
    if max_markets < 1:
        raise ValueError("max_markets must be at least 1")
    generated_at = now or datetime.now(UTC)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = selection_profile_for_duration(duration_seconds)
    provenance = collect_runtime_code_provenance(PUBLIC_REPO_ROOT)
    try:
        auth = load_kalshi_ws_auth_config_from_env()
    except KalshiWsAuthBlocked as exc:
        return write_d2_runtime_preflight_block(
            output_dir=output_dir,
            campaign_id=campaign_id,
            mode="read_only_websocket_smoke",
            configured_duration_seconds=duration_seconds,
            provenance=provenance,
            blocker_code=exc.code,
            started_at_utc=generated_at,
            selected_market_selection=_blocked_ws_selection_record(profile),
        )

    discovery = discover_kalshi_demo_ws_market(
        duration_seconds=duration_seconds,
        safety_buffer_seconds=selection_safety_buffer_seconds(profile),
        selected_at_utc=generated_at,
        selection_profile=profile,
        eligible_market_limit=max_markets,
        max_orderbook_probes=RUNTIME_MARKET_SELECTION_MAX_ORDERBOOK_PROBES,
    )
    market_metadata = discovery.get("market_metadata")
    market_selection = discovery.get("selection")
    if not isinstance(market_metadata, Mapping) or not isinstance(market_selection, Mapping):
        blocker_code = str(discovery["blocker_code"])
        return write_d2_runtime_preflight_block(
            output_dir=output_dir,
            campaign_id=campaign_id,
            mode="read_only_websocket_smoke",
            configured_duration_seconds=duration_seconds,
            provenance=provenance,
            blocker_code=blocker_code,
            started_at_utc=generated_at,
            selected_market_selection=_blocked_ws_selection_record(profile, discovery),
        )
    return run_d2_kalshi_ws_runtime(
        output_dir=output_dir,
        campaign_id=campaign_id,
        mode="read_only_websocket_smoke",
        duration_seconds=duration_seconds,
        market_metadata=market_metadata,
        market_selection=market_selection,
        auth=auth,
        provenance=provenance,
        use_yes_price=use_yes_price,
    )


def validate_campaign(*, input_dir: Path) -> dict[str, object]:
    failures: list[str] = []
    summary = _read_json(input_dir / "campaign_summary.json", failures)
    if summary.get("runtime_schema_version") == D2_RUNTIME_SCHEMA_VERSION:
        return validate_d2_runtime_artifacts(input_dir)
    heartbeats = _read_jsonl(input_dir / "campaign_heartbeat.jsonl", failures)
    recorder_events = _read_optional_jsonl(input_dir / "kalshi_readonly_events.jsonl", failures)
    rebuild_frames = _read_optional_jsonl(input_dir / "rebuild_frames.jsonl", failures)
    daily_validation = _read_optional_jsonl(input_dir / "daily_validation.jsonl", failures)
    if summary.get("schema_version") != SCHEMA_VERSION:
        failures.append("campaign_summary schema_version missing or unsupported")
    if summary.get("live_gate_status") != "disabled":
        failures.append("live_gate_status must be disabled")
    if summary.get("production_endpoint_used") is not False:
        failures.append("production_endpoint_used must be false")
    if summary.get("submit_attempt_count") != 0:
        failures.append("submit_attempt_count must be zero")
    if _as_int(summary.get("duration_seconds")) > MAX_SMOKE_SECONDS:
        if summary.get("mode") != "read_only_websocket_campaign":
            failures.append("duration_seconds exceeds bounded smoke maximum")
    source_type = summary.get("source_type")
    if source_type not in SOURCE_TYPES:
        failures.append("source_type missing or unsupported")
    if not heartbeats:
        failures.append("campaign_heartbeat.jsonl must contain at least one heartbeat")
    for row in heartbeats:
        if row.get("submit_attempt") is not False:
            failures.append("heartbeat submit_attempt must be false")
        if row.get("production_endpoint_used") is not False:
            failures.append("heartbeat production_endpoint_used must be false")
    if summary.get("status") == "recorder_smoke_complete":
        if not recorder_events:
            failures.append("recorder smoke must contain kalshi_readonly_events.jsonl")
        if not rebuild_frames:
            failures.append("recorder smoke must contain rebuild_frames.jsonl")
        if not daily_validation:
            failures.append("recorder smoke must contain daily_validation.jsonl")
    if _secret_like_files(input_dir):
        failures.append("secret-like field found in campaign artifacts")
    evidence_classification = _classify_campaign(
        summary=summary,
        failures=failures,
        recorder_events=recorder_events,
        rebuild_frames=rebuild_frames,
    )
    market_evidence_valid = not _market_closed_or_finalized(summary) and not (
        summary.get("mode") == "read_only_websocket_campaign"
        and summary.get("selection_gate_result") != "pass"
    )
    evidence_validity_classification = (
        "CAMPAIGN_EVIDENCE_VALID"
        if market_evidence_valid
        else "CAMPAIGN_EVIDENCE_INVALID_MARKET_LIFECYCLE"
    )
    status = "pass" if not failures else "fail"
    if not failures and str(summary.get("status", "")).startswith("websocket_"):
        if summary.get("blocker_code"):
            status = "blocked"
    if not failures and summary.get("status") == "websocket_auth_blocked":
        status = "blocked"
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "input_dir": str(input_dir),
        "campaign_id": summary.get("campaign_id"),
        "source_type": source_type,
        "evidence_classification": evidence_classification,
        "data_integrity_classification": "DATA_INTEGRITY_FAIL"
        if failures
        else "DATA_INTEGRITY_PASS",
        "campaign_evidence_valid": market_evidence_valid,
        "evidence_validity_classification": evidence_validity_classification,
        "market_lifecycle_status": _market_lifecycle_status(summary),
        "market_closed_or_finalized": _market_closed_or_finalized(summary),
        "heartbeat_count": len(heartbeats),
        "event_count": _campaign_count(summary, "event_count", len(recorder_events)),
        "snapshot_count": _campaign_count(summary, "snapshot_count", 0),
        "delta_count": _campaign_count(summary, "delta_count", 0),
        "trade_count": _campaign_count(summary, "trade_count", 0),
        "status_update_count": _campaign_count(summary, "status_update_count", 0),
        "disconnect_count": _campaign_count(summary, "disconnect_count", 0),
        "reconnect_count": _campaign_count(summary, "reconnect_count", 0),
        "gap_count": _campaign_count(summary, "gap_count", 0),
        "last_event_time": summary.get("last_event_time"),
        "stale_seconds": summary.get("stale_seconds"),
        "recorder_event_count": len(recorder_events),
        "rebuild_frame_count": _campaign_count(summary, "rebuild_frame_count", len(rebuild_frames)),
        "daily_validation_count": len(daily_validation),
        "failures": failures,
        "blocker": summary.get("blocker"),
        "blocker_code": summary.get("blocker_code"),
        "connection_established": summary.get("connection_established"),
        "subscription_acknowledged": summary.get("subscription_acknowledged"),
        "strict_verdict": "STRICT NO-GO",
    }
    _write_json(input_dir / "campaign_validation.json", result)
    _write_markdown(input_dir / "campaign_validation.md", result)
    _write_campaign_manifest(input_dir, summary, validation=result)
    _write_run_metadata(input_dir, summary, validation=result)
    return result


def main(argv: list[str] | None = None) -> None:
    effective_argv = sys.argv[1:] if argv is None else argv
    if "--mode" in effective_argv:
        payload = _run_mode_command(effective_argv)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    plan_parser = subcommands.add_parser("plan")
    _add_common_args(plan_parser)
    smoke_parser = subcommands.add_parser("smoke")
    _add_common_args(smoke_parser)
    smoke_parser.add_argument("--sleep", action="store_true")
    kalshi_parser = subcommands.add_parser("kalshi-rest-smoke")
    _add_common_args(kalshi_parser)
    kalshi_parser.add_argument("--live-readonly-opt-in", action="store_true")
    kalshi_parser.add_argument("--depth", type=int, default=None)
    validate_parser = subcommands.add_parser("validate")
    validate_parser.add_argument("--input-dir", required=True, type=Path)
    args = parser.parse_args(effective_argv)

    if args.command == "plan":
        payload = plan_campaign(
            root=args.output_dir,
            campaign_id=args.campaign_id,
            venue=args.venue,
            market=args.market,
            duration_seconds=args.duration_seconds,
            interval_seconds=args.interval_seconds,
        )
    elif args.command == "smoke":
        payload = run_smoke(
            output_dir=args.output_dir,
            campaign_id=args.campaign_id,
            venue=args.venue,
            market=args.market,
            duration_seconds=args.duration_seconds,
            interval_seconds=args.interval_seconds,
            sleep=args.sleep,
        )
    elif args.command == "kalshi-rest-smoke":
        payload = run_kalshi_rest_smoke(
            output_dir=args.output_dir,
            campaign_id=args.campaign_id,
            market=args.market,
            duration_seconds=args.duration_seconds,
            interval_seconds=args.interval_seconds,
            live_readonly_opt_in=args.live_readonly_opt_in,
            depth=args.depth,
        )
    else:
        payload = validate_campaign(input_dir=args.input_dir)
    print(json.dumps(payload, indent=2, sort_keys=True))


def _run_mode_command(argv: list[str]) -> dict[str, object]:
    parser = argparse.ArgumentParser(description="V2 read-only campaign mode runner")
    parser.add_argument(
        "--mode",
        required=True,
        choices=("kalshi-ws-smoke", "kalshi-ws-campaign"),
    )
    parser.add_argument("--duration-seconds", type=int, required=True)
    parser.add_argument("--max-markets", type=int, default=1)
    parser.add_argument("--use-yes-price", action="store_true")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--campaign-id")
    args = parser.parse_args(argv)
    campaign_id = args.campaign_id or args.output_dir.name
    if args.mode == "kalshi-ws-campaign":
        return run_kalshi_ws_campaign(
            output_dir=args.output_dir,
            campaign_id=campaign_id,
            duration_seconds=args.duration_seconds,
            max_markets=args.max_markets,
            use_yes_price=args.use_yes_price,
        )
    return run_kalshi_ws_smoke(
        output_dir=args.output_dir,
        campaign_id=campaign_id,
        duration_seconds=args.duration_seconds,
        max_markets=args.max_markets,
        use_yes_price=args.use_yes_price,
    )


def plan_kalshi_ws_campaign(
    *,
    output_dir: Path,
    campaign_id: str,
    duration_seconds: int,
    max_markets: int,
    now: datetime | None = None,
    market_metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    _validate_duration(duration_seconds, allow_seven_day=True)
    if max_markets < 1:
        raise ValueError("max_markets must be at least 1")
    generated_at = now or datetime.now(UTC)
    profile = selection_profile_for_duration(duration_seconds)
    lifecycle = evaluate_market_selection(
        market_metadata,
        selected_at_utc=generated_at,
        duration_seconds=duration_seconds,
        selection_reason="kalshi_ws_campaign_requires_selected_market_metadata",
        require_event_metadata=profile is not SelectionProfile.SMOKE,
        selection_profile=profile,
    )
    selected_market = str(lifecycle.get("market_ticker") or "OWNER_SELECTED")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "status": "planned_owner_supervised",
        "artifact_root": str(output_dir),
        "venue": "kalshi_demo",
        "market": selected_market,
        "market_count": 1 if lifecycle["selection_gate_result"] == "pass" else 0,
        "max_markets": max_markets,
        "source_type": "WEBSOCKET_DELTA",
        "generated_at_utc": generated_at.isoformat(),
        "planned_end_utc": (generated_at + timedelta(seconds=duration_seconds)).isoformat(),
        "duration_seconds": duration_seconds,
        "mode": "read_only_websocket_campaign",
        "live_gate_status": "disabled",
        "production_endpoint_used": False,
        "submit_attempt_count": 0,
        "submit_attempts": 0,
        "real_money_trading": False,
        "validation_status": "planned",
        "evidence_classification": "LAYER1_WS_CAMPAIGN_INCOMPLETE",
        "manifest_path": str(output_dir / "campaign_manifest.json"),
        "validation_report_path": str(output_dir / "campaign_validation.json"),
        "raw_data_path_redacted": f"[LOCAL_PRIVATE_DATA_ROOT]/{output_dir.name}",
        **lifecycle,
        "supervisor_liveness_status": "UNKNOWN",
        "campaign_process_liveness_status": "UNKNOWN",
        "websocket_message_freshness_status": "UNKNOWN",
        "exchange_heartbeat_status": "UNKNOWN",
    }
    _write_json(output_dir / "campaign_summary.json", summary)
    _write_campaign_manifest(output_dir, summary, validation=None)
    _write_run_metadata(output_dir, summary, validation=None)
    return summary


def run_kalshi_ws_campaign(
    *,
    output_dir: Path,
    campaign_id: str,
    duration_seconds: int,
    max_markets: int,
    now: datetime | None = None,
    use_yes_price: bool = False,
) -> dict[str, object]:
    _validate_duration(duration_seconds, allow_seven_day=True)
    generated_at = now or datetime.now(UTC)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = selection_profile_for_duration(duration_seconds)
    provenance = collect_runtime_code_provenance(PUBLIC_REPO_ROOT)
    try:
        auth = load_kalshi_ws_auth_config_from_env()
    except KalshiWsAuthBlocked as exc:
        return write_d2_runtime_preflight_block(
            output_dir=output_dir,
            campaign_id=campaign_id,
            mode="read_only_websocket_campaign",
            configured_duration_seconds=duration_seconds,
            provenance=provenance,
            blocker_code=exc.code,
            started_at_utc=generated_at,
            selected_market_selection=_blocked_ws_selection_record(profile),
        )

    discovery = discover_kalshi_demo_ws_market(
        duration_seconds=duration_seconds,
        safety_buffer_seconds=selection_safety_buffer_seconds(profile),
        selected_at_utc=generated_at,
        selection_profile=profile,
        eligible_market_limit=max_markets,
        max_orderbook_probes=RUNTIME_MARKET_SELECTION_MAX_ORDERBOOK_PROBES,
    )
    market_metadata = discovery.get("market_metadata")
    market_selection = discovery.get("selection")
    if not isinstance(market_metadata, Mapping) or not isinstance(market_selection, Mapping):
        blocker_code = str(discovery["blocker_code"])
        return write_d2_runtime_preflight_block(
            output_dir=output_dir,
            campaign_id=campaign_id,
            mode="read_only_websocket_campaign",
            configured_duration_seconds=duration_seconds,
            provenance=provenance,
            blocker_code=blocker_code,
            started_at_utc=generated_at,
            selected_market_selection=_blocked_ws_selection_record(profile, discovery),
        )
    return run_d2_kalshi_ws_runtime(
        output_dir=output_dir,
        campaign_id=campaign_id,
        mode="read_only_websocket_campaign",
        duration_seconds=duration_seconds,
        market_metadata=market_metadata,
        market_selection=market_selection,
        auth=auth,
        provenance=provenance,
        use_yes_price=use_yes_price,
        max_events=1_000_000,
        max_reconnects=1_000,
    )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--campaign-id", default="round4-readonly-smoke")
    parser.add_argument("--venue", choices=("kalshi_demo", "polymarket_us"), default="kalshi_demo")
    parser.add_argument("--market", default="DEMO-MARKET")
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=int, default=15)


def _validate_duration(duration_seconds: int, *, allow_seven_day: bool) -> None:
    max_seconds = SEVEN_DAY_SECONDS if allow_seven_day else MAX_SMOKE_SECONDS
    if duration_seconds < 1 or duration_seconds > max_seconds:
        raise ValueError(f"duration_seconds must be between 1 and {max_seconds}")


def _classify_campaign(
    *,
    summary: dict[str, object],
    failures: list[str],
    recorder_events: list[dict[str, object]],
    rebuild_frames: list[dict[str, object]],
) -> str:
    source_type = summary.get("source_type")
    status = summary.get("status")
    blocker_code = summary.get("blocker_code")
    if blocker_code == "NO_WS_CREDENTIALS":
        return "NO_WS_CREDENTIALS"
    if blocker_code == "WS_CREDENTIAL_STORAGE_UNSAFE":
        return "WS_CREDENTIAL_STORAGE_UNSAFE"
    if blocker_code in {"WS_PRIVATE_KEY_LOAD_FAILED", "AUTH_SIGNATURE_FAILED"}:
        return "WS_AUTH_FAILED"
    if _market_closed_or_finalized(summary):
        return "MARKET_CLOSED_OR_FINALIZED_ENDS_CAMPAIGN_EVIDENCE"
    if failures or status == "websocket_blocked":
        return "LAYER1_WS_CAMPAIGN_INCOMPLETE"
    if source_type == "REST":
        return "LAYER1_REST_SMOKE_PASS"
    if source_type in WEBSOCKET_SOURCE_TYPES:
        event_count = _campaign_count(summary, "event_count", len(recorder_events))
        snapshot_count = _campaign_count(summary, "snapshot_count", 0)
        delta_count = _campaign_count(summary, "delta_count", 0)
        if event_count <= 0:
            return "LAYER1_WS_CAMPAIGN_INCOMPLETE"
        if _as_int(summary.get("duration_seconds")) >= SEVEN_DAY_SECONDS:
            if status == "websocket_campaign_complete":
                return "LAYER1_WS_CAMPAIGN_PASS_7D"
            if delta_count > 0:
                return "LAYER1_WS_DELTA_SMOKE_PASS"
            return "LAYER1_WS_CAMPAIGN_INCOMPLETE"
        if delta_count > 0:
            return "LAYER1_WS_DELTA_SMOKE_PASS"
        if snapshot_count > 0 and summary.get("subscription_acknowledged") is True:
            if _as_int(summary.get("duration_seconds")) >= EXTENDED_WS_SMOKE_SECONDS:
                return "LAYER1_WS_SNAPSHOT_ONLY_EXTENDED"
            return "LAYER1_WS_SNAPSHOT_SMOKE_PASS"
        return "LAYER1_WS_CAMPAIGN_INCOMPLETE"
    return "LAYER1_WS_CAMPAIGN_INCOMPLETE"


def _campaign_count(summary: dict[str, object], key: str, fallback: int) -> int:
    value = summary.get(key)
    return value if isinstance(value, int) else fallback


def _write_campaign_manifest(
    root: Path,
    summary: dict[str, object],
    *,
    validation: dict[str, object] | None,
) -> None:
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": summary.get("campaign_id"),
        "venue": summary.get("venue"),
        "source_type": summary.get("source_type"),
        "status": summary.get("status"),
        "market_ticker": summary.get("market_ticker") or summary.get("market"),
        "subscribed_market_ticker": summary.get("market_ticker") or summary.get("market"),
        "event_ticker": summary.get("event_ticker"),
        "title": summary.get("title") or summary.get("name"),
        "name": summary.get("name") or summary.get("title"),
        "event_category": summary.get("event_category"),
        "event_title": summary.get("event_title"),
        "event_subtitle": summary.get("event_subtitle"),
        "event_type": summary.get("event_type"),
        "event_metadata_fetched": summary.get("event_metadata_fetched"),
        "category": summary.get("category"),
        "market_type": summary.get("market_type"),
        "status_at_launch": summary.get("status_at_launch"),
        "market_status": summary.get("market_status") or summary.get("status_at_launch"),
        "raw_market_status": summary.get("raw_market_status"),
        "open_time": summary.get("open_time"),
        "close_time": summary.get("close_time"),
        "expected_expiration": summary.get("expected_expiration"),
        "expected_expiration_time": summary.get("expected_expiration_time"),
        "latest_expiration_time": summary.get("latest_expiration_time"),
        "occurrence_time": summary.get("occurrence_time"),
        "occurrence_datetime": summary.get("occurrence_datetime"),
        "occurrence_raw_value": summary.get("occurrence_raw_value"),
        "occurrence_semantic_classification": summary.get(
            "occurrence_semantic_classification"
        ),
        "occurrence_included_as_safety_bound": summary.get(
            "occurrence_included_as_safety_bound"
        ),
        "occurrence_equals_close_time": summary.get("occurrence_equals_close_time"),
        "occurrence_equals_expected_expiration_time": summary.get(
            "occurrence_equals_expected_expiration_time"
        ),
        "dual_interpretation_pass": summary.get("dual_interpretation_pass"),
        "settlement_time": summary.get("settlement_time"),
        "settlement_ts": summary.get("settlement_ts"),
        "listed_expiration": summary.get("listed_expiration"),
        "can_close_early": summary.get("can_close_early"),
        "early_close_condition": summary.get("early_close_condition"),
        "early_close_deadline": summary.get("early_close_deadline"),
        "early_close_deadline_authoritative": summary.get(
            "early_close_deadline_authoritative"
        ),
        "selected_at_utc": summary.get("selected_at_utc"),
        "campaign_expected_end_utc": summary.get("campaign_expected_end_utc"),
        "campaign_required_end_utc": summary.get("campaign_required_end_utc"),
        "time_to_close_at_launch_seconds": summary.get("time_to_close_at_launch_seconds"),
        "time_to_lifecycle_deadline_at_launch_seconds": summary.get(
            "time_to_lifecycle_deadline_at_launch_seconds"
        ),
        "lifecycle_deadline": summary.get("lifecycle_deadline"),
        "lifecycle_deadline_components": summary.get(
            "lifecycle_deadline_components", {}
        ),
        "selection_profile": summary.get("selection_profile"),
        "selection_profile_version": summary.get("selection_profile_version"),
        "selection_profile_hash": summary.get("selection_profile_hash"),
        "selection_safety_buffer_seconds": summary.get("selection_safety_buffer_seconds"),
        "selection_reason": summary.get("selection_reason"),
        "selection_gate_result": summary.get("selection_gate_result"),
        "selection_gate_rejection_reason": summary.get("selection_gate_rejection_reason"),
        "market_discovery_pages": summary.get("market_discovery_pages"),
        "market_discovery_count": summary.get("market_discovery_count"),
        "market_discovery_cursor_remaining": summary.get("market_discovery_cursor_remaining"),
        "market_discovery_rejection_counts": summary.get(
            "market_discovery_rejection_counts", {}
        ),
        "validation_status": (validation or {}).get("status") or summary.get("validation_status"),
        "evidence_classification": (validation or {}).get("evidence_classification")
        or summary.get("evidence_classification"),
        "event_count": summary.get("event_count", 0),
        "snapshot_count": summary.get("snapshot_count", 0),
        "delta_count": summary.get("delta_count", 0),
        "trade_count": summary.get("trade_count", 0),
        "status_update_count": summary.get("status_update_count", 0),
        "heartbeat_count": summary.get("heartbeat_count", 0),
        "disconnect_count": summary.get("disconnect_count", 0),
        "reconnect_count": summary.get("reconnect_count", 0),
        "gap_count": summary.get("gap_count", 0),
        "last_event_time": summary.get("last_event_time"),
        "stale_seconds": summary.get("stale_seconds"),
        "supervisor_liveness_status": summary.get("supervisor_liveness_status"),
        "campaign_process_liveness_status": summary.get("campaign_process_liveness_status"),
        "websocket_message_freshness_status": summary.get("websocket_message_freshness_status"),
        "market_lifecycle_status": (validation or {}).get("market_lifecycle_status")
        or _market_lifecycle_status(summary),
        "exchange_heartbeat_status": summary.get("exchange_heartbeat_status") or "UNKNOWN",
        "rebuild_frame_count": summary.get("rebuild_frame_count", 0),
        "live_gate_status": summary.get("live_gate_status"),
        "submit_attempts": summary.get("submit_attempts", summary.get("submit_attempt_count", 0)),
        "connection_established": summary.get("connection_established"),
        "subscription_acknowledged": summary.get("subscription_acknowledged"),
        "market_tickers": summary.get("market_tickers", []),
        "credential_presence": summary.get("credential_presence"),
        "raw_event_path": summary.get("raw_data_path_redacted"),
        "raw_event_sha256": summary.get("raw_event_sha256"),
        "raw_data_path_redacted": summary.get("raw_data_path_redacted"),
        "manifest_path": summary.get("manifest_path"),
        "validation_report_path": summary.get("validation_report_path"),
        "strict_verdict": "STRICT NO-GO",
    }
    if summary.get("blocker"):
        manifest["blocker"] = summary["blocker"]
    if summary.get("blocker_code"):
        manifest["blocker_code"] = summary["blocker_code"]
    _write_json(root / "campaign_manifest.json", manifest)


def _write_run_metadata(
    root: Path,
    summary: dict[str, object],
    *,
    validation: dict[str, object] | None,
) -> None:
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": summary.get("campaign_id"),
        "generated_at_utc": summary.get("generated_at_utc"),
        "duration_seconds": summary.get("duration_seconds"),
        "mode": summary.get("mode"),
        "status": summary.get("status"),
        "market_ticker": summary.get("market_ticker") or summary.get("market"),
        "market_status": summary.get("market_status") or summary.get("status_at_launch"),
        "raw_market_status": summary.get("raw_market_status"),
        "close_time": summary.get("close_time"),
        "campaign_expected_end_utc": summary.get("campaign_expected_end_utc"),
        "selection_gate_result": summary.get("selection_gate_result"),
        "selection_gate_rejection_reason": summary.get("selection_gate_rejection_reason"),
        "market_discovery_pages": summary.get("market_discovery_pages"),
        "market_discovery_count": summary.get("market_discovery_count"),
        "market_discovery_cursor_remaining": summary.get("market_discovery_cursor_remaining"),
        "market_discovery_rejection_counts": summary.get(
            "market_discovery_rejection_counts", {}
        ),
        "validation_status": (validation or {}).get("status") or summary.get("validation_status"),
        "evidence_classification": (validation or {}).get("evidence_classification")
        or summary.get("evidence_classification"),
        "live_gate_status": summary.get("live_gate_status"),
        "production_endpoint_used": summary.get("production_endpoint_used"),
        "submit_attempts": summary.get("submit_attempts", summary.get("submit_attempt_count", 0)),
        "credential_presence": summary.get("credential_presence"),
        "connection_established": summary.get("connection_established"),
        "subscription_acknowledged": summary.get("subscription_acknowledged"),
        "raw_data_path_redacted": summary.get("raw_data_path_redacted"),
        "strict_verdict": "STRICT NO-GO",
    }
    if summary.get("blocker"):
        metadata["blocker"] = summary["blocker"]
    if summary.get("blocker_code"):
        metadata["blocker_code"] = summary["blocker_code"]
    _write_json(root / "run_metadata.json", metadata)


def discover_kalshi_demo_ws_market(
    *,
    duration_seconds: int,
    safety_buffer_seconds: int,
    selected_at_utc: datetime,
    client: KalshiDemoMarketDataClient | None = None,
    max_pages: int = MAX_MARKET_DISCOVERY_PAGES,
    max_event_pages: int = MAX_EVENT_DISCOVERY_PAGES,
    max_event_fallback_requests: int = MAX_EVENT_FALLBACK_REQUESTS,
    selection_profile: SelectionProfile | str | None = None,
    eligible_market_limit: int | None = None,
    max_orderbook_probes: int | None = None,
) -> dict[str, object]:
    """Find one lifecycle-eligible Demo market with bounded complete discovery."""

    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    if max_event_pages < 1:
        raise ValueError("max_event_pages must be at least 1")
    if max_event_fallback_requests < 1:
        raise ValueError("max_event_fallback_requests must be at least 1")
    if eligible_market_limit is not None and eligible_market_limit < 1:
        raise ValueError("eligible_market_limit must be at least 1")
    if max_orderbook_probes is not None and max_orderbook_probes < 1:
        raise ValueError("max_orderbook_probes must be at least 1")
    active_client = client or KalshiDemoMarketDataClient()
    owns_client = client is None
    cursor: str | None = None
    pages_attempted = 0
    pages_fetched = 0
    diagnostics: dict[str, Any] = {
        "coverage_complete": False,
        "event_page_requests": 0,
        "event_pages_completed": 0,
        "event_final_cursor_empty": False,
        "event_pagination_complete": False,
        "event_metadata_source": "documented_open_event_pagination_with_exact_fallback",
        "discovery_protocol_version": DISCOVERY_PROTOCOL_VERSION,
        "event_page_limit": EVENT_DISCOVERY_PAGE_LIMIT,
        "max_event_pages": max_event_pages,
        "event_status_filter": "open",
        "market_mve_filter": "exclude",
        "max_event_fallback_requests": max_event_fallback_requests,
        "event_fallback_request_limit_reached": False,
        "single_event_fallback_requests": 0,
        "orderbook_requests": 0,
        "retry_count": 0,
        "rate_limit_count": 0,
        "server_error_count": 0,
        "http_status_counts": {},
        "timeout_count": 0,
        "connection_error_count": 0,
        "parse_schema_failure_count": 0,
        "candidate_local_failure_count": 0,
    }
    raw_normalized_markets: list[dict[str, object]] = []
    profile = (
        SelectionProfile(selection_profile)
        if selection_profile is not None
        else selection_profile_for_duration(duration_seconds)
    )
    require_event_metadata = profile is not SelectionProfile.SMOKE
    diagnostics.update(
        {
            "selection_profile": profile.value,
            "selection_profile_version": SELECTION_PROFILE_VERSION,
            "selection_profile_hash": selection_profile_hash(
                profile,
                duration_seconds=duration_seconds,
                safety_buffer_seconds=safety_buffer_seconds,
            ),
        }
    )
    try:
        for _ in range(max_pages):
            pages_attempted += 1
            payload, error = _discovery_request(
                lambda cursor=cursor: active_client.list_markets(
                    limit=MARKET_DISCOVERY_PAGE_LIMIT,
                    cursor=cursor,
                    status="open",
                    mve_filter="exclude",
                ),
                diagnostics,
            )
            if error or not isinstance(payload, Mapping):
                return _market_discovery_blocker(
                    "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR",
                    pages_fetched=pages_fetched,
                    markets_seen=len(raw_normalized_markets),
                    rejection_counts={},
                    cursor_remaining=bool(cursor),
                    diagnostics={**diagnostics, "pages_attempted": pages_attempted},
                )
            pages_fetched += 1
            raw_markets = payload.get("markets", [])
            raw_normalized_markets.extend(
                normalize_kalshi_market_metadata(item)
                for item in raw_markets
                if isinstance(item, Mapping)
            )

            next_cursor = payload.get("cursor")
            cursor = next_cursor if isinstance(next_cursor, str) and next_cursor else None
            if cursor is None:
                break

        diagnostics.update(
            {
                "pages_attempted": pages_attempted,
                "pages_completed": pages_fetched,
                "final_cursor_empty": cursor is None,
                "max_pages_reached": cursor is not None and pages_fetched == max_pages,
                "raw_market_count": len(raw_normalized_markets),
            }
        )
        normalized_markets, duplicate_market_count = _deduplicate_discovery_markets(
            raw_normalized_markets
        )
        diagnostics.update(
            {
                "distinct_market_count": len(normalized_markets),
                "duplicate_market_count": duplicate_market_count,
            }
        )
        if cursor is not None:
            return _market_discovery_blocker(
                "DEMO_MARKET_DISCOVERY_INCOMPLETE_PAGE_LIMIT",
                pages_fetched=pages_fetched,
                markets_seen=len(normalized_markets),
                rejection_counts={},
                cursor_remaining=True,
                diagnostics=diagnostics,
            )

        event_cache: dict[str, Mapping[str, object]] = {}
        if require_event_metadata:
            requested_event_tickers = sorted(
                {
                    str(market.get("event_ticker"))
                    for market in normalized_markets
                    if market.get("event_ticker")
                }
            )
            requested_event_ticker_set = set(requested_event_tickers)
            diagnostics["unique_event_tickers"] = len(requested_event_tickers)
            event_cursor: str | None = None
            raw_event_count = 0
            duplicate_event_count = 0
            for _ in range(max_event_pages):
                diagnostics["event_page_requests"] += 1
                payload, error = _discovery_request(
                    lambda event_cursor=event_cursor: active_client.list_events(
                        limit=EVENT_DISCOVERY_PAGE_LIMIT,
                        cursor=event_cursor,
                        status="open",
                    ),
                    diagnostics,
                )
                if error or not isinstance(payload, Mapping):
                    return _market_discovery_blocker(
                        "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR",
                        pages_fetched=pages_fetched,
                        markets_seen=len(normalized_markets),
                        rejection_counts={},
                        cursor_remaining=bool(cursor),
                        diagnostics={**diagnostics, "pages_attempted": pages_attempted},
                    )
                diagnostics["event_pages_completed"] += 1
                for event in payload.get("events", []):
                    if isinstance(event, Mapping) and event.get("event_ticker"):
                        raw_event_count += 1
                        event_ticker = str(event["event_ticker"])
                        if event_ticker in event_cache:
                            duplicate_event_count += 1
                        if event_ticker in requested_event_ticker_set:
                            event_cache[event_ticker] = event

                next_event_cursor = payload.get("cursor")
                event_cursor = (
                    next_event_cursor
                    if isinstance(next_event_cursor, str) and next_event_cursor
                    else None
                )
                if event_cursor is None:
                    break

            diagnostics.update(
                {
                    "raw_event_count": raw_event_count,
                    "matched_event_count": len(event_cache),
                    "duplicate_event_count": duplicate_event_count,
                    "event_final_cursor_empty": event_cursor is None,
                    "event_pagination_complete": event_cursor is None,
                    "event_max_pages_reached": event_cursor is not None,
                }
            )
            if event_cursor is not None:
                return _market_discovery_blocker(
                    "DEMO_EVENT_DISCOVERY_INCOMPLETE_PAGE_LIMIT",
                    pages_fetched=pages_fetched,
                    markets_seen=len(normalized_markets),
                    rejection_counts={},
                    cursor_remaining=False,
                    diagnostics={**diagnostics, "pages_attempted": pages_attempted},
                )

            missing = [
                ticker
                for ticker in requested_event_tickers
                if ticker not in event_cache
            ]
            diagnostics["missing_event_ticker_count"] = len(missing)
            for ticker in missing:
                if (
                    diagnostics["single_event_fallback_requests"]
                    >= max_event_fallback_requests
                ):
                    diagnostics["event_fallback_request_limit_reached"] = True
                    return _market_discovery_blocker(
                        "DEMO_EVENT_DISCOVERY_FALLBACK_LIMIT",
                        pages_fetched=pages_fetched,
                        markets_seen=len(normalized_markets),
                        rejection_counts={},
                        cursor_remaining=False,
                        diagnostics={
                            **diagnostics,
                            "pages_attempted": pages_attempted,
                        },
                    )
                diagnostics["single_event_fallback_requests"] += 1
                event, error = _discovery_request(
                    lambda ticker=ticker: active_client.get_event(ticker), diagnostics
                )
                if error in {"HTTP_404", "RESPONSE_SCHEMA_ERROR"}:
                    diagnostics["candidate_local_failure_count"] += 1
                    continue
                if error or not isinstance(event, Mapping):
                    return _market_discovery_blocker(
                        "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR",
                        pages_fetched=pages_fetched,
                        markets_seen=len(normalized_markets),
                        rejection_counts={},
                        cursor_remaining=bool(cursor),
                        diagnostics={**diagnostics, "pages_attempted": pages_attempted},
                    )
                event_cache[ticker] = event

        audit_rows: list[tuple[dict[str, object], list[str]]] = []
        lifecycle_candidates: list[
            tuple[dict[str, object], dict[str, object], list[str]]
        ] = []
        event_metadata_complete_count = 0
        for market_metadata in normalized_markets:
            candidate_metadata = market_metadata
            reasons: list[str] = []
            if require_event_metadata:
                event_ticker = str(market_metadata.get("event_ticker") or "")
                event = event_cache.get(event_ticker)
                if event is None:
                    reasons.append("EVENT_METADATA_FETCH_FAILED")
                else:
                    try:
                        candidate_metadata = _merge_event_metadata(market_metadata, event)
                        event_metadata_complete_count += 1
                    except KalshiResponseError:
                        reasons.append("EVENT_METADATA_INCOMPLETE")
            policy_reasons = _market_selection_rejection_reasons(
                candidate_metadata,
                selected_at_utc=selected_at_utc,
                campaign_required_end=selected_at_utc
                + timedelta(seconds=duration_seconds + safety_buffer_seconds),
                profile=profile,
                require_non_empty_orderbook=False,
                require_event_metadata=require_event_metadata,
                allow_sports_long_horizon=False,
            )
            reasons.extend(
                reason for reason in policy_reasons if reason not in reasons
            )
            audit_rows.append((candidate_metadata, reasons))
            if not reasons:
                selection = evaluate_market_selection(
                    candidate_metadata,
                    selected_at_utc=selected_at_utc,
                    duration_seconds=duration_seconds,
                    safety_buffer_seconds=safety_buffer_seconds,
                    selection_reason="kalshi_demo_paginated_market_discovery",
                    require_non_empty_orderbook=False,
                    require_event_metadata=require_event_metadata,
                    selection_profile=profile,
                )
                lifecycle_candidates.append((candidate_metadata, selection, reasons))

        lifecycle_candidates.sort(
            key=lambda item: (
                _as_bool(item[0].get("can_close_early")),
                -int(item[1].get("time_to_lifecycle_deadline_at_launch_seconds") or 0),
                not _has_current_quote_indicator(item[0]),
            )
        )
        diagnostics.update(
            {
                "normalized_open_count": sum(
                    market.get("status") in OPEN_MARKET_STATUSES
                    for market in normalized_markets
                ),
                "event_metadata_complete_count": event_metadata_complete_count,
                "lifecycle_candidate_count": len(lifecycle_candidates),
                "non_sports_count": sum(
                    _event_metadata_fetched(metadata) and not _is_sports_market(metadata)
                    for metadata, _reasons in audit_rows
                ),
                "eligible_market_limit": eligible_market_limit,
                "max_orderbook_probes": max_orderbook_probes,
                "orderbook_candidate_count": len(lifecycle_candidates),
            }
        )
        eligible_candidates: list[tuple[dict[str, object], dict[str, object]]] = []
        orderbook_candidate_scan_complete = True
        orderbook_probe_limit_reached = False
        for candidate_index, (candidate_metadata, _selection, reasons) in enumerate(
            lifecycle_candidates
        ):
            if (
                max_orderbook_probes is not None
                and diagnostics["orderbook_requests"] >= max_orderbook_probes
            ):
                orderbook_candidate_scan_complete = False
                orderbook_probe_limit_reached = True
                break
            ticker = candidate_metadata.get("ticker") or candidate_metadata.get("market_ticker")
            if not isinstance(ticker, str) or not ticker:
                reasons.append("MISSING_MARKET_METADATA")
                continue
            diagnostics["orderbook_requests"] += 1
            orderbook, error = _discovery_request(
                lambda ticker=ticker: active_client.get_market_orderbook(ticker), diagnostics
            )
            if error in {"EMPTY_ORDERBOOK", "HTTP_404", "RESPONSE_SCHEMA_ERROR"}:
                reasons.append(error)
                diagnostics["candidate_local_failure_count"] += 1
                continue
            if error or not isinstance(orderbook, Mapping):
                audit = _discovery_audit_summary(
                    audit_rows,
                    selected_at_utc=selected_at_utc,
                    duration_seconds=duration_seconds,
                    safety_buffer_seconds=safety_buffer_seconds,
                    selection_profile=profile,
                )
                diagnostics.update(
                    {
                        "rejection_overlap_counts": audit["rejection_overlap_counts"],
                        "occurrence_semantic_counts": audit[
                            "occurrence_semantic_counts"
                        ],
                        "occurrence_equality_counts": audit[
                            "occurrence_equality_counts"
                        ],
                        "dual_interpretation_pass_count": audit[
                            "dual_interpretation_pass_count"
                        ],
                    }
                )
                return _market_discovery_blocker(
                    "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR",
                    pages_fetched=pages_fetched,
                    markets_seen=len(normalized_markets),
                    rejection_counts=audit["rejection_counts"],
                    cursor_remaining=bool(cursor),
                    diagnostics={**diagnostics, "pages_attempted": pages_attempted},
                    multi_label_rejection_counts=audit[
                        "multi_label_rejection_counts"
                    ],
                    near_misses=audit["near_misses"],
                )
            book = orderbook["orderbook_fp"]
            level_count = len(book["yes_dollars"]) + len(book["no_dollars"])
            selected_metadata = {**candidate_metadata, "orderbook_level_count": level_count}
            selected = evaluate_market_selection(
                selected_metadata,
                selected_at_utc=selected_at_utc,
                duration_seconds=duration_seconds,
                safety_buffer_seconds=safety_buffer_seconds,
                selection_reason="kalshi_demo_paginated_market_discovery",
                require_event_metadata=require_event_metadata,
                selection_profile=profile,
            )
            final_reasons = _market_selection_rejection_reasons(
                selected_metadata,
                selected_at_utc=selected_at_utc,
                campaign_required_end=selected_at_utc
                + timedelta(seconds=duration_seconds + safety_buffer_seconds),
                profile=profile,
                require_non_empty_orderbook=True,
                require_event_metadata=require_event_metadata,
                allow_sports_long_horizon=False,
            )
            if final_reasons:
                reasons.extend(reason for reason in final_reasons if reason not in reasons)
                continue
            eligible_candidates.append((selected_metadata, selected))
            if (
                eligible_market_limit is not None
                and len(eligible_candidates) >= eligible_market_limit
            ):
                orderbook_candidate_scan_complete = (
                    candidate_index + 1 == len(lifecycle_candidates)
                )
                break

        audit = _discovery_audit_summary(
            audit_rows,
            selected_at_utc=selected_at_utc,
            duration_seconds=duration_seconds,
            safety_buffer_seconds=safety_buffer_seconds,
            selection_profile=profile,
        )
        diagnostics.update(
            {
                "coverage_complete": True,
                "eligible_count": len(eligible_candidates),
                "eligible_count_complete": orderbook_candidate_scan_complete,
                "eligible_count_is_lower_bound": not orderbook_candidate_scan_complete,
                "orderbook_candidate_scan_complete": orderbook_candidate_scan_complete,
                "orderbook_probe_limit_reached": orderbook_probe_limit_reached,
                "all_markets_multilabel_evaluated": len(audit_rows)
                == len(normalized_markets),
                "rejection_overlap_counts": audit["rejection_overlap_counts"],
                "occurrence_semantic_counts": audit["occurrence_semantic_counts"],
                "occurrence_equality_counts": audit["occurrence_equality_counts"],
                "dual_interpretation_pass_count": audit[
                    "dual_interpretation_pass_count"
                ],
            }
        )
        if eligible_candidates:
            selected_metadata, selected = eligible_candidates[0]
            selected = {
                **selected,
                "market_discovery_pages": pages_fetched,
                "market_discovery_count": len(normalized_markets),
                "market_discovery_cursor_remaining": False,
                "market_discovery_coverage_complete": True,
                "market_discovery_orderbook_requests": diagnostics[
                    "orderbook_requests"
                ],
                "market_discovery_orderbook_candidate_count": diagnostics[
                    "orderbook_candidate_count"
                ],
                "market_discovery_orderbook_candidate_scan_complete": diagnostics[
                    "orderbook_candidate_scan_complete"
                ],
                "market_discovery_eligible_count": len(eligible_candidates),
                "market_discovery_eligible_count_complete": diagnostics[
                    "eligible_count_complete"
                ],
                "market_discovery_eligible_count_is_lower_bound": diagnostics[
                    "eligible_count_is_lower_bound"
                ],
                "market_discovery_eligible_market_limit": eligible_market_limit,
                "market_discovery_max_orderbook_probes": max_orderbook_probes,
                "market_discovery_orderbook_probe_limit_reached": False,
                **_discovery_selection_diagnostics(diagnostics),
            }
            return {
                "market_metadata": selected_metadata,
                "selection": selected,
                "blocker_code": None,
                "pages_fetched": pages_fetched,
                "markets_seen": len(normalized_markets),
                "rejection_counts": audit["rejection_counts"],
                "multi_label_rejection_counts": audit[
                    "multi_label_rejection_counts"
                ],
                "rejection_overlap_counts": audit["rejection_overlap_counts"],
                "occurrence_semantic_counts": audit["occurrence_semantic_counts"],
                "occurrence_equality_counts": audit["occurrence_equality_counts"],
                "dual_interpretation_pass_count": audit[
                    "dual_interpretation_pass_count"
                ],
                "near_misses": audit["near_misses"],
                "cursor_remaining": False,
                "coverage_complete": True,
                "eligible_count": len(eligible_candidates),
                "selection_profile_version": SELECTION_PROFILE_VERSION,
                "selection_profile_hash": diagnostics["selection_profile_hash"],
                "diagnostics": diagnostics,
            }

        if orderbook_probe_limit_reached:
            blocker_code = "DEMO_MARKET_DISCOVERY_ORDERBOOK_PROBE_LIMIT"
        else:
            blocker_code = (
                "DEMO_NO_OPEN_MARKETS"
                if not normalized_markets
                else "DEMO_NO_ELIGIBLE_MARKET"
            )
        return _market_discovery_blocker(
            blocker_code,
            pages_fetched=pages_fetched,
            markets_seen=len(normalized_markets),
            rejection_counts=audit["rejection_counts"],
            cursor_remaining=False,
            diagnostics=diagnostics,
            multi_label_rejection_counts=audit["multi_label_rejection_counts"],
            near_misses=audit["near_misses"],
        )
    finally:
        if owns_client:
            active_client.close()


def _deduplicate_discovery_markets(
    markets: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    seen: set[str] = set()
    deduplicated: list[dict[str, object]] = []
    duplicate_count = 0
    for market in markets:
        ticker = str(market.get("ticker") or market.get("market_ticker") or "").strip()
        if ticker and ticker in seen:
            duplicate_count += 1
            continue
        if ticker:
            seen.add(ticker)
        deduplicated.append(market)
    return deduplicated, duplicate_count


def _discovery_audit_summary(
    rows: list[tuple[dict[str, object], list[str]]],
    *,
    selected_at_utc: datetime,
    duration_seconds: int,
    safety_buffer_seconds: int,
    selection_profile: SelectionProfile,
) -> dict[str, Any]:
    rejection_counts: Counter[str] = Counter()
    multi_label_rejection_counts: Counter[str] = Counter()
    rejection_overlap_counts: Counter[str] = Counter()
    occurrence_semantic_counts: Counter[str] = Counter()
    occurrence_equality_counts: Counter[str] = Counter()
    dual_interpretation_pass_count = 0
    near_misses: list[dict[str, object]] = []
    required_end = selected_at_utc + timedelta(
        seconds=duration_seconds + safety_buffer_seconds
    )
    profile = selection_profile
    for metadata, reasons in rows:
        if reasons:
            rejection_counts[reasons[0]] += 1
            multi_label_rejection_counts.update(reasons)
            for index, left in enumerate(sorted(set(reasons))):
                for right in sorted(set(reasons))[index + 1 :]:
                    rejection_overlap_counts[f"{left}|{right}"] += 1
        policy = _lifecycle_policy_evidence(
            metadata,
            selected_at_utc=selected_at_utc,
            campaign_required_end=required_end,
            profile=profile,
        )
        occurrence_semantic_counts[
            str(policy["occurrence_semantic_classification"])
        ] += 1
        if policy["dual_interpretation_pass"] is True:
            dual_interpretation_pass_count += 1
        if policy["occurrence_equals_close_time"] is True:
            occurrence_equality_counts["equals_close_time"] += 1
        if policy["occurrence_equals_expected_expiration_time"] is True:
            occurrence_equality_counts["equals_expected_expiration_time"] += 1
        deadline = policy["conservative_lifecycle_deadline"]
        deadline_source = next(
            (
                field
                for field in (
                    "close_time",
                    "expected_expiration_time",
                    "early_close_deadline",
                    "occurrence_safety_bound",
                )
                if policy[field] == deadline
            ),
            None,
        )
        margin = int((deadline - required_end).total_seconds()) if deadline else None
        close_time = policy["close_time"]
        expected_expiration = policy["expected_expiration_time"]
        market_id = str(
            metadata.get("ticker") or metadata.get("market_ticker") or ""
        ).strip()
        event_id = str(metadata.get("event_ticker") or "").strip()
        near_misses.append(
            {
                "market_id_hash": hashlib.sha256(market_id.encode("utf-8")).hexdigest()[:16]
                if market_id
                else None,
                "event_id_hash": hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:16]
                if event_id
                else None,
                "primary_rejection_reason": reasons[0] if reasons else None,
                "lifecycle_deadline_source": deadline_source,
                "lifecycle_margin_seconds": margin,
                "close_margin_seconds": int((close_time - required_end).total_seconds())
                if close_time
                else None,
                "expected_expiration_margin_seconds": int(
                    (expected_expiration - required_end).total_seconds()
                )
                if expected_expiration
                else None,
                "occurrence_semantic_classification": policy[
                    "occurrence_semantic_classification"
                ],
                "occurrence_margin_seconds": int(
                    (policy["occurrence_safety_bound"] - required_end).total_seconds()
                )
                if policy["occurrence_safety_bound"]
                else None,
                "dual_interpretation_pass": policy["dual_interpretation_pass"],
                "can_close_early": _as_optional_bool(metadata.get("can_close_early")),
                "event_category_class": (
                    "sports" if _is_sports_market(metadata) else "non_sports"
                ),
                "match_like": _is_match_event(metadata),
                "current_quote_indicator": _has_current_quote_indicator(metadata),
            }
        )
    near_misses.sort(
        key=lambda item: (
            abs(item["lifecycle_margin_seconds"])
            if isinstance(item["lifecycle_margin_seconds"], int)
            else sys.maxsize,
            str(item["market_id_hash"] or ""),
        )
    )
    return {
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "multi_label_rejection_counts": dict(
            sorted(multi_label_rejection_counts.items())
        ),
        "rejection_overlap_counts": dict(sorted(rejection_overlap_counts.items())),
        "occurrence_semantic_counts": dict(sorted(occurrence_semantic_counts.items())),
        "occurrence_equality_counts": dict(sorted(occurrence_equality_counts.items())),
        "dual_interpretation_pass_count": dual_interpretation_pass_count,
        "near_misses": near_misses[:DISCOVERY_NEAR_MISS_LIMIT],
    }


def _with_event_metadata(
    client: KalshiDemoMarketDataClient,
    market_metadata: Mapping[str, object],
) -> dict[str, object]:
    event_ticker = market_metadata.get("event_ticker")
    if not isinstance(event_ticker, str) or not event_ticker:
        raise KalshiResponseError("selected market has no event_ticker")
    return _merge_event_metadata(market_metadata, client.get_event(event_ticker))


def _merge_event_metadata(
    market_metadata: Mapping[str, object], event: Mapping[str, object]
) -> dict[str, object]:
    if not event.get("category") or not event.get("title"):
        raise KalshiResponseError("event metadata missing category or title")
    return {
        **market_metadata,
        "event_metadata_fetched": True,
        "event_category": event.get("category"),
        "event_title": event.get("title"),
        "event_subtitle": event.get("sub_title") or event.get("subtitle"),
        "event_type": event.get("event_type"),
        "series_ticker": event.get("series_ticker"),
    }


def _market_discovery_blocker(
    blocker_code: str,
    *,
    pages_fetched: int,
    markets_seen: int,
    rejection_counts: Mapping[str, int],
    cursor_remaining: bool = False,
    diagnostics: Mapping[str, object] | None = None,
    multi_label_rejection_counts: Mapping[str, int] | None = None,
    near_misses: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    detail = dict(diagnostics or {})
    return {
        "market_metadata": None,
        "selection": None,
        "blocker_code": blocker_code,
        "pages_fetched": pages_fetched,
        "markets_seen": markets_seen,
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "multi_label_rejection_counts": dict(
            sorted((multi_label_rejection_counts or {}).items())
        ),
        "rejection_overlap_counts": detail.get("rejection_overlap_counts", {}),
        "occurrence_semantic_counts": detail.get("occurrence_semantic_counts", {}),
        "occurrence_equality_counts": detail.get("occurrence_equality_counts", {}),
        "dual_interpretation_pass_count": detail.get(
            "dual_interpretation_pass_count", 0
        ),
        "near_misses": list(near_misses or []),
        "cursor_remaining": cursor_remaining,
        "coverage_complete": detail.get("coverage_complete") is True,
        "eligible_count": 0,
        "selection_profile_version": detail.get("selection_profile_version"),
        "selection_profile_hash": detail.get("selection_profile_hash"),
        "diagnostics": detail,
    }


def _discovery_request(
    operation: Callable[[], Any], diagnostics: dict[str, Any]
) -> tuple[Any | None, str | None]:
    for attempt in range(1, DISCOVERY_MAX_ATTEMPTS + 1):
        try:
            result = operation()
            _increment_status(diagnostics, 200)
            return result, None
        except KalshiEmptyOrderBookError:
            return None, "EMPTY_ORDERBOOK"
        except KalshiHTTPError as exc:
            _increment_status(diagnostics, exc.status_code)
            code = f"HTTP_{exc.status_code}"
            retryable = exc.status_code == 429 or exc.status_code >= 500
            if retryable and attempt < DISCOVERY_MAX_ATTEMPTS:
                diagnostics["retry_count"] += 1
                time.sleep((0.1 * (2 ** (attempt - 1))) + random.uniform(0, 0.05))
                continue
            return None, code
        except KalshiResponseError:
            diagnostics["parse_schema_failure_count"] += 1
            return None, "RESPONSE_SCHEMA_ERROR"
        except KalshiClientError as exc:
            cause = exc.__cause__
            if isinstance(cause, httpx.TimeoutException):
                diagnostics["timeout_count"] += 1
                code = "TRANSPORT_TIMEOUT"
            else:
                diagnostics["connection_error_count"] += 1
                code = "CONNECTION_ERROR"
            if attempt < DISCOVERY_MAX_ATTEMPTS:
                diagnostics["retry_count"] += 1
                time.sleep(0.1 * (2 ** (attempt - 1)))
                continue
            return None, code
    return None, "CONNECTION_ERROR"


def _increment_status(diagnostics: dict[str, Any], status_code: int) -> None:
    counts = diagnostics["http_status_counts"]
    key = str(status_code)
    counts[key] = counts.get(key, 0) + 1
    if status_code == 429:
        diagnostics["rate_limit_count"] += 1
    if status_code >= 500:
        diagnostics["server_error_count"] += 1


def _has_current_quote_indicator(market_metadata: Mapping[str, object]) -> bool:
    for field in (
        "yes_bid_size_fp",
        "yes_ask_size_fp",
        "no_bid_size_fp",
        "no_ask_size_fp",
    ):
        try:
            if Decimal(str(market_metadata.get(field) or "0")) > 0:
                return True
        except InvalidOperation:
            continue
    return False


def _read_json(path: Path, failures: list[str]) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{path.name} unreadable: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path, failures: list[str]) -> list[dict[str, object]]:
    try:
        return list(read_jsonl_records(path))
    except (OSError, ValueError) as exc:
        failures.append(f"{path.name} unreadable: {exc}")
        return []


def _read_optional_jsonl(path: Path, failures: list[str]) -> list[dict[str, object]]:
    return _read_jsonl(path, failures) if path.exists() else []


def _secret_like_files(input_dir: Path) -> bool:
    for path in sorted(input_dir.glob("*.json*")):
        try:
            for payload in _payloads(path):
                if _has_secret_key(payload):
                    return True
        except (OSError, json.JSONDecodeError, ValueError):
            return True
    return False


def _payloads(path: Path) -> list[object]:
    if path.suffix == ".jsonl":
        return list(read_jsonl_records(path))
    return [json.loads(path.read_text(encoding="utf-8"))]


def _has_secret_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in ALLOWED_SECRET_LIKE_KEYS:
                continue
            if any(part in lowered for part in SECRET_KEY_PARTS):
                return True
            if _has_secret_key(item):
                return True
    if isinstance(value, list):
        return any(_has_secret_key(item) for item in value)
    return False


def _as_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _default_lifecycle_record(
    market: str,
    selected_at_utc: datetime,
    duration_seconds: int,
) -> dict[str, object]:
    profile = selection_profile_for_duration(duration_seconds)
    return {
        "market_ticker": market,
        "event_ticker": None,
        "title": None,
        "name": None,
        "status_at_launch": None,
        "market_status": None,
        "raw_market_status": None,
        "event_category": None,
        "event_title": None,
        "event_subtitle": None,
        "event_type": None,
        "event_metadata_fetched": False,
        "category": None,
        "market_type": None,
        "open_time": None,
        "close_time": None,
        "expected_expiration": None,
        "expected_expiration_time": None,
        "latest_expiration_time": None,
        "occurrence_time": None,
        "occurrence_datetime": None,
        "occurrence_raw_value": None,
        "occurrence_semantic_classification": "MISSING",
        "occurrence_included_as_safety_bound": False,
        "occurrence_equals_close_time": False,
        "occurrence_equals_expected_expiration_time": False,
        "dual_interpretation_pass": None,
        "lifecycle_deadline_components": {
            "close_time": None,
            "expected_expiration_time": None,
            "early_close_deadline": None,
            "occurrence_safety_bound": None,
        },
        "settlement_time": None,
        "settlement_ts": None,
        "listed_expiration": None,
        "can_close_early": None,
        "early_close_condition": None,
        "early_close_deadline": None,
        "early_close_deadline_authoritative": False,
        "selected_at_utc": selected_at_utc.isoformat(),
        "campaign_expected_end_utc": (
            selected_at_utc + timedelta(seconds=duration_seconds)
        ).isoformat(),
        "campaign_required_end_utc": (
            selected_at_utc
            + timedelta(seconds=duration_seconds + DEFAULT_SELECTION_SAFETY_BUFFER_SECONDS)
        ).isoformat(),
        "time_to_close_at_launch_seconds": None,
        "time_to_lifecycle_deadline_at_launch_seconds": None,
        "lifecycle_deadline": None,
        "selection_profile": profile.value,
        "selection_profile_version": SELECTION_PROFILE_VERSION,
        "selection_profile_hash": selection_profile_hash(
            profile,
            duration_seconds=duration_seconds,
            safety_buffer_seconds=selection_safety_buffer_seconds(profile),
        ),
        "selection_safety_buffer_seconds": selection_safety_buffer_seconds(profile),
        "selection_reason": "bounded_smoke",
        "selection_gate_result": "not_required",
        "selection_gate_rejection_reason": None,
        "market_lifecycle_status": "UNKNOWN",
    }


def _market_lifecycle_record(
    market_metadata: Mapping[str, object],
    *,
    selected_at_utc: datetime,
    duration_seconds: int,
    safety_buffer_seconds: int,
    selection_reason: str,
    result: str,
    reason: str | None,
    selection_profile: SelectionProfile,
) -> dict[str, object]:
    campaign_required_end = selected_at_utc + timedelta(
        seconds=duration_seconds + safety_buffer_seconds
    )
    policy = _lifecycle_policy_evidence(
        market_metadata,
        selected_at_utc=selected_at_utc,
        campaign_required_end=campaign_required_end,
        profile=selection_profile,
    )
    close_time = policy["close_time"]
    lifecycle_deadline = policy["conservative_lifecycle_deadline"]
    market_ticker = (
        market_metadata.get("market_ticker")
        or market_metadata.get("ticker")
        or market_metadata.get("market")
    )
    title = market_metadata.get("title") or market_metadata.get("name")
    status = str(market_metadata.get("status") or "").strip().lower() or None
    return {
        "market_ticker": market_ticker,
        "event_ticker": market_metadata.get("event_ticker"),
        "title": title,
        "name": market_metadata.get("name") or title,
        "status_at_launch": status,
        "market_status": status,
        "raw_market_status": market_metadata.get("raw_status") or status,
        "event_category": market_metadata.get("event_category"),
        "event_title": market_metadata.get("event_title"),
        "event_subtitle": market_metadata.get("event_subtitle"),
        "event_type": market_metadata.get("event_type"),
        "event_metadata_fetched": _event_metadata_fetched(market_metadata),
        "category": market_metadata.get("category"),
        "market_type": market_metadata.get("market_type"),
        "open_time": _time_text(market_metadata.get("open_time")),
        "close_time": _time_text(market_metadata.get("close_time")),
        "expected_expiration": _time_text(market_metadata.get("expected_expiration")),
        "expected_expiration_time": _time_text(
            market_metadata.get("expected_expiration_time")
        ),
        "latest_expiration_time": _time_text(market_metadata.get("latest_expiration_time")),
        "occurrence_time": _time_text(market_metadata.get("occurrence_time")),
        "occurrence_datetime": _time_text(market_metadata.get("occurrence_datetime")),
        "occurrence_raw_value": policy["occurrence_raw_value"],
        "occurrence_semantic_classification": policy[
            "occurrence_semantic_classification"
        ],
        "occurrence_included_as_safety_bound": policy[
            "occurrence_included_as_safety_bound"
        ],
        "occurrence_equals_close_time": policy["occurrence_equals_close_time"],
        "occurrence_equals_expected_expiration_time": policy[
            "occurrence_equals_expected_expiration_time"
        ],
        "dual_interpretation_pass": policy["dual_interpretation_pass"],
        "lifecycle_deadline_components": {
            field: _time_text(policy[field])
            for field in (
                "close_time",
                "expected_expiration_time",
                "early_close_deadline",
                "occurrence_safety_bound",
            )
        },
        "settlement_time": _time_text(market_metadata.get("settlement_time")),
        "settlement_ts": _time_text(market_metadata.get("settlement_ts")),
        "listed_expiration": _time_text(market_metadata.get("listed_expiration")),
        "can_close_early": market_metadata.get("can_close_early"),
        "early_close_condition": market_metadata.get("early_close_condition"),
        "early_close_deadline": _time_text(
            _first_metadata_value(market_metadata, *EARLY_CLOSE_DEADLINE_FIELDS)
        ),
        "early_close_deadline_authoritative": policy[
            "early_close_deadline_authoritative"
        ],
        "selected_at_utc": selected_at_utc.isoformat(),
        "campaign_expected_end_utc": (
            selected_at_utc + timedelta(seconds=duration_seconds)
        ).isoformat(),
        "campaign_required_end_utc": campaign_required_end.isoformat(),
        "time_to_close_at_launch_seconds": (
            int((close_time - selected_at_utc).total_seconds()) if close_time else None
        ),
        "time_to_lifecycle_deadline_at_launch_seconds": (
            int((lifecycle_deadline - selected_at_utc).total_seconds())
            if lifecycle_deadline
            else None
        ),
        "lifecycle_deadline": _time_text(lifecycle_deadline),
        "selection_reason": selection_reason,
        "selection_profile": selection_profile.value,
        "selection_profile_version": SELECTION_PROFILE_VERSION,
        "selection_profile_hash": selection_profile_hash(
            selection_profile,
            duration_seconds=duration_seconds,
            safety_buffer_seconds=safety_buffer_seconds,
        ),
        "selection_gate_result": result,
        "selection_gate_rejection_reason": reason,
        "selection_safety_buffer_seconds": safety_buffer_seconds,
        "market_lifecycle_status": _status_lifecycle(status),
    }


def _first_metadata_time(market_metadata: Mapping[str, object], *keys: str) -> datetime | None:
    for key in keys:
        parsed = _parse_time(market_metadata.get(key))
        if parsed is not None:
            return parsed
    return None


def _first_metadata_value(market_metadata: Mapping[str, object], *keys: str) -> object:
    for key in keys:
        value = market_metadata.get(key)
        if value is not None and value != "":
            return value
    return None


def _event_metadata_fetched(market_metadata: Mapping[str, object]) -> bool:
    return (
        market_metadata.get("event_metadata_fetched") is True
        and bool(_event_category(market_metadata))
        and bool(market_metadata.get("event_title"))
    )


def _event_category(market_metadata: Mapping[str, object]) -> str:
    return str(
        market_metadata.get("event_category") or market_metadata.get("category") or ""
    ).strip()


def _as_bool(value: object) -> bool:
    return _as_optional_bool(value) is True


def _as_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    return None


def _is_sports_market(market_metadata: Mapping[str, object]) -> bool:
    categories = (
        market_metadata.get("event_category"),
        market_metadata.get("category"),
    )
    return any("sport" in str(category).strip().lower() for category in categories if category)


def _is_match_event(market_metadata: Mapping[str, object]) -> bool:
    text = " ".join(
        str(market_metadata.get(key) or "")
        for key in ("title", "event_title", "event_subtitle", "event_type", "market_type")
    ).lower()
    words = {
        "".join(character for character in word if character.isalnum())
        for word in text.split()
    }
    return bool(words & {"game", "match", "race", "bout", "set", "tournamentmatch"})


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _time_text(value: object) -> str | None:
    parsed = _parse_time(value)
    if parsed is not None:
        return parsed.isoformat()
    return value if isinstance(value, str) and value else None


def _is_empty_orderbook(market_metadata: Mapping[str, object]) -> bool:
    if market_metadata.get("orderbook_empty") is True:
        return True
    if market_metadata.get("has_orderbook") is False:
        return True
    level_count = market_metadata.get("orderbook_level_count")
    return isinstance(level_count, int) and level_count <= 0


def _market_lifecycle_status(summary: Mapping[str, object]) -> str:
    status = str(summary.get("market_status") or summary.get("status_at_launch") or "").lower()
    return _status_lifecycle(status or None)


def _status_lifecycle(status: str | None) -> str:
    if status in OPEN_MARKET_STATUSES:
        return "OPEN"
    if status in CLOSED_OR_FINAL_STATUSES:
        return "CLOSED_OR_FINALIZED"
    if status == "paused":
        return "PAUSED"
    if status == "unopened":
        return "UNOPENED"
    return "UNKNOWN"


def _market_closed_or_finalized(summary: Mapping[str, object]) -> bool:
    return _market_lifecycle_status(summary) == "CLOSED_OR_FINALIZED"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, result: dict[str, object]) -> None:
    failures = result.get("failures", [])
    lines = [
        "# V2 Read-Only Campaign Validation",
        "",
        f"- status: {result['status']}",
        f"- heartbeat_count: {result['heartbeat_count']}",
        f"- recorder_event_count: {result['recorder_event_count']}",
        f"- rebuild_frame_count: {result['rebuild_frame_count']}",
        f"- daily_validation_count: {result['daily_validation_count']}",
        f"- strict_verdict: {result['strict_verdict']}",
        "",
        "## Failures",
        "",
    ]
    lines.extend(f"- {failure}" for failure in failures) if failures else lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
