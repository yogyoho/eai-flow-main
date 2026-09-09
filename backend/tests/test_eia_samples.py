"""样例库 kf_samples CRUD / 批量导入幂等 / 场景过滤测试（EAI-CUSTOM: coal-eia v2 BS3 MVP）。

真库语义（sqlite+aiosqlite 内存库 + 真实 SampleService），非 AsyncMock——
upsert 幂等与 scenario 过滤依赖 SQL 行为，mock 无法证明。只建 kf_samples 单表
（users FK 引用表可缺席：SQLite 默认不强制外键），不触发 init_db/migrate_db。
EAI-CUSTOM (2026-09 样例库迁出): 服务自 knowledge_factory 迁至 app.extensions.eia_samples，
本测试随迁改打新模块（原 backend/tests/test_kf_samples.py）。
EAI-CUSTOM (2026-09 二期 BS3 ③④): + 提取流水线（真实小样例 txt/docx 出章节树）与
质检面板（六项逐检查断言）测试。
"""

import json
import zipfile
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.extensions.eia_samples.extract import (
    ExtractSourceError,
    cn_to_int,
    extract_entities,
    extract_outline,
    run_extract,
)
from app.extensions.eia_samples.models import KFSample
from app.extensions.eia_samples.quality import QualityService
from app.extensions.eia_samples.schemas import (
    SampleBatchUpdate,
    SampleBulkImportRequest,
    SampleBulkItem,
    SampleCreate,
    SampleScenario,
    SampleStatus,
    SampleUpdate,
)
from app.extensions.eia_samples.service import SampleHashConflictError, SampleService

SEED_PATH = Path(__file__).resolve().parents[1] / "app" / "extensions" / "eia_samples" / "data" / "kf_samples_seed.json"

# 真实小样例：CRLF 行尾 + 目录区 + 章节跳号(缺3) + 二级节 + 实体 + 正文噪声行
EIA_MINI_SAMPLE = (
    "目  录\r\n"
    "1 总论\t1\r\n"
    "2 项目概况\t2\r\n"
    "4 环境影响预测与评价 4\r\n"
    "5 环境保护措施及其可行性论证\t5\r\n"
    "6 环境管理与监测计划\t6\r\n"
    "7 结论与建议\t7\r\n"
    "\r\n"
    "1 总论\r\n"
    "1.1 项目由来\r\n"
    "本项目为月儿湾矿井及选煤厂新建工程。\r\n"
    "1.2 评价范围\r\n"
    "评价范围为井田边界外延500m。\r\n"
    "2 项目概况\r\n"
    "2.1 基本情况\r\n"
    "哈巴湖国家级自然保护区位于井田西南侧，刘家沟水库为饮用水水源地。\r\n"
    "4 环境影响预测与评价\r\n"
    "4.1 地表沉陷预测\r\n"
    "3 个月内完成招标，2 台考核机组同期建设。\r\n"
    "5 环境保护措施及其可行性论证\r\n"
    "6 环境管理与监测计划\r\n"
    "7 结论与建议\r\n"
)

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _item(**overrides) -> dict:
    base = {
        "title": f"测试样例 {uuid4().hex[:8]}",
        "source_path": "D:/corpus/测试样例.docx",
        "file_hash": uuid4().hex,
        "scenario": "planning_eia",
        "variant": "修编·报批版",
        "status": "parsed",
        "confidence": 0.9,
        "notes": None,
    }
    base.update(overrides)
    return base


def _outline(chapter_nos: tuple[int, ...] = (1, 2, 3), notes: str | None = None) -> dict:
    """构造 outline/v1 形状的提取产物（质检测试用，跳号可由 chapter_nos 控制）。"""
    return {
        "schema": "eia-sample-outline/v1",
        "source_kind": "txt",
        "source_chars": 1234,
        "chapters": [{"no": str(n), "no_int": n, "title": f"第{n}章 测试", "sections": [{"no": f"{n}.1", "title": "小节"}]} for n in chapter_nos],
        "candidates": {"mines": ["月儿湾矿井"], "sensitive": [], "waters": []},
        "notes": notes,
    }


