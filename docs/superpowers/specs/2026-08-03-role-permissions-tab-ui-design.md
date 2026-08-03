# 角色管理 · 操作权限 Tab UI/UE 改进 + 插件市场下线

> 日期：2026-08-03 | 状态：已批准
> 范围：`/admin/roles` 页「操作权限」tab 的 UI/UE 重构 + 数据层权限点错配修复 + 插件市场全栈下线

## 1. 背景与现状

「操作权限」tab 现有 4 个 tab（操作权限 / 数据权限 / 自定义策略 / 关联用户），操作权限 tab 提供列表视图（三级树：模块 → 子页 → 操作）与只读矩阵概览两种视图。经审计发现三类问题：

1. **UI/UE**：三级树对单页模块冗余（8/12 模块只有 1 个 page，中间"子页"层是噪音）；模块级与子页级可见性都用 Switch 造成语义混淆；面板过长无搜索；`app_center` 模块无权限点却始终展示。
2. **数据层错配**：`permissions.yaml` 声明与后端 `require_permission()` 实际强制不一致，UI 能配的操作不生效、后端强制的操作 UI 配不到。
3. **插件市场半下线**：前端入口已注释下线（"插件系统容器化改造中"）、前端 API 基址 `/plugins` 断裂调不通，从未实际启用。

## 2. 目标

- 操作权限 tab 面板改为「方案 A 卡片树精修」：单页模块折叠两级、子页可见性改用状态 Tag、隐藏 app_center、新增搜索与展开/收起工具条。
- 修复 permissions.yaml 与后端强制的错配（补缺 / 删冗余 / 改错位）。
- 全栈删除插件市场（前端组件、后端路由、模型、seed、测试、DB 表）。
- 矩阵概览保留并做视觉微调（不动结构）。

## 3. 设计

### 3.1 删除插件市场（全栈）

**后端**（`backend/app/extensions/plugin/` 整个模块删除）：
- `routers.py` / `service.py` / `schemas.py` / `seed.py` / `builtin/` / `__init__.py`
- `models/__init__.py:912-975` — `Plugin` / `PluginInstance` / `PluginApiKey` 三个模型类
- `gateway/app.py:26,602` — `plugin_router` import + `app.include_router(plugin_router)`
- `database.py:1566-1570` — `seed_builtin_plugins` 调用块
- 测试删除：`test_plugin_mcp_wiring.py` / `test_plugin_models.py` / `test_plugin_routers.py` / `test_plugin_service.py`

**前端**：
- `frontend/src/extensions/plugin/` 整个模块
- `frontend/src/app/plugins/page.tsx`（孤儿路由，无导航链接）
- `settings/page.tsx` — 删 `import PluginMarketplace`（L10）+ 注释掉的嵌入块（L87-99）

**DB**：
- `eai-flow-postgres-ext`（DB `agentflow`）执行：
  ```sql
  DROP TABLE IF EXISTS plugin_api_keys;
  DROP TABLE IF EXISTS plugin_instances;
  DROP TABLE IF EXISTS plugins;
  ```
  已确认三表存在。DB 用 `create_all`（无 alembic），删模型后新库不再建表；此处手动 DROP 清理既有表。

**影响面**：`sync_mcp_registration` 仅被 `plugin/service.py` 内部调用；app-center 用独立 `app_center/models.py` 不引用 plugin；`skill:*` 不在 yaml 中（删除后权限点不存在，无需补）。经全库 grep 无其他引用方。

### 3.2 数据层权限点错配修复（permissions.yaml）

| 操作 | 位置 | 说明 |
|---|---|---|
| 改 | `workflow_admin` 模块：删 `workflow:start/cancel/edit` 三项，加一项 `project:advance`（display_name="推进工作流"，语义覆盖启动/信号/取消三个动作，避免三个按钮配同一把锁的误导） | 后端 `workflow/permissions.py` 的 WORKFLOW_START/SIGNAL/CANCEL 全部用 `project:advance` 强制，旧三项配了不生效 |
| 补 | `projects` 模块：加 `chapter:view_all`（"查看全部章节"）、`ai:stop_writing`（"停止 AI 写作"） | 后端强制（`workflow/permissions.py` SOURCE_READ / `role_permission.py`）但 UI 配不到 |
| 删 | 合同价格 `cpa:cluster` / `cpa:export` | 后端只用 `cpa:read`/`cpa:import` 强制，此两项从不检查 |
| 删 | `source:view` | 实际强制的是 `chapter:view_all` |

**不处理**（在模块树范围外，本轮不动）：`chapter:edit`、`chapter:confirm`、`runs:*`、`threads:*` 等——属项目内协作/运行系统权限，需后续单独设计归属。

### 3.3 操作权限面板 UI（方案 A 卡片树精修）

