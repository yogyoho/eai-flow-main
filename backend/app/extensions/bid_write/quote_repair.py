"""quote_repair.py — AI 摘录修复管线(Tier-1,批卅;EAI-CUSTOM 2026-11-18)。

背景:抽取 provenance.quote 由生成式模型"重新说出",措辞/标点/全半角走样 →
verify_quotes 逐字核验失败 → 矩阵 blocked 放大 + 溯源定位 404。
本管线零 LLM:归一化模糊定位 → 按索引映射回原文 **复制** 真实片段替换 quote
(程序复印不改字;改写内容救得回,编造内容相似度不达标救不回=诚实失败)。
审查端 bid_review 引擎零改动;verify_quotes 仍为最终真值裁决。

设计裁决(ponytail):
- NFKC 逐字符折叠:全角字母数字/标点 1:1;多字符展开(㎡ 等)取首字符的诚实近似,
  招标文本罕见,相似度门槛兜底。
- 锚点定位:摘录首/中/尾三段 12-gram 在归一语料 find,窗口 ±摘录长,窗口内
  SequenceMatcher 计相似——避免全文档滑窗 O(n·m)。
- 只在 provenance 自报的 doc_id 语料内找:AI 指错文档=诚实 unrepaired,不跨文档乱救。
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# 归一剔除集:空白(含零宽)与中英标点全剔(摘录常见引号/括号/序号/千分位差异)
_PUNCT = re.compile(
    r"[\s　​-‍﻿!-/:-@\\[-`{-~　-〿"
    r"！-／：-＠［-｀｛-･"
    r"—‘’“”…·]"
)

REPAIR_RATIO = 0.72  # 相似度门槛:低于=改写过度/编造,诚实放弃
_MIN_QUOTE = 8       # 归一后短于 8 字不修(锚点不足,误对齐风险)
_ANCHOR = 12         # 锚点长度


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """(归一串, 归一下标→原文下标映射)。NFKC 逐字符折叠后剔空白与标点。"""
    normed: list[str] = []
    origins: list[int] = []
    for i, ch in enumerate(text):
        folded = unicodedata.normalize("NFKC", ch)
        if len(folded) > 1:
            folded = folded[0]  # 多字符展开只取首字符(诚实近似,见模块头)
        if _PUNCT.fullmatch(folded):
            continue
        normed.append(folded)
        origins.append(i)
    return "".join(normed), origins


def repair_quotes(
    provenance: dict, docs: list[dict], ratio: float = REPAIR_RATIO
) -> dict:
    """原地修复 provenance[path].quote;返回遥测 {scanned, verified_fast,
    repaired, unrepaired, skipped_short}。只动 quote(不动 doc_id/page/conf),
    修复成功的 path 追加 repaired=True 标记。"""
    # 同 doc_id 多分片拼接(与 verify_quotes 同口径),再建归一语料
    joined: dict[str, str] = {}
    for d in docs:
        doc_id = str(d.get("doc_id") or "doc")
        joined[doc_id] = joined.get(doc_id, "") + str(d.get("text") or "")
    corpus: dict[str, tuple[str, list[int]]] = {}
    for doc_id, text in joined.items():
        corpus[doc_id] = _norm_with_map(text)

    stats = {
        "scanned": 0,
        "verified_fast": 0,
        "repaired": 0,
        "unrepaired": 0,
        "skipped_short": 0,
    }
    for _path, p in (provenance or {}).items():
        if not isinstance(p, dict):
            continue
        quote = str(p.get("quote") or "")
        if not quote:
            continue
        stats["scanned"] += 1
        doc_id = str(p.get("doc_id") or "")
        hay_raw = joined.get(doc_id, "")
        if "".join(quote.split()) in "".join(hay_raw.split()):
            stats["verified_fast"] += 1  # 已逐字命中,verify_quotes 会过,不动
            continue
        qn, _ = _norm_with_map(quote)
        if len(qn) < _MIN_QUOTE:
            stats["skipped_short"] += 1
            continue
        hn, horig = corpus.get(doc_id, ("", []))
        if not hn:
            stats["unrepaired"] += 1
            continue
        best: tuple[float, int, int] | None = None
        mid = len(qn) // 2
        anchors = {qn[:_ANCHOR], qn[mid : mid + _ANCHOR], qn[-_ANCHOR:]}
        for anchor in anchors:
            if len(anchor) < _MIN_QUOTE // 2:
                continue
            start = hn.find(anchor)
            while start >= 0:
                win_lo = max(0, start - len(qn))
                win_hi = min(len(hn), start + len(anchor) + len(qn))
                cand = hn[win_lo:win_hi]
                r = SequenceMatcher(None, qn, cand, autojunk=False).ratio()
                if best is None or r > best[0]:
                    best = (r, win_lo, win_hi)
                start = hn.find(anchor, start + 1)
                if best is not None and best[0] >= 0.999:
                    break
        if best is None or best[0] < ratio:
            stats["unrepaired"] += 1
            continue
        _r, lo, hi = best
        orig_lo, orig_hi = horig[lo], horig[hi - 1] + 1
        p["quote"] = hay_raw[orig_lo:orig_hi]  # 原文复制,逐字保真
        p["repaired"] = True  # 遥测标记(测量/前端可辨,不参与定位契约)
        stats["repaired"] += 1
    return stats
