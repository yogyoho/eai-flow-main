"""bank_compile / resolve_targets 矿种选基线单元测试（Phase 2）。"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "skills" / "public" / "geological-report"
sys.path.insert(0, str(SKILL / "scripts"))

import build_output  # noqa: E402

# 样例库基线形状（照 references/depth_targets.json 契约：load_targets 只硬性要求 per_chapter dict）
_BASELINE = {
    "coefficient": 0.6,
    "scale_floor": 0.25,
    "per_signal_penalty": 0.05,
    "missing_table_weight": 8,
    "absolute_floor": 0.4,
    "samples": [],
    "per_chapter": {f"ch{i}": {"median_eff": 900, "median_table_rows": 2, "median_paragraphs": 3} for i in range(1, 11)},
}


def _make_stage(tmp_path):
    stage = tmp_path / "stages" / "exploration.json"
    stage.parent.mkdir(parents=True)
    stage.write_text("{}", encoding="utf-8")
    return stage


def test_normalize_mineral_aliases():
    assert build_output.normalize_mineral("铜") == "copper"
    assert build_output.normalize_mineral("铜银金") == "copper"  # 最早位置胜出：铜(0) < 金(2)
    assert build_output.normalize_mineral("岩金") == "gold"
    assert build_output.normalize_mineral("煤矿") == "coal"
    assert build_output.normalize_mineral("铅锌矿") == "lead_zinc"
    assert build_output.normalize_mineral("铅锌金银") == "lead_zinc"  # 最早位置胜出：铅锌(0) < 金(3)
    assert build_output.normalize_mineral("金银") == "gold"
    assert build_output.normalize_mineral("金矿") == "gold"
    # 负向守卫：「非金属」排除；「金」后接「属」的复合词（金属量/贵金属/多金属）不是矿种名
    assert build_output.normalize_mineral("非金属矿") is None
    assert build_output.normalize_mineral("多金属") is None
    assert build_output.normalize_mineral("贵金属") is None
    assert build_output.normalize_mineral("金属量") is None
    assert build_output.normalize_mineral("萤石") is None  # 词表外
    assert build_output.normalize_mineral("") is None
    assert build_output.normalize_mineral(None) is None


def test_resolve_targets_mineral_dir_precedence(tmp_path, monkeypatch, capsys):
    """样例库基线存在时优先于三级探测与 CANONICAL 兜底；不打非技能基准警告。"""
    stage = _make_stage(tmp_path)
    monkeypatch.setattr(build_output, "CANONICAL_TARGETS", tmp_path / "depth_targets.json")  # 探测路径自动重定向到 tmp
    mineral_file = tmp_path / "depth_targets" / "exploration" / "gold.json"
    mineral_file.parent.mkdir(parents=True)
    mineral_file.write_text(json.dumps(_BASELINE, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text(json.dumps({"commodity": "岩金", "stage": "勘探"}), encoding="utf-8")
    targets, src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets["per_chapter"]["ch1"]["median_eff"] == 900
    assert "gold" in str(src)  # resolve_targets 第二元为 Path
    captured = capsys.readouterr()
    assert "非技能基准" not in captured.err  # 技能自有资产不打非基准警告
    assert "矿种基线缺失" not in captured.err


def test_resolve_targets_mineral_beats_stage_adjacent(tmp_path, monkeypatch, capsys):
    """stage 旁 depth_targets.json 可伪造（bug-3058）——gated 的样例库基线优先于 stage 旁扫描。"""
    stage = _make_stage(tmp_path)
    (stage.parent / "depth_targets.json").write_text(json.dumps({"per_chapter": {"ch1": {"median_eff": 99999}}}), encoding="utf-8")
    monkeypatch.setattr(build_output, "CANONICAL_TARGETS", tmp_path / "depth_targets.json")
    mineral_file = tmp_path / "depth_targets" / "exploration" / "gold.json"
    mineral_file.parent.mkdir(parents=True)
    mineral_file.write_text(json.dumps(_BASELINE), encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text(json.dumps({"commodity": "岩金"}), encoding="utf-8")
    targets, src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets["per_chapter"]["ch1"]["median_eff"] == 900  # mineral 基线胜出，非 stage 旁伪造的 99999
    assert "gold" in str(src)
    captured = capsys.readouterr()
    assert "非技能基准" not in captured.err


def test_resolve_targets_missing_baseline_falls_back(tmp_path, monkeypatch, capsys):
    """矿种命中但基线文件缺失 → stderr 一行提示 + 回退既有探测链/兜底（行为不变）。"""
    stage = _make_stage(tmp_path)
    fake_canonical = tmp_path / "canonical" / "depth_targets.json"  # 可存在的兜底，隔离真实技能目录
    fake_canonical.parent.mkdir(parents=True)
    fake_canonical.write_text(json.dumps({"per_chapter": {"ch1": {"median_eff": 7487}}}), encoding="utf-8")
    monkeypatch.setattr(build_output, "CANONICAL_TARGETS", fake_canonical)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text(json.dumps({"commodity": "岩金"}), encoding="utf-8")
    targets, _src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets is not None  # 兜底（重定向后的 canonical）
    captured = capsys.readouterr()
    assert "矿种基线缺失" in captured.err
    assert "gold" in captured.err


def test_resolve_targets_fallback_unchanged(tmp_path):
    """无矿种/无基线文件时走既有链（data_dir 不存在/词表外），兜底 CANONICAL——向后兼容。"""
    stage = _make_stage(tmp_path)
    data_dir = tmp_path / "data"  # 目录不存在
    targets, _src = build_output.resolve_targets(None, stage, data_dir=data_dir)
    assert targets is not None  # 兜底 CANONICAL（技能自带铜矿基线）


def test_project_mineral_non_dict_json(tmp_path):
    """00_project.json 为非对象 JSON（如 [1,2]）→ .get 抛 AttributeError → 归一化 None（不炸探测链）。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "00_project.json").write_text("[1,2]", encoding="utf-8")
    assert build_output._project_mineral(data_dir) is None


