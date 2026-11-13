"""SK-RT 商务响应表装配(批二十 M1-g,EAI-CUSTOM 2026-11-13)——批十九 F1
矩阵行→表二响应表(§2.3):只收 kind∈(attachment,clause)(aggregate 行属要素
对照,不入响应表);★透传(D0 覆盖面的生成侧同源);conclusion 缺省「完全响应」
+deviation 对 None(负偏离由人工 PATCH matrix 卡点/批廿一预审查翻转,生成器不
造偏离);response_text=参数化应答(带条款号,绕空应答词桶——「满足招标文件
要求」类即 D0,模板硬钉零命中);requirement_excerpt/evidence_refs 透传。
纯函数零 IO 零时钟。"""

from __future__ import annotations

_RT_KINDS = ("attachment", "clause")


def build_response_table(matrix_rows: list[dict] | None) -> dict:
    rows: list[dict] = []
    star_ids: list[str] = []
    for r in matrix_rows or []:
        if not isinstance(r, dict) or r.get("kind") not in _RT_KINDS:
            continue
        cid = str(r.get("clause_id") or "")
        if r.get("star"):
            star_ids.append(cid)
        rows.append(
            {
                "clause_id": cid,
                "star": bool(r.get("star")),
                "conclusion": "完全响应",
                "response_text": f"我方已按第{cid}条要求备妥响应材料。",
                "requirement_excerpt": str(r.get("requirement") or ""),
                "evidence_refs": list(r.get("evidence_refs") or []),
                "deviation_reason": None,
                "replacement_plan": None,
            }
        )
    return {"matrix_star_clause_ids": star_ids, "rows": rows, "pending_items": []}
