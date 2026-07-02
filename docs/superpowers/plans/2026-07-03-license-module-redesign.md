# License 模块控制重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 license 许可模块从 8 键收敛为 4 键（`project` / `dashboard` / `typography` / `contract_price`），同步全部 5 处硬编码定义点，并给 docmgr「项目文件夹」加 `project` 守卫。

**Architecture:** 不改 license 架构（JWT+RSA、机器绑定、宽限期、dev_mode、前端闸门、后端不拦截）。仅改模块分类——同步 5 处定义点 + 一次性 SQL 迁移修存量库 + docmgr 子视图守卫。硬切换、无向后兼容（已确认线上无正式 `.lic`）。

**Tech Stack:** Python 3.12（backend）、TypeScript/React（frontend）、PostgreSQL（app_definitions 表）、pytest、Docker（`-p eai-docker`）。

**Spec:** [`docs/superpowers/specs/2026-07-03-license-module-redesign-design.md`](../specs/2026-07-03-license-module-redesign-design.md)

**分支:** `main-dev-fork`（所有提交到此分支，不提交 main）

---

## File Structure

| 文件 | 动作 | 责任 |
|---|---|---|
| `backend/tests/test_license_modules_sync.py` | Create | 同步守卫测试：锁住 4 键在 5 处定义点一致 |
| `backend/app/extensions/license/service.py` | Modify (L30-33) | `ALL_MODULES` → 4 键 |
| `tools/license/license_generator.py` | Modify (L28-31, L72-73) | `ALL_MODULES` + 默认 modules_dict → 4 键 |
| `frontend/src/extensions/license/ModuleLockedPage.tsx` | Modify (L8-17) | `MODULE_LABELS` → 4 键 |
| `frontend/src/extensions/shell/Sidebar.tsx` | Modify (L48-53) | 侧边栏 nav `licenseModule` 重映射 |
| `backend/app/extensions/database.py` | Modify (~L1483-1514) | 种子 apps 的 `license` 值 |
| `scripts/migrate_license_modules_v2.sql` | Create | 一次性 UPDATE 迁移（修存量库） |
| `frontend/src/extensions/docmgr/DocumentManagement.tsx` | Modify (L37, L77, L237-264) | 项目文件夹区段加 `project` 守卫 |

---

## Task 1: 写同步守卫测试（先红）

**Files:**
- Create: `backend/tests/test_license_modules_sync.py`

- [ ] **Step 1: 写测试文件**

```python
"""License module key sync guard.

Locks the canonical 4-key license module set and ensures every hardcoded
definition site stays in sync. Drift causes silent breakage: a key renamed in
one place but not others makes licensed apps vanish from sidebar/app-center
(hasModule returns false for the stale key).

Canonical keys: project, dashboard, typography, contract_price
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_KEYS = ["project", "dashboard", "typography", "contract_price"]
REMOVED_KEYS = ["docmgr", "knowledge", "collab", "report", "approval", "workflow"]


def test_service_all_modules_is_canonical():
    from app.extensions.license.service import ALL_MODULES

    assert ALL_MODULES == EXPECTED_KEYS


def test_generator_all_modules_is_canonical():
    src = (REPO_ROOT / "tools" / "license" / "license_generator.py").read_text(encoding="utf-8")
    m = re.search(r"ALL_MODULES = \[\s*([^\]]*)\]", src)
    assert m, "ALL_MODULES not found in license_generator.py"
    keys = [k.strip().strip('"').strip("'") for k in m.group(1).split(",") if k.strip()]
    assert keys == EXPECTED_KEYS


def test_module_locked_page_labels_match_canonical():
    src = (
        REPO_ROOT / "frontend" / "src" / "extensions" / "license" / "ModuleLockedPage.tsx"
    ).read_text(encoding="utf-8")
    for key in EXPECTED_KEYS:
        assert re.search(rf"\b{key}:\s*\"", src), f"ModuleLockedPage missing label for {key}"
    for removed in REMOVED_KEYS:
        assert not re.search(rf"\b{removed}:\s*\"", src), (
            f"ModuleLockedPage still references removed key '{removed}'"
        )


def test_sidebar_nav_licensing_matches_classification():
    src = (REPO_ROOT / "frontend" / "src" / "extensions" / "shell" / "Sidebar.tsx").read_text(
        encoding="utf-8"
    )
    # 收费项必须带正确 licenseModule
    assert re.search(r'href: "/dashboard"[^}]*licenseModule: "dashboard"', src, re.S)
    assert re.search(r'href: "/projects"[^}]*licenseModule: "project"', src, re.S)
    # 免费项不得带 licenseModule
    for free in ["/docmgr", "/knowledge-factory", "/knowledge"]:
        m = re.search(rf'href: "{free}"[^}}]*\}}', src)
        assert m, f"{free} nav item not found in Sidebar.tsx"
        assert "licenseModule" not in m.group(0), f"{free} should be free but has licenseModule"


def test_seed_uses_no_removed_license_keys():
    src = (REPO_ROOT / "backend" / "app" / "extensions" / "database.py").read_text(encoding="utf-8")
    for removed in REMOVED_KEYS:
        assert f'"license": "{removed}"' not in src, (
            f"database.py seed still uses removed license key '{removed}'"
        )
```

