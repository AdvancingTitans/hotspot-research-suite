from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .assistant_analyzer import InstructorTopicAnalyzer, plan_search_queries
from .assistant_models import TopicDiscoveryInput, TopicDirection, TopicSelection
from .assistant_settings import AssistantSettings
from .assistant_sources import Last30DaysProvider
from .assistant_store import AssistantStore
from .assistant_writer import BriefWriter
from .config import ConfigError, ConfigManager, DEFAULT_TEMPLATE
from .distribution import ChannelRegistry, DistributionError, lark_auth_status, lark_cli_status
from .hotspots import HotspotCandidate


class TopicAssistantApp:
    def __init__(
        self,
        *,
        console: Optional[Console] = None,
        settings: Optional[AssistantSettings] = None,
        provider: Optional[Last30DaysProvider] = None,
        analyzer: Optional[InstructorTopicAnalyzer] = None,
    ) -> None:
        self.console = console or Console()
        self.settings = settings or AssistantSettings()
        self.store = AssistantStore()
        self.provider = provider or Last30DaysProvider(self.store, cache_ttl_seconds=self.settings.cache_ttl_seconds)
        self.analyzer = analyzer or InstructorTopicAnalyzer(self.settings)
        self.seen_topics: list[str] = []
        self.refresh_round = 0

    def run(self, output_dir: Path, *, refresh: bool = False) -> None:
        self._render_welcome(output_dir)
        field, mode = self._ask_field()
        if not self.settings.has_llm_key():
            self.console.print("[yellow]未检测到 LLM API Key，将使用本地规则分析。运行 `hotspot-research config model setup` 可开启模型规划。[/yellow]")

        candidates = self._collect_candidates(field, mode=mode, refresh=refresh)
        discovery = self.analyzer.discover_directions(TopicDiscoveryInput(field=field, window_days=30, candidates=candidates))
        if not discovery.directions:
            self.console.print("[red]没有发现足够可靠的选题方向。可以换一个更具体的领域，或使用 --refresh 重新抓取。[/red]")
            return
        self._remember_topics(discovery.directions)
        self._render_directions(discovery.directions)
        while True:
            raw = self._ask_followup(len(discovery.directions))
            if raw.isdigit() and 1 <= int(raw) <= len(discovery.directions):
                direction = discovery.directions[int(raw) - 1]
                self._create_brief(direction, field, candidates, output_dir, refresh=refresh)
                return
            if raw.lower() in {"q", "quit", "退出"}:
                return
            if raw.lower() in {"r", "refresh", "换一批", "刷新"}:
                self.console.print("[dim]正在避开已展示主题，换一批候选方向...[/dim]")
                candidates = self._collect_candidates(field, mode=mode, refresh=True)
                discovery = self.analyzer.discover_directions(TopicDiscoveryInput(field=field, window_days=30, candidates=candidates))
            else:
                self.console.print(Panel(f"按你的追问重新检索：{raw}", title="继续分析", border_style="bright_black"))
                focus = f"{field} {raw}"
                candidates = self._collect_candidates(focus, mode="followup", refresh=True)
                discovery = self.analyzer.discover_directions(TopicDiscoveryInput(field=focus, window_days=30, candidates=candidates))
            self._remember_topics(discovery.directions)
            self._render_directions(discovery.directions)

    def _render_welcome(self, output_dir: Path) -> None:
        left = "\n".join(
            [
                "[bold]Welcome back[/bold]",
                "",
                f"[dim]Model[/dim]  {self.settings.llm_model}",
                f"[dim]Cache[/dim]  {round(self.settings.cache_ttl_seconds / 3600, 2)}h",
                f"[dim]Cwd[/dim]    {Path.cwd()}",
                f"[dim]Output[/dim] {output_dir}",
            ]
        )
        right = "\n".join(
            [
                "[bold orange3]Tips for getting started[/bold orange3]",
                "`/setup` configure model and Lark",
                "`refresh` get a different batch",
                "`1-8` create a topic brief",
                "",
                "[bold orange3]Recent activity[/bold orange3]",
                "Run `config cache show` to inspect cache",
            ]
        )
        self.console.print(
            Panel(
                Columns(
                    [
                        Panel(left, border_style="orange3", box=box.ROUNDED, title="[bold orange3]Hotspot Research[/bold orange3]"),
                        Panel(right, border_style="orange3", box=box.ROUNDED),
                    ],
                    equal=True,
                    expand=True,
                ),
                border_style="orange3",
                box=box.ROUNDED,
                title="[bold orange3]Hotspot Research[/bold orange3] [dim]topic intelligence[/dim]",
            )
        )

    def _ask_field(self) -> tuple[str, str]:
        try:
            import questionary  # type: ignore

            mode = questionary.select(
                "你现在想怎么开始？",
                choices=[
                    "我有明确领域，手动输入",
                    "没有思路，帮我推荐近期高价值 AI 选题",
                    "偏学术：优先看近期论文、评测和研究缺口",
                    "偏产业：优先看产品、开源项目和市场信号",
                ],
                default="没有思路，帮我推荐近期高价值 AI 选题",
            ).ask()
            if mode == "我有明确领域，手动输入":
                value = questionary.text("输入你关注的领域、行业或具体问题").ask()
                return (value or "AI 研究与产业趋势").strip(), "manual"
            if mode == "偏学术：优先看近期论文、评测和研究缺口":
                return "近期 AI 论文、基准评测、研究缺口", "academic"
            if mode == "偏产业：优先看产品、开源项目和市场信号":
                return "AI 产品、开源项目、产业落地", "industry"
            return "近期高价值 AI 选题", "general"
        except Exception:
            value = input("请输入想探索的领域；没有思路可直接回车：").strip()
            return value or "近期高价值 AI 选题", "manual" if value else "general"

    def _ask_followup(self, count: int) -> str:
        prompt = f"输入 1-{count} 选择方向，或直接输入追问（如：更细分、加上中国场景、和 XXX 对比），输入 q 退出"
        try:
            import questionary  # type: ignore

            value = questionary.text(prompt).ask()
            return (value or "").strip()
        except Exception:
            return input(prompt + "\n> ").strip()

    def _collect_candidates(self, field: str, *, mode: str, refresh: bool) -> list[HotspotCandidate]:
        if refresh:
            self.refresh_round += 1
        queries = plan_search_queries(settings=self.settings, user_input=field, mode=mode, avoid=self.seen_topics, limit=8 if refresh else 5)
        if not queries:
            queries = _normalize_field_queries(field)
        if refresh:
            queries = _refresh_query_variants(queries, self.refresh_round)
        query_label = " / ".join(queries[:3]) + (" ..." if len(queries) > 3 else "")
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console) as progress:
            task = progress.add_task(f"Planning search · {query_label}", total=None)
            if len(queries) == 1:
                candidates = self.provider.search(queries[0], window_days=30, limit=72 if refresh else 36, refresh=refresh)
            else:
                candidates = self.provider.search_many(queries, window_days=30, limit=72 if refresh else 36, refresh=refresh)
            progress.update(task, description="Scoring evidence")
        fresh = _exclude_seen(_viable_candidates(candidates), self.seen_topics)
        if refresh and len(fresh) < 5:
            broad_queries = _refresh_query_variants(_normalize_field_queries(field), self.refresh_round + 3)
            broad = self.provider.search_many(broad_queries, window_days=30, limit=72, refresh=True)
            fresh = _unique_candidates(fresh + _exclude_seen(_viable_candidates(broad), self.seen_topics))
        return fresh

    def _render_directions(self, directions: list[TopicDirection]) -> None:
        table = Table(title="新兴高价值选题方向（5~8 个）", show_lines=True)
        table.add_column("序号", justify="right", style="cyan", width=4)
        table.add_column("选题名称", style="bold", min_width=18)
        table.add_column("为什么现在热门 + 数据证据", min_width=28)
        table.add_column("竞争程度信号", min_width=22)
        table.add_column("近期代表性热点", min_width=26)
        for idx, direction in enumerate(directions, 1):
            reps = "\n".join(f"- {item.title}（{item.source}）" for item in direction.representative_items[:3])
            table.add_row(str(idx), direction.name, direction.why_now, direction.competition_signal, reps)
        self.console.print(table)

    def _create_brief(self, direction: TopicDirection, field: str, candidates: list[HotspotCandidate], output_dir: Path, *, refresh: bool) -> None:
        query = direction.name
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console) as progress:
            task = progress.add_task("正在计算 7/30/30~60 天趋势", total=None)
            trend = self.provider.trend(query, refresh=refresh)
            progress.update(task, description="正在生成《选题情报简报》")
            evidence = _evidence_for_direction(direction, candidates)
            selection = TopicSelection(name=direction.name, field=field, query=query, rationale=direction.why_now, evidence=evidence)
            brief = self.analyzer.create_brief(selection, trend)
            path = BriefWriter(output_dir).save(brief)
            self.store.add_history("brief", brief.topic, {"path": str(path), "topic": brief.topic})
        self.console.print(Markdown(brief.to_markdown()))
        self.console.print(f"[bold green]简报已保存：[/bold green][cyan]{path}[/cyan]")
        self._offer_lark_send(path=path, topic=brief.topic, summary=brief.timeliness[:180])
        self.console.print(Panel("下一步可以重新运行并输入：细化角度 / 找更细分方向 / 验证我的想法 / 加上中国场景", title="继续探索建议", border_style="bright_black"))

    def _offer_lark_send(self, *, path: Path, topic: str, summary: str) -> None:
        if not _ask_yes_no("是否发送到飞书群？", default=False):
            return
        ok, message = lark_cli_status()
        if not ok:
            self.console.print(f"[yellow]{message}[/yellow]")
            self.console.print("安装后运行：`hotspot-research config lark auth --init`，再重新发送。")
            return
        auth_ok, auth_message = lark_auth_status()
        if not auth_ok:
            self.console.print(f"[yellow]{auth_message}[/yellow]")
            self.console.print("请先运行：`hotspot-research config lark auth --init`")
            return
        manager = ConfigManager()
        config = manager.load()
        if not config.lark.chat_id:
            self.console.print("[yellow]尚未配置飞书群 chat_id。请先把应用机器人加入目标群，然后复制群 ID。[/yellow]")
            chat_id = _ask_text("请输入飞书群 chat_id（例如 oc_xxx），留空则跳过")
            if not chat_id:
                self.console.print("已跳过发送。之后可运行：`hotspot-research config lark setup --chat-id oc_xxx`")
                return
            identity = _ask_text("发送身份 bot/user", default="bot") or "bot"
            try:
                config = manager.update_lark(chat_id=chat_id, identity=identity, message_template=DEFAULT_TEMPLATE)
            except ConfigError as exc:
                self.console.print(f"[red]飞书配置保存失败：{exc}[/red]")
                return
        try:
            ChannelRegistry().get("lark").send(
                chat_id=config.lark.chat_id,
                topic=topic,
                summary=summary,
                report_path=path.resolve(),
                identity=config.lark.identity,
                message_template=config.lark.message_template,
                upload_folder_token=config.lark.upload_folder_token,
            )
        except DistributionError as exc:
            self.console.print(f"[red]飞书发送失败：{exc}[/red]")
            self.console.print("可运行 `hotspot-research config lark doctor` 查看授权状态。")
            return
        self.console.print("[green]已发送到飞书群。[/green]")

    def _remember_topics(self, directions: list[TopicDirection]) -> None:
        for direction in directions:
            self.seen_topics.append(direction.name)
            self.seen_topics.extend(item.title for item in direction.representative_items)
        self.seen_topics = _unique(self.seen_topics)[-60:]


