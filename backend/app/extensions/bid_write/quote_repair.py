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


def _verbatim_hit(quote: str, hay_raw: str) -> bool:
    """逐字命中(空白折叠口径,与 verify_quotes 相同)。"""
    return bool(quote) and "".join(quote.split()) in "".join(hay_raw.split())


def repair_and_verify(
    provenance: dict, docs: list[dict], ratio: float = REPAIR_RATIO
) -> dict:
    """批卅 T1b:分段修复+分段核验(真实任务复盘产物,2026-11-18)。

    实测:未命中摘录多为**多源合成句**(AI 把散落各处的条款拼成一句),单段
    模糊修复救不了(repair_quotes 全文无单一连续区域达标)。改契约:
      · 合成句按 ;/;/\\n 拆子句,逐子句**逐字核验**(不做子句级模糊修——覆盖率
        口径实测会放过"数值写错"的幻觉摘录 0.82>0.6,安全侧裁决 2026-11-18);
      · 全部子句逐字可溯 = 该路径 verified;
      · provenance[path].quote 改写为**最长可溯子句的原文**(溯源锚点:弹窗
        定位+高亮直接生效);原合成句存 quote_orig 留审计,不删不编。
    返回遥测 {scanned, verified_whole, verified_parts, repaired_parts,
    unverified, skipped_short};审查端引擎零改动(verify_quotes 语义仍由
    "逐字命中"承担,本函数只是把"逐字"的考题从合成句换成子句集)。
    """
    import re as _re

    joined: dict[str, str] = {}
    for d in docs:
        doc_id = str(d.get("doc_id") or "doc")
        joined[doc_id] = joined.get(doc_id, "") + str(d.get("text") or "")
    corpus: dict[str, tuple[str, list[int]]] = {
        doc_id: _norm_with_map(text) for doc_id, text in joined.items()
    }

    stats = {
        "scanned": 0,
        "verified_whole": 0,
        "verified_parts": 0,
        "repaired_parts": 0,
        "unverified": 0,
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
        if _verbatim_hit(quote, hay_raw):
            stats["verified_whole"] += 1  # 整句已逐字:什么都不用动
            continue
        parts = [
            s.strip() for s in _re.split(r"[;;\n]", quote) if s.strip()
        ]
        if len(parts) <= 1:
            # 非合成句:整句走单段模糊修复(原 repair_quotes 语义)
            if _repair_single(p, hay_raw, corpus.get(doc_id, ("", [])), quote, ratio, stats):
                stats["repaired_parts"] += 1
            else:
                stats["unverified"] += 1
            continue
        # 合成句:逐子句**逐字核验**(不做模糊修——覆盖率口径会放过"数值写错"
        # 的幻觉摘录,实测 0.82 可过 0.6 门槛;安全侧裁决 2026-11-18)
        anchors: list[str] = []
        all_ok = True
        for part in parts:
            if _verbatim_hit(part, hay_raw):
                anchors.append(part)
                continue
            all_ok = False
            break
        if not all_ok or not anchors:
            stats["unverified"] += 1
            continue
        anchor = max(anchors, key=len)  # 最长子句=最具体定位锚
        p["quote_orig"] = quote  # 原合成句留审计
        p["quote"] = anchor  # 原文逐字锚点(弹窗定位+高亮直接生效)
        p["repaired"] = True
        stats["verified_parts"] += 1
    return stats


def _repair_single(
    entry: dict,
    hay_raw: str,
    corpus: tuple[str, list[int]],
    quote: str,
    ratio: float,
    stats: dict,
) -> bool:
    """单段模糊修复:成功则 entry["quote"] 被替换为原文片段并返回 True。"""
    qn, _ = _norm_with_map(quote)
    if len(qn) < _MIN_QUOTE:
        stats["skipped_short"] = stats.get("skipped_short", 0) + 1
        return False
    hn, horig = corpus
    if not hn:
        return False
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
        return False
    _r, lo, hi = best
    orig_lo, orig_hi = horig[lo], horig[hi - 1] + 1
    entry["quote"] = hay_raw[orig_lo:orig_hi]  # 原文复制,逐字保真
    entry["repaired"] = True
    return True


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
        if _repair_single(p, hay_raw, corpus.get(doc_id, ("", [])), quote, ratio, stats):
            stats["repaired"] += 1
        else:
            stats["unrepaired"] += 1
    return stats
