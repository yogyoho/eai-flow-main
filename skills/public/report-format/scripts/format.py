#!/usr/bin/env python3
"""report-format: 格式化报告结构。

三步处理(不改文字内容,只改结构):
1. 去源编号: 段首 "11.4.1.1 xxx" → "xxx" (保留列表标记、数值、标准号)
2. 删空节: 只有标题没有实质内容的 section 删除
3. 生成目录: 基于标题,插在报告标题之后、第一章之前

注意: 不做子标题重编号——在纯文本中检测"哪些行是子标题"不可靠,
容易把正文短句当成标题重新编号,反而引入混乱。子标题重编号留给
未来版本(需要 structure.json 辅助判断哪些行是真正的标题)。

Usage:
  python format.py <input.md> <output.md>
"""
import re
import sys
from pathlib import Path

# ── 正则 ────────────────────────────────────────────────────────────

# 源文档编号: "11.4.1.1" (带点) 或 "1 概述" (数字+空格+中文)
# 排除: 列表标记(1）a）)、数值(198)、标准号(GB 50016)
_SRC_NUM_RE = re.compile(r"^\d+(?:\.\d+)+(?:\s*|(?=[一-鿿]))|^\d{1,2}\s+(?=[一-鹿])")

# fire-spec 标题: "## 4.3 供电安全" 或 "### 4.3.1 xxx"
_FIRE_HEADING_RE = re.compile(r"^(#{1,6})\s+(\d+(?:\.\d+)?)\s+(.+)$")

# 子标题: 短行(2-15字),无句末标点,纯CJK/字母数字
_SUBHEAD_RE = re.compile(r"^[一-鿿\w、，。；：·\-/]+$")


# ── Step 1: 去源编号 ────────────────────────────────────────────────

def strip_src_numbering(text):
    """去掉段首源文档编号,保留列表标记和数值。"""
    m = _SRC_NUM_RE.match(text)
    if not m:
        return text
    num = m.group().strip()
    # 无点且 >2 位 = 数值,不删 (如 198, 11000)
    if "." not in num and len(num) > 2:
        return text
    # 编号太长 = 可能误匹配,不删
    if len(m.group()) >= 15:
        return text
    return text[m.end():]


def step1_strip_numbers(lines):
    """遍历所有行,去掉正文段首的源编号(markdown 标题行不动)。"""
    out = []
    for line in lines:
        stripped = line.strip()
        # 不处理: markdown 标题、表格行、源标记、空行
        if (stripped.startswith("#")
                or stripped.startswith("|")
                or stripped.startswith("> 源:")
                or stripped.startswith("<!--")
                or not stripped):
            out.append(line)
            continue
        new_text = strip_src_numbering(stripped)
        indent = line[:len(line) - len(line.lstrip())]
        out.append(indent + new_text if new_text != stripped else line)
    return out


# ── Step 2: 章节重编号 ──────────────────────────────────────────────

def _is_subsection_heading(text):
    """检测短行是否像子标题(不是列表项、不是源标记)。"""
    t = text.strip()
    if len(t) > 15 or len(t) < 2:
        return False
    if t[0] in "abcdABCD" and len(t) > 1 and t[1] in "）)":
        return False
    if t[0] in "123456789" and len(t) > 1 and t[1] in "）)":
        return False
    if t.startswith(("> 源:", "[⚠", "表", "图", "|", "<!--")):
        return False
    if any(c in t for c in "。！？；，：、（）()"):
        return False
    return bool(_SUBHEAD_RE.match(t))


def step2_renumber(lines):
    """对每个 fire-spec section 下的子标题重新编号(带层级)。"""
    out = list(lines)
    current_base = ""
    counters = []
    prev_was_heading = False
    prev_was_body = False

    for i, line in enumerate(out):
        m = _FIRE_HEADING_RE.match(line) if line.startswith("#") else None
        if m and not line.startswith("# "):
            current_base = m.group(2)
            counters = [0]
            prev_was_heading = False
            prev_was_body = False
            continue

        if line.startswith("> 源:"):
            continue

        stripped = line.strip()

        if current_base and _is_subsection_heading(stripped):
            if prev_was_heading:
                # 连续标题 = 父子关系,加深一层
                counters.append(0)
            elif prev_was_body and len(counters) > 1:
                # 正文后新标题 = 回到上一层
                while len(counters) > 1:
                    counters.pop()
            counters[-1] += 1
            num = current_base + "".join(f".{c}" for c in counters)
            indent = line[:len(line) - len(line.lstrip())]
            out[i] = f"{indent}{num} {stripped}"
            prev_was_heading = True
            prev_was_body = False
            continue

        if stripped and not stripped.startswith("#") and not stripped.startswith("|"):
            prev_was_body = True
            prev_was_heading = False

    return out


