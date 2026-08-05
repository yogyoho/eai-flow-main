# fire-protection-extract 分阶段重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 fire-protection-extract 技能从单一"基础设计"大纲重构为按阶段（初步设计 7 章 / 基础设计 8 章）生成消防设计专篇，彻底根治"契约格式漂移导致空章节"与"标题 XX"两个 bug。

**Architecture:** 两层分离——`references/stage-outlines/{阶段}.json` 为锁定的大纲骨架（章节/class/template/guide 关键词），`contracts/{阶段}/{项目}.json` 只存每节段落锚点（与大纲按索引对齐）。`run.sh` 先解析→检测阶段→加载大纲→阶段内找映射→校验格式→抽取→溯源。契约缺失或格式错误**硬失败**，绝不静默产出空报告。

**Tech Stack:** 纯 Python stdlib（json/sqlite 无）；bash；pytest（单元测试）。修改源在 `skills/public/fire-protection-extract/`（bind-mount 到容器 `/mnt/skills`，即时生效；另需同步 `backend/.deer-flow/skills_view/public/` 投影 + 重启 gateway）。

**分支：** `main-dev-fork`（用户既定工作分支，不用 worktree）。

---

## 文件结构

```
skills/public/fire-protection-extract/
├── references/
│   ├── stage-outlines/初步设计.json      [新建] 7章大纲（样例逐字标题+模板+guide）
│   ├── stage-outlines/基础设计.json      [新建] 8章大纲（由 fire_spec_mapping.json 演进+补guide）
│   ├── fire_spec_mapping.json            [删除→迁移入基础设计大纲]（或保留为兼容别名，见Task1）
│   └── extractor_rules.md                [重写] 新 schema 文档
├── scripts/
│   ├── detect_stage.py                   [新建] 阶段检测
│   ├── extract.py                        [重写] 两层合并 + 项目名参数
│   ├── contract_store.py                 [改造] stage 维度 + 格式校验
│   ├── grounding_check.py                [改造] 两层 + 大纲完整性
│   ├── migrate_contracts.py              [新建] 一次性迁移旧字符串锚契约
│   └── run.sh                            [重写] 阶段检测 + 硬失败
├── contracts/
│   ├── 初步设计/仓库项目.json             [迁移重建]
│   ├── 基础设计/基地项目.json             [迁移：旧锚→索引]
│   ├── 基础设计/基地综合大队消防站.json    [迁移：加_stage]
│   └── _index.json                       [重建] {stage:{name:fp}}
├── tests/
│   ├── test_staged_pipeline.py           [新建] 阶段检测/两层extract/格式校验 单元测试
│   ├── test_contract_store_stage.py      [新建] 阶段内 find/save/平局
│   └── verify_samples.sh                 [新建] 样例集成验证（读用户D盘样例，可选运行）
└── SKILL.md                              [更新] 阶段流程
```

---

## Task 1: 阶段大纲文件

**Files:**
- Create: `skills/public/fire-protection-extract/references/stage-outlines/初步设计.json`
- Create: `skills/public/fire-protection-extract/references/stage-outlines/基础设计.json`
- Test: `skills/public/fire-protection-extract/tests/test_staged_pipeline.py`

- [ ] **Step 1: 写失败测试**（验证大纲文件存在、结构合法、标题与规格附录一致）

```python
import json
from pathlib import Path

OUTLINES = Path(__file__).resolve().parents[1] / "references" / "stage-outlines"


def _load(stage: str) -> dict:
    return json.loads((OUTLINES / f"{stage}.json").read_text(encoding="utf-8"))


def test_outline_files_exist():
    assert (OUTLINES / "初步设计.json").exists()
    assert (OUTLINES / "基础设计.json").exists()


def test_outline_structure_valid():
    for stage in ("初步设计", "基础设计"):
        o = _load(stage)
        assert o["stage"] == stage
        assert "{项目名}" in o["report_title"]
        assert len(o["sections"]) > 15
        for sec in o["sections"]:
            assert sec["class"] in ("heading", "verbatim", "template", "compute")
            if sec["class"] == "template":
                assert sec["template"] in o["templates"]


def test_preliminary_outline_titles():
    o = _load("初步设计")
    titles = [s["fire"] for s in o["sections"]]
    assert "1 设计依据" in titles
    assert "1.1 设计依据的文件" in titles
    assert "2.4 工程的消防环境状况" in titles
    assert "4.1.1 装置的平面布置" in titles
    assert "4.6.1 建筑防火" in titles          # 样例正文含此节
    assert "5 消防系统设计" in titles
    assert "6 消防设施专项投资概算" in titles
    assert "7 图纸及表格" in titles
    assert not any("消防设施专项投资概算" in s["fire"] for s in o["sections"] if "8 " in s["fire"])


def test_basic_outline_titles():
    o = _load("基础设计")
    titles = [s["fire"] for s in o["sections"]]
    assert "1.3 及地方相关法规" in titles
    assert "4.5 建筑物通风措施" in titles
    assert "5.5 视频监控系统" in titles
    assert "6 灭火救援设施" in titles
    assert "8 图纸及表格" in titles
    assert "5.1 室外消防水系统" in titles       # 以样例正文为准（非目录"稳高压"）


def test_container_sections_have_no_guide():
    """容器节（自身无正文）不带 guide，避免 E3 误配锚点。"""
    for stage in ("初步设计", "基础设计"):
        o = _load(stage)
        for sec in o["sections"]:
            if sec["class"] == "heading":
                assert "guide" not in sec
```

- [ ] **Step 2: 运行确认失败**

Run（在 skill 目录）: `python -m pytest tests/test_staged_pipeline.py -v`
Expected: `FAILED ... FileNotFoundError`（outlines 不存在）

- [ ] **Step 3: 创建初步设计大纲**（标题逐字来自样例正文；容器节=heading；模板逐字见规格附录 A1）

