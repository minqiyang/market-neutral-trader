from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from edmn_trader.scripts import phase0f_activity_measurement as phase0f_module
from edmn_trader.scripts.phase0f_activity_measurement import (
    PHASE0F_DISCOVERY_REQUEST_LIMIT,
    PHASE0F_MEASUREMENT_SECONDS,
    Phase0FNetworkClassification,
    Phase0FNetworkResult,
    _probe_allows_candidate_fallback,
    assess_phase0f_runtime,
    main,
    run_phase0f_activity_measurement,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def test_phase0f_cli_sanitizes_unexpected_failures(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    def fail_closed(**_kwargs: object) -> Phase0FNetworkResult:
        raise RuntimeError("SECRET-TICKER /private/evidence/path count=99")

    monkeypatch.setattr(
        phase0f_module,
        "run_phase0f_activity_measurement",
        fail_closed,
    )

    assert (
        main(
            [
                "--output-root",
                str(tmp_path / "private-root"),
                "--demo-readonly-opt-in",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert output.err == ""
    assert "PHASE0F_CONTROLLER_BLOCKED" in output.out
    assert "SECRET-TICKER" not in output.out
    assert "/private/evidence/path" not in output.out
    assert "count" not in output.out.lower()


def test_phase0f_public_status_contains_no_correlatable_detail() -> None:
    record = Phase0FNetworkResult(
        classification=Phase0FNetworkClassification.DELTA_MEASUREMENT_CAPTURED,
        activity_aware_candidate_qualified=True,
        bounded_probe_passed=True,
        measurement_started=True,
        measurement_qualified=True,
        delta_admitted=True,
        replay_semantics_supported=False,
    ).to_public_record()

    serialized = json.dumps(record, sort_keys=True).lower()
    assert all(
        forbidden not in serialized
        for forbidden in (
            "ticker",
            "campaign_id",
            "segment_id",
            "path",
            "count",
            "timestamp",
            "hash",
            "sequence",
            "sid",
        )
    )


def test_phase0f_output_root_must_remain_outside_git(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)

    try:
        run_phase0f_activity_measurement(
            output_root=repository / "private-data",
            demo_readonly_opt_in=True,
            auth_preflight=lambda: None,
            discovery=lambda **_kwargs: {},
            probe_runner=lambda **_kwargs: {},
            measurement_runner=lambda **_kwargs: {},
            runtime_assessor=lambda *_args, **_kwargs: {},
        )
    except ValueError as exc:
        assert "outside Git" in str(exc)
    else:
        raise AssertionError("Phase 0F output inside Git must fail closed")


def test_phase0f_runtime_assessment_accepts_closed_delta_with_unknown_safe_sequence(
    tmp_path: Path,
) -> None:
    summary = {
        "configured_duration_seconds": 300,
        "actual_elapsed_seconds": "300",
        "terminal_reason": "bounded_duration_complete",
        "stop_requested": False,
        "connection_established": True,
        "subscription_acknowledged": True,
        "admitted_selected_snapshot_count": 1,
        "admitted_selected_delta_count": 1,
        "sequence_summaries": [
            {"aggregate_result": "SEQUENCE_INTEGRITY_UNKNOWN"}
        ],
        "rebuild_summaries": [
            {
                "orderbook_row_count": 2,
                "frame_count": 2,
                "snapshot_first_admitted": True,
                "native_state_valid": True,
                "invalidation_reasons": {},
            }
        ],
        "segment_summaries": [{"segment_closed": True}],
        "live_gate_status": "disabled",
        "production_trading_enabled": False,
        "executable_order_intent": False,
        "production_endpoint_used": False,
        "submit_attempts": 0,
    }
    (tmp_path / "campaign_summary.json").write_text(json.dumps(summary))
    validation = {
        "status": "pass",
        "artifact_integrity": "PASS",
        "transport_connectivity": "PASS",
        "subscription_status": "PASS",
        "market_lifecycle_validity": "PASS",
        "duration_evidence": "PASS",
        "sequence_integrity": "UNKNOWN",
        "rebuild_integrity": "PASS",
    }

    result = assess_phase0f_runtime(
        tmp_path,
        required_duration_seconds=300,
        phase="probe",
        validator=lambda _root: validation,
    )

    assert result["qualified"] is True
    assert result["snapshot_admitted"] is True
    assert result["delta_admitted"] is True
    assert result["sequence_integrity"] == "UNKNOWN"
    assert result["rebuild_integrity"] == "PASS"
    assert result["source_closed"] is True


def test_phase0f_distinguishes_discovery_failure_from_no_candidate(
    tmp_path: Path,
) -> None:
    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        auth_preflight=lambda: None,
        discovery=lambda **_kwargs: {
            "blocker_code": "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR",
            "eligible_candidates": [],
            "diagnostics": {},
        },
        probe_runner=lambda **_kwargs: {},
        measurement_runner=lambda **_kwargs: {},
        runtime_assessor=lambda *_args, **_kwargs: {},
    )

    assert result.classification is Phase0FNetworkClassification.ACTIVITY_DISCOVERY_BLOCKED
    assert result.activity_aware_candidate_qualified is False
    assert result.measurement_started is False


def test_phase0f_stops_before_probe_when_activity_discovery_has_no_candidate(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def discovery(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "blocker_code": "DEMO_NO_ELIGIBLE_MARKET",
            "eligible_candidates": [],
            "diagnostics": {},
        }

    def forbidden_runner(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("no runtime may start without an eligible candidate")

    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        now=NOW,
        auth_preflight=lambda: None,
        discovery=discovery,
        probe_runner=forbidden_runner,
        measurement_runner=forbidden_runner,
        runtime_assessor=lambda *_args, **_kwargs: {},
    )

    assert (
        result.classification
        is Phase0FNetworkClassification.NO_ACTIVITY_AWARE_ELIGIBLE_CANDIDATE
    )
    assert result.activity_aware_candidate_qualified is False
    assert result.bounded_probe_passed is False
    assert result.measurement_started is False
    assert captured["duration_seconds"] == PHASE0F_MEASUREMENT_SECONDS
    assert captured["require_recent_activity"] is True
    assert captured["max_request_attempts"] == 1
    assert captured["request_budget"].limit == PHASE0F_DISCOVERY_REQUEST_LIMIT


def test_phase0f_fails_closed_on_malformed_ranked_candidate_identity(
    tmp_path: Path,
) -> None:
    def forbidden_runner(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("malformed ranked identity must stop before probing")

    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        auth_preflight=lambda: None,
        discovery=lambda **_kwargs: {
            "blocker_code": None,
            "eligible_candidates": [
                {"market_metadata": {"ticker": "SYNTHETIC-MALFORMED"}},
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC-VALID",
                        "event_ticker": "SYNTHETIC-EVENT",
                    }
                },
            ],
        },
        probe_runner=forbidden_runner,
        measurement_runner=forbidden_runner,
        runtime_assessor=lambda *_args, **_kwargs: {},
    )

    assert result.classification is Phase0FNetworkClassification.ACTIVITY_DISCOVERY_BLOCKED
    assert result.activity_aware_candidate_qualified is False
    assert result.bounded_probe_passed is False
    assert result.measurement_started is False


@pytest.mark.parametrize(
    "market_metadata",
    (
        {"ticker": " SYNTHETIC-MARKET", "event_ticker": "SYNTHETIC-EVENT"},
        {"ticker": "SYNTHETIC-MARKET ", "event_ticker": "SYNTHETIC-EVENT"},
        {"ticker": "SYNTHETIC-MARKET", "event_ticker": "\tSYNTHETIC-EVENT"},
        {"ticker": "SYNTHETIC-MARKET", "event_ticker": "SYNTHETIC-EVENT\n"},
        {"ticker": "SYNTHETIC-MARKET\u2003", "event_ticker": "SYNTHETIC-EVENT"},
        {"ticker": "SYNTHETIC-MARKET\u200b", "event_ticker": "SYNTHETIC-EVENT"},
        {"ticker": "SYNTHETIC-MARKET", "event_ticker": "\ufeffSYNTHETIC-EVENT"},
        {
            "ticker": "SYNTHETIC-MARKET",
            "market_ticker": "SYNTHETIC-OTHER-MARKET",
            "event_ticker": "SYNTHETIC-EVENT",
        },
    ),
)
def test_phase0f_fails_before_probe_on_noncanonical_candidate_identity(
    tmp_path: Path,
    market_metadata: dict[str, object],
) -> None:
    def forbidden_runner(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("noncanonical candidate must not reach a runtime")

    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        auth_preflight=lambda: None,
        discovery=lambda **_kwargs: {
            "blocker_code": None,
            "eligible_candidates": [{"market_metadata": market_metadata}],
        },
        probe_runner=forbidden_runner,
        measurement_runner=forbidden_runner,
        runtime_assessor=lambda *_args, **_kwargs: {},
    )

    assert result.classification is Phase0FNetworkClassification.ACTIVITY_DISCOVERY_BLOCKED
    assert result.bounded_probe_passed is False
    assert result.measurement_started is False


def test_phase0f_first_qualifying_probe_starts_one_same_candidate_measurement(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    assessments: dict[Path, dict[str, object]] = {}
    shared_budget: object | None = None

    def discovery(**kwargs: object) -> dict[str, object]:
        nonlocal shared_budget
        shared_budget = kwargs["request_budget"]
        return {
            "blocker_code": None,
            "eligible_candidates": [
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC-A",
                        "event_ticker": "SYNTHETIC-EVENT-A",
                    },
                    "selection": {"selection_gate_result": "pass"},
                },
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC-B",
                        "event_ticker": "SYNTHETIC-EVENT-B",
                    },
                    "selection": {"selection_gate_result": "pass"},
                },
            ],
            "diagnostics": {},
        }

    def probe_runner(**kwargs: object) -> dict[str, object]:
        calls.append(("probe", kwargs))
        root = Path(kwargs["output_dir"])
        root.mkdir()
        assessments[root] = {
            "qualified": True,
            "delta_admitted": True,
            "sequence_integrity": "UNKNOWN",
            "rebuild_integrity": "PASS",
        }
        return {"validation_status": "pass"}

    def measurement_runner(**kwargs: object) -> dict[str, object]:
        calls.append(("measurement", kwargs))
        root = Path(kwargs["output_dir"])
        root.mkdir()
        assessments[root] = {
            "qualified": True,
            "delta_admitted": True,
            "sequence_integrity": "UNKNOWN",
            "rebuild_integrity": "PASS",
        }
        return {"validation_status": "pass"}

    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        now=NOW,
        auth_preflight=lambda: None,
        discovery=discovery,
        probe_runner=probe_runner,
        measurement_runner=measurement_runner,
        runtime_assessor=lambda root, **_kwargs: assessments[Path(root)],
    )

    assert result.classification is Phase0FNetworkClassification.DELTA_MEASUREMENT_CAPTURED
    assert result.activity_aware_candidate_qualified is True
    assert result.bounded_probe_passed is True
    assert result.measurement_started is True
    assert result.measurement_qualified is True
    assert result.delta_admitted is True
    assert result.replay_semantics_supported is False
    assert [kind for kind, _kwargs in calls] == ["probe", "measurement"]
    probe = calls[0][1]
    measurement = calls[1][1]
    assert probe["pinned_market_ticker"] == measurement["pinned_market_ticker"]
    assert probe["expected_event_ticker"] == measurement["expected_event_ticker"]
    assert probe["duration_seconds"] == 300
    assert measurement["duration_seconds"] == PHASE0F_MEASUREMENT_SECONDS
    for invocation in (probe, measurement):
        assert invocation["selection_duration_seconds"] == PHASE0F_MEASUREMENT_SECONDS
        assert invocation["require_recent_activity"] is True
        assert invocation["max_request_attempts"] == 1
        assert invocation["request_budget"] is shared_budget


