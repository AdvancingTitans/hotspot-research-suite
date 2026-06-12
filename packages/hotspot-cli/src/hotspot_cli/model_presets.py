from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPreset:
    provider: str
    label: str
    model: str
    api_key_name: str
    base_url: str = ""
    note: str = ""


MODEL_PRESETS: dict[str, ModelPreset] = {
    "deepseek": ModelPreset(
        provider="deepseek",
        label="DeepSeek（推荐，便宜且中文表现好）",
        model="deepseek/deepseek-chat",
        api_key_name="DEEPSEEK_API_KEY",
        note="适合中文选题分析和长文本结构化输出。",
    ),
    "openai": ModelPreset(
        provider="openai",
        label="OpenAI",
        model="gpt-4o-mini",
        api_key_name="OPENAI_API_KEY",
        note="稳定通用，适合英文资料较多的研究方向。",
    ),
    "anthropic": ModelPreset(
        provider="anthropic",
        label="Anthropic Claude",
        model="claude-3-5-sonnet-latest",
        api_key_name="ANTHROPIC_API_KEY",
        note="适合长文推理和结构化写作。",
    ),
    "openrouter": ModelPreset(
        provider="openrouter",
        label="OpenRouter（多模型聚合）",
        model="openrouter/anthropic/claude-3.5-sonnet",
        api_key_name="OPENROUTER_API_KEY",
        note="一个 Key 切换多家模型。",
    ),
    "siliconflow": ModelPreset(
        provider="siliconflow",
        label="SiliconFlow（国内聚合）",
        model="openai/Qwen/Qwen2.5-72B-Instruct",
        api_key_name="SILICONFLOW_API_KEY",
        base_url="https://api.siliconflow.cn/v1",
        note="OpenAI-Compatible 接口，适合国内网络环境。",
    ),
    "moonshot": ModelPreset(
        provider="moonshot",
        label="Moonshot Kimi",
        model="openai/moonshot-v1-32k",
        api_key_name="MOONSHOT_API_KEY",
        base_url="https://api.moonshot.cn/v1",
        note="适合中文长上下文资料整理。",
    ),
    "qwen": ModelPreset(
        provider="qwen",
        label="通义千问 DashScope",
        model="openai/qwen-plus",
        api_key_name="DASHSCOPE_API_KEY",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        note="OpenAI-Compatible 接口，适合中文场景。",
    ),
    "ollama": ModelPreset(
        provider="ollama",
        label="Ollama 本地模型",
        model="ollama/qwen2.5:14b",
        api_key_name="",
        base_url="http://localhost:11434",
        note="不需要云端 API Key，但质量取决于本地模型。",
    ),
    "custom": ModelPreset(
        provider="openai-compatible",
        label="自定义 OpenAI-Compatible 接口",
        model="openai/your-model-name",
        api_key_name="OPENAI_API_KEY",
        note="适合火山、智谱、OneAPI、LiteLLM Proxy 等兼容接口。",
    ),
    "openai-compatible": ModelPreset(
        provider="openai-compatible",
        label="自定义 OpenAI-Compatible 接口",
        model="openai/your-model-name",
        api_key_name="OPENAI_API_KEY",
        note="适合火山、智谱、OneAPI、LiteLLM Proxy 等兼容接口。",
    ),
}


def preset_choices() -> list[tuple[str, str]]:
    return [(key, f"{item.label}：{item.note}") for key, item in MODEL_PRESETS.items()]
