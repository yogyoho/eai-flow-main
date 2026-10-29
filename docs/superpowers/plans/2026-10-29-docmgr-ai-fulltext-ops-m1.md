# docmgr 右侧 AI 助手全文操作 M1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** docmgr 个人文档右侧 AI 面板新增「预设操作库」任务通道——6 个全文操作（全文润色/全文校对/术语统一/格式规范/生成目录/全文摘要），服务端分节逐节调模型，产出永远是 `DocOperation[]`（新增 `replace_section` 原语），回灌现有 applyOperations / 快照 / 撤销机制。

**Architecture:** 双通道不变——自由对话照走 lead_agent（useStream），本计划完全不动它；确定性任务走新端点 `POST /api/extensions/docmgr/ai/transform`（NDJSON 事件流）。服务端**零读盘**（content 请求体直传）；模型装配走 `create_chat_model`（ai-edit 先例）；前端新增独立任务区（不进 thread 消息流）。

**Tech Stack:** FastAPI StreamingResponse(NDJSON) + `deerflow.models.create_chat_model`；React 19 + rstest + happy-dom；BlockNote editor API。

**Spec:** `docs/superpowers/specs/2026-10-29-docmgr-ai-fulltext-ops-design.md`（commit 1de60def5）§4 + §11。M2（审查 findings）/ M3（diff+翻译）依赖本计划产物，**M1 落地后各出独立计划**，本计划不含。

**约定（全程适用）:**

- 提交到 `main-dev-fork`，不在 main。
- 后端测试：`cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_ai_transform.py -v`；lint：`cd backend && make lint`（改完后跑）。
- 前端测试 **rstest（非 vitest）**：`cd frontend && pnpm test tests/unit/docmgr/<file>`（rstest 以位置参数为过滤路径）；typecheck：`cd frontend && pnpm typecheck`。
- 改后端 Python 后：`docker compose -p eai-docker restart gateway`（必须带 `-p eai-docker`）。
- 前端容器 HMR 可能不生效，必要时 `docker compose -p eai-docker restart frontend`。
- 新增后端文件头部带 EAI-CUSTOM 注释；不改 harness 核心代码。
- 先红后绿：每个任务先写失败测试 → 跑红 → 最小实现 → 跑绿 → commit。

---

## 文件结构

**Create:**

| 文件 | 职责 |
|---|---|
| `backend/app/extensions/docmgr/ai_transform.py` | 分节引擎（纯函数）+ `/ai/transform` NDJSON 端点 + 6 预设 prompt |
| `backend/scripts/docmgr_doc_scale.py` | T0 规模盘点一次性只读脚本（stdlib only） |
| `backend/tests/test_docmgr_ai_transform.py` | 后端全部单测 |
| `frontend/src/extensions/docmgr/DocAITaskArea.tsx` | 任务区：taskReducer 纯函数 + useDocAITask hook + PresetChips/SectionCard 组件 |
| `frontend/tests/unit/docmgr/anchor-ambiguity.test.ts` | 锚点歧义加固回归 |
| `frontend/tests/unit/docmgr/section-range.test.ts` | findSectionRange 节边界 |
| `frontend/tests/unit/docmgr/op-content.test.ts` | applyOperations 数学管线回归 |
| `frontend/tests/unit/docmgr/message-parse-cache.test.ts` | bug-3301 解析缓存回归 |
| `frontend/tests/unit/docmgr/task-reducer.test.ts` | 任务区状态机 |
| `frontend/tests/unit/docmgr/task-area.dom.test.tsx` | SectionCard/PresetChips 渲染 |

**Modify:**

| 文件 | 变更 |
|---|---|
| `backend/app/gateway/app.py` | docmgr 挂载块（:1611-1612 附近）+2 行 |
| `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx` | DocOperation 加 `replace_section`；findBlockByAnchor 加固；新增 findSectionRange / parseOperationContent；applyOperations 管线修复 + replace_section 分支；ref 加 onDocumentChange |
| `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx` | createAIMessageParser 导出 + auto 效果修复（bug-3301）；任务区/预设 chips 接线；busy 锁 |
| `frontend/src/extensions/api/index.ts` | `DocAITransformEvent` 类型 + `aiTransformStream` |

---

### Task 1: T0 规模盘点（只读脚本）

**Files:**
- Create: `backend/scripts/docmgr_doc_scale.py`

- [ ] **Step 1: 写盘点脚本**

```python
# backend/scripts/docmgr_doc_scale.py
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
```

- [ ] **Step 2: 在容器内找 .deer-flow 根并运行**

```bash
docker compose -p eai-docker exec gateway sh -c "find / -maxdepth 5 -type d -name '.deer-flow' 2>/dev/null | head -3"
# 假设输出 /app/backend/.deer-flow —— 以下命令按实际输出替换
docker compose -p eai-docker exec gateway sh -c "cd /app/backend && python scripts/docmgr_doc_scale.py --root /app/backend/.deer-flow/users"
```

- [ ] **Step 3: 回填阈值**

把输出记入本文件末尾「T0 盘点记录」。校准规则：
- section p99 < 4000 → 保持 `SECTION_CHAR_LIMIT = 4000`；否则调大到 p99。
- 单文档节数 max < 200 → 保持 `MAX_SECTIONS = 200`。
- 文档 chars p99 < 400k → 保持 `MAX_CONTENT_CHARS = 400_000`。
- 把三个常量终值写进 Task 2 的 `ai_transform.py`（下方代码中的值即为初值）。

spec §11-2 round-trip 对应性的另一半（BlockNote `tryParseMarkdownToBlocks` 块序列对应）：rstest node 环境无真实编辑器实例，不建 harness——由 Task 7 的 fake-tryParse 管线测试 + Task 14 walkthrough 在真实 2 万字文档上覆盖（ponytail：整编辑器 round-trip 测试架不值得，走查兜底）。

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/docmgr_doc_scale.py
git commit -m "chore(docmgr): T0 规模盘点脚本(outputs md 节数/节长分布,只读)"
```

---

### Task 2: T0 max_tokens 核实（已完成，记录在案）

**核实结论（本计划撰写时已完成，无需再查）**：`deerflow.models.create_chat_model`（`backend/packages/harness/deerflow/models/factory.py:526`）签名含 `model_overrides: dict | None`；`factory.py:575-576` 将 overrides 合并到模型 profile 之上、`None` 值忽略。因此**显式下发 max_tokens 的方式 = `create_chat_model(name=..., thinking_enabled=False, model_overrides={"max_tokens": 8192})`**。Codex 端点会自行丢弃 max_tokens（factory.py:649-650 既有归一化），无需我们处理。

- [ ] **Step 1: 无代码。** 确认 Task 3 代码里用的是 `model_overrides={"max_tokens": 8192}`。

---

### Task 3: 后端分节引擎（TDD）

**Files:**
- Create: `backend/app/extensions/docmgr/ai_transform.py`
- Create: `backend/tests/test_docmgr_ai_transform.py`

- [ ] **Step 1: 写失败测试**（`backend/tests/test_docmgr_ai_transform.py`）

```python
"""docmgr ai_transform（全文操作 M1）单测——分节引擎纯函数 + transform 端点 NDJSON 事件流。

EAI-CUSTOM: 端点测试沿 test_bid_review_routers.py 先例——独立 FastAPI 子 app +
dependency_overrides 打桩权限依赖；模型注入 monkeypatch ai_transform.create_chat_model。
"""

import json

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.extensions.docmgr import ai_transform as AT


# ── 分节引擎 ──────────────────────────────────────────────────────────


class TestSplitSections:
    def test_lossless_join(self):
        doc = "# A\n\n内容一\n\n## B\n\n内容二\n"
        secs = AT.split_sections(doc)
        assert "".join(s["content"] for s in secs) == doc

    def test_heading_levels_and_titles(self):
        secs = AT.split_sections("# T\n\nintro\n\n## S1\n\na\n\n### SS\n\nb\n\n## S2\n\nc\n")
        assert [(s["title"], s["level"]) for s in secs] == [
            ("T", 1), ("S1", 2), ("SS", 3), ("S2", 2),
        ]

    def test_no_heading_single_section(self):
        secs = AT.split_sections("正文没有标题\n第二行\n")
        assert len(secs) == 1 and secs[0]["title"] == "" and secs[0]["level"] is None

    def test_empty_doc(self):
        assert AT.split_sections("") == []
        assert AT.split_sections("   \n  ") == []

    def test_lead_whitespace_merged_into_first_section(self):
        doc = "\n\n# A\n\nx\n"
        secs = AT.split_sections(doc)
        assert len(secs) == 1
        assert "".join(s["content"] for s in secs) == doc

    def test_long_section_resplit_pieces_lossless(self):
        body = "段落内容，用于填充长度。\n\n```python\nx = 1\n\ny = 2\n```\n\n尾段。\n\n"
        doc = "# H\n\n" + body * 120  # ≈5.7k 字符，确保触发 >4000 再切
        secs = AT.split_sections(doc)
        assert len(secs) == 1
        pieces = secs[0]["pieces"]
        assert len(pieces) > 1
        assert "".join(pieces) == secs[0]["content"]
        for p in pieces:
            # 围栏不拦腰截断：``` 计数必为偶数
            assert p.count("```") % 2 == 0

    def test_math_block_atomic(self):
        body = "前文。\n\n$$\nE = mc^2\n\n+ c\n$$\n\n后文。\n\n"
        doc = "# H\n\n" + body * 60
        secs = AT.split_sections(doc)
        for piece in secs[0]["pieces"]:
            assert piece.count("$$") % 2 == 0  # $$ 成对，区间未被腰斩

    def test_table_atomic(self):
        # 两张 ~2.8k 的表 + 段落 ≈ 5.7k：触发再切，但每段表 <4000 不落硬切
        row = "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        doc = "# H\n\n" + row * 100 + "分隔段落文字。\n\n" + row * 100
        secs = AT.split_sections(doc)
        assert len(secs) == 1
        assert len(secs[0]["pieces"]) > 1  # 确实触发了再切
        for piece in secs[0]["pieces"]:
            lines = [ln for ln in piece.split("\n") if ln.strip().startswith("|")]
            # 表行按 3 行一段的原子段整体进出 → 数量必为 3 的倍数或 0，不出孤行
            assert len(lines) % 3 == 0

    def test_hard_cut_lossless(self):
        seg = "这是一句话。" * 2000
        pieces = AT._hard_cut(seg, 4000)
        assert "".join(pieces) == seg
        assert all(len(p) <= 4001 for p in pieces)

    def test_structured_detection(self):
        assert AT._is_structured("文字\n\n$$\nx\n$$\n") is True
        assert AT._is_structured("| a | b |\n|---|---|\n| 1 | 2 |") is True
        assert AT._is_structured("<details><summary>s</summary>x</details>") is True
        assert AT._is_structured("![图](a.png)") is True
        assert AT._is_structured("纯文本一段。\n\n```python\ncode\n```\n") is False


# ── 端点（fake model 注入） ───────────────────────────────────────────


class _FakeResp:
    def __init__(self, content):
        self.content = content


