"""合同元数据提取修复(2026-09-21) — 7 档真值 fixture 全量仿真。

用例全部取自容器内 OCR 缓存取证(.wolf/tmp/meta_fix/forensic1~3, 2026-09-21),
期望值=任务定案真值表。覆盖六字段:
  (project_name, project_location, contract_no, supplier, sign_date, project_no)

修复点:
- supplier: 标签族=乙方/卖方/分包人/供方单位/卖方单位…;值守卫(标签词拒收+
  公司字样甄别+（或/以下简称"X"）尾缀剥离);表格 [标签]→右/下邻格兜底。
- project_name: 同行 + 跨行拼接(续行不含标签词,闭合尾缀即停,上限80字);
  表格 cell 兜底(标签格冒号值/右邻/下邻,内部空白折叠);完整度优先排序
  (项目经理部尾缀者胜——jzgs 甲方格完整名 vs 项目全称格缺尾缀);
  甲方锚兜底(值须以 项目经理部/项目部 收尾,防印章文本混入)。
- project_no 新字段: 同行 '项目编号：' + cell 同格冒号/邻格兜底,代码形态门。
- sign_date: 盖章/甲方：/乙方： 签名区 ±3 行窗口内的已填 年月日 形态
  (容忍手写下划线 '2025_年12月_2日');找不到→诚实 NULL。
- contract_no: 中文尾段(-补01)保留 + 尾连字符剥离 + [合同编号]独立格→右邻兜底。
"""

import pytest

from scripts.project_fields import (
    extract_project_fields,
    find_contract_from_tables,
)


class _T:
    """Minimal TableExtract stand-in (only .rows/.page_no are read)."""

    def __init__(self, rows, page_no=1):
        self.rows = rows
        self.page_no = page_no
        self.table_idx = 0


# ---------------------------------------------------------------- 桂北(1d433138)
GUIBEI_P1 = (
    "合同协议书\n"
    "（房建工程（桂北数据中心））\n"
    "合同编号：101448206-1GS-GZ09-0105-2025-0021\n"
    "承包人：中交三公局第一工程有限公司桂林-恭城一贺州公路（桂林至钟山段）\n"
    "No9合同段工程项目经理部（以下简称“甲方”）\n"
    "分包人：河北润奥佳建筑劳务分包有限公司（以下简称“乙方”）\n"
    "一、分包工程概况\n"
    "工程名称：房建工程（桂北数据中心）\n"
    "工程地点：广西桂林市临桂区。\n"
)
GUIBEI_P3 = (
    "六、合同生效与终止\n"
    "本合同自双方法定代表人或委托代理人签字盖章后生效，双方权利和义务\n"
    "履行完毕后终止。\n"
    "七、其他\n"
    "合同订立时间：2025_年12月_2日。\n"
    "合同订立地点：_桂钟9标项目部。\n"
    "本合同一式_四_份，甲方执三份，乙方执_二份。\n"
    "甲方：\n"
    "乙方：（盖\n"
    "法定代表人\n"
)


def test_guibei_full_truth():
    f = extract_project_fields({1: GUIBEI_P1, 3: GUIBEI_P3})
    assert f == (
        "房建工程（桂北数据中心）",
        "广西桂林市临桂区",
        "101448206-1GS-GZ09-0105-2025-0021",
        "河北润奥佳建筑劳务分包有限公司",
        "2025-12-02",
        None,
    )


