"""Local, industry-scoped Agent conversations and execution proposals."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from .models import json_text, json_value, utc_now


def _proposal(row) -> dict:
    value = dict(row)
    value["payload"] = json_value(value.pop("payload_json"), {})
    return value


class ConversationRepositoryMixin:
    def get_or_create_conversation(self, folder: str, provider: str) -> dict:
        industry_id = self.industry_id(folder)
        provider = str(provider or "").strip().casefold()
        if not provider:
            raise ValueError("provider is required")
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT * FROM agent_conversations
                WHERE industry_id=? AND provider=? AND archived_at IS NULL""",
                (industry_id, provider)).fetchone()
            if row is None:
                conversation_id = "conv_" + uuid.uuid4().hex
                con.execute("""INSERT INTO agent_conversations
                    (id,industry_id,provider,external_session_id,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)""",
                    (conversation_id, industry_id, provider, "", now, now))
                row = con.execute(
                    "SELECT * FROM agent_conversations WHERE id=?",
                    (conversation_id,)).fetchone()
        return dict(row)

    def set_conversation_session(self, conversation_id: str,
                                 external_session_id: str) -> None:
        with self.transaction() as con:
            changed = con.execute("""UPDATE agent_conversations
                SET external_session_id=?,updated_at=? WHERE id=?
                AND archived_at IS NULL""",
                (str(external_session_id or "")[:500], utc_now(),
                 conversation_id)).rowcount
        if changed != 1:
            raise FileNotFoundError("conversation not found")

    def append_conversation_message(self, conversation_id: str, role: str,
                                    content: str, metadata: dict | None = None) -> dict:
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError("invalid conversation role")
        content = str(content or "").strip()
        if not content or len(content) > 200_000:
            raise ValueError("message content must contain 1-200000 characters")
        message_id, now = "msg_" + uuid.uuid4().hex, utc_now()
        with self.transaction() as con:
            if not con.execute("""SELECT 1 FROM agent_conversations
                    WHERE id=? AND archived_at IS NULL""", (conversation_id,)).fetchone():
                raise FileNotFoundError("conversation not found")
            con.execute("""INSERT INTO conversation_messages
                (id,conversation_id,role,content,metadata_json,created_at)
                VALUES(?,?,?,?,?,?)""",
                (message_id, conversation_id, role, content,
                 json_text(metadata or {}), now))
            con.execute("UPDATE agent_conversations SET updated_at=? WHERE id=?",
                        (now, conversation_id))
        return {"id": message_id, "conversation_id": conversation_id,
                "role": role, "content": content,
                "metadata": metadata or {}, "created_at": now}

    def list_conversation_messages(self, conversation_id: str, *,
                                   limit: int = 200) -> list[dict]:
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM conversation_messages
                WHERE conversation_id=? AND rowid IN (
                    SELECT rowid FROM conversation_messages WHERE conversation_id=?
                    ORDER BY rowid DESC LIMIT ?)
                ORDER BY rowid""",
                (conversation_id, conversation_id,
                 max(1, min(int(limit), 1000)))).fetchall()
        output = []
        for row in rows:
            value = dict(row)
            value["metadata"] = json_value(value.pop("metadata_json"), {})
            output.append(value)
        return output

    def create_action_proposal(self, conversation_id: str, action: str,
                               payload: dict, *, ttl_seconds: int = 1800) -> dict:
        action = str(action or "").strip()
        if not action or not isinstance(payload, dict):
            raise ValueError("action and payload are required")
        ttl_seconds = max(30, min(int(ttl_seconds), 86_400))
        proposal_id = "prop_" + uuid.uuid4().hex
        now = utc_now()
        expires = (datetime.now(timezone.utc) + timedelta(
            seconds=ttl_seconds)).isoformat(timespec="seconds")
        with self.transaction() as con:
            if not con.execute("""SELECT 1 FROM agent_conversations
                    WHERE id=? AND archived_at IS NULL""", (conversation_id,)).fetchone():
                raise FileNotFoundError("conversation not found")
            con.execute("""INSERT INTO action_proposals
                (id,conversation_id,revision,action,payload_json,status,
                 expires_at,created_at,updated_at) VALUES(?,?,?,?,?,'pending',?,?,?)""",
                (proposal_id, conversation_id, 1, action, json_text(payload),
                 expires, now, now))
            row = con.execute("SELECT * FROM action_proposals WHERE id=?",
                              (proposal_id,)).fetchone()
        return _proposal(row)

    def list_action_proposals(self, conversation_id: str) -> list[dict]:
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM action_proposals
                WHERE conversation_id=? ORDER BY created_at,id""",
                (conversation_id,)).fetchall()
        return [_proposal(row) for row in rows]

    def confirm_action_proposal(self, folder: str, proposal_id: str,
                                revision: int) -> dict:
        industry_id = self.industry_id(folder)
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT p.*,c.industry_id FROM action_proposals p
                JOIN agent_conversations c ON c.id=p.conversation_id
                WHERE p.id=?""", (proposal_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("proposal not found")
            if row["industry_id"] != industry_id:
                raise ValueError("proposal belongs to another industry")
            if int(row["revision"]) != int(revision):
                raise ValueError("proposal revision changed")
            if row["status"] != "pending":
                raise ValueError("proposal is not pending")
            if str(row["expires_at"]) <= now:
                con.execute("""UPDATE action_proposals SET status='expired',updated_at=?
                    WHERE id=? AND status='pending'""", (now, proposal_id))
                raise ValueError("proposal expired")
            changed = con.execute("""UPDATE action_proposals
                SET status='confirmed',confirmed_at=?,updated_at=?
                WHERE id=? AND status='pending' AND revision=?""",
                (now, now, proposal_id, revision)).rowcount
            if changed != 1:
                raise ValueError("proposal is not pending")
            updated = con.execute("SELECT * FROM action_proposals WHERE id=?",
                                  (proposal_id,)).fetchone()
        return _proposal(updated)

    def reject_action_proposal(self, folder: str, proposal_id: str,
                               revision: int) -> dict:
        industry_id = self.industry_id(folder)
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT p.*,c.industry_id FROM action_proposals p
                JOIN agent_conversations c ON c.id=p.conversation_id WHERE p.id=?""",
                (proposal_id,)).fetchone()
            if row is None:
                raise FileNotFoundError("proposal not found")
            if row["industry_id"] != industry_id or int(row["revision"]) != int(revision):
                raise ValueError("proposal industry or revision mismatch")
            if row["status"] != "pending":
                raise ValueError("proposal is not pending")
            con.execute("""UPDATE action_proposals SET status='rejected',updated_at=?
                WHERE id=?""", (now, proposal_id))
            updated = con.execute("SELECT * FROM action_proposals WHERE id=?",
                                  (proposal_id,)).fetchone()
        return _proposal(updated)

    def finish_action_proposal(self, proposal_id: str, *, task_run_id: str = "",
                               error: str = "") -> dict:
        status = "executed" if task_run_id else "failed"
        with self.transaction() as con:
            changed = con.execute("""UPDATE action_proposals SET status=?,task_run_id=?,
                updated_at=? WHERE id=? AND status='confirmed'""",
                (status, task_run_id or None, utc_now(), proposal_id)).rowcount
            if changed != 1:
                raise ValueError("proposal is not confirmed")
            row = con.execute("SELECT * FROM action_proposals WHERE id=?",
                              (proposal_id,)).fetchone()
        value = _proposal(row)
        if error:
            value["error"] = str(error)[:1000]
        return value
