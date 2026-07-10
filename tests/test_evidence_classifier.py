from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from edmn_trader.data.evidence_classifier import (
    EvidenceDimensions,
    EvidenceStatus,
    OverallEvidenceClassification,
    build_evidence_timing,
    classify_duration_evidence,
    classify_evidence,
)

START = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def test_all_orthogonal_dimensions_must_pass_for_overall_pass() -> None:
    result = classify_evidence(_dimensions(EvidenceStatus.PASS))

    assert result.overall_classification is OverallEvidenceClassification.PASS
    assert set(result.to_record()["dimensions"]) == {
        "artifact_integrity",
        "transport_connectivity",
        "transport_keepalive",
        "subscription_status",
        "sequence_integrity",
        "rebuild_integrity",
        "market_lifecycle_validity",
        "duration_evidence",
        "process_liveness",
        "supervisor_liveness",
        "backup_integrity",
        "replay_qualification",
    }


def test_unknown_critical_dimension_cannot_produce_overall_pass() -> None:
    dimensions = replace(
        _dimensions(EvidenceStatus.PASS),
        sequence_integrity=EvidenceStatus.UNKNOWN,
    )

    result = classify_evidence(dimensions)

    assert result.overall_classification is OverallEvidenceClassification.INCOMPLETE
    assert result.dimensions.sequence_integrity is EvidenceStatus.UNKNOWN

    with pytest.raises(ValueError, match="overall classification"):
        replace(result, overall_classification=OverallEvidenceClassification.PASS)


def test_failed_dimension_produces_overall_fail_without_hiding_other_unknowns() -> None:
    dimensions = replace(
        _dimensions(EvidenceStatus.PASS),
        artifact_integrity=EvidenceStatus.FAIL,
        replay_qualification=EvidenceStatus.UNKNOWN,
    )

    result = classify_evidence(dimensions)
    record = result.to_record()

    assert result.overall_classification is OverallEvidenceClassification.FAIL
    assert record["dimensions"]["artifact_integrity"] == EvidenceStatus.FAIL
    assert record["dimensions"]["replay_qualification"] == EvidenceStatus.UNKNOWN


def test_snapshot_transport_pass_does_not_promote_other_dimensions() -> None:
    dimensions = _dimensions(EvidenceStatus.UNKNOWN)
    dimensions = replace(
        dimensions,
        artifact_integrity=EvidenceStatus.PASS,
        transport_connectivity=EvidenceStatus.PASS,
        subscription_status=EvidenceStatus.PASS,
    )

    result = classify_evidence(dimensions)

    assert result.overall_classification is OverallEvidenceClassification.INCOMPLETE
    assert result.dimensions.sequence_integrity is EvidenceStatus.UNKNOWN
    assert result.dimensions.rebuild_integrity is EvidenceStatus.UNKNOWN
    assert result.dimensions.duration_evidence is EvidenceStatus.UNKNOWN
    assert result.dimensions.replay_qualification is EvidenceStatus.UNKNOWN


def test_duration_uses_actual_timestamps_not_configured_duration() -> None:
    timing = build_evidence_timing(
        configured_duration_seconds=86_400,
        started_at_utc=START,
        checkpoint_at_utc=None,
        ended_at_utc=START + timedelta(hours=1),
        first_snapshot_at=START + timedelta(seconds=2),
        last_event_at=START + timedelta(minutes=59),
        terminal_reason="remote_close",
        stop_requested=False,
        total_disconnect_seconds=Decimal("10.25"),
        threshold_policy_version="edmn.v2.thresholds.v1",
        threshold_source_commit="0123456789abcdef",
        threshold_effective_utc=START,
    )

    assert timing.actual_elapsed_seconds == Decimal("3600")
    assert timing.connected_elapsed_seconds == Decimal("3589.75")
    assert classify_duration_evidence(timing) is EvidenceStatus.FAIL

    with pytest.raises(ValueError, match="actual elapsed"):
        replace(timing, actual_elapsed_seconds=Decimal("86400"))


