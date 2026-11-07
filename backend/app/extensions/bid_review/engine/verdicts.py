# EAI-CUSTOM(P1-β批三 2026-11-07,C-08 值域三拆终章):verdict 引擎五值域。
# 引擎判定域 = FAIL|PASS|UNKNOWN|ERROR|SKIP;false_positive = 复核域值(A8),
# 仍落 verdict 列但非引擎产出;历史三值 violation/need_human/unclear 经
# normalize_verdict 单向归一(golden loader/DB remap/评测读面共用;先例 =
# C-05/C-22 MATCHED→PRESENT 别名归一,夹具与存量裁决记录零改动)。
VERDICT_FAIL = "FAIL"
VERDICT_PASS = "PASS"
VERDICT_UNKNOWN = "UNKNOWN"
VERDICT_ERROR = "ERROR"
VERDICT_SKIP = "SKIP"
VERDICT_DOMAIN = (VERDICT_FAIL, VERDICT_PASS, VERDICT_UNKNOWN, VERDICT_ERROR, VERDICT_SKIP)

# 旧值→新值(单向;新值与复核域 false_positive 恒等透传;未知串原样返回=防御)
_VERDICT_ALIASES = {
    "violation": VERDICT_FAIL,
    "pass": VERDICT_PASS,
    "need_human": VERDICT_UNKNOWN,
    "unclear": VERDICT_UNKNOWN,
}


def normalize_verdict(v: str | None) -> str:
    """旧三值→引擎五值;新五值/false_positive/未知串恒等返回。"""
    s = str(v or "")
    return _VERDICT_ALIASES.get(s, s)
