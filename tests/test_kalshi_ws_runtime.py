from __future__ import annotations

import json
import tracemalloc
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
from edmn_trader.adapters.kalshi.ws_auth import KalshiWsAuthBlocked, KalshiWsAuthConfig
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
from edmn_trader.data.evidence_durability import RotationReason
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


def test_runtime_provenance_strips_git_remote_credentials() -> None:
    provenance = RuntimeCodeProvenance(
        COMMIT,
        "main",
        "https://user:secret-token@github.com/org/repo.git?token=secret",
        False,
    )

    assert provenance.remote == "https://github.com/org/repo.git"
    assert "secret" not in json.dumps(provenance.to_record())


def test_public_entrypoint_collects_provenance_from_imported_repository(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed_roots: list[Path] = []
    provenance = RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False)

    def collect(root: Path) -> RuntimeCodeProvenance:
        observed_roots.append(root)
        return provenance

    def block_auth():
        raise KalshiWsAuthBlocked("NO_WS_CREDENTIALS")

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    monkeypatch.setattr(v2_readonly_campaign, "collect_runtime_code_provenance", collect)
    monkeypatch.setattr(v2_readonly_campaign, "load_kalshi_ws_auth_config_from_env", block_auth)

    v2_readonly_campaign.run_kalshi_ws_smoke(
        output_dir=tmp_path / "run",
        campaign_id="d2e-provenance-root",
        duration_seconds=300,
        max_markets=1,
        now=START,
    )

    assert observed_roots == [v2_readonly_campaign.PUBLIC_REPO_ROOT]
    assert observed_roots[0] != unrelated


def test_preflight_requires_empty_root_and_rejects_private_metadata(tmp_path: Path) -> None:
    for index, relative_path in enumerate(
        ("campaign_summary.json", "legacy.json", "evidence_segments/partial.jsonl")
    ):
        existing = tmp_path / f"existing-{index}"
        artifact = existing / relative_path
        artifact.parent.mkdir(parents=True)
        artifact.write_text("{}\n", encoding="utf-8")
        with pytest.raises(FileExistsError, match="empty artifact root"):
            ws_runtime.write_d2_runtime_preflight_block(
                output_dir=existing,
                campaign_id="d2e-no-overwrite",
                mode="read_only_websocket_smoke",
                configured_duration_seconds=300,
                provenance=RuntimeCodeProvenance(
                    COMMIT, "main", "https://example.test/repo", False
                ),
                blocker_code="NO_WS_CREDENTIALS",
                started_at_utc=START,
            )

    with pytest.raises(ValueError, match="private account/order data"):
        ws_runtime.write_d2_runtime_preflight_block(
            output_dir=tmp_path / "private-metadata",
            campaign_id="d2e-private-metadata",
            mode="read_only_websocket_smoke",
            configured_duration_seconds=300,
            provenance=RuntimeCodeProvenance(
                COMMIT, "main", "https://example.test/repo", False
            ),
            blocker_code="NO_WS_CREDENTIALS",
            started_at_utc=START,
            selected_market_metadata={"metadata": {"order_id": "private"}},
        )

    with pytest.raises(ValueError, match="private account/order data"):
        RuntimeEvidenceSession(
            output_dir=tmp_path / "private-session",
            campaign_id="d2e-private-session",
            mode="read_only_websocket_smoke",
            configured_duration_seconds=300,
            selected_market_metadata={
                "ticker": MARKET,
                "metadata": {"account_id": "private"},
            },
            selected_market_selection={"selection_gate_result": "pass"},
            lifecycle_mode_and_source="selected_market_rest_fallback",
            pricing_mode_and_source="explicit",
            provenance=RuntimeCodeProvenance(
                COMMIT, "main", "https://example.test/repo", False
            ),
            started_at_utc=START,
        )


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


def test_actual_runtime_accepts_split_public_channel_acknowledgments(tmp_path: Path) -> None:
    fake_time = _FakeTime()
    websocket = _FakeWebSocket(
        [
            {
                "type": "subscribed",
                "id": 1,
                "sid": 11,
                "msg": {"channel": "orderbook_delta"},
            },
            {
                "type": "subscribed",
                "id": 1,
                "sid": 22,
                "msg": {"channel": "trade"},
            },
            {
                "type": "trade",
                "sid": 22,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "trade_id": "trade-before-snapshot",
                },
            },
            {
                "type": "orderbook_snapshot",
                "sid": 11,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            },
            {
                "type": "trade",
                "sid": 22,
                "seq": 2,
                "msg": {"market_ticker": MARKET, "trade_id": "trade-after-snapshot"},
            },
            {
                "type": "orderbook_delta",
                "sid": 11,
                "seq": 2,
                "msg": {
                    "market_ticker": MARKET,
                    "side": "yes",
                    "price_dollars": "0.42",
                    "delta_fp": "1",
                },
            },
        ]
    )

    summary = run_d2_kalshi_ws_runtime(
        output_dir=tmp_path / "run",
        campaign_id="d2e-split-ack",
        mode="read_only_websocket_smoke",
        duration_seconds=300,
        market_metadata={"ticker": MARKET, "status": "active"},
        market_selection={"selection_gate_result": "pass"},
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

    assert summary["subscription_acknowledged"] is True
    assert summary["rebuild_frame_count"] == 2
    assert any(
        rebuild["snapshot_first_admitted"] is True
        for rebuild in summary["rebuild_summaries"]
        if rebuild["orderbook_row_count"]
    )
    assert summary["admitted_selected_delta_count"] == 1
    assert summary["public_trade_count"] == 2
    orderbook_rebuild = next(
        rebuild
        for rebuild in summary["rebuild_summaries"]
        if rebuild["orderbook_row_count"]
    )
    assert orderbook_rebuild["invalidation_reasons"] == {}
    assert orderbook_rebuild["native_state_valid"] is True
    assert orderbook_rebuild["latest_frame_hash"]
    assert orderbook_rebuild["terminal_state_hash"]
    assert validate_d2_runtime_artifacts(tmp_path / "run")["status"] == "pass"


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
                    "msg": {
                        "channels": ["orderbook_delta", "trade"],
                        "use_yes_price": False,
                    },
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

    assert summary["raw_event_count"] == 2
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
    session = _session(tmp_path, configured_duration_seconds=3, use_yes_price=True)
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


def test_control_frame_pricing_conflict_invalidates_rebuild_dimension(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=2)
    tracker = _tracker()
    events = [
        tracker.record(
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "use_yes_price": False,
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
                "type": "ack",
                "sid": 41,
                "seq": 2,
                "msg": {"use_yes_price": True},
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

    assert summary["independent_evidence_classifications"]["rebuild_integrity"] == "FAIL"
    assert any(
        "CONTRADICTORY_PRICING_MODE" in item["invalidation_reasons"]
        for item in summary["rebuild_summaries"]
    )


def test_running_monitor_blocks_unsafe_or_incomplete_runtime_summary(tmp_path: Path) -> None:
    _session(tmp_path, configured_duration_seconds=300)
    summary_path = tmp_path / "campaign_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.pop("independent_evidence_classifications")
    summary["selected_market_metadata"]["order_id"] = "private-value"
    summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")

    snapshot = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=1))

    assert snapshot["run_info"]["health"] == "BLOCKED"
    assert snapshot["validation"]["status"] == "fail"


def test_running_monitor_never_reports_paper_ok(tmp_path: Path) -> None:
    _session(tmp_path, configured_duration_seconds=300)
    summary_path = tmp_path / "campaign_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["independent_evidence_classifications"] = {
        field: "PASS"
        for field in summary["independent_evidence_classifications"]
    }
    summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")

    snapshot = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=1))

    assert snapshot["run_info"]["health"] == "WARNING"


