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
    "kalshi-access",
    "token",
    "private_key",
    "password",
    "headers",
)
_PRIVATE_ACCOUNT_KEYS = {
    "account",
    "account_id",
    "account_number",
    "accounts",
    "client_order_id",
    "fill",
    "fill_id",
    "fills",
    "member_id",
    "order",
    "order_id",
    "orders",
    "portfolio",
    "portfolio_id",
    "portfolios",
    "position",
    "positions",
    "user",
    "user_id",
    "users",
}
_PRIVATE_ACCOUNT_PREFIXES = (
    "account_",
    "client_order_",
    "fill_",
    "member_",
    "order_",
    "portfolio_",
    "position_",
    "user_",
)


def validate_no_secret_payload(value: Mapping[str, Any], *, path: str = "payload") -> None:
    """Reject secret-like keys before payloads are written to repo JSONL."""

    for key, item in value.items():
        key_text = str(key).lower()
        if any(forbidden in key_text for forbidden in _FORBIDDEN_RAW_KEY_PARTS):
            msg = f"{path}.{key} must not contain credentials, headers, or secrets"
            raise ValueError(msg)
        _validate_nested_value(item, path=f"{path}.{key}")


def validate_no_private_account_payload(
    value: Mapping[str, Any],
    *,
    path: str = "payload",
) -> None:
    """Reject private account/order/fill fields from public market-data evidence."""

    for key, item in value.items():
        key_text = str(key).lower()
        if key_text in _PRIVATE_ACCOUNT_KEYS or key_text.startswith(
            _PRIVATE_ACCOUNT_PREFIXES
        ):
            raise ValueError(f"{path}.{key} must not contain private account/order data")
        _validate_private_nested_value(item, path=f"{path}.{key}")


def _validate_private_nested_value(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        validate_no_private_account_payload(value, path=path)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, item in enumerate(value):
            _validate_private_nested_value(item, path=f"{path}[{index}]")


def _validate_nested_value(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        validate_no_secret_payload(value, path=path)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, item in enumerate(value):
            _validate_nested_value(item, path=f"{path}[{index}]")
