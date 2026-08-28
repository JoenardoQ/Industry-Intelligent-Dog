"""LLM 分析提示词模板：领域拆解、产业链、公司、知识模块、前沿技术.

这些模板用于生成"模型无关任务包"（agent 中立）：可交给 Codex / WorkBuddy /
Claude Code / 自写脚本执行；当 llm.provider 为 openai/deepseek/qwen 时，
也可直接转换为 API messages 由 Search 自带联网 LLM 直连执行。
"""


class PromptTemplates:
    """领域分析提示词集合."""

    def __init__(self, config: dict):
        self.domain = config.get("domain", {})
        self.name = self.domain.get("name", "该领域")
        self.name_en = self.domain.get("name_en", self.name)
        self.depth = self.domain.get("depth", "beginner")
        depth_label = {
            "beginner": "新手（零基础，需要基础概念铺垫）",
            "intermediate": "熟手（有基础，需要进阶和实操）",
            "expert": "专家（需要前沿深度和细节）",
        }.get(self.depth, "新手")
        self.depth_label = depth_label

    # ---------------- 1. 子领域 ----------------
    def list_subdomains(self) -> str:
        return f"""你是一名"{self.name}"领域的资深研究分析师。
请面向【{self.depth_label}】，完成以下任务：

**任务 1：列出该领域的不同子领域**
请以结构化方式列出"{self.name}"（{self.name_en}）的主要子领域，建议 8-15 个。
对每个子领域给出：
- 名称
- 一句话定义
- 核心研究方向 / 典型应用
- 与上下游的关联

输出格式：Markdown 列表，每个子领域一个小节。"""

    # ---------------- 2. 产业上下游 ----------------
    def industry_chain(self) -> str:
        return f"""你是一名"{self.name}"产业链研究专家。
请详细解释"{self.name}"的产业上下游：

**任务 2：产业链上下游分析**
1. 上游（原材料、基础设施、核心技术/算法、硬件）
2. 中游（制造、集成、平台、服务）
3. 下游（应用场景、终端用户、渠道）
对每个环节：说明其关键投入、产出、主要参与者类型、技术壁垒。
并绘制（文字版）产业链全景图。

输出格式：Markdown，分上/中/下游三节 + 全景概述。"""

    # ---------------- 3. 产业链各层级 Top 中外国公司 ----------------
    def top_companies(self) -> str:
        return f"""你是一名"{self.name}"产业投资分析师。
请列出产业链**每一个层级**中的 Top 10 公司，区分**中国**与**外国（欧美日韩等）**：

**任务 3：各层级 Top 10 公司**
- 对每个产业链层级（上游/中游/下游，可结合任务2的层级）
- 分别列出中国 Top 10 与外国 Top 10 公司
- 每家公司给出：名称、国别、主营业务、在该层级的定位

输出格式：按层级分节，每节内含"中国"和"外国"两个子表。
注意：如果某一层级公司数量不足10家，列出实际全部即可。"""

    # ---------------- 4. 公司深度分析 ----------------
    def company_deep_dive(self, companies: list[str]) -> str:
        comp_str = "\n".join(f"- {c}" for c in companies)
        return f"""你是一名跨境产业与金融分析师。
针对以下"{self.name}"领域公司，逐一详细分析：

{comp_str}

**任务 4：公司深度画像**（每家公司独立小节）
- 核心优势（技术/渠道/牌照/生态）
- 核心劣势（短板/风险）
- 进口依赖 or 出口能力（关键技术/材料是否受制于人）
- 市值规模（给出量级，如千亿级）
- 市场信心指标（近期股价趋势、机构评级、舆情基调）

输出格式：每家公司一个 Markdown 小节，含上述5个要点。"""

    # ---------------- 5. 知识模块与学习路径 ----------------
    def knowledge_modules(self) -> str:
        return f"""你是一名"{self.name}"领域的教育专家。
请为【{self.depth_label}】设计该领域的知识地图：

**任务 5：子领域知识模块拆解**
对每个主要子领域：
- 所属大类（基础层/技术层/应用层/商业层）
- 核心知识模块（概念、工具、方法）
- 推荐学习路径（从入门到进阶，含资源类型：书籍/课程/论文/项目）
- 关键前置知识

输出格式：按子领域分节，每节含"类别 / 知识模块 / 学习路径 / 前置知识"。"""

    # ---------------- 7. 前沿技术（面向略懂一二的学者） ----------------
    def cutting_edge(self) -> str:
        return f"""你是一名善于科普的"{self.name}"研究科学家。
请总结该领域**最先进的技术方向**，面向"略懂一二的学者"（有专业基础但想快速理解前沿）：

**任务 7：前沿技术导览**
列出 5-8 个最前沿的技术方向，每个包含：
- 名称
- 一句话核心思想（用类比让外行也能懂）
- 为什么重要（突破点）
- 主要玩家（学术团队/公司）
- 当前成熟度（实验室/原型/商用）

输出格式：Markdown 列表，每个方向一个小节。也可结合近期论文/新闻中的新进展。"""

    # ---------------- 年度轨迹分析 ----------------
    def yearly_timeline(self, headlines: list[str]) -> str:
        hls = "\n".join(f"- {h}" for h in headlines[:50])
        return f"""你是"{self.name}"领域的历史脉络分析师。
以下是近一年该领域的重要新闻标题（按时间倒序）：

{hls}

请据此整理出**近一年的发展轨迹**：
1. 以季度（或关键节点）为轴，梳理重大事件脉络
2. 标注每条轨迹的"驱动因素"（技术突破/资本/政策/竞争）
3. 总结年度主线和转折点

输出格式：Markdown 时间线 + 主线总结。"""

    # ---------------- 通用：把抓取内容转成摘要指令 ----------------
    def summarize_for_digest(self, items: list[dict], kind: str) -> str:
        bulk = "\n".join(
            f"- [{i.get('source','')}] {i.get('title','')}：{i.get('summary','')[:150]}"
            for i in items[:25]
        )
        kind_label = {
            "news": "行业新闻", "academic": "学术动态",
            "finance": "金融资讯", "policy": "政策要闻",
        }.get(kind, "内容")
        return f"""你是"{self.name}"领域的情报编辑。
以下是今日抓取的{kind_label}（已按相关性筛选）：

{bulk}

请生成一则面向【{self.depth_label}】的{kind_label}简报：
1. 用 3-5 条要点概括最重要的进展
2. 标注每条的意义（为什么值得关注）
3. 语言简洁，中文输出，不超过 300 字。"""
