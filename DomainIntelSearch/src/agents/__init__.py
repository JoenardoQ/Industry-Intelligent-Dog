"""IIOS 多 Agent 层（IIOS_SPEC.md §5）.

- 研究组（LLM 任务包）: Industry / ValueChain / Company / Technology / Learning / Timeline / Social
- 情报组（爬虫，位于 src/crawlers/）: News / Paper / Policy / Finance / Startup
- 综合组: Planner（调度） / KnowledgeGraph（图谱） / Reporter（src/generators/）
"""

from .base import BaseAgent, AgentContext
from .planner import PlannerAgent
from .research import (
    IndustryAgent, ValueChainAgent, CompanyAgent, TechnologyAgent,
    LearningAgent, TimelineAgent, SocialAgent,
)
from .kg import KnowledgeGraphAgent

AGENT_REGISTRY = {
    "planner": PlannerAgent,
    "industry": IndustryAgent,
    "value_chain": ValueChainAgent,
    "company": CompanyAgent,
    "technology": TechnologyAgent,
    "learning": LearningAgent,
    "timeline": TimelineAgent,
    "social": SocialAgent,
    "kg": KnowledgeGraphAgent,
}

__all__ = ["BaseAgent", "AgentContext", "AGENT_REGISTRY"] + [
    c.__name__ for c in AGENT_REGISTRY.values()
]