- [ ] **Step 2: 运行测试，确认 RED（当前 8 键，必然失败）**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_license_modules_sync.py -v`
Expected: 5 个测试全部 FAIL（`ALL_MODULES == ['project','docmgr',...] != EXPECTED_KEYS` 等）。这一步只为证明测试能抓住漂移，不提交。

---

## Task 2: service.ALL_MODULES → 4 键

**Files:**
- Modify: `backend/app/extensions/license/service.py` (L30-33)

- [ ] **Step 1: 替换 ALL_MODULES**

old:
```python
ALL_MODULES = [
    "project", "docmgr", "knowledge", "collab",
    "report", "approval", "workflow", "dashboard",
]
```

new:
```python
ALL_MODULES = [
    "project",
    "dashboard",
    "typography",
    "contract_price",
]
```

> `LicensePayload.dev_mode()` 用 `{m: True for m in ALL_MODULES}`，自动跟随，无需另改。

- [ ] **Step 2: 跑测试，确认 service 那条变绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_license_modules_sync.py::test_service_all_modules_is_canonical -v`
Expected: PASS（其余仍 FAIL）。

- [ ] **Step 3: 提交**

```bash
git add backend/app/extensions/license/service.py
git commit -m "feat(license): ALL_MODULES 收敛为 4 键 (project/dashboard/typography/contract_price)"
```

---

## Task 3: license_generator.ALL_MODULES + 默认 → 4 键

**Files:**
- Modify: `tools/license/license_generator.py` (L28-31, L72-73)

- [ ] **Step 1: 替换 ALL_MODULES（L28-31）**

old:
```python
ALL_MODULES = [
    "project", "docmgr", "knowledge", "collab",
    "report", "approval", "workflow", "dashboard",
]
```

new:
```python
ALL_MODULES = [
    "project",
    "dashboard",
    "typography",
    "contract_price",
]
```

- [ ] **Step 2: 改默认 modules_dict（L72-73）**

old:
```python
    else:
        modules_dict = {"project": True, "docmgr": True}
```

new:
```python
    else:
        modules_dict = {m: True for m in ALL_MODULES}
```

> 旧默认含 `docmgr`（已非许可键）；新默认给 4 键全 True，`--modules` 仍可裁剪。

