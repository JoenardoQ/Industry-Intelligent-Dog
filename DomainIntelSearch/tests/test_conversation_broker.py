from intdog_core.repository import IntelligenceRepository
from src.services.conversation_broker import ConversationBroker


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
