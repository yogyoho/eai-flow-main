"""_parse_json_object 尾逗号宽松修复 + _invoke_json 三试纠错共享核。

bug-4086 血亲(2026-11-06 活体方差回采):tables 分片小输出尾逗号是高频死因;
extract 大分片截断型双败。三试 + 第 2/3 试回灌 assistant 原文 + 纠错 user 轮
(模型可见自己的错误,修复率高于盲目重掷)。
"""

import pytest

from app.extensions.bid_review import worker


class _FakeModel:
    """按脚本回放 content 的假模型;记录每次收到的 messages。"""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls: list[list[dict]] = []

    def invoke(self, messages):
        self.calls.append([dict(m) for m in messages])

        class _R:
            pass

        r = _R()
        r.content = self.scripts.pop(0)
        return r


def test_parse_json_object_repairs_trailing_comma():
    assert worker._parse_json_object('{"a": [1, 2,], "b": "x",}') == {"a": [1, 2], "b": "x"}


def test_parse_json_object_strict_error_still_raised():
    with pytest.raises(ValueError):
        worker._parse_json_object('{"a": "未闭合')


def test_invoke_json_recovers_by_third_attempt():
    m = _FakeModel(["完全不是JSON", '{"a": [1, 2]}}', '{"a": 1}'])
    out = worker._invoke_json(m, "P", "表格提取")
    assert out == {"a": 1}
    assert len(m.calls) == 3
    # 第 2 试起:assistant 原文回灌 + 纠错 user 轮(模型可见自己上轮输出)
    assert m.calls[1][-2]["role"] == "assistant"
    assert m.calls[1][-1]["role"] == "user"
    assert "JSON" in m.calls[1][-1]["content"]


def test_invoke_json_exhausts_with_noun_label():
    m = _FakeModel(["x", "y", "z"])
    with pytest.raises(RuntimeError, match="表格提取三试未获有效 JSON"):
        worker._invoke_json(m, "P", "表格提取")
