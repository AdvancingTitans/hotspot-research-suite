#!/usr/bin/env python3
"""Render a local HTML report to PDF with WeasyPrint.

On macOS with Homebrew-installed glib/pango/cairo, Python may fail to find
`libgobject-2.0-0` unless `/opt/homebrew/lib` is added before importing
WeasyPrint. Keep that setup here so report generation is reproducible.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_native_libraries() -> None:
    if sys.platform != "darwin":
        return

    candidates = [Path("/opt/homebrew/lib"), Path("/usr/local/lib")]
    existing = [p for p in os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(":") if p]

    for lib_dir in candidates:
        if (lib_dir / "libgobject-2.0.dylib").exists() or (lib_dir / "libgobject-2.0-0").exists():
            if str(lib_dir) not in existing:
                existing.insert(0, str(lib_dir))
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(existing)
            return


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: render_pdf_weasy.py input.html output.pdf", file=sys.stderr)
        return 2

    configure_native_libraries()

    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        print(
            "WeasyPrint is unavailable. On macOS, install native libraries with "
            "`brew install pango cairo glib` and run this script before importing "
            "WeasyPrint. If using system Python, prefer a Homebrew/venv Python.",
            file=sys.stderr,
        )
        print(f"Original error: {exc}", file=sys.stderr)
        return 1

    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    HTML(filename=str(src), base_url=str(src.parent)).write_pdf(str(dst))
    print(dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
