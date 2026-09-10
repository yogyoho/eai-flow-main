"""bank_compile 样例入库工具：脱敏/切片/深度统计/产物确定性（纯函数契约）。"""

import importlib.util
import json
import re
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
    p.write_text(md, encoding="utf-8", newline="\n")  # LF 落盘——M-5 契约测 writer 不翻译换行, 输入先不带 CRLF
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
    # M-2 fail-closed: 表格两位小数金额(3,500.00 无元后缀)AMOUNT_RE 不掩码, 由残留门兜底——
    # 唯一残留恰为该行, 其余(金额/信用代码/手机/身份证)必须零残留。
    assert hits == ["| 1 | 课堂观测终端 | 200 | 3,500.00 |"], f"残留应恰为表格金额行: {hits}"


def test_residual_scan_catches_miss(tender_md):
    assert bc.residual_scan("报价 9,999,999.99 元") != [], "漏网金额必须被扫描抓到"


def test_redact_cjk_adjacency_boundary():
    """bug-3061 回归钉: 无空格紧邻汉字的边界形态(空格形态下 \b 回退也能过, 探不到雷)。"""
    r = bc.redact("电话13800138000代码91360100MA001AB2CD号360102199001011234", mapping={})
    assert "13800138000" not in r and "91360100MA001AB2CD" not in r and "360102199001011234" not in r
    # M-4: 规则级显式断言——身份证(含 X 尾)不依赖端到端推断
    assert bc.ID_CARD_RE.search("号360102199001011234"), "身份证规则 CJK 紧邻命中"
    assert bc.ID_CARD_RE.search("号36010219900101123X"), "身份证 X 尾命中"
    assert bc.PHONE_RE.search("电话13800138000"), "手机号规则 CJK 紧邻命中"
    assert bc.CREDIT_CODE_RE.search("代码91360100MA001AB2CD"), "信用代码规则 CJK 紧邻命中"


def test_redact_edge_probes():
    """I-1 顺手钉: 19 位纯数字串不截段误配 + 空 mapping 键跳过("".replace 语义陷阱)。"""
    assert bc.PHONE_RE.search("1234567890123456789") is None and bc.ID_CARD_RE.search("1234567890123456789") is None
    assert bc.redact("abc", {"": "X"}) == "abc"


def test_redact_title_map_only_auto_skip():
    """I-2(修法a): 标题行只吃 --map 逐字替换、跳过四条自动正则(# 结构保真);
    标题里的裸金额不再静默, 由残留门 fail-closed 兜底; 正文行自动模式照常。"""
    text = "## 五、报价 500 万元一览\n\n正文合计 500 万元。\n"
    out = bc.redact(text, mapping={})
    assert out.split("\n")[0] == "## 五、报价 500 万元一览", "标题行自动正则零改动"
    assert "正文合计****。" in out, "正文行自动脱敏照常(掩码吞掉匹配内空格)"
    assert bc.residual_scan(out) != [], "标题残留金额进残留门(不静默泄漏)"
    out2 = bc.redact("## 一、投标函\n", mapping={"投标函": "某函"})
    assert out2 == "## 一、某函\n", "标题行 --map 逐字替换(机构名清洗唯一通道)"


# --- Task 3: 深度统计 + 四产物确定性落盘 ---------------------------------------------------------


def test_slugify_deterministic_ascii():
    """sha1(title)[:12] 小写 hex——ASCII 文件系统安全、同题恒同 slug(可读名进 bank_index)。"""
    s1 = bc.slugify("江西师范大学课堂观测系统")
    assert s1 == bc.slugify("江西师范大学课堂观测系统")
    assert re.fullmatch(r"[0-9a-f]{12}", s1)
    assert bc.slugify("另一项目") != s1


def test_percentile_index_semantics():
    """索引取整取值: idx=len*pct//100 截断钳位到 [0, n-1]; 空表返 0。"""
    assert bc.percentile([10, 20, 30, 40], 25) == 20
    assert bc.percentile([10, 20, 30, 40], 50) == 30
    assert bc.percentile([10, 20, 30, 40], 0) == 10
    assert bc.percentile([10, 20, 30, 40], 100) == 40
    assert bc.percentile([7], 25) == 7
    assert bc.percentile([], 50) == 0


