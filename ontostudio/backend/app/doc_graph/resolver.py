"""doc_graph 实体消解——纯逻辑（无 DB; DB 侧由 ingest/mcp 调用）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §6。
借鉴 Semantica deduplication 模式（设计借用, 零依赖）: 归一化 → blocking(同域同类型) → 相似度分层。
归一化语义对应引擎 SQL LOWER(BTRIM(col)) 的 Python 侧, 外加 NFKC 全角折叠与内部空白折叠（中文实体名必需）。
"""

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

AUTO_MERGE_THRESHOLD = 0.97  # 评审加固后 fuzzy auto 带已废除（auto=归一化精确相等）; 常量仅为兼容既有导入保留, 不再参与决策
REVIEW_THRESHOLD = 0.92  # fuzzy ratio ≥ 0.92 且非精确相等 → 人工复核(pending); 以下不合并


def normalize_name(raw: str | None) -> str:
    """NFKC 全角→半角 + strip+lower + 内部空白折叠为单空格。幂等; None/纯空白 → ""。"""
    s = unicodedata.normalize("NFKC", raw or "").strip().lower()
    return " ".join(s.split())


def block_key(domain: str, etype: str, norm_name: str) -> tuple[str, str, str]:
    """Blocking 键：同域同类型 + 规范名首字（跨域/跨类型永不互并; 空名落 "#" 桶）。"""
    return (domain, etype, norm_name[:1] or "#")


@dataclass(frozen=True)
class MergeDecision:
    action: Literal["auto_merge", "review", "none"]
    similarity: float
    candidate_name: str
    canonical_name: str


def decide_merge(new_norm: str, existing_norm: str) -> MergeDecision:
    """两段式合并决策。前置条件: 两个参数必须已是 normalize_name 的输出。

    分带（评审加固 2026-09-11）:
    - 归一化后精确相等 → auto_merge（fuzzy 0.97 带已废除: char 级 SequenceMatcher 会把
      19 字名+1 冗余字(ratio≈0.974)或 ≥34 字名单字翻错静默自动合并; 精确去重由 Task 4
      的自然键 ON CONFLICT upsert 承担, fuzzy 只喂 review 队列）;
    - 其余 ratio ∈ [0.92, 1) → review（进人工复核）;
    - 以下 → none。
    空名守卫: 任一参数为空 → none（堵住 "",""→auto_merge 1.0 的 "#" blocking 桶漏洞）。
    """
    if not new_norm or not existing_norm:
        return MergeDecision(action="none", similarity=0.0, candidate_name=new_norm, canonical_name=existing_norm)
    ratio = SequenceMatcher(None, new_norm, existing_norm, autojunk=False).ratio()
    if new_norm == existing_norm:
        action = "auto_merge"
    elif ratio >= REVIEW_THRESHOLD:
        action = "review"
    else:
        action = "none"
    return MergeDecision(action=action, similarity=ratio, candidate_name=new_norm, canonical_name=existing_norm)
