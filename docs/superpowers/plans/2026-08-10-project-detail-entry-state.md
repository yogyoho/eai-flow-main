# 项目详情页 · 入口态与分工视图 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把项目详情页 OverviewTab「章节进度」区块从"总是铺开大纲树"改成状态驱动（未生成 / 生成中 / 人工修改确认），CTA 接既有 `start-workflow` 端点，并新增 `ReportProject.assignment_strategy` 字段（`by_chapter` / `by_role`，默认 `by_chapter`）驱动「人工修改确认」态的分工叠加层。

**Architecture:** 纯前端从现成信号（`temporalWorkflowId` + `chapter.content` 是否存在）派生 3 态状态机；后端只加一个字段 + 迁移 + schema/router/service 透传，**零新端点**（CTA 复用 `workflowApi.startWorkflow`）。`by_chapter` 复用现有 `ChapterNode`/`KanbanBoard`，`by_role` 新增角色分组看板。所有改动在 app 层 `extensions/`，不碰 harness 核心。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / Pydantic（后端）；Next.js 16 / React 19 / TypeScript 5.8 / Tailwind 4 / Rstest（前端）；PostgreSQL（Docker `eai-docker`）。

**Spec:** `docs/superpowers/specs/2026-08-10-project-detail-entry-state-design.md`（commit d70791a3b）

**Branch:** `main-dev-fork`（所有提交到此分支，不提交 main）

---

## File Structure

**后端（3 文件改动）：**
- `backend/app/extensions/project/schemas.py` — `ProjectCreate`/`ProjectUpdate`/`ProjectOut` 各加 `assignment_strategy` 字段（Task 1）
- `backend/app/extensions/models/__init__.py` — `ReportProject` ORM 加列（Task 2）
- `backend/app/extensions/database.py` — 幂等迁移 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`（Task 2）
- `backend/app/extensions/project/routers.py` — create 端点透传字段（Task 2）
- `backend/app/extensions/project/service.py` — `create_project` 加形参 + ORM 赋值（Task 2；update 路径由 `model_dump(exclude_unset=True)` 自动透传，无需改）

**后端测试（1 文件改动）：**
- `backend/tests/test_project_schemas.py` — 加 `assignment_strategy` schema 测试（Task 1）

**前端（新建 2 文件 + 改动 5 文件）：**
- `frontend/src/extensions/project/utils.ts` — 加纯函数 `deriveBlockState` / `hasAnyContent` / `groupByRole` + `AssignmentStrategy` 类型（Task 3）
- `frontend/src/extensions/project/types.ts` — `ReportProject` / `CreateProjectRequest` / `UpdateProjectRequest` 加 `assignmentStrategy` 字段（Task 3）
- `frontend/src/extensions/project/components/AssignmentStrategySelect.tsx` — **新建**，共享策略选择器（Task 4）
- `frontend/src/extensions/project/components/RoleBoard.tsx` — **新建**，`by_role` 角色分组看板（Task 5）
- `frontend/src/extensions/project/tabs/OverviewTab.tsx` — 章节进度区块改状态驱动渲染器（Task 6）
- `frontend/src/extensions/project/ProjectCreateWizard.tsx` — 成员步骤加策略选择 + create payload 透传（Task 7）
- `frontend/src/extensions/project/components/SettingsDialog.tsx` — 加策略选择 + update 透传（Task 7）

**前端测试（1 文件改动）：**
- `frontend/tests/unit/extensions/project/utils.test.ts` — 加 3 个纯函数的真值表测试（Task 3）

**依赖方向（无环）：** Task 1 → Task 2（后端）；Task 3（types+utils）→ Task 4（select）→ Task 5（roleboard，依赖 utils.groupByRole）→ Task 6（OverviewTab，依赖 4+5+utils）→ Task 7（wizard/settings，依赖 4）。后端 Task 1–2 与前端 Task 3–7 可并行，但建议先完成后端（Task 7 的 create/update 需要后端字段存在才能端到端）。

---

## Task 1: 后端 schema — `assignment_strategy` 字段（TDD）

**Files:**
- Modify: `backend/app/extensions/project/schemas.py:102-177`
- Test: `backend/tests/test_project_schemas.py`（已有 `TestProjectCreate` / `TestProjectUpdate` / `TestProjectOut` 类）

- [ ] **Step 1: 写失败的 schema 测试**

在 `backend/tests/test_project_schemas.py` 的 `TestProjectCreate` 类末尾（第 119 行 `test_with_template` 之后）追加：

```python
    def test_default_assignment_strategy(self):
        # EAI-CUSTOM: 分工策略默认按章节(ADR 2026-08-10)
        p = ProjectCreate(name="T", report_type="other")
        assert p.assignment_strategy == "by_chapter"

    def test_by_role_strategy_accepted(self):
        p = ProjectCreate(name="T", report_type="other", assignment_strategy="by_role")
        assert p.assignment_strategy == "by_role"

    def test_invalid_strategy_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="T", report_type="other", assignment_strategy="by_domain")
```

在 `TestProjectUpdate` 类（第 121 行起）末尾追加：

```python
    def test_assignment_strategy(self):
        u = ProjectUpdate(assignment_strategy="by_role")
        assert u.assignment_strategy == "by_role"

    def test_assignment_strategy_none_by_default(self):
        u = ProjectUpdate()
        assert u.assignment_strategy is None
