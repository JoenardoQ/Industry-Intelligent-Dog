"""Application service: the only mutation boundary used by UI and pipelines."""

from __future__ import annotations

import json
import hashlib
import hmac
import shutil
import re
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

from .models import canonical_url, stable_id, utc_now, validate_folder
from .repository import IntelligenceRepository


SOURCE_CATEGORIES = ("official", "associations", "blogs", "platforms",
                     "self_media", "news", "journals", "financials", "finance")
INDUSTRY_BUNDLE_MAX_BYTES = 64 * 1024 * 1024
INDUSTRY_BUNDLE_MAX_RECORD_BYTES = 256 * 1024
INDUSTRY_BUNDLE_LIMITS = {
    "sources": 5_000, "documents": 100_000, "chain": 5_000,
    "chain_edges": 20_000, "entities": 100_000, "relations": 200_000,
    "claims": 100_000,
}

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

    @staticmethod
    def _portable_record(item: dict) -> dict:
        """Remove runtime paths and other local-only compatibility fields."""
        return {key: value for key, value in item.items()
                if not str(key).startswith("_") and key not in {
                    "raw_path", "artifact_path", "original_file"}}

    @staticmethod
    def _bundle_bytes(bundle: dict, *, include_checksum: bool = False) -> bytes:
        payload = dict(bundle)
        if not include_checksum:
            payload.pop("checksum_sha256", None)
        try:
            return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), default=str).encode("utf-8")
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("行业包不是可移植的 JSON 数据") from exc

    @classmethod
    def _bundle_checksum(cls, bundle: dict) -> str:
        return hashlib.sha256(cls._bundle_bytes(bundle)).hexdigest()

    @classmethod
    def _validate_industry_bundle(cls, bundle: dict) -> None:
        if not isinstance(bundle, dict) or int(bundle.get("schema_version", 0) or 0) != 1:
            raise ValueError("不支持的行业包版本")
        checksum = str(bundle.get("checksum_sha256") or "").casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("行业包缺少有效校验和")
        if len(cls._bundle_bytes(bundle, include_checksum=True)) > INDUSTRY_BUNDLE_MAX_BYTES:
            raise ValueError("行业包超过 64 MiB 上限")
        expected = cls._bundle_checksum(bundle)
        if not hmac.compare_digest(checksum, expected):
            raise ValueError("行业包校验和不匹配")
        if not isinstance(bundle.get("industry"), dict):
            raise ValueError("行业包缺少行业元数据")
        for key, limit in INDUSTRY_BUNDLE_LIMITS.items():
            rows = bundle.get(key, [])
            if not isinstance(rows, list) or len(rows) > limit:
                raise ValueError(f"行业包 {key} 记录数超过上限")
            for row in rows:
                if (not isinstance(row, dict)
                        or len(cls._bundle_bytes({"record": row})) >
                        INDUSTRY_BUNDLE_MAX_RECORD_BYTES):
                    raise ValueError(f"行业包 {key} 包含无效或过大的记录")
        for row in bundle.get("sources", []):
            if (str(row.get("category") or "") not in SOURCE_CATEGORIES
                    or not canonical_url(row.get("url", ""))):
                raise ValueError("行业包包含无效来源")
        for row in bundle.get("documents", []):
            if (not canonical_url(row.get("url", ""))
                    or not str(row.get("title") or "").strip()
                    or not str(row.get("category") or "").strip()
                    or not str(row.get("date") or row.get("observed_date") or "").strip()):
                raise ValueError("行业包包含无效文档")
        node_keys = {str(row.get("id") or row.get("name") or "")
                     for row in bundle.get("chain", [])}
        entity_keys = {str(row.get("id") or "") for row in bundle.get("entities", [])}
        if any(not str(row.get("name") or "").strip() for row in bundle.get("chain", [])):
            raise ValueError("行业包包含无效产业链节点")
        if any(not str(row.get("name") or row.get("canonical_name") or "").strip()
               for row in bundle.get("entities", [])):
            raise ValueError("行业包包含无效实体")
        for row in bundle.get("chain_edges", []):
            if (str(row.get("src_node_id") or row.get("src_name") or "") not in node_keys
                    or str(row.get("dst_node_id") or row.get("dst_name") or "") not in node_keys):
                raise ValueError("行业包产业链边引用未知节点")
        for row in bundle.get("relations", []):
            if (str(row.get("src_entity_id") or "") not in entity_keys
                    or str(row.get("dst_entity_id") or "") not in entity_keys):
                raise ValueError("行业包关系引用未知实体")

    def export_industry_bundle(self, folder: str) -> dict:
        """Export one industry without credentials, local paths, or shared DB state."""
        folder = validate_folder(folder)
        if not (self.root / folder).is_dir():
            raise FileNotFoundError(f"行业不存在：{folder}")
        industry = self.read_json(
            self.root / folder / "one_time/knowledge/industry.json", {})
        claims = []
        for claim in self.repo.list_claim_evidence(folder):
            portable = self._portable_record(claim)
            portable["evidence"] = [self._portable_record(row)
                                    for row in claim.get("evidence", [])]
            claims.append(portable)
        bundle = {
            "schema_version": 1,
            "exported_at": utc_now(),
            "industry": self._portable_record(industry),
            "sources": [self._portable_record(row)
                        for row in self.repo.list_sources(folder)],
            "documents": [self._portable_record(row)
                          for row in self.repo.list_documents(folder, limit=1_000_000)],
            "chain": [self._portable_record(row)
                      for row in self.repo.list_chain_nodes(folder)],
            "chain_edges": [self._portable_record(row)
                            for row in self.repo.list_chain_edges(folder, active_only=False)],
            "entities": [self._portable_record(row)
                         for row in self.repo.list_compat_entities(folder)],
            "relations": [self._portable_record(row)
                          for row in self.repo.graph(folder, limit=1_000_000)["edges"]],
            "claims": claims,
        }
        for key, limit in INDUSTRY_BUNDLE_LIMITS.items():
            if len(bundle[key]) > limit:
                raise ValueError(f"行业数据超过可移植包 {key} 上限")
        bundle["checksum_sha256"] = self._bundle_checksum(bundle)
        if len(self._bundle_bytes(bundle, include_checksum=True)) > INDUSTRY_BUNDLE_MAX_BYTES:
            raise ValueError("行业数据超过 64 MiB 可移植包上限")
        return bundle

    def import_industry_bundle(self, folder: str, name: str, bundle: dict) -> dict:
        """Stage, validate and atomically merge an untrusted portable bundle."""
        folder = validate_folder(folder)
        self._validate_industry_bundle(bundle)
        industry = bundle.get("industry") or {}
        display_name = str(name or industry.get("name") or folder).strip()
        target = self.root / folder
        if target.exists():
            raise FileExistsError(f"行业已存在：{folder}")
        with self.repo.connection() as con:
            if con.execute("SELECT 1 FROM industries WHERE folder=?", (folder,)).fetchone():
                raise FileExistsError(f"行业记录已存在：{folder}")
        staging_parent = self.root / "_import_staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix="bundle-", dir=staging_parent))
        try:
            staged = IntDogService(staging_root)
            counts = staged._populate_import_staging(folder, display_name, bundle)
            self._merge_staged_import(staged, folder)
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
        return {"folder": folder, "name": display_name, "imported": counts}

    def _populate_import_staging(self, folder: str, display_name: str,
                                 bundle: dict) -> dict:
        """Populate an isolated database; imported trust decisions are never retained."""
        self.create_industry(folder, display_name)
        counts = {key: 0 for key in INDUSTRY_BUNDLE_LIMITS}
        grouped: dict[tuple[str, str], list[dict]] = {}
        document_map: dict[str, str] = {}
        for row in bundle.get("documents", []):
            date = str(row.get("date") or row.get("observed_date"))
            category = str(row.get("category"))
            clean = {**row, "review_status": "unreviewed",
                     "evidence_status": "collected", "verified": False}
            grouped.setdefault((date, category), []).append(clean)
        for (date, category), rows in grouped.items():
            ids = self.repo.upsert_documents(folder, category, date, rows, strict=True)
            counts["documents"] += len(ids)
            for row, document_id in zip(rows, ids, strict=True):
                document_map[str(row.get("id") or document_id)] = document_id
        for row in bundle.get("sources", []):
            clean = {**row, "monitoring_status": "recommended_manual",
                     "added_manually": True,
                     "governance_reason": "portable_bundle_requires_review"}
            self.repo.upsert_source(folder, str(row["category"]), clean)
            counts["sources"] += 1
        node_map: dict[str, str] = {}
        for row in bundle.get("chain", []):
            clean = {**row, "parent_id": None, "status": "candidate",
                     "coverage_status": "empty", "evidence_count": 0}
            node_id = self.repo.upsert_chain_node(folder, clean)
            node_map[str(row.get("id") or row.get("name"))] = node_id
            node_map[str(row.get("name"))] = node_id
            counts["chain"] += 1
        for row in bundle.get("chain", []):
            parent = node_map.get(str(row.get("parent_id") or ""))
            if parent:
                self.repo.upsert_chain_node(folder, {
                    **row, "parent_id": parent, "status": "candidate",
                    "coverage_status": "empty", "evidence_count": 0})
        for row in bundle.get("chain_edges", []):
            self.repo.upsert_chain_edge(folder, {
                **row,
                "src_node_id": node_map[str(row.get("src_node_id") or row.get("src_name"))],
                "dst_node_id": node_map[str(row.get("dst_node_id") or row.get("dst_name"))],
                "status": "candidate", "evidence_count": 0})
            counts["chain_edges"] += 1
        entity_map: dict[str, str] = {}
        for row in bundle.get("entities", []):
            clean = {**row, "name": row.get("name") or row.get("canonical_name"),
                     "references": [], "status": "candidate", "evidence_count": 0}
            entity_id = self.repo.upsert_entity(folder, clean)
            entity_map[str(row.get("id") or entity_id)] = entity_id
            counts["entities"] += 1
        iid, now = self.repo.industry_id(folder), utc_now()
        relations = bundle.get("relations", [])
        if relations:
            round_id = stable_id("cvr", iid, 1)
            with self.repo.transaction() as con:
                con.execute("""INSERT INTO coverage_rounds
                    (id,industry_id,round_no,status,frontier_json,outcome_json,log_json,
                     stopping_reason,created_at,updated_at)
                    VALUES(?,?,1,'planned','[]','{}','[]','portable import review',?,?)""",
                    (round_id, iid, now, now))
                for index, row in enumerate(relations):
                    src = entity_map[str(row.get("src_entity_id"))]
                    dst = entity_map[str(row.get("dst_entity_id"))]
                    predicate = str(row.get("predicate") or "related_to")
                    payload = {**row, "source": src, "target": dst,
                               "relation": predicate, "imported_from_bundle": True}
                    canonical_key = stable_id("relation-candidate-key", src, predicate, dst)
                    candidate_id = stable_id("rlc", iid, canonical_key, "portable-import")
                    con.execute("""INSERT INTO relation_candidates
                        (id,industry_id,round_id,query_id,cell_id,canonical_key,payload_json,
                         document_id,assertion_id,status,status_reason,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,NULL,NULL,'manual_review',?,?,?)""",
                        (candidate_id, iid, round_id, None, "portable-import", canonical_key,
                         json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                         "portable bundle relationships require evidence review", now, now))
                    counts["relations"] += 1
        for row in bundle.get("claims", []):
            evidence = []
            for item in row.get("evidence", []) or []:
                document_id = document_map.get(str(item.get("document_id") or ""))
                if not document_id:
                    continue
                evidence.append({
                    "document_id": document_id,
                    "relation": item.get("relation", "supports"),
                    "excerpt": item.get("excerpt", ""),
                    "publisher_cluster": item.get("publisher_cluster", ""),
                    "extraction_method": "portable_bundle_import_untrusted",
                    "confidence": item.get("confidence"),
                })
            self.repo.save_claim_bundles(folder, [{
                "subject_id": entity_map.get(str(row.get("subject_id") or "")),
                "predicate": row.get("predicate", "states"),
                "object": row.get("object"), "qualifiers": row.get("qualifiers", {}),
                "valid_from": row.get("valid_from") or "",
                "valid_to": row.get("valid_to") or "", "status": "candidate",
                "evidence": evidence,
            }])
            counts["claims"] += 1
        result = self.reconcile_compat([folder])
        if result["failed"]:
            raise OSError(result["errors"][0]["error"])
        return counts

    @staticmethod
    def _read_table(con, table: str) -> list[dict]:
        return [dict(row) for row in con.execute(f'SELECT * FROM "{table}"')]

    def _merge_staged_import(self, staged: "IntDogService", folder: str) -> None:
        """Merge a fully validated staging DB and filesystem as one recoverable unit."""
        global_tables = ("publishers", "sources", "entities", "publisher_domains",
                         "source_publishers", "documents", "entity_aliases",
                         "entity_names", "entity_identifiers")
        industry_tables = ("industries", "industry_sources", "industry_documents",
                           "value_chain_nodes", "value_chain_edges", "industry_entities",
                           "entity_chain_roles", "claims", "evidence", "coverage_rounds",
                           "coverage_round_queries", "relation_candidates",
                           "compatibility_views")
        rows: dict[str, list[dict]] = {}
        with staged.repo.connection() as source:
            for table in (*global_tables, *industry_tables):
                rows[table] = self._read_table(source, table)
        target = self.root / folder
        moved = False
        try:
            with self.repo.transaction() as con:
                for table in global_tables:
                    for row in rows[table]:
                        columns = tuple(row)
                        sql = (f'INSERT OR IGNORE INTO "{table}" '
                               f'({",".join(columns)}) VALUES '
                               f'({",".join("?" for _ in columns)})')
                        con.execute(sql, tuple(row[key] for key in columns))
                for table in industry_tables:
                    table_rows = rows[table]
                    if table == "value_chain_nodes":
                        table_rows = [{**row, "parent_id": None} for row in table_rows]
                    for row in table_rows:
                        columns = tuple(row)
                        sql = (f'INSERT INTO "{table}" ({",".join(columns)}) VALUES '
                               f'({",".join("?" for _ in columns)})')
                        con.execute(sql, tuple(row[key] for key in columns))
                for row in rows["value_chain_nodes"]:
                    if row.get("parent_id"):
                        con.execute("UPDATE value_chain_nodes SET parent_id=? WHERE id=?",
                                    (row["parent_id"], row["id"]))
                (staged.root / folder).rename(target)
                moved = True
        except Exception:
            if moved and target.exists():
                shutil.rmtree(target, ignore_errors=True)
            raise

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
