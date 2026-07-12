from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edmn_trader.adapters.kalshi.public_evidence import (
    ConnectionEvidenceEvent,
    ConnectionEvidenceSource,
    ConnectionEvidenceType,
    KeepaliveStatus,
    LifecycleSource,
    LifecycleStatus,
    LifecycleValidity,
    PublicTradeStreamStatus,
    build_public_trade_stream,
    evaluate_evidence_freshness,
    record_rest_lifecycle,
    write_public_trade_evidence,
)
from edmn_trader.adapters.kalshi.ws_events import (
    ExclusionReason,
    KalshiWsIntegrityTracker,
)
from edmn_trader.adapters.kalshi.ws_recorder import _source_type, _subscription_payload

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
MARKET = "DEMO-MARKET"
OTHER_MARKET = "DEMO-OTHER"


def test_selected_public_trade_is_preserved_exactly() -> None:
    event = _event(
        _tracker(markets=(MARKET, OTHER_MARKET)),
        {
            "type": "trade",
            "sid": 7,
            "seq": 101,
            "msg": {
                "trade_id": "trade-1",
                "market_ticker": MARKET,
                "yes_price": 42,
                "no_price": 58,
                "yes_price_dollars": "0.4200",
                "no_price_dollars": "0.5800",
                "count": 3,
                "count_fp": "3.125",
                "taker_side": "yes",
                "ts": 1_788_000_001,
            },
        },
    )
    before = event.to_record()

    stream = build_public_trade_stream([event], selected_market_tickers=(MARKET,))

    assert stream.status is PublicTradeStreamStatus.OBSERVED
    assert len(stream.trades) == 1
    trade = stream.trades[0]
    assert trade.market_ticker == MARKET
    assert trade.native_trade_id == "trade-1"
    assert trade.native_sid == 7
    assert trade.native_seq == 101
    assert trade.native_exchange_ts == 1_788_000_001
    assert trade.is_account_fill is False
    assert trade.native_trade_payload == before["original_payload"]["msg"]
    assert event.to_record() == before


def test_nonselected_public_trade_is_filtered() -> None:
    event = _trade_event(market_ticker=OTHER_MARKET)

    stream = build_public_trade_stream([event], selected_market_tickers=(MARKET,))

    assert stream.status is PublicTradeStreamStatus.QUIET_NO_PUBLIC_TRADES
    assert stream.trades == ()
    assert stream.filtered_nonselected_count == 1


def test_trade_evidence_file_contains_only_selected_market(
    tmp_path: Path,
) -> None:
    stream = build_public_trade_stream(
        [_trade_event(market_ticker=MARKET), _trade_event(market_ticker=OTHER_MARKET)],
        selected_market_tickers=(MARKET,),
    )

    count = write_public_trade_evidence(tmp_path / "public_trades.jsonl", stream)
    records = [
        json.loads(line)
        for line in (tmp_path / "public_trades.jsonl").read_text().splitlines()
    ]

    assert count == 1
    assert [record["market_ticker"] for record in records] == [MARKET]


def test_account_fill_is_not_public_trade_evidence() -> None:
    with pytest.raises(ValueError, match="private account/order data"):
        _event(
            _tracker(),
            {
                "type": "fill",
                "msg": {
                    "fill_id": "fill-1",
                    "order_id": "order-1",
                    "market_ticker": MARKET,
                },
            },
        )


def test_account_like_fields_quarantine_mislabeled_trade() -> None:
    with pytest.raises(ValueError, match="private account/order data"):
        _event(
            _tracker(),
            {
                "type": "trade",
                "msg": {
                    "trade_id": "trade-1",
                    "order_id": "order-1",
                    "market_ticker": MARKET,
                },
            },
        )


def test_trade_missing_market_identity_is_quarantined() -> None:
    event = _event(
        _tracker(),
        {
            "type": "trade",
            "msg": {
                "trade_id": "trade-1",
                "yes_price_dollars": "0.4200",
                "count_fp": "1",
            },
        },
    )

    stream = build_public_trade_stream([event], selected_market_tickers=(MARKET,))

    assert stream.trades == ()
    assert stream.quarantined_count == 1
    assert stream.filtered_nonselected_count == 0
    assert stream.status is PublicTradeStreamStatus.QUARANTINED_INPUT


