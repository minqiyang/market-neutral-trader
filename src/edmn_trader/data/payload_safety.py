"""Shared checks for raw exchange payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_FORBIDDEN_RAW_KEY_PARTS = (
    "authorization",
    "api_key",
    "apikey",
    "secret",
    "signature",
    "token",
    "private_key",
    "password",
    "headers",
)


def validate_no_secret_payload(value: Mapping[str, Any], *, path: str = "payload") -> None:
    """Reject secret-like keys before payloads are written to repo JSONL."""

    for key, item in value.items():
        key_text = str(key).lower()
        if any(forbidden in key_text for forbidden in _FORBIDDEN_RAW_KEY_PARTS):
            msg = f"{path}.{key} must not contain credentials, headers, or secrets"
            raise ValueError(msg)
        if isinstance(item, Mapping):
            validate_no_secret_payload(item, path=f"{path}.{key}")
        elif isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
            for index, nested_item in enumerate(item):
                if isinstance(nested_item, Mapping):
                    validate_no_secret_payload(nested_item, path=f"{path}.{key}[{index}]")
