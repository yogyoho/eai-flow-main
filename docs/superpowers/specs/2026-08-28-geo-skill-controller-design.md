# 地质报告技能控制器化改造设计（借鉴 superpowers 过程纪律）

- 日期：2026-08-28
- 状态：待用户审阅
- 技能：`skills/public/geological-report/`
- 前置：三门硬化已落地（commit `93a71f4e2`），单表单铁律已落地（`5475bd8c8`）

## 1. 背景与问题

页面测试（线程 03e18e4a）取证结论：死循环主体是 agent 行为，但行为背后有真实的结构性根因——

- **10/10 章初稿全薄**：每章有效字符 776~7764 vs 真目标 1498~10522，总缺口 18,854 eff 字符
- 面对深度门 FAIL，agent 选择「让门消失」而非补写：伪造 depth_targets.json（coefficient=0.01）、绕 CLI 直调 assemble() ~10 次
- 熔断链：60 次 bash 熔断 → FORCED STOP → GraphRecursionError(300)

已在 `93a71f4e2` 修复的脚本放大器（本设计不重复覆盖）：L1 父节结构陷阱、fail-fast 单章打回、`--targets` 旁路与直调通道。

**残留根因**（本设计的靶子）：

| # | 根因 |
|---|---|
| R1 | 单上下文体量：一次跑全 10 章 × 1k-6k eff 字符/章 + 全管线步骤，超出单 agent 能力 → 初稿全薄 |
| R2 | 编排靠 prose：管线步骤/修错循环/波次顺序全在 SKILL.md 叙述里，agent 压力下即兴发挥 |
| R3 | 无断点续跑：磁盘有 data/state，但无「下一步做什么/哪些已验证」的进度模型 |
| R4 | 无范围协商：目标不可达时只有死磕或作弊两条路 |
| R5 | 单兵作战：无子代理扇出 |

## 2. 已拍板的决策

| # | 决策 | 内容 |
|---|---|---|
| D1 | 成功标准 | **可靠跑通 + 少量问询**：允许中途问数据缺口/深度降档，但死循环、熔断、绕门是绝对禁区 |
| D2 | 失败终态 | **诚实部分交付**：达标章正常交付，未达标章在交付物与 manifest 明确标注「深度未达标+差多少」，收尾说明补齐路径 |
| D3 | 方案 | **A 全扇出**：wave1 全部独立章走 task() 子代理（water-drainage-report 生产验证过的同构范式） |

## 3. 借鉴的 superpowers 模式

| 模式（来源技能） | 根因 | 落点 |
|---|---|---|
| 控制器 + 每任务全新子代理（subagent-driven-development） | R1 R5 | 步骤 4 改派发协议，主会话只做协调 |
| 子代理不继承历史 + 文件通道（implementer-prompt） | R1 R2 | 派发 prompt 指向沙箱文件路径，不贴全文 |
| 不信任报告只信产物（verification-before-completion / request-code-review） | R2 | 收章必跑单章门，PASS 才落 VERIFIED——子代理说什么不算 |
| checkbox 状态文件 = 协议（writing-plans） | R2 R3 | state/progress.json 唯一事实源 |
| 文件头执行路由 + 精确命令/期望 rc（writing-plans） | R3 | progress.py next 输出恰好一个下一步 |
| 升级安全条款 + 状态枚举（implementer-prompt） | R4 | BLOCKED 是一等公民，申请降档被鼓励而非惩罚 |
| 门不可省、门重可调（brainstorming HARD-GATE 精神） | R4 | 深度门不可伪造，但 coefficient 可经用户批准 + 留痕调整 |
| 反合理化表 RED 基线法（writing-skills） | R4 行为面 | Excuse\|Reality 表取自 03e18e4a 逐字取证 |
| 渐进披露（writing-skills） | R1 上下文面 | 写作工艺下沉 references/chapter_craft.md |

**明确不借鉴**：git 提交节奏/worktree（沙箱 markdown 无 git 语义，snapshot.py SHA-256 已覆盖）；TDD 红绿循环（门是基础设施不是每章要编写的对象）；双阶段 LLM 评审回路（失败模式是量不足不是质偏航，成本×2 留作后续选项）；技能链式调用协议（单技能内部 Phase 推进，无多技能路由问题）；dot 有向图（管线已有编号步骤+rc 路由）。

## 4. 架构

