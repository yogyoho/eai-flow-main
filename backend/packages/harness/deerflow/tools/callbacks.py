"""Lightweight callback registry for cross-layer communication.

EAI-CUSTOM: 本文件为 EAI 新增模块(非上游 deer-flow 的一部分)。因 harness 层(``deerflow.*``)
不可 import app 层(``app.*``,由 test_harness_boundary.py 守护),本注册表让 app 层注册回调、
harness 层在 ``present_files`` 工具执行后触发——用于把产出文件同步进 docmgr 文档空间
(AIDocument 后端回调自动同步)。升级/差分时按 ``EAI-CUSTOM`` 识别整个文件;若上游原生提供
等价的 harness↔app 跨层钩子,或 docmgr 同步不再需要,则删去本文件。

The harness layer (``deerflow.*``) cannot import the app layer (``app.*``).
This module provides a simple registry where the app layer can register
callbacks that the harness layer invokes at specific hook points.

Currently used by ``present_files`` to trigger document-space sync.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type: async callable(user_id: str, thread_id: str, virtual_paths: list[str]) -> dict
PresentFilesCallback = Callable[[str, str, list[str]], Awaitable[dict[str, Any] | None]]

# Module-level singleton registries
_present_files_callbacks: list[PresentFilesCallback] = []


def register_present_files_callback(fn: PresentFilesCallback) -> None:
    """Register a callback to fire after ``present_files`` tool execution.

    The callback receives (user_id, thread_id, virtual_paths) and should
    return a dict with sync statistics or None.
    """
    _present_files_callbacks.append(fn)
    logger.debug("Registered present_files callback: %s", fn.__qualname__)


async def fire_present_files_callbacks(
    user_id: str,
    thread_id: str,
    virtual_paths: list[str],
) -> list[dict[str, Any] | None]:
    """Invoke all registered present_files callbacks.

    Exceptions are caught per-callback so a failing sync never breaks
    the tool response.
    """
    results: list[dict[str, Any] | None] = []
    for cb in _present_files_callbacks:
        try:
            result = await cb(user_id, thread_id, virtual_paths)
            results.append(result)
        except Exception:
            logger.exception(
                "present_files callback %s failed (thread=%s)",
                cb.__qualname__,
                thread_id,
            )
            results.append(None)
    return results
