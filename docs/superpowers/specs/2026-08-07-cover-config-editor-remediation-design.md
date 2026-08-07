# 封面配置 Section 评审与修复设计 — 排版模板编辑器

**日期**: 2026-08-07
**状态**: APPROVED（2026-08-07，经 2 轮对抗评审，8/10）
**范围**: 报告输出扩展
- 前端 `frontend/src/extensions/output/components/LayoutTemplateEditor.tsx`、`api.ts`、`OutputManager.tsx`
- 后端 `backend/app/extensions/output/{layout_import.py, generator.py, routers.py}`

**上游设计**: `2026-08-07-cover-master-reproduction-design.md`（封面母版 OOXML 透传 + 槽位绑定）。本文件是对其「封面配置」区块的评审深化与缺陷修复设计。评审对象是已合入 `main-dev-fork` 的实现（commits `85484657c`/`f5c641027`/`aae5a60ac` 等）。

---

## 1. 评审结论

**架构方案正确，状态管理不完备。**

- **合理**：OOXML 透传 + 槽位绑定正确解决了"真实还原表格类封面"（数据模型表达力天花板）问题；生成优先级 `master > cover_template > 无` 清晰且向后兼容；`target` 标签包含方案解决重复值碰撞（bug-1117）；槽位预填规则与图片 `rId` 重写有单测覆盖。
- **不完备**：交互语义层有 3 个高影响缺陷（封面导入覆盖全量配置、母版无法清除且重复导入 stale、首次点开关全亮）+ 6 个中低缺陷（`logoPosition` 死字段、`sampleValue` 编辑误导、无 `defaultFrom` 来源提示、封面渲染失败静默吞异常、不可解析槽位可切"变量"但永不生效、列表接口携带全量母版载荷）。（注：M5 初判的"命名空间脆裂"经实证不成立，详见 M5 节。）

---

## 2. 缺陷清单与修复方案

每条含：现象 / 根因（证据）/ 修复（文件 + 行为）。

### H1 — 封面专用导入按钮覆盖全部排版设置（数据丢失，最高优先）

**现象**：封面区「重新从样例导入封面」/「从样例 .docx 导入真实封面」两个按钮，与基本信息区「从样例导入排版」共享同一个 `fileInputRef` 与 `handleImportedFile`。用户配好正文/页面/页眉后只想换封面 → 其它 section 全部被样例覆盖。

**根因**：`LayoutTemplateEditor.tsx:389-407` → `applyImported`（`364-387`）一次性写入 `pageSettings/bodyStyles/headingStyles/tableStyles/figureStyles/headerFooter/coverTemplate/coverMaster`。设计文档 §5.5"重新从样例导入封面按钮复用同一端点"——复用端点即复用全量导入副作用，设计级缺陷。

**修复**（前端为主，无需后端改动）：
1. 前端 `LayoutTemplateEditor.tsx` 拆分：
   - `applyImportedLayout(data)` — 全量写入（基本信息区按钮使用）。
   - `applyImportedCover(data)` — **只**读 `cover_master`/`cover_template`/`cover_detected`，**丢弃其余键**（封面区两个按钮使用）。导入端点本就返回全量，丢弃非封面键即可达成"只导封面"；无需后端 scope 参数（响应体积对一次性导入可忽略）。
2. **按钮路由机制（必须明确，否则实现者会把封面按钮接到全量 applier）**：三个按钮共享一个 `fileInputRef` 与一个 `handleImportedFile`。新增 `pendingScopeRef = useRef<"full" | "cover">("full")`：
   - 基本信息区按钮点击前设 `pendingScopeRef.current = "full"`；
   - 封面区两个按钮点击前设 `pendingScopeRef.current = "cover"`；
   - `handleImportedFile` 读完 ref 后调用对应 applier。保持单 hidden input，避免三份 input。
3. （可选优化，非必需）后端 `routers.py::import_layout` 加 `scope: str = Query("full")`，`scope=="cover"` 时只返回封面三键，减少响应体积。需在 `routers.py:11` 引入 `Query`。

### H2 — 母版无法清除 / 重复导入产生 stale master

**现象**：
- 封面区无任何「移除母版」入口；`setCoverMaster` 全文件只在导入时赋非空值（`LayoutTemplateEditor.tsx:317` 初始化、`379` 赋值），从不置 `null`。
- `applyImported` 在 `data.cover_master` 为 `None` 或非 master 时**不重置** coverMaster（`376-386`）。重新导入一个无封面/仅开关模板的样例后，旧母版仍留在 state、继续显示并保存生效——用户以为换了封面，生成仍是旧的。
- 一旦进 master 模式，旧的 6 开关简单封面（数据模型允许 `coverMaster: null + coverTemplate`）永远回不去。

