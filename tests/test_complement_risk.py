from __future__ import annotations

import json
from decimal import Decimal

from edmn_trader.arb.risk import (
    ComplementRiskInput,
    evaluate_complement_risk,
    write_complement_risk_jsonl,
    write_complement_risk_markdown,
)
from edmn_trader.data.jsonl import read_jsonl_records
from edmn_trader.scripts.complement_risk import run


def test_risk_engine_blocks_data_fee_edge_ledger_and_kill_switch_risks() -> None:
    decision = evaluate_complement_risk(
        _risk_input(
            data_quality_flags=("stale_book", "sequence_gap"),
            fee_status="missing",
            net_edge_per_contract=Decimal("0.0100"),
            minimum_net_edge_per_contract=Decimal("0.0200"),
            reconciliation_mismatch_count=1,
            kill_switch_active=True,
        )
    )

    assert decision.decision == "reject"
    assert decision.approved is False
    assert decision.manual_approval_required is True
    assert decision.reasons == (
        "manual_approval_required",
        "stale_data",
        "data_gap",
        "missing_fee_model",
        "insufficient_net_edge",
        "reconciliation_mismatch",
        "kill_switch_active",
    )


def test_risk_engine_blocks_exposure_open_order_and_daily_loss_breaches() -> None:
    decision = evaluate_complement_risk(
        _risk_input(
            projected_exposure=Decimal("10.0001"),
            max_exposure=Decimal("10"),
            open_order_count=3,
            max_open_orders=2,
            daily_loss=Decimal("2.0001"),
            max_daily_loss=Decimal("2"),
        )
    )

    assert decision.decision == "reject"
    assert "exposure_limit_breach" in decision.reasons
    assert "open_order_limit_breach" in decision.reasons
    assert "daily_loss_limit_breach" in decision.reasons


def test_clear_risk_check_still_requires_manual_approval() -> None:
    decision = evaluate_complement_risk(_risk_input())

    assert decision.decision == "manual_review_required"
    assert decision.approved is False
    assert decision.manual_approval_required is True
    assert decision.reasons == ("manual_approval_required",)
    record = decision.to_record()
    assert record["executable_order_intent"] is False
    assert "order_intent" not in record
    assert "execution_mode" not in record


def test_risk_engine_preserves_decimal_precision() -> None:
    decision = evaluate_complement_risk(
        _risk_input(
            projected_exposure=Decimal("0.123456789"),
            max_exposure=Decimal("1"),
        )
    )

    assert decision.projected_exposure == Decimal("0.123456789")
    assert decision.to_record()["projected_exposure"] == "0.123456789"


def test_risk_output_is_deterministic_jsonl_and_markdown(tmp_path) -> None:
    decisions = [evaluate_complement_risk(_risk_input())]
    jsonl_path = tmp_path / "risk.jsonl"
    markdown_path = tmp_path / "risk.md"

    write_complement_risk_jsonl(jsonl_path, decisions)
    first = jsonl_path.read_text(encoding="utf-8")
    write_complement_risk_jsonl(jsonl_path, decisions)

    assert jsonl_path.read_text(encoding="utf-8") == first
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["record_type"] == "complement_risk_decision_v2"
    assert record["research_use"] == "paper_risk_research_record_only"

    write_complement_risk_markdown(markdown_path, decisions)
    summary = markdown_path.read_text(encoding="utf-8")
    assert "paper risk research records only" in summary
    assert "manual_review_required_count: 1" in summary


def test_risk_cli_reads_local_fixture_only(tmp_path) -> None:
    fixture = tmp_path / "risk_checks.json"
    jsonl_path = tmp_path / "risk.jsonl"
    markdown_path = tmp_path / "risk.md"
    fixture.write_text(json.dumps({"checks": [_risk_input_record()]}), encoding="utf-8")

    decisions = run(
        input_path=fixture,
        jsonl_output_path=jsonl_path,
        markdown_output_path=markdown_path,
    )

    assert len(decisions) == 1
    [record] = list(read_jsonl_records(jsonl_path))
    assert record["decision"] == "manual_review_required"
    assert "risk_decision_count: 1" in markdown_path.read_text(encoding="utf-8")


def test_negative_risk_limits_are_rejected() -> None:
    try:
        ComplementRiskInput(
            proposal_id="proposal-1",
            candidate_hash="c" * 64,
            fee_status="supplied",
            net_edge_per_contract=Decimal("0.0500"),
            minimum_net_edge_per_contract=Decimal("0.0100"),
            projected_exposure=Decimal("-1"),
            max_exposure=Decimal("10"),
            open_order_count=0,
            max_open_orders=1,
            daily_loss=Decimal("0"),
            max_daily_loss=Decimal("1"),
        )
    except ValueError as exc:
        assert "projected_exposure must be non-negative" in str(exc)
    else:  # pragma: no cover - keeps the assertion message explicit
        raise AssertionError("negative projected exposure should fail")


def _risk_input(
    *,
    data_quality_flags: tuple[str, ...] = (),
    fee_status: str = "supplied",
    net_edge_per_contract: Decimal = Decimal("0.0500"),
    minimum_net_edge_per_contract: Decimal = Decimal("0.0100"),
    projected_exposure: Decimal = Decimal("5"),
    max_exposure: Decimal = Decimal("10"),
    open_order_count: int = 1,
    max_open_orders: int = 2,
    daily_loss: Decimal = Decimal("0"),
    max_daily_loss: Decimal = Decimal("1"),
    reconciliation_mismatch_count: int = 0,
    kill_switch_active: bool = False,
) -> ComplementRiskInput:
    return ComplementRiskInput(
        proposal_id="proposal-1",
        candidate_hash="c" * 64,
        fee_status=fee_status,
        net_edge_per_contract=net_edge_per_contract,
        minimum_net_edge_per_contract=minimum_net_edge_per_contract,
        data_quality_flags=data_quality_flags,
        projected_exposure=projected_exposure,
        max_exposure=max_exposure,
        open_order_count=open_order_count,
        max_open_orders=max_open_orders,
        daily_loss=daily_loss,
        max_daily_loss=max_daily_loss,
        reconciliation_mismatch_count=reconciliation_mismatch_count,
        kill_switch_active=kill_switch_active,
    )


def _risk_input_record() -> dict[str, object]:
    return {
        "proposal_id": "proposal-1",
        "candidate_hash": "c" * 64,
        "fee_status": "supplied",
        "net_edge_per_contract": "0.0500",
        "minimum_net_edge_per_contract": "0.0100",
        "data_quality_flags": [],
        "projected_exposure": "5",
        "max_exposure": "10",
        "open_order_count": 1,
        "max_open_orders": 2,
        "daily_loss": "0",
        "max_daily_loss": "1",
        "reconciliation_mismatch_count": 0,
        "kill_switch_active": False,
    }