async def _add_raw(db: AsyncSession, **overrides) -> KFSample:
    """绕过 schema 校验直接插行（构造坏数据：非法 scenario/缺失哈希等质检输入）。"""
    data = _item(**overrides)
    row = KFSample(
        title=data["title"],
        source_path=data["source_path"],
        file_hash=data["file_hash"],
        scenario=data["scenario"],
        variant=data.get("variant"),
        status=data["status"],
        confidence=data.get("confidence"),
        notes=data.get("notes"),
        outline_json=data.get("outline_json"),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def json_items() -> list[dict]:
    """种子台账 JSON 条目（同时验证全部条目满足 SampleBulkItem 契约）。"""
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))["items"]


@pytest_asyncio.fixture()
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(KFSample.__table__.create)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ── CRUD ──


@pytest.mark.asyncio
async def test_create_and_get_roundtrip(db):
    data = SampleCreate(**_item(confidence=0.55, notes="n1"))
    sample = await SampleService.create_sample(db, data)
    assert sample.scenario == "planning_eia"
    assert sample.status == "parsed"
    assert sample.confidence == 0.55

    fetched = await SampleService.get_sample(db, sample.id)
    assert fetched is not None and fetched.file_hash == sample.file_hash
    by_hash = await SampleService.get_by_hash(db, sample.file_hash)
    assert by_hash is not None and by_hash.id == sample.id


@pytest.mark.asyncio
async def test_create_duplicate_hash_conflicts(db):
    item = _item()
    await SampleService.create_sample(db, SampleCreate(**item))
    with pytest.raises(SampleHashConflictError):
        await SampleService.create_sample(db, SampleCreate(**_item(file_hash=item["file_hash"], title="同哈希另一条")))


@pytest.mark.asyncio
async def test_update_patch_semantics(db):
    sample = await SampleService.create_sample(db, SampleCreate(**_item()))
    updated = await SampleService.update_sample(db, sample, SampleUpdate(scenario=SampleScenario.PROJECT_EIA_OPENPIT, confidence=0.5))
    assert updated.scenario == "project_eia_openpit"
    assert updated.confidence == 0.5
    assert updated.status == "parsed"  # 未触碰字段保持
    assert updated.title == sample.title


@pytest.mark.asyncio
async def test_delete_removes_row(db):
    sample = await SampleService.create_sample(db, SampleCreate(**_item()))
    await SampleService.delete_sample(db, sample)
    assert await SampleService.get_sample(db, sample.id) is None
    samples, total = await SampleService.list_samples(db)
    assert samples == [] and total == 0


# ── 批量导入幂等 ──


@pytest.mark.asyncio
async def test_bulk_import_seed_then_rerun_is_idempotent(db):
    first = await SampleService.bulk_import(db, SampleService.make_bulk_payload(json_items()))
    assert first == {"created": 29, "updated": 0, "total": 29}

    again = await SampleService.bulk_import(db, SampleService.make_bulk_payload(json_items()))
    assert again == {"created": 0, "updated": 29, "total": 29}

    _, total = await SampleService.list_samples(db, limit=1)
    assert total == 29  # 不产生重复行

    # 覆盖语义：重导入条目字段生效（post_eia 两条姊妹互证）
    samples, _ = await SampleService.list_samples(db, scenario=SampleScenario.POST_EIA, limit=10)
    assert len(samples) == 2 and all(s.status == "parsed" for s in samples)


@pytest.mark.asyncio
async def test_bulk_import_mixed_create_update(db):
    await SampleService.bulk_import(db, SampleService.make_bulk_payload(json_items()[:5]))
    items = json_items()
    items[2] = {**items[2], "status": "converted_failed"}  # 既有哈希 → 覆盖
    result = await SampleService.bulk_import(db, SampleService.make_bulk_payload(items))
    assert result == {"created": 24, "updated": 5, "total": 29}
    target = await SampleService.get_by_hash(db, items[2]["file_hash"])
    assert target is not None and target.status == "converted_failed"


# ── 场景过滤 + 分页 ──


