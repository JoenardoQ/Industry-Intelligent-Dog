"""Resumable, time-stratified evidence backfill for long-duration reports."""

from __future__ import annotations

import math
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests
import feedparser
from email.utils import parsedate_to_datetime


@dataclass(frozen=True)
class HorizonPolicy:
    name: str
    days: int
    bucket_days: int
    target: int
    target_low: int
    target_high: int
    minimum_total_ratio: float = 0.75
    minimum_bucket_ratio: float = 0.90
    bucket_mode: str = "fixed"


POLICIES = {
    "weekly": HorizonPolicy("weekly", 7, 1, 42, 32, 53),
    "monthly": HorizonPolicy("monthly", 30, 7, 180, 135, 225),
    "quarterly": HorizonPolicy("quarterly", 90, 30, 540, 405, 675,
                                bucket_mode="calendar_month"),
    "semiannual": HorizonPolicy("semiannual", 183, 30, 1080, 824, 1373,
                                 bucket_mode="calendar_month"),
    "biennial": HorizonPolicy("biennial", 730, 30, 4500, 3600, 5400,
                               minimum_total_ratio=.80,
                               bucket_mode="calendar_month"),
    "fiveyear": HorizonPolicy("fiveyear", 1826, 30, 12000, 10500, 13500,
                               minimum_total_ratio=.875,
                               bucket_mode="calendar_month"),
}


class HistoryCoverageError(RuntimeError):
    pass


def _buckets(policy: HorizonPolicy, end: date) -> list[tuple[date, date]]:
    start = end - timedelta(days=policy.days - 1)
    if policy.bucket_mode == "calendar_month":
        rows = []
        cursor = start
        while cursor <= end:
            if cursor.month == 12:
                following = date(cursor.year + 1, 1, 1)
            else:
                following = date(cursor.year, cursor.month + 1, 1)
            bucket_end = min(end, following - timedelta(days=1))
            rows.append((cursor, bucket_end))
            cursor = bucket_end + timedelta(days=1)
        return rows
    rows = []
    cursor = start
    while cursor <= end:
        bucket_end = min(end, cursor + timedelta(days=policy.bucket_days - 1))
        rows.append((cursor, bucket_end))
        cursor = bucket_end + timedelta(days=1)
    return rows


def plan_horizon(horizon: str, *, end: date | None = None,
                 policy: HorizonPolicy | None = None) -> dict:
    if horizon not in POLICIES and policy is None:
        raise ValueError(f"未知历史周期：{horizon}")
    policy = policy or POLICIES[horizon]
    end = end or datetime.now().date()
    buckets = _buckets(policy, end)
    days = [int((finish - start).days) + 1 for start, finish in buckets]
    exact = [policy.target * count / policy.days for count in days]
    targets = [math.floor(value) for value in exact]
    remainder = policy.target - sum(targets)
    order = sorted(range(len(buckets)),
                   key=lambda index: (exact[index] - targets[index], -index),
                   reverse=True)
    for index in order[:remainder]:
        targets[index] += 1
    return {
        "horizon": horizon, "window_start": buckets[0][0].isoformat(),
        "window_end": end.isoformat(), "target": policy.target,
        "target_range": [policy.target_low, policy.target_high],
        "minimum_month_coverage": policy.minimum_bucket_ratio,
        "buckets": [{
            "start": start.isoformat(), "end": finish.isoformat(),
            "days": bucket_days, "target": target,
            "daily_density": round(target / bucket_days, 4),
        } for (start, finish), bucket_days, target in zip(
            buckets, days, targets, strict=True)],
    }


def _qualified_history_item(item: dict) -> tuple[bool, str]:
    if item.get("duplicate") or item.get("is_duplicate"):
        return False, "duplicate"
    status = str(item.get("review_status") or "").casefold()
    if status in {"rejected", "quarantined", "invalid"}:
        return False, "low_quality"
    raw_quality = item.get("credibility", item.get("quality", .75))
    if isinstance(raw_quality, (int, float)) and not isinstance(raw_quality, bool):
        if not math.isfinite(float(raw_quality)) or float(raw_quality) < .60:
            return False, "low_quality"
    if not _date(item.get("published_at") or item.get("date")):
        return False, "low_quality"
    if not str(item.get("url") or "").strip() or not str(item.get("title") or "").strip():
        return False, "low_quality"
    return True, ""


