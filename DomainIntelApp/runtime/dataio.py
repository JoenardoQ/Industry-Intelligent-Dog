"""DomainIntelData 直连读写（纯标准库，不依赖 DomainIntelSearch 的 src）.

DomainIntelApp 只做 UI：读取 / 删除 DomainIntelData 里按行业分目录保存的数据。
本模块负责定位数据根、遍历行业、读取/删除定期条目与产物、读写控制开关。

数据根定位顺序：
  1. 环境变量 DOMAIN_INTEL_DATA_ROOT / INTDOG_DATA_ROOT
  2. 当前代码仓库内的 ../DomainIntelData

行业文件夹结构（由 DomainIntelSearch 写入）：
  <行业>/control.json                 定期开关
  <行业>/sources.json                 信息源
  <行业>/one_time/knowledge/*.json    三层知识（industry/chains/entities）
  <行业>/one_time/reports/*           行业报告 + tasks.json
  <行业>/periodic/daily/<日期>/<类别>.json
  <行业>/periodic/{weekly,monthly,quarterly}/*.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

_PROJECT_ROOT = Path(os.environ.get("INTDOG_PROJECT_ROOT") or
                     Path(__file__).resolve().parents[2]).resolve()
_SEARCH_ROOT = Path(os.environ.get("INTDOG_SEARCH_ROOT") or
                    _PROJECT_ROOT / "DomainIntelSearch").resolve()
if str(_SEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_SEARCH_ROOT))
from intdog_core import IntDogService  # noqa: E402
from intdog_core.models import validate_folder  # noqa: E402
from src.source_discovery import source_origin  # noqa: E402
from src.lab.artifacts import list_valid_bundles  # noqa: E402

DAILY_CATEGORIES = ("news", "github", "funding", "hiring", "ceo", "papers")
PERIOD_KINDS = ("weekly", "monthly", "quarterly")
INDUSTRY_REPORT_IDS = ("trend_5y", "popular_2y", "tech_6m")
# 非行业目录（扫描行业时跳过）
SKIP_DIRS = {"skill", "domains", "images", "_trash"}
SOURCE_CATEGORIES = ("official", "associations", "blogs", "platforms",
                     "self_media", "news", "journals", "financials", "finance")


def find_data_root() -> Path:
    env = os.environ.get("DOMAIN_INTEL_DATA_ROOT") or os.environ.get("INTDOG_DATA_ROOT")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve()
    return here.parents[2] / "DomainIntelData"


# ----------------------------------------------------------------------
# 基础 JSON 读写（原子写）
# ----------------------------------------------------------------------
def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return default


def write_json(path: Path, data):
    IntDogService.write_json(path, data)


@lru_cache(maxsize=8)
def _cached_service(root: str) -> IntDogService:
    service = IntDogService(root)
    service.migrate_legacy()
    service.reconcile_compat()
    return service


def _service(root: Path) -> IntDogService:
    return _cached_service(str(Path(root).resolve()))


# ----------------------------------------------------------------------
# 行业
# ----------------------------------------------------------------------
def list_industries(root: Path) -> list[dict]:
    """List active industries from the transactional registry."""
    rows = _service(root).repo.list_industries()
    return [{"folder": row["folder"], "name": row["name"],
             "periodic_enabled": read_control(root, row["folder"]).get(
                 "periodic_enabled", False)} for row in rows]


def create_industry(root: Path, folder: str, display_name: str = "") -> Path:
    return _service(root).create_industry(validate_folder(folder), display_name.strip())


def rename_industry(root: Path, old_folder: str, new_folder: str,
                    display_name: str = "") -> Path:
    return _service(root).rename_industry(
        validate_folder(old_folder), validate_folder(new_folder), display_name.strip())


def archive_industry(root: Path, folder: str) -> Path:
    return _service(root).archive_industry(validate_folder(folder))


def export_industry(root: Path, folder: str) -> dict:
    return _service(root).export_industry_bundle(validate_folder(folder))


def import_industry(root: Path, folder: str, name: str, bundle: dict) -> dict:
    return _service(root).import_industry_bundle(
        validate_folder(folder), name.strip(), bundle)


def list_trash(root: Path) -> list[dict]:
    return _service(root).list_trash()


def restore_trash(root: Path, item_id: str, desired_folder: str = "") -> dict:
    return _service(root).restore_trash(item_id, desired_folder=desired_folder)


def preview_trash_restore(root: Path, item_id: str) -> dict:
    return _service(root).preview_trash_restore(item_id)


def list_audits(root: Path, limit: int = 100) -> list[dict]:
    return _service(root).repo.list_audits(limit=limit)


def read_control(root: Path, folder: str) -> dict:
    return read_json(root / folder / "control.json", {"periodic_enabled": False})


def set_periodic(root: Path, folder: str, enabled: bool):
    _service(root).set_periodic(folder, enabled)


def update_control(root: Path, folder: str, changes: dict) -> dict:
    return _service(root).update_control(folder, changes)


# ----------------------------------------------------------------------
# 信息源
# ----------------------------------------------------------------------
def read_sources(root: Path, folder: str) -> dict:
    payload = {key: [] for key in SOURCE_CATEGORIES}
    for item in _service(root).repo.list_sources(folder):
        category = item["category"]
        payload.setdefault(category, []).append(item)
    metadata = read_json(root / folder / "one_time/knowledge/industry.json", {})
    payload["industry"] = metadata.get("name") or folder
    return payload


def add_source(root: Path, folder: str, category: str, source: dict) -> bool:
    return _service(root).add_source(folder, category, source)


def delete_source(root: Path, folder: str, category: str, url: str) -> bool:
    return _service(root).delete_source(folder, category, url)


def read_bootstrap_status(root: Path, folder: str) -> dict:
    """读取来源优先研究初始化状态；旧行业没有该文件时返回空对象。"""
    return read_json(root / folder / "bootstrap_status.json", {})


def read_core_status(root: Path, folder: str) -> dict:
    """Return compact structured-knowledge coverage for the app header."""
    return _service(root).repo.knowledge_stats(folder)


# ----------------------------------------------------------------------
# 每日定期条目
# ----------------------------------------------------------------------
def _key(item: dict) -> str:
    return (item.get("url") or item.get("title") or "")[:200]


def list_daily_dates(root: Path, folder: str) -> list[str]:
    return _service(root).repo.list_document_dates(folder)


def list_daily(root: Path, folder: str, date: str = None,
               category: str = None) -> list[dict]:
    if date is None:
        dates = list_daily_dates(root, folder)
        date = dates[0] if dates else None
    if not date:
        return []
    out = _service(root).repo.list_documents(folder, date=date, category=category)
    for item in out:
        item["_file"] = str(root / folder / "periodic/daily" / date /
                            f"{item['category']}.json")
        item["_cat"] = item["category"]
        item["_date"] = date
    return out


def page_daily(root: Path, folder: str, date: str = None,
               category: str = None, query: str = "", sort: str = "title",
               cursor: str = "", limit: int = 50) -> dict:
    if date is None:
        dates = list_daily_dates(root, folder)
        date = dates[0] if dates else None
    if not date:
        return {"items": [], "total": 0, "next_cursor": None}
    page = _service(root).repo.page_documents(
        folder, date=date, category=category, query=query, sort=sort,
        cursor=cursor, limit=limit)
    for item in page["items"]:
        item["_file"] = str(root / folder / "periodic/daily" / date /
                            f"{item['category']}.json")
        item["_cat"] = item["category"]
        item["_date"] = date
    return page


def delete_daily_item(root: Path, folder: str, date: str, category: str,
                      key: str) -> bool:
    return delete_daily_items(root, folder, [(date, category, key)]) > 0


def delete_daily_items(root: Path, folder: str,
                       identities: list[tuple[str, str, str]]) -> int:
    valid = [(date, category, key) for date, category, key in identities
             if category in DAILY_CATEGORIES and date]
    return _service(root).delete_daily(folder, valid)


# ----------------------------------------------------------------------
# 周/月/季产物
# ----------------------------------------------------------------------
def list_period(root: Path, folder: str, kind: str) -> list[dict]:
    d = root / folder / "periodic" / kind
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json"), reverse=True):
        it = read_json(f, {})
        if it:
            it["_file"] = str(f)
            it["_key"] = f.stem
            out.append(it)
    return out


def delete_period(root: Path, folder: str, kind: str, key: str) -> bool:
    return _service(root).delete_period(folder, kind, key)


# ----------------------------------------------------------------------
# 三层知识
# ----------------------------------------------------------------------
def read_knowledge(root: Path, folder: str) -> dict:
    kdir = root / folder / "one_time" / "knowledge"
    ind = read_json(kdir / "industry.json", {})
    service = _service(root)
    chains = service.repo.list_chain_nodes(folder)
    ents = service.repo.list_compat_entities(folder)
    for c in chains:
        c["entities"] = [e for e in ents if e.get("chain") == c.get("name")]
    return {"industry": ind, "chains": chains, "entities": ents}


def read_industry_knowledge(root: Path, folder: str) -> dict:
    return read_json(root / folder / "one_time" / "knowledge" / "industry.json", {})


def list_chain_knowledge(root: Path, folder: str) -> list[dict]:
    return _service(root).repo.list_chain_nodes(folder)


def list_chain_edges(root: Path, folder: str) -> list[dict]:
    return _service(root).repo.list_chain_edges(folder)


def delete_entity(root: Path, folder: str, entity_id: str) -> bool:
    return _service(root).delete_entity(folder, entity_id)


# ----------------------------------------------------------------------
# 行业报告（one_time/reports）
# ----------------------------------------------------------------------
def list_reports(root: Path, folder: str) -> list[dict]:
    """List the three user-facing industry reports in their stable product order.

    Deep-research products and bootstrap transcripts have separate readers and
    are deliberately not part of this index.
    """
    out = []
    industry = root / folder
    directory = industry / "one_time" / "reports"
    tasks = read_json(directory / "tasks.json", {})
    task_by_id = {
        str(item.get("id")): item
        for item in tasks.get("tasks", [])
        if isinstance(item, dict) and item.get("id")
    }
    for report_id in INDUSTRY_REPORT_IDS:
        path = next(
            (
                directory / f"{report_id}{suffix}"
                for suffix in (".md", ".html", ".txt")
                if (directory / f"{report_id}{suffix}").is_file()
            ),
            None,
        )
        if path is None:
            continue
        task = task_by_id.get(report_id, {})
        visualization = read_json(directory / f"{report_id}.viz.json", {})
        status = str(visualization.get("status") or task.get("status") or "draft")
        limitations = list(visualization.get("limitations") or task.get("limitations") or [])
        if status in {"draft", "draft_review_required"} and not limitations:
            limitations.append("待人工复核")
        out.append({
            "id": report_id,
            "name": path.relative_to(industry).as_posix(),
            "title": str(task.get("title") or report_id),
            "path": str(path),
            "size": path.stat().st_size,
            "provider": str(visualization.get("provider") or task.get("provider") or "N/A"),
            "model": str(visualization.get("model") or task.get("model") or "N/A"),
            "status": status,
            "limitations": limitations,
            "visualization": visualization if isinstance(visualization, dict) else {},
            "portable_file": visualization.get("portable_file"),
            "quality": visualization.get("quality", {}),
        })
    return out


def read_text(path: Path, limit: int = 200_000) -> str:
    try:
        t = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"读取失败: {e}"
    return t[:limit] + ("\n\n…（截断）" if len(t) > limit else "")


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)


def read_report_text(path: Path, limit: int = 200_000) -> str:
    """Render JSON and HTML reports as readable text instead of raw source."""
    path = Path(path)
    raw = read_text(path, limit)
    if raw.startswith("读取失败:"):
        return raw
    if path.suffix.lower() == ".json":
        try:
            return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return raw
    if path.suffix.lower() in {".html", ".htm"}:
        parser = _HTMLText()
        parser.feed(raw)
        return "\n\n".join(parser.parts)
    return raw


# ----------------------------------------------------------------------
# 竞争格局（one_time/landscape，DomainIntelSearch landscape 命令产出）
# ----------------------------------------------------------------------
def read_landscape(root: Path, folder: str) -> dict:
    """读取竞争格局最新结果 + 历史快照日期列表."""
    ldir = root / folder / "one_time" / "landscape"
    latest = read_json(ldir / "landscape.json", {})
    hdir = ldir / "history"
    history = []
    if hdir.exists():
        history = [f.stem for f in sorted(hdir.glob("*.json"))]
    return {"landscape": latest, "history": history}


def share_trend(root: Path, folder: str, company: str) -> list[dict]:
    """某公司在历史快照中的提及量序列（地位变化代理指标）."""
    hdir = root / folder / "one_time" / "landscape" / "history"
    out = []
    if not hdir.exists():
        return out
    for f in sorted(hdir.glob("*.json")):
        data = read_json(f, {})
        mentions = 0
        for tier in (data.get("tiers") or {}).values():
            for e in tier:
                if e.get("name") == company:
                    mentions = e.get("mentions", 0)
        out.append({"date": f.stem, "mentions": mentions})
    return out


# ----------------------------------------------------------------------
# 事件影响分析（one_time/impact，DomainIntelSearch impact 命令产出）
# ----------------------------------------------------------------------
def read_impact_events(root: Path, folder: str) -> dict:
    return read_json(root / folder / "one_time" / "impact" / "events.json",
                     {"events": []})


def list_impact_analyses(root: Path, folder: str) -> list[dict]:
    """列出已分析的事件（每个子目录一个）."""
    idir = root / folder / "one_time" / "impact"
    out = []
    if not idir.exists():
        return out
    for d in sorted(idir.iterdir()):
        if d.is_dir() and (d / "impact.json").exists():
            data = read_json(d / "impact.json", {})
            out.append({"slug": d.name,
                        "event": data.get("event", d.name),
                        "generated_at": data.get("generated_at", ""),
                        "companies": len(data.get("affected_companies", [])),
                        "chains": len(data.get("affected_chains", [])),
                        "papers": len(data.get("related_papers", [])),
                        "policies": len(data.get("related_policies", []))})
    return out


def read_impact(root: Path, folder: str, slug: str) -> dict:
    return read_json(root / folder / "one_time" / "impact" / slug / "impact.json", {})


def read_intelligence_lab(root: Path, folder: str) -> dict:
    """Read deterministic Intelligence Lab compatibility artifacts."""
    base = root / folder / "one_time" / "intelligence"
    scenarios = []
    bundle_dir = base / "artifacts" / "chain_scenario"
    if bundle_dir.exists():
        for item in list_valid_bundles(base, "chain_scenario"):
            item["_path"] = str(Path(item.pop("_bundle_path")) / "artifact.json")
            scenarios.append(item)
    else:
        scenario_dir = base / "scenarios"
        if scenario_dir.exists():
            for path in sorted(scenario_dir.glob("*.json"), reverse=True):
                item = read_json(path, {})
                if item:
                    item["_path"] = str(path)
                    scenarios.append(item)
    return {
        "evidence": read_json(base / "evidence_graph.json", {}),
        "sources": read_json(base / "source_observatory.json", {}),
        "agenda": read_json(base / "research_agenda.json", {}),
        "scenarios": scenarios,
    }


def list_research_agenda(root: Path, folder: str) -> list[dict]:
    return _service(root).repo.list_research_agenda(folder, include_closed=True)


def update_agenda_status(root: Path, folder: str, item_id: str, status: str) -> bool:
    return _service(root).update_research_agenda_status(folder, item_id, status)


def agenda_history(root: Path, folder: str, item_id: str) -> list[dict]:
    return _service(root).repo.list_research_agenda_history(folder, item_id)


def create_research_task(root: Path, folder: str, item_id: str,
                         budget: int = 20) -> dict:
    return _service(root).create_research_task(folder, item_id, budget)


def list_research_tasks(root: Path, folder: str, item_id: str = "") -> list[dict]:
    return _service(root).repo.list_research_tasks(folder, item_id)


# ----------------------------------------------------------------------
# 深度研究报告（one_time/reports/deep_tasks.json + deep/*.md）
# ----------------------------------------------------------------------
def read_deep_tasks(root: Path, folder: str) -> list[dict]:
    data = read_json(root / folder / "one_time" / "reports" / "deep_tasks.json", {})
    return data.get("tasks", [])


def list_deep_reports(root: Path, folder: str) -> list[dict]:
    """列出已回写完成的深度报告成品（deep/ 下的 .md）."""
    d = root / folder / "one_time" / "reports" / "deep"
    out = []
    if not d.exists():
        return out
    for f in sorted(d.glob("*.md")):
        metadata = read_json(f.with_suffix(".viz.json"), {})
        out.append({"name": f.name, "path": str(f), "size": f.stat().st_size,
                    "title": metadata.get("title") or f.stem,
                    "status": metadata.get("status") or "draft_review_required",
                    "provider": metadata.get("provider") or "N/A",
                    "model": metadata.get("model") or "N/A",
                    "limitations": metadata.get("limitations") or [],
                    "references": metadata.get("references") or [],
                    "portable_file": metadata.get("portable_file"),
                    "quality": metadata.get("quality") or {},
                    "visualization": metadata})
    return out
