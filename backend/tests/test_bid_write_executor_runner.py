"""批二十 M1 执行器 runner 语义测试(EAI-CUSTOM 2026-11-13)——排序/短路/委托
镜像/CtxMissing/注册完备性/CMN 恒执行(spec §8 执行语义逐条钉)。"""

from __future__ import annotations

import copy

from bid_write_exec_fixtures import get_result, green_ctx, statuses

from app.extensions.bid_write.executor.loader import load_registry
from app.extensions.bid_write.executor.models import RunReport
from app.extensions.bid_write.executor.runner import run_assertions
from app.extensions.bid_write.executor.validators import REGISTRY

# ── 注册完备性(与注册表同步的机器钉)────────────────────────────────────────


def test_registry_covers_all_non_delegate_assertions():
    snap = load_registry()
    missing = [a.id for a in snap.assertions if a.delegates_to is None and a.id not in REGISTRY]
    # Task 2 态:仅 AI+CMN-005 注册;Task 3 全量后本钉收紧为 == []
    covered_skills = {a.skill for a in snap.assertions if a.id in REGISTRY}
    assert not [i for i in missing if i.startswith(("SK-AI-", "SK-CMN-005"))]
    assert covered_skills <= {"AI", "CMN"}


def test_delegate_assertions_not_registered():
    snap = load_registry()
    for a in snap.assertions:
        if a.delegates_to is not None:
            assert a.id not in REGISTRY, f"委托条 {a.id} 不得独立实现(单实现律)"


# ── 全绿基线(AI 技能跑通)──────────────────────────────────────────────────


def test_green_ai_run_all_pass_and_order():
    report = run_assertions(green_ctx(), skills=("AI",))
    assert isinstance(report, RunReport)
    st = statuses(report)
    ids = [r.assertion_id for r in report.results]
    # 报告序:(level_rank, assertion_id)——D0 九条(AI-001/002/003/008/009+CMN-001/003/004/005)→ D1 五条(AI-004..007+CMN-002)
    assert ids == [
        "SK-AI-001", "SK-AI-002", "SK-AI-003", "SK-AI-008", "SK-AI-009",
        "SK-CMN-001", "SK-CMN-003", "SK-CMN-004", "SK-CMN-005",
        "SK-AI-004", "SK-AI-005", "SK-AI-006", "SK-AI-007", "SK-CMN-002",
    ]
    # AI 全绿 + CMN-005 PASS;CMN-001..004 为 Task 3 注册面——基建完备面 ERROR 不短路不静默
    for i in ("SK-AI-001", "SK-AI-002", "SK-AI-003", "SK-AI-004", "SK-AI-005", "SK-AI-006", "SK-AI-007", "SK-AI-008", "SK-AI-009", "SK-CMN-005"):
        assert st[i] == "PASS", i
    for i in ("SK-CMN-001", "SK-CMN-002", "SK-CMN-003", "SK-CMN-004"):
        r = get_result(report, i)
        assert r.status == "ERROR" and r.message.startswith("E-VALIDATOR-MISSING")
    assert report.skills == ("AI",)


def test_delegate_mirror_ai009_from_cmn005():
    report = run_assertions(green_ctx(), skills=("AI",))
    r = get_result(report, "SK-AI-009")
    assert r.source_id == "SK-CMN-005"
    assert r.status == "PASS"
    assert r.human_action == "补记录检索范围/最接近候选(同 SK-CMN-005)"


# ── 短路语义 ─────────────────────────────────────────────────────────────────


def test_d0_fail_short_circuits_skill_only():
    ctx = green_ctx()
    ctx["products"]["attachment_index"]["items"][0]["no"] = "2"  # 与第二行撞号→AI-001 D0 FAIL
    report = run_assertions(ctx, skills=("AI",))
    st = statuses(report)
    assert st["SK-AI-001"] == "FAIL"
    for skipped_id in ("SK-AI-002", "SK-AI-003", "SK-AI-008"):
        r = get_result(report, skipped_id)
        assert r.status == "SKIPPED"
        assert r.skipped_reason == "short_circuit"
        assert r.message.startswith("因 SK-AI-001 失败跳过")
        assert "不代表通过" in r.message
    # CMN 共享层不受 AI 短路影响
    assert st["SK-CMN-005"] == "PASS"


