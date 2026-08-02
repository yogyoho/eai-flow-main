# 角色管理子页面可见性控制 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在角色管理"操作控制"三级面板中为每个子页面加"可见"开关（方案 A），持久化到 overlay `pages` 字段，并把 `canPage` 接线到知识工厂 9 tab 与合同价格 6 子视图的渲染。

**Architecture:** 后端 `RoleUpdate.pages`/`RoleResponse.pages` + `update_role` 写透 overlay（含 page id 校验）；前端 `PermissionPanel` 每子页面加可见开关（隐藏页操作置灰但保留勾选）；知识工厂/合同价格 tab 数组按 `usePermission().canPage(pageId)` 过滤（含 activeTab 回退）。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / PyYAML / Next.js 16 / React 19 / TypeScript / Vitest

**Spec:** `docs/superpowers/specs/2026-08-02-role-page-visibility-design.md`

**Environment:** 后端改动后 `docker compose -p eai-docker -f docker/docker-compose-dev.yaml restart gateway`；前端无新依赖，`restart frontend` 即可。测试在 host：`cd backend && PYTHONPATH=. uv run pytest ...`；`cd frontend && pnpm typecheck` / `pnpm exec vitest run <file>`。

---

## 文件结构

**后端：**
- Modify: `backend/app/extensions/auth/registry.py` — 加 `page_id_exists(page_id)`
- Modify: `backend/app/extensions/schemas.py` — `RoleUpdate.pages`、`RoleResponse.pages`
- Modify: `backend/app/extensions/role/service.py` — `update_role` 写透 pages + 校验；`to_response` 合并 pages
- Test: `backend/tests/test_role_overlay_store.py`（pages 写透/校验）

**配置：**
- Modify: `config/permissions.yaml` — knowledge_factory 补 `kf:page:extraction`

**前端：**
- Modify: `frontend/src/app/admin/roles/page.tsx` — PermissionPanel 子页面开关 + AdminRolesPage 状态
- Modify: `frontend/src/extensions/types.ts` — `Role.pages`、`UpdateRoleRequest.pages`
- Modify: `frontend/src/app/knowledge-factory/page.tsx` — tab 按 `canPage` 过滤
- Modify: `frontend/src/extensions/knowledge-factory/TabNavigation.tsx` — tab 按 `canPage` 过滤
- Modify: `frontend/src/app/contract-price/layout.tsx` — 子路由按 `canPage` 过滤
- Test: `frontend/tests/unit/extensions/roles/page-visibility.test.ts`（纯函数：`*` 展开、显式列表、切关生成列表）

---

## Task 1: 后端 — registry page 校验 + schema + 写透

**Files:**
- Modify: `backend/app/extensions/auth/registry.py`
- Modify: `backend/app/extensions/schemas.py`
- Modify: `backend/app/extensions/role/service.py`
- Test: `backend/tests/test_role_overlay_store.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_role_overlay_store.py` 追加：

