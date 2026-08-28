"""三种行业报告生成（近五年趋势 / 近两年流行 / 近半年技术）.

以 LLM 任务包（模型无关）形式产出，存入 DomainIntelData/<行业>/one_time/reports/。
任何 agent/模型（Codex / WorkBuddy / Claude Code / 自写 API）执行 prompt 后回写 Markdown。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

REPORTS = {
    "trend_5y": {
        "title": "近五年行业报告（趋势）",
        "window": "近五年",
        "focus": "趋势",
        "prompt": (
            "请输出一份【近五年行业趋势报告】（Markdown），着重**长期趋势**：\n"
            "1. 五年产业规模/结构/区域格局的演变曲线（分年列出关键转折点）\n"
            "2. 技术路线的长期演进方向与范式转移\n"
            "3. 产业链权力结构的变迁（哪些层级崛起/衰落）\n"
            "4. 驱动趋势的底层因素（政策/资本/需求/技术突破）\n"
            "5. 未来 3-5 年趋势研判\n"
            "每个论断附来源 [n]，文末 references[]（含 url 与年份）。"),
    },
    "popular_2y": {
        "title": "近两年行业报告（流行）",
        "window": "近两年",
        "focus": "流行",
        "prompt": (
            "请输出一份【近两年行业流行报告】（Markdown），着重**当下流行/热点**：\n"
            "1. 近两年最热门的技术概念/产品/赛道（按热度排序）\n"
            "2. 资本追逐的热点（融资热点、明星公司、估值案例）\n"
            "3. 舆论与社区关注的焦点（GitHub/社交媒体/媒体高频词）\n"
            "4. 流行背后的供需逻辑与可持续性判断\n"
            "每条热点附来源 [n]，文末 references[]（含 url 与时间）。"),
    },
    "tech_6m": {
        "title": "近半年行业报告（技术）",
        "window": "近半年",
        "focus": "技术",
        "prompt": (
            "请输出一份【近半年行业技术报告】（Markdown），着重**最新技术进展**：\n"
            "1. 近半年最重要的技术突破/论文/产品发布（按月梳理）\n"
            "2. 关键技术指标的最新水平（性能/成本/良率等，给数据）\n"
            "3. 学术界与工业界的最新方向对比\n"
            "4. 尚待解决的技术瓶颈\n"
            "5. 面向略懂一二的读者的通俗解释（每个技术点配一段白话）\n"
            "每条进展附来源 [n]，文末 references[]（含 url 与日期）。"),
    },
}

EVIDENCE_POLICY = (
    "\n\n【统一证据要求】\n"
    "- 事实与研判分段；事实逐条引用，不得引用搜索结果页或无出处摘要。\n"
    "- 数值必须给出 as_of、currency、unit、统计口径；冲突数据并列说明差异。\n"
    "- 优先官方披露、监管文件、论文原文和公司 IR；未知写 N/A，禁止推测补齐。\n"
    "- 输出状态为 draft，并同时给出 claims[]：claim/evidence_urls/confidence/status。"
)


def build_report_tasks(store, industry_name: str, industry_en: str = "") -> list[dict]:
    """为某行业生成三份报告的 LLM 任务包，并写入 one_time/reports/tasks.json."""
    tasks = []
    for rid, meta in REPORTS.items():
        header = (f"你是\"{industry_name}\"({industry_en or industry_name})行业的资深研究分析师，"
                  f"面向对该领域略懂一二的读者。\n时间窗口：{meta['window']}；侧重：{meta['focus']}。\n\n")
        tasks.append({
            "id": rid,
            "title": meta["title"],
            "focus": meta["focus"],
            "window": meta["window"],
            "prompt": header + meta["prompt"] + EVIDENCE_POLICY,
            "output_file": f"one_time/reports/{rid}.md",
        })
    # 写入任务清单
    out = {
        "industry": industry_name,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "instruction": "把每个 task 的 prompt 交给任意 LLM/agent 执行，"
                       "将 Markdown 结果写入对应 output_file。",
        "tasks": tasks,
    }
    path = Path(store.reports) / "tasks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return tasks
