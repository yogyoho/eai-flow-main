# 知识工厂权限简化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 知识工厂权限收敛为「模块可见 + 子 tab 可见」——删除 permissions.yaml 全部 kf:* 操作点，前端改为扁平子页卡片网格渲染。

**Architecture:** 两个独立工作块：(1) 数据层——permissions.yaml 删 9 组 kf:* 操作点 + sample 显示名改 + 角色默认/overlay 清理（保留 kf:page:* 页级 id）；(2) 前端——新增 `isVisibilityOnlyModule` 判定 + PermissionPanel 可见性纯模块网格渲染（TDD）。

**Tech Stack:** YAML / Python 3.12 / Next.js 16 / React 19 / Tailwind 4 / vitest

---

## 文件结构总览

| 文件 | 职责 | 操作 |
|---|---|---|
| `config/permissions.yaml` | 权限注册表 | 删 kf:* 操作点 + 改 sample 名 + 清 dept_head 引用 |
| `config/roles_custom.yaml` | 角色 overlay | 删 kf:* 操作 id（L99-107），保留 kf:page:*（L37-45） |
| `frontend/src/extensions/role/pageVisibility.ts` | 面板辅助函数 | 新增 `isVisibilityOnlyModule` |
| `frontend/src/app/admin/roles/page.tsx` | 面板组件 | PermissionPanel 增加可见性纯模块网格渲染 |
| `frontend/tests/unit/extensions/roles/page-visibility.test.ts` | 测试 | 新增 `isVisibilityOnlyModule` 测试 |

---

## Task 1: 数据层 —— permissions.yaml 删除知识工厂操作层

**Files:**
- Modify: `config/permissions.yaml:93-136`（knowledge_factory 模块）、`config/permissions.yaml:292-294`（dept_head 默认）

- [ ] **Step 1: 替换 knowledge_factory 模块定义**

`config/permissions.yaml` L93-136，将 `knowledge_factory` 模块的整个 pages 定义替换为（删除所有 operations，sample 显示名改 "样例管理"）：

```yaml
  # ─── 知识工厂（9 个 tab ↔ 9 个 page id）───
  knowledge_factory:
    display_name: "知识工厂"
    nav_id: "nav:knowledge-factory"
    pages:
      - id: "kf:page:sample"
        display_name: "样例管理"
      - id: "kf:page:extraction"
        display_name: "模板抽取"
      - id: "kf:page:template"
        display_name: "模板编辑"
      - id: "kf:page:law"
        display_name: "法规标准"
      - id: "kf:page:compliance"
        display_name: "合规规则"
      - id: "kf:page:version"
        display_name: "版本管理"
      - id: "kf:page:quality"
        display_name: "质量评估"
      - id: "kf:page:scrape"
        display_name: "网页爬取"
      - id: "kf:page:dict"
        display_name: "业务字典"
```

- [ ] **Step 2: 清理 dept_head 角色默认的 kf:* 引用**

`config/permissions.yaml` L292-294，从 dept_head 的 `permissions:` 列表删除：

```yaml
      - kf:read
      - kf:scrape:read
      - kf:law:read
```

删除后 dept_head 的 permissions 列表以 `- chapter:review` 收尾，直接接 `data_scopes:`。

- [ ] **Step 3: 验证 yaml 语法 + registry 解析**

```bash
cd /d/eai/eai-flow-main && python -c "import yaml; d=yaml.safe_load(open('config/permissions.yaml', encoding='utf-8')); kf=d['modules']['knowledge_factory']; print('yaml OK, kf pages:', len(kf['pages']), ', all have ops:', all('operations' in p or p.get('operations')==[] for p in kf['pages']))"
```

预期：`yaml OK, kf pages: 9, all have ops: True`（缺省 operations 视作空）。

