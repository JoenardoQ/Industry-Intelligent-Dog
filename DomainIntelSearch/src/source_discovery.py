"""信息源发现：设定行业后，先确定"该看谁"再开始抓.

两类来源：
  1. 内置种子源（seed）：开箱即用的常见高质量信息源（按类别）。
  2. LLM 任务包：生成一份"为某行业梳理权威信息源"的 prompt，
     交给任意 agent/模型执行后回写，合并进 sources.json。

sources.json 结构（存于 DomainIntelData/<行业>/sources.json）：
{
  "industry": "Chips",
  "blogs":       [{"name","url","note"}],
  "platforms":   [...],    # 平台/社区
  "self_media":  [...],    # 自媒体/公众号/大V
  "news":        [...],    # 新闻媒体（RSS 优先）
  "journals":    [...],    # 学术会议/期刊
  "financials":  [...],    # 公司财报/披露
  "finance":     [...],    # 金融资讯
  "updated_at":  "..."
}
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

# 信息源类别（顺序即展示顺序）
SOURCE_CATEGORIES = [
    ("official", "政府/监管/统计"),
    ("associations", "行业协会/标准组织"),
    ("blogs", "博客"),
    ("platforms", "平台/社区"),
    ("self_media", "自媒体"),
    ("news", "新闻媒体"),
    ("journals", "学术会议/期刊"),
    ("financials", "公司财报"),
    ("finance", "金融资讯"),
]

CHINA_DOMAIN_HINTS = ("gov.cn", "cninfo.com.cn", "wallstreetcn.com",
                      "caict.ac.cn", "miit.gov.cn", "cac.gov.cn")


def source_origin(item: dict) -> str:
    """Return china/foreign using explicit metadata first, conservative URL inference second."""
    explicit = str(item.get("origin") or item.get("site_region") or "").lower()
    if explicit in {"china", "cn", "中国", "chinese"}:
        return "china"
    if explicit in {"foreign", "international", "global", "overseas", "国外", "国际"}:
        return "foreign"
    country = str(item.get("publisher_country") or item.get("country") or "").lower()
    if any(token in country for token in ("china", "中国", "chinese")):
        return "china"
    try:
        domain = urlsplit(str(item.get("url") or "")).netloc.lower().removeprefix("www.")
    except ValueError:
        domain = ""
    if domain.endswith(".cn") or any(domain.endswith(hint) for hint in CHINA_DOMAIN_HINTS):
        return "china"
    return "foreign" if domain else "unknown"

COMMON_SOURCES = {
    "official": [
        {"name": "国家统计局", "url": "https://www.stats.gov.cn/", "note": "中国官方宏观与行业统计", "tier": "primary"},
        {"name": "国家市场监督管理总局", "url": "https://www.samr.gov.cn/", "note": "监管、标准与执法一手信息", "tier": "primary"},
    ],
    "associations": [
        {"name": "ISO", "url": "https://www.iso.org/standards.html", "note": "国际标准一手目录", "tier": "primary"},
        {"name": "IEC", "url": "https://www.iec.ch/", "note": "电工电子国际标准", "tier": "primary"},
    ],
    "platforms": [
        {"name": "GitHub Trending", "url": "https://github.com/trending", "note": "开源项目热度"},
        {"name": "Hacker News", "url": "https://hnrss.org/frontpage", "note": "技术社区信号"},
    ],
    "news": [
        {"name": "Reuters", "url": "https://www.reutersagency.com/feed/", "note": "国际通讯社"},
    ],
    "financials": [
        {"name": "SEC EDGAR", "url": "https://www.sec.gov/edgar/search/", "note": "美国上市公司一手披露"},
        {"name": "巨潮资讯", "url": "https://www.cninfo.com.cn/", "note": "中国上市公司一手披露"},
        {"name": "港交所披露易", "url": "https://www1.hkexnews.hk/", "note": "香港上市公司一手披露"},
    ],
}

DOMAIN_SOURCES = {
    "ai": {
        "blogs": [{"name": "MIT Technology Review AI", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/", "note": "AI 技术与产业"}],
        "journals": [{"name": "arXiv AI", "url": "https://export.arxiv.org/api/query?search_query=cat:cs.AI", "note": "AI 预印本"}],
    },
    "semiconductor": {
        "blogs": [{"name": "Semiconductor Engineering", "url": "https://semiengineering.com/feed/", "note": "半导体工程深度技术"}],
        "news": [{"name": "EE Times", "url": "https://www.eetimes.com/feed/", "note": "半导体与电子工程"}],
        "journals": [{"name": "IEEE Xplore", "url": "https://ieeexplore.ieee.org/", "note": "电子工程论文与会议"}],
    },
    "biomed": {
        "platforms": [{"name": "ClinicalTrials.gov", "url": "https://clinicaltrials.gov/", "note": "临床试验一手登记"}],
        "journals": [{"name": "PubMed", "url": "https://pubmed.ncbi.nlm.nih.gov/", "note": "生物医学文献"}],
        "news": [{"name": "FDA News", "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds", "note": "FDA 官方更新"}],
    },
    "new_energy": {
        "blogs": [{"name": "IEA", "url": "https://www.iea.org/newsroom", "note": "能源统计与政策"}],
        "journals": [{"name": "Nature Energy", "url": "https://www.nature.com/nenergy.rss", "note": "能源前沿研究"}],
    },
    "robotics": {
        "blogs": [{"name": "IEEE Spectrum Robotics", "url": "https://spectrum.ieee.org/feeds/topic/robotics.rss", "note": "机器人技术"}],
        "journals": [{"name": "IEEE Robotics and Automation", "url": "https://www.ieee-ras.org/", "note": "机器人学术组织"}],
    },
}


def seed_sources(industry_name: str, industry_en: str = "", profile: dict = None) -> dict:
    """生成开箱即用的种子信息源（通用 + 可由 LLM 任务包扩充）."""
    profile = profile or {}
    pid = str(profile.get("id") or "").lower()
    blob = f"{industry_name} {industry_en}".lower()
    if not pid:
        pid = next((key for key in DOMAIN_SOURCES if key in blob), "")
    result = {
        "industry": industry_name,
        "profile_id": pid or "custom",
        "official": [], "associations": [], "blogs": [], "platforms": [], "self_media": [], "news": [],
        "journals": [], "financials": [],
        "finance": [
            {"name": "华尔街见闻", "url": "https://wallstreetcn.com/rss.xml", "note": "金融资讯"},
            {"name": "Financial Times", "url": "https://www.ft.com/rss/home", "note": "金融资讯"},
        ],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    for source_set in (COMMON_SOURCES, DOMAIN_SOURCES.get(pid, {})):
        for category, entries in source_set.items():
            result.setdefault(category, []).extend(dict(entry) for entry in entries)
    return result


def build_discovery_task(industry_name: str, industry_en: str = "") -> dict:
    """生成"为某行业梳理权威信息源"的 LLM 任务包（模型无关）."""
    en = industry_en or industry_name
    cats = "、".join(label for _, label in SOURCE_CATEGORIES)
    prompt = f"""你是"{industry_name}"({en})行业的资深情报分析师。
