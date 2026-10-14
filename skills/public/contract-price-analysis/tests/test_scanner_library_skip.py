"""scanner 跳过 library/ 前缀（cpa v3 文件库档案区, spec 2026-10-14 §1.2）。

文件库上传的对象落在 library/ 下;只有「加入解析」服务端拷到扫描区根的对象
才允许被管线拾取。previews/ 的既有跳过行为一并回归。
"""

from types import SimpleNamespace

from scripts.document_scanner import scan_changed


class FakeStore:
    def __init__(self, names):
        self._names = names

    def list_objects(self):
        return [SimpleNamespace(object_name=n, is_dir=False, size=10) for n in self._names]

    def sha256(self, key):
        return "h-" + key


def test_scanner_skips_library_and_previews_prefixes():
    store = FakeStore(["合同A.pdf", "library/f1/合同B.pdf", "previews/docid/page-1.png"])
    changed = scan_changed(store, {})
    assert [c["key"] for c in changed] == ["合同A.pdf"]


def test_library_prefix_skipped_even_with_cache_entry():
    # 即使 library/ 对象带 cache(理论上不该有),也不得被拾取
    store = FakeStore(["library/f1/a.pdf"])
    changed = scan_changed(store, {"library/f1/a.pdf": {"size": 11, "hash": "old"}})
    assert changed == []
