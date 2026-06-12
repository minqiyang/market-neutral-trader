"""Event-driven market-neutral trader research package."""

from edmn_trader.core.models import (
    ExecutionMode,
    Instrument,
    NormalizedOrderBook,
    OrderBookLevel,
    OrderIntent,
    Position,
    Quote,
    RiskDecision,
    RiskLimits,
)
from edmn_trader.execution import (
    DemoExecutionConfig,
    DemoExecutionRequest,
    DemoExecutionResult,
    ExecutionAuditLogger,
    FakeDemoExecutionAdapter,
    decide_execution_risk,
    execute_demo_request,
)

__all__ = [
    "DemoExecutionConfig",
    "DemoExecutionRequest",
    "DemoExecutionResult",
    "ExecutionMode",
    "ExecutionAuditLogger",
    "FakeDemoExecutionAdapter",
    "Instrument",
    "NormalizedOrderBook",
    "OrderBookLevel",
    "OrderIntent",
    "Position",
    "Quote",
    "RiskDecision",
    "RiskLimits",
    "decide_execution_risk",
    "execute_demo_request",
]
