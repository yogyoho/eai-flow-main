"""响应矩阵装配器(批十九 T3)——纯服务端零 LLM:tender_fields(抽取快照)→
response_matrix 行列表。确定性可 golden(同输入同输出,行序按 kind+clause_id
稳定排序)。只抄不编:requirement 摘录逐条来自抽取值,缺失路径不造行(F1
「block 类未抽出不允许进入生成」→ 缺行=下游可见缺口,不造假行)。

blocked 语义(F1 强制标红):source_path 的 fields_conf.verified=False 且
conf<0.6 → status=blocked(低置信未确认禁入生成);verified=True 或 conf 缺省
→ draft。★面(设计稿「三类强制标红」之一,M0 落两类):attachment_requirements
mandatory=="★" 行 + required_declarations 逐条行。
"""

from __future__ import annotations

_LOW_CONF = 0.6
_EXCERPT_CAP = 120


def _status_of(source_path: str, fields_conf: dict) -> str:
    entry = fields_conf.get(source_path) or {}
    conf = entry.get("conf")
    verified = bool(entry.get("verified"))
    if not verified and isinstance(conf, (int, float)) and conf < _LOW_CONF:
        return "blocked"
    return "draft"


def _excerpt(value) -> str:
    """要求摘录:标量直取;列表逐条 JSON 摘要;超长截断带省略号(只抄不编)。"""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                # 附件要求行摘录=名称+份数+来源(槽位富信息,provenance 另存全形)
                name = str(item.get("name") or "").strip()
                mandatory = str(item.get("mandatory") or "").strip()
                clause = str(item.get("clause") or "").strip()
                parts.append("、".join(x for x in (name, mandatory, clause) if x))
            else:
                parts.append(str(item))
        text = ";".join(p for p in parts if p)
    else:
        text = str(value)
    return text[:_EXCERPT_CAP] + ("…" if len(text) > _EXCERPT_CAP else "")


def _req_rows(value: list, source_path: str, prefix: str, fields_conf: dict) -> list[dict]:
    """列表型要求源逐条成行(附件要求/承诺条款);行内带 index 便于人工定位。
    ★ 逐行判定:仅附件行自身 mandatory=="★"(不继承包级——规格 is_star 按条款,
    包级继承会把「必需/建议」行误标红,首版 golden 抓到已修)。"""
    rows: list[dict] = []
    status = _status_of(source_path, fields_conf)
    for i, item in enumerate(value, 1):
        if isinstance(item, dict):
            row_star = source_path == "tender.attachment_requirements" and str(item.get("mandatory") or "").strip() == "★"
            requirement = _excerpt("; ".join(f"{k}={item.get(k)}" for k in ("no", "name", "clause", "mandatory", "min_count", "year_span") if item.get(k) not in (None, "")))
        else:
            row_star = False
            requirement = _excerpt(item)
        rows.append(
            {
                "clause_id": f"{prefix}:{i}",
                "kind": "attachment" if source_path == "tender.attachment_requirements" else "clause",
                "source_path": source_path,
                "requirement": requirement,
                "star": bool(row_star),
                "strategy": "pending",
                "target_section": "",
                "evidence_refs": [],
                "status": status,
            }
        )
    return rows


def _agg_row(clause_id: str, source_path: str, fields: dict, fields_conf: dict, label: str, *, star: bool = False) -> dict | None:
    """聚合要素行:路径有值才造行(缺路径=不造,下游据缺行见缺口)。"""
    value = fields.get(source_path)
    if value in (None, "", [], {}):
        return None
    return {
        "clause_id": clause_id,
        "kind": "aggregate",
        "source_path": source_path,
        "requirement": f"{label}:{_excerpt(value)}",
        "star": star,
        "strategy": "pending",
        "target_section": "",
        "evidence_refs": [],
        "status": _status_of(source_path, fields_conf),
    }


def assemble_matrix(tender_fields: dict, fields_conf: dict | None = None) -> list[dict]:
    """tender_fields(商务子集抽取快照)→ matrix 行 dict 列表(crud.replace_matrix 直落)。

    行源三类(F1):① attachment_requirements 逐条(★标红)② required_declarations
    逐条(★承诺条款面)③ 聚合要素行(保证金/截止/签章/章节/表格/字段/分册/资格门槛/
    质保工期对照/联合体/导出适配)。输出按 (kind, clause_id) 稳定排序。"""
    fields_conf = fields_conf or {}
    fields = tender_fields or {}
    rows: list[dict] = []

    reqs = fields.get("tender.attachment_requirements")
    if isinstance(reqs, list) and reqs:
        rows.extend(_req_rows(reqs, "tender.attachment_requirements", "att", fields_conf))

    decls = fields.get("tender.required_declarations")
    if isinstance(decls, list) and decls:
        rows.extend(_req_rows(decls, "tender.required_declarations", "decl", fields_conf))

    sigs = fields.get("tender.required_signatures")
    if isinstance(sigs, list) and sigs:
        rows.extend(_req_rows(sigs, "tender.required_signatures", "sign", fields_conf))

    aggregates = (
        ("deposit", "tender.deposit_required", "投标保证金", False),
        ("deadline", "tender.bid_deadline", "投标截止", False),
        ("scope", "tender.bid_scope", "招标范围", False),
        ("sections", "tender.required_sections", "必需章节", False),
        ("tables", "tender.required_tables", "必需表格", False),
        ("fields", "tender.required_fields", "必需字段", False),
        ("volume", "tender.volume_specs", "分册与份数", False),
        ("qual_level", "tender.required_qual_level", "资质等级门槛", False),
        ("perf_amount", "tender.min_performance_amount", "业绩金额门槛", False),
        ("perf_window", "tender.performance_window_months", "业绩年限窗口", False),
        ("warranty", "tender.min_warranty_period", "最低质保期", True),
        ("duration", "tender.max_duration", "最长交货期", True),
        ("consortium", "tender.consortium_allowed", "联合体", False),
        ("submit_methods", "tender.allowed_submit_methods", "递交方式", False),
        ("e_files", "tender.electronic_files", "电子标书要求", False),
    )
    for clause_id, path, label, star in aggregates:
        row = _agg_row(clause_id, path, fields, fields_conf, label, star=star)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: (r["kind"], r["clause_id"]))
    return rows