@pytest.mark.asyncio
async def test_scenario_filter_and_pagination(db):
    rows = [
        _item(scenario="planning_eia"),
        _item(scenario="planning_eia"),
        _item(scenario="project_eia_underground"),
        _item(scenario="project_eia_openpit", status="converted"),
    ]
    await SampleService.bulk_import(db, SampleBulkImportRequest(items=[SampleBulkItem.model_validate(r) for r in rows]))

    samples, total = await SampleService.list_samples(db, scenario=SampleScenario.PLANNING_EIA)
    assert total == 2 and {s.scenario for s in samples} == {"planning_eia"}

    samples, total = await SampleService.list_samples(db, scenario=SampleScenario.PROJECT_EIA_OPENPIT, status=SampleStatus.CONVERTED)
    assert total == 1 and samples[0].status == "converted"

    page1, total = await SampleService.list_samples(db, page=1, limit=2)
    page2, _ = await SampleService.list_samples(db, page=2, limit=2)
    assert total == 4
    assert {s.id for s in page1}.isdisjoint({s.id for s in page2}) and len(page2) == 2

    found, total = await SampleService.list_samples(db, search=rows[0]["title"][5:])
    assert total == 1 and found[0].file_hash == rows[0]["file_hash"]


# ── 批量归类 ──


@pytest.mark.asyncio
async def test_batch_update_scenario_status(db):
    await SampleService.bulk_import(db, SampleService.make_bulk_payload(json_items()[:6]))
    samples, _ = await SampleService.list_samples(db, limit=10)
    ids = [s.id for s in samples[:4]]

    updated = await SampleService.batch_update(db, SampleBatchUpdate(ids=ids, scenario=SampleScenario.OTHER, status=SampleStatus.FILENAME_ONLY))
    assert updated == 4
    after, _ = await SampleService.list_samples(db, scenario=SampleScenario.OTHER, limit=10)
    assert {s.id for s in after} == set(ids) and all(s.status == "filename_only" for s in after)


# ── 契约校验 ──


def test_schema_rejects_unknown_scenario_and_bad_values():
    with pytest.raises(ValidationError):
        SampleBulkItem.model_validate(_item(scenario="not_a_scenario"))
    with pytest.raises(ValidationError):
        SampleBulkItem.model_validate(_item(confidence=1.5))
    with pytest.raises(ValidationError):
        SampleBulkItem.model_validate(_item(file_hash="short"))  # <8 字符
    with pytest.raises(ValidationError):
        SampleBatchUpdate(ids=[uuid4()])  # 全空更新被拒


# ── 二期③ 提取流水线：章节大纲（双通道 + CR 归一 + 目录区跳过） ──


def test_cn_to_int_supports_mixed_forms():
    assert cn_to_int("十") == 10
    assert cn_to_int("十三") == 13
    assert cn_to_int("一百零三") == 103
    assert cn_to_int("23") == 23
    assert cn_to_int("甲") is None


def test_extract_outline_dual_channel_toc_skip_and_jump_preserved():
    chapters = extract_outline(EIA_MINI_SAMPLE)
    nos = [c["no"] for c in chapters]
    # 目录区 6 条页码行不重复入树；正文出 1/2/4/5/6/7（源文档真跳号 3 保留，供质检上报）
    assert nos == ["1", "2", "4", "5", "6", "7"]
    assert [c["title"] for c in chapters][:2] == ["总论", "项目概况"]
    assert [(s["no"], s["title"]) for s in chapters[0]["sections"]] == [("1.1", "项目由来"), ("1.2", "评价范围")]
    assert [s["no"] for s in chapters[1]["sections"]] == ["2.1"]
    assert [s["no"] for s in chapters[2]["sections"]] == ["4.1"]


def test_extract_outline_rejects_body_noise_lines():
    text = "1 总论\n\n3 个月内完成招标\n\n2 台考核机组同期建设\n\n2 项目概况\n"
    chapters = extract_outline(text)
    assert [(c["no"], c["title"]) for c in chapters] == [("1", "总论"), ("2", "项目概况")]


def test_normalize_cr_splits_word_page_break():
    r"""bug-3201：Word 分页 Range 导出的 txt，页首开章标题黏在上一页尾 \x0c 后——须归一为行分隔。"""
    text = "图1.7-1 技术工作程序\x0c1 总论\r1.1 项目由来\x0c2 项目概况\r\n2.1 项目组成\n"
    chapters = extract_outline(text)
    assert [(c["no"], c["title"]) for c in chapters] == [("1", "总论"), ("2", "项目概况")]
    assert [s["no"] for s in chapters[0]["sections"]] == ["1.1"]


