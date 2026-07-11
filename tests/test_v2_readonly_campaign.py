from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from edmn_trader.adapters.kalshi import (
    KalshiDemoMarketDataClient,
    KalshiReadOnlyOptInRequired,
    normalize_kalshi_market_metadata,
)
from edmn_trader.cli.monitor import build_monitor_snapshot, render_snapshot
from edmn_trader.scripts.v2_readonly_campaign import (
    CANARY_SECONDS,
    CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
    SEVEN_DAY_SECONDS,
    SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
    SelectionProfile,
    discover_kalshi_demo_ws_market,
    evaluate_market_selection,
    plan_campaign,
    plan_kalshi_ws_campaign,
    run_kalshi_rest_smoke,
    run_kalshi_ws_smoke,
    run_smoke,
    selection_profile_for_duration,
    validate_campaign,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 7, 3, 18, 0, tzinfo=UTC)


def _market_metadata(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticker": "DEMO-EVENT-MARKET",
        "event_ticker": "DEMO-EVENT",
        "title": "Demo event market",
        "status": "open",
        "open_time": "2026-07-01T00:00:00Z",
        "close_time": "2026-07-20T00:00:00Z",
        "orderbook_level_count": 2,
        "event_category": "Finance",
        "event_title": "Long-horizon finance event",
        "event_metadata_fetched": True,
        "market_type": "binary",
    }
    payload.update(overrides)
    return payload


