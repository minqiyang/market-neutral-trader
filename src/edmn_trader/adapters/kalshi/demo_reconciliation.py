"""Local Kalshi Demo reconciliation replay."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from edmn_trader.core.models import ONE, ZERO
from edmn_trader.data.jsonl import append_jsonl_record

DemoEventType = Literal[
    "accepted",
    "rejected",
    "partial_fill",
    "full_fill",
    "cancel",
    "error",
    "timeout",
    "backfill",
]
ResolvedDemoEventType = Literal[
    "accepted",
    "rejected",
    "partial_fill",
    "full_fill",
    "cancel",
    "error",
    "timeout",
]

_EVENT_TYPES = {
    "accepted",
    "rejected",
    "partial_fill",
    "full_fill",
    "cancel",
    "error",
    "timeout",
    "backfill",
}
_RESOLVED_EVENT_TYPES = _EVENT_TYPES - {"backfill"}
_TERMINAL_EVENT_TYPES = {"rejected", "cancel", "error", "timeout"}


class KalshiDemoReconciliationError(Exception):
    """Raised when Demo reconciliation records are malformed."""


@dataclass(frozen=True, slots=True)
class KalshiDemoOrderState:
    """Reconciled local state for one Stage 49 Demo request preview."""

    client_order_id: str
    side: Literal["yes", "no"]
    submitted_quantity: Decimal
    accepted: bool = False
    rejected: bool = False
    canceled: bool = False
    errored: bool = False
    timed_out: bool = False
    filled_quantity: Decimal = ZERO
    average_fill_price: Decimal = ZERO

    @property
    def fully_filled(self) -> bool:
        return self.filled_quantity == self.submitted_quantity

    def to_record(self) -> dict[str, object]:
        return {
            "client_order_id": self.client_order_id,
            "side": self.side,
            "submitted_quantity": str(self.submitted_quantity),
            "accepted": self.accepted,
            "rejected": self.rejected,
            "canceled": self.canceled,
            "errored": self.errored,
            "timed_out": self.timed_out,
            "filled_quantity": str(self.filled_quantity),
            "average_fill_price": str(self.average_fill_price),
            "fully_filled": self.fully_filled,
        }


@dataclass(frozen=True, slots=True)
class KalshiDemoReconciliationMismatch:
    """One mismatch that blocks later Demo submit eligibility."""

    client_order_id: str
    reason: str
    event_id: str | None = None

    def to_record(self) -> dict[str, object]:
        return {
            "client_order_id": self.client_order_id,
            "reason": self.reason,
            "event_id": self.event_id,
        }


@dataclass(frozen=True, slots=True)
class KalshiDemoReconciliationState:
    """Final local reconciliation state rebuilt from connector audit and events."""

    proposal_id: str
    candidate_hash: str
    approval_id: str
    audit_record_hash: str
    orders: tuple[KalshiDemoOrderState, ...]
    mismatches: tuple[KalshiDemoReconciliationMismatch, ...]
    accepted_count: int
    rejected_count: int
    partial_fill_count: int
    full_fill_count: int
    cancel_count: int
    error_count: int
    timeout_count: int
    backfill_count: int
    duplicate_event_count: int
    record_type: str = "kalshi_demo_reconciliation_state"
    research_use: str = "demo_paper_research_reconciliation_only"
    executable_order_intent: bool = False

    @property
    def mismatch_count(self) -> int:
        return len(self.mismatches)

    @property
    def submit_eligible(self) -> bool:
        return self.mismatch_count == 0

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "proposal_id": self.proposal_id,
            "candidate_hash": self.candidate_hash,
            "approval_id": self.approval_id,
            "audit_record_hash": self.audit_record_hash,
            "submit_eligible": self.submit_eligible,
            "mismatch_count": self.mismatch_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "partial_fill_count": self.partial_fill_count,
            "full_fill_count": self.full_fill_count,
            "cancel_count": self.cancel_count,
            "error_count": self.error_count,
            "timeout_count": self.timeout_count,
            "backfill_count": self.backfill_count,
            "duplicate_event_count": self.duplicate_event_count,
            "orders": [order.to_record() for order in self.orders],
            "mismatches": [mismatch.to_record() for mismatch in self.mismatches],
        }


@dataclass(slots=True)
class _MutableOrderState:
    client_order_id: str
    side: Literal["yes", "no"]
    submitted_quantity: Decimal
    accepted: bool = False
    rejected: bool = False
    canceled: bool = False
    errored: bool = False
    timed_out: bool = False
    filled_quantity: Decimal = ZERO
    fill_cost: Decimal = ZERO

    @property
    def terminal(self) -> bool:
        return self.rejected or self.canceled or self.errored or self.timed_out

    def to_order_state(self) -> KalshiDemoOrderState:
        average = ZERO
        if self.filled_quantity > ZERO:
            average = self.fill_cost / self.filled_quantity
        return KalshiDemoOrderState(
            client_order_id=self.client_order_id,
            side=self.side,
            submitted_quantity=self.submitted_quantity,
            accepted=self.accepted,
            rejected=self.rejected,
            canceled=self.canceled,
            errored=self.errored,
            timed_out=self.timed_out,
            filled_quantity=self.filled_quantity,
            average_fill_price=average,
        )


def reconcile_kalshi_demo_events(
    audit_record: Mapping[str, object],
    event_records: Iterable[Mapping[str, object]],
) -> KalshiDemoReconciliationState:
    """Replay local/mock Demo events against one Stage 49 connector audit record."""

    proposal_id = _expect_str(audit_record, "proposal_id")
    candidate_hash = _expect_str(audit_record, "candidate_hash")
    approval_id = _expect_str(audit_record, "approval_id")
    orders = _orders_from_audit(audit_record)
    mismatches: list[KalshiDemoReconciliationMismatch] = []
    seen_events: dict[str, str] = {}
    duplicate_count = 0
    counts = {
        "accepted": 0,
        "rejected": 0,
        "partial_fill": 0,
        "full_fill": 0,
        "cancel": 0,
        "error": 0,
        "timeout": 0,
        "backfill": 0,
    }

    for event in event_records:
        _require_event_record(event)
        event_id = _expect_str(event, "event_id")
        event_hash = _hash_record(event)
        previous_hash = seen_events.get(event_id)
        if previous_hash == event_hash:
            duplicate_count += 1
            continue
        if previous_hash is not None:
            mismatches.append(_mismatch(event, "conflicting_duplicate_event"))
            continue
        seen_events[event_id] = event_hash

        if event.get("proposal_id") != proposal_id or event.get("candidate_hash") != candidate_hash:
            mismatches.append(_mismatch(event, "source_hash_mismatch"))
            continue
        if event.get("approval_id") != approval_id:
            mismatches.append(_mismatch(event, "approval_id_mismatch"))
            continue

        client_order_id = _expect_str(event, "client_order_id")
        order = orders.get(client_order_id)
        if order is None:
            mismatches.append(_mismatch(event, "unknown_client_order_id"))
            continue

        event_type = _event_type(event)
        counts[event_type] += 1
        resolved_type = _resolved_event_type(event, event_type=event_type)
        if event_type == "backfill":
            counts[resolved_type] += 1
        _apply_event(order=order, event=event, event_type=resolved_type, mismatches=mismatches)

    if audit_record.get("status") == "submitted":
        for order in orders.values():
            if not _has_any_state(order):
                mismatches.append(
                    KalshiDemoReconciliationMismatch(
                        client_order_id=order.client_order_id,
                        reason="missing_demo_event",
                    )
                )

    return KalshiDemoReconciliationState(
        proposal_id=proposal_id,
        candidate_hash=candidate_hash,
        approval_id=approval_id,
        audit_record_hash=_hash_record(audit_record),
        orders=tuple(order.to_order_state() for order in orders.values()),
        mismatches=tuple(mismatches),
        accepted_count=counts["accepted"],
        rejected_count=counts["rejected"],
        partial_fill_count=counts["partial_fill"],
        full_fill_count=counts["full_fill"],
        cancel_count=counts["cancel"],
        error_count=counts["error"],
        timeout_count=counts["timeout"],
        backfill_count=counts["backfill"],
        duplicate_event_count=duplicate_count,
    )


def append_kalshi_demo_reconciliation_jsonl(
    path: Path,
    state: KalshiDemoReconciliationState,
) -> None:
    """Append one local reconciliation state record."""

    append_jsonl_record(path, state.to_record())


def require_demo_reconciliation_submit_eligible(record: Mapping[str, object]) -> None:
    """Raise when a reconciliation state must hard-stop later Demo submissions."""

    if record.get("record_type") != "kalshi_demo_reconciliation_state":
        msg = "demo reconciliation record_type must be kalshi_demo_reconciliation_state"
        raise KalshiDemoReconciliationError(msg)
    if record.get("executable_order_intent") is not False:
        msg = "demo reconciliation record must not be executable"
        raise KalshiDemoReconciliationError(msg)
    if record.get("submit_eligible") is not True or record.get("mismatch_count") != 0:
        msg = "demo reconciliation mismatch blocks Demo submit eligibility"
        raise KalshiDemoReconciliationError(msg)


def _apply_event(
    *,
    order: _MutableOrderState,
    event: Mapping[str, object],
    event_type: ResolvedDemoEventType,
    mismatches: list[KalshiDemoReconciliationMismatch],
) -> None:
    if event_type == "accepted":
        if order.terminal:
            mismatches.append(_mismatch(event, "accepted_after_terminal_event"))
            return
        order.accepted = True
        return
    if event_type in _TERMINAL_EVENT_TYPES:
        _apply_terminal(order=order, event=event, event_type=event_type, mismatches=mismatches)
        return

    if not order.accepted:
        mismatches.append(_mismatch(event, "missing_acceptance_before_fill"))
    quantity = _positive_decimal(event, "quantity")
    price = _probability_decimal(event, "price")
    order.filled_quantity += quantity
    order.fill_cost += price * quantity
    if order.filled_quantity > order.submitted_quantity:
        mismatches.append(_mismatch(event, "fill_exceeds_submitted_quantity"))
    if event_type == "partial_fill" and order.filled_quantity >= order.submitted_quantity:
        mismatches.append(_mismatch(event, "partial_fill_not_partial"))
    if event_type == "full_fill" and order.filled_quantity != order.submitted_quantity:
        mismatches.append(_mismatch(event, "full_fill_quantity_mismatch"))


def _apply_terminal(
    *,
    order: _MutableOrderState,
    event: Mapping[str, object],
    event_type: ResolvedDemoEventType,
    mismatches: list[KalshiDemoReconciliationMismatch],
) -> None:
    if order.filled_quantity == order.submitted_quantity:
        mismatches.append(_mismatch(event, "terminal_event_after_full_fill"))
        return
    if order.terminal:
        mismatches.append(_mismatch(event, "conflicting_terminal_event"))
        return
    if event_type == "rejected":
        if order.accepted or order.filled_quantity > ZERO:
            mismatches.append(_mismatch(event, "reject_after_accept_or_fill"))
        order.rejected = True
    elif event_type == "cancel":
        if not order.accepted:
            mismatches.append(_mismatch(event, "missing_acceptance_before_cancel"))
        order.canceled = True
    elif event_type == "error":
        order.errored = True
    elif event_type == "timeout":
        order.timed_out = True


def _orders_from_audit(audit_record: Mapping[str, object]) -> dict[str, _MutableOrderState]:
    previews = _sequence(audit_record.get("request_previews"), field_name="request_previews")
    orders: dict[str, _MutableOrderState] = {}
    for preview_object in previews:
        preview = _mapping(preview_object, field_name="request_preview")
        body = _mapping(preview.get("body"), field_name="request_preview.body")
        client_order_id = _expect_str(body, "client_order_id")
        if client_order_id in orders:
            msg = "duplicate client_order_id in audit record"
            raise KalshiDemoReconciliationError(msg)
        side = _side(body)
        orders[client_order_id] = _MutableOrderState(
            client_order_id=client_order_id,
            side=side,
            submitted_quantity=_count_decimal(body),
        )
    if not orders:
        msg = "audit record must contain at least one request preview"
        raise KalshiDemoReconciliationError(msg)
    return orders


def _require_event_record(record: Mapping[str, object]) -> None:
    if record.get("record_type") != "kalshi_demo_event":
        msg = "event record_type must be kalshi_demo_event"
        raise KalshiDemoReconciliationError(msg)
    if record.get("executable_order_intent") is not False:
        msg = "event record must not be executable"
        raise KalshiDemoReconciliationError(msg)


def _event_type(record: Mapping[str, object]) -> DemoEventType:
    value = _expect_str(record, "event_type")
    if value not in _EVENT_TYPES:
        msg = "event_type must be a supported Kalshi Demo reconciliation event"
        raise KalshiDemoReconciliationError(msg)
    return value  # type: ignore[return-value]


def _resolved_event_type(
    record: Mapping[str, object],
    *,
    event_type: DemoEventType,
) -> ResolvedDemoEventType:
    if event_type != "backfill":
        return event_type
    resolved = _expect_str(record, "resolved_event_type")
    if resolved not in _RESOLVED_EVENT_TYPES:
        msg = "backfill resolved_event_type must be a supported non-backfill event"
        raise KalshiDemoReconciliationError(msg)
    return resolved  # type: ignore[return-value]


def _mismatch(
    record: Mapping[str, object],
    reason: str,
) -> KalshiDemoReconciliationMismatch:
    client_order_id = record.get("client_order_id")
    event_id = record.get("event_id")
    return KalshiDemoReconciliationMismatch(
        client_order_id=client_order_id if isinstance(client_order_id, str) else "unknown",
        reason=reason,
        event_id=event_id if isinstance(event_id, str) else None,
    )


def _has_any_state(order: _MutableOrderState) -> bool:
    return (
        order.accepted
        or order.terminal
        or order.filled_quantity > ZERO
    )


def _hash_record(record: Mapping[str, object]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _side(record: Mapping[str, object]) -> Literal["yes", "no"]:
    value = _expect_str(record, "side")
    if value not in {"yes", "no"}:
        msg = "side must be yes or no"
        raise KalshiDemoReconciliationError(msg)
    return value  # type: ignore[return-value]


def _count_decimal(record: Mapping[str, object]) -> Decimal:
    value = record.get("count")
    if not isinstance(value, int) or value <= 0:
        msg = "request preview count must be a positive integer"
        raise KalshiDemoReconciliationError(msg)
    return Decimal(value)


def _expect_str(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise KalshiDemoReconciliationError(msg)
    return value


def _positive_decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = _decimal(record, field_name)
    if value <= ZERO:
        msg = f"{field_name} must be positive"
        raise KalshiDemoReconciliationError(msg)
    return value


def _probability_decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = _decimal(record, field_name)
    if value < ZERO or value > ONE:
        msg = f"{field_name} must be in [0, 1]"
        raise KalshiDemoReconciliationError(msg)
    return value


def _decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string"
        raise KalshiDemoReconciliationError(msg)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise KalshiDemoReconciliationError(msg) from exc


def _sequence(value: object, *, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        msg = f"{field_name} must be a list"
        raise KalshiDemoReconciliationError(msg)
    return value


def _mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be an object"
        raise KalshiDemoReconciliationError(msg)
    return value
