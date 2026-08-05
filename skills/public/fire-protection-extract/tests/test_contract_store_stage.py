import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import contract_store

TMP = Path(tempfile.mkdtemp(prefix="fp_extract_test_"))
OLD_CONTRACTS_DIR = contract_store.CONTRACTS_DIR


def setup_function():
    contract_store.CONTRACTS_DIR = TMP / "contracts"
    contract_store.INDEX_PATH = contract_store.CONTRACTS_DIR / "_index.json"
    contract_store.CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)


def teardown_function():
    shutil.rmtree(TMP, ignore_errors=True)
    contract_store.CONTRACTS_DIR = OLD_CONTRACTS_DIR
    contract_store.INDEX_PATH = OLD_CONTRACTS_DIR / "_index.json"


def _struct(para_count=100, tables=None):
    return {
        "paras": [{"i": i, "text": f"p{i}"} for i in range(para_count)],
        "tables": tables or {},
        "headings": [],
    }


def test_save_and_find_by_stage():
    mapping = {"sources": [[{"kind": "range", "paras": [0, 2]}]]}
    struct = _struct()
    contract_store.save_contract("基地项目", "基础设计", mapping, struct)
    assert (contract_store.CONTRACTS_DIR / "基础设计" / "基地项目.json").exists()

    name, found, sim = contract_store.find_best(struct, stage="基础设计")
    assert name == "基地项目"
    assert found["sources"] == mapping["sources"]
    # 其他阶段查不到
    assert contract_store.find_best(struct, stage="初步设计") is None


def test_find_tie_breaks_to_newest_saved():
    s1, s2 = _struct(), _struct()
    contract_store.save_contract("同构A", "基础设计", {"sources": []}, s1)
    contract_store.save_contract("同构B", "基础设计", {"sources": [["newer"]]}, s2)
    name, found, _ = contract_store.find_best(s1, stage="基础设计")
    assert name == "同构B", "同指纹应命中后保存的契约"


def test_format_validation_rejects_old_anchor():
    old = {"sections": [{"sources": [{"kind": "para", "anchor": "xxx"}]}]}
    err = contract_store.validate_format(old)
    assert err, "旧字符串锚格式必须被识别为不合法"
    good = {"sources": [[{"kind": "range", "paras": [0, 1]}]]}
    assert contract_store.validate_format(good) is None