def test_compile_bank_redact_before_slice_and_residual_evidence():
    """T2 评审接线: compile_bank 先 redact 全文再切章——章 title 字段来自 redacted 文本,
    标题里的机构名不绕过 --map; residual 证据随返回值传出(Task 4 闸门消费)。"""
    res = bc.compile_bank("## 一、江西师范大学投标函\n\n正文 500 元。\n", title="T", industry="信息技术", category="IT软件平台", mapping={"江西师范大学": "某大学"})
    assert res["chapters"][0]["title"] == "一、某大学投标函", "章 title 必须来自 redacted 文本"
    assert "江西师范大学" not in res["redacted"]
    res2 = bc.compile_bank("## 一、报价 500 万元一览\n\n正文合计 500 万元。\n", title="T", industry="信息技术", category="IT软件平台", mapping={})
    assert res2["residual"] == ["## 一、报价 500 万元一览"], "标题残留进 residual 证据(不静默泄漏)"


def test_compile_bank_depth_targets_m1_exclusion():
    """深度统计手算钉: M-1 剔 #/| 结构行后取分布, P25/median 为索引取整取值。"""
    text = "## 一、甲\n\n" + "字" * 30 + "\n\n短段\n\n| 表 | 头 |\n| --- | --- |\n\n## 二、乙\n\n" + "言" * 20 + "\n"
    res = bc.compile_bank(text, title="T", industry="信息技术", category="IT软件平台", mapping={})
    # 正文段恰 [30, 2, 20](表行剔除) → sorted [2, 20, 30]; P25: 3*25//100=0→2; median: 3*50//100=1→20
    dt = res["depth_targets"]
    assert dt["absolute_floor"] == 2 and dt["global_median"] == 20
    assert dt["paragraph_count"] == 3 and dt["calibrated_from"] == res["file_hash"]
    assert len(res["file_hash"]) == 64, "bid_samples 台账 file_hash 恰 64 字符契约"
    assert res["registration_item"]["scenario"] == "bid_sample"
    assert res["registration_item"]["source_path"] == f"{res['slug']}/full.md"


def test_compile_outputs_full_pipeline(tender_md, tmp_path, capsys):
    bank_dir = tmp_path / "samples_bank"
    # 表格两位小数金额(3,500.00)=fixture 已知唯一 fail-closed 残留, --map 显式清洗后闸门才放行
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"3,500.00": "****"}), encoding="utf-8")
    argv = [
        "--input",
        str(tender_md),
        "--title",
        "江西师范大学课堂观测系统",
        "--industry",
        "信息技术",
        "--category",
        "IT软件平台",
        "--bank-dir",
        str(bank_dir),
        "--map",
        str(map_path),
    ]
    assert bc.main(argv) == 0
    slug = bc.slugify("江西师范大学课堂观测系统")
    slug_dir = bank_dir / slug
    full = slug_dir / "full.md"
    full_bytes = full.read_bytes()
    assert full.is_file() and "投标函" in full_bytes.decode("utf-8")
    assert b"\r\n" not in full_bytes, "M-5: LF 落盘契约(跨机字节一致, 不吃 os.linesep 翻译)"
    chapter_files = sorted((slug_dir / "chapters").glob("ch*.md"))
    assert len(chapter_files) == 3, "3 章切片逐章落盘"
    index = json.loads((bank_dir / "bank_index.json").read_text(encoding="utf-8"))
    assert slug in index and index[slug]["title"] == "江西师范大学课堂观测系统"
    assert index[slug]["chapters"] and all((slug_dir / c["file"]).is_file() for c in index[slug]["chapters"]), "index 章条目可导航"
    targets = json.loads((bank_dir / "depth_targets.json").read_text(encoding="utf-8"))
    # M-5 精确值钉: fixture 脱敏后段长 sorted [15, 16, 20, 57](掩码缩短原文) → P25=idx1=16, median=idx2=20
    assert targets["absolute_floor"] == 16 and targets["global_median"] == 20
    reg = json.loads((bank_dir / "registration.json").read_text(encoding="utf-8"))
    assert reg["items"] and reg["items"][0]["scenario"] == "bid_sample"
    # 残留闸门(Task 4): --map 清洗后零残留 → 闸门放行, 全程无残留告警(命中即 rc=1 零落盘, 见闸门用例)
    captured = capsys.readouterr()
    assert "残留" not in captured.err
    # 确定性: 重跑字节一致(同 slug 不重复登记)
    before = {p.relative_to(bank_dir).as_posix(): p.read_bytes() for p in bank_dir.rglob("*") if p.is_file()}
    assert bc.main(argv) == 0
    after = {p.relative_to(bank_dir).as_posix(): p.read_bytes() for p in bank_dir.rglob("*") if p.is_file()}
    assert before == after, "重跑字节级幂等"
    assert len(json.loads((bank_dir / "registration.json").read_text(encoding="utf-8"))["items"]) == 1, "同 slug 重跑不重复登记"


