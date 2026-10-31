"""docmgr ai_review（全文操作 M2 审查）单测——审查端点 NDJSON 事件流 + findings 契约过滤。

EAI-CUSTOM: 克隆 test_docmgr_ai_transform.py 手法——独立 FastAPI 子 app +
dependency_overrides 打桩权限依赖；模型注入 monkeypatch ai_transform.create_chat_model。
"""

import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.extensions.docmgr import ai_transform as AT

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "docmgr_findings.v1.json"

DOC2 = "# 一\n\n甲内容。\n\n## 二\n\n乙内容。\n"


def _ok(sev="warn", **over):
    """一条字段齐全的合法 finding（模型输出形态：无 id，id 由服务端生成）。"""
    item = {"severity": sev, "anchor": "一", "excerpt": "问题片段", "problem": "问题描述", "suggestion": "修改建议"}
    item.update(over)
    return item


def _finding_json(*items) -> str:
    return json.dumps(list(items), ensure_ascii=False)


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
    async with client.stream("POST", "/api/extensions/docmgr/ai/review", json=payload) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.strip():
                events.append(json.loads(line))
    return events


UNITS2 = {"thread_id": "t", "rel_path": "r.md", "review_type": "units", "content": DOC2}


class TestReviewGuards:
    @pytest.mark.asyncio
    async def test_unknown_review_type_400(self, client):
        r = await client.post("/api/extensions/docmgr/ai/review", json={"thread_id": "t", "rel_path": "r", "review_type": "bogus", "content": "x"})
        assert r.status_code == 400
        detail = r.json()["detail"]
        for legal in ("consistency", "numbering", "units", "custom"):
            assert legal in detail

    @pytest.mark.asyncio
    async def test_custom_without_instruction_400(self, client):
        # instruction 缺省 / 空白串都算「为空」→ 400
        for instruction in (None, "", "   "):
            payload = {"thread_id": "t", "rel_path": "r", "review_type": "custom", "content": DOC2}
            if instruction is not None:
                payload["instruction"] = instruction
            r = await client.post("/api/extensions/docmgr/ai/review", json=payload)
            assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_model_assembly_overrides(self, client, monkeypatch):
        # 模型装配同 transform：thinking 关 + max_tokens 8192
        captured = {}
        fake = FakeModel(["[]", "[]"])

        def _fake_factory(name=None, thinking_enabled=False, model_overrides=None, **kw):
            captured["overrides"] = model_overrides
            captured["thinking"] = thinking_enabled
            return fake

        monkeypatch.setattr(AT, "create_chat_model", _fake_factory)
        await _events(client, UNITS2)
        assert captured["overrides"] == {"max_tokens": 8192}
        assert captured["thinking"] is False


