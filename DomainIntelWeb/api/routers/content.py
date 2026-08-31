from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter

from ..schemas import ProductsState, ResearchState


def build_content_router(*, data_root: Path, dataio,
                         resolve_folder: Callable[[str], str]) -> APIRouter:
    router = APIRouter(prefix="/api/industries/{folder}", tags=["content"])

    def impact_products(folder: str) -> list[dict]:
        rows = dataio.list_impact_analyses(data_root, folder)
        for row in rows:
            base = data_root / folder / "one_time" / "impact" / row["slug"]
            document = base / "analysis.md"
            if not document.is_file():
                document = base / "impact.json"
            detail = dataio.read_impact(data_root, folder, row["slug"])
            row.update({
                "id": f"impact:{row['slug']}",
                "title": row.get("event") or row["slug"],
                "path": str(document),
                "status": detail.get("status", "draft_review_required"),
                "provider": detail.get("provider", "N/A"),
                "model": detail.get("model", "N/A"),
                "summary": detail.get("summary", ""),
                "limitations": detail.get("limitations", ["待人工复核"]),
                "references": detail.get("references", []),
                "visualization": detail.get("visualization", {}),
            })
        return rows

    @router.get("/products", response_model=ProductsState)
    def products(folder: str) -> dict:
        folder = resolve_folder(folder)
        return {
            "periodic": {kind: dataio.list_period(data_root, folder, kind)
                         for kind in dataio.PERIOD_KINDS},
            "reports": dataio.list_reports(data_root, folder),
            "deep_reports": dataio.list_deep_reports(data_root, folder),
            "impacts": impact_products(folder),
        }

    @router.get("/research", response_model=ResearchState)
    def research(folder: str) -> dict:
        folder = resolve_folder(folder)
        return {
            "lab": dataio.read_intelligence_lab(data_root, folder),
            "agenda": dataio.list_research_agenda(data_root, folder),
            "tasks": dataio.list_research_tasks(data_root, folder),
            "impacts": impact_products(folder),
        }

    return router
