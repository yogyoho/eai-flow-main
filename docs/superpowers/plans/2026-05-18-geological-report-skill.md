# Geological Report Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a SKILL.md-based geological exploration report generation skill for `skills/custom/geological-report/`, validated by TDD tests covering frontmatter correctness, structural completeness, and standards compliance.

**Architecture:** Single comprehensive SKILL.md file containing report templates (DZ/T 0033-2020 Appendix A/B/C), technical requirements (GB/T 13908-2020), resource classification tables, quality checklists, and mineral-type adaptation guides. Tests validate the file can be parsed by the existing skills system and contains all required content.

**Tech Stack:** Python 3.12+, pytest, yaml (for test parsing)

**Spec:** `docs/superpowers/specs/2026-05-18-geological-report-skill-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `skills/custom/geological-report/SKILL.md` | The skill itself — frontmatter + full instruction content |
| `backend/tests/test_geological_report_skill.py` | TDD tests: frontmatter validation, structure validation, content completeness |

---

### Task 1: Test — Frontmatter Validation

**Files:**
- Create: `backend/tests/test_geological_report_skill.py`

This task writes the test file with the first test group verifying the SKILL.md frontmatter is valid and parseable.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_geological_report_skill.py`:

```python
"""TDD tests for the geological-report SKILL.md.

Validates that the skill file:
1. Parses correctly through the existing skills parser
2. Has valid frontmatter (name, description, license, allowed-tools)
3. Contains all required content sections per the design spec
4. Includes the three report stage templates
5. Contains mineral-type adaptation guides
6. Contains resource classification and quality checklists
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from deerflow.skills.parser import parse_skill_file
from deerflow.skills.types import SkillCategory

SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"
SKILL_DIR = SKILLS_ROOT / "custom" / "geological-report"
SKILL_FILE = SKILL_DIR / "SKILL.md"


def _read_skill_content() -> str:
    """Read the SKILL.md file content; skip if not yet created."""
    if not SKILL_FILE.exists():
        pytest.skip("SKILL.md not yet created")
    return SKILL_FILE.read_text(encoding="utf-8")


def _extract_frontmatter(content: str) -> dict:
    """Extract and parse YAML frontmatter from SKILL.md content."""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


import pytest


# ---------------------------------------------------------------------------
# Group 1: Frontmatter validation
# ---------------------------------------------------------------------------


class TestFrontmatter:
    """Verify SKILL.md frontmatter is valid and parseable."""

    def test_skill_file_exists(self):
        """SKILL.md file must exist at the expected path."""
        assert SKILL_FILE.exists(), f"SKILL.md not found at {SKILL_FILE}"

    def test_skill_file_not_empty(self):
        """SKILL.md must not be empty."""
        content = _read_skill_content()
        assert len(content.strip()) > 0

    def test_has_yaml_frontmatter(self):
        """SKILL.md must start with YAML frontmatter block."""
        content = _read_skill_content()
        assert content.startswith("---\n"), "SKILL.md must start with --- frontmatter delimiter"
        # Must have closing --- on its own line
        match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
        assert match, "SKILL.md must have properly closed YAML frontmatter"

    def test_frontmatter_name(self):
        """Frontmatter must have name='geological-report'."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        assert fm.get("name") == "geological-report"

    def test_frontmatter_description_not_empty(self):
        """Frontmatter description must be non-empty."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        desc = fm.get("description", "")
        assert isinstance(desc, str) and len(desc.strip()) > 0

    def test_frontmatter_description_mentions_standards(self):
        """Description must mention key standards."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        desc = fm.get("description", "")
        assert "DZ/T 0033" in desc
        assert "GB/T 13908" in desc

    def test_frontmatter_license(self):
        """Frontmatter must specify license."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        assert fm.get("license") is not None

    def test_frontmatter_allowed_tools(self):
        """Frontmatter allowed-tools must be a list of valid tool names."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        tools = fm.get("allowed-tools")
        assert isinstance(tools, list)
        assert len(tools) > 0
        expected_tools = {"bash", "read_file", "write_file", "str_replace", "ls", "ask_clarification"}
        assert set(tools) == expected_tools

    def test_parses_via_skill_parser(self):
        """SKILL.md must parse successfully through the DeerFlow skills parser."""
        skill = parse_skill_file(SKILL_FILE, category=SkillCategory.CUSTOM)
        assert skill is not None, "parse_skill_file returned None — check frontmatter format"
        assert skill.name == "geological-report"
        assert skill.category == SkillCategory.CUSTOM
        assert skill.license is not None
        assert skill.allowed_tools is not None
        assert len(skill.allowed_tools) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestFrontmatter -v`