def test_running_monitor_blocks_tampered_safety_scalars(tmp_path: Path) -> None:
    _session(tmp_path, configured_duration_seconds=300)
    summary_path = tmp_path / "campaign_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        {
            "live_gate_status": "enabled",
            "production_endpoint_used": True,
            "submit_attempts": 1,
        }
    )
    summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")

    snapshot = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=1))

    assert snapshot["run_info"]["health"] == "BLOCKED"
    assert snapshot["validation"]["status"] == "fail"


def test_validator_rejects_noncanonical_durable_provenance(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    launch_path = tmp_path / session.current_data_path.relative_to(tmp_path)
    launch_record = json.loads(launch_path.read_text(encoding="utf-8").splitlines()[0])
    launch = launch_record["runtime_launch"]
    launch["branch"] = ""

    with pytest.raises(ValueError, match="provenance"):
        ws_runtime._validate_runtime_launch_record(launch, session.campaign_id)


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


def test_boundary_disconnects_count_against_transport_threshold(tmp_path: Path) -> None:
    session = _session_without_connection(tmp_path, configured_duration_seconds=1_800)
    for event_type, observed_at in (
        (ConnectionEvidenceType.CONNECTION_OPEN, START + timedelta(seconds=60)),
        (ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED, START + timedelta(seconds=60)),
        (ConnectionEvidenceType.CONNECTION_CLOSE, START + timedelta(seconds=1_800)),
    ):
        session.record_connection_event(
            ConnectionEvidenceEvent(
                event_type=event_type,
                observed_at_utc=observed_at,
                connection_id="late-connection",
                segment_id="late-segment",
                reason="boundary_disconnect_test",
            )
        )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1_800),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert "60" in summary["disconnect_durations"]
    assert summary["maximum_disconnect_seconds"] == "60"
    assert summary["independent_evidence_classifications"]["transport_connectivity"] == "FAIL"


def test_freshness_maximum_includes_start_to_first_observation(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1_800)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41},
            local_row_index=1,
            received_at_utc=START + timedelta(seconds=1_700),
            received_monotonic_ns=1,
        )
    )
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1_800),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    assert summary["transport_keepalive_age_seconds"] == 100
    assert summary["max_transport_keepalive_age_seconds"] == 1_700
    assert summary["independent_evidence_classifications"]["transport_keepalive"] == "FAIL"


