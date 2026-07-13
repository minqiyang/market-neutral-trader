from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
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
    run_kalshi_ws_campaign,
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
        "expected_expiration_time": "2026-07-20T00:00:00Z",
        "can_close_early": False,
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


def test_market_selection_rejects_historical_occurrence() -> None:
    result = evaluate_market_selection(
        _market_metadata(
            close_time="2026-07-20T00:00:00Z",
            expected_expiration_time="2026-07-20T00:00:00Z",
            occurrence_datetime="2026-07-02T00:00:00Z",
            event_category="Finance",
            event_metadata_fetched=True,
        ),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_result"] == "reject"
    assert result["selection_gate_rejection_reason"] == "OCCURRENCE_ALREADY_OCCURRED_UNSAFE"
    assert result["occurrence_semantic_classification"] == (
        "HISTORICAL_OR_ALREADY_OCCURRED"
    )
    assert result["occurrence_included_as_safety_bound"] is False
    assert result["dual_interpretation_pass"] is False


def test_market_selection_rejects_occurrence_within_clock_skew_tolerance() -> None:
    result = evaluate_market_selection(
        _market_metadata(occurrence_datetime=(NOW + timedelta(seconds=60)).isoformat()),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == "OCCURRENCE_ALREADY_OCCURRED_UNSAFE"
    assert result["occurrence_semantic_classification"] == (
        "HISTORICAL_OR_ALREADY_OCCURRED"
    )


def test_market_selection_accepts_future_occurrence_under_both_interpretations() -> None:
    result = evaluate_market_selection(
        _market_metadata(
            close_time="2026-07-04T00:00:00Z",
            expected_expiration_time="2026-07-04T00:00:00Z",
            occurrence_datetime="2026-07-03T23:00:00Z",
        ),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_result"] == "pass"
    assert result["occurrence_semantic_classification"] == (
        "AMBIGUOUS_FUTURE_OCCURRENCE"
    )
    assert result["occurrence_included_as_safety_bound"] is True
    assert result["dual_interpretation_pass"] is True


def test_market_selection_rejects_future_occurrence_before_required_end() -> None:
    result = evaluate_market_selection(
        _market_metadata(occurrence_datetime="2026-07-03T19:00:00Z"),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == (
        "OCCURRENCE_SAFETY_BOUND_TOO_SHORT"
    )
    assert result["dual_interpretation_pass"] is False


def test_equal_future_occurrence_records_anomaly_without_global_stop() -> None:
    deadline = "2026-07-04T00:00:00Z"
    result = evaluate_market_selection(
        _market_metadata(
            close_time=deadline,
            expected_expiration_time=deadline,
            occurrence_datetime=deadline,
        ),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_result"] == "pass"
    assert result["occurrence_equals_close_time"] is True
    assert result["occurrence_equals_expected_expiration_time"] is True
    assert result["dual_interpretation_pass"] is True


def test_missing_occurrence_passes_only_with_independent_safe_deadlines() -> None:
    result = evaluate_market_selection(
        _market_metadata(),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_result"] == "pass"
    assert result["occurrence_semantic_classification"] == "MISSING"
    assert result["occurrence_included_as_safety_bound"] is False
    assert result["dual_interpretation_pass"] is True


def test_missing_occurrence_with_early_close_risk_is_rejected() -> None:
    result = evaluate_market_selection(
        _market_metadata(
            can_close_early=True,
            early_close_deadline="2026-07-10T00:00:00Z",
        ),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == (
        "CAN_CLOSE_EARLY_UNSAFE_FOR_CANARY"
    )
    assert result["dual_interpretation_pass"] is False


def test_missing_can_close_early_status_is_not_treated_as_false() -> None:
    metadata = _market_metadata()
    del metadata["can_close_early"]

    result = evaluate_market_selection(
        metadata,
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == (
        "CAN_CLOSE_EARLY_STATUS_UNKNOWN"
    )
    assert result["dual_interpretation_pass"] is False


def test_malformed_occurrence_is_rejected_and_preserved_as_raw_telemetry() -> None:
    result = evaluate_market_selection(
        _market_metadata(occurrence_datetime="not-a-timestamp"),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == "OCCURRENCE_DATETIME_INVALID"
    assert result["occurrence_raw_value"] == "not-a-timestamp"
    assert result["occurrence_semantic_classification"] == "INVALID"


def test_occurrence_cannot_override_unsafe_early_close() -> None:
    result = evaluate_market_selection(
        _market_metadata(
            can_close_early=True,
            occurrence_datetime="2026-07-20T00:00:00Z",
        ),
        selected_at_utc=NOW,
        duration_seconds=CANARY_SECONDS,
    )

    assert result["selection_gate_rejection_reason"] == (
        "CAN_CLOSE_EARLY_UNSAFE_FOR_CANARY"
    )
    assert result["dual_interpretation_pass"] is False


def test_market_selection_accepts_all_conservative_deadlines_beyond_required_end() -> None:
    result = evaluate_market_selection(
        _market_metadata(
            close_time="2026-07-20T00:00:00Z",
            expected_expiration_time="2026-07-19T00:00:00Z",
            occurrence_datetime="2026-07-18T00:00:00Z",
            latest_expiration_time="2026-07-30T00:00:00Z",
            can_close_early=True,
            early_close_deadline="2026-07-17T00:00:00Z",
            early_close_deadline_authoritative=True,
            event_category="Finance",
            event_metadata_fetched=True,
        ),
        selected_at_utc=NOW,
        duration_seconds=SEVEN_DAY_SECONDS,
    )

    assert result["selection_gate_result"] == "pass"
    assert result["lifecycle_deadline"] == "2026-07-17T00:00:00+00:00"
    assert result["dual_interpretation_pass"] is True


def test_short_smoke_accepts_sufficiently_long_short_lived_market() -> None:
    result = evaluate_market_selection(
        _market_metadata(close_time="2026-07-03T20:00:00Z"),
        selected_at_utc=NOW,
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
    )

    assert result["selection_gate_result"] == "pass"
    assert result["dual_interpretation_pass"] is None


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
    assert canary["selection_gate_rejection_reason"] == "TIME_TO_CLOSE_TOO_SHORT"


def test_selection_profiles_are_explicit_and_distinct() -> None:
    assert selection_profile_for_duration(300) is SelectionProfile.SMOKE
    assert selection_profile_for_duration(CANARY_SECONDS) is SelectionProfile.CANARY
    assert selection_profile_for_duration(SEVEN_DAY_SECONDS) is SelectionProfile.SEVEN_DAY


def test_canary_requires_complete_event_metadata() -> None:
    incomplete = _market_metadata(event_metadata_fetched=True, event_title=None)
    missing_category = _market_metadata(event_category=None, category=None)

    assert evaluate_market_selection(
        incomplete, selected_at_utc=NOW, duration_seconds=CANARY_SECONDS
    )["selection_gate_rejection_reason"] == "EVENT_METADATA_INCOMPLETE"
    assert evaluate_market_selection(
        missing_category, selected_at_utc=NOW, duration_seconds=CANARY_SECONDS
    )["selection_gate_rejection_reason"] == "EVENT_CATEGORY_MISSING"


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


def test_market_discovery_stops_after_requested_eligible_market_count() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={
                    "markets": [
                        _market_metadata(ticker="FIRST"),
                        _market_metadata(ticker="SECOND"),
                        _market_metadata(ticker="THIRD"),
                    ],
                    "cursor": "",
                },
            )
        return httpx.Response(
            200,
            json={
                "orderbook_fp": {
                    "yes_dollars": [["0.4000", "2.00"]],
                    "no_dollars": [],
                }
            },
        )

    result = discover_kalshi_demo_ws_market(
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
        eligible_market_limit=1,
        max_orderbook_probes=5,
    )

    orderbook_requests = [
        request for request in requests if request.url.path.endswith("/orderbook")
    ]
    assert result["blocker_code"] is None
    assert result["market_metadata"]["ticker"] == "FIRST"
    assert result["eligible_count"] == 1
    assert result["coverage_complete"] is True
    assert result["diagnostics"]["orderbook_requests"] == 1
    assert result["diagnostics"]["orderbook_candidate_count"] == 3
    assert result["diagnostics"]["orderbook_candidate_scan_complete"] is False
    assert result["diagnostics"]["eligible_count_complete"] is False
    assert result["diagnostics"]["eligible_count_is_lower_bound"] is True
    assert result["selection"]["market_discovery_orderbook_requests"] == 1
    assert result["selection"]["market_discovery_orderbook_candidate_count"] == 3
    assert (
        result["selection"]["market_discovery_orderbook_candidate_scan_complete"]
        is False
    )
    assert result["selection"]["market_discovery_eligible_count"] == 1
    assert result["selection"]["market_discovery_eligible_count_complete"] is False
    assert result["selection"]["market_discovery_eligible_count_is_lower_bound"] is True
    assert result["selection"]["market_discovery_eligible_market_limit"] == 1
    assert result["selection"]["market_discovery_max_orderbook_probes"] == 5
    assert len(orderbook_requests) == 1


def test_market_discovery_fails_closed_at_orderbook_probe_limit() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={
                    "markets": [
                        _market_metadata(ticker="FIRST"),
                        _market_metadata(ticker="SECOND"),
                        _market_metadata(ticker="THIRD"),
                    ],
                    "cursor": "",
                },
            )
        return httpx.Response(
            200,
            json={"orderbook_fp": {"yes_dollars": [], "no_dollars": []}},
        )

    result = discover_kalshi_demo_ws_market(
        duration_seconds=300,
        safety_buffer_seconds=SMOKE_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
        eligible_market_limit=1,
        max_orderbook_probes=2,
    )

    orderbook_requests = [
        request for request in requests if request.url.path.endswith("/orderbook")
    ]
    assert result["blocker_code"] == "DEMO_MARKET_DISCOVERY_ORDERBOOK_PROBE_LIMIT"
    assert result["coverage_complete"] is True
    assert result["eligible_count"] == 0
    assert result["diagnostics"]["orderbook_requests"] == 2
    assert result["diagnostics"]["orderbook_candidate_scan_complete"] is False
    assert result["diagnostics"]["orderbook_probe_limit_reached"] is True
    assert len(orderbook_requests) == 2


def test_market_discovery_does_not_call_page_cap_complete_with_cursor_remaining() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"markets": [_market_metadata()], "cursor": "more-markets"},
        )

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
        max_pages=2,
    )

    assert result["blocker_code"] == "DEMO_MARKET_DISCOVERY_INCOMPLETE_PAGE_LIMIT"
    assert result["coverage_complete"] is False
    assert result["cursor_remaining"] is True
    assert result["pages_fetched"] == 2
    assert result["diagnostics"]["final_cursor_empty"] is False
    assert result["diagnostics"]["max_pages_reached"] is True
    assert all(request.url.path.endswith("/markets") for request in requests)


def test_market_discovery_emits_complete_multilabel_profile_evidence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={
                    "markets": [
                        _market_metadata(
                            ticker="RISKY-MARKET",
                            event_ticker="RISKY-EVENT",
                            can_close_early=True,
                            expected_expiration_time="2026-07-03T19:00:00Z",
                        ),
                        _market_metadata(
                            ticker="SAFE-MARKET",
                            event_ticker="SAFE-EVENT",
                            expected_expiration_time="2026-07-20T00:00:00Z",
                        ),
                    ],
                    "cursor": "",
                },
            )
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "event_ticker": "RISKY-EVENT",
                            "category": "Sports",
                            "title": "Season outcome",
                        },
                        {
                            "event_ticker": "SAFE-EVENT",
                            "category": "Finance",
                            "title": "Long-horizon finance event",
                        },
                    ],
                    "cursor": "",
                },
            )
        return httpx.Response(
            200,
            json={
                "orderbook_fp": {
                    "yes_dollars": [["0.4000", "2.00"]],
                    "no_dollars": [],
                }
            },
        )

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] is None
    assert result["coverage_complete"] is True
    assert result["eligible_count"] == 1
    assert result["market_metadata"]["ticker"] == "SAFE-MARKET"
    assert result["diagnostics"]["distinct_market_count"] == 2
    assert result["diagnostics"]["duplicate_market_count"] == 0
    assert result["diagnostics"]["all_markets_multilabel_evaluated"] is True
    assert result["multi_label_rejection_counts"] == {
        "CAN_CLOSE_EARLY_UNSAFE_FOR_CANARY": 1,
        "CANARY_LIFECYCLE_DEADLINE_TOO_SHORT": 1,
        "EXPECTED_EXPIRATION_TOO_SHORT": 1,
        "SPORTS_UNSUITABLE_FOR_CANARY": 1,
    }
    assert result["selection_profile_version"] == "edmn.kalshi.selection_profile.v4"
    assert len(result["selection_profile_hash"]) == 64
    assert result["occurrence_semantic_counts"] == {"MISSING": 2}
    assert result["dual_interpretation_pass_count"] == 1
    assert result["near_misses"]
    assert "RISKY-MARKET" not in json.dumps(result["near_misses"])


