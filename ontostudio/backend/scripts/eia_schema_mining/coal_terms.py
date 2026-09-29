"""煤炭术语 → spec §4.2 v2 类提名词典。T3 统计的提名依据。"""

# 三层草案 + 三轮参考资料 A-E 组映射；None 值 = 仅术语提名、待归类
COAL_TERMS: dict[str, str | None] = {
    # 资源地质
    "煤层": "coal_seam", "可采煤层": "coal_seam", "煤质": "coal_seam",
    "含水层": "aquifer", "水位降深": "impact_result:drawdown", "富水性": "aquifer",
    "覆岩": "stratigraphic_unit", "导水裂缝带": "impact_result:water_conducting_zone",
    "冒落带": "stratigraphic_unit", "弯曲带": "stratigraphic_unit",
    "断层": "fault", "导水断层": "fault", "采空区": "goaf",
    "井田": "mine_field", "矿区": "mine_field", "矿区总体规划": "planning_scheme",
    # 开采工程
    "采区": "mining_district", "首采区": "mining_district", "工作面": "working_face",
    "采煤方法": "mining_method", "综采": "mining_method", "放顶煤": "mining_method",
    "充填开采": "mining_method", "顶板管理": None, "开拓方式": None,
    "工业场地": "engineering_site", "风井场地": "engineering_site", "排土场": "engineering_site",
    "矸石场": "engineering_site", "铁路专用线": "engineering_site",
    "选煤厂": "coal_prep_plant", "重介": None, "跳汰": None,
    # 排放骨架
    "排放口": "emission_point", "排污口": "emission_point", "排放去向": "receiving_medium",
    "矸石": "waste_stream", "危险废物": "waste_stream", "矿井涌水量": None,
    # 影响结果
    "地表沉陷": "impact_result:subsidence", "最大下沉": "impact_result:subsidence",
    "下沉值": "impact_result:subsidence", "水平变形": "impact_result:subsidence",
    "岩移观测": None, "保水开采": None,
    # 规划环评
    "规划环评": "planning_scheme", "三线一单": "regulation_clause", "承载力": "carrying_capacity",
    "回顾性评价": "retrospective_problem", "规划调整": "planning_change", "重大变动": "planning_change",
    # 约束/时效
    "GB 20426": "standard_threshold", "GB 21522": "standard_threshold",
    "GB 8978": "standard_threshold", "GB 12348": "standard_threshold",
    "HJ 619": "regulation_clause", "HJ 463": "regulation_clause",
    # 素材
    "类比": "analogy_case", "同类矿山": "analogy_case", "措施投资": "measure_spec",
    "去除效率": "measure_spec", "处理工艺": "measure_spec",
}

# 报告体裁关键词（按文件名归类 report_type；顺序即优先级——规划/后评价优先于项目环评兜底词）
REPORT_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "planning_eia": ("规划环评", "总体规划", "规划环境影响"),
    "post_assessment": ("后评价", "环境影响后评价"),
    "project_eia": ("环境影响报告书", "改扩建", "矿井及选煤厂"),
}
