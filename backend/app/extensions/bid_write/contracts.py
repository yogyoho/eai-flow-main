"""bid_write 契约层(批十九 T1,EAI-CUSTOM 2026-11-13)——写作端字段/槽位/断言
词汇表。真源原则:审查端 tender.* 契约真源=bid_review.engine.extract.FIELD_TYPE_
CONTRACTS,本模块只 **import 引用** 不复制(双真源=漂移);写作端新增面(response_
matrix/material.*/槽位系统/降级等级/禁用词)落本文件,SCHEMA_VERSION 单调递增。

对应设计稿《投标方案(商务部分)智能写作》§四(数据结构)/P0 规格 §0(通用约定):
槽位语法/槽位类型系统/降级等级 D0-D3/断言编号 SK-<SKILL>-<n>/错误码 E-<SK>-<n>。
"""

from __future__ import annotations

# 契约版本(设计稿「与审查端同版本管理」的落点:审查端契约经 import 随引擎演进,
# 写作端新增面以本版本号钉;破坏性变更必须 bump + golden 全量重审)。
SCHEMA_VERSION = "1.0.0"

# ── 导出前置校验(F6/批廿一 M2;P0 规格 §8)────────────────────────────────
# 阻断层级口径钉死:D0 断言 FAIL/ERROR 或规则层 L1 fatal det FAIL→禁导出。
# gate_verdict(executor/gate.py)消费同口径,本常量=防漂移钉(测试对锁)。
BLOCK_EXPORT_LEVELS = ("D0",)
# 风险水印:L4 竞争力包全语义规则,写侧预审查不喂模型→L4 恒未评估→导出物
# 恒带水印(诚实:商务风险未经模型确认)。M2 后接模型审查再评估摘除条件。
EXPORT_RISK_WATERMARK = "商务风险未确认"

# ── response_matrix 行契约(F1;设计稿 §四)────────────────────────────────
# 行形: {clause_id, requirement, source_path, star, strategy, target_section,
#        evidence_refs, status, conf, verified, kind}
# clause_id 确定性生成(矩阵装配唯一约束;同一招标文件重解析同 key,幂等重跑)。
MATRIX_STRATEGIES = ("pending", "full", "positive", "negative")  # 未定/完全响应/正偏离/负偏离
MATRIX_STATUSES = ("draft", "confirmed", "blocked")  # 草稿/人工确认/阻断(低置信未确认禁入生成)
ROW_KINDS = ("attachment", "clause", "aggregate")  # 附件要求行/★承诺条款行/聚合要素行

# ── 素材实体六类(F2/P1;M0 仅类型枚举,实体表批二十)──────────────────────
# 设计稿 §四 material.*:资质/业绩/人员/产能/网点/历史标书;verifiable=有可佐证附件。
MATERIAL_ENTITY_TYPES = (
    "qualification",  # 资质(营业执照/MA·KA/防爆合格证/型式检验/审计/纳税社保)
    "performance",  # 同类业绩(机型/工作面/吨位/合同额/验收时间)
    "personnel",  # 人员(项目经理/授权代表)
    "capacity",  # 产能与排产
    "network",  # 服务网点与响应时限支撑
    "past_bid",  # 历史标书(脱敏段落沉淀)
)

# ── 槽位类型系统(P0 规格 §0.2;渲染器/校验器批二十消费)───────────────────
# 校验器名=批二十 generators 公共件注册表键;M0 只钉词汇与语义,不落执行器。
SLOT_TYPES = (
    "str",  # 自由文本(长度/禁用词/占位符检测)
    "enum",  # 枚举(白名单成员)
    "decimal",  # 数值 Decimal 2 位 ROUND_HALF_UP
    "date",  # 日期(时序约束,如 sign_date ≤ deadline)
    "money",  # 金额(大小写成对互转一致)
    "entity_ref",  # 素材实体 ID(存在性+字段一致性;M0 无实体库→一律 D0 缺件)
    "list",  # list[T](非空/唯一键/覆盖率)
    "computed",  # 确定性计算槽位 {{calc(expr)}},禁 LLM 参与
)

# ── 降级等级(P0 规格 §0.3,全局统一)──────────────────────────────────────
# D0 阻断(不可导出,进待补清单)/ D1 降级(可导出标黄,计预审查 UNKNOWN)/
# D2 提示(看板提示)/ D3 静默。
DEGRADE_LEVELS = ("D0", "D1", "D2", "D3")
BLOCK_EXPORT_LEVELS = ("D0",)  # 导出前置校验阻断面(M2 §5.3 消费)

