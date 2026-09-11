from intdog_core.repository import IntelligenceRepository
from src.services import conversation_broker
from src.services.agent_sessions import AgentSessionError
from src.services.conversation_broker import ConversationBroker, NativeSessionRunner
import pytest


class _TextResult:
    text = "CLI fallback response"


@pytest.mark.parametrize("provider", ["codex", "opencode"])
def test_native_turns_use_delta_but_fallback_keeps_history(tmp_path, monkeypatch, provider):
    sent = []
    class Session:
        def __init__(self, *_args): pass
        def start(self): pass
        def start_thread(self): return "thread-1"
        new_session = start_thread
        def resume_thread(self, session_id): assert session_id == "thread-1"
        load_session = resume_thread
        def start_turn(self, session_id, prompt):
            sent.append(prompt)
            if prompt == "delta-fail":
                raise AgentSessionError("transport failed")
            return {"result": {"text": "answer"}}
        prompt = start_turn
        def close(self): pass
    monkeypatch.setattr(conversation_broker, "CodexAppServerSession", Session)
    monkeypatch.setattr(conversation_broker, "AcpSession", Session)
    monkeypatch.setattr("src.services.provider_readiness.session_readiness",
                        lambda *_args: {"ready": True, "executable": "/tools/agent"})
    # Exercise both real transport branches with the same direct fallback contract.
    from types import SimpleNamespace
    monkeypatch.setattr(conversation_broker, "capability_or_unknown", lambda _provider: SimpleNamespace(
        native_session_implemented=True, native_args=(), name=provider,
        session_protocol="codex_app_server" if provider == "codex" else "acp",
        execution_level="direct", fallbacks=("cli",)))
    class Cli:
        def complete(self, prompt):
            sent.append(prompt)
            return _TextResult()
    monkeypatch.setattr("src.services.provider_factory.create_provider", lambda *_args: Cli())
    runner = NativeSessionRunner()
    runner(provider, tmp_path, "full-first", "", "delta-first")
    runner(provider, tmp_path, "full-second", "thread-1", "delta-second")
    runner.close()
    runner(provider, tmp_path, "full-resume", "thread-1", "delta-resume")
    result = runner(provider, tmp_path, "full-fail", "thread-1", "delta-fail")
    assert sent == ["full-first", "delta-second", "delta-resume", "delta-fail", "full-fail"]
    assert result["connection"] == "cli_fallback"


