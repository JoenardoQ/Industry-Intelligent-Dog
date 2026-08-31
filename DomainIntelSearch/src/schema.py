"""IIOS 统一输出 Schema — 所有 Agent 的数据交换契约.

规格见 IIOS_SPEC.md §3.1。任何 Agent 产出（新闻/论文/公司/政策/任务包）
最终都应转换为 IIOSRecord 后入库或落盘。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

from intdog_core import stable_id, utc_now


VALID_TYPES = {
    "news", "paper", "company", "policy", "finance", "startup",
    "technology", "learning", "timeline", "value_chain", "industry",
    "social", "report", "task",
}
EVIDENCE_STATES = {"candidate", "collected", "verified", "corroborated", "rejected"}
REVIEW_STATES = {"unreviewed", "draft_review_required", "reviewed", "published"}


def record_id(*parts: str) -> str:
    return stable_id("rec", *parts)


@dataclass
class Impact:
    companies: list = field(default_factory=list)      # 受影响公司
    technologies: list = field(default_factory=list)   # 受影响技术
    importance: int = 3                                 # 1-5


@dataclass
class IIOSRecord:
    """统一记录格式（IIOS_SPEC.md §3.1）."""

    type: str
    title: str
    schema_version: str = "3.0"
    summary: str = ""
    source: str = ""
    url: str = ""
    confidence: float = 0.7
    tags: list = field(default_factory=list)
    region: str = "global"
    industry: str = ""
    published: str = ""                                 # YYYY-MM-DD
    observed_at: str = ""
    valid_from: str = ""
    valid_to: str = ""
    evidence_status: str = "candidate"
    review_status: str = "unreviewed"
    references: list = field(default_factory=list)      # [{title, url}]
    provenance: dict = field(default_factory=dict)
    impact: Impact = field(default_factory=Impact)
    extra: dict = field(default_factory=dict)
    id: str = ""
    last_updated: str = ""

    def __post_init__(self):
        if self.type not in VALID_TYPES:
            raise ValueError(f"非法记录类型: {self.type}，合法值: {sorted(VALID_TYPES)}")
        self.title = str(self.title or "").strip()
        if not self.title:
            raise ValueError("记录 title 不能为空")
        try:
            self.confidence = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence 必须是 0-1 数字") from exc
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence 必须位于 0-1")
        if not isinstance(self.references, list):
            raise ValueError("references 必须是数组")
        if self.evidence_status not in EVIDENCE_STATES:
            raise ValueError(f"非法 evidence_status: {self.evidence_status}")
        if self.review_status not in REVIEW_STATES:
            raise ValueError(f"非法 review_status: {self.review_status}")
        self.references = [reference for reference in self.references
                           if isinstance(reference, dict) and reference.get("url")]
        if isinstance(self.impact, dict):
            self.impact = Impact(
                companies=list(self.impact.get("companies", [])),
                technologies=list(self.impact.get("technologies", [])),
                importance=self.impact.get("importance", 3))
        if not isinstance(self.impact, Impact):
            raise ValueError("impact 必须是 Impact 或对象")
        self.impact.importance = max(1, min(5, int(self.impact.importance)))
        if not self.id:
            self.id = record_id(self.type, self.title, self.url or self.source)
        if not self.last_updated:
            self.last_updated = utc_now()
        if not self.observed_at:
            self.observed_at = self.last_updated

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_article(cls, art_dict: dict, industry: str = "") -> "IIOSRecord":
        """从旧版 Article.to_dict() 转换（向后兼容爬虫层）.

        每条记录自动生成 references 首条引用（原文链接），保证任何入库信息都可溯源。
        """
        cat_map = {"academic": "paper", "general": "news"}
        rtype = cat_map.get(art_dict.get("category", ""), art_dict.get("category", "news"))
        if rtype not in VALID_TYPES:
            rtype = "news"
        refs = []
        if art_dict.get("url"):
            refs.append({
                "title": art_dict.get("title", ""),
                "url": art_dict["url"],
                "source": art_dict.get("source", ""),
                "published": art_dict.get("published", ""),
            })
        return cls(
            type=rtype,
            title=art_dict.get("title", ""),
            summary=art_dict.get("summary", ""),
            source=art_dict.get("source", ""),
            url=art_dict.get("url", ""),
            published=art_dict.get("published", ""),
            valid_from=art_dict.get("published", ""),
            evidence_status="collected",
            tags=[art_dict.get("lang", "")] if art_dict.get("lang") else [],
            industry=industry,
            references=refs,
            extra={k: v for k, v in art_dict.items()
                   if k not in ("title", "summary", "source", "url", "published", "lang")},
        )


# 公司 24 项指标模板（IIOS_SPEC.md §6）——Company Agent 任务包与 companies 表共用
COMPANY_METRICS_TEMPLATE = {
    "overview": "", "founded": "", "ceo": "", "employees": "",
    "market_cap": "", "revenue": "", "net_profit": "", "gross_margin": "",
    "cash_flow": "", "pe": "", "ps": "", "pb": "",
    "customers": [], "suppliers": [], "competitors": [], "products": [],
    "patents": "", "market_share": "",
    "advantages": [], "weaknesses": [], "moat": "",
    "import_export": "", "supply_chain_position": "",
    "latest_strategy": "", "risks": [], "future_outlook": "",
    "confidence_score": 0.0,
}

# 评分维度（scores 表）
SCORE_DIMENSIONS = ["innovation", "financial", "supply_chain", "talent",
                    "research", "market", "policy", "overall"]
