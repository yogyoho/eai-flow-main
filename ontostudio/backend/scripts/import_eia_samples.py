#!/usr/bin/env python3
"""EIA 样例实体注册表 → doc_graph eia 域批量导入（EAI-CUSTOM: doc-graph 计划 Task 3）.

把 skills/public/coal-eia-report/references/sample_entities/{slug}.json 实体注册表转换为
EiaExtraction payload, 经 ingest_extraction 入库（dg_entities/dg_mentions/dg_relations）。
幂等性: ingest 仅对实体幂等 upsert（uq_dg_entities_natural）, mentions/relations 是盲 INSERT——
本脚本以 document_id 重入守卫补齐（_already_ingested, 命中即跳过该样例; --force 显式绕过重导, 会再翻倍）。

隐私硬排除: generic_terms / aux.people / aux.doc_numbers 三桶永不入库——_build_payload 只读
entities 下 5 个实体桶（projects/mines/orgs/places/sensitive）, 测试钉死（tests/test_import_eia_samples.py）。

大纲关系: 若 {outlines-dir}/{slug}-outline.md 存在, 解析其头部结构化行合成 org_compiles/org_commissions/
org_develops_project 关系边（subject=org 实体, object=entities.projects[0]）。识别格式: `- **编制单位**: X`、
非粗体 `- 编制单位: X`、表格行 `| 编制单位 | X |`、`标签 = 值`（org_hint 行）, 同义词 委托单位/委托方→commissions、
开发主体/矿区主体→develops; 复合标签（如 原环评/后评价编制单位）不解析并计入 skip 报告。
projects 为空的样例只导实体, 不产关系边（报告计数）。

Run:
    cd ontostudio/backend && PYTHONPATH=. uv run python scripts/import_eia_samples.py --dry-run   # 统计, 不触库
    cd ontostudio/backend && PYTHONPATH=. uv run python scripts/import_eia_samples.py             # 真入库（需 extensions 库 dg_* 表）

容器内运行（S1 Task 3 容器化前的旧路径写法; gateway 无 .wolf 挂载, 默认 --outlines-dir 不可达）: 先把大纲 digest 拷进可达路径再显式传参, 如
    docker cp .wolf/tmp/eia-samples deer-flow-gateway:/tmp/eia-samples
    docker exec deer-flow-gateway python /app/backend/scripts/import_eia_samples.py --outlines-dir /tmp/eia-samples
（EAI-CUSTOM 迁移注: 脚本已迁 ontostudio/backend/scripts/, 上行 gateway 容器路径在 Task 2/3 切换后由 ontostudio 容器路径替代;
默认值不改——host 主场景优先。）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402 (sys.path 先插入)

from app.doc_graph.schemas import EiaExtraction  # noqa: E402 (只依赖 schemas, 不触 ingest/DB)

# EAI-CUSTOM(2026-09-17 迁出独立): scripts 由 backend/ 深一届至 ontostudio/backend/ → repo root = parents[3]
_REPO = Path(__file__).resolve().parents[3]

# 桶 → etype（顺序即实体产出顺序; 隐私三桶 generic_terms/aux 不在此表 = 结构性排除）
_BUCKET_ETYPE = {"projects": "project", "mines": "mine", "orgs": "org", "places": "place", "sensitive": "sensitive_point"}

# 大纲头部标签（含同义词）→ 谓词角色; dict 顺序决定关系边产出顺序（compiles → commissions → develops）
_FIELD_PREDICATE = {"compiles": "org_compiles_project", "commissions": "org_commissions_project", "develops": "org_develops_project"}
_HEADER_FIELDS = {"编制单位": "compiles", "委托单位": "commissions", "委托方": "commissions", "开发主体": "develops", "矿区主体": "develops"}
# 粗体可选; 负向后行断言排除复合标签（如 原环评/后评价编制单位——语义指原环评非本文档, 计入 skip 报告）;
# 分隔符 : ： =（org_hint 行） |（表格行）
_LABEL_RE = re.compile(r"(?<![一-鿿A-Za-z0-9])\*{0,2}(编制单位|委托单位|委托方|开发主体|矿区主体)\*{0,2}\s*[:：=|]\s*")
_BRACKET_RE = re.compile(r"[（(][^（）()]*[)）]")
_EXTRACTED_BY = "eia-sample-import"


def _entity(name: str, etype: str, document_id: str, source: str) -> dict:
    return {"etype": etype, "name": name, "mention": {"document_id": document_id, "quote": "", "doc_span": {"source": source}}}


def _build_payload(entities_json: dict, slug: str, project_name: str | None) -> dict:
    """sample_entities JSON → EiaExtraction 兼容 dict（纯函数）.

    只读 entities 下 5 个实体桶; generic_terms / aux(people/doc_numbers/privacy_notes) 硬排除, 永不产出实体。
    project_name 供大纲关系边作 object——给出时必须已在实体清单声明（fail-closed 预检, 防悬空引用）。
    """
    entities: list[dict] = []
    for bucket, etype in _BUCKET_ETYPE.items():
        seen: set[str] = set()
        for raw in entities_json.get("entities", {}).get(bucket) or []:
            name = str(raw).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            entities.append(_entity(name, etype, f"eia-sample:{slug}", "sample_entities"))
    if project_name is not None and not any(e["name"] == project_name for e in entities):
        raise ValueError(f"[{slug}] project_name {project_name!r} 未在实体清单声明——关系边会引用未声明实体")
    return {"domain": "eia", "extracted_by": _EXTRACTED_BY, "entities": entities, "relations": []}


def _parse_outline_header(text: str) -> dict:
    """解析 digest 头部结构化行 → {"compiles": [...], "commissions": [...], "develops": [...]}（纯函数）.

    识别格式（评审 Fix1 扩宽）: 粗体/非粗体标签行 `- **编制单位**: X（注记）；**委托单位**: Y`、
    表格行 `| 编制单位 | X |`、`标签 = 值`（org_hint 行）; 同义词 委托单位/委托方、开发主体/矿区主体。
    解析前先整行剥全/半角括号注记——既清值内注记, 也处理 `编制单位(委托方:...): X` 嵌套并防
    `（编制单位，x4）` 假标签; 值以 ；;。 为字段终止符, 顿号多值。
    """
    parsed: dict[str, list[str]] = {key: [] for key in _FIELD_PREDICATE}
    for line in text.splitlines():
        line = _BRACKET_RE.sub("", line)
        labels = list(_LABEL_RE.finditer(line))
        for i, m in enumerate(labels):
            end = labels[i + 1].start() if i + 1 < len(labels) else len(line)
            segment = re.split(r"[；;。]", line[m.end() : end], 1)[0].replace("|", " ")
            parsed[_HEADER_FIELDS[m.group(1)]].extend(p.strip().lstrip("=:： \t") for p in segment.split("、") if p.strip())
    return {key: list(dict.fromkeys(vals)) for key, vals in parsed.items()}


def _outline_relations(parsed: dict, project_name: str) -> tuple[list[dict], list[dict]]:
    """大纲头部解析结果 → (待并入的 org 实体清单, 关系边清单)（纯函数）.

    compiles→org_compiles_project / commissions→org_commissions_project / develops→org_develops_project;
    subject=org 实体名, object=project_name。org 跨角色去重（同名一实体可挂多边）。
    document_id 直取 parsed["document_id"]（主流程注入 f"eia-sample:{slug}"）, 缺键 KeyError=fail-closed。
    """
    document_id = parsed["document_id"]
    orgs: list[dict] = []
    relations: list[dict] = []
    seen: set[str] = set()
    for field, predicate in _FIELD_PREDICATE.items():
        for org in parsed.get(field) or []:
            if org not in seen:
                seen.add(org)
                orgs.append(_entity(org, "org", document_id, "outline_header"))
            relations.append({"predicate": predicate, "subject": org, "object": project_name, "mention": {"document_id": document_id, "quote": "", "doc_span": {"source": "outline_header"}}})
    return orgs, relations


def _entity_files(entities_dir: Path, slug_filter: str | None) -> list[Path]:
    files = sorted(p for p in entities_dir.glob("*.json") if p.name != "_index.json")
    if slug_filter:
        files = [p for p in files if p.stem == slug_filter]
        if not files:
            raise SystemExit(f"ERROR: --slug {slug_filter!r} 在 {entities_dir} 下无对应 JSON")
    if not files:
        raise SystemExit(f"ERROR: {entities_dir} 下无样例 JSON")
    return files


def _already_ingested(document_id: str) -> bool:
    """重入守卫: 该 document_id 在 dg_mentions 已有任一 mention 视为该样例已导入.

    EAI-CUSTOM: ingest_extraction 对 mentions/relations 盲 INSERT（仅实体幂等）, 批量脚本重跑
    会整样例翻倍; 以 document_id 判重使重跑零副作用（同 crash 中断后的补跑也只补缺失样例）。
    连接模式照抄 ingest_extraction（NullPool + _ext_url 单一真源）, 延迟 import 保持 dry-run 零 DB 依赖。
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.ontology.connectors import _ext_url

    async def _query() -> bool:
        engine = create_async_engine(_ext_url(), poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                row = (await conn.execute(text("SELECT 1 FROM dg_mentions WHERE document_id = :doc LIMIT 1"), {"doc": document_id})).first()
                return row is not None
        finally:
            await engine.dispose()

    return bool(asyncio.run(_query()))


def _process(path: Path, args: argparse.Namespace, outlines_usable: bool) -> dict:
    """单样例: 读 JSON → _build_payload → 大纲关系合成 → fail-closed 校验 → (非 dry-run) 入库."""
    slug = path.stem
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"ERROR: [{slug}] 样例 JSON 读取/解析失败: {e}") from e
    buckets = data.get("entities", {})
    projects = [str(p).strip() for p in buckets.get("projects") or [] if str(p).strip()]
    project_name = projects[0] if projects else None  # project_name 策略: entities.projects[0]
    payload = _build_payload(data, slug, project_name)

    outline_status = "skip"
    if outlines_usable:
        outline_path = args.outlines_dir / f"{slug}-outline.md"
        if not outline_path.exists():
            outline_status = "no-file"
        elif project_name is None:
            outline_status = "no-project"
        else:
            parsed = _parse_outline_header(outline_path.read_text(encoding="utf-8"))
            parsed["document_id"] = f"eia-sample:{slug}"
            if not any(parsed[field] for field in _FIELD_PREDICATE):
                outline_status = "no-match"
            else:
                orgs, relations = _outline_relations(parsed, project_name)
                existing = {e["name"] for e in payload["entities"] if e["etype"] == "org"}  # 去重限定 org 桶, 防跨 etype 撞名绑错边
                added = [o for o in orgs if o["name"] not in existing]
                payload["entities"].extend(added)
                payload["relations"].extend(relations)
                outline_status = f"+{len(added)}org/+{len(relations)}rel"

    try:
        model = EiaExtraction.model_validate(payload)
    except ValidationError as e:
        raise SystemExit(f"ERROR: [{slug}] EiaExtraction 校验失败（fail-closed, 不静默跳过）: {e}") from e

    ingested = None
    skipped_existing = False
    if not args.dry_run:
        if getattr(args, "force", False):
            from app.doc_graph.ingest import ingest_extraction  # 延迟导入: dry-run 路径绝不 import ingest（host 无库可跑）

            ingested = asyncio.run(ingest_extraction(model))
        elif _already_ingested(f"eia-sample:{slug}"):
            skipped_existing = True  # 重入守卫: 该样例已导入过, 跳过防 mentions/relations 翻倍
        else:
            from app.doc_graph.ingest import ingest_extraction  # 延迟导入: dry-run 路径绝不 import ingest（host 无库可跑）

            ingested = asyncio.run(ingest_extraction(model))
    return {"slug": slug, "model": model, "outline": outline_status, "has_project": project_name is not None, "ingested": ingested, "skipped_existing": skipped_existing}


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows 控制台/管道打印中文名不炸
        except (AttributeError, ValueError, OSError):
            pass
    parser = argparse.ArgumentParser(description="EIA 样例实体注册表 → doc_graph eia 域导入")
    parser.add_argument("--entities-dir", type=Path, default=_REPO / "skills" / "public" / "coal-eia-report" / "references" / "sample_entities")
    parser.add_argument("--outlines-dir", type=Path, default=_REPO / ".wolf" / "tmp" / "eia-samples")
    parser.add_argument("--skip-outlines", action="store_true", help="跳过大纲头部关系, 仅导实体桶")
    parser.add_argument("--slug", default=None, help="只处理指定 slug")
    parser.add_argument("--dry-run", action="store_true", help="只打印统计, 不入库（不 import ingest）")
    parser.add_argument("--force", action="store_true", help="绕过已导入守卫强制重导（mentions/relations 会翻倍, 仅故意重导时用）")
    args = parser.parse_args()

    if not args.entities_dir.is_dir():
        raise SystemExit(f"ERROR: entities-dir 不存在: {args.entities_dir}")
    outlines_usable = not args.skip_outlines
    if outlines_usable and not args.outlines_dir.is_dir():
        print(f"WARN: outlines-dir 不存在: {args.outlines_dir}——跳过大纲关系, 仅导实体")
        outlines_usable = False

    total_ent = total_rel = 0
    total_ing: dict[str, int] = Counter()
    no_project: list[str] = []
    n_outline_applied = 0
    n_skipped = 0
    files = _entity_files(args.entities_dir, args.slug)
    for path in files:
        r = _process(path, args, outlines_usable)
        model = r["model"]
        total_ent += len(model.entities)
        total_rel += len(model.relations)
        if not r["has_project"]:
            no_project.append(r["slug"])
        if r["outline"].startswith("+"):
            n_outline_applied += 1
        detail = ", ".join(f"{etype} {n}" for etype, n in sorted(Counter(e.etype for e in model.entities).items()))
        line = f"[{r['slug']}] entities={len(model.entities)} ({detail}) relations={len(model.relations)} outline={r['outline']}"
        if r["ingested"]:
            line += f" ingested(ent={r['ingested']['entities_upserted']}, rel={r['ingested']['relations']}, mentions={r['ingested']['mentions']})"
            total_ing.update(r["ingested"])
        elif r["skipped_existing"]:
            line += " ingested=skipped(existing)"
            n_skipped += 1
        print(line)

    print("====")
    mode = "dry-run: 未触库" if args.dry_run else f"ingested: entities={total_ing['entities_upserted']} relations={total_ing['relations']} mentions={total_ing['mentions']} skipped(existing)={n_skipped}"
    print(f"samples={len(files)} entities={total_ent} relations={total_rel} outline-applied={n_outline_applied} entities-only={len(no_project)} {mode}")
    if no_project:
        print(f"entities-only（无 project, 跳过关系边）: {', '.join(no_project)}")


if __name__ == "__main__":
    main()
