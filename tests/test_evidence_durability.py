from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edmn_trader.data.evidence_durability import (
    DEFAULT_MAX_SEGMENT_AGE_SECONDS,
    DEFAULT_MAX_SEGMENT_BYTES,
    EVIDENCE_OPEN_STATUS_SCHEMA_VERSION,
    EVIDENCE_SEGMENT_START_SCHEMA_VERSION,
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    BackupVerificationState,
    EvidenceSegmentWriter,
    RecoveryResult,
    RotationReason,
    chain_genesis_hash,
    compute_chain_hash,
    recover_unterminated_segment,
    verify_segment_chain,
)

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def test_chain_hash_matches_exact_length_prefixed_bytes() -> None:
    genesis = chain_genesis_hash("segment-1")
    record_bytes = b'{"local_row_index":1,"value":"x"}\n'

    actual = compute_chain_hash(genesis, record_bytes)
    expected = hashlib.sha256(
        bytes.fromhex(genesis)
        + struct.pack(">Q", len(record_bytes))
        + record_bytes
    ).hexdigest()

    assert actual == expected
    assert compute_chain_hash(genesis, record_bytes + b" ") != actual


def test_checkpoint_records_committed_offset_and_chain_hash(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=2)
    first_hash = writer.append(_record(1))
    terminal_hash = writer.append(_record(2))

    checkpoint = json.loads(writer.checkpoint_path.read_text())
    verified = verify_segment_chain(writer.data_path, segment_id="segment-1")

    assert checkpoint["segment_id"] == "segment-1"
    assert checkpoint["last_committed_local_row_index"] == 2
    assert checkpoint["byte_offset"] == writer.data_path.stat().st_size
    assert checkpoint["chain_hash"] == terminal_hash
    assert first_hash != terminal_hash
    assert verified.record_count == 2
    assert verified.terminal_chain_hash == terminal_hash
    writer.close(terminal_reason="test_complete")


def test_new_segment_persists_genesis_checkpoint_before_first_append(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)

    checkpoint = json.loads(writer.checkpoint_path.read_text())

    assert checkpoint["last_committed_local_row_index"] == 0
    assert checkpoint["byte_offset"] == 0
    assert checkpoint["chain_hash"] == chain_genesis_hash("segment-1")

    writer.append(_record(1))
    writer._handle.close()
    recovered = recover_unterminated_segment(
        data_path=writer.data_path,
        checkpoint_path=writer.checkpoint_path,
        summary_path=writer.summary_path,
        segment_id="segment-1",
        next_segment_id="segment-2",
        now_utc=lambda: NOW + timedelta(seconds=1),
    )

    assert recovered.last_committed_local_row_index == 1
    assert recovered.partial_tail_bytes_removed == 0


def test_atomic_checkpoint_replaces_without_temp_file(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)
    writer.append(_record(1))
    writer.checkpoint()
    first = writer.checkpoint_path.read_text()
    writer.append(_record(2))
    writer.checkpoint()
    second = writer.checkpoint_path.read_text()

    assert first != second
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads(second)["last_committed_local_row_index"] == 2
    writer.close(terminal_reason="test_complete")


def test_open_segment_claims_checkpoint_bounded_integrity_only(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=1)
    writer.append(_record(1))

    status = writer.status_record()

    assert status["segment_closed"] is False
    assert status["schema_version"] == EVIDENCE_OPEN_STATUS_SCHEMA_VERSION
    assert status["integrity_scope"] == "CHECKPOINT_BOUNDED"
    assert status["closed_file_sha256"] is None
    assert writer.full_file_hash_count == 0
    writer.close(terminal_reason="test_complete")


def test_open_status_never_claims_uncheckpointed_tail(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)
    writer.append(_record(1))

    status = writer.status_record()

    assert status["last_committed_local_row_index"] == 0
    assert status["byte_offset"] == 0
    assert status["chain_hash"] == chain_genesis_hash("segment-1")
    writer.close(terminal_reason="test_complete")