def test_market_selection_accepts_open_market_beyond_campaign_end() -> None:
    result = evaluate_market_selection(
        _market_metadata(),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_result"] == "pass"
    assert result["selection_gate_rejection_reason"] is None
    assert result["market_ticker"] == "DEMO-EVENT-MARKET"


def test_market_selection_rejects_finalized_market() -> None:
    result = evaluate_market_selection(
        _market_metadata(status="finalized"),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_result"] == "reject"
    assert result["selection_gate_rejection_reason"] == "MARKET_STATUS_FINALIZED"


def test_market_selection_rejects_closed_and_settled_markets() -> None:
    for status, reason in (
        ("closed", "MARKET_STATUS_CLOSED"),
        ("settled", "MARKET_STATUS_SETTLED"),
    ):
        result = evaluate_market_selection(
            _market_metadata(status=status),
            selected_at_utc=NOW,
            duration_seconds=SEVEN_DAY_SECONDS,
        )

        assert result["selection_gate_rejection_reason"] == reason


def test_market_selection_rejects_short_close_window() -> None:
    result = evaluate_market_selection(
        _market_metadata(close_time="2026-07-08T00:00:00Z"),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == "TIME_TO_CLOSE_TOO_SHORT"


def test_market_selection_rejects_early_expected_expiration_even_with_long_close_time() -> None:
    result = evaluate_market_selection(
        _market_metadata(
            close_time="2026-07-20T00:00:00Z",
            expected_expiration_time="2026-07-08T00:00:00Z",
            latest_expiration_time="2026-07-30T00:00:00Z",
        ),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == "EXPECTED_EXPIRATION_TOO_SHORT"
    assert result["lifecycle_deadline"] == "2026-07-08T00:00:00+00:00"


def test_market_selection_rejects_unsafe_early_close_without_expected_expiration() -> None:
    result = evaluate_market_selection(
        _market_metadata(can_close_early=True),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == "CAN_CLOSE_EARLY_UNSAFE_FOR_DURATION"


def test_market_selection_rejects_sports_occurrence_inside_long_horizon() -> None:
    result = evaluate_market_selection(
        _market_metadata(
            close_time="2026-07-20T00:00:00Z",
            expected_expiration_time="2026-07-20T00:00:00Z",
            occurrence_datetime="2026-07-08T00:00:00Z",
            event_category="Sports",
            event_metadata_fetched=True,
        ),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == "EVENT_OCCURRENCE_TOO_EARLY"


def test_market_selection_accepts_all_conservative_deadlines_beyond_required_end() -> None:
    result = evaluate_market_selection(
        _market_metadata(
            close_time="2026-07-20T00:00:00Z",
            expected_expiration_time="2026-07-19T00:00:00Z",
            occurrence_datetime="2026-07-18T00:00:00Z",
            latest_expiration_time="2026-07-30T00:00:00Z",
            can_close_early=True,
            event_category="Finance",
            event_metadata_fetched=True,
        ),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_result"] == "pass"
    assert result["lifecycle_deadline"] == "2026-07-18T00:00:00+00:00"


def test_short_smoke_accepts_sufficiently_long_short_lived_market() -> None:
    result = evaluate_market_selection(
        _market_metadata(close_time="2026-07-03T20:00:00Z"),
        selected_at_utc=NOW,
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
    )

    assert result["selection_gate_result"] == "pass"


def test_thirty_minute_canary_uses_its_own_duration_gate() -> None:
    metadata = _market_metadata(close_time="2026-07-03T18:40:00Z")

    smoke = evaluate_market_selection(
        metadata,
        selected_at_utc=NOW,
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
    )
    canary = evaluate_market_selection(
        metadata,
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert smoke["selection_gate_result"] == "pass"
    assert canary["selection_profile"] == "canary"
    assert canary["selection_safety_buffer_seconds"] == 3_600
    assert canary["selection_gate_rejection_reason"] == "CANARY_LIFECYCLE_DEADLINE_TOO_SHORT"


def test_selection_profiles_are_explicit_and_distinct() -> None:
    assert selection_profile_for_duration(300) is SelectionProfile.SMOKE
    assert selection_profile_for_duration(CANARY_SECONDS) is SelectionProfile.CANARY
    assert selection_profile_for_duration(SEVEN_DAY_SECONDS) is SelectionProfile.SEVEN_DAY


def test_canary_requires_complete_event_metadata() -> None:
    incomplete = _market_metadata(event_metadata_fetched=True, event_title=None)
    missing_category = _market_metadata(event_category=None, category=None)
    missing_type = _market_metadata(event_type=None, market_type=None)

    assert evaluate_market_selection(
        incomplete, selected_at_utc=NOW, duration_seconds=CANARY_SECONDS
    )["selection_gate_rejection_reason"] == "EVENT_METADATA_INCOMPLETE"
    assert evaluate_market_selection(
        missing_category, selected_at_utc=NOW, duration_seconds=CANARY_SECONDS
    )["selection_gate_rejection_reason"] == "EVENT_CATEGORY_MISSING"
    assert evaluate_market_selection(
        missing_type, selected_at_utc=NOW, duration_seconds=CANARY_SECONDS
    )["selection_gate_rejection_reason"] == "EVENT_METADATA_INCOMPLETE"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"event_category": "Sports"}, "SPORTS_UNSUITABLE_FOR_CANARY"),
        ({"event_title": "Championship match"}, "MATCH_EVENT_UNSUITABLE_FOR_CANARY"),
        ({"event_title": "Horse race winner"}, "MATCH_EVENT_UNSUITABLE_FOR_CANARY"),
        ({"event_title": "Boxing bout result"}, "MATCH_EVENT_UNSUITABLE_FOR_CANARY"),
        ({"event_title": "Final tournament-match"}, "MATCH_EVENT_UNSUITABLE_FOR_CANARY"),
    ],
)
def test_canary_rejects_sports_and_match_events(
    overrides: dict[str, object], reason: str
) -> None:
    result = evaluate_market_selection(
        _market_metadata(**overrides),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == reason


def test_canary_uses_earliest_deadline_and_rejects_unsafe_early_close() -> None:
    early_expected = evaluate_market_selection(
        _market_metadata(
            close_time="2026-07-04T00:00:00Z",
            expected_expiration_time="2026-07-03T19:00:00Z",
            latest_expiration_time="2026-08-01T00:00:00Z",
        ),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )
    unsafe_early_close = evaluate_market_selection(
        _market_metadata(can_close_early=True),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert early_expected["lifecycle_deadline"] == "2026-07-03T19:00:00+00:00"
    assert early_expected["selection_gate_rejection_reason"] == "EXPECTED_EXPIRATION_TOO_SHORT"
    assert (
        unsafe_early_close["selection_gate_rejection_reason"]
        == "CAN_CLOSE_EARLY_UNSAFE_FOR_CANARY"
    )


def test_valid_canary_records_profile_and_required_horizon(tmp_path: Path) -> None:
    plan_kalshi_ws_campaign(
        output_dir=tmp_path,
        campaign_id="canary-profile",
        duration_seconds=CANARY_SECONDS,
        max_markets=1,
        now=NOW,
        market_metadata=_market_metadata(
            close_time="2026-07-04T00:00:00Z",
            expected_expiration_time="2026-07-04T00:00:00Z",
        ),
    )
    manifest = json.loads((tmp_path / "campaign_manifest.json").read_text())

    assert manifest["selection_profile"] == "canary"
    assert manifest["selection_safety_buffer_seconds"] == CANARY_SELECTION_SAFETY_BUFFER_SECONDS
    assert manifest["campaign_required_end_utc"] == "2026-07-03T19:30:00+00:00"
    assert manifest["event_metadata_fetched"] is True
    assert manifest["event_category"] == "Finance"
    assert manifest["selection_gate_rejection_reason"] is None


def test_market_selection_rejects_missing_close_time_and_empty_orderbook() -> None:
    missing_close = _market_metadata()
    del missing_close["close_time"]

    assert (
        evaluate_market_selection(
            missing_close,
            selected_at_utc=NOW,
            duration_seconds=SEVEN_DAY_SECONDS,
        )["selection_gate_rejection_reason"]
        == "MISSING_CLOSE_TIME"
    )
    assert (
        evaluate_market_selection(
            _market_metadata(orderbook_level_count=0),
            selected_at_utc=NOW,
            duration_seconds=SEVEN_DAY_SECONDS,
        )["selection_gate_rejection_reason"]
        == "EMPTY_ORDERBOOK"
    )


def test_smoke_and_seven_day_selection_profiles_remain_distinct() -> None:
    short_lived = normalize_kalshi_market_metadata(
        _market_metadata(status="active", close_time="2026-07-03T20:00:00Z")
    )

    smoke = evaluate_market_selection(
        short_lived,
        selected_at_utc=NOW,
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
    )
    seven_day = evaluate_market_selection(
        short_lived,
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )
    long_lived = evaluate_market_selection(
        normalize_kalshi_market_metadata(
            _market_metadata(status="active", close_time="2026-07-20T00:00:00Z")
        ),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert smoke["selection_gate_result"] == "pass"
    assert smoke["raw_market_status"] == "active"
    assert seven_day["selection_gate_rejection_reason"] == "TIME_TO_CLOSE_TOO_SHORT"
    assert long_lived["selection_gate_result"] == "pass"


def test_market_discovery_paginates_and_selects_active_market() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/markets"):
            if request.url.params.get("cursor") == "page-2":
                return httpx.Response(
                    200,
                    json={
                        "markets": [
                            _market_metadata(
                                ticker="PAGE-2",
                                status="active",
                                close_time="2026-07-03T20:00:00Z",
                            )
                        ],
                        "cursor": "",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "markets": [
                        _market_metadata(
                            ticker="PAGE-1",
                            status="active",
                            close_time="2026-07-03T20:00:00Z",
                        )
                    ],
                    "cursor": "page-2",
                },
            )
        if request.url.path.endswith("PAGE-1/orderbook"):
            return httpx.Response(
                200,
                json={"orderbook_fp": {"yes_dollars": [], "no_dollars": []}},
            )
        return httpx.Response(
            200,
            json={"orderbook_fp": {"yes_dollars": [["0.4000", "2.00"]], "no_dollars": []}},
        )

    result = discover_kalshi_demo_ws_market(
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] is None
    assert result["pages_fetched"] == 2
    assert result["market_metadata"]["ticker"] == "PAGE-2"
    assert result["market_metadata"]["status"] == "open"
    assert result["market_metadata"]["raw_status"] == "active"
    assert result["selection"]["selection_gate_result"] == "pass"
    market_requests = [request for request in requests if request.url.path.endswith("/markets")]
    assert [request.url.params.get("cursor") for request in market_requests] == [None, "page-2"]
    assert all(request.method == "GET" for request in requests)
    assert all(request.url.host == "external-api.demo.kalshi.co" for request in requests)


def test_market_discovery_fetches_event_metadata_for_seven_day_selection() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={
                    "markets": [
                        _market_metadata(
                            close_time="2026-07-20T00:00:00Z",
                            expected_expiration_time="2026-07-19T00:00:00Z",
                            occurrence_datetime="2026-07-18T00:00:00Z",
                        )
                    ],
                    "cursor": "",
                },
            )
        if request.url.path.endswith("/events/DEMO-EVENT"):
            return httpx.Response(
                200,
                json={
                    "event": {
                        "event_ticker": "DEMO-EVENT",
                        "category": "Finance",
                        "title": "Long-horizon event",
                    }
                },
            )
        return httpx.Response(
            200,
            json={"orderbook_fp": {"yes_dollars": [["0.4000", "2.00"]], "no_dollars": []}},
        )

    result = discover_kalshi_demo_ws_market(
        duration_seconds=SEVEN_DAY_SECONDS,
        safety_buffer_seconds=86_400,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] is None
    assert result["market_metadata"]["event_metadata_fetched"] is True
    assert result["market_metadata"]["event_category"] == "Finance"
    assert any(request.url.path.endswith("/events/DEMO-EVENT") for request in requests)


def test_market_discovery_fetches_complete_event_metadata_for_canary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={"markets": [_market_metadata()], "cursor": ""},
            )
        if request.url.path.endswith("/events/DEMO-EVENT"):
            return httpx.Response(
                200,
                json={
                    "event": {
                        "event_ticker": "DEMO-EVENT",
                        "category": "Finance",
                        "title": "Long-horizon event",
                    }
                },
            )
        return httpx.Response(
            200,
            json={"orderbook_fp": {"yes_dollars": [["0.4000", "2.00"]], "no_dollars": []}},
        )

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] is None
    assert result["selection"]["selection_profile"] == "canary"
    assert result["selection"]["event_metadata_fetched"] is True


def test_canary_discovery_never_marks_incomplete_event_fetch_successful() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [_market_metadata()], "cursor": ""})
        if request.url.path.endswith("/events/DEMO-EVENT"):
            return httpx.Response(200, json={"event": {"category": "Finance"}})
        return httpx.Response(500)

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] == "DEMO_NO_ELIGIBLE_MARKET"
    assert result["rejection_counts"] == {"EVENT_METADATA_FETCH_FAILED": 1}


def test_market_discovery_rejects_incomplete_event_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={"markets": [_market_metadata()], "cursor": ""},
            )
        if request.url.path.endswith("/events/DEMO-EVENT"):
            return httpx.Response(200, json={"event": {"event_ticker": "DEMO-EVENT"}})
        return httpx.Response(500)

    result = discover_kalshi_demo_ws_market(
        duration_seconds=SEVEN_DAY_SECONDS,
        safety_buffer_seconds=86_400,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] == "DEMO_NO_ELIGIBLE_MARKET"
    assert result["rejection_counts"] == {"EVENT_METADATA_MISSING": 1}


