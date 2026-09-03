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


# ---------------------------------------------------------------------------
# suggest-id 端点（Phase 3 T2，batch-cli）：题名解析 → 结构化 report_id + 同组序号顺延。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_id_dedup_bump(monkeypatch):
    """同组已有 gsb-kc-cu-0007 → 建议 0008；解析失败 → gsb-auto-NNNN。"""
    from unittest.mock import MagicMock

    from app.extensions.geo_samples import routers

    async def fake_next(db, prefix):
        return f"{prefix}-0008" if prefix == "gsb-kc-cu" else f"{prefix}-0002"

    monkeypatch.setattr(routers.crud, "next_report_id", fake_next)
    r1 = await routers.suggest_id_impl(MagicMock(), "云南省昆明市东川区某铜矿勘探报告")
    assert r1["report_id"] == "gsb-kc-cu-0008" and r1["confidence"] == "auto"
    r2 = await routers.suggest_id_impl(MagicMock(), "无任何规律的文档")
    assert r2["report_id"].startswith("gsb-auto-") and r2["confidence"] == "needs-review"


@pytest.mark.asyncio
async def test_next_report_id_bumps_max(tmp_path):
    """next_report_id 从 LIKE 前缀行取最大序号 +1（真实 SQLite 会话，模式同 identity-map 测试）。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.extensions.geo_samples import crud
    from app.extensions.geo_samples.models import GsbDocument

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "t.db"))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        # 偏离 plan 字面（Base.metadata.create_all）：共享 Base 里的 report_projects 表
        # 外键指向本进程未导入的 extraction_templates → create_all 在 DDL 排序时抛
        # NoReferencedTableError。照 identity-map 测试只建本表（controller 注明模式同其写法）。
        await conn.run_sync(lambda sync_conn: GsbDocument.__table__.create(sync_conn, checkfirst=True))
    async with maker() as db:
        # gsb-kc-cu-0007-old：非数字尾段钉死「跳过不计入 max」（crud docstring 声明的行为锁进测试）
        for rid in ("gsb-kc-cu-0001", "gsb-kc-cu-0003", "gsb-kc-cu-0007-old", "gsb-auto-0001"):
            db.add(GsbDocument(id=rid, report_id=rid, file_name="a.docx", file_hash="h" + rid, file_type="docx", status="uploaded", raw_uri=f"s3://geo-samples/raw/{rid}/a.docx"))
        await db.commit()
        assert await crud.next_report_id(db, "gsb-kc-cu") == "gsb-kc-cu-0004"
        assert await crud.next_report_id(db, "gsb-xc") == "gsb-xc-0001"  # 无同行新组从 0001 起
    await engine.dispose()


# ---------------------------------------------------------------------------
# count_documents（Phase 3 T4，batch-cli）：list_documents 响应 total 的来源，
# 前端分页控件消费。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_documents_filters(tmp_path):
    """count_documents 与 list_documents 同三过滤：全量 4、stage=exploration 3、stage+status 组合 2。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.extensions.geo_samples import crud
    from app.extensions.geo_samples.models import GsbDocument

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "t.db"))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        # 定点建表（勿 Base.metadata.create_all——共享 Base 的跨模块 FK 在 DDL 排序时炸，同 test_next_report_id_bumps_max）
        await conn.run_sync(lambda sync_conn: GsbDocument.__table__.create(sync_conn, checkfirst=True))
    async with maker() as db:
        rows = [
            ("a", "exploration", "copper", "reviewed"),
            ("b", "exploration", "gold", "reviewed"),
            ("c", "exploration", "copper", "uploaded"),
            ("d", "survey", "copper", "uploaded"),
        ]
        for rid, stage, mineral, status in rows:
            db.add(GsbDocument(id=rid, report_id=rid, file_name="a.docx", file_hash="h" + rid, file_type="docx", stage=stage, mineral=mineral, status=status, raw_uri=f"s3://geo-samples/raw/{rid}/a.docx"))
        await db.commit()
        assert await crud.count_documents(db) == 4
        assert await crud.count_documents(db, stage="exploration") == 3
        assert await crud.count_documents(db, stage="exploration", status="reviewed") == 2
        assert await crud.count_documents(db, mineral="gold") == 1  # 其余两过滤可独立组合
    await engine.dispose()


