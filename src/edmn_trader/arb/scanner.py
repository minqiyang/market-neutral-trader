"""Offline scanner for same-market YES/NO complement candidates."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from edmn_trader.arb.complement import (
    ComplementArbCandidate,
    ComplementArbDecision,
    ComplementArbInput,
    compute_canonical_yes_side_cross_candidate,
    compute_kalshi_complement_candidate,
)
from edmn_trader.core.models import ZERO
from edmn_trader.data.replay import ReplaySession
from edmn_trader.fees import (
    FeeEstimate,
    FeeEstimateStatus,
    missing_fee_estimate,
    supplied_fee_estimate,
    unknown_fee_estimate,
)

InputKind = Literal["fixture", "snapshot_jsonl"]


@dataclass(frozen=True, slots=True)
class ComplementScanRecord:
    """One offline scan record; never an order intent."""

    source: str
    input_kind: InputKind
    sequence: int
    candidate: ComplementArbCandidate
    fee_source_note: str
    data_quality_flags: tuple[str, ...]
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComplementScanReport:
    """Deterministic offline scan report."""

    input_source: str
    input_kind: InputKind
    records: tuple[ComplementScanRecord, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.records)

    @property
    def paper_candidate_count(self) -> int:
        return _decision_count(self.records, ComplementArbDecision.PAPER_CANDIDATE)

    @property
    def audit_only_count(self) -> int:
        return _decision_count(self.records, ComplementArbDecision.AUDIT_ONLY)

    @property
    def reject_count(self) -> int:
        return _decision_count(self.records, ComplementArbDecision.REJECT)

    @property
    def missing_fee_count(self) -> int:
        return _fee_status_count(self.records, FeeEstimateStatus.MISSING)

    @property
    def unknown_fee_count(self) -> int:
        return _fee_status_count(self.records, FeeEstimateStatus.UNKNOWN)

    @property
    def rejection_reason_counts(self) -> Counter[str]:
        reasons: Counter[str] = Counter()
        for record in self.records:
            reasons.update(record.rejection_reasons)
        return reasons

    @property
    def data_quality_flag_counts(self) -> Counter[str]:
        flags: Counter[str] = Counter()
        for record in self.records:
            flags.update(record.data_quality_flags)
        return flags


def scan_fixture_file(path: Path) -> ComplementScanReport:
    """Scan a local fixture JSON file."""

    payload = _read_fixture_payload(path)
    source = _fixture_source(payload, path)
    books = _fixture_books(payload)
    records = tuple(
        _scan_fixture_book(
            book,
            source=source,
            sequence=sequence,
            top_level=payload if isinstance(payload, Mapping) else {},
        )
        for sequence, book in enumerate(books, start=1)
    )
    return ComplementScanReport(
        input_source=source,
        input_kind="fixture",
        records=records,
    )


def scan_snapshot_jsonl_file(
    path: Path,
    *,
    fee_status: FeeEstimateStatus = FeeEstimateStatus.MISSING,
    fee_per_contract: Decimal | None = None,
    fee_source_note: str = "scanner fee assumption",
    strict: bool = True,
) -> ComplementScanReport:
    """Scan existing local snapshot JSONL with canonical YES-side best bid/ask."""

    fee_estimate = _fee_estimate(
        venue="snapshot",
        status=fee_status,
        fee_per_contract=fee_per_contract,
        source_note=fee_source_note,
    )
    records: list[ComplementScanRecord] = []
    for frame in ReplaySession.from_path(path, strict=strict):
        snapshot = frame.snapshot
        book = snapshot.normalized_orderbook
        if book.best_bid is None or book.best_ask is None:
            msg = "snapshot scan requires both best bid and best ask"
            raise ValueError(msg)
        frame_fee = _fee_estimate(
            venue=snapshot.exchange,
            status=fee_estimate.status,
            fee_per_contract=fee_estimate.fee_per_contract,
            source_note=fee_estimate.source_note,
        )
        data_flags = tuple(sorted(set(snapshot.tags)))
        stale_book = "stale_book" in data_flags or "invalid_book_state" in data_flags
        candidate = compute_canonical_yes_side_cross_candidate(
            venue=snapshot.exchange,
            market_id=snapshot.ticker,
            best_yes_bid=book.best_bid.price,
            best_yes_ask=book.best_ask.price,
            yes_bid_size=book.best_bid.quantity,
            yes_ask_size=book.best_ask.quantity,
            fee_estimate=frame_fee,
            stale_book=stale_book,
        )
        records.append(
            ComplementScanRecord(
                source=str(path),
                input_kind="snapshot_jsonl",
                sequence=frame.sequence,
                candidate=candidate,
                fee_source_note=frame_fee.source_note,
                data_quality_flags=data_flags,
                rejection_reasons=_rejection_reasons(candidate),
            )
        )
    return ComplementScanReport(
        input_source=str(path),
        input_kind="snapshot_jsonl",
        records=tuple(records),
    )


def write_jsonl_report(path: Path, report: ComplementScanReport) -> None:
    """Write deterministic JSONL candidate records."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(_record_to_json(record), sort_keys=True, separators=(",", ":"))
        for record in report.records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def render_markdown_summary(report: ComplementScanReport) -> str:
    """Render a deterministic Markdown scan summary."""

    lines = [
        "# Offline Complement Scanner Summary",
        "",
        "This report contains audit/paper research records only. It is not a trade "
        "recommendation and contains no executable order intent.",
        "",
        f"- Input source: `{report.input_source}`",
        f"- Input kind: `{report.input_kind}`",
        f"- Candidate count: {report.candidate_count}",
        f"- paper_candidate count: {report.paper_candidate_count}",
        f"- audit_only count: {report.audit_only_count}",
        f"- reject count: {report.reject_count}",
        f"- missing fee count: {report.missing_fee_count}",
        f"- unknown fee count: {report.unknown_fee_count}",
        "",
        "## Rejection Reason Counts",
        "",
    ]
    lines.extend(_counter_lines(report.rejection_reason_counts))
    lines.extend(["", "## Data-Quality Flags", ""])
    lines.extend(_counter_lines(report.data_quality_flag_counts))
    return "\n".join(lines) + "\n"


