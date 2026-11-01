"""L2 P1 附件清单匹配器(spec 2026-11-02 §2,EAI-CUSTOM):招标要求集 × 投标
提供集两级精确匹配。covers() 是子串语义不复用(spec §7)——名称通道要求归一后
**全等**,非包含,防「报价表」吞「分项报价表」;贪心一对一,一份提供项只归属
一个 req(先编号后名称)。纯函数,pytest 全覆盖(test_bid_review_attachments.py)。"""

import re
from typing import Any

# 全角 ASCII(！-～)与表意空格 → 半角
_FULLWIDTH = {0x3000: 0x20, **{0xFF01 + i: 0x21 + i for i in range(94)}}
# 「附件N」「附件N-M」(阿拉伯/中文数字)序号前缀 + 紧随分隔符
_PREFIX_RE = re.compile(r"^附件[\d一二三四五六七八九十]+(?:[-–—][\d一二三四五六七八九十]+)?[、..::．]?\s*")


def normalize_name(value: Any) -> str:
    """全半角归一/去空白/剥「附件N」序号前缀/去尾冒号(spec §2)。非字符串 → 空串。"""
    if not isinstance(value, str):
        return ""
    t = value.strip().translate(_FULLWIDTH)
    t = re.sub(r"\s+", "", t)
    t = _PREFIX_RE.sub("", t)
    return t.rstrip(":：..。")


def match_attachments(requirements: Any, provided: Any) -> dict:
    """两级精确匹配,贪心一对一:① no 全等(双方非空) ② normalize_name 全等。
    同一 req 可命中多份提供项(份数语义:min_count>1 且 found<min_count → PARTIAL)。
    状态:found==0→MISSING;否则见上;未匹配提供项→extra。"""
    reqs = [r for r in (requirements or []) if isinstance(r, dict)]
    prov = [p for p in (provided or []) if isinstance(p, dict)]
    taken: set[int] = set()
    matched: list[list[int]] = [[] for _ in reqs]
    # ① 编号精确(双方非空;O(n²) 对几十行清单足够)
    for ri, r in enumerate(reqs):
        no = str(r.get("no") or "").strip()
        if not no:
            continue
        for i, p in enumerate(prov):
            if i not in taken and str(p.get("no") or "").strip() == no:
                taken.add(i)
                matched[ri].append(i)
    # ② 规范化名称全等(非包含)
    for ri, r in enumerate(reqs):
        nm = normalize_name(r.get("name"))
        if not nm:
            continue
        for i, p in enumerate(prov):
            if i not in taken and normalize_name(p.get("name")) == nm:
                taken.add(i)
                matched[ri].append(i)

    per_req = []
    for ri, r in enumerate(reqs):
        hits = [prov[i] for i in matched[ri]]
        found = len(hits)
        try:
            min_count = int(r.get("min_count") or 0)
        except (TypeError, ValueError):
            min_count = 0
        if found == 0:
            status = "MISSING"
        elif min_count > 1 and found < min_count:
            status = "PARTIAL"
        else:
            status = "MATCHED"
        per_req.append({"req": r, "matched": hits, "found": found, "status": status})
    return {"per_req": per_req, "extra": [p for i, p in enumerate(prov) if i not in taken]}
