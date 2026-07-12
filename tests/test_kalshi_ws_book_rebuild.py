from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from edmn_trader.adapters.kalshi.ws_book_rebuild import (
    CanonicalBookState,
    CanonicalLevel,
    KalshiWsBookRebuilder,
    NativeLevel,
    PricingMode,
    PricingModeSource,
    RebuildDisposition,
    RebuildReason,
    SegmentValidity,
    SnapshotResetReason,
    SnapshotSidePresence,
)
from edmn_trader.adapters.kalshi.ws_events import (
    AdmissionStatus,
    ExclusionReason,
    KalshiWsIntegrityTracker,
    ResyncState,
    SequenceContinuityPolicy,
    SequenceState,
)

MARKET = "DEMO-MARKET"
OTHER_MARKET = "DEMO-OTHER"
RECEIVED_AT = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)


def test_legacy_mode_snapshot_builds_native_and_canonical_books() -> None:
    tracker = _tracker()
    event = _snapshot(
        tracker,
        yes=[["0.4100", "2.5"], ["0.4200", "3.25"]],
        no=[["0.5500", "4.5"], ["0.5600", "5.75"]],
    )

    result = KalshiWsBookRebuilder().apply(event)

    assert result.disposition is RebuildDisposition.FRAME_EMITTED
    assert result.reason is None
    assert result.frame is not None
    frame = result.frame
    assert frame.pricing_mode is PricingMode.LEGACY_SIDE_PRICE
    assert frame.pricing_mode_source is PricingModeSource.RECORDER_DEFAULT_ASSUMPTION
    assert frame.pricing_mode_assumption
    assert _levels(frame.native_yes_bids) == [
        (Decimal("0.4200"), Decimal("3.25")),
        (Decimal("0.4100"), Decimal("2.5")),
    ]
    assert _levels(frame.native_no_bids) == [
        (Decimal("0.5600"), Decimal("5.75")),
        (Decimal("0.5500"), Decimal("4.5")),
    ]
    assert _levels(frame.canonical_yes_bids) == _levels(frame.native_yes_bids)
    assert _levels(frame.canonical_yes_asks) == [
        (Decimal("0.4400"), Decimal("5.75")),
        (Decimal("0.4500"), Decimal("4.5")),
    ]
    assert [level.native_reported_price for level in frame.canonical_yes_asks] == [
        Decimal("0.5600"),
        Decimal("0.5500"),
    ]
    assert frame.book_state is CanonicalBookState.TWO_SIDED
    assert frame.segment_validity is SegmentValidity.VALID
    assert frame.snapshot_received is True
    assert frame.reset_reason is SnapshotResetReason.INITIAL_SNAPSHOT
    assert len(frame.frame_hash) == 64
    assert len(frame.terminal_state_hash) == 64


def test_versioned_d2a_record_mapping_is_supported() -> None:
    event = _snapshot(_tracker(), yes=[["0.42", "3"]], no=[["0.56", "5"]])

    result = KalshiWsBookRebuilder().apply(event.to_record())

    assert result.disposition is RebuildDisposition.FRAME_EMITTED
    assert result.frame is not None
    assert result.frame.market_ticker == MARKET


def test_rebuild_does_not_mutate_input_envelopes() -> None:
    tracker = _tracker()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[["0.56", "5"]])
    delta = _delta(tracker, side="yes", price="0.42", delta="1")
    records = [snapshot.to_record(), delta.to_record()]
    before = deepcopy(records)
    rebuilder = KalshiWsBookRebuilder()

    results = [rebuilder.apply(record) for record in records]

    assert all(result.frame is not None for result in results)
    assert records == before


def test_unified_yes_price_metadata_does_not_complement_no_levels() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    acknowledgement = _ack(tracker, use_yes_price=True)
    snapshot = _snapshot(
        tracker,
        yes=[["0.42", "3"]],
        no=[["0.44", "5"]],
        local_row_index=2,
        seq=2,
    )

    ack_result = rebuilder.apply(acknowledgement)
    result = rebuilder.apply(snapshot)

    assert ack_result.disposition is RebuildDisposition.IGNORED_NON_ORDERBOOK
    assert result.frame is not None
    assert result.frame.pricing_mode is PricingMode.UNIFIED_YES_PRICE
    assert result.frame.pricing_mode_source is PricingModeSource.D2A_SUBSCRIPTION_METADATA
    assert result.frame.pricing_mode_assumption is None
    assert _levels(result.frame.canonical_yes_asks) == [
        (Decimal("0.44"), Decimal("5"))
    ]


def test_subscription_params_bind_explicit_future_pricing_mode() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    subscription = tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 41,
            "params": {
                "channels": ["orderbook_delta"],
                "use_yes_price": True,
            },
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1001,
    )
    snapshot = _snapshot(
        tracker,
        yes=[["0.42", "3"]],
        no=[["0.44", "5"]],
        local_row_index=2,
        seq=2,
    )

    rebuilder.apply(subscription)
    result = rebuilder.apply(snapshot)

    assert result.frame is not None
    assert result.frame.pricing_mode is PricingMode.UNIFIED_YES_PRICE
    assert result.frame.pricing_mode_source is PricingModeSource.D2A_SUBSCRIPTION_METADATA
    assert result.frame.pricing_mode_assumption is None
    assert _levels(result.frame.canonical_yes_asks) == [
        (Decimal("0.44"), Decimal("5"))
    ]


@pytest.mark.parametrize("value", ["true", 1, None])
def test_unknown_pricing_mode_metadata_is_quarantined(value: object) -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    event = _snapshot(
        tracker,
        yes=[["0.42", "3"]],
        no=[["0.56", "5"]],
        use_yes_price=value,
    )

    result = rebuilder.apply(event)
    state = rebuilder.state_for(
        event.native_market_ticker,
        event.connection_id,
        event.segment_id,
    )

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.UNKNOWN_PRICING_MODE
    assert result.frame is None
    assert state is not None
    assert state.segment_validity is SegmentValidity.INVALID


