# 抽取与溯源规则

## 四分类（每 fire 小节必标 class）
- `verbatim` 抄：从说明书逐字摘。source 必填。
- `template` 填：固定文本（标准清单/法规），用大纲的 templates[name]。
- `compute` 算：说明书无此数据（如消防设施专项投资概算），输出 `[需计算]`，绝不伪造。
- `heading` 标记：纯结构章节标题（如"1 设计依据及采用的标准"），无 content/sources，仅输出标题作为分组容器。

## source 类型（新格式：索引锚定）

两层结构：
- **大纲** `references/stage-outlines/{阶段}.json`：锁定章节骨架（fire 标题/class/template/guide 关键词）。永不随项目漂移。
- **映射** `contracts/{阶段}/{项目}.json`：只存 `sources[]`，与大纲 `sections[]` 按索引 1:1 对齐。E3 只重建映射。

verbatim 节的 source 三种 kind（全部索引锚定，不做字符串匹配）：
- `para` `{"kind":"para","paras":[i]}`：逐字复制第 i 段。
- `range` `{"kind":"range","paras":[a,b]}`：闭区间逐段复制（a≤b）。`para_run` 是旧别名，extract.py 会兜底转换为 range，新契约禁用。
- `table` `{"kind":"table","no":"表号"}`：整表复制（表号如 `表3.1-1`）。

⛔ 旧字符串锚（`anchor`/`from`/`to`）已废弃：extract.py/grounding_check.py 不再做字符串匹配。旧字符串锚契约会被 `find_best` 跳过（表现为 CONTRACT_NEEDED），或 save 时被 `CONTRACT_FORMAT_MISMATCH` 拒绝；两层格式契约请走 E3 重跑。

## 防抄错
1. 索引锚定（按大纲 sections[] 顺序 + 段号/表号定位，非相似度、非字符串匹配）→ 防抄错段/错表。
2. `authoritative: true` → 冲突字段权威源。如消防水量取消防章（30L/s/DN200），不取给水章（8L/s/DN150）。
   生产校验由 grounding_check 读**映射 source**上的 `conflict_assertions: [{must_contain, must_not_contain}]` 完成（如§5.1 要求 DN200 在、DN150 不在）。断言是项目专属的，挂在 mapping 对应 source 上，不放在大纲里。
3. 逐字溯源校验 → 抄录块必须是源子串，否则标红。
4. 覆盖检查 → 每小节有源或标 template/compute，否则报警漏抄。

## 未命中处理
段号/表号在源里找不到，或区间越界（a>b / 段号超出范围）→ 输出 `[⚠未找到...]`，**绝不静默跳过、绝不编造**。此时要么修 mapping 锚（E3 重跑），要么说明书结构变了（触发 cerebrum 记录的"投影"失配，需人工校准契约）。

## 锚选取（跨项目通用版）

**核心原则：锚 = 结构定位符（段号/表号），不是内容指纹。** 锚的作用是定位「从哪里抄」，不应该依赖项目特有的地名/数值/专有名词——那些是「抄什么内容」，会随项目变化。

### 优先级（从高到低）
1. **段号（最稳定）**：用批量脚本 KEYWORD SEARCH 定位段落，直接填 `paras` 段号。
2. **表号**：表格一律用 `{"kind":"table","no":"表号"}`，不做内容匹配。
3. **guide[] 关键词（仅用于定位）**：E3 用大纲 `guide[]` 里的通用词批量搜段，命中后记段号。guide 词选描述同类概念的通用词（如"消火栓"、"灭火器"），不选具体数值（如"30L/s"、"DN200"）。

### 禁止作为锚的内容（换了项目就变）
- ❌ 地名：浙江省、某地、某化工企业
- ❌ 数值：11000吨、198 m3/h、0.4MPa、DN65
- ❌ 专有名词：聚乙烯粒料、C库房、执勤楼、综合大队
- ❌ 项目名：基地综合大队、仓库改扩建项目

### 应该作为锚的内容（跨项目稳定）
- ✅ 通用术语关键词（仅用于 guide 批量搜段定位）："消火栓"、"灭火器"、"火灾自动报警"
- ✅ 标准代号："GB50016"、"GB50116"（国家标准跨项目不变）
- ✅ 表题关键词（定位表号）："建筑物一览表"、"电信用户表"

### 全局唯一性
**⚠ guide 关键词只需能定位到正确段落**：批量脚本会列出所有命中段，E3 从中挑选与大纲该节语义最匹配的段号填入 `paras`。若关键词命中多段，必要时用区间 `[a,b]` 框定。

### 旧规则（单文档时代，已废弃）
~~锚从「样本对」逐段比对得到，选源段里独一无二、抗改写的子串（含具体数值/编号/专有名词最佳）；mapping 存字符串 anchor/from/to。~~ ← 这条规则导致锚跨项目全部失配（基地项目→仓库项目：0%），且字符串匹配在 grounding 校验里不可溯源。**新模型 = 两层结构**：大纲锁章节骨架（永不漂移），mapping 只存与大纲按索引 1:1 对齐的段号/表号锚点。改项目 = 只重建 mapping，不动大纲。

## 依赖与格式
- 映射契约同时提供 `.yaml`（人读/编辑）和 `.json`（机读，std-lib 零依赖）。
  `extract.py` / `grounding_check.py` 优先读 `.json`；`.yaml` 需 PyYAML 才可读。
- `parse_spec.py` 优先用 python-docx（结构好），装不上自动回退 zipfile+xml 标准库路径（永远可用）。
- PyYAML (YAML 1.1) 会把裸键 `no`/`yes`/`on`/`off` 强制成布尔。契约里的表号键必须写成 quoted 形式 `"no":`（JSON 里无此问题）。
- `heading_level`（可选，默认 2）：控制 Markdown 标题级数。`2` = `##`，`3` = `###`。章节容器标题用默认 `##`，其下子节用 `###`。
  `class=heading` 的纯容器节不需要 `heading_level`（永远是 `##`）。
- `source_label`（verbatim 节推荐填写）：溯源引用中显示的设计说明书出处，如 `设计说明书 §7 建筑与结构`。
  若不填，默认退化为 `设计说明书`（不再使用专篇自身的章节号，避免"§4.4 ← 源: §4.4"的循环引用）。

## 复用件
- 解析：本技能 `scripts/parse_spec.py`（替代 v2 的 docx_to_md.py 用于结构化抽取；纯文本场景仍可用 v2 的）。
- 合规校验：`skills/public/fire-regulatory-compliance-check/scripts/compliance_checker.py`（10 项 GB 检查）。
- 输出：write_file 到 outputs/ + present_files（沿用 v2 写盘铁律，一次写完）。