class FakeModel:
    """按序返回预设响应；raise_on=N 时第 N 次调用抛异常（1-based）。"""

    def __init__(self, replies, raise_on=None):
        self.replies = list(replies)
        self.raise_on = raise_on
        self.prompts: list[str] = []
        self.calls = 0

    async def ainvoke(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        if self.raise_on is not None and self.calls == self.raise_on:
            raise RuntimeError("boom")
        return _FakeResp(self.replies.pop(0) if self.replies else "兜底响应")


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(AT.router)
    app.dependency_overrides[AT._doc_perm] = lambda: type("U", (), {"id": "u1"})()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _events(client, payload) -> list[dict]:
    events = []
    async with client.stream("POST", "/api/extensions/docmgr/ai/transform", json=payload) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.strip():
                events.append(json.loads(line))
    return events


DOC2 = "# 一\n\n甲内容。\n\n## 二\n\n乙内容。\n"


class TestTransformEndpoint:
    @pytest.mark.asyncio
    async def test_two_sections_happy_path(self, client, monkeypatch):
        fake = FakeModel(["甲改写。", "乙改写。"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r.md", "operation": "polish", "content": DOC2})
        assert [e["type"] for e in events] == ["section_start", "ops", "section_start", "ops", "done"]
        assert events[1]["ops"] == [{"op": "replace_section", "anchor": "一", "content": "甲改写。"}]
        assert events[3]["ops"] == [{"op": "replace_section", "anchor": "二", "content": "乙改写。"}]
        assert events[-1] == {"type": "done", "total": 2, "failed": [], "skipped": []}

    @pytest.mark.asyncio
    async def test_max_tokens_override_passed(self, client, monkeypatch):
        captured = {}
        fake = FakeModel(["改写。"])
        def _fake_factory(name=None, thinking_enabled=False, model_overrides=None, **kw):
            captured["overrides"] = model_overrides
            return fake
        monkeypatch.setattr(AT, "create_chat_model", _fake_factory)
        await _events(client, {"thread_id": "t", "rel_path": "r.md", "operation": "polish", "content": "# A\n\nx\n"})
        assert captured["overrides"] == {"max_tokens": 8192}

    @pytest.mark.asyncio
    async def test_structured_section_skipped(self, client, monkeypatch):
        fake = FakeModel(["改写。"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        doc = "# 一\n\n纯文字。\n\n## 二\n\n$$\nE\n$$\n"
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "polish", "content": doc})
        assert events[2] == {"type": "section_start", "index": 1, "total": 2, "title": "二", "skipped": True}
        assert events[-1]["skipped"] == [1] and fake.calls == 1

    @pytest.mark.asyncio
    async def test_section_error_continues(self, client, monkeypatch):
        fake = FakeModel(["乙改写。"], raise_on=1)
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "polish", "content": DOC2})
        kinds = [e["type"] for e in events]
        assert kinds == ["section_start", "section_error", "section_start", "ops", "done"]
        assert events[1]["index"] == 0 and "失败" in events[1]["message"]
        assert events[-1]["failed"] == [0]

    @pytest.mark.asyncio
    async def test_unchanged_section_empty_ops(self, client, monkeypatch):
        # 第一节响应须含标题与原文全同（含尾随空行）才判 unchanged
        fake = FakeModel(["# 一\n\n甲内容。\n\n", "乙改写。"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "polish", "content": DOC2})
        assert events[1]["ops"] == []  # 与原文一致 → 空批次，前端标「无变更」
        assert events[3]["ops"] != []

    @pytest.mark.asyncio
    async def test_partial_rerun(self, client, monkeypatch):
        fake = FakeModel(["乙改写。"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "polish", "content": DOC2, "sections": [1]})
        assert [e["type"] for e in events] == ["section_start", "ops", "done"]
        assert events[0]["index"] == 1 and events[-1]["total"] == 1

    @pytest.mark.asyncio
    async def test_unknown_operation_400(self, client):
        r = await client.post("/api/extensions/docmgr/ai/transform", json={"thread_id": "t", "rel_path": "r", "operation": "bogus", "content": "x"})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_titleless_doc_section_error(self, client, monkeypatch):
        fake = FakeModel(["改写。"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "polish", "content": "无标题全文。"})
        assert any(e["type"] == "section_error" and "标题" in e["message"] for e in events)

    @pytest.mark.asyncio
    async def test_toc_no_model_call(self, client, monkeypatch):
        fake = FakeModel([])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "toc", "content": DOC2})
        assert events[0]["type"] == "section_start"
        ops = events[1]["ops"]
        assert ops == [{"op": "prepend", "content": ops[0]["content"]}]  # 形状
        assert "## 目录" in ops[0]["content"] and "- 一" in ops[0]["content"] and "  - 二" in ops[0]["content"]
        assert fake.calls == 0  # 纯机械，不调模型

    @pytest.mark.asyncio
    async def test_toc_no_headings_message(self, client, monkeypatch):
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: FakeModel([]))
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "toc", "content": "没有任何标题"})
        assert events[-1]["type"] == "done" and events[-1]["message"] and "标题" in events[-1]["message"]

    @pytest.mark.asyncio
    async def test_terminology_two_pass(self, client, monkeypatch):
        scan = json.dumps([{"canonical": "供水系统", "variants": ["给水系统"]}], ensure_ascii=False)
        fake = FakeModel([scan, "统一后甲。", "统一后乙。"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "terminology", "content": DOC2})
        assert "术语审校" in fake.prompts[0]  # 第一遍全文扫描
        assert "供水系统" in fake.prompts[1]  # 第二遍携术语表
        assert events[1]["ops"][0]["op"] == "replace_section"

    @pytest.mark.asyncio
    async def test_summary_map_reduce(self, client, monkeypatch):
        fake = FakeModel(["甲要点。", "乙要点。", "## 全文摘要\n\n整合摘要。"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "summary", "content": DOC2})
        types = [e["type"] for e in events]
        assert "summary" in types
        summary_ev = next(e for e in events if e["type"] == "summary")
        assert "整合摘要" in summary_ev["content"]
        assert all(e["type"] != "ops" for e in events)  # 摘要不直接产 ops
        assert fake.calls == 3  # 两节 map + 一次 reduce
```

- [ ] **Step 2: 跑红**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_ai_transform.py -v
```

预期：collection error `ModuleNotFoundError: No module named 'app.extensions.docmgr.ai_transform'`。

- [ ] **Step 3: 写实现**（`backend/app/extensions/docmgr/ai_transform.py`）

```python
"""EAI-CUSTOM: docmgr 全文操作 M1（spec: docs/superpowers/specs/2026-10-29-docmgr-ai-fulltext-ops-design.md §4）。

- 服务端零读盘：content 请求体直传，thread_id/rel_path 仅审计日志用（无越权读通道、无 PUT-read 竞态）。
- 模型装配走 create_chat_model（同 routers.py ai-edit 先例），max_tokens 显式 8192 防 provider 默认 4096 截断。
- 产出永远是 DocOperation[]（新增 replace_section）；分节引擎为确定性纯函数，同 content 必得同边界。
- 升级注意：collab_ai_chat.py 的裸 httpx 装配是反面教材（无 override / 无 max_tokens / 错误静默），勿回抄。
"""

import asyncio
import json
import logging
import re
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.extensions.auth.middleware import CurrentUser, require_permission
from app.extensions.docmgr.routers import _extract_ai_response_text
from deerflow.models import create_chat_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/docmgr", tags=["docmgr-ai"])  # EAI-CUSTOM: 独立模块 router，gateway app.py 挂载区注册
_doc_perm = require_permission("doc:upload")  # EAI-CUSTOM: 模块级命名依赖（同 ai-edit 的 doc:upload 门），测试可 dependency_overrides

SECTION_CHAR_LIMIT = 4000  # T0 盘点校准（Task 1），初值按 spec §4.2
MAX_SECTIONS = 200
MAX_CONTENT_CHARS = 400_000
SECTION_TIMEOUT_SECONDS = 120
SUMMARY_TIMEOUT_SECONDS = 180

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


# ── 分节引擎（纯函数） ────────────────────────────────────────────────


def _is_structured(text: str) -> bool:
    """节内含公式($$)/表格/图片/折叠块 → v1 整节跳过（不做块级穿引，spec §8）。"""
    if "$$" in text:
        return True
    if re.search(r"^!\[.*\]\(.*\)", text, re.M):
        return True
    if "<details" in text.lower():
        return True
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            return True
    return False


def _segments(text: str) -> list[str]:
    """节文本 → 最小不可切单元序列（代码围栏 / $$..$$ / 表格 / <details> / 空行分段）。

    依序拼接 == text（无损；分隔空行挂段尾）。
    """
    lines = text.split("\n")
    segs: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            segs.append("\n".join(buf))
            buf.clear()

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush()
            j = i + 1
            while j < n and not lines[j].strip().startswith("```"):
                j += 1
            j = min(j + 1, n)
            segs.append("\n".join(lines[i:j]))
            i = j
            continue
        if s.startswith("$$"):
            flush()
            j = i + 1
            while j < n and "$$" not in lines[j] and not s.endswith("$$"):
                j += 1
            j = min(j + 1, n) if not s.endswith("$$") else i + 1
            segs.append("\n".join(lines[i:j]))
            i = j
            continue
        if s.lower().startswith("<details"):
            flush()
            j = i + 1
            while j < n and "</details>" not in lines[j].lower():
                j += 1
            j = min(j + 1, n)
            segs.append("\n".join(lines[i:j]))
            i = j
            continue
        if s.startswith("|"):
            flush()
            j = i
            while j < n and lines[j].strip().startswith("|"):
                j += 1
            segs.append("\n".join(lines[i:j]))
            i = j
            continue
        if not s:
            if buf:
                buf.append(line)
                flush()
            else:
                segs.append(line)
            i += 1
            continue
        buf.append(line)
        i += 1
    flush()
    return segs


_SENTENCE_END_RE = re.compile(r"[。．.!?！？；;\n]")


def _hard_cut(text: str, limit: int) -> list[str]:
    """单原子段仍超限 → 句号边界硬切（保底不丢字；依序拼接 == text）。"""
    out: list[str] = []
    start, n = 0, len(text)
    while n - start > limit:
        bound = start + limit
        last_end = -1
        for m in _SENTENCE_END_RE.finditer(text, start, bound + 1):
            last_end = m.end()
        cut = last_end if last_end > start else bound
        out.append(text[start:cut])
        start = cut
    if start < n:
        out.append(text[start:])
    return out or [text]


def _split_long(text: str, limit: int = SECTION_CHAR_LIMIT) -> list[str]:
    """超长节按原子段聚合再切；依序拼接 == text。"""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for seg in _segments(text):
        if len(seg) > limit:
            if cur:
                chunks.append("".join(cur))
                cur, size = [], 0
            chunks.extend(_hard_cut(seg, limit))
            continue
        if size + len(seg) > limit and cur:
            chunks.append("".join(cur))
            cur, size = [], 0
        cur.append(seg)
        size += len(seg)
    if cur:
        chunks.append("".join(cur))
    return chunks


