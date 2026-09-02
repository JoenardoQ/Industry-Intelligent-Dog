from pathlib import Path
from unittest.mock import patch
import subprocess

import pytest

from src.services.agent_registry import discover_agents
from src.services.claude_cli_service import ClaudeCLIService
from src.services.provider_readiness import provider_readiness
from src.services.llm_service import (
    LLMConfigurationError,
    LLMService,
    ProviderRequestError,
    validate_model_id,
)
from src.services import capability_manifest
from src.services.capability_manifest import AGENT_SPECS, API_SPECS, DIRECT_PROVIDER_IDS
from src.services.provider_factory import CAPABILITIES, create_provider


def test_registry_distinguishes_native_execution_from_handoff():
    def found(command):
        return f"/tools/{command}" if command in {"codex", "claude", "dsh", "gemini"} else None
    def diagnosed(profile, **_kwargs):
        return {
            "id": profile["id"], "connection": "native_cli",
            "execution_level": "direct", "installed": True,
            "authenticated": True, "version_verified": True, "ready": True,
            "executable": profile["executable"], "status": "ready",
            "failure_code": None, "version": "1.2.3", "detail": "ready",
        }
    with patch("src.services.agent_registry.shutil.which", side_effect=found), \
         patch("src.services.agent_registry.diagnose_agent", side_effect=diagnosed):
        rows = {row["id"]: row for row in discover_agents()}
    assert rows["codex"]["ready"] and rows["codex"]["execution"] == "native"
    assert rows["claude"]["ready"] and rows["claude"]["execution"] == "native"
    assert rows["deepseek_harness"]["ready"] and rows["deepseek_harness"]["execution"] == "handoff"
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


def test_provider_factory_passes_diagnosed_executable_binding_without_rewhich(tmp_path):
    binding = {
        "provider": "claude", "ready": True, "resolved_executable": "/tools/claude",
        "executable_fingerprint": {"source_path": "/tools/claude",
            "canonical_path": "/tools/claude", "device": 1, "inode": 2,
            "size": 3, "mtime_ns": 4, "sha256": "a" * 64},
    }
    with patch("src.services.provider_readiness.provider_readiness",
               return_value=binding) as readiness, \
         patch("src.services.claude_cli_service.ClaudeCLIService") as service:
        create_provider({}, "claude", tmp_path)
    readiness.assert_called_once_with("claude", tmp_path)
    service.assert_called_once_with({}, tmp_path, executable_binding=binding)


def test_api_readiness_is_secret_presence_only_and_redaction_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "test-only-value")
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "deepseek")
    result = provider_readiness("deepseek", tmp_path)
    assert result["ready"] is True
    assert "secret-value" not in str(result)


@pytest.mark.parametrize(("provider", "invalid_auth"), [
    ("openai", "api_key_header"), ("deepseek", "api_key_header"),
    ("qwen", "api_key_header"), ("azure", "bearer"),
])
def test_fixed_provider_rejects_auth_type_outside_manifest(
        monkeypatch, tmp_path, provider, invalid_auth):
    spec = capability_manifest.capability(provider)
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", provider)
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "secret-value")
    monkeypatch.setenv(spec.key_env, "secret-value")
    monkeypatch.setenv("INTDOG_LLM_MODEL", spec.default_model or "deployment")
    monkeypatch.setenv("INTDOG_LLM_API_BASE", spec.default_api_base or
                       "https://azure.example/openai/deployments/test/chat/completions")
    monkeypatch.setenv("INTDOG_LLM_AUTH_TYPE", invalid_auth)
    readiness = provider_readiness(provider, tmp_path)
    assert readiness["ready"] is False
    assert readiness["failure_code"] == "invalid_auth_type"
    with pytest.raises(LLMConfigurationError, match="认证方式"):
        LLMService({"llm": {}}, provider=provider)


