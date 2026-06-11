from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


PACKAGE_LAST30_MODULE = "hotspot_cli.last30days_safe"
LAST30_SCRIPT = Path(os.environ.get("LAST30DAYS_SAFE_SCRIPT", "/Users/yjw/.hermes/skills/research/last30days-safe/scripts/last30days_safe.py"))
DEFAULT_PYTHON = Path("/opt/homebrew/bin/python3.12")

MAINSTREAM_DOMAINS = [
    "人工智能",
    "具身智能",
    "半导体",
    "新能源汽车",
    "生物医药",
    "绿色能源",
    "低空经济",
    "机器人",
    "量子计算",
    "商业航天",
    "数据中心",
    "网络安全",
    "储能",
    "智能制造",
    "金融科技",
]

DOMAIN_HOTSPOT_SEEDS = [
    "政策 监管 标准",
    "融资 并购 投资",
    "市场规模 CAGR 出货量",
    "技术突破 论文 benchmark",
    "产品发布 版本 量产",
    "供应链 产能 成本",
    "产业事件 合作 订单",
    "开源 GitHub release",
    "临床 试验 审批",
    "国际竞争 出口 管制",
]

OBJECTIVE_KEYWORDS = (
    "policy",
    "regulation",
    "standard",
    "market",
    "funding",
    "investment",
    "release",
    "github",
    "benchmark",
    "paper",
    "arxiv",
    "trial",
    "approval",
    "政策",
    "监管",
    "标准",
    "融资",
    "投资",
    "市场",
    "规模",
    "出货",
    "发布",
    "论文",
    "成果",
    "技术",
    "审批",
    "临床",
    "订单",
    "量产",
    "供应链",
)

BLOCKED_KEYWORDS = (
    "明星",
    "八卦",
    "绯闻",
    "综艺",
    "短剧",
    "meme",
    "memecoin",
    "概念币",
    "暴涨",
    "暴跌",
    "彩票",
    "博彩",
    "price prediction",
    "trading signal",
)


@dataclass(frozen=True)
class HotspotCandidate:
    title: str
    domain: str
    score: float
    sources: list[str]
    evidence: str
    source_urls: list[str]

    def summary(self) -> str:
        return f"{self.title}｜依据：{self.evidence}"


class HotspotError(RuntimeError):
    pass


class Last30DaysClient:
    def __init__(
        self,
        script_path: Path = LAST30_SCRIPT,
        python_bin: Path = DEFAULT_PYTHON,
        sources: str = "hn,github,reddit,polymarket",
    ) -> None:
        self.script_path = script_path
        self.python_bin = python_bin if python_bin.exists() else Path(sys.executable)
        self.sources = sources

    def collect(self, topic: str, *, limit: int = 20) -> dict:
        if self.script_path.exists():
            argv = [str(self.python_bin), str(self.script_path)]
        else:
            argv = [str(self.python_bin), "-m", PACKAGE_LAST30_MODULE]
        argv.extend([topic, "--emit", "json", "--limit", str(limit), "--sources", self.sources])
        try:
            proc = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired as exc:
            raise HotspotError("last30days-safe 请求超时，请检查网络或稍后重试。") from exc
        if proc.returncode != 0:
            raise HotspotError(f"last30days-safe 执行失败：{proc.stderr.strip() or proc.stdout.strip()}")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise HotspotError("last30days-safe 返回内容不是合法 JSON。") from exc


class HotspotFilter:
    def filter(self, candidates: Iterable[HotspotCandidate]) -> list[HotspotCandidate]:
        filtered: list[HotspotCandidate] = []
        for item in candidates:
            text = f"{item.title} {item.evidence}".lower()
            if any(word.lower() in text for word in BLOCKED_KEYWORDS):
                continue
            if not any(word.lower() in text for word in OBJECTIVE_KEYWORDS):
                continue
            if not item.source_urls:
                continue
            filtered.append(item)
        return sorted(filtered, key=lambda c: c.score, reverse=True)


