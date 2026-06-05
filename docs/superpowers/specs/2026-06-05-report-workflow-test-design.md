# 报告项目全流程测试方案

**日期**: 2026-06-05
**状态**: 已批准
**测试项目**: 抚顺石化新装置消防设计报告编写项目
**部门**: 共用工程室

---

## 1. 测试环境

| 角色 | 姓名 | 账户 | 密码 |
|------|------|------|------|
| Admin（系统管理员） | — | admin@eai-flow.com | Admin@2026 |
| 主任（部门负责人/审批人） | zhangsan | zhangsan@eai-flow.com | Admin@2026 |
| 项目经理（PM/章节审核人） | lisi | lisi@eai-flow.com | Admin@2026 |
| 组员1 | wanger | wanger@eai-flow.com | Admin@2026 |
| 组员2 | zhaoliu | zhaoliu@eai-flow.com | Admin@2026 |

**系统地址**: http://localhost:2026

## 2. DAG 工作流定义

使用 Temporal DAG 工作流引擎（非 Legacy 审批链）。

```
Node1[AI生成初稿] → Node2[人工编辑/确认] → Node3[PM审核&提交] → Node4[主任审批] → Node5[完成]
                          ▲                         │
                          └───── 驳回退回到此 ◄───────┘
                          ▲                         │
                          └───── 驳回退回到此 ◄───────┘ (Node4也退回到此)
```

### 节点定义

| 节点 | DAG类型 | 执行者 | 章节状态 | 项目状态 |
|------|---------|--------|---------|---------|
| Node1 AI生成初稿 | ai_generate | lisi(lead) | pending→draft | setup→outline |
| Node2 人工编辑/确认 | phase | wanger,zhaoliu,lisi(writer) | draft→completed | writing |
| Node3 PM审核&提交 | review | lisi(reviewer) | completed→approved 或退回draft | editing |
| Node4 主任审批 | review | zhangsan(approver) | approved→signed 或退回draft | approval |
| Node5 完成 | end | — | — | completed |

### 退回规则

- Node3(PM审核)驳回 → 退回Node2(人工编辑/确认)
- Node4(主任审批)驳回 → 退回Node2(人工编辑/确认)

### 阶段职责分配

| 成员 | Node1 | Node2 | Node3 | Node4 |
|------|-------|-------|-------|-------|
| lisi（项目经理） | lead | writer | reviewer | — |
| wanger（组员1） | — | writer | — | — |
| zhaoliu（组员2） | — | writer | — | — |
| zhangsan（主任） | — | — | — | approver |

## 3. 页面地图

```
/login                          → 登录页
/dashboard                      → 工作台
/projects                       → 报告项目列表
/projects/new                   → 新建项目向导
/projects/[id]                  → 项目工作区
  ├─ [项目概览] tab             → 统计、章节进度、成员管理、阶段推进
  ├─ [文档编辑] tab             → 章节列表、协同编辑器、AI生成
  └─ [审核工作台] tab           → 审核队列、通过/驳回操作
/admin/templates                → 流程管理（工作流模板）
/admin/users                    → 用户管理
/admin/departments              → 部门管理
/output                         → 报告输出
```

## 4. 覆盖维度

| 标记 | 维度 | 关注点 |
|------|------|--------|
| DF | 数据流 | 数据在不同节点间传递是否完整一致 |
| SF | 状态流 | 状态转换是否正确、是否有非法转换 |
| WF | 工作流 | 流程节点推进是否符合业务规则 |
| RB | 角色权限 | 各角色只能执行授权操作 |
| CO | 多角色协同 | 多人操作不冲突、变更可追溯 |

## 5. 完整测试用例

### 阶段一：Admin 系统准备（admin@eai-flow.com）

#### TC-1.1 Admin 登录
- **用户**: admin@eai-flow.com
- **页面**: `/login` → `/dashboard`
- **操作**: 输入邮箱密码，点击登录
- **检查点**: ① 跳转到工作台 ② 侧边栏可见「系统管理」
- **维度**: DF

