import io
import json
import pytest

from src.services.agent_sessions import AcpSession, AgentSessionError, CodexAppServerSession


class _Input:
    def __init__(self, rows):
        self.rows = iter(json.dumps(row) + "\n" for row in rows)

    def readline(self):
        return next(self.rows, "")


class _Output(io.StringIO):
    def flush(self):
        return None


class _Process:
    def __init__(self, rows):
        self.stdin = _Output()
        self.stdout = _Input(rows)
        self.stderr = io.StringIO()

    def poll(self):
        return None

    def terminate(self):
        return None


def _sent(process):
    return [json.loads(line) for line in process.stdin.getvalue().splitlines()]


def test_codex_app_server_handshake_precedes_thread_and_turn():
    process = _Process([
        {"id": 1, "result": {"serverInfo": {"name": "codex"}}},
        {"id": 2, "result": {"thread": {"id": "thread-1"}}},
        {"method": "item/agentMessage/delta", "params": {"delta": "hello"}},
        {"id": 3, "result": {"turn": {"id": "turn-1"}}},
        {"method": "item/agentMessage/delta", "params": {"delta": " world"}},
        {"method": "turn/completed", "params": {"turn": {"id": "turn-1"}}},
    ])
    session = CodexAppServerSession(
        "/tools/codex", "/work", process_factory=lambda *_a, **_k: process)
    session.start()
    thread_id = session.start_thread()
    turn = session.start_turn(thread_id, "research this")
    sent = _sent(process)
    assert [row.get("method") for row in sent] == [
        "initialize", "initialized", "thread/start", "turn/start"]
    assert thread_id == "thread-1"
    assert turn["turn_id"] == "turn-1"
    assert [row["method"] for row in turn["events"]] == [
        "item/agentMessage/delta", "item/agentMessage/delta", "turn/completed"]


def test_acp_session_negotiates_before_new_session_and_never_auto_approves():
    process = _Process([
        {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": 1}},
        {"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "acp-1"}},
        {"jsonrpc": "2.0", "method": "session/request_permission",
         "params": {"sessionId": "acp-1", "options": [{"optionId": "allow"}]}},
        {"jsonrpc": "2.0", "id": 3, "result": {"stopReason": "end_turn"}},
    ])
    session = AcpSession(
        "/tools/kimi", ("acp",), "/work", process_factory=lambda *_a, **_k: process)
    session.start()
    session_id = session.new_session()
    with pytest.raises(AgentSessionError, match="permission"):
        session.prompt(session_id, "hello")
    sent = _sent(process)
    assert [row.get("method") for row in sent] == [
        "initialize", "session/new", "session/prompt"]
    assert not any(row.get("method") == "session/permission_response" for row in sent)