```
[全选][清空]  🔍搜索操作   [全部展开][全部收起]
┌─ 报告项目 ──────────── [8/24] ▾ 全选本组 ┐
│ 项目列表   ◉可见 (8/24)                 │
│ ☑创建 ☑编辑 ☐删除 ☐加成员 ☐移除成员…      │
└─────────────────────────────────────────┘
┌─ 知识工厂 ──────────── [3/9] ▾ 全选本组  ┐
│ 模块可见 [●──────○]                     │
│ ▸ 样例管理/模板抽取  ◉可见 (1/3)         │
│ ▸ 模板抽取          ◉可见 (1/1)         │
│ ▸ 合规规则          ◌不可见 (0/1)        │
└─────────────────────────────────────────┘
```

具体改动：

1. **单页模块折叠两级**：模块只有 1 个 page（`dashboard`/`writing`/`projects`/`docmgr`/`knowledge`/`output`/`workflow_admin`）→ 主页卡片直接展开操作项网格，不渲染中间"子页"行。子页可见性由模块可见开关控制（单页无独立显隐）。多页模块（`knowledge_factory` 9 页、`contract_price` 6 页、`admin` 4 页、`settings` 3 页）保留三级。
2. **子页可见性改用状态 Tag**：`◉可见`（主色圆点）/ `◌不可见`（灰点）文字 Tag，点击切换；模块级保留 Switch。两级控件彻底区分，消除"模块可见 vs 子页可见"都是 Switch 的混淆。
3. **隐藏 `app_center` 模块卡片**：始终可见、无可配权限，列表视图与矩阵视图都不再展示该模块行。
4. **顶部工具条**：新增 `🔍 搜索操作`（跨模块过滤，输入即展开匹配模块并高亮操作项）+ `全部展开 / 全部收起`（批量切换展开态）。
5. **只读态**：系统角色（`is_system`）整体置灰、禁用交互，保留"系统角色权限为只读"提示。
6. **矩阵概览**：保留右上角列表/矩阵切换，视觉微调（列对齐、斑马纹、模块计数角标），不做结构改动。

### 3.4 交互与状态

- **保存**：维持即时保存（每次勾选即 `roleApi.update(...)`，失败 `alert`）。不引入批量保存/防抖/撤销。
- **搜索**：输入 → 匹配操作所在模块自动展开并高亮；清空 → 恢复搜索前展开态（可用「全部收起」重置）。
- **页可见性 Tag 写入**：沿用现有 `onPageToggle` → `roleApi.update({ pages })` 路径，Tag 只是控件视觉替换，不改数据流。
- **错误处理**：沿用现有 `alert` 提示，不新增 toast 体系。

## 4. 文件清单

**后端**
- `backend/app/extensions/plugin/` — 删除
- `backend/app/extensions/models/__init__.py` — 删 3 个 plugin 模型类
- `backend/app/gateway/app.py` — 删 plugin_router import + include
- `backend/app/extensions/database.py` — 删 seed_builtin_plugins 调用
- `config/permissions.yaml` — 错配修复（改 workflow_admin、补 chapter:view_all / ai:stop_writing、删 cpa:cluster / cpa:export / source:view）
- `backend/tests/test_plugin_*.py`（4 个）— 删除

**前端**
- `frontend/src/extensions/plugin/` — 删除
- `frontend/src/app/plugins/page.tsx` — 删除
- `frontend/src/app/settings/page.tsx` — 删 plugin import + 注释块
- `frontend/src/app/admin/roles/page.tsx` — 面板重构（单页折叠两级、状态 Tag、隐藏 app_center、搜索、展开/收起）
- `frontend/src/extensions/types.ts` — （如需）同步权限类型

**DB（执行一次）**
```sql
DROP TABLE IF EXISTS plugin_api_keys;
DROP TABLE IF EXISTS plugin_instances;
DROP TABLE IF EXISTS plugins;
```

## 5. 测试

- 后端：`test_registry_overlay.py` 等 registry 测试适配错配修复；确认删 plugin 模块后无 import 断裂（跑 `make test`）。
- 前端：vitest 补「单页折叠两级」判定、搜索过滤（纯函数可测）、状态 Tag 切换状态推导；`pnpm typecheck` / `pnpm lint`。
- 手动：admin 打开 `/admin/roles`，验证单页模块两级显示、多页模块三级 + Tag、搜索展开高亮、应用中心不出现、系统角色只读。

## 6. 非目标 / 延后

- `chapter:edit` / `chapter:confirm` / `runs:*` / `threads:*` 等模块树外权限的归属设计。
- 插件市场「容器化改造」恢复（当前直接下线，不做恢复）。
- 矩阵概览结构重构（仅视觉微调）。
- 批量保存 / 防抖 / 撤销。
