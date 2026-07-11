"""Reviewed prospective thresholds for D2 runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class EvidenceThresholdPolicy:
    version: str
    effective_at_utc: datetime
    minimum_connection_coverage: Decimal
    maximum_disconnect_seconds: int
    maximum_lifecycle_age_seconds: int
    orderbook_quiet_warning_seconds: int
    maximum_transport_keepalive_age_seconds: int

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("threshold policy version is required")
        if self.effective_at_utc.tzinfo is None:
            raise ValueError("threshold policy effective time must be timezone-aware")
        if not Decimal("0") <= self.minimum_connection_coverage <= Decimal("1"):
            raise ValueError("connection coverage threshold must be between zero and one")
        for value in (
            self.maximum_disconnect_seconds,
            self.maximum_lifecycle_age_seconds,
            self.orderbook_quiet_warning_seconds,
            self.maximum_transport_keepalive_age_seconds,
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("threshold ages must be non-negative integers")

    def to_record(self) -> dict[str, object]:
        return {
            "threshold_policy_version": self.version,
            "threshold_effective_utc": self.effective_at_utc.isoformat(),
            "minimum_connection_coverage": str(self.minimum_connection_coverage),
            "maximum_disconnect_seconds": self.maximum_disconnect_seconds,
            "maximum_lifecycle_age_seconds": self.maximum_lifecycle_age_seconds,
            "orderbook_quiet_warning_seconds": self.orderbook_quiet_warning_seconds,
            "maximum_transport_keepalive_age_seconds": (
                self.maximum_transport_keepalive_age_seconds
            ),
        }


V2_THRESHOLD_POLICY = EvidenceThresholdPolicy(
    version="edmn.v2.thresholds.v1",
    effective_at_utc=datetime(2026, 7, 10, 2, 24, tzinfo=UTC),
    minimum_connection_coverage=Decimal("0.95"),
    maximum_disconnect_seconds=15,
    maximum_lifecycle_age_seconds=120,
    orderbook_quiet_warning_seconds=300,
    maximum_transport_keepalive_age_seconds=120,
)