```python
def test_update_role_persists_pages(tmp_path, monkeypatch):
    """update_role 写透 pages 到 overlay；校验未知 page id 拒绝。"""
    overlay_path = tmp_path / "roles_custom.yaml"
    overlay_path.write_text("roles: {}\ndisabled_roles: []\n", encoding="utf-8")
    store = RoleOverlayStore(overlay_path=str(overlay_path))
    monkeypatch.setattr(RoleService, "_store", store)

    fake_registry = _FakeRegistry()
    fake_registry.page_ids = {"kf:page:sample", "kf:page:law"}  # 见 Step 2 的 _FakeRegistry
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)
    monkeypatch.setattr("app.extensions.auth.registry.get_permission_registry", lambda: fake_registry)

    role = Role(
        id=uuid_mod.uuid4(), name="部门主管", code="dept_head",
        permissions=["kb:read"], is_system=False, level=50, description=None, nav=[],
    )
    fake_db = _FakeDb()

    result = asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(pages=["kf:page:sample"])))
    entry = store.read()["roles"]["dept_head"]
    assert entry["pages"] == ["kf:page:sample"]
    assert result is not None and result.code == "dept_head"

    # 未知 page id → ValueError，不落盘
    with pytest.raises(ValueError):
        asyncio.run(RoleService.update_role(fake_db, role, RoleUpdate(pages=["bogus:page"])))
    entry2 = store.read()["roles"]["dept_head"]
    assert entry2["pages"] == ["kf:page:sample"]  # 未被覆盖


def test_to_response_merges_pages(tmp_path, monkeypatch):
    """RoleResponse.pages 来自 registry.get_page_ids_for_role。"""
    from app.extensions.role.service import RoleService

    fake_registry = _FakeRegistry()
    fake_registry.role_pages = {"dept_head": ["*"]}
    monkeypatch.setattr("app.extensions.role.service.get_permission_registry", lambda: fake_registry)

    role = Role(
        id=uuid_mod.uuid4(), name="部门主管", code="dept_head",
        permissions=["kb:read"], is_system=False, level=50, description=None, nav=[],
    )
    fake_db = _FakeDb()
    resp = asyncio.run(RoleService.to_response(fake_db, role))
    assert resp.pages == ["*"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_role_overlay_store.py::test_update_role_persists_pages tests/test_role_overlay_store.py::test_to_response_merges_pages -v`
Expected: FAIL（`_FakeRegistry.page_ids`/`role_pages` 不存在或 `RoleService.update_role` 未处理 pages / `RoleResponse.pages` 不存在）

`_FakeRegistry`（test_role_overlay_store.py 内已有类）追加属性与方法：

```python
class _FakeRegistry:
    page_ids: set[str] = set()          # Task1 测试设置
    role_pages: dict[str, list[str]] = {}  # Task1 to_response 测试设置

    def page_id_exists(self, page_id):
        return page_id in getattr(self, "page_ids", set())

    def get_page_ids_for_role(self, code):
        return getattr(self, "role_pages", {}).get(code, [])
```

- [ ] **Step 3: registry.py 加 `page_id_exists`**

`backend/app/extensions/auth/registry.py` — 在 `list_all_permissions` 附近新增：

```python
    def page_id_exists(self, page_id: str) -> bool:
        """True if a module defines this page id (across all nav modules)."""
        for mp in self.modules.values():
            for p in mp.pages:
                if p.id == page_id:
                    return True
        return False
```

- [ ] **Step 4: schemas.py 加 pages**

`backend/app/extensions/schemas.py` — `RoleUpdate` 加（data_scopes 之后）：

```python
    # EAI-CUSTOM: sub-page visibility ids (persisted to overlay via write-through)
    pages: list[str] | None = None
```

`RoleResponse` 加（data_scopes 之后）：

```python
    # EAI-CUSTOM: sub-page visibility ids resolved from registry
    pages: list[str] = []
```

- [ ] **Step 5: service.py — update_role 写透 pages + to_response 合并**

`backend/app/extensions/role/service.py` — `update_role` 在 `if data.data_scopes is not None:` 块之后加：

```python
        if data.pages is not None:
            registry = get_permission_registry()
            invalid_pages = [pid for pid in data.pages if pid != "*" and not registry.page_id_exists(pid)]
            if invalid_pages:
                raise ValueError(f"Unknown page ids: {invalid_pages}")
            entry["pages"] = list(data.pages)
```

`to_response` — 返回字典加 `pages=registry.get_page_ids_for_role(role.code)`：

```python
        registry = get_permission_registry()
        return RoleResponse(
            id=role.id,
            name=role.name,
            code=role.code,
            permissions=role.permissions or [],
            is_system=role.is_system,
            description=role.description,
            level=role.level,
            parent_role_id=role.parent_role_id,
            parent_role_name=parent_role_name,
            created_at=role.created_at,
            nav=role.nav or [],
            data_scopes=registry.get_data_scopes_for_role(role.code),
            pages=registry.get_page_ids_for_role(role.code),
        )
```

