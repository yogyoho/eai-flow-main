"""B立项 M5 交叉自检(纯服务端零 LLM,spec 2026-11-04 §5 M5 行,2026-11-05)。

§八三检 + §十指标的抽取侧四件,全部纯函数(复用 M4 clusters.py 先例:零配额、
确定性、单测全覆盖);产出落 payload["crosscheck"](非字段路径——universe/M0/
golden 零触碰,materials_hash 不含本报告):

- declarations(§八1 声明↔实体双向):missing=招标声明清单有、投标实体无(强
  MISSING 方向;裁决面在 L2-031 规则,本处是交叉报告面);extra=投标实体有、
  清单无(提示补清单,**不判 MISSING**——与 L2-031 `all` 而非 `set_eq` 语义对齐:
  清单外自附不算违规)。
- page_offset(§八2 页码偏移>5 降置信,消费 M2 offset_flag 形态):flag 命中时
  worker 对 page-bearing provenance 路径注记 fields_conf page_offset:true
  (annotate_page_offset;不覆盖 conf/verified)。gate/规则链自动消费挂账 R2+。
- copy_conflicts(正副本一致性,§八语义自定挂账原文复核):同一字段路径在 ≥2 个
  doc_id 观察到 ≥2 个归一不同非空值→advisory(不判违规;正本不可判定)。
- core_success_rate(§十指标,CORE_FIELDS 自定挂账原文校准):商业关键字段非 null 占比。

负证据覆盖 100%(§十)不在此:实现门禁在 attachments.py(M1),回归锁在
test_bid_review_crosscheck.py::TestNegativeEvidenceCoverageGate;issue 级结构化
上浮挂账 R2+。
"""

CORE_FIELDS = [
    "bid.total_price",
    "bid.total_price_words",
    "bid.validity_days",
    "bid.warranty_period",
    "bid.deposit_amount",
    "bid.commitment_completion_date",
    "bid.bid_letter_signatory",
    "bid.authorization_letter_present",
]


def run_crosscheck(fields: dict, candidates: dict | None = None) -> dict:
    """fields(+可选 candidates)→ 交叉自检报告。四键齐落,空输入给空壳(诚实零值)。"""
    fields = fields if isinstance(fields, dict) else {}
    return {
        "declarations": _declarations(fields),
        "page_offset": _page_offset(fields),
        "copy_conflicts": _copy_conflicts(candidates),
        "core_success_rate": _core_success_rate(fields),
    }


def _declarations(fields: dict) -> dict:
    req = {str(c).strip() for c in fields.get("tender.required_declarations") or []}
    req.discard("")
    got = {str(c).strip() for c in fields.get("bid.declaration_letter_codes") or []}
    got.discard("")
    return {"missing": sorted(req - got), "extra": sorted(got - req)}


def _page_offset(fields: dict) -> dict:
    rows = fields.get("bid.section_tree") or []
    offs = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("offset_flag") is True and isinstance(r.get("offset"), int):
            offs.append(r)
    return {
        "flag": bool(offs),
        "max_abs_offset": max((abs(r["offset"]) for r in offs), default=None),
        "affected_codes": [str(r.get("code") or "") for r in offs],
    }


def _copy_conflicts(candidates: dict | None) -> list[dict]:
    out = []
    for path, cands in (candidates or {}).items():
        by_doc: dict[str, set[str]] = {}
        for c in cands or []:
            if not isinstance(c, dict):
                continue
            v = str(c.get("value") or "").strip()
            d = str(c.get("doc_id") or "")
            if v:
                by_doc.setdefault(d, set()).add(v)
        values = {v for vs in by_doc.values() for v in vs}
        docs = sorted(d for d, vs in by_doc.items() if vs)
        if len(values) >= 2 and len(docs) >= 2:  # 跨文档且值分歧才算正副本冲突
            out.append({"path": str(path), "values": sorted(values), "doc_ids": docs})
    return out


def _core_success_rate(fields: dict) -> float:
    ok = sum(1 for p in CORE_FIELDS if fields.get(p) is not None)
    return round(ok / len(CORE_FIELDS), 4)


def annotate_page_offset(fields_conf: dict | None, provenance: dict | None, page_offset: dict | None) -> dict | None:
    """页偏移命中时,对 provenance page 非 null 的路径注记 page_offset:true
    (不覆盖 conf/verified——模型自报与服务端核验信号不污染)。未命中原样返回。"""
    if not (page_offset or {}).get("flag"):
        return fields_conf
    out: dict = {}
    for path, item in (fields_conf or {}).items():
        page = ((provenance or {}).get(path) or {}).get("page")
        out[path] = {**item, "page_offset": True} if page is not None else dict(item)
    return out
