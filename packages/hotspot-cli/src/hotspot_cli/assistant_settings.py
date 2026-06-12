from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()
USER_ENV_PATH = Path.home() / ".hotspot-research-cli" / ".env"
load_dotenv(USER_ENV_PATH)


class AssistantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HOTSPOT_", extra="ignore")

    llm_provider: str = "deepseek"
    llm_model: str = "deepseek/deepseek-chat"
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    siliconflow_api_key: Optional[str] = None
    moonshot_api_key: Optional[str] = None
    qwen_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"
    cache_ttl_seconds: int = 6 * 3600
    output_dir: Path = Path("briefs")

    def has_llm_key(self) -> bool:
        if self.llm_api_key:
            return True
        if self.llm_provider == "openai":
            return bool(self.openai_api_key or os.environ.get("OPENAI_API_KEY"))
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
        if self.llm_provider == "deepseek":
            return bool(self.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY"))
        if self.llm_provider == "openrouter":
            return bool(self.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY"))
        if self.llm_provider == "siliconflow":
            return bool(self.siliconflow_api_key or os.environ.get("SILICONFLOW_API_KEY"))
        if self.llm_provider == "moonshot":
            return bool(self.moonshot_api_key or os.environ.get("MOONSHOT_API_KEY"))
        if self.llm_provider == "qwen":
            return bool(self.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY"))
        if self.llm_provider in {"openai-compatible", "custom"}:
            return bool(self.llm_api_key or os.environ.get("OPENAI_API_KEY"))
        if self.llm_provider == "ollama":
            return True
        return False

    def apply_provider_env(self) -> None:
        if self.llm_api_key and not os.environ.get("HOTSPOT_LLM_API_KEY"):
            os.environ["HOTSPOT_LLM_API_KEY"] = self.llm_api_key
        if self.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = self.anthropic_api_key
        if self.deepseek_api_key and not os.environ.get("DEEPSEEK_API_KEY"):
            os.environ["DEEPSEEK_API_KEY"] = self.deepseek_api_key
        if self.openrouter_api_key and not os.environ.get("OPENROUTER_API_KEY"):
            os.environ["OPENROUTER_API_KEY"] = self.openrouter_api_key
        if self.siliconflow_api_key and not os.environ.get("SILICONFLOW_API_KEY"):
            os.environ["SILICONFLOW_API_KEY"] = self.siliconflow_api_key
        if self.moonshot_api_key and not os.environ.get("MOONSHOT_API_KEY"):
            os.environ["MOONSHOT_API_KEY"] = self.moonshot_api_key
        if self.qwen_api_key and not os.environ.get("DASHSCOPE_API_KEY"):
            os.environ["DASHSCOPE_API_KEY"] = self.qwen_api_key
        if self.ollama_base_url and not os.environ.get("OLLAMA_API_BASE"):
            os.environ["OLLAMA_API_BASE"] = self.ollama_base_url

    def litellm_kwargs(self) -> dict[str, str]:
        kwargs: dict[str, str] = {}
        api_key = self.llm_api_key or _provider_api_key(self)
        if api_key:
            kwargs["api_key"] = api_key
        base_url = self.llm_base_url
        if self.llm_provider == "ollama":
            base_url = self.ollama_base_url
        if base_url:
            kwargs["api_base"] = base_url
        return kwargs


def save_llm_env(
    *,
    provider: str,
    model: str,
    api_key: str = "",
    base_url: str = "",
    ollama_base_url: str = "http://localhost:11434",
) -> Path:
    USER_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"HOTSPOT_LLM_PROVIDER={provider}",
        f"HOTSPOT_LLM_MODEL={model}",
        f"HOTSPOT_LLM_BASE_URL={base_url}",
        f"HOTSPOT_OLLAMA_BASE_URL={ollama_base_url}",
    ]
    if api_key:
        lines.append(f"HOTSPOT_LLM_API_KEY={api_key}")
    if provider == "openai" and api_key:
        lines.append(f"HOTSPOT_OPENAI_API_KEY={api_key}")
        lines.append(f"OPENAI_API_KEY={api_key}")
    if provider == "anthropic" and api_key:
        lines.append(f"HOTSPOT_ANTHROPIC_API_KEY={api_key}")
        lines.append(f"ANTHROPIC_API_KEY={api_key}")
    if provider == "deepseek" and api_key:
        lines.append(f"HOTSPOT_DEEPSEEK_API_KEY={api_key}")
        lines.append(f"DEEPSEEK_API_KEY={api_key}")
    if provider == "openrouter" and api_key:
        lines.append(f"HOTSPOT_OPENROUTER_API_KEY={api_key}")
        lines.append(f"OPENROUTER_API_KEY={api_key}")
    if provider == "siliconflow" and api_key:
        lines.append(f"HOTSPOT_SILICONFLOW_API_KEY={api_key}")
        lines.append(f"SILICONFLOW_API_KEY={api_key}")
    if provider == "moonshot" and api_key:
        lines.append(f"HOTSPOT_MOONSHOT_API_KEY={api_key}")
        lines.append(f"MOONSHOT_API_KEY={api_key}")
    if provider == "qwen" and api_key:
        lines.append(f"HOTSPOT_QWEN_API_KEY={api_key}")
        lines.append(f"DASHSCOPE_API_KEY={api_key}")
    if provider in {"openai-compatible", "custom"} and api_key:
        lines.append(f"OPENAI_API_KEY={api_key}")
    if provider in {"openai-compatible", "custom"} and base_url:
        lines.append(f"OPENAI_BASE_URL={base_url}")
    USER_ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return USER_ENV_PATH


def _provider_api_key(settings: AssistantSettings) -> Optional[str]:
    mapping = {
        "openai": settings.openai_api_key or os.environ.get("OPENAI_API_KEY"),
        "anthropic": settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"),
        "deepseek": settings.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY"),
        "openrouter": settings.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY"),
        "siliconflow": settings.siliconflow_api_key or os.environ.get("SILICONFLOW_API_KEY"),
        "moonshot": settings.moonshot_api_key or os.environ.get("MOONSHOT_API_KEY"),
        "qwen": settings.qwen_api_key or os.environ.get("DASHSCOPE_API_KEY"),
        "openai-compatible": os.environ.get("OPENAI_API_KEY"),
        "custom": os.environ.get("OPENAI_API_KEY"),
    }
    return mapping.get(settings.llm_provider)