def test_validator_rejects_event_before_connection_subscription_ack(tmp_path: Path) -> None:
    session = _session_without_connection(tmp_path, configured_duration_seconds=1)
    tracker = _tracker(offset=False)
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.CONNECTION_OPEN,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason="unacknowledged_connection",
        )
    )
    session.record_event(
        tracker.record(
            {"type": "heartbeat", "sid": 41},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="runtime_blocked:SUBSCRIPTION_REJECTED",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=False,
        blocker_code="SUBSCRIPTION_REJECTED",
    )

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any(
        "before subscription acknowledgment" in failure
        for failure in validation["failures"]
    )


def test_validator_rejects_ack_not_grounded_in_all_durable_channel_frames(
    tmp_path: Path,
) -> None:
    session = _session_without_connection(tmp_path, configured_duration_seconds=1)
    tracker = _tracker(offset=False)
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.CONNECTION_OPEN,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id="d2e-runtime-test:segment:0001",
            reason="partial_ack_connection",
        )
    )
    session.record_event(
        tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "msg": {"channel": "orderbook_delta"},
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason="incorrect_combined_ack",
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

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any(
        "typed subscription acknowledgment precedes durable raw channels" in item
        for item in validation["failures"]
    )


def test_validator_rejects_data_connection_with_no_raw_ack_frame(tmp_path: Path) -> None:
    session = _session_without_connection(tmp_path, configured_duration_seconds=1)
    tracker = _tracker(offset=False)
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.CONNECTION_OPEN,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id="d2e-runtime-test:segment:0001",
            reason="missing_raw_ack_connection",
        )
    )
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason="ungrounded_typed_ack",
        )
    )
    session.record_event(
        tracker.record(
            {
                "type": "orderbook_snapshot",
                "sid": 11,
                "seq": 1,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "1"]],
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

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any(
        "typed subscription acknowledgment precedes durable raw channels" in item
        for item in validation["failures"]
    )


def test_validator_rejects_typed_ack_before_durable_raw_channels(tmp_path: Path) -> None:
    session = _session_without_connection(tmp_path, configured_duration_seconds=61)
    tracker = _tracker(offset=False)
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.CONNECTION_OPEN,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason="typed_ack_before_raw_channels",
        )
    )
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason="typed_ack_before_raw_channels",
        )
    )
    session.record_event(
        tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "msg": {"channels": ["orderbook_delta", "trade"]},
            },
            local_row_index=1,
            received_at_utc=START + timedelta(seconds=60),
            received_monotonic_ns=1,
        )
    )
    running = json.loads((tmp_path / "campaign_summary.json").read_text())
    assert running["subscription_acknowledged"] is False
    assert running["independent_evidence_classifications"]["subscription_status"] == (
        "FAIL"
    )
    session.close(
        ended_at_utc=START + timedelta(seconds=61),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any(
        "typed subscription acknowledgment precedes durable raw channels" in item
        for item in validation["failures"]
    )


def test_validator_requires_contiguous_d2a_runtime_indices(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41},
            local_row_index=2,
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

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("D2A local row indices" in failure for failure in validation["failures"])


def test_validator_rejects_reused_connection_identity(tmp_path: Path) -> None:
    session = _session_without_connection(tmp_path, configured_duration_seconds=2)
    tracker = _tracker(offset=False)
    for event_type, observed_at, segment_id in (
        (ConnectionEvidenceType.CONNECTION_OPEN, START, "segment-1"),
        (ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED, START, "segment-2"),
        (ConnectionEvidenceType.CONNECTION_CLOSE, START + timedelta(seconds=1), "segment-2"),
        (ConnectionEvidenceType.RECONNECT, START + timedelta(seconds=1), "segment-3"),
        (
            ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
            START + timedelta(seconds=1),
            "segment-4",
        ),
    ):
        session.record_connection_event(
            ConnectionEvidenceEvent(
                event_type=event_type,
                observed_at_utc=observed_at,
                connection_id=tracker.connection_id,
                segment_id=segment_id,
                reason="reused_connection_test",
            )
        )
        if event_type is ConnectionEvidenceType.CONNECTION_OPEN:
            session.record_event(
                tracker.record(
                    {
                        "type": "subscribed",
                        "id": 1,
                        "msg": {"channels": ["orderbook_delta", "trade"]},
                    },
                    local_row_index=1,
                    received_at_utc=START,
                    received_monotonic_ns=1,
                )
            )
    session.close(
        ended_at_utc=START + timedelta(seconds=2),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("connection identifiers must be unique" in item for item in validation["failures"])


def test_validator_rejects_connection_outside_terminal_interval(tmp_path: Path) -> None:
    session = _session_without_connection(tmp_path, configured_duration_seconds=1)
    tracker = _tracker(offset=False)
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.CONNECTION_OPEN,
            observed_at_utc=START - timedelta(seconds=1),
            connection_id=tracker.connection_id,
            segment_id="early-segment",
            reason="pre_runtime_connection",
        )
    )
    session.record_event(
        tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "msg": {"channels": ["orderbook_delta", "trade"]},
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id="subscription-segment",
            reason="subscription_acknowledged",
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

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("outside terminal timing" in item for item in validation["failures"])


def test_validator_rejects_private_account_fields_in_runtime_metadata(tmp_path: Path) -> None:
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
        artifact = json.loads(path.read_text())
        artifact["selected_market_metadata"]["order_id"] = "private"
        path.write_text(json.dumps(artifact), encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("private account/order data" in failure for failure in validation["failures"])


@pytest.mark.parametrize("escaped_path", ["../outside.events.jsonl", "/tmp/outside.jsonl"])
def test_validator_rejects_segment_paths_outside_runtime_root(
    tmp_path: Path,
    escaped_path: str,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    summary_path = tmp_path / "campaign_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["segment_summaries"][0]["data_path"] = escaped_path
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("artifact path" in item for item in validation["failures"])


def test_validator_rejects_unlisted_segment_artifact(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    orphan = tmp_path / "evidence_segments" / "orphan.events.jsonl"
    orphan.write_text('{"unlisted":true}\n', encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("unlisted files" in item for item in validation["failures"])


@pytest.mark.parametrize("metadata_name", ["campaign_manifest.json", "run_metadata.json"])
def test_validator_rejects_fixed_metadata_symlink_escape(
    tmp_path: Path,
    metadata_name: str,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    outside = tmp_path.parent / f"{tmp_path.name}-metadata.json"
    outside.write_text("{}\n", encoding="utf-8")
    (tmp_path / metadata_name).unlink()
    (tmp_path / metadata_name).symlink_to(outside)

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any(metadata_name in item for item in validation["failures"])


@pytest.mark.parametrize("alias_kind", ["nested", "symlink", "directory_symlink"])
def test_validator_rejects_nested_or_alias_segment_artifact(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    evidence_root = tmp_path / "evidence_segments"
    if alias_kind == "nested":
        orphan = evidence_root / "nested" / "orphan.events.jsonl"
        orphan.parent.mkdir()
        orphan.write_text('{"unlisted":true}\n', encoding="utf-8")
    elif alias_kind == "symlink":
        target = tmp_path / summary["segment_summaries"][0]["data_path"]
        (evidence_root / "alias.events.jsonl").symlink_to(target)
    else:
        (evidence_root / "aliasdir").symlink_to(
            evidence_root,
            target_is_directory=True,
        )

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("unlisted files" in item for item in validation["failures"])


def test_validator_rejects_segment_symlink_escape(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    outside = tmp_path.parent / f"{tmp_path.name}-outside.jsonl"
    outside.write_text("outside\n", encoding="utf-8")
    symlink = tmp_path / "evidence_segments" / "escape.events.jsonl"
    symlink.symlink_to(outside)
    summary_path = tmp_path / "campaign_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["segment_summaries"][0]["data_path"] = str(symlink.relative_to(tmp_path))
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("escapes the runtime root" in item for item in validation["failures"])


def test_validator_binds_market_selection_to_durable_launch_record(tmp_path: Path) -> None:
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
        artifact = json.loads(path.read_text())
        artifact["selected_market_selection"]["time_to_close_at_launch_seconds"] = 1
        path.write_text(json.dumps(artifact), encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("selected_market_selection" in item for item in validation["failures"])


def test_missing_orderbook_observation_is_unknown_not_fresh(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    validation = validate_d2_runtime_artifacts(tmp_path)

    assert summary["websocket_message_freshness_status"] == "UNKNOWN_NOT_OBSERVED"
    assert validation["status"] == "pass"


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


def test_runtime_open_status_and_rebuild_hash_memory_are_bounded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    writes: list[Path] = []
    real_atomic_write = ws_runtime._atomic_write_json

    def counted_write(path: Path, payload) -> None:
        writes.append(path)
        real_atomic_write(path, payload)

    monkeypatch.setattr(ws_runtime, "_atomic_write_json", counted_write)
    session = RuntimeEvidenceSession(
        output_dir=tmp_path,
        campaign_id="d2e-bounded-runtime",
        mode="read_only_websocket_campaign",
        configured_duration_seconds=300,
        selected_market_metadata={"ticker": MARKET, "status": "active"},
        selected_market_selection={"selection_gate_result": "pass"},
        lifecycle_mode_and_source="selected_market_rest_fallback",
        pricing_mode_and_source="explicit",
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        started_at_utc=START,
        checkpoint_every_records=1_000,
    )
    tracker = KalshiWsIntegrityTracker(
        campaign_id="d2e-bounded-runtime",
        requested_market_tickers=(MARKET,),
        continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT,
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1)
    for event_type, reason in (
        (ConnectionEvidenceType.CONNECTION_OPEN, "bounded_connection_open"),
        (ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED, "bounded_subscription_ack"),
    ):
        session.record_connection_event(
            ConnectionEvidenceEvent(
                event_type=event_type,
                observed_at_utc=START,
                connection_id=tracker.connection_id,
                segment_id=(
                    "d2e-bounded-runtime:segment:0001"
                    if event_type is ConnectionEvidenceType.CONNECTION_OPEN
                    else tracker.segment_id
                ),
                reason=reason,
            )
        )
    for index in range(1, 201):
        payload = (
            {
                "type": "orderbook_snapshot",
                "sid": 41,
                "seq": index,
                "msg": {
                    "market_ticker": MARKET,
                    "yes_dollars_fp": [["0.42", "3"]],
                    "no_dollars_fp": [],
                },
            }
            if index == 1
            else {
                "type": "orderbook_delta",
                "sid": 41,
                "seq": index,
                "msg": {
                    "market_ticker": MARKET,
                    "side": "yes",
                    "price_dollars": "0.42",
                    "delta_fp": "1",
                },
            }
        )
        session.record_event(
            tracker.record(
                payload,
                local_row_index=index,
                received_at_utc=START,
                received_monotonic_ns=index,
            )
        )
    session.record_event(
        tracker.record(
            {"type": "heartbeat", "sid": 41, "seq": 201},
            local_row_index=201,
            received_at_utc=START + timedelta(seconds=61),
            received_monotonic_ns=201,
        )
    )
    rebuild_summary = session._rebuild_summary_records()[0]
    session._writer._handle.close()

    assert len(writes) == 4
    assert "frame_hashes" not in rebuild_summary
    assert len(rebuild_summary["frame_hash_chain"]) == 64
    assert len(rebuild_summary["latest_frame_hash"]) == 64


def test_runtime_validation_accumulator_is_bounded_at_100k_events() -> None:
    campaign_id = "d2e-runtime-100k"
    provenance = RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False)
    tracker = KalshiWsIntegrityTracker(
        campaign_id=campaign_id,
        requested_market_tickers=(MARKET,),
    )
    tracker.start_connection()
    opening_segment = tracker.segment_id
    tracker.bind_subscription(command_id=1)
    subscription_segment = tracker.segment_id

    def records():
        yield {
            "record_type": "runtime_launch",
            "campaign_id": campaign_id,
            "runtime_launch": {
                "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
                "raw_event_schema_version": "edmn.kalshi.ws.raw.v2",
                "evidence_schema_version": "edmn.evidence.chain.v1",
                "threshold_policy_version": V2_THRESHOLD_POLICY.version,
                "threshold_source_commit": COMMIT,
                "threshold_policy": V2_THRESHOLD_POLICY.to_record(),
                **provenance.to_record(),
                "campaign_id": campaign_id,
                "mode": "read_only_websocket_campaign",
                "configured_duration_seconds": 300,
                "started_at_utc": START.isoformat(),
                "selected_market_metadata": {"ticker": MARKET, "status": "active"},
                "selected_market_selection": {"selection_gate_result": "pass"},
                "lifecycle_mode_and_source": "selected_market_rest_fallback",
                "pricing_mode_and_source": "explicit_subscription_use_yes_price_false",
                "subscription_command_id": 1,
                "subscription_channels": ["orderbook_delta", "trade"],
                "use_yes_price": False,
            },
        }
        yield {
            "record_type": "connection_evidence",
            "campaign_id": campaign_id,
            "connection_event": ConnectionEvidenceEvent(
                event_type=ConnectionEvidenceType.CONNECTION_OPEN,
                observed_at_utc=START,
                connection_id=tracker.connection_id,
                segment_id=opening_segment,
                reason="synthetic_100k_validation",
            ).to_record(),
        }
        raw_ack = tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "msg": {"channels": ["orderbook_delta", "trade"]},
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
        yield {
            "record_type": "raw_transport_event",
            "campaign_id": campaign_id,
            "d2a_event": raw_ack.to_record(),
            "d2b_rebuild": {
                "disposition": "IGNORED_NON_ORDERBOOK",
                "reason": None,
                "frame": None,
            },
            "d2c_public_trades": [],
        }
        yield {
            "record_type": "connection_evidence",
            "campaign_id": campaign_id,
            "connection_event": ConnectionEvidenceEvent(
                event_type=ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
                observed_at_utc=START,
                connection_id=tracker.connection_id,
                segment_id=subscription_segment,
                reason="synthetic_100k_validation",
            ).to_record(),
        }
        for index in range(2, 100_001):
            event = tracker.record(
                {"type": "heartbeat"},
                local_row_index=index,
                received_at_utc=START,
                received_monotonic_ns=index,
            )
            yield {
                "record_type": "raw_transport_event",
                "campaign_id": campaign_id,
                "d2a_event": event.to_record(),
                "d2b_rebuild": {
                    "disposition": "IGNORED_NON_ORDERBOOK",
                    "reason": None,
                    "frame": None,
                },
                "d2c_public_trades": [],
            }

    summary = {
        "campaign_id": campaign_id,
        "mode": "read_only_websocket_campaign",
        "blocker_code": None,
        "configured_duration_seconds": 300,
        "started_at": START.isoformat(),
        "ended_at": (START + timedelta(seconds=300)).isoformat(),
        "terminal_reason": "bounded_duration_complete",
        "stop_requested": False,
        "threshold_source_commit": COMMIT,
    }
    tracemalloc.start()
    _, counts, _, _ = ws_runtime._derive_runtime_validation(
        summary,
        records(),
        allow_summary_terminal=True,
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert counts["event_count"] == 100_000
    assert peak < 64 * 1024 * 1024


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


def test_running_monitor_reports_observed_connection_and_freshness(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START + timedelta(seconds=60),
            received_monotonic_ns=1,
        )
    )

    monitor = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=60))
    campaign = monitor["campaign"]

    assert campaign["status"] == "D2_RUNTIME_RUNNING"
    assert campaign["connection_established"] is True
    assert campaign["subscription_acknowledged"] is True
    assert Decimal(campaign["connected_elapsed_seconds"]) == 60
    assert campaign["freshness_dimensions"]["transport_keepalive_age_seconds"] == 0
    assert campaign["exchange_heartbeat_status"] == "OBSERVED"
    assert campaign["independent_evidence_classifications"][
        "transport_connectivity"
    ] == "PASS"
    assert campaign["independent_evidence_classifications"]["subscription_status"] == (
        "PASS"
    )
    assert campaign["independent_evidence_classifications"]["transport_keepalive"] == (
        "PASS"
    )


def test_running_monitor_blocks_observed_lifecycle_failure(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session.record_lifecycle(
        {"ticker": MARKET, "status": "finalized"},
        observed_at_utc=START + timedelta(seconds=60),
        evaluated_at_utc=START + timedelta(seconds=60),
    )

    monitor = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=60))

    assert monitor["campaign"]["market_lifecycle_status"] == "SETTLED"
    assert monitor["campaign"]["independent_evidence_classifications"][
        "market_lifecycle_validity"
    ] == "FAIL"
    assert monitor["campaign"]["status"] == "D2_RUNTIME_EVIDENCE_FAILED"
    assert monitor["run_info"]["health"] == "BLOCKED"


def test_running_monitor_blocks_sequence_and_rebuild_failures(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    tracker = _tracker(
        continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT,
    )
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
            received_at_utc=START + timedelta(seconds=60),
            received_monotonic_ns=1,
        )
    )
    session.record_event(
        tracker.record(
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
            local_row_index=2,
            received_at_utc=START + timedelta(seconds=120),
            received_monotonic_ns=2,
        )
    )

    monitor = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=120))
    dimensions = monitor["campaign"]["independent_evidence_classifications"]

    assert dimensions["sequence_integrity"] == "FAIL"
    assert dimensions["rebuild_integrity"] == "FAIL"
    assert monitor["campaign"]["status"] == "D2_RUNTIME_EVIDENCE_FAILED"
    assert monitor["run_info"]["health"] == "BLOCKED"


def test_running_monitor_does_not_pass_stale_keepalive_on_lifecycle_write(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START + timedelta(seconds=1),
            received_monotonic_ns=1,
        )
    )
    session.record_lifecycle(
        {"ticker": MARKET, "status": "active"},
        observed_at_utc=START + timedelta(seconds=300),
        evaluated_at_utc=START + timedelta(seconds=300),
    )

    monitor = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=300))
    campaign = monitor["campaign"]

    assert campaign["freshness_dimensions"]["transport_keepalive_age_seconds"] == 299
    assert campaign["independent_evidence_classifications"]["transport_keepalive"] == (
        "FAIL"
    )
    assert monitor["campaign"]["status"] == "D2_RUNTIME_EVIDENCE_FAILED"
    assert monitor["run_info"]["health"] == "BLOCKED"

    stalled_monitor = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=1_000))
    assert stalled_monitor["campaign"]["freshness_dimensions"][
        "transport_keepalive_age_seconds"
    ] == 999
    assert stalled_monitor["campaign"]["status"] == "D2_RUNTIME_EVIDENCE_FAILED"
    assert stalled_monitor["run_info"]["health"] == "BLOCKED"