def split_sections(content: str) -> list[dict]:
    """按 ATX 标题切节（确定性纯函数）。

    返回 [{"title", "level", "content", "structured", "pieces"}]；无标题文档 = 单节
    （title=""）；空文档 = []；各节 content 依序拼接 == 原文（无损划分）。
    """
    if not content.strip():
        return []
    raw: list[tuple[str, int | None, list[str]]] = []
    cur_title: str = ""
    cur_level: int | None = None
    buf: list[str] = []
    for line in content.split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            if buf:
                raw.append((cur_title, cur_level, buf))
            cur_title, cur_level, buf = m.group(2).strip(), len(m.group(1)), [line]
        else:
            buf.append(line)
    if buf:
        raw.append((cur_title, cur_level, buf))

    sections: list[dict] = []
    lead = ""
    for title, level, ls in raw:
        text = "\n".join(ls)
        if not text.strip():
            if sections:
                sections[-1]["content"] += text  # 空白块并入前节，保持无损
            else:
                lead += text
            continue
        if lead:
            text = lead + text
            lead = ""
        structured = _is_structured(text)
        sections.append({
            "title": title,
            "level": level,
            "content": text,
            "structured": structured,
            "pieces": [text] if (structured or len(text) <= SECTION_CHAR_LIMIT) else _split_long(text),
        })
    if lead and sections:
        sections[-1]["content"] += lead
    return sections


# ── 预设 prompt ───────────────────────────────────────────────────────

_REWRITE_PRESETS: dict[str, dict] = {
    "polish": {"rules": "任务=全文润色：使语句更流畅、专业，不改变原意，不增删信息。"},
    "proofread": {"rules": "任务=全文校对：仅修正错别字、标点误用、单位符号格式；没有错误的原句原样保留，禁止改写措辞。"},
    "format": {"rules": "任务=格式规范：修正标题层级跳级、序号不连续、中英文之间缺空格；不改动句子措辞与内容。"},
    "terminology": {"rules": "任务=术语统一：按术语表把变体术语替换为标准术语，其余内容一字不改。"},
}

_REWRITE_PROMPT = """你是文档编辑器中的全文处理助手。下面是一篇文档中的一节，请对这一节执行指定任务。

**任务**：{rules}

**硬性约束**：
1. 只输出处理后的这一节 markdown 正文；不要任何解释、前言、结语，也不要用 ```markdown 围栏包裹全文
2. 保持标题层级、列表/引用结构、加粗斜体不变；代码块内容一字不改
3. 保留所有数字、单位、公式、图表引用标号不变
4. 输出语言与原文一致
{terminology_block}
**本节内容**：
{section}"""

_TERMINOLOGY_SCAN_PROMPT = """你是术语审校助手。扫描下方文档全文，找出「同一概念使用了多个不同名称」的术语变体组（例如「给水系统」与「供水系统」混用）。

只输出 JSON 数组，格式：[{{"canonical": "应统一采用的标准术语", "variants": ["变体1", "变体2"]}}]
没有发现任何变体时输出 []。不要输出解释。

**文档全文**：
{doc}"""

_SUMMARY_MAP_PROMPT = """你是摘要助手。请用 3-5 句话概括以下文档片段的要点，保留关键数据。只输出概括文本。

**片段**：
{section}"""

_SUMMARY_REDUCE_PROMPT = """你是摘要助手。以下是一篇长文档各部分的要点概括，请整合成一篇 200-400 字的全文摘要，保留关键数据与结论。只输出摘要正文（可含一个「## 全文摘要」标题）。

**各部分要点**：
{digest}"""

_ALL_OPERATIONS = set(_REWRITE_PRESETS) | {"toc", "summary"}


# ── 工具 ──────────────────────────────────────────────────────────────


def _ndjson(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", t)


def _strip_markdown_fence(text: str) -> str:
    """仅剥 ```markdown 包裹（模型无视约束时的兜底）；正文自身以代码围栏开头则不动。"""
    t = text.strip()
    if t.startswith("```markdown"):
        body = t[t.find("\n") + 1 :] if "\n" in t[:20] else t[len("```markdown"):]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: body.rstrip().rfind("```")]
        return body.strip("\n")
    return text.strip("\n")


def _build_toc(content: str) -> str | None:
    """纯机械生成目录（不调模型）：扫 ATX 标题产缩进列表；无标题返回 None。"""
    items: list[tuple[int, str]] = []
    for line in content.split("\n"):
        m = _HEADING_RE.match(line)
        if m and m.group(2).strip():
            items.append((len(m.group(1)), m.group(2).strip()))
    if not items:
        return None
    lines = ["## 目录", ""]
    for level, title in items:
        if title == "目录":
            continue
        lines.append(f"{'  ' * (level - 1)}- {title}")
    return "\n".join(lines) + "\n"


async def _scan_terminology(model, doc: str) -> list[dict]:
    """术语统一第一遍：全文扫变体，返回 [{canonical, variants}]；解析失败按无变体处理。"""
    resp = await model.ainvoke(_TERMINOLOGY_SCAN_PROMPT.format(doc=doc))
    m = re.search(r"\[[\s\S]*\]", _extract_ai_response_text(resp.content))
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[dict] = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and isinstance(item.get("canonical"), str) and isinstance(item.get("variants"), list):
            variants = [v for v in item["variants"] if isinstance(v, str) and v and v != item["canonical"]]
            if variants:
                out.append({"canonical": item["canonical"], "variants": variants})
    return out


def _terminology_block(table: list[dict]) -> str:
    if not table:
        return ""
    rows = "\n".join(f"- 「{t['canonical']}」 ← {'、'.join('「' + v + '」' for v in t['variants'])}" for t in table)
    return f"\n**术语表（必须执行替换）**：\n{rows}\n"


async def _rewrite_section(model, operation: str, section: dict, terminology_block: str) -> str:
    """单节改写：超长节分片逐片调模型，输出按片序拼接。"""
    preset = _REWRITE_PRESETS[operation]
    outs: list[str] = []
    for piece in section["pieces"]:
        prompt = _REWRITE_PROMPT.format(rules=preset["rules"], terminology_block=terminology_block, section=piece)
        resp = await asyncio.wait_for(model.ainvoke(prompt), timeout=SECTION_TIMEOUT_SECONDS)
        outs.append(_strip_markdown_fence(_extract_ai_response_text(resp.content)))
    return "\n\n".join(outs)


# ── 端点 ──────────────────────────────────────────────────────────────


class AITransformRequest(BaseModel):
    thread_id: str = Field(..., description="仅审计日志；服务端零读盘")
    rel_path: str = Field(..., description="仅审计日志；服务端零读盘")
    operation: str = Field(..., description="polish | proofread | terminology | format | toc | summary")
    content: str = Field(..., min_length=1, description="面板当前全文 markdown（请求体直传）")
    model_name: str | None = Field(None, description="模型覆盖，缺省走 Settings 默认")
    sections: list[int] | None = Field(None, description="全量切分后的节下标，部分重跑")


@router.post("/ai/transform")
async def ai_transform(
    request: AITransformRequest,
    current_user: CurrentUser = Depends(_doc_perm),  # EAI-CUSTOM: 权限门同 ai-edit 先例
):
    if request.operation not in _ALL_OPERATIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown operation: {request.operation}. Must be one of: {sorted(_ALL_OPERATIONS)}")
    if len(request.content) > MAX_CONTENT_CHARS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"文档过长（>{MAX_CONTENT_CHARS} 字符），请分段处理")
    model = create_chat_model(name=request.model_name, thinking_enabled=False, model_overrides={"max_tokens": 8192})
    sections = split_sections(request.content)
    if len(sections) > MAX_SECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"分节数超过上限 {MAX_SECTIONS}，请分段处理")
    chosen = list(range(len(sections))) if request.sections is None else sorted({i for i in request.sections if 0 <= i < len(sections)})
    logger.info(
        "docmgr ai_transform user=%s op=%s thread=%s rel=%s sections=%d/%d chars=%d",
        getattr(current_user, "id", "?"), request.operation, request.thread_id, request.rel_path, len(chosen), len(sections), len(request.content),
    )

    async def generate() -> AsyncIterator[str]:
        failed: list[int] = []
        skipped: list[int] = []
        message: str | None = None

        if request.operation == "toc":
            toc_md = _build_toc(request.content)
            if toc_md is None:
                message = "文档没有标题，无法生成目录"
            else:
                yield _ndjson({"type": "section_start", "index": 0, "total": 1, "title": "目录"})
                yield _ndjson({"type": "ops", "index": 0, "ops": [{"op": "prepend", "content": toc_md}]})
            done: dict = {"type": "done", "total": 0 if toc_md is None else 1, "failed": [], "skipped": []}
            if message:
                done["message"] = message
            yield _ndjson(done)
            return

        if request.operation == "summary":
            digest: list[str] = []
            for i, sec in enumerate(sections):
                if sec["structured"]:
                    skipped.append(i)
                    continue
                yield _ndjson({"type": "section_start", "index": i, "total": len(sections), "title": sec["title"] or f"第 {i + 1} 节"})
                try:
                    resp = await asyncio.wait_for(model.ainvoke(_SUMMARY_MAP_PROMPT.format(section=sec["content"])), timeout=SECTION_TIMEOUT_SECONDS)
                    digest.append(_extract_ai_response_text(resp.content).strip())
                except Exception as e:
                    failed.append(i)
                    logger.warning("docmgr summary map section %s failed: %s", i, e)
                    yield _ndjson({"type": "section_error", "index": i, "message": "本节概括失败，已跳过"})
            if digest:
                try:
                    resp = await asyncio.wait_for(model.ainvoke(_SUMMARY_REDUCE_PROMPT.format(digest="\n\n".join(digest))), timeout=SUMMARY_TIMEOUT_SECONDS)
                    yield _ndjson({"type": "summary", "content": _extract_ai_response_text(resp.content).strip()})
                except Exception as e:
                    logger.warning("docmgr summary reduce failed: %s", e)
                    message = "摘要整合失败，请重试"
            done = {"type": "done", "total": len(sections), "failed": failed, "skipped": skipped}
            if message:
                done["message"] = message
            yield _ndjson(done)
            return

        # 逐节改写预设（polish / proofread / terminology / format）
        terminology_block = ""
        if request.operation == "terminology":
            terminology_block = _terminology_block(await _scan_terminology(model, request.content))
        for i in chosen:
            sec = sections[i]
            start_ev: dict = {"type": "section_start", "index": i, "total": len(chosen), "title": sec["title"] or f"第 {i + 1} 节"}
            if sec["structured"]:
                start_ev["skipped"] = True
                skipped.append(i)
                yield _ndjson(start_ev)
                continue
            yield _ndjson(start_ev)
            if not sec["title"]:
                failed.append(i)
                yield _ndjson({"type": "section_error", "index": i, "message": "文档无标题（全文单节），无法按节定位；请先给文档加标题，或改用对话模式"})
                continue
            try:
                new_md = await _rewrite_section(model, request.operation, sec, terminology_block)
            except Exception as e:
                failed.append(i)
                logger.warning("docmgr ai_transform section %s failed: %s", i, e)
                yield _ndjson({"type": "section_error", "index": i, "message": "本节处理失败，可稍后单独重试本节"})
                continue
            if _norm(new_md) == _norm(sec["content"]):
                yield _ndjson({"type": "ops", "index": i, "ops": []})
                continue
            yield _ndjson({"type": "ops", "index": i, "ops": [{"op": "replace_section", "anchor": sec["title"], "content": new_md}]})
        done = {"type": "done", "total": len(chosen), "failed": failed, "skipped": skipped}
        if message:
            done["message"] = message
        yield _ndjson(done)

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

注意：`from deerflow.models import create_chat_model` 是模块级导入（测试 monkeypatch `AT.create_chat_model` 才生效）；`_extract_ai_response_text` 从同包 `routers.py` 复用（私有名包内复用，勿复制）。