- [ ] **Step 6: 运行确认通过 + 回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_role_overlay_store.py tests/test_role_calibration.py tests/test_permission_engine.py -q`
Expected: all passed

Ruff: `cd backend && uv run ruff check app/extensions/auth/registry.py app/extensions/schemas.py app/extensions/role/service.py`

- [ ] **Step 7: Commit**

```bash
git add backend/app/extensions/auth/registry.py backend/app/extensions/schemas.py backend/app/extensions/role/service.py backend/tests/test_role_overlay_store.py
git commit -m "feat(rbac): RoleUpdate/RoleResponse pages + update_role write-through with page-id validation"
```

---

## Task 2: 配置 — permissions.yaml 补 kf:page:extraction

**Files:**
- Modify: `config/permissions.yaml`

- [ ] **Step 1: 加页面**

`config/permissions.yaml` — `knowledge_factory` 模块，在 `kf:page:sample` 页之后插入：

```yaml
      - id: "kf:page:extraction"
        display_name: "模板抽取"
        operations:
          - { id: "kf:read", display_name: "查看知识工厂" }
```

（9 tab ↔ 9 page id 一一对应：reports→sample, extraction→extraction, editor→template, law→law, rules→compliance, version→version, quality→quality, scraper→scrape, dictionaries→dict。）

- [ ] **Step 2: 验证 YAML + registry**

Run: `cd backend && PYTHONPATH=. uv run python -c "from app.extensions.auth.registry import get_permission_registry; r=get_permission_registry(); print('extraction exists:', r.page_id_exists('kf:page:extraction')); import yaml; yaml.safe_load(open('../config/permissions.yaml',encoding='utf-8')); print('YAML OK')"`
Expected: extraction exists: True / YAML OK

- [ ] **Step 3: Commit**

```bash
git add config/permissions.yaml
git commit -m "feat(rbac): add kf:page:extraction page (9 knowledge-factory tabs ↔ 9 page ids)"
```

---

## Task 3: 前端 — PermissionPanel 子页面可见开关 + 状态

**Files:**
- Modify: `frontend/src/extensions/types.ts`
- Modify: `frontend/src/app/admin/roles/page.tsx`

- [ ] **Step 1: types.ts 加 pages**

`frontend/src/extensions/types.ts` — `Role` interface 加：

```ts
  /** EAI-CUSTOM: sub-page visibility ids resolved from registry ("*" = all) */
  pages?: string[];
```

`UpdateRoleRequest` 加：

```ts
  /** EAI-CUSTOM: sub-page visibility ids */
  pages?: string[];
```

- [ ] **Step 2: 提取纯函数（可测）**

新建 `frontend/src/extensions/role/pageVisibility.ts`：

```ts
import type { RegistryModule } from "@/extensions/types";

/** Collect every page id across registry modules. */
export function allPageIds(modules: RegistryModule[]): string[] {
  return (modules || []).flatMap((m) => (m.pages || []).map((p) => p.id));
}

/** Resolve a role's pages into a visible-page-id set ("*" or missing → all). */
export function resolveVisiblePages(
  modules: RegistryModule[],
  rolePages?: string[],
): Set<string> {
  const ids = allPageIds(modules);
  if (!rolePages || rolePages.length === 0 || rolePages.includes("*")) {
    return new Set(ids);
  }
  return new Set(rolePages.filter((id) => ids.includes(id)));
}

/** Serialize a visible-page set back to the role.pages wire format ("*" when all). */
export function serializePages(visible: Set<string>, modules: RegistryModule[]): string[] {
  const ids = allPageIds(modules);
  if (ids.length > 0 && ids.every((id) => visible.has(id))) {
    return ["*"];
  }
  return [...visible];
}
```

- [ ] **Step 3: PermissionPanel 加 props 与子页面开关**

`frontend/src/app/admin/roles/page.tsx` — `PermissionPanel` 签名加：

```ts
  /** EAI-CUSTOM: set of visible page ids (sub-page visibility) */
  enabledPages?: Set<string>;
  /** EAI-CUSTOM: called when a sub-page visibility toggle changes */
  onPageToggle?: (pageId: string, enabled: boolean) => void;
