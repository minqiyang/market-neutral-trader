"""Disabled private live execution gate for the public repository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PRIVATE_LIVE_PREREQUISITES_UNMET = (
    "30-90 days live read-only data",
    "30+ days paper trading history",
    "zero unresolved reconciliation mismatches",
    "validated fee/slippage assumptions",
    "successful demo lifecycle coverage",
    "kill-switch and manual approval drills",
    "legal/platform compliance review",
)


@dataclass(frozen=True, slots=True)
class PrivateLiveGateDecision:
    """Public-repo live gate state. It never authorizes execution."""

    status: Literal["disabled"] = "disabled"
    reason: str = "public repository live execution is disabled"
    prerequisites_unmet: tuple[str, ...] = PRIVATE_LIVE_PREREQUISITES_UNMET
    production_trading_enabled: bool = False
    executable_order_intent: bool = False
    record_type: str = "private_live_execution_gate"
    research_use: str = "private_live_gate_design_only"

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "status": self.status,
            "reason": self.reason,
            "production_trading_enabled": self.production_trading_enabled,
            "executable_order_intent": self.executable_order_intent,
            "prerequisites_unmet": list(self.prerequisites_unmet),
        }


def attempt_private_live_execution() -> PrivateLiveGateDecision:
    """Fail closed for any public-repo live execution attempt."""

    return PrivateLiveGateDecision()
