"""Canonical sparse workflow settings with explicit inheritance."""

from __future__ import annotations

import re

from .models import json_text, json_value, utc_now


WORKFLOW_DEFAULTS = {
    "provider": "taskpack",
    "execution_mode": "taskpack",
    "pipeline_mode": "generate",
}
_KEYS = frozenset(WORKFLOW_DEFAULTS)
_OPERATION = re.compile(r"^(?:\*|[a-z][a-z0-9_]{0,63})$")


def _settings(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("workflow settings must be an object")
    unknown = set(value) - _KEYS
    if unknown:
        raise ValueError(f"unknown workflow settings: {', '.join(sorted(unknown))}")
    clean = {}
    for key, raw in value.items():
        if key == "provider":
            text = " ".join(str(raw or "").split()).strip()
            if not text:
                raise ValueError("provider cannot be empty")
            clean[key] = text
        elif key == "execution_mode":
            if raw not in {"direct", "taskpack"}:
                raise ValueError("execution_mode must be direct or taskpack")
            clean[key] = raw
        elif key == "pipeline_mode":
            if raw not in {"generate", "aggregate"}:
                raise ValueError("pipeline_mode must be generate or aggregate")
            clean[key] = raw
    return clean


class SettingsRepositoryMixin:
    def _settings_scope(self, folder: str | None) -> str:
        return "global" if folder is None else f"industry:{self.industry_id(folder)}"

    def put_workflow_settings(self, folder: str | None, operation: str,
                              values: dict) -> dict:
        operation = str(operation or "*").strip().casefold()
        if not _OPERATION.fullmatch(operation):
            raise ValueError("invalid workflow operation")
        incoming = _settings(values)
        scope = self._settings_scope(folder)
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT settings_json FROM workflow_settings
                WHERE scope_key=? AND operation=?""", (scope, operation)).fetchone()
            current = json_value(row["settings_json"], {}) if row else {}
            merged = {**current, **incoming}
            con.execute("""INSERT INTO workflow_settings
                (scope_key,operation,settings_json,updated_at) VALUES(?,?,?,?)
                ON CONFLICT(scope_key,operation) DO UPDATE SET
                settings_json=excluded.settings_json,updated_at=excluded.updated_at""",
                        (scope, operation, json_text(merged), now))
        return merged

    def delete_workflow_settings(self, folder: str | None, operation: str) -> bool:
        operation = str(operation or "*").strip().casefold()
        if not _OPERATION.fullmatch(operation):
            raise ValueError("invalid workflow operation")
        scope = self._settings_scope(folder)
        with self.transaction() as con:
            return con.execute("""DELETE FROM workflow_settings
                WHERE scope_key=? AND operation=?""", (scope, operation)).rowcount > 0

    def effective_workflow_settings(self, folder: str, operation: str) -> dict:
        operation = str(operation or "*").strip().casefold()
        if not _OPERATION.fullmatch(operation):
            raise ValueError("invalid workflow operation")
        industry_scope = self._settings_scope(folder)
        wanted = (("global", "*", "global"),
                  ("global", operation, "global_task"),
                  (industry_scope, "*", "industry"),
                  (industry_scope, operation, "industry_task"))
        result = dict(WORKFLOW_DEFAULTS)
        provenance = {key: "system" for key in result}
        with self.connection() as con:
            rows = {(row["scope_key"], row["operation"]): row
                    for row in con.execute("""SELECT scope_key,operation,settings_json
                        FROM workflow_settings WHERE scope_key IN (?,?)
                        AND operation IN ('*',?)""",
                                           ("global", industry_scope, operation)).fetchall()}
        layers = []
        for scope, task, label in wanted:
            row = rows.get((scope, task))
            if not row:
                continue
            values = _settings(json_value(row["settings_json"], {}))
            result.update(values)
            provenance.update({key: label for key in values})
            layers.append({"scope": label, "values": values})
        return {**result, "provenance": provenance, "layers": layers}
