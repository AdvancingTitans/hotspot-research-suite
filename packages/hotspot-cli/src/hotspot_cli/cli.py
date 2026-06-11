from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import ConfigError, ConfigManager, DEFAULT_TEMPLATE
from .distribution import ChannelRegistry, DistributionError
from .hotspots import HotspotCandidate, HotspotError, HotspotService
from .report import ReportError, ReportGenerator


app = typer.Typer(help="交互式热点研究报告 CLI")
config_app = typer.Typer(help="配置管理")
lark_app = typer.Typer(help="飞书配置")
config_app.add_typer(lark_app, name="lark")
app.add_typer(config_app, name="config")
console = Console()


def _print_candidates(title: str, items: list[HotspotCandidate]) -> None:
    table = Table(title=title, show_lines=True)
    table.add_column("序号", justify="right", style="cyan", width=4)
    table.add_column("选题/领域", style="bold")
    table.add_column("评分", justify="right")
    table.add_column("依据")
    for idx, item in enumerate(items, 1):
        table.add_row(str(idx), item.title, f"{item.score:.0f}", item.evidence)
    console.print(table)


def _choose_from_list(items: list[HotspotCandidate], *, refresh_word: str = "refresh") -> Union[int, str]:
    while True:
        raw = typer.prompt(f"输入序号确认，或输入 {refresh_word} 换一批").strip()
        if raw.lower() == refresh_word:
            return refresh_word
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(items):
                return idx - 1
        console.print("[red]输入无效。请输入列表中的序号，或 refresh。[/red]")


def _resolve_domain(service: HotspotService) -> str:
    raw = typer.prompt("你是否有想要研究的指定领域？有则直接输入领域；没有请直接回车", default="", show_default=False).strip()
    if raw:
        return raw

    refresh_index = 0
    while True:
        console.print("[bold]正在使用 last30days-safe 拉取主流研究领域...[/bold]")
        domains = service.top_domains(refresh_index=refresh_index)
        if not domains:
            raise HotspotError("未获取到热门领域。请检查网络，或直接输入指定领域。")
        _print_candidates("最近30天主流研究领域 TOP10", domains)
        choice = _choose_from_list(domains)
        if choice == "refresh":
            refresh_index += 1
            continue
        return domains[int(choice)].domain


def _resolve_hotspot(service: HotspotService, domain: str) -> HotspotCandidate:
    refresh_index = 0
    while True:
        console.print(f"[bold]正在拉取「{domain}」近30天客观热点 TOP10...[/bold]")
        hotspots = service.top_hotspots(domain, refresh_index=refresh_index)
        if not hotspots:
            raise HotspotError("未获取到符合规则的客观热点。可输入 refresh 再试，或换一个领域。")
        _print_candidates(f"{domain} 近30天客观热点 TOP10", hotspots)
        choice = _choose_from_list(hotspots)
        if choice == "refresh":
            refresh_index += 1
            continue
        return hotspots[int(choice)]


@app.command("run")
def run(
    output_dir: Path = typer.Option(Path("reports"), "--output-dir", "-o", help="报告输出目录"),
    push_lark: bool = typer.Option(False, "--push-lark", help="报告生成后推送到飞书"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径，支持 .json/.yaml"),
    language: str = typer.Option("zh", "--language", help="报告语言：zh/en"),
) -> None:
    """启动交互式问答，选择领域和热点，生成报告并可推送飞书。"""
    console.print(Panel.fit("Hotspot Research CLI", subtitle="last30days-safe + hotspot-research"))
    config_manager = ConfigManager(config_path)
    service = HotspotService()
    try:
        domain = _resolve_domain(service)
        candidate = _resolve_hotspot(service, domain)
        console.print(f"[green]已确认选题：{candidate.title}[/green]")
        result = ReportGenerator(output_dir=output_dir).generate(candidate, language=language)
    except (HotspotError, ReportError, ConfigError) as exc:
        console.print(f"[red]执行失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print("[bold green]报告已生成[/bold green]")
    console.print(f"Markdown: [cyan]{result.markdown_path}[/cyan]")
    console.print(f"HTML: [cyan]{result.html_path}[/cyan]")
    if result.pdf_path:
        console.print(f"PDF: [cyan]{result.pdf_path}[/cyan]")
    else:
        console.print("[yellow]PDF 未生成；请检查 WeasyPrint/native 依赖。[/yellow]")

    if push_lark:
        try:
            cfg = config_manager.load()
            report_for_push = result.pdf_path or result.markdown_path
            ChannelRegistry().get("lark").send(
                chat_id=cfg.lark.chat_id,
                topic=result.topic,
                summary=result.summary,
                report_path=report_for_push,
                identity=cfg.lark.identity,
                message_template=cfg.lark.message_template,
                upload_folder_token=cfg.lark.upload_folder_token,
            )
            console.print("[green]已调用 lark-cli 推送飞书。[/green]")
        except (ConfigError, DistributionError) as exc:
            console.print(f"[red]飞书推送失败：{exc}[/red]")
            console.print("[yellow]排查：确认 lark-cli 已 config init、bot/user 有 IM 与 Drive 权限、chat_id 正确。[/yellow]")
            raise typer.Exit(code=2) from exc


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
    upload_folder_token: Optional[str] = typer.Option(None, "--upload-folder-token", help="可选，报告上传到指定 Drive 文件夹"),
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


@app.command("send")
def send(
    report_path: Path = typer.Argument(..., help="要推送的本地报告文件"),
    topic: str = typer.Option("研究报告", "--topic"),
    summary: str = typer.Option("详见附件", "--summary"),
    channel: str = typer.Option("lark", "--channel"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """将已有报告推送到指定渠道。"""
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