```

在 `TestProjectOut` 类（第 133 行起）的 `test_defaults` 之后追加：

```python
    def test_default_assignment_strategy(self):
        uid = uuid4()
        p = ProjectOut(id=uid, name="Test", report_type="other")
        assert p.assignment_strategy == "by_chapter"  # EAI-CUSTOM: ADR 2026-08-10
```

- [ ] **Step 2: 运行测试，确认失败**

Run（在 `backend/` 目录）:
```bash
PYTHONPATH=. uv run pytest tests/test_project_schemas.py -v
```
Expected: FAIL — `ProjectCreate` 无 `assignment_strategy` 属性（`AttributeError`）。

- [ ] **Step 3: 在 schemas.py 顶部加 `Literal` 导入**

打开 `backend/app/extensions/project/schemas.py`，在文件顶部 import 区找到现有 typing 相关导入。若已有 `from typing import ...`，把 `Literal` 加进去；否则在 pydantic 导入之前加一行：

```python
from typing import Literal
```

- [ ] **Step 4: 给三个 schema 加字段**

`ProjectCreate`（第 102 行），在 `description` 字段后加一行：

```python
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    report_type: str = Field(..., min_length=1, max_length=100)
    template_id: UUID | None = None
    workflow_id: UUID | None = None
    auto_start_workflow: bool = False
    members: list["MemberWithDuties"] | None = None
    description: str | None = None  # EAI-CUSTOM: 项目说明/要求(选填),注入 agent
    assignment_strategy: Literal["by_chapter", "by_role"] = "by_chapter"  # EAI-CUSTOM: 分工策略(ADR 2026-08-10)
```

`ProjectUpdate`（第 150 行），在 `description` 字段后加一行：

```python
class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = None
    workflow_id: UUID | None = None
    current_phase_node: str | None = None
    description: str | None = None  # EAI-CUSTOM: 项目说明/要求(选填);注:传 null 不清空(service if v is not None)
    assignment_strategy: Literal["by_chapter", "by_role"] | None = None  # EAI-CUSTOM: 分工策略(ADR 2026-08-10)
```

`ProjectOut`（第 158 行），在 `description` 字段后、`archived_at` 之前加一行：

```python
    description: str | None = None  # EAI-CUSTOM: 项目说明/要求,注入 agent project-context
    assignment_strategy: str = "by_chapter"  # EAI-CUSTOM: 分工策略回显(ADR 2026-08-10)
    archived_at: datetime | None = None  # EAI-CUSTOM: orthogonal archive bucket (ADR P5)
```

- [ ] **Step 5: 运行测试，确认通过**

Run:
```bash
PYTHONPATH=. uv run pytest tests/test_project_schemas.py -v
```
Expected: PASS（新加的 5 个测试全过，既有测试不受影响）。

- [ ] **Step 6: 提交**

```bash
git add backend/app/extensions/project/schemas.py backend/tests/test_project_schemas.py
git commit -m "feat(project): ProjectCreate/Update/Out 加 assignment_strategy 字段(by_chapter/by_role)"
```

---

## Task 2: 后端 model + 迁移 + router/service 透传

> 注：schema 测试（Task 1）是纯 Pydantic，不碰 DB；本任务是 ORM 列 + 迁移 + 写入透传，验证靠重启容器 + psql 查列 + 重跑 schema 测试。

**Files:**
- Modify: `backend/app/extensions/models/__init__.py:658`
- Modify: `backend/app/extensions/database.py:1028`
- Modify: `backend/app/extensions/project/routers.py:141-150`
- Modify: `backend/app/extensions/project/service.py:610-630`

- [ ] **Step 1: ORM model 加列**

`backend/app/extensions/models/__init__.py`，在 `ReportProject` 的 `description` 列（第 658 行）之后加一行：

```python
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # EAI-CUSTOM: 项目自由文本说明/要求,写入 project-context.json 注入 agent
    assignment_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="by_chapter")  # EAI-CUSTOM: 分工策略 by_chapter|by_role (ADR 2026-08-10)
```

- [ ] **Step 2: 加幂等迁移**

`backend/app/extensions/database.py`，在第 1025–1028 行的 `description` 迁移块之后加一段：

```python
        # EAI-CUSTOM: 项目自由文本说明/要求字段(create_all 不 ALTER 已有表,须在此幂等加列)
        await conn.execute(text(
            "ALTER TABLE report_projects ADD COLUMN IF NOT EXISTS description TEXT"
        ))
        # EAI-CUSTOM: 分工策略(ADR 2026-08-10) — 章节进度区块在「人工修改确认」态按此渲染分工叠加层
        await conn.execute(text(
            "ALTER TABLE report_projects ADD COLUMN IF NOT EXISTS assignment_strategy VARCHAR(20) NOT NULL DEFAULT 'by_chapter'"
        ))
```

- [ ] **Step 3: router create 端点透传**

`backend/app/extensions/project/routers.py`，在第 141–150 行的 `service.create_project(...)` 调用里，在 `description=body.description,` 之后加一行：

```python
    project = await service.create_project(
        db,
        name=body.name,
        report_type=body.report_type,
        description=body.description,  # EAI-CUSTOM: 项目说明/要求(选填),注入 agent
        assignment_strategy=body.assignment_strategy,  # EAI-CUSTOM: 分工策略(ADR 2026-08-10)
        template_id=body.template_id,
        workflow_id=body.workflow_id,
        created_by=_user.id,
        members_data=members_data,
    )