def test_trade_with_wrong_channel_sid_is_quarantined() -> None:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=(MARKET,),
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1, channels=("orderbook_delta", "trade"))
    tracker.record(
        {
            "type": "subscribed",
            "id": 1,
            "sid": 7,
            "msg": {"channel": "trade"},
        },
        local_row_index=1,
        received_at_utc=NOW,
        received_monotonic_ns=1,
    )
    event = tracker.record(
        {
            "type": "trade",
            "sid": 8,
            "seq": 1,
            "msg": {"trade_id": "wrong-sid", "market_ticker": MARKET},
        },
        local_row_index=2,
        received_at_utc=NOW,
        received_monotonic_ns=2,
    )

    stream = build_public_trade_stream([event], selected_market_tickers=(MARKET,))

    assert event.exclusion_reason is ExclusionReason.SUBSCRIPTION_IDENTITY_MISMATCH
    assert stream.trade_count == 0
    assert stream.quarantined_count == 1
    assert stream.status is PublicTradeStreamStatus.QUARANTINED_INPUT


def test_accepted_trade_does_not_hide_quarantined_input() -> None:
    malformed = _event(
        _tracker(),
        {
            "type": "trade",
            "msg": {"trade_id": "malformed-no-market"},
        },
    )

    stream = build_public_trade_stream(
        [_trade_event(), malformed],
        selected_market_tickers=(MARKET,),
    )

    assert stream.trade_count == 1
    assert stream.quarantined_count == 1
    assert stream.status is PublicTradeStreamStatus.QUARANTINED_INPUT


def test_conflicting_trade_identity_is_quarantined_without_aborting_stream() -> None:
    conflicting = _event(
        _tracker(markets=(MARKET, OTHER_MARKET)),
        {
            "type": "trade",
            "market_ticker": MARKET,
            "msg": {
                "trade_id": "conflicting-trade",
                "market_ticker": OTHER_MARKET,
            },
        },
    )

    stream = build_public_trade_stream(
        [conflicting, _trade_event()],
        selected_market_tickers=(MARKET,),
    )

    assert stream.trade_count == 1
    assert stream.quarantined_count == 1
    assert stream.status is PublicTradeStreamStatus.QUARANTINED_INPUT


def test_zero_trade_fixture_is_valid_quiet_market_evidence() -> None:
    stream = build_public_trade_stream([], selected_market_tickers=(MARKET,))

    assert stream.status is PublicTradeStreamStatus.QUIET_NO_PUBLIC_TRADES
    assert stream.trade_count == 0
    assert stream.quarantined_count == 0


def test_fixture_subscription_includes_orderbook_and_public_trade_channels() -> None:
    assert json.loads(_subscription_payload((MARKET,))) == {
        "id": 1,
        "cmd": "subscribe",
        "params": {
            "channels": ["orderbook_delta", "trade"],
            "market_tickers": [MARKET],
            "use_yes_price": False,
        },
    }


@pytest.mark.parametrize(
    ("snapshot_count", "delta_count", "trade_count", "expected"),
    [
        (1, 0, 0, "WEBSOCKET_SNAPSHOT"),
        (1, 1, 0, "WEBSOCKET_DELTA"),
        (0, 0, 1, "WEBSOCKET_PUBLIC_TRADE"),
        (0, 0, 0, "WEBSOCKET_NO_ORDERBOOK"),
    ],
)
def test_recorder_source_type_does_not_call_trade_a_snapshot(
    snapshot_count: int,
    delta_count: int,
    trade_count: int,
    expected: str,
) -> None:
    assert _source_type(snapshot_count, delta_count, trade_count) == expected


@pytest.mark.parametrize(
    ("raw_status", "expected_status"),
    [
        ("active", LifecycleStatus.OPEN),
        ("closed", LifecycleStatus.CLOSED),
        ("finalized", LifecycleStatus.SETTLED),
        ("future_value", LifecycleStatus.UNKNOWN),
    ],
)
def test_rest_lifecycle_status_transitions(
    raw_status: str,
    expected_status: LifecycleStatus,
) -> None:
    evidence = record_rest_lifecycle(
        {
            "ticker": MARKET,
            "status": raw_status,
        },
        selected_market_ticker=MARKET,
        observed_at_utc=NOW - timedelta(seconds=30),
        evaluated_at_utc=NOW,
        max_age_seconds=60,
    )

    assert evidence.source is LifecycleSource.REST_FALLBACK
    assert evidence.raw_status == raw_status
    assert evidence.lifecycle_status is expected_status
    assert evidence.observation_age_seconds == 30
    assert evidence.proves_websocket_transport is False
    assert evidence.validity is (
        LifecycleValidity.UNKNOWN_STATUS
        if expected_status is LifecycleStatus.UNKNOWN
        else LifecycleValidity.VALID
    )