# ---------------------------------------------------------------- JZGS(f28c9d26)
JZGS_P1 = (
    "II类合同审批单\n物资采购合同（钢材）\nJZGS-JS-IC-CL-01-2021\n合同名称\n合同编号\n"
    "中交第三公路工程局有限公司IC集\n175448755.00元\n所属项目\n预估总价\n成电路研创园项目\n"
    "中交第三公路工程局有限公\n代理人及\n王园园：13811178792\n甲方\n司IC集成电路研创园项目经\n联系电话\n理部\n"
    "中国交通物资有限公司\n代理人及\n周连营，13910061516\n合同当事人\n乙方\n联系电话\n"
)
JZGS_TABLES = [
    _T([
        ["II类合同审批单", "", "", ""],
        ["合同名称", "物资采购合同（钢材）", "合同编号", "JZGS-JS-IC-CL-01-2021"],
        ["所属项目", "中交第三公路工程局有限公司IC集 成电路研创园项目", "", "175448755.00元 预估总价"],
        ["合同当事人", "甲方 理部", "中交第三公路工程局有限公 司IC集成电路研创园项目经",
         "代理人及 王园园，13811178792 联系电话"],
        ["", "乙方", "中国交通物资有限公司", "代理人及 周连营，13910061516 联系电话"],
        ["", "丙方 II类合同", "", "代理人及 联系电话"],
    ], page_no=1),
    _T([
        ["合同名称", "物资采购合同 (钢材)", "", "", "局审批编号", "局-建-IC-153- 2021", ""],
        ["项目全称", "中交第三公路工程局有限公司IC集 成电路研创园项目", "", "", "合同编号",
         "JZGS-JS-IC-CL -01-2021", ""],
        ["合同当事人", "甲方", "中交第三公路工程局有限公司IC集成电路研创园项目经 理部", "", "", "", ""],
        ["", "", "代理人", "王园园", "联系电话", "13811178792", ""],
        ["", "", "中国交通物资有限公司 乙方 周连营", "", "", "", ""],
    ], page_no=3),
]


def test_jzgs_full_truth():
    """带标签源两级优先: [项目全称]格真值(不带经理部尾缀)胜过 [甲方]格部门全名。"""
    f = extract_project_fields({1: JZGS_P1}, JZGS_TABLES)
    assert f == (
        "中交第三公路工程局有限公司IC集成电路研创园项目",
        None,
        "JZGS-JS-IC-CL-01-2021",
        "中国交通物资有限公司",
        None,
        None,
    )


def test_jzgs_supplier_not_lianxidianhua():
    """回归: 旧逻辑把 split-line 乙方→下一行'联系电话'当供应商(错值入库)。"""
    f = extract_project_fields({1: JZGS_P1}, JZGS_TABLES)
    assert f[3] == "中国交通物资有限公司"
    assert f[3] != "联系电话"


def test_jzgs_contract_from_label_cell_right_neighbor():
    """文本路无冒号合同编号 → [合同编号]独立格右邻 兜底;合并格('局审批编号 合同编号')不参与。"""
    assert find_contract_from_tables(JZGS_TABLES) == "JZGS-JS-IC-CL-01-2021"
    merged_only = [_T([
        ["合同名称", "物资采购合同 (砂石料)", "", "", "局审批编号 合同编号", "2-YCDD-13-201", ""],
        ["项目全称", "某项目经理部", "", "", "", "2GS-YCXM-CL-C G-024-2019", ""],
    ], page_no=1)]
    # 合并格右邻的 2-YCDD-13-201 是局审批流水号,绝不许被当合同编号
    assert find_contract_from_tables(merged_only) is None


def test_contract_neighbor_cell_normalizes_inner_whitespace():
    tables = [_T([["合同编号", "JZGS-JS-IC-CL -01-2021"]], page_no=3)]
    assert find_contract_from_tables(tables) == "JZGS-JS-IC-CL-01-2021"


# ---------------------------------------------------------------- 补充协议(03e28c4c)
BUDX_P1 = (
    "物资采购合同补充协议\n"
    "招标（或竞价、询价）编号：FA00000377762\n"
    "合同编号：ZCB-HEB-0201-2025-0353-补01\n"
    "签订地点：_黑龙江哈尔滨香坊区哈成路263号\n"
    "签订日期：\n年月\n日\n"
    "买方：中交第三公路工程局有限公司（或简称“甲方”）\n"
    "项目名称：中交第三公路工程局有限公司哈尔滨市香区高端电气装备智能\n"
    "制造基地一期项目经理部\n"
    "卖方：中国交通物资有限公司（或简称“乙方”）\n"
    "买卖双方于2025年10月_13日签订《钢筋采购合同》（以下简称“原合\n"
    "同”），合同编号：ZCB-HEB-0201-2025-0353。现因_工程量调整，经双方\n"
)