```

- [ ] **Step 4: service create_project 加形参 + ORM 赋值**

`backend/app/extensions/project/service.py`，在 `create_project` 签名（第 610 行）加形参，并在 `ReportProject(...)` 构造里赋值：

```python
async def create_project(
    db: AsyncSession,
    *,
    name: str,
    report_type: str,
    created_by=None,
    template_id=None,
    workflow_id=None,
    members_data: list[dict] | None = None,
    description: str | None = None,
    assignment_strategy: str = "by_chapter",  # EAI-CUSTOM: 分工策略(ADR 2026-08-10)
) -> ProjectOut:
    has_template = bool(template_id)
    project = ReportProject(
        name=name,
        report_type=report_type,
        created_by=created_by,
        description=description,
        assignment_strategy=assignment_strategy,  # EAI-CUSTOM: 分工策略(ADR 2026-08-10)
        template_id=template_id,
        workflow_id=workflow_id,
        status="draft",  # EAI-CUSTOM: canonical status (ADR 2026-08-02)
    )
```

> **update 路径无需改动**：`routers.py` 的 update 端点用 `service.update_project(db, project_id, **body.model_dump(exclude_unset=True))`，`ProjectUpdate` 已有 `assignment_strategy`（Task 1），`exclude_unset=True` 保证未传不覆盖；service 的 `update_project` setattr 循环会自动写入。确认 `update_project` 的 setattr 循环不过滤 `assignment_strategy`（它只跳过 `None`，而 `exclude_unset` 已排除未设字段）。

- [ ] **Step 5: 重启 gateway 让迁移生效**

```bash
docker compose -p eai-docker restart gateway
```

- [ ] **Step 6: 验证迁移加列成功**

```bash
docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "\d report_projects" | grep assignment_strategy
```
Expected: 输出含 `assignment_strategy | character varying(20) | not null default 'by_chapter'`。
> 若容器名不同，先 `docker compose -p eai-docker ps` 找 postgres 容器名。

- [ ] **Step 7: 重跑 schema 测试确认无回归**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_project_schemas.py tests/test_project_service.py tests/test_project_routers.py -v
```
Expected: PASS。

- [ ] **Step 8: lint**

```bash
cd backend && make lint
```
Expected: 无错误（ruff）。

- [ ] **Step 9: 提交**

```bash
git add backend/app/extensions/models/__init__.py backend/app/extensions/database.py backend/app/extensions/project/routers.py backend/app/extensions/project/service.py
git commit -m "feat(project): ReportProject 加 assignment_strategy 列+迁移,router/service 透传"
```

---

## Task 3: 前端 types + 纯函数（`deriveBlockState` / `hasAnyContent` / `groupByRole`）— TDD

**Files:**
- Modify: `frontend/src/extensions/project/types.ts:49-104`
- Modify: `frontend/src/extensions/project/utils.ts:1-40`
- Test: `frontend/tests/unit/extensions/project/utils.test.ts`

- [ ] **Step 1: 写失败的纯函数测试**

在 `frontend/tests/unit/extensions/project/utils.test.ts` 顶部 import 区，把现有：
```ts
import {
  type ChapterStatus,
  activityLabel,
  flattenChapters,
  inferStatus,
} from "@/extensions/project/utils";
```
改为：
```ts
import {
  type ChapterBlockState,
  type ChapterStatus,
  activityLabel,
  deriveBlockState,
  flattenChapters,
  groupByRole,
  hasAnyContent,
  inferStatus,
} from "@/extensions/project/utils";
```

然后在文件末尾（第 120 行 `activityLabel` describe 块之后）追加三个 describe 块：

```ts
// EAI-CUSTOM: 状态机 + 分工纯函数(ADR 2026-08-10)

const baseChapter = (overrides: Partial<ProjectChapter> = {}): ProjectChapter => ({
  id: "1", projectId: "p", parentId: null, title: "Test", level: 1,
  sortOrder: 0, status: "pending", content: null,
  assignedTo: null, assignedName: null,
  wordCountTarget: 0, wordCountCurrent: 0,
  purpose: null, generationHint: null, children: [],
  createdAt: null, updatedAt: null,
  ...overrides,
});

describe("hasAnyContent", () => {
  it("returns false when no chapters have content", () => {
    expect(hasAnyContent([baseChapter(), baseChapter({ children: [baseChapter()] })])).toBe(false);
  });

  it("returns true when any chapter has content", () => {
    expect(hasAnyContent([baseChapter(), baseChapter({ content: "hello" })])).toBe(true);
  });

  it("returns true for nested content", () => {
    expect(hasAnyContent([baseChapter({ children: [baseChapter({ content: "x" })] })])).toBe(true);
  });

  it("ignores whitespace-only content", () => {
    expect(hasAnyContent([baseChapter({ content: "   \n\t " })])).toBe(false);
  });

  it("returns false for empty input", () => {
    expect(hasAnyContent([])).toBe(false);
  });
});

describe("deriveBlockState", () => {
  it("not_generated when temporal workflow id is null/undefined/empty", () => {
    expect(deriveBlockState(null, false)).toBe<ChapterBlockState>("not_generated");
    expect(deriveBlockState(undefined, false)).toBe<ChapterBlockState>("not_generated");
    expect(deriveBlockState("", false)).toBe<ChapterBlockState>("not_generated");
  });

  it("generating when workflow started but no content", () => {
    expect(deriveBlockState("wf-123", false)).toBe<ChapterBlockState>("generating");
  });

  it("human_edit when at least one chapter has content", () => {
    expect(deriveBlockState("wf-123", true)).toBe<ChapterBlockState>("human_edit");
  });

  it("content takes priority over workflow id presence", () => {
    expect(deriveBlockState(null, true)).toBe<ChapterBlockState>("not_generated");
  });
});

describe("groupByRole", () => {
  it("groups items by role", () => {
    const items = [
      { role: "writer", id: "1" },
      { role: "writer", id: "2" },
      { role: "reviewer", id: "3" },
    ];
    expect(groupByRole(items)).toEqual({
      writer: [{ role: "writer", id: "1" }, { role: "writer", id: "2" }],
      reviewer: [{ role: "reviewer", id: "3" }],
    });
  });

  it("returns empty object for empty input", () => {
    expect(groupByRole([])).toEqual({});
  });
});
```

