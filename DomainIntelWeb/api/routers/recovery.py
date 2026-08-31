from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas import (AuditState, RestorePreviewState, RestoreState,
                       TrashRestoreRequest, TrashState)


def build_recovery_router(*, data_root: Path, dataio) -> APIRouter:
    router = APIRouter(prefix="/api/trash", tags=["recovery"])

    @router.get("", response_model=TrashState)
    def trash() -> dict:
        items = dataio.list_trash(data_root)
        return {"items": items, "total": len(items),
                "permanent_delete_available": False}

    @router.post("/{item_id}/restore", response_model=RestoreState)
    def restore(item_id: str, request: TrashRestoreRequest) -> dict:
        try:
            return dataio.restore_trash(
                data_root, item_id, request.desired_folder.strip())
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (FileExistsError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/{item_id}/preview", response_model=RestorePreviewState)
    def preview(item_id: str) -> dict:
        try:
            return dataio.preview_trash_restore(data_root, item_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/audits/recent", response_model=list[AuditState])
    def audits() -> list[dict]:
        return dataio.list_audits(data_root, limit=100)

    return router
