"""批十二 live 批:21 叶平键生产侧真值探针 + A-ADJ-1 递交方式集先验(EAI-CUSTOM 2026-11-10)。

批七 T1 注册的 21 条叶平键契约(FIELD_TYPE_CONTRACTS :534 起)自落地以来从未 live 验证——
golden 夹具是静态值,golden --live 只跑 26 主键打分不含叶键面。本脚本对两夹具各单跑一次
advance_task 生产全链路,采集:
  1) 21 叶键 flatten 后的值/在场率(真值验证——null=模型没抽到,锚定 ADJ 纪律);
  2) A-ADJ-1 先验:标书原文递交方式线索(电子/纸质/邮寄/哉体)逐行摘录 + fields 无该键的确认;
  3) stage 统计复用 bid_review_live_full._stage_stats(锚对照)。

一次性运维脚本:sqlite 内存库定点五表,不触生产 postgres;exit 恒 0(判读在调用方);
进度走 stderr,完整 JSON 走 stdout(重定向落文件——bug-4027 教训,禁 tail 管道)。

容器内运行(gateway 容器):
  cd /app/backend && PYTHONPATH=. uv run python scripts/bid_review_live_leafkeys.py > /tmp/leafkeys.json 2>/tmp/leafkeys.err
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

_CASES = BACKEND / "app" / "extensions" / "bid_review" / "golden" / "extract_cases"

# 批七 T1 21 叶平键(extract.py :535-557 逐字;含批七 T3 富化键 required_signatures)
LEAF_KEYS = [
    "bid.pm.certs",
    "bid.pm.social_months",
    "bid.pm.on_other_project",
    "tender.pm_req.certs",
    "tender.pm_req.social_months",
    "tender.pm_req.exclusive",
    "tender.subcontract_limit.allowed",
    "tender.subcontract_limit.scope",
    "tender.required_signatures",
    "tender.format_requirements.copies",
    "tender.format_requirements.toc",
    "tender.format_requirements.page_numbering",
    "tender.format_requirements.font",
    "tender.format_requirements.sealing",
    "bid.format.copies",
    "bid.format.toc",
    "bid.format.page_numbering",
    "bid.format.font",
    "bid.format.sealing_label",
    "bid.service_commitments",
    "bid.submit_time",
]

_DOCSETS = {
    "variance": [("variance-tender.md", "tender"), ("variance-bid.md", "bid")],
    "walkthrough": [("walkthrough-tender.md", "tender"), ("walkthrough-bid.md", "bid")],
}

# A-ADJ-1 先验:递交方式线索行(原文里有没有可抽的「允许递交方式集合」表述)
_SUBMIT_METHOD_PAT = re.compile(r"递交|提交方式|电子标|纸质|邮寄|光盘|U盘|密封递交", re.IGNORECASE)


def _flatten(d: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def _leaf_report(fields_flat: dict) -> dict:
    """21 叶键逐键:值截断展示+在场判定。flatten 键可能带容器前缀,按后缀匹配。"""
    out = {}
    for lk in LEAF_KEYS:
        hit = None
        for fk, fv in fields_flat.items():
            if fk == lk or fk.endswith("." + lk):
                hit = (fk, fv)
                break
        if hit is None:
            out[lk] = {"present": False, "value": None}
        else:
            fk, fv = hit
            s = json.dumps(fv, ensure_ascii=False, default=str)
            out[lk] = {"present": True, "flat_key": fk, "value": s[:160]}
    return out


def _submit_method_probe(tender_text: str, fields_flat: dict) -> dict:
    """A-ADJ-1 先验:原文递交方式线索行(去重,前 12 行)+ 注册键里无方式集合的确认。"""
    lines = []
    seen: set[str] = set()
    for raw in tender_text.splitlines():
        line = raw.strip()
        if line and _SUBMIT_METHOD_PAT.search(line) and line not in seen:
            seen.add(line)
            lines.append(line[:200])
        if len(lines) >= 12:
            break
    method_keys = sorted(k for k in fields_flat if "submit_method" in k or "递交方式" in k)
    return {"tender_lines": lines, "registered_method_keys": method_keys}


async def _run_docset(name: str, docs: list[dict]) -> dict:
    from bid_review_live_full import _TABLES, _stage_stats
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.extensions.bid_review import crud
    from app.extensions.bid_review.worker import _default_extract_fn, advance_task
    from app.extensions.database import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    t0 = time.perf_counter()
    async with factory() as s:
        t = await crud.create_task(s, owner_id="live-leafkeys")
        await advance_task(s, t.id, "live-leafkeys", docs, _default_extract_fn(), True)
        rows = await crud.list_baselines(s, task_id=t.id, owner_id="live-leafkeys")
        payload = rows[0].payload
    await engine.dispose()
    fields = payload.get("fields") or {}
    flat = _flatten(fields)
    tender_text = next(d["text"] for d in docs if d["role"] == "tender")
    return {
        "docset": name,
        "seconds": round(time.perf_counter() - t0, 1),
        "stages": _stage_stats(fields),
        "leaf_keys": _leaf_report(flat),
        "leaf_present": sum(1 for v in _leaf_report(flat).values() if v["present"]),
        "adj1": _submit_method_probe(tender_text, flat),
    }


async def main() -> int:
    results = []
    for name, names in _DOCSETS.items():
        docs = [{"doc_id": n, "role": role, "text": (_CASES / n).read_text(encoding="utf-8")} for n, role in names]
        print(f"[leafkeys] docset {name} start", file=sys.stderr, flush=True)
        try:
            results.append(await _run_docset(name, docs))
            print(f"[leafkeys] docset {name} done in {results[-1]['seconds']}s", file=sys.stderr, flush=True)
        except Exception as e:  # noqa: BLE001 — 运维脚本,失败类型不枚举(bug-4086 律)
            results.append({"docset": name, "ok": False, "error": f"{type(e).__name__}: {e}"})
            print(f"[leafkeys] docset {name} FAILED: {e}", file=sys.stderr, flush=True)
    print(json.dumps({"leaf_keys_total": len(LEAF_KEYS), "results": results}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
