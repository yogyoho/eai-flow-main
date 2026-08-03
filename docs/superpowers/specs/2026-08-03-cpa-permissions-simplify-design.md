# 合同价格分析 · 权限收敛设计

> 日期：2026-08-03 | 状态：已批准
> 范围：角色管理「操作权限」tab 中合同价格分析模块 —— 参照知识工厂收敛为「模块可见 + 子 tab 可见」，后端权限收口为 system:access

## 1. 背景与审计发现

合同价格分析与知识工厂结构相同（模块 → 子页 → 操作），但**关键差异**在于操作层的后端强制情况：

| | 知识工厂 | 合同价格 |
|---|---|---|
| 后端操作点强制 | ❌ 全部零强制（system:access 统一收口） | ✅ **真实强制**：`cpa:read` 12 处 + `cpa:import` 20 处，共 32 处接口 |
| 操作点现状 | 已全删 | 剩 2 个：`cpa:read`（总览）、`cpa:import`（合同解析），其余 4 页空 |
| 前端 tab 接线 | 9 tab ↔ 9 `kf:page:*` canPage | 6 tab ↔ 6 `cpa:page:*` canPage（已接线 ✅） |

**含义**：不能像知识工厂那样直接删操作点——后端 32 处 `require_permission("cpa:read"/"cpa:import")` 会指向不存在的权限点 → 合同价格全部接口 403。必须先收口后端权限。

**用户决策**：后端统一收口为 `system:access`，接受失去"仅查看 vs 可导入"细粒度；`data_scopes` 保留。

## 2. 目标

1. 后端 32 处 `require_permission("cpa:read")` / `require_permission("cpa:import")` 全部改为 `require_permission("system:access")`。
2. `permissions.yaml` 删除 `cpa:read`/`cpa:import` 操作点，清角色持有引用（保留 `cpa:page:*` + `data_scopes`）。
3. 前端零改动——`isVisibilityOnlyModule`（上轮实现，通用）自动将合同价格渲染为可见性纯模块扁平子页网格。

## 3. 设计

### 3.1 后端收口（backend/app/extensions/contract_price/routers.py）

将 32 处权限检查替换为 `system:access`。采用**方案 A（sed 全局替换，2 次）**：

```
require_permission("cpa:read")   → require_permission("system:access")
require_permission("cpa:import") → require_permission("system:access")
```

每个替换点保留 `# EAI-CUSTOM: Add permission check` 注释。

**影响**：合同价格接口从"需 cpa:read/cpa:import"变为"需 system:access"——与知识工厂及多数 EAI 扩展模块一致。已持有 cpa:read/cpa:import 的角色（dept_head/项目经理）本就持有 system:access，**无角色受影响**。

### 3.2 数据层（config/permissions.yaml + roles_custom.yaml）

- `permissions.yaml` contract_price 模块：删 `cpa:read`（总览页）、`cpa:import`（合同解析页）操作点 → 6 页全部 `operations` 为空（保留 `cpa:page:*` + `data_scopes`）。
- `permissions.yaml` dept_head 默认：删 `cpa:read`、`cpa:import`。
- `roles_custom.yaml`：删 `cpa:read`、`cpa:import`。
- **保留**：`cpa:page:*`（canPage 需要）、`data_scopes`（数据权限 tab 不受影响）。

### 3.3 前端面板

**零改动**。`isVisibilityOnlyModule`（`pages.every(p => p.operations.length === 0)`）是通用的：删操作后合同价格 6 页全空 operations → 自动进入可见性纯模块渲染：
- 模块头「可见 X/6 子页」+ 进度条
- 6 张子页卡片网格（名称 + 可见 Tag，点击切换）
- 隐藏全选本组按钮
- 模块可见开关保留

前端 `contract-price/layout.tsx` 的 6 tab ↔ `cpa:page:*` canPage 接线已存在，无需改。

## 4. 文件清单

| 文件 | 操作 |
|---|---|
| `backend/app/extensions/contract_price/routers.py` | 32 处 cpa:* → system:access |
| `config/permissions.yaml` | 删 cpa:read/cpa:import 操作点 + dept_head 引用 |
| `config/roles_custom.yaml` | 删 cpa:read/cpa:import |

## 5. 测试

- 后端：`test_contract_price_extension.py` 确认权限替换后通过；`make lint` 确认 routers.py 无新错误。
- 前端：roles 测试确认 `isVisibilityOnlyModule` 对合同价格成立（已测通用逻辑，跑一遍确认）。
- 手动：浏览器角色管理 → 合同价格卡片"可见 X/6 子页"+6 张子页卡；实际访问合同价格页面 200；切子页不可见 → tab 消失。

## 6. 非目标 / 延后

- 不改 `data_scopes`（保留数据权限 tab 配置）。
- 不动 contract-price 前端组件逻辑。
- 后端权限统一为 system:access 后，"仅查看合同价格"的细粒度能力永久移除（可接受）。
