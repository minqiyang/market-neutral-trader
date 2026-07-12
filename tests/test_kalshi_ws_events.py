from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from edmn_trader.adapters.kalshi.ws_events import (
    KALSHI_WS_RAW_SCHEMA_VERSION,
    AdmissionStatus,
    ExclusionReason,
    KalshiWsIntegrityTracker,
    KalshiWsRawEvent,
    KalshiWsSchemaCompatibilityError,
    LegacyCompatibilityStatus,
    LegacyKalshiWsRawEvent,
    NativeEnvelopeRejection,
    ResyncState,
    SegmentBoundaryReason,
    SequenceContinuityPolicy,
    SequenceState,
    SubscriptionBindingObservation,
    SubscriptionBindingState,
    parse_kalshi_ws_raw_record,
    payload_sha256,
)

RECEIVED_AT = datetime(2026, 7, 10, 1, 2, 3, tzinfo=UTC)


@pytest.mark.parametrize(
    ("field", "top", "nested", "reason"),
    [
        ("type", "orderbook_snapshot", "trade", NativeEnvelopeRejection.CONFLICTING_NATIVE_TYPE),
        ("channel", "orderbook_delta", "trade", NativeEnvelopeRejection.CONFLICTING_NATIVE_CHANNEL),
        ("id", 1, 2, NativeEnvelopeRejection.CONFLICTING_NATIVE_ID),
        ("sid", 41, 42, NativeEnvelopeRejection.CONFLICTING_NATIVE_SID),
    ],
)
def test_conflicting_native_routing_fields_are_typed_and_excluded(
    field: str,
    top: object,
    nested: object,
    reason: NativeEnvelopeRejection,
) -> None:
    tracker = _pending_tracker()
    payload: dict[str, object] = {
        "type": "orderbook_snapshot",
        "sid": 41,
        "msg": {"market_ticker": "DEMO-MARKET"},
    }
    payload[field] = top
    payload["msg"][field] = nested

    event = tracker.record(
        payload,
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )

    assert event.native_envelope_rejection is reason
    assert event.admission_status is AdmissionStatus.EXCLUDED
    assert event.exclusion_reason is ExclusionReason.NATIVE_ENVELOPE_REJECTED


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("id", NativeEnvelopeRejection.INVALID_NATIVE_ID),
        ("sid", NativeEnvelopeRejection.INVALID_NATIVE_SID),
    ],
)
def test_boolean_native_identifiers_are_typed_rejections(
    field: str,
    reason: NativeEnvelopeRejection,
) -> None:
    payload = {
        "type": "subscribed",
        "id": 1,
        "sid": 41,
        "msg": {"channel": "orderbook_delta"},
    }
    payload[field] = True

    event = _pending_tracker().record(
        payload,
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )

    assert event.native_envelope_rejection is reason


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, NativeEnvelopeRejection.MISSING_NATIVE_TYPE),
        (
            {"type": "subscribed", "id": 1, "sid": 41},
            NativeEnvelopeRejection.MISSING_ACK_CHANNEL,
        ),
        (
            {"type": "subscribed", "sid": 41, "msg": {"channel": "orderbook_delta"}},
            NativeEnvelopeRejection.MISSING_ACK_ID,
        ),
        (
            {"type": "subscribed", "id": 1, "msg": {"channel": "orderbook_delta"}},
            NativeEnvelopeRejection.MISSING_ACK_SID,
        ),
    ],
)
def test_missing_required_native_fields_are_typed_rejections(
    payload: dict[str, object],
    reason: NativeEnvelopeRejection,
) -> None:
    event = _pending_tracker().record(
        payload,
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )

    assert event.native_envelope_rejection is reason