- [ ] **Step 4: 运行 registry 测试确认无回归**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_registry_overlay.py -q
```

预期：PASS（若 3 个已知 pre-existing 失败出现，忽略——非本次引入）。

- [ ] **Step 5: Commit**

```bash
git add config/permissions.yaml
git commit -m "fix(rbac): remove knowledge factory operation layer from permissions.yaml (keep page-level canPage)"
```

---

## Task 2: 数据层 —— roles_custom.yaml 清理 kf:* 操作 id

**Files:**
- Modify: `config/roles_custom.yaml:99-107`

- [ ] **Step 1: 删除 kf:* 操作 id**

`config/roles_custom.yaml` L99-107，从 project_manager（或对应角色）的 `permissions:` 列表删除：

```yaml
    - kf:read
    - kf:template:edit
    - kf:template:publish
    - kf:law:read
    - kf:law:edit
    - kf:compliance:edit
    - kf:scrape:read
    - kf:scrape:execute
    - kf:dict:edit
```

**保留** L37-45 的 `kf:page:*`（页级 id，canPage 需要）。

- [ ] **Step 2: 验证**

```bash
cd /d/eai/eai-flow-main && grep -n "kf:" config/roles_custom.yaml
```

预期：只剩 `kf:page:*` 行（9 行），无 `kf:read`/`kf:template:*` 等操作 id。

```bash
python -c "import yaml; yaml.safe_load(open('config/roles_custom.yaml', encoding='utf-8')); print('roles_custom OK')"
```

预期：`roles_custom OK`。

- [ ] **Step 3: Commit**

```bash
git add config/roles_custom.yaml
git commit -m "fix(rbac): remove kf:* operation ids from roles_custom overlay (keep kf:page:* page ids)"
```

---

## Task 3: 前端 TDD —— isVisibilityOnlyModule 判定函数

**Files:**
- Modify: `frontend/src/extensions/role/pageVisibility.ts`
- Modify: `frontend/tests/unit/extensions/roles/page-visibility.test.ts`

- [ ] **Step 1: 写失败测试**

`frontend/tests/unit/extensions/roles/page-visibility.test.ts` 追加：

```ts
import { isVisibilityOnlyModule } from "@/extensions/role/pageVisibility";

const kfModule: RegistryModule = {
  key: "knowledge_factory", display_name: "知识工厂",
  pages: [
    { id: "kf:page:sample", display_name: "样例管理", operations: [] },
    { id: "kf:page:law", display_name: "法规标准", operations: [] },
  ],
  permissions: [], data_scopes: [],
};

describe("visibility-only module", () => {
  it("module whose pages all have no operations is visibility-only", () => {
    expect(isVisibilityOnlyModule(kfModule)).toBe(true);
  });
  it("module with any page having operations is NOT visibility-only", () => {
    expect(isVisibilityOnlyModule(singlePageMod)).toBe(false);
    expect(isVisibilityOnlyModule(mods[0])).toBe(false);
  });
  it("module with no pages is NOT visibility-only", () => {
    expect(isVisibilityOnlyModule(emptyMod)).toBe(false);
  });
});
```

（`singlePageMod`/`mods`/`emptyMod` 已在本测试文件上部定义；若 `kfModule` 与已定义变量冲突，用新名 `kfMod`。）

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && pnpm vitest run tests/unit/extensions/roles/page-visibility.test.ts`
Expected: FAIL with `isVisibilityOnlyModule is not a function`.

- [ ] **Step 3: 实现函数**

`frontend/src/extensions/role/pageVisibility.ts` 追加：

