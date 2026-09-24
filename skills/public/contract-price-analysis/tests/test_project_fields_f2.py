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
    """文本路合同编号命中 → contract 不取表格值(表格里的合同编号诱饵必须落败)。
    注: project_name 的完整度排序自 2026-09-21 起凡有 tables 即参与 cell 候选
    (上浦: 文本截断名须让位给 cell 全名),严格的'零扫描'断言仅对合同编号成立。"""
    tables = [_T([["合同编号：TDecoy-AA-BB-CCC"]], page_no=3)]

    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x",
        front_texts={
            # 项目编号也须文本命中——project_no 的 cell 兜底同样只在文本 miss 时扫表
            1: "项目名称：某工程\n合同编号：2GS-SPXM-CL-CG-011-2021\n项目编号：P2021-001\n"
               "乙方：某公司\n签订日期：2025-06-18",
            3: "项目合同编号：2GS-SPXM-CL-CG-011-20 包合同段项目经理部",  # 粘连格在文本层也不得触发
        },
        tables=tables,
    ))
    assert got[2] == "2GS-SPXM-CL-CG-011-2021"
    assert got[5] == "P2021-001"


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
    """砂石料全字段仿真(2026-09-21 甄别规则更新): name 拒收→None;
    supplier='供方：易全勇' 个人名无公司字样 → 甄别拒收(bug: 错值易全勇曾入库);
    contract 走表格兜底(另测)。"""
    from scripts.project_fields import extract_project_fields

    front = {
        1: "局审批编号 合同编号\n合同名称\n局审批编号\n供方：易全勇",
        6: "项目合同编号",
        10: "项目合同编号：2GS-YCXM-CL-CG-024-2019",  # 该格在文本层也存在
    }
    name, loc, contract, supplier, sign, pno = extract_project_fields(front)
    assert name is None          # F2b: '局审批编号' 不再被当项目名
    assert loc is None
    assert supplier is None      # 个人名拒收(公司字样甄别)——真值在 p6 [供方单位]格,cell 兜底另测
    assert sign is None
    assert pno is None


# ---------- bug-3431: 重解析 None 必须落库清空(truthy-冻结修复) ----------


def test_persist_one_doc_field_sentinel_is_key_presence():
    """重解析路径元数据字段以键存在为哨兵: 键在(None 也在)→ 写 None 清旧值;
    失败标记路径无键 → 不触碰。回归 bug-3431(砂石料 project_name 旧值被
    truthy-guard 冻结)。源码契约断言(无 DB 依赖,同 test_persist_one_doc_writes_category_kwarg)。"""
    import inspect

    from scripts.cli import _persist_one_doc

    src = inspect.getsource(_persist_one_doc)
    # 键存在哨兵: 元数据字段统一按 `_mf in doc` 判定,不再 if doc.get(...)(truthy)
    assert 'for _mf in ("project_name", "project_location", "contract_no", "supplier", "project_no"):' in src
    assert "if _mf in doc:" in src
    assert 'if "sign_date" in doc:' in src
    assert 'if doc.get("project_name")' not in src, "truthy-guard 回潮(bug-3431 复发)"
    assert 'if doc.get("contract_no")' not in src
    assert 'if doc.get("supplier")' not in src
    assert 'if doc.get("project_location")' not in src
    assert 'if doc.get("project_no")' not in src
    assert 'if doc.get("sign_date")' not in src


# ── bug-3431 行为三例(桩 session+桩 ORM, 验证持久化语义本身而非源码形状) ─────
# _persist_one_doc 全身 try/except 吞异常 → 桩必须记 commit 次数, 断言前先证明
# 真的走到了提交(否则静默跳过会伪装成"字段保持"假绿)。

import pytest  # noqa: E402
import sqlalchemy as _sa  # noqa: E402
from sqlalchemy.orm import declarative_base  # noqa: E402

_PStubBase = declarative_base()


class _StubCpaDocument(_PStubBase):
    """可 select/可实例化的轻量替身(纯表达式构造, 不落任何真库)。"""

    __tablename__ = "stub_persist_docs"

    id = _sa.Column(_sa.Integer, primary_key=True)
    storage_uri = _sa.Column(_sa.Text)
    file_name = _sa.Column(_sa.Text)
    file_hash = _sa.Column(_sa.Text)
    file_type = _sa.Column(_sa.Text)
    quick_fp = _sa.Column(_sa.Text)
    parse_mode = _sa.Column(_sa.Text)
    parse_status = _sa.Column(_sa.Text)
    confirm_status = _sa.Column(_sa.Text)
    parse_meta = _sa.Column(_sa.Text)
    page_count = _sa.Column(_sa.Integer)
    preview_prefix = _sa.Column(_sa.Text)
    project_name = _sa.Column(_sa.Text)
    project_location = _sa.Column(_sa.Text)
    contract_no = _sa.Column(_sa.Text)
    supplier = _sa.Column(_sa.Text)
    sign_date = _sa.Column(_sa.Text)
    parsed_at = _sa.Column(_sa.Text)