def _normalize_field_queries(field: str) -> list[str]:
    text = field.strip()
    if text in {"随便推荐", "AI 通用", "ai 通用", "只看 cs.AI", "近期高价值 AI 选题", "AI 研究与产业趋势"}:
        return [
            "LLM agents benchmark arxiv",
            "multimodal reasoning benchmark arxiv",
            "AI coding agents GitHub",
            "AI agent evaluation",
            "open source AI agents",
        ]
    if text == "近期 AI 论文、基准评测、研究缺口":
        return [
            "LLM benchmark evaluation arxiv",
            "AI agent benchmark arxiv",
            "multimodal reasoning arxiv",
            "LLM safety evaluation arxiv",
        ]
    if text == "AI 产品、开源项目、产业落地":
        return [
            "AI agents open source GitHub",
            "AI coding agent GitHub",
            "browser agent GitHub",
            "AI product launch agent",
        ]
    expanded = [text]
    lowered = text.lower()
    expansions = {
        "大模型智能体": ["LLM agents benchmark arxiv", "AI agent evaluation", "open source AI agents", "browser agent GitHub"],
        "智能体": ["LLM agents benchmark arxiv", "AI agent evaluation", "agent memory arxiv", "open source AI agents"],
        "多模态": ["multimodal reasoning benchmark arxiv", "multimodal LLM evaluation arxiv", "vision language model benchmark"],
        "中文大模型安全": ["Chinese LLM safety evaluation arxiv", "LLM safety benchmark Chinese", "jailbreak defense LLM arxiv"],
        "大模型安全": ["LLM safety evaluation arxiv", "AI safety benchmark", "jailbreak defense LLM arxiv"],
        "具身智能": ["embodied AI agents arxiv", "robotics foundation model arxiv", "vision language action model"],
        "ai 编程": ["AI coding agent GitHub", "code agent benchmark arxiv", "software engineering agent benchmark"],
        "代码智能体": ["AI coding agent GitHub", "code agent benchmark arxiv", "software engineering agent benchmark"],
        "评测": ["LLM benchmark evaluation arxiv", "AI agent benchmark arxiv", "LLM evaluation benchmark"],
    }
    for keyword, queries in expansions.items():
        if keyword in text or keyword in lowered:
            expanded.extend(queries)
    return _unique(expanded)[:5]