def test_closed_file_hash_is_computed_once_only_when_segment_closes(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=1)
    writer.append(_record(1))
    assert writer.full_file_hash_count == 0

    summary = writer.close(
        terminal_reason="rotation",
        rotation_reason=RotationReason.BYTE_LIMIT,
    )

    assert writer.full_file_hash_count == 1
    assert summary["segment_closed"] is True
    assert summary["schema_version"] == EVIDENCE_SUMMARY_SCHEMA_VERSION
    assert summary["integrity_scope"] == "CLOSED_FILE"
    assert len(summary["closed_file_sha256"]) == 64
    assert summary["backup_verification_state"] == BackupVerificationState.NOT_VERIFIED
    assert summary["retention_deletion_eligible"] is False


def test_recovery_result_hard_codes_fresh_snapshot_safety_boundary() -> None:
    result = RecoveryResult(
        segment_id="segment-1",
        last_committed_local_row_index=1,
        terminal_chain_hash="0" * 64,
        closed_file_sha256="1" * 64,
        partial_tail_bytes_removed=0,
        next_segment_id="segment-2",
        next_segment_metadata_path="segment-2.start.json",
    )

    assert result.terminal_reason == "crash_recovered"
    assert result.snapshot_required is True
    assert result.inherited_book_state is False
    with pytest.raises(ValueError, match="init=False"):
        replace(result, snapshot_required=False)
    with pytest.raises(ValueError, match="new segment"):
        replace(result, next_segment_id="segment-1")


def test_rotation_by_bytes_and_time(tmp_path) -> None:
    monotonic = _MonotonicClock()
    byte_writer = _writer(
        tmp_path / "bytes",
        checkpoint_every_records=99,
        max_segment_bytes=1,
        monotonic_ns=monotonic,
    )
    byte_writer.append(_record(1))
    assert byte_writer.rotation_reason() is RotationReason.BYTE_LIMIT
    byte_rotation = byte_writer.rotate_if_needed(next_segment_id="segment-2")
    assert byte_rotation is not None
    assert byte_rotation.reason is RotationReason.BYTE_LIMIT
    assert byte_rotation.closed_summary["segment_closed"] is True
    assert byte_rotation.next_writer.segment_id == "segment-2"
    byte_rotation.next_writer.close(terminal_reason="test_complete")

    time_writer = _writer(
        tmp_path / "time",
        checkpoint_every_records=99,
        max_segment_age_seconds=1,
        monotonic_ns=monotonic,
    )
    monotonic.advance(seconds=2)
    assert time_writer.rotation_reason() is RotationReason.TIME_LIMIT
    time_rotation = time_writer.rotate_if_needed(next_segment_id="segment-2")
    assert time_rotation is not None
    assert time_rotation.reason is RotationReason.TIME_LIMIT
    assert time_rotation.closed_summary["rotation_reason"] == RotationReason.TIME_LIMIT
    time_rotation.next_writer.close(terminal_reason="test_complete")


def test_rotation_rejects_reused_segment_id_before_closing_current(tmp_path) -> None:
    writer = _writer(tmp_path, max_segment_bytes=1)
    writer.append(_record(1))

    with pytest.raises(ValueError, match="new segment"):
        writer.rotate_if_needed(next_segment_id="segment-1")

    assert writer.status_record()["segment_closed"] is False
    writer.close(terminal_reason="test_complete")


@pytest.mark.parametrize(
    ("terminal_reason", "rotation_reason"),
    [
        ("rotation", None),
        ("test_complete", RotationReason.BYTE_LIMIT),
    ],
)
def test_close_rejects_contradictory_rotation_metadata(
    tmp_path,
    terminal_reason,
    rotation_reason,
) -> None:
    writer = _writer(tmp_path)

    with pytest.raises(ValueError, match="rotation_reason"):
        writer.close(
            terminal_reason=terminal_reason,
            rotation_reason=rotation_reason,
        )

    writer.close(terminal_reason="test_complete")


def test_writer_rejects_existing_checkpoint_or_summary_artifacts(tmp_path) -> None:
    (tmp_path / "segment-1.summary.json").write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="segment artifacts"):
        _writer(tmp_path)

    assert (tmp_path / "segment-1.summary.json").read_text(encoding="utf-8") == (
        "preserve"
    )
    assert not (tmp_path / "segment-1.events.jsonl").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("checkpoint_every_records", True),
        ("max_segment_bytes", 1.5),
        ("max_segment_age_seconds", False),
    ],
)
def test_writer_requires_integer_thresholds(tmp_path, field, value) -> None:
    kwargs = {field: value}

    with pytest.raises(ValueError, match="positive integer"):
        EvidenceSegmentWriter(tmp_path, segment_id="segment-1", **kwargs)


