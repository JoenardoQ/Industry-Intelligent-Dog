"""模块层：每个步骤（采集/报告/推送/研究/建图）都是可插拔模块.

- base     ModuleSpec / ModuleResult / ModuleContext / 注册表
- catalog  全部内置模块（现有组件的薄包装）
- runner   依赖解析 + 顺序执行 + 行业档案合并
"""

from .base import (BaseModule, ModuleContext, ModuleResult, ModuleSpec,
                   MODULE_REGISTRY, get_module, list_modules, register)
from . import catalog  # noqa: F401  （导入即注册全部内置模块）
from .runner import PipelineRunner, resolve_selection

__all__ = [
    "BaseModule", "ModuleContext", "ModuleResult", "ModuleSpec",
    "MODULE_REGISTRY", "get_module", "list_modules", "register",
    "PipelineRunner", "resolve_selection",
]