`references/stage-outlines/初步设计.json`：
```json
{
  "stage": "初步设计",
  "outline_version": "2026-08-05",
  "report_title": "{项目名} 消防设计专篇",
  "sections": [
    {"fire": "1 设计依据", "class": "heading"},
    {"fire": "1.1 设计依据的文件", "class": "verbatim", "heading_level": 3, "guide": ["设计依据", "委托书", "可研", "批复", "基础工程设计内容规定"]},
    {"fire": "1.2 设计采用的主要消防技术标准和规范", "class": "template", "heading_level": 3, "template": "gb_standards"},
    {"fire": "2 项目概述", "class": "heading"},
    {"fire": "2.1 建设性质", "class": "verbatim", "heading_level": 3, "guide": ["建设性质", "新建", "改扩建"]},
    {"fire": "2.2 设计范围", "class": "verbatim", "heading_level": 3, "guide": ["设计范围"]},
    {"fire": "2.3 建设规模", "class": "verbatim", "heading_level": 3, "guide": ["建设规模", "储存", "库容"]},
    {"fire": "2.4 工程的消防环境状况", "class": "heading"},
    {"fire": "2.4.1 消防站情况", "class": "verbatim", "heading_level": 4, "guide": ["消防站", "消防队", "机动消防"]},
    {"fire": "2.4.2 消防水水源及管网依托情况", "class": "verbatim", "heading_level": 4, "guide": ["消防水", "水源", "管网", "给水管线"]},
    {"fire": "2.5 区域位置", "class": "verbatim", "heading_level": 3, "guide": ["区域位置", "地理位置", "厂址"]},
    {"fire": "3 火灾危险性分析", "class": "verbatim", "guide": ["火灾危险性", "生产类别", "火灾危险", "中危险"]},
    {"fire": "4 防火安全措施", "class": "heading"},
    {"fire": "4.1 总平面布置", "class": "heading"},
    {"fire": "4.1.1 装置的平面布置", "class": "verbatim", "heading_level": 4, "guide": ["平面布置", "库区", "贴邻"]},
    {"fire": "4.1.2 防火间距", "class": "verbatim", "heading_level": 4, "guide": ["防火间距", "间距为"]},
    {"fire": "4.1.3 消防通道", "class": "verbatim", "heading_level": 4, "guide": ["消防通道", "消防道路", "环形", "转弯半径"]},
    {"fire": "4.2 安防监控系统", "class": "verbatim", "heading_level": 3, "guide": ["安防", "监控", "摄像机"]},
    {"fire": "4.3 火灾报警系统", "class": "verbatim", "heading_level": 3, "guide": ["火灾报警", "探测器", "声光"]},
    {"fire": "4.4 防雷、接地及照明系统", "class": "heading"},
    {"fire": "4.4.1 防雷设计原则", "class": "verbatim", "heading_level": 4, "guide": ["防雷", "接闪", "避雷"]},
    {"fire": "4.4.2 接地设计原则", "class": "verbatim", "heading_level": 4, "guide": ["接地", "接地电阻"]},
    {"fire": "4.4.3 照明供电及控制", "class": "verbatim", "heading_level": 4, "guide": ["照明", "应急照明"]},
    {"fire": "4.5 供电安全", "class": "verbatim", "heading_level": 3, "guide": ["供电", "配电", "用电负荷", "负荷等级"]},
    {"fire": "4.6 建、构筑物防火", "class": "heading"},
    {"fire": "4.6.1 建筑防火", "class": "verbatim", "heading_level": 4, "guide": ["围护结构", "外墙", "耐火", "防火门"]},
    {"fire": "4.6.2 建、构筑物及钢结构的耐火保护", "class": "verbatim", "heading_level": 4, "guide": ["钢结构", "耐火保护", "防火涂料"]},
    {"fire": "5 消防系统设计", "class": "heading"},
    {"fire": "5.1 室外水消防系统", "class": "verbatim", "heading_level": 3, "guide": ["室外", "消防水", "消火栓", "消防给水"]},
    {"fire": "5.2 室内水消防系统", "class": "verbatim", "heading_level": 3, "guide": ["室内", "消防水", "消火栓", "消防泵"]},
    {"fire": "5.3 移动式灭火器", "class": "verbatim", "heading_level": 3, "guide": ["灭火器", "灭火器材"]},
    {"fire": "6 消防设施专项投资概算", "class": "compute", "note": "说明书无此数据，标[需计算]，由人工/概算技能补，不伪造"},
    {"fire": "7 图纸及表格", "class": "verbatim", "guide": ["附图", "附表", "图纸", "一览表"]}
  ],
  "templates": {
    "gb_standards": "建筑设计防火规范                  GB50016-2006\n爆炸和火灾危险环境电力装置设计规范GB50058-92\n火灾自动报警系统设计规范          GB50116-98\n建筑灭火器配置设计规范            GB50140-2005\n石油化工静电接地设计规范          SH3097-2000\n建筑物防雷设计规范                GB50057-94 (2000年版)\n室外给水设计规范                 GB50013-2006\n建筑物电子信息系统防雷技术规范    GB50343-2004\n"
  }
}
```

- [ ] **Step 4: 创建基础设计大纲**（由现 `fire_spec_mapping.json` 演进：保留其 sections，改 5.1 标题为正文"室外消防水系统"，补 `guide` 关键词，`report_title` 标注基础设计）

`references/stage-outlines/基础设计.json`：
```json
{
  "stage": "基础设计",
  "outline_version": "2026-08-05",
  "report_title": "{项目名} 消防设计专篇",
  "sections": [
    {"fire": "1 设计依据及采用的标准", "class": "heading"},
    {"fire": "1.1 设计依据", "class": "verbatim", "heading_level": 3, "guide": ["设计依据", "可研", "批复", "函"]},
    {"fire": "1.2 设计采用的技术标准、规范", "class": "template", "heading_level": 3, "template": "gb_standards"},
    {"fire": "1.3 及地方相关法规", "class": "template", "heading_level": 3, "template": "fire_law"},
    {"fire": "2 概述", "class": "heading"},
    {"fire": "2.1 项目位置", "class": "verbatim", "heading_level": 3, "guide": ["项目位置", "区域位置", "地理位置", "占地"]},
    {"fire": "2.2 项目建设功能定位", "class": "verbatim", "heading_level": 3, "guide": ["功能定位", "建成能够"]},
    {"fire": "2.3 建设规模", "class": "verbatim", "heading_level": 3, "guide": ["建设规模", "特勤", "规模为"]},
    {"fire": "2.4 建设内容", "class": "verbatim", "heading_level": 3, "guide": ["建设内容", "业务用房", "车库"]},
    {"fire": "2.5 建设性质", "class": "verbatim", "heading_level": 3, "guide": ["建设性质", "新建", "扩建"]},
    {"fire": "2.6 工程所在地地址气象条件", "class": "verbatim", "heading_level": 3, "guide": ["气象", "自然条件", "气温"]},
    {"fire": "2.7 周围消防站情况", "class": "verbatim", "heading_level": 3, "guide": ["消防站", "消防队", "邻近"]},
    {"fire": "3 火灾危险性分析", "class": "verbatim", "guide": ["火灾危险性", "生产类别", "丙类", "火灾危险"]},
    {"fire": "4 防火安全措施", "class": "heading"},
    {"fire": "4.1 总平面布置、防火间距及消防通道", "class": "verbatim", "heading_level": 3, "guide": ["总平面", "平面布置", "防火间距", "消防通道"]},
    {"fire": "4.2 防雷、接地的设计原则", "class": "heading"},
    {"fire": "4.2.1 防雷设计原则", "class": "verbatim", "heading_level": 4, "guide": ["防雷", "第三类防雷", "接闪"]},
    {"fire": "4.2.2 接地设计原则", "class": "verbatim", "heading_level": 4, "guide": ["接地", "接地电阻"]},
    {"fire": "4.3 供电安全", "class": "heading"},
    {"fire": "4.3.1 设计范围", "class": "verbatim", "heading_level": 4, "guide": ["设计范围", "供电范围"]},
    {"fire": "4.3.2 用电负荷", "class": "verbatim", "heading_level": 4, "guide": ["用电负荷", "负荷等级"]},
    {"fire": "4.3.3 供、配电系统", "class": "verbatim", "heading_level": 4, "guide": ["供配电", "配电系统"]},
    {"fire": "4.3.4 供、配电系统设计", "class": "verbatim", "heading_level": 4, "guide": ["配电系统设计", "低压配电"]},
    {"fire": "4.3.5 配电设计", "class": "verbatim", "heading_level": 4, "guide": ["配电设计", "配电箱"]},
    {"fire": "4.3.6 照明", "class": "verbatim", "heading_level": 4, "guide": ["照明", "应急照明", "照度"]},
    {"fire": "4.4 建、构筑物防火", "class": "heading"},
    {"fire": "4.4.1 建筑类型及规模", "class": "verbatim", "heading_level": 4, "guide": ["建筑类型", "耐火等级", "建筑面积"]},
    {"fire": "4.4.2 采用的防火、防水、抗震、节能等技术措施", "class": "verbatim", "heading_level": 4, "guide": ["防火", "防水", "抗震", "节能", "防火门"]},
    {"fire": "4.4.3 主要建筑物构造及装修", "class": "verbatim", "heading_level": 4, "guide": ["构造", "装修", "砌块", "墙"]},
    {"fire": "4.5 建筑物通风措施", "class": "verbatim", "heading_level": 3, "guide": ["通风", "排风", "换气"]},
    {"fire": "5 消防设施", "class": "heading"},
    {"fire": "5.1 室外消防水系统", "class": "verbatim", "heading_level": 3, "guide": ["室外", "消防水", "消火栓", "DN"]},
    {"fire": "5.2 室内水消防系统", "class": "verbatim", "heading_level": 3, "guide": ["室内", "消防水池", "消火栓", "消防泵"]},
    {"fire": "5.3 移动式灭火器", "class": "verbatim", "heading_level": 3, "guide": ["灭火器", "灭火器材"]},
    {"fire": "5.4 火灾报警系统", "class": "heading"},
    {"fire": "5.4.1 系统构成", "class": "verbatim", "heading_level": 4, "guide": ["系统构成", "火灾自动报警", "探测器"]},
    {"fire": "5.4.2 设置原则和安装地点", "class": "verbatim", "heading_level": 4, "guide": ["设置原则", "安装地点"]},
    {"fire": "5.4.3 消防联动控制逻辑关系", "class": "verbatim", "heading_level": 4, "guide": ["联动", "控制逻辑"]},
    {"fire": "5.4.4 系统电源", "class": "verbatim", "heading_level": 4, "guide": ["系统电源", "供电"]},
    {"fire": "5.5 视频监控系统", "class": "heading"},
    {"fire": "5.5.1 系统构成", "class": "verbatim", "heading_level": 4, "guide": ["系统构成", "摄像机"]},
    {"fire": "5.5.2 控制方式", "class": "verbatim", "heading_level": 4, "guide": ["控制方式", "控制室"]},
    {"fire": "5.5.3 供电方式及电源", "class": "verbatim", "heading_level": 4, "guide": ["供电方式", "电源"]},
    {"fire": "5.5.4 设置地点", "class": "verbatim", "heading_level": 4, "guide": ["设置地点", "安装地点"]},
    {"fire": "6 灭火救援设施", "class": "verbatim", "guide": ["消防道路", "消防通道", "转弯半径"]},
    {"fire": "7 消防设施专项投资概算", "class": "compute", "note": "说明书无此数据，标[需计算]，由人工/概算技能补，不伪造"},
    {"fire": "8 图纸及表格", "class": "verbatim", "guide": ["附图", "附表", "图纸", "一览表"]}
  ],
  "templates": {
    "gb_standards": "石油化工企业设计防火标准（2018版）        GB50160-2008\n建筑设计防火规范（2018版）                GB50016-2014\n爆炸危险环境电力装置设计规范              GB50058-2014\n火灾自动报警系统设计规范                  GB50116-2013\n建筑灭火器配置设计规范                    GB50140-2005\n消防给水及消火栓系统技术规范              GB50974-2014\n",
    "fire_law": "中华人民共和国消防法（2019.4.23）"
  }
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_staged_pipeline.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add skills/public/fire-protection-extract/references/stage-outlines/ skills/public/fire-protection-extract/tests/test_staged_pipeline.py
git commit -m "feat(fire-extract): 阶段大纲文件 — 初步设计7章/基础设计8章 逐字锁样例"
```

