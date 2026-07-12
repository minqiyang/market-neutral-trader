"""D2A-D2D runtime evidence assembly for Kalshi Demo read-only WebSockets."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from itertools import chain
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from edmn_trader.adapters.kalshi.client import KalshiDemoMarketDataClient
from edmn_trader.adapters.kalshi.public_evidence import (
    ConnectionEvidenceEvent,
    ConnectionEvidenceType,
    KalshiRestLifecycleEvidence,
    KeepaliveStatus,
    LifecycleStatus,
    LifecycleValidity,
    build_public_trade_stream,
    evaluate_evidence_freshness,
    record_rest_lifecycle,
)
from edmn_trader.adapters.kalshi.ws_auth import KalshiWsAuthConfig
from edmn_trader.adapters.kalshi.ws_book_rebuild import (
    KalshiWsBookRebuilder,
    PricingMode,
    SegmentValidity,
)
from edmn_trader.adapters.kalshi.ws_events import (
    CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION,
    KALSHI_WS_RAW_SCHEMA_VERSION,
    LEGACY_CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION,
    AdmissionStatus,
    ExclusionReason,
    KalshiWsRawEvent,
    SegmentBoundaryReason,
    SequenceState,
    SubscriptionBindingObservation,
    SubscriptionBindingState,
    SubscriptionRequestEvidence,
    normalize_native_envelope,
)
from edmn_trader.adapters.kalshi.ws_recorder import (
    REQUIRED_PUBLIC_CHANNELS,
    KalshiWsRecorderConfig,
    WebSocketFactory,
    record_kalshi_demo_ws_orderbook,
    subscription_ack_channels,
)
from edmn_trader.data.evidence_classifier import (
    EvidenceDimensions,
    EvidenceStatus,
    build_evidence_timing,
    classify_duration_evidence,
    classify_evidence,
)
from edmn_trader.data.evidence_durability import (
    EVIDENCE_CHAIN_SCHEMA_VERSION,
    EVIDENCE_CHECKPOINT_SCHEMA_VERSION,
    EVIDENCE_SEGMENT_START_SCHEMA_VERSION,
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    EvidenceSegmentWriter,
    RecoveryResult,
    chain_genesis_hash,
    recover_unterminated_segment,
    verify_segment_chain,
)
from edmn_trader.data.evidence_policy import (
    V2_THRESHOLD_POLICY,
    EvidenceThresholdPolicy,
)
from edmn_trader.data.payload_safety import (
    validate_no_private_account_payload,
    validate_no_secret_payload,
)

D2_RUNTIME_SCHEMA_VERSION = "edmn.kalshi.ws.runtime.v2"
D2_RUNTIME_RECORD_SCHEMA_VERSION = "edmn.kalshi.ws.runtime_record.v1"
OPEN_STATUS_INTERVAL_SECONDS = 60
_HEX_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_BAD_SEQUENCE_STATES = {
    SequenceState.SEQUENCE_GAP_DETECTED,
    SequenceState.SEQUENCE_OUT_OF_ORDER,
    SequenceState.SEQUENCE_DUPLICATE,
    SequenceState.RESYNC_REQUIRED,
    SequenceState.UNRECOVERED_GAP,
}
_REQUIRED_SEGMENT_SUMMARY_FIELDS = {
    "schema_version",
    "segment_id",
    "segment_created",
    "segment_closed",
    "created_at_utc",
    "closed_at_utc",
    "terminal_reason",
    "rotation_reason",
    "integrity_scope",
    "last_committed_local_row_index",
    "byte_offset",
    "genesis_hash",
    "terminal_chain_hash",
    "closed_file_sha256",
    "backup_verification_state",
    "retention_deletion_eligible",
}


@dataclass(frozen=True, slots=True)
class RuntimeCodeProvenance:
    public_code_commit: str
    branch: str
    remote: str
    dirty_state: bool

    def __post_init__(self) -> None:
        commit = self.public_code_commit.lower()
        if not _HEX_COMMIT.fullmatch(commit):
            raise ValueError("public code commit must be a hexadecimal Git commit")
        remote = _sanitize_git_remote(self.remote)
        if not self.branch or not remote or not isinstance(self.dirty_state, bool):
            raise ValueError("complete runtime code provenance is required")
        object.__setattr__(self, "public_code_commit", commit)
        object.__setattr__(self, "remote", remote)

    def to_record(self) -> dict[str, object]:
        return {
            "public_code_commit": self.public_code_commit,
            "branch": self.branch,
            "remote": self.remote,
            "dirty_state": self.dirty_state,
        }


def collect_runtime_code_provenance(repo_root: Path) -> RuntimeCodeProvenance:
    root = Path(repo_root)

    def git(*args: str) -> str:
        return subprocess.run(
            ("git", *args),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    return RuntimeCodeProvenance(
        public_code_commit=git("rev-parse", "HEAD"),
        branch=git("branch", "--show-current") or "DETACHED_HEAD",
        remote=git("remote", "get-url", "origin"),
        dirty_state=bool(git("status", "--porcelain")),
    )


def _sanitize_git_remote(remote: str) -> str:
    parts = urlsplit(remote)
    if not parts.scheme or not parts.hostname:
        return remote
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    netloc = f"{host}:{parts.port}" if parts.port is not None else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _require_empty_runtime_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError("new D2 runtime requires an empty artifact root")


def _contained_artifact_path(
    root: Path,
    value: object,
    *,
    reject_symlinks: bool = False,
) -> Path:
    relative = Path(str(value))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("artifact path must be relative to the runtime root")
    resolved_root = root.resolve()
    candidate = resolved_root / relative
    resolved_candidate = candidate.resolve(strict=False)
    if (
        resolved_candidate == resolved_root
        or resolved_root not in resolved_candidate.parents
    ):
        raise ValueError("artifact path escapes the runtime root")
    if reject_symlinks:
        current = resolved_root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError(f"artifact path must not be a symlink: {value}")
    return candidate


def _runtime_metadata_path(root: Path, name: str) -> Path:
    path = _contained_artifact_path(root, name)
    resolved_root = root.resolve()
    current = resolved_root
    for part in Path(name).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"runtime metadata path must not be a symlink: {name}")
    return path


def run_d2_kalshi_ws_runtime(
    *,
    output_dir: Path,
    campaign_id: str,
    mode: str,
    duration_seconds: int,
    market_metadata: Mapping[str, object],
    market_selection: Mapping[str, object],
    auth: KalshiWsAuthConfig,
    provenance: RuntimeCodeProvenance,
    websocket_factory: WebSocketFactory | None = None,
    lifecycle_provider: Callable[[str], Mapping[str, object]] | None = None,
    now: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] | None = None,
    monotonic_ns: Callable[[], int] | None = None,
    max_events: int = 500,
    max_reconnects: int = 0,
    use_yes_price: bool = False,
) -> dict[str, object]:
    """Run the actual D2 read-only assembly; callers own auth/discovery preflight."""

    clock = now or (lambda: datetime.now(UTC))
    started_at = clock()
    session = RuntimeEvidenceSession(
        output_dir=output_dir,
        campaign_id=campaign_id,
        mode=mode,
        configured_duration_seconds=duration_seconds,
        selected_market_metadata=market_metadata,
        selected_market_selection=market_selection,
        lifecycle_mode_and_source="selected_market_rest_fallback",
        pricing_mode_and_source=(
            "explicit_subscription_use_yes_price_"
            f"{'true' if use_yes_price else 'false'}"
        ),
        provenance=provenance,
        started_at_utc=started_at,
        use_yes_price=use_yes_price,
    )
    provider = lifecycle_provider or _default_lifecycle_provider
    session.record_lifecycle(
        market_metadata,
        observed_at_utc=started_at,
        evaluated_at_utc=started_at,
    )
    last_lifecycle_poll = started_at
    lifecycle_blocker: str | None = None

    def poll_lifecycle(observed_at: datetime) -> None:
        nonlocal last_lifecycle_poll, lifecycle_blocker
        if (observed_at - last_lifecycle_poll).total_seconds() < 60:
            return
        last_lifecycle_poll = observed_at
        try:
            current = provider(session.selected_market_ticker)
        except Exception:
            lifecycle_blocker = "LIFECYCLE_OBSERVATION_FAILED"
            return
        session.record_lifecycle(
            current,
            observed_at_utc=observed_at,
            evaluated_at_utc=observed_at,
        )

    recorder = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id=campaign_id,
            market_tickers=(session.selected_market_ticker,),
            raw_events_path=session.current_data_path,
            duration_seconds=duration_seconds,
            max_events=max_events,
            max_reconnects=max_reconnects,
            persist_legacy_raw_events=False,
            use_yes_price=use_yes_price,
        ),
        auth,
        websocket_factory=websocket_factory,
        now=clock,
        event_callback=session.record_event,
        connection_callback=session.record_connection_event,
        request_callback=session.record_subscription_request,
        tick_callback=poll_lifecycle,
        monotonic=monotonic,
        monotonic_ns=monotonic_ns,
    )
    ended_at = clock()
    poll_lifecycle(ended_at)
    blocker_code = recorder.blocker_code or lifecycle_blocker
    elapsed = _decimal_seconds(ended_at - started_at)
    return session.close(
        ended_at_utc=ended_at,
        terminal_reason=(
            "bounded_duration_complete"
            if blocker_code is None and elapsed >= duration_seconds
            else "event_limit_reached"
            if blocker_code is None
            else f"runtime_blocked:{blocker_code}"
        ),
        stop_requested=False,
        connection_established=recorder.connection_established,
        subscription_acknowledged=recorder.subscription_acknowledged,
        blocker_code=blocker_code,
    )


def _default_lifecycle_provider(ticker: str) -> Mapping[str, object]:
    with KalshiDemoMarketDataClient() as client:
        return client.get_market(ticker)


def _preflight_dimensions() -> EvidenceDimensions:
    return EvidenceDimensions(
        artifact_integrity=EvidenceStatus.UNKNOWN,
        transport_connectivity=EvidenceStatus.FAIL,
        transport_keepalive=EvidenceStatus.UNKNOWN,
        subscription_status=EvidenceStatus.FAIL,
        sequence_integrity=EvidenceStatus.UNKNOWN,
        rebuild_integrity=EvidenceStatus.UNKNOWN,
        market_lifecycle_validity=EvidenceStatus.UNKNOWN,
        duration_evidence=EvidenceStatus.FAIL,
        process_liveness=EvidenceStatus.UNKNOWN,
        supervisor_liveness=EvidenceStatus.UNKNOWN,
        backup_integrity=EvidenceStatus.UNKNOWN,
        replay_qualification=EvidenceStatus.UNKNOWN,
    )


def write_d2_runtime_preflight_block(
    *,
    output_dir: Path,
    campaign_id: str,
    mode: str,
    configured_duration_seconds: int,
    provenance: RuntimeCodeProvenance,
    blocker_code: str,
    started_at_utc: datetime,
    selected_market_metadata: Mapping[str, object] | None = None,
    selected_market_selection: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Record a D2-versioned preflight block without opening a transport."""

    _require_aware(started_at_utc, "started_at_utc")
    root = Path(output_dir)
    _require_empty_runtime_root(root)
    metadata = dict(selected_market_metadata or {})
    selection = dict(selected_market_selection or {})
    for label, value in (("market metadata", metadata), ("market selection", selection)):
        validate_no_secret_payload(value, path=label)
        validate_no_private_account_payload(value, path=label)
    dimensions = _preflight_dimensions()

    summary = {
        "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "raw_event_schema_version": KALSHI_WS_RAW_SCHEMA_VERSION,
        "subscription_identity_model": CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION,
        "evidence_schema_version": EVIDENCE_CHAIN_SCHEMA_VERSION,
        "threshold_policy_version": V2_THRESHOLD_POLICY.version,
        "threshold_source_commit": provenance.public_code_commit,
        "threshold_policy": V2_THRESHOLD_POLICY.to_record(),
        **provenance.to_record(),
        "campaign_id": campaign_id,
        "mode": mode,
        "venue": "kalshi_demo",
        "configured_duration_seconds": configured_duration_seconds,
        "duration_seconds": configured_duration_seconds,
        "actual_elapsed_seconds": "0",
        "connected_elapsed_seconds": "0",
        "started_at": started_at_utc.isoformat(),
        "started_at_utc": started_at_utc.isoformat(),
        "ended_at": started_at_utc.isoformat(),
        "ended_at_utc": started_at_utc.isoformat(),
        "terminal_reason": f"preflight_blocked:{blocker_code}",
        "stop_requested": False,
        "selected_market_metadata": metadata,
        "selected_market_selection": selection,
        "market": metadata.get("ticker", "UNSELECTED"),
        "market_tickers": [],
        "lifecycle_mode_and_source": "selected_market_rest_fallback",
        "pricing_mode_and_source": "not_observed",
        "connection_windows": [],
        "disconnect_durations": [],
        "segment_summaries": [],
        "sequence_summaries": [],
        "rebuild_summaries": [],
        "freshness_dimensions": {
            "transport_keepalive_status": KeepaliveStatus.UNKNOWN_NOT_OBSERVED,
            "transport_keepalive_age_seconds": None,
            "lifecycle_observation_age_seconds": None,
            "orderbook_event_quiet_interval_seconds": None,
        },
        "artifact_integrity_summary": {
            "required_artifacts_present": False,
            "status": "NOT_APPLICABLE_PREFLIGHT_BLOCK",
        },
        "independent_evidence_classifications": dimensions.to_record(),
        "overall_evidence_classification": "FAIL",
        "source_type": "WEBSOCKET_NO_ORDERBOOK",
        "event_count": 0,
        "snapshot_count": 0,
        "delta_count": 0,
        "trade_count": 0,
        "rebuild_frame_count": 0,
        "connection_established": False,
        "subscription_acknowledged": False,
        "blocker_code": blocker_code,
        "status": "d2_runtime_preflight_blocked",
        "validation_status": "blocked",
        "evidence_classification": blocker_code,
        "live_gate_status": "disabled",
        "production_trading_enabled": False,
        "executable_order_intent": False,
        "production_endpoint_used": False,
        "submit_attempts": 0,
        "submit_attempt_count": 0,
        "real_money_trading": False,
        "replay_qualified": False,
        "raw_data_path_redacted": f"[LOCAL_PRIVATE_DATA_ROOT]/{root.name}",
    }
    validation = {
        "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "status": "blocked",
        "campaign_id": campaign_id,
        "blocker_code": blocker_code,
        "artifact_integrity": "NOT_APPLICABLE_PREFLIGHT_BLOCK",
        **dimensions.to_record(),
        "overall_evidence_classification": "FAIL",
        "source_type": "WEBSOCKET_NO_ORDERBOOK",
        "event_count": 0,
        "snapshot_count": 0,
        "delta_count": 0,
        "trade_count": 0,
        "live_gate_status": "disabled",
        "submit_attempts": 0,
        "strict_verdict": "STRICT NO-GO",
    }
    validate_no_secret_payload(summary)
    _atomic_write_json(_runtime_metadata_path(root, "campaign_summary.json"), summary)
    _atomic_write_json(_runtime_metadata_path(root, "campaign_manifest.json"), summary)
    _atomic_write_json(_runtime_metadata_path(root, "run_metadata.json"), summary)
    _atomic_write_json(_runtime_metadata_path(root, "campaign_validation.json"), validation)
    return {
        "campaign_id": campaign_id,
        "artifact_root": str(root),
        "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "validation_status": "blocked",
        "evidence_classification": blocker_code,
        "blocker_code": blocker_code,
        "live_gate_status": "disabled",
        "submit_attempt_count": 0,
    }


