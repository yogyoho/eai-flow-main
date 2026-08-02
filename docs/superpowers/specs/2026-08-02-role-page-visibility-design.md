# 角色管理 · 子页面可见性控制设计

> 日期：2026-08-02 | 状态：草稿
> 背景：角色管理"操作控制"tab 目前是三级结构（主页面→子页面→操作）。主页面（模块）有"模块可见"开关，但**子页面级没有可见性控制**——只能控制"某个操作有没有"，无法控制"某个子页面 tab 让不让看"。

## 1. 现状与缺口

| 层级 | 现有控制 | 缺口 |
|---|---|---|
| 主页面（模块） | "模块可见"开关 → 写 `nav`，控制侧边栏入口 | — |
| 子页面（页面/tab） | 无 | **无法控制子页面 tab 显隐**；0 操作页面（版本管理、分组审核、任务中心）无任何控制手段 |
| 操作 | 复选框 | — |

**数据层现状**：角色的 `pages` 字段（page id 列表）已存在于 permissions.yaml 角色默认（`pages: [...]` 或 `pages: ["*"]`）；`/me` 已返回并展开 `*`；前端 `canPage(pageId)` 已实现。但：
- `canPage` 目前**只有 settings 页在消费**（`frontend/src/app/settings/page.tsx:26`）——知识工厂 9 tab、合同价格 6 子视图都没按页面可见性过滤。
- 角色管理 UI 没有写入 `pages` 的控件（RoleUpdate schema 无 `pages` 字段，写透未处理）。

## 2. 目标

1. 角色管理 UI 增加**子页面级"可见"开关**（方案 A：显式，与模块级开关同款）。
2. 子页面可见性**持久化**到 overlay `pages` 字段。
3. **接线到实际 tab 渲染**：知识工厂、合同价格的 tab 按 `canPage` 过滤。

## 3. 设计方案

### 3.1 UI：每子页面一个"可见"开关（已与用户确认）

三级面板展开后，每个子页面行 = `页面名 + [可见/不可见 开关] + (n/m 计数)`，**开关紧跟页面文字，左侧排列不右对齐**（用户明确要求）。

- 开关状态来源：角色的 `pages` 列表（含 `*` 展开）；页面 id 在 pages 中 = 可见。
- 开关写入：切到不可见 → 把该 page id 从 pages 移除；切回 → 加回。

**子页面设为不可见时的操作处理**（用户选 A）：
- 该页操作**置灰 + 不可点**，但勾选值**保留**（不撤销权限配置）。
- 恢复可见后操作自动生效。
- 提示文案："操作保留（n 项）· 恢复可见后自动生效"。

**0 操作页面**（如 `kf:page:version`、`cpa:page:clusters`、`cpa:page:tasks`）：
- 只渲染页面名 + 开关 + "无操作项 · 仅控制 tab 显隐"，可单独显隐（方案 A 相对方案 B 的核心优势）。

**模块级可见 vs 子页面级可见**：
- 模块不可见 → 侧边栏入口消失，其下子页面 tab 自然不可达（dormant，不特殊处理）。
- 模块可见但某子页面不可见 → 该 tab 隐藏，其余 tab 正常。

### 3.2 数据模型

- **`RoleUpdate` schema** 增加 `pages: list[str] | None = None`。
- **`update_role` 写透** 处理 `data.pages` → overlay entry 的 `pages`（与 nav/permissions 同路径）。
- **默认兼容**：`pages: ["*"]` 角色（superadmin/dept_head/project_manager）→ 所有子页面可见，前端每页开关默认 ON。管理员首次切关某页 → 写显式列表 = 该模块全部 page id 去掉被关页（`*` 在 `/me` 已展开为全部 page id，前端可据此推导）。
- `RoleResponse` 补 `pages`（供前端角色详情读取当前页面可见性）。`to_response` 从 registry 合并。

### 3.3 canPage 接线范围

子页面可见性必须在实际 tab 渲染生效（否则配了不生效）。需要接线的多 tab 模块：

