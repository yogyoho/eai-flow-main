"""seed 库双份镜像 parity 测试: 技能源真相 ↔ backend 默认注入必须逐字段一致。

skills/public 的 pytest 不在 CI 里跑;本文件保证两份 DEFAULT_TABLE_SEEDS 漂移时
backend CI 必红。区别于 skills/custom 的 gitignored parity 前例
(test_contract_price_model_parity.py 因文件缺失而 skip)——本测试指向的
skills/public/.../seed_library.py 是已提交文件,故无 skipif。

技能模块按路径装载(importlib.util.spec_from_file_location,同
test_coal_eia_report_v2_scripts.py 前例),以私有模块名注册 sys.modules,
不污染技能包命名空间。
"""

import importlib.util
import sys
from pathlib import Path

from app.extensions.contract_price import seed_defaults as backend_mod

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_SEED_LIBRARY = (
    _REPO_ROOT / "skills" / "public" / "contract-price-analysis" / "scripts" / "seed_library.py"
)


def _load_skill_seed_library():
    name = "cpa_skill_seed_library"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, _SKILL_SEED_LIBRARY)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def test_seed_library_mirror_in_sync():
    """skill seed_library.py 与 backend seed_defaults.py 深比较必须全等。"""
    skill_mod = _load_skill_seed_library()
    assert skill_mod.DEFAULT_TABLE_SEEDS == backend_mod.DEFAULT_TABLE_SEEDS
