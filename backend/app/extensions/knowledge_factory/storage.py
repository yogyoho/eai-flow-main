"""Template storage - JSON snapshot file read/write."""

import json
import logging
from pathlib import Path
from typing import Optional

from app.extensions.config import get_extensions_config

logger = logging.getLogger(__name__)

# 快照文件存放根目录
SNAPSHOT_ROOT = "extraction_templates"


def get_snapshot_dir(domain: str, template_name: str, version: str) -> Path:
    """获取模板快照目录路径。"""
    config = get_extensions_config()
    base = Path(config.storage.base_path)
    return base / SNAPSHOT_ROOT / domain / template_name / f"v{version.lstrip('v')}"


def save_snapshot(
    domain: str,
    template_name: str,
    version: str,
    template_data: dict,
) -> Path:
    """保存模板快照到 JSON 文件。"""
    dir_path = get_snapshot_dir(domain, template_name, version)
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / "template.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(template_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved template snapshot to {file_path}")
    return file_path


def load_snapshot(
    domain: str,
    template_name: str,
    version: str,
) -> Optional[dict]:
    """从 JSON 文件加载模板快照。"""
    file_path = get_snapshot_dir(domain, template_name, version) / "template.json"
    if not file_path.exists():
        return None

    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load snapshot {file_path}: {e}")
        return None


def delete_snapshot(
    domain: str,
    template_name: str,
    version: str,
) -> bool:
    """删除模板快照目录。"""
    dir_path = get_snapshot_dir(domain, template_name, version)
    if not dir_path.exists():
        return False

    try:
        import shutil
        shutil.rmtree(dir_path)
        logger.info(f"Deleted template snapshot at {dir_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete snapshot {dir_path}: {e}")
        return False


def export_template_json(
    domain: str,
    template_name: str,
    version: str,
) -> Optional[bytes]:
    """导出模板为 JSON 字节串（用于下载）。"""
    data = load_snapshot(domain, template_name, version)
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
