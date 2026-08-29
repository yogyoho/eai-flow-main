#!/usr/bin/env python3
"""参数驱动示意图生成器（插图占位契约的图片侧）。

从 formula_state.json 的 all_params 读数，绘制 3 张带尺寸标注的工程线图（PNG），
落到 <outdir>/<12hex>.png —— 文件名固定（见 DIAGRAMS），SKILL.md 里的图片引用
逐字使用这些名字；docmgr Word 导出按相对引用 images/<name> 解析嵌图（bug-3004）。

用法：
    python render_diagrams.py --state formula_state.json --outdir /mnt/user-data/outputs/images
    python render_diagrams.py --state ... --outdir ... --only fig_821_bell_mouth

输出 marker（agent 依据）：
    DIAGRAMS_READY: <n>      成功张数，随后每行 DIAGRAM_FILE: <fig_id> <相对路径>
    DIAGRAM_SKIP: <fig_id> <原因>   缺参数/字体缺失时逐张跳过；全部失败 exit 1

铁律#1 同源：图上标注数值 = state JSON 值（本脚本只做格式化，不做任何计算）。
中文字体：assets/NotoSansSC-subset.ttf（OFL 许可，按本脚本 label 词表子集化）；
新增标注文字后须重跑子集化并把字符集同步进 assets/font_chars.txt（test_diagrams 锁）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# ── 固定产物名：md5(fig_id)[:12].png，SKILL.md 引用与此处必须一致（test_diagrams 锁） ──
FIG_723_SCREEN = "fig_723_screen_lift"
FIG_821_BELL = "fig_821_bell_mouth"
FIG_823_PUMPHOUSE = "fig_823_pumphouse"


def fig_filename(fig_id: str) -> str:
    return hashlib.md5(fig_id.encode()).hexdigest()[:12] + ".png"


# ── 标注词表（也是字体子集的字符来源之一；改这里须同步 font_chars.txt） ──
L = {
    "screen_title": "滤网起吊示意图",
    "hoist": "滑车+葫芦",
    "ring": "吊环",
    "screen": "滤网",
    "platform": "操作平台",
    "lift_h": "起升高度",
    "water": "水面",
    "submerge": "淹没深度",
    "bell": "吸水喇叭口",
    "pool_bottom": "吸水池池底",
    "rear": "后墙",
    "side": "侧墙",
    "suction": "吸水管",
    "pumphouse_title": "泵房剖面示意图",
    "crane": "吊车梁+滑车+葫芦",
    "rope": "起重绳",
    "pump": "水泵机组",
    "ground": "室内地坪",
    "clear": "吊离间隙",
}

# 画布与线型
W, H = 1400, 1000
BG = (255, 255, 255)
INK = (30, 30, 30)
DIM = (0, 90, 180)  # 尺寸标注蓝
WATER = (120, 170, 220)


def _fmt(v) -> str:
    """state 数值 → 标注文本：保留 2 位小数并去尾零（铁律#1：只格式化不改值）。"""
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