def _refresh_query_variants(queries: list[str], round_no: int) -> list[str]:
    angles = [
        "emerging benchmark",
        "new arxiv",
        "open source GitHub",
        "evaluation dataset",
        "research gap",
        "product launch",
        "developer discussion",
        "China application",
    ]
    offset = (round_no * 3) % len(angles)
    rotated = angles[offset:] + angles[:offset]
    expanded: list[str] = []
    for idx, query in enumerate(queries):
        expanded.append(query)
        expanded.append(f"{query} {rotated[idx % len(rotated)]}")
    return _unique(expanded)[:10]


def _evidence_for_direction(direction: TopicDirection, candidates: list[HotspotCandidate]) -> list[HotspotCandidate]:
    urls = {item.url for item in direction.representative_items if item.url}
    matched = [item for item in candidates if any(url in item.source_urls for url in urls)]
    if matched:
        return matched[:8]
    names = [item.title for item in direction.representative_items]
    return [item for item in candidates if item.title in names][:8]


def _exclude_seen(candidates: list[HotspotCandidate], seen_topics: list[str]) -> list[HotspotCandidate]:
    if not seen_topics:
        return candidates
    seen = " ".join(seen_topics).lower()
    fresh = [item for item in candidates if not _candidate_seen(item, seen)]
    return fresh


