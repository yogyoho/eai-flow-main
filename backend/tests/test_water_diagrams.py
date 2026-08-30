"""water-drainage-report render_diagrams.py 契约锁（EAI-CUSTOM，插图占位方案）。

锁四件事：
1. 图片文件名 md5(fig_id)[:12].png 与 SKILL.md 引用逐字一致（改名任一侧即打回）；
2. 合成 state 可产出 3 张 PNG（PIL 管线在测试环境可用）；
3. 铁律#1：图上标注数值 = state 值（dim_v 显式 value 优先于坐标差；
   fig1 H / fig3 H 不与链和一致性耦合——state 值不同则图上文本跟着变）；
4. 字体子集字符集覆盖全部标注字符（新增标注文字须先扩 charset）。
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SKILL = _REPO / "skills" / "public" / "water-drainage-report"

_spec = importlib.util.spec_from_file_location("render_diagrams", _SKILL / "scripts" / "render_diagrams.py")
render_diagrams = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_diagrams)

# 合成 state（与 formulas.json 公式链自洽：0.85×2.2=1.87 等）——非真实项目数据
SMOKE = {
    "screen_hoist_len": 0.86,
    "screen_ring_height": 0.45,
    "screen_height": 2.2,
    "screen_clearance": 1.0,
    "platform_elev": 0.7,
    "screen_lift_height": 5.21,
    "bell_mouth_D1": 1620,
    "DN_suction": 1200,
    "bell_bottom_clearance": 1.13,
    "bell_submerge_depth": 1.78,
    "bell_rear_wall_dist": 1.46,
    "bell_side_wall_dist": 2.43,
    "hoist_assembly_len": 1.475,
    "lift_rope_len": 1.87,
    "pump_height": 2.04,
    "lift_clearance": 0.5,
    "pumphouse_h2": 3.3,
    "pumphouse_h1": 5.885,
    "pumphouse_height": 9.185,
}


class _Recorder:
    """Pen 的 draw 侧替身：只记录 text 调用，图形原语（line/rect/椭圆/弧/多边形/剖面线）不碰 PIL。"""

    def __init__(self):
        self.texts: list[str] = []

    def text(self, xy, s, **kw):
        self.texts.append(s)

    def line(self, coords, **kw):
        pass

    def rectangle(self, *a, **kw):
        pass

    def ellipse(self, *a, **kw):
        pass

    def arc(self, *a, **kw):
        pass

    def polygon(self, *a, **kw):
        pass


def _recording_pen(params) -> tuple[render_diagrams.Pen, _Recorder]:
    rec = _Recorder()
    pen = render_diagrams.Pen(rec, None, None, scale=100, ox=0, oy=0)
    return pen, rec


def test_fig_filenames_match_skill_contract():
    """文件名是 SKILL.md ↔ render_diagrams.py 的共享契约，任一侧改动必须同步。"""
    assert render_diagrams.fig_filename(render_diagrams.FIG_723_SCREEN) == "08bb824f44bb.png"
    assert render_diagrams.fig_filename(render_diagrams.FIG_821_BELL) == "35115cff8642.png"
    assert render_diagrams.fig_filename(render_diagrams.FIG_823_PUMPHOUSE) == "b1cfb1ccb5a3.png"
    skill_text = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    for fig_id in (render_diagrams.FIG_723_SCREEN, render_diagrams.FIG_821_BELL, render_diagrams.FIG_823_PUMPHOUSE):
        assert f"](images/{render_diagrams.fig_filename(fig_id)})" in skill_text


def test_render_three_pngs_from_synthetic_state(tmp_path):
    """合成 state → 3 张 PNG 落盘，文件名锁定，字节为真 PNG。"""
    outdir = tmp_path / "images"
    for fig_id, _title, _fn in render_diagrams.DIAGRAMS:
        out = render_diagrams.render(fig_id, dict(SMOKE), outdir)
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    names = {p.name for p in outdir.iterdir()}
    assert names == {"08bb824f44bb.png", "35115cff8642.png", "b1cfb1ccb5a3.png"}


def test_missing_params_skip_diagram():
    """缺参数必须显式报 KeyError（main 转 DIAGRAM_SKIP），不许静默画错图。"""
    pen, _rec = _recording_pen({})
    with pytest.raises(KeyError):
        render_diagrams.draw_screen_lift({}, pen)


def test_p_resolves_namespaced_formula_keys():
    """E2E 实测 bug-3011：formula_state all_params 部分公式输出键带 formula_id 前缀
    （lift_rope_len.lift_rope_len 等），裸键查找 KeyError → 图3 被 DIAGRAM_SKIP。
    _p 须唯一后缀解析；歧义后缀视为缺失（宁可 skip 不猜值）。"""
    ns = {f"{k}.{k}": v for k, v in SMOKE.items()}  # 全命名空间形式
    pen, rec = _recording_pen(None)
    render_diagrams.draw_pumphouse(ns, pen)
    assert "H=9.19m（H1=5.88m + H2=3.3m）" in rec.texts
    pen, rec = _recording_pen(None)
    render_diagrams.draw_screen_lift(ns, pen)
    assert "H=5.21" in rec.texts  # screen_lift_height 同为命名空间键，不再退链和
    # 混合形式（真实 state：部分裸、部分带前缀）
    mixed = dict(SMOKE)
    for k in ("lift_rope_len", "pumphouse_h1", "pumphouse_height"):
        mixed[f"{k}.{k}"] = mixed.pop(k)
    pen, rec = _recording_pen(None)
    render_diagrams.draw_pumphouse(mixed, pen)
    assert "x=1.87" in rec.texts and "H1=5.88" in rec.texts
    # 歧义后缀不猜
    assert render_diagrams._p({"a.a": 1.0, "b.a": 2.0}, "a") is None
    assert render_diagrams._p({"a.a": 1.0, "a": 2.0}, "a") == 2.0  # 裸键在场时精确优先


def test_dim_v_prefers_explicit_state_value():
    """铁律#1 核心：dim_v 的 value= 显式 state 值压过坐标差——H1=0.81 回归锁。"""
    pen, rec = _recording_pen(None)
    # 坐标差 5.885，显式值 7.7——必须打印显式值
    pen.dim_v(5, 3.3, 9.185, "H1", value=7.7)
    assert "H1=7.7" in rec.texts
    assert "H1=5.88" not in rec.texts
    # 无显式值 → 坐标差兜底（绘制链内部分段，坐标即真值；用整米坐标避开 float 噪声）
    pen.dim_v(5, 3.0, 9.0, "H2")
    assert "H2=6" in rec.texts