# ---------------------------------------------------------------------------
# DELETE /documents/{id}（Phase 3 T3，batch-cli）：守卫时序 404→compiled 409→
# running 409→MinIO 三 uri best-effort 尽删→行删；审计流水（无 FK）保留。
# ---------------------------------------------------------------------------


def _delete_doc(status, raw=None, work=None, clean=None):
    from app.extensions.geo_samples.models import GsbDocument

    return GsbDocument(id="d1", report_id="r1", file_name="a.docx", file_hash="h", file_type="docx", status=status, parse_mode="docx", raw_uri=raw, work_uri=work, clean_uri=clean)


async def _run_delete_route(monkeypatch, doc, running=()):
    """桩件直调 DELETE 端点实现；返回 (HTTPException|None, 操作流水, 响应|None)。

    流水元素："obj"/uri（MinIO 删除）与 "row"/document_id（行删除）——None uri 必不出现 obj 项。
    """
    from unittest.mock import MagicMock

    from app.extensions.geo_samples import routers

    deleted = []

    async def _get(db, did):
        return doc

    async def _running(db, did, rt):
        return rt in running

    async def _del_row(db, did):
        deleted.append(("row", did))

    async def _sweep(db, max_age_minutes=60):
        return 0

    monkeypatch.setattr(routers.crud, "get_document", _get)
    monkeypatch.setattr(routers.crud, "has_running_run", _running)
    monkeypatch.setattr(routers.crud, "delete_document", _del_row)
    monkeypatch.setattr(routers.crud, "sweep_stale_runs", _sweep)
    monkeypatch.setattr(routers.storage, "delete_object_by_uri", lambda uri: deleted.append(("obj", uri)))
    err = result = None
    try:
        result = await routers.delete_document("d1", db=MagicMock())
    except routers.HTTPException as exc:
        err = exc
    return err, deleted, result


@pytest.mark.asyncio
async def test_delete_document_missing_404(monkeypatch):
    """守卫①：文档不存在 → 404，且不触碰任何删除。"""
    err, deleted, _ = await _run_delete_route(monkeypatch, None)
    assert err is not None and err.status_code == 404
    assert deleted == []


@pytest.mark.asyncio
async def test_delete_document_compiled_blocked(monkeypatch):
    """守卫②：compiled → 409（编译产物在技能 references，回收机制未设计——spec §5.3）。"""
    err, deleted, _ = await _run_delete_route(monkeypatch, _delete_doc("compiled"))
    assert err is not None and err.status_code == 409
    assert deleted == []  # 守卫先于任何删除动作


@pytest.mark.asyncio
async def test_delete_document_running_blocked(monkeypatch):
    """守卫③：parse 或 redact 任一在跑 → 409（互斥闸门复用 has_running_run，防删到写一半的产物）。"""
    for rt in ("parse", "redact"):
        err, deleted, _ = await _run_delete_route(monkeypatch, _delete_doc("parsed"), running={rt})
        assert err is not None and err.status_code == 409, rt
        assert deleted == []


@pytest.mark.asyncio
async def test_delete_document_happy_path(monkeypatch):
    """成功路径：raw/work 两对象尽删（clean=None 跳过）+ 行删；响应含 report_id。"""
    err, deleted, result = await _run_delete_route(
        monkeypatch,
        _delete_doc("parsed", raw="s3://geo-samples/raw/r1/a.docx", work="s3://geo-samples/work/r1/parsed.md"),
    )
    assert err is None
    assert result == {"deleted": True, "report_id": "r1"}
    assert ("obj", "s3://geo-samples/raw/r1/a.docx") in deleted
    assert ("obj", "s3://geo-samples/work/r1/parsed.md") in deleted
    assert ("row", "d1") in deleted
    assert len([e for e in deleted if e[0] == "obj"]) == 2  # clean_uri=None 被跳过，绝无第三个 obj
    assert len([e for e in deleted if e[0] == "row"]) == 1


