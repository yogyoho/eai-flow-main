# 角色管理操作权限 Tab UI/UE 改进 + 插件市场下线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 `/admin/roles` 操作权限 tab（单页模块折叠两级、子页状态 Tag、隐藏 app_center、搜索+展开/收起）、修复 permissions.yaml 权限点错配、全栈下线插件市场。

**Architecture:** 四个独立工作块按依赖顺序执行：(1) 删除插件市场前后端+DB三表；(2) permissions.yaml 错配修复；(3) roles 页面板重构；(4) 测试与验证。DB 用 `create_all` 无 alembic，删除模型后手动 DROP 既有表。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / Next.js 16 / React 19 / Tailwind 4 / vitest

---

## 文件结构总览

| 文件 | 职责 | 操作 |
|---|---|---|
| `backend/app/extensions/plugin/` | 插件市场后端模块 | 删除 |
| `backend/app/extensions/models/__init__.py:912-989` | Plugin/PluginInstance/ApiKey 模型 | 删 3 个类 |
| `backend/app/gateway/app.py:26,602` | plugin_router 挂载 | 删 2 行 |
| `backend/app/extensions/database.py:1566-1570` | seed_builtin_plugins 调用 | 删块 |
| `backend/tests/test_plugin_*.py`（4 个） | 插件测试 | 删除 |
| `frontend/src/extensions/plugin/` | 插件市场前端模块 | 删除 |
| `frontend/src/app/plugins/page.tsx` | 孤儿路由 | 删除 |
| `frontend/src/app/settings/page.tsx` | plugin 引用 | 删 2 处 |
| `frontend/tests/unit/extensions/plugin/` | 插件前端测试 | 删除 |
| `config/permissions.yaml` | 权限注册表 | 修改 |
| `config/roles_custom.yaml` | 角色 overlay | 改 `source:view` |
| `frontend/src/app/admin/roles/page.tsx` | 面板重构 | 修改 |
| `frontend/src/extensions/role/pageVisibility.ts` | 单页折叠/隐藏辅助函数 | 修改 |
| `frontend/tests/unit/extensions/roles/page-visibility.test.ts` | 新增测试 | 修改 |
| `eai-flow-postgres-ext` DB | DROP 三表 | 手动 SQL |

---

## Task 1: 删除插件市场后端模块

**Files:**
- Delete: `backend/app/extensions/plugin/`（整个目录）
- Modify: `backend/app/gateway/app.py:26,602`
- Modify: `backend/app/extensions/database.py:1566-1570`
- Modify: `backend/app/extensions/models/__init__.py:912-989`
- Delete: `backend/tests/test_plugin_mcp_wiring.py`, `test_plugin_models.py`, `test_plugin_routers.py`, `test_plugin_service.py`

- [ ] **Step 1: 删除插件模块目录与测试**

```bash
rm -rf backend/app/extensions/plugin
rm -f backend/tests/test_plugin_mcp_wiring.py backend/tests/test_plugin_models.py backend/tests/test_plugin_routers.py backend/tests/test_plugin_service.py
```

- [ ] **Step 2: 从 gateway/app.py 移除 plugin_router**

`backend/app/gateway/app.py`：
- 删除 L26：`from app.extensions.plugin.routers import router as plugin_router`
- 删除 L602：`app.include_router(plugin_router)`

- [ ] **Step 3: 从 database.py 移除 seed 调用**

`backend/app/extensions/database.py` L1565-1570，删除：

```python
            # Seed built-in plugins for the plugin marketplace
            try:
                from app.extensions.plugin.seed import seed_builtin_plugins

                await seed_builtin_plugins(session)
            except Exception as e:
                logger.warning(f"Failed to seed built-in plugins: {e}")
```

- [ ] **Step 4: 从 models/__init__.py 删除三个模型类**

`backend/app/extensions/models/__init__.py` L912-989，删除 `class Plugin(Base)`、`class PluginInstance(Base)`、`class ApiKey(Base)` 三个完整类（含 docstring 与方法）。保留后面的 `class DataSourceDataset(Base)`（L992 起）不动。

- [ ] **Step 5: 验证无残留 import 断裂**

```bash
cd backend && grep -rn "extensions.plugin\|plugin_router\|PluginMarketplace" app/ --include="*.py" | grep -v __pycache__
```