def test_phase0f_never_advances_after_an_unqualified_delta() -> None:
    assert (
        _probe_allows_candidate_fallback(
            {
                "qualified": False,
                "controlled_exit": True,
                "duration_gate": True,
                "transport_gate": True,
                "subscription_gate": True,
                "snapshot_admitted": True,
                "delta_admitted": True,
                "lifecycle_valid": True,
                "sequence_integrity": "UNKNOWN",
                "rebuild_integrity": "PASS",
                "artifact_integrity": True,
                "source_closed": True,
                "safety_gate": True,
            }
        )
        is False
    )


def test_phase0f_stops_after_global_probe_preflight_failure(
    tmp_path: Path,
) -> None:
    probe_calls = 0

    def discovery(**_kwargs: object) -> dict[str, object]:
        return {
            "eligible_candidates": [
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC-A",
                        "event_ticker": "SYNTHETIC-EVENT-A",
                    }
                },
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC-B",
                        "event_ticker": "SYNTHETIC-EVENT-B",
                    }
                },
            ]
        }

    def probe_runner(**_kwargs: object) -> dict[str, object]:
        nonlocal probe_calls
        probe_calls += 1
        return {"blocker_code": "DEMO_MARKET_DISCOVERY_INCOMPLETE_HTTP_ERROR"}

    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        auth_preflight=lambda: None,
        discovery=discovery,
        probe_runner=probe_runner,
        measurement_runner=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("measurement must remain blocked")
        ),
        runtime_assessor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("blocked preflight has no qualifying runtime")
        ),
    )

    assert result.classification is Phase0FNetworkClassification.PROBE_BLOCKED
    assert probe_calls == 1
    assert result.bounded_probe_passed is False
    assert result.measurement_started is False


