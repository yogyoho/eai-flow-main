"""批二十 M1-d 确定性 20× + CLI oracle 测试(EAI-CUSTOM 2026-11-13)——
spec §8 验收链收口环:20 次独立 run 的报告序列化逐字节相等(绿/红两态);
CLI 退出码 0/1/2 三面 + stdout 为确定性 JSON。"""

from __future__ import annotations

import json

from bid_write_exec_fixtures import green_ctx

from app.extensions.bid_write.executor.cli import main
from app.extensions.bid_write.executor.report import to_report_dict
from app.extensions.bid_write.executor.runner import run_assertions


def _dumps(ctx: dict, skills=None) -> str:
    return json.dumps(to_report_dict(run_assertions(dict(ctx), skills=skills)), sort_keys=True, ensure_ascii=False)


# ── 确定性 20×(spec §8:同输入同输出,零时钟零集合序)────────────────────────


def test_determinism_20x_green_byte_identical():
    base = green_ctx()
    first = _dumps(base)
    assert all(_dumps(green_ctx()) == first for _ in range(20))


def test_determinism_20x_red_byte_identical():
    """短路红态同样字节级一致(红面覆盖排序/短路/镜像分支)。"""
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["legal_rep_name"] = ""
    ctx["tender"]["tender.max_price"] = 1500000
    first = _dumps(ctx)
    assert all(_dumps(ctx) == first for _ in range(20))


# ── CLI oracle 退出码 ────────────────────────────────────────────────────────


def test_cli_exit_0_green(capsys, tmp_path):
    p = tmp_path / "ctx.json"
    p.write_text(json.dumps(green_ctx(), ensure_ascii=False), encoding="utf-8")
    assert main([str(p)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert all(r["status"] == "PASS" for r in out["results"])


def test_cli_exit_1_fail(capsys, tmp_path):
    ctx = green_ctx()
    ctx["products"]["bid_letter"]["slots"]["legal_rep_name"] = ""
    p = tmp_path / "ctx.json"
    p.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    assert main([str(p)]) == 1


def test_cli_exit_2_error_trumps_fail(tmp_path):
    ctx = green_ctx()
    del ctx["products"]  # CtxMissing→ERROR(优先于任何 FAIL)
    p = tmp_path / "ctx.json"
    p.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    assert main([str(p)]) == 2


def test_cli_skills_scope(tmp_path):
    ctx = green_ctx()
    del ctx["products"]["attachment_index"]  # 只打 AI 面(PS-003 四表加总含 bid_letter 信,不能删 BL 面)
    p = tmp_path / "ctx.json"
    p.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    assert main([str(p), "--skills", "PS"]) == 0
