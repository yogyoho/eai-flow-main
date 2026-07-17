"""SkillStorage singleton + reflection-based factory.

Mirrors the pattern used by ``deerflow/sandbox/sandbox_provider.py``.
"""

from __future__ import annotations

import threading

from deerflow.skills.storage.local_skill_storage import LocalSkillStorage
from deerflow.skills.storage.skill_storage import SkillStorage

_default_skill_storage: SkillStorage | None = None
_default_skill_storage_config: object | None = None  # AppConfig identity the singleton was built from
_skill_storage_lock = threading.Lock()


def get_or_new_skill_storage(**kwargs) -> SkillStorage:
    """Return a ``SkillStorage`` instance — either a new one or the process singleton.

    **New instance** is created (never cached) when:
    - ``skills_path`` is provided — uses it as the ``host_path`` override (class still resolved via config).
    - ``app_config`` is provided — constructs a storage from ``app_config.skills``
      so that per-request config (e.g. Gateway ``Depends(get_config)``) is respected
      without polluting the process-level singleton.

    **Singleton** is returned (created on first call, then reused) when neither
    ``skills_path`` nor ``app_config`` is given — uses ``get_app_config()`` to
    resolve the active configuration.
    """
    global _default_skill_storage, _default_skill_storage_config

    from deerflow.config import get_app_config
    from deerflow.config.skills_config import SkillsConfig

    def _make_storage(skills_config: SkillsConfig, *, host_path: str | None = None, **kwargs) -> SkillStorage:
        from deerflow.reflection import resolve_class

        cls = resolve_class(skills_config.use, SkillStorage)
        return cls(
            host_path=host_path if host_path is not None else str(skills_config.get_skills_path()),
            container_path=skills_config.container_path,
            **kwargs,
        )

    skills_path = kwargs.pop("skills_path", None)
    app_config = kwargs.pop("app_config", None)

    if skills_path is not None:
        if app_config is not None:
            return _make_storage(app_config.skills, host_path=str(skills_path), **kwargs)
        # No app_config: use a default SkillsConfig so we never need to read config.yaml
        # when the caller has already supplied an explicit host path.
        from deerflow.config.skills_config import SkillsConfig

        return _make_storage(SkillsConfig(), host_path=str(skills_path), **kwargs)

    if app_config is not None:
        return _make_storage(app_config.skills, **kwargs)

    # If the singleton was manually injected (e.g. in tests) without a config
    # identity (_default_skill_storage_config is None), skip get_app_config()
    # entirely to avoid requiring a config.yaml on disk.
    if _default_skill_storage is not None and _default_skill_storage_config is None:
        return _default_skill_storage

    app_config_now = get_app_config()

    # Build the singleton under the lock with a double-check so racing cold-start
    # callers construct exactly one instance, and reset_skill_storage() can't null
    # the global out from under a concurrent read. We construct *inside* the lock
    # — mirroring get_memory_storage() rather than sandbox_provider's build-outside-
    # then-discard-the-loser — because SkillStorage has no teardown hook, so an
    # orphaned instance from a losing racer could not be cleaned up.
    with _skill_storage_lock:
        if _default_skill_storage is None or _default_skill_storage_config is not app_config_now:
            _default_skill_storage = _make_storage(app_config_now.skills, **kwargs)
            _default_skill_storage_config = app_config_now
        return _default_skill_storage


def reset_skill_storage() -> None:
    """Clear the cached singleton (used in tests and hot-reload scenarios)."""
    global _default_skill_storage, _default_skill_storage_config
    with _skill_storage_lock:
        _default_skill_storage = None
        _default_skill_storage_config = None


# ponytail: upstream compat — returns a user-scoped storage or falls back to singleton
def get_or_new_user_skill_storage(user_id: str, **kwargs) -> SkillStorage:
    """Return a SkillStorage for *user_id*, falling back to the process singleton."""
    from deerflow.config.paths import make_safe_user_id
    from deerflow.skills.storage.user_scoped_skill_storage import UserScopedSkillStorage

    app_config = kwargs.pop("app_config", None)
    safe_id = make_safe_user_id(user_id)

    if app_config is not None:
        return UserScopedSkillStorage(safe_id, app_config=app_config, **kwargs)

    # Fall back to the shared singleton (backward compat)
    return get_or_new_skill_storage(**kwargs)

def user_should_see_legacy_skills(user_id: str, **kwargs) -> bool:
    """Return whether discovery exposes any LEGACY skills for this user."""
    from deerflow.skills.storage.user_scoped_skill_storage import UserScopedSkillStorage
    from deerflow.skills.types import SkillCategory

    if kwargs:
        from deerflow.config.paths import make_safe_user_id

        storage = UserScopedSkillStorage(make_safe_user_id(user_id), **kwargs)
    else:
        storage = get_or_new_user_skill_storage(user_id)
    return any(
        (skill.category.value if hasattr(skill.category, "value") else skill.category) == SkillCategory.LEGACY.value
        for skill in storage.load_skills(enabled_only=False)
    )


__all__ = [
    "LocalSkillStorage",
    "SkillStorage",
    "get_or_new_skill_storage",
    "get_or_new_user_skill_storage",
    "reset_skill_storage",
    "user_should_see_legacy_skills",
]