def test_error_frame_cannot_acknowledge_a_binding() -> None:
    event = _pending_tracker().record(
        {
            "type": "error",
            "id": 1,
            "sid": 41,
            "msg": {"channel": "orderbook_delta", "error": "rejected"},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )

    assert event.subscription_binding_state is SubscriptionBindingState.REJECTED
    assert (
        event.subscription_binding_observation
        is SubscriptionBindingObservation.REJECTED
    )


@pytest.mark.parametrize("native_type", ["orderbook_snapshot", "orderbook_delta", "trade"])
def test_bound_data_without_sid_is_typed_and_excluded(native_type: str) -> None:
    tracker = _tracker()
    event = tracker.record(
        {
            "type": native_type,
            "msg": {"market_ticker": "DEMO-MARKET"},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )

    assert event.native_envelope_rejection is NativeEnvelopeRejection.MISSING_DATA_SID
    assert event.admission_status is AdmissionStatus.EXCLUDED
    assert event.exclusion_reason is ExclusionReason.NATIVE_ENVELOPE_REJECTED


def test_snapshot_envelope_preserves_native_fields_and_local_order() -> None:
    tracker = _tracker()
    payload = {
        "type": "orderbook_snapshot",
        "sid": 41,
        "seq": 9001,
        "msg": {
            "market_ticker": "DEMO-MARKET",
            "market_id": "market-id-1",
            "ts": "2026-07-10T01:02:02.900000Z",
            "ts_ms": 1_783_648_922_900,
            "yes_dollars": [["0.42", "10"]],
            "unknown_native_field": {"kept": True},
        },
    }

    event = tracker.record(
        payload,
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=123_456,
    )
    record = event.to_record()

    assert record["schema_version"] == KALSHI_WS_RAW_SCHEMA_VERSION
    assert record["local_row_index"] == 1
    assert record["native_seq"] == 9001
    assert record["native_sid"] == 41
    assert record["native_type"] == "orderbook_snapshot"
    assert record["native_market_ticker"] == "DEMO-MARKET"
    assert record["native_market_id"] == "market-id-1"
    assert record["native_exchange_ts"] == "2026-07-10T01:02:02.900000Z"
    assert record["native_exchange_ts_ms"] == 1_783_648_922_900
    assert record["original_payload"] == payload
    assert record["connection_id"] == "campaign-1:connection:0001"
    assert record["segment_id"] == "campaign-1:segment:0002"
    assert record["segment_boundary_reason"] == SegmentBoundaryReason.NEW_SUBSCRIPTION
    assert record["subscription_command_id"] == 1
    assert record["admission_status"] == AdmissionStatus.ADMITTED
    assert record["exclusion_reason"] is None
    assert record["sequence_continuity_policy"] == SequenceContinuityPolicy.UNKNOWN
    assert record["sequence_state"] == SequenceState.SEQUENCE_PRESENT_SEMANTICS_UNKNOWN
    assert record["resync_state"] == ResyncState.RESYNCED_WITH_SNAPSHOT
    assert record["received_at_utc"] == RECEIVED_AT.isoformat()
    assert record["received_monotonic_ns"] == 123_456
    assert len(record["payload_sha256"]) == 64


def test_delta_before_snapshot_is_preserved_but_excluded() -> None:
    tracker = _tracker()
    payload = {
        "type": "orderbook_delta",
        "sid": 41,
        "seq": 9002,
        "msg": {"market_ticker": "DEMO-MARKET", "price": "0.43", "delta": "2"},
    }

    event = tracker.record(
        payload,
        local_row_index=2,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=123_456,
    )

    assert event.original_payload == payload
    assert event.admission_status is AdmissionStatus.EXCLUDED
    assert event.exclusion_reason is ExclusionReason.DELTA_BEFORE_SNAPSHOT
    assert event.resync_state is ResyncState.RESYNC_REQUIRED


def test_channel_scoped_acknowledgements_keep_independent_native_sids() -> None:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=("DEMO-MARKET",),
    )
    tracker.start_connection()
    tracker.bind_subscription(
        command_id=1,
        channels=("orderbook_delta", "trade"),
    )

    orderbook_ack = tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 41,
            "msg": {"channel": "orderbook_delta"},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )
    trade_ack = tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 99,
            "msg": {"channel": "trade"},
        },
        local_row_index=2,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=2,
    )
    snapshot = tracker.record(
        {
            "type": "orderbook_snapshot",
            "sid": 41,
            "seq": 1,
            "msg": {"market_ticker": "DEMO-MARKET"},
        },
        local_row_index=3,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=3,
    )

    assert orderbook_ack.subscription_sid == 41
    assert trade_ack.subscription_sid == 99
    assert orderbook_ack.subscription_binding_id != trade_ack.subscription_binding_id
    assert snapshot.subscription_binding_id == orderbook_ack.subscription_binding_id
    assert snapshot.subscription_binding_state is SubscriptionBindingState.ACKNOWLEDGED
    assert snapshot.admission_status is AdmissionStatus.ADMITTED