Expected: FAIL — `SKILL.md not found` or `SKILL.md not yet created` (file does not exist yet)

- [ ] **Step 3: Commit the failing test**

```bash
cd D:/eai/eai-flow-main
git add backend/tests/test_geological_report_skill.py
git commit -m "test: add geological report skill frontmatter validation tests (TDD red)"
```

---

### Task 2: Implement — SKILL.md Frontmatter + Overview Section

**Files:**
- Create: `skills/custom/geological-report/SKILL.md`

This task creates the SKILL.md file with valid frontmatter and the first content section (Overview & Role), enough to make the frontmatter tests pass.

- [ ] **Step 1: Create the SKILL.md with frontmatter and overview**

Create `skills/custom/geological-report/SKILL.md`:

```markdown
---
name: geological-report
description: >
  固体矿产地质勘查报告制作技能 — 基于 DZ/T 0033-2020、GB/T 13908-2020、
  GB/T 33444-2016 标准，支持普查/详查/勘探三阶段，多矿种定制，
  双模式输入（数据文件解析 + 对话引导），生成符合国家标准的 Markdown 格式报告
license: MIT
allowed-tools: ["bash", "read_file", "write_file", "str_replace", "ls", "ask_clarification"]
---

# 固体矿产地质勘查报告制作技能

## 角色与身份

你是专业的固体矿产地质勘查报告编写专家。你精通以下国家标准和行业规范：

- **DZ/T 0033-2020**《固体矿产地质勘查报告编写规范》— 报告结构、章节要求、编写规则
- **GB/T 13908-2020**《固体矿产地质勘查规范 总则》— 勘查程度、工程间距、资源量分类
- **GB/T 33444-2016**《固体矿产勘查工作规范》— 勘查工作程度、质量要求
- **DZ/T 0215-2020**《矿产地质勘查规范 煤》— 煤矿专用要求
- **DZ/T 0214-2020**《矿产地质勘查规范 铜、铅、锌、银、镍、钼》— 有色金属专用要求

### 适用范围

- 矿种：通用固体矿产（可适配煤、铜、铅、锌、银、镍、钼等）
- 勘查阶段：普查（附录A）、详查（附录B）、勘探（附录C）
- 输入方式：自动解析数据文件（Excel/CSV/PDF/Word）或对话引导
- 输出格式：Markdown 文档，可迭代修改

### 核心工具

- `bash` / `read_file`：解析上传的数据文件
- `write_file`：生成报告文件到 `/mnt/user-data/outputs/`
- `str_replace`：迭代修改报告内容
- `ask_clarification`：向用户请求缺失信息
```

- [ ] **Step 2: Run frontmatter tests to verify they pass**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestFrontmatter -v`

Expected: All 9 frontmatter tests PASS

- [ ] **Step 3: Commit**

```bash
cd D:/eai/eai-flow-main
git add skills/custom/geological-report/SKILL.md
git commit -m "feat: create geological report SKILL.md with frontmatter and overview"
```

---

### Task 3: Test — Structural Sections Completeness

**Files:**
- Modify: `backend/tests/test_geological_report_skill.py`

Add tests verifying the SKILL.md body contains all required structural sections from the design spec §2.3.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_geological_report_skill.py`:

