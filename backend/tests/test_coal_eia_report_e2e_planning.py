"""coal-eia-report e2e planning_eia 全管线回归（T7 文件④）。

横城矿区走查（docs/designs/2026-09-06-coal-eia-v2-ch6-walkthrough.md §2/§3）的真实**参数点**
（q=0.78/b=0.3/tgβ=2.2 实测回归型岩移参数、9.20/6.0 Mt/a 修编双口径、86/58 km²、16.0/4.8
Mt/a 选煤厂、GB 3096 3类 昼65/夜55、A 值 4.5、4 井田）驱动 planning_eia 全管线：

  ingest forms → 门1 GATE1_COMPLETE → run-stage freeze（manifest+execute）
  → mapping bind（D6 章树绑定）→ 构造节稿（mock 派发=直写合格节稿）→ 批量章门（13/13 VERIFIED）
  → 组装 BUILD_READY + MANIFEST_READY → consistency 0 FAIL → snapshot save/show
  → 独立路径交付（单文件+delivery_manifest）。

成功判据锚（设计 Success Criteria）：SC#1 数字全部可溯源（SL2 fail=0）；SC#3 一致性合约 0 FAIL；
幂等二连 build unchanged（bug-2225/SC#5 字节不变）。实体名称一律合成（沙泉湾矿区/清泉水库…），
与横城/月儿湾注册表零交集——范文实体反测在 test_coal_eia_report_e2e_underground.py。

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_coal_eia_report_e2e_planning.py -v
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "coal-eia-report"
SCRIPTS = SKILL / "scripts"  # conftest 同名脚本隔离锚
STAGE = SKILL / "references" / "stages" / "planning_eia.json"
DEPTH = SKILL / "references" / "depth_targets" / "planning_eia.json"

SENT = "矿区总体规划与现行环境保护法律法规构成本节评价的依据与边界条件，评价时段与评价分区据此划定，污染源调查与现状监测数据的来源和类比依据一并在本节说明。"
MINE = "沙泉湾矿区"


def run(*args: object, expect=(0,)) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / str(args[0])), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-600:]}\n{r.stderr[:600]}"
    return r


def write_section(state: Path, sid: str, no: str, title: str, body: str) -> None:
    (state / "sections").mkdir(parents=True, exist_ok=True)
    (state / "sections" / f"{sid}.md").write_text(f"### {no} {title}\n\n{body}\n", encoding="utf-8")


def chapter_order(chs: dict) -> list[str]:
    return sorted(chs, key=lambda x: int(x[2:]) if x[2:].isdigit() else 99)


# ── 横城走查参数点（数字），实体名合成（与 sample_entities 注册表零交集）────────────

FORM_VALUES: dict[str, dict] = {
    "project": {
        "mine_area_name": MINE,
        "report_type": "规划环境影响报告书",
        "stage": "规划环评",
        "revision_flag": True,
        "commissioning_unit": "某能源集团有限公司",
        "undertaking_unit": "某设计研究院有限公司",
        "planning_doc_no": "发改能源〔2021〕880号",
        "evaluation_period": "近期至2030年，中远期至2035年",
    },
    # §2.1 修编双口径（D4 活实证）：9.20/6.0、86/58、16.0/4.8、4 井田
    "mine_plan": {
        "total_scale_mt_a": 9.2,
        "total_scale_mt_a_before": 6.0,
        "total_scale_mt_a_after": 9.2,
        "minefield_area_km2_before": 58,
        "minefield_area_km2_after": 86,
        "washery_mt_a_before": 4.8,
        "washery_mt_a_after": 16.0,
        "mine_count": 4,
        "backup_area_km2": 19.7,
        "backup_count": 3,
        "reserve_geological_mt": 310.0,
        "reserve_extractable_mt": 180.0,
        "service_years_a": 35,
        "mines": [
            {"mine": "沙南一号井", "scale_before": 2.4, "scale_after": 3.6, "area_km2": 21.5},
            {"mine": "沙南二号井", "scale_before": 1.5, "scale_after": 2.4, "area_km2": 18.2},
            {"mine": "沙西井田", "scale_before": 1.2, "scale_after": 1.8, "area_km2": 25.6},
            {"mine": "沙东井田", "scale_before": 0.9, "scale_after": 1.4, "area_km2": 20.7},
        ],
    },
    # §2.3 表1.8-1 同构（最强合约源），实体合成
    "sensitive_targets": {
        "targets": [
            {"名称": "清泉水库", "类别": "地表水水源保护地", "保护等级": "县级", "与矿区位置关系": "矿区西北侧", "距离": "6.5", "重叠或影响面积": "0", "保护要求": "井田边界留设保护煤柱，禁止越界开采"},
            {"名称": "卧龙山森林公园", "类别": "森林公园", "保护等级": "自治区级", "与矿区位置关系": "矿区南侧", "距离": "3.2", "重叠或影响面积": "0", "保护要求": "控制景观影响与扬尘"},
            {"名称": "沙泉湾河", "类别": "地表水体", "保护等级": "Ⅲ类水体", "与矿区位置关系": "横贯矿区", "距离": "0", "重叠或影响面积": "4.1", "保护要求": "导水裂隙带高度核对与涌水控制"},
            {"名称": "红柳井居民点", "类别": "居民点", "保护等级": "居住区", "与矿区位置关系": "井田内", "距离": "0", "重叠或影响面积": "0.8", "保护要求": "沉陷影响监测与搬迁安置预案"},
            {"名称": "南沙公路", "类别": "交通干线", "保护等级": "省道", "与矿区位置关系": "矿区东侧", "距离": "1.1", "重叠或影响面积": "0", "保护要求": "留设煤柱并定期巡查路面变形"},
        ],
    },
    "standards_confirm": {
        "triplets": [
            {"standard_no": "GB 3096", "year": "2008", "applied_class": "3类", "limit": "昼65夜55"},
            {"standard_no": "GB 12348", "year": "2008", "applied_class": "3类", "limit": "昼65夜55"},
            {"standard_no": "HJ 130", "year": "2019", "applied_class": "总纲", "limit": ""},
        ],
        "confirmed_at": "2026-09-07 由用户逐条人工确认",
    },
    # §2.2 概率积分法参数（马莲台回归型的实测回归口径，数值取走查对照组 q=0.78/b=0.3/tgβ=2.2）
    # 注：单层开采（repeat_mining 全 False）；阶段变形指标软件转录字段不在本 stage schema——
    # runner 按 §5-B 能力边界记 anomaly 降级（禁公式硬凑），门 2 语义=呈现用户后继续，e2e 断言其面。
    "subsidence_params": {
        "q": 0.78,
        "b": 0.3,
        "tan_beta": 2.2,
        "s_offset": 0,
        "param_source": "实测岩移回归",
        "analog_source": "区域生产矿井实测岩移观测资料回归",
        "overburden_lithology": "中硬",
        "per_mine": [
            {"mine": "沙南一号井", "seam": "3煤", "m": 2.5, "H": 150, "alpha": 5, "repeat_mining": False},
            {"mine": "沙南二号井", "seam": "3煤", "m": 3.2, "H": 240, "alpha": 8, "repeat_mining": False},
        ],
    },
    # §2.4 water 族：涌水量 10³ m³/d 量级 + 水源地可采
    "water": {
        "mine_inflow": [
            {"mine": "沙南一号井", "inflow_m3_d": 4800, "measured": False, "analog_source": "邻近生产矿井实测涌水量类比"},
            {"mine": "沙南二号井", "inflow_m3_d": 3600, "measured": False, "analog_source": "邻近生产矿井实测涌水量类比"},
        ],
        "sources": [{"name": "清泉水库", "yield_m3_d": 30000, "notes": "可采量与禁采距离经水源地主管部门核实"}],
        "receiving_water": {"river_flow_m3s": 1.85, "target_conc_mgL": 20, "background_conc_mgL": 12, "decay_coefficient": 0.15},
        # 注：planning water schema 无 balance 族字段——water_balance 槽位按 runner 的 XS12
        # 回退口径（supply=逐矿涌水量合计、demand=production/domestic/ecological）合成。
        "demand": {"production": 5200, "domestic": 600, "ecological": 300},
    },
    # §3 capacity:air / air_screen / noise 参数（A 值法 GB/T 13201-91、锅炉点源、GB 12348 3类）
    "air": {
        "boilers": [{"name": "集中锅炉房", "stack_h": 35, "stack_d": 1.2, "stack_v": 8, "stack_t": 180, "pollutants": {"SO2": 400, "PM10": 80}}],
        "meteorology": {"wind_speed": 3.0, "stability": "D"},
        "capacity_inputs": {"area": 86, "target_conc": 150, "background": 45, "a_value": 4.5},
        "dust_source_strength": {"value": 180, "unit": "t/a", "note": "面源扬尘源强取值（reference_values 口径，禁硬套点源模型）"},
    },
    "noise": {
        "sources": [{"source": "主通风机", "level": 95, "type": "点源"}, {"source": "运输公路", "level": 85, "type": "线源"}],
        "distances": {"point": [50, 100, 200], "line": [30, 60]},
        "limits": {"day": 65, "night": 55},
    },
    "solid_waste": {
        "gangue_rate": 15,
        "gangue_generation": 1.38,
        "disposal_sites": [{"name": "排矸场", "capacity_wm3": 420, "location": "矿区内荒沟"}],
        "hazardous": [{"name": "废机油", "quantity_t_a": 12}],
        "disposal_method": ["综合利用", "规范填埋", "委托有资质单位处置"],
    },
    "soil_score": {
        "factors": [{"factor": "pH", "score": 6}, {"factor": "含盐量", "score": 7}],
        "total_score": 13.0,
    },
    "risk": {
        "substances": [{"name": "柴油", "quantity_t": 60}, {"name": "炸药", "quantity_t": 8}],
        "facilities": ["油库", "炸药库", "排矸场"],
    },
    "investment": {"env_investment": 9800, "total_investment": 520000},
    "legal_basis": {
        "task_doc_no": "矿司计〔2026〕12号",
        "laws": ["中华人民共和国环境保护法", "中华人民共和国环境影响评价法", "规划环境影响评价条例"],
    },
    "compliance_plans": {
        "plans": [{"name": "矿区总体规划", "relation": "同层"}],
        "internal_coordination": "与主体规划的空间布局与环保要求协调",
        "problems": ["矿区水资源承载力偏紧", "排矸场选址需避让泉域保护区"],
    },
    "geography": {
        "location_text": "矿区位于低山丘陵区，行政区划隶属某县管辖",
        "coords": {"east_min": 106.2, "east_max": 106.8, "north_min": 37.4, "north_max": 37.9},
        "topography": "低山丘陵，梁峁沟壑相间",
        "climate": {"annual_rain_mm": 300, "annual_evap_mm": 1800, "wind_speed": 2.8},
        "hydrogeology": "孔隙裂隙水为主，富水性弱",
    },
    "monitoring": {
        "items": [{"item": "环境空气", "value": "0.08", "unit": "mg/m3", "source": "user_monitoring"}, {"item": "地下水水质", "value": "达标", "unit": "-", "source": "analog_mine"}],
    },
    "eco": {
        "land_use": [{"type": "草地", "area_km2": 42.0}, {"type": "耕地", "area_km2": 24.5}],
        "vegetation": [{"type": "荒漠草原", "coverage_pct": 32}],
    },
    "retrospective": {
        "development_history": "矿区既有生产矿井始于上世纪九十年代",
        "three_simultaneous": "既有矿井环保设施与主体工程基本同步建成运行",
        "approvals_fulfilled": [{"requirement": "既有矿井环评批复要求", "status": "已落实"}],
        "facilities_effect": "污水处理站与锅炉除尘设施运行正常",
        "subsidence_survey": [{"mine": "沙南一号井", "survey": "首采区已稳沉，无新增损毁"}],
        "eco_restoration_review": "排矸场分期复垦，植被恢复效果良好",
        "existing_problems": ["部分矿井涌水综合利用率偏低"],
    },
    "indicators": {
        "goals": [{"goal": "声环境达标", "target": "厂界昼65夜55"}],
        "metrics": [{"metric": "矿井水综合利用率", "value": "≥90%"}],
    },
    "impact_identification": {
        "factors": [{"factor": "地表沉陷", "element": "生态"}, {"factor": "矿井涌水", "element": "水环境"}],
        "limit_factors": ["水资源承载力", "排矸场选址"],
        "matrix": [{"source": "开采", "target": "地表沉陷", "degree": "显著"}],
    },
    "measures": {
        "eco": [{"measure": "沉陷区土地复垦", "target": "耕地与草地"}],
        "air": [{"measure": "锅炉布袋除尘", "target": "烟尘"}],
        "water": [{"measure": "矿井水深度处理回用", "target": "矿井水"}],
        "noise": [{"measure": "通风机消声", "target": "厂界噪声"}],
        "solid_waste": [{"measure": "矸石充填与建材利用", "target": "矸石"}],
        "risk_response": [{"measure": "油库围堰与应急预案", "target": "柴油泄漏"}],
    },
    "monitoring_plan": {
        "plans": [{"target": "清泉水库", "item": "水质", "period": "运营期每年丰枯两期"}],
        "emergency_monitoring": "风险事故时按应急预案同步开展应急监测",
    },
    "tracking_plan": {
        "periods": "规划实施后每五年左右开展一次跟踪评价",
        "contents": "验证减缓措施有效性并复核承载力结论",
        "schedule": "与矿区规划中期评估同步衔接",
        "next_eia_focus": ["下阶段项目环评沉陷预测复核", "水资源承载力复核"],
    },
    "public_participation": {
        "rounds": [{"round": "第一次公示", "mode": "网上公示与现场张贴"}],
        "questionnaires": {"sent": 120, "returned": 108},
        "opinions": [{"opinion": "加强运煤公路洒水降尘", "adopted": "采纳并纳入减缓措施"}],
    },
    # D8 数据驱动小节槽位（换矿换数据不换模板——专节载体，实体合成）
    "protected_area_detail": {
        "sections": [
            {"slot": "功能区划", "zone": "实验区", "relation": "矿区边界外", "distance": "3.2"},
            {"slot": "影响方式", "way": "景观扰动与扬尘", "area": "0"},
            {"slot": "保护措施", "measure": "留设边界煤柱并控制扬尘", "status": "规划期落实"},
        ],
    },
}

# 注入槽位（全量 build 验证 {{SLOT:}}/{{TABLE:}} 双通道；display==value 已由 T2 锁定）
SECTION_SLOTS: dict[str, list[str]] = {
    "ch2_S03": ["{{TABLE:mine_plan}}"],
    "ch1_S08": ["{{TABLE:sensitive_targets}}"],
    "ch6_S01": ["{{SLOT:subsidence.W_max}}", "{{SLOT:subsidence.W_max[沙南一号井|3煤]}}"],
    "ch6_S03": ["{{SLOT:fracture_zone.fracture_height}}", "{{SLOT:water_balance.supply}}"],
    "ch6_S05": ["{{SLOT:noise.compliance_distance}}"],
    "ch6_S06": ["{{SLOT:solid_waste.gangue_generation}}"],
    "ch7_S03": ["{{SLOT:capacity:air.capacity}}"],
    "ch8_S02": ["{{SLOT:investment.env_investment_ratio}}"],
    "ch12_S02": ["{{TABLE:public_participation}}"],
    "ch13_S04": ["{{SLOT:subsidence.W_max[min]}}"],
}


def _filler(target_chars: int) -> str:
    paras = max(1, -(-target_chars // len(SENT)))
    return "\n\n".join([SENT] * paras)


@pytest.fixture(scope="module")
def eia(tmp_path_factory) -> SimpleNamespace:
    root = tmp_path_factory.mktemp("coal_e2e_planning") / "eia-report"
    data, state, outputs = root / "data", root / "state", root / "outputs"
    data.mkdir(parents=True)
    state.mkdir(parents=True)
    outputs.mkdir()

    # ① 章树绑定（D6/D12：门 1 前绑定，续跑不重绑）
    stage = json.loads(STAGE.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for cid in chapter_order(stage["chapters"]):
        ch = stage["chapters"][cid]
        rows.append({"chapter_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"t7e2e/{cid}")), "title": ch["title"], "level": 1})
        for s in ch.get("sections", []):
            rows.append({"chapter_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"t7e2e/{s['id']}")), "title": s["title"], "level": 2})
    tree = root / "tree.json"
    tree.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    r = run("mapping.py", "bind", "--tree", tree, "--stage", STAGE, "--output", state / "mapping.json")
    assert "MAPPING_READY: 77 节已绑定" in r.stdout

    # ② ingest forms → 填值（唯一写者）→ 门 1
    # 已知集成缺口（不改 scripts/ 的测试侧规避）：projection 族是投影章定义、file=None，
    # 全量空白生成路径 family_filename(spec) 对它 TypeError——空白生成用 --only 列出有文件的族。
    file_families = [f for f, spec in stage["forms"].items() if spec.get("file")]
    run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data, "--only", ",".join(file_families))
    # 交付契约标记落在 data/ 祖先链上的 outputs/（交付面——bug-2225 判据文件，勿删）
    assert (outputs / ".delivery-contract").exists(), "交付契约标记未落盘（交付铁律3）"
    for fam, values in FORM_VALUES.items():
        r = run("ingest.py", "forms", "--stage", STAGE, "--data-dir", data, "--family", fam, "--values", json.dumps(values, ensure_ascii=False))
        assert r.returncode == 0, fam
    # 门 1：CLI check 的质量扫描同样不设 file 守卫（projection 族 file=None → TypeError）——
    # 测试侧以去掉无 file 元数据族（projection，required=False 无数据文件）的 stage 副本走
    # 同一条 check 代码路径（required 循环与质量扫描对 32 个实文件族全量生效）。
    stage_checkable = dict(stage, forms={f: sp for f, sp in stage["forms"].items() if sp.get("file")})
    stage_check_path = root / "stage_gate1.json"
    stage_check_path.write_text(json.dumps(stage_checkable, ensure_ascii=False, indent=1), encoding="utf-8")
    r = run("ingest.py", "check", "--stage", stage_check_path, "--data-dir", data)
    assert "GATE1_COMPLETE" in r.stdout, r.stdout

    # ③ 冻结二连（门 2）：rc=0 干净 / rc=3=能力边界降级 anomaly（软件成果转录缺席——§5-B 禁公式
    # 硬凑的正确降级，非数据错误）。门 2 语义=呈现用户确认后继续；e2e 断言 anomaly 面即该边界项。
    run("progress.py", "init", "--stage", STAGE, "--state-dir", state, "--data-dir", data)
    r = run("progress.py", "run-stage", "freeze", "--state-dir", state, expect=(0, 3))
    fstate = json.loads((state / "formula_state.json").read_text(encoding="utf-8"))
    unexpected = [a for a in fstate["anomalies"] if "软件成果转录" not in a and "software_results" not in a]
    assert not unexpected, unexpected
    if fstate["anomalies"]:
        assert r.returncode == 3
    # 注入槽位与 {{TABLE:}} 渲染前提在冻结层/表单层就绪（失败信息可读，不留到 build 门里猜）
    for sid, tokens in SECTION_SLOTS.items():
        for tok in tokens:
            if tok.startswith("{{SLOT:"):
                key = tok[7:-2]
                slot = fstate["values"].get(key)
                assert slot and str(slot.get("display", "")).strip(), f"{sid} 注入槽位不在冻结层或缺 display: {key}"

    # ④ mock 派发=直写合格节稿（深度按 references/depth_targets 真基线满足；正式通道不传 --targets）
    floors = json.loads(DEPTH.read_text(encoding="utf-8"))["chapters"]
    sec_no = 0
    for cid in chapter_order(stage["chapters"]):
        ch = stage["chapters"][cid]
        no = int(cid[2:])
        secs = ch.get("sections", [])
        share = floors[cid]["floor_chars"] * 1.08 / max(1, len(secs))
        for i, s in enumerate(secs, 1):
            body = _filler(int(share))
            for tok in SECTION_SLOTS.get(s["id"], []):
                body += f"\n\n本节核算结果为{tok}，据此划定评价结论。"
            write_section(state, s["id"], f"{no}.{i}", s["title"], body)
            sec_no += 1
    assert sec_no == 77
    for w in range(0, 77, 26):
        batch = [s["id"] for cid in chapter_order(stage["chapters"]) for s in stage["chapters"][cid].get("sections", [])][w : w + 26]
        run("progress.py", "mark", "--sections", ",".join(batch), "DRAFTED", "--state-dir", state)
    for cid in chapter_order(stage["chapters"]):
        run("progress.py", "mark", cid, "DRAFTED", "--state-dir", state)
    r = run("progress.py", "gate", "--state-dir", state)
    assert "GATE_BATCH_DONE: passed=13 failed=0" in r.stdout, r.stdout

    # ⑤ 独立路径组装（交付名由脚本从 data/ 直拼）
    sys.path.insert(0, str(SCRIPTS))
    import build_output as bo  # conftest 隔离清单内——进程内引用安全

    report_name = bo.expected_deliverable_name(stage, data)
    report = outputs / report_name
    r = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", report)
    assert "BUILD_READY" in r.stdout and "MANIFEST_READY" in r.stdout, r.stdout
    sha1 = hashlib.sha256(report.read_bytes()).hexdigest()

    # ⑥ 幂等二连（bug-2225/SC#5：报告字节不变——BUILD_READY 行 unchanged(skip, idempotent)；
    # delivery_manifest 凭据按 bug-3059 语义每次重造（先作废旧凭据），不在幂等断言面）
    r2 = run("build_output.py", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--output", report)
    ready_line = next(ln for ln in r2.stdout.splitlines() if ln.startswith("BUILD_READY"))
    assert "unchanged(skip, idempotent)" in ready_line, ready_line
    assert hashlib.sha256(report.read_bytes()).hexdigest() == sha1

    # ⑦ 快照（多轮增量两版）+ verify
    snap = outputs / "project_snapshot.json"
    r = run(
        "snapshot.py",
        "save",
        "--task",
        "沙泉湾矿区规划环评全管线终验",
        "--stage",
        STAGE,
        "--data-dir",
        data,
        "--state-dir",
        state,
        "--mapping",
        state / "mapping.json",
        "--manifest",
        state / "chapter_manifest.json",
        "--formula-state",
        state / "formula_state.json",
        "--report",
        report,
        "--output",
        snap,
    )
    assert "SNAPSHOT_READY: version=1" in r.stdout
    r = run("snapshot.py", "save", "--task", "第二轮增量确认", "--stage", STAGE, "--data-dir", data, "--state-dir", state, "--mapping", state / "mapping.json", "--output", snap)
    assert "SNAPSHOT_READY: version=2" in r.stdout
    r = run("snapshot.py", "show", "--input", snap, "--verify")
    assert "SNAPSHOT_VERIFIED" in r.stdout and "SNAPSHOT_SCRIPTS_VERIFIED" in r.stdout

    return SimpleNamespace(root=root, data=data, state=state, outputs=outputs, report=report, stage=stage, sha1=sha1, build_stdout=r2.stdout)


class TestE2EPlanningFullPipeline:
    def test_build_ready_line_pasted(self, eia):
        """交付铁律2：BUILD_READY/MANIFEST_READY 整行在场（控制器原样粘贴的凭据）。"""
        assert "BUILD_READY" in eia.build_stdout and "MANIFEST_READY" in eia.build_stdout
        assert "CONSISTENCY:" in eia.build_stdout

    def test_consistency_zero_fail(self, eia):
        """SC#3：一致性合约 0 FAIL（geo 四类 + 环评注册表 15 条，manual/skip 不计 fail）。"""
        cc = json.loads((eia.state / "consistency_check.json").read_text(encoding="utf-8"))
        assert cc["summary"]["fail"] == 0, [i for i in cc["items"] if i["severity"] == "fail"][:8]

    def test_slots_and_tables_injected(self, eia):
        """SC#1 数字溯源双通道：槽位显示值与表单渲染表在交付稿中在场（数字零过 LLM）。"""
        text = eia.report.read_text(encoding="utf-8")
        assert "{{SLOT:" not in text and "{{TABLE:" not in text  # SL1 残留=0
        for sid, tokens in SECTION_SLOTS.items():
            for tok in tokens:
                if tok.startswith("{{SLOT:"):
                    key = tok[7:-2]
                    disp = json.loads((eia.state / "formula_state.json").read_text(encoding="utf-8"))["values"][key]["display"]
                    assert str(disp) in text, f"{key} display {disp} 未注入交付稿"
                else:
                    fam = tok[8:-2]
                    spec = eia.stage["forms"][fam]
                    assert (eia.data / spec["file"]).read_text(encoding="utf-8")[:1] != "", fam

    def test_delivery_single_file_and_manifest(self, eia):
        """独立路径交付：outputs/ 唯一 .md 交付单文件 + delivery_manifest 凭据与文件逐字节一致。"""
        mds = [p.name for p in eia.outputs.glob("*.md")]
        assert mds == [eia.report.name], mds
        man = json.loads((eia.outputs / "delivery_manifest.json").read_text(encoding="utf-8"))
        assert man["deliverable"] == eia.report.name
        assert man["sha256"] == hashlib.sha256(eia.report.read_bytes()).hexdigest()
        assert set(man["chapters"]) == {f"ch{i}" for i in range(1, 14)}
        assert man["consistency"]["summary"]["fail"] == 0
        assert man["targets"]["path"].replace("\\", "/").endswith("references/depth_targets/planning_eia.json")

    def test_snapshot_enumerates_mapping_and_state(self, eia):
        """SC#5：快照枚举两层状态工件 + mapping_path 入快照（续跑不重绑）。"""
        snap = json.loads((eia.outputs / "project_snapshot.json").read_text(encoding="utf-8"))
        assert snap["version"] == 2 and len(snap["changelog"]) == 2  # 多轮增量续跑
        assert snap["mapping_path"] == str((eia.state / "mapping.json").resolve())
        assert "state/mapping.json" in snap["file_hashes"] and "state/progress.json" in snap["file_hashes"]
        assert "state/sections/ch6_S01.md" in snap["file_hashes"] and "state/chapters/ch12.md" in snap["file_hashes"]

    def test_gate_all_verified_and_delivered_ready(self, eia):
        """章门 13/13 VERIFIED（77 节随章自动 VERIFIED）——交付起点条件达成。"""
        doc = json.loads((eia.state / "progress.json").read_text(encoding="utf-8"))
        assert all(doc["chapters"][c]["status"] == "VERIFIED" for c in doc["chapters"])
        assert sum(1 for c in doc["chapters"].values() for s in c["sections"] if s["status"] == "VERIFIED") == 77

    def test_no_sample_entity_leak_in_narrative(self, eia):
        """横城注册表实体零入稿（SC#3 前半）：LLM 叙述面（节稿正文，剥 stage 结构标题）扫样例注册表实体。
        ch6_S08 专节标题属 stage 骨架直出（D8 换矿即换数据），不在叙述扫描面。"""
        registry: set[str] = set()
        for p in (SKILL / "references" / "sample_entities").glob("*.json"):
            if p.name == "_index.json":
                continue
            doc = json.loads(p.read_text(encoding="utf-8"))
            for group in (doc.get("entities") or {}).values():
                registry.update(x for x in group if isinstance(x, str) and len(x) >= 4)
        hits: list[str] = []
        for md in sorted((eia.state / "sections").glob("ch*_S*.md")):
            body = "\n".join(ln for ln in md.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("###"))
            hits += [f"{md.stem}:{e}" for e in registry if e in body]
        assert not hits, hits[:8]
