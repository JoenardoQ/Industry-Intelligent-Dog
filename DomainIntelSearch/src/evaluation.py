"""Versioned, deterministic quality gates for retrieval and knowledge integrity."""

from __future__ import annotations

import json
from pathlib import Path


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def evaluate_fixture(payload: dict) -> dict:
    retrieval = payload.get("retrieval") or []
    publisher = payload.get("publisher_attribution") or []
    stories = payload.get("stories") or []
    entities = payload.get("entity_links") or []
    claims = payload.get("claims") or []

    predicted_pairs: set[tuple[str, str]] = set()
    gold_pairs: set[tuple[str, str]] = set()
    for rows, target in ((stories, predicted_pairs),):
        for left in rows:
            for right in rows:
                if left["id"] < right["id"] and left["predicted_story"] == right["predicted_story"]:
                    target.add((left["id"], right["id"]))
    for left in stories:
        for right in stories:
            if left["id"] < right["id"] and left["gold_story"] == right["gold_story"]:
                gold_pairs.add((left["id"], right["id"]))
    intersection = predicted_pairs & gold_pairs
    high_risk = [row for row in claims if row.get("risk") == "high"]
    scores = {
        "retrieval_precision": _ratio(sum(bool(row.get("relevant")) for row in retrieval), len(retrieval)),
        "publisher_attribution_accuracy": _ratio(sum(row.get("predicted") == row.get("gold") for row in publisher), len(publisher)),
        "story_pairwise_precision": _ratio(len(intersection), len(predicted_pairs)),
        "story_pairwise_recall": _ratio(len(intersection), len(gold_pairs)),
        "entity_link_accuracy": _ratio(sum(row.get("predicted") == row.get("gold") for row in entities), len(entities)),
        "high_risk_citation_coverage": _ratio(sum(bool(row.get("citations")) for row in high_risk), len(high_risk)),
    }
    thresholds = payload.get("thresholds") or {}
    failures = {name: {"score": score, "minimum": float(thresholds[name])}
                for name, score in scores.items()
                if name in thresholds and score < float(thresholds[name])}
    return {"fixture_version": payload.get("fixture_version"),
            "industry": payload.get("industry"), "scores": scores,
            "thresholds": thresholds, "passed": not failures, "failures": failures}


def evaluate_file(path: str | Path) -> dict:
    source = Path(path)
    return evaluate_fixture(json.loads(source.read_text(encoding="utf-8")))
