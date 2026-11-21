"""批十五 T2 定点判读(容器内一次性运维,不进 git):单样本全链路 + 缺陷键 issue 级 dump。"""
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path("/app/backend")
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from app.extensions.database import Base  # noqa: E402
from app.extensions.bid_review import crud  # noqa: E402
from app.extensions.bid_review.worker import _default_extract_fn, advance_task  # noqa: E402
from deerflow.utils.file_conversion import convert_file_to_markdown  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from bid_review_live_full import _TABLES  # noqa: E402


def _flatten(d, p=""):
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            out.update(_flatten(v, p + k + "."))
        else:
            out[p + k] = v
    return out


async def main():
    docs = []
    for path, role in ((Path("/tmp/realcase-tender.docx"), "tender"), (Path("/tmp/realcase-bid.docx"), "bid")):
        md = await convert_file_to_markdown(path)
        docs.append({"doc_id": path.name, "role": role, "text": md.read_text(encoding="utf-8") if md else ""})
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        t = await crud.create_task(s, owner_id="j15")
        await advance_task(s, t.id, "j15", docs, _default_extract_fn(), False)
        issues = await crud.list_issues(s, task_id=t.id, owner_id="j15")
        rows = await crud.list_baselines(s, task_id=t.id, owner_id="j15")
    flat = _flatten(rows[0].payload.get("fields") if rows else {})
    watch = [k for k in flat if any(s in k for s in ["total_price", "max_price", "tax_rate", "boq", "deposit", "license", "deadline", "bid_scope", "signatory", "business_scope", "qual_level", "qual_levels", "similar_performances", "alternative_price", "submit_time", "submit_method", "allowed_submit"])]
    out = {
        "issues": [{"rule": i.rule_id, "verdict": i.verdict, "msg": (i.message or "")[:140]} for i in issues],
        "keys": {k: str(flat[k])[:70] for k in sorted(watch)},
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