```ts
/** 可见性纯模块：pages 非空且全部子页无操作 → 只控制子页可见性，无操作网格。 */
export function isVisibilityOnlyModule(mod: RegistryModule): boolean {
  return !!mod.pages && mod.pages.length > 0 && mod.pages.every((p) => p.operations.length === 0);
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && pnpm vitest run tests/unit/extensions/roles/page-visibility.test.ts`
Expected: PASS（全部测试）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/role/pageVisibility.ts frontend/tests/unit/extensions/roles/page-visibility.test.ts
git commit -m "feat(roles-ui): add isVisibilityOnlyModule helper for flat page-grid modules"
```

---

## Task 4: 前端 —— PermissionPanel 可见性纯模块网格渲染

**Files:**
- Modify: `frontend/src/app/admin/roles/page.tsx`

**设计**：`isVisibilityOnlyModule(mod)` 时——模块头计数改为「可见 X/N 子页」、隐藏全选本组按钮、展开内容渲染子页卡片网格（名称 + 可见 Tag，点击切换）。

- [ ] **Step 1: 引入 isVisibilityOnlyModule**

`frontend/src/app/admin/roles/page.tsx` L20，import 追加：

```ts
import { isSinglePageModule, isVisibilityOnlyModule, resolveVisiblePages, serializePages, shouldHideModule } from "@/extensions/role/pageVisibility";
```

- [ ] **Step 2: 模块 map 内增加可见性纯模块派生变量**

在 L388-394（`totalOps`/`selectedCount`/`allCatSelected`/`ratio` 计算后）追加：

```tsx
          const visibilityOnly = isVisibilityOnlyModule(mod);
          const pageCount = mod.pages ? mod.pages.length : 0;
          const visiblePageCount = mod.pages
            ? mod.pages.filter((pg) => (enabledPages ? enabledPages.has(pg.id) : true)).length
            : 0;
          const pageRatio = pageCount > 0 ? visiblePageCount / pageCount : 0;
```

- [ ] **Step 3: 模块头计数与全选按钮逻辑**

L413 的计数 span 替换为（可见性纯模块显示「可见 X/N 子页」，否则保留原「选中 X/Y」）：

```tsx
                      <span className={cn("text-xs tabular-nums", moduleVisible ? "text-muted-foreground" : "text-muted-foreground/50")}>
                        {visibilityOnly ? `可见 ${visiblePageCount}/${pageCount} 子页` : `${selectedCount}/${totalOps}`}
                      </span>
```

L414-421 的进度条 `animate={{ width: `${ratio * 100}%` }}` 与 `ratio` 变量改为按模式取：

```tsx
                        <motion.span
                          className={cn("absolute inset-y-0 left-0 rounded-full", moduleVisible ? "bg-primary" : "bg-muted-foreground/30")}
                          initial={false}
                          animate={{ width: `${(visibilityOnly ? pageRatio : ratio) * 100}%` }}
                          transition={{ duration: 0.3, ease: "easeOut" }}
                        />
```

L430 全选本组按钮条件加 `&& !visibilityOnly`：

```tsx
                {!readonly && totalOps > 0 && !visibilityOnly && (
```

L404-408 模块图标高亮条件：可见性纯模块用「有可见子页」判定替代 `selectedCount > 0`：

```tsx
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors duration-200",
                    (visibilityOnly ? visiblePageCount > 0 : selectedCount > 0) && moduleVisible
                      ? "bg-primary/10 border border-primary/20"
                      : "bg-muted border border-border",
                  )}>
                    <Icon className={cn("w-4 h-4 transition-colors duration-200", (visibilityOnly ? visiblePageCount > 0 : selectedCount > 0) && moduleVisible ? "text-primary" : "text-muted-foreground")} />
                  </div>
