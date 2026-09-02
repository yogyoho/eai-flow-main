# Geo Sample Bank — Phase 2（编译管线与技能消费对接）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reviewed 样例经 bank_compile 编译为技能 repo 衍生物（per 矿种深度基线 / 范文切片库 / SL3 指纹扩容 / bank_index），resolve_targets 按用户矿种自动选基线，RAGFlow 切片分发上线并通过分块质量验收——写一篇非铜矿报告时深度门/范文参照/SL3 全部吃到新样例。

**Architecture:** 模块后端（可碰 DB/MinIO/网络）准备编译工作区并触发 skill CLI 子进程（纯 stdlib，cwd=技能 scripts/，contract_price 模板+超时加固）；skill CLI 产出 repo 内确定性文件；RAGFlow 分发在模块侧异步执行（delete-by-name 幂等上传）。技能侧改动仅 resolve_targets 一处探测步 + 文档两处——其余四个消费点零改动自动生效。

**Tech Stack:** 纯 stdlib skill CLI（复用 calibrate 子进程）+ FastAPI BackgroundTasks + RAGFlowClient（extensions knowledge）+ rstest（仅 T3 一行前端）。

**Spec:** `docs/superpowers/specs/2026-09-01-geo-sample-bank-design.md` §3.4/§5/§6/§9-Phase2；详细设计 `2026-09-02-geo-sample-bank-detailed-design.md` §2.5/§5；终审风险 R1/R2/R3 前置。

**约定（全任务通用）：**
- 后端测试 `cd backend && PYTHONPATH=. uv run pytest tests/<file> -v`；技能脚本测试统一在新文件 `backend/tests/test_geo_sample_bank_compile.py`（`sys.path.insert(0, str(SKILL/scripts))` 直 import，沿用 test_geological_report_v2_scripts.py:34 模式）。
- **并发漂移防线**：skills/public/geological-report 正被并发会话硬化（基线 build_output=61d03175d、SKILL.md=838da31c2、consistency=5896a115e）。每个触碰技能文件的任务开工前先 `git log -1 -- <file>` 复核，行号漂移>10 行时按语义重锚并在报告里注明。
- pathspec 提交；不 restart docker（T10 统一做）；EAI-CUSTOM 头注明 `(geo-sample-bank Phase 2, spec 2026-09-01)`。

---

### Task 1: R1 前置——docx 标题样式别名归一（中文 Word 样式防降级）

**Files:**
- Modify: `backend/app/extensions/geo_samples/parsers.py`（docx_to_markdown 标题映射处，现 ~44-61 行）
- Test: `backend/tests/test_geo_samples_parsers.py`（追加）

中文 authored 的 docx 样式名常为「标题 1」而非 "Heading 1"——现映射 `style.startswith("heading 1")` 会整篇降级为正文，Phase 2 切片将找不到任何 `## N.M`（R1 根因）。

- [ ] **Step 1: 写失败测试**

```python
def test_docx_localized_heading_styles():
    """中文 Word 样式名（标题 1/标题 2）须归一化进标题映射——R1 防线。"""
    from docx import Document
    from app.extensions.geo_samples.parsers import docx_to_markdown

    doc = Document()
    doc.add_paragraph("第1章 总论", style="Heading 1")
    p = doc.add_paragraph("1.1 编制依据")
    p.style = doc.styles["Heading 2"]
    buf = io.BytesIO()
    doc.save(buf)
    md = docx_to_markdown(buf.getvalue())
    assert "## 第1章 总论" in md and "### 1.1 编制依据" in md


def test_docx_style_alias_map():
    from app.extensions.geo_samples.parsers import _heading_level

    assert _heading_level("Heading 1") == 1
    assert _heading_level("Title") == 1
    assert _heading_level("标题 1") == 1
    assert _heading_level("标题 2") == 2
    assert _heading_level("标题 3") == 3
    assert _heading_level("Heading 4") in (3, 4)
    assert _heading_level("Normal") is None
```

- [ ] **Step 2: 跑测试确认失败**（`_heading_level` 不存在 → FAIL）

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_geo_samples_parsers.py -v`

- [ ] **Step 3: 实现别名归一**

parsers.py 新增（docx_to_markdown 上方）：

```python
# 中文/英文 Word 内置样式名归一——中文 authored docx 的样式名是「标题 1」而非
# "Heading 1"，不归一则整篇降级正文、Phase 2 节号切片将找零节（终审 R1）。
_STYLE_ALIASES = {"标题 1": "heading 1", "标题 2": "heading 2", "标题 3": "heading 3",
                  "标题 4": "heading 4", "标题 5": "heading 5", "标题": "title"}


