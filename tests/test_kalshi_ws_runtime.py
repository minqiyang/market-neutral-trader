from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from edmn_trader.adapters.kalshi import ws_recorder, ws_runtime
from edmn_trader.adapters.kalshi.public_evidence import (
    ConnectionEvidenceEvent,
    ConnectionEvidenceType,
)
from edmn_trader.adapters.kalshi.ws_auth import KalshiWsAuthConfig
from edmn_trader.adapters.kalshi.ws_book_rebuild import KalshiWsBookRebuilder
from edmn_trader.adapters.kalshi.ws_events import (
    KalshiWsIntegrityTracker,
    SequenceContinuityPolicy,
)
from edmn_trader.adapters.kalshi.ws_runtime import (
    D2_RUNTIME_SCHEMA_VERSION,
    RuntimeCodeProvenance,
    RuntimeEvidenceSession,
    collect_runtime_code_provenance,
    recover_d2_runtime_artifacts,
    run_d2_kalshi_ws_runtime,
    validate_d2_runtime_artifacts,
)
from edmn_trader.cli.monitor import build_monitor_snapshot
from edmn_trader.data.evidence_policy import V2_THRESHOLD_POLICY
from edmn_trader.scripts import v2_readonly_campaign

MARKET = "D2E-MARKET"
START = datetime(2026, 7, 11, 0, 0, tzinfo=UTC)
COMMIT = "012ea1e6feee4e54b2ac92014822f452361d30f8"


def test_reviewed_threshold_policy_is_single_versioned_runtime_contract() -> None:
    assert V2_THRESHOLD_POLICY.to_record() == {
        "threshold_policy_version": "edmn.v2.thresholds.v1",
        "threshold_effective_utc": "2026-07-10T02:24:00+00:00",
        "minimum_connection_coverage": "0.95",
        "maximum_disconnect_seconds": 15,
        "maximum_lifecycle_age_seconds": 120,
        "orderbook_quiet_warning_seconds": 300,
        "maximum_transport_keepalive_age_seconds": 120,
    }


def test_runtime_provenance_names_detached_head_instead_of_failing(monkeypatch) -> None:
    outputs = {
        ("rev-parse", "HEAD"): COMMIT,
        ("branch", "--show-current"): "",
        ("remote", "get-url", "origin"): "https://example.test/repo",
        ("status", "--porcelain"): "",
    }

    def fake_run(command, **_kwargs):
        return type("Result", (), {"stdout": outputs[tuple(command[1:])]})()

    monkeypatch.setattr(ws_runtime.subprocess, "run", fake_run)

    provenance = collect_runtime_code_provenance(Path.cwd())

    assert provenance.branch == "DETACHED_HEAD"


def test_actual_runtime_assembly_uses_d2_writer_and_mocked_transports(
    tmp_path: Path,
) -> None:
    fake_time = _FakeTime()
    websocket = _FakeWebSocket(
        [
            {
                "type": "subscribed",
                "id": 1,
                "sid": 41,
                "msg": {
                    "channels": ["orderbook_delta", "trade"],
                    "use_yes_price": False,
                },
            },
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [["0.56", "5"]],
                },
            },
            {
                "type": "orderbook_delta",
                "sid": 41,
                "seq": 2,
                "msg": {
                    "market_ticker": MARKET,
                    "side": "yes",
                    "price_dollars": "0.42",
                    "delta_fp": "1",
                },
            },
            {
                "type": "orderbook_delta",
                "sid": 41,
                "seq": 3,
                "msg": {
                    "market_ticker": MARKET,
                    "side": "no",
                    "price_dollars": "0.56",
                    "delta_fp": "-1",
                },
            },
            {
                "type": "trade",
                "sid": 41,
                "seq": 4,
                "msg": {"market_ticker": MARKET, "trade_id": "trade-1"},
            },
        ]
    )
    key_path = _private_key(tmp_path)

    summary = run_d2_kalshi_ws_runtime(
        output_dir=tmp_path / "run",
        campaign_id="d2e-runtime-network-mock",
        mode="read_only_websocket_smoke",
        duration_seconds=300,
        market_metadata={"ticker": MARKET, "status": "active"},
        market_selection={"selection_profile": "smoke", "selection_gate_result": "pass"},
        auth=KalshiWsAuthConfig(api_key_id="fixture-id", private_key_path=key_path),
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        websocket_factory=lambda *_args, **_kwargs: websocket,
        lifecycle_provider=lambda ticker: {"ticker": ticker, "status": "active"},
        now=fake_time.now,
        monotonic=fake_time.monotonic,
        monotonic_ns=fake_time.monotonic_ns,
    )

    assert summary["runtime_schema_version"] == D2_RUNTIME_SCHEMA_VERSION
    assert Decimal(summary["actual_elapsed_seconds"]) >= 300
    assert summary["event_count"] == 5
    assert summary["snapshot_count"] == 1
    assert summary["delta_count"] == 2
    assert summary["public_trade_count"] == 1
    assert summary["connection_event_count"] >= 2
    assert summary["lifecycle_observation_count"] >= 3
    assert summary["max_lifecycle_observation_age_seconds"] <= 120
    assert summary["freshness_dimensions"]["transport_keepalive_status"] == (
        "UNKNOWN_NOT_OBSERVED"
    )
    assert not (tmp_path / "run" / "kalshi_ws_raw_events.jsonl").exists()
    monitor = build_monitor_snapshot(
        tmp_path / "run",
        now=datetime.fromisoformat(summary["ended_at"]),
    )
    assert monitor["run_info"]["health"] == "WARNING"
    assert monitor["run_info"]["health"] != "OK_PAPER"


