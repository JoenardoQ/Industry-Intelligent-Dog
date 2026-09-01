"""Conservative, auditable document deduplication.

Independent publishers are evidence, not duplicates. Text similarity is only
used automatically inside one publisher cluster and a bounded time window.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

from intdog_core.models import canonical_url
from intdog_core.source_trust import publisher_key


ALGORITHM_VERSION = "document-dedup-v1"
_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\u3400-\u9fff]+", re.UNICODE)


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return _SPACE.sub(" ", _PUNCT.sub(" ", text)).strip()


def content_fingerprint(item: dict) -> str:
    """Hash content, never location; an URL is not document content."""
    title = normalize_text(item.get("title"))
    abstract = normalize_text(item.get("abstract") or item.get("summary"))
    return hashlib.sha256(f"{title}\n{abstract}".encode("utf-8")).hexdigest()[:24]


def _date(item: dict) -> datetime | None:
    value = str(item.get("published_at") or item.get("published") or
                item.get("date") or "")[:10]
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _near_in_time(left: dict, right: dict, days: int = 3) -> bool:
    left_date, right_date = _date(left), _date(right)
    return not left_date or not right_date or abs((left_date - right_date).days) <= days


def _series_markers(value: object) -> set[str]:
    text = normalize_text(value)
    tokens = text.split()
    markers = {token for token in tokens
               if token in {"上", "中", "下", "一", "二", "三", "四", "五"}}
    markers.update(re.findall(
        r"\b(?:part|episode|chapter|version|vol|v)\s*\d+\b", text))
    return markers


def duplicate_reason(left: dict, right: dict) -> str:
    left_url = canonical_url(left.get("url", ""))
    right_url = canonical_url(right.get("url", ""))
    if left_url and left_url == right_url:
        return "canonical_url"

    left_title, right_title = normalize_text(left.get("title")), normalize_text(
        right.get("title"))
    left_abstract = normalize_text(left.get("abstract") or left.get("summary"))
    right_abstract = normalize_text(right.get("abstract") or right.get("summary"))

    # Exact rich content across mirrors is a copy, not independent reporting.
    if (left_title and left_title == right_title and left_abstract and
            left_abstract == right_abstract and len(left_abstract) >= 80):
        return "content_fingerprint"

    # Empty/short summaries cannot prove cross-publisher duplication.
    if publisher_key(left) != publisher_key(right) or not _near_in_time(left, right):
        return ""
    if left_title and left_title == right_title:
        return "publisher_exact_title"
    if min(len(left_title), len(right_title)) >= 18:
        left_markers, right_markers = (_series_markers(left.get("title")),
                                       _series_markers(right.get("title")))
        if left_markers and right_markers and left_markers != right_markers:
            return ""
        ratio = SequenceMatcher(None, left_title, right_title, autojunk=False).ratio()
        if ratio >= 0.94:
            return "publisher_near_title"
    return ""


def _richness(item: dict) -> tuple[int, int, int, int]:
    abstract = str(item.get("abstract") or item.get("summary") or "")
    authors = item.get("authors") or item.get("author") or []
    author_count = len(authors) if isinstance(authors, list) else int(bool(authors))
    return (len(abstract), author_count, len(str(item.get("title") or "")),
            -len(str(item.get("url") or "")))


def _item_order(item: dict) -> tuple:
    """Choose one representative independently of caller input order."""
    richness = _richness(item)
    syndicated = bool(item.get("syndicated_from") or
                      item.get("original_publisher_url") or item.get("original_url"))
    return (*(-value for value in richness), syndicated,
            canonical_url(item.get("url", "")), str(item.get("id") or ""),
            normalize_text(item.get("title")))


def _document_provenance(item: dict) -> list[dict]:
    """Retain every absorbed Document-to-Source observation in the merged record."""
    rows = list(item.get("document_provenance") or [])
    document_id = str(item.get("document_id") or item.get("id") or "")
    source_id = str(item.get("source_id") or "")
    url = canonical_url(item.get("url", ""))
    if document_id or source_id:
        rows.append({
            "document_id": document_id,
            "source_id": source_id,
            "url": url,
            "publisher_cluster": publisher_key(item),
        })
    unique: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized = {
            "document_id": str(row.get("document_id") or ""),
            "source_id": str(row.get("source_id") or ""),
            "url": canonical_url(row.get("url", "")),
            "publisher_cluster": str(row.get("publisher_cluster") or ""),
        }
        key = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
        unique[key] = normalized
    return [unique[key] for key in sorted(unique)]


def merge_duplicate(primary: dict, duplicate: dict, reason: str) -> dict:
    richer, other = sorted((primary, duplicate), key=_item_order)
    merged = dict(richer)
    for key, value in other.items():
        if key not in merged or merged[key] in (None, "", [], {}):
            merged[key] = value
    urls = list(dict.fromkeys(
        [*primary.get("duplicate_urls", []), *duplicate.get("duplicate_urls", []),
         str(primary.get("url") or ""), str(duplicate.get("url") or "")]))
    canonical = canonical_url(merged.get("url", ""))
    merged["url"] = canonical or merged.get("url", "")
    merged["duplicate_urls"] = [url for url in urls if url and canonical_url(url) != canonical]
    merged["duplicate_count"] = max(
        int(primary.get("duplicate_count") or 1),
        int(duplicate.get("duplicate_count") or 1)) + 1
    merged["document_provenance"] = _document_provenance(primary) + [
        row for row in _document_provenance(duplicate)
        if row not in _document_provenance(primary)]
    merged["document_provenance"] = sorted(
        merged["document_provenance"],
        key=lambda row: (row["document_id"], row["source_id"], row["url"],
                         row["publisher_cluster"]))
    merged["dedup_reason"] = reason
    merged["dedup_algorithm"] = ALGORITHM_VERSION
    merged["content_hash"] = content_fingerprint(merged)
    return merged


def collapse_batch(items: list[dict]) -> tuple[list[dict], dict]:
    kept: list[dict] = []
    reasons: dict[str, int] = {}
    for item in sorted(items, key=_item_order):
        match = next(((index, duplicate_reason(existing, item))
                      for index, existing in enumerate(kept)
                      if duplicate_reason(existing, item)), None)
        if not match:
            kept.append(item)
            continue
        index, reason = match
        kept[index] = merge_duplicate(kept[index], item, reason)
        reasons[reason] = reasons.get(reason, 0) + 1
    kept.sort(key=_item_order)
    return kept, {"input": len(items), "kept": len(kept),
                  "duplicates": len(items) - len(kept), "reasons": reasons,
                  "algorithm": ALGORITHM_VERSION}


def suppress_replays(items: list[dict], historical: list[dict]) -> tuple[list[dict], dict]:
    kept, reasons = [], {}
    for item in items:
        reason = next((duplicate_reason(previous, item) for previous in historical
                       if duplicate_reason(previous, item)), "")
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            kept.append(item)
    return kept, {"input": len(items), "kept": len(kept),
                  "suppressed_replays": len(items) - len(kept), "reasons": reasons,
                  "algorithm": ALGORITHM_VERSION}


def plan_history(items: list[dict]) -> dict:
    """Build a non-destructive link-suppression plan for persisted history."""
    representatives: list[dict] = []
    groups: list[dict] = []
    by_url: dict[str, int] = {}
    by_content: dict[str, int] = {}
    by_publisher_title: dict[tuple[str, str], int] = {}
    by_publisher: dict[str, list[int]] = {}
    reasons: dict[str, int] = {}

    ordered = sorted(items, key=lambda item: (
        str(item.get("date") or ""), str(item.get("published_at") or ""),
        str(item.get("id") or ""), str(item.get("category") or "")))
    for item in ordered:
        url = canonical_url(item.get("url", ""))
        title = normalize_text(item.get("title"))
        abstract = normalize_text(item.get("abstract") or item.get("summary"))
        publisher = publisher_key(item)
        content = content_fingerprint(item) if len(abstract) >= 80 else ""
        index = by_url.get(url) if url else None
        reason = "canonical_url" if index is not None else ""
        if index is None and content:
            index = by_content.get(content)
            reason = "content_fingerprint" if index is not None else ""
        if index is None and title:
            candidate = by_publisher_title.get((publisher, title))
            if candidate is not None and _near_in_time(representatives[candidate], item):
                index, reason = candidate, "publisher_exact_title"
        if index is None:
            for candidate in reversed(by_publisher.get(publisher, [])[-50:]):
                candidate_reason = duplicate_reason(representatives[candidate], item)
                if candidate_reason:
                    index, reason = candidate, candidate_reason
                    break
        if index is None:
            index = len(representatives)
            representatives.append(dict(item))
            groups.append({"keeper": dict(item), "duplicates": [], "reasons": {}})
            by_publisher.setdefault(publisher, []).append(index)
        else:
            keeper = groups[index]["keeper"]
            merged = merge_duplicate(keeper, item, reason)
            for identity in ("id", "category", "date", "published_at"):
                if identity in keeper:
                    merged[identity] = keeper[identity]
            groups[index]["keeper"] = merged
            groups[index]["duplicates"].append(dict(item))
            groups[index]["reasons"][reason] = groups[index]["reasons"].get(reason, 0) + 1
            representatives[index] = merged
            reasons[reason] = reasons.get(reason, 0) + 1
        if url:
            by_url[url] = index
        if content:
            by_content[content] = index
        if title:
            by_publisher_title[(publisher, title)] = index

    duplicate_groups = [group for group in groups if group["duplicates"]]
    return {"algorithm": ALGORITHM_VERSION, "input_links": len(items),
            "kept_links": len(items) - sum(len(group["duplicates"])
                                            for group in duplicate_groups),
            "suppressed_links": sum(len(group["duplicates"])
                                    for group in duplicate_groups),
            "duplicate_groups": duplicate_groups, "reasons": reasons}
