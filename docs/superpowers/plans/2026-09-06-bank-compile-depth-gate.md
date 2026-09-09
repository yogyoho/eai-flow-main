# bank_compile 样例入库 + 深度门 实现计划（Plan 2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 投标样例入库工具（脱敏→切片→深度基线→RAGFlow 推送→台账登记）+ build 深度门（响应级命中组校准），打通"编造合法但有基线牵引"的内容质量闭环。

**Architecture:** `bank_compile.py`（技能 scripts/，stdlib 自包含，离线一键产全部衍生物）；`depth_targets.json`（技能 references/，absolute_floor=P25 全库段长）；build_output 深度门消费 `depth_target` 字段（stage4a 检索命中组写入，build 无状态）。脱敏自动规则+--map 显式对照双轨，残留扫描 rc=1 不出库。

**Tech Stack:** 纯 stdlib（zipfile+XML 解析 docx 文本，re 脱敏）；测试 pytest；真实语料验收用江西师大主标转出 md。

**依据 spec:** `docs/superpowers/specs/2026-09-06-bid-materials-two-skill-design.md` §4（本计划=spec §4 全量）+ §2.2 BidSample 台账（已落库）。

---

### Task 1: bank_compile.py——文本装载与章切片（纯函数）

**Files:**
- Create: `skills/public/bid-proposal-writing/scripts/bank_compile.py`
- Test: `backend/tests/test_bank_compile.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_bank_compile.py
"""bank_compile 样例入库工具：脱敏/切片/深度统计/产物确定性（纯函数契约）。"""
import json
import math
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "public" / "bid-proposal-writing" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import bank_compile as bc


@pytest.fixture
def tender_md(tmp_path):
    md = (
        "# 投标文件格式\n\n"
        "## 一、投标函\n\n"
        "致：江西师范大学。我方愿以总金额 1,280,000.00 元（含税）承接本项目，"
        "统一社会信用代码 91360100MA001AB2CD 为准。联系电话 13800138000。\n\n"
        "## 二、法定代表人身份证明\n\n"
        "身份证号 360102199001011234，姓名张三。\n\n"
        "## 三、开标一览表\n\n"
        "| 序号 | 名称 | 数量 | 单价(元) |\n| --- | --- | --- | --- |\n"
        "| 1 | 课堂观测终端 | 200 | 3,500.00 |\n\n"
        "以上报价含运输安装调试费用合计 700,000.00 元。\n"
    )
    p = tmp_path / "tender.md"
    p.write_text(md, encoding="utf-8")
    return p


def test_load_text_md(tender_md):
    assert bc.load_text(tender_md).startswith("# 投标文件格式")


def test_split_chapters_by_h1h2(tender_md):
    text = bc.load_text(tender_md)
    chapters = bc.split_chapters(text)
    titles = [c["title"] for c in chapters]
    assert any("投标函" in t for t in titles), "H2 章边界可切"
    assert all(c["text"].strip() for c in chapters), "零空章"


def test_paragraph_lengths(tender_md):
    text = bc.load_text(tender_md)
    lens = bc.paragraph_lengths(text)
    assert all(isinstance(x, int) and x >= 0 for x in lens)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bank_compile.py -v`
Expected: FAIL（`ModuleNotFoundError: bank_compile`）

- [ ] **Step 3: 写 bank_compile.py（本 Task 只实现装载/切片/统计三函数 + CLI 骨架，后续 Task 逐个补）**

