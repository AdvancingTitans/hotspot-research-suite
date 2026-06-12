from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path
from typing import Optional


SKILL_NAME = "hotspot-research"


def default_skill_dir() -> Path:
    return Path.home() / ".codex" / "skills" / SKILL_NAME


def bundled_skill_dir() -> Path:
    return resources.files("hotspot_cli").joinpath("embedded_skill", SKILL_NAME)  # type: ignore[return-value]


def ensure_hotspot_skill_installed(target_dir: Optional[Path] = None) -> Path:
    target = (target_dir or default_skill_dir()).expanduser()
    source = Path(str(bundled_skill_dir()))
    if not (source / "SKILL.md").exists():
        return target

    try:
        target.mkdir(parents=True, exist_ok=True)
        _copy_file(source / "SKILL.md", target / "SKILL.md")
        for dirname in ("assets", "references", "scripts"):
            src_dir = source / dirname
            if src_dir.exists():
                dst_dir = target / dirname
                dst_dir.mkdir(parents=True, exist_ok=True)
                for src in src_dir.rglob("*"):
                    if src.is_file() and "__pycache__" not in src.parts and src.suffix != ".pyc":
                        rel = src.relative_to(src_dir)
                        _copy_file(src, dst_dir / rel)
        return target
    except OSError:
        return source


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        return
    shutil.copy2(src, dst)
