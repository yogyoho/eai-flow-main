"""禁用词扫描器(批二十 M1,EAI-CUSTOM 2026-11-13)——CMN 全文扫描与 BL-006/
PS-009/RT-003/RT-009 技能级扫描共用。词表+静态级真源=contracts.FORBIDDEN_WORDS
(词→(级,整改提示));本模块只做执行器侧「哪些词在哪个面扫」的 6 桶分类,pin
测试钉 union==FORBIDDEN_WORDS keys(新词入合同必须入桶,漏桶=测试红)。"""

from __future__ import annotations

from app.extensions.bid_write.contracts import (
    FORBIDDEN_CASE_INSENSITIVE,
    FORBIDDEN_WORDS,
)

# 执行器侧桶:桶名 → 该面上要扫的词集。桶粒度=断言消费粒度:
#   placeholder → CMN-001 全文 D0
#   absolute+redline → CMN-002(D1/D0 按词静态级)
#   absolute+vague+redline → BL-006 投标函措辞(BL 面除调价/空应答外全扫)
#   price_vague → PS-009 报价说明(无调价机制 D0/有 D1)
#   empty_answer → RT-003 响应表空应答 D0
#   placeholder → RT-009 响应文本占位符 D0
CATEGORIES: dict[str, frozenset[str]] = {
    "placeholder": frozenset({"待补充", "待定", "TBD", "XX"}),
    "absolute": frozenset({"无条件", "绝不", "无限期", "终身"}),
    "redline": frozenset({"包过", "保证中标", "内部渠道", "围标", "串标"}),
    "vague": frozenset({"尽量", "力争", "原则上", "视情况", "酌情", "尽可能", "基本满足", "按现场实际"}),
    "price_vague": frozenset({"暂估", "以最终结算为准", "另行协商", "随市场调整", "价格另议"}),
    "empty_answer": frozenset({"满足招标文件要求", "符合招标文件要求", "按招标文件执行", "无异议"}),
}

_CASE_INSENSITIVE = frozenset(FORBIDDEN_CASE_INSENSITIVE)


def words_for(*categories: str) -> frozenset[str]:
    """桶并集;空桶=编程错误(断言面必点名要扫什么)。"""
    if not categories:
        raise ValueError("words_for 需至少一个桶")
    out: frozenset[str] = frozenset()
    for c in categories:
        if c not in CATEGORIES:
            raise ValueError(f"未知禁用词桶 {c!r}(合法:{sorted(CATEGORIES)})")
        out |= CATEGORIES[c]
    return out


def static_level(word: str) -> str:
    """词静态级(D0/D1),真源 FORBIDDEN_WORDS。"""
    return FORBIDDEN_WORDS[word][0]


def scan_text(text: str, words: frozenset[str]) -> list[str]:
    """单文本命中词列表(按词在 contracts 字典序稳定排序去重;大小写不敏感面
    upper() 匹配)。调用方拼 Hit 级别/整改提示。"""
    if not text:
        return []
    hits: set[str] = set()
    upper = text.upper()
    for w in words:
        if w in _CASE_INSENSITIVE:
            if w.upper() in upper:
                hits.add(w)
        elif w in text:
            hits.add(w)
    return sorted(hits)


def hit_message(hits: list[str]) -> str:
    """命中词→提示串(词+整改提示),截 8 条防报告爆量。"""
    parts = [f"「{w}」({FORBIDDEN_WORDS[w][1]})" for w in hits[:8]]
    more = f" 等{len(hits)}处" if len(hits) > 8 else ""
    return "; ".join(parts) + more
