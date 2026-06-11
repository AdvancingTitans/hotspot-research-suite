#!/usr/bin/env python3
"""Safe public-source last-30-days research helper.

No cookies, no Keychain, no environment credential discovery, no subprocesses,
no persistent writes. Uses only Python standard library and public HTTP APIs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Iterable

USER_AGENT = "Hermes-last30days-safe/1.0 (+public research; no auth)"
DEFAULT_SOURCES = ("hn", "github", "reddit", "polymarket")


@dataclass
class Item:
    source: str
    title: str
    url: str
    published: str | None = None
    score: float = 0.0
    snippet: str | None = None
    meta: dict[str, Any] | None = None


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def cutoff_iso(days: int) -> str:
    return (utc_now() - dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            d = dt.datetime.fromisoformat(s)
            return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pass
        try:
            d = email.utils.parsedate_to_datetime(value)
            return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        except Exception:
            return None
    return None


def within_days(value: Any, days: int) -> bool:
    d = parse_time(value)
    if d is None:
        return True
    return d >= utc_now() - dt.timedelta(days=days)


def clean_text(value: Any, limit: int = 500) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def http_json(url: str, timeout: int = 15) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec: public user-selected URLs only from fixed API bases
        raw = resp.read(2_000_000)
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(raw.decode(charset, errors="replace"))


def hn_search(topic: str, days: int, limit: int) -> list[Item]:
    since = int((utc_now() - dt.timedelta(days=days)).timestamp())
    q = urllib.parse.urlencode({
        "query": topic,
        "tags": "story,comment",
        "numericFilters": f"created_at_i>{since}",
        "hitsPerPage": min(max(limit, 1), 50),
    })
    data = http_json(f"https://hn.algolia.com/api/v1/search_by_date?{q}")
    out: list[Item] = []
    for h in data.get("hits", []):
        title = clean_text(h.get("title") or h.get("story_title") or h.get("comment_text"), 160)
        if not title:
            continue
        object_id = h.get("objectID")
        url = h.get("url") or (f"https://news.ycombinator.com/item?id={object_id}" if object_id else "https://news.ycombinator.com/")
        pts = h.get("points") or 0
        comments = h.get("num_comments") or 0
        out.append(Item(
            source="hn",
            title=title,
            url=url,
            published=h.get("created_at"),
            score=float(pts) + float(comments) * 0.5,
            snippet=clean_text(h.get("comment_text") or h.get("story_text"), 260) or None,
            meta={"points": pts, "comments": comments},
        ))
    return out


def github_search(topic: str, days: int, limit: int) -> list[Item]:
    created = (utc_now() - dt.timedelta(days=days)).date().isoformat()
    q = f"{topic} created:>={created}"
    params = urllib.parse.urlencode({"q": q, "sort": "updated", "order": "desc", "per_page": min(max(limit, 1), 30)})
    data = http_json(f"https://api.github.com/search/repositories?{params}")
    out: list[Item] = []
    for r in data.get("items", []):
        out.append(Item(
            source="github",
            title=clean_text(r.get("full_name"), 180),
            url=r.get("html_url") or "https://github.com/",
            published=r.get("created_at") or r.get("updated_at"),
            score=float(r.get("stargazers_count") or 0) + float(r.get("forks_count") or 0) * 0.5,
            snippet=clean_text(r.get("description"), 260) or None,
            meta={"stars": r.get("stargazers_count"), "forks": r.get("forks_count"), "language": r.get("language")},
        ))
    return out


def reddit_search(topic: str, days: int, limit: int) -> list[Item]:
    params = urllib.parse.urlencode({"q": topic, "sort": "new", "restrict_sr": "false", "limit": min(max(limit, 1), 25), "t": "month"})
    data = http_json(f"https://www.reddit.com/search.json?{params}")
    out: list[Item] = []
    for child in data.get("data", {}).get("children", []):
        p = child.get("data", {})
        created = p.get("created_utc")
        if not within_days(created, days):
            continue
        permalink = p.get("permalink") or ""
        out.append(Item(
            source="reddit",
            title=clean_text(p.get("title"), 180),
            url=("https://www.reddit.com" + permalink) if permalink.startswith("/") else (p.get("url") or "https://www.reddit.com/"),
            published=parse_time(created).isoformat().replace("+00:00", "Z") if parse_time(created) else None,
            score=float(p.get("score") or 0) + float(p.get("num_comments") or 0) * 0.5,
            snippet=clean_text(p.get("selftext"), 260) or None,
            meta={"subreddit": p.get("subreddit"), "comments": p.get("num_comments"), "score": p.get("score")},
        ))
    return [i for i in out if i.title]


def polymarket_search(topic: str, days: int, limit: int) -> list[Item]:
    params = urllib.parse.urlencode({"search": topic, "limit": min(max(limit, 1), 50), "active": "true"})
    data = http_json(f"https://gamma-api.polymarket.com/markets?{params}")
    if isinstance(data, dict):
        rows = data.get("markets") or data.get("data") or []
    else:
        rows = data or []
    out: list[Item] = []
    for m in rows:
        title = clean_text(m.get("question") or m.get("title") or m.get("slug"), 180)
        if not title:
            continue
        created = m.get("createdAt") or m.get("created_at") or m.get("startDate")
        if created and not within_days(created, days):
            continue
        slug = m.get("slug") or m.get("marketSlug") or ""
        url = m.get("url") or (f"https://polymarket.com/market/{slug}" if slug else "https://polymarket.com/markets")
        volume = m.get("volume") or m.get("volumeNum") or 0
        liquidity = m.get("liquidity") or m.get("liquidityNum") or 0
        try:
            score = float(volume or 0) + float(liquidity or 0) * 0.1
        except Exception:
            score = 0.0
        out.append(Item(
            source="polymarket",
            title=title,
            url=url,
            published=created,
            score=score,
            snippet=clean_text(m.get("description"), 260) or None,
            meta={"volume": volume, "liquidity": liquidity, "endDate": m.get("endDate")},
        ))
    return out


SOURCE_FUNCS = {
    "hn": hn_search,
    "github": github_search,
    "reddit": reddit_search,
    "polymarket": polymarket_search,
}


def collect(topic: str, sources: Iterable[str], days: int, limit: int) -> tuple[list[Item], list[str]]:
    items: list[Item] = []
    warnings: list[str] = []
    for src in sources:
        fn = SOURCE_FUNCS.get(src)
        if not fn:
            warnings.append(f"unknown source skipped: {src}")
            continue
        try:
            items.extend(fn(topic, days, limit))
        except urllib.error.HTTPError as e:
            warnings.append(f"{src}: HTTP {e.code} {e.reason}")
        except urllib.error.URLError as e:
            warnings.append(f"{src}: network error {e.reason}")
        except Exception as e:
            warnings.append(f"{src}: {type(e).__name__}: {e}")
        time.sleep(0.15)
    items.sort(key=lambda i: (i.score, i.published or ""), reverse=True)
    return items[: max(limit, 1)], warnings


def render_markdown(topic: str, sources: list[str], days: int, items: list[Item], warnings: list[str]) -> str:
    counts: dict[str, int] = {}
    for it in items:
        counts[it.source] = counts.get(it.source, 0) + 1
    lines = [
        f"# Last {days} days: {topic}",
        "",
        "Safe mode: public endpoints only; no cookies, Keychain, env credentials, subprocesses, or local writes.",
        "",
        "## Source counts",
    ]
    for s in sources:
        lines.append(f"- {s}: {counts.get(s, 0)}")
    if warnings:
        lines += ["", "## Warnings"] + [f"- {w}" for w in warnings]
    lines += ["", "## Top items"]
    if not items:
        lines.append("No items found.")
    for idx, it in enumerate(items, 1):
        when = f" · {it.published}" if it.published else ""
        score = f" · score {it.score:.0f}" if it.score else ""
        lines.append(f"{idx}. [{it.source}] {it.title}{when}{score}")
        lines.append(f"   {it.url}")
        if it.snippet:
            lines.append(f"   {it.snippet}")
        if it.meta:
            compact = ", ".join(f"{k}={v}" for k, v in it.meta.items() if v not in (None, ""))
            if compact:
                lines.append(f"   meta: {compact}")
    return "\n".join(lines) + "\n"


def diagnose(sources: list[str], days: int, limit: int) -> int:
    result: dict[str, Any] = {
        "safe_mode": True,
        "python": sys.version.split()[0],
        "sources_requested": sources,
        "days": days,
        "checks": {},
        "security": {
            "reads_browser_cookies": False,
            "reads_keychain": False,
            "reads_env_credentials": False,
            "uses_subprocess": False,
            "writes_files": False,
        },
    }
    for src in sources:
        try:
            items, warnings = collect("Hermes Agent", [src], days, min(limit, 3))
            result["checks"][src] = {"ok": not warnings, "items": len(items), "warnings": warnings}
        except Exception as e:
            result["checks"][src] = {"ok": False, "items": 0, "warnings": [f"{type(e).__name__}: {e}"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def parse_sources(value: str) -> list[str]:
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    return parts or list(DEFAULT_SOURCES)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Safe public-source last-30-days research helper")
    ap.add_argument("topic", nargs="?", help="topic to research")
    ap.add_argument("--sources", default=",".join(DEFAULT_SOURCES), help="comma-separated sources: hn,github,reddit,polymarket")
    ap.add_argument("--days", type=int, default=30, help="lookback days, default 30")
    ap.add_argument("--limit", type=int, default=20, help="max final items, default 20")
    ap.add_argument("--emit", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--diagnose", action="store_true", help="check source availability without credentials")
    args = ap.parse_args(argv)

    sources = parse_sources(args.sources)
    if args.diagnose:
        return diagnose(sources, args.days, args.limit)
    if not args.topic:
        ap.error("topic is required unless --diagnose is used")
    items, warnings = collect(args.topic, sources, args.days, args.limit)
    if args.emit == "json":
        payload = {
            "topic": args.topic,
            "days": args.days,
            "safe_mode": True,
            "sources": sources,
            "items": [asdict(i) for i in items],
            "warnings": warnings,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(args.topic, sources, args.days, items, warnings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