def test_actual_runtime_requires_acknowledgement_after_resubscription(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_time = _FakeTime()
    websockets = [
        _FailingFakeWebSocket(
            [
                {
                    "type": "subscribed",
                    "id": 1,
                    "sid": 41,
                    "msg": {"channels": ["orderbook_delta", "trade"]},
                },
                {
                    "type": "orderbook_snapshot",
                    "sid": 41,
                    "seq": 1,
                    "msg": {
                        "market_ticker": MARKET,
                        "yes_dollars_fp": [["0.42", "3"]],
                        "no_dollars_fp": [],
                    },
                },
            ]
        ),
        _FakeWebSocket(
            [
                {
                    "type": "orderbook_delta",
                    "sid": 42,
                    "seq": 2,
                    "msg": {
                        "market_ticker": MARKET,
                        "side": "yes",
                        "price_dollars": "0.42",
                        "delta_fp": "1",
                    },
                }
            ]
        ),
    ]
    monkeypatch.setattr(ws_recorder.time, "sleep", lambda _seconds: None)

    summary = run_d2_kalshi_ws_runtime(
        output_dir=tmp_path / "run",
        campaign_id="d2e-runtime-reconnect",
        mode="read_only_websocket_smoke",
        duration_seconds=20,
        market_metadata={"ticker": MARKET, "status": "active"},
        market_selection={"selection_profile": "smoke", "selection_gate_result": "pass"},
        auth=KalshiWsAuthConfig(
            api_key_id="fixture-id",
            private_key_path=_private_key(tmp_path),
        ),
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        websocket_factory=lambda *_args, **_kwargs: websockets.pop(0),
        lifecycle_provider=lambda ticker: {"ticker": ticker, "status": "active"},
        now=fake_time.now,
        monotonic=fake_time.monotonic,
        monotonic_ns=fake_time.monotonic_ns,
        max_reconnects=1,
    )

    assert summary["reconnect_count"] == 1
    assert len(summary["connection_windows"]) == 2
    assert any(
        "subscription_rebound_after_reconnect" in window["reasons"]
        for window in summary["connection_windows"]
    )
    assert summary["subscription_acknowledged"] is False
    assert summary["independent_evidence_classifications"]["subscription_status"] == "FAIL"
    assert len(summary["sequence_summaries"]) == 2


@pytest.mark.parametrize(
    ("runner", "duration_seconds", "expected_profile"),
    [
        (v2_readonly_campaign.run_kalshi_ws_smoke, 300, "smoke"),
        (v2_readonly_campaign.run_kalshi_ws_campaign, 1_800, "canary"),
    ],
)
def test_public_ws_entrypoints_emit_d2_artifacts_with_selection_provenance(
    tmp_path: Path,
    monkeypatch,
    runner,
    duration_seconds: int,
    expected_profile: str,
) -> None:
    fake_time = _FakeTime()
    websocket = _FakeWebSocket(
        [
            {
                "type": "subscribed",
                "id": 1,
                "sid": 41,
                "msg": {"channels": ["orderbook_delta", "trade"]},
            },
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
        ]
    )
    auth = KalshiWsAuthConfig(
        api_key_id="fixture-id",
        private_key_path=_private_key(tmp_path),
    )
    monkeypatch.setattr(v2_readonly_campaign, "load_kalshi_ws_auth_config_from_env", lambda: auth)
    monkeypatch.setattr(
        v2_readonly_campaign,
        "discover_kalshi_demo_ws_market",
        lambda **kwargs: {
            "market_metadata": {"ticker": MARKET, "status": "active"},
            "selection": {
                "selection_profile": kwargs["selection_profile"].value,
                "selection_safety_buffer_seconds": kwargs["safety_buffer_seconds"],
                "selection_gate_result": "pass",
            },
            "blocker_code": None,
        },
    )
    real_runtime = run_d2_kalshi_ws_runtime

    def mocked_runtime(**kwargs: Any) -> dict[str, object]:
        return real_runtime(
            **kwargs,
            websocket_factory=lambda *_args, **_kwargs: websocket,
            lifecycle_provider=lambda ticker: {"ticker": ticker, "status": "active"},
            now=fake_time.now,
            monotonic=fake_time.monotonic,
            monotonic_ns=fake_time.monotonic_ns,
        )

    monkeypatch.setattr(v2_readonly_campaign, "run_d2_kalshi_ws_runtime", mocked_runtime)
    summary = runner(
        output_dir=tmp_path / "run",
        campaign_id="d2e-public-entrypoint",
        duration_seconds=duration_seconds,
        max_markets=1,
    )

    assert summary["runtime_schema_version"] == D2_RUNTIME_SCHEMA_VERSION
    assert summary["schema_version"] != "v2.readonly_campaign.v1"
    assert summary["selected_market_selection"]["selection_profile"] == expected_profile


def test_blocked_canary_discovery_preserves_selection_policy_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    auth = KalshiWsAuthConfig(
        api_key_id="fixture-id",
        private_key_path=_private_key(tmp_path),
    )
    monkeypatch.setattr(
        v2_readonly_campaign,
        "load_kalshi_ws_auth_config_from_env",
        lambda: auth,
    )
    monkeypatch.setattr(
        v2_readonly_campaign,
        "discover_kalshi_demo_ws_market",
        lambda **_kwargs: {
            "market_metadata": None,
            "selection": None,
            "blocker_code": "DEMO_MARKET_DISCOVERY_INCOMPLETE",
            "pages_fetched": 3,
            "markets_seen": 250,
            "rejection_counts": {"EVENT_METADATA_MISSING": 7},
            "cursor_remaining": True,
            "coverage_complete": False,
        },
    )

    result = v2_readonly_campaign.run_kalshi_ws_campaign(
        output_dir=tmp_path / "run",
        campaign_id="d2e-blocked-canary",
        duration_seconds=1_800,
        max_markets=1,
    )
    summary = json.loads(
        (tmp_path / "run" / "campaign_summary.json").read_text(encoding="utf-8")
    )

    assert result["blocker_code"] == "DEMO_MARKET_DISCOVERY_INCOMPLETE"
    assert summary["selected_market_selection"] == {
        "selection_profile": "canary",
        "selection_safety_buffer_seconds": 3_600,
        "selection_gate_result": "reject",
        "selection_gate_rejection_reason": "DEMO_MARKET_DISCOVERY_INCOMPLETE",
        "market_discovery_pages": 3,
        "market_discovery_count": 250,
        "market_discovery_rejection_counts": {"EVENT_METADATA_MISSING": 7},
        "market_discovery_cursor_remaining": True,
        "market_discovery_coverage_complete": False,
    }


def test_runtime_session_wires_d2_pipeline_and_closes_verified_artifacts(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    tracker = _tracker()
    events = [
        tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "sid": 41,
                "msg": {"channel": "orderbook_delta", "use_yes_price": False},
            },
            local_row_index=1,
            received_at_utc=START + timedelta(seconds=1),
            received_monotonic_ns=1,
        ),
        tracker.record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 100,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [["0.56", "5"]],
                },
            },
            local_row_index=2,
            received_at_utc=START + timedelta(seconds=2),
            received_monotonic_ns=2,
        ),
        tracker.record(
            {
                "type": "orderbook_delta",
                "sid": 41,
                "seq": 101,
                "msg": {
                    "market_ticker": MARKET,
                    "side": "yes",
                    "price_dollars": "0.42",
                    "delta_fp": "1",
                },
            },
            local_row_index=3,
            received_at_utc=START + timedelta(seconds=3),
            received_monotonic_ns=3,
        ),
        tracker.record(
            {
                "type": "trade",
                "sid": 41,
                "seq": 102,
                "msg": {
                    "market_ticker": MARKET,
                    "trade_id": "trade-1",
                    "yes_price_dollars": "0.43",
                    "count_fp": "2",
                },
            },
            local_row_index=4,
            received_at_utc=START + timedelta(seconds=4),
            received_monotonic_ns=4,
        ),
    ]

    session.record_lifecycle(
        {"ticker": MARKET, "status": "active"},
        observed_at_utc=START,
        evaluated_at_utc=START,
    )
    for event in events:
        session.record_event(event)
    session.record_lifecycle(
        {"ticker": MARKET, "status": "active"},
        observed_at_utc=START + timedelta(seconds=300),
        evaluated_at_utc=START + timedelta(seconds=300),
    )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=300),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["runtime_schema_version"] == D2_RUNTIME_SCHEMA_VERSION
    assert summary["raw_event_schema_version"] == "edmn.kalshi.ws.raw.v2"
    assert summary["threshold_policy_version"] == "edmn.v2.thresholds.v1"
    assert summary["actual_elapsed_seconds"] == "300"
    assert summary["public_trade_count"] == 1
    assert summary["rebuild_summaries"][0]["frame_count"] == 2
    assert summary["rebuild_summaries"][0]["pricing_modes"] == ["LEGACY_SIDE_PRICE"]
    assert summary["independent_evidence_classifications"]["duration_evidence"] == "PASS"
    assert summary["independent_evidence_classifications"]["replay_qualification"] == "UNKNOWN"
    assert summary["artifact_integrity_summary"]["append_chain_verified"] is True
    assert summary["artifact_integrity_summary"]["closed_file_hash_verified"] is True
    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "pass"
    assert validation["artifact_integrity"] == "PASS"
    assert validation["replay_qualification"] == "UNKNOWN"
    monitor = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=301))
    assert monitor["campaign"]["runtime_schema_version"] == D2_RUNTIME_SCHEMA_VERSION
    assert monitor["evidence"]["dimensions"]["rebuild_integrity"] == "PASS"
    assert monitor["evidence"]["replay_qualified"] is False
    assert monitor["validation"]["artifact_integrity"] == "PASS"