def test_market_discovery_rejects_finalized_and_empty_results_explicitly() -> None:
    finalized = discover_kalshi_demo_ws_market(
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(
            lambda _request: httpx.Response(
                200,
                json={"markets": [_market_metadata(status="finalized")], "cursor": ""},
            )
        ),
    )
    empty = discover_kalshi_demo_ws_market(
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(
            lambda _request: httpx.Response(200, json={"markets": [], "cursor": ""})
        ),
    )

    assert finalized["blocker_code"] == "DEMO_NO_ELIGIBLE_MARKET"
    assert finalized["rejection_counts"] == {"MARKET_STATUS_SETTLED": 1}
    assert empty["blocker_code"] == "DEMO_NO_OPEN_MARKETS"


@pytest.mark.parametrize(
    ("response", "blocker_code"),
    (
        (httpx.Response(503, json={"code": "unavailable"}), "DEMO_MARKET_DISCOVERY_HTTP_ERROR"),
        (httpx.Response(200, content=b"not-json"), "DEMO_MARKET_DISCOVERY_PARSE_ERROR"),
    ),
)
def test_market_discovery_does_not_collapse_http_or_parse_errors(
    response: httpx.Response,
    blocker_code: str,
) -> None:
    result = discover_kalshi_demo_ws_market(
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(lambda _request: response),
    )

    assert result["blocker_code"] == blocker_code
    assert result["blocker_code"] not in {"DEMO_NO_OPEN_MARKETS", "DEMO_NO_ELIGIBLE_MARKET"}


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
        market_metadata=_market_metadata(
            event_category="Finance",
            event_metadata_fetched=True,
        ),
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


