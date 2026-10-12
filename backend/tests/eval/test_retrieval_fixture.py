"""Retrieval hit@k evaluation fixture (EAI-CUSTOM, T7 — 样例闸预建件).

用法（设计构件 5 检索链路闸）:
  1. 复制 ``retrieval_fixtures.example.jsonl`` → ``retrieval_fixtures.jsonl``（本目录）
  2. 填真实条目（smoke 8 条起步 → 20 条，中文提问→期望 doc/page）
  3. 容器内跑: PYTHONPATH=. uv run pytest tests/eval/test_retrieval_fixture.py -v
     （需 env: EAI_TLT_EVAL_KB_READY=1 显式开启，防误跑真库）
  4. 阈值: EAI_TLT_HIT_THRESHOLD（默认 0.8 = 设计建议基线 hit@5≥80%，样例后与客户裁定）

夹具缺文件/空 → SKIP（预建状态）；这是「样例到手 30 分钟出检索质量证据」的仪器。
"""

import json
import os
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent / "retrieval_fixtures.jsonl"
HIT_THRESHOLD = float(os.environ.get("EAI_TLT_HIT_THRESHOLD", "0.8"))
TOP_K = 5


def _load_fixtures() -> list[dict]:
    if not FIXTURE_PATH.exists():
        return []
    rows = []
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if str(row.get("question", "")).startswith("EXAMPLE-") or row.get("_readme"):
            continue  # 模板示例行不参与评测
        rows.append(row)
    return rows


def _chunk_doc(chunk: dict) -> str:
    """RAGFlow chunk 的文档名字段多版本兼容读取。"""
    return chunk.get("document_name") or chunk.get("doc_name") or chunk.get("name") or ""


def _chunk_pages(chunk: dict) -> set[int]:
    pages: set[int] = set()
    for pos in chunk.get("positions") or []:
        if isinstance(pos, (list, tuple)) and pos:
            try:
                pages.add(int(pos[0]))
            except (TypeError, ValueError):
                continue
    if chunk.get("page") is not None:
        try:
            pages.add(int(chunk["page"]))
        except (TypeError, ValueError):
            pass
    return pages


def _is_hit(chunk: dict, expect_doc: str, expect_page: int | None) -> bool:
    if _chunk_doc(chunk) != expect_doc:
        return False
    if expect_page is None:
        return True
    pages = _chunk_pages(chunk)
    return not pages or expect_page in pages  # 无页信息时不因页码误判 miss


@pytest.mark.skipif(
    not os.environ.get("EAI_TLT_EVAL_KB_READY") or not _load_fixtures(),
    reason="retrieval fixture not populated yet（样例闸解锁；复制 example 模板并设 EAI_TLT_EVAL_KB_READY=1）",
)
def test_retrieval_hit_at_k():
    """检索链路闸：hit@5 ≥ 阈值（建议基线 80%，最终阈值样例后与客户裁定）。"""
    import asyncio

    from app.extensions.config import get_extensions_config
    from app.extensions.knowledge.client import RAGFlowClient

    fixtures = _load_fixtures()
    assert fixtures, "fixture file present but empty"
    cfg = get_extensions_config()
    client = RAGFlowClient(cfg.ragflow.api_key, cfg.ragflow.base_url)

    async def _run():
        results = []
        for row in fixtures:
            resp = await client.chat(
                row["kb_id"],
                row["question"],
                top_k=TOP_K,
            )
            chunks = (resp.get("data") or {}).get("chunks") or []
            hits = [
                c
                for c in chunks
                if _is_hit(c, row["expect_doc"], row.get("expect_page"))
            ]
            results.append(
                {
                    "question": row["question"],
                    "hit": bool(hits),
                    "top_docs": [_chunk_doc(c) for c in chunks[:TOP_K]],
                }
            )
        return results

    results = asyncio.run(_run())
    hit_rate = sum(1 for r in results if r["hit"]) / len(results)
    misses = [r for r in results if not r["hit"]]
    detail = "\n".join(f"  MISS: {m['question']} → got {m['top_docs']}" for m in misses)
    print(f"\nhit@{TOP_K} = {hit_rate:.0%} ({len(results) - len(misses)}/{len(results)}) threshold={HIT_THRESHOLD:.0%}")
    if misses:
        print(detail)
    assert hit_rate >= HIT_THRESHOLD, f"retrieval gate failed: hit@{TOP_K}={hit_rate:.0%} < {HIT_THRESHOLD:.0%}\n{detail}"