def test_runtime_preserves_unknown_sequence_and_excluded_delta(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    tracker = _tracker()
    delta = tracker.record(
        {
            "type": "orderbook_delta",
            "sid": 41,
            "seq": 10,
            "msg": {
                "market_ticker": MARKET,
                "side": "yes",
                "price_dollars": "0.42",
                "delta_fp": "1",
            },
        },
        local_row_index=1,
        received_at_utc=START,
        received_monotonic_ns=1,
    )

    session.record_event(delta)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["raw_event_count"] == 1
    assert summary["rebuild_frame_count"] == 0
    assert summary["rebuild_excluded_count"] == 1
    assert summary["independent_evidence_classifications"]["sequence_integrity"] == "UNKNOWN"
    assert summary["independent_evidence_classifications"]["rebuild_integrity"] == "UNKNOWN"


def test_snapshot_only_runtime_preserves_rebuild_pass_but_fails_early_duration(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    tracker = _tracker()
    snapshot = tracker.record(
        {
            "type": "orderbook_snapshot",
            "sid": 41,
            "seq": 1,
            "msg": {
                "market_ticker": MARKET,
                "yes_dollars_fp": [["0.42", "3"]],
                "no_dollars_fp": [],
            },
        },
        local_row_index=1,
        received_at_utc=START + timedelta(seconds=1),
        received_monotonic_ns=1,
    )
    session.record_lifecycle(
        {"ticker": MARKET, "status": "active"},
        observed_at_utc=START,
        evaluated_at_utc=START,
    )
    session.record_event(snapshot)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=100),
        terminal_reason="early_exit",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["snapshot_count"] == 1
    assert summary["delta_count"] == 0
    assert summary["independent_evidence_classifications"]["rebuild_integrity"] == "PASS"
    assert summary["independent_evidence_classifications"]["duration_evidence"] == "FAIL"


def test_explicit_sequence_gap_is_excluded_then_resynced_by_new_snapshot(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=4)
    tracker = _tracker(continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT)
    payloads = [
        {
            "type": "orderbook_snapshot",
            "sid": 41,
            "seq": 1,
            "msg": {
                "market_ticker": MARKET,
                "yes_dollars_fp": [["0.42", "3"]],
                "no_dollars_fp": [],
            },
        },
        {
            "type": "orderbook_delta",
            "sid": 41,
            "seq": 3,
            "msg": {
                "market_ticker": MARKET,
                "side": "yes",
                "price_dollars": "0.42",
                "delta_fp": "1",
            },
        },
        {
            "type": "orderbook_snapshot",
            "sid": 41,
            "seq": 4,
            "msg": {
                "market_ticker": MARKET,
                "yes_dollars_fp": [["0.43", "2"]],
                "no_dollars_fp": [],
            },
        },
    ]
    for index, payload in enumerate(payloads, start=1):
        session.record_event(
            tracker.record(
                payload,
                local_row_index=index,
                received_at_utc=START + timedelta(seconds=index),
                received_monotonic_ns=index,
            )
        )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=4),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["independent_evidence_classifications"]["sequence_integrity"] == "FAIL"
    assert summary["rebuild_frame_count"] == 2
    assert summary["rebuild_excluded_count"] == 1
    assert len(summary["sequence_summaries"]) == 2
    assert any(
        item["aggregate_result"] == "SEQUENCE_INTEGRITY_FAIL"
        for item in summary["sequence_summaries"]
    )


