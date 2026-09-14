"""组装与交付门测试（单文档 tmp_path，无容器依赖）。"""
import json
from pathlib import Path

import build_output  # conftest.py 已注入 scripts/

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
FILLER = "锚杆支护施工必须严格执行敲帮问顶制度，严禁空顶作业，临时支护紧跟迎头。" * 40


def _stage_env(tmp_path):
    data = tmp_path / "data"; state = tmp_path / "state"; out = tmp_path / "outputs"
    for d in (data, state, out):
        d.mkdir()
    (state / "chapters").mkdir()
    # 交付名门数据源（对抗评审 P0：expected_deliverable_name 直读这两文件，缺了=名字回退 rc=1）
    (data / "00_profile.json").write_text(json.dumps({"mine_name": "某矿"}, ensure_ascii=False), encoding="utf-8")
    (data / "01_roadway.json").write_text(json.dumps({"roadway_name": "N3218运输顺槽"}, ensure_ascii=False), encoding="utf-8")
    titles = json.load(open(ROOT / "references" / "stages" / "tunneling.json", encoding="utf-8"))["chapters"]
    for ch, spec in titles.items():
        # T11 实测修正：C2（巷道全称 exact，消费者 ch5/ch8/ch9）与 C12（档案 echo，消费者 ch1/ch2）
        # 在场即激活——纯 FILLER 正文=档案漂移 fail（非 rc 0/3）；正文统一带矿名+巷道名呼应句，
        # 对齐真实产物形态（名称/档案值逐章在场）
        (state / "chapters" / f"{ch}.md").write_text(
            f"## {spec['title']}\n\n某矿N3218运输顺槽巷道掘进施工执行本规程，落实有掘必探、先探后掘。\n\n{FILLER}\n",
            encoding="utf-8")
    (state / "formula_state.json").write_text(json.dumps({"version": 2, "values": {}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps({"coefficient": 0.0, "absolute_floor": 0.4,
        "per_chapter": {f"ch{i}": {"median_eff": 3000, "median_table_rows": 2, "median_paragraphs": 10} for i in range(1, 10)}}, ensure_ascii=False), encoding="utf-8")
    return str(data), str(state), str(out), str(targets)


def test_assemble_writes_deliverable_and_manifest(tmp_path):
    data, state, out, targets = _stage_env(tmp_path)
    rc, out_text = _run(["--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", str(Path(out) / "某矿N3218运输顺槽掘进作业规程.md"), "--targets", targets])
    assert rc in (0, 3), out_text  # 3=consistency warn/manual 非阻断（无表单填充时 manual 居多）
    assert "BUILD_READY" in out_text
    assert (Path(out) / "delivery_manifest.json").exists()


def test_outputs_stray_file_gate(tmp_path):
    data, state, out, targets = _stage_env(tmp_path)
    (Path(out) / "草稿.md").write_text("x", encoding="utf-8")
    rc, out_text = _run(["--stage", STAGE, "--data-dir", data, "--state-dir", state,
                          "--output", str(Path(out) / "某矿N3218运输顺槽掘进作业规程.md"), "--targets", targets])
    assert rc == 1  # 散文件门（交付名门 L788-791：outputs/ 唯一交付单文件）


def _run(argv):
    import contextlib, io
    buf, ebuf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(ebuf):
        try:
            rc = build_output.main(argv)  # J13：main(argv=None) 签名
        except SystemExit as e:  # argparse 退出兜底（正常路径全部 return int）
            rc = e.code
    return rc, buf.getvalue() + ebuf.getvalue()
