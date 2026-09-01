"""Credential-free bootstrap over observed public documents.

Adapters are deliberately injected: unit tests stay deterministic while a native
release gate may provide a network adapter.  Seed catalogs and task packages are
never accepted as observations.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


class PublicSourceAdapter(Protocol):
    def collect(self, industry: str) -> dict: ...


class ReviewedFeedAdapter:
    """Fetch only user-reviewed public feed endpoints from the current industry."""

    def __init__(self, store, *, timeout: float = 12.0, limit: int = 40):
        self.store, self.timeout, self.limit = store, timeout, limit

    def collect(self, industry: str) -> dict:
        import feedparser
        import requests
        documents = []
        sources = self.store.get_sources()
        for category, rows in sources.items():
            if not isinstance(rows, list):
                continue
            for source in rows:
                if len(documents) >= self.limit or not isinstance(source, dict):
                    break
                if source.get("monitoring_status") not in {"active", "trusted"}:
                    continue
                feed_url = source.get("rss_url") or source.get("feed_url")
                if not _url(feed_url) or not _url(source.get("url")):
                    continue
                try:
                    response = requests.get(str(feed_url), timeout=self.timeout,
                                            headers={"User-Agent": "IntDog/2.3 public-bootstrap"})
                    response.raise_for_status()
                except requests.RequestException:
                    continue
                parsed = feedparser.parse(response.content)
                for entry in parsed.entries[: max(0, self.limit - len(documents))]:
                    link = str(entry.get("link") or "")
                    content = str(entry.get("summary") or entry.get("description") or "")
                    published = str(entry.get("published") or entry.get("updated") or "")
                    if _url(link) and content and published:
                        documents.append({
                            "title": str(entry.get("title") or link), "url": link,
                            "content": content, "published_at": published,
                            "collected_at": datetime.now(timezone.utc).isoformat(),
                            "publisher": str(source.get("name") or urlparse(link).netloc),
                            "publisher_url": source["url"],
                            "publisher_category": category,
                            "publisher_identity_verified": True, "reachable": True,
                            "category": "papers" if category == "journals" else "news",
                        })
        return {"mode": "public_credential_free", "provider_calls": 0,
                "documents": documents, "entities": [],
                "chain_nodes": [], "chain_edges": []}


def _url(value: object) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def collect_public_bootstrap(adapter: PublicSourceAdapter, *, industry: str,
                             output_dir: str | Path, store=None) -> dict:
    """Collect and persist only concrete public observations, then apply NOM-01."""
    raw = adapter.collect(industry)
    if not isinstance(raw, dict) or raw.get("mode") != "public_credential_free":
        raise ValueError("adapter must return public_credential_free observations")
    collected_at = datetime.now(timezone.utc).isoformat()
    documents, publishers, document_ids = [], {}, {}
    for item in raw.get("documents", []):
        if not isinstance(item, dict) or not _url(item.get("url")):
            continue
        content = str(item.get("content") or "")
        publisher = str(item.get("publisher") or "").strip()
        publisher_url = str(item.get("publisher_url") or "")
        if (not content or not publisher or not _url(publisher_url)
                or item.get("publisher_identity_verified") is not True
                or item.get("reachable") is not True
                or not item.get("published_at")):
            continue
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document = {
            "title": str(item.get("title") or item["url"]), "url": item["url"],
            "publisher": publisher, "published_at": item["published_at"],
            "collected_at": str(item.get("collected_at") or collected_at),
            "content_sha256": digest,
        }
        documents.append(document)
        publishers[publisher.casefold()] = {
            "name": publisher, "url": publisher_url,
            "category": str(item.get("publisher_category") or "unknown"),
            "reachable": True, "identity_verified": True,
        }
        if store is not None:
            document_ids[item["url"]] = store.service.repo.upsert_document(
                store.folder, str(item.get("category") or "news"),
                str(item["published_at"])[:10], {
                    **document, "content_hash": digest, "retrieved_at": document["collected_at"],
                    "source": publisher, "source_url": publisher_url,
                    "source_category": item.get("publisher_category") or "news",
                    "review_status": "unreviewed", "evidence_status": "collected",
                })
    known_urls = {item["url"] for item in documents}
    entities = []
    for item in raw.get("entities", []):
        refs = [url for url in item.get("document_urls", []) if url in known_urls]
        if not (item.get("name") and item.get("type") and refs):
            continue
        entity = {**item, "status": "candidate", "evidence": refs}
        entities.append(entity)
        if store is not None:
            entity["id"] = store.service.repo.upsert_entity(store.folder, {
                **entity, "references": [{"document_id": document_ids[url]}
                                           for url in refs if url in document_ids],
            }, str(item.get("chain") or ""))
    nodes = [dict(item) for item in raw.get("chain_nodes", [])
             if isinstance(item, dict) and item.get("id") is not None
             and item.get("name") and isinstance(item.get("order"), int)]
    node_ids = {str(item["id"]) for item in nodes}
    persisted_nodes = {}
    if store is not None:
        for item in nodes:
            persisted_nodes[str(item["id"])] = store.service.repo.upsert_chain_node(
                store.folder, {**item, "status": "candidate"})
    edges = []
    for item in raw.get("chain_edges", []):
        refs = [url for url in item.get("document_urls", []) if url in known_urls]
        if (str(item.get("source")) not in node_ids or
                str(item.get("target")) not in node_ids or not refs):
            continue
        edge = {**item, "evidence": refs, "status": "candidate"}
        edges.append(edge)
        if store is not None:
            edge_id = store.service.repo.upsert_chain_edge(store.folder, {
                **edge, "src_node_id": persisted_nodes[str(item["source"])],
                "dst_node_id": persisted_nodes[str(item["target"])],
            })
            for url in refs:
                store.service.repo.add_chain_edge_evidence(
                    edge_id, "supports", document_id=document_ids[url], url=url)
    categories = {item["category"] for item in publishers.values()}
    counts = {"publishers": len(publishers), "source_categories": len(categories),
              "documents": len({item["url"] for item in documents}),
              "independent_publishers": len({item["publisher"].casefold() for item in documents}),
              "entity_candidates": len(entities),
              "entity_types": len({item["type"] for item in entities}),
              "chain_nodes": len(nodes) if len({item["order"] for item in nodes}) == len(nodes) else 0,
              "chain_edges": len(edges), "provider_calls": int(raw.get("provider_calls", -1))}
    thresholds = {"publishers": 3, "source_categories": 2, "documents": 6,
                  "independent_publishers": 2, "entity_candidates": 5,
                  "entity_types": 3, "chain_nodes": 3, "chain_edges": 2}
    failures = [f"threshold:{key}:{counts[key]}:{minimum}" for key, minimum in thresholds.items()
                if counts[key] < minimum]
    if counts["provider_calls"] != 0:
        failures.append(f"provider_calls:{counts['provider_calls']}")
    binding = {}
    if store is not None:
        tasks = [item for item in store.service.repo.list_tasks(store.folder)
                 if item.get("operation") in {"bootstrap", "public-bootstrap"}
                 and item.get("provider") == "public_sources"]
        if tasks:
            run_id = tasks[0]["id"]
        else:
            run_id = store.service.repo.create_task(
                folder=store.folder, operation="public-bootstrap",
                input={"mode": "public_credential_free"}, origin="cli",
                provider="public_sources")["id"]
        database = store.service.repo.db_path
        digest = hashlib.sha256()
        with database.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        binding = {"data_root": str(store.data_root.resolve()),
                   "industry_root": str(store.root.resolve()),
                   "database": str(database.resolve()),
                   "database_sha256": digest.hexdigest(),
                   "job_run_id": run_id, "provider_ledger_calls": 0}
    record = {"schema": "intdog-nom01-v1", "mode": "public_credential_free",
              "industry": industry, "collected_at": collected_at,
              "publishers": list(publishers.values()), "documents": documents,
              "entities": entities, "chain_nodes": nodes, "chain_edges": edges,
              "provider_calls": counts["provider_calls"],
              "binding": binding,
              "provenance": {"adapter": type(adapter).__name__, "seed_used": False,
                             "taskpack_used": False}}
    output = Path(output_dir)
    _write(output / "nom01-record.json", record)
    status = "completed" if not failures else "partial"
    result = {"status": status, "state": status,
              "oracle": {"passed": not failures, "counts": counts, "failures": failures},
              "record_path": str(output / "nom01-record.json")}
    _write(output / "bootstrap_status.json", result)
    return result