```python
# ---------------------------------------------------------------------------
# Group 2: Structural sections
# ---------------------------------------------------------------------------


class TestStructuralSections:
    """Verify SKILL.md contains all required content sections (design spec §2.3)."""

    @pytest.fixture(autouse=True)
    def _load_content(self):
        self.content = _read_skill_content()

    def test_has_workflow_protocol_section(self):
        """Must contain workflow protocol section."""
        assert "工作流协议" in self.content or "## 工作流" in self.content

    def test_has_stage_templates_section(self):
        """Must contain report stage templates section."""
        assert "附录A" in self.content or "普查" in self.content
        assert "附录B" in self.content or "详查" in self.content
        assert "附录C" in self.content or "勘探" in self.content

    def test_has_technical_requirements_section(self):
        """Must contain technical requirements section (GB/T 13908-2020)."""
        assert "勘查类型" in self.content
        assert "工程间距" in self.content

    def test_has_resource_classification_section(self):
        """Must contain resource classification section (TD/KZ/TM/KX/ZS)."""
        for code in ["TD", "KZ", "TM", "KX", "ZS"]:
            assert code in self.content, f"Resource classification code {code} not found"

    def test_has_quality_checklist_section(self):
        """Must contain quality checklist section."""
        assert "质量校验" in self.content or "质量自检" in self.content or "质量检查" in self.content

    def test_has_mineral_adaptation_section(self):
        """Must contain mineral-type adaptation section."""
        assert "矿种适配" in self.content or "矿种" in self.content
        assert "煤" in self.content
        assert "铜" in self.content

    def test_has_output_specification_section(self):
        """Must contain output specification section."""
        assert "输出规范" in self.content or "输出格式" in self.content
        assert "/mnt/user-data/outputs" in self.content

    def test_has_dual_mode_workflow(self):
        """Must describe both auto-parse and conversational guidance modes."""
        assert "自动解析" in self.content or "解析模式" in self.content
        assert "对话引导" in self.content or "引导模式" in self.content

    def test_has_conversational_question_sequence(self):
        """Must define the information collection question sequence."""
        # Check for key fields the agent must ask about
        assert "矿种" in self.content
        assert "勘查阶段" in self.content
        assert "资源量估算" in self.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestStructuralSections -v`

Expected: FAIL — structural sections not yet written in SKILL.md

- [ ] **Step 3: Commit the failing tests**

```bash
cd D:/eai/eai-flow-main
git add backend/tests/test_geological_report_skill.py
git commit -m "test: add structural sections completeness tests (TDD red)"
```

---

### Task 4: Implement — Workflow Protocol Section

**Files:**
- Modify: `skills/custom/geological-report/SKILL.md`

Append the workflow protocol section (design spec §3) to SKILL.md. This section is the largest content block.

- [ ] **Step 1: Append workflow protocol to SKILL.md**

Append the following after the existing `### 核心工具` section in `skills/custom/geological-report/SKILL.md`:

```markdown

## 工作流协议

### 入口判定

技能激活后，首先判断输入模式：

1. **自动解析模式**：如果用户上传了数据文件（Excel、CSV、PDF、Word），使用 `read_file` 和 `bash`（Python 脚本）解析文件，提取关键信息后呈现给用户确认。
2. **对话引导模式**：如果没有数据文件，通过对话逐步收集信息。

### 自动解析模式

1. 使用 `read_file` 读取上传文件内容
2. 使用 `bash` 执行 Python 脚本解析结构化数据（Excel/CSV 用 pandas，PDF 用 pymupdf）
3. 提取以下关键信息：
   - 勘查区位置与范围
   - 矿种
   - 勘查阶段
   - 矿体参数（编号、形态、产状、规模、品位）
   - 样品分析数据
   - 工程布置数据
4. 将提取结果结构化呈现给用户确认
5. 确认后进入报告生成阶段

### 对话引导模式

按以下优先级依次收集信息（用户已有信息可跳过）：

| 序号 | 信息类别 | 关键字段 |
|------|----------|----------|
| 1 | 矿种类型 | 煤/铜/铅/锌/银/镍/钼/其他 |
| 2 | 勘查阶段 | 普查/详查/勘探 |
| 3 | 项目基本信息 | 项目名称、地理位置、勘查面积、勘查单位、工作期限 |
| 4 | 区域地质概况 | 地层、构造、岩浆岩、变质岩 |
| 5 | 矿区地质 | 地层、构造、岩浆岩、蚀变带、地球化学异常 |
| 6 | 矿体描述 | 矿体编号、形态、产状、规模（走向/倾向/延深）、厚度、品位 |
| 7 | 勘查工作 | 钻探/槽探/坑探工程量、工程质量评述 |
| 8 | 样品与化验 | 采样方法、分析项目、内检外检结果 |
| 9 | 开采技术条件 | 水文地质、工程地质、环境地质（详查/勘探阶段） |
| 10 | 资源量估算 | 工业指标、估算方法、块段划分、估算结果 |

每次只问一个类别的问题。使用 `ask_clarification` 工具请求缺失信息。

### 报告生成流程

1. 根据勘查阶段选择对应模板（附录A/B/C）
2. 逐章生成 Markdown 内容
3. 使用 `write_file` 写入 `/mnt/user-data/outputs/{项目名称}-{阶段}-地质勘查报告.md`
4. 每完成一个主要章节向用户汇报进度

### 迭代修改

用户指出需要修改的部分时：
1. 定位需要修改的章节
2. 使用 `str_replace` 修改内容
3. 检查修改是否影响其他章节的数据一致性
4. 更新文件
```

