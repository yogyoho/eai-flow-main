# EAI-CUSTOM (geo-batch-cli, spec 2026-09-03): 报告题名解析器——report_id 自动编码与
# suggest-id 端点的共用纯函数。词表与技能层 build_output.MINERAL_ALIASES 语义一致
# （最早位置=主矿种、非金属/金属量负向），但两层部署域隔离须各自维护，改动须双向同步。
from __future__ import annotations

REGION_TAILS = ("省", "市", "区", "县", "旗", "盟")
STAGE_WORDS = [("普查", "survey"), ("详查", "detail"), ("勘探", "exploration")]
# 与 skills/public/geological-report/scripts/build_output.py MINERAL_ALIASES 双向同步（DNR）
MINERAL_KEYWORDS = [
    ("copper", ("铜",)),
    ("coal", ("煤",)),
    ("gold", ("金",)),
    ("iron", ("铁",)),
    ("lead_zinc", ("铅锌", "铅", "锌")),
]


def parse_region(title: str) -> str | None:
    """取最深一级区划尾字（省/市/区/县/旗/盟）截到的前缀（如「云南省昆明市东川区」），2-20 字。

    复合词守卫：尾字前一字符为 矿/城/发/景（矿区/城市/开发区/景区）时跳过该候选继续向前找。
    """
    skip_prev = ("矿", "城", "发", "景")
    best = None
    for i, ch in enumerate(title):
        if ch in REGION_TAILS and (i == 0 or title[i - 1] not in skip_prev):
            seg = title[: i + 1]
            if 2 <= len(seg) <= 20:
                best = seg
    return best


def parse_stage(title: str) -> str | None:
    """尾缀语义：取位置最大的阶段词（「勘探报告」在尾部）。勘查为泛词不映射。"""
    best_pos, best = -1, None
    for word, slug in STAGE_WORDS:
        pos = title.rfind(word)
        if pos > best_pos:
            best_pos, best = pos, slug
    return best


def parse_mineral(title: str) -> str | None:
    """已知限制（V1）：「五金建材」类生活词「金」会误报为 gold——地质题名域内不现实，接受。"""
    s = title.strip()
    if "非金属" in s:
        return None
    best_pos, best = -1, None
    for slug, keys in MINERAL_KEYWORDS:
        for k in keys:
            pos = s.find(k)
            if pos == -1:
                continue
            if k == "金" and pos + 1 < len(s) and s[pos + 1] == "属":
                continue  # 金属量/贵金属负向
            if best_pos == -1 or pos < best_pos:
                best_pos, best = pos, slug
    return best


def parse_title(title: str) -> dict:
    """已知限制（V1）：「五金建材」类生活词「金」会误报为 gold——地质题名域内不现实，接受。"""
    t = (title or "").strip().removesuffix(".docx").removesuffix(".pdf").removesuffix("报告")
    region = parse_region(t)
    mineral = parse_mineral(t)
    stage = parse_stage(t)
    confidence = "auto" if (mineral and stage) else "needs-review"
    return {"region": region, "mineral": mineral, "stage": stage, "confidence": confidence}