def test_generic_desktop_key_is_scoped_to_its_selected_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "secret-value")
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "deepseek")
    assert provider_readiness("deepseek", tmp_path)["ready"] is True
    assert provider_readiness("openai", tmp_path)["ready"] is False
    with patch.dict("os.environ", {
            "INTDOG_LLM_API_KEY": "test-only-value",
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
                       if item.execution_level == "direct"}
    assert manifest_direct == DIRECT_PROVIDER_IDS == set(CAPABILITIES)
    assert {item.id for item in AGENT_SPECS} >= {
        "codex", "claude", "deepseek_harness", "workbuddy", "qwen_code",
        "codebuddy", "kimi", "gemini", "opencode"}


def test_agent_manifest_declares_native_session_protocols_and_honest_fallbacks():
    expected = {
        "codex": ("codex_app_server", "stable", "full", True),
        "claude": ("claude_agent_sdk", "stable", "full", False),
        "deepseek_harness": ("deepseek_jsonrpc", "preview", "basic", False),
        "workbuddy": ("workbuddy_mcp", "stable", "handoff", False),
        "qwen_code": ("acp", "experimental", "basic", True),
        "codebuddy": ("acp", "beta", "basic", True),
        "kimi": ("acp", "experimental", "basic", True),
        "gemini": ("acp", "experimental", "basic", True),
        "opencode": ("opencode_http", "beta", "full", False),
    }
    assert {
        item.id: (
            item.session_protocol,
            item.protocol_maturity,
            item.session_level,
            item.native_session_implemented,
        )
        for item in AGENT_SPECS
    } == expected
    for item in AGENT_SPECS:
        public = item.public()
        assert public["session_protocol"]
        assert public["fallbacks"]
        assert public["native_session_implemented"] is expected[item.id][3]


def test_manifest_declares_exact_connection_and_execution_tiers():
    expected = {
        "codex": ("native_cli", "direct"),
        "claude": ("native_cli", "direct"),
        "openai": ("api", "direct"),
        "anthropic": ("api", "import_only"),
        "deepseek": ("api", "direct"),
        "qwen": ("api", "direct"),
        "compatible_api": ("api", "direct"),
        "mcp": ("mcp", "handoff"),
        "taskpack": ("taskpack", "import_only"),
        "workbuddy": ("restricted_cli", "handoff"),
    }
    assert {
        item_id: (
            capability_manifest.capability(item_id).connection,
            capability_manifest.capability(item_id).execution_level,
        )
        for item_id in expected
    } == expected
    unknown = capability_manifest.capability_or_unknown("unlisted-agent")
    assert unknown.id == "unlisted-agent"
    assert unknown.connection == "restricted_cli"
    assert unknown.execution_level == "import_only"


def test_compatible_api_requires_explicit_https_base_auth_type_model_and_secret(
        monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "compatible_api")
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "secret-value")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "custom-model")
    monkeypatch.setenv("INTDOG_LLM_AUTH_TYPE", "bearer")

    missing_base = provider_readiness("compatible_api", tmp_path)
    assert missing_base["ready"] is False
    assert missing_base["failure_code"] == "missing_api_base"

    monkeypatch.setenv("INTDOG_LLM_API_BASE", "https://models.example/v1")
    ready = provider_readiness("compatible_api", tmp_path)
    assert ready["ready"] is True
    assert "secret-value" not in str(ready)
    service = LLMService({"llm": {}}, provider="compatible_api")
    assert service.base == "https://models.example/v1"
    assert service.model == "custom-model"


def test_non_allowlisted_api_is_catalogued_without_becoming_direct_provider():
    anthropic = capability_manifest.capability("anthropic")
    assert anthropic is not None
    assert anthropic.execution_level == "import_only"
    assert "anthropic" not in DIRECT_PROVIDER_IDS
    assert "anthropic" not in CAPABILITIES


def test_generic_compatible_api_cannot_consume_a_different_selected_provider_secret(
        monkeypatch, tmp_path):
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "deepseek-only-secret")
    config = {"llm": {
        "provider": "compatible_api", "model": "custom-model",
        "api_base": "https://models.example/v1", "auth_type": "bearer",
    }}
    assert provider_readiness("compatible_api", tmp_path)["ready"] is False
    try:
        LLMService(config, provider="compatible_api")
    except LLMConfigurationError as exc:
        assert "密钥" in str(exc)
    else:
        raise AssertionError("generic API must not consume another provider's desktop key")


