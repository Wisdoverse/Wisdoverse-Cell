"""
Multi-provider LLM client for acceptance checks.
=================================================
Supports international and Chinese LLM providers.
Auto-detects available provider from environment variables.

International: Anthropic, OpenAI, Google Gemini, OpenRouter
China:         Zhipu, MiniMax, DeepSeek, Qwen, Baichuan, Moonshot
Local:         Ollama
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Provider registry — OpenAI-compatible providers share one implementation
# ---------------------------------------------------------------------------

_PROVIDER_REGISTRY: dict[str, dict] = {
    # --- International ---
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
        "type": "anthropic",
    },
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "type": "openai_compat",
        "base_url": None,  # uses SDK default
    },
    "gemini": {
        "env_key": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-flash",
        "type": "gemini",
    },
    "openrouter": {
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "anthropic/claude-sonnet-4-20250514",
        "type": "openai_compat",
        "base_url": "https://openrouter.ai/api/v1",
    },
    # --- China ---
    "zhipu": {
        "env_key": "ZHIPU_API_KEY",
        "default_model": "glm-4-plus",
        "type": "openai_compat",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
    },
    "minimax": {
        "env_key": "MINIMAX_API_KEY",
        "default_model": "MiniMax-Text-01",
        "type": "openai_compat",
        "base_url": "https://api.minimax.chat/v1",
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "type": "openai_compat",
        "base_url": "https://api.deepseek.com/v1",
    },
    "qwen": {
        "env_key": "DASHSCOPE_API_KEY",
        "default_model": "qwen-plus",
        "type": "openai_compat",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "baichuan": {
        "env_key": "BAICHUAN_API_KEY",
        "default_model": "Baichuan4",
        "type": "openai_compat",
        "base_url": "https://api.baichuan-ai.com/v1",
    },
    "moonshot": {
        "env_key": "MOONSHOT_API_KEY",
        "default_model": "moonshot-v1-8k",
        "type": "openai_compat",
        "base_url": "https://api.moonshot.cn/v1",
    },
    "yi": {
        "env_key": "YI_API_KEY",
        "default_model": "yi-large",
        "type": "openai_compat",
        "base_url": "https://api.lingyiwanwu.com/v1",
    },
    "stepfun": {
        "env_key": "STEPFUN_API_KEY",
        "default_model": "step-2-16k",
        "type": "openai_compat",
        "base_url": "https://api.stepfun.com/v1",
    },
    # --- Local ---
    "ollama": {
        "env_key": "OLLAMA_BASE_URL",
        "default_model": "qwen2.5:14b",
        "type": "ollama",
    },
}

# Detection order: international first, then CN, then local
_DETECT_ORDER = [
    "anthropic", "openai", "gemini", "openrouter",
    "zhipu", "minimax", "deepseek", "qwen",
    "baichuan", "moonshot", "yi", "stepfun",
    "ollama",
]


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


def _detect_provider() -> tuple[str, str]:
    """Detect available LLM provider from env vars."""
    for name in _DETECT_ORDER:
        conf = _PROVIDER_REGISTRY[name]
        val = os.environ.get(conf["env_key"], "")
        if val:
            return name, val

    # Fallback: acceptance-specific override
    override = os.environ.get("ACCEPTANCE_LLM_PROVIDER", "")
    if override:
        key_var = os.environ.get("ACCEPTANCE_LLM_API_KEY", "")
        return override, key_var

    return "", ""


def list_providers() -> list[dict]:
    """List all supported providers and their status."""
    result = []
    for name in _DETECT_ORDER:
        conf = _PROVIDER_REGISTRY[name]
        available = bool(os.environ.get(conf["env_key"], ""))
        result.append({
            "name": name,
            "env_key": conf["env_key"],
            "default_model": conf["default_model"],
            "available": available,
        })
    return result


def complete(
    prompt: str,
    *,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 2000,
    provider: str | None = None,
) -> LLMResponse:
    """
    Send a completion request to the best available LLM provider.

    Auto-detects provider from environment variables if not specified.
    All OpenAI-compatible providers (OpenAI, Zhipu, MiniMax, Deepseek,
    Qwen, Baichuan, Moonshot, Yi, StepFun, OpenRouter) use a shared
    implementation.
    """
    if provider:
        conf = _PROVIDER_REGISTRY.get(provider)
        if not conf:
            raise RuntimeError(
                f"Unknown provider: {provider}. "
                f"Supported: {', '.join(_DETECT_ORDER)}"
            )
        api_key = os.environ.get(conf["env_key"], "")
        if not api_key:
            api_key = os.environ.get("ACCEPTANCE_LLM_API_KEY", "")
    else:
        provider, api_key = _detect_provider()

    if not provider:
        env_keys = [_PROVIDER_REGISTRY[p]["env_key"] for p in _DETECT_ORDER]
        raise RuntimeError(
            "No LLM provider available. Set one of:\n"
            + ", ".join(env_keys)
        )

    conf = _PROVIDER_REGISTRY[provider]
    model = model or conf["default_model"]
    ptype = conf["type"]

    if ptype == "anthropic":
        return _call_anthropic(prompt, system, model, max_tokens, api_key)
    elif ptype == "openai_compat":
        base_url = conf.get("base_url")
        return _call_openai_compat(
            prompt, system, model, max_tokens, api_key,
            base_url=base_url, provider_name=provider,
        )
    elif ptype == "gemini":
        return _call_gemini(prompt, system, model, max_tokens, api_key)
    elif ptype == "ollama":
        return _call_ollama(prompt, system, model, max_tokens, api_key)
    else:
        raise RuntimeError(f"Unknown provider type: {ptype}")


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_anthropic(
    prompt: str, system: str, model: str, max_tokens: int, api_key: str,
) -> LLMResponse:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return LLMResponse(
        text=resp.content[0].text,
        model=model,
        provider="anthropic",
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
    )


def _call_openai_compat(
    prompt: str,
    system: str,
    model: str,
    max_tokens: int,
    api_key: str,
    *,
    base_url: str | None = None,
    provider_name: str = "openai",
) -> LLMResponse:
    """Shared implementation for all OpenAI-compatible APIs.

    Works with: OpenAI, Zhipu, MiniMax, Deepseek, Qwen,
    Baichuan, Moonshot, Yi, StepFun, OpenRouter.
    """
    from openai import OpenAI

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    choice = resp.choices[0]
    usage = resp.usage
    return LLMResponse(
        text=choice.message.content or "",
        model=model,
        provider=provider_name,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )


def _call_gemini(
    prompt: str, system: str, model: str, max_tokens: int, api_key: str,
) -> LLMResponse:
    """Call Google Gemini via REST API (no SDK dependency)."""
    import urllib.request

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    usage_meta = data.get("usageMetadata", {})
    return LLMResponse(
        text=text,
        model=model,
        provider="gemini",
        input_tokens=usage_meta.get("promptTokenCount", 0),
        output_tokens=usage_meta.get("candidatesTokenCount", 0),
    )


def _call_ollama(
    prompt: str, system: str, model: str, max_tokens: int, base_url: str,
) -> LLMResponse:
    """Call local Ollama instance via REST API."""
    import urllib.request

    url = f"{base_url.rstrip('/')}/api/generate"
    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    if system:
        body["system"] = system

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())

    return LLMResponse(
        text=data.get("response", ""),
        model=model,
        provider="ollama",
        input_tokens=data.get("prompt_eval_count", 0),
        output_tokens=data.get("eval_count", 0),
    )


def parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)