- [ ] **Step 3: 跑测试，确认 generator 那条变绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_license_modules_sync.py::test_generator_all_modules_is_canonical -v`
Expected: PASS。

- [ ] **Step 4: 提交**

```bash
git add tools/license/license_generator.py
git commit -m "feat(license): generator ALL_MODULES 与默认 modules 对齐 4 键"
```

---

## Task 4: ModuleLockedPage.MODULE_LABELS → 4 键

**Files:**
- Modify: `frontend/src/extensions/license/ModuleLockedPage.tsx` (L8-17)

- [ ] **Step 1: 替换 MODULE_LABELS**

old:
```tsx
const MODULE_LABELS: Record<string, string> = {
  project: "项目管理",
  docmgr: "文档管理",
  knowledge: "知识库",
  collab: "协同编辑",
  report: "报告生成",
  approval: "审批流程",
  workflow: "工作流",
  dashboard: "仪表盘",
};
```

new:
```tsx
const MODULE_LABELS: Record<string, string> = {
  project: "项目协作",
  dashboard: "工作台",
  typography: "报告输出",
  contract_price: "合同价格分析",
};
```

- [ ] **Step 2: 跑测试，确认 ModuleLockedPage 那条变绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_license_modules_sync.py::test_module_locked_page_labels_match_canonical -v`
Expected: PASS。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/extensions/license/ModuleLockedPage.tsx
git commit -m "feat(license): ModuleLockedPage 标签对齐 4 键"
```

---

## Task 5: Sidebar nav licenseModule 重映射

**Files:**
- Modify: `frontend/src/extensions/shell/Sidebar.tsx` (L48-53)

- [ ] **Step 1: 替换 nav 项（L48-53）**

old:
```tsx
  { href: "/dashboard", label: "工作台", icon: LayoutDashboard },
  { href: "/writing", label: "智能写作", icon: Bot, newTab: true },
  { href: "/projects", label: "报告项目", icon: ClipboardList, licenseModule: "project" },
  { href: "/docmgr", label: "文档空间", icon: FolderCheck, licenseModule: "docmgr" },
  { href: "/knowledge-factory", label: "知识工厂", icon: Factory, licenseModule: "knowledge" },
  { href: "/knowledge", label: "知识库", icon: BookOpen, licenseModule: "knowledge" },
```

new:
```tsx
  { href: "/dashboard", label: "工作台", icon: LayoutDashboard, licenseModule: "dashboard" },
  { href: "/writing", label: "智能写作", icon: Bot, newTab: true },
  { href: "/projects", label: "报告项目", icon: ClipboardList, licenseModule: "project" },
  { href: "/docmgr", label: "文档空间", icon: FolderCheck },
  { href: "/knowledge-factory", label: "知识工厂", icon: Factory },
  { href: "/knowledge", label: "知识库", icon: BookOpen },
```

> 漏改此项 → 免费模块在侧边栏消失（`hasModule("docmgr")` 键不存在恒 false）。

- [ ] **Step 2: 跑测试，确认 Sidebar 那条变绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_license_modules_sync.py::test_sidebar_nav_licensing_matches_classification -v`
Expected: PASS。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/extensions/shell/Sidebar.tsx
git commit -m "feat(license): Sidebar nav licenseModule 对齐新分类"
```

---

## Task 6: database.py 种子 license 值

**Files:**
- Modify: `backend/app/extensions/database.py` (~L1483-1514, apps 列表)

- [ ] **Step 1: 替换 apps 列表中的 license 字段**

逐行改 `license` 值（其余字段不动）：

| app_id | 旧 | 新 |
|---|---|---|
| `dashboard` | `None` | `"dashboard"` |
| `docmgr` | `"docmgr"` | `None` |
| `knowledge-factory` | `"knowledge"` | `None` |
| `knowledge` | `"knowledge"` | `None` |
| `output` | `"report"` | `"typography"` |
| `procurement` | `None` | `"contract_price"` |
| `workflow-admin` | `None` | `"project"` |

改后这段形如（仅示 dashboard / docmgr / output / procurement / workflow-admin 行有变，按上表对齐）：

```python
                apps = [
                    {"app_id": "dashboard", "name": "工作台", ...,
                     "path": "/dashboard", "license": "dashboard", "admin": False, "sort": 1, ...},
                    {"app_id": "smart-writing", ...,
                     "path": "/writing", "license": None, ...},
                    {"app_id": "projects", ...,
                     "path": "/projects", "license": "project", ...},
                    {"app_id": "docmgr", "name": "文档空间", ...,
                     "path": "/docmgr", "license": None, ...},
                    {"app_id": "knowledge-factory", ...,
                     "path": "/knowledge-factory", "license": None, ...},
                    {"app_id": "knowledge", ...,
                     "path": "/knowledge", "license": None, ...},
                    {"app_id": "output", "name": "报告输出", ...,
                     "path": "/output", "license": "typography", ...},
                    {"app_id": "procurement", "name": "采购管理", ...,
                     "path": "/contract-price", "license": "contract_price", ...},
                    {"app_id": "admin", ...,
                     "path": "/admin", "license": None, "admin": True, ...},
                    {"app_id": "workflow-admin", "name": "流程管理", ...,
                     "path": "/workflow-admin", "license": "project", "admin": True, ...},
                ]
