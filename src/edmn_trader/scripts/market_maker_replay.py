"""Run a finite Stage 6 market-maker replay in dry-run/demo modes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from edmn_trader.adapters.kalshi.client import KALSHI_DEMO_REST_BASE_URL
from edmn_trader.core import ExecutionMode, RiskLimits
from edmn_trader.data.jsonl import append_jsonl_record
from edmn_trader.data.replay import ReplaySession
from edmn_trader.execution import (
    DemoExecutionConfig,
    DemoExecutionRequest,
    FakeDemoExecutionAdapter,
    decide_execution_risk,
)
from edmn_trader.execution.demo import DemoExecutionAdapter
from edmn_trader.research import DryRunOrderIntent, DryRunQuoteEngine, QuoteEngineConfig

DEFAULT_LOG_OUTPUT = Path("/tmp/edmn_stage6_market_maker_replay.jsonl")
LIMITATION_NOTE = (
    "finite replay only; fake adapter only; no fills, PnL, live trading, or profitability claims"
)
ZERO = Decimal("0")

LifecycleAction = Literal["place", "replace", "cancel", "hold"]


@dataclass(frozen=True, slots=True)
class OpenQuote:
    """In-memory quote state for one side of the finite replay."""

    side: Literal["buy", "sell"]
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class MarketMakerReplayConfig:
    """Explicit Stage 6 replay controls."""

    execution_mode: ExecutionMode = ExecutionMode.DEMO
    demo_opt_in: bool = False
    base_url: str = KALSHI_DEMO_REST_BASE_URL
    current_position: Decimal = ZERO
    current_inventory: Decimal = ZERO
    current_daily_loss: Decimal = ZERO
    max_position_abs: Decimal = Decimal("10")
    max_order_quantity: Decimal = Decimal("2.00")
    max_notional: Decimal = Decimal("1.00")
    max_loss: Decimal = Decimal("5.00")
    max_open_orders: int = 2
    kill_switch: bool = False
    min_quote_change: Decimal = Decimal("0.0001")

    def __post_init__(self) -> None:
        for field_name in (
            "current_position",
            "current_inventory",
            "current_daily_loss",
            "max_position_abs",
            "max_order_quantity",
            "max_notional",
            "max_loss",
            "min_quote_change",
        ):
            if not isinstance(getattr(self, field_name), Decimal):
                msg = f"{field_name} must be a Decimal"
                raise TypeError(msg)
        if self.max_open_orders < 0:
            msg = "max_open_orders must be non-negative"
            raise ValueError(msg)
        if self.min_quote_change < ZERO:
            msg = "min_quote_change must be non-negative"
            raise ValueError(msg)

    @property
    def risk_limits(self) -> RiskLimits:
        return RiskLimits(
            max_position_abs=self.max_position_abs,
            max_order_quantity=self.max_order_quantity,
            max_notional=self.max_notional,
            max_daily_loss=self.max_loss,
        )

    @property
    def demo_config(self) -> DemoExecutionConfig:
        return DemoExecutionConfig(base_url=self.base_url, demo_opt_in=self.demo_opt_in)


@dataclass(frozen=True, slots=True)
class MarketMakerRunSummary:
    """Run-level Stage 6 metrics."""

    frame_count: int
    quote_count: int
    approved_actions: int
    rejected_actions: int
    skipped_actions: int
    adapter_calls: int
    limitation_notes: tuple[str, ...] = (LIMITATION_NOTE,)


def run_market_maker_replay(
    *,
    input_path: Path,
    log_output: Path,
    config: MarketMakerReplayConfig | None = None,
    quote_engine: DryRunQuoteEngine | None = None,
    adapter: DemoExecutionAdapter | None = None,
    strict: bool = True,
    initial_open_quotes: tuple[OpenQuote, ...] = (),
) -> MarketMakerRunSummary:
    """Replay snapshots through quote generation, lifecycle, and risk gates."""

    replay_config = config or MarketMakerReplayConfig()
    engine = quote_engine or DryRunQuoteEngine()
    demo_adapter = adapter or FakeDemoExecutionAdapter()
    open_quotes = {quote.side: quote for quote in initial_open_quotes}
    summary = _MutableSummary()

    for frame in ReplaySession.from_path(input_path, strict=strict).frames():
        summary.frame_count += 1
        _log(
            log_output,
            {
                "record_type": "frame",
                "sequence": frame.sequence,
                "exchange": frame.snapshot.exchange,
                "ticker": frame.snapshot.ticker,
                "observed_at": frame.snapshot.observed_at,
            },
        )
        quote = engine.quote(
            frame.snapshot.normalized_orderbook,
            inventory=replay_config.current_inventory,
        )
        intents = (quote.bid_intent, quote.ask_intent)
        for intent in intents:
            summary.quote_count += 1
            _log_quote_candidate(log_output, frame.sequence, intent, quote.inventory_skew)

        if replay_config.kill_switch:
            _handle_kill_switch(
                log_output=log_output,
                sequence=frame.sequence,
                open_quotes=open_quotes,
                intents=intents,
                summary=summary,
            )
            continue

        for intent in intents:
            lifecycle_action = _lifecycle_action(
                intent,
                open_quotes.get(intent.side),
                min_quote_change=replay_config.min_quote_change,
            )
            if lifecycle_action == "hold":
                summary.skipped_actions += 1
                _log_lifecycle(
                    log_output,
                    sequence=frame.sequence,
                    action="hold",
                    intent=intent,
                    result_status="skipped",
                    reason="open quote is already within the deterministic change threshold",
                )
                continue

            if lifecycle_action == "place" and len(open_quotes) >= replay_config.max_open_orders:
                summary.skipped_actions += 1
                _log_lifecycle(
                    log_output,
                    sequence=frame.sequence,
                    action="place",
                    intent=intent,
                    result_status="skipped",
                    reason="max_open_orders would be exceeded",
                )
                continue

            _risk_and_maybe_submit(
                log_output=log_output,
                sequence=frame.sequence,
                lifecycle_action=lifecycle_action,
                intent=intent,
                config=replay_config,
                adapter=demo_adapter,
                open_quotes=open_quotes,
                summary=summary,
            )

    result = MarketMakerRunSummary(
        frame_count=summary.frame_count,
        quote_count=summary.quote_count,
        approved_actions=summary.approved_actions,
        rejected_actions=summary.rejected_actions,
        skipped_actions=summary.skipped_actions,
        adapter_calls=summary.adapter_calls,
    )
    _log_summary(log_output, result)
    return result


def render_summary(summary: MarketMakerRunSummary, *, log_output: Path) -> str:
    """Render concise run metrics and safety limitations."""

    return "\n".join(
        (
            f"frames={summary.frame_count}",
            f"quotes={summary.quote_count}",
            f"approved_actions={summary.approved_actions}",
            f"rejected_actions={summary.rejected_actions}",
            f"skipped_actions={summary.skipped_actions}",
            f"adapter_calls={summary.adapter_calls}",
            f"log_output={log_output}",
            f"limitations={'; '.join(summary.limitation_notes)}",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Input JSONL snapshot path.")
    parser.add_argument("--log-output", type=Path, default=DEFAULT_LOG_OUTPUT)
    parser.add_argument("--demo-opt-in", action="store_true")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in ExecutionMode],
        default=ExecutionMode.DEMO.value,
    )
    parser.add_argument("--base-url", default=KALSHI_DEMO_REST_BASE_URL)
    parser.add_argument("--inventory", default="0")
    parser.add_argument("--current-position", default="0")
    parser.add_argument("--current-daily-loss", default="0")
    parser.add_argument("--max-position-abs", default="10")
    parser.add_argument("--max-open-orders", type=int, default=2)
    parser.add_argument("--max-notional", default="1.00")
    parser.add_argument("--max-loss", default="5.00")
    parser.add_argument("--quantity", default="1.00")
    parser.add_argument("--tick-size", default="0.0001")
    parser.add_argument("--default-spread", default="0.0200")
    parser.add_argument("--min-quote-change", default="0.0001")
    parser.add_argument("--kill-switch", action="store_true")
    parser.add_argument("--no-strict", action="store_true")
    args = parser.parse_args()

    summary = run_market_maker_replay(
        input_path=args.input,
        log_output=args.log_output,
        config=MarketMakerReplayConfig(
            execution_mode=ExecutionMode(args.mode),
            demo_opt_in=args.demo_opt_in,
            base_url=args.base_url,
            current_position=Decimal(args.current_position),
            current_inventory=Decimal(args.inventory),
            current_daily_loss=Decimal(args.current_daily_loss),
            max_position_abs=Decimal(args.max_position_abs),
            max_order_quantity=Decimal(args.quantity),
            max_notional=Decimal(args.max_notional),
            max_loss=Decimal(args.max_loss),
            max_open_orders=args.max_open_orders,
            kill_switch=args.kill_switch,
            min_quote_change=Decimal(args.min_quote_change),
        ),
        quote_engine=DryRunQuoteEngine(
            config=QuoteEngineConfig(
                tick_size=Decimal(args.tick_size),
                order_quantity=Decimal(args.quantity),
                default_spread=Decimal(args.default_spread),
                min_spread=Decimal(args.tick_size),
            )
        ),
        strict=not args.no_strict,
    )
    print(render_summary(summary, log_output=args.log_output))


@dataclass(slots=True)
class _MutableSummary:
    frame_count: int = 0
    quote_count: int = 0
    approved_actions: int = 0
    rejected_actions: int = 0
    skipped_actions: int = 0
    adapter_calls: int = 0


def _handle_kill_switch(
    *,
    log_output: Path,
    sequence: int,
    open_quotes: dict[str, OpenQuote],
    intents: tuple[DryRunOrderIntent, DryRunOrderIntent],
    summary: _MutableSummary,
) -> None:
    if open_quotes:
        for quote in tuple(open_quotes.values()):
            summary.skipped_actions += 1
            _log(
                log_output,
                {
                    "record_type": "lifecycle_intent",
                    "sequence": sequence,
                    "lifecycle_action": "cancel",
                    "side": quote.side,
                    "price": quote.price,
                    "quantity": quote.quantity,
                    "result_status": "skipped",
                    "reason": "kill_switch enabled; adapter access prevented",
                },
            )
        return

    for intent in intents:
        summary.skipped_actions += 1
        _log_lifecycle(
            log_output,
            sequence=sequence,
            action="place",
            intent=intent,
            result_status="skipped",
            reason="kill_switch enabled; adapter access prevented",
        )


def _risk_and_maybe_submit(
    *,
    log_output: Path,
    sequence: int,
    lifecycle_action: LifecycleAction,
    intent: DryRunOrderIntent,
    config: MarketMakerReplayConfig,
    adapter: DemoExecutionAdapter,
    open_quotes: dict[str, OpenQuote],
    summary: _MutableSummary,
) -> None:
    request = DemoExecutionRequest(
        instrument_id=intent.instrument_id,
        action="modify" if lifecycle_action == "replace" else "place",
        side=intent.side,
        price=intent.price,
        quantity=intent.quantity,
        execution_mode=config.execution_mode,
        current_position=config.current_position,
        current_inventory=config.current_inventory,
        current_daily_loss=config.current_daily_loss,
        reason=f"from dry-run intent: {intent.reason}",
    )
    decision = decide_execution_risk(
        request=request,
        config=config.demo_config,
        limits=config.risk_limits,
    )
    _log_lifecycle(
        log_output,
        sequence=sequence,
        action=lifecycle_action,
        intent=intent,
        result_status="risk_approved" if decision.approved else "rejected",
        reason=decision.reason,
    )
    _log(
        log_output,
        {
            "record_type": "risk_decision",
            "sequence": sequence,
            "lifecycle_action": lifecycle_action,
            "execution_action": request.action,
            "side": intent.side,
            "approved": decision.approved,
            "reason": decision.reason,
            "limit_name": decision.limit_name,
        },
    )

    if not decision.approved:
        summary.rejected_actions += 1
        return

    summary.approved_actions += 1
    try:
        adapter_result = (
            adapter.modify_order(request)
            if lifecycle_action == "replace"
            else adapter.place_order(request)
        )
    except Exception as exc:  # noqa: BLE001 - fake/demo adapter failures are audited.
        summary.adapter_calls += 1
        _log(
            log_output,
            {
                "record_type": "adapter_error",
                "sequence": sequence,
                "lifecycle_action": lifecycle_action,
                "side": intent.side,
                "error_reason": str(exc),
            },
        )
        return

    summary.adapter_calls += 1
    open_quotes[intent.side] = OpenQuote(
        side=intent.side,
        price=intent.price,
        quantity=intent.quantity,
    )
    _log(
        log_output,
        {
            "record_type": "adapter_submission",
            "sequence": sequence,
            "lifecycle_action": lifecycle_action,
            "side": intent.side,
            "adapter_called": True,
            "adapter_result": dict(adapter_result),
        },
    )


def _lifecycle_action(
    intent: DryRunOrderIntent,
    existing: OpenQuote | None,
    *,
    min_quote_change: Decimal,
) -> LifecycleAction:
    if existing is None:
        return "place"
    if existing.quantity != intent.quantity:
        return "replace"
    if abs(existing.price - intent.price) >= min_quote_change:
        return "replace"
    return "hold"


def _log_quote_candidate(
    log_output: Path,
    sequence: int,
    intent: DryRunOrderIntent,
    inventory_skew: Decimal,
) -> None:
    _log(
        log_output,
        {
            "record_type": "quote_candidate",
            "sequence": sequence,
            "instrument_id": intent.instrument_id,
            "side": intent.side,
            "price": intent.price,
            "quantity": intent.quantity,
            "inventory_skew": inventory_skew,
            "execution_policy": intent.execution_policy,
        },
    )


def _log_lifecycle(
    log_output: Path,
    *,
    sequence: int,
    action: LifecycleAction,
    intent: DryRunOrderIntent,
    result_status: str,
    reason: str,
) -> None:
    _log(
        log_output,
        {
            "record_type": "lifecycle_intent",
            "sequence": sequence,
            "lifecycle_action": action,
            "instrument_id": intent.instrument_id,
            "side": intent.side,
            "price": intent.price,
            "quantity": intent.quantity,
            "result_status": result_status,
            "reason": reason,
        },
    )


def _log_summary(log_output: Path, summary: MarketMakerRunSummary) -> None:
    _log(
        log_output,
        {
            "record_type": "run_summary",
            "frame_count": summary.frame_count,
            "quote_count": summary.quote_count,
            "approved_actions": summary.approved_actions,
            "rejected_actions": summary.rejected_actions,
            "skipped_actions": summary.skipped_actions,
            "adapter_calls": summary.adapter_calls,
            "fills_assumed": ZERO,
            "pnl_assumed": False,
            "limitation_notes": list(summary.limitation_notes),
        },
    )


def _log(log_output: Path, record: dict[str, object]) -> None:
    append_jsonl_record(log_output, record)


if __name__ == "__main__":
    main()
