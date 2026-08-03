# 知识工厂 · 权限划分简化设计

> 日期：2026-08-03 | 状态：已批准
> 范围：角色管理「操作权限」tab 中知识工厂模块 —— 删除操作层，收敛为「模块可见 + 子 tab 可见」，子页以网格卡片呈现

## 1. 背景与审计发现

角色管理「操作权限」tab 的知识工厂模块当前是 模块 → 子页 → 操作 三级结构，9 个子页各带一组 `kf:*` 操作点。经审计：

| 现状 | 证据 | 结论 |
|---|---|---|
| 页级可见性已接线 | `TabNavigation.tsx` 用 `canPage(kf:page:*)` 过滤 9 个 tab | ✅ 生效 |
| 模块级可见已接线 | `nav:knowledge-factory` 控制侧边栏入口 | ✅ 生效 |
| **操作层零强制** | `knowledge_factory/routers.py:89` 与 `law/routers.py:42` 全部 `require_permission("system:access")`；`kf:read/kf:template:edit/kf:law:*/kf:compliance:*/kf:scrape:*/kf:dict:*` 从未出现在任何 `require_permission()` | ❌ 纯摆设 |
| **操作层零消费** | 知识工厂前端组件无任何 `can()`/`hasPermission` 调用 | ❌ 纯摆设 |
| 命名歧义 | `kf:page:sample` 显示名 "样例管理/模板抽取"（带斜杠）；`kf:read` 在 sample/extraction/template 三页重复声明 | ⚠️ 需清理 |

**结论**：操作层是不生效的 UI 装饰。用户决策：知识工厂权限控制收敛为「模块可见 + 子 tab 可见」，彻底删除操作层。

## 2. 目标

1. 从 `permissions.yaml` 彻底删除知识工厂全部 `kf:*` 操作点（数据层简化）。
2. 角色默认引用清理（`dept_head` 的 `kf:read`/`kf:scrape:read`/`kf:law:read`）。
3. 前端知识工厂模块改为**扁平子页网格**：模块卡片 → 9 个子页卡片网格，每卡 = 名称 + 可见 Tag，点击切换；模块头显示「可见 X/9」。
4. 其他模块（合同价格/系统管理等有操作项的）不受影响。

## 3. 设计

### 3.1 数据层（config/permissions.yaml）

`knowledge_factory` 模块的 9 个 `pages` 全部删除 `operations:`（纯页级定义）：

```yaml
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

**同时**：
- `kf:page:sample` 显示名改为 `"样例管理"`（去掉 "/模板抽取" 歧义——模板抽取已是独立 tab）。
- 角色默认清理：`dept_head`（原 L292-294）的 `kf:read` / `kf:scrape:read` / `kf:law:read` 三项删除。

**兼容性**：registry 解析器 `p.get("operations") or []` 天然处理缺省 operations；`PageDef` 照常注册，`canPage(kf:page:*)` 不受影响。`roles_custom.yaml` 需检查是否有 kf:* 引用。

### 3.2 前端面板（frontend/src/app/admin/roles/page.tsx）

`PermissionPanel` 增加**「可见性纯模块」渲染模式**：判定 `pages.every(p => p.operations.length === 0)`（全部子页无操作 → 可见性纯模块）。渲染：

```
┌─ 知识工厂 ──────── [可见 7/9] ▾ ┐
│ 模块可见 [●───────○]              │
│ ┌─────────┐ ┌─────────┐ ┌───────┐ │
│ │ 样例管理  │ │ 模板抽取  │ │ 模板编辑│ │
│ │ ◉可见    │ │ ◉可见    │ │ ◉可见  │ │
│ └─────────┘ └─────────┘ └───────┘ │
│ ...(auto-fill 网格自适应换行)      │
└─────────────────────────────────────┘
```

具体改动：
1. **判定函数**：新增 `isVisibilityOnlyModule(mod)`（`pages` 非空且全部 `operations.length === 0`）。放 `pageVisibility.ts` 便于测试。
2. **模块头**：
   - 计数从「选中操作 X/Y」改为「可见子页 X/N」（N = pages.length，X = 可见数）。
   - 进度条照画（比例 = X/N）。
   - `全选本组` 按钮**隐藏**（无可选操作）。
   - 模块可见开关保留（沿用 `onNavToggle`）。
3. **展开内容**：直接渲染子页网格，每卡复用现有操作卡样式（`group/perm flex items-center gap-2.5 ... p-2 rounded-lg`），卡内 = 名称 + 可见 Tag（沿用已实现的状态 Tag：`◉可见`/`◌不可见`）。点击卡片切换 `onPageToggle(page.id, !pageVisible)`。无操作网格、无"暂无操作项"占位。
4. **计数来源**：页可见数用 `enabledPages`（现有 `resolveVisiblePages` 产物）统计。

### 3.3 边界

- **其他模块不受影响**：有操作项的模块（合同价格、系统管理、设置等）仍走三级树 + 操作网格。
- **只读态**：系统角色（superadmin）整体置灰，沿用现有 readonly。
- **搜索**：搜索框匹配子页名 `display_name`，命中即展开并高亮——现有 `highlight()` 在子页名上继续生效。

## 4. 文件清单

**数据层**
- `config/permissions.yaml` — 删 kf:* 操作点、改 sample 显示名、清 dept_head 角色默认引用
- `config/roles_custom.yaml` — **只清理 permissions 列表中的 kf:* 操作 id（L99-107：`kf:read`/`kf:template:edit`/`kf:template:publish`/`kf:law:read`/`kf:law:edit`/`kf:compliance:edit`/`kf:scrape:read`/`kf:scrape:execute`/`kf:dict:edit`）**；`pages:` 列表中的 `kf:page:*`（L37-45）是页级 id，保留不动（页面仍存在，canPage 需要）

**前端**
- `frontend/src/extensions/role/pageVisibility.ts` — 新增 `isVisibilityOnlyModule`
- `frontend/src/app/admin/roles/page.tsx` — PermissionPanel 增加可见性纯模块网格渲染（模块头计数/隐藏全选本组/子页网格）
- `frontend/tests/unit/extensions/roles/page-visibility.test.ts` — 新增 `isVisibilityOnlyModule` 测试

## 5. 测试

- **前端 vitest**：
  - `isVisibilityOnlyModule`：全空 operations → true；任一页有操作 → false；无 pages → false。
  - 可见子页计数推导（`resolveVisiblePages` 产物统计）。
- **后端**：registry 测试确认无 operations 的 pages 仍被解析、`/me` pages 展开正常（现有 `test_registry_overlay.py` 已覆盖，跑一遍确认）。
- **手动**：admin 打开角色管理 → 知识工厂卡片只显示 9 个子页卡片网格；点击切换不可见 → 对应 tab 消失、计数更新；模块不可见 → 侧边栏入口消失。

## 6. 非目标 / 延后

- 不为知识工厂操作层"接线"（后端挂 require_permission）——本轮明确不做。
- 其他模块操作层是否也简化（合同价格、系统管理等），后续单独评估。
- `kf:page:sample` 已从 "样例管理/模板抽取" 改为 "样例管理"——若实际业务希望该页语义含模板抽取，需另行确认（本轮按 tab 名对齐）。
