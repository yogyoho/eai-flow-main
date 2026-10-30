"""A-* 锚点注册表(EAI-CUSTOM 2026-10-30 二期,spec §三)。

ui-gaps 文档「anchors.py 存在,未上 wire」有误——本文件在二期前从未存在;实际
状态是规则包 1.0.0.yaml 全部 det 规则的 evidence: [A-PRICE-SHEET, ...] 锚名
漂浮无解析。真实残余价值(routers.py:490 回退注释的现行账):attach_evidence
只回填 rule.inputs ∩ provenance,锚点把证据源扩到「inputs ∪ 锚点映射路径」,
det issue 证据 chips 更丰满;注册表同时是 20 个锚名的唯一语义档案。

三方同步契约:规则包 evidence 锚名 / 本表 / labels.FIELD_LABELS——新增锚名
须先落本表,否则 resolve 静默跳过(诚实降级,与既有 provenance 缺失同口径)。
"""

from __future__ import annotations

ANCHOR_REGISTRY: dict[str, dict] = {
    # ── 招标侧 ────────────────────────────────────────────────────────
    "A-TENDER-NOTICE": {
        "label": "招标公告/招标文件正文",
        "paths": [
            "tender.project_identity.name",
            "tender.project_identity.code",
            "tender.max_price",
            "tender.price_includes_tax",
            "tender.tax_rate",
            "tender.currency",
            "tender.boq_items",
            "tender.bid_scope",
            "tender.bid_deadline",
            "tender.required_qual_level",
            "tender.required_validity_days",
            "tender.deposit_required",
            "tender.max_duration",
            "tender.min_warranty_period",
            "tender.min_similar_performance_count",
            "tender.required_declarations",
            "tender.required_sections",
            "tender.substantive_clauses",
            "tender.tenderee_name",
            "tender.device_models",
        ],
    },
    "A-TENDER-BOQ": {"label": "招标工程量清单", "paths": ["tender.boq_items"]},
    # ── 投标侧:价格 ──────────────────────────────────────────────────
    "A-PRICE-SHEET": {
        "label": "投标报价汇总表",
        "paths": [
            "bid.total_price",
            "bid.total_price_words",
            "bid.price_includes_tax",
            "bid.currency_occurrences",
            "bid.tax_rate_occurrences",
            "bid.alternative_price_offers",
            "bid.amount_occurrences",
        ],
    },
    "A-PRICE-DETAIL": {
        "label": "报价明细表",
        "paths": ["bid.detail_rows", "bid.subtotal", "bid.boq_unit_checks"],
    },
    "A-BOQ": {
        "label": "投标工程量清单",
        "paths": ["bid.boq_items", "bid.boq_unit_checks"],
    },
    # ── 投标侧:主体/资质 ────────────────────────────────────────────
    "A-LICENSE": {
        "label": "营业执照/资质证书",
        "paths": [
            "bid.entity.license_name",
            "bid.entity.license_valid_until",
            "bid.entity.business_scope",
            "bid.qual_levels",
        ],
    },
    "A-QUAL-CERT": {"label": "资质证书", "paths": ["bid.qual_levels"]},
    "A-BID-LETTER": {
        "label": "投标函",
        "paths": [
            "bid.entity.name_in_bid_letter",
            "bid.bid_letter_date",
            "bid.bid_letter_signatory",
            "bid.validity_days",
            "bid.total_price",
        ],
    },
    "A-POA": {
        "label": "授权委托书",
        "paths": ["bid.authorization_letter_present", "bid.authorization_signatory"],
    },
    "A-DEPOSIT": {"label": "保证金凭证", "paths": ["bid.deposit_amount"]},
    "A-PERF-DOCS": {"label": "业绩证明", "paths": ["bid.similar_performances"]},
    "A-PERSONNEL": {
        "label": "人员配置",
        "paths": ["bid.personnel_commercial", "bid.personnel_technical"],
    },
    "A-STAMP": {"label": "签署盖章页", "paths": ["bid.missing_signature_pages"]},
    "A-DECLARATION": {"label": "声明函", "paths": ["bid.declaration_letter_codes"]},
    # ── 投标侧:工期/技术/文件结构 ──────────────────────────────────
    "A-SCHEDULE": {
        "label": "进度计划表",
        "paths": ["bid.duration_schedule", "bid.schedule_start_date", "bid.schedule_end_date"],
    },
    "A-MAIN-TEXT": {
        "label": "投标正文",
        "paths": ["bid.duration_main_text", "bid.old_project_mentions", "bid.appendix_references"],
    },
    "A-COMMIT": {
        "label": "承诺函",
        "paths": [
            "bid.duration_commitment_letter",
            "bid.commitment_completion_date",
            "bid.commitment_letter_date",
            "bid.warranty_period",
        ],
    },
    "A-TECH-PROPOSAL": {
        "label": "技术方案",
        "paths": ["bid.device_models", "bid.device_model_mismatches"],
    },
    "A-HEADER": {
        "label": "封面/页眉页脚",
        "paths": ["bid.header_footer.project_name", "bid.document_version"],
    },
    "A-TOC": {"label": "投标文件目录", "paths": ["bid.toc_section_codes"]},
}


def anchor_rule_paths(evidence_ids: list[str], rule_inputs: list[str]) -> list[str]:
    """规则的证据取数路径 = inputs ∪ 锚点映射路径(inputs 优先序保持;未注册锚名
    静默跳过——诚实降级)。attach_evidence 消费,证据源从 inputs 扩到锚点区域。"""
    out = list(rule_inputs)
    seen = set(rule_inputs)
    for aid in evidence_ids or []:
        entry = ANCHOR_REGISTRY.get(aid)
        if not entry:
            continue
        for p in entry.get("paths") or []:
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out