def test_validator_blocks_finalized_market_as_campaign_evidence(tmp_path: Path) -> None:
    plan_campaign(
        root=tmp_path,
        campaign_id="ws1",
        venue="kalshi_demo",
        market="DEMO-EVENT-MARKET",
        duration_seconds=300,
        interval_seconds=10,
        source_type="WEBSOCKET_DELTA",
        now=NOW,
        market_metadata=_market_metadata(status="finalized"),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text(encoding="utf-8"))
    summary.update(
        {
            "status": "websocket_smoke_complete",
            "event_count": 2,
            "delta_count": 1,
            "snapshot_count": 1,
            "rebuild_frame_count": 2,
            "last_event_time": NOW.isoformat(),
        }
    )
    (tmp_path / "campaign_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _write_ok_heartbeat(tmp_path)

    result = validate_campaign(input_dir=tmp_path)

    assert result["status"] == "pass"
    assert (
        result["evidence_classification"]
        == "MARKET_CLOSED_OR_FINALIZED_ENDS_CAMPAIGN_EVIDENCE"
    )
    assert result["data_integrity_classification"] == "DATA_INTEGRITY_PASS"
    assert result["campaign_evidence_valid"] is False
    assert (
        result["evidence_validity_classification"]
        == "CAMPAIGN_EVIDENCE_INVALID_MARKET_LIFECYCLE"
    )


def test_validator_separates_lifecycle_rejection_from_data_integrity(tmp_path: Path) -> None:
    plan_kalshi_ws_campaign(
        output_dir=tmp_path,
        campaign_id="lifecycle-rejected",
        duration_seconds=SEVEN_DAY_SECONDS,
        max_markets=1,
        now=NOW,
        market_metadata=_market_metadata(
            close_time="2026-07-05T00:00:00Z",
            event_category="Finance",
            event_metadata_fetched=True,
        ),
    )
    _write_ok_heartbeat(tmp_path)

    result = validate_campaign(input_dir=tmp_path)

    assert result["status"] == "pass"
    assert result["data_integrity_classification"] == "DATA_INTEGRITY_PASS"
    assert result["campaign_evidence_valid"] is False
    assert (
        result["evidence_validity_classification"]
        == "CAMPAIGN_EVIDENCE_INVALID_MARKET_LIFECYCLE"
    )


def test_manifest_preserves_lifecycle_v2_fields(tmp_path: Path) -> None:
    plan_kalshi_ws_campaign(
        output_dir=tmp_path,
        campaign_id="manifest-v2",
        duration_seconds=SEVEN_DAY_SECONDS,
        max_markets=1,
        now=NOW,
        market_metadata=_market_metadata(
            close_time="2026-07-20T00:00:00Z",
            expected_expiration_time="2026-07-19T00:00:00Z",
            occurrence_datetime="2026-07-18T00:00:00Z",
            can_close_early=True,
            early_close_condition="after outcome",
            event_category="Finance",
            event_metadata_fetched=True,
        ),
    )

    manifest = json.loads((tmp_path / "campaign_manifest.json").read_text(encoding="utf-8"))

    assert manifest["can_close_early"] is True
    assert manifest["expected_expiration_time"] == "2026-07-19T00:00:00+00:00"
    assert manifest["occurrence_datetime"] == "2026-07-18T00:00:00+00:00"
    assert manifest["lifecycle_deadline"] == "2026-07-18T00:00:00+00:00"
    assert manifest["selection_gate_rejection_reason"] is None


def test_lifecycle_gate_keeps_execution_safety_disabled(tmp_path: Path) -> None:
    summary = plan_kalshi_ws_campaign(
        output_dir=tmp_path,
        campaign_id="safety-v2",
        duration_seconds=SEVEN_DAY_SECONDS,
        max_markets=1,
        now=NOW,
        market_metadata=_market_metadata(
            close_time="2026-07-20T00:00:00Z",
            expected_expiration_time="2026-07-19T00:00:00Z",
            event_category="Finance",
            event_metadata_fetched=True,
        ),
    )

    assert summary["live_gate_status"] == "disabled"
    assert summary["production_endpoint_used"] is False
    assert summary["submit_attempts"] == 0


def test_ws_campaign_plan_requires_market_metadata(tmp_path: Path) -> None:
    result = plan_kalshi_ws_campaign(
        output_dir=tmp_path,
        campaign_id="seven-day",
        duration_seconds=SEVEN_DAY_SECONDS,
        max_markets=1,
        now=NOW,
    )

    assert result["selection_gate_result"] == "reject"
    assert result["selection_gate_rejection_reason"] == "MISSING_MARKET_METADATA"
    assert result["live_gate_status"] == "disabled"
    assert result["submit_attempt_count"] == 0


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


def test_monitor_warns_for_running_websocket_campaign_staleness(tmp_path: Path) -> None:
    _write_ws_campaign_summary(tmp_path, status="websocket_campaign_running")

    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 30, tzinfo=UTC))

    assert snapshot["campaign"]["status"] == "WEBSOCKET_CAMPAIGN_RUNNING"
    assert "STALE_DATA: kalshi_demo staleness=1800" in snapshot["system"]["warnings"]
    assert snapshot["system"]["health"] == "WARNING"