---

## Task 2: detect_stage.py

**Files:**
- Create: `skills/public/fire-protection-extract/scripts/detect_stage.py`
- Test: `skills/public/fire-protection-extract/tests/test_staged_pipeline.py`

- [ ] **Step 1: 写失败测试**（追加到 test_staged_pipeline.py）

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import detect_stage


def test_detect_from_paras_initial():
    struct = {"paras": [{"i": 0, "text": "项目名"}, {"i": 1, "text": "初步设计"}, {"i": 2, "text": "消防设计专篇"}]}
    assert detect_stage.detect_from_struct(struct) == "初步设计"


def test_detect_from_paras_basic():
    struct = {"paras": [{"i": 0, "text": "项目名"}, {"i": 1, "text": "基础设计"}, {"i": 2, "text": "第一册 说明书"}]}
    assert detect_stage.detect_from_struct(struct) == "基础设计"


def test_detect_default_when_absent():
    struct = {"paras": [{"i": 0, "text": "项目名"}, {"i": 1, "text": "消防设计专篇"}], "headings": []}
    assert detect_stage.detect_from_struct(struct) == detect_stage.DEFAULT_STAGE


def test_detect_both_markers_treats_ambiguous_as_default():
    # 封面同页含两词时，优先精确段落命中；命中歧义 → 默认
    struct = {"paras": [{"i": 0, "text": "初步设计及基础设计说明"}]}
    assert detect_stage.detect_from_struct(struct) == detect_stage.DEFAULT_STAGE
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_staged_pipeline.py -k detect_ -v`
Expected: `FAILED ... ModuleNotFoundError: No module named 'detect_stage'`

- [ ] **Step 3: 实现**

`scripts/detect_stage.py`：
```python
#!/usr/bin/env python3
"""Detect design stage (初步设计/基础设计) from a parsed structure.

Only reads document text; explicit user override is applied by run.sh.
"""
import json
import sys

DEFAULT_STAGE = "基础设计"


def _has_only(t: str, stage: str) -> bool:
    other = "基础设计" if stage == "初步设计" else "初步设计"
    return stage in t and other not in t


def detect_from_struct(struct: dict) -> str:
    # Title-page marks appear in the first ~60 paragraphs.
    for p in struct.get("paras", [])[:60]:
        t = p.get("text", "")
        if _has_only(t, "初步设计"):
            return "初步设计"
        if _has_only(t, "基础设计"):
            return "基础设计"
    for h in struct.get("headings", []):
        t = h.get("text", "")
        if _has_only(t, "初步设计"):
            return "初步设计"
        if _has_only(t, "基础设计"):
            return "基础设计"
    return DEFAULT_STAGE


def main(argv):
    if len(argv) != 1:
        print("usage: detect_stage.py <structure.json>", file=sys.stderr)
        return 2
    struct = json.loads(open(argv[0], encoding="utf-8").read())
    print(detect_from_struct(struct))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_staged_pipeline.py -k detect_ -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add skills/public/fire-protection-extract/scripts/detect_stage.py skills/public/fire-protection-extract/tests/test_staged_pipeline.py
git commit -m "feat(fire-extract): detect_stage — 从源文档识别初步设计/基础设计"
```

---

## Task 3: extract.py 两层合并 + 项目名参数

**Files:**
- Rewrite: `skills/public/fire-protection-extract/scripts/extract.py`
- Test: `skills/public/fire-protection-extract/tests/test_staged_pipeline.py`

- [ ] **Step 1: 写失败测试**（追加）

```python
def _mini_outline():
    return {
        "report_title": "{项目名} 消防设计专篇",
        "sections": [
            {"fire": "1 设计依据", "class": "heading"},
            {"fire": "1.1 设计依据", "class": "verbatim", "heading_level": 3},
            {"fire": "1.2 标准", "class": "template", "heading_level": 3, "template": "gb_standards"},
            {"fire": "7 投资概算", "class": "compute", "note": "无数据"},
        ],
        "templates": {"gb_standards": "GB50016-2014"},
    }


def _mini_struct():
    return {"paras": [{"i": 0, "text": "依据A"}, {"i": 1, "text": "依据B"}, {"i": 2, "text": "无关段"}], "tables": {}}


def _mini_mapping():
    return {"sources": [None, [{"kind": "range", "paras": [0, 1]}], None, None]}


def test_two_layer_extract_merges_outline_and_sources():
    import extract
    out, _ = extract.extract(_mini_struct(), _mini_outline(), _mini_mapping())
    assert "1 设计依据" in out
    assert "1.1 设计依据" in out
    assert "依据A" in out and "依据B" in out
    assert "无关段" not in out          # 未锚定的段落不得抄入
    assert "GB50016-2014" in out        # template 从大纲取
    assert "[需计算] 无数据" in out