class Pen:
    """PIL 绘图薄封装：线/箭头尺寸线/虚线/文字。坐标一律米，由 scale 折算像素。"""

    def __init__(self, draw, font, font_small, scale, ox, oy):
        self.d = draw
        self.f = font
        self.fs = font_small
        self.scale = scale
        self.ox = ox
        self.oy = oy

    def px(self, x: float, y: float) -> tuple[int, int]:
        # 工程坐标：y 向上（0=地面），像素 y 翻转（oy=画布底部基线）
        return (int(self.ox + x * self.scale), int(self.oy - y * self.scale))

    def line(self, x1, y1, x2, y2, color=INK, width=3, dash=False):
        p1, p2 = self.px(x1, y1), self.px(x2, y2)
        if not dash:
            self.d.line([p1, p2], fill=color, width=width)
            return
        # 简易虚线：按 12px 步进分段
        import math

        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        n = max(2, int(length // 14))
        for i in range(n):
            if i % 2:
                continue
            t0, t1 = i / n, (i + 1) / n
            self.d.line(
                [
                    (p1[0] + (p2[0] - p1[0]) * t0, p1[1] + (p2[1] - p1[1]) * t0),
                    (p1[0] + (p2[0] - p1[0]) * t1, p1[1] + (p2[1] - p1[1]) * t1),
                ],
                fill=color,
                width=width,
            )

    def text(self, x, y, s, color=INK, small=False, anchor="mm"):
        self.d.text(self.px(x, y), s, fill=color, font=self.fs if small else self.f, anchor=anchor)

    def rect(self, x1, y1, x2, y2, color=INK, width=3):
        """矩形（米坐标，y1>y2 语义不敏感化：取 min/max）。"""
        ax, ay = self.px(x1, y1)
        bx, by = self.px(x2, y2)
        self.d.rectangle([min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)], outline=color, width=width)

    def dim_v(self, x, y1, y2, label, value=None):
        """竖直尺寸线（带端点刻度），label=值 写在线左侧（value 显式给 state 值，否则取坐标差）。"""
        self.line(x, y1, x, y2, color=DIM, width=2)
        for yy in (y1, y2):
            self.line(x - 0.06, yy, x + 0.06, yy, color=DIM, width=2)
        v = abs(y1 - y2) if value is None else value
        self.text(x - 0.12, (y1 + y2) / 2, f"{label}={_fmt(v)}", color=DIM, small=True, anchor="rm")

    def dim_h(self, y, x1, x2, label):
        self.line(x1, y, x2, y, color=DIM, width=2)
        for xx in (x1, x2):
            self.line(xx, y - 0.06, xx, y + 0.06, color=DIM, width=2)
        self.text((x1 + x2) / 2, y + 0.14, f"{label}={_fmt(abs(x1 - x2))}", color=DIM, small=True)


def _p(params, key):
    v = params.get(key)
    return None if v is None else float(v)


# ── 图1：滤网起吊示意（7.2.3） ────────────────────────────────────────────
# a 滑车+葫芦 / b 吊环 / c 滤网 / d 滤网底-平台顶 / e 平台顶标高；链和=起升高度
def draw_screen_lift(params, pen: Pen) -> None:
    need = ["screen_hoist_len", "screen_ring_height", "screen_height", "screen_clearance", "platform_elev"]
    vals = {k: _p(params, k) for k in need}
    missing = [k for k, v in vals.items() if v is None]
    if missing:
        raise KeyError(",".join(missing))
    a, b, c, d, e = (vals[k] for k in need)
    sw, sh = 2.2, c  # 滤网外形（宽取样例 2.2m 量级，仅示意比例）
    cx = 3.0
    # 地面与平台
    pen.line(0, 0, 8, 0, width=4)
    pen.line(1.2, e, 5.2, e, width=3)
    pen.text(5.45, e, L["platform"], small=True, anchor="lm")
    for gx in (1.35, 5.05):  # 平台支腿
        pen.line(gx, e, gx, 0, width=3)
    # 吊链链段：顶部钩点 → 滑车+葫芦 a → 吊环 b → 滤网 c → 底距 d
    top = e + d + sh + b + a
    pen.line(cx, top, cx, top - a, width=3)
    pen.line(cx - 0.45, top - a, cx + 0.45, top - a, width=5)  # 滑车横杆
    pen.line(cx, top - a, cx, top - a - b, width=3)
    pen.line(cx - 0.25, top - a - b, cx + 0.25, top - a - b, width=4)  # 吊环
    pen.rect(cx - sw / 2, top - a - b, cx + sw / 2, top - a - b - sh)
    for i in range(1, 6):  # 滤网网格线（示意）
        xx = cx - sw / 2 + sw * i / 6
        pen.line(xx, top - a - b, xx, top - a - b - sh, width=1, dash=True)
    pen.text(cx - sw / 2 - 0.2, top - a - b - sh / 2, L["screen"], anchor="rm")
    # 右侧尺寸链 a/b/c/d/e + 总高
    x_dim = cx + sw / 2 + 1.0
    segs = [("a", a), ("b", b), ("c", sh), ("d", d), ("e", e)]
    y_cur = top
    for name, _v in segs:
        pen.dim_v(x_dim, y_cur, y_cur - _v, name)
        y_cur -= _v
    h_state = _p(params, "screen_lift_height")  # state 值优先（铁律#1），缺失才退回链和
    pen.dim_v(x_dim + 0.8, top, 0, "H", value=h_state)
    pen.text(x_dim + 1.0, top / 2, f"{L['lift_h']} H={_fmt(top if h_state is None else h_state)}m", color=DIM, small=True, anchor="lm")
    # 段名图例（中文段名整行列在左下，尺寸线旁只留字母）
    pen.text(0.2, -0.35, "a滑车+葫芦 b吊环 c滤网 d滤网底-平台顶 e平台顶标高", small=True, anchor="lm")


# ── 图2：吸水喇叭口安装剖面（8.2.1，02S403） ─────────────────────────────
# D1 喇叭口直径 / DN 吸水管径 / hb 距池底 / hs 淹没深度 / Lr 后墙 / Ls 侧墙
def draw_bell_mouth(params, pen: Pen) -> None:
    need = ["bell_mouth_D1", "DN_suction", "bell_bottom_clearance", "bell_submerge_depth",
            "bell_rear_wall_dist", "bell_side_wall_dist"]
    vals = {k: _p(params, k) for k in need}
    missing = [k for k, v in vals.items() if v is None]
    if missing:
        raise KeyError(",".join(missing))
    d1, dn, hb, hs, lr, ls = (vals[k] for k in need)
    d1m, dnm = d1 / 1000, dn / 1000  # mm → m
    # 池体：底 0，水面 hs+d1m+0.2，后墙在 x=0，侧墙在 x=lr+ls+0.5
    wl = hs + d1m + 0.2
    xr = lr + ls + 0.5
    pen.line(0, 0, xr, 0, width=4)  # 池底
    pen.line(0, 0, 0, wl + 0.6, width=4)  # 后墙
    pen.line(xr, 0, xr, wl + 0.6, width=4)  # 侧墙
    pen.line(0.1, wl, xr - 0.1, wl, color=WATER, width=3, dash=True)
    pen.text(xr - 0.25, wl + 0.22, L["water"], color=WATER, small=True, anchor="rm")
    # 吸水管（竖管自水面下伸）+ 喇叭口（梯形张口向下）
    cx = lr  # 喇叭口中心 = 距后墙 Lr
    bell_top = hb + d1m
    pen.line(cx - dnm / 2, wl + 0.5, cx - dnm / 2, bell_top, width=4)
    pen.line(cx + dnm / 2, wl + 0.5, cx + dnm / 2, bell_top, width=4)
    pen.line(cx - dnm / 2, bell_top, cx - d1m / 2, hb, width=4)
    pen.line(cx + dnm / 2, bell_top, cx + d1m / 2, hb, width=4)
    pen.line(cx - d1m / 2, hb, cx + d1m / 2, hb, width=3, dash=True)
    pen.text(cx + d1m / 2 + 0.15, hb + d1m / 2, L["bell"], anchor="lm")
    pen.text(cx, wl + 0.65, f"DN={_fmt(dn)}mm", color=INK, small=True)
    # 尺寸标注
    pen.dim_v(0.35, 0, hb, "hb")  # 距池底
    pen.dim_v(xr - 0.35, wl, bell_top, "hs")  # 淹没深度
    pen.dim_h(0.35, 0, cx, "Lr")  # 后墙
    pen.dim_h(-0.35, cx, xr, "Ls")  # 侧墙（画在池外左侧偏移，示意）
    pen.dim_v(xr + 0.4, hb, hb + d1m, "D1")
    pen.text(xr + 0.6, hb + d1m + 0.3, f"D1={_fmt(d1)}mm", color=DIM, small=True, anchor="lm")
    pen.text(0.2, -0.35, L["pool_bottom"], small=True, anchor="lm")
    pen.text(0.15, wl * 0.6, L["rear"], small=True, anchor="lm")
    pen.text(xr - 0.15, 1.0, L["side"], small=True, anchor="rm")


# ── 图3：泵房剖面（8.2.3） ──────────────────────────────────────────────
# H1 = a 滑车组 + x 起重绳 + f 吊离间隙 + e 泵高（自地坪向上链）；H = H1 + H2（地下）
def draw_pumphouse(params, pen: Pen) -> None:
    need = ["hoist_assembly_len", "lift_rope_len", "pump_height", "lift_clearance", "pumphouse_h1", "pumphouse_h2"]
    vals = {k: _p(params, k) for k in need}
    missing = [k for k, v in vals.items() if v is None]
    if missing:
        raise KeyError(",".join(missing))
    aa, rope, ph, fc, h1, h2 = (vals[k] for k in need)
    htot = _p(params, "pumphouse_height")
    if htot is None:
        htot = h1 + h2  # 兜底：正式 state 恒有 pumphouse_height（v3 公式输出）
    ground = h2  # 室内地坪标高（地下部分 h2）
    top = h1 + h2  # 吊车梁顶 = H1 顶；H = H1 + H2
    # 房体轮廓 + 地坪线
    pen.line(0, 0, 10, 0, width=4)
    pen.line(0, top, 10, top, width=4)
    pen.line(0, 0, 0, top, width=4)
    pen.line(10, 0, 10, top, width=4)
    pen.line(0.2, ground, 9.8, ground, color=INK, width=3, dash=True)
    pen.text(1.0, ground - 0.3, L["ground"], small=True, anchor="lm")
    # 吊车梁贴建筑顶；泵落地（高 e），吊钩悬停位与泵顶之间留吊离间隙 f
    cx = 5.0
    pen.line(1.0, top - 0.1, 9.0, top - 0.1, width=5)  # 吊车梁
    pen.text(1.0, top - 0.45, L["crane"], small=True, anchor="lm")
    pen.line(cx, top - 0.1, cx, ground + ph + fc, width=2)  # 起重绳+吊钩（悬停位）
    pen.rect(cx - 1.2, ground, cx + 1.2, ground + ph)
    pen.text(cx, ground + ph / 2, L["pump"], anchor="mm")
    pen.text(cx + 1.45, ground + ph + fc / 2, L["clear"], color=DIM, small=True, anchor="lm")
    # 尺寸链（自地坪向上 e→f→x→a，地下 H2）；H1/H 取 state 值（铁律#1）
    x_dim = 9.4
    pen.dim_v(x_dim, ground, ground + ph, "e")
    pen.dim_v(x_dim, ground + ph, ground + ph + fc, "f")
    pen.dim_v(x_dim, ground + ph + fc, ground + ph + fc + rope, "x")
    pen.dim_v(x_dim, ground + ph + fc + rope, top, "a")
    pen.dim_v(x_dim, 0, ground, "H2")
    pen.dim_v(x_dim - 0.8, ground, top, "H1", value=h1)
    pen.text(4.6, top + 0.35, f"H={_fmt(htot)}m（H1={_fmt(h1)}m + H2={_fmt(h2)}m）", color=DIM, anchor="mm")


DIAGRAMS = [
    (FIG_723_SCREEN, L["screen_title"], draw_screen_lift),
    (FIG_821_BELL, L["bell"], draw_bell_mouth),
    (FIG_823_PUMPHOUSE, L["pumphouse_title"], draw_pumphouse),
]


def _load_font():
    """加载子集中文字体（OFL）。缺失 → 明确报错（比 PIL 默认字体豆腐块可诊断）。"""
    from PIL import ImageFont

    font_path = Path(__file__).resolve().parent.parent / "assets" / "NotoSansSC-subset.ttf"
    if not font_path.is_file():
        print(f"FONT_MISSING: {font_path}")
        return None
    return ImageFont.truetype(str(font_path), 34), ImageFont.truetype(str(font_path), 24)


# 各图绘图域（米）：ymax 须 ≥ 该图最大总高（泵房 9.185+标注余量）
EXTENTS = {
    FIG_723_SCREEN: (8.5, 6.2),
    FIG_821_BELL: (5.6, 5.0),
    FIG_823_PUMPHOUSE: (10.4, 10.2),
}


def render(fig_id: str, params: dict, outdir: Path) -> Path:
    from PIL import Image, ImageDraw

    fonts = _load_font()
    if fonts is None:
        raise RuntimeError("FONT_MISSING")
    font, font_small = fonts
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    xmax, ymax = EXTENTS[fig_id]
    scale = min((W - 220) / xmax, (H - 170) / ymax)
    pen = Pen(draw, font, font_small, scale, 100, H - 90)
    fn = dict((fid, f) for fid, _, f in DIAGRAMS)[fig_id]
    fn(params, pen)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / fig_filename(fig_id)
    img.save(out, "PNG")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="给排水计算书 — 参数驱动示意图生成器")
    ap.add_argument("--state", required=True, help="formula_state.json 路径")
    ap.add_argument("--outdir", required=True, help="图片输出目录（应为 /mnt/user-data/outputs/images）")
    ap.add_argument("--only", help="只画指定 fig_id（逗号分隔）")
    args = ap.parse_args()

    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    params = state.get("all_params") or state  # 兼容裸 params
    outdir = Path(args.outdir)
    wanted = [t for t in DIAGRAMS if not args.only or t[0] in args.only.split(",")]

    ok = 0
    for fig_id, _title, _fn in wanted:
        try:
            out = render(fig_id, params, outdir)
            print(f"DIAGRAM_FILE: {fig_id} images/{out.name}")
            ok += 1
        except KeyError as exc:
            print(f"DIAGRAM_SKIP: {fig_id} 缺参数 {exc}")
        except RuntimeError as exc:
            print(f"DIAGRAM_SKIP: {fig_id} {exc}")
            break  # 字体缺失对所有图相同，不必逐张重试
    print(f"DIAGRAMS_READY: {ok}")
    sys.exit(0 if ok > 0 else 1)


if __name__ == "__main__":
    main()
