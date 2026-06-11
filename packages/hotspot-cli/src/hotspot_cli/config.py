from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_TEMPLATE = "选题：{topic}\n简介：{summary}\n本地报告：{report_path}"


@dataclass
class LarkConfig:
    chat_id: str = ""
    identity: str = "bot"
    message_template: str = DEFAULT_TEMPLATE
    upload_folder_token: str = ""


@dataclass
class AppConfig:
    lark: LarkConfig = field(default_factory=LarkConfig)


class ConfigError(RuntimeError):
    pass


class ConfigManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path.home() / ".hotspot-research-cli" / "config.json"

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            raw = self._read_mapping()
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"配置文件读取失败：{self.path}。请检查 JSON/YAML 格式。原始错误：{exc}") from exc
        lark_raw = raw.get("lark", {}) if isinstance(raw, dict) else {}
        return AppConfig(
            lark=LarkConfig(
                chat_id=str(lark_raw.get("chat_id", "") or ""),
                identity=str(lark_raw.get("identity", "bot") or "bot"),
                message_template=str(lark_raw.get("message_template", DEFAULT_TEMPLATE) or DEFAULT_TEMPLATE),
                upload_folder_token=str(lark_raw.get("upload_folder_token", "") or ""),
            )
        )

    def save(self, config: AppConfig) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.suffix.lower() in {".yaml", ".yml"}:
                self._write_yaml(asdict(config))
            else:
                self.path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except PermissionError as exc:
            raise ConfigError(f"无法写入配置文件：{self.path}。请检查目录权限。") from exc

    def update_lark(
        self,
        *,
        chat_id: str | None = None,
        identity: str | None = None,
        message_template: str | None = None,
        upload_folder_token: str | None = None,
    ) -> AppConfig:
        config = self.load()
        if chat_id is not None:
            config.lark.chat_id = chat_id
        if identity is not None:
            if identity not in {"bot", "user"}:
                raise ConfigError("飞书 identity 只能是 bot 或 user。")
            config.lark.identity = identity
        if message_template is not None:
            config.lark.message_template = message_template
        if upload_folder_token is not None:
            config.lark.upload_folder_token = upload_folder_token
        self.save(config)
        return config

    def reset(self) -> None:
        self.save(AppConfig())

    def _read_mapping(self) -> dict[str, Any]:
        text = self.path.read_text(encoding="utf-8")
        if self.path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise ConfigError("读取 YAML 配置需要安装 PyYAML；也可以改用 config.json。") from exc
            data = yaml.safe_load(text) or {}
            return data if isinstance(data, dict) else {}
        data = json.loads(text)
        return data if isinstance(data, dict) else {}

    def _write_yaml(self, data: dict[str, Any]) -> None:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ConfigError("写入 YAML 配置需要安装 PyYAML；也可以改用 config.json。") from exc
        self.path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
