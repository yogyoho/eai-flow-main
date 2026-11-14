"""批三十:编辑器真执行器桥(AST→ctx 覆盖 + 真实 43 条断言 + 锚点)与
POST /tasks/{id}/assert 只读端点。"""

import copy

import httpx
import pytest
import pytest_asyncio
from bid_write_exec_fixtures import green_ctx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_write import crud, models, worker
from app.extensions.bid_write import routers as R
from app.extensions.bid_write.executor.editor import run_editor_assertions
from app.extensions.database import Base, get_db
from app.extensions.workflow import subject_approval as SA


def _cell(role: str, text: str) -> dict:
    return {"type": "table_cell", "attrs": {"col_role": role}, "content": [{"type": "text", "text": text}]}


def _amount(role: str, text: str) -> dict:
    return {
        "type": "amount_cell",
        "attrs": {"readonly": True, "computed_expr": "", "role": role},
        "content": [{"type": "text", "text": text}],
    }


def _enum(current: str) -> dict:
    return {
        "type": "enum_cell",
        "attrs": {"enum_values": ["完全响应", "正偏离", "负偏离"], "current": current},
        "content": [{"type": "text", "text": current}],
    }


def editor_ast() -> dict:
    """green_ctx 的正文镜像:四表加总一致、★行全响应、无负偏离。"""
    return {
        "type": "doc",
        "content": [
            {
                "type": "section",
                "attrs": {"level": 1, "title": "一、投标函", "section_id": "S-letter"},
                "content": [
                    {
                        "type": "para",
                        "attrs": {"slot_id": "bl-opening"},
                        "content": [
                            {"type": "text", "text": "我方报价 "},
                            {"type": "text", "text": "2,000,000.00"},
                            {"type": "text", "text": " 元(大写:贰佰万元整)。"},
                        ],
                    }
                ],
            },
            {
                "type": "section",
                "attrs": {"level": 1, "title": "二、报价表", "section_id": "S-price"},
                "content": [
                    {
                        "type": "table",
                        "attrs": {"table_type": "price"},
                        "content": [
                            {
                                "type": "table_row",
                                "attrs": {"row_id": "1.1"},
                                "content": [
                                    _cell("name", "设备安装"),
                                    _cell("qty", "2"),
                                    _cell("unit", "800000.00"),
                                    _amount("amount", "1,600,000.00"),
                                ],
                            },
                            {
                                "type": "table_row",
                                "attrs": {"row_id": "1.2"},
                                "content": [
                                    _cell("name", "调试服务"),
                                    _cell("qty", "1"),
                                    _cell("unit", "400000.00"),
                                    _amount("amount", "400,000.00"),
                                ],
                            },
                            {
                                "type": "table_row",
                                "attrs": {"row_id": "TOTAL"},
                                "content": [
                                    _cell("name", "合计"),
                                    _cell("qty", ""),
                                    _cell("unit", ""),
                                    _amount("total_num", "2,000,000.00"),
                                    _amount("total_cn", "贰佰万元整"),
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "type": "section",
                "attrs": {"level": 1, "title": "三、商务响应", "section_id": "S-response"},
                "content": [
                    {
                        "type": "table",
                        "attrs": {"table_type": "response"},
                        "content": [
                            {
                                "type": "table_row",
                                "attrs": {"row_id": "att:1"},
                                "content": [_cell("name", "营业执照"), _enum("完全响应")],
                            },
                            {
                                "type": "table_row",
                                "attrs": {"row_id": "decl:1"},
                                "content": [_cell("name", "承诺"), _enum("完全响应")],
                            },
                        ],
                    }
                ],
            },
        ],
    }


def _payload(ast: dict | None = None) -> dict:
    return run_editor_assertions(green_ctx(), ast or editor_ast())


def test_green_ast_passes_and_has_no_false_decorations():
    out = _payload()
    assert out["states"] == {}
    assert out["skipped"] == []
    assert out["summary"] == {"d0": 0, "d1": 0, "d2": 0, "skipped": []}
    assert all(item["status"] == "PASS" for item in out["results"])


def test_letter_amount_mismatch_anchors_total_and_letter():
    ast = editor_ast()
    ast["content"][0]["content"][0]["content"][1]["text"] = "1,900,000.00"
    out = _payload(ast)
    assert out["states"]["bl-opening"]["err_code"] == "SK-BL-002"
    assert out["states"]["price:TOTAL"]["err_code"] == "SK-PS-003"


def test_price_row_arithmetic_mismatch_anchors_row_despite_d0_short_circuit():
    ast = editor_ast()
    ast["content"][1]["content"][0]["content"][0]["content"][3]["content"][0]["text"] = "700,000.00"
    out = _payload(ast)
    assert out["states"]["price:1.1"] == {
        "state": "D0",
        "err_code": "SK-PS-008",
        "message": "行金额失配:qty×单价≠金额",
    }
    assert out["states"]["price:TOTAL"]["err_code"] == "SK-PS-003"
    # 报告口径不被装饰面改写:SK-PS-008 仍是 SKIPPED(短路),不是 PASS
    status = {item["assertion_id"]: item["status"] for item in out["results"]}
    assert status["SK-PS-008"] == "SKIPPED"


def test_negative_star_and_unclosed_deviation_anchor():
    ast = editor_ast()
    row = ast["content"][2]["content"][0]["content"][0]
    row["content"][1] = _enum("负偏离")
    out = _payload(ast)
    assert out["states"]["rt:att:1"]["err_code"] == "SK-RT-002"
    assert out["states"]["devnote:att:1"]["err_code"] == "SK-RT-005"

    # 展开面补全 → RT-005 闭环;RT-002(★负偏离)仍阻断
    ast["content"][2]["content"].append(
        {
            "type": "deviation_note",
            "attrs": {"row_id": "att:1"},
            "content": [
                {"type": "para", "attrs": {"slot_id": "", "label": "偏离原因"}, "content": [{"type": "text", "text": "产能不足"}]},
                {"type": "para", "attrs": {"slot_id": "", "label": "替代方案"}, "content": [{"type": "text", "text": "分批交付"}]},
            ],
        }
    )
    out2 = _payload(ast)
    assert "devnote:att:1" not in out2["states"]
    assert out2["states"]["rt:att:1"]["err_code"] == "SK-RT-002"


def test_orphan_deviation_note_is_d1():
    ast = editor_ast()
    ast["content"][2]["content"].append(
        {
            "type": "deviation_note",
            "attrs": {"row_id": "att:1"},
            "content": [
                {"type": "para", "attrs": {"slot_id": "", "label": "偏离原因"}, "content": [{"type": "text", "text": "旧原因"}]},
                {"type": "para", "attrs": {"slot_id": "", "label": "替代方案"}, "content": [{"type": "text", "text": "旧方案"}]},
            ],
        }
    )
    out = _payload(ast)
    assert out["states"]["devnote:att:1"]["state"] == "D1"
    assert out["states"]["devnote:att:1"]["err_code"] == "SK-RT-005"


def test_todo_and_status_mark_are_reflected():
    ast = editor_ast()
    ast["content"].append({"type": "todo_block", "attrs": {"missing": "质保承诺函", "pending_item_id": "P-9", "level": "D0", "blocks_export": True}})
    ast["content"][0]["content"][0]["content"][1]["marks"] = [{"type": "status_mark", "attrs": {"state": "D1", "err_code": "SK-BL-002"}}]
    out = _payload(ast)
    assert out["states"]["todo:P-9"]["state"] == "D0"
    assert out["states"]["bl-opening"]["state"] == "D1"
    assert out["states"]["bl-opening"]["err_code"] == "SK-BL-002"


def test_duplicate_row_id_raises():
    ast = editor_ast()
    table = ast["content"][1]["content"][0]
    table["content"].append(copy.deepcopy(table["content"][0]))
    with pytest.raises(ValueError, match="row_id 重复"):
        _payload(ast)


def test_bad_ast_root_raises():
    with pytest.raises(ValueError, match="type"):
        _payload({"type": "para"})


# ── endpoint ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(
            Base.metadata.create_all,
            tables=[
                models.WriteTask.__table__,
                models.MatrixRow.__table__,
                models.MaterialEntity.__table__,
                models.MaterialProfile.__table__,
                models.BidWritePolicy.__table__,
                models.TaskDocument.__table__,
                R._SkillRun.__table__,
                SA.WorkflowSubjectInstance.__table__,
                SA.WorkflowSubjectReview.__table__,
            ],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    async def fake_ctx(*_args, **_kwargs):
        return green_ctx()

    monkeypatch.setattr(worker, "build_task_ctx", fake_ctx)
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.asyncio
async def test_assert_endpoint_is_read_only(client, db):
    task = await crud.create_task(db, "u1")
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/assert", json={"ast": editor_ast()})
    assert r.status_code == 200
    body = r.json()
    assert body["states"] == {} and body["run_at"]
    assert len(body["results"]) == 43
    assert await crud.latest_skill_run(db, task_id=task.id, owner_id="u1") is None


@pytest.mark.asyncio
async def test_assert_endpoint_validation_and_owner(client, db):
    task = await crud.create_task(db, "u1")
    r = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/assert", json={"ast": {"type": "para"}})
    assert r.status_code == 422

    dup = editor_ast()
    table = dup["content"][1]["content"][0]
    table["content"].append(copy.deepcopy(table["content"][0]))
    r2 = await client.post(f"/api/extensions/bid-write/tasks/{task.id}/assert", json={"ast": dup})
    assert r2.status_code == 422 and "row_id" in r2.json()["detail"]

    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u2"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c2:
        r3 = await c2.post(f"/api/extensions/bid-write/tasks/{task.id}/assert", json={"ast": editor_ast()})
        assert r3.status_code == 404
