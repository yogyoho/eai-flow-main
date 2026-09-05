import asyncio
import logging
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.config import get_config
from langgraph.types import Command

from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.builtins import delivery_contract
from deerflow.tools.callbacks import fire_present_files_callbacks
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)

OUTPUTS_VIRTUAL_PREFIX = f"{VIRTUAL_PATH_PREFIX}/outputs"


def _get_thread_id(runtime: Runtime) -> str | None:
    """Resolve the current thread id from runtime context or RunnableConfig."""
    thread_id = runtime.context.get("thread_id") if runtime.context else None
    if thread_id:
        return thread_id

    runtime_config = getattr(runtime, "config", None) or {}
    thread_id = runtime_config.get("configurable", {}).get("thread_id")
    if thread_id:
        return thread_id

    try:
        return get_config().get("configurable", {}).get("thread_id")
    except RuntimeError:
        return None


def _normalize_presented_filepath(
    runtime: Runtime,
    filepath: str,
) -> str:
    """Normalize a presented file path to the `/mnt/user-data/outputs/*` contract.

    Accepts either:
    - A virtual sandbox path such as `/mnt/user-data/outputs/report.md`
    - A host-side thread outputs path such as
      `/app/backend/.deer-flow/threads/<thread>/user-data/outputs/report.md`

    Returns:
        The normalized virtual path.

    Raises:
        ValueError: If runtime metadata is missing or the path is outside the
            current thread's outputs directory.
    """
    if runtime.state is None:
        raise ValueError("Thread runtime state is not available")

    thread_id = _get_thread_id(runtime)
    if not thread_id:
        raise ValueError("Thread ID is not available in runtime context or runtime config")

    thread_data = runtime.state.get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    if not outputs_path:
        raise ValueError("Thread outputs path is not available in runtime state")

    outputs_dir = Path(outputs_path).resolve()
    stripped = filepath.lstrip("/")
    virtual_prefix = VIRTUAL_PATH_PREFIX.lstrip("/")

    if stripped == virtual_prefix or stripped.startswith(virtual_prefix + "/"):
        try:
            actual_path = get_paths().resolve_virtual_path(thread_id, filepath, user_id=resolve_runtime_user_id(runtime))
        except TypeError:
            actual_path = get_paths().resolve_virtual_path(thread_id, filepath)
    else:
        actual_path = Path(filepath).expanduser().resolve()

    try:
        relative_path = actual_path.relative_to(outputs_dir)
    except ValueError as exc:
        raise ValueError(f"Only files in {OUTPUTS_VIRTUAL_PREFIX} can be presented: {filepath}") from exc

    return f"{OUTPUTS_VIRTUAL_PREFIX}/{relative_path.as_posix()}"


# ── START EAI-CUSTOM (bug-2225; bug-3109 v4 通用化) 交付契约门 ───────────────
# 背景: geological-report 等管线技能以 build_output.py 产交付 .md（成功后写
# outputs/delivery_manifest.json 放行凭据）。E2E 实测 agent 可绕过管线手拼 .md 并
# present 成功（bug-2225）。管线脚本沿祖先链在 outputs/ 落 .delivery-contract 契约
# 标记——有标记的线程，未经管线产出的 .md 一律拒绝（工具层报错→agent 循环内自纠，
# 零用户交互）。无标记线程零影响（全部放行）。同步层门：app/gateway/routers/artifacts.py
# （GET 403）与 app/extensions/workspace/sandbox_sync.py（跳过旁路同步）。
# v4 通用化（bug-3109，设计稿 WP-2.3）: bid-proposal-writing 交付物从单文件变册集，
# 单名契约不可承载——manifest 契约升级为 skill/version/deliverables[]/aux_md，
# 向后兼容 geo 旧单名 deliverable；解析收口到 delivery_contract.py（三端共用）。
# 升级注意: 上游升级本文件时保留本块；门判据只经 delivery_contract.resolve_manifest
# 读取 outputs/ 下两个文件名级判据（.delivery-contract / delivery_manifest.json），
# 不在此处自行解析 manifest 字段。
DELIVERY_CONTRACT_NAME = delivery_contract.DELIVERY_CONTRACT_NAME
DELIVERY_MANIFEST_NAME = delivery_contract.DELIVERY_MANIFEST_NAME


def _thread_outputs_dir(runtime: Runtime) -> Path | None:
    """线程交付目录（来自 thread_data.outputs_path）；缺失→None（门不启用）。"""
    thread_data = (runtime.state or {}).get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    return Path(outputs_path) if outputs_path else None