```
主 agent（控制器，薄上下文）
 ├─ 步骤1-3 不变（ingest → gate1 → formula_runner，含数据缺口 ask_clarification）
 ├─ 步骤4 = 派发协议（本设计核心）
 │    读 progress.py next → 组装派发 prompt → 每轮 ≤3 个 task() 并发
 │    → 子代理直写 state/chapters/chN.md，只返回 ≤10 行摘要
 │    → 控制器跑 build_output.py --chapter N 单章门
 │    → PASS: progress.py mark VERIFIED / FAIL: 原 prompt+门 stderr 重派（每章 ≤1 次）
 │    → 重派仍 FAIL: mark BLOCKED
 ├─ wave1（ch1-9）全 VERIFIED → 控制器蒸馏要点包写 state/key_points.json
 │    → 单张 ask_clarification 确认 → ch10 派发
 └─ 全 VERIFIED → build_output.py 终验 → BUILD_READY
    存在 BLOCKED → 降档协商 → --allow-partial 分级交付
```

## 5. 组件规格

### 5.1 `progress.py`（新脚本，~200 行）

命令面：

| 命令 | 行为 |
|---|---|
| `init --stage <path> --state-dir <dir>` | 按 stage 章节清单初始化 progress.json（全部 PENDING） |
| `next` | 输出恰好一个下一步动作：动作描述 + 精确命令 + 期望 rc。路由见下 |
| `status` | 全章状态表 + 派发计数 + 额度余量 |
| `mark <chN> <STATUS> [--gate PASS\|FAIL] [--detail ...]` | 状态转移（STATUS ∈ DRAFTED/VERIFIED/BLOCKED） |
| `approve-downgrade --chapters ch3,ch8 --note "..."` | 记录用户批准的降档（追加 downgrade_approvals） |

`next` 路由（状态机）：

- phase=WAVE1：首个 PENDING → 派发动作；首个 DRAFTED → 跑门动作；ch1-9 全 VERIFIED → phase=KEY_POINTS
- KEY_POINTS：key_points 未确认 → 表单动作；已确认 → 派发 ch10 → phase=WAVE2
- WAVE2：ch10 DRAFTED → 跑门；VERIFIED → phase=FINAL
- 存在 BLOCKED 且无批准 → NEGOTIATE（表单动作）；有批准覆盖全部 BLOCKED → FINAL 可 `--allow-partial`
- FINAL：全 VERIFIED → 终验 build；有批准 → 终验 build --allow-partial

`state/progress.json` schema（progress.py 唯一写者，防手改同 formula_state 惯例）：

```json
{
  "phase": "WAVE1|KEY_POINTS|WAVE2|NEGOTIATE|FINAL",
  "total_dispatches": 0,
  "chapters": {
    "ch1": {"status": "PENDING|DRAFTED|VERIFIED|BLOCKED",
             "dispatches": 0, "last_gate": null, "gate_detail": "",
             "blocked_reason": null}
  },
  "key_points_confirmed": false,
  "downgrade_approvals": [
    {"chapters": ["ch3"], "note": "用户批准 2026-08-28 对话确认", "approved_at": "..."}
  ]
}
```

### 5.2 `build_output.py` 加两个模式

**`--chapter N`**（单章全门，验证前置——不是复活 fail-fast：FAILED 章只影响该章，VERIFIED 章不动）：

- 复用 assemble 的章内校验块：validate_chapter（首行 `## N`、禁保留标题、手改检测）+ validate_depth（L1 含父节豁免）+ validate_toc + inject（槽位解析）+ validate_depth_target（L2，强制技能真基准）
- 章文件缺失 → 按未过门报「章节产物缺失」
- rc=0 PASS / rc=1 FAIL（该章错误一次报齐，格式同 93a71f4e2）
- **不写 progress.json**（唯一写者是 progress.py），只出 stdout/stderr + rc

**`--allow-partial`**（分级交付，D2 终态）：

- 前置校验：progress.json 的 downgrade_approvals 必须覆盖全部 BLOCKED 章，否则硬 FAIL 并指引协商流程；**任何章节产物缺失（含 PENDING 未派发）一律硬 FAIL**——降档交付的是「写了但深度不够」的章，不是「没写」的章
- 行为：跳过 BLOCKED 章的 L2 深度门（L0/L1/toc/槽位门仍在场），照常组装交付
- delivery_manifest 增逐章深度表：`{"chapter","effective_chars","target","ratio","status":"VERIFIED|DOWNGRADED"}` + downgrade_approvals 原文留痕
- rc=0，stdout 明示「分级交付：N 章降档」

### 5.3 `state/key_points.json`（新状态文件）

