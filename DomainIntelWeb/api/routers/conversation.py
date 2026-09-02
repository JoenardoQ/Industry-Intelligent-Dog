"""Industry-scoped Agent conversation and review-gated execution routes."""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from ..schemas import (ConfirmedProposalState, ConversationState,
                       ConversationTurnRequest, GenerateRequest,
                       ProposalDecisionRequest, ActionProposalState)


def build_conversation_router(*, broker, repo,
                              resolve_folder: Callable[[str], str],
                              generate: Callable) -> APIRouter:
    from src.services.capability_manifest import capability

    router = APIRouter(prefix="/api/industries/{folder}/conversation",
                       tags=["conversation"])

    def checked_provider(provider: str) -> str:
        value = str(provider or "").strip().casefold()
        spec = capability(value)
        if spec is None or spec.kind not in {"agent", "api"}:
            raise HTTPException(400, "未知 Agent 或 API Provider")
        return value

    @router.get("", response_model=ConversationState)
    def conversation(folder: str, provider: str = Query(min_length=1, max_length=80)):
        folder = resolve_folder(folder)
        try:
            return broker.state(folder, checked_provider(provider))
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/turn", response_model=ConversationState)
    def turn(folder: str, request: ConversationTurnRequest):
        folder = resolve_folder(folder)
        try:
            return broker.chat(folder, checked_provider(request.provider), request.message)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(409, f"Agent 对话失败：{exc}") from exc

    @router.post("/proposals/{proposal_id}/confirm", status_code=202,
                 response_model=ConfirmedProposalState)
    def confirm(folder: str, proposal_id: str,
                request: ProposalDecisionRequest):
        folder = resolve_folder(folder)
        confirmed = False
        try:
            proposal = repo.confirm_action_proposal(
                folder, proposal_id, request.revision)
            confirmed = True
            payload = dict(proposal["payload"])
            payload.pop("summary", None)
            operation = GenerateRequest.model_validate({
                **payload, "action": proposal["action"]})
            job = generate(folder, operation)
            proposal = repo.finish_action_proposal(
                proposal_id, task_run_id=str(job["run_id"]))
            return {"proposal": proposal, "job": job}
        except (ValueError, FileNotFoundError) as exc:
            if confirmed:
                try:
                    repo.finish_action_proposal(proposal_id, error=str(exc))
                except (ValueError, FileNotFoundError):
                    pass
            raise HTTPException(409, str(exc)) from exc
        except HTTPException as exc:
            try:
                repo.finish_action_proposal(proposal_id, error=str(exc.detail))
            except (ValueError, FileNotFoundError):
                pass
            raise
        except Exception as exc:
            try:
                repo.finish_action_proposal(proposal_id, error=str(exc))
            except (ValueError, FileNotFoundError):
                pass
            raise HTTPException(409, f"任务未能入队：{exc}") from exc

    @router.post("/proposals/{proposal_id}/reject",
                 response_model=ActionProposalState)
    def reject(folder: str, proposal_id: str,
               request: ProposalDecisionRequest):
        folder = resolve_folder(folder)
        try:
            return repo.reject_action_proposal(folder, proposal_id, request.revision)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