def test_delete_object_by_uri_prefix_mismatch(monkeypatch):
    """storage 直测：非 geo-samples 前缀 → 直接忽略，绝不触碰 MinIO（防误删他桶对象）。"""
    from unittest.mock import MagicMock

    from app.extensions.geo_samples import storage

    client = MagicMock()
    monkeypatch.setattr(storage, "_client", lambda: client)

    storage.delete_object_by_uri("s3://other-bucket/x")

    client.remove_object.assert_not_called()


def test_delete_object_by_uri_s3error_swallowed(monkeypatch, caplog):
    """storage 直测：remove_object 抛 S3Error → 吞掉不上抛 + warning 一条（销毁路径失败不零痕迹）。"""
    import logging
    from unittest.mock import MagicMock

    from minio.error import S3Error

    from app.extensions.geo_samples import storage

    client = MagicMock()
    # minio 7.2.20 实际签名：(response, code, message, resource, request_id, host_id, …)——response 居首
    client.remove_object.side_effect = S3Error(MagicMock(), "NoSuchKey", "boom", "res", "rid", "hid")
    monkeypatch.setattr(storage, "_client", lambda: client)

    with caplog.at_level(logging.WARNING, logger="geo_samples.storage"):
        storage.delete_object_by_uri("s3://geo-samples/raw/r1/a.docx")

    client.remove_object.assert_called_once_with("geo-samples", "raw/r1/a.docx")
    assert any("delete_object_by_uri failed" in r.getMessage() for r in caplog.records)


# --- upload 端点直测：defer_parse（batch-cli P4 T1, spec 2026-09-04）-----------


def _upload_file(name="样例.docx", data=b"docx-bytes"):
    import io

    from fastapi import UploadFile

    return UploadFile(file=io.BytesIO(data), filename=name)


async def _run_upload_route(monkeypatch, defer=None):
    """桩件直调 POST /documents/upload 端点实现（同 _run_delete_route 直调模式）。

    defer=None → 按签名声明缺省（模拟 FastAPI 解析 Form(False)）；defer=True → defer_parse=True
    （FastAPI 层的 "true"→bool 解析不在此测）。返回 (HTTPException|None, 响应|None, db,
    background, create_run, run_parse, create_document 捕获的 kwargs)。
    """
    import inspect
    from datetime import datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import BackgroundTasks

    from app.extensions.geo_samples import routers
    from app.extensions.geo_samples.models import GsbDocument

    created = {}
    create_run = AsyncMock(return_value=SimpleNamespace(id="run-1"))
    run_parse = AsyncMock()

    async def _by_report_id(db, rid):
        return None

    async def _dup(db, digest, exclude_uri):
        return None

    async def _create_doc(db, **kw):
        created.update(kw)
        # created_at 必须显式给：未 flush 的 ORM 实例 server_default 未生效，DocumentOut 会炸
        return GsbDocument(id="d1", status="uploaded", created_at=datetime(2026, 9, 4), **kw)

    monkeypatch.setattr(routers.crud, "get_document_by_report_id", _by_report_id)
    monkeypatch.setattr(routers.crud, "find_duplicate_document", _dup)
    monkeypatch.setattr(routers.crud, "create_document", _create_doc)
    monkeypatch.setattr(routers.crud, "create_run", create_run)
    monkeypatch.setattr(routers.service, "run_parse", run_parse)
    monkeypatch.setattr(routers.storage, "put_raw", lambda rid, name, data: f"s3://geo-samples/raw/{rid}/{name}")

    db = MagicMock()
    background = BackgroundTasks()
    kwargs = dict(file=_upload_file(), report_id="gsb-kc-cu-0001", stage="exploration", mineral="copper", year=None, region=None, db=db)
    if defer is None:
        # 直调绕过 FastAPI：缺省时形参绑定的是 Form(False) Dependant 对象（truthy！），非 False。
        # 此处模拟 FastAPI 的缺省解析（取 Form(...).default），并顺带锁死「声明缺省必须是 False」契约。
        declared = inspect.signature(routers.upload_document).parameters["defer_parse"].default
        resolved = getattr(declared, "default", declared)
        assert resolved is False, f"defer_parse 声明缺省漂移为 {resolved!r}——即改批量导入行为，须回归 Task 3 parse-batch 契约"
        kwargs["defer_parse"] = resolved
    else:
        kwargs["defer_parse"] = defer
    err = result = None
    try:
        result = await routers.upload_document(background=background, **kwargs)
    except routers.HTTPException as exc:
        err = exc
    return err, result, db, background, create_run, run_parse, created