def test_contradictory_pricing_mode_invalidates_segment() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_ack(tracker, use_yes_price=False))
    event = _snapshot(
        tracker,
        yes=[["0.42", "3"]],
        no=[["0.44", "5"]],
        use_yes_price=True,
        local_row_index=2,
        seq=2,
    )

    result = rebuilder.apply(event)
    state = rebuilder.state_for(
        event.native_market_ticker,
        event.connection_id,
        event.segment_id,
    )

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.CONTRADICTORY_PRICING_MODE
    assert result.frame is None
    assert state is not None
    assert state.segment_validity is SegmentValidity.INVALID


def test_pricing_metadata_conflict_quarantines_the_rest_of_segment() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_ack(tracker, use_yes_price=False))
    rebuilder.apply(_ack(tracker, use_yes_price=True, local_row_index=2))

    result = rebuilder.apply(
        _snapshot(
            tracker,
            yes=[["0.42", "3"]],
            no=[["0.56", "5"]],
            local_row_index=3,
            seq=3,
        )
    )

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.CONTRADICTORY_PRICING_MODE
    assert result.frame is None


@pytest.mark.parametrize(
    ("sid", "market_ticker"),
    [(99, None), (41, OTHER_MARKET)],
)
def test_control_frame_identity_mismatch_is_quarantined(
    sid: int,
    market_ticker: str | None,
) -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_ack(tracker, use_yes_price=False))
    payload: dict[str, object] = {
        "type": "subscribed",
        "id": 1,
        "sid": sid,
        "msg": {"channel": "orderbook_delta", "use_yes_price": False},
    }
    if market_ticker is not None:
        payload["market_ticker"] = market_ticker

    result = rebuilder.apply(
        tracker.record(
            payload,
            local_row_index=2,
            received_at_utc=RECEIVED_AT,
            received_monotonic_ns=1002,
        )
    )

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.IDENTITY_MISMATCH


def test_distinct_public_channel_sids_do_not_cross_invalidate_orderbook() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    orderbook_ack = tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 41,
            "msg": {"channel": "orderbook_delta", "use_yes_price": False},
        },
        local_row_index=1,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1001,
    )
    trade_ack = tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 42,
            "msg": {"channel": "trade"},
        },
        local_row_index=2,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1002,
    )

    assert rebuilder.apply(orderbook_ack).disposition is RebuildDisposition.IGNORED_NON_ORDERBOOK
    assert rebuilder.apply(trade_ack).disposition is RebuildDisposition.IGNORED_NON_ORDERBOOK
    snapshot = _snapshot(
        tracker,
        yes=[["0.42", "3"]],
        no=[],
        local_row_index=3,
        seq=1,
    )
    delta = _delta(
        tracker,
        side="yes",
        price="0.42",
        delta="1",
        sid=41,
        local_row_index=4,
        seq=2,
    )

    snapshot_result = rebuilder.apply(snapshot)
    delta_result = rebuilder.apply(delta)

    assert snapshot_result.disposition is RebuildDisposition.FRAME_EMITTED
    assert snapshot_result.frame is not None
    assert snapshot_result.frame.subscription_sid == 41
    assert delta_result.disposition is RebuildDisposition.FRAME_EMITTED


def test_public_channels_may_reuse_same_numeric_sid() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    for local_row_index, channel in enumerate(("orderbook_delta", "trade"), start=1):
        result = rebuilder.apply(
            tracker.record(
                {
                    "type": "subscribed",
                    "id": 1,
                    "sid": 41,
                    "msg": {"channel": channel},
                },
                local_row_index=local_row_index,
                received_at_utc=RECEIVED_AT,
                received_monotonic_ns=1000 + local_row_index,
            )
        )
        assert result.disposition is RebuildDisposition.IGNORED_NON_ORDERBOOK


def test_unknown_orderbook_sid_is_quarantined() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_ack(tracker, use_yes_price=False))
    mismatched = _snapshot(
        tracker,
        yes=[["0.42", "3"]],
        no=[],
        local_row_index=2,
        seq=1,
        sid=99,
    )

    result = rebuilder.apply(mismatched)

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.IDENTITY_MISMATCH
    assert result.frame is None


def test_error_control_frame_identity_mismatch_is_quarantined() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_ack(tracker, use_yes_price=False))

    result = rebuilder.apply(
        tracker.record(
            {
                "type": "error",
                "id": 1,
                "sid": 99,
                "msg": {"channel": "orderbook_delta", "error": "rejected"},
            },
            local_row_index=2,
            received_at_utc=RECEIVED_AT,
            received_monotonic_ns=1002,
        )
    )

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.IDENTITY_MISMATCH


def test_control_frame_market_id_mismatch_is_quarantined() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(snapshot)

    result = rebuilder.apply(
        tracker.record(
            {
                "type": "ack",
                "id": 1,
                "sid": 41,
                "market_ticker": MARKET,
                "market_id": "different-market-id",
                "msg": {"channel": "orderbook_delta"},
            },
            local_row_index=2,
            received_at_utc=RECEIVED_AT,
            received_monotonic_ns=1002,
        )
    )

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.IDENTITY_MISMATCH


def test_late_subscription_metadata_cannot_reprice_an_existing_book() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[["0.56", "5"]])
    rebuilder.apply(snapshot)

    result = rebuilder.apply(
        _ack(tracker, use_yes_price=True, local_row_index=2)
    )
    state = rebuilder.state_for(MARKET, snapshot.connection_id, snapshot.segment_id)

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.CONTRADICTORY_PRICING_MODE
    assert state is not None
    assert state.segment_validity is SegmentValidity.INVALID
    assert state.pricing_mode is PricingMode.LEGACY_SIDE_PRICE