def _heading_level(style_name: str | None) -> int | None:
    """样式名 → 标题级（1=##/2=###/3+=####）；非标题返回 None。"""
    if not style_name:
        return None
    s = _STYLE_ALIASES.get(style_name.strip(), style_name.strip()).lower()
    if s == "title" or s.startswith("heading 1"):
        return 1
    if s.startswith("heading 2"):
        return 2
    if s.startswith(("heading 3", "heading 4", "heading 5")):
        return 3
    return None
```

docx_to_markdown 内标题分支替换为：

```python
            lvl = _heading_level(block.style.name if block.style is not None else None)
            if lvl == 1:
                lines.append(f"## {text}")
            elif lvl == 2:
                lines.append(f"### {text}")
            elif lvl == 3:
                lines.append(f"#### {text}")
            else:
                lines.append(text)
```

- [ ] **Step 4: 跑测试确认通过**（parsers 全绿，原 4+2 用例不回归）→ **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/parsers.py backend/tests/test_geo_samples_parsers.py
git commit -m "fix(geo-samples): docx localized heading style alias map (R1 preflight)" -- backend/app/extensions/geo_samples/parsers.py backend/tests/test_geo_samples_parsers.py
```

---

### Task 2: R2 前置——run_parse 事务释放（OCR 1800s 不占连接）

**Files:**
- Modify: `backend/app/extensions/geo_samples/service.py`（run_parse）
- Test: `backend/tests/test_geo_samples_service.py`（追加）

现状：run_parse 的 SELECT 之后连接一直被占，OCR 分支最长 1800s——批量扫描入库会榨干 asyncpg 池（终审 R2）。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_run_parse_releases_connection_before_heavy_work(monkeypatch):
    """OCR 级重活前必须 commit 释放连接、重活后重取文档（R2）。"""
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r5", file_name="a.pdf", file_hash="h", file_type="pdf",
                      status="uploaded", raw_uri="s3://geo-samples/raw/r5/a.pdf")
    events = []

    async def _get(db_, did):
        events.append("get")
        return doc

    async def _heavy(*a, **k):
        events.append("heavy")

    def _get_obj(uri):
        events.append("getobj")
        return b"pdf"

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.storage, "get_object", _get_obj)
    monkeypatch.setattr(service.parsers, "parse_document", _heavy)
    monkeypatch.setattr(service.storage, "put_work", lambda rid, d: f"s3://geo-samples/work/{rid}/parsed.md")
    db = MagicMock()
    db.commit = AsyncMock(side_effect=lambda: events.append("commit"))
    db.refresh = AsyncMock()

    await service.run_parse(db, "doc-5", run_id="run-5")
    assert doc.status == "parsed"
    # 连接释放必须发生在 heavy 之前
    assert events.index("commit") < events.index("heavy")
    # 重活后必须重取文档（状态可能已被 sweep/驳回改变）
    assert events.count("get") >= 2
```

- [ ] **Step 2: 确认失败** → **Step 3: 重构 run_parse**（成功路径三段式；失败路径同构处理）：

```python
async def run_parse(db: AsyncSession, document_id: str, run_id: str) -> None:
    doc = await crud.get_document(db, document_id)
    if doc is None:
        await _finish_run(db, run_id, "failed", "document not found")
        return
    raw_uri, file_name, report_id = doc.raw_uri, doc.file_name, doc.report_id
    await db.commit()  # R2：释放连接再进重活（OCR 最长 1800s，占池会楔死无关请求）
    try:
        raw = await asyncio.to_thread(storage.get_object, raw_uri)
        md, mode = await parsers.parse_document(file_name, raw)  # 重活（内含 to_thread/OCR）
        doc = await crud.get_document(db, document_id)  # 重活后重取——状态可能已被 sweep 改判
        if doc is None or doc.status not in ("uploaded", "failed", "parsed"):
            await _finish_run(db, run_id, "failed", f"document state changed during parse: {doc.status if doc else 'gone'}")
            return
        doc.work_uri = await asyncio.to_thread(storage.put_work, doc.report_id, md.encode("utf-8"))
        doc.parse_mode = mode
        doc.status = "parsed"
        await db.commit()
        await _finish_run(db, run_id, "done", f"mode={mode}")
    except Exception as exc:  # noqa: BLE001
        log.exception("parse failed for %s (%s)", report_id, document_id)
        # except 分支保持 4ff600824 版本原样（守护 rollback → failed → 守护 commit → _finish_run），仅
        # 注意 except 内引用的 doc 字段改用 report_id/file_name 局部变量（doc 可能重取失败为 None）