**修复**：
1. Master 模式加「移除母版」按钮 → `setCoverMaster(null)`，UI 回落到开关模式。
2. 开关模式加「移除封面」按钮 → `setCoverMaster(null)` 且 `setCoverTemplate(null)`（两键都置 null 才是真正"无封面"，见 `generator.py:1025` `has_cover = bool(cover_master or cover_template)`）。
3. `applyImportedCover` 改为**总是**复位：`setCoverMaster(cm?.mode === "master" ? cm : null)`；无母版时按 `cover_detected` 决定是否写 `coverTemplate`，否则也置 null。杜绝 stale master。
4. **同一复位语义必须同时放进 `applyImportedLayout`**（全量导入 applier，即旧 `applyImported`）——否则用户先导母版、再用基本信息区「从样例导入排版」导入无封面样例，stale master 会从这条路径漏回（H2 缺陷距用户一个按钮）。两个 applier 抽一个共享的 `resolveCoverFromImport(data)` 助手。

### M1 — 开关兜底模式"点一个开关全亮"

**现象**：显示侧用 `?? false`（初始全关，`LayoutTemplateEditor.tsx:646-651`），合并侧 `patchCover` 用 `{ ...(c ?? COVER_DEFAULT), ...p }`（`332`），`COVER_DEFAULT` 五键全 `true`（`291`）。从 `null` 点第一个开关 → 五开关同时亮，预览从"只显 Logo"跳成"完整封面"。

**根因**：显示默认值（false）与合并默认值（true）不一致。

**修复**：`patchCover` 的 base 必须是**含全部 5 个布尔 + logoPosition 的完整对象**，且布尔全 `false`。不能是 `{ logoPosition: "center" }`（缺 5 布尔）——否则 `tsc` 报缺字段，且保存会踩后端默认值陷阱：
- `schemas.py:22-28` `CoverTemplateSchema` 五布尔默认 `True`；`service.py:34` **create 路径用无 `exclude_unset` 的 `model_dump()`** → 前端省略的布尔被 Pydantic 以默认值补齐存库 → 下次编辑五开关全亮（save→reload 回归）。update 路径 `service.py:54` 有 `exclude_unset=True` 不受影响，但 create 会。
```ts
const COVER_EMPTY: CoverTemplate = { showLogo: false, showTitle: false, showClient: false, showDate: false, showProjectNumber: false, logoPosition: "center" };
const patchCover = useCallback(
  (p: Partial<CoverTemplate>) => setCoverTemplate((c) => ({ ...(c ?? COVER_EMPTY), ...p })),
  [],
);
```
首点只开当前那一个开关，且载荷始终显式携带 5 布尔（false），create 存库不被默认值污染。删除被 M2 复用的旧 `COVER_DEFAULT`（M1/M2 统一用 `COVER_EMPTY`，避免死代码触发 ESLint）。测试断言用 `=== true`（点中键）与 `!== true`（其余键），并加 save→reload 往返断言（见 §4）。

### M2 — `logoPosition` 是死字段

**现象**：`types.ts:36` 声明 `logoPosition: "left"|"center"|"right"`，全 UI 无控件，永远 center；预览硬编码居中。

**修复**（前端 + 后端，否则字段在导出里仍是死的）：
1. 前端开关模式加一个 `AdminSelect`（左/中/右）→ `patchCover({ logoPosition: v })`；封面预览 Logo 块按 `logoPosition` 对齐（flex `justify-start/center/end`）。
2. 后端 `generator.py::_render_cover`（`126` 行 Logo 段落硬编码 `WD_ALIGN_PARAGRAPH.CENTER`）改为按 `ct.get("logoPosition")` 映射 left/center/right → `WD_ALIGN_PARAGRAPH.LEFT/CENTER/RIGHT`。
3. 说明：`logoPosition` 只作用于**开关兜底模式**（`_render_cover`）；母版模式是 OOXML 透传，位置已烘焙进样例 XML，不受该字段影响——前端仅在无 master 时展示此控件。
4. 统一使用 `COVER_EMPTY`（见 M1），删除旧 `COVER_DEFAULT`。

### M3 — `sampleValue` 编辑语义误导，会静默破坏替换

**现象**：输入框让用户改 `sampleValue`，但生成端 `_render_cover_master`（`generator.py:214`）用 `target = slot.target || sampleValue` 在**导入时定格的 xml** 里找文本替换。用户把 `sampleValue` 改成样例中不存在的文本 → find-target 找不到 → 该槽位静默不替换。

