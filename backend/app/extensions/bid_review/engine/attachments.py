"""L2 P1 附件清单匹配器(spec 2026-11-02 §2,EAI-CUSTOM):招标要求集 × 投标
提供集两级精确匹配。covers() 是子串语义不复用(spec §7)——名称通道要求归一后
**全等**,非包含,防「报价表」吞「分项报价表」;贪心一对一,一份提供项只归属
一个 req(先编号后名称)。P2 复合附件:带 sub_items 的 req 子件独立归组,分组失败降 UNKNOWN(spec §7)。
P3.2:子行 MISSING 同入近似门降 UNKNOWN,父行上卷+unknown_reason 戳记(spec 2026-11-03)。纯函数,pytest 全覆盖(test_bid_review_attachments.py)。"""

import difflib
import re
from typing import Any

from . import tuning

# 全角 ASCII(！-～)与表意空格 → 半角
_FULLWIDTH = {0x3000: 0x20, **{0xFF01 + i: 0x21 + i for i in range(94)}}
# 「附件N」「附件N-M」(阿拉伯/中文数字)序号前缀 + 紧随分隔符
_PREFIX_RE = re.compile(r"^附件[\d一二三四五六七八九十]+(?:[-–—][\d一二三四五六七八九十]+)?[、..::．]?\s*")

# L2 P3 同义词组(spec 2026-11-03 §3.1,EAI-CUSTOM):首元素=规范形;子串替换,
# 组内最长变体优先(防部分重叠吞字)。副本/复印件/回执/正本等方向不明变体**不入表**
# ——折叠进等值通道=静默升级 MATCHED,它们由 near-miss 门降 UNKNOWN 交人工。
# ponytail: 模块常量起步,>20 组外置 engine/dicts/synonyms.yaml。
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("营业执照", "企业法人营业执照"),
    ("审计报告", "年度审计报告"),
)


def _fold_synonyms(t: str) -> str:
    """组内变体子串替换到规范形;单遍按声明序,现数据组间无耦合(规范形不含他组变体)。"""
    for group in _SYNONYM_GROUPS:
        for variant in sorted(group[1:], key=len, reverse=True):
            if variant in t:
                t = t.replace(variant, group[0])
    return t


# L2 P3 近似命中门(spec 2026-11-03 §3.2,EAI-CUSTOM):平件 MISSING 行 × extra 池
# SequenceMatcher 相似度,≥门限降 UNKNOWN(near_miss)——归一化变体不得直接 fatal
# 缺失,交人工;真缺失仍 MISSING 但携带负证据佐证。标定:「中标通知书」vs
# 「中标通知书回执」ratio≈0.83 须入门,跨附件名对(中标通知书 vs 业绩合同)≈0.0
# 须门外;金标准 L2-020-near-miss 题 + 单测(含 tuning 覆盖生效钉)双向锁。
# L2 调参外置(spec 2026-11-03 §1,EAI-CUSTOM):门限/滤噪/截断三参外置
# engine/dicts/tuning.yaml,NEAR_MISS_GATE 常量退役——读 tuning.get,缺文件/坏值回落默认。


def _sim_cands(nm: str, pool: list[dict]) -> list[tuple[float, dict]]:
    """候选相似度降序;nm 或候选名归一为空则不参与(与通道②空名跳过同语义)。"""
    if not nm:
        return []
    return sorted(
        ((difflib.SequenceMatcher(None, nm, normalize_name(p.get("name"))).ratio(), p) for p in pool if normalize_name(p.get("name"))),
        key=lambda t: t[0],
        reverse=True,
    )


def _evidence(channels: list[str], pool: list[dict], cands: list[tuple[float, dict]]) -> dict:
    """行级负证据(spec §3.3):channels=实际尝试通道,pool=未占用提供项数,
    closest=相似度 top evidence_top_k(≥evidence_min_sim 滤噪;均 tuning 可调,
    L2 调参外置 spec 2026-11-03 §2,EAI-CUSTOM)。"""
    return {
        "channels": channels,
        "pool": len(pool),
        "closest": [{"no": str(p.get("no") or ""), "name": str(p.get("name") or ""), "sim": round(s, 4)} for s, p in cands[: int(tuning.get("evidence_top_k"))] if s >= float(tuning.get("evidence_min_sim"))],
    }


