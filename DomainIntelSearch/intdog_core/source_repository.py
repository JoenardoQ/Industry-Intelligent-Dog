"""Transactional persistence for source-discovery campaigns and review history."""

from __future__ import annotations

import json
import math
import sqlite3
import uuid

from .models import canonical_url, json_text, json_value, stable_id, utc_now
from .source_trust import publisher_profile


CAMPAIGN_TRANSITIONS = {
    "planned": {"running"},
    "running": {"paused", "converged", "failed"},
    "paused": {"running", "failed"},
    "converged": set(),
    "failed": set(),
}

CANDIDATE_TRANSITIONS = {
    "candidate": {"manual_review", "active", "reserve", "rejected"},
    "manual_review": {"active", "reserve", "rejected"},
    "active": {"reserve", "rejected"},
    "reserve": {"manual_review", "active", "rejected"},
    "rejected": set(),
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, default=str)


def _required_text(value: object, field: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text


def _immutable_candidate_payload(item: dict) -> str:
    normalized = dict(item)
    normalized.pop("query_id", None)
    normalized.pop("query_ids", None)
    normalized["url"] = canonical_url(normalized.get("url", ""))
    return _canonical_json(normalized)


class SourceRepositoryMixin:
    """Repository methods mixed into :class:`IntelligenceRepository`."""

    @staticmethod
    def _campaign_dict(row: sqlite3.Row) -> dict:
        item = dict(row)
        item["targets"] = json_value(item.pop("targets_json", "[]"), [])
        item["rounds"] = int(item.get("rounds") or 0)
        item["budget"] = int(item.get("budget") or 0)
        return item

    def create_source_campaign(self, folder: str, targets: list[str], budget: int) -> dict:
        if not isinstance(targets, list):
            raise ValueError("targets must be a non-empty list")
        normalized_targets: list[str] = []
        seen: set[str] = set()
        for value in targets:
            target = " ".join(str(value or "").split()).strip().casefold()
            if target and target not in seen:
                normalized_targets.append(target)
                seen.add(target)
        if not normalized_targets:
            raise ValueError("targets must be a non-empty list")
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise ValueError("budget must be a positive integer")

        industry_id = self.industry_id(folder)
        now = utc_now()
        campaign_id = stable_id(
            "scp", industry_id, now, uuid.uuid4().hex)
        with self.transaction() as con:
            con.execute("""INSERT INTO source_campaigns
                (id,industry_id,targets_json,status,rounds,budget,stopping_reason,
                 created_at,updated_at) VALUES(?,?,?,'planned',0,?,'',?,?)""",
                        (campaign_id, industry_id, _canonical_json(normalized_targets),
                         budget, now, now))
        return self.get_source_campaign(campaign_id)

    def get_source_campaign(self, campaign_id: str) -> dict:
        with self.connection() as con:
            row = con.execute(
                "SELECT * FROM source_campaigns WHERE id=?", (campaign_id,)).fetchone()
        if not row:
            raise FileNotFoundError(f"source campaign not found: {campaign_id}")
        return self._campaign_dict(row)

    def list_source_campaigns(self, folder: str) -> list[dict]:
        industry_id = self.industry_id(folder)
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM source_campaigns
                WHERE industry_id=? ORDER BY created_at DESC,id""",
                               (industry_id,)).fetchall()
        return [self._campaign_dict(row) for row in rows]

    def transition_source_campaign(self, campaign_id: str, status: str, *,
                                   reason: str = "") -> dict:
        target = str(status or "").strip().casefold()
        if target not in CAMPAIGN_TRANSITIONS:
            raise ValueError(f"unknown source campaign status: {status}")
        normalized_reason = " ".join(str(reason or "").split()).strip()
        if target in {"paused", "converged", "failed"} and not normalized_reason:
            raise ValueError(f"{target} source campaign requires reason")

        with self.transaction() as con:
            row = con.execute(
                "SELECT status FROM source_campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not row:
                raise FileNotFoundError(f"source campaign not found: {campaign_id}")
            current = str(row["status"])
            if target == current:
                return self.get_source_campaign(campaign_id)
            if target not in CAMPAIGN_TRANSITIONS[current]:
                raise ValueError(
                    f"invalid source campaign transition: {current} -> {target}")
            now = utc_now()
            stopping_reason = normalized_reason if target != "running" else ""
            changed = con.execute("""UPDATE source_campaigns
                SET status=?,stopping_reason=?,updated_at=?
                WHERE id=? AND status=?""",
                                  (target, stopping_reason, now, campaign_id,
                                   current)).rowcount
            if changed != 1:
                raise RuntimeError("source campaign changed concurrently")
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,'source-campaign-state-machine','source_campaign_transition',
                       'source_campaign',?,?)""",
                        (now, campaign_id, json_text({
                            "from_status": current,
                            "to_status": target,
                            "reason": stopping_reason,
                        })))
        return self.get_source_campaign(campaign_id)

    def record_source_query(self, campaign_id: str, *, round_no: int,
                            language: str, family: str, dimensions: dict,
                            query: str, outcome: dict) -> dict:
        if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no <= 0:
            raise ValueError("round_no must be a positive integer")
        normalized_language = _required_text(language, "language")
        normalized_family = _required_text(family, "family")
        normalized_query = _required_text(query, "query")
        if not isinstance(dimensions, dict):
            raise ValueError("dimensions must be an object")
        if not isinstance(outcome, dict):
            raise ValueError("outcome must be an object")
        dimensions_json = _canonical_json(dimensions)
        outcome_json = _canonical_json(outcome)
        query_id = stable_id(
            "sqy", campaign_id, round_no, normalized_language.casefold(),
            normalized_family.casefold(), dimensions_json,
            normalized_query.casefold())
        now = utc_now()

        with self.transaction() as con:
            campaign = con.execute(
                "SELECT status FROM source_campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not campaign:
                raise FileNotFoundError(f"source campaign not found: {campaign_id}")
            if campaign["status"] != "running":
                raise ValueError("source queries require a running campaign")
            con.execute("""INSERT INTO source_queries
                (id,campaign_id,round_no,language,family,dimensions_json,query,
                 outcome_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET outcome_json=excluded.outcome_json""",
                        (query_id, campaign_id, round_no, normalized_language,
                         normalized_family, dimensions_json, normalized_query,
                         outcome_json, now))
            row = con.execute(
                "SELECT * FROM source_queries WHERE id=?", (query_id,)).fetchone()
        item = dict(row)
        item["dimensions"] = json_value(item.pop("dimensions_json"), {})
        item["outcome"] = json_value(item.pop("outcome_json"), {})
        return item

    @staticmethod
    def _round_dict(row: sqlite3.Row) -> dict:
        item = dict(row)
        item["plan"] = json_value(item.pop("plan_json"), [])
        item["frontier"] = json_value(item.pop("frontier_json"), [])
        item["outcome"] = json_value(item.pop("outcome_json"), {})
        item["log"] = json_value(item.pop("log_json"), [])
        return item

    def begin_source_campaign_round(self, campaign_id: str, *, plan: list[dict],
                                    frontier: list[dict]) -> dict:
        if not isinstance(plan, list) or not isinstance(frontier, list):
            raise ValueError("campaign round plan/frontier must be lists")
        token = uuid.uuid4().hex
        now = utc_now()
        with self.transaction() as con:
            campaign = con.execute("""SELECT status,rounds FROM source_campaigns
                WHERE id=?""", (campaign_id,)).fetchone()
            if not campaign:
                raise FileNotFoundError(f"source campaign not found: {campaign_id}")
            if campaign["status"] != "running":
                raise ValueError("source campaign round requires a running campaign")
            round_no = int(campaign["rounds"]) + 1
            existing = con.execute("""SELECT * FROM source_campaign_rounds
                WHERE campaign_id=? AND round_no=?""",
                (campaign_id, round_no)).fetchone()
            if existing and existing["status"] == "running":
                raise RuntimeError("source campaign round is already running")
            round_id = stable_id("scr", campaign_id, round_no)
            if existing:
                con.execute("""UPDATE source_campaign_rounds SET status='running',
                    lease_token=?,plan_json=?,frontier_json=?,updated_at=?
                    WHERE id=? AND status IN ('paused','failed')""",
                    (token, _canonical_json(plan), _canonical_json(frontier), now,
                     existing["id"]))
                round_id = existing["id"]
            else:
                con.execute("""INSERT INTO source_campaign_rounds
                    (id,campaign_id,round_no,status,lease_token,plan_json,frontier_json,
                     outcome_json,log_json,started_at,updated_at)
                    VALUES(?,?,?,'running',?,?,?,'{}','[]',?,?)""",
                    (round_id, campaign_id, round_no, token,
                     _canonical_json(plan), _canonical_json(frontier), now, now))
            row = con.execute("SELECT * FROM source_campaign_rounds WHERE id=?",
                              (round_id,)).fetchone()
            return self._round_dict(row)

    def append_source_campaign_log(self, round_id: str, lease_token: str,
                                   message: str, *, level: str = "info") -> None:
        normalized = _required_text(message, "message")
        with self.transaction() as con:
            row = con.execute("""SELECT log_json FROM source_campaign_rounds
                WHERE id=? AND status='running' AND lease_token=?""",
                (round_id, lease_token)).fetchone()
            if not row:
                raise RuntimeError("source campaign round lease was lost")
            log = json_value(row["log_json"], [])
            log.append({"at": utc_now(), "level": str(level),
                        "message": normalized})
            con.execute("UPDATE source_campaign_rounds SET log_json=?,updated_at=? WHERE id=?",
                        (_canonical_json(log[-500:]), utc_now(), round_id))

    def finish_source_campaign_round(self, round_id: str, lease_token: str,
                                     outcome: dict) -> dict:
        if not isinstance(outcome, dict):
            raise ValueError("campaign round outcome must be an object")
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT campaign_id,round_no FROM source_campaign_rounds
                WHERE id=? AND status='running' AND lease_token=?""",
                (round_id, lease_token)).fetchone()
            if not row:
                raise RuntimeError("source campaign round lease was lost")
            changed = con.execute("""UPDATE source_campaign_rounds
                SET status='completed',outcome_json=?,finished_at=?,updated_at=?
                WHERE id=? AND status='running' AND lease_token=?""",
                (_canonical_json(outcome), now, now, round_id, lease_token)).rowcount
            campaign_changed = con.execute("""UPDATE source_campaigns SET rounds=?,updated_at=?
                WHERE id=? AND status='running' AND rounds=?""",
                (row["round_no"], now, row["campaign_id"], row["round_no"] - 1)).rowcount
            if changed != 1 or campaign_changed != 1:
                raise RuntimeError("source campaign round changed concurrently")
            completed = con.execute("SELECT * FROM source_campaign_rounds WHERE id=?",
                                    (round_id,)).fetchone()
            return self._round_dict(completed)

    def pause_source_campaign_round(self, round_id: str, lease_token: str,
                                    reason: str) -> dict:
        normalized = _required_text(reason, "reason")
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT campaign_id FROM source_campaign_rounds
                WHERE id=? AND status='running' AND lease_token=?""",
                (round_id, lease_token)).fetchone()
            if not row:
                raise RuntimeError("source campaign round lease was lost")
            con.execute("""UPDATE source_campaign_rounds SET status='paused',
                outcome_json=?,updated_at=? WHERE id=? AND lease_token=?""",
                (_canonical_json({"stopping_reason": normalized}), now,
                 round_id, lease_token))
            con.execute("""UPDATE source_campaigns SET status='paused',stopping_reason=?,
                updated_at=? WHERE id=? AND status='running'""",
                (normalized, now, row["campaign_id"]))
            paused = con.execute("SELECT * FROM source_campaign_rounds WHERE id=?",
                                 (round_id,)).fetchone()
            return self._round_dict(paused)

    def list_source_campaign_rounds(self, campaign_id: str) -> list[dict]:
        with self.connection() as con:
            rows = con.execute("""SELECT * FROM source_campaign_rounds
                WHERE campaign_id=? ORDER BY round_no""", (campaign_id,)).fetchall()
        result = [self._round_dict(row) for row in rows]
        for item in result:
            item.pop("lease_token", None)
        return result

    @staticmethod
    def _query_ids(item: dict) -> list[str]:
        values: list[object] = []
        if item.get("query_id") is not None:
            values.append(item["query_id"])
        supplied = item.get("query_ids", [])
        if supplied is not None:
            if not isinstance(supplied, list):
                raise ValueError("query_ids must be a list")
            values.extend(supplied)
        query_ids = sorted({_required_text(value, "query_id") for value in values})
        if not query_ids:
            raise ValueError("query_id provenance is required")
        return query_ids

    @staticmethod
    def _candidate_dict(row: sqlite3.Row, query_ids: list[str]) -> dict:
        attributes = json_value(row["attributes_json"], {})
        item = dict(attributes) if isinstance(attributes, dict) else {}
        item.update({
            "id": row["id"],
            "campaign_id": row["campaign_id"],
            "canonical_url": row["canonical_url"],
            "url": row["canonical_url"],
            "source_id": row["source_id"],
            "publisher_id": row["publisher_id"],
            "publisher_name": row["publisher_name"],
            "publisher_owner_cluster": row["owner_cluster"],
            "publisher_verification": row["verification_status"],
            "name": row["name"],
            "category": row["category"],
            "ownership": json_value(row["ownership_json"], {}),
            "score": float(row["score"]),
            "status": row["status"],
            "selection_reason": row["selection_reason"],
            "status_reason": row["status_reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "query_ids": sorted(query_ids),
        })
        return item

    @staticmethod
    def _candidate_select() -> str:
        return """SELECT c.*,p.canonical_name AS publisher_name,p.owner_cluster,
            p.verification_status FROM source_candidates c
            JOIN publishers p ON p.id=c.publisher_id"""

    def _candidate_from_connection(self, con: sqlite3.Connection,
                                   candidate_id: str) -> dict:
        row = con.execute(
            self._candidate_select() + " WHERE c.id=?", (candidate_id,)).fetchone()
        if not row:
            raise FileNotFoundError(f"source candidate not found: {candidate_id}")
        query_ids = [query_row[0] for query_row in con.execute(
            """SELECT query_id FROM source_candidate_queries
            WHERE candidate_id=? ORDER BY query_id""", (candidate_id,))]
        return self._candidate_dict(row, query_ids)

    def upsert_source_candidate(self, campaign_id: str, item: dict) -> dict:
        if not isinstance(item, dict):
            raise ValueError("source candidate must be an object")
        url = canonical_url(item.get("url", ""))
        if not url:
            raise ValueError("source candidate requires a valid http/https URL")
        query_ids = self._query_ids(item)
        requested_status = str(item.get("status") or item.get("selection_status")
                               or "candidate").strip().casefold()
        if requested_status != "candidate":
            raise ValueError("new source candidates must start in candidate status")
        raw_score = item.get("score", 0.0)
        if isinstance(raw_score, bool):
            raise ValueError("score must be a finite number")
        try:
            score = float(raw_score)
        except (TypeError, ValueError) as exc:
            raise ValueError("score must be a finite number") from exc
        if not math.isfinite(score):
            raise ValueError("score must be a finite number")

        profile = publisher_profile({**item, "url": url})
        publisher_id = stable_id("pub", profile["owner_cluster"])
        candidate_id = stable_id("src-candidate", campaign_id, url)
        name = " ".join(str(item.get("name") or url).split()).strip()
        category = " ".join(str(item.get("category") or
                                 item.get("source_type") or "uncategorized").split()).strip()
        ownership = item.get("ownership", {})
        if not isinstance(ownership, dict):
            ownership = {"reported_owner": str(ownership)}
        ownership_json = _canonical_json(ownership)
        attributes_json = _canonical_json(item)
        selection_reason = " ".join(str(
            item.get("selection_reason") or item.get("reason") or "").split()).strip()
        now = utc_now()

        with self.transaction() as con:
            campaign = con.execute("""SELECT id,status FROM source_campaigns
                WHERE id=?""", (campaign_id,)).fetchone()
            if not campaign:
                raise FileNotFoundError(f"source campaign not found: {campaign_id}")
            if campaign["status"] != "running":
                raise ValueError("source candidates require a running campaign")
            placeholders = ",".join("?" for _ in query_ids)
            found_query_ids = {row[0] for row in con.execute(
                f"""SELECT id FROM source_queries WHERE campaign_id=?
                AND id IN ({placeholders})""", [campaign_id, *query_ids])}
            if found_query_ids != set(query_ids):
                raise ValueError("query_id must belong to the source candidate campaign")

            existing = con.execute("""SELECT * FROM source_candidates
                WHERE campaign_id=? AND canonical_url=?""",
                (campaign_id, url)).fetchone()
            if existing and existing["status"] != "candidate":
                existing_attributes = json_value(existing["attributes_json"], {})
                immutable_changed = any((
                    existing["name"] != name,
                    existing["category"] != category,
                    existing["ownership_json"] != ownership_json,
                    float(existing["score"]) != score,
                    existing["selection_reason"] != selection_reason,
                    _immutable_candidate_payload(existing_attributes)
                    != _immutable_candidate_payload(item),
                ))
                if immutable_changed:
                    raise ValueError("reviewed candidate fields are immutable")
                for query_id in query_ids:
                    con.execute("""INSERT INTO source_candidate_queries
                        (candidate_id,query_id,created_at) VALUES(?,?,?)
                        ON CONFLICT(candidate_id,query_id) DO NOTHING""",
                        (existing["id"], query_id, now))
                return self._candidate_from_connection(con, existing["id"])

            domain_row = con.execute(
                "SELECT publisher_id FROM publisher_domains WHERE domain=?",
                (profile["domain"],)).fetchone() if profile["domain"] else None
            if domain_row:
                publisher_id = domain_row["publisher_id"]
            else:
                con.execute("""INSERT INTO publishers
                    (id,canonical_name,country,owner_cluster,verification_status,
                     metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                    canonical_name=CASE
                        WHEN publishers.verification_status!='verified'
                         AND excluded.verification_status='verified'
                        THEN excluded.canonical_name ELSE publishers.canonical_name END,
                    country=CASE WHEN publishers.country IS NULL OR publishers.country=''
                        THEN excluded.country ELSE publishers.country END,
                    verification_status=CASE WHEN excluded.verification_status='verified'
                        THEN 'verified' ELSE publishers.verification_status END,
                    updated_at=excluded.updated_at""",
                            (publisher_id, profile["name"],
                             str(item.get("publisher_country") or ""),
                             profile["owner_cluster"], profile["verification_status"],
                             json_text(profile), now, now))
                if profile["domain"]:
                    con.execute("""INSERT INTO publisher_domains
                        (domain,publisher_id,verified,source) VALUES(?,?,?,?)
                        ON CONFLICT(domain) DO UPDATE SET
                        verified=MAX(publisher_domains.verified,excluded.verified)""",
                                (profile["domain"], publisher_id,
                                 int(profile["verification_status"] == "verified"),
                                 "source-campaign"))

            source = con.execute(
                "SELECT id FROM sources WHERE canonical_url=?", (url,)).fetchone()
            source_id = source["id"] if source else None
            con.execute("""INSERT INTO source_candidates
                (id,campaign_id,canonical_url,source_id,publisher_id,name,category,
                 ownership_json,attributes_json,score,status,selection_reason,
                 status_reason,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'candidate',?,'',?,?)
                ON CONFLICT(campaign_id,canonical_url) DO UPDATE SET
                source_id=COALESCE(excluded.source_id,source_candidates.source_id),
                publisher_id=excluded.publisher_id,
                name=excluded.name,category=excluded.category,
                ownership_json=excluded.ownership_json,
                attributes_json=excluded.attributes_json,score=excluded.score,
                selection_reason=excluded.selection_reason,
                updated_at=excluded.updated_at""",
                        (candidate_id, campaign_id, url, source_id, publisher_id,
                         name, category, ownership_json, attributes_json, score,
                         selection_reason, now, now))
            for query_id in query_ids:
                con.execute("""INSERT INTO source_candidate_queries
                    (candidate_id,query_id,created_at) VALUES(?,?,?)
                    ON CONFLICT(candidate_id,query_id) DO NOTHING""",
                            (candidate_id, query_id, now))
            return self._candidate_from_connection(con, candidate_id)

    def get_source_candidate(self, folder: str, candidate_id: str) -> dict:
        industry_id = self.industry_id(folder)
        with self.connection() as con:
            scoped = con.execute("""SELECT c.id FROM source_candidates c
                JOIN source_campaigns sc ON sc.id=c.campaign_id
                WHERE c.id=? AND sc.industry_id=?""",
                                 (candidate_id, industry_id)).fetchone()
            if not scoped:
                raise FileNotFoundError(f"source candidate not found: {candidate_id}")
            return self._candidate_from_connection(con, candidate_id)

    def list_source_candidates(self, campaign_id: str) -> list[dict]:
        with self.connection() as con:
            campaign = con.execute(
                "SELECT 1 FROM source_campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not campaign:
                raise FileNotFoundError(f"source campaign not found: {campaign_id}")
            rows = con.execute(
                self._candidate_select() +
                " WHERE c.campaign_id=? ORDER BY c.score DESC,c.canonical_url",
                (campaign_id,)).fetchall()
            output = []
            for row in rows:
                query_ids = [query_row[0] for query_row in con.execute(
                    """SELECT query_id FROM source_candidate_queries
                    WHERE candidate_id=? ORDER BY query_id""", (row["id"],))]
                output.append(self._candidate_dict(row, query_ids))
            return output

    def review_source_candidate(self, folder: str, candidate_id: str, *,
                                decision: str, actor: str, reason: str) -> dict:
        from src.source_review import assess_source_candidate

        target = str(decision or "").strip().casefold()
        if target not in CANDIDATE_TRANSITIONS:
            raise ValueError(f"unknown source candidate decision: {decision}")
        normalized_actor = _required_text(actor, "actor")
        normalized_reason = _required_text(reason, "reason")
        industry_id = self.industry_id(folder)
        now = utc_now()

        with self.transaction() as con:
            row = con.execute("""SELECT c.*,p.canonical_name AS publisher_name,
                p.owner_cluster,p.verification_status
                FROM source_candidates c
                JOIN source_campaigns sc ON sc.id=c.campaign_id
                JOIN publishers p ON p.id=c.publisher_id
                WHERE c.id=? AND sc.industry_id=?""",
                              (candidate_id, industry_id)).fetchone()
            if not row:
                raise FileNotFoundError(f"source candidate not found: {candidate_id}")
            current = str(row["status"])
            if target not in CANDIDATE_TRANSITIONS[current]:
                raise ValueError(
                    f"invalid source candidate transition: {current} -> {target}")
            attributes = json_value(row["attributes_json"], {})
            candidate_item = {
                **attributes,
                "name": row["name"],
                "url": row["canonical_url"],
                "category": row["category"],
                "ownership": json_value(row["ownership_json"], {}),
            }
            assessment = None
            source_id = row["source_id"]
            if target == "active":
                candidate_item["human_review"] = {
                    "decision": "active", "actor": normalized_actor,
                    "reason": normalized_reason,
                }
                assessment = assess_source_candidate(
                    candidate_item, category=row["category"])
                if assessment["decision"] != "active":
                    raise ValueError(
                        "source admission gates failed: " + assessment["reason"])
                source_id = self._upsert_source_in_transaction(
                    con, industry_id, row["category"], {
                        **candidate_item,
                        "admission_assessment": assessment,
                        "monitoring_status": "active",
                    }, monitoring_status="active")
            snapshot = {
                "name": row["name"],
                "url": row["canonical_url"],
                "publisher_id": row["publisher_id"],
                "publisher_name": row["publisher_name"],
                "publisher_owner_cluster": row["owner_cluster"],
                "publisher_verification": row["verification_status"],
                "ownership": json_value(row["ownership_json"], {}),
                "access": attributes.get("access", ""),
                "assessment": assessment,
            }
            changed = con.execute("""UPDATE source_candidates
                SET status=?,status_reason=?,source_id=COALESCE(?,source_id),updated_at=?
                WHERE id=? AND status=?""",
                                  (target, normalized_reason, source_id, now, candidate_id,
                                   current)).rowcount
            if changed != 1:
                raise RuntimeError("source candidate changed concurrently")
            con.execute("""INSERT INTO source_reviews
                (candidate_id,from_status,to_status,decision,actor,reason,
                 snapshot_json,occurred_at) VALUES(?,?,?,?,?,?,?,?)""",
                        (candidate_id, current, target, target, normalized_actor,
                         normalized_reason, _canonical_json(snapshot), now))
            return self._candidate_from_connection(con, candidate_id)

    def reassess_source(self, folder: str, source_id: str, *, decision: str,
                        actor: str, reason: str) -> dict:
        from src.source_review import assess_source_candidate

        normalized_actor = _required_text(actor, "actor")
        normalized_reason = _required_text(reason, "reason")
        target = str(decision or "").strip().casefold()
        stored_statuses = {
            "active": "active",
            "manual": "recommended_manual",
            "manual_review": "recommended_manual",
            "reserve": "reserve",
            "rejected": "quarantined",
        }
        if target not in stored_statuses:
            raise ValueError(f"unknown source reassessment decision: {decision}")
        industry_id = self.industry_id(folder)
        now = utc_now()
        with self.transaction() as con:
            row = con.execute("""SELECT s.canonical_url,s.name,s.publisher_country,
                s.metadata_json,x.category,x.metadata_json AS link_json,
                x.monitoring_status,x.added_manually
                FROM industry_sources x JOIN sources s ON s.id=x.source_id
                WHERE x.industry_id=? AND x.source_id=? AND x.deleted_at IS NULL""",
                (industry_id, source_id)).fetchone()
            if not row:
                raise FileNotFoundError(f"source not found: {source_id}")
            item = json_value(row["metadata_json"], {})
            item.update(json_value(row["link_json"], {}))
            item.update({
                "url": row["canonical_url"], "name": row["name"],
                "publisher_country": row["publisher_country"],
                "category": row["category"],
                "added_manually": bool(row["added_manually"]),
                "human_review": {
                    "decision": target, "actor": normalized_actor,
                    "reason": normalized_reason,
                },
            })
            assessment = assess_source_candidate(item, category=row["category"])
            if target == "active" and assessment["decision"] != "active":
                raise ValueError(
                    "source admission gates failed: " + assessment["reason"])
            metadata = {
                **item,
                "reassessment": {
                    "decision": target, "actor": normalized_actor,
                    "reason": normalized_reason, "occurred_at": now,
                    "assessment": assessment,
                },
                "monitoring_status": stored_statuses[target],
            }
            con.execute("""UPDATE industry_sources SET monitoring_status=?,metadata_json=?
                WHERE industry_id=? AND source_id=? AND deleted_at IS NULL""",
                (stored_statuses[target], json_text(metadata), industry_id, source_id))
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,?,?,?,?,?)""",
                (now, normalized_actor, "source_reassessment", "source", source_id,
                 json_text({"decision": target, "reason": normalized_reason,
                            "assessment": assessment})))
            self._insert_quality_observation(con, industry_id, {
                "observed_at": now, "metric": "manual_correction_rate",
                "numerator": 1, "denominator": 1,
                "algorithm_version": "source-governance-v1",
                "dimensions": {"object_type": "source", "decision": target,
                               "category": row["category"]},
            })
            self._mark_compat_dirty(con, industry_id, "sources")
        return {"source_id": source_id, "state": target,
                "review": {"decision": target, "actor": normalized_actor,
                           "reason": normalized_reason}}
