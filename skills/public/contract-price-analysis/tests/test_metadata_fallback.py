"""末页兜底: 前3页字段 miss → 补 OCR 最后2页 → 合并 page_texts 重试。"""

import asyncio

import scripts.cli as cli


def test_fallback_triggers_only_on_miss(monkeypatch):
    async def fake_parse(file_bytes, filename, url, last_pages=0):
        assert last_pages == 2, "miss 时应请求末2页"
        return [], {99: "乙方：末页建筑公司\n签订日期 2025年6月18日"}

    monkeypatch.setattr(cli, "parse_document", fake_parse)
    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x",
        front_texts={1: "项目名称：某工程"},  # 前页无乙方/日期
    ))
    assert got[3] == "末页建筑公司"   # supplier
    assert got[4] == "2025-06-18"     # sign_date


def test_no_fallback_when_front_pages_hit(monkeypatch):
    async def fail_parse(*a, **k):
        raise AssertionError("字段齐全时不应发起末页 OCR")

    monkeypatch.setattr(cli, "parse_document", fail_parse)
    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x",
        front_texts={1: "项目名称：某工程\n乙方：甲公司\n签订日期：2025-06-18"},
    ))
    assert got[3] == "甲公司"
