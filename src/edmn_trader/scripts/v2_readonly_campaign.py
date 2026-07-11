"""V2 read-only campaign runner and validator."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from edmn_trader.adapters.kalshi import (
    KalshiClientError,
    KalshiDemoMarketDataClient,
    KalshiEmptyOrderBookError,
    KalshiHTTPError,
    KalshiReadOnlyRecorderConfig,
    KalshiResponseError,
    KalshiWsAuthBlocked,
    KalshiWsRecorderConfig,
    load_kalshi_ws_auth_config_from_env,
    normalize_kalshi_market_metadata,
    record_kalshi_demo_ws_orderbook,
    record_kalshi_readonly_orderbook,
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
MAX_MARKET_DISCOVERY_PAGES = 5
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
    "occurrence_datetime",
    "occurrence_time",
    "early_close_deadline",
    "early_close_time",
    "settlement_time",
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

    status = str(market_metadata.get("status") or "").strip().lower()
    reason = MARKET_STATUS_REJECTION_REASONS.get(status)
    if not status:
        reason = "MARKET_STATUS_UNKNOWN"
    elif status not in OPEN_MARKET_STATUSES and reason is None:
        reason = "MARKET_STATUS_UNKNOWN"

    campaign_required_end = selected_at_utc + timedelta(
        seconds=duration_seconds + effective_safety_buffer
    )
    expected_expiration = _first_metadata_time(market_metadata, *EXPECTED_EXPIRATION_FIELDS)
    occurrence_time = _first_metadata_time(market_metadata, *OCCURRENCE_FIELDS)
    early_close_deadline = _first_metadata_time(market_metadata, *EARLY_CLOSE_DEADLINE_FIELDS)
    lifecycle_deadline = _earliest_metadata_time(
        market_metadata, *CONSERVATIVE_LIFECYCLE_TIME_FIELDS
    )
    long_horizon = profile is SelectionProfile.SEVEN_DAY
    event_metadata_required = require_event_metadata or profile is not SelectionProfile.SMOKE

    if reason is None and event_metadata_required and not _event_category(market_metadata):
        reason = "EVENT_CATEGORY_MISSING"
    if reason is None and event_metadata_required and not _event_metadata_fetched(market_metadata):
        reason = (
            "EVENT_METADATA_INCOMPLETE"
            if profile is SelectionProfile.CANARY
            else "EVENT_METADATA_MISSING"
        )
    if reason is None and profile is SelectionProfile.CANARY and _as_bool(
        market_metadata.get("can_close_early")
    ):
        reason = "CAN_CLOSE_EARLY_UNSAFE_FOR_CANARY"
    if reason is None and _as_bool(market_metadata.get("can_close_early")):
        if expected_expiration is None and early_close_deadline is None:
            reason = "CAN_CLOSE_EARLY_UNSAFE_FOR_DURATION"
    if reason is None and expected_expiration is not None:
        if expected_expiration <= campaign_required_end:
            reason = "EXPECTED_EXPIRATION_TOO_SHORT"
    if reason is None and profile is not SelectionProfile.SMOKE and occurrence_time is not None:
        if occurrence_time <= campaign_required_end:
            reason = "EVENT_OCCURRENCE_TOO_EARLY"
    if reason is None and lifecycle_deadline is None:
        reason = "MISSING_CLOSE_TIME"
    if reason is None and lifecycle_deadline <= campaign_required_end:
        if profile is SelectionProfile.CANARY:
            reason = "CANARY_LIFECYCLE_DEADLINE_TOO_SHORT"
        elif (
            _parse_time(market_metadata.get("close_time")) == lifecycle_deadline
            and expected_expiration is None
            and occurrence_time is None
            and early_close_deadline is None
        ):
            reason = "TIME_TO_CLOSE_TOO_SHORT"
        else:
            reason = "CONSERVATIVE_LIFECYCLE_DEADLINE_TOO_SHORT"
    if reason is None and profile is SelectionProfile.CANARY and _is_sports_market(
        market_metadata
    ):
        reason = "SPORTS_UNSUITABLE_FOR_CANARY"
    if reason is None and profile is SelectionProfile.CANARY and _is_match_event(
        market_metadata
    ):
        reason = "MATCH_EVENT_UNSUITABLE_FOR_CANARY"
    if reason is None and long_horizon and not allow_sports_long_horizon:
        if _is_sports_market(market_metadata) or _is_match_event(market_metadata):
            reason = "SPORTS_MATCH_UNSUITABLE_FOR_LONG_CAMPAIGN"

    if reason is None and require_non_empty_orderbook and _is_empty_orderbook(market_metadata):
        reason = "EMPTY_ORDERBOOK"

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
) -> dict[str, object]:
    """Run the bounded authenticated read-only Kalshi WS smoke, or block safely."""

    _validate_duration(duration_seconds, allow_seven_day=False)
    if max_markets < 1:
        raise ValueError("max_markets must be at least 1")
    generated_at = now or datetime.now(UTC)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        auth = load_kalshi_ws_auth_config_from_env()
    except KalshiWsAuthBlocked as exc:
        message = "Kalshi Demo WebSocket read-only credentials are missing."
        if exc.code == "WS_CREDENTIAL_STORAGE_UNSAFE":
            message = "Kalshi Demo WebSocket credential storage is unsafe."
        elif exc.code == "WS_PRIVATE_KEY_LOAD_FAILED":
            message = "Kalshi Demo WebSocket private key could not be loaded."
        return _write_kalshi_ws_summary(
            output_dir=output_dir,
            campaign_id=campaign_id,
            duration_seconds=duration_seconds,
            max_markets=max_markets,
            generated_at=generated_at,
            status="websocket_auth_blocked",
            blocker_code=exc.code,
            blocker=f"{exc.code}: {message}",
            credential_presence={"access_id_present": False, "signing_material_present": False},
        )

    profile = selection_profile_for_duration(duration_seconds)
    discovery = discover_kalshi_demo_ws_market(
        duration_seconds=duration_seconds,
        safety_buffer_seconds=selection_safety_buffer_seconds(profile),
        selected_at_utc=generated_at,
        selection_profile=profile,
    )
    market_metadata = discovery.get("market_metadata")
    if not isinstance(market_metadata, Mapping):
        blocker_code = str(discovery["blocker_code"])
        return _write_kalshi_ws_summary(
            output_dir=output_dir,
            campaign_id=campaign_id,
            duration_seconds=duration_seconds,
            max_markets=max_markets,
            generated_at=generated_at,
            status="websocket_blocked",
            blocker_code=blocker_code,
            blocker=blocker_code,
            credential_presence=auth.credential_presence,
            discovery=discovery,
        )
    market = str(market_metadata.get("ticker") or market_metadata["market_ticker"])

    recorder = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id=campaign_id,
            market_tickers=(market,),
            raw_events_path=output_dir / "kalshi_ws_raw_events.jsonl",
            duration_seconds=duration_seconds,
        ),
        auth,
    )
    status = "websocket_smoke_complete" if recorder.blocker_code is None else "websocket_blocked"
    return _write_kalshi_ws_summary(
        output_dir=output_dir,
        campaign_id=campaign_id,
        duration_seconds=duration_seconds,
        max_markets=max_markets,
        generated_at=generated_at,
        status=status,
        blocker_code=recorder.blocker_code,
        blocker=recorder.blocker_code,
        credential_presence=auth.credential_presence,
        market_tickers=[market],
        market_selection=discovery.get("selection"),
        discovery=discovery,
        connection_established=recorder.connection_established,
        subscription_acknowledged=recorder.subscription_acknowledged,
        source_type=recorder.source_type,
        event_count=recorder.event_count,
        snapshot_count=recorder.snapshot_count,
        delta_count=recorder.delta_count,
        trade_count=recorder.trade_count,
        status_update_count=recorder.status_update_count,
        heartbeat_count=recorder.heartbeat_count,
        error_count=recorder.error_count,
        disconnect_count=recorder.disconnect_count,
        reconnect_count=recorder.reconnect_count,
        gap_count=recorder.gap_count,
        last_event_time=recorder.last_event_time,
        stale_seconds=recorder.stale_seconds,
        raw_event_path=recorder.raw_event_path,
        raw_event_sha256=recorder.raw_event_sha256,
    )


def _write_kalshi_ws_summary(
    *,
    output_dir: Path,
    campaign_id: str,
    duration_seconds: int,
    max_markets: int,
    generated_at: datetime,
    status: str,
    blocker_code: str | None,
    blocker: str | None,
    credential_presence: dict[str, bool],
    market_tickers: list[str] | None = None,
    market_selection: object = None,
    discovery: Mapping[str, object] | None = None,
    connection_established: bool = False,
    subscription_acknowledged: bool = False,
    source_type: str = "WEBSOCKET_SNAPSHOT",
    event_count: int = 0,
    snapshot_count: int = 0,
    delta_count: int = 0,
    trade_count: int = 0,
    status_update_count: int = 0,
    heartbeat_count: int = 1,
    error_count: int = 1,
    disconnect_count: int = 0,
    reconnect_count: int = 0,
    gap_count: int = 0,
    last_event_time: str | None = None,
    stale_seconds: int | None = None,
    raw_event_path: str | None = None,
    raw_event_sha256: str | None = None,
    mode: str = "read_only_websocket_smoke",
) -> dict[str, object]:
    market_tickers = market_tickers or []
    lifecycle = (
        dict(market_selection)
        if isinstance(market_selection, Mapping)
        else _default_lifecycle_record(
            market_tickers[0] if market_tickers else "UNSELECTED",
            generated_at,
            duration_seconds,
        )
    )
    heartbeat = {
        "record_type": "campaign_heartbeat",
        "campaign_id": campaign_id,
        "venue": "kalshi_demo",
        "market": market_tickers[0] if market_tickers else "UNSELECTED",
        "sequence": 1,
        "observed_at": generated_at.isoformat(),
        "received_at": generated_at.isoformat(),
        "source_type": source_type,
        "live_gate_status": "disabled",
        "submit_attempt": False,
        "production_endpoint_used": False,
        "status": status,
        "blocker_code": blocker_code,
    }
    write_jsonl_records(output_dir / "campaign_heartbeat.jsonl", [heartbeat])
    summary = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "status": status,
        "artifact_root": str(output_dir),
        "venue": "kalshi_demo",
        "market": market_tickers[0] if market_tickers else "UNSELECTED",
        "market_tickers": market_tickers,
        "market_count": len(market_tickers),
        "max_markets": max_markets,
        "source_type": source_type,
        "generated_at_utc": generated_at.isoformat(),
        "planned_end_utc": (generated_at + timedelta(seconds=duration_seconds)).isoformat(),
        "duration_seconds": duration_seconds,
        "interval_seconds": None,
        "mode": mode,
        "live_gate_status": "disabled",
        "production_endpoint_used": False,
        "submit_attempt_count": 0,
        "submit_attempts": 0,
        "real_money_trading": False,
        "connection_established": connection_established,
        "subscription_acknowledged": subscription_acknowledged,
        "event_count": event_count,
        "snapshot_count": snapshot_count,
        "delta_count": delta_count,
        "trade_count": trade_count,
        "status_update_count": status_update_count,
        "heartbeat_count": heartbeat_count,
        "error_count": error_count,
        "disconnect_count": disconnect_count,
        "reconnect_count": reconnect_count,
        "gap_count": gap_count,
        "last_event_time": last_event_time,
        "stale_seconds": stale_seconds,
        "rebuild_frame_count": 0,
        "validation_status": "blocked" if blocker_code else "pass",
        "blocker_code": blocker_code,
        "blocker": blocker,
        "credential_presence": credential_presence,
        "market_discovery_pages": (discovery or {}).get("pages_fetched"),
        "market_discovery_count": (discovery or {}).get("markets_seen"),
        "market_discovery_cursor_remaining": (discovery or {}).get("cursor_remaining"),
        "market_discovery_rejection_counts": (discovery or {}).get("rejection_counts", {}),
        "raw_event_path": raw_event_path,
        "raw_event_sha256": raw_event_sha256,
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
    validation = validate_campaign(input_dir=output_dir)
    summary = {
        **summary,
        "validation_status": validation["status"],
        "evidence_classification": validation["evidence_classification"],
    }
    _write_json(output_dir / "campaign_summary.json", summary)
    _write_campaign_manifest(output_dir, summary, validation=validation)
    _write_run_metadata(output_dir, summary, validation=validation)
    return {
        "campaign_id": campaign_id,
        "artifact_root": str(output_dir),
        "validation_status": validation["status"],
        "evidence_classification": validation["evidence_classification"],
        "blocker": blocker,
        "blocker_code": blocker_code,
        "live_gate_status": "disabled",
        "submit_attempt_count": 0,
    }


def validate_campaign(*, input_dir: Path) -> dict[str, object]:
    failures: list[str] = []
    summary = _read_json(input_dir / "campaign_summary.json", failures)
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
        )
    return run_kalshi_ws_smoke(
        output_dir=args.output_dir,
        campaign_id=campaign_id,
        duration_seconds=args.duration_seconds,
        max_markets=args.max_markets,
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
) -> dict[str, object]:
    _validate_duration(duration_seconds, allow_seven_day=True)
    generated_at = now or datetime.now(UTC)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        auth = load_kalshi_ws_auth_config_from_env()
    except KalshiWsAuthBlocked as exc:
        return _write_kalshi_ws_summary(
            output_dir=output_dir,
            campaign_id=campaign_id,
            duration_seconds=duration_seconds,
            max_markets=max_markets,
            generated_at=generated_at,
            status="websocket_auth_blocked",
            blocker_code=exc.code,
            blocker=exc.code,
            credential_presence={"access_id_present": False, "signing_material_present": False},
            mode="read_only_websocket_campaign",
        )

    profile = selection_profile_for_duration(duration_seconds)
    discovery = discover_kalshi_demo_ws_market(
        duration_seconds=duration_seconds,
        safety_buffer_seconds=selection_safety_buffer_seconds(profile),
        selected_at_utc=generated_at,
        selection_profile=profile,
    )
    market_metadata = discovery.get("market_metadata")
    if not isinstance(market_metadata, Mapping):
        blocker_code = str(discovery["blocker_code"])
        return _write_kalshi_ws_summary(
            output_dir=output_dir,
            campaign_id=campaign_id,
            duration_seconds=duration_seconds,
            max_markets=max_markets,
            generated_at=generated_at,
            status="websocket_blocked",
            blocker_code=blocker_code,
            blocker=blocker_code,
            credential_presence=auth.credential_presence,
            mode="read_only_websocket_campaign",
            discovery=discovery,
        )
    market = str(market_metadata.get("ticker") or market_metadata["market_ticker"])

    def checkpoint(progress: dict[str, object]) -> None:
        _write_kalshi_ws_summary(
            output_dir=output_dir,
            campaign_id=campaign_id,
            duration_seconds=duration_seconds,
            max_markets=max_markets,
            generated_at=generated_at,
            status="websocket_campaign_running",
            blocker_code=None,
            blocker=None,
            credential_presence=auth.credential_presence,
            market_tickers=[market],
            market_selection=discovery.get("selection"),
            discovery=discovery,
            mode="read_only_websocket_campaign",
            **progress,
        )

    _write_kalshi_ws_summary(
        output_dir=output_dir,
        campaign_id=campaign_id,
        duration_seconds=duration_seconds,
        max_markets=max_markets,
        generated_at=generated_at,
        status="websocket_campaign_running",
        blocker_code=None,
        blocker=None,
        credential_presence=auth.credential_presence,
        market_tickers=[market],
        market_selection=discovery.get("selection"),
        discovery=discovery,
        mode="read_only_websocket_campaign",
    )
    recorder = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id=campaign_id,
            market_tickers=(market,),
            raw_events_path=output_dir / "kalshi_ws_raw_events.jsonl",
            duration_seconds=duration_seconds,
            max_events=1_000_000,
            max_reconnects=1_000,
        ),
        auth,
        progress_callback=checkpoint,
    )
    status = "websocket_campaign_complete" if recorder.blocker_code is None else "websocket_blocked"
    return _write_kalshi_ws_summary(
        output_dir=output_dir,
        campaign_id=campaign_id,
        duration_seconds=duration_seconds,
        max_markets=max_markets,
        generated_at=generated_at,
        status=status,
        blocker_code=recorder.blocker_code,
        blocker=recorder.blocker_code,
        credential_presence=auth.credential_presence,
        market_tickers=[market],
        market_selection=discovery.get("selection"),
        discovery=discovery,
        connection_established=recorder.connection_established,
        subscription_acknowledged=recorder.subscription_acknowledged,
        source_type=recorder.source_type,
        event_count=recorder.event_count,
        snapshot_count=recorder.snapshot_count,
        delta_count=recorder.delta_count,
        trade_count=recorder.trade_count,
        status_update_count=recorder.status_update_count,
        heartbeat_count=recorder.heartbeat_count,
        error_count=recorder.error_count,
        disconnect_count=recorder.disconnect_count,
        reconnect_count=recorder.reconnect_count,
        gap_count=recorder.gap_count,
        last_event_time=recorder.last_event_time,
        stale_seconds=recorder.stale_seconds,
        raw_event_path=recorder.raw_event_path,
        raw_event_sha256=recorder.raw_event_sha256,
        mode="read_only_websocket_campaign",
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
        "settlement_time": summary.get("settlement_time"),
        "settlement_ts": summary.get("settlement_ts"),
        "listed_expiration": summary.get("listed_expiration"),
        "can_close_early": summary.get("can_close_early"),
        "early_close_condition": summary.get("early_close_condition"),
        "early_close_deadline": summary.get("early_close_deadline"),
        "selected_at_utc": summary.get("selected_at_utc"),
        "campaign_expected_end_utc": summary.get("campaign_expected_end_utc"),
        "campaign_required_end_utc": summary.get("campaign_required_end_utc"),
        "time_to_close_at_launch_seconds": summary.get("time_to_close_at_launch_seconds"),
        "time_to_lifecycle_deadline_at_launch_seconds": summary.get(
            "time_to_lifecycle_deadline_at_launch_seconds"
        ),
        "lifecycle_deadline": summary.get("lifecycle_deadline"),
        "selection_profile": summary.get("selection_profile"),
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
    selection_profile: SelectionProfile | str | None = None,
) -> dict[str, object]:
    """Find one lifecycle-eligible Demo market without hiding discovery failures."""

    active_client = client or KalshiDemoMarketDataClient()
    owns_client = client is None
    cursor: str | None = None
    pages_fetched = 0
    markets_seen = 0
    rejection_counts: Counter[str] = Counter()
    orderbook_http_error = False
    orderbook_parse_error = False
    profile = (
        SelectionProfile(selection_profile)
        if selection_profile is not None
        else selection_profile_for_duration(duration_seconds)
    )
    require_event_metadata = profile is not SelectionProfile.SMOKE
    try:
        for _ in range(max_pages):
            try:
                payload = active_client.list_markets(
                    limit=MARKET_DISCOVERY_PAGE_LIMIT,
                    cursor=cursor,
                    status="open",
                )
            except KalshiHTTPError:
                return _market_discovery_blocker(
                    "DEMO_MARKET_DISCOVERY_HTTP_ERROR",
                    pages_fetched=pages_fetched,
                    markets_seen=markets_seen,
                    rejection_counts=rejection_counts,
                )
            except KalshiResponseError:
                return _market_discovery_blocker(
                    "DEMO_MARKET_DISCOVERY_PARSE_ERROR",
                    pages_fetched=pages_fetched,
                    markets_seen=markets_seen,
                    rejection_counts=rejection_counts,
                )
            except KalshiClientError:
                return _market_discovery_blocker(
                    "DEMO_MARKET_DISCOVERY_HTTP_ERROR",
                    pages_fetched=pages_fetched,
                    markets_seen=markets_seen,
                    rejection_counts=rejection_counts,
                )

            pages_fetched += 1
            raw_markets = payload.get("markets", [])
            normalized_markets = [
                normalize_kalshi_market_metadata(item)
                for item in raw_markets
                if isinstance(item, Mapping)
            ]
            markets_seen += len(normalized_markets)
            normalized_markets.sort(key=lambda item: not _has_current_quote_indicator(item))
            for market_metadata in normalized_markets:
                candidate_metadata = market_metadata
                selection = evaluate_market_selection(
                    candidate_metadata,
                    selected_at_utc=selected_at_utc,
                    duration_seconds=duration_seconds,
                    safety_buffer_seconds=safety_buffer_seconds,
                    selection_reason="kalshi_demo_paginated_market_discovery",
                    require_non_empty_orderbook=False,
                    selection_profile=SelectionProfile.SMOKE,
                )
                rejection = selection.get("selection_gate_rejection_reason")
                if rejection:
                    rejection_counts[str(rejection)] += 1
                    continue
                if require_event_metadata:
                    try:
                        candidate_metadata = _with_event_metadata(
                            active_client, candidate_metadata
                        )
                    except (KalshiClientError, KalshiResponseError):
                        rejection_counts[
                            "EVENT_METADATA_FETCH_FAILED"
                            if profile is SelectionProfile.CANARY
                            else "EVENT_METADATA_MISSING"
                        ] += 1
                        continue
                    selection = evaluate_market_selection(
                        candidate_metadata,
                        selected_at_utc=selected_at_utc,
                        duration_seconds=duration_seconds,
                        safety_buffer_seconds=safety_buffer_seconds,
                        selection_reason="kalshi_demo_paginated_market_discovery",
                        require_non_empty_orderbook=False,
                        require_event_metadata=True,
                        selection_profile=profile,
                    )
                    rejection = selection.get("selection_gate_rejection_reason")
                    if rejection:
                        rejection_counts[str(rejection)] += 1
                        continue
                ticker = candidate_metadata.get("ticker") or candidate_metadata.get(
                    "market_ticker"
                )
                if not isinstance(ticker, str) or not ticker:
                    rejection_counts["MISSING_MARKET_METADATA"] += 1
                    continue
                try:
                    orderbook = active_client.get_market_orderbook(ticker)
                except KalshiEmptyOrderBookError:
                    rejection_counts["EMPTY_ORDERBOOK"] += 1
                    continue
                except KalshiHTTPError:
                    rejection_counts["ORDERBOOK_HTTP_ERROR"] += 1
                    orderbook_http_error = True
                    continue
                except KalshiResponseError:
                    rejection_counts["ORDERBOOK_PARSE_ERROR"] += 1
                    orderbook_parse_error = True
                    continue
                except KalshiClientError:
                    rejection_counts["ORDERBOOK_HTTP_ERROR"] += 1
                    orderbook_http_error = True
                    continue
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
                return {
                    "market_metadata": selected_metadata,
                    "selection": selected,
                    "blocker_code": None,
                    "pages_fetched": pages_fetched,
                    "markets_seen": markets_seen,
                    "rejection_counts": dict(sorted(rejection_counts.items())),
                    "cursor_remaining": bool(payload.get("cursor")),
                }

            next_cursor = payload.get("cursor")
            cursor = next_cursor if isinstance(next_cursor, str) and next_cursor else None
            if cursor is None:
                break
    finally:
        if owns_client:
            active_client.close()

    if markets_seen == 0:
        blocker_code = "DEMO_NO_OPEN_MARKETS"
    elif orderbook_http_error:
        blocker_code = "DEMO_MARKET_DISCOVERY_HTTP_ERROR"
    elif orderbook_parse_error:
        blocker_code = "DEMO_MARKET_DISCOVERY_PARSE_ERROR"
    else:
        blocker_code = "DEMO_NO_ELIGIBLE_MARKET"
    return _market_discovery_blocker(
        blocker_code,
        pages_fetched=pages_fetched,
        markets_seen=markets_seen,
        rejection_counts=rejection_counts,
        cursor_remaining=cursor is not None,
    )


def _with_event_metadata(
    client: KalshiDemoMarketDataClient,
    market_metadata: Mapping[str, object],
) -> dict[str, object]:
    event_ticker = market_metadata.get("event_ticker")
    if not isinstance(event_ticker, str) or not event_ticker:
        raise KalshiResponseError("selected market has no event_ticker")
    event = client.get_event(event_ticker)
    event_type = event.get("event_type") or market_metadata.get("market_type")
    if not event.get("category") or not event.get("title") or not event_type:
        raise KalshiResponseError("event metadata missing category, title, or type")
    return {
        **market_metadata,
        "event_metadata_fetched": True,
        "event_category": event.get("category"),
        "event_title": event.get("title"),
        "event_subtitle": event.get("sub_title") or event.get("subtitle"),
        "event_type": event_type,
        "series_ticker": event.get("series_ticker"),
    }


def _market_discovery_blocker(
    blocker_code: str,
    *,
    pages_fetched: int,
    markets_seen: int,
    rejection_counts: Mapping[str, int],
    cursor_remaining: bool = False,
) -> dict[str, object]:
    return {
        "market_metadata": None,
        "selection": None,
        "blocker_code": blocker_code,
        "pages_fetched": pages_fetched,
        "markets_seen": markets_seen,
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "cursor_remaining": cursor_remaining,
    }


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
        "settlement_time": None,
        "settlement_ts": None,
        "listed_expiration": None,
        "can_close_early": None,
        "early_close_condition": None,
        "early_close_deadline": None,
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
    close_time = _parse_time(market_metadata.get("close_time"))
    lifecycle_deadline = _earliest_metadata_time(
        market_metadata, *CONSERVATIVE_LIFECYCLE_TIME_FIELDS
    )
    campaign_required_end = selected_at_utc + timedelta(
        seconds=duration_seconds + safety_buffer_seconds
    )
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
        "settlement_time": _time_text(market_metadata.get("settlement_time")),
        "settlement_ts": _time_text(market_metadata.get("settlement_ts")),
        "listed_expiration": _time_text(market_metadata.get("listed_expiration")),
        "can_close_early": market_metadata.get("can_close_early"),
        "early_close_condition": market_metadata.get("early_close_condition"),
        "early_close_deadline": _time_text(
            _first_metadata_value(market_metadata, *EARLY_CLOSE_DEADLINE_FIELDS)
        ),
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


def _earliest_metadata_time(
    market_metadata: Mapping[str, object], *keys: str
) -> datetime | None:
    parsed = [
        value
        for key in keys
        if (value := _parse_time(market_metadata.get(key))) is not None
    ]
    return min(parsed) if parsed else None


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
        and bool(_event_type(market_metadata))
    )


def _event_category(market_metadata: Mapping[str, object]) -> str:
    return str(
        market_metadata.get("event_category") or market_metadata.get("category") or ""
    ).strip()


def _event_type(market_metadata: Mapping[str, object]) -> str:
    return str(
        market_metadata.get("event_type") or market_metadata.get("market_type") or ""
    ).strip()


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() in {"1", "true", "yes"}


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
