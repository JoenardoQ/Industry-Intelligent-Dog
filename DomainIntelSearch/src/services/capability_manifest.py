"""Declarative, redaction-safe catalog for Agent and model capabilities.

The manifest is the single authority for connection and execution tiers. The
legacy ``execution`` field is a read-only compatibility projection for the
existing setup UI; adapters never authorize from it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Connection = Literal["native_cli", "api", "mcp", "taskpack", "restricted_cli"]
ExecutionLevel = Literal["direct", "handoff", "import_only"]


@dataclass(frozen=True)
class AgentCapability:
    id: str
    name: str
    kind: Literal["agent", "api", "bridge"]
    region: str
    connection: Connection
    execution_level: ExecutionLevel
    docs_url: str
    note: str
    commands: tuple[str, ...] = ()
    version_args: tuple[str, ...] = ("--version",)
    version_pattern: str = ""
    auth_args: tuple[str, ...] = ()
    auth: str = "none"
    web_access: bool | None = None
    structured_output: bool = False
    key_env: str = ""
    default_model: str = ""
    default_api_base: str = ""
    schedulable: bool = False

    @property
    def execution(self) -> str:
        """Legacy setup-UI projection; never use this for authorization."""
        return {"direct": "native", "handoff": "handoff",
                "import_only": "import_only"}[self.execution_level]

    @property
    def web_search(self) -> bool:
        return self.web_access is True

    def public(self) -> dict:
        value = asdict(self)
        for key in ("commands", "version_args", "auth_args"):
            value[key] = list(value[key])
        value.pop("version_pattern", None)
        value["execution"] = self.execution
        value["web_search"] = self.web_search
        return value


CapabilitySpec = AgentCapability  # compatibility import


CAPABILITY_MANIFEST: tuple[AgentCapability, ...] = (
    AgentCapability(
        "codex", "Codex CLI", "agent", "international", "native_cli", "direct",
        "https://developers.openai.com/codex/cli/",
        "Uses the user's public Codex CLI sign-in status.", ("codex",),
        version_pattern=r"(?im)^\s*(?:openai\s+)?codex(?:-cli)?\s+v?\d+\.\d+",
        auth_args=("login", "status"), auth="subscription", web_access=True,
        schedulable=True,
    ),
    AgentCapability(
        "claude", "Claude Code", "agent", "international", "native_cli", "direct",
        "https://code.claude.com/docs/en/cli-usage",
        "Uses Claude Code's public version and authentication status commands.",
        ("claude",), version_pattern=r"(?im)^\s*claude(?:\s+code)?\s+v?\d+\.\d+",
        auth_args=("auth", "status"), auth="subscription", web_access=True,
        schedulable=True,
    ),
    AgentCapability(
        "deepseek_harness", "DeepSeek Harness", "agent", "china",
        "restricted_cli", "handoff", "https://deepseek-harness.github.io/deepseek-harness/",
        "Developer preview; use MCP or a reviewable task package.", ("dsh",),
    ),
    AgentCapability(
        "workbuddy", "Work Buddy", "agent", "international", "restricted_cli", "handoff",
        "https://docs.work-buddy.ai/", "Connect through MCP or reviewable task packages.",
        ("work-buddy", "workbuddy"), version_pattern=r"(?i)\bwork\s*buddy\s+v?\d+\.\d+",
    ),
    AgentCapability(
        "qwen_code", "Qwen Code", "agent", "china", "restricted_cli", "handoff",
        "https://github.com/QwenLM/qwen-code",
        "MCP/task-package handoff until a stable direct adapter is verified.",
        ("qwen", "qwen-code"),
    ),
    AgentCapability(
        "codebuddy", "CodeBuddy Code", "agent", "china", "restricted_cli", "handoff",
        "https://www.codebuddy.ai/", "MCP/task-package handoff.",
        ("codebuddy", "codebuddy-code"),
    ),
    AgentCapability(
        "kimi", "Kimi CLI", "agent", "china", "restricted_cli", "handoff",
        "https://github.com/MoonshotAI/kimi-cli", "MCP/task-package handoff.",
        ("kimi", "kimi-cli"),
    ),
    AgentCapability(
        "gemini", "Gemini CLI", "agent", "international", "restricted_cli", "handoff",
        "https://github.com/google-gemini/gemini-cli", "MCP/task-package handoff.",
        ("gemini",),
    ),
    AgentCapability(
        "opencode", "OpenCode", "agent", "international", "restricted_cli", "handoff",
        "https://opencode.ai/docs/", "Provider-neutral MCP/task-package handoff.",
        ("opencode",),
    ),
    AgentCapability(
        "openai", "OpenAI API", "api", "international", "api", "direct",
        "https://platform.openai.com/docs/", "Explicit OpenAI Responses API mode.",
        auth="bearer", web_access=True, structured_output=True,
        key_env="OPENAI_API_KEY", default_model="gpt-5",
        default_api_base="https://api.openai.com/v1", schedulable=True,
    ),
    AgentCapability(
        "anthropic", "Anthropic API", "api", "international", "api", "import_only",
        "https://docs.anthropic.com/", "Catalogued for task/result exchange; no direct adapter yet.",
        auth="api_key_header", key_env="ANTHROPIC_API_KEY",
    ),
    AgentCapability(
        "deepseek", "DeepSeek API", "api", "china", "api", "direct",
        "https://api-docs.deepseek.com/", "OpenAI-compatible chat API mode.",
        auth="bearer", key_env="DEEPSEEK_API_KEY", default_model="deepseek-chat",
        default_api_base="https://api.deepseek.com", schedulable=True,
    ),
    AgentCapability(
        "qwen", "Qwen / DashScope API", "api", "china", "api", "direct",
        "https://help.aliyun.com/zh/model-studio/", "OpenAI-compatible chat API mode.",
        auth="bearer", key_env="DASHSCOPE_API_KEY", default_model="qwen-plus",
        default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        schedulable=True,
    ),
    AgentCapability(
        "azure", "Azure OpenAI", "api", "international", "api", "direct",
        "https://learn.microsoft.com/azure/ai-services/openai/",
        "Explicit Azure deployment endpoint mode.", auth="api_key_header",
        key_env="AZURE_OPENAI_API_KEY", schedulable=True,
    ),
    AgentCapability(
        "compatible_api", "Generic Compatible API", "api", "international", "api", "direct",
        "", "Requires an explicit HTTPS base URL, auth type, model, and secret.",
        auth="explicit", key_env="INTDOG_LLM_API_KEY", schedulable=True,
    ),
    AgentCapability(
        "mcp", "Model Context Protocol", "bridge", "international", "mcp", "handoff",
        "https://modelcontextprotocol.io/", "Read-only tools plus review-gated result import.",
        structured_output=True,
    ),
    AgentCapability(
        "taskpack", "Reviewable Task Package", "bridge", "international", "taskpack",
        "import_only", "", "Portable export/import path for any Agent.",
        structured_output=True,
    ),
)


BY_ID = {item.id: item for item in CAPABILITY_MANIFEST}
AGENT_SPECS = tuple(item for item in CAPABILITY_MANIFEST if item.kind == "agent")
API_SPECS = tuple(item for item in CAPABILITY_MANIFEST if item.kind == "api")
DIRECT_PROVIDER_IDS = frozenset(
    item.id for item in CAPABILITY_MANIFEST if item.execution_level == "direct")
SCHEDULABLE_PROVIDER_IDS = frozenset(
    item.id for item in CAPABILITY_MANIFEST if item.schedulable)


def capability(provider: str) -> AgentCapability | None:
    return BY_ID.get(str(provider or "").strip().lower())


def capability_or_unknown(provider: str) -> AgentCapability:
    normalized = str(provider or "unknown").strip().lower() or "unknown"
    known = capability(normalized)
    if known is not None:
        return known
    return AgentCapability(
        normalized, normalized, "agent", "unknown", "restricted_cli", "import_only",
        "", "Unknown Agents are limited to review-gated result import.",
    )
