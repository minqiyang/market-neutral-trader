"""Guarded Kalshi Demo submission preview connector."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

import httpx

from edmn_trader.adapters.kalshi.client import (
    KALSHI_DEMO_REST_BASE_URL,
    KalshiConfigurationError,
)
from edmn_trader.adapters.kalshi.demo_reconciliation import (
    KalshiDemoReconciliationError,
    require_demo_reconciliation_submit_eligible,
)
from edmn_trader.core.models import ONE, ZERO
from edmn_trader.data.jsonl import append_jsonl_record, write_jsonl_records

KalshiDemoTimeInForce = Literal["fok", "ioc"]
KalshiDemoSubmissionStatus = Literal["preview", "submitted", "rejected", "error"]
CredentialLoader = Callable[[], Mapping[str, str]]

_ORDER_PATH = "/portfolio/orders"
_REDACTED = "[REDACTED]"
_SECRET_KEY_PARTS = (
    "authorization",
    "credential",
    "key",
    "pass",
    "private",
    "secret",
    "signature",
    "token",
)


class KalshiDemoConnectorError(Exception):
    """Raised when guarded Kalshi Demo preview/submission cannot proceed."""


@dataclass(frozen=True, slots=True)
class KalshiDemoConnectorConfig:
    """Config for guarded Kalshi Demo request previews and mocked submissions."""

    time_in_force: KalshiDemoTimeInForce = "fok"
    submit_opt_in: bool = False
    base_url: str = KALSHI_DEMO_REST_BASE_URL
    max_order_quantity: Decimal = Decimal("1")
    max_total_notional: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != KALSHI_DEMO_REST_BASE_URL:
            msg = "Kalshi Demo connector is restricted to the Demo REST base URL"
            raise KalshiConfigurationError(msg)
        if self.time_in_force not in {"fok", "ioc"}:
            msg = "time_in_force must be fok or ioc"
            raise ValueError(msg)
        for field_name in ("max_order_quantity", "max_total_notional"):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                msg = f"{field_name} must be a Decimal"
                raise TypeError(msg)
            if value <= ZERO:
                msg = f"{field_name} must be positive"
                raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class KalshiDemoRequestPreview:
    """One demo request preview; still not an executable order intent."""

    method: str
    path: str
    body: Mapping[str, object]

    def to_record(self) -> dict[str, object]:
        return {
            "method": self.method,
            "path": self.path,
            "body": dict(self.body),
            "credential_headers": "required_for_submit_redacted",
            "executable_order_intent": False,
        }


@dataclass(frozen=True, slots=True)
class KalshiDemoConnectorResult:
    """Result of one guarded preview or submit attempt."""

    status: KalshiDemoSubmissionStatus
    proposal_id: str
    candidate_hash: str
    approval_id: str
    dry_run: bool
    request_previews: tuple[KalshiDemoRequestPreview, ...]
    response_records: tuple[Mapping[str, object], ...] = ()
    error_reason: str | None = None
    record_type: str = "kalshi_demo_submission_preview"
    research_use: str = "demo_paper_research_infrastructure_only"
    executable_order_intent: bool = False
    manual_review_required: bool = True

    def to_record(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "research_use": self.research_use,
            "executable_order_intent": self.executable_order_intent,
            "manual_review_required": self.manual_review_required,
            "proposal_id": self.proposal_id,
            "candidate_hash": self.candidate_hash,
            "approval_id": self.approval_id,
            "status": self.status,
            "dry_run": self.dry_run,
            "request_previews": [preview.to_record() for preview in self.request_previews],
            "response_records": [dict(record) for record in self.response_records],
            "error_reason": self.error_reason,
        }


def preview_or_submit_kalshi_demo(
    *,
    proposal_record: Mapping[str, object],
    risk_decision_record: Mapping[str, object],
    pending_approval_record: Mapping[str, object],
    approval_decision_record: Mapping[str, object],
    paper_ledger_state_record: Mapping[str, object],
    config: KalshiDemoConnectorConfig,
    audit_log_path: Path,
    demo_reconciliation_state_record: Mapping[str, object] | None = None,
    now: datetime | None = None,
    credential_loader: CredentialLoader | None = None,
    http_client: httpx.Client | None = None,
) -> KalshiDemoConnectorResult:
    """Build a guarded Kalshi Demo dry-run preview, or submit with explicit opt-in."""

    observed_at = now or datetime.now(UTC)
    _require_timezone(observed_at, field_name="now")
    proposal_id, candidate_hash, market_id = _validate_proposal(proposal_record)
    _validate_risk_decision(
        risk_decision_record,
        proposal_id=proposal_id,
        candidate_hash=candidate_hash,
    )
    approval_id = _validate_manual_approval(
        pending_approval_record,
        approval_decision_record,
        proposal_id=proposal_id,
        candidate_hash=candidate_hash,
        now=observed_at,
    )
    _validate_ledger_state(
        paper_ledger_state_record,
        proposal_id=proposal_id,
        candidate_hash=candidate_hash,
    )
    previews = _build_request_previews(proposal_record, market_id=market_id, config=config)

    if not config.submit_opt_in:
        if demo_reconciliation_state_record is not None:
            _validate_demo_reconciliation_state(
                demo_reconciliation_state_record,
                proposal_id=proposal_id,
                candidate_hash=candidate_hash,
                approval_id=approval_id,
            )
        result = KalshiDemoConnectorResult(
            status="preview",
            proposal_id=proposal_id,
            candidate_hash=candidate_hash,
            approval_id=approval_id,
            dry_run=True,
            request_previews=previews,
        )
        _append_audit(audit_log_path, result, observed_at=observed_at)
        return result

    if demo_reconciliation_state_record is None:
        msg = "Kalshi Demo submit requires a clean demo reconciliation state"
        raise KalshiDemoConnectorError(msg)
    _validate_demo_reconciliation_state(
        demo_reconciliation_state_record,
        proposal_id=proposal_id,
        candidate_hash=candidate_hash,
        approval_id=approval_id,
    )

    if http_client is None:
        msg = "submit path requires an explicit http_client in this stage"
        raise KalshiDemoConnectorError(msg)

    headers = dict((credential_loader or load_kalshi_demo_auth_headers_from_env)())
    if not headers:
        msg = "Kalshi Demo submit requires credential headers from the configured loader"
        raise KalshiDemoConnectorError(msg)

    responses: list[Mapping[str, object]] = []
    for preview in previews:
        try:
            response = http_client.post(
                f"{config.base_url.rstrip('/')}{preview.path}",
                json=preview.body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            result = KalshiDemoConnectorResult(
                status="error",
                proposal_id=proposal_id,
                candidate_hash=candidate_hash,
                approval_id=approval_id,
                dry_run=False,
                request_previews=previews,
                response_records=tuple(responses),
                error_reason=str(exc),
            )
            _append_audit(audit_log_path, result, observed_at=observed_at, headers=headers)
            return result

        response_record = _response_record(response)
        responses.append(response_record)
        if response.status_code >= 400:
            result = KalshiDemoConnectorResult(
                status="rejected",
                proposal_id=proposal_id,
                candidate_hash=candidate_hash,
                approval_id=approval_id,
                dry_run=False,
                request_previews=previews,
                response_records=tuple(responses),
                error_reason=f"HTTP {response.status_code}",
            )
            _append_audit(audit_log_path, result, observed_at=observed_at, headers=headers)
            return result

    result = KalshiDemoConnectorResult(
        status="submitted",
        proposal_id=proposal_id,
        candidate_hash=candidate_hash,
        approval_id=approval_id,
        dry_run=False,
        request_previews=previews,
        response_records=tuple(responses),
    )
    _append_audit(audit_log_path, result, observed_at=observed_at, headers=headers)
    return result


def write_kalshi_demo_result_jsonl(path: Path, result: KalshiDemoConnectorResult) -> None:
    """Write one deterministic preview/submission result JSONL file."""

    write_jsonl_records(path, [result.to_record()])


def load_kalshi_demo_auth_headers_from_env() -> Mapping[str, str]:
    """Load Demo auth headers from environment names without logging values."""

    required = {
        "KALSHI-ACCESS-KEY": "KALSHI_DEMO_ACCESS_KEY",
        "KALSHI-ACCESS-SIGNATURE": "KALSHI_DEMO_ACCESS_SIGNATURE",
        "KALSHI-ACCESS-TIMESTAMP": "KALSHI_DEMO_ACCESS_TIMESTAMP",
    }
    headers: dict[str, str] = {}
    missing: list[str] = []
    for header_name, env_name in required.items():
        value = os.environ.get(env_name)
        if not value:
            missing.append(env_name)
        else:
            headers[header_name] = value
    if missing:
        msg = "missing Kalshi Demo credential environment variables"
        raise KalshiDemoConnectorError(msg)
    return headers


def _require_demo_reconciliation_submit_eligible(record: Mapping[str, object]) -> None:
    try:
        require_demo_reconciliation_submit_eligible(record)
    except KalshiDemoReconciliationError as exc:
        raise KalshiDemoConnectorError(str(exc)) from exc


def _validate_demo_reconciliation_state(
    record: Mapping[str, object],
    *,
    proposal_id: str,
    candidate_hash: str,
    approval_id: str,
) -> None:
    _match_hashes(record, proposal_id=proposal_id, candidate_hash=candidate_hash)
    if _expect_str(record, "approval_id") != approval_id:
        msg = "demo reconciliation approval_id mismatch"
        raise KalshiDemoConnectorError(msg)
    _require_demo_reconciliation_submit_eligible(record)


def _validate_proposal(record: Mapping[str, object]) -> tuple[str, str, str]:
    _require_record(record, "paper_complement_order_proposal")
    venue = _expect_str(record, "venue")
    if venue != "kalshi_demo":
        msg = "proposal venue must be kalshi_demo"
        raise KalshiDemoConnectorError(msg)
    proposal_id = _expect_str(record, "proposal_id")
    candidate_hash = _expect_str(record, "candidate_hash")
    market_id = _expect_str(record, "market_id")
    legs = _sequence(record.get("legs"), field_name="legs")
    if len(legs) != 2:
        msg = "proposal must contain exactly two legs"
        raise KalshiDemoConnectorError(msg)
    sides = sorted(_expect_str(_mapping(leg, field_name="leg"), "side") for leg in legs)
    if sides != ["no", "yes"]:
        msg = "proposal legs must contain one yes and one no side"
        raise KalshiDemoConnectorError(msg)
    return proposal_id, candidate_hash, market_id


def _validate_risk_decision(
    record: Mapping[str, object],
    *,
    proposal_id: str,
    candidate_hash: str,
) -> None:
    _require_record(record, "complement_risk_decision_v2")
    _match_hashes(record, proposal_id=proposal_id, candidate_hash=candidate_hash)
    if record.get("decision") != "manual_review_required":
        msg = "risk decision must be a passing manual_review_required decision"
        raise KalshiDemoConnectorError(msg)
    if record.get("approved") is not False:
        msg = "risk decision must remain non-approved pending manual approval"
        raise KalshiDemoConnectorError(msg)
    if record.get("manual_approval_required") is not True:
        msg = "risk decision must require manual approval"
        raise KalshiDemoConnectorError(msg)
    if tuple(record.get("reasons", ())) != ("manual_approval_required",):
        msg = "risk decision contains blocker reasons"
        raise KalshiDemoConnectorError(msg)


def _validate_manual_approval(
    pending: Mapping[str, object],
    decision: Mapping[str, object],
    *,
    proposal_id: str,
    candidate_hash: str,
    now: datetime,
) -> str:
    _require_record(pending, "manual_approval_pending")
    _require_record(decision, "manual_approval_decision")
    _match_hashes(pending, proposal_id=proposal_id, candidate_hash=candidate_hash)
    _match_hashes(decision, proposal_id=proposal_id, candidate_hash=candidate_hash)
    approval_id = _expect_str(pending, "approval_id")
    if _expect_str(decision, "approval_id") != approval_id:
        msg = "manual approval id mismatch"
        raise KalshiDemoConnectorError(msg)
    expires_at = _datetime_from_record(pending, "expires_at")
    if now > expires_at:
        msg = "manual approval is expired"
        raise KalshiDemoConnectorError(msg)
    if pending.get("reusable") is not False or decision.get("reusable") is not False:
        msg = "manual approval must be single-use only"
        raise KalshiDemoConnectorError(msg)
    if decision.get("used") is True:
        msg = "manual approval was already used"
        raise KalshiDemoConnectorError(msg)
    if decision.get("approved") is not True or decision.get("status") != "approved_for_paper_once":
        msg = "manual approval must be approved_for_paper_once"
        raise KalshiDemoConnectorError(msg)
    return approval_id


def _validate_ledger_state(
    record: Mapping[str, object],
    *,
    proposal_id: str,
    candidate_hash: str,
) -> None:
    _require_record(record, "paper_ledger_state")
    if record.get("reconciliation_mismatch_count") != 0:
        msg = "paper ledger has reconciliation mismatches"
        raise KalshiDemoConnectorError(msg)
    source_hashes = _sequence(record.get("source_hashes"), field_name="source_hashes")
    for source in source_hashes:
        source_record = _mapping(source, field_name="source_hash")
        if (
            source_record.get("proposal_id") == proposal_id
            and source_record.get("candidate_hash") == candidate_hash
        ):
            return
    msg = "paper ledger state does not include the approved proposal"
    raise KalshiDemoConnectorError(msg)


def _build_request_previews(
    proposal_record: Mapping[str, object],
    *,
    market_id: str,
    config: KalshiDemoConnectorConfig,
) -> tuple[KalshiDemoRequestPreview, ...]:
    previews: list[KalshiDemoRequestPreview] = []
    total_notional = ZERO
    proposal_id = _expect_str(proposal_record, "proposal_id")
    for leg_object in _sequence(proposal_record.get("legs"), field_name="legs"):
        leg = _mapping(leg_object, field_name="leg")
        side = _expect_str(leg, "side")
        if side not in {"yes", "no"}:
            msg = "leg side must be yes or no"
            raise KalshiDemoConnectorError(msg)
        quantity = _decimal(leg, "quantity")
        price = _probability_decimal(leg, "limit_price")
        if quantity <= ZERO or quantity > config.max_order_quantity:
            msg = "leg quantity exceeds guarded Demo limit"
            raise KalshiDemoConnectorError(msg)
        if quantity != quantity.to_integral_value():
            msg = "Kalshi Demo request preview requires whole-contract quantity"
            raise KalshiDemoConnectorError(msg)
        total_notional += price * quantity
        body: dict[str, object] = {
            "ticker": market_id,
            "action": "buy",
            "type": "limit",
            "side": side,
            "count": int(quantity),
            "time_in_force": config.time_in_force,
            "client_order_id": _client_order_id(
                proposal_id=proposal_id,
                side=side,
                time_in_force=config.time_in_force,
            ),
            "research_label": "demo_paper_research_infrastructure_not_trading_advice",
        }
        body[f"{side}_price"] = _price_cents(price)
        previews.append(KalshiDemoRequestPreview(method="POST", path=_ORDER_PATH, body=body))
    if total_notional > config.max_total_notional:
        msg = "total Demo request notional exceeds guarded limit"
        raise KalshiDemoConnectorError(msg)
    return tuple(previews)


def _append_audit(
    path: Path,
    result: KalshiDemoConnectorResult,
    *,
    observed_at: datetime,
    headers: Mapping[str, str] | None = None,
) -> None:
    record = result.to_record()
    record["timestamp"] = observed_at
    if headers is not None:
        record["auth_headers"] = dict(headers)
    append_jsonl_record(path, _redact(record))


def _response_record(response: httpx.Response) -> Mapping[str, object]:
    body: object
    try:
        body = response.json()
    except ValueError:
        body = response.text[:300]
    return _redact(
        {
            "status_code": response.status_code,
            "body": body,
        }
    )


def _redact(value: object, *, parent_key: str = "") -> object:
    if isinstance(value, Mapping):
        clean: dict[str, object] = {}
        for key, item in value.items():
            key_str = str(key)
            if _is_secret_key(key_str):
                clean[key_str] = _REDACTED
            else:
                clean[key_str] = _redact(item, parent_key=key_str)
        return clean
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_redact(item, parent_key=parent_key) for item in value]
    if parent_key and _is_secret_key(parent_key):
        return _REDACTED
    return value


def _is_secret_key(key: str) -> bool:
    lower = key.lower()
    return any(part in lower for part in _SECRET_KEY_PARTS)


def _require_record(record: Mapping[str, object], record_type: str) -> None:
    if record.get("record_type") != record_type:
        msg = f"record_type must be {record_type}"
        raise KalshiDemoConnectorError(msg)
    if record.get("executable_order_intent") is not False:
        msg = "source record must not be executable"
        raise KalshiDemoConnectorError(msg)


def _match_hashes(
    record: Mapping[str, object],
    *,
    proposal_id: str,
    candidate_hash: str,
) -> None:
    if _expect_str(record, "proposal_id") != proposal_id:
        msg = "proposal_id mismatch"
        raise KalshiDemoConnectorError(msg)
    if _expect_str(record, "candidate_hash") != candidate_hash:
        msg = "candidate_hash mismatch"
        raise KalshiDemoConnectorError(msg)


def _client_order_id(
    *,
    proposal_id: str,
    side: str,
    time_in_force: str,
) -> str:
    return f"edmn-demo-{proposal_id[:16]}-{side}-{time_in_force}"


def _price_cents(price: Decimal) -> int:
    cents = price * Decimal("100")
    if cents != cents.to_integral_value():
        msg = "Kalshi Demo request preview requires cent precision"
        raise KalshiDemoConnectorError(msg)
    return int(cents)


def _expect_str(record: Mapping[str, object], field_name: str) -> str:
    value = record.get(field_name)
    if not isinstance(value, str) or not value:
        msg = f"{field_name} must be a non-empty string"
        raise KalshiDemoConnectorError(msg)
    return value


def _decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = record.get(field_name)
    if not isinstance(value, str):
        msg = f"{field_name} must be a decimal string"
        raise KalshiDemoConnectorError(msg)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise KalshiDemoConnectorError(msg) from exc


def _probability_decimal(record: Mapping[str, object], field_name: str) -> Decimal:
    value = _decimal(record, field_name)
    if value < ZERO or value > ONE:
        msg = f"{field_name} must be in [0, 1]"
        raise KalshiDemoConnectorError(msg)
    return value


def _datetime_from_record(record: Mapping[str, object], field_name: str) -> datetime:
    raw_value = _expect_str(record, field_name)
    parsed = datetime.fromisoformat(raw_value)
    _require_timezone(parsed, field_name=field_name)
    return parsed


def _require_timezone(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None:
        msg = f"{field_name} must be timezone-aware"
        raise KalshiDemoConnectorError(msg)


def _sequence(value: object, *, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        msg = f"{field_name} must be a list"
        raise KalshiDemoConnectorError(msg)
    return value


def _mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be an object"
        raise KalshiDemoConnectorError(msg)
    return value
