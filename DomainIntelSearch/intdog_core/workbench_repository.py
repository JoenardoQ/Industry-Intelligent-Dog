"""Persistence contracts used by the default Web workbench."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from .models import json_text, json_value, normalized_name, stable_id, utc_now


class WorkbenchRepositoryMixin:
    """Durable automation, coverage and detailed Story reads."""

    def ensure_schedule(self, folder: str, action: str) -> dict:
        if action not in {"daily", "weekly", "monthly", "quarterly"}:
            raise ValueError("不支持的调度动作")
        iid, now = self.industry_id(folder), utc_now()
        with self.transaction() as con:
            con.execute("""INSERT OR IGNORE INTO automation_schedules
                (industry_id,action,enabled,local_time,weekday,monthday,timezone,
                 catch_up,provider,updated_at) VALUES(?,?,0,'08:00',0,1,'Asia/Shanghai',1,'',?)""",
                        (iid, action, now))
        return self.get_schedule(folder, action)

    def get_schedule(self, folder: str, action: str) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            row = con.execute("""SELECT s.*,i.folder FROM automation_schedules s
                JOIN industries i ON i.id=s.industry_id
                WHERE s.industry_id=? AND s.action=?""", (iid, action)).fetchone()
        if row is None:
            return self.ensure_schedule(folder, action)
        return dict(row)

    def list_schedules(self, folder: str | None = None) -> list[dict]:
        args: list[object] = []
        sql = """SELECT s.*,i.folder,i.name AS industry_name
            FROM automation_schedules s JOIN industries i ON i.id=s.industry_id
            WHERE i.status='active'"""
        if folder:
            sql += " AND i.folder=?"; args.append(folder)
        sql += " ORDER BY i.folder,s.action"
        with self.connection() as con:
            rows = [dict(row) for row in con.execute(sql, args)]
        return rows

    def update_schedule(self, folder: str, action: str, *, enabled: bool,
                        local_time: str, weekday: int = 0, monthday: int = 1,
                        timezone_name: str = "Asia/Shanghai",
                        catch_up: bool = True, pipeline_mode: str = "generate",
                        provider: str = "") -> dict:
        if action not in {"daily", "weekly", "monthly", "quarterly"}:
            raise ValueError("不支持的调度动作")
        try:
            hour, minute = (int(value) for value in local_time.split(":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("时间必须是 HH:MM") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("时间必须是 HH:MM")
        if not 0 <= int(weekday) <= 6 or not 1 <= int(monthday) <= 28:
            raise ValueError("星期必须为 0-6，月日期必须为 1-28")
        if pipeline_mode not in {"aggregate", "generate"}:
            raise ValueError("周期模式必须是 aggregate 或 generate")
        if not isinstance(provider, str) or len(provider) > 80:
            raise ValueError("模型提供方式无效")
        iid, now = self.industry_id(folder), utc_now()
        with self.transaction() as con:
            con.execute("""INSERT INTO automation_schedules
                (industry_id,action,enabled,local_time,weekday,monthday,timezone,
                catch_up,pipeline_mode,provider,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(industry_id,action) DO UPDATE SET
                enabled=excluded.enabled,local_time=excluded.local_time,
                weekday=excluded.weekday,monthday=excluded.monthday,
                timezone=excluded.timezone,catch_up=excluded.catch_up,
                pipeline_mode=excluded.pipeline_mode,provider=excluded.provider,
                runtime_status='idle',pause_reason='',
                updated_at=excluded.updated_at""",
                (iid, action, int(enabled), f"{hour:02d}:{minute:02d}", int(weekday),
                 int(monthday), timezone_name, int(catch_up), pipeline_mode,
                 provider, now))
        return self.get_schedule(folder, action)

    def claim_schedule(self, folder: str, action: str, period_key: str,
                       owner: str, *, lease_seconds: int = 3600,
                       period_identity: str | None = None,
                       origin: str = "app") -> bool:
        """Atomically reserve one period before a job is enqueued."""
        iid = self.industry_id(folder)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(30, lease_seconds))
        with self.transaction() as con:
            row = con.execute("""SELECT enabled,last_period_key,last_period_identity,
                attempted_period_key,attempted_period_identity,runtime_status,
                lease_owner,lease_expires_at,retry_after FROM automation_schedules
                WHERE industry_id=? AND action=?""", (iid, action)).fetchone()
            identity = str(period_identity or period_key)
            if (row is None or not row["enabled"] or
                    row["runtime_status"] == "paused" or
                    (row["last_period_identity"] or row["last_period_key"]) == identity):
                return False
            lease = row["lease_expires_at"]
            if lease:
                try:
                    if datetime.fromisoformat(lease.replace("Z", "+00:00")) > now:
                        return False
                except ValueError:
                    pass
            retry_after = row["retry_after"]
            if retry_after:
                try:
                    if datetime.fromisoformat(retry_after.replace("Z", "+00:00")) > now:
                        return False
                except ValueError:
                    pass
            con.execute("""UPDATE automation_schedules SET attempted_period_key=?,
                attempted_period_identity=?,last_attempt_at=?,last_error=NULL,
                runtime_status='running',pause_reason='',last_origin=?,lease_owner=?,
                lease_expires_at=?,retry_after=NULL,updated_at=?
                WHERE industry_id=? AND action=?""",
                (period_key, identity, now.isoformat(timespec="seconds"), origin, owner,
                 expires.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"),
                 iid, action))
        return True

    def set_schedule_next_run(self, folder: str, action: str,
                              next_run_at: str | None) -> None:
        iid = self.industry_id(folder)
        with self.transaction() as con:
            con.execute("""UPDATE automation_schedules SET next_run_at=?,updated_at=?
                WHERE industry_id=? AND action=? AND COALESCE(next_run_at,'')!=COALESCE(?,'')""",
                (next_run_at, utc_now(), iid, action, next_run_at))

    def set_schedule_job(self, folder: str, action: str, owner: str,
                         run_id: str) -> None:
        iid = self.industry_id(folder)
        with self.transaction() as con:
            con.execute("""UPDATE automation_schedules SET last_job_run_id=?,updated_at=?
                WHERE industry_id=? AND action=? AND lease_owner=?""",
                (run_id, utc_now(), iid, action, owner))

    def finish_schedule(self, folder: str, action: str, owner: str, *,
                        success: bool, error: str = "", artifact_path: str = "",
                        outcome: str | None = None, error_category: str = "",
                        successful_boundary: str | None = None,
                        time_window: dict | None = None) -> None:
        iid = self.industry_id(folder)
        timestamp = datetime.now(timezone.utc)
        now = timestamp.isoformat(timespec="seconds")
        with self.transaction() as con:
            row = con.execute("""SELECT attempted_period_key,attempted_period_identity,
                retry_count,max_retries
                FROM automation_schedules WHERE industry_id=? AND action=?
                AND lease_owner=?""", (iid, action, owner)).fetchone()
            if row is None:
                return
            outcome = str(outcome or ("completed" if success else "failed")).casefold()
            if outcome not in {"completed", "partial", "failed", "paused",
                                "cancelled", "interrupted"}:
                raise ValueError("invalid schedule outcome")
            advance = outcome == "completed" and bool(success)
            paused = outcome == "paused"
            retries = (0 if advance else int(row["retry_count"] or 0)
                       if paused else int(row["retry_count"] or 0) + 1)
            exhausted = not advance and not paused and retries >= int(
                row["max_retries"] or 5)
            runtime_status = "paused" if paused or exhausted else outcome
            pause_reason = (str(error)[:1000] if paused else
                            f"retry_exhausted: {str(error)[:950]}" if exhausted else "")
            retry_after = None if advance or paused or exhausted else (
                timestamp + timedelta(minutes=min(60, 2 ** min(retries, 5)))
            ).isoformat(timespec="seconds")
            window = time_window or {}
            con.execute("""UPDATE automation_schedules SET
                last_period_key=CASE WHEN ? THEN attempted_period_key ELSE last_period_key END,
                last_period_identity=CASE WHEN ? THEN attempted_period_identity
                    ELSE last_period_identity END,
                last_success_at=CASE WHEN ? THEN ? ELSE last_success_at END,
                last_success_boundary=CASE WHEN ? THEN ? ELSE last_success_boundary END,
                last_error=?,retry_count=?,retry_after=?,runtime_status=?,pause_reason=?,
                last_window_start=COALESCE(?,last_window_start),
                last_window_end=COALESCE(?,last_window_end),
                last_window_timezone=COALESCE(?,last_window_timezone),
                last_artifact_path=CASE WHEN ?!='' THEN ? ELSE last_artifact_path END,
                lease_owner=NULL,lease_expires_at=NULL,updated_at=?
                WHERE industry_id=? AND action=? AND lease_owner=?""",
                (int(advance), int(advance), int(advance), now,
                 int(advance), successful_boundary or window.get("end") or now,
                 "" if advance else f"{error_category}: {error}".strip(": ")[:1000],
                 retries, retry_after, runtime_status, pause_reason,
                 window.get("start"), window.get("end"), window.get("timezone"),
                 artifact_path, artifact_path, now,
                 iid, action, owner))

    def begin_worker_wakeup(self, owner: str, *, origin: str) -> str:
        wake_id, now = f"wake_{uuid.uuid4().hex}", utc_now()
        with self.transaction() as con:
            con.execute("""INSERT INTO worker_wakeups
                (id,owner,origin,started_at,status,summary_json,error_json)
                VALUES(?,?,?,?,'running','{}','{}')""",
                (wake_id, owner, origin, now))
        return wake_id

    def finish_worker_wakeup(self, wake_id: str, *, status: str,
                             summary: dict, error: dict | None = None) -> None:
        with self.transaction() as con:
            changed = con.execute("""UPDATE worker_wakeups SET status=?,summary_json=?,
                error_json=?,finished_at=? WHERE id=? AND status='running'""",
                (status, json_text(summary), json_text(error or {}), utc_now(),
                 wake_id)).rowcount
            if changed != 1:
                raise RuntimeError("worker wakeup is not running")

    def latest_worker_wakeup(self) -> dict | None:
        with self.connection() as con:
            row = con.execute("""SELECT * FROM worker_wakeups
                ORDER BY started_at DESC,id DESC LIMIT 1""").fetchone()
        if row is None:
            return None
        item = dict(row)
        item["summary"] = json_value(item.pop("summary_json"), {})
        item["error"] = json_value(item.pop("error_json"), {})
        return item

    def upsert_coverage_cell(self, folder: str, dimensions: dict, *,
                             priority: int = 50, status: str = "gap",
                             rationale: str = "") -> str:
        iid = self.industry_id(folder)
        normalized = {key: str(dimensions.get(key) or "unknown").strip()
                      for key in ("region", "subdomain", "chain_stage", "entity_type",
                                  "source_type", "event_type", "time_horizon")}
        cell_id = stable_id("cov", iid, json_text(normalized))
        now = utc_now()
        with self.transaction() as con:
            con.execute("""INSERT INTO coverage_cells
                (id,industry_id,dimensions_json,priority,status,rationale,
                 attempts,source_yield,entity_yield,updated_at,created_at)
                VALUES(?,?,?,?,?,?,0,0,0,?,?) ON CONFLICT(id) DO UPDATE SET
                priority=excluded.priority,status=excluded.status,
                rationale=excluded.rationale,updated_at=excluded.updated_at""",
                (cell_id, iid, json_text(normalized), max(0, min(100, int(priority))),
                 status, rationale, now, now))
        return cell_id

    def record_coverage_attempt(self, folder: str, cell_id: str, *, query: str,
                                rationale: str = "", status: str = "planned",
                                source_yield: int = 0, entity_yield: int = 0,
                                evidence: list | None = None,
                                stopping_reason: str = "") -> str:
        iid, now = self.industry_id(folder), utc_now()
        attempt_id = stable_id("cva", cell_id, query.strip().casefold())
        with self.transaction() as con:
            if con.execute("SELECT 1 FROM coverage_cells WHERE id=? AND industry_id=?",
                           (cell_id, iid)).fetchone() is None:
                raise FileNotFoundError("覆盖单元不存在")
            con.execute("""INSERT INTO coverage_attempts
                (id,cell_id,query,rationale,status,source_yield,entity_yield,
                 evidence_json,stopping_reason,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(cell_id,query) DO UPDATE SET
                rationale=excluded.rationale,status=excluded.status,
                source_yield=excluded.source_yield,entity_yield=excluded.entity_yield,
                evidence_json=excluded.evidence_json,
                stopping_reason=excluded.stopping_reason,updated_at=excluded.updated_at""",
                (attempt_id, cell_id, query.strip(), rationale, status,
                 max(0, int(source_yield)), max(0, int(entity_yield)),
                 json_text(evidence or []), stopping_reason, now, now))
            aggregates = con.execute("""SELECT COUNT(*) AS attempts,
                COALESCE(SUM(source_yield),0) AS sy,COALESCE(SUM(entity_yield),0) AS ey
                FROM coverage_attempts WHERE cell_id=?""", (cell_id,)).fetchone()
            con.execute("""UPDATE coverage_cells SET attempts=?,source_yield=?,
                entity_yield=?,last_attempt_at=?,updated_at=? WHERE id=?""",
                (aggregates["attempts"], aggregates["sy"], aggregates["ey"],
                 now, now, cell_id))
        return attempt_id

    def list_coverage(self, folder: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM coverage_cells WHERE industry_id=?
                ORDER BY CASE status WHEN 'gap' THEN 0 WHEN 'thin' THEN 1 ELSE 2 END,
                priority DESC,updated_at""", (iid,)).fetchall()
        result = []
        for row in rows:
            item = dict(row); item["dimensions"] = json_value(item.pop("dimensions_json"), {})
            result.append(item)
        return result

    def coverage_attempts(self, cell_id: str) -> list[dict]:
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM coverage_attempts WHERE cell_id=?
                ORDER BY created_at DESC""", (cell_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row); item["evidence"] = json_value(item.pop("evidence_json"), [])
            result.append(item)
        return result

    @staticmethod
    def _coverage_round_dict(row) -> dict:
        item = dict(row)
        item["frontier"] = json_value(item.pop("frontier_json"), [])
        item["outcome"] = json_value(item.pop("outcome_json"), {})
        item["log"] = json_value(item.pop("log_json"), [])
        return item

    def create_coverage_round(self, folder: str, frontier) -> dict:
        """Persist a server-generated, full-dimensional entity/relation frontier."""
        iid = self.industry_id(folder)
        cells = [dict(item) for item in getattr(frontier, "cells", [])]
        entity_queries = [dict(item) for item in getattr(frontier, "entity_queries", [])]
        relation_queries = [dict(item) for item in getattr(frontier, "relation_queries", [])]
        now = utc_now()
        with self.transaction() as con:
            round_no = int(con.execute("""SELECT COALESCE(MAX(round_no),0)+1
                FROM coverage_rounds WHERE industry_id=?""", (iid,)).fetchone()[0])
            round_id = stable_id("cvr", iid, round_no)
            con.execute("""INSERT INTO coverage_rounds
                (id,industry_id,round_no,status,frontier_json,outcome_json,log_json,
                 stopping_reason,created_at,updated_at)
                VALUES(?,?,?,'planned',?,'{}','[]','',?,?)""",
                (round_id, iid, round_no, json_text(cells), now, now))
            for kind, queries in (("entity", entity_queries),
                                  ("relation", relation_queries)):
                for query in queries:
                    cell_id = str(query.get("cell_id") or "").strip()
                    text = str(query.get("query") or "").strip()
                    if not cell_id or not text:
                        continue
                    cell = con.execute("""SELECT dimensions_json FROM coverage_cells
                        WHERE id=? AND industry_id=?""", (cell_id, iid)).fetchone()
                    if not cell:
                        raise ValueError("coverage frontier contains a non-persistent cell")
                    dimensions = json_value(cell["dimensions_json"], {})
                    query_id = stable_id("cvq", round_id, kind, cell_id,
                                         text.casefold())
                    con.execute("""INSERT INTO coverage_round_queries
                        (id,round_id,cell_id,kind,language,family,dimensions_json,
                         query,status,outcome_json,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,'{}',?,?)""",
                        (query_id, round_id, cell_id, kind,
                         str(query.get("language") or ""),
                         str(query.get("family") or ""), json_text(dimensions),
                         text, "planned", now, now))
            row = con.execute("SELECT * FROM coverage_rounds WHERE id=?",
                              (round_id,)).fetchone()
            return self._coverage_round_dict(row)

    def start_coverage_round(self, folder: str, round_id: str) -> dict:
        iid = self.industry_id(folder)
        token, now = uuid.uuid4().hex, utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT status FROM coverage_rounds
                WHERE id=? AND industry_id=?""", (round_id, iid)).fetchone()
            if not row:
                raise FileNotFoundError("coverage round not found")
            if row["status"] == "running":
                raise RuntimeError("coverage round is already running")
            if row["status"] not in {"planned", "paused", "failed"}:
                raise ValueError(f"coverage round cannot start from {row['status']}")
            con.execute("""UPDATE coverage_rounds SET status='running',lease_token=?,
                stopping_reason='',updated_at=? WHERE id=? AND status=?""",
                (token, now, round_id, row["status"]))
            started = con.execute("SELECT * FROM coverage_rounds WHERE id=?",
                                  (round_id,)).fetchone()
            return self._coverage_round_dict(started)

    def list_coverage_rounds(self, folder: str) -> list[dict]:
        iid = self.industry_id(folder)
        with self.connection() as con:
            rounds = con.execute("""SELECT * FROM coverage_rounds
                WHERE industry_id=? ORDER BY round_no DESC""", (iid,)).fetchall()
            result = []
            for row in rounds:
                item = self._coverage_round_dict(row)
                item.pop("lease_token", None)
                query_rows = con.execute("""SELECT * FROM coverage_round_queries
                    WHERE round_id=? ORDER BY kind,id""", (row["id"],)).fetchall()
                item["queries"] = []
                for query_row in query_rows:
                    query = dict(query_row)
                    query["dimensions"] = json_value(query.pop("dimensions_json"), {})
                    query["outcome"] = json_value(query.pop("outcome_json"), {})
                    item["queries"].append(query)
                result.append(item)
            return result

    def record_coverage_round_query(self, round_id: str, lease_token: str,
                                    query_id: str, *, status: str,
                                    outcome: dict) -> dict:
        if status not in {"running", "completed", "paused", "failed"}:
            raise ValueError("invalid coverage query status")
        if not isinstance(outcome, dict):
            raise ValueError("coverage query outcome must be an object")
        now = utc_now()
        with self.transaction() as con:
            if not con.execute("""SELECT 1 FROM coverage_rounds
                    WHERE id=? AND status='running' AND lease_token=?""",
                    (round_id, lease_token)).fetchone():
                raise RuntimeError("coverage round lease was lost")
            changed = con.execute("""UPDATE coverage_round_queries
                SET status=?,outcome_json=?,updated_at=? WHERE id=? AND round_id=?""",
                (status, json_text(outcome), now, query_id, round_id)).rowcount
            if changed != 1:
                raise FileNotFoundError("coverage query not found")
            row = con.execute("SELECT * FROM coverage_round_queries WHERE id=?",
                              (query_id,)).fetchone()
        item = dict(row)
        item["dimensions"] = json_value(item.pop("dimensions_json"), {})
        item["outcome"] = json_value(item.pop("outcome_json"), {})
        return item

    def append_coverage_round_log(self, round_id: str, lease_token: str,
                                  message: str, *, level: str = "info") -> None:
        text = " ".join(str(message or "").split()).strip()
        if not text:
            return
        with self.transaction() as con:
            row = con.execute("""SELECT log_json FROM coverage_rounds
                WHERE id=? AND status='running' AND lease_token=?""",
                (round_id, lease_token)).fetchone()
            if not row:
                raise RuntimeError("coverage round lease was lost")
            log = json_value(row["log_json"], [])
            log.append({"at": utc_now(), "level": level, "message": text})
            con.execute("UPDATE coverage_rounds SET log_json=?,updated_at=? WHERE id=?",
                        (json_text(log[-500:]), utc_now(), round_id))

    def upsert_coverage_candidate(self, folder: str, round_id: str,
                                  query_id: str, cell_id: str, *, kind: str,
                                  payload: dict) -> dict:
        if kind not in {"entity", "relation"} or not isinstance(payload, dict):
            raise ValueError("invalid coverage candidate")
        iid, now = self.industry_id(folder), utc_now()
        if kind == "entity":
            name = normalized_name(payload.get("name"))
            entity_type = str(payload.get("type") or payload.get("kind") or "").casefold()
            if not name or not entity_type:
                raise ValueError("entity candidate requires name and type")
            canonical_key = stable_id(
                "entity-candidate-key", entity_type, name,
                str(payload.get("country") or "").casefold(),
                json_text(payload.get("external_ids") or {}))
            table, prefix = "entity_candidates", "enc"
        else:
            relation = str(payload.get("relation") or "").casefold()
            src = str(payload.get("src_node_id") or payload.get("source") or "").strip()
            dst = str(payload.get("dst_node_id") or payload.get("target") or "").strip()
            if not relation or not src or not dst:
                raise ValueError("relation candidate requires source, target and relation")
            canonical_key = stable_id("relation-candidate-key", src, relation, dst)
            table, prefix = "relation_candidates", "rlc"
        candidate_id = stable_id(prefix, iid, canonical_key, cell_id)
        with self.transaction() as con:
            query = con.execute("""SELECT q.kind,r.industry_id FROM coverage_round_queries q
                JOIN coverage_rounds r ON r.id=q.round_id
                WHERE q.id=? AND q.round_id=? AND q.cell_id=?""",
                (query_id, round_id, cell_id)).fetchone()
            if not query or query["industry_id"] != iid or query["kind"] != kind:
                raise ValueError("coverage candidate provenance is invalid")
            if kind == "entity":
                con.execute("""INSERT INTO entity_candidates
                    (id,industry_id,round_id,query_id,cell_id,canonical_key,payload_json,
                     status,status_reason,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,'candidate','',?,?)
                    ON CONFLICT(industry_id,canonical_key,cell_id) DO UPDATE SET
                    query_id=excluded.query_id,round_id=excluded.round_id,
                    payload_json=CASE WHEN entity_candidates.status='candidate'
                        THEN excluded.payload_json ELSE entity_candidates.payload_json END,
                    updated_at=excluded.updated_at""",
                    (candidate_id, iid, round_id, query_id, cell_id, canonical_key,
                     json_text(payload), now, now))
            else:
                con.execute("""INSERT INTO relation_candidates
                    (id,industry_id,round_id,query_id,cell_id,canonical_key,payload_json,
                     document_id,assertion_id,status,status_reason,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,'candidate','',?,?)
                    ON CONFLICT(industry_id,canonical_key,cell_id) DO UPDATE SET
                    query_id=excluded.query_id,round_id=excluded.round_id,
                    payload_json=CASE WHEN relation_candidates.status='candidate'
                        THEN excluded.payload_json ELSE relation_candidates.payload_json END,
                    document_id=COALESCE(excluded.document_id,relation_candidates.document_id),
                    assertion_id=COALESCE(excluded.assertion_id,relation_candidates.assertion_id),
                    updated_at=excluded.updated_at""",
                    (candidate_id, iid, round_id, query_id, cell_id, canonical_key,
                     json_text(payload), payload.get("document_id"),
                     payload.get("assertion_id"), now, now))
            row = con.execute(f"SELECT * FROM {table} WHERE id=?", (candidate_id,)).fetchone()
        result = dict(row); result["payload"] = json_value(result.pop("payload_json"), {})
        return result

    def finish_coverage_round(self, round_id: str, lease_token: str,
                              outcome: dict, *, status: str = "completed",
                              stopping_reason: str = "") -> dict:
        if status not in {"completed", "paused", "converged", "failed"}:
            raise ValueError("invalid coverage round terminal status")
        now = utc_now()
        with self.transaction() as con:
            changed = con.execute("""UPDATE coverage_rounds SET status=?,outcome_json=?,
                stopping_reason=?,updated_at=?
                WHERE id=? AND status='running' AND lease_token=?""",
                (status, json_text(outcome), stopping_reason, now,
                 round_id, lease_token)).rowcount
            if changed != 1:
                raise RuntimeError("coverage round lease was lost")
            row = con.execute("SELECT * FROM coverage_rounds WHERE id=?", (round_id,)).fetchone()
            self._insert_quality_observation(con, row["industry_id"], {
                "observed_at": now, "metric": "chain_node_coverage_change",
                "numerator": float(outcome.get("qualified_gain") or 0),
                "denominator": max(1, int(outcome.get("coverage_units") or 0)),
                "algorithm_version": "entity-coverage-v1",
                "dimensions": {"round_id": round_id, "status": status},
            })
            return self._coverage_round_dict(row)

    def list_coverage_review_queue(self, folder: str) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            entity_rows = con.execute("""SELECT * FROM entity_candidates
                WHERE industry_id=? AND status IN ('candidate','manual_review')
                ORDER BY updated_at DESC""", (iid,)).fetchall()
            relation_rows = con.execute("""SELECT * FROM relation_candidates
                WHERE industry_id=? AND status IN ('candidate','manual_review')
                ORDER BY updated_at DESC""", (iid,)).fetchall()
        def decode(rows):
            output = []
            for row in rows:
                item = dict(row); item["payload"] = json_value(item.pop("payload_json"), {})
                output.append(item)
            return output
        return {"entities": decode(entity_rows), "relations": decode(relation_rows)}

    def get_coverage_candidate(self, folder: str, candidate_id: str, *,
                               kind: str) -> dict:
        if kind not in {"entity", "relation"}:
            raise ValueError("invalid coverage candidate kind")
        iid = self.industry_id(folder)
        table = "entity_candidates" if kind == "entity" else "relation_candidates"
        with self.connection() as con:
            row = con.execute(f"SELECT * FROM {table} WHERE id=? AND industry_id=?",
                              (candidate_id, iid)).fetchone()
        if not row:
            raise FileNotFoundError("coverage candidate not found")
        item = dict(row); item["payload"] = json_value(item.pop("payload_json"), {})
        return item

    def review_coverage_candidate(self, folder: str, candidate_id: str, *, kind: str,
                                  decision: str, actor: str, reason: str,
                                  entity_id: str | None = None) -> dict:
        if kind not in {"entity", "relation"}:
            raise ValueError("invalid coverage candidate kind")
        target = {"approve": "accepted", "accepted": "accepted",
                  "manual_review": "manual_review", "rejected": "rejected"}.get(
                      str(decision or "").casefold())
        if not target:
            raise ValueError("invalid coverage candidate decision")
        normalized_actor = " ".join(str(actor or "").split()).strip()
        normalized_reason = " ".join(str(reason or "").split()).strip()
        if not normalized_actor or not normalized_reason:
            raise ValueError("coverage review actor and reason are required")
        iid, now = self.industry_id(folder), utc_now()
        table = "entity_candidates" if kind == "entity" else "relation_candidates"
        with self.transaction() as con:
            row = con.execute(f"SELECT * FROM {table} WHERE id=? AND industry_id=?",
                              (candidate_id, iid)).fetchone()
            if not row:
                raise FileNotFoundError("coverage candidate not found")
            current = row["status"]
            if current in {"accepted", "rejected"}:
                raise ValueError("coverage candidate review is terminal")
            if kind == "entity" and target == "accepted" and not entity_id:
                raise ValueError("accepted entity candidate requires materialized entity")
            if kind == "relation" and target == "accepted":
                valid_document = bool(row["document_id"] and con.execute("""
                    SELECT 1 FROM industry_documents WHERE industry_id=?
                    AND document_id=? AND deleted_at IS NULL""",
                    (iid, row["document_id"])).fetchone())
                valid_assertion = bool(row["assertion_id"] and con.execute("""
                    SELECT 1 FROM agent_assertions a JOIN agent_results r ON r.id=a.result_id
                    JOIN claims c ON c.id=a.claim_id WHERE a.id=? AND r.industry_id=?
                    AND a.status='accepted' AND c.industry_id=? AND c.status='accepted'""",
                    (row["assertion_id"], iid, iid)).fetchone())
                if not valid_document and not valid_assertion:
                    raise ValueError("accepted relation candidate requires current-industry evidence")
            snapshot = dict(row)
            changed = con.execute(f"""UPDATE {table} SET status=?,status_reason=?,
                {"entity_id=? ," if kind == "entity" else ""} updated_at=?
                WHERE id=? AND status=?""",
                ((target, normalized_reason, entity_id, now, candidate_id, current)
                 if kind == "entity" else
                 (target, normalized_reason, now, candidate_id, current))).rowcount
            if changed != 1:
                raise RuntimeError("coverage candidate changed concurrently")
            con.execute("""INSERT INTO coverage_candidate_reviews
                (candidate_kind,candidate_id,from_status,to_status,actor,reason,
                 snapshot_json,occurred_at) VALUES(?,?,?,?,?,?,?,?)""",
                (kind, candidate_id, current, target, normalized_actor,
                 normalized_reason, json_text(snapshot), now))
            if kind == "relation" and target == "accepted":
                payload = json_value(row["payload_json"], {})
                src = str(payload.get("source") or payload.get("src_entity_id") or "")
                dst = str(payload.get("target") or payload.get("dst_entity_id") or "")
                predicate = str(payload.get("relation") or payload.get("predicate") or "")
                membership_count = con.execute("""SELECT COUNT(DISTINCT entity_id)
                    FROM industry_entities WHERE industry_id=? AND entity_id IN (?,?)""",
                    (iid, src, dst)).fetchone()[0]
                if membership_count != 2 or not predicate:
                    raise ValueError("accepted relation endpoints are not current-industry entities")
                relation_id = stable_id(
                    "rel", iid, src, predicate, dst, payload.get("valid_from") or "")
                evidence = ({"kind": "document", "id": row["document_id"]}
                            if valid_document else
                            {"kind": "assertion", "id": row["assertion_id"]})
                con.execute("""INSERT INTO relations
                    (id,src_entity_id,predicate,dst_entity_id,industry_id,valid_from,valid_to,
                     confidence,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET valid_to=excluded.valid_to,
                    confidence=excluded.confidence,metadata_json=excluded.metadata_json""",
                    (relation_id, src, predicate, dst, iid,
                     payload.get("valid_from") or None, payload.get("valid_to") or None,
                     payload.get("confidence"), json_text({
                         "review_candidate_id": candidate_id, "evidence": [evidence],
                         "derived_evidence_count": 1,
                     })))
        return self.get_coverage_candidate(folder, candidate_id, kind=kind)

    def story_detail(self, folder: str, story_id: str) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            story = con.execute("SELECT * FROM stories WHERE id=? AND industry_id=?",
                                (story_id, iid)).fetchone()
            if story is None:
                raise FileNotFoundError("Story 不存在")
            documents = con.execute("""SELECT d.id,d.title,d.canonical_url AS url,
                d.abstract,d.published_at,d.origin,x.category,x.observed_date,
                sd.relation,sd.publisher_cluster,
                CASE WHEN ec.document_id IS NULL THEN 0 ELSE 1 END AS editorially_locked
                FROM story_documents sd JOIN documents d ON d.id=sd.document_id
                JOIN industry_documents x ON x.document_id=d.id AND x.industry_id=?
                LEFT JOIN story_editorial_constraints ec ON ec.industry_id=x.industry_id
                    AND ec.document_id=d.id AND ec.story_id=sd.story_id
                WHERE sd.story_id=? AND x.deleted_at IS NULL
                ORDER BY COALESCE(d.published_at,x.observed_date),d.id""",
                (iid, story_id)).fetchall()
            reviews = con.execute("""SELECT action,actor,details_json,occurred_at
                FROM story_reviews WHERE story_id=? ORDER BY occurred_at""",
                (story_id,)).fetchall()
            claims = con.execute("""SELECT DISTINCT c.* FROM claims c
                JOIN evidence e ON e.claim_id=c.id JOIN story_documents sd
                    ON sd.document_id=e.document_id
                WHERE c.industry_id=? AND sd.story_id=? AND c.superseded_at IS NULL
                ORDER BY c.updated_at DESC""", (iid, story_id)).fetchall()
        item = dict(story); item["metadata"] = json_value(item.pop("metadata_json"), {})
        item["documents"] = [dict(row) for row in documents]
        item["document_count"] = len(documents)
        publishers = {row["publisher_cluster"] for row in documents
                      if row["publisher_cluster"]}
        item["publisher_count"] = len(publishers)
        item["corroborated"] = len(publishers) >= 2
        item["reviews"] = [{**dict(row), "details": json_value(row["details_json"], {})}
                           for row in reviews]
        for review in item["reviews"]:
            review.pop("details_json", None)
        item["claims"] = []
        with self.connection() as con:
            for row in claims:
                claim = dict(row)
                claim["object"] = json_value(claim.pop("object_json"), None)
                claim["qualifiers"] = json_value(claim.pop("qualifiers_json"), {})
                claim["evidence"] = [dict(value) for value in con.execute("""SELECT
                    e.relation,e.excerpt,e.publisher_cluster,d.title AS document_title,
                    d.canonical_url AS document_url FROM evidence e
                    LEFT JOIN documents d ON d.id=e.document_id WHERE e.claim_id=?
                    ORDER BY e.created_at""", (claim["id"],))]
                item["claims"].append(claim)
        return item

    def unlock_story_documents(self, folder: str, story_id: str,
                               document_ids: list[str], actor: str = "web") -> int:
        iid, now = self.industry_id(folder), utc_now()
        if not document_ids:
            raise ValueError("请选择要解除审核锁的文档")
        marks = ",".join("?" for _ in document_ids)
        with self.transaction() as con:
            cur = con.execute(f"""DELETE FROM story_editorial_constraints
                WHERE industry_id=? AND story_id=? AND document_id IN ({marks})""",
                [iid, story_id, *document_ids])
            con.execute("""INSERT INTO story_reviews
                (story_id,action,actor,details_json,occurred_at) VALUES(?,?,?,?,?)""",
                (story_id, "unlock", actor,
                 json_text({"document_ids": document_ids, "removed": cur.rowcount}), now))
            self._insert_quality_observation(con, iid, {
                "observed_at": now, "metric": "manual_correction_rate",
                "numerator": 1, "denominator": 1,
                "algorithm_version": "story-editorial-v1",
                "dimensions": {"action": "unlock"},
            })
        return cur.rowcount

    def restore_industry_record(self, folder: str, name: str = "") -> None:
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("SELECT id,name FROM industries WHERE folder=?", (folder,)).fetchone()
            if row is None:
                raise FileNotFoundError("归档行业注册记录不存在")
            con.execute("""UPDATE industries SET status='active',
                name=CASE WHEN ?!='' THEN ? ELSE name END,updated_at=? WHERE folder=?""",
                (name, name, now, folder))
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,?,?,?,?,?)""",
                (now, "web", "restore", "industry", row["id"],
                 json_text({"folder": folder})))

    def audit(self, action: str, object_type: str, *, object_id: str = "",
              details: dict | None = None, actor: str = "web") -> None:
        with self.transaction() as con:
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,?,?,?,?,?)""",
                (utc_now(), actor, action, object_type, object_id or None,
                 json_text(details or {})))

    def page_knowledge_entities(self, folder: str, *, query: str = "",
                                kind: str = "", country: str = "", status: str = "",
                                chain: str = "", offset: int = 0,
                                limit: int = 50) -> dict:
        """Bounded, filterable access to the complete active industry entity set."""
        iid = self.industry_id(folder)
        limit, offset = max(1, min(100, int(limit))), max(0, int(offset))
        where = ["x.industry_id=?", "x.status!='deleted'",
                 "e.kind!='supply_chain_activity'"]
        args: list[object] = [iid]
        if query.strip():
            token = f"%{query.strip()}%"
            where.append("""(e.canonical_name LIKE ? OR e.name_en LIKE ? OR EXISTS(
                SELECT 1 FROM entity_aliases a WHERE a.entity_id=e.id AND a.alias LIKE ?))""")
            args.extend([token, token, token])
        for column, value in (("e.kind", kind), ("e.country", country),
                              ("x.status", status), ("x.chain_name", chain)):
            if value:
                where.append(f"{column}=?"); args.append(value)
        clause = " AND ".join(where)
        with self.connection() as con:
            total = con.execute(f"""SELECT COUNT(*) FROM industry_entities x
                JOIN entities e ON e.id=x.entity_id WHERE {clause}""", args).fetchone()[0]
            rows = con.execute(f"""SELECT e.id,e.kind,e.canonical_name AS name,e.name_en,
                e.country,x.role,x.chain_name AS chain,x.status,x.confidence
                FROM industry_entities x JOIN entities e ON e.id=x.entity_id
                WHERE {clause} ORDER BY x.chain_name,e.canonical_name,e.id
                LIMIT ? OFFSET ?""", [*args, limit, offset]).fetchall()
        return {"items": [dict(row) for row in rows], "total": int(total),
                "offset": offset, "limit": limit,
                "next_offset": offset + len(rows) if offset + len(rows) < total else None}

    def knowledge_entity_detail(self, folder: str, entity_id: str) -> dict:
        iid = self.industry_id(folder)
        with self.connection() as con:
            entity = con.execute("""SELECT e.*,x.role,x.chain_name AS chain,x.status,
                x.confidence,x.metadata_json AS membership_json
                FROM entities e JOIN industry_entities x ON x.entity_id=e.id
                WHERE x.industry_id=? AND x.entity_id=? AND x.status!='deleted'
                ORDER BY x.chain_name LIMIT 1""", (iid, entity_id)).fetchone()
            if entity is None:
                raise FileNotFoundError("实体不存在")
            aliases = [dict(row) for row in con.execute("""SELECT alias,language,valid_from,
                valid_to FROM entity_aliases WHERE entity_id=? ORDER BY alias""",
                (entity_id,))]
            roles = [dict(row) for row in con.execute("""SELECT r.role,n.name AS chain,
                r.valid_from,r.valid_to,r.status,r.confidence,r.evidence_count
                FROM entity_chain_roles r JOIN value_chain_nodes n ON n.id=r.chain_node_id
                WHERE r.industry_id=? AND r.entity_id=? ORDER BY n.position,r.role""",
                (iid, entity_id))]
            relations = [dict(row) for row in con.execute("""SELECT r.id,r.predicate,
                r.src_entity_id,r.dst_entity_id,s.canonical_name AS src_name,
                d.canonical_name AS dst_name,r.valid_from,r.valid_to,r.confidence
                FROM relations r JOIN entities s ON s.id=r.src_entity_id
                JOIN entities d ON d.id=r.dst_entity_id WHERE r.industry_id=? AND
                (r.src_entity_id=? OR r.dst_entity_id=?) ORDER BY r.predicate LIMIT 200""",
                (iid, entity_id, entity_id))]
        item = dict(entity)
        item["metadata"] = json_value(item.pop("metadata_json"), {})
        item["membership"] = json_value(item.pop("membership_json"), {})
        item["aliases"], item["roles"], item["relations"] = aliases, roles, relations
        claims = [claim for claim in self.list_claim_evidence(folder)
                  if claim.get("subject_id") == entity_id]
        item["claims"] = claims
        item["evidence_count"] = sum(len(claim.get("evidence") or []) for claim in claims)
        return item

    def list_audits(self, *, folder: str = "", limit: int = 100) -> list[dict]:
        args: list[object] = []
        sql = "SELECT * FROM audit_log"
        if folder:
            iid = self.industry_id(folder)
            sql += " WHERE object_id=? OR details_json LIKE ?"
            args.extend([iid, f'%"folder":"{folder}"%'])
        sql += " ORDER BY occurred_at DESC,id DESC LIMIT ?"; args.append(max(1, min(500, limit)))
        with self.connection() as con:
            rows = con.execute(sql, args).fetchall()
        result = []
        for row in rows:
            item = dict(row); item["details"] = json_value(item.pop("details_json"), {})
            result.append(item)
        return result
