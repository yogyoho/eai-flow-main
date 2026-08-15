"""Ontology 注册表加载器（YAML → 类型化注册表）.

- fail-closed：任何文件解析/校验/交叉引用失败 → 抛 RegistryError（带文件名+行号），
  绝不半加载（热重载失败保留旧版本继续服务）。
- 逐文件 SHA-256 内容指纹（mtime 在挂载环境不可靠，同 config.yaml 签名模式）；
  指纹变化 → 全量重解析 → 原子替换 → registry_version 递增。
- D4 双进程一致性：gateway 与 MCP 进程各自逐调用 check_reload()（同指纹输入 → 同版本输出）。
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.extensions.ontology.schemas import DomainFile, LinkType, Manifest, ObjectType

REGISTRY_DIR = Path(__file__).parent / "registry"


class RegistryError(Exception):
    """注册表加载失败（fail-closed）。"""


class Registry:
    """不可变快照：加载完成后整体替换，不做增量变异。"""

    def __init__(
        self,
        manifest: Manifest,
        object_types: dict[str, ObjectType],
        link_types: dict[str, LinkType],
        file_fingerprints: dict[str, str],
        registry_version: int,
    ) -> None:
        self.manifest = manifest
        self.object_types = object_types
        self.link_types = link_types
        self.file_fingerprints = file_fingerprints
        self.registry_version = registry_version


def _read_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        mark = getattr(getattr(e, "problem_mark", None), "line", None)
        loc = f"{path.name}:{mark + 1}" if mark is not None else path.name
        raise RegistryError(f"YAML 语法错误: {loc}: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RegistryError(f"{path.name}: 顶层必须是 mapping, 得到 {type(data).__name__}")
    return data


def _validate_domain_file(path: Path, data: dict) -> DomainFile:
    try:
        return DomainFile.model_validate(data)
    except ValidationError as e:
        loc0 = ".".join(str(x) for x in (e.errors()[0]["loc"] if e.errors() else []))
        raise RegistryError(f"schema 校验失败: {path.name}: {loc0}: {e.errors()[0]['msg'] if e.errors() else e}") from e


def _check_cross_refs(path: Path, objects: dict[str, ObjectType], links: dict[str, LinkType], pending: set[str]) -> None:
    """文件内 + 跨文件（pending=尚未加载的 api_name）交叉引用检查。"""
    for lt in links.values():
        for role, ref in (("source", lt.source), ("target", lt.target)):
            if ref not in objects and ref not in pending:
                raise RegistryError(f"{path.name}: 链接 {lt.api_name} 的 {role} 对象类型 '{ref}' 未注册")
        if lt.reverse == lt.api_name:
            raise RegistryError(f"{path.name}: 链接 {lt.api_name} 的 reverse 名不能与自身相同")
        j = lt.join
        if j.type == "foreign_key" and not (j.source_column and j.target_column):
            raise RegistryError(f"{path.name}: 链接 {lt.api_name} foreign_key join 需要 source/target_column")
        if j.type == "normalized_key_match" and not j.key_pairs:
            raise RegistryError(f"{path.name}: 链接 {lt.api_name} normalized_key_match join 需要 key_pairs")
        # FK 列必须在已注册对象的属性里声明（declared-only 铁律从注册表开始）
        if j.type == "foreign_key" and lt.source in objects and j.source_column:
            src_props = {p.name for p in objects[lt.source].properties}
            if j.source_column not in src_props and j.source_column != objects[lt.source].pk.column:
                raise RegistryError(f"{path.name}: 链接 {lt.api_name} 的 source_column '{j.source_column}' 未在 {lt.source} 属性中声明")
        if j.type == "normalized_key_match" and lt.source in objects:
            src_props = {p.name for p in objects[lt.source].properties}
            for pair in j.key_pairs or []:
                if pair[0] not in src_props:
                    raise RegistryError(f"{path.name}: 链接 {lt.api_name} 的 key 列 '{pair[0]}' 未在 {lt.source} 属性中声明")


def load_registry(registry_dir: Path = REGISTRY_DIR) -> Registry:
    """全量加载 + 校验。任何失败 fail-closed 抛 RegistryError。"""
    manifest_path = registry_dir / "_manifest.yaml"
    if not manifest_path.exists():
        raise RegistryError(f"清单不存在: {manifest_path}")
    try:
        manifest = Manifest.model_validate(_parse_yaml(manifest_path))
    except ValidationError as e:
        raise RegistryError(f"_manifest.yaml 校验失败: {e.errors()[0]['loc']}: {e.errors()[0]['msg']}") from e

    objects: dict[str, ObjectType] = {}
    links: dict[str, LinkType] = {}
    fingerprints: dict[str, str] = {}
    file_names = [mf.file for mf in manifest.files]
    pending = set()  # 先收集全部声明的 api_name（跨文件前向引用）
    parsed: list[tuple[str, DomainFile]] = []
    for name in file_names:
        path = registry_dir / name
        if not path.exists():
            raise RegistryError(f"清单引用的文件不存在: {name}")
        domain = _validate_domain_file(path, _parse_yaml(path))
        parsed.append((name, domain))
        pending.update(o.api_name for o in domain.object_types)
    fingerprints["_manifest.yaml"] = _read_fingerprint(manifest_path)

    for name, domain in parsed:
        for obj in domain.object_types:
            if obj.api_name in objects:
                raise RegistryError(f"{name}: 对象类型 '{obj.api_name}' 重复注册")
            if obj.pk.column not in {p.name for p in obj.properties}:
                raise RegistryError(f"{name}: 对象 {obj.api_name} 的 pk 列 '{obj.pk.column}' 未在属性中声明")
            hidden_leak = [p.name for p in obj.properties if p.hidden and (p.filterable or p.searchable)]
            if hidden_leak:
                raise RegistryError(f"{name}: 对象 {obj.api_name} 的 hidden 属性 {hidden_leak} 不能同时 filterable/searchable")
            objects[obj.api_name] = obj
        for lt in domain.link_types:
            if lt.api_name in links:
                raise RegistryError(f"{name}: 链接类型 '{lt.api_name}' 重复注册")
            links[lt.api_name] = lt
        fingerprints[name] = _read_fingerprint(registry_dir / name)
        _check_cross_refs(registry_dir / name, objects, links, pending - set(objects))

    if not objects:
        raise RegistryError("注册表为空：未声明任何对象类型")
    return Registry(manifest, objects, links, fingerprints, registry_version=manifest.registry_version)


class RegistryStore:
    """进程内单例 + 热重载（指纹比对 → 原子替换 → 版本递增）。"""

    def __init__(self, registry_dir: Path = REGISTRY_DIR) -> None:
        self._dir = registry_dir
        self._registry: Registry | None = None
        self._lock = threading.Lock()

    def current_fingerprint(self) -> str:
        """当前磁盘内容聚合指纹（未加载文件时也可靠）。"""
        parts: list[str] = []
        for f in sorted(self._dir.glob("*.yaml")):
            parts.append(f"{f.name}:{_read_fingerprint(f)}")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def get(self) -> Registry:
        """读当前注册表（磁盘变化时自动重载；重载失败保留旧版本并抛错由调用方决定）。"""
        with self._lock:
            if self._registry is not None and self._registry.file_fingerprints and self.current_fingerprint() == self._agg(self._registry):
                return self._registry
            fresh = load_registry(self._dir)
            if self._registry is not None:
                fresh.registry_version = self._registry.registry_version + 1
            self._registry = fresh
            return self._registry

    @staticmethod
    def _agg(registry: Registry) -> str:
        return hashlib.sha256("|".join(f"{k}:{v}" for k, v in sorted(registry.file_fingerprints.items())).encode()).hexdigest()


_store: RegistryStore | None = None


def get_registry_store() -> RegistryStore:
    global _store
    if _store is None:
        _store = RegistryStore()
    return _store


def get_registry() -> Registry:
    """逐调用入口（D4：gateway 与 MCP 进程各自调用，指纹一致 → 版本一致）。"""
    return get_registry_store().get()
