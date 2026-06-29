from __future__ import annotations

from decimal import Decimal

import pytest

from edmn_trader.arb.paper_ledger import (
    replay_paper_ledger,
    write_paper_ledger_jsonl,
    write_paper_ledger_markdown,
)
from edmn_trader.data.jsonl import read_jsonl_records, write_jsonl_records
from edmn_trader.scripts.paper_ledger import run


def test_ledger_replays_order_fill_position_fee_and_settlement() -> None:
    state = replay_paper_ledger(
        [
            _proposal(),
            _fill(side="yes", price="0.4700", quantity="2", fee="0.0100"),
            _settlement(side="yes", quantity="1", payout_per_contract="1"),
        ]
    )

    assert state.paper_order_count == 1
    assert state.paper_fill_count == 1
    assert state.settlement_count == 1
    assert state.total_fees == Decimal("0.0100")
    assert state.realized_gross_pnl == Decimal("0.5300")
    assert state.realized_net_pnl == Decimal("0.5200")
    assert state.reconciliation_mismatch_count == 0
    assert state.source_hashes[0].candidate_hash == "c" * 64
    assert state.positions[0].quantity == Decimal("1")
    assert state.positions[0].average_price == Decimal("0.4700")


def test_ledger_reports_reconciliation_mismatches_without_executable_intents() -> None:
    state = replay_paper_ledger(
        [
            _proposal(),
            _fill(candidate_hash="d" * 64),
            _settlement(proposal_id="missing-proposal"),
        ]
    )

    assert state.reconciliation_mismatch_count == 2
    reasons = [mismatch.reason for mismatch in state.reconciliation_mismatches]
    assert reasons == ["candidate_hash_mismatch", "unknown_proposal"]
    record = state.to_record()
    assert record["executable_order_intent"] is False
    assert "order_intent" not in record
    assert "execution_mode" not in record


def test_ledger_rejects_malformed_local_events_safely() -> None:
    with pytest.raises(ValueError, match="quantity must be non-negative"):
        replay_paper_ledger([_proposal(), _fill(quantity="-1")])


def test_ledger_outputs_deterministic_jsonl_and_markdown(tmp_path) -> None:
    state = replay_paper_ledger([_proposal(), _fill(), _settlement()])
    jsonl_path = tmp_path / "ledger.jsonl"
    markdown_path = tmp_path / "ledger.md"

    write_paper_ledger_jsonl(jsonl_path, state)
    first = jsonl_path.read_text(encoding="utf-8")
    write_paper_ledger_jsonl(jsonl_path, state)

    assert jsonl_path.read_text(encoding="utf-8") == first
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["record_type"] == "paper_ledger_state"
    assert record["research_use"] == "paper_research_record_only"
    assert record["total_fees"] == "0.0100"

    write_paper_ledger_markdown(markdown_path, state)
    summary = markdown_path.read_text(encoding="utf-8")
    assert "paper ledger research records only" in summary
    assert "paper_order_count: 1" in summary
    assert "reconciliation_mismatch_count: 0" in summary


def test_ledger_cli_reads_local_jsonl_events_only(tmp_path) -> None:
    events_path = tmp_path / "events.jsonl"
    jsonl_path = tmp_path / "ledger.jsonl"
    markdown_path = tmp_path / "ledger.md"
    write_jsonl_records(events_path, [_proposal(), _fill(), _settlement()])

    state = run(
        events_path=events_path,
        jsonl_output_path=jsonl_path,
        markdown_output_path=markdown_path,
    )

    assert state.paper_fill_count == 1
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["record_type"] == "paper_ledger_state"
    assert "paper_fill_count: 1" in markdown_path.read_text(encoding="utf-8")


def test_decimal_precision_is_preserved() -> None:
    state = replay_paper_ledger(
        [
            _proposal(),
            _fill(price="0.3333", quantity="3", fee="0.0003"),
            _settlement(quantity="3", payout_per_contract="1"),
        ]
    )

    assert state.realized_gross_pnl == Decimal("2.0001")
    assert state.realized_net_pnl == Decimal("1.9998")


def _proposal() -> dict[str, object]:
    return {
        "record_type": "paper_complement_order_proposal",
        "research_use": "paper_research_record_only",
        "executable_order_intent": False,
        "proposal_id": "proposal-1",
        "venue": "kalshi_demo",
        "market_id": "DEMO-MARKET",
        "candidate_hash": "c" * 64,
        "simulation_hash": "s" * 64,
        "legs": [
            {"side": "yes", "limit_price": "0.4700", "quantity": "2"},
            {"side": "no", "limit_price": "0.4800", "quantity": "2"},
        ],
        "risk_preview": {
            "allowed_for_paper": False,
            "reasons": ["manual_approval_required"],
        },
    }


def _fill(
    *,
    proposal_id: str = "proposal-1",
    candidate_hash: str = "c" * 64,
    side: str = "yes",
    price: str = "0.4700",
    quantity: str = "2",
    fee: str = "0.0100",
) -> dict[str, object]:
    return {
        "record_type": "paper_fill",
        "research_use": "paper_research_record_only",
        "executable_order_intent": False,
        "proposal_id": proposal_id,
        "candidate_hash": candidate_hash,
        "simulation_hash": "s" * 64,
        "side": side,
        "price": price,
        "quantity": quantity,
        "fee": fee,
    }


def _settlement(
    *,
    proposal_id: str = "proposal-1",
    side: str = "yes",
    quantity: str = "2",
    payout_per_contract: str = "1",
) -> dict[str, object]:
    return {
        "record_type": "paper_settlement",
        "research_use": "paper_research_record_only",
        "executable_order_intent": False,
        "proposal_id": proposal_id,
        "side": side,
        "quantity": quantity,
        "payout_per_contract": payout_per_contract,
    }