class RuntimeEvidenceSession:
    """Persist and summarize one D2 read-only runtime without collapsing evidence."""

    def __init__(
        self,
        *,
        output_dir: Path,
        campaign_id: str,
        mode: str,
        configured_duration_seconds: int,
        selected_market_metadata: Mapping[str, object],
        selected_market_selection: Mapping[str, object],
        lifecycle_mode_and_source: str,
        pricing_mode_and_source: str,
        provenance: RuntimeCodeProvenance,
        started_at_utc: datetime,
        threshold_policy: EvidenceThresholdPolicy = V2_THRESHOLD_POLICY,
        use_yes_price: bool = False,
        checkpoint_every_records: int = 1_000,
        max_segment_bytes: int = 64 * 1024 * 1024,
        max_segment_age_seconds: int = 3_600,
    ) -> None:
        if not campaign_id or not mode or configured_duration_seconds < 1:
            raise ValueError("runtime identity, mode, and duration are required")
        _require_aware(started_at_utc, "started_at_utc")
        validate_no_secret_payload(selected_market_metadata)
        validate_no_secret_payload(selected_market_selection)
        validate_no_private_account_payload(selected_market_metadata)
        validate_no_private_account_payload(selected_market_selection)
        ticker = selected_market_metadata.get("ticker") or selected_market_metadata.get(
            "market_ticker"
        )
        if not isinstance(ticker, str) or not ticker:
            raise ValueError("selected market ticker is required")
        if threshold_policy.effective_at_utc > started_at_utc:
            raise ValueError("threshold policy must be effective before runtime start")
        if not isinstance(use_yes_price, bool):
            raise ValueError("use_yes_price must be Boolean")
        self.output_dir = Path(output_dir)
        _require_empty_runtime_root(self.output_dir)
        self.campaign_id = campaign_id
        self.mode = mode
        self.configured_duration_seconds = configured_duration_seconds
        self.selected_market_metadata = dict(selected_market_metadata)
        self.selected_market_selection = dict(selected_market_selection)
        self.selected_market_ticker = ticker
        self.lifecycle_mode_and_source = lifecycle_mode_and_source
        self.pricing_mode_and_source = pricing_mode_and_source
        self.provenance = provenance
        self.started_at_utc = started_at_utc.astimezone(UTC)
        self.threshold_policy = threshold_policy
        self.use_yes_price = use_yes_price
        self.checkpoint_every_records = checkpoint_every_records
        self.max_segment_bytes = max_segment_bytes
        self.max_segment_age_seconds = max_segment_age_seconds
        self._artifact_clock = self.started_at_utc
        self._evidence_segment_number = 0
        self._evidence_local_row_index = 0
        self._closed_segment_summaries: list[dict[str, object]] = []
        self._writer = self._new_writer()
        self._rebuilder = KalshiWsBookRebuilder(
            explicit_pricing_mode=(
                PricingMode.UNIFIED_YES_PRICE
                if self.use_yes_price
                else PricingMode.LEGACY_SIDE_PRICE
            )
        )
        self._sequence: dict[tuple[str, str], dict[str, object]] = {}
        self._rebuild: dict[tuple[str, str, str], dict[str, object]] = {}
        self._connection_events: list[dict[str, object]] = []
        self._connection_windows: dict[str, dict[str, object]] = {}
        self._lifecycle_observation_count = 0
        self._latest_lifecycle_record: dict[str, object] | None = None
        self._lifecycle_invalid_observed = False
        self._raw_counts: Counter[str] = Counter()
        self._durable_ack_channels: dict[str, set[str]] = {}
        self._durable_ack_completed_at: dict[str, datetime] = {}
        self._grounded_acknowledged_ids: set[str] = set()
        self._admitted_selected_orderbook_counts: Counter[str] = Counter()
        self._raw_event_count = 0
        self._public_trade_count = 0
        self._binding_failure_observed = False
        self._binding_failure_count = 0
        self._subscription_request_count = 0
        self._rebuild_frame_count = 0
        self._rebuild_excluded_count = 0
        self._first_snapshot_at: datetime | None = None
        self._last_event_at: datetime | None = None
        self._last_orderbook_event_at: datetime | None = None
        self._last_keepalive_at: datetime | None = None
        self._last_lifecycle_at: datetime | None = None
        self._max_keepalive_age: int | None = None
        self._max_lifecycle_age: int | None = None
        self._max_orderbook_quiet: int | None = None
        self._last_open_status_at: datetime | None = None
        self._last_open_status_segment_id: str | None = None
        self._last_open_status_checkpoint_index = -1
        self._evidence_local_row_index = 1
        self._writer.append(
            {
                "schema_version": D2_RUNTIME_RECORD_SCHEMA_VERSION,
                "record_type": "runtime_launch",
                "campaign_id": self.campaign_id,
                "local_row_index": self._evidence_local_row_index,
                "observed_at_utc": self.started_at_utc.isoformat(),
                "runtime_launch": self._runtime_launch_record(),
            }
        )
        self._writer.checkpoint()
        self._write_open_status(self.started_at_utc)

    @property
    def current_data_path(self) -> Path:
        return self._writer.data_path

    def record_connection_event(self, event: ConnectionEvidenceEvent) -> None:
        record = event.to_record()
        if event.event_type is ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED:
            raw_ack_at = self._durable_ack_completed_at.get(event.connection_id)
            if raw_ack_at is not None and raw_ack_at <= event.observed_at_utc:
                self._grounded_acknowledged_ids.add(event.connection_id)
        self._connection_events.append(record)
        window = self._connection_windows.setdefault(
            event.connection_id,
            {
                "connection_id": event.connection_id,
                "segment_ids": [],
                "opened_at_utc": None,
                "closed_at_utc": None,
                "error_count": 0,
                "reasons": [],
            },
        )
        segment_ids = window["segment_ids"]
        if isinstance(segment_ids, list) and event.segment_id not in segment_ids:
            segment_ids.append(event.segment_id)
        reasons = window["reasons"]
        if isinstance(reasons, list):
            reasons.append(event.reason)
        if event.event_type in {
            ConnectionEvidenceType.CONNECTION_OPEN,
            ConnectionEvidenceType.RECONNECT,
        } and window["opened_at_utc"] is None:
            window["opened_at_utc"] = event.observed_at_utc.isoformat()
        if event.event_type is ConnectionEvidenceType.CONNECTION_CLOSE:
            window["closed_at_utc"] = event.observed_at_utc.isoformat()
        if event.event_type is ConnectionEvidenceType.CONNECTION_ERROR:
            window["error_count"] = int(window["error_count"]) + 1
        self._append(
            "connection_evidence",
            {"connection_event": record},
            observed_at_utc=event.observed_at_utc,
        )

    def record_subscription_request(self, request: SubscriptionRequestEvidence) -> None:
        if request.connection_id not in self._connection_windows:
            raise ValueError("subscription request has no active connection evidence")
        self._subscription_request_count += int(request.send_outcome == "PENDING_SEND")
        self._append(
            "subscription_request_evidence",
            {"subscription_request": request.to_record()},
            observed_at_utc=request.created_at_utc,
        )

    def _runtime_launch_record(self) -> dict[str, object]:
        return {
            "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "raw_event_schema_version": KALSHI_WS_RAW_SCHEMA_VERSION,
            "subscription_identity_model": (
                CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION
            ),
            "evidence_schema_version": EVIDENCE_CHAIN_SCHEMA_VERSION,
            "threshold_policy_version": self.threshold_policy.version,
            "threshold_source_commit": self.provenance.public_code_commit,
            "threshold_policy": self.threshold_policy.to_record(),
            **self.provenance.to_record(),
            "campaign_id": self.campaign_id,
            "mode": self.mode,
            "configured_duration_seconds": self.configured_duration_seconds,
            "started_at_utc": self.started_at_utc.isoformat(),
            "selected_market_metadata": self.selected_market_metadata,
            "selected_market_selection": self.selected_market_selection,
            "lifecycle_mode_and_source": self.lifecycle_mode_and_source,
            "pricing_mode_and_source": self.pricing_mode_and_source,
            "use_yes_price": self.use_yes_price,
            "subscription_request_policy": "one_channel_per_command_run_unique_positive_id",
            "subscription_channels": sorted(REQUIRED_PUBLIC_CHANNELS),
        }

    def record_lifecycle(
        self,
        market_metadata: Mapping[str, object],
        *,
        observed_at_utc: datetime,
        evaluated_at_utc: datetime,
    ) -> None:
        self._max_lifecycle_age = _max_age(
            self._max_lifecycle_age,
            _age_seconds(
                evaluated_at_utc,
                self._last_lifecycle_at or self.started_at_utc,
            ),
        )
        evidence = record_rest_lifecycle(
            market_metadata,
            selected_market_ticker=self.selected_market_ticker,
            observed_at_utc=observed_at_utc,
            evaluated_at_utc=evaluated_at_utc,
            max_age_seconds=self.threshold_policy.maximum_lifecycle_age_seconds,
        )
        record = evidence.to_record()
        self._lifecycle_observation_count += 1
        self._latest_lifecycle_record = record
        self._lifecycle_invalid_observed |= (
            record.get("lifecycle_status") != LifecycleStatus.OPEN
            or record.get("validity") != LifecycleValidity.VALID
        )
        self._last_lifecycle_at = observed_at_utc
        self._sample_freshness(evaluated_at_utc)
        self._append(
            "lifecycle_evidence",
            {"lifecycle_event": record},
            observed_at_utc=evaluated_at_utc,
        )

    def record_event(self, event: KalshiWsRawEvent) -> None:
        if event.campaign_id != self.campaign_id:
            raise ValueError("D2A event campaign does not match runtime campaign")
        validate_no_private_account_payload(
            event.original_payload,
            path="d2a_event.original_payload",
        )
        binding_failure = event.exclusion_reason in {
            ExclusionReason.NATIVE_ENVELOPE_REJECTED,
            ExclusionReason.PRE_ACKNOWLEDGMENT_DATA,
            ExclusionReason.SUBSCRIPTION_BINDING_CONFLICTED,
            ExclusionReason.SUBSCRIPTION_IDENTITY_MISMATCH,
            ExclusionReason.CHANNEL_TYPE_MISMATCH,
        } or event.subscription_binding_observation is (
            SubscriptionBindingObservation.CONFLICTING_ACK
        ) or event.subscription_binding_observation is (
            SubscriptionBindingObservation.CONFLICTING_REJECTION
        ) or (
            event.native_type in {"error", "rejected"}
            and event.subscription_binding_state
            in {SubscriptionBindingState.UNKNOWN, SubscriptionBindingState.REQUEST_MISMATCH}
        )
        self._binding_failure_observed |= binding_failure
        self._binding_failure_count += int(binding_failure)
        self._sample_freshness(event.received_at_utc)
        rebuild = self._rebuilder.apply(event)
        trade_stream = build_public_trade_stream(
            (event,),
            selected_market_tickers=(self.selected_market_ticker,),
        )
        trade_records = trade_stream.to_records()
        self._raw_event_count += 1
        self._raw_counts[event.native_type or "unknown"] += 1
        if event.native_type in {"subscribed", "ack", "ok", "error", "rejected"}:
            channels = self._durable_ack_channels.setdefault(event.connection_id, set())
            if (
                event.subscription_binding_state
                is SubscriptionBindingState.ACKNOWLEDGED
                and event.subscription_binding_observation
                in {
                    SubscriptionBindingObservation.ACKNOWLEDGED,
                    SubscriptionBindingObservation.DUPLICATE_ACK,
                }
            ):
                channels.update(
                    subscription_ack_channels(
                        event.original_payload,
                        event.native_type or "unknown",
                    )
                )
            if (
                REQUIRED_PUBLIC_CHANNELS <= channels
                and event.connection_id not in self._durable_ack_completed_at
            ):
                self._durable_ack_completed_at[event.connection_id] = event.received_at_utc
        self._public_trade_count += len(trade_records)
        self._last_event_at = event.received_at_utc
        selected_orderbook_event = (
            event.admission_status is AdmissionStatus.ADMITTED
            and event.native_market_ticker == self.selected_market_ticker
            and event.native_type in {"orderbook_snapshot", "orderbook_delta"}
        )
        if event.native_type in {"heartbeat", "pong"} and self._last_keepalive_at is None:
            self._max_keepalive_age = _max_age(
                self._max_keepalive_age,
                _age_seconds(event.received_at_utc, self.started_at_utc),
            )
        if selected_orderbook_event and self._last_orderbook_event_at is None:
            self._max_orderbook_quiet = _max_age(
                self._max_orderbook_quiet,
                _age_seconds(event.received_at_utc, self.started_at_utc),
            )
        if selected_orderbook_event:
            self._admitted_selected_orderbook_counts[event.native_type or "unknown"] += 1
            self._last_orderbook_event_at = event.received_at_utc
        if event.native_type in {"heartbeat", "pong"}:
            self._last_keepalive_at = event.received_at_utc
        if (
            selected_orderbook_event
            and event.native_type == "orderbook_snapshot"
            and self._first_snapshot_at is None
        ):
            self._first_snapshot_at = event.received_at_utc
        self._update_sequence_summary(event)
        rebuild_record = self._update_rebuild_summary(event, rebuild)
        self._append(
            "raw_transport_event",
            {
                "d2a_event": event.to_record(),
                "d2b_rebuild": rebuild_record,
                "d2c_public_trades": trade_records,
            },
            observed_at_utc=event.received_at_utc,
        )
        if binding_failure:
            self._write_open_status(event.received_at_utc)

    def close(
        self,
        *,
        ended_at_utc: datetime,
        terminal_reason: str,
        stop_requested: bool,
        connection_established: bool,
        subscription_acknowledged: bool,
        blocker_code: str | None,
    ) -> dict[str, object]:
        _require_aware(ended_at_utc, "ended_at_utc")
        ended_at_utc = ended_at_utc.astimezone(UTC)
        for window in self._connection_windows.values():
            if window["opened_at_utc"] and window["closed_at_utc"] is None:
                window["closed_at_utc"] = ended_at_utc.isoformat()
        self._sample_freshness(ended_at_utc)
        self._artifact_clock = max(self._artifact_clock, ended_at_utc)
        actual = _decimal_seconds(ended_at_utc - self.started_at_utc)
        connected = self._connected_seconds(ended_at_utc, connection_established)
        total_disconnect = max(Decimal("0"), actual - connected)
        freshness = evaluate_evidence_freshness(
            evaluated_at_utc=ended_at_utc,
            transport_keepalive_observed_at_utc=self._last_keepalive_at,
            transport_keepalive_source=(
                "RECORDED_WS_HEARTBEAT_OR_PONG" if self._last_keepalive_at else None
            ),
            lifecycle_observed_at_utc=self._last_lifecycle_at,
            orderbook_event_at_utc=self._last_orderbook_event_at,
        )
        timing = build_evidence_timing(
            configured_duration_seconds=self.configured_duration_seconds,
            started_at_utc=self.started_at_utc,
            checkpoint_at_utc=None,
            ended_at_utc=ended_at_utc,
            first_snapshot_at=self._first_snapshot_at,
            last_event_at=self._last_event_at,
            terminal_reason=terminal_reason,
            stop_requested=stop_requested,
            total_disconnect_seconds=total_disconnect,
            threshold_policy_version=self.threshold_policy.version,
            threshold_source_commit=self.provenance.public_code_commit,
            threshold_effective_utc=self.threshold_policy.effective_at_utc,
            transport_keepalive_age_seconds=freshness.transport_keepalive_age_seconds,
            lifecycle_observation_age_seconds=freshness.lifecycle_observation_age_seconds,
            orderbook_event_quiet_interval_seconds=(
                freshness.orderbook_event_quiet_interval_seconds
            ),
            max_transport_keepalive_age_seconds=self._max_keepalive_age,
            max_lifecycle_observation_age_seconds=self._max_lifecycle_age,
            max_orderbook_event_quiet_interval_seconds=self._max_orderbook_quiet,
        )
        self._append(
            "runtime_terminal",
            {
                "runtime_terminal": _runtime_terminal_payload(
                    timing=timing,
                    mode=self.mode,
                    blocker_code=blocker_code,
                    connection_established=connection_established,
                    subscription_acknowledged=subscription_acknowledged,
                )
            },
            observed_at_utc=ended_at_utc,
        )
        self._closed_segment_summaries.append(
            self._closed_segment_record(
                self._writer,
                self._writer.close(terminal_reason=terminal_reason),
            )
        )
        artifact_integrity = self._verify_closed_segments()
        dimensions = self._dimensions(
            timing=timing,
            artifact_integrity=artifact_integrity,
            connection_established=connection_established,
            subscription_acknowledged=subscription_acknowledged,
            blocker_code=blocker_code,
        )
        classification = classify_evidence(dimensions)
        connection_windows = self._connection_window_records()
        disconnect_durations = self._disconnect_durations(
            connection_windows,
            started_at_utc=self.started_at_utc,
            ended_at_utc=ended_at_utc,
        )
        summary: dict[str, object] = {
            "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "raw_event_schema_version": KALSHI_WS_RAW_SCHEMA_VERSION,
            "subscription_identity_model": (
                CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION
            ),
            "evidence_schema_version": EVIDENCE_CHAIN_SCHEMA_VERSION,
            "threshold_policy_version": self.threshold_policy.version,
            "threshold_source_commit": self.provenance.public_code_commit,
            "threshold_policy": self.threshold_policy.to_record(),
            **self.provenance.to_record(),
            "campaign_id": self.campaign_id,
            "mode": self.mode,
            "venue": "kalshi_demo",
            "configured_duration_seconds": self.configured_duration_seconds,
            "duration_seconds": self.configured_duration_seconds,
            **timing.to_record(),
            "started_at": self.started_at_utc.isoformat(),
            "ended_at_utc": ended_at_utc.isoformat(),
            "selected_market_metadata": self.selected_market_metadata,
            "selected_market_selection": self.selected_market_selection,
            "market": self.selected_market_ticker,
            "market_ticker": self.selected_market_ticker,
            "market_tickers": [self.selected_market_ticker],
            "market_count": 1,
            "market_status": _selected_status(self.selected_market_metadata),
            "status_at_launch": _selected_status(self.selected_market_metadata),
            "close_time": self.selected_market_metadata.get("close_time"),
            "lifecycle_mode_and_source": self.lifecycle_mode_and_source,
            "pricing_mode_and_source": self.pricing_mode_and_source,
            "use_yes_price": self.use_yes_price,
            "connection_windows": connection_windows,
            "disconnect_durations": disconnect_durations,
            "disconnect_count": len(disconnect_durations),
            "reconnect_count": sum(
                event.get("event_type") == ConnectionEvidenceType.RECONNECT
                for event in self._connection_events
            ),
            "maximum_disconnect_seconds": _decimal_text(
                max(
                    (Decimal(value) for value in disconnect_durations),
                    default=Decimal("0"),
                )
            ),
            "connection_coverage": _decimal_text(
                connected / actual if actual else Decimal("0")
            ),
            "segment_summaries": self._closed_segment_summaries,
            "sequence_summaries": self._sequence_summary_records(),
            "rebuild_summaries": self._rebuild_summary_records(),
            "freshness_dimensions": freshness.to_record(),
            "artifact_integrity_summary": artifact_integrity,
            "independent_evidence_classifications": dimensions.to_record(),
            "overall_evidence_classification": classification.overall_classification,
            "raw_event_count": self._raw_event_count,
            "event_count": self._raw_event_count,
            "snapshot_count": self._raw_counts["orderbook_snapshot"],
            "delta_count": self._raw_counts["orderbook_delta"],
            "admitted_selected_snapshot_count": self._admitted_selected_orderbook_counts[
                "orderbook_snapshot"
            ],
            "admitted_selected_delta_count": self._admitted_selected_orderbook_counts[
                "orderbook_delta"
            ],
            "public_trade_count": self._public_trade_count,
            "trade_count": self._public_trade_count,
            "lifecycle_observation_count": self._lifecycle_observation_count,
            "connection_event_count": len(self._connection_events),
            "rebuild_frame_count": self._rebuild_frame_count,
            "rebuild_excluded_count": self._rebuild_excluded_count,
            "gap_count": sum(
                summary["sequence_states"].get(SequenceState.SEQUENCE_GAP_DETECTED, 0)
                for summary in self._sequence.values()
            ),
            "heartbeat_count": self._raw_counts["heartbeat"],
            "status_update_count": self._raw_counts["market_status"],
            "first_snapshot_at": (
                self._first_snapshot_at.isoformat() if self._first_snapshot_at else None
            ),
            "last_event_time": self._last_event_at.isoformat() if self._last_event_at else None,
            "market_lifecycle_status": (
                self._latest_lifecycle_record["lifecycle_status"]
                if self._latest_lifecycle_record
                else "UNKNOWN"
            ),
            "websocket_message_freshness_status": _orderbook_freshness_status(
                freshness.orderbook_event_quiet_interval_seconds
            ),
            "exchange_heartbeat_status": freshness.transport_keepalive_status,
            "supervisor_liveness_status": "UNKNOWN",
            "campaign_process_liveness_status": "EXITED",
            "connection_established": connection_established,
            "subscription_acknowledged": subscription_acknowledged,
            "binding_failure_observed": self._binding_failure_observed,
            "binding_failure_count": self._binding_failure_count,
            "subscription_request_count": self._subscription_request_count,
            "blocker_code": blocker_code,
            "status": "d2_runtime_complete" if blocker_code is None else "d2_runtime_blocked",
            "source_type": _source_type(self._raw_counts),
            "live_gate_status": "disabled",
            "production_trading_enabled": False,
            "executable_order_intent": False,
            "production_endpoint_used": False,
            "submit_attempts": 0,
            "real_money_trading": False,
            "replay_qualified": False,
            "raw_data_path_redacted": f"[LOCAL_PRIVATE_DATA_ROOT]/{self.output_dir.name}",
            "raw_event_path": f"[LOCAL_PRIVATE_DATA_ROOT]/{self.output_dir.name}/evidence_segments",
            "manifest_path": "campaign_manifest.json",
            "validation_report_path": "campaign_validation.json",
        }
        validate_no_secret_payload(summary)
        _sync_runtime_summary(self.output_dir, summary)
        validation = validate_d2_runtime_artifacts(self.output_dir)
        summary["validation_status"] = validation["status"]
        summary["evidence_classification"] = validation["overall_evidence_classification"]
        _sync_runtime_summary(self.output_dir, summary)
        return summary

    def _new_writer(self) -> EvidenceSegmentWriter:
        self._evidence_segment_number += 1
        self._evidence_local_row_index = 0
        return EvidenceSegmentWriter(
            self.output_dir / "evidence_segments",
            segment_id=f"{self.campaign_id}.evidence.{self._evidence_segment_number:04d}",
            checkpoint_every_records=self.checkpoint_every_records,
            max_segment_bytes=self.max_segment_bytes,
            max_segment_age_seconds=self.max_segment_age_seconds,
            now_utc=lambda: self._artifact_clock,
        )

    def _append(
        self,
        record_type: str,
        payload: Mapping[str, object],
        *,
        observed_at_utc: datetime,
    ) -> None:
        self._artifact_clock = max(self._artifact_clock, observed_at_utc.astimezone(UTC))
        next_id = f"{self.campaign_id}.evidence.{self._evidence_segment_number + 1:04d}"
        rotation = self._writer.rotate_if_needed(next_segment_id=next_id)
        if rotation is not None:
            self._closed_segment_summaries.append(
                self._closed_segment_record(self._writer, rotation.closed_summary)
            )
            self._writer = rotation.next_writer
            self._evidence_segment_number += 1
            self._evidence_local_row_index = 0
        self._evidence_local_row_index += 1
        self._writer.append(
            {
                "schema_version": D2_RUNTIME_RECORD_SCHEMA_VERSION,
                "record_type": record_type,
                "campaign_id": self.campaign_id,
                "local_row_index": self._evidence_local_row_index,
                "observed_at_utc": observed_at_utc.isoformat(),
                **payload,
            }
        )
        self._maybe_write_open_status(observed_at_utc)

    def _maybe_write_open_status(self, observed_at_utc: datetime) -> None:
        status = self._writer.status_record()
        checkpoint_index = int(status["last_committed_local_row_index"])
        interval_due = (
            self._last_open_status_at is None
            or (observed_at_utc - self._last_open_status_at).total_seconds()
            >= OPEN_STATUS_INTERVAL_SECONDS
        )
        if (
            interval_due
            or self._writer.segment_id != self._last_open_status_segment_id
            or checkpoint_index != self._last_open_status_checkpoint_index
        ):
            self._write_open_status(observed_at_utc)

    def _write_open_status(self, observed_at_utc: datetime) -> None:
        actual = _decimal_seconds(observed_at_utc - self.started_at_utc)
        connection_windows = self._connection_window_records(observed_at_utc)
        opened_ids = {
            str(event["connection_id"])
            for event in self._connection_events
            if event.get("event_type")
            in {ConnectionEvidenceType.CONNECTION_OPEN, ConnectionEvidenceType.RECONNECT}
        }
        acknowledged_ids = {
            str(event["connection_id"])
            for event in self._connection_events
            if event.get("event_type") == ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED
        }
        ungrounded_acknowledgments = acknowledged_ids - self._grounded_acknowledged_ids
        connection_established = bool(opened_ids)
        subscription_rejected = any(
            event.get("event_type") == ConnectionEvidenceType.SUBSCRIPTION_REJECTED
            for event in self._connection_events
        )
        subscription_acknowledged = bool(
            opened_ids
            and opened_ids <= self._grounded_acknowledged_ids
            and not subscription_rejected
        )
        connected = self._connected_seconds(observed_at_utc, connection_established)
        disconnect_durations = self._disconnect_durations(
            connection_windows,
            started_at_utc=self.started_at_utc,
            ended_at_utc=observed_at_utc,
        )
        maximum_disconnect = max(
            (Decimal(value) for value in disconnect_durations),
            default=Decimal("0"),
        )
        coverage = connected / actual if actual else Decimal("0")
        freshness = evaluate_evidence_freshness(
            evaluated_at_utc=observed_at_utc,
            transport_keepalive_observed_at_utc=self._last_keepalive_at,
            transport_keepalive_source=(
                "RECORDED_WS_HEARTBEAT_OR_PONG" if self._last_keepalive_at else None
            ),
            lifecycle_observed_at_utc=self._last_lifecycle_at,
            orderbook_event_at_utc=self._last_orderbook_event_at,
        )
        dimensions = {
            field: EvidenceStatus.UNKNOWN for field in EvidenceDimensions.__dataclass_fields__
        }
        if connection_established and actual:
            dimensions["transport_connectivity"] = (
                EvidenceStatus.PASS
                if coverage >= self.threshold_policy.minimum_connection_coverage
                and maximum_disconnect
                <= self.threshold_policy.maximum_disconnect_seconds
                else EvidenceStatus.FAIL
            )
        if opened_ids:
            dimensions["subscription_status"] = (
                EvidenceStatus.FAIL
                if (
                    subscription_rejected
                    or ungrounded_acknowledgments
                    or self._binding_failure_observed
                )
                else EvidenceStatus.PASS
                if subscription_acknowledged
                else EvidenceStatus.UNKNOWN
            )
        dimensions["sequence_integrity"] = _sequence_evidence_status(self._sequence)
        dimensions["rebuild_integrity"] = _rebuild_evidence_status(self._rebuild)
        dimensions["market_lifecycle_validity"] = _lifecycle_evidence_status(
            self._lifecycle_observation_count,
            self._lifecycle_invalid_observed,
            self._max_lifecycle_age,
            self.threshold_policy.maximum_lifecycle_age_seconds,
        )
        if self._last_keepalive_at is not None:
            dimensions["transport_keepalive"] = (
                EvidenceStatus.PASS
                if (self._max_keepalive_age or 0)
                <= self.threshold_policy.maximum_transport_keepalive_age_seconds
                else EvidenceStatus.FAIL
            )
        summary = {
            "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "raw_event_schema_version": KALSHI_WS_RAW_SCHEMA_VERSION,
            "subscription_identity_model": (
                CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION
            ),
            "evidence_schema_version": EVIDENCE_CHAIN_SCHEMA_VERSION,
            "threshold_policy_version": self.threshold_policy.version,
            "threshold_source_commit": self.provenance.public_code_commit,
            **self.provenance.to_record(),
            "campaign_id": self.campaign_id,
            "mode": self.mode,
            "venue": "kalshi_demo",
            "configured_duration_seconds": self.configured_duration_seconds,
            "duration_seconds": self.configured_duration_seconds,
            "actual_elapsed_seconds": _decimal_text(actual),
            "connected_elapsed_seconds": _decimal_text(connected),
            "started_at_utc": self.started_at_utc.isoformat(),
            "started_at": self.started_at_utc.isoformat(),
            "ended_at": None,
            "ended_at_utc": None,
            "terminal_reason": None,
            "stop_requested": False,
            "selected_market_metadata": self.selected_market_metadata,
            "selected_market_selection": self.selected_market_selection,
            "market": self.selected_market_ticker,
            "market_ticker": self.selected_market_ticker,
            "market_tickers": [self.selected_market_ticker],
            "market_count": 1,
            "market_status": _selected_status(self.selected_market_metadata),
            "status_at_launch": _selected_status(self.selected_market_metadata),
            "close_time": self.selected_market_metadata.get("close_time"),
            "lifecycle_mode_and_source": self.lifecycle_mode_and_source,
            "pricing_mode_and_source": self.pricing_mode_and_source,
            "use_yes_price": self.use_yes_price,
            "connection_windows": connection_windows,
            "disconnect_durations": disconnect_durations,
            "connection_coverage": _decimal_text(coverage),
            "segment_summaries": [
                *self._closed_segment_summaries,
                {
                    **self._writer.status_record(),
                    "data_path": str(self._writer.data_path.relative_to(self.output_dir)),
                    "checkpoint_path": str(
                        self._writer.checkpoint_path.relative_to(self.output_dir)
                    ),
                },
            ],
            "sequence_summaries": self._sequence_summary_records(),
            "rebuild_summaries": self._rebuild_summary_records(),
            "freshness_dimensions": freshness.to_record(),
            "artifact_integrity_summary": {
                "integrity_scope": "CHECKPOINT_BOUNDED",
                "closed_file_hash_verified": None,
            },
            "independent_evidence_classifications": dimensions,
            "overall_evidence_classification": "INCOMPLETE",
            "event_count": self._raw_event_count,
            "snapshot_count": self._raw_counts["orderbook_snapshot"],
            "delta_count": self._raw_counts["orderbook_delta"],
            "admitted_selected_snapshot_count": self._admitted_selected_orderbook_counts[
                "orderbook_snapshot"
            ],
            "admitted_selected_delta_count": self._admitted_selected_orderbook_counts[
                "orderbook_delta"
            ],
            "trade_count": self._public_trade_count,
            "rebuild_frame_count": self._rebuild_frame_count,
            "gap_count": sum(
                summary["sequence_states"].get(SequenceState.SEQUENCE_GAP_DETECTED, 0)
                for summary in self._sequence.values()
            ),
            "last_event_time": self._last_event_at.isoformat() if self._last_event_at else None,
            "market_lifecycle_status": (
                self._latest_lifecycle_record["lifecycle_status"]
                if self._latest_lifecycle_record
                else "UNKNOWN"
            ),
            "websocket_message_freshness_status": _orderbook_freshness_status(
                freshness.orderbook_event_quiet_interval_seconds
            ),
            "exchange_heartbeat_status": freshness.transport_keepalive_status,
            "connection_established": connection_established,
            "subscription_acknowledged": subscription_acknowledged,
            "binding_failure_observed": self._binding_failure_observed,
            "binding_failure_count": self._binding_failure_count,
            "subscription_request_count": self._subscription_request_count,
            "status": "d2_runtime_running",
            "source_type": _source_type(self._raw_counts),
            "live_gate_status": "disabled",
            "production_trading_enabled": False,
            "executable_order_intent": False,
            "production_endpoint_used": False,
            "submit_attempts": 0,
            "real_money_trading": False,
            "replay_qualified": False,
            "raw_data_path_redacted": f"[LOCAL_PRIVATE_DATA_ROOT]/{self.output_dir.name}",
            "raw_event_path": f"[LOCAL_PRIVATE_DATA_ROOT]/{self.output_dir.name}/evidence_segments",
            "manifest_path": "campaign_manifest.json",
            "validation_report_path": "campaign_validation.json",
        }
        for name in ("campaign_summary.json", "run_metadata.json"):
            _atomic_write_json(
                _runtime_metadata_path(self.output_dir, name),
                summary,
            )
        writer_status = self._writer.status_record()
        self._last_open_status_at = observed_at_utc
        self._last_open_status_segment_id = self._writer.segment_id
        self._last_open_status_checkpoint_index = int(
            writer_status["last_committed_local_row_index"]
        )

    def _closed_segment_record(
        self,
        writer: EvidenceSegmentWriter,
        summary: Mapping[str, object],
    ) -> dict[str, object]:
        root = self.output_dir
        return {
            **dict(summary),
            "data_path": str(writer.data_path.relative_to(root)),
            "checkpoint_path": str(writer.checkpoint_path.relative_to(root)),
            "summary_path": str(writer.summary_path.relative_to(root)),
            "append_chain_update_count": writer.append_chain_update_count,
            "full_file_hash_count": writer.full_file_hash_count,
            "recovery_status": "NOT_APPLICABLE_CLEAN_CLOSE",
            "partial_tail_bytes_removed": 0,
            "snapshot_required_after_recovery": None,
        }

    def _verify_closed_segments(self) -> dict[str, object]:
        chain_ok = checkpoint_ok = closed_hash_ok = True
        for segment in self._closed_segment_summaries:
            data_path = self.output_dir / str(segment["data_path"])
            checkpoint_path = self.output_dir / str(segment["checkpoint_path"])
            verified = verify_segment_chain(data_path, segment_id=str(segment["segment_id"]))
            chain_ok &= (
                verified.terminal_chain_hash == segment["terminal_chain_hash"]
                and verified.record_count == segment["last_committed_local_row_index"]
            )
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint_ok &= (
                checkpoint.get("schema_version") == EVIDENCE_CHECKPOINT_SCHEMA_VERSION
                and checkpoint.get("chain_hash") == segment["terminal_chain_hash"]
                and checkpoint.get("last_committed_local_row_index")
                == segment["last_committed_local_row_index"]
            )
            with data_path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            closed_hash_ok &= digest == segment["closed_file_sha256"]
        return {
            "schema_valid": True,
            "required_artifacts_present": bool(self._closed_segment_summaries),
            "append_chain_verified": chain_ok,
            "atomic_checkpoint_verified": checkpoint_ok,
            "closed_file_hash_verified": closed_hash_ok,
            "prohibited_content_scan": "PASS",
            "recovery_status": "NOT_APPLICABLE_CLEAN_CLOSE",
            "partial_tail_bytes_removed": 0,
            "segment_count": len(self._closed_segment_summaries),
        }

    def _update_sequence_summary(self, event: KalshiWsRawEvent) -> None:
        key = (event.connection_id, event.segment_id)
        summary = self._sequence.setdefault(
            key,
            {
                "connection_id": event.connection_id,
                "segment_id": event.segment_id,
                "segment_boundary_reasons": set(),
                "native_sid_values": set(),
                "native_seq_present_count": 0,
                "sequence_states": Counter(),
                "admitted_rows": 0,
                "excluded_rows": 0,
                "acknowledgement_count": 0,
                "rejection_count": 0,
                "channel_bindings": {},
            },
        )
        summary["segment_boundary_reasons"].add(event.segment_boundary_reason)
        if event.native_sid is not None:
            summary["native_sid_values"].add(str(event.native_sid))
        if event.native_seq is not None:
            summary["native_seq_present_count"] += 1
        summary["sequence_states"][event.sequence_state] += 1
        if event.admission_status is AdmissionStatus.ADMITTED:
            summary["admitted_rows"] += 1
        elif event.admission_status is AdmissionStatus.EXCLUDED:
            summary["excluded_rows"] += 1
        if event.native_type in {"subscribed", "ack", "ok"}:
            summary["acknowledgement_count"] += 1
        if event.native_type in {"error", "rejected"}:
            summary["rejection_count"] += 1
        _observe_channel_binding(summary, event)

    def _update_rebuild_summary(self, event: KalshiWsRawEvent, result: Any) -> dict[str, object]:
        key = (
            event.native_market_ticker or self.selected_market_ticker,
            event.connection_id,
            event.segment_id,
        )
        summary = self._rebuild.setdefault(
            key,
            {
                "market_ticker": key[0],
                "connection_id": key[1],
                "segment_id": key[2],
                "frame_count": 0,
                "orderbook_row_count": 0,
                "excluded_row_count": 0,
                "invalidation_reasons": Counter(),
                "pricing_modes": set(),
                "pricing_mode_sources": set(),
                "frame_hash_chain": None,
                "latest_frame_hash": None,
                "terminal_state_hash": None,
                "snapshot_first_admitted": False,
                "native_state_valid": None,
            },
        )
        record: dict[str, object] = {
            "disposition": result.disposition,
            "reason": result.reason,
            "frame": None,
        }
        if event.native_type in {"orderbook_snapshot", "orderbook_delta"}:
            summary["orderbook_row_count"] += 1
        if result.reason is not None:
            summary["invalidation_reasons"][result.reason] += 1
            summary["native_state_valid"] = False
        if result.frame is not None:
            frame = result.frame
            frame_record = frame.to_record()
            record["frame"] = frame_record
            summary["frame_count"] += 1
            summary["frame_hash_chain"] = _advance_frame_hash_chain(
                summary["frame_hash_chain"], frame.frame_hash
            )
            summary["latest_frame_hash"] = frame.frame_hash
            summary["terminal_state_hash"] = frame.terminal_state_hash
            summary["pricing_modes"].add(frame.pricing_mode)
            summary["pricing_mode_sources"].add(frame.pricing_mode_source)
            summary["native_state_valid"] = frame.segment_validity is SegmentValidity.VALID
            if event.native_type == "orderbook_snapshot":
                summary["snapshot_first_admitted"] = True
            self._rebuild_frame_count += 1
        elif event.native_type in {"orderbook_snapshot", "orderbook_delta"}:
            summary["excluded_row_count"] += 1
            self._rebuild_excluded_count += 1
        return record

    def _sequence_summary_records(self) -> list[dict[str, object]]:
        return _sequence_summary_records(self._sequence)

    def _rebuild_summary_records(self) -> list[dict[str, object]]:
        return _rebuild_summary_records(self._rebuild)

    def _sample_freshness(self, observed_at_utc: datetime) -> None:
        if self._last_keepalive_at is not None:
            self._max_keepalive_age = _max_age(
                self._max_keepalive_age,
                _age_seconds(observed_at_utc, self._last_keepalive_at),
            )
        if self._last_lifecycle_at is not None:
            self._max_lifecycle_age = _max_age(
                self._max_lifecycle_age,
                _age_seconds(observed_at_utc, self._last_lifecycle_at),
            )
        if self._last_orderbook_event_at is not None:
            self._max_orderbook_quiet = _max_age(
                self._max_orderbook_quiet,
                _age_seconds(observed_at_utc, self._last_orderbook_event_at),
            )

    def _connected_seconds(
        self,
        ended_at_utc: datetime,
        connection_established: bool,
    ) -> Decimal:
        windows = self._connection_window_records(ended_at_utc)
        if not windows:
            return (
                _decimal_seconds(ended_at_utc - self.started_at_utc)
                if connection_established
                else Decimal("0")
            )
        return sum(
            (Decimal(str(window["duration_seconds"])) for window in windows),
            Decimal("0"),
        )

    def _connection_window_records(
        self,
        open_through_utc: datetime | None = None,
    ) -> list[dict[str, object]]:
        records = []
        for window in self._connection_windows.values():
            opened = _parse_time(window["opened_at_utc"])
            closed = _parse_time(window["closed_at_utc"]) or open_through_utc
            duration = _decimal_seconds(closed - opened) if opened and closed else Decimal("0")
            records.append({**window, "duration_seconds": _decimal_text(duration)})
        return records

    @staticmethod
    def _disconnect_durations(
        windows: list[dict[str, object]],
        *,
        started_at_utc: datetime,
        ended_at_utc: datetime,
    ) -> list[str]:
        ordered = sorted(
            (window for window in windows if window["opened_at_utc"]),
            key=lambda window: str(window["opened_at_utc"]),
        )
        durations: list[str] = []
        if not ordered:
            return [_decimal_text(_decimal_seconds(ended_at_utc - started_at_utc))]
        first_opened = _parse_time(ordered[0]["opened_at_utc"])
        if first_opened and first_opened > started_at_utc:
            durations.append(
                _decimal_text(_decimal_seconds(first_opened - started_at_utc))
            )
        for previous, current in zip(ordered, ordered[1:], strict=False):
            closed = _parse_time(previous["closed_at_utc"])
            opened = _parse_time(current["opened_at_utc"])
            if closed and opened and opened >= closed:
                durations.append(_decimal_text(_decimal_seconds(opened - closed)))
        last_closed = _parse_time(ordered[-1]["closed_at_utc"])
        if last_closed and ended_at_utc > last_closed:
            durations.append(_decimal_text(_decimal_seconds(ended_at_utc - last_closed)))
        return durations

    def _dimensions(
        self,
        *,
        timing: Any,
        artifact_integrity: Mapping[str, object],
        connection_established: bool,
        subscription_acknowledged: bool,
        blocker_code: str | None,
    ) -> EvidenceDimensions:
        lifecycle = _lifecycle_evidence_status(
            self._lifecycle_observation_count,
            self._lifecycle_invalid_observed,
            self._max_lifecycle_age,
            self.threshold_policy.maximum_lifecycle_age_seconds,
        )
        keepalive = (
            EvidenceStatus.UNKNOWN
            if self._last_keepalive_at is None
            else EvidenceStatus.PASS
            if (self._max_keepalive_age or 0)
            <= self.threshold_policy.maximum_transport_keepalive_age_seconds
            else EvidenceStatus.FAIL
        )
        coverage = (
            timing.connected_elapsed_seconds / timing.actual_elapsed_seconds
            if timing.actual_elapsed_seconds
            else Decimal("0")
        )
        disconnects = self._disconnect_durations(
            self._connection_window_records(),
            started_at_utc=timing.started_at_utc,
            ended_at_utc=timing.ended_at or timing.checkpoint_at_utc,
        )
        maximum_disconnect = max(
            (Decimal(value) for value in disconnects),
            default=Decimal("0"),
        )
        return EvidenceDimensions(
            artifact_integrity=(
                EvidenceStatus.PASS
                if all(
                    artifact_integrity[field]
                    for field in (
                        "schema_valid",
                        "required_artifacts_present",
                        "append_chain_verified",
                        "atomic_checkpoint_verified",
                        "closed_file_hash_verified",
                    )
                )
                else EvidenceStatus.FAIL
            ),
            transport_connectivity=(
                EvidenceStatus.PASS
                if connection_established
                and coverage >= self.threshold_policy.minimum_connection_coverage
                and maximum_disconnect
                <= self.threshold_policy.maximum_disconnect_seconds
                else EvidenceStatus.FAIL
            ),
            transport_keepalive=keepalive,
            subscription_status=(
                EvidenceStatus.PASS
                if subscription_acknowledged and not self._binding_failure_observed
                else EvidenceStatus.FAIL
            ),
            sequence_integrity=_sequence_evidence_status(self._sequence),
            rebuild_integrity=_rebuild_evidence_status(self._rebuild),
            market_lifecycle_validity=lifecycle,
            duration_evidence=classify_duration_evidence(timing),
            process_liveness=(
                EvidenceStatus.PASS if blocker_code is None else EvidenceStatus.FAIL
            ),
            supervisor_liveness=EvidenceStatus.UNKNOWN,
            backup_integrity=EvidenceStatus.UNKNOWN,
            replay_qualification=EvidenceStatus.UNKNOWN,
        )


