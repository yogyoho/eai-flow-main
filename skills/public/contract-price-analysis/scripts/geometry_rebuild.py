"""几何网格重建: 表区域行级 token → rows/cell_bboxes(spec §2.2,计划 Task 3)。

输入 tokens 为页归一化(0~1)行级 OCR 结果 [{text, box:[x1,y1,x2,y2], score}]——
由 OCR 服务 _table_region 透出(裁剪偏移→页绝对像素)、
document_parser.parse_document 按页宽高归一化。算法:

  行: 正常高度 token 按 y-center 排序聚带(带宽 = token 高度中位数×0.6);
      高 token(高于中位行高 1.5 倍,纵跨≥2带的多行表头/合并格)不参与划带,
      按区间重叠落入所有覆盖带 → 各带同置(表头跨行由下游 _collapse_header
      合并去重,此处只要求 token 各落其带)。
  列: 行内相邻 token 大间隙(> 带宽)取中点为断点 → 全部断点(近邻去重)切分
      x 轴成全局列带(spec §2.2.2 断点检测)。跨带宽 token 桥接不融带——只要
      任一行把两列分开过,断点即存在;胶合对 gap < 带宽不产生断点,保持同带。
      token 按 x 落带;横跨多带者占首个空带、余带自然留空(colspan 占位空串,
      与 PP-Structure 展开语义一致,不与真实单列值抢格)。
  并格: 同行同带相邻 token x-gap < 带宽×0.5 才并一格('83.'+'91'→'83.91'
      撕裂重组);gap 达带宽量级('3466' '84605.06')→ 分成两格,PP-Structure
      胶合格在重建网格中天然消失(spec §2.2.4)。

输出与 TableExtract.rows/cell_bboxes 同构(归一化 0~1;rows 允许胶合分格导致
的锯齿,与 PP-Structure 展开行为一致,下游 x-band 路径按 bbox 对齐不受影响)。
放弃: 无可用 token / 行数==0 / 列数<3 → (None, None),调用方退回原表
(spec §2.4/§6 降级纪律)。本模块零外部依赖,任何异常由调用方 try/except 兜底。
"""

import re
from statistics import median

_GLUE_NUM = re.compile(r"\d[\d,，.]*\s+\d[\d,，.]*")

# 高 token 判定: 高于中位行高 1.5 倍视为纵跨多带的合并格 token(不参与行带划分)
_TALL_RATIO = 1.5


def has_glue_symptom(rows) -> bool:
    """P-1 病征: 任一 cell 文本含 ≥2 个空格分隔可解析数字('3466 84605.06')。"""
    return any(_GLUE_NUM.search(c or "") for row in rows or [] for c in row)


def _union_bb(toks: list) -> list:
    """token 簇 bbox 并集(归一化 0~1 [x1,y1,x2,y2])。"""
    return [
        min(t["x1"] for t in toks),
        min(t["y1"] for t in toks),
        max(t["x2"] for t in toks),
        max(t["y2"] for t in toks),
    ]