```

- [ ] **Step 4: 展开内容 —— 可见性纯模块渲染子页网格**

在 L463 `{singlePage ? (` 之前插入分支（L462 `<div className={cn("px-3 pb-3 pt-1", ...)}>` 之后）：

```tsx
                      {visibilityOnly ? (
                        /* 可见性纯模块：扁平子页卡片网格，每卡 = 名称 + 可见 Tag */
                        <div className="grid gap-1.5" style={gridStyle}>
                          {mod.pages!.map((page) => {
                            const pageVisible = enabledPages ? enabledPages.has(page.id) : true;
                            return (
                              <button
                                key={page.id}
                                type="button"
                                onClick={() => { if (!readonly) onPageToggle(page.id, !pageVisible); }}
                                disabled={readonly}
                                className={cn(
                                  "flex items-center gap-2.5 text-sm p-2 rounded-lg transition-all duration-200 min-w-0 select-none",
                                  readonly ? "cursor-default" : "cursor-pointer",
                                  pageVisible
                                    ? "bg-primary/[0.04] border border-primary/10"
                                    : "border border-transparent hover:bg-accent/50 hover:border-border",
                                )}
                              >
                                <span className={cn("truncate leading-tight", readonly ? "text-muted-foreground" : pageVisible ? "text-foreground font-medium" : "text-foreground/70 group-hover/perm:text-foreground")}>
                                  {highlight(page.display_name)}
                                </span>
                                <span className={cn(
                                  "ml-auto shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium border",
                                  pageVisible
                                    ? "bg-primary/10 text-primary border-primary/20"
                                    : "bg-muted text-muted-foreground border-transparent",
                                )}>
                                  <span className={cn("w-1.5 h-1.5 rounded-full", pageVisible ? "bg-primary" : "bg-muted-foreground/50")} />
                                  {pageVisible ? "可见" : "不可见"}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      ) : singlePage ? (
```

- [ ] **Step 5: 类型检查**

```bash
cd frontend && pnpm typecheck
```

预期：仅剩 2 个 pre-existing 错误（`admin/roles/page.tsx` 的 PolicyCondition/PolicyGrant，非本次引入）。

- [ ] **Step 6: 手动验证（浏览器）**

重启 frontend 容器后打开 `http://localhost:2026/admin/roles`，选中部门负责人：
- 知识工厂卡片头显示「可见 9/9 子页」+ 进度条满格。
- 展开后 9 个子页卡片网格，每卡 = 名称 + 可见 Tag。
- 点击某卡 Tag → 对应 tab 消失、计数减一。
- 其他模块（报告项目/合同价格）仍为操作网格。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/admin/roles/page.tsx
git commit -m "feat(roles-ui): render visibility-only modules as flat sub-page card grid"
```

---

## Task 5: 全量验证

- [ ] **Step 1: 前端测试 + 类型检查**

```bash
cd frontend && pnpm vitest run tests/unit/extensions/roles/ && pnpm typecheck
```

预期：roles 测试全过；typecheck 仅 pre-existing 错误。

- [ ] **Step 2: 后端 registry 测试**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_registry_overlay.py tests/test_role_calibration.py -q
```

预期：PASS（3 个已知 pre-existing registry 失败除外）。

- [ ] **Step 3: 容器重启 + 浏览器回归**

```bash
docker compose -p eai-docker restart frontend
```

浏览器验证：
- 知识工厂卡片 = 可见子页计数 + 子页卡片网格。
- 切换子页可见 → tab 消失；模块不可见 → 侧边栏入口消失。
- 搜索"法规" → 知识工厂展开并高亮法规标准卡。
- 系统角色（超级管理员）只读置灰。

- [ ] **Step 4: Commit 收尾**

```bash
git add -A && git commit -m "test: verify knowledge factory permission simplify end-to-end"
```

---

## 自审记录

- **Spec 覆盖**：①数据层删 kf:* 操作点 + sample 改名 + dept_head 清理（Task 1）✓；roles_custom 清理（Task 2）✓；②`isVisibilityOnlyModule` 判定（Task 3）✓；面板网格渲染 + 模块头计数 + 隐藏全选本组（Task 4）✓；③测试验证（Task 5）✓。
- **占位符**：无 TBD/TODO；所有代码步骤给出完整内容。
- **类型一致性**：`isVisibilityOnlyModule` 在 Task 3 定义、Task 4 消费，签名一致；`visibilityOnly`/`visiblePageCount`/`pageRatio` 在 Task 4 Step 2 定义、Step 3/4 使用，命名一致。
- **注意**：Task 4 Step 4 需注意 JSX 括号嵌套（在 `{singlePage ? (` 前插入分支需闭合 `) :`）；执行时若 typecheck 报括号错配，按报错行修正闭合。已知 pre-existing 失败（3 registry + 2 skill_permissions + 5 collection errors）均为基线问题，非本次引入。
