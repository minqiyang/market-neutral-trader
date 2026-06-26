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
    term_glossary_entry_count: int
    assumption_register_entry_count: int
    coverage_matrix_entry_count: int
    reproducibility_checklist_step_count: int
    risk_review_entry_count: int
    data_rights_review_entry_count: int
    artifact_inventory_entry_count: int
    appendix_index_entry_count: int
    limitation_register_entry_count: int
    open_questions_entry_count: int
    decision_log_entry_count: int
    follow_up_register_entry_count: int
    version_notes_entry_count: int
    distribution_checklist_entry_count: int
    handoff_notes_entry_count: int


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


@dataclass(frozen=True, slots=True)
class LocalTermGlossaryEntry:
    """One descriptive local term-glossary entry."""

    source_label: str
    term_label: str
    source_path: str
    definition: str
    usage_scope: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingTermGlossaryInput:
    """Optional local term-glossary descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalAssumptionRegisterEntry:
    """One descriptive local assumption-register entry."""

    source_label: str
    assumption_label: str
    source_path: str
    rationale: str
    scope: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingAssumptionRegisterInput:
    """Optional local assumption-register descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalCoverageMatrixEntry:
    """One descriptive local coverage-matrix entry."""

    source_label: str
    section_label: str
    source_path: str
    input_label: str
    validation_label: str
    coverage_note: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingCoverageMatrixInput:
    """Optional local coverage-matrix descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalReproducibilityChecklistStep:
    """One descriptive local reproducibility-checklist step."""

    source_label: str
    step_label: str
    artifact_path: str
    command_label: str
    environment_label: str
    expected_output_label: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingReproducibilityChecklistInput:
    """Optional local reproducibility-checklist descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalRiskReviewEntry:
    """One descriptive local risk-review entry."""

    source_label: str
    risk_control_label: str
    boundary_label: str
    mitigation_note: str
    review_status_label: str
    evidence_path: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingRiskReviewInput:
    """Optional local risk-review descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalDataRightsReviewEntry:
    """One descriptive local data-rights-review entry."""

    source_label: str
    data_label: str
    rights_status_label: str
    permitted_use_note: str
    restriction_note: str
    evidence_path: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingDataRightsReviewInput:
    """Optional local data-rights-review descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalArtifactInventoryEntry:
    """One descriptive local artifact-inventory entry."""

    source_label: str
    artifact_label: str
    artifact_type_label: str
    local_path: str
    generation_source_label: str
    intended_report_use: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingArtifactInventoryInput:
    """Optional local artifact-inventory descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalAppendixIndexEntry:
    """One descriptive local appendix-index entry."""

    source_label: str
    appendix_label: str
    report_section_label: str
    artifact_path: str
    appendix_purpose_note: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingAppendixIndexInput:
    """Optional local appendix-index descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalLimitationRegisterEntry:
    """One descriptive local limitation-register entry."""

    source_label: str
    limitation_label: str
    affected_section_label: str
    reference_path: str
    scope_note: str
    mitigation_note: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingLimitationRegisterInput:
    """Optional local limitation-register descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalOpenQuestionEntry:
    """One descriptive local open-question entry."""

    source_label: str
    question_label: str
    affected_section_label: str
    reference_path: str
    owner_label: str
    status_label: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingOpenQuestionsInput:
    """Optional local open-questions descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalDecisionLogEntry:
    """One descriptive local decision-log entry."""

    source_label: str
    decision_label: str
    decision_context_label: str
    reference_path: str
    owner_label: str
    status_label: str
    rationale_note: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingDecisionLogInput:
    """Optional local decision-log descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalFollowUpRegisterEntry:
    """One descriptive local follow-up register entry."""

    source_label: str
    follow_up_label: str
    related_section_label: str
    reference_path: str
    owner_label: str
    status_label: str
    tracking_note: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingFollowUpRegisterInput:
    """Optional local follow-up register descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalVersionNoteEntry:
    """One descriptive local version-note entry."""

    source_label: str
    version_label: str
    artifact_path: str
    change_summary_label: str
    owner_label: str
    status_label: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingVersionNotesInput:
    """Optional local version-notes descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalDistributionChecklistEntry:
    """One descriptive local distribution-checklist entry."""

    source_label: str
    distribution_item_label: str
    artifact_path: str
    readiness_status_label: str
    owner_label: str
    review_note: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingDistributionChecklistInput:
    """Optional local distribution-checklist descriptor that was not supplied."""

    display_label: str
    local_path: str


@dataclass(frozen=True, slots=True)
class LocalHandoffNoteEntry:
    """One descriptive local handoff-note entry."""

    source_label: str
    handoff_label: str
    artifact_path: str
    recipient_label: str
    status_label: str
    handoff_note: str
    limitation_note: str


@dataclass(frozen=True, slots=True)
class MissingHandoffNotesInput:
    """Optional local handoff-notes descriptor that was not supplied."""

    display_label: str
    local_path: str


VALIDATION_SUMMARY_STATUSES = frozenset(("pass", "fail", "skipped"))
SOURCE_CONTENT_FIELDS = frozenset(
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
    term_glossary_entries, missing_term_glossary = _read_term_glossary(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    assumption_register_entries, missing_assumption_register = _read_assumption_register(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    coverage_matrix_entries, missing_coverage_matrix = _read_coverage_matrix(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    reproducibility_steps, missing_reproducibility = _read_reproducibility_checklist(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    risk_review_entries, missing_risk_review = _read_risk_review(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    data_rights_entries, missing_data_rights = _read_data_rights_review(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    artifact_inventory_entries, missing_artifact_inventory = _read_artifact_inventory(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    appendix_index_entries, missing_appendix_index = _read_appendix_index(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    limitation_register_entries, missing_limitation_register = _read_limitation_register(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    open_question_entries, missing_open_questions = _read_open_questions(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    decision_log_entries, missing_decision_log = _read_decision_log(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    follow_up_entries, missing_follow_up_register = _read_follow_up_register(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    version_note_entries, missing_version_notes = _read_version_notes(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    distribution_entries, missing_distribution_checklist = _read_distribution_checklist(
        pack_input.report_input_manifest,
        manifest_entries,
    )
    handoff_note_entries, missing_handoff_notes = _read_handoff_notes(
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
            term_glossary_entries=term_glossary_entries,
            missing_term_glossary=missing_term_glossary,
            assumption_register_entries=assumption_register_entries,
            missing_assumption_register=missing_assumption_register,
            coverage_matrix_entries=coverage_matrix_entries,
            missing_coverage_matrix=missing_coverage_matrix,
            reproducibility_steps=reproducibility_steps,
            missing_reproducibility=missing_reproducibility,
            risk_review_entries=risk_review_entries,
            missing_risk_review=missing_risk_review,
            data_rights_entries=data_rights_entries,
            missing_data_rights=missing_data_rights,
            artifact_inventory_entries=artifact_inventory_entries,
            missing_artifact_inventory=missing_artifact_inventory,
            appendix_index_entries=appendix_index_entries,
            missing_appendix_index=missing_appendix_index,
            limitation_register_entries=limitation_register_entries,
            missing_limitation_register=missing_limitation_register,
            open_question_entries=open_question_entries,
            missing_open_questions=missing_open_questions,
            decision_log_entries=decision_log_entries,
            missing_decision_log=missing_decision_log,
            follow_up_entries=follow_up_entries,
            missing_follow_up_register=missing_follow_up_register,
            version_note_entries=version_note_entries,
            missing_version_notes=missing_version_notes,
            distribution_entries=distribution_entries,
            missing_distribution_checklist=missing_distribution_checklist,
            handoff_note_entries=handoff_note_entries,
            missing_handoff_notes=missing_handoff_notes,
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
        term_glossary_entry_count=len(term_glossary_entries),
        assumption_register_entry_count=len(assumption_register_entries),
        coverage_matrix_entry_count=len(coverage_matrix_entries),
        reproducibility_checklist_step_count=len(reproducibility_steps),
        risk_review_entry_count=len(risk_review_entries),
        data_rights_review_entry_count=len(data_rights_entries),
        artifact_inventory_entry_count=len(artifact_inventory_entries),
        appendix_index_entry_count=len(appendix_index_entries),
        limitation_register_entry_count=len(limitation_register_entries),
        open_questions_entry_count=len(open_question_entries),
        decision_log_entry_count=len(decision_log_entries),
        follow_up_register_entry_count=len(follow_up_entries),
        version_notes_entry_count=len(version_note_entries),
        distribution_checklist_entry_count=len(distribution_entries),
        handoff_notes_entry_count=len(handoff_note_entries),
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
            f"term_glossary_entries={pack.term_glossary_entry_count}",
            f"assumption_register_entries={pack.assumption_register_entry_count}",
            f"coverage_matrix_entries={pack.coverage_matrix_entry_count}",
            f"reproducibility_checklist_steps={pack.reproducibility_checklist_step_count}",
            f"risk_review_entries={pack.risk_review_entry_count}",
            f"data_rights_review_entries={pack.data_rights_review_entry_count}",
            f"artifact_inventory_entries={pack.artifact_inventory_entry_count}",
            f"appendix_index_entries={pack.appendix_index_entry_count}",
            f"limitation_register_entries={pack.limitation_register_entry_count}",
            f"open_questions_entries={pack.open_questions_entry_count}",
            f"decision_log_entries={pack.decision_log_entry_count}",
            f"follow_up_register_entries={pack.follow_up_register_entry_count}",
            f"version_notes_entries={pack.version_notes_entry_count}",
            f"distribution_checklist_entries={pack.distribution_checklist_entry_count}",
            f"handoff_notes_entries={pack.handoff_notes_entry_count}",
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
    _reject_source_content_fields(payload, path=path, descriptor_label="citation-index")

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
        _reject_source_content_fields(item, path=path, descriptor_label="citation-index")
        parsed_citations.append(
            _parse_citation_index_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_citations)


def _reject_source_content_fields(
    payload: dict[str, object], *, path: Path, descriptor_label: str
) -> None:
    found = sorted(
        key
        for key in payload
        if key.lower().replace("-", "_") in SOURCE_CONTENT_FIELDS
    )
    if found:
        msg = f"{path}: local {descriptor_label} descriptor contains source-content field(s)"
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


def _read_term_glossary(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalTermGlossaryEntry, ...], tuple[MissingTermGlossaryInput, ...]]:
    if manifest_path is None:
        return (), ()

    terms: list[LocalTermGlossaryEntry] = []
    missing: list[MissingTermGlossaryInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_term_glossary":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local term-glossary input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingTermGlossaryInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        terms.extend(
            _read_term_glossary_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(terms), tuple(missing)


def _read_term_glossary_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalTermGlossaryEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local term-glossary descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="term-glossary")

    terms = payload.get("terms")
    if not isinstance(terms, list):
        msg = f"{path}: local term-glossary descriptor must contain a terms list"
        raise ValueError(msg)

    parsed_terms: list[LocalTermGlossaryEntry] = []
    for index, item in enumerate(terms, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local term-glossary entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="term-glossary")
        parsed_terms.append(
            _parse_term_glossary_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_terms)


def _parse_term_glossary_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalTermGlossaryEntry:
    required_fields = (
        "term_label",
        "source_path",
        "definition",
        "usage_scope",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local term-glossary entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    source_path = str(item["source_path"])
    parsed = urlparse(source_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local term-glossary entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalTermGlossaryEntry(
        source_label=source_label,
        term_label=str(item["term_label"]),
        source_path=source_path,
        definition=str(item["definition"]),
        usage_scope=str(item["usage_scope"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_assumption_register(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalAssumptionRegisterEntry, ...],
    tuple[MissingAssumptionRegisterInput, ...],
]:
    if manifest_path is None:
        return (), ()

    assumptions: list[LocalAssumptionRegisterEntry] = []
    missing: list[MissingAssumptionRegisterInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_assumption_register":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local assumption-register input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingAssumptionRegisterInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        assumptions.extend(
            _read_assumption_register_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(assumptions), tuple(missing)


def _read_assumption_register_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalAssumptionRegisterEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local assumption-register descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="assumption-register")

    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, list):
        msg = f"{path}: local assumption-register descriptor must contain an assumptions list"
        raise ValueError(msg)

    parsed_assumptions: list[LocalAssumptionRegisterEntry] = []
    for index, item in enumerate(assumptions, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local assumption-register entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="assumption-register")
        parsed_assumptions.append(
            _parse_assumption_register_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_assumptions)


def _parse_assumption_register_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalAssumptionRegisterEntry:
    required_fields = (
        "assumption_label",
        "source_path",
        "rationale",
        "scope",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local assumption-register entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    source_path = str(item["source_path"])
    parsed = urlparse(source_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local assumption-register entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalAssumptionRegisterEntry(
        source_label=source_label,
        assumption_label=str(item["assumption_label"]),
        source_path=source_path,
        rationale=str(item["rationale"]),
        scope=str(item["scope"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_coverage_matrix(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalCoverageMatrixEntry, ...], tuple[MissingCoverageMatrixInput, ...]]:
    if manifest_path is None:
        return (), ()

    coverage_entries: list[LocalCoverageMatrixEntry] = []
    missing: list[MissingCoverageMatrixInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_coverage_matrix":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local coverage-matrix input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingCoverageMatrixInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        coverage_entries.extend(
            _read_coverage_matrix_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(coverage_entries), tuple(missing)


def _read_coverage_matrix_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalCoverageMatrixEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local coverage-matrix descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="coverage-matrix")

    coverage = payload.get("coverage")
    if not isinstance(coverage, list):
        msg = f"{path}: local coverage-matrix descriptor must contain a coverage list"
        raise ValueError(msg)

    parsed_coverage: list[LocalCoverageMatrixEntry] = []
    for index, item in enumerate(coverage, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local coverage-matrix entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="coverage-matrix")
        parsed_coverage.append(
            _parse_coverage_matrix_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_coverage)


def _parse_coverage_matrix_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalCoverageMatrixEntry:
    required_fields = (
        "section_label",
        "source_path",
        "input_label",
        "validation_label",
        "coverage_note",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local coverage-matrix entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    source_path = str(item["source_path"])
    parsed = urlparse(source_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local coverage-matrix entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalCoverageMatrixEntry(
        source_label=source_label,
        section_label=str(item["section_label"]),
        source_path=source_path,
        input_label=str(item["input_label"]),
        validation_label=str(item["validation_label"]),
        coverage_note=str(item["coverage_note"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_reproducibility_checklist(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalReproducibilityChecklistStep, ...],
    tuple[MissingReproducibilityChecklistInput, ...],
]:
    if manifest_path is None:
        return (), ()

    steps: list[LocalReproducibilityChecklistStep] = []
    missing: list[MissingReproducibilityChecklistInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_reproducibility_checklist":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local reproducibility-checklist "
                    f"input is missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingReproducibilityChecklistInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        steps.extend(
            _read_reproducibility_checklist_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(steps), tuple(missing)


def _read_reproducibility_checklist_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalReproducibilityChecklistStep, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local reproducibility-checklist descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(
        payload,
        path=path,
        descriptor_label="reproducibility-checklist",
    )

    steps = payload.get("steps")
    if not isinstance(steps, list):
        msg = f"{path}: local reproducibility-checklist descriptor must contain a steps list"
        raise ValueError(msg)

    parsed_steps: list[LocalReproducibilityChecklistStep] = []
    for index, item in enumerate(steps, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local reproducibility-checklist step {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(
            item,
            path=path,
            descriptor_label="reproducibility-checklist",
        )
        parsed_steps.append(
            _parse_reproducibility_checklist_step(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_steps)


def _parse_reproducibility_checklist_step(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalReproducibilityChecklistStep:
    required_fields = (
        "step_label",
        "artifact_path",
        "command_label",
        "environment_label",
        "expected_output_label",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local reproducibility-checklist step {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    artifact_path = str(item["artifact_path"])
    parsed = urlparse(artifact_path)
    if parsed.scheme or parsed.netloc:
        msg = (
            f"{path}: local reproducibility-checklist step {index} "
            "remote URL is not supported"
        )
        raise ValueError(msg)

    return LocalReproducibilityChecklistStep(
        source_label=source_label,
        step_label=str(item["step_label"]),
        artifact_path=artifact_path,
        command_label=str(item["command_label"]),
        environment_label=str(item["environment_label"]),
        expected_output_label=str(item["expected_output_label"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_risk_review(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[tuple[LocalRiskReviewEntry, ...], tuple[MissingRiskReviewInput, ...]]:
    if manifest_path is None:
        return (), ()

    risk_entries: list[LocalRiskReviewEntry] = []
    missing: list[MissingRiskReviewInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_risk_review":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local risk-review input is missing: "
                    f"{entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingRiskReviewInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        risk_entries.extend(
            _read_risk_review_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(risk_entries), tuple(missing)


def _read_risk_review_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalRiskReviewEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local risk-review descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="risk-review")

    risks = payload.get("risks")
    if not isinstance(risks, list):
        msg = f"{path}: local risk-review descriptor must contain a risks list"
        raise ValueError(msg)

    parsed_risks: list[LocalRiskReviewEntry] = []
    for index, item in enumerate(risks, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local risk-review entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="risk-review")
        parsed_risks.append(
            _parse_risk_review_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_risks)


def _parse_risk_review_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalRiskReviewEntry:
    required_fields = (
        "risk_control_label",
        "boundary_label",
        "mitigation_note",
        "review_status_label",
        "evidence_path",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local risk-review entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    evidence_path = str(item["evidence_path"])
    parsed = urlparse(evidence_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local risk-review entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalRiskReviewEntry(
        source_label=source_label,
        risk_control_label=str(item["risk_control_label"]),
        boundary_label=str(item["boundary_label"]),
        mitigation_note=str(item["mitigation_note"]),
        review_status_label=str(item["review_status_label"]),
        evidence_path=evidence_path,
        limitation_note=str(item["limitation_note"]),
    )


def _read_data_rights_review(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalDataRightsReviewEntry, ...],
    tuple[MissingDataRightsReviewInput, ...],
]:
    if manifest_path is None:
        return (), ()

    rights_entries: list[LocalDataRightsReviewEntry] = []
    missing: list[MissingDataRightsReviewInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_data_rights_review":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local data-rights-review input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingDataRightsReviewInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        rights_entries.extend(
            _read_data_rights_review_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(rights_entries), tuple(missing)


def _read_data_rights_review_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalDataRightsReviewEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local data-rights-review descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="data-rights-review")

    rights = payload.get("rights")
    if not isinstance(rights, list):
        msg = f"{path}: local data-rights-review descriptor must contain a rights list"
        raise ValueError(msg)

    parsed_rights: list[LocalDataRightsReviewEntry] = []
    for index, item in enumerate(rights, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local data-rights-review entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="data-rights-review")
        parsed_rights.append(
            _parse_data_rights_review_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_rights)


def _parse_data_rights_review_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalDataRightsReviewEntry:
    required_fields = (
        "data_label",
        "rights_status_label",
        "permitted_use_note",
        "restriction_note",
        "evidence_path",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local data-rights-review entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    evidence_path = str(item["evidence_path"])
    parsed = urlparse(evidence_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local data-rights-review entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalDataRightsReviewEntry(
        source_label=source_label,
        data_label=str(item["data_label"]),
        rights_status_label=str(item["rights_status_label"]),
        permitted_use_note=str(item["permitted_use_note"]),
        restriction_note=str(item["restriction_note"]),
        evidence_path=evidence_path,
        limitation_note=str(item["limitation_note"]),
    )


def _read_artifact_inventory(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalArtifactInventoryEntry, ...],
    tuple[MissingArtifactInventoryInput, ...],
]:
    if manifest_path is None:
        return (), ()

    artifact_entries: list[LocalArtifactInventoryEntry] = []
    missing: list[MissingArtifactInventoryInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_artifact_inventory":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local artifact-inventory input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingArtifactInventoryInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        artifact_entries.extend(
            _read_artifact_inventory_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(artifact_entries), tuple(missing)


def _read_artifact_inventory_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalArtifactInventoryEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local artifact-inventory descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="artifact-inventory")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        msg = f"{path}: local artifact-inventory descriptor must contain an artifacts list"
        raise ValueError(msg)

    parsed_artifacts: list[LocalArtifactInventoryEntry] = []
    for index, item in enumerate(artifacts, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local artifact-inventory entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="artifact-inventory")
        parsed_artifacts.append(
            _parse_artifact_inventory_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_artifacts)


def _parse_artifact_inventory_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalArtifactInventoryEntry:
    required_fields = (
        "artifact_label",
        "artifact_type_label",
        "local_path",
        "generation_source_label",
        "intended_report_use",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local artifact-inventory entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    local_path = str(item["local_path"])
    parsed = urlparse(local_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local artifact-inventory entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalArtifactInventoryEntry(
        source_label=source_label,
        artifact_label=str(item["artifact_label"]),
        artifact_type_label=str(item["artifact_type_label"]),
        local_path=local_path,
        generation_source_label=str(item["generation_source_label"]),
        intended_report_use=str(item["intended_report_use"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_appendix_index(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalAppendixIndexEntry, ...],
    tuple[MissingAppendixIndexInput, ...],
]:
    if manifest_path is None:
        return (), ()

    appendix_entries: list[LocalAppendixIndexEntry] = []
    missing: list[MissingAppendixIndexInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_appendix_index":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local appendix-index input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingAppendixIndexInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        appendix_entries.extend(
            _read_appendix_index_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(appendix_entries), tuple(missing)


def _read_appendix_index_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalAppendixIndexEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local appendix-index descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="appendix-index")

    appendices = payload.get("appendices")
    if not isinstance(appendices, list):
        msg = f"{path}: local appendix-index descriptor must contain an appendices list"
        raise ValueError(msg)

    parsed_appendices: list[LocalAppendixIndexEntry] = []
    for index, item in enumerate(appendices, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local appendix-index entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="appendix-index")
        parsed_appendices.append(
            _parse_appendix_index_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_appendices)


def _parse_appendix_index_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalAppendixIndexEntry:
    required_fields = (
        "appendix_label",
        "report_section_label",
        "artifact_path",
        "appendix_purpose_note",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local appendix-index entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    artifact_path = str(item["artifact_path"])
    parsed = urlparse(artifact_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local appendix-index entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalAppendixIndexEntry(
        source_label=source_label,
        appendix_label=str(item["appendix_label"]),
        report_section_label=str(item["report_section_label"]),
        artifact_path=artifact_path,
        appendix_purpose_note=str(item["appendix_purpose_note"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_limitation_register(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalLimitationRegisterEntry, ...],
    tuple[MissingLimitationRegisterInput, ...],
]:
    if manifest_path is None:
        return (), ()

    limitation_entries: list[LocalLimitationRegisterEntry] = []
    missing: list[MissingLimitationRegisterInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_limitation_register":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local limitation-register input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingLimitationRegisterInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        limitation_entries.extend(
            _read_limitation_register_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(limitation_entries), tuple(missing)


def _read_limitation_register_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalLimitationRegisterEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local limitation-register descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="limitation-register")

    limitations = payload.get("limitations")
    if not isinstance(limitations, list):
        msg = f"{path}: local limitation-register descriptor must contain a limitations list"
        raise ValueError(msg)

    parsed_limitations: list[LocalLimitationRegisterEntry] = []
    for index, item in enumerate(limitations, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local limitation-register entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="limitation-register")
        parsed_limitations.append(
            _parse_limitation_register_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_limitations)


def _parse_limitation_register_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalLimitationRegisterEntry:
    required_fields = (
        "limitation_label",
        "affected_section_label",
        "reference_path",
        "scope_note",
        "mitigation_note",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local limitation-register entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    reference_path = str(item["reference_path"])
    parsed = urlparse(reference_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local limitation-register entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalLimitationRegisterEntry(
        source_label=source_label,
        limitation_label=str(item["limitation_label"]),
        affected_section_label=str(item["affected_section_label"]),
        reference_path=reference_path,
        scope_note=str(item["scope_note"]),
        mitigation_note=str(item["mitigation_note"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_open_questions(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalOpenQuestionEntry, ...],
    tuple[MissingOpenQuestionsInput, ...],
]:
    if manifest_path is None:
        return (), ()

    question_entries: list[LocalOpenQuestionEntry] = []
    missing: list[MissingOpenQuestionsInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_open_questions":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local open-questions input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingOpenQuestionsInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        question_entries.extend(
            _read_open_questions_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(question_entries), tuple(missing)


def _read_open_questions_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalOpenQuestionEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local open-questions descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="open-questions")

    questions = payload.get("questions")
    if not isinstance(questions, list):
        msg = f"{path}: local open-questions descriptor must contain a questions list"
        raise ValueError(msg)

    parsed_questions: list[LocalOpenQuestionEntry] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local open-questions entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="open-questions")
        parsed_questions.append(
            _parse_open_question_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_questions)


def _parse_open_question_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalOpenQuestionEntry:
    required_fields = (
        "question_label",
        "affected_section_label",
        "reference_path",
        "owner_label",
        "status_label",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local open-questions entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    reference_path = str(item["reference_path"])
    parsed = urlparse(reference_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local open-questions entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalOpenQuestionEntry(
        source_label=source_label,
        question_label=str(item["question_label"]),
        affected_section_label=str(item["affected_section_label"]),
        reference_path=reference_path,
        owner_label=str(item["owner_label"]),
        status_label=str(item["status_label"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_decision_log(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalDecisionLogEntry, ...],
    tuple[MissingDecisionLogInput, ...],
]:
    if manifest_path is None:
        return (), ()

    decision_entries: list[LocalDecisionLogEntry] = []
    missing: list[MissingDecisionLogInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_decision_log":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local decision-log input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingDecisionLogInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        decision_entries.extend(
            _read_decision_log_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(decision_entries), tuple(missing)


def _read_decision_log_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalDecisionLogEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local decision-log descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="decision-log")

    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        msg = f"{path}: local decision-log descriptor must contain a decisions list"
        raise ValueError(msg)

    parsed_decisions: list[LocalDecisionLogEntry] = []
    for index, item in enumerate(decisions, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local decision-log entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="decision-log")
        parsed_decisions.append(
            _parse_decision_log_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_decisions)


def _parse_decision_log_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalDecisionLogEntry:
    required_fields = (
        "decision_label",
        "decision_context_label",
        "reference_path",
        "owner_label",
        "status_label",
        "rationale_note",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local decision-log entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    reference_path = str(item["reference_path"])
    parsed = urlparse(reference_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local decision-log entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalDecisionLogEntry(
        source_label=source_label,
        decision_label=str(item["decision_label"]),
        decision_context_label=str(item["decision_context_label"]),
        reference_path=reference_path,
        owner_label=str(item["owner_label"]),
        status_label=str(item["status_label"]),
        rationale_note=str(item["rationale_note"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_follow_up_register(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalFollowUpRegisterEntry, ...],
    tuple[MissingFollowUpRegisterInput, ...],
]:
    if manifest_path is None:
        return (), ()

    follow_up_entries: list[LocalFollowUpRegisterEntry] = []
    missing: list[MissingFollowUpRegisterInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_follow_up_register":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local follow-up-register input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingFollowUpRegisterInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        follow_up_entries.extend(
            _read_follow_up_register_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(follow_up_entries), tuple(missing)


def _read_follow_up_register_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalFollowUpRegisterEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local follow-up-register descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(
        payload,
        path=path,
        descriptor_label="follow-up-register",
    )

    follow_ups = payload.get("follow_ups")
    if not isinstance(follow_ups, list):
        msg = (
            f"{path}: local follow-up-register descriptor must contain a "
            "follow_ups list"
        )
        raise ValueError(msg)

    parsed_follow_ups: list[LocalFollowUpRegisterEntry] = []
    for index, item in enumerate(follow_ups, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local follow-up-register entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(
            item,
            path=path,
            descriptor_label="follow-up-register",
        )
        parsed_follow_ups.append(
            _parse_follow_up_register_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_follow_ups)


def _parse_follow_up_register_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalFollowUpRegisterEntry:
    required_fields = (
        "follow_up_label",
        "related_section_label",
        "reference_path",
        "owner_label",
        "status_label",
        "tracking_note",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local follow-up-register entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    reference_path = str(item["reference_path"])
    parsed = urlparse(reference_path)
    if parsed.scheme or parsed.netloc:
        msg = (
            f"{path}: local follow-up-register entry {index} "
            "remote URL is not supported"
        )
        raise ValueError(msg)

    return LocalFollowUpRegisterEntry(
        source_label=source_label,
        follow_up_label=str(item["follow_up_label"]),
        related_section_label=str(item["related_section_label"]),
        reference_path=reference_path,
        owner_label=str(item["owner_label"]),
        status_label=str(item["status_label"]),
        tracking_note=str(item["tracking_note"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_version_notes(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalVersionNoteEntry, ...],
    tuple[MissingVersionNotesInput, ...],
]:
    if manifest_path is None:
        return (), ()

    version_entries: list[LocalVersionNoteEntry] = []
    missing: list[MissingVersionNotesInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_version_notes":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local version-notes input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingVersionNotesInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        version_entries.extend(
            _read_version_notes_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(version_entries), tuple(missing)


def _read_version_notes_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalVersionNoteEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local version-notes descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="version-notes")

    versions = payload.get("versions")
    if not isinstance(versions, list):
        msg = f"{path}: local version-notes descriptor must contain a versions list"
        raise ValueError(msg)

    parsed_versions: list[LocalVersionNoteEntry] = []
    for index, item in enumerate(versions, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local version-notes entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="version-notes")
        parsed_versions.append(
            _parse_version_note_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_versions)


def _parse_version_note_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalVersionNoteEntry:
    required_fields = (
        "version_label",
        "artifact_path",
        "change_summary_label",
        "owner_label",
        "status_label",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local version-notes entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    artifact_path = str(item["artifact_path"])
    parsed = urlparse(artifact_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local version-notes entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalVersionNoteEntry(
        source_label=source_label,
        version_label=str(item["version_label"]),
        artifact_path=artifact_path,
        change_summary_label=str(item["change_summary_label"]),
        owner_label=str(item["owner_label"]),
        status_label=str(item["status_label"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_distribution_checklist(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalDistributionChecklistEntry, ...],
    tuple[MissingDistributionChecklistInput, ...],
]:
    if manifest_path is None:
        return (), ()

    checklist_entries: list[LocalDistributionChecklistEntry] = []
    missing: list[MissingDistributionChecklistInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_distribution_checklist":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local distribution-checklist input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingDistributionChecklistInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        checklist_entries.extend(
            _read_distribution_checklist_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(checklist_entries), tuple(missing)


def _read_distribution_checklist_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalDistributionChecklistEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local distribution-checklist descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(
        payload,
        path=path,
        descriptor_label="distribution-checklist",
    )

    items = payload.get("items")
    if not isinstance(items, list):
        msg = f"{path}: local distribution-checklist descriptor must contain an items list"
        raise ValueError(msg)

    parsed_items: list[LocalDistributionChecklistEntry] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local distribution-checklist entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(
            item,
            path=path,
            descriptor_label="distribution-checklist",
        )
        parsed_items.append(
            _parse_distribution_checklist_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_items)


def _parse_distribution_checklist_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalDistributionChecklistEntry:
    required_fields = (
        "distribution_item_label",
        "artifact_path",
        "readiness_status_label",
        "owner_label",
        "review_note",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local distribution-checklist entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    artifact_path = str(item["artifact_path"])
    parsed = urlparse(artifact_path)
    if parsed.scheme or parsed.netloc:
        msg = (
            f"{path}: local distribution-checklist entry {index} "
            "remote URL is not supported"
        )
        raise ValueError(msg)

    return LocalDistributionChecklistEntry(
        source_label=source_label,
        distribution_item_label=str(item["distribution_item_label"]),
        artifact_path=artifact_path,
        readiness_status_label=str(item["readiness_status_label"]),
        owner_label=str(item["owner_label"]),
        review_note=str(item["review_note"]),
        limitation_note=str(item["limitation_note"]),
    )


def _read_handoff_notes(
    manifest_path: Path | None,
    manifest_entries: tuple[ReportInputManifestEntry, ...],
) -> tuple[
    tuple[LocalHandoffNoteEntry, ...],
    tuple[MissingHandoffNotesInput, ...],
]:
    if manifest_path is None:
        return (), ()

    handoff_entries: list[LocalHandoffNoteEntry] = []
    missing: list[MissingHandoffNotesInput] = []
    for entry in manifest_entries:
        if entry.input_kind != "local_handoff_notes":
            continue
        descriptor_path = _resolve_manifest_local_path(manifest_path, entry.local_path)
        if not descriptor_path.exists():
            if entry.required:
                msg = (
                    f"{manifest_path}: required local handoff-notes input is "
                    f"missing: {entry.local_path}"
                )
                raise ValueError(msg)
            missing.append(
                MissingHandoffNotesInput(
                    display_label=entry.display_label,
                    local_path=entry.local_path,
                )
            )
            continue

        handoff_entries.extend(
            _read_handoff_notes_descriptor(
                descriptor_path,
                source_label=entry.display_label,
            )
        )
    return tuple(handoff_entries), tuple(missing)


def _read_handoff_notes_descriptor(
    path: Path, *, source_label: str
) -> tuple[LocalHandoffNoteEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path}: local handoff-notes descriptor must contain a JSON object"
        raise ValueError(msg)
    _reject_secret_like_fields(payload, path=path)
    _reject_source_content_fields(payload, path=path, descriptor_label="handoff-notes")

    notes = payload.get("notes")
    if not isinstance(notes, list):
        msg = f"{path}: local handoff-notes descriptor must contain a notes list"
        raise ValueError(msg)

    parsed_notes: list[LocalHandoffNoteEntry] = []
    for index, item in enumerate(notes, start=1):
        if not isinstance(item, dict):
            msg = f"{path}: local handoff-notes entry {index} must be an object"
            raise ValueError(msg)
        _reject_secret_like_fields(item, path=path)
        _reject_source_content_fields(item, path=path, descriptor_label="handoff-notes")
        parsed_notes.append(
            _parse_handoff_note_entry(
                item,
                path=path,
                index=index,
                source_label=source_label,
            )
        )
    return tuple(parsed_notes)


def _parse_handoff_note_entry(
    item: dict[str, object], *, path: Path, index: int, source_label: str
) -> LocalHandoffNoteEntry:
    required_fields = (
        "handoff_label",
        "artifact_path",
        "recipient_label",
        "status_label",
        "handoff_note",
        "limitation_note",
    )
    missing = [field for field in required_fields if field not in item]
    if missing:
        msg = (
            f"{path}: local handoff-notes entry {index} "
            f"missing field(s): {', '.join(missing)}"
        )
        raise ValueError(msg)

    artifact_path = str(item["artifact_path"])
    parsed = urlparse(artifact_path)
    if parsed.scheme or parsed.netloc:
        msg = f"{path}: local handoff-notes entry {index} remote URL is not supported"
        raise ValueError(msg)

    return LocalHandoffNoteEntry(
        source_label=source_label,
        handoff_label=str(item["handoff_label"]),
        artifact_path=artifact_path,
        recipient_label=str(item["recipient_label"]),
        status_label=str(item["status_label"]),
        handoff_note=str(item["handoff_note"]),
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
    term_glossary_entries: tuple[LocalTermGlossaryEntry, ...],
    missing_term_glossary: tuple[MissingTermGlossaryInput, ...],
    assumption_register_entries: tuple[LocalAssumptionRegisterEntry, ...],
    missing_assumption_register: tuple[MissingAssumptionRegisterInput, ...],
    coverage_matrix_entries: tuple[LocalCoverageMatrixEntry, ...],
    missing_coverage_matrix: tuple[MissingCoverageMatrixInput, ...],
    reproducibility_steps: tuple[LocalReproducibilityChecklistStep, ...],
    missing_reproducibility: tuple[MissingReproducibilityChecklistInput, ...],
    risk_review_entries: tuple[LocalRiskReviewEntry, ...],
    missing_risk_review: tuple[MissingRiskReviewInput, ...],
    data_rights_entries: tuple[LocalDataRightsReviewEntry, ...],
    missing_data_rights: tuple[MissingDataRightsReviewInput, ...],
    artifact_inventory_entries: tuple[LocalArtifactInventoryEntry, ...],
    missing_artifact_inventory: tuple[MissingArtifactInventoryInput, ...],
    appendix_index_entries: tuple[LocalAppendixIndexEntry, ...],
    missing_appendix_index: tuple[MissingAppendixIndexInput, ...],
    limitation_register_entries: tuple[LocalLimitationRegisterEntry, ...],
    missing_limitation_register: tuple[MissingLimitationRegisterInput, ...],
    open_question_entries: tuple[LocalOpenQuestionEntry, ...],
    missing_open_questions: tuple[MissingOpenQuestionsInput, ...],
    decision_log_entries: tuple[LocalDecisionLogEntry, ...],
    missing_decision_log: tuple[MissingDecisionLogInput, ...],
    follow_up_entries: tuple[LocalFollowUpRegisterEntry, ...],
    missing_follow_up_register: tuple[MissingFollowUpRegisterInput, ...],
    version_note_entries: tuple[LocalVersionNoteEntry, ...],
    missing_version_notes: tuple[MissingVersionNotesInput, ...],
    distribution_entries: tuple[LocalDistributionChecklistEntry, ...],
    missing_distribution_checklist: tuple[MissingDistributionChecklistInput, ...],
    handoff_note_entries: tuple[LocalHandoffNoteEntry, ...],
    missing_handoff_notes: tuple[MissingHandoffNotesInput, ...],
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
            "## Local Term Glossary",
            "",
            _render_term_glossary(term_glossary_entries, missing_term_glossary),
            "",
            "## Local Assumption Register",
            "",
            _render_assumption_register(
                assumption_register_entries,
                missing_assumption_register,
            ),
            "",
            "## Local Coverage Matrix",
            "",
            _render_coverage_matrix(coverage_matrix_entries, missing_coverage_matrix),
            "",
            "## Local Reproducibility Checklist",
            "",
            _render_reproducibility_checklist(
                reproducibility_steps,
                missing_reproducibility,
            ),
            "",
            "## Local Risk Review",
            "",
            _render_risk_review(risk_review_entries, missing_risk_review),
            "",
            "## Local Data Rights Review",
            "",
            _render_data_rights_review(data_rights_entries, missing_data_rights),
            "",
            "## Local Artifact Inventory",
            "",
            _render_artifact_inventory(
                artifact_inventory_entries,
                missing_artifact_inventory,
            ),
            "",
            "## Local Appendix Index",
            "",
            _render_appendix_index(appendix_index_entries, missing_appendix_index),
            "",
            "## Local Limitation Register",
            "",
            _render_limitation_register(
                limitation_register_entries,
                missing_limitation_register,
            ),
            "",
            "## Local Open Questions",
            "",
            _render_open_questions(open_question_entries, missing_open_questions),
            "",
            "## Local Decision Log",
            "",
            _render_decision_log(decision_log_entries, missing_decision_log),
            "",
            "## Local Follow-Up Register",
            "",
            _render_follow_up_register(
                follow_up_entries,
                missing_follow_up_register,
            ),
            "",
            "## Local Version Notes",
            "",
            _render_version_notes(version_note_entries, missing_version_notes),
            "",
            "## Local Distribution Checklist",
            "",
            _render_distribution_checklist(
                distribution_entries,
                missing_distribution_checklist,
            ),
            "",
            "## Local Handoff Notes",
            "",
            _render_handoff_notes(handoff_note_entries, missing_handoff_notes),
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
            "- Distribution checklist inputs are reviewer-supplied metadata only; this "
            "pack does not approve distribution or verify rights.",
            "- Handoff-note inputs are reviewer-supplied metadata only; this pack does "
            "not approve distribution or verify rights.",
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


def _render_term_glossary(
    terms: tuple[LocalTermGlossaryEntry, ...],
    missing_inputs: tuple[MissingTermGlossaryInput, ...],
) -> str:
    if not terms and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local term glossary | not supplied |"

    rows = [
        "| source | term | source path | definition | usage scope | limitation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {term.source_label} | {term.term_label} | {term.source_path} | "
        f"{term.definition} | {term.usage_scope} | {term.limitation_note} |"
        for term in terms
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | "
        "not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_assumption_register(
    assumptions: tuple[LocalAssumptionRegisterEntry, ...],
    missing_inputs: tuple[MissingAssumptionRegisterInput, ...],
) -> str:
    if not assumptions and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local assumption register | not supplied |"

    rows = [
        "| source | assumption | source path | rationale | scope | limitation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {assumption.source_label} | {assumption.assumption_label} | "
        f"{assumption.source_path} | {assumption.rationale} | "
        f"{assumption.scope} | {assumption.limitation_note} |"
        for assumption in assumptions
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | "
        "not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_coverage_matrix(
    coverage_entries: tuple[LocalCoverageMatrixEntry, ...],
    missing_inputs: tuple[MissingCoverageMatrixInput, ...],
) -> str:
    if not coverage_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local coverage matrix | not supplied |"

    rows = [
        "| source | section | source path | input | validation | coverage note | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.section_label} | {entry.source_path} | "
        f"{entry.input_label} | {entry.validation_label} | {entry.coverage_note} | "
        f"{entry.limitation_note} |"
        for entry in coverage_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | "
        "not supplied | not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_reproducibility_checklist(
    steps: tuple[LocalReproducibilityChecklistStep, ...],
    missing_inputs: tuple[MissingReproducibilityChecklistInput, ...],
) -> str:
    if not steps and not missing_inputs:
        return (
            "| input | status |\n"
            "| --- | --- |\n"
            "| Local reproducibility checklist | not supplied |"
        )

    rows = [
        "| source | step | artifact path | command | environment | expected output | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {step.source_label} | {step.step_label} | {step.artifact_path} | "
        f"{step.command_label} | {step.environment_label} | "
        f"{step.expected_output_label} | {step.limitation_note} |"
        for step in steps
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | {missing_input.local_path} | "
        "not supplied | not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_risk_review(
    risk_entries: tuple[LocalRiskReviewEntry, ...],
    missing_inputs: tuple[MissingRiskReviewInput, ...],
) -> str:
    if not risk_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local risk review | not supplied |"

    rows = [
        "| source | risk control | boundary | mitigation | review status | "
        "evidence path | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.risk_control_label} | {entry.boundary_label} | "
        f"{entry.mitigation_note} | {entry.review_status_label} | {entry.evidence_path} | "
        f"{entry.limitation_note} |"
        for entry in risk_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"not supplied | not supplied | {missing_input.local_path} | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_data_rights_review(
    rights_entries: tuple[LocalDataRightsReviewEntry, ...],
    missing_inputs: tuple[MissingDataRightsReviewInput, ...],
) -> str:
    if not rights_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local data rights review | not supplied |"

    rows = [
        "| source | data | rights status | permitted use | restriction | "
        "evidence path | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.data_label} | {entry.rights_status_label} | "
        f"{entry.permitted_use_note} | {entry.restriction_note} | {entry.evidence_path} | "
        f"{entry.limitation_note} |"
        for entry in rights_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"not supplied | not supplied | {missing_input.local_path} | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_artifact_inventory(
    artifact_entries: tuple[LocalArtifactInventoryEntry, ...],
    missing_inputs: tuple[MissingArtifactInventoryInput, ...],
) -> str:
    if not artifact_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local artifact inventory | not supplied |"

    rows = [
        "| source | artifact | artifact type | local path | generation source | "
        "report use | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.artifact_label} | "
        f"{entry.artifact_type_label} | {entry.local_path} | "
        f"{entry.generation_source_label} | {entry.intended_report_use} | "
        f"{entry.limitation_note} |"
        for entry in artifact_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_appendix_index(
    appendix_entries: tuple[LocalAppendixIndexEntry, ...],
    missing_inputs: tuple[MissingAppendixIndexInput, ...],
) -> str:
    if not appendix_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local appendix index | not supplied |"

    rows = [
        "| source | appendix | report section | artifact path | purpose | limitation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.appendix_label} | "
        f"{entry.report_section_label} | {entry.artifact_path} | "
        f"{entry.appendix_purpose_note} | {entry.limitation_note} |"
        for entry in appendix_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_limitation_register(
    limitation_entries: tuple[LocalLimitationRegisterEntry, ...],
    missing_inputs: tuple[MissingLimitationRegisterInput, ...],
) -> str:
    if not limitation_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local limitation register | not supplied |"

    rows = [
        "| source | limitation | affected section | reference path | scope | "
        "mitigation | limitation note |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.limitation_label} | "
        f"{entry.affected_section_label} | {entry.reference_path} | "
        f"{entry.scope_note} | {entry.mitigation_note} | {entry.limitation_note} |"
        for entry in limitation_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_open_questions(
    question_entries: tuple[LocalOpenQuestionEntry, ...],
    missing_inputs: tuple[MissingOpenQuestionsInput, ...],
) -> str:
    if not question_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local open questions | not supplied |"

    rows = [
        "| source | question | affected section | reference path | owner | "
        "status | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.question_label} | "
        f"{entry.affected_section_label} | {entry.reference_path} | "
        f"{entry.owner_label} | {entry.status_label} | {entry.limitation_note} |"
        for entry in question_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_decision_log(
    decision_entries: tuple[LocalDecisionLogEntry, ...],
    missing_inputs: tuple[MissingDecisionLogInput, ...],
) -> str:
    if not decision_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local decision log | not supplied |"

    rows = [
        "| source | decision | context | reference path | owner | status | "
        "rationale | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.decision_label} | "
        f"{entry.decision_context_label} | {entry.reference_path} | "
        f"{entry.owner_label} | {entry.status_label} | "
        f"{entry.rationale_note} | {entry.limitation_note} |"
        for entry in decision_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied | "
        "not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_follow_up_register(
    follow_up_entries: tuple[LocalFollowUpRegisterEntry, ...],
    missing_inputs: tuple[MissingFollowUpRegisterInput, ...],
) -> str:
    if not follow_up_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local follow-up register | not supplied |"

    rows = [
        "| source | follow-up | related section | reference path | owner | "
        "status | tracking note | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.follow_up_label} | "
        f"{entry.related_section_label} | {entry.reference_path} | "
        f"{entry.owner_label} | {entry.status_label} | "
        f"{entry.tracking_note} | {entry.limitation_note} |"
        for entry in follow_up_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied | "
        "not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_version_notes(
    version_entries: tuple[LocalVersionNoteEntry, ...],
    missing_inputs: tuple[MissingVersionNotesInput, ...],
) -> str:
    if not version_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local version notes | not supplied |"

    rows = [
        "| source | version | artifact path | change summary | owner | status | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.version_label} | "
        f"{entry.artifact_path} | {entry.change_summary_label} | "
        f"{entry.owner_label} | {entry.status_label} | {entry.limitation_note} |"
        for entry in version_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied | "
        "not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_distribution_checklist(
    checklist_entries: tuple[LocalDistributionChecklistEntry, ...],
    missing_inputs: tuple[MissingDistributionChecklistInput, ...],
) -> str:
    if not checklist_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local distribution checklist | not supplied |"

    rows = [
        "| source | item | artifact path | readiness status | owner | review note | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.distribution_item_label} | "
        f"{entry.artifact_path} | {entry.readiness_status_label} | "
        f"{entry.owner_label} | {entry.review_note} | {entry.limitation_note} |"
        for entry in checklist_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied | "
        "not supplied | not supplied |"
        for missing_input in missing_inputs
    )
    return "\n".join(rows)


def _render_handoff_notes(
    handoff_entries: tuple[LocalHandoffNoteEntry, ...],
    missing_inputs: tuple[MissingHandoffNotesInput, ...],
) -> str:
    if not handoff_entries and not missing_inputs:
        return "| input | status |\n| --- | --- |\n| Local handoff notes | not supplied |"

    rows = [
        "| source | handoff | artifact path | recipient | status | handoff note | limitation |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {entry.source_label} | {entry.handoff_label} | "
        f"{entry.artifact_path} | {entry.recipient_label} | "
        f"{entry.status_label} | {entry.handoff_note} | {entry.limitation_note} |"
        for entry in handoff_entries
    )
    rows.extend(
        f"| {missing_input.display_label} | not supplied | "
        f"{missing_input.local_path} | not supplied | not supplied | "
        "not supplied | not supplied |"
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