class HotspotService:
    def __init__(
        self,
        collector: Callable[[str, int], list[HotspotCandidate]] | None = None,
        client: Last30DaysClient | None = None,
        hotspot_filter: HotspotFilter | None = None,
    ) -> None:
        self.client = client or Last30DaysClient()
        self.hotspot_filter = hotspot_filter or HotspotFilter()
        self.collector = collector

    def top_domains(self, *, refresh_index: int = 0, limit: int = 10) -> list[HotspotCandidate]:
        rotated = _rotate(MAINSTREAM_DOMAINS, refresh_index * limit)
        candidates: list[HotspotCandidate] = []
        for domain in rotated[: limit + 4]:
            candidates.extend(self._collect_for_query(domain, domain, refresh_index, limit=6))
        scored = _merge_by_domain(candidates)
        return scored[:limit]

    def top_hotspots(self, domain: str, *, refresh_index: int = 0, limit: int = 10) -> list[HotspotCandidate]:
        if self.collector:
            return self.hotspot_filter.filter(self.collector(domain, refresh_index))[:limit]
        seeds = _rotate(DOMAIN_HOTSPOT_SEEDS, refresh_index * 3)
        candidates: list[HotspotCandidate] = []
        for seed in seeds[:6]:
            candidates.extend(self._collect_for_query(f"{domain} {seed}", domain, refresh_index, limit=8))
        merged = _merge_similar(candidates)
        return self.hotspot_filter.filter(merged)[:limit]

    def _collect_for_query(self, query: str, domain: str, refresh_index: int, *, limit: int) -> list[HotspotCandidate]:
        payload = self.client.collect(query, limit=limit + refresh_index * 2)
        rows = payload.get("items", [])
        out: list[HotspotCandidate] = []
        for row in rows:
            title = _normalize_title(str(row.get("title", "")))
            if not title:
                continue
            meta = row.get("meta") or {}
            source = str(row.get("source", "public"))
            evidence_parts = [f"{source} score={row.get('score', 0):.0f}"]
            if isinstance(meta, dict):
                for key in ("stars", "forks", "comments", "score", "volume", "liquidity", "language"):
                    value = meta.get(key)
                    if value not in (None, ""):
                        evidence_parts.append(f"{key}={value}")
            snippet = str(row.get("snippet") or "")
            if snippet:
                evidence_parts.append(_short(snippet, 90))
            out.append(
                HotspotCandidate(
                    title=title,
                    domain=domain,
                    score=float(row.get("score") or 0),
                    sources=[source],
                    evidence="; ".join(evidence_parts),
                    source_urls=[str(row.get("url", ""))] if row.get("url") else [],
                )
            )
        return out


def _rotate(items: list[str], offset: int) -> list[str]:
    if not items:
        return []
    n = offset % len(items)
    return items[n:] + items[:n]


def _normalize_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r"^[\[\(].*?[\]\)]\s*", "", title)
    return _short(title, 90)


def _short(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _merge_similar(candidates: list[HotspotCandidate]) -> list[HotspotCandidate]:
    buckets: dict[str, HotspotCandidate] = {}
    for item in candidates:
        key = re.sub(r"[^\w\u4e00-\u9fff]+", "", item.title.lower())[:28] or item.title.lower()
        existing = buckets.get(key)
        if not existing:
            buckets[key] = item
            continue
        buckets[key] = HotspotCandidate(
            title=existing.title if existing.score >= item.score else item.title,
            domain=existing.domain,
            score=existing.score + item.score * 0.35,
            sources=sorted(set(existing.sources + item.sources)),
            evidence="; ".join(dict.fromkeys((existing.evidence + "; " + item.evidence).split("; "))),
            source_urls=list(dict.fromkeys(existing.source_urls + item.source_urls)),
        )
    return sorted(buckets.values(), key=lambda c: c.score, reverse=True)


def _merge_by_domain(candidates: list[HotspotCandidate]) -> list[HotspotCandidate]:
    by_domain: dict[str, HotspotCandidate] = {}
    for item in candidates:
        existing = by_domain.get(item.domain)
        if not existing:
            by_domain[item.domain] = HotspotCandidate(
                title=item.domain,
                domain=item.domain,
                score=item.score,
                sources=item.sources,
                evidence=item.evidence,
                source_urls=item.source_urls,
            )
            continue
        by_domain[item.domain] = HotspotCandidate(
            title=item.domain,
            domain=item.domain,
            score=existing.score + item.score,
            sources=sorted(set(existing.sources + item.sources)),
            evidence=existing.evidence,
            source_urls=list(dict.fromkeys(existing.source_urls + item.source_urls)),
        )
    return sorted(by_domain.values(), key=lambda c: c.score, reverse=True)