def test_monitor_completed_websocket_canary_quiet_period_is_informational(tmp_path: Path) -> None:
    _write_ws_campaign_summary(tmp_path, status="websocket_campaign_complete")

    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 30, tzinfo=UTC))

    assert (
        snapshot["campaign"]["completion_status"]
        == "CANARY_COMPLETED_QUIET_MARKET_NO_RECENT_EVENT"
    )
    assert snapshot["system"]["warnings"] == []
    assert snapshot["system"]["health"] == "OK_PAPER"
    assert snapshot["campaign"]["live_gate_status"] == "disabled"
    assert snapshot["campaign"]["submit_attempts"] == 0


def test_monitor_completed_websocket_canary_without_events_stays_incomplete(tmp_path: Path) -> None:
    _write_ws_campaign_summary(
        tmp_path,
        status="websocket_campaign_complete",
        event_count=0,
        snapshot_count=0,
        delta_count=0,
    )

    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 30, tzinfo=UTC))

    assert snapshot["campaign"]["status"] == "NO_DATA"
    assert (
        snapshot["campaign"]["completion_status"]
        == "COMPLETED_WITH_MONITOR_STALE_METADATA_WARNING"
    )
    assert "STALE_DATA: kalshi_demo staleness=1800" in snapshot["system"]["warnings"]


