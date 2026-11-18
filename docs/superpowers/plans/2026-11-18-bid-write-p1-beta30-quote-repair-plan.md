# bid_write 批卅(摘录修复管线 Tier-1)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI 摘录(quote)走样导致 verified=False → 矩阵大量 blocked + 溯源 404。加一道确定性修复管线:模糊定位→**复制原文**替换 AI 版本,不改提示词、不碰审查端引擎。

**Architecture:** 新模块 `bid_write/quote_repair.py` 纯函数(零 LLM):NFKC+去空白+去标点归一 → 锚点定位(3 段 12-gram)→ SequenceMatcher 相似度 ≥0.72 → 按归一索引映射回原文偏移,**复制原文片段**替换 quote;已逐字命中的走快路径不动。worker `run_tender_extract` 在 provenance 归一后、verify 前调用。遥测 stats 走 logger,不动函数签名。

**Tech Stack:** unicodedata NFKC + difflib.SequenceMatcher(stdlib,零新依赖)/ pytest golden / 真实任务数据测量脚本 / Playwright QA

**用户四规则映射:**
- ①顶尖视角:限制与未覆盖面见文末诚实段。
- ②原始材料:已核 merge 223dfffc5 未动 extract.py/matrix.py;worker.py 今日全文重读;插入点行号以当前树为准。
- ③方法可复查:测量脚本入库 `backend/scripts/measure_quote_repair.py`,任何人可重跑。
- ④结论须验证:golden 测试钉行为;真实任务数据量恢复率;QA 全新任务上传实测 blocked 下降+溯源高亮。

---

### Task 1: quote_repair.py 纯函数 + golden 测试

**Files:**
- Create: `backend/app/extensions/bid_write/quote_repair.py`
- Test: `backend/tests/test_bid_write_quote_repair.py`

- [ ] **Step 1: 模块全文**

```python
"""quote_repair.py — AI 摘录修复管线(Tier-1,批卅;EAI-CUSTOM 2026-11-18)。

背景:抽取 provenance.quote 由生成式模型"重新说出",措辞/标点/全半角走样 →
verify_quotes 逐字核验失败 → 矩阵 blocked 放大 + 溯源定位 404。
本管线零 LLM:归一化模糊定位 → 按索引映射回原文 **复制** 真实片段替换 quote
(程序复印不改字;改写内容救得回,编造内容相似度不达标救不回=诚实失败)。
审查端 bid_review 引擎零改动;verify_quotes 仍为最终真值裁决。
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# 归一剔除集:空白(含零宽)经 NFKC 后剔除;标点全剔(摘录常见引号/括号/序号差异)
_PUNCT = re.compile(r"[\s　​-‍﻿!-/:-@\\[-`{-~　-〿！-／：-＠［-｀｛-･—‘’“”…·]+")

REPAIR_RATIO = 0.72  # 相似度门槛:低于=改写过度/编造,诚实放弃
_MIN_QUOTE = 8       # 归一后短于 8 字不修(锚点不足,误对齐风险)
_ANCHOR = 12         # 锚点长度

def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """(归一串, 归一下标→原文下标映射)。NFKC 折叠全半角后剔空白与标点。"""
    normed: list[str] = []
    origins: list[int] = []
    for i, ch in enumerate(unicodedata.normalize("NFKC", text)):
        if _PUNCT.fullmatch(ch):
            continue
        normed.append(ch)
        origins.append(i)
    return "".join(normed), origins
```

等等——NFKC 展开会改变字符数(如 ㎡→m2),逐字符枚举 + map 会对不齐。ponytail 裁决:**逐字符 NFKC 仅折叠单字符映射**(全角字母数字、全角标点都是 1:1);多字符展开(㎡ 等)在招标文本罕见,逐字符时取展开首字符只记首映射,展开多余字符丢弃(诚实近似,测试钉)。实现:

```python
def _norm_with_map(text: str) -> tuple[str, list[int]]:
    normed: list[str] = []
    origins: list[int] = []
    for i, ch in enumerate(text):
        for j, folded in enumerate(unicodedata.normalize("NFKC", ch)):
            if j > 0:
                continue  # 多字符展开只取首字符(罕见;诚实近似)
            if _PUNCT.fullmatch(folded):
                continue
            normed.append(folded)
            origins.append(i)
    return "".join(normed), origins