- [ ] **Step 2: 运行测试，确认失败**

Run（在 `frontend/` 目录）:
```bash
pnpm test tests/unit/extensions/project/utils.test.ts
```
Expected: FAIL — `deriveBlockState` / `hasAnyContent` / `groupByRole` 未导出。

- [ ] **Step 3: types.ts 加字段与类型**

`frontend/src/extensions/project/types.ts`：

(a) 在 `ReportProject`（第 49 行）的 `description` 字段后加：
```ts
  description?: string | null; // EAI-CUSTOM: 项目说明/要求,写入 project-context.json 注入 agent
  assignmentStrategy?: AssignmentStrategy; // EAI-CUSTOM: 分工策略(ADR 2026-08-10)
```

(b) 在 `CreateProjectRequest`（第 90 行）的 `description` 字段后加：
```ts
  description?: string | null; // EAI-CUSTOM: 项目说明/要求(选填)
  assignmentStrategy?: AssignmentStrategy; // EAI-CUSTOM: 分工策略(ADR 2026-08-10)
```

(c) 在 `UpdateProjectRequest`（第 100 行）的 `description` 字段后加：
```ts
  description?: string | null; // EAI-CUSTOM: 项目说明/要求(选填)
  assignmentStrategy?: AssignmentStrategy; // EAI-CUSTOM: 分工策略(ADR 2026-08-10)
```

(d) 在 `MemberRole` 类型定义（第 12 行）之后加一个导出类型：
```ts
export type AssignmentStrategy = "by_chapter" | "by_role"; // EAI-CUSTOM: ADR 2026-08-10
```

- [ ] **Step 4: utils.ts 加纯函数**

在 `frontend/src/extensions/project/utils.ts` 末尾追加：

```ts
// EAI-CUSTOM: 章节进度区块状态机 + 分工纯函数(ADR 2026-08-10)

/** 章节进度区块的 3 态。 */
export type ChapterBlockState = "not_generated" | "generating" | "human_edit";

/** 任意章节(递归)是否有非空 content。 */
export function hasAnyContent(chapters: ProjectChapter[]): boolean {
  return flattenChapters(chapters).some((c) => (c.content ?? "").trim().length > 0);
}

/**
 * EAI-CUSTOM: 章节进度区块状态机(ADR 2026-08-10)。
 * not_generated = 工作流未启动; generating = 已启动但无任何章节有 content;
 * human_edit = 至少一章有 content(初稿已产出)。
 * 用 chapter.content 是否存在做 ②↔③ 分界,不依赖工作流节点类型。
 */
export function deriveBlockState(
  temporalWorkflowId: string | null | undefined,
  hasAnyChapterContent: boolean,
): ChapterBlockState {
  if (!temporalWorkflowId) return "not_generated";
  if (!hasAnyChapterContent) return "generating";
  return "human_edit";
}

/** 按角色分组(泛型,适用于任何带 role 字段的对象)。 */
export function groupByRole<T extends { role: string }>(members: T[]): Record<string, T[]> {
  const groups: Record<string, T[]> = {};
  for (const m of members) {
    (groups[m.role] ??= []).push(m);
  }
  return groups;
}
```

> 注：`flattenChapters` 与 `ProjectChapter` 已在 utils.ts 顶部导入，无需新加 import。

- [ ] **Step 5: 运行测试，确认通过**

Run:
```bash
pnpm test tests/unit/extensions/project/utils.test.ts
```
Expected: PASS（新加 11 个测试全过）。

- [ ] **Step 6: typecheck**

```bash
pnpm typecheck
```
Expected: 无新增错误（既有 2 个无关错误可忽略，确认本任务未引入新错误）。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/extensions/project/types.ts frontend/src/extensions/project/utils.ts frontend/tests/unit/extensions/project/utils.test.ts
git commit -m "feat(project): 加 deriveBlockState/hasAnyContent/groupByRole 纯函数 + assignmentStrategy 类型"
```

---

## Task 4: `AssignmentStrategySelect` 共享组件

**Files:**
- Create: `frontend/src/extensions/project/components/AssignmentStrategySelect.tsx`

- [ ] **Step 1: 新建组件文件**

创建 `frontend/src/extensions/project/components/AssignmentStrategySelect.tsx`：

```tsx
"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AssignmentStrategy } from "@/extensions/project/types";

