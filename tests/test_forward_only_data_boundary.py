from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCANNER = Path(__file__).parents[1] / "scripts" / "check_forward_only_data_boundary.py"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _policy(repo: Path, baseline: str) -> Path:
    policy = repo / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "policy_id": "edmn.market_data_boundary.v1",
                "policy_revision": 3,
                "github_allowed": ["source_code", "synthetic_fixtures"],
                "github_forbidden": ["raw_REST_or_WebSocket_data"],
                "forward_only_git": {
                    "baseline_sha": baseline,
                    "profile": "test",
                    "frozen_path_globs": ["legacy_evidence/**"],
                    "sensitive_path_globs": ["legacy_evidence/**"],
                    "forbidden_path_globs": [
                        "legacy_evidence/**",
                        "**/detailed_reports/**",
                        "**/normalized_books/**",
                        "**/replay/**",
                    ],
                    "synthetic_fixture_globs": ["tests/fixtures/**"],
                    "governance_path_globs": ["governance/**", "policy.json"],
                    "git_safe_receipt_globs": ["receipts/**"],
                    "software_provenance_path_globs": ["*.lock"],
                    "allowed_path_globs": [
                        "*.md",
                        "*.py",
                        "*.json",
                        "*.lock",
                    ],
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return policy


def _repo(tmp_path: Path) -> tuple[Path, str, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Synthetic Test")
    _git(repo, "config", "user.email", "synthetic@example.invalid")
    (repo / "legacy_evidence").mkdir()
    (repo / "legacy_evidence" / "frozen.json").write_text(
        "legacy baseline is intentionally not inspected\n", encoding="utf-8"
    )
    (repo / "README.md").write_text("synthetic repository\n", encoding="utf-8")
    baseline = _commit(repo, "Synthetic baseline")
    return repo, baseline, _policy(repo, baseline)


def _scan(
    repo: Path,
    policy: Path,
    baseline: str,
    *,
    ruleset: str = "all",
    event: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCANNER),
        "--repo",
        str(repo),
        "--policy",
        str(policy),
        "--expected-profile",
        "test",
        "--mode",
        "commit-range",
        "--base",
        baseline,
        "--head",
        "HEAD",
        "--ruleset",
        ruleset,
    ]
    if event is not None:
        command.extend(["--github-event", str(event)])
    return subprocess.run(command, capture_output=True, text=True)


def _scan_mode(
    repo: Path,
    policy: Path,
    *,
    mode: str,
    base: str | None = None,
    head: str = "HEAD",
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCANNER),
        "--repo",
        str(repo),
        "--policy",
        str(policy),
        "--expected-profile",
        "test",
        "--mode",
        mode,
        "--head",
        head,
    ]
    if base is not None:
        command.extend(["--base", base])
    return subprocess.run(command, capture_output=True, text=True)


def test_forward_only_scan_allows_source_and_untouched_legacy_baseline(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "feature.py").write_text("ENABLED = True\n", encoding="utf-8")
    _commit(repo, "Add generic source code")

    result = _scan(repo, policy, baseline)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "FORWARD_ONLY_DATA_BOUNDARY_PASS"


def test_synthetic_fixture_requires_declared_provenance(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    fixtures = repo / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "book.json").write_text(
        json.dumps({"market_ticker": "SYNTH-MARKET-A"}), encoding="utf-8"
    )
    _commit(repo, "Add fixture without provenance")

    result = _scan(repo, policy, baseline, ruleset="synthetic")

    assert result.returncode == 1
    assert "SYNTHETIC_PROVENANCE_MISSING" in result.stderr
    assert "SYNTH-MARKET-A" not in result.stderr


def test_declared_synthetic_fixture_is_allowed(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    fixtures = repo / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "book.json").write_text(
        json.dumps(
            {
                "provenance": "SYNTHETIC",
                "market_ticker": "SYNTH-MARKET-A",
                "levels": [[10, 1]],
            }
        ),
        encoding="utf-8",
    )
    _commit(repo, "Add declared synthetic fixture")

    result = _scan(repo, policy, baseline)

    assert result.returncode == 0, result.stderr


