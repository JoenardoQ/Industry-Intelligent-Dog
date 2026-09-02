from datetime import datetime, timedelta, timezone

import pytest

from intdog_core.repository import IntelligenceRepository


def _repo(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("ai", "Artificial Intelligence")
    repo.ensure_industry("chips", "Chips")
    return repo


def test_conversations_and_messages_are_isolated_by_industry(tmp_path):
    repo = _repo(tmp_path)
    ai = repo.get_or_create_conversation("ai", "codex")
    chips = repo.get_or_create_conversation("chips", "codex")
    repo.append_conversation_message(ai["id"], "user", "AI question")
    repo.append_conversation_message(chips["id"], "user", "chip question")
    assert [row["content"] for row in repo.list_conversation_messages(ai["id"])] == [
        "AI question"]
    assert [row["content"] for row in repo.list_conversation_messages(chips["id"])] == [
        "chip question"]


def test_proposal_confirmation_is_industry_revision_and_replay_bound(tmp_path):
    repo = _repo(tmp_path)
    conversation = repo.get_or_create_conversation("ai", "codex")
    proposal = repo.create_action_proposal(
        conversation["id"], "daily", {"provider": "codex"})
    with pytest.raises(ValueError, match="industry"):
        repo.confirm_action_proposal("chips", proposal["id"], proposal["revision"])
    with pytest.raises(ValueError, match="revision"):
        repo.confirm_action_proposal("ai", proposal["id"], proposal["revision"] + 1)
    confirmed = repo.confirm_action_proposal(
        "ai", proposal["id"], proposal["revision"])
    assert confirmed["status"] == "confirmed"
    with pytest.raises(ValueError, match="pending"):
        repo.confirm_action_proposal("ai", proposal["id"], proposal["revision"])


def test_expired_proposal_cannot_be_confirmed(tmp_path):
    repo = _repo(tmp_path)
    conversation = repo.get_or_create_conversation("ai", "codex")
    proposal = repo.create_action_proposal(
        conversation["id"], "report", {"kind": "overview"})
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with repo.transaction() as con:
        con.execute("UPDATE action_proposals SET expires_at=? WHERE id=?",
                    (expired, proposal["id"]))
    with pytest.raises(ValueError, match="expired"):
        repo.confirm_action_proposal("ai", proposal["id"], proposal["revision"])
