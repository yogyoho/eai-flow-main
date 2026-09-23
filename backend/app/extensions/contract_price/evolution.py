"""cpa → agent_learnings 捕获桥（D-1 文档字段 / D-3 行字段，补遗 2026-09-22）。

EAI-CUSTOM: 自进化循环设计 docs/designs/self-improving-loop-port.md 补遗。

零触碰约束（learnings/models.py: gateway 不得 import learnings 模块，表归 MCP
子进程 create_all）：本模块用原生 SQL 写**已存在**的 agent_learnings 表，复刻
mint_or_fold 的折叠语义（D12: 命中无条件 recurrence+1；resolved 重开、dismissed
尊重人工裁决不动），不 import 模块、不建表。表不存在（learnings 未初始化）时
静默降级——修正是主操作，捕获只是养料。
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import text

logger = logging.getLogger(__name__)

# learnings 枚举的合法子集（patterns.py KINDS/AREAS），本地字面量对齐——故意不
# import（零触碰）；枚举漂移由 learnings 侧 surface/stats 兜底显示。
_KIND = "correction"
_AREA = "data"

# 与 service.mint_or_fold 等价的 upsert：命中即 count+1（D12），resolved 重开、
# dismissed 不动；details 折叠时以最新样例覆盖——D-1/D-3 是数据承载型捕获，
# 评审需要近例（工具错误型"首例即足够"的语义不适用于字段修正）。
# suggested_action 必须显式给 ''：Mapped[str] NOT NULL 且默认只在 ORM 层，原生
# INSERT 漏它会炸非空约束（真机 e2e 抓过）。
_UPSERT_SQL = text(
    """
    INSERT INTO agent_learnings
        (id, user_id, kind, area, symptom, pattern_key, summary, details,
         suggested_action, status, recurrence_count, first_seen_at, last_seen_at,
         distinct_thread_count, source_thread_ids, source)
    VALUES
        (:id, :user_id, :kind, :area, :symptom, :pattern_key,
         :summary, :details, '', 'pending', 1, now(), now(), 0, '', 'agent')
    ON CONFLICT (user_id, pattern_key) DO UPDATE SET
        recurrence_count = agent_learnings.recurrence_count + 1,
        last_seen_at = now(),
        status = CASE WHEN agent_learnings.status = 'resolved'
                      THEN 'pending' ELSE agent_learnings.status END,
        details = EXCLUDED.details
    """
)


def classify_error_pattern(old: str, new: str) -> str:
    """错误模式粗分类（补遗 D-3: 粘连/错位/单位/命名变体/漏提）。"""
    if not old:
        return "missed"
    if not new:
        return "cleared"
    o, n = old.strip(), new.strip()
    d_old, d_new = re.sub(r"\D", "", o), re.sub(r"\D", "", n)
    if d_old and d_new and d_old != d_new:
        if sorted(d_old) == sorted(d_new):
            return "digit-transposed"
        if d_new in d_old or d_old in d_new:
            return "digit-split"
        return "digit-drift"
    norm = re.compile(r"[\s()（）\-—_]").sub
    if norm("", o).lower() == norm("", n).lower():
        return "variant"
    if n.startswith(o) or o.startswith(n) or n.endswith(o) or o.endswith(n):
        return "unit-affixed"
    return "other"


async def capture_field_correction(
    session,
    *,
    user_id: str | None = None,
    scope: str,
    field: str,
    old_value,
    new_value,
    doc_hash: str | None = None,
    error_pattern: str | None = None,
) -> None:
    """一次人工字段修正 → ledger 一条（kind=correction / area=data）。

    折叠键 = (user, data.<scope>field-<field>)：同字段修正跨文档折叠，
    recurrence 达到晋升阈值即进入人工评审（D7 晋升走 skill_manage 管线）。
    身份对齐 learnings MCP（D5 cwd 推导的 core runtime user id）：harness
    contextvar 有真 id 时优先，否则退回调用方传入的扩展侧 id。任何异常只记
    warning，绝不影响主流程。
    """
    resolved = None
    try:
        from deerflow.runtime.user_context import get_effective_user_id

        candidate = get_effective_user_id()
        if candidate and candidate != "default":
            resolved = candidate
    except Exception:  # noqa: BLE001 — 身份解析失败退回显式值
        pass
    resolved = resolved or user_id or "default"
    symptom = f"{scope}field-{field}"
    doc_tag = f" doc={doc_hash[:12]}" if doc_hash else ""
    pattern_tag = f" [{error_pattern}]" if error_pattern else ""
    params = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "kind": _KIND,
        "area": _AREA,
        "symptom": symptom,
        "pattern_key": f"{_AREA}.{symptom}",
        "summary": f"cpa {scope} 字段 {field} 人工修正",
        "details": f"{pattern_tag}{doc_tag} {old_value!r} -> {new_value!r}"[:4000],
    }
    try:
        await session.execute(_UPSERT_SQL, params)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 — 捕获永不影响主流程
        logger.warning("cpa evolution capture skipped (%s): %s", symptom, exc)


# --- ⑥ 落地工作流: 候选列表 + 晋升/忽略（补遗 2026-09-22） -------------------

_DETAILS_RE = re.compile(r"^\s*\[(?P<pat>[^\]]*)\]\s*(?:doc=(?P<doc>\S+))?\s*(?P<rest>.*)$")

_CANDIDATES_SQL = text(
    """
    SELECT id, pattern_key, recurrence_count, details,
           first_seen_at, last_seen_at
    FROM agent_learnings
    WHERE pattern_key LIKE 'data.%' AND status = 'pending'
    ORDER BY recurrence_count DESC, last_seen_at DESC
    LIMIT :limit
    """
)

_SET_STATUS_SQL = text(
    """
    UPDATE agent_learnings
    SET status = :status
    WHERE id = :id AND pattern_key LIKE 'data.%'
    """
)

_DOC_ANCHORS_SQL = text(
    """
    SELECT COALESCE(parse_meta -> 'suggested_anchors', '{}'::jsonb)::text AS anchors
    FROM cpa_documents
    WHERE file_hash LIKE :prefix
    LIMIT 1
    """
)


async def list_candidates(session, *, limit: int = 50) -> list[dict]:
    """pending 的 data.* 修正候选（recurrence 降序），附文档级 L4 建议锚词。

    ⑥ 工作流: 证据面板在配置页种子规则卡旁——人照着证据把锚词写进规则卡、
    保存,然后一键标记晋升;或者忽略。"""
    import json as _json

    rows = (
        await session.execute(_CANDIDATES_SQL, {"limit": limit})
    ).mappings().all()
    out: list[dict] = []
    for r in rows:
        key = r["pattern_key"] or ""
        symptom = key.split(".", 1)[1] if "." in key else key  # itemfield-unit_price
        scope = symptom.split("-", 1)[0].replace("field", "")  # item / doc
        field = symptom.split("-", 1)[1] if "-" in symptom else symptom
        m = _DETAILS_RE.match(r["details"] or "")
        error_pattern = m.group("pat") if m else ""
        doc_hash = (m.group("doc") if m else None) or ""
        anchors: dict = {}
        if doc_hash and scope == "item":
            try:
                row = (
                    await session.execute(_DOC_ANCHORS_SQL, {"prefix": f"{doc_hash}%"})
                ).first()
                if row and row.anchors:
                    anchors = _json.loads(row.anchors)
            except Exception:  # noqa: BLE001 — 锚词附注失败不影响候选列表
                anchors = {}
        out.append(
            {
                "learning_id": r["id"],
                "scope": scope.replace("field", "") if scope.endswith("field") else scope,
                "field": field,
                "recurrence": r["recurrence_count"],
                "error_pattern": error_pattern,
                "doc_hash": doc_hash,
                "evidence": (m.group("rest") if m else (r["details"] or ""))[:200],
                "suggested_anchors": anchors,
                "first_seen_at": str(r["first_seen_at"]),
                "last_seen_at": str(r["last_seen_at"]),
            }
        )
    return out


async def set_candidate_status(session, learning_id: str, status: str) -> bool:
    """候选状态流转（promoted_to_skill=已落规则卡 / dismissed=忽略）。"""
    if status not in ("promoted_to_skill", "dismissed", "resolved"):
        return False
    result = await session.execute(
        _SET_STATUS_SQL, {"id": learning_id, "status": status}
    )
    await session.commit()
    return (result.rowcount or 0) > 0