```python
# skills/public/bid-proposal-writing/scripts/bank_compile.py
"""bank_compile——投标样例入库编译器(v4 WP-2/G1, 离线一键产全部衍生物)。

流程: 装载(标书 md/docx) → 章切片 → 自动脱敏(+--map 显式对照) → 残留扫描(rc=1 不出库)
→ 深度统计(P25 floor/全库 median) → 四产物(samples_bank 切片+指纹池+bank_index+depth_targets)
→ registration.json(供 backend/scripts/bid_seed_samples.py 入 BidSample 台账)
→ 可选 RAGFlow bid_samples 域推送(失败=warnings 不阻塞)。

stdlib 自包含(技能=自包含分发单元)。离线维护者工具, 不进 SKILL.md 速查表。
用法:
  python bank_compile.py --input 标书.md --title "江西师范大学课堂观测系统" \
    --industry 信息技术 --category IT软件平台 --bank-dir references/samples_bank \
    [--map map.json] [--ragflow-push]
退出码: 0 干净 / 1 用法或残留扫描命中。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1

HEAD1_RE = re.compile(r"^# (?!#)(.+)$")
HEAD2_RE = re.compile(r"^## (?!#)(.+)$")


def load_text(path: Path) -> str:
    """md 直读; docx 走内置极简文本抽取(段落带样式层级→md 标题)。"""
    if path.suffix.lower() == ".md":
        return path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".docx":
        return _docx_to_markdown(path)
    raise ValueError(f"不支持的输入类型: {path.suffix}(支持 .md/.docx)")


def _docx_to_markdown(path: Path) -> str:
    """docx → md(标题样式→# 层级, 段落照抄, 表格→管道表)。极简: 只服务切片。"""
    import zipfile

    from xml.etree import ElementTree as ET

    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines: list[str] = []
    with zipfile.ZipFile(str(path)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    for child in root.find(f"{W}body") or []:
        if child.tag == f"{W}p":
            text = "".join(t.text or "" for t in child.iter(f"{W}t")).strip()
            if not text:
                continue
            style = child.find(f"{W}pPr/{W}pStyle")
            sid = style.get(f"{W}val", "") if style is not None else ""
            m = __import__("re").match(r"^[Hh]eading(\d)$", sid) or __import__("re").match(r"^(\d)$", sid or "")
            lines.append(("#" * int(m.group(1)) + " " + text) if m else text)
        elif child.tag == f"{W}tbl":
            rows = child.findall(f"{W}tr")
            grid: list[list[str]] = []
            for tr in rows:
                grid.append(["".join(t.text or "" for t in tc.iter(f"{W}t")) for tc in tr.findall(f"{W}tc")])
            if grid:
                lines.append("| " + " | ".join(grid[0]) + " |")
                lines.append("|" + "---|" * len(grid[0]))
                for r in grid[1:]:
                    lines.append("| " + " | ".join(r) + " |")
    return "\n\n".join(lines)


def split_chapters(text: str) -> list[dict]:
    """章切片: H1/H2 标题为界连续分段(不重排——1:1 纪律)。返回 [{title, level, text}]。"""
    lines = text.split("\n")
    chapters: list[dict] = []
    cur: dict | None = None
    buf: list[str] = []

    def _flush():
        nonlocal cur, buf
        if cur is not None:
            cur["text"] = "\n".join(buf).strip()
            chapters.append(cur)
        buf = []

    for line in lines:
        m1 = HEAD1_RE.match(line)
        m2 = HEAD2_RE.match(line)
        if m1 or m2:
            _flush()
            cur = {"title": (m1 or m2).group(1).strip(), "level": 1 if m1 else 2, "text": ""}
            buf = [line]
        else:
            buf.append(line)
    _flush()
    return chapters


def paragraph_lengths(text: str) -> list[int]:
    """非空段落长度列表(深度统计输入)。"""
    return [len(p.strip()) for p in text.split("\n") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bank_compile.py", description="投标样例入库编译器(离线)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--industry", default="信息技术")
    ap.add_argument("--category", default="IT软件平台")
    ap.add_argument("--bank-dir", required=True)
    args = ap.parse_args()
    text = load_text(Path(args.input))
    _ = split_chapters(text)  # Task 3 起接入完整流水线
    print(json.dumps({"command": "bank_compile", "chapters": 0}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bank_compile.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-proposal-writing/scripts/bank_compile.py backend/tests/test_bank_compile.py
git commit -m "feat(bid-materials): bank_compile 装载/切片/段长统计(骨架)"
```

---

### Task 2: 脱敏引擎（规则+残留扫描）

**Files:**
- Modify: `skills/public/bid-proposal-writing/scripts/bank_compile.py`
- Test: `backend/tests/test_bank_compile.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_redact_auto_patterns(tender_md):
    text = bc.load_text(tender_md)
    redacted = bc.redact(text, mapping={})
    assert "1,280,000.00" not in redacted and "****" in redacted, "金额脱敏"
    assert "91360100MA001AB2CD" not in redacted, "信用代码脱敏"
    assert "13800138000" not in redacted, "手机号脱敏"
    assert "江西师范大学" in redacted, "无 --map 时机构名保留(不虚构替换)"


def test_redact_with_map(tender_md):
    text = bc.load_text(tender_md)
    redacted = bc.redact(text, mapping={"江西师范大学": "某大学【1】", "张三": "某人"})
    assert "江西师范大学" not in redacted and "某大学【1】" in redacted
    assert "张三" not in redacted and "某人" in redacted


def test_residual_scan_hits(tender_md):
    text = bc.load_text(tender_md)
    redacted = bc.redact(text, mapping={})
    hits = bc.residual_scan(redacted)
    assert hits == [], f"自动脱敏后零残留: {hits}"


def test_residual_scan_catches_miss(tender_md):
    assert bc.residual_scan("报价 9,999,999.99 元") != [], "漏网金额必须被扫描抓到"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_bank_compile.py -k redact -v`
