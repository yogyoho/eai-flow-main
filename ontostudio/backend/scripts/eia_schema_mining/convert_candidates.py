"""候选 JSONL → 每报告一个 EiaExtraction payload dict（不过 EiaExtraction 校验的行数计入 stats 丢弃）。

管线：幻觉过滤(quote 归一核验,复用 out/check_candidates 三件套) → 谓词角色校验
(predicate_roles 取自 EiaExtraction ClassVar) → 同名实体 etype 消解(多数决) →
消解后关系角色复检(多数决可能翻转 etype 使个别关系失配 → 丢弃该关系并计入
resolved_role_dropped，实体保留——文本已核验；保证 payload 整体通过
EiaExtraction.model_validate，即 Task5 ingest 的 fail-closed 硬门) →
entities/relations 去重 → confidence=0.6 全 pending → mention 溯源(document_id=源文件, quote≤2000)。

计划勘误（2026-09-29，实施时修正）：
- 计划片段 sys.path 用 parents[1]，本脚本在 backend/scripts/eia_schema_mining/ 两层深，
  parents[1]=scripts/ 导不进 app/——按同目录 llm_extract.py:35 先例用 parents[2]。
- 计划原文同名单测用 located_in，该谓词不在契约角色表（v2 定型 33 谓词），测试数据已改。
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend 根可导入 app/（两层深,同 llm_extract.py:35）
from app.doc_graph.schemas import EiaExtraction  # noqa: E402

# review 2026-09-29 已核: schemas.py 无模块级 EIA_PREDICATE_ROLES(仅私有 _EIA_PREDICATE_ROLES);
# ClassVar 即公开真源——整表含 v2 全部 19 条扩容谓词角色 + 14 条 v1 旧谓词，校验即全覆盖。
EIA_PREDICATE_ROLES = EiaExtraction.predicate_roles

PENDING_CONFIDENCE = 0.6  # < REVIEW_CONFIDENCE(0.7) → 全量 pending_review 走人审（设计意图,非缺陷）

_norm = lambda s: re.sub(r"\s+", "", s or "")


def _canon(s):
    """空白归一 + 省略号剔除 + 全角数字/字母转半角（PDF 转换文本常见假阳性来源,同 out/check_candidates.py）。"""
    s = re.sub(r"\s+", "", s or "").replace("...", "").replace("…", "")
    return "".join(chr(ord(c) - 0xFEE0) if "０" <= c <= "９" or "Ａ" <= c <= "Ｚ" or "ａ" <= c <= "ｚ" else c for c in s)


def quote_in_text(quote, canon):
    """省略号拼接的引用拆片断逐段核验；≤6 字碎片不作要求（同三件套）。"""
    frags = [f for f in re.split(r"\.{3}|…", quote or "") if len(_norm(f)) >= 6]
    return bool(frags) and all(_canon(f) in canon for f in frags)


def convert(rows, fulltext_getter, source):
    """rows=单报告候选 dict 列表; fulltext_getter(source)→全文; source=document_id（Task3 传 f"eia-batch:{slug}"）。

    返回 SimpleNamespace(payloads=[payload_dict]|[], stats=Counter)。
    """
    canon = _canon(fulltext_getter(source))
    stats = Counter(hallu_dropped=0, role_dropped=0, resolved_role_dropped=0, dup_entities_merged=0, kept=0)
    seen_ent, ents, rels = {}, [], []
    name_types = defaultdict(Counter)
    # ① 幻觉过滤 + 角色/枚举校验（整段命中兜底：碎片核验失败但全 quote 归一后命中原文 → 保留）
    clean = []
    for r in rows:
        q = r.get("evidence_quote")
        if not q or quote_in_text(q, canon) is False and _canon(q) not in canon:
            stats["hallu_dropped"] += 1
            continue
        st, ot, pred = r.get("subject_type"), r.get("object_type"), r.get("predicate")
        if pred not in EIA_PREDICATE_ROLES or EIA_PREDICATE_ROLES[pred] != (st, ot):
            stats["role_dropped"] += 1
            continue
        clean.append(r)
    # ② 同名 etype 消解（多数决；平票按首次插入序）
    for r in clean:
        name_types[r["subject"]][r["subject_type"]] += 1
        name_types[r["object"]][r["object_type"]] += 1
    resolved = {n: c.most_common(1)[0][0] for n, c in name_types.items()}
    stats["dup_entities_merged"] = sum(sum(c.values()) - 1 for c in name_types.values())
    # ③ 实体/关系去重落 payload（消解后角色复检）
    seen_rel = set()
    mention = lambda r: {"document_id": source, "doc_span": {"chunk_start": r.get("span", [0])[0]},  # noqa: E731
                         "quote": (r.get("evidence_quote") or "")[:2000]}
    for r in clean:
        s_name, o_name = r["subject"], r["object"]
        for nm in (s_name, o_name):
            if nm not in seen_ent:
                seen_ent[nm] = True
                ents.append({"name": nm, "etype": resolved[nm], "attrs": {}, "confidence": PENDING_CONFIDENCE,
                             "mention": mention(r)})
        key = (s_name, r["predicate"], o_name)
        if key in seen_rel:
            continue
        seen_rel.add(key)
        # 消解后角色复检：多数决翻转 etype 后个别关系失配 → 丢关系保实体，payload 仍整体可过 model_validate
        if EIA_PREDICATE_ROLES[r["predicate"]] != (resolved[s_name], resolved[o_name]):
            stats["resolved_role_dropped"] += 1
            continue
        rels.append({"subject": s_name, "predicate": r["predicate"], "object": o_name,
                     "confidence": PENDING_CONFIDENCE, "mention": mention(r)})
        stats["kept"] += 1
    payload = {"domain": "eia", "extracted_by": "eia-batch-v2-llm", "thread_id": "",
               "entities": ents, "relations": rels} if ents else None
    from types import SimpleNamespace
    return SimpleNamespace(payloads=[payload] if payload else [], stats=stats)