#### TC-1.2 确认用户与部门
- **用户**: admin@eai-flow.com
- **页面**: 侧边栏→「系统管理」→ `/admin/users`
- **操作**: 搜索 zhangsan、lisi、wanger、zhaoliu
- **检查点**: ① 4个用户存在 ② 所属共用工程室 ③ zhangsan为部门负责人
- **维度**: DF

#### TC-1.3 确认部门信息
- **用户**: admin@eai-flow.com
- **页面**: 顶部导航→「部门管理」→ `/admin/departments`
- **操作**: 查找「共用工程室」
- **检查点**: ① 部门存在 ② 负责人=zhangsan ③ 成员列表正确
- **维度**: DF

#### TC-1.4 创建/配置 DAG 工作流模板
- **用户**: admin@eai-flow.com
- **页面**: 顶部导航→「流程管理」→ `/admin/templates` → `/admin/templates/new`
- **操作**:
  1. 创建模板：「消防设计报告工作流」
  2. DAG编辑器添加5个节点（ai_generate→phase→review→review→end）
  3. 连线+退回边（Node3→Node2, Node4→Node2）
  4. 配置 required_roles
  5. 保存
- **检查点**: ① 模板保存成功 ② DAG图正确
- **维度**: WF, DF

#### TC-1.5 发布工作流模板
- **用户**: admin@eai-flow.com
- **页面**: `/admin/templates`
- **操作**: 点击模板的「发布」
- **检查点**: ① 状态变为「已发布」
- **维度**: WF, SF

#### TC-1.6 非Admin无权限
- **用户**: lisi@eai-flow.com
- **页面**: `/dashboard`
- **操作**: lisi查看侧边栏，尝试访问 `/admin/templates`
- **检查点**: ① 无「系统管理」菜单 ② `/admin/*` 被拒绝
- **维度**: RB

### 阶段二：项目经理创建项目（lisi@eai-flow.com）

#### TC-2.1 PM 登录
- **用户**: lisi@eai-flow.com
- **页面**: `/login` → `/dashboard`
- **检查点**: 跳转工作台，侧边栏有「报告项目」
- **维度**: DF

#### TC-2.2 进入项目列表
- **用户**: lisi@eai-flow.com
- **页面**: 侧边栏→「报告项目」→ `/projects`
- **检查点**: 项目列表页正常显示
- **维度**: DF

#### TC-2.3 创建新项目
- **用户**: lisi@eai-flow.com
- **页面**: `/projects` → `/projects/new`
- **操作**: 填写项目名称、部门、报告类型、工作流模板
- **检查点**: ① 创建成功跳转到 `/projects/[id]` ② 状态=setup ③ 模板已关联
- **维度**: DF, SF, WF

#### TC-2.4 添加成员并分配阶段职责
- **用户**: lisi@eai-flow.com
- **页面**: `/projects/[id]` → 「项目概览」→ 成员管理
- **操作**: 添加 zhangsan(approver)、wanger(writer)、zhaoliu(writer)，lisi 自动为 owner
- **检查点**: 成员4人，职责分配正确
- **维度**: DF, RB, WF

#### TC-2.5 确认项目初始状态
- **用户**: lisi@eai-flow.com
- **页面**: `/projects/[id]` → 「项目概览」
- **检查点**: ① 状态=setup ② 工作流在Node1 ③ 成员完整 ④ required_roles满足
- **维度**: SF, DF

### 阶段三：AI 生成初稿（lisi@eai-flow.com）

#### TC-3.1 创建章节大纲
- **用户**: lisi@eai-flow.com
- **页面**: `/projects/[id]` → 「文档编辑」
- **操作**: 创建5个章节（项目概述、设计依据、系统设计、设施配置、结论建议）
- **检查点**: ① 章节树正确 ② 状态=pending
- **维度**: DF

#### TC-3.2 分配章节给组员
- **用户**: lisi@eai-flow.com
- **页面**: `/projects/[id]` → 「文档编辑」
- **操作**: 第3章→wanger，第4章→zhaoliu，其余→lisi
- **检查点**: 负责人标签显示正确
- **维度**: DF, CO