@pytest.mark.asyncio
async def test_upload_defer_parse_skips_run(monkeypatch):
    """defer_parse=true：落行+raw 上传，但不 create_run、不起后台任务、响应无 run_id 键。"""
    import hashlib

    err, result, _db, background, create_run, run_parse, created = await _run_upload_route(monkeypatch, defer=True)
    assert err is None
    create_run.assert_not_awaited()
    run_parse.assert_not_awaited()
    assert background.tasks == []  # add_task 未被调
    assert "run_id" not in result  # 省略键（非 null）——CLI .get 已容忍
    assert result["document"]["status"] == "uploaded"
    assert result["document"]["id"] == "d1"
    assert created["report_id"] == "gsb-kc-cu-0001"
    assert created["raw_uri"] == "s3://geo-samples/raw/gsb-kc-cu-0001/样例.docx"
    assert created["file_hash"] == hashlib.sha256(b"docx-bytes").hexdigest()


@pytest.mark.asyncio
async def test_upload_immediate_parse_regression(monkeypatch):
    """回归：defer_parse 缺省（false）→ create_run 一次 + 后台任务入队 + 响应含 run_id。"""
    err, result, db, background, create_run, run_parse, _created = await _run_upload_route(monkeypatch)
    assert err is None
    create_run.assert_awaited_once()
    assert create_run.await_args.args == (db, "d1", "parse")
    assert len(background.tasks) == 1
    task = background.tasks[0]
    assert task.func is run_parse
    assert task.args == (db, "d1", "run-1")
    run_parse.assert_not_awaited()  # 端点只入队，不在请求内执行
    assert result["run_id"] == "run-1"
    assert result["document"]["status"] == "uploaded"


# --- parse-batch 端点 + list_uploaded（batch-cli P4 T3，spec 2026-09-04）-------
# defer_parse 上传行（status=uploaded、无 run）的受控启动：POST /documents/parse-batch
# 按 created_at asc 取前 N 行逐行建 parse run + 后台任务；N≤20（Query le）即天然并发闸。


@pytest.mark.asyncio
async def test_list_uploaded_asc_limit(tmp_path):
    """list_uploaded：仅 status=uploaded 行、created_at asc（先传先跑 FIFO）、limit 截断。"""
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.extensions.geo_samples import crud
    from app.extensions.geo_samples.models import GsbDocument

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "t.db"))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        # 定点建表（勿 Base.metadata.create_all——共享 Base 的跨模块 FK 在 DDL 排序时炸，同 test_next_report_id_bumps_max）
        await conn.run_sync(lambda sync_conn: GsbDocument.__table__.create(sync_conn, checkfirst=True))
    async with maker() as db:
        rows = [
            ("up-early", "r-early", "uploaded", datetime(2026, 9, 1, 12, tzinfo=UTC)),
            ("parsed-mid", "r-parsed", "parsed", datetime(2026, 9, 1, 13, tzinfo=UTC)),
            ("up-late", "r-late", "uploaded", datetime(2026, 9, 1, 14, tzinfo=UTC)),
        ]
        for rid, rpt, status, created in rows:
            db.add(GsbDocument(id=rid, report_id=rpt, file_name="a.docx", file_hash="h" + rid, file_type="docx", status=status, raw_uri=f"s3://geo-samples/raw/{rpt}/a.docx", created_at=created))
        await db.commit()
        got = await crud.list_uploaded(db, limit=10)
        assert [r.id for r in got] == ["up-early", "up-late"]  # parsed 行被滤掉，uploaded 升序
        assert [r.id for r in await crud.list_uploaded(db, limit=1)] == ["up-early"]  # limit 截断取最旧
    await engine.dispose()


