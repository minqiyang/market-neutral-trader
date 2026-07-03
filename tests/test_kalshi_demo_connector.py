from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from edmn_trader.adapters.kalshi import (
    KalshiConfigurationError,
    KalshiDemoConnectorConfig,
    KalshiDemoConnectorError,
    preview_or_submit_kalshi_demo,
)
from edmn_trader.data.jsonl import read_jsonl_records
from edmn_trader.scripts.kalshi_demo_connector import run

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_dry_run_preview_works_without_credentials(tmp_path: Path) -> None:
    called = False

    def credential_loader() -> dict[str, str]:
        nonlocal called
        called = True
        return {}

    result = preview_or_submit_kalshi_demo(
        **_connector_kwargs(tmp_path),
        config=KalshiDemoConnectorConfig(),
        audit_log_path=tmp_path / "audit.jsonl",
        now=NOW,
        credential_loader=credential_loader,
    )

    assert result.status == "preview"
    assert result.dry_run is True
    assert called is False
    assert result.executable_order_intent is False
    assert len(result.request_previews) == 2
    assert {preview.body["side"] for preview in result.request_previews} == {"yes", "no"}
    assert all(preview.body["time_in_force"] == "fok" for preview in result.request_previews)
    assert all(preview.body["count"] == 1 for preview in result.request_previews)
    assert "order_intent" not in result.to_record()

    [audit] = list(read_jsonl_records(tmp_path / "audit.jsonl"))
    assert audit["status"] == "preview"
    assert audit["research_use"] == "demo_paper_research_infrastructure_only"
    assert audit["executable_order_intent"] is False


def test_dry_run_preview_works_without_reconciliation_state(tmp_path: Path) -> None:
    result = preview_or_submit_kalshi_demo(
        **_connector_kwargs(tmp_path, demo_reconciliation_state_record=None),
        config=KalshiDemoConnectorConfig(),
        audit_log_path=tmp_path / "audit.jsonl",
        now=NOW,
    )

    assert result.status == "preview"
    assert result.dry_run is True


def test_production_url_is_rejected_by_configuration() -> None:
    with pytest.raises(KalshiConfigurationError, match="Demo REST"):
        KalshiDemoConnectorConfig(base_url="https://external-api.kalshi.com/trade-api/v2")


def test_only_fok_or_ioc_time_in_force_is_allowed() -> None:
    with pytest.raises(ValueError, match="time_in_force"):
        KalshiDemoConnectorConfig(time_in_force="gtc")  # type: ignore[arg-type]


def test_tiny_default_limits_are_enforced(tmp_path: Path) -> None:
    proposal = _proposal_record()
    proposal["legs"] = [
        {"side": "yes", "limit_price": "0.47", "quantity": "2"},
        {"side": "no", "limit_price": "0.48", "quantity": "2"},
    ]

    with pytest.raises(KalshiDemoConnectorError, match="quantity"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(tmp_path, proposal_record=proposal),
            config=KalshiDemoConnectorConfig(),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
        )


def test_risk_decision_must_be_clear_manual_review_required(tmp_path: Path) -> None:
    risk = {
        **_risk_record(),
        "decision": "reject",
        "reasons": ["manual_approval_required", "stale_data"],
    }

    with pytest.raises(KalshiDemoConnectorError, match="passing"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(tmp_path, risk_decision_record=risk),
            config=KalshiDemoConnectorConfig(),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
        )


def test_manual_approval_hash_expiry_and_reuse_are_enforced(tmp_path: Path) -> None:
    pending = {**_pending_record(), "expires_at": (NOW - timedelta(minutes=1)).isoformat()}
    with pytest.raises(KalshiDemoConnectorError, match="expired"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(tmp_path, pending_approval_record=pending),
            config=KalshiDemoConnectorConfig(),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
        )

    reused = {**_approval_decision_record(), "used": True}
    with pytest.raises(KalshiDemoConnectorError, match="already used"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(tmp_path, approval_decision_record=reused),
            config=KalshiDemoConnectorConfig(),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
        )

    mismatched = {**_approval_decision_record(), "candidate_hash": "d" * 64}
    with pytest.raises(KalshiDemoConnectorError, match="candidate_hash mismatch"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(tmp_path, approval_decision_record=mismatched),
            config=KalshiDemoConnectorConfig(),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
        )


def test_paper_ledger_must_be_reconciled_and_match_proposal(tmp_path: Path) -> None:
    ledger = {**_ledger_record(), "reconciliation_mismatch_count": 1}

    with pytest.raises(KalshiDemoConnectorError, match="reconciliation"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(tmp_path, paper_ledger_state_record=ledger),
            config=KalshiDemoConnectorConfig(),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
        )


