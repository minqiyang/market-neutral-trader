"""Risk-gated demo execution smoke-test infrastructure."""

from edmn_trader.execution.demo import (
    DemoExecutionConfig,
    DemoExecutionRequest,
    DemoExecutionResult,
    ExecutionAuditLogger,
    FakeDemoExecutionAdapter,
    decide_execution_risk,
    execute_demo_request,
)
from edmn_trader.execution.private_live_gate import (
    PRIVATE_LIVE_PREREQUISITES_UNMET,
    PrivateLiveGateDecision,
    attempt_private_live_execution,
)

__all__ = [
    "DemoExecutionConfig",
    "DemoExecutionRequest",
    "DemoExecutionResult",
    "ExecutionAuditLogger",
    "FakeDemoExecutionAdapter",
    "PRIVATE_LIVE_PREREQUISITES_UNMET",
    "PrivateLiveGateDecision",
    "attempt_private_live_execution",
    "decide_execution_risk",
    "execute_demo_request",
]
