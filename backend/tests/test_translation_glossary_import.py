"""Glossary Excel/CSV import parsing + merge tests (pure, no DB)."""

import openpyxl
import pytest

from app.extensions.translation.glossary import GlossaryEntry
from app.extensions.translation.glossary_import import MAX_IMPORT_BYTES, merge, parse_file


def _xlsx(rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    from io import BytesIO

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_xlsx_parse_merge_and_validation() -> None:
    data = _xlsx(
        [
            ["源词", "语言", "动作", "目标译法", "领域", "说明"],
            ["iron ore concentrate", "EN", "指定译法", "铁精矿", "铁矿开采", "首批术语"],
            ["contrat d'enlèvement", "法文", "指定译法", "包销协议", "合同法务", "旧译法待替换"],
            ["force majeure", "fr", "指定译法", None, "合同法务; 铁矿开采", "待补翻译"],
            ["ArcelorMittal", "ANY", "保留原文", None, None, "公司名"],
            ["iron ore concentrate", "en", "指定译法", "铁矿石精矿", "铁矿开采", None],
            ["EBITDA", "通用", "原样保留", None, "经营财务", "缩写"],
        ]
    )
    existing = [
        GlossaryEntry(
            source="iron ore concentrate",
            lang="en",
            action="force",
            target="铁精矿",
            domains=["铁矿开采"],
            notes="首批术语",
        ),
        GlossaryEntry(source="contrat d'enlèvement", lang="fr", action="force", target="提货合同", domains=["合同法务"]),
    ]

    parsed = parse_file("glossary.xlsx", data)
    result = merge(existing, parsed)

    assert [row.row for row in parsed] == [2, 3, 4, 5, 6, 7]
    statuses = {row.row: row.status for row in result.rows}
    assert statuses[2] == "unchanged"
    assert statuses[3] == "update"
    assert statuses[4] == "invalid"  # force 缺目标译法
    assert statuses[5] == "add"
    assert statuses[6] == "invalid"  # 文件内重复
    assert statuses[7] == "add"

    assert result.summary == {"add": 2, "update": 1, "unchanged": 1, "invalid": 2, "total": 6}
    merged = {(e.source.casefold(), e.lang): e for e in result.merged}
    assert merged[("contrat d'enlèvement", "fr")].target == "包销协议"
    assert merged[("contrat d'enlèvement", "fr")].domains == ["合同法务"]
    assert merged[("iron ore concentrate", "en")].notes == "首批术语"
    assert merged[("arcelormittal", "any")].action == "forbid"
    assert merged[("arcelormittal", "any")].notes == "公司名"
    assert parsed[2].domains == ["合同法务", "铁矿开采"]  # 分号分隔多值
    assert ("force majeure", "fr") not in merged


def test_csv_chinese_headers_and_aliases() -> None:
    data = ("术语,语言,类型,译文,业务领域,说明\nfreight rate,英文,指定译法,运费率,货物运输、价格条款,运费口径\nconnaissement,法文,指定译法,提单,货物运输,\nbordereau,fr,保留原文,,货物运输,提单背面\n").encode("utf-8-sig")

    parsed = parse_file("glossary.csv", data)
    result = merge([], parsed)

    assert [row.status for row in result.rows] == ["add", "add", "add"]
    assert result.merged[0].lang == "en"
    assert result.merged[0].target == "运费率"
    assert result.merged[0].domains == ["货物运输", "价格条款"]
    assert result.merged[0].notes == "运费口径"
    assert result.merged[1].lang == "fr"
    assert result.merged[2].action == "forbid" and result.merged[2].target is None
    assert result.merged[2].notes == "提单背面"


def test_rejects_xls_and_oversized_and_missing_header() -> None:
    with pytest.raises(ValueError, match=r"\.xls"):
        parse_file("glossary.xls", b"anything")
    with pytest.raises(ValueError, match="2 MB"):
        parse_file("glossary.xlsx", b"x" * (MAX_IMPORT_BYTES + 1))
    with pytest.raises(ValueError, match="表头"):
        parse_file(
            "glossary.csv",
            b"a,b\n1,2\n",
        )


def test_header_can_start_after_title_rows() -> None:
    data = _xlsx(
        [
            ["铁矿项目术语表", None, None, None],
            [None, None, None, None],
            ["源词", "语言", "动作", "目标译法"],
            ["demurrage", "en", "指定译法", "滞期费"],
        ]
    )

    parsed = parse_file("glossary.xlsx", data)
    assert len(parsed) == 1
    assert parsed[0].row == 4
    assert parsed[0].source == "demurrage"
