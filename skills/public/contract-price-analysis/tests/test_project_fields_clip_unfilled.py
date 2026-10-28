"""BUG-B/BUG-C 生产修复回归(2026-10-29 木饰面、石材物资采购合同 取证)。

BUG-B project_name 抽不出(四层根因的最后一层): PaddleOCR-VL 对首页整页纯
文字只输出一个 cell,parse 拼行后首页 400 余字无换行 → _LINE[lbl] 的
[^\n\r]+ 把「项目名称：」的值吞到行尾(带着「卖方：…」的冒号),_valid_name
以「含冒号=未拆标签残渣」拒收 → project_name=None → cli 三态判定落
needs_review → 前端「同步分项表」按钮(只认 parsed)永不出现。
修复: _clip_at_next_label 把值裁剪到下一个「已知标签+分隔符」之前,只用于
_find_name 的 primary 路径(_iter_same_line 被 _find_supplier 复用,不得
全局裁剪——生产影子验证:全局裁剪把 supplier 裁成 46 字污染值)。

BUG-C sign_date 误抽: 首页「签订日期：____年____月____日」显式未填,占位符
本就不匹配 _DATE_RE(年月日须实际数字);2016-09-19 误值来自 _find_date 第三
层兜底 _BARE_DATE_LINE 把附件证照/票据页的裸「日期:2016.9.19」抓走。
修复: _UNFILLED_DATE_LABEL 守卫——显式未填 ⇒ 诚实 None(人工补填);盖章区
手写日期走独立 _find_stamp_date(物证),仍能兜住。
"""

from scripts.project_fields import (
    _clip_at_next_label,
    extract_project_fields,
)


class TestClipAtNextLabel:
    """BUG-B: 无换行单 cell 形态的项目名裁剪。"""

    def test_single_cell_no_newline_name_clipped(self):
        """整页一行: 项目名值吞进 卖方/联系电话/工程地点 整段 → 裁剪出真名。"""
        blob = (
            "项目名称：中交三公局黄河三角洲（二）室内装饰项目"
            "卖方：某建设有限公司联系电话：13800000000工程地点：某市"
        )
        name, loc, contract, supplier, sign_date, project_no = extract_project_fields({"1": blob})
        assert name == "中交三公局黄河三角洲（二）室内装饰项目"
        assert loc == "某市"
        # supplier 走不裁剪路径: 吞进联系电话(污染词)被 _valid_supplier 拒收
        assert supplier is None

    def test_multi_line_contract_unaffected(self):
        """正常多行合同: 裁剪是 no-op,既有抽取不受影响。"""
        blob = "项目名称：桂北数据中心专业分包工程\n工程地点：桂北市"
        name, loc, *_ = extract_project_fields({"1": blob})
        assert name == "桂北数据中心专业分包工程"
        assert loc == "桂北市"

    def test_clip_function_cuts_at_next_label(self):
        assert _clip_at_next_label("某某项目卖方：某公司") == "某某项目"
        assert _clip_at_next_label("某某项目") == "某某项目"
        assert _clip_at_next_label("") == ""
        # 全角冒号/顿号分隔同样命中
        assert _clip_at_next_label("某某项目工程地点：某市") == "某某项目"

    def test_long_wrapped_name_still_joins(self):
        """值在行内被裁剪后,跨行拼接(_join_from)仍生效。"""
        blob = "项目名称：某智能装备卖方：某公司\n制造基地项目经理部"
        name, *_ = extract_project_fields({"1": blob})
        assert name == "某智能装备制造基地项目经理部"


class TestUnfilledDateGuard:
    """BUG-C: 显式未填的签订日期 ⇒ 不做全文 scavenging。"""

    def test_unfilled_label_ignores_bare_dates_elsewhere(self):
        """未填标签 + 证照/票据页裸日期 → 诚实 None(修复前误抽 2016-09-19)。"""
        blob = "签订日期：____年____月____日\n日期:2016.9.19"
        _, _, _, _, sign_date, _ = extract_project_fields({"1": blob})
        assert sign_date is None

    def test_unfilled_label_but_stamp_date_rescues(self):
        """未填印刷日期但盖章区(甲方：锚 ±3 行)有手写日期 → 盖章窗口仍兜住。"""
        blob = "签订日期：____年____月____日\n甲方：某工程有限公司\n2026年9月10日"
        _, _, _, _, sign_date, _ = extract_project_fields({"1": blob})
        assert sign_date == "2026-09-10"

    def test_filled_date_unaffected(self):
        """已填日期不触发守卫,标签锚定正常抽取。"""
        blob = "签订日期：2025年6月18日"
        _, _, _, _, sign_date, _ = extract_project_fields({"1": blob})
        assert sign_date == "2025-06-18"

    def test_fullwidth_underscores_also_trigger(self):
        """全角下划线/签署时间 变体同样识别为未填。"""
        blob = "签署时间：＿＿＿年＿＿月＿＿日\n日期:2016.9.19"
        _, _, _, _, sign_date, _ = extract_project_fields({"1": blob})
        assert sign_date is None