def rebuild_grid(tokens, ncols_hint=None):
    """token 阵列 → (rows, cell_bboxes),与 TableExtract 同构;放弃 → (None, None)。

    tokens: [{text, box:[x1,y1,x2,y2], score}](页归一化 0~1)。
    ncols_hint: 保留参数(预留列数校验,当前不消费——列数以聚类结果为准,
    行数下限由调用方 _GEOMETRY_MIN_ROWS_RATIO 把关)。"""
    toks: list = []
    for t in tokens or []:
        b = (t or {}).get("box") or []
        txt = ((t or {}).get("text") or "").strip()
        if len(b) >= 4 and txt and b[2] > b[0] and b[3] > b[1]:
            toks.append(
                {
                    "text": txt,
                    "x1": float(b[0]),
                    "y1": float(b[1]),
                    "x2": float(b[2]),
                    "y2": float(b[3]),
                }
            )
    if not toks:
        return None, None
    med_h = median(t["y2"] - t["y1"] for t in toks)
    if med_h <= 0:
        return None, None
    band = med_h * 0.6  # 行聚带 / 列并区间 共用带宽(≈一字符高/宽)
    merge_gap = band * 0.5  # 同带相邻 token 并格阈值

    # ── 行带: 正常高度 token 按 y-center 聚带(相邻 center 差 ≤ 带宽 → 同带) ──
    normal = [t for t in toks if (t["y2"] - t["y1"]) <= med_h * _TALL_RATIO]
    if not normal:
        return None, None  # 全是高 token,无法划带 → 放弃
    row_bands: list[list[dict]] = []
    for t in sorted(normal, key=lambda t: (t["y1"] + t["y2"]) / 2):
        yc = (t["y1"] + t["y2"]) / 2
        if row_bands:
            last = row_bands[-1][-1]
            if yc - (last["y1"] + last["y2"]) / 2 <= band:
                row_bands[-1].append(t)
                continue
        row_bands.append([t])
    row_iv = [[min(t["y1"] for t in b), max(t["y2"] for t in b)] for b in row_bands]

    def _nearest(iv: list, v: float) -> int:
        return min(range(len(iv)), key=lambda i: abs(v - (iv[i][0] + iv[i][1]) / 2))

    # ── 行带成员(全 token): 正常 token 归 center 所在带;高 token 归全部重叠带 ──
    band_members: list[list[dict]] = [list(b) for b in row_bands]
    for t in toks:
        yc = (t["y1"] + t["y2"]) / 2
        if (t["y2"] - t["y1"]) <= med_h * _TALL_RATIO:
            continue  # 划带时已入带
        r_hit = [ri for ri, (a, b) in enumerate(row_iv) if t["y1"] < b and t["y2"] > a]
        for ri in r_hit or [_nearest(row_iv, yc)]:
            band_members[ri].append(t)

    # ── 列带: 行带内相邻 token 大间隙(> 带宽)为断点区间;重叠区间合并后取中点
    #    切分 x 轴(不同行 token 宽度差会让中点漂移,取区间并才稳定)。
    #    高 token 参与所在带断点检测——纯 colspan 覆盖的列才能被分开。──
    cut_iv: list = []
    for members in band_members:
        toks_r = sorted(members, key=lambda t: t["x1"])
        for left, right in zip(toks_r, toks_r[1:]):
            if right["x1"] - left["x2"] > band:
                cut_iv.append([left["x2"], right["x1"]])
    cut_iv.sort()
    merged: list = []
    for lo, hi in cut_iv:
        if merged and lo - merged[-1][1] <= band:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    xmin = min(t["x1"] for t in toks)
    xmax = max(t["x2"] for t in toks)
    bounds = [xmin, *[(lo + hi) / 2 for lo, hi in merged], xmax]
    col_iv = [[a, b] for a, b in zip(bounds, bounds[1:]) if b > a]
    if len(col_iv) < 3:
        return None, None  # 列数 < 3 → 放弃
    ncols = len(col_iv)

    # ── 落格: 行取 center 所在带(高 token 取全部重叠带=rowspan 同置);
    #    列取重叠首带(colspan 占左格,余带留空=占位空串) ──
    placements: list = []
    for t in toks:
        yc = (t["y1"] + t["y2"]) / 2
        if (t["y2"] - t["y1"]) > med_h * _TALL_RATIO:
            r_hit = [ri for ri, (a, b) in enumerate(row_iv) if t["y1"] < b and t["y2"] > a] or [
                _nearest(row_iv, yc)
            ]
        else:
            r_hit = [_nearest(row_iv, yc)]
        c_hit = [ci for ci, (a, b) in enumerate(col_iv) if t["x1"] < b and t["x2"] > a] or [
            _nearest(col_iv, (t["x1"] + t["x2"]) / 2)
        ]
        placements.append((t, r_hit, c_hit))
    # 先落单列带 token,再落跨带 token——colspan 不与真实单列值抢格,
    # 占首个空带;全部被占才退回首带(并格兜底)。
    placements.sort(key=lambda p: len(p[2]))
    grid: dict = {}
    for t, r_hit, c_hit in placements:
        for ri in r_hit:
            if len(c_hit) == 1:
                target = c_hit[0]
            else:
                free = [ci for ci in c_hit if not grid.get((ri, ci))]
                target = free[0] if free else c_hit[0]
            grid.setdefault((ri, target), []).append(t)

    # ── 组装: 逐带逐列,簇内(相邻 x-gap < 并格阈值)并格,簇间分格 ──
    rows_out: list = []
    cbbs_out: list = []
    for ri in range(len(row_iv)):
        row_texts: list = []
        row_bbs: list = []
        for ci in range(ncols):
            members = grid.get((ri, ci)) or []
            if not members:
                row_texts.append("")
                row_bbs.append([0.0, 0.0, 0.0, 0.0])
                continue
            members.sort(key=lambda t: t["x1"])
            cluster = [members[0]]
            for t in members[1:]:
                if t["x1"] - cluster[-1]["x2"] < merge_gap:
                    cluster.append(t)
                else:
                    row_texts.append("".join(x["text"] for x in cluster))
                    row_bbs.append(_union_bb(cluster))
                    cluster = [t]
            row_texts.append("".join(x["text"] for x in cluster))
            row_bbs.append(_union_bb(cluster))
        rows_out.append(row_texts)
        cbbs_out.append(row_bbs)
    return rows_out, cbbs_out