def test_mocked_submit_accepts_and_redacts_audit_values(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"status": "accepted", "signature": "mock-signature"})

    result = preview_or_submit_kalshi_demo(
        **_connector_kwargs(
            tmp_path,
            demo_reconciliation_state_record=_clean_reconciliation_record(),
        ),
        config=KalshiDemoConnectorConfig(submit_opt_in=True, time_in_force="ioc"),
        audit_log_path=tmp_path / "audit.jsonl",
        now=NOW,
        credential_loader=lambda: {
            "KALSHI-ACCESS-KEY": "mock-access-value",
            "KALSHI-ACCESS-SIGNATURE": "mock-signature-value",
            "KALSHI-ACCESS-TIMESTAMP": "mock-timestamp-value",
        },
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert result.status == "submitted"
    assert result.dry_run is False
    assert len(requests) == 2
    assert {request.url.path for request in requests} == {"/trade-api/v2/portfolio/orders"}
    assert all(json.loads(request.content)["time_in_force"] == "ioc" for request in requests)

    audit_text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "mock-access-value" not in audit_text
    assert "mock-signature-value" not in audit_text
    assert "mock-signature" not in audit_text
    assert "[REDACTED]" in audit_text


def test_submit_opt_in_requires_demo_reconciliation_state(tmp_path: Path) -> None:
    with pytest.raises(KalshiDemoConnectorError, match="clean demo reconciliation"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(tmp_path),
            config=KalshiDemoConnectorConfig(submit_opt_in=True),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
            credential_loader=_credential_headers,
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda _: httpx.Response(201))
            ),
        )


def test_submit_opt_in_rejects_demo_reconciliation_mismatch(tmp_path: Path) -> None:
    with pytest.raises(KalshiDemoConnectorError, match="mismatch"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(
                tmp_path,
                demo_reconciliation_state_record={
                    **_clean_reconciliation_record(),
                    "submit_eligible": False,
                    "mismatch_count": 1,
                },
            ),
            config=KalshiDemoConnectorConfig(submit_opt_in=True),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
            credential_loader=_credential_headers,
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda _: httpx.Response(201))
            ),
        )


def test_submit_opt_in_rejects_reconciliation_for_other_candidate(tmp_path: Path) -> None:
    with pytest.raises(KalshiDemoConnectorError, match="candidate_hash mismatch"):
        preview_or_submit_kalshi_demo(
            **_connector_kwargs(
                tmp_path,
                demo_reconciliation_state_record={
                    **_clean_reconciliation_record(),
                    "candidate_hash": "d" * 64,
                },
            ),
            config=KalshiDemoConnectorConfig(submit_opt_in=True),
            audit_log_path=tmp_path / "audit.jsonl",
            now=NOW,
            credential_loader=_credential_headers,
            http_client=httpx.Client(
                transport=httpx.MockTransport(lambda _: httpx.Response(201))
            ),
        )


def test_mocked_submit_rejection_and_timeout_are_logged(tmp_path: Path) -> None:
    rejected = preview_or_submit_kalshi_demo(
        **_connector_kwargs(
            tmp_path,
            demo_reconciliation_state_record=_clean_reconciliation_record(),
        ),
        config=KalshiDemoConnectorConfig(submit_opt_in=True),
        audit_log_path=tmp_path / "rejected.jsonl",
        now=NOW,
        credential_loader=_credential_headers,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(403, json={"status": "reject"})
            )
        ),
    )
    assert rejected.status == "rejected"
    assert rejected.error_reason == "HTTP 403"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("mock timeout", request=request)

    errored = preview_or_submit_kalshi_demo(
        **_connector_kwargs(
            tmp_path,
            demo_reconciliation_state_record=_clean_reconciliation_record(),
        ),
        config=KalshiDemoConnectorConfig(submit_opt_in=True),
        audit_log_path=tmp_path / "error.jsonl",
        now=NOW,
        credential_loader=_credential_headers,
        http_client=httpx.Client(transport=httpx.MockTransport(timeout)),
    )
    assert errored.status == "error"
    assert "mock timeout" in str(errored.error_reason)