- [ ] **Step 2: Run structural tests to check progress**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestStructuralSections::test_has_dual_mode_workflow tests/test_geological_report_skill.py::TestStructuralSections::test_has_conversational_question_sequence tests/test_geological_report_skill.py::TestStructuralSections::test_has_output_specification_section -v`

Expected: PASS for these three tests

- [ ] **Step 3: Commit**

```bash
cd D:/eai/eai-flow-main
git add skills/custom/geological-report/SKILL.md
git commit -m "feat: add workflow protocol section to geological report skill"
```

---

### Task 5: Implement — Stage Report Templates

**Files:**
- Modify: `skills/custom/geological-report/SKILL.md`

Append the three stage report templates (design spec §4) — the core content of the skill.

- [ ] **Step 1: Append stage report templates to SKILL.md**

Append the following after the workflow protocol section:

```markdown

## 阶段报告模板

### 附录A：普查阶段报告目录（DZ/T 0033-2020）

```
第一章 绪论
  1.1 目的任务
  1.2 位置交通
  1.3 自然地理与经济概况
  1.4 以往地质工作评述

第二章 区域地质
  2.1 地层
  2.2 构造
  2.3 岩浆岩
  2.4 变质岩

第三章 矿区地质
  3.1 地层
  3.2 构造
  3.3 岩浆岩
  3.4 围岩蚀变
  3.5 地球化学特征

第四章 矿体
  4.1 矿体特征
  4.2 矿石质量
  4.3 矿床成因类型及找矿标志

第五章 资源量估算
  5.1 工业指标
  5.2 估算方法及参数确定
  5.3 资源量估算结果

第六章 结论与建议
```

**普查阶段写作要点**：
- 绪论：明确勘查目的、工作范围，简述以往工作成果
- 区域地质：概略描述区域地质背景，侧重与成矿有关的地质因素
- 矿区地质：初步查明矿区地质特征，发现并圈定矿化带
- 矿体：初步了解矿体数量、规模、形态、产状、品位
- 资源量估算：以推断资源量（TD）为主，使用几何法或地质统计学法

### 附录B：详查阶段报告目录（DZ/T 0033-2020）

```
第一章 绪论
  1.1 目的任务
  1.2 位置交通
  1.3 自然地理与经济概况
  1.4 以往地质工作评述
  1.5 勘查工作依据
  1.6 勘查许可证范围

第二章 区域地质
  2.1 地层
  2.2 构造
  2.3 岩浆岩
  2.4 变质岩

第三章 矿区地质
  3.1 地层
  3.2 构造
  3.3 岩浆岩
  3.4 围岩蚀变
  3.5 地球物理特征
  3.6 地球化学特征

第四章 矿体
  4.1 矿体特征（含矿体控制程度）
  4.2 矿石质量
  4.3 矿石类型
  4.4 矿床成因

第五章 矿石加工选冶技术性能

第六章 矿床开采技术条件
  6.1 水文地质
  6.2 工程地质
  6.3 环境地质

第七章 勘查工作及其质量评述
  7.1 勘查方法
  7.2 勘查工程
  7.3 地质编录
  7.4 采样与化验

第八章 资源量估算
  8.1 工业指标
  8.2 资源量分类
  8.3 估算方法
  8.4 参数确定
  8.5 块段划分
  8.6 估算结果
  8.7 资源量可靠性评述

第九章 结论与建议
```

**详查阶段写作要点**：
- 绪论：增加勘查许可证信息和工作依据
- 矿区地质：增加地球物理特征描述
- 矿体：增加控制程度分析和矿石类型划分
- 新增矿石加工选冶章节：初步评价矿石可选性
- 新增开采技术条件：水文地质、工程地质、环境地质
- 新增勘查工作质量评述：方法、工程、编录、采样
- 资源量估算：控制资源量（KZ）+ 推断资源量（TD）