# ── Step 3: 删空节 ──────────────────────────────────────────────────

def _has_content(lines, start, end):
    """检查 lines[start:end] 之间是否有实质内容。"""
    for line in lines[start:end]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        if s.startswith("> 源:"):
            continue
        if s.startswith("<!--"):
            continue
        return True
    return False


def step3_remove_empty(lines):
    """删除只有标题没有实质内容的 fire-spec section。"""
    # 找所有 fire-spec 标题位置
    headings = []
    for i, line in enumerate(lines):
        m = _FIRE_HEADING_RE.match(line) if line.startswith("#") else None
        if m and not line.startswith("# "):
            depth = len(m.group(1))
            headings.append((i, depth))

    if not headings:
        return lines

    # 找空 section(只看 ## 级别,不删 ### 子节)
    empty_ranges = []
    for idx, (pos, depth) in enumerate(headings):
        if depth != 2:  # 只检查 ## 级别
            continue
        # 找下一个同级或更高级标题
        next_pos = len(lines)
        for j in range(idx + 1, len(headings)):
            if headings[j][1] <= depth:
                next_pos = headings[j][0]
                break
        # 检查 pos 到 next_pos 之间有没有内容
        if not _has_content(lines, pos + 1, next_pos):
            empty_ranges.append((pos, next_pos))

    if not empty_ranges:
        return lines

    # 删除空 section(倒序删,避免索引偏移)
    out = list(lines)
    for start, end in reversed(empty_ranges):
        del out[start:end]
    return out


# ── Step 4: 生成目录 ────────────────────────────────────────────────

def step4_generate_toc(lines):
    """基于标题生成目录,插在报告标题之后、第一个 ## 之前。"""
    # 找报告大标题(# xxx)和第一个 ## 章节
    title_idx = None
    first_section_idx = None
    toc_entries = []

    for i, line in enumerate(lines):
        if line.startswith("# ") and title_idx is None:
            title_idx = i
        m = _FIRE_HEADING_RE.match(line) if line.startswith("#") else None
        if m and not line.startswith("# "):
            if first_section_idx is None:
                first_section_idx = i
            depth = len(m.group(1))
            number = m.group(2)
            title_text = m.group(3).strip()
            indent = "  " * (depth - 2)  # ## → 0缩进, ### → 1缩进
            toc_entries.append(f"{indent}- {number} {title_text}")

    if not toc_entries or first_section_idx is None:
        return lines

    toc_block = ["", "## 目录", ""]
    toc_block.extend(toc_entries)
    toc_block.append("")

    # 插入在第一个 ## 之前(如果 # 标题存在,在它之后)
    insert_at = first_section_idx
    return lines[:insert_at] + toc_block + lines[insert_at:]


# ── 主流程 ──────────────────────────────────────────────────────────

def format_report(report_md):
    lines = report_md.splitlines()
    lines = step1_strip_numbers(lines)
    lines = step3_remove_empty(lines)
    lines = step4_generate_toc(lines)
    return "\n".join(lines)


def main(argv):
    if len(argv) < 2:
        print("usage: format.py <input.md> <output.md> [passport.json]", file=sys.stderr)
        return 2
    report = Path(argv[0]).read_text(encoding="utf-8")
    result = format_report(report)
    out_path = Path(argv[1])
    out_path.write_text(result, encoding="utf-8")
    print(f"OK -> {argv[1]} ({len(result)} chars)")

    # Update passport if provided
    if len(argv) >= 3:
        passport_path = Path(argv[2])
        if passport_path.exists():
            import json
            passport = json.loads(passport_path.read_text(encoding="utf-8"))
            passport["stages"]["format"] = {
                "applied": True,
                "output_path": str(out_path),
                "output_chars": len(result),
                "toc_generated": "## 目录" in result,
            }
            passport_path.write_text(json.dumps(passport, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"PASSPORT_UPDATED: {passport_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
