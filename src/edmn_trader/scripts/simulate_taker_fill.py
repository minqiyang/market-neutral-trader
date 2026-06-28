"""Run offline taker fill, slippage, and failed-leg simulations."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from edmn_trader.arb.complement import (
    ComplementArbInput,
    compute_kalshi_complement_candidate,
)
from edmn_trader.arb.fill_simulation import (
    FillPolicy,
    FillSimulationInput,
    FillSimulationResult,
    simulate_taker_fill,
    write_fill_simulation_jsonl,
    write_fill_simulation_markdown,
)


def run(
    *,
    input_path: Path,
    jsonl_output_path: Path,
    markdown_output_path: Path,
) -> tuple[FillSimulationResult, ...]:
    scenarios = _read_scenarios(input_path)
    results = tuple(simulate_taker_fill(_scenario_to_input(scenario)) for scenario in scenarios)
    write_fill_simulation_jsonl(jsonl_output_path, results)
    write_fill_simulation_markdown(markdown_output_path, results)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Local simulation fixture JSON.")
    parser.add_argument("--jsonl-output", required=True, type=Path, help="Simulation JSONL output.")
    parser.add_argument(
        "--markdown-output",
        required=True,
        type=Path,
        help="Simulation Markdown summary output.",
    )
    args = parser.parse_args()

    results = run(
        input_path=args.input,
        jsonl_output_path=args.jsonl_output,
        markdown_output_path=args.markdown_output,
    )
    print(f"wrote {len(results)} offline fill simulation record(s)")


def _read_scenarios(path: Path) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("scenarios"), list):
        scenarios = payload["scenarios"]
    else:
        scenarios = [payload]
    if not all(isinstance(item, dict) for item in scenarios):
        msg = "simulation fixture scenarios must be objects"
        raise ValueError(msg)
    return tuple(scenarios)


def _scenario_to_input(scenario: dict[str, Any]) -> FillSimulationInput:
    candidate = compute_kalshi_complement_candidate(
        ComplementArbInput(
            venue=_expect_str(scenario, "venue"),
            market_id=_expect_str(scenario, "market_id"),
            best_yes_bid=_expect_decimal(scenario, "best_yes_bid"),
            best_no_bid=_expect_decimal(scenario, "best_no_bid"),
            yes_bid_size=_expect_decimal(scenario, "yes_bid_size"),
            no_bid_size=_expect_decimal(scenario, "no_bid_size"),
            estimated_fee_per_contract=_optional_decimal(
                scenario,
                "estimated_fee_per_contract",
                default=Decimal("0"),
            ),
            estimated_slippage_per_contract=_optional_decimal(
                scenario,
                "estimated_slippage_per_contract",
                default=Decimal("0"),
            ),
            failed_leg_reserve_per_contract=_optional_decimal(
                scenario,
                "candidate_failed_leg_reserve_per_contract",
                default=Decimal("0"),
            ),
        )
    )
    return FillSimulationInput(
        candidate=candidate,
        policy=FillPolicy(_expect_str(scenario, "policy")),
        target_size=_expect_decimal(scenario, "target_size"),
        yes_available_size=_expect_decimal(scenario, "yes_available_size"),
        no_available_size=_expect_decimal(scenario, "no_available_size"),
        yes_slippage_per_contract=_optional_decimal(
            scenario,
            "yes_slippage_per_contract",
            default=Decimal("0"),
        ),
        no_slippage_per_contract=_optional_decimal(
            scenario,
            "no_slippage_per_contract",
            default=Decimal("0"),
        ),
        latency_shock_per_contract=_optional_decimal(
            scenario,
            "latency_shock_per_contract",
            default=Decimal("0"),
        ),
        failed_leg_reserve_per_contract=_optional_decimal(
            scenario,
            "failed_leg_reserve_per_contract",
            default=None,
        ),
    )


def _expect_str(record: dict[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return value


def _expect_decimal(record: dict[str, Any], field_name: str) -> Decimal:
    value = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string"
        raise ValueError(msg)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ValueError(msg) from exc


def _optional_decimal(
    record: dict[str, Any],
    field_name: str,
    *,
    default: Decimal | None,
) -> Decimal | None:
    if field_name not in record:
        return default
    value = record[field_name]
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string when present"
        raise ValueError(msg)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ValueError(msg) from exc


if __name__ == "__main__":
    main()