def _viable_candidates(candidates: list[HotspotCandidate]) -> list[HotspotCandidate]:
    return [item for item in candidates if item.score > 0 and item.source_urls]


def _unique_candidates(candidates: list[HotspotCandidate]) -> list[HotspotCandidate]:
    seen: set[str] = set()
    result: list[HotspotCandidate] = []
    for item in candidates:
        key = (item.source_urls[0] if item.source_urls else item.title).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _candidate_seen(item: HotspotCandidate, seen: str) -> bool:
    text = f"{item.title} {item.domain}".lower()
    if item.title.lower() in seen or item.domain.lower() in seen:
        return True
    tokens = [token.lower() for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{7,}|[\u4e00-\u9fff]{4,}", text)]
    return any(token in seen for token in tokens[:6])


def _ask_yes_no(message: str, default: bool = True) -> bool:
    try:
        import questionary  # type: ignore

        answer = questionary.confirm(message, default=default).ask()
        return bool(answer)
    except Exception:
        suffix = "Y/n" if default else "y/N"
        raw = input(f"{message} [{suffix}] ").strip().lower()
        if not raw:
            return default
        return raw in {"y", "yes", "是", "好", "确认"}


def _ask_text(message: str, default: str = "") -> str:
    try:
        import questionary  # type: ignore

        value = questionary.text(message, default=default).ask()
        return (value or "").strip()
    except Exception:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{message}{suffix}\n> ").strip()
        return raw or default


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