### 附录C：勘探阶段报告目录（DZ/T 0033-2020）

在详查目录基础上增强：

```
第四章 矿体
  4.1 矿体特征（含详细的矿体控制程度分析和矿体连通性分析）

第五章 矿石加工选冶试验
  （含详细试验流程和可选方案对比）

第六章 矿床开采技术条件
  （更详细的水文地质参数和工程地质评价）

第八章 资源储量估算
  （使用"储量"术语，需包含探明+控制资源量）
  8.1 工业指标确定依据
  8.2 资源储量分类
  8.3 估算方法选择及依据
  8.4 各参数确定详述
  8.5 块段划分及单工程圈定
  8.6 估算结果（分类汇总表）
  8.7 资源储量可靠性评述
  8.8 与前期成果对比分析

第十章 矿床经济评价概要
```

**勘探阶段写作要点**：
- 矿体：详细的控制程度分析和连通性论证
- 加工选冶：详细试验数据，推荐工艺流程
- 资源储量：探明资源量（TM）+ 控制资源量（KZ）+ 推断资源量（TD），估算结果需分类汇总
- 新增经济评价概要章节
```

- [ ] **Step 2: Run stage template tests**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestStructuralSections::test_has_stage_templates_section -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd D:/eai/eai-flow-main
git add skills/custom/geological-report/SKILL.md
git commit -m "feat: add three-stage report templates (普查/详查/勘探) to skill"
```

---

### Task 6: Implement — Technical Requirements & Resource Classification

**Files:**
- Modify: `skills/custom/geological-report/SKILL.md`

Append technical requirements tables (design spec §5) and resource classification.

- [ ] **Step 1: Append technical requirements and classification**

Append the following:

```markdown

## 技术要求精要（GB/T 13908-2020）

### 勘查类型划分

| 类型 | 代号 | 特征 |
|------|------|------|
| 简单 | Ⅰ | 矿体规模大、形态简单、品位分布均匀、构造简单 |
| 中等 | Ⅱ | 矿体规模中等、形态较简单、品位较均匀 |
| 复杂 | Ⅲ | 矿体规模小、形态复杂、品位变化大、构造复杂 |
| 过渡类型 | Ⅰ-Ⅱ | 兼具简单和中等类型特征 |
| 过渡类型 | Ⅱ-Ⅲ | 兼具中等和复杂类型特征 |

### 工程间距参考

工程间距根据勘查类型和勘查阶段确定：

- **普查阶段**：稀疏工程控制，间距较宽松
- **详查阶段**：按勘查类型确定系统工程间距
- **勘探阶段**：加密工程控制，间距最密

具体数值依据矿种规范（如 DZ/T 0214、DZ/T 0215）确定，生成报告时需引导用户确认或参照规范。

### 各阶段勘查程度要求

**普查阶段**：
- 地质填图 1:25000～1:5000
- 初步查明矿体规模、形态、产状
- 推断资源量为主
- 矿种工业指标参考一般工业指标

**详查阶段**：
- 地质填图 1:10000～1:2000
- 基本查明矿体特征、矿石质量
- 控制资源量+推断资源量
- 矿石加工选冶技术性能初步评价

**勘探阶段**：
- 地质填图 1:5000～1:500
- 详细查明矿体形态、产状、品位变化
- 探明资源量+控制资源量+推断资源量
- 可行性评价

## 资源量分类体系

按 GB/T 17766 和 GB/T 13908 规定：

| 分类 | 代号 | 全称 | 含义 |
|------|------|------|------|
| 探明资源量 | TM | 探明的 | 工程控制程度最高，矿体形态、产状、品位已详细查明 |
| 控制资源量 | KZ | 控制的 | 工程控制程度较高，矿体主要特征已基本查明 |
| 推断资源量 | TD | 推定的 | 工程控制程度较低，矿体总体特征初步查明 |
| 可信储量 | KX | 可信的 | 经过预可行性或可行性研究的控制资源量/探明资源量 |
| 证实储量 | ZS | 证实的 | 经过可行性研究的探明资源量 |

**使用规则**：
- 普查阶段主要估算 TD
- 详查阶段估算 KZ + TD
- 勘探阶段估算 TM + KZ + TD，储量报告还需 KX 和 ZS
- 在报告中统一使用代号，首次出现时注明全称
```

