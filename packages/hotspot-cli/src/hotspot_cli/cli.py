from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import shutil
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown

from .assistant_analyzer import InstructorTopicAnalyzer
from .assistant_models import TopicSelection
from .assistant_settings import save_llm_env, set_user_env_value
from .assistant_sources import Last30DaysProvider
from .assistant_store import AssistantStore
from .assistant_writer import BriefWriter
from .config import ConfigError, ConfigManager, DEFAULT_TEMPLATE
from .conversation_app import AdaptiveTopicAssistantApp
from .distribution import ChannelRegistry, DistributionError, lark_cli_status
from .hotspots import HotspotError
from .model_config import fetch_model_ids, prepare_model_config, verify_model_config
from .model_presets import MODEL_PRESETS, preset_choices


app = typer.Typer(help="交互式选题智能助手", rich_markup_mode="rich")
config_app = typer.Typer(help="配置管理")
lark_app = typer.Typer(help="飞书配置")
llm_app = typer.Typer(help="模型配置")
cache_app = typer.Typer(help="缓存配置")
profile_app = typer.Typer(help="用户选题画像")
config_app.add_typer(lark_app, name="lark")
config_app.add_typer(llm_app, name="llm")
config_app.add_typer(llm_app, name="model")
config_app.add_typer(cache_app, name="cache")
config_app.add_typer(profile_app, name="profile")
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
    command_path = shutil.which("hotspot-research")
    if os.name == "nt":
        return
    if command_path is not None:
        path = Path(command_path)
        expected = Path.home() / ".local" / "bin" / "hotspot-research"
        if path == expected:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return
            head = "\n".join(text.splitlines()[:2])
            if sys.executable not in text and "exec " not in head:
                try:
                    shim = _install_entrypoint_shim()
                except OSError:
                    return
                console.print(f"[yellow]已刷新旧命令入口：{shim}[/yellow]")
        return
    try:
        shim = _install_entrypoint_shim()
    except OSError:
        return
    console.print(f"[yellow]已创建命令入口：{shim}。若当前 shell 仍找不到命令，请将 ~/.local/bin 加入 PATH。[/yellow]")


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _run_interactive(argv: list[str]) -> int:
    console.print(f"[dim]$ {' '.join(argv)}[/dim]")
    return subprocess.run(argv, check=False).returncode


def _ask_yes_no(message: str, default: bool = True) -> bool:
    try:
        import questionary  # type: ignore

        answer = questionary.confirm(message, default=default).ask()
        return bool(answer)
    except Exception:
        suffix = "Y/n" if default else "y/N"
        raw = typer.prompt(f"{message} [{suffix}]", default="", show_default=False).strip().lower()
        if not raw:
            return default
        return raw in {"y", "yes", "是", "好", "确认"}


def _select_model_preset(default: str = "deepseek") -> str:
    try:
        import questionary  # type: ignore

        choices = [f"{key}｜{label}" for key, label in preset_choices()]
        selected = questionary.select("请选择模型服务商", choices=choices, default=f"{default}｜{MODEL_PRESETS[default].label}：{MODEL_PRESETS[default].note}").ask()
        return str(selected).split("｜", 1)[0]
    except Exception:
        console.print("可选模型服务商：")
        for key, label in preset_choices():
            console.print(f"  {key}: {label}")
        return typer.prompt("请输入服务商", default=default).strip()


