# fire-protection-extract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `fire-protection-extract` skill that generates a 消防设计专篇 by **verbatim extraction from an uploaded 设计说明书** (mapped by a reusable contract), with a grounding verifier that proves every copied block traces back to the source — replacing v2's generative approach.

**Architecture:** Anchor-based extraction. A parser turns the docx 说明书 into `{paras[], tables{}}` (ordered, flat). A YAML **mapping contract** lists, per fire-report section, atomic sources — either a `para` (located by a unique substring **anchor**), a `para_run` (span between two anchors), or a `table` (by 表号). The extractor copies each source **verbatim** into the report with a citation. A grounding checker confirms every output block is a substring of the source corpus, that all anchors resolve, and that conflict fields (e.g. 消防水量) use the authoritative source. Engine scripts and the fire-specific contract live in separate files so 给排水/抗震 later = add a yaml, engine untouched.

**Tech Stack:** Python 3.12, python-docx (already in sandbox), PyYAML, pytest. Skill source under `skills/custom/fire-protection-extract/`; runs in agent sandbox at `/mnt/skills/custom/fire-protection-extract/`.

**Spec:** `docs/superpowers/specs/2026-07-03-fire-protection-extract-design.md`

---

## File Structure

```
skills/custom/fire-protection-extract/
  SKILL.md                                # skill entry (workflow + tool rules)
  requirements.txt                        # python-docx, pyyaml, pytest
  scripts/
    parse_spec.py                         # ENGINE: docx -> {paras, tables} JSON
    extract.py                            # ENGINE: structure.json + mapping.yaml -> report.md + citations
    grounding_check.py                    # ENGINE: report.md vs structure.json -> pass rate + missing anchors
  references/
    fire_spec_mapping.yaml                # CONTRACT: 8章 x 子节 -> 源锚 (the one per-report artifact)
    extractor_rules.md                    # doc: anchor/grounding/conflict rules
  tests/
    conftest.py                           # pytest fixture: tiny synthetic docx
    _fixtures.py                          # build_tiny_spec(path)
    test_parse_spec.py
    test_mapping.py
    test_extract.py
    test_grounding.py
    test_integration.py                   # real-sample end-to-end (skips if sample absent)
```

**Responsibilities:** `parse_spec.py` = docx→structure (no domain logic). `extract.py` = contract-driven verbatim assembly (no parsing). `grounding_check.py` = safety net (no extraction). `fire_spec_mapping.yaml` = the ONLY fire-specific artifact. Three engine scripts are report-agnostic (the generalization hook from spec §10.5).

---

## Task 1: Scaffold + test fixture

**Files:**
- Create: `skills/custom/fire-protection-extract/requirements.txt`
- Create: `skills/custom/fire-protection-extract/tests/_fixtures.py`
- Create: `skills/custom/fire-protection-extract/tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```
python-docx>=0.8.11
PyYAML>=6.0
pytest>=7.0
```

- [ ] **Step 2: Create the fixture builder** `tests/_fixtures.py`

```python
"""Synthetic docx fixture for unit tests (avoids depending on the real sample)."""
from pathlib import Path
from docx import Document


def build_tiny_spec(path):
    """A minimal 设计说明书: TOC + 2 numbered sections + 1 table with a 表号 caption.

    Section 2.1 has a conflicting datum scenario mirroring §9.1 vs §9.2:
    a 给水 paragraph says 生活水 8L/s/DN150, a 消防 paragraph says 30L/s/DN200.
    """
    doc = Document()
    doc.add_paragraph("目  录")
    for line in ["1 概述\t1", "1.1 概况\t1", "2 给排水及消防\t2", "2.1 消防\t2"]:
        doc.add_paragraph(line)
    doc.add_paragraph("概述")
    doc.add_paragraph("1.1 概况")
    doc.add_paragraph("本项目为基地综合大队，占地面积23.8亩，特勤消防站。")
    doc.add_paragraph("2 给排水及消防")
    doc.add_paragraph("2.1 消防")
    # 给水 paragraph (the WRONG source for fire water — must not be picked)
    doc.add_paragraph("生活水系统设计生活用水量8L/s，管径DN150，自东侧市政管网引入。")
    # 消防 paragraph (the AUTHORITATIVE source for fire water)
    doc.add_paragraph("表2.1-1 消防水量")
    t = doc.add_table(rows=2, cols=2)
    t.rows[0].cells[0].text = "项目"
    t.rows[0].cells[1].text = "水量"
    t.rows[1].cells[0].text = "室外消火栓"
    t.rows[1].cells[1].text = "30L/s"
    doc.add_paragraph("本项目设计室外消火栓水量30L/s（108m³/h），引入两根管径DN200的管线。")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return str(path)
```

- [ ] **Step 3: Create conftest.py**

```python
import pytest
from ._fixtures import build_tiny_spec


@pytest.fixture
def tiny_spec(tmp_path):
    return build_tiny_spec(tmp_path / "tiny.docx")
