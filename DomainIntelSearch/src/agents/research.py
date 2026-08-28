"""研究组 Agent：Industry / ValueChain / Company / Technology / Learning / Timeline / Social.

均为 llm_task 型：产出结构化任务包（IIOSRecord type=task），
由 WorkBuddy / Codex / 任意 LLM 执行后把 Markdown 写回 industry/<industry>/ 目录。
ValueChain 额外内置行业模板，可离线直接产出 Mermaid 产业链图。
"""

from __future__ import annotations

import json

from .base import BaseAgent
from ..schema import IIOSRecord, COMPANY_METRICS_TEMPLATE, SCORE_DIMENSIONS


# ======================================================================
# 1. Industry Agent
# ======================================================================
class IndustryAgent(BaseAgent):
    name = "industry"
    description = "行业整体介绍：概述/规模/历史/玩家/趋势/挑战/机会/政策"

    def run(self, **kw) -> list[IIOSRecord]:
        c = self.ctx
        prompt = f"""你是"{c.industry}"行业的首席研究分析师，面向【{c.level_label}】、区域视角【{c.region}】。
生成行业总览报告，必须包含以下 12 节（Markdown 二级标题）：
1. 行业概述  2. 行业规模（含数据来源与年份）  3. 发展历史（关键节点）
4. 主要玩家（按区域分组）  5. 产业链概览  6. 上下游关系
7. 关键技术  8. 未来趋势（3-5年）  9. 主要挑战  10. 主要机会
11. 投资热点  12. 政策影响（{c.region} 视角）
要求：每节引用至少 1 个可核实来源；数字必须给出年份；结尾给出整体 confidence(0-1)。"""
        return [self.make_task("行业总览", prompt, "overview.md")]


# ======================================================================
# 2. ValueChain Agent（内置模板 + LLM 适配任务）
# ======================================================================
VALUE_CHAIN_TEMPLATES = {
    "半导体": ["EDA", "IP", "Fabless 设计", "Foundry 制造", "封装测试",
              "设备", "材料", "OEM/整机", "云厂商", "AI 公司"],
    "semiconductor": ["EDA", "IP", "Fabless", "Foundry", "Packaging",
                      "Equipment", "Materials", "Testing", "OEM", "Cloud", "AI Company"],
    "人工智能": ["算力芯片", "云基础设施", "数据/标注", "基础大模型",
               "开发框架/工具链", "行业模型/Agent", "应用层", "终端硬件"],
    "新能源": ["上游资源(锂/钴/硅料)", "材料(正负极/电解液/隔膜)", "电芯制造",
             "电池包/系统", "整车/储能集成", "充换电/电网", "回收利用"],
    "机器人": ["核心零部件(减速器/伺服/传感器)", "控制器/芯片", "本体制造",
             "系统集成", "行业应用", "运营服务"],
    "生物医药": ["基础研究/靶点发现", "药物设计(CADD/AIDD)", "临床前 CRO",
              "临床试验", "生产 CDMO", "审批注册", "流通商业化"],
}


