"""kernel P4 golden 测试：SHACL 校验 + 国标 GB/T 48000.3 符合性套件（spec §5/§6 P4）.

- SHACL：干净数据 conforms；注入违规（status 非法）→ 非符合 + 报告五字段完整；
  Mention 二选一（xone）；MergeAudit 字段完备。
- 国标五项套件：合法 mini 词表全绿；违规注入（坏命名空间/悬空 subClassOf）逐项失败。
纯单元零 DB 依赖（复用 P1 mini 词表 + P2/P3 写路径）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ontology.kernel.compile import collect_vocabularies
from app.ontology.kernel.conformance import all_passed, run_conformance
from app.ontology.kernel.graph_ops import add_mention, merge_entities, upsert_entity
from app.ontology.kernel.infer import refresh_schema
from app.ontology.kernel.store import OxStore
from app.ontology.kernel.validate import run_shacl
from app.ontology.registry import load_registry
from tests.test_kernel_p1 import MINI_YAML

UUID_SRC = "11111111-1111-1111-1111-111111111111"
UUID_TGT = "33333333-3333-3333-3333-333333333333"
UUID_MENT = "55555555-5555-5555-5555-555555555555"


@pytest.fixture()
def env(tmp_path: Path):
    (tmp_path / "_manifest.yaml").write_text("schema_version: 1\nfiles:\n  - file: mini.yaml\n", encoding="utf-8")
    (tmp_path / "mini.yaml").write_text(MINI_YAML, encoding="utf-8")
    registry = load_registry(tmp_path)
    vocab = collect_vocabularies(registry)["mini"]
    store = OxStore()
    refresh_schema(store, registry)
    yield store, vocab, registry
    store.close()


def _seed_valid(store, vocab):
    """干净数据：两个实体 + 一次真实合并（含审计）+ 一条证据。"""
    src = upsert_entity(store, vocab, class_name="Org", entity_uuid=UUID_SRC, etype="org", canonical_name="山西煤矿机械制造有限公司", confidence=0.9)
    tgt = upsert_entity(store, vocab, class_name="Org", entity_uuid=UUID_TGT, etype="org", canonical_name="山西煤机集团", confidence=0.94)
    audit = merge_entities(store, vocab, source_iri=src, target_iri=tgt, actor="测试", reason="golden")
    mention = add_mention(store, vocab, mention_uuid=UUID_MENT, entity_iri=tgt, quote="标书 L412")
    return src, tgt, audit, mention


# ---- SHACL ----


def test_shacl_clean_data_conforms(env):
    store, vocab, registry = env
    _seed_valid(store, vocab)
    report = run_shacl(store, registry)
    assert report.conforms, f"干净数据不应有违规: {report.violations[:3]}"
    assert report.violations == []


def test_shacl_bad_status_violation_report(env):
    store, vocab, registry = env
    bad = upsert_entity(store, vocab, class_name="Project", entity_uuid="22222222-2222-2222-2222-222222222222", etype="project", canonical_name="横城煤矿项目", confidence=0.9, status="archived")
    report = run_shacl(store, registry)
    assert not report.conforms
    status_violations = [v for v in report.violations if v["path"] and v["path"].endswith("status")]
    assert status_violations, "非法 status 必须触发违规"
    assert any(v["focusNode"] == bad for v in status_violations)
    # 报告五字段齐备（国标 §5.3 结构化输出形态）
    assert all(v["focusNode"] and v["message"] and v["severity"] and v["source"] for v in report.violations)


def test_shacl_rejected_status_conforms(env):
    """Task 3（动作层设计 §1.3）：rejected 是合法 status——驳回动作的落库值, 必须过 SHACL。

    与 test_shacl_bad_status_violation_report 成对：只钉负路径时，「枚举被改窄（删掉 rejected）」
    不会有任何测试变红，而 rejected 实体一旦判违规, 驳回后的图重投影就当场自相矛盾。
    """
    store, vocab, registry = env
    upsert_entity(store, vocab, class_name="Project", entity_uuid="66666666-6666-6666-6666-666666666666", etype="project", canonical_name="横城煤矿项目", confidence=0.9, status="rejected")
    report = run_shacl(store, registry)
    assert report.conforms, f"rejected 是合法 status: {report.violations[:3]}"


def test_shacl_status_message_lists_full_enum(env):
    """违规提示必须列全枚举（含 rejected）——操作者据此才能改正, 少列即误导。

    钉的是 validate.py 的 `_severity` 文案（负路径那条测试只断言「有违规」, 文案删掉 /rejected
    照样全绿）。
    """
    store, vocab, registry = env
    upsert_entity(store, vocab, class_name="Project", entity_uuid="77777777-7777-7777-7777-777777777777", etype="project", canonical_name="横渠煤矿项目", confidence=0.9, status="archived")
    report = run_shacl(store, registry)
    messages = [v["message"] for v in report.violations if v["path"] and v["path"].endswith("status")]
    assert messages, "非法 status 必须触发违规"
    assert all("rejected" in m for m in messages), messages


def test_shacl_mention_requires_target(env):
    store, vocab, registry = env
    # graph_ops 层已挡（二选一守卫），此处直写绕过 → SHACL 兜底
    from pyoxigraph import Quad

    from app.ontology.kernel.store import ASSERTED_GRAPH
    from app.ontology.kernel.vocab import C_MENTION, nn

    orphan = f"{vocab.scheme.namespace}mention/orphan-0000"
    store._store.add(Quad(nn(orphan), nn("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), nn(C_MENTION), nn(ASSERTED_GRAPH)))
    report = run_shacl(store, registry)
    assert not report.conforms, "无指向 mention 必须被 sh:xone 拦下"


def test_shacl_merge_audit_complete(env):
    store, vocab, registry = env
    _seed_valid(store, vocab)
    report = run_shacl(store, registry)
    assert report.conforms, "MergeAudit 审计节点必须满足字段完备形状"


# ---- 国标五项符合性套件 ----


def test_conformance_all_green(env):
    store, vocab, registry = env
    _seed_valid(store, vocab)
    results = run_conformance(store, registry)
    assert all_passed(results), f"五项应全绿: {[r for r in results if not r.passed]}"
    clauses = {r.clause for r in results}
    assert clauses == {"条款 5.4", "条款 5.3", "附录 A", "条款 9"}


def test_conformance_c5_detects_namespace_conflict(tmp_path: Path):
    """§9：两域声明同一命名空间 → C5 必须抓到跨域冲突。"""
    header = "schema_version: 1\nfiles:\n  - file: mini.yaml\n  - file: mini2.yaml\n"
    (tmp_path / "_manifest.yaml").write_text(header, encoding="utf-8")
    (tmp_path / "mini.yaml").write_text(MINI_YAML, encoding="utf-8")
    mini2 = MINI_YAML.replace("domain: mini", "domain: mini2").replace("api_name: thing", "api_name: thing2").replace("table: mini_things", "table: mini2_things")  # 同一命名空间（故意）
    (tmp_path / "mini2.yaml").write_text(mini2, encoding="utf-8")
    registry = load_registry(tmp_path)
    store = OxStore()
    refresh_schema(store, registry)
    results = run_conformance(store, registry)
    c5 = next(r for r in results if r.clause == "条款 9")
    assert not c5.passed, "同命名空间两域必须触发冲突"
    assert "跨域冲突" in c5.detail
    store.close()


def test_conformance_real_registry_green(tmp_path: Path):
    """真实 5 域 registry：空断言图 → 五项全绿（合规基线）。"""
    registry = load_registry()
    store = OxStore()
    refresh_schema(store, registry)
    results = run_conformance(store, registry)
    assert all_passed(results), f"真实 registry 五项应全绿: {[r for r in results if not r.passed]}"