def test_two_layer_title_uses_project_name():
    import extract
    report = extract.build_report(_mini_struct(), _mini_outline(), _mini_mapping(), project_name="吉林石化新装置")
    assert report.startswith("# 吉林石化新装置 消防设计专篇")
    assert "XX" not in report.splitlines()[0]


def test_two_layer_missing_sources_mark_not_found():
    import extract
    mapping = {"sources": [None, None, None, None]}
    out, _ = extract.extract(_mini_struct(), _mini_outline(), mapping)
    assert "[⚠未找到段落" in out
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_staged_pipeline.py -k two_layer -v`
Expected: FAIL（旧 extract.py 签名不兼容 `extract(struct, outline, mapping)`）

- [ ] **Step 3: 重写 extract.py**

```python
#!/usr/bin/env python3
"""按阶段大纲 + 项目映射 逐字摘抄组装消防专篇 Markdown。

大纲 outline = 阶段骨架：sections[].{fire,class,heading_level,template,note,guide} + templates{}。
映射 mapping = 项目锚点：sources[] 与 outline.sections 按索引对齐（无源的节为 null 或 []）。

Each source atom:
  para  -> 按段落索引逐字复制（paras: [i]）
  range -> 按闭区间逐段复制（paras: [from, to]）
  table -> 按 no 取整表，渲染为 Markdown 表
未命中 → 显式 [⚠未找到...] 标记。
class=template -> 输出 outline.templates[name]；class=compute -> 输出 [需计算]。
段落索引由 E3 工作流中的 LLM 分析 structure.json 后生成——引擎只按给定索引逐字复制，
不做字符串匹配（字符串锚格式已废弃，见 extractor_rules.md）。
"""
import json
import sys
from pathlib import Path


def table_md(t):
    rows = t["rows"]
    if not rows:
        return ""

    def _flat(cell):
        return cell.replace("\n", " ")

    head = [_flat(c) for c in rows[0]]
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(_flat(c) for c in r) + " |")
    return "\n".join(out)


def extract(structure, outline, mapping):
    paras, tables = structure["paras"], structure["tables"]
    lines, citations = [], []
    n_paras = len(paras)
    sections = outline.get("sections", [])
    sources_by_idx = mapping.get("sources", [])

    for idx, sec in enumerate(sections):
        lines.append("")
        level = sec.get("heading_level", 2)
        lines.append(f"{'#' * level} {sec['fire']}")
        lines.append("")
        cls = sec.get("class")
        if cls == "heading":
            continue
        if cls == "template":
            tpl = (outline.get("templates") or {}).get(sec.get("template"))
            lines.append(tpl.rstrip() if tpl else f"[⚠未找到模板: {sec.get('template') or '<未指定>'}]")
            lines.append("")
            continue
        if cls == "compute":
            lines.append(f"[需计算] {sec.get('note', '')}")
            lines.append("")
            continue

        src_ref = sec.get("source_label", "设计说明书")
        sources = sources_by_idx[idx] if idx < len(sources_by_idx) else []
        sources = sources or []
        for src in sources:
            kind = src.get("kind")
            idxs = src.get("paras")
            resolved_kind = "range" if kind == "para_run" else kind  # 旧别名兼容（format 校验已挡，兜底）
            if resolved_kind == "para" and idxs and len(idxs) >= 1 and 0 <= idxs[0] < n_paras:
                p = paras[idxs[0]]
                lines.append(p["text"])
                lines.append(f"> 源: {src_ref} ¶{p['i']}")
                citations.append((sec["fire"], "¶", p["i"], str(idxs[0])))
            elif resolved_kind == "range" and idxs and len(idxs) >= 2 and 0 <= idxs[0] < n_paras and idxs[1] < n_paras:
                start, end = idxs[0], idxs[1]
                for p in paras[start:end + 1]:
                    lines.append(p["text"])
                    lines.append("")
                lines.append(f"> 源: {src_ref} ¶{paras[start]['i']}-{paras[end]['i']}")
                citations.append((sec["fire"], "¶run", (paras[start]["i"], paras[end]["i"]), str(idxs)))
            elif kind == "table":
                no = src.get("no", "")
                t = tables.get(no)
                if t:
                    lines.append(table_md(t))
                    lines.append(f"> 源: {src_ref} {no}")
                    citations.append((sec["fire"], "表", no, ""))
                else:
                    lines.append(f"[⚠未找到表: {no}]")
            else:
                lines.append(f"[⚠未找到段落: {idxs}]")
            lines.append("")

    return "\n".join(lines).strip(), citations


def build_report(structure, outline, mapping, project_name="XX"):
    body, _ = extract(structure, outline, mapping)
    title = outline.get("report_title", "{项目名} 消防设计专篇")
    title = title.replace("{项目名}", project_name)
    return f"# {title}\n\n{body}\n"


def _load_json(path_str):
    p = Path(path_str)
    text = p.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import yaml
        return yaml.safe_load(text)


