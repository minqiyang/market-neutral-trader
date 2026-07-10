"""Orthogonal evidence classification and timestamp-derived timing."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum


class EvidenceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class OverallEvidenceClassification(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class EvidenceDimensions:
    artifact_integrity: EvidenceStatus
    transport_connectivity: EvidenceStatus
    transport_keepalive: EvidenceStatus
    subscription_status: EvidenceStatus
    sequence_integrity: EvidenceStatus
    rebuild_integrity: EvidenceStatus
    market_lifecycle_validity: EvidenceStatus
    duration_evidence: EvidenceStatus
    process_liveness: EvidenceStatus
    supervisor_liveness: EvidenceStatus
    backup_integrity: EvidenceStatus
    replay_qualification: EvidenceStatus

    def __post_init__(self) -> None:
        for item in fields(self):
            object.__setattr__(self, item.name, EvidenceStatus(getattr(self, item.name)))

    def to_record(self) -> dict[str, EvidenceStatus]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass(frozen=True, slots=True)
class EvidenceClassification:
    dimensions: EvidenceDimensions
    overall_classification: OverallEvidenceClassification

    def __post_init__(self) -> None:
        expected = _overall_classification(self.dimensions)
        if OverallEvidenceClassification(self.overall_classification) is not expected:
            raise ValueError("overall classification contradicts evidence dimensions")
        object.__setattr__(self, "overall_classification", expected)

    def to_record(self) -> dict[str, object]:
        return {
            "dimensions": self.dimensions.to_record(),
            "overall_classification": self.overall_classification,
        }


@dataclass(frozen=True, slots=True)
class EvidenceTiming:
    configured_duration_seconds: int
    actual_elapsed_seconds: Decimal
    connected_elapsed_seconds: Decimal
    started_at_utc: datetime
    checkpoint_at_utc: datetime | None
    first_snapshot_at: datetime | None
    last_event_at: datetime | None
    ended_at: datetime | None
    terminal_reason: str | None
    stop_requested: bool
    total_disconnect_seconds: Decimal
    transport_keepalive_age_seconds: int | None
    lifecycle_observation_age_seconds: int | None
    orderbook_event_quiet_interval_seconds: int | None
    max_transport_keepalive_age_seconds: int | None
    max_lifecycle_observation_age_seconds: int | None
    max_orderbook_event_quiet_interval_seconds: int | None
    threshold_policy_version: str
    threshold_source_commit: str
    threshold_effective_utc: datetime

    def __post_init__(self) -> None:
        _require_positive_int(
            self.configured_duration_seconds,
            "configured_duration_seconds",
        )
        for name, value in (
            ("actual_elapsed_seconds", self.actual_elapsed_seconds),
            ("connected_elapsed_seconds", self.connected_elapsed_seconds),
            ("total_disconnect_seconds", self.total_disconnect_seconds),
        ):
            _require_finite_decimal(value, name)
        for name, value in (
            ("started_at_utc", self.started_at_utc),
            ("checkpoint_at_utc", self.checkpoint_at_utc),
            ("first_snapshot_at", self.first_snapshot_at),
            ("last_event_at", self.last_event_at),
            ("ended_at", self.ended_at),
            ("threshold_effective_utc", self.threshold_effective_utc),
        ):
            if value is not None:
                _require_aware(value, name)
                object.__setattr__(self, name, value.astimezone(UTC))
        evidence_at = self.ended_at or self.checkpoint_at_utc
        if evidence_at is None or evidence_at < self.started_at_utc:
            raise ValueError("valid terminal or checkpoint evidence is required")
        if (
            self.checkpoint_at_utc is not None
            and self.checkpoint_at_utc < self.started_at_utc
        ):
            raise ValueError("checkpoint_at_utc must not precede evidence start")
        expected_actual = _decimal_duration(evidence_at - self.started_at_utc)
        if self.actual_elapsed_seconds != expected_actual:
            raise ValueError("actual elapsed time contradicts timestamps")
        if (
            self.total_disconnect_seconds < 0
            or self.total_disconnect_seconds > expected_actual
            or self.connected_elapsed_seconds
            != expected_actual - self.total_disconnect_seconds
        ):
            raise ValueError("connected elapsed time contradicts disconnect evidence")
        if self.ended_at is None:
            if self.terminal_reason is not None:
                raise ValueError("terminal_reason requires ended_at evidence")
        elif not isinstance(self.terminal_reason, str) or not self.terminal_reason:
            raise ValueError("terminal_reason is required for ended evidence")
        if not self.threshold_policy_version or not self.threshold_source_commit:
            raise ValueError("threshold policy provenance is required")
        source_commit = self.threshold_source_commit.lower()
        if len(source_commit) < 7 or any(
            character not in "0123456789abcdef" for character in source_commit
        ):
            raise ValueError("threshold source commit must be hexadecimal")
        object.__setattr__(self, "threshold_source_commit", source_commit)
        if self.threshold_effective_utc > self.started_at_utc:
            raise ValueError("threshold policy must be effective before evidence starts")
        if not isinstance(self.stop_requested, bool):
            raise ValueError("stop_requested must be Boolean")
        for name, value in (
            ("first_snapshot_at", self.first_snapshot_at),
            ("last_event_at", self.last_event_at),
        ):
            if value is not None and not self.started_at_utc <= value <= evidence_at:
                raise ValueError(f"{name} must fall within the evidence window")
        if self.first_snapshot_at is not None and (
            self.last_event_at is None or self.first_snapshot_at > self.last_event_at
        ):
            raise ValueError("first_snapshot_at cannot be later than last_event_at")
        current_ages = (
            self.transport_keepalive_age_seconds,
            self.lifecycle_observation_age_seconds,
            self.orderbook_event_quiet_interval_seconds,
        )
        max_ages = (
            self.max_transport_keepalive_age_seconds,
            self.max_lifecycle_observation_age_seconds,
            self.max_orderbook_event_quiet_interval_seconds,
        )
        _validate_freshness_ages(current_ages, max_ages)

    def to_record(self) -> dict[str, object]:
        return {
            "configured_duration_seconds": self.configured_duration_seconds,
            "actual_elapsed_seconds": _decimal_text(self.actual_elapsed_seconds),
            "connected_elapsed_seconds": _decimal_text(self.connected_elapsed_seconds),
            "started_at_utc": self.started_at_utc.isoformat(),
            "checkpoint_at_utc": _time_text(self.checkpoint_at_utc),
            "first_snapshot_at": _time_text(self.first_snapshot_at),
            "last_event_at": _time_text(self.last_event_at),
            "ended_at": _time_text(self.ended_at),
            "terminal_reason": self.terminal_reason,
            "stop_requested": self.stop_requested,
            "total_disconnect_seconds": _decimal_text(
                self.total_disconnect_seconds
            ),
            "transport_keepalive_age_seconds": self.transport_keepalive_age_seconds,
            "lifecycle_observation_age_seconds": (
                self.lifecycle_observation_age_seconds
            ),
            "orderbook_event_quiet_interval_seconds": (
                self.orderbook_event_quiet_interval_seconds
            ),
            "max_transport_keepalive_age_seconds": (
                self.max_transport_keepalive_age_seconds
            ),
            "max_lifecycle_observation_age_seconds": (
                self.max_lifecycle_observation_age_seconds
            ),
            "max_orderbook_event_quiet_interval_seconds": (
                self.max_orderbook_event_quiet_interval_seconds
            ),
            "threshold_policy_version": self.threshold_policy_version,
            "threshold_source_commit": self.threshold_source_commit,
            "threshold_effective_utc": self.threshold_effective_utc.isoformat(),
        }


def classify_evidence(dimensions: EvidenceDimensions) -> EvidenceClassification:
    return EvidenceClassification(dimensions, _overall_classification(dimensions))


def _overall_classification(
    dimensions: EvidenceDimensions,
) -> OverallEvidenceClassification:
    statuses = tuple(dimensions.to_record().values())
    if EvidenceStatus.FAIL in statuses:
        return OverallEvidenceClassification.FAIL
    if EvidenceStatus.UNKNOWN in statuses:
        return OverallEvidenceClassification.INCOMPLETE
    return OverallEvidenceClassification.PASS


def build_evidence_timing(
    *,
    configured_duration_seconds: int,
    started_at_utc: datetime,
    checkpoint_at_utc: datetime | None,
    ended_at_utc: datetime | None,
    first_snapshot_at: datetime | None,
    last_event_at: datetime | None,
    terminal_reason: str | None,
    stop_requested: bool,
    total_disconnect_seconds: Decimal,
    threshold_policy_version: str,
    threshold_source_commit: str,
    threshold_effective_utc: datetime,
    transport_keepalive_age_seconds: int | None = None,
    lifecycle_observation_age_seconds: int | None = None,
    orderbook_event_quiet_interval_seconds: int | None = None,
    max_transport_keepalive_age_seconds: int | None = None,
    max_lifecycle_observation_age_seconds: int | None = None,
    max_orderbook_event_quiet_interval_seconds: int | None = None,
) -> EvidenceTiming:
    for name, value in (
        ("started_at_utc", started_at_utc),
        ("checkpoint_at_utc", checkpoint_at_utc),
        ("ended_at_utc", ended_at_utc),
        ("first_snapshot_at", first_snapshot_at),
        ("last_event_at", last_event_at),
        ("threshold_effective_utc", threshold_effective_utc),
    ):
        if value is not None:
            _require_aware(value, name)
    evidence_at = ended_at_utc or checkpoint_at_utc
    if evidence_at is None:
        raise ValueError("ended_at_utc or checkpoint_at_utc is required")
    if evidence_at < started_at_utc:
        raise ValueError("evidence timestamp must not precede start")
    actual = _decimal_duration(evidence_at - started_at_utc)
    disconnect = _require_finite_decimal(
        total_disconnect_seconds,
        "total_disconnect_seconds",
    )
    if disconnect < 0 or disconnect > actual:
        raise ValueError("total_disconnect_seconds is outside the evidence window")
    return EvidenceTiming(
        configured_duration_seconds=configured_duration_seconds,
        actual_elapsed_seconds=actual,
        connected_elapsed_seconds=actual - disconnect,
        started_at_utc=started_at_utc,
        checkpoint_at_utc=checkpoint_at_utc,
        first_snapshot_at=first_snapshot_at,
        last_event_at=last_event_at,
        ended_at=ended_at_utc,
        terminal_reason=terminal_reason,
        stop_requested=stop_requested,
        total_disconnect_seconds=disconnect,
        transport_keepalive_age_seconds=transport_keepalive_age_seconds,
        lifecycle_observation_age_seconds=lifecycle_observation_age_seconds,
        orderbook_event_quiet_interval_seconds=orderbook_event_quiet_interval_seconds,
        max_transport_keepalive_age_seconds=max_transport_keepalive_age_seconds,
        max_lifecycle_observation_age_seconds=max_lifecycle_observation_age_seconds,
        max_orderbook_event_quiet_interval_seconds=(
            max_orderbook_event_quiet_interval_seconds
        ),
        threshold_policy_version=threshold_policy_version,
        threshold_source_commit=threshold_source_commit,
        threshold_effective_utc=threshold_effective_utc,
    )


def classify_duration_evidence(timing: EvidenceTiming) -> EvidenceStatus:
    if timing.actual_elapsed_seconds >= timing.configured_duration_seconds:
        return EvidenceStatus.PASS
    if timing.ended_at is not None:
        return EvidenceStatus.FAIL
    return EvidenceStatus.UNKNOWN


def _decimal_duration(value: timedelta) -> Decimal:
    days = value.days
    seconds = value.seconds
    microseconds = value.microseconds
    return (
        Decimal(days * 86_400 + seconds)
        + Decimal(microseconds) / Decimal("1000000")
    )


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _time_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_finite_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")
    return value


def _require_positive_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _validate_freshness_ages(
    current_ages: tuple[int | None, int | None, int | None],
    max_ages: tuple[int | None, int | None, int | None],
) -> None:
    if any(
        value is not None
        and (not isinstance(value, int) or isinstance(value, bool) or value < 0)
        for value in (*current_ages, *max_ages)
    ):
        raise ValueError("freshness ages must be non-negative integer seconds")
    if any(
        current is not None and maximum is not None and maximum < current
        for current, maximum in zip(current_ages, max_ages, strict=True)
    ):
        raise ValueError("freshness window maximum cannot be below current age")
