import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from edmn_trader.arb.scanner import (
    render_markdown_summary,
    scan_fixture_file,
    scan_snapshot_jsonl_file,
    write_jsonl_report,
    write_markdown_summary,
)
from edmn_trader.core.models import NormalizedOrderBook, OrderBookLevel
from edmn_trader.data.snapshots import MarketDataSnapshot, write_snapshots


def test_scanner_finds_no_candidate_when_no_complement_edge_exists(tmp_path) -> None:
    fixture = tmp_path / "no_edge.json"
    fixture.write_text(
        json.dumps(
            {
                "source": "unit-fixture",
                "markets": [
                    _book(
                        best_yes_bid="0.4800",
                        best_no_bid="0.4900",
                        fee_status="supplied",
                        fee_per_contract="0.0100",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    report = scan_fixture_file(fixture)

    assert report.candidate_count == 1
    assert report.paper_candidate_count == 0
    assert report.audit_only_count == 0
    assert report.reject_count == 1
    assert report.rejection_reason_counts["no_complement_edge"] == 1


def test_scanner_reports_audit_and_reject_counts(tmp_path) -> None:
    fixture = tmp_path / "mixed.json"
    fixture.write_text(
        json.dumps(
            {
                "source": "mixed-fixture",
                "fee_status": "missing",
                "markets": [
                    _book(best_yes_bid="0.5300", best_no_bid="0.5200"),
                    _book(best_yes_bid="0.4800", best_no_bid="0.4900"),
                ],
            }
        ),
        encoding="utf-8",
    )

    report = scan_fixture_file(fixture)

    assert report.candidate_count == 2
    assert report.audit_only_count == 1
    assert report.reject_count == 1
    assert report.paper_candidate_count == 0
    assert report.rejection_reason_counts["missing_fee_model"] == 2
    assert report.rejection_reason_counts["no_complement_edge"] == 1


@pytest.mark.parametrize("fee_status", ["missing", "unknown"])
def test_scanner_blocks_paper_candidate_when_fee_model_is_missing_or_unknown(
    tmp_path,
    fee_status,
) -> None:
    fixture = tmp_path / f"{fee_status}.json"
    fixture.write_text(
        json.dumps(
            {
                "source": "fee-fixture",
                "markets": [
                    _book(
                        best_yes_bid="0.5300",
                        best_no_bid="0.5200",
                        fee_status=fee_status,
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    report = scan_fixture_file(fixture)
    record = report.records[0]

    assert report.paper_candidate_count == 0
    assert report.audit_only_count == 1
    assert record.candidate.fee_status.value == fee_status
    assert "manual_review_required" in record.candidate.flags


def test_scanner_emits_deterministic_jsonl(tmp_path) -> None:
    fixture = tmp_path / "candidate.json"
    output = tmp_path / "candidates.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "source": "candidate-fixture",
                "markets": [
                    _book(
                        best_yes_bid="0.5300",
                        best_no_bid="0.5200",
                        fee_status="supplied",
                        fee_per_contract="0.0100",
                        estimated_slippage_per_contract="0.0050",
                        failed_leg_reserve_per_contract="0.0050",
                        minimum_net_edge_per_contract="0.0100",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    report = scan_fixture_file(fixture)

    write_jsonl_report(output, report)

    first = output.read_text(encoding="utf-8")
    write_jsonl_report(output, report)
    assert output.read_text(encoding="utf-8") == first
    payload = json.loads(first)
    assert payload["decision"] == "paper_candidate"
    assert payload["record_type"] == "offline_complement_research_candidate"
    assert payload["executable_order_intent"] is False
    assert "manual_review_required" in payload["flags"]


def test_scanner_emits_deterministic_markdown_summary(tmp_path) -> None:
    fixture = tmp_path / "summary.json"
    output = tmp_path / "summary.md"
    fixture.write_text(
        json.dumps(
            {
                "source": "summary-fixture",
                "markets": [
                    _book(
                        best_yes_bid="0.5300",
                        best_no_bid="0.5200",
                        fee_status="unknown",
                        data_quality_flags=["stale_book"],
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    report = scan_fixture_file(fixture)

    write_markdown_summary(output, report)

    first = output.read_text(encoding="utf-8")
    assert output.read_text(encoding="utf-8") == render_markdown_summary(report)
    write_markdown_summary(output, report)
    assert output.read_text(encoding="utf-8") == first
    assert "- Input source: `summary-fixture`" in first
    assert "- audit_only count: 1" in first
    assert "- unknown fee count: 1" in first
    assert "- stale_book: 1" in first


def test_invalid_input_is_rejected_safely(tmp_path) -> None:
    fixture = tmp_path / "invalid.json"
    fixture.write_text(
        json.dumps(
            {
                "source": "invalid-fixture",
                "markets": [_book(best_yes_bid="0.5300", best_no_bid=0.5200)],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="best_no_bid must be a decimal string"):
        scan_fixture_file(fixture)


def test_scanner_does_not_emit_executable_order_intent(tmp_path) -> None:
    fixture = tmp_path / "safe.json"
    output = tmp_path / "safe.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "source": "safe-fixture",
                "markets": [
                    _book(
                        best_yes_bid="0.5300",
                        best_no_bid="0.5200",
                        fee_status="supplied",
                        fee_per_contract="0.0100",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    write_jsonl_report(output, scan_fixture_file(fixture))

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["executable_order_intent"] is False
    assert "execution_mode" not in payload
    assert "order_intent" not in payload


def test_decimal_precision_is_preserved_in_scan_output(tmp_path) -> None:
    fixture = tmp_path / "precision.json"
    output = tmp_path / "precision.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "source": "precision-fixture",
                "markets": [
                    _book(
                        best_yes_bid="0.3333",
                        best_no_bid="0.6668",
                        yes_bid_size="3",
                        no_bid_size="5",
                        fee_status="supplied",
                        fee_per_contract="0",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    report = scan_fixture_file(fixture)
    write_jsonl_report(output, report)

    assert report.records[0].candidate.gross_edge_per_contract == Decimal("0.0001")
    assert report.records[0].candidate.total_estimated_net_edge == Decimal("0.0003")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["gross_edge_per_contract"] == "0.0001"
    assert payload["total_estimated_net_edge"] == "0.0003"


def test_scanner_consumes_existing_snapshot_jsonl(tmp_path) -> None:
    snapshot_path = tmp_path / "snapshots.jsonl"
    write_snapshots(
        snapshot_path,
        [
            MarketDataSnapshot(
                exchange="kalshi_demo",
                ticker="DEMO-MARKET",
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                recorded_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
                normalized_orderbook=NormalizedOrderBook(
                    instrument_id="DEMO-MARKET",
                    source="fixture",
                    bids=(OrderBookLevel(price=Decimal("0.4800"), quantity=Decimal("10")),),
                    asks=(OrderBookLevel(price=Decimal("0.5100"), quantity=Decimal("7")),),
                ),
                source_type="fixture",
            )
        ],
    )

    report = scan_snapshot_jsonl_file(snapshot_path)

    assert report.input_kind == "snapshot_jsonl"
    assert report.candidate_count == 1
    assert report.reject_count == 1
    assert report.records[0].candidate.best_no_bid == Decimal("0.4900")
    assert report.rejection_reason_counts["no_complement_edge"] == 1


def _book(
    *,
    best_yes_bid,
    best_no_bid,
    yes_bid_size="10",
    no_bid_size="7",
    fee_status="missing",
    fee_per_contract=None,
    estimated_slippage_per_contract="0",
    failed_leg_reserve_per_contract="0",
    minimum_net_edge_per_contract="0",
    data_quality_flags=None,
):
    book = {
        "venue": "kalshi_demo",
        "market_id": "DEMO-MARKET",
        "best_yes_bid": best_yes_bid,
        "best_no_bid": best_no_bid,
        "yes_bid_size": yes_bid_size,
        "no_bid_size": no_bid_size,
        "fee_status": fee_status,
        "estimated_slippage_per_contract": estimated_slippage_per_contract,
        "failed_leg_reserve_per_contract": failed_leg_reserve_per_contract,
        "minimum_net_edge_per_contract": minimum_net_edge_per_contract,
    }
    if fee_per_contract is not None:
        book["fee_per_contract"] = fee_per_contract
    if data_quality_flags is not None:
        book["data_quality_flags"] = data_quality_flags
    return book