@pytest.mark.parametrize(
    ("native_type", "channel"),
    [("orderbook_snapshot", "trade"), ("trade", "orderbook_delta")],
)
def test_native_type_cannot_use_another_channel_binding(
    native_type: str,
    channel: str,
) -> None:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=("DEMO-MARKET",),
    )
    tracker.start_connection()
    tracker.bind_subscription(
        command_id=1,
        channels=("orderbook_delta", "trade"),
    )
    event = tracker.record(
        {
            "type": native_type,
            "sid": 7,
            "msg": {"channel": channel, "market_ticker": "DEMO-MARKET"},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )

    assert event.admission_status is AdmissionStatus.EXCLUDED
    assert event.exclusion_reason is ExclusionReason.CHANNEL_TYPE_MISMATCH


def test_acknowledgement_with_unknown_request_id_does_not_bind_sid() -> None:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=("DEMO-MARKET",),
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1, channels=("orderbook_delta",))

    mismatched = tracker.record(
        {
            "type": "subscribed",
            "id": 999,
            "sid": 99,
            "msg": {"channel": "orderbook_delta"},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )
    valid = tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 41,
            "msg": {"channel": "orderbook_delta"},
        },
        local_row_index=2,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=2,
    )

    assert mismatched.subscription_binding_state is SubscriptionBindingState.REQUEST_MISMATCH
    assert mismatched.subscription_sid == 99
    assert valid.subscription_binding_state is SubscriptionBindingState.ACKNOWLEDGED
    assert valid.subscription_sid == 41


def test_duplicate_ack_is_idempotent_but_conflicting_sid_conflicts_binding() -> None:
    tracker = _pending_tracker()
    first = _ack_channel(
        tracker,
        command_id=1,
        channel="trade",
        sid=22,
    )
    duplicate = _ack_channel(
        tracker,
        command_id=1,
        channel="trade",
        sid=22,
    )
    conflict = _ack_channel(
        tracker,
        command_id=1,
        channel="trade",
        sid=99,
    )
    after_conflict = _record(
        tracker,
        "trade",
        seq=1,
        local_row_index=4,
        sid=22,
    )

    assert first.subscription_binding_state is SubscriptionBindingState.ACKNOWLEDGED
    assert duplicate.subscription_binding_state is SubscriptionBindingState.ACKNOWLEDGED
    assert (
        duplicate.subscription_binding_observation
        is SubscriptionBindingObservation.DUPLICATE_ACK
    )
    assert conflict.subscription_binding_state is SubscriptionBindingState.CONFLICTED
    assert (
        conflict.subscription_binding_observation
        is SubscriptionBindingObservation.CONFLICTING_ACK
    )
    assert after_conflict.exclusion_reason is ExclusionReason.SUBSCRIPTION_BINDING_CONFLICTED


def test_exact_duplicate_orderbook_ack_is_idempotent() -> None:
    tracker = _pending_tracker()
    _ack_channel(
        tracker,
        command_id=1,
        channel="orderbook_delta",
        sid=41,
    )
    duplicate = _ack_channel(
        tracker,
        command_id=1,
        channel="orderbook_delta",
        sid=41,
    )

    assert duplicate.subscription_binding_state is SubscriptionBindingState.ACKNOWLEDGED
    assert (
        duplicate.subscription_binding_observation
        is SubscriptionBindingObservation.DUPLICATE_ACK
    )


def test_pre_ack_orderbook_data_stays_excluded_after_ack_until_fresh_snapshot() -> None:
    tracker = _pending_tracker()
    early_snapshot = _record(
        tracker,
        "orderbook_snapshot",
        seq=1,
        local_row_index=1,
        sid=41,
    )
    _ack_channel(
        tracker,
        command_id=1,
        channel="orderbook_delta",
        sid=41,
    )
    early_delta = _record(
        tracker,
        "orderbook_delta",
        seq=2,
        local_row_index=3,
        sid=41,
    )
    fresh_snapshot = _record(
        tracker,
        "orderbook_snapshot",
        seq=3,
        local_row_index=4,
        sid=41,
    )

    assert early_snapshot.exclusion_reason is ExclusionReason.PRE_ACKNOWLEDGMENT_DATA
    assert early_delta.exclusion_reason is ExclusionReason.DELTA_BEFORE_SNAPSHOT
    assert fresh_snapshot.admission_status is AdmissionStatus.ADMITTED


def test_late_ack_from_prior_orderbook_generation_cannot_rebind_current_sid() -> None:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=("DEMO-MARKET",),
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1, channels=("orderbook_delta",))
    tracker.bind_subscription(command_id=2, channels=("orderbook_delta",))

    late = tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 41,
            "msg": {"channel": "orderbook_delta"},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )
    current = tracker.record(
        {
            "type": "subscribed",
            "id": 2,
            "sid": 44,
            "msg": {"channel": "orderbook_delta"},
        },
        local_row_index=2,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=2,
    )

    assert late.subscription_binding_state is SubscriptionBindingState.REQUEST_MISMATCH
    assert current.subscription_binding_state is SubscriptionBindingState.ACKNOWLEDGED
    assert current.subscription_generation == 2
    assert current.subscription_sid == 44


