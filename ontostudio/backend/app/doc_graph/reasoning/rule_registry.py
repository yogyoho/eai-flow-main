"""推理规则注册表——YAML 规则的 fail-closed 加载 + SHA 指纹热重载.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-reasoning-rules-design.md §3/§4/§5。
镜像 ontology/registry.py 模式（pydantic + manifest + 指纹热重载 + 失败保旧快照）。
规则引用的 predicate/etype 有两层 fail-closed 校验：
- 存在性: ⊆ registry doc_graph.yaml 枚举（关系谓词 = graph_relation.predicate enum;
  类型谓词 = graph_entity.etype enum, 形如 ``mine(?M)``）；派生谓词（org_involved_in）
  也须入枚举——派生事实要能被查询。
- 域归属: ⊆ rule.domain 的域谓词/域 etype 集（跨域拒绝, spec §5）。单一真源 =
  schemas.py 的 *Extraction ClassVar（与抽取侧 _check_domain_and_refs 同源强制）;
  派生谓词无抽取角色, 由 DERIVED_PREDICATE_DOMAIN 归入宿主域。
- 模式解析复用 facade._compile_pattern / RuleSyntaxError（单一真源，避免两处语法漂移）。

与 registry.RegistryStore 的一处有意偏差: 热重载失败且已有旧快照时**返回旧快照继续服务**
（evaluate_rules 是读侧现算工具，宁可旧规则不中断），错误记入 store.last_error 并打
warning 日志；冷加载失败照常抛 RulesError。registry.py 则是抛错由调用方决定。
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.doc_graph.reasoning.facade import RuleSyntaxError, _compile_pattern
from app.doc_graph.schemas import BidExtraction, EiaExtraction, ExtractionPayload
from app.ontology.registry import Registry, get_registry, load_registry

RULES_DIR = Path(__file__).parent.parent / "rules"

logger = logging.getLogger(__name__)


class RulesError(Exception):
    """规则注册表加载失败（fail-closed）。"""


# 域 → 抽取模型: 域谓词/etype 单一真源 = schemas.py 的 *Extraction ClassVar
# （domain_predicates/domain_etypes, 与抽取侧同源, schemas 改动自动跟随）;
# 新域 = schemas 加 *Extraction 子类 + 此处登记一行。
_DOMAIN_EXTRACTIONS: dict[str, type[ExtractionPayload]] = {
    "bid": BidExtraction,
    "eia": EiaExtraction,
}

# 派生谓词无抽取角色, 不入 schemas 角色表（写侧抽取契约不受影响）——在此归入宿主域,
# 使派生事实可被同域规则引用/派生（org_involved_in 由 eia 域规则派生与消费）。
DERIVED_PREDICATE_DOMAIN: dict[str, str] = {"org_involved_in": "eia"}


class RuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool = True
    domain: str
    when: list[str] = Field(min_length=1)
    derive: str
    note: str = ""


class RuleFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str


class RulesManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    rules_version: int = 1  # 内存单调递增起点；实际版本由加载器维护
    hot_reload: bool = True  # declarative-only（镜像 registry.Manifest 同款死字段）——RuleStore 无条件指纹热重载, false 不会关闭
    files: list[RuleFileEntry] = Field(min_length=1)


class RulesFile(BaseModel):
    """单个规则 YAML 文件根模型。"""

    model_config = ConfigDict(extra="forbid")

    rules: list[RuleModel] = []


class RulesSnapshot:
    """不可变快照：加载完成后整体替换，不做增量变异。"""

    def __init__(
        self,
        manifest: RulesManifest,
        rules: tuple[RuleModel, ...],
        file_fingerprints: dict[str, str],
        rules_version: int,
        source_registry_version: int,
    ) -> None:
        self.manifest = manifest
        self.rules = rules
        self.file_fingerprints = file_fingerprints
        self.rules_version = rules_version
        self.source_registry_version = source_registry_version

    @property
    def enabled_rules(self) -> list[RuleModel]:
        """enabled 开关过滤在注册表层（facade 不管 enabled）。"""
        return [r for r in self.rules if r.enabled]


def _read_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        mark = getattr(getattr(e, "problem_mark", None), "line", None)
        loc = f"{path.name}:{mark + 1}" if mark is not None else path.name
        raise RulesError(f"YAML 语法错误: {loc}: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RulesError(f"{path.name}: 顶层必须是 mapping, 得到 {type(data).__name__}")
    return data


def _registry_vocab(reg: Registry) -> tuple[set[str], set[str]]:
    """从 registry 提取 (关系谓词枚举, etype 枚举)——doc_graph.yaml 是唯一真源。"""
    rel = reg.object_types.get("graph_relation")
    ent = reg.object_types.get("graph_entity")
    if rel is None or ent is None:
        raise RulesError("registry 缺少 graph_relation/graph_entity 对象——谓词/etype 枚举真源不存在")
    pred_enum = next((p.enum for p in rel.properties if p.name == "predicate"), None)
    etype_enum = next((p.enum for p in ent.properties if p.name == "etype"), None)
    if pred_enum is None or etype_enum is None:
        raise RulesError("registry graph_relation.predicate / graph_entity.etype 属性缺 enum——枚举真源不存在")
    return set(pred_enum), set(etype_enum)


def _domain_vocab(rule: RuleModel) -> tuple[set[str], set[str]]:
    """规则所属域的 (谓词集, etype集); 未知域 fail-closed 拒绝（不静默放行）。"""
    cls = _DOMAIN_EXTRACTIONS.get(rule.domain)
    if cls is None:
        raise RulesError(f"规则 {rule.name}: domain '{rule.domain}' 未注册（已知域: {sorted(_DOMAIN_EXTRACTIONS)}）")
    derived = {p for p, d in DERIVED_PREDICATE_DOMAIN.items() if d == rule.domain}
    return set(cls.domain_predicates) | derived, set(cls.domain_etypes)


def _check_rule(file_name: str, rule: RuleModel, reg_vocab: tuple[set[str], set[str]]) -> None:
    """规则 when/derive 谓词的两层校验（fail-closed，带文件名+规则名定位）：

    1. 存在性 ⊆ registry doc_graph.yaml 枚举（关系谓词/etype 全集）;
    2. 域归属 ⊆ rule.domain 域谓词/域 etype 集（跨域拒绝, spec §5——与抽取侧按域强制同源）。
    """
    reg_predicates, reg_etypes = reg_vocab
    known = reg_predicates | reg_etypes
    d_predicates, d_etypes = _domain_vocab(rule)
    allowed = d_predicates | d_etypes

    def _pred_of(pattern: str) -> str:
        try:
            return _compile_pattern(pattern).predicate
        except RuleSyntaxError as e:
            raise RulesError(f"{file_name}: 规则 {rule.name}: {e}") from e

    def _check_pred(side: str, pred: str) -> None:
        if pred not in known:
            raise RulesError(f"{file_name}: 规则 {rule.name}: {side}谓词 '{pred}' 未注册（graph_relation.predicate / graph_entity.etype 枚举外）")
        if pred not in allowed:
            raise RulesError(f"{file_name}: 规则 {rule.name}: {side}谓词 '{pred}' 不属于域 '{rule.domain}'（跨域, 域内允许: {sorted(allowed)}）")

    for pattern in rule.when:
        _check_pred("when", _pred_of(pattern))
    _check_pred("derive", _pred_of(rule.derive))


def load_rules(rules_dir: Path = RULES_DIR, reg: Registry | None = None) -> RulesSnapshot:
    """全量加载 + 校验。任何失败 fail-closed 抛 RulesError（带文件名）。"""
    manifest_path = rules_dir / "manifest.yaml"
    if not manifest_path.exists():
        raise RulesError(f"清单不存在: {manifest_path}")
    try:
        manifest = RulesManifest.model_validate(_parse_yaml(manifest_path))
    except ValidationError as e:
        raise RulesError(f"manifest.yaml 校验失败: {e.errors()[0]['loc']}: {e.errors()[0]['msg']}") from e

    reg = reg if reg is not None else load_registry()
    vocab = _registry_vocab(reg)

    rules: list[RuleModel] = []
    fingerprints: dict[str, str] = {}
    seen: set[str] = set()
    for mf in manifest.files:
        path = rules_dir / mf.file
        if not path.exists():
            raise RulesError(f"清单引用的文件不存在: {mf.file}")
        try:
            rfile = RulesFile.model_validate(_parse_yaml(path))
        except ValidationError as e:
            loc0 = ".".join(str(x) for x in (e.errors()[0]["loc"] if e.errors() else []))
            raise RulesError(f"schema 校验失败: {mf.file}: {loc0}: {e.errors()[0]['msg'] if e.errors() else e}") from e
        for rule in rfile.rules:
            if rule.name in seen:
                raise RulesError(f"{mf.file}: 规则名 '{rule.name}' 重复注册")
            _check_rule(mf.file, rule, vocab)
            seen.add(rule.name)
            rules.append(rule)
        fingerprints[mf.file] = _read_fingerprint(path)
    fingerprints["manifest.yaml"] = _read_fingerprint(manifest_path)

    if not rules:
        raise RulesError("规则注册表为空：未声明任何规则")
    return RulesSnapshot(manifest, tuple(rules), fingerprints, rules_version=manifest.rules_version, source_registry_version=reg.registry_version)


class RuleStore:
    """进程内单例 + 热重载（指纹比对 → 原子替换 → 版本递增）。

    重载条件 = 规则文件指纹变化 **或** registry 版本变化（枚举收缩时重校验，
    fail-closed 方向）。重载失败且已有旧快照 → 保留旧快照继续服务（last_error 可观测）。
    """

    def __init__(self, rules_dir: Path = RULES_DIR, reg_provider: Callable[[], Registry] | None = None) -> None:
        self._dir = rules_dir
        # 默认走 get_registry（指纹缓存）；注入 load_registry 会让每次 get() 全量重解析 6 个域文件
        self._reg_provider: Callable[[], Registry] = reg_provider or get_registry
        self._snapshot: RulesSnapshot | None = None
        self._lock = threading.Lock()
        self.last_error: str | None = None

    def current_fingerprint(self) -> str:
        """当前磁盘内容聚合指纹（未加载文件时也可靠）。"""
        parts: list[str] = []
        for f in sorted(self._dir.glob("*.yaml")):
            parts.append(f"{f.name}:{_read_fingerprint(f)}")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def get(self) -> RulesSnapshot:
        """读当前规则快照（磁盘/枚举变化时自动重载；重载失败保留旧快照继续服务）。"""
        with self._lock:
            reg = self._reg_provider()
            snap = self._snapshot
            if snap is not None and snap.file_fingerprints and self.current_fingerprint() == self._agg(snap) and snap.source_registry_version == reg.registry_version:
                self.last_error = None  # 所服务快照与磁盘一致 → 此前重载失败记录已过时
                return snap
            try:
                fresh = load_rules(self._dir, reg=reg)
            except RulesError as e:
                if snap is None:
                    raise
                self.last_error = str(e)
                logger.warning("规则热重载失败，保留旧快照继续服务: %s", e)
                return snap
            self.last_error = None
            if snap is not None:
                fresh.rules_version = snap.rules_version + 1
            self._snapshot = fresh
            return fresh

    @staticmethod
    def _agg(snapshot: RulesSnapshot) -> str:
        return hashlib.sha256("|".join(f"{k}:{v}" for k, v in sorted(snapshot.file_fingerprints.items())).encode()).hexdigest()


_store: RuleStore | None = None


def get_rules_store() -> RuleStore:
    global _store
    if _store is None:
        _store = RuleStore()
    return _store


def get_rules() -> RulesSnapshot:
    """逐调用入口（D4：gateway 与 MCP 进程各自调用，指纹一致 → 版本一致）。"""
    return get_rules_store().get()
