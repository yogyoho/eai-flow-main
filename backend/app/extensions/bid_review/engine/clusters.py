"""业绩条目确定性聚类(B立项 M4,spec §5,2026-11-05):纯服务端零 LLM。
三通道(裁决③):①归一化名全等 → 同组(P2 name 快路径保留);②ratio ≥ SIM_MERGE
且佐证(甲方/金额/日期任一相等)→ 并组 ok=true;③SIM_SUSPECT ≤ ratio < SIM_MERGE
且佐证 → 并组 ok=false(疑似同项,UNKNOWN 人工复核,禁强行 PARTIAL);
无佐证一律不并组(ratio 再高也不并,防同名不同项)。
输出 [{group_id, ok, members}];R2+ 规则以 len(ok=true 组)=确认去重数消费。
任一不确定配对落入组 → 整组降 ok=false(人工未决嫌疑不自动转正)。
"""

from difflib import SequenceMatcher

SIM_MERGE = 0.80
SIM_SUSPECT = 0.60


def _norm(s) -> str:
    """比较用归一:去全部空白 + casefold(中文名以字为单位,空白/全半角大小写不敏感)。"""
    return "".join(str(s).split()).casefold() if isinstance(s, str) else ""


def _corroborates(a: dict, b: dict) -> bool:
    """佐证 = 甲方/金额/日期任一归一相等(金额精确相等,日期串归一相等)。"""
    ca, cb = _norm(a.get("client")), _norm(b.get("client"))
    if ca and ca == cb:
        return True
    aa, ab = a.get("amount"), b.get("amount")
    if aa is not None and aa == ab:
        return True
    da, db = _norm(a.get("date")), _norm(b.get("date"))
    return bool(da) and da == db


def cluster_performance_entries(entries: list[dict] | None) -> list[dict]:
    """贪心单遍聚类:逐条目对既有组首成员(代表)判三通道,命中即入组;否则新组。
    # ponytail: O(n²) 代表比较,业绩条目 <10³ 量级够用;不够再上并查集全两两。
    """
    groups: list[dict] = []
    for ent in entries or []:
        n = _norm(ent.get("name")) if isinstance(ent, dict) else ""
        target: dict | None = None
        confident = True
        for g in groups:
            rep = g["members"][0]
            rep_n = _norm(rep.get("name"))
            if not n or not rep_n:
                continue
            if rep_n == n:  # 通道①:P2 name 快路径(全等)
                target, confident = g, True
                break
            ratio = SequenceMatcher(None, rep_n, n).ratio()
            if ratio >= SIM_MERGE and _corroborates(rep, ent):  # 通道②
                target, confident = g, True
                break
            if ratio >= SIM_SUSPECT and _corroborates(rep, ent):  # 通道③
                target, confident = g, False
                break
        if target is not None:
            target["members"].append(ent)
            target["ok"] = target["ok"] and confident
        else:
            groups.append({"group_id": f"G{len(groups) + 1}", "ok": True, "members": [ent]})
    return groups
