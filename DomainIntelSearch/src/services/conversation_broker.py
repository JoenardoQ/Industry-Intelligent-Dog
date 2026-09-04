"""Industry-scoped Agent conversation orchestration.

The broker may ask an Agent to suggest an allowlisted IntDog action, but it
never executes that action. Confirmation and enqueueing belong to the API
boundary so they remain an explicit local-user operation.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Callable

from .agent_sessions import AcpSession, AgentSessionError, CodexAppServerSession
from .capability_manifest import capability_or_unknown


ACTION_BLOCK = re.compile(
    r"```intdog-action\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
ALLOWED_ACTIONS = frozenset({
    "daily", "weekly", "monthly", "quarterly", "report", "deep_report",
    "impact", "lab", "bootstrap", "coverage", "history",
})
ALLOWED_PARAMETERS = frozenset({
    "kind", "event", "pipeline_mode",
})


def _event_text(events: list[dict]) -> str:
    parts: list[str] = []
    for row in events:
        method = str(row.get("method") or "")
        if "delta" not in method.casefold() and method != "session/update":
            continue
        params = row.get("params") if isinstance(row.get("params"), dict) else {}
        value = params.get("delta") or params.get("text")
        update = params.get("update")
        if not value and isinstance(update, dict):
            value = update.get("delta") or update.get("text") or update.get("content")
        if isinstance(value, str):
            parts.append(value)
    return "".join(parts).strip()


class NativeSessionRunner:
    """Keeps one native Agent process per IntDog conversation session."""

    def __init__(self):
        self._sessions: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    def __call__(self, provider: str, workspace: Path, prompt: str,
                 external_session_id: str) -> dict:
        from .provider_factory import create_provider
        from .provider_readiness import session_readiness

        spec = capability_or_unknown(provider)
        state = session_readiness(provider, workspace)
        executable = str(state.get("resolved_executable") or state.get("executable") or "")
        if spec.native_session_implemented and executable and state.get("ready"):
            key = (provider, str(workspace))
            entry = None
            candidate_session = None
            try:
                with self._lock:
                    entry = self._sessions.get(key)
                    created = entry is None
                    if created:
                        candidate_session = (
                            CodexAppServerSession(executable, workspace)
                            if spec.session_protocol == "codex_app_server"
                            else AcpSession(executable, spec.native_args, workspace))
                        candidate_session.start()
                        entry = {"session": candidate_session, "session_id": "",
                                 "turn_lock": threading.Lock()}
                        self._sessions[key] = entry
                session = entry["session"]
                with entry["turn_lock"]:
                    session_id = str(entry.get("session_id") or external_session_id or "")
                    if spec.session_protocol == "codex_app_server":
                        if created and session_id:
                            session.resume_thread(session_id)
                        elif not session_id:
                            session_id = session.start_thread()
                        result = session.start_turn(session_id, prompt)
                    else:
                        if created and session_id:
                            session.load_session(session_id)
                        elif not session_id:
                            session_id = session.new_session()
                        result = session.prompt(session_id, prompt)
                    entry["session_id"] = session_id
                text = _event_text(result.get("events", []))
                if not text:
                    text = str((result.get("result") or {}).get("text") or "").strip()
                if not text:
                    raise AgentSessionError(
                        "Agent session completed without readable text")
                return {"text": text, "connection": spec.session_protocol,
                        "external_session_id": session_id}
            except (AgentSessionError, OSError) as exc:
                with self._lock:
                    failed = self._sessions.pop(key, None)
                failed_session = ((failed or {}).get("session")
                                  if failed is not None else candidate_session)
                if failed_session is not None:
                    try:
                        failed_session.close()
                    except Exception:
                        pass
                if spec.execution_level != "direct" or "cli" not in spec.fallbacks:
                    raise
                service = create_provider({}, provider, workspace)
                result = service.complete(prompt)
                protocol_name = ("Codex App Server"
                                 if spec.session_protocol == "codex_app_server"
                                 else spec.session_protocol)
                return {
                    "text": result.text,
                    "connection": "cli_fallback",
                    "external_session_id": "",
                    "connection_warning": (
                        f"{protocol_name} 连接失败（{type(exc).__name__}），"
                        f"已改用同一 {spec.name}。"),
                }

        # Existing CLI and API implementations remain a deliberate fallback.
        # The response metadata exposes this downgrade to the UI.
        service = create_provider({}, provider, workspace)
        result = service.complete(prompt)
        return {"text": result.text,
                "connection": "api" if spec.kind == "api" else "cli",
                "external_session_id": ""}

    def close(self) -> None:
        with self._lock:
            sessions, self._sessions = self._sessions, {}
        for entry in sessions.values():
            entry["session"].close()


class ConversationBroker:
    def __init__(self, repo, data_root: str | Path,
                 *, runner: Callable | None = None):
        self.repo = repo
        self.data_root = Path(data_root)
        self.runner = runner or NativeSessionRunner()

    def state(self, folder: str, provider: str) -> dict:
        conversation = self.repo.get_or_create_conversation(folder, provider)
        return {
            "conversation": conversation,
            "messages": self.repo.list_conversation_messages(conversation["id"]),
            "proposals": self.repo.list_action_proposals(conversation["id"]),
            "capability": capability_or_unknown(provider).public(),
        }

    def chat(self, folder: str, provider: str, message: str) -> dict:
        message = str(message or "").strip()
        if not message or len(message) > 20_000:
            raise ValueError("message must contain 1-20000 characters")
        conversation = self.repo.get_or_create_conversation(folder, provider)
        self.repo.append_conversation_message(conversation["id"], "user", message)
        history = self.repo.list_conversation_messages(conversation["id"], limit=24)
        prompt = self._prompt(folder, history)
        result = self.runner(
            provider, self.data_root / folder, prompt,
            str(conversation.get("external_session_id") or ""))
        raw = str(result.get("text") or "").strip()
        if result.get("external_session_id") != conversation.get("external_session_id"):
            self.repo.set_conversation_session(
                conversation["id"], str(result.get("external_session_id") or ""))
        proposals = []
        for match in ACTION_BLOCK.finditer(raw):
            proposal = self._validated_proposal(match.group(1), provider)
            if proposal:
                proposals.append(self.repo.create_action_proposal(
                    conversation["id"], proposal["action"], {
                        **proposal["parameters"],
                        "summary": proposal["summary"],
                    }))
        visible = ACTION_BLOCK.sub("", raw).strip()
        if not visible:
            visible = "我已生成一个待确认的执行建议。" if proposals else raw
        self.repo.append_conversation_message(
            conversation["id"], "assistant", visible,
            {key: value for key, value in {
                "connection": str(result.get("connection") or "unknown"),
                "connection_warning": str(result.get("connection_warning") or ""),
            }.items() if value})
        state = self.state(folder, provider)
        state["connection"] = str(result.get("connection") or "unknown")
        if result.get("connection_warning"):
            state["connection_warning"] = str(result["connection_warning"])
        return state

    @staticmethod
    def _validated_proposal(raw: str, provider: str) -> dict | None:
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict) or value.get("action") not in ALLOWED_ACTIONS:
            return None
        parameters = value.get("parameters") or {}
        if not isinstance(parameters, dict) or set(parameters) - ALLOWED_PARAMETERS:
            return None
        parameters = {key: item for key, item in parameters.items()
                      if item is not None and str(item).strip()}
        if any(not isinstance(value, str) for value in parameters.values()):
            return None
        if len(parameters.get("kind", "")) > 80 or len(parameters.get("event", "")) > 1000:
            return None
        if parameters.get("pipeline_mode", "") not in {"", "aggregate", "generate"}:
            return None
        spec = capability_or_unknown(provider)
        if spec.execution_level == "direct":
            parameters["provider"] = provider
            parameters["execution_mode"] = "direct"
        else:
            parameters.pop("provider", None)
            parameters["execution_mode"] = "taskpack"
        return {"action": value["action"], "parameters": parameters,
                "summary": str(value.get("summary") or value["action"])[:500]}

    @staticmethod
    def _prompt(folder: str, history: list[dict]) -> str:
        transcript = "\n".join(
            f"{row['role']}: {row['content']}" for row in history[-16:])
        return f"""You are the research assistant for IntDog industry `{folder}`.
Answer the user's question with concise, evidence-aware analysis. Do not claim
to have changed IntDog data or started a task. If an IntDog task would help,
you may append exactly one fenced `intdog-action` JSON object with keys:
action, parameters, summary. Allowed actions: {', '.join(sorted(ALLOWED_ACTIONS))}.
The host will validate it and require explicit user confirmation.

Conversation:
{transcript}"""

    def close(self) -> None:
        close = getattr(self.runner, "close", None)
        if close:
            close()