def validate_d2_runtime_artifacts(
    input_dir: Path,
    *,
    persist: bool = True,
) -> dict[str, object]:
    root = Path(input_dir).resolve()
    failures: list[str] = []
    try:
        validation_path: Path | None = _runtime_metadata_path(root, "campaign_validation.json")
    except (OSError, ValueError) as exc:
        validation_path = None
        failures.append(f"campaign_validation unavailable: {exc}")
    summary: Mapping[str, object]
    try:
        loaded_summary = json.loads(
            _runtime_metadata_path(root, "campaign_summary.json").read_text(
                encoding="utf-8"
            )
        )
        if not isinstance(loaded_summary, Mapping):
            raise ValueError("campaign_summary must be a JSON object")
        summary = loaded_summary
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        summary = {}
        failures.append(f"campaign_summary unavailable: {exc}")
    if summary.get("status") == "d2_runtime_preflight_blocked":
        return _validate_d2_preflight_block(root, summary, persist=persist)
    if summary.get("runtime_schema_version") != D2_RUNTIME_SCHEMA_VERSION:
        failures.append("runtime schema missing or unsupported")
    if summary.get("raw_event_schema_version") != KALSHI_WS_RAW_SCHEMA_VERSION:
        failures.append("raw event schema missing or unsupported")
    if summary.get("evidence_schema_version") != EVIDENCE_CHAIN_SCHEMA_VERSION:
        failures.append("evidence schema missing or unsupported")
    if summary.get("threshold_policy_version") != V2_THRESHOLD_POLICY.version:
        failures.append("threshold policy version contradicts the runtime contract")
    if summary.get("threshold_policy") != V2_THRESHOLD_POLICY.to_record():
        failures.append("threshold policy values contradict the runtime contract")
    if summary.get("threshold_source_commit") != summary.get("public_code_commit"):
        failures.append("threshold source commit contradicts runtime provenance")
    required = (
        "threshold_policy_version",
        "threshold_source_commit",
        "public_code_commit",
        "configured_duration_seconds",
        "actual_elapsed_seconds",
        "connected_elapsed_seconds",
        "segment_summaries",
        "sequence_summaries",
        "rebuild_summaries",
        "freshness_dimensions",
        "independent_evidence_classifications",
        "selected_market_selection",
        "use_yes_price",
    )
    failures.extend(f"missing required field: {name}" for name in required if name not in summary)
    try:
        validate_no_secret_payload(summary)
        _validate_runtime_metadata_safety(summary)
    except ValueError as exc:
        failures.append(str(exc))
    segments = summary.get("segment_summaries", [])
    if not isinstance(segments, list) or not segments:
        failures.append("at least one closed evidence segment is required")
        segments = []
    runtime_data_paths: list[Path] = []
    listed_segment_paths: set[Path] = set()
    for segment in segments:
        try:
            relative_paths = tuple(
                Path(str(segment[field]))
                for field in ("data_path", "checkpoint_path", "summary_path")
            )
            data_path = _contained_artifact_path(root, segment["data_path"])
            checkpoint_path = _contained_artifact_path(root, segment["checkpoint_path"])
            segment_summary_path = _contained_artifact_path(root, segment["summary_path"])
            listed_segment_paths.update(relative_paths)
            next_metadata = segment.get("next_segment_metadata_path")
            if next_metadata is not None:
                next_metadata_relative = Path(str(next_metadata))
                _contained_artifact_path(root, next_metadata)
                listed_segment_paths.add(next_metadata_relative)
            segment_id = str(segment["segment_id"])
            verified = verify_segment_chain(data_path, segment_id=segment_id)
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            segment_summary = json.loads(
                segment_summary_path.read_text(encoding="utf-8")
            )
            runtime_data_paths.append(data_path)
            with data_path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if verified.terminal_chain_hash != segment["terminal_chain_hash"]:
                failures.append(f"append-chain mismatch: {segment_id}")
            if checkpoint.get("schema_version") != EVIDENCE_CHECKPOINT_SCHEMA_VERSION:
                failures.append(f"checkpoint schema mismatch: {segment_id}")
            if checkpoint.get("chain_hash") != segment["terminal_chain_hash"]:
                failures.append(f"checkpoint hash mismatch: {segment_id}")
            expected_row_count = verified.record_count
            expected_byte_offset = verified.byte_offset
            for label, artifact in (
                ("checkpoint", checkpoint),
                ("manifest segment", segment),
                ("segment summary", segment_summary),
            ):
                if artifact.get("segment_id") != segment_id:
                    failures.append(f"{label} identity mismatch: {segment_id}")
                if artifact.get("last_committed_local_row_index") != expected_row_count:
                    failures.append(f"{label} row count mismatch: {segment_id}")
                if artifact.get("byte_offset") != expected_byte_offset:
                    failures.append(f"{label} byte offset mismatch: {segment_id}")
            if digest != segment["closed_file_sha256"]:
                failures.append(f"closed-file hash mismatch: {segment_id}")
            if segment.get("schema_version") != EVIDENCE_SUMMARY_SCHEMA_VERSION:
                failures.append(f"segment summary schema mismatch: {segment_id}")
            expected_segment_fields = {
                "schema_version": EVIDENCE_SUMMARY_SCHEMA_VERSION,
                "segment_id": segment_id,
                "segment_created": True,
                "segment_closed": True,
                "integrity_scope": "CLOSED_FILE",
                "last_committed_local_row_index": expected_row_count,
                "byte_offset": expected_byte_offset,
                "genesis_hash": chain_genesis_hash(segment_id),
                "terminal_chain_hash": verified.terminal_chain_hash,
                "closed_file_sha256": digest,
                "backup_verification_state": "NOT_VERIFIED",
                "retention_deletion_eligible": False,
            }
            for field, expected in expected_segment_fields.items():
                if segment.get(field) != expected:
                    failures.append(
                        "manifest segment field contradicts durable artifacts: "
                        f"{segment_id}: {field}"
                    )
                if segment_summary.get(field) != expected:
                    failures.append(
                        "segment summary field contradicts durable artifacts: "
                        f"{segment_id}: {field}"
                    )
            if segment_summary.get("created_at_utc") != checkpoint.get(
                "segment_created_at_utc"
            ):
                failures.append(f"segment creation timestamp mismatch: {segment_id}")
            try:
                created_at = _parse_required_time(
                    segment_summary.get("created_at_utc"),
                    "segment summary created_at_utc",
                )
                closed_at = _parse_required_time(
                    segment_summary.get("closed_at_utc"),
                    "segment summary closed_at_utc",
                )
                _require_aware(created_at, "segment summary created_at_utc")
                _require_aware(closed_at, "segment summary closed_at_utc")
                if closed_at < created_at:
                    failures.append(f"segment close timestamp precedes creation: {segment_id}")
            except ValueError as exc:
                failures.append(f"segment timing metadata invalid: {segment_id}: {exc}")
            terminal_reason = segment_summary.get("terminal_reason")
            rotation_reason = segment_summary.get("rotation_reason")
            if not isinstance(terminal_reason, str) or not terminal_reason:
                failures.append(f"segment terminal reason is invalid: {segment_id}")
            elif terminal_reason == "rotation" and rotation_reason not in {
                "BYTE_LIMIT",
                "TIME_LIMIT",
            }:
                failures.append(f"segment rotation reason is invalid: {segment_id}")
            elif terminal_reason != "rotation" and rotation_reason is not None:
                failures.append(f"segment rotation reason is unexpected: {segment_id}")
            if segment_summary.get("terminal_chain_hash") != segment["terminal_chain_hash"]:
                failures.append(f"segment summary artifact mismatch: {segment_id}")
            if segment_summary.get("closed_file_sha256") != digest:
                failures.append(f"segment summary closed-file hash mismatch: {segment_id}")
            recovery_summary_fields = _REQUIRED_SEGMENT_SUMMARY_FIELDS | {
                "partial_tail_bytes_removed"
            }
            allowed_summary_fields = (
                (_REQUIRED_SEGMENT_SUMMARY_FIELDS, recovery_summary_fields)
                if segment.get("recovery_status")
                in {"CRASH_RECOVERED", "FINALIZED_BEFORE_MANIFEST_SYNC"}
                else (_REQUIRED_SEGMENT_SUMMARY_FIELDS,)
            )
            if set(segment_summary) not in allowed_summary_fields:
                failures.append(f"segment summary field set mismatch: {segment_id}")
            for field, value in segment_summary.items():
                if field not in segment or segment[field] != value:
                    failures.append(
                        f"segment summary field contradicts manifest: {segment_id}: {field}"
                    )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"segment verification failed: {exc}")
    evidence_root = root / "evidence_segments"
    actual_segment_paths = {
        path.relative_to(root)
        for pattern in (
            "*.events.jsonl",
            "*.checkpoint.json",
            "*.summary.json",
            "*.start.json",
        )
        for path in evidence_root.rglob(pattern)
    }
    has_symlink = evidence_root.is_symlink() or any(
        path.is_symlink() for path in evidence_root.rglob("*")
    )
    if actual_segment_paths != listed_segment_paths or has_symlink:
        failures.append("segment artifact inventory contains missing or unlisted files")
    recovery_metadata: Mapping[str, object] | None = None
    recovery_path: Path | None = None
    try:
        candidate_recovery_path = _runtime_metadata_path(root, "runtime_recovery.json")
        if candidate_recovery_path.exists():
            recovery_path = candidate_recovery_path
    except (OSError, ValueError) as exc:
        failures.append(f"runtime recovery metadata unavailable: {exc}")
    if summary.get("status") == "d2_runtime_crash_recovered" and recovery_path is None:
        failures.append("runtime recovery metadata is missing")
    if recovery_path is not None:
        try:
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            if not isinstance(recovery, Mapping):
                raise ValueError("runtime recovery metadata must be an object")
            validate_no_secret_payload(recovery)
            validate_no_private_account_payload(recovery)
            recovery_metadata = recovery
            recovery_segment = next(
                (
                    segment
                    for segment in segments
                    if isinstance(segment, Mapping)
                    and segment.get("segment_id") == recovery.get("segment_id")
                ),
                None,
            )
            if recovery_segment is None:
                raise ValueError("runtime recovery segment is not in the manifest")
            recovery_data_path = _contained_artifact_path(
                root,
                recovery_segment["data_path"],
                reject_symlinks=True,
            )
            pre_recovery_file_size = recovery.get("pre_recovery_file_size")
            post_recovery_file_size = recovery.get("post_recovery_file_size")
            partial_tail_bytes_removed = recovery.get("partial_tail_bytes_removed")
            for field, value in (
                ("pre_recovery_file_size", pre_recovery_file_size),
                ("post_recovery_file_size", post_recovery_file_size),
                ("partial_tail_bytes_removed", partial_tail_bytes_removed),
            ):
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"runtime recovery {field} must be non-negative")
            if pre_recovery_file_size < post_recovery_file_size:
                raise ValueError("runtime recovery file size grew during recovery")
            if post_recovery_file_size != recovery_data_path.stat().st_size:
                raise ValueError("runtime recovery post-recovery file size mismatch")
            if partial_tail_bytes_removed != pre_recovery_file_size - post_recovery_file_size:
                raise ValueError("runtime recovery partial tail size mismatch")
            expected_recovery = {
                "runtime_schema_version": summary.get("runtime_schema_version"),
                "campaign_id": summary.get("campaign_id"),
                "segment_id": recovery_segment.get("segment_id"),
                "terminal_reason": "crash_recovered",
                "last_committed_local_row_index": recovery_segment.get(
                    "last_committed_local_row_index"
                ),
                "terminal_chain_hash": recovery_segment.get("terminal_chain_hash"),
                "closed_file_sha256": recovery_segment.get("closed_file_sha256"),
                "partial_tail_bytes_removed": recovery_segment.get(
                    "partial_tail_bytes_removed"
                ),
                "pre_recovery_file_size": pre_recovery_file_size,
                "post_recovery_file_size": post_recovery_file_size,
                "next_segment_metadata_path": recovery_segment.get(
                    "next_segment_metadata_path"
                ),
                "snapshot_required": recovery_segment.get(
                    "snapshot_required_after_recovery"
                ),
                "inherited_book_state": recovery_segment.get("inherited_book_state"),
            }
            expected_next_segment_id = (
                f"{summary['campaign_id']}.recovery.next"
            )
            expected_recovery["next_segment_id"] = expected_next_segment_id
            expected_recovery["next_segment_metadata_path"] = (
                f"evidence_segments/{expected_next_segment_id}.start.json"
            )
            expected_recovery["recovered_at_utc"] = recovery_segment.get("closed_at_utc")
            expected_recovery["validation_status"] = recovery.get("validation_status")
            if recovery.get("validation_status") not in {None, "pass", "fail", "blocked"}:
                raise ValueError("runtime recovery validation status is invalid")
            if set(recovery) != set(expected_recovery) | {
                "automatic_restart",
                "replay_qualified",
            }:
                raise ValueError("runtime recovery metadata field set mismatch")
            for field, expected in expected_recovery.items():
                if recovery.get(field) != expected:
                    raise ValueError(f"runtime recovery metadata mismatch: {field}")
            if recovery.get("automatic_restart") is not False:
                raise ValueError("runtime recovery automatic restart must remain false")
            if recovery.get("replay_qualified") is not False:
                raise ValueError("runtime recovery replay qualification must remain false")
            metadata_path = _runtime_metadata_path(
                root, recovery["next_segment_metadata_path"]
            )
            start = json.loads(metadata_path.read_text(encoding="utf-8"))
            expected_start = {
                "schema_version": EVIDENCE_SEGMENT_START_SCHEMA_VERSION,
                "segment_id": recovery["next_segment_id"],
                "previous_segment_id": recovery["segment_id"],
                "segment_created": True,
                "connection_reset_required": True,
                "snapshot_required": True,
                "inherited_book_state": False,
                "created_at_utc": recovery["recovered_at_utc"],
            }
            if not isinstance(start, Mapping) or set(start) != {
                *expected_start,
                "created_at_utc",
            } or any(
                start.get(field) != value for field, value in expected_start.items()
            ) or _parse_time(start.get("created_at_utc")) is None:
                raise ValueError("runtime recovery segment-start metadata mismatch")
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"runtime recovery metadata verification failed: {exc}")
    for sibling_name in ("campaign_manifest.json", "run_metadata.json"):
        try:
            sibling = json.loads(
                _runtime_metadata_path(root, sibling_name).read_text(encoding="utf-8")
            )
            if sibling != summary:
                failures.append(f"{sibling_name} contradicts campaign_summary.json")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{sibling_name} unavailable: {exc}")
    for field, expected in (
        ("live_gate_status", "disabled"),
        ("production_trading_enabled", False),
        ("executable_order_intent", False),
        ("production_endpoint_used", False),
        ("submit_attempts", 0),
        ("real_money_trading", False),
        ("replay_qualified", False),
    ):
        if summary.get(field) != expected:
            failures.append(f"unsafe runtime field: {field}")

    recorded_integrity = summary.get("artifact_integrity_summary")
    if not isinstance(recorded_integrity, Mapping):
        failures.append("artifact integrity summary is missing or invalid")
    elif recovery_metadata is not None:
        expected_integrity = {
            "integrity_scope": "CLOSED_FILE",
            "recovery_status": "CRASH_RECOVERED",
            "partial_tail_bytes_removed": recovery_metadata["partial_tail_bytes_removed"],
            "snapshot_required": recovery_metadata["snapshot_required"],
            "inherited_book_state": recovery_metadata["inherited_book_state"],
        }
        if dict(recorded_integrity) != expected_integrity:
            failures.append("artifact integrity summary contradicts recovery metadata")
    else:
        expected_integrity = {
            "schema_valid": True,
            "required_artifacts_present": bool(segments),
            "append_chain_verified": True,
            "atomic_checkpoint_verified": True,
            "closed_file_hash_verified": True,
            "prohibited_content_scan": "PASS",
            "recovery_status": "NOT_APPLICABLE_CLEAN_CLOSE",
            "partial_tail_bytes_removed": 0,
            "segment_count": len(segments),
        }
        if dict(recorded_integrity) != expected_integrity:
            failures.append("artifact integrity summary contradicts verified artifacts")
    try:
        dimensions, durable_counts, durable_fields, _ = _derive_runtime_validation(
            summary,
            chain.from_iterable(_iter_runtime_records(path) for path in runtime_data_paths),
        )
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(f"durable evidence classification failed: {exc}")
        dimensions = {
            field: EvidenceStatus.UNKNOWN
            for field in EvidenceDimensions.__dataclass_fields__
        }
        durable_counts = Counter()
        durable_fields = {}
    recorded_dimensions = summary.get("independent_evidence_classifications")
    if not isinstance(recorded_dimensions, Mapping):
        failures.append("recorded evidence dimensions are missing or invalid")
        recorded_dimensions = {}
    for field, derived in dimensions.items():
        if field != "artifact_integrity" and recorded_dimensions.get(field) != derived:
            failures.append(f"recorded evidence dimension contradicts durable records: {field}")
    for field, expected in durable_counts.items():
        if summary.get(field) != expected:
            failures.append(f"summary count contradicts durable records: {field}")
    for field, expected in durable_fields.items():
        if summary.get(field) != expected:
            failures.append(f"summary evidence contradicts durable records: {field}")
    dimensions["artifact_integrity"] = (
        EvidenceStatus.PASS if not failures else EvidenceStatus.FAIL
    )
    if recorded_dimensions.get("artifact_integrity") != dimensions["artifact_integrity"]:
        failures.append("recorded evidence dimension contradicts artifacts: artifact_integrity")
        dimensions["artifact_integrity"] = EvidenceStatus.FAIL
    overall = classify_evidence(EvidenceDimensions(**dimensions)).overall_classification
    if summary.get("overall_evidence_classification") != overall:
        failures.append("overall evidence classification contradicts durable records")
    result = {
        "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "status": "pass" if not failures else "fail",
        "campaign_id": summary.get("campaign_id"),
        **dimensions,
        "overall_evidence_classification": overall,
        "event_count": durable_counts["event_count"],
        "snapshot_count": durable_counts["snapshot_count"],
        "delta_count": durable_counts["delta_count"],
        "trade_count": durable_counts["trade_count"],
        "rebuild_frame_count": durable_counts["rebuild_frame_count"],
        "failures": failures,
        "live_gate_status": summary.get("live_gate_status"),
        "submit_attempts": summary.get("submit_attempts"),
        "strict_verdict": "STRICT NO-GO",
    }
    if persist and validation_path is not None:
        _atomic_write_json(validation_path, result)
    return result