def test_budx_full_truth():
    f = extract_project_fields({1: BUDX_P1})
    assert f == (
        "中交第三公路工程局有限公司哈尔滨市香区高端电气装备智能制造基地一期项目经理部",
        None,
        "ZCB-HEB-0201-2025-0353-补01",
        "中国交通物资有限公司",
        None,
        None,
    )


def test_contract_number_keeps_chinese_tail_segment():
    """-补01 的'补'是中文,旧 [A-Za-z0-9-]+ 把它吞成尾连字符截断。"""
    assert extract_project_fields({1: "合同编号：ZCB-HEB-0201-2025-0353-补01"})[2] == \
        "ZCB-HEB-0201-2025-0353-补01"
    # 正文引用原合同号: 无中文尾段 → 照常;尾连字符剥离
    assert extract_project_fields({1: "合同编号：ZCB-HEB-0201-2025-0353。现因调整"})[2] == \
        "ZCB-HEB-0201-2025-0353"
    assert extract_project_fields({1: "合同编号：ABC-DEF-0353-\n下一行"})[2] == "ABC-DEF-0353"
    # CJK 尾段只认『-中文+可选数字』结尾段;中断形态截到该段为止(语料无此形态,定义行为)
    assert extract_project_fields({1: "合同编号：ZCB-HEB-补-01-2025"})[2] == "ZCB-HEB-补"


def test_budx_sign_date_stays_honest_null():
    """正文 '买卖双方于2025年10月_13日签订' 是原合同日期且附近无签名区锚 → NULL。"""
    assert extract_project_fields({1: BUDX_P1})[4] is None


# ---------------------------------------------------------------- 砂石料(9839d01b)
SHASHI_P1 = (
    "二公司\n物资采购\n中交三局\n合同订立审批单\n物资采购合同 (砂石料)\n2-YCDD-13-201\n合同名称\n局审批编号\n"
    "中交第三公路工程局有限公司宜春大\n2GS-YCXM-CL-C\n项目全称\n合同编号\n道总承包项目经理部\nG-024-2019\n"
    "中交第三公路工程局有限公司宜春大道总承包项目经理\n部\n甲方\n王文聪\n代理人\n联系电话\n18870947777\n"
    "宜春市佳之通贸易有限公司\n合同当事人\n乙方\n易全勇\n代理人\n联系电话\n18007050500\n丙方\n"
)
SHASHI_TABLES = [
    _T([
        ["中父三局", "", "", "", "合同订立审批单", "", ""],
        ["合同名称", "物资采购合同 (砂石料)", "", "", "局审批编号 合同编号", "2-YCDD-13-201", ""],
        ["项目全称", "中交第三公路工程局有限公司宜春大 道总承包项目经理部", "", "", "",
         "2GS-YCXM-CL-C G-024-2019", ""],
        ["合同当事人", "部 甲方", "", "", "", "中交第三公路工程局有限公司宜春大道总承包项目经理", ""],
        ["", "", "代理人", "王文聪", "联系电话", "18870947777", ""],
        ["", "", "宜春市佳之通贸易有限公司", "", "", "", ""],
        ["", "乙方", "易全勇 代理人", "", "联系电话", "18007050500", ""],
        ["", "丙方", "", "", "", "", ""],
    ], page_no=1),
    _T([
        ["项目名称：", "合同备案编亏： 2G3-CL-CG-2019-393 中交第三公路工程局有限公司宜春大道总承包项目经理部"
         " 合同编号：2GS-YCXM-CL-CG-024-2019", "", "", "", "", ""],
        ["", "砂石料采购", "", "项目合同编号", "", "", ""],
        ["合同内容", "", "", "是", "2GS-YCXM-CL-CG-024-2019", "", ""],
        ["供方单位 付款方式", "宜春市佳之通贸易有限公司", "", "项目是否会签 采购方式 线上公开", "", "", ""],
    ], page_no=6),
]