| 模块 | tab 结构 | page id 映射 | 现状 |
|---|---|---|---|
| 知识工厂 | `TabNavigation.tsx` 9 tab（样例/模板抽取/模板编辑/法规/合规/版本/质量/爬取/字典） | `TabId`→`kf:page:*`（见下） | 未接 |
| 合同价格 | `app/contract-price/layout.tsx` 6 子路由（总览/合同解析/分项校验/分组审核/任务中心/配置） | →`cpa:page:{overview,contracts,items,clusters,tasks,settings}` | 未接 |
| 设置 | `app/settings/page.tsx` | 已接 `canPage` | ✅ |
| 其他模块（项目/文档/知识库/写作/工作台） | 单页无 tab | 无需接线（模块级可见已覆盖） | — |

**知识工厂 tab→page 映射**（9 tab vs 8 page id，需实现时确认）：
- `reports`(样例管理)→`kf:page:sample`；`editor`(模板编辑)→`kf:page:template`；`law`→`kf:page:law`；`rules`(合规)→`kf:page:compliance`；`version`→`kf:page:version`；`quality`→`kf:page:quality`；`scraper`(网页爬取)→`kf:page:scrape`；`dictionaries`(业务字典)→`kf:page:dict`
- `extraction`(模板抽取) 无独立 page id → 实现时二选一：(a) 映射到 `kf:page:sample`（共享）；(b) permissions.yaml 补一个 `kf:page:extraction`。

**接线方式**：`TabNavigation` / `contract-price/layout` 的 tab 数组生成处，用 `usePermission().canPage(pageId)` 过滤；不可见的 tab 不渲染。隐藏 tab 由路由守卫（后端 require_permission）兜底。

## 4. 边界与错误处理

- **`pages: ["*"]` 展开**：`/me` 已把 `*` 展开为全部 page id；前端开关状态据此推导。写透时若整个 pages 等于全量，可写回 `["*"]` 保持简洁（可选优化）。
- **并发写**：沿用 overlay 原子写 + mtime 乐观锁（409）。
- **未知 page id**：服务端写透时校验 page id 存在于 registry（类似 data_scopes 的 `get_data_scope` 校验），未知 id 拒绝。
- **隐藏页的深层链接**：tab 不渲染但路由仍可直达 → 后端操作权限照常校验（隐藏 ≠ 撤销操作）。

## 5. 文件清单

**后端：**
- `backend/app/extensions/schemas.py` — `RoleUpdate.pages` + `RoleResponse.pages`
- `backend/app/extensions/role/service.py` — `update_role` 写透 pages、`to_response` 合并 pages、page id 校验
- `backend/app/extensions/auth/registry.py` — （如需）`get_page_ids_for_role` 已存在；`page_ids` 写透已由 service 处理

**前端：**
- `frontend/src/app/admin/roles/page.tsx` — PermissionPanel 增加子页面"可见"开关（紧跟页面文字）、置灰逻辑、页面级 n/m 计数；`initPageVisibility` 状态初始化
- `frontend/src/extensions/knowledge-factory/TabNavigation.tsx` — tab 数组按 `canPage(pageId)` 过滤（+ TabId→pageId 映射）
- `frontend/src/app/contract-price/layout.tsx` — 子路由导航按 `canPage` 过滤
- `frontend/src/extensions/types.ts` — `Role.pages`、`UpdateRoleRequest.pages`

**配置：**
- `config/permissions.yaml` — （如需）补 `kf:page:extraction` 或确认映射

## 6. 测试

- 后端：`update_role` 写透 pages（含 `*`→显式列表转换）、page id 校验拒绝未知、`to_response` 合并 pages。
- 前端：vitest 单测页面开关状态推导（`pages:["*"]` 全开、显式列表、切关生成列表）；知识工厂/合同价格 tab 过滤逻辑（纯函数可测）。
- 手动：admin 关闭项目经理某子页面 → 刷新后 tab 不渲染、开关保持关；恢复可见后操作恢复。

## 7. 非目标 / 延后

- 子页面可见性与操作权限的**更细粒度解耦**（隐藏页操作是否随模块隐藏失效）——本设计保持操作独立授权。
- 其他单页模块的 tab 化拆分。
