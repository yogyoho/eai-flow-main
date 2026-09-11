"""doc_graph 实体消解——纯逻辑（无 DB; DB 侧由 ingest/mcp 调用）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §6。
借鉴 Semantica deduplication 模式（设计借用, 零依赖）: 归一化 → blocking(同域同类型) → 相似度分层。
归一化语义对应引擎 SQL LOWER(BTRIM(col)) 的 Python 侧, 外加 NFKC 全角折叠与内部空白折叠（中文实体名必需）。
"""

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

AUTO_MERGE_THRESHOLD = 0.97  # ≥ 直接自动合并
REVIEW_THRESHOLD = 0.92  # [0.92, 0.97) 进人工复核(pending); 以下不合并


def normalize_name(raw: str) -> str:
    """NFKC 全角→半角 + strip+lower + 内部空白折叠为单空格。"""
    s = unicodedata.normalize("NFKC", raw or "").strip().lower()
    return " ".join(s.split())


def block_key(domain: str, etype: str, norm_name: str) -> tuple[str, str, str]:
    """Blocking 键：同域同类型 + 规范名首字（跨域/跨类型永不互并）。"""
    return (domain, etype, norm_name[:1] or "#")


@dataclass
class MergeDecision:
    action: str  # "auto_merge" | "review" | "none"
    similarity: float
    candidate_name: str
    canonical_name: str


def decide_merge(new_norm: str, existing_norm: str) -> MergeDecision:
    """两段式决策：≥0.97 自动合并；[0.92,0.97) 待复核；以下不动。"""
    ratio = SequenceMatcher(None, new_norm, existing_norm).ratio()
    if ratio >= AUTO_MERGE_THRESHOLD:
        action = "auto_merge"
    elif ratio >= REVIEW_THRESHOLD:
        action = "review"
    else:
        action = "none"
    return MergeDecision(action, ratio, new_norm, existing_norm)