def test_parse_batch_limit_query_contract():
    """并发闸契约锁死：limit=Query(5, ge=1, le=20)——le=20 即天然并发上限（不另设信号量）；
    漂移即改触发风暴语义（defer 1000 行分 50 批的前提），须回归 Task 3 契约。"""
    import inspect

    from fastapi import params

    from app.extensions.geo_samples import routers

    q = inspect.signature(routers.parse_batch).parameters["limit"].default
    assert isinstance(q, params.Query)
    assert q.default == 5
    # pydantic v2 形态：约束以 Ge/Le 注解类型挂在 FieldInfo.metadata，非 .ge/.le 属性
    assert [m.ge for m in q.metadata if hasattr(m, "ge")] == [1]
    assert [m.le for m in q.metadata if hasattr(m, "le")] == [20]


async def _run_parse_batch(monkeypatch, docs, running=frozenset()):
    """桩件直调 POST /documents/parse-batch 端点实现（同 _run_delete_route 直调模式）。

    running：视为已有 running parse run 的 document_id 集合（行级守卫的桩输入）。
    返回 (db, background, create_run, run_parse, sweep 次数, 响应|None, HTTPException|None)。
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import BackgroundTasks

    from app.extensions.geo_samples import routers

    sweeps = []
    running_set = set(running)

    async def _sweep(db, max_age_minutes=60):
        sweeps.append(1)
        return 0

    async def _list_uploaded(db, limit):
        return list(docs)

    async def _has_running(db, did, rt):
        return did in running_set and rt == "parse"

    runs = [SimpleNamespace(id=f"run-{i + 1}") for i in range(len(docs))]
    create_run = AsyncMock(side_effect=runs)
    run_parse = AsyncMock()

    monkeypatch.setattr(routers.crud, "sweep_stale_runs", _sweep)
    monkeypatch.setattr(routers.crud, "list_uploaded", _list_uploaded)
    monkeypatch.setattr(routers.crud, "has_running_run", _has_running)
    monkeypatch.setattr(routers.crud, "create_run", create_run)
    monkeypatch.setattr(routers.service, "run_parse", run_parse)

    db = MagicMock()
    background = BackgroundTasks()
    err = result = None
    try:
        result = await routers.parse_batch(background=background, limit=5, db=db)
    except routers.HTTPException as exc:
        err = exc
    return db, background, create_run, run_parse, sweeps, result, err


@pytest.mark.asyncio
async def test_parse_batch_endpoint_schedules(monkeypatch):
    """两行 uploaded → sweep 先行 + 逐行 create_run("parse") + 后台 run_parse 入队 + scheduled/ids 有序。"""
    from types import SimpleNamespace

    docs = [SimpleNamespace(id="doc-a"), SimpleNamespace(id="doc-b")]
    db, background, create_run, run_parse, sweeps, result, err = await _run_parse_batch(monkeypatch, docs)
    assert err is None
    assert sum(sweeps) == 1  # 模块自愈惯例：sweep_stale_runs 先行
    assert create_run.await_count == 2
    assert [c.args for c in create_run.await_args_list] == [(db, "doc-a", "parse"), (db, "doc-b", "parse")]
    assert result == {"scheduled": 2, "ids": ["run-1", "run-2"], "skipped_running": 0}
    assert len(background.tasks) == 2
    assert all(t.func is run_parse for t in background.tasks)
    assert [t.args for t in background.tasks] == [(db, "doc-a", "run-1"), (db, "doc-b", "run-2")]
    run_parse.assert_not_awaited()  # 端点只入队，不在请求内执行


@pytest.mark.asyncio
async def test_parse_batch_zero_rows(monkeypatch):
    """零 defer 行 → {"scheduled": 0, "ids": []}，不 404、不建 run、不入队。"""
    _db, background, create_run, _run_parse, _sweeps, result, err = await _run_parse_batch(monkeypatch, [])
    assert err is None
    assert result == {"scheduled": 0, "ids": [], "skipped_running": 0}
    create_run.assert_not_awaited()
    assert background.tasks == []


@pytest.mark.asyncio
async def test_parse_batch_skips_running_parse(monkeypatch):
    """行级守卫（P4-T3 quality）：某行已有 running parse（上批调度仍在跑）→ 跳过而非 409
    （批处理语义）——不建重复 run、不重复 OCR；scheduled/ids 只计实际调度的行，
    skipped_running 计跳过数（加键不改键，向后兼容）。"""
    from types import SimpleNamespace

    docs = [SimpleNamespace(id="doc-a"), SimpleNamespace(id="doc-b")]
    db, background, create_run, run_parse, _sweeps, result, err = await _run_parse_batch(monkeypatch, docs, running={"doc-a"})
    assert err is None
    assert create_run.await_count == 1
    assert create_run.await_args.args == (db, "doc-b", "parse")  # 仅第 2 行被调度
    assert result == {"scheduled": 1, "ids": ["run-1"], "skipped_running": 1}
    assert [t.args for t in background.tasks] == [(db, "doc-b", "run-1")]
    run_parse.assert_not_awaited()


def test_upload_multipart_defer_true_string(monkeypatch):
    """P4-T1 质量闭环（Important #1）：真 multipart 上传路径（starlette TestClient 最小 app +
    dependency_overrides 覆盖 get_db/_PERM）下，FastAPI Form bool 把 "true" 解析为 True——
    defer 行绝不 create_run、响应省略 run_id 键。直调版（_run_upload_route defer=True）只证
    「布尔已解析后」的行为，此测锁 multipart 层的字符串转换。"""
    from datetime import datetime
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from app.extensions.database import get_db
    from app.extensions.geo_samples import routers
    from app.extensions.geo_samples.models import GsbDocument

    create_run = AsyncMock()

    async def _by_report_id(db, rid):
        return None

    async def _dup(db, digest, exclude_uri):
        return None

    async def _create_doc(db, **kw):
        # created_at 必须显式给：未 flush 的 ORM 实例 server_default 未生效，DocumentOut 会炸
        return GsbDocument(id="d1", status="uploaded", created_at=datetime(2026, 9, 4), **kw)

    monkeypatch.setattr(routers.crud, "get_document_by_report_id", _by_report_id)
    monkeypatch.setattr(routers.crud, "find_duplicate_document", _dup)
    monkeypatch.setattr(routers.crud, "create_document", _create_doc)
    monkeypatch.setattr(routers.crud, "create_run", create_run)
    monkeypatch.setattr(routers.service, "run_parse", AsyncMock())
    monkeypatch.setattr(routers.storage, "put_raw", lambda rid, name, data: f"s3://geo-samples/raw/{rid}/{name}")

    app = FastAPI()
    app.include_router(routers.router)

    async def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[routers._PERM.dependency] = lambda: None  # 权限依赖 pass-through（最小 app 不挂 auth 中间件）

    client = TestClient(app)
    resp = client.post(
        "/api/extensions/geo-samples/documents/upload",
        data={"report_id": "gsb-kc-cu-0009", "defer_parse": "true"},
        files={"file": ("样例.docx", b"docx-bytes")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "run_id" not in body
    create_run.assert_not_called()
    assert body["document"]["status"] == "uploaded"
    assert body["document"]["id"] == "d1"


# ── P5 ledger A（plan 2026-09-04-geo-p5-orepack Task 1）：后端三修 ──────────────────


@pytest.mark.asyncio
async def test_run_redact_discards_result_when_doc_state_drifted(monkeypatch):
    """P5 ledger A：run_redact 对齐 run_parse R2 三段式——commit 释放连接 → 重活 → fresh 重取。
    重取见漂移态（非 parsed）→ 丢弃脱敏产物（不写 clean_uri）、doc 状态不被覆盖、run=failed。"""
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc_initial = GsbDocument(report_id="r9", file_name="a.docx", file_hash="h", file_type="docx", status="parsed", work_uri="s3://geo-samples/work/r9/parsed.md")
    doc_drifted = GsbDocument(report_id="r9", file_name="a.docx", file_hash="h", file_type="docx", status="reviewed", work_uri="s3://geo-samples/work/r9/parsed.md")
    events: list[str] = []

    async def _get_first(db_, did):
        events.append("get")
        return doc_initial

    async def _get_fresh(db_, did):
        events.append("fresh")
        return doc_drifted

    def _get_obj(uri):
        events.append("getobj")
        return "证号C5300002023000003".encode()

    async def _finish(db_, rid, status, detail):
        events.append("finish")

    put_clean = MagicMock()
    monkeypatch.setattr(service.crud, "get_document", _get_first)
    monkeypatch.setattr(service.crud, "get_document_fresh", _get_fresh)
    monkeypatch.setattr(service.crud, "finish_run", _finish)
    monkeypatch.setattr(service.storage, "get_object", _get_obj)
    monkeypatch.setattr(service.storage, "put_clean", put_clean)
    db = MagicMock()
    db.commit = AsyncMock(side_effect=lambda: events.append("commit"))

    await service.run_redact(db, "doc-9", run_id="run-9")

    # R2 顺序：get → commit 释放连接 → 下载重活 → fresh 重取 → failed 落账
    assert events == ["get", "commit", "getobj", "fresh", "finish"]
    assert doc_drifted.status == "reviewed"  # 漂移态不被脱敏结果覆盖
    assert doc_initial.status == "parsed"
    put_clean.assert_not_called()


@pytest.mark.asyncio
async def test_run_redact_releases_connection_before_heavy_work(monkeypatch):
    """P5 ledger A：run_redact 重活（下载+规则脱敏）前必须 commit 释放连接（R2 同款），
    且完成后走 fresh 重取落 redacted——正常路径不被漂移守卫误伤。"""
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import service
    from app.extensions.geo_samples.models import GsbDocument

    doc = GsbDocument(report_id="r10", file_name="a.docx", file_hash="h", file_type="docx", status="parsed", work_uri="s3://geo-samples/work/r10/parsed.md")
    events: list[str] = []

    async def _get(db_, did):
        events.append("get")
        return doc

    async def _get_fresh(db_, did):
        events.append("fresh")
        return doc

    def _get_obj(uri):
        events.append("getobj")
        return "证号C5300002023000003 正文".encode()

    def _put_clean(rid, data):
        events.append("putclean")
        return f"s3://geo-samples/clean/{rid}/source.md"

    monkeypatch.setattr(service.crud, "get_document", _get)
    monkeypatch.setattr(service.crud, "get_document_fresh", _get_fresh)
    monkeypatch.setattr(service.storage, "get_object", _get_obj)
    monkeypatch.setattr(service.storage, "put_clean", _put_clean)
    monkeypatch.setattr(service.crud, "add_redactions", AsyncMock(side_effect=lambda *a, **k: events.append("redactions")))
    db = MagicMock()
    db.commit = AsyncMock(side_effect=lambda: events.append("commit"))

    await service.run_redact(db, "doc-10", run_id="run-10")

    assert doc.status == "redacted"
    assert doc.clean_uri == "s3://geo-samples/clean/r10/source.md"
    # 连接释放在下载重活之前；fresh 重取在 put_clean 之前（漂移则不写产物）
    assert events.index("commit") < events.index("getobj") < events.index("fresh") < events.index("putclean")


def test_fc7_null_economics_sub_dicts_guard():
    """P5 ledger A（rates=null 清偿）：forms.economics 的 rates/concentrate/prices 为显式 null
    （LLM 抽取可产出 null 子对象）时 check_fc 不抛 AttributeError——rates 按 0 稀释计，
    E 链输入缺失时 FC7 整体跳过。"""
    from types import SimpleNamespace

    import consistency as cons

    eco = {"rates": None, "concentrate": None, "prices": None}
    data = SimpleNamespace(form=lambda name: eco if name == "economics" else {})

    # ① E1/E2 齐：修复前 `eco.get("rates", {}).get(...)` 在 rates=None 时 AttributeError
    vals = {
        "E1.C_usable": {"value": "100", "display": "100", "source": "t"},
        "E2.C_mined": {"value": "100", "display": "100", "source": "t"},
    }
    rep = cons.Report()
    cons.check_fc(rep, {"values": vals}, data)
    fc7 = [i for i in rep.items if i["contract"] == "FC7"]
    assert fc7 and fc7[0]["severity"] == "pass" and "E2.C_mined" in fc7[0]["detail"], fc7

    # ② 无 E 链输入：整体跳过，零 FC7 项
    rep2 = cons.Report()
    cons.check_fc(rep2, {"values": {}}, data)
    assert not [i for i in rep2.items if i["contract"] == "FC7"]


@pytest.mark.asyncio
async def test_parse_batch_integrity_error_conflict_409(monkeypatch):
    """P5 ledger A（TOCTOU 互斥）：行级 has_running_run 过检后、create_run 提交撞
    uq_gsb_run_running（他方批次在窗口内对同文档先落 running 行）→ IntegrityError →
    409「该样例解析已在调度」——批次终止、会话回滚复位、不静默入队双 run。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import BackgroundTasks
    from sqlalchemy.exc import IntegrityError

    from app.extensions.geo_samples import routers

    async def _sweep(db, max_age_minutes=60):
        return 0

    async def _list_uploaded(db, limit):
        return [SimpleNamespace(id="doc-a")]

    async def _has_running(db, did, rt):
        return False  # 行级守卫放行——TOCTOU 窗口

    create_run = AsyncMock(side_effect=IntegrityError('duplicate key value violates unique constraint "uq_gsb_run_running"', None, Exception("dup")))
    monkeypatch.setattr(routers.crud, "sweep_stale_runs", _sweep)
    monkeypatch.setattr(routers.crud, "list_uploaded", _list_uploaded)
    monkeypatch.setattr(routers.crud, "has_running_run", _has_running)
    monkeypatch.setattr(routers.crud, "create_run", create_run)

    db = MagicMock()
    db.rollback = AsyncMock()
    background = BackgroundTasks()
    with pytest.raises(routers.HTTPException) as ei:
        await routers.parse_batch(background=background, limit=5, db=db)
    assert ei.value.status_code == 409
    assert "已在调度" in ei.value.detail
    db.rollback.assert_awaited_once()  # IntegrityError 后事务作废，须复位会话
    assert background.tasks == []  # 撞互斥行不入队