```

- [ ] **Step 4: 全套件绿**（`pytest tests/test_geo_samples_service.py tests/test_geo_samples_parsers.py -q`）→ **Step 5: Commit**

```bash
git commit -m "fix(geo-samples): release DB connection before OCR-heavy parse work (R2)" -- backend/app/extensions/geo_samples/service.py backend/tests/test_geo_samples_service.py
```

---

### Task 3: R3 前置——前端统计查询突破 limit=50

**Files:**
- Modify: `frontend/src/extensions/geo-samples/components/DocumentsView.tsx`（统计头查询 ~:75-81）

- [ ] **Step 1:** 统计头查询改 `useGsbDocuments({ limit: 200 })`（后端 le=200；计数端点 Phase 3 再做）——`useGsbDocuments` 的 filters 类型加 `limit?: number`（hooks.ts 一行）。
- [ ] **Step 2:** `cd frontend && pnpm typecheck && pnpm lint` → **Step 3: Commit**

```bash
git commit -m "fix(geo-samples): stats header queries beyond limit=50 (R3)" -- frontend/src/extensions/geo-samples/components/DocumentsView.tsx frontend/src/extensions/geo-samples/hooks.ts
```

---

### Task 4: resolve_targets 矿种选基线（commodity 归一化 + 探测链扩展）

**Files:**
- Modify: `skills/public/geological-report/scripts/build_output.py`（resolve_targets ~:439-461 + 顶部常量区；两处调用方 progress.py:300、build_output CLI main）
- Test: `backend/tests/test_geo_sample_bank_compile.py`（新建）

设计（recon 实证）：`data/00_project.json` 的 `commodity` 是中文自由文本（实物「铜」/「铜银金」，无词表）；`stage` 是三值枚举。归一化=关键词扫描（顺序即优先级，"铜银金" 含「铜」→ copper）；基线目录 `references/depth_targets/<stage_stem>/<mineral>.json`；无命中/无文件 → 走既有探测链完全不变。样例库基线由门控 compile 生成、属技能自有资产——**不打 bug-3058 非基准警告**，但 origin 照记。

- [ ] **Step 1: 写失败测试**（新文件，头部 `sys.path.insert(0, str(SKILL/"scripts"))`）

```python
"""bank_compile / resolve_targets 矿种选基线单元测试（Phase 2）。"""
import json, sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "skills" / "public" / "geological-report"
sys.path.insert(0, str(SKILL / "scripts"))

import build_output  # noqa: E402


def test_normalize_mineral_aliases():
    assert build_output.normalize_mineral("铜") == "copper"
    assert build_output.normalize_mineral("铜银金") == "copper"   # 连写取首命中（优先级序）
    assert build_output.normalize_mineral("岩金") == "gold"
    assert build_output.normalize_mineral("煤矿") == "coal"
    assert build_output.normalize_mineral("铅锌矿") == "lead_zinc"
    assert build_output.normalize_mineral("萤石") is None         # 词表外 → None
    assert build_output.normalize_mineral("") is None
    assert build_output.normalize_mineral(None) is None