def test_snapshot_omits_zero_levels_and_represents_one_sided_book() -> None:
    event = _snapshot(
        _tracker(),
        yes=[["0.42", "0"], ["0.41", "2.125"]],
        no=[],
    )

    result = KalshiWsBookRebuilder().apply(event)

    assert result.frame is not None
    assert _levels(result.frame.native_yes_bids) == [
        (Decimal("0.41"), Decimal("2.125"))
    ]
    assert result.frame.native_no_bids == ()
    assert result.frame.canonical_yes_asks == ()
    assert result.frame.book_state is CanonicalBookState.YES_BIDS_ONLY


def test_empty_yes_side_is_explicit() -> None:
    result = KalshiWsBookRebuilder().apply(
        _snapshot(_tracker(), yes=[], no=[["0.56", "1"]])
    )

    assert result.frame is not None
    assert result.frame.book_state is CanonicalBookState.YES_ASKS_ONLY
    assert result.frame.canonical_yes_bids == ()


def test_resnapshot_atomically_replaces_prior_state() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    first = _snapshot(tracker, yes=[["0.42", "3"]], no=[["0.56", "5"]])
    second = _snapshot(
        tracker,
        yes=[["0.40", "7"]],
        no=[],
        local_row_index=2,
        seq=2,
    )

    first_result = rebuilder.apply(first)
    second_result = rebuilder.apply(second)

    assert first_result.frame is not None
    assert second_result.frame is not None
    assert _levels(second_result.frame.native_yes_bids) == [
        (Decimal("0.40"), Decimal("7"))
    ]
    assert second_result.frame.native_no_bids == ()
    assert second_result.frame.reset_reason is SnapshotResetReason.RESNAPSHOT_SAME_SEGMENT
    assert second_result.frame.frame_count == 2


@pytest.mark.parametrize(
    ("yes", "no", "yes_presence", "no_presence", "book_state"),
    [
        (
            [["0.42", "3"]],
            ...,
            SnapshotSidePresence.PRESENT_NONEMPTY,
            SnapshotSidePresence.OMITTED_CONFIRMED_EMPTY,
            CanonicalBookState.YES_BIDS_ONLY,
        ),
        (
            ...,
            [["0.56", "5"]],
            SnapshotSidePresence.OMITTED_CONFIRMED_EMPTY,
            SnapshotSidePresence.PRESENT_NONEMPTY,
            CanonicalBookState.YES_ASKS_ONLY,
        ),
        (
            [],
            [],
            SnapshotSidePresence.PRESENT_EMPTY,
            SnapshotSidePresence.PRESENT_EMPTY,
            CanonicalBookState.EMPTY,
        ),
    ],
)
def test_official_optional_snapshot_sides_are_normalized(
    yes: object,
    no: object,
    yes_presence: SnapshotSidePresence,
    no_presence: SnapshotSidePresence,
    book_state: CanonicalBookState,
) -> None:
    result = KalshiWsBookRebuilder().apply(_snapshot(_tracker(), yes=yes, no=no))

    assert result.frame is not None
    assert result.frame.snapshot_yes_presence is yes_presence
    assert result.frame.snapshot_no_presence is no_presence
    assert result.frame.book_state is book_state
    assert result.frame.schema_version == "edmn.kalshi.ws.book.frame.v2"
    assert len(result.frame.frame_hash) == 64
    assert len(result.frame.terminal_state_hash) == 64


@pytest.mark.parametrize(
    ("yes", "no", "expected_reason"),
    [
        (..., ..., RebuildReason.SNAPSHOT_BOTH_SIDES_OMITTED),
        (..., None, RebuildReason.SNAPSHOT_NULL_SIDE),
        (None, [], RebuildReason.SNAPSHOT_NULL_SIDE),
        (..., "not-levels", RebuildReason.SNAPSHOT_WRONG_SIDE_TYPE),
        ({}, [], RebuildReason.SNAPSHOT_WRONG_SIDE_TYPE),
    ],
)
def test_invalid_snapshot_side_presence_fails_closed(
    yes: object,
    no: object,
    expected_reason: RebuildReason,
) -> None:
    result = KalshiWsBookRebuilder().apply(_snapshot(_tracker(), yes=yes, no=no))

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is expected_reason
    assert result.frame is None


def test_omitted_and_explicit_empty_sides_share_native_state_hash() -> None:
    omitted_tracker = _tracker()
    explicit_tracker = _tracker()
    omitted = _snapshot(omitted_tracker, yes=[["0.42", "3"]], no=...)
    explicit = _snapshot(explicit_tracker, yes=[["0.42", "3"]], no=[])
    omitted_result = KalshiWsBookRebuilder().apply(omitted)
    explicit_result = KalshiWsBookRebuilder().apply(explicit)

    assert omitted_result.frame is not None
    assert explicit_result.frame is not None
    assert omitted_result.frame.terminal_state_hash == explicit_result.frame.terminal_state_hash
    assert omitted.payload_sha256 != explicit.payload_sha256
    assert omitted_result.frame.snapshot_no_presence is SnapshotSidePresence.OMITTED_CONFIRMED_EMPTY
    assert explicit_result.frame.snapshot_no_presence is SnapshotSidePresence.PRESENT_EMPTY


