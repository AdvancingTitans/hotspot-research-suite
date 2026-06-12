from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .hotspots import HotspotCandidate
from .skill import ensure_hotspot_skill_installed


DEFAULT_SKILL_DIR = Path.home() / ".codex" / "skills" / "hotspot-research"


@dataclass(frozen=True)
class ReportResult:
    topic: str
    markdown_path: Path
    html_path: Path
    pdf_path: Optional[Path]
    summary: str


class ReportError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceEvidence:
    url: str
    kind: str
    title: str
    publisher: str
    published: str
    facts: list[str]
    excerpt: str = ""


class ReportGenerator:
    def __init__(self, output_dir: Optional[Path] = None, skill_dir: Optional[Path] = None, source_researcher: Optional[Any] = None) -> None:
        self.output_dir = (output_dir or Path.cwd() / "reports").resolve()
        self.skill_dir = skill_dir
        self.source_researcher = source_researcher or SourceResearcher()

    def generate(self, candidate: HotspotCandidate, *, language: str = "zh") -> ReportResult:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise ReportError(f"无法创建报告目录：{self.output_dir}。请检查写入权限。") from exc

        skill_dir = ensure_hotspot_skill_installed(self.skill_dir or DEFAULT_SKILL_DIR)
        slug = _slugify(candidate.title)
        md_path = (self.output_dir / f"{slug}.md").resolve()
        html_path = (self.output_dir / f"{slug}.html").resolve()
        pdf_path = (self.output_dir / f"{slug}.pdf").resolve()
        summary = _summary(candidate)
        sources = self.source_researcher.collect(candidate.source_urls)
        md_path.write_text(_render_markdown(candidate, summary, language, sources, skill_dir), encoding="utf-8")
        self._render_html(md_path, html_path, skill_dir)
        pdf_result = self._render_pdf(html_path, pdf_path)
        return ReportResult(candidate.title, md_path, html_path, pdf_result, summary)

    def _render_html(self, md_path: Path, html_path: Path, skill_dir: Path) -> None:
        script = skill_dir / "scripts" / "simple_report_html.py"
        if script.exists():
            proc = subprocess.run(["python3", str(script), str(md_path), str(html_path)], capture_output=True, text=True)
            if proc.returncode == 0:
                return
        proc = subprocess.run([sys.executable, "-m", "hotspot_cli.simple_report_html", str(md_path), str(html_path)], capture_output=True, text=True)
        if proc.returncode == 0:
            return
        html_path.write_text("<pre>" + md_path.read_text(encoding="utf-8") + "</pre>", encoding="utf-8")

    def _render_pdf(self, html_path: Path, pdf_path: Path) -> Optional[Path]:
        skill_dir = self.skill_dir or DEFAULT_SKILL_DIR
        script = skill_dir / "scripts" / "render_pdf_weasy.py"
        if script.exists():
            argv = ["python3", str(script), str(html_path), str(pdf_path)]
        else:
            argv = [sys.executable, "-m", "hotspot_cli.render_pdf_weasy", str(html_path), str(pdf_path)]
        proc = subprocess.run(argv, capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        return pdf_path if pdf_path.exists() else None


class SourceResearcher:
    def __init__(self, timeout: int = 14) -> None:
        self.timeout = timeout
        self.github_token_file = Path(os.environ.get("GITHUB_TOKEN_FILE", str(Path.home() / ".config" / "github" / "token")))

    def collect(self, urls: list[str]) -> list[SourceEvidence]:
        out: list[SourceEvidence] = []
        for url in urls[:12]:
            try:
                out.append(self.fetch(url))
            except Exception:
                out.append(SourceEvidence(url=url, kind="public", title=_url_label(url), publisher=_publisher(url), published="暂未确认", facts=["来源可访问性或解析失败，保留 URL 供人工复核。"]))
        return out

    def fetch(self, url: str) -> SourceEvidence:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host == "github.com" and len(parsed.path.strip("/").split("/")) >= 2:
            return self._github(url)
        if host in {"arxiv.org", "export.arxiv.org"}:
            return self._arxiv(url)
        if "news.ycombinator.com" in host:
            return self._hn(url)
        return self._generic(url)

    def _json(self, url: str) -> Any:
        headers = {"User-Agent": "hotspot-research-cli/0.1.3 (+source enrichment)", "Accept": "application/json,text/plain;q=0.8,*/*;q=0.5"}
        if "api.github.com" in url and self.github_token_file.exists():
            token = self.github_token_file.read_text(encoding="utf-8").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec: fixed public source URLs
            raw = resp.read(2_000_000)
            return json.loads(raw.decode(resp.headers.get_content_charset() or "utf-8", errors="replace"))

    def _text(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "hotspot-research-cli/0.1.3 (+source enrichment)"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec: public source URLs from candidate list
            raw = resp.read(1_500_000)
            return raw.decode(resp.headers.get_content_charset() or "utf-8", errors="replace")

    def _github(self, url: str) -> SourceEvidence:
        parts = urllib.parse.urlparse(url).path.strip("/").split("/")
        owner, repo = parts[0], parts[1]
        data = self._json(f"https://api.github.com/repos/{owner}/{repo}")
        topics = data.get("topics") or []
        facts = [
            f"stars={int(data.get('stargazers_count') or 0):,}",
            f"forks={int(data.get('forks_count') or 0):,}",
            f"open_issues={int(data.get('open_issues_count') or 0):,}",
            f"created_at={data.get('created_at') or 'n/a'}",
            f"updated_at={data.get('updated_at') or 'n/a'}",
            f"pushed_at={data.get('pushed_at') or 'n/a'}",
            f"language={data.get('language') or 'n/a'}",
            f"license={(data.get('license') or {}).get('spdx_id') or 'n/a'}",
        ]
        if topics:
            facts.append("topics=" + ", ".join(str(topic) for topic in topics[:8]))
        return SourceEvidence(
            url=url,
            kind="github",
            title=str(data.get("full_name") or f"{owner}/{repo}"),
            publisher="GitHub API",
            published=str(data.get("created_at") or "暂未确认"),
            facts=facts,
            excerpt=_short_sentence(str(data.get("description") or ""), 260),
        )

    def _arxiv(self, url: str) -> SourceEvidence:
        match = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", url)
        paper_id = match.group(1) if match else url.rstrip("/").split("/")[-1]
        text = self._text(f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(paper_id)}")
        root = ET.fromstring(text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", ns)
        if entry is None:
            raise ReportError(f"无法解析 arXiv 来源：{url}")
        title = " ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split())
        published = entry.findtext("a:published", default="", namespaces=ns) or "暂未确认"
        authors = [node.findtext("a:name", default="", namespaces=ns) or "" for node in entry.findall("a:author", ns)]
        summary = " ".join((entry.findtext("a:summary", default="", namespaces=ns) or "").split())
        facts = [f"paper_id={paper_id}", f"submitted={published}", "authors=" + ", ".join([a for a in authors if a][:6])]
        return SourceEvidence(url=url, kind="arxiv", title=title or paper_id, publisher="arXiv", published=published, facts=facts, excerpt=_short_sentence(summary, 420))

    def _hn(self, url: str) -> SourceEvidence:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        item_id = (query.get("id") or [""])[0]
        data = self._json(f"https://hn.algolia.com/api/v1/items/{urllib.parse.quote(item_id)}") if item_id else {}
        title = str(data.get("title") or _url_label(url))
        facts = [f"points={data.get('points') or 0}", f"comments={len(data.get('children') or [])}", f"created_at={data.get('created_at') or 'n/a'}"]
        if data.get("url"):
            facts.append(f"linked_url={data.get('url')}")
        return SourceEvidence(url=url, kind="hn", title=title, publisher="Hacker News", published=str(data.get("created_at") or "暂未确认"), facts=facts, excerpt="HN 讨论只能作为热度与实践问题发现线索，关键事实仍需回到原始链接复核。")

    def _generic(self, url: str) -> SourceEvidence:
        text = self._text(url)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', text, re.I | re.S)
        title = _clean_html(title_match.group(1)) if title_match else _url_label(url)
        excerpt = _clean_html(desc_match.group(1)) if desc_match else ""
        return SourceEvidence(url=url, kind="web", title=title, publisher=_publisher(url), published="暂未确认", facts=["已抓取页面标题/摘要；发布日期和核心数据需人工复核。"], excerpt=_short_sentence(excerpt, 320))


def _render_markdown(candidate: HotspotCandidate, summary: str, language: str, sources: list[SourceEvidence], skill_dir: Path) -> str:
    today = dt.date.today().isoformat()
    start = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    if language == "en":
        return _render_deep_markdown_en(candidate, summary, start, today, sources, skill_dir)
    return _render_deep_markdown_zh(candidate, summary, start, today, sources, skill_dir)


def _render_deep_markdown_zh(candidate: HotspotCandidate, summary: str, start: str, today: str, sources: list[SourceEvidence], skill_dir: Path) -> str:
    signals = _signal_table(candidate)
    source_table = _source_table(candidate, sources)
    source_profiles = _source_profiles(sources)
    skill_basis = _skill_basis(skill_dir)
    source_types = "、".join(candidate.sources) if candidate.sources else "公开来源"
    evidence_quality = _evidence_quality(candidate)
    return f"""# {candidate.title}：近30天热点研究报告

> 研究窗口：{start} 至 {today}  
> 研究模式：Domain-Specific / Hotspot-Guided  
> 领域：{candidate.domain}  
> 输出语言：中文，关键术语中英对照  
> 访问日期：{today}  
> 证据来源类型：{source_types}  
> 报告框架：内嵌 hotspot-research skill（{skill_dir}）  

## 执行摘要

| 项目 | 结论 |
|---|---|
| 一句话定义 | 「{candidate.title}」是最近 30 天在「{candidate.domain}」赛道中由公开数据源捕捉到的高信号研究主题。它的价值不只来自讨论热度，而来自可追踪的客观信号：{_short_sentence(candidate.evidence)} |
| 热点判断 | 当前热度由 {source_types} 共同支撑，热点评分为 {candidate.score:.0f}。这说明它至少已经形成可被外部观察的开发者、媒体、论文、社区或产业活动，而不是单纯概念炒作。 |
| 核心问题 | 本报告重点回答三个问题：第一，最近 30 天为什么是观察窗口；第二，这个热点在历史路径上处于哪个阶段；第三，横向竞争或替代路径如何影响未来 30-90 天走势。 |
| 证据边界 | {evidence_quality} 本报告不会把单一来源的热度直接解释为收入、市场份额或长期胜负；未能从现有来源直接确认的内容会放入“未确认与后续验证”。 |
| 初步判断 | 该主题适合进入正式研究，因为它具备“近期触发 + 可验证来源 + 后续可跟踪指标”三项条件。进一步研究应优先补充官方公告、监管/政策文件、市场规模口径、企业案例与财务数据。 |

## 报告生成依据

本报告由 CLI 内嵌的 `hotspot-research` skill 生成。该 skill 已随 Python 包安装到本机，不依赖用户额外安装 Codex、Hermes 或其他 agent 框架。CLI 负责三件事：第一，安装并读取 skill 的结构化研究框架；第二，对候选热点的 URL 做二次取证；第三，将已确认事实、推断和未确认事项分层写入报告。

{skill_basis}

## 一句话定义

「{candidate.title}」可以被定义为：在「{candidate.domain}」领域内，最近 30 天被公开数据源捕捉到，并且已经出现可度量信号的研究对象。这里的可度量信号包括但不限于 GitHub stars/forks/issues、论文提交或引用、Hacker News / Reddit 讨论量、新闻报道密度、政策或监管文本、融资与订单、产品发布、开源 release、标准制定和公开客户案例。

这个定义刻意避开“很火”“大家都在聊”这类不可验证表达。对研究报告而言，热点只有在能被拆解为时间、主体、事件、数据和来源时才值得进入深度分析。换句话说，本报告把热点视为一个可以复核的产业信号，而不是一个标题。

## 选题理由

| 维度 | 评分 | 当前证据 | 解释 |
|---|---:|---|---|
| 近30天新闻与媒体覆盖 | {_dimension_score(candidate, "media")} | 来源类型包含：{source_types} | 若后续补充权威媒体或官方公告，可进一步判断这是否是单点事件还是持续议题。 |
| 技术里程碑或产品发布 | {_dimension_score(candidate, "tech")} | {signals} | GitHub、论文或开发者社区信号通常意味着该主题有工程可验证性，适合做技术路线与生态分析。 |
| 社交/搜索/开发者兴趣 | {_dimension_score(candidate, "social")} | 热点评分 {candidate.score:.0f}；来源：{source_types} | 分数不是结论，只是筛选优先级。真正的结论必须回到来源本身。 |
| 政策/监管变化 | {_dimension_score(candidate, "policy")} | 当前候选证据中未必包含官方政策文本 | 如涉及金融、医疗、数据、自动驾驶、低空经济、能源等高监管行业，需要强制补充官方来源。 |
| 资本流入与商业化 | {_dimension_score(candidate, "capital")} | 当前候选证据中未必包含融资、订单或收入数据 | 若没有资本或收入证据，应避免把热度写成确定性商业爆发。 |
| 市场增长潜力 | {_dimension_score(candidate, "market")} | 可通过 TAM/SAM/SOM、CAGR、渗透率、成本曲线进一步验证 | 当前报告先给出研究框架，不编造市场规模。 |
| 证据质量 | {_dimension_score(candidate, "evidence")} | {evidence_quality} | 有 URL 和数据字段的候选优先级高于只有标题或转述的候选。 |

本主题被选中，不是因为它看起来“热”，而是因为它已经暴露出足够的可追踪对象：标题、领域、来源类型、URL、评分和数据依据。一个合格的研究选题必须能被继续追问：谁推动了它、什么时候发生、发生了什么、数据从哪里来、还有哪些口径冲突。

## 纵向分析：从诞生到当下

### 1. 问题背景

任何产业热点都会经历从“概念出现”到“形成可交易、可部署、可监管对象”的过程。对于「{candidate.title}」而言，当前最重要的研究切入点不是复述热度，而是判断它正处在哪个阶段：早期概念验证、产品化扩散、商业化拐点、政策定调，还是竞争格局重排。

本报告建议将该主题拆成四条时间线同步研究：

| 时间线 | 需要寻找的证据 | 为什么重要 |
|---|---|---|
| 技术线 | 论文、benchmark、开源 release、API 文档、issue/PR、专利 | 判断进展是否来自真实技术突破，还是仅是包装概念。 |
| 产品线 | 发布会、官网文档、版本更新、客户案例、价格页 | 判断技术是否已经进入可使用产品。 |
| 商业线 | 融资、并购、订单、收入、客户扩张、渠道合作 | 判断热度是否能转化为投入和收入。 |
| 政策线 | 法规、监管问询、行业标准、补贴、采购、合规要求 | 判断外部约束是否会改变市场速度和参与门槛。 |

### 2. 当前阶段判断

基于当前候选证据，「{candidate.title}」至少已经越过“无来源概念”阶段。它拥有明确来源 URL 和可读的数据依据：

{signals}

二次取证后的来源画像如下：

{source_profiles}

这意味着研究者可以继续沿着来源追溯原始信息，而不是依赖二手转述。若来源以 GitHub 为主，则重点验证开发者采用、更新频率、issue 质量和生态依赖；若来源以论文为主，则重点验证方法、数据集、实验可复现性和同行引用；若来源以媒体为主，则重点验证报道是否来自原始采访或官方披露；若来源以社区为主，则只能作为早期发现线索，不能直接作为事实结论。

### 3. 最近 30 天触发因素

最近 30 天窗口的价值，在于它能区分长期趋势与短期噪音。长期趋势通常已经存在多年，而真正值得研究的是最近发生了什么，让旧问题出现新拐点。对本主题而言，当前候选证据指向以下可能触发因素：

| 触发类型 | 如何从当前证据识别 | 后续验证方法 |
|---|---|---|
| 开发者活动上升 | GitHub stars/forks/issues/updated_at/pushed_at 等字段 | 拉取 GitHub API，比较近 30 天 stars、commits、release、issue close rate。 |
| 学术或技术突破 | arXiv、论文、benchmark、technical report | 读取论文摘要、实验设置、代码仓库，检查是否有独立复现。 |
| 社区讨论升温 | HN/Reddit/X/论坛 comments、points、upvotes | 统计帖子数量、评论质量、是否有一线实践者参与。 |
| 产品或平台发布 | 官方 blog、docs、release note、pricing | 优先引用官方页面，再用媒体报道补充解读。 |
| 政策或监管变化 | 政府、监管机构、标准组织文件 | 只用官方文本确认，不用媒体标题替代政策原文。 |

### 4. 纵向结论

当前更稳妥的判断是：该主题已经具备被持续跟踪的条件，但尚不能仅凭候选证据给出“市场已经爆发”或“竞争格局已定”的强结论。下一步研究应补齐三类缺口：第一，历史起点和关键里程碑；第二，最近 30 天事件与历史趋势之间的因果关系；第三，未来 30-90 天可观察指标。

## 横向分析：竞争图谱

### 1. 参与者类型

一个热点是否有长期价值，取决于参与者是否足够多元。如果只有单一公司或单一社区在自我传播，风险较高；如果同时出现公司、开发者、研究机构、资本、监管与客户信号，说明它可能进入更真实的产业扩散阶段。

| 参与者类型 | 在本主题中的可能角色 | 需要验证的来源 |
|---|---|---|
| 龙头公司/平台方 | 定义产品形态、生态接口、价格策略和默认标准。 | 官网、开发者文档、财报、发布会、客户案例。 |
| 创业公司/新进入者 | 推动差异化、低成本方案或垂直场景落地。 | 融资公告、产品 demo、招聘、客户名单。 |
| 开源社区/开发者 | 通过代码、issue、插件和 benchmark 影响技术路线。 | GitHub API、release note、package registry、HN/Reddit。 |
| 学术机构/论文作者 | 提供新方法、评测基准、理论解释和可复现实验。 | arXiv、会议论文、代码仓库、引用关系。 |
| 监管/标准组织 | 决定准入门槛、责任边界、数据合规和安全要求。 | 政府网站、监管公告、标准草案、行业协会。 |
| 企业客户/采购方 | 验证真实需求、预算、部署阻力和 ROI。 | case study、招标、采购、访谈、岗位 JD。 |

### 2. 竞争维度

| 维度 | 研究问题 | 对结论的影响 |
|---|---|
| 技术路线 | 不同参与者用什么路线解决同一问题？路线差异是否影响成本、性能、安全或可扩展性？ | 决定短期产品体验和长期壁垒。 |
| 产品形态 | 是工具、平台、API、硬件、服务，还是完整解决方案？ | 决定销售路径和客户预算归属。 |
| 生态位置 | 依赖哪些上游供应商？控制哪些下游渠道？ | 决定议价能力和抗风险能力。 |
| 数据与网络效应 | 是否拥有专有数据、用户反馈、开发者生态或客户流程沉淀？ | 决定竞争优势是否会随规模增强。 |
| 商业模式 | 免费开源、订阅、按量计费、硬件利润、交易抽成还是服务费？ | 决定增长质量与盈利路径。 |
| 合规门槛 | 是否涉及隐私、安全、金融、医疗、交通、能源等高监管场景？ | 决定落地速度和企业采购周期。 |

### 3. 当前竞争格局的保守判断

从候选证据看，本主题还处于“需要进一步拆分参与者”的阶段。当前证据能说明它值得研究，但不足以直接给出完整市场份额或胜负排序。因此，本报告采用“竞争假设”而不是“竞争结论”：

1. 如果核心来源来自 GitHub，则开源生态和开发者采用是当前最强信号，但要警惕 stars 与真实生产部署之间的差距。
2. 如果核心来源来自论文，则技术新颖性是当前最强信号，但要警惕 benchmark 与真实环境之间的落差。
3. 如果核心来源来自媒体，则社会关注和行业叙事是当前最强信号，但要警惕报道密度与商业结果之间的落差。
4. 如果核心来源来自政策，则外部约束可能成为关键变量，但要区分征求意见、正式法规、执法案例和财政补贴。

## 横纵交汇洞察

纵向分析回答“这个主题如何走到今天”，横向分析回答“今天谁在竞争、用什么方式竞争”。两者交汇后，才有判断价值。

### 洞察一：近期热度只有落到历史路径中才有意义

如果一个主题在过去长期沉寂，最近 30 天突然出现高密度信号，可能意味着技术、政策、成本或需求出现拐点；如果它过去已经长期很热，最近只是延续讨论，则需要判断是否出现了新的实质变量。对「{candidate.title}」而言，当前候选证据显示它至少有近期可追踪活动，但仍需补充历史阶段证据，才能判断这是“趋势加速”还是“周期性曝光”。

### 洞察二：多源证据比单一高分更重要

热点评分 {candidate.score:.0f} 只是排序工具。真正提高可信度的是来源类型的多样性：{source_types}。如果未来能继续补充官方公告、财务数据、政策文本和第三方研究，本主题的结论强度会明显提高。相反，如果后续只能找到同一消息的重复转载，就要下调判断。

### 洞察三：最值得追踪的是“热度向行动的转化”

热点研究最常见的错误，是把讨论量当成结果。更稳健的做法是追踪行动指标：公司是否发布产品、客户是否采购、开发者是否持续维护、监管是否正式落地、资本是否继续投入、用户是否愿意付费。只有当热度转化为行动，主题才从舆论热点变成产业变量。

## 专题深挖一：如何判断这个热点不是纯概念炒作

纯概念炒作通常有三个特征：来源单一、缺少数字、无法追溯到原始材料。当前候选至少包含以下可复核字段：

{signals}

这些字段让研究者可以继续验证，而不是停留在标题。为了进一步排除炒作，建议使用“四重证据门槛”：

| 门槛 | 合格标准 | 不合格表现 |
|---|---|---|
| 来源门槛 | 至少一个原始来源，例如官方公告、GitHub API、论文页、监管文件、财报。 | 只有转载文章或社交截图。 |
| 数字门槛 | 至少一个可复核数字，例如 stars、forks、融资额、订单量、市场规模、样本数、benchmark 分数。 | 只有“快速增长”“爆火”等形容词。 |
| 时间门槛 | 能说清事件发生或来源访问日期。 | 不知道是今天、去年还是旧闻翻炒。 |
| 反证门槛 | 主动列出未确认事项和可能冲突口径。 | 只写单边乐观叙事。 |

本报告目前满足前两项基础门槛：有来源 URL、有候选数据依据；但更完整的结论仍需要补充官方与第三方强来源。

## 专题深挖二：从研究报告到决策材料还缺什么

如果这份报告要进一步服务投资、战略、产品或技术选型，需要补齐以下模块：

| 决策场景 | 必须补充的信息 | 推荐工具或来源 |
|---|---|---|
| 投资研究 | 市场规模、增速、竞争份额、融资历史、估值、收入质量、退出路径。 | 公司公告、财报、投融资数据库、券商研报、行业协会。 |
| 产品战略 | 用户痛点、替代方案、价格敏感度、渠道、使用频率、留存和 NPS。 | 用户访谈、竞品体验、价格页、应用商店评论、社区帖子。 |
| 技术选型 | 架构、性能、可靠性、安全、维护成本、生态依赖、迁移成本。 | 官方文档、GitHub issue、benchmark、POC、内部压测。 |
| 政策研判 | 监管主体、法规层级、执行时间、处罚案例、合规成本。 | 政府官网、监管公告、标准文本、法律数据库。 |
| 市场进入 | 客户画像、采购流程、销售周期、合作伙伴、地方政策。 | 招投标、客户案例、招聘 JD、渠道访谈。 |

这也是 CLI 生成报告的边界：它可以根据公开信号快速形成一份结构化研究底稿，但如果要变成可投资或可上会材料，还必须进行定向二次验证。

## 专题深挖三：未来 30-90 天观察指标

| 指标 | 为什么重要 | 如何观察 |
|---|---|---|
| 原始来源更新频率 | 判断热度是否持续。 | 持续抓取 GitHub updated_at、release、论文 follow-up、官方 blog。 |
| 参与者数量变化 | 判断是否从单点事件扩散为赛道。 | 统计新进入公司、开源项目、论文、政策文件和客户案例。 |
| 质量型讨论占比 | 判断讨论是否从围观转向实践。 | 查看 HN/Reddit/GitHub issue 中是否有部署、bug、成本、性能讨论。 |
| 付费或采购信号 | 判断商业化是否开始。 | 价格页、订单、招投标、客户公告、财报口径。 |
| 监管或安全事件 | 判断外部约束是否增强。 | CVE、监管问询、行业标准、事故复盘。 |
| 反向信号 | 判断热度是否降温或被证伪。 | 仓库停更、客户流失、负面评测、政策收紧、融资失败。 |

## 给决策者的行动建议

1. **先做证据分层**：把来源分成官方/论文/API/媒体/社区五类，不同来源承担不同证明力。社区热度可以发现问题，但不能单独支撑结论。
2. **建立候选池而不是押单点**：把「{candidate.title}」放入同领域 5-10 个候选主题中横向比较，避免被单个高分热点牵引。
3. **把未确认事项写进报告**：没有确认的市场规模、收入、客户数量、政策状态，不要用推测补齐。宁可留下空白，也不要制造确定性。
4. **用未来指标验证当下判断**：给每个结论配一个未来 30-90 天可观察指标。若指标没有发生，及时下调判断。
5. **将报告转为任务清单**：对技术、市场、政策、财务分别列出下一步数据抓取任务，形成可迭代研究流程。

## 自动化生成质量控制

为了避免 CLI 输出退化成摘要式报告，后续每次生成都应检查以下门槛：

| 质量门槛 | 当前报告处理方式 |
|---|---|
| 结构完整 | 保留执行摘要、一句话定义、纵向分析、横向分析、横纵交汇洞察、专题深挖、行动建议、信息来源和未确认附录。 |
| 数据可追溯 | 所有候选事实只来自 `HotspotCandidate.evidence` 和 `source_urls`，不额外编造数字。 |
| 结论分级 | 区分已确认、推断、待验证，避免把热度写成确定事实。 |
| 可二次编辑 | Markdown 保留表格和清晰小节，可继续交给 Kami 或人工补充。 |
| 可扩展 | 后续可接入 finance、browser、camofox、news API，将当前“深度底稿”升级为真正多源实证报告。 |

## 信息来源

{source_table}

## 附录：未确认与后续验证

| 事项 | 当前状态 | 为什么未确认 | 后续验证路径 |
|---|---|---|---|
| 完整市场规模 / TAM / CAGR | 暂未确认 | 当前候选证据未提供口径清楚的市场规模数据。 | 检索行业协会、券商研报、Gartner/IDC/Forrester、公司财报。 |
| 具体融资、收入或订单 | 暂未确认 | 当前 evidence 未包含融资额、收入或订单金额。 | 查询公司公告、融资新闻、工商数据、招投标、财报。 |
| 政策或监管正式状态 | 暂未确认 | 当前来源不一定包含官方政策文本。 | 检索监管机构、政府官网、标准组织原文。 |
| 竞争份额排名 | 暂未确认 | 当前热点评分不能代表市场份额。 | 使用出货量、收入、用户数、客户数、生态活跃度等多指标交叉验证。 |
| 长期可持续性 | 暂未确认 | 最近 30 天热度不等于长期趋势。 | 连续跟踪 30-90 天更新频率、客户采用、社区质量和负面信号。 |

## 附录：原始选题数据

| 字段 | 内容 |
|---|---|
| 标题 | {candidate.title} |
| 领域 | {candidate.domain} |
| 热点评分 | {candidate.score:.0f} |
| 来源类型 | {source_types} |
| 数据依据 | {candidate.evidence} |
"""


def _render_deep_markdown_en(candidate: HotspotCandidate, summary: str, start: str, today: str, sources: list[SourceEvidence], skill_dir: Path) -> str:
    source_types = ", ".join(candidate.sources) if candidate.sources else "public sources"
    return f"""# {candidate.title}: Last-30-Days Hotspot Research Report

> Research window: {start} to {today}  
> Mode: Domain-Specific / Hotspot-Guided  
> Domain: {candidate.domain}  
> Access date: {today}  
> Source classes: {source_types}  
> Framework: bundled hotspot-research skill installed at {skill_dir}  

## Executive Summary

{summary}

This is a deep research draft rather than a short summary. It separates confirmed evidence from assumptions, uses the available public-source signals as the starting point, and turns the selected topic into a structured research agenda: one-sentence definition, longitudinal analysis, cross-sectional competitive map, integrated insights, deep-dive sections, action recommendations, source table, and an explicit unverified-items appendix.

## Skill And Source Basis

This report is generated through the bundled `hotspot-research` skill that ships with the Python package. It does not require the user to have Codex, Hermes, or another agent framework installed. The CLI installs the skill resources locally, reads the research framework, enriches the selected URLs, and separates confirmed facts from follow-up verification tasks.

{_skill_basis(skill_dir)}

## Source Profiles

{_source_profiles(sources)}

## One-Sentence Definition

`{candidate.title}` is a recent high-signal topic in `{candidate.domain}` selected from public evidence, not from unsupported hype. The current evidence base is: {_short_sentence(candidate.evidence)}

## Selection Rationale

| Dimension | Current Reading |
|---|---|
| Public evidence | {candidate.evidence} |
| Source classes | {source_types} |
| Hotspot score | {candidate.score:.0f} |
| Evidence quality | {_evidence_quality(candidate)} |

## Longitudinal Analysis

The key research question is how this topic moved from an earlier background trend into a recent observable hotspot. Analyze four timelines: technical milestones, product releases, commercialization signals, and policy or governance constraints. The available evidence does not justify inventing market-size or revenue numbers, so this report treats those as follow-up verification tasks.

## Cross-Sectional Competitive Map

Compare platform owners, startups, open-source communities, academic actors, regulators, and enterprise customers. For each actor, collect positioning, technology route, product form, data advantage, business model, ecosystem dependencies, and risk exposure.

## Integrated Insights

The most important distinction is between attention and action. Public attention is useful for discovery; durable action is visible through product launches, sustained repository activity, papers, customer adoption, procurement, regulation, funding, and paid usage. This topic deserves monitoring because it has traceable public evidence, but the strength of any strategic conclusion depends on the next round of source verification.

## Deep Dive 1: Evidence Quality

{_signal_table(candidate)}

Use a four-part evidence gate: original source, numeric support, date clarity, and explicit counter-evidence. A topic passes the first screen when it has URLs and objective fields; it becomes decision-grade only when primary sources and independent verification agree.

## Deep Dive 2: Decision Use Cases

| Use Case | Required Additional Evidence |
|---|---|
| Investment research | Market size, CAGR, financing, revenue quality, comparable companies |
| Product strategy | User pain, alternatives, pricing, retention, distribution |
| Technical selection | Architecture, benchmark, reliability, security, maintenance cost |
| Policy analysis | Regulator, legal text, enforcement timeline, compliance cost |

## Next 30-90 Days Watchlist

| Indicator | Why It Matters |
|---|---|
| Primary-source updates | Tests whether the topic keeps moving after the initial spike |
| More independent participants | Shows whether the topic is becoming a sector, not a single event |
| Practitioner discussions | Separates real usage from surface-level attention |
| Paid adoption or procurement | Converts heat into business signal |
| Regulation or security incidents | Can accelerate or slow adoption |

## Sources

{_source_table(candidate, sources)}

## Appendix: Unverified Items

| Item | Status | Verification Path |
|---|---|---|
| Market size / TAM / CAGR | Unverified | Industry reports, filings, analyst research |
| Revenue, funding, orders | Unverified | Company announcements, filings, reputable media |
| Regulatory status | Unverified | Government and regulator primary sources |
| Market share ranking | Unverified | Revenue, shipment, customer, and usage data |
"""


def _source_lines(candidate: HotspotCandidate) -> str:
    if not candidate.source_urls:
        return "- 暂无可用 URL，需补充复核。\n"
    return "\n".join(f"- {url}" for url in candidate.source_urls) + "\n"


def _source_table(candidate: HotspotCandidate, enriched_sources: Optional[list[SourceEvidence]] = None) -> str:
    if enriched_sources:
        rows = ["| 编号 | 标题 | 发布方 | 日期 | URL | 已提取事实 |", "|---|---|---|---|---|---|"]
        for index, item in enumerate(enriched_sources, 1):
            rows.append(
                "| S{} | {} | {} | {} | {} | {} |".format(
                    index,
                    _escape_table(item.title),
                    _escape_table(item.publisher),
                    _escape_table(item.published),
                    item.url,
                    _escape_table("; ".join(item.facts[:8])),
                )
            )
        return "\n".join(rows)
    if not candidate.source_urls:
        return "| 编号 | URL | 来源类型 | 支撑事实 |\n|---|---|---|---|\n| S1 | 暂无 URL | 待补充 | 需要补充原始来源后再下结论 |\n"
    rows = ["| 编号 | URL | 来源类型 | 支撑事实 |", "|---|---|---|---|"]
    sources = candidate.sources or ["public"]
    for index, url in enumerate(candidate.source_urls, 1):
        source_type = sources[min(index - 1, len(sources) - 1)]
        rows.append(f"| S{index} | {url} | {source_type} | 支撑选题存在公开来源；具体事实需沿原始页面继续复核。 |")
    return "\n".join(rows)


def _source_profiles(sources: list[SourceEvidence]) -> str:
    if not sources:
        return "暂无可解析来源画像；报告仅能基于候选 evidence 形成研究框架，需补充原始来源。"
    blocks = []
    for index, item in enumerate(sources, 1):
        facts = "\n".join(f"- {fact}" for fact in item.facts[:10])
        excerpt = f"\n\n摘录/摘要：{item.excerpt}" if item.excerpt else ""
        blocks.append(
            f"### S{index}. {item.title}\n\n"
            f"- 来源类型：{item.kind}\n"
            f"- 发布方：{item.publisher}\n"
            f"- 日期：{item.published}\n"
            f"- URL：{item.url}\n"
            f"- 已提取事实：\n{facts}{excerpt}"
        )
    return "\n\n".join(blocks)


def _skill_basis(skill_dir: Path) -> str:
    template = skill_dir / "assets" / "report-template.md"
    framework = skill_dir / "references" / "market-research-frameworks.md"
    parts = []
    if template.exists():
        parts.append("- 已加载报告模板：`assets/report-template.md`，用于保持“一句话定义、纵向分析、横向分析、横纵交汇洞察、信息来源”的结构。")
    if framework.exists():
        parts.append("- 已加载研究框架：`references/market-research-frameworks.md`，用于约束 TAM/SAM/SOM、PESTLE、Porter、SWOT、情景分析等框架的使用边界。")
    if not parts:
        parts.append("- 未找到本地 skill 模板文件，已使用包内默认结构生成。")
    return "\n".join(parts)


def _signal_table(candidate: HotspotCandidate) -> str:
    parts = _split_evidence(candidate.evidence)
    if not parts:
        parts = [candidate.evidence or "暂无结构化 evidence"]
    rows = ["| 信号 | 当前记录 | 研究含义 |", "|---|---|---|"]
    for part in parts[:12]:
        rows.append(f"| {_signal_name(part)} | {part} | {_signal_meaning(part)} |")
    return "\n".join(rows)


def _split_evidence(evidence: str) -> list[str]:
    return [item.strip() for item in re.split(r";\s*", evidence or "") if item.strip()]


def _signal_name(part: str) -> str:
    lower = part.lower()
    if "github" in lower or "stars" in lower or "forks" in lower:
        return "开发者/开源信号"
    if "arxiv" in lower or "paper" in lower or "submitted" in lower:
        return "学术/技术信号"
    if "hn" in lower or "hacker news" in lower or "comments" in lower or "reddit" in lower:
        return "社区讨论信号"
    if "policy" in lower or "regulation" in lower or "监管" in lower or "政策" in lower:
        return "政策/监管信号"
    if "funding" in lower or "融资" in lower or "investment" in lower:
        return "资本信号"
    if "market" in lower or "cagr" in lower or "市场" in lower:
        return "市场信号"
    return "候选证据信号"


def _signal_meaning(part: str) -> str:
    lower = part.lower()
    if "stars" in lower or "forks" in lower:
        return "说明开发者关注或复用度可被量化，但不能直接等同收入或生产部署。"
    if "issues" in lower:
        return "说明项目存在活跃讨论或待解决问题，需要结合 issue 质量和关闭速度判断维护能力。"
    if "updated" in lower or "pushed" in lower:
        return "说明近期仍有维护活动，可作为最近 30 天热度的时间证据。"
    if "arxiv" in lower or "submitted" in lower:
        return "说明存在论文或技术报告线索，需要进一步阅读方法、实验和可复现性。"
    if "comments" in lower or "hn" in lower or "reddit" in lower:
        return "说明社区有讨论热度，适合作为发现线索，但必须用更强来源复核事实。"
    return "这是候选阶段证据，需要回到原始 URL 做交叉验证。"


def _dimension_score(candidate: HotspotCandidate, dimension: str) -> str:
    text = f"{candidate.evidence} {' '.join(candidate.sources)}".lower()
    score = 2
    if dimension == "media" and any(word in text for word in ("news", "media", "hn", "reddit", "comments")):
        score += 1
    if dimension == "tech" and any(word in text for word in ("github", "arxiv", "paper", "release", "benchmark", "stars", "forks")):
        score += 2
    if dimension == "social" and candidate.score >= 50:
        score += 2
    if dimension == "policy" and any(word in text for word in ("policy", "regulation", "监管", "政策", "standard")):
        score += 2
    if dimension == "capital" and any(word in text for word in ("funding", "investment", "融资", "并购", "valuation")):
        score += 2
    if dimension == "market" and any(word in text for word in ("market", "cagr", "tam", "sam", "som", "市场")):
        score += 2
    if dimension == "evidence":
        score = 2 + min(3, len(candidate.source_urls))
    return f"{min(score, 5)}/5"


def _evidence_quality(candidate: HotspotCandidate) -> str:
    if len(candidate.source_urls) >= 3 and len(set(candidate.sources)) >= 2:
        return "当前证据质量为中高：至少包含多个 URL 和多类公共来源，但仍需要原始页面逐条复核。"
    if candidate.source_urls:
        return "当前证据质量为中等：已有可追溯 URL，但来源类型仍需扩展。"
    return "当前证据质量偏弱：缺少可追溯 URL，只能作为候选线索。"


def _short_sentence(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return "当前候选未提供足够 evidence，需要补充来源。"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _publisher(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host.replace("www.", "") or "public web"


def _url_label(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return (parsed.netloc + parsed.path).strip("/") or url


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()


def _escape_table(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).replace("|", "\\|").strip()


def _summary(candidate: HotspotCandidate) -> str:
    return f"选题「{candidate.title}」来自「{candidate.domain}」赛道，筛选依据为：{candidate.evidence}。"


def _slugify(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or "hotspot-report"
