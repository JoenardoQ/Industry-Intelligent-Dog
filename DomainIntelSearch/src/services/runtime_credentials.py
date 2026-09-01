"""Process-local credentials installed from the one-use parent pipe."""

from __future__ import annotations

import threading


_LOCK = threading.RLock()
_VALUE: dict[str, str] = {}
_FIELDS = ("provider", "model", "apiKey", "apiBase", "authType")


def install_runtime_credential(value: dict | None) -> None:
    normalized = {field: str((value or {}).get(field) or "").strip()
                  for field in _FIELDS}
    with _LOCK:
        clear_runtime_credential()
        _VALUE.update(normalized)
    if isinstance(value, dict):
        for field in tuple(value):
            value[field] = ""


def credential_bundle(provider: str = "", operation: str = "") -> dict[str, str]:
    """Return a one-task frame scoped to an explicit provider and operation."""
    normalized_provider = str(provider or "").strip().casefold()
    normalized_operation = str(operation or "").strip().casefold()
    if (not normalized_provider or not normalized_operation
            or normalized_provider in {"public", "public_sources", "none", "local"}):
        return {}
    value = credential_for(normalized_provider)
    if not value:
        return {}
    return {**value, "operation": normalized_operation}


def credential_for(provider: str) -> dict[str, str]:
    name = str(provider or "").strip().casefold()
    with _LOCK:
        return dict(_VALUE) if _VALUE.get("provider", "").casefold() == name else {}


def clear_runtime_credential() -> None:
    with _LOCK:
        for key in tuple(_VALUE):
            _VALUE[key] = ""
        _VALUE.clear()