def test_delta_can_add_first_level_to_omitted_side_and_remove_it() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_snapshot(tracker, yes=[["0.42", "3"]], no=...))

    added = rebuilder.apply(_delta(tracker, side="no", price="0.56", delta="2"))
    removed = rebuilder.apply(
        _delta(
            tracker,
            side="no",
            price="0.56",
            delta="-2",
            local_row_index=3,
            seq=3,
        )
    )

    assert added.frame is not None
    assert _levels(added.frame.native_no_bids) == [(Decimal("0.56"), Decimal("2"))]
    assert removed.frame is not None
    assert removed.frame.native_no_bids == ()
    assert removed.frame.snapshot_no_presence is SnapshotSidePresence.OMITTED_CONFIRMED_EMPTY


def test_resnapshot_can_switch_from_omitted_to_explicit_empty_side() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_snapshot(tracker, yes=[["0.42", "3"]], no=...))

    result = rebuilder.apply(
        _snapshot(
            tracker,
            yes=[["0.42", "3"]],
            no=[],
            local_row_index=2,
            seq=2,
        )
    )

    assert result.frame is not None
    assert result.frame.snapshot_no_presence is SnapshotSidePresence.PRESENT_EMPTY
    assert result.frame.native_no_bids == ()
    assert result.frame.segment_validity is SegmentValidity.VALID


def test_malformed_snapshot_is_atomic_and_invalidates_segment() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    first = _snapshot(tracker, yes=[["0.42", "3"]], no=[["0.56", "5"]])
    malformed = _snapshot(
        tracker,
        yes=[["0.40", "7"], ["bad-level"]],
        no=[],
        local_row_index=2,
        seq=2,
    )
    rebuilder.apply(first)

    result = rebuilder.apply(malformed)
    state = rebuilder.state_for(first.native_market_ticker, first.connection_id, first.segment_id)

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.MALFORMED_SNAPSHOT
    assert state is not None
    assert state.segment_validity is SegmentValidity.INVALID
    assert state.invalidation_reason is RebuildReason.MALFORMED_SNAPSHOT
    assert state.native_yes_bids == {Decimal("0.42"): Decimal("3")}


def test_duplicate_snapshot_price_is_rejected_atomically() -> None:
    event = _snapshot(
        _tracker(),
        yes=[["0.42", "3"], ["0.420", "4"]],
        no=[],
    )

    result = KalshiWsBookRebuilder().apply(event)

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.DUPLICATE_SNAPSHOT_PRICE
    assert result.frame is None


@pytest.mark.parametrize(
    ("side", "delta", "expected"),
    [
        ("yes", "1.125", [("0.42", "4.125")]),
        ("yes", "-1.125", [("0.42", "1.875")]),
        ("no", "2.25", [("0.56", "7.25")]),
        ("no", "-2.25", [("0.56", "2.75")]),
    ],
)
def test_signed_delta_updates_the_selected_native_side(
    side: str,
    delta: str,
    expected: list[tuple[str, str]],
) -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_snapshot(tracker, yes=[["0.42", "3"]], no=[["0.56", "5"]]))

    result = rebuilder.apply(
        _delta(tracker, side=side, price="0.42" if side == "yes" else "0.56", delta=delta)
    )

    assert result.disposition is RebuildDisposition.FRAME_EMITTED
    assert result.frame is not None
    levels = (
        result.frame.native_yes_bids if side == "yes" else result.frame.native_no_bids
    )
    assert _levels(levels) == [
        (Decimal(price), Decimal(quantity)) for price, quantity in expected
    ]
    assert result.frame.reset_reason is None
    assert result.frame.frame_count == 2


@pytest.mark.parametrize("side", ["yes", "no"])
def test_delta_exact_zero_deletes_level(side: str) -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    rebuilder.apply(_snapshot(tracker, yes=[["0.42", "3"]], no=[["0.56", "5"]]))

    result = rebuilder.apply(
        _delta(
            tracker,
            side=side,
            price="0.42" if side == "yes" else "0.56",
            delta="-3" if side == "yes" else "-5",
        )
    )

    assert result.frame is not None
    levels = (
        result.frame.native_yes_bids if side == "yes" else result.frame.native_no_bids
    )
    assert levels == ()


@pytest.mark.parametrize(
    ("price", "delta"),
    [("0.42", "-3.0001"), ("0.41", "-0.0001")],
)
def test_negative_resulting_quantity_invalidates_without_clamping(
    price: str,
    delta: str,
) -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(snapshot)

    result = rebuilder.apply(_delta(tracker, side="yes", price=price, delta=delta))
    state = rebuilder.state_for(
        snapshot.native_market_ticker,
        snapshot.connection_id,
        snapshot.segment_id,
    )

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.NEGATIVE_RESULTING_QUANTITY
    assert result.frame is None
    assert state is not None
    assert state.segment_validity is SegmentValidity.INVALID
    assert state.native_yes_bids == {Decimal("0.42"): Decimal("3")}


def test_admitted_delta_before_snapshot_invalidates_segment() -> None:
    tracker = _tracker()
    excluded = _delta(tracker, side="yes", price="0.42", delta="1")
    admitted = replace(
        excluded,
        admission_status=AdmissionStatus.ADMITTED,
        exclusion_reason=None,
        resync_state=ResyncState.RESYNCED_WITH_SNAPSHOT,
    )
    rebuilder = KalshiWsBookRebuilder()

    result = rebuilder.apply(admitted)
    state = rebuilder.state_for(
        admitted.native_market_ticker,
        admitted.connection_id,
        admitted.segment_id,
    )

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.DELTA_BEFORE_SNAPSHOT
    assert state is not None
    assert state.snapshot_received is False
    assert state.segment_validity is SegmentValidity.INVALID