class _StubCpaItem(_PStubBase):
    __tablename__ = "stub_persist_items"

    id = _sa.Column(_sa.Integer, primary_key=True)
    document_id = _sa.Column(_sa.Integer)


class _StubResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _StubSession:
    """select → 预置 existing 行; 其余(add/flush/delete-execute)全 no-op。"""

    def __init__(self, existing):
        self._existing = existing
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _stmt):
        return _StubResult(self._existing)

    def add(self, _obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


def _persist_doc_dict(**meta):
    d = {
        "storage_uri": "contracts/ssxl.pdf",
        "file_name": "ssxl.pdf",
        "hash": "a" * 64,
        "type": "pdf",
        "parse_status": "parsed",
        "parse_meta": {},
    }
    d.update(meta)
    return d


@pytest.mark.asyncio
async def test_persist_none_clears_stale_value_to_null(monkeypatch):
    """例1 旧错值+本轮诚实 None → 清 NULL: 砂石料 project_name='局审批编号'
    被重解析诚实 None 清掉, contract_no 有值照写(键在即写, 哨兵语义)。"""
    import scripts.db as db_mod
    import scripts.models as models_mod

    existing = _StubCpaDocument(
        project_name="局审批编号", project_location="旧地点", supplier="旧供方",
        contract_no=None, sign_date=None,
    )
    session = _StubSession(existing)
    monkeypatch.setattr(db_mod, "async_session", lambda: session)
    monkeypatch.setattr(models_mod, "CpaDocument", _StubCpaDocument)
    monkeypatch.setattr(models_mod, "CpaItem", _StubCpaItem)

    from scripts.cli import _persist_one_doc

    await _persist_one_doc(
        _persist_doc_dict(
            project_name=None, project_location=None, supplier=None,
            contract_no="2GS-YCXM-CL-CG-024-2019", sign_date=None,
        ),
        [],
    )
    assert session.commits == 1, "中途异常被 except 吞掉, 持久化未执行"
    assert existing.project_name is None, "诚实 None 未清掉旧错值(bug-3431 复发)"
    assert existing.project_location is None
    assert existing.supplier is None
    assert existing.sign_date is None
    assert existing.contract_no == "2GS-YCXM-CL-CG-024-2019"


@pytest.mark.asyncio
async def test_persist_new_value_overwrites_old(monkeypatch):
    """例2 旧值+新值 → 覆写: supplier/sign_date 均被本轮新抽取值替换。"""
    import datetime as _dt

    import scripts.db as db_mod
    import scripts.models as models_mod

    existing = _StubCpaDocument(
        project_name="旧项目", project_location="旧地点",
        supplier="旧供方A", contract_no="OLD-001",
        sign_date=_dt.date(2019, 1, 1),
    )
    session = _StubSession(existing)
    monkeypatch.setattr(db_mod, "async_session", lambda: session)
    monkeypatch.setattr(models_mod, "CpaDocument", _StubCpaDocument)
    monkeypatch.setattr(models_mod, "CpaItem", _StubCpaItem)

    from scripts.cli import _persist_one_doc

    await _persist_one_doc(
        _persist_doc_dict(
            project_name="新项目", project_location="新地点",
            supplier="新供方B", contract_no="NEW-002", sign_date="2019-07-25",
        ),
        [],
    )
    assert session.commits == 1, "中途异常被 except 吞掉, 持久化未执行"
    assert existing.project_name == "新项目"
    assert existing.project_location == "新地点"
    assert existing.supplier == "新供方B"
    assert existing.contract_no == "NEW-002"
    assert existing.sign_date == _dt.date(2019, 7, 25)


@pytest.mark.asyncio
async def test_persist_no_extraction_keys_keeps_existing(monkeypatch):
    """例3 抽取未跑(失败标记路径, doc 无元数据键) → 既有字段分毫不动。
    防误清语义: except 分支只标 parse_status=failed, 不许把旧值洗成 NULL。"""
    import datetime as _dt

    import scripts.db as db_mod
    import scripts.models as models_mod

    existing = _StubCpaDocument(
        project_name="旧项目", project_location="旧地点",
        supplier="旧供方", contract_no="OLD-001",
        sign_date=_dt.date(2019, 1, 1), parse_status="parsed",
    )
    session = _StubSession(existing)
    monkeypatch.setattr(db_mod, "async_session", lambda: session)
    monkeypatch.setattr(models_mod, "CpaDocument", _StubCpaDocument)
    monkeypatch.setattr(models_mod, "CpaItem", _StubCpaItem)

    from scripts.cli import _persist_one_doc

    # 失败标记 doc: 与 cli.py except 分支同形——无任何元数据键
    await _persist_one_doc(
        _persist_doc_dict(parse_status="failed"),
        [],
    )
    assert session.commits == 1, "中途异常被 except 吞掉, 持久化未执行"
    assert existing.parse_status == "failed"
    assert existing.project_name == "旧项目"
    assert existing.project_location == "旧地点"
    assert existing.supplier == "旧供方"
    assert existing.contract_no == "OLD-001"
    assert existing.sign_date == _dt.date(2019, 1, 1)
