"""bank_compile 样例入库工具：脱敏/切片/深度统计/产物确定性（纯函数契约）。"""

import importlib.util
import zipfile
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
        "### 2.1 三级标题不应切分\n\n"
        "三级标题并入本章正文，不另立章。\n\n"
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


def test_load_text_md_gbk_fallback(tmp_path, capsys):
    """M-7：非 UTF-8 md 退回 gb18030 解码 + stderr 提示（真实标书常有 GBK 导出）。"""
    p = tmp_path / "gbk.md"
    p.write_bytes("## 一、投标函\n\n报价含税。".encode("gb18030"))
    assert bc.load_text(p).startswith("## 一、投标函")
    assert "gb18030" in capsys.readouterr().err


def test_load_text_md_undecodable_actionable_error(tmp_path):
    """M-7：UTF-8/gb18030 双败 → 可操作 ValueError（带处置指引，不裸抛 UnicodeDecodeError）。"""
    p = tmp_path / "bad.md"
    p.write_bytes(b"\xff\xfe\x00\x00")  # 0xFF 非 gb18030 合法首字节、亦非 UTF-8
    with pytest.raises(ValueError, match="UTF-8"):
        bc.load_text(p)


def test_split_chapters_by_h1h2(tender_md):
    text = bc.load_text(tender_md)
    chapters = bc.split_chapters(text)
    assert len(chapters) == 3, "I-2: H3 不误切恰 3 章, H1 封面不立章"
    assert [c["level"] for c in chapters] == [2, 2, 2], "I-2: 只收 H2 章"
    assert "### 2.1 三级标题不应切分" in chapters[1]["text"], "I-2: ### 行并入第二章正文"
    assert any("投标函" in c["title"] for c in chapters), "H2 章边界可切"
    assert all(c["text"].strip() for c in chapters), "零空章"


def test_split_chapters_strips_closing_hashes(tmp_path):
    """M-4：ATX 闭合 # 序列从章标题剥离。"""
    p = tmp_path / "atx.md"
    p.write_text("## 四、售后服务 ##\n\n正文。\n", encoding="utf-8")
    chapters = bc.split_chapters(p.read_text(encoding="utf-8"))
    assert [c["title"] for c in chapters] == ["四、售后服务"]


def test_paragraph_lengths(tender_md):
    text = bc.load_text(tender_md)
    lens = bc.paragraph_lengths(text)
    # I-1 精确值锁死（M-1 口径: 剔 # 标题行与 | 表格行, fixture 正文恰 4 段）
    assert len(lens) == 4 and max(lens) == 89 and min(lens) == 16
    assert lens == [89, 29, 16, 29]


def test_main_warns_on_zero_chapters(tmp_path, capsys):
    """M-6：零章切片 → stderr 警告（自定义样式 docx 全量丢弃的极端形态），rc 仍 0。"""
    p = tmp_path / "nohead.md"
    p.write_text("没有任何标题的正文一段。\n", encoding="utf-8")
    rc = bc.main(["--input", str(p), "--title", "测试项目", "--industry", "信息技术", "--category", "IT软件平台", "--bank-dir", str(tmp_path / "bank")])
    assert rc == 0
    assert "0 章" in capsys.readouterr().err


# --- M-5：_docx_to_markdown 合成 docx 测试（zipfile+writestr 手法） ----------------

_DOCX_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx(tmp_path, body: str, name="t.docx"):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr(
            "word/document.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{_DOCX_W_NS}"><w:body>{body}</w:body></w:document>',
        )
    return p


def _docx_para(style: str | None, text: str) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"


def test_docx_headings_paragraphs(tmp_path):
    """HeadingN 与纯数字样式 → # 层级；普通段落照抄无前缀；H1 封面不立章。"""
    body = _docx_para("Heading1", "投标文件格式") + _docx_para("2", "数字样式二级标题") + _docx_para(None, "正文段落照抄。")
    out = bc._docx_to_markdown(_make_docx(tmp_path, body))
    assert out.split("\n\n") == ["# 投标文件格式", "## 数字样式二级标题", "正文段落照抄。"]
    chapters = bc.split_chapters(out)
    assert [c["title"] for c in chapters] == ["数字样式二级标题"]


def test_docx_table_escape_pad_contiguity(tmp_path):
    """M-2：单元格 | 转义防碎表、内嵌换行折叠空格、短行补齐表头列数、整表行连续。"""
    body = (
        _docx_para("Heading2", "三、开标一览表") + "<w:tbl><w:tr><w:tc>" + _docx_para(None, "含|竖线") + "</w:tc><w:tc>" + _docx_para(None, "名称") + "</w:tc></w:tr><w:tr><w:tc>" + _docx_para(None, "多\n行文本") + "</w:tc></w:tr></w:tbl>"
    )
    lines = bc._docx_to_markdown(_make_docx(tmp_path, body)).split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.startswith("|")]
    assert idx == list(range(idx[0], idx[0] + 3)), "表格行连续不碎"
    assert lines[idx[0]] == "| 含\\|竖线 | 名称 |", "单元格 | 已转义"
    assert lines[idx[1]] == "|---|---|"
    assert lines[idx[2]] == "| 多 行文本 |  |", "短行补齐到表头列数, 内嵌换行折叠空格"


def test_docx_no_body_returns_empty(tmp_path):
    """M-3：document.xml 无 w:body → 空串（is None 显式判定，不 DeprecationWarning 不炸）。"""
    p = tmp_path / "empty.docx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", f'<w:document xmlns:w="{_DOCX_W_NS}"></w:document>')
    assert bc._docx_to_markdown(p) == ""


# --- 脱敏引擎（--map 显式对照 + 自动模式 + 残留扫描） -------------------------------------------


def test_redact_auto_patterns(tender_md):
    text = bc.load_text(tender_md)
    redacted = bc.redact(text, mapping={})
    assert "1,280,000.00" not in redacted and "****" in redacted, "金额脱敏"
    assert "91360100MA001AB2CD" not in redacted, "信用代码脱敏"
    assert "13800138000" not in redacted, "手机号脱敏"
    assert "江西师范大学" in redacted, "无 --map 时机构名保留(不虚构替换)"


def test_redact_with_map(tender_md):
    text = bc.load_text(tender_md)
    redacted = bc.redact(text, mapping={"江西师范大学": "某大学【1】", "张三": "某人"})
    assert "江西师范大学" not in redacted and "某大学【1】" in redacted
    assert "张三" not in redacted and "某人" in redacted


def test_residual_scan_hits(tender_md):
    text = bc.load_text(tender_md)
    redacted = bc.redact(text, mapping={})
    hits = bc.residual_scan(redacted)
    assert hits == [], f"自动脱敏后零残留: {hits}"


def test_residual_scan_catches_miss(tender_md):
    assert bc.residual_scan("报价 9,999,999.99 元") != [], "漏网金额必须被扫描抓到"
