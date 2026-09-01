# EAI-CUSTOM: geo-sample-bank Phase 1 脱敏规则引擎（spec 2026-09-01 §3.3）。
# 两档制：auto=替换为 MASK；review=只记事件不替换。红线：不含任何匹配地质数值的规则——
# 品位/厚度/资源量/涌水量等数字必须原样保留（脱敏会毁掉 SL3 指纹库与深度标定）。
from __future__ import annotations

import hashlib
import re

MASK = "****"


def _p(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(pattern, flags)


# 边界约定：不用 \b，用 ASCII 环视（(?<![0-9A-Za-z]) / (?![0-9]) 等）——Python re 的 Unicode 模式下
# CJK 汉字属于 \w，"探矿权证号C530000…"、"联系电话13812345678" 里 \b 永不成立，规则会整段漏配。
RULES: list[tuple[str, re.Pattern[str], str]] = [
    # ── auto 档：身份类，直接替换 ──
    ("exploration_cert", _p(r"(?<![0-9A-Za-z])C\d{10,16}(?![0-9])"), "auto"),  # 探矿许可证号（bug-2216 形态 C+行政区划+年+序号）
    ("uscc", _p(r"(?<![0-9A-Za-z])(?=[0-9A-HJ-NPQRTUWXY]*[A-HJ-NPQRTUWXY])[0-9A-HJ-NPQRTUWXY]{18}(?![0-9A-Za-z])"), "auto"),  # 统一社会信用代码（至少含一个字母，纯 18 位数字不误配）
    ("coord_pair", _p(r"X\s*[:：]?\s*\d{6,8}(?:\.\d+)?\s*[,，、]\s*Y\s*[:：]?\s*\d{6,8}(?:\.\d+)?", re.I), "auto"),  # 高斯 XY 对
    ("latlon", _p(r"(?<!\d)\d{1,3}°\d{1,2}(?:′\d{1,2}(?:\.\d+)?)?″?\s*[NSEW]"), "auto"),  # 经纬度（带方位字母；(?<!\d) 防止从长数字串中截段）
    ("phone", _p(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "auto"),
    ("tel", _p(r"(?<![0-9A-Za-z])0\d{2,3}-\d{7,8}(?![0-9A-Za-z])"), "auto"),
    ("email", _p(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "auto"),
    ("org_name", _p(r"[一-龥（）()]{2,24}(?:有限公司|股份有限公司|集团有限公司|勘查院|勘察院|研究院|设计院|地质队|地质大队)"), "auto"),
    # ── review 档：高误报，只标记待审 ──
    ("person_field", _p(r"(?:负责人|编制人|审核人|审查人|项目经理|技术负责人)[：:]\s*[一-龥]{2,4}"), "review"),
]


def redact_text(md: str) -> tuple[str, list[dict]]:
    """返回 (脱敏后文本, 事件列表)。事件含 rule/mode/start/end/original_hash/replaced。"""
    spans: list[tuple[int, int, str, str]] = []  # (start, end, rule, mode)
    for rule, rx, mode in RULES:
        for m in rx.finditer(md):
            spans.append((m.start(), m.end(), rule, mode))
    # 重叠消解：按 start 升序、end 降序保留最先/最长者
    spans.sort(key=lambda s: (s[0], -s[1]))
    kept: list[tuple[int, int, str, str]] = []
    for s in spans:
        if kept and s[0] < kept[-1][1]:
            continue
        kept.append(s)

    events: list[dict] = []
    out = md
    for start, end, rule, mode in reversed(kept):  # 从尾向头替换，偏移不失效
        original = md[start:end]
        replaced = mode == "auto"
        if replaced:
            out = out[:start] + MASK + out[end:]
        events.append(
            {
                "rule": rule,
                "mode": mode,
                "start": start,
                "end": end,
                "original_hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "replaced": replaced,
            }
        )
    events.reverse()  # 恢复文档顺序
    return out, events
