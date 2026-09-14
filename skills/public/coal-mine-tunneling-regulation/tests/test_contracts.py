"""一致性合约注册表测试（C2 名exact / C10 manual / C12 档案漂移 fail+skip 语义 / 条件激活）。"""
import json
from pathlib import Path

import consistency  # conftest.py 已注入 scripts/
import ingest
from conftest import run_cli

ROOT = Path(__file__).resolve().parents[1]
STAGE = str(ROOT / "references" / "stages" / "tunneling.json")
CONTRACTS = str(ROOT / "references" / "consistency_contracts.json")
DIGEST = json.load(open(ROOT / "tests" / "fixtures" / "sample3218_digest.json", encoding="utf-8"))

def _setup(tmp_path, name="N3218运输顺槽", with_profile=False):
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)  # 对抗评审 P1：可重入
    run_cli(ingest.main, ["forms", "--stage", STAGE, "--data-dir", str(data)])
    vals = DIGEST["form_seed"]["roadway"] | {"roadway_use": "运输", "working_face_no": "W1", "reg_no": "掘ZJED-2026T/01",
        "azimuth": "N", "start_end_date": "x", "adjacent_relation": "实体煤", "net_height_mm": 3600, "drive_height_mm": 3600}
    vals["roadway_name"] = name
    run_cli(ingest.main, ["forms", "--stage", STAGE, "--data-dir", str(data), "--family", "roadway", "--values", json.dumps(vals, ensure_ascii=False)])
    if with_profile:  # C12 漂移场景需要档案在场
        run_cli(ingest.main, ["forms", "--stage", STAGE, "--data-dir", str(data), "--family", "profile",
                     "--values", json.dumps(DIGEST["form_seed"]["profile"], ensure_ascii=False)])
    (data / "formula_state.json").write_text(json.dumps({"version": 2, "values": {}, "anomalies": []}, ensure_ascii=False), encoding="utf-8")
    return str(data)

def _report(name="N3218运输顺槽", drop_chapter=None, gas_note=None, archive_note=None):
    chs = ["概况", "地面位置及地质情况", "巷道布置及支护说明", "施工工艺", "生产系统",
            "劳动组织及主要技术经济指标", "安全风险辨识与管控", "安全技术措施", "灾害应急措施及避灾路线"]
    if drop_chapter:
        chs = [c for c in chs if c != drop_chapter]  # 条件激活 skip 用例（对抗评审 P2）
    parts = [f"# 某矿{name}掘进作业规程", "## 作业规程会审主要栏", ""]
    for i, c in enumerate(chs, 1):
        body = f"本章为{i}章测试正文。" * 40
        if c == "概况":
            body += f"巷道名称{name}，编号 掘ZJED-2026T/01，设计长度 902.236m。"
            if gas_note:
                body += gas_note  # 漂移注入（如『本矿为高瓦斯矿井』）
        if archive_note:
            # 档案+工程值全量跨章回声（C1/C2/C3/C11/C12 正路径——消费者章各章都在场）
            body += archive_note + f"巷道{name}，掘进断面 18.0m²，净断面 15.0m²，设计长度 902.236m，编号 掘ZJED-2026T/01。"
        if c == "施工工艺":
            body += f"掘进断面 18.0m²，风筒 {name} 内铺设。"
        parts.append(f"## {c}\n\n{body}\n")
    return "\n".join(parts)

def _run_consistency(tmp_path, data, report, out_name):
    rc, out = run_cli(consistency.main, ["--report", str(report), "--data-dir", data, "--stage", STAGE,
                                 "--state", str(Path(data) / "formula_state.json"),
                                 "--contracts", CONTRACTS, "--output", str(tmp_path / out_name)])
    return rc, json.load(open(tmp_path / out_name, encoding="utf-8"))

def test_c2_pass_and_fail(tmp_path):
    data = _setup(tmp_path)
    report = tmp_path / "r.md"; report.write_text(_report(), encoding="utf-8")
    rc, res = _run_consistency(tmp_path, data, report, "c.json")
    assert "skip" in res["summary"]  # 五档计数（eia:159）
    report2 = tmp_path / "r2.md"; report2.write_text(_report(name="N3218运输巷"), encoding="utf-8")
    rc2, res2 = _run_consistency(tmp_path, data, report2, "c2.json")
    c2 = [i for i in res2["items"] if i["contract"] == "C2"]
    assert c2 and any(i["severity"] == "fail" for i in c2)

def test_c10_manual_and_c12_skip(tmp_path):
    data = _setup(tmp_path)  # 无档案
    report = tmp_path / "r.md"; report.write_text(_report(), encoding="utf-8")
    rc, res = _run_consistency(tmp_path, data, report, "c.json")
    by_id = {i["contract"]: i["severity"] for i in res["items"]}
    assert by_id.get("C10") == "manual"      # J8：恒 manual
    assert by_id.get("C12") == "skip"        # 档案族未填 → skip（首跑正常）

def test_c12_drift_fail_and_conditional_skip(tmp_path):
    data = _setup(tmp_path, with_profile=True)  # 档案 gas_grade=低瓦斯
    report = tmp_path / "r.md"
    report.write_text(_report(gas_note="本矿为高瓦斯矿井，按高瓦斯管理。"), encoding="utf-8")
    rc, res = _run_consistency(tmp_path, data, report, "c.json")
    c12 = [i for i in res["items"] if i["contract"] == "C12"]
    assert c12 and any(i["severity"] == "fail" for i in c12)  # 漂移=fail（spec 测试矩阵）
    # 条件激活：删除依赖章 → C7/C9 记 skip 不计退出码（正文带档案全量回声——C12 正路径）
    data2 = _setup(tmp_path, with_profile=True)
    prof = DIGEST["form_seed"]["profile"]
    echo = (f" {prof['mine_name']}矿，瓦斯等级{prof['gas_grade']}，水文地质类型{prof['hydro_type']}，"
            f"自燃倾向性{prof['spontaneous_tendency']}，煤尘{prof['coal_dust_explosion']}。")
    report2 = tmp_path / "r2.md"; report2.write_text(_report(drop_chapter="灾害应急措施及避灾路线", archive_note=echo), encoding="utf-8")
    rc2, res2 = _run_consistency(tmp_path, data2, report2, "c2.json")
    by2 = {i["contract"]: i["severity"] for i in res2["items"]}
    assert by2.get("C7") == "skip" and by2.get("C9") == "skip"
    assert rc2 != 1  # skip 不影响退出码
