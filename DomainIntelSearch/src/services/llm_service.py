"""Optional, explicit LLM execution for research task packages.

Task-package mode remains the default.  API calls only happen when a user
selects a provider and supplies both a model and a secret via environment
variables or configuration.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests

from .capability_manifest import API_SPECS
from .runtime_credentials import credential_for


class LLMConfigurationError(ValueError):
    pass


_PROVIDER_LABELS = {
    "openai", "openaiapi", "deepseek", "deepseekapi", "qwen", "qwenapi",
    "dashscope", "azure", "azureopenai", "anthropic", "anthropicapi",
    "compatibleapi", "provider",
}


def validate_model_id(provider: str, model: str) -> str:
    """Reject empty values and common provider labels without guessing model catalogs."""
    value = str(model or "").strip()
    compact = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if not value or compact in _PROVIDER_LABELS:
        raise LLMConfigurationError(
            f"{provider or 'API'} 的模型 ID 无效；请输入供应商提供的精确模型 ID")
    return value


class ProviderRequestError(RuntimeError):
    """Redaction-safe provider failure suitable for task logs and API responses."""

    def __init__(self, *, category: str, detail: str, status_code: int = 0,
                 code: str = "", param: str = "", request_id: str = ""):
        self.category = str(category or "provider_error")
        self.status_code = int(status_code or 0)
        self.code = str(code or "")[:120]
        self.param = str(param or "")[:120]
        self.request_id = str(request_id or "")[:160]
        self.detail = " ".join(str(detail or "Provider request failed").split())[:800]
        super().__init__(self.detail)

    def public(self) -> dict:
        return {
            "category": self.category,
            "status_code": self.status_code,
            "code": self.code,
            "param": self.param,
            "request_id": self.request_id,
            "detail": self.detail,
        }


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    response_id: str = ""
    usage: dict | None = None


class LLMService:
    """Small provider adapter; OpenAI uses Responses, others are compatible chat APIs."""

    DIRECT_APIS = tuple(item for item in API_SPECS if item.execution_level == "direct")
    DEFAULT_BASES = {item.id: item.default_api_base for item in DIRECT_APIS
                     if item.default_api_base}
    DEFAULT_MODELS = {item.id: item.default_model for item in DIRECT_APIS
                      if item.default_model}
    KEY_ENV = {item.id: item.key_env for item in DIRECT_APIS if item.key_env}
    AUTH_TYPES = {item.id: item.auth for item in DIRECT_APIS}

    def __init__(self, config: dict, provider: str = None):
        cfg = config.get("llm", {}) or {}
        self.provider = (provider or cfg.get("provider") or "none").lower()
        configured_provider = str(cfg.get("provider") or "none").lower()
        runtime = credential_for(self.provider)
        selected_env = (runtime.get("provider") or
                        os.environ.get("INTDOG_LLM_PROVIDER", "")).strip().lower()
        env_matches = not selected_env or selected_env == self.provider
        env_model = (runtime.get("model") or os.environ.get("INTDOG_LLM_MODEL", "")) \
            if env_matches else ""
        self.model = str(env_model or
                         (cfg.get("model") if configured_provider == self.provider else "") or
                         self.DEFAULT_MODELS.get(self.provider, "")).strip()
        configured_base = str(cfg.get("api_base") or "").strip()
        env_base = (runtime.get("apiBase") or os.environ.get(
            "INTDOG_LLM_API_BASE", "")).strip() if env_matches else ""
        self.base = (env_base or
                     (configured_base if configured_provider == self.provider else "") or
                     self.DEFAULT_BASES.get(self.provider, "")).rstrip("/")
        generic_key = (runtime.get("apiKey") or os.environ.get(
            "INTDOG_LLM_API_KEY")) if env_matches else ""
        key_env = self.KEY_ENV.get(self.provider, "")
        provider_key = (os.environ.get(key_env, "")
                        if key_env and (key_env != "INTDOG_LLM_API_KEY" or env_matches)
                        else "")
        self.api_key = generic_key or provider_key
        env_auth = (runtime.get("authType") or os.environ.get(
            "INTDOG_LLM_AUTH_TYPE", "")).strip().lower() \
            if env_matches else ""
        configured_auth = str(cfg.get("auth_type") or "").strip().lower()
        default_auth = self.AUTH_TYPES.get(self.provider, "")
        self.auth_type = env_auth or configured_auth or (
            "" if default_auth == "explicit" else default_auth)
        self.timeout = int(cfg.get("timeout_seconds", 180))
        self.web_search = bool(cfg.get("web_search", True))
        self.reasoning_effort = str(cfg.get("reasoning_effort") or "").strip().lower()
        self._validate()

    def _validate(self):
        if self.provider not in self.KEY_ENV:
            raise LLMConfigurationError(f"不支持的 LLM provider: {self.provider!r}")
        self.model = validate_model_id(self.provider, self.model)
        if not self.api_key or self.api_key.lower() in {"your_api_key", "changeme"}:
            env = self.KEY_ENV.get(self.provider, "INTDOG_LLM_API_KEY")
            raise LLMConfigurationError(f"缺少 API 密钥；请设置 {env} 或 INTDOG_LLM_API_KEY")
        if not self.base:
            raise LLMConfigurationError("缺少 llm.api_base")
        parsed = urlsplit(self.base)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
            raise LLMConfigurationError("非本机 API Base 必须使用 HTTPS")
        if self.auth_type not in {"bearer", "api_key_header"}:
            raise LLMConfigurationError("API 模式必须显式选择 bearer 或 api_key_header 认证")
        manifest_auth = self.AUTH_TYPES.get(self.provider, "")
        if manifest_auth != "explicit" and self.auth_type != manifest_auth:
            raise LLMConfigurationError(
                f"{self.provider} 认证方式必须使用能力目录声明的 {manifest_auth}")

    def complete(self, prompt: str) -> LLMResult:
        if self.provider == "openai":
            return self._openai_response(prompt)
        return self._compatible_chat(prompt)

    @staticmethod
    def _category(status_code: int, code: str, param: str, detail: str) -> str:
        haystack = " ".join((code, param, detail)).casefold()
        if status_code == 401 or "authentication" in haystack or "invalid_api_key" in haystack:
            return "authentication"
        if "tool" in haystack and any(word in haystack for word in (
                "unsupported", "not supported", "unknown", "invalid")):
            return "unsupported_tool"
        if param.casefold() == "model" or "model_not_found" in haystack or (
                "model" in haystack and any(word in haystack for word in (
                    "does not exist", "not found", "unsupported", "invalid"))):
            return "invalid_model"
        if status_code == 429:
            return "quota" if "quota" in haystack else "rate_limit"
        if status_code == 403:
            return "permission"
        return "provider_error"

    def _safe_detail(self, value: object) -> str:
        detail = " ".join(str(value or "Provider request failed").split())
        if self.api_key:
            detail = detail.replace(self.api_key, "***")
        detail = re.sub(r"(?i)\bsk-[A-Za-z0-9._-]+", "***", detail)
        return detail[:800]

    def _post_json(self, url: str, payload: dict, headers: dict) -> tuple[dict, str]:
        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout)
        except requests.Timeout as exc:
            raise ProviderRequestError(category="timeout", detail="Provider 请求超时") from exc
        except requests.RequestException as exc:
            raise ProviderRequestError(
                category="transport", detail=f"Provider 连接失败：{type(exc).__name__}") from exc
        status = int(getattr(response, "status_code", 0) or 0)
        response_headers = getattr(response, "headers", {}) or {}
        request_id = str(response_headers.get("x-request-id") or
                         response_headers.get("request-id") or "")
        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            if status >= 400:
                raise ProviderRequestError(
                    category="provider_error", status_code=status,
                    request_id=request_id, detail=f"Provider 返回 HTTP {status}") from exc
            raise ProviderRequestError(
                category="invalid_response", status_code=status,
                request_id=request_id, detail="Provider 返回的内容不是 JSON") from exc
        if status >= 400:
            error = data.get("error") if isinstance(data, dict) else {}
            error = error if isinstance(error, dict) else {}
            code = str(error.get("code") or "")
            param = str(error.get("param") or "")
            detail = self._safe_detail(error.get("message") or f"Provider 返回 HTTP {status}")
            raise ProviderRequestError(
                category=self._category(status, code, param, detail),
                status_code=status, code=code, param=param,
                request_id=request_id, detail=detail)
        if not status and hasattr(response, "raise_for_status"):
            response.raise_for_status()
        if not isinstance(data, dict):
            raise ProviderRequestError(
                category="invalid_response", status_code=status,
                request_id=request_id, detail="Provider 返回的 JSON 不是对象")
        return data, request_id

    def probe(self, required_web_search: bool = False) -> dict:
        if self.provider == "openai":
            payload = {"model": self.model, "input": "Reply with OK.", "store": False}
            if required_web_search:
                payload["tools"] = [{"type": "web_search"}]
            _data, request_id = self._post_json(
                f"{self.base}/responses", payload,
                {"Authorization": f"Bearer {self.api_key}",
                 "Content-Type": "application/json"})
            return {"ready": True, "provider": self.provider, "model": self.model,
                    "web_search": bool(required_web_search), "request_id": request_id}
        if required_web_search:
            raise ProviderRequestError(
                category="unsupported_tool",
                detail=f"{self.provider} 适配器未声明初始化所需的联网搜索工具")
        result = self._compatible_chat("Reply with OK.")
        return {"ready": True, "provider": self.provider, "model": self.model,
                "web_search": False, "request_id": result.response_id}

    def _openai_response(self, prompt: str) -> LLMResult:
        payload = {"model": self.model, "input": prompt, "store": False}
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        if self.web_search:
            payload["tools"] = [{"type": "web_search"}]
        data, _request_id = self._post_json(
            f"{self.base}/responses", payload,
            {"Authorization": f"Bearer {self.api_key}",
             "Content-Type": "application/json"})
        chunks = []
        for output in data.get("output", []):
            if output.get("type") != "message":
                continue
            for content in output.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        text = "\n".join(chunks).strip()
        if not text:
            raise RuntimeError("LLM 返回成功，但没有可读 output_text")
        return LLMResult(text=text, provider=self.provider, model=self.model,
                         response_id=data.get("id", ""), usage=data.get("usage"))

    def _compatible_chat(self, prompt: str) -> LLMResult:
        headers = {"Content-Type": "application/json"}
        if self.auth_type == "api_key_header":
            headers["api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider == "azure":
            url = self.base
        else:
            url = f"{self.base}/chat/completions"
        data, _request_id = self._post_json(
            url, {"model": self.model,
                  "messages": [{"role": "user", "content": prompt}]}, headers)
        choices = data.get("choices") or []
        text = choices[0].get("message", {}).get("content", "") if choices else ""
        if not text:
            raise RuntimeError("LLM 返回成功，但没有可读文本")
        return LLMResult(text=text, provider=self.provider, model=self.model,
                         response_id=data.get("id", ""), usage=data.get("usage"))
