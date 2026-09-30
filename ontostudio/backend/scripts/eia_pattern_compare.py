#!/usr/bin/env python3
"""EIA B 库规律归并前后对比报告（ontostudio 子项目 5 深化交付）——before/after 差异审计.

EAI-CUSTOM(2026-09-30, 子项目 5): 只读脚本，不写库、不碰容器。

用法:

    cd ontostudio/backend && PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_pattern_compare.py

输入：
  scripts/eia_pattern_mine_out/patterns_pre_merge.json  归并前基线（无归一、min_support=3、已入图 522 条）
  scripts/eia_pattern_mine_out/patterns.json            归并后（受控词表归一 + 复合名全分解、min_support=2）

输出：scripts/eia_pattern_mine_out/merge_compare.md
  总量对比 / 碎片对消失归因（旧候选逐条核销：id 消失者必须能按词表归一到新规范配对，否则显式告警）/
  Top 聚合（before→after support）/ 门槛扩量 / 词表变更记录。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# scripts/ 不是包——importlib 按文件路径加载挖掘脚本，复用其词表装载（test_eia_scope_tag.py 同法）
_MINE = Path(__file__).resolve().parent / "eia_pattern_mine.py"
_spec = importlib.util.spec_from_file_location("eia_pattern_mine", _MINE)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["eia_pattern_mine"] = _mod
_spec.loader.exec_module(_mod)

OUT_DIR, VOCAB_PATH, load_normalizer = _mod.OUT_DIR, _mod.VOCAB_PATH, _mod.load_normalizer
POSITION_TABLES = _mod.POSITION_TABLES

PRE = OUT_DIR / "patterns_pre_merge.json"
POST = OUT_DIR / "patterns.json"
OUT_MD = OUT_DIR / "merge_compare.md"

TYPES = ("治理", "标准", "处置")


def _key(pattern_type: str, e: dict) -> tuple:
    return (pattern_type, e["subject_name"], e["object_name"], e["predicate"])


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cand_map(payload: dict, min_support: int) -> dict[tuple, dict]:
    return {_key(t, e): e for t, entries in payload["patterns"].items() for e in entries if e["support_count"] >= min_support}


def main() -> None:
    pre, post = _load(PRE), _load(POST)
    normalizer = load_normalizer(VOCAB_PATH)
    pre_cand = _cand_map(pre, pre["min_support"])
    post_cand = _cand_map(post, post["min_support"])

    # 旧候选核销：id 仍在（原位存活）vs 键变更（归并/改名吸收）vs 无法归因（异常，告警）
    post_ids = {e["pattern_id"] for e in post_cand.values()}
    absorbed: list[tuple[str, dict, tuple]] = []
    unattributed: list[tuple[str, dict]] = []
    survivors = 0
    for k, old in pre_cand.items():
        if old["pattern_id"] in post_ids:
            survivors += 1
            continue
        t, s, o, p = k
        pos = POSITION_TABLES.get(t, {"subject": (), "object": ()})
        s_canon = normalizer.expand(s, pos["subject"])[0]
        o_canon = normalizer.expand(o, pos["object"])[0]
        target = (t, s_canon, o_canon, p)
        if target in post_cand and target != k:
            absorbed.append((k, old, target))
        else:
            unattributed.append((k, old))

    # 归并家族统计（按规范目标配对聚合）；变体对消失数按类型分布
    fam: dict[tuple, list[tuple]] = defaultdict(list)
    for k, old, target in absorbed:
        fam[target].append((k, old))
    fam_counts = Counter(tgt[0] for tgt in fam)

    # Top 聚合表：按新 support 降序取头部，展示 before→after
    def pre_support_of(t: str, s: str, o: str, p: str) -> int:
        return pre_cand.get((t, s, o, p), {}).get("support_count", 0)

    renamed_pairs: list[tuple] = []
    for k_new, e_new in post_cand.items():
        t, s, o, p = k_new
        pre_k = (t, s, o, p)
        before = pre_cand.get(pre_k)
        # 规范名链路：收集旧配对中能归一到本规范键的全部变体对
        vars_merged = []
        pos = POSITION_TABLES.get(t, {"subject": (), "object": ()})
        for k_old, old in pre_cand.items():
            if k_old[0] != t or k_old[3] != p:
                continue
            sc = normalizer.expand(k_old[1], pos["subject"])[0]
            oc = normalizer.expand(k_old[2], pos["object"])[0]
            if (sc, oc) == (s, o) and k_old != k_new:
                vars_merged.append(k_old)
        before_direct = before["support_count"] if before else 0
        renamed_pairs.append((e_new, before_direct, vars_merged))
    renamed_pairs.sort(key=lambda x: (-x[0]["support_count"], x[0]["subject_name"]))

    # 扩量：新候选中 support<3（旧门槛下不入图）的条数
    expanded = [e for e in post_cand.values() if e["support_count"] < 3]

    now = datetime.now(UTC).isoformat()
    L: list[str] = [
        "# EIA B 库领域规律归并前后对比报告",
        "",
        f"- 生成时间：{now}",
        f"- before = `patterns_pre_merge.json`（无归一，min_support={pre['min_support']}，即已入图 522 条基线，挖掘于 {pre['mined_at']}）",
        f"- after = `patterns.json`（受控词表归一 + 复合名全分解，min_support={post['min_support']}，挖掘于 {post['mined_at']}）",
        f"- 归一统计：名称归一命中 {post['normalization']['normalized_name_hits']} 次、复合名全分解 {post['normalization']['compound_expansions']} 次、alias 冲突 {len(post['normalization']['alias_conflicts'])} 次",
        "- support 语义保持「配对级去重报告数」：变体合并 = 报告集**并集**，不做算术累加（算术和会虚破跨报告共现定义）",
        "",
        "## 1. 总量对比",
        "",
        "| 类型 | before 配对 | before 候选(≥3) | after 配对 | after 候选(≥2) |",
        "|---|---|---|---|---|",
    ]
    for t in TYPES:
        pb, pc = pre["counts"].get(t, {"pairs": 0, "candidates": 0})["pairs"], pre["counts"].get(t, {"pairs": 0, "candidates": 0})["candidates"]
        ac, ann = post["counts"].get(t, {"pairs": 0, "candidates": 0})["pairs"], post["counts"].get(t, {"pairs": 0, "candidates": 0})["candidates"]
        L.append(f"| {t}规律 | {pb} | {pc} | {ac} | {ann} |")
    L += [
        f"| **合计** | **{sum(pre['counts'][t]['pairs'] for t in TYPES)}** | **{sum(pre['counts'][t]['candidates'] for t in TYPES)}** "
        f"| **{sum(post['counts'][t]['pairs'] for t in TYPES)}** | **{sum(post['counts'][t]['candidates'] for t in TYPES)}** |",
        "",
        "## 2. 旧候选核销（522 条入图基线的去向）",
        "",
        f"- 原位存活（pattern_id 不变，入图时 attrs 原位更新）：**{survivors}** 条",
        f"- 归并吸收（变体名→规范名后并入新配对，入图时旧节点 prune、内容并入规范 pattern）：**{len(absorbed)}** 条，聚成 **{len(fam)}** 个规范家族",
        f"- 无法归因（既不在新候选也不能按词表归一归并——**不应出现**）：**{len(unattributed)}** 条" + ("" if not unattributed else "：" + "；".join(f"{k}" for k, _ in unattributed[:10])),
        "",
        "### 归并家族明细（碎片对消失的去向）",
        "",
        "| 规范配对（去向） | 谓词 | 吸收变体对数 | 吸收的变体配对 |",
        "|---|---|---|---|",
    ]
    for tgt, items in sorted(fam.items(), key=lambda x: -len(x[1]))[:40]:
        t, s, o, p = tgt
        variants = "、".join(sorted({f"{k[1]}→{k[2]}" for k, _ in items})[:6]) + ("…" if len(items) > 6 else "")
        L.append(f"| {s}→{o} | {p} | {len(items)} | {variants} |")
    L += [
        "",
        f"规范家族按类型分布：{dict(sorted(fam_counts.items()))}",
        "",
        "## 3. Top 聚合（规范名归并后 support 变化，头部 25）",
        "",
        "| 规范配对 | 谓词 | before support（同名直接对比） | 并入变体对 | after support |",
        "|---|---|---|---|---|",
    ]
    for e_new, before_direct, vars_merged in renamed_pairs[:25]:
        vs = "、".join(sorted({f"{k[1]}→{k[2]}" for k in vars_merged})[:4]) + ("…" if len(vars_merged) > 4 else "") if vars_merged else "—"
        L.append(f"| {e_new['subject_name']}→{e_new['object_name']} | {e_new['predicate']} | {before_direct} | {vs} | {e_new['support_count']} |")
    L += [
        "",
        "## 4. 门槛扩量（min-support 3→2）",
        "",
        f"- 新候选中 support=2 的条目 **{sum(1 for e in expanded if e['support_count'] == 2)}** 条——旧门槛（≥3）下这些跨项目弱共性不入图，本次纳入覆盖。",
        f"- 合计扩量候选 **{len(expanded)}** 条（含复合名展开新增的规范配对）。",
        "",
        "## 5. 受控词表变更记录（本次归并的归一依据）",
        "",
        "- `pollutant_concept.悬浮物` aliases 增补：`悬浮`、`悬浮性固体`（图内实测碎片变体）",
        "- 新增 `disposal_target_concept` 表（二批共 7 概念）：一批=「有资质单位」（13 aliases，org 与 treatment_measure 两 etype 上的变体均收编）、「环卫部门」（当地/地方/城建 3 泛称）；",
        "  二批=「井下充填」（17 aliases：回填井下/充填/采空区注浆充填/井下膏体充填/井下废弃巷道 等）、「沉陷区充填」（10：充填沉陷区/塌陷坑/塌陷土地复垦/回填矿区洼地 等）、",
        "  「采坑回填」（6：含新岭/金运具名坑池）、「市政垃圾处理厂」（9）、「场地平整」（3）",
        "- 归一作用域=模式位置（治理主语→pollutant 表、治理宾语→measure 表、处置宾语→disposal∪measure 表），同名跨表冲突天然消解（如「矸石井下充填」）",
        "- 既有表按别名大小写不敏感生效：ss/COD/CODCr/NOx/SO2/TSP/PM10/PM2.5/粉尘/烟尘→规范名等",
        "- 未归并残差（明确不动，留抽取层/人审治理）：waste_stream 项目专名碎片（任家庄煤矿矸石 等）、「处理后回用/回用」家族、排土场/排矸场/周转场堆存条目族（与处置语义有别不并）、",
        "  填沟造地/黄土掩埋/不出井/合理处置/无害化处置率100%、伊敏污水处理厂同名异写、复合名未全分解者（含 bod/bod5/筑路基 等词表外段）、生活垃圾中转站与焚烧发电具名公司条目",
        "",
        "## 6. 入图对账指引",
        "",
        f"- after 候选 **{len(post_cand)}** 条 → `eia_pattern_ingest.py --min-support 2 --apply --prune`：新建/原位更新后，图内旧基线中 {len(absorbed)} 条归并吸收节点删除，预计图内 domain_pattern 稳定为 **{len(post_cand)}** 条。",
        "- 幂等：重跑 ingest 应全部 `原位更新 + 边已存在 + prune 0`。",
    ]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"落盘: {OUT_MD}")
    print(f"存活 {survivors} / 吸收 {len(absorbed)}（{len(fam)} 家族）/ 无法归因 {len(unattributed)}；after 候选 {len(post_cand)}")


if __name__ == "__main__":
    main()
