"""Strict activity-aware Phase 0F Demo read-only network controller."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from edmn_trader.adapters.kalshi.client import (
    validate_kalshi_identifier,
    validate_kalshi_market_identity,
)
from edmn_trader.adapters.kalshi.ws_auth import load_kalshi_ws_auth_config_from_env
from edmn_trader.adapters.kalshi.ws_runtime import validate_d2_runtime_artifacts
from edmn_trader.scripts.v2_readonly_campaign import (
    CANARY_SECONDS,
    CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
    RUNTIME_MARKET_SELECTION_MAX_ORDERBOOK_PROBES,
    DiscoveryRequestBudget,
    DiscoveryRequestPacer,
    SelectionProfile,
    discover_kalshi_demo_ws_market,
    run_kalshi_ws_campaign,
    run_kalshi_ws_smoke,
)

PHASE0F_DISCOVERY_REQUEST_LIMIT = 1_000
# Static baseline below the lowest documented default-cost read rate; no account query.
PHASE0F_DISCOVERY_CONSERVATIVE_REQUESTS_PER_SECOND = 10
PHASE0F_DISCOVERY_MIN_REQUEST_INTERVAL_SECONDS = (
    1 / PHASE0F_DISCOVERY_CONSERVATIVE_REQUESTS_PER_SECOND
)
PHASE0F_MAX_CANDIDATES = 2
PHASE0F_PROBE_SECONDS = 300
PHASE0F_MEASUREMENT_SECONDS = CANARY_SECONDS
PHASE0F_REQUEST_ATTEMPTS = 1


class Phase0FNetworkClassification(StrEnum):
    CONTROLLER_BLOCKED = "PHASE0F_CONTROLLER_BLOCKED"
    NO_ACTIVITY_AWARE_ELIGIBLE_CANDIDATE = (
        "PHASE0F_NO_ACTIVITY_AWARE_ELIGIBLE_CANDIDATE"
    )
    ACTIVITY_DISCOVERY_BLOCKED = "PHASE0F_ACTIVITY_DISCOVERY_BLOCKED"
    ACTIVITY_PROBES_NOT_DELTA_QUALIFIED = (
        "PHASE0F_ACTIVITY_PROBES_NOT_DELTA_QUALIFIED"
    )
    PROBE_BLOCKED = "PHASE0F_PROBE_BLOCKED"
    MEASUREMENT_BLOCKED = "PHASE0F_MEASUREMENT_BLOCKED"
    MEASUREMENT_SNAPSHOT_ONLY = "PHASE0F_MEASUREMENT_SNAPSHOT_ONLY"
    DELTA_MEASUREMENT_CAPTURED = "PHASE0F_DELTA_MEASUREMENT_CAPTURED"
    MEASUREMENT_NOT_QUALIFIED = "PHASE0F_MEASUREMENT_NOT_QUALIFIED"


@dataclass(frozen=True, slots=True)
class Phase0FNetworkResult:
    classification: Phase0FNetworkClassification
    activity_aware_candidate_qualified: bool
    bounded_probe_passed: bool
    measurement_started: bool
    measurement_qualified: bool
    delta_admitted: bool
    replay_semantics_supported: bool

    def to_public_record(self) -> dict[str, object]:
        """Return only non-correlatable Boolean/categorical controller status."""

        return {
            "classification": self.classification,
            "activity_aware_candidate_qualified": (
                self.activity_aware_candidate_qualified
            ),
            "bounded_probe_passed": self.bounded_probe_passed,
            "measurement_started": self.measurement_started,
            "measurement_qualified": self.measurement_qualified,
            "delta_admitted": self.delta_admitted,
            "replay_semantics_supported": self.replay_semantics_supported,
            "replay_qualified": False,
            "production_endpoint_used": False,
            "order_write_invoked": False,
            "live_gate": "disabled",
            "real_money_decision": "STRICT_NO_GO",
        }


def assess_phase0f_runtime(
    input_dir: Path,
    *,
    required_duration_seconds: int,
    phase: str,
    validator: Callable[[Path], Mapping[str, object]] = validate_d2_runtime_artifacts,
) -> dict[str, object]:
    """Derive only Boolean/categorical Phase 0F gates from closed artifacts."""

    if phase not in {"probe", "measurement"}:
        raise ValueError("phase must be probe or measurement")
    try:
        summary = json.loads(
            (input_dir / "campaign_summary.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        summary = {}
    if not isinstance(summary, Mapping):
        summary = {}
    validation = validator(input_dir)
    try:
        actual_elapsed = Decimal(str(summary.get("actual_elapsed_seconds")))
    except (InvalidOperation, TypeError):
        actual_elapsed = Decimal("-1")
    duration_gate = (
        summary.get("configured_duration_seconds") == required_duration_seconds
        and actual_elapsed.is_finite()
        and actual_elapsed >= required_duration_seconds
        and validation.get("duration_evidence") == "PASS"
    )
    controlled_exit = (
        summary.get("terminal_reason") == "bounded_duration_complete"
        and summary.get("stop_requested") is False
    )
    transport_gate = (
        summary.get("connection_established") is True
        and validation.get("transport_connectivity") == "PASS"
    )
    subscription_gate = (
        summary.get("subscription_acknowledged") is True
        and validation.get("subscription_status") == "PASS"
    )
    snapshot_admitted = _positive_int(
        summary.get("admitted_selected_snapshot_count")
    )
    delta_admitted = _positive_int(summary.get("admitted_selected_delta_count"))
    sequence_summaries = summary.get("sequence_summaries")
    sequence_safe = (
        validation.get("sequence_integrity") != "FAIL"
        and isinstance(sequence_summaries, list)
        and bool(sequence_summaries)
        and all(
            isinstance(item, Mapping)
            and item.get("aggregate_result") != "SEQUENCE_INTEGRITY_FAIL"
            for item in sequence_summaries
        )
    )
    rebuild_summaries = summary.get("rebuild_summaries")
    orderbook_rebuilds = (
        [
            item
            for item in rebuild_summaries
            if isinstance(item, Mapping) and _positive_int(item.get("frame_count"))
        ]
        if isinstance(rebuild_summaries, list)
        else []
    )
    rebuild_noninvalid = (
        validation.get("rebuild_integrity") != "FAIL"
        and bool(orderbook_rebuilds)
        and all(
            item.get("snapshot_first_admitted") is True
            and item.get("native_state_valid") is True
            and not item.get("invalidation_reasons")
            for item in orderbook_rebuilds
        )
    )
    segments = summary.get("segment_summaries")
    source_closed = (
        isinstance(segments, list)
        and bool(segments)
        and all(
            isinstance(segment, Mapping) and segment.get("segment_closed") is True
            for segment in segments
        )
    )
    lifecycle_valid = validation.get("market_lifecycle_validity") == "PASS"
    artifact_integrity = (
        validation.get("status") == "pass"
        and validation.get("artifact_integrity") == "PASS"
    )
    safety_gate = all(
        (
            summary.get("live_gate_status") == "disabled",
            summary.get("production_trading_enabled") is False,
            summary.get("executable_order_intent") is False,
            summary.get("production_endpoint_used") is False,
            summary.get("submit_attempts") == 0,
        )
    )
    qualified = all(
        (
            controlled_exit,
            duration_gate,
            transport_gate,
            subscription_gate,
            snapshot_admitted,
            delta_admitted,
            lifecycle_valid,
            sequence_safe,
            rebuild_noninvalid,
            artifact_integrity,
            source_closed,
            safety_gate,
        )
    )
    return {
        "qualified": qualified,
        "controlled_exit": controlled_exit,
        "duration_gate": duration_gate,
        "transport_gate": transport_gate,
        "subscription_gate": subscription_gate,
        "snapshot_admitted": snapshot_admitted,
        "delta_admitted": delta_admitted,
        "lifecycle_valid": lifecycle_valid,
        "sequence_integrity": validation.get("sequence_integrity", "UNKNOWN"),
        "rebuild_integrity": validation.get("rebuild_integrity", "UNKNOWN"),
        "artifact_integrity": artifact_integrity,
        "source_closed": source_closed,
        "safety_gate": safety_gate,
    }


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def run_phase0f_activity_measurement(
    *,
    output_root: Path,
    demo_readonly_opt_in: bool,
    now: datetime | None = None,
    auth_preflight: Callable[[], object] = load_kalshi_ws_auth_config_from_env,
    discovery: Callable[..., dict[str, object]] = discover_kalshi_demo_ws_market,
    probe_runner: Callable[..., dict[str, object]] = run_kalshi_ws_smoke,
    measurement_runner: Callable[..., dict[str, object]] = run_kalshi_ws_campaign,
    runtime_assessor: Callable[..., Mapping[str, object]] = assess_phase0f_runtime,
) -> Phase0FNetworkResult:
    """Run one strictly bounded activity-aware discovery/probe/measurement flow."""

    if demo_readonly_opt_in is not True:
        raise ValueError("explicit Demo read-only opt-in is required")
    root = _prepare_private_root(output_root)
    auth_preflight()
    selected_at = now or datetime.now(UTC)
    budget = DiscoveryRequestBudget(
        limit=PHASE0F_DISCOVERY_REQUEST_LIMIT,
        pacer=DiscoveryRequestPacer(
            minimum_interval_seconds=(
                PHASE0F_DISCOVERY_MIN_REQUEST_INTERVAL_SECONDS
            )
        ),
    )
    selection = discovery(
        duration_seconds=PHASE0F_MEASUREMENT_SECONDS,
        safety_buffer_seconds=CANARY_SELECTION_SAFETY_BUFFER_SECONDS,
        selected_at_utc=selected_at,
        selection_profile=SelectionProfile.CANARY,
        eligible_market_limit=PHASE0F_MAX_CANDIDATES,
        max_orderbook_probes=RUNTIME_MARKET_SELECTION_MAX_ORDERBOOK_PROBES,
        require_recent_activity=True,
        request_budget=budget,
        max_request_attempts=PHASE0F_REQUEST_ATTEMPTS,
    )
    _write_private_json(root / "activity_discovery.json", selection)
    candidates = selection.get("eligible_candidates")
    if not isinstance(candidates, list) or not candidates:
        no_candidate_codes = {"DEMO_NO_ELIGIBLE_MARKET", "DEMO_NO_OPEN_MARKETS"}
        classification = (
            Phase0FNetworkClassification.NO_ACTIVITY_AWARE_ELIGIBLE_CANDIDATE
            if selection.get("blocker_code") in no_candidate_codes
            else Phase0FNetworkClassification.ACTIVITY_DISCOVERY_BLOCKED
        )
        return _finish_controller(
            root,
            budget,
            Phase0FNetworkResult(
                classification=classification,
                activity_aware_candidate_qualified=False,
                bounded_probe_passed=False,
                measurement_started=False,
                measurement_qualified=False,
                delta_admitted=False,
                replay_semantics_supported=False,
            ),
        )

    qualified_candidate: tuple[str, str] | None = None
    for index, candidate in enumerate(candidates[:PHASE0F_MAX_CANDIDATES], start=1):
        identity = _candidate_identity(candidate)
        if identity is None:
            return _finish_controller(
                root,
                budget,
                _blocked_network_result(
                    Phase0FNetworkClassification.ACTIVITY_DISCOVERY_BLOCKED
                ),
            )
        market_ticker, event_ticker = identity
        probe_root = root / f"probe-{index}"
        probe_result = probe_runner(
            output_dir=probe_root,
            campaign_id=f"<owner-private-phase0f-probe-{index}>",
            duration_seconds=PHASE0F_PROBE_SECONDS,
            max_markets=1,
            pinned_market_ticker=market_ticker,
            expected_event_ticker=event_ticker,
            selection_duration_seconds=PHASE0F_MEASUREMENT_SECONDS,
            require_recent_activity=True,
            request_budget=budget,
            max_request_attempts=PHASE0F_REQUEST_ATTEMPTS,
        )
        blocker_code = probe_result.get("blocker_code")
        if blocker_code == "DEMO_PINNED_MARKET_REVALIDATION_REJECTED":
            continue
        if blocker_code is not None:
            return _finish_controller(
                root,
                budget,
                _blocked_network_result(
                    Phase0FNetworkClassification.PROBE_BLOCKED,
                    activity_candidate=True,
                ),
            )
        assessment = runtime_assessor(
            probe_root,
            required_duration_seconds=PHASE0F_PROBE_SECONDS,
            phase="probe",
        )
        if assessment.get("qualified") is True:
            qualified_candidate = identity
            break
        if not _probe_allows_candidate_fallback(assessment):
            return _finish_controller(
                root,
                budget,
                _blocked_network_result(
                    Phase0FNetworkClassification.PROBE_BLOCKED,
                    activity_candidate=True,
                ),
            )

    if qualified_candidate is None:
        return _finish_controller(
            root,
            budget,
            Phase0FNetworkResult(
                classification=(
                    Phase0FNetworkClassification.ACTIVITY_PROBES_NOT_DELTA_QUALIFIED
                ),
                activity_aware_candidate_qualified=True,
                bounded_probe_passed=False,
                measurement_started=False,
                measurement_qualified=False,
                delta_admitted=False,
                replay_semantics_supported=False,
            ),
        )

    market_ticker, event_ticker = qualified_candidate
    measurement_root = root / "measurement"
    measurement_result = measurement_runner(
        output_dir=measurement_root,
        campaign_id="<owner-private-phase0f-measurement>",
        duration_seconds=PHASE0F_MEASUREMENT_SECONDS,
        max_markets=1,
        pinned_market_ticker=market_ticker,
        expected_event_ticker=event_ticker,
        selection_duration_seconds=PHASE0F_MEASUREMENT_SECONDS,
        require_recent_activity=True,
        request_budget=budget,
        max_request_attempts=PHASE0F_REQUEST_ATTEMPTS,
    )
    if measurement_result.get("blocker_code") is not None:
        return _finish_controller(
            root,
            budget,
            Phase0FNetworkResult(
                classification=Phase0FNetworkClassification.MEASUREMENT_BLOCKED,
                activity_aware_candidate_qualified=True,
                bounded_probe_passed=True,
                measurement_started=False,
                measurement_qualified=False,
                delta_admitted=False,
                replay_semantics_supported=False,
            ),
        )
    measurement = runtime_assessor(
        measurement_root,
        required_duration_seconds=PHASE0F_MEASUREMENT_SECONDS,
        phase="measurement",
    )
    delta_admitted = measurement.get("delta_admitted") is True
    qualified = measurement.get("qualified") is True
    replay_supported = (
        qualified
        and measurement.get("sequence_integrity") == "PASS"
        and measurement.get("rebuild_integrity") == "PASS"
    )
    if qualified:
        classification = Phase0FNetworkClassification.DELTA_MEASUREMENT_CAPTURED
    elif measurement.get("snapshot_admitted") is True and not delta_admitted:
        classification = Phase0FNetworkClassification.MEASUREMENT_SNAPSHOT_ONLY
    else:
        classification = Phase0FNetworkClassification.MEASUREMENT_NOT_QUALIFIED
    return _finish_controller(
        root,
        budget,
        Phase0FNetworkResult(
            classification=classification,
            activity_aware_candidate_qualified=True,
            bounded_probe_passed=True,
            measurement_started=True,
            measurement_qualified=qualified,
            delta_admitted=delta_admitted,
            replay_semantics_supported=replay_supported,
        ),
    )


def _probe_allows_candidate_fallback(assessment: Mapping[str, object]) -> bool:
    operational_gates = (
        "controlled_exit",
        "duration_gate",
        "transport_gate",
        "subscription_gate",
        "lifecycle_valid",
        "artifact_integrity",
        "source_closed",
        "safety_gate",
    )
    if not all(assessment.get(gate) is True for gate in operational_gates):
        return False
    if assessment.get("delta_admitted") is not False:
        return False
    if assessment.get("sequence_integrity") == "FAIL":
        return False
    if assessment.get("rebuild_integrity") == "FAIL":
        return False
    return not (
        assessment.get("snapshot_admitted") is True
        and assessment.get("rebuild_integrity") != "PASS"
    )


def _blocked_network_result(
    classification: Phase0FNetworkClassification,
    *,
    activity_candidate: bool = False,
) -> Phase0FNetworkResult:
    return Phase0FNetworkResult(
        classification=classification,
        activity_aware_candidate_qualified=activity_candidate,
        bounded_probe_passed=False,
        measurement_started=False,
        measurement_qualified=False,
        delta_admitted=False,
        replay_semantics_supported=False,
    )


def _finish_controller(
    root: Path,
    budget: DiscoveryRequestBudget,
    result: Phase0FNetworkResult,
) -> Phase0FNetworkResult:
    _write_private_json(
        root / "controller_result.json",
        {
            **result.to_public_record(),
            "discovery_request_limit": budget.limit,
            "discovery_requests_consumed": budget.consumed,
        },
    )
    return result


def _write_private_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = (json.dumps(payload, default=str, sort_keys=True) + "\n").encode()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, path)


def _candidate_identity(candidate: object) -> tuple[str, str] | None:
    if not isinstance(candidate, Mapping):
        return None
    metadata = candidate.get("market_metadata")
    if not isinstance(metadata, Mapping):
        return None
    try:
        return (
            validate_kalshi_market_identity(metadata),
            validate_kalshi_identifier(metadata.get("event_ticker")),
        )
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--demo-readonly-opt-in", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_phase0f_activity_measurement(
            output_root=args.output_root,
            demo_readonly_opt_in=args.demo_readonly_opt_in,
        )
    except Exception:
        blocked = Phase0FNetworkResult(
            classification=Phase0FNetworkClassification.CONTROLLER_BLOCKED,
            activity_aware_candidate_qualified=False,
            bounded_probe_passed=False,
            measurement_started=False,
            measurement_qualified=False,
            delta_admitted=False,
            replay_semantics_supported=False,
        )
        print(json.dumps(blocked.to_public_record(), sort_keys=True))
        return 2
    print(json.dumps(result.to_public_record(), sort_keys=True))
    return 0


def _prepare_private_root(path: Path) -> Path:
    if not path.is_absolute() or _has_symlink_component(path):
        raise ValueError("Phase 0F output root must be an absolute non-symlink path")
    root = path.resolve(strict=False)
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ValueError("Phase 0F output root must remain outside Git")
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(root, 0o700)
    return root


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