def test_shashi_full_truth():
    f = extract_project_fields({1: SHASHI_P1}, SHASHI_TABLES)
    assert f == (
        "中交第三公路工程局有限公司宜春大道总承包项目经理部",
        None,
        "2GS-YCXM-CL-CG-024-2019",
        "宜春市佳之通贸易有限公司",
        None,
        None,
    )


def test_shashi_supplier_rejects_agent_person():
    """回归: 旧逻辑把乙方邻格个人名'易全勇'当供应商;公司字样甄别必须拒收。"""
    f = extract_project_fields({1: SHASHI_P1}, SHASHI_TABLES)
    assert f[3] == "宜春市佳之通贸易有限公司"
    assert f[3] != "易全勇"


def test_shashi_name_cell_colon_junk_rejected():
    """p6 '项目名称：'格右邻是 '合同备案编亏：…' 混合格——含冒号的拼接残渣必须拒收,
    项目名由 p1 [项目全称]格右邻(带'项目经理部'完整尾缀)胜出。"""
    f = extract_project_fields({1: SHASHI_P1}, SHASHI_TABLES)
    assert f[0] == "中交第三公路工程局有限公司宜春大道总承包项目经理部"
    assert "合同备案" not in (f[0] or "")
    assert "2G3-CL" not in (f[0] or "")


# ---------------------------------------------------------------- 上浦(5b39470d)
SHANGPU_P1 = (
    "材料采购合同评审表\n"
    "项目编号：01116102P20200020000000000P\n"
    "中交三公局第二工程有限公司上浦高速EPC+F\n"
    "合同编号：2GS-SPXM-CL-CG-011-2021\n"
    "合同名称：钢材采购合同\n"
    "合同类型：材料采购\n币种：人民币\n"
    "合同甲方：上浦项目\n甲方代理人及电话：彭芳葵\n13051265111\n"
    "合同乙方：中交天津工贸有限公司\n乙方代理人及电话：黄小军（18624876888）\n"
    "不含税合同金额：1，479，828.57\n税率（%）：13.00\n税金：192,377.32\n含税合同金额：1672205.89\n"
    "签订日期：\n合同期限（月）：\n合同开始日期：2021-07-16\n合同终止日期：\n"
)
SHANGPU_P3 = (
    "中交第三公路工程局有限公司\n物资采购合同会签表\n"
    "项目名称：中交三公局第二工程有限公司上浦高速\n"
    "项目合同编号：2GS-SPXM-CL-CG-011-2021\n"
    "EPC+F总承包合同段项目经理部\n"
    "供方单位全称\n中交天津工贸有限公司\n"
)
SHANGPU_TABLES = [
    _T([
        ["", "材料采购合同评审表", "", ""],
        ["", "项目编号：01116102P20200020000000000P", "项目名称：",
         "中交三公局第二工程有限公司上浦高速EPC+F 总承包合同段项目经理部"],
        ["", "合同编号：2GS-SPXM-CL-CG-011-2021", "合同名称：钢材采购合同", ""],
        ["合同甲方：上浦项目", "", "甲方代理人及电话：彭芳葵", "13051265111"],
        ["", "合同乙方：中交天津工贸有限公司", "乙方代理人及电话：黄小军（18624876888）", ""],
        ["签订日期：", "", "合同期限（月）：", ""],
        ["合同开始口期：2021-07-16", "", "合同终止日期：", ""],
    ], page_no=1),
    _T([["页目名称： 中交三公局第二工程有限公司上浦高 PC+F总承包合同段项目经理部"]], page_no=3),
]


def test_shangpu_full_truth():
    f = extract_project_fields({1: SHANGPU_P1, 3: SHANGPU_P3}, SHANGPU_TABLES)
    assert f == (
        "中交三公局第二工程有限公司上浦高速EPC+F总承包合同段项目经理部",
        None,
        "2GS-SPXM-CL-CG-011-2021",
        "中交天津工贸有限公司",
        None,
        "01116102P20200020000000000P",
    )


def test_shangpu_project_no_text_hit():
    assert extract_project_fields({1: "项目编号：01116102P20200020000000000P"})[5] == \
        "01116102P20200020000000000P"
    # 招标/审批编号不是项目编号
    assert extract_project_fields({1: "招标编号：FA00000377762"})[5] is None
    assert extract_project_fields({1: "局审批编号：2-YCDD-13-201"})[5] is None


