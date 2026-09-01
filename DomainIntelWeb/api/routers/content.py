from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter

from ..schemas import PortableExportState, ProductsState, ResearchState


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
                "portable_file": detail.get("portable_file"),
                "quality_file": detail.get("quality_file"),
                "manifest_file": detail.get("manifest_file"),
                "quality": detail.get("quality", {}),
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

    @router.post("/portable/daily", response_model=PortableExportState)
    def portable_daily(folder: str) -> dict:
        from datetime import datetime
        from src.artifact_quality import evaluate_artifact
        from src.portable_briefing import build_manifest, write_portable_html

        folder = resolve_folder(folder)
        rows = dataio.list_daily(data_root, folder)
        generated = datetime.now().isoformat(timespec="seconds")
        lines = [f"# {folder} 每日情报", "", f"生成时间：{generated}", ""]
        references = []
        for item in rows:
            title = str(item.get("title") or "未命名情报")
            url = str(item.get("url") or "")
            source = str(item.get("display_source") or item.get("source") or "来源待识别")
            date = str(item.get("published_at") or item.get("date") or "日期待核验")
            abstract = str(item.get("abstract") or "暂无具体摘要")
            lines.extend([f"## {date[:10]} · {title}", "", f"{abstract} [{source}]({url})", ""])
            if url:
                references.append({"title": source, "url": url})
        markdown = "\n".join(lines)
        metadata = {"title": f"{folder} 每日情报", "generated_at": generated,
                    "status": "draft_review_required", "source": "IntDog Daily",
                    "references": references,
                    "items": [{"id": item.get("id"), "title": item.get("title"),
                               "abstract": item.get("abstract"),
                               "published_at": item.get("published_at") or item.get("date"),
                               "source": item.get("display_source") or item.get("source"),
                               "status": item.get("status") or "unreviewed",
                               "chain_stage": item.get("chain_stage") or "未分类",
                               "url": item.get("url")} for item in rows]}
        quality = evaluate_artifact(markdown, metadata)
        metadata.update({"quality": quality, "artifact_status": quality["artifact_status"]})
        base = data_root / folder / "periodic" / "daily" / f"portable-{generated[:10]}"
        base.parent.mkdir(parents=True, exist_ok=True)
        manifest = build_manifest(markdown, metadata)
        dataio.write_json(base.with_suffix(".manifest.json"), manifest)
        dataio.write_json(base.with_suffix(".quality.json"), quality)
        temp = base.with_suffix(".md.tmp")
        temp.write_text(markdown + "\n", encoding="utf-8")
        temp.replace(base.with_suffix(".md"))
        path = write_portable_html(base.with_suffix(".html"), manifest)
        return {"path": str(path), "status": quality["artifact_status"], "quality": quality}

    return router
