"""深度研究报告生成器（Deep Research Reports）.

不同于 periodic 的日/周/月/季监控简报，这里产出**可交付的研究初稿**，
四种类型（对应用户示例）：
  quarterly   《<行业>行业季度报告》   —— 季度全景：市场/技术/资本/政策
  chain       《<主题>产业链研究》      —— 如 RISC-V 产业链：上游IP→设计→制造→生态
  landscape   《<主题>竞争格局》        —— 如量子芯片：四类玩家 + 份额 + 技术路线对比
  market      《<主题>市场分析》        —— 如 EDA 市场：规模/增速/格局/驱动因素

每份报告 = 一个 LLM 任务包（模型无关）。任务包**显式列出本地可读的数据文件**
（每日情报/知识三层/竞争格局/信息源），要求 agent 先读本地数据、引用编号成文，
再联网补充，最后回写 Markdown 到 output_file。

存储：DomainIntelData/<行业>/one_time/reports/deep_tasks.json（任务清单）
     DomainIntelData/<行业>/one_time/reports/deep/<rid>.md（agent 回写的成品）
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# 四种深度报告：标题模板 + 研究提纲
# {ind} = 行业名，{topic} = 主题（默认取行业名，可在 prompt 中自行替换）
DEEP_REPORTS = {
    "quarterly": {
        "title": "《{ind}行业季度报告》",
        "topic": "{ind}",
        "outline": [
            "本季度市场全景：规模/增速/区域结构变化（给数据，引用 [n]）",
            "技术进展：本季度最重要的发布/突破/论文（按月梳理，引用 [n]）",
            "资本动向：融资/并购/IPO 清单与解读（引用本地 funding 语料 [n]）",
            "政策与监管：本季度政策事件及其影响（引用 [n]）",
            "竞争格局变化：Leader/Challenger/Emerging/Declining 的迁移（引用本地 landscape）",
            "下季度研判：3-5 条关键趋势 + 风险点",
        ],
    },
    "chain": {
        "title": "《{topic}产业链研究》",
        "topic": "{ind}",
        "outline": [
            "产业链全景图：从上游到下游逐环节拆解（建议配 ASCII/表格图）",
            "每个环节：市场规模/主要玩家/技术壁垒/毛利率水平（引用 [n]）",
            "关键环节深拆：卡脖子环节 + 国产/替代现状",
            "链上重点公司逐一画像（引用本地知识库实体 + 情报 [n]）",
            "高校/研究组的技术源头梳理（引用本地 knowledge 实体）",
            "产业链趋势与投资机会研判",
        ],
    },
    "landscape": {
        "title": "《{topic}竞争格局》",
        "topic": "{ind}",
        "outline": [
            "玩家分层：Leader/Challenger/Emerging/Declining 四象限（先引用本地 landscape.json，再校正）",
            "市场份额估算：主要玩家份额(%) + 估算依据（引用 [n]）",
            "技术路线对比：各阵营的技术押注与成熟度",
            "近一年格局关键变化：谁升谁降、为什么（引用 [n]）",
            "护城河与软肋分析（每家 Leader 一段）",
            "格局推演：未来 2-3 年最可能的剧本（2-3 种情景）",
        ],
    },
    "market": {
        "title": "《{topic}市场分析》",
        "topic": "{ind}",
        "outline": [
            "市场定义与边界：统计口径说明",
            "规模与增速：近 3-5 年市场规模、CAGR、分区域/分应用结构（给数据，引用 [n]）",
            "需求侧：下游驱动力拆解（哪个应用/行业在买、为什么）",
            "供给侧：主要供应商与份额、定价与商业模式",
            "波特五力/进入壁垒分析",
            "预测与机会：未来 3 年规模预测 + 高潜力细分（引用 [n]）",
        ],
    },
}

DEEP_ORDER = ("quarterly", "chain", "landscape", "market")


def _data_manifest(store) -> str:
    """列出 agent 应读取的本地数据文件（写进 prompt，落实"自动引用数据和来源"）."""
    lines = [
        "在动笔前，请先读取以下本地数据文件（相对 DomainIntelData/<行业>/ 的路径），"
        "凡引用其中内容须在文中标注来源编号 [n]，并在文末 references[] 列出 url/日期：",
        "- periodic/daily/<日期>/news.json    每日新闻（含 credibility 可信度/references 印证）",
        "- periodic/daily/<日期>/papers.json  每日论文",
        "- periodic/daily/<日期>/funding.json 每日融资事件",
        "- periodic/daily/<日期>/github.json  每日开源项目动态",
        "- periodic/daily/<日期>/ceo.json     CEO/高管公开发言",
        "- periodic/daily/<日期>/hiring.json  招聘信号",
        "- one_time/knowledge/entities.json   三层知识：企业/高校实体（含所属产业链）",
        "- one_time/knowledge/chains.json     产业链层级",
        "- one_time/landscape/landscape.json  竞争格局四类玩家骨架（若存在）",
        "- one_time/impact/events.json        近期高可信行业事件（若存在）",
        "- sources.json                       本行业信息源清单",
        "本地数据不足的部分可联网补充，但同样必须给出 url 引用。",
    ]
    return "\n".join(lines)


def build_deep_reports(store, industry_name: str, industry_en: str = "",
                       rtype: str = None, topic: str = "") -> list[dict]:
    """生成深度研究报告任务包并写入 deep_tasks.json.

    rtype: 为空则生成全部四种；否则只生成指定类型
           （quarterly / chain / landscape / market）。
    topic: 自定义研究主题（如 RISC-V / 量子芯片 / EDA），默认取行业名。
    返回任务列表。
    """
    types = [rtype] if rtype else list(DEEP_ORDER)
    tasks = []
    for rid in types:
        meta = DEEP_REPORTS.get(rid)
        if not meta:
            raise ValueError(f"未知深度报告类型: {rid!r}，可选 {list(DEEP_REPORTS)}")
        tp = (topic or meta["topic"]).replace("{ind}", industry_name)
        title = meta["title"].replace("{ind}", industry_name).replace("{topic}", tp)
        outline = "\n".join(f"{i+1}. {o}" for i, o in enumerate(meta["outline"]))
        outfile = f"one_time/reports/deep/{rid}.md"

        prompt = f"""你是"{industry_name}"({industry_en or industry_name})行业的资深研究分析师。
