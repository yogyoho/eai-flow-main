"""授权判定结果缓存。

EAI-CUSTOM (2026-09-22): 键必须是 (user_id, permission) 复合键。
历史实现只按 user_id 做键、值的语义却是"某一次查询的那个权限"——
在只查单一权限（system:access）时未暴露；本体动作层引入第二个权限后
会造成跨权限串味（把一个权限的放行结果当成另一个的）。见
docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3。

注：OntoStudio 是独立服务（无法 import app.*），持有同语义的手写副本
（ontostudio/backend/app/auth.py::_authz_cache）——两侧的键口径必须同步维护。
"""

from __future__ import annotations

import threading
import time
import uuid


class AuthzCache:
    """进程内 TTL 缓存。部署为单实例，进程内即可；失败方向恒为 fail-closed。"""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._data: dict[tuple[uuid.UUID, str], tuple[bool, float]] = {}
        self._lock = threading.Lock()

    def get(self, user_id: uuid.UUID, permission: str) -> bool | None:
        with self._lock:
            hit = self._data.get((user_id, permission))
            if hit is None:
                return None
            allowed, expires_at = hit
            if time.monotonic() >= expires_at:
                self._data.pop((user_id, permission), None)
                return None
            return allowed

    def put(self, user_id: uuid.UUID, permission: str, allowed: bool) -> None:
        with self._lock:
            self._data[(user_id, permission)] = (allowed, time.monotonic() + self._ttl)

    def invalidate_user(self, user_id: uuid.UUID) -> None:
        with self._lock:
            for key in [k for k in self._data if k[0] == user_id]:
                self._data.pop(key, None)