def _delivery_gate_error(outputs_dir: Path, normalized_paths: list[str]) -> str | None:
    """契约门判据（同步体，经 asyncio.to_thread 调用，勿在事件循环内直呼）：

    - 无 .delivery-contract 标记 → None（非管线线程，全放行）
    - present 清单无 .md → None（只交付图片/JSON 等，不涉报告）
    - 有标记无 delivery_manifest.json → 管线从未成功 build → 拒
    - manifest 未知契约/版本过高 → 显式拒（bug-3109, 3A 向前兼容, 不静默放行）
    - manifest 在场但存在 ∉ deliverables[]∪aux_md 的 .md → 手拼/散文件混入 → 整单拒
    """
    if not (outputs_dir / delivery_contract.DELIVERY_CONTRACT_NAME).exists():
        return None
    md_names = [Path(p).name for p in normalized_paths if Path(p).suffix.lower() == ".md"]
    if not md_names:
        return None
    status, data = delivery_contract.resolve_manifest(outputs_dir)
    if status != delivery_contract.STATUS_OK:
        return delivery_contract.rebuild_hint(status, data)
    allowed: set[str] = data["allowed"]
    skill = data.get("skill")
    rogue = sorted({name for name in md_names if name not in allowed})
    if rogue:
        if skill:
            return (
                f"交付门 FAIL（bug-3109）：{rogue} 不是 {skill} 管线申报的交付物（deliverables/aux_md 白名单外）——"
                f"手拼/散 .md 禁止交付（整单拒收）。请把非交付 .md 移出 outputs/ 并重跑 "
                f"skills/public/{skill}/scripts/build_output.py（rc=0）后再 present_files。"
            )
        deliverable = sorted(allowed)[0] if len(allowed) == 1 else ""
        return f"交付门 FAIL（bug-2225）：{rogue} 不是管线交付物（本线程唯一 .md 交付={deliverable!r}）——手拼/散 .md 禁止交付。请把非交付 .md 移出 outputs/ 并重跑 build_output.py（rc=0）后再 present_files。"
    return None


# ── END EAI-CUSTOM (bug-2225) ────────────────────────────────────────────────


@tool("present_files", parse_docstring=True)
async def present_file_tool(
    runtime: Runtime,
    filepaths: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Make files visible to the user for viewing and rendering in the client interface.

    When to use the present_files tool:

    - Making any file available for the user to view, download, or interact with
    - Presenting multiple related files at once
    - After creating files that should be presented to the user

    When NOT to use the present_files tool:
    - When you only need to read file contents for your own processing
    - For temporary or intermediate files not meant for user viewing

    Notes:
    - You should call this tool after creating files and moving them to the `/mnt/user-data/outputs` directory.
    - This tool can be safely called in parallel with other tools. State updates are handled by a reducer to prevent conflicts.

    Args:
        filepaths: List of absolute file paths to present to the user. **Only** files in `/mnt/user-data/outputs` can be presented.
    """
    try:
        normalized_paths = [_normalize_presented_filepath(runtime, filepath) for filepath in filepaths]
    except ValueError as exc:
        return Command(
            update={"messages": [ToolMessage(f"Error: {exc}", tool_call_id=tool_call_id)]},
        )

    # ── START EAI-CUSTOM (bug-2225) 交付契约门：未经管线产出的 .md 拒绝 present ──
    # 门必须位于 bug-1145 docmgr 同步块之前——被拒的 present 绝不触发文档空间同步。
    # 文件系统探测经 asyncio.to_thread 下放（gateway 运行于 Blockbuster 阻塞 IO 检测下）。
    outputs_dir = _thread_outputs_dir(runtime)
    if outputs_dir:
        gate_error = await asyncio.to_thread(_delivery_gate_error, outputs_dir, normalized_paths)
        if gate_error is not None:
            return Command(update={"messages": [ToolMessage(gate_error, tool_call_id=tool_call_id)]})
    # ── END EAI-CUSTOM (bug-2225) ────────────────────────────────────────────────

    # EAI-CUSTOM (bug-1145): fire registered present_files callbacks so the app
    # layer (docmgr) auto-syncs presented outputs into the document space
    # (AIDocument rows). The registry lives in deerflow.tools.callbacks and is
    # populated by app.gateway.app at startup; this is its intended fire point.
    # Best-effort: a sync failure must never break the tool's primary job of
    # presenting files to the user (fire_present_files_callbacks already swallows
    # per-callback errors; this try/except is defense-in-depth for the whole path).
    # Upgrade note (deerflow upstream): upstream present_files has no callback
    # hook; on upstream sync, re-apply this async fire block after normalized_paths
    # is computed. START EAI-CUSTOM
    try:
        await fire_present_files_callbacks(
            resolve_runtime_user_id(runtime),
            _get_thread_id(runtime) or "",
            normalized_paths,
        )
    except Exception:
        logger.warning("present_files callback fire failed", exc_info=True)
    # END EAI-CUSTOM (bug-1145)

    # The merge_artifacts reducer will handle merging and deduplication
    return Command(
        update={
            "artifacts": normalized_paths,
            "messages": [ToolMessage("Successfully presented files", tool_call_id=tool_call_id)],
        },
    )