预期：无输出（除 __pycache__ 残留，可忽略）。若 `test_skill_permissions.py` 或其它测试引用了被删权限，见 Task 4 后再跑全量测试。

- [ ] **Step 6: 验证后端语法**

```bash
cd backend && PYTHONPATH=. python -c "from app.gateway.app import app; print('gateway OK')"
```

预期输出：`gateway OK`（若报错说明 import 残留）。

- [ ] **Step 7: Commit**

```bash
git add -A backend/
git commit -m "feat(plugin): remove plugin marketplace backend module, models, router, seed, tests"
```

---

## Task 2: DROP 插件 DB 三表

**Files:**
- Execute: `eai-flow-postgres-ext`（DB `agentflow`）

- [ ] **Step 1: 确认三表存在**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '%plugin%';"
```

预期：` plugin_api_keys`、` plugins`、` plugin_instances` 三行。

- [ ] **Step 2: DROP 三表**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "DROP TABLE IF EXISTS plugin_api_keys; DROP TABLE IF EXISTS plugin_instances; DROP TABLE IF EXISTS plugins;"
```

预期：三个 `DROP TABLE` 成功输出。

- [ ] **Step 3: 确认已删**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '%plugin%';"
```

预期：无输出。

- [ ] **Step 4: 重启 gateway 使模型变更生效**

```bash
docker compose -p eai-docker restart gateway
```

---

## Task 3: 删除插件市场前端

**Files:**
- Delete: `frontend/src/extensions/plugin/`
- Delete: `frontend/src/app/plugins/page.tsx`
- Delete: `frontend/tests/unit/extensions/plugin/`
- Modify: `frontend/src/app/settings/page.tsx:10,87-99`

- [ ] **Step 1: 删除插件前端模块与测试**

```bash
rm -rf frontend/src/extensions/plugin frontend/src/app/plugins frontend/tests/unit/extensions/plugin
```

- [ ] **Step 2: 从 settings/page.tsx 移除 plugin 引用**

`frontend/src/app/settings/page.tsx`：
- 删除 L10：`import PluginMarketplace from "@/extensions/plugin/PluginMarketplace";`
- 删除 L87-99 注释块（`{/* 插件系统容器化改造中，暂时下线入口` 到 `*/}`），即整个注释掉的 `{activeTab === "plugins" && (...)}` 块。
- L24 注释行 `// { id: "plugins", ... }` 一并删除。

- [ ] **Step 3: 验证无残留引用**

```bash
cd frontend && grep -rn "PluginMarketplace\|extensions/plugin\|app/plugins" src/ tests/ --include="*.ts" --include="*.tsx" | grep -v __pycache__
```

预期：无输出。

- [ ] **Step 4: 类型检查**

```bash
cd frontend && pnpm typecheck
```

预期：PASS。

- [ ] **Step 5: Commit**

```bash
git add -A frontend/
git commit -m "feat(plugin): remove plugin marketplace frontend module, orphan route, settings refs"
```

---

## Task 4: permissions.yaml 权限点错配修复

**Files:**
- Modify: `config/permissions.yaml`

- [ ] **Step 1: 修改 workflow_admin 模块操作项**

`config/permissions.yaml` L179-190，`workflow_admin` 模块的 pages→workflow-admin:page:index operations 改为：

```yaml
        operations:
          - { id: "project:advance", display_name: "推进工作流" }
```

（删除原 `workflow:read` / `workflow:start` / `workflow:cancel` / `workflow:edit` 四项中的 start/cancel/edit；`workflow:read` 保留在系统其它角色默认里，本模块操作集仅保留与后端 `project:advance` 对应的单点。若确认 `workflow:read` 无其它后端强制用途，一并保留——它出现在多个角色默认中。）

- [ ] **Step 2: projects 模块补两项**

`config/permissions.yaml` 的 `projects` 模块（L33-57 operations 列表末尾）追加：

```yaml
          - { id: "chapter:view_all", display_name: "查看全部章节/来源" }
          - { id: "ai:stop_writing", display_name: "停止 AI 写作" }
```

- [ ] **Step 3: 删除合同价格冗余项**