```

```python
def repair_quotes(provenance: dict, docs: list[dict], ratio: float = REPAIR_RATIO) -> dict:
    """原地修复 provenance[path].quote;返回遥测 {scanned, verified_fast, repaired,
    unrepaired, skipped_short}。只动 quote,不动 doc_id/page/conf。"""
    # 按 doc_id 预构建语料(与 verify_quotes 同口径:同 doc_id 多分片拼接)
    corpus: dict[str, tuple[str, list[int]]] = {}
    joined: dict[str, str] = {}
    for d in docs:
        doc_id = str(d.get("doc_id") or "doc")
        joined[doc_id] = joined.get(doc_id, "") + str(d.get("text") or "")
    for doc_id, text in joined.items():
        corpus[doc_id] = _norm_with_map(text)

    stats = {"scanned": 0, "verified_fast": 0, "repaired": 0, "unrepaired": 0, "skipped_short": 0}
    for path, p in (provenance or {}).items():
        if not isinstance(p, dict):
            continue
        quote = str(p.get("quote") or "")
        if not quote:
            continue
        stats["scanned"] += 1
        doc_id = str(p.get("doc_id") or "")
        hay_raw = joined.get(doc_id, "")
        if quote and "".join(quote.split()) in "".join(hay_raw.split()):
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
        anchors = {qn[:_ANCHOR], qn[len(qn) // 2 : len(qn) // 2 + _ANCHOR], qn[-_ANCHOR:]}
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
                if best and best[0] >= 0.999:
                    break
        if best is None or best[0] < ratio:
            stats["unrepaired"] += 1
            continue
        r, lo, hi = best
        orig_lo, orig_hi = horig[lo], horig[hi - 1] + 1
        p["quote"] = hay_raw[orig_lo:orig_hi]  # 原文复制,逐字保真
        p["repaired"] = True  # 遥测标记(前端/测量可辨)
        stats["repaired"] += 1
    return stats
```

- [ ] **Step 2: golden 测试**(确定性,SequenceMatcher 无随机)

```python
"""批卅 T1:quote_repair golden(修复=原文复制;编造/短摘录/错文档=诚实放弃)。"""
from app.extensions.bid_write.quote_repair import repair_quotes

DOCS = [{"doc_id": "T", "text": "投标保证金:人民币伍万元整(¥50,000.00),应当从基本账户转出。第三章 评标办法详见附件二。投标截止时间:2026年12月1日09时30分。"}]

def _prov(quote, doc_id="T"):
    return {"t.deposit_required": {"doc_id": doc_id, "quote": quote}}

def test_verbatim_fast_path_untouched():
    prov = _prov("人民币伍万元整")
    stats = repair_quotes(prov, DOCS)
    assert stats["verified_fast"] == 1 and stats["repaired"] == 0
    assert prov["t.deposit_required"]["quote"] == "人民币伍万元整"

def test_punct_width_variant_repaired_to_verbatim():
    # AI 版:全角标点改写+漏逗号 → 归一后高相似 → 复制原文片段
    prov = _prov("投标保证金 人民币伍万元整 ¥5000000 应当从基本账户转出")
    stats = repair_quotes(prov, DOCS)
    assert stats["repaired"] == 1
    q = prov["t.deposit_required"]["quote"]
    assert "人民币伍万元整(¥50,000.00)" in q  # 原文逐字(含全角括号/千分位)
    assert "".join(q.split()) in "".join(DOCS[0]["text"].split())  # 必为原文子串

def test_hallucinated_number_not_repaired():
    prov = _prov("投标保证金人民币壹拾万元整,应当从一般账户转出")  # 金额/账户都错
    stats = repair_quotes(prov, DOCS)
    assert stats["unrepaired"] == 1 and "repaired" not in prov["t.deposit_required"]

def test_short_quote_skipped():
    prov = _prov("伍万元")
    stats = repair_quotes(prov, DOCS)
    assert stats["skipped_short"] == 1

def test_wrong_doc_unrepaired():
    prov = _prov("投标保证金人民币伍万元整", doc_id="OTHER")
    stats = repair_quotes(prov, DOCS)
    assert stats["unrepaired"] == 1

def test_empty_quote_ignored():
    stats = repair_quotes({"p": {"doc_id": "T", "quote": ""}}, DOCS)
    assert stats["scanned"] == 0
```

- [ ] **Step 3: 跑测试**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_write_quote_repair.py -v
```

Expected: 6 PASS。若相似度边缘(全角改写例 ratio<0.72),调 anchors/窗口宽,不动门槛——门槛改动须附真实数据依据。

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/bid_write/quote_repair.py backend/tests/test_bid_write_quote_repair.py
git commit -m "feat(bid-write): 批卅 T1 摘录修复管线——quote_repair 纯函数(NFKC+去标点归一→锚点定位→SequenceMatcher≥0.72→原文复制替换;逐字命中快路径;编造/短摘录/错文档诚实放弃)+6 golden"
```

---

### Task 2: worker 接线 + telemetry 日志

**Files:**
- Modify: `backend/app/extensions/bid_write/worker.py:88-94`(provenance 归一后、verified 前插一行调用 + logger.info)

- [ ] **Step 1: 插入调用**(在 `provenance = {k: ...}` 过滤行之后、`confidences = ...` 之前)

```python
    repair_stats = repair_quotes(provenance, docs)  # 批卅 Tier-1:摘录修复(复制原文;审查端引擎零改动)
    if repair_stats.get("repaired"):
        logger.info("bid_write quote repair: %s", repair_stats)
```

import:`from app.extensions.bid_write.quote_repair import repair_quotes`(函数顶部与其他 bid_write 导入同组)。

- [ ] **Step 2: pytest 回归**(run_tender_extract 现有测试 + routers 混合 0 测试)

```bash
PYTHONPATH=. uv run pytest tests/test_bid_write_routers.py tests/test_bid_write_matrix.py -q
```

Expected: 全 PASS(修复不改变"已逐字"路径;既有 run_tender_extract fixture 若 quote 均逐字 → fast path 零影响)。

- [ ] **Step 3: Commit**

```bash
git add backend/app/extensions/bid_write/worker.py
git commit -m "feat(bid-write): 批卅 T2 worker 接线——run_tender_extract 在 verify 前跑摘录修复,repaired>0 打点 logger.info"
```

---

### Task 3: 真实任务数据测量(规则④:先量效益再宣称)

**Files:**
- Create: `backend/scripts/measure_quote_repair.py`(入库,可复查重跑)

- [ ] **Step 1: 测量脚本全文**(本机跑,不进容器:raw 文件与 .deer-flow 在宿主;DB 经 docker exec psql 导出 JSON 由脚本 stdin 读)

```python
"""批卅 T3:真实任务摘录修复恢复率测量(用户规则④:先量后宣)。
用法:
  1) docker exec eai-docker-postgres-ext-1 psql -U business -d sales -t -A -c \
       "select jsonb_build_object('owner_id',owner_id,'task_id',id,'meta',engine_meta) \
        from write_tasks where owner_id=(select owner_id from write_tasks order by created_at desc limit 1) \
        order by created_at desc limit 1" > /tmp/wt.json
     (表名/库名以实际为准:写作端表在 extensions 库,用 \dt 先确认)
  2) cd backend && PYTHONPATH=. uv run python scripts/measure_quote_repair.py /tmp/wt.json
输出:per-path 表(旧 verified→修复→新 verified)+ 汇总恢复率 + 矩阵 blocked 前后对比。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extensions.bid_review import parse  # noqa: E402
from app.extensions.bid_review.engine.extract import verify_quotes  # noqa: E402
from app.extensions.bid_write.quote_repair import repair_quotes  # noqa: E402

def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    meta = data["meta"]
    owner_id, task_id = data["owner_id"], data["task_id"]
    docs_meta = [e for e in (meta.get("docs") or []) if isinstance(e, dict)]
    docs = parse.docs_from_entries(owner_id, task_id, docs_meta)
    provenance = meta.get("provenance") or {}
    fields_conf = meta.get("fields_conf") or {}

    old_verified = verify_quotes(provenance, docs)
    stats = repair_quotes(provenance, docs)
    new_verified = verify_quotes(provenance, docs)

    rows = []
    for path, conf_entry in sorted(fields_conf.items()):
        p = provenance.get(path) or {}
        if path not in old_verified and path not in new_verified:
            continue  # 无 provenance 路径不参与
        rows.append((path, old_verified.get(path), new_verified.get(path), bool(p.get("repaired"))))
    fixed = sum(1 for _, o, n, _ in rows if o is False and n is True)
    print(f"stats={stats}")
    for path, o, n, rep in rows:
        print(f"{'FIXED' if rep else '    '} {path}: {o} -> {n}")
    total = len(rows)
    print(f"恢复率: {fixed}/{total - sum(1 for _, o, _, _ in rows if o)} 修复 unverified 中 {fixed} 条(old_verified True {sum(1 for _, o, _, _ in rows if o)} 条不计)")
    # 矩阵 blocked 前后(_status_of 口径: not verified and conf<0.6)
    LOW = 0.6
    def blocked_count(vmap):
        n = 0
        for path, conf_entry in fields_conf.items():
            if fields.get(path) is None:
                continue
            conf = conf_entry.get("conf")
            if not vmap.get(path, False) and isinstance(conf, (int, float)) and conf < LOW:
                n += 1
        return n
    fields = meta.get("fields") or {}
    print(f"矩阵 blocked: {blocked_count(old_verified)} -> {blocked_count(new_verified)}")

if __name__ == "__main__":
    main()
```

(执行时按实际表名/容器名修 SQL;`fields` 闭包引用在最终代码里改为参数传入——执行时落地,plan 占位不许带入提交。)

- [ ] **Step 2: 找最近真实任务,导出,跑测量**

容器名先 `docker ps --format "{{.Names}}" | grep postgres` 核对;表名 `docker exec <pg> psql -U business -d sales -c "\dt"` 核对写作端表。取**用户实际上传过招标文件的任务**(有 provenance 的最新一条)。输出保存到批卅收口记录。

Expected(推断,待实测):unverified 中 ≥60% 修复;若 <30% 则停下复盘(门槛/锚点设计问题),不硬上。

- [ ] **Step 3: 测量结果写入本 plan + Commit**

```bash
git add backend/scripts/measure_quote_repair.py docs/superpowers/plans/2026-11-18-bid-write-p1-beta30-quote-repair-plan.md
git commit -m "feat(bid-write): 批卅 T3 真实任务恢复率测量脚本+实测数字入库(规则④)"
```

---

### Task 4: 全链路真实验证(规则④:真实用户结果验证)

- [ ] **Step 1:** gateway 重启(canonical:`cd docker && docker compose -p eai-docker -f docker-compose-dev.yaml -f docker-compose.extensions.yaml -f docker-compose.ragflow.yaml restart gateway`,until 轮询 401=healthy)
- [ ] **Step 2:** UI 用同一份招标文件**新建任务**走 created→matrix_ready(QA 脚本 `qa-bidwrite-m3.mjs` 登录段复用,任务走 API 创建+直推);记录:矩阵 blocked 数(对照旧任务同文件)、"待人工核对"计数、抽查 2 条修复行点溯源 → 弹窗应定位+黄色 mark 高亮(不再 404)
- [ ] **Step 3:** 对照测量:新任务 blocked 数 ≤ 旧任务 blocked − 测量预估值(±2 容差,模型自报 conf 有波动)
- [ ] **Step 4:** 全量 pytest `tests/test_bid_write*.py` + 前端 bid-write rstest 兜底(前端零改动,跑 intake/workbench 相关即可)

---

### Task 5: 收口

- [ ] **Step 1:** plan 全勾(git add -f)+ wolf 四件套(cerebrum:quote 修复=定位-摘录分离 Tier-1/锚点+窗口法/NFKC 逐字符近似;memory 批线;anatomy quote_repair.py 条目;buglog 若有)
- [ ] **Step 2:** auto-memory `bid-write-p1-beta30-quote-repair-landed.md` + MEMORY.md 行
- [ ] **Step 3:** docs commit。**不推,等「push」。**

---

## 限制与未覆盖面(规则①诚实段)

1. **修复不改 conf**:模型自报置信仍低 → 行 verified=True 后 status=draft(不再 blocked),但"平均置信"指标仍显示低分——Tier-2(位置指针制)才动这里。
2. **错位风险**:AI 指对内容指错 doc_id → 本管线限定在该 doc 内找,错文档=诚实 unrepaired(不做跨文档兜底,防乱救)。
3. **NFKC 逐字符近似**:㎡ 等多字符展开只取首字符——招标文本罕见,golden 不覆盖;真遇到=相似度略降,门槛兜底。
4. **已解析任务不回填**:管线只作用未来抽取;旧任务想受益须重解析(重解析入口挂 QA 验证时确认)。
5. **遥测 repaired 标记**:provenance 新增 `repaired: true` 键——前端 LocateTarget 不读它,零影响;审查端引擎零改动红线未越。

## Self-Review

1. 覆盖:修复管线(模块+接线)✓ 测量(规则④先量后宣)✓ 真实验证(新任务 QA)✓
2. 占位:Task 3 SQL 表名/容器名/fields 闭包——均为"执行时按实际核对",已在文中标注,非 TBD。
3. 类型一致:provenance entry {doc_id, quote, page?};repair_quotes(provenance, docs)→stats dict;worker 单行调用。
