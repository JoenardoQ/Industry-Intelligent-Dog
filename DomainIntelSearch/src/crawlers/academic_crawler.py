"""学术爬虫：arXiv + Semantic Scholar."""

import os
from datetime import datetime

import feedparser

from .base import BaseCrawler, Article
from ..utils import days_ago, article_id, SeenStore


class ArxivCrawler(BaseCrawler):
    """arXiv 论文爬虫（无需 API Key）."""

    name = "arxiv"
    BASE = "https://export.arxiv.org/api/query"

    def __init__(self, config, since_days=1):
        super().__init__(config)
        self.academic_cfg = config.get("academic", {})
        self.categories = self.academic_cfg.get("arxiv_categories", ["cs.AI"])
        self.since = days_ago(since_days)

    def fetch(self) -> list[Article]:
        from .http_utils import fetch_url
        cat_query = "(" + " OR ".join(f"cat:{c}" for c in self.categories) + ")"
        # 使用 submittedDate 范围过滤（API 的 sortBy=submittedDate 在本环境返回 400）
        start = self.since.strftime("%Y%m%d") + "0000"
        end = datetime.now().strftime("%Y%m%d") + "2359"
        date_range = f"submittedDate:[{start} TO {end}]"
        query = f"{cat_query} AND {date_range}"
        params = {
            "search_query": query,
            "start": 0,
            "max_results": self.academic_cfg.get("max_papers_per_day", 20) * 3,
        }
        try:
            resp = fetch_url(self.BASE, params=params, timeout=25,
                             name="arXiv",
                             headers={"User-Agent": "research-agent/1.0"})
            parsed = feedparser.parse(resp.text)
            articles = []
            for entry in parsed.entries:
                published = entry.get("published", "")[:10]
                a = Article(
                    title=entry.get("title", "").strip(),
                    url=entry.get("link", ""),
                    source="arXiv",
                    published=published,
                    summary=(entry.get("summary", "") or "").strip()[:600],
                    lang="en",
                    category="academic",
                    authors=[a.get("name", "") for a in entry.get("authors", [])],
                )
                a.extra["uid"] = article_id(a.url)
                a.extra["arxiv_id"] = entry.get("id", "")
                if a.url:
                    articles.append(a)
            articles.sort(key=lambda x: x.published, reverse=True)
            # 修复：行业关键词多为中文，英文论文几乎不命中 → 只用 ASCII 关键词过滤；
            # 若命中过少，保留分类内最新 N 条（arXiv 分类本身即行业方向，属合理兜底），
            # 并标注 keyword_match=False 保持诚实。
            max_n = self.academic_cfg.get("max_papers_per_day", 20)
            en_kw = [k for k in self.domain_cfg.get("keywords", [])
                     if k and k.isascii()]
            matched = [a for a in articles
                       if self.match_keywords(f"{a.title} {a.summary}")] if en_kw else []
            for a in articles:
                a.extra["keyword_match"] = a in matched
            # Profiles with searchable English terms must not silently fall
            # back to unrelated category-wide papers.
            if en_kw:
                return matched[:max_n]
            for article in articles:
                article.extra["selection_reason"] = "category_only_no_ascii_keywords"
            return articles[:max_n]
        except Exception as e:
            print(f"[Arxiv] 抓取失败: {e}")
            return []


class SemanticScholarCrawler(BaseCrawler):
    """Semantic Scholar 论文爬虫（无需 API Key）."""

    name = "semantic_scholar"
    BASE = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, config, since_days=7):
        super().__init__(config)
        self.academic_cfg = config.get("academic", {})
        self.fields = self.academic_cfg.get("semantic_scholar_fields", ["Computer Science"])
        self.since = since_days

    def fetch(self) -> list[Article]:
        from .http_utils import fetch_url
        # S2 是英文库：只用 ASCII 关键词组 query，中文关键词只会稀释结果
        en_kw = [k for k in self.domain_cfg.get("keywords", []) if k and k.isascii()]
        query = " OR ".join(en_kw) or self.domain_cfg.get("name_en", "")
        params = {
            "query": query,
            "fields": "title,url,abstract,authors,publicationDate,venue",
            "limit": self.academic_cfg.get("max_papers_per_day", 20),
            "year": datetime.now().year,
        }
        headers = {}
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        if api_key:
            headers["x-api-key"] = api_key
        try:
            resp = fetch_url(self.BASE, params=params, headers=headers,
                             timeout=15, name="SemanticScholar")
            data = resp.json()
            articles = []
            for item in data.get("data", []):
                a = Article(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source=f"SemanticScholar ({item.get('venue', '')})",
                    published=item.get("publicationDate", ""),
                    summary=(item.get("abstract") or "")[:600],
                    lang="en",
                    category="academic",
                    authors=[au.get("name", "") for au in item.get("authors", [])],
                )
                a.extra["uid"] = article_id(a.url or a.title)
                a.extra["citation_venue"] = item.get("venue", "")
                if a.title:
                    articles.append(a)
            return self.filter_by_keywords(articles)
        except Exception as e:
            print(f"[SemanticScholar] 抓取失败: {e}")
            return []


class AcademicAggregator:
    """聚合学术源."""

    def __init__(self, config):
        from ..utils import SeenStore
        self.config = config
        profile_id = (config.get("_profile", {}) or {}).get("id", "default")
        self.seen = SeenStore(
            config.get("output", {}).get("data_dir", "./data")
            + f"/seen_academic_{profile_id}.json"
        )

    def collect(self, since_days: int = 1) -> list[Article]:
        articles = []
        articles.extend(ArxivCrawler(self.config, since_days=since_days).fetch())
        articles.extend(SemanticScholarCrawler(self.config, since_days=max(since_days, 7)).fetch())

        seen_ids = set()
        unique = []
        for a in articles:
            uid = a.extra.get("uid") or article_id(a.url or a.title)
            if uid in seen_ids or self.seen.is_seen(uid):
                continue
            seen_ids.add(uid)
            unique.append(a)
        return unique

    def mark_seen(self, articles: list[Article]):
        for a in articles:
            uid = a.extra.get("uid") or article_id(a.url or a.title)
            self.seen.mark(uid)
        self.seen.save()
