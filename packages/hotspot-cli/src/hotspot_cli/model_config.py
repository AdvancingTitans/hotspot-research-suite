from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .model_presets import MODEL_PRESETS


OPENAI_COMPATIBLE_PROVIDERS = {"ark", "qwen", "moonshot", "siliconflow", "openai-compatible", "custom"}
PLACEHOLDER_MODELS = {"", "openai/your-model-name", "your-model-name"}


@dataclass
class ModelConfigPlan:
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    ollama_base_url: str = "http://localhost:11434"
    warnings: list[str] = field(default_factory=list)


@dataclass
class ModelCheckResult:
    ok: bool
    message: str
    detail: str = ""


def existing_api_key(provider: str) -> str:
    env_names = {
        "openai": ("HOTSPOT_OPENAI_API_KEY", "OPENAI_API_KEY"),
        "anthropic": ("HOTSPOT_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
        "deepseek": ("HOTSPOT_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
        "openrouter": ("HOTSPOT_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
        "siliconflow": ("HOTSPOT_SILICONFLOW_API_KEY", "SILICONFLOW_API_KEY", "HOTSPOT_LLM_API_KEY"),
        "moonshot": ("HOTSPOT_MOONSHOT_API_KEY", "MOONSHOT_API_KEY", "HOTSPOT_LLM_API_KEY"),
        "qwen": ("HOTSPOT_QWEN_API_KEY", "DASHSCOPE_API_KEY", "HOTSPOT_LLM_API_KEY"),
        "ark": ("HOTSPOT_ARK_API_KEY", "ARK_API_KEY", "HOTSPOT_LLM_API_KEY", "OPENAI_API_KEY"),
        "openai-compatible": ("HOTSPOT_LLM_API_KEY", "OPENAI_API_KEY"),
        "custom": ("HOTSPOT_LLM_API_KEY", "OPENAI_API_KEY"),
    }.get(provider, ("HOTSPOT_LLM_API_KEY",))
    for name in env_names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def prepare_model_config(
    *,
    provider: str,
    model: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
    ollama_base_url: str = "http://localhost:11434",
) -> ModelConfigPlan:
    preset = MODEL_PRESETS.get(provider)
    if preset is None:
        raise ValueError(f"未知模型服务商：{provider}")

    actual_provider = "openai-compatible" if provider == "custom" else provider
    chosen_model = model or preset.model
    chosen_base = base_url if base_url is not None else preset.base_url
    chosen_key = api_key if api_key is not None else existing_api_key(provider)
    warnings: list[str] = []

    if provider == "ark":
        if not chosen_base or "/api/coding" in chosen_base:
            if chosen_base and "/api/coding" in chosen_base:
                warnings.append("已将火山方舟错误入口 /api/coding 自动修正为 /api/v3。")
            chosen_base = "https://ark.cn-beijing.volces.com/api/v3"
        if chosen_model in PLACEHOLDER_MODELS:
            chosen_model = preset.model
            warnings.append(f"已将占位模型名替换为可用默认模型：{chosen_model}。")

    if provider in {"custom", "openai-compatible"}:
        if not chosen_base:
            raise ValueError("自定义 OpenAI-Compatible 接口必须提供 --base-url。")
        if chosen_model in PLACEHOLDER_MODELS:
            raise ValueError("自定义 OpenAI-Compatible 接口必须提供真实 --model，不能使用 openai/your-model-name。")

    if provider != "ollama" and not chosen_key:
        raise ValueError(f"{provider} 需要 API Key。可通过 --api-key 传入，或先设置对应环境变量。")

    if provider == "ollama":
        chosen_base = ""
        chosen_key = ""
        ollama_base_url = base_url or ollama_base_url

    return ModelConfigPlan(
        provider=actual_provider,
        model=chosen_model,
        api_key=chosen_key,
        base_url=chosen_base or "",
        ollama_base_url=ollama_base_url,
        warnings=warnings,
    )


def verify_model_config(plan: ModelConfigPlan, *, timeout: float = 30) -> ModelCheckResult:
    try:
        if plan.provider == "ollama":
            return _verify_ollama(plan, timeout=timeout)
        _verify_model_endpoint(plan, timeout=timeout)
        from litellm import completion  # type: ignore

        kwargs: dict[str, str] = {}
        if plan.api_key:
            kwargs["api_key"] = plan.api_key
        if plan.base_url:
            kwargs["api_base"] = plan.base_url
        response = completion(
            model=plan.model,
            messages=[{"role": "user", "content": "只回复 OK"}],
            max_tokens=10,
            temperature=0,
            **kwargs,
        )
        content = (response.choices[0].message.content or "").strip()
        if content:
            return ModelCheckResult(True, "模型连通性验证通过。", f"返回：{content[:40]}")
        return ModelCheckResult(False, "模型返回为空。", "请检查模型名是否支持 Chat Completions。")
    except Exception as exc:
        return ModelCheckResult(False, "模型连通性验证失败。", _friendly_error(str(exc), plan))


def fetch_model_ids(plan: ModelConfigPlan, *, timeout: float = 20, limit: int = 30) -> list[str]:
    if plan.provider == "ollama":
        url = plan.ollama_base_url.rstrip("/") + "/api/tags"
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()
        return [str(item.get("name")) for item in data.get("models", []) if item.get("name")][:limit]
    if not plan.base_url:
        return []
    headers = {"Authorization": f"Bearer {plan.api_key}"} if plan.api_key else {}
    with httpx.Client(timeout=timeout) as client:
        response = client.get(plan.base_url.rstrip("/") + "/models", headers=headers)
        response.raise_for_status()
        data = response.json()
    ids = []
    for item in data.get("data", []):
        status = str(item.get("status") or "").lower()
        if status in {"shutdown", "expired", "retired", "retiring"}:
            continue
        model_id = str(item.get("id") or "")
        if not model_id:
            continue
        lowered = model_id.lower()
        if any(token in lowered for token in ("embedding", "seedance", "seedream", "tts", "asr", "image", "video", "vision")):
            continue
        ids.append(model_id)
    if plan.provider in OPENAI_COMPATIBLE_PROVIDERS:
        ids = [mid if mid.startswith(("openai/", "ollama/")) else f"openai/{mid}" for mid in ids]
    return ids[:limit]


def _verify_model_endpoint(plan: ModelConfigPlan, *, timeout: float) -> None:
    if plan.provider not in OPENAI_COMPATIBLE_PROVIDERS or not plan.base_url:
        return
    headers = {"Authorization": f"Bearer {plan.api_key}"} if plan.api_key else {}
    with httpx.Client(timeout=timeout) as client:
        response = client.get(plan.base_url.rstrip("/") + "/models", headers=headers)
        response.raise_for_status()


def _verify_ollama(plan: ModelConfigPlan, *, timeout: float) -> ModelCheckResult:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(plan.ollama_base_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
        return ModelCheckResult(True, "Ollama 连通性验证通过。")
    except Exception as exc:
        return ModelCheckResult(False, "Ollama 连通性验证失败。", str(exc))


def _friendly_error(message: str, plan: ModelConfigPlan) -> str:
    text = message.replace(plan.api_key, "***REDACTED***") if plan.api_key else message
    if plan.provider == "ark" and ("/api/coding" in text or "404" in text):
        return "火山方舟 OpenAI-Compatible Base URL 应为 https://ark.cn-beijing.volces.com/api/v3，不是 /api/coding。"
    if "model" in text.lower() and "not" in text.lower():
        return f"模型名可能不可用：{plan.model}。可运行 `hotspot-research config model models --provider {plan.provider}` 查看可用模型。"
    return text[:600]
