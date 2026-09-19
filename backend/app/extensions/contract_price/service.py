"""Pipeline orchestration service for the management API.

Triggers the agent-skill pipeline (``skills/public/contract-price-analysis``) as
a subprocess so the Gateway never imports the gitignored skill package directly.
The skill's CLI writes its results to the shared ``cpa_`` tables (same DB), which
this extension reads back. The run is recorded in ``cpa_run_history``.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.contract_price import crud

logger = logging.getLogger(__name__)

# Skill directory resolved relative to the repo root (backend/ is cwd at runtime).
_REPO_ROOT = Path(__file__).resolve().parents[4]  # backend/app/extensions/contract_price -> repo root
# EAI-CUSTOM: skill migrated custom→public in commit 86735708; this path MUST
# stay in sync with the on-disk skill location or the subprocess trigger fails
# silently (bug-526). Guarded by test_skill_dir_exists in the backend suite.
_SKILL_DIR = _REPO_ROOT / "skills" / "public" / "contract-price-analysis"

# EAI-CUSTOM P2 LLM 兜底(spec 2026-09-19 §3): 扩展配置(gateway 配置 API 同一
# config.json)中的 LLM 三元组 → 子进程 --llm-* argv。任一缺失/空 → 不传
# (LLM 层关闭,管线行为零变化);key 支持 "$ENV_VAR" 形式,运行时解析。
_LLM_FLAG_MAP = (
    ("llm_base_url", "--llm-base-url"),
    ("llm_key", "--llm-key"),
    ("llm_model", "--llm-model"),
)


def _resolve_llm_args() -> list[str]:
    """Read the LLM triple from the extension config and build --llm-* argv flags.

    缺省(config 无三元组/读取失败/任一要素为空或 $ENV 未解析)→ [] 不传——
    层关闭,子进程行为与未引入本机制前完全一致。"""
    try:
        cfg = crud.load_config()
    except Exception:  # noqa: BLE001 — 配置不可读时绝不阻塞管线触发
        return []
    vals: list[tuple[str, str]] = []
    for field_name, flag in _LLM_FLAG_MAP:
        v = str(getattr(cfg, field_name, None) or "").strip()
        if v.startswith("$"):
            v = os.environ.get(v[1:], "").strip()
        if not v:
            return []
        vals.append((flag, v))
    out: list[str] = []
    for flag, v in vals:
        out += [flag, v]
    return out


async def run_pipeline_subprocess(
    session: AsyncSession,
    run_id: UUID,
    mode: str = "table",
    trigger: str = "manual",
    phase: str = "parse",
    force_key: str | None = None,
    re_ocr: bool = False,
) -> None:
    """Run the skill CLI as a subprocess and record the outcome.

    ``phase``: "parse" (scan→OCR→extract→persist items) or "cluster" (cluster
    confirmed/skipped docs' items). Designed to run in a background task
    (fire-and-forget from the request handler).

    ``force_key``: re-parse a single MinIO object key (single-document reparse),
    bypassing the SHA-256 hash cache. doc_id is preserved via storage_uri upsert.

    ``re_ocr``: re_ocr=True 强制重 OCR(绕过 MinIO OCR 缓存);默认读缓存仅重跑分类+提取。
    """
    cmd = [
        sys.executable,  # same interpreter (venv) as the gateway process
        "-m",
        "scripts.cli",
        "--phase",
        phase,
        "--trigger",
        trigger,
        "--run-id",
        str(run_id),
    ]
    if force_key:
        cmd += ["--force-key", force_key]
    if re_ocr:
        cmd += ["--re-ocr"]
    # P2 LLM 兜底(spec §3): gateway 配置了三元组才注入;超时 30s 与验收门
    # 0.90 由技能侧 llm_fallback 默认值保证,不可达 → 整表 needs_review 不阻塞。
    cmd += _resolve_llm_args()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SKILL_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(_SKILL_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await crud.finish_run(
                session,
                run_id,
                status="completed",
                error=None,
            )
            logger.info("Pipeline run %s completed: %s", run_id, stdout.decode()[-500:])
            # The CLI logs per-doc warnings (e.g. "Failed to parse X: ...") to
            # stderr. On a successful run (exit 0) stderr was previously discarded,
            # hiding the reason when some docs failed inside an otherwise-OK run.
            # Surface it so progress {failed: N} is debuggable.
            err_tail = stderr.decode().strip()[-1500:]
            if err_tail:
                logger.info("Pipeline run %s stderr (per-doc warnings): %s", run_id, err_tail)
        else:
            err = stderr.decode()[-2000:] or f"exit code {proc.returncode}"
            await crud.finish_run(session, run_id, status="failed", error=err)
            # 兜底:子进程整体失败时,把仍卡在「解析中」的文档置为「解析失败」,
            # 否则它们会永远停在 解析中(用户要求:失败就是解析失败)。
            await crud.mark_stale_parsing_failed(session, f"解析任务失败: {err[:200]}")
            logger.warning("Pipeline run %s failed: %s", run_id, stderr.decode()[-500:])
    except FileNotFoundError:
        # The skill is not installed in this environment.
        err = f"skill not found at {_SKILL_DIR}"
        await crud.finish_run(session, run_id, status="failed", error=err)
        await crud.mark_stale_parsing_failed(session, f"解析任务失败: {err}")
    except Exception as exc:  # noqa: BLE001
        await crud.finish_run(session, run_id, status="failed", error=repr(exc))
        await crud.mark_stale_parsing_failed(session, f"解析任务异常: {exc!r}")
        logger.exception("Pipeline run %s raised", run_id)


def skill_dir() -> Path:
    return _SKILL_DIR
