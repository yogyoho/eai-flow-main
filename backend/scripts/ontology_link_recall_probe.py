"""Ontology 跨模块链接召回预测量（eng-review D12 / plan T1）.

对 4 条跨模块链接在当前数据上实测匹配率，决定每条链接 YAML 的 enabled 值：
阈值 30%——低于即建议 enabled:false stub + note 记录实测值。

运行（gateway 容器内，同 seed_mock_market.py 模式）:
    docker exec deer-flow-gateway python /app/backend/scripts/ontology_link_recall_probe.py

4 条链接（母稿 §6.2）:
  1. part_cluster_matches_goods_cluster   csp_clusters.representative_name ↔ cpa_clusters.representative_name
  2. contract_document_matches_spare_document  csp_documents ↔ cpa_documents (contract_no 或 file_hash)
  3. won_bid_contracts_project            mock_bid(won=true).project_name ↔ cpa_documents.project_name  [跨库]
  4. document_supplied_by                 cpa_documents.supplier ↔ csp_documents.supplier

归一化 = LOWER(BTRIM(col))，与引擎级标准一致；两侧 NULL/空串守卫（引擎将强制，此处同口径）。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import asyncpg

PG_HOST = os.environ.get("EXTENSIONS_DB_HOST", "postgres-ext")
PG_PORT = int(os.environ.get("EXTENSIONS_DB_PORT", "5432"))
PG_USER = os.environ.get("EXTENSIONS_DB_USER", "agentflow")
PG_PASS = os.environ.get("EXTENSIONS_DB_PASSWORD", "agentflow123")
EXT_DB = os.environ.get("EXTENSIONS_DB_NAME", "agentflow")  # 扩展库(cpa_/csp_)
MOCK_DB = "mock_market"  # data_source bid-quote 背书库(mock_bid)

THRESHOLD = 0.30  # eng-review D12 建议 30%
NORM = "LOWER(BTRIM({col}))"


async def side_counts(conn: asyncpg.Connection, table: str, col: str) -> tuple[int, int]:
    """返回 (有效键行数, 总行数)。有效 = 归一化后非空。"""
    total = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
    valid = await conn.fetchval(f"SELECT COUNT(*) FROM {table} WHERE {NORM.format(col=col)} IS NOT NULL AND {NORM.format(col=col)} <> ''")
    return valid or 0, total or 0


async def link1(ext: asyncpg.Connection) -> dict:
    """part_cluster ↔ goods_cluster（同库单 SQL）。"""
    q = f"""
        SELECT
          (SELECT COUNT(*) FROM csp_clusters c WHERE {NORM.format(col="c.representative_name")} <> '') AS src_valid,
          (SELECT COUNT(*) FROM csp_clusters) AS src_total,
          (SELECT COUNT(*) FROM cpa_clusters p WHERE {NORM.format(col="p.representative_name")} <> '') AS tgt_valid,
          (SELECT COUNT(*) FROM cpa_clusters) AS tgt_total,
          (SELECT COUNT(*) FROM csp_clusters c JOIN cpa_clusters p
             ON {NORM.format(col="c.representative_name")} = {NORM.format(col="p.representative_name")}
           WHERE {NORM.format(col="c.representative_name")} <> '' AND {NORM.format(col="p.representative_name")} <> '') AS matched_src
        , (SELECT COUNT(DISTINCT p.id) FROM csp_clusters c JOIN cpa_clusters p
             ON {NORM.format(col="c.representative_name")} = {NORM.format(col="p.representative_name")}
           WHERE {NORM.format(col="c.representative_name")} <> '' AND {NORM.format(col="p.representative_name")} <> '') AS matched_tgt
    """
    r = await ext.fetchrow(q)
    return _mk("part_cluster_matches_goods_cluster", dict(r))


async def link2(ext: asyncpg.Connection) -> dict:
    """spare_part_document ↔ contract_document（contract_no 归一化相等 或 file_hash 相等；两分支均非空守卫）。"""
    q = """
        SELECT
          (SELECT COUNT(*) FROM csp_documents WHERE LOWER(BTRIM(contract_no)) <> '' OR BTRIM(file_hash) <> '') AS src_valid,
          (SELECT COUNT(*) FROM csp_documents) AS src_total,
          (SELECT COUNT(*) FROM cpa_documents WHERE LOWER(BTRIM(contract_no)) <> '' OR BTRIM(file_hash) <> '') AS tgt_valid,
          (SELECT COUNT(*) FROM cpa_documents) AS tgt_total,
          (SELECT COUNT(*) FROM csp_documents s WHERE
             (LOWER(BTRIM(s.contract_no)) <> '' AND LOWER(BTRIM(s.contract_no)) IN (SELECT LOWER(BTRIM(contract_no)) FROM cpa_documents WHERE LOWER(BTRIM(contract_no)) <> ''))
             OR (BTRIM(s.file_hash) <> '' AND BTRIM(s.file_hash) IN (SELECT BTRIM(file_hash) FROM cpa_documents WHERE BTRIM(file_hash) <> ''))) AS matched_src
    """
    r = await ext.fetchrow(q)
    d = dict(r)
    d["matched_tgt"] = None  # 反向口径同构，省略（对称谓词）
    return _mk("contract_document_matches_spare_document", d)


async def link3(ext: asyncpg.Connection, mock: asyncpg.Connection) -> dict:
    """won_bid(won=true) ↔ contract_document（跨库：分块应用侧 join，即 D11 引擎机制的一次性手工版）。"""
    won_names = [r["n"] for r in await mock.fetch("SELECT LOWER(BTRIM(project_name)) AS n FROM mock_bid WHERE won = true AND LOWER(BTRIM(project_name)) <> ''")]
    won_total = await mock.fetchval("SELECT COUNT(*) FROM mock_bid WHERE won = true")
    matched = 0
    CHUNK = 200  # 与守卫 LIMIT 200 同口径（D11）
    for i in range(0, len(won_names), CHUNK):
        batch = won_names[i : i + CHUNK]
        rows = await ext.fetch(
            "SELECT DISTINCT LOWER(BTRIM(project_name)) FROM cpa_documents WHERE LOWER(BTRIM(project_name)) = ANY($1::text[])",
            batch,
        )
        matched += len(rows)
    cp_doc_valid, cp_doc_total = await side_counts(ext, "cpa_documents", "project_name")
    return _mk(
        "won_bid_contracts_project",
        {
            "src_valid": len(won_names),
            "src_total": won_total,
            "tgt_valid": cp_doc_valid,
            "tgt_total": cp_doc_total,
            "matched_src": matched,
            "matched_tgt": matched,
        },
    )


async def link4(ext: asyncpg.Connection) -> dict:
    """contract_document ↔ spare_part_document（supplier 归一化相等）。"""
    q = f"""
        SELECT
          (SELECT COUNT(*) FROM cpa_documents WHERE {NORM.format(col="supplier")} <> '') AS src_valid,
          (SELECT COUNT(*) FROM cpa_documents) AS src_total,
          (SELECT COUNT(*) FROM csp_documents WHERE {NORM.format(col="supplier")} <> '') AS tgt_valid,
          (SELECT COUNT(*) FROM csp_documents) AS tgt_total,
          (SELECT COUNT(*) FROM cpa_documents a WHERE {NORM.format(col="a.supplier")} <> ''
             AND {NORM.format(col="a.supplier")} IN (SELECT {NORM.format(col="supplier")} FROM csp_documents WHERE {NORM.format(col="supplier")} <> '')) AS matched_src
    """
    r = await ext.fetchrow(q)
    d = dict(r)
    d["matched_tgt"] = None
    return _mk("document_supplied_by", d)


def _mk(api_name: str, d: dict) -> dict:
    src_rate = (d["matched_src"] / d["src_valid"]) if d["src_valid"] else 0.0
    out = {
        "api_name": api_name,
        "src_valid": d["src_valid"],
        "src_total": d["src_total"],
        "matched_src": d["matched_src"],
        "src_match_rate": round(src_rate, 4),
        "tgt_valid": d["tgt_valid"],
        "tgt_total": d["tgt_total"],
        "matched_tgt": d.get("matched_tgt"),
    }
    today = __import__("datetime").date.today()
    if d["src_valid"] == 0 or d["tgt_valid"] == 0:
        out["verdict"] = "NO_DATA"  # 无数据 ≠ 零召回：数据到位后重测，先 stub 不下结论
        out["suggested"] = {"enabled": False, "note": f"recall probe {today}: source/target empty (src {d['src_total']} rows, tgt {d['tgt_total']} rows) — re-probe when data lands"}
    else:
        out["verdict"] = "OK" if src_rate >= THRESHOLD else "STUB"
        out["suggested"] = {"enabled": src_rate >= THRESHOLD, "note": f"recall probe {today}: src_match_rate={src_rate:.1%} (threshold {THRESHOLD:.0%})"}
    return out


async def main() -> None:
    common = dict(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS)
    try:
        ext = await asyncpg.connect(**common, database=EXT_DB)
    except Exception as e:
        sys.exit(f"[fail] 扩展库连接失败: {e}")
    try:
        mock = await asyncpg.connect(**common, database=MOCK_DB)
    except Exception:
        mock = None
        print("[warn] mock_market 不可达——link3 将输出 unavailable", file=sys.stderr)

    results = [await link1(ext), await link2(ext)]
    if mock:
        results.append(await link3(ext, mock))
    else:
        results.append({"api_name": "won_bid_contracts_project", "verdict": "UNAVAILABLE", "suggested": {"enabled": False, "note": "mock_market unreachable at probe time"}})
    results.append(await link4(ext))

    print(json.dumps({"threshold": THRESHOLD, "links": results}, ensure_ascii=False, indent=2))
    print("\n┌─ 召回判定（写回 cross_module.yaml 的 enabled/note）─", file=sys.stderr)
    for r in results:
        if r.get("verdict") == "UNAVAILABLE":
            print(f"│  {r['api_name']}: UNAVAILABLE → enabled:false + note", file=sys.stderr)
        else:
            print(f"│  {r['api_name']}: src {r['matched_src']}/{r['src_valid']} = {r['src_match_rate']:.1%} → {r['verdict']}", file=sys.stderr)
    print("└──────────────────────────────────────────────────", file=sys.stderr)

    await ext.close()
    if mock:
        await mock.close()


if __name__ == "__main__":
    asyncio.run(main())