def _near_miss_pass(per_req: list[dict], extra: list[dict]) -> None:
    """就地降级扫描(spec §3.2):只读 extra 池不回写占用;复合父行(sub_results 在场)
    与 found>0 行跳过;req 名归一为空不进门,保持 MISSING。"""
    for e in per_req:
        if e.get("sub_results") is not None or e["found"] > 0:
            continue
        req = e["req"]
        no = str(req.get("no") or "").strip()
        nm = normalize_name(req.get("name"))
        channels = (["no"] if no else []) + (["name"] if nm else [])
        cands = _sim_cands(nm, extra)
        e["negative_evidence"] = _evidence(channels, extra, cands)
        if cands and cands[0][0] >= float(tuning.get("near_miss_gate")):
            e["status"] = "UNKNOWN"
            e["unknown_reason"] = "near_miss"


def normalize_name(value: Any) -> str:
    """全半角归一/去空白/剥「附件N」序号前缀/去尾冒号(spec §2)。非字符串 → 空串。"""
    if not isinstance(value, str):
        return ""
    t = value.strip().translate(_FULLWIDTH)
    t = re.sub(r"\s+", "", t)
    t = _PREFIX_RE.sub("", t)
    return _fold_synonyms(t.rstrip(":：..。"))


_SUB_STATUS_ORDER = {"UNKNOWN": 0, "MISSING": 1, "PARTIAL": 2, "MATCHED": 3}


def _refs_parent(parent_no: str, p_no: str) -> bool:
    """p_no 是否以「{parent_no}+分隔符(- – — . 、)」开头,即引用复合附件父件。"""
    return bool(parent_no and p_no and re.match(rf"^{re.escape(parent_no)}[-–—.、]", p_no))


def _status_for(found: int, min_count: int) -> str:
    """单项状态:0 份 MISSING;min_count>1 且不足 PARTIAL;其余 MATCHED。"""
    if found == 0:
        return "MISSING"
    if min_count > 1 and found < min_count:
        return "PARTIAL"
    return "MATCHED"


def _sub_items(req: dict) -> list[dict] | None:
    """复合门(加固):仅当 sub_items 是非空列表且每项皆 dict 才认复合件,返回该列表;
    否则 None → 一律走平件匹配(LLM 脏值如字符串/混入非 dict 不得误入复合通道,防
    「MATCHED,found=0」矛盾态)。三处门位与 _match_composite 共用本判定,防门判漂移。"""
    raw = req.get("sub_items")
    if not isinstance(raw, list) or not raw or not all(isinstance(s, dict) for s in raw):
        return None
    return raw