def test_unknown_current_segment_cannot_inherit_historical_sequence_or_rebuild_pass(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=3)
    tracker = _tracker(continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT)
    first_segment = [
        tracker.record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        ),
        tracker.record(
            {
                "type": "orderbook_delta",
                "sid": 41,
                "seq": 2,
                "msg": {
                    "market_ticker": MARKET,
                    "side": "yes",
                    "price_dollars": "0.42",
                    "delta_fp": "1",
                },
            },
            local_row_index=2,
            received_at_utc=START + timedelta(seconds=1),
            received_monotonic_ns=2,
        ),
    ]
    tracker.start_connection()
    tracker.bind_subscription(command_id=1)
    current_unknown = tracker.record(
        {
            "type": "orderbook_delta",
            "sid": 42,
            "msg": {
                "market_ticker": MARKET,
                "side": "yes",
                "price_dollars": "0.42",
                "delta_fp": "1",
            },
        },
        local_row_index=3,
        received_at_utc=START + timedelta(seconds=2),
        received_monotonic_ns=3,
    )
    for event in (*first_segment, current_unknown):
        session.record_event(event)

    summary = session.close(
        ended_at_utc=START + timedelta(seconds=3),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["independent_evidence_classifications"]["sequence_integrity"] == "UNKNOWN"
    assert summary["independent_evidence_classifications"]["rebuild_integrity"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("second_sequence", "expected_state"),
    [(5, "SEQUENCE_DUPLICATE"), (4, "SEQUENCE_OUT_OF_ORDER")],
)
def test_runtime_preserves_duplicate_and_out_of_order_states(
    tmp_path: Path,
    second_sequence: int,
    expected_state: str,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=2)
    tracker = _tracker(continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT)
    events = [
        tracker.record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 5,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        ),
        tracker.record(
            {
                "type": "orderbook_delta",
                "sid": 41,
                "seq": second_sequence,
                "msg": {
                    "market_ticker": MARKET,
                    "side": "yes",
                    "price_dollars": "0.42",
                    "delta_fp": "1",
                },
            },
            local_row_index=2,
            received_at_utc=START + timedelta(seconds=1),
            received_monotonic_ns=2,
        ),
    ]
    for event in events:
        session.record_event(event)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=2),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    states = summary["sequence_summaries"][0]["sequence_states"]
    assert states[expected_state] == 1
    assert summary["rebuild_excluded_count"] == 1
    assert summary["independent_evidence_classifications"]["sequence_integrity"] == "FAIL"


def test_sid_change_creates_a_new_isolated_runtime_segment(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=2)
    tracker = _tracker()
    for index, sid in enumerate((41, 42), start=1):
        session.record_event(
            tracker.record(
                {
                    "type": "orderbook_snapshot",
                    "sid": sid,
                    "seq": index,
                    "msg": {
                        "market_ticker": MARKET,
                        "yes_dollars_fp": [["0.42", str(index)]],
                        "no_dollars_fp": [],
                    },
                },
                local_row_index=index,
                received_at_utc=START + timedelta(seconds=index - 1),
                received_monotonic_ns=index,
            )
        )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=2),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert len(summary["sequence_summaries"]) == 2
    assert summary["sequence_summaries"][1]["segment_boundary_reasons"] == ["SID_CHANGE"]
    assert len([item for item in summary["rebuild_summaries"] if item["frame_count"]]) == 2


def test_runtime_keeps_two_markets_isolated_and_records_explicit_pricing_modes(
    tmp_path: Path,
) -> None:
    other = "D2E-OTHER"
    session = _session(tmp_path, configured_duration_seconds=3)
    tracker = _tracker(markets=(MARKET, other))
    events = [
        tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "sid": 41,
                "msg": {"use_yes_price": True},
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        ),
        *[
            tracker.record(
                {
                    "type": "orderbook_snapshot",
                    "sid": 41,
                    "seq": index,
                    "msg": {
                        "market_ticker": market,
                        "yes_dollars_fp": [["0.42", str(index)]],
                        "no_dollars_fp": [],
                    },
                },
                local_row_index=index,
                received_at_utc=START + timedelta(seconds=index),
                received_monotonic_ns=index,
            )
            for index, market in enumerate((MARKET, other), start=2)
        ],
    ]
    for event in events:
        session.record_event(event)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=3),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    rebuilt = [item for item in summary["rebuild_summaries"] if item["frame_count"]]
    assert {item["market_ticker"] for item in rebuilt} == {MARKET, other}
    assert all(item["pricing_modes"] == ["UNIFIED_YES_PRICE"] for item in rebuilt)
    assert len({item["terminal_state_hash"] for item in rebuilt}) == 2


