# 三层次架构图（L1/L2/L3）设计

日期：2026-09-01
状态：已与用户逐节确认（范围/L1L2 静态架构/L3 四子流程/6 张独立图/L2 分组链/L1 功能分层视角）

## 1. 目标与范围

在已完成并入库的 geological-report 技能架构图（`docs/geo-report-architecture.html`）基础上，细化绘制三层次架构图。**只做以下三个层次，不涉及其他技能**：

1. **L1** — eai-flow 系统整体功能架构（静态分层视图）
2. **L2** — eaiflow harness 架构（静态组件视图）
3. **L3** — geological-report 技能各子项具体设计流程（workflow × 4）

命名约定：框架名称统一用 **eaiflow**；`import deerflow.*`、包路径 `backend/packages/harness/deerflow/` 等代码级标识符在需要精确引用处保留原文。

工具链：archify skill（validate showcase → deliver → visual-check），全中文产出。

## 2. 产出物

```
docs/architecture/
  README.md                                    # 索引：三层下钻关系 + 链接表
  l1-system-architecture.html / .spec.json     # L1 系统功能分层
  l2-harness-architecture.html / .spec.json    # L2 harness 内部
  l3a-data-collection-gate1.html / .spec.json  # 步骤1 数据收集→门1 (workflow)
  l3b-freeze-calc-gate2.html / .spec.json      # 步骤2-3 冻结→门2 (workflow)
  l3c-dispatch-protocol.html / .spec.json      # 步骤4 派发协议 (workflow)
  l3d-recover-finalize-loop.html / .spec.json  # 步骤0+5-7+修改回路 (workflow)
  geo-report-architecture.html / .spec.json    # 已有图 git mv 入内（L3 总览层）
```

spec 命名模式：`<图名>.spec.json`。全部完成后一次 commit 到 main-dev-fork（含 git mv 与 README）。

## 3. 各图内容

### L1 系统功能分层（architecture，六层堆叠，≈12 节点 + 6 区域）

| 层 | 节点内容 |
|---|---|
| 接入 | nginx :2026（`/api/langgraph/*` 重写 → gateway；`/*` → 前端） |
| 前端 | Next.js :4000（workspace 对话 + extensions 管理端；cookie 认证 + extensions JWT 双体系；TanStack Query + useStream） |
| 应用 | Gateway FastAPI :8001（13 routers、RunManager、StreamBridge SSE、Cookie JWT + CSRF） |
| 框架 | **eaiflow harness**（单框，标注"→ L2 下钻"接续点） |
| 能力 | 3 原语：MCP 工具 · Skills（46 public + custom）· 子代理；extensions_config.json 热加载 |
| 数据 | Postgres 双库（agentflow / deerflow）、config.yaml、沙箱文件区 /mnt/user-data |

卡片（3 张以内）：harness/app 依赖方向铁律（app→deerflow 单向，测试守护）；3-layer 能力模型（能力必须经 MCP/Skills/子代理 3 原语到达 agent，否则是孤岛）；config 热加载。部署细节（docker 容器/端口）只在卡片文字带过，不画容器。

### L2 eaiflow harness（architecture，子系统 + 分组中间件链）

- **中枢**：Lead Agent（动态模型选择、工具加载、系统提示生成），注册于 langgraph.json
- **中间件链**：17+ 个按功能分 5 组，不逐个列出——安全组（Guardrails/ErrorHandling/ToolError）、上下文组（ThreadData/Uploads/Memory/ViewImage）、流程组（Summarization/TodoList/LoopDetection/Clarification/SubagentLimit）、记账组（TokenUsage/Title）、Sandbox
- **子代理**：双线程池（3 调度 + 3 执行），内置 general-purpose / bash；`task()` → SubagentExecutor → 后台线程 → SSE
- **周边子系统**：Tools、Sandbox（per-user `/mnt/user-data` 虚拟路径映射）、Models（动态选择）、MCP（managed providers）、Skills、Config（config.yaml 变更自动重载）
- **标注**：ThreadState 扩展 AgentState（sandbox/thread_data/artifacts/todos/uploads…）
- **接续点**：Skills/MCP/子代理原语框 → L3 下钻

