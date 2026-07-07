"""Tests for decimal heading-number computation."""
from app.extensions.output.generator import Block, _compute_heading_numbers


def _blocks(*specs):
    # specs: ("h1","总论"), ("h2","子"), ...
    out = []
    for level, text in specs:
        out.append(Block(kind="heading", level=level, text=text))
    return out


def test_decimal_multilevel():
    blocks = _blocks((1, "总论"), (2, "a"), (2, "b"), (3, "b1"), (1, "二章"), (2, "c"))
    hs = [
        {"level": 1, "numbering": "decimal"},
        {"level": 2, "numbering": "decimal"},
        {"level": 3, "numbering": "decimal"},
    ]
    nums = _compute_heading_numbers(blocks, hs)
    assert nums == {0: "1", 1: "1.1", 2: "1.2", 3: "1.2.1", 4: "2", 5: "2.1"}


def test_level_reset_when_parent_advances():
    blocks = _blocks((1, "一"), (2, "a"), (1, "二"), (2, "b"))
    hs = [{"level": 1, "numbering": "decimal"}, {"level": 2, "numbering": "decimal"}]
    nums = _compute_heading_numbers(blocks, hs)
    assert nums == {0: "1", 1: "1.1", 2: "2", 3: "2.1"}


def test_numbering_none_skips_number():
    blocks = _blocks((1, "一"), (2, "a"))
    hs = [{"level": 1, "numbering": "none"}, {"level": 2, "numbering": "none"}]
    nums = _compute_heading_numbers(blocks, hs)
    assert nums == {}


def test_non_heading_blocks_ignored():
    blocks = [Block(kind="paragraph", text="p"), Block(kind="heading", level=1, text="h")]
    nums = _compute_heading_numbers(blocks, [{"level": 1, "numbering": "decimal"}])
    assert nums == {1: "1"}