def write_markdown_summary(path: Path, report: ComplementScanReport) -> None:
    """Write a deterministic Markdown scan summary."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_summary(report), encoding="utf-8")


def _scan_fixture_book(
    book: Mapping[str, Any],
    *,
    source: str,
    sequence: int,
    top_level: Mapping[str, Any],
) -> ComplementScanRecord:
    venue = _expect_str(book, "venue")
    fee_status = _fee_status(book, top_level=top_level)
    fee_estimate = _fee_estimate(
        venue=venue,
        status=fee_status,
        fee_per_contract=_optional_decimal(book, "fee_per_contract", top_level=top_level),
        source_note=_optional_str(book, "fee_source_note", top_level=top_level)
        or "scanner fixture fee assumption",
    )
    data_quality_flags = _data_quality_flags(book)
    candidate = compute_kalshi_complement_candidate(
        ComplementArbInput(
            venue=venue,
            market_id=_expect_str(book, "market_id"),
            best_yes_bid=_expect_decimal(book, "best_yes_bid"),
            best_no_bid=_expect_decimal(book, "best_no_bid"),
            yes_bid_size=_expect_decimal(book, "yes_bid_size"),
            no_bid_size=_expect_decimal(book, "no_bid_size"),
            fee_estimate=fee_estimate,
            estimated_slippage_per_contract=_decimal_with_default(
                book,
                "estimated_slippage_per_contract",
                top_level=top_level,
            ),
            failed_leg_reserve_per_contract=_decimal_with_default(
                book,
                "failed_leg_reserve_per_contract",
                top_level=top_level,
            ),
            minimum_net_edge_per_contract=_decimal_with_default(
                book,
                "minimum_net_edge_per_contract",
                top_level=top_level,
            ),
            stale_book=_stale_or_invalid(book, data_quality_flags),
        )
    )
    return ComplementScanRecord(
        source=source,
        input_kind="fixture",
        sequence=sequence,
        candidate=candidate,
        fee_source_note=fee_estimate.source_note,
        data_quality_flags=data_quality_flags,
        rejection_reasons=_rejection_reasons(candidate),
    )


def _read_fixture_payload(path: Path) -> Mapping[str, Any] | list[Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = "fixture must be valid JSON"
        raise ValueError(msg) from exc
    if not isinstance(payload, Mapping | list):
        msg = "fixture root must be an object or list"
        raise ValueError(msg)
    return payload


def _fixture_source(payload: Mapping[str, Any] | list[Any], path: Path) -> str:
    if isinstance(payload, Mapping):
        source = payload.get("source")
        if source is not None:
            if not isinstance(source, str):
                msg = "source must be a string when present"
                raise ValueError(msg)
            return source
    return str(path)


def _fixture_books(payload: Mapping[str, Any] | list[Any]) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        books = payload
    else:
        books = payload.get("markets", payload.get("books"))
    if not isinstance(books, list):
        msg = "fixture must contain a markets or books list"
        raise ValueError(msg)
    if not all(isinstance(book, Mapping) for book in books):
        msg = "fixture books must be objects"
        raise ValueError(msg)
    return list(books)


def _fee_status(book: Mapping[str, Any], *, top_level: Mapping[str, Any]) -> FeeEstimateStatus:
    value = _optional_str(book, "fee_status", top_level=top_level) or "missing"
    try:
        return FeeEstimateStatus(value)
    except ValueError as exc:
        msg = "fee_status must be supplied, missing, or unknown"
        raise ValueError(msg) from exc


def _fee_estimate(
    *,
    venue: str,
    status: FeeEstimateStatus,
    fee_per_contract: Decimal | None,
    source_note: str,
) -> FeeEstimate:
    if status is FeeEstimateStatus.SUPPLIED:
        if fee_per_contract is None:
            msg = "supplied fee_status requires fee_per_contract"
            raise ValueError(msg)
        return supplied_fee_estimate(
            venue=venue,
            fee_per_contract=fee_per_contract,
            source_note=source_note,
        )
    if status is FeeEstimateStatus.MISSING:
        return missing_fee_estimate(venue=venue, source_note=source_note)
    return unknown_fee_estimate(venue=venue, source_note=source_note)


def _data_quality_flags(book: Mapping[str, Any]) -> tuple[str, ...]:
    value = book.get("data_quality_flags")
    flags: set[str] = set()
    if value is not None:
        if not isinstance(value, list) or not all(isinstance(flag, str) for flag in value):
            msg = "data_quality_flags must be a string list when present"
            raise ValueError(msg)
        flags.update(value)
    if book.get("stale_book") is True:
        flags.add("stale_book")
    if book.get("invalid_book_state") is True:
        flags.add("invalid_book_state")
    return tuple(sorted(flags))


def _stale_or_invalid(book: Mapping[str, Any], flags: Sequence[str]) -> bool:
    stale_value = book.get("stale_book", False)
    invalid_value = book.get("invalid_book_state", False)
    if not isinstance(stale_value, bool):
        msg = "stale_book must be a boolean when present"
        raise ValueError(msg)
    if not isinstance(invalid_value, bool):
        msg = "invalid_book_state must be a boolean when present"
        raise ValueError(msg)
    return stale_value or invalid_value or "stale_book" in flags or "invalid_book_state" in flags


def _rejection_reasons(candidate: ComplementArbCandidate) -> tuple[str, ...]:
    if candidate.decision is ComplementArbDecision.PAPER_CANDIDATE:
        return ()
    reasons: set[str] = set()
    reasons.update(
        flag
        for flag in candidate.flags
        if flag
        in {
            "stale_book",
            "insufficient_depth",
            "missing_fee_model",
            "unknown_fee_model",
        }
    )
    if candidate.gross_edge_per_contract <= ZERO:
        reasons.add("no_complement_edge")
    elif candidate.net_edge_per_contract <= candidate.gross_edge_per_contract:
        if candidate.estimated_fee_per_contract is not None:
            reasons.add("fee_adjustment")
        if candidate.estimated_slippage_per_contract > ZERO:
            reasons.add("slippage_adjustment")
        if candidate.failed_leg_reserve_per_contract > ZERO:
            reasons.add("failed_leg_reserve")
    if candidate.decision is ComplementArbDecision.REJECT:
        reasons.add("not_paper_candidate")
    return tuple(sorted(reasons))


def _record_to_json(record: ComplementScanRecord) -> dict[str, Any]:
    candidate = record.candidate
    return {
        "candidate_size": str(candidate.candidate_size),
        "data_quality_flags": list(record.data_quality_flags),
        "decision": candidate.decision.value,
        "executable_order_intent": False,
        "failed_leg_reserve_per_contract": str(candidate.failed_leg_reserve_per_contract),
        "fee_source_note": record.fee_source_note,
        "fee_status": candidate.fee_status.value,
        "flags": list(candidate.flags),
        "gross_edge_per_contract": str(candidate.gross_edge_per_contract),
        "input_kind": record.input_kind,
        "market_id": candidate.market_id,
        "net_edge_per_contract": str(candidate.net_edge_per_contract),
        "record_type": "offline_complement_research_candidate",
        "rejection_reasons": list(record.rejection_reasons),
        "research_use": "audit_or_paper_research_record_only",
        "sequence": record.sequence,
        "source": record.source,
        "total_estimated_net_edge": str(candidate.total_estimated_net_edge),
        "venue": candidate.venue,
    }


def _counter_lines(counter: Counter[str]) -> list[str]:
    if not counter:
        return ["- none: 0"]
    return [f"- {key}: {counter[key]}" for key in sorted(counter)]


def _decision_count(
    records: Iterable[ComplementScanRecord],
    decision: ComplementArbDecision,
) -> int:
    return sum(1 for record in records if record.candidate.decision is decision)


def _fee_status_count(
    records: Iterable[ComplementScanRecord],
    status: FeeEstimateStatus,
) -> int:
    return sum(1 for record in records if record.candidate.fee_status is status)


def _expect_str(record: Mapping[str, Any], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return value


def _optional_str(
    record: Mapping[str, Any],
    field_name: str,
    *,
    top_level: Mapping[str, Any],
) -> str | None:
    value = record.get(field_name, top_level.get(field_name))
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{field_name} must be a string when present"
        raise ValueError(msg)
    return value


def _expect_decimal(record: Mapping[str, Any], field_name: str) -> Decimal:
    if field_name not in record:
        msg = f"{field_name} is required"
        raise ValueError(msg)
    return _parse_decimal(record[field_name], field_name)


def _optional_decimal(
    record: Mapping[str, Any],
    field_name: str,
    *,
    top_level: Mapping[str, Any],
) -> Decimal | None:
    value = record.get(field_name, top_level.get(field_name))
    if value is None:
        return None
    return _parse_decimal(value, field_name)


def _decimal_with_default(
    record: Mapping[str, Any],
    field_name: str,
    *,
    top_level: Mapping[str, Any],
) -> Decimal:
    value = record.get(field_name, top_level.get(field_name, "0"))
    return _parse_decimal(value, field_name)


def _parse_decimal(value: Any, field_name: str) -> Decimal:
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string"
        raise ValueError(msg)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ValueError(msg) from exc