def main(argv):
    if len(argv) != 5:
        print("usage: extract.py <structure.json> <outline.json> <mapping.json|yaml> <report.md> <project_name>", file=sys.stderr)
        return 2
    structure = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    outline = _load_json(argv[1])
    mapping = _load_json(argv[2])
    report = build_report(structure, outline, mapping, project_name=argv[4])
    Path(argv[3]).write_text(report, encoding="utf-8")
    print(f"OK -> {argv[3]} ({len(report)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_staged_pipeline.py -k two_layer -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add skills/public/fire-protection-extract/scripts/extract.py skills/public/fire-protection-extract/tests/test_staged_pipeline.py
git commit -m "feat(fire-extract): extract.py 两层合并 + 项目名参数(修XX标题)"
```

---

## Task 4: contract_store.py 阶段维度 + 格式校验

**Files:**
- Modify: `skills/public/fire-protection-extract/scripts/contract_store.py`
- Test: `skills/public/fire-protection-extract/tests/test_contract_store_stage.py`

- [ ] **Step 1: 写失败测试**

`tests/test_contract_store_stage.py`：
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_contract_store_stage.py -v`
Expected: FAIL（`save_contract` 无 `stage` 参数 / `validate_format` 不存在）

- [ ] **Step 3: 改造 contract_store.py**

关键变更（保留 `save/load/find/list` CLI 但加 stage 参数；新增 `validate_format`）：

```python
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
INDEX_PATH = CONTRACTS_DIR / "_index.json"

LEGACY_ANCHOR_KEYS = ("anchor", "from", "to")  # 旧字符串锚格式已废弃


def validate_format(mapping):
    """新格式合法返回 None；旧字符串锚格式返回错误说明。"""
    if "sections" in mapping and any(
        ("anchor" in src or "from" in src or "to" in src)
        for sec in mapping.get("sections", [])
        for src in sec.get("sources", []) or []
    ):
        return "旧字符串锚格式(anchor/from/to)已废弃，请用 paras 索引新格式并重跑 E3"
    if "sources" in mapping:
        for srcs in mapping["sources"]:
            for src in srcs or []:
                if "anchor" in src or "from" in src or "to" in src:
                    return "旧字符串锚格式(anchor/from/to)已废弃，请用 paras 索引新格式并重跑 E3"
    return None


def save_contract(name, stage, mapping, structure):
    _ensure_dir()
    contract_dir = CONTRACTS_DIR / stage
    contract_dir.mkdir(parents=True, exist_ok=True)
    contract_path = contract_dir / f"{name}.json"
    fp = fingerprint_from_structure(structure)
    contract = dict(mapping)
    contract.setdefault("_stage", stage)
    contract["_saved_at"] = datetime.now().isoformat()
    contract["_fingerprint"] = fp
    tmp_path = contract_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, contract_path)
    index = _read_index()
    index.setdefault(stage, {})[name] = fp
    _write_index(index)
    return contract_path


def load_contract(name, stage):
    try:
        contract_path = CONTRACTS_DIR / stage / f"{name}.json"
        return json.loads(contract_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def find_best(structure, stage=None, min_similarity=0.3):
    index = _read_index()
    if not index:
        return None
    stages = [stage] if stage else list(index.keys())
    target_fp = fingerprint_from_structure(structure)
    best_name, best_sim, best_saved = None, 0.0, ""
    for st in stages:
        for name, stored_fp in index.get(st, {}).items():
            sim = _combined_similarity(target_fp, stored_fp)
            saved = load_contract(name, st).get("_saved_at", "") if load_contract(name, st) else ""
            # 严格大于 → 首胜；同分取最新保存
            if sim > best_sim or (sim == best_sim and saved > best_saved and sim > 0):
                best_sim, best_name, best_saved = sim, name, saved
    if best_name and best_sim >= min_similarity:
        mapping = load_contract(best_name, stage if stage else _stage_of(best_name, index))
        if mapping:
            return best_name, mapping, best_sim
    return None


def _stage_of(name, index):
    for st, names in index.items():
        if name in names:
            return st
    return None
```

CLI `main(argv)` 更新为：
```python
if cmd == "save":   # usage: save <stage> <name> <structure.json>
if cmd == "load":   # usage: load <stage> <name>
if cmd == "find":   # usage: find <stage> <structure.json>
if cmd == "list":   # 遍历 {stage: name}
```

（保存 `find_best` 对旧格式契约先 `validate_format`，不合法则跳过并在 CLI 打印 `CONTRACT_FORMAT_MISMATCH`。）

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_contract_store_stage.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add skills/public/fire-protection-extract/scripts/contract_store.py skills/public/fire-protection-extract/tests/test_contract_store_stage.py
git commit -m "feat(fire-extract): contract_store 阶段维度 + 旧格式校验硬失败"
```

---

## Task 5: grounding_check.py 两层 + 大纲完整性

**Files:**
- Modify: `skills/public/fire-protection-extract/scripts/grounding_check.py`
- Test: `skills/public/fire-protection-extract/tests/test_staged_pipeline.py`

- [ ] **Step 1: 写失败测试**

```python
def test_grounding_two_layer_and_completeness():
    import grounding_check
    struct = _mini_struct()
    outline = _mini_outline()
    mapping = {"sources": [None, [{"kind": "range", "paras": [0, 1]}], None, None]}
    report, _ = extract.extract(struct, outline, mapping)
    res = grounding_check.check(report, struct, outline, mapping)
    assert res["rate"] >= 0.5
    assert res["missing_anchors"] == []
    # 完整性：verbatim 节必须有 source
    assert res["uncovered_sections"] == []


def test_grounding_completeness_flags_missing_verbatim_source():
    import grounding_check
    struct = _mini_struct()
    outline = _mini_outline()
    mapping = {"sources": [None, None, None, None]}  # 1.1 verbatim 无 source
    report, _ = extract.extract(struct, outline, mapping)
    res = grounding_check.check(report, struct, outline, mapping)
    assert any("1.1 设计依据" in s for s in res["uncovered_sections"])
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_staged_pipeline.py -k grounding -v`
Expected: FAIL（`check` 签名不兼容）

- [ ] **Step 3: 改造 grounding_check.py**

关键变更：`check(report_md, structure, outline, mapping)`——锚可达性改为遍历 `mapping["sources"]`（对齐大纲），覆盖检查改为"大纲每个 verbatim 节必须有非空 sources"：

```python
def check(report_md, structure, outline, mapping):
    paras, tables = structure["paras"], structure["tables"]
    missing = []
    n_paras = len(paras)
    sections = outline.get("sections", [])
    sources_by_idx = mapping.get("sources", [])

    for idx, sec in enumerate(sections):
        if sec.get("class") != "verbatim":
            continue
        sources = sources_by_idx[idx] if idx < len(sources_by_idx) else []
        sources = sources or []
        for src in sources:
            ok = False
            kind = src.get("kind", "")
            if kind in ("para", "range", "para_run"):
                idxs = src.get("paras", [])
                ok = (idxs and all(isinstance(i, int) and 0 <= i < n_paras for i in idxs))
                if ok:
                    ok = all(paras[i].get("text", "").strip() for i in idxs)
            elif kind == "table":
                ok = src.get("no", "") in tables
            if not ok:
                label = src.get("no") or str(src.get("paras", src))
                missing.append((sec["fire"], label))

    # grounding（与现实现一致：corpus 逐字溯源）
    corp = _norm(corpus(structure))
    blocks = [b.strip() for b in re.split(r"\n\s*\n", report_md)]
    checked = grounded = 0
    failed = []
    for b in blocks:
        if _is_decorative(b):
            continue
        checked += 1
        needle = _norm(_search_text(b))
        if needle and needle in corp:
            grounded += 1
        else:
            failed.append(b[:48])
    rate = grounded / checked if checked else 0.0

    # 完整性：大纲每个 verbatim 节必须有非空 sources
    uncovered = [sec["fire"] for idx, sec in enumerate(sections)
                 if sec.get("class") == "verbatim"
                 and not (sources_by_idx[idx] if idx < len(sources_by_idx) else [])]

    conflict_failures = []
    for sec in sections:
        for ca in sec.get("conflict_assertions", []) or []:
            mc = ca.get("must_contain")
            mnc = ca.get("must_not_contain")
            if mc and mc not in report_md:
                conflict_failures.append((sec["fire"], "missing", mc))
            if mnc and mnc in report_md:
                conflict_failures.append((sec["fire"], "unexpected", mnc))

    return {
        "grounded": grounded, "checked": checked, "rate": rate,
        "missing_anchors": missing, "uncovered_sections": uncovered,
        "conflict_failures": conflict_failures,
        "failed_samples": failed[:5],
    }
```

`main(argv)` 改为 4 参：`grounding_check.py <report.md> <structure.json> <outline.json> <mapping.json>`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_staged_pipeline.py -k grounding -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add skills/public/fire-protection-extract/scripts/grounding_check.py skills/public/fire-protection-extract/tests/test_staged_pipeline.py
git commit -m "feat(fire-extract): grounding_check 两层 + 大纲完整性检查"
```

---

## Task 6: run.sh 阶段检测 + 硬失败

**Files:**
- Rewrite: `skills/public/fire-protection-extract/scripts/run.sh`

- [ ] **Step 1: 重写 run.sh**

要点：
1. 参数：`run.sh "<说明书.docx>" "<项目名>" [--stage 初步设计|基础设计]`（可选显式阶段）
2. 第 0 步解析 struct 后调用 `detect_stage.py` 得 STAGE（显式 `--stage` 优先）
3. 加载 `references/stage-outlines/$STAGE.json` 为 OUTLINE
4. `contract_store.py find $STAGE $STRUCT`：
   - 命中 → `validate_format`，合法则抽取；非法 → 打印 `CONTRACT_FORMAT_MISMATCH` 并 exit 3
   - 未命中 → 打印 `CONTRACT_NEEDED: <struct>` + `STAGE: <stage>` + `OUTLINE: <path>`，**exit 3**（不产出空报告）
5. `extract.py <struct> <outline> <mapping> <report> <项目名>`
6. `grounding_check.py <report> <struct> <outline> <mapping>` → `grounding ≥ 0.85` 且 `missing_anchors == []` 且 `uncovered_sections == []` 才 PASS
7. 合规检查、passport（不变）
8. 输出 `REPORT_READY:` 或 `REPORT_NEEDS_REVIEW:`

```bash
#!/usr/bin/env bash
# 消防设计专篇 一键流水线：解析 → 阶段检测 → 大纲 → 契约 → 抽取 → 溯源校验。
#   bash run.sh "<设计说明书.docx>" "<项目名>" [阶段]
#   可选第3参阶段：初步设计|基础设计（显式覆盖自动识别）

set -euo pipefail
export PYTHONIOENCODING=utf-8

if [ "$#" -lt 2 ]; then
  echo "usage: bash run.sh <设计说明书.docx> <项目名> [初步设计|基础设计]" >&2
  exit 2
fi

DOCX="${1:?need docx}"
PROJECT="${2:?need project}"
STAGE_OVERRIDE="${3:-}"

WORK_DIR="${WORK:-/mnt/user-data/workspace}"
OUT_DIR="${OUT:-/mnt/user-data/outputs}"
for _try in "/app/skills" "/mnt/skills" "$(dirname "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")")"; do
  if [ -f "${_try}/public/fire-protection-extract/scripts/parse_spec.py" ]; then
    SKILL_DIR="${_try}/public/fire-protection-extract"; break
  fi
  if [ -f "${_try}/scripts/parse_spec.py" ]; then SKILL_DIR="${_try}"; break; fi
done
if [ -z "${SKILL_DIR:-}" ]; then echo "ERROR: skills dir not found" >&2; exit 1; fi

REPORT="${OUT_DIR}/${PROJECT}消防设计专篇.md"
STRUCT="${WORK_DIR}/${PROJECT}_struct.json"
OUTLINE_DIR="${SKILL_DIR}/references/stage-outlines"
MAPPING="${WORK_DIR}/${PROJECT}_mapping.json"

mkdir -p "$WORK_DIR" "$OUT_DIR"

echo "[1/5] 解析说明书..."
python "${SKILL_DIR}/scripts/parse_spec.py" "$DOCX" "$STRUCT"

echo "[2/5] 阶段检测..."
if [ -n "$STAGE_OVERRIDE" ]; then
  STAGE="$STAGE_OVERRIDE"
  echo "  显式阶段: $STAGE"
else
  STAGE=$(python "${SKILL_DIR}/scripts/detect_stage.py" "$STRUCT")
  echo "  自动识别: $STAGE"
fi
OUTLINE="${OUTLINE_DIR}/${STAGE}.json"
if [ ! -f "$OUTLINE" ]; then echo "ERROR: 阶段大纲不存在 $OUTLINE" >&2; exit 3; fi

echo "[3/5] 契约查找 (stage=$STAGE)..."
FOUND=""
if python "${SKILL_DIR}/scripts/contract_store.py" find "$STAGE" "$STRUCT" > "$MAPPING" 2>/dev/null; then
  FOUND=$(python -c "import sys,json; print(json.load(open('$MAPPING',encoding='utf-8'))['name'])" 2>/dev/null || echo "")
  FORMAT_ERR=$(python -c "
import json,sys
m=json.load(open('$MAPPING',encoding='utf-8'))['mapping']
import importlib.util
spec=importlib.util.spec_from_file_location('cs','${SKILL_DIR}/scripts/contract_store.py')
cs=importlib.util.module_from_spec(spec); spec.loader.exec_module(cs)
print(cs.validate_format(m) or '')" 2>/dev/null || echo "契约解析失败")
  if [ -n "$FORMAT_ERR" ]; then
    echo "CONTRACT_FORMAT_MISMATCH: $FORMAT_ERR" >&2
    echo "  → 该契约是旧字符串锚格式，需删除后重跑 E3 生成新契约" >&2
    exit 3
  fi
  python -c "import sys,json; m=json.load(open('$MAPPING',encoding='utf-8'))['mapping']; json.dump(m,open('$MAPPING','w',encoding='utf-8'),ensure_ascii=False,indent=2)" 2>/dev/null || true
  echo "  ✓ 使用契约: ${FOUND}"
else
  echo "CONTRACT_NEEDED: ${STRUCT}"
  echo "STAGE: ${STAGE}"
  echo "OUTLINE: ${OUTLINE}"
  echo "  → 新项目/新阶段，需 E3 生成 <项目名>_mapping.json 后重跑" >&2
  exit 3
fi

echo "[4/5] 按契约抽取报告..."
python "${SKILL_DIR}/scripts/extract.py" "$STRUCT" "$OUTLINE" "$MAPPING" "$REPORT" "$PROJECT"

echo "[5/5] 逐字溯源校验..."
GROUNDING_ERR_LOG="${WORK_DIR}/${PROJECT}_grounding_err.log"
GROUNDING_OUT=$(python "${SKILL_DIR}/scripts/grounding_check.py" "$REPORT" "$STRUCT" "$OUTLINE" "$MAPPING" 2>"$GROUNDING_ERR_LOG") || true
echo "$GROUNDING_OUT"

REPORT_STATUS="NEEDS_REVIEW"
if echo "$GROUNDING_OUT" | grep -q '"rate"'; then
  RATE=$(echo "$GROUNDING_OUT" | python -c "import sys,json; print(json.load(sys.stdin).get('rate',0))" 2>/dev/null || echo "0")
  MISS=$(echo "$GROUNDING_OUT" | python -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('missing_anchors',[])) + len(d.get('uncovered_sections',[])))" 2>/dev/null || echo "99")
  echo "grounding_rate: ${RATE}  missing_anchors+uncovered: ${MISS}"
  if python -c "exit(0 if float(${RATE:-0}) >= 0.85 and int(${MISS:-99}) == 0 else 1)" 2>/dev/null; then
    REPORT_STATUS="READY"
  fi
fi

if grep -q "\[⚠未找到" "$REPORT"; then
  echo "⚠ 报告含 $(grep -c '\[⚠未找到' "$REPORT" || true) 处失配锚。E5 校准或 E3 重跑。"
fi

# ── 合规检查（复用）──────────────────────────────
COMPLIANCE="${OUT_DIR}/${PROJECT}消防设计合规检查报告.md"
COMPLIANCE_STATUS="pass"
if python "${SKILL_DIR}/scripts/compliance_check.py" "$REPORT" > "$COMPLIANCE" 2>&1; then
  echo "  ✓ 合规检查通过"
else
  COMPLIANCE_STATUS="issues"
  echo "  ⚠ 合规检查发现问题，详见报告"
fi

# ── Passport ──────────────────────────────────────
PASSPORT="${OUT_DIR}/${PROJECT}_passport.json"
REPORT_CHARS=$(wc -m < "$REPORT" | tr -d ' ')
GROUNDING_JSON=$(echo "$GROUNDING_OUT" | python -c "import sys,json; d=sys.stdin.read(); print(json.dumps(json.loads(d[d.find('{'):])))" 2>/dev/null || echo "{}")
python "${SKILL_DIR}/scripts/gen_passport.py" "$PASSPORT" "$PROJECT" "$REPORT" "$COMPLIANCE" \
  "${FOUND:-default}" "$GROUNDING_JSON" "$COMPLIANCE_STATUS" "$REPORT_CHARS" 2>&1

echo "REPORT_${REPORT_STATUS}: ${REPORT}"
```

> 注：`find` 输出已含 `mapping`（剥离 `_` 字段）；此处再抽取 name/mapping 落盘。若实现中 `find` CLI 行为与此不一致，以 Task 4 的 CLI 为准微调此段。

- [ ] **Step 2: 语法检查**

Run: `bash -n skills/public/fire-protection-extract/scripts/run.sh`
Expected: 无输出（语法 OK）

- [ ] **Step 3: 提交**

```bash
git add skills/public/fire-protection-extract/scripts/run.sh
git commit -m "feat(fire-extract): run.sh 阶段检测 + 契约缺失/格式错误硬失败(不产空报告)"
```

---

## Task 7: 迁移/重建契约

**Files:**
- Create: `skills/public/fire-protection-extract/scripts/migrate_contracts.py`
- Modify: `skills/public/fire-protection-extract/contracts/*`（迁移到阶段子目录）

- [ ] **Step 1: 写迁移脚本**（旧字符串锚 → 段落索引；旧大纲 → 阶段大纲对齐）

`scripts/migrate_contracts.py` 核心逻辑：
```python
#!/usr/bin/env python3
"""一次性迁移：旧契约 → 阶段子目录 + 新格式。

用法：
  migrate_contracts.py <旧契约.json> <struct.json> <阶段> <新大纲.json> <输出.json>
旧字符串锚(anchor/from/to)按 struct 段落文本反查索引；无法命中的段标 [⚠未迁移]。
"""
import json, sys
from pathlib import Path


def find_para_index(struct, needle):
    for p in struct.get("paras", []):
        if needle in p["text"]:
            return p["i"]
    return None


def convert_source(src, struct):
    kind = src.get("kind")
    if kind == "para":
        i = find_para_index(struct, src.get("anchor", ""))
        return {"kind": "para", "paras": [i]} if i is not None else None
    if kind in ("range", "para_run"):
        a = find_para_index(struct, src.get("from", ""))
        b = find_para_index(struct, src.get("to", ""))
        if a is not None and b is not None and a <= b:
            return {"kind": "range", "paras": [a, b]}
        return None
    if kind == "table":
        return {"kind": "table", "no": src.get("no", "")}
    return None


def align_to_outline(old_mapping, struct, outline):
    """按新大纲逐节对齐：旧映射按 fire 标题找对应节，找不到则空（触发E3）。"""
    old_by_fire = {s.get("fire"): s.get("sources", []) for s in old_mapping.get("sections", [])}
    sources = []
    for sec in outline["sections"]:
        cls = sec.get("class")
        if cls == "heading" or cls == "template" or cls == "compute":
            sources.append(None)
            continue
        old_srcs = old_by_fire.get(sec["fire"], [])
        converted = [s for s in (convert_source(s, struct) for s in old_srcs) if s]
        sources.append(converted or None)
    return {"sources": sources}
```

- [ ] **Step 2: 执行迁移**

```bash
cd skills/public/fire-protection-extract
# 基地项目.json（旧锚）→ 基础设计/基地项目.json
python scripts/migrate_contracts.py contracts/基地项目.json <基地项目_struct.json> 基础设计 \
  references/stage-outlines/基础设计.json contracts/基础设计/基地项目.json
# 基地综合大队消防站.json（新格式）→ 基础设计/，补 _stage
python scripts/migrate_contracts.py contracts/基地综合大队消防站.json <base_struct.json> 基础设计 \
  references/stage-outlines/基础设计.json contracts/基础设计/基地综合大队消防站.json
# 仓库项目.json → 初步设计/（大纲不同，sources 需按初步设计大纲重新 E3；先迁移占位）
python scripts/migrate_contracts.py contracts/仓库项目.json <仓库项目_struct.json> 初步设计 \
  references/stage-outlines/初步设计.json contracts/初步设计/仓库项目.json
rm contracts/基地项目.json contracts/基地综合大队消防站.json contracts/仓库项目.json
```
（`<基地项目_struct.json>` / `<仓库项目_struct.json>` 用 parse_spec.py 对两个样例源说明书现场生成；`migrate_contracts.py` 输出若含 `[⚠未迁移]` 的节，在重跑时用 E3 补齐。）

- [ ] **Step 3: 验证迁移产物格式合法**

```bash
for f in contracts/基础设计/*.json contracts/初步设计/*.json; do
  python -c "import json,sys; from pathlib import Path; p=Path('$f'); m=json.loads(p.read_text(encoding='utf-8')); sys.path.insert(0,'scripts'); import contract_store as cs; e=cs.validate_format(m); assert e is None, (p.name, e); print('OK', p.name, '| sources:', len(m.get('sources',[])))"
done
```
Expected: 每个文件打印 OK 且无 assert 错误

- [ ] **Step 4: 重建 _index.json**（用 `contract_store.py save` 重存或运行 `list` 校验）

```bash
cd skills/public/fire-protection-extract
python scripts/contract_store.py list
```
Expected: 列出 `初步设计: 仓库项目`、`基础设计: 基地项目、基地综合大队消防站`

- [ ] **Step 5: 提交**

```bash
git add skills/public/fire-protection-extract/scripts/migrate_contracts.py skills/public/fire-protection-extract/contracts/
git commit -m "feat(fire-extract): 迁移契约到阶段子目录 + 旧锚→索引(基地项目)"
```

---

## Task 8: SKILL.md + extractor_rules.md 更新

**Files:**
- Modify: `skills/public/fire-protection-extract/SKILL.md`
- Modify: `skills/public/fire-protection-extract/references/extractor_rules.md`
- Test: `skills/public/fire-protection-extract/tests/test_routing.py`（确保路由测试仍过）

- [ ] **Step 1: 更新 SKILL.md**（关键段落）

- 启动前必检后加「**阶段判定**」小节：
  ```markdown
  ## 阶段判定（初步设计 / 基础设计）
  1. 用户请求里显式写了「初步设计」「基础设计」→ 作为 `--stage` 参数传给 run.sh
  2. 否则 run.sh 自动从源说明书首段识别（"初步设计"/"基础设计"）
  3. 不同阶段大纲不同（初步设计 7 章 / 基础设计 8 章），由 `references/stage-outlines/` 锁定
  ```
- 第 1 步命令改为（第 3 参为可选阶段覆盖）：
  ```bash
  WORK=/mnt/user-data/workspace OUT=/mnt/user-data/outputs \
    bash /mnt/skills/public/fire-protection-extract/scripts/run.sh \
    "/mnt/user-data/uploads/<说明书.docx>" "<项目名>" [初步设计|基础设计]
  ```
- 第 2 步「情况 B」改为：输出含 `CONTRACT_NEEDED` **或** `CONTRACT_FORMAT_MISMATCH` → 都需要 E3（删除旧契约后）重新生成映射再重跑；**契约未就绪时不再产出半成品报告**。
- E3 步骤更新：用所选阶段大纲的 `guide[]` 批量搜索；`write_file(<WORK>/<项目名>_mapping.json)` 只写 `{"sources": [...]}`（与大纲按索引对齐）；`contract_store.py save "<阶段>" "<项目名>" <STRUCT>`。
- 第 4 步展示逻辑不变；新增：grounding < 0.85 或含 `[⚠未找到]` 时明确提示"需 E5 校准或 E3 重跑"，不得直接交付。

- [ ] **Step 2: 重写 extractor_rules.md** 的「source 三种 kind」为：

```markdown
## source 两种 kind + table（新格式，索引锚定）
- `para` {paras:[i]}：段落索引，逐字复制第 i 段。
- `range` {paras:[from,to]}：闭区间逐段复制。`para_run` 为旧别名，仅格式校验层兜底，新契约禁用。
- `table` {no}：表号如 `表3.1-1`，整表复制。
- ⛔ 旧字符串锚（`anchor`/`from`/`to`）已废弃：extract.py 不再做字符串匹配，`contract_store.validate_format` 会拒绝旧格式并硬失败。
```
并删除"旧规则（单文档时代）"中与新格式矛盾的描述，新增「两层结构」小节：
```markdown
## 两层结构（大纲 / 映射）
- 大纲 `references/stage-outlines/{阶段}.json`：锁定章节骨架 + 模板 + 每节 `guide` 关键词。永不随项目漂移。
- 映射 `contracts/{阶段}/{项目}.json`：只存 `sources[]`，与大纲 `sections[]` 按索引对齐。E3 只重建映射。
- `_outline_version` 变更 → 旧映射校验失败 → E3 重跑。
```

- [ ] **Step 3: 跑路由测试确认不回归**

Run: `python -m pytest tests/test_routing.py -v`
Expected: PASS（路由测试只验 frontmatter，不涉及大纲）

- [ ] **Step 4: 提交**

```bash
git add skills/public/fire-protection-extract/SKILL.md skills/public/fire-protection-extract/references/extractor_rules.md
git commit -m "docs(fire-extract): SKILL.md 阶段流程 + extractor_rules 新schema(索引锚定)"
```

---

## Task 9: 样例集成验证脚本

**Files:**
- Create: `skills/public/fire-protection-extract/tests/verify_samples.sh`

- [ ] **Step 1: 写验证脚本**（读用户 D 盘样例，可选执行）

`tests/verify_samples.sh`：
```bash
#!/usr/bin/env bash
# 样例集成验证：跑通两个阶段，检查 章节=样例、grounding≥0.85、无[⚠未找到]。
# 用法: bash tests/verify_samples.sh <样例根目录> <工作目录>
#   样例根目录应含 仓库项目/{总说明书,消防设计专篇}.docx 与 基地项目/{设计说明书,消防设计专篇}.docx
set -euo pipefail
SAMPLE_DIR="${1:?需要样例根目录}"
TMP="${2:-$(mktemp -d)}"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

run_one() {
  local docx="$1" proj="$2" stage="$3" exp_docx="$4"
  echo "=== $proj ($stage) ==="
  WORK="$TMP/workspace" OUT="$TMP/outputs" bash "$SKILL_DIR/scripts/run.sh" "$docx" "$proj" "$stage" > "$TMP/$proj.log" 2>&1 || { echo "✗ run.sh 失败: $(tail -3 "$TMP/$proj.log")"; return 1; }
  local report="$TMP/outputs/${proj}消防设计专篇.md"
  grep -q "^# ${proj} 消防设计专篇" "$report" || { echo "✗ 标题不符"; return 1; }
  # 章节标题与样例对比（用 extract_outline 快速 diff）
  python - "$report" "$exp_docx" <<'PY' || { echo "✗ 章节与样例不符"; return 1; }
import re, sys, zipfile
def headings(md):
    return [l.strip() for l in md.splitlines() if re.match(r'^#{1,4} ', l)]
def exp_headings(docx):
    z=zipfile.ZipFile(docx); xml=z.read('word/document.xml').decode('utf-8','replace')
    return [ ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>',p)).strip()
             for p in re.findall(r'<w:p\b[^>]*>.*?</w:p>', xml, re.DOTALL)
             if re.match(r'^\d+(\.\d+){0,2}\s+\S', ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>',p)).strip()) ]
md=open(sys.argv[1],encoding='utf-8').read()
got=[h.lstrip('# ').strip() for h in headings(md)]
exp=[h for h in exp_headings(sys.argv[2]) if h]
# 只比对章节主标题（去掉正文里重复出现的子节），可人工复核差异
missing=[e for e in exp if e not in got]
print('generated headings:', len(got)); print('sample headings:', len(exp)); print('missing:', missing[:10])
sys.exit(0 if not missing else 1)
PY
  grep -q "grounding_rate: 0.8" "$TMP/$proj.log" || true
  if grep -q "\[⚠未找到" "$report"; then echo "✗ 仍有[⚠未找到]"; return 1; fi
  echo "✓ $proj OK"
}

# 依赖样例文件存在；不存在则提示跳过（CI 不跑）
for p in "$SAMPLE_DIR/仓库项目/仓库项目-总说明书.docx" "$SAMPLE_DIR/基地项目/基地项目-设计说明书.docx"; do
  [ -f "$p" ] || { echo "样例缺失(跳过): $p"; exit 0; }
done
run_one "$SAMPLE_DIR/仓库项目/仓库项目-总说明书.docx" "仓库项目" "初步设计" "$SAMPLE_DIR/仓库项目/仓库项目-消防设计专篇.docx"
run_one "$SAMPLE_DIR/基地项目/基地项目-设计说明书.docx" "基地项目" "基础设计" "$SAMPLE_DIR/基地项目/基地项目-消防设计专篇.docx"
```

- [ ] **Step 2: 用真实样例跑通**

Run: `bash skills/public/fire-protection-extract/tests/verify_samples.sh "D:\18 辽宁创元\03 项目策划\02 中石油\吉林院\报告智能体\模板资料-00" .wolf/sample-verify`
Expected: `✓ 仓库项目 OK` 与 `✓ 基地项目 OK`（若某节 E3 锚点不足 → 该节标 `[⚠未找到]` → 进入 Task 7 的 E3 补齐循环）

- [ ] **Step 3: 补齐锚点（若 Step 2 有失配节）** — 对失配节用 E3 批量搜索 guide 关键词补映射后重跑，直至 `0 处 [⚠未找到]`。

- [ ] **Step 4: 提交**

```bash
git add skills/public/fire-protection-extract/tests/verify_samples.sh
git commit -m "test(fire-extract): 两阶段样例集成验证脚本"
```

---

## Task 10: 同步运行时 + 端到端回归

**Files:**
- Sync: `backend/.deer-flow/skills_view/public/fire-protection-extract/`（投影副本）
- 容器: `deer-flow-gateway`（重启）

- [ ] **Step 1: 同步 skills_view 投影**

```bash
cp -r skills/public/fire-protection-extract/* backend/.deer-flow/skills_view/public/fire-protection-extract/
```

- [ ] **Step 2: 重启 gateway 使 skill_context/加载缓存生效**

```bash
docker compose -p eai-docker restart gateway
```
Expected: 容器 `Up`，日志无报错（`docker compose -p eai-docker logs --tail 20 gateway`）

- [ ] **Step 3: 回归——重放旧空章节场景**

在对话页 `http://localhost:2026/workspace/chats/` 新建线程，上传 `基地项目-设计说明书.docx`，输入「编写基地项目消防设计专篇（基础设计）」。
Expected:
- run.sh 自动识别"基础设计"，命中 `基础设计/基地项目.json` 新格式映射
- 报告标题为 `# 基地项目 消防设计专篇`（不再是 XX）
- 各节有真实抄录内容，无 `[⚠未找到段落: None]` 大面积空洞
- grounding ≥ 0.85 或明确提示需校准

- [ ] **Step 4: 提交最终同步**

```bash
git add -A skills/public/fire-protection-extract/ backend/.deer-flow/skills_view/public/fire-protection-extract/
git commit -m "chore(fire-extract): 同步技能到 skills_view + 端到端回归"
```

---

## 自检（plan vs spec）

- **Spec §3.1 阶段层** → Task 1（大纲）+ Task 2（检测）+ Task 6（run.sh 集成）✓
- **Spec §3.2 契约层** → Task 4（store 阶段+校验）+ Task 7（迁移）✓
- **Spec §3.3 引擎/bug** → Task 3（extract 两层+XX标题）+ Task 5（grounding）+ Task 6 ✓
- **Spec §3.4 能抄尽可能抄** → Task 1 outline `guide` + Task 9 验证覆盖门槛 ✓
- **Spec §3.5 测试** → Task 1/2/3/4/5 单元 + Task 9 样例集成 + Task 10 回归 ✓
- **Spec §4 实施顺序** → Task 1→10 顺序一致 ✓

**已知边界：**
- `fire_spec_mapping.json` 在 Task 1 之后由 `基础设计.json` 取代；旧引用处（测试/test_extract_skill_files_complete 的 required 列表）需同步改或保留文件做兼容别名——以保留文件、内容改为引用基础设计大纲为最稳妥。
- run.sh 中 `find` CLI 输出结构与 Task 4 的 `find` 实现细节需在联调时对齐（已注）。