`config/permissions.yaml` L153：删除 `- { id: "cpa:cluster", display_name: "执行聚类分析" }`。
L163：删除 `- { id: "cpa:export", display_name: "导出分析结果" }`。

`cpa:page:items`（分项校验）operations 变为空数组 `operations: []`；`cpa:page:settings`（配置）operations 变为空数组 `operations: []`。

- [ ] **Step 4: 删除 source:view（共 5 处）**

`source:view` 实际强制的是 `chapter:view_all`（见设计文档 §3.2），且后端从不强制 `source:view` → 全部移除：

- `config/permissions.yaml` L52：删除 `- { id: "source:view", display_name: "查看来源" }`（projects 模块 operation 声明）。
- `config/permissions.yaml` L295（dept_head 默认）、L344（writer 默认）、L362（reviewer 默认）：从各自 `permissions:` 列表删除 `- source:view`。
- `config/roles_custom.yaml` L83：删除 `- source:view`（Task 5 会再确认，若已删则跳过）。

> 若 L344/L362 所属角色需要"查看来源"能力，语义由 `chapter:view_all` 替代（不自动补授，保持最小变更）。

- [ ] **Step 5: 验证 yaml 语法**

```bash
python -c "import yaml; d=yaml.safe_load(open('config/permissions.yaml', encoding='utf-8')); print('yaml OK', len(d['modules']), 'modules')"
```

预期：`yaml OK 12 modules`。

- [ ] **Step 6: 运行 registry 相关测试**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_permission_registry.py tests/test_registry_overlay.py -v
```

预期：PASS。若测试断言引用了被删的 `cpa:cluster` 等（本仓库测试未引用），则跳过；若失败，更新测试断言为删除后的期望值。

- [ ] **Step 7: Commit**

```bash
git add config/permissions.yaml
git commit -m "fix(rbac): align permissions.yaml ops with backend enforcement (project:advance, chapter:view_all, ai:stop_writing; drop cpa:cluster/cpa:export)"
```

---

## Task 5: roles_custom.yaml 清理 source:view 引用

**Files:**
- Modify: `config/roles_custom.yaml:83`

- [ ] **Step 1: 移除 source:view**

`config/roles_custom.yaml` L83，从 dept_head（或对应角色）的 permissions 列表中删除 `- source:view`。若该角色需要"查看来源"能力，用 `chapter:view_all` 语义替代（本任务仅删除，不添加——是否补授由后续角色校准决定）。

- [ ] **Step 2: 验证 overlay 解析**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_role_overlay_store.py tests/test_role_calibration.py -v
```

预期：PASS。

- [ ] **Step 3: Commit**

```bash
git add config/roles_custom.yaml
git commit -m "fix(rbac): remove source:view ref from roles_custom overlay (permission retired)"
```

---

## Task 6: 面板重构基础 —— 单页折叠两级 + 隐藏 app_center

**Files:**
- Modify: `frontend/src/extensions/role/pageVisibility.ts`
- Modify: `frontend/src/app/admin/roles/page.tsx`
- Modify: `frontend/tests/unit/extensions/roles/page-visibility.test.ts`

**设计**：单页模块（`pages` 长度为 1）直接渲染模块卡片 → 操作网格，跳过中间"子页"行；`app_center`（`pages` 为空且无可配权限）整卡隐藏。

- [ ] **Step 1: 写失败测试**

`frontend/tests/unit/extensions/roles/page-visibility.test.ts` 追加：

```ts
import { isSinglePageModule, shouldHideModule } from "@/extensions/role/pageVisibility";
import type { RegistryModule } from "@/extensions/types";

describe("single-page fold + hidden modules", () => {
  const mod = (pages: unknown[]): RegistryModule =>
    ({ key: "m", display_name: "M", permissions: [], data_scopes: [], pages: pages as never }) as RegistryModule;

  test("module with exactly 1 page folds to 2 levels", () => {
    expect(isSinglePageModule(mod([{ id: "p1", display_name: "P", operations: [] }]))).toBe(true);
  });

  test("module with 0 or 2+ pages does not fold", () => {
    expect(isSinglePageModule(mod([]))).toBe(false);
    expect(isSinglePageModule(mod([{ id: "p1", display_name: "P", operations: [] }, { id: "p2", display_name: "Q", operations: [] }]))).toBe(false);
  });

  test("app_center module with no pages is hidden", () => {
    expect(shouldHideModule(mod([]))).toBe(true);
  });

  test("module with pages is not hidden", () => {
    expect(shouldHideModule(mod([{ id: "p1", display_name: "P", operations: [] }]))).toBe(false);
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && pnpm vitest run tests/unit/extensions/roles/page-visibility.test.ts`
Expected: FAIL with `isSinglePageModule is not a function`.