def _setup_model_interactive(
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    ollama_base_url: str = "http://localhost:11434",
    verify: bool = True,
) -> Path:
    provider = provider or _select_model_preset()
    preset = MODEL_PRESETS.get(provider)
    if preset is None:
        raise ConfigError(f"未知模型服务商：{provider}。可运行 `hotspot-research config model list` 查看支持项。")
    model = model or preset.model
    base_url = base_url if base_url is not None else preset.base_url
    if provider in {"custom", "openai-compatible"} and not base_url:
        base_url = typer.prompt("请输入 OpenAI-Compatible Base URL，例如 https://api.example.com/v1").strip()
    if provider in {"custom", "openai-compatible"} and model in {"", "openai/your-model-name", "your-model-name"}:
        model = typer.prompt("请输入真实模型名，例如 openai/gpt-4o-mini 或 openai/your-deployment-id").strip()
    if provider != "ollama" and api_key is None:
        key_label = preset.api_key_name or "API Key"
        try:
            import questionary  # type: ignore

            api_key = questionary.password(f"请输入 {key_label}（不会显示；留空则尝试读取已有环境变量）").ask()
        except Exception:
            api_key = typer.prompt(f"请输入 {key_label}（留空则尝试读取已有环境变量）", hide_input=True, default="", show_default=False)
    try:
        plan = prepare_model_config(
            provider=provider,
            model=model,
            api_key=api_key or None,
            base_url=base_url,
            ollama_base_url=ollama_base_url,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    for warning in plan.warnings:
        console.print(f"[yellow]{warning}[/yellow]")
    if verify:
        with console.status("正在验证模型配置..."):
            check = verify_model_config(plan)
        if not check.ok:
            raise ConfigError(f"{check.message} {check.detail}".strip())
        console.print(f"[green]{check.message}[/green]")
    path = save_llm_env(
        provider=plan.provider,
        model=plan.model,
        api_key=plan.api_key,
        base_url=plan.base_url,
        ollama_base_url=plan.ollama_base_url,
    )
    return path


def _lark_cli_or_raise() -> None:
    ok, message = lark_cli_status()
    if not ok:
        raise ConfigError(message + "。推荐安装命令：`npx @larksuite/cli@latest install`，或查看 https://github.com/larksuite/cli。")


def _print_lark_setup_notes() -> None:
    console.print("[bold]飞书发送简报需要三步：[/bold]")
    console.print("1. 安装 lark-cli：npx @larksuite/cli@latest install")
    console.print("2. 初始化应用配置：lark-cli config init --new")
    console.print("3. 用户身份授权：lark-cli auth login --recommend")
    console.print("[dim]参考 larksuite/cli：官方推荐 config init 后 auth login --recommend，再用 auth status 验证。[/dim]")


@app.command("run")
def run(
    output_dir: Path = typer.Option(Path("briefs"), "--output-dir", "-o", help="简报输出目录"),
    refresh: bool = typer.Option(False, "--refresh", help="忽略缓存，重新抓取公开信号"),
) -> None:
    """启动交互式选题智能助手，发现新兴高价值选题并生成情报简报。"""
    _ensure_entrypoint_hint()
    try:
        AdaptiveTopicAssistantApp(console=console).run(output_dir, refresh=refresh)
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


@app.command("setup")
def setup(
    skip_model: bool = typer.Option(False, "--skip-model", help="跳过模型配置"),
    skip_lark: bool = typer.Option(False, "--skip-lark", help="跳过飞书配置"),
) -> None:
    """首次运行向导：配置模型，并可选完成飞书 CLI 初始化和授权。"""
    console.print("[bold]Hotspot Research 首次运行向导[/bold]")
    if not skip_model:
        try:
            path = _setup_model_interactive()
        except ConfigError as exc:
            console.print(f"[red]模型配置失败：{exc}[/red]")
            raise typer.Exit(code=1) from exc
        console.print(f"[green]模型配置已保存：{path}[/green]")
    if not skip_lark and _ask_yes_no("是否现在配置飞书群推送？", default=False):
        try:
            _configure_lark_interactive()
        except ConfigError as exc:
            console.print(f"[red]飞书配置失败：{exc}[/red]")
            _print_lark_setup_notes()
            raise typer.Exit(code=1) from exc
    console.print("[green]配置完成。可以运行：hotspot-research run[/green]")


@app.command("doctor")
def doctor(
    fix_entrypoint: bool = typer.Option(False, "--fix-entrypoint", help="当前 PATH 找不到命令时，自动创建 ~/.local/bin/hotspot-research shim"),
) -> None:
    """检查本机命令入口、Python 环境和飞书 CLI 可用性。"""
    command_path = shutil.which("hotspot-research")
    module_hint = "python3 -m hotspot_cli run --output-dir ./briefs"
    console.print("[bold]Hotspot Research CLI 检查[/bold]")
    if command_path and not fix_entrypoint:
        console.print(f"[green]命令入口可用：{command_path}[/green]")
    elif fix_entrypoint and os.name != "nt":
        try:
            shim = _install_entrypoint_shim()
        except OSError as exc:
            console.print(f"[red]创建命令入口失败：{exc}[/red]")
        else:
            console.print(f"[green]已刷新命令入口：{shim}[/green]")
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
    console.print("模型配置：运行 `hotspot-research config model show` 查看当前模型，或运行 `hotspot-research setup` 重新配置。")


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


def _configure_lark_interactive(config_path: Optional[Path] = None) -> None:
    _lark_cli_or_raise()
    _print_lark_setup_notes()
    if _ask_yes_no("是否运行 `lark-cli config init --new` 初始化飞书应用配置？", default=False):
        code = _run_interactive(["lark-cli", "config", "init", "--new"])
        if code != 0:
            raise ConfigError("lark-cli config init 执行失败。请根据终端提示完成应用配置后重试。")
    if _ask_yes_no("是否运行 `lark-cli auth login --recommend` 获取用户授权？", default=False):
        code = _run_interactive(["lark-cli", "auth", "login", "--recommend"])
        if code != 0:
            raise ConfigError("lark-cli auth login 执行失败。请确认浏览器授权已完成。")
    chat_id = typer.prompt("目标飞书群 chat_id，例如 oc_xxx（可稍后再填）", default="", show_default=False).strip()
    identity = typer.prompt("发送身份：bot 或 user", default="bot").strip()
    if chat_id:
        ConfigManager(config_path).update_lark(chat_id=chat_id, identity=identity, message_template=DEFAULT_TEMPLATE)
        console.print("[green]飞书群配置已保存。[/green]")
    _run_interactive(["lark-cli", "auth", "status"])


@lark_app.command("auth")
def lark_auth(
    init: bool = typer.Option(False, "--init", help="先运行 lark-cli config init --new"),
    recommend: bool = typer.Option(True, "--recommend/--no-recommend", help="使用 lark-cli 推荐授权范围"),
    scope: Optional[str] = typer.Option(None, "--scope", help="精确授权 scope，例如 im:message"),
    no_wait: bool = typer.Option(False, "--no-wait", help="发起授权后立即返回，便于复制浏览器授权链接"),
    chat_id: Optional[str] = typer.Option(None, "--chat-id", help="授权后顺便保存目标飞书群 chat_id"),
    identity: str = typer.Option("bot", "--identity", help="发送身份：bot 或 user"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """按 lark-cli 官方流程初始化配置、登录授权，并保存群聊发送配置。"""
    try:
        _lark_cli_or_raise()
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        _print_lark_setup_notes()
        raise typer.Exit(code=1) from exc
    if init:
        code = _run_interactive(["lark-cli", "config", "init", "--new"])
        if code != 0:
            raise typer.Exit(code=1)
    argv = ["lark-cli", "auth", "login"]
    if scope:
        argv.extend(["--scope", scope])
    elif recommend:
        argv.append("--recommend")
    if no_wait:
        argv.append("--no-wait")
    code = _run_interactive(argv)
    if code != 0:
        raise typer.Exit(code=1)
    if chat_id:
        try:
            ConfigManager(config_path).update_lark(chat_id=chat_id, identity=identity)
        except ConfigError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        console.print(f"[green]飞书群配置已保存：{chat_id}[/green]")


@lark_app.command("doctor")
def lark_doctor() -> None:
    """检查 lark-cli 安装、版本和当前授权状态。"""
    ok, message = lark_cli_status()
    if not ok:
        console.print(f"[red]{message}[/red]")
        _print_lark_setup_notes()
        raise typer.Exit(code=1)
    console.print(f"[green]{message}[/green]")
    _run_interactive(["lark-cli", "auth", "status"])


@llm_app.command("list")
def model_list() -> None:
    """列出内置模型服务商预设。"""
    for key, preset in MODEL_PRESETS.items():
        console.print(f"[bold]{key}[/bold] - {preset.label}")
        console.print(f"  默认模型：{preset.model}")
        if preset.base_url:
            console.print(f"  Base URL：{preset.base_url}")
        if preset.api_key_name:
            console.print(f"  Key 名称：{preset.api_key_name}")
        console.print(f"  说明：{preset.note}")


@llm_app.command("show")
def model_show() -> None:
    """查看当前模型配置，不显示密钥内容。"""
    from .assistant_settings import AssistantSettings

    settings = AssistantSettings()
    console.print_json(
        data={
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "base_url": settings.llm_base_url or settings.ollama_base_url if settings.llm_provider == "ollama" else settings.llm_base_url,
            "has_key": settings.has_llm_key(),
        }
    )


@llm_app.command("setup")
def llm_setup(
    provider: Optional[str] = typer.Option(None, "--provider", help="deepseek / openai / anthropic / openrouter / siliconflow / moonshot / qwen / ark / ollama / custom"),
    model: Optional[str] = typer.Option(None, "--model", help="模型名；留空使用该服务商推荐默认值"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API Key；ollama 可留空"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="OpenAI-Compatible Base URL"),
    ollama_base_url: str = typer.Option("http://localhost:11434", "--ollama-base-url", help="Ollama 地址"),
    verify: bool = typer.Option(True, "--verify/--no-verify", help="保存前做真实模型连通性验证"),
) -> None:
    """配置结构化模型分析。"""
    try:
        path = _setup_model_interactive(provider=provider, model=model, api_key=api_key, base_url=base_url, ollama_base_url=ollama_base_url, verify=verify)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]模型配置已保存：{path}[/green]")


@llm_app.command("verify")
def model_verify() -> None:
    """验证当前模型配置是否能列模型并完成一次最小对话。"""
    from .assistant_settings import AssistantSettings

    settings = AssistantSettings()
    try:
        plan = prepare_model_config(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            ollama_base_url=settings.ollama_base_url,
        )
    except ValueError as exc:
        console.print(f"[red]模型配置无效：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    for warning in plan.warnings:
        console.print(f"[yellow]{warning}[/yellow]")
    with console.status("正在验证模型配置..."):
        result = verify_model_config(plan)
    if not result.ok:
        console.print(f"[red]{result.message}[/red]")
        if result.detail:
            console.print(f"[yellow]{result.detail}[/yellow]")
        raise typer.Exit(code=1)
    console.print(f"[green]{result.message}[/green]")
    if result.detail:
        console.print(f"[dim]{result.detail}[/dim]")


@llm_app.command("models")
def model_models(
    provider: Optional[str] = typer.Option(None, "--provider", help="要查询的 provider；默认使用当前配置"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API Key；留空复用当前配置或环境变量"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="OpenAI-Compatible Base URL；preset 可留空"),
    limit: int = typer.Option(30, "--limit", help="最多展示模型数"),
) -> None:
    """从 provider 拉取可用模型列表，避免填错模型名。"""
    from .assistant_settings import AssistantSettings

    settings = AssistantSettings()
    provider = provider or settings.llm_provider
    preset = MODEL_PRESETS.get(provider)
    if preset is None:
        console.print(f"[red]未知 provider：{provider}[/red]")
        raise typer.Exit(code=1)
    try:
        plan = prepare_model_config(
            provider=provider,
            model=preset.model,
            api_key=api_key or (settings.llm_api_key if provider == settings.llm_provider else None),
            base_url=base_url if base_url is not None else (settings.llm_base_url if provider == settings.llm_provider else preset.base_url),
            ollama_base_url=settings.ollama_base_url,
        )
        ids = fetch_model_ids(plan, limit=limit)
    except Exception as exc:
        console.print(f"[red]获取模型列表失败：{str(exc)[:500]}[/red]")
        raise typer.Exit(code=1) from exc
    if not ids:
        console.print("[yellow]未获取到模型列表。该 provider 可能不支持 /models，可直接用官方控制台中的模型名。[/yellow]")
        return
    for item in ids:
        console.print(item)


@llm_app.command("doctor")
def model_doctor() -> None:
    """诊断模型配置常见问题，并给出可直接执行的修复命令。"""
    from .assistant_settings import AssistantSettings

    settings = AssistantSettings()
    console.print("[bold]模型配置诊断[/bold]")
    console.print_json(
        data={
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "base_url": settings.llm_base_url,
            "has_key": settings.has_llm_key(),
            "cache_ttl_seconds": settings.cache_ttl_seconds,
        }
    )
    if settings.llm_provider == "ark":
        if settings.llm_base_url and "/api/coding" in settings.llm_base_url:
            console.print("[red]Ark base_url 使用了 /api/coding，这是错误入口。[/red]")
            console.print("修复：hotspot-research config model setup --provider ark")
        if settings.llm_model in {"", "openai/your-model-name", "your-model-name"}:
            console.print("[red]当前模型名是占位值。[/red]")
            console.print("修复：hotspot-research config model setup --provider ark --model openai/doubao-1-5-lite-32k-250115")
    model_verify()


@cache_app.command("show")
def cache_show() -> None:
    """查看缓存文件和缓存超时时间。"""
    from .assistant_settings import AssistantSettings

    settings = AssistantSettings()
    store = AssistantStore()
    console.print_json(
        data={
            "cache_path": str(store.path),
            "cache_available": store.available,
            "cache_ttl_seconds": settings.cache_ttl_seconds,
            "cache_ttl_hours": round(settings.cache_ttl_seconds / 3600, 2),
        }
    )


@cache_app.command("set")
def cache_set(
    ttl_seconds: Optional[int] = typer.Option(None, "--ttl-seconds", help="缓存有效期，秒"),
    ttl_hours: Optional[float] = typer.Option(None, "--ttl-hours", help="缓存有效期，小时"),
) -> None:
    """设置 last30days-safe 查询缓存超时时间。"""
    if ttl_seconds is None:
        if ttl_hours is None:
            ttl_hours = typer.prompt("缓存有效期（小时）", default=6.0)
        ttl_seconds = int(float(ttl_hours) * 3600)
    if ttl_seconds < 0:
        console.print("[red]缓存 TTL 不能为负数。[/red]")
        raise typer.Exit(code=1)
    path = set_user_env_value("HOTSPOT_CACHE_TTL_SECONDS", str(ttl_seconds))
    console.print(f"[green]缓存 TTL 已保存：{ttl_seconds} 秒（{round(ttl_seconds / 3600, 2)} 小时）[/green]")
    console.print(f"[dim]{path}[/dim]")


@cache_app.command("clear")
def cache_clear() -> None:
    """清理本地查询缓存；用于缓存损坏、权限异常或希望强制重抓时。"""
    store = AssistantStore()
    try:
        if store.path.exists():
            store.path.unlink()
        console.print(f"[green]缓存已清理：{store.path}[/green]")
    except OSError as exc:
        console.print(f"[red]缓存清理失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc


@profile_app.command("show")
def profile_show() -> None:
    """查看本地保存的用户选题画像。"""
    from .conversation_models import ResearchProfile

    store = AssistantStore()
    data = store.get_profile()
    if not data:
        console.print("[yellow]当前没有保存的选题画像。运行 `hotspot-research run` 完成一次自然对话后会自动保存。[/yellow]")
        return
    try:
        profile = ResearchProfile.model_validate(data)
    except Exception as exc:
        console.print(f"[red]画像数据无法解析：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print("[bold]本地选题画像[/bold]")
    console.print(Markdown(profile.summary()))
    console.print(f"[dim]存储位置：{store.path}[/dim]")


@profile_app.command("clear")
def profile_clear() -> None:
    """清除本地保存的用户选题画像，下次 run 会重新自然对话生成。"""
    store = AssistantStore()
    store.clear_profile()
    console.print("[green]已清除本地选题画像。下次运行 `hotspot-research run` 会重新生成。[/green]")


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
