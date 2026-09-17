"""内置 seed 定位规则库(源真相)。

backend/app/extensions/contract_price/seed_defaults.py 的默认注入与本文件保持同步
(同 models.py 的双份镜像约定)。锚点为归一化子串——归一化规则见
table_classifier._norm_header(去内部空白/去（）括注/全角转半角)。
v1 锚点草案,以 7 样例验收运行实测为准(设计文档 §5)。
"""

from __future__ import annotations

_GCL_EXCLUDE = {"price_unit": ["不含税"]}

DEFAULT_TABLE_SEEDS: list[dict] = [
    {
        "id": "gcl-qd",
        "display_name": "工程量清单计价表",
        "title_keywords": ["工程量清单", "清单计价"],
        "columns": {
            "name": ["项目名称", "品名", "物资名称"],
            "spec": ["规格型号", "参数"],
            "qty": ["工程量", "数量"],
            "unit": ["单位", "计量单位"],
            "price_unit": ["含税单价"],
            "price_total": ["含税合价"],
            "price_untaxed": ["不含税单价"],
        },
        "exclude": _GCL_EXCLUDE,
        "source": "样例:房建工程（桂北数据中心）",
    },
    {
        "id": "jzgs-gc",
        "display_name": "钢材物资采购清单(JZGS)",
        "title_keywords": ["物资采购", "钢材"],
        "columns": {
            "name": ["品名"],
            "spec": ["规格型号"],
            "qty": ["数量"],
            "unit": ["单位"],
            "price_unit": ["综合单价"],
            "price_total": ["总金额"],
            "price_untaxed": [],
        },
        "exclude": {"price_unit": ["不含税"]},
        "source": "样例:JZGS-JS-IC-CL-01-2021物资采购合同（钢材）",
    },
    {
        "id": "sp-gj",
        "display_name": "钢筋供货价格表(上浦)",
        "title_keywords": ["钢筋", "供货"],
        "columns": {
            "name": ["物资名称"],
            "spec": ["材质"],
            "qty": ["暂定数量", "数量"],
            "unit": ["计量单位", "单位"],
            "price_unit": ["含税单价"],
            "price_total": ["含税总价"],
            "price_untaxed": ["不含税单价"],
        },
        "exclude": _GCL_EXCLUDE,
        "source": "样例:上浦项目-钢筋采购合同",
    },
    {
        "id": "msm-sc",
        "display_name": "木饰面石材物资清单",
        "title_keywords": ["木饰面", "石材", "物资"],
        "columns": {
            "name": ["物资名称", "材质", "品名"],
            "spec": ["规格", "材质规格"],
            "qty": ["暂定数量", "数量"],
            "unit": ["计量单位", "单位"],
            "price_unit": ["综合单价", "含税单价"],
            "price_total": ["含税总价"],
            "price_untaxed": ["不含税单价"],
        },
        "exclude": _GCL_EXCLUDE,
        "source": "样例:木饰面、石材物资采购合同",
    },
    {
        "id": "gc-qzb",
        "display_name": "钢材采购明细(签字版)",
        "title_keywords": ["钢材", "采购"],
        "columns": {
            "name": ["品名"],
            "spec": ["规格型号"],
            "qty": ["数量"],
            "unit": ["单位"],
            "price_unit": ["含税单价"],
            "price_total": ["含税合价"],
            "price_untaxed": ["不含税单价"],
        },
        "exclude": {"price_unit": ["不含税"], "price_total": ["不含税"]},
        "source": "样例:钢材采购合同-签字版",
    },
    {
        "id": "bcxy-tj",
        "display_name": "补充协议价格调整表",
        "title_keywords": ["补充协议", "价格调整", "调价"],
        "columns": {
            "name": ["物资名称"],
            "spec": ["材质规格"],
            "qty": ["调整数量", "数量"],
            "unit": ["计量单位", "单位"],
            "price_unit": ["综合单价", "调整后单价"],
            "price_total": ["调整后合价", "总金额", "含税总价"],
            "price_untaxed": [],
        },
        "exclude": _GCL_EXCLUDE,
        "source": "样例:钢筋补充协议-需盖章11",
    },
]


def normalize_seeds(raw: object) -> list[dict]:
    """清洗外部输入的 seed 列表: 丢非 dict/缺 id/不满足确认条件最低要求的条目,
    补全缺失键。UI 保存的任意 JSON 都不会让管线拿到坏 seed。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        cols = s.get("columns") if isinstance(s.get("columns"), dict) else {}
        name = [str(t) for t in cols.get("name") or [] if str(t).strip()]
        price_unit = [str(t) for t in cols.get("price_unit") or [] if str(t).strip()]
        price_total = [str(t) for t in cols.get("price_total") or [] if str(t).strip()]
        if not str(s.get("id") or "").strip() or not name or not (price_unit or price_total):
            continue
        out.append(
            {
                "id": str(s["id"]).strip(),
                "display_name": str(s.get("display_name") or s["id"]).strip(),
                "title_keywords": [str(t) for t in s.get("title_keywords") or [] if str(t).strip()],
                "columns": {
                    "name": name,
                    "spec": [str(t) for t in cols.get("spec") or [] if str(t).strip()],
                    "qty": [str(t) for t in cols.get("qty") or [] if str(t).strip()],
                    "unit": [str(t) for t in cols.get("unit") or [] if str(t).strip()],
                    "price_unit": price_unit,
                    "price_total": price_total,
                    "price_untaxed": [str(t) for t in cols.get("price_untaxed") or [] if str(t).strip()],
                },
                "exclude": {
                    str(k): [str(t) for t in v if str(t).strip()]
                    for k, v in (s.get("exclude") or {}).items()
                    if isinstance(v, list)
                },
                "source": str(s["source"]) if s.get("source") else None,
            }
        )
    return out
