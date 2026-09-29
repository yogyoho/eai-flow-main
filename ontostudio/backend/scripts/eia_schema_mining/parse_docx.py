"""docx→txt 解析（stdlib zipfile+XML，先例参考 skills/.../ingest.py:16 只读）。
python-docx 不在 ontostudio venv——stdlib 是唯一依赖路线。
输出 out/fulltexts/{slug}-fulltext.txt（缓存：已存在则跳过）。

slug→文件名真源 = backend/app/extensions/eia_samples/data/kf_samples_seed.json
（2026-09-06 回填对账定稿），逐字照抄；个别文件名带哈希后缀的（santanghu）按该台账取哈希版。
"""
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SRC_DIR = Path(r"D:\18 辽宁创元\03 项目策划\01 中煤科工\knowledge\样例文件")
SLUG_FILES = {  # 22 份 docx（kf_samples_seed.json 对账定稿 slug→文件映射，huojitu/ningtiaota 为 .doc 排除）
    "baiyinhua2": "白音华二号露天矿项目环境影响后评价报告书-2026.3.docx",
    "baiyinhua3": "白音华煤田三号露天矿项目环境影响后评价报告书-2021.10.docx",
    "balasu": "巴拉素调整建设规模项目环境影响报告书（报批版）-2023.4.docx",
    "gaotaoyao": "鄂尔多斯市东胜煤田高头窑矿区总体规划修编环境影响报告书2023.5.docx",
    "guojiatai": "郭家台二号煤矿环评报告（报批稿）5.15.docx",
    "hegang": "黑龙江省鹤岗煤炭矿区总体规划（修编）环境影响报告书 .docx",
    "hengcheng": "横城矿区总体规划（修编）环评——报告书报批版2021.1.docx",
    "huating": "华亭矿区总体规划修编环境影响报告书-正式评审会后修改2024.11（加一句话在铁路建成前，采用清洁能源运输车运输）.docx",
    "jiulongchuan": "九龙川矿井及选煤厂800万吨项目环评-2026.2.docx",
    "lingtai": "3灵台矿区总体规划（修编）环境影响报告书 .docx",
    "nalinxili": "4纳林希里矿区总体规划环境影响报告书-审查会后修改(补充).docx",
    "naomaohu2025": "淖毛湖总规（修编）环评2025.11.docx",
    "santanghu": "三塘湖矿区规划环评修编（报批版）-0c6e43497902.docx",
    "sijitun": "3.1黑龙江省四季屯矿山地质环境保护与土地复垦方案报告书（报批版）.docx",
    "weizhou": "评审会后修改韦州矿区总体规划（修编）环评报告书 2022.12.7.docx",
    "wujianfang": "五间房矿区总体规划环评-报批-终稿.docx",
    "yakeshi2026": "文字——牙克石-五九煤田矿区总规环评2026.docx",
    "yimin": "5伊敏矿区规划环评（最终归档版）-出版，2套，蓝白皮.docx",
    "yimin3500": "伊敏3500万吨环评项目---最终2024.4.11.docx",
    "yining": "1新疆伊宁矿区北区总体规划（修编）环境影响报告书 报批版 2024.1.30.docx",
    "yitai": "压缩_5最终修改黑字版 伊泰煤矿（露天部分）及选煤厂900万吨环评2023.8.docx",
    "yueerwan": "(WPS)宁夏通达新能源集团有限公司月儿湾矿井及选煤厂环评报告书-排版.docx",
}


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(f"{W_NS}p"):
        text = "".join(t.text or "" for t in p.iter(f"{W_NS}t"))
        if text.strip():
            paras.append(text.strip())
    return "\n".join(paras)


def main() -> None:
    out_dir = Path("out/fulltexts")
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = miss = fail = 0
    for slug, fname in SLUG_FILES.items():
        dst = out_dir / f"{slug}-fulltext.txt"
        if dst.exists():
            print(f"skip {slug} (cached)")
            continue
        src = SRC_DIR / fname
        if not src.exists():
            print(f"MISS {slug}: {fname} 不存在")
            miss += 1
            continue
        try:
            dst.write_text(docx_text(src), encoding="utf-8")
        except Exception as exc:  # 单文件损坏不中断整批（如加密容器）
            print(f"PARSE-FAIL {slug}: {fname} ({exc})")
            fail += 1
            continue
        print(f"ok {slug}: {dst.stat().st_size // 1024}KB")
        ok += 1
    print(f"done: ok={ok} miss={miss} fail={fail} total={len(SLUG_FILES)}")


if __name__ == "__main__":
    main()
