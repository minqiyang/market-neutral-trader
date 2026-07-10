"""Synthetic performance gate for evidence append-chain durability."""

from __future__ import annotations

import hashlib
import math
import resource
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from edmn_trader.data.evidence_durability import (
    EvidenceSegmentWriter,
    recover_unterminated_segment,
    serialize_record_bytes,
    verify_segment_chain,
)

MAX_ELAPSED_SECONDS = 600
MAX_PEAK_RSS_MIB = 512
MAX_CHECKPOINT_P95_SECONDS = 1
MIN_BENCHMARK_EVENT_COUNT = 100_000
MAX_BENCHMARK_CHECKPOINT_INTERVAL = 1_000


@dataclass(frozen=True, slots=True)
class EvidenceBenchmarkResult:
    event_count: int
    memory_profile_bytes: int
    checkpoint_every_records: int
    elapsed_seconds: float
    peak_rss_mib: float
    checkpoint_count: int
    checkpoint_p95_seconds: float
    no_oom: bool
    no_full_file_callback_work: bool
    valid_hashes: bool
    crash_recovery_valid: bool

    def __post_init__(self) -> None:
        for name, value in (
            ("event_count", self.event_count),
            ("memory_profile_bytes", self.memory_profile_bytes),
            ("checkpoint_every_records", self.checkpoint_every_records),
            ("checkpoint_count", self.checkpoint_count),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name, value in (
            ("elapsed_seconds", self.elapsed_seconds),
            ("peak_rss_mib", self.peak_rss_mib),
            ("checkpoint_p95_seconds", self.checkpoint_p95_seconds),
        ):
            if (
                not isinstance(value, int | float)
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        for name, value in (
            ("no_oom", self.no_oom),
            ("no_full_file_callback_work", self.no_full_file_callback_work),
            ("valid_hashes", self.valid_hashes),
            ("crash_recovery_valid", self.crash_recovery_valid),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be Boolean")

    @property
    def passed(self) -> bool:
        return (
            self.event_count >= MIN_BENCHMARK_EVENT_COUNT
            and self.checkpoint_every_records
            <= MAX_BENCHMARK_CHECKPOINT_INTERVAL
            and self.checkpoint_count
            >= self.event_count // self.checkpoint_every_records + 2
            and self.elapsed_seconds <= MAX_ELAPSED_SECONDS
            and self.peak_rss_mib <= MAX_PEAK_RSS_MIB
            and self.peak_rss_mib * 1024 * 1024 <= self.memory_profile_bytes
            and self.checkpoint_p95_seconds <= MAX_CHECKPOINT_P95_SECONDS
            and self.no_oom
            and self.no_full_file_callback_work
            and self.valid_hashes
            and self.crash_recovery_valid
        )

    def to_record(self) -> dict[str, object]:
        return {
            "event_count": self.event_count,
            "memory_profile_bytes": self.memory_profile_bytes,
            "checkpoint_every_records": self.checkpoint_every_records,
            "elapsed_seconds": self.elapsed_seconds,
            "peak_rss_mib": self.peak_rss_mib,
            "checkpoint_count": self.checkpoint_count,
            "checkpoint_p95_seconds": self.checkpoint_p95_seconds,
            "no_oom": self.no_oom,
            "no_full_file_callback_work": self.no_full_file_callback_work,
            "valid_hashes": self.valid_hashes,
            "crash_recovery_valid": self.crash_recovery_valid,
            "passed": self.passed,
        }


def run_evidence_benchmark(
    root: Path,
    *,
    event_count: int = 100_000,
    checkpoint_every_records: int = 1_000,
    memory_profile_bytes: int = 1024 * 1024 * 1024,
) -> EvidenceBenchmarkResult:
    if event_count < 1 or checkpoint_every_records < 1:
        raise ValueError("benchmark event and checkpoint counts must be positive")
    if memory_profile_bytes < 1:
        raise ValueError("memory_profile_bytes must be positive")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    now = datetime.now(UTC)
    writer = EvidenceSegmentWriter(
        root / "append",
        segment_id="benchmark-segment",
        checkpoint_every_records=checkpoint_every_records,
        now_utc=lambda: now,
    )
    for index in range(1, event_count + 1):
        writer.append(
            {
                "local_row_index": index,
                "record_type": "synthetic_benchmark_event",
                "market_ticker": "SYNTHETIC-MARKET",
                "price_dollars": "0.4200",
                "quantity_fp": "1.125",
            }
        )
    no_callback_full_hash = writer.full_file_hash_count == 0
    summary = writer.close(terminal_reason="synthetic_benchmark_complete")
    verified = verify_segment_chain(
        writer.data_path,
        segment_id=writer.segment_id,
    )
    valid_hashes = (
        verified.record_count == event_count
        and verified.terminal_chain_hash == summary["terminal_chain_hash"]
        and verified.byte_offset == summary["byte_offset"]
        and _closed_file_sha256(writer.data_path) == summary["closed_file_sha256"]
        and writer.full_file_hash_count == 1
    )
    crash_recovery_valid = _run_crash_recovery_fixture(root / "recovery", now)
    elapsed = time.perf_counter() - started
    checkpoint_p95 = _p95(writer.checkpoint_durations_seconds)
    peak_rss_mib = _peak_rss_mib()
    return EvidenceBenchmarkResult(
        event_count=event_count,
        memory_profile_bytes=memory_profile_bytes,
        checkpoint_every_records=checkpoint_every_records,
        elapsed_seconds=elapsed,
        peak_rss_mib=peak_rss_mib,
        checkpoint_count=len(writer.checkpoint_durations_seconds),
        checkpoint_p95_seconds=checkpoint_p95,
        no_oom=True,
        no_full_file_callback_work=no_callback_full_hash,
        valid_hashes=valid_hashes,
        crash_recovery_valid=crash_recovery_valid,
    )


def _run_crash_recovery_fixture(root: Path, now: datetime) -> bool:
    writer = EvidenceSegmentWriter(
        root,
        segment_id="crashed-segment",
        checkpoint_every_records=99,
        now_utc=lambda: now,
    )
    writer.append({"local_row_index": 1, "record_type": "synthetic_recovery"})
    writer.checkpoint()
    writer._handle.close()
    with writer.data_path.open("ab") as handle:
        handle.write(
            serialize_record_bytes(
                {"local_row_index": 2, "record_type": "synthetic_recovery"}
            )
        )
        handle.write(b'{"local_row_index":3')
    recovered = recover_unterminated_segment(
        data_path=writer.data_path,
        checkpoint_path=writer.checkpoint_path,
        summary_path=writer.summary_path,
        segment_id="crashed-segment",
        next_segment_id="fresh-segment",
        now_utc=lambda: now,
    )
    verified = verify_segment_chain(writer.data_path, segment_id="crashed-segment")
    return (
        recovered.last_committed_local_row_index == 2
        and recovered.partial_tail_bytes_removed > 0
        and recovered.snapshot_required
        and not recovered.inherited_book_state
        and verified.terminal_chain_hash == recovered.terminal_chain_hash
        and _closed_file_sha256(writer.data_path) == recovered.closed_file_sha256
        and Path(recovered.next_segment_metadata_path).is_file()
    )


def _p95(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def _peak_rss_mib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    bytes_used = value if sys.platform == "darwin" else value * 1024
    return bytes_used / (1024 * 1024)


def _closed_file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
