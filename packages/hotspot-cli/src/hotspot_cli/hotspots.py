from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


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

DOMAIN_QUERY_MAP = {
    "人工智能": "AI agent",
    "具身智能": "humanoid robot",
    "半导体": "AI chip",
    "新能源汽车": "EV battery",
    "生物医药": "biotech clinical",
    "绿色能源": "solar storage",
    "低空经济": "eVTOL drone",
    "机器人": "robotics humanoid",
    "量子计算": "quantum computing",
    "商业航天": "commercial space",
    "数据中心": "AI data center",
    "网络安全": "cybersecurity vulnerability",
    "储能": "energy storage",
    "智能制造": "industrial automation",
    "金融科技": "fintech payment",
}

DOMAIN_HOTSPOT_SEEDS = [
    "policy regulation standard",
    "funding investment acquisition",
    "market size shipment CAGR",
    "breakthrough paper benchmark arxiv",
    "product launch release GA",
    "supply chain capacity cost",
    "industry partnership order deployment",
    "open source GitHub release",
    "trial approval FDA clinical",
    "export control international competition",
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
    "gta",
    "album",
    "rihanna",
    "playboi",
    "bitcoin hit",
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

    def collect(self, topic: str, *, limit: int = 20, days: int = 30) -> dict:
        if self.script_path.exists():
            argv = [str(self.python_bin), str(self.script_path)]
        else:
            argv = [str(self.python_bin), "-m", PACKAGE_LAST30_MODULE]
        argv.extend([topic, "--emit", "json", "--limit", str(limit), "--days", str(days), "--sources", self.sources])
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


class PublicSignalClient:
    """Collect objective public signals without requiring private accounts."""

    def __init__(self, timeout: int = 16) -> None:
        self.timeout = timeout
        self.github_token_file = Path(os.environ.get("GITHUB_TOKEN_FILE", str(Path.home() / ".config" / "github" / "token")))

    def collect(self, query: str, domain: str, *, limit: int, refresh_index: int = 0) -> list[HotspotCandidate]:
        out: list[HotspotCandidate] = []
        collectors = (self._github, self._hn, self._arxiv, self._reddit)
        for fn in collectors:
            try:
                out.extend(fn(query, domain, limit=max(2, limit // 2), refresh_index=refresh_index))
            except Exception:
                continue
            time.sleep(0.08)
        return sorted(out, key=lambda item: item.score, reverse=True)[:limit]

    def _json(self, url: str) -> Any:
        headers = {
            "User-Agent": "hotspot-research-cli/0.1 (+public research)",
            "Accept": "application/json,text/plain;q=0.8,*/*;q=0.5",
        }
        if "api.github.com" in url and self.github_token_file.exists():
            token = self.github_token_file.read_text(encoding="utf-8").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec: fixed public API bases
            raw = resp.read(2_000_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            return json.loads(raw.decode(charset, errors="replace"))

    def _text(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "hotspot-research-cli/0.1 (+public research)"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec: fixed public API bases
            raw = resp.read(2_000_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")

    def _github(self, query: str, domain: str, *, limit: int, refresh_index: int) -> list[HotspotCandidate]:
        page = refresh_index + 1
        pushed_after = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 30 * 86400))
        q = f"{query} pushed:>={pushed_after} stars:>50"
        params = urllib.parse.urlencode({"q": q, "sort": "stars", "order": "desc", "per_page": min(limit, 10), "page": page})
        data = self._json(f"https://api.github.com/search/repositories?{params}")
        rows = data.get("items", []) if isinstance(data, dict) else []
        out = []
        for repo in rows:
            title = str(repo.get("full_name") or "").strip()
            url = str(repo.get("html_url") or "").strip()
            if not title or not url:
                continue
            description = str(repo.get("description") or "")
            topics = " ".join(str(topic) for topic in (repo.get("topics") or []))
            if not _is_relevant_signal(query, title, description, topics):
                continue
            stars = int(repo.get("stargazers_count") or 0)
            forks = int(repo.get("forks_count") or 0)
            issues = int(repo.get("open_issues_count") or 0)
            score = min(stars, 5000) * 0.08 + min(forks, 1200) * 0.12 + min(issues, 500) * 0.04
            desc = _short(description, 120)
            evidence = f"GitHub stars={stars}; forks={forks}; issues={issues}; updated={repo.get('updated_at')}; {desc}".strip("; ")
            out.append(HotspotCandidate(title=title, domain=domain, score=score, sources=["github"], evidence=evidence, source_urls=[url]))
        return out

    def _hn(self, query: str, domain: str, *, limit: int, refresh_index: int) -> list[HotspotCandidate]:
        since = int(time.time() - 30 * 86400)
        params = urllib.parse.urlencode({
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{since}",
            "hitsPerPage": min(limit, 10),
            "page": refresh_index,
        })
        data = self._json(f"https://hn.algolia.com/api/v1/search_by_date?{params}")
        rows = data.get("hits", []) if isinstance(data, dict) else []
        out = []
        for item in rows:
            title = _short(str(item.get("title") or item.get("story_title") or ""), 100)
            object_id = item.get("objectID")
            url = str(item.get("url") or (f"https://news.ycombinator.com/item?id={object_id}" if object_id else "")).strip()
            if not title or not url:
                continue
            points = int(item.get("points") or 0)
            comments = int(item.get("num_comments") or 0)
            score = points * 1.5 + comments
            evidence = f"Hacker News points={points}; comments={comments}; created={item.get('created_at')}"
            out.append(HotspotCandidate(title=title, domain=domain, score=score, sources=["hn"], evidence=evidence, source_urls=[url]))
        return out

    def _arxiv(self, query: str, domain: str, *, limit: int, refresh_index: int) -> list[HotspotCandidate]:
        start = refresh_index * limit
        params = urllib.parse.urlencode({
            "search_query": f"all:{query}",
            "start": start,
            "max_results": min(limit, 8),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
        text = self._text(f"https://export.arxiv.org/api/query?{params}")
        root = ET.fromstring(text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out = []
        for entry in root.findall("a:entry", ns):
            title = _short(" ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split()), 120)
            url = entry.findtext("a:id", default="", namespaces=ns) or ""
            published = entry.findtext("a:published", default="", namespaces=ns) or ""
            summary = _short(" ".join((entry.findtext("a:summary", default="", namespaces=ns) or "").split()), 120)
            if not title or not url:
                continue
            score = 18 - min(refresh_index * 3, 12)
            evidence = f"arXiv submitted={published}; paper signal; {summary}"
            out.append(HotspotCandidate(title=title, domain=domain, score=score, sources=["arxiv"], evidence=evidence, source_urls=[url]))
        return out

    def _reddit(self, query: str, domain: str, *, limit: int, refresh_index: int) -> list[HotspotCandidate]:
        after = "" if refresh_index == 0 else None
        params = {"q": query, "sort": "new", "restrict_sr": "false", "limit": min(limit, 10), "t": "month"}
        if after:
            params["after"] = after
        data = self._json(f"https://www.reddit.com/search.json?{urllib.parse.urlencode(params)}")
        children = data.get("data", {}).get("children", []) if isinstance(data, dict) else []
        out = []
        skip = refresh_index * limit
        for child in children[skip: skip + limit] if refresh_index else children:
            p = child.get("data", {})
            title = _short(str(p.get("title") or ""), 100)
            permalink = str(p.get("permalink") or "")
            url = "https://www.reddit.com" + permalink if permalink.startswith("/") else str(p.get("url") or "")
            if not title or not url:
                continue
            score = float(p.get("score") or 0) + float(p.get("num_comments") or 0) * 0.6
            evidence = f"Reddit score={p.get('score') or 0}; comments={p.get('num_comments') or 0}; subreddit={p.get('subreddit')}"
            out.append(HotspotCandidate(title=title, domain=domain, score=score, sources=["reddit"], evidence=evidence, source_urls=[url]))
        return out

    def _polymarket(self, query: str, domain: str, *, limit: int, refresh_index: int) -> list[HotspotCandidate]:
        params = urllib.parse.urlencode({"search": query, "limit": min(limit + refresh_index * limit, 30), "active": "true"})
        data = self._json(f"https://gamma-api.polymarket.com/markets?{params}")
        rows = data.get("markets") if isinstance(data, dict) else data
        rows = rows or []
        out = []
        for market in rows[refresh_index * limit: refresh_index * limit + limit]:
            title = _short(str(market.get("question") or market.get("title") or ""), 100)
            slug = str(market.get("slug") or market.get("marketSlug") or "")
            url = str(market.get("url") or (f"https://polymarket.com/market/{slug}" if slug else ""))
            if not title or not url:
                continue
            volume = float(market.get("volume") or market.get("volumeNum") or 0)
            liquidity = float(market.get("liquidity") or market.get("liquidityNum") or 0)
            score = volume * 0.01 + liquidity * 0.02
            evidence = f"Polymarket volume={volume:.0f}; liquidity={liquidity:.0f}; end={market.get('endDate')}"
            out.append(HotspotCandidate(title=title, domain=domain, score=score, sources=["polymarket"], evidence=evidence, source_urls=[url]))
        return out


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
        collector: Optional[Callable[[str, int], list[HotspotCandidate]]] = None,
        client: Optional[Last30DaysClient] = None,
        hotspot_filter: Optional[HotspotFilter] = None,
        signal_client: Optional[PublicSignalClient] = None,
    ) -> None:
        self.client = client or Last30DaysClient()
        self.signal_client = signal_client or PublicSignalClient()
        self.hotspot_filter = hotspot_filter or HotspotFilter()
        self.collector = collector

    def top_domains(self, *, refresh_index: int = 0, limit: int = 10) -> list[HotspotCandidate]:
        rotated = _rotate(MAINSTREAM_DOMAINS, refresh_index * limit)
        candidates: list[HotspotCandidate] = []
        for domain in rotated[:limit]:
            query = DOMAIN_QUERY_MAP.get(domain, domain)
            signals = self.signal_client.collect(query, domain, limit=4, refresh_index=refresh_index)
            if signals:
                score = sum(item.score for item in signals[:3])
                sources = sorted({src for item in signals for src in item.sources})
                urls = list(dict.fromkeys(url for item in signals for url in item.source_urls))[:5]
                evidence = "; ".join(dict.fromkeys(item.evidence for item in signals[:2]))
                candidates.append(HotspotCandidate(domain, domain, score, sources, evidence, urls))
        scored = _merge_by_domain(candidates)
        return scored[:limit]

    def top_hotspots(self, domain: str, *, refresh_index: int = 0, limit: int = 10) -> list[HotspotCandidate]:
        if self.collector:
            return self.hotspot_filter.filter(self.collector(domain, refresh_index))[:limit]
        seeds = _rotate(DOMAIN_HOTSPOT_SEEDS, refresh_index * 4)
        base_query = DOMAIN_QUERY_MAP.get(domain, domain)
        candidates: list[HotspotCandidate] = []
        candidates.extend(self.signal_client.collect(base_query, domain, limit=10, refresh_index=refresh_index))
        for seed in seeds[:4]:
            candidates.extend(self.signal_client.collect(f"{base_query} {seed}", domain, limit=8, refresh_index=refresh_index))
        if not candidates:
            candidates.extend(self._collect_for_query(f"{domain} 最近30天 热点", domain, refresh_index, limit=12))
        merged = _merge_similar(candidates)
        filtered = self.hotspot_filter.filter(merged)
        return (filtered or merged)[:limit]

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


def _is_relevant_signal(query: str, *fields: str) -> bool:
    haystack = " ".join(fields).lower()
    tokens = [token for token in re.findall(r"[a-z0-9]{2,}", query.lower()) if token not in {"the", "and", "for", "with"}]
    if not tokens:
        return True
    if "agent" in tokens and not re.search(r"\b(agent|agents|agentic|llm|rag|workflow|automation)\b", haystack):
        return False
    strong_tokens = [token for token in tokens if len(token) >= 4]
    if any(token in haystack for token in strong_tokens):
        return True
    if "ai" in tokens and re.search(r"\b(ai|llm|agent|agents|model|models)\b", haystack):
        return True
    return sum(1 for token in tokens if token in haystack) >= min(2, len(tokens))


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
