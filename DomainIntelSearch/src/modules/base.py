"""模块框架：把系统的每一个步骤（采集/报告/推送/研究/建图）抽象为可插拔模块.

设计原则：
1. 每个模块只做一件事，通过 ModuleSpec 自描述（id/名称/分类/依赖/参数），
   界面与 CLI 直接读取规格渲染功能清单。
2. 模块间不互相 import，只通过共享 RunState（dict）交换数据；
   requires 声明硬依赖（自动补全），after 声明软顺序。
3. 模块是现有爬虫/生成器/Agent 的薄包装，不改变原有内部实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


# ======================================================================
# 规格与结果
# ======================================================================
@dataclass
class ModuleSpec:
    """模块自描述（界面据此渲染勾选项）."""

    id: str
    name: str
    category: str            # collect | report | deliver | research | graph
    description: str = ""
    kind: str = "code"       # code（确定性代码） | llm_task（产出 LLM 任务包）
    requires: list = field(default_factory=list)   # 硬依赖：自动补全
    after: list = field(default_factory=list)      # 软顺序提示
    network: bool = False    # 是否需要联网
    params: list = field(default_factory=list)     # [{key,label,type,default}]
    default_selected: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "description": self.description, "kind": self.kind,
            "requires": self.requires, "after": self.after,
            "network": self.network, "params": self.params,
            "default_selected": self.default_selected,
        }


@dataclass
class ModuleResult:
    """模块执行结果."""

    ok: bool = True
    message: str = ""
    data: dict = field(default_factory=dict)          # 计数等结构化信息
    artifacts: list = field(default_factory=list)     # [{label, path}] 产出文件
    references: list = field(default_factory=list)    # [{title,url,source,published}]

    def to_dict(self) -> dict:
        return {"ok": self.ok, "message": self.message, "data": self.data,
                "artifacts": self.artifacts, "references": self.references}


class ModuleContext:
    """一次运行的共享上下文：配置 + 编排器 + 行业档案 + 共享状态 + 日志."""

    def __init__(self, config: dict, orchestrator, profile: dict = None,
                 params: dict = None, log: Callable[[str], None] = None,
                 agent_ctx=None):
        self.config = config
        self.orch = orchestrator
        self.profile = profile or {}
        self.params = params or {}
        self.state: dict = {}          # RunState：模块间交换数据的唯一通道
        self.agent_ctx = agent_ctx     # AgentContext（研究/图谱模块用）
        self._log = log or (lambda msg: None)

    def log(self, msg: str):
        self._log(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    @property
    def industry(self) -> str:
        return self.config.get("domain", {}).get("name", "")

    def param(self, key: str, default=None):
        return self.params.get(key, default)


class BaseModule:
    """模块基类：子类设置 spec 并实现 run()."""

    spec = ModuleSpec(id="base", name="基类", category="collect")

    def run(self, ctx: ModuleContext) -> ModuleResult:
        raise NotImplementedError


# ======================================================================
# 注册表
# ======================================================================
MODULE_REGISTRY: dict[str, type[BaseModule]] = {}


def register(cls: type[BaseModule]) -> type[BaseModule]:
    MODULE_REGISTRY[cls.spec.id] = cls
    return cls


def get_module(module_id: str) -> type[BaseModule] | None:
    return MODULE_REGISTRY.get(module_id)


def list_modules() -> list[ModuleSpec]:
    """按 分类→声明顺序 返回全部模块规格."""
    order = {"collect": 0, "report": 1, "deliver": 2, "research": 3, "graph": 4}
    specs = [cls.spec for cls in MODULE_REGISTRY.values()]
    specs.sort(key=lambda s: (order.get(s.category, 9), list(MODULE_REGISTRY).index(s.id)))
    return specs