- [ ] **Step 3: 实现辅助函数**

`frontend/src/extensions/role/pageVisibility.ts` 追加：

```ts
/** 模块只有 1 个 page → 面板折叠为两级（跳过中间子页行）。 */
export function isSinglePageModule(mod: RegistryModule): boolean {
  return !!mod.pages && mod.pages.length === 1;
}

/** 模块无可配权限（无 pages 且无直接 permissions）→ 整卡隐藏。 */
export function shouldHideModule(mod: RegistryModule): boolean {
  return !mod.pages || mod.pages.length === 0;
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && pnpm vitest run tests/unit/extensions/roles/page-visibility.test.ts`
Expected: PASS。

- [ ] **Step 5: 在 PermissionPanel 应用折叠与隐藏**

`frontend/src/app/admin/roles/page.tsx` 的 `PermissionPanel`（L242 起）：

a. 引入 `isSinglePageModule`、`shouldHideModule`：
```ts
import { isSinglePageModule, resolveVisiblePages, serializePages, shouldHideModule } from "@/extensions/role/pageVisibility";
```

b. 在 `treeModules` 渲染前过滤隐藏模块：
```ts
const visibleModules = isTree ? treeModules.filter((m) => !shouldHideModule(m)) : [];
```

c. 将 L319 `treeModules.map((mod) => {` 改为 `visibleModules.map((mod) => {`。

d. 在模块渲染内部，单页模块跳过子页行：将 L404-503 的 `{hasPages ? (mod.pages!.map(...)) : (...)}` 块包裹为：

```tsx
{isSinglePageModule(mod) ? (
  /* 单页模块：直接渲染该页操作网格，无子页行 */
  <div className={cn("px-3 pb-3 pt-1", !moduleVisible && "opacity-50 pointer-events-none")}>
    {mod.pages![0].operations.length > 0 ? (
      <div className="grid gap-1.5" style={gridStyle}>
        {mod.pages![0].operations.map((op) => {
          const isChecked = selected.includes(op.id);
          return (
            <label key={op.id}
              className={cn(
                "group/perm flex items-center gap-2.5 text-sm p-2 rounded-lg transition-all duration-200 min-w-0 select-none",
                readonly ? "cursor-default" : "cursor-pointer",
                isChecked ? "bg-primary/[0.04] border border-primary/10" : "border border-transparent hover:bg-accent/50 hover:border-border",
              )}>
              <input type="checkbox" checked={isChecked} onChange={() => togglePerm(op.id)} disabled={readonly} className="sr-only peer" />
              <PermCheckbox checked={isChecked} disabled={readonly} />
              <span className={cn("truncate transition-colors duration-200 leading-tight",
                readonly ? "text-muted-foreground" : isChecked ? "text-foreground font-medium" : "text-foreground/70 group-hover/perm:text-foreground")}>
                {op.display_name}
              </span>
            </label>
          );
        })}
      </div>
    ) : (
      <div className="text-xs text-muted-foreground/50 px-1 py-2">暂无操作项</div>
    )}
  </div>
) : (
  hasPages ? (
    /* 多页模块：原有子页渲染（子页 Tag 在 Task 7 改） */
    mod.pages!.map((page) => { /* ... 现有逻辑，保留 ... */ })
  ) : (
    /* 无 pages 的旧兼容渲染（保留） */
    totalOps > 0 ? ( /* 原操作网格 */ ) : ( /* 暂无权限点 */ )
  )
)}
```

e. 单页模块也参与 `全选本组`/模块可见开关（保留现有 header 逻辑不变，单页模块的"全选本组"用现有 `toggleCategory(allOpIds)`）。

- [ ] **Step 6: 类型检查**

```bash
cd frontend && pnpm typecheck
```

