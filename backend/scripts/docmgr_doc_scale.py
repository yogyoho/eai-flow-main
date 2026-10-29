"""EAI-CUSTOM: docmgr 全文操作 T0 规模盘点（只读，一次性）。

扫个人文档 outputs/ 下 .md 文件：节数/节长分布，校准 ai_transform.py 的
SECTION_CHAR_LIMIT / MAX_SECTIONS / MAX_CONTENT_CHARS。stdlib only。
用法: python scripts/docmgr_doc_scale.py --root <.deer-flow/users 根>
"""

import argparse
import re
import statistics
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def split_sections_light(content: str) -> list[str]:
    """与 ai_transform.split_sections 同规则的轻量切分（脚本自包含，返回各节全文）。

    规则差异仅一处：不做超长再切/结构检测（盘点不需要）——节边界规则一致。
    """
    if not content.strip():
        return []
    raw: list[list[str]] = []
    buf: list[str] = []
    for line in content.split("\n"):
        if _HEADING_RE.match(line):
            if buf:
                raw.append(buf)
            buf = [line]
        else:
            buf.append(line)
    if buf:
        raw.append(buf)
    sections = ["\n".join(ls) for ls in raw]
    # 空白块并入前节（与 split_sections 的无损归并同规则）
    out: list[str] = []
    lead = ""
    for text in sections:
        if not text.strip():
            if out:
                out[-1] += text
            else:
                lead += text
            continue
        out.append(lead + text)
        lead = ""
    if lead and out:
        out[-1] += lead
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root)
    files = sorted(root.rglob("outputs/*.md"))
    all_sizes: list[int] = []
    doc_stats: list[tuple[str, int, int]] = []  # (path, chars, sections)
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        secs = split_sections_light(content)
        # T0 round-trip 对应性（spec §11-2 后端半边）：切分必须无损——
        # 各节依序拼接 == 原文；违例文档点名（说明分节规则有洞，修实现再放行）
        if "".join(secs) != content:
            print(f"LOSSLESS VIOLATION: {f}")
        sizes = [len(s) for s in secs]
        all_sizes.extend(sizes)
        doc_stats.append((str(f), len(content), len(secs)))

    def pct(values: list[int], p: float) -> int:
        if not values:
            return 0
        s = sorted(values)
        return s[min(len(s) - 1, int(len(s) * p))]

    print(f"docs={len(doc_stats)} total_sections={len(all_sizes)}")
    if all_sizes:
        print(
            f"section chars: max={max(all_sizes)} mean={int(statistics.mean(all_sizes))} "
            f"p50={pct(all_sizes, 0.5)} p90={pct(all_sizes, 0.9)} p99={pct(all_sizes, 0.99)}"
        )
        over = sum(1 for x in all_sizes if x > 4000)
        print(f"sections >4000 chars: {over} ({over * 100 // max(1, len(all_sizes))}%)")
    big = [d for d in doc_stats if d[1] > 400_000]
    print(f"docs >400k chars: {len(big)}")
    for path, chars, secs in sorted(doc_stats, key=lambda d: -d[1])[:10]:
        print(f"  top: {chars:>8} chars {secs:>4} sections  {path}")


if __name__ == "__main__":
    main()