def test_cli_emits_deterministic_jsonl_without_credential_arguments(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    output = tmp_path / "preview.jsonl"
    audit = tmp_path / "audit.jsonl"
    fixture.write_text(json.dumps(_fixture_payload(), sort_keys=True), encoding="utf-8")

    first = run(
        input_path=fixture,
        jsonl_output_path=output,
        audit_log_path=audit,
        time_in_force="fok",
    )
    first_text = output.read_text(encoding="utf-8")
    second = run(
        input_path=fixture,
        jsonl_output_path=output,
        audit_log_path=audit,
        time_in_force="fok",
    )

    assert first.status == second.status == "preview"
    assert output.read_text(encoding="utf-8") == first_text
    [record] = list(read_jsonl_records(output))
    assert record["status"] == "preview"
    assert record["dry_run"] is True
    assert "--credential" not in json.dumps(record).lower()
    assert "mock-access-value" not in json.dumps(record)


def _connector_kwargs(tmp_path: Path, **overrides: dict[str, object]) -> dict[str, object]:
    values: dict[str, object] = {
        "proposal_record": _proposal_record(),
        "risk_decision_record": _risk_record(),
        "pending_approval_record": _pending_record(),
        "approval_decision_record": _approval_decision_record(),
        "paper_ledger_state_record": _ledger_record(),
    }
    values.update(overrides)
    return values


def _fixture_payload() -> dict[str, object]:
    return {
        "proposal": _proposal_record(),
        "risk_decision": _risk_record(),
        "pending_approval": _pending_record(),
        "approval_decision": _approval_decision_record(),
        "paper_ledger_state": _ledger_record(),
        "now": NOW.isoformat(),
    }


def _proposal_record() -> dict[str, object]:
    return {
        "record_type": "paper_complement_order_proposal",
        "research_use": "paper_research_record_only",
        "executable_order_intent": False,
        "proposal_id": "p" * 64,
        "venue": "kalshi_demo",
        "market_id": "DEMO-MARKET",
        "candidate_hash": "c" * 64,
        "simulation_hash": "s" * 64,
        "legs": [
            {"side": "yes", "limit_price": "0.47", "quantity": "1"},
            {"side": "no", "limit_price": "0.48", "quantity": "1"},
        ],
        "risk_preview": {
            "allowed_for_paper": False,
            "reasons": ["manual_approval_required"],
        },
    }


def _risk_record() -> dict[str, object]:
    return {
        "record_type": "complement_risk_decision_v2",
        "research_use": "paper_risk_research_record_only",
        "executable_order_intent": False,
        "proposal_id": "p" * 64,
        "candidate_hash": "c" * 64,
        "decision": "manual_review_required",
        "approved": False,
        "manual_approval_required": True,
        "reasons": ["manual_approval_required"],
        "projected_exposure": "1",
    }


def _pending_record() -> dict[str, object]:
    return {
        "record_type": "manual_approval_pending",
        "research_use": "paper_manual_review_record_only",
        "executable_order_intent": False,
        "approval_id": "a" * 64,
        "proposal_id": "p" * 64,
        "candidate_hash": "c" * 64,
        "requested_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "reusable": False,
    }


def _approval_decision_record() -> dict[str, object]:
    return {
        "record_type": "manual_approval_decision",
        "research_use": "paper_manual_review_record_only",
        "executable_order_intent": False,
        "approval_id": "a" * 64,
        "proposal_id": "p" * 64,
        "candidate_hash": "c" * 64,
        "status": "approved_for_paper_once",
        "approved": True,
        "reusable": False,
        "reasons": ["manual_approval_verified", "single_use_only"],
    }


def _ledger_record() -> dict[str, object]:
    return {
        "record_type": "paper_ledger_state",
        "research_use": "paper_research_record_only",
        "executable_order_intent": False,
        "paper_order_count": 1,
        "paper_fill_count": 0,
        "settlement_count": 0,
        "total_fees": "0",
        "realized_gross_pnl": "0",
        "realized_net_pnl": "0",
        "reconciliation_mismatch_count": 0,
        "source_hashes": [
            {
                "proposal_id": "p" * 64,
                "candidate_hash": "c" * 64,
                "simulation_hash": "s" * 64,
            }
        ],
        "positions": [],
        "reconciliation_mismatches": [],
    }


def _clean_reconciliation_record() -> dict[str, object]:
    return {
        "record_type": "kalshi_demo_reconciliation_state",
        "research_use": "demo_paper_research_reconciliation_only",
        "executable_order_intent": False,
        "proposal_id": "p" * 64,
        "candidate_hash": "c" * 64,
        "approval_id": "a" * 64,
        "submit_eligible": True,
        "mismatch_count": 0,
    }


def _credential_headers() -> dict[str, str]:
    return {
        "KALSHI-ACCESS-KEY": "mock-access-value",
        "KALSHI-ACCESS-SIGNATURE": "mock-signature-value",
        "KALSHI-ACCESS-TIMESTAMP": "mock-timestamp-value",
    }