def test_running_monitor_rounds_fractional_staleness_up(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START + timedelta(seconds=60),
            received_monotonic_ns=1,
        )
    )

    monitor = build_monitor_snapshot(
        tmp_path,
        now=START + timedelta(seconds=180, microseconds=100_000),
    )

    assert monitor["campaign"]["freshness_dimensions"][
        "transport_keepalive_age_seconds"
    ] == 121
    assert monitor["campaign"]["status"] == "D2_RUNTIME_EVIDENCE_FAILED"
    assert monitor["run_info"]["health"] == "BLOCKED"


def test_validator_rejects_segment_root_symlink(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    evidence_root = tmp_path / "evidence_segments"
    real_root = tmp_path / "real_segments"
    evidence_root.rename(real_root)
    evidence_root.symlink_to(real_root, target_is_directory=True)

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("unlisted files" in item for item in validation["failures"])


def test_runtime_recovery_rejects_path_escape_without_touching_target(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session._writer._handle.close()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.events.jsonl"
    outside.write_text("outside-must-remain\n", encoding="utf-8")
    summary_path = tmp_path / "campaign_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["segment_summaries"][-1]["data_path"] = f"../{outside.name}"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="relative to the runtime root"):
        recover_d2_runtime_artifacts(
            tmp_path,
            recovered_at_utc=START + timedelta(seconds=1),
        )

    assert outside.read_text(encoding="utf-8") == "outside-must-remain\n"


def test_runtime_recovery_accepts_runtime_root_symlink(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    session = _session(actual, configured_duration_seconds=300)
    session._writer._handle.close()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)

    recovery = recover_d2_runtime_artifacts(
        alias,
        recovered_at_utc=START + timedelta(seconds=1),
    )

    assert recovery["validation_status"] == "pass"
    assert (actual / "campaign_validation.json").is_file()


def test_runtime_recovery_rejects_dangling_partial_successor_before_mutation(
    tmp_path: Path,
) -> None:
    session = RuntimeEvidenceSession(
        output_dir=tmp_path,
        campaign_id="d2e-dangling-successor",
        mode="read_only_websocket_smoke",
        configured_duration_seconds=300,
        selected_market_metadata={"ticker": MARKET, "status": "active"},
        selected_market_selection={"selection_gate_result": "pass"},
        lifecycle_mode_and_source="selected_market_rest_fallback",
        pricing_mode_and_source="explicit",
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        started_at_utc=START,
    )
    session._writer.close(
        terminal_reason="rotation",
        rotation_reason=RotationReason.BYTE_LIMIT,
    )
    successor = tmp_path / "evidence_segments" / (
        "d2e-dangling-successor.evidence.0002.summary.json"
    )
    successor.symlink_to(tmp_path / "missing-summary.json")

    with pytest.raises(ValueError, match="partial successor|must not be a symlink"):
        recover_d2_runtime_artifacts(
            tmp_path,
            recovered_at_utc=START + timedelta(seconds=2),
        )
    assert not (tmp_path / "runtime_recovery.json").exists()


@pytest.mark.parametrize(
    "missing_artifact",
    ["start", "timestamp", "recovery", "recovery_symlink", "extra"],
)
def test_validator_requires_untampered_recovery_metadata(
    tmp_path: Path,
    missing_artifact: str,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session._writer._handle.close()
    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=10),
    )
    assert recovery["validation_status"] == "pass"
    if missing_artifact in {"start", "timestamp"}:
        summary = json.loads((tmp_path / "campaign_summary.json").read_text())
        recovered_segment = next(
            segment
            for segment in summary["segment_summaries"]
            if segment.get("recovery_status") == "CRASH_RECOVERED"
        )
        start_path = tmp_path / recovered_segment["next_segment_metadata_path"]
        if missing_artifact == "start":
            start_path.unlink()
        else:
            start = json.loads(start_path.read_text())
            start["created_at_utc"] = (START + timedelta(hours=1)).isoformat()
            start_path.write_text(json.dumps(start) + "\n", encoding="utf-8")
    elif missing_artifact == "recovery_symlink":
        outside = tmp_path.parent / f"{tmp_path.name}-recovery.json"
        outside.write_text("{}\n", encoding="utf-8")
        recovery_path = tmp_path / "runtime_recovery.json"
        recovery_path.unlink()
        recovery_path.symlink_to(outside)
    elif missing_artifact == "extra":
        recovery_path = tmp_path / "runtime_recovery.json"
        recovery_payload = json.loads(recovery_path.read_text())
        recovery_payload["account_number"] = "must-not-persist"
        recovery_path.write_text(json.dumps(recovery_payload) + "\n", encoding="utf-8")
    else:
        (tmp_path / "runtime_recovery.json").unlink()

    validation = validate_d2_runtime_artifacts(tmp_path)
    assert validation["status"] == "fail"
    assert any("runtime recovery metadata" in item for item in validation["failures"])


def test_runtime_recovery_is_retry_safe_after_metadata_write_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session._writer._handle.close()
    original_write = ws_runtime._atomic_write_json
    failed = False

    def fail_recovery_write(path: Path, payload: dict[str, object]) -> None:
        nonlocal failed
        if path.name == "runtime_recovery.json" and not failed:
            failed = True
            raise RuntimeError("synthetic recovery metadata crash")
        original_write(path, payload)

    monkeypatch.setattr(ws_runtime, "_atomic_write_json", fail_recovery_write)
    with pytest.raises(RuntimeError, match="recovery metadata crash"):
        recover_d2_runtime_artifacts(
            tmp_path,
            recovered_at_utc=START + timedelta(seconds=10),
        )
    monkeypatch.setattr(ws_runtime, "_atomic_write_json", original_write)

    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=20),
    )

    assert recovery["validation_status"] == "pass"