**根因**：`sampleValue` 实际是"原文靶文本"（find-target），不是"最终显示值"。UI 无任何说明。

**修复**：
1. 槽位列表区加说明行：`原文靶文本：生成时按此文本定位并替换；编辑后须仍存在于封面原文中，否则该槽位不生效。`
2. 每个 `sampleValue` 输入框加 `title` 提示 + 输入框 placeholder 提示。
3. 后端不改（生成语义正确，是 UI 未澄清）。

### M4 — 无 `defaultFrom` 来源提示（偏离设计）

**现象**：设计文档 §7 明确每行槽位带"来源提示"；实现漏了（`LayoutTemplateEditor.tsx:619-637`）。用户无法知道变量槽位生成时从哪取值（`doc_title`? `frontmatter`? `today`?）。

**修复**：槽位行 label 下加来源小字，映射。注意只映射**实际会出现的非空值**——`layout_import.py:597-612` `_COVER_COLON_FIELDS` 中 `project_name`/`stage`/`archive_no`/`version`/`certificate_no` 的 `default_from` 全部为 `None`（只有 `title→doc_title`、`client→frontmatter:client`、`date→today` 非空），映射里放死键会在 UI 上永不渲染：
```ts
const DEFAULT_FROM_LABELS: Record<string, string> = {
  doc_title: "来自文档标题",
  today: "来自当前日期",
  "frontmatter:client": "来自报告元数据·建设单位",
};
// 无 defaultFrom → "无自动来源"
```

### M5 — 封面渲染失败静默吞异常（原"命名空间脆裂"经实证不成立，降级为纯日志修复）

**现象**：`generator.py:1037-1038` 封面渲染包在 `try/except: pass` —— 任何失败（坏 XML、槽位替换异常、图片重嵌异常）都被吞掉，母版直接不出封面且无任何提示。用户只看到"没封面"，无法区分是"样例无封面"还是"生成失败了"。

**命名空间推论（已证伪，勿再实施静态表）**：原稿推断 `_render_cover_master`（`generator.py:197`）wrapper 只声明 `w/a/r`，含 `mc:`/`wps:`/`wp:`/`pic:` 前缀的封面会 `unbound prefix`。经 lxml 6.0.2 实证：`_extract_cover_master` 用 `etree.tostring(deepcopy(block), encoding="unicode")`（`layout_import.py:719`）逐块序列化，**lxml 会在每个块根上输出该子树所需的全部 xmlns 声明**——块是自包含的，重新包进 `w/a/r` wrapper 再解析不会报 unbound prefix（含 `mc:Ignorable="w14 wp14"` 的纯 token 属性也安全）。因此原 M5 的"文本框/浮动图定时炸弹"根因不成立，命名空间静态表是**为不存在的问题过度设计**，不实施。

**修复**（仅日志）：
1. `generator.py:1037-1038` 改为 `logger.warning("cover render failed: %s", exc)`（`logger` 已在文件内定义）——仍不中断生成（封面失败不能 abort 报告），但失败可观测。
2. 若日后真实样例确实出现反序列化失败，再走升级路径：提取端收集封面区 in-scope `nsmap` 并集存入 `cover_master["nsmap"]`，生成端用它构造 wrapper（需同步 `CoverMasterSchema`/前端 `CoverMaster` 加可选字段）。本期不做。

### M6 — 不可解析槽位可切"变量"但永不生效

**现象**：`_prefill_cover_slots` 会造出生成器无法解析的槽位——`design_unit`（`layout_import.py:670-671`）、以及 `archive_no`/`version`/`certificate_no`（`_COVER_COLON_FIELDS` `597-612`，`default_from=None`）。UI 允许把它们切成 `variable`，但 `_render_cover_master` 的 `slot_value`（`generator.py:199-206`）只含 `{title, client, project_number, date, project_name, stage}` → `repl=None` → 跳过，静默无效。UI 暴露了生成器兑现不了的选项。

**修复**：前端在 `kind` 切换按钮上，对不在可解析集合 `["title","client","project_number","date","project_name","stage"]`（= `slot_value` 键全集）的槽位**禁用切换**，`title` 提示"该槽位生成时无取值来源，仅保留原文"。不可解析槽位包括：`design_unit`、`archive_no`、`version`、`certificate_no`。

**注意：显示态必须从可解析集合推导，不能从 `slot.kind` 读**。`archive_no`/`version`/`certificate_no` 是 `_prefill_cover_slots` 以 `kind="variable"`（冒号字段默认）创建的——若只是禁用按钮而徽章仍按存储 `kind` 渲染，会显示禁用的"变量"徽章，误导依旧。实现：渲染时按 id 是否在可解析集合决定徽章文案（不可解析一律显示"字面"）+ 按钮禁用；`slot.kind` 仅对可解析槽位有意义。后端保持现状（这些字面量仍有识别价值）。

