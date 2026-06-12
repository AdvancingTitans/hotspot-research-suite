from __future__ import annotations

import os
import sys
from pathlib import Path
import shutil
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown

from .assistant_app import TopicAssistantApp
from .assistant_analyzer import InstructorTopicAnalyzer
from .assistant_models import TopicSelection
from .assistant_settings import save_llm_env
from .assistant_sources import Last30DaysProvider
from .assistant_writer import BriefWriter
from .config import ConfigError, ConfigManager, DEFAULT_TEMPLATE
from .distribution import ChannelRegistry, DistributionError, lark_cli_status
from .hotspots import HotspotError


app = typer.Typer(help="交互式选题智能助手", rich_markup_mode="rich")
config_app = typer.Typer(help="配置管理")
lark_app = typer.Typer(help="飞书配置")
llm_app = typer.Typer(help="LLM 配置")
config_app.add_typer(lark_app, name="lark")
config_app.add_typer(llm_app, name="llm")
app.add_typer(config_app, name="config")
console = Console()


def _install_entrypoint_shim() -> Path:
    bin_dir = Path.home() / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "hotspot-research"
    script = f"#!/bin/sh\nexec {shlex_quote(sys.executable)} -m hotspot_cli \"$@\"\n"
    shim.write_text(script, encoding="utf-8")
    shim.chmod(0o755)
    return shim


def _ensure_entrypoint_hint() -> None:
    if shutil.which("hotspot-research") is not None or os.name == "nt":
        return
    try:
        shim = _install_entrypoint_shim()
    except OSError:
        return
    console.print(f"[yellow]已创建命令入口：{shim}。若当前 shell 仍找不到命令，请将 ~/.local/bin 加入 PATH。[/yellow]")


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


