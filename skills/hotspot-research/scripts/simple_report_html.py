#!/usr/bin/env python3
"""Convert the hotspot report Markdown subset to a styled HTML file."""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path


STYLE = """
body {
  max-width: 920px;
  margin: 48px auto;
  padding: 0 28px;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
    "Noto Sans CJK SC", "Microsoft YaHei", Arial, sans-serif;
  color: #1f2933;
  line-height: 1.75;
  background: #fbfaf7;
}
h1, h2, h3 {
  color: #153e75;
  line-height: 1.25;
}
h1 {
  font-size: 30px;
  margin-bottom: 18px;
  padding-bottom: 18px;
  border-bottom: 3px solid #1f7a8c;
}
h2 {
  font-size: 22px;
  margin-top: 42px;
  border-bottom: 1px solid #d9e2ec;
  padding-bottom: 8px;
}
h3 {
  font-size: 18px;
  margin-top: 28px;
}
p {
  margin: 12px 0;
}
blockquote {
  margin: 18px 0;
  padding: 10px 16px;
  background: #eef6f7;
  border-left: 4px solid #1f7a8c;
  color: #334e68;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 18px 0 28px;
  font-size: 13px;
  background: #fff;
}
th {
  background: #153e75;
  color: #fff;
  font-weight: 650;
}
th, td {
  border: 1px solid #d9e2ec;
  padding: 8px 10px;
  vertical-align: top;
}
tr:nth-child(even) td {
  background: #f7fafc;
}
a {
  color: #0f609b;
}
code {
  background: #edf2f7;
  padding: 1px 4px;
  border-radius: 4px;
}
@media print {
  body {
    max-width: none;
    margin: 18mm;
    background: #fff;
  }
  h2 {
    page-break-after: avoid;
  }
  table {
    page-break-inside: avoid;
  }
}
"""


def inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    escaped = re.sub(
        r"(https?://[^\s<]+)",
        lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
        escaped,
    )
    return escaped


def render_table(rows: list[str]) -> str:
    parsed = []
    for row in rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        parsed.append(cells)
    if len(parsed) >= 2 and all(set(cell) <= {"-", ":", " "} for cell in parsed[1]):
        body_rows = parsed[2:]
    else:
        body_rows = parsed[1:]
    out = ["<table>", "<thead><tr>"]
    for cell in parsed[0]:
        out.append(f"<th>{inline(cell)}</th>")
    out.append("</tr></thead><tbody>")
    for row in body_rows:
        out.append("<tr>")
        for cell in row:
            out.append(f"<td>{inline(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    table: list[str] = []
    quote: list[str] = []

    def flush_table() -> None:
        nonlocal table
        if table:
            out.append(render_table(table))
            table = []

    def flush_quote() -> None:
        nonlocal quote
        if quote:
            out.append("<blockquote>" + "<br>".join(inline(q) for q in quote) + "</blockquote>")
            quote = []

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("|") and line.endswith("|"):
            flush_quote()
            table.append(line)
            continue
        flush_table()
        if line.startswith(">"):
            quote.append(line.lstrip(">").strip())
            continue
        flush_quote()
        if not line:
            continue
        if line.startswith("# "):
            out.append(f"<h1>{inline(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            out.append(f"<h3>{inline(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            out.append(f"<p>• {inline(line[2:].strip())}</p>")
        else:
            out.append(f"<p>{inline(line)}</p>")

    flush_table()
    flush_quote()
    return "<!doctype html><html><head><meta charset='utf-8'><title>Hotspot Research Report</title><style>" + STYLE + "</style></head><body>" + "\n".join(out) + "</body></html>"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: simple_report_html.py input.md output.html", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    dst.write_text(convert(src.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