def test_main_applies_map_flag(tender_md, tmp_path):
    """--map JSON 对照经 main 接入 compile_bank(全文先脱敏后切片, 机构名含标题全清)。"""
    bank_dir = tmp_path / "bank"
    map_path = tmp_path / "map.json"
    # 3,500.00=fixture 表格行已知 fail-closed 残留, 须一并 --map 清洗否则 Task 4 残留闸门 rc=1 零落盘
    map_path.write_text(json.dumps({"江西师范大学": "某大学【1】", "3,500.00": "****"}), encoding="utf-8")
    assert bc.main(["--input", str(tender_md), "--title", "T项目", "--bank-dir", str(bank_dir), "--map", str(map_path)]) == 0
    full = (bank_dir / bc.slugify("T项目") / "full.md").read_text(encoding="utf-8")
    assert "江西师范大学" not in full and "某大学【1】" in full


def test_depth_targets_bank_level_aggregate(tmp_path):
    """I-1: depth_targets.json 对 bank_index 全册聚合——floor=各册 min、median=各册中位,
    名实相符且与编译顺序无关(先 A 后 B 与先 B 后 A 同值, 根除 last-writer-wins)。"""
    a = tmp_path / "a.md"
    a.write_text("## 一、甲\n\n" + "字" * 30 + "\n\n短段\n\n" + "言" * 20 + "\n", encoding="utf-8")  # 段[30,2,20]: floor 2/median 20
    b = tmp_path / "b.md"
    b.write_text("## 一、乙\n\n" + "深" * 100 + "\n", encoding="utf-8")  # 段[100]: floor 100/median 100

    def argv(src, title, bank):
        return ["--input", str(src), "--title", title, "--bank-dir", str(bank)]

    bank1, bank2 = tmp_path / "bank1", tmp_path / "bank2"
    assert bc.main(argv(a, "A项目", bank1)) == 0 and bc.main(argv(b, "B项目", bank1)) == 0
    assert bc.main(argv(b, "B项目", bank2)) == 0 and bc.main(argv(a, "A项目", bank2)) == 0
    t1 = json.loads((bank1 / "depth_targets.json").read_text(encoding="utf-8"))
    t2 = json.loads((bank2 / "depth_targets.json").read_text(encoding="utf-8"))
    assert t1["absolute_floor"] == 2, "全库 floor=各册 min(后编的高 floor 样本不覆盖)"
    assert t1["global_median"] == 60, "全库 median=各册中位 statistics.median([20,100])"
    assert (t2["absolute_floor"], t2["global_median"]) == (t1["absolute_floor"], t1["global_median"]), "聚合与编译顺序无关"


def test_main_warns_on_content_drift(tmp_path, capsys):
    """M-2: 同题(同 slug)重编但内容已变 → file_hash 漂移一行 stderr 警告。"""
    p = tmp_path / "t.md"
    p.write_text("## 一、甲\n\n正文A。\n", encoding="utf-8")
    bank = tmp_path / "bank"
    assert bc.main(["--input", str(p), "--title", "同题项目", "--bank-dir", str(bank)]) == 0
    capsys.readouterr()
    p.write_text("## 一、甲\n\n正文B改版。\n", encoding="utf-8")
    assert bc.main(["--input", str(p), "--title", "同题项目", "--bank-dir", str(bank)]) == 0
    assert "漂移" in capsys.readouterr().err, "内容漂移必须可见"


