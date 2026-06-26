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
    run_comparison_count: int
    validation_summary_count: int
    review_note_count: int
    methodology_note_count: int
    data_dictionary_field_count: int
    citation_index_entry_count: int


@dataclass(frozen=True, slots=True)
class ReportInputManifestEntry:
    """One descriptive local report input."""

    local_path: str
    input_kind: str
    display_label: str
    rights_note: str
    assumption_scope: str
    required: bool


@dataclass(frozen=True, slots=True)
class LocalRunComparison:
    """One descriptive local run-comparison row."""

    source_label: str
    run_name: str
    local_path: str
    observed_decision_count: int
    not_supplied_inputs: tuple[str, ...]
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingRunComparisonInput:
    """Optional local run-comparison descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalValidationSummary:
    """One descriptive local validation-summary row."""

    source_label: str
    command_label: str
    status: str
    artifact_path: str
    observed_at: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingValidationSummaryInput:
    """Optional local validation-summary descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalReviewNote:
    """One descriptive local review note."""

    source_label: str
    note_label: str
    source_path: str
    note_text: str
    follow_up_question: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingReviewNotesInput:
    """Optional local review-notes descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalMethodologyNote:
    """One descriptive local methodology note."""

    source_label: str
    method_label: str
    source_path: str
    methodology_text: str
    assumption_scope: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingMethodologyNotesInput:
    """Optional local methodology-notes descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalDataDictionaryField:
    """One descriptive local data-dictionary field."""

    source_label: str
    field_label: str
    source_path: str
    data_type_label: str
    unit: str
    definition: str
    rights_sensitivity_label: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingDataDictionaryInput:
    """Optional local data-dictionary descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalCitationIndexEntry:
    """One descriptive local citation-index entry."""

    source_label: str
    citation_label: str
    source_path: str
    citation_purpose: str
    rights_note: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingCitationIndexInput:
    """Optional local citation-index descriptor that was not supplied."""

    display_label: str
    local_path: str


VALIDATION_SUMMARY_STATUSES = frozenset(("pass", "fail", "skipped"))
CITATION_SOURCE_CONTENT_FIELDS = frozenset(
    (
        "content",
        "excerpt",
        "quote",
        "raw_text",
        "source_content",
        "source_excerpt",
        "text",
    )
)


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
    run_comparisons, missing_run_comparisons = _read_run_comparisons(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    validation_summaries, missing_validation_summaries = _read_validation_summaries(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    review_notes, missing_review_notes = _read_review_notes(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    methodology_notes, missing_methodology_notes = _read_methodology_notes(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    data_dictionary_fields, missing_data_dictionary = _read_data_dictionary(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    citation_index_entries, missing_citation_index = _read_citation_index(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    output_path = pack_input.output_dir / "report_pack.md"
    output_path.write_text(
        _render_markdown(
            pack_input=pack_input,
            stage7_report=stage7_report,
            stage7_report_path=stage7_report_path,
            sec_facts=sec_facts,
            manifest_entries=manifest_entries,
            run_comparisons=run_comparisons,
            missing_run_comparisons=missing_run_comparisons,
            validation_summaries=validation_summaries,
            missing_validation_summaries=missing_validation_summaries,
            review_notes=review_notes,
            missing_review_notes=missing_review_notes,
            methodology_notes=methodology_notes,
            missing_methodology_notes=missing_methodology_notes,
            data_dictionary_fields=data_dictionary_fields,
            missing_data_dictionary=missing_data_dictionary,
            citation_index_entries=citation_index_entries,
            missing_citation_index=missing_citation_index,
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
        run_comparison_count=len(run_comparisons),
        validation_summary_count=len(validation_summaries),
        review_note_count=len(review_notes),
        methodology_note_count=len(methodology_notes),
        data_dictionary_field_count=len(data_dictionary_fields),
        citation_index_entry_count=len(citation_index_entries),
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
            f"run_comparisons={pack.run_comparison_count}",
            f"validation_summaries={pack.validation_summary_count}",
            f"review_notes={pack.review_note_count}",
            f"methodology_notes={pack.methodology_note_count}",
            f"data_dictionary_fields={pack.data_dictionary_field_count}",
            f"citation_index_entries={pack.citation_index_entry_count}",
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


def _read_run_comparisons(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalRunComparison, ...], tuple[MissingRunComparisonInput, ...]]:
    if manifest_path is None:
        return (), ()

    runs: list[LocalRunComparison] = []
    missing: list[MissingRunComparisonInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_run_comparison":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local run-comparison input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingRunComparisonInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        runs.extend(
            _read_run_comparison_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(runs), tuple(missing)


def _resolve_manifest_local_path(manifest_path: Path, local_path: str) -> Path:
    path = Path(local_path)
    if path.is_absolute():
        return path
    return manifest_path.parent / path


def _read_run_comparison_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalRunComparison, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local run-comparison descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)

    runs = payload.get("runs")
    if not isinstance(runs, list):
        msg = f"{path}: local run-comparison descriptor must contain a runs list"
        raise ValueError(msg)

    parsed_runs: list[LocalRunComparison] = []
    for index, item in enumerate(runs, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local run-comparison run {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        parsed_runs.append(
            _parse_run_comparison(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_runs)


def _parse_run_comparison(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalRunComparison:
    required_fields = (
        "run_name",
        "local_path",
        "observed_decision_count",
        "not_supplied_inputs",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = f"{path}: local run-comparison run {index} missing field(s): {', '.join(missing)}"
        raise ValueError(msg)

    local_path = str(item["local_path"])
    parsed = urlparse(local_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local run-comparison run {index} remote URL is not supported"
        raise ValueError(msg)

    observed_decision_count = item["observed_decision_count"]
    if not isinstance(observed_decision_count, int) or observed_decision_count < 0:
        msg = (
            f"{path}: local run-comparison run {index} "
            "observed_decision_count must be a non-negative integer"
        )
        raise ValueError(msg)

    not_supplied_inputs = item["not_supplied_inputs"]
    if not isinstance(not_supplied_inputs, list) or not all(
        isinstance(value, str) for value in not_supplied_inputs
    ):
        msg = f"{path}: local run-comparison run {index} not_supplied_inputs must be a string list"
        raise ValueError(msg)

    return LocalRunComparison(
        source_label=source_label,
        run_name=str(item["run_name"]),
        local_path=local_path,
        observed_decision_count=observed_decision_count,
        not_supplied_inputs=tuple(not_supplied_inputs),
        limitation_note=str(item["limitation_note"]),
    )


def _read_validation_summaries(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalValidationSummary, ...], tuple[MissingValidationSummaryInput, ...]]:
    if manifest_path is None:
        return (), ()

    summaries: list[LocalValidationSummary] = []
    missing: list[MissingValidationSummaryInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_validation_summary":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local validation-summary input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingValidationSummaryInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        summaries.extend(
            _read_validation_summary_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(summaries), tuple(missing)


def _read_validation_summary_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalValidationSummary, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local validation-summary descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)

    checks = payload.get("checks")
    if not isinstance(checks, list):
        msg = f"{path}: local validation-summary descriptor must contain a checks list"
        raise ValueError(msg)

    parsed_checks: list[LocalValidationSummary] = []
    for index, item in enumerate(checks, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local validation-summary check {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        parsed_checks.append(
            _parse_validation_summary(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_checks)


def _parse_validation_summary(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalValidationSummary:
    required_fields = (
        "command_label",
        "status",
        "artifact_path",
        "observed_at",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local validation-summary check {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    artifact_path = str(item["artifact_path"])
    parsed = urlparse(artifact_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local validation-summary check {index} remote URL is not supported"
        raise ValueError(msg)

    status = str(item["status"])
    if status not in VALIDATION_SUMMARY_STATUSES:
        allowed = ", ".join(sorted(VALIDATION_SUMMARY_STATUSES))
        msg = f"{path}: local validation-summary check {index} status must be one of: {allowed}"
        raise ValueError(msg)

    return LocalValidationSummary(
        source_label=source_label,
        command_label=str(item["command_label"]),
        status=status,
        artifact_path=artifact_path,
        observed_at=str(item["observed_at"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_review_notes(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalReviewNote, ...], tuple[MissingReviewNotesInput, ...]]:
    if manifest_path is None:
        return (), ()

    notes: list[LocalReviewNote] = []
    missing: list[MissingReviewNotesInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_review_notes":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local review-notes input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingReviewNotesInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        notes.extend(
            _read_review_notes_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(notes), tuple(missing)


def _read_review_notes_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalReviewNote, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local review-notes descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)

    notes = payload.get("notes")
    if not isinstance(notes, list):
        msg = f"{path}: local review-notes descriptor must contain a notes list"
        raise ValueError(msg)

    parsed_notes: list[LocalReviewNote] = []
    for index, item in enumerate(notes, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local review note {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        parsed_notes.append(
            _parse_review_note(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_notes)


def _parse_review_note(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalReviewNote:
    required_fields = (
        "note_label",
        "source_path",
        "note_text",
        "follow_up_question",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = f"{path}: local review note {index} missing field(s): {', '.join(missing)}"
        raise ValueError(msg)

    source_path = str(item["source_path"])
    parsed = urlparse(source_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local review note {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalReviewNote(
        source_label=source_label,
        note_label=str(item["note_label"]),
        source_path=source_path,
        note_text=str(item["note_text"]),
        follow_up_question=str(item["follow_up_question"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_methodology_notes(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalMethodologyNote, ...], tuple[MissingMethodologyNotesInput, ...]]:
    if manifest_path is None:
        return (), ()

    methods: list[LocalMethodologyNote] = []
    missing: list[MissingMethodologyNotesInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_methodology_notes":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local methodology-notes input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingMethodologyNotesInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        methods.extend(
            _read_methodology_notes_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(methods), tuple(missing)


def _read_methodology_notes_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalMethodologyNote, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local methodology-notes descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)

    methods = payload.get("methods")
    if not isinstance(methods, list):
        msg = f"{path}: local methodology-notes descriptor must contain a methods list"
        raise ValueError(msg)

    parsed_methods: list[LocalMethodologyNote] = []
    for index, item in enumerate(methods, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local methodology note {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        parsed_methods.append(
            _parse_methodology_note(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_methods)


def _parse_methodology_note(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalMethodologyNote:
    required_fields = (
        "method_label",
        "source_path",
        "methodology_text",
        "assumption_scope",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = f"{path}: local methodology note {index} missing field(s): {', '.join(missing)}"
        raise ValueError(msg)

    source_path = str(item["source_path"])
    parsed = urlparse(source_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local methodology note {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalMethodologyNote(
        source_label=source_label,
        method_label=str(item["method_label"]),
        source_path=source_path,
        methodology_text=str(item["methodology_text"]),
        assumption_scope=str(item["assumption_scope"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_data_dictionary(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalDataDictionaryField, ...], tuple[MissingDataDictionaryInput, ...]]:
    if manifest_path is None:
        return (), ()

    fields: list[LocalDataDictionaryField] = []
    missing: list[MissingDataDictionaryInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_data_dictionary":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local data-dictionary input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingDataDictionaryInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        fields.extend(
            _read_data_dictionary_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(fields), tuple(missing)


def _read_data_dictionary_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalDataDictionaryField, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local data-dictionary descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)

    fields = payload.get("fields")
    if not isinstance(fields, list):
        msg = f"{path}: local data-dictionary descriptor must contain a fields list"
        raise ValueError(msg)

    parsed_fields: list[LocalDataDictionaryField] = []
    for index, item in enumerate(fields, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local data-dictionary field {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        parsed_fields.append(
            _parse_data_dictionary_field(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_fields)


def _parse_data_dictionary_field(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalDataDictionaryField:
    required_fields = (
        "field_label",
        "source_path",
        "data_type_label",
        "unit",
        "definition",
        "rights_sensitivity_label",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local data-dictionary field {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    source_path = str(item["source_path"])
    parsed = urlparse(source_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local data-dictionary field {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalDataDictionaryField(
        source_label=source_label,
        field_label=str(item["field_label"]),
        source_path=source_path,
        data_type_label=str(item["data_type_label"]),
        unit=str(item["unit"]),
        definition=str(item["definition"]),
        rights_sensitivity_label=str(item["rights_sensitivity_label"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_citation_index(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalCitationIndexEntry, ...], tuple[MissingCitationIndexInput, ...]]:
    if manifest_path is None:
        return (), ()

    citations: list[LocalCitationIndexEntry] = []
    missing: list[MissingCitationIndexInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_citation_index":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local citation-index input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingCitationIndexInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        citations.extend(
            _read_citation_index_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(citations), tuple(missing)


def _read_citation_index_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalCitationIndexEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local citation-index descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_citation_source_content_fields(payload, path=path)

    citations = payload.get("citations")
    if not isinstance(citations, list):
        msg = f"{path}: local citation-index descriptor must contain a citations list"
        raise ValueError(msg)

    parsed_citations: list[LocalCitationIndexEntry] = []
    for index, item in enumerate(citations, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local citation-index entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_citation_source_content_fields(item, path=path)
        parsed_citations.append(
            _parse_citation_index_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_citations)


def _reject_citation_source_content_fields(payload: dict[str, object], *, path: Path) -> None:
    found = sorted(
        key
        for key in payload
        if key.lower().replace("-", "_") in CITATION_SOURCE_CONTENT_FIELDS
    )
    if found:
        msg = f"{path}: local citation-index descriptor contains source-content field(s)"
        raise ValueError(msg)


def _parse_citation_index_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalCitationIndexEntry:
    required_fields = (
        "citation_label",
        "source_path",
        "citation_purpose",
        "rights_note",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local citation-index entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    source_path = str(item["source_path"])
    parsed = urlparse(source_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local citation-index entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalCitationIndexEntry(
        source_label=source_label,
        citation_label=str(item["citation_label"]),
        source_path=source_path,
        citation_purpose=str(item["citation_purpose"]),
        rights_note=str(item["rights_note"]),
        limitation_note=str(item["limitation_note"]),
    )


def _render_markdown(
    *,
    pack_input: PaperReportPackInput,
    stage7_report: ResearchReport,
    stage7_report_path: Path,
    sec_facts: tuple[EquityFundamentalFact, ...],
    manifest_entries: tuple[ReportInputManifestEntry, ...],
    run_comparisons: tuple[LocalRunComparison, ...],
    missing_run_comparisons: tuple[MissingRunComparisonInput, ...],
    validation_summaries: tuple[LocalValidationSummary, ...],
    missing_validation_summaries: tuple[MissingValidationSummaryInput, ...],
    review_notes: tuple[LocalReviewNote, ...],
    missing_review_notes: tuple[MissingReviewNotesInput, ...],
    methodology_notes: tuple[LocalMethodologyNote, ...],
    missing_methodology_notes: tuple[MissingMethodologyNotesInput, ...],
    data_dictionary_fields: tuple[LocalDataDictionaryField, ...],
    missing_data_dictionary: tuple[MissingDataDictionaryInput, ...],
    citation_index_entries: tuple[LocalCitationIndexEntry, ...],
    missing_citation_index: tuple[MissingCitationIndexInput, ...],
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
            "## Local Run Comparison",
            "",
            _render_run_comparisons(run_comparisons, missing_run_comparisons),
            "",
            "## Local Validation Summary",
            "",
            _render_validation_summaries(validation_summaries, missing_validation_summaries),
            "",
            "## Local Review Notes",
            "",
            _render_review_notes(review_notes, missing_review_notes),
            "",
            "## Local Methodology Notes",
            "",
            _render_methodology_notes(methodology_notes, missing_methodology_notes),
            "",
            "## Local Data Dictionary",
            "",
            _render_data_dictionary(data_dictionary_fields, missing_data_dictionary),
            "",
            "## Local Citation Index",
            "",
            _render_citation_index(citation_index_entries, missing_citation_index),
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


def _render_run_comparisons(
    runs: tuple[LocalRunComparison, ...],
    missing_inputs: tuple[MissingRunComparisonInput, ...],
) -> str:
    if not runs and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local run comparison | not supplied |"

    rows = [
        "| source | run | local path | observed decisions | not supplied inputs | limitation |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    rows.extend(
        f"| {run.source_label} | {run.run_name} | {run.local_path} | "
        f"{run.observed_decision_count} | {_format_not_supplied_inputs(run.not_supplied_inputs)} | "
        f"{run.limitation_note} |"
        for run in runs
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | 0 | "
        "not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _format_not_supplied_inputs(values: tuple[str, ...]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


def _render_validation_summaries(
    summaries: tuple[LocalValidationSummary, ...],
    missing_inputs: tuple[MissingValidationSummaryInput, ...],
) -> str:
    if not summaries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local validation summary | not supplied |"

    rows = [
        "| source | command | status | artifact path | observed at | limitation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {summary.source_label} | {summary.command_label} | {summary.status} | "
        f"{summary.artifact_path} | {summary.observed_at} | {summary.limitation_note} |"
        for summary in summaries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_review_notes(
    notes: tuple[LocalReviewNote, ...],
    missing_inputs: tuple[MissingReviewNotesInput, ...],
) -> str:
    if not notes and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local review notes | not supplied |"

    rows = [
        "| source | note | source path | note text | follow-up question | limitation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {note.source_label} | {note.note_label} | {note.source_path} | "
        f"{note.note_text} | {note.follow_up_question} | {note.limitation_note} |"
        for note in notes
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | "
        "not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_methodology_notes(
    methods: tuple[LocalMethodologyNote, ...],
    missing_inputs: tuple[MissingMethodologyNotesInput, ...],
) -> str:
    if not methods and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local methodology notes | not supplied |"

    rows = [
        "| source | method | source path | methodology | assumption scope | limitation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {method.source_label} | {method.method_label} | {method.source_path} | "
        f"{method.methodology_text} | {method.assumption_scope} | {method.limitation_note} |"
        for method in methods
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | "
        "not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_data_dictionary(
    fields: tuple[LocalDataDictionaryField, ...],
    missing_inputs: tuple[MissingDataDictionaryInput, ...],
) -> str:
    if not fields and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local data dictionary | not supplied |"

    rows = [
        "| source | field | source path | data type | unit | definition | "
        "rights/sensitivity | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {field.source_label} | {field.field_label} | {field.source_path} | "
        f"{field.data_type_label} | {field.unit} | {field.definition} | "
        f"{field.rights_sensitivity_label} | {field.limitation_note} |"
        for field in fields
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | "
        "not supplied | not supplied | not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_citation_index(
    citations: tuple[LocalCitationIndexEntry, ...],
    missing_inputs: tuple[MissingCitationIndexInput, ...],
) -> str:
    if not citations and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local citation index | not supplied |"

    rows = [
        "| source | citation | source path | purpose | rights note | limitation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {citation.source_label} | {citation.citation_label} | "
        f"{citation.source_path} | {citation.citation_purpose} | "
        f"{citation.rights_note} | {citation.limitation_note} |"
        for citation in citations
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | "
        "not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
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
