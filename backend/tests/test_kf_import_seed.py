"""Tests for POST /api/kf/templates/import-seed (EAI-CUSTOM: coal-eia v2 D12).

seed = seed_gen.py 从 stage JSON 单向派生的模板工件（kind=kf_template_seed）。
导入服务校验方式与 seed_gen selfcheck 一致：逐节点用 schemas.TemplateSection
pydantic 真模型装载。只写主表 extraction_templates.root_sections_json
（编辑器真源），不双写 template_sections 表。
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.extensions.knowledge_factory import routers
from app.extensions.knowledge_factory.schemas import TemplateSeedImportRequest
from app.extensions.knowledge_factory.service import (
    TemplateNameConflictError,
    TemplateSeedImportService,
)

# 真实 spike 产物（seed_gen 生成，13 章 77 节）；不在本机则跳过集成冒烟
SEED_SPIKE_PATH = r"C:/Users/admin/.claude/jobs/5bb3dc2a/tmp/t0spike/planning_seed.json"


# ──────────────────────────────────────────────────────────────────────
# Helpers（fixture 风格对齐 test_knowledge_factory_mcp.py：AsyncMock db）
# ──────────────────────────────────────────────────────────────────────


def _make_seed(**overrides):
    """最小合法 seed（2 章 × 2 节，形状对齐 seed_gen.py 产出）。"""
    seed = {
        "kind": "kf_template_seed",
        "metadata": {
            "stage": "测试环评",
            "stage_id": "test_eia",
            "totals": {"chapters": 2, "sections": 4, "floor_chars_total": 800},
        },
        "template": {
            "domain": "test_eia",
            "name": "测试环评报告模板（节级·seed 生成）",
            "version": "v1.0",
            "status": "draft",
        },
        "root_sections_json": {
            "sections": [
                {
                    "id": "ch1",
                    "title": "总则",
                    "level": 1,
                    "required": True,
                    "purpose": "编制依据",
                    "generation_hint": "- 依据清单",
                    "content_contract": {"min_word_count": 400, "key_elements": ["编制依据"]},
                    "children": [
                        {
                            "id": "ch1-1",
                            "title": "评价目的",
                            "level": 2,
                            "required": True,
                            "content_contract": {"min_word_count": 200, "key_elements": []},
                        },
                        {
                            "id": "ch1-2",
                            "title": "评价标准",
                            "level": 2,
                            "required": True,
                            "content_contract": {"min_word_count": 200, "key_elements": []},
                        },
                    ],
                },
                {
                    "id": "ch2",
                    "title": "结论与建议",
                    "level": 1,
                    "required": True,
                    "content_contract": {"min_word_count": 400, "key_elements": []},
                    "children": [
                        {
                            "id": "ch2-1",
                            "title": "结论",
                            "level": 2,
                            "required": True,
                            "content_contract": {"min_word_count": 200, "key_elements": []},
                        },
                        {
                            "id": "ch2-2",
                            "title": "建议",
                            "level": 2,
                            "required": True,
                            "content_contract": {"min_word_count": 200, "key_elements": []},
                        },
                    ],
                },
            ]
        },
    }
    seed.update(overrides)
    return seed


def _mock_db(existing=None):
    """AsyncMock 风格 db：execute→scalar_one_or_none(existing)，其余写方法就绪。

    db.add 侧效给 ORM 对象补 id——模拟真实 flush 时 SQLAlchemy 应用的
    default=uuid.uuid4 列默认值（mock flush 不会触发）。
    """
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock(side_effect=lambda obj: setattr(obj, "id", uuid4()))
    return db


def _fake_user():
    user = MagicMock()
    user.id = uuid4()
    return user


# ──────────────────────────────────────────────────────────────────────
# 服务层：合法导入 / 发布 / 幂等 409 / 校验 422
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_seed_creates_draft_row():
    """合法 seed → draft 行：root_sections_json 原样落库、created_by=当前用户、缺省 v1.0。"""
    seed = _make_seed()
    db = _mock_db(existing=None)
    user = _fake_user()

    tpl = await TemplateSeedImportService.import_seed_template(db, seed, user_id=user.id)

    assert tpl.status == "draft"
    assert tpl.name == seed["template"]["name"]
    assert tpl.domain == seed["template"]["domain"]
    assert tpl.version == "v1.0"
    assert tpl.completeness_score == 0
    assert tpl.created_by == user.id
    assert tpl.root_sections_json == seed["root_sections_json"]  # 原样落 jsonb
    assert TemplateSeedImportService.count_sections(tpl.root_sections_json["sections"]) == 6
    db.add.assert_called_once()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_import_seed_name_domain_overrides_and_metadata_score():
    """请求 name/domain 覆盖 seed.template 建议值；completeness_score 取 seed.metadata。"""
    seed = _make_seed()
    seed["metadata"]["completeness_score"] = 80
    db = _mock_db()

    tpl = await TemplateSeedImportService.import_seed_template(db, seed, name="自定义名", domain="自定义域", user_id=uuid4())
    assert tpl.name == "自定义名"
    assert tpl.domain == "自定义域"
    assert tpl.completeness_score == 80


@pytest.mark.asyncio
async def test_import_seed_publish_true_goes_through_publish_path():
    """publish=true → 复用 TemplateService.publish_template：status=published + 版本快照行。"""
    seed = _make_seed()
    db = _mock_db()
    user = _fake_user()

    with patch("app.extensions.knowledge_factory.service.save_snapshot") as snap:
        tpl = await TemplateSeedImportService.import_seed_template(db, seed, publish=True, user_id=user.id)

    assert tpl.status == "published"
    snap.assert_called_once()
    # publish_template 额外 add 了一条版本快照记录
    assert db.add.call_count == 2


@pytest.mark.asyncio
async def test_import_seed_duplicate_name_raises_conflict():
    """同 name 已存在 → TemplateNameConflictError（携带已存在 id），路由映射 409。"""
    existing = MagicMock()
    existing.id = uuid4()
    existing.name = _make_seed()["template"]["name"]
    db = _mock_db(existing=existing)

    with pytest.raises(TemplateNameConflictError) as exc_info:
        await TemplateSeedImportService.import_seed_template(db, _make_seed(), user_id=uuid4())
    assert exc_info.value.template_id == existing.id


@pytest.mark.asyncio
async def test_import_seed_empty_sections_rejected():
    """root_sections_json.sections 空 → ValueError（路由映射 422）。"""
    seed = _make_seed()
    seed["root_sections_json"] = {"sections": []}
    with pytest.raises(ValueError, match="非空数组"):
        await TemplateSeedImportService.import_seed_template(db=_mock_db(), seed=seed, user_id=uuid4())


@pytest.mark.asyncio
async def test_import_seed_node_missing_title_rejected():
    """任一节点缺 title → ValueError（递归检查，路由映射 422）。"""
    seed = _make_seed()
    del seed["root_sections_json"]["sections"][1]["children"][0]["title"]
    with pytest.raises(ValueError, match="title"):
        await TemplateSeedImportService.import_seed_template(db=_mock_db(), seed=seed, user_id=uuid4())


@pytest.mark.asyncio
async def test_import_seed_node_bad_content_contract_rejected():
    """content_contract.min_word_count 非正整数 → TemplateSection 装载失败 → ValueError。"""
    seed = _make_seed()
    seed["root_sections_json"]["sections"][0]["children"][0]["content_contract"]["min_word_count"] = "abc"
    with pytest.raises(ValueError, match="TemplateSection"):
        await TemplateSeedImportService.import_seed_template(db=_mock_db(), seed=seed, user_id=uuid4())


@pytest.mark.asyncio
async def test_import_seed_missing_name_everywhere_rejected():
    """请求与 seed.template 均无 name → ValueError（路由映射 422）。"""
    seed = _make_seed()
    seed["template"] = {"domain": "test_eia"}
    with pytest.raises(ValueError, match="名称缺失"):
        await TemplateSeedImportService.import_seed_template(db=_mock_db(), seed=seed, user_id=uuid4())


# ──────────────────────────────────────────────────────────────────────
# 路由层：状态码映射（直接调路由函数，风格同 KF 既有单测）
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_router_conflict_maps_to_409_with_existing_id():
    existing = MagicMock()
    existing.id = uuid4()
    db = _mock_db(existing=existing)
    body = TemplateSeedImportRequest(seed=_make_seed())

    with pytest.raises(HTTPException) as exc:
        await routers.import_seed_template(body=body, db=db, current_user=_fake_user())
    assert exc.value.status_code == 409
    assert str(existing.id) in exc.value.detail


@pytest.mark.asyncio
async def test_router_validation_error_maps_to_422():
    seed = _make_seed()
    seed["root_sections_json"] = {"sections": []}
    body = TemplateSeedImportRequest(seed=seed)

    with pytest.raises(HTTPException) as exc:
        await routers.import_seed_template(body=body, db=_mock_db(), current_user=_fake_user())
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_router_success_returns_201_payload_with_storage_note():
    body = TemplateSeedImportRequest(seed=_make_seed())
    resp = await routers.import_seed_template(body=body, db=_mock_db(), current_user=_fake_user())

    assert resp.status == "draft"
    assert resp.sections_count == 6
    assert resp.storage_note  # 注明单写主表、未双写 template_sections
    assert "template_sections" in resp.storage_note


def test_router_requires_permission_dependency():
    """端点鉴权模式 = 同文件既有 CurrentUser（require_permission('system:access')）。"""
    from app.extensions.auth.middleware import require_permission
    from app.extensions.knowledge_factory.routers import CurrentUser

    anno = routers.import_seed_template.__annotations__["current_user"]
    assert anno is CurrentUser
    dep = require_permission("system:access")
    assert callable(dep)


# ──────────────────────────────────────────────────────────────────────
# 鉴权：无会话 cookie 的裸请求 → 401（get_current_user 链）
# ──────────────────────────────────────────────────────────────────────


def test_import_seed_unauthenticated_returns_401():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.extensions.database import get_db
    from app.extensions.knowledge_factory.routers import router as kf_router

    app = FastAPI()
    app.include_router(kf_router)
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/api/kf/templates/import-seed", json={"seed": {"root_sections_json": {"sections": []}}})
    assert resp.status_code == 401


# ──────────────────────────────────────────────────────────────────────
# 集成冒烟：真实 planning_seed.json（seed_gen 产物，本机无该文件则 skip）
# ──────────────────────────────────────────────────────────────────────


def _load_real_seed():
    import json
    from pathlib import Path

    p = Path(SEED_SPIKE_PATH)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.skipif(_load_real_seed() is None, reason=f"spike seed 不存在: {SEED_SPIKE_PATH}")
@pytest.mark.asyncio
async def test_real_planning_seed_smoke():
    seed = _load_real_seed()
    assert seed["kind"] == "kf_template_seed"

    tpl = await TemplateSeedImportService.import_seed_template(db=_mock_db(), seed=seed, user_id=uuid4())

    sections = tpl.root_sections_json["sections"]
    assert len(sections) == seed["metadata"]["totals"]["chapters"] == 13
    leaves = sum(len(s.get("children", [])) for s in sections)
    assert leaves == seed["metadata"]["totals"]["sections"] == 77
    assert TemplateSeedImportService.count_sections(sections) == 90
    assert tpl.status == "draft"
    assert tpl.name == seed["template"]["name"]
    assert tpl.domain == seed["template"]["domain"]
    assert isinstance(tpl.id, UUID)