def test_market_discovery_deduplicates_markets_before_counting_eligibility() -> None:
    market = _market_metadata(expected_expiration_time="2026-07-20T00:00:00Z")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={"markets": [market, dict(market)], "cursor": ""},
            )
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={
                    "events": [{
                        "event_ticker": "DEMO-EVENT",
                        "category": "Finance",
                        "title": "Long-horizon finance event",
                    }],
                    "cursor": "",
                },
            )
        return httpx.Response(
            200,
            json={
                "orderbook_fp": {
                    "yes_dollars": [["0.4000", "2.00"]],
                    "no_dollars": [],
                }
            },
        )

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["eligible_count"] == 1
    assert result["markets_seen"] == 1
    assert result["diagnostics"]["distinct_market_count"] == 1
    assert result["diagnostics"]["duplicate_market_count"] == 1


def test_market_discovery_deduplicates_event_hydration_for_shared_events() -> None:
    requests: list[httpx.Request] = []
    markets = [_market_metadata(ticker=f"DEMO-EVENT-{index}") for index in range(1_000)]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": markets, "cursor": ""})
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={
                    "events": [{
                        "event_ticker": "DEMO-EVENT",
                        "category": "Finance",
                        "title": "Long-horizon finance event",
                    }],
                    "cursor": "",
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
    assert result["diagnostics"]["unique_event_tickers"] == 1
    assert result["diagnostics"]["event_page_requests"] == 1
    assert result["diagnostics"]["event_pagination_complete"] is True
    assert sum(request.url.path.endswith("/events") for request in requests) == 1


def test_market_discovery_exhausts_documented_open_event_pagination() -> None:
    markets = [
        _market_metadata(ticker="DEMO-A-MARKET", event_ticker="DEMO-A"),
        _market_metadata(ticker="DEMO-B-MARKET", event_ticker="DEMO-B"),
    ]
    event_cursors: list[str | None] = []
    market_mve_filters: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            market_mve_filters.append(request.url.params.get("mve_filter"))
            return httpx.Response(200, json={"markets": markets, "cursor": ""})
        if request.url.path.endswith("/events"):
            cursor = request.url.params.get("cursor")
            event_cursors.append(cursor)
            ticker = "DEMO-B" if cursor else "DEMO-A"
            return httpx.Response(
                200,
                json={
                    "events": [{
                        "event_ticker": ticker,
                        "category": "Finance",
                        "title": "Long-horizon finance event",
                    }],
                    "cursor": "" if cursor else "event-page-2",
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
    assert event_cursors == [None, "event-page-2"]
    assert market_mve_filters == ["exclude"]
    assert result["diagnostics"]["event_page_requests"] == 2
    assert result["diagnostics"]["event_pages_completed"] == 2
    assert result["diagnostics"]["event_final_cursor_empty"] is True
    assert result["diagnostics"]["event_pagination_complete"] is True
    assert result["diagnostics"]["single_event_fallback_requests"] == 0
    assert (
        result["diagnostics"]["discovery_protocol_version"]
        == "edmn.kalshi.discovery_protocol.v1"
    )
    assert (
        result["selection"]["market_discovery_protocol_version"]
        == "edmn.kalshi.discovery_protocol.v1"
    )
    assert result["selection"]["market_discovery_event_pages_completed"] == 2
    assert result["selection"]["market_discovery_event_pagination_complete"] is True
    assert result["selection"]["market_discovery_event_fallback_requests"] == 0
    assert result["selection"]["market_discovery_market_mve_filter"] == "exclude"


def test_market_discovery_fails_closed_at_event_page_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={"markets": [_market_metadata()], "cursor": ""},
            )
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={"events": [], "cursor": "more-events"},
            )
        raise AssertionError(f"unexpected request: {request.url.path}")

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
        max_event_pages=2,
    )

    assert result["blocker_code"] == "DEMO_EVENT_DISCOVERY_INCOMPLETE_PAGE_LIMIT"
    assert result["diagnostics"]["event_pages_completed"] == 2
    assert result["diagnostics"]["event_final_cursor_empty"] is False
    assert result["diagnostics"]["event_pagination_complete"] is False