def test_validator_rejects_unknown_runtime_record_type(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text())
    records = list(
        ws_runtime._iter_runtime_records(
            tmp_path / summary["segment_summaries"][0]["data_path"]
        )
    )
    records.append(
        {
            "record_type": "future_extension",
            "campaign_id": summary["campaign_id"],
        }
    )

    with pytest.raises(ValueError, match="unsupported durable runtime record type"):
        ws_runtime._derive_runtime_validation(summary, records)


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
    assert summary["event_count"] == 2
    assert summary["raw_event_count"] == 2
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


def test_runtime_recovers_after_segment_finalized_before_manifest_sync(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )

    def crash_after_segment_close():
        raise RuntimeError("synthetic post-close crash")

    monkeypatch.setattr(session, "_verify_closed_segments", crash_after_segment_close)
    with pytest.raises(RuntimeError, match="post-close crash"):
        session.close(
            ended_at_utc=START + timedelta(seconds=1),
            terminal_reason="bounded_duration_complete",
            stop_requested=False,
            connection_established=True,
            subscription_acknowledged=True,
            blocker_code=None,
        )

    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=2),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text())

    assert recovery["validation_status"] == "pass"
    assert summary["segment_summaries"][0]["recovery_status"] == (
        "FINALIZED_BEFORE_MANIFEST_SYNC"
    )


