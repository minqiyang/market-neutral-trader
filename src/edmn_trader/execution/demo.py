"""Risk-gated, fake-adapter demo execution smoke infrastructure."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

from edmn_trader.adapters.kalshi.client import KALSHI_DEMO_REST_BASE_URL
from edmn_trader.core import ExecutionMode, RiskDecision, RiskLimits
from edmn_trader.data.jsonl import append_jsonl_record
from edmn_trader.research import DryRunOrderIntent

ZERO = Decimal("0")
ONE = Decimal("1")

ExecutionAction = Literal["place", "cancel", "modify"]
ExecutionSide = Literal["buy", "sell"]
ExecutionStatus = Literal["rejected", "executed", "adapter_error"]
STAGE5_SMOKE_MARKER = "stage5_demo_execution_smoke"


class DemoExecutionAdapter(Protocol):
    """Minimal adapter boundary for Stage 5 fake/offline execution tests."""

    def place_order(self, request: DemoExecutionRequest) -> Mapping[str, Any]:
        """Place a demo order after risk approval."""

    def cancel_order(self, request: DemoExecutionRequest) -> Mapping[str, Any]:
        """Cancel a demo order after risk approval."""

    def modify_order(self, request: DemoExecutionRequest) -> Mapping[str, Any]:
        """Modify a demo order after risk approval."""


@dataclass(frozen=True, slots=True)
class DemoExecutionConfig:
    """Explicit demo execution configuration for Stage 5 smoke paths."""

    exchange: str = "kalshi_demo"
    base_url: str = KALSHI_DEMO_REST_BASE_URL
    demo_opt_in: bool = False
    smoke_test_marker: str = STAGE5_SMOKE_MARKER

    def __post_init__(self) -> None:
        if not self.exchange:
            msg = "exchange is required"
            raise ValueError(msg)
        if not self.base_url:
            msg = "base_url is required"
            raise ValueError(msg)
        if not self.smoke_test_marker:
            msg = "smoke_test_marker is required"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DemoExecutionRequest:
    """A candidate execution action before risk approval.

    Unlike core `OrderIntent`, this request can represent blocked attempts such
    as `LIVE_DISABLED`, so rejected actions can still be audited.
    """

    instrument_id: str
    action: ExecutionAction
    side: ExecutionSide
    price: Decimal
    quantity: Decimal
    execution_mode: ExecutionMode
    current_position: Decimal = ZERO
    current_inventory: Decimal = ZERO
    current_daily_loss: Decimal = ZERO
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.instrument_id:
            msg = "instrument_id is required"
            raise ValueError(msg)
        if self.action not in {"place", "cancel", "modify"}:
            msg = "action must be place, cancel, or modify"
            raise ValueError(msg)
        if self.side not in {"buy", "sell"}:
            msg = "side must be buy or sell"
            raise ValueError(msg)
        for field_name in (
            "price",
            "quantity",
            "current_position",
            "current_inventory",
            "current_daily_loss",
        ):
            if not isinstance(getattr(self, field_name), Decimal):
                msg = f"{field_name} must be a Decimal"
                raise TypeError(msg)
        if self.quantity <= ZERO:
            msg = "quantity must be positive"
            raise ValueError(msg)
        if self.current_daily_loss < ZERO:
            msg = "current_daily_loss must be non-negative"
            raise ValueError(msg)

    @classmethod
    def from_dry_run_intent(
        cls,
        intent: DryRunOrderIntent,
        *,
        execution_mode: ExecutionMode,
        current_position: Decimal = ZERO,
        current_inventory: Decimal = ZERO,
        action: ExecutionAction = "place",
    ) -> DemoExecutionRequest:
        """Convert a Stage 4 dry-run intent into a Stage 5 risk-gated request."""

        return cls(
            instrument_id=intent.instrument_id,
            action=action,
            side=intent.side,
            price=intent.price,
            quantity=intent.quantity,
            execution_mode=execution_mode,
            current_position=current_position,
            current_inventory=current_inventory,
            reason=f"from dry-run intent: {intent.reason}",
        )


@dataclass(frozen=True, slots=True)
class DemoExecutionResult:
    """Result of a risk-gated demo execution attempt."""

    status: ExecutionStatus
    risk_decision: RiskDecision
    adapter_result: Mapping[str, Any] | None = None
    error_reason: str | None = None


@dataclass(slots=True)
class FakeDemoExecutionAdapter:
    """Offline adapter used by tests and smoke scripts."""

    fail_actions: set[ExecutionAction] = field(default_factory=set)
    calls: list[tuple[ExecutionAction, DemoExecutionRequest]] = field(default_factory=list)

    def place_order(self, request: DemoExecutionRequest) -> Mapping[str, Any]:
        return self._record("place", request)

    def cancel_order(self, request: DemoExecutionRequest) -> Mapping[str, Any]:
        return self._record("cancel", request)

    def modify_order(self, request: DemoExecutionRequest) -> Mapping[str, Any]:
        return self._record("modify", request)

    def _record(self, action: ExecutionAction, request: DemoExecutionRequest) -> Mapping[str, Any]:
        self.calls.append((action, request))
        if action in self.fail_actions:
            msg = f"fake adapter {action} failure"
            raise RuntimeError(msg)
        return {
            "adapter": "fake",
            "action": action,
            "instrument_id": request.instrument_id,
            "status": "accepted",
        }


@dataclass(frozen=True, slots=True)
class ExecutionAuditLogger:
    """Append structured Stage 5 execution audit records as JSONL."""

    path: Path

    def log(
        self,
        *,
        request: DemoExecutionRequest,
        config: DemoExecutionConfig,
        risk_decision: RiskDecision,
        status: ExecutionStatus,
        adapter_called: bool,
        adapter_result: Mapping[str, Any] | None = None,
        error_reason: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Append one structured execution attempt record."""

        append_jsonl_record(
            self.path,
            build_execution_log_record(
                request=request,
                config=config,
                risk_decision=risk_decision,
                status=status,
                adapter_called=adapter_called,
                adapter_result=adapter_result,
                error_reason=error_reason,
                timestamp=timestamp,
            ),
        )