def test_completed_actual_duration_can_pass() -> None:
    timing = build_evidence_timing(
        configured_duration_seconds=3_600,
        started_at_utc=START,
        checkpoint_at_utc=None,
        ended_at_utc=START + timedelta(hours=1),
        first_snapshot_at=START,
        last_event_at=START + timedelta(hours=1),
        terminal_reason="configured_duration_reached",
        stop_requested=False,
        total_disconnect_seconds=Decimal("0"),
        threshold_policy_version="edmn.v2.thresholds.v1",
        threshold_source_commit="0123456789abcdef",
        threshold_effective_utc=START,
    )

    assert classify_duration_evidence(timing) is EvidenceStatus.PASS


def test_in_progress_short_checkpoint_is_unknown_not_failed() -> None:
    timing = build_evidence_timing(
        configured_duration_seconds=3_600,
        started_at_utc=START,
        checkpoint_at_utc=START + timedelta(minutes=5),
        ended_at_utc=None,
        first_snapshot_at=START,
        last_event_at=START + timedelta(minutes=4),
        terminal_reason=None,
        stop_requested=False,
        total_disconnect_seconds=Decimal("0"),
        threshold_policy_version="edmn.v2.thresholds.v1",
        threshold_source_commit="0123456789abcdef",
        threshold_effective_utc=START,
    )

    assert timing.actual_elapsed_seconds == Decimal("300")
    assert classify_duration_evidence(timing) is EvidenceStatus.UNKNOWN


def test_open_timing_rejects_terminal_reason_and_impossible_event_chronology() -> None:
    timing = build_evidence_timing(
        configured_duration_seconds=3_600,
        started_at_utc=START,
        checkpoint_at_utc=START + timedelta(minutes=5),
        ended_at_utc=None,
        first_snapshot_at=START + timedelta(minutes=1),
        last_event_at=START + timedelta(minutes=4),
        terminal_reason=None,
        stop_requested=False,
        total_disconnect_seconds=Decimal("0"),
        threshold_policy_version="edmn.v2.thresholds.v1",
        threshold_source_commit="0123456789abcdef",
        threshold_effective_utc=START,
    )

    with pytest.raises(ValueError, match="terminal_reason"):
        replace(timing, terminal_reason="remote_close")
    with pytest.raises(ValueError, match="first_snapshot_at"):
        replace(timing, last_event_at=START + timedelta(seconds=30))
    with pytest.raises(ValueError, match="first_snapshot_at"):
        replace(timing, last_event_at=None)


def test_checkpoint_cannot_predate_evidence_start_even_when_run_has_ended() -> None:
    with pytest.raises(ValueError, match="checkpoint_at_utc"):
        build_evidence_timing(
            configured_duration_seconds=60,
            started_at_utc=START,
            checkpoint_at_utc=START - timedelta(seconds=1),
            ended_at_utc=START + timedelta(seconds=60),
            first_snapshot_at=START,
            last_event_at=START + timedelta(seconds=60),
            terminal_reason="configured_duration_reached",
            stop_requested=False,
            total_disconnect_seconds=Decimal("0"),
            threshold_policy_version="edmn.v2.thresholds.v1",
            threshold_source_commit="0123456789abcdef",
            threshold_effective_utc=START,
        )


@pytest.mark.parametrize(
    "disconnect",
    [0.25, Decimal("NaN"), Decimal("Infinity")],
)
def test_disconnect_duration_requires_a_finite_decimal(disconnect) -> None:
    with pytest.raises(ValueError, match="total_disconnect_seconds"):
        build_evidence_timing(
            configured_duration_seconds=60,
            started_at_utc=START,
            checkpoint_at_utc=START + timedelta(seconds=60),
            ended_at_utc=None,
            first_snapshot_at=None,
            last_event_at=None,
            terminal_reason=None,
            stop_requested=False,
            total_disconnect_seconds=disconnect,
            threshold_policy_version="edmn.v2.thresholds.v1",
            threshold_source_commit="0123456789abcdef",
            threshold_effective_utc=START,
        )