### L3 四张 workflow（每张 ≤12 主节点，泳道按 用户 / 控制器 / 脚本 / 子代理 分区域）

| 图 | 主链 | 关键分支 / 回环 / 卡片 |
|---|---|---|
| l3a 数据收集→门1 | KF 三件套（真实调用 resolve_template → found=false 兜底声明 → 数据预告）→ ingest forms 生成表单 → 逐类收集（单回合一张卡、对象族按子键、>10 条引导 CSV）→ ingest 落盘（唯一写者）→ 门1 check | rc=2 缺项译中文清单回环补齐；GATE1_QUALITY warn 消化；卡片：示例值≠数据、崩溃即停 |
| l3b 冻结→门2 | chapter_planner manifest → formula_runner execute（Decimal HALF_EVEN、槽位 source 溯源）→ state/formula_state.json → 门2 | rc=3 anomalies 逐条确认（免打扰指令法定例外）；全 0/空 = 数据缺失即停；确认后冻结 |
| l3c 派发协议 | 读 progress.json → chapter_manifest → batch_task wave1 全扇出（每章写够再进下一章）→ wave2 结论 → chapters/chN.md 落盘 → 单章门 `--chapter N` | Iron Law 卡（门 FAIL 两条合法出路）；降档 approve-downgrade 分支留痕 |
| l3d 恢复+终验+修改回路 | snapshot show --verify（rc=3 篡改即停）→ build_output 槽位注入 → consistency 22 合约 → snapshot save SHA-256 → delivery_manifest → present_files 唯一交付物 | build 硬门（未知 SLOT FAIL/目录覆盖门/残留扫描/深度地板）；consistency FAIL 修章节回环；修改回路只落 chapters/ 重跑三连，禁改 outputs/ |

## 4. 制作工艺

每张图相同流程，串行执行：

1. **取证**：内容只从 CLAUDE.md / backend/docs/ARCHITECTURE.md / SKILL.md / 代码结构取，不编造；每张先出文字大纲给用户快速确认。
2. **绘 spec**：archify fast authoring 路径；自动路由优先，诊断驱动修复。
3. **质量门**：`validate --quality showcase`（9 检全过）→ `deliver`（SHA-256 回执）→ `visual-check`（1440/1600/1920/2048 四视口，浅+深）→ 读截图目检。
4. **入库**：全部完成后一次 commit 到 main-dev-fork（含 git mv geo 图 + README 索引）。

### 已知坑（复用自 geo 架构图经验）

- viewBox 宽度 ≤≈1230（1440 视口下图区仅 930px，缩放后 8px 小字不得低于 6px 投影）
- 节点 sublabel 不得超节点宽（过长触发自动缩字号 → 拖垮全图投影字号）
- 卡片 ≤3 张，防止第 4 张折行导致首屏溢出
- fan 边标签用 labelSegment 分散到入端垂直段
- 长回边用显式 via 走外围走廊（x=20 / 底部 y+50）

## 5. 错误处理

- validate 几何诊断：按诊断修复（标签位移/走廊让路/压缩 viewBox）；连续 2 轮无改善即如实报告，不硬凑。
- visual-check 溢出：先砍卡片/精简文字，不动语义标签。
- 内容与源文档冲突：以源文档为准，冲突点标记并问用户。

## 6. 验收标准（每张图）

- [ ] showcase validate 0 错误 0 警告
- [ ] visual-check 4 视口 containment pass（浅 + 深）
- [ ] 目检：无重叠、字号可读、布局平衡
- [ ] 内容抽查：节点/连线事实能在 CLAUDE.md / SKILL.md / ARCHITECTURE.md 找到出处
- [ ] README 三层下钻链接可用

## 7. 不做（YAGNI）

- 不画其他 45 个技能的任何图
- 不画 docker 容器/部署拓扑（方案 B 已否）
- 不做全管线大图 + guided views 下钻（文件少但密度不可控，已否）
- 不做索引页以外的导航设施（deep-link/iframe 嵌入等）
- 设计过程流程图（「架构怎么被设计出来的」）不做，只画静态架构