def test_runtime_recovers_rotation_finalized_before_manifest_sync(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = RuntimeEvidenceSession(
        output_dir=tmp_path,
        campaign_id="d2e-rotation-crash",
        mode="read_only_websocket_smoke",
        configured_duration_seconds=300,
        selected_market_metadata={"ticker": MARKET, "status": "active"},
        selected_market_selection={"selection_gate_result": "pass"},
        lifecycle_mode_and_source="selected_market_rest_fallback",
        pricing_mode_and_source="explicit",
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        started_at_utc=START,
        max_segment_bytes=1,
    )
    tracker = KalshiWsIntegrityTracker(
        campaign_id="d2e-rotation-crash",
        requested_market_tickers=(MARKET,),
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1)
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.CONNECTION_OPEN,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason="rotation_connection_open",
        )
    )
    session.record_event(
        tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "msg": {"channels": ["orderbook_delta", "trade"]},
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )

    def crash_before_rotated_manifest(_observed_at_utc: datetime) -> None:
        raise RuntimeError("synthetic rotation manifest crash")

    monkeypatch.setattr(session, "_write_open_status", crash_before_rotated_manifest)
    with pytest.raises(RuntimeError, match="rotation manifest crash"):
        session.record_connection_event(
            ConnectionEvidenceEvent(
                event_type=ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
                observed_at_utc=START,
                connection_id=tracker.connection_id,
                segment_id=tracker.segment_id,
                reason="rotation_subscription_acknowledged",
            )
        )
    session._writer._handle.close()

    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=2),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text())

    assert recovery["validation_status"] == "pass"
    assert len(summary["segment_summaries"]) == 5
    assert summary["segment_summaries"][0]["terminal_reason"] == "rotation"
    assert any(
        segment["recovery_status"] == "FINALIZED_BEFORE_MANIFEST_SYNC"
        for segment in summary["segment_summaries"]
    )


@pytest.mark.parametrize(
    "partial_successor_suffix",
    [None, "events.jsonl", "checkpoint.json", "summary.json"],
)
def test_runtime_recovers_finalized_rotation_without_complete_successor(
    tmp_path: Path,
    partial_successor_suffix: str | None,
) -> None:
    session = RuntimeEvidenceSession(
        output_dir=tmp_path,
        campaign_id="d2e-rotation-no-successor",
        mode="read_only_websocket_smoke",
        configured_duration_seconds=300,
        selected_market_metadata={"ticker": MARKET, "status": "active"},
        selected_market_selection={"selection_gate_result": "pass"},
        lifecycle_mode_and_source="selected_market_rest_fallback",
        pricing_mode_and_source="explicit",
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        started_at_utc=START,
    )
    session._writer.close(
        terminal_reason="rotation",
        rotation_reason=RotationReason.BYTE_LIMIT,
    )
    if partial_successor_suffix is not None:
        successor = (
            session.current_data_path.parent
            / f"d2e-rotation-no-successor.evidence.0002.{partial_successor_suffix}"
        )
        successor.touch()

    if partial_successor_suffix is not None:
        with pytest.raises(ValueError, match="partial successor"):
            recover_d2_runtime_artifacts(
                tmp_path,
                recovered_at_utc=START + timedelta(seconds=2),
            )
        return
    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=2),
    )
    summary = json.loads((tmp_path / "campaign_summary.json").read_text())

    assert recovery["validation_status"] == "pass"
    assert summary["segment_summaries"][0]["terminal_reason"] == "rotation"
    assert summary["segment_summaries"][0]["recovery_status"] == (
        "FINALIZED_BEFORE_MANIFEST_SYNC"
    )


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
        record
        for record in records
        if record["record_type"] == "raw_transport_event"
        and record["d2b_rebuild"]["frame"] is not None
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
        payload["rebuild_summaries"][0]["frame_hash_chain"] = "0" * 64
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
                row
                for row in rows
                if row["record_type"] == "raw_transport_event"
                and row["d2c_public_trades"]
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
    assert any("append-chain mismatch" in failure for failure in validation["failures"])


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
    use_yes_price: bool = False,
) -> RuntimeEvidenceSession:
    session = _session_without_connection(
        root,
        configured_duration_seconds=configured_duration_seconds,
        max_segment_bytes=max_segment_bytes,
        use_yes_price=use_yes_price,
    )
    tracker = KalshiWsIntegrityTracker(
        campaign_id="d2e-runtime-test",
        requested_market_tickers=(MARKET,),
    )
    tracker.start_connection()
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.CONNECTION_OPEN,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason="test_connection_open",
        )
    )
    tracker.bind_subscription(command_id=1)
    session.record_event(
        tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "msg": {"channels": ["orderbook_delta", "trade"]},
            },
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    session.record_connection_event(
        ConnectionEvidenceEvent(
            event_type=ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED,
            observed_at_utc=START,
            connection_id=tracker.connection_id,
            segment_id=tracker.segment_id,
            reason="test_subscription_acknowledged",
        )
    )
    return session


def _session_without_connection(
    root: Path,
    *,
    configured_duration_seconds: int,
    max_segment_bytes: int = 64 * 1024 * 1024,
    use_yes_price: bool = False,
) -> RuntimeEvidenceSession:
    return RuntimeEvidenceSession(
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
        use_yes_price=use_yes_price,
        checkpoint_every_records=2,
        max_segment_bytes=max_segment_bytes,
    )


def _tracker(
    *,
    markets: tuple[str, ...] = (MARKET,),
    continuity_policy: SequenceContinuityPolicy = SequenceContinuityPolicy.UNKNOWN,
    offset: bool = True,
):
    tracker = KalshiWsIntegrityTracker(
        campaign_id="d2e-runtime-test",
        requested_market_tickers=markets,
        continuity_policy=continuity_policy,
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1)
    return _OffsetTracker(tracker) if offset else tracker


class _OffsetTracker:
    def __init__(self, tracker: KalshiWsIntegrityTracker) -> None:
        self._tracker = tracker

    def __getattr__(self, name: str):
        return getattr(self._tracker, name)

    def record(self, payload, *, local_row_index: int, **kwargs):
        return self._tracker.record(
            payload,
            local_row_index=local_row_index + 1,
            **kwargs,
        )


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


@pytest.mark.parametrize(
    ("metadata_name", "target_name"),
    [
        ("campaign_summary.json", "run_metadata.json"),
        ("campaign_manifest.json", "run_metadata.json"),
        ("run_metadata.json", "campaign_summary.json"),
    ],
)
def test_validator_rejects_internal_fixed_metadata_symlink(
    tmp_path: Path,
    metadata_name: str,
    target_name: str,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    metadata_path = tmp_path / metadata_name
    metadata_path.unlink()
    metadata_path.symlink_to(tmp_path / target_name)

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any(metadata_name in failure for failure in validation["failures"])


def test_preflight_validator_rejects_symlinked_metadata(tmp_path: Path) -> None:
    ws_runtime.write_d2_runtime_preflight_block(
        output_dir=tmp_path,
        campaign_id="d2e-preflight-symlink",
        mode="read_only_websocket_smoke",
        configured_duration_seconds=300,
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        blocker_code="NO_WS_CREDENTIALS",
        started_at_utc=START,
    )
    manifest = tmp_path / "campaign_manifest.json"
    manifest.unlink()
    manifest.symlink_to(tmp_path / "run_metadata.json")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("campaign_manifest.json" in failure for failure in validation["failures"])


def test_monitor_does_not_read_internal_summary_symlink(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    summary = tmp_path / "campaign_summary.json"
    summary.unlink()
    summary.symlink_to(tmp_path / "run_metadata.json")

    snapshot = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=1))

    assert snapshot["campaign"].get("campaign_id") is None
    assert any("campaign_summary.json" in warning for warning in snapshot["run_info"]["warnings"])