def test_monitor_stopped_unexpected_websocket_campaign_staleness_remains_warning(
    tmp_path: Path,
) -> None:
    _write_ws_campaign_summary(tmp_path, status="websocket_blocked", validation_status="fail")

    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 30, tzinfo=UTC))

    assert snapshot["campaign"]["completion_status"] is None
    assert "STALE_DATA: kalshi_demo staleness=1800" in snapshot["system"]["warnings"]
    assert snapshot["system"]["health"] == "WARNING"


def test_monitor_does_not_validate_incomplete_seven_day_artifact(tmp_path: Path) -> None:
    _write_ws_campaign_summary(
        tmp_path,
        status="websocket_campaign_running",
        duration_seconds=604800,
        evidence_classification="LAYER1_WS_CAMPAIGN_INCOMPLETE",
        event_count=2,
        snapshot_count=1,
        delta_count=0,
    )

    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 5, tzinfo=UTC))

    assert snapshot["campaign"]["status"] == "CAMPAIGN_INCOMPLETE"
    assert snapshot["campaign"]["evidence_classification"] == "LAYER1_WS_CAMPAIGN_INCOMPLETE"
    assert snapshot["campaign"]["delta_count"] == 0
    assert snapshot["campaign"]["submit_attempts"] == 0


def test_monitor_prominently_shows_finalized_market(tmp_path: Path) -> None:
    plan_campaign(
        root=tmp_path,
        campaign_id="ws1",
        venue="kalshi_demo",
        market="DEMO-EVENT-MARKET",
        duration_seconds=300,
        interval_seconds=10,
        source_type="WEBSOCKET_DELTA",
        now=NOW,
        market_metadata=_market_metadata(status="settled"),
    )
    _write_ok_heartbeat(tmp_path)
    validate_campaign(input_dir=tmp_path)

    snapshot = build_monitor_snapshot(tmp_path, now=NOW)
    rendered = render_snapshot(snapshot, "table")

    assert snapshot["campaign"]["status"] == "MARKET_CLOSED_OR_FINALIZED"
    assert snapshot["campaign"]["subscribed_market_ticker"] == "DEMO-EVENT-MARKET"
    assert snapshot["campaign"]["market_status"] == "settled"
    assert "MARKET_CLOSED_OR_FINALIZED" in rendered
    assert "market=DEMO-EVENT-MARKET" in rendered