def test_delta_envelope_preserves_native_timestamp_and_delta_fields() -> None:
    tracker = _tracker()
    _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)
    payload = {
        "type": "orderbook_delta",
        "sid": 41,
        "seq": 101,
        "msg": {
            "market_ticker": "DEMO-MARKET",
            "ts": "2026-07-10T01:02:03Z",
            "ts_ms": 1_783_648_923_000,
            "price": "0.43",
            "delta": "2",
            "side": "yes",
        },
    }

    event = tracker.record(
        payload,
        local_row_index=2,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=123_458,
    )

    assert event.native_exchange_ts == "2026-07-10T01:02:03Z"
    assert event.native_exchange_ts_ms == 1_783_648_923_000
    assert event.original_payload["msg"]["price"] == "0.43"
    assert event.original_payload["msg"]["delta"] == "2"


def test_each_requested_market_requires_its_own_snapshot() -> None:
    tracker = _tracker(requested_market_tickers=("MARKET-A", "MARKET-B"))
    snapshot_a = _record(
        tracker,
        "orderbook_snapshot",
        seq=100,
        local_row_index=1,
        market_ticker="MARKET-A",
    )
    early_delta_b = _record(
        tracker,
        "orderbook_delta",
        seq=101,
        local_row_index=2,
        market_ticker="MARKET-B",
    )
    snapshot_b = _record(
        tracker,
        "orderbook_snapshot",
        seq=102,
        local_row_index=3,
        market_ticker="MARKET-B",
    )
    delta_b = _record(
        tracker,
        "orderbook_delta",
        seq=103,
        local_row_index=4,
        market_ticker="MARKET-B",
    )

    assert snapshot_a.admission_status is AdmissionStatus.ADMITTED
    assert early_delta_b.admission_status is AdmissionStatus.EXCLUDED
    assert early_delta_b.exclusion_reason is ExclusionReason.DELTA_BEFORE_SNAPSHOT
    assert early_delta_b.resync_state is ResyncState.RESYNC_REQUIRED
    assert snapshot_b.admission_status is AdmissionStatus.ADMITTED
    assert delta_b.admission_status is AdmissionStatus.ADMITTED


@pytest.mark.parametrize(
    ("market_ticker", "reason"),
    [
        (None, ExclusionReason.MISSING_MARKET_TICKER),
        ("OTHER-MARKET", ExclusionReason.UNREQUESTED_MARKET_TICKER),
    ],
)
def test_snapshot_requires_a_requested_market_ticker(
    market_ticker: str | None,
    reason: ExclusionReason,
) -> None:
    payload: dict[str, object] = {"type": "orderbook_snapshot", "sid": 41, "seq": 100}
    if market_ticker is not None:
        payload["market_ticker"] = market_ticker

    event = _tracker().record(
        payload,
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=123_457,
    )

    assert event.admission_status is AdmissionStatus.EXCLUDED
    assert event.exclusion_reason is reason
    assert event.resync_state is ResyncState.RESYNC_REQUIRED


def test_unknown_sequence_policy_observes_monotonicity_without_claiming_continuity() -> None:
    tracker = _tracker()
    snapshot = _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)
    next_delta = _record(tracker, "orderbook_delta", seq=101, local_row_index=2)
    jumped_delta = _record(tracker, "orderbook_delta", seq=110, local_row_index=3)

    assert snapshot.sequence_state is SequenceState.SEQUENCE_PRESENT_SEMANTICS_UNKNOWN
    assert next_delta.sequence_state is SequenceState.SEQUENCE_OBSERVED_MONOTONIC
    assert jumped_delta.sequence_state is SequenceState.SEQUENCE_OBSERVED_MONOTONIC
    assert next_delta.admission_status is AdmissionStatus.ADMITTED
    assert jumped_delta.admission_status is AdmissionStatus.ADMITTED


def test_controlled_contiguous_policy_can_verify_one_step_continuity() -> None:
    tracker = _tracker(continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT)
    snapshot = _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)
    delta = _record(tracker, "orderbook_delta", seq=101, local_row_index=2)

    assert snapshot.sequence_state is SequenceState.SEQUENCE_PRESENT_SEMANTICS_UNKNOWN
    assert delta.sequence_continuity_policy is SequenceContinuityPolicy.CONTIGUOUS_INCREMENT
    assert delta.sequence_state is SequenceState.SEQUENCE_CONTIGUITY_VERIFIED
    assert delta.admission_status is AdmissionStatus.ADMITTED


def test_non_orderbook_sequence_does_not_contaminate_orderbook_continuity() -> None:
    tracker = _tracker(continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT)
    _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)
    heartbeat = _record(tracker, "heartbeat", seq=9_999, local_row_index=2)
    delta = _record(tracker, "orderbook_delta", seq=101, local_row_index=3)

    assert heartbeat.sequence_state is SequenceState.SEQUENCE_PRESENT_SEMANTICS_UNKNOWN
    assert heartbeat.admission_status is AdmissionStatus.NOT_APPLICABLE
    assert delta.sequence_state is SequenceState.SEQUENCE_CONTIGUITY_VERIFIED
    assert delta.admission_status is AdmissionStatus.ADMITTED


