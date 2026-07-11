"""D2A-D2D runtime evidence assembly for Kalshi Demo read-only WebSockets."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from pathlib import Path
from typing import Any

from edmn_trader.adapters.kalshi.client import KalshiDemoMarketDataClient
from edmn_trader.adapters.kalshi.public_evidence import (
    ConnectionEvidenceEvent,
    ConnectionEvidenceType,
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
    SegmentValidity,
)
from edmn_trader.adapters.kalshi.ws_events import (
    KALSHI_WS_RAW_SCHEMA_VERSION,
    AdmissionStatus,
    KalshiWsRawEvent,
    SequenceState,
)
from edmn_trader.adapters.kalshi.ws_recorder import (
    KalshiWsRecorderConfig,
    WebSocketFactory,
    record_kalshi_demo_ws_orderbook,
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
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    EvidenceSegmentWriter,
    recover_unterminated_segment,
    verify_segment_chain,
)
from edmn_trader.data.evidence_policy import (
    V2_THRESHOLD_POLICY,
    EvidenceThresholdPolicy,
)
from edmn_trader.data.payload_safety import validate_no_secret_payload

D2_RUNTIME_SCHEMA_VERSION = "edmn.kalshi.ws.runtime.v2"
D2_RUNTIME_RECORD_SCHEMA_VERSION = "edmn.kalshi.ws.runtime_record.v1"
_HEX_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_BAD_SEQUENCE_STATES = {
    SequenceState.SEQUENCE_GAP_DETECTED,
    SequenceState.SEQUENCE_OUT_OF_ORDER,
    SequenceState.SEQUENCE_DUPLICATE,
    SequenceState.RESYNC_REQUIRED,
    SequenceState.UNRECOVERED_GAP,
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
        if not self.branch or not self.remote or not isinstance(self.dirty_state, bool):
            raise ValueError("complete runtime code provenance is required")
        object.__setattr__(self, "public_code_commit", commit)

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
        pricing_mode_and_source="subscription_metadata_or_explicit_venue_default",
        provenance=provenance,
        started_at_utc=started_at,
    )
    provider = lifecycle_provider or _default_lifecycle_provider
    session.record_lifecycle(
        market_metadata,
        observed_at_utc=started_at,
        evaluated_at_utc=started_at,
    )
    last_lifecycle_poll = started_at
    lifecycle_blocker: str | None = None

    def poll_lifecycle(observed_at: datetime, *, force: bool = False) -> None:
        nonlocal last_lifecycle_poll, lifecycle_blocker
        if not force and (
            observed_at - last_lifecycle_poll
        ).total_seconds() < 60:
            return
        try:
            current = provider(session.selected_market_ticker)
            session.record_lifecycle(
                current,
                observed_at_utc=observed_at,
                evaluated_at_utc=observed_at,
            )
            last_lifecycle_poll = observed_at
        except Exception:
            lifecycle_blocker = "LIFECYCLE_OBSERVATION_FAILED"

    recorder = record_kalshi_demo_ws_orderbook(
        KalshiWsRecorderConfig(
            campaign_id=campaign_id,
            market_tickers=(session.selected_market_ticker,),
            raw_events_path=session.current_data_path,
            duration_seconds=duration_seconds,
            max_events=max_events,
            max_reconnects=max_reconnects,
            persist_legacy_raw_events=False,
        ),
        auth,
        websocket_factory=websocket_factory,
        now=clock,
        event_callback=session.record_event,
        connection_callback=session.record_connection_event,
        tick_callback=poll_lifecycle,
        monotonic=monotonic,
        monotonic_ns=monotonic_ns,
    )
    ended_at = clock()
    poll_lifecycle(ended_at, force=True)
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
    root.mkdir(parents=True, exist_ok=True)
    dimensions = EvidenceDimensions(
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
    summary = {
        "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "schema_version": D2_RUNTIME_SCHEMA_VERSION,
        "raw_event_schema_version": KALSHI_WS_RAW_SCHEMA_VERSION,
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
        "selected_market_metadata": dict(selected_market_metadata or {}),
        "selected_market_selection": dict(selected_market_selection or {}),
        "market": (selected_market_metadata or {}).get("ticker", "UNSELECTED"),
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
    _atomic_write_json(root / "campaign_summary.json", summary)
    _atomic_write_json(root / "campaign_manifest.json", summary)
    _atomic_write_json(root / "run_metadata.json", summary)
    _atomic_write_json(root / "campaign_validation.json", validation)
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
        checkpoint_every_records: int = 1_000,
        max_segment_bytes: int = 64 * 1024 * 1024,
        max_segment_age_seconds: int = 3_600,
    ) -> None:
        if not campaign_id or not mode or configured_duration_seconds < 1:
            raise ValueError("runtime identity, mode, and duration are required")
        _require_aware(started_at_utc, "started_at_utc")
        validate_no_secret_payload(selected_market_metadata)
        validate_no_secret_payload(selected_market_selection)
        ticker = selected_market_metadata.get("ticker") or selected_market_metadata.get(
            "market_ticker"
        )
        if not isinstance(ticker, str) or not ticker:
            raise ValueError("selected market ticker is required")
        if threshold_policy.effective_at_utc > started_at_utc:
            raise ValueError("threshold policy must be effective before runtime start")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for name in ("campaign_summary.json", "campaign_validation.json"):
            if (self.output_dir / name).exists():
                raise FileExistsError(f"new D2 runtime will not overwrite {name}")
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
        self.checkpoint_every_records = checkpoint_every_records
        self.max_segment_bytes = max_segment_bytes
        self.max_segment_age_seconds = max_segment_age_seconds
        self._artifact_clock = self.started_at_utc
        self._evidence_segment_number = 0
        self._evidence_local_row_index = 0
        self._closed_segment_summaries: list[dict[str, object]] = []
        self._writer = self._new_writer()
        self._rebuilder = KalshiWsBookRebuilder()
        self._sequence: dict[tuple[str, str], dict[str, object]] = {}
        self._rebuild: dict[tuple[str, str, str], dict[str, object]] = {}
        self._connection_events: list[dict[str, object]] = []
        self._connection_windows: dict[str, dict[str, object]] = {}
        self._lifecycle_records: list[dict[str, object]] = []
        self._raw_counts: Counter[str] = Counter()
        self._admitted_selected_orderbook_counts: Counter[str] = Counter()
        self._raw_event_count = 0
        self._public_trade_count = 0
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
        self._write_open_status(self.started_at_utc)

    @property
    def current_data_path(self) -> Path:
        return self._writer.data_path

    def record_connection_event(self, event: ConnectionEvidenceEvent) -> None:
        record = event.to_record()
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

    def record_lifecycle(
        self,
        market_metadata: Mapping[str, object],
        *,
        observed_at_utc: datetime,
        evaluated_at_utc: datetime,
    ) -> None:
        if self._last_lifecycle_at is not None:
            self._max_lifecycle_age = _max_age(
                self._max_lifecycle_age,
                _age_seconds(evaluated_at_utc, self._last_lifecycle_at),
            )
        evidence = record_rest_lifecycle(
            market_metadata,
            selected_market_ticker=self.selected_market_ticker,
            observed_at_utc=observed_at_utc,
            evaluated_at_utc=evaluated_at_utc,
            max_age_seconds=self.threshold_policy.maximum_lifecycle_age_seconds,
        )
        record = evidence.to_record()
        self._lifecycle_records.append(record)
        self._last_lifecycle_at = observed_at_utc
        self._append(
            "lifecycle_evidence",
            {"lifecycle_event": record},
            observed_at_utc=evaluated_at_utc,
        )
        self._sample_freshness(evaluated_at_utc)

    def record_event(self, event: KalshiWsRawEvent) -> None:
        if event.campaign_id != self.campaign_id:
            raise ValueError("D2A event campaign does not match runtime campaign")
        rebuild = self._rebuilder.apply(event)
        trade_stream = build_public_trade_stream(
            (event,),
            selected_market_tickers=(self.selected_market_ticker,),
        )
        trade_records = trade_stream.to_records()
        self._raw_event_count += 1
        self._raw_counts[event.native_type or "unknown"] += 1
        self._public_trade_count += len(trade_records)
        self._last_event_at = event.received_at_utc
        selected_orderbook_event = (
            event.admission_status is AdmissionStatus.ADMITTED
            and event.native_market_ticker == self.selected_market_ticker
            and event.native_type in {"orderbook_snapshot", "orderbook_delta"}
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
        self._sample_freshness(event.received_at_utc)

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
        self._closed_segment_summaries.append(
            self._closed_segment_record(
                self._writer,
                self._writer.close(terminal_reason=terminal_reason),
            )
        )
        artifact_integrity = self._verify_closed_segments()
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
        dimensions = self._dimensions(
            timing=timing,
            artifact_integrity=artifact_integrity,
            connection_established=connection_established,
            subscription_acknowledged=subscription_acknowledged,
            blocker_code=blocker_code,
        )
        classification = classify_evidence(dimensions)
        connection_windows = self._connection_window_records()
        disconnect_durations = self._disconnect_durations(connection_windows)
        summary: dict[str, object] = {
            "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "raw_event_schema_version": KALSHI_WS_RAW_SCHEMA_VERSION,
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
            "lifecycle_observations": self._lifecycle_records,
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
            "lifecycle_observation_count": len(self._lifecycle_records),
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
                self._lifecycle_records[-1]["lifecycle_status"]
                if self._lifecycle_records
                else "UNKNOWN"
            ),
            "websocket_message_freshness_status": (
                "QUIET_WARNING"
                if (freshness.orderbook_event_quiet_interval_seconds or 0)
                > self.threshold_policy.orderbook_quiet_warning_seconds
                else "FRESH"
            ),
            "exchange_heartbeat_status": freshness.transport_keepalive_status,
            "supervisor_liveness_status": "UNKNOWN",
            "campaign_process_liveness_status": "EXITED",
            "connection_established": connection_established,
            "subscription_acknowledged": subscription_acknowledged,
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
        _atomic_write_json(self.output_dir / "campaign_summary.json", summary)
        _atomic_write_json(self.output_dir / "campaign_manifest.json", summary)
        _atomic_write_json(self.output_dir / "run_metadata.json", summary)
        validation = validate_d2_runtime_artifacts(self.output_dir)
        summary["validation_status"] = validation["status"]
        summary["evidence_classification"] = validation["overall_evidence_classification"]
        _atomic_write_json(self.output_dir / "campaign_summary.json", summary)
        _atomic_write_json(self.output_dir / "campaign_manifest.json", summary)
        _atomic_write_json(self.output_dir / "run_metadata.json", summary)
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
        self._write_open_status(observed_at_utc)

    def _write_open_status(self, observed_at_utc: datetime) -> None:
        actual = _decimal_seconds(observed_at_utc - self.started_at_utc)
        summary = {
            "runtime_schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "schema_version": D2_RUNTIME_SCHEMA_VERSION,
            "raw_event_schema_version": KALSHI_WS_RAW_SCHEMA_VERSION,
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
            "connected_elapsed_seconds": None,
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
            "connection_windows": self._connection_window_records(),
            "disconnect_durations": [],
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
            "freshness_dimensions": {
                "transport_keepalive_status": (
                    KeepaliveStatus.OBSERVED
                    if self._last_keepalive_at
                    else KeepaliveStatus.UNKNOWN_NOT_OBSERVED
                ),
                "transport_keepalive_age_seconds": None,
                "lifecycle_observation_age_seconds": None,
                "orderbook_event_quiet_interval_seconds": None,
            },
            "artifact_integrity_summary": {
                "integrity_scope": "CHECKPOINT_BOUNDED",
                "closed_file_hash_verified": None,
            },
            "independent_evidence_classifications": {
                field: EvidenceStatus.UNKNOWN for field in EvidenceDimensions.__dataclass_fields__
            },
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
        _atomic_write_json(self.output_dir / "campaign_summary.json", summary)
        _atomic_write_json(self.output_dir / "run_metadata.json", summary)

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
                "frame_hashes": [],
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
        if result.frame is not None:
            frame = result.frame
            frame_record = frame.to_record()
            record["frame"] = frame_record
            summary["frame_count"] += 1
            summary["frame_hashes"].append(frame.frame_hash)
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
            if result.reason is not None:
                summary["invalidation_reasons"][result.reason] += 1
        return record

    def _sequence_summary_records(self) -> list[dict[str, object]]:
        records = []
        for summary in self._sequence.values():
            records.append(
                {
                    **summary,
                    "segment_boundary_reasons": sorted(summary["segment_boundary_reasons"]),
                    "native_sid_values": sorted(summary["native_sid_values"]),
                    "sequence_states": dict(sorted(summary["sequence_states"].items())),
                    "continuity_semantics_supported": (
                        SequenceState.SEQUENCE_CONTIGUITY_VERIFIED
                        in summary["sequence_states"]
                    ),
                    "aggregate_result": _sequence_result(summary["sequence_states"]),
                }
            )
        return records

    def _rebuild_summary_records(self) -> list[dict[str, object]]:
        records = []
        for summary in self._rebuild.values():
            records.append(
                {
                    **summary,
                    "invalidation_reasons": dict(
                        sorted(summary["invalidation_reasons"].items())
                    ),
                    "pricing_modes": sorted(summary["pricing_modes"]),
                    "pricing_mode_sources": sorted(summary["pricing_mode_sources"]),
                }
            )
        return records

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
        windows = self._connection_window_records()
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

    def _connection_window_records(self) -> list[dict[str, object]]:
        records = []
        for window in self._connection_windows.values():
            opened = _parse_time(window["opened_at_utc"])
            closed = _parse_time(window["closed_at_utc"])
            duration = _decimal_seconds(closed - opened) if opened and closed else Decimal("0")
            records.append({**window, "duration_seconds": _decimal_text(duration)})
        return records

    @staticmethod
    def _disconnect_durations(windows: list[dict[str, object]]) -> list[str]:
        ordered = sorted(
            (window for window in windows if window["opened_at_utc"]),
            key=lambda window: str(window["opened_at_utc"]),
        )
        durations = []
        for previous, current in zip(ordered, ordered[1:], strict=False):
            closed = _parse_time(previous["closed_at_utc"])
            opened = _parse_time(current["opened_at_utc"])
            if closed and opened and opened >= closed:
                durations.append(_decimal_text(_decimal_seconds(opened - closed)))
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
            self._lifecycle_records,
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
        disconnects = self._disconnect_durations(self._connection_window_records())
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
                EvidenceStatus.PASS if subscription_acknowledged else EvidenceStatus.FAIL
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


def validate_d2_runtime_artifacts(input_dir: Path) -> dict[str, object]:
    root = Path(input_dir)
    failures: list[str] = []
    try:
        summary = json.loads((root / "campaign_summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        summary = {}
        failures.append(f"campaign_summary unavailable: {exc}")
    if summary.get("runtime_schema_version") != D2_RUNTIME_SCHEMA_VERSION:
        failures.append("runtime schema missing or unsupported")
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
    )
    failures.extend(f"missing required field: {name}" for name in required if name not in summary)
    try:
        validate_no_secret_payload(summary)
    except ValueError as exc:
        failures.append(str(exc))
    segments = summary.get("segment_summaries", [])
    if not isinstance(segments, list) or not segments:
        failures.append("at least one closed evidence segment is required")
        segments = []
    runtime_record_counts: Counter[str] = Counter()
    runtime_records: list[dict[str, object]] = []
    for segment in segments:
        try:
            data_path = root / str(segment["data_path"])
            checkpoint_path = root / str(segment["checkpoint_path"])
            segment_summary_path = root / str(segment["summary_path"])
            segment_id = str(segment["segment_id"])
            verified = verify_segment_chain(data_path, segment_id=segment_id)
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            segment_summary = json.loads(
                segment_summary_path.read_text(encoding="utf-8")
            )
            _validate_runtime_records(data_path, runtime_record_counts, runtime_records)
            with data_path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if verified.terminal_chain_hash != segment["terminal_chain_hash"]:
                failures.append(f"append-chain mismatch: {segment_id}")
            if checkpoint.get("schema_version") != EVIDENCE_CHECKPOINT_SCHEMA_VERSION:
                failures.append(f"checkpoint schema mismatch: {segment_id}")
            if checkpoint.get("chain_hash") != segment["terminal_chain_hash"]:
                failures.append(f"checkpoint hash mismatch: {segment_id}")
            if digest != segment["closed_file_sha256"]:
                failures.append(f"closed-file hash mismatch: {segment_id}")
            if segment.get("schema_version") != EVIDENCE_SUMMARY_SCHEMA_VERSION:
                failures.append(f"segment summary schema mismatch: {segment_id}")
            if segment_summary.get("terminal_chain_hash") != segment["terminal_chain_hash"]:
                failures.append(f"segment summary artifact mismatch: {segment_id}")
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"segment verification failed: {exc}")
    for sibling_name in ("campaign_manifest.json", "run_metadata.json"):
        try:
            sibling = json.loads((root / sibling_name).read_text(encoding="utf-8"))
            if sibling != summary:
                failures.append(f"{sibling_name} contradicts campaign_summary.json")
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{sibling_name} unavailable: {exc}")
    for field, expected in (
        ("live_gate_status", "disabled"),
        ("production_trading_enabled", False),
        ("executable_order_intent", False),
        ("production_endpoint_used", False),
        ("submit_attempts", 0),
    ):
        if summary.get(field) != expected:
            failures.append(f"unsafe runtime field: {field}")
    try:
        dimensions, durable_counts = _derive_runtime_validation(summary, runtime_records)
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(f"durable evidence classification failed: {exc}")
        dimensions = {
            field: EvidenceStatus.UNKNOWN
            for field in EvidenceDimensions.__dataclass_fields__
        }
        durable_counts = Counter()
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
    dimensions["artifact_integrity"] = (
        EvidenceStatus.PASS if not failures else EvidenceStatus.FAIL
    )
    if recorded_dimensions.get("artifact_integrity") != dimensions["artifact_integrity"]:
        failures.append("recorded evidence dimension contradicts artifacts: artifact_integrity")
        dimensions["artifact_integrity"] = EvidenceStatus.FAIL
    overall = classify_evidence(EvidenceDimensions(**dimensions)).overall_classification
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
    _atomic_write_json(root / "campaign_validation.json", result)
    return result


def _validate_runtime_records(
    path: Path,
    counts: Counter[str],
    records: list[dict[str, object]],
) -> None:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            validate_no_secret_payload(record)
            if record.get("schema_version") != D2_RUNTIME_RECORD_SCHEMA_VERSION:
                raise ValueError("runtime record schema missing or unsupported")
            record_type = record.get("record_type")
            if not isinstance(record_type, str):
                raise ValueError("runtime record type is required")
            counts[record_type] += 1
            records.append(record)
            if record_type == "raw_transport_event":
                d2a_event = record.get("d2a_event")
                if not isinstance(d2a_event, Mapping):
                    raise ValueError("durable raw record is missing its D2A envelope")
                KalshiWsRawEvent.from_record(d2a_event)


def _derive_runtime_validation(
    summary: Mapping[str, object],
    records: list[dict[str, object]],
) -> tuple[dict[str, EvidenceStatus], Counter[str]]:
    raw_events: list[KalshiWsRawEvent] = []
    sequence: dict[tuple[str, str], dict[str, object]] = {}
    rebuild: dict[tuple[str, str, str], dict[str, object]] = {}
    connection_events: list[Mapping[str, object]] = []
    lifecycle_records: list[Mapping[str, object]] = []
    counts: Counter[str] = Counter()
    selected_market = str(summary["market_ticker"])
    for record in records:
        record_type = record["record_type"]
        if record_type == "connection_evidence":
            connection_events.append(_required_mapping(record, "connection_event"))
            continue
        if record_type == "lifecycle_evidence":
            lifecycle_records.append(_required_mapping(record, "lifecycle_event"))
            continue
        if record_type != "raw_transport_event":
            continue
        event = KalshiWsRawEvent.from_record(_required_mapping(record, "d2a_event"))
        raw_events.append(event)
        counts["event_count"] += 1
        counts[f"native:{event.native_type or 'unknown'}"] += 1
        trades = record.get("d2c_public_trades")
        if not isinstance(trades, list):
            raise ValueError("durable public trade evidence must be a list")
        counts["trade_count"] += len(trades)
        _accumulate_validation_sequence(sequence, event)
        _accumulate_validation_rebuild(
            rebuild,
            event,
            _required_mapping(record, "d2b_rebuild"),
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
    for key in tuple(counts):
        if key.startswith(("native:", "admitted_selected:")):
            del counts[key]

    started = _parse_required_time(summary.get("started_at"), "started_at")
    ended = _parse_required_time(summary.get("ended_at"), "ended_at")
    actual = _decimal_seconds(ended - started)
    windows = _validation_connection_windows(connection_events, ended)
    connected = sum(
        (Decimal(str(window["duration_seconds"])) for window in windows),
        Decimal("0"),
    )
    connected = min(actual, connected)
    disconnects = RuntimeEvidenceSession._disconnect_durations(windows)
    maximum_disconnect = max(
        (Decimal(value) for value in disconnects),
        default=Decimal("0"),
    )
    keepalives = [
        event.received_at_utc
        for event in raw_events
        if event.native_type in {"heartbeat", "pong"}
    ]
    selected_orderbook = [
        event
        for event in raw_events
        if event.admission_status is AdmissionStatus.ADMITTED
        and event.native_market_ticker == selected_market
        and event.native_type in {"orderbook_snapshot", "orderbook_delta"}
    ]
    lifecycle_times = [
        _parse_required_time(record.get("observed_at_utc"), "lifecycle observed_at_utc")
        for record in lifecycle_records
    ]
    maximum_keepalive_age = _maximum_observation_gap(keepalives, ended)
    maximum_lifecycle_age = _maximum_observation_gap(lifecycle_times, ended)
    maximum_orderbook_quiet = _maximum_observation_gap(
        [event.received_at_utc for event in selected_orderbook],
        ended,
    )
    timing = build_evidence_timing(
        configured_duration_seconds=int(summary["configured_duration_seconds"]),
        started_at_utc=started,
        checkpoint_at_utc=None,
        ended_at_utc=ended,
        first_snapshot_at=next(
            (
                event.received_at_utc
                for event in selected_orderbook
                if event.native_type == "orderbook_snapshot"
            ),
            None,
        ),
        last_event_at=raw_events[-1].received_at_utc if raw_events else None,
        terminal_reason=str(summary["terminal_reason"]),
        stop_requested=bool(summary["stop_requested"]),
        total_disconnect_seconds=max(Decimal("0"), actual - connected),
        threshold_policy_version=V2_THRESHOLD_POLICY.version,
        threshold_source_commit=str(summary["threshold_source_commit"]),
        threshold_effective_utc=V2_THRESHOLD_POLICY.effective_at_utc,
        transport_keepalive_age_seconds=(
            _age_seconds(ended, keepalives[-1]) if keepalives else None
        ),
        lifecycle_observation_age_seconds=(
            _age_seconds(ended, lifecycle_times[-1]) if lifecycle_times else None
        ),
        orderbook_event_quiet_interval_seconds=(
            _age_seconds(ended, selected_orderbook[-1].received_at_utc)
            if selected_orderbook
            else None
        ),
        max_transport_keepalive_age_seconds=maximum_keepalive_age,
        max_lifecycle_observation_age_seconds=maximum_lifecycle_age,
        max_orderbook_event_quiet_interval_seconds=maximum_orderbook_quiet,
    )
    if Decimal(str(summary["actual_elapsed_seconds"])) != timing.actual_elapsed_seconds:
        raise ValueError("actual elapsed summary contradicts timestamps")
    if Decimal(str(summary["connected_elapsed_seconds"])) != timing.connected_elapsed_seconds:
        raise ValueError("connected elapsed summary contradicts connection evidence")
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
    lifecycle = _loaded_lifecycle_status(
        lifecycle_records,
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
            if not keepalives
            else EvidenceStatus.PASS
            if (maximum_keepalive_age or 0)
            <= V2_THRESHOLD_POLICY.maximum_transport_keepalive_age_seconds
            else EvidenceStatus.FAIL
        ),
        subscription_status=(
            EvidenceStatus.PASS
            if opened_ids and opened_ids <= acknowledged_ids and not rejected
            else EvidenceStatus.FAIL
        ),
        sequence_integrity=_sequence_evidence_status(sequence),
        rebuild_integrity=_rebuild_evidence_status(rebuild),
        market_lifecycle_validity=lifecycle,
        duration_evidence=classify_duration_evidence(timing),
        process_liveness=(
            EvidenceStatus.PASS
            if summary.get("status") == "d2_runtime_complete"
            and summary.get("blocker_code") is None
            else EvidenceStatus.FAIL
        ),
        supervisor_liveness=EvidenceStatus.UNKNOWN,
        backup_integrity=EvidenceStatus.UNKNOWN,
        replay_qualification=EvidenceStatus.UNKNOWN,
    ).to_record()
    return dimensions, counts


def _required_mapping(record: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = record.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"durable runtime record is missing {field}")
    return value


def _accumulate_validation_sequence(
    summaries: dict[tuple[str, str], dict[str, object]],
    event: KalshiWsRawEvent,
) -> None:
    summary = summaries.setdefault(
        (event.connection_id, event.segment_id),
        {"sequence_states": Counter()},
    )
    summary["sequence_states"][event.sequence_state] += 1


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
            "frame_count": 0,
            "orderbook_row_count": 0,
            "invalidation_reasons": Counter(),
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
    if isinstance(frame, Mapping):
        summary["frame_count"] += 1
        counts["rebuild_frame_count"] += 1
        summary["native_state_valid"] = frame.get("segment_validity") == SegmentValidity.VALID
        if event.native_type == "orderbook_snapshot":
            summary["snapshot_first_admitted"] = True
    elif event.native_type in {"orderbook_snapshot", "orderbook_delta"}:
        reason = result.get("reason")
        if reason is not None:
            summary["invalidation_reasons"][str(reason)] += 1


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
                "opened_at_utc": None,
                "closed_at_utc": None,
            },
        )
        event_type = str(event["event_type"])
        observed = str(event["observed_at_utc"])
        if event_type in {
            ConnectionEvidenceType.CONNECTION_OPEN,
            ConnectionEvidenceType.RECONNECT,
        } and window["opened_at_utc"] is None:
            window["opened_at_utc"] = observed
        if event_type == ConnectionEvidenceType.CONNECTION_CLOSE:
            window["closed_at_utc"] = observed
    records = []
    for window in windows.values():
        opened = _parse_time(window["opened_at_utc"])
        closed = _parse_time(window["closed_at_utc"]) or ended_at_utc
        duration = (
            _decimal_seconds(closed - opened)
            if opened is not None and closed >= opened
            else Decimal("0")
        )
        records.append({**window, "duration_seconds": _decimal_text(duration)})
    return records


def _loaded_lifecycle_status(
    records: list[Mapping[str, object]],
    maximum_age: int | None,
) -> EvidenceStatus:
    if not records:
        return EvidenceStatus.UNKNOWN
    if any(
        record.get("lifecycle_status") != LifecycleStatus.OPEN
        or record.get("validity") != LifecycleValidity.VALID
        for record in records
    ):
        return EvidenceStatus.FAIL
    return (
        EvidenceStatus.PASS
        if (maximum_age or 0) <= V2_THRESHOLD_POLICY.maximum_lifecycle_age_seconds
        else EvidenceStatus.FAIL
    )


def _maximum_observation_gap(
    observations: list[datetime],
    ended_at_utc: datetime,
) -> int | None:
    if not observations:
        return None
    ordered = sorted(observations)
    return max(
        [
            _age_seconds(current, previous)
            for previous, current in zip(ordered, ordered[1:], strict=False)
        ]
        + [_age_seconds(ended_at_utc, ordered[-1])]
    )


def _parse_required_time(value: object, field: str) -> datetime:
    parsed = _parse_time(value)
    if parsed is None:
        raise ValueError(f"{field} is missing or invalid")
    return parsed


def recover_d2_runtime_artifacts(
    input_dir: Path,
    *,
    recovered_at_utc: datetime,
) -> dict[str, object]:
    """Close one crashed open D2 segment; never auto-resume the campaign."""

    _require_aware(recovered_at_utc, "recovered_at_utc")
    root = Path(input_dir)
    summary_path = root / "campaign_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("runtime_schema_version") != D2_RUNTIME_SCHEMA_VERSION:
        raise ValueError("runtime recovery requires the D2 runtime schema")
    open_segments = [
        segment
        for segment in summary.get("segment_summaries", [])
        if isinstance(segment, Mapping) and segment.get("segment_closed") is False
    ]
    if len(open_segments) != 1:
        raise ValueError("runtime recovery requires exactly one open segment")
    segment = open_segments[0]
    segment_id = str(segment["segment_id"])
    next_segment_id = f"{summary['campaign_id']}.recovery.next"
    data_path = root / str(segment["data_path"])
    checkpoint_path = root / str(segment["checkpoint_path"])
    closed_summary_path = data_path.with_name(f"{segment_id}.summary.json")
    recovered = recover_unterminated_segment(
        data_path=data_path,
        checkpoint_path=checkpoint_path,
        summary_path=closed_summary_path,
        segment_id=segment_id,
        next_segment_id=next_segment_id,
        now_utc=lambda: recovered_at_utc,
    )
    closed_summary = json.loads(closed_summary_path.read_text(encoding="utf-8"))
    segment_record = {
        **closed_summary,
        "data_path": str(data_path.relative_to(root)),
        "checkpoint_path": str(checkpoint_path.relative_to(root)),
        "summary_path": str(closed_summary_path.relative_to(root)),
        "recovery_status": "CRASH_RECOVERED",
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
        recovered_windows
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
        "next_segment_id": recovered.next_segment_id,
        "next_segment_metadata_path": segment_record["next_segment_metadata_path"],
        "snapshot_required": recovered.snapshot_required,
        "inherited_book_state": recovered.inherited_book_state,
        "automatic_restart": False,
        "replay_qualified": False,
    }
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
    _atomic_write_json(root / "runtime_recovery.json", recovery)
    return recovery


def _sync_runtime_summary(root: Path, summary: Mapping[str, object]) -> None:
    for name in ("campaign_summary.json", "campaign_manifest.json", "run_metadata.json"):
        _atomic_write_json(root / name, summary)


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
    records: list[Mapping[str, object]],
    maximum_age: int | None,
    threshold: int,
) -> EvidenceStatus:
    if not records:
        return EvidenceStatus.UNKNOWN
    if any(
        record.get("lifecycle_status") is not LifecycleStatus.OPEN
        or record.get("validity") is not LifecycleValidity.VALID
        for record in records
    ):
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


def _selected_status(metadata: Mapping[str, object]) -> object:
    return metadata.get("status") or metadata.get("raw_status")


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    validate_no_secret_payload(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


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