def test_d0_error_short_circuits_same_as_fail():
    ctx = green_ctx()
    del ctx["products"]["attachment_index"]["items"]  # AI-001 CtxMissing→ERROR(D0)
    report = run_assertions(ctx, skills=("AI",))
    st = statuses(report)
    assert st["SK-AI-001"] == "ERROR"
    assert st["SK-AI-002"] == "SKIPPED"
    assert st["SK-AI-008"] == "SKIPPED"


def test_delegate_mirrors_skipped_and_fail_states():
    # CMN-005 FAIL(待补缺负证据)→ AI-009 镜像 FAIL;AI-001 独立 FAIL → 002..008 SKIPPED
    ctx = green_ctx()
    ctx["products"]["attachment_index"]["items"][0]["no"] = "2"
    ctx["products"]["attachment_index"]["pending_items"] = [
        {"item": "安全生产许可证", "status": "待补", "negative_evidence": {}},
    ]
    report = run_assertions(ctx, skills=("AI",))
    st = statuses(report)
    assert st["SK-CMN-005"] == "FAIL"
    r = get_result(report, "SK-AI-009")
    assert r.status == "FAIL"
    assert r.source_id == "SK-CMN-005"


# ── 上下文缺失(E-CTX-MISSING 不得静默)──────────────────────────────────────


def test_missing_products_all_error_face():
    # products 整体缺失:AI-001(D0)CtxMissing→ERROR 视为失败短路 AI 余量;
    # CMN-005 CtxMissing→短路 CMN-002;CMN-001..004 基建面独立 ERROR 不短路
    report = run_assertions({"tender": {}}, skills=("AI",))
    st = statuses(report)
    assert st["SK-AI-001"] == "ERROR"
    assert st["SK-AI-002"] == "SKIPPED"
    assert st["SK-CMN-005"] == "ERROR"
    assert st["SK-AI-009"] == "ERROR"  # 委托镜像
    for i in ("SK-CMN-001", "SK-CMN-003", "SK-CMN-004"):
        assert get_result(report, i).message.startswith("E-VALIDATOR-MISSING")
    assert get_result(report, "SK-CMN-002").status == "SKIPPED"  # 因 SK-CMN-005
    for r in report.results:
        if r.status == "ERROR" and not r.message.startswith("E-VALIDATOR-MISSING"):
            assert r.message.startswith("E-CTX-MISSING:"), r.assertion_id


def test_ctx_missing_counts_as_failure_for_gate_face():
    ctx = green_ctx()
    del ctx["products"]["attachment_index"]
    report = run_assertions(ctx, skills=("AI",))
    # attachment_index 整体缺失 → 该技能断言全 ERROR;AI-009 镜像 CMN-005(仍 PASS)
    st = statuses(report)
    assert st["SK-AI-001"] == "ERROR"
    assert st["SK-CMN-005"] == "PASS"


# ── 范围与恒执行 ─────────────────────────────────────────────────────────────


def test_cmn_always_executes_regardless_of_skills():
    ctx = green_ctx()
    report = run_assertions(ctx, skills=("BL",))
    ids = {r.assertion_id for r in report.results}
    assert "SK-CMN-005" in ids
    assert not any(i.startswith("SK-AI-") for i in ids)
    # BL 校验器 Task 3 才落地:未注册面=运行时兜底 ERROR,不静默
    assert get_result(report, "SK-BL-001").message.startswith("E-VALIDATOR-MISSING")


def test_full_run_skills_none_and_report_shape():
    ctx = green_ctx()
    report = run_assertions(ctx)
    assert report.skills is None
    assert report.schema_version == "1.0.0"
    ids = {r.assertion_id for r in report.results}
    assert {"SK-AI-009", "SK-CMN-005"} <= ids
    # BL/PS/RT 未注册面:全 ERROR(E-VALIDATOR-MISSING),不静默不通过
    st = statuses(report)
    assert st["SK-BL-001"] == "ERROR"
    assert st["SK-PS-003"] == "ERROR"
    assert st["SK-RT-002"] == "ERROR"


def test_run_is_pure_deterministic_within_process():
    ctx = green_ctx()
    frozen = copy.deepcopy(ctx)
    r1 = run_assertions(ctx, skills=("AI",))
    r2 = run_assertions(frozen, skills=("AI",))
    assert [(r.assertion_id, r.status, r.level, r.message) for r in r1.results] == [
        (r.assertion_id, r.status, r.level, r.message) for r in r2.results
    ]
    # ctx 未被执行面篡改(纯函数)
    assert ctx == frozen
