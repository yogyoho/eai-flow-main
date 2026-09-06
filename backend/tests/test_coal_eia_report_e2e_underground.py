"""coal-eia-report e2e project_eia_underground 回归 + 实体泄漏反测（T7 文件⑤）。

两块（geo 先例 test_geological_report_e2e_full.py + SL3 指纹测试形制）：

  ① 实体泄漏反测（SC#3：横城实体注入月儿湾报告被泄漏检测拦截）——不依赖 underground stage，
     本期即可跑：
       a) 注册表契约：横城/月儿湾实体注册表（references/sample_entities/）覆盖反测实体串；
          合成的月儿湾节稿全文 0 命中（干净面），注入横城实体串后逐条命中（检测面有效）
       b) 脚本级拦截：consistency.check_sl3 范文数值指纹（tmp 样例库 fixture，geo 先例同款）——
          横城样例库数值 27185（走查 §5-F「长城全长 27185 千米」笔误实证）入稿 → fail 拦截；
          专名「××组」→ warn
       c) 数值溯源拦截：consistency.check_sl——范文数值不在项目数值池 → SL2 fail（rc=1 拦交付）
  ② 月儿湾参数走 underground stage 全管线（W_max=2018.39 实证锚，走查 §3 复现 q=0.8/m=3.08/
     α≈35°）——stages/project_eia_underground.json 尚未由并行会话落盘时整块 skipif。

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_coal_eia_report_e2e_underground.py -v
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "coal-eia-report"
SCRIPTS = SKILL / "scripts"  # conftest 同名脚本隔离锚
STAGE = SKILL / "references" / "stages" / "planning_eia.json"
UNDERGROUND = SKILL / "references" / "stages" / "project_eia_underground.json"
ENTITIES = SKILL / "references" / "sample_entities"

SENT = "矿区总体规划与现行环境保护法律法规构成本节评价的依据与边界条件，评价时段与评价分区据此划定。"

# 月儿湾注册表实体（自家面——干净稿的合法实体）与横城注册表实体（他项目面——反测注入串）
YUEERWAN_CLEAN = (
    "### 5.3.4 地表移动变形预测\n\n"
    "本节依据概率积分法对月儿湾矿井及选煤厂项目各开采阶段的地表移动变形进行预计，"
    "评价范围覆盖积家井矿区规划井田。首采工作面最大下沉值预计为 2018.39 毫米，"
    "相邻煤层叠加后为 956.77 毫米的倍数关系按软件成果转录，"
    "保护煤柱对象按银西铁路与矿区铁路专用线分别留设，盐池人饮工程与盐环定扬黄灌渠"
    "按哈巴湖国家级自然保护区外围的保护要求核查。"
)
HENGCHEng_INJECT = ["白芨滩国家级自然保护区", "水洞沟遗址", "明长城", "鸭子荡水库", "马莲台煤矿", "枣泉"]
HENGCHEng_NUMBER = "27185"  # 走查 §5-F：横城原文「长城全长 27185 千米（应为米）」笔误实证
INJECTED = (
    "### 5.3.4 地表移动变形预测\n\n"
    "本节依据概率积分法对月儿湾矿井及选煤厂项目各开采阶段的地表移动变形进行预计，"
    "对照明长城与鸭子荡水库的保护要求，并参考白芨滩国家级自然保护区与水洞沟遗址的监测数据，"
    "类比马莲台煤矿与枣泉矿井的实测参数，含煤地层侏罗系延安组覆岩类型一并核算，"
    "长城本体全长 27185 千米的数据在校核表中引用。"
)


def run(*args: object, expect=(0,)) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / str(args[0])), *map(str, args[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode in expect, f"{args[:3]} rc={r.returncode} (expect {expect})\n{r.stdout[-500:]}\n{r.stderr[:500]}"
    return r


def load_consistency():
    """本技能 consistency.py 以私有模块名装载（防 geo/coal 同名 sys.modules 串染）。"""
    name = "coal_eia_e2u_consistency"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / "consistency.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def registry_entities() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for p in sorted(ENTITIES.glob("*.json")):
        if p.name == "_index.json":
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        ents: set[str] = set()
        for group in (doc.get("entities") or {}).values():
            ents.update(x for x in group if isinstance(x, str) and len(x) >= 2)
        out[p.stem] = ents
    return out


# ── ① 实体泄漏反测（SC#3）──────────────────────────────────────────────────────


class TestEntityLeakCounterTest:
    def test_registry_covers_counter_test_entities(self):
        """反测前置（数据契约）：横城注册表覆盖全部注入实体串，月儿湾注册表在册。"""
        reg = registry_entities()
        assert "yueerwan" in reg and "hengcheng" in reg
        hc = reg["hengcheng"]
        missing = [e for e in HENGCHEng_INJECT if not any(e in x for x in hc)]
        assert not missing, f"横城注册表缺反测实体: {missing}"
        assert any("月儿湾" in x for x in reg["yueerwan"])

    def test_clean_draft_zero_hits_injected_draft_intercepted(self):
        """干净月儿湾节稿（自家实体+自家数值）→ 横城（他项目）实体 0 命中；
        注入横城实体串 → 逐条命中（泄漏检测清单对生成面有效；节题属 stage 骨架直出，不在扫描面）。"""
        reg = registry_entities()
        all_ents: set[str] = set().union(*reg.values())
        hc_ents = reg["hengcheng"]

        def sweep(text: str) -> set[str]:
            return {e for e in all_ents if e in text}

        body = YUEERWAN_CLEAN.replace("### 5.3.4 地表移动变形预测", "")
        assert not (sweep(body) & hc_ents), f"干净稿含横城实体: {sweep(body) & hc_ents}"
        injected_hits = sweep(INJECTED.replace("### 5.3.4 地表移动变形预测", ""))
        for e in HENGCHEng_INJECT:
            assert any(e in h for h in injected_hits), f"注入实体未被检测面捕获: {e}"

    def test_sl3_sample_fingerprint_intercepts(self, tmp_path):
        """脚本级拦截（geo N18/SL3 语义）：横城样例库数值 27185 入稿 → fail；在池/未入稿 → 不 fail；
        专名「延安组」疑带入 → warn。样例库 fixture = tmp references/samples/<stage_stem>/。"""
        cons = load_consistency()
        stage_path = tmp_path / "references" / "stages" / "project_eia_underground.json"
        samples = tmp_path / "references" / "samples" / "project_eia_underground"
        samples.mkdir(parents=True)
        (samples / "hengcheng_digest.md").write_text(f"横城样例摘录：明长城全长 {HENGCHEng_NUMBER} 千米（应为米——走查 §5-F 笔误实证）。\n侏罗系延安组。\n", encoding="utf-8")
        data = SimpleNamespace(forms={}, csvs={})
        chs = [("## 5 地表沉陷", YUEERWAN_CLEAN)]
        rep = cons.Report()
        cons.check_sl3(rep, chs, data, stage_path, set())
        assert not [i for i in rep.items if i["contract"] == "SL3" and i["severity"] == "fail"]
        rep_inj = cons.Report()
        cons.check_sl3(rep_inj, [("## 5 地表沉陷", INJECTED)], data, stage_path, set())
        fails = [i for i in rep_inj.items if i["contract"] == "SL3" and i["severity"] == "fail"]
        assert any(HENGCHEng_NUMBER in i["detail"] for i in fails), fails  # 数值指纹泄漏 → 拦截
        warns = [i for i in rep_inj.items if i["contract"] == "SL3" and i["severity"] == "warn"]
        assert any("延安组" in i["detail"] for i in warns), warns  # 范文专名疑带入 → warn

    def test_sl2_untraceable_sample_number_fails_gate(self):
        """管线级拦截：范文数值不在项目数值池 → SL2 fail（consistency rc=1 → build 拒交付）；
        池内冻结值（2018.39/956.77——走查 §3 实证锚）不误报。"""
        cons = load_consistency()
        pool = {Decimal("2018.39"), Decimal("956.77")}
        rep_clean = cons.Report()
        cons.check_sl(rep_clean, [("## 5 地表沉陷", YUEERWAN_CLEAN)], pool)
        assert not [i for i in rep_clean.items if i["severity"] == "fail"], rep_clean.items
        rep_inj = cons.Report()
        cons.check_sl(rep_inj, [("## 5 地表沉陷", INJECTED)], pool)
        fails = [i for i in rep_inj.items if i["severity"] == "fail"]
        assert any(HENGCHEng_NUMBER in i["detail"] for i in fails), fails


# ── ② 月儿湾参数走 underground stage（stage 文件在编——并行会话落盘前整块 skip）────

requires_underground = pytest.mark.skipif(not UNDERGROUND.exists(), reason="stages/project_eia_underground.json 尚未落盘（一期清单3 并行在编）")


def _write_form(stage: dict, data: Path, family: str, payload: dict) -> None:
    (data / stage["forms"][family]["file"]).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.mark.usefixtures("requires_underground_marker")
class TestUndergroundE2E:
    @pytest.fixture(scope="class")
    def ueia(self, tmp_path_factory):
        """月儿湾参数全管线：freeze（W_max=2018.39 实证锚）→ 沉陷专章节级派发 → 章门 VERIFIED。"""
        root = tmp_path_factory.mktemp("coal_e2u") / "ws"
        data, state = root / "data", root / "state"
        data.mkdir(parents=True)
        state.mkdir(parents=True)
        stage = json.loads(UNDERGROUND.read_text(encoding="utf-8"))
        # 月儿湾走查 §2.1/§3 实证参数（新建矿=规范推荐值口径；表 5.3-7 W_max 单层 2018.39）
        forms = {
            "subsidence_params": {
                "q": 0.8,
                "b": 0.3,
                "tan_beta": 2.4,
                "param_source": "规范推荐值",
                "overburden_lithology": "软弱",
                "per_mine": [{"mine": "月儿湾", "seam": "3煤", "m": 3.08, "H": 250, "alpha": 35, "repeat_mining": False}],
            },
        }
        for fam, payload in forms.items():
            if fam in stage["forms"]:
                _write_form(stage, data, fam, payload)
        run("progress.py", "init", "--stage", UNDERGROUND, "--state-dir", state, "--data-dir", data)
        r = run("progress.py", "run-stage", "freeze", "--state-dir", state, expect=(0, 3))
        assert r.returncode in (0, 3)
        fstate = json.loads((state / "formula_state.json").read_text(encoding="utf-8"))
        wmax = {k: v for k, v in fstate["values"].items() if "W_max" in k}
        assert any(v.get("display") == "2018.39" for v in wmax.values()), f"W_max=2018.39 实证锚未复现: {list(wmax)[:6]}"
        # 沉陷专章节级派发（必备章槽位——SC#2 前置走查 §5-E 验证对象），语义定位不锁章号
        sub_id = next(cid for cid, ch in stage["chapters"].items() if "沉陷" in str(ch.get("title", "")))
        sub = stage["chapters"][sub_id]
        depth = root / "depth_debug.json"
        depth.write_text(json.dumps({"chapters": {sub_id: {"floor_chars": 600}}}, ensure_ascii=False), encoding="utf-8")
        no = int(sub_id[2:]) if sub_id[2:].isdigit() else 0
        sids = []
        for i, s in enumerate(sub.get("sections", []), 1):
            body = "本节依据概率积分法预测各开采阶段的地表移动变形，并按保护对象逐一核定影响程度与治理要求。" + SENT * 8
            (state / "sections").mkdir(exist_ok=True)
            (state / "sections" / f"{s['id']}.md").write_text(f"### {no}.{i} {s['title']}\n\n{body}\n", encoding="utf-8")
            sids.append(s["id"])
        run("progress.py", "mark", "--sections", ",".join(sids), "DRAFTED", "--state-dir", state)
        run("progress.py", "mark", sub_id, "DRAFTED", "--state-dir", state)
        r = run("progress.py", "gate", "--chapters", sub_id, "--state-dir", state, "--targets", depth)
        assert "passed=1 failed=0" in r.stdout
        return SimpleNamespace(stage=stage, state=state, sub_id=sub_id, wmax=wmax, fstate=fstate)

    def test_stage_skeleton_and_subsidence_chapter(self, ueia):
        """必备章槽位：沉陷专章在场且已 VERIFIED；章树两层（章=level1 语义由 stage 唯一约束）。"""
        assert ueia.stage.get("chapter_order_policy") == "order_free_with_semantic_match"
        doc = json.loads((ueia.state / "progress.json").read_text(encoding="utf-8"))
        assert doc["chapters"][ueia.sub_id]["status"] == "VERIFIED"

    def test_w_max_anchor_and_slot_coverage(self, ueia):
        """W_max=2018.39 实证锚（走查 §3 复现）+ 沉陷槽位族（W_max/r 影响半径）在冻结层。"""
        assert any(v.get("display") == "2018.39" for v in ueia.wmax.values())
        assert any(k.startswith("subsidence.r") for k in ueia.fstate["values"]), sorted(k for k in ueia.fstate["values"] if k.startswith("subsidence"))

    def test_optional_chapter_absent_semantics(self, ueia):
        """可选章缺席 = ABSENT 豁免（走查 §5-E 总量控制缺席首验语义；无可选章时语义退化跳过）。"""
        stage = ueia.stage
        optional = [cid for cid, ch in stage["chapters"].items() if ch.get("optional")]
        if not optional:
            pytest.skip("underground stage 未登记 optional 章——可选章语义由其 stage 落盘版承载")
        run("progress.py", "mark", optional[0], "ABSENT", "--state-dir", ueia.state, "--detail", "总量控制章缺席（可选集）")
        depth = ueia.state.parent / "depth_debug.json"
        r = run("progress.py", "gate", "--chapters", optional[0], "--state-dir", ueia.state, "--targets", depth)
        assert "CHAPTER_GATE_SKIP" in r.stdout or "passed=0 failed=0" in r.stdout


@pytest.fixture()
def requires_underground_marker():
    """占位 marker fixture：使 usefixtures 装饰在 stage 缺席时不短路 skipif 语义。"""
    if not UNDERGROUND.exists():
        pytest.skip("stages/project_eia_underground.json 尚未落盘（一期清单3 并行在编）")