def test_writer_rejects_clock_rollback_before_checkpoint(tmp_path) -> None:
    clock_values = iter((NOW, NOW - timedelta(seconds=1)))

    with pytest.raises(ValueError, match="move backwards"):
        EvidenceSegmentWriter(
            tmp_path,
            segment_id="segment-1",
            now_utc=lambda: next(clock_values),
        )


def test_default_rotation_policy_is_64_mib_or_one_hour(tmp_path) -> None:
    writer = _writer(tmp_path)

    assert writer.max_segment_bytes == DEFAULT_MAX_SEGMENT_BYTES == 64 * 1024 * 1024
    assert writer.max_segment_age_seconds == DEFAULT_MAX_SEGMENT_AGE_SECONDS == 3600
    writer.close(terminal_reason="empty_test")


def test_segment_close_fsyncs_data_summary_and_directory(tmp_path, monkeypatch) -> None:
    calls: list[int] = []
    real_fsync = __import__("os").fsync

    def recording_fsync(fd: int) -> None:
        calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr("edmn_trader.data.evidence_durability.os.fsync", recording_fsync)
    writer = _writer(tmp_path, checkpoint_every_records=99)
    writer.append(_record(1))

    writer.close(terminal_reason="test_complete")

    assert len(calls) >= 5


def test_partial_tail_recovery_finalizes_old_segment_and_requires_fresh_snapshot(
    tmp_path,
) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)
    writer.append(_record(1))
    writer.checkpoint()
    writer._handle.close()
    complete_tail = _serialized(_record(2))
    partial_tail = b'{"local_row_index":3,"value":'
    with writer.data_path.open("ab") as handle:
        handle.write(complete_tail + partial_tail)

    result = recover_unterminated_segment(
        data_path=writer.data_path,
        checkpoint_path=writer.checkpoint_path,
        summary_path=writer.summary_path,
        segment_id="segment-1",
        next_segment_id="segment-2",
        now_utc=lambda: NOW + timedelta(seconds=10),
        monotonic_ns=lambda: 11_000,
    )

    assert result.terminal_reason == "crash_recovered"
    assert result.last_committed_local_row_index == 2
    assert result.partial_tail_bytes_removed == len(partial_tail)
    assert result.next_segment_id == "segment-2"
    assert result.snapshot_required is True
    assert result.inherited_book_state is False
    assert writer.data_path.read_bytes().endswith(complete_tail)
    summary = json.loads(writer.summary_path.read_text())
    assert summary["closed_file_sha256"] == result.closed_file_sha256
    assert summary["terminal_reason"] == "crash_recovered"
    next_segment = json.loads(Path(result.next_segment_metadata_path).read_text())
    assert next_segment["schema_version"] == EVIDENCE_SEGMENT_START_SCHEMA_VERSION
    assert next_segment["connection_reset_required"] is True
    assert next_segment["snapshot_required"] is True
    assert next_segment["inherited_book_state"] is False


def test_recovery_rejects_malformed_complete_tail_record(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)
    writer.append(_record(1))
    writer.checkpoint()
    writer._handle.close()
    with writer.data_path.open("ab") as handle:
        handle.write(b"not-json\n")

    with pytest.raises(ValueError, match="complete tail record"):
        recover_unterminated_segment(
            data_path=writer.data_path,
            checkpoint_path=writer.checkpoint_path,
            summary_path=writer.summary_path,
            segment_id="segment-1",
            next_segment_id="segment-2",
        )


@pytest.mark.parametrize("invalid_index", [True, 1.0, "1"])
def test_chain_verifier_rejects_non_integer_local_row_index(
    tmp_path,
    invalid_index,
) -> None:
    data_path = tmp_path / "invalid.events.jsonl"
    data_path.write_bytes(
        json.dumps({"local_row_index": invalid_index}, separators=(",", ":")).encode()
        + b"\n"
    )

    with pytest.raises(ValueError, match="local_row_index"):
        verify_segment_chain(data_path, segment_id="segment-1")