def test_shangpu_project_no_cell_fallback_shape_gate():
    """文本 miss → cell 同格冒号兜底;混入中文的粘连值过不了形态门,落到干净格。"""
    tables = [_T([
        ["", "项目编号：01116102P20200020000000000P 中交三公局EPC+F 项目名称", "", ""],
        ["", "项目编号：01116102P20200020000000000P", "项目名称：", "某项目经理部"],
    ], page_no=1)]
    assert extract_project_fields({1: "封面"}, tables)[5] == "01116102P20200020000000000P"
    assert extract_project_fields({1: "封面 无编号"}, None)[5] is None


# ---------------------------------------------------------------- 木饰面(52bce87c)
MUSHI_P1 = (
    "中交三公局黄河三角洲（二）室内装饰项目\n木饰面、石材物资采购合同\n"
    "招标编号：BZGC-2026-032\n合同编号：ZCB-HZZX2ZS-0201-2026-0210\n"
    "签订地点：中交第三公路工程局有限公司黄河三角洲农产品交易服务中心基础设\n"
    "施项目配套服务中心（二）室内装饰装修及室外配套工程室内装饰装修及室外配套工\n"
    "程项目经理部\n签订日期：\n二年月日\n"
    "买方：中交第三公路工程局有限公司（或简称“买方”）\n"
    "项目名称：中交第三公路工程局有限公司黄河三角洲农产品交易服务中心基础设\n"
    "施项目配套服务中心（二）室内装饰装修及室外配套工程室内装饰装修及室外配套工\n"
    "程项目经理部\n"
    "卖方：中交第三公路工程局（西藏）有限公司（或简称“卖方”）\n"
)


def test_mushimian_full_truth():
    f = extract_project_fields({1: MUSHI_P1})
    assert f == (
        "中交第三公路工程局有限公司黄河三角洲农产品交易服务中心基础设施项目配套服务中心"
        "（二）室内装饰装修及室外配套工程室内装饰装修及室外配套工程项目经理部",
        None,
        "ZCB-HZZX2ZS-0201-2026-0210",
        "中交第三公路工程局（西藏）有限公司",
        None,
        None,
    )


# ---------------------------------------------------------------- 钢材签字版(41ddcdd1)
GANGCAI_P1 = (
    "物资采购合同\n"
    "合同编号：503-CHN-PZ-ClG-4-22\n"
    "日期：2021、426\n地点：\n"
    "甲方：中交第三公路工程局有限公司彭州市凤鸣湖饮用水水源地保护区污水\n"
    "治理工程项目经理部\n"
    "彭州市风鸣湖饮\n保护区污水治理工程\n"
    "地址：四川省成都市彭州市龙门山镇宝山村\n委托代表人：钱昌静\n"
    "纳税人识别号：911100007596009847\n电话：18580127012\n传真：\n"
    "开户银行：中国银行彭州支行\n帐号：126669958905\n税号：911100007596009847\n"
    "乙方：成都翔润钢铁商贸有限公司\n"
    "地址：成都市金牛区金府路777号2-1-6号\n法定代表人：李秀杰\n"
)


def test_gangcai_full_truth():
    f = extract_project_fields({1: GANGCAI_P1})
    assert f == (
        "中交第三公路工程局有限公司彭州市凤鸣湖饮用水水源地保护区污水治理工程项目经理部",
        None,
        "503-CHN-PZ-ClG-4-22",
        "成都翔润钢铁商贸有限公司",
        None,
        None,
    )


def test_gangcai_project_name_anchor_skips_seal_fragments():
    """甲方值跨行续行拼到'项目经理部'闭合即停——印章碎片('彭州市风鸣湖饮')不得混入。"""
    f = extract_project_fields({1: GANGCAI_P1})
    assert f[0].endswith("项目经理部")
    assert "风鸣湖饮" not in f[0].replace("彭州市凤鸣湖", "")


