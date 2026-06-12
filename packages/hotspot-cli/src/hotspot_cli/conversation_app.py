from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .assistant_analyzer import InstructorTopicAnalyzer, plan_search_queries
from .assistant_models import EvidenceItem, ReadingItem, ResearchQuestion, TopicDiscoveryInput, TrendMetrics
from .assistant_settings import AssistantSettings
from .assistant_sources import Last30DaysProvider
from .assistant_store import AssistantStore
from .assistant_writer import _slugify
from .config import ConfigError, ConfigManager, DEFAULT_TEMPLATE
from .conversation_models import (
    ConversationState,
    InitialDirection,
    IntentResult,
    MatchedTopic,
    PersonalizedTopicBrief,
    ResearchProfile,
)
from .distribution import ChannelRegistry, DistributionError, lark_auth_status, lark_cli_status
from .hotspots import HotspotCandidate


class AdaptiveTopicAssistantApp:
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
        self.state = ConversationState()
        self.refresh_round = 0

    def run(self, output_dir: Path, *, refresh: bool = False) -> None:
        self._render_welcome(output_dir)
        if not self.settings.has_llm_key():
            self.console.print("[yellow]未检测到 LLM API Key，将使用本地规则完成自适应问答。运行 `hotspot-research setup` 可开启模型增强。[/yellow]")
        if self._load_saved_profile():
            topics = self._stage_scan(refresh=refresh)
            if not topics:
                self.console.print("[red]没有发现足够可靠且与你画像匹配的方向。可以说“换一个方向”，或先运行 `hotspot-research config profile clear` 重新生成画像。[/red]")
                return
            self._stage_match(topics, output_dir, refresh=refresh)
            return
        focus = self._stage_interest()
        if not focus:
            return
        if not self._stage_profile(focus):
            return
        topics = self._stage_scan(refresh=refresh)
        if not topics:
            self.console.print("[red]没有发现足够可靠且与你画像匹配的方向。可以换一个更具体的兴趣，或使用 --refresh 重试。[/red]")
            return
        self._stage_match(topics, output_dir, refresh=refresh)

    def _load_saved_profile(self) -> bool:
        data = self.store.get_profile()
        if not data:
            return False
        try:
            profile = ResearchProfile.model_validate(data)
        except Exception:
            return False
        if not profile.broad_interest and not profile.selected_focus:
            return False
        self.state.profile = profile
        self.state.phase = "profile"
        self.console.print(Panel(profile.summary(), title="已读取本地选题画像", border_style="green"))
        self.console.print("[dim]如果想重新聊一遍画像，运行：hotspot-research config profile clear[/dim]")
        raw = _ask_text("这次想沿用这个画像继续找题吗？回车沿用；也可以直接输入新的方向，或输入 clear 重新生成画像。", default="沿用")
        if raw.lower() in {"clear", "清除", "重来", "重新生成"}:
            self.store.clear_profile()
            self.state = ConversationState()
            self.console.print("[green]已清除本地画像，我们重新开始。[/green]")
            return False
        if raw not in {"", "沿用", "是", "好", "确认", "ok", "OK"}:
            self.state.profile.selected_focus = raw
            self.state.profile.broad_interest = _append_text(self.state.profile.broad_interest, raw)
            self._save_profile()
        return True

    def _render_welcome(self, output_dir: Path) -> None:
        left = "\n".join(
            [
                "[bold]Welcome back[/bold]",
                "",
                f"[dim]Model[/dim]  {self.settings.llm_model}",
                f"[dim]Cache[/dim]  {round(self.settings.cache_ttl_seconds / 3600, 2)}h",
                f"[dim]Output[/dim] {output_dir}",
            ]
        )
        right = "\n".join(
            [
                "[bold orange3]Adaptive topic interview[/bold orange3]",
                "先理解你，再扫描机会",
                "`换一个方向` 重新聚焦",
                "`再问我几个问题` 补充画像",
                "`都看看但帮我排序` 深度排序",
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
                title="[bold orange3]Hotspot Research[/bold orange3] [dim]personal topic intelligence[/dim]",
            )
        )

    def _stage_interest(self) -> str:
        self.state.phase = "interest"
        prompt = "最近你想探索什么 broad 领域或问题？也可以说“随便推荐”“完全没思路”“AI+人文社科交叉”。"
        raw = _ask_text(prompt, default="随便推荐")
        if _is_quit(raw):
            return ""
        self.state.add_turn("user", raw)
        self.state.profile.broad_interest = raw or "随便推荐"
        directions = self._initial_directions(raw)
        self.state.initial_directions = directions
        self._render_initial_directions(directions)
        choice = _ask_text("你更倾向哪个方向？输入序号，或直接说想更聚焦的子领域。", default="1")
        if _is_quit(choice):
            return ""
        self.state.add_turn("user", choice)
        focus = _resolve_initial_focus(choice, directions)
        self.state.profile.selected_focus = focus
        return focus

    def _stage_profile(self, focus: str) -> bool:
        self.state.phase = "profile"
        self.console.print(Panel("我想先多了解你一点，这样后面不是单纯追热点，而是帮你找真正适合你写、也写得出彩的题。", title="先聊聊你", border_style="bright_black"))
        while self.state.profile_rounds < 6:
            topic, question = self._next_profile_prompt()
            if not topic:
                break
            answer = _ask_text(question)
            if _is_quit(answer):
                return False
            intent = self._recognize_intent(answer)
            if intent.intent == "refresh":
                self.state.profile.selected_focus = intent.rewritten_focus or focus
                break
            self.state.add_turn("user", answer)
            self._mark_profile_topic(topic)
            if not _is_non_informative_answer(answer):
                self.state.profile = self._update_profile(self.state.profile, topic, question, answer)
            self.state.profile_rounds += 1
            if intent.intent == "easier":
                self.state.profile.risk_preference = "偏稳健，希望难度适中、资料相对充分"
            elif intent.intent == "harder":
                self.state.profile.risk_preference = "愿意探索高风险高回报的新方向"
            elif intent.intent == "narrow" and intent.rewritten_focus:
                self.state.profile.selected_focus = intent.rewritten_focus
        self.state.profile.confidence = _profile_confidence(self.state.profile)
        self._render_profile_summary()
        confirm = _ask_text("这个画像基本准确吗？回车确认；也可以补充一句需要修正的地方。", default="确认")
        if _is_quit(confirm):
            return False
        if confirm not in {"", "确认", "是", "对", "准确", "ok", "OK"}:
            self.state.profile.constraints = _append_text(self.state.profile.constraints, confirm)
            self._render_profile_summary()
        self._save_profile()
        return True

    def _stage_scan(self, *, refresh: bool) -> list[MatchedTopic]:
        self.state.phase = "scan"
        profile = self.state.profile
        query_seed = _profile_query_seed(profile)
        if refresh:
            self.refresh_round += 1
        queries = plan_search_queries(
            settings=self.settings,
            user_input=query_seed,
            mode="manual",
            avoid=self.state.seen_topics,
            limit=8,
        )
        if refresh:
            queries = _expand_refresh_queries(queries, self.refresh_round)
        label = " / ".join(queries[:3]) + (" ..." if len(queries) > 3 else "")
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console) as progress:
            task = progress.add_task(f"扫描公开证据 · {label}", total=None)
            candidates = self.provider.search_many(queries, window_days=30, limit=72 if refresh else 48, refresh=refresh)
            progress.update(task, description="匹配你的画像")
            candidates = _filter_seen_viable(candidates, self.state.seen_topics)
            discovery = self.analyzer.discover_directions(TopicDiscoveryInput(field=profile.selected_focus or profile.broad_interest, window_days=30, candidates=candidates))
            topics = self._match_topics(discovery.directions, candidates)
        self.state.matched_topics = topics
        self.state.seen_topics.extend(topic.name for topic in topics)
        self._render_matched_topics(topics)
        return topics

    def _stage_match(self, topics: list[MatchedTopic], output_dir: Path, *, refresh: bool) -> None:
        self.state.phase = "match"
        current = topics
        while True:
            raw = _ask_text("输入序号生成个性化简报；也可说“都看看但帮我排序”“更细一点”“这个太难了，换简单点的”“换一个方向”，输入 q 退出。", default="1")
            if _is_quit(raw):
                return
            intent = self._recognize_intent(raw)
            if raw.isdigit() and 1 <= int(raw) <= len(current):
                self._create_personalized_brief(current[int(raw) - 1], output_dir, refresh=refresh)
                return
            if "再问" in raw or "多问" in raw or "补充画像" in raw:
                self._ask_additional_profile_questions(count=2)
                current = self._stage_scan(refresh=True)
                if not current:
                    return
                continue
            if intent.intent == "rank" or "排序" in raw:
                current = sorted(current, key=lambda item: item.total_score, reverse=True)
                self._render_matched_topics(current, title="按个人契合度与数据机会排序")
                continue
            if intent.intent in {"easier", "harder", "refresh", "broaden", "narrow"} or "换" in raw:
                self.state.profile.constraints = _append_text(self.state.profile.constraints, raw)
                current = self._stage_scan(refresh=True)
                if not current:
                    return
                continue
            self.console.print(Panel(f"我会按你的追问重新细化：{raw}", title="继续匹配", border_style="bright_black"))
            self.state.profile.constraints = _append_text(self.state.profile.constraints, raw)
            current = self._stage_scan(refresh=True)
            if not current:
                return

    def _ask_additional_profile_questions(self, *, count: int = 2) -> None:
        self.state.phase = "profile"
        self.console.print(Panel("好，我再多了解一点点，把后面的推荐调得更贴近你。", title="再聊两句", border_style="bright_black"))
        for _ in range(count):
            topic, question = self._next_profile_prompt(allow_revisit=True)
            if not topic:
                return
            answer = _ask_text(question)
            if _is_quit(answer):
                return
            self.state.add_turn("user", answer)
            self._mark_profile_topic(topic)
            if not _is_non_informative_answer(answer):
                self.state.profile = self._update_profile(self.state.profile, topic, question, answer)
            self.state.profile_rounds += 1
        self.state.profile.confidence = _profile_confidence(self.state.profile)
        self._render_profile_summary()
        self._save_profile()

    def _save_profile(self) -> None:
        self.state.profile.confidence = _profile_confidence(self.state.profile)
        self.store.set_profile(self.state.profile.model_dump(mode="json"))

    def _initial_directions(self, raw: str) -> list[InitialDirection]:
        fallback = _fallback_initial_directions(raw)
        data = self._llm_json(
            {
                "task": "根据用户初始兴趣，给出 3-5 个初步研究/写作方向。方向要具体、有探索空间，并适合继续追问画像。",
                "user_input": raw,
                "schema": {"directions": [{"name": "方向名", "why_it_may_fit": "为什么可能适合", "suggested_focus": "可继续聚焦的子领域"}]},
            }
        )
        rows = data.get("directions", []) if isinstance(data, dict) else []
        directions = []
        for row in rows:
            try:
                directions.append(InitialDirection.model_validate(row))
            except Exception:
                continue
        return (directions or fallback)[:5]

    def _next_profile_prompt(self, *, allow_revisit: bool = False) -> tuple[str, str]:
        topic = _next_profile_topic(self.state.profile, self.state.asked_profile_topics, allow_revisit=allow_revisit)
        if not topic:
            return "", ""
        fallback = _fallback_profile_question(topic, self.state.profile_rounds)
        data = self._llm_json(
            {
                "task": "为中文选题助手生成下一句自然追问。像聊天一样，只问一个问题，不要列清单，不要像科研申请表。",
                "conversation_goal": "自然了解用户，而不是审问用户。用户可以回答没有、不知道、还没想好。",
                "profile": self.state.profile.model_dump(),
                "topic_to_ask": topic,
                "already_asked_topics": self.state.asked_profile_topics,
                "recent_turns": [turn.model_dump(mode="json") for turn in self.state.turns[-6:]],
                "round": self.state.profile_rounds + 1,
                "rules": [
                    "语气自然、有温度，像一个懂写作的研究伙伴",
                    "不要出现：画像、风险偏好、输出偏好、资源约束、学术/写作背景、核心目标 等字段化表达",
                    "不要重复问已经问过的主题，也不要换一种说法重复追问",
                    "如果 topic_to_ask 是 goal，要问真实想达成什么结果，这是最关键的问题",
                    "如果 topic_to_ask 是 concern，要允许用户说没有顾虑",
                ],
                "schema": {"question": "一句中文问题"},
            }
        )
        question = str(data.get("question", "")).strip() if isinstance(data, dict) else ""
        if not question or _looks_like_form_question(question) or not _question_matches_topic(topic, question):
            question = fallback
        return topic, question

    def _mark_profile_topic(self, topic: str) -> None:
        if topic not in self.state.asked_profile_topics:
            self.state.asked_profile_topics.append(topic)

    def _update_profile(self, profile: ResearchProfile, topic: str, question: str, answer: str) -> ResearchProfile:
        data = self._llm_json(
            {
                "task": "根据自然对话更新内部用户画像。未提及字段保留原值。用户说没有、不知道、还没想好时，不要编造。",
                "current_profile": profile.model_dump(),
                "topic": topic,
                "question": question,
                "answer": answer,
                "schema": ResearchProfile.model_json_schema(),
            }
        )
        if isinstance(data, dict):
            merged = profile.model_dump()
            for key, value in data.items():
                if key in merged and value not in (None, ""):
                    merged[key] = str(value) if not isinstance(value, (int, float)) else value
            try:
                return ResearchProfile.model_validate(merged)
            except Exception:
                pass
        return _heuristic_update_profile(profile, topic, question, answer)

    def _recognize_intent(self, raw: str) -> IntentResult:
        text = raw.strip()
        if _is_quit(text):
            return IntentResult(intent="quit")
        lowered = text.lower()
        if "排序" in text or "都看看" in text or "rank" in lowered:
            return IntentResult(intent="rank")
        if "换" in text or "refresh" in lowered:
            return IntentResult(intent="refresh", rewritten_focus=text)
        if "细" in text or "聚焦" in text:
            return IntentResult(intent="narrow", rewritten_focus=text)
        if "简单" in text or "太难" in text:
            return IntentResult(intent="easier")
        if "高风险" in text or "前沿" in text or "难一点" in text:
            return IntentResult(intent="harder")
        if text.isdigit():
            return IntentResult(intent="choose", target_index=int(text))
        data = self._llm_json(
            {
                "task": "识别用户在选题助手中的意图。",
                "input": text,
                "intents": ["answer", "refresh", "narrow", "broaden", "easier", "harder", "rank", "choose", "quit", "unknown"],
                "schema": IntentResult.model_json_schema(),
            }
        )
        if isinstance(data, dict):
            try:
                return IntentResult.model_validate(data)
            except Exception:
                pass
        return IntentResult(intent="answer")

    def _match_topics(self, directions: list[Any], candidates: list[HotspotCandidate]) -> list[MatchedTopic]:
        if not directions:
            return []
        payload = {
            "task": "结合用户画像和候选方向，输出 4-6 个最契合用户的选题，并给出个人契合、数据机会、可行性三类分数。",
            "profile": self.state.profile.model_dump(),
            "directions": [direction.model_dump(mode="json") for direction in directions[:8]],
            "schema": {"topics": [MatchedTopic.model_json_schema()]},
        }
        data = self._llm_json(payload)
        rows = data.get("topics", []) if isinstance(data, dict) else []
        topics = []
        for row in rows:
            try:
                topics.append(MatchedTopic.model_validate(row))
            except Exception:
                continue
        if topics:
            return sorted(topics, key=lambda item: item.total_score, reverse=True)[:6]
        return _fallback_match_topics(self.state.profile, directions, candidates)[:6]

    def _create_personalized_brief(self, topic: MatchedTopic, output_dir: Path, *, refresh: bool) -> None:
        self.state.phase = "brief"
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console) as progress:
            task = progress.add_task("计算多时间窗口趋势", total=None)
            trend = self.provider.trend(topic.query or topic.name, refresh=refresh)
            progress.update(task, description="生成个性化选题情报简报")
            topic.trend = trend
            brief = self._personalized_brief(topic, trend)
            path = _save_personalized_brief(brief, output_dir)
            self.store.add_history("personalized_brief", brief.topic, {"path": str(path), "topic": brief.topic})
        self.console.print(Markdown(brief.to_markdown()))
        self.console.print(f"[bold green]简报已保存：[/bold green][cyan]{path}[/cyan]")
        self._offer_lark_send(path=path, topic=brief.topic, summary=brief.why_best_fit[:180])

    def _personalized_brief(self, topic: MatchedTopic, trend: TrendMetrics) -> PersonalizedTopicBrief:
        fallback = _fallback_personalized_brief(self.state.profile, topic, trend)
        data = self._llm_json(
            {
                "task": "生成中文《个性化选题情报简报》。重点解释为什么这个选题最契合用户，而不是只说热门。",
                "profile": self.state.profile.model_dump(),
                "topic": topic.model_dump(mode="json"),
                "trend": trend.model_dump(mode="json"),
                "schema": PersonalizedTopicBrief.model_json_schema(),
            }
        )
        if isinstance(data, dict):
            data["trend"] = data.get("trend") or trend.model_dump(mode="json")
            try:
                return PersonalizedTopicBrief.model_validate(data)
            except Exception:
                return fallback
        return fallback

    def _render_initial_directions(self, directions: list[InitialDirection]) -> None:
        table = Table(title="初步方向（先粗看，不急着定题）", show_lines=True)
        table.add_column("序号", justify="right", style="cyan", width=4)
        table.add_column("方向", style="bold", min_width=20)
        table.add_column("为什么可能适合", min_width=32)
        table.add_column("可聚焦子领域", min_width=26)
        for idx, item in enumerate(directions, 1):
            table.add_row(str(idx), item.name, item.why_it_may_fit, item.suggested_focus)
        self.console.print(table)

    def _render_profile_summary(self) -> None:
        self.console.print(Panel(self.state.profile.summary(), title="你的选题画像", border_style="green"))

    def _render_matched_topics(self, topics: list[MatchedTopic], title: str = "与你画像匹配的候选选题") -> None:
        table = Table(title=title, show_lines=True)
        table.add_column("序号", justify="right", style="cyan", width=4)
        table.add_column("候选选题", style="bold", min_width=20)
        table.add_column("个人契合", justify="right", width=8)
        table.add_column("数据机会", justify="right", width=8)
        table.add_column("可行性", justify="right", width=8)
        table.add_column("匹配理由 + 数据信号", min_width=36)
        for idx, item in enumerate(topics, 1):
            reason = f"{item.personal_reason}\n数据：{item.data_signal}\n缺口：{item.research_gap}"
            table.add_row(str(idx), item.name, str(item.personal_fit), str(item.opportunity_score), str(item.feasibility_score), reason)
        self.console.print(table)

    def _offer_lark_send(self, *, path: Path, topic: str, summary: str) -> None:
        if not _ask_yes_no("是否发送到飞书群？", default=False):
            return
        ok, message = lark_cli_status()
        if not ok:
            self.console.print(f"[yellow]{message}[/yellow]")
            self.console.print("请先安装并运行：`hotspot-research config lark auth --init`")
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
                return
            try:
                config = manager.update_lark(chat_id=chat_id, identity="bot", message_template=DEFAULT_TEMPLATE)
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
            return
        self.console.print("[green]已发送到飞书群。[/green]")

    def _llm_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.has_llm_key():
            return {}
        try:
            self.settings.apply_provider_env()
            from litellm import completion  # type: ignore

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                response = completion(
                    model=self.settings.llm_model,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "你是严谨、自然的中文研究选题助手。只输出合法 JSON，不要 Markdown。"},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    **self.settings.litellm_kwargs(),
                )
            content = response.choices[0].message.content or "{}"
            return json.loads(_extract_json(content))
        except Exception:
            return {}


