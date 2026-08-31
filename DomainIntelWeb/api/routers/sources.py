from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException

from ..schemas import CountState, SourceCreate, SourceMutationState, SourcesState


def build_sources_router(*, data_root: Path, dataio,
                         resolve_folder: Callable[[str], str]) -> APIRouter:
    router = APIRouter(prefix="/api/industries/{folder}", tags=["sources"])

    @router.get("/sources", response_model=SourcesState)
    def sources(folder: str) -> dict:
        folder = resolve_folder(folder)
        payload = dataio.read_sources(data_root, folder)
        return {"industry": payload.pop("industry", folder), "categories": payload}

    @router.post("/sources", status_code=201, response_model=SourceMutationState)
    def add_source(folder: str, request: SourceCreate) -> dict:
        folder = resolve_folder(folder)
        if request.category not in dataio.SOURCE_CATEGORIES:
            raise HTTPException(400, "未知信息源类别")
        return {"added": dataio.add_source(
            data_root, folder, request.category, request.model_dump())}

    @router.delete("/sources", response_model=CountState)
    def remove_source(folder: str, category: str, url: str) -> dict:
        folder = resolve_folder(folder)
        if category not in dataio.SOURCE_CATEGORIES:
            raise HTTPException(400, "未知信息源类别")
        return {"deleted": dataio.delete_source(data_root, folder, category, url)}

    return router
