# 三层次架构图（L1/L2/L3）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-09-01-architecture-diagrams-design.md` 用 archify 制作 6 张中文架构图（L1 系统分层 / L2 eaiflow harness / L3 geo 技能 4 张子流程 workflow）+ README 索引，全部通过 showcase 质量门与 4 视口浏览器验证。

**Architecture:** 每张图独立走「内容大纲确认 → archify spec → validate 修复循环 → deliver → visual-check → 目检 → commit」流水线；几何修复协议与已知坑已固化在本计划 P 节。产出集中 `docs/architecture/`。

**Tech Stack:** archify skill（`~/.claude/skills/archify`，Node CLI）、Git（pathspec commit）。

---

## P. 通用工艺（Task 2–7 每张图完整执行一遍）

**P.0 调用 archify skill**：执行图任务前先 `Skill(archify)`（fast authoring 契约会加载；workflow 图还需读 `schemas/workflow.schema.json`、`schemas/common.schema.json`、示例 `examples/agent-tool-call.workflow.json`，architecture 图读 `schemas/architecture.schema.json`、`schemas/common.schema.json`、示例 `examples/production-deployment.architecture.json`）。首次生成候选后跑一次 `node scripts/check-update.mjs`（silent 则不提）。

**P.1 写候选 spec** 到 `docs/architecture/<图名>.spec.json`（UTF-8 无 BOM）。公共 meta：

```json
"meta": { "title": "<图标题>", "locale": "zh-CN", "quality_profile": "showcase" }
```

省略 `visual_preset`/`subtitle`/`legend`/`animation`。

**P.2 validate 修复循环**（每轮后执行，直到 ok:true 0 错误 0 警告）：

```bash
cd ~/.claude/skills/archify && node bin/archify.mjs validate <architecture|workflow> "D:\eai\eai-flow-main\docs\architecture\<图名>.spec.json" --quality showcase --json > "D:\eai\eai-flow-main\.wolf\tmp\val.json" 2>&1
python -c "import json,io; d=json.load(io.open(r'D:\eai\eai-flow-main\.wolf\tmp\val.json',encoding='utf-8')); ds=d.get('diagnostics',[]); print('ok:',d.get('ok'),'| errors:',len([x for x in ds if x['severity']=='error'])); [print('-',x['code'],':',x['message'][:200]) for x in ds]"
```

（勿用管道直喂 python——GBK 控制台会弄坏 JSON；必须落文件再解析。）

修复协议：按诊断的 `subject`+`supportedFixes` 改，一次一处；连续 2 轮错误数不降即停下如实报告。已知坑（直接预防，不要等诊断）：
- viewBox 内容宽 ≤≈1230（1440 视口图区仅 930px；任何 sublabel 被自动缩字号都会拖垮全图投影 ≥6px 门槛）→ 节点宽度按最长 sublabel ≥8px 字号估算，放不下就删字，语义移卡片
- 所有连线显式 `fromSide`/`toSide`；同起点扇出边用 `labelSegment` 把标签分散到不同段
- 长回边走外围走廊：`via` 左侧 x=20、底部 = 最低节点底 +50
- 存储节点与唯一写者垂直对齐（避免 L 形横段贴 region 边）
- region `pad:16`；链上相邻节点间隙 ≥ 最长标签宽 +8px
- 卡片 ≤3 张（第 4 张折行 → 首屏溢出）；每卡 ≤3 条，每条 ≤40 字

**P.3 deliver**（validate ok 后执行一次；失败不得描述为成功）：

```bash
cd ~/.claude/skills/archify && node bin/archify.mjs deliver <architecture|workflow> "D:\eai\eai-flow-main\docs\architecture\<图名>.spec.json" "D:\eai\eai-flow-main\docs\architecture\<图名>.html" --quality showcase --json > "D:\eai\eai-flow-main\.wolf\tmp\deliver.json" 2>&1
python -c "import json,io; d=json.load(io.open(r'D:\eai\eai-flow-main\.wolf\tmp\deliver.json',encoding='utf-8')); print('deliver ok:',d.get('ok'))"
```

**P.4 visual-check**：

```bash
cd ~/.claude/skills/archify && node bin/archify.mjs visual-check "D:\eai\eai-flow-main\docs\architecture\<图名>.html" --json > "D:\eai\eai-flow-main\.wolf\tmp\visual.json" 2>&1
python -c "import json,io; d=json.load(io.open(r'D:\eai\eai-flow-main\.wolf\tmp\visual.json',encoding='utf-8')); print('visual ok:',d.get('ok')); [print(v['width'],'x',v['height'],'scroll:',v['scrollWidth'],'x',v['scrollHeight'],'ok:',v['ok']) for v in d.get('containment',{}).get('viewports',[])]"
```

