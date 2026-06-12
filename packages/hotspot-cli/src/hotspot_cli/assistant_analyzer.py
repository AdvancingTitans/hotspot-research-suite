from __future__ import annotations

import re
import json
from collections import defaultdict
from typing import Optional

from .assistant_models import (
    EvidenceItem,
    ReadingItem,
    ResearchQuestion,
    TopicBrief,
    TopicDirection,
    TopicDiscoveryInput,
    TopicDiscoveryResult,
    TopicSelection,
    TrendMetrics,
)
from .assistant_settings import AssistantSettings
from .hotspots import HotspotCandidate


class TopicAnalyzer:
    def discover_directions(self, payload: TopicDiscoveryInput) -> TopicDiscoveryResult:
        raise NotImplementedError

    def create_brief(self, selection: TopicSelection, trend: Optional[TrendMetrics] = None) -> TopicBrief:
        raise NotImplementedError


class InstructorTopicAnalyzer(TopicAnalyzer):
    def __init__(self, settings: Optional[AssistantSettings] = None, fallback: Optional[TopicAnalyzer] = None) -> None:
        self.settings = settings or AssistantSettings()
        self.fallback = fallback or FallbackTopicAnalyzer()

    def discover_directions(self, payload: TopicDiscoveryInput) -> TopicDiscoveryResult:
        if not self.settings.has_llm_key():
            return self.fallback.discover_directions(payload)
        try:
            self.settings.apply_provider_env()
            import instructor  # type: ignore
            from litellm import completion  # type: ignore

            client = instructor.from_litellm(completion)
            return client.chat.completions.create(
                model=self.settings.llm_model,
                response_model=TopicDiscoveryResult,
                messages=[
                    {"role": "system", "content": "你是数据严谨的中文研究选题助手。只基于给定证据输出具体、低竞争、可写作的细分方向。"},
                    {"role": "user", "content": json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)},
                ],
            )
        except Exception:
            return self.fallback.discover_directions(payload)

    def create_brief(self, selection: TopicSelection, trend: Optional[TrendMetrics] = None) -> TopicBrief:
        if not self.settings.has_llm_key():
            return self.fallback.create_brief(selection, trend)
        try:
            self.settings.apply_provider_env()
            import instructor  # type: ignore
            from litellm import completion  # type: ignore

            client = instructor.from_litellm(completion)
            data = {"selection": selection.model_dump(), "trend": (trend or TrendMetrics()).model_dump()}
            return client.chat.completions.create(
                model=self.settings.llm_model,
                response_model=TopicBrief,
                messages=[
                    {"role": "system", "content": "你是中文深度写作选题情报分析师。输出稳定结构，强调时效性、低竞争窗口、研究缺口和必读文献。"},
                    {"role": "user", "content": str(data)},
                ],
            )
        except Exception:
            return self.fallback.create_brief(selection, trend)


