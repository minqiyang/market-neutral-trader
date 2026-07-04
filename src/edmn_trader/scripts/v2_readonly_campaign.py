"""V2 read-only campaign runner and validator."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from edmn_trader.adapters.kalshi import (
    KalshiDemoMarketDataClient,
    KalshiReadOnlyRecorderConfig,
    KalshiWsAuthBlocked,
    KalshiWsRecorderConfig,
    load_kalshi_ws_auth_config_from_env,
    record_kalshi_demo_ws_orderbook,
    record_kalshi_readonly_orderbook,
)
from edmn_trader.data.jsonl import read_jsonl_records, write_jsonl_records
from edmn_trader.scripts.daily_validation_report import run as run_daily_validation_report
from edmn_trader.scripts.rebuild_orderbooks import run as run_rebuild_orderbooks

MAX_SMOKE_SECONDS = 1_800
EXTENDED_WS_SMOKE_SECONDS = 900
SEVEN_DAY_SECONDS = 604_800
SCHEMA_VERSION = "v2.readonly_campaign.v1"
SOURCE_TYPES = {"SYNTHETIC", "REST", "WEBSOCKET_SNAPSHOT", "WEBSOCKET_DELTA"}
WEBSOCKET_SOURCE_TYPES = {"WEBSOCKET_SNAPSHOT", "WEBSOCKET_DELTA"}
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

    market = _select_kalshi_demo_ws_market(max_markets=max_markets)
    if market is None:
        return _write_kalshi_ws_summary(
            output_dir=output_dir,
            campaign_id=campaign_id,
            duration_seconds=duration_seconds,
            max_markets=max_markets,
            generated_at=generated_at,
            status="websocket_blocked",
            blocker_code="NO_ACTIVE_DEMO_MARKET",
            blocker="NO_ACTIVE_DEMO_MARKET: no active Demo market with a non-empty orderbook.",
            credential_presence=auth.credential_presence,
        )

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
        "raw_event_path": raw_event_path,
        "raw_event_sha256": raw_event_sha256,
        "evidence_classification": "LAYER1_WS_CAMPAIGN_INCOMPLETE",
        "manifest_path": str(output_dir / "campaign_manifest.json"),
        "validation_report_path": str(output_dir / "campaign_validation.json"),
        "raw_data_path_redacted": f"[LOCAL_PRIVATE_DATA_ROOT]/{output_dir.name}",
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
) -> dict[str, object]:
    _validate_duration(duration_seconds, allow_seven_day=True)
    if max_markets < 1:
        raise ValueError("max_markets must be at least 1")
    generated_at = now or datetime.now(UTC)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "status": "planned_owner_supervised",
        "artifact_root": str(output_dir),
        "venue": "kalshi_demo",
        "market": "OWNER_SELECTED",
        "market_count": 0,
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

    market = _select_kalshi_demo_ws_market(max_markets=max_markets)
    if market is None:
        return _write_kalshi_ws_summary(
            output_dir=output_dir,
            campaign_id=campaign_id,
            duration_seconds=duration_seconds,
            max_markets=max_markets,
            generated_at=generated_at,
            status="websocket_blocked",
            blocker_code="NO_ACTIVE_DEMO_MARKET",
            blocker="NO_ACTIVE_DEMO_MARKET",
            credential_presence=auth.credential_presence,
            mode="read_only_websocket_campaign",
        )

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
        mode="read_only_websocket_campaign",
    )
    recorder = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id=campaign_id,
            market_tickers=(market,),
            raw_events_path=output_dir / "kalshi_ws_raw_events.jsonl",
            duration_seconds=duration_seconds,
            max_events=1_000_000,
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


def _select_kalshi_demo_ws_market(*, max_markets: int) -> str | None:
    try:
        with KalshiDemoMarketDataClient() as client:
            payload = client.list_markets(limit=max(1, max_markets * 20), status="open")
            markets = payload.get("markets")
            if not isinstance(markets, list):
                return None
            for item in markets:
                if not isinstance(item, dict):
                    continue
                ticker = item.get("ticker") or item.get("market_ticker")
                if not isinstance(ticker, str) or not ticker:
                    continue
                try:
                    client.get_market_orderbook(ticker)
                except Exception:
                    continue
                return ticker
    except Exception:
        return None
    return None


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