```

- [ ] **Step 2: 跑测试，确认 seed 那条变绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_license_modules_sync.py::test_seed_uses_no_removed_license_keys -v`
Expected: PASS。

- [ ] **Step 3: lint**

Run: `cd backend && make lint`
Expected: 通过（行宽 240，双引号）。

- [ ] **Step 4: 提交**

```bash
git add backend/app/extensions/database.py
git commit -m "feat(license): app-center 种子 license_module 对齐新分类"
```

---

## Task 7: 同步测试全绿 + 提交测试

**Files:**
- (无新文件改动，仅验证 Task 1 的测试文件)

- [ ] **Step 1: 跑完整同步测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_license_modules_sync.py -v`
Expected: 5 passed（5 处定义点现已全部对齐 4 键）。

- [ ] **Step 2: 提交测试文件**

```bash
git add backend/tests/test_license_modules_sync.py
git commit -m "test(license): 加 4 键 5 处定义点同步守卫"
```

---

## Task 8: 一次性 SQL 迁移脚本

**Files:**
- Create: `scripts/migrate_license_modules_v2.sql`

- [ ] **Step 1: 写迁移脚本**

```sql
-- 一次性迁移：把 app_definitions.license_module 对齐 v2 四键方案。
-- 在每个已存在的部署上、签发首张正式 license 之前跑一次。幂等。
-- 新部署靠 database.py 种子自动得到正确值，无需跑此脚本。
--
-- 运行方式（扩展库 postgres 容器内）：
--   docker exec -i eai-docker-postgres-ext-1 psql -U agentflow -d agentflow < scripts/migrate_license_modules_v2.sql
-- 先确认容器名：docker compose -p eai-docker ps

BEGIN;

UPDATE app_definitions SET license_module = 'dashboard'      WHERE app_id = 'dashboard';
UPDATE app_definitions SET license_module = NULL             WHERE app_id IN ('docmgr', 'knowledge', 'knowledge-factory');
UPDATE app_definitions SET license_module = 'typography'     WHERE app_id = 'output';
UPDATE app_definitions SET license_module = 'contract_price' WHERE app_id = 'procurement';
UPDATE app_definitions SET license_module = 'project'        WHERE app_id = 'workflow-admin';

COMMIT;

-- 验证：非空 license_module 应只含 4 个键
-- SELECT app_id, license_module FROM app_definitions WHERE license_module IS NOT NULL ORDER BY app_id;
```

- [ ] **Step 2: 执行迁移（存量库；dev_mode 下无害但务必在出正式证前做）**

Run: `docker exec -i eai-docker-postgres-ext-1 psql -U agentflow -d agentflow < scripts/migrate_license_modules_v2.sql`
Expected: `BEGIN` ×1 / `UPDATE N` ×5 / `COMMIT` ×1。

- [ ] **Step 3: 验证存量值**

Run: `docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT app_id, license_module FROM app_definitions WHERE license_module IS NOT NULL ORDER BY app_id;"`
Expected: 仅 dashboard(dashboard) / output(typography) / procurement(contract_price) / projects(project) / workflow-admin(project) 五行，值都在 4 键内。

- [ ] **Step 4: 提交**

```bash
git add scripts/migrate_license_modules_v2.sql
git commit -m "feat(license): 存量库 license_module 一次性迁移脚本 v2"
```

---

## Task 9: docmgr 项目文件夹区段加 project 守卫

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx` (L37, L77, L237-264)

- [ ] **Step 1: 加 useLicense import（L37 后）**

在 `import { useFolderTree } from "./useFolderTree";` 之后新增一行：

```tsx
import { useLicense } from "@/extensions/license/useLicense";
```

- [ ] **Step 2: 在 DocumentList 组件体内加守卫变量（L77 `archiveOpen` 声明后）**

在 `const [archiveOpen, setArchiveOpen] = useState(true);` 之后新增：

```tsx
  // 项目文件夹是 project 许可的子能力；未授权则隐藏整段（含 CollabEditor 入口）
  const { hasModule, isLoading: licenseLoading } = useLicense();
  const canUseProject = licenseLoading || hasModule("project");