def _ask_text(message: str, default: str = "") -> str:
    if not sys.stdin.isatty():
        suffix = f" [{default}]" if default else ""
        raw = input(f"{message}{suffix}\n> ").strip()
        return raw or default
    try:
        import questionary  # type: ignore

        value = questionary.text(message, default=default).ask()
        return (value or "").strip()
    except Exception:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{message}{suffix}\n> ").strip()
        return raw or default


def _ask_yes_no(message: str, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        suffix = "Y/n" if default else "y/N"
        raw = input(f"{message} [{suffix}] ").strip().lower()
        if not raw:
            return default
        return raw in {"y", "yes", "是", "好", "确认"}
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


def _is_quit(raw: str) -> bool:
    return raw.strip().lower() in {"q", "quit", "exit", "退出", "不做了"}


def _resolve_initial_focus(raw: str, directions: list[InitialDirection]) -> str:
    text = raw.strip()
    if text.isdigit() and 1 <= int(text) <= len(directions):
        item = directions[int(text) - 1]
        return item.suggested_focus or item.name
    return text


def _fallback_initial_directions(raw: str) -> list[InitialDirection]:
    text = raw.strip() or "随便推荐"
    if text in {"随便推荐", "我完全没思路", "完全没思路", "没思路"}:
        return [
            InitialDirection(name="AI Agent 评测与可靠性", why_it_may_fit="近期论文和开源项目密集，适合用数据找低竞争切口。", suggested_focus="LLM Agent 评测、记忆、可靠性"),
            InitialDirection(name="多模态推理的失败模式", why_it_may_fit="有技术热度，也容易形成深度文章的解释框架。", suggested_focus="多模态推理评测与失败案例"),
            InitialDirection(name="AI 编程工具的真实生产力", why_it_may_fit="GitHub 和产业讨论多，适合做证据型分析。", suggested_focus="AI coding agent 生产力评测"),
            InitialDirection(name="中文大模型安全", why_it_may_fit="中文场景有差异化优势，资料足但仍有细分缺口。", suggested_focus="中文大模型安全评测与治理"),
        ]
    if "人文" in text or "社科" in text:
        return [
            InitialDirection(name="LLM 作为社会科学研究工具", why_it_may_fit="能结合 AI 与社科方法，形成跨学科优势。", suggested_focus="LLM 辅助社会科学可复现性评估"),
            InitialDirection(name="AI 介导的认知与写作", why_it_may_fit="适合深度文章和研究综述，问题意识清晰。", suggested_focus="AI 写作工具对认知劳动的影响"),
            InitialDirection(name="中文语境下的算法治理", why_it_may_fit="有文化和制度语境优势，容易做本土化切入。", suggested_focus="中文 AI 治理与平台实践"),
        ]
    return [
        InitialDirection(name=f"{text} 的近期低竞争切口", why_it_may_fit="你已经给出明确兴趣，适合围绕近期证据继续缩小范围。", suggested_focus=text),
        InitialDirection(name=f"{text} 的应用场景化研究", why_it_may_fit="应用场景更容易连接个人资源和写作目标。", suggested_focus=f"{text} 应用场景"),
        InitialDirection(name=f"{text} 的评测与方法比较", why_it_may_fit="评测/比较类选题更容易建立可验证的数据支撑。", suggested_focus=f"{text} 评测 benchmark"),
    ]


PROFILE_TOPIC_ORDER = ["background", "goal", "advantage", "concern"]


def _next_profile_topic(profile: ResearchProfile, asked_topics: list[str], *, allow_revisit: bool = False) -> str:
    if allow_revisit:
        for topic in ["advantage", "concern", "goal", "background"]:
            if topic not in asked_topics:
                return topic
        return "concern"
    for topic in PROFILE_TOPIC_ORDER:
        if topic not in asked_topics:
            return topic
    return ""


def _fallback_profile_question(topic: str, round_no: int) -> str:
    questions = {
        "background": "先聊聊你自己吧，你之前主要在哪些方向做过研究、写作或者项目？随便说个大概就行。",
        "goal": "这次如果真花时间做这个选题，你最希望它帮你达成什么？比如写一篇有人看的文章、系统学一个领域、为工作做准备，或者只是满足好奇。",
        "advantage": "你有没有一些别人不太容易复制的视角或资源？比如行业经历、城市/语言优势、能接触到的人或数据，哪怕很小也算。",
        "concern": "有没有什么你现在不太想碰的方向，或者一想到就觉得麻烦、没把握的地方？没有也可以直接说没有。",
    }
    return questions.get(topic, questions[PROFILE_TOPIC_ORDER[round_no % len(PROFILE_TOPIC_ORDER)]])


def _heuristic_update_profile(profile: ResearchProfile, topic: str, question: str, answer: str) -> ResearchProfile:
    data = profile.model_copy(deep=True)
    if topic == "background":
        data.background = _append_text(data.background, answer)
    elif topic == "goal":
        data.goal = _append_text(data.goal, answer)
        if any(word in answer for word in ["论文", "paper", "投稿", "发表"]):
            data.output_preference = _append_text(data.output_preference, "学术论文")
        if any(word in answer for word in ["长文", "公众号", "文章", "爆款", "很多人看", "阅读"]):
            data.output_preference = _append_text(data.output_preference, "深度长文")
        if any(word in answer for word in ["职业", "工作", "跳槽", "转型"]):
            data.goal = _append_text(data.goal, "职业发展")
    elif topic == "advantage":
        data.unique_advantages = _append_text(data.unique_advantages, answer)
        if any(word in answer for word in ["数据", "访谈", "人脉", "客户", "用户", "行业"]):
            data.resources = _append_text(data.resources, answer)
    elif topic == "concern":
        data.constraints = _append_text(data.constraints, answer)
        if any(word in answer for word in ["简单", "别太难", "太难", "时间少", "稳"]):
            data.risk_preference = _append_text(data.risk_preference, "偏稳健，希望难度适中")
    else:
        data.constraints = _append_text(data.constraints, answer)
    if any(word in answer for word in ["一周", "两周", "一个月", "周末", "今晚", "短期"]):
        data.time_budget = _append_text(data.time_budget, answer)
    return data


def _is_non_informative_answer(answer: str) -> bool:
    text = re.sub(r"\s+", "", answer.strip().lower())
    return text in {"", "无", "没有", "没", "不知道", "还没想好", "不清楚", "随便", "都行", "none", "no", "na", "n/a"}


def _looks_like_form_question(question: str) -> bool:
    banned = [
        "画像",
        "风险偏好",
        "输出偏好",
        "资源约束",
        "时间与资源约束",
        "学术/写作背景",
        "核心目标",
        "独特个人优势",
        "请描述",
        "请说明",
        "以下维度",
    ]
    if any(word in question for word in banned):
        return True
    return question.count("？") + question.count("?") > 1


def _question_matches_topic(topic: str, question: str) -> bool:
    keywords = {
        "background": ["背景", "之前", "做过", "研究", "写作", "项目", "经历", "积累"],
        "goal": ["达成", "希望", "想通过", "结果", "目标", "发论文", "文章", "系统学", "职业", "好奇"],
        "advantage": ["优势", "资源", "视角", "经历", "数据", "人", "接触", "行业", "城市", "语言"],
        "concern": ["不想", "顾虑", "担心", "没把握", "麻烦", "避开", "没有"],
    }
    return any(word in question for word in keywords.get(topic, []))


def _profile_confidence(profile: ResearchProfile) -> float:
    total = 8
    filled = sum(1 for item in [profile.broad_interest, profile.selected_focus, profile.background, profile.goal, profile.time_budget, profile.unique_advantages, profile.risk_preference, profile.output_preference] if item)
    return round(filled / total, 2)


def _profile_query_seed(profile: ResearchProfile) -> str:
    pieces = [
        profile.selected_focus,
        profile.broad_interest,
        profile.goal,
        profile.output_preference,
        profile.unique_advantages,
        profile.constraints,
    ]
    return " ".join(piece for piece in pieces if piece)[:500] or "AI research opportunities"


def _filter_seen_viable(candidates: list[HotspotCandidate], seen_topics: list[str]) -> list[HotspotCandidate]:
    seen = " ".join(seen_topics).lower()
    result = []
    for item in candidates:
        if item.score <= 0 or not item.source_urls:
            continue
        title = item.title.lower()
        if seen and (title in seen or any(token in seen for token in _strong_tokens(title)[:5])):
            continue
        result.append(item)
    return result


def _strong_tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{7,}|[\u4e00-\u9fff]{4,}", text)]


def _expand_refresh_queries(queries: list[str], round_no: int) -> list[str]:
    angles = ["emerging research gap", "new benchmark", "case study", "China context", "low competition", "survey gap", "developer adoption"]
    offset = (round_no * 2) % len(angles)
    angles = angles[offset:] + angles[:offset]
    out = []
    for idx, query in enumerate(queries):
        out.append(query)
        out.append(f"{query} {angles[idx % len(angles)]}")
    return _dedupe(out)[:10]


def _fallback_match_topics(profile: ResearchProfile, directions: list[Any], candidates: list[HotspotCandidate]) -> list[MatchedTopic]:
    topics: list[MatchedTopic] = []
    profile_text = profile.summary()
    for direction in directions[:6]:
        reps = list(getattr(direction, "representative_items", []) or [])
        evidence_titles = {item.title for item in reps}
        matched = [item for item in candidates if item.title in evidence_titles]
        total_score = sum(item.score for item in matched[:3]) or sum(getattr(item, "score", 0) for item in reps[:3])
        fit = _score_personal_fit(profile_text, direction.name + " " + direction.research_gap)
        opportunity = min(95, 45 + int(total_score))
        feasibility = _score_feasibility(profile, direction.name)
        total = int(fit * 0.4 + opportunity * 0.35 + feasibility * 0.25)
        topics.append(
            MatchedTopic(
                name=direction.name,
                field=profile.selected_focus or profile.broad_interest or "AI",
                query=direction.name,
                personal_fit=fit,
                opportunity_score=opportunity,
                feasibility_score=feasibility,
                total_score=total,
                personal_reason=f"与你的画像交集主要在：{_short(profile.selected_focus or profile.broad_interest, 48)}。",
                data_signal=direction.why_now,
                research_gap=direction.research_gap,
                suggested_angles=direction.writing_angles[:4],
                representative_items=reps[:4],
            )
        )
    return sorted(topics, key=lambda item: item.total_score, reverse=True)


def _score_personal_fit(profile_text: str, topic_text: str) -> int:
    tokens = set(_strong_tokens(profile_text.lower()))
    overlap = sum(1 for token in _strong_tokens(topic_text.lower()) if token in tokens)
    return min(95, 55 + overlap * 8)


def _score_feasibility(profile: ResearchProfile, topic_name: str) -> int:
    score = 70
    if "一周" in profile.time_budget or "短" in profile.time_budget:
        score -= 10
    if "稳健" in profile.risk_preference or "简单" in profile.constraints:
        score += 8
    if "论文" in profile.output_preference and ("benchmark" in topic_name.lower() or "评测" in topic_name):
        score += 8
    return max(30, min(95, score))


def _fallback_personalized_brief(profile: ResearchProfile, topic: MatchedTopic, trend: TrendMetrics) -> PersonalizedTopicBrief:
    readings = [
        ReadingItem(title=item.title, source=item.source, url=item.url, reason=f"代表近期公开证据；摘要：{item.summary[:120]}")
        for item in topic.representative_items[:6]
    ]
    if not readings:
        readings = [ReadingItem(title=topic.name, source="待补充", url="", reason="需要继续补充论文、GitHub 或新闻来源。")]
    angles = []
    source_angles = topic.suggested_angles or ["机制解释", "场景验证", "对比评测"]
    for angle in source_angles[:4]:
        angles.append(
            ResearchQuestion(
                angle=angle,
                question=f"如何围绕「{topic.name}」提出一个具体、可验证且与你优势相关的问题？",
                value=f"该角度能把公开热度转化为你的差异化切入：{topic.personal_reason}",
                feasibility="可用近期论文、开源项目和社区讨论做证据链，先完成小范围综述再扩展。",
            )
        )
    return PersonalizedTopicBrief(
        topic=topic.name,
        field=topic.field,
        profile_summary=profile.summary(),
        why_best_fit=f"{topic.personal_reason} 同时，公开数据窗口显示：{topic.data_signal} 综合评分中个人契合度 {topic.personal_fit}/100、数据机会 {topic.opportunity_score}/100、可行性 {topic.feasibility_score}/100。",
        angles=angles,
        title_suggestions=[
            f"《{topic.name}：为什么这是最适合你的近期选题》",
            f"《从数据窗口看{topic.name}的低竞争机会》",
            f"《{topic.name}的研究缺口、个人优势与写作路径》",
            f"{topic.name}: Personalized Research Opportunity Brief",
        ],
        outline=[
            "问题背景：说明近期数据窗口和选题重要性",
            "个人切入：解释你的背景/资源如何形成差异化",
            "证据地图：整理论文、开源项目、讨论和趋势信号",
            "研究缺口：列出尚未被充分回答的问题",
            "核心论证：围绕 2-4 个切入角度展开",
            "风险与边界：说明资料不足、可复现性和外推限制",
        ],
        readings=readings,
        risks=[
            "低竞争可能来自资料不足，需要继续交叉验证。",
            "公开热度不等同长期价值，建议补充引用数据和专家材料。",
            "如果时间预算较短，应先收窄为一个可完成的小问题。",
        ],
        trend=trend,
    )


def _save_personalized_brief(brief: PersonalizedTopicBrief, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = brief.generated_at.strftime("%Y%m%d-%H%M%S")
    path = (output_dir / f"{stamp}-{_slugify(brief.topic)}.md").resolve()
    path.write_text(brief.to_markdown(), encoding="utf-8")
    return path


def _append_text(current: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return current
    if not current:
        return addition
    if addition in current:
        return current
    return f"{current}；{addition}"


def _short(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result


def _extract_json(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    raise ValueError("No JSON object found")
