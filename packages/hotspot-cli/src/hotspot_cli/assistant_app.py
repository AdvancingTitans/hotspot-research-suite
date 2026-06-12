from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .assistant_analyzer import InstructorTopicAnalyzer
from .assistant_models import TopicDiscoveryInput, TopicDirection, TopicSelection
from .assistant_settings import AssistantSettings
from .assistant_sources import Last30DaysProvider
from .assistant_store import AssistantStore
from .assistant_writer import BriefWriter
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

    def run(self, output_dir: Path, *, refresh: bool = False) -> None:
        self.console.print(Panel.fit("交互式选题智能助手", subtitle="用数据说话，降低选题不确定性"))
        field = self._ask_field()
        if not self.settings.has_llm_key():
            self.console.print("[yellow]未检测到 LLM API Key，将使用本地规则分析；后续可通过 .env 配置 HOTSPOT_OPENAI_API_KEY 等。[/yellow]")

        candidates = self._collect_candidates(field, refresh=refresh)
        discovery = self.analyzer.discover_directions(TopicDiscoveryInput(field=field, window_days=30, candidates=candidates))
        if not discovery.directions:
            self.console.print("[red]没有发现足够可靠的选题方向。可以换一个更具体的领域，或使用 --refresh 重新抓取。[/red]")
            return
        self._render_directions(discovery.directions)
        while True:
            raw = self._ask_followup(len(discovery.directions))
            if raw.isdigit() and 1 <= int(raw) <= len(discovery.directions):
                direction = discovery.directions[int(raw) - 1]
                self._create_brief(direction, field, candidates, output_dir, refresh=refresh)
                return
            if raw.lower() in {"q", "quit", "退出"}:
                return
            self.console.print(Panel(f"我会按你的追问重新聚焦：{raw}", title="继续分析"))
            filtered = self._filter_by_instruction(candidates, raw)
            discovery = self.analyzer.discover_directions(TopicDiscoveryInput(field=f"{field} {raw}", window_days=30, candidates=filtered or candidates))
            self._render_directions(discovery.directions)

    def _ask_field(self) -> str:
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
                value = questionary.text("请输入你感兴趣的领域，例如：大模型智能体 / 多模态推理 / 中文大模型安全 / 具身智能").ask()
                return (value or "AI 研究与产业趋势").strip()
            if mode == "偏学术：优先看近期论文、评测和研究缺口":
                return "近期 AI 论文、基准评测、研究缺口"
            if mode == "偏产业：优先看产品、开源项目和市场信号":
                return "AI 产品、开源项目、产业落地"
            return "近期高价值 AI 选题"
        except Exception:
            return input("请输入想探索的领域；没有思路可直接回车：").strip() or "近期高价值 AI 选题"

    def _ask_followup(self, count: int) -> str:
        prompt = f"输入 1-{count} 选择方向，或直接输入追问（如：更细分、加上中国场景、和 XXX 对比），输入 q 退出"
        try:
            import questionary  # type: ignore

            value = questionary.text(prompt).ask()
            return (value or "").strip()
        except Exception:
            return input(prompt + "\n> ").strip()

    def _collect_candidates(self, field: str, *, refresh: bool) -> list[HotspotCandidate]:
        query = _normalize_field_query(field)
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console) as progress:
            task = progress.add_task(f"正在查询最近 30 天公开信号：{query}", total=None)
            candidates = self.provider.search(query, window_days=30, limit=36, refresh=refresh)
            progress.update(task, description="正在整理可验证证据")
        return candidates

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
        self.console.print(Panel("下一步可以重新运行并输入：细化角度 / 找更细分方向 / 验证我的想法 / 加上中国场景", title="继续探索建议"))

    def _filter_by_instruction(self, candidates: list[HotspotCandidate], instruction: str) -> list[HotspotCandidate]:
        text = instruction.lower()
        if "中国" in instruction or "中文" in instruction:
            return [item for item in candidates if any(word in f"{item.title} {item.evidence}" for word in ("china", "chinese", "中文", "中国"))]
        if "论文" in instruction or "cs." in text or "paper" in text:
            return [item for item in candidates if "arxiv" in item.sources]
        if "开源" in instruction or "github" in text:
            return [item for item in candidates if "github" in item.sources]
        return candidates


def _normalize_field_query(field: str) -> str:
    text = field.strip()
    if text in {"随便推荐", "AI 通用", "ai 通用", "只看 cs.AI", "近期高价值 AI 选题", "AI 研究与产业趋势"}:
        return "AI agents multimodal reasoning arxiv"
    if text == "近期 AI 论文、基准评测、研究缺口":
        return "AI benchmark evaluation arxiv LLM agents multimodal reasoning"
    if text == "AI 产品、开源项目、产业落地":
        return "AI agents open source product launch GitHub"
    return text


def _evidence_for_direction(direction: TopicDirection, candidates: list[HotspotCandidate]) -> list[HotspotCandidate]:
    urls = {item.url for item in direction.representative_items if item.url}
    matched = [item for item in candidates if any(url in item.source_urls for url in urls)]
    if matched:
        return matched[:8]
    names = [item.title for item in direction.representative_items]
    return [item for item in candidates if item.title in names][:8]
