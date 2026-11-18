# bid_write 批卅一(Tier-2 位置锚点制)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans,逐任务勾 `- [ ]`。

**Goal:** 从根上消灭"摘录改写/缺出处"两类 blocked:AI 只交**短锚点**(≤40 字单处连续片段,逐字)+ **逐字段强制 provenance**;程序侧**值反查兜底**(字段值本身当锚点,零 AI 定位复制原文);批卅修复管线降级为安全网。

**红线:** 审查端 `bid_review/engine/extract.py` **零改动**(用户常驻规则)——写作端自建提示词,复用引擎原语(shard_docs/normalize_*/verify_quotes,import 不改)。

**已验证事实(2026-11-18 实测 8d76e6aa):** 引擎 prompt 已要求"逐字照抄"(extract.py:897)但模型仍合成;8 blocked = 4 合成句 + 5 无 provenance(「conf 自报低」另有 3 条重叠)。原 prompt 骨架见 extract.py:872-902(镜像时保持 fields/provenance/candidates/confidence 四对象契约,normalize 依赖它)。

**Architecture:** ① `bid_write/extract_prompt.py` 新提示词:quote 改「原文关键短语 ≤40 字,单处连续逐字,禁止拼接多出」,provenance 对每个非 null 字段**必须**给(找不到出处就把该字段值填 null——宁缺勿假);② `quote_repair.py` 加 `synthesize_missing_provenance(fields, provenance, docs)`:无 provenance 的已抽取路径 → 归一化反查字段值(标量;list 逐项试)→ 命中即**程序复制**所在原句(句界。;;!?扩展)为 quote,`synthesized=True`;③ worker 接线:先 synthesize 再 repair_and_verify;④ 测量脚本扩展对比;⑤ 真实任务新抽取 QA。

**Tech Stack:** stdlib re/unicodedata / pytest golden / measure script / QA

---

### T1 值反查兜底 `synthesize_missing_provenance`(quote_repair.py 追加)

```python
_SENT_END = "。;;!?!!??"

def _sentence_span(hay_raw: str, orig_lo: int, orig_hi: int, cap: int = 160) -> tuple[int, int]:
    """从命中区向外扩到句界(。;;!?…),超 cap 截半句。"""
    lo = orig_lo
    while lo > 0 and hay_raw[lo - 1] not in _SENT_END:
        lo -= 1
    hi = orig_hi
    while hi < len(hay_raw) and hay_raw[hi] not in _SENT_END:
        hi += 1
    if hi - lo > cap:  # 超长句截命中±半cap
        lo = max(lo, orig_lo - cap // 2)
        hi = min(hi, orig_hi + cap // 2)
    return lo, hi

def synthesize_missing_provenance(fields: dict, provenance: dict, docs: list[dict]) -> dict:
    """无 provenance 的已抽取路径:字段值反查原文 → 程序复制所在原句为 quote。
    零 AI;查不到=诚实不造(与「缺路径不造行」同口径)。返回 {synthesized, candidates_missed}。"""
    joined: dict[str, str] = {}
    for d in docs:
        doc_id = str(d.get("doc_id") or "doc")
        joined[doc_id] = joined.get(doc_id, "") + str(d.get("text") or "")
    corpus = {doc_id: _norm_with_map(t) for doc_id, t in joined.items()}
    stats = {"synthesized": 0, "missed": 0}
    for path, value in (fields or {}).items():
        if path in provenance or value in (None, "", [], {}):
            continue
        items = value if isinstance(value, list) else [value]
        hit = None
        for item in items:
            s = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
            s = s.strip()
            if not s or len(s) > 120:
                continue
            sn, _ = _norm_with_map(s)
            if len(sn) < _MIN_QUOTE:
                continue
            for doc_id, (hn, horig) in corpus.items():
                pos = hn.find(sn[:64])  # 长值取前64字定位
                if pos >= 0:
                    lo, hi = horig[pos], horig[min(pos + len(sn) - 1, len(horig) - 1)] + 1
                    slo, shi = _sentence_span(joined[doc_id], lo, hi)
                    hit = {"doc_id": doc_id, "page": None, "quote": joined[doc_id][slo:shi], "synthesized": True}
                    break
            if hit:
                break
        if hit:
            provenance[path] = hit
            stats["synthesized"] += 1
        else:
            stats["missed"] += 1
    return stats
```

(import json 加模块头;长值 `sn[:64]` 定位后需核对全文命中而非仅前缀——实现时改为 `hn.find(sn[:64])` 命中后再验 `hn[pos:pos+len(sn)] == sn` 全等,不等则继续 find 循环。此为 plan 内已标注的实现细节。)

**Golden(追加到 test_bid_write_quote_repair.py):**
- 标量值原文命中 → synthesized quote=所在原句且逐字子串;`verified_fast` 后续为 True
- list 值首项命中 → 同上
- 值不在原文(聚合/推导值)→ missed,不造 provenance
- 已有 provenance 的路径不触碰

### T2 写作端锚点提示词 `extract_prompt.py` + worker 切换

新模块镜像引擎 prompt(extract.py:880-902 全文为底稿),仅改 quote 行:
- `quote 为该字段依据的**原文关键短语**:`≤40 字`、**单处连续片段逐字照抄**;禁止跨处拼接、禁止改写、禁止概括` + 追加铁律「5. quote 抽不出连续短语时,宁可将该字段填 null 并在 provenance 给 {doc_id,page:null,quote:""} 也绝不编造」
- provenance 行改:`provenance:fields 中每个非 null 字段**必须**给出处`
- worker `_default_extract_fn._fn` 里 `build_extract_prompt(shard, field_paths)` → `build_anchor_prompt(shard, field_paths)`(bid_write 本地 import)
- 契约兼容:normalize_provenance/verify_quotes 不变;≤40 字锚点对 locate/高亮完全够用(段落级 ±10 窗口)
- Golden:`test_build_anchor_prompt` 钉关键子串(≤40 字/必须出处/宁 null 勿编);不钉全文(允许措辞微调)

### T3 测量扩展 + 真实任务重测

measure_quote_repair.py 加三段:无 provenance 路径清单;synthesize 后 verified 变化;汇总「blocked 前后」三级(原始→+修复→+值反查)。对 8d76e6aa 重跑:**预期** 5 条无 provenance 中值可反查者救回(如 project_name/tender_no/purchaser_name 等标量),4 合成句仍拒(诚实)——数字如实入 plan。

### T4 全链路 QA(真实验证,规则④)

gateway 重启(canonical 三 overlay restart)→ UI 同文件新建任务 → 对比旧任务:待人工核对计数、溯源点击成功率;记录数字入 plan。

### T5 收口

plan 全勾(add -f)+ wolf 四件套 + auto-memory + docs commit。**不推,等「push」。**

---

## 限制与未覆盖面
1. 值反查只救「值逐字出现在原文」的路径;推导值(合计/对照类)救不了=诚实缺 provenance,仍 blocked 待人工。
2. 锚点 ≤40 字靠提示词约束,模型仍可能违规 → 批卅管线(fast/合成拆分/单句模糊)全量保留为安全网,两道工序同一入口。
3. candidates(多值冲突面)本批不动;prompt 契约四对象不变,normalize 零适配。