def _validate_d2_preflight_block(
    root: Path,
    summary: Mapping[str, object],
    *,
    persist: bool = True,
) -> dict[str, object]:
    failures: list[str] = []
    try:
        validation = json.loads(
            _runtime_metadata_path(root, "campaign_validation.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        validation = {}
        failures.append(f"campaign_validation unavailable: {exc}")
    if not isinstance(validation, Mapping):
        validation = {}
        failures.append("campaign_validation must be a JSON object")
    try:
        validate_no_secret_payload(summary)
        _validate_runtime_metadata_safety(summary)
    except ValueError as exc:
        failures.append(str(exc))
    for sibling_name in ("campaign_manifest.json", "run_metadata.json"):
        try:
            sibling = json.loads(
                _runtime_metadata_path(root, sibling_name).read_text(encoding="utf-8")
            )
            if sibling != summary:
                failures.append(f"{sibling_name} contradicts campaign_summary.json")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{sibling_name} unavailable: {exc}")
    for field, expected in (
        ("runtime_schema_version", D2_RUNTIME_SCHEMA_VERSION),
        ("live_gate_status", "disabled"),
        ("production_trading_enabled", False),
        ("executable_order_intent", False),
        ("production_endpoint_used", False),
        ("submit_attempts", 0),
        ("real_money_trading", False),
        ("replay_qualified", False),
        ("event_count", 0),
        ("snapshot_count", 0),
        ("delta_count", 0),
        ("trade_count", 0),
        ("rebuild_frame_count", 0),
        ("segment_summaries", []),
    ):
        if summary.get(field) != expected:
            failures.append(f"invalid preflight field: {field}")
    if not summary.get("blocker_code"):
        failures.append("preflight blocker_code is required")
    if not isinstance(summary.get("selected_market_selection"), Mapping):
        failures.append("preflight selection provenance is required")
    canonical_dimensions = _preflight_dimensions().to_record()
    for field, expected in {
        "raw_event_schema_version": KALSHI_WS_RAW_SCHEMA_VERSION,
        "subscription_identity_model": CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION,
        "evidence_schema_version": EVIDENCE_CHAIN_SCHEMA_VERSION,
        "threshold_policy_version": V2_THRESHOLD_POLICY.version,
        "threshold_policy": V2_THRESHOLD_POLICY.to_record(),
        "status": "d2_runtime_preflight_blocked",
        "actual_elapsed_seconds": "0",
        "connected_elapsed_seconds": "0",
        "terminal_reason": f"preflight_blocked:{summary.get('blocker_code')}",
        "stop_requested": False,
        "connection_windows": [],
        "disconnect_durations": [],
        "sequence_summaries": [],
        "rebuild_summaries": [],
        "independent_evidence_classifications": canonical_dimensions,
        "overall_evidence_classification": "FAIL",
        "artifact_integrity_summary": {
            "required_artifacts_present": False,
            "status": "NOT_APPLICABLE_PREFLIGHT_BLOCK",
        },
        "source_type": "WEBSOCKET_NO_ORDERBOOK",
        "connection_established": False,
        "subscription_acknowledged": False,
        "validation_status": "blocked",
        "evidence_classification": summary.get("blocker_code"),
    }.items():
        if summary.get(field) != expected:
            failures.append(f"invalid canonical preflight field: {field}")
    if summary.get("threshold_source_commit") != summary.get("public_code_commit"):
        failures.append("preflight threshold provenance contradicts public code")
    configured_duration = summary.get("configured_duration_seconds")
    if not (
        configured_duration == summary.get("duration_seconds")
        and isinstance(configured_duration, int)
        and configured_duration > 0
    ):
        failures.append("preflight configured duration is invalid")
    if not (
        summary.get("started_at")
        == summary.get("started_at_utc")
        == summary.get("ended_at")
        == summary.get("ended_at_utc")
    ):
        failures.append("preflight timing boundaries contradict")
    expected_validation = {
        "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "status": "blocked",
        "campaign_id": summary.get("campaign_id"),
        "blocker_code": summary.get("blocker_code"),
        **canonical_dimensions,
        "overall_evidence_classification": "FAIL",
        "source_type": "WEBSOCKET_NO_ORDERBOOK",
        "event_count": 0,
        "snapshot_count": 0,
        "delta_count": 0,
        "trade_count": 0,
        "live_gate_status": "disabled",
        "submit_attempts": 0,
        "strict_verdict": "STRICT NO-GO",
    }
    if validation != expected_validation:
        failures.append("preflight validation artifact contradicts summary")
    if failures:
        result = {
            **validation,
            "status": "fail",
            "failures": failures,
            "strict_verdict": "STRICT NO-GO",
        }
        if persist:
            try:
                _atomic_write_json(_runtime_metadata_path(root, "campaign_validation.json"), result)
            except (OSError, ValueError):
                pass
        return result
    return expected_validation


def _validate_runtime_metadata_safety(summary: Mapping[str, object]) -> None:
    validate_no_private_account_payload(summary, path="campaign_summary")
    for field in ("selected_market_metadata", "selected_market_selection"):
        value = summary.get(field)
        if isinstance(value, Mapping):
            validate_no_private_account_payload(value, path=field)


def _iter_runtime_records(path: Path) -> Iterator[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            validate_no_secret_payload(record)
            if record.get("schema_version") != D2_RUNTIME_RECORD_SCHEMA_VERSION:
                raise ValueError("runtime record schema missing or unsupported")
            record_type = record.get("record_type")
            if not isinstance(record_type, str):
                raise ValueError("runtime record type is required")
            if record_type == "raw_transport_event":
                d2a_event = record.get("d2a_event")
                if not isinstance(d2a_event, Mapping):
                    raise ValueError("durable raw record is missing its D2A envelope")
                validate_no_private_account_payload(
                    d2a_event.get("original_payload")
                    if isinstance(d2a_event.get("original_payload"), Mapping)
                    else {},
                    path="d2a_event.original_payload",
                )
                KalshiWsRawEvent.from_record(d2a_event)
            yield record


def _iter_summary_runtime_records(
    root: Path,
    segments: Iterable[Mapping[str, object]],
) -> Iterator[dict[str, object]]:
    return chain.from_iterable(
        _iter_runtime_records(_contained_artifact_path(root, segment["data_path"]))
        for segment in segments
    )


def _update_validation_connection_state(
    states: dict[str, dict[str, object]],
    event: ConnectionEvidenceEvent,
) -> None:
    state = states.get(event.connection_id)
    if event.event_type in {
        ConnectionEvidenceType.CONNECTION_OPEN,
        ConnectionEvidenceType.RECONNECT,
    }:
        if state is not None:
            raise ValueError("connection identifiers must be unique")
        states[event.connection_id] = {
            "opened_at": event.observed_at_utc,
            "opening_segment_id": event.segment_id,
            "acknowledged_at": None,
            "acknowledged_segment_id": None,
            "closed_at": None,
            "last_event_at": None,
        }
        return
    if state is None or state["closed_at"] is not None:
        raise ValueError("connection evidence occurred outside an open connection")
    opened_at = state["opened_at"]
    if not isinstance(opened_at, datetime) or event.observed_at_utc < opened_at:
        raise ValueError("connection evidence predates its open event")
    last_event_at = state["last_event_at"]
    if isinstance(last_event_at, datetime) and event.observed_at_utc < last_event_at:
        raise ValueError("connection evidence predates its latest D2A event")
    if event.event_type is ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED:
        if state["acknowledged_at"] is not None:
            raise ValueError("connection has duplicate subscription acknowledgment")
        state["acknowledged_at"] = event.observed_at_utc
        state["acknowledged_segment_id"] = event.segment_id
    elif event.event_type is ConnectionEvidenceType.CONNECTION_CLOSE:
        state["closed_at"] = event.observed_at_utc


def _validate_event_subscription_state(
    event: KalshiWsRawEvent,
    states: dict[str, dict[str, object]],
    *,
    require_channel_binding: bool,
) -> None:
    state = states.get(event.connection_id)
    if state is None:
        raise ValueError("D2A event has no matching connection open evidence")
    opened_at = state.get("opened_at")
    acknowledged_at = state.get("acknowledged_at")
    closed_at = state.get("closed_at")
    subscription_control = event.native_type in {
        "subscribed",
        "ack",
        "ok",
        "error",
        "rejected",
    }
    if not isinstance(opened_at, datetime) or event.received_at_utc < opened_at:
        raise ValueError("D2A event predates its connection open evidence")
    if not subscription_control and (
        not isinstance(acknowledged_at, datetime)
        or event.received_at_utc < acknowledged_at
    ):
        raise ValueError("D2A event was recorded before subscription acknowledgment")
    if isinstance(closed_at, datetime) and event.received_at_utc >= closed_at:
        raise ValueError("D2A event was recorded after connection close")
    last_event_at = state.get("last_event_at")
    if isinstance(last_event_at, datetime) and event.received_at_utc < last_event_at:
        raise ValueError("D2A event chronology moves backwards")
    if not subscription_control and event.segment_boundary_reason in {
        SegmentBoundaryReason.NEW_SUBSCRIPTION,
        SegmentBoundaryReason.RESUBSCRIPTION,
    } and event.segment_id != state.get("acknowledged_segment_id"):
        raise ValueError("D2A subscription segment contradicts acknowledgment evidence")
    if require_channel_binding:
        _validate_channel_binding(event)
    state["last_event_at"] = event.received_at_utc


def _validate_channel_binding(event: KalshiWsRawEvent) -> None:
    if event.subscription_identity_model not in {
        CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION,
        LEGACY_CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION,
    }:
        raise ValueError("D2A event lacks channel-scoped subscription identity")
    if event.subscription_binding_state is SubscriptionBindingState.REQUEST_MISMATCH:
        raise ValueError("D2A subscription acknowledgment request ID mismatch")
    expected_channel = (
        "orderbook_delta"
        if event.native_type in {"orderbook_snapshot", "orderbook_delta"}
        else "trade"
        if event.native_type == "trade"
        else None
    )
    if expected_channel is not None and event.channel != expected_channel:
        raise ValueError("D2A native type contradicts its channel binding")
    if event.native_type in {"subscribed", "ack", "ok", "error", "rejected"}:
        if event.channel in REQUIRED_PUBLIC_CHANNELS and (
            event.subscription_generation is None
            or event.subscription_binding_id is None
            or isinstance(event.subscription_command_id, bool)
            or not isinstance(event.subscription_command_id, int)
            or event.subscription_command_id < 1
            or (
                event.subscription_identity_model
                == CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION
                and (event.connection_epoch is None or event.run_request_index is None)
            )
        ):
            raise ValueError("D2A subscription control lacks a channel binding")
        return
    binding_required = (
        event.native_type in {"orderbook_snapshot", "orderbook_delta", "trade"}
        or event.channel in REQUIRED_PUBLIC_CHANNELS
    )
    if not binding_required:
        return
    if (
        event.subscription_generation is None
        or event.subscription_binding_id is None
        or isinstance(event.subscription_command_id, bool)
        or not isinstance(event.subscription_command_id, int)
        or event.subscription_command_id < 1
        or (
            event.subscription_identity_model
            == CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION
            and (event.connection_epoch is None or event.run_request_index is None)
        )
        or event.subscription_binding_state
        is not SubscriptionBindingState.ACKNOWLEDGED
    ):
        raise ValueError("D2A public channel row lacks a valid channel binding")
    expected_suffix = (
        f":subscription:{event.channel}:{event.subscription_generation:04d}"
    )
    if not event.subscription_binding_id.startswith(f"{event.connection_id}:") or not (
        event.subscription_binding_id.endswith(expected_suffix)
    ):
        raise ValueError("D2A channel binding identity is inconsistent")


def _replay_channel_binding(
    event: KalshiWsRawEvent,
    bindings: dict[object, dict[str, object]],
    requests: Mapping[tuple[str, str], SubscriptionRequestEvidence],
) -> None:
    if (
        event.subscription_identity_model
        == LEGACY_CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION
    ):
        _replay_legacy_channel_binding(event, bindings)
        return
    envelope = normalize_native_envelope(event.original_payload)
    if envelope.rejection != event.native_envelope_rejection:
        raise ValueError("D2A native envelope rejection was not independently reproduced")
    request = requests.get((event.connection_id, envelope.channel))
    if request is None and envelope.native_type in {"error", "rejected"}:
        matches = tuple(
            candidate
            for (connection_id, _channel), candidate in requests.items()
            if connection_id == event.connection_id
            and candidate.native_command_id == envelope.request_id
        )
        request = matches[0] if len(matches) == 1 else None
    binding_channel = request.channel if request is not None else envelope.channel
    binding = bindings.get(binding_channel)
    if envelope.native_type in {"subscribed", "ack", "ok"}:
        if envelope.rejection is not None:
            return
        request_matches = (
            request is not None
            and request.send_outcome == "SENT"
            and envelope.request_id == request.native_command_id
            and event.subscription_command_id == request.native_command_id
            and event.subscription_generation == request.subscription_generation
            and event.connection_epoch == request.connection_epoch
            and event.run_request_index == request.run_request_index
        )
        if not request_matches:
            if event.subscription_binding_state is not SubscriptionBindingState.REQUEST_MISMATCH:
                raise ValueError("D2A unknown or stale acknowledgment state was not reproduced")
            if (
                event.subscription_binding_observation
                is not SubscriptionBindingObservation.STALE_ACK
            ):
                raise ValueError("D2A stale acknowledgment evidence was not reproduced")
            return
        exact_duplicate = (
            binding is not None
            and binding["connection_id"] == event.connection_id
            and binding["sid"] == envelope.sid
            and binding["generation"] == request.subscription_generation
            and binding["request_id"] == request.native_command_id
            and binding["state"] is SubscriptionBindingState.ACKNOWLEDGED
        )
        if exact_duplicate:
            expected = SubscriptionBindingState.ACKNOWLEDGED
            expected_observation = SubscriptionBindingObservation.DUPLICATE_ACK
        elif binding is None or (
            binding["connection_id"] != event.connection_id
            and request.subscription_generation == binding["generation"] + 1
            and request.native_command_id != binding["request_id"]
        ):
            bindings[envelope.channel] = {
                "sid": envelope.sid,
                "state": SubscriptionBindingState.ACKNOWLEDGED,
                "generation": request.subscription_generation,
                "request_id": request.native_command_id,
                "connection_id": event.connection_id,
                "connection_epoch": request.connection_epoch,
                "run_request_index": request.run_request_index,
            }
            expected = SubscriptionBindingState.ACKNOWLEDGED
            expected_observation = SubscriptionBindingObservation.ACKNOWLEDGED
        elif (
            binding["connection_id"] == event.connection_id
            and request.subscription_generation == binding["generation"] + 1
            and request.native_command_id != binding["request_id"]
        ):
            binding.update(
                sid=envelope.sid,
                state=SubscriptionBindingState.ACKNOWLEDGED,
                generation=request.subscription_generation,
                request_id=request.native_command_id,
                connection_id=event.connection_id,
                connection_epoch=request.connection_epoch,
                run_request_index=request.run_request_index,
            )
            expected = SubscriptionBindingState.ACKNOWLEDGED
            expected_observation = SubscriptionBindingObservation.ACKNOWLEDGED
        else:
            binding["state"] = SubscriptionBindingState.CONFLICTED
            expected = SubscriptionBindingState.CONFLICTED
            expected_observation = SubscriptionBindingObservation.CONFLICTING_ACK
        if event.subscription_binding_state is not expected:
            raise ValueError("D2A acknowledgment state contradicts independent replay")
        if event.subscription_binding_observation is not expected_observation:
            raise ValueError("D2A acknowledgment observation contradicts replay")
        return
    if envelope.native_type in {"error", "rejected"}:
        request_matches = (
            envelope.rejection is None
            and request is not None
            and request.send_outcome == "SENT"
            and envelope.request_id == request.native_command_id
            and event.subscription_command_id == request.native_command_id
            and event.subscription_generation == request.subscription_generation
            and event.connection_epoch == request.connection_epoch
            and event.run_request_index == request.run_request_index
        )
        if request_matches:
            if binding is None:
                bindings[binding_channel] = {
                    "sid": None,
                    "state": SubscriptionBindingState.REJECTED,
                    "generation": request.subscription_generation,
                    "request_id": request.native_command_id,
                    "connection_id": event.connection_id,
                    "connection_epoch": request.connection_epoch,
                    "run_request_index": request.run_request_index,
                }
                expected = SubscriptionBindingState.REJECTED
                expected_observation = SubscriptionBindingObservation.REJECTED
            elif (
                binding["connection_id"] == event.connection_id
                and binding["generation"] == request.subscription_generation
                and binding["request_id"] == request.native_command_id
            ):
                if binding["state"] is SubscriptionBindingState.REJECTED:
                    expected = SubscriptionBindingState.REJECTED
                    expected_observation = (
                        SubscriptionBindingObservation.DUPLICATE_REJECTION
                    )
                else:
                    binding["state"] = SubscriptionBindingState.CONFLICTED
                    expected = SubscriptionBindingState.CONFLICTED
                    expected_observation = (
                        SubscriptionBindingObservation.CONFLICTING_REJECTION
                    )
            elif (
                request.subscription_generation == binding["generation"] + 1
                and request.native_command_id != binding["request_id"]
            ):
                bindings[binding_channel] = {
                    "sid": None,
                    "state": SubscriptionBindingState.REJECTED,
                    "generation": request.subscription_generation,
                    "request_id": request.native_command_id,
                    "connection_id": event.connection_id,
                    "connection_epoch": request.connection_epoch,
                    "run_request_index": request.run_request_index,
                }
                expected = SubscriptionBindingState.REJECTED
                expected_observation = SubscriptionBindingObservation.REJECTED
            else:
                raise ValueError("D2A rejection contradicts active binding identity")
        else:
            if request is None and binding is None:
                expected = SubscriptionBindingState.UNKNOWN
                expected_observation = None
            else:
                expected = SubscriptionBindingState.REQUEST_MISMATCH
                expected_observation = SubscriptionBindingObservation.REJECTED
        if event.subscription_binding_state is not expected:
            raise ValueError("D2A rejection state contradicts independent replay")
        if event.subscription_binding_observation is not expected_observation:
            raise ValueError("D2A rejection observation contradicts replay")
        return
    if envelope.native_type not in {"orderbook_snapshot", "orderbook_delta", "trade"}:
        return
    trusted = (
        envelope.rejection is None
        and binding is not None
        and binding["connection_id"] == event.connection_id
        and binding["state"] is SubscriptionBindingState.ACKNOWLEDGED
        and binding["sid"] == envelope.sid
        and binding["generation"] == event.subscription_generation
        and request is not None
        and request.send_outcome == "SENT"
        and event.subscription_command_id == request.native_command_id
        and event.connection_epoch == request.connection_epoch
        and event.run_request_index == request.run_request_index
        and binding["connection_epoch"] == request.connection_epoch
        and binding["run_request_index"] == request.run_request_index
    )
    if trusted:
        if event.subscription_binding_state is not SubscriptionBindingState.ACKNOWLEDGED:
            raise ValueError("trusted D2A data binding state contradicts replay")
    elif event.admission_status is not AdmissionStatus.EXCLUDED:
        raise ValueError("untrusted D2A data was admitted before binding confirmation")


def _replay_legacy_channel_binding(
    event: KalshiWsRawEvent,
    bindings: dict[object, dict[str, object]],
) -> None:
    envelope = normalize_native_envelope(event.original_payload)
    key = (event.connection_id, envelope.channel)
    binding = bindings.get(key)
    if envelope.native_type in {"subscribed", "ack", "ok"}:
        if envelope.rejection is not None:
            return
        if envelope.request_id != event.subscription_command_id:
            if event.subscription_binding_state is not SubscriptionBindingState.REQUEST_MISMATCH:
                raise ValueError("legacy D2A stale acknowledgment state was not reproduced")
            return
        if binding is None:
            bindings[key] = {
                "sid": envelope.sid,
                "state": SubscriptionBindingState.ACKNOWLEDGED,
                "generation": event.subscription_generation,
                "request_id": envelope.request_id,
            }
            expected = SubscriptionBindingState.ACKNOWLEDGED
            observation = SubscriptionBindingObservation.ACKNOWLEDGED
        elif binding["state"] is SubscriptionBindingState.ACKNOWLEDGED:
            if binding["sid"] == envelope.sid:
                expected = SubscriptionBindingState.ACKNOWLEDGED
                observation = SubscriptionBindingObservation.DUPLICATE_ACK
            else:
                binding["state"] = SubscriptionBindingState.CONFLICTED
                expected = SubscriptionBindingState.CONFLICTED
                observation = SubscriptionBindingObservation.CONFLICTING_ACK
        else:
            expected = binding["state"]
            observation = SubscriptionBindingObservation.CONFLICTING_ACK
        if event.subscription_binding_state is not expected:
            raise ValueError("legacy D2A acknowledgment state contradicts replay")
        if event.subscription_binding_observation is not observation:
            raise ValueError("legacy D2A acknowledgment observation contradicts replay")
        return
    if envelope.native_type not in {"orderbook_snapshot", "orderbook_delta", "trade"}:
        return
    trusted = (
        envelope.rejection is None
        and binding is not None
        and binding["state"] is SubscriptionBindingState.ACKNOWLEDGED
        and binding["sid"] == envelope.sid
        and binding["generation"] == event.subscription_generation
    )
    if trusted:
        if event.subscription_binding_state is not SubscriptionBindingState.ACKNOWLEDGED:
            raise ValueError("legacy trusted D2A binding state contradicts replay")
    elif event.admission_status is not AdmissionStatus.EXCLUDED:
        raise ValueError("legacy untrusted D2A data was admitted")


def _validate_runtime_launch_record(
    launch: Mapping[str, object],
    campaign_id: str,
) -> None:
    for field, expected in (
        ("runtime_schema_version", D2_RUNTIME_SCHEMA_VERSION),
        ("raw_event_schema_version", KALSHI_WS_RAW_SCHEMA_VERSION),
        ("evidence_schema_version", EVIDENCE_CHAIN_SCHEMA_VERSION),
        ("threshold_policy_version", V2_THRESHOLD_POLICY.version),
        ("threshold_policy", V2_THRESHOLD_POLICY.to_record()),
        ("campaign_id", campaign_id),
        ("subscription_channels", sorted(REQUIRED_PUBLIC_CHANNELS)),
    ):
        if launch.get(field) != expected:
            raise ValueError(f"durable runtime launch contradicts {field}")
    identity_model = launch.get("subscription_identity_model")
    if identity_model == CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION:
        if launch.get("subscription_request_policy") != (
            "one_channel_per_command_run_unique_positive_id"
        ):
            raise ValueError(
                "durable runtime launch contradicts subscription_request_policy"
            )
    elif identity_model == LEGACY_CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION:
        if launch.get("subscription_command_id") != 1:
            raise ValueError("legacy durable runtime launch contradicts command ID")
    elif identity_model is not None:
        raise ValueError("durable runtime launch identity model is unsupported")
    if launch.get("threshold_source_commit") != launch.get("public_code_commit"):
        raise ValueError("durable runtime launch threshold provenance contradicts code")
    if not isinstance(launch.get("use_yes_price"), bool):
        raise ValueError("durable runtime launch use_yes_price must be Boolean")
    provenance_fields = {
        "public_code_commit": launch.get("public_code_commit"),
        "branch": launch.get("branch"),
        "remote": launch.get("remote"),
        "dirty_state": launch.get("dirty_state"),
    }
    if not all(
        isinstance(provenance_fields[field], str)
        for field in ("public_code_commit", "branch", "remote")
    ):
        raise ValueError("durable runtime code provenance types are invalid")
    try:
        provenance = RuntimeCodeProvenance(**provenance_fields)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("durable runtime code provenance is invalid") from exc
    if provenance.to_record() != provenance_fields:
        raise ValueError("durable runtime code provenance is not canonical")
    for field in ("selected_market_metadata", "selected_market_selection"):
        value = _required_mapping(launch, field)
        validate_no_secret_payload(value, path=f"runtime_launch.{field}")
        validate_no_private_account_payload(value, path=f"runtime_launch.{field}")


def _observe_runtime_gap(
    *,
    previous: datetime | None,
    maximum: int | None,
    observed_at_utc: datetime,
    started_at_utc: datetime,
) -> tuple[datetime, int]:
    return observed_at_utc, _max_age(
        maximum,
        _age_seconds(observed_at_utc, previous or started_at_utc),
    )


def _derive_runtime_validation(
    summary: Mapping[str, object],
    records: Iterable[Mapping[str, object]],
    *,
    allow_summary_terminal: bool = False,
) -> tuple[
    dict[str, EvidenceStatus],
    Counter[str],
    dict[str, object],
    dict[str, object],
]:
    sequence: dict[tuple[str, str], dict[str, object]] = {}
    rebuild: dict[tuple[str, str, str], dict[str, object]] = {}
    connection_events: list[Mapping[str, object]] = []
    lifecycle_observation_count = 0
    latest_lifecycle_record: Mapping[str, object] | None = None
    lifecycle_invalid_observed = False
    last_lifecycle_at: datetime | None = None
    maximum_lifecycle_age: int | None = None
    lifecycle_observed_min: datetime | None = None
    lifecycle_observed_max: datetime | None = None
    launch_record: Mapping[str, object] | None = None
    terminal_record: Mapping[str, object] | None = None
    durable_campaign_ids: set[str] = set()
    connection_states: dict[str, dict[str, object]] = {}
    connection_epochs: dict[str, int] = {}
    last_connection_observed_at: datetime | None = None
    last_event_at: datetime | None = None
    first_snapshot_at: datetime | None = None
    last_keepalive_at: datetime | None = None
    maximum_keepalive_age: int | None = None
    last_orderbook_at: datetime | None = None
    maximum_orderbook_quiet: int | None = None
    raw_observed_min: datetime | None = None
    raw_observed_max: datetime | None = None
    durable_ack_channels: dict[str, set[str]] = {}
    validation_bindings: dict[str, dict[str, object]] = {}
    validation_requests: dict[tuple[str, str], SubscriptionRequestEvidence] = {}
    requests_with_inbound_evidence: set[tuple[str, str]] = set()
    used_command_ids: set[int] = set()
    last_generation_by_channel: dict[str, int] = {}
    last_run_request_index = 0
    counts: Counter[str] = Counter()
    selected_market: str | None = None
    launch_started_at: datetime | None = None
    validation_rebuilder: KalshiWsBookRebuilder | None = None
    for record in records:
        record_campaign_id = record.get("campaign_id")
        if not isinstance(record_campaign_id, str) or not record_campaign_id:
            raise ValueError("durable runtime record campaign_id is required")
        durable_campaign_ids.add(record_campaign_id)
        record_type = record["record_type"]
        if record_type == "runtime_launch":
            if launch_record is not None:
                raise ValueError("exactly one durable runtime launch record is required")
            launch_record = _required_mapping(record, "runtime_launch")
            launch_started_at = _parse_required_time(
                launch_record.get("started_at_utc"), "launch started_at_utc"
            )
            market_metadata = _required_mapping(
                launch_record, "selected_market_metadata"
            )
            ticker = market_metadata.get("ticker") or market_metadata.get("market_ticker")
            if not isinstance(ticker, str) or not ticker:
                raise ValueError("durable runtime launch selected market is invalid")
            selected_market = ticker
            _validate_runtime_launch_record(launch_record, record_campaign_id)
            validation_rebuilder = KalshiWsBookRebuilder(
                explicit_pricing_mode=(
                    PricingMode.UNIFIED_YES_PRICE
                    if launch_record["use_yes_price"] is True
                    else PricingMode.LEGACY_SIDE_PRICE
                )
            )
            continue
        if (
            launch_record is None
            or selected_market is None
            or launch_started_at is None
            or validation_rebuilder is None
        ):
            raise ValueError("durable runtime launch must precede all runtime evidence")
        if record_type == "connection_evidence":
            connection_record = _required_mapping(record, "connection_event")
            observed_at = _parse_required_time(
                connection_record.get("observed_at_utc"),
                "connection observed_at_utc",
            )
            connection = ConnectionEvidenceEvent(
                event_type=connection_record["event_type"],
                observed_at_utc=observed_at,
                connection_id=str(connection_record["connection_id"]),
                segment_id=str(connection_record["segment_id"]),
                reason=str(connection_record["reason"]),
                previous_connection_id=connection_record.get("previous_connection_id"),
                previous_segment_id=connection_record.get("previous_segment_id"),
            )
            if connection.to_record() != connection_record:
                raise ValueError("durable connection evidence contradicts its schema")
            if (
                last_connection_observed_at is not None
                and observed_at < last_connection_observed_at
            ):
                raise ValueError("connection evidence chronology moves backwards")
            if (
                connection.event_type
                is ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED
                and not REQUIRED_PUBLIC_CHANNELS
                <= durable_ack_channels.get(connection.connection_id, set())
            ):
                raise ValueError(
                    "typed subscription acknowledgment precedes durable raw channels"
                )
            last_connection_observed_at = observed_at
            _update_validation_connection_state(connection_states, connection)
            if connection.event_type in {
                ConnectionEvidenceType.CONNECTION_OPEN,
                ConnectionEvidenceType.RECONNECT,
            }:
                if connection.connection_id in connection_epochs:
                    raise ValueError("connection identity was reused")
                connection_epochs[connection.connection_id] = len(connection_epochs) + 1
            connection_events.append(connection_record)
            continue
        if record_type == "lifecycle_evidence":
            lifecycle_record = _required_mapping(record, "lifecycle_event")
            lifecycle = KalshiRestLifecycleEvidence(
                market_ticker=str(lifecycle_record["market_ticker"]),
                observed_at_utc=_parse_required_time(
                    lifecycle_record.get("observed_at_utc"),
                    "lifecycle observed_at_utc",
                ),
                evaluated_at_utc=_parse_required_time(
                    lifecycle_record.get("evaluated_at_utc"),
                    "lifecycle evaluated_at_utc",
                ),
                raw_status=lifecycle_record.get("raw_status"),
                normalized_status=lifecycle_record.get("normalized_status"),
                lifecycle_status=lifecycle_record["lifecycle_status"],
                validity=lifecycle_record["validity"],
                observation_age_seconds=int(lifecycle_record["observation_age_seconds"]),
                max_age_seconds=int(lifecycle_record["max_age_seconds"]),
                mve_unsupported=lifecycle_record["mve_unsupported"],
            )
            if lifecycle.market_ticker != selected_market:
                raise ValueError("lifecycle evidence does not match selected market")
            if lifecycle.to_record() != lifecycle_record:
                raise ValueError("durable lifecycle evidence contradicts its schema")
            lifecycle_observation_count += 1
            latest_lifecycle_record = lifecycle_record
            lifecycle_invalid_observed |= (
                lifecycle.lifecycle_status is not LifecycleStatus.OPEN
                or lifecycle.validity is not LifecycleValidity.VALID
            )
            last_lifecycle_at, maximum_lifecycle_age = _observe_runtime_gap(
                previous=last_lifecycle_at,
                maximum=maximum_lifecycle_age,
                observed_at_utc=lifecycle.observed_at_utc,
                started_at_utc=launch_started_at,
            )
            lifecycle_observed_min = min(
                lifecycle_observed_min or lifecycle.observed_at_utc,
                lifecycle.observed_at_utc,
            )
            lifecycle_observed_max = max(
                lifecycle_observed_max or lifecycle.observed_at_utc,
                lifecycle.observed_at_utc,
            )
            continue
        if record_type == "subscription_request_evidence":
            request = SubscriptionRequestEvidence.from_record(
                _required_mapping(record, "subscription_request")
            )
            key = (request.connection_id, request.channel)
            prior = validation_requests.get(key)
            if request.send_outcome == "PENDING_SEND":
                if prior is not None:
                    raise ValueError("duplicate pending subscription request")
                if request.run_request_index != last_run_request_index + 1:
                    raise ValueError("subscription run request index is not contiguous")
                if request.native_command_id in used_command_ids:
                    raise ValueError("native subscription command ID was reused")
                if request.subscription_generation != (
                    last_generation_by_channel.get(request.channel, 0) + 1
                ):
                    raise ValueError("subscription generation is not contiguous")
                if request.connection_id not in connection_states:
                    raise ValueError("subscription request lacks connection-open evidence")
                if connection_epochs.get(request.connection_id) != request.connection_epoch:
                    raise ValueError("subscription request connection epoch is invalid")
                validation_requests[key] = request
                used_command_ids.add(request.native_command_id)
                last_generation_by_channel[request.channel] = request.subscription_generation
                last_run_request_index = request.run_request_index
            else:
                if (
                    prior is None
                    or prior.send_outcome != "PENDING_SEND"
                    or key in requests_with_inbound_evidence
                    or replace(prior, send_outcome=request.send_outcome) != request
                ):
                    raise ValueError("subscription send outcome lacks matching pending request")
                validation_requests[key] = request
            continue
        if record_type == "runtime_terminal":
            if terminal_record is not None:
                raise ValueError("exactly one durable runtime terminal record is required")
            terminal_record = _required_mapping(record, "runtime_terminal")
            continue
        if record_type != "raw_transport_event":
            raise ValueError(f"unsupported durable runtime record type: {record_type}")
        event = KalshiWsRawEvent.from_record(_required_mapping(record, "d2a_event"))
        if event.campaign_id != record_campaign_id:
            raise ValueError("D2A campaign identity contradicts durable runtime record")
        if event.local_row_index != counts["event_count"] + 1:
            raise ValueError("D2A local row indices must be contiguous across the runtime")
        _replay_channel_binding(event, validation_bindings, validation_requests)
        request_key = (event.connection_id, event.channel)
        if (
            request_key not in validation_requests
            and event.native_type in {"error", "rejected"}
        ):
            matching_keys = tuple(
                key
                for key, candidate in validation_requests.items()
                if key[0] == event.connection_id
                and candidate.native_command_id == event.subscription_id
            )
            if len(matching_keys) == 1:
                request_key = matching_keys[0]
        if request_key in validation_requests:
            requests_with_inbound_evidence.add(request_key)
        _validate_event_subscription_state(
            event,
            connection_states,
            require_channel_binding=(
                launch_record.get("subscription_identity_model")
                == CHANNEL_SCOPED_SUBSCRIPTION_IDENTITY_VERSION
            ),
        )
        counts["event_count"] += 1
        counts[f"native:{event.native_type or 'unknown'}"] += 1
        if event.exclusion_reason in {
            ExclusionReason.NATIVE_ENVELOPE_REJECTED,
            ExclusionReason.PRE_ACKNOWLEDGMENT_DATA,
            ExclusionReason.SUBSCRIPTION_BINDING_CONFLICTED,
            ExclusionReason.SUBSCRIPTION_IDENTITY_MISMATCH,
            ExclusionReason.CHANNEL_TYPE_MISMATCH,
        } or event.subscription_binding_observation is (
            SubscriptionBindingObservation.CONFLICTING_ACK
        ) or event.subscription_binding_observation is (
            SubscriptionBindingObservation.CONFLICTING_REJECTION
        ) or (
            event.native_type in {"error", "rejected"}
            and event.subscription_binding_state
            in {SubscriptionBindingState.UNKNOWN, SubscriptionBindingState.REQUEST_MISMATCH}
        ):
            counts["binding_failure_count"] += 1
        last_event_at = event.received_at_utc
        raw_observed_min = min(raw_observed_min or event.received_at_utc, event.received_at_utc)
        raw_observed_max = max(raw_observed_max or event.received_at_utc, event.received_at_utc)
        control_channels = subscription_ack_channels(
            event.original_payload,
            event.native_type or "unknown",
        )
        if event.native_type in {"subscribed", "ack", "ok", "error", "rejected"}:
            if (
                event.subscription_binding_state
                is SubscriptionBindingState.ACKNOWLEDGED
                and event.subscription_binding_observation
                in {
                    SubscriptionBindingObservation.ACKNOWLEDGED,
                    SubscriptionBindingObservation.DUPLICATE_ACK,
                }
            ):
                durable_ack_channels.setdefault(event.connection_id, set()).update(
                    control_channels
                )
        if event.native_type in {"heartbeat", "pong"}:
            last_keepalive_at, maximum_keepalive_age = _observe_runtime_gap(
                previous=last_keepalive_at,
                maximum=maximum_keepalive_age,
                observed_at_utc=event.received_at_utc,
                started_at_utc=launch_started_at,
            )
        selected_orderbook_event = (
            event.admission_status is AdmissionStatus.ADMITTED
            and event.native_market_ticker == selected_market
            and event.native_type in {"orderbook_snapshot", "orderbook_delta"}
        )
        if selected_orderbook_event:
            last_orderbook_at, maximum_orderbook_quiet = _observe_runtime_gap(
                previous=last_orderbook_at,
                maximum=maximum_orderbook_quiet,
                observed_at_utc=event.received_at_utc,
                started_at_utc=launch_started_at,
            )
            if event.native_type == "orderbook_snapshot" and first_snapshot_at is None:
                first_snapshot_at = event.received_at_utc
        recorded_trades = record.get("d2c_public_trades")
        if not isinstance(recorded_trades, list):
            raise ValueError("durable public trade evidence must be a list")
        expected_trades = build_public_trade_stream(
            (event,),
            selected_market_tickers=(selected_market,),
        ).to_records()
        if recorded_trades != expected_trades:
            raise ValueError("durable public trade evidence contradicts D2A")
        counts["trade_count"] += len(expected_trades)
        _accumulate_validation_sequence(sequence, event)
        rebuilt = validation_rebuilder.apply(event)
        expected_rebuild = {
            "disposition": rebuilt.disposition,
            "reason": rebuilt.reason,
            "frame": rebuilt.frame.to_record() if rebuilt.frame is not None else None,
        }
        if record.get("d2b_rebuild") != expected_rebuild:
            raise ValueError("durable D2B evidence contradicts independent rebuild")
        _accumulate_validation_rebuild(
            rebuild,
            event,
            expected_rebuild,
            selected_market,
            counts,
        )
    counts["snapshot_count"] = counts["native:orderbook_snapshot"]
    counts["delta_count"] = counts["native:orderbook_delta"]
    counts["admitted_selected_snapshot_count"] = counts[
        "admitted_selected:orderbook_snapshot"
    ]
    counts["admitted_selected_delta_count"] = counts[
        "admitted_selected:orderbook_delta"
    ]
    for field in ("event_count", "trade_count", "rebuild_frame_count"):
        counts[field] = counts[field]
    native_counts = Counter(
        {
            key.removeprefix("native:"): value
            for key, value in counts.items()
            if key.startswith("native:")
        }
    )
    for key in tuple(counts):
        if key.startswith(("native:", "admitted_selected:")):
            del counts[key]

    if len(durable_campaign_ids) != 1:
        raise ValueError("durable runtime records require one campaign identity")
    durable_campaign_id = next(iter(durable_campaign_ids))
    if launch_record is None or launch_started_at is None or selected_market is None:
        raise ValueError("exactly one durable runtime launch record is required")
    if terminal_record is not None:
        terminal = terminal_record
        terminal_timing = _required_mapping(terminal, "timing")
    elif allow_summary_terminal:
        terminal = {
            "mode": summary["mode"],
            "blocker_code": summary.get("blocker_code"),
        }
        terminal_timing = {
            "configured_duration_seconds": summary["configured_duration_seconds"],
            "started_at_utc": summary["started_at"],
            "ended_at": summary["ended_at"],
            "terminal_reason": summary["terminal_reason"],
            "stop_requested": summary["stop_requested"],
            "threshold_source_commit": summary["threshold_source_commit"],
        }
    else:
        raise ValueError("exactly one durable runtime terminal record is required")
    if terminal.get("mode") != launch_record.get("mode"):
        raise ValueError("runtime terminal mode contradicts durable launch")
    if (
        terminal_timing.get("configured_duration_seconds")
        != launch_record.get("configured_duration_seconds")
        or terminal_timing.get("threshold_source_commit")
        != launch_record.get("threshold_source_commit")
    ):
        raise ValueError("runtime terminal policy contradicts durable launch")
    started = _parse_required_time(terminal_timing.get("started_at_utc"), "started_at_utc")
    ended = _parse_required_time(terminal_timing.get("ended_at"), "ended_at")
    if started != launch_started_at:
        raise ValueError("runtime terminal start contradicts durable launch")
    if ended < started:
        raise ValueError("runtime terminal end precedes start")
    actual = _decimal_seconds(ended - started)
    windows = _validation_connection_windows(connection_events, ended)
    _validate_runtime_interval(
        started,
        ended,
        connection_events=connection_events,
        raw_observed_min=raw_observed_min,
        raw_observed_max=raw_observed_max,
        lifecycle_observed_min=lifecycle_observed_min,
        lifecycle_observed_max=lifecycle_observed_max,
        windows=windows,
    )
    connected = sum(
        (Decimal(str(window["duration_seconds"])) for window in windows),
        Decimal("0"),
    )
    if connected > actual:
        raise ValueError("connection coverage exceeds the runtime interval")
    disconnects = RuntimeEvidenceSession._disconnect_durations(
        windows,
        started_at_utc=started,
        ended_at_utc=ended,
    )
    maximum_disconnect = max(
        (Decimal(value) for value in disconnects),
        default=Decimal("0"),
    )
    if last_keepalive_at is not None:
        maximum_keepalive_age = _max_age(
            maximum_keepalive_age,
            _age_seconds(ended, last_keepalive_at),
        )
    if last_lifecycle_at is not None:
        maximum_lifecycle_age = _max_age(
            maximum_lifecycle_age,
            _age_seconds(ended, last_lifecycle_at),
        )
    if last_orderbook_at is not None:
        maximum_orderbook_quiet = _max_age(
            maximum_orderbook_quiet,
            _age_seconds(ended, last_orderbook_at),
        )
    timing = build_evidence_timing(
        configured_duration_seconds=int(terminal_timing["configured_duration_seconds"]),
        started_at_utc=started,
        checkpoint_at_utc=None,
        ended_at_utc=ended,
        first_snapshot_at=first_snapshot_at,
        last_event_at=last_event_at,
        terminal_reason=str(terminal_timing["terminal_reason"]),
        stop_requested=bool(terminal_timing["stop_requested"]),
        total_disconnect_seconds=max(Decimal("0"), actual - connected),
        threshold_policy_version=V2_THRESHOLD_POLICY.version,
        threshold_source_commit=str(terminal_timing["threshold_source_commit"]),
        threshold_effective_utc=V2_THRESHOLD_POLICY.effective_at_utc,
        transport_keepalive_age_seconds=(
            _age_seconds(ended, last_keepalive_at)
            if last_keepalive_at is not None
            else None
        ),
        lifecycle_observation_age_seconds=(
            _age_seconds(ended, last_lifecycle_at)
            if last_lifecycle_at is not None
            else None
        ),
        orderbook_event_quiet_interval_seconds=(
            _age_seconds(ended, last_orderbook_at)
            if last_orderbook_at is not None
            else None
        ),
        max_transport_keepalive_age_seconds=maximum_keepalive_age,
        max_lifecycle_observation_age_seconds=maximum_lifecycle_age,
        max_orderbook_event_quiet_interval_seconds=maximum_orderbook_quiet,
    )
    opened_ids = {
        str(event["connection_id"])
        for event in connection_events
        if event.get("event_type")
        in {ConnectionEvidenceType.CONNECTION_OPEN, ConnectionEvidenceType.RECONNECT}
    }
    acknowledged_ids = {
        str(event["connection_id"])
        for event in connection_events
        if event.get("event_type") is ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED
        or event.get("event_type") == ConnectionEvidenceType.SUBSCRIPTION_ACKNOWLEDGED
    }
    rejected = any(
        event.get("event_type") == ConnectionEvidenceType.SUBSCRIPTION_REJECTED
        for event in connection_events
    )
    coverage = connected / actual if actual else Decimal("0")
    derived_connection_established = bool(opened_ids)
    durable_acknowledged_ids = {
        connection_id
        for connection_id, channels in durable_ack_channels.items()
        if REQUIRED_PUBLIC_CHANNELS <= channels
    }
    grounded_acknowledged_ids = acknowledged_ids & durable_acknowledged_ids
    derived_subscription_acknowledged = bool(
        opened_ids and opened_ids <= grounded_acknowledged_ids and not rejected
    )
    canonical_terminal = _runtime_terminal_payload(
        timing=timing,
        mode=str(terminal["mode"]),
        blocker_code=(
            str(terminal["blocker_code"])
            if terminal.get("blocker_code") is not None
            else None
        ),
        connection_established=derived_connection_established,
        subscription_acknowledged=derived_subscription_acknowledged,
    )
    if terminal_record is not None and dict(terminal) != canonical_terminal:
        raise ValueError("durable runtime terminal contradicts derived evidence")
    lifecycle = _loaded_lifecycle_status(
        lifecycle_observation_count,
        lifecycle_invalid_observed,
        maximum_lifecycle_age,
    )
    dimensions = EvidenceDimensions(
        artifact_integrity=EvidenceStatus.UNKNOWN,
        transport_connectivity=(
            EvidenceStatus.PASS
            if opened_ids
            and coverage >= V2_THRESHOLD_POLICY.minimum_connection_coverage
            and maximum_disconnect <= V2_THRESHOLD_POLICY.maximum_disconnect_seconds
            else EvidenceStatus.FAIL
        ),
        transport_keepalive=(
            EvidenceStatus.UNKNOWN
            if last_keepalive_at is None
            else EvidenceStatus.PASS
            if (maximum_keepalive_age or 0)
            <= V2_THRESHOLD_POLICY.maximum_transport_keepalive_age_seconds
            else EvidenceStatus.FAIL
        ),
        subscription_status=(
            EvidenceStatus.PASS
            if opened_ids
            and opened_ids <= grounded_acknowledged_ids
            and not rejected
            and counts["binding_failure_count"] == 0
            else EvidenceStatus.FAIL
        ),
        sequence_integrity=_sequence_evidence_status(sequence),
        rebuild_integrity=_rebuild_evidence_status(rebuild),
        market_lifecycle_validity=lifecycle,
        duration_evidence=classify_duration_evidence(timing),
        process_liveness=(
            EvidenceStatus.PASS
            if canonical_terminal["status"] == "d2_runtime_complete"
            else EvidenceStatus.FAIL
        ),
        supervisor_liveness=EvidenceStatus.UNKNOWN,
        backup_integrity=EvidenceStatus.UNKNOWN,
        replay_qualification=EvidenceStatus.UNKNOWN,
    ).to_record()
    freshness = evaluate_evidence_freshness(
        evaluated_at_utc=ended,
        transport_keepalive_observed_at_utc=last_keepalive_at,
        transport_keepalive_source=(
            "RECORDED_WS_HEARTBEAT_OR_PONG" if last_keepalive_at is not None else None
        ),
        lifecycle_observed_at_utc=last_lifecycle_at,
        orderbook_event_at_utc=last_orderbook_at,
    )
    durable_fields: dict[str, object] = {
        **timing.to_record(),
        **{
            field: launch_record[field]
            for field in (
                "runtime_schema_version",
                "raw_event_schema_version",
                "evidence_schema_version",
                "threshold_policy_version",
                "threshold_source_commit",
                "threshold_policy",
                "public_code_commit",
                "branch",
                "remote",
                "dirty_state",
                "configured_duration_seconds",
                "selected_market_metadata",
                "selected_market_selection",
                "lifecycle_mode_and_source",
                "pricing_mode_and_source",
                "use_yes_price",
            )
        },
        "subscription_identity_model": launch_record.get(
            "subscription_identity_model"
        ),
        "campaign_id": durable_campaign_id,
        "market": selected_market,
        "market_ticker": selected_market,
        "market_tickers": [selected_market],
        "market_count": 1,
        "market_status": _selected_status(
            _required_mapping(launch_record, "selected_market_metadata")
        ),
        "status_at_launch": _selected_status(
            _required_mapping(launch_record, "selected_market_metadata")
        ),
        "close_time": _required_mapping(
            launch_record, "selected_market_metadata"
        ).get("close_time"),
        "sequence_summaries": _sequence_summary_records(sequence),
        "rebuild_summaries": _rebuild_summary_records(rebuild),
        "connection_windows": windows,
        "disconnect_durations": disconnects,
        "disconnect_count": len(disconnects),
        "reconnect_count": sum(
            event.get("event_type") == ConnectionEvidenceType.RECONNECT
            for event in connection_events
        ),
        "maximum_disconnect_seconds": _decimal_text(maximum_disconnect),
        "connection_coverage": _decimal_text(coverage),
        "freshness_dimensions": freshness.to_record(),
        "raw_event_count": counts["event_count"],
        "public_trade_count": counts["trade_count"],
        "lifecycle_observation_count": lifecycle_observation_count,
        "connection_event_count": len(connection_events),
        "rebuild_excluded_count": sum(
            int(item["excluded_row_count"]) for item in rebuild.values()
        ),
        "gap_count": sum(
            item["sequence_states"].get(SequenceState.SEQUENCE_GAP_DETECTED, 0)
            for item in sequence.values()
        ),
        "heartbeat_count": native_counts["heartbeat"],
        "status_update_count": native_counts["market_status"],
        "first_snapshot_at": (
            timing.first_snapshot_at.isoformat() if timing.first_snapshot_at else None
        ),
        "last_event_time": timing.last_event_at.isoformat() if timing.last_event_at else None,
        "market_lifecycle_status": (
            latest_lifecycle_record["lifecycle_status"]
            if latest_lifecycle_record is not None
            else "UNKNOWN"
        ),
        "websocket_message_freshness_status": _orderbook_freshness_status(
            freshness.orderbook_event_quiet_interval_seconds
        ),
        "exchange_heartbeat_status": freshness.transport_keepalive_status,
        "connection_established": bool(opened_ids),
        "subscription_acknowledged": derived_subscription_acknowledged,
        "binding_failure_observed": counts["binding_failure_count"] > 0,
        "mode": canonical_terminal["mode"],
        "status": canonical_terminal["status"],
        "blocker_code": canonical_terminal["blocker_code"],
        "duration_seconds": timing.configured_duration_seconds,
        "started_at": timing.started_at_utc.isoformat(),
        "ended_at_utc": timing.ended_at.isoformat() if timing.ended_at else None,
        "source_type": _source_type(native_counts),
    }
    return dimensions, counts, durable_fields, canonical_terminal


def _required_mapping(record: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = record.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"durable runtime record is missing {field}")
    return value


def _runtime_terminal_payload(
    *,
    timing: Any,
    mode: str,
    blocker_code: str | None,
    connection_established: bool,
    subscription_acknowledged: bool,
) -> dict[str, object]:
    status = (
        "d2_runtime_crash_recovered"
        if timing.terminal_reason == "crash_recovered"
        else "d2_runtime_complete"
        if blocker_code is None
        else "d2_runtime_blocked"
    )
    return {
        "timing": timing.to_record(),
        "mode": mode,
        "status": status,
        "blocker_code": blocker_code,
        "connection_established": connection_established,
        "subscription_acknowledged": subscription_acknowledged,
    }


def _accumulate_validation_sequence(
    summaries: dict[tuple[str, str], dict[str, object]],
    event: KalshiWsRawEvent,
) -> None:
    summary = summaries.setdefault(
        (event.connection_id, event.segment_id),
        {
            "connection_id": event.connection_id,
            "segment_id": event.segment_id,
            "segment_boundary_reasons": set(),
            "native_sid_values": set(),
            "native_seq_present_count": 0,
            "sequence_states": Counter(),
            "admitted_rows": 0,
            "excluded_rows": 0,
            "acknowledgement_count": 0,
            "rejection_count": 0,
            "channel_bindings": {},
        },
    )
    summary["segment_boundary_reasons"].add(event.segment_boundary_reason)
    if event.native_sid is not None:
        summary["native_sid_values"].add(str(event.native_sid))
    if event.native_seq is not None:
        summary["native_seq_present_count"] += 1
    summary["sequence_states"][event.sequence_state] += 1
    if event.admission_status is AdmissionStatus.ADMITTED:
        summary["admitted_rows"] += 1
    elif event.admission_status is AdmissionStatus.EXCLUDED:
        summary["excluded_rows"] += 1
    if event.native_type in {"subscribed", "ack", "ok"}:
        summary["acknowledgement_count"] += 1
    if event.native_type in {"error", "rejected"}:
        summary["rejection_count"] += 1
    _observe_channel_binding(summary, event)


def _accumulate_validation_rebuild(
    summaries: dict[tuple[str, str, str], dict[str, object]],
    event: KalshiWsRawEvent,
    result: Mapping[str, object],
    selected_market: str,
    counts: Counter[str],
) -> None:
    key = (
        event.native_market_ticker or selected_market,
        event.connection_id,
        event.segment_id,
    )
    summary = summaries.setdefault(
        key,
        {
            "market_ticker": key[0],
            "connection_id": key[1],
            "segment_id": key[2],
            "frame_count": 0,
            "orderbook_row_count": 0,
            "excluded_row_count": 0,
            "invalidation_reasons": Counter(),
            "pricing_modes": set(),
            "pricing_mode_sources": set(),
            "frame_hash_chain": None,
            "latest_frame_hash": None,
            "terminal_state_hash": None,
            "snapshot_first_admitted": False,
            "native_state_valid": None,
        },
    )
    selected_admitted = (
        event.admission_status is AdmissionStatus.ADMITTED
        and event.native_market_ticker == selected_market
        and event.native_type in {"orderbook_snapshot", "orderbook_delta"}
    )
    if selected_admitted:
        counts[f"admitted_selected:{event.native_type}"] += 1
    if event.native_type in {"orderbook_snapshot", "orderbook_delta"}:
        summary["orderbook_row_count"] += 1
    frame = result.get("frame")
    reason = result.get("reason")
    if reason is not None:
        summary["invalidation_reasons"][str(reason)] += 1
        summary["native_state_valid"] = False
    if isinstance(frame, Mapping):
        summary["frame_count"] += 1
        counts["rebuild_frame_count"] += 1
        summary["native_state_valid"] = frame.get("segment_validity") == SegmentValidity.VALID
        summary["frame_hash_chain"] = _advance_frame_hash_chain(
            summary["frame_hash_chain"], str(frame["frame_hash"])
        )
        summary["latest_frame_hash"] = frame["frame_hash"]
        summary["terminal_state_hash"] = frame["terminal_state_hash"]
        summary["pricing_modes"].add(frame["pricing_mode"])
        summary["pricing_mode_sources"].add(frame["pricing_mode_source"])
        if event.native_type == "orderbook_snapshot":
            summary["snapshot_first_admitted"] = True
    elif event.native_type in {"orderbook_snapshot", "orderbook_delta"}:
        summary["excluded_row_count"] += 1


def _sequence_summary_records(
    summaries: Mapping[tuple[str, str], Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            **summary,
            "segment_boundary_reasons": sorted(summary["segment_boundary_reasons"]),
            "native_sid_values": sorted(summary["native_sid_values"]),
            "channel_bindings": {
                channel: {
                    field_name: sorted(values)
                    for field_name, values in sorted(binding.items())
                }
                for channel, binding in sorted(summary["channel_bindings"].items())
            },
            "sequence_states": dict(sorted(summary["sequence_states"].items())),
            "continuity_semantics_supported": (
                SequenceState.SEQUENCE_CONTIGUITY_VERIFIED
                in summary["sequence_states"]
            ),
            "aggregate_result": _sequence_result(summary["sequence_states"]),
        }
        for summary in summaries.values()
    ]


def _observe_channel_binding(
    summary: dict[str, object],
    event: KalshiWsRawEvent,
) -> None:
    if (
        event.subscription_binding_id is None
        and event.subscription_generation is None
        and event.subscription_command_id is None
    ):
        return
    bindings = summary["channel_bindings"]
    binding = bindings.setdefault(
        event.channel,
        {
            "command_ids": set(),
            "generations": set(),
            "binding_ids": set(),
            "native_sids": set(),
            "states": set(),
        },
    )
    if event.subscription_command_id is not None:
        binding["command_ids"].add(str(event.subscription_command_id))
    if event.subscription_generation is not None:
        binding["generations"].add(str(event.subscription_generation))
    if event.subscription_binding_id is not None:
        binding["binding_ids"].add(event.subscription_binding_id)
    if event.native_sid is not None:
        binding["native_sids"].add(str(event.native_sid))
    binding["states"].add(str(event.subscription_binding_state))


def _rebuild_summary_records(
    summaries: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            **summary,
            "invalidation_reasons": dict(
                sorted(summary["invalidation_reasons"].items())
            ),
            "pricing_modes": sorted(summary["pricing_modes"]),
            "pricing_mode_sources": sorted(summary["pricing_mode_sources"]),
        }
        for summary in summaries.values()
    ]


def _validation_connection_windows(
    events: list[Mapping[str, object]],
    ended_at_utc: datetime,
) -> list[dict[str, object]]:
    windows: dict[str, dict[str, object]] = {}
    for event in events:
        connection_id = str(event["connection_id"])
        window = windows.setdefault(
            connection_id,
            {
                "connection_id": connection_id,
                "segment_ids": [],
                "opened_at_utc": None,
                "closed_at_utc": None,
                "error_count": 0,
                "reasons": [],
            },
        )
        segment_id = str(event["segment_id"])
        if segment_id not in window["segment_ids"]:
            window["segment_ids"].append(segment_id)
        window["reasons"].append(str(event["reason"]))
        event_type = str(event["event_type"])
        observed = str(event["observed_at_utc"])
        if event_type in {
            ConnectionEvidenceType.CONNECTION_OPEN,
            ConnectionEvidenceType.RECONNECT,
        } and window["opened_at_utc"] is None:
            window["opened_at_utc"] = observed
        if event_type == ConnectionEvidenceType.CONNECTION_CLOSE:
            window["closed_at_utc"] = observed
        if event_type == ConnectionEvidenceType.CONNECTION_ERROR:
            window["error_count"] += 1
    records = []
    for window in windows.values():
        opened = _parse_time(window["opened_at_utc"])
        closed = _parse_time(window["closed_at_utc"]) or ended_at_utc
        duration = (
            _decimal_seconds(closed - opened)
            if opened is not None and closed >= opened
            else Decimal("0")
        )
        records.append(
            {
                **window,
                "closed_at_utc": closed.isoformat() if opened is not None else None,
                "duration_seconds": _decimal_text(duration),
            }
        )
    return records


def _validate_runtime_interval(
    started_at_utc: datetime,
    ended_at_utc: datetime,
    *,
    connection_events: list[Mapping[str, object]],
    raw_observed_min: datetime | None,
    raw_observed_max: datetime | None,
    lifecycle_observed_min: datetime | None,
    lifecycle_observed_max: datetime | None,
    windows: list[Mapping[str, object]],
) -> None:
    observed_times = [
        _parse_required_time(event.get("observed_at_utc"), "connection observed_at_utc")
        for event in connection_events
    ]
    observed_times.extend(
        value for value in (raw_observed_min, raw_observed_max) if value is not None
    )
    observed_times.extend(
        value
        for value in (lifecycle_observed_min, lifecycle_observed_max)
        if value is not None
    )
    if any(value < started_at_utc or value > ended_at_utc for value in observed_times):
        raise ValueError("runtime evidence falls outside terminal timing boundaries")
    previous_closed: datetime | None = None
    for window in sorted(windows, key=lambda item: str(item["opened_at_utc"])):
        opened = _parse_required_time(window.get("opened_at_utc"), "connection opened_at_utc")
        closed = _parse_required_time(window.get("closed_at_utc"), "connection closed_at_utc")
        if (
            opened < started_at_utc
            or closed > ended_at_utc
            or closed < opened
            or (previous_closed is not None and opened < previous_closed)
        ):
            raise ValueError("connection windows contradict terminal timing boundaries")
        previous_closed = closed


def _loaded_lifecycle_status(
    observation_count: int,
    invalid_observed: bool,
    maximum_age: int | None,
) -> EvidenceStatus:
    if not observation_count:
        return EvidenceStatus.UNKNOWN
    if invalid_observed:
        return EvidenceStatus.FAIL
    return (
        EvidenceStatus.PASS
        if (maximum_age or 0) <= V2_THRESHOLD_POLICY.maximum_lifecycle_age_seconds
        else EvidenceStatus.FAIL
    )


def _parse_required_time(value: object, field: str) -> datetime:
    parsed = _parse_time(value)
    if parsed is None:
        raise ValueError(f"{field} is missing or invalid")
    return parsed


def _reconciled_finalized_segment_record(
    root: Path,
    segment_id: str,
    data_path: Path,
    checkpoint_path: Path,
    summary_path: Path,
    segment_summary: Mapping[str, object],
) -> dict[str, object]:
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    verified = verify_segment_chain(data_path, segment_id=segment_id)
    with data_path.open("rb") as handle:
        closed_file_sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
    if (
        segment_summary.get("schema_version") != EVIDENCE_SUMMARY_SCHEMA_VERSION
        or segment_summary.get("segment_id") != segment_id
        or segment_summary.get("segment_closed") is not True
        or checkpoint.get("schema_version") != EVIDENCE_CHECKPOINT_SCHEMA_VERSION
        or checkpoint.get("segment_id") != segment_id
        or checkpoint.get("last_committed_local_row_index") != verified.record_count
        or checkpoint.get("byte_offset") != verified.byte_offset
        or checkpoint.get("chain_hash") != verified.terminal_chain_hash
        or segment_summary.get("last_committed_local_row_index") != verified.record_count
        or segment_summary.get("byte_offset") != verified.byte_offset
        or segment_summary.get("terminal_chain_hash") != verified.terminal_chain_hash
        or segment_summary.get("closed_file_sha256") != closed_file_sha256
    ):
        raise ValueError("finalized segment artifacts contradict before manifest sync")
    return {
        **segment_summary,
        "data_path": str(data_path.relative_to(root)),
        "checkpoint_path": str(checkpoint_path.relative_to(root)),
        "summary_path": str(summary_path.relative_to(root)),
        "recovery_status": "FINALIZED_BEFORE_MANIFEST_SYNC",
        "partial_tail_bytes_removed": 0,
        "snapshot_required_after_recovery": True,
        "inherited_book_state": False,
    }


def _next_rotated_segment_id(segment_id: str) -> str:
    match = re.fullmatch(r"(.+\.evidence\.)(\d+)", segment_id)
    if match is None:
        raise ValueError("rotated runtime segment id is not incrementable")
    number = match.group(2)
    return f"{match.group(1)}{int(number) + 1:0{len(number)}d}"


def _write_recovery_segment_start(
    root: Path,
    *,
    segment_id: str,
    next_segment_id: str,
    recovered_at_utc: datetime,
) -> Path:
    path = root / f"{next_segment_id}.start.json"
    payload = {
        "schema_version": EVIDENCE_SEGMENT_START_SCHEMA_VERSION,
        "segment_id": next_segment_id,
        "previous_segment_id": segment_id,
        "segment_created": True,
        "connection_reset_required": True,
        "snapshot_required": True,
        "inherited_book_state": False,
        "created_at_utc": recovered_at_utc.isoformat(),
    }
    if path.exists() or path.is_symlink():
        if path.is_symlink():
            raise ValueError("runtime recovery metadata must not be a symlink")
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("runtime recovery metadata is unreadable") from exc
        if not isinstance(existing, Mapping) or set(existing) != set(payload):
            raise ValueError("runtime recovery metadata already exists")
        existing_created_at = _parse_time(existing.get("created_at_utc"))
        if existing_created_at is not None:
            _require_aware(existing_created_at, "existing recovery segment-start created_at_utc")
        if (
            any(
                existing.get(field) != value
                for field, value in payload.items()
                if field != "created_at_utc"
            )
            or existing_created_at != recovered_at_utc
        ):
            raise ValueError("runtime recovery metadata already exists")
        return path
    _atomic_write_json(
        path,
        payload,
    )
    return path


def _preflight_recovery_artifact_paths(
    root: Path,
    segments: list[object],
) -> None:
    for name in (
        "campaign_summary.json",
        "campaign_manifest.json",
        "run_metadata.json",
        "campaign_validation.json",
        "runtime_recovery.json",
    ):
        _runtime_metadata_path(root, name)
    evidence_root = root / "evidence_segments"
    if evidence_root.is_symlink():
        raise ValueError("evidence segment root must not be a symlink")
    if evidence_root.exists():
        for path in evidence_root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"recovery artifact must not be a symlink: {path.name}")
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise ValueError("runtime recovery segment metadata must be an object")
        for field in (
            "data_path",
            "checkpoint_path",
            "summary_path",
            "next_segment_metadata_path",
        ):
            value = segment.get(field)
            if value is not None:
                _contained_artifact_path(root, value, reject_symlinks=True)


def recover_d2_runtime_artifacts(
    input_dir: Path,
    *,
    recovered_at_utc: datetime,
) -> dict[str, object]:
    """Close one crashed open D2 segment; never auto-resume the campaign."""

    _require_aware(recovered_at_utc, "recovered_at_utc")
    root = Path(input_dir).resolve()
    summary_path = _runtime_metadata_path(root, "campaign_summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, Mapping):
        raise ValueError("runtime recovery campaign summary must be an object")
    if summary.get("runtime_schema_version") != D2_RUNTIME_SCHEMA_VERSION:
        raise ValueError("runtime recovery requires the D2 runtime schema")
    segment_summaries = summary.get("segment_summaries", [])
    if not isinstance(segment_summaries, list):
        raise ValueError("runtime recovery segment summaries must be a list")
    _preflight_recovery_artifact_paths(root, segment_summaries)
    open_segments = [
        segment
        for segment in segment_summaries
        if isinstance(segment, Mapping) and segment.get("segment_closed") is False
    ]
    recovery_path = _runtime_metadata_path(root, "runtime_recovery.json")
    if recovery_path.exists():
        loaded_recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_recovery, Mapping):
            raise ValueError("runtime recovery metadata must be an object")
        if not open_segments:
            try:
                dimensions, durable_counts, durable_fields, _ = _derive_runtime_validation(
                    summary,
                    _iter_summary_runtime_records(root, segment_summaries),
                )
                summary.update(durable_counts)
                summary.update(durable_fields)
                dimensions["artifact_integrity"] = EvidenceStatus.PASS
                summary["independent_evidence_classifications"] = dimensions
                summary["overall_evidence_classification"] = classify_evidence(
                    EvidenceDimensions(**dimensions)
                ).overall_classification
                _sync_runtime_summary(root, summary)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "existing runtime recovery artifacts could not be reconciled"
                ) from exc
            validation = validate_d2_runtime_artifacts(root)
            recovery = dict(loaded_recovery)
            recovery["validation_status"] = validation["status"]
            summary["validation_status"] = validation["status"]
            summary["evidence_classification"] = validation["overall_evidence_classification"]
            _sync_runtime_summary(root, summary)
            _atomic_write_json(recovery_path, recovery)
            if validation["status"] != "pass":
                raise ValueError("existing runtime recovery artifacts failed validation")
            return recovery
        recovered_at_utc = _parse_required_time(
            loaded_recovery.get("recovered_at_utc"),
            "runtime recovery recovered_at_utc",
        )
        _require_aware(recovered_at_utc, "runtime recovery recovered_at_utc")
    if len(open_segments) != 1:
        raise ValueError("runtime recovery requires exactly one open segment")
    segment = open_segments[0]
    while True:
        segment_id = str(segment["segment_id"])
        data_path = _contained_artifact_path(
            root,
            segment["data_path"],
            reject_symlinks=True,
        )
        checkpoint_path = _contained_artifact_path(
            root,
            segment["checkpoint_path"],
            reject_symlinks=True,
        )
        closed_summary_path = _contained_artifact_path(
            root,
            data_path.with_name(f"{segment_id}.summary.json").relative_to(root),
            reject_symlinks=True,
        )
        if not closed_summary_path.is_file():
            break
        closed_summary = json.loads(closed_summary_path.read_text(encoding="utf-8"))
        finalized_record = _reconciled_finalized_segment_record(
            root,
            segment_id,
            data_path,
            checkpoint_path,
            closed_summary_path,
            closed_summary,
        )
        summary["segment_summaries"] = [
            finalized_record if item is segment else item
            for item in summary["segment_summaries"]
        ]
        if closed_summary.get("terminal_reason") != "rotation":
            segment = finalized_record
            break
        next_segment_id = _next_rotated_segment_id(segment_id)
        next_data_path = _contained_artifact_path(
            root,
            data_path.with_name(f"{next_segment_id}.events.jsonl").relative_to(root),
        )
        next_checkpoint_path = _contained_artifact_path(
            root,
            data_path.with_name(f"{next_segment_id}.checkpoint.json").relative_to(root),
        )
        next_summary_path = _contained_artifact_path(
            root,
            data_path.with_name(f"{next_segment_id}.summary.json").relative_to(root),
        )
        successor_data_exists = next_data_path.exists() or next_data_path.is_symlink()
        successor_checkpoint_exists = (
            next_checkpoint_path.exists() or next_checkpoint_path.is_symlink()
        )
        successor_summary_exists = next_summary_path.exists() or next_summary_path.is_symlink()
        successor_exists = (
            successor_data_exists
            or successor_checkpoint_exists
            or successor_summary_exists
        )
        if successor_exists and not (
            successor_data_exists and successor_checkpoint_exists
        ):
            raise ValueError("finalized rotation has a partial successor segment")
        if not successor_data_exists:
            segment = finalized_record
            break
        segment = {
            "segment_id": next_segment_id,
            "segment_closed": False,
            "data_path": str(next_data_path.relative_to(root)),
            "checkpoint_path": str(next_checkpoint_path.relative_to(root)),
        }
        summary["segment_summaries"].append(segment)

    segment_id = str(segment["segment_id"])
    next_segment_id = f"{summary['campaign_id']}.recovery.next"
    data_path = _contained_artifact_path(
        root,
        segment["data_path"],
        reject_symlinks=True,
    )
    checkpoint_path = _contained_artifact_path(
        root,
        segment["checkpoint_path"],
        reject_symlinks=True,
    )
    closed_summary_path = _contained_artifact_path(
        root,
        data_path.with_name(f"{segment_id}.summary.json").relative_to(root),
        reject_symlinks=True,
    )
    pre_recovery_file_size = data_path.stat().st_size
    already_finalized = closed_summary_path.is_file()
    if already_finalized:
        closed_summary = json.loads(closed_summary_path.read_text(encoding="utf-8"))
        recovered_at_utc = _parse_required_time(
            closed_summary.get("closed_at_utc"),
            "finalized segment closed_at_utc",
        )
        _require_aware(recovered_at_utc, "finalized segment closed_at_utc")
        next_segment_metadata_path = _write_recovery_segment_start(
            data_path.parent,
            segment_id=segment_id,
            next_segment_id=next_segment_id,
            recovered_at_utc=recovered_at_utc,
        )
        recovered = RecoveryResult(
            segment_id=segment_id,
            last_committed_local_row_index=int(
                closed_summary["last_committed_local_row_index"]
            ),
            terminal_chain_hash=str(closed_summary["terminal_chain_hash"]),
            closed_file_sha256=str(closed_summary["closed_file_sha256"]),
            partial_tail_bytes_removed=0,
            next_segment_id=next_segment_id,
            next_segment_metadata_path=str(next_segment_metadata_path),
        )
    else:
        recovered = recover_unterminated_segment(
            data_path=data_path,
            checkpoint_path=checkpoint_path,
            summary_path=closed_summary_path,
            segment_id=segment_id,
            next_segment_id=next_segment_id,
            now_utc=lambda: recovered_at_utc,
        )
    post_recovery_file_size = data_path.stat().st_size
    recovery_start_absolute = Path(recovered.next_segment_metadata_path).resolve()
    recovery_start_path = _contained_artifact_path(
        root,
        recovery_start_absolute.relative_to(root),
        reject_symlinks=True,
    )
    recovery_start = json.loads(recovery_start_path.read_text(encoding="utf-8"))
    recovered_at_utc = _parse_required_time(
        recovery_start.get("created_at_utc"),
        "recovery segment-start created_at_utc",
    )
    closed_summary = json.loads(closed_summary_path.read_text(encoding="utf-8"))
    segment_record = {
        **closed_summary,
        "data_path": str(data_path.relative_to(root)),
        "checkpoint_path": str(checkpoint_path.relative_to(root)),
        "summary_path": str(closed_summary_path.relative_to(root)),
        "recovery_status": (
            "FINALIZED_BEFORE_MANIFEST_SYNC" if already_finalized else "CRASH_RECOVERED"
        ),
        "partial_tail_bytes_removed": recovered.partial_tail_bytes_removed,
        "snapshot_required_after_recovery": recovered.snapshot_required,
        "inherited_book_state": recovered.inherited_book_state,
        "next_segment_metadata_path": str(
            Path(recovered.next_segment_metadata_path).relative_to(root)
        ),
    }
    summary["segment_summaries"] = [
        segment_record if item is segment else item
        for item in summary["segment_summaries"]
    ]
    summary["status"] = "d2_runtime_crash_recovered"
    summary["threshold_policy"] = V2_THRESHOLD_POLICY.to_record()
    started_at = _parse_required_time(summary.get("started_at"), "started_at")
    actual_elapsed = _decimal_seconds(recovered_at_utc - started_at)
    recovered_windows = []
    for window in summary.get("connection_windows", []):
        if not isinstance(window, Mapping):
            continue
        opened = _parse_time(window.get("opened_at_utc"))
        closed = _parse_time(window.get("closed_at_utc")) or recovered_at_utc
        duration = (
            _decimal_seconds(closed - opened)
            if opened is not None and closed >= opened
            else Decimal("0")
        )
        recovered_windows.append(
            {
                **window,
                "closed_at_utc": closed.isoformat() if opened is not None else None,
                "duration_seconds": _decimal_text(duration),
            }
        )
    connected_elapsed = min(
        actual_elapsed,
        sum(
            (Decimal(str(window["duration_seconds"])) for window in recovered_windows),
            Decimal("0"),
        ),
    )
    summary["connection_windows"] = recovered_windows
    summary["disconnect_durations"] = RuntimeEvidenceSession._disconnect_durations(
        recovered_windows,
        started_at_utc=started_at,
        ended_at_utc=recovered_at_utc,
    )
    summary["actual_elapsed_seconds"] = _decimal_text(actual_elapsed)
    summary["connected_elapsed_seconds"] = _decimal_text(connected_elapsed)
    summary["connection_coverage"] = _decimal_text(
        connected_elapsed / actual_elapsed if actual_elapsed else Decimal("0")
    )
    summary["ended_at"] = recovered_at_utc.isoformat()
    summary["ended_at_utc"] = recovered_at_utc.isoformat()
    summary["terminal_reason"] = "crash_recovered"
    summary["stop_requested"] = False
    summary["replay_qualified"] = False
    summary["campaign_process_liveness_status"] = "EXITED"
    summary["artifact_integrity_summary"] = {
        "integrity_scope": "CLOSED_FILE",
        "recovery_status": "CRASH_RECOVERED",
        "partial_tail_bytes_removed": recovered.partial_tail_bytes_removed,
        "snapshot_required": recovered.snapshot_required,
        "inherited_book_state": recovered.inherited_book_state,
    }
    recovery = {
        "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "campaign_id": summary["campaign_id"],
        "segment_id": segment_id,
        "terminal_reason": recovered.terminal_reason,
        "last_committed_local_row_index": recovered.last_committed_local_row_index,
        "terminal_chain_hash": recovered.terminal_chain_hash,
        "closed_file_sha256": recovered.closed_file_sha256,
        "partial_tail_bytes_removed": recovered.partial_tail_bytes_removed,
        "pre_recovery_file_size": pre_recovery_file_size,
        "post_recovery_file_size": post_recovery_file_size,
        "next_segment_id": recovered.next_segment_id,
        "next_segment_metadata_path": segment_record["next_segment_metadata_path"],
        "snapshot_required": recovered.snapshot_required,
        "inherited_book_state": recovered.inherited_book_state,
        "automatic_restart": False,
        "replay_qualified": False,
        "recovered_at_utc": recovered_at_utc.isoformat(),
        "validation_status": None,
    }
    _atomic_write_json(_runtime_metadata_path(root, "runtime_recovery.json"), recovery)
    terminal_count = sum(
        record.get("record_type") == "runtime_terminal"
        for record in _iter_summary_runtime_records(root, summary["segment_summaries"])
    )
    if terminal_count == 0:
        _, _, initial_fields, recovery_terminal = _derive_runtime_validation(
            summary,
            _iter_summary_runtime_records(root, summary["segment_summaries"]),
            allow_summary_terminal=True,
        )
        summary.update(initial_fields)
        terminal_writer = EvidenceSegmentWriter(
            data_path.parent,
            segment_id=f"{summary['campaign_id']}.recovery.terminal",
            checkpoint_every_records=1,
            now_utc=lambda: recovered_at_utc,
        )
        terminal_writer.append(
            {
                "schema_version": D2_RUNTIME_RECORD_SCHEMA_VERSION,
                "record_type": "runtime_terminal",
                "campaign_id": summary["campaign_id"],
                "local_row_index": 1,
                "observed_at_utc": recovered_at_utc.isoformat(),
                "runtime_terminal": recovery_terminal,
            }
        )
        terminal_summary = terminal_writer.close(terminal_reason="crash_recovery_terminal")
        summary["segment_summaries"].append(
            {
                **terminal_summary,
                "data_path": str(terminal_writer.data_path.relative_to(root)),
                "checkpoint_path": str(terminal_writer.checkpoint_path.relative_to(root)),
                "summary_path": str(terminal_writer.summary_path.relative_to(root)),
                "append_chain_update_count": terminal_writer.append_chain_update_count,
                "full_file_hash_count": terminal_writer.full_file_hash_count,
                "recovery_status": "RECOVERY_TERMINAL_EVIDENCE",
                "partial_tail_bytes_removed": 0,
                "snapshot_required_after_recovery": True,
            }
        )
    elif terminal_count != 1:
        raise ValueError("recovery requires at most one durable runtime terminal")
    _, durable_counts, durable_fields, _ = _derive_runtime_validation(
        summary,
        _iter_summary_runtime_records(root, summary["segment_summaries"]),
    )
    summary.update(durable_counts)
    summary.update(durable_fields)
    _sync_runtime_summary(root, summary)
    first_validation = validate_d2_runtime_artifacts(root)
    summary["independent_evidence_classifications"] = {
        field: first_validation[field] for field in EvidenceDimensions.__dataclass_fields__
    }
    summary["independent_evidence_classifications"]["artifact_integrity"] = (
        EvidenceStatus.PASS
    )
    summary["overall_evidence_classification"] = classify_evidence(
        EvidenceDimensions(**summary["independent_evidence_classifications"])
    ).overall_classification
    _sync_runtime_summary(root, summary)
    validation = validate_d2_runtime_artifacts(root)
    summary["validation_status"] = validation["status"]
    summary["evidence_classification"] = validation["overall_evidence_classification"]
    recovery["validation_status"] = validation["status"]
    _sync_runtime_summary(root, summary)
    _atomic_write_json(_runtime_metadata_path(root, "runtime_recovery.json"), recovery)
    return recovery


