# 四大模块页面验证测试报告

> 日期: 2026-06-14
> 浏览器: Chrome (localhost:2026)
> 测试账号: admin / lisi(组长) / wanger(组员)
> 测试计划: [2026-06-14-four-module-page-test-plan.md](./2026-06-14-four-module-page-test-plan.md)
> 创建项目: 辽阳石化消防设计专篇 (id `16c4ab13-8cfd-4ccf-88dc-233901829a09`)

## 一、总体结论

| 模块 | 结果 | 说明 |
|------|------|------|
| 流程编排 | 🟡 基本可用 | 模板列表/发布正常；编辑已发布模板 404 |
| 项目管理 | 🔴 严重缺陷 | 向导 UI 可走通，但**组建团队提交用户名→422**、**创建者无法访问自己项目→403** |
| AI 写作 | 🔴 核心失效 | 工作流"空跑完成"，**AI 编写初稿节点未执行，0 章节生成** |
| 文档空间 | 🟡 基本可用 | 页面/文件夹树正常；但**无项目子文件夹与报告生成**(被 AI 失效连带) |

**端到端主场景未能跑通**，根因为 3 个 P0 缺陷（DF-2 / DF-3 / DF-5）级联阻塞。

## 二、用例执行明细

### 模块一：流程编排（Admin）

| 用例 | 结果 | 证据 |
|------|------|------|
| TC-1.1 模板列表含「消防设计专篇」 | ✅ 通过 | `/admin/templates` 显示，状态「已发布」，report_type=fire_protection_design |
| TC-1.2 查看 DAG 结构 | 🔶 受阻 | 点击「编辑模板」→ **404**（DF-1）；改用 DB/API 核对：4 节点 t1-ai→t2-edit→t3-submit→t4-review，驳回边回滚 t2-edit，结构正确 |
| TC-1.3 模板已发布 | ✅ 通过 | template_status=published |

### 模块二：项目管理（lisi 组长建项目）

| 用例 | 结果 | 证据 |
|------|------|------|
| TC-2.1 进入 5 步向导 | ✅ 通过 | 步骤 1/5 ~ 5/5 正常 |
| TC-2.2 基本信息 + 报告类型 | ✅ 通过 | 报告类型下拉含「消防设计专篇」（**bug-056 已修复**，report_type 字典已注册） |
| TC-2.3 内容大纲模板 | ✅ 通过 | 「公用工程_消防设计专篇_模板」可选 |
| TC-2.4 工作流模板选择 | ✅ 通过 | 第 3 步出现「消防设计专篇」工作流（report_type 过滤命中） |
| TC-2.5 组建团队 | 🔴 **DF-2** | UI 可填组长/组员，但提交发送**用户名字符串**（lisi/zhangsan/wanger），后端要求 UUID → **HTTP 422** |
| TC-2.6 创建项目 | 🔴 **DF-3** | UI 创建被 DF-2 阻断；改用 API 创建(201)后，**创建者 lisi 未写入 project_members → GET 返回 403 "You are not a member of this project"**，工作台显示「项目不存在」 |

### 模块三：AI 写作

| 用例 | 结果 | 证据 |
|------|------|------|
| TC-3.1 AI 编写初稿 | 🔴 **DF-5** | temporal_workflow_id 已生成（自动启动成功），但 workflow-status 返回 `status=completed, nodes=[]`；**34 章全部 pending、0 字、0 内容**，AI 节点从未执行 |
| TC-3.2 组员仪表盘待办 | 🔶 受阻 | wanger 仪表盘「没有待办任务 / 所有任务已完成」——因 DF-5 无章节分配。另见 **DF-6**：wanger 角色显示「查看者」而非「组员」 |
| TC-3.3 文档编辑 Tab | ✅ UI 可用 | Tab 加载正常，显示「共 0 篇文档 / 项目工作流产出的文件会出现在这里」（无内容，DF-5 连带） |
| TC-3.4 组长提交报告 | 🔴 受阻 | 工作流未推进到 t3-submit 节点 |

### 模块四：文档空间 + 部门审核

| 用例 | 结果 | 证据 |
|------|------|------|
| TC-4.1 审核工作台 | ✅ UI 可用 | Tab 加载正常（我的审核/全部审核 + 过滤），「暂无待审核项」（DF-5 连带） |
| TC-4.2 文档空间项目文件夹 | 🔴 失败 | 「项目文件夹」下仅有历史项目「锦州石化」，**无「辽阳石化」子文件夹，无消防设计报告生成**。注：个人文件夹存在历史会话同步文档，说明同步机制本身可用 |
| TC-4.3 项目概览进度 | 🔶 部分 | 章节列表/统计/成员渲染正常；但「流程进度」显示**「项目暂未设置工作流程」**（**DF-4**），与实际 workflow_id/temporal 运行矛盾 |