- [ ] **Step 4: 跑绿**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_ai_transform.py -v
```

预期：全 PASS。若有失败：先核对 `_segments` 中 `$$` 分支的单行 `$$..$$`（`s.endswith("$$")` 时 `j = i + 1`）与测试断言是否一致，修实现不改测试语义。

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/docmgr/ai_transform.py backend/tests/test_docmgr_ai_transform.py
git commit -m "feat(docmgr): ai_transform 分节引擎+NDJSON 端点+6 预设(fake-model 单测先红后绿)"
```

---

### Task 4: gateway 注册 + lint + 容器 smoke

**Files:**
- Modify: `backend/app/gateway/app.py`（docmgr 挂载块，:1611-1612 附近）

- [ ] **Step 1: 注册 router**

在 `app.py` :37（`from app.extensions.docmgr.routers import router as docmgr_router` 之后）加：

```python
from app.extensions.docmgr.ai_transform import router as docmgr_ai_router  # EAI-CUSTOM: docmgr 全文操作(预设操作库) M1
```

在 :1612 `app.include_router(docmgr_router)` 之后加：

```python
    # Doc Mgr AI 全文操作（预设操作库，NDJSON 事件流）— /api/extensions/docmgr/ai/transform
    app.include_router(docmgr_ai_router)  # EAI-CUSTOM
```

- [ ] **Step 2: lint**

```bash
cd backend && make lint
```

预期：0 错（若 I001 排序报错按 ruff --fix 修）。

- [ ] **Step 3: 容器内 smoke**

```bash
docker compose -p eai-docker restart gateway
docker compose -p eai-docker exec gateway python -c "from app.extensions.docmgr.ai_transform import router; print([r.path for r in router.routes])"
```

预期输出：`['/ai/transform']`（prefix 单独携带）。再用浏览器登录态（:2026，admin@eai-flow.com）开任一个人文档 → 右侧 AI 面板 → DevTools Network 手动 POST（或留待 Task 13 前端接通后一并验证）。确认 401/403/404 之外的 422（缺 body 字段）即路由已通。

- [ ] **Step 4: Commit**

```bash
git add backend/app/gateway/app.py
git commit -m "feat(docmgr): gateway 挂载 ai_transform router(EAI-CUSTOM,docmgr 挂载块)"
```

---

### Task 5: 前端锚点歧义加固（bug 修复，TDD）

**Files:**
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx:197-213`
- Create: `frontend/tests/unit/docmgr/anchor-ambiguity.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// frontend/tests/unit/docmgr/anchor-ambiguity.test.ts
import { describe, expect, test } from "@rstest/core";

import { findBlockByAnchor } from "@/extensions/docmgr/PersonalBlockNoteEditor";

const heading = (id: string, text: string, level = 2) => ({
  id,
  type: "heading",
  props: { level },
  content: [{ type: "text", text }],
});
const para = (id: string, text: string) => ({
  id,
  type: "paragraph",
  content: [{ type: "text", text }],
});

describe("findBlockByAnchor 歧义加固（重复标题静默错配→安全失败）", () => {
  const doc = [
    heading("h1", "概述", 1),
    para("p1", "正文一"),
    heading("h2", "概述", 2),
    para("p2", "正文二"),
  ];

  test("exact 重复标题 → null", () => {
    expect(findBlockByAnchor(doc, "概述")).toBeNull();
  });

  test("prefix 重复前缀 → null", () => {
    expect(findBlockByAnchor(doc, "概")).toBeNull();
  });

  test("唯一标题正常命中", () => {
    const doc2 = [heading("h1", "概述", 1), para("p1", "正文")];
    expect(findBlockByAnchor(doc2, "概述")?.blockId).toBe("h1");
  });

  test("不同标题各自唯一仍命中", () => {
    expect(findBlockByAnchor(doc, "正文一")?.blockId).toBe("p1");
  });
});
```

- [ ] **Step 2: 跑红**

```bash
cd frontend && pnpm test tests/unit/docmgr/anchor-ambiguity.test.ts
```

预期：前两个 FAIL（现实现首中即返回，返回了 h1/p1）。

- [ ] **Step 3: 加固实现**（`PersonalBlockNoteEditor.tsx` 第 1、2 级匹配改扫全量）

替换 `findBlockByAnchor` 内 :196-213 的两级循环为：

```ts
  // 1. Exact match（normalized）— 扫全量，>1 命中视为歧义（加固：重复标题
  //    首中即返回会静默错配到第一个同名节；与 contains 级 null 纪律对齐）
  let exact: { blockId: string; blockIndex: number } | null = null;
  for (let i = 0; i < doc.length; i++) {
    const block = doc[i];
    if (!block) continue;
    const fullText = normalizeAnchorText(getBlockText(block));
    if (!fullText) continue;
    if (fullText === trimmed) {
      if (exact) return null; // ambiguous
      exact = { blockId: block.id, blockIndex: i };
    }
  }
  if (exact) return exact;

  // 2. Prefix match（normalized）— 同上加固
  let prefix: { blockId: string; blockIndex: number } | null = null;
  for (let i = 0; i < doc.length; i++) {
    const block = doc[i];
    if (!block) continue;
    const fullText = normalizeAnchorText(getBlockText(block));
    if (!fullText) continue;
    if (fullText.startsWith(trimmed)) {
      if (prefix) return null; // ambiguous
      prefix = { blockId: block.id, blockIndex: i };
    }
  }
  if (prefix) return prefix;
```

- [ ] **Step 4: 跑绿 + 既有回归**

```bash
cd frontend && pnpm test tests/unit/docmgr/anchor-ambiguity.test.ts && pnpm test tests/unit/docmgr/ai-panel.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx frontend/tests/unit/docmgr/anchor-ambiguity.test.ts
git commit -m "fix(docmgr): findBlockByAnchor exact/prefix 歧义加固——重复标题返回 null 弃静默错配(bug-3301 同源安全网)"
```

---

### Task 6: replace_section 原语 + 节边界（TDD）

**Files:**
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx`（:94-98 DocOperation、applyOperations :650-689）
- Create: `frontend/tests/unit/docmgr/section-range.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// frontend/tests/unit/docmgr/section-range.test.ts
import { describe, expect, test } from "@rstest/core";

import { findSectionRange } from "@/extensions/docmgr/PersonalBlockNoteEditor";

const h = (id: string, text: string, level: number) => ({
  id,
  type: "heading",
  props: { level },
  content: [{ type: "text", text }],
});
const p = (id: string, text: string) => ({
  id,
  type: "paragraph",
  content: [{ type: "text", text }],
});

describe("findSectionRange（replace_section 节边界）", () => {
  const doc = [
    h("a", "一", 1),
    p("a1", "甲"),
    h("b", "二", 2),
    p("b1", "乙"),
    p("b2", "丙"),
    h("c", "三", 2),
    p("c1", "丁"),
    h("d", "四", 1),
    p("d1", "戊"),
  ];

  test("同级标题截断", () => {
    expect(findSectionRange(doc, 2)).toEqual({
      blockIds: ["b", "b1", "b2"],
      startIndex: 2,
      endIndex: 4,
    });
  });

  test("低级标题不截断高级节", () => {
    // 「一」(level 1) 的节吃到 level 2 的「二」之前
    expect(findSectionRange(doc, 0)).toEqual({
      blockIds: ["a", "a1"],
      startIndex: 0,
      endIndex: 1,
    });
  });

  test("文末无边界 → 扫到底", () => {
    expect(findSectionRange(doc, 7)?.blockIds).toEqual(["d", "d1"]);
  });

  test("锚点非标题 → null", () => {
    expect(findSectionRange(doc, 1)).toBeNull();
    expect(findSectionRange(doc, 99)).toBeNull();
  });
});
```

- [ ] **Step 2: 跑红**（`pnpm test tests/unit/docmgr/section-range.test.ts` → export 不存在 FAIL）

- [ ] **Step 3: 实现**

3a. `DocOperation` union 扩展（:94-98）：

```ts
export interface DocOperation {
  op:
    | "replace"
    | "replace_section" // EAI-CUSTOM (全文操作 M1): 按标题锚点整节替换（plain replace 只删单块会节体倍增）
    | "insert_after"
    | "delete"
    | "prepend"
    | "append";
  anchor?: string;
  content?: string;
}
```

3b. 新增导出纯函数（放 `findBlockByAnchor` 之后）：

```ts
// EAI-CUSTOM (全文操作 M1): 从标题锚点块向下扫到下一 level <= 锚点级 的标题前，
// 返回节内全部顶层块 id（含标题块）。非标题锚点 → null。
export function findSectionRange(
  doc: AnchorBlock[],
  anchorIndex: number,
): { blockIds: string[]; startIndex: number; endIndex: number } | null {
  const block = doc[anchorIndex];
  if (!block) return null;
  const level = (block.props as Record<string, unknown> | undefined)?.level;
  if (block.type !== "heading" || typeof level !== "number") return null;
  let end = anchorIndex;
  for (let i = anchorIndex + 1; i < doc.length; i++) {
    const b = doc[i]!;
    if (b.type === "heading") {
      const l = (b.props as Record<string, unknown> | undefined)?.level;
      if (typeof l === "number" && l <= level) break;
    }
    end = i;
  }
  const blockIds: string[] = [];
  for (let i = anchorIndex; i <= end; i++) blockIds.push(doc[i]!.id);
  return { blockIds, startIndex: anchorIndex, endIndex: end };
}
```

3c. `applyOperations` switch 增加 `replace_section` 分支（在 `case "prepend"` 之前）：

```ts
          case "replace_section": {
            if (!op.anchor) throw new Error("操作缺少 anchor: replace_section");
            const secMatch = findBlockByAnchor(editor.document, op.anchor);
            if (!secMatch) throw new Error(`找不到匹配的文本: "${op.anchor}"`);
            const range = findSectionRange(
              editor.document as unknown as AnchorBlock[],
              secMatch.blockIndex,
            );
            if (!range)
              throw new Error(`锚点不是标题块，无法按节替换: "${op.anchor}"`);
            editor.replaceBlocks(range.blockIds, parsed);
            break;
          }
```

- [ ] **Step 4: 跑绿 + typecheck**

```bash
cd frontend && pnpm test tests/unit/docmgr/section-range.test.ts && pnpm typecheck
```

