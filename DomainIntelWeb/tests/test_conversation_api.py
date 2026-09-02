from fastapi import HTTPException

from DomainIntelWeb.api.routers.conversation import build_conversation_router
from DomainIntelWeb.api.schemas import ConversationTurnRequest, ProposalDecisionRequest
from src.services.conversation_broker import ConversationBroker
from intdog_core.repository import IntelligenceRepository


def test_conversation_requires_explicit_proposal_confirmation_before_enqueue(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("ai", "AI")
    response = {
        "text": "Ready.\n```intdog-action\n"
                '{"action":"daily","parameters":{},"summary":"Daily scan"}\n```',
        "connection": "cli",
    }
    broker = ConversationBroker(repo, tmp_path, runner=lambda *_a: response)
    enqueued = []

    def generate(folder, request):
        enqueued.append((folder, request.action))
        task = repo.create_task(folder=folder, operation=request.action,
                                input={}, origin="app", provider="codex")
        return {"run_id": task["id"], "status": "queued",
                "title": "Daily", "action": request.action}

    router = build_conversation_router(
        broker=broker, repo=repo, resolve_folder=lambda value: value,
        generate=generate)
    endpoints = {route.path: route.endpoint for route in router.routes}
    turn = endpoints["/api/industries/{folder}/conversation/turn"](
        "ai", ConversationTurnRequest(provider="codex", message="scan today"))
    proposal = turn["proposals"][0]
    assert enqueued == []
    request = ProposalDecisionRequest(revision=proposal["revision"])
    confirm = endpoints["/api/industries/{folder}/conversation/proposals/{proposal_id}/confirm"]
    confirmed = confirm("ai", proposal["id"], request)
    assert confirmed["job"]["run_id"].startswith("task_")
    assert enqueued == [("ai", "daily")]
    try:
        confirm("ai", proposal["id"], request)
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("confirmed proposal must not be replayed")


def test_conversation_route_rejects_unknown_provider(tmp_path):
    repo = IntelligenceRepository(tmp_path)
    repo.ensure_industry("ai", "AI")
    broker = ConversationBroker(repo, tmp_path, runner=lambda *_a: {"text": "x"})
    router = build_conversation_router(
        broker=broker, repo=repo, resolve_folder=lambda value: value,
        generate=lambda *_a: {})
    endpoint = next(route.endpoint for route in router.routes if route.path.endswith("conversation"))
    try:
        endpoint("ai", "made-up-agent")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("unknown provider must be rejected")