def test_completed_canary_quiet_market_is_not_stale_warning(tmp_path: Path) -> None:
    run_smoke(
        output_dir=tmp_path,
        campaign_id="canary",
        venue="kalshi_demo",
        market="DEMO-MARKET",
        duration_seconds=30,
        interval_seconds=10,
        now=NOW,
    )

    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 4, 18, 0, tzinfo=UTC))

    assert snapshot["data_status"]["stale_status"] == "COMPLETE"
    assert not any("STALE_DATA" in warning for warning in snapshot["run_info"]["warnings"])


def test_no_production_or_submit_path_is_added(tmp_path: Path) -> None:
    result = run_smoke(
        output_dir=tmp_path,
        campaign_id="safe",
        venue="kalshi_demo",
        market="DEMO-MARKET",
        duration_seconds=30,
        interval_seconds=10,
        now=NOW,
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text(encoding="utf-8"))

    assert result["submit_attempt_count"] == 0
    assert summary["production_endpoint_used"] is False
    assert summary["live_gate_status"] == "disabled"


def _write_ok_heartbeat(tmp_path: Path) -> None:
    (tmp_path / "campaign_heartbeat.jsonl").write_text(
        json.dumps(
            {
                "record_type": "campaign_heartbeat",
                "campaign_id": "ws1",
                "venue": "kalshi_demo",
                "market": "DEMO-EVENT-MARKET",
                "sequence": 1,
                "observed_at": NOW.isoformat(),
                "received_at": NOW.isoformat(),
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

def _kalshi_client(requests: list[httpx.Request] | None = None) -> KalshiDemoMarketDataClient:
    payload = json.loads((FIXTURES / "kalshi_orderbook_response.json").read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=payload)

    return KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _market_discovery_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> KalshiDemoMarketDataClient:
    return KalshiDemoMarketDataClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _write_ws_campaign_summary(
    root: Path,
    *,
    status: str,
    validation_status: str = "pass",
    event_count: int = 6,
    snapshot_count: int = 1,
    delta_count: int = 4,
    duration_seconds: int = 1800,
    evidence_classification: str = "LAYER1_WS_DELTA_SMOKE_PASS",
) -> None:
    summary = {
        "schema_version": "v2.readonly_campaign.v1",
        "campaign_id": "ws-canary",
        "status": status,
        "venue": "kalshi_demo",
        "market": "DEMO-MARKET",
        "source_type": "WEBSOCKET_DELTA",
        "duration_seconds": duration_seconds,
        "live_gate_status": "disabled",
        "production_endpoint_used": False,
        "submit_attempt_count": 0,
        "submit_attempts": 0,
        "real_money_trading": False,
        "connection_established": True,
        "subscription_acknowledged": True,
        "event_count": event_count,
        "snapshot_count": snapshot_count,
        "delta_count": delta_count,
        "trade_count": 0,
        "gap_count": 0,
        "reconnect_count": 0,
        "last_event_time": "2026-07-03T18:00:00+00:00",
        "validation_status": validation_status,
        "evidence_classification": evidence_classification,
    }
    validation = {
        "status": validation_status,
        "source_type": "WEBSOCKET_DELTA",
        "evidence_classification": evidence_classification,
        "event_count": event_count,
        "snapshot_count": snapshot_count,
        "delta_count": delta_count,
        "trade_count": 0,
        "gap_count": 0,
        "reconnect_count": 0,
        "last_event_time": "2026-07-03T18:00:00+00:00",
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "campaign_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (root / "campaign_validation.json").write_text(json.dumps(validation), encoding="utf-8")
    (root / "campaign_heartbeat.jsonl").write_text(
        json.dumps(
            {
                "record_type": "campaign_heartbeat",
                "campaign_id": "ws-canary",
                "venue": "kalshi_demo",
                "observed_at": "2026-07-03T18:00:00+00:00",
                "received_at": "2026-07-03T18:00:00+00:00",
                "source_type": "WEBSOCKET_DELTA",
                "live_gate_status": "disabled",
                "submit_attempt": False,
                "production_endpoint_used": False,
                "status": status,
            }
        )
        + "\n",
        encoding="utf-8",
    )
