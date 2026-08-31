"""定期监控的新爬虫类别：GitHub / 融资 / 招聘 / CEO发言.

每条产出统一字段：{title, abstract, url, source, date, category}，
供 IndustryStore.save_daily() 写入 periodic/daily/<日期>/<类别>.json。

诚实说明（抓取可行性）：
  - github   真实抓取：GitHub Search API（无需 Key，限流 10 次/分钟）
  - funding  融资：对行业新闻 RSS 做融资关键词过滤（36氪等源含融资报道）
  - hiring   招聘：对新闻 RSS 做招聘/人事关键词过滤（无法直连 LinkedIn/猎聘）
  - ceo      CEO发言：对新闻 RSS 做高管言论关键词过滤（无法直连 X/LinkedIn）
后三类受限于免费公开源，覆盖度有限；更全的需 LLM 任务包或专用 API。
"""

from __future__ import annotations

import re
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta

import feedparser
import requests

UA = {"User-Agent": "DomainIntelSearch/1.0 (+https://github.com/)"}


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _item(title, abstract, url, source, category, date=None, **extra):
    return {
        "title": (title or "").strip(),
        "abstract": (abstract or "").strip()[:500],
        "url": (url or "").strip(),
        "source": source,
        "date": date or _today(),
        "category": category,
        "published_at": date or "",
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
        **extra,
    }


def _matches(text: str, keywords: list[str]) -> list[str]:
    """Match short ASCII acronyms as words; avoid `AI` matching `said`."""
    low = (text or "").lower()
    hits = []
    for keyword in keywords or []:
        key = str(keyword).strip().lower()
        if not key:
            continue
        if key.isascii() and len(key) <= 3:
            matched = re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", low)
        else:
            matched = key in low
        if matched:
            hits.append(keyword)
    return hits


def _search_terms(keywords: list[str], limit: int = 8) -> list[str]:
    """Prefer discriminative English technical terms for global search APIs."""
    unique = list(dict.fromkeys(str(value).strip() for value in keywords if str(value).strip()))
    def rank(value: str):
        ascii_term = value.isascii()
        generic = value.lower() in {"ai", "it", "ic", "tech", "technology"}
        return (0 if ascii_term and not generic and len(value) >= 4 else
                1 if ascii_term and not generic else
                2 if not ascii_term else 3, -len(value))
    return sorted(unique, key=rank)[:limit]


def _published_date(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed)).strftime("%Y-%m-%d")
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
            except (TypeError, ValueError, OverflowError):
                pass
    return ""


# ----------------------------------------------------------------------
# GitHub（真实 API）
# ----------------------------------------------------------------------
def fetch_github(keywords: list[str], per_kw: int = 5, days: int = 30) -> list[dict]:
    """按关键词搜 GitHub 近期活跃仓库."""
    from .http_utils import fetch_url
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out, seen = [], set()
    for kw in _search_terms(keywords):  # 控制请求数，优先高区分度英文技术词
        q = f"{kw} pushed:>={since}"
        try:
            r = fetch_url(
                "https://api.github.com/search/repositories",
                name=f"GitHub[{kw}]",
                params={"q": q, "sort": "updated", "order": "desc",
                        "per_page": per_kw},
                headers={"Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                continue
            for repo in r.json().get("items", []):
                url = repo.get("html_url", "")
                if url in seen:
                    continue
                seen.add(url)
                stars = repo.get("stargazers_count", 0)
                abstract = (repo.get("description") or "")[:300]
                abstract += f"  ★{stars} · {repo.get('language') or ''}"
                out.append(_item(repo.get("full_name", ""), abstract, url,
                                 "GitHub", "github",
                                 date=(repo.get("pushed_at") or "")[:10],
                                 origin="foreign", source_language="en",
                                 classification_reason={"domain": [kw], "type": ["repository"]},
                                 relevance_score=1.0,
                                 metrics={"stars": stars,
                                          "language": repo.get("language") or ""}))
        except (requests.RequestException, ValueError):
            continue
    return out


# ----------------------------------------------------------------------
# 基于新闻 RSS 的关键词过滤（融资 / 招聘 / CEO）
# ----------------------------------------------------------------------
def _fetch_rss(feeds: list[dict], kw_include: list[str], category: str,
               domain_keywords: list[str], max_items: int = 20,
               since_days: int = 7) -> list[dict]:
    from .http_utils import parse_feed
    out, seen = [], set()
    for feed in feeds:
        parsed = parse_feed(feed["url"], name=feed.get("name", "RSS"))
        if parsed is None:
            continue  # 失败已登记到 http_utils.feed_failures()
        for e in parsed.entries[:30]:
            title = e.get("title", "")
            summary = e.get("summary", "") or e.get("description", "")
            text = title + " " + summary
            type_hits = _matches(text, kw_include)
            domain_hits = _matches(text, domain_keywords)
            if not type_hits or not domain_hits:
                continue
            published = _published_date(e)
            if published:
                try:
                    age = (datetime.now().date() -
                           datetime.strptime(published, "%Y-%m-%d").date()).days
                    if age < 0 or age > max(1, since_days):
                        continue
                except ValueError:
                    pass
            url = e.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(_item(title, summary, url, feed.get("name", "RSS"),
                             category, date=published,
                             origin=("china" if feed.get("lang") == "zh" else "foreign"),
                             source_language=feed.get("lang", "en"),
                             classification_reason={"domain": domain_hits[:5],
                                                    "type": type_hits[:5]}))
            if len(out) >= max_items:
                return out
    return out


FUNDING_KW = ["融资", "轮", "投资", "估值", "募资", "funding", "raised",
              "series a", "series b", "series c", "ipo", "venture"]
HIRING_KW = ["招聘", "扩招", "裁员", "人才", "hiring", "layoff", "recruit",
             "job opening", "headcount", "入职", "离职"]
CEO_KW = ["ceo", "首席执行官", "总裁", "创始人", "董事长", "founder",
          "chief executive", "表示", "发表讲话", "interview", "专访"]


def fetch_funding(feeds: list[dict], domain_keywords: list[str],
                  max_items: int = 20, since_days: int = 7) -> list[dict]:
    return _fetch_rss(feeds, FUNDING_KW, "funding", domain_keywords,
                      max_items, since_days)


def fetch_hiring(feeds: list[dict], domain_keywords: list[str],
                 max_items: int = 20, since_days: int = 7) -> list[dict]:
    return _fetch_rss(feeds, HIRING_KW, "hiring", domain_keywords,
                      max_items, since_days)


def fetch_ceo(feeds: list[dict], domain_keywords: list[str],
              max_items: int = 20, since_days: int = 7) -> list[dict]:
    return _fetch_rss(feeds, CEO_KW, "ceo", domain_keywords,
                      max_items, since_days)