def _sync_runtime_summary(root: Path, summary: Mapping[str, object]) -> None:
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        _atomic_write_json(_runtime_metadata_path(root, name), summary)


def _sequence_result(states: Counter[SequenceState]) -> str:
    if any(state in states for state in _BAD_SEQUENCE_STATES):
        return "SEQUENCE_INTEGRITY_FAIL"
    if SequenceState.SEQUENCE_CONTIGUITY_VERIFIED in states:
        return "SEQUENCE_CONTIGUITY_VERIFIED"
    return "SEQUENCE_INTEGRITY_UNKNOWN"


def _sequence_evidence_status(
    summaries: Mapping[tuple[str, str], Mapping[str, object]],
) -> EvidenceStatus:
    if not summaries:
        return EvidenceStatus.UNKNOWN
    counters = [summary["sequence_states"] for summary in summaries.values()]
    if any(any(state in counter for state in _BAD_SEQUENCE_STATES) for counter in counters):
        return EvidenceStatus.FAIL
    if all(SequenceState.SEQUENCE_CONTIGUITY_VERIFIED in counter for counter in counters):
        return EvidenceStatus.PASS
    return EvidenceStatus.UNKNOWN


def _rebuild_evidence_status(
    summaries: Mapping[tuple[str, str, str], Mapping[str, object]],
) -> EvidenceStatus:
    if any(
        any(str(reason) != "D2A_ROW_EXCLUDED" for reason in summary["invalidation_reasons"])
        for summary in summaries.values()
    ):
        return EvidenceStatus.FAIL
    orderbook = [
        summary for summary in summaries.values() if summary["orderbook_row_count"]
    ]
    if not orderbook:
        return EvidenceStatus.UNKNOWN
    if any(
        summary["frame_count"]
        and (
            not summary["snapshot_first_admitted"]
            or summary["native_state_valid"] is not True
            or summary["invalidation_reasons"]
        )
        for summary in orderbook
    ):
        return EvidenceStatus.FAIL
    if any(
        not summary["frame_count"]
        or not summary["snapshot_first_admitted"]
        or summary["native_state_valid"] is not True
        for summary in orderbook
    ):
        return EvidenceStatus.UNKNOWN
    return EvidenceStatus.PASS