- [ ] **Step 2: Run technical requirements tests**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestStructuralSections::test_has_technical_requirements_section tests/test_geological_report_skill.py::TestStructuralSections::test_has_resource_classification_section -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd D:/eai/eai-flow-main
git add skills/custom/geological-report/SKILL.md
git commit -m "feat: add technical requirements and resource classification tables"
```

---

### Task 7: Implement — Quality Checklist, Mineral Adaptation, Output Spec

**Files:**
- Modify: `skills/custom/geological-report/SKILL.md`

Append the remaining three sections (design spec §6, §7, §8) to complete the skill content.

- [ ] **Step 1: Append quality checklist, mineral adaptation, and output specification**

Append the following:

```markdown

## 质量校验清单

报告生成完成后，按以下清单逐项自检：

### 完整性检查

- [ ] 当前阶段模板的所有必填章节都有内容
- [ ] 每个章节内的必填子项都已覆盖
- [ ] 绪论包含项目名称、位置、勘查单位
- [ ] 资源量估算章节包含工业指标、方法、结果

### 数据一致性检查

- [ ] 矿体参数（走向、倾向、倾角、厚度、品位）在各章节引用时数值一致
- [ ] 工程量统计数字与正文描述吻合
- [ ] 资源量估算表与正文数据对应
- [ ] 同一概念使用统一术语，不混用不同名称

### 标准符合性检查

- [ ] 资源量分类使用正确代号（TD/KZ/TM/KX/ZS）
- [ ] 工程间距符合勘查类型对应要求
- [ ] 采样质量评述包含必要的质量指标（内检合格率、外检偏差等）
- [ ] 章节结构符合 DZ/T 0033-2020 对应阶段要求
- [ ] 勘查程度描述符合 GB/T 13908-2020 对应阶段要求

## 矿种适配引导

当用户指定矿种时，按以下指引调整报告内容：

### 煤矿（参照 DZ/T 0215-2020）

**工业指标差异**：
- 最低可采厚度
- 最高灰分（Ad）
- 最低发热量（Qnet,d）
- 最高硫分（St,d）

**特殊章节要求**：
- 煤层对比与可靠性分析（对比标志层、测井曲线对比）
- 煤质评价：工业分析（水分、灰分、挥发分、固定碳）、元素分析、工艺性能（粘结性、结焦性等）
- 煤炭资源量分类使用煤炭专用标准

**注意**：DZ/T 0215-2020 已移除泥炭相关内容，不生成泥炭评价章节。

### 铜、铅、锌、银、镍、钼（参照 DZ/T 0214-2020）

**工业指标差异**：
- 边界品位（铜 Cu ≥ 0.2～0.3%，锌 Zn ≥ 0.5～1.0%，铅 Pb ≥ 0.3～0.5%）
- 最低工业品位
- 最小可采厚度
- 夹石剔除厚度

**基本分析项目**：
- Cu 矿：Cu、Ag、Au、S、As
- Pb-Zn 矿：Pb、Zn、Ag、S、Cd
- Ag 矿：Ag、Au、Pb、Zn、Cu
- Ni 矿：Ni、Cu、Co、S
- Mo 矿：Mo、S、Cu、W

**特殊要求**：
- 伴生元素综合评价（所有有益伴生组分须单独圈定、估算）
- 绿色勘查要求（2020版新增）：勘查活动中注重生态环保

### 其他矿种

- 引导用户提供该矿种的具体工业指标
- 使用 GB/T 13908 通用框架生成报告
- 提示用户参照对应矿种专用规范

## 输出规范

### 文件格式

- 格式：Markdown（.md）
- 编码：UTF-8
- 命名：`{项目名称}-{阶段}-地质勘查报告.md`
  - 示例：`张家沟-勘探-地质勘查报告.md`
- 存储路径：`/mnt/user-data/outputs/`

### 章节编号

- 一级章节：`第一章`、`第二章`...
- 二级章节：`1.1`、`1.2`...
- 三级章节：`1.1.1`、`1.1.2`...

### 表格格式

Markdown 表格，资源量估算结果表使用标准格式：

```markdown
| 块段编号 | 矿体编号 | 面积(m²) | 平均厚度(m) | 体积(m³) | 矿石量(t) | 平均品位 | 金属量(t) | 资源量分类 |
|----------|----------|----------|-------------|----------|-----------|----------|-----------|-----------|
```

