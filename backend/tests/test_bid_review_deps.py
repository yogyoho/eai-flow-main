"""bid-review 入口依赖安全网:parse.py 直导入 openpyxl,但历史上仅经
deerflow-harness→markitdown[all,xlsx] 传递到运行时——markitdown 换 extras 即静默断供
(xlsx 入口全灭)。此测试锁死 base deps 显式声明,防止回归为传递依赖。
"""

from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_openpyxl_declared_in_base_dependencies():
    text = _PYPROJECT.read_text(encoding="utf-8")
    start = text.index("dependencies = [")
    # 行首 ] 作块边界——数组内 "uvicorn[standard]" 这类 extras 括号不能截断切片
    base_deps = text[start : text.index("\n]", start)]
    assert '"openpyxl' in base_deps, "openpyxl 必须是 backend base deps 显式声明(parse.py 直导入),禁止退化为 markitdown 传递依赖"
