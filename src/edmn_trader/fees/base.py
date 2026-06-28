"""Venue-neutral fee estimate objects."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from edmn_trader.core.models import ZERO


class FeeEstimateStatus(StrEnum):
    """How usable a fee estimate is for paper-candidate decisions."""

    SUPPLIED = "supplied"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FeeEstimate:
    """Explicit fee estimate for one venue."""

    venue: str
    status: FeeEstimateStatus
    fee_per_contract: Decimal | None
    source_note: str

    def __post_init__(self) -> None:
        if not self.venue:
            msg = "venue is required"
            raise ValueError(msg)
        if not self.source_note:
            msg = "source_note is required"
            raise ValueError(msg)
        if not isinstance(self.status, FeeEstimateStatus):
            msg = "status must be a FeeEstimateStatus"
            raise TypeError(msg)
        if self.status is FeeEstimateStatus.SUPPLIED:
            _require_decimal(self.fee_per_contract, field_name="fee_per_contract")
            _validate_non_negative(self.fee_per_contract, field_name="fee_per_contract")
        elif self.fee_per_contract is not None:
            msg = "fee_per_contract must be None unless status is supplied"
            raise ValueError(msg)

    @property
    def blocks_paper_candidate(self) -> bool:
        return self.status is not FeeEstimateStatus.SUPPLIED


def supplied_fee_estimate(
    *,
    venue: str,
    fee_per_contract: Decimal,
    source_note: str,
) -> FeeEstimate:
    return FeeEstimate(
        venue=venue,
        status=FeeEstimateStatus.SUPPLIED,
        fee_per_contract=fee_per_contract,
        source_note=source_note,
    )


def missing_fee_estimate(
    *,
    venue: str,
    source_note: str = "fee model not supplied",
) -> FeeEstimate:
    return FeeEstimate(
        venue=venue,
        status=FeeEstimateStatus.MISSING,
        fee_per_contract=None,
        source_note=source_note,
    )


def unknown_fee_estimate(
    *,
    venue: str,
    source_note: str,
) -> FeeEstimate:
    return FeeEstimate(
        venue=venue,
        status=FeeEstimateStatus.UNKNOWN,
        fee_per_contract=None,
        source_note=source_note,
    )


def _require_decimal(value: Decimal | None, *, field_name: str) -> None:
    if not isinstance(value, Decimal):
        msg = f"{field_name} must be a Decimal"
        raise TypeError(msg)


def _validate_non_negative(value: Decimal, *, field_name: str) -> None:
    if value < ZERO:
        msg = f"{field_name} must be non-negative"
        raise ValueError(msg)
