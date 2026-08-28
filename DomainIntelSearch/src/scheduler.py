"""定期监控调度器：把每日/每周/每月/每季的抓取与产物写入 periodic/.

每日：news / github / funding / hiring / ceo / papers
每周：行业总结（汇总一周 daily + LLM 任务包）
每月：产业分析（LLM 任务包）
每季：上市公司财报分析（LLM 任务包）

定期产物与一次性深度爬取（one_time/）分开存放。
"""

from __future__ import annotations

import html
import copy
from datetime import datetime

from .crawlers.news_crawler import NewsAggregator
from .crawlers.academic_crawler import AcademicAggregator
from .crawlers import periodic_crawlers as pc
from .industry_store import IndustryStore, DAILY_CATEGORIES


def _article_to_item(a, category: str) -> dict:
    item = {
        "title": a.title,
        "abstract": (a.summary or "")[:500],
        "url": a.url,
        "source": a.source,
        "date": a.published or datetime.now().strftime("%Y-%m-%d"),
        "published_at": a.published or "",
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
        "category": category,
        "source_category": a.category,
        "source_language": a.lang or "",
        "origin": "china" if (a.lang or "").lower().startswith("zh") else "foreign",
    }
    item.update(a.extra or {})
    return item


def _all_news_feeds(config: dict) -> list[dict]:
    """汇总全部新闻 RSS 源（供融资/招聘/CEO 过滤使用）."""
    feeds_cfg = config.get("news", {}).get("rss_feeds", {})
    out = []
    for cat in ("general", "startup", "finance", "policy"):
        out.extend(feeds_cfg.get(cat, []))
    return out


