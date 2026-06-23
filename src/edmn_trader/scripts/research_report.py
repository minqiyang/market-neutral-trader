"""Generate a local Stage 7 research report from Stage 6 logs."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from edmn_trader.data.jsonl import read_jsonl_records

SECRET_FIELD_PARTS = ("secret", "token", "password", "private", "credential", "api_key", "key")
ZERO = Decimal("0")
MONEY_PLACES = Decimal("0.0001")
QUANTITY_PLACES = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ResearchReportInput:
    """Local Stage 7 report inputs."""

    market_maker_logs: tuple[Path, ...]
    output_path: Path
    fills_path: Path | None = None


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """Stage 7 attribution summary."""

    frame_count: int
    quote_count: int
    risk_approvals: int
    risk_rejections: int
    skipped_actions: int
    adapter_submissions: int
    adapter_errors: int
    supplied_fills: int
    total_fees: Decimal
    realized_gross_pnl: Decimal
    realized_net_pnl: Decimal
    ending_inventory: Decimal


@dataclass(frozen=True, slots=True)
class ExplicitFill:
    """A local explicit fill assumption."""

    instrument_id: str
    side: Literal["buy", "sell"]
    price: Decimal
    quantity: Decimal
    fee: Decimal
    observed_at: str
    assumption_note: str


def generate_research_report(report_input: ResearchReportInput) -> ResearchReport:
    """Generate a Markdown report from local Stage 6 logs and optional fills."""

    counts = _count_stage_6_records(report_input.market_maker_logs)
    fills = _read_fills(report_input.fills_path) if report_input.fills_path else ()
    attribution = _attribute_fills(fills)
    report = ResearchReport(
        frame_count=counts["frame"],
        quote_count=counts["quote_candidate"],
        risk_approvals=counts["risk_approval"],
        risk_rejections=counts["risk_rejection"],
        skipped_actions=counts["skipped_action"],
        adapter_submissions=counts["adapter_submission"],
        adapter_errors=counts["adapter_error"],
        supplied_fills=len(fills),
        total_fees=attribution.total_fees,
        realized_gross_pnl=attribution.realized_gross_pnl,
        realized_net_pnl=attribution.realized_net_pnl,
        ending_inventory=attribution.ending_inventory,
    )
    report_input.output_path.parent.mkdir(parents=True, exist_ok=True)
    report_input.output_path.write_text(
        _render_markdown(report=report, fills=fills),
        encoding="utf-8",
        newline="\n",
    )
    return report


def render_summary(report: ResearchReport, *, output_path: Path) -> str:
    """Render concise CLI output."""

    return "\n".join(
        (
            f"report_output={output_path}",
            f"supplied_fills={report.supplied_fills}",
            f"realized_net_pnl={_format_money(report.realized_net_pnl)}",
            "limitations=local/offline report; explicit fills only; no profitability claims",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--market-maker-log",
        action="append",
        required=True,
        type=Path,
        help="Stage 6 market-maker replay JSONL log. May be repeated.",
    )
    parser.add_argument("--fills", type=Path, default=None, help="Optional explicit fill JSONL.")
    parser.add_argument("--output", required=True, type=Path, help="Output Markdown report path.")
    args = parser.parse_args()

    report = generate_research_report(
        ResearchReportInput(
            market_maker_logs=tuple(args.market_maker_log),
            fills_path=args.fills,
            output_path=args.output,
        )
    )
    print(render_summary(report, output_path=args.output))


@dataclass(frozen=True, slots=True)
class _Attribution:
    total_fees: Decimal
    realized_gross_pnl: Decimal
    realized_net_pnl: Decimal
    ending_inventory: Decimal


def _count_stage_6_records(paths: tuple[Path, ...]) -> Counter[str]:
    if not paths:
        msg = "at least one market-maker log is required"
        raise ValueError(msg)

    counts: Counter[str] = Counter()
    for path in paths:
        for record in read_jsonl_records(path):
            record_type = str(record.get("record_type", ""))
            counts[record_type] += 1
            if record_type == "risk_decision":
                if record.get("approved") is True:
                    counts["risk_approval"] += 1
                else:
                    counts["risk_rejection"] += 1
            if (
                record_type == "lifecycle_intent"
                and str(record.get("result_status", "")) == "skipped"
            ):
                counts["skipped_action"] += 1
    return counts


def _read_fills(path: Path) -> tuple[ExplicitFill, ...]:
    fills: list[ExplicitFill] = []
    for line_number, record in enumerate(read_jsonl_records(path), start=1):
        _reject_secret_like_fields(record, path=path, line_number=line_number)
        fills.append(_parse_fill(record, path=path, line_number=line_number))
    return tuple(fills)


def _reject_secret_like_fields(record: dict[str, object], *, path: Path, line_number: int) -> None:
    for field in record:
        lowered = field.lower()
        if any(part in lowered for part in SECRET_FIELD_PARTS):
            msg = f"{path}:{line_number}: secret-like fill field is not allowed: {field}"
            raise ValueError(msg)


def _parse_fill(record: dict[str, object], *, path: Path, line_number: int) -> ExplicitFill:
    required = (
        "instrument_id",
        "side",
        "price",
        "quantity",
        "fee",
        "observed_at",
        "assumption_note",
    )
    missing = [field for field in required if field not in record]
    if missing:
        msg = f"{path}:{line_number}: fill missing required field(s): {', '.join(missing)}"
        raise ValueError(msg)

    side = str(record["side"])
    if side not in {"buy", "sell"}:
        msg = f"{path}:{line_number}: fill side must be buy or sell"
        raise ValueError(msg)

    return ExplicitFill(
        instrument_id=str(record["instrument_id"]),
        side=side,
        price=_parse_decimal(record["price"], path=path, line_number=line_number, field="price"),
        quantity=_parse_decimal(
            record["quantity"], path=path, line_number=line_number, field="quantity"
        ),
        fee=_parse_decimal(record["fee"], path=path, line_number=line_number, field="fee"),
        observed_at=str(record["observed_at"]),
        assumption_note=str(record["assumption_note"]),
    )


def _parse_decimal(value: object, *, path: Path, line_number: int, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = f"{path}:{line_number}: {field} must be a Decimal-compatible value"
        raise ValueError(msg) from exc
    if parsed < ZERO:
        msg = f"{path}:{line_number}: {field} must be non-negative"
        raise ValueError(msg)
    return parsed


def _attribute_fills(fills: tuple[ExplicitFill, ...]) -> _Attribution:
    lots: defaultdict[str, deque[tuple[Decimal, Decimal]]] = defaultdict(deque)
    total_fees = ZERO
    realized_gross_pnl = ZERO
    ending_inventory = ZERO

    for fill in fills:
        total_fees += fill.fee
        if fill.side == "buy":
            lots[fill.instrument_id].append((fill.quantity, fill.price))
            ending_inventory += fill.quantity
            continue

        ending_inventory -= fill.quantity
        quantity_to_match = fill.quantity
        instrument_lots = lots[fill.instrument_id]
        while quantity_to_match > ZERO and instrument_lots:
            lot_quantity, lot_price = instrument_lots.popleft()
            matched_quantity = min(quantity_to_match, lot_quantity)
            realized_gross_pnl += (fill.price - lot_price) * matched_quantity
            quantity_to_match -= matched_quantity
            remaining_lot_quantity = lot_quantity - matched_quantity
            if remaining_lot_quantity > ZERO:
                instrument_lots.appendleft((remaining_lot_quantity, lot_price))

    return _Attribution(
        total_fees=total_fees,
        realized_gross_pnl=realized_gross_pnl,
        realized_net_pnl=realized_gross_pnl - total_fees,
        ending_inventory=ending_inventory,
    )


def _render_markdown(*, report: ResearchReport, fills: tuple[ExplicitFill, ...]) -> str:
    fill_note = "no fills supplied" if not fills else "explicit local fill assumptions supplied"
    fill_rows = "\n".join(
        f"| {fill.observed_at} | {fill.instrument_id} | {fill.side} | "
        f"{_format_money(fill.price)} | {_format_quantity(fill.quantity)} | "
        f"{_format_money(fill.fee)} | {fill.assumption_note} |"
        for fill in fills
    )
    if not fill_rows:
        fill_rows = "| n/a | n/a | n/a | 0 | 0 | 0 | no fills supplied |"

    return "\n".join(
        (
            "# Stage 7 Research Report",
            "",
            "Local/offline attribution report from Stage 6 market-maker replay logs.",
            "",
            "## Observed Stage 6 Counts",
            "",
            "| metric | value |",
            "| --- | ---: |",
            f"| frames | {report.frame_count} |",
            f"| quote candidates | {report.quote_count} |",
            f"| risk approvals | {report.risk_approvals} |",
            f"| risk rejections | {report.risk_rejections} |",
            f"| skipped actions | {report.skipped_actions} |",
            f"| adapter submissions | {report.adapter_submissions} |",
            f"| adapter errors | {report.adapter_errors} |",
            "",
            "## Supplied Fill Assumptions",
            "",
            f"Fill source status: {fill_note}. Fills are not inferred from "
            "fake/demo adapter submissions.",
            "",
            "| observed at | instrument | side | price | quantity | fee | assumption note |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
            fill_rows,
            "",
            "## Attribution Summary",
            "",
            "| metric | value |",
            "| --- | ---: |",
            f"| supplied fills | {report.supplied_fills} |",
            f"| total fees | {_format_money(report.total_fees)} |",
            f"| realized gross PnL | {_format_money(report.realized_gross_pnl)} |",
            f"| realized net PnL | {_format_money(report.realized_net_pnl)} |",
            f"| ending inventory | {_format_quantity(report.ending_inventory)} |",
            "",
            "## Limitations",
            "",
            "- This report uses local Stage 6 logs and explicit assumptions only.",
            "- Missing fills are reported as no fills supplied; they are not synthesized "
            "or backfilled.",
            "- Slippage, marks, and adverse-selection proxies are omitted unless explicit "
            "input supports them.",
            "- This report does not claim profitability or production readiness.",
            "",
        )
    )


def _format_money(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    return str(value.quantize(MONEY_PLACES))


def _format_quantity(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    return str(value.quantize(QUANTITY_PLACES))


if __name__ == "__main__":
    main()
