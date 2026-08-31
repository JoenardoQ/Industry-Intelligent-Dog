"""Application service: the only mutation boundary used by UI and pipelines."""

from __future__ import annotations

import json
import shutil
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

from .models import canonical_url, stable_id, utc_now, validate_folder
from .repository import IntelligenceRepository


SOURCE_CATEGORIES = ("official", "associations", "blogs", "platforms",
                     "self_media", "news", "journals", "financials", "finance")

_ACTIVE_RUN: ContextVar[tuple[str, str, str] | None] = ContextVar("intdog_active_run", default=None)


class IntDogService:
    def __init__(self, data_root: str | Path):
        self.root = Path(data_root)
        self.repo = IntelligenceRepository(self.root)

    @staticmethod
    def read_json(path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def write_text(path: Path, text: str) -> None:
        """Atomically replace a UTF-8 text artifact."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    def create_industry(self, folder: str, name: str = "") -> Path:
        folder = validate_folder(folder)
        target = self.root / folder
        if target.exists():
            raise FileExistsError(f"行业已存在：{folder}")
        for sub in ("one_time/knowledge", "one_time/reports", "one_time/tasks",
                    "periodic/daily", "periodic/weekly", "periodic/monthly",
                    "periodic/quarterly"):
            (target / sub).mkdir(parents=True, exist_ok=True)
        now = utc_now()
        self.write_json(target / "control.json", {"schema_version": "3.0",
            "periodic_enabled": False, "daily_time": "08:00", "weekly_day": "monday",
            "monthly_day": 1, "quarterly_months": [1, 4, 7, 10],
            "last_run": {}, "job_status": {}, "created_at": now})
        self.write_json(target / "one_time/knowledge/industry.json",
                        {"id": stable_id("ind", folder), "name": name or folder,
                         "name_en": "", "description": "", "references": [],
                         "status": "draft", "schema_version": "3.0"})
        self.write_json(target / "one_time/knowledge/chains.json", [])
        self.write_json(target / "one_time/knowledge/entities.json", [])
        self.write_json(target / "sources.json", {"industry": name or folder,
                        "schema_version": "3.0", **{key: [] for key in SOURCE_CATEGORIES}})
        self.repo.ensure_industry(folder, name or folder)
        self.repo.mark_compat_clean(folder, "sources")
        self.repo.mark_compat_clean(folder, "entities")
        self.repo.mark_compat_clean(folder, "chains")
        return target

    def rename_industry(self, old_folder: str, new_folder: str, name: str = "") -> Path:
        old_folder, new_folder = validate_folder(old_folder), validate_folder(new_folder)
        old, new = self.root / old_folder, self.root / new_folder
        if not old.exists():
            raise FileNotFoundError(f"行业不存在：{old_folder}")
        if new.exists() and old.resolve() != new.resolve():
            raise FileExistsError(f"目标行业已存在：{new_folder}")
        with self.run(old_folder, "rename-industry"):
            moved = old.resolve() != new.resolve()
            if moved:
                old.rename(new)
            try:
                self.repo.rename_industry(old_folder, new_folder, name)
            except Exception:
                if moved and new.exists() and not old.exists():
                    new.rename(old)
                raise
            if name:
                knowledge = new / "one_time/knowledge/industry.json"
                item = self.read_json(knowledge, {}); item["name"] = name
                self.write_json(knowledge, item)
                sources = self.read_json(new / "sources.json", {}); sources["industry"] = name
                self.write_json(new / "sources.json", sources)
        return new

    def archive_industry(self, folder: str) -> Path:
        folder = validate_folder(folder)
        source = self.root / folder
        if not source.exists():
            raise FileNotFoundError(f"行业不存在：{folder}")
        trash = self.root / "_trash/industries"; trash.mkdir(parents=True, exist_ok=True)
        target = trash / f"{folder}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        with self.run(folder, "archive-industry"):
            shutil.move(str(source), str(target))
            try:
                self.repo.archive_industry(folder)
            except Exception:
                shutil.move(str(target), str(source))
                raise
        return target

    def list_trash(self) -> list[dict]:
        """Return recoverable records without following paths outside `_trash`."""
        trash = self.root / "_trash"
        rows: list[dict] = []
        industry_root = trash / "industries"
        if industry_root.is_dir():
            for path in sorted(industry_root.iterdir(), reverse=True):
                if not path.is_dir():
                    continue
                match = re.match(r"^(.*)_\d{8}_\d{6}_\d{6}$", path.name)
                folder = match.group(1) if match else path.name
                knowledge = self.read_json(
                    path / "one_time/knowledge/industry.json", {})
                rows.append({"id": path.name, "kind": "industry", "folder": folder,
                             "name": knowledge.get("name") or folder,
                             "created_at": datetime.fromtimestamp(
                                 path.stat().st_mtime).isoformat(timespec="seconds"),
                             "item_count": 1})
        daily_root = trash / "daily"
        if daily_root.is_dir():
            for path in sorted(daily_root.glob("*.json"), reverse=True):
                payload = self.read_json(path, {})
                if not isinstance(payload, dict):
                    continue
                rows.append({"id": path.name, "kind": "daily",
                             "folder": payload.get("folder", ""),
                             "name": f"{payload.get('folder', '')} 每日情报批次",
                             "created_at": payload.get("removed_at", ""),
                             "item_count": len(payload.get("items") or [])})
        return rows

    def restore_trash(self, item_id: str, *, desired_folder: str = "") -> dict:
        """Restore an archived industry or deleted daily batch without overwrite."""
        if not item_id or Path(item_id).name != item_id:
            raise ValueError("无效的回收站记录")
        industry_path = self.root / "_trash/industries" / item_id
        if industry_path.is_dir():
            match = re.match(r"^(.*)_\d{8}_\d{6}_\d{6}$", item_id)
            original = match.group(1) if match else item_id
            folder = validate_folder(desired_folder or original)
            target = self.root / folder
            if target.exists():
                raise FileExistsError(f"目标行业已存在：{folder}")
            # Renaming an archived registry key is deliberately not implicit:
            # it would also require updating compatibility paths and consumers.
            if folder != original:
                raise ValueError("恢复行业必须使用原文件夹名称；可在恢复后重命名")
            shutil.move(str(industry_path), str(target))
            try:
                self.repo.restore_industry_record(folder)
            except Exception:
                shutil.move(str(target), str(industry_path))
                raise
            return {"kind": "industry", "folder": folder, "restored": 1,
                    "skipped": 0}
        daily_path = self.root / "_trash/daily" / item_id
        if not daily_path.is_file():
            raise FileNotFoundError("回收站记录不存在")
        payload = self.read_json(daily_path, {})
        folder = validate_folder(str(payload.get("folder") or ""))
        if not (self.root / folder).is_dir():
            raise FileNotFoundError("原行业当前未激活，请先恢复行业")
        restored = skipped = 0
        grouped: dict[tuple[str, str], list[dict]] = {}
        for record in payload.get("items") or []:
            date, category, item = str(record.get("date") or ""), str(
                record.get("category") or ""), record.get("item") or {}
            if not date or not category or not isinstance(item, dict):
                skipped += 1; continue
            active = self.repo.list_documents(folder, date=date, category=category)
            key = str(item.get("url") or item.get("title") or "")
            if any(str(row.get("url") or row.get("title") or "") == key for row in active):
                skipped += 1; continue
            grouped.setdefault((date, category), []).append(item)
        for (date, category), items in grouped.items():
            restored += self.import_daily(folder, category, date, items)
        result = self.reconcile_compat([folder])
        if result["failed"]:
            raise OSError(result["errors"][0]["error"])
        restored_root = self.root / "_trash/restored"; restored_root.mkdir(parents=True, exist_ok=True)
        target = restored_root / daily_path.name
        if target.exists():
            target = restored_root / f"{daily_path.stem}_{datetime.now().strftime('%f')}.json"
        daily_path.replace(target)
        self.repo.audit("restore", "daily_batch", object_id=item_id,
                        details={"folder": folder, "restored": restored,
                                 "skipped": skipped})
        return {"kind": "daily", "folder": folder, "restored": restored,
                "skipped": skipped}

    def preview_trash_restore(self, item_id: str) -> dict:
        if not item_id or Path(item_id).name != item_id:
            raise ValueError("无效的回收站记录")
        industry_path = self.root / "_trash/industries" / item_id
        if industry_path.is_dir():
            match = re.match(r"^(.*)_\d{8}_\d{6}_\d{6}$", item_id)
            folder = match.group(1) if match else item_id
            return {"id": item_id, "kind": "industry", "folder": folder,
                    "restorable": not (self.root / folder).exists(),
                    "restore_count": 1, "skip_count": 0,
                    "collisions": ([folder] if (self.root / folder).exists() else [])}
        daily_path = self.root / "_trash/daily" / item_id
        if not daily_path.is_file():
            raise FileNotFoundError("回收站记录不存在")
        payload = self.read_json(daily_path, {})
        folder = validate_folder(str(payload.get("folder") or ""))
        if not (self.root / folder).is_dir():
            return {"id": item_id, "kind": "daily", "folder": folder,
                    "restorable": False, "restore_count": 0,
                    "skip_count": len(payload.get("items") or []),
                    "collisions": ["原行业当前未激活"]}
        restore_count, collisions = 0, []
        cache: dict[tuple[str, str], set[str]] = {}
        for record in payload.get("items") or []:
            date = str(record.get("date") or "")
            category = str(record.get("category") or "")
            item = record.get("item") or {}
            if not date or not category or not isinstance(item, dict):
                collisions.append("无效记录"); continue
            group = (date, category)
            if group not in cache:
                cache[group] = {str(row.get("url") or row.get("title") or "")
                                for row in self.repo.list_documents(
                                    folder, date=date, category=category)}
            key = str(item.get("url") or item.get("title") or "")
            if not key or key in cache[group]:
                collisions.append(key or "空标识")
            else:
                restore_count += 1; cache[group].add(key)
        return {"id": item_id, "kind": "daily", "folder": folder,
                "restorable": True, "restore_count": restore_count,
                "skip_count": len(collisions), "collisions": collisions[:100]}

    def set_periodic(self, folder: str, enabled: bool) -> None:
        self.update_control(folder, {"periodic_enabled": bool(enabled)})

    def update_control(self, folder: str, changes: dict) -> dict:
        folder = validate_folder(folder)
        with self.run(folder, "update-control"):
            path = self.root / folder / "control.json"
            control = self.read_json(path, {})
            control.update(changes); control["updated_at"] = utc_now()
            self.write_json(path, control)
        return control

    def delete_period(self, folder: str, kind: str, key: str) -> bool:
        if kind not in {"weekly", "monthly", "quarterly"}:
            raise ValueError(f"未知周期：{kind}")
        path = self.root / validate_folder(folder) / "periodic" / kind / f"{key}.json"
        if not path.exists():
            return False
        with self.run(folder, "delete-period"):
            trash = self.root / "_trash/periodic"; trash.mkdir(parents=True, exist_ok=True)
            target = trash / f"{folder}_{kind}_{key}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            path.replace(target)
        return True

    def _write_compat(self, folder: str, view_key: str, path: Path, payload) -> None:
        """Write one materialized JSON view and clear its transactional dirty flag."""
        try:
            self.write_json(path, payload)
        except Exception as exc:
            self.repo.mark_compat_error(folder, view_key, exc)
            raise
        self.repo.mark_compat_clean(folder, view_key)

    def reconcile_compat(self, folders: list[str] | None = None) -> dict:
        """Rebuild dirty compatibility JSON views from canonical SQLite facts."""
        result = {"repaired": 0, "failed": 0, "errors": []}
        for view in self.repo.dirty_compat_views(folders):
            folder, key = view["folder"], view["view_key"]
            try:
                if key == "sources":
                    path = self.root / folder / "sources.json"
                    payload = self.read_json(path, {})
                    payload.setdefault("industry", folder)
                    payload.setdefault("schema_version", "3.0")
                    for category in SOURCE_CATEGORIES:
                        payload[category] = []
                    for item in self.repo.list_sources(folder):
                        category = item.pop("category")
                        payload.setdefault(category, []).append(item)
                    payload["updated_at"] = utc_now()
                elif key == "entities":
                    path = self.root / folder / "one_time/knowledge/entities.json"
                    payload = self.repo.list_compat_entities(folder)
                elif key == "chains":
                    path = self.root / folder / "one_time/knowledge/chains.json"
                    payload = self.repo.list_chain_nodes(folder)
                elif key.startswith("daily:"):
                    _, date, category = key.split(":", 2)
                    path = self.root / folder / "periodic/daily" / date / f"{category}.json"
                    payload = self.repo.list_documents(
                        folder, date=date, category=category, limit=100_000)
                    for item in payload:
                        item.pop("id", None)
                else:
                    raise ValueError(f"未知兼容视图：{key}")
                self._write_compat(folder, key, path, payload)
                result["repaired"] += 1
            except Exception as exc:
                result["failed"] += 1
                result["errors"].append({"folder": folder, "view": key,
                                         "error": f"{type(exc).__name__}: {exc}"})
                try:
                    self.repo.mark_compat_error(folder, key, exc)
                except Exception:
                    pass
        return result

    def add_source(self, folder: str, category: str, source: dict) -> bool:
        if category not in SOURCE_CATEGORIES:
            raise ValueError(f"未知来源类别：{category}")
        url = canonical_url(source.get("url", ""))
        if not url:
            raise ValueError("请输入完整的 http/https URL")
        exists = any(canonical_url(item.get("url", "")) == url
                     for item in self.repo.list_sources(folder))
        if exists:
            return False
        item = dict(source, url=url)
        item.setdefault("added_manually", True)
        item.setdefault("added_at", utc_now())
        item.setdefault("governance_role", "manual")
        item.setdefault("governance_reason", "manual_registration_pending_portfolio_review")
        self.repo.upsert_source(folder, category, item)
        result = self.reconcile_compat([folder])
        if result["failed"]:
            raise OSError(result["errors"][0]["error"])
        return True

    def delete_source(self, folder: str, category: str, url: str) -> bool:
        folder = validate_folder(folder)
        wanted = canonical_url(url)
        if not self.repo.delete_source(folder, category, wanted):
            return False
        result = self.reconcile_compat([folder])
        if result["failed"]:
            raise OSError(result["errors"][0]["error"])
        return True

    def delete_daily(self, folder: str,
                     identities: list[tuple[str, str, str]]) -> int:
        grouped: dict[tuple[str, str], set[str]] = {}
        for date, category, key in identities:
            grouped.setdefault((str(date), str(category)), set()).add(str(key))
        removed, document_ids = [], []
        for (date, category), keys in grouped.items():
            items = self.repo.list_documents(folder, date=date, category=category)
            if not items:
                legacy_path = (self.root / folder / "periodic/daily" / date /
                               f"{category}.json")
                legacy_items = self.read_json(legacy_path, [])
                if legacy_items:
                    self.import_daily(folder, category, date, legacy_items)
                    items = self.repo.list_documents(folder, date=date, category=category)
            for item in items:
                item_key = str(item.get("url") or item.get("title") or "")[:200]
                if item_key in keys:
                    removed.append({"date": date, "category": category, "item": item})
                    document_ids.append(item["id"])
        if not removed:
            return 0
        trash = self.root / "_trash/daily"; trash.mkdir(parents=True, exist_ok=True)
        backup = trash / f"{folder}_batch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        self.write_json(backup, {"folder": folder, "removed_at": utc_now(), "items": removed})
        self.repo.soft_delete_documents(folder, document_ids)
        result = self.reconcile_compat([folder])
        if result["failed"]:
            raise OSError(result["errors"][0]["error"])
        return len(removed)

    def delete_entity(self, folder: str, entity_id: str) -> bool:
        path = self.root / folder / "one_time/knowledge/entities.json"
        entities = self.read_json(path, [])
        match = next((item for item in entities if item.get("id") == entity_id), None)
        canonical_id = entity_id
        if match:
            canonical_id = stable_id(
                "ent", match.get("type") or match.get("kind") or "company",
                match.get("name"), match.get("country", ""))
        if not self.repo.delete_entity(folder, canonical_id):
            return False
        result = self.reconcile_compat([folder])
        if result["failed"]:
            raise OSError(result["errors"][0]["error"])
        return True

    def update_research_agenda_status(self, folder: str, item_id: str,
                                      status: str, *, note: str = "") -> bool:
        folder = validate_folder(folder)
        with self.run(folder, "agenda-status", "update"):
            return self.repo.update_research_agenda_status(
                folder, item_id, status, actor="app", note=note)

    def create_research_task(self, folder: str, agenda_id: str,
                             budget: int = 20) -> dict:
        folder = validate_folder(folder)
        with self.run(folder, "create-research-task", "package"):
            task = self.repo.create_research_task(folder, agenda_id, budget)
            path = (self.root / folder / "one_time" / "intelligence" / "tasks" /
                    f"{task['id']}.json")
            self.write_json(path, task)
            return {**task, "path": str(path)}

    def import_sources(self, folder: str, payload: dict, *, replace: bool = False) -> int:
        count = 0
        active = set()
        for category in SOURCE_CATEGORIES:
            for item in payload.get(category, []) or []:
                try:
                    source_id = self.repo.upsert_source(folder, category, item)
                    active.add((source_id, category)); count += 1
                except (TypeError, ValueError):
                    continue
        if replace:
            self.repo.retain_source_links(folder, active)
        return count

    def import_daily(self, folder: str, category: str, date: str,
                     items: list[dict]) -> int:
        return len(self.repo.upsert_documents(folder, category, date, items))

    @contextmanager
    def run(self, folder: str, kind: str, stage: str = "start"):
        active = _ACTIVE_RUN.get()
        db_key = str(self.repo.db_path.resolve())
        if active and active[:2] == (db_key, folder):
            self.repo.update_run(active[2], stage=stage)
            yield active[2]
            return
        run_id = self.repo.start_run(folder, kind, stage)
        lock_key = f"industry:{folder}"
        token = None
        try:
            self.repo.acquire_lock(lock_key, run_id)
            token = _ACTIVE_RUN.set((db_key, folder, run_id))
            yield run_id
        except Exception as exc:
            self.repo.update_run(run_id, status="failed", error=exc)
            raise
        else:
            self.repo.finish_run_if_running(run_id)
        finally:
            if token is not None:
                _ACTIVE_RUN.reset(token)
            self.repo.release_lock(lock_key, run_id)

    def migrate_legacy(self, folders: list[str] | None = None) -> dict:
        stats = {"industries": 0, "sources": 0, "documents": 0, "entities": 0,
                 "skipped_files": 0}
        candidates = [self.root / name for name in folders] if folders else list(self.root.iterdir())
        for directory in candidates:
            if not directory.is_dir() or not (directory / "control.json").exists():
                continue
            folder = directory.name
            industry = self.read_json(directory / "one_time/knowledge/industry.json", {})
            self.repo.ensure_industry(folder, industry.get("name") or folder)
            stats["industries"] += 1
            sources_file = directory / "sources.json"
            if self._legacy_needs_import(sources_file, "industry_sources", folder):
                stats["sources"] += self.import_sources(
                    folder, self.read_json(sources_file, {}))
                self._mark_legacy_import(sources_file)
                self.repo.mark_compat_clean(folder, "sources")
            elif sources_file.exists():
                stats["skipped_files"] += 1
            daily = directory / "periodic/daily"
            if daily.exists():
                for file in daily.glob("*/*.json"):
                    if not self._legacy_needs_import(file):
                        stats["skipped_files"] += 1; continue
                    items = self.read_json(file, [])
                    if isinstance(items, list):
                        stats["documents"] += self.import_daily(
                            folder, file.stem, file.parent.name, items)
                    self._mark_legacy_import(file)
                    self.repo.mark_compat_clean(
                        folder, f"daily:{file.parent.name}:{file.stem}")
            entity_file = directory / "one_time/knowledge/entities.json"
            if self._legacy_needs_import(entity_file, "industry_entities", folder):
                entities = self.read_json(entity_file, [])
                for item in entities if isinstance(entities, list) else []:
                    try:
                        entity_id = self.repo.upsert_entity(folder, item)
                        chain = str(item.get("chain") or "").strip()
                        if chain:
                            chain_id = self.repo.upsert_entity(folder, {
                                "name": chain, "type": "supply_chain_activity",
                                "role": "supply_chain_activity", "chain": chain,
                                "status": "candidate"})
                            self.repo.upsert_relation(
                                folder, entity_id, "participates_in", chain_id,
                                confidence=item.get("confidence"),
                                metadata={"references": item.get("references", []),
                                          "migrated_from": "entities.json"})
                        stats["entities"] += 1
                    except (TypeError, ValueError):
                        continue
                self._mark_legacy_import(entity_file)
                self.repo.mark_compat_clean(folder, "entities")
            elif entity_file.exists():
                stats["skipped_files"] += 1
            chain_file = directory / "one_time/knowledge/chains.json"
            if self._legacy_needs_import(chain_file):
                chains = self.read_json(chain_file, [])
                for item in chains if isinstance(chains, list) else []:
                    try:
                        self.repo.upsert_chain_node(folder, item)
                    except (TypeError, ValueError):
                        continue
                self._mark_legacy_import(chain_file)
                self.repo.mark_compat_clean(folder, "chains")
        return stats

    def _legacy_needs_import(self, path: Path, populated_table: str = "",
                             folder: str = "") -> bool:
        if not path.exists():
            return False
        key = path.relative_to(self.root).as_posix()
        mtime = path.stat().st_mtime_ns
        already_populated = False
        with self.repo.connection() as con:
            seen = con.execute("SELECT mtime_ns FROM legacy_imports WHERE path=?", (key,)).fetchone()
            if seen:
                return seen["mtime_ns"] != mtime
            if populated_table and folder:
                iid = self.repo.industry_id(folder)
                count = con.execute(
                    f"SELECT COUNT(*) FROM {populated_table} WHERE industry_id=?", (iid,)).fetchone()[0]
                already_populated = bool(count)
        if already_populated:
            self._mark_legacy_import(path)
            return False
        return True

    def _mark_legacy_import(self, path: Path) -> None:
        if not path.exists():
            return
        key = path.relative_to(self.root).as_posix()
        with self.repo.transaction() as con:
            con.execute("""INSERT INTO legacy_imports(path,mtime_ns,imported_at)
                VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET
                mtime_ns=excluded.mtime_ns,imported_at=excluded.imported_at""",
                (key, path.stat().st_mtime_ns, utc_now()))