def execute_demo_request(
    request: DemoExecutionRequest,
    *,
    config: DemoExecutionConfig,
    limits: RiskLimits,
    adapter: DemoExecutionAdapter,
    logger: ExecutionAuditLogger,
) -> DemoExecutionResult:
    """Risk-check, log, and optionally send a request to the fake/demo adapter."""

    decision = decide_execution_risk(request=request, config=config, limits=limits)
    if not decision.approved:
        logger.log(
            request=request,
            config=config,
            risk_decision=decision,
            status="rejected",
            adapter_called=False,
            error_reason=decision.reason,
        )
        return DemoExecutionResult(
            status="rejected",
            risk_decision=decision,
            error_reason=decision.reason,
        )

    try:
        adapter_result = _call_adapter(adapter=adapter, request=request)
    except Exception as exc:  # noqa: BLE001 - adapter errors must be logged and returned.
        error_reason = str(exc)
        logger.log(
            request=request,
            config=config,
            risk_decision=decision,
            status="adapter_error",
            adapter_called=True,
            error_reason=error_reason,
        )
        return DemoExecutionResult(
            status="adapter_error",
            risk_decision=decision,
            error_reason=error_reason,
        )

    logger.log(
        request=request,
        config=config,
        risk_decision=decision,
        status="executed",
        adapter_called=True,
        adapter_result=adapter_result,
    )
    return DemoExecutionResult(
        status="executed",
        risk_decision=decision,
        adapter_result=adapter_result,
    )