### 图表描述

对于无法直接生成的图表（勘探线剖面图、矿体投影图等），生成文字描述块：

```markdown
> **[图表: {图表名称}]**
> - 类型: {剖面图/投影图/等值线图等}
> - 比例尺: {1:XXXX}
> - 内容描述: {详细描述应展示的内容}
> - 数据来源: {引用数据出处}
```
```

- [ ] **Step 2: Run ALL structural tests**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestStructuralSections -v`

Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
cd D:/eai/eai-flow-main
git add skills/custom/geological-report/SKILL.md
git commit -m "feat: add quality checklist, mineral adaptation, and output specification"
```

---

### Task 8: Test — Content Depth Validation

**Files:**
- Modify: `backend/tests/test_geological_report_skill.py`

Add deeper content validation tests ensuring specific template details and standards references are present.

- [ ] **Step 1: Write content depth tests**

Append to `backend/tests/test_geological_report_skill.py`:

```python
# ---------------------------------------------------------------------------
# Group 3: Content depth validation
# ---------------------------------------------------------------------------


class TestContentDepth:
    """Verify specific content details from the design spec are present."""

    @pytest.fixture(autouse=True)
    def _load_content(self):
        self.content = _read_skill_content()

    # --- Census template completeness ---

    def test_census_template_has_six_chapters(self):
        """Census (附录A) template must have chapters 绪论 through 结论."""
        # Find the census template section
        assert "第一章 绪论" in self.content
        assert "结论与建议" in self.content

    def test_census_template_has_resource_estimation(self):
        """Census template must include resource estimation chapter."""
        assert "资源量估算" in self.content
        assert "工业指标" in self.content
        assert "估算方法" in self.content

    # --- Detailed template completeness ---

    def test_detailed_template_has_mining_conditions(self):
        """Detailed (附录B) template must include mining conditions."""
        assert "水文地质" in self.content
        assert "工程地质" in self.content
        assert "环境地质" in self.content

    def test_detailed_template_has_quality_assessment(self):
        """Detailed template must include exploration quality assessment."""
        assert "勘查工作" in self.content
        assert "质量评述" in self.content

    # --- Exploration template completeness ---

    def test_exploration_template_has_economic_evaluation(self):
        """Exploration (附录C) template must include economic evaluation."""
        assert "经济评价" in self.content

    # --- Resource classification completeness ---

    def test_resource_classification_has_all_codes_defined(self):
        """Each resource classification code must have its full name defined."""
        assert "TM" in self.content
        assert "探明" in self.content or "探明的" in self.content
        assert "KZ" in self.content
        assert "控制" in self.content or "控制的" in self.content
        assert "TD" in self.content
        assert "推断" in self.content or "推定的" in self.content

    # --- Mineral adaptation completeness ---

    def test_coal_adaptation_has_industrial_indicators(self):
        """Coal adaptation must list key industrial indicators."""
        assert "最低可采厚度" in self.content
        assert "灰分" in self.content
        assert "发热量" in self.content

    def test_copper_adaptation_has_analysis_items(self):
        """Copper adaptation must list analysis items."""
        assert "Cu" in self.content
        assert "Ag" in self.content or "Au" in self.content

    # --- Standards references ---

    def test_references_dz0033(self):
        """Must reference DZ/T 0033-2020."""
        assert "DZ/T 0033" in self.content
        assert "2020" in self.content

    def test_references_gb13908(self):
        """Must reference GB/T 13908-2020."""
        assert "GB/T 13908" in self.content

    def test_references_gb33444(self):
        """Must reference GB/T 33444-2016."""
        assert "GB/T 33444" in self.content or "33444" in self.content

    # --- Quality checklist items ---

    def test_quality_checklist_has_completeness_items(self):
        """Quality checklist must cover completeness checks."""
        assert "完整性" in self.content

    def test_quality_checklist_has_consistency_items(self):
        """Quality checklist must cover data consistency checks."""
        assert "一致性" in self.content

    # --- Output specification ---

    def test_output_spec_has_markdown_format(self):
        """Output spec must specify Markdown format."""
        assert "Markdown" in self.content

    def test_output_spec_has_chapter_numbering(self):
        """Output spec must define chapter numbering scheme."""
        assert "第一章" in self.content
        assert "1.1" in self.content
```

- [ ] **Step 2: Run content depth tests**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestContentDepth -v`

