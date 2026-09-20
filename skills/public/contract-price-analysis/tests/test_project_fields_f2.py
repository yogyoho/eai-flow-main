"""F2 元数据兜底: 表格 cell 合同编号(方案A) + project_name split-line 守卫。

用例与容器内真实 OCR 缓存取证结论一致(2026-09-20,
.wolf/tmp/fix/probe_f2_sim.py / probe_f2b_sim.py;bug-1760713 后续修复):
- 砂石料 9839d01b: contract 文本路 miss, p10 会签表格命中 2GS-YCXM-CL-CG-024-2019;
  project_name '局审批编号' 误提取由 F2b 守卫拒收。
- 上浦 5b39470d: 文本路已命中 → 表格扫描零触发; p3 OCR 粘连截断值由形态门挡。
- 木饰面/钢材签字版/桂北: 全档零影响(文本路命中,表格无假命中)。
"""

import asyncio

import scripts.cli as cli
from scripts.project_fields import _find, find_contract_from_tables


class _T:
    """Minimal TableExtract stand-in (only .rows/.page_no are read)."""

    def __init__(self, rows, page_no=1):
        self.rows = rows
        self.page_no = page_no
        self.table_idx = 0


# ---------- F2a: 表格 cell 冒号兜底(方案A) ----------


def test_table_cell_hit_real_shashiao_p10():
    """砂石料 p10 会签表真实 cell → 命中 2GS-YCXM-CL-CG-024-2019。"""
    tables = [_T([["项目合同编号：2GS-YCXM-CL-CG-024-2019"]], page_no=10)]
    assert find_contract_from_tables(tables) == "2GS-YCXM-CL-CG-024-2019"


def test_table_cell_skips_approval_and_bid_decoys():
    """含 '审批编号'/'招标编号' 字样的格是招标/审批流水号诱饵 → 整格跳过。"""
    tables = [_T([
        ["招标文件审批编号：2GS-ZB-2019-038 宜春市佳之通贸易有 供方单位全称 限公司"],
        ["物资设备招标文件审批单 审批编号： 2GS-ZB-2019-038"],
        ["项目合同编号：2GS-YCXM-CL-CG-024-2019"],
    ], page_no=10)]
    assert find_contract_from_tables(tables) == "2GS-YCXM-CL-CG-024-2019"

    only_decoys = [_T([["局审批编号 合同编号"]], page_no=1)]
    assert find_contract_from_tables(only_decoys) is None


def test_table_cell_rejects_ocr_glued_truncation():
    """上浦 p3 OCR 粘连截断值('…-011-20 包合同段项目经理部')→ 形态门拒绝。"""
    tables = [_T([["项目合同编号：2GS-SPXM-CL-CG-011-20 包合同段项目经理部"]], page_no=3)]
    assert find_contract_from_tables(tables) is None


def test_table_cell_requires_colon_and_shape():
    """无冒号 label 独格(砂石料 p6)/形态不过/dash 段数<3 → 全拒。"""
    assert find_contract_from_tables([_T([["项目合同编号"]], page_no=6)]) is None
    assert find_contract_from_tables([_t_of("合同编号：短-值")]) is None
    assert find_contract_from_tables([_t_of("合同编号：HT-2025")]) is None  # 2 段
    assert find_contract_from_tables([_t_of("合同编号：HT-2025-001")]) == "HT-2025-001"


def _t_of(cell):
    return _T([[cell]])


def test_table_cell_first_hit_wins_and_dict_rows_ok():
    """取首个命中;dict 形态的表(rows 键)同样支持。"""
    tables = [
        {"rows": [["合同编号：AAA-BBB-CCC"]]},
        _T([["项目合同编号：2GS-YCXM-CL-CG-024-2019"]], page_no=10),
    ]
    assert find_contract_from_tables(tables) == "AAA-BBB-CCC"
    assert find_contract_from_tables(None) is None


# ---------- F2a 接入 _extract_project_fields_with_fallback 的档位仿真 ----------


