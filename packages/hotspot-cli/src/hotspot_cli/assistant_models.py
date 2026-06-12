from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .hotspots import HotspotCandidate


TrendLabel = Literal["上升", "平稳", "下降", "数据不足"]


class EvidenceItem(BaseModel):
    title: str
    source: str
    url: str
    published: Optional[str] = None
    score: float = 0
    summary: str = ""


class TopicDirection(BaseModel):
    name: str = Field(description="具体、可写作的细分选题名称")
    why_now: str = Field(description="为什么现在值得关注，必须含数据证据")
    competition_signal: str = Field(description="论文量、讨论量、具体程度等低竞争窗口信号")
    research_gap: str = Field(description="尚未被充分研究的缺口")
    writing_angles: list[str] = Field(default_factory=list)
    representative_items: list[EvidenceItem] = Field(default_factory=list, min_length=1)


class TopicDiscoveryInput(BaseModel):
    field: str
    window_days: int = 30
    candidates: list[HotspotCandidate] = Field(default_factory=list)


class TopicDiscoveryResult(BaseModel):
    field: str
    generated_at: datetime = Field(default_factory=datetime.now)
    directions: list[TopicDirection] = Field(default_factory=list)


class TopicSelection(BaseModel):
    name: str
    field: str
    query: str
    rationale: str
    evidence: list[HotspotCandidate] = Field(default_factory=list)


class TrendMetrics(BaseModel):
    heat_7d: int = 0
    heat_30d: int = 0
    heat_30_60d: int = 0
    trend: TrendLabel = "数据不足"
    explanation: str = ""


class ResearchQuestion(BaseModel):
    angle: str
    question: str
    value: str
    feasibility: str


class ReadingItem(BaseModel):
    title: str
    source: str
    url: str
    reason: str
    published: Optional[str] = None


class TopicBrief(BaseModel):
    topic: str
    field: str
    generated_at: datetime = Field(default_factory=datetime.now)
    timeliness: str
    current_state: str
    gaps: list[str]
    questions: list[ResearchQuestion]
    title_suggestions: list[str]
    readings: list[ReadingItem]
    risks: list[str]
    trend: TrendMetrics

    def to_markdown(self) -> str:
        lines = [
            f"# 选题情报简报：{self.topic}",
            "",
            f"> 领域：{self.field}  ",
            f"> 生成时间：{self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"> 趋势判断：{self.trend.trend}（7天={self.trend.heat_7d}，30天={self.trend.heat_30d}，30~60天前={self.trend.heat_30_60d}）",
            "",
            "## 1. 为什么这个选题现在具有时效性",
            "",
            self.timeliness,
            "",
            "## 2. 当前研究现状",
            "",
            self.current_state,
            "",
            "## 3. 高潜力研究缺口 / 切入角度",
            "",
        ]
        lines.extend(f"- {gap}" for gap in self.gaps)
        lines.extend(["", "## 4. 具体写作/研究问题", ""])
        for item in self.questions:
            lines.extend(
                [
                    f"### {item.angle}",
                    "",
                    f"- 研究问题：{item.question}",
                    f"- 为什么有价值：{item.value}",
                    f"- 可行性分析：{item.feasibility}",
                    "",
                ]
            )
        lines.extend(["## 5. 标题建议", ""])
        lines.extend(f"- {title}" for title in self.title_suggestions)
        lines.extend(["", "## 6. 值得重点阅读的近期文章及理由", ""])
        for item in self.readings:
            published = f" · {item.published}" if item.published else ""
            lines.append(f"- [{item.source}] [{item.title}]({item.url}){published}：{item.reason}")
        lines.extend(["", "## 7. 潜在风险提示", ""])
        lines.extend(f"- {risk}" for risk in self.risks)
        lines.extend(["", "## 趋势数据说明", "", self.trend.explanation])
        return "\n".join(lines).strip() + "\n"
