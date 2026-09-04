from intdog_core.repository import IntelligenceRepository
from src.services import conversation_broker
from src.services.agent_sessions import AgentSessionError
from src.services.conversation_broker import ConversationBroker, NativeSessionRunner


class _TextResult:
    text = "CLI fallback response"


def test_broker_persists_text_and_validated_proposal_without_executing(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("ai", "AI")
    calls = []

    def runner(provider, workspace, prompt, external_session_id):
        calls.append((provider, workspace, prompt, external_session_id))
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
