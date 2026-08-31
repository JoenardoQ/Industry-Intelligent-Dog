"""Claim–Evidence compilation with independent aggregation axes."""

from __future__ import annotations

from collections import Counter


def _weight(evidence: dict) -> float:
    confidence = evidence.get("confidence")
    confidence = 0.5 if confidence is None else max(0.0, min(1.0, float(confidence)))
    authority = 1.0 if evidence.get("publisher_verification") == "verified" else 0.75
    return round(confidence * authority, 4)


def build_evidence_graph(raw_claims: list[dict], chains: list[dict]) -> dict:
    claims, counts = [], Counter()
    for claim in raw_claims:
        unique = {item["id"]: item for item in claim["evidence"]}
        evidence = list(unique.values())
        supports = [item for item in evidence if item["relation"] == "supports"]
        contradicts = [item for item in evidence if item["relation"] == "contradicts"]
        qualifies = [item for item in evidence if item["relation"] == "qualifies"]
        clusters = {item["resolved_cluster"] for item in supports
                    if item["resolved_cluster"] != "unknown"}
        support_weight = round(sum(_weight(item) for item in supports), 4)
        contradiction_weight = round(sum(_weight(item) for item in contradicts), 4)
        verified_single = any(item.get("publisher_verification") == "verified"
                              for item in supports)
        if contradicts:
            evidence_state = "contested"
        elif len(clusters) >= 2:
            evidence_state = "corroborated"
        elif supports:
            evidence_state = "single_source"
        else:
            evidence_state = "unsupported"
        authority_state = ("authoritative_support" if verified_single else
                           "unverified_support" if supports else "no_support")
        counts[evidence_state] += 1
        claims.append({
            "id": claim["id"], "subject_id": claim["subject_id"],
            "subject": claim.get("subject_name") or "", "predicate": claim["predicate"],
            "object": claim["object"], "qualifiers": claim["qualifiers"],
            "claim_status": claim["status"], "evidence_state": evidence_state,
            "authority_state": authority_state, "supports": len(supports),
            "contradicts": len(contradicts), "qualifies": len(qualifies),
            "support_weight": support_weight, "contradiction_weight": contradiction_weight,
            "independent_supporting_publishers": len(clusters),
            "publisher_clusters": sorted(clusters),
            "unknown_publisher_evidence": sum(item["resolved_cluster"] == "unknown"
                                              for item in evidence),
            "evidence_items": [{"id": item["id"], "relation": item["relation"],
                                "document_title": item.get("document_title") or "",
                                "document_url": item.get("document_url") or "",
                                "publisher_cluster": item["resolved_cluster"],
                                "publisher_verification": item.get("publisher_verification"),
                                "confidence": item.get("confidence"),
                                "excerpt": item.get("excerpt") or ""}
                               for item in evidence],
        })
    chain_gaps = [{"id": chain["id"], "name": chain["name"],
                   "coverage_status": chain["coverage_status"],
                   "entity_count": chain["entity_count"],
                   "evidenced_entities": chain["evidenced_entities"]}
                  for chain in chains if chain["coverage_status"] != "covered"]
    metrics = {"claims": len(claims), **{key: counts[key] for key in
               ("unsupported", "single_source", "contested", "corroborated")},
               "chain_nodes": len(chains), "chain_gaps": len(chain_gaps)}
    return {"kind": "evidence_graph", "metrics": metrics,
            "claims": claims, "chain_gaps": chain_gaps}
