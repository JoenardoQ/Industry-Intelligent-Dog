"""模块目录：把现有爬虫 / 生成器 / 服务 / Agent 包装为标准模块.

每个模块都是薄包装——不改变原有实现的内部逻辑，只做：
接收 ModuleContext → 调用原有类 → 结果写入 ctx.state → 返回 ModuleResult。
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseModule, ModuleContext, ModuleResult, ModuleSpec, register
from ..utils import today_str


def _refs(articles, limit: int = 50) -> list[dict]:
    """从 Article 列表提取引用清单（每条信息必须带链接）."""
    out = []
    for a in articles[:limit]:
        if getattr(a, "url", ""):
            out.append({"title": a.title, "url": a.url,
                        "source": a.source, "published": a.published})
    return out


def _save_by_category(ctx: ModuleContext, articles, mapping: dict = None) -> dict:
    """按类别归档一批 Article，返回 {类别: 条数}."""
    groups: dict[str, list] = {}
    for a in articles:
        cat = (mapping or {}).get(a.category, a.category)
        groups.setdefault(cat, []).append(a)
    counts = {}
    for cat, items in groups.items():
        ctx.orch.archive.save_articles(items, category=cat)
        counts[cat] = len(items)
    return counts


# ======================================================================
# 采集模块（collect）
# ======================================================================
@register
class NewsCollectModule(BaseModule):
    spec = ModuleSpec(
        id="news_collect", name="新闻采集", category="collect",
        description="RSS + NewsAPI + GNews 聚合抓取行业新闻（含初创/金融/政策源），关键词过滤 + 去重",
        kind="code", network=True, default_selected=True,
        params=[{"key": "days", "label": "抓取天数窗口", "type": "int", "default": 1}],
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        from ..crawlers.news_crawler import NewsAggregator
        days = int(ctx.param("days", 1))
        agg = NewsAggregator(ctx.config)
        articles = agg.collect(since_days=days)
        counts = _save_by_category(ctx, articles)
        agg.mark_seen(articles)

        cats = ctx.state.setdefault("news_by_cat", {})
        for a in articles:
            cats.setdefault(a.category, []).append(a)

        ctx.log(f"[news_collect] {ctx.industry}：抓取 {len(articles)} 条（{counts}）")
        return ModuleResult(
            message=f"新闻 {len(articles)} 条", data=counts, references=_refs(articles))


@register
class AcademicCollectModule(BaseModule):
    spec = ModuleSpec(
        id="academic_collect", name="学术采集", category="collect",
        description="arXiv + Semantic Scholar 论文抓取，按行业档案的 arXiv 分类与关键词过滤",
        kind="code", network=True, default_selected=True,
        params=[{"key": "days", "label": "抓取天数窗口", "type": "int", "default": 1}],
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        from ..crawlers.academic_crawler import AcademicAggregator
        days = int(ctx.param("days", 1))
        agg = AcademicAggregator(ctx.config)
        articles = agg.collect(since_days=days)
        if articles:
            ctx.orch.archive.save_articles(articles, category="academic")
        agg.mark_seen(articles)
        ctx.state["academic"] = articles
        ctx.log(f"[academic_collect] {ctx.industry}：论文 {len(articles)} 篇")
        return ModuleResult(
            message=f"论文 {len(articles)} 篇", data={"academic": len(articles)},
            references=_refs(articles))


@register
class FinancePolicyCollectModule(BaseModule):
    spec = ModuleSpec(
        id="finance_policy_collect", name="金融与政策采集", category="collect",
        description="抓取金融资讯与政策要闻（复用 RSS finance/policy 源，更长窗口）",
        kind="code", network=True, default_selected=True,
        params=[{"key": "days", "label": "抓取天数窗口", "type": "int", "default": 1}],
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        from ..crawlers.finance_crawler import FinanceAggregator
        days = int(ctx.param("days", 1))
        agg = FinanceAggregator(ctx.config)
        news = agg.collect_news(since_days=days)
        cats = ctx.state.setdefault("news_by_cat", {})
        total = 0
        for cat in ("finance", "policy"):
            items = news.get(cat, [])
            existing_urls = {a.url for a in cats.get(cat, [])}
            fresh = [a for a in items if a.url not in existing_urls]
            cats.setdefault(cat, []).extend(fresh)
            if fresh:
                ctx.orch.archive.save_articles(fresh, category=cat)
            total += len(fresh)
        ctx.log(f"[finance_policy_collect] {ctx.industry}：金融 {len(news.get('finance', []))} / 政策 {len(news.get('policy', []))}，新增 {total}")
        refs = _refs(news.get("finance", [])) + _refs(news.get("policy", []))
        return ModuleResult(
            message=f"金融/政策新增 {total} 条",
            data={"finance": len(news.get("finance", [])),
                  "policy": len(news.get("policy", []))},
            references=refs)


@register
class MarketDataModule(BaseModule):
    spec = ModuleSpec(
        id="market_data", name="重点公司行情", category="collect",
        description="AKShare 抓取行业档案 tracked_companies 的实时行情（可选依赖 akshare）",
        kind="code", network=True,
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        from ..crawlers.finance_crawler import FinanceAggregator
        companies = ctx.config.get("domain", {}).get("tracked_companies", [])
        if not companies:
            return ModuleResult(ok=False, message="行业档案未配置 tracked_companies，跳过")
        data = FinanceAggregator(ctx.config).collect_market_data(companies)
        ctx.state["market_data"] = data
        ctx.log(f"[market_data] 行情 {len(data)}/{len(companies)} 家")
        refs = [{"title": f"{d.get('name')} 行情快照", "url": "",
                 "source": "AKShare/东方财富", "published": today_str()} for d in data]
        return ModuleResult(message=f"行情 {len(data)} 家",
                            data={"count": len(data)}, references=refs)


# ======================================================================
# 报告模块（report）
# ======================================================================
@register
class DailyReportModule(BaseModule):
    spec = ModuleSpec(
        id="daily_report", name="每日情报日报", category="report",
        description="把本次采集的新闻/论文/金融/政策渲染为 HTML 日报（含编号引用列表）并归档",
        kind="code",
        requires=["news_collect", "academic_collect", "finance_policy_collect"],
        default_selected=True,
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        cats = ctx.state.get("news_by_cat", {})
        academic = ctx.state.get("academic", [])
        html = ctx.orch.digest.build_daily(
            cats.get("general", []), academic,
            cats.get("finance", []), cats.get("policy", []))
        path = ctx.orch.output_dir / f"daily_{today_str()}.html"
        path.write_text(html, encoding="utf-8")
        ctx.orch.archive.save_report("daily", path)
        ctx.state.setdefault("reports", {})["daily"] = str(path)
        ctx.log(f"[daily_report] 日报已生成：{path.name}")
        return ModuleResult(message=f"日报：{path.name}",
                            artifacts=[{"label": "每日情报日报", "path": str(path)}])


@register
class WeeklyReportModule(BaseModule):
    spec = ModuleSpec(
        id="weekly_report", name="每周金融政策简报", category="report",
        description="金融+政策周报（若选了重点公司行情则附市场数据表），HTML 归档",
        kind="code", requires=["finance_policy_collect"],
        after=["market_data"],
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        cats = ctx.state.get("news_by_cat", {})
        days = max(int(ctx.param("days", 7)), 7)
        # 周报窗口更长：若本次只采了 1 天，补采 7 天金融/政策
        if days >= 7:
            from ..crawlers.finance_crawler import FinanceAggregator
            agg = FinanceAggregator(ctx.config)
            extra = agg.collect_news(since_days=days)
            for cat in ("finance", "policy"):
                existing = {a.url for a in cats.get(cat, [])}
                fresh = [a for a in extra.get(cat, []) if a.url not in existing]
                cats.setdefault(cat, []).extend(fresh)
        html = ctx.orch.digest.build_weekly(
            cats.get("finance", []), cats.get("policy", []),
            ctx.state.get("market_data", []))
        path = ctx.orch.output_dir / f"weekly_{today_str()}.html"
        path.write_text(html, encoding="utf-8")
        ctx.orch.archive.save_report("weekly", path)
        ctx.state.setdefault("reports", {})["weekly"] = str(path)
        ctx.log(f"[weekly_report] 周报已生成：{path.name}")
        return ModuleResult(message=f"周报：{path.name}",
                            artifacts=[{"label": "每周简报", "path": str(path)}])


@register
class TimelineReportModule(BaseModule):
    spec = ModuleSpec(
        id="timeline_report", name="年度发展轨迹", category="report",
        description="汇总近一年新闻生成按月分组的发展轨迹 HTML（默认 365 天窗口）",
        kind="code", network=True,
        params=[{"key": "days", "label": "回溯天数", "type": "int", "default": 365}],
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        days = int(ctx.param("days", 365))
        r = ctx.orch.run_timeline(since_days=days)
        ctx.state.setdefault("reports", {})["timeline"] = r["html_path"]
        ctx.log(f"[timeline_report] 轨迹 {r['count']} 条：{Path(r['html_path']).name}")
        return ModuleResult(
            message=f"轨迹 {r['count']} 条", data={"count": r["count"]},
            artifacts=[{"label": "年度发展轨迹", "path": r["html_path"]}])


@register
class ResearchBriefModule(BaseModule):
    spec = ModuleSpec(
        id="research_brief", name="研究任务简报", category="report",
        description="生成一次性领域研究任务清单（brief JSON），供 WorkBuddy/Codex 执行分析",
        kind="llm_task",
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        r = ctx.orch.build_research_brief()
        ctx.log(f"[research_brief] 简报：{Path(r['path']).name}")
        return ModuleResult(message="研究简报已生成",
                            artifacts=[{"label": "研究任务简报", "path": r["path"]}])


# ======================================================================
# 研究模块（research，LLM 任务包）
# ======================================================================
class _AgentModule(BaseModule):
    """研究 Agent 模块基类：运行 Agent → 保存任务包 → 汇报产出."""

    agent_name = ""

    def run(self, ctx: ModuleContext) -> ModuleResult:
        from ..agents import AGENT_REGISTRY
        agent = AGENT_REGISTRY[self.agent_name](ctx.agent_ctx)
        records = agent.run()
        tasks = [r for r in records if r.type == "task"]
        artifacts, refs = [], []
        if tasks:
            bundle = agent.save_tasks(tasks, self.agent_name)
            artifacts.append({"label": f"{self.spec.name}任务包", "path": str(bundle)})
        for r in records:
            if r.type != "task":
                refs.append({"title": r.title, "url": r.url,
                             "source": r.source, "published": r.published})
        # ValueChain 等会额外离线产出 mmd/json
        for fname in ("value_chain.mmd", "value_chain.json"):
            f = ctx.agent_ctx.industry_dir / fname
            if self.agent_name == "value_chain" and f.exists():
                artifacts.append({"label": fname, "path": str(f)})
        ctx.log(f"[{self.spec.id}] 任务包 {len(tasks)} 个（LLM 执行后回写知识库）")
        return ModuleResult(
            message=f"{self.spec.name}：{len(tasks)} 个任务包",
            data={"tasks": len(tasks)}, artifacts=artifacts, references=refs)


def _agent_module(module_id: str, name: str, desc: str, agent_name: str):
    return register(type(
        f"Research_{module_id}", (_AgentModule,),
        {"agent_name": agent_name,
         "spec": ModuleSpec(id=module_id, name=name, category="research",
                            description=desc, kind="llm_task")},
    ))


@register
class ResearchPlanModule(BaseModule):
    spec = ModuleSpec(
        id="research_plan", name="全量研究计划", category="research",
        description="Planner 生成任务 DAG（plan.json/plan.mmd）并为勾选的各研究 Agent 产出任务包",
        kind="llm_task",
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        from ..agents import PlannerAgent
        agents_filter = ctx.param("agents_filter") or None
        records = PlannerAgent(ctx.agent_ctx).run(agents_filter=agents_filter)
        tasks = [r for r in records if r.type == "task"]
        d = ctx.agent_ctx.industry_dir
        artifacts = [
            {"label": "研究计划 plan.json", "path": str(d / "plan.json")},
            {"label": "任务 DAG plan.mmd", "path": str(d / "plan.mmd")},
        ]
        tasks_dir = d / "tasks"
        if tasks_dir.exists():
            for f in sorted(tasks_dir.glob("*.json")):
                artifacts.append({"label": f"任务包 {f.stem}", "path": str(f)})
        scope = "、".join(agents_filter) if agents_filter else "全部 7 个研究 Agent"
        ctx.log(f"[research_plan] {ctx.industry}：DAG + 任务包（{scope}）")
        return ModuleResult(
            message=f"研究计划：{len(tasks) - 1} 个 Agent 任务包 + DAG",
            data={"tasks": len(tasks) - 1}, artifacts=artifacts)


_agent_module("research_industry", "行业总览",
              "12 节行业总览报告任务包（概述/规模/玩家/趋势/政策等，强制引用来源）", "industry")
_agent_module("research_value_chain", "产业链分析",
              "产业链标准化：内置模板离线出图 + LLM 细化任务包（层级/壁垒/集中度/毛利）", "value_chain")
_agent_module("research_company", "公司画像",
              "各层级 Top 公司清单 + 24 项指标 + 8 维评分任务包（要求数据日期与来源）", "company")
_agent_module("research_technology", "技术地图",
              "技术方向→子方向→知识模块→关键论文（附链接）→技术树任务包", "technology")
_agent_module("research_learning", "学习路径",
              "按水平生成带前置依赖的学习 DAG + Roadmap 任务包", "learning")
_agent_module("research_timeline", "时间轴",
              "产业/公司/技术/政策四类时间轴任务包（事件含 source_url，供入库）", "timeline")
_agent_module("research_social", "高管发言追踪",
              "CEO/CTO/创始人公开发言情报任务包（原文链接 + 可信度标注）", "social")


# ======================================================================
# 图谱模块（graph）
# ======================================================================
@register
class KgBuildModule(BaseModule):
    spec = ModuleSpec(
        id="kg_build", name="知识图谱构建", category="graph",
        description="读取知识库回写结果（value_chain/companies/events）+ 新闻共现，构建实体关系图谱并导出 Mermaid",
        kind="code", after=["research_plan"],
    )

    def run(self, ctx: ModuleContext) -> ModuleResult:
        from ..agents.kg import KnowledgeGraphAgent
        agent = KnowledgeGraphAgent(ctx.agent_ctx)
        rec = agent.run()[0]
        mmd = ctx.agent_ctx.industry_dir / "knowledge_graph" / "graph.mmd"
        totals = rec.extra.get("kg_totals", {})
        ctx.log(f"[kg_build] 图谱总量：{totals}")
        return ModuleResult(
            message=rec.summary, data=totals,
            artifacts=[{"label": "知识图谱 graph.mmd", "path": str(mmd)}])
