from __future__ import annotations

from edmn_trader.execution import (
    PRIVATE_LIVE_PREREQUISITES_UNMET,
    attempt_private_live_execution,
)


def test_private_live_gate_is_disabled_and_lists_unmet_prerequisites() -> None:
    decision = attempt_private_live_execution()

    assert decision.status == "disabled"
    assert decision.production_trading_enabled is False
    assert decision.executable_order_intent is False
    assert decision.prerequisites_unmet == PRIVATE_LIVE_PREREQUISITES_UNMET
    assert decision.prerequisites_unmet == (
        "30-90 days live read-only data",
        "30+ days paper trading history",
        "zero unresolved reconciliation mismatches",
        "validated fee/slippage assumptions",
        "successful demo lifecycle coverage",
        "kill-switch and manual approval drills",
        "legal/platform compliance review",
    )


def test_attempted_public_live_execution_fails_closed() -> None:
    result = attempt_private_live_execution()

    assert result.status == "disabled"
    assert result.reason == "public repository live execution is disabled"
    assert result.production_trading_enabled is False
    assert result.executable_order_intent is False


def test_private_live_gate_record_contains_no_endpoint_credentials_or_order_payload() -> None:
    record = attempt_private_live_execution().to_record()

    assert record["record_type"] == "private_live_execution_gate"
    assert record["status"] == "disabled"
    assert record["production_trading_enabled"] is False
    assert record["executable_order_intent"] is False
    assert "base_url" not in record
    assert "endpoint" not in record
    assert "credential" not in str(record).lower()
    assert "wallet" not in str(record).lower()
    assert "order_intent" not in record
    assert "order_payload" not in record