def _match_composite(req: dict, prov: list[dict], taken: set[int]) -> dict:
    """复合附件子件归组(L2 P2,spec 2026-11-02 §7 挂账行,EAI-CUSTOM):子件从
    「未被其它 req 两级匹配取走」的池独立归组,三通道按 D2 编号:① no 全等;
    ② {父号}-{序} 或 {父号}.{序}(1-based,序=子件在 sub_items 中的位置);
    ③ 名称归一全等。提供项引用了父件(no 以 {父号}+分隔符开头,或名称
    含父名)却归属不了任何子件 → 分组失败,父行 UNKNOWN(禁强行 PARTIAL)。
    零引用(什么都没提供)→ 诚实 MISSING,不算分组失败。
    归属成功与引用父件的孤儿项都就地写入 taken(调用方共享的占用池),既防后续
    req 偷项,也不进 extra(孤儿项归组进父件,交由 UNKNOWN 行人工复核)。"""
    subs = _sub_items(req) or []
    parent_no = str(req.get("no") or "").strip()
    parent_nm = normalize_name(req.get("name"))
    sub_results = []
    for idx, s in enumerate(subs, start=1):
        s_no = str(s.get("no") or "").strip()
        s_nm = normalize_name(s.get("name"))
        hits = 0
        for i, p in enumerate(prov):
            if i in taken:
                continue
            p_no = str(p.get("no") or "").strip()
            hit = (s_no and p_no == s_no) or (s_nm and normalize_name(p.get("name")) == s_nm)
            if not hit and parent_no and p_no:
                hit = p_no == f"{parent_no}-{idx}" or p_no == f"{parent_no}.{idx}"
            if hit:
                taken.add(i)
                hits += 1
        try:
            s_min = int(s.get("min_count") or 0)
        except (TypeError, ValueError):
            s_min = 0
        sub_results.append({"no": s_no, "name": str(s.get("name") or ""), "found": hits, "status": _status_for(hits, s_min)})
    orphan = False
    for i, p in enumerate(prov):
        if i in taken:
            continue
        p_no = str(p.get("no") or "").strip()
        refs_parent = _refs_parent(parent_no, p_no)
        if not refs_parent and parent_nm:
            refs_parent = parent_nm in normalize_name(p.get("name"))
        if refs_parent:
            orphan = True
            taken.add(i)
    # L2 P3 (spec 2026-11-03 §3.3,EAI-CUSTOM):子行 MISSING 记负证据;P3.2 (spec
    # 2026-11-03 §1.1,EAI-CUSTOM):同入近似门——sim≥near_miss_gate(tuning) 降 UNKNOWN(near_miss),
    # 父行经 _SUB_STATUS_ORDER 上卷。只读后处理不回写 taken,占用记账零触碰;
    # 真缺失(门外)仍 MISSING。证据池=orphan 归组后仍未占用者;父行
    # negative_evidence=None(分组失败是另一种证据形态,不混用)。
    untaken = [p for i, p in enumerate(prov) if i not in taken]
    for s in sub_results:
        if s["status"] == "MISSING":
            channels = (["no"] if s.get("no") else []) + (["name"] if normalize_name(s.get("name")) else [])
            cands = _sim_cands(normalize_name(s.get("name")), untaken)
            if cands and cands[0][0] >= float(tuning.get("near_miss_gate")):  # 门判定用 raw ratio,与平件门同规
                s["status"] = "UNKNOWN"
                s["unknown_reason"] = "near_miss"
            s["negative_evidence"] = _evidence(channels, untaken, cands)
    return {"sub_results": sub_results, "orphan": orphan}