def test_main_resets_corrupt_json_products(tmp_path, capsys):
    """M-3: 既有 JSON 产物损坏/形态异常 → stderr 提示后重置重建(rc 仍 0, 不裸 traceback)。"""
    p = tmp_path / "t.md"
    p.write_text("## 一、甲\n\n正文。\n", encoding="utf-8")
    bank = tmp_path / "bank"
    bank.mkdir(parents=True)
    (bank / "bank_index.json").write_text("{corrupt", encoding="utf-8")
    (bank / "registration.json").write_text(json.dumps({"items": "not-a-list"}), encoding="utf-8")
    assert bc.main(["--input", str(p), "--title", "T", "--bank-dir", str(bank)]) == 0
    err = capsys.readouterr().err
    assert "bank_index.json" in err and "registration.json" in err, "两产物损坏均须提示并重置"
    reg = json.loads((bank / "registration.json").read_text(encoding="utf-8"))
    assert isinstance(reg["items"], list) and len(reg["items"]) == 1, "重置后正常重建"


def test_registration_legacy_row_without_slug_kept(tmp_path):
    """M-4: 旧行缺 slug 键 → 排序空串排首不崩, 行保留不丢。"""
    p = tmp_path / "t.md"
    p.write_text("## 一、甲\n\n正文。\n", encoding="utf-8")
    bank = tmp_path / "bank"
    bank.mkdir(parents=True)
    (bank / "registration.json").write_text(json.dumps({"items": [{"title": "旧行无slug"}]}), encoding="utf-8")
    assert bc.main(["--input", str(p), "--title", "T", "--bank-dir", str(bank)]) == 0
    items = json.loads((bank / "registration.json").read_text(encoding="utf-8"))["items"]
    assert len(items) == 2, "旧行不丢"
    assert items[0].get("title") == "旧行无slug", "缺 slug 旧行空串排首"
    assert items[1]["scenario"] == "bid_sample"


def test_main_map_bad_json_actionable(tmp_path):
    """M-7: --map 坏 JSON → 可操作 ValueError(对齐 load_text 报错风格), 不裸 traceback。"""
    p = tmp_path / "t.md"
    p.write_text("## 一、甲\n\n正文。\n", encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(ValueError, match="map 文件 JSON 解析失败"):
        bc.main(["--input", str(p), "--title", "T", "--bank-dir", str(tmp_path / "bank"), "--map", str(bad)])


# --- Task 4: 残留闸门(命中 → rc=1 零落盘) --------------------------------------------------------


def test_residual_hits_block_output(tmp_path, capsys):
    """残留扫描命中 → rc=1 且零落盘(不静默出库), 证据行全量上 stderr。

    fixture 注意(Do-Not-Repeat 2026-09-10: plan 测试串先干跑再照抄): 「1,280,000.00 元」会被
    AMOUNT_RE 正常掩码、不触发残留; 真正漏网的是表格两位小数千分位形态(3,500.00 无元后缀,
    M-2/bug-3236 fail-closed 分支)——闸门要拦的正是它。
    """
    dirty = tmp_path / "dirty.md"
    dirty.write_text("# 投标函\n\n报价 1,280,000.00 元整，另有单价 3,500.00 漏网。\n", encoding="utf-8")
    bank = tmp_path / "bank"
    rc = bc.main(["--input", str(dirty), "--title", "测试项目", "--industry", "信息技术", "--category", "IT软件平台", "--bank-dir", str(bank)])
    assert rc == 1
    assert not (bank / "bank_index.json").exists(), "残留命中=零落盘"
    assert not bank.exists(), "闸门先于一切落盘——bank 目录都不建(depth_targets/registration/切片同理全不写)"
    err = capsys.readouterr().err
    assert "残留" in err and "3,500.00" in err, "证据行必须全量呈现(stderr), 供维护者补 --map 或人工处置"


# --- Task 5: 可选 RAGFlow bid_samples 域推送(失败=warnings) + argparse 用法错误改道(T4 评审 Minor-1) --


@pytest.fixture
def clean_map(tmp_path):
    """fixture 表格两位小数金额(3,500.00)=已知 fail-closed 残留——推送用例须先 --map 清洗,
    否则残留闸门先行 rc=1 零落盘, 永远走不到闸门之后的推送段(Do-Not-Repeat 2026-09-10:
    plan 测试串先干跑再照抄——本组用例已按闸门事实补 --map)。"""
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({"3,500.00": "****"}), encoding="utf-8")
    return str(map_path)


