"""字段中文名映射(EAI-CUSTOM 2026-10-30 二期,spec §四;ui-gaps spec 提案 A②并入)。

66+ 字段路径 → 中文名,前端字段卡/完备性聚合卡/need_human 卡统一消费(baselines
GET 顶层 labels 投影)。与 FIELD_DICTIONARY + 规则包 inputs 三方契约同步:改动
extract.FIELD_DICTIONARY / 规则包 inputs 时须同步本表;缺路径回退原路径名
(label_of),不阻塞新字段上线。
"""

from __future__ import annotations

FIELD_LABELS: dict[str, str] = {
    # ── tender(招标基准)────────────────────────────────────────────
    "tender.project_identity.name": "项目名称",
    "tender.project_identity.code": "项目编号",
    "tender.project_identity.lot_section": "标段",  # B1 裁定12(2026-10-31)
    "tender.max_price": "最高限价",
    "tender.price_includes_tax": "报价含税要求",
    "tender.tax_rate": "税率要求",
    "tender.currency": "招标币种",
    "tender.boq_items": "招标工程量清单",
    "tender.bid_scope": "招标范围",
    "tender.bid_deadline": "投标截止时间",
    "tender.required_qual_level": "资质等级要求",
    "tender.required_validity_days": "投标有效期要求(天)",
    "tender.deposit_required": "投标保证金要求",
    "tender.max_duration": "最长工期要求",
    "tender.min_warranty_period": "最短质保期要求",
    "tender.min_similar_performance_count": "类似业绩数量要求",
    "tender.required_declarations": "必备承诺函",
    "tender.required_fields": "招标必填字段/清单行",  # R2+ L2-041 消费(plan 2026-11-05;整合版编号对齐 2026-11-06,原 EAI L2-022)
    "tender.required_sections": "必备章节",
    "tender.substantive_clauses": "实质性条款",
    "tender.tenderee_name": "招标人名称",
    "tender.device_models": "招标设备型号要求",
    "tender.scoring_items": "评分办法项",  # B4 评分覆盖度(spec §5)
    "deviation.items": "响应偏离表",  # B9(spec 2026-11-01 §1.1)
    "tender.allowed_submit_methods": "允许递交方式集合",  # 批十六 A-ADJ-1 方式集维 L1-026 inputs
    "tender.attachment_requirements": "附件要求",  # L2 P1 附件核对(spec 2026-11-02 §1)
    # ── 批八扫尾(2026-11-08,plan A-β8-④:universe−labels 差集 54 兑付;批六/批七沿袭债)──
    "tender.commitment_sections": "承诺类章节要求",  # 批六 T1 L2-013 inputs
    "tender.consortium_allowed": "联合体投标允许",  # 批六 T1 L1-017 inputs
    "tender.deposit_forms": "保证金缴纳形式要求",  # 批六 T1 L1-006 inputs
    "tender.electronic_files": "电子标书要求",  # 批二续 L2-003
    "tender.file_composition": "投标文件组成要求",  # 批二续 L2-001
    "tender.format_requirements.copies": "投标文件份数要求",  # 批七 L1-022 inputs
    "tender.format_requirements.font": "投标文件字体要求",  # 批七 L1-022 inputs
    "tender.format_requirements.page_numbering": "投标文件页码要求",  # 批七 L1-022 inputs
    "tender.format_requirements.sealing": "密封标识要求",  # 批七 L1-022 inputs
    "tender.format_requirements.toc": "投标文件目录要求",  # 批七 L1-022 inputs
    "tender.min_performance_amount": "类似业绩最低金额要求",  # 批六 T4 L1-003 富化
    "tender.performance_window_months": "业绩考核年限窗口(月)",  # 批六 T4 L1-003 富化
    "tender.pm_req.certs": "项目负责人持证要求",  # 批七 L1-004 inputs
    "tender.pm_req.exclusive": "项目负责人专职要求",  # 批七 L1-004 inputs
    "tender.pm_req.social_months": "项目负责人社保月数要求",  # 批七 L1-004 inputs
    "tender.required_figures": "必备附图/图表要求",  # 批六 T1 L2-014 inputs
    "tender.required_signatures": "招标签章要求清单",  # 批七 L1-007 富化
    "tender.required_tables": "必备表格要求",  # 批六 T1 L2-040 inputs
    "tender.signature_slots": "招标要求签署位",  # 批二续 T3 L2-030
    "tender.subcontract_limit.allowed": "分包允许",  # 批七 L1-020 inputs
    "tender.subcontract_limit.scope": "分包允许范围",  # 批七 L1-020 inputs
    "tender.tech_sections_required": "技术方案必备章节",  # 批六 T1 L2-012 inputs
    "tender.volume_specs": "招标分册份数要求",  # 批二续 L2-002
    "bid.attachment_index": "投标附件清单",  # L2 P1 附件核对(spec 2026-11-02 §1)
    # ── bid(投标响应)───────────────────────────────────────────────
    "bid.total_price": "投标总报价",
    "bid.total_price_words": "总报价大写金额",
    "bid.price_includes_tax": "投标报价含税",
    "bid.detail_rows": "报价明细行",
    "bid.subtotal": "报价小计",
    "bid.boq_items": "投标工程量清单",
    "bid.boq_unit_checks": "清单单价核对",
    "bid.alternative_price_offers": "备选报价方案",
    "bid.amount_occurrences": "金额全文出现记录",
    "bid.currency_occurrences": "币种全文出现记录",
    "bid.tax_rate_occurrences": "税率全文出现记录",
    "bid.entity.license_name": "营业执照名称",
    "bid.entity.license_valid_until": "营业执照有效期至",
    "bid.entity.business_scope": "营业执照经营范围",
    "bid.entity.name_in_bid_letter": "投标函投标人名称",
    "bid.entity_name_occurrences": "投标人名称全文出现记录",
    "bid.header_footer.project_name": "页眉页脚项目名称",
    "bid.bid_letter_date": "投标函日期",
    "bid.bid_letter_signatory": "投标函签署人",
    "bid.authorization_letter_present": "授权委托书是否提供",
    "bid.authorization_signatory": "授权委托书签署人",
    "bid.qual_levels": "投标资质等级",
    "bid.validity_days": "投标有效期(天)",
    "bid.deposit_amount": "投标保证金金额",
    "bid.duration_main_text": "正文工期",
    "bid.duration_schedule": "进度计划工期",
    "bid.duration_commitment_letter": "承诺函工期",
    "bid.schedule_start_date": "进度计划开始日期",
    "bid.schedule_end_date": "进度计划结束日期",
    "bid.commitment_completion_date": "承诺函完工日期",
    "bid.commitment_letter_date": "承诺函日期",
    "bid.warranty_period": "质保期",
    "bid.similar_performances": "类似业绩",
    "bid.personnel_commercial": "商务标人员信息",
    "bid.personnel_technical": "技术标人员信息",
    "bid.missing_signature_pages": "缺签署页",
    "bid.declaration_letter_codes": "承诺函编号",
    "bid.device_models": "投标设备型号",
    "bid.device_model_mismatches": "设备型号偏差",
    "bid.toc_section_codes": "目录章节编号",
    "bid.appendix_references": "附件引用",
    "bid.document_version": "文件版本",
    "bid.version_tag_occurrences": "版本标识出现记录",
    "bid.old_project_mentions": "旧项目名称残留",
    "bid.tenderee_name_mentions": "招标人名称提及",
    # ── 批八扫尾(2026-11-08,plan A-β8-④ 续)──
    "bid.archive_files": "压缩包内文件",  # 批二续 T2 L2-004
    "bid.attachments": "投标附件",  # M1 附件实体层
    "bid.boq_rows": "投标工程量清单行",  # M3 表格层
    "bid.consortium": "联合体协议书实体",  # 批六 T1 L1-017 inputs
    "bid.deposit_forms": "保证金实际缴纳形式",  # 批六 T1 L1-006 inputs
    "bid.deposit_receipt_present": "保证金凭证存在性",  # 批二续 T3 L2-033(服务端派生)
    "bid.electronic_files": "电子标书文件",  # 批二续 L2-003
    "bid.figures": "图纸/图表清单",  # 批六 T1 L2-012 inputs
    "bid.file_index": "投标文件索引",  # 批二续 L2-001
    "bid.files": "全量文件清单",  # 批二续 T2 L2-050
    "bid.format.copies": "投标文件实际份数",  # 批七 L1-022 inputs
    "bid.format.font": "投标文件实际字体",  # 批七 L1-022 inputs
    "bid.format.page_numbering": "投标文件实际页码",  # 批七 L1-022 inputs
    "bid.format.sealing_label": "密封标识实际",  # 批七 L1-022 inputs
    "bid.format.toc": "投标文件实际目录",  # 批七 L1-022 inputs
    "bid.full_text": "全文域",  # 批二续 T2 L2-051(服务端派生)
    "bid.id_copy_present": "身份证复印件存在性",  # 批二续 T3 L2-032(服务端派生)
    "bid.is_consortium": "联合体投标标识",  # 批六 T1 L1-017 inputs
    "bid.legal_id_proof_present": "法人身份证明存在性",  # 批二续 T3 L2-032(服务端派生)
    "bid.performance_entries": "业绩条目",  # M4 聚类层
    "bid.performance_groups": "业绩聚类组",  # M4 聚类层
    "bid.pm.certs": "拟任项目负责人持证",  # 批七 L1-004 inputs
    "bid.pm.on_other_project": "拟任项目负责人在建任职",  # 批七 L1-004 inputs
    "bid.pm.social_months": "拟任项目负责人社保月数",  # 批七 L1-004 inputs
    "bid.section_tree": "章节树",  # M2 章节层
    "bid.service_commitments": "分包相关服务承诺",  # 批七 L1-020 inputs
    "bid.signature_slots": "投标签署位(实际)",  # 批二续 T3 L2-030
    "bid.submit_method": "投标递交方式",  # 批十六 A-ADJ-1 方式集维 L1-026 inputs
    "bid.submit_time": "投标文件递交时间",  # 批七 L1-026 inputs
    "bid.table_cells": "表格单元格",  # M3 表格层
    "bid.tables": "表格骨架",  # 批六 T2(服务端派生)
    "bid.volume_index": "投标分册索引",  # 批二续 L2-002
    # ── project(共享上下文)─────────────────────────────────────────
    "project.entity_whitelist.names": "主体白名单名称",
}


def label_of(path: str) -> str:
    """字段路径 → 中文名;未收录路径回退原路径(新字段不阻塞上线)。"""
    return FIELD_LABELS.get(path, path)
