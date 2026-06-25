"""Generate a local Stage 10 paper research report pack."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from edmn_trader.adapters.sec_edgar import normalize_sec_company_facts
from edmn_trader.research.equities import EquityFundamentalFact
from edmn_trader.scripts.research_report import (
    SECRET_FIELD_PARTS,
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
    report_input_manifest: Path | None = None


@dataclass(frozen=True, slots=True)
class PaperReportPack:
    """Stage 10 report-pack summary."""

    output_path: Path
    stage7_report_path: Path
    stage7_report: ResearchReport
    sec_fact_count: int
    manifest_entry_count: int


@dataclass(frozen=True, slots=True)
class ReportInputManifestEntry:
    """One descriptive local report input."""

    local_path: str
    input_kind: str
    display_label: str
    rights_note: str
    assumption_scope: str
    required: bool


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
    manifest_entries = (
        _read_manifest_entries(pack_input.report_input_manifest)
        if pack_input.report_input_manifest
        else ()
    )
    output_path = pack_input.output_dir / "report_pack.md"
    output_path.write_text(
        _render_markdown(
            pack_input=pack_input,
            stage7_report=stage7_report,
            stage7_report_path=stage7_report_path,
            sec_facts=sec_facts,
            manifest_entries=manifest_entries,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return PaperReportPack(
        output_path=output_path,
        stage7_report_path=stage7_report_path,
        stage7_report=stage7_report,
        sec_fact_count=len(sec_facts),
        manifest_entry_count=len(manifest_entries),
    )


def render_summary(pack: PaperReportPack) -> str:
    """Render concise CLI output."""

    return "\n".join(
        (
            f"report_pack_output={pack.output_path}",
            f"stage7_report_output={pack.stage7_report_path}",
            f"supplied_fills={pack.stage7_report.supplied_fills}",
            f"sec_facts={pack.sec_fact_count}",
            f"manifest_inputs={pack.manifest_entry_count}",
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
    parser.add_argument(
        "--report-input-manifest",
        type=Path,
        default=None,
        help="Optional local report-input manifest JSON.",
    )
    parser.add_argument("--output-dir", required=True, type=Path, help="Output report-pack dir.")
    args = parser.parse_args()

    pack = generate_paper_report_pack(
        PaperReportPackInput(
            market_maker_logs=tuple(args.market_maker_log),
            fills_path=args.fills,
            sec_companyfacts=tuple(args.sec_companyfacts),
            report_input_manifest=args.report_input_manifest,
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


def _read_manifest_entries(path: Path) -> tuple[ReportInputManifestEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: report-input manifest must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)

    inputs = payload.get("inputs")
    if not isinstance(inputs, list):
        msg = f"{path}: report-input manifest must contain an inputs list"
        raise ValueError(msg)

    entries: list[ReportInputManifestEntry] = []
    for index, item in enumerate(inputs, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: manifest input {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        entries.append(_parse_manifest_entry(item, path=path, index=index))
    return tuple(entries)


def _reject_secret_like_fields(record: dict[str, object], *, path: Path) -> None:
    for field in record:
        lowered = field.lower()
        if any(part in lowered for part in SECRET_FIELD_PARTS):
            msg = f"{path}: secret-like manifest field is not allowed: {field}"
            raise ValueError(msg)


def _parse_manifest_entry(
    item: dict[str, object], *, path: Path, index: int
) -> ReportInputManifestEntry:
    required_fields = (
        "local_path",
        "input_kind",
        "display_label",
        "rights_note",
        "assumption_scope",
        "required",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = f"{path}: manifest input {index} missing field(s): {', '.join(missing)}"
        raise ValueError(msg)

    local_path = str(item["local_path"])
    parsed = urlparse(local_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: manifest input {index} remote URL is not supported"
        raise ValueError(msg)

    required = item["required"]
    if not isinstance(required, bool):
        msg = f"{path}: manifest input {index} required must be a boolean"
        raise ValueError(msg)

    return ReportInputManifestEntry(
        local_path=local_path,
        input_kind=str(item["input_kind"]),
        display_label=str(item["display_label"]),
        rights_note=str(item["rights_note"]),
        assumption_scope=str(item["assumption_scope"]),
        required=required,
    )


def _render_markdown(
    *,
    pack_input: PaperReportPackInput,
    stage7_report: ResearchReport,
    stage7_report_path: Path,
    sec_facts: tuple[EquityFundamentalFact, ...],
    manifest_entries: tuple[ReportInputManifestEntry, ...],
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
            "| Report input manifest | "
            f"{_optional_path_status(pack_input.report_input_manifest)} |",
            f"| Generated Stage 7 report | supplied: {stage7_report_path.name} |",
            "",
            "## Report Input Manifest",
            "",
            _render_manifest_entries(manifest_entries),
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


def _render_manifest_entries(entries: tuple[ReportInputManifestEntry, ...]) -> str:
    if not entries:
        return "| input | status |\n| --- | --- |\n| Report input manifest | not supplied |"

    rows = [
        "| label | kind | local path | rights note | assumption scope | required |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.display_label} | {entry.input_kind} | {entry.local_path} | "
        f"{entry.rights_note} | {entry.assumption_scope} | {entry.required} |"
        for entry in entries
    )
    return "\n".join(rows)


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
