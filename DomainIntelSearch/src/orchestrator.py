"""主编排器：串联抓取、分析、生成、推送全流程."""

import json
from datetime import datetime
from pathlib import Path

from .utils import load_config, ensure_dir, save_json, today_str
from .generators.digest_generator import DigestGenerator
from .services.archive_store import ArchiveStore
from .analyzers.prompts import PromptTemplates
from .spec_loader import load_spec, summarize


class Orchestrator:
    """领域情报系统主控."""

    def __init__(self, config_path: str = None, config: dict = None):
        self.config = config or load_config(config_path)
        self.domain = self.config.get("domain", {})
        out = self.config.get("output", {})
        self.data_dir = ensure_dir(out.get("data_dir", "./data"))
        # settings 用 output.dir 表示报告目录（兼容旧的 output_dir 键名）
        self.output_dir = ensure_dir(out.get("dir") or out.get("output_dir", "./output"))
        self.prompts = PromptTemplates(self.config)
        self.digest = DigestGenerator(self.config)
        self.archive = ArchiveStore(self.config)
        # 读取 DomainIntelData/skill/spec.md：抓取领域 + 保存格式（agent 中立驱动）
        self.data_root = Path(self.config.get("archive", {}).get("root", "./data"))
        self.spec = load_spec(self.data_root)
        try:
            print(summarize(self.spec))
        except Exception:
            pass

    # ===================================================================
    # 阶段一：一次性深度研究（面向新手/熟手）
    # 该部分由 LLM 完成分析，本系统负责生成"分析任务清单(brief)"
    # ===================================================================
    def build_research_brief(self) -> dict:
        """生成一份研究任务简报（模型无关任务包），供任何 agent/模型执行."""
        brief = {
            "domain": self.domain,
            "tasks": {
                "1_subdomains": self.prompts.list_subdomains(),
                "2_industry_chain": self.prompts.industry_chain(),
                "3_top_companies": self.prompts.top_companies(),
                "4_company_analysis": "（先执行任务3获取公司列表，再执行 company_deep_dive）",
                "5_knowledge_modules": self.prompts.knowledge_modules(),
                "7_cutting_edge": self.prompts.cutting_edge(),
            },
        }
        path = self.output_dir / f"research_brief_{today_str()}.json"
        save_json(brief, path)
        self.archive.save_report("brief", path)
        return {"brief": brief, "path": str(path)}

    def analyze_domain(self, provider: str = None) -> dict:
        """深度研究：产出"模型无关任务包"，可供任何 agent/模型执行。

        provider 取值：
          - none / workbuddy / taskpack：只产出任务包（不直连 LLM）
          - openai / deepseek / qwen / azure：Search 自带联网 LLM 直连能力
        """
        provider = provider or self.config.get("llm", {}).get("provider", "none")
        if provider in ("none", "workbuddy", "taskpack"):
            # 返回任务清单，由任何 agent（Codex/WorkBuddy/Claude Code/自写脚本）执行
            return self.build_research_brief()
        from .agents.base import AgentContext
        from .services.provider_factory import create_provider
        ctx = AgentContext.from_config(self.config)
        brief = self.build_research_brief()["brief"]
        tasks = []
        for name, prompt in brief["tasks"].items():
            if isinstance(prompt, str) and not prompt.startswith("（先执行"):
                tasks.append(f"## {name}\n{prompt}")
        combined = (
            "你正在执行一份行业研究任务包。严格区分事实与研判；事实必须附可访问 URL、"
            "发布日期和统计口径；未知信息写 N/A，禁止猜测。输出 Markdown。\n\n"
            + "\n\n".join(tasks))
        result = create_provider(self.config, provider, ctx.industry_root).complete(combined)
        out_dir = ctx.industry_dir / "api_runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = out_dir / f"domain_research_{stamp}.md"
        report_path.write_text(result.text, encoding="utf-8")
        meta_path = out_dir / f"domain_research_{stamp}.json"
        meta_path.write_text(json.dumps({
            "provider": result.provider, "model": result.model,
            "response_id": result.response_id, "usage": result.usage,
            "report": str(report_path),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"mode": "api", "provider": result.provider,
                "model": result.model, "path": str(report_path),
                "metadata": str(meta_path)}

    # ===================================================================
    # 阶段二：持续监控（每日/每周推送）
    # ===================================================================
    def run_daily(self, since_days: int = 1) -> dict:
        """执行每日情报收集."""
        from .crawlers.news_crawler import NewsAggregator
        from .crawlers.academic_crawler import AcademicAggregator
        from .crawlers.finance_crawler import FinanceAggregator
        news_agg = NewsAggregator(self.config)
        news = news_agg.collect(since_days=since_days)

        # 分类
        from .crawlers.base import Article
        cats = {"general": [], "startup": [], "finance": [], "policy": []}
        for a in news:
            cats.setdefault(a.category, []).append(a)
        news_agg.mark_seen(news)

        academic_agg = AcademicAggregator(self.config)
        academic = academic_agg.collect(since_days=since_days)
        academic_agg.mark_seen(academic)

        # 金融 + 政策已在 categories 里，这里再单独取（更长窗口）
        fin_agg = FinanceAggregator(self.config)
        fin_news = fin_agg.collect_news(since_days=since_days)
        for cat in ("finance", "policy"):
            for a in fin_news.get(cat, []):
                if a not in cats[cat]:
                    cats[cat].append(a)

        html = self.digest.build_daily(
            cats.get("general", []), academic,
            cats.get("finance", []), cats.get("policy", []),
        )
        path = self.output_dir / f"daily_{today_str()}.html"
        path.write_text(html, encoding="utf-8")

        # 归档到 D 盘（JSON + SQLite，按 时间/类别 索引）
        self.archive.save_articles(cats.get("general", []), category="news")
        self.archive.save_articles(cats.get("startup", []), category="startup")
        self.archive.save_articles(academic, category="academic")
        self.archive.save_articles(cats.get("finance", []), category="finance")
        self.archive.save_articles(cats.get("policy", []), category="policy")
        self.archive.save_report("daily", path)

        result = {
            "news_count": len(cats.get("general", [])),
            "academic_count": len(academic),
            "finance_count": len(cats.get("finance", [])),
            "policy_count": len(cats.get("policy", [])),
            "html_path": str(path),
        }
        return result

    def run_weekly(self, since_days: int = 7) -> dict:
        """执行每周金融政策简报."""
        from .crawlers.finance_crawler import FinanceAggregator
        fin_agg = FinanceAggregator(self.config)
        news = fin_agg.collect_news(since_days=since_days)
        finance = news.get("finance", [])
        policy = news.get("policy", [])

        # 可选：拉取重点公司市场数据
        market_data = []
        companies = self.config.get("domain", {}).get("tracked_companies", [])
        if companies:
            market_data = fin_agg.collect_market_data(companies)

        html = self.digest.build_weekly(finance, policy, market_data)
        path = self.output_dir / f"weekly_{today_str()}.html"
        path.write_text(html, encoding="utf-8")

        # 归档
        self.archive.save_articles(finance, category="finance")
        self.archive.save_articles(policy, category="policy")
        self.archive.save_report("weekly", path)

        result = {
            "finance_count": len(finance),
            "policy_count": len(policy),
            "market_count": len(market_data),
            "html_path": str(path),
        }
        return result

    def run_timeline(self, since_days: int = 365) -> dict:
        """生成近一年发展轨迹（历史回顾）."""
        from .crawlers.news_crawler import NewsAggregator
        news_agg = NewsAggregator(self.config)
        news = news_agg.collect(since_days=since_days)
        from .crawlers.base import Article
        # 仅保留 general + startup 作为产业轨迹
        items = [a for a in news if a.category in ("general", "startup", "finance")]
        headlines = [f"{a.published} | {a.title}" for a in items]
        html = self.digest.build_timeline(items)
        path = self.output_dir / f"timeline_{today_str()}.html"
        path.write_text(html, encoding="utf-8")
        self.archive.save_articles(items)
        self.archive.save_report("timeline", path)
        # 同时输出分析提示
        timeline_prompt = self.prompts.yearly_timeline(headlines)
        return {
            "count": len(items),
            "html_path": str(path),
            "analysis_prompt": timeline_prompt,
        }

    # ===================================================================
    # 便捷：直接抓取原始数据（供 Codex/API 进一步处理）
    # ===================================================================
    def collect_raw(self, since_days: int = 1) -> dict:
        from .crawlers.news_crawler import NewsAggregator
        from .crawlers.academic_crawler import AcademicAggregator
        news_agg = NewsAggregator(self.config)
        news = news_agg.collect(since_days=since_days)
        academic_agg = AcademicAggregator(self.config)
        academic = academic_agg.collect(since_days=since_days)
        # 原始数据同样归档
        self.archive.save_articles(news)
        self.archive.save_articles(academic, category="academic")
        return {
            "news": [a.to_dict() for a in news],
            "academic": [a.to_dict() for a in academic],
        }
