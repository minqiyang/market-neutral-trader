"""SEC EDGAR companyfacts normalization helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from edmn_trader.research.equities import EquityFundamentalFact


class SecEdgarResponseError(ValueError):
    """Raised when an SEC EDGAR public response cannot be normalized."""


def normalize_sec_company_facts(raw: dict[str, Any]) -> tuple[EquityFundamentalFact, ...]:
    """Normalize SEC companyfacts JSON into exchange-agnostic research facts."""

    cik = _format_cik(raw.get("cik"))
    entity_name = _require_str(raw.get("entityName"), field_name="entityName")
    facts = raw.get("facts")
    if not isinstance(facts, dict):
        msg = "SEC companyfacts payload must contain a facts object"
        raise SecEdgarResponseError(msg)

    normalized: list[EquityFundamentalFact] = []
    for taxonomy, concepts in facts.items():
        if not isinstance(concepts, dict):
            continue
        for concept, concept_payload in concepts.items():
            if not isinstance(concept_payload, dict):
                continue
            normalized.extend(
                _normalize_concept(
                    cik=cik,
                    entity_name=entity_name,
                    taxonomy=str(taxonomy),
                    concept=str(concept),
                    concept_payload=concept_payload,
                )
            )
    return tuple(normalized)


def _normalize_concept(
    *,
    cik: str,
    entity_name: str,
    taxonomy: str,
    concept: str,
    concept_payload: dict[str, Any],
) -> list[EquityFundamentalFact]:
    units = concept_payload.get("units")
    if not isinstance(units, dict):
        msg = f"SEC companyfacts concept {concept} must contain units"
        raise SecEdgarResponseError(msg)

    label = str(concept_payload.get("label", concept))
    facts: list[EquityFundamentalFact] = []
    for unit, unit_facts in units.items():
        if not isinstance(unit_facts, list):
            msg = f"SEC companyfacts unit {unit} for {concept} must be a list"
            raise SecEdgarResponseError(msg)
        for raw_fact in unit_facts:
            if not isinstance(raw_fact, dict):
                msg = f"SEC companyfacts entries for {concept} must be objects"
                raise SecEdgarResponseError(msg)
            facts.append(
                EquityFundamentalFact(
                    cik=cik,
                    entity_name=entity_name,
                    taxonomy=taxonomy,
                    concept=concept,
                    label=label,
                    unit=str(unit),
                    value=_parse_decimal(raw_fact.get("val")),
                    fiscal_year=_parse_int(raw_fact.get("fy"), field_name="fiscal year"),
                    fiscal_period=_require_str(raw_fact.get("fp"), field_name="fiscal period"),
                    form=_require_str(raw_fact.get("form"), field_name="form"),
                    filed=_require_str(raw_fact.get("filed"), field_name="filed date"),
                    end_date=_require_str(raw_fact.get("end"), field_name="end date"),
                    accession_number=_require_str(
                        raw_fact.get("accn"), field_name="accession number"
                    ),
                )
            )
    return facts


def _format_cik(value: Any) -> str:
    try:
        return f"{int(str(value)):010d}"
    except (TypeError, ValueError) as exc:
        msg = "SEC companyfacts cik must be integer-compatible"
        raise SecEdgarResponseError(msg) from exc


def _parse_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = "SEC companyfacts value must be decimal-compatible"
        raise SecEdgarResponseError(msg) from exc


def _parse_int(value: Any, *, field_name: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        msg = f"SEC companyfacts {field_name} must be integer-compatible"
        raise SecEdgarResponseError(msg) from exc


def _require_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        msg = f"SEC companyfacts {field_name} is required"
        raise SecEdgarResponseError(msg)
    return value
