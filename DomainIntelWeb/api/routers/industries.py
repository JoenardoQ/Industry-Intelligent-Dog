from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException

from ..schemas import (ArchiveState, IndustryCreate, IndustryMutationState,
                       IndustryRename, IndustryState, OverviewState)


def build_industries_router(*, data_root: Path, dataio,
                            resolve_folder: Callable[[str], str]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["industries"])

    @router.get("/industries", response_model=list[IndustryState])
    def industries() -> list[dict]:
        return dataio.list_industries(data_root)

    @router.post("/industries", status_code=201, response_model=IndustryMutationState)
    def create_industry(request: IndustryCreate) -> dict:
        try:
            path = dataio.create_industry(data_root, request.folder, request.name)
        except (ValueError, FileExistsError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"folder": path.name, "name": request.name or path.name}

    @router.patch("/industries/{folder}", response_model=IndustryMutationState)
    def rename_industry(folder: str, request: IndustryRename) -> dict:
        folder = resolve_folder(folder)
        try:
            path = dataio.rename_industry(
                data_root, folder, request.folder, request.name)
        except (ValueError, FileExistsError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"folder": path.name, "name": request.name or path.name}

    @router.delete("/industries/{folder}", response_model=ArchiveState)
    def archive_industry(folder: str) -> dict:
        return {"archived_to": str(dataio.archive_industry(
            data_root, resolve_folder(folder)))}

    @router.get("/industries/{folder}/overview", response_model=OverviewState)
    def overview(folder: str) -> dict:
        folder = resolve_folder(folder)
        industry = dataio.read_industry_knowledge(data_root, folder)
        chains = dataio.list_chain_knowledge(data_root, folder)
        sources = dataio.read_sources(data_root, folder)
        stats = dataio.read_core_status(data_root, folder)
        dates = dataio.list_daily_dates(data_root, folder)
        return {
            "industry": industry, "stats": stats,
            "chain": chains, "entities": [],
            "source_categories": {category: len(items) for category, items in sources.items()
                                  if isinstance(items, list)},
            "latest_document_date": dates[0] if dates else None,
        }

    return router
