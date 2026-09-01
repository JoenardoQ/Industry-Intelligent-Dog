"""Persistence for imported Agent results and assertion review state."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .models import canonical_url, json_text, json_value, stable_id, utc_now
from .source_trust import evidence_publisher_profile


HUMAN_REVIEW_ALLOWED = {
    "draft_review_required": {"rejected", "opinion", "submitted_for_verification"},
}
VERIFICATION_ALLOWED = {
    "submitted_for_verification": {"candidate", "disputed", "accepted", "rejected"},
}
ALLOWED = {**HUMAN_REVIEW_ALLOWED, **VERIFICATION_ALLOWED}

_VOLATILE_RESULT_FIELDS = {
    "content_sha256", "content_hash", "result_id", "status", "created_at",
    "industry", "path", "raw_path", "original_file", "duplicate", "review",
}
MAX_AGENT_RESULT_BYTES = 512_000
MAX_AGENT_ASSERTIONS = 100
MAX_ASSERTION_CITATIONS = 20
MAX_VERIFICATION_JSON_BYTES = 256 * 1024
REQUIRED_ACCEPTANCE_CHECKS = {
    "atomization", "reachability", "publisher_identity", "publication_time",
    "entity_alignment", "semantic_support", "locator_integrity",
    "numeric_consistency", "corroboration", "conflict",
    "verifier_independence", "generation_provenance", "type_classification",
    "type_policy", "resource_budget", "fact_projection",
}
NOT_APPLICABLE_ACCEPTANCE_CHECKS = {"numeric_consistency"}
NON_FACT_ASSERTION_TYPES = {
    "causal", "causality", "forecast", "investment_judgment", "investment",
    "forecast_estimate", "estimate", "opinion", "judgment",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _validate_typed_acceptance(
        con, assertion_id: str, checks: dict, raw_evidence: list[dict]) -> None:
    """Do not let callers forge strings that merely look like passed gates."""
    citation_rows = con.execute(
        "SELECT id,canonical_url FROM agent_citations WHERE assertion_id=?",
        (assertion_id,)).fetchall()
    citation_ids = {row["id"] for row in citation_rows}
    citation_urls = {row["id"]: row["canonical_url"] for row in citation_rows}
    for name in REQUIRED_ACCEPTANCE_CHECKS:
        check = checks.get(name)
        if not isinstance(check, dict) or not str(check.get("reason") or "").strip():
            raise ValueError(f"verification check {name} requires a typed reason")
        if not isinstance(check.get("evidence_ids"), list) or not isinstance(
                check.get("locators"), list):
            raise ValueError(f"verification check {name} requires evidence_ids and locators")
        if not set(check["evidence_ids"]).issubset(citation_ids):
            raise ValueError(f"verification check {name} references a foreign citation")
        for locator in check["locators"]:
            if (not isinstance(locator, dict) or
                    locator.get("evidence_id") not in citation_ids or
                    not _SHA256.fullmatch(str(locator.get("content_hash") or "")) or
                    not isinstance(locator.get("locator"), dict) or
                    not str(locator.get("excerpt") or "")):
                raise ValueError(f"verification check {name} has invalid locator provenance")
    semantic = checks["semantic_support"]
    if semantic.get("decision") != "supported" or not semantic["evidence_ids"]:
        raise ValueError("semantic_support requires supported, cited evidence")
    projection = checks["fact_projection"]
    raw_by_id: dict[str, dict] = {}
    for raw in raw_evidence:
        citation_id = str(raw.get("citation_id") or "") if isinstance(raw, dict) else ""
        content = str(raw.get("content") or "") if isinstance(raw, dict) else ""
        content_hash = str(raw.get("content_hash") or "") if isinstance(raw, dict) else ""
        if (citation_id not in citation_ids or not content or
                not _SHA256.fullmatch(content_hash) or
                hashlib.sha256(content.encode("utf-8")).hexdigest() != content_hash):
            raise ValueError("trusted raw evidence content hash is invalid")
        raw_by_id[citation_id] = raw
    fact_by_id: dict[str, dict] = {}
    for item in projection.get("evidence") or []:
        if not isinstance(item, dict):
            raise ValueError("fact projection evidence must be typed objects")
        citation_id = str(item.get("citation_id") or "")
        content_hash = str(item.get("content_hash") or "")
        if citation_id not in citation_ids:
            raise ValueError("fact projection evidence references a foreign citation")
        if canonical_url(item.get("url", "")) != citation_urls[citation_id]:
            raise ValueError("fact projection evidence URL differs from its citation")
        raw = raw_by_id.get(citation_id)
        if (not _SHA256.fullmatch(content_hash) or not raw or
                content_hash != raw.get("content_hash") or
                canonical_url(raw.get("url", "")) != citation_urls[citation_id] or
                raw.get("locator") != item.get("locator") or
                raw.get("excerpt") != item.get("excerpt")):
            raise ValueError("fact projection evidence does not match trusted raw evidence")
        role, relation = item.get("role"), item.get("relation")
        if ((role == "support" and relation != "supports") or
                (role == "conversion_benchmark" and relation != "qualifies") or
                role not in {"support", "conversion_benchmark"}):
            raise ValueError("fact projection evidence role/relation is invalid")
        fact_by_id[citation_id] = item
    for evidence_id in semantic["evidence_ids"]:
        item = fact_by_id.get(evidence_id)
        if not item or item.get("role") != "support" or item.get("relation") != "supports":
            raise ValueError("semantic_support is not associated with supporting fact evidence")
        provenance = next((record for record in semantic["locators"]
                           if record.get("evidence_id") == evidence_id), None)
        if (not provenance or provenance.get("content_hash") != item.get("content_hash") or
                provenance.get("locator") != item.get("locator") or
                provenance.get("excerpt") != item.get("excerpt")):
            raise ValueError("semantic_support hash/locator provenance is inconsistent")


def _read_agent_result_artifact(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_AGENT_RESULT_BYTES + 1)
    except OSError as exc:
        raise ValueError("Agent result artifact is not readable") from exc
    if len(raw) > MAX_AGENT_RESULT_BYTES:
        raise ValueError("Agent result artifact exceeds the 500 KiB limit")
    try:
        artifact = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Agent result artifact is not valid JSON") from exc
    if not isinstance(artifact, dict):
        raise ValueError("Agent result artifact must contain a JSON object")
    return artifact


def _substantive_json(record: dict) -> str:
    substantive = {key: value for key, value in record.items()
                   if key not in _VOLATILE_RESULT_FIELDS}
    return json.dumps(substantive, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def _validated_assertions(record: dict) -> list[tuple[str, str, list[tuple[str, str]]]]:
    assertions = record.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        raise ValueError("Agent result must contain at least one assertion")
    if len(assertions) > MAX_AGENT_ASSERTIONS:
        raise ValueError("Agent result must contain at most 100 assertions")
    validated = []
    for assertion in assertions:
        if not isinstance(assertion, dict):
            raise ValueError("Agent assertions must be objects")
        text = str(assertion.get("text") or "").strip()
        if not text:
            raise ValueError("Agent assertion text must not be blank")
        citations = {}
        raw_citations = assertion.get("citations")
        if isinstance(raw_citations, list) and len(raw_citations) > MAX_ASSERTION_CITATIONS:
            raise ValueError("Agent assertion must contain at most 20 citations")
        if isinstance(raw_citations, list):
            for citation in raw_citations:
                source_url = str(citation.get("url") if isinstance(citation, dict)
                                 else citation)
                normalized = canonical_url(source_url)
                if normalized and normalized not in citations:
                    citations[normalized] = source_url
        if not citations:
            raise ValueError("Agent assertion must contain an HTTP(S) citation")
        validated.append((text, str(assertion.get("type") or "unspecified"),
                          [(source, normalized)
                           for normalized, source in citations.items()]))
    return validated


class EvidenceRepositoryMixin:
    def index_agent_result(self, folder: str, record: dict, raw_path: str) -> dict:
        industry_id = self.industry_id(folder)
        assertions = _validated_assertions(record)
        substantive_json = _substantive_json(record)
        artifact_path = Path(raw_path)
        try:
            resolved_path = artifact_path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("Agent result artifact must be a regular JSON file") from exc
        if not resolved_path.is_file():
            raise ValueError("Agent result artifact must be a regular JSON file")
        managed_directory = (self.data_root / folder).resolve()
        try:
            resolved_path.relative_to(managed_directory)
        except ValueError as exc:
            raise ValueError(
                "Agent result artifact must be inside the managed industry directory") from exc
        artifact = _read_agent_result_artifact(resolved_path)
        if _substantive_json(artifact) != substantive_json:
            raise ValueError("Agent result artifact does not match supplied record")
        content_hash = hashlib.sha256(substantive_json.encode("utf-8")).hexdigest()
        result_id = stable_id("agr", industry_id, content_hash)
        now = str(record.get("created_at") or utc_now())
        with self.transaction() as con:
            existing = con.execute(
                "SELECT id FROM agent_results WHERE industry_id=? AND content_hash=?",
                (industry_id, content_hash)).fetchone()
            if existing:
                result_id = existing["id"]
            else:
                con.execute("""INSERT INTO agent_results
                    (id,industry_id,task_id,agent_id,original_file,content_hash,summary,
                     status,record_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (result_id, industry_id, str(record.get("task_id") or ""),
                     str(record.get("agent_id") or ""), str(resolved_path), content_hash,
                     str(record.get("summary") or ""), "draft_review_required",
                     json_text(record), now))
                for ordinal, (text, assertion_type, citations) in enumerate(assertions):
                    assertion_id = stable_id("aas", result_id, ordinal, text)
                    con.execute("""INSERT INTO agent_assertions
                        (id,result_id,ordinal,assertion_text,assertion_type,status,
                         verification_json,created_at,updated_at)
                        VALUES(?,?,?,?,?,'draft_review_required','{}',?,?)""",
                        (assertion_id, result_id, ordinal, text, assertion_type, now, now))
                    for source_url, normalized in citations:
                        citation_id = stable_id("act", assertion_id, normalized)
                        con.execute("""INSERT INTO agent_citations
                            (id,assertion_id,url,canonical_url,reachability,created_at)
                            VALUES(?,?,?,?,?,?)""",
                            (citation_id, assertion_id, source_url, normalized,
                             "unchecked", now))
                con.execute("""INSERT INTO audit_log
                    (occurred_at,actor,action,object_type,object_id,details_json)
                    VALUES(?,?,?,?,?,?)""",
                    (now, "web", "import_agent_result", "agent_result", result_id,
                     json_text({"industry": folder,
                                "task_id": str(record.get("task_id") or ""),
                                "agent_id": str(record.get("agent_id") or ""),
                                "status": "draft_review_required"})))
        return self.get_agent_result(folder, result_id)

    def list_agent_results(self, folder: str, *, limit: int, offset: int) -> dict:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1..100 and offset must be non-negative")
        industry_id = self.industry_id(folder)
        with self.connection() as con:
            total = con.execute(
                "SELECT COUNT(*) FROM agent_results WHERE industry_id=?",
                (industry_id,)).fetchone()[0]
            ids = [row[0] for row in con.execute("""SELECT id FROM agent_results
                WHERE industry_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?""",
                (industry_id, limit, offset))]
        items = [self.get_agent_result(folder, result_id) for result_id in ids]
        next_offset = offset + limit if offset + limit < total else None
        return {"industry": folder, "items": items, "total": total, "offset": offset,
                "limit": limit, "next_offset": next_offset}

    def get_agent_result(self, folder: str, result_id: str) -> dict:
        industry_id = self.industry_id(folder)
        with self.connection() as con:
            row = con.execute("""SELECT * FROM agent_results
                WHERE industry_id=? AND id=?""", (industry_id, result_id)).fetchone()
            if not row:
                raise FileNotFoundError(f"Agent result not found: {result_id}")
            assertions = [self._agent_assertion_dict(con, item) for item in con.execute(
                "SELECT * FROM agent_assertions WHERE result_id=? ORDER BY ordinal",
                (result_id,))]
        original = json_value(row["record_json"], {})
        return {**original, "result_id": row["id"], "industry": folder,
                "task_id": row["task_id"], "agent_id": row["agent_id"],
                "summary": row["summary"], "content_sha256": row["content_hash"],
                "status": row["status"], "original_file": row["original_file"],
                "created_at": row["created_at"], "assertions": assertions}

    def review_agent_assertion(self, folder: str, assertion_id: str, *,
                               decision: str, actor: str, note: str) -> dict:
        industry_id = self.industry_id(folder)
        now = utc_now()
        with self.transaction() as con:
            row = self._agent_assertion_row(con, industry_id, assertion_id)
            current = row["status"]
            if decision not in HUMAN_REVIEW_ALLOWED.get(current, set()):
                raise ValueError(f"illegal assertion transition: {current} -> {decision}")
            con.execute("UPDATE agent_assertions SET status=?,updated_at=? WHERE id=?",
                        (decision, now, assertion_id))
            con.execute("""INSERT INTO agent_result_reviews
                (result_id,assertion_id,from_status,action,actor,explanation,occurred_at)
                VALUES(?,?,?,?,?,?,?)""",
                (row["result_id"], assertion_id, current, decision, actor, note, now))
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,?,?,?,?,?)""",
                (now, actor, "review_agent_assertion", "agent_assertion", assertion_id,
                 json_text({"industry": folder, "result_id": row["result_id"],
                            "from": current, "status": decision, "note": note})))
            self._update_agent_result_status(con, row["result_id"])
        return self._get_agent_assertion(folder, assertion_id)

    def apply_assertion_verification(self, folder: str, assertion_id: str, *,
                                     checks: dict, disposition: str) -> dict:
        """Persist non-fact outcomes; accepted facts require trusted orchestration."""
        if disposition == "accepted":
            raise ValueError(
                "accepted facts require trusted verifier orchestration; raw checks are rejected")
        return self._apply_assertion_verification_from_verifier(
            folder, assertion_id, checks=checks, disposition=disposition)

    def _apply_assertion_verification_from_verifier(
            self, folder: str, assertion_id: str, *, checks: dict,
            disposition: str, raw_evidence: list[dict] | None = None) -> dict:
        industry_id = self.industry_id(folder)
        now = utc_now()
        with self.transaction() as con:
            row = self._agent_assertion_row(con, industry_id, assertion_id)
            current = row["status"]
            if (current in {"candidate", "disputed", "accepted", "rejected"} and
                    json_value(row["verification_json"], {})):
                return self._agent_assertion_dict(con, row)
            if disposition not in VERIFICATION_ALLOWED.get(current, set()):
                raise ValueError(f"illegal assertion transition: {current} -> {disposition}")
            checks = json_value(json_text(checks), {})
            conflict_group_id = ""
            if disposition == "disputed":
                conflict = checks.get("conflict")
                conflicting_claim_ids = sorted({
                    str(claim_id) for claim_id in (
                        conflict.get("conflicting_claim_ids") or [])
                    if str(claim_id)
                }) if isinstance(conflict, dict) else []
                if conflicting_claim_ids:
                    conflict_group_id = stable_id(
                        "cfg", industry_id, *conflicting_claim_ids)
                    conflict["conflict_group_id"] = conflict_group_id
                    conflict["conflict_group_members"] = {
                        "accepted_claim_ids": conflicting_claim_ids,
                        "disputed_assertion_ids": [assertion_id],
                    }
            if disposition == "accepted":
                blocking = sorted(
                    name for name, check in checks.items()
                    if not isinstance(check, dict) or
                    (check.get("status") != "passed" and not (
                        name in NOT_APPLICABLE_ACCEPTANCE_CHECKS and
                        check.get("status") == "not_applicable")))
                if blocking:
                    raise ValueError(
                        "blocking verification check prevents acceptance: " +
                        ", ".join(blocking))
                missing = sorted(REQUIRED_ACCEPTANCE_CHECKS - set(checks))
                if missing:
                    raise ValueError(
                        "incomplete verification checks prevent acceptance: " +
                        ", ".join(missing))
                if str(row["assertion_type"] or "").casefold() in NON_FACT_ASSERTION_TYPES:
                    raise ValueError("non-factual assertion type cannot be accepted")
                _validate_typed_acceptance(
                    con, assertion_id, checks, list(raw_evidence or []))
            verification_text = json_text(checks)
            if len(verification_text.encode("utf-8")) > MAX_VERIFICATION_JSON_BYTES:
                raise ValueError("verification decision exceeds the 256 KiB storage limit")
            projection = (self._agent_fact_projection(con, row)
                          if disposition == "accepted" else None)
            evidence_items = list(raw_evidence or [])
            if disposition == "accepted" and not evidence_items:
                raise ValueError("accepted assertion requires locatable evidence")
            if disposition == "accepted" and not any(
                    isinstance(item, dict) and item.get("role") == "support" and
                    item.get("relation") == "supports" for item in evidence_items):
                raise ValueError("accepted assertion requires supporting evidence")
            persisted_evidence = self._persist_agent_evidence_observations(
                con, industry_id, assertion_id, evidence_items, now,
                require_locatable=disposition == "accepted",
                accepted_fact=disposition == "accepted")
            claim_id = None
            if disposition == "accepted":
                object_json = json_text(projection["object"])
                qualifiers_json = json_text(projection["qualifiers"])
                claim_id = stable_id(
                    "clm", industry_id, projection["subject_id"],
                    projection["predicate"], object_json, qualifiers_json,
                    projection["valid_from"], projection["valid_to"])
                con.execute("""INSERT INTO claims
                    (id,industry_id,subject_id,predicate,object_json,qualifiers_json,
                     valid_from,valid_to,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?, 'accepted',?,?)
                    ON CONFLICT(id) DO UPDATE SET status='accepted',updated_at=excluded.updated_at,
                    superseded_at=NULL""",
                    (claim_id, industry_id, projection["subject_id"],
                     projection["predicate"], object_json, qualifiers_json,
                     projection["valid_from"] or None, projection["valid_to"] or None,
                     now, now))
                for evidence_item, document_id, snapshot_id in persisted_evidence:
                    relation = str(evidence_item.get("relation") or "supports")
                    if relation not in {"supports", "contradicts", "qualifies"}:
                        relation = "qualifies"
                    evidence_id = stable_id(
                        "evd", claim_id, document_id, relation,
                        str(evidence_item.get("excerpt") or ""))
                    con.execute("""INSERT INTO evidence
                        (id,claim_id,document_id,snapshot_id,relation,excerpt,publisher_cluster,
                         extraction_method,confidence,created_at)
                        VALUES(?,?,?,?,?,?,?,?,NULL,?)
                        ON CONFLICT(claim_id,document_id,relation) DO UPDATE SET
                        snapshot_id=excluded.snapshot_id,
                        excerpt=excluded.excerpt,
                        publisher_cluster=excluded.publisher_cluster,
                        extraction_method=excluded.extraction_method""",
                        (evidence_id, claim_id, document_id, snapshot_id, relation,
                         str(evidence_item.get("excerpt") or ""),
                         str(evidence_item.get("publisher_cluster") or ""),
                         "agent_assertion_verifier", now))
                    con.execute("""INSERT INTO claim_evidence_snapshots
                        (claim_id,snapshot_id,relation,excerpt,publisher_cluster,created_at)
                        VALUES(?,?,?,?,?,?) ON CONFLICT(claim_id,snapshot_id,relation)
                        DO NOTHING""", (claim_id, snapshot_id, relation,
                        str(evidence_item.get("excerpt") or ""),
                        str(evidence_item.get("publisher_cluster") or ""), now))
            con.execute("""UPDATE agent_assertions SET status=?,claim_id=?,
                verification_json=?,updated_at=? WHERE id=?""",
                (disposition, claim_id, verification_text, now, assertion_id))
            con.execute("""INSERT INTO agent_result_reviews
                (result_id,assertion_id,from_status,action,actor,explanation,occurred_at)
                VALUES(?,?,?,?,?,?,?)""",
                (row["result_id"], assertion_id, current, disposition,
                 "assertion-verifier", "", now))
            con.execute("""INSERT INTO audit_log
                (occurred_at,actor,action,object_type,object_id,details_json)
                VALUES(?,?,?,?,?,?)""",
                (now, "assertion-verifier", "verify_agent_assertion",
                 "agent_assertion", assertion_id,
                 json_text({"industry": folder, "result_id": row["result_id"],
                            "from": current, "status": disposition,
                            "claim_id": claim_id,
                            "conflict_group_id": conflict_group_id})))
            self._insert_quality_observation(con, industry_id, {
                "observed_at": now, "metric": "citation_failure_rate",
                "numerator": int(disposition in {"rejected", "disputed"}),
                "denominator": 1, "algorithm_version": "assertion-verifier-v1",
                "dimensions": {"assertion_type": row["assertion_type"],
                               "disposition": disposition},
            })
            self._insert_quality_observation(con, industry_id, {
                "observed_at": now, "metric": "classification_unknown_rate",
                "numerator": int(str(row["assertion_type"]).casefold() == "unspecified"),
                "denominator": 1, "algorithm_version": "assertion-verifier-v1",
                "dimensions": {"stage": "assertion_type"},
            })
            self._update_agent_result_status(con, row["result_id"])
        return self._get_agent_assertion(folder, assertion_id)

    @staticmethod
    def _agent_fact_projection(con, row) -> dict:
        result = con.execute(
            "SELECT record_json FROM agent_results WHERE id=?",
            (row["result_id"],)).fetchone()
        record = json_value(result["record_json"], {}) if result else {}
        imported_assertions = record.get("assertions") or []
        imported = (imported_assertions[row["ordinal"]]
                    if row["ordinal"] < len(imported_assertions) else {})
        imported = imported if isinstance(imported, dict) else {}
        atomic = imported.get("atomic")
        if not isinstance(atomic, dict):
            keys = (
                "subject", "subject_id", "predicate", "object", "time", "region",
                "value", "unit", "currency", "period", "statistical_definition",
                "qualifiers", "valid_from", "valid_to",
            )
            atomic = {key: imported[key] for key in keys if key in imported}
        required = ("subject", "predicate", "object", "time", "region")
        if any(atomic.get(key) is None or
               (isinstance(atomic.get(key), str) and not atomic[key].strip())
               for key in required):
            raise ValueError("accepted assertion requires an atomic fact projection")
        qualifiers = atomic.get("qualifiers", {})
        if not isinstance(qualifiers, dict):
            raise ValueError("accepted assertion qualifiers must be an object")
        qualifiers = dict(qualifiers)
        for key in ("subject", "time", "region", "value", "unit", "currency",
                    "period", "statistical_definition"):
            value = atomic.get(key)
            if value is not None and (not isinstance(value, str) or value.strip()):
                qualifiers[key] = value
        subject_id = str(atomic.get("subject_id") or "") or None
        if not subject_id or not con.execute(
                "SELECT 1 FROM entities WHERE id=?", (subject_id,)).fetchone():
            raise ValueError("accepted assertion requires a governed canonical subject_id")
        return {
            "subject_id": subject_id,
            "predicate": str(atomic["predicate"]),
            "object": atomic["object"],
            "qualifiers": qualifiers,
            "valid_from": str(atomic.get("valid_from") or ""),
            "valid_to": str(atomic.get("valid_to") or ""),
        }

    @staticmethod
    def _persist_agent_evidence_observations(
            con, industry_id: str, assertion_id: str,
            evidence_items: list[dict], now: str, *,
            require_locatable: bool,
            accepted_fact: bool) -> list[tuple[dict, str]]:
        persisted = []
        for item in evidence_items:
            if not isinstance(item, dict):
                raise ValueError("fact projection evidence must be objects")
            url = canonical_url(item.get("url", ""))
            content_hash = str(item.get("content_hash") or "")
            locator = item.get("locator")
            if (not url or len(content_hash) != 64 or
                    not isinstance(locator, dict) or not locator):
                if require_locatable:
                    raise ValueError(
                        "fact projection evidence requires URL, content hash, and locator")
                citation_id = str(item.get("citation_id") or "")
                if citation_id:
                    con.execute("""UPDATE agent_citations SET reachability=?,verified_at=?
                        WHERE id=? AND assertion_id=?""",
                        ("reachable" if item.get("reachable") else "unreachable",
                         now, citation_id, assertion_id))
                continue
            content = str(item.get("content") or "")
            if (not _SHA256.fullmatch(content_hash) or not content or
                    hashlib.sha256(content.encode("utf-8")).hexdigest() != content_hash):
                if require_locatable:
                    raise ValueError("fact projection evidence content hash does not match content")
                continue
            profile = evidence_publisher_profile(url)
            source_id = stable_id("src", url)
            publisher_id = stable_id("pub", profile["owner_cluster"])
            con.execute("""INSERT INTO sources
                (id,canonical_url,name,publisher_country,metadata_json,created_at,updated_at)
                VALUES(?,?,?,NULL,?,?,?) ON CONFLICT(canonical_url) DO UPDATE SET
                name=excluded.name,metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at""",
                (source_id, url, profile["name"], json_text({
                    "verification_status": profile["verification_status"],
                    "evidence_type": profile["evidence_type"]}), now, now))
            source_row = con.execute(
                "SELECT id FROM sources WHERE canonical_url=?", (url,)).fetchone()
            source_id = source_row["id"]
            con.execute("""INSERT INTO publishers
                (id,canonical_name,country,owner_cluster,verification_status,
                 metadata_json,created_at,updated_at) VALUES(?,?,NULL,?,?,?, ?,?)
                ON CONFLICT(id) DO UPDATE SET verification_status=excluded.verification_status,
                updated_at=excluded.updated_at""",
                (publisher_id, profile["name"], profile["owner_cluster"],
                 profile["verification_status"], json_text({}), now, now))
            if profile["domain"]:
                con.execute("""INSERT INTO publisher_domains(domain,publisher_id,verified,source)
                    VALUES(?,?,?, 'reviewed_registry') ON CONFLICT(domain) DO UPDATE SET
                    publisher_id=excluded.publisher_id,verified=excluded.verified""",
                    (profile["domain"], publisher_id,
                     1 if profile["verification_status"] == "verified" else 0))
            con.execute("""INSERT INTO source_publishers
                (source_id,publisher_id,relation,confidence) VALUES(?,?,'publishes',1.0)
                ON CONFLICT(source_id,publisher_id,relation) DO NOTHING""",
                (source_id, publisher_id))
            con.execute("""INSERT INTO industry_sources
                (industry_id,source_id,category,monitoring_status,added_manually,
                 metadata_json,deleted_at) VALUES(?,?,'agent_evidence','active',0,?,NULL)
                ON CONFLICT(industry_id,source_id,category) DO UPDATE SET
                monitoring_status='active',deleted_at=NULL""",
                (industry_id, source_id, json_text({"governed_by": "assertion-verifier"})))
            document_id = stable_id("doc", url)
            excerpt = str(item.get("excerpt") or "")
            published_at = str(item.get("published_at") or "") or None
            con.execute("""INSERT INTO documents
                (id,canonical_url,content_hash,title,abstract,source_id,published_at,
                 retrieved_at,language,origin,raw_json)
                VALUES(?,?,?,?,?,?,?, ?,NULL,'agent_verification',?)
                ON CONFLICT(canonical_url) DO UPDATE SET
                abstract=CASE WHEN excluded.abstract!='' THEN excluded.abstract
                              ELSE documents.abstract END,
                source_id=COALESCE(documents.source_id,excluded.source_id),
                retrieved_at=excluded.retrieved_at""",
                (document_id, url, content_hash, excerpt[:240] or url, excerpt,
                 source_id, published_at, now,
                 json_text({"locator": locator,
                            "publisher_cluster": item.get("publisher_cluster", "")})))
            snapshot_id = stable_id("dsp", document_id, content_hash)
            snapshot_status = "verified" if accepted_fact else "observed"
            con.execute("""INSERT INTO document_snapshots
                (id,document_id,source_id,content_hash,content_text,title,published_at,
                 locator_json,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(document_id,content_hash)
                DO UPDATE SET status=CASE
                    WHEN document_snapshots.status='verified' OR excluded.status='verified'
                    THEN 'verified' ELSE document_snapshots.status END,
                    updated_at=excluded.updated_at""",
                (snapshot_id, document_id, source_id, content_hash, content,
                 excerpt[:240] or url, published_at, json_text(locator),
                 snapshot_status, now, now))
            observed_date = (published_at or now)[:10]
            review_status = "verified" if accepted_fact else "evidence_observed"
            credibility = "verified" if accepted_fact else "collected"
            con.execute("""INSERT INTO industry_documents
                (industry_id,document_id,category,observed_date,review_status,
                 credibility,metadata_json)
                VALUES(?,?, 'agent_evidence',?,?,?,?)
                ON CONFLICT(industry_id,document_id,category,observed_date)
                DO UPDATE SET review_status=CASE
                    WHEN industry_documents.review_status='verified'
                    THEN industry_documents.review_status ELSE excluded.review_status END,
                credibility=CASE WHEN industry_documents.credibility='verified'
                    THEN industry_documents.credibility ELSE excluded.credibility END,
                metadata_json=CASE WHEN industry_documents.review_status='verified'
                    THEN industry_documents.metadata_json ELSE excluded.metadata_json END,
                deleted_at=NULL""",
                (industry_id, document_id, observed_date, review_status, credibility,
                 json_text({"agent_assertion_id": assertion_id,
                            "locator": locator})))
            citation_id = str(item.get("citation_id") or "")
            if citation_id:
                updated = con.execute("""UPDATE agent_citations SET
                    reachability=?,source_id=?,document_id=?,snapshot_id=?,verified_at=?
                    WHERE id=? AND assertion_id=?""",
                    ("reachable" if item.get("reachable") else "unreachable",
                     source_id, document_id, snapshot_id, now, citation_id, assertion_id))
            else:
                updated = con.execute("""UPDATE agent_citations SET
                    reachability=?,source_id=?,document_id=?,snapshot_id=?,verified_at=?
                    WHERE canonical_url=? AND assertion_id=?""",
                    ("reachable" if item.get("reachable") else "unreachable",
                     source_id, document_id, snapshot_id, now, url, assertion_id))
            if updated.rowcount != 1:
                raise ValueError("fact projection evidence does not match an assertion citation")
            persisted.append((item, document_id, snapshot_id))
        return persisted

    @staticmethod
    def _agent_assertion_dict(con, row) -> dict:
        citations = [dict(item) for item in con.execute("""SELECT id,url,canonical_url,
            reachability,source_id,document_id,snapshot_id,verified_at FROM agent_citations
            WHERE assertion_id=? ORDER BY id""", (row["id"],))]
        verification = json_value(row["verification_json"], {})
        return {"id": row["id"], "text": row["assertion_text"],
                "type": row["assertion_type"], "status": row["status"],
                "claim_id": row["claim_id"],
                "verification": verification or None,
                "citations": citations}

    @staticmethod
    def _agent_assertion_row(con, industry_id: str, assertion_id: str):
        row = con.execute("""SELECT a.* FROM agent_assertions a
            JOIN agent_results r ON r.id=a.result_id
            WHERE a.id=? AND r.industry_id=?""", (assertion_id, industry_id)).fetchone()
        if not row:
            raise FileNotFoundError(f"Agent assertion not found: {assertion_id}")
        return row

    def _get_agent_assertion(self, folder: str, assertion_id: str) -> dict:
        industry_id = self.industry_id(folder)
        with self.connection() as con:
            row = self._agent_assertion_row(con, industry_id, assertion_id)
            return self._agent_assertion_dict(con, row)

    @staticmethod
    def _update_agent_result_status(con, result_id: str) -> None:
        statuses = [row[0] for row in con.execute(
            "SELECT status FROM agent_assertions WHERE result_id=?", (result_id,))]
        if len(set(statuses)) == 1:
            status = statuses[0]
        else:
            status = next((item for item in ("draft_review_required",
                          "submitted_for_verification", "disputed", "candidate")
                          if item in statuses), "candidate")
        con.execute("UPDATE agent_results SET status=? WHERE id=?", (status, result_id))
