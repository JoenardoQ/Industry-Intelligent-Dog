"""Agent 基类与运行上下文.

设计原则（IIOS_SPEC.md §4）：
1. 研究组 Agent 不直接调用 LLM API，而是产出「任务包」——
   结构化 Prompt + 数据上下文 + 期望输出路径，交由 WorkBuddy/Codex/任意 LLM 执行。
   这样系统离线也能跑，且 LLM 可替换。
2. Agent 之间只通过 IIOSRecord / 归档目录交换数据，禁止互相依赖内部实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..schema import IIOSRecord


@dataclass
class AgentContext:
    """统一输入（IIOS_SPEC.md §2）."""

    industry: str = "人工智能"
    industry_en: str = ""
    level: str = "beginner"        # beginner | intermediate | expert
    region: str = "global"         # global | china | us | europe
    lang: str = "zh"               # zh | en | both
    config: dict = field(default_factory=dict)
    data_root: Path = None         # canonical DomainIntelData root
    data_folder: str = ""          # e.g. Chips / AI

    @classmethod
    def from_config(cls, config: dict, **overrides) -> "AgentContext":
        domain = config.get("domain", {})
        iios = config.get("iios", {})
        from ..profiles import profile_folder
        from ..utils import data_root
        profile = config.get("_profile", {}) or {}
        ctx = cls(
            industry=domain.get("name", "人工智能"),
            industry_en=domain.get("name_en", ""),
            level=domain.get("depth", "beginner"),
            region=iios.get("region", "global"),
            lang=config.get("output", {}).get("language", "zh"),
            config=config,
            data_root=data_root(config),
            data_folder=profile_folder(profile) if profile else "",
        )
        for k, v in overrides.items():
            if v:
                setattr(ctx, k, v)
        return ctx

    @property
    def level_label(self) -> str:
        return {
            "beginner": "新手（零基础，需要基础概念铺垫）",
            "intermediate": "熟手（有基础，需要进阶和实操）",
            "expert": "专家（需要前沿深度和细节）",
        }.get(self.level, "新手")

    @property
    def industry_root(self) -> Path:
        """Canonical root shared by collectors, research agents, UI and MCP."""
        safe = "".join(c for c in self.industry if c not in r'\/:*?"<>|').strip() or "default"
        folder = self.data_folder or safe
        d = self.data_root / folder
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def industry_dir(self) -> Path:
        """Research workspace under the canonical industry root."""
        d = self.industry_root / "one_time" / "research"
        d.mkdir(parents=True, exist_ok=True)
        return d


class BaseAgent:
    """所有 Agent 的基类."""

    name = "base"
    agent_type = "llm_task"        # llm_task | crawler | code
    description = ""

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx

    # 子类实现：返回 IIOSRecord 列表
    def run(self, **kwargs) -> list[IIOSRecord]:
        raise NotImplementedError

    # ------------------------------------------------------------------
    def make_task(self, task_name: str, prompt: str,
                  output_file: str, tags: list = None) -> IIOSRecord:
        """产出一个 LLM 任务包记录。output_file 为相对 industry_dir 的路径."""
        return IIOSRecord(
            type="task",
            title=f"[{self.name}] {task_name}",
            summary=prompt,
            source=f"agent:{self.name}",
            industry=self.ctx.industry,
            region=self.ctx.region,
            tags=(tags or []) + [self.name, self.ctx.level],
            extra={
                "agent": self.name,
                "output_file": str(self.ctx.industry_dir / output_file),
                "artifact_status": "pending_execution",
                "quality_gates": ["schema_valid", "citations_resolve",
                                  "fact_opinion_separated", "human_review"],
                "instruction": (
                    "执行 summary 中的分析任务，将 Markdown 结果写入 output_file。"
                    "引用规范（必须遵守）：每个关键结论后用 [n] 标注来源，"
                    "文末附编号 references 列表（title + url），引用来源不少于 3 个；"
                    "JSON 输出中的每个对象必须带 source_url 或 references 字段；"
                    "每个数值必须带 as_of/currency/unit/definition；"
                    "整体结论标注 confidence(0-1)，未经复核的成品状态必须是 draft。"
                ),
            },
        )

    def save_tasks(self, records: list[IIOSRecord], bundle_name: str) -> Path:
        """把任务包写入当前行业 one_time/research/tasks/."""
        import json
        out_dir = self.ctx.industry_dir / "tasks"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{bundle_name}.json"
        path.write_text(
            json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path