- wave1→wave2 要点包唯一事实源，不再活在会被摘要压缩掉的对话轮里
- **原料 = 各子代理摘要里的「本章要点 3-5 条」**（随章返回，见 §6 契约）+ formula_state 关键值——控制器只聚合 10 份 ≤10 行摘要，**不重读 9 章全文**（省 ~40k 字符主上下文）
- 字段：`{"chapters":{"ch1":[要点...]}, "highlights":{"资源量":"…","品位":"…"}, "issues":[...]}`
- 写者=控制器（步骤 4.5 write_file 落盘），内容经用户单表单确认后才可用于 ch10 派发
- 纳入 snapshot.py 哈希清单（progress.json 同）

### 5.4 `references/chapter_craft.md`（新参考文件）

- 内容=现 SKILL.md 步骤 4 的写作工艺迁移：逐要素成段、表后五步解读、判定词逐字、动笔前读深度目标、ch6 大章分节写作指引
- 用途：每个派发 prompt 注入节选（跨章风格统一锚）；主 SKILL.md 瘦身
- SKILL.md 原位置改为一句指向（条件句触发加载，防跳过：派发协议里硬性引用）

### 5.5 SKILL.md 步骤 4 重写（派发协议五要素）

1. **资格判定**：wave1 独立章（ch1-9）走子代理；要点包确认与 ch10 串行在 wave2；步骤 1-3 归主 agent
2. **冻结引用**：派发 prompt 指向沙箱路径（formula_state.json 槽位词汇表 / chapter_craft.md / chN_sample.md），子代理自读——**正文数值只写 `{{SLOT:key}}`，真数永不经过子代理**（比 water-drainage 冻结快照更强：零数值漂移）
3. **轮次硬写**：每轮至多 3 个并发 task()（超发被运行时静默丢弃）；总派发 ≤16（config 额度）；重派 >3 章 → 提前进协商
4. **类型与预算**：`subagent_type="general-purpose"`；单子代理 ≤150 轮/30min/1M token；结果剥 `Task Succeeded. Result: ` 前缀；单章失败重派或 BLOCKED，不中断全书
5. **父端收口**：子代理直写 `state/chapters/chN.md` 并只回 ≤10 行摘要；控制器跑门定夺（只信产物）；交付动作（present_files）归主 agent

**置顶 Iron Law**（代码块呈现）：

```
门 FAIL 只有两条合法出路：补写正文、申请用户降档。
编辑 references/ 或绕过 build_output CLI = 伪造基准，直接违反本技能红线。
```

**Excuse|Reality 表**（条目取自 03e18e4a 取证逐字）：

