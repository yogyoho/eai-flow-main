"""Translation glossary loader (EAI-CUSTOM, T4 — 机制先行，内容=样例闸产出).

yaml 文件（可选，缺省空表跑机制）::

    terms:
      - source: iron ore concentrate
        action: force          # force=强制译法 / forbid|keep=不译清单（原样保留）
        target: 铁精矿
      - source: ArcelorMittal
        action: forbid

路径：``EAI_TRANSLATION_GLOSSARY`` env 或 ``config/translation_glossary.yaml``。
"""

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_PATHS = (
    "config/translation_glossary.yaml",
    "../config/translation_glossary.yaml",
)


@dataclass
class Glossary:
    force_terms: dict[str, str] = field(default_factory=dict)  # source -> 指定译法
    dont_translate: set[str] = field(default_factory=set)  # 不译清单（原样保留）

    def prompt_fragment(self) -> str:
        """注入 LLM prompt 的术语片段（空表 → 空串，不占 token）。"""
        lines: list[str] = []
        if self.force_terms:
            pairs = "；".join(f"{s}→{t}" for s, t in self.force_terms.items())
            lines.append(f"术语表（必须使用指定译法）：{pairs}")
        if self.dont_translate:
            lines.append("不译清单（以下词语在译文中保持原文不变）：" + "、".join(sorted(self.dont_translate)))
        return "\n".join(lines)


def load_glossary(path: str | None = None) -> Glossary:
    """加载术语库；文件缺失/解析失败 → 空表（机制跑通，内容样例闸后补）。"""
    candidates = [path] if path else list(_DEFAULT_PATHS)
    for candidate in candidates:
        if not candidate or not os.path.exists(candidate):
            continue
        try:
            import yaml

            with open(candidate, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            glossary = Glossary()
            for entry in data.get("terms") or []:
                source = str(entry.get("source", "")).strip()
                action = str(entry.get("action", "force")).strip().lower()
                if not source:
                    continue
                if action == "force":
                    target = str(entry.get("target", "")).strip()
                    if target:
                        glossary.force_terms[source] = target
                else:  # forbid / keep
                    glossary.dont_translate.add(source)
            logger.info("tlt glossary loaded: %s (force=%d, dont=%d)", candidate, len(glossary.force_terms), len(glossary.dont_translate))
            return glossary
        except Exception:
            logger.exception("tlt glossary load failed for %s; using empty glossary", candidate)
            return Glossary()
    return Glossary()