（applyOperations 分支无 editor 难单测，由 findSectionRange 纯测 + Task 13 walkthrough 兜底。）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx frontend/tests/unit/docmgr/section-range.test.ts
git commit -m "feat(docmgr): replace_section 原语——findSectionRange 节边界纯函数+applyOperations 分支"
```

---

### Task 7: applyOperations 数学管线修复（TDD）

**Files:**
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx`（:650-659）
- Create: `frontend/tests/unit/docmgr/op-content.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// frontend/tests/unit/docmgr/op-content.test.ts
import { describe, expect, test } from "@rstest/core";

import { parseOperationContent } from "@/extensions/docmgr/PersonalBlockNoteEditor";

describe("parseOperationContent（op.content 统一走 details+math 管线）", () => {
  test("$$ 独立公式被转成 equation 块（不再裸 parse 成文本段）", () => {
    const blocks = parseOperationContent("前文。\n\n$$\nE = mc^2\n$$", (md) => [
      { id: "raw", type: "paragraph", content: [{ type: "text", text: md }] },
    ]) as Array<{ type: string }>;
    expect(blocks.some((b) => b.type === "equation")).toBe(true);
  });

  test("无公式内容原样通过管线（块数不丢）", () => {
    const blocks = parseOperationContent("a\n\nb", (md) =>
      md.split("\n\n").map((t, i) => ({
        id: `b${i}`,
        type: "paragraph",
        content: [{ type: "text", text: t }],
      })),
    ) as Array<{ type: string }>;
    expect(blocks.length).toBe(2);
    expect(blocks.every((b) => b.type === "paragraph")).toBe(true);
  });

  test("details 切分走 buildBlocksWithDetails（<details> 区域被识别）", () => {
    const seen: string[] = [];
    parseOperationContent("前文。\n\n<details>\n<summary>s</summary>\n\n内容\n\n</details>", (md) => {
      seen.push(md);
      return [];
    });
    // details 区域被切出单独交给 tryParse（detailsMarkdown 既有行为）
    expect(seen.some((md) => md.includes("<details>"))).toBe(true);
  });
});
```

（注：`equation` 类型名以 `utils/mathBlocks.ts:176-190` 实际产出为准——若跑红后实际类型名不同，按真实值改断言，不改实现。）

- [ ] **Step 2: 跑红**（parseOperationContent 不存在）

- [ ] **Step 3: 实现**

在 `PersonalBlockNoteEditor.tsx` 顶部 import 区（:60-71 已有 `buildBlocksWithDetails` 与 `transformMathInBlocks`，无需新增 import），`findSectionRange` 旁新增：

```ts
// EAI-CUSTOM (全文操作 M1 / spec §3-2): op.content 统一经「details 切分 + 数学转换」管线，
// 与 seed 同款（:472-481）。修复 $$..$$ 独立公式被裸 tryParse 成纯文本段落的问题。
// tryParse 由调用方注入以便测试。
export function parseOperationContent(
  content: string,
  tryParse: (md: string) => unknown[],
): unknown[] {
  const parsed = buildBlocksWithDetails(content, (md) => tryParse(md));
  return transformMathInBlocks(
    parsed as unknown as Parameters<typeof transformMathInBlocks>[0],
  ) as unknown[];
}
```

`applyOperations` :651-652 的裸 parse 替换为：

```ts
      for (const op of ops) {
        const parsed =
          op.op === "delete"
            ? []
            : parseOperationContent(op.content ?? "", (md) =>
                editor.tryParseMarkdownToBlocks(md) as unknown as unknown[],
              );
```

- [ ] **Step 4: 跑绿**

```bash
cd frontend && pnpm test tests/unit/docmgr/op-content.test.ts && pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx frontend/tests/unit/docmgr/op-content.test.ts
git commit -m "fix(docmgr): applyOperations op.content 走 details+math 管线——$$ 公式回灌不再退化为纯文本(bug-3301 同源)"
```

---

### Task 8: bug-3301 auto 模式解析缓存 + 逐 op 捕获（TDD）

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx`（parseAIMessage :772-799、OperationCards :452-462）
- Create: `frontend/tests/unit/docmgr/message-parse-cache.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// frontend/tests/unit/docmgr/message-parse-cache.test.ts
import { describe, expect, test } from "@rstest/core";

import { createAIMessageParser } from "@/extensions/docmgr/DocAIAgentPanel";

describe("createAIMessageParser（bug-3301：解析结果按消息身份缓存）", () => {
  test("同 id 同内容 → 同一对象引用（重渲染不产新 ops 数组）", () => {
    const parse = createAIMessageParser();
    const content = "说明\n\n---OPERATIONS---\n[{\"op\":\"append\",\"content\":\"x\"}]";
    const a = parse("m1", content);
    const b = parse("m1", content);
    expect(b).toBe(a);
    expect(b.ops).toHaveLength(1);
  });

  test("同 id 内容变化 → 重新解析（流式中内容增长）", () => {
    const parse = createAIMessageParser();
    const a = parse("m1", "前半");
    const b = parse("m1", "前半\n\n---OPERATIONS---\n[]");
    expect(b).not.toBe(a);
  });

  test("不同 id 各自缓存", () => {
    const parse = createAIMessageParser();
    const a = parse("m1", "AAA");
    const b = parse("m2", "AAA");
    expect(b).not.toBe(a);
    expect(parse("m1", "AAA")).toBe(a);
  });

  test("数组型 content 归一为文本再解析", () => {
    const parse = createAIMessageParser();
    const r = parse("m3", [{ type: "text", text: "---OPERATIONS---\n[{\"op\":\"append\",\"content\":\"y\"}]" }]);
    expect(r.ops).toHaveLength(1);
  });
});
```

- [ ] **Step 2: 跑红**（createAIMessageParser 不存在）

- [ ] **Step 3: 实现**

3a. `DocAIAgentPanel.tsx`：在 `parseOperations`（:136-185）之后新增导出：

```ts
/** EAI-CUSTOM (bug-3301): 解析结果按 message.id+内容缓存——流式完成后重渲染返回同一对象。
 *  内联解析每次渲染产出新 ops 数组 → auto effect 视为依赖变化重复应用并覆写快照点。 */
export function createAIMessageParser(): (
  id: string,
  content: unknown,
) => { text: string; ops: DocOperation[] | null; error: string | null } {
  const cache = new Map<
    string,
    { sig: string; parsed: { text: string; ops: DocOperation[] | null; error: string | null } }
  >();
  return (id, content) => {
    const raw =
      typeof content === "string"
        ? content
        : Array.isArray(content)
          ? content
              .map((b) => {
                if (typeof b !== "object" || b === null || !("text" in b))
                  return "";
                const t = (b as { text?: unknown }).text;
                return typeof t === "string" ? t : "";
              })
              .join("")
          : "";
    const hit = cache.get(id);
    if (hit && hit.sig === raw) return hit.parsed;
    // ponytail: 缓存上限 50 条，防长对话内存增长
    if (cache.size > 50) {
      const first = cache.keys().next().value;
      if (first !== undefined) cache.delete(first);
    }
    const parsed = parseOperations(raw);
    const result = {
      text: parsed.analysis,
      ops: parsed.operations,
      error: parsed.parseError,
    };
    cache.set(id, { sig: raw, parsed: result });
    return result;
  };
}
```

3b. 组件内 `parseAIMessage`（:772-799 整个 useCallback）替换为：

```ts
  /** Parse a single AI message for operations（bug-3301: 按消息缓存,身份稳定）。 */
  const parseAIMessageRef = useRef(createAIMessageParser());
  const parseAIMessage = useCallback(
    (msg: { id: string; content: unknown }) =>
      parseAIMessageRef.current(msg.id, msg.content),
    [],
  );
```

3c. 渲染处 :872 调用点改传整条消息：

```ts
                  const { text, ops, error } = parseAIMessage(item.msg);
```

3d. `OperationCards` auto effect（:452-462）替换为逐 op 捕获 + 防重挂载守卫：

```ts
  // Auto mode: apply all immediately, show notification with undo.
  // ponytail (bug-3301): 逐 op 捕获失败继续（弃首错即断）；appliedRef 防组件重挂载重复应用。
  const appliedRef = useRef(false);
  useEffect(() => {
    if (mode === "auto" && operations.length > 0 && !appliedRef.current) {
      appliedRef.current = true;
      snapshotRef.current = editorRef.current?.snapshotBlocks() ?? null;
      setAutoError(null);
      const failures: string[] = [];
      operations.forEach((op, i) => {
        try {
          editorRef.current?.applyOperations([op]);
        } catch (e) {
          failures.push(
            `操作${i + 1}${op.anchor ? `(${op.anchor.slice(0, 20)})` : ""}: ${getErrorMessage(e, "失败")}`,
          );
        }
      });
      if (failures.length > 0) setAutoError(failures.join("；"));
    }
  }, [operations, editorRef, mode]);
```

- [ ] **Step 4: 跑绿 + 既有回归**

```bash
cd frontend && pnpm test tests/unit/docmgr/message-parse-cache.test.ts && pnpm test tests/unit/docmgr/ai-panel.test.ts && pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAIAgentPanel.tsx frontend/tests/unit/docmgr/message-parse-cache.test.ts
git commit -m "fix(docmgr): bug-3301 auto 模式——解析结果按消息缓存+逐 op 捕获继续,弃重渲染重复应用与快照覆写"
```

---

### Task 9: aiTransformStream + NDJSON 事件类型（TDD）

**Files:**
- Modify: `frontend/src/extensions/api/index.ts`（aiEditStream :762-833 之后）
- Create: `frontend/tests/unit/docmgr/transform-stream.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// frontend/tests/unit/docmgr/transform-stream.test.ts
import { describe, expect, test } from "@rstest/core";

import { docmgrApi, ApiError } from "@/extensions/api";
import type { DocAITransformEvent } from "@/extensions/api";

function ndjsonResponse(lines: unknown[], status = 200): Response {
  const body = lines.map((l) => JSON.stringify(l) + "\n").join("");
  return new Response(body, { status, headers: { "Content-Type": "application/x-ndjson" } });
}

describe("aiTransformStream（NDJSON 逐行事件）", () => {
  test("逐行解析并回调；空行跳过", async () => {
    const events: DocAITransformEvent[] = [];
    const fetchMock = async () => ndjsonResponse([
      { type: "section_start", index: 0, total: 2, title: "一" },
      {},
      { type: "ops", index: 0, ops: [{ op: "replace_section", anchor: "一", content: "x" }] },
      { type: "done", total: 2, failed: [], skipped: [] },
    ]);
    const orig = globalThis.fetch;
    globalThis.fetch = fetchMock as typeof fetch;
    try {
      await docmgrApi.aiTransformStream<DocAITransformEvent>(
        { thread_id: "t", rel_path: "r", operation: "polish", content: "c" },
        (e) => events.push(e),
      );
    } finally {
      globalThis.fetch = orig;
    }
    expect(events.map((e) => e.type)).toEqual(["section_start", "ops", "done"]);
  });

  test("非 2xx 抛 ApiError（带状态码与响应体）", async () => {
    const orig = globalThis.fetch;
    globalThis.fetch = async () => new Response("boom", { status: 400 });
    try {
      await expect(
        docmgrApi.aiTransformStream(
          { thread_id: "t", rel_path: "r", operation: "polish", content: "c" },
          () => undefined,
        ),
      ).rejects.toMatchObject({ status: 400 });
    } finally {
      globalThis.fetch = orig;
    }
    expect(ApiError).toBeDefined();
  });
});
```

（注：若 `ApiError` 未从 `@/extensions/api` 导出，以该文件既有导出为准调整 import——`aiEditStream` 已在使用它。）

- [ ] **Step 2: 跑红**（aiTransformStream 不存在）

- [ ] **Step 3: 实现**（`extensions/api/index.ts`，aiEditStream 之后）

```ts
  // EAI-CUSTOM (全文操作 M1): docmgr /ai/transform 的 NDJSON 事件流（每行一个 JSON 事件，
  // 无 SSE data: 前缀）。克隆 aiEditStream 骨架（withCsrf + getReader + 行缓冲 + AbortSignal）。
  aiTransformStream: async <T>(
    data: {
      thread_id: string;
      rel_path: string;
      operation: string;
      content: string;
      model_name?: string;
      sections?: number[];
    },
    onEvent: (event: T) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    const response = await fetch(`${API_BASE}/docmgr/ai/transform`, {
      method: "POST",
      headers: withCsrf({ "Content-Type": "application/json" }, "POST"),
      body: JSON.stringify(data),
      signal,
      credentials: "include",
    });

    if (!response.ok) {
      const err = await response.text().catch(() => "Unknown error");
      throw new ApiError(
        response.status,
        `AI transform failed: ${response.status} ${err}`,
      );
    }

    const reader = response.body?.getReader();
    if (!reader) throw new ApiError(500, "No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          try {
            onEvent(JSON.parse(trimmed) as T);
          } catch {
            /* skip malformed line */
          }
        }
      }
    } finally {
      void reader.cancel();
    }
  },
