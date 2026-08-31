"""Single construction boundary for model providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class CompletionResult(Protocol):
    text: str
    provider: str
    model: str
    response_id: str
    usage: dict | None


class Provider(Protocol):
    def complete(self, prompt: str) -> CompletionResult: ...


@dataclass(frozen=True)
class ProviderCapabilities:
    name: str
    web_search: bool
    subscription_auth: bool
    structured_output: bool = False


CAPABILITIES = {
    "codex": ProviderCapabilities("codex", web_search=True, subscription_auth=True),
    "openai": ProviderCapabilities("openai", web_search=True, subscription_auth=False),
    "deepseek": ProviderCapabilities("deepseek", web_search=False, subscription_auth=False),
    "qwen": ProviderCapabilities("qwen", web_search=False, subscription_auth=False),
    "azure": ProviderCapabilities("azure", web_search=False, subscription_auth=False),
}


def create_provider(config: dict, provider: str, workspace: str | Path) -> Provider:
    name = str(provider or "").strip().lower()
    if name not in CAPABILITIES:
        raise ValueError(f"不支持的 provider：{name or '空'}")
    if name == "codex":
        from .codex_cli_service import CodexCLIService
        return CodexCLIService(config, workspace)
    from .llm_service import LLMService
    return LLMService(config, provider=name)