class PeriodicScheduler:
    """单个行业的定期监控."""

    def __init__(self, config: dict, store: IndustryStore):
        self.config = self._with_discovered_feeds(config, store)
        self.store = store
        self.keywords = (self.config.get("domain", {}) or {}).get("keywords", [])

    @staticmethod
    def _with_discovered_feeds(config: dict, store: IndustryStore) -> dict:
        """Make RSS sources discovered for an industry affect actual collection."""
        merged = copy.deepcopy(config)
        feeds = merged.setdefault("news", {}).setdefault("rss_feeds", {})
        mapping = {"blogs": "general", "self_media": "general", "news": "general",
                   "platforms": "startup", "finance": "finance"}
        discovered = store.get_sources()
        for source_category, feed_category in mapping.items():
            target = feeds.setdefault(feed_category, [])
            seen = {entry.get("url") for entry in target}
            for entry in discovered.get(source_category, []) or []:
                url = entry.get("rss_url") or entry.get("feed_url") or entry.get("url", "")
                hint = f"{url} {entry.get('note', '')}".lower()
                if (not url or url in seen or
                        not any(token in hint for token in ("rss", "feed", "atom", "hnrss"))):
                    continue
                target.append({"name": entry.get("name", "RSS"), "url": url,
                               "lang": entry.get("language") or entry.get("lang", "en")})
                seen.add(url)
        return merged

    def _send_digest(self, subject: str, items: list[dict]) -> bool:
        email_cfg = self.config.get("email", {}) or {}
        if not (email_cfg.get("enabled") and email_cfg.get("send_on_periodic", True)):
            return False
        from .services.email_service import EmailService
        ordered = sorted(items, key=lambda item: (
            item.get("credibility", 0), item.get("source_count", 0)), reverse=True)
        rows = []
        for item in ordered[:30]:
            rows.append(
                f'<li><a href="{html.escape(item.get("url", ""))}">'
                f'{html.escape(item.get("title", ""))}</a> '
                f'<small>{html.escape(item.get("source", ""))} · '
                f'{item.get("credibility_label", "待评估")}</small><br>'
                f'{html.escape((item.get("abstract") or "")[:240])}</li>')
        body = (f'<h2>{html.escape(subject)}</h2><p>共 {len(items)} 条，按可信度排序。</p>'
                f'<ol>{"".join(rows)}</ol>')
        return EmailService(self.config).send_html(subject, body)

    # ------------------------------------------------------------------
    # 每日：六类
    # ------------------------------------------------------------------
    def run_daily(self, date: str = None, since_days: int = 1) -> dict:
        from .crawlers import http_utils
        http_utils.reset_feed_failures()
        date = date or datetime.now().strftime("%Y-%m-%d")
        result: dict[str, int] = {}

        # 新闻（复用现有聚合器）
        try:
            news_agg = NewsAggregator(self.config)
            news = news_agg.collect(since_days=since_days)
            items = [_article_to_item(a, "news") for a in news]
            self.store.save_daily("news", items, date)
            news_agg.mark_seen(news)
            result["news"] = len(items)
        except Exception as e:
            result["news_error"] = str(e)

        # 论文（复用现有聚合器）
        try:
            ac_agg = AcademicAggregator(self.config)
            papers = ac_agg.collect(since_days=since_days)
            items = [_article_to_item(a, "papers") for a in papers]
            self.store.save_daily("papers", items, date)
            ac_agg.mark_seen(papers)
            result["papers"] = len(items)
        except Exception as e:
            result["papers_error"] = str(e)

        # GitHub
        try:
            items = pc.fetch_github(self.keywords)
            self.store.save_daily("github", items, date)
            result["github"] = len(items)
        except Exception as e:
            result["github_error"] = str(e)

        # 融资 / 招聘 / CEO（基于新闻 RSS 关键词过滤）
        feeds = _all_news_feeds(self.config)
        for cat, fn in (("funding", pc.fetch_funding),
                        ("hiring", pc.fetch_hiring),
                        ("ceo", pc.fetch_ceo)):
            try:
                items = fn(feeds, self.keywords, since_days=max(since_days, 2))
                self.store.save_daily(cat, items, date)
                result[cat] = len(items)
            except Exception as e:
                result[f"{cat}_error"] = str(e)

        # 多源交叉验证：跨天归并（近 3 天）同一事件、打可信度分、回填 references[]
        try:
            from . import verification
            stats = verification.verify_store_daily(self.store, date=date, days=3)
            result["verified"] = f"{stats['verified_items']}/{stats['stories']}故事"
            result["credibility"] = (f"高{stats['high']} 中{stats['medium']} "
                                     f"低{stats['low']}")
        except Exception as e:
            result["verify_error"] = str(e)

        # Deterministic delivery works without an LLM.  Research commentary
        # remains a separate reviewed artifact.
        try:
            digest_items = self.store.list_daily(date=date)
            result["email_sent"] = self._send_digest(
                f"{self.store.name} 每日情报 · {date}", digest_items)
        except Exception as e:
            result["email_error"] = str(e)

        # 抓取源健康汇总：失败源写入当天 _crawl_log.json，并在结果里报数
        failures = http_utils.feed_failures()
        result["feed_failures"] = len(failures)
        try:
            log = {
                "date": date,
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "counts": {k: v for k, v in result.items()},
                "failed_feeds": failures,
            }
            self.store._write_json(
                self.store.periodic / "daily" / date / "_crawl_log.json", log)
        except Exception as e:
            result["crawl_log_error"] = str(e)

        return result

    # ------------------------------------------------------------------
    # 每周：行业总结
    # ------------------------------------------------------------------
    def run_weekly(self) -> dict:
        # 汇总本周每天的条目数量 + 生成 LLM 总结任务包
        counts = {}
        for cat in DAILY_CATEGORIES:
            items = self.store.list_daily_range(days=7, category=cat)
            counts[cat] = len(items)
        task = {
            "type": "weekly_summary",
            "prompt": (
                f"你是\"{self.store.name}\"行业分析师。请基于本周抓取到的新闻、GitHub、"
                f"融资、招聘、CEO发言、论文数据，输出一份**每周行业总结**（Markdown）：\n"
                f"1. 本周最重要 3-5 个动态（每条附来源链接 [n]）\n"
                f"2. 融资与招聘反映的行业冷热\n3. 技术进展亮点\n"
                f"文末附 references[]（含 url）。数据见 periodic/daily/ 本周文件。"),
            "output_file": f"periodic/weekly/{self.store._period_key('weekly')}.md",
        }
        payload = {"counts": counts, "task": task,
                   "summary": "本周行业总结（数据已汇总，LLM 任务包见 task.prompt）"}
        path = self.store.save_period("weekly", payload)
        week_items = self.store.list_daily_range(days=7)
        email_sent = self._send_digest(
            f"{self.store.name} 每周行业与政策总结 · {self.store._period_key('weekly')}",
            week_items)
        return {"weekly": str(path), "counts": counts, "email_sent": email_sent}

    # ------------------------------------------------------------------
    # 每月：产业分析
    # ------------------------------------------------------------------
    def run_monthly(self) -> dict:
        task = {
            "type": "monthly_analysis",
            "prompt": (
                f"你是\"{self.store.name}\"产业研究员。请输出一份**每月产业分析**（Markdown）：\n"
                f"1. 本月产业链各层级动态（设计/制造/封装等）\n"
                f"2. 重点公司动向与投融资\n3. 政策与区域格局变化\n"
                f"4. 下月值得关注的信号\n每条结论附来源 [n]，文末 references[]（含 url）。"),
            "output_file": f"periodic/monthly/{self.store._period_key('monthly')}.md",
        }
        path = self.store.save_period("monthly", {"task": task,
                                     "summary": "本月产业分析（LLM 任务包）"})
        return {"monthly": str(path)}

    # ------------------------------------------------------------------
    # 每季：上市公司财报分析
    # ------------------------------------------------------------------
    def run_quarterly(self) -> dict:
        companies = (self.config.get("domain", {}) or {}).get("tracked_companies", [])
        company_names = [c.get("name", "") if isinstance(c, dict) else str(c)
                         for c in companies]
        company_names = [name for name in company_names if name]
        task = {
            "type": "quarterly_financials",
            "prompt": (
                f"你是\"{self.store.name}\"行业财务分析师。请输出**季度上市公司财报分析**（Markdown）：\n"
                f"跟踪公司：{', '.join(company_names) if company_names else '（在 sources.json 财报源中列举的重点公司）'}\n"
                f"对每家公司：营收/利润同比、毛利率、业务分部表现、管理层指引、市场反应。\n"
                f"数据来源：sources.json 的 financials 源（SEC/巨潮/港交所）。\n"
                f"每个数据点附来源 [n]，文末 references[]（含 url）。"),
            "output_file": f"periodic/quarterly/{self.store._period_key('quarterly')}.md",
        }
        path = self.store.save_period("quarterly", {"task": task,
                                       "summary": "本季上市公司财报分析（LLM 任务包）"})
        return {"quarterly": str(path)}