```

事件类型放同文件顶部（`ApiError` 类定义附近）：

```ts
// EAI-CUSTOM (全文操作 M1): /ai/transform NDJSON 事件（spec §4.1）
export type DocAITransformEvent =
  | { type: "section_start"; index: number; total: number; title: string; skipped?: boolean }
  | { type: "ops"; index: number; ops: Array<{ op: string; anchor?: string; content?: string }> }
  | { type: "summary"; content: string }
  | { type: "section_error"; index: number; message: string }
  | { type: "done"; total: number; failed: number[]; skipped: number[]; message?: string };
```

- [ ] **Step 4: 跑绿**

```bash
cd frontend && pnpm test tests/unit/docmgr/transform-stream.test.ts && pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/api/index.ts frontend/tests/unit/docmgr/transform-stream.test.ts
git commit -m "feat(docmgr): aiTransformStream NDJSON reader(克隆 aiEditStream 骨架去 data: 前缀)+事件类型"
```

---

### Task 10: taskReducer 任务区状态机（TDD）

**Files:**
- Create: `frontend/src/extensions/docmgr/DocAITaskArea.tsx`（本任务先只写类型 + reducer）
- Create: `frontend/tests/unit/docmgr/task-reducer.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// frontend/tests/unit/docmgr/task-reducer.test.ts
import { describe, expect, test } from "@rstest/core";

import { taskReducer, initialTaskState } from "@/extensions/docmgr/DocAITaskArea";

const s0 = () => initialTaskState("polish");

describe("taskReducer（任务区状态机）", () => {
  test("section_start → streaming 卡片；skipped → skipped", () => {
    let s = taskReducer(s0(), { type: "section_start", index: 0, total: 2, title: "一" });
    expect(s.sections[0]).toMatchObject({ index: 0, status: "streaming", title: "一" });
    s = taskReducer(s, { type: "section_start", index: 1, total: 2, title: "二", skipped: true });
    expect(s.sections[1]).toMatchObject({ index: 1, status: "skipped" });
    expect(s.skipped).toEqual([1]);
  });

  test("ops 非空 → ready；空 → unchanged", () => {
    let s = taskReducer(s0(), { type: "section_start", index: 0, total: 1, title: "一" });
    s = taskReducer(s, { type: "ops", index: 0, ops: [{ op: "replace_section", anchor: "一", content: "x" }] });
    expect(s.sections[0]).toMatchObject({ status: "ready" });
    s = taskReducer(s, { type: "section_start", index: 1, total: 2, title: "二" });
    s = taskReducer(s, { type: "ops", index: 1, ops: [] });
    expect(s.sections[1]).toMatchObject({ status: "unchanged" });
  });

  test("section_error → failed 且后续节继续", () => {
    let s = taskReducer(s0(), { type: "section_start", index: 0, total: 2, title: "一" });
    s = taskReducer(s, { type: "section_error", index: 0, message: "失败" });
    expect(s.sections[0]).toMatchObject({ status: "failed", error: "失败" });
    s = taskReducer(s, { type: "section_start", index: 1, total: 2, title: "二" });
    expect(s.sections[1]).toMatchObject({ status: "streaming" });
    expect(s.failed).toEqual([0]);
  });

  test("applySection → applied；reverted 批量回 applied", () => {
    let s = taskReducer(s0(), { type: "section_start", index: 0, total: 1, title: "一" });
    s = taskReducer(s, { type: "ops", index: 0, ops: [{ op: "replace_section", anchor: "一", content: "x" }] });
    s = taskReducer(s, { type: "apply_section", index: 0 });
    expect(s.sections[0]?.status).toBe("applied");
    s = taskReducer(s, { type: "reverted" });
    expect(s.sections[0]?.status).toBe("ready");
  });

  test("summary 事件与 done 收口", () => {
    let s = taskReducer(s0(), { type: "summary", content: "摘要" });
    expect(s.summary).toBe("摘要");
    s = taskReducer(s, { type: "done", total: 0, failed: [], skipped: [], message: "提示" });
    expect(s).toMatchObject({ running: false, message: "提示" });
  });

  test("cancel 丢弃未确认（streaming/ready/failed 清除,applied/unchanged/skipped 保留）", () => {
    let s = taskReducer(s0(), { type: "section_start", index: 0, total: 3, title: "一" });
    s = taskReducer(s, { type: "ops", index: 0, ops: [{ op: "replace_section", anchor: "一", content: "x" }] });
    s = taskReducer(s, { type: "apply_section", index: 0 });
    s = taskReducer(s, { type: "section_start", index: 1, total: 3, title: "二" });
    s = taskReducer(s, { type: "section_start", index: 2, total: 3, title: "三", skipped: true });
    s = taskReducer(s, { type: "cancel" });
    expect(s.sections.map((x) => x.status)).toEqual(["applied", "skipped"]);
    expect(s.running).toBe(false);
    expect(s.message).toContain("已取消");
  });

  test("dismiss 清空任务", () => {
    expect(taskReducer(s0(), { type: "dismiss" })).toBeNull();
  });
});
```

- [ ] **Step 2: 跑红**

- [ ] **Step 3: 实现**（`DocAITaskArea.tsx` 本任务先只放类型 + reducer，组件/hook 在 Task 11-12 补）

```tsx
"use client";

// EAI-CUSTOM (全文操作 M1): 面板任务区状态机 + 组件（spec §4.4）。
// 任务区独立于 thread 消息流：不伪造 assistant 消息、不污染 lead_agent 线程历史。

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import type { DocAITransformEvent } from "../api";
import type { DocOperation, PersonalBlockNoteEditorRef } from "./PersonalBlockNoteEditor";
import { docmgrApi } from "../api";

// ── 状态机 ───────────────────────────────────────────────────────────

export type TaskSectionStatus =
  | "streaming"
  | "ready"
  | "unchanged"
  | "applied"
  | "skipped"
  | "failed";

export interface TaskSection {
  index: number;
  title: string;
  status: TaskSectionStatus;
  ops?: DocOperation[];
  error?: string;
}

export interface DocAITaskState {
  operation: string;
  running: boolean;
  sections: TaskSection[];
  summary?: string;
  failed: number[];
  skipped: number[];
  message?: string;
}

export type DocAITaskAction =
  | DocAITransformEvent
  | { type: "reset"; operation: string }
  | { type: "apply_section"; index: number }
  | { type: "reverted" }
  | { type: "cancel" }
  | { type: "dismiss" }
  | { type: "finish" };

export const initialTaskState = (operation: string): DocAITaskState => ({
  operation,
  running: true,
  sections: [],
  failed: [],
  skipped: [],
});

function upsertSection(sections: TaskSection[], next: TaskSection): TaskSection[] {
  const i = sections.findIndex((s) => s.index === next.index);
  if (i === -1) return [...sections, next].sort((a, b) => a.index - b.index);
  const copy = [...sections];
  copy[i] = { ...copy[i]!, ...next };
  return copy;
}

export function taskReducer(
  state: DocAITaskState | null,
  action: DocAITaskAction,
): DocAITaskState | null {
  if (action.type === "reset") return initialTaskState(action.operation);
  if (action.type === "dismiss") return null;
  if (action.type === "finish") return state ? { ...state, running: false } : state;
  if (!state) return state;
  switch (action.type) {
    case "section_start":
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title: action.title,
          status: action.skipped ? "skipped" : "streaming",
        }),
        skipped: action.skipped ? [...new Set([...state.skipped, action.index])] : state.skipped,
      };
    case "ops": {
      if (action.ops.length === 0) {
        return {
          ...state,
          sections: upsertSection(state.sections, {
            index: action.index,
            title: state.sections.find((s) => s.index === action.index)?.title ?? "",
            status: "unchanged",
          }),
        };
      }
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title: state.sections.find((s) => s.index === action.index)?.title ?? "",
          status: "ready",
          ops: action.ops as DocOperation[],
        }),
      };
    }
    case "section_error":
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title: state.sections.find((s) => s.index === action.index)?.title ?? "",
          status: "failed",
          error: action.message,
        }),
        failed: [...new Set([...state.failed, action.index])],
      };
    case "summary":
      return { ...state, summary: action.content };
    case "done":
      return { ...state, running: false, failed: action.failed, skipped: action.skipped, message: action.message };
    case "apply_section":
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title: state.sections.find((s) => s.index === action.index)?.title ?? "",
          status: "applied",
        }),
      };
    case "reverted":
      return {
        ...state,
        sections: state.sections.map((s) =>
          s.status === "applied" ? { ...s, status: "ready" } : s,
        ),
      };
    case "cancel":
      return {
        ...state,
        running: false,
        // 取消 = 未确认 ops 丢弃（spec §4.4）：已应用/无变更/跳过保留，其余清除
        sections: state.sections.filter((s) =>
          ["applied", "unchanged", "skipped"].includes(s.status),
        ),
        message: "已取消：未确认的操作已丢弃",
      };
    default:
      return state;
  }
}
```

注意 `ops` 事件的 ops 类型收窄：`action.ops as DocOperation[]`（DocAITransformEvent 里 op 为 string，此处信任后端枚举）。

- [ ] **Step 4: 跑绿**

```bash
cd frontend && pnpm test tests/unit/docmgr/task-reducer.test.ts
```

（此文件暂未导出组件，typecheck 留到 Task 12 一并过。）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAITaskArea.tsx frontend/tests/unit/docmgr/task-reducer.test.ts
git commit -m "feat(docmgr): 任务区 taskReducer 状态机(streaming/ready/unchanged/applied/skipped/failed+取消丢弃未确认)"
```

---

### Task 11: useDocAITask hook（任务通道流程 + 脏检查撤销）

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocAITaskArea.tsx`（hook 部分）
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx`（ref 加 onDocumentChange）

- [ ] **Step 1: 编辑器 ref 加变更监听**

`PersonalBlockNoteEditor.tsx`：

1a. 组件体内（`saveTimer` 等 ref 附近）加：

```ts
  // EAI-CUSTOM (全文操作 M1): 文档变更监听注册表（任务区脏检查用——任务开始后
  // 用户手动编辑过则禁用整批回滚，防止 restoreBlocks 吞掉手改，spec §3-6）。
  const docChangeListenersRef = useRef(new Set<() => void>());
```

1b. 既有 onChange disposer（:497 `const disposer = editor.onChange(() => {` 的回调体最前面）插入：

```ts
        docChangeListenersRef.current.forEach((cb) => cb());
```

1c. `PersonalBlockNoteEditorRef` 接口（:264 起）加：

```ts
  /** EAI-CUSTOM (全文操作): 注册文档变更监听（任务区脏检查）。返回注销函数。 */
  onDocumentChange: (cb: () => void) => () => void;
```