@pytest.mark.parametrize(
    ("bad_seq", "expected_reason"),
    [
        (10, ExclusionReason.SEQUENCE_DUPLICATE),
        (9, ExclusionReason.SEQUENCE_OUT_OF_ORDER),
        (12, ExclusionReason.SEQUENCE_GAP),
    ],
)
def test_d2a_excluded_sequence_row_does_not_mutate_state(
    bad_seq: int,
    expected_reason: ExclusionReason,
) -> None:
    tracker = _tracker(
        continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT
    )
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(
        tracker,
        yes=[["0.42", "3"]],
        no=[],
        seq=10,
    )
    rebuilder.apply(snapshot)
    before_hash = rebuilder.terminal_state_hash(
        MARKET,
        snapshot.connection_id,
        snapshot.segment_id,
    )
    excluded = _delta(
        tracker,
        side="yes",
        price="0.42",
        delta="99",
        seq=bad_seq,
    )

    result = rebuilder.apply(excluded)

    assert excluded.admission_status is AdmissionStatus.EXCLUDED
    assert excluded.exclusion_reason is expected_reason
    assert result.disposition is RebuildDisposition.EXCLUDED
    assert result.reason is RebuildReason.D2A_ROW_EXCLUDED
    assert (
        rebuilder.terminal_state_hash(
            MARKET,
            snapshot.connection_id,
            snapshot.segment_id,
        )
        == before_hash
    )


def test_invalid_segment_excludes_deltas_until_fresh_snapshot_recovers() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(snapshot)
    rebuilder.apply(_delta(tracker, side="yes", price="0.42", delta="-4"))

    blocked = rebuilder.apply(
        _delta(tracker, side="yes", price="0.42", delta="1", local_row_index=3, seq=3)
    )
    recovered = rebuilder.apply(
        _snapshot(
            tracker,
            yes=[["0.40", "7"]],
            no=[],
            local_row_index=4,
            seq=4,
        )
    )
    after_recovery = rebuilder.apply(
        _delta(
            tracker,
            side="yes",
            price="0.40",
            delta="0.5",
            local_row_index=5,
            seq=5,
        )
    )

    assert blocked.disposition is RebuildDisposition.EXCLUDED
    assert blocked.reason is RebuildReason.SEGMENT_INVALID
    assert recovered.frame is not None
    assert recovered.frame.reset_reason is SnapshotResetReason.RECOVERY_AFTER_INVALIDATION
    assert after_recovery.frame is not None
    assert _levels(after_recovery.frame.native_yes_bids) == [
        (Decimal("0.40"), Decimal("7.5"))
    ]


def test_snapshot_for_one_market_does_not_mutate_another_market() -> None:
    tracker = _tracker(markets=(MARKET, OTHER_MARKET))
    rebuilder = KalshiWsBookRebuilder()
    market_a = _snapshot(tracker, yes=[["0.42", "3"]], no=[], seq=1)
    market_b = _snapshot(
        tracker,
        yes=[["0.31", "8"]],
        no=[["0.68", "9"]],
        market_ticker=OTHER_MARKET,
        market_id="market-id-2",
        local_row_index=2,
        seq=2,
    )

    rebuilder.apply(market_a)
    rebuilder.apply(market_b)
    before_b = rebuilder.terminal_state_hash(
        OTHER_MARKET,
        market_b.connection_id,
        market_b.segment_id,
    )
    rebuilder.apply(
        _snapshot(
            tracker,
            yes=[["0.40", "7"]],
            no=[],
            local_row_index=3,
            seq=3,
        )
    )

    state_a = rebuilder.state_for(MARKET, market_a.connection_id, market_a.segment_id)
    state_b = rebuilder.state_for(
        OTHER_MARKET,
        market_b.connection_id,
        market_b.segment_id,
    )
    assert state_a is not None
    assert state_b is not None
    assert state_a.native_yes_bids == {Decimal("0.40"): Decimal("7")}
    assert state_b.native_yes_bids == {Decimal("0.31"): Decimal("8")}
    assert (
        rebuilder.terminal_state_hash(
            OTHER_MARKET,
            market_b.connection_id,
            market_b.segment_id,
        )
        == before_b
    )


def test_same_market_has_independent_state_per_segment() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    first = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(first)
    tracker.bind_subscription(command_id=2)
    second = _snapshot(
        tracker,
        yes=[["0.35", "9"]],
        no=[],
        local_row_index=2,
        seq=1,
    )

    second_result = rebuilder.apply(second)

    assert first.segment_id != second.segment_id
    assert second_result.frame is not None
    assert second_result.frame.reset_reason is SnapshotResetReason.INITIAL_SNAPSHOT
    first_state = rebuilder.state_for(MARKET, first.connection_id, first.segment_id)
    second_state = rebuilder.state_for(MARKET, second.connection_id, second.segment_id)
    assert first_state is not None
    assert second_state is not None
    assert first_state.native_yes_bids == {Decimal("0.42"): Decimal("3")}
    assert second_state.native_yes_bids == {Decimal("0.35"): Decimal("9")}


def test_same_market_has_independent_state_per_connection() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    first = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(first)
    tracker.start_connection()
    tracker.bind_subscription(command_id=2)
    second = _snapshot(
        tracker,
        yes=[["0.35", "9"]],
        no=[],
        local_row_index=2,
        seq=1,
    )

    rebuilder.apply(second)

    assert first.connection_id != second.connection_id
    first_state = rebuilder.state_for(MARKET, first.connection_id, first.segment_id)
    second_state = rebuilder.state_for(MARKET, second.connection_id, second.segment_id)
    assert first_state is not None
    assert second_state is not None
    assert first_state.native_yes_bids == {Decimal("0.42"): Decimal("3")}
    assert second_state.native_yes_bids == {Decimal("0.35"): Decimal("9")}