def test_phase0f_stops_when_pinned_measurement_revalidation_blocks(
    tmp_path: Path,
) -> None:
    probe_root: Path | None = None

    def discovery(**_kwargs: object) -> dict[str, object]:
        return {
            "eligible_candidates": [
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC-A",
                        "event_ticker": "SYNTHETIC-EVENT-A",
                    }
                }
            ]
        }

    def probe_runner(**kwargs: object) -> dict[str, object]:
        nonlocal probe_root
        probe_root = Path(kwargs["output_dir"])
        probe_root.mkdir()
        return {}

    def assessor(root: Path, **_kwargs: object) -> dict[str, object]:
        if Path(root) != probe_root:
            raise AssertionError("blocked measurement must not be assessed as a runtime")
        return {"qualified": True}

    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        auth_preflight=lambda: None,
        discovery=discovery,
        probe_runner=probe_runner,
        measurement_runner=lambda **_kwargs: {
            "blocker_code": "DEMO_PINNED_MARKET_REVALIDATION_REJECTED"
        },
        runtime_assessor=assessor,
    )

    assert result.classification is Phase0FNetworkClassification.MEASUREMENT_BLOCKED
    assert result.bounded_probe_passed is True
    assert result.measurement_started is False
    assert result.measurement_qualified is False