def test_gangcai_sign_date_stays_null():
    """'日期：2021、426' 非 年月日 形态 → 签名区窗口也不收,诚实 NULL。"""
    assert extract_project_fields({1: GANGCAI_P1})[4] is None


# ---------------------------------------------------------------- sign_date 窗口单测
def test_sign_date_stamp_window_needs_anchor():
    # 有锚(盖章)且 ±3 行内有已填年月日 → 收
    assert extract_project_fields({1: "双方签字盖章后生效\n合同订立时间：2026年1月2日。"})[4] == "2026-01-02"
    # 有年月日但周围没有签名区锚 → 不收
    assert extract_project_fields({1: "本工程于2024年5月6日开工建设，质量第一。"})[4] is None
    # 距锚超过 ±3 行 → 不收
    assert extract_project_fields(
        {1: "盖章\nL1\nL2\nL3\nL4\n合同订立时间：2025年3月4日"}
    )[4] is None


def test_sign_date_excludes_contract_term_lines():
    pt = {1: "合同甲方：上浦项目\n签订日期：\n合同开始日期：2021-07-16\n合同终止日期：\n甲方：（盖章）"}
    assert extract_project_fields(pt)[4] is None


def test_sign_date_ignores_numeric_approval_timestamps():
    """jzgs 审批意见时间戳([刘爱连2021-05-0110:55])是数字形态,年月日窗口不收。"""
    pt = {1: JZGS_P1 + "\n【同意】\n同意\n[刘爱连2021-05-0110:55]"}
    assert extract_project_fields(pt, JZGS_TABLES)[4] is None


# ---------------------------------------------------------------- supplier 单元
@pytest.mark.parametrize("line,want", [
    ("分包人：河北润奥佳建筑劳务分包有限公司（以下简称“乙方”）", "河北润奥佳建筑劳务分包有限公司"),
    ("卖方：中国交通物资有限公司（或简称“乙方”）", "中国交通物资有限公司"),
    ("卖方：中交第三公路工程局（西藏）有限公司（或简称“卖方”）", "中交第三公路工程局（西藏）有限公司"),
    ("供方单位：宜春市佳之通贸易有限公司", "宜春市佳之通贸易有限公司"),
    ("乙方：桂北建工有限公司", "桂北建工有限公司"),
])
def test_supplier_suffix_strip_forms(line, want):
    assert extract_project_fields({1: line})[3] == want


@pytest.mark.parametrize("line", [
    "乙方：易全勇",          # 个人名(无公司字样)
    "乙方：李秀杰",
    "乙方\n联系电话",        # F2b 标签邻行
    "乙方：联系电话",
    "供方：易全勇",          # 旧自检样例(砂石料错值来源)——甄别规则后必须拒收
])
def test_supplier_rejects_person_and_label_fragments(line):
    assert extract_project_fields({1: line})[3] is None


def test_supplier_cell_neighbor_jzgs():
    tables = [_T([
        ["合同当事人", "甲方 理部", "中交第三公路工程局有限公司", "代理人及 联系电话"],
        ["", "乙方", "中国交通物资有限公司", "代理人及 周连营，13910061516 联系电话"],
    ], page_no=1)]
    assert extract_project_fields({1: "无标签封面"}, tables)[3] == "中国交通物资有限公司"


def test_supplier_merged_label_cell_shashi():
    """'供方单位 付款方式' 合并标签格 startswith 命中 → 右邻公司值;个人名邻格先被拒。"""
    tables = [_T([
        ["", "乙方", "易全勇 代理人", "", "联系电话", "18007050500", ""],
        ["", "丙方", "", "", "", "", ""],
        ["供方单位 付款方式", "宜春市佳之通贸易有限公司", "", "", "", "", ""],
    ], page_no=6)]
    assert extract_project_fields({1: ""}, tables)[3] == "宜春市佳之通贸易有限公司"


# ---------------------------------------------------------------- project_name 单元
def test_name_crossline_join_closes_on_project_dept():
    pt = {1: "项目名称：中交第三公路工程局有限公司哈尔滨市香区高端电气装备智能\n"
             "制造基地一期项目经理部\n卖方：某公司"}
    assert extract_project_fields(pt)[0] == \
        "中交第三公路工程局有限公司哈尔滨市香区高端电气装备智能制造基地一期项目经理部"


