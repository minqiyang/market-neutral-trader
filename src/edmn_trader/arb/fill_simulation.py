"""Offline taker fill, slippage, and failed-leg simulation records."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from edmn_trader.arb.complement import ComplementArbCandidate
from edmn_trader.core.models import ZERO
from edmn_trader.data.jsonl import write_jsonl_records


class FillPolicy(StrEnum):
    """Offline fill policy assumption for two-leg taker simulation."""

    FILL_OR_KILL = "fok"
    IMMEDIATE_OR_CANCEL = "ioc"


@dataclass(frozen=True, slots=True)
class FillSimulationInput:
    """Explicit offline assumptions for one two-leg taker fill simulation."""

    candidate: ComplementArbCandidate
    policy: FillPolicy
    target_size: Decimal
    yes_available_size: Decimal
    no_available_size: Decimal
    yes_slippage_per_contract: Decimal = ZERO
    no_slippage_per_contract: Decimal = ZERO
    latency_shock_per_contract: Decimal = ZERO
    failed_leg_reserve_per_contract: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ComplementArbCandidate):
            msg = "candidate must be a ComplementArbCandidate"
            raise TypeError(msg)
        if not isinstance(self.policy, FillPolicy):
            msg = "policy must be a FillPolicy"
            raise TypeError(msg)
        for field_name in (
            "target_size",
            "yes_available_size",
            "no_available_size",
            "yes_slippage_per_contract",
            "no_slippage_per_contract",
            "latency_shock_per_contract",
        ):
            _require_non_negative_decimal(getattr(self, field_name), field_name=field_name)
        if self.failed_leg_reserve_per_contract is not None:
            _require_non_negative_decimal(
                self.failed_leg_reserve_per_contract,
                field_name="failed_leg_reserve_per_contract",
            )


@dataclass(frozen=True, slots=True)
class FillSimulationResult:
    """Deterministic offline fill simulation output; never an order intent."""

    venue: str
    market_id: str
    policy: FillPolicy
    target_size: Decimal
    filled_yes_size: Decimal
    filled_no_size: Decimal
    completed_pair_size: Decimal
    failed_leg_quantity: Decimal
    yes_fill_price: Decimal
    no_fill_price: Decimal
    simulated_net_edge_per_pair: Decimal
    simulated_total_net_edge: Decimal
    failed_leg_reserve_total: Decimal
    flags: tuple[str, ...]
    record_type: str = "offline_taker_fill_simulation"
    executable_order_intent: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "executable_order_intent": self.executable_order_intent,
            "venue": self.venue,
            "market_id": self.market_id,
            "policy": self.policy.value,
            "target_size": str(self.target_size),
            "filled_yes_size": str(self.filled_yes_size),
            "filled_no_size": str(self.filled_no_size),
            "completed_pair_size": str(self.completed_pair_size),
            "failed_leg_quantity": str(self.failed_leg_quantity),
            "yes_fill_price": str(self.yes_fill_price),
            "no_fill_price": str(self.no_fill_price),
            "simulated_net_edge_per_pair": str(self.simulated_net_edge_per_pair),
            "simulated_total_net_edge": str(self.simulated_total_net_edge),
            "failed_leg_reserve_total": str(self.failed_leg_reserve_total),
            "flags": list(self.flags),
        }


def simulate_taker_fill(simulation: FillSimulationInput) -> FillSimulationResult:
    """Simulate two-leg taker fill assumptions from explicit offline inputs."""

    filled_yes, filled_no = _filled_sizes(simulation)
    completed_pair_size = min(filled_yes, filled_no)
    failed_leg_quantity = abs(filled_yes - filled_no)
    reserve_per_contract = (
        simulation.failed_leg_reserve_per_contract
        if simulation.failed_leg_reserve_per_contract is not None
        else simulation.candidate.failed_leg_reserve_per_contract
    )
    simulated_net_edge_per_pair = (
        simulation.candidate.gross_edge_per_contract
        - _candidate_fee(simulation.candidate)
        - simulation.yes_slippage_per_contract
        - simulation.no_slippage_per_contract
        - simulation.latency_shock_per_contract
        - reserve_per_contract
    )
    return FillSimulationResult(
        venue=simulation.candidate.venue,
        market_id=simulation.candidate.market_id,
        policy=simulation.policy,
        target_size=simulation.target_size,
        filled_yes_size=filled_yes,
        filled_no_size=filled_no,
        completed_pair_size=completed_pair_size,
        failed_leg_quantity=failed_leg_quantity,
        yes_fill_price=simulation.candidate.yes_ask + simulation.yes_slippage_per_contract,
        no_fill_price=simulation.candidate.no_ask + simulation.no_slippage_per_contract,
        simulated_net_edge_per_pair=simulated_net_edge_per_pair,
        simulated_total_net_edge=simulated_net_edge_per_pair * completed_pair_size,
        failed_leg_reserve_total=reserve_per_contract * failed_leg_quantity,
        flags=_result_flags(
            simulation=simulation,
            filled_yes=filled_yes,
            filled_no=filled_no,
            failed_leg_quantity=failed_leg_quantity,
            reserve_per_contract=reserve_per_contract,
        ),
    )


def write_fill_simulation_jsonl(
    path: Path,
    results: Iterable[FillSimulationResult],
) -> None:
    write_jsonl_records(path, (result.to_record() for result in results))


def write_fill_simulation_markdown(
    path: Path,
    results: Iterable[FillSimulationResult],
) -> None:
    records = tuple(results)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown_summary(records), encoding="utf-8")


def _filled_sizes(simulation: FillSimulationInput) -> tuple[Decimal, Decimal]:
    if (
        simulation.policy is FillPolicy.FILL_OR_KILL
        and (
            simulation.yes_available_size < simulation.target_size
            or simulation.no_available_size < simulation.target_size
        )
    ):
        return ZERO, ZERO
    return (
        min(simulation.target_size, simulation.yes_available_size),
        min(simulation.target_size, simulation.no_available_size),
    )


def _result_flags(
    *,
    simulation: FillSimulationInput,
    filled_yes: Decimal,
    filled_no: Decimal,
    failed_leg_quantity: Decimal,
    reserve_per_contract: Decimal,
) -> tuple[str, ...]:
    flags = ["manual_review_required", "not_trade_recommendation"]
    if filled_yes == ZERO and filled_no == ZERO and simulation.target_size > ZERO:
        flags.append("blocked_by_fok_depth")
    if failed_leg_quantity > ZERO:
        flags.append("partial_fill")
    if reserve_per_contract > ZERO:
        flags.append("failed_leg_reserve_applied")
    if (
        simulation.yes_slippage_per_contract > ZERO
        or simulation.no_slippage_per_contract > ZERO
    ):
        flags.append("slippage_applied")
    if simulation.latency_shock_per_contract > ZERO:
        flags.append("latency_shock_applied")
    return tuple(flags)


def _candidate_fee(candidate: ComplementArbCandidate) -> Decimal:
    return candidate.estimated_fee_per_contract or ZERO


def _markdown_summary(results: tuple[FillSimulationResult, ...]) -> str:
    blocked_count = sum("blocked_by_fok_depth" in result.flags for result in results)
    partial_count = sum("partial_fill" in result.flags for result in results)
    return "\n".join(
        [
            "# Offline Taker Fill Simulation Summary",
            "",
            "Records are audit/paper fill simulation records only, not executable order intents.",
            "",
            f"- simulations: {len(results)}",
            f"- partial_fill_count: {partial_count}",
            f"- blocked_by_fok_depth_count: {blocked_count}",
            "",
        ]
    )


def _require_non_negative_decimal(value: Decimal, *, field_name: str) -> None:
    if not isinstance(value, Decimal):
        msg = f"{field_name} must be a Decimal"
        raise TypeError(msg)
    if value < ZERO:
        msg = f"{field_name} must be non-negative"
        raise ValueError(msg)
