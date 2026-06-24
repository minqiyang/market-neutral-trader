"""Generate a local Stage 10 paper research report pack."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from edmn_trader.adapters.sec_edgar import normalize_sec_company_facts
from edmn_trader.research.equities import EquityFundamentalFact
from edmn_trader.scripts.research_report import (
    ResearchReport,
    ResearchReportInput,
    generate_research_report,
)


@dataclass(frozen=True, slots=True)
class PaperReportPackInput:
    """Local Stage 10 report-pack inputs."""

    market_maker_logs: tuple[Path, ...]
    output_dir: Path
    fills_path: Path | None = None
    sec_companyfacts: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class PaperReportPack:
    """Stage 10 report-pack summary."""

    output_path: Path
    stage7_report_path: Path
    stage7_report: ResearchReport
    sec_fact_count: int


def generate_paper_report_pack(pack_input: PaperReportPackInput) -> PaperReportPack:
    """Generate an offline Markdown report pack from local inputs only."""

    pack_input.output_dir.mkdir(parents=True, exist_ok=True)
    stage7_report_path = pack_input.output_dir / "stage7_attribution.md"
    stage7_report = generate_research_report(
        ResearchReportInput(
            market_maker_logs=pack_input.market_maker_logs,
            fills_path=pack_input.fills_path,
            output_path=stage7_report_path,
        )
    )
    sec_facts = _read_sec_facts(pack_input.sec_companyfacts)
    output_path = pack_input.output_dir / "report_pack.md"
    output_path.write_text(
        _render_markdown(
            pack_input=pack_input,
            stage7_report=stage7_report,
            stage7_report_path=stage7_report_path,
            sec_facts=sec_facts,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return PaperReportPack(
        output_path=output_path,
        stage7_report_path=stage7_report_path,
        stage7_report=stage7_report,
        sec_fact_count=len(sec_facts),
    )


def render_summary(pack: PaperReportPack) -> str:
    """Render concise CLI output."""

    return "\n".join(
        (
            f"report_pack_output={pack.output_path}",
            f"stage7_report_output={pack.stage7_report_path}",
            f"supplied_fills={pack.stage7_report.supplied_fills}",
            f"sec_facts={pack.sec_fact_count}",
            "limitations=local/offline pack; descriptive only; no profitability claims",
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
    parser.add_argument(
        "--sec-companyfacts",
        action="append",
        default=[],
        type=Path,
        help="Optional local SEC companyfacts JSON fixture. May be repeated.",
    )
    parser.add_argument("--output-dir", required=True, type=Path, help="Output report-pack dir.")
    args = parser.parse_args()

    pack = generate_paper_report_pack(
        PaperReportPackInput(
            market_maker_logs=tuple(args.market_maker_log),
            fills_path=args.fills,
            sec_companyfacts=tuple(args.sec_companyfacts),
            output_dir=args.output_dir,
        )
    )
    print(render_summary(pack))


def _read_sec_facts(paths: tuple[Path, ...]) -> tuple[EquityFundamentalFact, ...]:
    facts: list[EquityFundamentalFact] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            msg = f"{path}: SEC companyfacts fixture must contain a JSON object"
            raise ValueError(msg)
        facts.extend(normalize_sec_company_facts(payload))
    return tuple(facts)


def _render_markdown(
    *,
    pack_input: PaperReportPackInput,
    stage7_report: ResearchReport,
    stage7_report_path: Path,
    sec_facts: tuple[EquityFundamentalFact, ...],
) -> str:
    return "\n".join(
        (
            "# Stage 10 Paper Research Report Pack",
            "",
            "Local/offline report pack combining Stage 7 attribution and SEC EDGAR "
            "public fundamentals.",
            "",
            "## Observed Stage 7 Attribution",
            "",
            f"Source report: `{stage7_report_path.name}`",
            "",
            "| metric | value |",
            "| --- | ---: |",
            f"| frames | {stage7_report.frame_count} |",
            f"| quote candidates | {stage7_report.quote_count} |",
            f"| risk approvals | {stage7_report.risk_approvals} |",
            f"| risk rejections | {stage7_report.risk_rejections} |",
            f"| adapter submissions | {stage7_report.adapter_submissions} |",
            f"| adapter errors | {stage7_report.adapter_errors} |",
            "",
            "## Supplied Assumptions",
            "",
            "| input | status |",
            "| --- | --- |",
            _fill_assumption_row(stage7_report),
            "",
            "## Local Source Inventory",
            "",
            "| source | status |",
            "| --- | --- |",
            f"| Market-maker logs | supplied: {_path_names(pack_input.market_maker_logs)} |",
            f"| Fills | {_optional_path_status(pack_input.fills_path)} |",
            f"| SEC companyfacts | {_optional_paths_status(pack_input.sec_companyfacts)} |",
            f"| Generated Stage 7 report | supplied: {stage7_report_path.name} |",
            "",
            "## SEC Fundamentals",
            "",
            _render_sec_facts(sec_facts),
            "",
            "## Limitations",
            "",
            "- SEC EDGAR facts come from local companyfacts fixtures only.",
            "- missing optional inputs are reported as not supplied.",
            "- Fill assumptions are supplied explicitly or left as not supplied; they are "
            "not inferred.",
            "- This pack is descriptive, non-executable, and does not rank securities.",
            "- This pack does not claim profitability or production readiness.",
            "",
        )
    )


def _fill_assumption_row(stage7_report: ResearchReport) -> str:
    if stage7_report.supplied_fills == 0:
        return "| Fill assumptions | not supplied |"
    return f"| Fill assumptions | supplied: {stage7_report.supplied_fills} |"


def _optional_path_status(path: Path | None) -> str:
    if path is None:
        return "not supplied"
    return f"supplied: {path.name}"


def _optional_paths_status(paths: tuple[Path, ...]) -> str:
    if not paths:
        return "not supplied"
    return f"supplied: {_path_names(paths)}"


def _path_names(paths: tuple[Path, ...]) -> str:
    return ", ".join(path.name for path in paths)


def _render_sec_facts(sec_facts: tuple[EquityFundamentalFact, ...]) -> str:
    if not sec_facts:
        return "| input | status |\n| --- | --- |\n| SEC fundamentals | not supplied |"

    rows = [
        "| entity | concept | fiscal year | period | form | unit | value | filed |",
        "| --- | --- | ---: | --- | --- | --- | ---: | --- |",
    ]
    rows.extend(
        f"| {fact.entity_name} | {fact.concept} | {fact.fiscal_year} | "
        f"{fact.fiscal_period} | {fact.form} | {fact.unit} | {fact.value} | {fact.filed} |"
        for fact in sec_facts
    )
    return "\n".join(rows)


if __name__ == "__main__":
    main()