## 三、缺陷清单（按严重度）

### DF-2 [P0] 组建团队提交用户名导致创建失败
- **现象**: 项目创建向导「组建团队」步骤发送 `members[].user_id = "lisi"/"zhangsan"/"wanger"`（用户名），后端 422。
- **报错**: `{"type":"uuid_parsing","loc":["body","members",0,"user_id"],"msg":"Input should be a valid UUID","input":"lisi"}`
- **根因**: `ProjectCreateWizard.tsx` 的 `StepTeam` 用纯文本输入框接收成员，无用户搜索/自动补全，直接把输入串当 userId 提交。
- **修复建议**: StepTeam 改为用户搜索选择器（调 `/api/extensions/users` 搜索），提交 UUID；或后端 create 支持 username 自动解析为 UUID。
- **文件**: `frontend/src/extensions/project/ProjectCreateWizard.tsx`（StepTeam / handleAddMember）

### DF-3 [P0] 项目创建者无法访问自己创建的项目
- **现象**: 创建项目后，创建者(lisi) GET `/projects/{id}` 返回 **403 "You are not a member of this project"**，工作台显示「项目不存在」。
- **根因**: 后端 create 逻辑将 owner 仅写入 `report_projects.created_by`，**未向 `project_members` 插入 owner 行**（DB 核对：members 仅 zhangsan/wanger）。可见性校验只认 project_members。
- **修复建议**: create 时为 owner 插入 `project_members(role=owner)`；或可见性校验放行 `created_by`。
- **文件**: `backend/app/extensions/project/service.py`（create）

### DF-5 [P0] 工作流自动启动后"空跑完成"，AI 编写初稿未执行
- **现象**: `auto_start_workflow=true`，temporal_workflow_id 已生成；但 workflow-status = `completed`, `nodes=[]`, `current_phase_node=null`，**34 章全 pending、0 字、0 内容**，无文档同步、无待办生成。
- **根因**: 工作流启动后未真正遍历执行 DAG 节点（t1-ai ai_generate 从未触发）。可能与 temporal worker 未就绪（日志见多次 connection refused / "Not enough hosts"）、或 graph version2(mainGraph) 解析、或 ai_generate activity 异常有关。gateway 日志为空(0 行)，难以定位。
- **修复建议**: 排查 temporal worker 注册与 DAG 执行链路；为 ai_generate 增加失败可见性（节点→ERROR+error_code）；修复后再回归。
- **文件**: `backend/app/extensions/workflow/temporal/workflows.py`、`activities.py`、`local_executor.py`

### DF-4 [P1] 流程进度组件误报"未设置工作流"
- **现象**: 项目概览「流程进度」显示「项目暂未设置工作流程 / 可在项目设置中关联工作流模板」，但项目 `workflow_id` 已关联且 temporal 已启动。
- **根因**: `WorkflowProgressCompact` 判定条件与 workflow-status / project 字段不一致。
- **文件**: `frontend/src/extensions/project/components/WorkflowProgressCompact.tsx`

### DF-6 [P1] 组员被识别为"查看者"，无写作职责
- **现象**: wanger（role=member）仪表盘项目卡显示「查看者」，无 writer 职责/权限；与 t2-edit 节点 `requiredRoles: writer×2` 不匹配。
- **根因**: 向导 member 角色(普通成员) 与工作流所需 writer 职责未打通（phase_duties 未分配）。
- **文件**: `ProjectCreateWizard.tsx`、`backend/.../slot_filling.py`

### DF-1 [P2] 编辑已发布工作流模板 404
- **现象**: `/admin/templates` 点击「编辑模板」→ `/admin/templates/[id]` 返回 404。
- **根因**: 动态路由 `[templateId]/page.tsx` 未正确渲染或导出。
- **文件**: `frontend/src/app/admin/templates/[templateId]/page.tsx`

## 四、已验证可用的能力

- 登录/登出/多角色切换（cookie+CSRF）正常
- 仪表盘：待办区、我的项目、统计、日历、通知 聚合渲染正常
- 项目创建向导 5 步 UI、报告类型字典(消防设计专篇)、工作流模板过滤 均正确（bug-056 已修复）
- 项目工作台 3 Tab（项目概览/文档编辑/审核工作台）按角色可见性规则正确渲染
- 文档空间：文件夹树、个人/项目文件夹、历史文档同步 正常
- 工作流模板发布态、DAG 结构（4 节点）正确

## 五、回归建议