def evaluate_history_items(items: list[dict], horizon: str, *,
                           end: date | None = None,
                           policy: HorizonPolicy | None = None,
                           key_fn=None) -> dict:
    policy = policy or POLICIES[horizon]
    end = end or datetime.now().date()
    plan = plan_horizon(horizon, end=end, policy=policy)
    rejected_duplicates = 0
    rejected_low_quality = 0
    unique: dict[str, dict] = {}
    for item in items:
        accepted, reason = _qualified_history_item(item)
        if not accepted:
            if reason == "duplicate":
                rejected_duplicates += 1
            else:
                rejected_low_quality += 1
            continue
        key = str(key_fn(item) if key_fn else item.get("canonical_url") or
                  item.get("url") or f"{item.get('title')}:{_date(item.get('date'))}")
        if key in unique:
            rejected_duplicates += 1
            continue
        unique[key] = item
    bucket_rows = []
    bucket_items: list[list[dict]] = []
    for bucket in plan["buckets"]:
        values = [item for item in unique.values()
                  if bucket["start"] <= _date(
                      item.get("published_at") or item.get("date")) <= bucket["end"]]
        minimum = max(1, math.floor(int(bucket["target"]) * .60))
        bucket_items.append(values)
        bucket_rows.append({**bucket, "count": len(values), "minimum": minimum,
                            "covered": len(values) >= minimum})
    positive_counts = [row["count"] for row in bucket_rows if row["count"] > 0]
    median = float(statistics.median(positive_counts)) if positive_counts else 0.0
    overflow = []
    for row, values in zip(bucket_rows, bucket_items, strict=True):
        if median and row["count"] > median * 3:
            reasons = sorted({str(item.get("overflow_reason") or
                                  item.get("event_peak_reason") or "").strip()
                              for item in values
                              if item.get("overflow_reason") or item.get("event_peak_reason")})
            overflow.append({"start": row["start"], "end": row["end"],
                             "count": row["count"], "median": median,
                             "justified": bool(reasons), "reasons": reasons})
    covered = sum(row["covered"] for row in bucket_rows)
    required_buckets = math.ceil(len(bucket_rows) * policy.minimum_bucket_ratio)
    publishers = {str(item.get("source_domain") or item.get("source") or "").casefold()
                  for item in unique.values()
                  if item.get("source_domain") or item.get("source")}
    gaps = []
    unexplained = [row for row in overflow if not row["justified"]]
    if unexplained:
        gaps.append({"code": "unexplained_bucket_concentration",
                     "count": len(unexplained), "detail": unexplained})
    if len(unique) < policy.target_low:
        gaps.append({"code": "qualified_document_gap",
                     "current": len(unique), "target": policy.target_low})
    if covered < required_buckets:
        gaps.append({"code": "month_coverage_gap", "current": covered,
                     "target": required_buckets})
    if len(publishers) < 5:
        gaps.append({"code": "publisher_diversity_gap", "current": len(publishers),
                     "target": 5})
    return {
        **{key: value for key, value in plan.items() if key != "buckets"},
        "required_total": policy.target_low, "admitted_total": len(unique),
        "buckets_total": len(bucket_rows), "buckets_covered": covered,
        "required_buckets": required_buckets,
        "coverage_ratio": round(covered / len(bucket_rows), 4) if bucket_rows else 0.0,
        "publisher_count": len(publishers), "ready": not gaps,
        "buckets": bucket_rows, "overflow_buckets": overflow, "gaps": gaps,
        "rejected_low_quality": rejected_low_quality,
        "rejected_duplicates": rejected_duplicates,
    }


def _query(config: dict) -> str:
    domain = config.get("domain", {}) or {}
    keywords = [str(value).strip() for value in domain.get("keywords", [])
                if str(value).isascii() and len(str(value).strip()) > 2]
    name = str(domain.get("name_en") or domain.get("name") or "").strip()
    values = list(dict.fromkeys(([name] if name else []) + keywords))[:6]
    joined = " OR ".join(f'"{value}"' if " " in value else value for value in values)
    return f"({joined})" if len(values) > 1 else joined


