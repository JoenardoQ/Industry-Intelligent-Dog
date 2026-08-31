from pathlib import Path
from unittest.mock import patch
import subprocess

from src.services.agent_registry import discover_agents
from src.services.claude_cli_service import ClaudeCLIService
from src.services.provider_readiness import provider_readiness
from src.services.llm_service import LLMConfigurationError, LLMService
from src.services.capability_manifest import AGENT_SPECS, API_SPECS, DIRECT_PROVIDER_IDS
from src.services.provider_factory import CAPABILITIES


def test_registry_distinguishes_native_execution_from_handoff():
    def found(command):
        return f"/tools/{command}" if command in {"codex", "claude", "dsh", "gemini"} else None
    with patch("src.services.agent_registry.shutil.which", side_effect=found), \
         patch("src.services.agent_registry._run_status", return_value=subprocess.CompletedProcess([], 0, "signed in", "")):
        rows = {row["id"]: row for row in discover_agents()}
    assert rows["codex"]["ready"] and rows["codex"]["execution"] == "native"
    assert rows["claude"]["ready"] and rows["claude"]["execution"] == "native"
    assert rows["deepseek_harness"]["ready"] and rows["deepseek_harness"]["execution"] == "experimental"
    assert rows["gemini"]["ready"] and rows["gemini"]["execution"] == "handoff"
    assert not rows["workbuddy"]["installed"]


def test_registry_never_claims_a_missing_cli_is_connected():
    with patch("src.services.agent_registry.shutil.which", return_value=None):
        rows = discover_agents()
    assert rows
    assert all(not row["installed"] and not row["ready"] for row in rows)


def test_claude_print_adapter_is_bounded_and_noninteractive():
    service = ClaudeCLIService.__new__(ClaudeCLIService)
    service.executable = "/usr/bin/claude"
    service.workspace = Path("/tmp/intdog")
    service.timeout = 30
    service.model = "sonnet"
    completed = subprocess.CompletedProcess([], 0, "research result", "")
    with patch("src.services.claude_cli_service.subprocess.run", return_value=completed) as run:
        result = service.complete("prompt")
    command = run.call_args.args[0]
    assert command[:3] == ["/usr/bin/claude", "-p", "--permission-mode"]
    assert command[3] == "plan"
    assert run.call_args.kwargs["cwd"] == Path("/tmp/intdog")
    assert result.text == "research result"


def test_api_readiness_is_secret_presence_only_and_redaction_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "secret-value")
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "deepseek")
    result = provider_readiness("deepseek", tmp_path)
    assert result["ready"] is True
    assert "secret-value" not in str(result)


def test_generic_desktop_key_is_scoped_to_its_selected_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "secret-value")
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "deepseek")
    assert provider_readiness("deepseek", tmp_path)["ready"] is True
    assert provider_readiness("openai", tmp_path)["ready"] is False
    with patch.dict("os.environ", {
            "INTDOG_LLM_API_KEY": "secret-value",
            "INTDOG_LLM_PROVIDER": "deepseek",
            "INTDOG_LLM_MODEL": "deepseek-chat",
            "INTDOG_LLM_API_BASE": "https://api.deepseek.com"}, clear=True):
        try:
            LLMService({"llm": {}}, provider="openai")
        except LLMConfigurationError:
            pass
        else:
            raise AssertionError("OpenAI must not consume DeepSeek desktop credentials")


def test_handoff_agent_is_not_misrepresented_as_direct_provider(tmp_path):
    result = provider_readiness("workbuddy", tmp_path)
    assert result["ready"] is False
    assert "MCP" in result["detail"]


def test_capability_manifest_is_the_provider_factory_source_of_truth():
    manifest_direct = {item.id for item in (*AGENT_SPECS, *API_SPECS)
                       if item.execution == "native"}
    assert manifest_direct == DIRECT_PROVIDER_IDS == set(CAPABILITIES)
    assert {item.id for item in AGENT_SPECS} >= {
        "codex", "claude", "deepseek_harness", "workbuddy", "qwen_code",
        "codebuddy", "kimi", "gemini", "opencode"}
