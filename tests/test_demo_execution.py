from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from edmn_trader.core import ExecutionMode, RiskLimits
from edmn_trader.data.jsonl import read_jsonl_records
from edmn_trader.execution import (
    DemoExecutionConfig,
    DemoExecutionRequest,
    ExecutionAuditLogger,
    FakeDemoExecutionAdapter,
    decide_execution_risk,
    execute_demo_request,
)
from edmn_trader.research import DryRunOrderIntent


def test_live_disabled_blocks_place_cancel_and_modify_without_adapter_calls(tmp_path: Path) -> None:
    adapter = FakeDemoExecutionAdapter()
    log_path = tmp_path / "execution.jsonl"

    for action in ("place", "cancel", "modify"):
        result = execute_demo_request(
            _request(action=action, execution_mode=ExecutionMode.LIVE_DISABLED),
            config=DemoExecutionConfig(demo_opt_in=True),
            limits=_limits(),
            adapter=adapter,
            logger=ExecutionAuditLogger(log_path),
        )

        assert result.status == "rejected"
        assert result.risk_decision.limit_name == "execution_mode"

    assert adapter.calls == []
    records = list(read_jsonl_records(log_path))
    assert [record["requested_action"] for record in records] == ["place", "cancel", "modify"]
    assert all(record["result_status"] == "rejected" for record in records)
    assert all(record["adapter_called"] is False for record in records)


def test_missing_demo_opt_in_blocks_demo_execution_and_logs_attempt(tmp_path: Path) -> None:
    adapter = FakeDemoExecutionAdapter()
    log_path = tmp_path / "execution.jsonl"

    result = execute_demo_request(
        _request(),
        config=DemoExecutionConfig(demo_opt_in=False),
        limits=_limits(),
        adapter=adapter,
        logger=ExecutionAuditLogger(log_path),
    )

    assert result.status == "rejected"
    assert result.risk_decision.limit_name == "demo_opt_in"
    assert adapter.calls == []
    [record] = list(read_jsonl_records(log_path))
    assert record["risk_decision"]["approved"] is False
    assert record["error_reason"] == "explicit demo opt-in is required"
    assert record["demo_smoke_marker"] == "stage5_demo_execution_smoke"


def test_non_demo_endpoint_is_rejected_before_adapter_access(tmp_path: Path) -> None:
    adapter = FakeDemoExecutionAdapter()

    result = execute_demo_request(
        _request(),
        config=DemoExecutionConfig(
            base_url="https://api.elections.example.invalid/trade-api/v2",
            demo_opt_in=True,
        ),
        limits=_limits(),
        adapter=adapter,
        logger=ExecutionAuditLogger(tmp_path / "execution.jsonl"),
    )

    assert result.status == "rejected"
    assert result.risk_decision.limit_name == "base_url"
    assert adapter.calls == []


def test_risk_limits_block_size_price_notional_position_inventory_and_loss() -> None:
    cases = [
        (_request(quantity=Decimal("3.00")), "max_order_quantity"),
        (_request(price=Decimal("1.01")), "price_boundary"),
        (_request(price=Decimal("0.6000"), quantity=Decimal("2.00")), "max_notional"),
        (_request(current_position=Decimal("9.50"), quantity=Decimal("1.00")), "max_position_abs"),
        (_request(current_inventory=Decimal("-9.50"), side="sell"), "max_inventory_abs"),
        (_request(current_daily_loss=Decimal("5.01")), "max_daily_loss"),
    ]

    for request, limit_name in cases:
        decision = decide_execution_risk(
            request=request,
            config=DemoExecutionConfig(demo_opt_in=True),
            limits=_limits(),
        )

        assert decision.approved is False
        assert decision.limit_name == limit_name


def test_approved_demo_request_calls_fake_adapter_and_logs_execution(tmp_path: Path) -> None:
    adapter = FakeDemoExecutionAdapter()
    log_path = tmp_path / "execution.jsonl"

    result = execute_demo_request(
        _request(),
        config=DemoExecutionConfig(demo_opt_in=True),
        limits=_limits(),
        adapter=adapter,
        logger=ExecutionAuditLogger(log_path),
    )

    assert result.status == "executed"
    assert result.risk_decision.approved is True
    assert len(adapter.calls) == 1
    [(action, request)] = adapter.calls
    assert action == "place"
    assert request.instrument_id == "DEMO-EVENT-MARKET"

    [record] = list(read_jsonl_records(log_path))
    assert record["execution_mode"] == "demo"
    assert record["exchange"] == "kalshi_demo"
    assert record["ticker"] == "DEMO-EVENT-MARKET"
    assert record["requested_action"] == "place"
    assert record["order_intent"]["price"] == "0.4200"
    assert record["order_intent"]["quantity"] == "1.00"
    assert record["risk_decision"]["approved"] is True
    assert record["result_status"] == "executed"
    assert record["adapter_called"] is True
    assert record["adapter_result"]["adapter"] == "fake"
    assert record["demo_smoke_test"] is True


def test_dry_run_order_intent_converts_to_risk_gated_demo_request(tmp_path: Path) -> None:
    intent = DryRunOrderIntent(
        instrument_id="DEMO-EVENT-MARKET",
        side="buy",
        price=Decimal("0.4200"),
        quantity=Decimal("1.00"),
        reason="quote candidate",
    )
    request = DemoExecutionRequest.from_dry_run_intent(
        intent,
        execution_mode=ExecutionMode.DEMO,
    )

    result = execute_demo_request(
        request,
        config=DemoExecutionConfig(demo_opt_in=True),
        limits=_limits(),
        adapter=FakeDemoExecutionAdapter(),
        logger=ExecutionAuditLogger(tmp_path / "execution.jsonl"),
    )

    assert result.status == "executed"
    assert request.reason == "from dry-run intent: quote candidate"


def test_adapter_errors_are_logged_after_risk_approval(tmp_path: Path) -> None:
    adapter = FakeDemoExecutionAdapter(fail_actions={"place"})
    log_path = tmp_path / "execution.jsonl"

    result = execute_demo_request(
        _request(),
        config=DemoExecutionConfig(demo_opt_in=True),
        limits=_limits(),
        adapter=adapter,
        logger=ExecutionAuditLogger(log_path),
    )

    assert result.status == "adapter_error"
    assert result.risk_decision.approved is True
    [record] = list(read_jsonl_records(log_path))
    assert record["result_status"] == "adapter_error"
    assert record["adapter_called"] is True
    assert record["error_reason"] == "fake adapter place failure"


def _request(
    *,
    action: str = "place",
    side: str = "buy",
    price: Decimal = Decimal("0.4200"),
    quantity: Decimal = Decimal("1.00"),
    execution_mode: ExecutionMode = ExecutionMode.DEMO,
    current_position: Decimal = Decimal("0"),
    current_inventory: Decimal = Decimal("0"),
    current_daily_loss: Decimal = Decimal("0"),
) -> DemoExecutionRequest:
    return DemoExecutionRequest(
        instrument_id="DEMO-EVENT-MARKET",
        action=action,
        side=side,
        price=price,
        quantity=quantity,
        execution_mode=execution_mode,
        current_position=current_position,
        current_inventory=current_inventory,
        current_daily_loss=current_daily_loss,
        reason="test request",
    )


def _limits() -> RiskLimits:
    return RiskLimits(
        max_position_abs=Decimal("10"),
        max_order_quantity=Decimal("2.00"),
        max_notional=Decimal("1.00"),
        max_daily_loss=Decimal("5.00"),
    )
