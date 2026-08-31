"""Authoritative, redaction-safe catalog for agent and model capabilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    name: str
    kind: str
    region: str
    connection: str
    execution: str
    docs_url: str
    note: str
    commands: tuple[str, ...] = ()
    auth: str = "none"
    web_search: bool = False
    structured_output: bool = False
    key_env: str = ""
    default_model: str = ""
    default_api_base: str = ""
    schedulable: bool = False

    def public(self) -> dict:
        value = asdict(self)
        value["commands"] = list(self.commands)
        return value


CAPABILITY_MANIFEST: tuple[CapabilitySpec, ...] = (
    CapabilitySpec("codex", "Codex CLI", "agent", "international", "cli", "native",
                   "https://developers.openai.com/codex/cli/",
                   "Uses the user's public Codex CLI sign-in state.", ("codex",),
                   "subscription", True, schedulable=True),
    CapabilitySpec("claude", "Claude Code", "agent", "international", "cli", "native",
                   "https://code.claude.com/docs/en/cli-usage",
                   "Uses Claude Code print mode and its public auth status command.",
                   ("claude",), "subscription", True, schedulable=True),
    CapabilitySpec("deepseek_harness", "DeepSeek Harness", "agent", "china",
                   "mcp_or_taskpack", "experimental",
                   "https://deepseek-harness.github.io/deepseek-harness/",
                   "Developer preview; use MCP or a reviewable task package.", ("dsh",)),
    CapabilitySpec("workbuddy", "Work Buddy", "agent", "international",
                   "mcp_or_taskpack", "handoff", "https://docs.work-buddy.ai/",
                   "Connect through IntDog MCP or reviewable task packages.",
                   ("work-buddy", "workbuddy")),
    CapabilitySpec("qwen_code", "Qwen Code", "agent", "china", "mcp_or_taskpack",
                   "handoff", "https://github.com/QwenLM/qwen-code",
                   "MCP/task-package handoff until a stable adapter is configured.",
                   ("qwen", "qwen-code")),
    CapabilitySpec("codebuddy", "CodeBuddy Code", "agent", "china", "mcp_or_taskpack",
                   "handoff", "https://www.codebuddy.ai/", "MCP/task-package handoff.",
                   ("codebuddy", "codebuddy-code")),
    CapabilitySpec("kimi", "Kimi CLI", "agent", "china", "mcp_or_taskpack", "handoff",
                   "https://github.com/MoonshotAI/kimi-cli", "MCP/task-package handoff.",
                   ("kimi", "kimi-cli")),
    CapabilitySpec("gemini", "Gemini CLI", "agent", "international",
                   "mcp_or_taskpack", "handoff", "https://github.com/google-gemini/gemini-cli",
                   "MCP/task-package handoff.", ("gemini",)),
    CapabilitySpec("opencode", "OpenCode", "agent", "international",
                   "mcp_or_taskpack", "handoff", "https://opencode.ai/docs/",
                   "Provider-neutral MCP/task-package handoff.", ("opencode",)),
    CapabilitySpec("openai", "OpenAI API", "api", "international", "api", "native",
                   "https://platform.openai.com/docs/", "Explicit API mode.", auth="api_key",
                   web_search=True, structured_output=True, key_env="OPENAI_API_KEY",
                   default_model="gpt-5", default_api_base="https://api.openai.com/v1",
                   schedulable=True),
    CapabilitySpec("deepseek", "DeepSeek API", "api", "china", "api", "native",
                   "https://api-docs.deepseek.com/", "OpenAI-compatible chat API mode.",
                   auth="api_key", key_env="DEEPSEEK_API_KEY", default_model="deepseek-chat",
                   default_api_base="https://api.deepseek.com", schedulable=True),
    CapabilitySpec("qwen", "Qwen / DashScope API", "api", "china", "api", "native",
                   "https://help.aliyun.com/zh/model-studio/", "Compatible chat API mode.",
                   auth="api_key", key_env="DASHSCOPE_API_KEY", default_model="qwen-plus",
                   default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
                   schedulable=True),
    CapabilitySpec("azure", "Azure OpenAI", "api", "international", "api", "native",
                   "https://learn.microsoft.com/azure/ai-services/openai/", "Explicit endpoint mode.",
                   auth="api_key", key_env="AZURE_OPENAI_API_KEY"),
)


BY_ID = {item.id: item for item in CAPABILITY_MANIFEST}
AGENT_SPECS = tuple(item for item in CAPABILITY_MANIFEST if item.kind == "agent")
API_SPECS = tuple(item for item in CAPABILITY_MANIFEST if item.kind == "api")
DIRECT_PROVIDER_IDS = frozenset(item.id for item in CAPABILITY_MANIFEST
                                if item.execution == "native")
SCHEDULABLE_PROVIDER_IDS = frozenset(item.id for item in CAPABILITY_MANIFEST
                                     if item.schedulable)


def capability(provider: str) -> CapabilitySpec | None:
    return BY_ID.get(str(provider or "").strip().lower())
