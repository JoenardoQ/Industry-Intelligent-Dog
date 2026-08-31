"""按行业分目录的存储管理（IndustryStore）.

每个行业在 DomainIntelData 下有独立文件夹，一次性深度爬取与定期监控分开：

    DomainIntelData/
    └── <行业文件夹>/                  # 例：AI、Chips
        ├── control.json               # 定期更新开关 + 调度设置
        ├── sources.json               # 信息源发现结果（先爬"该看谁"）
        ├── one_time/                  # 一次性深度爬取
        │   ├── knowledge/             #   三层知识结构（行业→产业链→实体）
        │   │   ├── industry.json
        │   │   ├── chains.json
        │   │   └── entities.json
        │   └── reports/               #   5年/2年/半年 行业报告
        └── periodic/                  # 定期监控（与一次性分开）
            ├── daily/<YYYY-MM-DD>/<类别>.json
            ├── weekly/<YYYY>-W<ww>.json
            ├── monthly/<YYYY>-<MM>.json
            └── quarterly/<YYYY>-Q<q>.json

定期类别（daily）：news / github / funding / hiring / ceo / papers
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from intdog_core import IntDogService, stable_id
from .deduplication import (collapse_batch, content_fingerprint, plan_history,
                            suppress_replays)
from .source_governance import govern_sources

DAILY_CATEGORIES = ("news", "github", "funding", "hiring", "ceo", "papers")
PERIOD_KINDS = ("daily", "weekly", "monthly", "quarterly")

DEFAULT_CONTROL = {
    "periodic_enabled": False,
    "daily_time": "08:00",
    "weekly_day": "monday",
    "monthly_day": 1,
    "quarterly_months": [1, 4, 7, 10],
    "last_run": {},
    "job_status": {},
    "note": "periodic_enabled=true 时定期更新；各周期产物存于 periodic/",
}


class IndustryStore:
    """单个行业的数据存储（读写 DomainIntelData/<行业>/）."""

    def __init__(self, data_root: str | Path, folder: str, name: str = ""):
        self.data_root = Path(data_root)
        self.folder = folder
        self.name = name or folder
        self.root = self.data_root / folder
        self.one_time = self.root / "one_time"
        self.knowledge = self.one_time / "knowledge"
        self.reports = self.one_time / "reports"
        self.tasks = self.one_time / "tasks"
        self.periodic = self.root / "periodic"
        self._ensure()
        self.service = IntDogService(self.data_root)
        self.service.repo.ensure_industry(self.folder, self.name)
        self.service.migrate_legacy([self.folder])
        self.service.reconcile_compat([self.folder])

    def _ensure(self):
        for d in (self.knowledge, self.reports, self.tasks, self.periodic):
            d.mkdir(parents=True, exist_ok=True)
        for k in PERIOD_KINDS:
            (self.periodic / k).mkdir(parents=True, exist_ok=True)
        if not self.control_path.exists():
            self._write_json(self.control_path, DEFAULT_CONTROL)

    # ------------------------------------------------------------------
    # 基础路径
    # ------------------------------------------------------------------
    @property
    def control_path(self) -> Path:
        return self.root / "control.json"

    @property
    def sources_path(self) -> Path:
        return self.root / "sources.json"

    # ------------------------------------------------------------------
    # control.json（定期开关）
    # ------------------------------------------------------------------
    def get_control(self) -> dict:
        return self._read_json(self.control_path, dict(DEFAULT_CONTROL))

    def set_periodic_enabled(self, enabled: bool) -> dict:
        return self.service.update_control(
            self.folder, {"periodic_enabled": bool(enabled)})

    def update_control(self, **changes) -> dict:
        """Atomically merge scheduler state into ``control.json``."""
        return self.service.update_control(self.folder, changes)

    # ------------------------------------------------------------------
    # sources.json（信息源）
    # ------------------------------------------------------------------
    def get_sources(self) -> dict:
        payload = self._read_json(self.sources_path, {})
        rows = self.service.repo.list_sources(self.folder)
        if rows:
            for category in ("official", "associations", "blogs", "platforms",
                             "self_media", "news", "journals", "financials", "finance"):
                payload[category] = []
            for item in rows:
                payload.setdefault(item.pop("category"), []).append(item)
        return payload

    def save_sources(self, sources: dict):
        chains = self._read_json(self.knowledge / "chains.json", [])
        sources = govern_sources(dict(sources), len(chains) if isinstance(chains, list) else 0)
        sources["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.service.import_sources(self.folder, sources, replace=True)
        self._write_json(self.sources_path, sources)
        self.service.repo.mark_compat_clean(self.folder, "sources")

    def save_task(self, name: str, task: dict) -> Path:
        """Persist an executable task package instead of only printing it."""
        safe = re.sub(r"[^0-9A-Za-z_-]+", "_", name).strip("_") or "task"
        path = self.tasks / f"{safe}.json"
        payload = dict(task)
        payload.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        self._write_json(path, payload)
        return path

    # ------------------------------------------------------------------
    # 定期数据写入
    # ------------------------------------------------------------------
    def save_daily(self, category: str, items: list[dict], date: str = None) -> Path:
        """保存某日某类别的定期条目（合并去重）."""
        date = date or datetime.now().strftime("%Y-%m-%d")
        day_dir = self.periodic / "daily" / date
        day_dir.mkdir(parents=True, exist_ok=True)
        fpath = day_dir / f"{category}.json"
        existing = self._read_json(fpath, [])
        candidates = []
        candidates.extend(self._normalize_item(it, category, date) for it in existing)
        for it in items:
            normalized = self._normalize_item(it, category, date)
            if normalized is not None:
                candidates.append(normalized)
        candidates = [item for item in candidates if item is not None]
        out, batch_audit = collapse_batch(candidates)
        historical = [item for item in self.service.repo.list_documents(
            self.folder, limit=5000)
            if not (item.get("date") == date and item.get("category") == category)]
        out, replay_audit = suppress_replays(out, historical)
        self.service.import_daily(self.folder, category, date, out)
        self._write_json(fpath, out)
        audit_path = day_dir / "dedup_audit.json"
        audit = self._read_json(audit_path, {})
        audit[category] = {"batch": batch_audit, "history": replay_audit,
                           "updated_at": datetime.now().isoformat(timespec="seconds")}
        self._write_json(audit_path, audit)
        self.service.repo.mark_compat_clean(
            self.folder, f"daily:{date}:{category}")
        return fpath

    def save_period(self, kind: str, payload: dict, key: str = None) -> Path:
        """保存周/月/季产物。kind in weekly/monthly/quarterly."""
        key = key or self._period_key(kind)
        fpath = self.periodic / kind / f"{key}.json"
        payload = dict(payload)
        payload.setdefault("kind", kind)
        payload.setdefault("key", key)
        payload.setdefault("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._write_json(fpath, payload)
        return fpath

    def deduplicate_history(self, *, apply: bool = False) -> dict:
        """Audit all active document links and optionally suppress duplicates."""
        plan = plan_history(self.service.repo.list_documents(self.folder, limit=100_000))
        summary = {key: value for key, value in plan.items() if key != "duplicate_groups"}
        summary["group_count"] = len(plan["duplicate_groups"])
        summary["applied"] = False
        if apply and plan["suppressed_links"]:
            summary["applied_links"] = self.service.repo.apply_document_dedup_plan(
                self.folder, plan)
            result = self.service.reconcile_compat([self.folder])
            if result["failed"]:
                raise OSError(result["errors"][0]["error"])
            summary["applied"] = True
        return summary

    # ------------------------------------------------------------------
    # 定期数据读取 / 删除
    # ------------------------------------------------------------------
    def list_daily(self, date: str = None, category: str = None) -> list[dict]:
        """Read the latest structured records; JSON paths remain provenance hints."""
        if date is None:
            dates = self.service.repo.list_document_dates(self.folder)
            date = dates[0] if dates else None
        if not date:
            return []
        items = self.service.repo.list_documents(self.folder, date=date, category=category)
        for item in items:
            item["_file"] = str(self.periodic / "daily" / date /
                                f"{item['category']}.json")
        return items

    def list_daily_range(self, days: int = 7, category: str = None,
                         end_date: str = None) -> list[dict]:
        """Read all daily records in a real date window, newest first."""
        daily_root = self.periodic / "daily"
        if not daily_root.exists():
            return []
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        except ValueError:
            end = datetime.now()
        selected = []
        for directory in daily_root.iterdir():
            if not directory.is_dir():
                continue
            try:
                day = datetime.strptime(directory.name, "%Y-%m-%d")
            except ValueError:
                continue
            delta = (end.date() - day.date()).days
            if 0 <= delta < max(1, days):
                selected.append(directory.name)
        out = []
        for day in sorted(selected, reverse=True):
            out.extend(self.list_daily(date=day, category=category))
        return out

    def list_daily_window(self, window, category: str = None) -> list[dict]:
        """Read records intersecting an explicit timezone-aware collection window."""
        from .time_windows import intersects_item

        days = max(1, (window.end.date() - window.start.date()).days + 1)
        candidates = self.list_daily_range(
            days=days, category=category, end_date=window.end.strftime("%Y-%m-%d"))
        return [item for item in candidates if intersects_item(window, item)]

    def list_period(self, kind: str) -> list[dict]:
        """列出某周期的全部产物（新→旧）."""
        d = self.periodic / kind
        if not d.exists():
            return []
        out = []
        for f in sorted(d.glob("*.json"), reverse=True):
            it = self._read_json(f, {})
            if it:
                it["_file"] = str(f)
                out.append(it)
        return out

    def delete_daily_item(self, date: str, category: str, key: str) -> bool:
        """删除某日某类别下的指定条目（按 title+url 匹配）."""
        fpath = self.periodic / "daily" / date / f"{category}.json"
        items = self._read_json(fpath, [])
        new = [it for it in items if self._key(it) != key]
        if len(new) == len(items):
            return False
        document_ids = [stable_id("doc", self._canonical_url(it.get("url", "")))
                        for it in items if self._key(it) == key and it.get("url")]
        self.service.repo.soft_delete_documents(self.folder, document_ids, actor="search")
        self._write_json(fpath, new)
        self.service.repo.mark_compat_clean(
            self.folder, f"daily:{date}:{category}")
        return True

    def delete_period(self, kind: str, key: str) -> bool:
        """删除周/月/季产物：移入回收站（可恢复），不永久删除."""
        return self.service.delete_period(self.folder, kind, key)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @staticmethod
    def _key(item: dict) -> str:
        return IndustryStore._canonical_url(item.get("url", "")) or \
            (item.get("title") or "").strip().lower()[:240]

    @staticmethod
    def _canonical_url(url: str) -> str:
        """Normalize tracking URLs so syndicated links deduplicate reliably."""
        try:
            parts = urlsplit((url or "").strip())
        except ValueError:
            return ""
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return ""
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in
                 {"gclid", "fbclid", "ref", "source"}]
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."),
                           path, urlencode(query), ""))

    @classmethod
    def _normalize_item(cls, item: dict, category: str, date: str) -> dict | None:
        """Validate and enrich the public daily-record contract."""
        out = dict(item or {})
        title = str(out.get("title") or "").strip()
        url = cls._canonical_url(str(out.get("url") or ""))
        if not title or not url:
            return None
        out["title"] = title
        out["url"] = url
        out["category"] = category
        out.setdefault("schema_version", "2.0")
        out.setdefault("review_status", "unreviewed")
        out.setdefault("date", date)
        out.setdefault("published_at", out.get("date", ""))
        out.setdefault("retrieved_at", datetime.now().isoformat(timespec="seconds"))
        out.setdefault("source", urlsplit(url).netloc)
        out.setdefault("source_domain", urlsplit(url).netloc)
        if not out.get("origin"):
            from .source_discovery import source_origin
            out["origin"] = source_origin(out)
        out.setdefault("source_language", "zh" if out.get("origin") == "china" else "en")
        out["content_hash"] = content_fingerprint(out)
        return out

    @staticmethod
    def _period_key(kind: str) -> str:
        now = datetime.now()
        if kind == "weekly":
            y, w, _ = now.isocalendar()
            return f"{y}-W{w:02d}"
        if kind == "monthly":
            return now.strftime("%Y-%m")
        if kind == "quarterly":
            return f"{now.year}-Q{(now.month - 1) // 3 + 1}"
        return now.strftime("%Y-%m-%d")

    @staticmethod
    def _read_json(path: Path, default):
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        return default

    @staticmethod
    def _write_json(path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(path)


def list_industries(data_root: str | Path) -> list[dict]:
    """列出 DomainIntelData 下全部行业文件夹（以 control.json 为标识）."""
    root = Path(data_root)
    out = []
    if not root.exists():
        return out
    skip = {"skill", "domains", "images", "_trash"}
    for d in sorted(root.iterdir()):
        if not (d.is_dir() and d.name not in skip and not d.name.startswith(".")):
            continue
        ctrl_path = d / "control.json"
        if not ctrl_path.exists():
            continue  # 非行业文件夹（如旧的 data/db/index/reports）
        ctrl = IndustryStore._read_json(ctrl_path, {})
        out.append({
            "folder": d.name,
            "periodic_enabled": ctrl.get("periodic_enabled", False),
        })
    return out