def test_rest_lifecycle_preserves_existing_raw_status_provenance() -> None:
    evidence = record_rest_lifecycle(
        {
            "ticker": MARKET,
            "status": "open",
            "raw_status": "active",
        },
        selected_market_ticker=MARKET,
        observed_at_utc=NOW,
        evaluated_at_utc=NOW,
        max_age_seconds=60,
    )

    assert evidence.raw_status == "active"
    assert evidence.normalized_status == "open"
    assert evidence.lifecycle_status is LifecycleStatus.OPEN


def test_stale_lifecycle_observation_is_not_valid() -> None:
    evidence = record_rest_lifecycle(
        {"ticker": MARKET, "status": "active"},
        selected_market_ticker=MARKET,
        observed_at_utc=NOW - timedelta(seconds=61),
        evaluated_at_utc=NOW,
        max_age_seconds=60,
    )

    assert evidence.lifecycle_status is LifecycleStatus.OPEN
    assert evidence.validity is LifecycleValidity.STALE
    assert evidence.observation_age_seconds == 61


def test_fractional_age_rounds_up_at_stale_boundary() -> None:
    evidence = record_rest_lifecycle(
        {"ticker": MARKET, "status": "active"},
        selected_market_ticker=MARKET,
        observed_at_utc=NOW - timedelta(seconds=60, microseconds=1),
        evaluated_at_utc=NOW,
        max_age_seconds=60,
    )

    assert evidence.observation_age_seconds == 61
    assert evidence.validity is LifecycleValidity.STALE


def test_mve_lifecycle_is_explicitly_unsupported() -> None:
    evidence = record_rest_lifecycle(
        {
            "ticker": MARKET,
            "status": "active",
            "market_type": "mve",
        },
        selected_market_ticker=MARKET,
        observed_at_utc=NOW,
        evaluated_at_utc=NOW,
        max_age_seconds=60,
    )

    assert evidence.validity is LifecycleValidity.MVE_UNSUPPORTED


def test_nonselected_lifecycle_observation_is_rejected() -> None:
    with pytest.raises(ValueError, match="selected market"):
        record_rest_lifecycle(
            {"ticker": OTHER_MARKET, "status": "active"},
            selected_market_ticker=MARKET,
            observed_at_utc=NOW,
            evaluated_at_utc=NOW,
            max_age_seconds=60,
        )


@pytest.mark.parametrize("event_type", list(ConnectionEvidenceType))
def test_connection_evidence_event_types(event_type: ConnectionEvidenceType) -> None:
    event = ConnectionEvidenceEvent(
        event_type=event_type,
        observed_at_utc=NOW,
        connection_id="connection-1",
        segment_id="segment-1",
        reason="synthetic_fixture",
    )

    assert event.source is ConnectionEvidenceSource.RECORDER_OBSERVATION
    assert event.event_type is event_type
    assert event.reason == "synthetic_fixture"


def test_hard_evidence_flags_cannot_be_overridden() -> None:
    stream = build_public_trade_stream(
        [_trade_event()],
        selected_market_tickers=(MARKET,),
    )
    trade = stream.trades[0]
    lifecycle = record_rest_lifecycle(
        {"ticker": MARKET, "status": "active"},
        selected_market_ticker=MARKET,
        observed_at_utc=NOW,
        evaluated_at_utc=NOW,
        max_age_seconds=60,
    )

    with pytest.raises(ValueError, match="init=False"):
        replace(trade, is_account_fill=True)
    with pytest.raises(ValueError, match="init=False"):
        replace(lifecycle, proves_websocket_transport=True)
    with pytest.raises(ValueError, match="private account/order data"):
        replace(
            trade,
            native_trade_payload={
                **trade.native_trade_payload,
                "order_id": "order-1",
            },
        )
    with pytest.raises(ValueError, match="stream status"):
        replace(stream, status=PublicTradeStreamStatus.QUIET_NO_PUBLIC_TRADES)
    with pytest.raises(ValueError, match="lifecycle status"):
        replace(lifecycle, lifecycle_status=LifecycleStatus.UNKNOWN)
    with pytest.raises(ValueError, match="raw and normalized"):
        replace(lifecycle, raw_status="closed")