@pytest.mark.asyncio
async def test_resolve_targets_mineral_dir_precedence(tmp_path, monkeypatch, capsys):
    """样例库基线存在时优先于三级探测与 CANONICAL 兜底；origin 记 sample-bank。"""
    stage = tmp_path / "stages" / "exploration.json"
    stage.parent.mkdir(parents=True)
    stage.write_text("{}", encoding="utf-8")
    refs = SKILL / "references"
    mineral_file = refs / "depth_targets" / "exploration" / "gold.json"
    mineral_file.parent.mkdir(parents=True, exist_ok=True)
    baseline = {"coefficient": 0.6, "scale_floor": 0.25, "per_signal_penalty": 0.05,
                "missing_table_weight": 8, "absolute_floor": 0.4, "samples": [], 
                "per_chapter": {f"ch{i}": {"median_eff": 900, "median_table_rows": 2, "median_paragraphs": 3} for i in range(1, 11)}}
    mineral_file.write_text(json.dumps(baseline, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text(json.dumps({"commodity": "岩金", "stage": "勘探"}), encoding="utf-8")
    try:
        targets, src = build_output.resolve_targets(None, stage, data_dir=data_dir)
        assert targets["per_chapter"]["ch1"]["median_eff"] == 900
        assert "gold" in src
        captured = capsys.readouterr()
        assert "非技能基准" not in captured.err      # 技能自有资产不打非基准警告
    finally:
        import shutil; shutil.rmtree(mineral_file.parent.parent, ignore_errors=True)


def test_resolve_targets_fallback_unchanged(tmp_path):
    """无矿种/无基线文件时走既有链（data_dir 不存在/词表外），兜底 CANONICAL——向后兼容。"""
    stage = tmp_path / "stages" / "exploration.json"
    stage.parent.mkdir(parents=True)
    stage.write_text("{}", encoding="utf-8")
    data_dir = tmp_path / "data"                    # 目录不存在
    targets, _src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets is not None                      # 兜底 CANONICAL（技能自带铜矿基线）
```

- [ ] **Step 2: 确认失败** → **Step 3: 实现**（build_output.py）：

```python
# EAI-CUSTOM (geo-sample-bank Phase 2): commodity 中文串 → 样例库基线 slug 归一化。
# 顺序即优先级：「铜银金」含「铜」→ copper（首命中）；词表外返回 None 走既有探测链。
MINERAL_ALIASES = [
    ("copper", ("铜",)),
    ("coal", ("煤",)),
    ("gold", ("金",)),
    ("iron", ("铁",)),
    ("lead_zinc", ("铅锌", "铅", "锌")),
]


def normalize_mineral(commodity: str | None) -> str | None:
    if not commodity:
        return None
    for slug, keys in MINERAL_ALIASES:
        if any(k in commodity for k in keys):
            return slug
    return None


def _project_mineral(data_dir) -> str | None:
    if data_dir is None:
        return None
    p = Path(data_dir) / "00_project.json"
    if not p.exists():
        return None
    try:
        return normalize_mineral(json.loads(p.read_text(encoding="utf-8")).get("commodity"))
    except (OSError, ValueError):
        return None
```

resolve_targets 签名加 `data_dir: str | Path | None = None`（默认 None=全部既有调用零改动），在 `--targets` 分支后插入：

```python
    mineral = _project_mineral(Path(data_dir) if data_dir else None)
    if mineral:
        cand = Path(__file__).resolve().parent.parent / "references" / "depth_targets" / stage_path.stem / f"{mineral}.json"
        if cand.exists():
            targets = load_targets(cand)
            origin = f"sample-bank:{cand.name}"
            print(f"[build] 深度基准: {cand}（样例库编译产物，来源已记入 delivery_manifest）", file=sys.stderr)
            return targets, str(cand)
```

两处调用方各加一参：progress.py:300 `resolve_targets(args.targets, Path(doc["stage_path"]), data_dir=Path(doc["data_dir"]))`；build_output CLI main 的 resolve_targets 调用加 `data_dir=Path(args.data_dir)`（以实物参数名为准 grep 核对）。load_targets 若对缺 absolute_floor 有兜底行为则天然兼容新键。

- [ ] **Step 4: 全绿**（新测试 + `pytest tests/test_geological_report_v2_scripts.py -q` 回归）→ **Step 5: Commit**（pathspec：build_output.py、progress.py、新测试文件，消息 `feat(geo-samples): resolve_targets per-mineral baseline via commodity normalization (Phase 2 T4)`）

---

### Task 5: bank_compile.py——切片 + bank_index + SL3 扩容 + 标定（skill CLI，纯 stdlib）

**Files:**
- Create: `skills/public/geological-report/scripts/bank_compile.py`
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加）

**输入契约（模块后端准备）**：`--workdir` 下 `<report_id>/source.md`（脱敏全文）+ `workdir/manifest.json`：`[{"report_id","stage","mineral","file_name"}]`（stage/mineral 为 slug，由模块侧 gsb_documents 直读——模块可信，无需再归一化）。`--references` 指向技能 references 目录。

- [ ] **Step 1: 写失败测试**（构造 2 份合成报告 workdir：金/铜各 1，含 `## 1`/`## 2`/`### 2.1` 节号与正文；断言：切片文件落位 `samples_bank/exploration/slices/ch1/<rid>__1.md` 且首行含标记 `【矿种】gold｜【阶段】exploration｜【report_id】…｜【节号】1`；`samples/exploration/ch1__<rid>.md` 存在（SL3 源）；`depth_targets/exploration/gold.json` 生成且含 `absolute_floor: 0.4` 键与 per_chapter medians；`bank_index.json` 结构 `{"exploration":{"ch1":[{"report_id","sec","path"}]}}` sort_keys 幂等（二连跑字节同）；全部报告零切片 → rc=1）

- [ ] **Step 2: 确认失败** → **Step 3: 实现 bank_compile.py**（骨架 ~170 行，要点）：

```python
#!/usr/bin/env python3
"""bank_compile — reviewed 样例 → 技能衍生物的确定性编译器（Phase 2，spec 2026-09-01 §5）。
纯 stdlib + sibling import；无网络（RAGFlow 分发在模块侧）。维护者动作：由管理模块门控触发。
退出码：0 成功 / 1 用法错或全部报告零切片（绝不静默产空基线——calibrate 同纪律）"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
SEC_RE = re.compile(r"^(#{2,4})\s+(\d+(?:\.\d+)*)\s", re.MULTILINE)


def slice_report(text: str) -> list[tuple[str, str]]:
    """按节号标题切片；无节号 → 空列表（调用方计数，不抛——单报告降级不拖垮整批）。"""
    marks = [(m.start(), m.group(2)) for m in SEC_RE.finditer(text)]
    if not marks:
        return []
    out = []
    for i, (pos, sec) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.append((sec, text[pos:end].rstrip() + "\n"))
    return out


def mark_line(mineral: str, stage: str, rid: str, sec: str) -> str:
    return f"【矿种】{mineral}｜【阶段】{stage}｜【report_id】{rid}｜【节号】{sec}\n\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)      # <rid>/source.md + manifest.json
    ap.add_argument("--references", required=True)   # 技能 references 目录
    ap.add_argument("--python", default=sys.executable)  # calibrate 子进程解释器
    a = ap.parse_args()
    workdir, refs = Path(a.workdir), Path(a.references)
    manifest = json.loads((workdir / "manifest.json").read_text(encoding="utf-8"))
    index: dict = {}
    zero_slice = []
    for entry in manifest:                                   # ① 切片 + 双落点
        rid, stage, mineral = entry["report_id"], entry["stage"], entry["mineral"]
        text = (workdir / rid / "source.md").read_text(encoding="utf-8")
        slices = slice_report(text)
        if not slices:
            zero_slice.append(rid)
            continue
        for sec, body in slices:
            ch = "ch" + sec.split(".")[0]
            rel = f"samples_bank/{stage}/slices/{ch}/{rid}__{sec}.md"
            dst = refs / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(mark_line(mineral, stage, rid, sec) + body, encoding="utf-8")
            index.setdefault(stage, {}).setdefault(ch, []).append(
                {"report_id": rid, "sec": sec, "path": rel})
            (refs / "samples" / stage).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dst, refs / "samples" / stage / f"{ch}__{rid}.md")  # SL3 指纹源（glob 同层自动纳管）
    (refs / "samples_bank" / "bank_index.json").parent.mkdir(parents=True, exist_ok=True)
    (refs / "samples_bank" / "bank_index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if not index:
        print(f"[bank_compile] 错误: {len(manifest)} 份报告全部零节号切片（标题样式/内容异常）", file=sys.stderr)
        return 1
    # ② 标定：per (stage,mineral) 组建临时样例目录 → 子进程调 calibrate（不改 calibrate 一行）
    rid2mineral = {e["report_id"]: e["mineral"] for e in manifest}
    groups: dict[tuple, list[Path]] = {}
    for stage, chs in index.items():
        for ch, items in chs.items():
            for it in items:
                mineral = rid2mineral[it["report_id"]]
                groups.setdefault((stage, mineral), []).append(refs / it["path"])
    for (stage, mineral), paths in sorted(groups.items()):
        with tempfile.TemporaryDirectory() as td:
            for p in paths:
                shutil.copyfile(p, Path(td) / p.name.replace("__", "_", 1))  # ch1__rid → ch1_rid 满足 FNAME_RE ^ch(\d+)
            out = refs / "depth_targets" / stage / f"{mineral}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run([a.python, "-X", "utf8", str(Path(__file__).parent / "calibrate.py"),
                                "--samples-dir", td, "--output", str(out)], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[bank_compile] 警告: {stage}/{mineral} 标定失败 rc={r.returncode}（该组跳过）: {r.stderr[:200]}", file=sys.stderr)
                continue
            doc = json.loads(out.read_text(encoding="utf-8"))
            doc["absolute_floor"] = 0.4   # 代码默认落盘显式化（build_output 三处 .get 不变，键生效）
            out.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"[bank_compile] 完成: 切片 {sum(len(v) for chs in index.values() for v in chs.values())} 片, "
          f"零切片 {len(zero_slice)} 份 {zero_slice or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

（`...` 处 rid→mineral 反查用 manifest 建字典，实现时补全；测试断言细节按 Step 1。）

- [ ] **Step 4: 全绿 + 幂等复跑字节同** → **Step 5: Commit**（`feat(geo-samples): bank_compile slicer + bank_index + per-mineral calibration (Phase 2 T5)`）

---

### Task 6: SKILL.md 派发契约与 chapter_craft 升级（bank 优先、东川回退）

**Files:**
- Modify: `skills/public/geological-report/SKILL.md:118-119`（自读输入清单两行）
- Modify: `skills/public/geological-report/references/chapter_craft.md:33,41`

- [ ] **Step 1:** SKILL.md:118 行替换为：

```markdown
              references/samples_bank/bank_index.json —— 范文索引：优先取同矿种同节号切片
              references/samples/exploration/chN_sample.md —— 东川铜矿同章范文（bank 无该章时回退）
```

119 行替换为：

```markdown
              references/depth_targets/<阶段>/<矿种>.json —— 该矿种深度基线（矿种=00_project.commodity 归一化；无对应文件回退 references/depth_targets.json，以门报错行内嵌目标为准）
```

- [ ] **Step 2:** chapter_craft.md:41 范文段前插一句「优先读 bank_index.json 里同矿种同节号切片（真实同矿种范式）；无则读东川 chN_sample.md」；:33 深度段同样补「per 矿种基线优先，回退规则同上」。**不改 Red Flags/Iron Law**（compile 是管理模块门控动作，agent 侧红线原文不动）。
- [ ] **Step 3:** `pytest tests/test_geological_report_skill.py -q`（SKILL 结构测试若断言 118 行原文需同步更新断言——先跑看哪些红）→ **Step 4: Commit**（`feat(geo-samples): dispatch contract prefers mineral-matched bank slices (Phase 2 T6)`）

---

### Task 7: 模块侧 compile 编排（POST /pipeline/compile + 子进程 + RAGFlow 分发）

**Files:**
- Modify: `backend/app/extensions/geo_samples/service.py`（compile 编排 + RAGFlow push）
- Modify: `backend/app/extensions/geo_samples/crud.py`（list_reviewed；sweep 扩 compile run_type）
- Modify: `backend/app/extensions/geo_samples/routers.py`（POST /pipeline/compile）
- Modify: `backend/app/extensions/geo_samples/schemas.py`（RunOut.run_type 注释 + compile）
- Modify: `frontend/src/extensions/geo-samples/components/TasksView.tsx`（RUN_TYPE_ZH 加 compile编译；DocumentsView 工具行加「编译」按钮，可选）
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加 subprocess 守护与编排测试）

要点（全部有 recon 锚点）：
- `_REPO_ROOT = Path(__file__).resolve().parents[4]`、`_SKILL_DIR = _REPO_ROOT/"skills"/"public"/"geological-report"` + 守护测试 `test_geo_bank_skill_dir_exists`（断言 `(_SKILL_DIR/"scripts"/"bank_compile.py").exists()`，bug-526 模板）
- 子进程模板照抄 contract_price run_pipeline_subprocess，**加超时**：`asyncio.wait_for(proc.communicate(), timeout=1800)` 超时 kill → finish_run("failed","timeout")（recon risk：模板无超时会挂死 run）
- run_type 扩 `"compile"`（document_id=None 模块级）；互斥在 routers 层自实现（`has_running_compile = 任意 compile running 行存在`，crud 加 `has_running_compile_run(db)`）
- 编排两段：①prepare（读 reviewed 清单 + MinIO 下载 clean 到 `tempfile.TemporaryDirectory` 工作区 + 写 manifest.json，全 to_thread）→ ②子进程 bank_compile → ③RAGFlow push（env `GSB_RAGFLOW_DATASET_ID`，未设则跳过并记 detail）→ status=compiled 写回 gsb_documents（按 manifest report_id 批量）
- RAGFlow push 幂等契约：**delete-by-name + upload + parse**——先分页 list_documents（page/limit）建 name→id 映射，同名先 delete_document 再 upload_document(file_path=切片盘上路径) + parse_document；**不用 wait_for_parsing_complete**（>100 文档轮询陷阱，recon risk）——解析状态由人工在 RAGFlow 控制台看
- base_url 双前缀雷：容器内 compose environment 是 `http://ragflow:9380`（不带 /api/v1，client 恒拼 API_PREFIX）——恰好正确；**禁止**改用 .env.docker 形态（带 /api/v1 会变 /api/v1/api/v1）
- [ ] 步骤：失败测试（compile workspace 准备/子进程超时/RAGFlow 跳过路径）→ 实现 → `pytest tests/test_geo_sample_bank_compile.py tests/test_geo_samples_service.py -q` 全绿 → Commit（`feat(geo-samples): compile pipeline orchestration + RAGFlow slice distribution (Phase 2 T7)`）

service.py 追加骨架（常量区加 `import os, sys` 与 `_REPO_ROOT/_SKILL_DIR`；`GSB_RAGFLOW_DATASET_ID = os.environ.get("GSB_RAGFLOW_DATASET_ID", "")`）：

```python
async def run_compile(db: AsyncSession, run_id: str, workdir: Path) -> None:
    """模块级编译：子进程 bank_compile（超时 1800s kill）→ RAGFlow 切片分发 → status=compiled。"""
    refs = _SKILL_DIR / "references"
    cmd = [sys.executable, "-X", "utf8", str(_SKILL_DIR / "scripts" / "bank_compile.py"),
           "--workdir", str(workdir), "--references", str(refs), "--python", sys.executable]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(_SKILL_DIR),
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=1800.0)
        if proc.returncode != 0:
            raise RuntimeError(f"bank_compile rc={proc.returncode}: {err.decode('utf-8', 'replace')[-500:]}")
        manifest = json.loads((workdir / "manifest.json").read_text(encoding="utf-8"))
        pushed = 0
        if GSB_RAGFLOW_DATASET_ID:
            pushed = await push_slices_to_ragflow(refs, manifest)  # delete-by-name + upload + parse，见下
        for e in manifest:  # status→compiled 批量写回
            doc = await crud.get_document_by_report_id(db, e["report_id"])
            if doc:
                doc.status = "compiled"
        await db.commit()
        await _finish_run(db, run_id, "done", f"slices ok; ragflow pushed={pushed}")
    except Exception as exc:  # noqa: BLE001
        log.exception("compile failed (run %s)", run_id)
        await _finish_run(db, run_id, "failed", f"{type(exc).__name__}: {exc}")


async def push_slices_to_ragflow(refs: Path, manifest: list[dict]) -> int:
    """幂等分发：分页 list 建 name→id 映射 → 同名先 delete → upload(盘上切片路径) → parse。"""
    from app.extensions.knowledge.client import RAGFlowClient
    from app.extensions.config import get_extensions_config
    cfg = get_extensions_config().ragflow
    client = RAGFlowClient(base_url=cfg.base_url, api_key=cfg.api_key, timeout=cfg.timeout)
    existing: dict[str, str] = {}
    page = 1
    while True:
        resp = await client.list_documents(GSB_RAGFLOW_DATASET_ID, page=page, limit=100)
        docs = resp.get("data", [])
        if not docs:
            break
        existing.update({d["name"]: d["id"] for d in docs})
        page += 1
    pushed = 0
    for stage, chs in json.loads((refs / "samples_bank" / "bank_index.json").read_text(encoding="utf-8")).items():
        for ch, items in chs.items():
            for it in items:
                path = refs / it["path"]
                name = path.name
                if name in existing:
                    await client.delete_document(GSB_RAGFLOW_DATASET_ID, existing[name])
                up = await client.upload_document(GSB_RAGFLOW_DATASET_ID, str(path), file_name=name)
                doc_id = up["data"]["id"]
                await client.parse_document(GSB_RAGFLOW_DATASET_ID, doc_id)
                pushed += 1
    return pushed
```

（list_documents 分页形参名以 client.py 实物为准核对；upload_document 返回归一化为 `{"data": {…含 id}}`——recon 已证；prepare workspace 函数 `prepare_compile_workspace(db) -> Path`：查 reviewed（stage/mineral 可选过滤）→ 逐份 to_thread 下载 clean 到 `TemporaryDirectory` 下 `<rid>/source.md` → 写 manifest.json。空 reviewed 清单 → finish_run(failed,"no reviewed documents") 不起子进程。）

---

### Task 8: 分块质量验收（升级触发器，spec §9 Phase 2 人评项）

**Files:**
- Create: `scripts/geo_bank_ragflow_acceptance.py`（一次性验收脚本，repo 根 scripts/）

- [ ] **Step 1:** 脚本：读 `references/samples_bank/exploration/slices/` 前 10 片 → 上传到**验收专用 scratch dataset**（env `GSB_RAGFLOW_ACCEPTANCE_DATASET_ID`——绝不打生产固体矿产库）→ 对每片跑 `list_chunks` 断言：①片内 `## N.M` 标题行未被切开（chunk 文本含节号首行）；②md 表格行数与源片一致（v0.25.3 表格重复缺陷检测）；③parent_child 生效抽查（任一子块命中后返回块包含整节）。输出 PASS/FAIL 报告。
- [ ] **Step 2:** 人评 checklist（写入脚本 docstring）：节号完整性/表格完整性/标记行在首块/相邻语义。FAIL 判定 → 触发序：①切片降纯文本+标记行重编译重评 ②仍 FAIL → RAGFlow 镜像升级评估（spec §3.4 触发式升级）。
- [ ] **Step 3:** 跑通并留存报告 → Commit（`test(geo-samples): RAGFlow chunk-quality acceptance harness (Phase 2 T8)`）

---

### Task 9: 端到端演练（2 矿种 ≤6 份全链）+ 运维注记

- [ ] **Step 1:** 合成夹具脚本 `scripts/geo_bank_e2e_fixtures.py`：python-docx 造 4 份报告（金×2、煤×2，含中文「标题 1」样式、`## N` 节号、表格、植入 PII：证号/坐标/电话/负责人）→ 上传（report_id `e2e-gold-001…`）→ 解析→脱敏→抽审 approve 全通过（UI 或 API+cookie 均可，命令写入 docstring）
- [ ] **Step 2:** POST /pipeline/compile → 断言：`references/depth_targets/exploration/gold.json` 与 `coal.json` 生成（median 非 0、含 absolute_floor）；`bank_index.json` 含两组；`samples/exploration/` 下切片 ≥8 份；`gsb_documents.status=compiled` ×4
- [ ] **Step 3:** resolve_targets 实测：fixture `commodity="岩金"` 的项目跑 `progress.py gate` → delivery_manifest.targets.path 指向 gold.json（T4 的探测生效实证）
- [ ] **Step 4:** 运维注记追加 `deploy/offline/MANUAL-UPGRADE.md`：`GSB_MINIO_*`、`OCR_SERVICE_URL`、`GSB_RAGFLOW_DATASET_ID` 三个 env 的生产接线段（终审 R4）
- [ ] **Step 5:** 全量门禁（backend `make lint && make test` 按 Phase 1 T12 归因法；frontend 三闸）+ Commit（`feat(geo-samples): Phase 2 end-to-end drill fixtures + ops env notes (T9)`）

---

## Phase 2 完成判据（验收）

1. 门禁全绿（geo_samples + geo 技能测试套 + 前端三闸；无关失败按 T12 归因法）
2. 2 矿种 × ≤6 份报告：上传→解析→脱敏→过审→compile→`depth_targets/<stage>/<矿种>.json` 三件套生成、bank_index 双组、SL3 池可见扩容（SL3 PASS 行数值计数增长）
3. **resolve_targets 实证**：gold 项目（commodity=岩金）gate 的 manifest 基准指向 gold.json；词表外矿种回退 CANONICAL 不炸
4. RAGFlow 分块质量验收 PASS（或触发降级序并记录）；切片在 knowledge_search 可检索（主题查询命中带标记行）
5. SKILL.md/chapter_craft 消费契约更新且结构测试绿；运维 env 注记入库

## 明确不做（Phase 3+）

ore_pack 批量孵化（LLM 抽取+人审）、缺陷黑名单/standards_index 扩容、count 聚合端点、部分唯一索引（gsb_run_history）、preview PNG 对照。

## 关键风险备忘（实施者必读）

1. **并发硬化漂移**：每个触碰技能文件的任务先 `git log -1 -- <file>` 重锚；本计划行号锚定 2026-09-02 基线（build_output=61d03175d 系 / SKILL.md=838da31c2）
2. **absolute_floor 三处 `.get` 仍为兜底**——本计划只把它落盘进新基线文件，不改 build_output 三处读取；若未来调地板值须同步 compile 输出
3. **SL3 的 ≥100 是数值绝对值阈值**非样例数；samples/<stage>/ 下不要放整本 source.md（会污染指纹池且 calibrate 口径混乱）
4. **RAGFlow 客户端双雷**：.env.docker 形态的 base_url 带 /api/v1 会双拼（容器 compose 值恰好正确，勿改）；wait_for_parsing 在 >100 文档 dataset 会恒超时（V1 不用）
