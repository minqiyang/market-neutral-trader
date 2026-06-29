from __future__ import annotations

import json
from decimal import Decimal

from edmn_trader.arb.paper_engine import (
    propose_paper_order,
    write_paper_order_markdown,
    write_paper_order_proposals,
)
from edmn_trader.data.jsonl import read_jsonl_records, write_jsonl_records
from edmn_trader.scripts.paper_complement_engine import run


def test_paper_engine_preserves_candidate_and_simulation_hashes() -> None:
    proposal = propose_paper_order(_candidate_record(), _simulation_record())

    assert proposal.record_type == "paper_complement_order_proposal"
    assert proposal.executable_order_intent is False
    assert len(proposal.candidate_hash) == 64
    assert len(proposal.simulation_hash) == 64
    assert proposal.proposal_id == propose_paper_order(
        _candidate_record(),
        _simulation_record(),
    ).proposal_id
    assert proposal.legs[0].side == "yes"
    assert proposal.legs[0].limit_price == Decimal("0.4700")
    assert proposal.legs[1].side == "no"
    assert proposal.legs[1].quantity == Decimal("5")
    assert proposal.risk_preview.allowed_for_paper is False
    assert "manual_approval_required" in proposal.risk_preview.reasons


def test_paper_engine_blocks_non_paper_candidate() -> None:
    candidate = {**_candidate_record(), "decision": "audit_only"}

    proposal = propose_paper_order(candidate, _simulation_record())

    assert proposal.risk_preview.allowed_for_paper is False
    assert "candidate_not_paper_candidate" in proposal.risk_preview.reasons


def test_paper_engine_blocks_missing_completed_pair() -> None:
    simulation = {**_simulation_record(), "completed_pair_size": "0"}

    proposal = propose_paper_order(_candidate_record(), simulation)

    assert proposal.legs == ()
    assert "simulation_not_complete" in proposal.risk_preview.reasons


def test_paper_engine_outputs_deterministic_jsonl_and_markdown(tmp_path) -> None:
    proposal = propose_paper_order(_candidate_record(), _simulation_record())
    jsonl_path = tmp_path / "paper_orders.jsonl"
    markdown_path = tmp_path / "paper_orders.md"

    write_paper_order_proposals(jsonl_path, [proposal])
    first = jsonl_path.read_text(encoding="utf-8")
    write_paper_order_proposals(jsonl_path, [proposal])

    assert jsonl_path.read_text(encoding="utf-8") == first
    record = json.loads(first)
    assert record["executable_order_intent"] is False
    assert "order_intent" not in record
    assert record["candidate_hash"] == proposal.candidate_hash

    write_paper_order_markdown(markdown_path, [proposal])
    summary = markdown_path.read_text(encoding="utf-8")
    assert "paper research proposals only" in summary
    assert "proposals: 1" in summary


def test_paper_engine_cli_pairs_candidate_and_simulation_jsonl(tmp_path) -> None:
    candidates = tmp_path / "candidates.jsonl"
    simulations = tmp_path / "simulations.jsonl"
    output = tmp_path / "paper_orders.jsonl"
    markdown = tmp_path / "paper_orders.md"
    write_jsonl_records(candidates, [_candidate_record()])
    write_jsonl_records(simulations, [_simulation_record()])

    proposals = run(
        candidates_path=candidates,
        simulations_path=simulations,
        jsonl_output_path=output,
        markdown_output_path=markdown,
    )

    assert len(proposals) == 1
    [record] = list(read_jsonl_records(output))
    assert record["record_type"] == "paper_complement_order_proposal"
    assert record["research_use"] == "paper_research_record_only"
    assert "proposals: 1" in markdown.read_text(encoding="utf-8")


def _candidate_record() -> dict[str, object]:
    return {
        "record_type": "offline_complement_research_candidate",
        "venue": "kalshi_demo",
        "market_id": "DEMO-MARKET",
        "decision": "paper_candidate",
        "candidate_size": "5",
        "fee_status": "supplied",
        "net_edge_per_contract": "0.0500",
        "total_estimated_net_edge": "0.2500",
        "flags": ["manual_review_required", "crossed_book"],
        "executable_order_intent": False,
    }


def _simulation_record() -> dict[str, object]:
    return {
        "record_type": "offline_taker_fill_simulation",
        "venue": "kalshi_demo",
        "market_id": "DEMO-MARKET",
        "policy": "fok",
        "completed_pair_size": "5",
        "failed_leg_quantity": "0",
        "yes_fill_price": "0.4700",
        "no_fill_price": "0.4800",
        "simulated_net_edge_per_pair": "0.0500",
        "simulated_total_net_edge": "0.2500",
        "flags": ["manual_review_required"],
        "executable_order_intent": False,
    }
