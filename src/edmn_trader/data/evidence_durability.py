"""Append-chain durability, atomic checkpoints, and crash recovery."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from edmn_trader.data.payload_safety import validate_no_secret_payload

EVIDENCE_CHAIN_SCHEMA_VERSION = "edmn.evidence.chain.v1"
EVIDENCE_CHECKPOINT_SCHEMA_VERSION = "edmn.evidence.checkpoint.v1"
EVIDENCE_OPEN_STATUS_SCHEMA_VERSION = "edmn.evidence.open_status.v1"
EVIDENCE_SUMMARY_SCHEMA_VERSION = "edmn.evidence.segment_summary.v1"
EVIDENCE_SEGMENT_START_SCHEMA_VERSION = "edmn.evidence.segment_start.v1"
DEFAULT_MAX_SEGMENT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_SEGMENT_AGE_SECONDS = 3_600


class RotationReason(StrEnum):
    BYTE_LIMIT = "BYTE_LIMIT"
    TIME_LIMIT = "TIME_LIMIT"


class BackupVerificationState(StrEnum):
    NOT_VERIFIED = "NOT_VERIFIED"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True, slots=True)
class ChainVerification:
    segment_id: str
    record_count: int
    terminal_chain_hash: str
    byte_offset: int


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    segment_id: str
    last_committed_local_row_index: int
    terminal_chain_hash: str
    closed_file_sha256: str
    partial_tail_bytes_removed: int
    next_segment_id: str
    next_segment_metadata_path: str
    terminal_reason: str = field(init=False, default="crash_recovered")
    snapshot_required: bool = field(init=False, default=True)
    inherited_book_state: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        _validate_segment_id(self.segment_id)
        _validate_segment_id(self.next_segment_id)
        if self.segment_id == self.next_segment_id:
            raise ValueError("recovery must start a new segment")
        _require_nonnegative_int(
            self.last_committed_local_row_index,
            "last_committed_local_row_index",
        )
        _require_nonnegative_int(
            self.partial_tail_bytes_removed,
            "partial_tail_bytes_removed",
        )
        _validate_sha256_digest(self.terminal_chain_hash, "terminal_chain_hash")
        _validate_sha256_digest(self.closed_file_sha256, "closed_file_sha256")
        if not isinstance(self.next_segment_metadata_path, str) or not (
            self.next_segment_metadata_path
        ):
            raise ValueError("next_segment_metadata_path is required")


@dataclass(frozen=True, slots=True)
class RotationResult:
    reason: RotationReason
    closed_summary: Mapping[str, object]
    next_writer: EvidenceSegmentWriter


class EvidenceSegmentWriter:
    """Stream exact JSONL bytes while maintaining O(1) append-chain state."""

    def __init__(
        self,
        root: Path,
        *,
        segment_id: str,
        checkpoint_every_records: int = 1_000,
        max_segment_bytes: int = DEFAULT_MAX_SEGMENT_BYTES,
        max_segment_age_seconds: int = DEFAULT_MAX_SEGMENT_AGE_SECONDS,
        now_utc: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        _validate_segment_id(segment_id)
        for name, value in (
            ("checkpoint_every_records", checkpoint_every_records),
            ("max_segment_bytes", max_segment_bytes),
            ("max_segment_age_seconds", max_segment_age_seconds),
        ):
            _require_positive_int(value, name)
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.segment_id = segment_id
        self.checkpoint_every_records = checkpoint_every_records
        self.max_segment_bytes = max_segment_bytes
        self.max_segment_age_seconds = max_segment_age_seconds
        self._now_utc = now_utc or (lambda: datetime.now(UTC))
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self.created_at_utc = self._aware_now()
        self.created_monotonic_ns = self._monotonic_now()
        self.data_path = self.root / f"{segment_id}.events.jsonl"
        self.checkpoint_path = self.root / f"{segment_id}.checkpoint.json"
        self.summary_path = self.root / f"{segment_id}.summary.json"
        _require_available_artifacts(
            (self.data_path, self.checkpoint_path, self.summary_path),
            label="segment artifacts",
        )
        self._handle = self.data_path.open("xb")
        self._chain_hash = chain_genesis_hash(segment_id)
        self._last_local_row_index = 0
        self._byte_offset = 0
        self._checkpointed_local_row_index = 0
        self._checkpointed_byte_offset = 0
        self._checkpointed_chain_hash = self._chain_hash
        self._closed = False
        self._full_file_hash_count = 0
        self._append_chain_update_count = 0
        self._checkpoint_durations_seconds: list[float] = []
        try:
            self.checkpoint()
        except BaseException:
            self._handle.close()
            raise

    @property
    def full_file_hash_count(self) -> int:
        return self._full_file_hash_count

    @property
    def append_chain_update_count(self) -> int:
        return self._append_chain_update_count

    @property
    def checkpoint_durations_seconds(self) -> tuple[float, ...]:
        return tuple(self._checkpoint_durations_seconds)

    def append(self, record: Mapping[str, Any]) -> str:
        self._require_open()
        local_row_index = record.get("local_row_index")
        expected_index = self._last_local_row_index + 1
        if (
            not isinstance(local_row_index, int)
            or isinstance(local_row_index, bool)
            or local_row_index != expected_index
        ):
            raise ValueError(f"local_row_index must equal {expected_index}")
        record_bytes = serialize_record_bytes(record)
        self._handle.write(record_bytes)
        self._chain_hash = compute_chain_hash(self._chain_hash, record_bytes)
        self._last_local_row_index = local_row_index
        self._byte_offset += len(record_bytes)
        self._append_chain_update_count += 1
        if local_row_index % self.checkpoint_every_records == 0:
            self.checkpoint()
        return self._chain_hash

    def checkpoint(self) -> dict[str, object]:
        self._require_open()
        started = time.perf_counter()
        self._handle.flush()
        os.fsync(self._handle.fileno())
        checkpoint = _checkpoint_record(
            segment_id=self.segment_id,
            created_at_utc=self.created_at_utc,
            local_row_index=self._last_local_row_index,
            byte_offset=self._byte_offset,
            chain_hash=self._chain_hash,
            checkpoint_at_utc=self._aware_now(),
            checkpoint_monotonic_ns=self._monotonic_now(),
        )
        _atomic_write_json(self.checkpoint_path, checkpoint)
        self._checkpointed_local_row_index = self._last_local_row_index
        self._checkpointed_byte_offset = self._byte_offset
        self._checkpointed_chain_hash = self._chain_hash
        self._checkpoint_durations_seconds.append(time.perf_counter() - started)
        return checkpoint

    def rotation_reason(self) -> RotationReason | None:
        self._require_open()
        if self._byte_offset >= self.max_segment_bytes:
            return RotationReason.BYTE_LIMIT
        age_ns = self._monotonic_now() - self.created_monotonic_ns
        if age_ns >= self.max_segment_age_seconds * 1_000_000_000:
            return RotationReason.TIME_LIMIT
        return None

    def status_record(self) -> dict[str, object]:
        self._require_open()
        return {
            "schema_version": EVIDENCE_OPEN_STATUS_SCHEMA_VERSION,
            "segment_id": self.segment_id,
            "segment_closed": False,
            "integrity_scope": "CHECKPOINT_BOUNDED",
            "last_committed_local_row_index": self._checkpointed_local_row_index,
            "byte_offset": self._checkpointed_byte_offset,
            "chain_hash": self._checkpointed_chain_hash,
            "closed_file_sha256": None,
            "backup_verification_state": BackupVerificationState.NOT_VERIFIED,
            "retention_deletion_eligible": False,
        }

    def rotate_if_needed(self, *, next_segment_id: str) -> RotationResult | None:
        reason = self.rotation_reason()
        if reason is None:
            return None
        _validate_segment_id(next_segment_id)
        if next_segment_id == self.segment_id:
            raise ValueError("rotation requires a new segment_id")
        _require_available_artifacts(
            (
                self.root / f"{next_segment_id}.events.jsonl",
                self.root / f"{next_segment_id}.checkpoint.json",
                self.root / f"{next_segment_id}.summary.json",
            ),
            label="next segment artifacts",
        )
        summary = self.close(terminal_reason="rotation", rotation_reason=reason)
        next_writer = EvidenceSegmentWriter(
            self.root,
            segment_id=next_segment_id,
            checkpoint_every_records=self.checkpoint_every_records,
            max_segment_bytes=self.max_segment_bytes,
            max_segment_age_seconds=self.max_segment_age_seconds,
            now_utc=self._now_utc,
            monotonic_ns=self._monotonic_ns,
        )
        return RotationResult(reason, summary, next_writer)

    def close(
        self,
        *,
        terminal_reason: str,
        rotation_reason: RotationReason | None = None,
    ) -> dict[str, object]:
        self._require_open()
        if not isinstance(terminal_reason, str) or not terminal_reason:
            raise ValueError("terminal_reason must be a non-empty string")
        if rotation_reason is not None:
            rotation_reason = RotationReason(rotation_reason)
        if (terminal_reason == "rotation") != (rotation_reason is not None):
            raise ValueError(
                "rotation_reason is required exactly when terminal_reason is rotation"
            )
        checkpoint = self.checkpoint()
        self._handle.close()
        closed_at = self._aware_now()
        closed_file_sha256 = self._hash_closed_file()
        summary = {
            "schema_version": EVIDENCE_SUMMARY_SCHEMA_VERSION,
            "segment_id": self.segment_id,
            "segment_created": True,
            "segment_closed": True,
            "created_at_utc": self.created_at_utc.isoformat(),
            "closed_at_utc": closed_at.isoformat(),
            "terminal_reason": terminal_reason,
            "rotation_reason": rotation_reason,
            "integrity_scope": "CLOSED_FILE",
            "last_committed_local_row_index": checkpoint[
                "last_committed_local_row_index"
            ],
            "byte_offset": checkpoint["byte_offset"],
            "genesis_hash": chain_genesis_hash(self.segment_id),
            "terminal_chain_hash": checkpoint["chain_hash"],
            "closed_file_sha256": closed_file_sha256,
            "backup_verification_state": BackupVerificationState.NOT_VERIFIED,
            "retention_deletion_eligible": False,
        }
        _atomic_write_json(self.summary_path, summary)
        self._closed = True
        return summary

    def _hash_closed_file(self) -> str:
        self._full_file_hash_count += 1
        return _file_sha256(self.data_path)

    def _aware_now(self) -> datetime:
        value = self._now_utc()
        _require_aware(value, "now_utc")
        value = value.astimezone(UTC)
        previous = getattr(self, "_last_recorded_at_utc", None)
        if previous is not None and value < previous:
            raise ValueError("UTC evidence clock must not move backwards")
        self._last_recorded_at_utc = value
        return value

    def _monotonic_now(self) -> int:
        value = _require_nonnegative_int(self._monotonic_ns(), "monotonic_ns")
        previous = getattr(self, "_last_monotonic_ns", None)
        if previous is not None and value < previous:
            raise ValueError("monotonic evidence clock must not move backwards")
        self._last_monotonic_ns = value
        return value

    def _require_open(self) -> None:
        if self._closed or self._handle.closed:
            raise RuntimeError("evidence segment is closed")


def chain_genesis_hash(segment_id: str) -> str:
    _validate_segment_id(segment_id)
    payload = f"{EVIDENCE_CHAIN_SCHEMA_VERSION}:{segment_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def compute_chain_hash(previous_hash: str, record_bytes: bytes) -> str:
    if len(previous_hash) != 64:
        raise ValueError("previous_hash must be a SHA-256 hex digest")
    try:
        previous = bytes.fromhex(previous_hash)
    except ValueError as exc:
        raise ValueError("previous_hash must be a SHA-256 hex digest") from exc
    return hashlib.sha256(
        previous + struct.pack(">Q", len(record_bytes)) + record_bytes
    ).hexdigest()


def serialize_record_bytes(record: Mapping[str, Any]) -> bytes:
    validate_no_secret_payload(record)
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


def verify_segment_chain(data_path: Path, *, segment_id: str) -> ChainVerification:
    chain_hash = chain_genesis_hash(segment_id)
    record_count = 0
    byte_offset = 0
    with Path(data_path).open("rb") as handle:
        for line in handle:
            if not line.endswith(b"\n"):
                raise ValueError("segment contains a partial final record")
            record_count += 1
            _validate_serialized_record(line, record_count)
            chain_hash = compute_chain_hash(chain_hash, line)
            byte_offset += len(line)
    return ChainVerification(segment_id, record_count, chain_hash, byte_offset)


def recover_unterminated_segment(
    *,
    data_path: Path,
    checkpoint_path: Path,
    summary_path: Path,
    segment_id: str,
    next_segment_id: str,
    now_utc: Callable[[], datetime] | None = None,
    monotonic_ns: Callable[[], int] | None = None,
) -> RecoveryResult:
    _validate_segment_id(segment_id)
    _validate_segment_id(next_segment_id)
    if segment_id == next_segment_id:
        raise ValueError("recovery must start a new segment")
    data_path = Path(data_path)
    checkpoint_path = Path(checkpoint_path)
    summary_path = Path(summary_path)
    if _artifact_exists(summary_path):
        raise ValueError("segment is already finalized")
    if not data_path.is_file():
        raise ValueError("unterminated segment data file is missing")
    next_segment_path = data_path.parent / f"{next_segment_id}.start.json"
    _require_available_artifacts(
        (
            data_path.parent / f"{next_segment_id}.events.jsonl",
            data_path.parent / f"{next_segment_id}.checkpoint.json",
            data_path.parent / f"{next_segment_id}.summary.json",
            next_segment_path,
        ),
        label="next segment artifacts",
    )
    clock = now_utc or (lambda: datetime.now(UTC))
    mono = monotonic_ns or time.monotonic_ns
    recovered_at = clock()
    _require_aware(recovered_at, "now_utc")
    recovered_at = recovered_at.astimezone(UTC)
    checkpoint = _load_checkpoint(checkpoint_path, segment_id)
    checkpoint_at = _parse_utc(str(checkpoint["checkpoint_utc_timestamp"]))
    if recovered_at < checkpoint_at:
        raise ValueError("recovery timestamp precedes the persisted checkpoint")
    local_row_index = int(checkpoint["last_committed_local_row_index"])
    byte_offset = int(checkpoint["byte_offset"])
    chain_hash = str(checkpoint["chain_hash"])
    file_size = data_path.stat().st_size
    if byte_offset < 0 or byte_offset > file_size:
        raise ValueError("checkpoint byte offset is outside the segment")
    partial_tail_bytes_removed = 0
    with data_path.open("r+b") as handle:
        if byte_offset:
            handle.seek(byte_offset - 1)
            if handle.read(1) != b"\n":
                raise ValueError("checkpoint byte offset is not a record boundary")
        handle.seek(byte_offset)
        while True:
            record_offset = handle.tell()
            line = handle.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                partial_tail_bytes_removed = len(line)
                handle.seek(record_offset)
                handle.truncate()
                byte_offset = record_offset
                handle.flush()
                os.fsync(handle.fileno())
                break
            expected_index = local_row_index + 1
            try:
                _validate_serialized_record(line, expected_index)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError("complete tail record is invalid") from exc
            chain_hash = compute_chain_hash(chain_hash, line)
            local_row_index = expected_index
            byte_offset += len(line)
        handle.flush()
        os.fsync(handle.fileno())
    checkpoint_record = _checkpoint_record(
        segment_id=segment_id,
        created_at_utc=_parse_utc(str(checkpoint["segment_created_at_utc"])),
        local_row_index=local_row_index,
        byte_offset=byte_offset,
        chain_hash=chain_hash,
        checkpoint_at_utc=recovered_at,
        checkpoint_monotonic_ns=_require_nonnegative_int(mono(), "monotonic_ns"),
    )
    _atomic_write_json(checkpoint_path, checkpoint_record)
    closed_file_sha256 = _file_sha256(data_path)
    summary = {
        "schema_version": EVIDENCE_SUMMARY_SCHEMA_VERSION,
        "segment_id": segment_id,
        "segment_created": True,
        "segment_closed": True,
        "created_at_utc": checkpoint["segment_created_at_utc"],
        "closed_at_utc": recovered_at.isoformat(),
        "terminal_reason": "crash_recovered",
        "rotation_reason": None,
        "integrity_scope": "CLOSED_FILE",
        "last_committed_local_row_index": local_row_index,
        "byte_offset": byte_offset,
        "genesis_hash": chain_genesis_hash(segment_id),
        "terminal_chain_hash": chain_hash,
        "closed_file_sha256": closed_file_sha256,
        "partial_tail_bytes_removed": partial_tail_bytes_removed,
        "backup_verification_state": BackupVerificationState.NOT_VERIFIED,
        "retention_deletion_eligible": False,
    }
    _atomic_write_json(summary_path, summary)
    _atomic_write_json(
        next_segment_path,
        {
            "schema_version": EVIDENCE_SEGMENT_START_SCHEMA_VERSION,
            "segment_id": next_segment_id,
            "previous_segment_id": segment_id,
            "segment_created": True,
            "connection_reset_required": True,
            "snapshot_required": True,
            "inherited_book_state": False,
            "created_at_utc": recovered_at.isoformat(),
        },
    )
    return RecoveryResult(
        segment_id=segment_id,
        last_committed_local_row_index=local_row_index,
        terminal_chain_hash=chain_hash,
        closed_file_sha256=closed_file_sha256,
        partial_tail_bytes_removed=partial_tail_bytes_removed,
        next_segment_id=next_segment_id,
        next_segment_metadata_path=str(next_segment_path),
    )


def _checkpoint_record(
    *,
    segment_id: str,
    created_at_utc: datetime,
    local_row_index: int,
    byte_offset: int,
    chain_hash: str,
    checkpoint_at_utc: datetime,
    checkpoint_monotonic_ns: int,
) -> dict[str, object]:
    return {
        "schema_version": EVIDENCE_CHECKPOINT_SCHEMA_VERSION,
        "segment_id": segment_id,
        "segment_created_at_utc": created_at_utc.isoformat(),
        "last_committed_local_row_index": local_row_index,
        "byte_offset": byte_offset,
        "chain_hash": chain_hash,
        "checkpoint_utc_timestamp": checkpoint_at_utc.isoformat(),
        "checkpoint_monotonic_timestamp": checkpoint_monotonic_ns,
    }


def _load_checkpoint(path: Path, segment_id: str) -> Mapping[str, object]:
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("valid atomic checkpoint is required for recovery") from exc
    if not isinstance(checkpoint, Mapping):
        raise ValueError("valid atomic checkpoint is required for recovery")
    if (
        checkpoint.get("schema_version") != EVIDENCE_CHECKPOINT_SCHEMA_VERSION
        or checkpoint.get("segment_id") != segment_id
        or not isinstance(checkpoint.get("last_committed_local_row_index"), int)
        or isinstance(checkpoint.get("last_committed_local_row_index"), bool)
        or not isinstance(checkpoint.get("byte_offset"), int)
        or isinstance(checkpoint.get("byte_offset"), bool)
        or not isinstance(checkpoint.get("chain_hash"), str)
        or not isinstance(checkpoint.get("segment_created_at_utc"), str)
        or not isinstance(checkpoint.get("checkpoint_utc_timestamp"), str)
        or not isinstance(checkpoint.get("checkpoint_monotonic_timestamp"), int)
        or isinstance(checkpoint.get("checkpoint_monotonic_timestamp"), bool)
    ):
        raise ValueError("checkpoint contract is invalid")
    if (
        int(checkpoint["last_committed_local_row_index"]) < 0
        or int(checkpoint["byte_offset"]) < 0
        or int(checkpoint["checkpoint_monotonic_timestamp"]) < 0
    ):
        raise ValueError("checkpoint numeric fields must be non-negative")
    created_at = _parse_utc(str(checkpoint["segment_created_at_utc"]))
    checkpoint_at = _parse_utc(str(checkpoint["checkpoint_utc_timestamp"]))
    if checkpoint_at < created_at:
        raise ValueError("checkpoint timestamp precedes segment creation")
    compute_chain_hash(str(checkpoint["chain_hash"]), b"")
    local_row_index = int(checkpoint["last_committed_local_row_index"])
    byte_offset = int(checkpoint["byte_offset"])
    if (local_row_index == 0) != (byte_offset == 0):
        raise ValueError("checkpoint row and byte offset are inconsistent")
    if local_row_index == 0 and checkpoint["chain_hash"] != chain_genesis_hash(segment_id):
        raise ValueError("genesis checkpoint hash is invalid")
    return checkpoint


def _validate_serialized_record(record_bytes: bytes, expected_index: int) -> None:
    record = json.loads(record_bytes.decode("utf-8"))
    if not isinstance(record, Mapping):
        raise ValueError("serialized evidence record must be an object")
    local_row_index = record.get("local_row_index")
    if (
        not isinstance(local_row_index, int)
        or isinstance(local_row_index, bool)
        or local_row_index != expected_index
    ):
        raise ValueError("serialized evidence local_row_index is not contiguous")
    if serialize_record_bytes(record) != record_bytes:
        raise ValueError("serialized evidence record is not canonical JSONL")


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    validate_no_secret_payload(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    _require_aware(parsed, "segment_created_at_utc")
    return parsed


def _validate_segment_id(segment_id: str) -> None:
    if not isinstance(segment_id, str) or not segment_id or any(
        character in segment_id for character in ("/", "\\", "\x00")
    ):
        raise ValueError("segment_id must be a safe filename component")


def _validate_sha256_digest(value: object, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a SHA-256 hex digest") from exc


def _artifact_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _require_available_artifacts(
    paths: tuple[Path, ...],
    *,
    label: str,
) -> None:
    if any(_artifact_exists(path) for path in paths):
        raise FileExistsError(f"{label} already exist")


def _require_positive_int(value: object, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_nonnegative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