def test_market_discovery_fails_closed_at_exact_event_fallback_limit() -> None:
    markets = [
        _market_metadata(ticker="DEMO-A-MARKET", event_ticker="DEMO-A"),
        _market_metadata(ticker="DEMO-B-MARKET", event_ticker="DEMO-B"),
    ]
    exact_event_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal exact_event_requests
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": markets, "cursor": ""})
        if request.url.path.endswith("/events"):
            return httpx.Response(200, json={"events": [], "cursor": ""})
        if "/events/" in request.url.path:
            exact_event_requests += 1
            return httpx.Response(404, json={"code": "not_found"})
        raise AssertionError(f"unexpected request: {request.url.path}")

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
        max_event_fallback_requests=1,
    )

    assert result["blocker_code"] == "DEMO_EVENT_DISCOVERY_FALLBACK_LIMIT"
    assert exact_event_requests == 1
    assert result["diagnostics"]["single_event_fallback_requests"] == 1
    assert result["diagnostics"]["event_fallback_request_limit_reached"] is True
    assert result["diagnostics"]["coverage_complete"] is False


def test_market_discovery_retries_429_with_a_bounded_attempt_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("edmn_trader.scripts.v2_readonly_campaign.time.sleep", lambda _x: None)
    event_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal event_attempts
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [_market_metadata()], "cursor": ""})
        if request.url.path.endswith("/events"):
            event_attempts += 1
            if event_attempts < 3:
                return httpx.Response(429, json={"code": "rate_limited"})
            return httpx.Response(
                200,
                json={
                    "events": [{
                        "event_ticker": "DEMO-EVENT",
                        "category": "Finance",
                        "title": "Long-horizon finance event",
                    }],
                    "cursor": "",
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
    assert event_attempts == 3
    assert result["diagnostics"]["retry_count"] == 2
    assert result["diagnostics"]["http_status_counts"]["429"] == 2


def test_market_discovery_marks_exhausted_batch_rate_limit_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("edmn_trader.scripts.v2_readonly_campaign.time.sleep", lambda _x: None)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [_market_metadata()], "cursor": ""})
        return httpx.Response(429, json={"code": "rate_limited"})

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] == "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR"
    assert result["diagnostics"]["coverage_complete"] is False
    assert result["diagnostics"]["http_status_counts"]["429"] == 3