溢出修复顺序：砍第 3 张卡 → 精简卡条文字 → 压缩 spec 纵向节奏（重走 P.2–P.4）。**禁止** overflow:hidden / 内部滚动条。

**P.5 目检**：用 Read 看 visual-check 产出的 `<图名>.visual-check.1440x900.light.png`（落在 HTML 同目录）：无重叠、字号可读、布局平衡、无大面积空带。

**P.6 commit**（pathspec 限定，防并发会话 reset 误伤）：

```bash
cd "D:\eai\eai-flow-main" && git add docs/architecture/<图名>.spec.json docs/architecture/<图名>.html && git commit -m "docs(architecture): <图名>（showcase+4视口验证通过）" -- docs/architecture/<图名>.spec.json docs/architecture/<图名>.html
```

**P.7 大纲确认**：P.1 之前，把该图的节点/连线清单（即本任务「内容清单」表）以文字呈现用户，等确认（或按用户修改调整）后再写 spec。

---

### Task 1: 建 docs/architecture/ 并移入 geo 架构图

**Files:**
- Create: `docs/architecture/`
- Move: `docs/geo-report-architecture.html` → `docs/architecture/geo-report-architecture.html`
- Move: `docs/geo-report-architecture.spec.json` → `docs/architecture/geo-report-architecture.spec.json`

- [ ] **Step 1: git mv 两文件**

```bash
cd "D:\eai\eai-flow-main" && mkdir -p docs/architecture && git mv docs/geo-report-architecture.html docs/architecture/geo-report-architecture.html && git mv docs/geo-report-architecture.spec.json docs/architecture/geo-report-architecture.spec.json
```

- [ ] **Step 2: commit**

```bash
cd "D:\eai\eai-flow-main" && git commit -m "docs(architecture): geo 技能架构图移入 docs/architecture/（L3 总览层）" -- docs/architecture/geo-report-architecture.html docs/architecture/geo-report-architecture.spec.json docs/geo-report-architecture.html docs/geo-report-architecture.spec.json
```

---

### Task 2: L1 系统功能分层架构图

**Files:**
- Create: `docs/architecture/l1-system-architecture.spec.json`
- Create: `docs/architecture/l1-system-architecture.html`
- 参考: `CLAUDE.md`（Runtime Topology、Architecture、Key Design Decisions）、`backend/docs/ARCHITECTURE.md`

**类型** architecture。diagram_type 顶层字段 + components/connections/boundaries/cards。

**内容清单**（P.7 确认后照此写 spec）：

节点（12）：

