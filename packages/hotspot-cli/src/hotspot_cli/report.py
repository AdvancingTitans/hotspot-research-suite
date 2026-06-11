from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .hotspots import HotspotCandidate


DEFAULT_SKILL_DIR = Path("/Users/yjw/agent/hotspot-research")


@dataclass(frozen=True)
class ReportResult:
    topic: str
    markdown_path: Path
    html_path: Path
    pdf_path: Optional[Path]
    summary: str


class ReportError(RuntimeError):
    pass


class ReportGenerator:
    def __init__(self, output_dir: Optional[Path] = None, skill_dir: Path = DEFAULT_SKILL_DIR) -> None:
        self.output_dir = (output_dir or Path.cwd() / "reports").resolve()
        self.skill_dir = skill_dir

    def generate(self, candidate: HotspotCandidate, *, language: str = "zh") -> ReportResult:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise ReportError(f"无法创建报告目录：{self.output_dir}。请检查写入权限。") from exc

        slug = _slugify(candidate.title)
        md_path = (self.output_dir / f"{slug}.md").resolve()
        html_path = (self.output_dir / f"{slug}.html").resolve()
        pdf_path = (self.output_dir / f"{slug}.pdf").resolve()
        summary = _summary(candidate)
        md_path.write_text(_render_markdown(candidate, summary, language), encoding="utf-8")
        self._render_html(md_path, html_path)
        pdf_result = self._render_pdf(html_path, pdf_path)
        return ReportResult(candidate.title, md_path, html_path, pdf_result, summary)

    def _render_html(self, md_path: Path, html_path: Path) -> None:
        script = self.skill_dir / "scripts" / "simple_report_html.py"
        if script.exists():
            proc = subprocess.run(["python3", str(script), str(md_path), str(html_path)], capture_output=True, text=True)
            if proc.returncode == 0:
                return
        proc = subprocess.run([sys.executable, "-m", "hotspot_cli.simple_report_html", str(md_path), str(html_path)], capture_output=True, text=True)
        if proc.returncode == 0:
            return
        html_path.write_text("<pre>" + md_path.read_text(encoding="utf-8") + "</pre>", encoding="utf-8")

    def _render_pdf(self, html_path: Path, pdf_path: Path) -> Optional[Path]:
        script = self.skill_dir / "scripts" / "render_pdf_weasy.py"
        if script.exists():
            argv = ["python3", str(script), str(html_path), str(pdf_path)]
        else:
            argv = [sys.executable, "-m", "hotspot_cli.render_pdf_weasy", str(html_path), str(pdf_path)]
        proc = subprocess.run(argv, capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        return pdf_path if pdf_path.exists() else None


def _render_markdown(candidate: HotspotCandidate, summary: str, language: str) -> str:
    today = dt.date.today().isoformat()
    start = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    if language == "en":
        return f"""# {candidate.title} Research Report

> Research window: {start} to {today}
> Mode: Domain-Specific / Hotspot-Guided
> Domain: {candidate.domain}

## Executive Summary

{summary}

## One-Sentence Definition

{candidate.title} is a source-backed hotspot selected from public discussions and objective industry signals in the last 30 days.

## Longitudinal Analysis

This report should be expanded with the full hotspot-research workflow: origin, milestones, recent trigger, phase changes, and evidence-backed inflection points.

## Cross-Sectional Competitive Map

Compare leading players, substitutes, technical routes, business models, policy constraints, and user/community signals.

## Integrated Insights

The current hotspot should be judged by whether recent momentum is supported by durable data: policy movement, market size, funding, technical releases, papers, or adoption signals.

## Sources

{_source_lines(candidate)}
"""
    return f"""# {candidate.title}研究报告

> 研究窗口：{start} 至 {today}  
> 研究模式：Domain-Specific / Hotspot-Guided  
> 领域：{candidate.domain}  
> 生成方式：last30days-safe 选题 + hotspot-research 报告结构

## 执行摘要

{summary}

## 一句话定义

{candidate.title} 是一个基于最近 30 天公共讨论与客观行业信号筛选出的研究选题，具备进一步做政策、市场、技术、学术或产业链深度研究的价值。

## 纵向分析：从诞生到当下

本节应沿时间线补全：概念起源、关键政策/技术/产品节点、融资与产业化阶段、最近 30 天成为热点的直接触发因素。

当前可确认的选题依据：{candidate.evidence}

## 横向分析：竞争图谱

围绕该选题，应横向比较：

- 主要公司、机构、开源项目或政策主体
- 技术路线与产品形态
- 市场规模、增长率、融资、订单或出货量等客观指标
- 竞品/替代方案的优势与短板
- 用户、开发者或学术社区的公开反馈

## 横纵交汇洞察

初步判断：该选题值得研究的关键，不在于短期讨论热度，而在于它已经出现可追踪的数据支撑。后续应重点验证三类问题：

1. 最近 30 天触发因素是否会改变长期产业路径；
2. 当前参与者的竞争位置是否由早期技术/商业选择塑造；
3. 市场热度能否转化为真实投入、产品采用或监管变化。

## 信息来源

{_source_lines(candidate)}

## 附录：选题数据依据

| 字段 | 内容 |
|---|---|
| 热点评分 | {candidate.score:.0f} |
| 来源类型 | {", ".join(candidate.sources)} |
| 数据依据 | {candidate.evidence} |
"""


def _source_lines(candidate: HotspotCandidate) -> str:
    if not candidate.source_urls:
        return "- 暂无可用 URL，需补充复核。\n"
    return "\n".join(f"- {url}" for url in candidate.source_urls) + "\n"


def _summary(candidate: HotspotCandidate) -> str:
    return f"选题「{candidate.title}」来自「{candidate.domain}」赛道，筛选依据为：{candidate.evidence}。"


def _slugify(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or "hotspot-report"