def test_sid_change_cannot_mutate_the_prior_segment() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(snapshot)
    before = rebuilder.terminal_state_hash(
        MARKET,
        snapshot.connection_id,
        snapshot.segment_id,
    )

    delta = _delta(
        tracker,
        side="yes",
        price="0.42",
        delta="5",
        sid=42,
    )
    result = rebuilder.apply(delta)

    assert delta.segment_id != snapshot.segment_id
    assert delta.exclusion_reason is ExclusionReason.DELTA_BEFORE_SNAPSHOT
    assert result.disposition is RebuildDisposition.EXCLUDED
    assert rebuilder.state_for(MARKET, delta.connection_id, delta.segment_id) is None
    assert (
        rebuilder.terminal_state_hash(
            MARKET,
            snapshot.connection_id,
            snapshot.segment_id,
        )
        == before
    )


def test_cross_market_delta_is_excluded_without_mutating_existing_market() -> None:
    tracker = _tracker(markets=(MARKET, OTHER_MARKET))
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(snapshot)
    before = rebuilder.terminal_state_hash(
        MARKET,
        snapshot.connection_id,
        snapshot.segment_id,
    )

    delta = _delta(
        tracker,
        side="yes",
        price="0.31",
        delta="4",
        market_ticker=OTHER_MARKET,
        market_id="market-id-2",
    )
    result = rebuilder.apply(delta)

    assert delta.exclusion_reason is ExclusionReason.DELTA_BEFORE_SNAPSHOT
    assert result.disposition is RebuildDisposition.EXCLUDED
    assert rebuilder.state_for(
        OTHER_MARKET,
        delta.connection_id,
        delta.segment_id,
    ) is None
    assert (
        rebuilder.terminal_state_hash(
            MARKET,
            snapshot.connection_id,
            snapshot.segment_id,
        )
        == before
    )


def test_cross_segment_delta_is_excluded_without_mutating_prior_segment() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(snapshot)
    before = rebuilder.terminal_state_hash(
        MARKET,
        snapshot.connection_id,
        snapshot.segment_id,
    )
    tracker.bind_subscription(command_id=2)

    delta = _delta(tracker, side="yes", price="0.42", delta="4", seq=1)
    result = rebuilder.apply(delta)

    assert delta.segment_id != snapshot.segment_id
    assert result.disposition is RebuildDisposition.EXCLUDED
    assert rebuilder.state_for(MARKET, delta.connection_id, delta.segment_id) is None
    assert (
        rebuilder.terminal_state_hash(
            MARKET,
            snapshot.connection_id,
            snapshot.segment_id,
        )
        == before
    )


def test_changed_market_identity_invalidates_bound_state() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(snapshot)

    result = rebuilder.apply(
        _delta(
            tracker,
            side="yes",
            price="0.42",
            delta="1",
            market_id="different-market-id",
        )
    )

    state = rebuilder.state_for(MARKET, snapshot.connection_id, snapshot.segment_id)
    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.IDENTITY_MISMATCH
    assert state is not None
    assert state.segment_validity is SegmentValidity.INVALID
    assert state.native_yes_bids == {Decimal("0.42"): Decimal("3")}


def test_d2a_resync_snapshot_starts_fresh_segment_and_accepts_deltas() -> None:
    tracker = _tracker(
        continuity_policy=SequenceContinuityPolicy.CONTIGUOUS_INCREMENT
    )
    rebuilder = KalshiWsBookRebuilder()
    original = _snapshot(tracker, yes=[["0.42", "3"]], no=[], seq=10)
    rebuilder.apply(original)
    failed = _delta(tracker, side="yes", price="0.42", delta="9", seq=12)
    assert rebuilder.apply(failed).disposition is RebuildDisposition.EXCLUDED

    resynced = _snapshot(
        tracker,
        yes=[["0.40", "7"]],
        no=[],
        local_row_index=3,
        seq=20,
    )
    reset = rebuilder.apply(resynced)
    updated = rebuilder.apply(
        _delta(
            tracker,
            side="yes",
            price="0.40",
            delta="0.5",
            local_row_index=4,
            seq=21,
        )
    )

    assert resynced.segment_id != original.segment_id
    assert reset.frame is not None
    assert reset.frame.reset_reason is SnapshotResetReason.INITIAL_SNAPSHOT
    assert updated.frame is not None
    assert _levels(updated.frame.native_yes_bids) == [
        (Decimal("0.40"), Decimal("7.5"))
    ]


@pytest.mark.parametrize(
    ("yes", "no", "expected_reason"),
    [
        ([[True, "1"]], [], RebuildReason.MALFORMED_SNAPSHOT),
        ([[0.42, "1"]], [], RebuildReason.MALFORMED_SNAPSHOT),
        ([["NaN", "1"]], [], RebuildReason.MALFORMED_SNAPSHOT),
        ([["1.01", "1"]], [], RebuildReason.IMPOSSIBLE_PRICE),
        ([["0.42", "-1"]], [], RebuildReason.MALFORMED_SNAPSHOT),
    ],
)
def test_snapshot_exact_scalar_and_domain_validation(
    yes: list[list[object]],
    no: list[list[object]],
    expected_reason: RebuildReason,
) -> None:
    result = KalshiWsBookRebuilder().apply(_snapshot(_tracker(), yes=yes, no=no))

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is expected_reason


