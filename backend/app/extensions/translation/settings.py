"""Translation workbench runtime settings (EAI-CUSTOM).

Only non-secret values live here (currently the translation model name). The
settings file sits next to translation storage so the Gateway API and the
translation worker read the same value without a DB migration.

Resolution order for the model:
    1. UI setting (this file)
    2. EAI_TRANSLATION_MODEL environment variable
    3. first model declared in config.yaml
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SETTINGS_KEY = "translation_model"
_SETTINGS_FILE = "translation/settings.json"


def settings_path() -> Path:
    from app.extensions.config import get_extensions_config

    return Path(get_extensions_config().storage.base_path) / _SETTINGS_FILE


def read_translation_settings(path: Path | None = None) -> dict[str, Any]:
    p = path or settings_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_translation_settings(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def resolve_effective_model_name(
    setting: str | None = None,
    model_names: list[str] | None = None,
) -> str | None:
    """Return a valid config model name; invalid settings/env values fall through."""
    if model_names is None:
        from deerflow.config import get_app_config

        model_names = [m.name for m in get_app_config().models]
    if setting and setting in model_names:
        return setting
    env = os.environ.get("EAI_TRANSLATION_MODEL")
    if env and env in model_names:
        return env
    return model_names[0] if model_names else None
