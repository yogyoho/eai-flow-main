#!/usr/bin/env python3
"""参数驱动示意图生成器（插图占位契约的图片侧）。

从 formula_state.json 的 all_params 读数，按样例工程制图风格绘制 3 张示意图（PNG），
落到 <outdir>/<12hex>.png —— 文件名固定（见 DIAGRAMS），SKILL.md 里的图片引用
逐字使用这些名字；docmgr Word 导出按相对引用 images/<name> 解析嵌图（bug-3004）。

用法：
    python render_diagrams.py --state formula_state.json --outdir /mnt/user-data/outputs/images
    python render_diagrams.py --state ... --outdir ... --only fig_821_bell_mouth

输出 marker（agent 依据）：
    DIAGRAMS_READY: <n>      成功张数，随后每行 DIAGRAM_FILE: <fig_id> <相对路径>
    DIAGRAM_SKIP: <fig_id> <原因>   缺参数/字体缺失时逐张跳过；全部失败 exit 1

铁律#1 同源：图上标注数值 = state JSON 值（本脚本只做格式化，不做任何计算）。
构图对齐样例（2026-08-30 深度还原，对齐样图 image9/10/11）：图1 工字梁侧视双线+小车轮
组十字中心+吊板/卷筒法兰+排绳剖面线+电机散热线+C 形吊钩+V 形吊索卸扣+网格滤网+左侧
尺寸链（延长线过线+45°斜刻）+H 箭头；图2 02S403 图集件风格（法兰双头螺栓+n-b×30°引出
线+锥壁剖面线+壁厚横壁小尺寸+点划中心线+D/D1 箭头尺寸）；图3 吊车梁搁墙顶+墙外埋土
斜刻+小车/吊钩块/C 形钩+吊离间隙箭头+蜗壳泵双圆十字中心线+底座剖面线+字母链+竖排字。
坐标一律米、y 向上，Pen 折算像素；箭头/刻度按像素定长（跨图比例一致）。
中文字体：assets/NotoSansSC-subset.ttf（OFL 许可，按本脚本 label 词表子集化）；
新增标注文字后须重跑子集化并把字符集同步进 assets/font_chars.txt（test_diagrams 锁）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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
    "underground": "地下式",
    "aboveground": "地上式",
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
    """PIL 绘图薄封装：线/箭头尺寸线/虚线/点划线/剖面线/文字。坐标一律米，由 scale 折算像素。"""

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

    def poly(self, pts, color=INK, width=3, close=False, dash=False):
        ps = [self.px(x, y) for x, y in pts]
        if close:
            ps.append(ps[0])
        if not dash:
            self.d.line(ps, fill=color, width=width, joint="curve")
            return
        for (xa, ya), (xb, yb) in zip(ps, ps[1:]):
            self.d.line([(xa, ya), (xb, yb)], fill=color, width=width)

    def ellipse(self, x, y, rx, ry, color=INK, width=3):
        cx, cy = self.px(x, y)
        rx, ry = rx * self.scale, ry * self.scale
        self.d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=color, width=width)

    def cross(self, x, y, r, color=INK, width=1):
        """十字中心线（轮/滑轮/孔的中心标记，样例惯例）。"""
        self.line(x - r, y, x + r, y, color=color, width=width)
        self.line(x, y - r, x, y + r, color=color, width=width)

    def arc(self, x, y, r, start, end, color=INK, width=3):
        """圆弧；角度制，PIL 约定（0°=右，顺时针为正，屏幕坐标）。"""
        cx, cy = self.px(x, y)
        rr = r * self.scale
        self.d.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=start, end=end, fill=color, width=width)

    def text(self, x, y, s, color=INK, small=False, anchor="mm"):
        self.d.text(self.px(x, y), s, fill=color, font=self.fs if small else self.f, anchor=anchor)

    def vtext(self, x, y, s, color=INK, small=False):
        """竖排文字：自 y 起逐字向下排（样例 地下式/地上式）。"""
        step = 0.52 if not small else 0.42
        for i, ch in enumerate(s):
            self.text(x, y - i * step, ch, color=color, small=small, anchor="mm")

    def rect(self, x1, y1, x2, y2, color=INK, width=3):
        """矩形（米坐标，取 min/max）。"""
        ax, ay = self.px(x1, y1)
        bx, by = self.px(x2, y2)
        self.d.rectangle([min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)], outline=color, width=width)

    def hatch(self, x1, y1, x2, y2, spacing=0.18, color=INK, width=1):
        """矩形带 45° 剖面线（土/混凝土剖面惯例）。"""
        ax, ay = self.px(min(x1, x2), max(y1, y2))  # 像素左上
        bx, by = self.px(max(x1, x2), min(y1, y2))  # 像素右下
        step = max(5, int(spacing * self.scale))
        w, h = bx - ax, by - ay
        k = 0
        while True:
            o = -h + k * step
            k += 1
            if o > w:
                break
            t0, t1 = max(0.0, float(-o)), min(float(h), float(w - o))
            if t1 <= t0:
                continue
            self.d.line([(ax + o + t0, ay + t0), (ax + o + t1, ay + t1)], fill=color, width=width)

    def centerline(self, x1, y1, x2, y2, color=INK, width=1):
        """点划中心线（长划-点-长划）。"""
        p1, p2 = self.px(x1, y1), self.px(x2, y2)
        ln = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if ln <= 0:
            return
        ux, uy = (p2[0] - p1[0]) / ln, (p2[1] - p1[1]) / ln
        pat = [(18, True), (6, False), (3, True), (6, False)]
        t, i = 0.0, 0
        while t < ln:
            seg, on = pat[i % 4]
            i += 1
            t2 = min(ln, t + seg)
            if on:
                self.d.line(
                    [(p1[0] + ux * t, p1[1] + uy * t), (p1[0] + ux * t2, p1[1] + uy * t2)],
                    fill=color,
                    width=width,
                )
            t = t2

    def _arrowhead(self, x, y, dx, dy, color=INK, size=None):
        # 箭头按像素定长（随图幅缩放微调），避免大比例图上箭头过大喧宾夺主
        n = math.hypot(dx, dy) or 1.0
        ux, uy = dx / n, dy / n
        wx, wy = -uy, ux
        tip = self.px(x, y)
        s = size if size is not None else max(9.0, 0.052 * self.scale)
        half = s * 0.36
        b1 = (tip[0] - ux * s + wx * half, tip[1] - uy * s + wy * half)
        b2 = (tip[0] - ux * s - wx * half, tip[1] - uy * s - wy * half)
        self.d.polygon([tip, b1, b2], fill=color)

    def leader(self, x1, y1, x2, y2, text="", color=INK, small=True, anchor="lm"):
        """引出线：起点文字 + 细线 + 指向端小箭头（样例 n-b×30°/壁厚注法）。"""
        self.line(x1, y1, x2, y2, color=color, width=1)
        self._arrowhead(x2, y2, x2 - x1, y2 - y1, color=color, size=max(7.0, 0.03 * self.scale))
        if text:
            self.text(x1, y1, text, color=color, small=small, anchor=anchor)

    def hatch_quad(self, pts, spacing=0.04, color=INK, width=1):
        """凸四边形带 45° 剖面线（喇叭口壁厚带等沿任意走向的窄带）。"""
        ps = [self.px(x, y) for x, y in pts]
        step = max(4, int(spacing * self.scale))
        xs = [p[0] for p in ps]
        ys = [p[1] for p in ps]
        edges = list(zip(ps, ps[1:] + ps[:1]))
        for c in range(min(ys) - max(xs), max(ys) - min(xs) + 1, step):
            hits = []
            for (xa, ya), (xb, yb) in edges:
                da, db = ya - xa - c, yb - xb - c
                if (da > 0) != (db > 0) or da == 0:
                    t = da / (da - db) if da != db else 0.0
                    hits.append((xa + (xb - xa) * t, ya + (yb - ya) * t))
            if len(hits) >= 2:
                hits.sort()
                self.d.line([hits[0], hits[-1]], fill=color, width=width)

    def soil(self, x1, x2, y, color=INK, width=1):
        """地面/室外地坪斜短刻（朝左下，样例土侧惯例）。"""
        span = x2 - x1
        k = max(1, int(abs(span) / 0.22))
        for i in range(k + 1):
            xx = x1 + span * i / k
            self.line(xx, y, xx - 0.13, y - 0.13, color=color, width=width)

    def soil_v(self, x, y1, y2, color=INK, width=1):
        """竖直墙/井壁外侧埋土斜短刻（沿墙面向下排布）。"""
        ya, yb = min(y1, y2), max(y1, y2)
        yy = yb - 0.22
        while yy > ya + 0.05:
            self.line(x, yy, x - 0.12, yy - 0.12, color=color, width=width)
            yy -= 0.25

    def dim_arrow(self, x1, y1, x2, y2, text="", tx=0.0, ty=0.0, anchor="mm", color=DIM):
        """箭头式尺寸线（两端实心箭头），text 相对中点偏移 (tx,ty)。"""
        self.line(x1, y1, x2, y2, color=color, width=2)
        self._arrowhead(x1, y1, x2 - x1, y2 - y1, color=color)
        self._arrowhead(x2, y2, x1 - x2, y1 - y2, color=color)
        if text:
            self.text((x1 + x2) / 2 + tx, (y1 + y2) / 2 + ty, text, color=color, small=True, anchor=anchor)

    def dim_v(self, x, y1, y2, label, value=None):
        """竖直尺寸线（45° 斜刻），label=值 写在线左侧（value 显式给 state 值，否则取坐标差）。"""
        self.line(x, y1, x, y2, color=DIM, width=2)
        for yy in (y1, y2):
            self.line(x - 0.05, yy - 0.05, x + 0.05, yy + 0.05, color=DIM, width=2)
        v = abs(y1 - y2) if value is None else value
        self.text(x - 0.12, (y1 + y2) / 2, f"{label}={_fmt(v)}", color=DIM, small=True, anchor="rm")

    def dim_h(self, y, x1, x2, label):
        self.line(x1, y, x2, y, color=DIM, width=2)
        for xx in (x1, x2):
            self.line(xx - 0.05, y - 0.05, xx + 0.05, y + 0.05, color=DIM, width=2)
        self.text((x1 + x2) / 2, y + 0.14, f"{label}={_fmt(abs(x1 - x2))}", color=DIM, small=True)

    def break_mark(self, x, y, vertical=False, color=INK, width=2):
        """折断符号：直线上的一对小斜折。"""
        if vertical:
            self.line(x, y + 0.12, x + 0.09, y, color=color, width=width)
            self.line(x + 0.09, y, x, y - 0.12, color=color, width=width)
        else:
            self.line(x - 0.12, y + 0.05, x, y - 0.05, color=color, width=width)
            self.line(x, y - 0.05, x + 0.12, y + 0.05, color=color, width=width)


def _p(params, key):
    v = params.get(key)
    if v is None and key not in params:
        # formula_state all_params 部分公式输出键带 formula_id 前缀（如 lift_rope_len.lift_rope_len），
        # 裸键缺失时按唯一后缀解析；后缀歧义视为缺失（宁可 skip 不猜值）
        hits = [val for k, val in params.items() if k.rsplit(".", 1)[-1] == key]
        if len(hits) == 1:
            v = hits[0]
    return None if v is None else float(v)


# ── 图1：滤网起吊示意（7.2.3） ────────────────────────────────────────────
# a 滑车+葫芦 / b 吊环 / c 滤网 / d 滤网底-平台顶 / e 平台顶标高；链和=起升高度。
# 样例构图（image9）：工字梁侧视双线（端部折断）+ 行走小车上排三组同心轮（十字中心线）
# + 远侧下排轮对 + 吊板双线 → 电动葫芦卷筒（两端法兰板 + 排绳 45° 剖面线）+ 电机
# （散热线 + 端环）→ 吊环 b → C 形大吊钩 → V 形吊索带卸扣挂网格滤网两上角；滤网悬于
# 操作平台开口上方，平台板双线带剖面线；左侧尺寸链延长线过尺寸线 + 45° 斜刻 + 总高 H。
def draw_screen_lift(params, pen: Pen) -> None:
    need = ["screen_hoist_len", "screen_ring_height", "screen_height", "screen_clearance", "platform_elev"]
    vals = {k: _p(params, k) for k in need}
    missing = [k for k, v in vals.items() if v is None]
    if missing:
        raise KeyError(",".join(missing))
    a, b, c, d, e = (vals[k] for k in need)
    sw = 2.2  # 滤网外形（宽取样例 2.2m 量级，仅示意比例）
    cx = 3.6
    sx0, sx1 = cx - sw / 2, cx + sw / 2
    top = e + d + c + b + a  # 梁底 = a+b+c+d+e 链顶
    sc_top = e + d + c  # 滤网顶
    # 地面（粗线 + 下方土剖面线）
    pen.line(0.3, 0, 7.6, 0, width=4)
    pen.hatch(0.3, -0.42, 7.6, 0, spacing=0.3)
    # 滤网井井壁（落到地面）+ 平台板双线带剖面线 + 折断
    pen.line(cx - 2.3, e, cx - 2.3, 0, width=4)
    pen.line(cx + 2.3, e, cx + 2.3, 0, width=4)
    pen.line(cx - 2.3, e, cx + 2.3, e, width=5)
    pen.line(cx - 2.3, e - 0.14, cx + 2.3, e - 0.14, width=2)
    pen.hatch(cx - 2.3, e - 0.14, cx + 2.3, e, spacing=0.12, width=1)
    pen.break_mark(cx - 2.3, (e + 0) / 2, vertical=True)
    pen.break_mark(cx + 2.3, (e + 0) / 2, vertical=True)
    pen.text(cx - 2.3, e + 0.22, L["platform"], small=True, anchor="lm")
    # 工字梁侧视（上下翼缘双线 + 端部折断）
    beam_h = 0.2
    pen.line(1.5, top, 5.9, top, width=4)
    pen.line(1.5, top + beam_h, 5.9, top + beam_h, width=4)
    for bxx in (1.5, 5.9):
        pen.line(bxx, top, bxx, top + beam_h, width=3)
        pen.break_mark(bxx, top + beam_h / 2, vertical=True)
    # 行走小车：侧板轮廓 + 上排 3 组同心轮（十字中心）+ 下排远侧轮对 + 轮轴
    wheel_y = top + beam_h / 2
    pen.ellipse(cx, wheel_y, 0.62, beam_h / 2 + 0.03, width=2)
    for wx in (cx - 0.5, cx, cx + 0.5):
        pen.ellipse(wx, wheel_y, 0.1, 0.1, width=2)
        pen.ellipse(wx, wheel_y, 0.055, 0.055, width=2)
        pen.cross(wx, wheel_y, 0.17, width=1)
    for wx in (cx - 0.35, cx + 0.35):
        pen.ellipse(wx, top - 0.09, 0.05, 0.05, width=2)
        pen.cross(wx, top - 0.09, 0.09, width=1)
    pen.line(cx - 0.35, top - 0.09, cx + 0.35, top - 0.09, width=2)
    # 吊板双线 → 卷筒（两端法兰板 + 排绳剖面线）→ 电机（散热线 + 端环）
    drum_y1 = top - 0.2
    drum_y0 = drum_y1 - 0.3
    for hx in (cx - 0.5, cx + 0.5):
        pen.line(hx - 0.04, top - 0.02, hx - 0.04, drum_y1, width=2)
        pen.line(hx + 0.04, top - 0.02, hx + 0.04, drum_y1, width=2)
    pen.rect(cx - 0.75, drum_y0, cx + 0.35, drum_y1, width=3)
    pen.ellipse(cx - 0.75, (drum_y0 + drum_y1) / 2, 0.06, (drum_y1 - drum_y0) / 2, width=3)
    for colx in (cx - 0.52, cx + 0.12):
        pen.rect(colx - 0.035, drum_y0 - 0.05, colx + 0.035, drum_y1 + 0.05, width=2)
    pen.hatch(cx - 0.46, drum_y0 + 0.02, cx + 0.08, drum_y1 - 0.02, spacing=0.055, width=1)
    pen.rect(cx + 0.35, drum_y0 + 0.04, cx + 0.95, drum_y1 - 0.04, width=3)
    for i in range(5):
        yy = drum_y0 + 0.08 + i * 0.048
        pen.line(cx + 0.39, yy, cx + 0.91, yy, width=1)
    pen.arc(cx + 0.95, (drum_y0 + drum_y1) / 2, (drum_y1 - drum_y0) / 2 - 0.04, 270, 90, width=3)
    pen.text(cx - 1.6, top + 0.42, L["hoist"], small=True, anchor="rm")
    # 吊挂链：链环 → 吊环 b（竖椭圆环）→ 大吊钩（C 形钩身 + 内卷钩尖）
    ring_y0 = drum_y0 - 0.1
    pen.line(cx, drum_y0, cx, ring_y0, width=3)
    pen.ellipse(cx, ring_y0 - b / 2, 0.06, b / 2 - 0.04, width=3)
    hook_cy = ring_y0 - b - 0.14
    pen.line(cx, ring_y0 - b, cx, hook_cy + 0.12, width=3)
    pen.arc(cx - 0.02, hook_cy, 0.15, 40, 320, width=3)
    pen.line(cx + 0.08, hook_cy + 0.14, cx - 0.03, hook_cy + 0.04, width=3)
    # V 形吊索挂滤网两上角（角上小卸扣）
    pen.line(cx, hook_cy - 0.15, sx0 + 0.05, sc_top + 0.08, width=3)
    pen.line(cx, hook_cy - 0.15, sx1 - 0.05, sc_top + 0.08, width=3)
    for shx in (sx0 + 0.05, sx1 - 0.05):
        pen.ellipse(shx, sc_top + 0.05, 0.05, 0.07, width=2)
    # 滤网：粗框 + 网格 + 竖点划中心线（贯通吊钩轴线，样例惯例）
    pen.rect(sx0, sc_top - c, sx1, sc_top, width=4)
    nx, ny = 16, 8
    for i in range(1, nx):
        xx = sx0 + sw * i / nx
        pen.line(xx, sc_top - c, xx, sc_top, width=1)
    for j in range(1, ny):
        yy = sc_top - c * j / ny
        pen.line(sx0, yy, sx1, yy, width=1)
    pen.centerline(cx, sc_top - c - 0.2, cx, drum_y0 - 0.3, width=1)
    pen.text(sx0 - 0.18, sc_top - c / 2, L["screen"], anchor="rm")
    # 左侧尺寸链 a/b/c/d/e（延长线过尺寸线 + 45° 刻度）+ 总高 H 箭头尺寸
    bounds = [0.0, e, e + d, e + d + c, e + d + c + b, top]
    seg_names = ["e", "d", "c", "b", "a"]
    seg_vals = [e, d, c, b, a]
    x_dim = 1.05
    for yy in bounds:
        pen.line(cx - 1.35, yy, x_dim - 0.15, yy, color=DIM, width=1)
    y_prev = bounds[0]
    for (name, v), yy in zip(zip(seg_names, seg_vals), bounds[1:]):
        pen.dim_v(x_dim, y_prev, yy, name, value=v)
        y_prev = yy
    h_state = _p(params, "screen_lift_height")  # state 值优先（铁律#1），缺失才退回链和
    hv = top if h_state is None else h_state
    pen.dim_arrow(x_dim - 0.75, 0, x_dim - 0.75, top, text="", color=DIM)
    pen.text(x_dim - 1.05, top / 2, f"H={_fmt(hv)}", color=DIM, small=True, anchor="rm")
    pen.text(6.2, top * 0.45, f"{L['lift_h']} H={_fmt(hv)}m", color=DIM, small=True, anchor="lm")
    # 段名图例（中文段名整行列在左下，尺寸线旁只留字母）
    pen.text(0.2, -0.35, "a滑车+葫芦 b吊环 c滤网 d滤网底-平台顶 e平台顶标高", small=True, anchor="lm")


# ── 图2：吸水喇叭口（8.2.1，02S403 图集件风格，样例 image10） ─────────────
# 样例构图：顶部短管 + 法兰板（两端双头螺栓穿上/穿下 + n-b×30° 引出线）、双线锥壁
# （壁间 45° 剖面线，壁厚 t 小尺寸横穿双壁）、点划竖中心线；箭头尺寸 D（上口=吸水管
# 径）/ D1（下口喇叭口径），延长线过尺寸线少许。安装间距 hb/hs/Lr/Ls 属池体布置
# 尺寸，由正文 5.4.3 校核叙述承载，不入本图（对齐样例）。
def draw_bell_mouth(params, pen: Pen) -> None:
    need = ["bell_mouth_D1", "DN_suction"]
    vals = {k: _p(params, k) for k in need}
    missing = [k for k, v in vals.items() if v is None]
    if missing:
        raise KeyError(",".join(missing))
    d1, dn = (vals[k] for k in need)
    d1m, dnm = d1 / 1000, dn / 1000  # mm → m（仅画幅比例，标注文本仍用 state 原值）
    cx = 1.8
    fl_y0, fl_y1 = 2.75, 2.9  # 法兰
    fl_w = max(dnm + 0.18, d1m * 0.82)
    cone_h = 1.5
    mo_y = fl_y0 - cone_h  # 下口
    # 上口短管（双线 + 顶口开口线）
    h_stub = 0.2
    pen.rect(cx - dnm / 2, fl_y1, cx + dnm / 2, fl_y1 + h_stub, width=3)
    # 法兰板 + 端部双头螺栓（穿上、穿下各露一截，样例画法）
    pen.rect(cx - fl_w / 2, fl_y0, cx + fl_w / 2, fl_y1, width=4)
    for bx in (cx - fl_w / 2 + 0.07, cx + fl_w / 2 - 0.07):
        for ya, yb in ((fl_y1, fl_y1 + 0.09), (fl_y0 - 0.08, fl_y0)):
            pen.line(bx - 0.014, ya, bx - 0.014, yb, width=2)
            pen.line(bx + 0.014, ya, bx + 0.014, yb, width=2)
    # 锥管：外轮廓双线（壁厚）+ 壁间 45° 剖面线 + 底口切线（内外双线示壁厚）
    top_w, bot_w = dnm + 0.1, d1m
    tin = 0.05
    for s in (-1, 1):
        pen.poly([(cx + s * top_w / 2, fl_y0), (cx + s * bot_w / 2, mo_y)], width=4)
        pen.poly([(cx + s * (top_w / 2 - tin), fl_y0), (cx + s * (bot_w / 2 - tin), mo_y)], width=2)
        pen.hatch_quad(
            [
                (cx + s * top_w / 2, fl_y0),
                (cx + s * (top_w / 2 - tin), fl_y0),
                (cx + s * (bot_w / 2 - tin), mo_y),
                (cx + s * bot_w / 2, mo_y),
            ],
            spacing=0.035,
            width=1,
        )
    pen.line(cx - bot_w / 2, mo_y, cx + bot_w / 2, mo_y, width=3)
    pen.line(cx - (bot_w / 2 - tin), mo_y, cx + (bot_w / 2 - tin), mo_y, width=1)
    pen.centerline(cx, mo_y - 0.35, cx, fl_y1 + h_stub + 0.25, width=1)
    # 壁厚 t：小尺寸横穿双壁（两端箭头各指内/外壁线，样例 δ 注法）
    my = (fl_y0 + mo_y) / 2
    xw_out = cx + top_w / 2 + (bot_w / 2 - top_w / 2) * (fl_y0 - my) / cone_h
    pen.dim_arrow(xw_out - tin - 0.01, my - 0.02, xw_out + 0.01, my + 0.02, text="t", tx=0.22, ty=0.1)
    # 箭头尺寸：上口 D（=吸水管径）/ 下口 D1（=喇叭口径），延长线过尺寸线少许
    yd = fl_y1 + h_stub + 0.42
    for xx in (cx - dnm / 2, cx + dnm / 2):
        pen.line(xx, fl_y1 + h_stub - 0.02, xx, yd + 0.1, color=DIM, width=1)
    pen.dim_arrow(cx - dnm / 2, yd, cx + dnm / 2, yd, text=f"D={_fmt(dn)}", ty=0.2)
    yb = mo_y - 0.3
    for xx in (cx - bot_w / 2, cx + bot_w / 2):
        pen.line(xx, mo_y - 0.02, xx, yb - 0.1, color=DIM, width=1)
    pen.dim_arrow(cx - bot_w / 2, yb, cx + bot_w / 2, yb, text=f"D1={_fmt(d1)}", ty=-0.24)
    # 法兰钻孔注法（样例 n-b×30°，n/b 按选型，不标数值；引出线指端部螺栓）
    pen.leader(cx - fl_w / 2 - 0.5, fl_y1 + 0.4, cx - fl_w / 2 + 0.07, fl_y1 + 0.07, text="n-b×30°", anchor="rm")
    pen.text(cx, mo_y - 0.78, f"{L['bell']}（02S403）", anchor="mm")


# ── 图3：泵房剖面（8.2.3，样例 image11） ────────────────────────────────
# H1 = a 滑车组 + x 起重绳 + f 吊离间隙 + e 泵高（自地坪向上链）；H = H1 + H2（地下）。
# 样例构图：吊车梁搁置墙顶（横贯出墙）+ 墙身双线（墙外埋土斜短刻）+ 室外地坪 +
# 吊车小车（箱形 + 卷筒圆）→ 起重绳 → 吊钩块（滑轮圆 + C 形钩，钩底悬停于泵顶上方
# f=吊离间隙）→ 蜗壳泵双圆 + 十字中心线 + 底座剖面线；竖直点划中心线贯通吊钩—泵轴；
# 右侧 e/f/x/a 字母链（45° 刻度）+ H2，左侧 H1/H 箭头尺寸，地下式/地上式竖排字。
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
    top = h1 + h2  # 吊车梁底 = H1 顶；H = H1 + H2
    xl, xr = 0.0, 10.0
    wt = 0.22  # 墙厚（画幅示意）
    wl, wr = xl + wt, xr - wt  # 墙内皮
    # 吊车梁搁置墙顶（双线横梁，横贯出墙，样例画法）
    pen.rect(xl - 0.2, top, xr + 0.2, top + 0.24, width=4)
    # 外墙（外粗线 + 内细线，不加剖面线）+ 墙外埋土斜短刻（地下段）
    for wx, wxx in ((xl, wl), (xr, wr)):
        pen.line(wx, 0, wx, top, width=4)
        pen.line(wxx, 0, wxx, top, width=2)
    pen.soil_v(xl, 0, ground, width=1)
    # 底板（粗线 + 下方剖面线）
    pen.line(xl - 0.2, 0, xr + 0.2, 0, width=4)
    pen.hatch(xl - 0.2, -0.3, xr + 0.2, 0, spacing=0.24)
    # 室内地坪（点划）+ 室外地面（墙外侧短线 + 土斜刻）+ 地下式/地上式竖排字
    pen.centerline(wl, ground, wr, ground, width=2)
    pen.text(wl + 0.35, ground - 0.3, L["ground"], small=True, anchor="lm")
    pen.line(-0.95, ground, xl, ground, width=3)
    pen.soil(-0.95, xl, ground, width=1)
    pen.line(xr, ground, xr + 0.55, ground, width=3)
    pen.soil(xr, xr + 0.55, ground, width=1)
    pen.vtext(xr + 0.9, ground + 1.35, L["aboveground"], small=True)
    pen.vtext(-1.25, ground - 0.5, L["underground"], small=True)
    # 竖直点划中心线：贯通吊车—吊钩—泵轴（样例惯例）
    cx = 5.0
    pen.centerline(cx, top + 0.3, cx, -0.35, width=1)
    # 吊车小车（箱形 + 卷筒圆 + 十字中心）贴梁底
    pen.rect(cx - 0.34, top - 0.3, cx + 0.34, top - 0.02, width=3)
    pen.ellipse(cx, top - 0.16, 0.16, 0.09, width=2)
    pen.cross(cx, top - 0.16, 0.22, width=1)
    pul_y = top - 0.44
    pen.ellipse(cx, pul_y, 0.1, 0.08, width=2)
    pen.cross(cx, pul_y, 0.14, width=1)
    # 滑车组吊钩块（滑轮圆）+ 起重绳 + C 形吊钩（悬停位：钩底 = 泵顶 + 吊离间隙 f）
    hook_y = ground + ph + fc
    blk_y1 = hook_y + 0.75
    blk_y0 = hook_y + 0.1
    pen.line(cx, top - 0.52, cx, blk_y1, width=2)
    pen.rect(cx - 0.12, blk_y0, cx + 0.12, blk_y1, width=3)
    pen.ellipse(cx, hook_y + 0.42, 0.07, 0.05, width=2)
    pen.cross(cx, hook_y + 0.42, 0.1, width=1)
    pen.line(cx, blk_y0, cx, hook_y + 0.02, width=3)
    pen.arc(cx - 0.02, hook_y - 0.06, 0.13, 40, 320, width=3)
    pen.line(cx + 0.06, hook_y + 0.05, cx - 0.04, hook_y - 0.03, width=3)
    pen.text(cx - 0.6, top - 0.55, L["crane"], small=True, anchor="rm")
    pen.text(cx + 0.15, (top - 0.52 + blk_y1) / 2, L["rope"], color=DIM, small=True, anchor="lm")
    # 吊离间隙 f：钩底 → 泵顶小箭头尺寸 + 文字
    pen.dim_arrow(cx + 0.5, ground + ph, cx + 0.5, hook_y, text="", color=DIM)
    pen.text(cx + 0.62, (ground + ph + hook_y) / 2, L["clear"], color=DIM, small=True, anchor="lm")
    # 蜗壳泵：底座板（剖面线）+ 梯形支座 + 双圆泵壳 + 十字中心线（画幅总高≈e 链段）
    pen.rect(cx - 0.62, ground, cx + 0.62, ground + 0.1, width=3)
    pen.hatch(cx - 0.62, ground, cx + 0.62, ground + 0.1, spacing=0.07, width=1)
    pen.poly([(cx - 0.5, ground + 0.1), (cx - 0.28, ground + 0.26), (cx + 0.28, ground + 0.26), (cx + 0.5, ground + 0.1)], width=3)
    cyc = ground + 0.26 + 0.62
    pen.ellipse(cx, cyc, 0.62, 0.62, width=4)
    pen.ellipse(cx, cyc, 0.44, 0.44, width=2)
    pen.centerline(cx - 0.85, cyc, cx + 0.85, cyc, width=1)
    pen.text(cx + 0.85, cyc + 0.45, L["pump"], small=True, anchor="lm")
    # 右侧字母尺寸链 e/f/x/a + H2（延长线过尺寸线 + 45° 刻度）
    x_dim = 9.4
    bounds = [0.0, ground, ground + ph, ground + ph + fc, ground + ph + fc + rope, top]
    segs = [("e", ph), ("f", fc), ("x", rope), ("a", aa)]
    for yy in bounds:
        pen.line(cx + 1.25, yy, x_dim - 0.15, yy, color=DIM, width=1)
    y_prev = bounds[1]
    for (name, v), yy in zip(segs, bounds[2:]):
        pen.dim_v(x_dim, y_prev, yy, name, value=v)
        y_prev = yy
    pen.dim_v(x_dim, 0, ground, "H2", value=h2)
    # 左侧箭头尺寸：H1（地坪→梁底）与 H（全高，state 值优先）+ 延长线
    for yy in (ground, top):
        pen.line(wl, yy, -0.75, yy, color=DIM, width=1)
    pen.dim_arrow(0.75, ground, 0.75, top)
    pen.text(0.58, (ground + top) / 2, f"H1={_fmt(h1)}", color=DIM, small=True, anchor="rm")
    pen.dim_arrow(-0.6, 0, -0.6, top)
    pen.text(-0.72, top * 0.6, f"H={_fmt(htot)}m", color=DIM, small=True, anchor="rm")
    pen.text(4.9, top + 0.55, f"H={_fmt(htot)}m（H1={_fmt(h1)}m + H2={_fmt(h2)}m）", color=DIM, anchor="mm")


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
    FIG_723_SCREEN: (8.6, 6.4),
    FIG_821_BELL: (4.2, 3.6),
    FIG_823_PUMPHOUSE: (11.0, 10.4),
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
    scale = min((W - 260) / xmax, (H - 200) / ymax)
    pen = Pen(draw, font, font_small, scale, 170, H - 100)
    fn = dict((fid, f) for fid, _, f in DIAGRAMS)[fig_id]
    fn(params, pen)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / fig_filename(fig_id)
    img.save(out, "PNG")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="给排水计算书 — 参数驱动示意图生成器")
    ap.add_argument("--state", default="/mnt/user-data/workspace/formula_state.json", help="formula_state.json 路径（默认沙箱 canonical 路径）")
    ap.add_argument("--outdir", default="/mnt/user-data/outputs/images", help="图片输出目录（默认 /mnt/user-data/outputs/images）")
    ap.add_argument("--only", help="只画指定 fig_id（逗号分隔）")
    # bug-3017：agent 会幻觉出 --report/--output-dir 等不存在的旗标——忽略未知参数照常出图，
    # 不给 argparse 报错→自造 DIAGRAMS_SKIPPED 的机会
    args, unknown = ap.parse_known_args()
    if unknown:
        print(f"DIAGRAM_NOTE: 忽略未知参数 {unknown}（合法旗标仅 --state/--outdir/--only）")

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