def test_broker_persists_text_and_validated_proposal_without_executing(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("ai", "AI")
    calls = []

    def runner(provider, workspace, prompt, external_session_id, continuation_prompt):
        calls.append((provider, workspace, prompt, external_session_id, continuation_prompt))
        return {
            "text": "I can prepare it.\n```intdog-action\n"
                    '{"action":"daily","parameters":{},"summary":"Collect daily signals"}'
                    "\n```",
            "connection": "cli", "external_session_id": "session-1"}

    broker = ConversationBroker(repo, tmp_path, runner=runner)
    state = broker.chat("ai", "codex", "collect today's news")
    assert state["messages"][-1]["content"] == "I can prepare it."
    assert state["proposals"][0]["action"] == "daily"
    assert state["proposals"][0]["status"] == "pending"
    assert state["proposals"][0]["payload"]["provider"] == "codex"
    assert calls and "Artificial" not in calls[0][2]
    assert repo.list_tasks("ai") == []
    broker.chat("ai", "codex", "explain the sources")
    assert "collect today's news" in calls[-1][2]
    assert "collect today's news" not in calls[-1][4]
    assert "explain the sources" in calls[-1][4]


def test_broker_rejects_unallowlisted_or_malformed_action_blocks(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("ai", "AI")
    responses = iter([
        {"text": '```intdog-action\n{"action":"delete_industry","parameters":{}}\n```',
         "connection": "api"},
        {"text": '```intdog-action\nnot-json\n```', "connection": "api"},
    ])
    broker = ConversationBroker(repo, tmp_path, runner=lambda *_a: next(responses))
    first = broker.chat("ai", "openai", "delete")
    second = broker.chat("ai", "openai", "again")
    assert first["proposals"] == []
    assert second["proposals"] == []


def test_codex_native_failure_retries_same_agent_cli_and_evicts_session(
        tmp_path, monkeypatch):
    sessions = []
    provider_names = []

    class BrokenCodexSession:
        def __init__(self, executable, workspace):
            self.closed = False
            sessions.append(self)

        def start(self):
            raise AgentSessionError("app-server handshake failed")

        def close(self):
            self.closed = True

    class SameAgentCli:
        def complete(self, prompt):
            return _TextResult()

    monkeypatch.setattr(conversation_broker, "CodexAppServerSession", BrokenCodexSession)
    monkeypatch.setattr(
        "src.services.provider_readiness.session_readiness",
        lambda *_args: {"ready": True, "resolved_executable": "/tools/codex"})

    def create_provider(_config, provider, _workspace):
        provider_names.append(provider)
        return SameAgentCli()

    monkeypatch.setattr("src.services.provider_factory.create_provider", create_provider)
    runner = NativeSessionRunner()

    first = runner("codex", tmp_path, "hello", "thread-old")
    second = runner("codex", tmp_path, "again", "thread-old")

    assert first["text"] == "CLI fallback response"
    assert first["connection"] == "cli_fallback"
    assert first["external_session_id"] == ""
    assert first["connection_warning"] == (
        "Codex App Server 连接失败（AgentSessionError），已改用同一 Codex CLI。")
    assert second["connection"] == "cli_fallback"
    assert provider_names == ["codex", "codex"]
    assert len(sessions) == 2
    assert all(session.closed for session in sessions)


def test_broker_persists_visible_connection_downgrade(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("ai", "AI")
    broker = ConversationBroker(repo, tmp_path, runner=lambda *_args: {
        "text": "fallback answer", "connection": "cli_fallback",
        "external_session_id": "", "connection_warning": "native failed",
    })

    state = broker.chat("ai", "codex", "hello")

    assert state["connection"] == "cli_fallback"
    assert state["connection_warning"] == "native failed"
    assert state["messages"][-1]["metadata"] == {
        "connection": "cli_fallback", "connection_warning": "native failed"}


def test_conversation_turns_are_serial_but_other_industries_remain_independent(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    repo = IntelligenceRepository(tmp_path)
    for folder in ("ai", "chips"):
        repo.ensure_industry(folder, folder)
    first_entered, release_first = Event(), Event()
    second_attempted, second_entered = Event(), Event()
    prompts = []
    def runner(_provider, workspace, prompt, _session, delta):
        prompts.append((workspace.name, prompt, delta))
        if "user: first" in delta:
            first_entered.set()
            assert release_first.wait(timeout=3)
        if "user: second" in delta:
            second_entered.set()
            raise RuntimeError("synthetic failure")
        return {"text": "answer-" + delta.rsplit("user: ", 1)[-1],
                "external_session_id": ""}
    broker = ConversationBroker(repo, tmp_path, runner=runner)
    def second():
        second_attempted.set()
        return broker.chat("ai", "codex", "second")
    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(broker.chat, "ai", "codex", "first")
        assert first_entered.wait(timeout=3)
        next_turn = executor.submit(second)
        try:
            assert second_attempted.wait(timeout=3)
            other = executor.submit(broker.chat, "chips", "codex", "parallel")
            assert other.result(timeout=3)["messages"][-1]["content"] == "answer-parallel"
            assert not second_entered.wait(timeout=0.1)
        finally:
            release_first.set()
        first.result(timeout=3)
        with pytest.raises(RuntimeError, match="synthetic failure"):
            next_turn.result(timeout=3)
    recovered = broker.chat("ai", "codex", "third")
    assert [row["content"] for row in recovered["messages"]] == [
        "first", "answer-first", "second", "third", "answer-third"]
    second_prompt = next(item for item in prompts if "user: second" in item[2])
    assert "assistant: answer-first" in second_prompt[1]
    assert "user: first" not in second_prompt[2]
