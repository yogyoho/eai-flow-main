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
    """两份 reviewed 行的桩（SimpleNamespace 即可——编排层只读这几个字段）。"""
    from types import SimpleNamespace

    return [
        SimpleNamespace(report_id="rid-a", stage="exploration", mineral="gold", file_name="a.docx", clean_uri="s3://geo-samples/clean/rid-a/source.md", status="reviewed"),
        SimpleNamespace(report_id="rid-b", stage="exploration", mineral="gold", file_name="b.docx", clean_uri="s3://geo-samples/clean/rid-b/source.md", status="reviewed"),
    ]


def _patch_compile_happy_path(monkeypatch, tmp_path, docs):
    """编排层公共桩：reviewed 清单 / MinIO 下载 / 子进程 FakeProc / 无 RAGFlow env。返回 (exec_mock, write_back_rows, FakeProc)。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.extensions.geo_samples import service

    wd = tmp_path / "wd"
    wd.mkdir()
    monkeypatch.setattr(service.tempfile, "mkdtemp", lambda prefix="": str(wd))

    async def _list_reviewed(db, stage=None, mineral=None):
        return list(docs)

    write_back_rows = {d.report_id: SimpleNamespace(report_id=d.report_id, status="reviewed") for d in docs}

    async def _by_rid(db, rid):
        return write_back_rows[rid]

    monkeypatch.setattr(service.crud, "list_reviewed", _list_reviewed)
    monkeypatch.setattr(service.crud, "get_document_by_report_id", _by_rid)
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
    assert rows["rid-a"].status == "compiled"
    assert rows["rid-b"].status == "compiled"
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
