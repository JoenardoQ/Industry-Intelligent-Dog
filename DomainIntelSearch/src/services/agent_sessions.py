"""Native local Agent session transports.

Only protocol framing lives here. IntDog permissions and task execution remain
in the conversation broker; protocol permission requests are never approved
implicitly by these adapters.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable


class AgentSessionError(RuntimeError):
    pass


class JsonLineProcess:
    def __init__(self, command: list[str], cwd: str | Path, *,
                 process_factory: Callable = subprocess.Popen, timeout: float = 60):
        self.command = command
        self.cwd = Path(cwd)
        self.process_factory = process_factory
        self.timeout = timeout
        self.process = None
        self._next_id = 1
        self._messages: queue.Queue[dict] = queue.Queue()
        self._deferred: list[dict] = []
        self._stderr: list[str] = []

    def start(self) -> None:
        if self.process is not None:
            return
        self.process = self.process_factory(
            self.command, cwd=self.cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read(self) -> None:
        assert self.process is not None
        while True:
            line = self.process.stdout.readline()
            if not line:
                self._messages.put({"_transport_error": "Agent session ended"})
                return
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                self._messages.put(value)

    def _read_stderr(self) -> None:
        assert self.process is not None
        while True:
            line = self.process.stderr.readline()
            if not line:
                return
            self._stderr.append(str(line).rstrip()[:1000])
            if len(self._stderr) > 40:
                del self._stderr[:-40]

    def _check_event(self, row: dict) -> None:
        if row.get("_transport_error"):
            detail = "\n".join(self._stderr[-8:]).strip()
            raise AgentSessionError(
                f"{row['_transport_error']}{': ' + detail if detail else ''}")
        if row.get("method") == "session/request_permission":
            raise AgentSessionError(
                "Agent requested tool permission; interactive Agent-tool permission is not supported")

    def notify(self, method: str, params: dict | None = None) -> None:
        self._write({"method": method, "params": params or {}})

    def request(self, method: str, params: dict | None = None, *,
                jsonrpc: bool = False) -> tuple[dict, list[dict]]:
        request_id = self._next_id
        self._next_id += 1
        payload = {"id": request_id, "method": method, "params": params or {}}
        if jsonrpc:
            payload["jsonrpc"] = "2.0"
        self._write(payload)
        events: list[dict] = []
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                row = self._messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise AgentSessionError(f"Agent timed out during {method}") from exc
            self._check_event(row)
            if row.get("id") == request_id:
                if row.get("error"):
                    raise AgentSessionError(str(row["error"]))
                return row.get("result") or {}, events
            events.append(row)
        raise AgentSessionError(f"Agent timed out during {method}")

    def _write(self, payload: dict) -> None:
        if self.process is None:
            raise AgentSessionError("Agent session is not started")
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def events_until(self, predicate: Callable[[dict], bool]) -> list[dict]:
        events: list[dict] = []
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                row = self._messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise AgentSessionError("Agent timed out while streaming events") from exc
            self._check_event(row)
            events.append(row)
            if predicate(row):
                return events
        raise AgentSessionError("Agent timed out while streaming events")

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
        self.process = None


class CodexAppServerSession:
    """Official ``codex app-server`` JSONL/stdio client."""

    def __init__(self, executable: str, cwd: str | Path, **kwargs):
        self.transport = JsonLineProcess([executable, "app-server"], cwd, **kwargs)

    def start(self) -> None:
        self.transport.start()
        self.transport.request("initialize", {
            "clientInfo": {"name": "IntDog", "version": "4.1"},
            "capabilities": {"experimentalApi": False},
        })
        self.transport.notify("initialized")

    def start_thread(self) -> str:
        result, _ = self.transport.request("thread/start", {
            "cwd": str(self.transport.cwd), "sandbox": "read-only",
            "approvalPolicy": "never",
        })
        thread = result.get("thread") or {}
        thread_id = thread.get("id") or result.get("threadId")
        if not thread_id:
            raise AgentSessionError("Codex did not return a thread id")
        return str(thread_id)

    def resume_thread(self, thread_id: str) -> None:
        self.transport.request("thread/resume", {"threadId": thread_id})

    def start_turn(self, thread_id: str, prompt: str) -> dict:
        result, events = self.transport.request("turn/start", {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
        })
        turn = result.get("turn") or {}
        turn_id = str(turn.get("id") or result.get("turnId") or "")
        events.extend(self.transport.events_until(
            lambda row: row.get("method") == "turn/completed" and
            str((row.get("params", {}).get("turn") or {}).get("id") or
                row.get("params", {}).get("turnId") or "") in {"", turn_id}))
        return {"turn_id": turn_id, "events": events}

    def interrupt(self, thread_id: str, turn_id: str) -> None:
        self.transport.request("turn/interrupt", {
            "threadId": thread_id, "turnId": turn_id})

    def close(self) -> None:
        self.transport.close()


class AcpSession:
    """Shared ACP stdio adapter for CLIs that advertise ACP support."""

    def __init__(self, executable: str, args: tuple[str, ...], cwd: str | Path, **kwargs):
        self.transport = JsonLineProcess([executable, *args], cwd, **kwargs)

    def start(self) -> None:
        self.transport.start()
        self.transport.request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {},
            "clientInfo": {"name": "IntDog", "version": "4.1"},
        }, jsonrpc=True)

    def new_session(self) -> str:
        result, _ = self.transport.request("session/new", {
            "cwd": str(self.transport.cwd), "mcpServers": []}, jsonrpc=True)
        session_id = result.get("sessionId")
        if not session_id:
            raise AgentSessionError("ACP Agent did not return a session id")
        return str(session_id)

    def load_session(self, session_id: str) -> None:
        self.transport.request("session/load", {
            "sessionId": session_id, "cwd": str(self.transport.cwd),
            "mcpServers": []}, jsonrpc=True)

    def prompt(self, session_id: str, prompt: str) -> dict:
        result, events = self.transport.request("session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": prompt}],
        }, jsonrpc=True)
        permissions = [row for row in events
                       if row.get("method") == "session/request_permission"]
        return {"result": result, "events": events,
                "permission_requests": permissions}

    def cancel(self, session_id: str) -> None:
        self.transport.notify("session/cancel", {"sessionId": session_id})

    def close(self) -> None:
        self.transport.close()