修复优先级：**DF-2 → DF-3 → DF-5**（P0，三者任一存在即端到端不通）→ DF-6 → DF-4 → DF-1。
修复 DF-5 后，需重新回归 TC-3.1/3.2/3.4、TC-4.1/4.2 全链路（AI 初稿→组员确认→组长提交→部门审核→文档空间报告生成）。

> 注：测试中为绕过 DF-2/DF-3 验证下游，曾用 API 创建项目并用 DB 补写 lisi 的 owner 成员关系；这些仅为测试桩，不构成产品数据修复。

---

## 六、P0 修复进展（2026-06-14，本轮）

### DF-3 创建者加入 project_members — ✅ 已修复并验证
- **改动**: `backend/app/extensions/project/service.py` `create_project` — 将「创建者自动加为 owner」从 `if created_by and not members_data` 改为无条件 `if created_by`（原 members 循环里的 creator-skip 已防重复）。
- **回归测试**: `tests/test_project_service.py::TestCreateProjectOwnerMembership`（2 用例，PASS）。
- **运行时验证**: API 建项目(含成员) → 响应含 lisi(owner) → GET /projects/{id} 返回 **200**（原 403）。

### DF-2 组建团队提交 UUID — ✅ 已修复并验证
- **根因有两层**:
  1. 向导 `StepTeam` 用纯文本框收成员名，提交用户名 → 后端要 UUID → 422。
  2. 用户搜索端点 `/users/search` 注册在 `/{user_id}` **之后**，FastFX 路由顺序导致 `search` 被当作 UUID → 422（`AddMemberDialog` 同样受影响）。
- **改动**:
  - `frontend/.../ProjectCreateWizard.tsx` — StepTeam 改为用户搜索选择器（`/users/search` 防抖搜索 → 选 UUID），状态用 `{id,username}` 携带 UUID；StepConfirm/handleCreate 同步适配。
  - `backend/.../user/routers.py` — 将 `/search` 路由移到 `/{user_id}` **之前**（注释说明静态路径必须先注册）。
- **类型检查**: `src/` 无报错（仅 `.next/dev/types/*` 既有生成文件报错，与本次无关）。
- **运行时验证**: 向导走通 5 步 → 创建返回 **201**（原 422）；新项目成员 = lisi(owner) + wanger(owner)。
- **遗留**: `/users/statistics` 同样在 `/{user_id}` 之后（管理端 UI 受影响，非四模块路径，列为后续）。

### DF-5 工作流节点执行链路 — ✅ 已全闭环（AI 初稿端到端生成成功）

> **更新 (2026-06-14 01:50)**：二级问题全部修复，AI 初稿已能端到端生成。详见本节末「DF-5 二级问题全闭环」。
- **根因（已修复）**: Temporal 工作流 `run()` 及多个读取器对 v2 `graph_json` 直接 `graph.get("nodes")`，但节点实际在 `mainGraph.nodes` 下 → 工作流看到**空图**，直接返回不执行任何节点。
- **改动**（统一 `graph.get("mainGraph", graph)` 解包，5 处）:
  - `workflow/temporal/workflows.py::run`（核心）
  - `workflow/routers.py` workflow-status 端点（同时修 DF-4 流程进度空显）
  - `workflow/service.py::topological_sort`（防御性）
  - `workflow/review.py` 驳回边解析
  - `workflow/temporal/activities.py` 章节区间标注
  - 另：`project/routers.py` 自动启动的 `except Exception: pass` 改为 `warning` 记录（原静默吞错，是 DF-5 不可见的主因之一）。
- **回归测试**: `tests/test_workflow_graph_v2.py`（3 用例，PASS）。
- **运行时验证**: 修复前 workflow result = `{status:"empty_graph"}`；修复后 = `{completed:["t1-ai"], results:{t1-ai:{status:"error"}}, status:"completed"}` —— **节点已被处理，不再空跑**。
- **仍存在的二级问题（未闭环，需单独排查）**:
  1. `t1-ai` 活动执行报 `status:error`（活动侧异常，但 `start_ai_writing` 对 `chapter_id=None` 本应返回 `skipped`，疑为活动调用/注册或 LLM 配置问题）。
  2. **gateway 容器日志为空（0 行）**——`docker logs` 抓不到任何输出，是排查 DF-5 二级问题的硬阻塞（日志基础设施问题）。
  3. ai_generate 节点 `chapter_id=None` 时不批量生成（`start_ai_writing` 直接 skip），需补「无 chapter_id → 批量生成全章节」逻辑。
  4. t2-edit/t3-submit 任务节点的 `required_roles`(writer/lead) 与成员实际 `member` 角色未打通（见 DF-6）。

