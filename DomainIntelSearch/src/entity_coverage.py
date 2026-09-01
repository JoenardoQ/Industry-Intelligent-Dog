"""Deterministic open-world entity and value-chain coverage planning."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from intdog_core import normalized_name, stable_id
from intdog_core.models import json_value


OBJECT_CATEGORIES = (
    "company", "research_group", "government_institution", "association",
    "investment_institution", "person", "product", "technology", "standard",
    "policy",
)
REGIONS = ("china", "foreign")
QUALIFIED_STATUSES = {"accepted", "verified", "corroborated", "collected"}
_CHINA = {"cn", "china", "中国", "hong kong", "香港", "macau", "澳门"}
ALGORITHM_VERSION = "entity-coverage-v1"


@dataclass(frozen=True)
class CoverageFrontier:
    cells: list[dict]
    entity_queries: list[dict]
    relation_queries: list[dict]
    stopping_reason: str | None


def _region(record: dict) -> str:
    explicit = str(record.get("region") or "").strip().casefold()
    if explicit in REGIONS:
        return explicit
    return "china" if str(record.get("country") or "").strip().casefold() in _CHINA \
        else "foreign"


def _status(count: int, target: int) -> str:
    if count <= 0:
        return "empty"
    if count < target:
        return "gap"
    if count >= 10:
        return "saturated"
    return "covered"


def build_coverage_matrix(repo, folder: str) -> dict:
    nodes = repo.list_chain_nodes(folder)
    records = repo.list_entity_coverage_records(folder)
    cells: list[dict] = []
    for node in nodes:
        configured = node.get("applicable_entity_types") or node.get("entity_types")
        applicable = [item for item in (configured or OBJECT_CATEGORIES)
                      if item in OBJECT_CATEGORIES]
        high_value = bool(node.get("high_centrality") or
                          node.get("high_market_impact") or
                          node.get("high_research_value"))
        target = 8 if high_value else 3
        for entity_type in applicable:
            for region in REGIONS:
                members = {
                    row["entity_id"] for row in records
                    if row["chain_stage"] == node["name"] and
                    row["entity_type"] == entity_type and
                    _region(row) == region and
                    row["status"] in QUALIFIED_STATUSES and
                    int(row.get("evidence_count") or 0) > 0
                }
                count = len(members)
                cell_id = stable_id(
                    "ecv", repo.industry_id(folder), node["id"], entity_type, region)
                cells.append({
                    "id": cell_id,
                    "source_type": "entity_evidence",
                    "subdomain": str(node.get("subdomain") or node["name"]),
                    "chain_stage": node["name"],
                    "entity_type": entity_type,
                    "region": region,
                    "qualified_count": count,
                    "breadth_target": 3,
                    "depth_target": 8 if high_value else None,
                    "target": target,
                    "maximum": 10,
                    "gap": max(0, target - count),
                    "status": _status(count, target),
                    "high_value": high_value,
                    "priority": min(100, int(node.get("priority") or
                                              (90 if high_value else 60)) +
                                    (5 if region == "china" else 0)),
                })
    cells.sort(key=lambda cell: (
        cell["chain_stage"], cell["entity_type"], cell["region"]))
    return {
        "industry": folder,
        "object_categories": list(OBJECT_CATEGORIES),
        "regions": list(REGIONS),
        "cells": cells,
        "gap_count": sum(cell["status"] in {"empty", "gap"} for cell in cells),
        "known_coverage": True,
        "completeness_proven": False,
        "algorithm_version": ALGORITHM_VERSION,
        "round_history": [],
    }


def _zero_gain(round_record: dict) -> bool:
    return sum(max(0, int(round_record.get(key) or 0)) for key in (
        "entities", "nodes", "relationships", "coverage_units")) == 0


def plan_entity_frontier(matrix: dict, *, round_no: int) -> CoverageFrontier:
    gaps = [dict(cell) for cell in matrix.get("cells", [])
            if cell.get("status") in {"empty", "gap", "thin", "partial"}]
    gaps.sort(key=lambda cell: (
        -int(bool(cell.get("high_value"))), -int(cell.get("priority") or 0),
        -int(cell.get("gap") or max(0, int(cell.get("target") or 0) -
                                    int(cell.get("qualified_count") or 0))),
        str(cell.get("chain_stage") or ""), str(cell.get("entity_type") or ""),
        str(cell.get("region") or "")))
    entity_queries, relation_queries = [], []
    for cell in gaps:
        language = "zh" if cell.get("region") == "china" else "en"
        entity_queries.append({
            "cell_id": cell.get("id"), "round_no": round_no, "language": language,
            "family": "high_value_depth" if cell.get("high_value") else "breadth_gap",
            "query": " ".join(str(value) for value in (
                cell.get("chain_stage"), cell.get("entity_type"), cell.get("region"),
                "official registration evidence") if value),
        })
        relation_queries.append({
            "cell_id": cell.get("id"), "round_no": round_no, "language": language,
            "query": f"{cell.get('chain_stage', '')} relationship document assertion evidence",
            "requires_evidence": True,
        })
    history = list(matrix.get("round_history") or [])
    two_zero = len(history) >= 2 and all(_zero_gain(row) for row in history[-2:])
    stopping_reason = None
    if two_zero:
        stopping_reason = ("coverage_gaps_retained" if gaps else
                           "converged_two_zero_marginal_rounds")
    return CoverageFrontier(gaps, entity_queries, relation_queries, stopping_reason)


def _domain(url: object) -> str:
    try:
        return urlsplit(str(url or "")).netloc.casefold().removeprefix("www.")
    except ValueError:
        return ""


def _identity_rows(repo, folder: str, candidate: dict) -> tuple[list[dict], list[dict]]:
    kind = str(candidate.get("type") or candidate.get("kind") or "company")
    country = str(candidate.get("country") or "")
    identifiers = {str(key).casefold(): str(value).strip()
                   for key, value in (candidate.get("external_ids") or {}).items()
                   if str(value).strip()}
    names = [candidate.get("name"), candidate.get("name_en"),
             *(candidate.get("aliases") or [])]
    by_id: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    with repo.connection() as con:
        for scheme, value in identifiers.items():
            row = con.execute("""SELECT e.* FROM entity_identifiers i
                JOIN entities e ON e.id=i.entity_id WHERE i.scheme=? AND i.value=?""",
                (scheme, value)).fetchone()
            if row:
                by_id[row["id"]] = dict(row)
        for name in names:
            normalized = normalized_name(name)
            if not normalized:
                continue
            rows = con.execute("""SELECT e.* FROM entity_names n JOIN entities e
                ON e.id=n.entity_id WHERE n.kind=? AND n.country=?
                AND n.normalized_name=?""", (kind, country, normalized)).fetchall()
            by_name.update({row["id"]: dict(row) for row in rows})
    return list(by_id.values()), list(by_name.values())


def resolve_entity_candidate(repo, folder: str, candidate: dict) -> dict:
    name = str(candidate.get("name") or "").strip()
    kind = str(candidate.get("type") or candidate.get("kind") or "company")
    if not name or kind not in OBJECT_CATEGORIES:
        raise ValueError("entity candidate requires a supported type and non-empty name")
    id_matches, name_matches = _identity_rows(repo, folder, candidate)
    all_matches = {row["id"]: row for row in [*id_matches, *name_matches]}
    if len(all_matches) > 1 or len(id_matches) > 1:
        return {"decision": "manual_review", "reason": "ambiguous_identity",
                "entity_id": None, "candidate": dict(candidate)}
    existing = next(iter(all_matches.values()), None)
    if existing:
        existing_ids = {str(key).casefold(): str(value).strip()
                        for key, value in json_value(
                            existing.get("external_ids_json"), {}).items()}
        candidate_ids = {str(key).casefold(): str(value).strip()
                         for key, value in (candidate.get("external_ids") or {}).items()
                         if str(value).strip()}
        if any(scheme in existing_ids and existing_ids[scheme] != value
               for scheme, value in candidate_ids.items()):
            return {"decision": "manual_review",
                    "reason": "registration_identifier_conflict",
                    "entity_id": existing["id"], "candidate": dict(candidate)}
        existing_metadata = json_value(existing.get("metadata_json"), {})
        old_domain = _domain(existing_metadata.get("official_url") or
                             existing_metadata.get("official_website"))
        new_domain = _domain(candidate.get("official_url") or
                             candidate.get("official_website"))
        if old_domain and new_domain and old_domain != new_domain:
            return {"decision": "manual_review", "reason": "official_website_conflict",
                    "entity_id": existing["id"], "candidate": dict(candidate)}
        payload = dict(candidate)
        aliases = {str(alias).strip() for alias in payload.get("aliases", [])
                   if str(alias).strip()}
        if normalized_name(name) != normalized_name(existing["canonical_name"]):
            aliases.add(name)
        payload["aliases"] = sorted(aliases)
        entity_id = repo.upsert_entity(folder, payload, str(payload.get("chain") or ""))
        return {"decision": "merged", "reason": "verified_identity_match",
                "entity_id": entity_id, "candidate": payload}
    entity_id = repo.upsert_entity(folder, candidate, str(candidate.get("chain") or ""))
    return {"decision": "created", "reason": "new_distinct_identity",
            "entity_id": entity_id, "candidate": dict(candidate)}