@pytest.mark.parametrize(("status", "expected_attempts"), ((503, 3), (400, 1), (401, 1), (403, 1)))
def test_market_discovery_http_retry_policy_is_bounded(
    status: int,
    expected_attempts: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("edmn_trader.scripts.v2_readonly_campaign.time.sleep", lambda _x: None)
    event_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal event_attempts
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [_market_metadata()], "cursor": ""})
        event_attempts += 1
        return httpx.Response(status, json={"code": "redacted_error"})

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] == "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR"
    assert event_attempts == expected_attempts
    assert result["diagnostics"]["http_status_counts"][str(status)] == expected_attempts


@pytest.mark.parametrize("fallback_failure", ("not_found", "schema"))
def test_missing_paginated_event_uses_candidate_local_single_fallback(
    fallback_failure: str,
) -> None:
    markets = [
        _market_metadata(ticker="GOOD-MARKET", event_ticker="GOOD-EVENT"),
        _market_metadata(ticker="MISSING-MARKET", event_ticker="MISSING-EVENT"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": markets, "cursor": ""})
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={
                    "events": [{
                        "event_ticker": "GOOD-EVENT",
                        "category": "Finance",
                        "title": "Long-horizon finance event",
                    }],
                    "cursor": "",
                },
            )
        if request.url.path.endswith("/events/MISSING-EVENT"):
            if fallback_failure == "not_found":
                return httpx.Response(404, json={"code": "not_found"})
            return httpx.Response(200, json={"unexpected": []})
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
    assert result["market_metadata"]["ticker"] == "GOOD-MARKET"
    assert result["diagnostics"]["single_event_fallback_requests"] == 1
    assert result["diagnostics"]["candidate_local_failure_count"] == 1


def test_event_batch_schema_failure_marks_coverage_incomplete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(200, json={"markets": [_market_metadata()], "cursor": ""})
        return httpx.Response(200, json={"unexpected": []})

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] == "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR"
    assert result["diagnostics"]["coverage_complete"] is False
    assert result["diagnostics"]["parse_schema_failure_count"] == 1


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
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={
                    "events": [{
                        "event_ticker": "DEMO-EVENT",
                        "category": "Finance",
                        "title": "Long-horizon event",
                    }],
                    "cursor": "",
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
    assert any(request.url.path.endswith("/events") for request in requests)


def test_market_discovery_fetches_complete_event_metadata_for_canary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={"markets": [_market_metadata()], "cursor": ""},
            )
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={
                    "events": [{
                        "event_ticker": "DEMO-EVENT",
                        "category": "Finance",
                        "title": "Long-horizon event",
                    }],
                    "cursor": "",
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
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={
                    "events": [{"event_ticker": "DEMO-EVENT", "category": "Finance"}],
                    "cursor": "",
                },
            )
        return httpx.Response(500)

    result = discover_kalshi_demo_ws_market(
        duration_seconds=CANARY_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] == "DEMO_NO_ELIGIBLE_MARKET"
    assert result["rejection_counts"] == {"EVENT_METADATA_INCOMPLETE": 1}