预期：PASS。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/admin/roles/page.tsx frontend/src/extensions/role/pageVisibility.ts frontend/tests/unit/extensions/roles/page-visibility.test.ts
git commit -m "feat(roles-ui): fold single-page modules to 2 levels, hide empty app_center module card"
```

---

## Task 7: 子页可见性改状态 Tag（多页模块）

**Files:**
- Modify: `frontend/src/app/admin/roles/page.tsx`

**设计**：模块级保留 Switch；子页级"可见/不可见"从 Switch 改为 `◉可见` / `◌不可见` 状态 Tag（点击切换），消除两级控件同质化。

- [ ] **Step 1: 定位子页可见性渲染**

`frontend/src/app/admin/roles/page.tsx` L417-428（多页模块的 page header 内的可见性开关），当前是：

```tsx
{onPageToggle && (
  <span className={cn("flex items-center gap-1.5 ml-1 shrink-0", readonly ? "opacity-50 pointer-events-none" : "")}>
    <span className={cn("text-xs", pageVisible ? "text-primary" : "text-muted-foreground/50")}>
      {pageVisible ? "可见" : "不可见"}
    </span>
    <Switch checked={pageVisible} onCheckedChange={(c) => onPageToggle(page.id, c)} disabled={readonly} />
  </span>
)}
```

- [ ] **Step 2: 改为状态 Tag**

替换为：

```tsx
{onPageToggle && (
  <button
    type="button"
    onClick={() => { if (!readonly) onPageToggle(page.id, !pageVisible); }}
    disabled={readonly}
    className={cn(
      "ml-1 shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium border transition-colors",
      pageVisible
        ? "bg-primary/10 text-primary border-primary/20 hover:bg-primary/20"
        : "bg-muted text-muted-foreground border-transparent hover:bg-accent hover:text-foreground",
    )}
  >
    <span className={cn("w-1.5 h-1.5 rounded-full", pageVisible ? "bg-primary" : "bg-muted-foreground/50")} />
    {pageVisible ? "可见" : "不可见"}
  </button>
)}
```

- [ ] **Step 3: 类型检查**

```bash
cd frontend && pnpm typecheck
```

预期：PASS。

- [ ] **Step 4: 手动验证（浏览器）**

打开 `http://localhost:2026/admin/roles`，选中多页模块（知识工厂/合同价格），确认：
- 子页 Tag 点击切换可见性；隐藏时操作网格置灰（现有逻辑保留）。
- 模块级 Switch 仍为原样式。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/admin/roles/page.tsx
git commit -m "feat(roles-ui): sub-page visibility switch -> status Tag (distinct from module Switch)"
```

---

## Task 8: 顶部工具条 —— 搜索 + 全部展开/收起

**Files:**
- Modify: `frontend/src/app/admin/roles/page.tsx`

**设计**：PermissionPanel 顶部工具条新增 `🔍 搜索操作`（跨模块过滤，命中即展开匹配模块并高亮操作项）+ `全部展开 / 全部收起`。

- [ ] **Step 1: 在 PermissionPanel 增加状态**

`PermissionPanel`（L264 附近）增加：

```tsx
const [searchQuery, setSearchQuery] = useState("");
```

- [ ] **Step 2: 顶部工具条 UI**

在 `PermissionPanel` 顶部（现"全选/清空"按钮组之后、`{isTree && treeModules.length > 0 ? ...}` 之前）插入：

```tsx
{!readonly && (
  <div className="flex items-center gap-2">
    <div className="relative flex-1 max-w-xs">
      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
      <Input
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="搜索操作..."
        className="pl-8 h-8 text-xs"
      />
    </div>
    <button type="button" onClick={() => setExpandedCats(new Set(treeModules.map((m) => m.key)))}
      className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-background border border-border rounded-lg hover:border-primary/40 hover:text-primary transition-colors">
      全部展开
    </button>
    <button type="button" onClick={() => setExpandedCats(new Set())}
      className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-background border border-border rounded-lg hover:border-primary/40 hover:text-primary transition-colors">
      全部收起
    </button>
  </div>
)}
```

- [ ] **Step 3: 搜索过滤逻辑**

在 `toggleCat`/`togglePerm` 之后增加：

```tsx
const q = searchQuery.trim().toLowerCase();
// 命中操作所在模块 → 强制展开
useEffect(() => {
  if (!q) return;
  if (isTree) {
    const hitModules = treeModules.filter((mod) => {
      const pageOps = (mod.pages || []).flatMap((pg) => pg.operations.map((op) => op.id));
      const directOps = mod.permissions.map((p) => p.id);
      return [...pageOps, ...directOps].some((id) =>
        id.toLowerCase().includes(q) || (mod.display_name || "").toLowerCase().includes(q));
    });
    if (hitModules.length > 0) {
      setExpandedCats(new Set(hitModules.map((m) => m.key)));
    }
  } else {
    const hitCats = categories.filter((c) =>
      c.permissions.some((p) => p.key.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)));
    if (hitCats.length > 0) {
      setExpandedCats(new Set(hitCats.map((c) => c.name)));
    }
  }
}, [q, isTree, treeModules, categories]);
```

- [ ] **Step 4: 操作项/子页高亮**

在模块 header 名称处（L352 `{mod.display_name}`）与操作项 label（单页 L457 与多页 L452 附近的 `<span>`）套用高亮：

```tsx
const highlight = (text: string) => {
  if (!q) return text;
  const idx = text.toLowerCase().indexOf(q);
  if (idx < 0) return text;
  return (<>
    {text.slice(0, idx)}
    <mark className="bg-primary/20 text-primary rounded-sm px-0.5">{text.slice(idx, idx + q.length)}</mark>
    {text.slice(idx + q.length)}
  </>);
};
```

将 `{mod.display_name}` → `{highlight(mod.display_name)}`，操作 label `{op.display_name}` → `{highlight(op.display_name)}`，子页名 `{page.display_name}` → `{highlight(page.display_name)}`。`highlight` 定义放 `PermissionPanel` 内、return 前。

- [ ] **Step 5: 类型检查**

```bash
cd frontend && pnpm typecheck
```

预期：PASS。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/admin/roles/page.tsx
git commit -m "feat(roles-ui): add permission search with highlight + expand/collapse-all toolbar"
```

