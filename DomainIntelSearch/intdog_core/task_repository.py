"""Authoritative, transactional task ledger for foreground and background work."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import json_text, json_value, utc_now


TASK_STATES = (
    "queued", "running", "cancelling", "paused", "completed", "partial",
    "failed", "cancelled", "interrupted",
)
TASK_STATE_SET = frozenset(TASK_STATES)
TASK_TERMINAL_STATES = frozenset(
    {"completed", "partial", "failed", "cancelled", "interrupted"})
BACKGROUND_ORIGINS = frozenset({"system_schedule", "background_worker"})
BACKGROUND_PERMISSION_FREE_PROVIDERS = frozenset(
    {"local", "none", "public", "public_sources"})
TASK_ORIGINS = frozenset({"app", "manual", *BACKGROUND_ORIGINS})
TASK_TRANSITIONS = {
    "queued": frozenset({"running", "cancelling", "paused", "cancelled"}),
    "running": frozenset({
        "cancelling", "paused", "completed", "partial", "failed",
        "cancelled", "interrupted",
    }),
    "cancelling": frozenset({"cancelled", "failed", "interrupted"}),
    "paused": frozenset({"queued", "cancelled"}),
    "completed": frozenset(),
    "partial": frozenset({"queued", "cancelled"}),
    "failed": frozenset({"queued", "cancelled"}),
    "cancelled": frozenset(),
    "interrupted": frozenset({"queued", "cancelled"}),
}

_SECRET_KEY = re.compile(
    r"(?i)(api[_ -]?key|access[_ -]?token|authorization|password|secret|credential)$")
_BEARER = re.compile(r"(?i)\b(?:basic|bearer)\s+\S+")
_SK_SECRET = re.compile(r"(?i)\bsk-[A-Za-z0-9._-]+")
_CREDENTIAL_REF = re.compile(r"^credref:[A-Za-z0-9._:-]{1,180}$")


class TaskLedger(Protocol):
    def create_task(self, *, folder: str, operation: str, input: dict,
                    origin: str, provider: str, **metadata) -> dict: ...

    def heartbeat(self, run_id: str, *, owner: str, stage: str, progress: int,
                  checkpoint: dict) -> None: ...

    def transition(self, run_id: str, *, expected: set[str], target: str,
                   error: dict | None = None, owner: str | None = None) -> dict: ...

    def claim_expired(self, run_id: str, owner: str, ttl_seconds: int) -> bool: ...


def _required(value: object, name: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _redact(value: object, *, key: str = "", depth: int = 0) -> object:
    if depth > 20:
        return "[redacted-depth-limit]"
    if key and _SECRET_KEY.search(key):
        return "***"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, key=str(item_key), depth=depth + 1)
                for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return _SK_SECRET.sub("***", _BEARER.sub("***", value))
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("task metadata must contain finite numbers")
        return value
    return str(value)


def _time_window(value: dict | None) -> dict:
    if value is None:
        return {"start": None, "end": None, "timezone": None}
    if not isinstance(value, dict):
        raise ValueError("time_window must be an object")
    start = _required(value.get("start"), "time_window.start")
    end = _required(value.get("end"), "time_window.end")
    zone_name = _required(value.get("timezone"), "time_window.timezone")
    try:
        ZoneInfo(zone_name)
        start_value = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_value = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("time_window requires valid ISO timestamps and IANA timezone") from exc
    if start_value.tzinfo is None or end_value.tzinfo is None:
        raise ValueError("time_window timestamps must include an offset")
    if start_value >= end_value:
        raise ValueError("time_window.start must be before time_window.end")
    return {"start": start, "end": end, "timezone": zone_name}


def _task_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["input"] = json_value(item.pop("input_json"), {})
    item["checkpoint"] = json_value(item.pop("checkpoint_json"), {})
    item["error"] = json_value(item.pop("error_json"), {})
    item["time_window"] = {
        "start": item.pop("window_start"),
        "end": item.pop("window_end"),
        "timezone": item.pop("window_timezone"),
    }
    return item


class TaskRepositoryMixin:
    @staticmethod
    def task_states() -> tuple[str, ...]:
        return TASK_STATES

    @staticmethod
    def _insert_task_event(con: sqlite3.Connection, run_id: str, *,
                           from_status: str | None, to_status: str,
                           action: str, actor: str, details: dict | None = None) -> None:
        con.execute("""INSERT INTO task_state_events
            (run_id,from_status,to_status,action,actor,details_json,occurred_at)
            VALUES(?,?,?,?,?,?,?)""",
                    (run_id, from_status, to_status, action, actor,
                     json_text(_redact(details or {})), utc_now()))

    @staticmethod
    def _authorization_allowed(con: sqlite3.Connection, industry_id: str,
                               provider: str, operation: str) -> bool:
        if provider.casefold() in BACKGROUND_PERMISSION_FREE_PROVIDERS:
            return True
        return bool(con.execute("""SELECT 1 FROM background_authorizations
            WHERE industry_id=? AND provider=? AND operation=? AND allowed=1""",
                                (industry_id, provider, operation)).fetchone())

    def create_task(self, *, folder: str, operation: str, input: dict,
                    origin: str, provider: str, model: str = "",
                    parent_run_id: str | None = None,
                    time_window: dict | None = None, output_path: str = "",
                    credential_handle_ref: str | None = None) -> dict:
        industry_id = self.industry_id(folder)
        operation = _required(operation, "operation")
        provider = _required(provider, "provider")
        origin = _required(origin, "origin").casefold()
        if origin not in TASK_ORIGINS:
            raise ValueError(f"unknown task origin: {origin}")
        if not isinstance(input, dict):
            raise ValueError("task input must be an object")
        safe_input = _redact(input)
        encoded_input = json_text(safe_input)
        if len(encoded_input.encode("utf-8")) > 262_144:
            raise ValueError("task input exceeds 256 KiB")
        window = _time_window(time_window)
        model = " ".join(str(model or "").split()).strip()
        output_path = str(output_path or "").strip()
        if credential_handle_ref is not None:
            credential_handle_ref = str(credential_handle_ref).strip()
            if not _CREDENTIAL_REF.fullmatch(credential_handle_ref):
                raise ValueError("credential_handle_ref must be an opaque credref identifier")
        run_id = f"task_{uuid.uuid4().hex}"
        now = utc_now()
        with self.transaction() as con:
            if parent_run_id:
                parent = con.execute("""SELECT industry_id FROM task_runs WHERE id=?""",
                                     (parent_run_id,)).fetchone()
                if not parent or parent["industry_id"] != industry_id:
                    raise ValueError("parent task must exist in the same industry")
            authorized = (origin not in BACKGROUND_ORIGINS or
                          self._authorization_allowed(
                              con, industry_id, provider, operation))
            status = "queued" if authorized else "paused"
            error = {} if authorized else {
                "category": "background_authorization_required",
                "message": "Background use is not authorized for this provider, industry and task",
            }
            con.execute("""INSERT INTO task_runs
                (id,industry_id,operation,origin,status,input_json,provider,model,
                 parent_run_id,window_start,window_end,window_timezone,output_path,
                 stage,progress,checkpoint_json,error_json,credential_handle_ref,
                 created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'queued',0,'{}',?,?,?,?)""",
                        (run_id, industry_id, operation, origin, status, encoded_input,
                         provider, model, parent_run_id, window["start"], window["end"],
                         window["timezone"], output_path, json_text(error),
                         credential_handle_ref, now, now))
            self._insert_task_event(
                con, run_id, from_status=None, to_status=status, action="created",
                actor=origin, details={"authorization_required": not authorized})
            row = con.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        return _task_dict(row)

    def get_task(self, run_id: str) -> dict:
        with self.connection() as con:
            row = con.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f"task not found: {run_id}")
        return _task_dict(row)

    def list_tasks(self, folder: str | None = None, *, status: str = "",
                   limit: int = 500) -> list[dict]:
        sql = "SELECT t.* FROM task_runs t"
        args: list[object] = []
        clauses = []
        if folder:
            sql += " JOIN industries i ON i.id=t.industry_id"
            clauses.append("i.folder=?"); args.append(folder)
        if status:
            if status not in TASK_STATE_SET:
                raise ValueError("unknown task status")
            clauses.append("t.status=?"); args.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY t.updated_at DESC,t.id DESC LIMIT ?"
        args.append(max(1, min(int(limit), 2000)))
        with self.connection() as con:
            rows = con.execute(sql, args).fetchall()
        return [_task_dict(row) for row in rows]

    def list_task_events(self, run_id: str) -> list[dict]:
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM task_state_events
                WHERE run_id=? ORDER BY id""", (run_id,)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["details"] = json_value(item.pop("details_json"), {})
            output.append(item)
        return output

    def claim_expired(self, run_id: str, owner: str, ttl_seconds: int) -> bool:
        owner = _required(owner, "owner")
        ttl_seconds = int(ttl_seconds)
        if ttl_seconds < 1 or ttl_seconds > 86_400:
            raise ValueError("ttl_seconds must be between 1 and 86400")
        now = utc_now()
        expires = (datetime.now(timezone.utc) + timedelta(
            seconds=ttl_seconds)).isoformat(timespec="seconds")
        with self.transaction() as con:
            row = con.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise FileNotFoundError(f"task not found: {run_id}")
            if (row["origin"] in BACKGROUND_ORIGINS and not
                    self._authorization_allowed(
                        con, row["industry_id"], row["provider"], row["operation"])):
                if row["status"] == "queued":
                    error = {"category": "background_authorization_required",
                             "message": "Background authorization is absent or revoked"}
                    con.execute("""UPDATE task_runs SET status='paused',error_json=?,
                        lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?""",
                                (json_text(error), now, run_id))
                    self._insert_task_event(
                        con, run_id, from_status="queued", to_status="paused",
                        action="authorization_blocked", actor=owner, details=error)
                return False
            expired = (not row["lease_expires_at"] or
                       str(row["lease_expires_at"]) <= now)
            if row["status"] == "queued":
                action, previous = "lease_claim", "queued"
            elif row["status"] == "running" and expired:
                action, previous = "lease_takeover", "running"
            else:
                return False
            changed = con.execute("""UPDATE task_runs SET status='running',stage=CASE
                    WHEN stage='queued' THEN 'starting' ELSE stage END,
                    lease_owner=?,lease_expires_at=?,lease_ttl_seconds=?,heartbeat_at=?,
                    started_at=COALESCE(started_at,?),finished_at=NULL,updated_at=?
                WHERE id=? AND status=? AND COALESCE(lease_owner,'')=COALESCE(?, '')
                    AND COALESCE(lease_expires_at,'')=COALESCE(?, '')""",
                    (owner, expires, ttl_seconds, now, now, now, run_id,
                     row["status"], row["lease_owner"], row["lease_expires_at"])).rowcount
            if changed != 1:
                return False
            self._insert_task_event(
                con, run_id, from_status=previous, to_status="running",
                action=action, actor=owner,
                details={"previous_owner": row["lease_owner"],
                         "previous_expiry": row["lease_expires_at"]})
            return True

    def heartbeat(self, run_id: str, *, owner: str, stage: str, progress: int,
                  checkpoint: dict) -> None:
        owner = _required(owner, "owner")
        stage = _required(stage, "stage")
        if isinstance(progress, bool) or int(progress) != progress or not 0 <= int(progress) <= 100:
            raise ValueError("progress must be an integer from 0 to 100")
        if not isinstance(checkpoint, dict):
            raise ValueError("checkpoint must be an object")
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT status,lease_owner,lease_expires_at,
                lease_ttl_seconds FROM task_runs WHERE id=?""",
                              (run_id,)).fetchone()
            if row is None:
                raise FileNotFoundError(f"task not found: {run_id}")
            if row["status"] not in {"running", "cancelling"}:
                raise ValueError("heartbeat requires a running or cancelling task")
            if row["lease_owner"] != owner or not row["lease_expires_at"] or str(
                    row["lease_expires_at"]) <= now:
                raise RuntimeError("task lease was lost before heartbeat")
            expires = (datetime.now(timezone.utc) + timedelta(
                seconds=int(row["lease_ttl_seconds"] or 60))).isoformat(timespec="seconds")
            changed = con.execute("""UPDATE task_runs SET stage=?,progress=?,checkpoint_json=?,
                heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE id=?
                AND status IN ('running','cancelling') AND lease_owner=?
                AND lease_expires_at>?""",
                        (stage, int(progress), json_text(_redact(checkpoint)), now,
                         expires, now, run_id, owner, now)).rowcount
            if changed != 1:
                raise RuntimeError("task lease was lost before heartbeat")

    def transition(self, run_id: str, *, expected: set[str], target: str,
                   error: dict | None = None, owner: str | None = None) -> dict:
        target = str(target or "").casefold()
        expected = {str(value).casefold() for value in expected}
        if target not in TASK_STATE_SET or not expected or not expected <= TASK_STATE_SET:
            raise ValueError("invalid task transition state")
        if error is not None and not isinstance(error, dict):
            raise ValueError("task error must be an object")
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise FileNotFoundError(f"task not found: {run_id}")
            current = str(row["status"])
            if current == target and target in TASK_TERMINAL_STATES:
                return _task_dict(row)
            if current not in expected or target not in TASK_TRANSITIONS[current]:
                raise ValueError(f"invalid task transition: {current} -> {target}")
            terminal = target in TASK_TERMINAL_STATES
            release = target in {
                "queued", "paused", "completed", "partial", "failed",
                "cancelled", "interrupted",
            }
            safe_error = _redact(error or {})
            lease_guarded = current in {"running", "cancelling"} and target != "cancelling"
            normalized_owner = _required(owner, "owner") if lease_guarded else None
            if lease_guarded and (row["lease_owner"] != normalized_owner or
                                  not row["lease_expires_at"] or
                                  str(row["lease_expires_at"]) <= now):
                raise RuntimeError("task lease was lost before transition")
            changed = con.execute("""UPDATE task_runs SET status=?,error_json=?,
                finished_at=?,lease_owner=CASE WHEN ? THEN NULL ELSE lease_owner END,
                lease_expires_at=CASE WHEN ? THEN NULL ELSE lease_expires_at END,
                credential_handle_ref=CASE WHEN ? THEN NULL ELSE credential_handle_ref END,
                updated_at=? WHERE id=? AND status=?
                AND (?=0 OR (lease_owner=? AND lease_expires_at>?))""",
                    (target, json_text(safe_error), now if terminal else None,
                     int(release), int(release), int(terminal), now, run_id, current,
                     int(lease_guarded), normalized_owner, now)).rowcount
            if changed != 1:
                raise RuntimeError("task changed concurrently")
            self._insert_task_event(
                con, run_id, from_status=current, to_status=target,
                action="transition", actor="task-ledger", details={"error": safe_error})
            updated = con.execute("SELECT * FROM task_runs WHERE id=?", (run_id,)).fetchone()
            return _task_dict(updated)

    def update_task_output(self, run_id: str, output_path: str, *, owner: str) -> None:
        owner = _required(owner, "owner")
        value = str(output_path or "").strip()
        if not value:
            return
        now = utc_now()
        with self.transaction() as con:
            changed = con.execute("""UPDATE task_runs SET output_path=?,updated_at=?
                WHERE id=? AND status IN ('running','cancelling')
                AND lease_owner=? AND lease_expires_at>?""",
                (value, now, run_id, owner, now)).rowcount
            if changed != 1:
                if not con.execute("SELECT 1 FROM task_runs WHERE id=?", (run_id,)).fetchone():
                    raise FileNotFoundError(f"task not found: {run_id}")
                raise RuntimeError("task lease was lost before output publication")

    def mark_request_dispatched(self, run_id: str, *, owner: str) -> None:
        owner = _required(owner, "owner")
        now = utc_now()
        with self.transaction() as con:
            changed = con.execute("""UPDATE task_runs SET request_dispatched_at=?,
                credential_handle_ref=NULL,updated_at=?
                WHERE id=? AND status='running' AND lease_owner=?
                    AND lease_expires_at>? AND request_dispatched_at IS NULL""",
                (now, now, run_id, owner, now)).rowcount
            if changed != 1:
                row = con.execute("SELECT request_dispatched_at FROM task_runs WHERE id=?",
                                  (run_id,)).fetchone()
                if not row or not row["request_dispatched_at"]:
                    raise RuntimeError("task lease was lost before request dispatch")

    def recover_expired_tasks(self, *, actor: str, run_id: str | None = None) -> list[str]:
        """Atomically interrupt orphaned executing tasks after their lease expires."""
        actor = _required(actor, "actor")
        now = utc_now()
        recovered: list[str] = []
        with self.transaction() as con:
            rows = con.execute("""SELECT * FROM task_runs
                WHERE status IN ('running','cancelling')
                AND (lease_expires_at IS NULL OR lease_expires_at<=?)
                AND (? IS NULL OR id=?) ORDER BY id""", (now, run_id, run_id)).fetchall()
            for row in rows:
                error = {"category": "expired_lease",
                         "message": "Previous runtime ended before the task reached a terminal state"}
                changed = con.execute("""UPDATE task_runs SET status='interrupted',
                    error_json=?,finished_at=?,lease_owner=NULL,lease_expires_at=NULL,
                    credential_handle_ref=NULL,updated_at=?
                    WHERE id=? AND status=? AND COALESCE(lease_owner,'')=COALESCE(?, '')
                    AND COALESCE(lease_expires_at,'')=COALESCE(?, '')""",
                    (json_text(error), now, now, row["id"], row["status"],
                     row["lease_owner"], row["lease_expires_at"])).rowcount
                if changed != 1:
                    continue
                recovered.append(row["id"])
                self._insert_task_event(
                    con, row["id"], from_status=row["status"], to_status="interrupted",
                    action="expired_lease_recovery", actor=actor, details=error)
        return recovered

    def grant_background_authorization(self, folder: str, *, provider: str,
                                       operation: str, actor: str) -> dict:
        industry_id = self.industry_id(folder)
        provider = _required(provider, "provider")
        operation = _required(operation, "operation")
        actor = _required(actor, "actor")
        now = utc_now()
        with self.transaction() as con:
            con.execute("""INSERT INTO background_authorizations
                (industry_id,provider,operation,allowed,granted_by,granted_at,
                 revoked_by,revoked_at,updated_at) VALUES(?,?,?,1,?,?,NULL,NULL,?)
                ON CONFLICT(industry_id,provider,operation) DO UPDATE SET
                allowed=1,granted_by=excluded.granted_by,granted_at=excluded.granted_at,
                revoked_by=NULL,revoked_at=NULL,updated_at=excluded.updated_at""",
                (industry_id, provider, operation, actor, now, now))
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,?,?,'background_authorization',?,?)""",
                (now, actor, "grant_background_authorization",
                 f"{industry_id}:{provider}:{operation}",
                 json_text({"provider": provider, "operation": operation})))
        return {"folder": folder, "provider": provider, "operation": operation,
                "allowed": True, "updated_at": now}

    def revoke_background_authorization(self, folder: str, *, provider: str,
                                        operation: str, actor: str,
                                        reason: str) -> dict:
        industry_id = self.industry_id(folder)
        provider = _required(provider, "provider")
        operation = _required(operation, "operation")
        actor = _required(actor, "actor")
        reason = _required(reason, "reason")
        now = utc_now()
        affected: list[str] = []
        with self.transaction() as con:
            con.execute("""INSERT INTO background_authorizations
                (industry_id,provider,operation,allowed,granted_by,granted_at,
                 revoked_by,revoked_at,updated_at) VALUES(?,?,?,0,'','',?,?,?)
                ON CONFLICT(industry_id,provider,operation) DO UPDATE SET
                allowed=0,revoked_by=excluded.revoked_by,revoked_at=excluded.revoked_at,
                updated_at=excluded.updated_at""",
                (industry_id, provider, operation, actor, now, now))
            rows = con.execute("""SELECT * FROM task_runs WHERE industry_id=?
                AND provider=? AND operation=? AND origin IN
                ('system_schedule','background_worker')
                AND status IN ('queued','running','paused','cancelling')""",
                (industry_id, provider, operation)).fetchall()
            for row in rows:
                target = None
                if row["status"] == "queued":
                    target = "cancelled"
                elif row["status"] == "running" and not row["request_dispatched_at"]:
                    target = "cancelling"
                con.execute("""UPDATE task_runs SET credential_handle_ref=NULL,
                    status=COALESCE(?,status),finished_at=CASE WHEN ?='cancelled'
                        THEN ? ELSE finished_at END,updated_at=? WHERE id=?""",
                    (target, target, now, now, row["id"]))
                if target:
                    affected.append(row["id"])
                    self._insert_task_event(
                        con, row["id"], from_status=row["status"], to_status=target,
                        action="authorization_revoked", actor=actor,
                        details={"reason": reason,
                                 "request_already_dispatched": bool(
                                     row["request_dispatched_at"])})
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,?,?,'background_authorization',?,?)""",
                (now, actor, "revoke_background_authorization",
                 f"{industry_id}:{provider}:{operation}",
                 json_text({"provider": provider, "operation": operation,
                            "reason": reason, "affected_run_ids": affected})))
        return {"folder": folder, "provider": provider, "operation": operation,
                "allowed": False, "affected_run_ids": affected, "updated_at": now}

    def list_background_authorizations(self, folder: str | None = None) -> list[dict]:
        sql = """SELECT i.folder,a.provider,a.operation,a.allowed,a.granted_by,
            a.granted_at,a.revoked_by,a.revoked_at,a.updated_at
            FROM background_authorizations a
            JOIN industries i ON i.id=a.industry_id WHERE i.status='active'"""
        args: list[object] = []
        if folder:
            sql += " AND i.folder=?"; args.append(folder)
        sql += " ORDER BY i.folder,a.provider,a.operation"
        with self.connection() as con:
            rows = [dict(row) for row in con.execute(sql, args)]
        for row in rows:
            row["allowed"] = bool(row["allowed"])
        return rows