def test_duplicate_is_excluded_and_fresh_snapshot_starts_resynced_segment() -> None:
    tracker = _tracker()
    first_snapshot = _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)
    duplicate = _record(tracker, "orderbook_delta", seq=100, local_row_index=2)
    fresh_snapshot = _record(tracker, "orderbook_snapshot", seq=500, local_row_index=3)

    assert duplicate.segment_id == first_snapshot.segment_id
    assert duplicate.sequence_continuity_policy is SequenceContinuityPolicy.UNKNOWN
    assert duplicate.sequence_state is SequenceState.SEQUENCE_DUPLICATE
    assert duplicate.admission_status is AdmissionStatus.EXCLUDED
    assert duplicate.exclusion_reason is ExclusionReason.SEQUENCE_DUPLICATE
    assert duplicate.resync_state is ResyncState.RESYNC_REQUIRED
    assert fresh_snapshot.segment_id != first_snapshot.segment_id
    assert fresh_snapshot.admission_status is AdmissionStatus.ADMITTED
    assert fresh_snapshot.resync_state is ResyncState.RESYNCED_WITH_SNAPSHOT


def test_unknown_policy_decreasing_sequence_is_excluded_without_continuity_claim() -> None:
    tracker = _tracker()
    _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)

    out_of_order = _record(tracker, "orderbook_delta", seq=99, local_row_index=2)

    assert out_of_order.sequence_continuity_policy is SequenceContinuityPolicy.UNKNOWN
    assert out_of_order.sequence_state is SequenceState.SEQUENCE_OUT_OF_ORDER
    assert out_of_order.admission_status is AdmissionStatus.EXCLUDED
    assert out_of_order.exclusion_reason is ExclusionReason.SEQUENCE_OUT_OF_ORDER
    assert out_of_order.resync_state is ResyncState.RESYNC_REQUIRED


@pytest.mark.parametrize(
    ("next_seq", "expected_state", "expected_reason"),
    [
        (99, SequenceState.SEQUENCE_OUT_OF_ORDER, ExclusionReason.SEQUENCE_OUT_OF_ORDER),
        (105, SequenceState.SEQUENCE_GAP_DETECTED, ExclusionReason.SEQUENCE_GAP),
    ],
)
def test_supported_sequence_failures_are_excluded_and_require_resync(
    next_seq: int,
    expected_state: SequenceState,
    expected_reason: ExclusionReason,
) -> None:
    tracker = _tracker(continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT)
    first = _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)
    failed = _record(tracker, "orderbook_delta", seq=next_seq, local_row_index=2)
    pre_snapshot_delta = _record(
        tracker,
        "orderbook_delta",
        seq=next_seq + 1,
        local_row_index=3,
    )

    assert failed.segment_id == first.segment_id
    assert failed.sequence_state is expected_state
    assert failed.admission_status is AdmissionStatus.EXCLUDED
    assert failed.exclusion_reason is expected_reason
    assert pre_snapshot_delta.segment_id != first.segment_id
    assert pre_snapshot_delta.admission_status is AdmissionStatus.EXCLUDED
    assert pre_snapshot_delta.exclusion_reason is ExclusionReason.DELTA_BEFORE_SNAPSHOT


def test_missing_sequence_is_explicitly_not_observed() -> None:
    event = _record(_tracker(), "orderbook_snapshot", seq=None, local_row_index=1)

    assert event.native_seq is None
    assert event.sequence_state is SequenceState.SEQUENCE_NOT_OBSERVED