def test_market_discovery_rejects_incomplete_event_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/markets"):
            return httpx.Response(
                200,
                json={"markets": [_market_metadata()], "cursor": ""},
            )
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={"events": [{"event_ticker": "DEMO-EVENT"}], "cursor": ""},
            )
        return httpx.Response(500)

    result = discover_kalshi_demo_ws_market(
        duration_seconds=SEVEN_DAY_SECONDS,
        safety_buffer_seconds=86_400,
        selected_at_utc=NOW,
        client=_market_discovery_client(handler),
    )

    assert result["blocker_code"] == "DEMO_NO_ELIGIBLE_MARKET"
    assert result["rejection_counts"] == {"EVENT_METADATA_INCOMPLETE": 1}


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
        (
            httpx.Response(503, json={"code": "unavailable"}),
            "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR",
        ),
        (
            httpx.Response(200, content=b"not-json"),
            "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR",
        ),
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
    assert validation["runtime_schema_version"] == "edmn.kalshi.ws.runtime.v2"
    assert validation["schema_version"] == "edmn.kalshi.ws.runtime.v2"
    assert validation["source_type"] == "WEBSOCKET_NO_ORDERBOOK"
    assert validation["event_count"] == 0
    rerun_validation = validate_campaign(input_dir=tmp_path)
    assert rerun_validation["status"] == "blocked"
    assert rerun_validation["blocker_code"] == "NO_WS_CREDENTIALS"
    manifest = json.loads((tmp_path / "campaign_manifest.json").read_text(encoding="utf-8"))
    assert manifest["runtime_schema_version"] == "edmn.kalshi.ws.runtime.v2"
    assert manifest["schema_version"] != "v2.readonly_campaign.v1"
    snapshot = build_monitor_snapshot(tmp_path, now=datetime(2026, 7, 3, 18, 0, tzinfo=UTC))
    rendered = render_snapshot(snapshot, "table")
    assert snapshot["campaign"]["status"] == "WEBSOCKET_AUTH_BLOCKED"
    assert snapshot["campaign"]["source_type"] == "WEBSOCKET_NO_ORDERBOOK"
    assert "validation=blocked" in rendered
    canonical_validation = dict(validation)
    validation.update(
        campaign_id="tampered",
        event_count=99,
        overall_evidence_classification="PASS",
    )
    (tmp_path / "campaign_validation.json").write_text(
        json.dumps(validation) + "\n",
        encoding="utf-8",
    )
    assert validate_campaign(input_dir=tmp_path)["status"] == "fail"
    (tmp_path / "campaign_validation.json").write_text(
        json.dumps(canonical_validation) + "\n",
        encoding="utf-8",
    )
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        path = tmp_path / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["actual_elapsed_seconds"] = "999"
        payload["overall_evidence_classification"] = "PASS"
        payload["independent_evidence_classifications"] = {
            field: "PASS"
            for field in payload["independent_evidence_classifications"]
        }
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    assert validate_campaign(input_dir=tmp_path)["status"] == "fail"