def test_wrong_market_snapshot_cannot_refresh_selected_market_evidence(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    event = _tracker().record(
        {
            "type": "orderbook_snapshot",
            "sid": 41,
            "seq": 1,
            "msg": {
                "market_ticker": "UNREQUESTED-MARKET",
                "yes_dollars_fp": [["0.42", "3"]],
                "no_dollars_fp": [],
            },
        },
        local_row_index=1,
        received_at_utc=START,
        received_monotonic_ns=1,
    )

    session.record_event(event)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["snapshot_count"] == 1
    assert summary["admitted_selected_snapshot_count"] == 0
    assert summary["first_snapshot_at"] is None
    assert summary["freshness_dimensions"]["orderbook_event_quiet_interval_seconds"] is None
    assert summary["independent_evidence_classifications"]["rebuild_integrity"] == "UNKNOWN"


def test_runtime_pricing_mode_conflict_invalidates_rebuild_dimension(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=2)
    tracker = _tracker()
    events = [
        tracker.record(
            {"type": "subscribed", "id": 1, "sid": 41, "msg": {"use_yes_price": False}},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        ),
        tracker.record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "use_yes_price": True,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
            local_row_index=2,
            received_at_utc=START + timedelta(seconds=1),
            received_monotonic_ns=2,
        ),
    ]
    for event in events:
        session.record_event(event)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=2),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["rebuild_frame_count"] == 0
    assert summary["independent_evidence_classifications"]["rebuild_integrity"] == "FAIL"
    assert any(
        "CONTRADICTORY_PRICING_MODE" in item["invalidation_reasons"]
        for item in summary["rebuild_summaries"]
    )


def test_quiet_orderbook_does_not_become_transport_loss_and_lifecycle_stays_fresh(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=301)
    tracker = _tracker()
    session.record_event(
        tracker.record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    for seconds in (0, 60, 120, 180, 240, 300):
        observed = START + timedelta(seconds=seconds)
        session.record_lifecycle(
            {"ticker": MARKET, "status": "active"},
            observed_at_utc=observed,
            evaluated_at_utc=observed,
        )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=301),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["freshness_dimensions"]["transport_keepalive_status"] == (
        "UNKNOWN_NOT_OBSERVED"
    )
    assert summary["freshness_dimensions"]["orderbook_event_quiet_interval_seconds"] == 301
    assert summary["independent_evidence_classifications"]["transport_connectivity"] == "PASS"
    assert summary["independent_evidence_classifications"]["market_lifecycle_validity"] == "PASS"


def test_closed_and_stale_lifecycle_fail_independently(tmp_path: Path) -> None:
    closed = _session(tmp_path / "closed", configured_duration_seconds=1)
    closed.record_lifecycle(
        {"ticker": MARKET, "status": "finalized"},
        observed_at_utc=START + timedelta(seconds=1),
        evaluated_at_utc=START + timedelta(seconds=1),
    )
    closed_summary = closed.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=False,
        subscription_acknowledged=False,
        blocker_code=None,
    )
    stale = _session(tmp_path / "stale", configured_duration_seconds=121)
    stale.record_lifecycle(
        {"ticker": MARKET, "status": "active"},
        observed_at_utc=START,
        evaluated_at_utc=START,
    )
    stale_summary = stale.close(
        ended_at_utc=START + timedelta(seconds=121),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=False,
        subscription_acknowledged=False,
        blocker_code=None,
    )

    assert closed_summary["independent_evidence_classifications"][
        "market_lifecycle_validity"
    ] == "FAIL"
    assert stale_summary["independent_evidence_classifications"][
        "market_lifecycle_validity"
    ] == "FAIL"


def test_runtime_rotation_uses_segment_local_chain_indices(tmp_path: Path) -> None:
    session = _session(
        tmp_path,
        configured_duration_seconds=1,
        max_segment_bytes=1,
    )
    tracker = _tracker()
    for index in range(1, 3):
        event = tracker.record(
            {"type": "heartbeat", "sid": 41, "seq": index},
            local_row_index=index,
            received_at_utc=START + timedelta(milliseconds=index),
            received_monotonic_ns=index,
        )
        session.record_event(event)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert len(summary["segment_summaries"]) >= 2
    for segment in summary["segment_summaries"]:
        rows = [
            json.loads(line)
            for line in (tmp_path / segment["data_path"]).read_text().splitlines()
        ]
        assert [row["local_row_index"] for row in rows] == list(
            range(1, len(rows) + 1)
        )


def test_runtime_crash_recovery_removes_only_partial_tail_and_never_restarts(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    event = _tracker().record(
        {"type": "heartbeat", "sid": 41, "seq": 1},
        local_row_index=1,
        received_at_utc=START + timedelta(seconds=1),
        received_monotonic_ns=1,
    )
    session.record_event(event)
    session._writer._handle.close()
    with session.current_data_path.open("ab") as handle:
        handle.write(b'{"local_row_index":2')

    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=10),
    )

    assert recovery["partial_tail_bytes_removed"] > 0
    assert recovery["snapshot_required"] is True
    assert recovery["inherited_book_state"] is False
    assert recovery["automatic_restart"] is False
    assert recovery["replay_qualified"] is False
    assert recovery["validation_status"] == "pass"
    validation = validate_d2_runtime_artifacts(tmp_path)
    monitor = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=10))
    assert validation["status"] == "pass"
    assert validation["process_liveness"] == "FAIL"
    assert monitor["run_info"]["health"] == "BLOCKED"