Expected: FAIL（`no attribute redact`）

- [ ] **Step 3: 实现（追加到 bank_compile.py）**

```python
AMOUNT_RE = re.compile(r"[￥¥]?\s*\d{1,3}(?:[,，]\d{3})*(?:\.\d+)?\s*(?:万?元)")
CREDIT_CODE_RE = re.compile(r"\b[0-9A-HJ-NPQRTUWXY]{18}\b")
PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
RESIDUAL_RE = re.compile(r"[￥¥]\s*\d|万元|\b1[3-9]\d{9}\b|\b\d{17}[\dXx]\b")


def redact(text: str, mapping: dict[str, str]) -> str:
    """脱敏: --map 显式对照优先(逐字替换), 再跑自动模式(金额/信用代码/手机号/身份证)。
    mapping 键=原文, 值=脱敏占位; 不动标题行(# 开头)——章结构保真。"""
    out_lines = []
    for line in text.split("\n"):
        if line.lstrip().startswith("#"):
            out_lines.append(line)
            continue
        for src, dst in mapping.items():
            if src:
                line = line.replace(src, dst)
        line = AMOUNT_RE.sub("****", line)
        line = CREDIT_CODE_RE.sub("****", line)
        line = PHONE_RE.sub("****", line)
        line = ID_CARD_RE.sub("****", line)
        out_lines.append(line)
    return "\n".join(out_lines)


def residual_scan(text: str) -> list[str]:
    """残留扫描(脱敏后质检): 命中即返回证据行(调用方 rc=1 不出库)。"""
    return [ln.strip()[:120] for ln in text.split("\n") if RESIDUAL_RE.search(ln)]
```

（`RESIDUAL_RE`/`PHONE_RE`/`ID_CARD_RE` 放模块常量区。测试 `test_residual_scan_hits` 期望空列表——tender fixture 的金额/手机号已被自动模式脱净。）

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_bank_compile.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-proposal-writing/scripts/bank_compile.py backend/tests/test_bank_compile.py
git commit -m "feat(bid-materials): 脱敏引擎(自动模式+--map 对照+残留扫描)"
```

---

### Task 3: 深度统计与四产物（bank_index/depth_targets/registration/切片落盘）

**Files:**
- Modify: `skills/public/bid-proposal-writing/scripts/bank_compile.py`
- Test: `backend/tests/test_bank_compile.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_compile_outputs_full_pipeline(tender_md, tmp_path):
    bank_dir = tmp_path / "samples_bank"
    rc = bc.main([
        "--input", str(tender_md), "--title", "江西师范大学课堂观测系统",
        "--industry", "信息技术", "--category", "IT软件平台",
        "--bank-dir", str(bank_dir),
    ])
    assert rc == 0
    slug_dir = bank_dir / "jiangshishifandaxueketanguance"  # title 拼音 slug
    full = slug_dir / "full.md"
    assert full.is_file() and "投标函" in full.read_text(encoding="utf-8")
    index = json.loads((bank_dir / "bank_index.json").read_text(encoding="utf-8"))
    assert "jiangshishifandaxueketanguance" in index
    targets = json.loads((bank_dir / "depth_targets.json").read_text(encoding="utf-8"))
    assert targets["absolute_floor"] > 0 and targets["global_median"] > 0
    reg = json.loads((bank_dir / "registration.json").read_text(encoding="utf-8"))
    assert reg["items"] and reg["items"][0]["scenario"] == "bid_sample"
    # 确定性: 重跑字节一致
    before = {p.name: p.read_bytes() for p in bank_dir.rglob("*") if p.is_file()}
    bc.main(["--input", str(tender_md), "--title", "江西师范大学课堂观测系统",
             "--industry", "信息技术", "--category", "IT软件平台", "--bank-dir", str(bank_dir)])
    after = {p.name: p.read_bytes() for p in bank_dir.rglob("*") if p.is_file()}
    assert before == after, "重跑字节级幂等"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_bank_compile.py::test_compile_outputs_full_pipeline -v`
Expected: FAIL（main 未接流水线）

- [ ] **Step 3: 实现（slug/统计/产物落盘，追加函数并重写 main）**

```python
def slugify(title: str) -> str:
    """项目名 slug: 非字母数字(含 CJK)→拼音不可用时退化为 hash 前缀——直接用
    hash 前缀(title.encode sha1[:12])保证 ASCII 文件名确定性, 可读名进 bank_index。"""
    return hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]