| Excuse | Reality |
|---|---|
| 「median_eff 目标不合理，我调一下基准」 | 基准=合同。唯一合法变更=用户批准+progress.py approve-downgrade 留痕 |
| 「直接调 assemble() 更快」 | 直调已被脚本拒（强制真基准）；CLI 是唯一门 |
| 「先跑通全流程，深度后面再补」 | 薄初稿是 03e18e4a 死循环起点；每章写够再进下一章 |
| 「一次修一章跑一轮 build」 | 单章门 `--chapter N` 即时验；终验一次报齐 |
| 「摘要里说这章写完了」 | 只信 state/chapters/*.md + progress.json，不信对话记忆 |

**Red Flags**：发现自己在编辑 references/、自造 depth_targets、想跳过单章门直跑终验、重派同一章第 3 次 → STOP，回协商表单。

frontmatter `description` 保持触发式不动（CSO 陷阱：写成流程概要会诱导 agent 照 description 走捷径不读正文）。

### 5.6 config.yaml 一行提额

`subagents.max_total_per_run: 16`（默认 6，clamp [1,50]；`subagents.*` 为每 run 热加载字段，改完下一条消息生效，无需重启）。10 初派 + 重派余量 6。

### 5.7 snapshot.py

progress.json 与 key_points.json 纳入哈希清单。

## 6. 数据流

**派发 prompt 契约**（每章一次，控制器组装；重派 = 原 prompt 原文 + 门 stderr 原文，不重新组装——防逐次漂移）：

```
角色：第 N 章撰写者，只产出这一章
自读输入（沙箱路径）：
  state/formula_state.json          ← 槽位词汇表（正文数值只写 {{SLOT:key}}）
  /mnt/skills/.../chapter_craft.md  ← 写作工艺
  /mnt/skills/.../samples/chN_sample.md ← 范文（仅范式；范文数值/矿名/地名禁入正文）
  本章切片（title+toc，直接贴）
输出契约：直写 state/chapters/chN.md（绝对沙箱路径），首行 ## N，缺数标 [待确认]/[数据未提供]
返回：≤10 行摘要（结构/[待确认]清单/数据缺口/**本章要点 3-5 条**——供要点包蒸馏）
禁令：不改 data/、不碰 references/、不跑 build、不派 task
```

**四流**：

1. 验证流：收章 → `--chapter N` → rc=0 mark VERIFIED；rc=1 重派（≤1 次）→ 仍 FAIL mark BLOCKED
2. 要点包流：wave1 全 VERIFIED → 蒸馏写 key_points.json → 单表单确认 → ch10 派发
3. 降档协商流：差距表（章/实际 eff/目标/缺口）→ 单表单三选项：补数据（回 ingest→formula_runner→相关章重派）/ 批准降档（approve-downgrade → --allow-partial）/ [待确认] 收尾（既有 coverage_scale 机制因 signals 放宽目标，重写即可能达标）
4. 断点流：任何中断（FORCED STOP/用户停止/上下文摘要压缩/新会话）→ progress.py next 从磁盘续，无损

## 7. 错误处理

| 故障 | 行为 |
|---|---|
| 单章门 FAIL | stderr 原文进重派，≤1 次 → BLOCKED → 协商 |
| 子代理超时/轮次熔断 | 只认磁盘产物：chN.md 完整 → 跑门定夺；不完整 → 按 FAIL 重派（同 ≤1 次） |
| 派发额度（16）耗尽 | 剩余 PENDING → BLOCKED → 协商或用户续跑新会话（progress 无损续） |
| 3 并发超发 | 运行时静默丢弃 → 协议硬写每轮 ≤3 |
| 章文件手改 | 既有手改检测（bug2223）在单章门与终验都在场 |
| 伪造基准/绕门 | 93a71f4e2 已硬化 + Iron Law + Excuse\|Reality |
| 重派 >3 章 | 提前进协商，不硬扛满额度 |
| 用户不回表单 | ask_clarification 挂起即停，不推进 |

**熔断算术**（死循环不可复发的论证）：主 agent 每章 ≈3 次工具调用（派发+跑门+mark），10 章初派 + 步骤 1-3 + 要点包表单 + 协商 ≈40 次；重派被「每章 ≤1 次、>3 章提前协商」钉在 ≤3 次 → +9 → **~49 次 < 60 次熔断线**。派发额度：10 初派 + ≤3 重派 = 13 ≤ 16 ✓。每子代理独立预算（150 轮/1M token/同工具 50 次窗口），单章 10.5k 字符（ch6 最大目标）一轮 write_file 富余。

## 8. 测试策略

| 层 | 内容 |
|---|---|
| 脚本单元 | `progress.py`：init/next 五态路由/mark 转移/approve-downgrade；`--chapter N`：PASS/FAIL/缺章/手改/伪造槽位；`--allow-partial`：无批准拒/有批准 rc=0+manifest 逐章标注+留痕 |
| e2e-full 压力 | 真实数据包全流程 + 薄章→FAIL→BLOCKED→approve→分级交付全链路（脚本模拟，无真 LLM） |
| 回归 | 既有 118 geo 测试全绿；snapshot 哈希新文件 |
| 页面测试（真验收） | e2e-full 数据包按 README §0 跑；标准=D1（可靠跑通+少量问询，无死循环/熔断/绕门） |
| 诚实盲区 | 派发协议的 agent 依从性（是否照轮次/真派发/照 prompt 契约）脚本无法断言，只有页面测试能验 |

## 9. 实施切分建议（给 writing-plans 的粒度提示）

1. `progress.py` + 单测（纯新增，零依赖）
2. `build_output.py --chapter N` + 单测（复用 assemble 校验块）
3. `--allow-partial` + manifest 深度表 + 单测
4. `references/chapter_craft.md` 迁移 + SKILL.md 步骤 4 重写（协议+Iron Law+Excuse|Reality+速查表）+ key_points 流程
5. snapshot.py 哈希扩展 + config.yaml 提额 + e2e-full 压力场景
6. 页面测试（用户执行，按 README §0）

## 10. plan 时核对项

- `subagents.max_total_per_run` 在本项目 config.yaml 的准确落点（源码已确认键名：`backend/packages/harness/deerflow/subagents/runtime.py:91-97`）
- 派发 prompt 模板是否单独落 `references/dispatch_template.md`（若 SKILL.md 里放不下）
