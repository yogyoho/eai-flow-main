"""批二十 M1-i 生成端输入夹具(EAI-CUSTOM 2026-11-13)——与执行端 green_ctx 同
域(B 边矿项目),输入面=tender 抽取快照(扁平点键)+material+人工旋钮;矩阵行由
matrix.assemble_matrix 现算(端到端真链路)。降级负例=变异本夹具(缺单价/缺素材)。"""

from __future__ import annotations

from app.extensions.bid_write.matrix import assemble_matrix

TENDER_FIELDS = {
    "tender.attachment_requirements": [
        {"no": "1", "name": "营业执照", "clause": "3.1", "mandatory": "★", "min_count": 1, "year_span": None, "src": "tender_mandatory"},
        {"no": "2", "name": "矿用产品安全标志证书", "clause": "3.2", "mandatory": "必需", "min_count": 1, "year_span": None, "src": "tender_mandatory"},
    ],
    "tender.required_declarations": [
        "投标人须承诺投标文件真实合法有效",
        "投标人须承诺不发生围标串标行为",
    ],
    "tender.required_sections": ["1 商务卷", "2 资格证明文件", "2.1 营业资质"],
    "tender.volume_specs": [
        {"name": "商务卷", "min_copies": 2},
        {"name": "技术卷", "min_copies": 1},
    ],
    "tender.required_validity_days": 90,
    "tender.bid_deadline": "2026-12-01 09:00",
    "tender.deposit_required": 100000,
    "tender.deposit_forms": ["银行保函"],
    "tender.max_price": 2500000,
    "tender.boq_items": [
        {"id": "1.1", "name": "设备安装", "qty": 2, "unit": "套"},
        {"id": "1.2", "name": "调试服务", "qty": 1, "unit": "项"},
    ],
    "tender.purchaser_name": "华源矿业集团有限公司",
    "tender.project_name": "某矿井智能化建设项目",
    "tender.tender_no": "TB-2026-001",
}

MATERIAL = {
    "entities": {
        "ent:license": {"type": "qualification", "name": "营业执照", "fields": {"有效期": "2028-01-01"}},
    },
    "bidder_profile": {"name": "YY装备工程股份有限公司", "legal_rep": "张三"},
    "price_history": [{"project": "同类A", "amount": 2100000}, {"project": "同类B", "amount": 1900000}],
}

KNOBS = {
    "unit_prices": {"1.1": "800000", "1.2": "400000"},
    "sign_date": "2026-11-20",
    "price_note": "报价含安装调试,不含运输(运费按实结算,另行确认)",
    "general_commitments": [{"text": "质保期 24 个月", "tag": "通用承诺"}],
    "page_estimates": {"1": 3, "2": 5},
}


def closure_inputs(**overrides):
    """金标闭环输入:(tender_fields, matrix_rows, material, knobs)。overrides 深
    替换 knobs 顶层键(如 unit_prices={}, material 缺位传 material 参数)。"""
    knobs = dict(KNOBS)
    knobs.update(overrides)
    return dict(TENDER_FIELDS), assemble_matrix(dict(TENDER_FIELDS)), dict(MATERIAL), knobs
