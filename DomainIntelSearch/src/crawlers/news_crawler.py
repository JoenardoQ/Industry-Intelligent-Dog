"""新闻爬虫：RSS + NewsAPI + GNews 多源聚合."""

from datetime import datetime

import requests
import feedparser

from .base import BaseCrawler, Article
from ..utils import days_ago, article_id, SeenStore, ensure_dir


class RSSCrawler(BaseCrawler):
    """RSS 源爬虫（无需 API Key）."""

    name = "rss"

    def __init__(self, config, feed_category="general", since_days=1):
        super().__init__(config)
        self.feed_category = feed_category
        self.since = days_ago(since_days)
        feeds = config.get("news", {}).get("rss_feeds", {})
        self.feeds = feeds.get(feed_category, [])

    def fetch(self) -> list[Article]:
        from .http_utils import parse_feed
        articles = []
        for feed in self.feeds:
            parsed = parse_feed(feed["url"], name=feed.get("name", "RSS"))
            if parsed is None:
                continue  # 失败已登记到 http_utils.feed_failures()
            try:
                for entry in parsed.entries:
                    published = self._parse_date(entry)
                    if published and published < self.since:
                        continue
                    a = Article(
                        title=entry.get("title", ""),
                        url=entry.get("link", ""),
                        source=feed.get("name", "RSS"),
                        published=published.strftime("%Y-%m-%d") if published else "",
                        summary=self._extract_summary(entry),
                        lang=feed.get("lang", "en"),
                        category=self.feed_category,
                    )
                    a.extra["uid"] = article_id(a.url)
                    if a.url:
                        articles.append(a)
            except Exception as e:
                print(f"[RSS] 解析 {feed.get('name')} 条目失败: {e}")
        return self.filter_by_keywords(articles)

    def _parse_date(self, entry):
        for key in ("published_parsed", "updated_parsed"):
            if hasattr(entry, key) and getattr(entry, key):
                return datetime(*getattr(entry, key)[:6])
        for key in ("published", "updated"):
            if hasattr(entry, key) and getattr(entry, key):
                try:
                    return datetime.strptime(
                        getattr(entry, key)[:19], "%Y-%m-%dT%H:%M:%S"
                    )
                except (ValueError, TypeError):
                    continue
        return None

    def _extract_summary(self, entry):
        if hasattr(entry, "summary"):
            return entry.summary[:500]
        if hasattr(entry, "description"):
            return entry.description[:500]
        return ""


class NewsAPICrawler(BaseCrawler):
    """NewsAPI 爬虫（免费版 100 请求/天）."""

    name = "newsapi"
    BASE = "https://newsapi.org/v2/everything"

    def __init__(self, config, since_days=1):
        super().__init__(config)
        self.api_key = config.get("news", {}).get("newsapi_key", "")
        self.since_days = since_days

    def fetch(self) -> list[Article]:
        if not self.api_key:
            return []
        query = " OR ".join(f'"{k}"' for k in self.domain_cfg.get("keywords", []))
        params = {
            "q": query or self.domain_cfg.get("name_en", ""),
            "from": days_ago(self.since_days).strftime("%Y-%m-%d"),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 50,
            "apiKey": self.api_key,
        }
        try:
            from .http_utils import fetch_url
            resp = fetch_url(self.BASE, params=params, timeout=15, name="NewsAPI")
            data = resp.json()
            articles = []
            for item in data.get("articles", []):
                a = Article(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source=item.get("source", {}).get("name", "NewsAPI"),
                    published=item.get("publishedAt", "")[:10],
                    summary=(item.get("description") or "")[:500],
                    lang="en",
                    category="general",
                )
                a.extra["uid"] = article_id(a.url)
                if a.url:
                    articles.append(a)
            return self.filter_by_keywords(articles)
        except Exception as e:
            print(f"[NewsAPI] 抓取失败: {e}")
            return []


class GNewsCrawler(BaseCrawler):
    """GNews 爬虫（免费版 100 请求/天）."""

    name = "gnews"
    BASE = "https://gnews.io/api/v4/search"

    def __init__(self, config, since_days=1):
        super().__init__(config)
        self.api_key = config.get("news", {}).get("gnews_key", "")
        self.since_days = since_days

    def fetch(self) -> list[Article]:
        if not self.api_key:
            return []
        query = " OR ".join(self.domain_cfg.get("keywords", []))
        params = {
            "q": query or self.domain_cfg.get("name_en", ""),
            "max": 50,
            "lang": "zh" if self.domain_cfg.get("language", "zh") == "zh" else "en",
            "from": days_ago(self.since_days).isoformat(timespec="seconds") + "Z",
            "apikey": self.api_key,
        }
        try:
            from .http_utils import fetch_url
            resp = fetch_url(self.BASE, params=params, timeout=15, name="GNews")
            data = resp.json()
            articles = []
            for item in data.get("articles", []):
                a = Article(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source=item.get("source", {}).get("name", "GNews"),
                    published=item.get("publishedAt", "")[:10],
                    summary=(item.get("description") or "")[:500],
                    lang="zh",
                    category="general",
                )
                a.extra["uid"] = article_id(a.url)
                if a.url:
                    articles.append(a)
            return self.filter_by_keywords(articles)
        except Exception as e:
            print(f"[GNews] 抓取失败: {e}")
            return []


class NewsAggregator:
    """聚合所有新闻源，去重后输出."""

    def __init__(self, config):
        self.config = config
        profile_id = (config.get("_profile", {}) or {}).get("id", "default")
        self.seen = SeenStore(
            config.get("output", {}).get("data_dir", "./data")
            + f"/seen_news_{profile_id}.json"
        )

    def collect(self, since_days: int = 1) -> list[Article]:
        categories = {
            "general": "general",
            "startup": "startup",
            "finance": "finance",
            "policy": "policy",
        }
        all_articles = []
        for cat in categories:
            rss = RSSCrawler(self.config, feed_category=cat, since_days=since_days)
            all_articles.extend(rss.fetch())

        # API 源（仅 general 类别）
        all_articles.extend(NewsAPICrawler(self.config, since_days=since_days).fetch())
        all_articles.extend(GNewsCrawler(self.config, since_days=since_days).fetch())

        # 去重
        seen_urls = set()
        unique = []
        for a in all_articles:
            uid = a.extra.get("uid") or article_id(a.url)
            if uid in seen_urls or self.seen.is_seen(uid):
                continue
            seen_urls.add(uid)
            unique.append(a)

        # 按发布时间排序
        unique.sort(key=lambda x: x.published, reverse=True)
        return unique

    def mark_seen(self, articles: list[Article]):
        for a in articles:
            uid = a.extra.get("uid") or article_id(a.url)
            self.seen.mark(uid)
        self.seen.save()