def test_nested_string_identifiers_are_preserved_without_numeric_inference() -> None:
    event = _tracker(orderbook_sid="sid-41").record(
        {
            "msg": {
                "type": "orderbook_snapshot",
                "sid": "sid-41",
                "seq": "seq-9001",
                "market_ticker": "DEMO-MARKET",
            }
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=123_457,
    )

    assert event.native_type == "orderbook_snapshot"
    assert event.native_sid == "sid-41"
    assert event.native_seq == "seq-9001"
    assert event.sequence_state is SequenceState.SEQUENCE_PRESENT_SEMANTICS_UNKNOWN
    assert event.admission_status is AdmissionStatus.ADMITTED


def test_boolean_identifiers_are_not_treated_as_integers() -> None:
    event = _tracker().record(
        {
            "type": "orderbook_snapshot",
            "sid": True,
            "seq": True,
            "msg": {"market_ticker": "DEMO-MARKET"},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=123_457,
    )

    assert event.native_sid is None
    assert event.native_seq is None
    assert event.sequence_state is SequenceState.SEQUENCE_NOT_OBSERVED


def test_sid_change_is_excluded_until_explicit_orderbook_resubscription() -> None:
    tracker = _tracker(continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT)
    first = _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1, sid=41)
    changed_sid_delta = _record(
        tracker,
        "orderbook_delta",
        seq=101,
        local_row_index=2,
        sid=42,
    )
    tracker.bind_subscription(command_id=2)
    _ack_channel(tracker, command_id=2, channel="orderbook_delta", sid=42)
    fresh_snapshot = _record(
        tracker,
        "orderbook_snapshot",
        seq=500,
        local_row_index=3,
        sid=42,
    )

    assert changed_sid_delta.segment_id == first.segment_id
    assert changed_sid_delta.segment_boundary_reason is SegmentBoundaryReason.NEW_SUBSCRIPTION
    assert changed_sid_delta.admission_status is AdmissionStatus.EXCLUDED
    assert (
        changed_sid_delta.exclusion_reason
        is ExclusionReason.SUBSCRIPTION_IDENTITY_MISMATCH
    )
    assert fresh_snapshot.segment_id != changed_sid_delta.segment_id
    assert fresh_snapshot.segment_boundary_reason is SegmentBoundaryReason.RESUBSCRIPTION
    assert fresh_snapshot.admission_status is AdmissionStatus.ADMITTED


def test_reconnect_creates_new_connection_and_snapshot_required_segment() -> None:
    tracker = _tracker()
    first = _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)

    tracker.start_connection()
    tracker.bind_subscription(command_id=1)
    _ack_channel(tracker, command_id=1, channel="orderbook_delta", sid=41)
    after_reconnect = _record(tracker, "orderbook_delta", seq=101, local_row_index=2)
    fresh_snapshot = _record(tracker, "orderbook_snapshot", seq=500, local_row_index=3)

    assert after_reconnect.connection_id != first.connection_id
    assert after_reconnect.segment_id != first.segment_id
    assert after_reconnect.segment_boundary_reason is SegmentBoundaryReason.RESUBSCRIPTION
    assert after_reconnect.admission_status is AdmissionStatus.EXCLUDED
    assert after_reconnect.exclusion_reason is ExclusionReason.DELTA_BEFORE_SNAPSHOT
    assert fresh_snapshot.segment_id == after_reconnect.segment_id
    assert fresh_snapshot.admission_status is AdmissionStatus.ADMITTED
    assert fresh_snapshot.subscription_binding_id != first.subscription_binding_id
    assert fresh_snapshot.subscription_generation == 2


def test_resubscription_creates_new_segment_on_same_connection() -> None:
    tracker = _tracker()
    first = _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)

    tracker.bind_subscription(command_id=2)
    after_resubscribe = _record(tracker, "orderbook_delta", seq=101, local_row_index=2)

    assert after_resubscribe.connection_id == first.connection_id
    assert after_resubscribe.segment_id != first.segment_id
    assert after_resubscribe.segment_boundary_reason is SegmentBoundaryReason.RESUBSCRIPTION
    assert after_resubscribe.subscription_command_id == 2
    assert after_resubscribe.admission_status is AdmissionStatus.EXCLUDED


def test_orderbook_resubscription_rejects_old_sid_and_requires_new_snapshot() -> None:
    tracker = _tracker()
    first = _record(tracker, "orderbook_snapshot", seq=1, local_row_index=1, sid=41)
    tracker.bind_subscription(command_id=2, channels=("orderbook_delta",))
    acknowledgement = tracker.record(
        {
            "type": "subscribed",
            "id": 2,
            "sid": 44,
            "msg": {"channel": "orderbook_delta"},
        },
        local_row_index=2,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=2,
    )
    old_delta = _record(
        tracker,
        "orderbook_delta",
        seq=2,
        local_row_index=3,
        sid=41,
    )
    new_delta = _record(
        tracker,
        "orderbook_delta",
        seq=3,
        local_row_index=4,
        sid=44,
    )
    new_snapshot = _record(
        tracker,
        "orderbook_snapshot",
        seq=4,
        local_row_index=5,
        sid=44,
    )

    assert acknowledgement.subscription_generation == 2
    assert acknowledgement.subscription_binding_id != first.subscription_binding_id
    assert old_delta.exclusion_reason is ExclusionReason.SUBSCRIPTION_IDENTITY_MISMATCH
    assert new_delta.exclusion_reason is ExclusionReason.DELTA_BEFORE_SNAPSHOT
    assert new_snapshot.admission_status is AdmissionStatus.ADMITTED


