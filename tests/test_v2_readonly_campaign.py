from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from edmn_trader.adapters.kalshi import KalshiDemoMarketDataClient, KalshiReadOnlyOptInRequired
from edmn_trader.cli.monitor import build_monitor_snapshot, render_snapshot
from edmn_trader.scripts.v2_readonly_campaign import (
    plan_campaign,
    plan_kalshi_ws_campaign,
    run_kalshi_rest_smoke,
    run_kalshi_ws_smoke,
    run_smoke,
    validate_campaign,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_campaign_smoke_writes_bounded_readonly_artifacts(tmp_path: Path) -> None:
    result = run_smoke(
        output_dir=tmp_path,
        campaign_id="c1",
        venue="kalshi_demo",
        market="DEMO-MARKET",
        duration_seconds=30,
        interval_seconds=10,
        now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
    )

    assert result["validation_status"] == "pass"
    assert result["heartbeat_count"] == 3
    summary = json.loads((tmp_path / "campaign_summary.json").read_text(encoding="utf-8"))
    assert summary["live_gate_status"] == "disabled"
    assert summary["submit_attempt_count"] == 0
    assert (tmp_path / "campaign_validation.json").exists()


def test_kalshi_rest_smoke_runs_recorder_rebuild_and_validation(tmp_path: Path) -> None:
    client = _kalshi_client()

    result = run_kalshi_rest_smoke(
        output_dir=tmp_path,
        campaign_id="c1",
        market="DEMO-EVENT-MARKET",
        duration_seconds=30,
        interval_seconds=10,
        live_readonly_opt_in=True,
        client=client,
        now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
    )

    assert result["validation_status"] == "pass"
    assert result["recorder_event_count"] == 1
    assert result["rebuild_frame_count"] == 1
    assert result["daily_validation_count"] == 1
    validation = json.loads((tmp_path / "campaign_validation.json").read_text(encoding="utf-8"))
    assert validation["evidence_classification"] == "LAYER1_REST_SMOKE_PASS"
    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC))
    rendered = render_snapshot(snapshot, "table")
    assert snapshot["evidence"]["layers"]["Layer 1 recorder"] == "pass"
    assert snapshot["evidence"]["layers"]["Layer 2 replay/simulator"] == "pass"
    assert snapshot["campaign"]["status"] == "REST_SMOKE"
    assert "events=1" in rendered
    assert "rebuild_frames=1" in rendered


def test_kalshi_rest_smoke_requires_opt_in_before_http(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    client = _kalshi_client(requests=requests)

    with pytest.raises(KalshiReadOnlyOptInRequired, match="--live-readonly-opt-in"):
        run_kalshi_rest_smoke(
            output_dir=tmp_path,
            campaign_id="c1",
            market="DEMO-EVENT-MARKET",
            duration_seconds=30,
            interval_seconds=10,
            live_readonly_opt_in=False,
            client=client,
        )

    assert requests == []


def test_campaign_validator_fails_secret_like_fields(tmp_path: Path) -> None:
    plan_campaign(
        root=tmp_path,
        campaign_id="c1",
        venue="kalshi_demo",
        market="DEMO-MARKET",
        duration_seconds=30,
        interval_seconds=10,
        now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
    )
    (tmp_path / "campaign_heartbeat.jsonl").write_text(
        '{"record_type":"campaign_heartbeat","api_token":"nope"}\n',
        encoding="utf-8",
    )

    result = validate_campaign(input_dir=tmp_path)

    assert result["status"] == "fail"
    assert "secret-like field found in campaign artifacts" in result["failures"]


def test_campaign_duration_is_bounded(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="between 1 and 1800"):
        plan_campaign(
            root=tmp_path,
            campaign_id="c1",
            venue="kalshi_demo",
            market="DEMO-MARKET",
            duration_seconds=1801,
            interval_seconds=10,
        )


def test_kalshi_ws_smoke_truthfully_blocks_without_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KALSHI_DEMO_API_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_DEMO_PRIVATE_KEY_PATH", raising=False)

    result = run_kalshi_ws_smoke(
        output_dir=tmp_path,
        campaign_id="round6_kalshi_ws_smoke",
        duration_seconds=300,
        max_markets=1,
        now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
    )

    assert result["validation_status"] == "blocked"
    assert result["evidence_classification"] == "NO_WS_CREDENTIALS"
    assert result["submit_attempt_count"] == 0
    assert (tmp_path / "campaign_manifest.json").exists()
    assert (tmp_path / "run_metadata.json").exists()
    validation = json.loads((tmp_path / "campaign_validation.json").read_text(encoding="utf-8"))
    assert validation["source_type"] == "WEBSOCKET_SNAPSHOT"
    assert validation["event_count"] == 0
    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC))
    rendered = render_snapshot(snapshot, "table")
    assert snapshot["campaign"]["status"] == "WEBSOCKET_AUTH_BLOCKED"
    assert snapshot["campaign"]["source_type"] == "WEBSOCKET_SNAPSHOT"
    assert "validation=blocked" in rendered