class TestReviewStream:
    @pytest.mark.asyncio
    async def test_ndjson_event_sequence(self, client, monkeypatch):
        fake = FakeModel([_finding_json(_ok()), _finding_json(_ok("info"))])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, UNITS2)
        assert [e["type"] for e in events] == ["section_start", "finding", "section_start", "finding", "done"]
        assert events[0] == {"type": "section_start", "index": 0, "total": 2, "title": "一"}
        assert events[2] == {"type": "section_start", "index": 1, "total": 2, "title": "二"}
        f0 = events[1]["finding"]
        assert events[1]["index"] == 0
        assert f0["id"] == "units-0-0" and f0["severity"] == "warn" and f0["anchor"] == "一"
        assert events[3]["finding"]["id"] == "units-1-0"
        done = events[-1]
        assert done["total"] == 2 and done["failed"] == [] and done["skipped"] == []
        assert done["summary"] == {"error": 0, "warn": 1, "info": 1}

    @pytest.mark.asyncio
    async def test_summary_counts_mixed(self, client, monkeypatch):
        r1 = _finding_json(_ok("error"), _ok("warn"), _ok("warn"), _ok("info"))
        r2 = _finding_json(_ok("error"))
        fake = FakeModel([r1, r2])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, UNITS2)
        assert events[-1]["summary"] == {"error": 2, "warn": 2, "info": 1}
        assert len([e for e in events if e["type"] == "finding"]) == 5

    @pytest.mark.asyncio
    async def test_consistency_two_pass_uses_terminology_table(self, client, monkeypatch):
        scan = json.dumps([{"canonical": "供水系统", "variants": ["给水系统"]}], ensure_ascii=False)
        fake = FakeModel([scan, _finding_json(_ok("error", excerpt="给水系统残留")), _finding_json(_ok("warn"))])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "consistency", "content": DOC2})
        assert "术语审校" in fake.prompts[0]  # 第一遍 = 复用 _scan_terminology 全文扫描
        assert "供水系统" in fake.prompts[1] and "给水系统" in fake.prompts[1]  # 第二遍逐节携术语表
        assert events[1]["finding"]["id"] == "consistency-0-0"
        assert events[3]["finding"]["id"] == "consistency-1-0"
        assert fake.calls == 3  # 1 次扫描 + 2 节

    @pytest.mark.asyncio
    async def test_consistency_empty_table_short_circuits(self, client, monkeypatch):
        # 同 transform terminology 短路先例：空术语表不逐节空转
        fake = FakeModel(["[]"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "consistency", "content": DOC2})
        assert [e["type"] for e in events] == ["done"]
        assert events[0]["total"] == 0 and "术语" in events[0]["message"]
        assert fake.calls == 1

    @pytest.mark.asyncio
    async def test_numbering_two_pass(self, client, monkeypatch):
        scan = json.dumps([{"title": "一", "numbers": ["1", "1.1"]}], ensure_ascii=False)
        fake = FakeModel([scan, _finding_json(_ok()), _finding_json(_ok("info"))])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "numbering", "content": DOC2})
        assert "编号审校" in fake.prompts[0]  # 第一遍全文提编号清单
        assert "编号清单" in fake.prompts[1] and "1.1" in fake.prompts[1]  # 第二遍携清单
        assert events[1]["finding"]["id"] == "numbering-0-0"
        assert fake.calls == 3

    @pytest.mark.asyncio
    async def test_numbering_empty_scan_short_circuits(self, client, monkeypatch):
        fake = FakeModel(["[]"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "numbering", "content": DOC2})
        assert [e["type"] for e in events] == ["done"]
        assert events[0]["total"] == 0 and "编号" in events[0]["message"]
        assert fake.calls == 1

    @pytest.mark.asyncio
    async def test_custom_instruction_in_prompt(self, client, monkeypatch):
        fake = FakeModel(["[]", "[]"])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "custom", "instruction": "检查所有日期格式是否统一", "content": DOC2})
        assert fake.prompts[0].count("检查所有日期格式是否统一") >= 1
        assert "检查所有日期格式是否统一" in fake.prompts[1]

    @pytest.mark.asyncio
    async def test_bad_json_section_error_then_continue(self, client, monkeypatch):
        fake = FakeModel(["这不是JSON数组", _finding_json(_ok())])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, UNITS2)
        assert [e["type"] for e in events] == ["section_start", "section_error", "section_start", "finding", "done"]
        assert events[1]["index"] == 0 and "解析" in events[1]["message"]
        assert events[-1]["failed"] == [0]
        assert events[3]["finding"]["id"] == "units-1-0"  # 后续节继续

    @pytest.mark.asyncio
    async def test_model_exception_section_error_then_continue(self, client, monkeypatch):
        fake = FakeModel([_finding_json(_ok())], raise_on=1)
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, UNITS2)
        assert [e["type"] for e in events] == ["section_start", "section_error", "section_start", "finding", "done"]
        assert events[-1]["failed"] == [0]

    @pytest.mark.asyncio
    async def test_severity_downgrade_and_missing_field_drop(self, client, monkeypatch):
        items = _finding_json(
            _ok("critical"),  # severity 白名单外 → 降级 warn
            {"severity": "info", "anchor": "一", "excerpt": "x"},  # 缺 problem/suggestion → 整条丢弃
            _ok("info"),  # 合法条目仍发出
        )
        fake = FakeModel([items])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "units", "content": "# A\n\nx\n"})
        findings = [e["finding"] for e in events if e["type"] == "finding"]
        assert [f["id"] for f in findings] == ["units-0-0", "units-0-2"]  # id 按原始位次，被丢条留空位
        assert [f["severity"] for f in findings] == ["warn", "info"]
        assert events[-1]["summary"] == {"error": 0, "warn": 1, "info": 1}

    @pytest.mark.asyncio
    async def test_excerpt_truncated_to_120(self, client, monkeypatch):
        fake = FakeModel([_finding_json(_ok("info", excerpt="长" * 300))])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "units", "content": "# A\n\nx\n"})
        assert len(events[1]["finding"]["excerpt"]) == 120

    @pytest.mark.asyncio
    async def test_fixed_section_becomes_fix_op(self, client, monkeypatch):
        item = _ok("error", fixed_section="# 一\n\n修正后全文。")
        fake = FakeModel([_finding_json(item)])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "units", "content": "# A\n\nx\n"})
        f = events[1]["finding"]
        assert f["fix_op"] == {"op": "replace_section", "anchor": "A", "content": "# 一\n\n修正后全文。"}
        assert "fixed_section" not in f  # 模型内部字段不得漏进契约对象

    @pytest.mark.asyncio
    async def test_empty_fixed_section_no_fix_op(self, client, monkeypatch):
        fake = FakeModel([_finding_json(_ok("warn", fixed_section="   "))])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "units", "content": "# A\n\nx\n"})
        assert "fix_op" not in events[1]["finding"]

    @pytest.mark.asyncio
    async def test_structured_section_skipped_no_model_call(self, client, monkeypatch):
        fake = FakeModel([_finding_json(_ok())])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        doc = "# 一\n\n纯文字。\n\n## 二\n\n$$\nE\n$$\n"
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "units", "content": doc})
        assert events[2] == {"type": "section_start", "index": 1, "total": 2, "title": "二", "skipped": True}
        assert events[-1]["skipped"] == [1]
        assert fake.calls == 1  # 仅第一节送模型

    @pytest.mark.asyncio
    async def test_titleless_doc_section_error(self, client, monkeypatch):
        fake = FakeModel([_finding_json(_ok())])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "units", "content": "无标题全文。"})
        assert any(e["type"] == "section_error" and "标题" in e["message"] for e in events)
        assert events[-1]["failed"] == [0]


class TestContractSmoke:
    @pytest.mark.asyncio
    async def test_emitted_findings_match_contract(self, client, monkeypatch):
        items = _finding_json(_ok("error", fixed_section="修正"), _ok("warn"), _ok("info"))
        fake = FakeModel([items])
        monkeypatch.setattr(AT, "create_chat_model", lambda **kw: fake)
        events = await _events(client, {"thread_id": "t", "rel_path": "r", "review_type": "units", "content": "# A\n\nx\n"})
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        props = set(contract["properties"])
        required = set(contract["required"])
        emitted = 0
        for e in events:
            if e["type"] != "finding":
                continue
            emitted += 1
            f = e["finding"]
            assert set(f) <= props, f"finding 键超出契约 properties: {set(f) - props}"
            assert required <= set(f), f"契约 required 字段缺失: {required - set(f)}"
            assert f["severity"] in contract["properties"]["severity"]["enum"]
        assert emitted == 3
