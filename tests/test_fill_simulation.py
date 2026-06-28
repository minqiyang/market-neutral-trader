from __future__ import annotations

import json
from decimal import Decimal

import pytest

from edmn_trader.arb import ComplementArbInput
from edmn_trader.arb.complement import compute_kalshi_complement_candidate
from edmn_trader.arb.fill_simulation import (
    FillPolicy,
    FillSimulationInput,
    simulate_taker_fill,
    write_fill_simulation_jsonl,
    write_fill_simulation_markdown,
)
from edmn_trader.scripts.simulate_taker_fill import run


def test_fok_simulation_fills_both_legs_when_depth_is_available() -> None:
    result = simulate_taker_fill(
        FillSimulationInput(
            candidate=_candidate(),
            policy=FillPolicy.FILL_OR_KILL,
            target_size=Decimal("5"),
            yes_available_size=Decimal("5"),
            no_available_size=Decimal("5"),
        )
    )

    assert result.filled_yes_size == Decimal("5")
    assert result.filled_no_size == Decimal("5")
    assert result.completed_pair_size == Decimal("5")
    assert result.failed_leg_quantity == Decimal("0")
    assert result.simulated_net_edge_per_pair == Decimal("0.0500")
    assert result.record_type == "offline_taker_fill_simulation"
    assert result.executable_order_intent is False
    assert "manual_review_required" in result.flags


def test_fok_simulation_blocks_when_one_leg_lacks_depth() -> None:
    result = simulate_taker_fill(
        FillSimulationInput(
            candidate=_candidate(),
            policy=FillPolicy.FILL_OR_KILL,
            target_size=Decimal("5"),
            yes_available_size=Decimal("5"),
            no_available_size=Decimal("4"),
        )
    )

    assert result.filled_yes_size == Decimal("0")
    assert result.filled_no_size == Decimal("0")
    assert result.completed_pair_size == Decimal("0")
    assert result.failed_leg_quantity == Decimal("0")
    assert "blocked_by_fok_depth" in result.flags


def test_ioc_simulation_reports_partial_fill_and_failed_leg_reserve() -> None:
    result = simulate_taker_fill(
        FillSimulationInput(
            candidate=_candidate(),
            policy=FillPolicy.IMMEDIATE_OR_CANCEL,
            target_size=Decimal("5"),
            yes_available_size=Decimal("5"),
            no_available_size=Decimal("3"),
            failed_leg_reserve_per_contract=Decimal("0.0200"),
        )
    )

    assert result.filled_yes_size == Decimal("5")
    assert result.filled_no_size == Decimal("3")
    assert result.completed_pair_size == Decimal("3")
    assert result.failed_leg_quantity == Decimal("2")
    assert result.failed_leg_reserve_total == Decimal("0.0400")
    assert result.simulated_total_net_edge == Decimal("0.0900")
    assert "partial_fill" in result.flags
    assert "failed_leg_reserve_applied" in result.flags


def test_slippage_and_latency_reduce_simulated_edge() -> None:
    result = simulate_taker_fill(
        FillSimulationInput(
            candidate=_candidate(),
            policy=FillPolicy.FILL_OR_KILL,
            target_size=Decimal("5"),
            yes_available_size=Decimal("5"),
            no_available_size=Decimal("5"),
            yes_slippage_per_contract=Decimal("0.0100"),
            no_slippage_per_contract=Decimal("0.0050"),
            latency_shock_per_contract=Decimal("0.0050"),
        )
    )

    assert result.simulated_net_edge_per_pair == Decimal("0.0300")
    assert result.simulated_total_net_edge == Decimal("0.1500")
    assert "slippage_applied" in result.flags
    assert "latency_shock_applied" in result.flags


def test_simulation_output_is_deterministic_and_not_executable(tmp_path) -> None:
    result = simulate_taker_fill(
        FillSimulationInput(
            candidate=_candidate(),
            policy=FillPolicy.FILL_OR_KILL,
            target_size=Decimal("2"),
            yes_available_size=Decimal("2"),
            no_available_size=Decimal("2"),
        )
    )
    jsonl_path = tmp_path / "fills.jsonl"
    markdown_path = tmp_path / "fills.md"

    write_fill_simulation_jsonl(jsonl_path, [result])
    first = jsonl_path.read_text(encoding="utf-8")
    write_fill_simulation_jsonl(jsonl_path, [result])

    assert jsonl_path.read_text(encoding="utf-8") == first
    payload = json.loads(first)
    assert payload["executable_order_intent"] is False
    assert "order_intent" not in payload
    assert "execution_mode" not in payload

    write_fill_simulation_markdown(markdown_path, [result])
    summary = markdown_path.read_text(encoding="utf-8")
    assert "audit/paper fill simulation records only" in summary
    assert "simulations: 1" in summary


def test_cli_runs_from_local_fixture_only(tmp_path) -> None:
    fixture = tmp_path / "scenario.json"
    output = tmp_path / "fills.jsonl"
    markdown = tmp_path / "fills.md"
    fixture.write_text(
        json.dumps(
            {
                "venue": "kalshi_demo",
                "market_id": "DEMO-MARKET",
                "best_yes_bid": "0.5300",
                "best_no_bid": "0.5200",
                "yes_bid_size": "5",
                "no_bid_size": "5",
                "estimated_fee_per_contract": "0",
                "policy": "fok",
                "target_size": "5",
                "yes_available_size": "5",
                "no_available_size": "5",
            }
        ),
        encoding="utf-8",
    )

    results = run(input_path=fixture, jsonl_output_path=output, markdown_output_path=markdown)

    assert len(results) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["record_type"] == (
        "offline_taker_fill_simulation"
    )
    assert "simulations: 1" in markdown.read_text(encoding="utf-8")


def test_negative_decimal_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="target_size must be non-negative"):
        FillSimulationInput(
            candidate=_candidate(),
            policy=FillPolicy.FILL_OR_KILL,
            target_size=Decimal("-1"),
            yes_available_size=Decimal("5"),
            no_available_size=Decimal("5"),
        )


def _candidate():
    return compute_kalshi_complement_candidate(
        ComplementArbInput(
            venue="kalshi_demo",
            market_id="DEMO-MARKET",
            best_yes_bid=Decimal("0.5300"),
            best_no_bid=Decimal("0.5200"),
            yes_bid_size=Decimal("5"),
            no_bid_size=Decimal("5"),
            estimated_fee_per_contract=Decimal("0"),
        )
    )
