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
            ("T", 1),
            ("S1", 2),
            ("SS", 3),
            ("S2", 2),
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

    def test_whitespace_between_sections_lossless(self):
        doc = "# A\n\nx\n\n\n\n## B\n\ny\n"
        secs = AT.split_sections(doc)
        assert "".join(s["content"] for s in secs) == doc
        assert secs[0]["content"].endswith("\n\n\n\n")

    def test_no_trailing_newline_lossless(self):
        doc = "# A\n\nx\n\n## B\n\ny"
        secs = AT.split_sections(doc)
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
        doc = "# H\n\n" + body * 120
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

    def test_oversized_atomic_bucket_marks_section_skipped(self):
        # I4: >4000 的单个代码围栏桶不可句号硬切（腰斩围栏）→ 整段单 chunk + 节标 structured（端点跳过）
        doc = "# H\n\n```python\n" + "x = 1\n" * 1200 + "```\n"
        secs = AT.split_sections(doc)
        assert len(secs) == 1
        assert secs[0]["structured"] is True
        assert any(len(p) > AT.SECTION_CHAR_LIMIT for p in secs[0]["pieces"])
        assert "".join(s["content"] for s in secs) == doc  # 有损不变量不受影响

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
        assert ops[0]["op"] == "prepend"  # M6a: 实质断言（原同义反复式已删）
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
    async def test_format_whitespace_only_diff_produces_ops(self, client, monkeypatch):
        # I1: format 交付含「中英文加空格」类纯行内空白差异，_norm 全空白归一会误判无变更
        fake = FakeModel(["# A\n\n瓦斯涌出量 Q 为 30 m3\n"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "format", "content": "# A\n\n瓦斯涌出量Q为30m3\n"})
        assert events[1]["ops"] and events[1]["ops"][0]["op"] == "replace_section"

    @pytest.mark.asyncio
    async def test_terminology_scan_empty_short_circuits(self, client, monkeypatch):
        # I2: 扫描空表 → 不逐节空转改写，直接 done（省 N 次无意义模型调用）
        fake = FakeModel(["[]"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "terminology", "content": DOC2})
        assert [e["type"] for e in events] == ["done"]
        assert "术语" in events[0]["message"] and fake.calls == 1

    @pytest.mark.asyncio
    async def test_terminology_scan_error_treated_as_no_variants(self, client, monkeypatch):
        # I2: 扫描调用炸 → 兜底按无变体处理并短路 done，不 500 不悬挂
        fake = FakeModel([], raise_on=1)
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "operation": "terminology", "content": DOC2})
        assert [e["type"] for e in events] == ["done"]
        assert "术语" in events[0]["message"] and fake.calls == 1

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
