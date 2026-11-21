"""geological-report Phase-1 硬化回归——六个代码级缺陷修复的行为钉（审查 2026-11）。

修复清单：
  ① ingest.parse_pdf_tables 死代码 `EXIT_MANOMALY if False else EXIT_MANUAL`
     （EXIT_MANOMALY 未定义名，靠条件表达式短路才未 NameError）→ 源面清零钉
  ② formula_runner.emit 槽位键空白清洗——CSV 工程号/矿体号含空格（"ZK 0701"）
     不再崩 write_state/门2（此前指引是让用户清洗源数据）
  ③ build_output.depth_target_eff 唯一出处——原三处内联重复公式的数学等价钉
  ④ formula_runner.override_data CSV 分支按前缀限族（原跨所有 CSV 覆写同名列，
     且与 cmd_update 写面口径不一致——dry-run 差分 ≠ apply 实改）
  ⑤ formula_runner.cmd_update CSV 分支原子写（原裸 open 全表重写有崩溃窗口）
     + register_file 指纹仍同步、无 .tmp 残留
  ⑥ ingest.register_file 死锁文件 mtime 过期（>LOCK_STALE_SECONDS）自动清理
     （原 10s 超时报错需人工删 .lock）

运行: cd backend && python -m pytest tests/test_geological_report_phase1_hardening.py -q
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "public" / "geological-report" / "scripts"

sys.path.insert(0, str(SCRIPTS))

import build_output  # noqa: E402  # sys.path 注入后导入（脚本自包含 stdlib）
import formula_runner as fr  # noqa: E402
import ingest  # noqa: E402


def _run(*args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / args[0]), *map(str, args[1:])],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# ── ① 死代码/未定义名清零 ────────────────────────────────────────────────────


def test_pdf_deadcode_typo_eradicated():
    src = (SCRIPTS / "ingest.py").read_text(encoding="utf-8")
    assert "EXIT_MANOMALY" not in src, "未定义名 EXIT_MANOMALY 复活（正确名 EXIT_ANOMALY；不得再靠 if False 短路掩盖）"
    assert "if False else" not in src, "if False else 短路写法不得回归（掩盖未定义名/死分支）"


# ── ② 槽位键空白清洗 ────────────────────────────────────────────────────────


def _mini_stage() -> dict:
    return {
        "forms": {
            "industrial_params": {"file": "13_industrial_params.json"},
            "sample_assays": {
                "file": "08a_sample_assays.csv",
                "format": "csv",
                "columns": ["工程号", "矿体编号", "样长_m", "品位Cu_pct", "品位Ag_gpt"],
            },
        }
    }


def _write_mini_assay_csv(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "13_industrial_params.json").write_text(
        json.dumps(
            {
                "boundary_grade_cu": 0.3,
                "min_industrial_grade_cu": 0.5,
                "deposit_avg_grade": 0.85,
                "outlier_multiple": 7,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rows = [
        ["工程号", "矿体编号", "样长_m", "品位Cu_pct", "品位Ag_gpt"],
        ["ZK 0701", "Ⅰ-2", "1.5", "1.0", "10"],
        ["ZK 0701", "Ⅰ-2", "2.0", "0.8", "12"],
        ["ZK0702", "Ⅰ-2", "1.0", "0.6", "8"],
    ]
    with open(data_dir / "08a_sample_assays.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def test_slot_key_whitespace_sanitized(tmp_path):
    """工程号 "ZK 0701"（含空格）此前使 _SLOT_KEY_RE 拒键 → write_state 崩门2；现发射点折叠。"""
    _write_mini_assay_csv(tmp_path)
    data = fr.Data(tmp_path, _mini_stage())
    values, _anomalies = fr.compute(data)
    assert any(k.startswith("L3.T[") for k in values), f"mini 数据应产出 L3 槽位: {sorted(values)}"
    spaced = [k for k in values if " " in k]
    assert not spaced, f"槽位键不得含空白: {spaced}"
    assert any(k.startswith("L3.T[ZK0701|") for k in values), f"'ZK 0701' 应折叠为 'ZK0701' 入键: {sorted(k for k in values if k.startswith('L3.T['))}"
    fr.write_state(tmp_path / "state.json", values, [])  # 修复前此处抛「槽位键形非法」


# ── ③ 深度目标公式唯一出处 ──────────────────────────────────────────────────


def test_depth_target_eff_single_source_math():
    cases = [
        (7487, 0.6, 1.0, 0.4),  # 无缺数 → 缩放项主导
        (17537, 0.6, 0.25, 0.4),  # scale_floor → 地板项主导（ch6 级）
        (1000, 0.6, 0.5, 0.4),  # 恰好跨地板
        (2331, 0.6, 0.9, 0.4),
    ]
    for median, coeff, scale, floor in cases:
        expected = max(median * coeff * scale, median * floor)
        assert build_output.depth_target_eff(median, coeff, scale, floor) == expected
    # 地板分支钉：覆盖缩放再低也压不穿 absolute_floor（bug-3036 绝对地板语义）
    assert build_output.depth_target_eff(1000, 0.6, 0.2, 0.4) == 400.0


# ── ④ override_data 前缀限族 ────────────────────────────────────────────────


def test_override_data_scoped_to_family(tmp_path):
    """两 CSV 族含同名列——改 13a 不得误伤 08a（修复前跨所有族覆写）。"""
    stage = {
        "forms": {
            "sample_assays": {"file": "08a_assay.csv", "format": "csv", "columns": ["样品编号", "品位"]},
            "bulk_density": {"file": "13a_density.csv", "format": "csv", "columns": ["样品编号", "品位"]},
        }
    }
    with open(tmp_path / "08a_assay.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([["样品编号", "品位"], ["S1", "1.0"]])
    with open(tmp_path / "13a_density.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([["样品编号", "品位"], ["S1", "2.8"]])
    data = fr.Data(tmp_path, stage)
    fr.override_data(data, "13a:品位", "9.9")
    assert data.csvs["bulk_density"][0]["品位"] == "9.9"
    assert data.csvs["sample_assays"][0]["品位"] == "1.0", "他族同名列不得被误伤（跨族覆写回归）"
    fr.override_data(data, "99x:品位", "0")  # 未知前缀 → no-op（不炸不误写）
    assert data.csvs["bulk_density"][0]["品位"] == "9.9"


# ── ⑤ update CSV 分支原子写 + manifest 同步 ─────────────────────────────────


def test_update_csv_atomic_and_manifest_sync(tmp_path):
    stage_path = tmp_path / "stage.json"
    stage = {
        "forms": {
            "industrial_params": {"file": "13_industrial_params.json"},
            "bulk_density": {"file": "13a_bulk_density.csv", "format": "csv", "columns": ["样品编号", "品位Cu_pct", "体重_t_m3", "湿度_pct"]},
        }
    }
    stage_path.write_text(json.dumps(stage, ensure_ascii=False), encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "13_industrial_params.json").write_text(
        json.dumps(
            {
                "boundary_grade_cu": 0.3,
                "min_industrial_grade_cu": 0.5,
                "deposit_avg_grade": 0.85,
                "outlier_multiple": 7,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with open(data_dir / "13a_bulk_density.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(
            [
                ["样品编号", "品位Cu_pct", "体重_t_m3", "湿度_pct"],
                ["S1", "1.0", "2.85", "0.2"],
                ["S2", "0.4", "2.70", "0.3"],
            ]
        )

    r1 = _run("formula_runner.py", "execute", "--stage", stage_path, "--data-dir", data_dir, "--output", tmp_path / "state.json")
    assert r1.returncode in (0, 3), r1.stderr
    r2 = _run("formula_runner.py", "impacted", "--stage", stage_path, "--data-dir", data_dir, "--state", tmp_path / "state.json", "--field", "13a:体重_t_m3", "--value", "3.10", "--output", tmp_path / "impacted.json")
    assert r2.returncode == 0, r2.stderr
    impacted = json.loads((tmp_path / "impacted.json").read_text(encoding="utf-8"))
    assert impacted["affected_formulas"], "体重列改参应产生非空差分（S1 统计受影响）"
    r3 = _run(
        "formula_runner.py",
        "update",
        "--stage",
        stage_path,
        "--data-dir",
        data_dir,
        "--state",
        tmp_path / "state.json",
        "--field",
        "13a:体重_t_m3",
        "--value",
        "3.10",
        "--impacted-file",
        tmp_path / "impacted.json",
        "--output",
        tmp_path / "new_state.json",
    )
    assert r3.returncode in (0, 3), r3.stderr
    # 内容：整列覆写生效、表头保持
    with open(data_dir / "13a_bulk_density.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == stage["forms"]["bulk_density"]["columns"]
    assert {r[2] for r in rows[1:]} == {"3.10"}
    # register_file 指纹与盘上字节一致（atomic 路径不破坏唯一写者语义）
    manifest = json.loads((data_dir / ingest.MANIFEST_NAME).read_text(encoding="utf-8"))
    digest = hashlib.sha256((data_dir / "13a_bulk_density.csv").read_bytes()).hexdigest()
    assert manifest["files"]["13a_bulk_density.csv"]["sha256"] == digest
    # 无 .tmp 残留（原子写收尾干净）
    assert not list(data_dir.glob("*.tmp"))


# ── ⑥ register_file 死锁文件自动清理 ────────────────────────────────────────


def test_register_file_stale_lock_auto_recovered(tmp_path):
    target = tmp_path / "13a_bulk_density.csv"
    target.write_text("样品编号,品位\nS1,1.0\n", encoding="utf-8")
    lock = tmp_path / (ingest.MANIFEST_NAME + ".lock")
    lock.write_text("", encoding="utf-8")
    stale = time.time() - (ingest.LOCK_STALE_SECONDS + 60)
    os.utime(lock, (stale, stale))
    # 修复前：自旋 10s 后 RuntimeError（需人工删 .lock）；现 mtime 过期就地清理成功
    ingest.register_file(tmp_path, "13a_bulk_density.csv", "bulk_density", True, "csv")
    assert not lock.exists()
    manifest = json.loads((tmp_path / ingest.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["files"]["13a_bulk_density.csv"]["sha256"] == ingest.sha256_file(target)


def test_register_file_fresh_lock_still_blocks(tmp_path):
    """活跃锁（mtime 新鲜）仍按原语义自旋超时——自动清理只针对残留死锁，不放行并发竞争。"""
    target = tmp_path / "13a_bulk_density.csv"
    target.write_text("样品编号,品位\nS1,1.0\n", encoding="utf-8")
    lock = tmp_path / (ingest.MANIFEST_NAME + ".lock")
    lock.write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="被占用超过 10s"):
        ingest.register_file(tmp_path, "13a_bulk_density.csv", "bulk_density", True, "csv")


# ── 门禁分级（硬化 2026-11）：正确性硬门 vs 风格软门 ─────────────────────────


class TestGateRegrade:
    """收窄硬门：toc 节号覆盖/残留/槽位/绝对地板保持硬 FAIL；≥3句/标题相符/深度拉伸降 warn。"""

    def test_depth_target_floor_breach_is_hard(self):
        targets = {"coefficient": 0.6, "absolute_floor": 0.4, "per_chapter": {"ch2": {"median_eff": 1000}}}
        with pytest.raises(ValueError, match="绝对地板"):
            build_output.depth_target_check("ch2", "太薄。", targets)  # eff≈2 < 400

    def test_depth_target_stretch_shortfall_is_warn_not_raise(self):
        targets = {"coefficient": 0.6, "absolute_floor": 0.4, "per_chapter": {"ch2": {"median_eff": 1000}}}
        # 精确构造：地板 400、风格目标 600——eff=500 ∈ (400, 600) → 地板达标、拉伸不足 → warn 文案
        warn = build_output.depth_target_check("ch2", "地" * 500, targets)
        assert isinstance(warn, str) and "风格目标" in warn
        assert build_output.depth_target_check("ch2", "地" * 700, targets) is None  # eff=700 ≥ 600 达标

    def test_depth_target_uncovered_chapter_is_noop(self):
        assert build_output.depth_target_check("ch99", "任意正文。", {"per_chapter": {}}) is None

    def test_toc_title_mismatch_downgraded_to_warn(self):
        toc = ["4.1 矿体特征（4.1.1 矿体连接对比 / 4.1.2 矿体特征）", "4.2 矿石质量"]
        md = "## 4 矿体地质\n\n### 4.1 完全不同的标题\n\n叙述一。叙述二。叙述三。\n\n#### 4.1.1 矿体连接对比\n\n叙述一。叙述二。叙述三。\n\n#### 4.1.2 矿体特征\n\n叙述一。叙述二。叙述三。\n\n### 4.2 矿石质量\n\n叙述一。叙述二。叙述三。\n"
        stats = build_output.validate_toc("ch4", md, toc)  # 不再因标题不符 raise
        assert stats["toc_entries"] == 4 and stats["toc_covered"] == 4
        assert stats["title_mismatches"] and "4.1" in stats["title_mismatches"][0]

    def test_toc_missing_and_extra_sections_still_hard(self):
        toc = ["4.1 矿体特征", "4.2 矿石质量"]
        good = "## 4 矿体地质\n\n### 4.1 矿体特征\n\n叙述一。叙述二。叙述三。\n\n### 4.2 矿石质量\n\n叙述一。叙述二。叙述三。\n"
        assert build_output.validate_toc("ch4", good, toc)["title_mismatches"] == []
        with pytest.raises(ValueError, match="toc 节号未落标题"):
            build_output.validate_toc("ch4", "## 4 矿体地质\n\n### 4.1 矿体特征\n\n叙述。\n", toc)
        with pytest.raises(ValueError, match="契约外节号"):
            build_output.validate_toc("ch4", good + "\n### 4.9 自创节\n\n叙述。\n", toc)

    def test_depth_style_warns_thin_blocks_and_eff(self):
        thin_md = "## 3 矿区地质\n\n矿区出露地层为震旦系灯影组白云岩。\n\n### 3.1 地层\n\n落雪组是主要含矿层。\n"
        warns = build_output.depth_style_warns("ch3", thin_md)
        assert any("3.1 地层=1句" in w for w in warns), warns
        assert any("有效字符" in w for w in warns), warns
        full_md = "## 3 矿区地质\n\n" + "第一句明确。第二句完整。第三句收束。\n" * 60 + "\n### 3.1 地层\n\n" + "第一句明确。第二句完整。第三句收束。\n"
        assert build_output.depth_style_warns("ch3", full_md) == []