def test_generic_api_key_header_keeps_compatible_chat_path(monkeypatch):
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "compatible_api")
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "configured-secret")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "custom-model")
    monkeypatch.setenv("INTDOG_LLM_API_BASE", "https://models.example/v1")
    monkeypatch.setenv("INTDOG_LLM_AUTH_TYPE", "api_key_header")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "result-1", "choices": [{"message": {"content": "ok"}}]}

    with patch("src.services.llm_service.requests.post", return_value=Response()) as post:
        result = LLMService({"llm": {}}, provider="compatible_api").complete("prompt")
    assert result.text == "ok"
    assert post.call_args.args[0] == "https://models.example/v1/chat/completions"
    assert post.call_args.kwargs["headers"]["api-key"] == "configured-secret"
    assert "Authorization" not in post.call_args.kwargs["headers"]


@pytest.mark.parametrize("label", ["OpenAI", "openai api", "DeepSeek API", "Qwen"])
def test_provider_display_name_is_rejected_as_model_id(label):
    """Catches a provider label being sent as the API model identifier."""
    with pytest.raises(LLMConfigurationError, match="模型 ID"):
        validate_model_id("openai", label)


def test_readiness_rejects_provider_name_in_model_field(monkeypatch, tmp_path):
    """Catches setup declaring an obviously invalid API model ready."""
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "openai")
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "test-secret-value")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "Openai")
    result = provider_readiness("openai", tmp_path)
    assert result["ready"] is False
    assert result["failure_code"] == "invalid_model"
    assert "模型 ID" in result["detail"]


def test_openai_error_retains_safe_provider_detail_and_redacts_credentials(monkeypatch):
    """Catches Responses API failures collapsing to a generic HTTP 400."""
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "openai")
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "provider-error-canary-9347")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "gpt-test")

    class Response:
        status_code = 400
        headers = {"x-request-id": "req_safe_123"}

        @staticmethod
        def json():
            return {"error": {"message": "The requested model does not exist",
                              "type": "invalid_request_error", "param": "model",
                              "code": "model_not_found"}}

    with patch("src.services.llm_service.requests.post", return_value=Response()):
        with pytest.raises(ProviderRequestError) as caught:
            LLMService({"llm": {}}, provider="openai").complete("prompt")
    public = caught.value.public()
    assert public == {
        "category": "invalid_model", "status_code": 400,
        "code": "model_not_found", "param": "model",
        "request_id": "req_safe_123",
        "detail": "The requested model does not exist",
    }
    rendered = f"{caught.value} {public}"
    assert "provider-error-canary-9347" not in rendered
    assert "Authorization" not in rendered


def test_openai_unsupported_web_tool_has_distinct_category(monkeypatch):
    """Catches a required web-search failure being mislabeled as a model error."""
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "openai")
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "test-secret-value")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "gpt-test")

    class Response:
        status_code = 400
        headers = {"x-request-id": "req_tool_123"}

        @staticmethod
        def json():
            return {"error": {"message": "Tool web_search is not supported",
                              "type": "invalid_request_error", "param": "tools",
                              "code": "unsupported_tool"}}

    with patch("src.services.llm_service.requests.post", return_value=Response()):
        with pytest.raises(ProviderRequestError) as caught:
            LLMService({"llm": {}}, provider="openai").probe(required_web_search=True)
    assert caught.value.category == "unsupported_tool"


def test_openai_probe_exercises_required_web_search(monkeypatch):
    """Catches a connection probe claiming readiness without testing the required tool."""
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "openai")
    monkeypatch.setenv("INTDOG_LLM_API_KEY", "test-secret-value")
    monkeypatch.setenv("INTDOG_LLM_MODEL", "gpt-test")

    class Response:
        status_code = 200
        headers = {"x-request-id": "req_probe_123"}

        @staticmethod
        def json():
            return {"id": "resp_probe", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "ok"}]}], "usage": {}}

    with patch("src.services.llm_service.requests.post", return_value=Response()) as post:
        result = LLMService({"llm": {}}, provider="openai").probe(
            required_web_search=True)
    assert result == {"ready": True, "provider": "openai", "model": "gpt-test",
                      "web_search": True, "request_id": "req_probe_123"}
    assert post.call_args.kwargs["json"]["tools"] == [{"type": "web_search"}]


def test_compatible_api_probe_refuses_unavailable_required_web_search(monkeypatch):
    monkeypatch.setenv("INTDOG_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    service = LLMService({"llm": {"provider": "deepseek"}}, "deepseek")
    with pytest.raises(ProviderRequestError) as caught:
        service.probe(required_web_search=True)
    assert caught.value.category == "unsupported_tool"