def test_phase0f_classifies_snapshot_only_measurement_without_replay(
    tmp_path: Path,
) -> None:
    assessments: dict[Path, dict[str, object]] = {}

    def discovery(**_kwargs: object) -> dict[str, object]:
        return {
            "eligible_candidates": [
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC",
                        "event_ticker": "SYNTHETIC-EVENT",
                    }
                }
            ]
        }

    def probe_runner(**kwargs: object) -> dict[str, object]:
        root = Path(kwargs["output_dir"])
        root.mkdir()
        assessments[root] = {"qualified": True}
        return {}

    def measurement_runner(**kwargs: object) -> dict[str, object]:
        root = Path(kwargs["output_dir"])
        root.mkdir()
        assessments[root] = {
            "qualified": False,
            "snapshot_admitted": True,
            "delta_admitted": False,
            "sequence_integrity": "UNKNOWN",
            "rebuild_integrity": "PASS",
        }
        return {}

    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        auth_preflight=lambda: None,
        discovery=discovery,
        probe_runner=probe_runner,
        measurement_runner=measurement_runner,
        runtime_assessor=lambda root, **_kwargs: assessments[Path(root)],
    )

    assert result.classification is Phase0FNetworkClassification.MEASUREMENT_SNAPSHOT_ONLY
    assert result.measurement_started is True
    assert result.measurement_qualified is False
    assert result.delta_admitted is False
    assert result.replay_semantics_supported is False


def test_phase0f_uses_second_probe_only_after_first_fails(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str]] = []
    assessments: dict[Path, dict[str, object]] = {}

    def discovery(**_kwargs: object) -> dict[str, object]:
        return {
            "blocker_code": None,
            "eligible_candidates": [
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC-A",
                        "event_ticker": "SYNTHETIC-EVENT-A",
                    }
                },
                {
                    "market_metadata": {
                        "ticker": "SYNTHETIC-B",
                        "event_ticker": "SYNTHETIC-EVENT-B",
                    }
                },
            ],
            "diagnostics": {},
        }

    def probe_runner(**kwargs: object) -> dict[str, object]:
        ticker = str(kwargs["pinned_market_ticker"])
        calls.append(("probe", ticker))
        root = Path(kwargs["output_dir"])
        root.mkdir()
        assessments[root] = {
            "qualified": ticker == "SYNTHETIC-B",
            "controlled_exit": True,
            "duration_gate": True,
            "transport_gate": True,
            "subscription_gate": True,
            "snapshot_admitted": True,
            "delta_admitted": ticker == "SYNTHETIC-B",
            "lifecycle_valid": True,
            "sequence_integrity": "UNKNOWN",
            "rebuild_integrity": "PASS",
            "artifact_integrity": True,
            "source_closed": True,
            "safety_gate": True,
        }
        return {}

    def measurement_runner(**kwargs: object) -> dict[str, object]:
        ticker = str(kwargs["pinned_market_ticker"])
        calls.append(("measurement", ticker))
        root = Path(kwargs["output_dir"])
        root.mkdir()
        assessments[root] = {
            "qualified": True,
            "delta_admitted": True,
            "sequence_integrity": "UNKNOWN",
            "rebuild_integrity": "PASS",
        }
        return {}

    result = run_phase0f_activity_measurement(
        output_root=tmp_path / "phase0f",
        demo_readonly_opt_in=True,
        auth_preflight=lambda: None,
        discovery=discovery,
        probe_runner=probe_runner,
        measurement_runner=measurement_runner,
        runtime_assessor=lambda root, **_kwargs: assessments[Path(root)],
    )

    assert result.bounded_probe_passed is True
    assert calls == [
        ("probe", "SYNTHETIC-A"),
        ("probe", "SYNTHETIC-B"),
        ("measurement", "SYNTHETIC-B"),
    ]
