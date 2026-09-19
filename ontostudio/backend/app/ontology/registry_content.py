"""registry 内容管理端点（建模器 MVP 后端, EAI-CUSTOM 2026-09-20）——读 / 校验 / 原子写+热重载.

- GET  /files            清单内域文件列表
- GET  /content?file=    原文 + 结构化摘要（类/谓词/公理，建模器三栏数据源）
- POST /validate         草稿校验（临时目录全量 load_registry，fail-closed，不落盘）
- PUT  /content          校验通过 → 原子写 → RegistryStore 指纹热重载

安全：文件名白名单（^[A-Za-z0-9_-]+\\.yaml$）；写前强制 dry 校验；原子写（tmp+replace）。
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, require_permission
from app.ontology.kernel.iri import etype_to_class_name
from app.ontology.registry import (
    REGISTRY_DIR,
    RegistryError,
    get_registry,
    get_registry_store,
    load_registry,
)

router = APIRouter(prefix="/api/extensions/ontology/registry-content", tags=["ontology-registry"])

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-]+\.yaml$")


def _guard_file(file: str) -> str:
    if not _SAFE_NAME.match(file):
        raise HTTPException(status_code=400, detail=f"非法文件名: {file!r}")
    return file


def _manifest_files() -> list[str]:
    manifest = REGISTRY_DIR / "_manifest.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    return [m["file"] for m in data.get("files", [])]


def _registry_summary(registry) -> dict:  # noqa: ANN001 - Registry
    """结构化摘要：每域 {namespace, classes[{name,label,definition,parents,hasKey,etypes}], predicates, axioms}。"""
    domains: dict[str, dict] = {}
    class_meta: dict[tuple[str, str], dict] = {}

    for ot in registry.object_types.values():
        d = domains.setdefault(
            ot.domain,
            {"namespace": registry.namespaces_by_domain.get(ot.domain, f"https://ontology.eai-flow.com/{ot.domain}#"), "classes": [], "predicates": []},
        )
        etype_prop = next((p for p in ot.properties if p.name == "etype" and p.enum), None)
        pred_prop = next((p for p in ot.properties if p.name == "predicate" and p.enum), None)
        if etype_prop:
            for etype in etype_prop.enum:
                m = (ot.etype_classes or {}).get(etype)
                cname = m.class_name if m and m.class_name else etype_to_class_name(etype)
                key = (ot.domain, cname)
                if key not in class_meta:
                    class_meta[key] = {
                        "name": cname,
                        "label": (m.label if m and m.label else etype),
                        "definition": (m.definition if m and m.definition else ""),
                        "parents": list(m.sub_class_of) if m else [],
                        "hasKey": list(m.has_key) if m else [],
                        "etypes": [],
                    }
                    d["classes"].append(class_meta[key])
                if etype not in class_meta[key]["etypes"]:
                    class_meta[key]["etypes"].append(etype)
        if pred_prop:
            d["predicates"] = sorted(set(d["predicates"]) | set(pred_prop.enum))

    # formal 段引用的谓词/链自动入词表（与 collect_vocabularies 同语义）
    for domain, formal in registry.formal_by_domain.items():
        if domain not in domains:
            continue
        preds = domains[domain]["predicates"]
        for ax in formal.property_chains:
            preds.extend([ax.derived, *ax.chain])
        preds.extend(formal.transitive)
        for pair in formal.inverse:
            preds.extend(pair.pair)
        domains[domain]["predicates"] = sorted(set(preds))

    # parents 归位（sub_class_of 目标类已在本域声明）
    for (domain, cname), entry in class_meta.items():
        if entry["parents"]:
            d = domains[domain]
            for c in d["classes"]:
                if c["name"] == cname:
                    c["parents"] = entry["parents"]
                    break

    axioms = {
        domain: {
            "property_chains": [ax.model_dump() for ax in f.property_chains],
            "transitive": list(f.transitive),
            "inverse": [p.pair for p in f.inverse],
            "disjoint": list(f.disjoint),
        }
        for domain, f in registry.formal_by_domain.items()
    }
    return {"domains": domains, "axioms": axioms}


@router.get("/files")
async def list_registry_files(_: CurrentUser = Depends(require_permission("system:access"))):
    return {"files": _manifest_files()}


@router.get("/content")
async def get_registry_content(
    file: str = Query(...),
    _: CurrentUser = Depends(require_permission("system:access")),
):
    _guard_file(file)
    path = REGISTRY_DIR / file
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file}")
    registry = get_registry()
    return {
        "file": file,
        "raw": path.read_text(encoding="utf-8"),
        "summary": _registry_summary(registry),
        "fingerprint": get_registry_store().current_fingerprint()[:8],
        "registry_version": registry.registry_version,
    }


def _validate_draft(file: str, content: str) -> tuple[bool, list[str], object | None]:
    """草稿 → 临时目录全量 load_registry（其余文件用现网副本，交叉引用同真）."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for f in _manifest_files():
            if f != file:
                (td_path / f).write_bytes((REGISTRY_DIR / f).read_bytes())
        (td_path / "_manifest.yaml").write_bytes((REGISTRY_DIR / "_manifest.yaml").read_bytes())
        (td_path / file).write_text(content, encoding="utf-8")
        try:
            registry = load_registry(td_path)
        except RegistryError as e:
            return False, [str(e)], None
        return True, [], registry


@router.post("/validate")
async def validate_registry_content(
    payload: dict,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    file = str(payload.get("file", ""))
    content = payload.get("content", "")
    _guard_file(file)
    ok, errors, registry = _validate_draft(file, content)
    return {
        "ok": ok,
        "errors": errors,
        "summary": _registry_summary(registry) if registry else None,
    }


@router.put("/content")
async def save_registry_content(
    payload: dict,
    _: CurrentUser = Depends(require_permission("system:access")),
):
    file = str(payload.get("file", ""))
    content = str(payload.get("content", ""))
    _guard_file(file)
    ok, errors, _registry = _validate_draft(file, content)
    if not ok:
        raise HTTPException(status_code=422, detail={"errors": errors})
    # 原子写（tmp + os.replace）
    target = REGISTRY_DIR / file
    tmp = target.with_suffix(".yaml.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)
    store = get_registry_store()
    registry = store.get()  # 指纹变化 → 热重载
    return {
        "ok": True,
        "fingerprint": store._agg(registry)[:8],
        "registry_version": registry.registry_version,
    }
