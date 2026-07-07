"""Tests for markdown front-matter splitting."""

from app.extensions.output.generator import _split_frontmatter


def test_splits_simple_frontmatter():
    md = "---\ntitle: 消防专篇\nclient: 甲公司\n---\n# 总论\n正文\n"
    meta, body = _split_frontmatter(md)
    assert meta == {"title": "消防专篇", "client": "甲公司"}
    assert body == "# 总论\n正文\n"


def test_no_frontmatter_returns_empty_and_original():
    md = "# 没有前置 front-matter\n正文\n"
    meta, body = _split_frontmatter(md)
    assert meta == {}
    assert body == md


def test_strips_quoted_values():
    md = '---\ntitle: "双 引 号 标 题"\n---\n# H\n'
    meta, body = _split_frontmatter(md)
    assert meta == {"title": "双 引 号 标 题"}
    assert body == "# H\n"


def test_malformed_line_treats_whole_as_body():
    # 一行没有冒号 → 视为畸形,整段当正文
    md = "---\ntitle: X\n这行没有冒号\n---\n# H\n"
    meta, body = _split_frontmatter(md)
    assert meta == {}
    assert body == md


def test_ignores_comment_and_blank_lines_in_frontmatter():
    md = "---\n# 这是注释\ntitle: X\n\n---\n# H\n"
    meta, body = _split_frontmatter(md)
    assert meta == {"title": "X"}
    assert body == "# H\n"
