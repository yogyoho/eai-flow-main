import re
from typing import NamedTuple


class ParsedSource(NamedTuple):
    block_index: int
    source_type: str
    source_ref: str
    snippet: str
    confidence: float | None = None
    metadata: dict | None = None


def parse_source_markers(content: str, block_start_index: int = 0) -> list[ParsedSource]:
    """Parse [N] source markers from AI-generated content.

    AI output format:
        Text with data[1] and more[2].

        [1] source:rag_retrieval:知识库「...」→「文档」p.23
        [2] source:regulation:GB 3095-2012 表2
    """
    sources: list[ParsedSource] = []

    blocks = content.split("\n\n")

    # Collect footnotes: [N] source:type:ref
    footnotes: dict[str, dict] = {}
    footnote_pattern = re.compile(r"^\[(\d+)\]\s+source:(\w+):(.+)$", re.MULTILINE)
    for block in blocks:
        for match in footnote_pattern.finditer(block):
            num, stype, sref = match.group(1), match.group(2), match.group(3).strip()
            footnotes[num] = {"type": stype, "ref": sref}

    # Find inline markers: text[N]
    inline_pattern = re.compile(r"\[(\d+)\]")
    block_idx = block_start_index
    for block in blocks:
        if footnote_pattern.match(block.strip()):
            continue
        for match in inline_pattern.finditer(block):
            num = match.group(1)
            if num in footnotes:
                fn = footnotes[num]
                start = max(0, match.start() - 30)
                end = min(len(block), match.end() + 30)
                snippet = block[start:end].strip()
                sources.append(ParsedSource(
                    block_index=block_idx,
                    source_type=fn["type"],
                    source_ref=fn["ref"],
                    snippet=snippet,
                ))
        block_idx += 1

    return sources


def find_missing_sources(content: str) -> list[dict]:
    """Find paragraphs/blocks that have no source annotations."""
    blocks = content.split("\n\n")
    missing = []
    footnote_pattern = re.compile(r"^\[\d+\]\s+source:", re.MULTILINE)
    inline_pattern = re.compile(r"\[\d+\]")

    for idx, block in enumerate(blocks):
        if footnote_pattern.match(block.strip()):
            continue
        if not block.strip():
            continue
        if not inline_pattern.search(block):
            missing.append({
                "block_index": idx,
                "preview": block.strip()[:50],
            })

    return missing