def _lifecycle_evidence_status(
    observation_count: int,
    invalid_observed: bool,
    maximum_age: int | None,
    threshold: int,
) -> EvidenceStatus:
    if not observation_count:
        return EvidenceStatus.UNKNOWN
    if invalid_observed:
        return EvidenceStatus.FAIL
    return EvidenceStatus.PASS if (maximum_age or 0) <= threshold else EvidenceStatus.FAIL


def _source_type(counts: Counter[str]) -> str:
    if counts["orderbook_delta"]:
        return "WEBSOCKET_DELTA"
    if counts["orderbook_snapshot"]:
        return "WEBSOCKET_SNAPSHOT"
    if counts["trade"]:
        return "WEBSOCKET_PUBLIC_TRADE"
    return "WEBSOCKET_NO_ORDERBOOK"


def _orderbook_freshness_status(age_seconds: int | None) -> str:
    if age_seconds is None:
        return "UNKNOWN_NOT_OBSERVED"
    if age_seconds > V2_THRESHOLD_POLICY.orderbook_quiet_warning_seconds:
        return "QUIET_WARNING"
    return "FRESH"


def _advance_frame_hash_chain(previous: object, frame_hash: str) -> str:
    prefix = bytes.fromhex(str(previous)) if previous is not None else b""
    return hashlib.sha256(prefix + bytes.fromhex(frame_hash)).hexdigest()


def _selected_status(metadata: Mapping[str, object]) -> object:
    return metadata.get("status") or metadata.get("raw_status")


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    validate_no_secret_payload(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        if descriptor != -1:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def _decimal_seconds(value: Any) -> Decimal:
    return Decimal(value.days * 86_400 + value.seconds) + Decimal(value.microseconds) / Decimal(
        "1000000"
    )


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _age_seconds(later: datetime, earlier: datetime) -> int:
    return max(0, ceil((later - earlier).total_seconds()))


def _max_age(current: int | None, candidate: int) -> int:
    return candidate if current is None else max(current, candidate)


def _parse_time(value: object) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) and value else None


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