def test_validator_classifies_websocket_smoke_only_when_ws_events_exist(
    tmp_path: Path,
) -> None:
    plan_campaign(
        root=tmp_path,
        campaign_id="ws1",
        venue="kalshi_demo",
        market="DEMO-MARKET",
        duration_seconds=300,
        interval_seconds=10,
        source_type="WEBSOCKET_DELTA",
        now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text(encoding="utf-8"))
    summary.update(
        {
            "status": "websocket_smoke_complete",
            "event_count": 2,
            "delta_count": 1,
            "snapshot_count": 1,
            "rebuild_frame_count": 2,
            "connection_established": True,
            "subscription_acknowledged": True,
            "last_event_time": "2026-07-03T18:00:00+00:00",
        }
    )
    (tmp_path / "campaign_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "campaign_heartbeat.jsonl").write_text(
        json.dumps(
            {
                "record_type": "campaign_heartbeat",
                "campaign_id": "ws1",
                "venue": "kalshi_demo",
                "market": "DEMO-MARKET",
                "sequence": 1,
                "observed_at": "2026-07-03T18:00:00+00:00",
                "received_at": "2026-07-03T18:00:00+00:00",
                "source_type": "WEBSOCKET_DELTA",
                "live_gate_status": "disabled",
                "submit_attempt": False,
                "production_endpoint_used": False,
                "status": "ok",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_campaign(input_dir=tmp_path)

    assert result["status"] == "pass"
    assert result["evidence_classification"] == "LAYER1_WS_DELTA_SMOKE_PASS"


def test_validator_classifies_extended_snapshot_without_delta(tmp_path: Path) -> None:
    plan_campaign(
        root=tmp_path,
        campaign_id="ws1",
        venue="kalshi_demo",
        market="DEMO-MARKET",
        duration_seconds=1800,
        interval_seconds=10,
        source_type="WEBSOCKET_SNAPSHOT",
        now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text(encoding="utf-8"))
    summary.update(
        {
            "status": "websocket_smoke_complete",
            "event_count": 1,
            "snapshot_count": 1,
            "connection_established": True,
            "subscription_acknowledged": True,
        }
    )
    (tmp_path / "campaign_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "campaign_heartbeat.jsonl").write_text(
        json.dumps(
            {
                "record_type": "campaign_heartbeat",
                "campaign_id": "ws1",
                "venue": "kalshi_demo",
                "market": "DEMO-MARKET",
                "sequence": 1,
                "observed_at": "2026-07-03T18:00:00+00:00",
                "received_at": "2026-07-03T18:00:00+00:00",
                "source_type": "WEBSOCKET_SNAPSHOT",
                "live_gate_status": "disabled",
                "submit_attempt": False,
                "production_endpoint_used": False,
                "status": "ok",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_campaign(input_dir=tmp_path)

    assert result["status"] == "pass"
    assert result["evidence_classification"] == "LAYER1_WS_SNAPSHOT_ONLY_EXTENDED"


def test_validator_does_not_mark_running_seven_day_campaign_complete(tmp_path: Path) -> None:
    plan_kalshi_ws_campaign(
        output_dir=tmp_path,
        campaign_id="ws7d",
        duration_seconds=604800,
        max_markets=3,
        now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text(encoding="utf-8"))
    summary.update(
        {
            "status": "websocket_campaign_running",
            "mode": "read_only_websocket_campaign",
            "event_count": 2,
            "snapshot_count": 1,
            "delta_count": 1,
            "connection_established": True,
            "subscription_acknowledged": True,
        }
    )
    (tmp_path / "campaign_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "campaign_heartbeat.jsonl").write_text(
        json.dumps(
            {
                "record_type": "campaign_heartbeat",
                "campaign_id": "ws7d",
                "venue": "kalshi_demo",
                "market": "DEMO-MARKET",
                "sequence": 1,
                "observed_at": "2026-07-03T18:00:00+00:00",
                "received_at": "2026-07-03T18:00:00+00:00",
                "source_type": "WEBSOCKET_DELTA",
                "live_gate_status": "disabled",
                "submit_attempt": False,
                "production_endpoint_used": False,
                "status": "websocket_campaign_running",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_campaign(input_dir=tmp_path)

    assert result["status"] == "pass"
    assert result["evidence_classification"] == "LAYER1_WS_DELTA_SMOKE_PASS"


def test_monitor_shows_campaign_view(tmp_path: Path) -> None:
    run_smoke(
        output_dir=tmp_path,
        campaign_id="c1",
        venue="kalshi_demo",
        market="DEMO-MARKET",
        duration_seconds=30,
        interval_seconds=10,
        now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC),
    )

    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC))
    rendered = render_snapshot(snapshot, "table")

    assert snapshot["campaign"]["campaign_id"] == "c1"
    assert "CAMPAIGN: id=c1" in rendered
    assert "submit_attempts=0" in rendered


def _kalshi_client(requests: list[httpx.Request] | None = None) -> KalshiDemoMarketDataClient:
    payload = json.loads((FIXTURES / "kalshi_orderbook_response.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=payload)

    return KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