# ---------------------------------------------------------------------------
# bank_compile：样例库 → 技能衍生物（slices / SL3 指纹池 / bank_index / per 矿种基线）
# ---------------------------------------------------------------------------

import bank_compile  # noqa: E402


def _make_report(workdir: Path, rid: str, mineral: str, stage: str) -> None:
    """合成一份含 3 节的报告：## 1 / ## 2 / ### 2.1，正文若干行。"""
    d = workdir / rid
    d.mkdir(parents=True, exist_ok=True)
    text = "## 1 总论\n\n总论正文一段。\n\n## 2 地质特征\n\n地质正文。\n\n### 2.1 地层\n\n地层正文含数字 123.45。\n"
    (d / "source.md").write_text(text, encoding="utf-8")


def _write_manifest(workdir: Path, entries: list[dict]) -> None:
    (workdir / "manifest.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def test_bank_compile_slices_index_and_fingerprints(tmp_path):
    refs = tmp_path / "references"
    refs.mkdir()
    _make_report(tmp_path, "rid-gold", "gold", "exploration")
    _write_manifest(tmp_path, [{"report_id": "rid-gold", "stage": "exploration", "mineral": "gold", "file_name": "g.docx"}])
    rc = bank_compile.main_with_args(["--workdir", str(tmp_path), "--references", str(refs)])
    assert rc == 0
    # 切片落位 + 标记行
    s1 = refs / "samples_bank/exploration/slices/ch1/rid-gold__1.md"
    assert s1.exists()
    body = s1.read_text(encoding="utf-8")
    assert body.startswith("【矿种】gold｜【阶段】exploration｜【report_id】rid-gold｜【节号】1")
    assert "## 1 总论" in body
    # SL3 指纹源副本
    assert (refs / "samples/exploration/ch1__rid-gold.md").exists()
    assert (refs / "samples/exploration/ch2__rid-gold.md").exists()  # ### 2.1 归入 ## 2 片
    # bank_index 结构
    idx = json.loads((refs / "samples_bank/bank_index.json").read_text(encoding="utf-8"))
    assert idx["exploration"]["ch1"][0]["report_id"] == "rid-gold"
    assert idx["exploration"]["ch2"][1]["sec"] == "2.1"
    # per 矿种基线：median 生成 + absolute_floor 落盘
    base = json.loads((refs / "depth_targets/exploration/gold.json").read_text(encoding="utf-8"))
    assert base["absolute_floor"] == 0.4
    assert base["per_chapter"]["ch1"]["median_eff"] > 0


def test_bank_compile_idempotent(tmp_path):
    refs = tmp_path / "references"
    refs.mkdir()
    _make_report(tmp_path, "rid-cu", "copper", "exploration")
    _write_manifest(tmp_path, [{"report_id": "rid-cu", "stage": "exploration", "mineral": "copper", "file_name": "c.docx"}])
    args = ["--workdir", str(tmp_path), "--references", str(refs)]
    assert bank_compile.main_with_args(args) == 0
    idx1 = (refs / "samples_bank/bank_index.json").read_bytes()
    base1 = (refs / "depth_targets/exploration/copper.json").read_bytes()
    assert bank_compile.main_with_args(args) == 0
    assert (refs / "samples_bank/bank_index.json").read_bytes() == idx1
    assert (refs / "depth_targets/exploration/copper.json").read_bytes() == base1


def test_bank_compile_all_zero_slices_rc1(tmp_path):
    refs = tmp_path / "references"
    refs.mkdir()
    d = tmp_path / "rid-bad"
    d.mkdir()
    (d / "source.md").write_text("没有任何节号标题的正文。\n", encoding="utf-8")
    _write_manifest(tmp_path, [{"report_id": "rid-bad", "stage": "exploration", "mineral": "gold", "file_name": "b.docx"}])
    rc = bank_compile.main_with_args(["--workdir", str(tmp_path), "--references", str(refs)])
    assert rc == 1
    assert not (refs / "samples_bank/bank_index.json").exists()  # 绝不产空 index


def test_bank_compile_duplicate_chapter_skips_report(tmp_path, capsys):
    """重复章号（## 1 / ## 2.1 / ## 1 → 两个 ch1 片）→ 整份报告跳过；另一报告正常编译。"""
    refs = tmp_path / "references"
    refs.mkdir()
    d = tmp_path / "rid-dup"
    d.mkdir()
    (d / "source.md").write_text("## 1 甲\n\n甲正文。\n\n## 2.1 乙\n\n乙正文。\n\n## 1 丙\n\n丙正文。\n", encoding="utf-8")
    _make_report(tmp_path, "rid-ok", "gold", "exploration")
    _write_manifest(
        tmp_path,
        [
            {"report_id": "rid-dup", "stage": "exploration", "mineral": "gold", "file_name": "d.docx"},
            {"report_id": "rid-ok", "stage": "exploration", "mineral": "gold", "file_name": "g.docx"},
        ],
    )
    rc = bank_compile.main_with_args(["--workdir", str(tmp_path), "--references", str(refs)])
    assert rc == 0
    assert not (refs / "samples_bank/exploration/slices/ch1/rid-dup__1.md").exists()
    assert not (refs / "samples/exploration/ch1__rid-dup.md").exists()
    idx = json.loads((refs / "samples_bank/bank_index.json").read_text(encoding="utf-8"))
    rids = {e["report_id"] for entries in idx["exploration"].values() for e in entries}
    assert rids == {"rid-ok"}
    assert "重复章号" in capsys.readouterr().err


def test_bank_compile_prune_removes_stale_slices(tmp_path):
    """--prune：manifest 移除的报告残留切片（bank + SL3 池）被清掉，保留报告与手写样例完好。"""
    refs = tmp_path / "references"
    refs.mkdir()
    hand = refs / "samples/exploration/ch1_sample.md"
    hand.parent.mkdir(parents=True, exist_ok=True)
    hand.write_text("手写样例。\n", encoding="utf-8")
    _make_report(tmp_path, "rid-a", "gold", "exploration")
    _make_report(tmp_path, "rid-b", "copper", "exploration")
    _write_manifest(
        tmp_path,
        [
            {"report_id": "rid-a", "stage": "exploration", "mineral": "gold", "file_name": "a.docx"},
            {"report_id": "rid-b", "stage": "exploration", "mineral": "copper", "file_name": "b.docx"},
        ],
    )
    args = ["--workdir", str(tmp_path), "--references", str(refs)]
    assert bank_compile.main_with_args(args) == 0
    assert (refs / "samples_bank/exploration/slices/ch1/rid-b__1.md").exists()
    assert (refs / "samples/exploration/ch1__rid-b.md").exists()
    # manifest 移除 rid-b 后带 --prune 重编译：rid-b 残留被清，rid-a 与手写样例完好
    _write_manifest(tmp_path, [{"report_id": "rid-a", "stage": "exploration", "mineral": "gold", "file_name": "a.docx"}])
    assert bank_compile.main_with_args(args + ["--prune"]) == 0
    assert not (refs / "samples_bank/exploration/slices/ch1/rid-b__1.md").exists()
    assert not (refs / "samples/exploration/ch1__rid-b.md").exists()
    assert (refs / "samples_bank/exploration/slices/ch1/rid-a__1.md").exists()
    assert (refs / "samples/exploration/ch1__rid-a.md").exists()
    assert hand.exists()  # 手写 chN_sample.md 绝不动
    idx = json.loads((refs / "samples_bank/bank_index.json").read_text(encoding="utf-8"))
    rids = {e["report_id"] for entries in idx["exploration"].values() for e in entries}
    assert rids == {"rid-a"}


def test_bank_compile_bad_python_skips_group(tmp_path, capsys):
    """--python 指向不存在解释器 → OSError 被守护：rc=0，切片/索引照常落盘，该组标定跳过 + stderr 警告。"""
    refs = tmp_path / "references"
    refs.mkdir()
    _make_report(tmp_path, "rid-x", "gold", "exploration")
    _write_manifest(tmp_path, [{"report_id": "rid-x", "stage": "exploration", "mineral": "gold", "file_name": "x.docx"}])
    rc = bank_compile.main_with_args(["--workdir", str(tmp_path), "--references", str(refs), "--python", "Z:/no/such/interpreter.exe"])
    assert rc == 0
    assert (refs / "samples_bank/bank_index.json").exists()
    assert not (refs / "depth_targets/exploration/gold.json").exists()  # 该组标定被跳过
    assert "标定失败" in capsys.readouterr().err


def _compile_stub_docs():
    """两份 reviewed 行的桩（SimpleNamespace 即可——编排层只读这几个字段；id 供 get_document_fresh 主键桩）。"""
    from types import SimpleNamespace

    return [
        SimpleNamespace(id="doc-a", report_id="rid-a", stage="exploration", mineral="gold", file_name="a.docx", clean_uri="s3://geo-samples/clean/rid-a/source.md", status="reviewed"),
        SimpleNamespace(id="doc-b", report_id="rid-b", stage="exploration", mineral="gold", file_name="b.docx", clean_uri="s3://geo-samples/clean/rid-b/source.md", status="reviewed"),
    ]


def _patch_compile_happy_path(monkeypatch, tmp_path, docs):
    """编排层公共桩：reviewed 清单 / MinIO 下载 / 子进程 FakeProc / 无 RAGFlow env / fresh 写回桩。返回 (exec_mock, write_back_rows, FakeProc)。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.extensions.geo_samples import service

    wd = tmp_path / "wd"
    wd.mkdir()
    monkeypatch.setattr(service.tempfile, "mkdtemp", lambda prefix="": str(wd))

    async def _list_reviewed(db, stage=None, mineral=None):
        return list(docs)

    write_back_rows = {d.id: SimpleNamespace(id=d.id, report_id=d.report_id, status="reviewed") for d in docs}

    async def _fresh(db, did):
        return write_back_rows[did]

    monkeypatch.setattr(service.crud, "list_reviewed", _list_reviewed)
    monkeypatch.setattr(service.crud, "get_document_fresh", _fresh)
    monkeypatch.setattr(service.crud, "finish_run", AsyncMock())
    monkeypatch.setattr(service.storage, "get_object", lambda uri: b"# x")
    monkeypatch.delenv("GSB_RAGFLOW_DATASET_ID", raising=False)

    class FakeProc:
        returncode = 0
        killed = False

        async def communicate(self):
            return b"", b""

        def kill(self):
            FakeProc.killed = True

        async def wait(self):
            return -9

    async def _fake_exec(*cmd, **kwargs):
        FakeProc.cmd = list(cmd)
        FakeProc.kwargs = kwargs
        return FakeProc()

    exec_mock = AsyncMock(side_effect=_fake_exec)
    monkeypatch.setattr(service.asyncio, "create_subprocess_exec", exec_mock)
    return exec_mock, write_back_rows, FakeProc


def _finish_call(await_args):
    """service._finish_run 以 (db, run_id, status, detail) 全位置参数调 crud.finish_run——取出 (status, detail)。"""
    _args, kwargs = await_args
    return _args[2], (_args[3] if len(_args) > 3 else kwargs.get("detail"))


def test_compile_skill_dir_guard():
    """bug-526 模板守护：模块侧 _SKILL_DIR 必须指向 geological-report 且 bank_compile.py 实存。"""
    from app.extensions.geo_samples import service

    assert service._SKILL_DIR.name == "geological-report"
    assert (service._SKILL_DIR / "scripts" / "bank_compile.py").exists()


@pytest.mark.asyncio
async def test_compile_no_reviewed_fails_fast(monkeypatch):
    """空 reviewed 清单 → failed「无 reviewed」且绝不起子进程。"""
    from unittest.mock import AsyncMock

    from app.extensions.geo_samples import service

    async def _empty(db, stage=None, mineral=None):
        return []

    monkeypatch.setattr(service.crud, "list_reviewed", _empty)
    monkeypatch.setattr(service.crud, "finish_run", AsyncMock())
    exec_mock = AsyncMock()
    monkeypatch.setattr(service.asyncio, "create_subprocess_exec", exec_mock)

    await service.run_compile(AsyncMock(), "run-empty")

    exec_mock.assert_not_awaited()
    status, detail = _finish_call(service.crud.finish_run.await_args)
    assert status == "failed"
    assert "无 reviewed" in (detail or "")


@pytest.mark.asyncio
async def test_compile_invokes_subprocess_and_marks_compiled(tmp_path, monkeypatch):
    """happy path：子进程 cmd 含 bank_compile.py/--workdir；两份 reviewed 行批量 status=compiled；run=done。"""
    from unittest.mock import AsyncMock

    from app.extensions.geo_samples import service

    docs = _compile_stub_docs()
    _exec, rows, FakeProc = _patch_compile_happy_path(monkeypatch, tmp_path, docs)

    await service.run_compile(AsyncMock(), "run-c", "exploration", "gold")

    cmd = FakeProc.cmd
    assert any(str(c).endswith("bank_compile.py") for c in cmd)
    assert "--workdir" in cmd and any(str(c) == str(tmp_path / "wd") for c in cmd)
    assert "--python" in cmd
    assert FakeProc.kwargs.get("cwd") == str(service._SKILL_DIR)
    assert rows["doc-a"].status == "compiled"
    assert rows["doc-b"].status == "compiled"
    service.crud.finish_run.assert_awaited_once()
    status, detail = _finish_call(service.crud.finish_run.await_args)
    assert status == "done"
    assert "slices ok" in (detail or "")
    assert "ragflow skipped" in (detail or "")  # env 未配置 → 明说跳过而非静默


@pytest.mark.asyncio
async def test_compile_subprocess_timeout_marks_failed(tmp_path, monkeypatch):
    """超时加固：wait_for 超时 → kill 子进程 + failed「timeout」（recon risk：模板无超时会挂死 run）。"""
    import asyncio
    from unittest.mock import AsyncMock

    from app.extensions.geo_samples import service

    docs = _compile_stub_docs()
    _exec, _rows, FakeProc = _patch_compile_happy_path(monkeypatch, tmp_path, docs)

    async def _hang(self):
        await asyncio.sleep(30)

    FakeProc.communicate = _hang  # type: ignore[method-assign]
    monkeypatch.setattr(service, "_COMPILE_TIMEOUT_S", 0.05)

    await service.run_compile(AsyncMock(), "run-slow")

    assert FakeProc.killed
    status, detail = _finish_call(service.crud.finish_run.await_args)
    assert status == "failed"
    assert "timeout" in (detail or "")


@pytest.mark.asyncio
async def test_compile_ragflow_push_failure_does_not_fail_run(tmp_path, monkeypatch):
    """RAGFlow 分发是辅助通道（spec §7 降级链）：push 异常 → run 仍 done，detail 记 failed 原因。"""
    from unittest.mock import AsyncMock

    from app.extensions.geo_samples import service

    docs = _compile_stub_docs()
    _exec, _rows, _proc = _patch_compile_happy_path(monkeypatch, tmp_path, docs)
    monkeypatch.setenv("GSB_RAGFLOW_DATASET_ID", "ds1")
    monkeypatch.setattr(service, "push_slices_to_ragflow", AsyncMock(side_effect=RuntimeError("ragflow exploded")))

    await service.run_compile(AsyncMock(), "run-rf")

    status, detail = _finish_call(service.crud.finish_run.await_args)
    assert status == "done"  # 编译产物已落盘，分发失败不回滚结论
    assert "ragflow push failed" in (detail or "")


@pytest.mark.asyncio
async def test_compile_ragflow_push_budget_does_not_fail_run(tmp_path, monkeypatch):
    """quality Important-1：push 超预算（wait_for 封顶）→ run 仍 done，detail 记 budget exceeded——
    编排总寿命恒 < 60min sweep 线，防长尾 RAGFlow 拖过互斥造成并发编译写共享 references。"""
    import asyncio
    from unittest.mock import AsyncMock

    from app.extensions.geo_samples import service

    docs = _compile_stub_docs()
    _exec, _rows, _proc = _patch_compile_happy_path(monkeypatch, tmp_path, docs)
    monkeypatch.setenv("GSB_RAGFLOW_DATASET_ID", "ds1")
    monkeypatch.setattr(service, "_PUSH_BUDGET_S", 0.05)

    async def _long_push(refs, dataset_id):
        await asyncio.sleep(30)

    monkeypatch.setattr(service, "push_slices_to_ragflow", _long_push)

    await service.run_compile(AsyncMock(), "run-budget")

    status, detail = _finish_call(service.crud.finish_run.await_args)
    assert status == "done"  # 超预算与 push 失败同 containment：编译结论不回滚
    assert "budget exceeded" in (detail or "")
    assert "push incomplete" in (detail or "")


@pytest.mark.asyncio
async def test_compile_writeback_skips_drifted_state(tmp_path, monkeypatch):
    """quality Minor-3：在途编译期间状态漂移（非 reviewed）→ 不被覆盖，detail 记 skip；reviewed 行照常 compiled。"""
    from unittest.mock import AsyncMock

    from app.extensions.geo_samples import service

    docs = _compile_stub_docs()
    _exec, rows, _proc = _patch_compile_happy_path(monkeypatch, tmp_path, docs)
    rows["doc-b"].status = "redacted"  # 编译期间被重新解析（他方会话写入）

    await service.run_compile(AsyncMock(), "run-drift")

    assert rows["doc-a"].status == "compiled"  # 仍 reviewed → 正常写回
    assert rows["doc-b"].status == "redacted"  # 漂移者绝不覆盖
    status, detail = _finish_call(service.crud.finish_run.await_args)
    assert status == "done"
    assert "compiled skip (state drifted): rid-b" in (detail or "")


@pytest.mark.asyncio
async def test_compile_ragflow_push_delete_by_name(tmp_path, monkeypatch):
    """push_slices_to_ragflow 直测：分页 list 建 name→id → 同名先 delete → upload → parse（不等解析完成）。"""
    from types import SimpleNamespace

    from app.extensions import config as ext_config_mod
    from app.extensions.geo_samples import service
    from app.extensions.knowledge import client as ragflow_client_mod

    refs = tmp_path / "references"
    slice_dir = refs / "samples_bank" / "exploration" / "slices" / "ch1"
    slice_dir.mkdir(parents=True)
    (slice_dir / "a__1.md").write_text("【矿种】gold｜【节号】1\n\n## 1 总论\n", encoding="utf-8")
    (slice_dir / "b__1.md").write_text("【矿种】gold｜【节号】1\n\n## 1 总论\n", encoding="utf-8")
    index = {
        "exploration": {
            "ch1": [
                {"report_id": "rid-a", "mineral": "gold", "sec": "1", "title": "总论", "file": "samples_bank/exploration/slices/ch1/a__1.md"},
                {"report_id": "rid-b", "mineral": "gold", "sec": "1", "title": "总论", "file": "samples_bank/exploration/slices/ch1/b__1.md"},
            ]
        }
    }
    (refs / "samples_bank" / "bank_index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    class FakeClient:
        init_kwargs: dict = {}
        pages: list = []
        ops: list = []

        def __init__(self, api_key=None, base_url=None):
            FakeClient.init_kwargs = {"api_key": api_key, "base_url": base_url}

        async def list_documents(self, dataset_id, page=1, size=100):
            FakeClient.pages.append((dataset_id, page, size))
            data = {1: {"docs": [{"id": "old-a", "name": "a__1.md"}], "total": 150}, 2: {"docs": [{"id": "old-b", "name": "b__1.md"}], "total": 150}}.get(page)
            if data is None:
                return {"code": 0, "data": {"docs": [], "total": 0}}
            return {"code": 0, "data": data}

        async def delete_document(self, dataset_id, document_id):
            FakeClient.ops.append(("delete", document_id))

        async def upload_document(self, dataset_id, file_path, file_name=None, **kw):
            FakeClient.ops.append(("upload", file_name))
            return {"data": {"id": f"new-{file_name}"}}

        async def parse_document(self, dataset_id, document_id):
            FakeClient.ops.append(("parse", document_id))

    monkeypatch.setattr(ragflow_client_mod, "RAGFlowClient", FakeClient)
    monkeypatch.setattr(ext_config_mod, "get_extensions_config", lambda: SimpleNamespace(ragflow=SimpleNamespace(api_key="k", base_url="http://ragflow:9380", timeout=5)))

    pushed = await service.push_slices_to_ragflow(refs, "ds1")

    assert pushed == 2
    assert FakeClient.pages == [("ds1", 1, 100), ("ds1", 2, 100)]  # total-aware 分页：2 页即停
    assert FakeClient.init_kwargs == {"api_key": "k", "base_url": "http://ragflow:9380"}
    # 每片：同名先 delete → upload（盘上路径+file_name）→ parse；两片顺序稳定
    assert FakeClient.ops == [
        ("delete", "old-a"),
        ("upload", "a__1.md"),
        ("parse", "new-a__1.md"),
        ("delete", "old-b"),
        ("upload", "b__1.md"),
        ("parse", "new-b__1.md"),
    ]


def test_bank_compile_slug_and_utf8_guards_skip(tmp_path, capsys):
    """rid 非 slug / source.md 非 UTF-8 → 条目级 stderr 警告跳过；好报告照常编译。"""
    refs = tmp_path / "references"
    refs.mkdir()
    bad = tmp_path / "RID-BAD"  # 大写 → 非 slug
    bad.mkdir()
    (bad / "source.md").write_text("## 1 甲\n\n正文。\n", encoding="utf-8")
    bin_dir = tmp_path / "rid-bin"
    bin_dir.mkdir()
    (bin_dir / "source.md").write_bytes(b"\xff\xfe## 1 \xb2\xe2\n\n")  # UTF-16 BOM 字节 → 非 UTF-8
    _make_report(tmp_path, "rid-ok", "gold", "exploration")
    _write_manifest(
        tmp_path,
        [
            {"report_id": "RID-BAD", "stage": "exploration", "mineral": "gold", "file_name": "1.docx"},
            {"report_id": "rid-bin", "stage": "exploration", "mineral": "gold", "file_name": "2.docx"},
            {"report_id": "rid-ok", "stage": "exploration", "mineral": "gold", "file_name": "3.docx"},
        ],
    )
    rc = bank_compile.main_with_args(["--workdir", str(tmp_path), "--references", str(refs)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "非 slug" in err
    assert "非 UTF-8" in err
    idx = json.loads((refs / "samples_bank/bank_index.json").read_text(encoding="utf-8"))
    rids = {e["report_id"] for entries in idx["exploration"].values() for e in entries}
    assert rids == {"rid-ok"}


# ---------------------------------------------------------------------------
# geo_bank_ragflow_acceptance：RAGFlow 分块质量验收 harness（Phase 2 T8）
# 脚本在仓库根 scripts/、不在 backend 包内——importlib 按文件路径加载（模块级零 app 依赖，
# RAGFlow 交互经 sys.modules 共享模块 monkeypatch 成 FakeClient，真跑验收由人执行）。
# ---------------------------------------------------------------------------

_ACC_ENV = "GSB_RAGFLOW_ACCEPTANCE_DATASET_ID"
# 长正文（>50 字符）：保证父块断言走「标题+50 字符」严格分支而非放宽分支
_LONG_BODY = "总论正文：矿区位于华北地台南缘，区内地层发育齐全，资源储量估算采用地质块段法，开采方式为地下开采，本节概述供检索召回与深度比对使用。"


def _load_acceptance_module():
    import importlib.util

    script = REPO / "scripts" / "geo_bank_ragflow_acceptance.py"
    spec = importlib.util.spec_from_file_location("geo_bank_ragflow_acceptance", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeAccClient:
    """验收 harness 的 FakeClient：记录 wire ops；chunks 由上传时读到的源文派生（mutate 注入缺陷）。

    缺省 chunk 形态 = 单个含整个源片的父块（理想 parent_child 表现）；mutate[name] 可注入
    变形（表格重复 / 首块缺标记）模拟 RAGFlow 分块缺陷。page_map 模拟既有文档的分页 dataset。
    """

    init_kwargs: dict = {}
    pages: list = []
    ops: list = []
    store: dict = {}  # file_name -> 上传时读到的源片全文
    mutate: dict = {}  # file_name -> callable(src) -> list[str]
    page_map: dict = {}  # page -> {"docs": [...], "total": N}

    def __init__(self, api_key=None, base_url=None):
        FakeAccClient.init_kwargs = {"api_key": api_key, "base_url": base_url}

    async def list_documents(self, dataset_id, page=1, size=100):
        FakeAccClient.pages.append((dataset_id, page, size))
        data = FakeAccClient.page_map.get(page)
        if data is None:
            return {"code": 0, "data": {"docs": [], "total": 0}}
        return {"code": 0, "data": data}

    async def delete_document(self, dataset_id, document_id):
        FakeAccClient.ops.append(("delete", document_id))

    async def upload_document(self, dataset_id, file_path, file_name=None, **kw):
        FakeAccClient.store[file_name] = Path(file_path).read_text(encoding="utf-8")
        FakeAccClient.ops.append(("upload", file_name))
        return {"data": {"id": f"doc::{file_name}"}}

    async def parse_document(self, dataset_id, document_id):
        FakeAccClient.ops.append(("parse", document_id))

    async def get_document(self, dataset_id, document_id):
        FakeAccClient.ops.append(("get_doc", document_id))
        return {"data": {"id": document_id, "run": "DONE", "progress_msg": ""}}

    async def list_chunks(self, dataset_id, document_id, page=1, size=100):
        name = document_id.removeprefix("doc::")
        fn = FakeAccClient.mutate.get(name) or (lambda s: [s])
        contents = fn(FakeAccClient.store[name])
        return {"code": 0, "data": {"chunks": [{"content": c} for c in contents], "total": len(contents)}}

    @classmethod
    def reset(cls):
        cls.init_kwargs, cls.pages, cls.ops, cls.store, cls.mutate, cls.page_map = {}, [], [], {}, {}, {}


def _patch_acc_env(monkeypatch):
    """env dataset id + 懒 import 位点桩（与 test_compile_ragflow_push_delete_by_name 同款手法）。"""
    from types import SimpleNamespace

    from app.extensions import config as ext_config_mod
    from app.extensions.knowledge import client as ragflow_client_mod

    FakeAccClient.reset()
    monkeypatch.setenv(_ACC_ENV, "ds-acc")
    monkeypatch.setattr(ragflow_client_mod, "RAGFlowClient", FakeAccClient)
    monkeypatch.setattr(ext_config_mod, "get_extensions_config", lambda: SimpleNamespace(ragflow=SimpleNamespace(api_key="k", base_url="http://ragflow:9380", timeout=5)))


def _write_acc_slice(root: Path, stage: str, rid: str, mineral: str, ch: str, body: str, table: bool = False, sub: bool = False) -> Path:
    """写一片（标记行 + ## N 标题 + 正文；可选 ### 子节与 md 表格），返回切片路径。"""
    d = root / "samples_bank" / stage / "slices" / f"ch{ch}"
    d.mkdir(parents=True, exist_ok=True)
    marker = f"【矿种】{mineral}｜【阶段】{stage}｜【report_id】{rid}｜【节号】{ch}"
    seg = f"## {ch} 第{ch}节标题\n\n{body}\n"
    if sub:
        seg += f"\n### {ch}.1 地层\n\n地层小节正文。\n"
    if table:
        seg += "\n| 孔号 | 水位 |\n| --- | --- |\n| ZK1 | 12.5 |\n"
    p = d / f"{rid}__{ch}.md"
    p.write_text(marker + "\n\n" + seg, encoding="utf-8", newline="\n")
    return p


def test_acceptance_missing_dataset_env_rc2_no_network(monkeypatch, tmp_path, capsys):
    """缺 GSB_RAGFLOW_ACCEPTANCE_DATASET_ID → rc=2 明确报错，绝不构造 client / 发起任何网络调用。"""
    from app.extensions.knowledge import client as ragflow_client_mod

    mod = _load_acceptance_module()
    monkeypatch.delenv(_ACC_ENV, raising=False)

    class BoomClient:
        def __init__(self, *a, **k):
            raise AssertionError("缺 dataset env 时绝不构造 RAGFlowClient")

    monkeypatch.setattr(ragflow_client_mod, "RAGFlowClient", BoomClient)

    rc = mod.main_with_args(["--bank", str(tmp_path)])

    assert rc == 2
    err = capsys.readouterr().err
    assert _ACC_ENV in err
    assert "生产" in err


def _make_acc_bank(root: Path) -> list[Path]:
    """3 片、2 个 stage（跨 stage 混合按路径排序）：ch2 片含子节 + 表格，其余长正文片。"""
    return [
        _write_acc_slice(root, "exploration", "rid-gold", "gold", "1", _LONG_BODY),
        _write_acc_slice(root, "exploration", "rid-gold", "gold", "2", "地质正文：地层、构造与岩浆岩特征描述。", table=True, sub=True),
        _write_acc_slice(root, "feasibility", "rid-cu", "copper", "3", _LONG_BODY),
    ]


def test_acceptance_happy_path_passes_and_cleans_up(tmp_path, monkeypatch, capsys):
    """3 片 happy path（FakeClient：分页 list / 同名先删 / upload / parse / 轮询 DONE / 达标 chunks）
    → rc=0 全 PASS；默认清理把本脚本上传的 3 份文档全部 delete（验收不留痕）。"""
    mod = _load_acceptance_module()
    paths = _make_acc_bank(tmp_path)
    _patch_acc_env(monkeypatch)
    FakeAccClient.page_map = {
        1: {"docs": [{"id": "old-a", "name": paths[0].name}, {"id": "old-b", "name": "unrelated__9.md"}], "total": 150},
        2: {"docs": [{"id": "old-c", "name": "stale2__2.md"}], "total": 150},
    }

    rc = mod.main_with_args(["--bank", str(tmp_path / "samples_bank")])

    assert rc == 0
    assert "ACCEPTANCE: 3/3 PASS" in capsys.readouterr().out
    assert FakeAccClient.init_kwargs == {"api_key": "k", "base_url": "http://ragflow:9380"}
    assert FakeAccClient.pages == [("ds-acc", 1, 100), ("ds-acc", 2, 100)]  # total-aware 分页两页即停
    # 每片链路：同名先删（上次验收残留）→ upload → parse → 轮询 DONE（首轮即返回）
    assert FakeAccClient.ops[:4] == [
        ("delete", "old-a"),
        ("upload", paths[0].name),
        ("parse", f"doc::{paths[0].name}"),
        ("get_doc", f"doc::{paths[0].name}"),
    ]
    assert FakeAccClient.ops.count(("get_doc", f"doc::{paths[0].name}")) == 1
    assert not any(op == ("delete", "old-b") for op in FakeAccClient.ops)  # 非本脚本上传的残留绝不动
    assert not any(op == ("delete", "old-c") for op in FakeAccClient.ops)
    # 默认清理：结尾按 name 删除本脚本上传的全部 3 份文档
    assert FakeAccClient.ops[-3:] == [("delete", f"doc::{p.name}") for p in paths]


def test_acceptance_table_duplication_detected(tmp_path, monkeypatch, capsys):
    """v0.25.3「md 表格重复」缺陷：chunk 内容令表格行出现 2 倍 → table 项 FAIL、该片 FAIL、rc=1。"""
    mod = _load_acceptance_module()
    p = _write_acc_slice(tmp_path, "exploration", "rid-tbl", "gold", "2", "地质正文：地层描述。", table=True, sub=True)
    _patch_acc_env(monkeypatch)
    FakeAccClient.mutate[p.name] = lambda s: [s, s]  # 整片内容重复 → 每个表格行计数 2 倍

    rc = mod.main_with_args(["--bank", str(tmp_path / "samples_bank")])

    assert rc == 1
    out = capsys.readouterr().out
    assert "表格行计数不符" in out and "重复" in out
    assert "table" in out and "FAIL" in out
    assert "ACCEPTANCE: 0/1 PASS" in out
    assert ("delete", f"doc::{p.name}") in FakeAccClient.ops  # FAIL 后默认清理照常执行


def test_acceptance_table_row_whitespace_compression_still_passes(tmp_path, monkeypatch, capsys):
    """RAGFlow 分块常压缩单元格空格（chunk `| ZK1 |12.5|` vs 源 `| ZK1 | 12.5 |`）——
    行文本空格归一后计数一致，表格项仍 PASS，绝不系统性误报表格 FAIL 误导降级路径。"""
    mod = _load_acceptance_module()
    # 长正文：父块探针（标题后 50 字符）落在未被压缩的正文内，测试只针对表格计数项
    p = _write_acc_slice(tmp_path, "exploration", "rid-ws", "gold", "2", _LONG_BODY, table=True)
    _patch_acc_env(monkeypatch)
    FakeAccClient.mutate[p.name] = lambda s: ["\n".join(ln.replace(" ", "") if ln.lstrip().startswith("|") else ln for ln in s.splitlines())]  # 仅表格行单元格空格被压掉（RAGFlow 压缩场景；不牵连父块探针）

    rc = mod.main_with_args(["--bank", str(tmp_path / "samples_bank")])

    assert rc == 0
    out = capsys.readouterr().out
    assert "ACCEPTANCE: 1/1 PASS" in out
    assert "表格行计数不符" not in out
    assert "行表格逐一计数一致" in out


def test_acceptance_missing_marker_in_first_chunk_fails(tmp_path, monkeypatch, capsys):
    """首块无标记行 → 节号完整性（marker 项）FAIL、rc=1；其余项不受牵连照常评估。"""
    mod = _load_acceptance_module()
    p = _write_acc_slice(tmp_path, "exploration", "rid-nomark", "gold", "1", _LONG_BODY)
    marker_line = p.read_text(encoding="utf-8").splitlines()[0]
    _patch_acc_env(monkeypatch)
    FakeAccClient.mutate[p.name] = lambda s, m=marker_line: [s.replace(m + "\n\n", "", 1)]

    rc = mod.main_with_args(["--bank", str(tmp_path / "samples_bank")])

    assert rc == 1
    out = capsys.readouterr().out
    assert "标记行未出现在拼接文本前" in out
    assert "ACCEPTANCE: 0/1 PASS" in out
    assert "FAIL 处置序" in out  # 处置序提示随 FAIL 输出


def test_acceptance_keep_flag_skips_cleanup(tmp_path, monkeypatch, capsys):
    """--keep：验收照常跑（全 PASS rc=0）但全程零 delete——上传文档保留供人工复查。"""
    mod = _load_acceptance_module()
    p = _write_acc_slice(tmp_path, "exploration", "rid-keep", "gold", "1", _LONG_BODY)
    _patch_acc_env(monkeypatch)  # page_map 空 → 无既有文档 → 也不触发同名先删

    rc = mod.main_with_args(["--bank", str(tmp_path / "samples_bank"), "--keep"])

    assert rc == 0
    assert "ACCEPTANCE: 1/1 PASS" in capsys.readouterr().out
    assert not any(op[0] == "delete" for op in FakeAccClient.ops)
    assert ("upload", p.name) in FakeAccClient.ops


# ---------------------------------------------------------------------------
# title_parser：报告题名解析器（Phase 3 T1，batch-cli）——report_id 自动编码与
# suggest-id 端点共用的后端纯函数。
# ---------------------------------------------------------------------------


def test_parse_title_full_auto():
    from app.extensions.geo_samples import title_parser

    r = title_parser.parse_title("云南省昆明市东川区某铜矿铜银金多金属矿勘探报告")
    assert r["region"] == "云南省昆明市东川区"
    assert r["mineral"] == "copper"
    assert r["stage"] == "exploration"
    assert r["confidence"] == "auto"


def test_parse_title_needs_review_variants():
    from app.extensions.geo_samples import title_parser

    r = title_parser.parse_title("某萤石矿详查报告")  # 词表外矿种
    assert r["stage"] == "detail" and r["mineral"] is None
    assert r["confidence"] == "needs-review"
    r2 = title_parser.parse_title("某岩金矿床地质勘查报告")  # 勘查（泛词）不映射阶段
    assert r2["mineral"] == "gold" and r2["stage"] is None
    assert r2["confidence"] == "needs-review"
    r3 = title_parser.parse_title("无任何规律的文档")
    assert r3["confidence"] == "needs-review"
    assert r3["region"] is None and r3["mineral"] is None and r3["stage"] is None


def test_parse_title_negatives_and_earliest():
    from app.extensions.geo_samples import title_parser

    assert title_parser.parse_title("某非金属矿普查报告")["mineral"] is None
    assert title_parser.parse_title("某铅锌金银多金属勘探报告")["mineral"] == "lead_zinc"  # 铅(0)最早
    assert title_parser.parse_title("某金银矿勘探报告")["mineral"] == "gold"  # 金(1)唯一命中词表


def test_parse_title_region_compound_guard():
    """区划尾字复合词守卫：矿区/城市（及开发区/景区）的尾字跳过继续向前找。"""
    from app.extensions.geo_samples import title_parser

    r = title_parser.parse_title("昆明市东川区矿区一号铜矿勘探报告")
    assert r["region"] == "昆明市东川区"  # 矿区 的 区 被跳过
    r2 = title_parser.parse_title("杭州市城市地质调查报告")
    assert r2["region"] == "杭州市"  # 城市 的 市 被跳过（杭州市 的 市 先命中为合法候选）


def test_parse_title_region_compound_only_yields_none():
    """守卫的 continue 语义：唯一候选是复合词（矿区）→ 跳过后无合法候选 → region None（矿种/阶段不受牵连）。"""
    from app.extensions.geo_samples import title_parser

    r = title_parser.parse_title("矿区一号铜矿勘探报告")
    assert r["region"] is None
    assert r["mineral"] == "copper" and r["stage"] == "exploration"


def test_parse_title_filename_suffix_order():
    """扩展名先于「报告」剥离（batch-cli 直喂文件名）：.docx/.pdf 后缀名照常解析为 auto。"""
    from app.extensions.geo_samples import title_parser

    r = title_parser.parse_title("云南省昆明市东川区某铜矿勘探报告.docx")
    assert r["region"] == "云南省昆明市东川区"
    assert r["mineral"] == "copper" and r["stage"] == "exploration" and r["confidence"] == "auto"
    r2 = title_parser.parse_title("某铅锌矿详查报告.pdf")
    assert r2["mineral"] == "lead_zinc" and r2["stage"] == "detail" and r2["confidence"] == "auto"
