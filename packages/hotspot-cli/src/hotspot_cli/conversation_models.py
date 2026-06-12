from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .assistant_models import EvidenceItem, ReadingItem, ResearchQuestion, TrendMetrics


ConversationPhase = Literal["interest", "profile", "scan", "match", "brief"]
IntentName = Literal["answer", "refresh", "narrow", "broaden", "easier", "harder", "rank", "choose", "quit", "unknown"]


class DialogueTurn(BaseModel):
    role: Literal["assistant", "user"]
    content: str
    phase: ConversationPhase
    created_at: datetime = Field(default_factory=datetime.now)


class InitialDirection(BaseModel):
    name: str
    why_it_may_fit: str
    suggested_focus: str


class ResearchProfile(BaseModel):
    broad_interest: str = ""
    selected_focus: str = ""
    background: str = ""
    goal: str = ""
    time_budget: str = ""
    resources: str = ""
    unique_advantages: str = ""
    risk_preference: str = ""
    output_preference: str = ""
    constraints: str = ""
    confidence: float = 0.0

    def missing_fields(self) -> list[str]:
        fields = [
            "background",
            "goal",
            "time_budget",
            "unique_advantages",
            "risk_preference",
            "output_preference",
        ]
        return [field for field in fields if not getattr(self, field)]

    def summary(self) -> str:
        parts = [
            ("兴趣", self.broad_interest),
            ("聚焦方向", self.selected_focus),
            ("背景积累", self.background),
            ("核心目标", self.goal),
            ("时间资源", self.time_budget or self.resources),
            ("独特优势", self.unique_advantages),
            ("风险偏好", self.risk_preference),
            ("输出形式", self.output_preference),
            ("其他约束", self.constraints),
        ]
        lines = [f"- {name}：{value}" for name, value in parts if value]
        return "\n".join(lines) if lines else "- 暂无画像信息"


class ConversationState(BaseModel):
    phase: ConversationPhase = "interest"
    turns: list[DialogueTurn] = Field(default_factory=list)
    profile: ResearchProfile = Field(default_factory=ResearchProfile)
    initial_directions: list[InitialDirection] = Field(default_factory=list)
    matched_topics: list["MatchedTopic"] = Field(default_factory=list)
    seen_topics: list[str] = Field(default_factory=list)
    profile_rounds: int = 0

    def add_turn(self, role: Literal["assistant", "user"], content: str) -> None:
        self.turns.append(DialogueTurn(role=role, content=content, phase=self.phase))


class IntentResult(BaseModel):
    intent: IntentName = "answer"
    target_index: Optional[int] = None
    rewritten_focus: str = ""
    note: str = ""


class MatchedTopic(BaseModel):
    name: str
    field: str
    query: str
    personal_fit: int = Field(ge=0, le=100)
    opportunity_score: int = Field(ge=0, le=100)
    feasibility_score: int = Field(ge=0, le=100)
    total_score: int = Field(ge=0, le=100)
    personal_reason: str
    data_signal: str
    research_gap: str
    suggested_angles: list[str] = Field(default_factory=list)
    representative_items: list[EvidenceItem] = Field(default_factory=list)
    trend: TrendMetrics = Field(default_factory=TrendMetrics)


class PersonalizedTopicBrief(BaseModel):
    topic: str
    field: str
    generated_at: datetime = Field(default_factory=datetime.now)
    profile_summary: str
    why_best_fit: str
    angles: list[ResearchQuestion]
    title_suggestions: list[str]
    outline: list[str]
    readings: list[ReadingItem]
    risks: list[str]
    trend: TrendMetrics

    def to_markdown(self) -> str:
        lines = [
            f"# 个性化选题情报简报：{self.topic}",
            "",
            f"> 领域：{self.field}  ",
            f"> 生成时间：{self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"> 趋势判断：{self.trend.trend}（7天={self.trend.heat_7d}，30天={self.trend.heat_30d}，30~60天前={self.trend.heat_30_60d}）",
            "",
            "## 1. 你的选题画像",
            "",
            self.profile_summary,
            "",
            "## 2. 为什么这个选题最契合你",
            "",
            self.why_best_fit,
            "",
            "## 3. 推荐切入角度",
            "",
        ]
        for item in self.angles:
            lines.extend(
                [
                    f"### {item.angle}",
                    "",
                    f"- 研究问题：{item.question}",
                    f"- 推荐理由：{item.value}",
                    f"- 可行性：{item.feasibility}",
                    "",
                ]
            )
        lines.extend(["## 4. 标题建议", ""])
        lines.extend(f"- {title}" for title in self.title_suggestions)
        lines.extend(["", "## 5. 写作/研究大纲", ""])
        lines.extend(f"{idx}. {item}" for idx, item in enumerate(self.outline, 1))
        lines.extend(["", "## 6. 必读核心文献与材料", ""])
        for item in self.readings:
            published = f" · {item.published}" if item.published else ""
            lines.append(f"- [{item.source}] [{item.title}]({item.url}){published}：{item.reason}")
        lines.extend(["", "## 7. 潜在风险与应对", ""])
        lines.extend(f"- {risk}" for risk in self.risks)
        lines.extend(["", "## 趋势数据说明", "", self.trend.explanation])
        return "\n".join(lines).strip() + "\n"


ConversationState.model_rebuild()
