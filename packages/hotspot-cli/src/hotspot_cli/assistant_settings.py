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

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"
    cache_ttl_seconds: int = 6 * 3600
    output_dir: Path = Path("briefs")

    def has_llm_key(self) -> bool:
        if self.llm_provider == "openai":
            return bool(self.openai_api_key or os.environ.get("OPENAI_API_KEY"))
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
        if self.llm_provider == "ollama":
            return True
        return False

    def apply_provider_env(self) -> None:
        if self.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = self.anthropic_api_key
        if self.ollama_base_url and not os.environ.get("OLLAMA_API_BASE"):
            os.environ["OLLAMA_API_BASE"] = self.ollama_base_url


def save_llm_env(*, provider: str, model: str, api_key: str = "", ollama_base_url: str = "http://localhost:11434") -> Path:
    USER_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"HOTSPOT_LLM_PROVIDER={provider}",
        f"HOTSPOT_LLM_MODEL={model}",
        f"HOTSPOT_OLLAMA_BASE_URL={ollama_base_url}",
    ]
    if provider == "openai" and api_key:
        lines.append(f"HOTSPOT_OPENAI_API_KEY={api_key}")
        lines.append(f"OPENAI_API_KEY={api_key}")
    if provider == "anthropic" and api_key:
        lines.append(f"HOTSPOT_ANTHROPIC_API_KEY={api_key}")
        lines.append(f"ANTHROPIC_API_KEY={api_key}")
    USER_ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return USER_ENV_PATH