def test_legacy_evidence_is_tolerated_but_cannot_be_modified_or_leaked(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    forbidden_value = "REAL" + "-IDENTIFIER-DO-NOT-ECHO"
    (repo / "legacy_evidence" / "frozen.json").write_text(forbidden_value, encoding="utf-8")
    _commit(repo, "Attempt to change frozen evidence")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "LEGACY_FROZEN_PATH_MODIFIED" in result.stderr
    assert "<REDACTED_PATH>" in result.stderr
    assert "legacy_evidence/frozen.json" not in result.stderr
    assert forbidden_value not in result.stderr


def test_detailed_local_report_is_rejected_from_git(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    report = repo / "detailed_reports" / "report.json"
    report.parent.mkdir()
    report.write_text(json.dumps({"observations": 7}), encoding="utf-8")
    _commit(repo, "Add detailed report")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr
    assert "observations" not in result.stderr


@pytest.mark.parametrize("relative", ["normalized_books/book.json", "replay/session.jsonl"])
def test_normalized_book_and_replay_artifacts_are_rejected(tmp_path: Path, relative: str) -> None:
    repo, baseline, policy = _repo(tmp_path)
    artifact = repo / relative
    artifact.parent.mkdir()
    artifact.write_text("{}\n", encoding="utf-8")
    _commit(repo, "Add derived artifact")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_BOOK_OR_REPLAY_FORBIDDEN" in result.stderr


@pytest.mark.parametrize(
    ("payload", "rule_id"),
    [
        (
            {"market_" + "ticker": "KXMOCK-REAL-LIKE"},
            "REAL_IDENTIFIER_FORBIDDEN",
        ),
        ({"closed_file_sha256": "a" * 64}, "REAL_HASH_OR_MANIFEST_FORBIDDEN"),
        (
            {"message_count": 4, "observed_at": "2030-01-01T00:00:00Z"},
            "REAL_COUNTER_OR_TIMESTAMP_FORBIDDEN",
        ),
        ({"account_" + "id": "synthetic-account"}, "ACCOUNT_OR_ORDER_DATA_FORBIDDEN"),
        (
            dict(
                [
                    ("type", "orderbook_" + "delta"),
                    ("sid", 3),
                    ("seq", 4),
                    ("msg", {}),
                ]
            ),
            "REAL_VENUE_DATA_FORBIDDEN",
        ),
    ],
)
def test_data_shaped_json_is_rejected_without_synthetic_provenance(
    tmp_path: Path, payload: dict[str, object], rule_id: str
) -> None:
    repo, baseline, policy = _repo(tmp_path)
    data = repo / "data" / "result.json"
    data.parent.mkdir()
    data.write_text(json.dumps(payload), encoding="utf-8")
    _commit(repo, "Add data-shaped JSON")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert rule_id in result.stderr
    assert not any(str(value) in result.stderr for value in payload.values())


def test_git_safe_boolean_receipt_is_accepted(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    receipt = repo / "receipts" / "safety.json"
    receipt.parent.mkdir()
    receipt.write_text(
        json.dumps(
            {
                "policy_id": "edmn.market_data_boundary.v1",
                "public_code_commit": baseline,
                "validator_executed": True,
                "safety_controls_evaluated": True,
                "raw_and_venue_derived_artifacts": "OWNER_LOCAL_ONLY",
                "production_endpoint_used": False,
                "order_write_invoked": False,
            }
        ),
        encoding="utf-8",
    )
    _commit(repo, "Add Git-safe Boolean receipt")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 0, result.stderr


def test_correlatable_receipt_field_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    receipt = repo / "receipts" / "unsafe.json"
    receipt.parent.mkdir()
    local_reference = "LOCAL_" + "RECORD_999999"
    receipt.write_text(
        json.dumps(
            {
                "policy_id": "edmn.market_data_boundary.v1",
                "validator_executed": True,
                "safety_controls_evaluated": True,
                "raw_and_venue_derived_artifacts": "OWNER_LOCAL_ONLY",
                "production_endpoint_used": False,
                "order_write_invoked": False,
                "owner_local_reference": local_reference,
            }
        ),
        encoding="utf-8",
    )
    _commit(repo, "Add unsafe receipt")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr
    assert local_reference not in result.stderr


def test_secret_like_content_is_rejected_without_echoing_the_value(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    secret_value = "not" + "-a-real-secret-value"
    key_name = "api_" + "key"
    (repo / "config.txt").write_text(f'{key_name} = "{secret_value}"\n', encoding="utf-8")
    _commit(repo, "Add unsafe configuration")

    result = _scan(repo, policy, baseline, ruleset="secrets")

    assert result.returncode == 1
    assert "SECRET_FORBIDDEN" in result.stderr
    assert secret_value not in result.stderr


def test_ordinary_python_credential_declarations_are_allowed(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    source = repo / "src" / "settings.py"
    source.parent.mkdir()
    source.write_text(
        "token: str | None = None\npassword = None\ncredentials = settings.value\n",
        encoding="utf-8",
    )
    _commit(repo, "Add credential declarations")

    result = _scan(repo, policy, baseline, ruleset="secrets")

    assert result.returncode == 0, result.stderr


def test_quoted_python_secret_literal_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    source = repo / "src" / "settings.py"
    source.parent.mkdir()
    key_name = "api_" + "key"
    value = "not" + "-a-real-secret"
    source.write_text(f'{key_name} = "{value}"\n', encoding="utf-8")
    _commit(repo, "Add unsafe source literal")

    result = _scan(repo, policy, baseline, ruleset="secrets")

    assert result.returncode == 1
    assert "SECRET_FORBIDDEN" in result.stderr
    assert value not in result.stderr


@pytest.mark.parametrize("style", ["raw", "parenthesized", "multiline_triple"])
def test_wrapped_python_secret_literals_are_rejected(tmp_path: Path, style: str) -> None:
    repo, baseline, policy = _repo(tmp_path)
    source = repo / "src" / "settings.py"
    source.parent.mkdir()
    key_name = "api_" + "key"
    value = "not" + "-a-real-secret"
    if style == "raw":
        content = f'{key_name} = r"{value}"\n'
    elif style == "parenthesized":
        content = f'{key_name} = ("{value}")\n'
    else:
        content = f'{key_name} = (\n    """{value}"""\n)\n'
    source.write_text(content, encoding="utf-8")
    _commit(repo, "Add unsafe wrapped source literal")

    result = _scan(repo, policy, baseline, ruleset="secrets")

    assert result.returncode == 1
    assert "SECRET_FORBIDDEN" in result.stderr
    assert value not in result.stderr


def test_changed_line_in_existing_multiline_secret_assignment_is_rejected(
    tmp_path: Path,
) -> None:
    repo, _, policy = _repo(tmp_path)
    source = repo / "src" / "settings.py"
    source.parent.mkdir()
    key_name = "api_" + "key"
    source.write_text(f'{key_name} = (\n    """CHANGEME"""\n)\n', encoding="utf-8")
    comparison_base = _commit(repo, "Add placeholder source setting")
    value = "not" + "-a-real-secret"
    source.write_text(f'{key_name} = (\n    """{value}"""\n)\n', encoding="utf-8")
    _commit(repo, "Update source setting")

    result = _scan(repo, policy, comparison_base, ruleset="secrets")

    assert result.returncode == 1
    assert "SECRET_FORBIDDEN" in result.stderr
    assert value not in result.stderr


def test_quoted_python_placeholder_is_allowed(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    source = repo / "src" / "settings.py"
    source.parent.mkdir()
    key_name = "api_" + "key"
    source.write_text(f'{key_name} = "CHANGEME"\n', encoding="utf-8")
    _commit(repo, "Add source placeholder")

    result = _scan(repo, policy, baseline, ruleset="secrets")

    assert result.returncode == 0, result.stderr


def test_formatting_change_to_multiline_python_placeholder_is_allowed(
    tmp_path: Path,
) -> None:
    repo, _, policy = _repo(tmp_path)
    source = repo / "src" / "settings.py"
    source.parent.mkdir()
    key_name = "api_" + "key"
    source.write_text(f'{key_name} = (\n """CHANGEME"""\n)\n', encoding="utf-8")
    comparison_base = _commit(repo, "Add multiline source placeholder")
    source.write_text(f'{key_name} = (\n    """CHANGEME"""\n)\n', encoding="utf-8")
    _commit(repo, "Format multiline source placeholder")

    result = _scan(repo, policy, comparison_base, ruleset="secrets")

    assert result.returncode == 0, result.stderr


def test_pr_metadata_is_scanned_without_echoing_forbidden_text(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "safe.py").write_text("SAFE = True\n", encoding="utf-8")
    _commit(repo, "Add safe code")
    forbidden_text = "market_ticker=" + "KXMOCK-PRIVATE-LIKE"
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"title": "Unsafe evidence", "body": forbidden_text}}),
        encoding="utf-8",
    )

    result = _scan(repo, policy, baseline, event=event)

    assert result.returncode == 1
    assert "REAL_IDENTIFIER_FORBIDDEN" in result.stderr
    assert forbidden_text not in result.stderr


def test_commit_messages_are_scanned(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "safe.py").write_text("SAFE = True\n", encoding="utf-8")
    forbidden_text = "event_ticker=" + "KXMOCK-EVENT-LIKE"
    _commit(repo, f"Do not publish {forbidden_text}")

    result = _scan(repo, policy, baseline)

    assert result.returncode == 1
    assert "REAL_IDENTIFIER_FORBIDDEN" in result.stderr
    assert forbidden_text not in result.stderr


def test_staged_and_pr_diff_modes_use_only_forward_changes(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "staged.py").write_text("STAGED = True\n", encoding="utf-8")
    _git(repo, "add", ".")

    staged = _scan_mode(repo, policy, mode="staged-diff")

    assert staged.returncode == 0, staged.stderr
    _commit(repo, "Add staged source")
    pull_request = _scan_mode(repo, policy, mode="pr-diff", base=baseline)
    assert pull_request.returncode == 0, pull_request.stderr


def test_generic_governance_doc_is_allowed_but_embedded_identifier_is_not(
    tmp_path: Path,
) -> None:
    repo, baseline, policy = _repo(tmp_path)
    docs = repo / "docs"
    docs.mkdir()
    notice = docs / "boundary.md"
    notice.write_text("Real venue-derived data remains outside Git.\n", encoding="utf-8")
    _commit(repo, "Add generic governance notice")
    assert _scan(repo, policy, baseline).returncode == 0

    forbidden_text = "market_ticker=" + "KXMOCK-DOC-LIKE"
    notice.write_text(forbidden_text, encoding="utf-8")
    _commit(repo, "Attempt unsafe documentation")
    result = _scan(repo, policy, baseline)
    assert result.returncode == 1
    assert "REAL_IDENTIFIER_FORBIDDEN" in result.stderr
    assert forbidden_text not in result.stderr


def test_unclassified_json_fails_closed(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    ambiguous = repo / "data" / "ambiguous.json"
    ambiguous.parent.mkdir()
    ambiguous.write_text(json.dumps({"value": "unknown provenance"}), encoding="utf-8")
    _commit(repo, "Add ambiguous JSON")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr


def test_unclassified_file_type_fails_closed(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    unclassified = repo / "data" / "opaque.bin"
    unclassified.parent.mkdir()
    unclassified.write_bytes(b"synthetic-but-unclassified")
    _commit(repo, "Add unclassified file type")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr


def test_source_and_governance_literals_are_boundary_scanned(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    forbidden = "REAL" + "-SOURCE-LIKE-ID"
    source = repo / "src" / "unsafe.py"
    source.parent.mkdir()
    source.write_text(f'market_ticker = "{forbidden}"\n', encoding="utf-8")
    governance = repo / "governance" / "unsafe.md"
    governance.parent.mkdir()
    governance.write_text(f'event_ticker = "{forbidden}"\n', encoding="utf-8")
    _commit(repo, "Add unsafe source and governance literals")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_IDENTIFIER_FORBIDDEN" in result.stderr
    assert forbidden not in result.stderr


def test_declared_synthetic_wire_payload_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    fixture = repo / "tests" / "fixtures" / "wire.json"
    fixture.parent.mkdir(parents=True)
    payload = dict(
        [
            ("synthetic", True),
            ("type", "orderbook_delta"),
            ("sid", 1),
            ("seq", 2),
            ("msg", {}),
        ]
    )
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    _commit(repo, "Add declared synthetic wire payload")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr


def test_later_forbidden_identifier_is_not_hidden_by_placeholder(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    forbidden = "REAL" + "-LATER-ID"
    document = repo / "docs" / "unsafe.md"
    document.parent.mkdir()
    document.write_text(
        f'market_ticker="SYNTH-MARKET"\nevent_ticker="{forbidden}"\n',
        encoding="utf-8",
    )
    _commit(repo, "Add mixed identifiers")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_IDENTIFIER_FORBIDDEN" in result.stderr
    assert forbidden not in result.stderr


@pytest.mark.parametrize("key", ["run_id", "campaign_id", "segment_id", "bundle_name"])
def test_correlatable_reference_is_rejected(tmp_path: Path, key: str) -> None:
    repo, baseline, policy = _repo(tmp_path)
    document = repo / "docs" / "unsafe.md"
    document.parent.mkdir()
    document.write_text(f'{key}="REAL-CORRELATION"\n', encoding="utf-8")
    _commit(repo, "Add correlatable reference")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_IDENTIFIER_FORBIDDEN" in result.stderr


def test_bare_local_record_reference_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    reference = "LOCAL_" + "RECORD_999999"
    document = repo / "docs" / "unsafe.md"
    document.parent.mkdir()
    document.write_text(reference, encoding="utf-8")
    _commit(repo, "Add local reference")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert reference not in result.stderr


def test_quoted_pr_metadata_is_scanned(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "safe.py").write_text("SAFE = True\n", encoding="utf-8")
    _commit(repo, "Add safe code")
    forbidden = "REAL" + "-PR-ID"
    body = '{"market_' + f'ticker": "{forbidden}"' + "}"
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"body": body}}), encoding="utf-8")

    result = _scan(repo, policy, baseline, event=event)

    assert result.returncode == 1
    assert "REAL_IDENTIFIER_FORBIDDEN" in result.stderr
    assert forbidden not in result.stderr


def test_multiple_quoted_secrets_and_common_credential_form_are_rejected(
    tmp_path: Path,
) -> None:
    repo, baseline, policy = _repo(tmp_path)
    unsafe_value = "not" + "-a-real-password"
    cloud_access_value = "AKIA" + "A" * 16
    safe_key = "to" + "ken"
    unsafe_key = "pass" + "word"
    config = repo / "config.json"
    config.write_text(
        json.dumps(dict([(safe_key, "REDACTED"), (unsafe_key, unsafe_value)]))
        + f"\n{cloud_access_value}\n",
        encoding="utf-8",
    )
    _commit(repo, "Add unsafe quoted configuration")

    result = _scan(repo, policy, baseline, ruleset="secrets")

    assert result.returncode == 1
    assert "SECRET_FORBIDDEN" in result.stderr
    assert unsafe_value not in result.stderr
    assert cloud_access_value not in result.stderr


def test_sensitive_filename_is_never_echoed(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    forbidden = "REAL" + "-PATH-ID"
    path = repo / "docs" / f"unsafe-{forbidden}\nspoof.md"
    path.parent.mkdir()
    path.write_text(f'market_ticker="{forbidden}"\n', encoding="utf-8")
    _commit(repo, "Add unsafe path")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "<REDACTED_PATH>" in result.stderr
    assert forbidden not in result.stderr
    assert "spoof.md" not in result.stderr


def test_new_file_in_frozen_namespace_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    new_legacy = repo / "legacy_evidence" / "new.md"
    new_legacy.write_text("generic text\n", encoding="utf-8")
    _commit(repo, "Add to frozen namespace")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "LEGACY_FROZEN_PATH_MODIFIED" in result.stderr


def test_symlink_and_gitlink_entries_are_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    link = repo / "docs" / "link.md"
    link.parent.mkdir()
    link.symlink_to("../README.md")
    _commit(repo, "Add symbolic link")
    symlink_result = _scan(repo, policy, baseline, ruleset="boundary")
    assert symlink_result.returncode == 1

    _git(repo, "reset", "--hard", baseline)
    policy = _policy(repo, baseline)
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{baseline},vendor/module.md")
    _git(repo, "commit", "-m", "Add gitlink")
    gitlink_result = _scan(repo, policy, baseline, ruleset="boundary")
    assert gitlink_result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in gitlink_result.stderr


def test_software_lockfile_digest_is_allowed(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    lockfile = repo / "dependencies.lock"
    lockfile.write_text("b" * 64 + "\n", encoding="utf-8")
    _commit(repo, "Update software provenance")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 0, result.stderr


def test_non_account_field_names_are_not_misclassified(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    document = repo / "docs" / "safe.md"
    document.parent.mkdir()
    document.write_text(
        '{"disposition": "IGNORED_NON_ORDERBOOK", '
        '"contains_account_or_order_data": false}\n',
        encoding="utf-8",
    )
    _commit(repo, "Add generic safety result")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 0, result.stderr


def test_binary_content_with_allowed_extension_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    document = repo / "docs" / "encoded.md"
    document.parent.mkdir()
    document.write_bytes(b"\x00\xffsynthetic-binary\n")
    _commit(repo, "Add encoded document")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr


@pytest.mark.parametrize("control", ["\x7f", "\x85", "\u200b"])
def test_control_characters_with_allowed_extension_are_rejected(
    tmp_path: Path, control: str
) -> None:
    repo, baseline, policy = _repo(tmp_path)
    document = repo / "docs" / "controlled.md"
    document.parent.mkdir()
    document.write_text(f"safe{control}text\n", encoding="utf-8")
    _commit(repo, "Add controlled document")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr


def test_encoded_blob_with_allowed_extension_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    document = repo / "docs" / "encoded.md"
    document.parent.mkdir()
    encoded = base64.b64encode(b"synthetic wire payload" * 20).decode()
    document.write_text(encoded, encoding="utf-8")
    _commit(repo, "Add encoded document")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr
    assert encoded not in result.stderr


def test_wrapped_urlsafe_encoded_blob_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    document = repo / "docs" / "wrapped.md"
    document.parent.mkdir()
    encoded = base64.urlsafe_b64encode(b"synthetic wire payload" * 20).decode()
    wrapped = "\n".join(encoded[index : index + 16] for index in range(0, len(encoded), 16))
    document.write_text(wrapped, encoding="utf-8")
    _commit(repo, "Add wrapped document")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "REAL_VENUE_DATA_FORBIDDEN" in result.stderr
    assert encoded not in result.stderr


def test_frozen_baseline_blob_copied_to_allowed_path_is_rejected(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    copied = repo / "docs" / "copied.md"
    copied.parent.mkdir()
    copied.write_bytes((repo / "legacy_evidence" / "frozen.json").read_bytes())
    _commit(repo, "Copy frozen blob")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 1
    assert "LEGACY_FROZEN_PATH_MODIFIED" in result.stderr


def test_ordinary_source_domain_assignments_are_allowed(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    source = repo / "src" / "models.py"
    source.parent.mkdir()
    source.write_text(
        "order: object | None = None\nposition = 0\naccount = None\nfills = []\n",
        encoding="utf-8",
    )
    _commit(repo, "Add domain model")

    result = _scan(repo, policy, baseline, ruleset="boundary")

    assert result.returncode == 0, result.stderr


def test_production_profile_rejects_self_authorized_test_config(tmp_path: Path) -> None:
    repo, baseline, policy = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "safe.py").write_text("SAFE = True\n", encoding="utf-8")
    _commit(repo, "Add safe code")
    result = subprocess.run(
        [
            sys.executable,
            str(SCANNER),
            "--repo",
            str(repo),
            "--policy",
            str(policy),
            "--expected-profile",
            "public",
            "--mode",
            "commit-range",
            "--base",
            baseline,
            "--head",
            "HEAD",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "FORWARD_ONLY_DATA_BOUNDARY_CONFIGURATION_FAILED"
