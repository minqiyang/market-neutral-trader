from __future__ import annotations

import pytest

from edmn_trader.data.evidence_benchmark import (
    EvidenceBenchmarkResult,
    run_evidence_benchmark,
)


def test_synthetic_100k_evidence_benchmark_meets_merge_gates(tmp_path) -> None:
    result = run_evidence_benchmark(
        tmp_path,
        event_count=100_000,
        checkpoint_every_records=1_000,
        memory_profile_bytes=1024 * 1024 * 1024,
    )

    assert result.event_count == 100_000
    assert result.memory_profile_bytes == 1024 * 1024 * 1024
    assert result.elapsed_seconds <= 600
    assert result.peak_rss_mib <= 512
    assert result.checkpoint_p95_seconds <= 1
    assert result.no_oom is True
    assert result.no_full_file_callback_work is True
    assert result.valid_hashes is True
    assert result.crash_recovery_valid is True
    assert result.passed is True


def test_synthetic_benchmark_enforces_declared_memory_budget(tmp_path) -> None:
    result = run_evidence_benchmark(
        tmp_path,
        event_count=1,
        checkpoint_every_records=1,
        memory_profile_bytes=1,
    )

    assert result.peak_rss_mib > 0
    assert result.passed is False


def test_benchmark_pass_is_derived_and_cannot_be_overridden() -> None:
    result = EvidenceBenchmarkResult(
        event_count=1,
        memory_profile_bytes=1,
        elapsed_seconds=601,
        peak_rss_mib=513,
        checkpoint_count=1,
        checkpoint_p95_seconds=2,
        no_oom=False,
        no_full_file_callback_work=False,
        valid_hashes=False,
        crash_recovery_valid=False,
    )

    assert result.passed is False
    with pytest.raises(TypeError, match="passed"):
        EvidenceBenchmarkResult(
            event_count=1,
            memory_profile_bytes=1,
            elapsed_seconds=601,
            peak_rss_mib=513,
            checkpoint_count=1,
            checkpoint_p95_seconds=2,
            no_oom=False,
            no_full_file_callback_work=False,
            valid_hashes=False,
            crash_recovery_valid=False,
            passed=True,
        )
