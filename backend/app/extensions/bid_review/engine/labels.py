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
    "tender.required_sections": "必备章节",
    "tender.substantive_clauses": "实质性条款",
    "tender.tenderee_name": "招标人名称",
    "tender.device_models": "招标设备型号要求",
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
    # ── project(共享上下文)─────────────────────────────────────────
    "project.entity_whitelist.names": "主体白名单名称",
}


def label_of(path: str) -> str:
    """字段路径 → 中文名;未收录路径回退原路径(新字段不阻塞上线)。"""
    return FIELD_LABELS.get(path, path)
