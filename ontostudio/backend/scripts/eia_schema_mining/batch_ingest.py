"""子项目2 批量编排：--phase parse|extract|convert|ingest|report（断点续跑）。

parse   = 调 parse_docx.main()（out/fulltexts 已存在即跳过 = 缓存续跑）
extract = 调 llm_extract.py 子进程（env EIA_MINING_LLM_* 就绪时；--stride/--workers 透传；
          cwd=脚本目录——controlled_vocab.yaml 按相对路径读取, 同计划 Task 4 手跑命令）
convert = 候选 JSONL → out/payloads/{slug}.json（convert_candidates.convert 幂等纯函数；
          逐 payload 先过 EiaExtraction.model_validate fail-closed——与 Task5 ingest 同门, 提前暴露）
ingest  = 每报告: 重入守卫 → EiaExtraction.model_validate → asyncio.run(ingest_extraction)
          （照抄 import_eia_samples.py:193-209; 守卫照其 :135-157 _already_ingested——
          document_id = :doc 精确判等）。守卫键 dg_mentions.document_id **精确等于** 'eia-batch:{slug}'
          ——禁止改 LIKE 前缀（'eia-batch:yimin%' 会误吞 'eia-batch:yimin3500', review 2026-09-29 定案;
          且 convert 的 source 必须恰为 f"eia-batch:{slug}", 否则守卫永不命中）。
          守卫只挡整报告重导——ingest_extraction 对 mentions/relations 盲 INSERT（bug-3353）,
          --force 显式绕过（会翻倍, 仅清库后有意重跑用）。
report  = 汇总 out/ingest_report.md（每报告实体/关系/pending 数 + 守卫/已入库计数 + CQ 执行结果）

断点续跑 = 每 phase 独立可重入：parse 有缓存、convert 幂等纯函数、ingest 有守卫。
ingest 后打印 payload 官方统计（ingest_extraction 返回 dict: entities_upserted/relations/mentions）。

Run（backend 根, CWD 无关——路径全部锚定脚本目录）:
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_schema_mining/batch_ingest.py --phase convert --dry-run
    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/eia_schema_mining/batch_ingest.py --phase ingest --slug sijitun --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent  # scripts/eia_schema_mining/
BACKEND_ROOT = SCRIPT_DIR.parents[1]  # ontostudio/backend（app/ 可导入根）
OUT = SCRIPT_DIR / "out"
PAYLOADS_DIR = OUT / "payloads"
FULLTEXTS_DIR = OUT / "fulltexts"

sys.path.insert(0, str(BACKEND_ROOT))  # backend 根可导入 app/（同 llm_extract.py:35 / convert_candidates.py:21）
sys.path.insert(0, str(SCRIPT_DIR.parent))  # scripts/ 非包: 复用 eia_purge_v1.resolve_dsn（DSN 单一真源）

from app.doc_graph.schemas import EiaExtraction  # noqa: E402 (sys.path 先插入)

PENDING_THRESHOLD = 0.7  # < REVIEW_CONFIDENCE(app/doc_graph/ingest.py)=0.7 → pending_review 走人审
DEFAULT_CANDIDATES = OUT / "batch_candidates.jsonl"
FALLBACK_CANDIDATES = OUT / "llm_candidates.jsonl"  # 子项目1 已产出的 4 报告候选（dry-run 小验用）

_LLM_ENV_KEYS = ("EIA_MINING_LLM_BASE_URL", "EIA_MINING_LLM_API_KEY", "EIA_MINING_LLM_MODEL")


def _reconfigure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows 控制台/管道打印中文不炸（同 eia_purge_v1.py:84）
        except (AttributeError, ValueError, OSError):
            pass


# ---------------------------------------------------------------- phase: parse


def phase_parse(_args: argparse.Namespace) -> None:
    import parse_docx  # 脚本同目录（sys.path[0]）, 依赖 stdlib

    # parse_docx.main() 用相对路径 out/fulltexts——锚定到脚本目录, 调用方 CWD 无关
    with contextlib.chdir(SCRIPT_DIR):
        parse_docx.main()


# ---------------------------------------------------------------- phase: extract


def phase_extract(args: argparse.Namespace) -> None:
    if args.slug:
        # review 2026-09-29: 静默忽略过滤器是长任务陷阱——2-4h 批跑后才发现没过滤
        raise SystemExit("ERROR: --slug 仅 convert/ingest 支持（extract 按 --samples 清单全量跑）")
    missing = [k for k in _LLM_ENV_KEYS if not os.getenv(k)]
    if missing:
        raise SystemExit(f"ERROR: extract 的 LLM env 未就绪: {', '.join(missing)}（取值见计划「执行前必读」）")
    if not any(FULLTEXTS_DIR.glob("*-fulltext.txt")):
        raise SystemExit(f"ERROR: {FULLTEXTS_DIR} 无全文——先跑 --phase parse")
    cmd = [
        sys.executable, "llm_extract.py",
        "--src", "out/fulltexts",
        "--samples", args.samples,
        "--out", args.out,
        "--stride", str(args.stride),
        "--workers", str(args.workers),
    ]
    print("+", " ".join(cmd), f"  (cwd={SCRIPT_DIR})")
    if args.dry_run:
        print("dry-run: 未执行抽取")
        return
    raise SystemExit(subprocess.run(cmd, cwd=SCRIPT_DIR).returncode)


# ---------------------------------------------------------------- phase: convert


def _candidates_path(args: argparse.Namespace) -> Path:
    if args.candidates:
        p = Path(args.candidates)
        if not p.is_absolute() and not p.exists():
            p = SCRIPT_DIR / p  # 相对路径先按调用方 CWD, 再按脚本目录（backend 根手跑场景）
        if not p.exists():
            raise SystemExit(f"ERROR: --candidates 不存在: {args.candidates}")
        return p
    if DEFAULT_CANDIDATES.exists():
        return DEFAULT_CANDIDATES
    if FALLBACK_CANDIDATES.exists():
        print(f"NOTE: {DEFAULT_CANDIDATES.name} 尚无（Task4 批量抽取后生成）, 回退 {FALLBACK_CANDIDATES.name}（子项目1 四报告候选）")
        return FALLBACK_CANDIDATES
    raise SystemExit(f"ERROR: 无候选文件: {DEFAULT_CANDIDATES} 与 {FALLBACK_CANDIDATES} 均不存在——先跑 --phase extract")


def _load_candidate_rows(path: Path) -> dict[str, list[dict]]:
    by_report: dict[str, list[dict]] = defaultdict(list)
    bad = 0
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            rep = row.get("report")
            if not rep:
                bad += 1
                continue
            by_report[rep].append(row)
    if bad:
        print(f"WARN: {path.name} 跳过 {bad} 行（非 JSON / 缺 report 字段）")
    if not by_report:
        raise SystemExit(f"ERROR: {path} 无有效候选行")
    return dict(by_report)


def _fulltext_getter():
    def get(source: str) -> str:
        slug = source.removeprefix("eia-batch:")
        p = FULLTEXTS_DIR / f"{slug}-fulltext.txt"
        if not p.exists():
            raise SystemExit(f"ERROR: [{slug}] 全文缺失: {p}——幻觉过滤无法核验, 先跑 --phase parse")
        return p.read_text(encoding="utf-8", errors="ignore")

    return get


def phase_convert(args: argparse.Namespace) -> None:
    import convert_candidates as cc  # 脚本同目录（sys.path[0]）

    rows_by_report = _load_candidate_rows(_candidates_path(args))
    if args.slug:
        if args.slug not in rows_by_report:
            raise SystemExit(f"ERROR: --slug {args.slug!r} 在候选文件中无行")
        rows_by_report = {args.slug: rows_by_report[args.slug]}
    getter = _fulltext_getter()
    if not args.dry_run:
        PAYLOADS_DIR.mkdir(parents=True, exist_ok=True)
    totals: Counter = Counter()
    for slug in sorted(rows_by_report):
        res = cc.convert(rows_by_report[slug], getter, source=f"eia-batch:{slug}")
        totals.update(res.stats)
        if not res.payloads:
            print(f"[{slug}] 无存活实体 {dict(res.stats)}——不产 payload")
            continue
        payload = res.payloads[0]
        EiaExtraction.model_validate(payload)  # fail-closed: 与 Task5 ingest 同门, 此处不过必不过
        dst = PAYLOADS_DIR / f"{slug}.json"
        line = (f"[{slug}] entities={len(payload['entities'])} relations={len(payload['relations'])} "
                f"pending={sum(1 for e in payload['entities'] if e['confidence'] < PENDING_THRESHOLD)} "
                f"stats={dict(res.stats)}")
        if args.dry_run:
            print(line + " (dry-run: 未写文件)")
        else:
            dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(line + f" → {dst.relative_to(SCRIPT_DIR)}")
    tag = "dry-run 合计" if args.dry_run else "合计"
    print(f"==== {tag}: reports={len(rows_by_report)} {dict(totals)}")


# ---------------------------------------------------------------- phase: ingest


def _guard_count(slug: str, dsn: str) -> int:
    """重入守卫: dg_mentions.document_id 精确判等（bug-3353; 勿改 LIKE 前缀, yimin⊂yimin3500 会跨报告误判）。"""
    import asyncpg

    async def _query() -> int:
        conn = await asyncpg.connect(dsn)
        try:
            return int(await conn.fetchval(
                "SELECT count(*) FROM dg_mentions WHERE document_id = $1", f"eia-batch:{slug}"))
        finally:
            await conn.close()

    return asyncio.run(_query())


def _resolve_dsn(explicit: str | None) -> str:
    from eia_purge_v1 import resolve_dsn  # noqa: E402  scripts/ 已插入 sys.path（DSN 单一真源, 同 eia_purge_v1.py:57）

    return resolve_dsn(explicit)


def _payload_files(slug_filter: str | None) -> list[Path]:
    if not PAYLOADS_DIR.is_dir():
        raise SystemExit(f"ERROR: {PAYLOADS_DIR} 不存在——先跑 --phase convert")
    files = sorted(PAYLOADS_DIR.glob("*.json"))
    if slug_filter:
        files = [p for p in files if p.stem == slug_filter]
        if not files:
            raise SystemExit(f"ERROR: --slug {slug_filter!r} 在 {PAYLOADS_DIR} 下无 payload")
    if not files:
        raise SystemExit(f"ERROR: {PAYLOADS_DIR} 无 payload——先跑 --phase convert")
    return files


def phase_ingest(args: argparse.Namespace) -> None:
    files = _payload_files(args.slug)
    dsn = _resolve_dsn(args.dsn)
    n_skip = n_ing = 0
    total: Counter = Counter()
    for path in files:
        slug = path.stem
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            model = EiaExtraction.model_validate(payload)
        except Exception as e:  # pydantic ValidationError → fail-closed 不静默跳过（同 import_eia_samples.py:193-195）
            raise SystemExit(f"ERROR: [{slug}] EiaExtraction 校验失败（fail-closed）: {e}") from e
        would = {"entities": len(model.entities), "relations": len(model.relations),
                 "mentions": len(model.entities) + len(model.relations)}
        try:
            n = _guard_count(slug, dsn)
            guard = f"hit({n})" if n else "miss"
        except Exception as exc:
            if not args.dry_run:
                raise SystemExit(f"ERROR: [{slug}] 守卫查询失败（fail-closed, bug-3353 防翻倍）: {exc}") from exc
            guard = f"unreachable({exc.__class__.__name__})"
            n = None
        if args.dry_run:
            print(f"[{slug}] dry-run guard(document_id='eia-batch:{slug}')={guard} would-insert {would}")
            continue
        if n and not args.force:
            print(f"[{slug}] skip（守卫命中: {n} 条 mentions 已存在; 有意重导加 --force, 会翻倍）")
            n_skip += 1
            continue
        if n and args.force:
            print(f"[{slug}] FORCE 重导（mentions/relations 会翻倍——仅清库后有意重跑用）")
        from app.doc_graph.ingest import ingest_extraction  # 延迟导入: 非 ingest 路径不触 sqlalchemy（同 import_eia_samples.py:201）

        counts = asyncio.run(ingest_extraction(model))
        print(f"[{slug}] ingested {counts}")
        total.update(counts)
        n_ing += 1
    if not args.dry_run:
        print(f"==== ingested={n_ing} skipped(existing)={n_skip} total={dict(total)}")


# ---------------------------------------------------------------- phase: report


def _report_db_counts(slugs: list[str], dsn: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for slug in slugs:
        try:
            counts[slug] = _guard_count(slug, dsn)
        except Exception as exc:
            print(f"WARN: [{slug}] 守卫计数失败（报告按未入库处理）: {exc.__class__.__name__}: {exc}")
            counts[slug] = -1  # -1 = 查询失败, 报告中标注
    return counts


def phase_report(args: argparse.Namespace) -> None:
    files = sorted(PAYLOADS_DIR.glob("*.json")) if PAYLOADS_DIR.is_dir() else []
    if not files:
        raise SystemExit(f"ERROR: {PAYLOADS_DIR} 无 payload——先跑 --phase convert")
    slugs = [p.stem for p in files]
    db_counts = _report_db_counts(slugs, _resolve_dsn(args.dsn)) if not args.dry_run else {}

    lines = [
        "# 环评批量抽取入图验收报告（子项目2）",
        "",
        f"生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"payload 来源: `{PAYLOADS_DIR.relative_to(BACKEND_ROOT.parent).as_posix()}/`（extracted_by=eia-batch-v2-llm, confidence=0.6 全量 pending）",
        "",
        "| 报告 | 实体 | 关系 | pending(<0.7) | 已入库 mentions |",
        "|---|---:|---:|---:|---:|",
    ]
    t_ent = t_rel = t_pend = 0
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ents, rels = payload.get("entities", []), payload.get("relations", [])
        pend = sum(1 for e in ents if e.get("confidence", 1.0) < PENDING_THRESHOLD)
        t_ent += len(ents)
        t_rel += len(rels)
        t_pend += pend
        db = db_counts.get(path.stem)
        db_cell = "查询失败" if db == -1 else ("—" if args.dry_run else str(db))
        lines.append(f"| {path.stem} | {len(ents)} | {len(rels)} | {pend} | {db_cell} |")
    lines += [
        f"| **合计** | **{t_ent}** | **{t_rel}** | **{t_pend}** | |",
        "",
        f"reports={len(files)}；全部 confidence=0.6 → 全量落 pending_review 走人审（设计意图, 非缺陷）。",
    ]

    cq_path = Path(args.cq_results) if args.cq_results else OUT / "cq_report.json"
    lines += ["", "## CQ 执行结果", ""]
    if cq_path.exists():
        raw = cq_path.read_text(encoding="utf-8", errors="replace")
        if len(raw) > 4000:
            raw = raw[:4000] + "\n…（截断, 全文见 " + str(cq_path) + "）"
        lines += [f"来源: `{cq_path}`", "", "```", raw, "```"]
    else:
        lines += ["未执行——Task5 容器 formal/load → infer → validate（国标五项）后回填 12 条 CQ 执行结果"]

    dst = OUT / "ingest_report.md"
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"→ {dst}")


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> None:
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(description="环评批量抽取入图编排器（parse/extract/convert/ingest/report 五相断点续跑）")
    ap.add_argument("--phase", required=True, choices=["parse", "extract", "convert", "ingest", "report"])
    ap.add_argument("--slug", default=None, help="只处理指定 slug（仅 convert/ingest 支持过滤; extract 传此参数报错）")
    ap.add_argument("--dry-run", action="store_true",
                    help="convert: 只打印合法 payload 计数不写文件; ingest: 只显示守卫查询+将插入行数不写库; extract: 只打印命令")
    ap.add_argument("--candidates", default=None, help=f"候选 JSONL 路径（缺省 {DEFAULT_CANDIDATES.name}, 无则回退 {FALLBACK_CANDIDATES.name}）")
    ap.add_argument("--out", default="out/batch_candidates.jsonl", help="extract: 候选输出（相对脚本目录）")
    ap.add_argument("--samples", default="batch24.json", help="extract: 报告清单（相对脚本目录）")
    ap.add_argument("--stride", type=int, default=2, help="extract: chunk 步长透传（同计划 Task 4 命令）")
    ap.add_argument("--workers", type=int, default=6, help="extract: 并发透传（同计划 Task 4 命令）")
    ap.add_argument("--force", action="store_true", help="ingest: 绕过守卫强制重导（mentions/relations 翻倍, 仅清库后有意重跑用）")
    ap.add_argument("--dsn", default=None, help="显式 asyncpg DSN; 缺省 ONTOSTUDIO_PG_DSN / EXTENSIONS_DB_* 平台配置（同 eia_purge_v1）")
    ap.add_argument("--cq-results", default=None, help="report: CQ 执行结果文件（缺省 out/cq_report.json, 不存在则标注未执行）")
    args = ap.parse_args(argv)

    {"parse": phase_parse, "extract": phase_extract, "convert": phase_convert,
     "ingest": phase_ingest, "report": phase_report}[args.phase](args)


if __name__ == "__main__":
    main()