@app.command("run")
def run(
    output_dir: Path = typer.Option(Path("briefs"), "--output-dir", "-o", help="简报输出目录"),
    refresh: bool = typer.Option(False, "--refresh", help="忽略缓存，重新抓取公开信号"),
) -> None:
    """启动交互式选题智能助手，发现新兴高价值选题并生成情报简报。"""
    _ensure_entrypoint_hint()
    try:
        TopicAssistantApp(console=console).run(output_dir, refresh=refresh)
    except (HotspotError, ConfigError) as exc:
        console.print(f"[red]执行失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("brief")
def brief(
    idea: str = typer.Argument(..., help="你的选题想法，例如：中文大模型安全评测的新兴低竞争切口"),
    field: str = typer.Option("AI 通用", "--field", "-f", help="领域/行业"),
    output_dir: Path = typer.Option(Path("briefs"), "--output-dir", "-o", help="简报输出目录"),
    refresh: bool = typer.Option(False, "--refresh", help="忽略缓存，重新抓取公开信号"),
) -> None:
    """已有想法验证与增强：计算热度趋势并生成《选题情报简报》。"""
    provider = Last30DaysProvider()
    analyzer = InstructorTopicAnalyzer()
    try:
        with console.status("正在抓取公开信号并计算趋势..."):
            evidence = provider.search(idea, window_days=30, limit=24, refresh=refresh)
            trend = provider.trend(idea, refresh=refresh)
            selection = TopicSelection(
                name=idea,
                field=field,
                query=idea,
                rationale=f"用户已有选题，基于 last30days-safe 公开来源验证；趋势判断：{trend.trend}。",
                evidence=evidence,
            )
            result = analyzer.create_brief(selection, trend)
            path = BriefWriter(output_dir).save(result)
    except HotspotError as exc:
        console.print(f"[red]数据获取失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(Markdown(result.to_markdown()))
    console.print(f"[bold green]简报已保存：[/bold green][cyan]{path}[/cyan]")


@app.command("doctor")
def doctor(
    fix_entrypoint: bool = typer.Option(False, "--fix-entrypoint", help="当前 PATH 找不到命令时，自动创建 ~/.local/bin/hotspot-research shim"),
) -> None:
    """检查本机命令入口、Python 环境和飞书 CLI 可用性。"""
    command_path = shutil.which("hotspot-research")
    module_hint = "python3 -m hotspot_cli run --output-dir ./briefs"
    console.print("[bold]Hotspot Research CLI 检查[/bold]")
    if command_path:
        console.print(f"[green]命令入口可用：{command_path}[/green]")
    elif fix_entrypoint and os.name != "nt":
        try:
            shim = _install_entrypoint_shim()
        except OSError as exc:
            console.print(f"[red]创建命令入口失败：{exc}[/red]")
        else:
            console.print(f"[green]已创建命令入口：{shim}[/green]")
            console.print("如果当前 shell 仍提示 command not found，请将 ~/.local/bin 加入 PATH 后重新打开终端。")
    else:
        console.print("[yellow]当前 PATH 找不到 hotspot-research。[/yellow]")
        console.print(f"可直接使用模块入口：{module_hint}")
        console.print("也可以运行：python3 -m hotspot_cli doctor --fix-entrypoint")

    ok, message = lark_cli_status()
    if ok:
        console.print(f"[green]飞书 CLI：{message}[/green]")
    else:
        console.print(f"[yellow]飞书 CLI：{message}[/yellow]")
        console.print("安装并配置后可用 send 命令把简报文件发送到飞书群。")


@config_app.command("show")
def config_show(config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径")) -> None:
    """查看当前配置。"""
    manager = ConfigManager(config_path)
    try:
        cfg = manager.load()
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print_json(data={"lark": cfg.lark.__dict__, "config_path": str(manager.path)})


@config_app.command("reset")
def config_reset(config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径")) -> None:
    """重置配置文件。"""
    manager = ConfigManager(config_path)
    try:
        manager.reset()
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]配置已重置：{manager.path}[/green]")


@lark_app.command("setup")
def lark_setup(
    chat_id: Optional[str] = typer.Option(None, "--chat-id", help="目标飞书群 chat_id，例如 oc_xxx"),
    identity: str = typer.Option("bot", "--identity", help="bot 或 user"),
    message_template: Optional[str] = typer.Option(None, "--message-template", help="消息模板，支持 {topic}/{summary}/{report_path}"),
    upload_folder_token: Optional[str] = typer.Option(None, "--upload-folder-token", help="可选，简报上传到指定 Drive 文件夹"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """通过参数或交互式方式配置飞书推送。"""
    if chat_id is None:
        chat_id = typer.prompt("目标飞书群 chat_id，例如 oc_xxx").strip()
    if identity not in {"bot", "user"}:
        identity = typer.prompt("身份类型只能是 bot 或 user", default="bot").strip()
    if message_template is None:
        message_template = typer.prompt("消息模板", default=DEFAULT_TEMPLATE)
    if upload_folder_token is None:
        upload_folder_token = typer.prompt("Drive 文件夹 token（可留空）", default="", show_default=False)

    manager = ConfigManager(config_path)
    try:
        manager.update_lark(
            chat_id=chat_id,
            identity=identity,
            message_template=message_template,
            upload_folder_token=upload_folder_token,
        )
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]飞书配置已保存：{manager.path}[/green]")


@llm_app.command("setup")
def llm_setup(
    provider: str = typer.Option("openai", "--provider", help="openai / anthropic / ollama"),
    model: str = typer.Option("gpt-4o-mini", "--model", help="模型名，例如 gpt-4o-mini / claude-3-5-sonnet / ollama/qwen2.5"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API Key；ollama 可留空"),
    ollama_base_url: str = typer.Option("http://localhost:11434", "--ollama-base-url", help="Ollama 地址"),
) -> None:
    """配置结构化 LLM 分析。"""
    if provider not in {"openai", "anthropic", "ollama"}:
        console.print("[red]provider 只能是 openai / anthropic / ollama。[/red]")
        raise typer.Exit(code=1)
    if provider != "ollama" and not api_key:
        try:
            import questionary  # type: ignore

            api_key = questionary.password(f"请输入 {provider} API Key").ask()
        except Exception:
            api_key = typer.prompt(f"请输入 {provider} API Key", hide_input=True)
    path = save_llm_env(provider=provider, model=model, api_key=api_key or "", ollama_base_url=ollama_base_url)
    console.print(f"[green]LLM 配置已保存：{path}[/green]")


@app.command("send")
def send(
    report_path: Path = typer.Argument(..., help="要推送的本地简报文件"),
    topic: str = typer.Option("选题情报简报", "--topic"),
    summary: str = typer.Option("详见附件", "--summary"),
    channel: str = typer.Option("lark", "--channel"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """将已有简报推送到指定渠道。"""
    manager = ConfigManager(config_path)
    try:
        cfg = manager.load()
        ChannelRegistry().get(channel).send(
            chat_id=cfg.lark.chat_id,
            topic=topic,
            summary=summary,
            report_path=report_path.resolve(),
            identity=cfg.lark.identity,
            message_template=cfg.lark.message_template,
            upload_folder_token=cfg.lark.upload_folder_token,
        )
    except (ConfigError, DistributionError) as exc:
        console.print(f"[red]推送失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print("[green]推送完成。[/green]")


def main() -> None:
    app()
