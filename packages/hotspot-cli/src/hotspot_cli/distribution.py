from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional


class DistributionError(RuntimeError):
    pass


Runner = Callable[[list[str], Optional[Path]], str]


def subprocess_runner(argv: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if proc.returncode != 0:
        raise DistributionError(proc.stderr.strip() or proc.stdout.strip() or f"命令执行失败：{' '.join(argv)}")
    return proc.stdout.strip()


class DistributionChannel(ABC):
    @abstractmethod
    def send(
        self,
        *,
        chat_id: str,
        topic: str,
        summary: str,
        report_path: Path,
        identity: str,
        message_template: str,
        upload_folder_token: str = "",
    ) -> None:
        raise NotImplementedError


class LarkChannel(DistributionChannel):
    def __init__(self, runner: Runner = subprocess_runner) -> None:
        self.runner = runner

    def send(
        self,
        *,
        chat_id: str,
        topic: str,
        summary: str,
        report_path: Path,
        identity: str,
        message_template: str,
        upload_folder_token: str = "",
    ) -> None:
        if not chat_id:
            raise DistributionError("缺少飞书群 chat_id。请先运行 config lark。")
        if not report_path.exists():
            raise DistributionError(f"报告文件不存在：{report_path}")
        text = message_template.format(topic=topic, summary=summary, report_path=str(report_path))
        self.runner(
            [
                "lark-cli",
                "im",
                "+messages-send",
                "--chat-id",
                chat_id,
                "--text",
                text,
                "--as",
                identity,
            ],
            None,
        )
        self.runner(
            [
                "lark-cli",
                "im",
                "+messages-send",
                "--chat-id",
                chat_id,
                "--file",
                report_path.name,
                "--as",
                identity,
            ],
            report_path.parent,
        )
        if upload_folder_token:
            upload_cmd = ["lark-cli", "drive", "+upload", "--file", str(report_path), "--as", identity]
            upload_cmd.extend(["--folder-token", upload_folder_token])
            self.runner(upload_cmd, None)


class ChannelRegistry:
    def __init__(self) -> None:
        self._channels: dict[str, DistributionChannel] = {"lark": LarkChannel()}

    def register(self, name: str, channel: DistributionChannel) -> None:
        self._channels[name] = channel

    def get(self, name: str) -> DistributionChannel:
        try:
            return self._channels[name]
        except KeyError as exc:
            raise DistributionError(f"未知分发渠道：{name}") from exc