def test_initial_subscription_creates_a_segment_after_connection_boundary() -> None:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=("DEMO-MARKET",),
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1)

    first = _record(tracker, "orderbook_snapshot", seq=100, local_row_index=1)

    assert first.segment_id == "campaign-1:segment:0002"
    assert first.segment_boundary_reason is SegmentBoundaryReason.NEW_SUBSCRIPTION


def test_v2_record_round_trip_verifies_payload_hash() -> None:
    event = _record(_tracker(), "orderbook_snapshot", seq=100, local_row_index=1)

    parsed = parse_kalshi_ws_raw_record(event.to_record())

    assert isinstance(parsed, KalshiWsRawEvent)
    assert parsed == event


def test_v2_parser_keeps_pre_binding_provenance_rows_readable() -> None:
    record = _record(
        _tracker(),
        "orderbook_snapshot",
        seq=100,
        local_row_index=1,
    ).to_record()
    record.pop("subscription_generation")
    record.pop("subscription_binding_id")
    record.pop("subscription_binding_state")
    record.pop("subscription_identity_model")

    parsed = parse_kalshi_ws_raw_record(record)

    assert isinstance(parsed, KalshiWsRawEvent)
    assert parsed.subscription_generation is None
    assert parsed.subscription_binding_id is None
    assert parsed.subscription_binding_state is SubscriptionBindingState.UNKNOWN
    assert parsed.subscription_identity_model is None


def test_v2_parser_rejects_payload_hash_mismatch() -> None:
    record = _record(
        _tracker(),
        "orderbook_snapshot",
        seq=100,
        local_row_index=1,
    ).to_record()
    original_payload = record["original_payload"]
    assert isinstance(original_payload, dict)
    original_payload["mutated"] = True

    with pytest.raises(ValueError, match="does not match"):
        parse_kalshi_ws_raw_record(record)


def test_v2_parser_rejects_native_sequence_overwrite() -> None:
    record = _record(
        _tracker(),
        "orderbook_snapshot",
        seq=100,
        local_row_index=1,
    ).to_record()
    record["native_seq"] = 1

    with pytest.raises(ValueError, match="native_seq does not match"):
        parse_kalshi_ws_raw_record(record)


@pytest.mark.parametrize("schema_version", ["future.v99", 2, "", None])
def test_parser_rejects_unknown_explicit_schema(schema_version: object) -> None:
    with pytest.raises(KalshiWsSchemaCompatibilityError, match="unsupported"):
        parse_kalshi_ws_raw_record({"schema_version": schema_version})


def test_legacy_local_sequence_never_becomes_native_sequence() -> None:
    legacy = parse_kalshi_ws_raw_record(
        {
            "record_type": "kalshi_demo_ws_message",
            "campaign_id": "legacy-campaign",
            "venue": "kalshi_demo",
            "market_tickers": ["DEMO-MARKET"],
            "sequence": 7,
            "received_at": RECEIVED_AT.isoformat(),
            "message_type": "orderbook_delta",
            "payload": {
                "type": "orderbook_delta",
                "sid": 41,
                "seq": 9001,
                "msg": {"market_ticker": "DEMO-MARKET"},
            },
        }
    )

    assert isinstance(legacy, LegacyKalshiWsRawEvent)
    assert legacy.compatibility_status is LegacyCompatibilityStatus.LEGACY_LOCAL_SEQUENCE_ONLY
    assert legacy.local_row_index == 7
    assert legacy.legacy_message_type == "orderbook_delta"
    assert legacy.native_type is None
    assert legacy.native_seq is None
    assert legacy.native_sequence_evidence_eligible is False
    assert legacy.sequence_state is SequenceState.SEQUENCE_NOT_OBSERVED


def test_legacy_parser_rejects_non_demo_venue() -> None:
    with pytest.raises(KalshiWsSchemaCompatibilityError, match="Kalshi Demo"):
        parse_kalshi_ws_raw_record(
            {
                "record_type": "kalshi_demo_ws_message",
                "campaign_id": "legacy-campaign",
                "venue": "other",
                "market_tickers": ["DEMO-MARKET"],
                "sequence": 1,
                "received_at": RECEIVED_AT.isoformat(),
                "payload": {},
            }
        )


def test_payload_hash_uses_deterministic_canonical_json() -> None:
    first = {"type": "orderbook_delta", "msg": {"b": 2, "a": 1}}
    reordered = {"msg": {"a": 1, "b": 2}, "type": "orderbook_delta"}

    assert payload_sha256(first) == payload_sha256(reordered)


def test_payload_hash_preserves_unicode_as_utf8() -> None:
    expected = hashlib.sha256(b'{"label":"caf\xc3\xa9"}').hexdigest()

    assert payload_sha256({"label": "caf\u00e9"}) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_payload_hash_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="Out of range float values"):
        payload_sha256({"value": value})