@pytest.mark.parametrize(
    "runner",
    (run_kalshi_ws_smoke, run_kalshi_ws_campaign),
    ids=("smoke", "campaign"),
)
def test_kalshi_ws_runtime_bounds_market_selection_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: Callable[..., dict[str, object]],
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "edmn_trader.scripts.v2_readonly_campaign.load_kalshi_ws_auth_config_from_env",
        lambda: object(),
    )

    def fake_discovery(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "blocker_code": "DEMO_MARKET_DISCOVERY_ORDERBOOK_PROBE_LIMIT",
            "pages_fetched": 1,
            "markets_seen": 1,
            "rejection_counts": {},
            "cursor_remaining": False,
            "coverage_complete": True,
            "eligible_count": 0,
            "diagnostics": {
                "discovery_protocol_version": "edmn.kalshi.discovery_protocol.v1",
                "event_page_requests": 2,
                "event_pages_completed": 2,
                "event_pagination_complete": True,
                "single_event_fallback_requests": 1,
                "max_event_fallback_requests": 100,
                "event_fallback_request_limit_reached": False,
                "market_mve_filter": "exclude",
                "orderbook_requests": 100,
                "orderbook_candidate_count": 1000,
                "orderbook_candidate_scan_complete": False,
                "eligible_count_complete": False,
                "eligible_count_is_lower_bound": True,
                "eligible_market_limit": 1,
                "max_orderbook_probes": 100,
                "orderbook_probe_limit_reached": True,
            },
        }

    monkeypatch.setattr(
        "edmn_trader.scripts.v2_readonly_campaign.discover_kalshi_demo_ws_market",
        fake_discovery,
    )

    result = runner(
        output_dir=tmp_path,
        campaign_id="bounded-selection",
        duration_seconds=300,
        max_markets=1,
        now=NOW,
    )

    assert result["blocker_code"] == "DEMO_MARKET_DISCOVERY_ORDERBOOK_PROBE_LIMIT"
    assert captured["eligible_market_limit"] == 1
    assert captured["max_orderbook_probes"] == 100
    summary = json.loads((tmp_path / "campaign_summary.json").read_text())
    selection = summary["selected_market_selection"]
    assert selection["market_discovery_orderbook_requests"] == 100
    assert selection["market_discovery_orderbook_candidate_count"] == 1000
    assert selection["market_discovery_orderbook_candidate_scan_complete"] is False
    assert selection["market_discovery_eligible_count"] == 0
    assert selection["market_discovery_eligible_count_complete"] is False
    assert selection["market_discovery_eligible_count_is_lower_bound"] is True
    assert selection["market_discovery_eligible_market_limit"] == 1
    assert selection["market_discovery_max_orderbook_probes"] == 100
    assert (
        selection["market_discovery_protocol_version"]
        == "edmn.kalshi.discovery_protocol.v1"
    )
    assert selection["market_discovery_event_page_requests"] == 2
    assert selection["market_discovery_event_pages_completed"] == 2
    assert selection["market_discovery_event_pagination_complete"] is True
    assert selection["market_discovery_event_fallback_requests"] == 1
    assert selection["market_discovery_max_event_fallback_requests"] == 100
    assert selection["market_discovery_event_fallback_limit_reached"] is False
    assert selection["market_discovery_market_mve_filter"] == "exclude"
    assert selection["market_discovery_orderbook_probe_limit_reached"] is True


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
            early_close_deadline="2026-07-17T00:00:00Z",
            early_close_deadline_authoritative=True,
            event_category="Finance",
            event_metadata_fetched=True,
        ),
    )

    manifest = json.loads((tmp_path / "campaign_manifest.json").read_text(encoding="utf-8"))

    assert manifest["can_close_early"] is True
    assert manifest["expected_expiration_time"] == "2026-07-19T00:00:00+00:00"
    assert manifest["occurrence_datetime"] == "2026-07-18T00:00:00+00:00"
    assert manifest["lifecycle_deadline"] == "2026-07-17T00:00:00+00:00"
    assert manifest["occurrence_semantic_classification"] == (
        "AMBIGUOUS_FUTURE_OCCURRENCE"
    )
    assert manifest["occurrence_included_as_safety_bound"] is True
    assert manifest["dual_interpretation_pass"] is True
    assert manifest["early_close_deadline_authoritative"] is True
    assert manifest["lifecycle_deadline_components"] == {
        "close_time": "2026-07-20T00:00:00+00:00",
        "early_close_deadline": "2026-07-17T00:00:00+00:00",
        "expected_expiration_time": "2026-07-19T00:00:00+00:00",
        "occurrence_safety_bound": "2026-07-18T00:00:00+00:00",
    }
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
