"""Translation glossary store + loader (EAI-CUSTOM, T4; 2026-10-18 语言/领域维度).

yaml schema v2::

    terms:
      - source: iron ore concentrate
        lang: en            # en | fr | any（缺省 any = 英法通用）
        action: force       # force=指定译法 / forbid=保留原文 / keep=原样保留
        target: 铁精矿
        domains: [铁矿开采]  # 可选，仅标注，可多值（旧版 domain 单值仍兼容）
        notes: 首批术语        # 可选说明

路径：``EAI_TRANSLATION_GLOSSARY`` env 或 ``config/translation_glossary.yaml``。
存量无 ``lang`` 的词条按 ``any`` 处理——行为与旧版全局术语表等价。
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

ACTIONS = frozenset({"force", "forbid", "keep"})
LANGS = frozenset({"en", "fr", "any"})

_DEFAULT_PATHS = (
    "config/translation_glossary.yaml",
    "../config/translation_glossary.yaml",
)


@dataclass
class GlossaryEntry:
    """一条术语（routers / import / loader 共用的纯数据形态）。"""

    source: str
    action: str = "force"
    target: str | None = None
    lang: str = "any"
    domains: list[str] = field(default_factory=list)
    notes: str | None = None


def clean_domains(value: object) -> list[str]:
    """归一去重领域标签（兼容旧版单值 ``domain`` 与新 ``domains`` 列表）。"""
    if isinstance(value, str):
        raw: list[object] = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


@dataclass
class Glossary:
    """按语言分组的术语表。

    ``force_terms`` / ``dont_translate`` 保存 ``lang=any`` 的条目；
    ``force_by_lang`` / ``dont_by_lang`` 保存 en/fr 专属条目。
    ``for_language`` 合并两者，具体语言覆盖 ANY。
    """

    force_terms: dict[str, str] = field(default_factory=dict)  # ANY source -> target
    dont_translate: set[str] = field(default_factory=set)  # ANY 不译清单
    force_by_lang: dict[str, dict[str, str]] = field(default_factory=dict)
    dont_by_lang: dict[str, set[str]] = field(default_factory=dict)

    def for_language(self, lang: str) -> tuple[dict[str, str], set[str]]:
        """返回该任务源语言生效的 (force_terms, dont_translate)。mixed = en+fr+any。"""
        if lang == "mixed":
            codes = ["en", "fr"]
        elif lang in {"en", "fr"}:
            codes = [lang]
        else:
            codes = []
        force = dict(self.force_terms)
        dont = set(self.dont_translate)
        for code in codes:
            force.update(self.force_by_lang.get(code, {}))
            dont |= self.dont_by_lang.get(code, set())
        return force, dont

    def prompt_fragment(self, text: str, lang: str) -> str:
        """只拼接命中当前 block 文本的术语；空结果返回空串（不占 token）。"""
        force, dont = self.for_language(lang)
        haystack = text.casefold()
        force_hits = {s: t for s, t in force.items() if s.casefold() in haystack}
        dont_hits = sorted(s for s in dont if s.casefold() in haystack)
        lines: list[str] = []
        if force_hits:
            pairs = "；".join(f"{s}→{t}" for s, t in force_hits.items())
            lines.append(f"术语表（必须使用指定译法）：{pairs}")
        if dont_hits:
            lines.append("不译清单（以下词语在译文中保持原文不变）：" + "、".join(dont_hits))
        return "\n".join(lines)


def resolve_glossary_path(path: str | None = None) -> Path:
    """术语表文件路径：显式参数 > env > 既有文件 > 默认位置。"""
    if path:
        return Path(path)
    env = os.environ.get("EAI_TRANSLATION_GLOSSARY")
    if env:
        return Path(env)
    for candidate in _DEFAULT_PATHS:
        if Path(candidate).exists():
            return Path(candidate)
    return Path(_DEFAULT_PATHS[0])


def read_entries(path: Path) -> list[GlossaryEntry]:
    """读取并归一化词条；非法条目跳过并 warning（不阻断整表）。"""
    if not path.exists():
        return []
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[GlossaryEntry] = []
    for raw in data.get("terms") or []:
        if not isinstance(raw, dict):
            logger.warning("tlt glossary: skip non-mapping entry: %r", raw)
            continue
        source = str(raw.get("source", "")).strip()
        if not source:
            continue
        action = str(raw.get("action", "")).strip().lower()
        if action not in ACTIONS:
            logger.warning("tlt glossary: skip %r with invalid action %r", source, action)
            continue
        lang = str(raw.get("lang", "any")).strip().lower() or "any"
        if lang not in LANGS:
            logger.warning("tlt glossary: %r has invalid lang %r; treating as any", source, lang)
            lang = "any"
        target = str(raw.get("target", "")).strip() or None
        if action == "force" and not target:
            logger.warning("tlt glossary: skip force term %r without target", source)
            continue
        if action != "force":
            target = None
        domain_value = raw.get("domains") if raw.get("domains") is not None else raw.get("domain")
        domains = clean_domains(domain_value)
        notes = str(raw.get("notes") or "").strip() or None
        out.append(GlossaryEntry(source=source, action=action, target=target, lang=lang, domains=domains, notes=notes))
    return out


def write_entries(path: Path, entries: list[GlossaryEntry]) -> None:
    """原子写入 YAML（临时文件 + os.replace）。"""
    import yaml

    payload = {"terms": []}
    for e in entries:
        item: dict[str, object] = {"source": e.source, "lang": e.lang, "action": e.action}
        if e.target:
            item["target"] = e.target
        if e.domains:
            item["domains"] = list(e.domains)
        if e.notes:
            item["notes"] = e.notes
        payload["terms"].append(item)

    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    fd, tmp = tempfile.mkstemp(suffix=".yaml", dir=str(path.parent), prefix=".glossary-")
    os.close(fd)
    try:
        Path(tmp).write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def file_version(path: Path) -> str:
    """内容版本（sha256）；文件不存在时返回空内容的哈希。"""
    data = path.read_bytes() if path.exists() else b""
    return hashlib.sha256(data).hexdigest()


def load_glossary(path: str | None = None) -> Glossary:
    """加载术语表；文件缺失/解析失败 → 空表（机制跑通，内容后续维护）。"""
    resolved = resolve_glossary_path(path)
    if not resolved.exists():
        return Glossary()
    try:
        entries = read_entries(resolved)
    except Exception:
        logger.exception("tlt glossary load failed for %s; using empty glossary", resolved)
        return Glossary()

    glossary = Glossary()
    for e in entries:
        if e.lang == "any":
            if e.action == "force":
                glossary.force_terms[e.source] = e.target or ""
            else:
                glossary.dont_translate.add(e.source)
        elif e.action == "force":
            glossary.force_by_lang.setdefault(e.lang, {})[e.source] = e.target or ""
        else:
            glossary.dont_by_lang.setdefault(e.lang, set()).add(e.source)
    logger.info(
        "tlt glossary loaded: %s (any force=%d, any dont=%d, lang force=%s, lang dont=%s)",
        resolved,
        len(glossary.force_terms),
        len(glossary.dont_translate),
        {k: len(v) for k, v in glossary.force_by_lang.items()},
        {k: len(v) for k, v in glossary.dont_by_lang.items()},
    )
    return glossary
