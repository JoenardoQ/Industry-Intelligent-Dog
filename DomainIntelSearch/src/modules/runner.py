"""流水线运行器：按用户选择的模块组合一次运行.

职责：
1. 依赖解析：requires 硬依赖自动补全；按 分类阶段 + after 软顺序排序。
2. 互斥处理：research_plan 与单个 research_* 同选时，plan 只调度被选中的 Agent，
   单个模块不再重复执行。
3. 行业档案：apply_profile 合并行业配置后构造 Orchestrator / AgentContext。
"""

from __future__ import annotations

import traceback
from datetime import datetime

from .base import MODULE_REGISTRY, ModuleContext, ModuleResult, get_module, list_modules
from ..profiles import apply_profile

PHASE_ORDER = {"collect": 10, "report": 20, "deliver": 30, "research": 40, "graph": 50}

RESEARCH_AGENT_MODULES = {
    "research_industry": "industry",
    "research_value_chain": "value_chain",
    "research_company": "company",
    "research_technology": "technology",
    "research_learning": "learning",
    "research_timeline": "timeline",
    "research_social": "social",
}


def resolve_selection(module_ids: list[str]) -> list[str]:
    """把用户选择展开为有序执行列表（补全 requires，按阶段排序）."""
    selected: dict[str, None] = {}

    def add(mid: str):
        if mid in selected:
            return
        spec = get_module(mid).spec
        for dep in spec.requires:
            if dep in MODULE_REGISTRY:
                add(dep)
        selected[mid] = None

    for mid in module_ids:
        if mid in MODULE_REGISTRY:
            add(mid)

    # research_plan 选中时：它接管被勾选的单个研究 Agent（避免重复执行）
    if "research_plan" in selected:
        for mid in list(RESEARCH_AGENT_MODULES):
            selected.pop(mid, None)

    specs = [MODULE_REGISTRY[mid].spec for mid in selected]
    decl_pos = {s.id: i for i, s in enumerate(list_modules())}

    def sort_key(s):
        after_penalty = sum(1 for a in s.after if a in selected)
        return (PHASE_ORDER.get(s.category, 99), after_penalty, decl_pos.get(s.id, 999))

    specs.sort(key=sort_key)
    return [s.id for s in specs]


class PipelineRunner:
    """执行一组模块并汇报结果."""

    def __init__(self, base_config: dict, profile: dict = None,
                 params: dict = None, log=None):
        self.config = apply_profile(base_config, profile)
        self.profile = profile or {}
        self.params = params or {}
        self.log = log or (lambda msg: None)
        from ..orchestrator import Orchestrator
        self.orch = Orchestrator(config=self.config)

    def _make_agent_ctx(self, module_ids: list[str]):
        needs_agent = any(mid.startswith("research_") or mid == "kg_build"
                          for mid in module_ids)
        if not needs_agent:
            return None
        from ..agents.base import AgentContext
        return AgentContext.from_config(
            self.config,
            level=self.params.get("level", ""),
            region=self.params.get("region", ""),
            lang=self.params.get("lang", ""),
        )

    def run(self, module_ids: list[str]) -> dict:
        ordered = resolve_selection(module_ids)
        started = datetime.now()
        self.log(f"行业：{self.config.get('domain', {}).get('name')} | "
                 f"执行 {len(ordered)} 个模块：{' → '.join(ordered)}")

        # research_plan 与单个研究模块同选时，plan 只调度被选 Agent
        params = dict(self.params)
        if "research_plan" in ordered:
            chosen = [a for mid, a in RESEARCH_AGENT_MODULES.items()
                      if mid in module_ids]
            if chosen:
                params["agents_filter"] = chosen

        ctx = ModuleContext(self.config, self.orch, self.profile, params,
                            log=self.log, agent_ctx=self._make_agent_ctx(ordered))

        results, ok_count, fail_count = {}, 0, 0
        for mid in ordered:
            cls = get_module(mid)
            self.log(f"── 运行模块 [{mid}] {cls.spec.name}")
            try:
                res = cls().run(ctx)
            except Exception as e:  # 模块失败不中断整条流水线
                traceback.print_exc()
                res = ModuleResult(ok=False, message=f"异常：{e}")
            results[mid] = res.to_dict()
            if res.ok:
                ok_count += 1
            else:
                fail_count += 1
            self.log(f"   [{mid}] {'✔' if res.ok else '✘'} {res.message}")

        elapsed = (datetime.now() - started).total_seconds()
        summary = (f"完成：{ok_count} 成功 / {fail_count} 失败，耗时 {elapsed:.1f}s")
        self.log(summary)
        return {
            "industry": self.config.get("domain", {}).get("name"),
            "profile_id": self.profile.get("id", ""),
            "modules_ordered": ordered,
            "results": results,
            "ok": ok_count, "failed": fail_count,
            "elapsed_sec": round(elapsed, 1),
            "summary": summary,
        }
