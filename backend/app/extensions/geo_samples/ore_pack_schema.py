# EAI-CUSTOM (geo-batch-cli P5, spec 2026-09-03): ore_pack schema 机器可校验器。
# 防 v1「prose 不可校验」复辟：批量孵化草稿必须过此校验才可人审/落 repo（Task 5 管线
# 约定：errors 非空仍落草稿表供人审可见，approve 前置=errors==[]）。
# 契约真源 = 本文件常量 + skills/public/geological-report/references/ore_packs/README.md；
# copper.json 为契约活样例——改动常量须保证其 PASS（test_geo_sample_bank_compile.py 回归锁）。
# 纯函数零依赖（stdlib only），供抽取管线/CLI/测试共用。
from __future__ import annotations

import json

# 必有元数据键
REQUIRED_META = ("version", "ore", "generated")
# 业务键白名单（8 键同 copper.json 实例 + std_ref 规范出处——以实例校准，非反之）
KNOWN_BUSINESS_KEYS = {
    "basic_analysis_items",  # 数组：基本分析项目
    "phase_analysis",  # 对象：物相分析（含 zone_split_rule【待核实】形态）
    "ore_natural_types_anchored",  # 对象：矿石自然类型（sample_verbatim 锚定）
    "byproduct_policy",  # 串：伴生组分评价政策（formulas L11 锚定）
    "bulk_density_practice",  # 对象：小体重样实践
    "green_exploration",  # 串：绿色勘查要求
    "typical_deposit_models",  # 对象数组：典型矿床式
    "reporting_notes",  # 数组：报告叙述要点
    "std_ref",  # 串：规范出处（copper.json 实例携带）
}
# 词表单源裁决：5 production slug（other 不孵化）。
# 与 build_output.MINERAL_ALIASES / title_parser.MINERAL_KEYWORDS 双向同步（DNR）。
KNOWN_SLUGS = {"copper", "coal", "gold", "iron", "lead_zinc"}
# 锚点集 = copper.json 实例使用的 formulas 编号（DZ 标准估算链公式表编号）
ANCHOR_TOKENS = ("L11", "S1", "B1", "E3", "E4")
# 未核实阈值的唯一合法形态值
PENDING = "【待核实】"

# 业务键类型契约（README 同步声明；仅对出现的键做类型校验）
_EXPECTED_TYPES: dict[str, type] = {
    "basic_analysis_items": list,
    "phase_analysis": dict,
    "ore_natural_types_anchored": dict,
    "byproduct_policy": str,
    "bulk_density_practice": dict,
    "green_exploration": str,
    "typical_deposit_models": list,
    "reporting_notes": list,
    "std_ref": str,
}
_TYPE_NAMES = {list: "数组", dict: "对象", str: "串"}


def validate_ore_pack(doc: dict) -> list[str]:
    """校验 ore_pack 文档，返回中文错误串列表；空列表 = PASS。

    守卫链：元数据齐备 → slug 词表 → 锚点守卫（≥1 个 formulas 编号）→ 顶层键白名单
    → 业务键类型 → 【待核实】形态（zone_split_rule 结构 + 任意嵌套 status 须为
    {"status": "【待核实】"} 形态，裸串阈值不可机校验即拒）。
    """
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["ore_pack 必须为 JSON 对象"]

    for key in REQUIRED_META:
        if key not in doc:
            errors.append(f"缺元数据键: {key}")

    ore = doc.get("ore")
    if ore not in KNOWN_SLUGS:
        errors.append(f"ore slug 非法: {ore!r}（须 ∈ {sorted(KNOWN_SLUGS)}；other 不孵化）")

    # 锚点守卫：全文（含嵌套值）含任一 formulas 编号即过——零引用 = prose 复辟
    blob = json.dumps(doc, ensure_ascii=False, default=str)
    if not any(tok in blob for tok in ANCHOR_TOKENS):
        errors.append(f"零 formulas 锚点引用（{'/'.join(ANCHOR_TOKENS)}）——prose 复辟，拒绝")

    unknown = set(doc) - set(REQUIRED_META) - KNOWN_BUSINESS_KEYS
    if unknown:
        errors.append(f"未知键: {sorted(unknown)}（白名单见 references/ore_packs/README.md）")

    for key, typ in _EXPECTED_TYPES.items():
        if key in doc and not isinstance(doc[key], typ):
            errors.append(f"类型不符: {key} 须为{_TYPE_NAMES[typ]}")

    # 【待核实】形态守卫①：phase_analysis 必含 zone_split_rule 结构
    pa = doc.get("phase_analysis")
    if isinstance(pa, dict):
        zsr = pa.get("zone_split_rule")
        if not isinstance(zsr, dict):
            errors.append(f'形态不符: phase_analysis.zone_split_rule 缺失或非对象——必须为 {{"status": "{PENDING}", ...}} 形态')
        elif "status" not in zsr:
            errors.append(f'形态不符: phase_analysis.zone_split_rule 缺 status——必须为 {{"status": "{PENDING}", ...}} 形态')

    # 【待核实】形态守卫②：任意嵌套层出现 status 键 → 值必须恰为【待核实】
    _walk_status(doc, "", errors)

    return errors


def _walk_status(node: object, path: str, errors: list[str]) -> None:
    """递归扫描嵌套 dict/list；status 键的值非【待核实】形态值（裸串阈值等）即报错。"""
    if isinstance(node, dict):
        for k, v in node.items():
            child = f"{path}.{k}" if path else str(k)
            if k == "status" and v != PENDING:
                errors.append(f'形态不符: {child} 须为 "{PENDING}"——裸串阈值不可机校验，拒绝')
            else:
                _walk_status(v, child, errors)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_status(v, f"{path}[{i}]", errors)