# ── F1 商务抽取子集(tender.* 真实宇宙路径,零新增契约)─────────────────────
# 全部为 bid_review.engine.registry.universe() 既有成员(M0 不造新抽取契约);
# 矩阵装配只消费这些路径;星级面=tender.attachment_requirements.mandatory=="★"
# 行 + tender.required_declarations(★承诺条款),无 tender.clauses(P0 规格
# tender.clauses(star) 为愿景名,M0 以 required_declarations+attachment_requirements
# 承接;substantive_clauses 专项契约挂 M2 与 L4 激活同批落地)。
COMMERCIAL_TENDER_SUBSET: tuple[str, ...] = (
    # F1 矩阵直接行源
    "tender.attachment_requirements",
    "tender.required_declarations",
    "tender.required_signatures",
    "tender.signature_slots",
    # 聚合要素行
    "tender.deposit_required",
    "tender.deposit_forms",
    "tender.bid_deadline",
    "tender.required_validity_days",  # SK-BL-003 有效期操作数(L1-005 同源,v3 输入面补漏)
    "tender.bid_scope",
    "tender.required_sections",
    "tender.required_tables",
    "tender.required_fields",
    "tender.volume_specs",
    # 资格门槛行(M0 存值,M2 预审查 L1 消费)
    "tender.required_qual_level",
    "tender.min_performance_amount",
    "tender.performance_window_months",
    # 商务承诺对照(M2 预审查 L1/L4 消费;矩阵存对照行)
    "tender.min_warranty_period",
    "tender.max_duration",
    # 条件段(F4 模板 {{#if}} 面)
    "tender.consortium_allowed",
    # 导出适配(F8 后续批消费,M0 随抽取顺带落库)
    "tender.allowed_submit_methods",
    "tender.electronic_files",
)

# ── 禁用词表(P0 规格 §1.4/§2.6/§3.4/§4.4 归并;扫描器批二十公共件消费)──────
# 处置级:词 → (降级级, 处置说明)。白名单机制 P1(policy 联动);M0 词表只读。
FORBIDDEN_WORDS: dict[str, tuple[str, str]] = {
    # 绝对化(改写为受约束表述;白名单外 D1)
    "无条件": ("D1", "绝对化承诺,收敛为受约束表述"),
    "绝不": ("D1", "绝对化承诺"),
    "无限期": ("D1", "改为明确期限"),
    "终身": ("D1", "改为明确期限(如质保期 N 个月内)"),
    "包过": ("D0", "违规暗示"),
    "保证中标": ("D0", "围标串标红线,命中告警"),
    "内部渠道": ("D0", "合规红线"),
    "围标": ("D0", "合规红线"),
    "串标": ("D0", "合规红线"),
    # 模糊承诺(替换为确定表述或删除)
    "尽量": ("D1", "模糊承诺"),
    "力争": ("D1", "模糊承诺"),
    "原则上": ("D1", "模糊限定"),
    "视情况": ("D1", "模糊限定"),
    "酌情": ("D1", "模糊限定"),
    "尽可能": ("D1", "模糊承诺"),
    "基本满足": ("D1", "模糊限定(响应表空应答邻域)"),
    "按现场实际": ("D1", "模糊限定"),
    # 模糊调价(报价说明面;无调价机制时 D0)
    "暂估": ("D0", "无调价机制时禁止"),
    "以最终结算为准": ("D0", "无调价机制时禁止"),
    "另行协商": ("D0", "无调价机制时禁止"),
    "随市场调整": ("D0", "无调价机制时禁止"),
    "价格另议": ("D0", "无调价机制时禁止"),
    # 占位符(正文命中 D0)
    "待补充": ("D0", "占位符"),
    "待定": ("D0", "占位符"),
    "TBD": ("D0", "占位符"),
    "XX": ("D0", "占位符(大小写不敏感)"),
    # 空应答(响应表面;无参数化内容即 D0)
    "满足招标文件要求": ("D0", "空应答,须参数化应答"),
    "符合招标文件要求": ("D0", "空应答"),
    "按招标文件执行": ("D0", "空应答"),
    "无异议": ("D0", "空应答"),
}

# 占位符大小写不敏感面(扫描器对下列词做 upper() 匹配)
FORBIDDEN_CASE_INSENSITIVE = ("TBD", "XX")

# ── 断言注册词汇(P0 规格 §0.4;注册表 YAML=bid_write/assertions/,批二十执行器)──
# 断言编号 SK-<SKILL>-<序号>;错误码 E-<SK>-<序号> 一一对应。
# CMN=共享层(导出级全文扫描 SK-CMN-001..005,v2 规格):技能级断言只做本技能范围,
# 全文面归 CMN;同口径只允许一份实现(AI-009 delegates_to CMN-005,执行器不重复跑)。
SKILL_IDS = ("BL", "PS", "RT", "AI", "CMN")  # bid_letter/price_sheet/response_table/attachment_index/+shared


def assertion_id(skill: str, n: int) -> str:
    """SK-<SKILL>-<序号:03d>(规格 §0.4);skill 须在 SKILL_IDS。"""
    if skill not in SKILL_IDS:
        raise ValueError(f"未知技能编号 {skill!r}(合法:{SKILL_IDS})")
    return f"SK-{skill}-{n:03d}"


def error_code(skill: str, n: int) -> str:
    """E-<SK>-<序号:03d>,与断言一一对应(日志/待补清单写入用)。"""
    if skill not in SKILL_IDS:
        raise ValueError(f"未知技能编号 {skill!r}(合法:{SKILL_IDS})")
    return f"E-{skill}-{n:03d}"