def test_runtime_recovery_is_retry_safe_after_later_validation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session._writer._handle.close()
    original_validate = ws_runtime.validate_d2_runtime_artifacts
    failed = False

    def fail_after_summary_sync(path: Path) -> dict[str, object]:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("synthetic post-sync validation crash")
        return original_validate(path)

    with monkeypatch.context() as scoped:
        scoped.setattr(ws_runtime, "validate_d2_runtime_artifacts", fail_after_summary_sync)
        with pytest.raises(RuntimeError, match="post-sync validation crash"):
            recover_d2_runtime_artifacts(
                tmp_path,
                recovered_at_utc=START + timedelta(seconds=10),
            )

    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=20),
    )

    assert recovery["validation_status"] == "pass"


def test_runtime_recovery_rejects_tampered_existing_segment_start_timestamp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41},
            local_row_index=1,
            received_at_utc=START,
            received_monotonic_ns=1,
        )
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(
            session,
            "_verify_closed_segments",
            lambda: (_ for _ in ()).throw(RuntimeError("synthetic post-close crash")),
        )
        with pytest.raises(RuntimeError, match="post-close crash"):
            session.close(
                ended_at_utc=START + timedelta(seconds=1),
                terminal_reason="bounded_duration_complete",
                stop_requested=False,
                connection_established=True,
                subscription_acknowledged=True,
                blocker_code=None,
            )
    start_path = tmp_path / "evidence_segments" / "d2e-runtime-test.recovery.next.start.json"
    start_path.write_text(
        json.dumps(
            {
                "schema_version": ws_runtime.EVIDENCE_SEGMENT_START_SCHEMA_VERSION,
                "segment_id": "d2e-runtime-test.recovery.next",
                "previous_segment_id": "d2e-runtime-test.evidence.0001",
                "segment_created": True,
                "connection_reset_required": True,
                "snapshot_required": True,
                "inherited_book_state": False,
                "created_at_utc": (START + timedelta(hours=1)).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="recovery metadata already exists"):
        recover_d2_runtime_artifacts(
            tmp_path,
            recovered_at_utc=START + timedelta(seconds=2),
        )


def test_validator_rejects_non_object_campaign_summary(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    (tmp_path / "campaign_summary.json").write_text("[]\n", encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any(
        "campaign_summary must be a JSON object" in failure
        for failure in validation["failures"]
    )


@pytest.mark.parametrize("field", ["replay_qualified", "real_money_trading"])
def test_validator_rejects_tampered_top_level_safety_fields(
    tmp_path: Path,
    field: str,
) -> None:
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
        payload[field] = True
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any(field in failure for failure in validation["failures"])


def test_validator_rejects_tampered_integrity_and_overall_classification(
    tmp_path: Path,
) -> None:
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
        payload["artifact_integrity_summary"]["closed_file_hash_verified"] = False
        payload["overall_evidence_classification"] = "TAMPERED"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("artifact integrity summary" in failure for failure in validation["failures"])
    assert any("overall evidence classification" in failure for failure in validation["failures"])


def test_validator_rejects_top_level_private_account_field(tmp_path: Path) -> None:
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
        payload["account_id"] = "private"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert any("private account/order data" in failure for failure in validation["failures"])


def test_atomic_runtime_json_writer_rejects_temporary_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("unchanged\n", encoding="utf-8")
    temporary = tmp_path / ".artifact.json.tmp"
    temporary.symlink_to(outside)

    with pytest.raises(FileExistsError):
        ws_runtime._atomic_write_json(tmp_path / "artifact.json", {"status": "safe"})

    assert outside.read_text(encoding="utf-8") == "unchanged\n"


def test_validator_rejects_non_object_preflight_validation(tmp_path: Path) -> None:
    ws_runtime.write_d2_runtime_preflight_block(
        output_dir=tmp_path,
        campaign_id="d2e-non-object-validation",
        mode="read_only_websocket_smoke",
        configured_duration_seconds=300,
        provenance=RuntimeCodeProvenance(COMMIT, "main", "https://example.test/repo", False),
        blocker_code="NO_WS_CREDENTIALS",
        started_at_utc=START,
    )
    (tmp_path / "campaign_validation.json").write_text("[]\n", encoding="utf-8")

    validation = validate_d2_runtime_artifacts(tmp_path)

    assert validation["status"] == "fail"
    assert validation["strict_verdict"] == "STRICT NO-GO"
    assert any(
        "campaign_validation must be a JSON object" in failure
        for failure in validation["failures"]
    )


def test_monitor_rejects_external_jsonl_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-external.jsonl"
    outside.write_text(
        '{"record_type":"candidate","candidate_id":"external"}\n',
        encoding="utf-8",
    )
    (tmp_path / "external.jsonl").symlink_to(outside)

    snapshot = build_monitor_snapshot(tmp_path, now=START)

    assert any("external.jsonl" in warning for warning in snapshot["run_info"]["warnings"])
    assert all(
        item.get("candidate_id") != "external"
        for item in snapshot["candidates"]
        if isinstance(item, dict)
    )


def test_public_ws_entrypoint_wires_unified_yes_price_mode(
    tmp_path: Path,
    monkeypatch,
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
                    "use_yes_price": True,
                },
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
        assert kwargs["use_yes_price"] is True
        return real_runtime(
            **kwargs,
            websocket_factory=lambda *_args, **_kwargs: websocket,
            lifecycle_provider=lambda ticker: {"ticker": ticker, "status": "active"},
            now=fake_time.now,
            monotonic=fake_time.monotonic,
            monotonic_ns=fake_time.monotonic_ns,
        )

    monkeypatch.setattr(v2_readonly_campaign, "run_d2_kalshi_ws_runtime", mocked_runtime)
    summary = v2_readonly_campaign.run_kalshi_ws_smoke(
        output_dir=tmp_path / "run",
        campaign_id="d2e-public-unified-price",
        duration_seconds=300,
        max_markets=1,
        use_yes_price=True,
    )

    assert summary["use_yes_price"] is True
    assert summary["pricing_mode_and_source"] == "explicit_subscription_use_yes_price_true"
    assert summary["rebuild_summaries"][0]["pricing_modes"] == ["UNIFIED_YES_PRICE"]


def test_monitor_revalidates_d2_artifacts_without_trusting_stale_report(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    summary = session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    validation_path = tmp_path / "campaign_validation.json"
    validation_before = validation_path.read_bytes()
    data_path = tmp_path / summary["segment_summaries"][0]["data_path"]
    data_path.write_bytes(data_path.read_bytes() + b'{"tampered":true}\n')

    snapshot = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=1))

    assert snapshot["campaign"]["status"] == "D2_RUNTIME_VALIDATION_FAILED"
    assert snapshot["campaign"]["validation_status"] == "fail"
    assert snapshot["run_info"]["health"] == "BLOCKED"
    assert validation_path.read_bytes() == validation_before


def test_validator_rejects_tampered_segment_durability_metadata(tmp_path: Path) -> None:
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
    segment_baseline = json.loads(segment_summary_path.read_text(encoding="utf-8"))
    fixed_names = ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json")
    fixed_baselines = {
        name: json.loads((tmp_path / name).read_text(encoding="utf-8")) for name in fixed_names
    }
    mutations = {
        "genesis_hash": "0" * 64,
        "segment_closed": False,
        "backup_verification_state": "VERIFIED",
        "retention_deletion_eligible": True,
    }

    for field, value in mutations.items():
        segment_tampered = {**segment_baseline, field: value}
        segment_summary_path.write_text(
            json.dumps(segment_tampered) + "\n",
            encoding="utf-8",
        )
        for name, baseline in fixed_baselines.items():
            fixed_tampered = json.loads(json.dumps(baseline))
            fixed_tampered["segment_summaries"][0][field] = value
            (tmp_path / name).write_text(
                json.dumps(fixed_tampered) + "\n",
                encoding="utf-8",
            )

        validation = validate_d2_runtime_artifacts(tmp_path)

        assert validation["status"] == "fail", field
        assert any(field in failure for failure in validation["failures"]), field

        segment_summary_path.write_text(
            json.dumps(segment_baseline) + "\n",
            encoding="utf-8",
        )
        for name, baseline in fixed_baselines.items():
            (tmp_path / name).write_text(
                json.dumps(baseline) + "\n",
                encoding="utf-8",
            )

    assert validate_d2_runtime_artifacts(tmp_path)["status"] == "pass"


def test_runtime_recovery_rejects_in_root_segment_symlink_before_mutation(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session._writer._handle.close()
    summary_path = tmp_path / "campaign_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    real_data_path = tmp_path / summary["segment_summaries"][-1]["data_path"]
    decoy_path = real_data_path.with_name("decoy.events.jsonl")
    decoy_path.write_bytes(real_data_path.read_bytes() + b"partial-tail")
    alias_path = real_data_path.with_name("alias.events.jsonl")
    alias_path.symlink_to(decoy_path)
    summary["segment_summaries"][-1]["data_path"] = str(alias_path.relative_to(tmp_path))
    summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    decoy_before = decoy_path.read_bytes()

    with pytest.raises(ValueError, match="must not be a symlink"):
        recover_d2_runtime_artifacts(tmp_path, recovered_at_utc=START + timedelta(seconds=1))

    assert decoy_path.read_bytes() == decoy_before
    assert not (tmp_path / "runtime_recovery.json").exists()


def test_validator_rejects_tampered_recovery_tail_size_metadata(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session.record_event(
        _tracker().record(
            {"type": "heartbeat", "sid": 41, "seq": 1},
            local_row_index=1,
            received_at_utc=START + timedelta(seconds=1),
            received_monotonic_ns=1,
        )
    )
    session._writer._handle.close()
    with session.current_data_path.open("ab") as handle:
        handle.write(b'{"local_row_index":2')
    recovery = recover_d2_runtime_artifacts(
        tmp_path,
        recovered_at_utc=START + timedelta(seconds=10),
    )
    assert recovery["validation_status"] == "pass"
    recovery_path = tmp_path / "runtime_recovery.json"
    recovery_baseline = json.loads(recovery_path.read_text(encoding="utf-8"))
    summary_baselines = {
        name: json.loads((tmp_path / name).read_text(encoding="utf-8"))
        for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json")
    }
    recovered_segment = next(
        segment
        for segment in summary_baselines["campaign_summary.json"]["segment_summaries"]
        if segment.get("recovery_status") == "CRASH_RECOVERED"
    )
    segment_path = tmp_path / recovered_segment["summary_path"]
    segment_baseline = json.loads(segment_path.read_text(encoding="utf-8"))

    for value in (-1, 1_000_000):
        tampered_recovery = {**recovery_baseline, "partial_tail_bytes_removed": value}
        recovery_path.write_text(json.dumps(tampered_recovery) + "\n", encoding="utf-8")
        segment_tampered = {**segment_baseline, "partial_tail_bytes_removed": value}
        segment_path.write_text(json.dumps(segment_tampered) + "\n", encoding="utf-8")
        for name, baseline in summary_baselines.items():
            fixed_tampered = json.loads(json.dumps(baseline))
            recovered = next(
                item
                for item in fixed_tampered["segment_summaries"]
                if item.get("recovery_status") == "CRASH_RECOVERED"
            )
            recovered["partial_tail_bytes_removed"] = value
            (tmp_path / name).write_text(
                json.dumps(fixed_tampered) + "\n",
                encoding="utf-8",
            )

        validation = validate_d2_runtime_artifacts(tmp_path)

        assert validation["status"] == "fail"
        assert any("partial" in failure for failure in validation["failures"])

        recovery_path.write_text(json.dumps(recovery_baseline) + "\n", encoding="utf-8")
        segment_path.write_text(json.dumps(segment_baseline) + "\n", encoding="utf-8")
        for name, baseline in summary_baselines.items():
            (tmp_path / name).write_text(json.dumps(baseline) + "\n", encoding="utf-8")


def test_runtime_recovery_preflights_all_manifest_segment_paths(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=300)
    session._writer._handle.close()
    summary_path = tmp_path / "campaign_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    current_data_path = tmp_path / summary["segment_summaries"][-1]["data_path"]
    alias_path = current_data_path.with_name("other-segment.events.jsonl")
    alias_path.symlink_to(current_data_path)
    summary["segment_summaries"].append(
        {
            "segment_id": "other-segment.evidence.0001",
            "segment_closed": True,
            "data_path": str(alias_path.relative_to(tmp_path)),
            "checkpoint_path": summary["segment_summaries"][-1]["checkpoint_path"],
            "summary_path": summary["segment_summaries"][-1]["checkpoint_path"],
        }
    )
    summary_path.write_text(json.dumps(summary) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not be a symlink"):
        recover_d2_runtime_artifacts(tmp_path, recovered_at_utc=START + timedelta(seconds=1))

    assert not (tmp_path / "runtime_recovery.json").exists()


def test_monitor_fails_closed_when_campaign_summary_is_unsafe(tmp_path: Path) -> None:
    session = _session(tmp_path, configured_duration_seconds=1)
    session.close(
        ended_at_utc=START + timedelta(seconds=1),
        terminal_reason="bounded_duration_complete",
        stop_requested=False,
        connection_established=True,
        subscription_acknowledged=True,
        blocker_code=None,
    )
    outside = tmp_path.parent / f"{tmp_path.name}-campaign-summary.json"
    outside.write_text("{}\n", encoding="utf-8")
    campaign_summary = tmp_path / "campaign_summary.json"
    campaign_summary.unlink()
    campaign_summary.symlink_to(outside)

    snapshot = build_monitor_snapshot(tmp_path, now=START + timedelta(seconds=1))

    assert snapshot["run_info"]["health"] == "BLOCKED"
    assert snapshot["validation"]["status"] == "fail"
    assert any(
        "campaign_summary.json" in warning for warning in snapshot["run_info"]["warnings"]
    )