class FallbackTopicAnalyzer(TopicAnalyzer):
    def discover_directions(self, payload: TopicDiscoveryInput) -> TopicDiscoveryResult:
        groups = _group_candidates(payload.candidates)
        directions: list[TopicDirection] = []
        for keyword, items in groups[:8]:
            top = items[:3]
            name = _direction_name(payload.field, keyword, top)
            total_score = sum(item.score for item in top)
            arxiv_count = sum(1 for item in items if "arxiv" in item.sources)
            github_count = sum(1 for item in items if "github" in item.sources)
            representative = [_evidence(item) for item in top]
            directions.append(
                TopicDirection(
                    name=name,
                    why_now=f"为什么现在热门：最近 {payload.window_days} 天出现 {len(items)} 条相关公开信号，综合热度约 {total_score:.0f}；其中论文信号 {arxiv_count} 条、开源/开发者信号 {github_count} 条。",
                    competition_signal=f"竞争程度信号：主题词较具体（{keyword}），当前候选只有 {len(items)} 条，适合寻找尚未被综述化覆盖的低竞争窗口。",
                    research_gap=f"研究缺口：现有信号集中在单点论文/仓库/讨论，缺少系统比较、中文场景验证、失败案例和可复现评测。",
                    writing_angles=[
                        f"从 {keyword} 的近期证据出发，写一篇数据支撑的趋势判断。",
                        f"比较 {keyword} 与主流方案的差异、适用边界和风险。",
                        f"把 {keyword} 放入中国应用场景，寻找本土化研究问题。",
                    ],
                    representative_items=representative,
                )
            )
        if not directions and payload.candidates:
            top = payload.candidates[:3]
            directions.append(
                TopicDirection(
                    name=f"{payload.field} 的近期升温但低竞争切口",
                    why_now=f"为什么现在热门：最近 {payload.window_days} 天至少出现 {len(payload.candidates)} 条公开信号。",
                    competition_signal="竞争程度信号：候选较少，说明仍有细分空间，但需要继续补充论文和引用数据。",
                    research_gap="研究缺口：缺少针对具体机制、失败模式和场景化落地的系统分析。",
                    writing_angles=[f"围绕 {payload.field} 的最新证据做问题地图。"],
                    representative_items=[_evidence(item) for item in top],
                )
            )
        return TopicDiscoveryResult(field=payload.field, directions=directions[:8])

    def create_brief(self, selection: TopicSelection, trend: Optional[TrendMetrics] = None) -> TopicBrief:
        trend = trend or TrendMetrics(heat_7d=len(selection.evidence), heat_30d=len(selection.evidence), heat_30_60d=0, trend="数据不足", explanation="未传入趋势窗口数据。")
        readings = [_reading(item) for item in selection.evidence[:6]]
        if not readings:
            readings = [ReadingItem(title=selection.name, source="待补充", url="", reason="需要补充 last30days-safe 或论文来源。")]
        questions = [
            ResearchQuestion(
                angle="机制解释",
                question=f"{selection.name} 的核心技术或产业驱动因素是什么？",
                value="能把热点从新闻复述提升为解释型文章或研究问题。",
                feasibility="可用近期论文、GitHub 项目、开发者讨论和官方文档交叉验证。",
            ),
            ResearchQuestion(
                angle="低竞争切口",
                question=f"哪些子问题仍缺少系统梳理，尤其是中文场景、失败案例或评测方法？",
                value="避开泛泛综述，形成更具体、更容易写深的选题优势。",
                feasibility="通过最近 7/30 天信号和代表性文献即可形成初步证据链。",
            ),
            ResearchQuestion(
                angle="对比研究",
                question=f"{selection.name} 与相邻方向相比，真正的新变量是什么？",
                value="有助于写出差异化标题和清晰论点。",
                feasibility="可选择 2~3 个相邻技术路线或应用场景做矩阵比较。",
            ),
        ]
        return TopicBrief(
            topic=selection.name,
            field=selection.field,
            timeliness=f"{selection.rationale} 趋势判断为「{trend.trend}」：{trend.explanation}",
            current_state="当前公开信号主要覆盖近期论文、开发者项目和讨论热度；已经比较充分的是概念定义、单点方法和工具演示，尚不足的是跨来源验证、失败模式、复现成本和本土场景。",
            gaps=[
                "缺少对近期热点与 30~60 天前基线的趋势比较。",
                "缺少把论文/开源项目/社区讨论放在同一证据表里的低竞争选题分析。",
                "缺少面向中文语境或具体行业场景的可行性验证。",
            ],
            questions=questions,
            title_suggestions=[
                f"《{selection.name}：一个正在升温但尚未被充分研究的切口》",
                f"《从最近30天数据看{selection.name}的研究窗口》",
                f"《{selection.name}的低竞争机会：证据、缺口与写作角度》",
                f"{selection.name}: Evidence, Gaps, and Near-Term Research Opportunities",
                f"《为什么现在应该研究{selection.name}》",
            ],
            readings=readings,
            risks=[
                "last30days-safe 信号更适合发现热点，不等同于论文引用量或长期学术影响。",
                "社交/社区来源只能作为发现线索，关键事实仍需回到论文、官方文档或数据源验证。",
                "低竞争窗口可能来自资料不足而非真实机会，需要后续接入 OpenAlex/引用数据确认。",
            ],
            trend=trend,
        )


def _group_candidates(candidates: list[HotspotCandidate]) -> list[tuple[str, list[HotspotCandidate]]]:
    buckets: dict[str, list[HotspotCandidate]] = defaultdict(list)
    for item in sorted(candidates, key=lambda x: x.score, reverse=True):
        keyword = _keyword(item)
        buckets[keyword].append(item)
    return sorted(buckets.items(), key=lambda kv: (len(kv[1]), sum(item.score for item in kv[1])), reverse=True)


def _keyword(item: HotspotCandidate) -> str:
    text = f"{item.title} {item.evidence}".lower()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{3,}|[\u4e00-\u9fff]{2,}", text)
    stop = {"github", "arxiv", "paper", "signal", "submitted", "updated", "stars", "forks", "issues", "score"}
    for token in tokens:
        if token.lower() not in stop:
            return token[:40]
    return item.title[:30]


def _direction_name(field: str, keyword: str, items: list[HotspotCandidate]) -> str:
    if items and "arxiv" in items[0].sources:
        return f"{keyword}：{field} 的新论文驱动型低竞争切口"
    if items and "github" in items[0].sources:
        return f"{keyword}：开发者生态正在升温的实证选题"
    return f"{keyword}：{field} 的近期升温细分方向"


def _evidence(item: HotspotCandidate) -> EvidenceItem:
    return EvidenceItem(
        title=item.title,
        source=",".join(item.sources),
        url=item.source_urls[0] if item.source_urls else "",
        score=item.score,
        summary=item.evidence,
    )


def _reading(item: HotspotCandidate) -> ReadingItem:
    return ReadingItem(
        title=item.title,
        source=",".join(item.sources),
        url=item.source_urls[0] if item.source_urls else "",
        reason=f"代表近期 {','.join(item.sources)} 信号；数据依据：{item.evidence[:160]}",
    )