```

> 必须加在 `DocumentList`（L68 起的 `function DocumentList(...)`）体内，不是 `DocumentManagement`——项目文件夹区段由 DocumentList 渲染。加载中先显示，与 Sidebar/useApps 一致。

- [ ] **Step 3: 包裹「项目文件夹」区段（L237-264）**

把这一段：

```tsx
          {/* 项目文件夹 - 树形结构 */}
          <div className="pt-2 mt-2">
            <button
              onClick={() => setArchiveOpen((v) => !v)}
              className="..."
            >
              ...
            </button>
            {archiveOpen && (
              <ProjectFolderTree ... />
            )}
          </div>
```

改为（外层加 `{canUseProject && (<> ... </>)}`）：

```tsx
          {canUseProject && (
            <>
              {/* 项目文件夹 - 树形结构 */}
              <div className="pt-2 mt-2">
                <button
                  onClick={() => setArchiveOpen((v) => !v)}
                  className="..."
                >
                  ...
                </button>
                {archiveOpen && (
                  <ProjectFolderTree ... />
                )}
              </div>
            </>
          )}
```

> 实操：以 `{/* 项目文件夹 - 树形结构 */}` 注释为锚点，在该注释前插 `{canUseProject && (<>`，在该区段原 `</div>`（ProjectFolderTree 那个 `<div className="pt-2 mt-2">` 的闭合）后插 `</>)}`。区段内部缩进可保持不变。

- [ ] **Step 4: typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: 无错误。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr): 项目文件夹区段加 project 许可守卫"
```

---

## Task 10: 端到端验证

**Files:** 无（验证步骤）

- [ ] **Step 1: 重启受影响容器**

```bash
docker compose -p eai-docker restart gateway frontend
```

> gateway 读 service.py；frontend 编译 .tsx。database.py 种子改动只影响新部署（ON CONFLICT DO NOTHING），存量值已由 Task 8 迁移修正。

- [ ] **Step 2: 验证 /api/license/status（dev_mode 下 modules 应含 4 键全 true）**

Run: `curl -s http://localhost:2026/api/license/status | python -m json.tool`
Expected: `is_dev_mode: true`，`modules` 含且仅含 `project/dashboard/typography/contract_price` 四键（dev_mode 全 true）。

- [ ] **Step 3: 后端全量测试不回归**

Run: `cd backend && make test`
Expected: 全绿（含新增 test_license_modules_sync.py）。

- [ ] **Step 4: 前端检查**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: 通过。

- [ ] **Step 5: 手动验证（浏览器 http://localhost:2026）**

- 侧边栏：工作台/报告项目/文档空间/知识工厂/知识库/应用中心/系统管理 均可见（dev_mode 全开）。
- 文档空间（/docmgr）：左侧「项目文件夹」区段可见（dev_mode 下 canUseProject=true）。
- 应用中心：dashboard / output(报告输出) / contract-price(采购管理) / projects / workflow-admin 均可见。

> 若要验证「未授权隐藏」效果：临时关 dev_mode、删 license.lic 触发宽限期外状态不现实（会锁系统）。dev_mode/grace 下 hasModule 恒 true 是预期行为；真实验证留待签发首张受限 license 后做。

---

## Self-Review Notes

- **Spec 覆盖**：5 处同步点（Task 2-6）+ 迁移（Task 8）+ docmgr 守卫（Task 9）+ 测试（Task 1/7）全覆盖 spec 的「5 处同步点」「不变项」「向后兼容（不做）」「测试」「风险与边界」。collab 不需单独守卫（spec 已说明，CollabEditor 仅 project_id 文档渲染，入口被 /projects + docmgr 项目文件夹挡住）。
- **占位符**：无 TBD；每步含完整代码或确切命令。
- **类型一致**：4 键字符串 `project/dashboard/typography/contract_price` 全文一致；`canUseProject`、`licenseLoading` 命名前后一致。