@pytest.mark.parametrize(
    ("side", "price", "delta", "expected_reason"),
    [
        ("YES", "0.42", "1", RebuildReason.MALFORMED_DELTA),
        (None, "0.42", "1", RebuildReason.MALFORMED_DELTA),
        ("yes", 0.42, "1", RebuildReason.MALFORMED_DELTA),
        ("yes", "0.42", False, RebuildReason.MALFORMED_DELTA),
        ("yes", "0.42", "Infinity", RebuildReason.MALFORMED_DELTA),
        ("yes", "-0.01", "1", RebuildReason.IMPOSSIBLE_PRICE),
    ],
)
def test_malformed_delta_invalidates_without_mutating_levels(
    side: object,
    price: object,
    delta: object,
    expected_reason: RebuildReason,
) -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[])
    rebuilder.apply(snapshot)

    result = rebuilder.apply(_delta(tracker, side=side, price=price, delta=delta))
    state = rebuilder.state_for(MARKET, snapshot.connection_id, snapshot.segment_id)

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is expected_reason
    assert state is not None
    assert state.native_yes_bids == {Decimal("0.42"): Decimal("3")}
    assert state.segment_validity is SegmentValidity.INVALID


@pytest.mark.parametrize(
    ("yes", "no", "expected"),
    [
        ([["0.60", "1"]], [["0.40", "2"]], CanonicalBookState.LOCKED),
        ([["0.61", "1"]], [["0.40", "2"]], CanonicalBookState.CROSSED),
    ],
)
def test_locked_and_crossed_canonical_books_are_labeled(
    yes: list[list[object]],
    no: list[list[object]],
    expected: CanonicalBookState,
) -> None:
    result = KalshiWsBookRebuilder().apply(_snapshot(_tracker(), yes=yes, no=no))

    assert result.frame is not None
    assert result.frame.book_state is expected


def test_canonical_ordering_and_subpenny_values_remain_exact() -> None:
    result = KalshiWsBookRebuilder().apply(
        _snapshot(
            _tracker(),
            yes=[["0.123456", "1.0000001"], ["0.234567", "2.0000002"]],
            no=[["0.765431", "3.0000003"], ["0.876543", "4.0000004"]],
        )
    )

    assert result.frame is not None
    assert _levels(result.frame.canonical_yes_bids) == [
        (Decimal("0.234567"), Decimal("2.0000002")),
        (Decimal("0.123456"), Decimal("1.0000001")),
    ]
    assert _levels(result.frame.canonical_yes_asks) == [
        (Decimal("0.123457"), Decimal("4.0000004")),
        (Decimal("0.234569"), Decimal("3.0000003")),
    ]


def test_precision_beyond_decimal_default_context_remains_exact() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(
        tracker,
        yes=[["0.42", "1.123456789012345678901234567890123456789"]],
        no=[["0.123456789012345678901234567890123456789", "2"]],
    )
    rebuilder.apply(snapshot)

    result = rebuilder.apply(
        _delta(
            tracker,
            side="yes",
            price="0.42",
            delta="0.000000000000000000000000000000000000001",
        )
    )

    assert result.frame is not None
    assert _levels(result.frame.native_yes_bids) == [
        (Decimal("0.42"), Decimal("1.123456789012345678901234567890123456790"))
    ]
    assert _levels(result.frame.canonical_yes_asks) == [
        (Decimal("0.876543210987654321098765432109876543211"), Decimal("2"))
    ]
    assert result.frame.to_record()["native_yes_bids"] == [
        {
            "price": "0.42",
            "quantity": "1.12345678901234567890123456789012345679",
        }
    ]


def test_identical_streams_have_identical_frame_and_terminal_hashes() -> None:
    tracker = _tracker()
    stream = [
        _snapshot(tracker, yes=[["0.42", "3"]], no=[["0.56", "5"]]),
        _delta(tracker, side="yes", price="0.42", delta="0.125"),
        _delta(
            tracker,
            side="no",
            price="0.56",
            delta="-0.25",
            local_row_index=3,
            seq=3,
        ),
    ]
    first = KalshiWsBookRebuilder()
    second = KalshiWsBookRebuilder()

    first_frames = [first.apply(event).frame for event in stream]
    second_frames = [second.apply(event).frame for event in stream]

    assert all(frame is not None for frame in first_frames + second_frames)
    assert [frame.frame_hash for frame in first_frames if frame] == [
        frame.frame_hash for frame in second_frames if frame
    ]
    final = stream[-1]
    assert first.terminal_state_hash(
        MARKET,
        final.connection_id,
        final.segment_id,
    ) == second.terminal_state_hash(MARKET, final.connection_id, final.segment_id)


def test_level_identity_and_pricing_mode_each_change_frame_hash() -> None:
    base_tracker = _tracker()
    changed_level_tracker = _tracker()
    changed_identity_tracker = _tracker(markets=(OTHER_MARKET,))
    base = KalshiWsBookRebuilder().apply(
        _snapshot(base_tracker, yes=[["0.42", "3"]], no=[["0.56", "5"]])
    )
    changed_level = KalshiWsBookRebuilder().apply(
        _snapshot(
            changed_level_tracker,
            yes=[["0.42", "3.0001"]],
            no=[["0.56", "5"]],
        )
    )
    changed_identity = KalshiWsBookRebuilder().apply(
        _snapshot(
            changed_identity_tracker,
            yes=[["0.42", "3"]],
            no=[["0.56", "5"]],
            market_ticker=OTHER_MARKET,
            market_id="market-id-2",
        )
    )
    false_tracker = _tracker()
    true_tracker = _tracker()
    false_rebuilder = KalshiWsBookRebuilder()
    true_rebuilder = KalshiWsBookRebuilder()
    false_rebuilder.apply(_ack(false_tracker, use_yes_price=False))
    true_rebuilder.apply(_ack(true_tracker, use_yes_price=True))
    false_mode = false_rebuilder.apply(
        _snapshot(
            false_tracker,
            yes=[["0.42", "3"]],
            no=[["0.56", "5"]],
            local_row_index=2,
            seq=2,
        )
    )
    true_mode = true_rebuilder.apply(
        _snapshot(
            true_tracker,
            yes=[["0.42", "3"]],
            no=[["0.56", "5"]],
            local_row_index=2,
            seq=2,
        )
    )

    assert base.frame is not None
    assert changed_level.frame is not None
    assert changed_identity.frame is not None
    assert false_mode.frame is not None
    assert true_mode.frame is not None
    assert base.frame.frame_hash != changed_level.frame.frame_hash
    assert base.frame.frame_hash != changed_identity.frame.frame_hash
    assert false_mode.frame.frame_hash != true_mode.frame.frame_hash