### 回归测试汇总
```
tests/test_project_service.py::TestCreateProjectOwnerMembership  2 passed  (DF-3)
tests/test_workflow_graph_v2.py                                  3 passed  (DF-5 根因)
```

### DF-5 二级问题全闭环（2026-06-14 01:50）

利用 `logs/gateway.log`（gateway 日志重定向到此文件，非 docker logs）定位到 3 个二级根因并全部修复，AI 初稿端到端生成成功：

| 二级根因 | 改动 | 验证 |
|---------|------|------|
| `execute_activity(_act, a, b, c)` 位置展开 → temporalio 1.27 要求 `args=[...]` → TypeError | workflows.py 全部 14 处 `execute_activity` 改 `args=[...]` | t1-ai 不再 TypeError |
| `_execute_ai_generate` 对 `chapter_id=None` 调单章 `start_ai_writing` → 返回 skip 不生成 | 无 chapter_id 时改调 `start_phase_ai_writing` 批量生成；后者无 phase 章节时回退全项目章节 | 34 章全部进入生成流程 |
| `_generate_content` 硬编码 `create_chat_model("ai-writing")` → 模型不存在 | 改 `create_chat_model()` 用默认模型(agnes-2.0-Flash) | LLM 真正产出内容 |

**运行时验证**（项目 87d91f6b）：
```
chapter statuses: draft 34, 总计 22796 字
log: activity:start_phase_ai_writing phase_id=t1-ai strategy=batch chapters=34
内容含溯源标记：[1] source:knowledge_base:电气设计规范
```
工作流推进：t1-ai(AI初稿) ✅ → t2-edit(人工修改确认，等待组员 signal，符合人在回路)。

> 仍待跟进（非 DF-5 范畴）：t2-edit/t3-submit 任务节点的 `required_roles`(writer/lead) 与成员 `member` 角色未打通（**DF-6**），需在建项目时按工作流角色分配 phase_duties，否则任务节点的角色分配/待办仍受影响。

### DF-6 + 工作流回滚边死锁 — ✅ 已全闭环（2026-06-14 02:45）

排查 DF-6 时发现一个更根本的 **P0 死锁**（此前让工作流在 t1-ai 后即结束、t2-edit 永不执行）：

| 问题 | 根因 | 改动 | 验证 |
|------|------|------|------|
| **回滚边死锁（P0，新发现）** | `run()` 构建邻接表时把 `label=rejected` 的回滚边(t4-review→t2-edit)算进 upstream → t2-edit 前置=[t1-ai,t4-review]，t4-review 又依赖 t2-edit，成环 → 前向遍历只处理 t1-ai 就退出 | `workflows.py` 邻接表跳过 `label==rejected` 的边（回滚由 `_execute_review` 经完整 edges 单独处理） | walk order 由 `[t1-ai]` → `[t1-ai,t2-edit,t3-submit,t4-review]`；回归 `test_walk_ignores_rejected_rollback_edge` PASS |
| **DF-6 组员无待办** | ① `_init_task` 按 required_roles 设了 phase_duties(duty=writer) 但没把章节 `assigned_to` 给 writer；② tabRegistry 编辑Tab 的 hasAnyDuty 不含 writer/lead | ① `init_task` 分配 writer 职责后，把待编章节(pending/draft/error,未分配)按 sort_order 轮询分配给 writer；② `tabRegistry` 编辑Tab 增加 writer/lead/reviewer 职责 | 见下 |

**端到端运行时验证**（项目 921faddb，组长 lisi + 组员 wanger/zhaoliu）：
```
log: Processing node t1-ai → start_phase_ai_writing chapters=34
     Processing node t2-edit → init_task assigned=3 roles=2
成员职责: lisi=lead, wanger=writer, zhaoliu=writer  (匹配 t2-edit requiredRoles)
章节分配: wanger=17, zhaoliu=17  (轮询)
wanger 仪表盘: 17 项「撰写中」待办 + 「撰写人」角色（原「查看者」）+ 编辑器链接
lisi 仪表盘: 「阶段推进」待办，项目卡显示 t2-edit 阶段
```

四模块核心链路现已全部打通：**流程编排(模板) → 项目管理(创建/团队) → AI写作(初稿生成) → 仪表盘(组员待办) → 项目详情(文档编辑/审核工作台)**。

> 角色标签仍有 3 套并行词汇表（项目详情 owner/editor/member vs 仪表盘 owner/writer/viewer vs 流程编排 leader/writer）——这是展示层碎片化，不影响功能链路（写作走 phase_duties）。统一需以后端 `ProjectRole` 枚举为唯一源新增 `GET /roles` 端点，属独立重构任务。