#### TC-3.3 触发 AI 生成初稿
- **用户**: lisi@eai-flow.com
- **页面**: `/projects/[id]` → 「文档编辑」
- **操作**: 点击AI生成按钮，等待完成
- **检查点**: ① 状态pending→draft ② 内容非空 ③ 项目推进到outline
- **维度**: DF, SF, WF

#### TC-3.4 组员无法触发 AI
- **用户**: wanger@eai-flow.com
- **页面**: `/projects/[id]` → 「文档编辑」
- **操作**: 尝试点击AI生成
- **检查点**: 按钮不可见/禁用，API返回403
- **维度**: RB

### 阶段四：人工编辑/确认（wanger、zhaoliu、lisi）

#### TC-4.1 组员1查看任务
- **用户**: wanger@eai-flow.com
- **页面**: `/projects/[id]` → 「项目概览」
- **检查点**: ① 角色显示writer ② 第3章分配给自己 ③ 工作流在Node2
- **维度**: DF, RB

#### TC-4.2 组员1编辑章节
- **用户**: wanger@eai-flow.com
- **页面**: `/projects/[id]` → 「文档编辑」→ 第3章
- **操作**: 修改完善内容，保存
- **检查点**: 保存成功，内容更新
- **维度**: DF, CO

#### TC-4.3 组员1标记完成
- **用户**: wanger@eai-flow.com
- **页面**: 仍在第3章
- **操作**: 点击「标记完成」
- **检查点**: 第3章状态 draft→completed
- **维度**: SF

#### TC-4.4 组员2编辑并完成
- **用户**: zhaoliu@eai-flow.com
- **页面**: `/projects/[id]` → 「文档编辑」→ 第4章
- **操作**: 编辑→保存→标记完成
- **检查点**: 第4章 draft→completed
- **维度**: DF, SF, CO

#### TC-4.5 PM编辑自留章节
- **用户**: lisi@eai-flow.com
- **页面**: `/projects/[id]` → 「文档编辑」
- **操作**: 编辑第1、2、5章并标记完成
- **检查点**: 5章全部 completed
- **维度**: DF, SF, CO

#### TC-4.6 组员无法编辑他人章节
- **用户**: wanger@eai-flow.com
- **页面**: `/projects/[id]` → 「文档编辑」
- **操作**: 尝试编辑第4章
- **检查点**: 按钮禁用或提示无权限
- **维度**: RB

#### TC-4.7 组员无法审核/审批
- **用户**: wanger@eai-flow.com
- **页面**: `/projects/[id]`
- **操作**: 查看审核工作台tab，尝试审核操作
- **检查点**: tab不可见或按钮不可用
- **维度**: RB

### 阶段五：PM 审核 & 提交（lisi@eai-flow.com）

#### TC-5.1 PM进入审核工作台
- **用户**: lisi@eai-flow.com
- **页面**: `/projects/[id]` → 「审核工作台」
- **检查点**: ① 审核队列显示5章(completed) ② 工作流在Node3
- **维度**: DF, WF

#### TC-5.2 PM逐章审核通过
- **用户**: lisi@eai-flow.com
- **页面**: 「审核工作台」
- **操作**: 逐章查看内容→点击通过
- **检查点**: ① completed→approved ② 审核记录完整 ③ 5章全过后推进到Node4
- **维度**: SF, WF, DF

#### TC-5.3 PM提交审批
- **用户**: lisi@eai-flow.com
- **页面**: 「审核工作台」
- **操作**: 点击「提交审批」
- **检查点**: ① 推进到Node4 ② 项目状态=approval ③ 通知zhangsan ④ 审批记录创建
- **维度**: SF, WF, CO

#### TC-5.4（备选）PM审核驳回
- **用户**: lisi@eai-flow.com
- **页面**: 「审核工作台」
- **操作**: 驳回第3章，填写意见
- **检查点**: ① 第3章completed→draft ② 工作流退回Node2 ③ wanger收到通知
- **维度**: SF, WF, CO

#### TC-5.5（备选）驳回后组员重编辑
- **用户**: wanger@eai-flow.com → lisi@eai-flow.com
- **操作**: wanger重新编辑第3章→标记完成→lisi重新审核通过
- **检查点**: 完整退回→修改→重审路径畅通
- **维度**: SF, CO, WF

