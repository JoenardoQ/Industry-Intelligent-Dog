"""Planner Agent：按 industry/level/region 生成任务 DAG 并编排全部 Agent.

DAG 规格见 IIOS_SPEC.md §8：
  value_chain → industry_overview → company_research → scoring
  technology_map → learning_path
  (并行) news/paper/policy/finance/startup 爬取 → kg_build → report
"""

from __future__ import annotations

import json
from datetime import datetime

from .base import BaseAgent
from ..schema import IIOSRecord


# 标准任务 DAG：节点 = (task_id, agent, 说明)，edges = 依赖
STANDARD_DAG = {
    "nodes": [
        {"id": "value_chain",   "agent": "value_chain", "kind": "llm_task",
         "desc": "产业链标准化（模板 + 细化）"},
        {"id": "industry",      "agent": "industry",    "kind": "llm_task",
         "desc": "行业总览 12 节报告"},
        {"id": "company",       "agent": "company",     "kind": "llm_task",
         "desc": "各层级 Top 公司 + 24 项指标 + 8 维评分"},
        {"id": "technology",    "agent": "technology",  "kind": "llm_task",
         "desc": "技术地图 + 技术树"},
        {"id": "learning",      "agent": "learning",    "kind": "llm_task",
         "desc": "学习路径 DAG"},
        {"id": "timeline",      "agent": "timeline",    "kind": "llm_task",
         "desc": "四类时间轴 → events 表"},
        {"id": "social",        "agent": "social",      "kind": "llm_task",
         "desc": "高管发言追踪"},
        {"id": "crawl_all",     "agent": "crawlers",    "kind": "crawler",
         "desc": "新闻/论文/GitHub/融资/招聘/高管情报采集（crawl-daily）"},
        {"id": "kg_build",      "agent": "kg",          "kind": "code",
         "desc": "知识图谱构建（kg --build --industry）"},
        {"id": "report",        "agent": "reporter",    "kind": "code",
         "desc": "日报/周报生成与推送（crawl-daily|crawl-weekly）"},
    ],
    "edges": [
        ["value_chain", "industry"],
        ["value_chain", "company"],
        ["industry", "company"],
        ["technology", "learning"],
        ["crawl_all", "kg_build"],
        ["company", "kg_build"],
        ["kg_build", "report"],
        ["timeline", "report"],
    ],
}


class PlannerAgent(BaseAgent):
    name = "planner"
    agent_type = "code"
    description = "生成任务 DAG 并调用各 Agent 产出任务包"

    def run(self, agents_filter: list[str] = None, **kw) -> list[IIOSRecord]:
        from . import AGENT_REGISTRY  # 延迟导入避免循环

        c = self.ctx
        plan = {
            "industry": c.industry, "level": c.level,
            "region": c.region, "lang": c.lang,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "dag": STANDARD_DAG,
            "task_bundles": {},
        }

        all_records: list[IIOSRecord] = []
        research_agents = ["value_chain", "industry", "company",
                           "technology", "learning", "timeline", "social"]
        if agents_filter:
            research_agents = [a for a in research_agents if a in agents_filter]

        for aname in research_agents:
            agent = AGENT_REGISTRY[aname](c)
            records = agent.run()
            tasks = [r for r in records if r.type == "task"]
            if tasks:
                bundle = agent.save_tasks(tasks, aname)
                plan["task_bundles"][aname] = str(bundle)
            all_records.extend(records)

        # 生成 Mermaid DAG 图
        mmd = ["graph TD"]
        for n in STANDARD_DAG["nodes"]:
            shape = ("[/", "/]") if n["kind"] == "crawler" else \
                    (("[[", "]]") if n["kind"] == "code" else ("[", "]"))
            mmd.append(f'    {n["id"]}{shape[0]}"{n["id"]}<br/>{n["desc"]}"{shape[1]}')
        for a, b in STANDARD_DAG["edges"]:
            mmd.append(f"    {a} --> {b}")
        (c.industry_dir / "plan.mmd").write_text("\n".join(mmd), encoding="utf-8")

        plan_path = c.industry_dir / "plan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        all_records.append(IIOSRecord(
            type="task", title=f"[planner] {c.industry} 全量研究计划",
            summary=f"已生成 {len(plan['task_bundles'])} 个任务包 + DAG，"
                    f"执行方式见 plan.json；爬虫与 KG 由 CLI 命令承担。",
            source="agent:planner", industry=c.industry,
            extra={"plan_file": str(plan_path),
                   "next_steps": [
                       f"1. python -m src.main crawl-daily --industry {c.industry} --days 7",
                       "2. 将 tasks/*.json 中的任务包交给 WorkBuddy/Codex 执行（LLM 分析）",
                       f"3. python -m src.main kg --build --industry {c.industry}",
                       f"4. python -m src.main crawl-weekly --industry {c.industry}",
                   ]},
        ))
        return all_records
