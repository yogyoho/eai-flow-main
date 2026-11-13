"""F3 章节装配(批二十 M1-h,EAI-CUSTOM 2026-11-13)——tender.required_sections
→章节树 sec:N(spec §2.4 attachment_index 的章节输入面+M2 目录导出复用):
编号前缀("1."/"1.1"/"1.1.1")定级,无编号默认一级;code=sec:N 稳定序(输入序
即文档序)。纯函数零 IO 零时钟。"""

from __future__ import annotations

import re

_NUM_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)")


def assemble_sections(required_sections: list | None) -> list[dict]:
    out: list[dict] = []
    for i, s in enumerate(required_sections or [], 1):
        title = str(s).strip()
        m = _NUM_PREFIX.match(title)
        level = (m.group(1).count(".") + 1) if m else 1
        out.append({"code": f"sec:{i}", "title": title, "level": level})
    return out