请为这个行业梳理一份**权威信息源清单**，供持续监控使用。

要求覆盖以下来源类别；每类只保留权威、有代表性或能补足明确知识缺口的来源，
不要为满足固定数量而凑数（给出 name / url / 一句话 note）：
{cats}

筛选标准：
- 优先有 RSS / 稳定更新 / 可免费访问的源
- 必须先找政府/监管/统计、行业协会/标准组织、公司 IR、顶会顶刊等一手源，再补充媒体与社区信号
- 新闻要行业垂直的权威媒体；学术要该领域的顶会/顶刊/预印本
- 财报要官方披露渠道（SEC/巨潮/港交所/公司 IR 页）
- 自媒体要该领域有公信力的大V/公众号/专栏

不要预设总量或 Top 10。先把搜索空间拆成 region × subdomain × value_chain_stage ×
entity_type × source_type × event_type × time_horizon 的覆盖单元，优先搜索仍为空或证据
单薄的单元；记录每条实际搜索 query、选择理由、发现 URL，并在边际新增低或访问受限时
给出 stopping_reason。不设中外数量比例硬限制，但要尽可能扩大中国发布者原生来源，
重点补充政府/监管、官方媒体、垂直媒体和有行业公信力的自媒体。中文网站必须是中国发布者的原生站点，
不能把外国网站的中文翻译页算中文源。每个源额外给出
tier(primary/authoritative/secondary/signal)、coverage（覆盖主题数组）、
publisher_country、language(zh/en)、origin(china/international)、
access（rss/api/web）、selection_reason、monitoring_status(active/recommended_manual)、access_note；
若存在稳定 RSS/Atom，必须额外填写 rss_url，
且 rss_url 必须是实际订阅地址而不是栏目首页。不要虚构网址。
优质但因登录、付费墙、反爬或没有 RSS 而无法自动抓取的来源仍应推荐，标为
recommended_manual 并准确说明限制；社交媒体与自媒体内容只能作为线索。
输出为 JSON（只输出 JSON，不要 Markdown）。除九类来源外，必须包含 coverage_ledger、
query_ledger、stopping_reason；coverage/query 只是待验证发现记录，不得声称已核验：
{{"official":[{{"name","url","rss_url","note","tier","coverage","publisher_country","language","origin","access","selection_reason"}}],
  "associations":[...], "blogs":[...], "platforms":[...], "self_media":[...],
  "news":[...], "journals":[...], "financials":[...], "finance":[...],
  "coverage_ledger":[{{"dimensions":{{"region","subdomain","chain_stage","entity_type","source_type","event_type","time_horizon"}},"status":"gap|thin|candidate","rationale"}}],
  "query_ledger":[{{"dimensions":{{...}},"query","rationale","discovered_urls":[],"stopping_reason"}}],
  "stopping_reason":"本轮停止原因"}}
