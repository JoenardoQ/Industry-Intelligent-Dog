"""Legacy command adapter to canonical storage; no second database or index."""

import json
from datetime import date as calendar_date
from pathlib import Path

from ..agents.base import AgentContext
from ..industry_store import IndustryStore


class ArchiveStore:
    def __init__(self, config: dict):
        context = AgentContext.from_config(config)
        self.root = context.data_root
        self.store = IndustryStore(self.root, context.industry_root.name, context.industry)

    def save_articles(self, articles, category: str = None, date: str = None) -> dict:
        groups: dict[str, list[dict]] = {}
        for article in articles:
            item = dict(article) if isinstance(article, dict) else article.to_dict()
            kind = category or item.get("category") or "news"
            kind = {"general": "news", "academic": "papers", "startup": "funding"}.get(kind, kind)
            groups.setdefault(kind, []).append(item)
        observed = date or calendar_date.today().isoformat()
        return {kind: {"count": self.store.service.import_daily(
            self.store.folder, kind, observed, items)} for kind, items in groups.items()}

    def save_report(self, report_type: str, src_path, date: str = None) -> str:
        source = Path(src_path)
        if report_type not in {"daily", "weekly", "timeline", "brief"}:
            raise ValueError(f"unsupported archive report type: {report_type}")
        target = (self.store.periodic / report_type if report_type in {"daily", "weekly"}
                  else self.store.reports) / source.name
        if source.resolve() != target.resolve():
            self.store.service.write_text(target, source.read_text(encoding="utf-8"))
        elif not source.is_file():
            raise FileNotFoundError(source)
        return str(target)

    def migrate_existing(self, project_dir) -> dict:
        """Explicitly import old outputs without removing or overwriting originals."""
        project = Path(project_dir)
        counts = {"reports": 0, "raw": 0}
        for source in sorted((project / "output").glob("*")):
            if not source.is_file() or source.suffix not in {".html", ".json", ".md"}:
                continue
            kind = next((kind for prefix, kind in (("daily", "daily"), ("weekly", "weekly"),
                ("timeline", "timeline"), ("research_brief", "brief")) if source.name.startswith(prefix)), None)
            if kind is None:
                continue
            self.save_report(kind, source)
            counts["reports"] += 1
        raw = project / "data" / "raw_collect.json"
        if raw.exists():
            payload = json.loads(raw.read_text(encoding="utf-8"))
            for category in ("news", "academic"):
                items = payload.get(category, [])
                self.save_articles(items, category)
                counts["raw"] += len(items)
        return counts

    def stats(self) -> dict:
        repo = self.store.service.repo
        iid = repo.industry_id(self.store.folder)
        with repo.connection() as con:
            rows = con.execute("""SELECT category,COUNT(*),MIN(observed_date),MAX(observed_date)
                FROM industry_documents WHERE industry_id=? AND deleted_at IS NULL
                GROUP BY category""", (iid,)).fetchall()
        return {"total": sum(row[1] for row in rows), "by_category": {row[0]: row[1] for row in rows},
                "date_range": [min(row[2] for row in rows), max(row[3] for row in rows)] if rows else [None, None],
                "root": str(self.root)}