请撰写深度研究报告 {title}（主题：{tp}），要求达到**可直接作为研究初稿交付**的水准。

【本地数据引用（必须先读）】
{_data_manifest(store)}

【报告提纲】
{outline}

【硬性要求】
1. 全文 Markdown，3000 字以上；每个论断附来源编号 [n]，文末 references[]（url + 日期）
2. 数据优先引用本地 periodic/ 与 one_time/ 语料；本地没有的联网补充
3. 区分"事实"与"研判"：事实必须有引用，研判须写明推理依据
4. 涉及市场份额/规模数字时给出估算口径
5. 末尾附"数据附录"：本报告引用的本地条目清单（标题 + url + 日期）

输出：将 Markdown 正文写入 {outfile}；引用写入 deep/{rid}.references.json；
原子事实写入 deep/{rid}.claims.json，每条包含 claim/evidence_urls/as_of/confidence/status，
其中 status 只能为 verified/disputed/unverified。"""

        tasks.append({
            "id": f"deep_{rid}",
            "type": "deep_report",
            "title": title,
            "topic": tp,
            "prompt": prompt,
            "output_file": f"one_time/reports/deep/{rid}.md",
            "references_file": f"one_time/reports/deep/{rid}.references.json",
            "claims_file": f"one_time/reports/deep/{rid}.claims.json",
        })

    out = {
        "industry": industry_name,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "instruction": "把每个 task 的 prompt 交给任意 LLM/agent 执行：先读 prompt 中列出的"
                       "本地数据文件，引用编号成文，Markdown 写入 output_file，"
                       "引用清单写入 references_file。",
        "tasks": tasks,
    }
    path = Path(store.reports) / "deep_tasks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return tasks
