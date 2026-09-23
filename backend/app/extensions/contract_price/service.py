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


def _env_value(v: str | None) -> str:
    """解析 "$ENV_VAR" 形式的配置值;未设置返回空串。"""
    v = str(v or "").strip()
    if v.startswith("$"):
        return os.environ.get(v[1:], "").strip()
    return v


def _platform_llm_fallback() -> list[tuple[str, str]]:
    """系统模型清单(config.yaml models[])回退桥: 取第一个 OpenAI 兼容模型
    (use=langchain_openai:*,与 llm_fallback 的 chat-completions 协议匹配)
    解析为 (flag, value) 三元组。

    EAI-CUSTOM (2026-09-22): cpa 自身 llm_* 未配置时零配置开箱——设置页模型
    列表的服务端真源就是这份清单(浏览器 localStorage 的个人选择服务端不可见)。
    app→harness 导入合法;清单不可读/无兼容模型 → [] 层关闭。"""
    try:
        from deerflow.config import get_app_config

        for m in get_app_config().models or []:
            use = str(getattr(m, "use", "") or "")
            base_url = _env_value(getattr(m, "base_url", None))
            api_key = _env_value(getattr(m, "api_key", None))
            model = str(getattr(m, "model", "") or "").strip()
            if not (use.startswith("langchain_openai:") and base_url and api_key and model):
                continue
            return [
                ("--llm-base-url", base_url),
                ("--llm-key", api_key),
                ("--llm-model", model),
            ]
    except Exception:  # noqa: BLE001 — 桥接失败等同层关闭,绝不阻塞管线触发
        pass
    return []


def _resolve_llm_args() -> list[str]:
    """Read the LLM triple from the extension config and build --llm-* argv flags.

    优先级: cpa 扩展自身 llm_*(专用模型) > 系统模型清单回退桥 > [] 层关闭。
    任一要素为空或 $ENV 未解析 → 跳到下一级;最终 [] 不传——子进程行为与未引入
    本机制前完全一致。"""
    try:
        cfg = crud.load_config()
    except Exception:  # noqa: BLE001 — 配置不可读时绝不阻塞管线触发
        return []
    vals: list[tuple[str, str]] = []
    for field_name, flag in _LLM_FLAG_MAP:
        v = _env_value(getattr(cfg, field_name, None))
        if not v:
            vals = []  # 三元组不完整 → 整组放弃,走系统清单回退
            break
        vals.append((flag, v))
    if not vals:
        vals = _platform_llm_fallback()
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
    # EAI-CUSTOM (2026-09-23 货物分组规则): 聚类维度开关随 env 下发(CLI 侧
    # CPA_CLUSTER_BY_* 只在 cluster 相位消费);读不到配置按全开(兼容默认)。
    # 2026-09-23 续: eps/min_samples 同路接线——此前设置页这两个值从未到达 CLI。
    try:
        _cfg = crud.load_config()
        env["CPA_CLUSTER_BY_SPEC"] = "1" if _cfg.cluster_by_spec else "0"
        env["CPA_CLUSTER_BY_CATEGORY"] = "1" if _cfg.cluster_by_category else "0"
        env["CPA_CLUSTER_EPS"] = str(_cfg.cluster_eps)
        env["CPA_CLUSTER_MIN_SAMPLES"] = str(int(_cfg.cluster_min_samples))
    except Exception:  # noqa: BLE001 — 配置不可读不阻塞管线触发
        pass

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