def test_runtime_recovers_immediate_zero_record_crash(tmp_path: Path) -> None:
    session = RuntimeEvidenceSession(
        output_dir=tmp_path,
        campaign_id="d2e-zero-record-crash",
        mode="read_only_websocket_smoke",
        configured_duration_seconds=300,
        selected_market_metadata={"ticker": MARKET, "status": "active"},
        selected_market_selection={
            "selection_profile": "smoke",
            "selection_gate_result": "pass",
        },
        lifecycle_mode_and_source="selected_market_rest_fallback",
        pricing_mode_and_source="subscription_metadata_or_explicit_venue_default",
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        started_at_utc=START,
    )
    session._writer._handle.close()

    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=1),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text())

    assert recovery["validation_status"] == "pass"
    assert summary["campaign_id"] == "d2e-zero-record-crash"
    assert summary["event_count"] == 0


def test_runtime_crash_recovery_reconciles_complete_tail_record_counts(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    event = _tracker().record(
        {"type": "heartbeat", "sid": 41, "seq": 1},
        local_row_index=1,
        received_at_utc=START + timedelta(seconds=1),
        received_monotonic_ns=1,
    )
    rebuilt = KalshiWsBookRebuilder().apply(event)
    session._writer.append(
        {
            "schema_version": ws_runtime.D2_RUNTIME_RECORD_SCHEMA_VERSION,
            "record_type": "raw_transport_event",
            "campaign_id": session.campaign_id,
            "local_row_index": session._evidence_local_row_index + 1,
            "observed_at_utc": event.received_at_utc.isoformat(),
            "d2a_event": event.to_record(),
            "d2b_rebuild": {
                "disposition": rebuilt.disposition,
                "reason": rebuilt.reason,
                "frame": None,
            },
            "d2c_public_trades": [],
        }
    )
    session._writer._handle.close()

    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=10),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text())

    assert recovery["validation_status"] == "pass"
    assert summary["event_count"] == 1
    assert summary["raw_event_count"] == 1
    assert summary["sequence_summaries"]
    assert summary["rebuild_summaries"]
    assert summary["freshness_dimensions"]["transport_keepalive_status"] == "OBSERVED"
    assert summary["transport_keepalive_age_seconds"] == 9
    assert summary["max_transport_keepalive_age_seconds"] == 9


def test_runtime_recovery_preserves_single_preclose_terminal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )

    def crash_before_segment_close(*_args, **_kwargs):
        raise RuntimeError("synthetic pre-close crash")

    with monkeypatch.context() as scoped:
        scoped.setattr(ws_runtime.EvidenceSegmentWriter, "close", crash_before_segment_close)
        with pytest.raises(RuntimeError, match="pre-close crash"):
            session.close(
                ended_at_utc=START + timedelta(seconds=1),
                terminal_reason="bounded_duration_complete",
                stop_requested=False,
                connection_established=True,
                subscription_acknowledged=True,
                blocker_code=None,
            )
    session._writer._handle.close()

    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=2),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text())
    terminal_count = sum(
        json.loads(line)["record_type"] == "runtime_terminal"
        for segment in summary["segment_summaries"]
        for line in (tmp_path / segment["data_path"]).read_text().splitlines()
    )

    assert recovery["validation_status"] == "pass"
    assert terminal_count == 1
    assert summary["terminal_reason"] == "bounded_duration_complete"