```

模块展开内容中，`mod.pages!.map((page) => {...})` 块改为（页面头加开关+计数，隐藏页操作置灰）：

```tsx
                        mod.pages!.map((page) => {
                          const pageHasOps = page.operations.length > 0;
                          const pageOpIds = page.operations.map((op) => op.id);
                          const pageSelected = selected.filter((k) => pageOpIds.includes(k)).length;
                          const pageTotal = pageOpIds.length;
                          const pageVisible = enabledPages ? enabledPages.has(page.id) : true;
                          return (
                            <div key={page.id} className="mb-2 last:mb-0">
                              {/* Page header: icon + name + visible switch (right after text) + count */}
                              <div className="flex items-center gap-2 py-2 px-1 text-sm font-semibold text-muted-foreground">
                                <FileText className="w-3.5 h-3.5 shrink-0 opacity-60" />
                                <span className="truncate">{page.display_name}</span>
                                {onPageToggle && (
                                  <span className={cn("flex items-center gap-1.5 ml-1 shrink-0", readonly ? "opacity-50 pointer-events-none" : "")}>
                                    <span className={cn("text-xs", pageVisible ? "text-primary" : "text-muted-foreground/50")}>
                                      {pageVisible ? "可见" : "不可见"}
                                    </span>
                                    <Switch
                                      checked={pageVisible}
                                      onCheckedChange={(c) => onPageToggle(page.id, c)}
                                      disabled={readonly}
                                    />
                                  </span>
                                )}
                                {pageTotal > 0 && (
                                  <span className="text-xs tabular-nums text-muted-foreground/60 ml-1">{pageSelected}/{pageTotal}</span>
                                )}
                              </div>
                              {/* Operations grid — grayed + locked when page hidden */}
                              <div className={cn(pageVisible ? "" : "opacity-40 pointer-events-none")}>
                                {pageHasOps ? (
                                  <div className="grid gap-1.5" style={gridStyle}>
                                    {page.operations.map((op) => {
                                      const isChecked = selected.includes(op.id);
                                      return (
                                        <label key={op.id}
                                          className={cn(
                                            "group/perm flex items-center gap-2.5 text-sm p-2 rounded-lg transition-all duration-200 min-w-0 select-none",
                                            readonly ? "cursor-default" : "cursor-pointer",
                                            isChecked
                                              ? "bg-primary/[0.04] border border-primary/10"
                                              : "border border-transparent hover:bg-accent/50 hover:border-border",
                                          )}>
                                          <input type="checkbox" checked={isChecked}
                                            onChange={() => togglePerm(op.id)} disabled={readonly}
                                            className="sr-only peer" />
                                          <PermCheckbox checked={isChecked} disabled={readonly} />
                                          <span className={cn(
                                            "truncate transition-colors duration-200 leading-tight",
                                            readonly ? "text-muted-foreground" : isChecked ? "text-foreground font-medium" : "text-foreground/70 group-hover/perm:text-foreground",
                                          )}>
                                            {op.display_name}
                                          </span>
                                        </label>
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <div className="text-xs text-muted-foreground/50 px-1 pb-2">
                                    {pageVisible ? "暂无操作项" : "仅控制 tab 显隐"}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })
```

- [ ] **Step 4: AdminRolesPage 加状态与 handler**

`frontend/src/app/admin/roles/page.tsx` — AdminRolesPage 内：

1) 状态（detailNavSet 附近）：

```ts
  /* EAI-CUSTOM: which sub-pages are visible for the selected role (detail view) */
  const [detailPagesSet, setDetailPagesSet] = useState<Set<string>>(new Set());
```

2) 初始化 helper（initDataScopes 附近）：

```ts
  const initPageVisibility = (role: Role) => {
    setDetailPagesSet(resolveVisiblePages(registryModules || [], role.pages));
  };
```

3) `handleSelectRole` 与 `loadData` 里调用（与 initDataScopes 并列）；`useEffect`（registry 异步加载后补齐）里也调用：

```ts
        if (next) { initDataScopes(next); initPageVisibility(next); }
```

4) 传给 PermissionPanel 的 props 加 `enabledPages={detailPagesSet}` 与 `onPageToggle`：

```tsx
                      enabledPages={detailPagesSet}
                      onPageToggle={async (pageId, enabled) => {
                        const next = new Set(detailPagesSet);
                        enabled ? next.add(pageId) : next.delete(pageId);
                        setDetailPagesSet(next);
                        if (selectedRole && !selectedRole.is_system) {
                          try {
                            await roleApi.update(selectedRole.id, { pages: serializePages(next, registryModules || []) });
                          } catch (err: unknown) {
                            alert(err instanceof Error ? err.message : "更新页面可见性失败");
                          }
                        }
                      }}
```

- [ ] **Step 5: 写纯函数单测**

新建 `frontend/tests/unit/extensions/roles/page-visibility.test.ts`：

```ts
import { describe, expect, it } from "vitest";

import { allPageIds, resolveVisiblePages, serializePages } from "@/extensions/role/pageVisibility";
import type { RegistryModule } from "@/extensions/types";

const mods: RegistryModule[] = [
  { key: "knowledge_factory", display_name: "知识工厂", nav_id: "nav:knowledge-factory", pages: [
    { id: "kf:page:sample", display_name: "样例管理", operations: [] },
    { id: "kf:page:law", display_name: "法规标准", operations: [] },
  ], permissions: [], data_scopes: [] },
];

describe("page visibility helpers", () => {
  it("allPageIds collects page ids", () => {
    expect(allPageIds(mods)).toEqual(["kf:page:sample", "kf:page:law"]);
  });
  it("* or missing → all visible", () => {
    expect(resolveVisiblePages(mods, ["*"])).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
    expect(resolveVisiblePages(mods, undefined)).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
    expect(resolveVisiblePages(mods, [])).toEqual(new Set(["kf:page:sample", "kf:page:law"]));
  });
  it("explicit list → that set (unknown ids dropped)", () => {
    expect(resolveVisiblePages(mods, ["kf:page:law", "bogus"])).toEqual(new Set(["kf:page:law"]));
  });
  it("serializePages → * when all visible, else explicit", () => {
    expect(serializePages(new Set(["kf:page:sample", "kf:page:law"]), mods)).toEqual(["*"]);
    expect(serializePages(new Set(["kf:page:law"]), mods)).toEqual(["kf:page:law"]);
  });
});
```

- [ ] **Step 6: 验证**

Run: `cd frontend && pnpm exec vitest run page-visibility`
Expected: 5 passed

Run: `cd frontend && pnpm typecheck 2>&1 | grep -E "roles/page|pageVisibility|extensions/types" || echo "NO_NEW"`
Expected: no new errors in changed files（基线 ~127 允许）

- [ ] **Step 7: Commit**

```bash
git add frontend/src/extensions/types.ts frontend/src/extensions/role/pageVisibility.ts frontend/src/app/admin/roles/page.tsx frontend/tests/unit/extensions/roles/page-visibility.test.ts
git commit -m "feat(roles-ui): sub-page visibility switches in permission panel (hidden page ops grayed but retained)"
```

---

## Task 4: 前端 — 知识工厂 tab 按 canPage 过滤

**Files:**
- Modify: `frontend/src/app/knowledge-factory/page.tsx`
- Modify: `frontend/src/extensions/knowledge-factory/TabNavigation.tsx`

- [ ] **Step 1: page.tsx 过滤 NAV_ITEMS + TAB_COMPONENTS + activeTab 回退**

`frontend/src/app/knowledge-factory/page.tsx`：

1) `NAV_ITEMS` 每项加 `pageId`：

```ts
const NAV_ITEMS: { id: TabId; label: string; pageId: string }[] = [
  { id: "reports", label: "样例管理", pageId: "kf:page:sample" },
  { id: "extraction", label: "模板抽取", pageId: "kf:page:extraction" },
  { id: "editor", label: "模板编辑", pageId: "kf:page:template" },
  { id: "law", label: "法规标准", pageId: "kf:page:law" },
  { id: "rules", label: "合规规则", pageId: "kf:page:compliance" },
  { id: "version", label: "版本管理", pageId: "kf:page:version" },
  { id: "quality", label: "质量评估", pageId: "kf:page:quality" },
  { id: "scraper", label: "网页爬取", pageId: "kf:page:scrape" },
  { id: "dictionaries", label: "业务字典", pageId: "kf:page:dict" },
];
```

2) 组件内用 `usePermission` 过滤（镜像 settings 页模式）：

```ts
  const { canPage, isLoading: permLoading } = usePermission();
  const visibleNav = permLoading ? NAV_ITEMS : NAV_ITEMS.filter((n) => canPage(n.pageId));
  const currentTab = ((params.get("tab") ?? "reports") as TabId);
  const safeTab = visibleNav.some((n) => n.id === currentTab) ? currentTab : (visibleNav[0]?.id ?? "reports");
```

3) 渲染用 `visibleNav` 过滤后的列表；`safeTab` 替换 `currentTab`。传给 `TabNavigation` 的 `activeTab={safeTab}` 与 tab 切换仍用原 onTabChange（切到不可见 tab 会被回退逻辑拦下）。

- [ ] **Step 2: TabNavigation.tsx 过滤**

`frontend/src/extensions/knowledge-factory/TabNavigation.tsx` — 组件接收 `visibleIds` 或直接在组件内用 `usePermission`：

```ts
import { usePermission } from "@/core/permissions";

const NAV_ITEMS: (NavItem & { pageId: string })[] = [
  { id: "reports", label: "样例管理", icon: FileText, pageId: "kf:page:sample" },
  { id: "extraction", label: "模板抽取", icon: Settings, pageId: "kf:page:extraction" },
  { id: "editor", label: "模板编辑", icon: Edit3, pageId: "kf:page:template" },
  { id: "law", label: "法规标准", icon: Library, pageId: "kf:page:law" },
  { id: "rules", label: "合规规则", icon: ShieldCheck, pageId: "kf:page:compliance" },
  { id: "version", label: "版本管理", icon: GitBranch, pageId: "kf:page:version" },
  { id: "quality", label: "质量评估", icon: BarChart3, pageId: "kf:page:quality" },
  { id: "scraper", label: "网页爬取", icon: Globe, pageId: "kf:page:scrape" },
  { id: "dictionaries", label: "业务字典", icon: BookOpen, pageId: "kf:page:dict" },
];

export default function TabNavigation({ activeTab, onTabChange, collapsed = false, onToggleCollapse }: TabNavigationProps) {
  const { canPage, isLoading } = usePermission();
  const visibleItems = isLoading ? NAV_ITEMS : NAV_ITEMS.filter((n) => canPage(n.pageId));
  return (
    ... visibleItems.map((item) => ( ...现有渲染... ))
  );
}
```

- [ ] **Step 3: typecheck**

Run: `cd frontend && pnpm typecheck 2>&1 | grep -E "knowledge-factory|TabNavigation" || echo "NO_NEW"`
Expected: no new errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/knowledge-factory/page.tsx frontend/src/extensions/knowledge-factory/TabNavigation.tsx
git commit -m "feat(rbac): filter knowledge-factory tabs by canPage(pageId)"
```

---

## Task 5: 前端 — 合同价格子路由按 canPage 过滤

**Files:**
- Modify: `frontend/src/app/contract-price/layout.tsx`

- [ ] **Step 1: navItems 加 pageId + 过滤**

`frontend/src/app/contract-price/layout.tsx`：

```ts
import { usePermission } from "@/core/permissions";

const navItems = [
  { href: "/contract-price", label: "总览", icon: LayoutDashboard, exact: true, pageId: "cpa:page:overview" },
  { href: "/contract-price/contracts", label: "合同解析", icon: FileText, pageId: "cpa:page:contracts" },
  { href: "/contract-price/items", label: "分项校验", icon: ListChecks, pageId: "cpa:page:items" },
  { href: "/contract-price/clusters", label: "分组审核", icon: Boxes, pageId: "cpa:page:clusters" },
  { href: "/contract-price/tasks", label: "任务中心", icon: History, pageId: "cpa:page:tasks" },
  { href: "/contract-price/settings", label: "配置", icon: Settings, pageId: "cpa:page:settings" },
];

function ContractPriceLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  const visibleItems = isLoading ? navItems : navItems.filter((n) => canPage(n.pageId));

  return (
    ...
      <nav ...>
        {visibleItems.map(({ href, label, icon: Icon, exact }) => { ...现有渲染... })}
      </nav>
    ...
  );
}
```

隐藏子路由不主动跳转（避免影响深链）；若用户直达被隐藏路由，由后端 require_permission 兜底 403。

- [ ] **Step 2: typecheck**

Run: `cd frontend && pnpm typecheck 2>&1 | grep -E "contract-price" || echo "NO_NEW"`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/contract-price/layout.tsx
git commit -m "feat(rbac): filter contract-price sub-routes by canPage(pageId)"
```

---

## Task 6: 收尾回归

**Files:**
- 文档：`backend/CLAUDE.md`（若权限说明变更）

- [ ] **Step 1: 后端全量 plan 域测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_role_overlay_store.py tests/test_role_calibration.py tests/test_permission_engine.py tests/test_permission_registry.py tests/test_registry_overlay.py -q`
Expected: all passed

Ruff: `cd backend && uv run ruff check app/extensions/auth/registry.py app/extensions/schemas.py app/extensions/role/service.py`

- [ ] **Step 2: 前端 vitest + typecheck**

Run: `cd frontend && pnpm exec vitest run page-visibility && pnpm typecheck 2>&1 | grep -cE "error TS"`
Expected: vitest pass; typecheck count == 基线 127（无新增）

- [ ] **Step 3: 文档**

`backend/CLAUDE.md` 的 "Role / Permission System" 节追加一行：子页面可见性经 `RoleUpdate.pages` 写透 overlay，前端 `canPage(pageId)` 过滤知识工厂/合同价格 tab。

- [ ] **Step 4: Commit**

```bash
git add backend/CLAUDE.md
git commit -m "docs(rbac): note sub-page visibility (pages) + canPage tab filtering"
```

---

## Self-Review

**Spec 覆盖：**
- 3.1 UI（每子页面开关、置灰保留、0 操作页、n/m 计数、开关紧跟文字）→ Task 3 ✓
- 3.2 数据（RoleUpdate.pages 写透、`*` 默认、page id 校验、RoleResponse.pages）→ Task 1 ✓
- 3.3 接线（知识工厂 9 tab、合同价格 6 子视图、kf:page:extraction）→ Task 2/4/5 ✓
- 第 4 节边界（`*` 展开、并发写 409 沿用、未知 page id 拒绝、深层链接后端兜底）→ Task 1/5 ✓
- 第 6 节测试 → Task 1/3/6 ✓

**Type 一致性：** `page_id_exists`（registry）↔ `_FakeRegistry.page_id_exists` ✓；`get_page_ids_for_role`（registry）↔ `_FakeRegistry.get_page_ids_for_role` ✓；`resolveVisiblePages`/`serializePages`/`allPageIds`（Task 3 定义）在 Task 3 Step 4 与测试中一致使用 ✓；`Role.pages`/`UpdateRoleRequest.pages` 前后一致 ✓。

**已知留白：**
- 角色 `pages: []`（空显式）显示为"全可见"（前端 `resolveVisiblePages` 对空数组视为全量），而 `/me` 返回 `[]` 时 `canPage` 全 false —— 这是新角色无 pages 的显示兜底，写透一次后即一致；不在本计划内消除。
- 合同价格隐藏子路由不主动跳转（后端 require_permission 兜底），避免影响深链。
