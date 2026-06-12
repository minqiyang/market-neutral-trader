from __future__ import annotations

from pathlib import Path

from edmn_trader.data.jsonl import read_jsonl_records
from edmn_trader.scripts.demo_execution_smoke import main


def test_demo_execution_smoke_requires_explicit_opt_in(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    log_path = tmp_path / "smoke.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        ["demo_execution_smoke", "--log-output", str(log_path)],
    )

    main()

    output = capsys.readouterr().out
    assert "status=rejected" in output
    assert "risk_approved=False" in output
    [record] = list(read_jsonl_records(log_path))
    assert record["result_status"] == "rejected"
    assert record["adapter_called"] is False


def test_demo_execution_smoke_can_use_fake_adapter_after_opt_in(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    log_path = tmp_path / "smoke.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        ["demo_execution_smoke", "--demo-opt-in", "--log-output", str(log_path)],
    )

    main()

    output = capsys.readouterr().out
    assert "status=executed" in output
    assert "risk_approved=True" in output
    assert "local fake adapter only" in output
    [record] = list(read_jsonl_records(log_path))
    assert record["result_status"] == "executed"
    assert record["adapter_called"] is True