"""
    return {
        "type": "source_discovery",
        "industry": industry_name,
        "prompt": prompt,
        "output_file": "sources.json",
        "instruction": "执行 prompt，把返回的 JSON 合并写入 DomainIntelData/<行业>/sources.json",
    }


def merge_sources(base: dict, extra: dict) -> dict:
    """把 LLM 回写的信息源合并进现有 sources（按 url 去重）."""
    from intdog_core.models import canonical_url

    out = dict(base)
    for cat, _ in SOURCE_CATEGORIES:
        seen = {canonical_url(s.get("url", "")) for s in out.get(cat, [])
                if isinstance(s, dict)}
        for s in extra.get(cat, []) or []:
            url = canonical_url(s.get("url", "")) if isinstance(s, dict) else ""
            if url and url not in seen:
                out.setdefault(cat, []).append({**s, "url": url})
                seen.add(url)
    for key in ("coverage_ledger", "query_ledger", "stopping_reason"):
        if extra.get(key):
            out[key] = extra[key]
    out["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return out


def balance_source_origins(sources: dict, minimum_per_category: int = 3,
                           target_max: float = 1.8) -> dict:
    """Annotate origin coverage without deleting useful sources (legacy API name)."""
    out = dict(sources)

    def counts() -> tuple[int, int]:
        items = [item for key, _ in SOURCE_CATEGORIES
                 for item in out.get(key, []) or [] if isinstance(item, dict)]
        return (sum(source_origin(item) == "china" for item in items),
                sum(source_origin(item) == "foreign" for item in items))

    china, foreign = counts()
    out["origin_balance"] = {
        "policy": "advisory_domestic_recall_preferred",
        "hard_limit": False,
        "china": china,
        "foreign": foreign,
    }
    return out