def match_attachments(requirements: Any, provided: Any) -> dict:
    """两级精确匹配,贪心一对一:① no 全等(双方非空) ② normalize_name 全等。
    同一 req 可命中多份提供项(份数语义:min_count>1 且 found<min_count → PARTIAL)。
    状态:found==0→MISSING;否则见上;未匹配提供项→extra。
    P2 复合附件(spec 2026-11-02 §7):带非空 sub_items(非空列表且每项皆 dict,
    见 _sub_items)的 req 跳过两级主匹配,子件独立归组(_match_composite);父行
    状态 = UNKNOWN > MISSING > PARTIAL > MATCHED 上卷,found=子件命中数之和,
    父级 min_count 忽略。
    P3 (spec 2026-11-03):平件 found==0 行经 _near_miss_pass——近似候选 sim≥
    near_miss_gate(tuning) 降 UNKNOWN(near_miss),负证据(negative_evidence)一律记录。
    P3.2 (spec 2026-11-03):复合子行 MISSING 同入近似门降 UNKNOWN(near_miss),
    父行上卷 UNKNOWN 并带 unknown_reason 戳记(orphan 优先 grouping)。"""
    reqs = [r for r in (requirements or []) if isinstance(r, dict)]
    prov = [p for p in (provided or []) if isinstance(p, dict)]
    taken: set[int] = set()
    matched: list[list[int]] = [[] for _ in reqs]
    # ① 编号精确(双方非空;O(n²) 对几十行清单足够);复合 req 不参与,防父名/父号偷走子件
    for ri, r in enumerate(reqs):
        if _sub_items(r):
            continue
        no = str(r.get("no") or "").strip()
        if not no:
            continue
        for i, p in enumerate(prov):
            if i not in taken and str(p.get("no") or "").strip() == no:
                taken.add(i)
                matched[ri].append(i)
    # ② 规范化名称全等(非包含);引用复合父号的提供项(如 "3-1")保留给复合件
    #    归组,平件名称通道不得凭同名偷走(spec §7 平件/复合件互不偷项)
    comp_parent_nos = [str(r.get("no") or "").strip() for r in reqs if _sub_items(r)]
    comp_parent_nos = [n for n in comp_parent_nos if n]
    for ri, r in enumerate(reqs):
        if _sub_items(r):
            continue
        nm = normalize_name(r.get("name"))
        if not nm:
            continue
        for i, p in enumerate(prov):
            if i in taken:
                continue
            if any(_refs_parent(pn, str(p.get("no") or "").strip()) for pn in comp_parent_nos):
                continue
            if normalize_name(p.get("name")) == nm:
                taken.add(i)
                matched[ri].append(i)

    per_req = []
    for ri, r in enumerate(reqs):
        if _sub_items(r):
            comp = _match_composite(r, prov, taken)
            found = sum(s["found"] for s in comp["sub_results"])
            worst = min((s["status"] for s in comp["sub_results"]), key=lambda st: _SUB_STATUS_ORDER[st], default="MATCHED")
            if comp["orphan"]:
                per_req.append({"req": r, "matched": [], "found": found, "status": "UNKNOWN", "unknown_reason": "grouping", "negative_evidence": None, "sub_results": comp["sub_results"]})
            else:
                # L2 P3.2 (spec 2026-11-03 §1.2,EAI-CUSTOM):父行戳记=子行 near_miss 传播,
                # 供投影/att_check 分流消费;orphan 优先 grouping 不被覆盖(孤儿是父级事实)。
                sub_nm = any(s.get("unknown_reason") == "near_miss" for s in comp["sub_results"])
                per_req.append({"req": r, "matched": [], "found": found, "status": worst, "unknown_reason": "near_miss" if sub_nm else None, "negative_evidence": None, "sub_results": comp["sub_results"]})
            continue
        hits = [prov[i] for i in matched[ri]]
        found = len(hits)
        try:
            min_count = int(r.get("min_count") or 0)
        except (TypeError, ValueError):
            min_count = 0
        per_req.append({"req": r, "matched": hits, "found": found, "status": _status_for(found, min_count)})
    extra = [p for i, p in enumerate(prov) if i not in taken]
    _near_miss_pass(per_req, extra)  # L2 P3:近似命中降 UNKNOWN+行级负证据(spec 2026-11-03 §3.2,EAI-CUSTOM)
    return {"per_req": per_req, "extra": extra}


def build_checklist(requirements: Any, provided: Any, bid_doc_id: str | None = None) -> dict:
    """核对表投影原料(spec §4):match_attachments 结果摊平成 items 行(refs 注入
    bid 侧 doc_id——P1 refs=bid 侧首文档,调用方解析;解不到 → doc_id null,前端
    chip 降级纯文本)。counts 单一事实源;extra 提供项只进 extra_items 不产 issue。
    P2:复合行带 sub_results,分组失败行 status=UNKNOWN 进 counts.unknown。
    P3:行级 unknown_reason/negative_evidence 透传,counts.unknown 含 near_miss 降级。"""
    out = match_attachments(requirements, provided)
    items = []
    for e in out["per_req"]:
        req = e["req"]
        items.append(
            {
                "no": str(req.get("no") or ""),
                "name": str(req.get("name") or ""),
                "mandatory": req.get("mandatory"),
                "min_count": req.get("min_count"),
                "found": e["found"],
                "status": e["status"],
                "clause": req.get("clause"),
                "refs": [{"doc_id": bid_doc_id, "page": p.get("page")} for p in e["matched"]],
                "sub_results": e.get("sub_results") or [],
                "unknown_reason": e.get("unknown_reason"),
                "negative_evidence": e.get("negative_evidence"),
            }
        )
    counts = {
        "required": len(items),
        "matched": sum(1 for i in items if i["status"] == "MATCHED"),
        "partial": sum(1 for i in items if i["status"] == "PARTIAL"),
        "missing": sum(1 for i in items if i["status"] == "MISSING"),
        "unknown": sum(1 for i in items if i["status"] == "UNKNOWN"),
        "extra": len(out["extra"]),
    }
    extra_items = [{"name": str(p.get("name") or ""), "doc_id": bid_doc_id, "page": p.get("page")} for p in out["extra"]]
    return {"counts": counts, "items": items, "extra_items": extra_items}
