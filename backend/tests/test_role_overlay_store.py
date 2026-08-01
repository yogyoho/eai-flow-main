"""Tests for RoleOverlayStore — atomic write + mtime optimistic lock."""

import pytest

from app.extensions.role.service import RoleOverlayStore


def test_read_merge_write_roundtrip(tmp_path):
    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("""
roles:
  custom: { display_name: "自定义", permissions: ["doc:read"], nav: [], data_scopes: [] }
disabled_roles: []
""", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay))
    data = store.read()
    assert "custom" in data["roles"]

    data["roles"]["custom2"] = {
        "display_name": "自定义2", "permissions": ["kb:read"], "nav": [], "data_scopes": []
    }
    store.write(data)
    reloaded = store.read()
    assert "custom2" in reloaded["roles"]


def test_stale_overlay_rejected(tmp_path):
    import os

    overlay = tmp_path / "roles_custom.yaml"
    overlay.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay))
    mtime0 = store.mtime()
    overlay.write_text(
        "roles:\n  a: { display_name: 'A', permissions: [], nav: [], data_scopes: [] }\ndisabled_roles: []\n",
        encoding="utf-8",
    )
    # Simulate a concurrent edit advancing the file mtime. Direct re-write is
    # insufficient on coarse-mtime filesystems (two writes within the same
    # resolution quantum keep an identical st_mtime), so advance it explicitly.
    os.utime(overlay, (mtime0 + 2.0, mtime0 + 2.0))
    with pytest.raises(RuntimeError):
        store.write(store.read(), expect_mtime=mtime0)