---

## Task 9: 全量验证

- [ ] **Step 1: 后端全量测试**

```bash
cd backend && make lint && make test
```

预期：lint 与全量测试 PASS。若 test_plugin_* 删除后出现其它测试引用被删权限/模块的失败，修复对应测试断言。

- [ ] **Step 2: 前端检查**

```bash
cd frontend && pnpm lint && pnpm typecheck && pnpm test
```

预期：全部 PASS。`frontend/tests/unit/extensions/plugin/` 已删，无引用。

- [ ] **Step 3: 容器重启 + 手动回归**

```bash
docker compose -p eai-docker restart gateway frontend
```

浏览器打开 `http://localhost:2026/admin/roles`，验证：
- 单页模块（工作台/智能写作/文档空间）两级显示，无冗余子页行。
- 多页模块（知识工厂/合同价格）子页为状态 Tag，模块级为 Switch。
- `app_center`（应用中心）卡片不出现。
- 搜索"查看" → 命中模块自动展开并高亮。
- 系统角色（超级管理员）只读置灰。
- 设置页无插件 tab、无报错；`/plugins` 路由 404。

- [ ] **Step 4: DB 确认**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '%plugin%';"
```

预期：无输出。

- [ ] **Step 5: Commit 收尾**

```bash
git add -A && git commit -m "test: verify plugin removal + permissions tab redesign end-to-end"
```

---

## 自审记录

- **Spec 覆盖**：①插件下线（Task 1/2/3）✓；②permissions.yaml 错配（Task 4/5）✓；③面板重构 单页折叠/隐藏 app_center（Task 6）✓ 状态 Tag（Task 7）✓ 搜索+展开收起（Task 8）✓；④测试验证（Task 9）✓。
- **占位符**：无 TBD/TODO；所有代码步骤给出完整内容。
- **类型一致性**：`isSinglePageModule`/`shouldHideModule` 在 Task 6 定义，测试与渲染均引用同名；`highlight` 在 Task 8 定义并用于模块/操作/子页三处。
- **注意**：`source:view` 共 5 处引用——permissions.yaml L52（声明）+ L295/344/362（角色默认）+ roles_custom.yaml L83。Task 4 Step 4 处理 permissions.yaml 的 4 处，Task 5 处理 roles_custom 的 1 处。已实测确认这些行号。
