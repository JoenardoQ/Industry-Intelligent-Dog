"""Persistence queries for deterministic Intelligence Lab analyses."""

from __future__ import annotations

import uuid

from .models import json_text, json_value, stable_id, utc_now


class AnalysisRepositoryMixin:
    def save_analysis_artifact(self, folder: str, kind: str, content: dict, *,
                               input_hash: str, algorithm_version: str,
                               metrics: dict | None = None,
                               status: str = "completed",
                               deduplicate: bool = True) -> dict:
        iid = self.industry_id(folder)
        now = utc_now()
        if deduplicate:
            with self.connection() as con:
                previous = con.execute("""SELECT id,created_at FROM analysis_artifacts
                    WHERE industry_id=? AND kind=? AND input_hash=? AND algorithm_version=?
                    AND status=? ORDER BY created_at DESC,rowid DESC LIMIT 1""",
                    (iid, kind, input_hash, algorithm_version, status)).fetchone()
            if previous:
                return {"id": previous["id"], "created": False,
                        "created_at": previous["created_at"]}
        artifact_id = stable_id("art", iid, kind, input_hash, now, uuid.uuid4().hex)
        stored_content = dict(content)
        stored_content["artifact_id"] = artifact_id
        with self.transaction() as con:
            con.execute("""INSERT INTO analysis_artifacts
                (id,industry_id,kind,input_hash,algorithm_version,status,
                 content_json,metrics_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (artifact_id, iid, kind, input_hash, algorithm_version, status,
                 json_text(stored_content), json_text(metrics or {}), now))
        return {"id": artifact_id, "created": True, "created_at": now}

    def prune_analysis_artifacts(self, folder: str, kind: str, keep: int = 365) -> int:
        iid = self.industry_id(folder)
        keep = max(1, int(keep))
        with self.transaction() as con:
            cur = con.execute("""DELETE FROM analysis_artifacts WHERE id IN (
                SELECT id FROM analysis_artifacts WHERE industry_id=? AND kind=?
                ORDER BY created_at DESC,rowid DESC LIMIT -1 OFFSET ?)""", (iid, kind, keep))
        return cur.rowcount

    def list_analysis_artifacts(self, folder: str, kind: str, limit: int = 30) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT id,kind,input_hash,algorithm_version,status,
                metrics_json,created_at FROM analysis_artifacts
                WHERE industry_id=? AND kind=? ORDER BY created_at DESC,rowid DESC LIMIT ?""",
                (iid, kind, max(1, int(limit)))).fetchall()
        return [{"id": row["id"], "kind": row["kind"], "input_hash": row["input_hash"],
                 "algorithm_version": row["algorithm_version"], "status": row["status"],
                 "metrics": json_value(row["metrics_json"], {}),
                 "created_at": row["created_at"]} for row in rows]

    def latest_analysis_artifact(self, folder: str, kind: str) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            row = con.execute("""SELECT * FROM analysis_artifacts
                WHERE industry_id=? AND kind=? ORDER BY created_at DESC,rowid DESC LIMIT 1""",
                (iid, kind)).fetchone()
        if not row:
            return {}
        return {"id": row["id"], "kind": row["kind"],
                "input_hash": row["input_hash"],
                "algorithm_version": row["algorithm_version"],
                "status": row["status"], "created_at": row["created_at"],
                "content": json_value(row["content_json"], {}),
                "metrics": json_value(row["metrics_json"], {})}

    def list_claim_evidence(self, folder: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            claims = con.execute("""SELECT c.*,e.canonical_name AS subject_name
                FROM claims c LEFT JOIN entities e ON e.id=c.subject_id
                WHERE c.industry_id=? AND c.superseded_at IS NULL
                ORDER BY c.updated_at DESC,c.id""", (iid,)).fetchall()
            evidence = con.execute("""SELECT v.*,d.title AS document_title,
                d.canonical_url AS document_url,
                COALESCE(NULLIF(v.publisher_cluster,''),(
                    SELECT p.owner_cluster FROM source_publishers sp
                    JOIN publishers p ON p.id=sp.publisher_id WHERE sp.source_id=d.source_id
                    ORDER BY CASE sp.relation WHEN 'original' THEN 0 ELSE 1 END,
                    sp.confidence DESC LIMIT 1),'unknown') AS resolved_cluster,
                COALESCE((SELECT p.verification_status FROM source_publishers sp
                    JOIN publishers p ON p.id=sp.publisher_id WHERE sp.source_id=d.source_id
                    ORDER BY CASE sp.relation WHEN 'original' THEN 0 ELSE 1 END,
                    sp.confidence DESC LIMIT 1),'unverified') AS publisher_verification
                FROM evidence v JOIN claims c ON c.id=v.claim_id
                LEFT JOIN documents d ON d.id=v.document_id
                WHERE c.industry_id=? AND c.superseded_at IS NULL
                ORDER BY v.created_at,v.id""", (iid,)).fetchall()
        by_claim: dict[str, dict[str, dict]] = {}
        for row in evidence:
            by_claim.setdefault(row["claim_id"], {})[row["id"]] = dict(row)
        out = []
        for row in claims:
            item = dict(row)
            item["object"] = json_value(item.pop("object_json"), None)
            item["qualifiers"] = json_value(item.pop("qualifiers_json"), {})
            item["evidence"] = list(by_claim.get(item["id"], {}).values())
            out.append(item)
        return out

    def source_observations(self, folder: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT s.id,s.name,s.canonical_url,s.publisher_country,
                x.category,x.monitoring_status,x.added_manually,x.metadata_json,
                p.canonical_name AS publisher_name,p.owner_cluster,
                p.verification_status,
                COUNT(DISTINCT d.id) AS document_count,
                MAX(ix.observed_date) AS last_observed
                FROM industry_sources x JOIN sources s ON s.id=x.source_id
                LEFT JOIN source_publishers sp ON sp.source_id=s.id
                LEFT JOIN publishers p ON p.id=sp.publisher_id
                LEFT JOIN documents d ON d.source_id=s.id
                LEFT JOIN industry_documents ix ON ix.document_id=d.id
                    AND ix.industry_id=x.industry_id AND ix.deleted_at IS NULL
                WHERE x.industry_id=? AND x.deleted_at IS NULL
                GROUP BY s.id,x.category ORDER BY x.category,s.name""", (iid,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item.update(json_value(item.pop("metadata_json"), {}))
            item.update({"id": row["id"], "name": row["name"],
                         "url": row["canonical_url"], "category": row["category"],
                         "document_count": int(row["document_count"] or 0),
                         "last_observed": row["last_observed"] or "",
                         "publisher_cluster": row["owner_cluster"] or "unverified",
                         "publisher_verification": row["verification_status"] or "unverified"})
            out.append(item)
        return out

    def source_overlap_stats(self, folder: str) -> dict:
        """Exact normalized-title overlap proxy; no semantic equivalence is claimed."""
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT lower(trim(d.title)) AS title_key,
                COUNT(DISTINCT d.id) AS documents,
                COUNT(DISTINCT COALESCE(p.owner_cluster,s.id)) AS clusters
                FROM industry_documents x JOIN documents d ON d.id=x.document_id
                LEFT JOIN sources s ON s.id=d.source_id
                LEFT JOIN source_publishers sp ON sp.source_id=s.id
                LEFT JOIN publishers p ON p.id=sp.publisher_id
                WHERE x.industry_id=? AND x.deleted_at IS NULL AND trim(d.title)!=''
                GROUP BY lower(trim(d.title))""", (iid,)).fetchall()
        total = sum(int(row["documents"] or 0) for row in rows)
        duplicated = sum(int(row["documents"] or 0) for row in rows
                         if int(row["clusters"] or 0) > 1)
        exclusive = sum(int(row["documents"] or 0) for row in rows
                        if int(row["clusters"] or 0) == 1)
        return {"title_groups": len(rows), "documents": total,
                "cross_cluster_duplicate_documents": duplicated,
                "single_cluster_documents": exclusive,
                "duplicate_rate_proxy": round(duplicated / total, 4) if total else 0.0,
                "exclusive_rate_proxy": round(exclusive / total, 4) if total else 0.0}

    def source_observatory_stats(self, folder: str) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            unique_sources = con.execute("""SELECT COUNT(DISTINCT source_id)
                FROM industry_sources WHERE industry_id=? AND deleted_at IS NULL""",
                (iid,)).fetchone()[0]
            unique_documents = con.execute("""SELECT COUNT(DISTINCT document_id)
                FROM industry_documents WHERE industry_id=? AND deleted_at IS NULL""",
                (iid,)).fetchone()[0]
            rows = con.execute("""SELECT COALESCE((
                    SELECT p.owner_cluster FROM source_publishers sp
                    JOIN publishers p ON p.id=sp.publisher_id WHERE sp.source_id=d.source_id
                    ORDER BY CASE sp.relation WHEN 'original' THEN 0 ELSE 1 END,
                    sp.confidence DESC LIMIT 1),s.id) AS cluster,
                    COUNT(DISTINCT d.id) AS documents
                FROM industry_documents x JOIN documents d ON d.id=x.document_id
                LEFT JOIN sources s ON s.id=d.source_id
                WHERE x.industry_id=? AND x.deleted_at IS NULL GROUP BY cluster""",
                (iid,)).fetchall()
        return {"unique_sources": int(unique_sources or 0),
                "unique_documents": int(unique_documents or 0),
                "documents_by_cluster": {row["cluster"]: int(row["documents"] or 0)
                                         for row in rows}}

    def list_chain_roles(self, folder: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT r.*,n.name AS chain_name,n.position,
                e.canonical_name,e.name_en,e.country
                FROM entity_chain_roles r
                JOIN value_chain_nodes n ON n.id=r.chain_node_id
                JOIN entities e ON e.id=r.entity_id
                WHERE r.industry_id=? AND r.valid_to IS NULL
                ORDER BY n.position,e.canonical_name""", (iid,)).fetchall()
        return [dict(row) for row in rows]

    def upsert_research_agenda(self, folder: str, items: list[dict]) -> list[str]:
        iid = self.industry_id(folder)
        now = utc_now()
        ids = []
        with self.transaction() as con:
            for item in items:
                dimension = str(item["dimension"])
                target_key = str(item["target_key"])
                item_id = stable_id("agd", iid, dimension, target_key)
                ids.append(item_id)
                con.execute("""INSERT INTO research_agenda_items
                    (id,industry_id,dimension,target_key,title,priority,status,rationale,
                     query_json,acceptance_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(industry_id,dimension,target_key) DO UPDATE SET
                    title=excluded.title,priority=excluded.priority,
                    status=CASE WHEN research_agenda_items.status IN ('in_progress','done','dismissed')
                        THEN research_agenda_items.status ELSE excluded.status END,
                    rationale=excluded.rationale,query_json=excluded.query_json,
                    acceptance_json=excluded.acceptance_json,updated_at=excluded.updated_at""",
                    (item_id, iid, dimension, target_key, item["title"],
                     int(item["priority"]), item.get("status", "open"), item["rationale"],
                     json_text(item.get("queries", [])),
                     json_text(item.get("acceptance", {})), now, now))
        return ids

    def reconcile_research_agenda(self, folder: str, active_ids: list[str]) -> int:
        """Mark vanished open gaps as candidates for human resolution."""
        iid = self.industry_id(folder)
        with self.transaction() as con:
            if active_ids:
                marks = ",".join("?" for _ in active_ids)
                cur = con.execute(f"""UPDATE research_agenda_items
                    SET status='resolved_candidate',updated_at=? WHERE industry_id=?
                    AND status='open' AND id NOT IN ({marks})""", [utc_now(), iid, *active_ids])
            else:
                cur = con.execute("""UPDATE research_agenda_items
                    SET status='resolved_candidate',updated_at=? WHERE industry_id=?
                    AND status='open'""", (utc_now(), iid))
        return cur.rowcount

    def update_research_agenda_status(self, folder: str, item_id: str, status: str,
                                      *, actor: str = "app", note: str = "") -> bool:
        allowed = {"open", "in_progress", "done", "dismissed", "resolved_candidate"}
        if status not in allowed:
            raise ValueError(f"未知研究议程状态：{status}")
        iid = self.industry_id(folder)
        with self.transaction() as con:
            previous = con.execute("""SELECT status FROM research_agenda_items
                WHERE industry_id=? AND id=?""", (iid, item_id)).fetchone()
            if not previous:
                return False
            if previous["status"] == status:
                return True
            cur = con.execute("""UPDATE research_agenda_items SET status=?,updated_at=?
                WHERE industry_id=? AND id=?""", (status, utc_now(), iid, item_id))
            if cur.rowcount:
                con.execute("""INSERT INTO research_agenda_history
                    (agenda_id,from_status,to_status,actor,note,occurred_at)
                    VALUES(?,?,?,?,?,?)""", (item_id, previous["status"], status,
                                             actor, note, utc_now()))
                con.execute("""INSERT INTO audit_log
                    (occurred_at,actor,action,object_type,object_id,details_json)
                    VALUES(?,?,?,?,?,?)""", (utc_now(), "app", "agenda_status",
                    "research_agenda", item_id,
                    json_text({"from_status": previous["status"],
                               "status": status, "note": note})))
        return cur.rowcount > 0

    def list_research_agenda_history(self, folder: str, item_id: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT h.* FROM research_agenda_history h
                JOIN research_agenda_items a ON a.id=h.agenda_id
                WHERE a.industry_id=? AND h.agenda_id=?
                ORDER BY h.occurred_at DESC,h.id DESC""", (iid, item_id)).fetchall()
        return [dict(row) for row in rows]

    def create_research_task(self, folder: str, agenda_id: str,
                             budget: int = 20) -> dict:
        iid = self.industry_id(folder)
        budget = max(1, min(500, int(budget)))
        with self.connection() as con:
            row = con.execute("""SELECT * FROM research_agenda_items
                WHERE industry_id=? AND id=?""", (iid, agenda_id)).fetchone()
        if not row:
            raise ValueError("研究议程不存在")
        now = utc_now()
        task_id = stable_id("tsk", iid, agenda_id, now, uuid.uuid4().hex)
        task = {"id": task_id, "industry": folder, "agenda_id": agenda_id,
                "title": row["title"], "rationale": row["rationale"],
                "queries": json_value(row["query_json"], []),
                "acceptance": json_value(row["acceptance_json"], {}),
                "budget": budget,
                "constraints": {"max_documents": budget,
                                "require_citations": True,
                                "write_scope": "task_result_only"},
                "status": "ready", "created_at": now}
        with self.transaction() as con:
            con.execute("""INSERT INTO research_tasks
                (id,industry_id,agenda_id,status,budget,task_json,acceptance_json,
                 created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (task_id, iid, agenda_id, "ready", budget, json_text(task),
                 row["acceptance_json"], now, now))
        return task

    def list_research_tasks(self, folder: str, agenda_id: str = "") -> list[dict]:
        iid = self.industry_id(folder)
        sql = "SELECT * FROM research_tasks WHERE industry_id=?"
        args: list[object] = [iid]
        if agenda_id:
            sql += " AND agenda_id=?"; args.append(agenda_id)
        sql += " ORDER BY created_at DESC,id DESC"
        with self.connection() as con:
            rows = con.execute(sql, args).fetchall()
        out = []
        for row in rows:
            item = json_value(row["task_json"], {})
            item.update({"status": row["status"],
                         "result_artifact_id": row["result_artifact_id"],
                         "run_id": row["run_id"]})
            out.append(item)
        return out

    def complete_research_task(self, folder: str, task_id: str, *,
                               result_artifact_id: str, run_id: str = "") -> bool:
        iid = self.industry_id(folder)
        with self.transaction() as con:
            cur = con.execute("""UPDATE research_tasks SET status='completed',
                result_artifact_id=?,run_id=?,updated_at=?
                WHERE industry_id=? AND id=?""",
                (result_artifact_id, run_id or None, utc_now(), iid, task_id))
        return cur.rowcount > 0

    def list_research_agenda(self, folder: str, *, include_closed: bool = False) -> list[dict]:
        iid = self.industry_id(folder)
        sql = "SELECT * FROM research_agenda_items WHERE industry_id=?"
        if not include_closed:
            sql += " AND status NOT IN ('done','dismissed')"
        sql += " ORDER BY priority DESC,updated_at DESC,id"
        with self.connection() as con:
            rows = con.execute(sql, (iid,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["queries"] = json_value(item.pop("query_json"), [])
            item["acceptance"] = json_value(item.pop("acceptance_json"), {})
            out.append(item)
        return out