def test_validator_rebuilds_d2b_instead_of_trusting_persisted_frame(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    event = _tracker().record(
        {
            "type": "orderbook_snapshot",
            "sid": 41,
            "seq": 1,
            "msg": {
                "market_ticker": MARKET,
                "yes_dollars_fp": [["0.42", "3"]],
                "no_dollars_fp": [],
            },
        },
        local_row_index=1,
        received_at_utc=START,
        received_monotonic_ns=1,
    )
    session.record_event(event)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    records = []
    for segment in summary["segment_summaries"]:
        records.extend(
            json.loads(line)
            for line in (tmp_path / segment["data_path"]).read_text().splitlines()
        )
    raw_record = next(
        record for record in records if record["record_type"] == "raw_transport_event"
    )
    raw_record["d2b_rebuild"]["frame"]["terminal_state_hash"] = "0" * 64

    with pytest.raises(ValueError, match="independent rebuild"):
        ws_runtime._derive_runtime_validation(summary, records)


def test_validator_rejects_tampered_aggregate_rebuild_hashes(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        path = tmp_path / name
        payload = json.loads(path.read_text())
        payload["rebuild_summaries"][0]["frame_hashes"] = ["0" * 64]
        payload["rebuild_summaries"][0]["terminal_state_hash"] = "0" * 64
        path.write_text(json.dumps(payload) + "\n")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("rebuild_summaries" in item for item in validation["failures"])


def test_validator_rejects_tampered_top_level_freshness_timing(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        path = tmp_path / name
        payload = json.loads(path.read_text())
        payload["orderbook_event_quiet_interval_seconds"] = 999_999
        payload["max_orderbook_event_quiet_interval_seconds"] = 999_999
        path.write_text(json.dumps(payload) + "\n")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any(
        "orderbook_event_quiet_interval_seconds" in item
        for item in validation["failures"]
    )


def test_validator_binds_summary_campaign_id_to_durable_records(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        path = tmp_path / name
        payload = json.loads(path.read_text())
        payload["campaign_id"] = "tampered-campaign"
        path.write_text(json.dumps(payload) + "\n")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("campaign_id" in item for item in validation["failures"])


def test_validator_rejects_tampered_segment_summary_closed_hash(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    segment_summary_path = tmp_path / summary["segment_summaries"][0]["summary_path"]
    segment_summary = json.loads(segment_summary_path.read_text())
    segment_summary["closed_file_sha256"] = "0" * 64
    segment_summary_path.write_text(json.dumps(segment_summary) + "\n")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("closed-file hash mismatch" in item for item in validation["failures"])


def test_validator_compares_every_persisted_segment_summary_field(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    segment_summary_path = tmp_path / summary["segment_summaries"][0]["summary_path"]
    baseline = json.loads(segment_summary_path.read_text())
    for delete_field in (False, True):
        segment_summary = dict(baseline)
        if delete_field:
            del segment_summary["terminal_reason"]
        else:
            segment_summary["terminal_reason"] = "tampered"
        segment_summary_path.write_text(json.dumps(segment_summary) + "\n")
        assert validate_d2_runtime_artifacts(tmp_path)["status"] == "fail"
    segment_summary_path.write_text(json.dumps(baseline) + "\n")
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        path = tmp_path / name
        payload = json.loads(path.read_text())
        del payload["segment_summaries"][0]["rotation_reason"]
        path.write_text(json.dumps(payload) + "\n")
    assert validate_d2_runtime_artifacts(tmp_path)["status"] == "fail"


def test_validator_semantically_reconstructs_all_d2c_evidence(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_lifecycle(
        {"ticker": MARKET, "status": "active"},
        observed_at_utc=START,
        evaluated_at_utc=START,
    )
    session.record_event(
        _tracker().record(
            {
                "type": "trade",
                "sid": 41,
                "seq": 1,
                "msg": {"market_ticker": MARKET, "trade_id": "trade-1"},
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    baseline = [
        json.loads(line)
        for segment in summary["segment_summaries"]
        for line in (tmp_path / segment["data_path"]).read_text().splitlines()
    ]

    mutations = (
        lambda rows: next(
            row for row in rows if row["record_type"] == "raw_transport_event"
        ).update(d2c_public_trades=[]),
        lambda rows: next(
            row for row in rows if row["record_type"] == "lifecycle_evidence"
        )["lifecycle_event"].update(market_ticker="OTHER-MARKET"),
        lambda rows: next(
            row for row in rows if row["record_type"] == "connection_evidence"
        )["connection_event"].update(source="TAMPERED"),
    )
    for mutate in mutations:
        rows = json.loads(json.dumps(baseline))
        mutate(rows)
        with pytest.raises(ValueError):
            ws_runtime._derive_runtime_validation(summary, rows)


def test_validator_binds_every_evidence_timing_field_to_terminal_chain(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    names = ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json")
    baseline = json.loads((tmp_path / names[0]).read_text())
    mutations = {
        "configured_duration_seconds": 2,
        "actual_elapsed_seconds": "2",
        "connected_elapsed_seconds": "0",
        "started_at_utc": (START - timedelta(seconds=1)).isoformat(),
        "checkpoint_at_utc": START.isoformat(),
        "first_snapshot_at": START.isoformat(),
        "last_event_at": (START + timedelta(seconds=1)).isoformat(),
        "ended_at": (START + timedelta(seconds=2)).isoformat(),
        "terminal_reason": "tampered_terminal_reason",
        "stop_requested": True,
        "total_disconnect_seconds": "1",
        "transport_keepalive_age_seconds": 999,
        "lifecycle_observation_age_seconds": 999,
        "orderbook_event_quiet_interval_seconds": 999,
        "max_transport_keepalive_age_seconds": 999,
        "max_lifecycle_observation_age_seconds": 999,
        "max_orderbook_event_quiet_interval_seconds": 999,
        "threshold_policy_version": "edmn.v2.thresholds.tampered",
        "threshold_source_commit": "f" * 40,
        "threshold_effective_utc": (START - timedelta(days=1)).isoformat(),
    }
    for field, value in mutations.items():
        tampered = {**baseline, field: value}
        for name in names:
            (tmp_path / name).write_text(json.dumps(tampered) + "\n")
        assert validate_d2_runtime_artifacts(tmp_path)["status"] == "fail", field


def test_runtime_validator_rejects_tampered_durable_record(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    path = tmp_path / summary["segment_summaries"][0]["data_path"]
    path.write_bytes(path.read_bytes().replace(b'"heartbeat"', b'"heartbeaX"', 1))

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert validation["artifact_integrity"] == "FAIL"
    assert any("segment verification failed" in failure for failure in validation["failures"])


def test_validator_derives_dimensions_instead_of_trusting_mutable_summaries(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    tracker = _tracker(continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT)
    session.record_event(
        tracker.record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        path = tmp_path / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["independent_evidence_classifications"]["rebuild_integrity"] = "UNKNOWN"
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)
    monitor = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=1))

    assert validation["status"] == "fail"
    assert validation["rebuild_integrity"] == "PASS"
    assert any("rebuild_integrity" in failure for failure in validation["failures"])
    assert monitor["run_info"]["health"] == "BLOCKED"


def test_validator_rejects_checkpoint_row_count_corruption(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    checkpoint_path = tmp_path / summary["segment_summaries"][0]["checkpoint_path"]
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["last_committed_local_row_index"] = 999
    checkpoint_path.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("checkpoint row count mismatch" in item for item in validation["failures"])


def test_validator_rejects_mislabeled_threshold_policy(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        path = tmp_path / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["threshold_policy_version"] = "edmn.v2.thresholds.unreviewed"
        payload["threshold_policy"]["maximum_disconnect_seconds"] = 999
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("threshold policy" in item for item in validation["failures"])


def test_failed_lifecycle_polling_remains_rate_limited(
    tmp_path: Path,
) -> None:
    fake_time = _FakeTime()
    calls: list[int] = []

    def failing_provider(_ticker: str) -> dict[str, object]:
        calls.append(fake_time.seconds)
        raise RuntimeError("synthetic lifecycle outage")

    summary = run_d2_kalshi_ws_runtime(
        output_dir=tmp_path / "run",
        campaign_id="d2e-lifecycle-rate-limit",
        mode="read_only_websocket_smoke",
        duration_seconds=1_000,
        market_metadata={"ticker": MARKET, "status": "active"},
        market_selection={"selection_profile": "smoke", "selection_gate_result": "pass"},
        auth=KalshiWsAuthConfig(
            api_key_id="fixture-id",
            private_key_path=_private_key(tmp_path),
        ),
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        websocket_factory=lambda *_args, **_kwargs: _FakeWebSocket(
            [{"type": "heartbeat", "sid": 41} for _ in range(100)]
        ),
        lifecycle_provider=failing_provider,
        now=fake_time.now,
        monotonic=fake_time.monotonic,
        monotonic_ns=fake_time.monotonic_ns,
        max_events=100,
    )

    assert summary["event_count"] == 100
    assert 1 < len(calls) <= 5
    assert all(
        current - previous >= 60
        for previous, current in zip(calls, calls[1:], strict=False)
    )


@pytest.mark.parametrize(
    "forbidden_key",
    ["api_key", "order_id", "orders", "fills", "account_number"],
)
def test_actual_runtime_rejects_nested_private_fields_without_persisting_them(
    tmp_path: Path,
    forbidden_key: str,
) -> None:
    fake_time = _FakeTime()
    private_value = "fixture-private-value-must-not-persist"
    websocket = _FakeWebSocket(
        [
            {
                "type": "subscribed",
                "msg": {"metadata": {forbidden_key: private_value}},
            }
        ]
    )
    summary = run_d2_kalshi_ws_runtime(
        output_dir=tmp_path / "run",
        campaign_id="d2e-secret-rejection",
        mode="read_only_websocket_smoke",
        duration_seconds=1,
        market_metadata={"ticker": MARKET, "status": "active"},
        market_selection={"selection_profile": "smoke", "selection_gate_result": "pass"},
        auth=KalshiWsAuthConfig(
            api_key_id="fixture-id",
            private_key_path=_private_key(tmp_path),
        ),
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        websocket_factory=lambda *_args, **_kwargs: websocket,
        lifecycle_provider=lambda ticker: {"ticker": ticker, "status": "active"},
        now=fake_time.now,
        monotonic=fake_time.monotonic,
        monotonic_ns=fake_time.monotonic_ns,
    )

    assert summary["event_count"] == 0
    assert summary["blocker_code"] is not None
    assert private_value not in "".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "run").rglob("*")
        if path.is_file()
    )


def _session(
    root: Path,
    *,
    configured_duration_seconds: int,
    max_segment_bytes: int = 64 * 1024 * 1024,
) -> RuntimeEvidenceSession:
    session = RuntimeEvidenceSession(
        output_dir=root,
        campaign_id="d2e-runtime-test",
        mode="read_only_websocket_smoke",
        configured_duration_seconds=configured_duration_seconds,
        selected_market_metadata={"ticker": MARKET, "status": "active"},
        selected_market_selection={
            "selection_profile": "smoke",
            "selection_gate_result": "pass",
        },
        lifecycle_mode_and_source="selected_market_rest_fallback",
        pricing_mode_and_source="subscription_metadata_or_explicit_venue_default",
        provenance=RuntimeCodeProvenance(
            public_code_commit=COMMIT,
            branch="codex/d2e-runtime-entrypoint-integration",
            remote="https://github.com/minqiyang/market-neutral-trader.git",
            dirty_state=False,
        ),
        threshold_policy=V2_THRESHOLD_POLICY,
        started_at_utc=START,
        checkpoint_every_records=2,
        max_segment_bytes=max_segment_bytes,
    )
    for event_type, reason in (
        (ConnectionEvidenceType.CONNECTION_OPEN, "test_connection_open"),
        (
            ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
            "test_subscription_acknowledged",
        ),
    ):
        session.record_connection_event(
            ConnectionEvidenceEvent(
                event_type=event_type,
                observed_at_utc=START,
                connection_id="test-connection",
                segment_id="test-segment",
                reason=reason,
            )
        )
    return session


def _tracker(
    *,
    markets: tuple[str, ...] = (MARKET,),
    continuity_policy: SequenceContinuityPolicy = SequenceContinuityPolicy.UNKNOWN,
) -> KalshiWsIntegrityTracker:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="d2e-runtime-test",
        requested_market_tickers=markets,
        continuity_policy=continuity_policy,
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1)
    return tracker


class _FakeTime:
    def __init__(self) -> None:
        self.seconds = 0

    def now(self) -> datetime:
        return START + timedelta(seconds=self.seconds)

    def monotonic(self) -> float:
        self.seconds += 1
        return float(self.seconds)

    def monotonic_ns(self) -> int:
        return self.seconds * 1_000_000_000


class _FakeWebSocket:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.messages = [json.dumps(message) for message in messages]

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def send(self, _payload: str) -> None:
        return None

    def recv(self, *, timeout: float | None = None) -> str:
        if self.messages:
            return self.messages.pop(0)
        raise TimeoutError


class _FailingFakeWebSocket(_FakeWebSocket):
    def recv(self, *, timeout: float | None = None) -> str:
        if self.messages:
            return self.messages.pop(0)
        raise RuntimeError("synthetic disconnect")


def _private_key(root: Path) -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = root / "fixture.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return path