def test_timing_preserves_independent_freshness_and_window_maxima() -> None:
    timing = build_evidence_timing(
        configured_duration_seconds=60,
        started_at_utc=START,
        checkpoint_at_utc=START + timedelta(seconds=60),
        ended_at_utc=None,
        first_snapshot_at=START,
        last_event_at=START + timedelta(seconds=55),
        terminal_reason=None,
        stop_requested=False,
        total_disconnect_seconds=Decimal("3.5"),
        transport_keepalive_age_seconds=7,
        lifecycle_observation_age_seconds=31,
        orderbook_event_quiet_interval_seconds=503,
        max_transport_keepalive_age_seconds=11,
        max_lifecycle_observation_age_seconds=47,
        max_orderbook_event_quiet_interval_seconds=900,
        threshold_policy_version="edmn.v2.thresholds.v1",
        threshold_source_commit="0123456789abcdef",
        threshold_effective_utc=START,
    )

    record = timing.to_record()
    assert record["transport_keepalive_age_seconds"] == 7
    assert record["lifecycle_observation_age_seconds"] == 31
    assert record["orderbook_event_quiet_interval_seconds"] == 503
    assert record["max_transport_keepalive_age_seconds"] == 11
    assert record["max_lifecycle_observation_age_seconds"] == 47
    assert record["max_orderbook_event_quiet_interval_seconds"] == 900


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transport_keepalive_age_seconds", True),
        ("lifecycle_observation_age_seconds", 1.5),
        ("max_orderbook_event_quiet_interval_seconds", -1),
    ],
)
def test_freshness_ages_are_nonnegative_integer_seconds(field, value) -> None:
    freshness = {field: value}

    with pytest.raises(ValueError, match="freshness ages"):
        build_evidence_timing(
            configured_duration_seconds=60,
            started_at_utc=START,
            checkpoint_at_utc=START + timedelta(seconds=60),
            ended_at_utc=None,
            first_snapshot_at=None,
            last_event_at=None,
            terminal_reason=None,
            stop_requested=False,
            total_disconnect_seconds=Decimal("0"),
            threshold_policy_version="edmn.v2.thresholds.v1",
            threshold_source_commit="0123456789abcdef",
            threshold_effective_utc=START,
            **freshness,
        )


def test_timing_requires_threshold_provenance() -> None:
    with pytest.raises(ValueError, match="threshold"):
        build_evidence_timing(
            configured_duration_seconds=60,
            started_at_utc=START,
            checkpoint_at_utc=START + timedelta(seconds=60),
            ended_at_utc=None,
            first_snapshot_at=None,
            last_event_at=None,
            terminal_reason=None,
            stop_requested=False,
            total_disconnect_seconds=Decimal("0"),
            threshold_policy_version="",
            threshold_source_commit="",
            threshold_effective_utc=START,
        )


def test_threshold_policy_must_be_effective_before_evidence_window() -> None:
    with pytest.raises(ValueError, match="effective"):
        build_evidence_timing(
            configured_duration_seconds=60,
            started_at_utc=START,
            checkpoint_at_utc=START + timedelta(seconds=60),
            ended_at_utc=None,
            first_snapshot_at=None,
            last_event_at=None,
            terminal_reason=None,
            stop_requested=False,
            total_disconnect_seconds=Decimal("0"),
            threshold_policy_version="edmn.v2.thresholds.v1",
            threshold_source_commit="0123456789abcdef",
            threshold_effective_utc=START + timedelta(seconds=1),
        )


def _dimensions(status: EvidenceStatus) -> EvidenceDimensions:
    return EvidenceDimensions(
        artifact_integrity=status,
        transport_connectivity=status,
        transport_keepalive=status,
        subscription_status=status,
        sequence_integrity=status,
        rebuild_integrity=status,
        market_lifecycle_validity=status,
        duration_evidence=status,
        process_liveness=status,
        supervisor_liveness=status,
        backup_integrity=status,
        replay_qualification=status,
    )