class ValueChainAgent(BaseAgent):
    name = "value_chain"
    description = "标准化产业链：内置模板 + Mermaid 图 + LLM 细化任务"

    def _match_template(self) -> list[str] | None:
        key = self.ctx.industry.strip()
        for k, v in VALUE_CHAIN_TEMPLATES.items():
            if k in key or key in k or k.lower() == self.ctx.industry_en.lower():
                return v
        return None

    def run(self, **kw) -> list[IIOSRecord]:
        c = self.ctx
        tiers = self._match_template()
        records = []

        if tiers:
            # 离线直接产出 Mermaid + JSON
            mmd = "graph TD\n" + "\n".join(
                f'    T{i}["{t}"] --> T{i+1}["{tiers[i+1]}"]'
                for i, t in enumerate(tiers[:-1])
            )
            (c.industry_dir / "value_chain.mmd").write_text(mmd, encoding="utf-8")
            (c.industry_dir / "value_chain.json").write_text(
                json.dumps({"industry": c.industry, "tiers": tiers},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            records.append(IIOSRecord(
                type="value_chain", title=f"{c.industry} 产业链（模板）",
                summary=" → ".join(tiers), source="template",
                industry=c.industry, confidence=0.85,
                extra={"tiers": tiers, "mermaid_file": "value_chain.mmd"},
            ))

        tier_hint = ("参考已生成的层级模板：" + " → ".join(tiers)) if tiers else \
            "该行业无内置模板，请自行划分 6-12 个标准层级"
        prompt = f"""你是"{c.industry}"产业链研究专家。{tier_hint}。
任务：产出 value_chain.md，包含：
1. 每个层级：定义 / 关键投入产出 / 技术壁垒 / 集中度(CR5) / 毛利水平
2. 层级间的供需关系与卡脖子环节（{c.region} 视角）
3. 更新 value_chain.mmd（Mermaid graph TD，可加分支）
4. 输出 value_chain.json：{{"tiers": [{{"name","barrier","cr5","margin","key_players","references":[{{"title","url"}}]}}]}}
   —— 每个层级的判断都必须给出来源链接。"""
        records.append(self.make_task("产业链细化", prompt, "value_chain.md"))
        return records


# ======================================================================
# 3. Company Agent（24 项指标 + 评分雷达）
# ======================================================================
class CompanyAgent(BaseAgent):
    name = "company"
    description = "各层级 Top10 中国/全球公司 + 24 项指标 + 8 维评分"

    def run(self, companies: list[str] = None, **kw) -> list[IIOSRecord]:
        c = self.ctx
        metrics = json.dumps(COMPANY_METRICS_TEMPLATE, ensure_ascii=False, indent=2)
        dims = " / ".join(SCORE_DIMENSIONS)
        records = []

        prompt_top = f"""你是"{c.industry}"产业投资分析师。
任务：对产业链每个层级（读取 value_chain.json），分别列出 Top 10 中国公司 与 Top 10 全球公司。
每家公司一行：名称 | 国别 | 层级 | 主营 | 市值量级 | 定位。
输出 companies/top_companies.md，并生成 companies/companies.json：
[{{"name","name_en","tier","region","is_china","sources":[{{"title","url"}}],...}}]（供入库 companies 表）。
排名规则：先定义该层级的可比口径，再优先使用该层级营收/出货量/市场份额；无法取得时才使用市值，
且不得把集团总市值当成细分业务规模。中国公司可同时出现在全球榜，必须显式标注。
数量不足 10 家的层级列出实际全部，禁止凑数。每个排名值附 as_of、单位、口径和一手来源。"""
        records.append(self.make_task("Top 公司清单", prompt_top, "companies/top_companies.md"))

        targets = companies or ["（从 top_companies.md 中每层级选市值前 3）"]
        prompt_deep = f"""你是跨境产业与金融分析师。对以下"{c.industry}"公司逐一深度画像：
{chr(10).join('- ' + t for t in targets)}

每家公司必须填满以下 24 项指标（JSON，未知项标 "N/A" 并降低 confidence_score）：
{metrics}

同时给出 8 维评分（0-10 分 + 一句话依据）：{dims}
输出：companies/<公司名>.md（人读）+ companies/<公司名>.json（入库 companies/scores 表）。
市值/财务数据必须标注数据日期与来源链接；市场信心参考近期股价趋势、机构评级、舆情。
进出口数据必须标注 HS 编码/地区/时间区间；无公司级公开数据时写 N/A，不得用行业数据代替。
市场信心必须拆为价格动量、盈利预测修正、估值分位、新闻情绪，不能只给主观总分。
JSON 末尾必须带 "sources": [{{"title","url","published_at","accessed_at"}}]。"""
        records.append(self.make_task("公司深度画像", prompt_deep, "companies/deep_dive.md"))
        return records


# ======================================================================
# 4. Technology Agent
# ======================================================================
class TechnologyAgent(BaseAgent):
    name = "technology"
    description = "技术方向→子方向→知识模块→关键论文/教材→未来发展"

    def run(self, **kw) -> list[IIOSRecord]:
        c = self.ctx
        prompt = f"""你是"{c.industry}"技术地图专家，面向【{c.level_label}】。
任务：产出 technologies/tech_map.md，按层级拆解：
全部技术方向 → 子方向 → 知识模块 → 关键算法/工艺 → 关键论文(附链接) → 经典教材 → 未来发展。
每个技术方向标注成熟度（实验室/原型/商用）与主要玩家。
所有 SOTA 判断必须指定任务、数据集、指标、基线、结果日期，不能把预印本宣传语当共识。
最后 5-8 个最前沿方向做"面向略懂一二学者"的导览：核心思想类比 + 突破点 + 主要团队。
同时输出 technologies/tech_tree.mmd（Mermaid mindmap 或 graph TD 技术树）。"""
        return [self.make_task("技术地图", prompt, "technologies/tech_map.md")]


# ======================================================================
# 5. Learning Agent（学习 DAG）
# ======================================================================
class LearningAgent(BaseAgent):
    name = "learning"
    description = "按 level 生成带依赖关系的学习 DAG + Roadmap"

    def run(self, **kw) -> list[IIOSRecord]:
        c = self.ctx
        prompt = f"""你是"{c.industry}"领域的课程设计专家。为【{c.level_label}】设计学习路线。
核心要求——学习路径必须是 DAG（有向无环图），明确前置依赖，不是平铺清单：
1. learning/roadmap.md：
   - 阶段划分（每阶段：目标 / 知识模块 / 前置依赖 / 推荐资源[书/课/论文/项目] / 预估时长）
   - Checklist（可勾选）
2. learning/learning_dag.mmd：Mermaid graph TD，节点=知识模块，边=依赖关系，
   例：数学基础 --> 电路 --> 数字逻辑 --> 计算机组成 --> ...
3. learning/learning_dag.json：{{"nodes":[{{"id","name","stage","hours"}}],"edges":[["a","b"]]}}
   （供入库与前端渲染）
每个资源标注适用版本/发布日期/免费或付费；链接必须可访问。
expert 级重点放最新论文、工具链与工业趋势；beginner 级从基础学科开始。"""
        return [self.make_task("学习路径 DAG", prompt, "learning/roadmap.md")]


# ======================================================================
# 6. Timeline Agent
# ======================================================================
class TimelineAgent(BaseAgent):
    name = "timeline"
    description = "产业/公司/技术/政策四类时间轴 → events 表 + Mermaid"

    def run(self, headlines: list[str] = None, **kw) -> list[IIOSRecord]:
        c = self.ctx
        hl = ""
        if headlines:
            hl = "\n近一年新闻标题参考：\n" + "\n".join(f"- {h}" for h in headlines[:50])
        prompt = f"""你是"{c.industry}"历史脉络分析师。{hl}
任务：构建四类时间轴，输出 timeline/timeline.md + timeline/timeline.mmd（Mermaid timeline）+
timeline/events.json（[{{"etype","subject","date","title","description","importance","source_url"}}]，
etype ∈ industry|company|technology|policy，importance 1-5，供入库 events 表）：
1. 产业时间轴：从行业起源到今天的关键节点
2. 公司时间轴：头部公司的 成立/IPO/重大并购/重大产品/CEO更替/融资
3. 技术时间轴：范式转移节点（类比 2012 AlexNet → 2017 Transformer → 2022 ChatGPT）
4. 政策时间轴：{c.region} 视角的关键政策/管制事件
每个事件标注驱动因素（技术突破/资本/政策/竞争）。"""
        return [self.make_task("四类时间轴", prompt, "timeline/timeline.md")]


# ======================================================================
# 7. Social Agent
# ======================================================================
class SocialAgent(BaseAgent):
    name = "social"
    description = "追踪 CEO/CTO/创始人/研究负责人的公开发言"

    def run(self, recent_items: list[dict] = None, **kw) -> list[IIOSRecord]:
        c = self.ctx
        ctx_block = ""
        if recent_items:
            ctx_block = "\n今日抓取的相关条目：\n" + "\n".join(
                f"- [{i.get('source','')}] {i.get('title','')}" for i in recent_items[:30])
        prompt = f"""你是"{c.industry}"高管言论情报分析师。{ctx_block}
任务：总结该行业头部公司与明星初创的 CEO/CTO/创始人/研究负责人 近期公开发言
（来源：X、LinkedIn、GitHub、企业 Blog、微信公众号、访谈）。
输出 social/leaders_digest.md：
- Top Posts（原文链接 + 一句话摘要 + 为什么重要）
- Trending Topics / 新产品信号 / 招聘信号 / 研究信号
注意：无法直接抓取的平台，用搜索工具检索近 7 天公开报道替代，并标注来源可信度。"""
        return [self.make_task("高管发言追踪", prompt, "social/leaders_digest.md")]