```

- [ ] **Step 4: Verify the fixture builds**

Run: `cd skills/custom/fire-protection-extract && python -c "from tests._fixtures import build_tiny_spec; from pathlib import Path; build_tiny_spec(Path('/tmp/tiny.docx')); print('OK')"`
Expected: prints `OK` (install deps first: `pip install -r requirements.txt`)

- [ ] **Step 5: Commit**

```bash
git add skills/custom/fire-protection-extract/requirements.txt skills/custom/fire-protection-extract/tests/_fixtures.py skills/custom/fire-protection-extract/tests/conftest.py
git commit -m "feat(fire-extract): scaffold + synthetic docx test fixture"
```

---

## Task 2: parse_spec.py — docx → structure JSON

**Files:**
- Create: `skills/custom/fire-protection-extract/scripts/parse_spec.py`
- Create: `skills/custom/fire-protection-extract/tests/test_parse_spec.py`

- [ ] **Step 1: Write the failing test**

`tests/test_parse_spec.py`:
```python
import json
from pathlib import Path
from scripts.parse_spec import parse_spec


def test_parse_extracts_paras_and_table(tiny_spec):
    data = parse_spec(tiny_spec)
    texts = [p["text"] for p in data["paras"]]
    assert "本项目为基地综合大队，占地面积23.8亩，特勤消防站。" in texts
    # table caption captured as a paragraph too
    assert any("表2.1-1" in t for t in texts)
    # table indexed by 表号, rows preserved
    assert "表2.1-1" in data["tables"]
    rows = data["tables"]["表2.1-1"]["rows"]
    assert rows[0] == ["项目", "水量"]
    assert rows[1] == ["室外消火栓", "30L/s"]
    # paras carry stable indices
    assert data["paras"][0]["i"] == 0


