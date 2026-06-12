from __future__ import annotations

import time
from typing import Optional

from .assistant_models import TrendMetrics
from .assistant_store import AssistantStore
from .hotspots import HotspotCandidate, Last30DaysClient


class Last30DaysProvider:
    def __init__(self, store: Optional[AssistantStore] = None, client: Optional[Last30DaysClient] = None, cache_ttl_seconds: int = 6 * 3600) -> None:
        self.store = store or AssistantStore()
        self.client = client or Last30DaysClient(sources="hn,github,reddit")
        self.cache_ttl_seconds = cache_ttl_seconds

    def search(self, query: str, *, window_days: int = 30, limit: int = 20, refresh: bool = False) -> list[HotspotCandidate]:
        cached = None if refresh else self.store.get_cache(query, window_days, max_age_seconds=self.cache_ttl_seconds)
        if cached is not None:
            return [_candidate_from_dict(item) for item in cached.get("items", [])]
        payload = self.client.collect(query, limit=limit, days=window_days)
        rows = payload.get("items", []) if isinstance(payload, dict) else []
        candidates = [_candidate_from_last30_row(row, query) for row in rows]
        self.store.set_cache(query, window_days, {"items": [_candidate_to_dict(item) for item in candidates], "fetched_at": time.time()})
        return candidates

    def trend(self, query: str, *, refresh: bool = False) -> TrendMetrics:
        recent_7 = self.search(query, window_days=7, limit=30, refresh=refresh)
        recent_30 = self.search(query, window_days=30, limit=40, refresh=refresh)
        older_query = f"{query} 30-60 days ago"
        older = self.search(older_query, window_days=60, limit=30, refresh=refresh)
        heat_7 = _heat(recent_7)
        heat_30 = _heat(recent_30)
        heat_old = _heat(older)
        if heat_30 == 0 and heat_old == 0:
            label = "数据不足"
        elif heat_30 >= heat_old * 1.25 and heat_7 >= max(1, heat_30 * 0.22):
            label = "上升"
        elif heat_30 < heat_old * 0.75:
            label = "下降"
        else:
            label = "平稳"
        return TrendMetrics(
            heat_7d=heat_7,
            heat_30d=heat_30,
            heat_30_60d=heat_old,
            trend=label,
            explanation=f"热度按候选条数、来源评分和不同时间窗口估算：7天={heat_7}，30天={heat_30}，30~60天前对照={heat_old}。",
        )


def _candidate_from_last30_row(row: dict, query: str) -> HotspotCandidate:
    meta = row.get("meta") or {}
    evidence_parts = [f"{row.get('source', 'public')} score={float(row.get('score') or 0):.0f}"]
    if isinstance(meta, dict):
        for key in ("stars", "forks", "comments", "score", "points", "language", "volume", "liquidity"):
            value = meta.get(key)
            if value not in (None, ""):
                evidence_parts.append(f"{key}={value}")
    if row.get("published"):
        evidence_parts.append(f"published={row.get('published')}")
    if row.get("snippet"):
        evidence_parts.append(str(row.get("snippet"))[:180])
    return HotspotCandidate(
        title=str(row.get("title") or query),
        domain=query,
        score=float(row.get("score") or 0),
        sources=[str(row.get("source") or "public")],
        evidence="; ".join(evidence_parts),
        source_urls=[str(row.get("url"))] if row.get("url") else [],
    )


def _candidate_to_dict(item: HotspotCandidate) -> dict:
    return {
        "title": item.title,
        "domain": item.domain,
        "score": item.score,
        "sources": item.sources,
        "evidence": item.evidence,
        "source_urls": item.source_urls,
    }


def _candidate_from_dict(data: dict) -> HotspotCandidate:
    return HotspotCandidate(
        title=str(data.get("title", "")),
        domain=str(data.get("domain", "")),
        score=float(data.get("score") or 0),
        sources=[str(item) for item in data.get("sources", [])],
        evidence=str(data.get("evidence", "")),
        source_urls=[str(item) for item in data.get("source_urls", [])],
    )


def _heat(items: list[HotspotCandidate]) -> int:
    return int(sum(max(1.0, min(item.score, 1000.0) / 20.0) for item in items))
