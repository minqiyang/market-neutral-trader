"""Exchange-agnostic equities research data models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class EquityFundamentalFact:
    """One normalized public fundamentals fact for equities research."""

    cik: str
    entity_name: str
    taxonomy: str
    concept: str
    label: str
    unit: str
    value: Decimal
    fiscal_year: int
    fiscal_period: str
    form: str
    filed: str
    end_date: str
    accession_number: str
