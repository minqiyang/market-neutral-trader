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

__all__ = [
    "DemoExecutionConfig",
    "DemoExecutionRequest",
    "DemoExecutionResult",
    "ExecutionAuditLogger",
    "FakeDemoExecutionAdapter",
    "decide_execution_risk",
    "execute_demo_request",
]