#### TC-5.6 审批阶段无法归档
- **用户**: lisi@eai-flow.com
- **页面**: 「项目概览」
- **操作**: 尝试归档
- **检查点**: 归档按钮不可用
- **维度**: RB, SF

### 阶段六：部门负责人审批（zhangsan@eai-flow.com）

#### TC-6.1 主任查看待审批
- **用户**: zhangsan@eai-flow.com
- **页面**: `/login` → `/projects` → `/projects/[id]` → 「审核工作台」
- **检查点**: ① 项目卡片有审批中标记 ② 审核工作台有待审批内容
- **维度**: DF, CO

#### TC-6.2 主任查看报告（只读）
- **用户**: zhangsan@eai-flow.com
- **页面**: 「文档编辑」tab
- **操作**: 逐章查看内容
- **检查点**: ① 内容可查看 ② 无法编辑
- **维度**: DF, RB

#### TC-6.3 主任审批通过
- **用户**: zhangsan@eai-flow.com
- **页面**: 「审核工作台」
- **操作**: 通过，填写意见，确认
- **检查点**: ① 审批=approved ② 推进Node5 ③ 项目=completed
- **维度**: SF, WF, CO

#### TC-6.4（备选）主任审批驳回
- **用户**: zhangsan@eai-flow.com
- **页面**: 「审核工作台」
- **操作**: 驳回，填写原因
- **检查点**: ① 审批=rejected ② 退回Node2 ③ 通知PM和组员
- **维度**: SF, WF, CO

#### TC-6.5（备选）驳回后完整回退路径
- **用户**: zhaoliu → lisi → zhangsan
- **操作**: 组员修改→PM重审→提交→主任再审批
- **检查点**: ① 全流程畅通 ② 状态流转正确 ③ 两轮审批历史完整
- **维度**: SF, WF, CO, DF

#### TC-6.6 非审批人无法审批
- **用户**: wanger@eai-flow.com
- **页面**: 「审核工作台」
- **操作**: 尝试通过/驳回
- **检查点**: 无审批按钮或按钮不可用
- **维度**: RB

### 阶段七：Word 报告生成与归档（lisi@eai-flow.com）

#### TC-7.1 生成 Word 报告
- **用户**: lisi@eai-flow.com
- **页面**: 「项目概览」或「文档编辑」
- **操作**: 点击「生成报告」/「导出Word」
- **检查点**: 生成进度显示，完成提示出现
- **维度**: WF

#### TC-7.2 下载验证内容
- **用户**: lisi@eai-flow.com
- **操作**: 下载Word文件并检查
- **检查点**: ① 文件可打开 ② 含目录+5章完整 ③ 内容一致
- **维度**: DF

#### TC-7.3 验证报告格式
- **操作**: 检查排版细节
- **检查点**: 字体、标题层级、表格、页面布局符合模板
- **维度**: DF

#### TC-7.4 项目归档
- **用户**: lisi@eai-flow.com
- **页面**: 「项目概览」
- **操作**: 点击「归档」
- **检查点**: 状态变为 archived
- **维度**: SF, WF

#### TC-7.5 归档后只读
- **用户**: lisi@eai-flow.com
- **页面**: 「文档编辑」
- **操作**: 尝试编辑章节
- **检查点**: 编辑器只读，按钮禁用
- **维度**: RB, SF

## 6. 执行策略

| 轮次 | 范围 | 时长 | 目标 |
|------|------|------|------|
| 第1轮 | TC-1.1→7.5 正向主流程 | ~90min | 全流程畅通 |
| 第2轮 | 权限反向测试 | ~30min | 权限隔离 |
| 第3轮 | 驳回退回路径 | ~45min | 异常路径 |

## 7. 缺陷等级

| 等级 | 定义 |
|------|------|
| 🔴 阻塞 | 流程卡死无法继续 |
| 🟠 严重 | 功能不正确 |
| 🟡 一般 | UI/体验问题 |
| 🔵 建议 | 优化建议 |