// EAI-CUSTOM: 分工策略选择器(ADR 2026-08-10)。创建向导与项目设置共用。
const STRATEGY_LABELS: Record<AssignmentStrategy, string> = {
  by_chapter: "按章节分工",
  by_role: "按职责分工（按角色）",
};

const STRATEGY_HINT: Record<AssignmentStrategy, string> = {
  by_chapter: "每人认领/被分配若干章节，改完提交审核。",
  by_role: "成员按角色分组（撰写/审核/审批），跨全文各司其职。",
};

interface AssignmentStrategySelectProps {
  value: AssignmentStrategy;
  onChange: (v: AssignmentStrategy) => void;
  disabled?: boolean;
}

export function AssignmentStrategySelect({ value, onChange, disabled }: AssignmentStrategySelectProps) {
  return (
    <div className="space-y-1.5">
      <label className="text-[12px] text-muted-foreground font-medium">分工策略</label>
      <Select value={value} onValueChange={(v) => onChange(v as AssignmentStrategy)} disabled={disabled}>
        <SelectTrigger className="h-8 w-full text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(STRATEGY_LABELS) as AssignmentStrategy[]).map((k) => (
            <SelectItem key={k} value={k}>
              {STRATEGY_LABELS[k]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-[11px] text-muted-foreground">
        在「人工修改确认」阶段按此策略分配修改确认工作。{STRATEGY_HINT[value]}
      </p>
    </div>
  );
}
```

> 用原生 `<label>` 而非 `@/components/ui/label`，与 `SettingsDialog.tsx` 现有风格一致（避免引入未确认存在的依赖）。

- [ ] **Step 2: typecheck**

```bash
cd frontend && pnpm typecheck
```
Expected: 无新增错误（组件未被引用时不会报 unused，因为是具名导出）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/extensions/project/components/AssignmentStrategySelect.tsx
git commit -m "feat(project): 新建 AssignmentStrategySelect 共享策略选择器"
```

---

## Task 5: `RoleBoard` 组件（`by_role` 角色分组看板）

**Files:**
- Create: `frontend/src/extensions/project/components/RoleBoard.tsx`

- [ ] **Step 1: 新建组件文件**

创建 `frontend/src/extensions/project/components/RoleBoard.tsx`：

```tsx
"use client";

import { BookOpen } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  MEMBER_ROLE_LABELS,
  type MemberRole,
  type ProjectChapter,
  type ProjectMember,
} from "@/extensions/project/types";
import { groupByRole } from "@/extensions/project/utils";

// EAI-CUSTOM: 按职责(角色)分工看板(ADR 2026-08-10)。
// v1 = 角色分组的花名册 + 职责说明,不做自动章节重指派(spec §10 β)。

const ROLE_ORDER: MemberRole[] = ["writer", "reviewer", "approver", "phase_lead", "owner"];
const ROLE_DUTY: Record<MemberRole, string> = {
  writer: "改写初稿内容",
  reviewer: "审校章节质量",
  approver: "审批定稿",
  phase_lead: "牵头推进",
  owner: "项目负责",
};

interface RoleBoardProps {
  members: ProjectMember[];
  chapters: ProjectChapter[];
  onEdit: (chapterId: string) => void;
}

export function RoleBoard({ members, chapters: _chapters, onEdit: _onEdit }: RoleBoardProps) {
  const groups = groupByRole(members);
  const presentRoles = ROLE_ORDER.filter((r) => (groups[r]?.length ?? 0) > 0);

  if (presentRoles.length === 0) {
    return (
      <div className="px-5 pb-6 pt-4 flex flex-col items-center text-center">
        <BookOpen className="h-8 w-8 text-muted-foreground/30 mb-2" />
        <p className="text-sm text-muted-foreground">尚无项目成员</p>
        <p className="text-xs text-muted-foreground/60 mt-1">按职责分工需先添加成员并分配角色</p>
      </div>
    );
  }

  return (
    <div className="px-5 pb-4 pt-2 grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[480px] overflow-y-auto pr-1 cyber-scroll">
      {presentRoles.map((role) => (
        <div key={role} className="rounded-lg border border-border/60 p-3">
          <div className="flex items-center justify-between mb-2">
            <Badge variant="secondary" className="text-[10px] font-normal">
              {MEMBER_ROLE_LABELS[role] ?? role}
            </Badge>
            <span className="text-[11px] text-muted-foreground">{ROLE_DUTY[role]}</span>
          </div>
          <div className="space-y-1.5">
            {(groups[role] ?? []).map((m) => (
              <div key={m.id} className="flex items-center gap-2">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary">
                  {(m.username ?? "?").charAt(0).toUpperCase()}
                </div>
                <span className="text-sm text-foreground truncate">{m.username}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

> `chapters` 与 `onEdit` 当前以 `_` 前缀保留（未来按角色点击章节跳编辑用），避免 unused 警告；v1 不做章节级角色指派 UI。

- [ ] **Step 2: typecheck**

```bash
cd frontend && pnpm typecheck
```
Expected: 无新增错误。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/extensions/project/components/RoleBoard.tsx
git commit -m "feat(project): 新建 RoleBoard 按职责(角色)分组看板"
```

---

## Task 6: OverviewTab 章节进度区块 → 状态驱动渲染器

**Files:**
- Modify: `frontend/src/extensions/project/tabs/OverviewTab.tsx`（import 区 1–37；章节进度区块 376–432）

- [ ] **Step 1: 加 import**

在 `frontend/src/extensions/project/tabs/OverviewTab.tsx` 的 lucide-react import（第 3–12 行）加两个图标 `Loader2`（已有则跳过）、`Wand2`：

```ts
import {
  BookOpen,
  FileText,
  LayoutGrid,
  List,
  Loader2,
  Trash2,
  Users,
  UserPlus,
  Wand2,
} from "lucide-react";
```

在 `@/extensions/project/utils` import（第 31–37 行）追加新函数：

```ts
import {
  activityLabel,
  aggregateWordCount,
  type ChapterStatus,
  deriveBlockState,
  flattenChapters,
  hasAnyContent,
  inferStatus,
} from "@/extensions/project/utils";
```

在 import 区末尾（第 37 行后）加两行新 import：

```ts
import { AssignmentStrategySelect } from "@/extensions/project/components/AssignmentStrategySelect";
import { RoleBoard } from "@/extensions/project/components/RoleBoard";
import { workflowApi } from "@/extensions/workflow/api";
```

- [ ] **Step 2: 在组件体内加状态派生 + CTA handler**

在 `OverviewTab` 组件函数体内（`handleEditChapter` 等现有 handler 附近，且在 `return (` 之前），加：

```tsx
  // EAI-CUSTOM: 章节进度区块状态机(ADR 2026-08-10)
  const blockState = useMemo(
    () => deriveBlockState(project.temporalWorkflowId, hasAnyContent(project.chapters ?? [])),
    [project.temporalWorkflowId, project.chapters],
  );

  const [starting, setStarting] = useState(false);
  const canStartGenerate =
    (identity?.isAdmin ||
      identity?.projectRole === "owner" ||
      identity?.hasAnyPermission(["project:advance", "project:edit"]) ||
      false) &&
    !!project.workflowId;

  const handleStartGenerate = useCallback(async () => {
    if (!project.workflowId) return;
    setStarting(true);
    try {
      await workflowApi.startWorkflow(projectId, project.workflowId);
      toast.success("AI 开始生成初稿");
      onRefresh();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "启动失败，请稍后重试");
    } finally {
      setStarting(false);
    }
  }, [project.workflowId, projectId, onRefresh]);
```

> `useMemo` / `useState` / `useCallback` 已在第 13 行 import，`toast` 已在第 14 行 import，无需新加。

- [ ] **Step 3: 替换章节进度区块为状态驱动**

把第 376–432 行整段（从 `{/* Chapter Progress — 3 cols */}` 注释所在的外层 `<div className="lg:col-span-3">` 到其闭合 `</div>`）替换为：

```tsx
          {/* Chapter Progress — 3 cols — EAI-CUSTOM: 状态驱动(ADR 2026-08-10) */}
          <div className="lg:col-span-3">
            <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md">
              <div className="flex items-center justify-between px-5 pt-4 pb-0">
                <h3 className="text-sm font-medium text-foreground">章节进度</h3>
                {blockState === "human_edit" &&
                  project.assignmentStrategy !== "by_role" &&
                  kanbanCards.length > 0 && (
                    <div className="flex items-center gap-1 rounded-md border border-border p-0.5">
                      <Button
                        variant={kanbanView ? "ghost" : "secondary"}
                        size="icon-sm"
                        onClick={() => setKanbanView(false)}
                        title="列表视图"
                      >
                        <List className="size-3.5" />
                      </Button>
                      <Button
                        variant={kanbanView ? "secondary" : "ghost"}
                        size="icon-sm"
                        onClick={() => setKanbanView(true)}
                        title="看板视图"
                      >
                        <LayoutGrid className="size-3.5" />
                      </Button>
                    </div>
                  )}
              </div>

              {blockState === "not_generated" && (
                <div className="px-5 pb-6 pt-4">
                  <div className="flex flex-col items-center text-center">
                    <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                      <Wand2 className="h-6 w-6 text-primary" />
                    </div>
                    <p className="text-sm font-medium text-foreground mb-1">尚未生成初稿</p>
                    <p className="text-xs text-muted-foreground mb-4">
                      AI 将按所选大纲生成初稿（可能调整结构），随后进入「人工修改确认」。
                    </p>
                    <Button
                      onClick={handleStartGenerate}
                      disabled={!canStartGenerate || starting}
                      className="mb-5"
                    >
                      {starting ? (
                        <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                      ) : (
                        <Wand2 className="h-4 w-4 mr-1.5" />
                      )}
                      开始 AI 生成初稿
                    </Button>
                    {!project.workflowId && (
                      <p className="text-[11px] text-muted-foreground mb-4">
                        请先在「项目设置」关联工作流后再开始生成。
                      </p>
                    )}
                    <ol className="w-full max-w-sm space-y-2 text-left">
                      <li className="flex items-start gap-2 text-xs text-muted-foreground">
                        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary">1</span>
                        AI 按所选大纲生成初稿（可能调整结构）
                      </li>
                      <li className="flex items-start gap-2 text-xs text-muted-foreground">
                        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary">2</span>
                        进入「人工修改确认」阶段
                      </li>
                      <li className="flex items-start gap-2 text-xs text-muted-foreground">
                        <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-medium text-primary">3</span>
                        按「{project.assignmentStrategy === "by_role" ? "按职责" : "按章节"}」分工修改确认
                      </li>
                    </ol>
                  </div>
                </div>
              )}

              {blockState === "generating" && (
                <div className="px-5 pb-6 pt-4 flex flex-col items-center justify-center text-center">
                  <Loader2 className="h-7 w-7 text-primary animate-spin mb-3" />
                  <p className="text-sm font-medium text-foreground">AI 正在生成初稿…</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    生成完成后将进入「人工修改确认」，届时可按分工策略修改确认。
                  </p>
                </div>
              )}

              {blockState === "human_edit" &&
                (project.assignmentStrategy === "by_role" ? (
                  <RoleBoard
                    members={project.members ?? []}
                    chapters={project.chapters ?? []}
                    onEdit={handleEditChapter}
                  />
                ) : kanbanView ? (
                  <div className="px-5 pb-4 pt-2 max-h-[480px] overflow-y-auto overflow-x-auto pr-1 cyber-scroll">
                    <KanbanBoard cards={kanbanCards} onCardMove={handleCardMove} onCardEdit={handleEditChapter} />
                  </div>
                ) : (
                  <div className="px-5 pb-4 pt-2">
                    {project.chapters?.length > 0 ? (
                      <div className="max-h-[480px] overflow-y-auto pr-1 cyber-scroll divide-y divide-border/40">
                        {project.chapters.map((ch) => (
                          <ChapterNode
                            key={ch.id}
                            chapter={ch}
                            depth={0}
                            onMarkComplete={handleMarkComplete}
                            onEdit={handleEditChapter}
                            completingId={completingId}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-12">
                        <BookOpen className="h-8 w-8 text-muted-foreground/30 mb-2" />
                        <p className="text-sm text-muted-foreground">暂无章节</p>
                        <p className="text-xs text-muted-foreground/60 mt-1">从模板创建项目或手动添加章节</p>
                      </div>
                    )}
                  </div>
                ))}
            </div>
          </div>
```

> 关键：`by_chapter` 分支 = 原有 `ChapterNode`/`KanbanBoard` 原样搬进状态③；`by_role` 分支 = 新 `RoleBoard`。`not_generated` / `generating` 是新 UI。空章节提示保留在 `by_chapter` 列表态。

- [ ] **Step 4: typecheck**

```bash
cd frontend && pnpm typecheck
```
Expected: 无新增错误。

- [ ] **Step 5: 重启前端验证编译**

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 6: 浏览器手测（可选但推荐）**

打开 `http://localhost:2026`，登录（admin@eai-flow.com / Admin@2026），进入一个未启动工作流的项目详情页 → Overview → 确认「章节进度」区块显示「开始 AI 生成初稿」CTA + 3 步时间线，而非空大纲树。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/extensions/project/tabs/OverviewTab.tsx
git commit -m "feat(project): OverviewTab 章节进度区块改状态驱动(not_generated/generating/human_edit)"
```

---

## Task 7: 创建向导 + 项目设置 — 分工策略选择

**Files:**
- Modify: `frontend/src/extensions/project/ProjectCreateWizard.tsx`（state 906 行附近；members 步骤 UI 662 行附近；create payload 988–996 行）
- Modify: `frontend/src/extensions/project/components/SettingsDialog.tsx`（state 57 行附近；UI 275 行附近）

### Part A — 创建向导

> Step 4「Team」是独立子组件 `StepTeam`（第 526 行），需把策略 state 作 prop 透传。

- [ ] **Step 1: 顶部加 import + 主组件加 state**

`frontend/src/extensions/project/ProjectCreateWizard.tsx`，在文件顶部 import 区（其它 `@/extensions/project/components/...` 附近）加：

```ts
import { AssignmentStrategySelect } from "@/extensions/project/components/AssignmentStrategySelect";
```

在主组件 `autoStartWorkflow` state（第 906 行）之后加：

```tsx
  // Auto-start workflow option
  const [autoStartWorkflow, setAutoStartWorkflow] = useState(true);

  // EAI-CUSTOM: 分工策略(ADR 2026-08-10)
  const [assignmentStrategy, setAssignmentStrategy] = useState<"by_chapter" | "by_role">("by_chapter");
```

并在 StepTeam 调用处（第 1073–1080 行）把 state 透传为 props：

```tsx
              <StepTeam
                leader={leader}
                members={teamMembers}
                onSetLeader={setLeader}
                onAddMember={addTeamMember}
                onRemoveMember={removeTeamMember}
                onSkip={skipToNext}
                assignmentStrategy={assignmentStrategy}
                onStrategyChange={setAssignmentStrategy}
              />
```

- [ ] **Step 2: StepTeam 子组件加 props + 渲染选择器**

(a) 把 `StepTeam` 的签名（第 526–540 行）加两个 props：

```tsx
function StepTeam({
  leader,
  members,
  onSetLeader,
  onAddMember,
  onRemoveMember,
  onSkip,
  assignmentStrategy,
  onStrategyChange,
}: {
  leader: TeamMember | null;
  members: TeamMember[];
  onSetLeader: (m: TeamMember | null) => void;
  onAddMember: (m: TeamMember) => void;
  onRemoveMember: (id: string) => void;
  onSkip: () => void;
  assignmentStrategy: "by_chapter" | "by_role";
  onStrategyChange: (v: "by_chapter" | "by_role") => void;
}) {
```

(b) 在 Members 区块（第 659–696 行的 `<div className="rounded-lg border border-gray-200 bg-white p-4">…</div>`）闭合标签（第 696 行 `</div>`）之后、「跳过此步骤」按钮区块（第 698 行 `<div className="flex justify-end">`）之前，插入选择器：

```tsx
      </div>

      {/* EAI-CUSTOM: 分工策略(ADR 2026-08-10) */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <AssignmentStrategySelect value={assignmentStrategy} onChange={onStrategyChange} />
      </div>

      <div className="flex justify-end">
```

- [ ] **Step 3: create payload 透传字段**

把第 988–996 行的 `projectApi.create({...})` 调用，在 `autoStartWorkflow` 之后加 `assignmentStrategy`：

```tsx
      const project = await projectApi.create({
        name: name.trim(),
        reportType: reportType,
        description: description.trim() || undefined,
        templateId: resolveTemplateId(),
        workflowId,
        autoStartWorkflow: autoStartWorkflow && !!workflowId,
        assignmentStrategy, // EAI-CUSTOM: 分工策略(ADR 2026-08-10)
        members: memberList.length > 0 ? memberList : undefined,
      });
```

> `api.ts` 的 create 用 `toSnakeCase(req)`，`assignmentStrategy` 自动转 `assignment_strategy`（Task 1 已让后端接受）。

### Part B — 项目设置

- [ ] **Step 4: SettingsDialog 加 state + handler**

`frontend/src/extensions/project/components/SettingsDialog.tsx`，在顶部 import 区加：

```ts
import { AssignmentStrategySelect } from "@/extensions/project/components/AssignmentStrategySelect";
```

在 `projectStatus` state（第 57 行）之后加：

```tsx
  const [assignmentStrategy, setAssignmentStrategy] = useState<"by_chapter" | "by_role">(
    project.assignmentStrategy ?? "by_chapter",
  );
  const [savingStrategy, setSavingStrategy] = useState(false);
```

在 `handleOpenChange`（第 66 行）的 `if (nextOpen) {` 块内，`setProjectStatus(project.status);` 之后加：

```tsx
      setAssignmentStrategy(project.assignmentStrategy ?? "by_chapter");
```

在 `handleStatusChange` 之后加一个新 handler：

```tsx
  // EAI-CUSTOM: 分工策略(ADR 2026-08-10)
  const handleStrategyChange = async (v: "by_chapter" | "by_role") => {
    setAssignmentStrategy(v);
    setSavingStrategy(true);
    try {
      await projectApi.update(projectId, { assignmentStrategy: v });
      onRefresh();
      toast.success("分工策略已更新");
    } catch {
      toast.error("更新失败");
      setAssignmentStrategy(project.assignmentStrategy ?? "by_chapter");
    } finally {
      setSavingStrategy(false);
    }
  };
```

- [ ] **Step 5: SettingsDialog 加 UI**

在「项目状态」区块（约第 256–275 行）之后、「归档」区块之前，插入策略选择区块：

```tsx
          {/* Assignment Strategy — EAI-CUSTOM: 分工策略(ADR 2026-08-10) */}
          <div className="space-y-1.5">
            {canEdit ? (
              <AssignmentStrategySelect
                value={assignmentStrategy}
                onChange={(v) => handleStrategyChange(v)}
                disabled={savingStrategy}
              />
            ) : (
              <>
                <label className="text-[12px] text-muted-foreground font-medium">分工策略</label>
                <p className="text-sm text-foreground">
                  {project.assignmentStrategy === "by_role" ? "按职责分工（按角色）" : "按章节分工"}
                </p>
              </>
            )}
          </div>
```

- [ ] **Step 6: typecheck + lint**

```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 无新增错误。

- [ ] **Step 7: 重启前端验证**

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 8: 浏览器端到端手测**

(a) 新建项目向导 → 第 4 步成员页确认出现「分工策略」选择器，选「按职责分工」→ 完成创建 → 进项目设置确认策略已保存为 by_role。
(b) 项目设置里切换策略 → 刷新确认持久化。
(c) 创建一个 by_chapter 项目、不自动启动工作流 → 进详情页确认 CTA 显示 → 点「开始 AI 生成初稿」→ 确认状态翻到 generating（或工作流启动）。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/extensions/project/ProjectCreateWizard.tsx frontend/src/extensions/project/components/SettingsDialog.tsx
git commit -m "feat(project): 创建向导+项目设置加分工策略选择,create/update 透传 assignmentStrategy"
```

---

## 完成判定

全部 7 个 Task 完成后：

1. **后端**：`assignment_strategy` 列存在（psql 可见）、默认 `by_chapter`；schema 测试全过；create/update 端到端可设可改可回显。
2. **前端**：未启动工作流的项目详情页显示 CTA（非空大纲树）；启动后显示 generating；有 content 后按策略显示 by_chapter（原章节视图）/ by_role（角色看板）。
3. **纯函数单测**全过（`deriveBlockState` / `hasAnyContent` / `groupByRole`）。
4. **零新后端端点**、**零 harness 改动**、**零新依赖**。
5. 所有改动带 EAI-CUSTOM 注释，提交在 `main-dev-fork` 分支。

## 不做（scope guard，照 spec §7）

- 不改 harness 核心（`deerflow.*`）。
- 不做 AI 改写大纲机制（deferred 独立 spec）。
- 不做 `by_domain` / `by_phase`（enum 扩展位，v1 不实现）。
- 不改状态值词表（复用 `pending/draft/reviewing/approved`）。
- 不重写工作流引擎（CTA 复用既有 `start_workflow`）。