1d. `useImperativeHandle` 返回对象里加：

```ts
    onDocumentChange: (cb: () => void) => {
      docChangeListenersRef.current.add(cb);
      return () => docChangeListenersRef.current.delete(cb);
    },
```

- [ ] **Step 2: hook 实现**（`DocAITaskArea.tsx` reducer 之后）

```tsx
// ── 任务通道 hook ────────────────────────────────────────────────────

const CSRF_RE = /(?:^|;\s*)csrf_token=([^;]+)/;

function getErrMsg(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function useDocAITask(params: {
  editorRef: React.RefObject<PersonalBlockNoteEditorRef | null>;
  threadId: string;
  docRelPath: string;
  modelName: string | null;
}) {
  const [state, dispatch] = useReducer(taskReducer, null);
  const [busy, setBusy] = useState(false);
  const [undoBlocked, setUndoBlocked] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const snapshotRef = useRef<unknown[] | null>(null);
  const userEditedRef = useRef(false);
  const selfApplyRef = useRef(false);

  const markUserEdited = useCallback(() => {
    if (!selfApplyRef.current) userEditedRef.current = true;
  }, []);

  // 任务自己的 applyOperations 也会触发 onChange —— selfApplyRef 屏蔽，不算用户手改。
  const applyOpsSelf = useCallback(
    (ops: DocOperation[]) => {
      const ed = params.editorRef.current;
      if (!ed) throw new Error("编辑器未就绪");
      selfApplyRef.current = true;
      try {
        ed.applyOperations(ops);
      } finally {
        selfApplyRef.current = false;
      }
    },
    [params.editorRef],
  );

  const startTask = useCallback(
    async (operation: string, sections?: number[], fresh = true) => {
      const ed = params.editorRef.current;
      if (!ed || busy) return;
      setBusy(true);
      if (fresh) {
        userEditedRef.current = false;
        setUndoBlocked(false);
        snapshotRef.current = ed.snapshotBlocks();
        dispatch({ type: "reset", operation });
      }
      try {
        const raw = await ed.getMarkdown();
        const cleanContent = raw
          .replace(/<span[^>]*data-ai-\w+[^>]*>/g, "")
          .replace(/<\/span>/g, "");
        // bug-3302 同源修复：任务通道 PUT 同步必须检查 res.ok，失败即中止（半程文档不投喂模型）
        const token =
          typeof document !== "undefined"
            ? CSRF_RE.exec(document.cookie)?.[1]
            : null;
        const putRes = await fetch(
          `/api/extensions/docmgr/personal-docs/${encodeURIComponent(params.threadId)}/content`,
          {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
              ...(token ? { "X-CSRF-Token": token } : {}),
            },
            credentials: "include",
            body: JSON.stringify({ rel_path: params.docRelPath, content: cleanContent }),
          },
        );
        if (!putRes.ok) {
          throw new Error(`文档同步失败（${putRes.status}），已中止任务`);
        }
        try {
          await docmgrApi.createPersonalVersion(params.threadId, {
            rel_path: params.docRelPath,
            content: cleanContent,
            label: "AI 全文操作前快照",
          });
        } catch {
          /* 版本快照失败不阻塞任务 */
        }
        const controller = new AbortController();
        abortRef.current = controller;
        await docmgrApi.aiTransformStream(
          {
            thread_id: params.threadId,
            rel_path: params.docRelPath,
            operation,
            content: cleanContent,
            model_name: params.modelName ?? undefined,
            sections,
          },
          (event) => dispatch(event),
          controller.signal,
        );
      } catch (e) {
        if ((e as Error)?.name !== "AbortError") {
          dispatch({
            type: "done",
            total: 0,
            failed: [],
            skipped: [],
            message: getErrMsg(e, "任务失败"),
          });
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
        dispatch({ type: "finish" });
      }
    },
    [busy, params],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "cancel" });
  }, []);

  const applySection = useCallback(
    (index: number) => {
      const sec = state?.sections.find((s) => s.index === index);
      if (!sec?.ops) return;
      applyOpsSelf(sec.ops);
      dispatch({ type: "apply_section", index });
    },
    [state, applyOpsSelf],
  );

  const applyAll = useCallback(() => {
    if (!state) return;
    const failures: string[] = [];
    for (const sec of state.sections) {
      if (sec.status !== "ready" || !sec.ops) continue;
      try {
        applyOpsSelf(sec.ops);
        dispatch({ type: "apply_section", index: sec.index });
      } catch (e) {
        failures.push(`${sec.title || `第 ${sec.index + 1} 节`}: ${getErrMsg(e, "失败")}`);
      }
    }
    if (failures.length > 0) {
      dispatch({ type: "done", total: 0, failed: state.failed, skipped: state.skipped, message: `部分应用失败：${failures.join("；")}` });
    }
  }, [state, applyOpsSelf]);

  const undoAll = useCallback(() => {
    const ed = params.editorRef.current;
    if (!ed || !snapshotRef.current) return;
    if (userEditedRef.current) {
      setUndoBlocked(true); // 任务开始后文档被改过（含其他 AI 操作）→ 禁整批回滚，指路版本历史
      return;
    }
    ed.restoreBlocks(snapshotRef.current);
    dispatch({ type: "reverted" });
  }, [params.editorRef]);

  const dismiss = useCallback(() => {
    if (busy) return;
    dispatch({ type: "dismiss" });
  }, [busy]);

  const retrySection = useCallback(
    (index: number) => {
      if (!state) return;
      void startTask(state.operation, [index], false);
    },
    [state, startTask],
  );

  return {
    state,
    busy,
    undoBlocked,
    markUserEdited,
    startTask,
    cancel,
    applySection,
    applyAll,
    undoAll,
    dismiss,
    retrySection,
    insertSummary: applyOpsSelf,
  };
}

// ── 预设 chips + 任务区组件（Task 12 实现） ───────────────────────────
```

- [ ] **Step 3: typecheck**

```bash
cd frontend && pnpm typecheck
```

（hook 无独立单测——逻辑已拆进 reducer 纯测覆盖，fetch 流程由 Task 14 walkthrough 验证。）

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAITaskArea.tsx frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx
git commit -m "feat(docmgr): useDocAITask 任务通道——PUT res.ok 门+快照+取消丢弃+脏检查整批回滚(onDocumentChange)"
```

---

### Task 12: SectionCard / PresetChips / DocAITaskArea 组件（dom TDD）

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocAITaskArea.tsx`（组件部分）
- Create: `frontend/tests/unit/docmgr/task-area.dom.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
// frontend/tests/unit/docmgr/task-area.dom.test.tsx（.dom 后缀 → rstest 自动启用 happy-dom）
import { describe, expect, test } from "@rstest/core";
import { createRoot } from "react-dom/client";
import React from "react";

import {
  PresetChips,
  SectionCard,
} from "@/extensions/docmgr/DocAITaskArea";

function render(ui: React.ReactElement): HTMLElement {
  const host = document.createElement("div");
  document.body.appendChild(host);
  createRoot(host).render(ui);
  return host;
}

describe("PresetChips", () => {
  test("渲染 6 个预设并可点击", async () => {
    const picked: string[] = [];
    const host = render(
      <PresetChips
        disabled={false}
        onPick={(op) => picked.push(op)}
      />,
    );
    const buttons = Array.from(host.querySelectorAll("button"));
    expect(buttons.map((b) => b.textContent)).toEqual(
      ["全文润色", "全文校对", "术语统一", "格式规范", "生成目录", "全文摘要"],
    );
    buttons[0]!.click();
    await Promise.resolve();
    expect(picked).toEqual(["polish"]);
  });

  test("disabled 时点击无效", async () => {
    const picked: string[] = [];
    const host = render(<PresetChips disabled onPick={(op) => picked.push(op)} />);
    const btn = host.querySelectorAll("button")[0] as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});

describe("SectionCard", () => {
  const base = {
    index: 0,
    title: "第一节",
  };

  test("streaming → 生成中", () => {
    const host = render(<SectionCard section={{ ...base, status: "streaming" }} onApply={() => {}} onRetry={() => {}} />);
    expect(host.textContent).toContain("生成中");
  });

  test("skipped → 明示跳过原因", () => {
    const host = render(<SectionCard section={{ ...base, status: "skipped" }} onApply={() => {}} onRetry={() => {}} />);
    expect(host.textContent).toContain("已跳过");
  });

  test("unchanged → 无变更", () => {
    const host = render(<SectionCard section={{ ...base, status: "unchanged" }} onApply={() => {}} onRetry={() => {}} />);
    expect(host.textContent).toContain("无变更");
  });

  test("ready → 预览+应用+跳过", async () => {
    const applied: number[] = [];
    const host = render(
      <SectionCard
        section={{ ...base, status: "ready", ops: [{ op: "replace_section", anchor: "第一节", content: "新内容" }] }}
        onApply={(i) => applied.push(i)}
        onRetry={() => {}}
      />,
    );
    const buttons = Array.from(host.querySelectorAll("button"));
    const applyBtn = buttons.find((b) => b.textContent === "应用")!;
    applyBtn.click();
    await Promise.resolve();
    expect(applied).toEqual([0]);
  });

  test("failed → 错误信息+重试本节", async () => {
    const retried: number[] = [];
    const host = render(
      <SectionCard section={{ ...base, status: "failed", error: "超时" }} onApply={() => {}} onRetry={(i) => retried.push(i)} />,
    );
    expect(host.textContent).toContain("超时");
    const retry = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "重试本节")!;
    retry.click();
    await Promise.resolve();
    expect(retried).toEqual([0]);
  });

  test("applied → 已应用标记", () => {
    const host = render(<SectionCard section={{ ...base, status: "applied" }} onApply={() => {}} onRetry={() => {}} />);
    expect(host.textContent).toContain("已应用");
  });
});
```

- [ ] **Step 2: 跑红**

- [ ] **Step 3: 实现组件**（`DocAITaskArea.tsx` 末尾追加）

```tsx
// ── 组件 ─────────────────────────────────────────────────────────────

export const PRESETS = [
  { id: "polish", label: "全文润色" },
  { id: "proofread", label: "全文校对" },
  { id: "terminology", label: "术语统一" },
  { id: "format", label: "格式规范" },
  { id: "toc", label: "生成目录" },
  { id: "summary", label: "全文摘要" },
] as const;

export function PresetChips({
  disabled,
  onPick,
}: {
  disabled: boolean;
  onPick: (operation: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {PRESETS.map((p) => (
        <button
          key={p.id}
          type="button"
          disabled={disabled}
          onClick={() => onPick(p.id)}
          title={`对全文执行「${p.label}」（逐节处理，可逐节确认）`}
          className="border-border/60 hover:border-primary/50 hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-40 rounded-full border px-2.5 py-1 text-xs transition-colors"
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}

export function SectionCard({
  section,
  onApply,
  onRetry,
}: {
  section: TaskSection;
  onApply: (index: number) => void;
  onRetry: (index: number) => void;
}) {
  const { index, title, status, ops, error } = section;
  const preview = ops?.[0]?.content?.slice(0, 160) ?? "";
  return (
    <div className="border-border/60 bg-background rounded-lg border text-xs">
      <div className="flex items-center justify-between px-3 py-1.5">
        <span className="text-foreground font-medium">
          {title || `第 ${index + 1} 节`}
        </span>
        <span className="text-muted-foreground">
          {status === "streaming" && "生成中…"}
          {status === "ready" && "待确认"}
          {status === "unchanged" && "本节无变更"}
          {status === "skipped" && "已跳过（含公式/表格/图片）"}
          {status === "applied" && "✓ 已应用"}
          {status === "failed" && "失败"}
        </span>
      </div>
      {status === "ready" && preview && (
        <div className="border-border/40 text-muted-foreground max-h-24 overflow-y-auto border-t px-3 py-1.5 whitespace-pre-wrap">
          {preview}
          {(ops?.[0]?.content?.length ?? 0) > 160 ? "…" : ""}
        </div>
      )}
      {status === "failed" && error && (
        <div className="border-border/40 text-destructive border-t px-3 py-1.5">{error}</div>
      )}
      {status === "ready" && (
        <div className="border-border/40 flex border-t">
          <button type="button" onClick={() => onApply(index)} className="text-primary hover:bg-primary/5 flex-1 py-1.5">
            应用
          </button>
        </div>
      )}
      {status === "failed" && (
        <div className="border-border/40 flex border-t">
          <button type="button" onClick={() => onRetry(index)} className="text-primary hover:bg-primary/5 flex-1 py-1.5">
            重试本节
          </button>
        </div>
      )}
    </div>
  );
}
```