def test_name_splitline_join_still_guards_labels():
    # F2b 保持: 标签独行下一行仍是标签 → 拒;真值行 → 拼接
    assert extract_project_fields({1: "项目名称\n局审批编号"})[0] is None
    assert extract_project_fields({1: "项目名称\n桂北数据中心"})[0] == "桂北数据中心"


def test_name_80_char_cap_no_runaway_join():
    long_tail = "".join(f"第{i}段无标签" for i in range(30))  # 单行超长续体
    pt = {1: "项目名称：某工程\n" + long_tail}
    val = extract_project_fields(pt)[0]
    assert val is not None and len(val) <= 80


def test_name_labeled_source_priority_over_owner_anchor():
    """两级优先(2026-09-21 复审修正): 显式标签源存在时,甲方锚/尾缀排序不得越级——
    jzgs [项目全称]格(不带经理部尾缀)胜过 [甲方]格部门全名;带标签源内部取最完整者。"""
    f = extract_project_fields({1: JZGS_P1}, JZGS_TABLES)
    assert f[0] == "中交第三公路工程局有限公司IC集成电路研创园项目"
    # 上浦: 带标签源内部取最完整者——文本截断名让位 [项目名称]格全名
    f2 = extract_project_fields({1: SHANGPU_P1, 3: SHANGPU_P3}, SHANGPU_TABLES)
    assert f2[0] == "中交三公局第二工程有限公司上浦高速EPC+F总承包合同段项目经理部"


def test_name_contract_label_demoted_to_fallback():
    """合同名称标签降级为回退: 仅当无 项目名称/工程名称/项目全称 源时才用。"""
    # 无主标签 → 合同名称值可用(旧行为保持)
    assert extract_project_fields({1: "合同名称：某合同"})[0] == "某合同"
    # 有 项目名称 源 → 合同名称不参与竞争
    assert extract_project_fields({1: "项目名称：某工程\n合同名称：钢材采购合同"})[0] == "某工程"


def test_name_owner_anchor_fallback_keeps_gangcai():
    """回退路径不回归: 签字版无任何带标签源 → 甲方锚兜底照常。"""
    f = extract_project_fields({1: GANGCAI_P1})
    assert f[0] == "中交第三公路工程局有限公司彭州市凤鸣湖饮用水水源地保护区污水治理工程项目经理部"


def test_name_ignores_goods_schedule_label_headers():
    """guibei 回归(2026-09-21 用户复测): 工程量清单列头格 [项目名称](右邻='单位',
    下邻=品名如七氟丙烷灭火装置)是货物清单形态,不许冒充项目名——cell 源仅取
    表单形态(同格冒号/右邻)且限前 6 页;项目名仍取文本路 工程名称 值。"""
    schedule = [
        _T([
            ["项目名称", "单位", "数量", "单价"],
            ["七氟丙烷无管网灭火装置GQQ120/2.5-PAVLN", "套", "2", "38000"],
        ], page_no=36),
    ]
    f = extract_project_fields({1: GUIBEI_P1}, schedule)
    assert f[0] == "房建工程（桂北数据中心）"
    # 即使清单在前 6 页内,列头下邻格(品名)也不许成为候选
    early = [
        _T([
            ["项目名称", "单位", "数量"],
            ["七氟丙烷无管网灭火装置GQQ120/2.5-PAVLN", "套", "2"],
        ], page_no=2),
    ]
    f2 = extract_project_fields({1: "无标签封面"}, early)
    assert f2[0] != "七氟丙烷无管网灭火装置GQQ120/2.5-PAVLN"


def test_name_owner_anchor_requires_project_dept_suffix():
    # '合同甲方：上浦项目' 不以 项目经理部/项目部 收尾 → 不作项目名
    assert extract_project_fields({1: SHANGPU_P1, 3: SHANGPU_P3}, SHANGPU_TABLES)[0].endswith("项目经理部")
    assert extract_project_fields({1: "合同甲方：上浦项目\n nothing"})[0] is None