def percentile(sorted_vals: list[int], pct: float) -> int:
    if not sorted_vals:
        return 0
    idx = min(len(sorted_vals) - 1, max(0, round(pct / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def compile_bank(text: str, *, title: str, industry: str, category: str, mapping: dict[str, str]) -> dict:
    """全流水线(纯函数): 脱敏→切片→统计→四产物数据。返回 dict(无 IO)。"""
    redacted = redact(text, mapping)
    residual = residual_scan(redacted)
    chapters = [
        {**c, "text": redacted分段对齐}
        for c in split_chapters(redacted)
    ]
    # 段长分布(脱敏全册)
    lengths = sorted(paragraph_lengths(redacted))
    floor = percentile(lengths, 25)
    gmedian = percentile(lengths, 50)
    digest = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
    return {
        "redacted": redacted, "residual": residual,
        "chapters": chapters, "file_hash": digest,
        "depth_targets": {"absolute_floor": floor, "global_median": gmedian,
                          "calibrated_from": digest},
        "registration_item": {"title": title, "source_path": "", "file_hash": digest,
                              "industry": industry, "project_category": category,
                              "scenario": "bid_sample", "status": "indexed"},
    }
```

（实现注：`chapters` 的 text 用 `redacted` 重切——即 `split_chapters(redacted)`；上面 dict-comp 伪码替换为直接二次调用 `split_chapters(redacted)`。`main()` 组装：读 --map（可选 json）、调 compile_bank、`slug=slugify(title)`、落盘 `slug_dir/full.md`+`chapters/chNN__{slug短名}.md`+`bank_index.json`+`depth_targets.json`+`registration.json`（全 sort_keys 确定性）、可选 `--ragflow-push`（Task 5 接入）。残留 `residual` 非空 → 打印证据行 + return EXIT_ERROR 不落盘。）

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. uv run pytest tests/test_bank_compile.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-proposal-writing/scripts/bank_compile.py backend/tests/test_bank_compile.py
git commit -m "feat(bid-materials): 深度统计+四产物确定性落盘(P25 floor/bank_index/registration)"
```

---

### Task 4: 残留扫描 rc=1 与 CLI 收口

**Files:**
- Modify: `skills/public/bid-proposal-writing/scripts/bank_compile.py`
- Test: `backend/tests/test_bank_compile.py`（追加残留拒出库用例）

- [ ] **Step 1: 写失败测试**

```python
def test_residual_hits_block_output(tmp_path):
    """残留扫描命中 → rc=1 且零落盘(不静默出库)。"""
    dirty = tmp_path / "dirty.md"
    dirty.write_text("# 投标函\n\n报价 1,280,000.00 元整，此行含漏网金额。\n", encoding="utf-8")
    rc = bc.main([
        "--input", str(dirty), "--title", "测试项目", "--industry", "信息技术",
        "--category", "IT软件平台", "--bank-dir", str(tmp_path / "bank"),
    ])
    assert rc == 1
    assert not (tmp_path / "bank" / "bank_index.json").exists(), "残留命中=零落盘"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. uv run pytest tests/test_bank_compile.py::test_residual_hits_block_output -v`
Expected: FAIL（当前 main 恒 0 且落盘）

- [ ] **Step 3: main 接残留闸门**

main 内 compile_bank 后：`if result["residual"]: 打印证据行; return EXIT_ERROR`（零落盘）。

- [ ] **Step 4: 跑测试确认通过 + 全文件绿**

Run: `PYTHONPATH=. uv run pytest tests/test_bank_compile.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/public/bid-proposal-writing/scripts/bank_compile.py backend/tests/test_bank_compile.py
git commit -m "feat(bid-materials): 残留扫描闸门(rc=1 零落盘)"
```

---

### Task 5: RAGFlow 推送（可选，失败=warnings）

**Files:**
- Modify: `skills/public/bid-proposal-writing/scripts/bank_compile.py`
- Test: `backend/tests/test_bank_compile.py`（追加 mock 用例）

- [ ] **Step 1: 写失败测试**

```python
def test_ragflow_push_called_when_enabled(monkeypatch, tmp_path, tender_md, capsys):
    calls: list[tuple] = []
    monkeypatch.setenv("BID_RAGFLOW_DATASET_ID", "ds-123")
    monkeypatch.setattr(bc, "ragflow_push",
                        lambda md, meta: calls.append((md[:50], meta)) or True)
    rc = bc.main([
        "--input", str(tender_md), "--title", "测试项目", "--industry", "信息技术",
        "--category", "IT软件平台", "--bank-dir", str(tmp_path / "bank"),
        "--ragflow-push",
    ])
    assert rc == 0
    assert len(calls) == 1 and "投标文件格式" in calls[0][0]
    assert calls[0][1]["title"] == "测试项目" and calls[0][1]["dataset_id"] == "ds-123"


def test_ragflow_push_skipped_without_env(monkeypatch, tmp_path, tender_md, capsys):
    monkeypatch.delenv("BID_RAGFLOW_DATASET_ID", raising=False)
    calls: list[tuple] = []
    monkeypatch.setattr(bc, "ragflow_push",
                        lambda md, meta: calls.append((md, meta)) or True)
    rc = bc.main([
        "--input", str(tender_md), "--title", "测试项目", "--industry", "信息技术",
        "--category", "IT软件平台", "--bank-dir", str(tmp_path / "bank"),
        "--ragflow-push",
    ])
    assert rc == 0 and calls == [], "无 dataset id=跳过推送不报错"
```

- [ ] **Step 2: 实现 `ragflow_push(md, meta) -> bool`**（urllib POST 到 RAGFlow HTTP API，env 无 dataset id → False + warning；异常吞掉记 warning 返回 False——不阻塞）

- [ ] **Step 3: 跑测试 + Commit**（形态同前）

---

### Task 6: depth_target 字段贯通（schemas/responses/build 深度门）

**Files:**
- Modify: `skills/public/bid-proposal-writing/references/responses.schema.json`（+`depth_target`: integer ≥0 可选）
- Modify: `skills/public/bid-proposal-writing/scripts/responses.py`（merge 透传 depth_target——validate 校验 ≥0 整数形态）
- Modify: `skills/public/bid-proposal-writing/scripts/build_output.py`（深度门：读 references/depth_targets.json absolute_floor；逐条 response 实质长（复用 responses.py `_substantive_chars` 口径——import 或复制常量口径）vs depth_target 不足 → anomaly `depth_below_target`；无 depth_target 且实质长 < absolute_floor → anomaly `depth_below_floor`；落 实体lint报告.md 相邻新"深度"节或覆盖率报表——按 spec §4.4 落 lint 报告"深度"节）
- Modify: `skills/public/bid-proposal-writing/references/tech_response_prompt.md`（第一层检索落地指引：RAGFlow filters 按章组批量查询→命中段落 median 写入候选 `depth_target` 字段——含 SampleBulkImportResponse 无关说明删除）
- Test: `backend/tests/test_bid_materials.py`（追加深度门三态用例：有 target 达标/不足/无 target floor；测试与实现代码在执行时按 Task 4 已落的 `_substantive_chars` 实况对齐——写本任务时先读 responses.py 与 build_output.py 的实质长口径函数再落笔）

- [ ] **Step 1: 写失败测试**（三态，fixture 结构复用 TestEntityGateV4 的 _copy_prestate+responses 直写模式）
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: schemas+responses+build 三处实现**
- [ ] **Step 4: 全绿**
- [ ] **Step 5: Commit** `feat(bid-materials): 深度门贯通(depth_target 字段+build 双异常)`

（本任务测试与实现代码在执行时按 Task 4 已落的 `_substantive_chars` 实况对齐——写 Task 6 时先读 responses.py 该函数再落笔。）

---

### Task 7: 真实语料验收 + 全量回归 + 推送

- [ ] **Step 1**: markitdown 转 `D:\14 九次方存档\...\招标文件正文.pdf` → md，跑 bank_compile 全流程，人工走查脱敏册（金额/证号/人名零残留）
- [ ] **Step 2**: 三份标书（江西师大/东北大学一张表/中石油 PaaS）各产 registration.json
- [ ] **Step 3**: `bid_seed_samples.py` 入库（BidSample 3 行）+ 走查 KF 样例库 tab（同库不同 scenario 不混淆）
- [ ] **Step 4**: 全量回归 8 测试文件 + ruff
- [ ] **Step 5**: push + rev-list 0/0

---

## 后续计划

- **Plan 3**: 技能拆分（bid-proposal-overall / bid-technical 目录重组 + 两 SKILL.md）——bank_compile 随 B 迁移
- **Plan 4**: 前端 bid-materials 页面（镜像 frontend/src/app/coal-eia-samples/ + frontend/src/extensions/eia-samples/）
- **T6b 完结**: 深度门本章落 absolute_floor+响应级 target；章角色级校准随样例库语料增长演进