（本组件刻意不依赖 SafeStreamdown/编辑器——预览是纯文本截断，diff 对照 M3 再升级；`跳过`在 v1 即「不点应用」，不设按钮，spec 的「跳过」语义由不应用承载。若测试里需要「跳过」按钮文案，改测试断言为无按钮即可——以本实现为准，跑红后对齐。）

- [ ] **Step 4: 跑绿**

```bash
cd frontend && pnpm test tests/unit/docmgr/task-area.dom.test.tsx
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAITaskArea.tsx frontend/tests/unit/docmgr/task-area.dom.test.tsx
git commit -m "feat(docmgr): 任务区组件——PresetChips 六预设+SectionCard 六态(预览/应用/重试/跳过明示)"
```

---

### Task 13: 面板接线（chips + 任务区 + busy 锁 + onDocumentChange）

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx`

- [ ] **Step 1: import + hook 接线**

`DocAIAgentPanel.tsx` 顶部（:19 `import { docmgrApi } from "../api";` 附近）加：

```ts
import {
  DocAITaskArea,
  PresetChips,
  useDocAITask,
} from "./DocAITaskArea";
```

组件内（:565 `const [submitting, setSubmitting] = useState(false);` 之后）加：

```ts
  // ── 全文操作任务通道（EAI-CUSTOM M1） ─────────────────────────────
  const docTask = useDocAITask({ editorRef, threadId, docRelPath, modelName });
```

（`docTitle` 若未在解构里则不动；`docRelPath` 已在 props :527。）

- [ ] **Step 2: busy 锁 + 变更监听接线**

`handleSubmit`（:599-603 的 guard 区）最前面加：

```ts
    if (docTask.busy) {
      setError("全文任务进行中，请先完成或取消再发送对话");
      return;
    }
```

并把 `docTask.busy` 加进 `handleSubmit` 的 useCallback 依赖数组（:656-664）。

编辑器监听（模型下拉 effect 附近）加：

```ts
  // EAI-CUSTOM (全文操作): 编辑器就绪后挂脏检查监听（编辑器异步挂载,轮询接线）
  useEffect(() => {
    let off: (() => void) | null = null;
    let tries = 0;
    const timer = setInterval(() => {
      const ed = editorRef.current;
      if (ed?.onDocumentChange) {
        off = ed.onDocumentChange(docTask.markUserEdited);
        clearInterval(timer);
      } else if (++tries > 25) {
        clearInterval(timer);
      }
    }, 200);
    return () => {
      clearInterval(timer);
      off?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorRef]);
```

（`docTask.markUserEdited` 是 useCallback([]) 稳定引用，依赖数组只留 editorRef。）

- [ ] **Step 3: 渲染接线**

在 `{/* Input area */}` 注释（:920）之前插入预设 chips + 任务区：

```tsx
      {/* 全文操作任务通道（EAI-CUSTOM M1） */}
      <div className="border-border shrink-0 border-t px-3 pt-2">
        <PresetChips disabled={docTask.busy || isCreating} onPick={(op) => void docTask.startTask(op)} />
      </div>
      {docTask.state && (
        <DocAITaskArea
          task={docTask.state}
          busy={docTask.busy}
          undoBlocked={docTask.undoBlocked}
          onApplySection={docTask.applySection}
          onApplyAll={docTask.applyAll}
          onUndoAll={docTask.undoAll}
          onRetrySection={docTask.retrySection}
          onInsertSummary={(content) => docTask.insertSummary([{ op: "append", content }])}
          onCancel={docTask.cancel}
          onDismiss={docTask.dismiss}
        />
      )}
```

- [ ] **Step 4: DocAITaskArea 顶层组件**（`DocAITaskArea.tsx` 末尾补齐——Task 12 遗留的导出）

```tsx
export function DocAITaskArea({
  task,
  busy,
  undoBlocked,
  onApplySection,
  onApplyAll,
  onUndoAll,
  onRetrySection,
  onInsertSummary,
  onCancel,
  onDismiss,
}: {
  task: DocAITaskState;
  busy: boolean;
  undoBlocked: boolean;
  onApplySection: (index: number) => void;
  onApplyAll: () => void;
  onUndoAll: () => void;
  onRetrySection: (index: number) => void;
  onInsertSummary: (content: string) => void;
  onCancel: () => void;
  onDismiss: () => void;
}) {
  const appliedCount = task.sections.filter((s) => s.status === "applied").length;
  const readyCount = task.sections.filter((s) => s.status === "ready").length;
  return (
    <div className="shrink-0 space-y-2 px-3 py-2">
      <div className="flex items-center justify-between">
        <span className="text-foreground text-xs font-semibold">
          全文任务{busy ? "（进行中…）" : ""}
        </span>
        <div className="flex items-center gap-2">
          {busy && (
            <button type="button" onClick={onCancel} className="text-muted-foreground hover:text-foreground text-xs">
              取消
            </button>
          )}
          {!busy && (
            <button type="button" onClick={onDismiss} className="text-muted-foreground hover:text-foreground text-xs">
              关闭
            </button>
          )}
        </div>
      </div>
      {task.message && (
        <div className="bg-muted/30 text-muted-foreground rounded px-2 py-1.5 text-xs">{task.message}</div>
      )}
      {undoBlocked && (
        <div className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-400">
          任务开始后文档已被修改，整批回滚已禁用；请用「版本历史」恢复到「AI 全文操作前快照」。
        </div>
      )}
      {task.summary && (
        <div className="border-border/60 rounded-lg border p-2 text-xs">
          <div className="text-foreground mb-1 font-medium">全文摘要</div>
          <div className="text-muted-foreground max-h-40 overflow-y-auto whitespace-pre-wrap">{task.summary}</div>
          <button type="button" onClick={() => onInsertSummary(task.summary!)} className="text-primary mt-1.5 hover:underline">
            插入文末
          </button>
        </div>
      )}
      <div className="max-h-72 space-y-1.5 overflow-y-auto">
        {task.sections.map((s) => (
          <SectionCard key={s.index} section={s} onApply={onApplySection} onRetry={onRetrySection} />
        ))}
      </div>
      {!busy && readyCount > 0 && (
        <div className="flex items-center gap-2">
          <button type="button" onClick={onApplyAll} className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-xs">
            全部应用（{readyCount}）
          </button>
          {appliedCount > 0 && !undoBlocked && (
            <button type="button" onClick={onUndoAll} className="border-border/60 rounded-md border px-3 py-1.5 text-xs">
              撤销整批
            </button>
          )}
        </div>
      )}
      {!busy && appliedCount > 0 && readyCount === 0 && !undoBlocked && (
        <button type="button" onClick={onUndoAll} className="border-border/60 rounded-md border px-3 py-1.5 text-xs">
          撤销整批（{appliedCount}）
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 5: 全量前端验证**

```bash
cd frontend && pnpm test tests/unit/docmgr/ && pnpm typecheck && pnpm lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAIAgentPanel.tsx frontend/src/extensions/docmgr/DocAITaskArea.tsx
git commit -m "feat(docmgr): 面板接线任务通道——预设 chips+任务区+busy 互斥锁+脏检查监听挂载(EAI-CUSTOM M1)"
```

---

### Task 14: 端到端验收 walkthrough（容器内真实链路）

**Files:** 无新代码（修复 walkthrough 发现的问题除外）

- [ ] **Step 1: 重启容器**

```bash
docker compose -p eai-docker restart gateway frontend
```

- [ ] **Step 2: 验收场景（spec §9）**

浏览器 :2026 登录（admin@eai-flow.com / Admin@2026）→ 文档空间 → 打开一份 2 万字级、含公式与表格的计算书个人文档 → 右侧 AI 面板：

1. 点「全文校对」→ 逐节 section_start 流出、结构节显示「已跳过（含公式/表格/图片）」
2. 任一节 [应用] → 编辑器对应节替换、公式块仍是公式（**回归 Task 7 管线**）
3. [全部应用] → 全部 ready 节应用
4. 手动改一个字 → [撤销整批] → 出现琥珀色「整批回滚已禁用」提示（**回归脏检查**）
5. 关闭任务区重开面板 → 新任务「生成目录」→ 目录插入文首
6. 新任务「全文摘要」→ 摘要卡 + [插入文末]
7. 任务进行中点「取消」→ 未确认卡片消失、已应用保留
8. 对话输入框在任务进行中提交 → 提示「全文任务进行中」（**回归 busy 锁**）
9. 重复标题文档（两节同名）→ 自由对话 auto 模式 replace 该标题 → 卡片报「找不到匹配」（**回归 Task 5 安全失败**，不再静默错配）

- [ ] **Step 3: 收尾验证**

```bash
cd backend && make lint && make test
cd frontend && pnpm test && pnpm typecheck && pnpm lint
```

- [ ] **Step 4: 修复 walkthrough 发现的问题并按域拆 commit；最后记录**

```bash
git add -A && git commit -m "fix(docmgr): M1 walkthrough 修复(按实际问题补充)"
```

- [ ] **Step 5: 更新 .wolf 账本 + memory**

- `.wolf/buglog.json`：bug-3301/3302 状态更新为 fixed（本计划已修）
- `.wolf/memory.md` 追加一行 M1 落地记录
- 会话总结按 OPENWOLF.md 惯例写入

---

## T0 盘点记录（Task 1 执行后回填）

```
（待回填：docs=N total_sections=N section chars max/mean/p50/p90/p99、>4000 占比、>400k 文档数、top10）
（阈值裁定：SECTION_CHAR_LIMIT=____ MAX_SECTIONS=____ MAX_CONTENT_CHARS=____）
```

## 明确不做（对齐 spec §8）

协作文档面板 / 结构节块级穿引 / findings 跨会话记忆 / 字符级 diff / 操作库配置化 / 服务端单飞 / Plan 转执行 / 跨 tab 互斥。M2（审查 findings 契约 `contracts/docmgr_findings.v1.json` + FindingsCard）与 M3（行级 LCS diff + SectionDiffCard + 翻译预设）在 M1 验收后各出独立计划。
