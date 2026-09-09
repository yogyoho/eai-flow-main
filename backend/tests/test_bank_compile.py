"""bank_compile 样例入库工具：脱敏/切片/深度统计/产物确定性（纯函数契约）。"""

import importlib.util
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "skills" / "public" / "bid-proposal-writing" / "scripts"

# importlib 按路径加载且模块名唯一（不占 sys.modules['bank_compile']）——geological-report
# 技能 scripts/ 下有同名 bank_compile.py（test_geo_sample_bank_compile.py 裸名 `import bank_compile`），
# sys.path+裸名导入会让两测试文件按收集顺序互抢 sys.modules 缓存，全量跑必挂一边。
_spec = importlib.util.spec_from_file_location("bid_bank_compile", SCRIPTS_DIR / "bank_compile.py")
assert _spec is not None and _spec.loader is not None
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)


@pytest.fixture
def tender_md(tmp_path):
    md = (
        "# 投标文件格式\n\n"
        "## 一、投标函\n\n"
        "致：江西师范大学。我方愿以总金额 1,280,000.00 元（含税）承接本项目，"
        "统一社会信用代码 91360100MA001AB2CD 为准。联系电话 13800138000。\n\n"
        "## 二、法定代表人身份证明\n\n"
        "身份证号 360102199001011234，姓名张三。\n\n"
        "## 三、开标一览表\n\n"
        "| 序号 | 名称 | 数量 | 单价(元) |\n| --- | --- | --- | --- |\n"
        "| 1 | 课堂观测终端 | 200 | 3,500.00 |\n\n"
        "以上报价含运输安装调试费用合计 700,000.00 元。\n"
    )
    p = tmp_path / "tender.md"
    p.write_text(md, encoding="utf-8")
    return p


def test_load_text_md(tender_md):
    assert bc.load_text(tender_md).startswith("# 投标文件格式")


def test_split_chapters_by_h1h2(tender_md):
    text = bc.load_text(tender_md)
    chapters = bc.split_chapters(text)
    titles = [c["title"] for c in chapters]
    assert any("投标函" in t for t in titles), "H2 章边界可切"
    assert all(c["text"].strip() for c in chapters), "零空章"


def test_paragraph_lengths(tender_md):
    text = bc.load_text(tender_md)
    lens = bc.paragraph_lengths(text)
    assert all(isinstance(x, int) and x >= 0 for x in lens)