### L1 — 列表接口携带全量母版载荷

**现象**：`routers.py:79-88` `list_templates` 返回完整 `LayoutTemplateResponse`，含每个模板的 `cover_master.xml`（OOXML 片段）+ `images`（base64 图）。模板多/封面图大时列表响应膨胀。

**根因**：编辑器直接吃列表数据（`OutputManager.tsx:126` `setEditingTemplate(t)`），前端 `getTemplate`（`api.ts:14`）从未被调用。

**修复**：
1. 后端 `list_templates`：每项 `model_dump()` 后剔除 `cover_master.xml/images`（保留 `mode/slots/sourceFile/boundary`，槽位 label 可供列表/卡片后续展示）。`cover_master` 是 `dict | None`，剥离后仍通过 `LayoutTemplateResponse` 校验（`schemas.py:144`，`LayoutTemplateListResponse.items` 类型兼容）。
2. 前端 `OutputManager.tsx`：`onEdit` 改为异步——先 `await outputApi.getTemplate(t.id)` 拉全量再 `setEditingTemplate`；**拉取期间用 pending 态（禁用按钮/loading）**，避免用户重复点击。
3. **失败回退（不要"只读打开"）**：`LayoutTemplateEditor` 无只读模式，`handleSave` 会把残缺的 `coverMaster`（缺 `xml`，`schemas.py:45` 必填）原样发出 → 422。`getTemplate` 失败时**不打开编辑器**：`setEditingTemplate(null)` + 错误 toast。
4. 保留 `duplicate`/`create`/`update` 返回全量（`routers.py:141+` 等）。

---

## 3. 实施批次（依赖排序）

| 批次 | 内容 | 文件 | 改动规模 |
|------|------|------|---------|
| P0 | H1 封面专用导入（前端 scope applier）+ H2 母版清除/stale + M1 首点全开 + M3 语义提示 | `LayoutTemplateEditor.tsx`（`api.ts` 仅当实施 H1 可选 scope 参数时） | 纯前端，~1 文件为主 |
| P1 | M2 logoPosition（前端控件 + 后端 `_render_cover` 对齐）+ M4 defaultFrom 提示 + M6 变量陷阱禁用 | `LayoutTemplateEditor.tsx` `generator.py` | 前端为主 + 后端 3 行 |
| P2 | M5 封面渲染失败可见（`logger.warning`） | `generator.py` | 后端 2 行 |
| P3 | L1 列表剥离 + 编辑拉详情 | `routers.py` `OutputManager.tsx` | 前后端各 1 小改 |

P0/P1/P2 相互独立可并行；P3 依赖 P0 完成（`getTemplate` 拉详情后编辑器才拿到全量母版，与 H1 的前端 state 改动同文件）。

## 4. 测试

- 后端 `tests/test_cover_master.py` 增补：
  - 封面渲染抛异常（构造坏 xml）→ `logger.warning` 有输出（`caplog` 断言），且生成不 abort（M5）。
  - `_render_cover` 按 `logoPosition` 输出对应段落对齐（`WD_ALIGN_PARAGRAPH.LEFT/CENTER/RIGHT`）（M2）。
  - `list_templates` 剥离 `xml/images`、其余键保留（L1）。
  - 若实施 H1 可选优化：`import-layout?scope=cover` 只返回封面三键。
- 前端（`tests/unit/extensions/output/`，新增 `LayoutTemplateEditor` 组件测试）：
  - `applyImportedCover` 只写封面 state，其它 section 不变（H1）。
  - 重复导入无封面样例 → `coverMaster` 复位为 null（H2）。
  - 从 null 点单个开关 → 点中键 `=== true`、其余键 `!== true`（M1，注意非 `false`，是未设/false 都不得为 true）。
  - **M1 往返回归**：点单个开关 → 走 `createTemplate` 载荷 → 断言载荷里 5 布尔全显式（含 4 个 `false`），Pydantic 缺省补齐不再生效。
  - **M1 后端持久化回归**：`service.create_template` 收到显式 `showLogo:true, showTitle:false…` 的 `cover_template` → `model_dump()`（无 `exclude_unset`）存库 → 重读后 5 布尔与输入一致（`false` 不被默认值污染）。
  - 非可解析槽位（design_unit/archive_no）的 kind 按钮 disabled（M6）。

