#!/usr/bin/env python3
"""Fail closed on post-cutover Git content without inspecting legacy files."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import subprocess
import sys
import textwrap
import unicodedata
from pathlib import Path

PASS = "FORWARD_ONLY_DATA_BOUNDARY_PASS"
PRIVATE_KEY_PREFIX = "-----BEGIN "
PRIVATE_KEY_SUFFIX = "PRIVATE " + "KEY-----"
ALLOWED_PATH_GLOBS = frozenset(
    {
        "*.md",
        "*.rst",
        "*.txt",
        "*.py",
        "*.pyi",
        "*.sh",
        "*.toml",
        "*.cfg",
        "*.ini",
        "*.yaml",
        "*.yml",
        "*.json",
        "*.svg",
        "*.lock",
        ".gitignore",
        ".github/CODEOWNERS",
        "LICENSE",
    }
)
SOFTWARE_PROVENANCE_GLOBS = frozenset({"*.lock", "requirements*.txt", "*.sum"})
PRODUCTION_CONTRACTS = {
    "public": {
        "baseline_sha": "3de723578c0b44d742887305b1cbe82efd751f2b",
        "frozen_path_globs": {
            "tests/fixtures/**",
            "CHANGELOG.md",
            "docs/current_handoff.md",
            "docs/engineering_log.md",
        },
        "forbidden_path_globs": {
            "tests/fixtures/**",
            "**/private_data/**",
            "**/real_data/**",
            "**/detailed_reports/**",
            "**/campaign_manifests/**",
            "**/validation_reports/**",
            "**/monitor_snapshots/**",
            "**/run_metadata/**",
            "**/supervisor_evidence/**",
            "**/normalized_books/**",
            "**/replay/**",
            "**/*.jsonl",
            "**/*.parquet",
            "**/*.tar.zst",
        },
        "synthetic_fixture_globs": {"tests/synthetic_fixtures/**"},
        "governance_path_globs": {".github/forward_only_data_boundary.json"},
        "git_safe_receipt_globs": {"git_safe_receipts/**"},
    },
    "private_ops": {
        "baseline_sha": "f3eae534f2306fb4204b38858ef4ac7cd451200e",
        "frozen_path_globs": {
            "edmn/reports/**",
            "edmn/campaign_manifests/**",
            "edmn/supervisor_evidence/**",
            "edmn/diagnosis_reports/**",
            "edmn/validation_reports/**",
            "edmn/monitor_snapshots/**",
            "edmn/run_metadata/**",
            "edmn/postmortems/**",
            "edmn/drill_evidence/**",
            "edmn/runbooks/backup_restore_policy.md",
        },
        "forbidden_path_globs": {
            "edmn/reports/**",
            "edmn/campaign_manifests/**",
            "edmn/supervisor_evidence/**",
            "edmn/diagnosis_reports/**",
            "edmn/validation_reports/**",
            "edmn/monitor_snapshots/**",
            "edmn/run_metadata/**",
            "edmn/postmortems/**",
            "edmn/drill_evidence/**",
            "edmn/runbooks/backup_restore_policy.md",
            "**/private_data/**",
            "**/real_data/**",
            "**/detailed_reports/**",
            "**/normalized_books/**",
            "**/replay/**",
            "**/*.jsonl",
            "**/*.parquet",
            "**/*.tar.zst",
        },
        "synthetic_fixture_globs": {
            "tests/synthetic_fixtures/**",
            "tools/**/fixtures/**",
        },
        "governance_path_globs": {
            "edmn/governance/edmn_market_data_boundary_icloud_standard_revision.md",
            "edmn/governance/edmn_market_data_boundary_icloud_standard_revision.json",
            "edmn/governance/phase0d_icloud_standard_protection_amendment.md",
            "edmn/governance/phase0d_forward_only_cutover.md",
            "edmn/governance/phase0d_forward_only_cutover.json",
            "edmn/governance/forward_only_enforcement.json",
        },
        "git_safe_receipt_globs": {"edmn/git_safe_receipts/**"},
    },
}
IDENTIFIER_ASSIGNMENT = re.compile(
    r'''["']?(?:market|event)[_-]?(?:ticker|id)["']?\s*[:=]\s*'''
    r'''(?P<quote>["']?)(?P<value>[A-Za-z0-9._<>-]+)(?P=quote)''',
    re.IGNORECASE,
)
CORRELATION_ASSIGNMENT = re.compile(
    r'''["']?(?:run_id|campaign_id|segment_id|bundle_name|backup_id|local_record|'''
    r'''owner_local_reference)["']?\s*[:=]\s*'''
    r'''(?P<quote>["']?)(?P<value>[A-Za-z0-9._<>-]+)(?P=quote)''',
    re.IGNORECASE,
)
ACCOUNT_ASSIGNMENT = re.compile(
    r'''(?<![A-Za-z0-9_])(?P<key_quote>["']?)(?:account(?:_id|_data)?|'''
    r'''order(?:_id|_data)?|wallet(?:_id|_address)?|position(?:_id|s)?|'''
    r'''fill(?:_id|s)?)(?P=key_quote)\s*[:=]''',
    re.IGNORECASE,
)
COUNTER_ASSIGNMENT = re.compile(
    r'''["']?[^"']*(?:count|timestamp|observed_at|created_at|closed_at)["']?\s*[:=]''',
    re.IGNORECASE,
)
SECRET_ASSIGNMENT = re.compile(
    r'''(?P<key_quote>["']?)(?:api[_-]?key|private[_-]?key|client[_-]?secret|access[_-]?key|'''
    r'''access[_-]?token|secret|token|authorization|password|credentials?)'''
    r'''(?P=key_quote)\s*[:=]\s*(?P<quote>["']?)(?P<value>[^\s,"'}]+)(?P=quote)''',
    re.IGNORECASE,
)
STANDALONE_SECRET_PATTERNS = (
    re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)
PYTHON_SECRET_NAMES = frozenset(
    {
        "api_key",
        "private_key",
        "client_secret",
        "access_key",
        "access_token",
        "secret",
        "token",
        "authorization",
        "password",
        "credential",
        "credentials",
    }
)
SAFE_SECRET_VALUES = frozenset(
    {
        "<REDACTED>",
        "REDACTED",
        "CHANGEME",
        "EXAMPLE",
        "SYNTHETIC",
        "FORBIDDEN",
        "NOT_REQUIRED",
        "FALSE",
        "NULL",
    }
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError("Git provenance check failed")
    return result.stdout.strip()


def _git_bytes(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo, check=False, capture_output=True)
    if result.returncode:
        raise ValueError("Git content check failed")
    return result.stdout


def _matches(path: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(path, pattern)
        or (pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]))
        for pattern in patterns
    )


def _validate_contract(config: dict[str, object], expected_profile: str) -> None:
    if config.get("profile") != expected_profile:
        raise ValueError("Enforcement profile mismatch")
    if expected_profile == "test":
        return
    contract = PRODUCTION_CONTRACTS.get(expected_profile)
    if contract is None or config.get("baseline_sha") != contract["baseline_sha"]:
        raise ValueError("Enforcement baseline mismatch")
    exact_fields = (
        "frozen_path_globs",
        "forbidden_path_globs",
        "synthetic_fixture_globs",
        "governance_path_globs",
        "git_safe_receipt_globs",
    )
    if any(set(config.get(field, [])) != contract[field] for field in exact_fields):
        raise ValueError("Enforcement contract mismatch")
    if set(config.get("allowed_path_globs", [])) != ALLOWED_PATH_GLOBS:
        raise ValueError("Allowed-path contract mismatch")
    if set(config.get("software_provenance_path_globs", [])) != SOFTWARE_PROVENANCE_GLOBS:
        raise ValueError("Software-provenance contract mismatch")
    protected = set(config["frozen_path_globs"]) | set(config["forbidden_path_globs"])
    if not protected <= set(config.get("sensitive_path_globs", [])):
        raise ValueError("Sensitive-path contract is incomplete")


def _diff_base(repo: Path, mode: str, base: str | None, head: str) -> tuple[str, str]:
    if mode == "staged-diff":
        return "--cached", ""
    if not base:
        raise ValueError("A base commit is required")
    if mode == "pr-diff":
        base = _git(repo, "merge-base", base, head)
    return base, head


def _changed_paths(repo: Path, mode: str, base: str, head: str) -> list[str]:
    args = ["diff"]
    if base == "--cached":
        args.append("--cached")
    else:
        args.extend((base, head))
    args.extend(("--name-only", "--no-renames", "-z"))
    return [path.decode("utf-8") for path in _git_bytes(repo, *args).split(b"\0") if path]


def _content(repo: Path, mode: str, head: str, path: str) -> str | None:
    spec = f":{path}" if mode == "staged-diff" else f"{head}:{path}"
    result = subprocess.run(["git", "show", spec], cwd=repo, check=False, capture_output=True)
    if result.returncode:
        return None
    try:
        content = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(
        character not in "\t\n\r"
        and unicodedata.category(character) in {"Cc", "Cf"}
        for character in content
    ):
        return None
    return content


def _entry(repo: Path, mode: str, head: str, path: str) -> tuple[str, str] | None:
    if mode == "staged-diff":
        output = _git_bytes(repo, "ls-files", "--stage", "-z", "--", path)
    else:
        output = _git_bytes(repo, "ls-tree", "-z", head, "--", path)
    if not output:
        return None
    fields = output.split(b"\t", 1)[0].split(b" ")
    mode_field = fields[0]
    object_id = fields[1] if mode == "staged-diff" else fields[2]
    return mode_field.decode("ascii", "strict"), object_id.decode("ascii", "strict")


def _frozen_blob_ids(repo: Path, baseline: str, patterns: list[str]) -> set[str]:
    frozen: set[str] = set()
    for entry in _git_bytes(repo, "ls-tree", "-r", "-z", baseline).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        _, object_type, object_id = metadata.split(b" ", 2)
        path = raw_path.decode("utf-8")
        if object_type == b"blob" and _matches(path, patterns):
            frozen.add(object_id.decode("ascii", "strict"))
    return frozen


def _added_lines(repo: Path, mode: str, base: str, head: str, path: str) -> list[tuple[int, str]]:
    args = ["diff", "--unified=0", "--no-color", "--no-ext-diff"]
    if base == "--cached":
        args.append("--cached")
    else:
        args.extend((base, head))
    args.extend(("--", path))
    patch = _git_bytes(repo, *args).decode("utf-8", "replace")
    added: list[tuple[int, str]] = []
    line_number = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            line_number = int(match.group(1)) if match else 0
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((line_number, line[1:]))
            line_number += 1
        elif not line.startswith("-") and line_number:
            line_number += 1
    return added


def _synthetic_provenance(content: str) -> bool:
    if "SYNTHETIC_FIXTURE" in content:
        return True
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and (
        payload.get("synthetic") is True
        or str(payload.get("provenance", "")).upper() in {"SYNTHETIC", "MOCK", "MOCKED"}
    )


def _valid_git_safe_receipt(content: str) -> bool:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return False
    required = {
        "policy_id",
        "validator_executed",
        "safety_controls_evaluated",
        "raw_and_venue_derived_artifacts",
        "production_endpoint_used",
        "order_write_invoked",
    }
    allowed = required | {"public_code_commit"}
    if not isinstance(payload, dict) or set(payload) - allowed or not required <= set(payload):
        return False
    commit = payload.get("public_code_commit")
    return (
        payload["policy_id"] == "edmn.market_data_boundary.v1"
        and payload["validator_executed"] is True
        and payload["safety_controls_evaluated"] is True
        and payload["raw_and_venue_derived_artifacts"] in {"OWNER_LOCAL_ONLY", "OUTSIDE_GIT"}
        and payload["production_endpoint_used"] is False
        and payload["order_write_invoked"] is False
        and (commit is None or (isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)))
    )


def _redacted_location(line_number: int | None = None) -> str:
    location = "<REDACTED_PATH>"
    return f"{location} line={line_number}" if line_number is not None else location


def _forbidden_path_rule(path: str) -> str:
    lowered = path.lower()
    if "/normalized_books/" in f"/{lowered}" or "/replay/" in f"/{lowered}":
        return "REAL_BOOK_OR_REPLAY_FORBIDDEN"
    if any(word in lowered for word in ("manifest", "checkpoint", "hash_ledger")):
        return "REAL_HASH_OR_MANIFEST_FORBIDDEN"
    if any(word in lowered for word in ("account", "orders", "wallet", "positions", "fills")):
        return "ACCOUNT_OR_ORDER_DATA_FORBIDDEN"
    return "REAL_VENUE_DATA_FORBIDDEN"


def _placeholder(value: str) -> bool:
    upper = value.upper()
    return value.startswith("<") or upper.startswith(("SYNTH", "TEST", "MOCK", "FAKE"))


def _content_finding(
    added: list[tuple[int, str]],
    *,
    synthetic: bool,
    restricted: bool,
    software_provenance: bool,
    canonical_governance: bool = False,
) -> tuple[str, int] | None:
    joined = "\n".join(line for _, line in added)
    if not joined:
        return None
    for account_match in ACCOUNT_ASSIGNMENT.finditer(joined):
        if restricted and not account_match.group("key_quote"):
            continue
        return "ACCOUNT_OR_ORDER_DATA_FORBIDDEN", _line_for_offset(
            added, account_match.start()
        )
    for identifier in IDENTIFIER_ASSIGNMENT.finditer(joined):
        if restricted and not identifier.group("quote"):
            continue
        if not _placeholder(identifier.group("value")):
            return "REAL_IDENTIFIER_FORBIDDEN", _line_for_offset(added, identifier.start())
    for correlation in CORRELATION_ASSIGNMENT.finditer(joined):
        if restricted and not correlation.group("quote"):
            continue
        if not _placeholder(correlation.group("value")):
            return "REAL_IDENTIFIER_FORBIDDEN", _line_for_offset(added, correlation.start())
    local_reference = re.search(r"\bLOCAL_RECORD_[0-9]{6,}\b", joined)
    if local_reference and not (
        canonical_governance
        and local_reference.group(0) == "LOCAL_" + "RECORD_000001"
    ):
        return "REAL_IDENTIFIER_FORBIDDEN", _line_for_offset(added, local_reference.start())
    encoded_blob = re.search(
        r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{120,}={0,2}(?![A-Za-z0-9+/_=-])",
        joined,
    ) or re.search(
        r"(?m)(?:^[A-Za-z0-9+/_-]{16,}={0,2}[ \t]*$\n?){5,}",
        joined,
    )
    if encoded_blob and not software_provenance:
        return "REAL_VENUE_DATA_FORBIDDEN", _line_for_offset(added, encoded_blob.start())
    raw_keys = sum(
        bool(re.search(rf'''["']{key}["']\s*:''', joined, re.IGNORECASE))
        for key in ("sid", "seq", "sequence", "msg", "channel")
    )
    raw_type = re.search(
        r'''["']type["']\s*:\s*["'](?:orderbook_delta|trade)["']''',
        joined,
        re.IGNORECASE,
    )
    if raw_keys >= 2 or raw_type:
        offset = raw_type.start() if raw_type else 0
        return "REAL_VENUE_DATA_FORBIDDEN", _line_for_offset(added, offset)
    if restricted:
        return None
    if synthetic:
        return None
    digest = re.search(
        r'''["'][^"']*(?:sha256|chain_hash|manifest|checkpoint)[^"']*["']\s*:''',
        joined,
        re.IGNORECASE,
    )
    if digest and not software_provenance:
        return "REAL_HASH_OR_MANIFEST_FORBIDDEN", _line_for_offset(added, digest.start())
    counter = COUNTER_ASSIGNMENT.search(joined)
    if counter:
        return "REAL_COUNTER_OR_TIMESTAMP_FORBIDDEN", _line_for_offset(added, counter.start())
    return None


def _line_for_offset(added: list[tuple[int, str]], offset: int) -> int:
    consumed = 0
    for line_number, line in added:
        if offset <= consumed + len(line):
            return line_number
        consumed += len(line) + 1
    return added[0][0]


def _literal_string_expression(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bytes))
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal_string_expression(node.left) and _literal_string_expression(node.right)
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return any(_literal_string_expression(element) for element in node.elts)
    if isinstance(node, ast.Dict):
        return any(
            value is not None and _literal_string_expression(value) for value in node.values
        )
    return False


def _literal_secret_expression_allowed(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        value = (
            node.value.decode("utf-8", "ignore")
            if isinstance(node.value, bytes)
            else node.value
        )
        return value.upper() in SAFE_SECRET_VALUES
    if isinstance(node, ast.JoinedStr):
        return all(
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and value.value.upper() in SAFE_SECRET_VALUES
            for value in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal_secret_expression_allowed(
            node.left
        ) and _literal_secret_expression_allowed(node.right)
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return all(
            not _literal_string_expression(element)
            or _literal_secret_expression_allowed(element)
            for element in node.elts
        )
    if isinstance(node, ast.Dict):
        return all(
            value is None
            or not _literal_string_expression(value)
            or _literal_secret_expression_allowed(value)
            for value in node.values
        )
    return False


def _python_secret_literal_line(
    added: list[tuple[int, str]], full_content: str | None = None
) -> int | None:
    try:
        tree = ast.parse(
            full_content
            if full_content is not None
            else textwrap.dedent("\n".join(line for _, line in added))
        )
    except SyntaxError:
        if full_content is not None:
            return _python_secret_literal_line(added)
        return None
    for node in ast.walk(tree):
        targets: list[ast.expr]
        value: ast.expr
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        elif isinstance(node, ast.NamedExpr):
            targets = [node.target]
            value = node.value
        else:
            continue
        if (
            any(
                isinstance(target, ast.Name)
                and target.id.lower() in PYTHON_SECRET_NAMES
                for target in targets
            )
            and _literal_string_expression(value)
            and not _literal_secret_expression_allowed(value)
        ):
            if full_content is not None:
                changed_lines = [
                    line_number
                    for line_number, _ in added
                    if node.lineno <= line_number <= (node.end_lineno or node.lineno)
                ]
                if changed_lines:
                    return changed_lines[0]
                continue
            return added[min(max(node.lineno - 1, 0), len(added) - 1)][0]
    return None


def _secret_finding(
    path: str, added: list[tuple[int, str]], *, full_content: str | None = None
) -> int | None:
    name = Path(path).name.lower()
    python_source = name.endswith((".py", ".pyi"))
    env_file = name == ".env" or (
        name.startswith(".env.") and name not in {".env.example", ".env.sample", ".env.template"}
    )
    if env_file or name.endswith((".pem", ".key", ".p12", ".pfx")):
        return 1
    if python_source and (
        line_number := _python_secret_literal_line(added, full_content)
    ) is not None:
        return line_number
    for line_number, line in added:
        if PRIVATE_KEY_PREFIX in line and PRIVATE_KEY_SUFFIX in line:
            return line_number
        if any(pattern.search(line) for pattern in STANDALONE_SECRET_PATTERNS):
            return line_number
        for match in SECRET_ASSIGNMENT.finditer(line):
            if python_source and not match.group("key_quote") and not match.group("quote"):
                continue
            raw = match.group("value").strip()
            value = raw.upper()
            allowed = value in SAFE_SECRET_VALUES or raw.startswith(
                ("${", "<", "os.environ", "getenv(", "settings.", "args.")
            )
            if not allowed:
                return line_number
    return None


def _surface_rule(text: str, ruleset: str) -> str | None:
    if ruleset in {"all", "secrets"} and _secret_finding("surface", [(1, text)]):
        return "SECRET_FORBIDDEN"
    if ruleset not in {"all", "boundary"}:
        return None
    finding = _content_finding(
        [(1, text)],
        synthetic=False,
        restricted=False,
        software_provenance=False,
        canonical_governance=False,
    )
    return finding[0] if finding else None


def _commit_messages(repo: Path, mode: str, base: str, head: str) -> list[str]:
    if mode == "staged-diff":
        return []
    output = _git_bytes(repo, "log", "--format=%B%x00", f"{base}..{head}")
    return [message.decode("utf-8", "replace") for message in output.split(b"\0") if message]


def _event_text(path: Path | None) -> list[str]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    pull_request = payload.get("pull_request", {})
    if not isinstance(pull_request, dict):
        return []
    return [
        value
        for value in (pull_request.get("title"), pull_request.get("body"))
        if isinstance(value, str)
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--expected-profile", choices=("public", "private_ops", "test"), required=True
    )
    parser.add_argument("--mode", choices=("staged-diff", "commit-range", "pr-diff"), required=True)
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument(
        "--ruleset", choices=("all", "boundary", "secrets", "synthetic"), default="all"
    )
    parser.add_argument("--github-event", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        config_source = args.config or args.policy
        config_document = json.loads(config_source.read_text(encoding="utf-8"))
        config = config_document["forward_only_git"]
        if (
            policy.get("policy_id") != "edmn.market_data_boundary.v1"
            or policy.get("policy_revision") != 3
            or not isinstance(policy.get("github_allowed"), list)
            or not isinstance(policy.get("github_forbidden"), list)
            or config_document.get("policy_id") != policy["policy_id"]
            or config_document.get("policy_revision") != policy["policy_revision"]
        ):
            raise ValueError("Unsupported policy")
        baseline = config["baseline_sha"]
        required_globs = (
            "frozen_path_globs",
            "sensitive_path_globs",
            "forbidden_path_globs",
            "synthetic_fixture_globs",
            "governance_path_globs",
            "git_safe_receipt_globs",
            "software_provenance_path_globs",
            "allowed_path_globs",
        )
        if not re.fullmatch(r"[0-9a-f]{40}", baseline) or not all(
            isinstance(config.get(name), list) and config[name] for name in required_globs
        ):
            raise ValueError("Incomplete enforcement configuration")
        _validate_contract(config, args.expected_profile)
        _git(args.repo, "cat-file", "-e", f"{baseline}^{{commit}}")
        anchor = "HEAD" if args.mode == "staged-diff" else (args.base or "")
        if not anchor:
            raise ValueError("A base commit is required")
        _git(args.repo, "merge-base", "--is-ancestor", baseline, anchor)
        diff_base, diff_head = _diff_base(args.repo, args.mode, args.base, args.head)
        findings: list[tuple[str, str]] = []
        changed_paths = _changed_paths(args.repo, args.mode, diff_base, diff_head)
        if args.ruleset in {"all", "boundary"}:
            frozen_globs = config.get("frozen_path_globs", [])
            frozen_blobs = _frozen_blob_ids(args.repo, baseline, frozen_globs)
            for path in changed_paths:
                if _matches(path, frozen_globs):
                    findings.append((_redacted_location(), "LEGACY_FROZEN_PATH_MODIFIED"))
                    continue
                elif _matches(path, config.get("forbidden_path_globs", [])):
                    findings.append((_redacted_location(), _forbidden_path_rule(path)))
                    continue
                entry = _entry(args.repo, args.mode, args.head, path)
                if entry is not None and entry[1] in frozen_blobs:
                    findings.append((_redacted_location(), "LEGACY_FROZEN_PATH_MODIFIED"))
                    continue
                entry_mode = entry[0] if entry is not None else None
                if entry_mode not in {None, "100644", "100755"}:
                    findings.append((_redacted_location(), "REAL_VENUE_DATA_FORBIDDEN"))
                    continue
                content = _content(args.repo, args.mode, args.head, path)
                if entry_mode is not None and content is None:
                    findings.append((_redacted_location(), "REAL_VENUE_DATA_FORBIDDEN"))
                    continue
                governance = _matches(path, config.get("governance_path_globs", []))
                fixture = _matches(path, config.get("synthetic_fixture_globs", []))
                if _matches(path, config.get("git_safe_receipt_globs", [])):
                    if content is None or not _valid_git_safe_receipt(content):
                        findings.append((_redacted_location(), "REAL_VENUE_DATA_FORBIDDEN"))
                    continue
                if not (
                    governance
                    or fixture
                    or _matches(path, config.get("allowed_path_globs", []))
                ):
                    findings.append((_redacted_location(), "REAL_VENUE_DATA_FORBIDDEN"))
                    continue
                added = _added_lines(args.repo, args.mode, diff_base, diff_head, path)
                restricted = governance or path.endswith((".py", ".pyi", ".sh", ".toml"))
                finding = _content_finding(
                    added,
                    synthetic=fixture,
                    restricted=restricted,
                    software_provenance=_matches(
                        path, config.get("software_provenance_path_globs", [])
                    ),
                    canonical_governance=governance,
                )
                if finding:
                    rule_id, line_number = finding
                    findings.append((_redacted_location(line_number), rule_id))
                elif not fixture and not governance and path.lower().endswith(
                    (".json", ".jsonl", ".csv", ".parquet", ".zst", ".zip", ".gz")
                ):
                    findings.append((_redacted_location(), "REAL_VENUE_DATA_FORBIDDEN"))
        if args.ruleset in {"all", "synthetic"}:
            fixture_globs = config.get("synthetic_fixture_globs", [])
            for path in changed_paths:
                if not _matches(path, fixture_globs):
                    continue
                content = _content(args.repo, args.mode, args.head, path)
                if content is not None and not _synthetic_provenance(content):
                    findings.append((_redacted_location(), "SYNTHETIC_PROVENANCE_MISSING"))
        if args.ruleset in {"all", "secrets"}:
            for path in changed_paths:
                full_content = (
                    _content(args.repo, args.mode, args.head, path)
                    if path.lower().endswith((".py", ".pyi"))
                    else None
                )
                line_number = _secret_finding(
                    path,
                    _added_lines(args.repo, args.mode, diff_base, diff_head, path),
                    full_content=full_content,
                )
                if line_number is not None:
                    findings.append((_redacted_location(line_number), "SECRET_FORBIDDEN"))
        for message in _commit_messages(args.repo, args.mode, diff_base, diff_head):
            rule_id = _surface_rule(message, args.ruleset)
            if rule_id:
                findings.append(("<COMMIT_MESSAGE>", rule_id))
        for surface in _event_text(args.github_event):
            rule_id = _surface_rule(surface, args.ruleset)
            if rule_id:
                findings.append(("<PR_METADATA>", rule_id))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        print("FORWARD_ONLY_DATA_BOUNDARY_CONFIGURATION_FAILED", file=sys.stderr)
        return 2
    if findings:
        for path, rule_id in findings:
            print(f"path={path} rule_id={rule_id}", file=sys.stderr)
        print("FORWARD_ONLY_DATA_BOUNDARY_FAILED", file=sys.stderr)
        return 1
    print(PASS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