def _get_json(session, url: str, *, params: dict, headers: dict | None = None,
              attempts: int = 3, timeout: int = 30) -> dict:
    """Bounded retry with useful diagnostics for rate limits and non-JSON bodies."""
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            response = session.get(url, params=params, headers=headers, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                retry = response.headers.get("Retry-After", "")
                try:
                    delay = min(12.0, max(1.0, float(retry)))
                except ValueError:
                    delay = min(8.0, 2.0 ** attempt)
                if attempt + 1 < attempts:
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                body = " ".join(response.text[:300].split())
                raise ValueError(f"供应商返回非 JSON：{body or '<empty>'}") from exc
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts and not getattr(exc, "response", None):
                time.sleep(min(4.0, 2.0 ** attempt))
                continue
            break
    assert last_error is not None
    raise last_error


def _date(value: object) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4:5] == "-":
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return ""


def fetch_gdelt(session, query: str, start: date, end: date, limit: int) -> list[dict]:
    payload = _get_json(session,
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={"query": query, "mode": "artlist", "format": "json",
                "maxrecords": min(250, max(1, limit)), "sort": "datedesc",
                "startdatetime": start.strftime("%Y%m%d000000"),
                "enddatetime": end.strftime("%Y%m%d235959")},
        headers={"User-Agent": "IntDog/4.0 (local industry research)"},
        attempts=1, timeout=12,
    )
    rows = []
    for item in (payload.get("articles") or []):
        published = _date(item.get("seendate"))
        url, title = str(item.get("url") or ""), str(item.get("title") or "").strip()
        if not published or not url or not title:
            continue
        rows.append({"title": title, "url": url, "published_at": published,
                     "date": published, "source": item.get("domain") or urlsplit(url).netloc,
                     "source_domain": item.get("domain") or urlsplit(url).netloc,
                     "category": "news", "abstract": "",
                     "history_provider": "gdelt_doc_2", "history_query": query,
                     "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "url_validation": "indexed_by_gdelt"})
    return rows


def fetch_openalex(session, query: str, start: date, end: date, limit: int) -> list[dict]:
    params = {"search": query.replace('"', "").replace("(", "").replace(")", ""),
                "filter": f"from_publication_date:{start},to_publication_date:{end}",
                "per_page": min(100, max(1, limit)),
                "select": "id,doi,title,publication_date,primary_location,authorships"}
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if api_key:
        params["api_key"] = api_key
    payload = _get_json(
        session, "https://api.openalex.org/works", params=params,
        headers={"User-Agent": "IntDog/4.0 (local industry research)"})
    rows = []
    for item in (payload.get("results") or []):
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        url = (location.get("landing_page_url") or item.get("doi") or item.get("id") or "")
        published, title = _date(item.get("publication_date")), str(item.get("title") or "").strip()
        if not published or not url or not title:
            continue
        authors = [str((row.get("author") or {}).get("display_name") or "")
                   for row in (item.get("authorships") or [])[:12]]
        rows.append({"title": title, "url": url, "published_at": published,
                     "date": published, "source": source.get("display_name") or "OpenAlex",
                     "authors": [value for value in authors if value], "category": "papers",
                     "abstract": "", "history_provider": "openalex",
                     "history_query": query,
                     "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "url_validation": "indexed_by_openalex"})
    return rows


def fetch_google_news(session, query: str, start: date, end: date,
                      limit: int) -> list[dict]:
    """Dated RSS fallback; Google is an index, never the claimed publisher."""
    clean = query.replace("(", "").replace(")", "")
    before = end + timedelta(days=1)
    search = f"{clean} after:{start.isoformat()} before:{before.isoformat()}"
    locales = (("zh-CN", "CN", "CN:zh-Hans"), ("en-US", "US", "US:en"))
    localized: list[list[dict]] = []
    for language, country, edition in locales:
        locale_rows, seen = [], set()
        parsed = None
        for attempt in range(2):
            response = session.get(
                "https://news.google.com/rss/search",
                params={"q": search, "hl": language, "gl": country, "ceid": edition},
                headers={"User-Agent": "Mozilla/5.0 IntDog/4.0"}, timeout=30)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            if getattr(parsed, "entries", []):
                break
            if attempt == 0:
                time.sleep(2.0)
        assert parsed is not None
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
            raise ValueError(f"Google News RSS 解析失败：{parsed.bozo_exception}")
        for item in parsed.entries:
            url, title = str(item.get("link") or ""), str(item.get("title") or "").strip()
            try:
                published = parsedate_to_datetime(str(item.get("published") or "")).date().isoformat()
            except (TypeError, ValueError, OverflowError):
                continue
            if not url or not title or url in seen:
                continue
            source = item.get("source") or {}
            publisher = str(source.get("title") if hasattr(source, "get") else "").strip()
            locale_rows.append({"title": title, "url": url, "published_at": published,
                         "date": published, "source": publisher or "Google News indexed source",
                         "source_domain": publisher or "news.google.com",
                         "category": "news", "abstract": "",
                         "origin": "china" if country == "CN" else "foreign",
                         "history_provider": "google_news_rss",
                         "history_query": search,
                         "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "url_validation": "indexed_by_google_news"})
            seen.add(url)
        localized.append(locale_rows)
    china_quota = math.ceil(limit * .60)
    rows = localized[0][:china_quota] + localized[1][:max(0, limit - china_quota)]
    chosen = {item["url"] for item in rows}
    for item in localized[0][china_quota:] + localized[1][max(0, limit - china_quota):]:
        if item["url"] not in chosen:
            rows.append(item); chosen.add(item["url"])
        if len(rows) >= limit:
            break
    return rows


def _manifest_path(store, horizon: str) -> Path:
    return store.one_time / "research" / "history" / f"{horizon}.json"


def evaluate_history(store, horizon: str, *, end: date | None = None,
                     policy: HorizonPolicy | None = None) -> dict:
    policy = policy or POLICIES[horizon]
    end = end or datetime.now().date()
    items = store.list_daily_range(days=policy.days, end_date=end.isoformat())
    return evaluate_history_items(
        items, horizon, end=end, policy=policy, key_fn=store._key)


def backfill_history(config: dict, store, horizon: str, *, target: int | None = None,
                     max_buckets: int | None = None, session=None,
                     gdelt_fetch=fetch_gdelt, openalex_fetch=fetch_openalex,
                     google_fetch=fetch_google_news) -> dict:
    if horizon not in POLICIES:
        raise ValueError(f"未知历史周期：{horizon}")
    policy = POLICIES[horizon]
    if target is not None:
        normalized_target = max(1, int(target))
        policy = HorizonPolicy(**{
            **asdict(policy), "target": normalized_target,
            "target_low": normalized_target, "target_high": normalized_target,
        })
    end = datetime.now().date()
    buckets = _buckets(policy, end)
    query = _query(config)
    if not query:
        raise ValueError("行业档案缺少可用于历史搜索的英文关键词")
    path = _manifest_path(store, horizon)
    manifest = store._read_json(path, {})
    manifest.update({"schema_version": "1.0", "horizon": horizon,
                     "policy": asdict(policy), "query": query,
                     "window_start": buckets[0][0].isoformat(),
                     "window_end": end.isoformat(), "status": "running",
                     "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    attempts = list(manifest.get("attempts", []))
    client = session or requests.Session()
    old_provider_state = manifest.get("provider_state") or {}
    old_failures = old_provider_state.get("failures") or {}
    provider_failures = {name: int(old_failures.get(name, 0) or 0)
                         for name in ("gdelt", "openalex", "google_news_rss")}
    disabled: set[str] = set(old_provider_state.get("circuit_open") or [])
    unconfigured: set[str] = set(old_provider_state.get("unconfigured") or [])
    if provider_failures["gdelt"] >= 3:
        disabled.add("gdelt")
    if openalex_fetch is fetch_openalex and not os.environ.get("OPENALEX_API_KEY", "").strip():
        disabled.add("openalex")
        unconfigured.add("openalex")
    per_bucket = max(1, math.ceil(policy.target / len(buckets)))
    resume_minimum = max(1, math.floor(per_bucket * .60))
    completed = {row.get("key") for row in attempts
                 if row.get("status") in {"completed", "usable"}
                 and sum((row.get("saved") or {}).values()) >= resume_minimum}
    pending = [(start, finish) for start, finish in buckets
               if f"{start}:{finish}" not in completed]
    if max_buckets is not None:
        pending = pending[:max(0, int(max_buckets))]
    for index, (start, finish) in enumerate(pending, 1):
        key = f"{start}:{finish}"
        saved = {"news": 0, "papers": 0}; errors = []
        try:
            news = ([] if "gdelt" in disabled else
                    gdelt_fetch(client, query, start, finish, per_bucket))
        except Exception as exc:  # provider error is persisted, never an empty success
            news = []; provider_failures["gdelt"] += 1
            errors.append({"provider": "gdelt", "error": type(exc).__name__,
                           "message": str(exc)[:500]})
            if provider_failures["gdelt"] >= 3:
                disabled.add("gdelt")
        if len(news) < per_bucket:
            try:
                fallback = ([] if "google_news_rss" in disabled else google_fetch(
                    client, query, start, finish, per_bucket - len(news)))
                known = {str(item.get("url") or "") for item in news}
                news.extend(item for item in fallback
                            if str(item.get("url") or "") not in known)
                if not fallback and not news:
                    errors.append({"provider": "google_news_rss",
                                   "error": "EmptyResult",
                                   "message": "日期查询返回空集合；保留为待重试桶"})
            except Exception as exc:
                provider_failures["google_news_rss"] += 1
                errors.append({"provider": "google_news_rss",
                               "error": type(exc).__name__,
                               "message": str(exc)[:500]})
                if provider_failures["google_news_rss"] >= 3:
                    disabled.add("google_news_rss")
        try:
            papers = ([] if "openalex" in disabled else openalex_fetch(
                client, query, start, finish, math.ceil(per_bucket * .40)))
        except Exception as exc:
            papers = []; provider_failures["openalex"] += 1
            errors.append({"provider": "openalex", "error": type(exc).__name__,
                           "message": str(exc)[:500]})
            if provider_failures["openalex"] >= 2:
                disabled.add("openalex")
        # A healthy primary provider can satisfy the bucket by itself. Papers
        # enrich the mix up to roughly 35%; they are never a mathematical
        # dependency for the coverage gate.
        paper_quota = min(len(papers), math.ceil(per_bucket * .70))
        chosen_papers = papers[:paper_quota]
        chosen_news = news[:max(0, per_bucket - len(chosen_papers))]
        if len(chosen_news) + len(chosen_papers) < per_bucket:
            chosen_papers.extend(papers[paper_quota:per_bucket - len(chosen_news)])
        for category, rows in (("news", chosen_news), ("papers", chosen_papers)):
            grouped = {}
            for row in rows:
                published = _date(row.get("published_at") or row.get("date"))
                if start.isoformat() <= published <= finish.isoformat():
                    grouped.setdefault(published, []).append(row)
            for published, values in grouped.items():
                before = len(store.list_daily(date=published, category=category))
                store.save_daily(category, values, date=published)
                after = len(store.list_daily(date=published, category=category))
                saved[category] += max(0, after - before)
        attempts = [row for row in attempts if row.get("key") != key]
        saved_total = saved["news"] + saved["papers"]
        sufficient = saved_total >= resume_minimum
        bucket_status = ("completed" if sufficient and not errors else
                         "usable" if sufficient else "partial")
        attempts.append({"key": key, "start": start.isoformat(), "end": finish.isoformat(),
                         "status": bucket_status,
                         "saved": saved, "errors": errors,
                         "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        manifest["attempts"] = attempts
        manifest["last_bucket"] = key
        manifest["provider_state"] = {"failures": provider_failures,
                                      "circuit_open": sorted(disabled - unconfigured),
                                      "unconfigured": sorted(unconfigured)}
        store._write_json(path, manifest)
        print(f"[历史 {index}/{len(pending)}] {key}：news +{saved['news']} papers +{saved['papers']} errors={len(errors)}")
        if pending and index < len(pending):
            time.sleep(0.6)
    evaluation = evaluate_history(store, horizon, end=end, policy=policy)
    manifest.update({"evaluation": evaluation,
                     "status": "ready" if evaluation["ready"] else "sparse",
                     "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    store._write_json(path, manifest)
    return {**evaluation, "manifest": str(path), "status": manifest["status"]}


def ensure_history(config: dict, store, horizon: str) -> dict:
    evaluation = evaluate_history(store, horizon)
    if evaluation["ready"]:
        return evaluation
    result = backfill_history(config, store, horizon)
    if not result["ready"]:
        raise HistoryCoverageError(
            f"{horizon} 历史证据不足：{result['admitted_total']}/{result['required_total']}，"
            f"时间桶 {result['buckets_covered']}/{result['required_buckets']}；"
            f"manifest={result['manifest']}")
    return result
