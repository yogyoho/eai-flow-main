"""Pipeline orchestration service for the management API.

Triggers the agent-skill pipeline (``skills/custom/contract-price-analysis``) as
a subprocess so the Gateway never imports the gitignored skill package directly.
The skill's CLI writes its results to the shared ``cpa_`` tables (same DB), which
this extension reads back. The run is recorded in ``cpa_run_history``.
"""

import asyncio
import sys
import logging
import os
import shlex
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.contract_price import crud

logger = logging.getLogger(__name__)

# Skill directory resolved relative to the repo root (backend/ is cwd at runtime).
_REPO_ROOT = Path(__file__).resolve().parents[4]  # backend/app/extensions/contract_price -> repo root
_SKILL_DIR = _REPO_ROOT / "skills" / "custom" / "contract-price-analysis"


async def run_pipeline_subprocess(
    session: AsyncSession,
    run_id: UUID,
    mode: str = "table",
    trigger: str = "manual",
    phase: str = "parse",
    force_key: str | None = None,
) -> None:
    """Run the skill CLI as a subprocess and record the outcome.

    ``phase``: "parse" (scan→OCR→extract→persist items) or "cluster" (cluster
    confirmed/skipped docs' items). Designed to run in a background task
    (fire-and-forget from the request handler).

    ``force_key``: re-parse a single MinIO object key (single-document reparse),
    bypassing the SHA-256 hash cache. doc_id is preserved via storage_uri upsert.
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
        else:
            await crud.finish_run(
                session,
                run_id,
                status="failed",
                error=stderr.decode()[-2000:] or f"exit code {proc.returncode}",
            )
            logger.warning("Pipeline run %s failed: %s", run_id, stderr.decode()[-500:])
    except FileNotFoundError:
        # The skill is not installed in this environment.
        await crud.finish_run(
            session,
            run_id,
            status="failed",
            error=f"skill not found at {_SKILL_DIR}",
        )
    except Exception as exc:  # noqa: BLE001
        await crud.finish_run(session, run_id, status="failed", error=repr(exc))
        logger.exception("Pipeline run %s raised", run_id)


def skill_dir() -> Path:
    return _SKILL_DIR