def test_fig3_annotations_use_state_values():
    """图3 全部标注 = state 值原样格式化（a 滑车组/x 起重绳/f 间隙/e 泵高/H1/H2/H）。"""
    pen, rec = _recording_pen(None)
    render_diagrams.draw_pumphouse(dict(SMOKE), pen)
    for label in ("a=1.48", "x=1.87", "f=0.5", "e=2.04", "H2=3.3", "H1=5.88"):  # a=1.475 state 值二进制格式化 1.48（旧坐标差路径曾是 1.47）
        assert label in rec.texts
    assert "H=9.19m（H1=5.88m + H2=3.3m）" in rec.texts


def test_fig3_h_follows_state_not_chain():
    """state 的 pumphouse_height 与 H1+H2 不一致时，图上 H 必须跟 state（铁律#1 禁重算）。"""
    params = dict(SMOKE)
    params["pumphouse_height"] = 10.0
    pen, rec = _recording_pen(None)
    render_diagrams.draw_pumphouse(params, pen)
    assert "H=10m（H1=5.88m + H2=3.3m）" in rec.texts


def test_fig1_h_follows_state_screen_lift_height():
    """图1 总高 H 同样 state 值优先（与 a+b+c+d+e 链和无关）。"""
    params = dict(SMOKE)
    params["screen_lift_height"] = 6.0
    pen, rec = _recording_pen(None)
    render_diagrams.draw_screen_lift(params, pen)
    assert "H=6" in rec.texts
    assert "起升高度 H=6m" in rec.texts
    # 链内分段仍按各自 state 值标注
    for label in ("a=0.86", "b=0.45", "c=2.2", "d=1", "e=0.7"):
        assert label in rec.texts


def test_main_tolerates_hallucinated_flags(tmp_path, monkeypatch, capsys):
    """bug-3017 回归：agent 会幻觉出 --report/--output-dir 等不存在的旗标（E2E 实测，
    argparse 报错后 agent 自造 DIAGRAMS_SKIPPED 并手写语义名图片行）——脚本必须忽略
    未知参数照常出图。"""
    state = tmp_path / "formula_state.json"
    state.write_text(json.dumps({"all_params": dict(SMOKE)}), encoding="utf-8")
    outdir = tmp_path / "images"
    monkeypatch.setattr(
        sys,
        "argv",
        ["render_diagrams.py", "--report", "x.md", "--output-dir", "/tmp", "--state", str(state), "--outdir", str(outdir)],
    )
    with pytest.raises(SystemExit) as ei:
        render_diagrams.main()
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "忽略未知参数" in out
    assert "DIAGRAMS_READY: 3" in out
    assert {p.name for p in outdir.iterdir()} == {"08bb824f44bb.png", "35115cff8642.png", "b1cfb1ccb5a3.png"}


def test_font_charset_covers_all_labels():
    """标注词表 + 组合字符串的全部字符必须在字体子集字符集内，否则图上出豆腐块。"""
    charset = set((_SKILL / "assets" / "font_chars.txt").read_text(encoding="utf-8"))
    labels = set("".join(render_diagrams.L.values()))
    # 组合字符串会用到的 ASCII/标点/数字（图例行、DN/D1/H 复合标注）——此前已实测该并集 missing: NONE
    labels |= set("0123456789=.-+()（） m/sDNabcdeHfxLrMLs")
    missing = sorted(labels - charset)
    assert not missing, f"font_chars.txt 缺字符: {missing}"


def test_state_json_smoke_fixture_matches_formula_consistency():
    """冒烟 state 的派生值与 formulas.json 链自洽（lift_rope_len=0.85×screen_height 曾错标 1.06）。"""
    assert SMOKE["lift_rope_len"] == pytest.approx(0.85 * SMOKE["screen_height"])
    assert SMOKE["pumphouse_h1"] == pytest.approx(SMOKE["hoist_assembly_len"] + SMOKE["lift_rope_len"] + SMOKE["pump_height"] + SMOKE["lift_clearance"])
    assert SMOKE["pumphouse_height"] == pytest.approx(SMOKE["pumphouse_h1"] + SMOKE["pumphouse_h2"])
    assert SMOKE["screen_lift_height"] == pytest.approx(SMOKE["screen_hoist_len"] + SMOKE["screen_ring_height"] + SMOKE["screen_height"] + SMOKE["screen_clearance"] + SMOKE["platform_elev"])