def test_serialized_frame_contains_no_binary_float() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(
        tracker,
        yes=[["0.123456", "1.0000001"]],
        no=[["0.876543", "2.0000002"]],
    )
    result = rebuilder.apply(snapshot)

    assert result.frame is not None
    assert not _contains_float(result.frame.to_record())
    state = rebuilder.state_for(MARKET, snapshot.connection_id, snapshot.segment_id)
    assert state is not None
    assert all(isinstance(value, Decimal) for value in state.native_yes_bids)
    assert all(isinstance(value, Decimal) for value in state.native_yes_bids.values())


def test_unsupported_future_schema_is_preserved_and_quarantined() -> None:
    record = _snapshot(_tracker(), yes=[["0.42", "3"]], no=[]).to_record()
    record["schema_version"] = "edmn.kalshi.ws.raw.v999"

    result = KalshiWsBookRebuilder().apply(record)

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.UNSUPPORTED_SCHEMA
    assert result.quarantined_record == record


def test_legacy_local_sequence_is_quarantined_not_promoted() -> None:
    record = {
        "record_type": "kalshi_demo_ws_message",
        "campaign_id": "legacy-campaign",
        "venue": "kalshi_demo",
        "market_tickers": [MARKET],
        "sequence": 73,
        "received_at": RECEIVED_AT.isoformat(),
        "message_type": "orderbook_delta",
        "payload": {
            "type": "orderbook_delta",
            "msg": {
                "market_ticker": MARKET,
                "side": "yes",
                "price_dollars": "0.42",
                "delta_fp": "1",
            },
        },
    }

    result = KalshiWsBookRebuilder().apply(record)

    assert result.disposition is RebuildDisposition.QUARANTINED
    assert result.reason is RebuildReason.LEGACY_IDENTITY_UNPROVEN
    assert result.frame is None
    assert result.key is None


def test_unknown_and_monotonic_sequence_states_are_preserved_not_promoted() -> None:
    tracker = _tracker()
    rebuilder = KalshiWsBookRebuilder()
    snapshot = _snapshot(tracker, yes=[["0.42", "3"]], no=[], seq=100)
    delta = _delta(tracker, side="yes", price="0.42", delta="1", seq=110)

    snapshot_result = rebuilder.apply(snapshot)
    delta_result = rebuilder.apply(delta)

    assert snapshot_result.frame is not None
    assert delta_result.frame is not None
    assert snapshot_result.frame.sequence_state is SequenceState.SEQUENCE_PRESENT_SEMANTICS_UNKNOWN
    assert delta_result.frame.sequence_state is SequenceState.SEQUENCE_OBSERVED_MONOTONIC
    assert delta_result.frame.sequence_state is not SequenceState.SEQUENCE_CONTIGUITY_VERIFIED


def _tracker(
    *,
    markets: tuple[str, ...] = (MARKET,),
    continuity_policy: SequenceContinuityPolicy = SequenceContinuityPolicy.UNKNOWN,
) -> KalshiWsIntegrityTracker:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=markets,
        continuity_policy=continuity_policy,
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1)
    return tracker


def _ack(
    tracker: KalshiWsIntegrityTracker,
    *,
    use_yes_price: object,
    local_row_index: int = 1,
):
    return tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 41,
            "msg": {"channel": "orderbook_delta", "use_yes_price": use_yes_price},
        },
        local_row_index=local_row_index,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1000 + local_row_index,
    )


def _snapshot(
    tracker: KalshiWsIntegrityTracker,
    *,
    yes: object = ...,
    no: object = ...,
    market_ticker: str = MARKET,
    market_id: str | None = "market-id-1",
    use_yes_price: object = ...,
    local_row_index: int = 1,
    seq: int = 1,
    sid: int = 41,
):
    msg: dict[str, object] = {
        "market_ticker": market_ticker,
    }
    if yes is not ...:
        msg["yes_dollars_fp"] = yes
    if no is not ...:
        msg["no_dollars_fp"] = no
    if market_id is not None:
        msg["market_id"] = market_id
    if use_yes_price is not ...:
        msg["use_yes_price"] = use_yes_price
    return tracker.record(
        {"type": "orderbook_snapshot", "sid": sid, "seq": seq, "msg": msg},
        local_row_index=local_row_index,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1000 + local_row_index,
    )


def _delta(
    tracker: KalshiWsIntegrityTracker,
    *,
    side: object,
    price: object,
    delta: object,
    market_ticker: str = MARKET,
    market_id: str | None = "market-id-1",
    sid: int = 41,
    local_row_index: int = 2,
    seq: int = 2,
):
    msg: dict[str, object] = {
        "market_ticker": market_ticker,
        "side": side,
        "price_dollars": price,
        "delta_fp": delta,
    }
    if market_id is not None:
        msg["market_id"] = market_id
    return tracker.record(
        {"type": "orderbook_delta", "sid": sid, "seq": seq, "msg": msg},
        local_row_index=local_row_index,
        received_at_utc=RECEIVED_AT,
        received_monotonic_ns=1000 + local_row_index,
    )


def _levels(
    levels: tuple[NativeLevel, ...] | tuple[CanonicalLevel, ...],
) -> list[tuple[Decimal, Decimal]]:
    return [(level.price, level.quantity) for level in levels]


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_float(item) for item in value)
    return False