def test_recovery_rejects_non_integer_complete_tail_index(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)
    writer.append(_record(1))
    writer.checkpoint()
    writer._handle.close()
    with writer.data_path.open("ab") as handle:
        handle.write(b'{"local_row_index":2.0,"value":"invalid"}\n')

    with pytest.raises(ValueError, match="complete tail record"):
        recover_unterminated_segment(
            data_path=writer.data_path,
            checkpoint_path=writer.checkpoint_path,
            summary_path=writer.summary_path,
            segment_id="segment-1",
            next_segment_id="segment-2",
        )


def test_recovery_rejects_noncanonical_complete_tail_record(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)
    writer.append(_record(1))
    writer.checkpoint()
    writer._handle.close()
    with writer.data_path.open("ab") as handle:
        handle.write(b'{"local_row_index": 2, "value": "noncanonical"}\n')

    with pytest.raises(ValueError, match="complete tail record"):
        recover_unterminated_segment(
            data_path=writer.data_path,
            checkpoint_path=writer.checkpoint_path,
            summary_path=writer.summary_path,
            segment_id="segment-1",
            next_segment_id="segment-2",
        )


def test_recovery_rejects_invalid_genesis_checkpoint_hash(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)
    checkpoint = json.loads(writer.checkpoint_path.read_text())
    checkpoint["chain_hash"] = "0" * 64
    writer.checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    writer._handle.close()

    with pytest.raises(ValueError, match="genesis"):
        recover_unterminated_segment(
            data_path=writer.data_path,
            checkpoint_path=writer.checkpoint_path,
            summary_path=writer.summary_path,
            segment_id="segment-1",
            next_segment_id="segment-2",
        )


def test_recovery_does_not_overwrite_an_existing_next_segment(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=99)
    writer.append(_record(1))
    writer.checkpoint()
    writer._handle.close()
    partial_tail = b'{"local_row_index":2'
    with writer.data_path.open("ab") as handle:
        handle.write(partial_tail)
    next_start = tmp_path / "segment-2.start.json"
    next_start.write_text("preserve", encoding="utf-8")
    before = writer.data_path.read_bytes()

    with pytest.raises(FileExistsError, match="next segment artifacts"):
        recover_unterminated_segment(
            data_path=writer.data_path,
            checkpoint_path=writer.checkpoint_path,
            summary_path=writer.summary_path,
            segment_id="segment-1",
            next_segment_id="segment-2",
        )

    assert writer.data_path.read_bytes() == before
    assert not writer.summary_path.exists()
    assert next_start.read_text(encoding="utf-8") == "preserve"


def test_event_callbacks_do_not_hash_the_full_file(tmp_path) -> None:
    writer = _writer(tmp_path, checkpoint_every_records=10)

    for index in range(1, 101):
        writer.append(_record(index))

    assert writer.full_file_hash_count == 0
    assert writer.append_chain_update_count == 100
    writer.close(terminal_reason="test_complete")
    assert writer.full_file_hash_count == 1


def _writer(
    root,
    *,
    checkpoint_every_records: int = 10,
    max_segment_bytes: int = DEFAULT_MAX_SEGMENT_BYTES,
    max_segment_age_seconds: int = DEFAULT_MAX_SEGMENT_AGE_SECONDS,
    monotonic_ns=None,
) -> EvidenceSegmentWriter:
    return EvidenceSegmentWriter(
        root,
        segment_id="segment-1",
        checkpoint_every_records=checkpoint_every_records,
        max_segment_bytes=max_segment_bytes,
        max_segment_age_seconds=max_segment_age_seconds,
        now_utc=lambda: NOW,
        monotonic_ns=monotonic_ns,
    )


def _record(index: int) -> dict[str, object]:
    return {"local_row_index": index, "value": f"fixture-{index}"}


def _serialized(record: dict[str, object]) -> bytes:
    return (
        json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


class _MonotonicClock:
    def __init__(self) -> None:
        self.value = 1_000_000_000

    def __call__(self) -> int:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += seconds * 1_000_000_000
