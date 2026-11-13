"""批二十 M1 执行器 ctx 夹具构造器(EAI-CUSTOM 2026-11-13)——green_ctx()=断言
全绿基线(Task 2 起分批充实到 43 条全覆盖),负例=调用侧变异或 golden 注入
(cases-write/exec-negatives.yaml,Task 4)。tender 形状=审查端
FIELD_TYPE_CONTRACTS 真源零漂移引用(attachment_requirements{no,name,clause,
mandatory,min_count,year_span,src} / volume_specs{name,min_copies})。"""

from __future__ import annotations


def green_ctx() -> dict:
    """43 条断言全绿基线上下文。键契约=executor 校验器契约表(plan/批二十 M1)。"""
    return {
        "tender": {
            "tender.attachment_requirements": [
                {"no": "1", "name": "营业执照", "clause": "3.1", "mandatory": "★", "min_count": 1, "year_span": None, "src": "tender_mandatory"},
                {"no": "2", "name": "矿用产品安全标志证书", "clause": "3.2", "mandatory": "必需", "min_count": 1, "year_span": None, "src": "tender_mandatory"},
            ],
            "tender.volume_specs": [
                {"name": "商务卷", "min_copies": 2},
                {"name": "技术卷", "min_copies": 1},
            ],
            "tender.required_validity_days": 90,
            "tender.bid_deadline": "2026-12-01 09:00",
            "tender.max_price": 1000000,
            "tender.boq_items": [
                {"name": "设备安装", "qty": 2, "unit": "套"},
                {"name": "调试服务", "qty": 1, "unit": "项"},
            ],
        },
        "products": {
            "bid_letter": {
                "slots": {
                    "tender_purchaser_name": "XX矿业集团有限公司",
                    "project_name": "某矿井智能化建设项目",
                    "tender_no": "TB-2026-001",
                    "total_amount_cn": "贰佰万元整",
                    "total_amount_num": 2000000,
                    "valid_days": 90,
                    "deposit_amount": 100000,
                    "deposit_form": "银行保函",
                    "bidder_name": "YY装备工程股份有限公司",
                    "legal_rep_name": "张三",
                    "sign_date": "2026-11-20",
                },
                "text": "致 XX矿业集团有限公司:我方自愿参加…(全文无占位符无禁用词)",
                "fixed_text": "本投标函即为招标文件的组成部分…",
                "signature": {"seal_anchor": True, "sign_anchor": True},
                "extra_commitments": [
                    {"text": "质保期 24 个月", "clause_id": "decl:1"},
                    {"text": "通用服务承诺", "tag": "通用承诺"},
                ],
                "entity_refs": [],
                "pending_items": [],
            },
            "price_sheet": {
                "rows": [
                    {"name": "设备安装", "qty": 2, "unit": "套", "unit_price": 800000, "amount": 1600000},
                    {"name": "调试服务", "qty": 1, "unit": "项", "unit_price": 400000, "amount": 400000},
                ],
                "detail_total": 2000000,
                "summary_total": 2000000,
                "open_letter_total": 2000000,
                "price_mode": "不含税",
                "tax_rate": 0.13,
                "note": "报价含调试服务,不含运输(无模糊调价表述)",
                "price_adjust_mechanism": True,
                "pending_items": [],
            },
            "response_table": {
                "matrix_star_clause_ids": ["att:1", "decl:1"],
                "rows": [
                    {
                        "clause_id": "att:1",
                        "star": True,
                        "conclusion": "完全响应",
                        "response_text": "提供营业执照正本复印件并加盖公章,满足 3.1 条要求。",
                        "requirement_excerpt": "投标人须提供营业执照副本复印件加盖公章。",
                        "evidence_refs": [{"path": "sec:4", "quote": "营业执照", "page": 3}],
                        "deviation_reason": None,
                        "replacement_plan": None,
                    },
                    {
                        "clause_id": "decl:1",
                        "star": True,
                        "conclusion": "完全响应",
                        "response_text": "承诺投标函内容真实合法有效。",
                        "requirement_excerpt": "投标人须承诺投标文件真实合法。",
                        "evidence_refs": [{"path": "sec:6", "quote": "承诺真实合法", "page": 8}],
                        "deviation_reason": None,
                        "replacement_plan": None,
                    },
                ],
                "pending_items": [],
            },
            "attachment_index": {
                "items": [
                    {"no": "1", "name": "营业执照", "page": 3, "copies": 2, "type_fingerprint": "biz_license", "source": "sec:3", "status": "ready"},
                    {"no": "2", "name": "矿用产品安全标志证书", "page": 5, "copies": 1, "type_fingerprint": "ma_cert", "source": "sec:5", "status": "ready"},
                    {"no": "V1", "name": "商务卷", "page": 1, "copies": 2, "type_fingerprint": "volume", "source": "sec:1", "status": "ready"},
                    {"no": "V2", "name": "技术卷", "page": 1, "copies": 1, "type_fingerprint": "volume", "source": "sec:1", "status": "ready"},
                ],
                "total_pages": 12,
                "body_text": "资质证明详见附件1,安全认证详见附件2。",
                "toc_titles": ["营业执照", "矿用产品安全标志证书"],
                "body_headings": ["营业执照", "矿用产品安全标志证书"],
                "pending_items": [],
            },
        },
        "material": {
            "entities": {
                "ent:license": {"type": "qualification", "name": "营业执照", "fields": {"有效期": "2028-01-01"}},
            },
            "bidder_profile": {"name": "YY装备工程股份有限公司", "legal_rep": "张三"},
            "price_history": [{"project": "同类A", "amount": 2100000}, {"project": "同类B", "amount": 1900000}],
        },
        "pre": {
            "kernel_replay_equal": True,
            "ps_replay_equal": True,
            "bl_fixed_similarity": 0.99,
            "rt_excerpt_overlaps": {"att:1": 0.85, "decl:1": 0.92},
            "rt_cross_field": {"total_amount": {"rt": 2000000, "other": 2000000}},
            "toc_page_estimates": {"1": 3, "2": 5},
        },
    }


def statuses(report) -> dict[str, str]:
    """{assertion_id: status} 快查。"""
    return {r.assertion_id: r.status for r in report.results}


def get_result(report, assertion_id: str):
    for r in report.results:
        if r.assertion_id == assertion_id:
            return r
    raise AssertionError(f"结果缺 {assertion_id}")