| id | type | label | sublabel | 层（region） |
|---|---|---|---|---|
| browser | external | 浏览器 | 用户入口 | — |
| nginx | cloud | nginx :2026 | /api/langgraph/* 重写 → gateway · /* → 前端 | 接入层 |
| frontend | frontend | Next.js :4000 | workspace 对话 + extensions 管理端 · 双认证 | 前端层 |
| gateway | backend | Gateway FastAPI :8001 | 13 routers · RunManager · StreamBridge SSE · JWT+CSRF | 应用层 |
| harness | backend | eaiflow harness | Lead Agent · 中间件 · 子代理 · 沙箱 → L2 下钻 | 框架层 |
| mcp | cloud | MCP 工具 | managed providers · extensions_config 注册 | 能力层 |
| skills | cloud | Skills | 46 public + custom · 热加载 | 能力层 |
| subagents | cloud | 子代理 | task() 双线程池 | 能力层 |
| pg_ext | database | Postgres agentflow | extensions 数据库 | 数据层 |
| pg_core | database | Postgres deerflow | 核心库 · checkpointer | 数据层 |
| sandbox_fs | database | 沙箱文件区 | /mnt/user-data per-user | 数据层 |
| config | database | config.yaml + extensions_config.json | 变更自动重载 | 数据层 |

连线（10）：browser→nginx「HTTPS」emphasis；nginx→frontend「/*」；nginx→gateway「/api/* 重写」emphasis；frontend→gateway「useStream SSE」；gateway→harness「RunManager → run_agent」emphasis；harness→mcp「函数调用」dashed；harness→skills「技能加载」；harness→subagents「task()」；gateway→pg_ext「仓储读写」；harness→pg_core「checkpointer」dashed；harness→sandbox_fs「虚拟路径」；config→harness「热加载」dashed。（12 条，全部显式 fromSide/toSide）

区域（6）：接入层[nginx] / 前端层[frontend] / 应用层[gateway] / 框架层[harness] / 能力层[mcp,skills,subagents] / 数据层[pg_ext,pg_core,sandbox_fs,config]。

卡片（3）：「依赖方向铁律」app→deerflow 单向（tests/test_harness_boundary.py 守护）；「3 原则能力模型」能力必须经 MCP/Skills/子代理到达 agent，否则是孤岛；「热加载」config.yaml 与 extensions_config.json 变更即生效。

- [ ] **Step 1:** P.7 大纲确认
- [ ] **Step 2:** P.0–P.1 写 spec（布局起点：六层水平条带自上而下，browser 最上；框架层 harness 单框加宽）
- [ ] **Step 3:** P.2 validate 循环至全过
- [ ] **Step 4:** P.3 deliver
- [ ] **Step 5:** P.4 visual-check + P.5 目检
- [ ] **Step 6:** P.6 commit `l1-system-architecture`

---

### Task 3: L2 eaiflow harness 架构图

**Files:**
- Create: `docs/architecture/l2-harness-architecture.spec.json` / `.html`
- 参考: `CLAUDE.md` Agent System 节、`backend/docs/ARCHITECTURE.md`、`backend/packages/harness/deerflow/` 目录结构

**类型** architecture。

**内容清单**：

节点（12）：

| id | type | label | sublabel |
|---|---|---|---|
| lead | backend | Lead Agent | 动态模型选择 · 工具加载 · 系统提示生成 |
| mw_ctx | backend | 中间件·上下文组 | ThreadData/Uploads/Memory/ViewImage |
| mw_sec | backend | 中间件·安全组 | Guardrails/ErrorHandling/ToolError |
| sandbox | database | Sandbox 中间件 | per-user 目录挂载 |
| mw_flow | backend | 中间件·流程组 | Summarization/TodoList/LoopDetection/Clarification/SubagentLimit |
| mw_ledger | backend | 中间件·记账组 | TokenUsage/Title |
| subagents | backend | 子代理双线程池 | 3 调度 + 3 执行 · general-purpose/bash |
| tools | backend | Tools | 函数调用工具集 |
| models | cloud | Models | 动态选择 |
| mcp | cloud | MCP | managed providers |
| skills | cloud | Skills | 技能加载 |
| config | database | Config | config.yaml 热加载 |

连线（9，链序标注「示意分组，实际 17+ 中间件按固定顺序」于链首边标签或卡片）：lead→mw_ctx「进入链」；mw_ctx→mw_sec；mw_sec→sandbox；sandbox→mw_flow；mw_flow→mw_ledger；mw_ledger→tools「tool call」emphasis；mw_flow→subagents「task()」emphasis；mcp→tools「注册工具」dashed；skills→lead「加载」；config→lead「热加载」dashed；subagents→sandbox「沙箱执行」；models→lead「模型路由」。

区域（1）：`eaiflow harness (deerflow.*)` wraps 全部 12 节点 pad 20。

卡片（3）：「中间件链为示意」实际 17+ 个按固定顺序执行，此图按功能分组；「ThreadState」扩展 AgentState：sandbox/thread_data/artifacts/todos/uploaded_files；「SSE 合约」事件经 StreamBridge 匹配 LangGraph Platform 协议。

- [ ] **Step 1:** P.7 大纲确认
- [ ] **Step 2:** P.0–P.1 写 spec（布局：lead 居中上，链横排，子系统下排）
- [ ] **Step 3–6:** P.2 → P.3 → P.4+P.5 → P.6 commit `l2-harness-architecture`

---

### Task 4: L3a 数据收集→门1（workflow）

**Files:**
- Create: `docs/architecture/l3a-data-collection-gate1.spec.json` / `.html`
- 参考: `skills/public/geological-report/SKILL.md` 步骤 1 节

**类型** workflow（schema_version 2，先读 workflow schema + agent-tool-call 示例）。

**内容清单**（泳道：用户 / 控制器 / 脚本）：

| 节点 | 说明 |
|---|---|
| kf_resolve | 真实调用 kf_resolve_template（必须留调用记录） |
| declare | found=false → 声明内置 references 兜底 + 读 data_expectations 按章预告 |
| gen_forms | ingest.py forms 生成空白表单 |
| collect | 逐类 ask_clarification（单回合一张、对象族按子键、≤16 项/卡） |
| guide_csv | 矿体>3 或清单>10 条 → 普通消息引导上传 CSV（禁做成卡片） |
| ingest_write | ingest.py file/forms 落盘（唯一写者，只传用户提交的键） |
| gate1 | ingest.py check → GATE1_COMPLETE / rc=2 |

边：kf_resolve→declare「found=false」；kf_resolve→gen_forms「命中模板」；declare→gen_forms；gen_forms→collect；collect→guide_csv「清单>10」；guide_csv→ingest_write「CSV 上传」；collect→ingest_write「表单值」；ingest_write→gate1；gate1→collect「rc=2 缺项中文化回环」回环边；gate1→done「GATE1_COMPLETE」。terminal 节点 done「门1 通过，进入冻结」。

卡片（3）：「示例值≠数据」placeholder 示例绝不落盘；「崩溃即停」脚本报错原样呈现，绝不手写 data/；「卡片词条禁区」不得提供推导/假定/估算选项。

- [ ] **Step 1:** P.7 大纲确认
- [ ] **Step 2:** P.0–P.1 写 spec（workflow v2 readable layout；回环边给足走廊）
- [ ] **Step 3–6:** P.2 → P.3 → P.4+P.5 → P.6 commit `l3a-data-collection-gate1`

---

### Task 5: L3b 冻结计算→门2（workflow）

**Files:**
- Create: `docs/architecture/l3b-freeze-calc-gate2.spec.json` / `.html`
- 参考: SKILL.md 步骤 2–3 节

**内容清单**：

| 节点 | 说明 |
|---|---|
| planner | chapter_planner.py manifest → chapter_manifest.json |
| runner | formula_runner.py execute（Decimal ROUND_HALF_EVEN，槽位带 source） |
| state_write | 冻结值入库 state/formula_state.json（唯一写者） |
| gate2 | 退出码判定：rc=0 / rc=3 anomalies / 结果全 0 空 |
| confirm | rc=3 → ask_clarification 逐条确认（免打扰法定例外，只给「按冻结值继续」） |
| halt_zero | 全 0/空 → 停，呈现 anomaly 问数据 |
| frozen | 门2 通过，冻结生效 → 进入派发 |

边：planner→runner；runner→state_write；state_write→gate2；gate2→frozen「rc=0」；gate2→confirm「rc=3」；confirm→frozen「用户确认」；gate2→halt_zero「全 0/空」。

卡片（3）：「不隐瞒」anomalies=计算完成但你要知道，不可静默放行；「唯一写者」formula_state 手改必丢，build 检测门 FAIL；「口径」与 backend FormulaGraph float eval 无关，自包含。

- [ ] **Step 1:** P.7 大纲确认
- [ ] **Step 2–6:** P.0–P.1 → P.2 → P.3 → P.4+P.5 → P.6 commit `l3b-freeze-calc-gate2`

---

### Task 6: L3c 派发协议（workflow）

**Files:**
- Create: `docs/architecture/l3c-dispatch-protocol.spec.json` / `.html`
- 参考: SKILL.md 步骤 4 节

**内容清单**（泳道：控制器 / 子代理 / 脚本）：

| 节点 | 说明 |
|---|---|
| read_progress | 读 progress.json（唯一事实源，不信对话记忆） |
| wave1 | batch_task 全扇出写章（每章写够再进下一章，禁薄初稿） |
| write_ch | 子代理落 chapters/chN.md |
| ch_gate | 单章门 build_output --chapter N 即时验 |
| wave2 | wave2 结论汇总收束 |
| ledger | 记账 progress.json |
| downgrade | 门 FAIL 且目标不合理 → progress.py approve-downgrade（用户批准留痕） |

边：read_progress→wave1；wave1→write_ch；write_ch→ch_gate；ch_gate→wave1「未达标补写」回环；ch_gate→wave2「达标」；wave2→ledger；ch_gate→downgrade「申请降档」；downgrade→ledger「partial 留痕」。

卡片（3）：「Iron Law」门 FAIL 唯一合法出路=补写正文或申请降档，改 references/绕 CLI=伪造；「控制器」主会话薄上下文只协调不写章；「Excuse≠Reality」基准=合同，「先跑通再补深度」=死循环起点。

- [ ] **Step 1:** P.7 大纲确认
- [ ] **Step 2–6:** P.0–P.1 → P.2 → P.3 → P.4+P.5 → P.6 commit `l3c-dispatch-protocol`

---

### Task 7: L3d 恢复+终验+修改回路（workflow）

**Files:**
- Create: `docs/architecture/l3d-recover-finalize-loop.spec.json` / `.html`
- 参考: SKILL.md 步骤 0、5–7、修改回路、交付铁律节

**内容清单**：

| 节点 | 说明 |
|---|---|
| verify | snapshot.py show --verify（rc=3 被篡改即停） |
| build | build_output.py 槽位注入（未知 SLOT FAIL/目录覆盖门 v2/残留扫描/深度地板） |
| consistency | consistency.py 22 合约（0 过/1 FAIL/2 人工/3 WARN） |
| snapshot | snapshot.py save → project_snapshot.json（全文件 SHA-256） |
| manifest | delivery_manifest.json 在场确认 |
| present | present_files 交付唯一单文件（BUILD_READY+退出码原样粘贴） |
| modify | 修改回路：只落 state/chapters/chN.md |
| halt | rc≠0 → stderr 原样粘贴停下修章节 |

边：verify→build「新任务/续做」；build→consistency；consistency→build「FAIL 修章节回环」；consistency→snapshot「过」；snapshot→manifest；manifest→present；modify→build「重跑三连」回环；build→halt「rc≠0」；consistency→present「rc=3 WARN 如实汇报」dashed。

卡片（3）：「交付铁律」绝不手工拼装 outputs/*.md，交付名门强制；「禁改交付物」改扩写只落 chapters/ 重跑三连；「.delivery-contract 勿删」删除=门失效=交付作废。

- [ ] **Step 1:** P.7 大纲确认
- [ ] **Step 2–6:** P.0–P.1 → P.2 → P.3 → P.4+P.5 → P.6 commit `l3d-recover-finalize-loop`

---

### Task 8: README 索引 + 收尾

**Files:**
- Create: `docs/architecture/README.md`

- [ ] **Step 1: 写 README.md**（内容如下，原样使用）

```markdown
# 架构图总览（L1 → L2 → L3 下钻）

由 archify 生成，全部通过 showcase 质量门 + 4 视口浏览器验证。

| 层次 | 图 | 内容 |
|---|---|---|
| L1 | [l1-system-architecture](l1-system-architecture.html) | eai-flow 系统功能分层（接入/前端/应用/框架/能力/数据） |
| L2 | [l2-harness-architecture](l2-harness-architecture.html) | eaiflow harness（Lead Agent + 分组中间件链 + 子系统） |
| L3 总览 | [geo-report-architecture](geo-report-architecture.html) | geological-report 技能架构（两道门主链） |
| L3 子流程 | [l3a 数据收集→门1](l3a-data-collection-gate1.html) | KF 三件套 → 表单/CSV → ingest → 门1 |
| L3 子流程 | [l3b 冻结→门2](l3b-freeze-calc-gate2.html) | planner + formula_runner → 异常确认 → 冻结 |
| L3 子流程 | [l3c 派发协议](l3c-dispatch-protocol.html) | wave1 全扇出 + wave2 结论 + Iron Law |
| L3 子流程 | [l3d 恢复+终验+修改回路](l3d-recover-finalize-loop.html) | snapshot 验证 → build → consistency → 交付 |

下钻关系：L1 框架层 → L2；L2 Skills/子代理原语 → L3 总览；L3 总览各管线节点 → 对应 l3a–l3d 子流程。

各图 `.spec.json` 为 archify 规格（重渲染/改图用）。
```

- [ ] **Step 2: commit**

```bash
cd "D:\eai\eai-flow-main" && git add docs/architecture/README.md && git commit -m "docs(architecture): 三层次架构图索引 README" -- docs/architecture/README.md
```

- [ ] **Step 3: 链接自查**

```bash
cd "D:\eai\eai-flow-main" && python -c "
import re,io,os
md=io.open('docs/architecture/README.md',encoding='utf-8').read()
for m in re.findall(r'\]\(([^)]+\.html)\)',md):
    assert os.path.exists('docs/architecture/'+m), m
print('links ok')"
```

Expected: `links ok`

---

## 执行注意

- 每张图 commit 后 `.wolf/memory.md` 记一行（OpenWolf 协议）。
- 取证时若 SKILL.md/ARCHITECTURE.md 与 CLAUDE.md 表述冲突：以各域专属文档为准，冲突点原样呈现用户裁决，不自选。
- 不 push origin（除非用户要求）。
- spec 与 HTML 永远成对同名；禁止只改 HTML 不改 spec。
- Windows 下所有 node 命令在 `~/.claude/skills/archify` 目录执行；路径用引号包裹。
