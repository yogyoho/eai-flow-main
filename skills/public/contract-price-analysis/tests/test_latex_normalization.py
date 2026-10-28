"""BUG-D 生产修复回归(2026-10-29 木饰面/钢筋补充协议 取证)。

PaddleOCR-VL 按「数学公式」序列化孤立符号(Φ→\\Phi、×→\\times,有时裹行内
定界符 \\( \\)),相邻页输出形态不稳定(temperature=0 压不住解码非确定性)。
中间无任何环节拦截,cell → TableExtract.rows → 分项抽取 → cpa_items.
spec_model 原样透传落库(全库 \\Phi 20 次、\\times 2 次,21 条受影响)。

换 "OCR:" prompt 保符号丢表格结构(0 张表,分项提取全军覆没)——必须保留
"Table Recognition:" 保结构,下游 normalize_latex_math 归一化:
- 活体路径 parse_document_openai_vision 两分支汇合处逐 cell(同时覆盖
  TableExtract 与 page_texts 重建);
- 缓存路径 from_cache 重建 rows(旧缓存仍带脏值,否则缓存命中重解析会冲掉
  数据库回填成果——本仓加固,生产版未含)。
"""

import pytest

from scripts.document_parser import from_cache, normalize_latex_math


class TestRealDirtyValues:
    """生产真实脏值(钢筋补充协议 p2/p3、木饰面合同货物清单)。"""

    @pytest.mark.parametrize(
        ("src", "want"),
        [
            ("HRB400E \\Phi 8mm", "HRB400E Φ 8mm"),
            ("HRB400E \\(\\Phi\\) 20mm", "HRB400E Φ 20mm"),
            ("强电线槽 \\(100 \\times 100 \\times 1.2\\)", "强电线槽 100 × 100 × 1.2"),
            ("HPB300 \\Phi 6mm", "HPB300 Φ 6mm"),
            ("抗拉强度 \\geq 400MPa", "抗拉强度 ≥ 400MPa"),
            ("偏差 \\pm 0.5mm", "偏差 ± 0.5mm"),
            ("\\Omega 50\\Omega", "Ω 50Ω"),
            ("\\Phi 25m^{2}", "Φ 25m²"),
            ("角度 45^{\\circ}", "角度 45°"),
        ],
    )
    def test_normalized(self, src, want):
        assert normalize_latex_math(src) == want


class TestNoOpInvariants:
    """常规文本逐字节不变(无误伤)。"""

    @pytest.mark.parametrize(
        "src",
        [
            "ZCB-HZZX2ZS-0201-2026-0210",
            "1,234,567.89",
            "2026年9月10日",
            "HRB400E Φ 8mm",  # 已归一形态(幂等前置)
            "强电线槽 100 × 100 × 1.2",
            "(常规括号)文本",
            "$500",  # 裸 $ 不碰(货币金额)
            "纯中文无符号",
            "",
        ],
    )
    def test_untouched(self, src):
        assert normalize_latex_math(src) == src


class TestSafetyRedLines:
    """设计红线(生产 38 项回归固化)。"""

    def test_prefix_word_not_corrupted(self):
        # \\Philips 不得被误换成 Φilips
        assert normalize_latex_math("\\Philips 电动工具") == "\\Philips 电动工具"

    def test_unknown_command_preserved(self):
        # 未知命令原样保留:宁可不清理也不破坏文本
        assert normalize_latex_math("\\foo 12") == "\\foo 12"

    def test_escaped_dollar_keeps_dollar(self):
        assert normalize_latex_math("\\$500") == "$500"

    def test_bare_dollar_never_touched(self):
        assert "500" in normalize_latex_math("报价 $500 元")

    def test_vertical_whitespace_preserved(self):
        # 第 6 步只压 [ \t],不动 \n——page_texts 靠换行切行喂元数据正则
        assert normalize_latex_math("a\\times b\nc  d") == "a× b\nc d"

    def test_idempotent(
        self,
    ):
        for src in [
            "HRB400E \\Phi 8mm",
            "强电线槽 \\(100 \\times 100\\)",
            "\\Omega 50\\Omega",
        ]:
            once = normalize_latex_math(src)
            assert normalize_latex_math(once) == once


class TestFromCacheNormalization:
    """旧 OCR 缓存重建时归一化(本仓加固;防缓存命中重解析冲掉 DB 回填)。"""

    def test_dirty_rows_normalized_on_rebuild(self):
        tables, page_texts, _ = from_cache(
            {
                "tables": [
                    {
                        "page_no": 2,
                        "table_idx": 0,
                        "rows": [["HPB300 \\Phi 6mm", "100 \\times 100"]],
                    },
                ],
            }
        )
        assert tables[0].rows == [["HPB300 Φ 6mm", "100 × 100"]]
        # page_texts 从归一化后的 rows 拼行——元数据正则读到的也是干净值
        assert page_texts[2] == "HPB300 Φ 6mm\n100 × 100"

    def test_clean_cache_untouched(self):
        rows = [["品名", "规格"], ["钢筋", "HRB400E Φ 20mm"]]
        tables, page_texts, _ = from_cache(
            {
                "tables": [{"page_no": 1, "table_idx": 0, "rows": rows}],
            }
        )
        assert tables[0].rows == rows
        assert "\\" not in page_texts[1]

    def test_stored_page_texts_not_overwritten(self):
        # 已存 page_texts 的页(原生文本层)不覆盖——from_cache 既有语义
        tables, page_texts, _ = from_cache(
            {
                "tables": [{"page_no": 3, "table_idx": 0, "rows": [["\\Phi 脏值"]]}],
                "page_texts": {"3": "原生文本层干净内容"},
            }
        )
        assert page_texts[3] == "原生文本层干净内容"