def test_fallback_tables_hit_when_text_contract_misses(monkeypatch):
    """砂石料仿真: 文本路 contract miss + 乙方/日期前页齐 → 不发起末页 OCR,
    表格 cell 兜底命中(真实 p10 cell)。"""
    async def fail_parse(*a, **k):
        raise AssertionError("乙方/日期齐全时不应发起末页 OCR")

    monkeypatch.setattr(cli, "parse_document", fail_parse)
    tables = [_T([["项目合同编号：2GS-YCXM-CL-CG-024-2019"]], page_no=10)]
    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x",
        front_texts={1: "项目名称：某工程\n合同名称\n局审批编号\n乙方：某公司\n签订日期：2025-06-18"},
        tables=tables,
    ))
    assert got[0] == "某工程"                    # F2b 守卫不伤同路正名
    assert got[2] == "2GS-YCXM-CL-CG-024-2019"  # 表格兜底
    assert got[3] == "某公司"


def test_fallback_skips_tables_when_text_contract_hits(monkeypatch):
    """上浦仿真: 文本路已命中 → 表格零扫描(毒表被扫到即断言失败)。"""
    class Poison:
        @property
        def rows(self):
            raise AssertionError("文本路命中时不应扫描表格")

    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x",
        front_texts={
            1: "项目名称：某工程\n合同编号：2GS-SPXM-CL-CG-011-2021\n乙方：某公司\n签订日期：2025-06-18",
            3: "项目合同编号：2GS-SPXM-CL-CG-011-20 包合同段项目经理部",  # 粘连格在文本层也不得触发
        },
        tables=[Poison()],
    ))
    assert got[2] == "2GS-SPXM-CL-CG-011-2021"


def test_fallback_tables_default_none_stays_safe(monkeypatch):
    """tables 缺省 None(旧调用方) → 无表格兜底,维持文本路结果不抛。"""
    async def fake_parse(*a, **k):
        return [], {99: "末页无元数据"}, []

    monkeypatch.setattr(cli, "parse_document", fake_parse)
    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x", front_texts={1: "项目名称：某工程"},
    ))
    assert got[0] == "某工程"
    assert got[2] is None


def test_fallback_tail_merge_keeps_table_contract(monkeypatch):
    """表格兜底命中的合同号在与末页重试逐字段择优时必须保留。"""
    async def fake_parse(*a, **k):
        return [], {99: "合同编号：TAIL-AA-BB-CCC\n乙方：末页公司\n签订日期 2025年6月18日"}, []

    monkeypatch.setattr(cli, "parse_document", fake_parse)
    tables = [_T([["项目合同编号：2GS-YCXM-CL-CG-024-2019"]], page_no=10)]
    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x",
        front_texts={1: "项目名称：某工程"},
        tables=tables,
    ))
    assert got[2] == "2GS-YCXM-CL-CG-024-2019"  # 前档已得,末页不覆盖
    assert got[3] == "末页公司"
    assert got[4] == "2025-06-18"


# ---------- F2b: project_name split-line 守卫 ----------


def test_find_rejects_label_line_as_value():
    """标签独行下一行仍是标签(砂石料 '合同名称'→'局审批编号')→ 拒绝。"""
    name_labels = ["项目名称", "工程名称", "合同名称"]
    assert _find("合同名称\n局审批编号", name_labels) is None
    assert _find("项目名称\n招标编号：2GS-ZB-2019-038", name_labels) is None
    assert _find("项目名称\n工程名称", name_labels) is None


def test_find_split_line_still_takes_real_value():
    """既有正向行为不回归: 下一行是真值 → 照取(含守卫后 continue 再命中)。"""
    name_labels = ["项目名称", "工程名称", "合同名称"]
    assert _find("项目名称\n桂北数据中心", name_labels) == "桂北数据中心"
    # 第一个标签的下一行是标签被拒,第二个标签的下一行是真值 → 仍取到
    assert _find("合同名称\n局审批编号\n项目名称\n真项目名", name_labels) == "真项目名"


def test_shashiao_full_simulation():
    """砂石料全字段仿真(与 probe_f2b_sim 结论一致): name 拒收→None,
    其余字段行为不变;contract 走表格兜底(另测)。"""
    from scripts.project_fields import extract_project_fields

    front = {
        1: "局审批编号 合同编号\n合同名称\n局审批编号\n供方：易全勇",
        6: "项目合同编号",
        10: "项目合同编号：2GS-YCXM-CL-CG-024-2019",  # 该格在文本层也存在
    }
    name, loc, contract, supplier, sign = extract_project_fields(front)
    assert name is None          # F2b: '局审批编号' 不再被当项目名
    assert loc is None
    assert supplier == "易全勇"  # 非 F2 范围,行为保持
    assert sign is None
