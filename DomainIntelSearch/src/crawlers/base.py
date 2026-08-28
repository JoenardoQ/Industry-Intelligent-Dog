"""爬虫基类与通用数据结构."""

from dataclasses import dataclass, field, asdict
import re
from typing import List, Optional


@dataclass
class Article:
    """统一的文章/条目数据结构."""
    title: str
    url: str
    source: str = ""
    published: str = ""
    summary: str = ""
    lang: str = "en"
    category: str = "general"       # general / startup / finance / policy / academic
    authors: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class BaseCrawler:
    """爬虫基类：统一的 fetch 接口."""

    name = "base"

    def __init__(self, config: dict):
        self.config = config
        self.domain_cfg = config.get("domain", {})
        self.keywords = [k.lower() for k in self.domain_cfg.get("keywords", [])]

    def fetch(self) -> List[Article]:
        raise NotImplementedError

    def match_keywords(self, text: str) -> bool:
        """检查文本是否包含领域关键词（无关键词则全部通过）."""
        if not self.keywords:
            return True
        text = (text or "").lower()
        for keyword in self.keywords:
            if keyword.isascii() and len(keyword) <= 3:
                if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                    return True
            elif keyword in text:
                return True
        return False

    def filter_by_keywords(self, articles: List[Article]) -> List[Article]:
        """按关键词过滤文章."""
        if not self.keywords:
            return articles
        result = []
        for a in articles:
            combined = f"{a.title} {a.summary}"
            if self.match_keywords(combined):
                result.append(a)
        return result
