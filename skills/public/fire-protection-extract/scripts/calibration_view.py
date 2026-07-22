#!/usr/bin/env python3
"""Generate an interactive HTML calibration view from a fire report.

Shows each fire-spec section with: status (✅/⚠️), extracted content preview,
source traceability, and [⚠未找到] markers highlighted.

Usage:
  python calibration_view.py <report.md> <structure.json> [mapping.json] > calibration.html
  If mapping.json is provided, also shows anchor status per section.
"""
import json
import re
import sys
from pathlib import Path

MISSING_RE = re.compile(r"\[⚠未找到(?:锚|区间|表):\s*(.+?)(?:…|\])")
SOURCE_RE = re.compile(r"^> 源:\s*(.+)$", re.MULTILINE)


def _escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_html(report_md, structure=None, mapping=None):
    """Parse report.md and build an interactive HTML calibration view."""
    sections = []
    current_section = None
    current_content = []
    in_code_fence = False

    for line in report_md.splitlines():
        # Track code fences (table blocks)
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence

        # Heading detection
        if line.startswith("#") and not in_code_fence:
            if current_section:
                current_section["content"] = "\n".join(current_content)
                sections.append(current_section)
            level = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()
            current_section = {"level": level, "title": title, "content": "", "status": "ok"}
            current_content = []
        elif current_section is not None:
            current_content.append(line)
            if MISSING_RE.search(line):
                current_section["status"] = "missing"

    if current_section:
        current_section["content"] = "\n".join(current_content)
        sections.append(current_section)

    # Build mapping index if provided
    anchor_status = {}
    if mapping:
        for sec in mapping.get("sections", []):
            name = sec["fire"]
            sources = sec.get("sources", [])
            if sources and sec.get("class") == "verbatim":
                anchor_status[name] = {"total": len(sources)}
            elif sec.get("class") == "template":
                anchor_status[name] = {"template": True}
            elif sec.get("class") == "compute":
                anchor_status[name] = {"compute": True}

    # Build HTML
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>消防设计专篇 — 校准视图</title>
<style>
  body { font-family: -apple-system, 'Microsoft YaHei', sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #212529; }
  h1 { border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
  .section { background: #fff; border: 1px solid #e9ecef; border-radius: 6px; margin: 8px 0; padding: 12px 16px; }
  .section.missing { border-left: 4px solid #dc3545; background: #fff5f5; }
  .section.ok { border-left: 4px solid #28a745; }
  .section.heading-only { border-left: 4px solid #6c757d; background: #f8f9fa; }
  .section h2, .section h3 { margin: 0 0 8px 0; font-size: 1rem; }
  .section .badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: .75rem; font-weight: 600; }
  .badge-ok { background: #d4edda; color: #155724; }
  .badge-missing { background: #f8d7da; color: #721c24; }
  .badge-template { background: #cce5ff; color: #004085; }
  .badge-compute { background: #fff3cd; color: #856404; }
  .section .preview { font-size: .85rem; color: #6c757d; margin: 4px 0; max-height: 60px; overflow: hidden; }
  .section .source { font-size: .8rem; color: #0d6efd; margin-top: 4px; }
  .missing-marker { background: #fff3cd; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: .8rem; }
  .summary { display: flex; gap: 16px; margin: 16px 0; }
  .summary-box { padding: 10px 20px; border-radius: 6px; font-weight: 600; }
  .summary-ok { background: #d4edda; color: #155724; }
  .summary-missing { background: #f8d7da; color: #721c24; }
  .filter-bar { margin: 12px 0; }
  .filter-bar button { margin-right: 6px; padding: 4px 12px; border: 1px solid #dee2e6; border-radius: 4px; background: #fff; cursor: pointer; }
  .filter-bar button.active { background: #0d6efd; color: #fff; border-color: #0d6efd; }
</style>
</head>
<body>
<h1>消防设计专篇 — 校准视图</h1>
"""
    # Summary
    total = len(sections)
    missing_count = sum(1 for s in sections if s["status"] == "missing")
    ok_count = total - missing_count
    html += f"""<div class="summary">
  <div class="summary-box summary-ok">✅ {ok_count} 节正常</div>
  <div class="summary-box summary-missing">⚠️ {missing_count} 节需校准</div>
</div>
<div class="filter-bar">
  <button class="active" onclick="filter('all')">全部 ({total})</button>
  <button onclick="filter('missing')">⚠️ 需校准 ({missing_count})</button>
  <button onclick="filter('ok')">✅ 正常 ({ok_count})</button>
</div>
"""

    for s in sections:
        status_class = "ok" if s["status"] == "ok" else "missing"
        if s["level"] <= 2 and not s["content"].strip():
            status_class = "heading-only"

        badge = {"ok": '<span class="badge badge-ok">✓</span>',
                 "missing": '<span class="badge badge-missing">⚠ 需校准</span>',
                 "heading-only": ""}.get(status_class, "")

        # Truncated preview
        preview = s["content"].strip()[:200]
        if len(s["content"].strip()) > 200:
            preview += "…"

        # Source line
        source_match = SOURCE_RE.search(s["content"])
        source = source_match.group(0) if source_match else ""

        # Highlight missing markers
        preview_html = MISSING_RE.sub(r'<span class="missing-marker">[⚠未找到: \1…]</span>', _escape(preview))

        html += f"""<div class="section {status_class}" data-status="{status_class}">
  <strong>{_escape(s["title"])}</strong> {badge}
  <div class="preview">{preview_html or '<em>(空节)</em>'}</div>
  {f'<div class="source">{_escape(source)}</div>' if source else ''}
</div>
"""

    html += """
<script>
function filter(type) {
  document.querySelectorAll('.filter-bar button').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.section').forEach(s => {
    if (type === 'all') s.style.display = '';
    else s.style.display = s.dataset.status === type ? '' : 'none';
  });
}
</script>
</body>
</html>"""
    return html


def main(argv):
    if len(argv) < 2:
        print("usage: calibration_view.py <report.md> <structure.json> [mapping.json]", file=sys.stderr)
        return 2

    report = Path(argv[0]).read_text(encoding="utf-8")
    structure = json.loads(Path(argv[1]).read_text(encoding="utf-8")) if len(argv) > 1 else None
    mapping = json.loads(Path(argv[2]).read_text(encoding="utf-8")) if len(argv) > 2 else None

    html = build_html(report, structure, mapping)
    print(html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