def test_extract_entities_suffix_candidates():
    ents = extract_entities(EIA_MINI_SAMPLE)
    assert ents["mines"] == ["月儿湾矿井"]
    assert ents["sensitive"] == ["哈巴湖国家级自然保护区"]
    assert ents["waters"] == ["刘家沟水库"]


def _make_docx(path: Path, paragraphs: list[str]) -> None:
    """stdlib 构造最小 .docx（zip + ElementTree 写 word/document.xml）——与提取器同通道。"""
    ET.register_namespace("w", _W_NS)
    doc = ET.Element(f"{{{_W_NS}}}document")
    body = ET.SubElement(doc, f"{{{_W_NS}}}body")
    for text in paragraphs:
        p = ET.SubElement(body, f"{{{_W_NS}}}p")
        r = ET.SubElement(p, f"{{{_W_NS}}}r")
        t = ET.SubElement(r, f"{{{_W_NS}}}t")
        t.text = text
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", ET.tostring(doc, xml_declaration=True, encoding="UTF-8"))


def test_run_extract_txt_end_to_end(tmp_path):
    src = tmp_path / "月儿湾矿井环评报告.txt"
    src.write_text(EIA_MINI_SAMPLE, encoding="utf-8")
    outline = run_extract(str(src), "auto")
    assert outline["source_kind"] == "txt" and outline["source_chars"] > 0
    assert [c["no"] for c in outline["chapters"]] == ["1", "2", "4", "5", "6", "7"]
    assert outline["candidates"]["mines"] == ["月儿湾矿井"]


def test_run_extract_docx_end_to_end(tmp_path):
    src = tmp_path / "样例.docx"
    _make_docx(src, ["1 总论", "1.1 项目由来", "本项目为月儿湾矿井。", "2 项目概况"])
    outline = run_extract(str(src), "docx")
    assert outline["source_kind"] == "docx"
    assert [c["no"] for c in outline["chapters"]] == ["1", "2"]
    assert [s["title"] for s in outline["chapters"][0]["sections"]] == ["项目由来"]


def test_run_extract_doc_rejected_with_guidance(tmp_path):
    src = tmp_path / "旧样例.doc"
    src.write_bytes(b"\xd0\xcf\x11\xe0ole")  # OLE 魔数
    with pytest.raises(ExtractSourceError) as ei:
        run_extract(str(src), "auto")
    assert "doc_convert" in str(ei.value)


def test_run_extract_missing_file_rejected():
    with pytest.raises(ExtractSourceError) as ei:
        run_extract("D:/不存在/样例.txt", "auto")
    assert "源文件不存在" in str(ei.value)


@pytest.mark.asyncio
async def test_save_outline_persists_and_upgrades_status(db, tmp_path):
    src = tmp_path / "样例.txt"
    src.write_text(EIA_MINI_SAMPLE, encoding="utf-8")
    sample = await _add_raw(db, source_path=str(src), status="filename_only")
    outline = run_extract(sample.source_path, "auto")
    saved = await SampleService.save_outline(db, sample, outline)
    assert saved.outline_json["schema"] == "eia-sample-outline/v1"
    assert len(saved.outline_json["chapters"]) == 6
    assert saved.status == "parsed"  # 仅登记 → 提取成功升级

    # 已是 parsed 的样例保持；无章节的提取不触发升级
    sample2 = await _add_raw(db, status="converted")
    await SampleService.save_outline(db, sample2, {**outline, "chapters": []})
    assert sample2.status == "converted"


# ── 二期④ 质检面板：六项逐检查断言 ──


def _by_check(checks: list[dict]) -> dict[str, dict]:
    return {c["check"]: c for c in checks}


@pytest.mark.asyncio
async def test_quality_all_pass_for_clean_sample(db):
    sample = await _add_raw(db, outline_json=_outline((1, 2, 3)))
    checks = QualityService.run_checks(sample, await QualityService.title_counts(db))
    by = _by_check(checks)
    assert by["file_hash"]["result"] == "pass"
    assert by["content_outline"]["result"] == "pass"
    assert by["scenario_enum"]["result"] == "pass"
    assert by["duplicate_title"]["result"] == "pass"
    assert by["privacy_scan"]["result"] == "pass"
    assert by["chapter_numbering"]["result"] == "pass"
    assert QualityService.score_of(checks) == 100


