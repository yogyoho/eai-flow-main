"""规则包注册表——跨源索引+lint(EAI-CUSTOM 2026-11-05 R1,spec 裁决②③修正版)。

单一事实源各居其位:字段 inputs=规则包 yaml;锚点=anchors.ANCHOR_REGISTRY(代码单源);
形状契约=extract.FIELD_TYPE_CONTRACTS。本模块只做三件事,不复制任何账本:
1. universe():抽取请求字段宇宙 = 包 inputs ∪ 锚点路径 ∪ 投影字段
2. consumed_by():字段→消费者反查(改字段前先查炸谁,设计一 absorbed)
3. lint_rules():包语义校验(load_rulepack 硬拒载 + pytest 全量 lint)
依赖方向: extract → registry → anchors;rule_runner → registry。禁止反向(防环)。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.extensions.bid_review.engine.anchors import ANCHOR_REGISTRY

RULEPACK_DIR = Path(__file__).parent / "rulepacks" / "bid-review-core"

# 投影字段(spec §0 病灶③):被 worker/routers 消费但无规则 inputs 声明处的 3 条,此处即声明处。
PROJECTION_FIELDS: dict[str, str] = {
    "deviation.items": "B9 偏离表投影(routers.py)",
    "tender.scoring_items": "B4 评分办法投影(routers.py)",
    "tender.project_identity.lot_section": "task.lot_name 标段投影(worker.py)",
}

# severity 层白名单(EAI-CUSTOM 2026-11-05 R1,spec §1 enums 收敛):L1 major=业绩达标特例、
# 禁 minor(否决层无提示级);L3 禁 fatal(一致性层不否决);L2 中间层三档全放行(eval_core
# 夹具 EX-001 L2/minor 既有语义,取证修正);L4 竞争力层三档无 fatal(P1-β批二 A-β2-③:
# critical/high→major、medium→minor、info→info;fatal 拒载 lint 见 lint_rules C.1.4;
# L4 包=rulepacks/bid-review-l4 独立目录,不在 RULEPACK_DIR 扫描面,本白名单供其离线加载用)。
SEVERITY_BY_LAYER: dict[str, set[str]] = {
    "L1": {"fatal", "major"},
    "L2": {"fatal", "major", "minor"},
    "L3": {"major", "minor"},
    "L4": {"major", "minor", "info"},
}


def _pack_rules() -> list[dict]:
    out: list[dict] = []
    for p in sorted(RULEPACK_DIR.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out += data.get("rules") or []
    return out


def pack_inputs() -> set[str]:
    paths: set[str] = set()
    for r in _pack_rules():
        for p in r.get("inputs") or []:
            if isinstance(p, str):
                paths.add(p)
    return paths


def anchor_paths() -> set[str]:
    return {p for a in ANCHOR_REGISTRY.values() for p in a.get("paths", [])}


# 第二段抽取字段域(B立项 M1,spec §4,2026-11-05):进 universe(契约一致性域/lint 域)
# 但 collect_field_paths 剔除——首段 prompt 不含;R2+ 起新第二段路径(M2 section_tree/M3
# table_cells)加此处即可,universe 与首段拆分自动跟随。
SECOND_STAGE_FIELDS: dict[str, str] = {
    "bid.attachments": "附件实体层(M1):[{no,name,pages:[起,止],type_fingerprint,fingerprint_conf,is_empty_text,anchor{doc_id,page,pages,text,text_hash}}] 对象列表;逐实体一项,缺 name/pages 的行无效(零编造)",
    "bid.section_tree": '章节结构层(M2,spec §5):[{code:"章节编码或空串",title:"章节标题",toc_page:目录标注页码或null,'
    "body_page:正文标题所在物理页或null,is_empty:true|false 该节正文是否为空(文本量启发)] 对象列表;"
    "逐节一项,缺 title 的行无效(零编造);offset 由服务端按 body_page-toc_page 计算,模型禁报",
    "bid.boq_rows": '清单行级(M3,spec §5):[{id:"清单项编号",name:"项目名称",unit:"单位",qty:数量或null,price:单价或null,amount:合价金额或null}] 对象列表;'
    "逐行一项,从投标报价清单逐行提取;清单没有的行不编造;数量单价合价只引用原文数字;required 由服务端按招标 BOQ codes 回填,模型禁报",
    "bid.table_cells": '单元格层(M3,临时契约 R2+ 演进):[{table_no:"表格编号或标题",page:所在页或null,row_label:"行表头",col_label:"列表头",value:"单元格原文"}] 对象列表;'
    "逐单元格一项,只提取与报价/工期/人员等关键承诺相关的表格;空单元格跳过(零编造)",
    "bid.performance_entries": '业绩条目富行(M4,spec §5):[{name:"项目名称",client:"甲方/招标人名称",amount:合同金额或null,date:"竣工/签约日期或null",page:所在页或null}] 对象列表;'
    "逐条业绩一项,从类似业绩证明(中标通知书/合同/验收)提取;证明里没有的字段给 null(零编造)",
    "bid.performance_groups": '业绩聚类(M4,服务端产物,模型禁生成):[{group_id:"G1..",ok:true|false 确认同项去重组/疑似同项待人工(UNKNOWN,禁强行 PARTIAL),members:[原始条目]}] 对象列表;'
    "由 clusters.py 按(项目名 ≥0.80+甲方/金额/日期佐证)确定性聚类生成",
}


def universe() -> list[str]:
    """抽取请求字段宇宙 = 包 inputs ∪ 锚点路径 ∪ 投影字段 ∪ 第二段域。"""
    return sorted(pack_inputs() | anchor_paths() | set(PROJECTION_FIELDS) | set(SECOND_STAGE_FIELDS))


def consumed_by(path: str) -> dict[str, list[str]]:
    """字段→消费者反查索引:改字段前先查炸谁。"""
    rules = sorted({str(r["id"]) for r in _pack_rules() if path in (r.get("inputs") or [])})
    anchors = sorted(k for k, a in ANCHOR_REGISTRY.items() if path in a.get("paths", []))
    projections = [PROJECTION_FIELDS[path]] if path in PROJECTION_FIELDS else []
    return {"rules": rules, "anchors": anchors, "projections": projections}


def lint_rules(rules) -> list[str]:
    """包语义 lint;rules=Rule 列表(duck-typed,不 import rule_runner 防环)。"""
    problems: list[str] = []
    for r in rules:
        rid = str(getattr(r, "id", "?"))
        for ev in getattr(r, "evidence", []) or []:
            if ev not in ANCHOR_REGISTRY:
                problems.append(f"规则 {rid}: evidence 锚 {ev} 未注册(ANCHOR_REGISTRY 无此名,运行时会静默丢)")
        layer = str(getattr(r, "layer", ""))
        whitelist = SEVERITY_BY_LAYER.get(layer)
        if whitelist is None:
            problems.append(f"规则 {rid}: 未知层 {layer!r}")
        elif str(getattr(r, "severity", "")) not in whitelist:
            problems.append(f"规则 {rid}: severity {getattr(r, 'severity', '')!r} 不在 {layer} 白名单 {sorted(whitelist)}")
        if layer == "L4" and str(getattr(r, "severity", "")) == "fatal":
            problems.append(f"规则 {rid}: L4 层 severity fatal 直接拒载(C.1.4:竞争力层不否决)")  # P1-β批二 A-β2-③
        for p in getattr(r, "inputs", []) or []:
            if not isinstance(p, str) or not p.strip() or "." not in p:
                problems.append(f"规则 {rid}: input {p!r} 非点路径")
    return problems


if __name__ == "__main__":  # consumed_by 反查 CLI:无参打全表,带参打单字段
    import sys

    args = sys.argv[1:]
    if args:
        info = consumed_by(args[0])
        print(f"{args[0]}:")
        for kind, items in info.items():
            print(f"  {kind}: {', '.join(items) if items else '(无)'}")
    else:
        uni = universe()
        print(f"宇宙 {len(uni)} 路径:")
        for p in uni:
            info = consumed_by(p)
            consumers = info["rules"] + [f"@{a}" for a in info["anchors"]] + [f"→{x}" for x in info["projections"]]
            print(f"  {p:45s} {' '.join(consumers) if consumers else '(仅宇宙,无消费者)'}")