def _push_argv(tender_md, bank, clean_map):
    return [
        "--input",
        str(tender_md),
        "--title",
        "测试项目",
        "--industry",
        "信息技术",
        "--category",
        "IT软件平台",
        "--bank-dir",
        str(bank),
        "--map",
        clean_map,
        "--ragflow-push",
    ]


def test_ragflow_push_called_when_enabled(monkeypatch, tmp_path, tender_md, clean_map):
    calls: list[tuple] = []
    monkeypatch.setenv("BID_RAGFLOW_DATASET_ID", "ds-123")
    monkeypatch.setattr(bc, "ragflow_push", lambda md, meta: calls.append((md[:50], meta)) or True)
    rc = bc.main(_push_argv(tender_md, tmp_path / "bank", clean_map))
    assert rc == 0
    assert len(calls) == 1 and "投标文件格式" in calls[0][0], "推送的是 redacted 全文"
    assert calls[0][1]["title"] == "测试项目" and calls[0][1]["dataset_id"] == "ds-123"
    assert calls[0][1]["industry"] == "信息技术" and calls[0][1]["category"] == "IT软件平台"


def test_ragflow_push_skipped_without_env(monkeypatch, tmp_path, tender_md, clean_map, capsys):
    """无 dataset id=跳过推送不报错(rc 仍 0), 但留一行 stderr 提示让维护者知晓未推送。"""
    monkeypatch.delenv("BID_RAGFLOW_DATASET_ID", raising=False)
    calls: list[tuple] = []
    monkeypatch.setattr(bc, "ragflow_push", lambda md, meta: calls.append((md, meta)) or True)
    rc = bc.main(_push_argv(tender_md, tmp_path / "bank", clean_map))
    assert rc == 0 and calls == [], "无 dataset id=跳过推送不报错"
    assert "BID_RAGFLOW_DATASET_ID" in capsys.readouterr().err


def test_ragflow_push_failure_does_not_block(monkeypatch, tmp_path, tender_md, clean_map, capsys):
    """推送链路任何异常吞掉记 warning 返回 False——rc 仍 0, 本地衍生物已先行落盘(spec: 失败=warnings)。"""
    monkeypatch.setenv("BID_RAGFLOW_DATASET_ID", "ds-123")
    monkeypatch.setenv("BID_RAGFLOW_API_KEY", "k-test")

    def _boom(*a, **kw):
        raise RuntimeError("ragflow unreachable")

    monkeypatch.setattr(bc, "_ragflow_post", _boom)
    rc = bc.main(_push_argv(tender_md, tmp_path / "bank", clean_map))
    assert rc == 0
    assert "RAGFlow 推送失败" in capsys.readouterr().err, "推送失败必须可见(warnings 通道)"
    assert (tmp_path / "bank" / bc.slugify("测试项目") / "full.md").is_file(), "本地衍生物先行落盘, 推送失败不回滚"


def test_argparse_usage_error_returns_1_not_2(capsys):
    """T4 评审 Minor-1: argparse 用法错误改道 rc=1——默认退出码 2 与 docstring「1 用法错误」
    不符, 且 2 已保留给 ingest 的 OCR 分流(对齐 score_simulate/state_guard 家族惯例)。"""
    for argv in ([], ["--input", "x.md"], ["--unknown-flag"]):
        rc = bc.main(argv)
        assert rc == 1, f"用法错误 {argv!r} 应返回 1, 实际 {rc}"
    capsys.readouterr()


def test_help_returns_0(capsys):
    """--help 属 argparse 正常终止(code 0), 改道逻辑必须原样放行不按错误处理。"""
    assert bc.main(["--help"]) == 0
    capsys.readouterr()
