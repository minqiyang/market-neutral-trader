"""Run a local fake-adapter Stage 5 demo execution smoke check."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from edmn_trader.adapters.kalshi.client import KALSHI_DEMO_REST_BASE_URL
from edmn_trader.core import ExecutionMode, RiskLimits
from edmn_trader.execution import (
    DemoExecutionConfig,
    DemoExecutionRequest,
    ExecutionAuditLogger,
    FakeDemoExecutionAdapter,
    execute_demo_request,
)

DEFAULT_LOG_OUTPUT = Path("/tmp/edmn_stage5_demo_execution_smoke.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-opt-in",
        action="store_true",
        help="Allow the fake adapter to receive a risk-approved DEMO request.",
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_LOG_OUTPUT)
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in ExecutionMode],
        default=ExecutionMode.DEMO.value,
        help="Execution mode to risk-check.",
    )
    parser.add_argument(
        "--base-url",
        default=KALSHI_DEMO_REST_BASE_URL,
        help="Demo base URL. Any non-demo URL is rejected before adapter access.",
    )
    parser.add_argument("--action", choices=["place", "cancel", "modify"], default="place")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--ticker", default="DEMO-EVENT-MARKET")
    parser.add_argument("--price", default="0.4200")
    parser.add_argument("--quantity", default="1.00")
    parser.add_argument("--current-position", default="0")
    parser.add_argument("--current-inventory", default="0")
    args = parser.parse_args()

    request = DemoExecutionRequest(
        instrument_id=args.ticker,
        action=args.action,
        side=args.side,
        price=Decimal(args.price),
        quantity=Decimal(args.quantity),
        execution_mode=ExecutionMode(args.mode),
        current_position=Decimal(args.current_position),
        current_inventory=Decimal(args.current_inventory),
        reason="local Stage 5 fake-adapter smoke request",
    )
    result = execute_demo_request(
        request,
        config=DemoExecutionConfig(base_url=args.base_url, demo_opt_in=args.demo_opt_in),
        limits=RiskLimits(
            max_position_abs=Decimal("10"),
            max_order_quantity=Decimal("2.00"),
            max_notional=Decimal("1.00"),
            max_daily_loss=Decimal("5.00"),
        ),
        adapter=FakeDemoExecutionAdapter(),
        logger=ExecutionAuditLogger(args.log_output),
    )

    print(f"status={result.status}")
    print(f"risk_approved={result.risk_decision.approved}")
    print(f"reason={result.risk_decision.reason}")
    print(f"log_output={args.log_output}")
    print("limitations=local fake adapter only; no network, credentials, or production trading")


if __name__ == "__main__":
    main()
