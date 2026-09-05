"""Test configuration for the backend test suite.

Sets up sys.path and pre-mocks modules that would cause circular import
issues when unit-testing lightweight config/registry code in isolation.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Make 'app' and 'deerflow' importable from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

# EAI-CUSTOM (geo-batch-cli P4): host pytest env 毒化治理——仓库根 .env 是容器部署
# env 文件（DEER_FLOW_* 全是 /app 容器路径），两条模块级 load_dotenv(override=False)
# 会把它吸进 host 测试进程（~190 假失败 + requires_llm 真跑 LLM 挂死）。
# setdefault 空串即屏蔽（override=False 不覆盖已存在键）；容器内真值由 compose 注入不受影响。
# 维护契约：新增 DEER_FLOW_*/OPENAI 外键时须同步此清单。
for _k in (
    "DEER_FLOW_DEV_MODE",
    "DEER_FLOW_HOME",
    "DEER_FLOW_CONFIG_PATH",
    "DEER_FLOW_EXTENSIONS_CONFIG_PATH",
    "DEER_FLOW_DOCKER_SOCKET",
    "DEER_FLOW_REPO_ROOT",
    "DEER_FLOW_HOST_BASE_DIR",
    "DEER_FLOW_HOST_SKILLS_PATH",
    "OPENAI_API_KEY",
):
    os.environ.setdefault(_k, "")

# Break the circular import chain that exists in production code:
#   deerflow.subagents.__init__
#     -> .executor (SubagentExecutor, SubagentResult)
#       -> deerflow.agents.thread_state
#         -> deerflow.agents.__init__
#           -> lead_agent.agent
#             -> subagent_limit_middleware
#               -> deerflow.subagents.executor  <-- circular!
#
# By injecting a mock for deerflow.subagents.executor *before* any test module
# triggers the import, __init__.py's "from .executor import ..." succeeds
# immediately without running the real executor module.
_executor_mock = MagicMock()
_executor_mock.SubagentExecutor = MagicMock
_executor_mock.SubagentResult = MagicMock
_executor_mock.SubagentStatus = MagicMock
_executor_mock.MAX_CONCURRENT_SUBAGENTS = 3
_executor_mock.get_background_task_result = MagicMock()

sys.modules["deerflow.subagents.executor"] = _executor_mock


@pytest.fixture()
def provisioner_module():
    """Load docker/provisioner/app.py as an importable test module.

    Shared by test_provisioner_kubeconfig and test_provisioner_pvc_volumes so
    that any change to the provisioner entry-point path or module name only
    needs to be updated in one place.
    """
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "docker" / "provisioner" / "app.py"
    spec = importlib.util.spec_from_file_location("provisioner_app_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        if previous_module is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous_module


# ---------------------------------------------------------------------------
# Auto-set user context for every test unless marked no_auto_user
# ---------------------------------------------------------------------------
#
# Repository methods read ``user_id`` from a contextvar by default
# (see ``deerflow.runtime.user_context``). Without this fixture, every
# pre-existing persistence test would raise RuntimeError because the
# contextvar is unset. The fixture sets a default test user on every
# test; tests that explicitly want to verify behaviour *without* a user
# context should mark themselves ``@pytest.mark.no_auto_user``.


@pytest.fixture(autouse=True)
def _reset_skill_storage_singleton():
    """Reset the SkillStorage singleton between tests to prevent cross-test contamination."""
    try:
        from deerflow.skills.storage import reset_skill_storage
    except ImportError:
        yield
        return
    reset_skill_storage()
    try:
        yield
    finally:
        reset_skill_storage()


@pytest.fixture(autouse=True)
def _reset_frozen_checkpoint_channel_mode(monkeypatch):
    """Reset the process-global frozen checkpoint channel mode between tests.

    Production treats ``checkpoint_channel_mode`` (and the delta
    ``snapshot_frequency`` frozen alongside it) as restart-required: the
    first client/app freezes it for the process. The test suite builds many
    clients and apps with different modes in one process, so the freeze must
    not leak across tests. Mirrors the per-test ``monkeypatch.setattr``
    resets already used in test_client.py / test_lead_agent_model_resolution.py.
    """
    from deerflow.runtime import checkpoint_mode

    monkeypatch.setattr(checkpoint_mode, "_frozen_checkpoint_channel_mode", None)
    monkeypatch.setattr(checkpoint_mode, "_frozen_checkpoint_snapshot_frequency", None)
    yield


@pytest.fixture(autouse=True)
def _restore_title_config_singleton():
    """Reset ``_title_config`` to its pristine default after every test.

    ``AppConfig.from_file()`` writes the on-disk ``title`` block into the
    module-level singleton (``config/app_config.py`` calls
    ``load_title_config_from_dict``). Any test that loads the real
    ``config.yaml`` therefore leaves the singleton in a state that
    ``test_title_middleware_core_logic.py`` does not expect; that suite
    relies on the pristine ``TitleConfig()`` default (``enabled=True``).
    We restore the default after every test so test files stay
    independent regardless of order.
    """
    try:
        from deerflow.config.title_config import reset_title_config
    except ImportError:
        yield
        return

    try:
        yield
    finally:
        reset_title_config()


@pytest.fixture(autouse=True)
def _isolate_trace_context():
    """Give every test an unbound request trace context.

    Entry points bind a trace id unconditionally, and ``ensure_trace_id()``
    binds one for the remainder of whatever context it is called in. pytest
    runs the whole session in a single context, so without this reset one
    test's trace would leak into the next and quietly satisfy assertions
    about ids the test under exercise never bound.
    """
    from deerflow.trace_context import bind_trace_id, reset_trace_id

    token = bind_trace_id(None)
    try:
        yield
    finally:
        reset_trace_id(token)


@pytest.fixture(autouse=True)
def _auto_user_context(request):
    """Inject a default ``test-user-autouse`` into the contextvar.

    Opt-out via ``@pytest.mark.no_auto_user``. Uses lazy import so that
    tests which don't touch the persistence layer never pay the cost
    of importing runtime.user_context.
    """
    if request.node.get_closest_marker("no_auto_user"):
        yield
        return

    try:
        from deerflow.runtime.user_context import (
            reset_current_user,
            set_current_user,
        )
    except ImportError:
        yield
        return

    user = SimpleNamespace(id="test-user-autouse", email="test@local")
    token = set_current_user(user)
    try:
        yield
    finally:
        reset_current_user(token)


# ---------------------------------------------------------------------------
# Skill-script module isolation (bug-2223)
# ---------------------------------------------------------------------------
# Multiple skills publish same-named top-level scripts (water-drainage-report
# and geological-report both have formula_runner.py / chapter_planner.py;
# bid/water/geological all have snapshot.py; geological-report and
# bid-proposal-writing both have ingest.py / build_output.py). A module-level
# or lazily-imported ``formula_runner`` in one test file poisons the
# process-global sys.modules for every later in-process import in another
# skill's tests: in a full-suite (alphabetical) run the geological tests fail
# with ``AttributeError: module 'formula_runner' has no attribute 'q'`` and
# bid tests invoke another skill's ingest/snapshot CLI. Fix: while a test
# whose module defines ``SCRIPTS`` (or ``SCRIPTS_DIR``) runs, the colliding
# names resolve from THAT directory via a meta-path finder. Hook-based (not a
# fixture) on purpose: pytest_runtest_setup fires before session/module-scoped
# fixtures of the item instantiate, so fixtures importing these names are
# covered too.

_SKILL_SCRIPT_NAMES = ("build_output", "chapter_planner", "ingest", "formula_runner", "snapshot")
_current_skill_scripts: Path | None = None


class _SkillScriptsFinder:
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _SKILL_SCRIPT_NAMES or _current_skill_scripts is None:
            return None
        script = _current_skill_scripts / f"{fullname}.py"
        if not script.is_file():
            return None
        return importlib.util.spec_from_file_location(fullname, script)


sys.meta_path.insert(0, _SkillScriptsFinder())


def _item_scripts_dir(item) -> Path | None:
    module = item.getparent(pytest.Module)
    if module is None:
        return None
    for attr in ("SCRIPTS", "SCRIPTS_DIR"):
        scripts = getattr(module.obj, attr, None)
        if scripts and Path(scripts).is_dir():
            return Path(scripts)
    return None


def pytest_runtest_setup(item):
    global _current_skill_scripts
    _current_skill_scripts = _item_scripts_dir(item)
    if _current_skill_scripts is not None:
        # drop cached bindings so fresh imports re-resolve through the finder
        for name in _SKILL_SCRIPT_NAMES:
            if (_current_skill_scripts / f"{name}.py").is_file():
                sys.modules.pop(name, None)


def pytest_runtest_teardown(item, nextitem):
    global _current_skill_scripts
    _current_skill_scripts = None
