"""测试套件共享脚手架：把技能 scripts/ 注入 sys.path（沿 test_ingest_bug3229 L20-23 先例）。"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def run_cli(main_fn, argv):
    """CLI main() 契约：返回 int rc、输出走 print——重定向捕获返回 (rc, stdout)。

    T6 质量评审 M2：自 test_profile.run 泛化抽取为套件级基础设施；
    test_ingest_forms.run 改为薄包装（行为等价，用例不动）。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main_fn(argv)
    return rc, buf.getvalue()