def test_migrate_db_carries_gsb_run_running_index_migration():
    """P5 ledger A：migrate_db 必须携带 uq_gsb_run_running 部分唯一索引迁移（建索引前先清
    重复 running 行、保留最新）。migrate_db 全 PG 方言、sqlite 不可整跑 → 源码断言；
    索引语义另由 test_gsb_run_running_partial_unique_index_semantics 在 sqlite 实测，
    PG 实跑验证留 T8。"""
    import inspect

    from app.extensions import database

    src = inspect.getsource(database.migrate_db)
    assert "uq_gsb_run_running" in src
    assert "_GSB_RUN_RUNNING_DEDUP_SQL" in src, "建索引前必须先清历史重复 running 行（保留最新）"
    assert "_GSB_RUN_RUNNING_UQ_DDL" in src


def test_gsb_run_running_partial_unique_index_semantics(tmp_path):
    """P5 ledger A：uq_gsb_run_running 语义实测——sqlite 3.8+ 原生支持 partial index（plan 预估
    「sqlite 不支持」不成立，Python 3.12 捆绑 sqlite ≥3.40），同库即可锁语义：同文档第二条
    running parse/redact 拒、done 行/他文档行/NULL document_id 行（compile 型悬空行）放行。
    DDL 直取 database.py 常量防双份漂移；PG 实跑验证留 T8。"""
    import sqlite3

    from app.extensions import database

    conn = sqlite3.connect(tmp_path / "gsb_idx.db")
    conn.isolation_level = None  # autocommit——预期失败的 INSERT 不留悬挂事务
    conn.execute("CREATE TABLE gsb_run_history (id VARCHAR(36) PRIMARY KEY, document_id VARCHAR(36), run_type VARCHAR(16), status VARCHAR(16), created_at TIMESTAMP)")

    def ins(rid, doc, rt, st):
        conn.execute("INSERT INTO gsb_run_history (id, document_id, run_type, status) VALUES (?, ?, ?, ?)", (rid, doc, rt, st))

    conn.execute(database._GSB_RUN_RUNNING_UQ_DDL)
    ins("r1", "d1", "parse", "running")
    with pytest.raises(sqlite3.IntegrityError):
        ins("r2", "d1", "parse", "running")  # 同文档同类型双 running → 拒
    with pytest.raises(sqlite3.IntegrityError):
        ins("r3", "d1", "redact", "running")  # parse/redact 同域互斥 → 拒
    ins("r4", "d1", "parse", "done")  # 已完成行不计
    ins("r5", "d2", "parse", "running")  # 他文档放行
    ins("r6", None, "parse", "running")  # NULL document_id（compile 型悬空行）彼此不冲突
    ins("r7", None, "redact", "running")