def test_parse_writes_json(tmp_path, tiny_spec):
    from scripts.parse_spec import main
    out = tmp_path / "struct.json"
    rc = main([tiny_spec, str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["paras"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd skills/custom/fire-protection-extract && python -m pytest tests/test_parse_spec.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.parse_spec'`

- [ ] **Step 3: Write parse_spec.py**

`scripts/parse_spec.py`:
```python
#!/usr/bin/env python3
"""设计说明书 .docx → 带稳定 ID 的结构 JSON（{paras, tables}）。

按文档顺序遍历段落与表格（python-docx 的 doc.paragraphs/doc.tables 是两个独立列表，
丢失顺序；这里直接遍历 body XML 子元素拿到交错的段落+表格）。
表格按其前一个段落里的「表X.Y-Z」题注建索引；段落带稳定序号 i。
不依赖 Word 标题样式（样本里样式不一致），用锚/区间定位交给上层 extract.py。
"""
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

TABLE_NO_RE = re.compile(r"^(表\s*\d[\d.\-]*[A-Za-z]?)\s*(.*)$")


def iter_block_items(doc):
    """Yield Paragraph/Table in document order."""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _norm_no(raw):
    return re.sub(r"\s+", "", raw)


def parse_spec(docx_path):
    doc = Document(str(docx_path))
    paras, tables = [], {}
    pending_no, pending_title = None, None
    for blk in iter_block_items(doc):
        if isinstance(blk, Paragraph):
            text = blk.text.strip()
            if not text:
                continue
            paras.append({"i": len(paras), "text": text})
            m = TABLE_NO_RE.match(text)
            if m:
                pending_no = _norm_no(m.group(1))
                pending_title = m.group(2).strip()
        elif isinstance(blk, Table):
            rows = [[c.text.strip() for c in row.cells] for row in blk.rows]
            no = pending_no or f"__auto{len(tables)}"
            tables[no] = {"title": pending_title or "", "rows": rows, "n_rows": len(rows)}
            pending_no, pending_title = None, None
    return {"paras": paras, "tables": tables}


def main(argv):
    if len(argv) != 3:
        print("usage: parse_spec.py <input.docx> <output.json>", file=sys.stderr)
        return 2
    data = parse_spec(argv[1])
    Path(argv[2]).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK paras={len(data['paras'])} tables={len(data['tables'])} -> {argv[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd skills/custom/fire-protection-extract && python -m pytest tests/test_parse_spec.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/custom/fire-protection-extract/scripts/parse_spec.py skills/custom/fire-protection-extract/tests/test_parse_spec.py
git commit -m "feat(fire-extract): parse_spec docx->structure json"
```

---

## Task 3: Mapping contract YAML + schema/anchor test

**Files:**
- Create: `skills/custom/fire-protection-extract/references/fire_spec_mapping.yaml`
- Create: `skills/custom/fire-protection-extract/tests/test_mapping.py`

- [ ] **Step 1: Write the contract** (anchors transcribed from the verified sample pair)

`references/fire_spec_mapping.yaml`:
```yaml
# 消防设计专篇 ← 设计说明书 映射契约（基地项目样本对建，cerebrum 2026-07-03 投影洞察）
# 每个 fire 小节 = 一组原子摘抄。kind:
#   para      -> 单段，anchor=该段唯一子串，逐字复制整段
#   para_run  -> 区间，from/to=首尾段锚，复制闭区间内全部段
#   table     -> 表，no=表号（如 表3.1-1），整表复制
# class: verbatim(抄) / template(填) / compute(算)。
# authoritative=true 标记冲突字段的权威源（如消防水量取消防章非给水章）。
report_title: "{项目名} 消防设计专篇"
sections:
  - fire: "1.1 设计依据"
    class: verbatim
    sources:
      - {kind: para, anchor: "《基地综合大队建设项目可行性研究报告》及批复"}
  - fire: "1.2 设计采用的技术标准、规范"
    class: template
    template: gb_standards
  - fire: "1.3 及地方相关法规"
    class: template
    template: fire_law
  - fire: "2.1 项目位置"
    class: verbatim
    sources:
      - {kind: para, anchor: "建设基地综合大队，占地面积23.8"}
  - fire: "2.2 项目建设功能定位"
    class: verbatim
    sources:
      - {kind: para, anchor: "建成能够承担省及邻近周边省"}
  - fire: "2.3 建设规模"
    class: verbatim
    sources:
      - {kind: para, anchor: "新组建的综合大队建设规模为特勤消防站"}
  - fire: "2.4 建设内容"
    class: verbatim
    sources:
      - {kind: para, anchor: "消防综合业务用房：包括消防车库"}
  - fire: "2.5 建设性质"
    class: verbatim
    sources:
      - {kind: para, anchor: "本项目建设性质为新建"}
  - fire: "2.6 工程所在地气象条件"
    class: verbatim
    sources:
      - {kind: table, no: "表3.1-1"}
  - fire: "2.7 周围消防站情况"
    class: verbatim
    sources:
      - {kind: para, anchor: "距离北侧现有石化炼油消防队27.18m"}
  - fire: "3 火灾危险性分析"
    class: verbatim
    sources:
      - {kind: para, anchor: "本项目建设内容为消防站"}
      - {kind: table, no: "表2.3-1"}
      - {kind: para, anchor: "火灾危险级为轻危险级"}
  - fire: "4.1 总平面布置、防火间距及消防通道"
    class: verbatim
    sources:
      - {kind: para_run, from: "新建执勤楼布置在整个场地中部偏东侧", to: "能够满足车辆回转及消防的要求"}
  - fire: "4.2 防雷、接地的设计原则"
    class: verbatim
    sources:
      - {kind: para_run, from: "按照《建筑物防雷设计规范》（GB50057-2010）的规定，本项目执勤楼为第三类防雷", to: "其他接地材料采用纳米炭复合接地材料"}
  - fire: "4.3 供电安全"
    class: verbatim
    sources:
      - {kind: para_run, from: "基地综合大队建设项目的变配电、照明、防雷、接地、界区内供电外线和道路照明", to: "高杆灯采用铠装电缆埋地敷设"}
  - fire: "4.4 建、构筑物防火"
    class: verbatim
    sources:
      - {kind: para_run, from: "执勤楼：本工程为新建，钢筋混凝土结构，尺寸为142.1", to: "配电室采用乙级钢制防火门，窗采用铝合金窗"}
      - {kind: table, no: "表7.1-1"}
  - fire: "4.5 建筑物通风措施"
    class: verbatim
    sources:
      - {kind: para, anchor: "执勤楼变电所设机械排风系统排除室内的余热"}
      - {kind: table, no: "表8.2-1"}
  - fire: "5.1 室外消防水系统"
    class: verbatim
    sources:
      # ⚠ 锚必须落在 §9.2 消防段独有的续文上。「室外消火栓水量30L/s」在 §9.1 给水和 §9.2 消防
      # 两段都出现（§9.1=DN150、§9.2=DN200），用前者做锚会先命中 §9.1 抄错。用「生活用水量10L/s」
      # （§9.2 独有，§9.1 是 8L/s）定位到 §9.2 段，复制整段（含 30L/s、DN200）。
      - {kind: para, anchor: "生活用水量10L/s（36m³/h）", authoritative: true, conflict_note: "锚定§9.2消防段；不取给水章§9.1的8L/s/DN150"}
  - fire: "5.2 室内水消防系统"
    class: verbatim
    sources:
      - {kind: para, anchor: "新建消防水池1座，钢筋混凝土结构，总有效容积117m³"}
      - {kind: para, anchor: "建筑物内设置室内消火栓灭火系统，采用临时高压消防给水系统"}
  - fire: "5.3 移动式灭火器"
    class: verbatim
    sources:
      - {kind: para, anchor: "根据装置各危险场所的生产类别、危险等级，设置相应的移动式干粉灭火器"}
  - fire: "5.4 火灾报警系统"
    class: verbatim
    sources:
      - {kind: para_run, from: "火灾自动报警系统由集中火灾报警控制器", to: "接地电阻不大于1欧姆"}
      - {kind: table, no: "表6.5-1"}
  - fire: "5.5 视频监控系统"
    class: verbatim
    sources:
      - {kind: para_run, from: "为能及时发现消防站内的危险情况", to: "利用指挥中心内现有大屏幕查看"}
  - fire: "6 灭火救援设施"
    class: verbatim
    sources:
      - {kind: para, anchor: "该建设场地的西侧是乡道，南侧为纬一路"}
  - fire: "7 消防设施专项投资概算"
    class: compute
    note: "说明书无此数据，标[需计算]，由人工/概算技能补，不伪造"
  - fire: "8 图纸及表格"
    class: verbatim
    sources:
      - {kind: para_run, from: "区域位置图", to: "设备一览表"}
templates:
  gb_standards: |
    石油化工企业设计防火标准（2018版） GB50160-2008
    建筑设计防火规范（2018版） GB50016-2014
    爆炸危险环境电力装置设计规范 GB50058-2014
    火灾自动报警系统设计规范 GB50116-2013
    建筑灭火器配置设计规范 GB50140-2005
    消防给水及消火栓系统技术规范 GB50974-2014
  fire_law: "中华人民共和国消防法（2019.4.23）"
```

- [ ] **Step 2: Write the failing test**

`tests/test_mapping.py`:
```python
import yaml
from pathlib import Path

MAPPING = Path(__file__).resolve().parents[1] / "references" / "fire_spec_mapping.yaml"


def load_mapping():
    return yaml.safe_load(MAPPING.read_text(encoding="utf-8"))


def test_mapping_schema():
    m = load_mapping()
    assert "sections" in m and len(m["sections"]) >= 20
    valid_classes = {"verbatim", "template", "compute"}
    valid_kinds = {"para", "para_run", "table"}
    for sec in m["sections"]:
        assert "fire" in sec and "class" in sec
        assert sec["class"] in valid_classes
        for src in sec.get("sources", []) or []:
            assert src["kind"] in valid_kinds
            if src["kind"] == "para":
                assert src.get("anchor")
            elif src["kind"] == "para_run":
                assert src.get("from") and src.get("to")
            elif src["kind"] == "table":
                assert src.get("no")


def test_conflict_field_has_authoritative_source():
    m = load_mapping()
    sec511 = next(s for s in m["sections"] if s["fire"].startswith("5.1"))
    auth = [s for s in sec511["sources"] if s.get("authoritative")]
    assert auth and "30L/s" in auth[0]["anchor"]
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd skills/custom/fire-protection-extract && python -m pytest tests/test_mapping.py -v`
Expected: 2 PASS

- [ ] **Step 4: Commit**

```bash
git add skills/custom/fire-protection-extract/references/fire_spec_mapping.yaml skills/custom/fire-protection-extract/tests/test_mapping.py
git commit -m "feat(fire-extract): mapping contract yaml (8章×子节锚) + schema test"
```

---

## Task 4: extract.py — contract-driven verbatim assembly

**Files:**
- Create: `skills/custom/fire-protection-extract/scripts/extract.py`
- Create: `skills/custom/fire-protection-extract/tests/test_extract.py`

- [ ] **Step 1: Write the failing test**

`tests/test_extract.py`:
```python
import yaml
from pathlib import Path
from scripts.parse_spec import parse_spec
from scripts.extract import extract, build_report


def _structure(tiny_spec):
    return parse_spec(tiny_spec)


def _tiny_mapping():
    return {
        "report_title": "T 消防设计专篇",
        "sections": [
            {"fire": "2.1 概况", "class": "verbatim",
             "sources": [{"kind": "para", "anchor": "占地面积23.8亩"}]},
            {"fire": "2.2 给水(冲突)", "class": "verbatim",
             "sources": [{"kind": "para", "anchor": "室外消火栓水量30L/s", "authoritative": True}]},
            {"fire": "2.3 表", "class": "verbatim",
             "sources": [{"kind": "table", "no": "表2.1-1"}]},
            {"fire": "3 投资", "class": "compute", "note": "无源"},
        ],
        "templates": {},
    }


def test_extract_verbatim_para_and_table(tiny_spec):
    body, cites = extract(_structure(tiny_spec), _tiny_mapping())
    assert "占地面积23.8亩" in body           # verbatim para copied
    assert "30L/s（108m³/h）" in body          # authoritative para copied
    assert "室外消火栓" in body and "水量" in body  # table copied
    assert "[需计算]" in body                  # compute marker emitted
    assert ("2.2 给水(冲突)", "¶") in [(c[0], c[1]) for c in cites]


def test_extract_conflict_uses_authoritative_not_wrong_source(tiny_spec):
    body, _ = extract(_structure(tiny_spec), _tiny_mapping())
    # the WRONG 给水 datum must NOT appear (proves we didn't grab §9.1-style 8L/s)
    assert "8L/s" not in body
    assert "DN150" not in body
    # the AUTHORITATIVE 消防 datum must appear
    assert "30L/s" in body and "DN200" in body


def test_missing_anchor_is_flagged_not_silent(tiny_spec):
    m = _tiny_mapping()
    m["sections"][0]["sources"] = [{"kind": "para", "anchor": "这句根本不存在ZZZZ"}]
    body, _ = extract(_structure(tiny_spec), m)
    assert "[⚠未找到锚" in body


def test_build_report_has_title_and_headings(tiny_spec):
    md = build_report(_structure(tiny_spec), _tiny_mapping(), project_name="基地项目")
    assert md.startswith("# 基地项目 消防设计专篇")
    assert "## 2.1 概况" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd skills/custom/fire-protection-extract && python -m pytest tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.extract'`

- [ ] **Step 3: Write extract.py**

`scripts/extract.py`:
```python
#!/usr/bin/env python3
"""按映射契约从 structure.json 逐字摘抄组装消防专篇 Markdown。

每个 source 原子摘抄：
  para      -> 找到含 anchor 子串的源段，整段逐字复制
  para_run  -> 从含 from 的段到含 to 的段（闭区间），逐段复制
  table     -> 按 no 取整表，渲染为 Markdown 表
未命中锚/表 -> 显式 [⚠未找到...] 标记（绝不静默跳过，绝不编造）。
class=template -> 输出 mapping.templates[name]；class=compute -> 输出 [需计算]。
"""
import json
import sys
from pathlib import Path

import yaml


def find_para(paras, anchor):
    for p in paras:
        if anchor in p["text"]:
            return p
    return None


def find_run(paras, frm, to):
    start = next((i for i, p in enumerate(paras) if frm in p["text"]), None)
    if start is None:
        return None
    end = start
    for i in range(start, len(paras)):
        if to in paras[i]["text"]:
            end = i
            break
    else:
        end = len(paras) - 1
    return paras[start:end + 1]


def table_md(t):
    rows = t["rows"]
    if not rows:
        return ""
    head = rows[0]
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def extract(structure, mapping):
    paras, tables = structure["paras"], structure["tables"]
    lines, citations = [], []
    for sec in mapping["sections"]:
        lines.append("")
        lines.append(f"## {sec['fire']}")
        lines.append("")
        cls = sec.get("class")
        if cls == "template":
            tpl = (mapping.get("templates") or {}).get(sec.get("template"))
            if tpl:
                lines.append(tpl.rstrip())
                lines.append("")
            continue
        if cls == "compute":
            lines.append(f"[需计算] {sec.get('note', '')}")
            lines.append("")
            continue
        for src in sec.get("sources", []) or []:
            kind = src["kind"]
            if kind == "para":
                p = find_para(paras, src["anchor"])
                if p:
                    lines.append(p["text"])
                    lines.append(f"<!-- 源:¶{p['i']} -->")
                    citations.append((sec["fire"], "¶", p["i"], src["anchor"]))
                else:
                    lines.append(f"[⚠未找到锚: {src['anchor'][:24]}…]")
            elif kind == "para_run":
                run = find_run(paras, src["from"], src["to"])
                if run:
                    for p in run:
                        lines.append(p["text"])
                    lines.append(f"<!-- 源:¶{run[0]['i']}-{run[-1]['i']} -->")
                    citations.append((sec["fire"], "¶run", (run[0]["i"], run[-1]["i"]), src["from"]))
                else:
                    lines.append(f"[⚠未找到区间: {src['from'][:24]}…]")
            elif kind == "table":
                t = tables.get(src["no"])
                if t:
                    lines.append(table_md(t))
                    lines.append(f"<!-- 源:{src['no']} -->")
                    citations.append((sec["fire"], "表", src["no"], ""))
                else:
                    lines.append(f"[⚠未找到表: {src['no']}]")
            lines.append("")
    return "\n".join(lines).strip(), citations


def build_report(structure, mapping, project_name="XX"):
    body, _ = extract(structure, mapping)
    title = mapping.get("report_title", "{项目名} 消防设计专篇").replace("{项目名}", project_name)
    return f"# {title}\n\n{body}\n"


def main(argv):
    if len(argv) != 4:
        print("usage: extract.py <structure.json> <mapping.yaml> <report.md>", file=sys.stderr)
        return 2
    structure = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    mapping = yaml.safe_load(Path(argv[2]).read_text(encoding="utf-8"))
    report = build_report(structure, mapping)
    Path(argv[3]).write_text(report, encoding="utf-8")
    print(f"OK -> {argv[3]} ({len(report)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd skills/custom/fire-protection-extract && python -m pytest tests/test_extract.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/custom/fire-protection-extract/scripts/extract.py skills/custom/fire-protection-extract/tests/test_extract.py
git commit -m "feat(fire-extract): contract-driven verbatim extractor + conflict test"
```

---

## Task 5: grounding_check.py — verbatim safety net

**Files:**
- Create: `skills/custom/fire-protection-extract/scripts/grounding_check.py`
- Create: `skills/custom/fire-protection-extract/tests/test_grounding.py`

- [ ] **Step 1: Write the failing test**

`tests/test_grounding.py`:
```python
from scripts.parse_spec import parse_spec
from scripts.extract import build_report
from scripts.grounding_check import check, corpus


def _mapping():
    return {
        "report_title": "T",
        "sections": [
            {"fire": "1 概况", "class": "verbatim",
             "sources": [{"kind": "para", "anchor": "占地面积23.8亩"}]},
            {"fire": "2 消防水", "class": "verbatim",
             "sources": [{"kind": "para", "anchor": "室外消火栓水量30L/s"}]},
            {"fire": "3 表", "class": "verbatim",
             "sources": [{"kind": "table", "no": "表2.1-1"}]},
        ],
        "templates": {},
    }


def test_all_blocks_grounded(tiny_spec):
    s = parse_spec(tiny_spec)
    report = build_report(s, _mapping())
    res = check(report, s, _mapping())
    assert res["checked"] >= 3
    assert res["grounded"] == res["checked"]      # 100% verbatim
    assert res["rate"] == 1.0
    assert res["missing_anchors"] == []


def test_missing_anchor_reported(tiny_spec):
    s = parse_spec(tiny_spec)
    m = _mapping()
    m["sections"][0]["sources"][0]["anchor"] = "不存在ZZZ"
    res = check(build_report(s, m), s, m)
    assert len(res["missing_anchors"]) == 1
    assert res["missing_anchors"][0][0] == "1 概况"


def test_drift_detected(tiny_spec):
    s = parse_spec(tiny_spec)
    report = build_report(s, _mapping()) + "\n\n这是一段说明书里没有的编造内容用于触发漂移检测。\n"
    res = check(report, s, _mapping())
    assert res["grounded"] < res["checked"]       # the drift block fails
    assert res["rate"] < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd skills/custom/fire-protection-extract && python -m pytest tests/test_grounding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.grounding_check'`

- [ ] **Step 3: Write grounding_check.py**

`scripts/grounding_check.py`:
```python
#!/usr/bin/env python3
"""逐字溯源校验 + 锚可达性 + 覆盖检查。

三件事：
1. 锚可达：mapping 里每个 para/para_run/table 锚都能在 structure 里找到（否则契约漂移/源变了）。
2. 逐字溯源：report 里每个被抄录块（排除标题行/表格行/[需计算]/[⚠] 标记）必须是源语料的子串
   （空格/换行归一化后比对，容忍表格单元格空白差异）。
3. 覆盖：每个 fire 小节必须有源或显式标 template/compute，杜绝静默漏抄。
"""
import json
import re
import sys
from pathlib import Path

import yaml


def corpus(structure):
    parts = [p["text"] for p in structure["paras"]]
    for t in structure["tables"].values():
        for row in t["rows"]:
            parts.extend(row)
    return "\n".join(parts)


def _norm(s):
    return s.replace(" ", "").replace("　", "").replace("\n", "")


def _is_decorative(block):
    b = block.strip()
    if not b:
        return True
    if b.startswith("##") or b.startswith("# "):
        return True
    if b.startswith("|"):
        return True
    if b.startswith("[需") or b.startswith("[⚠"):
        return True
    if b.startswith("<!--"):
        return True
    return False


def check(report_md, structure, mapping):
    paras, tables = structure["paras"], structure["tables"]
    # 1. anchor resolvability
    missing = []
    for sec in mapping["sections"]:
        for src in sec.get("sources", []) or []:
            ok = False
            if src["kind"] == "para":
                ok = any(src["anchor"] in p["text"] for p in paras)
            elif src["kind"] == "para_run":
                ok = any(src["from"] in p["text"] for p in paras)
            elif src["kind"] == "table":
                ok = src["no"] in tables
            if not ok:
                missing.append((sec["fire"], src.get("anchor") or src.get("from") or src.get("no")))
    # 2. grounding
    corp = _norm(corpus(structure))
    blocks = [b.strip() for b in re.split(r"\n\s*\n", report_md)]
    checked = grounded = 0
    failed = []
    for b in blocks:
        if _is_decorative(b):
            continue
        checked += 1
        if _norm(b) and _norm(b) in corp:
            grounded += 1
        else:
            failed.append(b[:48])
    rate = grounded / checked if checked else 0.0
    # 3. coverage
    uncovered = [sec["fire"] for sec in mapping["sections"]
                 if sec.get("class") == "verbatim" and not sec.get("sources")]
    return {
        "grounded": grounded, "checked": checked, "rate": rate,
        "missing_anchors": missing, "uncovered_sections": uncovered,
        "failed_samples": failed[:5],
    }


def main(argv):
    if len(argv) != 4:
        print("usage: grounding_check.py <report.md> <structure.json> <mapping.yaml>", file=sys.stderr)
        return 2
    report = Path(argv[1]).read_text(encoding="utf-8")
    structure = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    mapping = yaml.safe_load(Path(argv[3]).read_text(encoding="utf-8"))
    res = check(report, structure, mapping)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["rate"] >= 0.85 and not res["missing_anchors"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd skills/custom/fire-protection-extract && python -m pytest tests/test_grounding.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/custom/fire-protection-extract/scripts/grounding_check.py skills/custom/fire-protection-extract/tests/test_grounding.py
git commit -m "feat(fire-extract): grounding verifier (verbatim/anchor/coverage)"
```

---

## Task 6: extractor_rules.md + SKILL.md workflow

**Files:**
- Create: `skills/custom/fire-protection-extract/references/extractor_rules.md`
- Create: `skills/custom/fire-protection-extract/SKILL.md`

- [ ] **Step 1: Write extractor_rules.md**

`references/extractor_rules.md`:
```markdown
# 抽取与溯源规则

## 三分类（每 fire 小节必标 class）
- `verbatim` 抄：从说明书逐字摘。source 必填。
- `template` 填：固定文本（标准清单/法规），用 mapping.templates[name]。
- `compute` 算：说明书无此数据（如§7投资概算），输出 `[需计算]`，绝不伪造。

## source 三种 kind
- `para` {anchor}：anchor=目标源段的唯一子串。复制含该子串的整段。
- `para_run` {from,to}：从含 from 的段到含 to 的段（闭区间），逐段复制。
- `table` {no}：表号如 `表3.1-1`，整表复制。

## 防抄错
1. 锚定位（非相似度）→ 防抄错段/错表。
2. `authoritative: true` → 冲突字段权威源。如消防水量取消防章（30L/s/DN200），不取给水章（8L/s/DN150）。
3. 逐字溯源校验 → 抄录块必须是源子串，否则标红。
4. 覆盖检查 → 每小节有源或标 template/compute，否则报警漏抄。

## 未命中处理
锚/表/区间在源里找不到 → 输出 `[⚠未找到...]`，**绝不静默跳过、绝不编造**。此时要么修契约锚，要么说明书结构变了（触发 cerebrum 记录的"投影"失配，需人工校准契约）。

## 锚选取
锚从「样本对」逐段比对得到，选源段里独一无二、抗改写的子串（含具体数值/编号/专有名词最佳）。换项目时锚可能失配——这是契约需要校准的信号，不是引擎 bug。
**⚠ 锚必须全局唯一**：`find_para` 返回第一个含锚的段。若同一子串在多段出现（典型陷阱：消防水量在
§9.1 给水段和 §9.2 消防段都以「室外消火栓水量30L/s」开头），必须把锚落在目标段**独有的续文**上
（如 §9.2 独有的「生活用水量10L/s」，§9.1 是 8L/s），否则会静默抄到错误段落——这正是要防的"抄错数值"。
grounding_check 的冲突断言（DN200 在 / DN150 不在）是这条的兜底验证。

## 复用件
- 解析：本技能 `scripts/parse_spec.py`（替代 v2 的 docx_to_md.py 用于结构化抽取；纯文本场景仍可用 v2 的）。
- 合规校验：`skills/custom/fire-regulatory-compliance-check/scripts/compliance_checker.py`（10 项 GB 检查）。
- 输出：write_file 到 outputs/ + present_files（沿用 v2 写盘铁律，一次写完）。
```

- [ ] **Step 2: Write SKILL.md**

`SKILL.md`:
```markdown
---
name: fire-protection-extract
description: |
  当用户为化工/石化项目编写「消防设计专篇」且已上传设计说明书(.docx)时使用此技能。
  它从设计说明书**逐字摘抄**重组出消防专篇（映射契约驱动 + 逐字溯源校验），而非从零生成。
  触发词：消防设计专篇/消防设计报告/消防设计篇章 + 有设计说明书。无说明书时改用 fire-protection-report-v2。
---

# 消防设计专篇 抽取技能

从已上传的**设计说明书**按映射契约精确摘抄出消防设计专篇。原则：**能抄尽抄，但不抄错**。

## 关键规则
0. 所有输出用中文（含 SESSION INTENT/SUMMARY/ARTIFACTS 等框架标签的中文替换）。
1. 仅用工具：read_file / bash / write_file / present_files / ask_clarification。禁调 text-to-cad_*/cad_*/word-document-server_*。
2. 上传的 docx 会在 uploads/ 自动生成同名 .md（markitdown）；但本技能需要**结构化**解析，用 bash 跑 parse_spec.py 生成 structure.json（见步骤2）。
3. 路径一律虚拟路径（/mnt/user-data/...、/mnt/skills/...）。禁容器物理路径。
4. 一次性 write_file 写完整报告到 outputs/，再 present_files（沿用 v2 写盘铁律，禁分块 append/str_replace 修补）。

## 工作流

### 步骤1：确认说明书
确认 uploads/ 下有 设计说明书.docx（或 .md）。缺项目名/编号用 ask_clarification 一次补齐。

### 步骤2：解析说明书为结构 JSON
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/parse_spec.py \
  "/mnt/user-data/uploads/<设计说明书>.docx" \
  "/mnt/user-data/workspace/<项目名>_struct.json"
```

### 步骤3：按契约抽取报告
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/extract.py \
  "/mnt/user-data/workspace/<项目名>_struct.json" \
  "/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.yaml" \
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md"
```
检查输出：有 `[⚠未找到...]` 说明契约锚与本项目说明书失配（结构差异）→ 走步骤3a。

### 步骤3a：失配处理（契约校准）
- 少量锚失配：read_file structure.json 找到对应内容的新锚，**临时**改一份 workspace 副本的 mapping 重跑（不直接改技能契约文件，除非用户要求沉淀）。
- 大面积失配：说明书结构与样本差异大 → ask_clarification 告知用户，考虑是否回退 fire-protection-report-v2 生成式。

### 步骤4：逐字溯源校验
```bash
python /mnt/skills/custom/fire-protection-extract/scripts/grounding_check.py \
  "/mnt/user-data/outputs/<项目名>消防设计专篇.md" \
  "/mnt/user-data/workspace/<项目名>_struct.json" \
  "/mnt/skills/custom/fire-protection-extract/references/fire_spec_mapping.yaml"
```
退出码 0 = 通过(rate≥0.85 且无失配锚)；非 0 = 看输出修契约锚后重跑步骤3-4。最多 2 轮。

### 步骤5：合规检查（复用 v2 链路）
```bash
python /mnt/skills/custom/fire-regulatory-compliance-check/scripts/compliance_checker.py \
  --report "/mnt/user-data/outputs/<项目名>消防设计专篇.md" \
  --output "/mnt/user-data/outputs/<项目名>消防合规检查报告.md"
```

### 步骤6：落盘 + 展示
一次 write_file（append=false）写完整报告到 outputs/，立即 present_files 触发文档空间同步。§7 投资概算保持 `[需计算]` 不伪造。

## 参考文件
- references/fire_spec_mapping.yaml — 映射契约（8章×子节→源锚；本项目结构不同时按步骤3a校准）
- references/extractor_rules.md — 抽取/溯源/防抄错规则
- scripts/parse_spec.py / extract.py / grounding_check.py — 引擎三件（report-agnostic，给排水/抗震将来复用）
```

- [ ] **Step 3: Commit**

```bash
git add skills/custom/fire-protection-extract/references/extractor_rules.md skills/custom/fire-protection-extract/SKILL.md
git commit -m "feat(fire-extract): SKILL.md workflow + extractor rules"
```

---

## Task 7: Real-sample integration test

**Files:**
- Create: `skills/custom/fire-protection-extract/tests/test_integration.py`

- [ ] **Step 1: Write the integration test** (skips if the sample isn't on disk)

`tests/test_integration.py`:
```python
"""End-to-end on the real sample pair. Skips unless the sample docx is present
(set FIRE_SAMPLE_DOCX env var or use the default path)."""
import os
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(os.environ.get(
    "FIRE_SAMPLE_DOCX",
    r"D:/18 辽宁创元/03 项目策划/02 中石油/吉林院/报告智能体/模板资料-00/基地项目/基地项目-设计说明书.docx",
))
MAPPING = ROOT / "references" / "fire_spec_mapping.yaml"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample design spec not present")


def test_sample_pipeline_meets_acceptance(tmp_path):
    struct_path = tmp_path / "struct.json"
    report_path = tmp_path / "report.md"
    # 1. parse
    subprocess.run([sys.executable, str(ROOT / "scripts" / "parse_spec.py"),
                    str(SAMPLE), str(struct_path)], check=True)
    structure = json.loads(struct_path.read_text(encoding="utf-8"))
    assert len(structure["paras"]) > 500, "expected a real design spec, not a stub"
    # 2. extract
    subprocess.run([sys.executable, str(ROOT / "scripts" / "extract.py"),
                    str(struct_path), str(MAPPING), str(report_path)], check=True)
    report = report_path.read_text(encoding="utf-8")
    # 3. acceptance: conflict field correct
    assert "30L/s" in report and "DN200" in report
    assert "生活用水量8L/s" not in report and "DN150" not in report
    # 4. acceptance: compute section not fabricated
    assert "[需计算]" in report
    # 5. grounding
    from scripts.grounding_check import check
    mapping = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
    res = check(report, structure, mapping)
    assert not res["missing_anchors"], f"unresolved anchors: {res['missing_anchors'][:5]}"
    assert res["rate"] >= 0.85, f"grounding rate {res['rate']:.2%} < 85%; failures: {res['failed_samples']}"
```

- [ ] **Step 2: Run it** (sample is present on this machine)

Run: `cd skills/custom/fire-protection-extract && python -m pytest tests/test_integration.py -v`
Expected: PASS. If an anchor doesn't resolve, the failure message names it — fix that anchor in `fire_spec_mapping.yaml` (it means the sample text differs slightly from the anchor) and rerun until green.

- [ ] **Step 3: Run the full suite**

Run: `cd skills/custom/fire-protection-extract && python -m pytest -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add skills/custom/fire-protection-extract/tests/test_integration.py
git commit -m "test(fire-extract): real-sample integration + acceptance (≥85% grounding, conflict resolution)"
```

---

## Self-Review (run after writing)

**1. Spec coverage:**
- 范式转变（生成→抽取-映射-校验）→ Tasks 2-5 ✓
- 内容三分类 verbatim/template/compute → mapping (Task 3) + extract (Task 4) + grounding coverage (Task 5) ✓
- 映射契约 8章×子节 → Task 3 yaml (all 22 sections present) ✓
- 按地址(锚)精确摘抄 → extract.py para/para_run/table ✓
- 逐字溯源校验 → Task 5 ✓
- 冲突字段权威源 (§9.1 vs §9.2) → mapping authoritative flag (Task 3) + test_extract conflict test (Task 4) + integration (Task 7) ✓
- 防抄错四层 → 锚定位/authoritative/grounding/coverage ✓
- 复用 v2 合规检查 + docx_to_md + present_files → SKILL.md steps 5-6 ✓
- 泛化口（引擎/契约分文件）→ file structure: 3 engine scripts vs fire_spec_mapping.yaml ✓
- 验收 ≥85% grounding + 空单元格不补全 + §7标[需计算] → Task 7 ✓

**2. Placeholder scan:** None — every code step has complete code; mapping yaml has all anchors transcribed from the sample.

**3. Type consistency:** `parse_spec` returns `{"paras":[{"i","text"}], "tables":{no:{"title","rows","n_rows"}}}` — used consistently in extract.py and grounding_check.py. `extract` returns `(body_str, citations_list)`. `check` returns dict with keys `grounded/checked/rate/missing_anchors/uncovered_sections/failed_samples`. All match across tests.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-03-fire-protection-extract.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