def test_keepalive_record_rejects_inconsistent_direct_mutation() -> None:
    freshness = evaluate_evidence_freshness(
        evaluated_at_utc=NOW,
        transport_keepalive_observed_at_utc=NOW,
        transport_keepalive_source="PING_PONG",
    )

    with pytest.raises(ValueError, match="inconsistent"):
        replace(
            freshness,
            transport_keepalive_status=KeepaliveStatus.UNKNOWN_NOT_OBSERVED,
        )


def test_keepalive_observed_and_unknown_are_distinct() -> None:
    unknown = evaluate_evidence_freshness(
        evaluated_at_utc=NOW,
        lifecycle_observed_at_utc=NOW - timedelta(seconds=20),
        orderbook_event_at_utc=NOW - timedelta(seconds=90),
    )
    observed = evaluate_evidence_freshness(
        evaluated_at_utc=NOW,
        transport_keepalive_observed_at_utc=NOW - timedelta(seconds=5),
        transport_keepalive_source="PING_PONG",
        lifecycle_observed_at_utc=NOW - timedelta(seconds=20),
        orderbook_event_at_utc=NOW - timedelta(seconds=90),
    )

    assert unknown.transport_keepalive_status is KeepaliveStatus.UNKNOWN_NOT_OBSERVED
    assert unknown.transport_keepalive_age_seconds is None
    assert observed.transport_keepalive_status is KeepaliveStatus.OBSERVED
    assert observed.transport_keepalive_age_seconds == 5


def test_three_freshness_dimensions_remain_independent() -> None:
    freshness = evaluate_evidence_freshness(
        evaluated_at_utc=NOW,
        transport_keepalive_observed_at_utc=NOW - timedelta(seconds=7),
        transport_keepalive_source="PING_PONG",
        lifecycle_observed_at_utc=NOW - timedelta(seconds=31),
        orderbook_event_at_utc=NOW - timedelta(seconds=503),
    )

    assert freshness.transport_keepalive_age_seconds == 7
    assert freshness.lifecycle_observation_age_seconds == 31
    assert freshness.orderbook_event_quiet_interval_seconds == 503


def test_orderbook_age_never_becomes_transport_keepalive() -> None:
    freshness = evaluate_evidence_freshness(
        evaluated_at_utc=NOW,
        lifecycle_observed_at_utc=NOW,
        orderbook_event_at_utc=NOW - timedelta(seconds=1),
    )

    assert freshness.transport_keepalive_status is KeepaliveStatus.UNKNOWN_NOT_OBSERVED
    assert freshness.transport_keepalive_age_seconds is None
    assert freshness.orderbook_event_quiet_interval_seconds == 1


@pytest.mark.parametrize(
    ("observed_at", "source"),
    [(NOW, None), (None, "PING_PONG")],
)
def test_keepalive_timestamp_and_source_are_atomic(
    observed_at: datetime | None,
    source: str | None,
) -> None:
    with pytest.raises(ValueError, match="supplied together"):
        evaluate_evidence_freshness(
            evaluated_at_utc=NOW,
            transport_keepalive_observed_at_utc=observed_at,
            transport_keepalive_source=source,
        )


def _tracker(
    *,
    markets: tuple[str, ...] = (MARKET,),
) -> KalshiWsIntegrityTracker:
    tracker = KalshiWsIntegrityTracker(
        campaign_id="campaign-1",
        requested_market_tickers=markets,
    )
    tracker.start_connection()
    tracker.bind_subscription(command_id=1)
    return tracker


def _trade_event(*, market_ticker: str = MARKET):
    return _event(
        _tracker(markets=(MARKET, OTHER_MARKET)),
        {
            "type": "trade",
            "sid": 7,
            "seq": 101,
            "msg": {
                "trade_id": "trade-1",
                "market_ticker": market_ticker,
                "yes_price_dollars": "0.4200",
                "count_fp": "3.125",
                "ts": 1_788_000_001,
            },
        },
    )


def _event(
    tracker: KalshiWsIntegrityTracker,
    payload: dict[str, object],
):
    return tracker.record(
        deepcopy(payload),
        local_row_index=1,
        received_at_utc=NOW,
        received_monotonic_ns=1_000,
    )