@pytest.mark.parametrize(
    "header_name",
    [
        "KALSHI-ACCESS-KEY",
        "KALSHI-ACCESS-SIGNATURE",
        "KALSHI-ACCESS-TIMESTAMP",
    ],
)
def test_secret_like_native_payload_is_rejected(header_name: str) -> None:
    tracker = _tracker()

    with pytest.raises(ValueError, match="must not contain credentials"):
        tracker.record(
            {
                "type": "orderbook_snapshot",
                header_name: "synthetic-auth-value",
            },
            local_row_index=1,
            received_at_utc=RECEIVED_AT,
            received_monotonic_ns=123_456,
        )


def test_secret_like_keys_nested_in_sequences_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not contain credentials"):
        _tracker().record(
            {
                "type": "orderbook_snapshot",
                "levels": [[{"api_key": "synthetic-auth-value"}]],
            },
            local_row_index=1,
            received_at_utc=RECEIVED_AT,
            received_monotonic_ns=123_456,
        )


def test_private_account_keys_nested_in_nested_sequences_are_rejected() -> None:
    with pytest.raises(ValueError, match="private account/order data"):
        _tracker().record(
            {
                "type": "trade",
                "levels": [[{"order_id": "private-value"}]],
            },
            local_row_index=1,
            received_at_utc=RECEIVED_AT,
            received_monotonic_ns=123_456,
        )


def test_public_trade_sid_does_not_reset_orderbook_integrity_segment() -> None:
    tracker = _tracker(orderbook_sid=11, trade_sid=22)
    snapshot = _record(
        tracker,
        "orderbook_snapshot",
        seq=1,
        local_row_index=1,
        sid=11,
    )
    trade = _record(
        tracker,
        "trade",
        seq=1,
        local_row_index=2,
        sid=22,
    )
    delta = _record(
        tracker,
        "orderbook_delta",
        seq=2,
        local_row_index=3,
        sid=11,
    )

    assert trade.native_sid == 22
    assert snapshot.segment_id == delta.segment_id
    assert delta.admission_status is AdmissionStatus.ADMITTED


@pytest.mark.parametrize(
    "private_key",
    ["account_id", "account_number", "fills", "order_id", "orders"],
)
def test_private_account_keys_nested_in_sequences_are_rejected(private_key: str) -> None:
    with pytest.raises(ValueError, match="private account/order data"):
        _tracker().record(
            {
                "type": "trade",
                "msg": {"metadata": [{private_key: "private-value"}]},
            },
            local_row_index=1,
            received_at_utc=RECEIVED_AT,
            received_monotonic_ns=123_456,
        )


def _tracker(
    *,
    continuity_policy: SequenceContinuityPolicy = SequenceContinuityPolicy.UNKNOWN,
    requested_market_tickers: tuple[str, ...] = ("DEMO-MARKET",),
    orderbook_sid: str | int = 41,
    trade_sid: str | int = 22,
) -> KalshiWsIntegrityTracker:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=requested_market_tickers,
        continuity_policy=continuity_policy,
    )
    tracker.start_connection()
    tracker.bind_subscription(
        command_id=1,
        channels=("orderbook_delta", "trade"),
    )
    for index, (channel, sid) in enumerate(
        (("orderbook_delta", orderbook_sid), ("trade", trade_sid)),
        start=1,
    ):
        tracker.record(
            {
                "type": "subscribed",
                "id": 1,
                "sid": sid,
                "msg": {"channel": channel},
            },
            local_row_index=index,
            received_at_utc=RECEIVED_AT,
            received_monotonic_ns=index,
        )
    return tracker


def _pending_tracker() -> KalshiWsIntegrityTracker:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=("DEMO-MARKET",),
    )
    tracker.start_connection()
    tracker.bind_subscription(
        command_id=1,
        channels=("orderbook_delta", "trade"),
    )
    return tracker


def _record(
    tracker: KalshiWsIntegrityTracker,
    native_type: str,
    *,
    seq: int | None,
    local_row_index: int,
    sid: int = 41,
    market_ticker: str = "DEMO-MARKET",
):
    payload: dict[str, object] = {
        "type": native_type,
        "sid": sid,
        "msg": {"market_ticker": market_ticker},
    }
    if seq is not None:
        payload["seq"] = seq
    return tracker.record(
        payload,
        local_row_index=local_row_index,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=123_456 + local_row_index,
    )


def _ack_channel(
    tracker: KalshiWsIntegrityTracker,
    *,
    command_id: int,
    channel: str,
    sid: int,
):
    return tracker.record(
        {
            "type": "subscribed",
            "id": command_id,
            "sid": sid,
            "msg": {"channel": channel},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1,
    )