**P0 实施偏差记录（2026-08-07）**：前端组件测试（`.dom.test.tsx`）未交付——repo 无 `happy-dom`/`@testing-library/react` 依赖、零 DOM 测试文件（56 个全为纯 node `.test.ts`），加依赖需 image rebuild，超出 P0 纯前端范围。改为把封面状态逻辑抽成纯模块 `frontend/src/extensions/output/cover-state.ts`，以纯 node 测试覆盖同等行为保证（`cover-state.test.ts`，39 用例）。已按评审补齐：`normalizeCoverTemplate`（全 false → null，防空白封面页）、`patchCoverState` 恒 seed `COVER_EMPTY`（非空 partial 也完整）、非 master `cover_master` 不采纳、master+toggle 并存时 master 优先等边界用例。组件级接线（按钮路由/移除按钮/save 载荷）仍缺自动测试——待补 `.dom.test.tsx` 基建后按 §4 补齐。

**P1 实施记录（2026-08-07）**：M2（logoPosition 控件 + 后端 `_render_cover` 对齐 + `coverLogoPosition` 纯函数）、M4（槽位来源提示 slot-aware：可解析槽位 null `defaultFrom` 仍显示实际来源，仅真不可解析槽位显示「无自动来源」）、M6（不可解析槽位锁变量 + 字面量渲染为纯文本 + 常量 `COVER_RESOLVABLE_SLOT_IDS`）。评审补强：`syncSlotTarget`（编辑 `sampleValue` 时同步重写 label-inclusive `target`，修复"编辑不生效"）、`CoverTemplateSchema.logoPosition` 改 `Literal["left","center","right"]`（数据完整性）、`COVER_SLOT_VALUE_KEYS` 后端常量 + 跨语言漂移测试、`pendingScopeRef` 取消对话框后不再残留、后端 logoPosition absent-key 用例。验证：前端 39 测试/tsc/eslint/prettier 全绿，后端 29 测试 + ruff 全绿。

**P2/P3 实施记录（2026-08-07）**：P2=M5（两处封面渲染 `except` 改 `logger.warning`，含图片重嵌内层 except；封面渲染失败时不再产生空白首页——`cover_rendered` 标志控制加分节）。P3=L1（`routers.py::list_templates` 经 `_strip_cover_master_payload` 剥离 `cover_master.xml/images` 只留轻量信封；`OutputManager` 编辑时先 `getTemplate` 拉全量再开编辑器 + 15s 超时 + pending 禁用编辑/新建按钮防叠模态；`CoverMaster.xml/images` 改可选以如实反映 list/detail 两种形态）。验证：前端 39 测试/tsc/eslint/prettier 全绿，后端 44 测试 + ruff 全绿。**四批次（P0-P3）全部完成。**

## 5. 风险与回退

- **H1 回归**：封面导入若接口异常，前端 fallback 到错误 toast，不落任何 state（封面/全量两个 applier 一致）。
- **H2 复位回归**：`applyImportedLayout`（全量导入）与 `applyImportedCover` 必须共享同一复位语义（见 H2 修复 3），否则用户先导母版、再用基本信息区「从样例导入排版」导入无封面样例，stale master 会从这条路径漏回。
- **L1 回归**：编辑器打开若 `getTemplate` 失败，**不打开编辑器**（`setEditingTemplate(null)` + 错误 toast），杜绝残缺 `cover_master`（缺必填 `xml`）被保存触发 422。
- **M5**：封面渲染失败降级为 `logger.warning` + 无封面（不 abort 报告），可观测且非静默；nsmap 升级路径仅在有真实失败样例时启用，本期不实施、无静态表。
- 向后兼容：老数据（无 `target` 的槽位、仅布尔 `cover_template`）行为不变；`COVER_EMPTY` 只在用户首次交互后写入显式布尔。

## 6. 成功标准

- 用户配好正文后单独换封面，其它 section 不被覆盖（H1）。
- 母版可一键移除、回落到开关模式；重复导入无封面样例不再显示/保存旧母版（H2）。
- 封面区所有可编辑项（开关、logoPosition、槽位 kind/靶文本、来源提示）语义自洽，无"点一个全开"、无"切了不生效"的陷阱（M1/M2/M3/M4/M6）。
- 封面渲染失败不再静默——`logger.warning` 可观测，不中断生成（M5）。
- 模板列表接口不再携带母版 xml/base64（L1）。

## 7. 非目标（本期不做）

- 封面母版实时 HTML/PNG 预览（沿用设计 D6，靠"生成输出"验证）。
- 槽位新增（插入新占位符到 OOXML 需 XML 编辑能力，另期）。
- 会签表签字人预填（花名册子系统，另期）。
