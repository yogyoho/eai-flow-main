"""IRI 策略（国标 GB/T 48000.3 §5.4：IRI = 命名空间 + 本地标识符）.

- 类 IRI：   {ns}{ClassName}          （如 …/doc_graph#Project）
- 实例 IRI： {ns}id/{uuid}            （机械可逆：反解即业务主键，零映射表）
- 每域独立命名空间（国标 §9.2 扩展原则）；域未声明 namespaces 时用默认基底。
"""

from __future__ import annotations

import re
import uuid

DEFAULT_BASE = "https://ontology.eai-flow.com/"

_PASCAL_BOUNDARY = re.compile(r"[_\-]+")


def etype_to_class_name(etype: str) -> str:
    """project → Project；sensitive_point → SensitivePoint（PascalCase）。"""
    return "".join(part[:1].upper() + part[1:] for part in _PASCAL_BOUNDARY.split(etype) if part)


def domain_namespace(domain: str, declared: dict[str, str] | None = None) -> str:
    """域命名空间：优先取域 YAML namespaces 中第一个非 W3C 声明，否则默认基底拼接。

    declared 形如 {"dg": "https://ontology.eai-flow.com/doc_graph#"}——任取其一即可
    （同一域文件内的声明应指向同一空间，冲突由 lint 层负责，此处不重复校验）。
    """
    if declared:
        for value in declared.values():
            if value and not value.startswith(("http://www.w3.org/", "urn:")):
                return value
    return f"{DEFAULT_BASE}{domain}#"


class IriScheme:
    """单域 IRI 编解码（compile/store 共用）。"""

    __slots__ = ("namespace",)

    def __init__(self, namespace: str) -> None:
        if not namespace.startswith(("http://", "https://", "urn:")):
            raise ValueError(f"命名空间必须是 IRI：{namespace!r}")
        self.namespace = namespace

    def class_iri(self, class_name: str) -> str:
        return f"{self.namespace}{class_name}"

    def instance_iri(self, entity_uuid: str | uuid.UUID) -> str:
        return f"{self.namespace}id/{entity_uuid}"

    def parse_instance(self, iri: str) -> uuid.UUID:
        """实例 IRI → 业务主键；非本域实例或非 uuid 后缀 → ValueError（fail-closed）。"""
        prefix = f"{self.namespace}id/"
        if not iri.startswith(prefix):
            raise ValueError(f"非本域实例 IRI：{iri}")
        return uuid.UUID(iri[len(prefix) :])  # 非法 uuid 此处抛 ValueError