Expected: PASS (all content was added in Tasks 4-7)

- [ ] **Step 3: Commit**

```bash
cd D:/eai/eai-flow-main
git add backend/tests/test_geological_report_skill.py
git commit -m "test: add content depth validation tests for geological report skill"
```

---

### Task 9: Test — Skill Loading Integration

**Files:**
- Modify: `backend/tests/test_geological_report_skill.py`

Add integration tests verifying the skill loads correctly through the existing DeerFlow skill storage system.

- [ ] **Step 1: Write integration tests**

Append to `backend/tests/test_geological_report_skill.py`:

```python
# ---------------------------------------------------------------------------
# Group 4: Skill loading integration
# ---------------------------------------------------------------------------


class TestSkillLoadingIntegration:
    """Verify the skill integrates with the DeerFlow skills system."""

    def test_skill_loads_into_storage(self, tmp_path: Path):
        """Skill should be discoverable by LocalSkillStorage when placed in custom/."""
        # Create a temporary skills root with the geological-report skill
        skill_dir = tmp_path / "custom" / "geological-report"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            SKILL_FILE.read_text(encoding="utf-8"), encoding="utf-8"
        )

        from deerflow.skills.storage import get_or_new_skill_storage

        storage = get_or_new_skill_storage(skills_path=tmp_path)
        skills = storage.load_skills(enabled_only=False)
        geo_skill = next((s for s in skills if s.name == "geological-report"), None)
        assert geo_skill is not None
        assert geo_skill.category == SkillCategory.CUSTOM

    def test_skill_container_path_correct(self, tmp_path: Path):
        """Skill container path must point to the correct custom location."""
        skill_dir = tmp_path / "custom" / "geological-report"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            SKILL_FILE.read_text(encoding="utf-8"), encoding="utf-8"
        )

        from deerflow.skills.storage import get_or_new_skill_storage

        storage = get_or_new_skill_storage(skills_path=tmp_path)
        skills = storage.load_skills(enabled_only=False)
        geo_skill = next(s for s in skills if s.name == "geological-report")
        assert geo_skill.get_container_file_path() == "/mnt/skills/custom/geological-report/SKILL.md"

    def test_skill_content_not_truncated(self):
        """Skill body content must not be empty (real content exists beyond frontmatter)."""
        content = _read_skill_content()
        # Remove frontmatter
        body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
        assert len(body.strip()) > 500, "SKILL.md body seems too short — content may be missing"
```

- [ ] **Step 2: Run integration tests**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py::TestSkillLoadingIntegration -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd D:/eai/eai-flow-main
git add backend/tests/test_geological_report_skill.py
git commit -m "test: add skill loading integration tests"
```

---

### Task 10: Final Verification — Run All Tests

**Files:** None (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/test_geological_report_skill.py -v`

Expected: ALL tests PASS (4 test groups, ~30 test cases)

- [ ] **Step 2: Run the full backend test suite to check for regressions**

Run: `cd D:/eai/eai-flow-main/backend && PYTHONPATH=. python -m pytest tests/ -v --timeout=120`

Expected: All existing tests continue to pass (no regressions)

- [ ] **Step 3: Final commit with any cleanup**

If any minor fixes were needed during verification:

```bash
cd D:/eai/eai-flow-main
git add -A
git commit -m "chore: final cleanup for geological report skill"
```

---

## Self-Review

**1. Spec coverage check:**

| Spec Section | Task |
|---|---|
| §1 Overview | Task 2 (overview in SKILL.md) |
| §2 Structure (location, frontmatter, sections) | Tasks 1-2 |
| §3 Workflow protocol | Task 4 |
| §4 Stage templates (A/B/C) | Task 5 |
| §5 Technical requirements | Task 6 |
| §5 Resource classification | Task 6 |
| §6 Mineral adaptation | Task 7 |
| §7 Output specification | Task 7 |
| §8 Implementation scope | Tasks 2-7 cover all "included" items |

**2. Placeholder scan:** No TBD, TODO, "implement later", "add appropriate" found. All steps contain complete code.

**3. Type consistency:** `parse_skill_file` returns `Skill | None` — tests check `skill is not None` before accessing attributes. `SkillCategory.CUSTOM` used consistently. `get_or_new_skill_storage(skills_path=)` parameter matches the constructor signature in `local_skill_storage.py`.
