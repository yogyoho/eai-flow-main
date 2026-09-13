"""doc_graph 消解建议打分 + REST 异常映射测试（纯逻辑，无 DB）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-semantic-map-v2-design.md §4。
score_candidates 的 self 圈除契约: 由 SQL 层 id != 目标id 承担（见 test_self_excluded 说明）,
HTTP 级 self 圈除与全链路验证在 test_doc_graph_resolution_rest.py。
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.extensions.ontology.doc_graph.resolver import REVIEW_THRESHOLD
from app.extensions.ontology.doc_graph.service import MergeConflict, ResourceNotFound, score_candidates


def test_exact_and_prefix_first():
    rows = [
        {"id": "1", "etype": "bidder", "norm_name": "山西煤机集团"},
        {"id": "2", "etype": "bidder", "norm_name": "山西煤机集团有限公司"},
        {"id": "3", "etype": "project", "norm_name": "山西煤机集团"},  # 跨 etype 排除
    ]
    out = score_candidates("山西煤机集团有限公司", "bidder", rows, top=5)
    ids = [s["id"] for s in out]
    assert "3" not in ids  # 跨 etype 排除
    assert out[0]["id"] == "2"  # 精确命中（相似度 1.0）排序第一; id=1 前缀 ratio≈0.75 低于阈值被排除
    assert out[0]["similarity"] >= REVIEW_THRESHOLD


def test_below_threshold_excluded():
    rows = [{"id": "1", "etype": "bidder", "norm_name": "太原重工"}]
    assert score_candidates("山西煤机集团", "bidder", rows, top=5) == []


def test_self_excluded():
    """计划原稿此断言与实现语义矛盾（精确同名 → decide_merge 给 similarity 1.0 → 必然入选,
    而 test_exact_and_prefix_first 又要求精确同名候选 id=2 入选——二者不可兼得）。
    契约定案: self 圈除是 SQL 层职责（resolution_suggestions 的 id != 目标id）, 纯函数无 id 信息;
    此处锁定纯函数对"泄漏进来的 self 行"的真实行为: auto_merge / 1.0 原样返回。
    HTTP 级 self 圈除断言在 test_doc_graph_resolution_rest.py::test_resolution_full_flow。"""
    rows = [{"id": "me", "etype": "bidder", "norm_name": "山西煤机集团"}]
    out = score_candidates("山西煤机集团", "bidder", rows, top=5)
    assert len(out) == 1
    assert out[0]["id"] == "me" and out[0]["action"] == "auto_merge" and out[0]["similarity"] == 1.0


def test_top_respected():
    rows = [{"id": str(i), "etype": "bidder", "norm_name": f"山西煤机集团{i}"} for i in range(10)]
    assert len(score_candidates("山西煤机集团0", "bidder", rows, top=3)) <= 3


def test_resource_not_found_is_keyerror():
    """MCP 的 except KeyError 必须照常捕获（子类兼容 → mcp.py 零改动）。"""
    assert issubclass(ResourceNotFound, KeyError)
    with pytest.raises(KeyError):
        raise ResourceNotFound("candidate x 不存在")


def test_merge_conflict_is_runtime_error():
    """MergeConflict 不继承 KeyError——资源存在但状态冲突, MCP 走通用 _err 而非"不存在"分支。"""
    assert issubclass(MergeConflict, RuntimeError) and not issubclass(MergeConflict, KeyError)


def test_error_mapping_three_states():
    """REST 异常映射三态: ResourceNotFound→404(args[0] 无 repr 引号) / IntegrityError→409 / 其他→400。"""
    from app.extensions.ontology.doc_graph.routers import _resolution_http_error

    e404 = _resolution_http_error(ResourceNotFound("candidate x 不存在"))
    assert e404.status_code == 404 and e404.detail == "candidate x 不存在"  # e.args[0], 非 KeyError repr
    e409 = _resolution_http_error(IntegrityError("INSERT INTO dg_merges ...", {}, Exception("ck_dg_merges_no_self_merge")))
    assert e409.status_code == 409 and e409.detail == "自合并或约束冲突"
    e409b = _resolution_http_error(MergeConflict("candidate x 已有合并留痕"))
    assert e409b.status_code == 409 and "留痕" in e409b.detail
    e400 = _resolution_http_error(ValueError("bad input"))
    assert e400.status_code == 400


def test_uuid_guard_malformed_is_404():
    """malformed uuid → 404（无法标识任何资源; 否则 asyncpg CAST DataError 变 500）。"""
    from app.extensions.ontology.doc_graph.routers import _uuid_or_404

    good = "00000000-0000-0000-0000-000000000001"
    assert _uuid_or_404(good, "entity") == good
    with pytest.raises(HTTPException) as ei:
        _uuid_or_404("not-a-uuid", "entity")
    assert ei.value.status_code == 404 and "不存在" in ei.value.detail