@pytest.mark.asyncio
async def test_quality_file_hash_missing_fail_and_malformed_warn(db):
    missing = await _add_raw(db, file_hash="")
    checks = QualityService.run_checks(missing, {})
    assert _by_check(checks)["file_hash"]["result"] == "fail"

    bad = await _add_raw(db, file_hash="zzzz-not-hex!")
    checks = QualityService.run_checks(bad, {})
    assert _by_check(checks)["file_hash"]["result"] == "warn"


@pytest.mark.asyncio
async def test_quality_scenario_enum_invalid_fails(db):
    sample = await _add_raw(db, scenario="not_a_scenario")
    checks = QualityService.run_checks(sample, {})
    c = _by_check(checks)["scenario_enum"]
    assert c["result"] == "fail" and "not_a_scenario" in c["detail"]


@pytest.mark.asyncio
async def test_quality_duplicate_title_warns(db):
    await _add_raw(db, title="同名报告")
    dup = await _add_raw(db, title="同名报告")
    checks = QualityService.run_checks(dup, await QualityService.title_counts(db))
    c = _by_check(checks)["duplicate_title"]
    assert c["result"] == "warn" and "2 条同题" in c["detail"]


@pytest.mark.asyncio
async def test_quality_privacy_scan_hits_and_masks(db):
    id_no, phone = "11010119900307861X", "13812345678"
    sample = await _add_raw(db, notes=f"联系人材料：身份证 {id_no}，电话 {phone}", outline_json=_outline())
    checks = QualityService.run_checks(sample, {})
    c = _by_check(checks)["privacy_scan"]
    assert c["result"] == "fail"
    assert id_no not in c["detail"] and phone not in c["detail"]  # detail 脱敏
    assert "身份证" in c["detail"] and "手机号" in c["detail"]


@pytest.mark.asyncio
async def test_quality_privacy_scan_unknown_without_data(db):
    sample = await _add_raw(db)  # 无 outline_json 无 notes
    checks = QualityService.run_checks(sample, {})
    by = _by_check(checks)
    assert by["privacy_scan"]["result"] == "unknown"
    assert by["content_outline"]["result"] == "unknown"
    assert by["chapter_numbering"]["result"] == "unknown"


@pytest.mark.asyncio
async def test_quality_chapter_numbering_jump_and_continuity(db):
    jump = await _add_raw(db, outline_json=_outline((1, 2, 4, 5)))
    c = _by_check(QualityService.run_checks(jump, {}))["chapter_numbering"]
    assert c["result"] == "warn" and "3" in c["detail"]

    ok = await _add_raw(db, outline_json=_outline((1, 2, 3, 4, 5)))
    assert _by_check(QualityService.run_checks(ok, {}))["chapter_numbering"]["result"] == "pass"


@pytest.mark.asyncio
async def test_quality_score_weighted_between_bounds(db):
    sample = await _add_raw(db, outline_json=_outline((1, 2, 4, 5)), notes="身份证 11010119900307861X")
    checks = QualityService.run_checks(sample, await QualityService.title_counts(db))
    score = QualityService.score_of(checks)
    assert 0 <= score < 100  # 有 warn(跳号)+fail(隐私) 拉低
    assert QualityService.worst_result(checks) == "fail"


@pytest.mark.asyncio
async def test_quality_summary_aggregates_library(db):
    await _add_raw(db, outline_json=_outline((1, 2, 3)), scenario="planning_eia")
    await _add_raw(db, outline_json=_outline((1, 2, 4, 5)), scenario="planning_eia")
    await _add_raw(db, notes="身份证 11010119900307861X", outline_json=_outline(), scenario="other")

    summary = await QualityService.summarize(db, items_limit=50)
    assert summary["total"] == 3
    assert set(summary["by_result"]) == {"pass", "warn", "fail", "unknown"}
    assert sum(summary["by_result"].values()) == 18  # 3 样例 × 6 检查项
    assert summary["by_scenario"]["planning_eia"]["samples"] == 2
    assert summary["by_scenario"]["other"]["samples"] == 1
    assert len(summary["items"]) == 3
    # 最差优先：含隐私 fail 的样例排第一
    assert summary["items"][0]["worst_result"] == "fail"
    assert summary["items"][0]["problems"]
    scores = [it["score"] for it in summary["items"]]
    assert scores == sorted(scores)
