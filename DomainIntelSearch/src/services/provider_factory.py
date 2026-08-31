"""Single construction boundary for model providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .capability_manifest import BY_ID


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


CAPABILITIES = {item.id: ProviderCapabilities(
    item.id, web_search=item.web_search, subscription_auth=item.auth == "subscription",
    structured_output=item.structured_output)
    for item in BY_ID.values() if item.execution == "native"}


def create_provider(config: dict, provider: str, workspace: str | Path) -> Provider:
    name = str(provider or "").strip().lower()
    if name not in CAPABILITIES:
        raise ValueError(f"不支持的 provider：{name or '空'}")
    if name == "codex":
        from .codex_cli_service import CodexCLIService
        return CodexCLIService(config, workspace)
    if name == "claude":
        from .claude_cli_service import ClaudeCLIService
        return ClaudeCLIService(config, workspace)
    from .llm_service import LLMService
    return LLMService(config, provider=name)
