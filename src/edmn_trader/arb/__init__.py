"""Offline complement-arbitrage candidate models."""

from edmn_trader.arb.complement import (
    ComplementArbCandidate,
    ComplementArbDecision,
    ComplementArbInput,
    compute_canonical_yes_side_cross_candidate,
    compute_kalshi_complement_candidate,
)
from edmn_trader.arb.fill_simulation import (
    FillPolicy,
    FillSimulationInput,
    FillSimulationResult,
    simulate_taker_fill,
    write_fill_simulation_jsonl,
    write_fill_simulation_markdown,
)
from edmn_trader.arb.scanner import (
    ComplementScanRecord,
    ComplementScanReport,
    render_markdown_summary,
    scan_fixture_file,
    scan_snapshot_jsonl_file,
    write_jsonl_report,
    write_markdown_summary,
)

__all__ = [
    "ComplementArbCandidate",
    "ComplementArbDecision",
    "ComplementArbInput",
    "ComplementScanRecord",
    "ComplementScanReport",
    "FillPolicy",
    "FillSimulationInput",
    "FillSimulationResult",
    "compute_canonical_yes_side_cross_candidate",
    "compute_kalshi_complement_candidate",
    "render_markdown_summary",
    "scan_fixture_file",
    "scan_snapshot_jsonl_file",
    "simulate_taker_fill",
    "write_fill_simulation_jsonl",
    "write_fill_simulation_markdown",
    "write_jsonl_report",
    "write_markdown_summary",
]