def decide_execution_risk(
    *,
    request: DemoExecutionRequest,
    config: DemoExecutionConfig,
    limits: RiskLimits,
) -> RiskDecision:
    """Return a deterministic pre-execution risk decision."""

    if request.execution_mode is ExecutionMode.LIVE_DISABLED:
        return RiskDecision(
            approved=False,
            reason="LIVE_DISABLED rejects every execution action",
            limit_name="execution_mode",
        )
    if request.execution_mode is not ExecutionMode.DEMO:
        return RiskDecision(
            approved=False,
            reason="Stage 5 execution smoke tests require DEMO mode",
            limit_name="execution_mode",
        )
    if config.base_url != KALSHI_DEMO_REST_BASE_URL:
        return RiskDecision(
            approved=False,
            reason="non-demo or production endpoint is rejected",
            limit_name="base_url",
        )
    if not config.demo_opt_in:
        return RiskDecision(
            approved=False,
            reason="explicit demo opt-in is required",
            limit_name="demo_opt_in",
        )
    if request.price < ZERO or request.price > ONE:
        return RiskDecision(
            approved=False,
            reason="price must be within the binary contract range [0, 1]",
            limit_name="price_boundary",
        )
    if request.quantity > limits.max_order_quantity:
        return RiskDecision(
            approved=False,
            reason="order quantity exceeds max_order_quantity",
            limit_name="max_order_quantity",
        )
    if request.price * request.quantity > limits.max_notional:
        return RiskDecision(
            approved=False,
            reason="order notional exceeds max_notional",
            limit_name="max_notional",
        )
    if abs(_projected_value(request.current_position, request)) > limits.max_position_abs:
        return RiskDecision(
            approved=False,
            reason="projected position exceeds max_position_abs",
            limit_name="max_position_abs",
        )
    if abs(_projected_value(request.current_inventory, request)) > limits.max_position_abs:
        return RiskDecision(
            approved=False,
            reason="projected inventory exceeds max_position_abs",
            limit_name="max_inventory_abs",
        )
    if request.current_daily_loss > limits.max_daily_loss:
        return RiskDecision(
            approved=False,
            reason="current daily loss exceeds max_daily_loss",
            limit_name="max_daily_loss",
        )

    return RiskDecision(
        approved=True,
        reason="approved for explicit demo smoke execution with risk limits satisfied",
    )


def build_execution_log_record(
    *,
    request: DemoExecutionRequest,
    config: DemoExecutionConfig,
    risk_decision: RiskDecision,
    status: ExecutionStatus,
    adapter_called: bool,
    adapter_result: Mapping[str, Any] | None = None,
    error_reason: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build a secret-free structured audit record."""

    observed_at = timestamp or datetime.now(UTC)
    return {
        "timestamp": observed_at,
        "execution_mode": request.execution_mode.value,
        "exchange": config.exchange,
        "base_url": config.base_url,
        "instrument_id": request.instrument_id,
        "ticker": request.instrument_id,
        "requested_action": request.action,
        "order_intent": {
            "side": request.side,
            "price": request.price,
            "quantity": request.quantity,
            "reason": request.reason,
        },
        "risk_inputs": {
            "current_position": request.current_position,
            "current_inventory": request.current_inventory,
            "current_daily_loss": request.current_daily_loss,
        },
        "risk_decision": {
            "approved": risk_decision.approved,
            "reason": risk_decision.reason,
            "limit_name": risk_decision.limit_name,
        },
        "result_status": status,
        "adapter_called": adapter_called,
        "adapter_result": dict(adapter_result) if adapter_result is not None else None,
        "error_reason": error_reason,
        "demo_smoke_test": True,
        "demo_smoke_marker": config.smoke_test_marker,
    }


def _call_adapter(
    *,
    adapter: DemoExecutionAdapter,
    request: DemoExecutionRequest,
) -> Mapping[str, Any]:
    if request.action == "place":
        return adapter.place_order(request)
    if request.action == "cancel":
        return adapter.cancel_order(request)
    return adapter.modify_order(request)


def _projected_value(current_value: Decimal, request: DemoExecutionRequest) -> Decimal:
    if request.side == "buy":
        return current_value + request.quantity
    return current_value - request.quantity
