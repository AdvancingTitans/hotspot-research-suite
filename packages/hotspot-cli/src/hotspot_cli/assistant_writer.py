from __future__ import annotations

from pathlib import Path

from .assistant_models import TopicBrief


class BriefWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def save(self, brief: TopicBrief) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = brief.generated_at.strftime("%Y%m%d-%H%M%S")
        slug = _slugify(brief.topic)
        path = (self.output_dir / f"{stamp}-{slug}.md").resolve()
        path.write_text(brief.to_markdown(), encoding="utf-8")
        return path


def _slugify(value: str) -> str:
    import re

    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip().lower())
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:70] or "topic-brief"
