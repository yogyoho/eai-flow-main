"""内置 seed 定位规则库(源真相)。

backend/app/extensions/contract_price/seed_defaults.py 的默认注入与本文件保持同步
(同 models.py 的双份镜像约定)。锚点为归一化子串——归一化规则见
table_classifier._norm_header(去内部空白/去（）括注/全角转半角)(Task 2 新增)。
v1 锚点草案,以 7 样例验收运行实测为准(设计文档 §5)。
"""

from __future__ import annotations

_UNTAXED_EXCLUDE = {"price_unit": ["不含税"]}

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
        "exclude": _UNTAXED_EXCLUDE,
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
        "exclude": _UNTAXED_EXCLUDE,
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
        "exclude": _UNTAXED_EXCLUDE,
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
        "exclude": _UNTAXED_EXCLUDE,
        "source": "样例:钢筋补充协议-需盖章11",
    },
]


def _str_list(v: object) -> list[str]:
    """列表字段类型守卫: 非 list → [];list 内只留标量(str/int/float),字符串化去空白。
    挡住 UI 保存的任意 JSON(如 "price_unit": 3 或 "name": "品名")变成崩溃或逐字符垃圾锚点。"""
    if not isinstance(v, list):
        return []
    return [str(t).strip() for t in v if isinstance(t, (str, int, float)) and str(t).strip()]


def normalize_seeds(raw: object) -> list[dict]:
    """清洗外部输入的 seed 列表: 丢非 dict/缺 id/不满足确认条件最低要求的条目,
    补全缺失键,重复 id 保留第一条。UI 保存的任意 JSON 都不会让管线拿到坏 seed。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for s in raw:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "").strip()
        cols = s.get("columns") if isinstance(s.get("columns"), dict) else {}
        name = _str_list(cols.get("name"))
        price_unit = _str_list(cols.get("price_unit"))
        price_total = _str_list(cols.get("price_total"))
        if not sid or not name or not (price_unit or price_total) or sid in seen:
            continue
        seen.add(sid)
        excl = s.get("exclude") if isinstance(s.get("exclude"), dict) else {}
        out.append(
            {
                "id": sid,
                "display_name": str(s.get("display_name") or sid).strip(),
                "title_keywords": _str_list(s.get("title_keywords")),
                "columns": {
                    "name": name,
                    "spec": _str_list(cols.get("spec")),
                    "qty": _str_list(cols.get("qty")),
                    "unit": _str_list(cols.get("unit")),
                    "price_unit": price_unit,
                    "price_total": price_total,
                    "price_untaxed": _str_list(cols.get("price_untaxed")),
                },
                "exclude": {str(k): _str_list(v) for k, v in excl.items()},
                "source": str(s["source"]) if s.get("source") else None,
            }
        )
    return out
