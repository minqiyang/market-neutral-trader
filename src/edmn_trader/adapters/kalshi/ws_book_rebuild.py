"""Deterministic native Kalshi WebSocket orderbook rebuilds."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import Any

from edmn_trader.adapters.kalshi.ws_events import (
    AdmissionStatus,
    ExclusionReason,
    KalshiWsRawEvent,
    KalshiWsSchemaCompatibilityError,
    LegacyKalshiWsRawEvent,
    SequenceState,
    parse_kalshi_ws_raw_record,
    payload_sha256,
)
from edmn_trader.data.payload_safety import validate_no_secret_payload

D2B_FRAME_SCHEMA_VERSION = "edmn.kalshi.ws.book.frame.v2"
D2B_STATE_SCHEMA_VERSION = "edmn.kalshi.ws.book.state.v2"
ZERO = Decimal("0")
ONE = Decimal("1")


class PricingMode(StrEnum):
    LEGACY_SIDE_PRICE = "LEGACY_SIDE_PRICE"
    UNIFIED_YES_PRICE = "UNIFIED_YES_PRICE"


class PricingModeSource(StrEnum):
    D2A_SUBSCRIPTION_METADATA = "D2A_SUBSCRIPTION_METADATA"
    RECORDER_EXPLICIT_SUBSCRIPTION = "RECORDER_EXPLICIT_SUBSCRIPTION"
    RECORDER_DEFAULT_ASSUMPTION = "RECORDER_DEFAULT_ASSUMPTION"


class SegmentValidity(StrEnum):
    AWAITING_SNAPSHOT = "AWAITING_SNAPSHOT"
    VALID = "VALID"
    INVALID = "INVALID"


class CanonicalBookState(StrEnum):
    EMPTY = "EMPTY"
    YES_BIDS_ONLY = "YES_BIDS_ONLY"
    YES_ASKS_ONLY = "YES_ASKS_ONLY"
    TWO_SIDED = "TWO_SIDED"
    LOCKED = "LOCKED"
    CROSSED = "CROSSED"


class SnapshotResetReason(StrEnum):
    INITIAL_SNAPSHOT = "INITIAL_SNAPSHOT"
    RESNAPSHOT_SAME_SEGMENT = "RESNAPSHOT_SAME_SEGMENT"
    RECOVERY_AFTER_INVALIDATION = "RECOVERY_AFTER_INVALIDATION"


class SnapshotSidePresence(StrEnum):
    PRESENT_NONEMPTY = "PRESENT_NONEMPTY"
    PRESENT_EMPTY = "PRESENT_EMPTY"
    OMITTED_CONFIRMED_EMPTY = "OMITTED_CONFIRMED_EMPTY"
    ABSENT_UNVERIFIED = "ABSENT_UNVERIFIED"
    NULL_INVALID = "NULL_INVALID"
    WRONG_TYPE_INVALID = "WRONG_TYPE_INVALID"
    MALFORMED_LEVEL_INVALID = "MALFORMED_LEVEL_INVALID"


class RebuildDisposition(StrEnum):
    FRAME_EMITTED = "FRAME_EMITTED"
    IGNORED_NON_ORDERBOOK = "IGNORED_NON_ORDERBOOK"
    EXCLUDED = "EXCLUDED"
    QUARANTINED = "QUARANTINED"


class RebuildReason(StrEnum):
    D2A_ROW_EXCLUDED = "D2A_ROW_EXCLUDED"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    LEGACY_IDENTITY_UNPROVEN = "LEGACY_IDENTITY_UNPROVEN"
    MALFORMED_D2A_ENVELOPE = "MALFORMED_D2A_ENVELOPE"
    SECRET_LIKE_RECORD = "SECRET_LIKE_RECORD"
    MISSING_IDENTITY = "MISSING_IDENTITY"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNKNOWN_PRICING_MODE = "UNKNOWN_PRICING_MODE"
    CONTRADICTORY_PRICING_MODE = "CONTRADICTORY_PRICING_MODE"
    MALFORMED_SNAPSHOT = "MALFORMED_SNAPSHOT"
    SNAPSHOT_BOTH_SIDES_OMITTED = "SNAPSHOT_BOTH_SIDES_OMITTED"
    SNAPSHOT_NULL_SIDE = "SNAPSHOT_NULL_SIDE"
    SNAPSHOT_WRONG_SIDE_TYPE = "SNAPSHOT_WRONG_SIDE_TYPE"
    DUPLICATE_SNAPSHOT_PRICE = "DUPLICATE_SNAPSHOT_PRICE"
    IMPOSSIBLE_PRICE = "IMPOSSIBLE_PRICE"
    DELTA_BEFORE_SNAPSHOT = "DELTA_BEFORE_SNAPSHOT"
    MALFORMED_DELTA = "MALFORMED_DELTA"
    NEGATIVE_RESULTING_QUANTITY = "NEGATIVE_RESULTING_QUANTITY"
    SEGMENT_INVALID = "SEGMENT_INVALID"


@dataclass(frozen=True, slots=True)
class NativeBookKey:
    market_ticker: str
    connection_id: str
    segment_id: str


@dataclass(frozen=True, slots=True)
class NativeLevel:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class CanonicalLevel:
    price: Decimal
    quantity: Decimal
    native_side: str
    native_reported_price: Decimal


@dataclass(slots=True)
class NativeBookState:
    market_ticker: str
    connection_id: str
    segment_id: str
    pricing_mode: PricingMode
    pricing_mode_source: PricingModeSource
    pricing_mode_assumption: str | None
    market_id: str | None = None
    subscription_id: str | int | None = None
    subscription_sid: str | int | None = None
    snapshot_yes_presence: SnapshotSidePresence = SnapshotSidePresence.ABSENT_UNVERIFIED
    snapshot_no_presence: SnapshotSidePresence = SnapshotSidePresence.ABSENT_UNVERIFIED
    snapshot_received: bool = False
    native_yes_bids: dict[Decimal, Decimal] = field(default_factory=dict)
    native_no_bids: dict[Decimal, Decimal] = field(default_factory=dict)
    last_local_row_index: int | None = None
    last_native_seq: str | int | None = None
    sequence_state: SequenceState = SequenceState.SEQUENCE_NOT_OBSERVED
    segment_validity: SegmentValidity = SegmentValidity.AWAITING_SNAPSHOT
    invalidation_reason: RebuildReason | None = None
    frame_count: int = 0
    schema_version: str = D2B_STATE_SCHEMA_VERSION

    @property
    def key(self) -> NativeBookKey:
        return NativeBookKey(self.market_ticker, self.connection_id, self.segment_id)


@dataclass(frozen=True, slots=True)
class KalshiWsBookFrame:
    market_ticker: str
    market_id: str | None
    connection_id: str
    segment_id: str
    subscription_id: str | int | None
    subscription_sid: str | int | None
    local_row_index: int
    native_seq: str | int | None
    sequence_state: SequenceState
    pricing_mode: PricingMode
    pricing_mode_source: PricingModeSource
    pricing_mode_assumption: str | None
    snapshot_yes_presence: SnapshotSidePresence
    snapshot_no_presence: SnapshotSidePresence
    snapshot_received: bool
    native_yes_bids: tuple[NativeLevel, ...]
    native_no_bids: tuple[NativeLevel, ...]
    canonical_yes_bids: tuple[CanonicalLevel, ...]
    canonical_yes_asks: tuple[CanonicalLevel, ...]
    book_state: CanonicalBookState
    segment_validity: SegmentValidity
    invalidation_reason: RebuildReason | None
    reset_reason: SnapshotResetReason | None
    frame_count: int
    frame_hash: str
    terminal_state_hash: str
    schema_version: str = D2B_FRAME_SCHEMA_VERSION

    def to_record(self) -> dict[str, object]:
        return {
            **_frame_hash_record(self),
            "frame_hash": self.frame_hash,
            "terminal_state_hash": self.terminal_state_hash,
        }


@dataclass(frozen=True, slots=True)
class RebuildResult:
    disposition: RebuildDisposition
    reason: RebuildReason | None
    key: NativeBookKey | None = None
    frame: KalshiWsBookFrame | None = None
    quarantined_record: Mapping[str, Any] | None = None


@dataclass(slots=True)
class _ChannelSubscriptionIdentity:
    request_id: str | int | None = None
    command_id: str | int | None = None
    sid: str | int | None = None
    binding_id: str | None = None
    market_tickers: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _ChannelSubscriptionRegistry:
    identities: dict[str, _ChannelSubscriptionIdentity] = field(default_factory=dict)

    def observe(self, event: KalshiWsRawEvent) -> RebuildReason | None:
        identity = self.identities.setdefault(event.channel, _ChannelSubscriptionIdentity())
        for field_name, observed in (
            ("request_id", event.subscription_id),
            ("command_id", event.subscription_command_id),
            ("sid", event.subscription_sid),
            ("binding_id", event.subscription_binding_id),
        ):
            current = getattr(identity, field_name)
            if current is not None and observed is not None and current != observed:
                return RebuildReason.IDENTITY_MISMATCH
            if current is None and observed is not None:
                setattr(identity, field_name, observed)
        if event.native_market_ticker is not None:
            identity.market_tickers.add(event.native_market_ticker)
        return None

    def identity_for(self, channel: str) -> _ChannelSubscriptionIdentity:
        return self.identities.setdefault(channel, _ChannelSubscriptionIdentity())


@dataclass(slots=True)
class _SegmentMetadata:
    pricing_mode: PricingMode | None = None
    pricing_mode_source: PricingModeSource | None = None
    subscriptions: _ChannelSubscriptionRegistry = field(
        default_factory=_ChannelSubscriptionRegistry
    )
    market_tickers: set[str] = field(default_factory=set)
    market_ids: dict[str, str] = field(default_factory=dict)
    invalidation_reason: RebuildReason | None = None


class _RebuildFailure(ValueError):
    def __init__(self, reason: RebuildReason) -> None:
        self.reason = reason
        super().__init__(reason)


class KalshiWsBookRebuilder:
    """Apply D2A envelopes to independent native book states."""

    def __init__(
        self,
        *,
        explicit_pricing_mode: PricingMode | None = None,
    ) -> None:
        self._states: dict[NativeBookKey, NativeBookState] = {}
        self._segment_metadata: dict[tuple[str, str], _SegmentMetadata] = {}
        self._explicit_pricing_mode = (
            PricingMode(explicit_pricing_mode) if explicit_pricing_mode is not None else None
        )

    def apply(self, record: Mapping[str, Any] | KalshiWsRawEvent) -> RebuildResult:
        parsed = self._parse_record(record)
        if isinstance(parsed, RebuildResult):
            return parsed
        if isinstance(parsed, LegacyKalshiWsRawEvent):
            return RebuildResult(
                disposition=RebuildDisposition.QUARANTINED,
                reason=RebuildReason.LEGACY_IDENTITY_UNPROVEN,
                quarantined_record=_record_copy(record),
            )
        event = parsed
        is_orderbook = event.native_type in {"orderbook_snapshot", "orderbook_delta"}
        key = _event_key(event) if is_orderbook else None
        is_control = event.native_type in {
            "subscribed",
            "ack",
            "ok",
            "error",
            "rejected",
        }
        is_unscoped_control = is_control and event.channel == event.native_type
        if (
            not is_orderbook
            and event.channel != "orderbook_delta"
            and not is_unscoped_control
        ):
            return RebuildResult(
                disposition=RebuildDisposition.IGNORED_NON_ORDERBOOK,
                reason=None,
            )
        if is_orderbook and (
            event.admission_status is not AdmissionStatus.ADMITTED
            or event.exclusion_reason is not None
        ):
            if (
                event.exclusion_reason
                is ExclusionReason.SUBSCRIPTION_IDENTITY_MISMATCH
            ):
                return RebuildResult(
                    disposition=RebuildDisposition.QUARANTINED,
                    reason=RebuildReason.IDENTITY_MISMATCH,
                    key=key,
                    quarantined_record=event.to_record(),
                )
            return RebuildResult(
                disposition=RebuildDisposition.EXCLUDED,
                reason=RebuildReason.D2A_ROW_EXCLUDED,
                key=key,
            )
        if not is_orderbook and not is_control:
            return RebuildResult(
                disposition=RebuildDisposition.IGNORED_NON_ORDERBOOK,
                reason=None,
            )
        metadata_reason = self._observe_segment_metadata(event)
        if metadata_reason is not None:
            self._invalidate_segment_states(event, metadata_reason)
            if key is not None:
                state = self._states.get(key) or self._state_for_event(event, key)
                _invalidate(state, event, metadata_reason)
            return RebuildResult(
                disposition=RebuildDisposition.QUARANTINED,
                reason=metadata_reason,
                key=key,
                quarantined_record=event.to_record(),
            )
        if not is_orderbook:
            binding_reason = self._reconcile_segment_states(event)
            if binding_reason is not None:
                return RebuildResult(
                    disposition=RebuildDisposition.QUARANTINED,
                    reason=binding_reason,
                    quarantined_record=event.to_record(),
                )
            return RebuildResult(
                disposition=RebuildDisposition.IGNORED_NON_ORDERBOOK,
                reason=None,
            )
        if key is None:
            return RebuildResult(
                disposition=RebuildDisposition.QUARANTINED,
                reason=RebuildReason.MISSING_IDENTITY,
                quarantined_record=event.to_record(),
            )
        state = self._state_for_event(event, key)
        binding_reason = self._validate_state_binding(state, event)
        if binding_reason is not None:
            _invalidate(state, event, binding_reason)
            return RebuildResult(
                disposition=RebuildDisposition.QUARANTINED,
                reason=binding_reason,
                key=key,
            )
        if event.native_type == "orderbook_snapshot":
            return self._apply_snapshot(state, event)
        return self._apply_delta(state, event)

    def _segment_states(self, event: KalshiWsRawEvent) -> list[NativeBookState]:
        return [
            state
            for state in self._states.values()
            if state.connection_id == event.connection_id
            and state.segment_id == event.segment_id
        ]

    def _invalidate_segment_states(
        self,
        event: KalshiWsRawEvent,
        reason: RebuildReason,
    ) -> None:
        for state in self._segment_states(event):
            _invalidate(state, event, reason)

    def _reconcile_segment_states(
        self,
        event: KalshiWsRawEvent,
    ) -> RebuildReason | None:
        states = self._segment_states(event)
        for state in states:
            if (reason := self._validate_state_binding(state, event)) is not None:
                metadata = self._segment_metadata[(event.connection_id, event.segment_id)]
                metadata.invalidation_reason = reason
                self._invalidate_segment_states(event, reason)
                return reason
        return None

    def state_for(
        self,
        market_ticker: str | None,
        connection_id: str,
        segment_id: str,
    ) -> NativeBookState | None:
        if market_ticker is None:
            return None
        return self._states.get(NativeBookKey(market_ticker, connection_id, segment_id))

    def terminal_state_hash(
        self,
        market_ticker: str,
        connection_id: str,
        segment_id: str,
    ) -> str | None:
        state = self.state_for(market_ticker, connection_id, segment_id)
        return _semantic_hash(_state_hash_record(state)) if state is not None else None

    def _parse_record(
        self,
        record: Mapping[str, Any] | KalshiWsRawEvent,
    ) -> KalshiWsRawEvent | LegacyKalshiWsRawEvent | RebuildResult:
        if isinstance(record, KalshiWsRawEvent):
            return record
        try:
            validate_no_secret_payload(record, path="raw_record")
        except ValueError:
            return RebuildResult(
                disposition=RebuildDisposition.QUARANTINED,
                reason=RebuildReason.SECRET_LIKE_RECORD,
            )
        try:
            return parse_kalshi_ws_raw_record(record)
        except KalshiWsSchemaCompatibilityError:
            return RebuildResult(
                disposition=RebuildDisposition.QUARANTINED,
                reason=RebuildReason.UNSUPPORTED_SCHEMA,
                quarantined_record=deepcopy(dict(record)),
            )
        except (TypeError, ValueError):
            return RebuildResult(
                disposition=RebuildDisposition.QUARANTINED,
                reason=RebuildReason.MALFORMED_D2A_ENVELOPE,
                quarantined_record=deepcopy(dict(record)),
            )

    def _observe_segment_metadata(self, event: KalshiWsRawEvent) -> RebuildReason | None:
        key = (event.connection_id, event.segment_id)
        metadata = self._segment_metadata.setdefault(
            key,
            _SegmentMetadata(
                pricing_mode=self._explicit_pricing_mode,
                pricing_mode_source=(
                    PricingModeSource.RECORDER_EXPLICIT_SUBSCRIPTION
                    if self._explicit_pricing_mode is not None
                    else None
                ),
            ),
        )
        if metadata.invalidation_reason is not None:
            return metadata.invalidation_reason
        if (identity_reason := metadata.subscriptions.observe(event)) is not None:
            metadata.invalidation_reason = identity_reason
            return metadata.invalidation_reason
        observed_market = event.native_market_ticker
        if observed_market is not None and observed_market not in event.requested_market_tickers:
            metadata.invalidation_reason = RebuildReason.IDENTITY_MISMATCH
            return metadata.invalidation_reason
        if observed_market is not None:
            metadata.market_tickers.add(observed_market)
            observed_market_id = event.native_market_id
            if observed_market_id is not None:
                current_market_id = metadata.market_ids.get(observed_market)
                if current_market_id is not None and current_market_id != observed_market_id:
                    metadata.invalidation_reason = RebuildReason.IDENTITY_MISMATCH
                    return metadata.invalidation_reason
                metadata.market_ids.setdefault(observed_market, observed_market_id)
        pricing_values = _pricing_values(event.original_payload)
        if not pricing_values:
            return None
        if not all(isinstance(value, bool) for value in pricing_values):
            metadata.invalidation_reason = RebuildReason.UNKNOWN_PRICING_MODE
            return metadata.invalidation_reason
        if len(set(pricing_values)) != 1:
            metadata.invalidation_reason = RebuildReason.CONTRADICTORY_PRICING_MODE
            return metadata.invalidation_reason
        mode = (
            PricingMode.UNIFIED_YES_PRICE
            if pricing_values[0]
            else PricingMode.LEGACY_SIDE_PRICE
        )
        if metadata.pricing_mode is not None and metadata.pricing_mode is not mode:
            metadata.invalidation_reason = RebuildReason.CONTRADICTORY_PRICING_MODE
            return metadata.invalidation_reason
        metadata.pricing_mode = mode
        metadata.pricing_mode_source = PricingModeSource.D2A_SUBSCRIPTION_METADATA
        return None

    def _state_for_event(
        self,
        event: KalshiWsRawEvent,
        key: NativeBookKey,
    ) -> NativeBookState:
        state = self._states.get(key)
        metadata = self._segment_metadata[(event.connection_id, event.segment_id)]
        mode = metadata.pricing_mode or PricingMode.LEGACY_SIDE_PRICE
        source = metadata.pricing_mode_source or PricingModeSource.RECORDER_DEFAULT_ASSUMPTION
        if state is None:
            orderbook_identity = metadata.subscriptions.identity_for("orderbook_delta")
            state = NativeBookState(
                market_ticker=key.market_ticker,
                market_id=event.native_market_id,
                connection_id=key.connection_id,
                segment_id=key.segment_id,
                subscription_id=orderbook_identity.request_id,
                subscription_sid=orderbook_identity.sid,
                pricing_mode=mode,
                pricing_mode_source=source,
                pricing_mode_assumption=(
                    "use_yes_price absent; current recorder uses the venue default false"
                    if source is PricingModeSource.RECORDER_DEFAULT_ASSUMPTION
                    else None
                ),
            )
            self._states[key] = state
        return state

    def _validate_state_binding(
        self,
        state: NativeBookState,
        event: KalshiWsRawEvent,
    ) -> RebuildReason | None:
        metadata = self._segment_metadata[(event.connection_id, event.segment_id)]
        orderbook_identity = metadata.subscriptions.identity_for("orderbook_delta")
        if metadata.pricing_mode is not None and state.pricing_mode is not metadata.pricing_mode:
            return RebuildReason.CONTRADICTORY_PRICING_MODE
        if metadata.pricing_mode_source is PricingModeSource.D2A_SUBSCRIPTION_METADATA:
            state.pricing_mode_source = metadata.pricing_mode_source
            state.pricing_mode_assumption = None
        for current, observed in (
            (state.market_id, event.native_market_id),
            (state.subscription_id, orderbook_identity.request_id),
            (state.subscription_sid, orderbook_identity.sid),
        ):
            if current is not None and observed is not None and current != observed:
                return RebuildReason.IDENTITY_MISMATCH
        if state.market_id is None:
            state.market_id = event.native_market_id
        if state.subscription_id is None:
            state.subscription_id = orderbook_identity.request_id
        if state.subscription_sid is None:
            state.subscription_sid = orderbook_identity.sid
        return None

    def _apply_snapshot(
        self,
        state: NativeBookState,
        event: KalshiWsRawEvent,
    ) -> RebuildResult:
        try:
            yes, yes_presence, no, no_presence = _parse_snapshot(event.original_payload)
        except _RebuildFailure as exc:
            _invalidate(state, event, exc.reason)
            return RebuildResult(
                disposition=RebuildDisposition.QUARANTINED,
                reason=exc.reason,
                key=state.key,
                quarantined_record=event.to_record(),
            )
        reset_reason = (
            SnapshotResetReason.RECOVERY_AFTER_INVALIDATION
            if state.segment_validity is SegmentValidity.INVALID
            else SnapshotResetReason.RESNAPSHOT_SAME_SEGMENT
            if state.snapshot_received
            else SnapshotResetReason.INITIAL_SNAPSHOT
        )
        state.native_yes_bids = yes
        state.native_no_bids = no
        state.snapshot_yes_presence = yes_presence
        state.snapshot_no_presence = no_presence
        state.snapshot_received = True
        state.segment_validity = SegmentValidity.VALID
        state.invalidation_reason = None
        _record_progress(state, event)
        state.frame_count += 1
        frame = _build_frame(state, event, reset_reason=reset_reason)
        return RebuildResult(
            disposition=RebuildDisposition.FRAME_EMITTED,
            reason=None,
            key=state.key,
            frame=frame,
        )

    def _apply_delta(
        self,
        state: NativeBookState,
        event: KalshiWsRawEvent,
    ) -> RebuildResult:
        if state.segment_validity is SegmentValidity.INVALID:
            return RebuildResult(
                disposition=RebuildDisposition.EXCLUDED,
                reason=RebuildReason.SEGMENT_INVALID,
                key=state.key,
            )
        if not state.snapshot_received or state.segment_validity is not SegmentValidity.VALID:
            return self._quarantine_delta(state, event, RebuildReason.DELTA_BEFORE_SNAPSHOT)
        try:
            side = _payload_value(
                event.original_payload,
                "side",
                RebuildReason.MALFORMED_DELTA,
            )
            if side not in {"yes", "no"}:
                raise _RebuildFailure(RebuildReason.MALFORMED_DELTA)
            price = _exact_decimal(
                _payload_value(
                    event.original_payload,
                    "price_dollars",
                    RebuildReason.MALFORMED_DELTA,
                ),
                RebuildReason.MALFORMED_DELTA,
            )
            delta = _exact_decimal(
                _payload_value(
                    event.original_payload,
                    "delta_fp",
                    RebuildReason.MALFORMED_DELTA,
                ),
                RebuildReason.MALFORMED_DELTA,
            )
            _validate_price(price)
        except _RebuildFailure as exc:
            return self._quarantine_delta(state, event, exc.reason)

        levels = state.native_yes_bids if side == "yes" else state.native_no_bids
        resulting_quantity = _exact_add(levels.get(price, ZERO), delta)
        if resulting_quantity < ZERO:
            return self._quarantine_delta(
                state,
                event,
                RebuildReason.NEGATIVE_RESULTING_QUANTITY,
            )
        if resulting_quantity == ZERO:
            levels.pop(price, None)
        else:
            levels[price] = resulting_quantity
        _record_progress(state, event)
        state.frame_count += 1
        frame = _build_frame(state, event, reset_reason=None)
        return RebuildResult(
            disposition=RebuildDisposition.FRAME_EMITTED,
            reason=None,
            key=state.key,
            frame=frame,
        )

    @staticmethod
    def _quarantine_delta(
        state: NativeBookState,
        event: KalshiWsRawEvent,
        reason: RebuildReason,
    ) -> RebuildResult:
        _invalidate(state, event, reason)
        return RebuildResult(
            disposition=RebuildDisposition.QUARANTINED,
            reason=reason,
            key=state.key,
            quarantined_record=event.to_record(),
        )


def _event_key(event: KalshiWsRawEvent) -> NativeBookKey | None:
    if not event.native_market_ticker:
        return None
    return NativeBookKey(
        event.native_market_ticker,
        event.connection_id,
        event.segment_id,
    )


def _record_copy(record: Mapping[str, Any] | KalshiWsRawEvent) -> Mapping[str, Any]:
    if isinstance(record, KalshiWsRawEvent):
        return record.to_record()
    return deepcopy(dict(record))


def _pricing_values(payload: Mapping[str, Any]) -> list[object]:
    values: list[object] = []
    sources: list[Mapping[str, Any]] = [payload]
    index = 0
    while index < len(sources):
        parent = sources[index]
        index += 1
        for key in ("msg", "params"):
            nested = parent.get(key)
            if isinstance(nested, Mapping):
                sources.append(nested)
    for source in sources:
        if "use_yes_price" in source:
            values.append(source["use_yes_price"])
    return values


def _payload_value(
    payload: Mapping[str, Any],
    field_name: str,
    reason: RebuildReason = RebuildReason.MALFORMED_SNAPSHOT,
) -> object:
    if field_name in payload:
        return payload[field_name]
    nested = payload.get("msg")
    if isinstance(nested, Mapping) and field_name in nested:
        return nested[field_name]
    raise _RebuildFailure(reason)


def _parse_snapshot(
    payload: Mapping[str, Any],
) -> tuple[
    dict[Decimal, Decimal],
    SnapshotSidePresence,
    dict[Decimal, Decimal],
    SnapshotSidePresence,
]:
    yes_present, yes_raw = _snapshot_side_value(payload, "yes_dollars_fp")
    no_present, no_raw = _snapshot_side_value(payload, "no_dollars_fp")
    if not yes_present and not no_present:
        raise _RebuildFailure(RebuildReason.SNAPSHOT_BOTH_SIDES_OMITTED)
    yes, yes_presence = _parse_snapshot_levels(yes_present, yes_raw)
    no, no_presence = _parse_snapshot_levels(no_present, no_raw)
    return yes, yes_presence, no, no_presence


def _snapshot_side_value(payload: Mapping[str, Any], field_name: str) -> tuple[bool, object]:
    if field_name in payload:
        return True, payload[field_name]
    nested = payload.get("msg")
    if isinstance(nested, Mapping) and field_name in nested:
        return True, nested[field_name]
    return False, None


def _parse_snapshot_levels(
    present: bool,
    raw_levels: object,
) -> tuple[dict[Decimal, Decimal], SnapshotSidePresence]:
    if not present:
        return {}, SnapshotSidePresence.OMITTED_CONFIRMED_EMPTY
    if raw_levels is None:
        raise _RebuildFailure(RebuildReason.SNAPSHOT_NULL_SIDE)
    if not isinstance(raw_levels, list):
        raise _RebuildFailure(RebuildReason.SNAPSHOT_WRONG_SIDE_TYPE)
    levels: dict[Decimal, Decimal] = {}
    for raw_level in raw_levels:
        if not isinstance(raw_level, list | tuple) or len(raw_level) != 2:
            raise _RebuildFailure(RebuildReason.MALFORMED_SNAPSHOT)
        price = _exact_decimal(raw_level[0], RebuildReason.MALFORMED_SNAPSHOT)
        quantity = _exact_decimal(raw_level[1], RebuildReason.MALFORMED_SNAPSHOT)
        _validate_price(price)
        if quantity < ZERO:
            raise _RebuildFailure(RebuildReason.MALFORMED_SNAPSHOT)
        if price in levels:
            raise _RebuildFailure(RebuildReason.DUPLICATE_SNAPSHOT_PRICE)
        if quantity != ZERO:
            levels[price] = quantity
    presence = (
        SnapshotSidePresence.PRESENT_NONEMPTY
        if raw_levels
        else SnapshotSidePresence.PRESENT_EMPTY
    )
    return levels, presence


def _exact_decimal(value: object, reason: RebuildReason) -> Decimal:
    if isinstance(value, bool | float) or not isinstance(value, str | int | Decimal):
        raise _RebuildFailure(reason)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        raise _RebuildFailure(reason) from None
    if not parsed.is_finite():
        raise _RebuildFailure(reason)
    return parsed


def _validate_price(price: Decimal) -> None:
    if price < ZERO or price > ONE:
        raise _RebuildFailure(RebuildReason.IMPOSSIBLE_PRICE)


def _invalidate(
    state: NativeBookState,
    event: KalshiWsRawEvent,
    reason: RebuildReason,
) -> None:
    state.segment_validity = SegmentValidity.INVALID
    state.invalidation_reason = reason
    _record_progress(state, event)


def _record_progress(state: NativeBookState, event: KalshiWsRawEvent) -> None:
    state.last_local_row_index = event.local_row_index
    state.last_native_seq = event.native_seq
    state.sequence_state = event.sequence_state


def _build_frame(
    state: NativeBookState,
    event: KalshiWsRawEvent,
    *,
    reset_reason: SnapshotResetReason | None,
) -> KalshiWsBookFrame:
    native_yes = tuple(
        NativeLevel(price, quantity)
        for price, quantity in sorted(state.native_yes_bids.items(), reverse=True)
    )
    native_no = tuple(
        NativeLevel(price, quantity)
        for price, quantity in sorted(state.native_no_bids.items(), reverse=True)
    )
    canonical_bids = tuple(
        CanonicalLevel(level.price, level.quantity, "yes", level.price)
        for level in native_yes
    )
    canonical_asks = tuple(
        sorted(
            (
                CanonicalLevel(
                    _exact_complement(level.price)
                    if state.pricing_mode is PricingMode.LEGACY_SIDE_PRICE
                    else level.price,
                    level.quantity,
                    "no",
                    level.price,
                )
                for level in native_no
            ),
            key=lambda level: level.price,
        )
    )
    for level in (*canonical_bids, *canonical_asks):
        _validate_price(level.price)
    book_state = _book_state(canonical_bids, canonical_asks)
    terminal_hash = _semantic_hash(_state_hash_record(state))
    placeholder = KalshiWsBookFrame(
        market_ticker=state.market_ticker,
        market_id=state.market_id,
        connection_id=state.connection_id,
        segment_id=state.segment_id,
        subscription_id=state.subscription_id,
        subscription_sid=state.subscription_sid,
        local_row_index=event.local_row_index,
        native_seq=event.native_seq,
        sequence_state=event.sequence_state,
        pricing_mode=state.pricing_mode,
        pricing_mode_source=state.pricing_mode_source,
        pricing_mode_assumption=state.pricing_mode_assumption,
        snapshot_yes_presence=state.snapshot_yes_presence,
        snapshot_no_presence=state.snapshot_no_presence,
        snapshot_received=state.snapshot_received,
        native_yes_bids=native_yes,
        native_no_bids=native_no,
        canonical_yes_bids=canonical_bids,
        canonical_yes_asks=canonical_asks,
        book_state=book_state,
        segment_validity=state.segment_validity,
        invalidation_reason=state.invalidation_reason,
        reset_reason=reset_reason,
        frame_count=state.frame_count,
        frame_hash="",
        terminal_state_hash=terminal_hash,
    )
    return replace(
        placeholder,
        frame_hash=_semantic_hash(_frame_hash_record(placeholder)),
    )


def _book_state(
    bids: tuple[CanonicalLevel, ...],
    asks: tuple[CanonicalLevel, ...],
) -> CanonicalBookState:
    if not bids and not asks:
        return CanonicalBookState.EMPTY
    if not asks:
        return CanonicalBookState.YES_BIDS_ONLY
    if not bids:
        return CanonicalBookState.YES_ASKS_ONLY
    if bids[0].price > asks[0].price:
        return CanonicalBookState.CROSSED
    if bids[0].price == asks[0].price:
        return CanonicalBookState.LOCKED
    return CanonicalBookState.TWO_SIDED


def _state_hash_record(state: NativeBookState) -> dict[str, object]:
    return {
        "schema_version": state.schema_version,
        "market_ticker": state.market_ticker,
        "market_id": state.market_id,
        "connection_id": state.connection_id,
        "segment_id": state.segment_id,
        "subscription_id": state.subscription_id,
        "subscription_sid": state.subscription_sid,
        "pricing_mode": state.pricing_mode,
        "pricing_mode_source": state.pricing_mode_source,
        "pricing_mode_assumption": state.pricing_mode_assumption,
        "snapshot_received": state.snapshot_received,
        "native_yes_bids": _mapping_level_records(state.native_yes_bids),
        "native_no_bids": _mapping_level_records(state.native_no_bids),
        "last_local_row_index": state.last_local_row_index,
        "last_native_seq": state.last_native_seq,
        "sequence_state": state.sequence_state,
        "segment_validity": state.segment_validity,
        "invalidation_reason": state.invalidation_reason,
        "frame_count": state.frame_count,
    }


def _frame_hash_record(frame: KalshiWsBookFrame) -> dict[str, object]:
    return {
        "schema_version": frame.schema_version,
        "market_ticker": frame.market_ticker,
        "market_id": frame.market_id,
        "connection_id": frame.connection_id,
        "segment_id": frame.segment_id,
        "subscription_id": frame.subscription_id,
        "subscription_sid": frame.subscription_sid,
        "local_row_index": frame.local_row_index,
        "native_seq": frame.native_seq,
        "sequence_state": frame.sequence_state,
        "pricing_mode": frame.pricing_mode,
        "pricing_mode_source": frame.pricing_mode_source,
        "pricing_mode_assumption": frame.pricing_mode_assumption,
        "snapshot_yes_presence": frame.snapshot_yes_presence,
        "snapshot_no_presence": frame.snapshot_no_presence,
        "snapshot_received": frame.snapshot_received,
        "native_yes_bids": _native_level_records(frame.native_yes_bids),
        "native_no_bids": _native_level_records(frame.native_no_bids),
        "canonical_yes_bids": _canonical_level_records(frame.canonical_yes_bids),
        "canonical_yes_asks": _canonical_level_records(frame.canonical_yes_asks),
        "book_state": frame.book_state,
        "segment_validity": frame.segment_validity,
        "invalidation_reason": frame.invalidation_reason,
        "reset_reason": frame.reset_reason,
        "frame_count": frame.frame_count,
    }


def _mapping_level_records(levels: Mapping[Decimal, Decimal]) -> list[dict[str, str]]:
    return [
        {"price": _decimal_text(price), "quantity": _decimal_text(quantity)}
        for price, quantity in sorted(levels.items(), reverse=True)
    ]


def _native_level_records(levels: tuple[NativeLevel, ...]) -> list[dict[str, str]]:
    return [
        {"price": _decimal_text(level.price), "quantity": _decimal_text(level.quantity)}
        for level in levels
    ]


def _canonical_level_records(levels: tuple[CanonicalLevel, ...]) -> list[dict[str, str]]:
    return [
        {
            "price": _decimal_text(level.price),
            "quantity": _decimal_text(level.quantity),
            "native_side": level.native_side,
            "native_reported_price": _decimal_text(level.native_reported_price),
        }
        for level in levels
    ]


def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value, "f")
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".")


def _exact_add(left: Decimal, right: Decimal) -> Decimal:
    fractional_places = max(-left.as_tuple().exponent, -right.as_tuple().exponent, 0)
    integer_places = max(
        left.adjusted() + 1 if left else 0,
        right.adjusted() + 1 if right else 0,
        0,
    )
    with localcontext() as context:
        context.prec = max(integer_places + fractional_places + 1, 1)
        return left + right


def _exact_complement(price: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = max(len(price.as_tuple().digits), -price.as_tuple().exponent, 1) + 1
        return ONE - price


def _semantic_hash(record: Mapping[str, object]) -> str:
    return payload_sha256(record)
