# 知识库对话框部门级访问权限选择 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建/编辑知识库对话框(共 3 个:列表页创建、列表页编辑、详情页编辑)在访问权限选「部门可见」时:admin 可内联勾选 1+ 个部门并以标签展示;普通用户自动只读展示自己所在部门标签;`allowed_depts` 随创建/更新提交。

**Architecture:** 新共享组件 `DeptAccessPicker`(面板内懒加载 `deptApi.list`,admin 勾选/普通用户只读标签),三个对话框分别接入;后端零改动(`allowed_depts` 链路全部既有)。

**Tech Stack:** Next.js 16 / React 19 / Tailwind 4;Rstest(happy-dom `*.dom.test.tsx` 项目);浏览器 E2E 用 superpowers-chrome。

**Spec:** `docs/superpowers/specs/2026-09-05-kb-dept-access-picker-design.md`(§2 已修正:共三个对话框)

**仓库纪律(并发会话!):** 所有 git add/commit 必须精确 pathspec(`git add <paths>` + `git commit -m ... -- <paths>`),禁止 `git add -A`/裸 `git commit`。当前分支 main-dev-fork,直接提交。改文件前先重读目标区段(可能漂移)。

---

### Task 1: `DeptAccessPicker` 组件 + DOM 测试

**Files:**
- Create: `frontend/src/app/knowledge/_components/DeptAccessPicker.tsx`
- Test: `frontend/tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx`

- [ ] **Step 1: 写失败的 DOM 测试**(先看 `frontend/tests/unit/components/landing/case-study-section.dom.test.tsx` 的 rstest DOM 项目/mock 惯例再落笔;`deptApi.list` 用该文件惯例的模块 mock 方式,若 rstest 模块 mock 不便,可给组件加可选 `departments?: Department[]` prop 供测试注入——父组件不传时组件内拉取,二选一,以仓库惯例为准)

```tsx
// frontend/tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "rstest";

import { DeptAccessPicker } from "@/app/knowledge/_components/DeptAccessPicker";

const deptApiList = vi.fn();
vi.mock("@/extensions/api", () => ({
  deptApi: { list: (...args: unknown[]) => deptApiList(...args) },
}));

const DEPTS = [
  { id: "d1", name: "采矿设计院", sort_order: 1 },
  { id: "d2", name: "机电设计院", sort_order: 2 },
];

function setup(ui: React.ReactElement) {
  return render(ui);
}

describe("DeptAccessPicker", () => {
  it("admin: 渲染勾选面板,勾选触发 onChange 并出现标签", async () => {
    deptApiList.mockResolvedValue({ departments: DEPTS });
    const onChange = vi.fn();
    setup(<DeptAccessPicker selectedIds={[]} onChange={onChange} />);
    await waitFor(() => screen.getByLabelText("采矿设计院"));
    fireEvent.click(screen.getByLabelText("采矿设计院"));
    expect(onChange).toHaveBeenCalledWith(["d1"]);
  });

  it("admin: selectedIds 渲染标签,× 移除触发 onChange", async () => {
    deptApiList.mockResolvedValue({ departments: DEPTS });
    const onChange = vi.fn();
    setup(<DeptAccessPicker selectedIds={["d2"]} onChange={onChange} />);
    await waitFor(() => screen.getByText("机电设计院"));
    fireEvent.click(screen.getByLabelText("移除 机电设计院"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("readOnly: 只渲染标签,无勾选面板", async () => {
    deptApiList.mockResolvedValue({ departments: DEPTS });
    setup(<DeptAccessPicker selectedIds={["d1"]} onChange={vi.fn()} readOnly />);
    await waitFor(() => screen.getByText("采矿设计院"));
    expect(screen.queryByLabelText("采矿设计院")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("readOnly 且空: 渲染无部门提示", async () => {
    deptApiList.mockResolvedValue({ departments: DEPTS });
    setup(<DeptAccessPicker selectedIds={[]} onChange={vi.fn()} readOnly />);
    await waitFor(() => screen.getByText("你尚未加入任何部门"));
  });
});
```

(断言细节按实际渲染的 label 关联方式微调——若 checkbox 用 `<label>` 包裹则 `getByLabelText` 直接可用;若不行改用 `getByRole("checkbox", { name })`。保持 4 个用例的意图不变。)

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && pnpm test tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx
```

Expected: FAIL(模块不存在)。

- [ ] **Step 3: 写实现**

```tsx
// frontend/src/app/knowledge/_components/DeptAccessPicker.tsx
"use client";

import { Loader2, X } from "lucide-react";
import React, { useEffect, useState } from "react";

// EAI-CUSTOM: 部门级访问权限选择器(spec 2026-09-05-kb-dept-access-picker-design)
// admin: 内联勾选面板(max-h-40 滚动)+ 下方标签(× 移除);普通用户(readOnly):只读标签。
// 部门列表组件内懒加载 deptApi.list(GET /departments 仅需登录,普通用户可调)。
import { deptApi } from "@/extensions/api";
import type { Department } from "@/extensions/types";
import { cn } from "@/lib/utils";

export function DeptAccessPicker({
  selectedIds,
  onChange,
  readOnly = false,
}: {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  readOnly?: boolean;
}) {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    deptApi
      .list({ limit: 500 })
      .then((res) => {
        if (!cancelled) setDepartments(res.departments ?? []);
      })
      .catch(() => {
        if (!cancelled) setDepartments([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const nameOf = (id: string) =>
    departments.find((d) => d.id === id)?.name ?? id;

  const toggle = (id: string) =>
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id],
    );

  if (loading) {
    return <Loader2 className="text-muted-foreground h-4 w-4 animate-spin" />;
  }

  return (
    <div className="space-y-2">
      {!readOnly && (
        <div className="border-border max-h-40 overflow-y-auto rounded-lg border p-2">
          {departments.length === 0 ? (
            <p className="text-muted-foreground text-xs">暂无可选部门</p>
          ) : (
            departments.map((d) => (
              <label
                key={d.id}
                className="hover:bg-accent flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(d.id)}
                  onChange={() => toggle(d.id)}
                />
                {d.name}
              </label>
            ))
          )}
        </div>
      )}

      {selectedIds.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedIds.map((id) => (
            <span
              key={id}
              className={cn(
                "bg-primary/10 text-primary inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs",
              )}
            >
              {nameOf(id)}
              {!readOnly && (
                <button
                  type="button"
                  aria-label={`移除 ${nameOf(id)}`}
                  onClick={() => onChange(selectedIds.filter((x) => x !== id))}
                  className="hover:text-destructive"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {readOnly && selectedIds.length === 0 && (
        <p className="text-muted-foreground text-xs">你尚未加入任何部门</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd frontend && pnpm test tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx
```

Expected: 4 passed。

- [ ] **Step 5: lint + typecheck**

```bash
cd frontend && pnpm exec eslint src/app/knowledge/_components/DeptAccessPicker.tsx tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx && pnpm exec prettier --write src/app/knowledge/_components/DeptAccessPicker.tsx tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx && pnpm typecheck
```

Expected: 全 clean。

- [ ] **Step 6: Commit(pathspec)**

```bash
git add frontend/src/app/knowledge/_components/DeptAccessPicker.tsx frontend/tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx
git commit -m "feat(knowledge): DeptAccessPicker 部门级访问权限选择器(内联勾选+标签/只读)" -- frontend/src/app/knowledge/_components/DeptAccessPicker.tsx frontend/tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx
```

---

### Task 2: 创建对话框接入(page.tsx)

**Files:**
- Modify: `frontend/src/app/knowledge/page.tsx`(~106 权限 hook、~118 createForm、~193 handleCreate、创建按钮 ~897、访问权限块 ~676 之后)

- [ ] **Step 1: hook 与提交逻辑**

`const { can } = usePermission();` 改为:

```tsx
  const { can, is_admin, identity } = usePermission();
```

`handleCreate` 提交前加校验与 allowed_depts 解析(放在 `if (!createForm.name.trim()) return;` 之后):

```tsx
    // EAI-CUSTOM: 部门可见时提交 allowed_depts;admin 用勾选,普通用户自动带本部门
    const resolveAllowedDepts = () => {
      if ((createForm.access_type ?? "private") !== "dept") return undefined;
      return is_admin ? (createForm.allowed_depts ?? []) : identity.dept_ids;
    };
    const allowedDepts = resolveAllowedDepts();
    if ((createForm.access_type ?? "private") === "dept" && allowedDepts && allowedDepts.length === 0) {
      toast(is_admin ? "至少选择一个部门" : "你尚未加入任何部门,无法设置部门可见", "error");
      return;
    }
```

`kbApi.create(createForm)` 改为 `kbApi.create({ ...createForm, allowed_depts: allowedDepts })`。

- [ ] **Step 2: 渲染 Picker**

访问权限 `</div>`(CustomSelect 所在块的收尾,~676)之后插入:

```tsx
                  {(createForm.access_type ?? "private") === "dept" && (
                    <div className="mt-2">
                      <DeptAccessPicker
                        selectedIds={
                          is_admin
                            ? (createForm.allowed_depts ?? [])
                            : identity.dept_ids
                        }
                        onChange={(ids) =>
                          setCreateForm({ ...createForm, allowed_depts: ids })
                        }
                        readOnly={!is_admin}
                      />
                    </div>
                  )}
```

并加导入 `import { DeptAccessPicker } from "./_components/DeptAccessPicker";`(相对组,字母序)。

- [ ] **Step 3: 静态检查**

```bash
cd frontend && pnpm exec eslint src/app/knowledge/page.tsx && pnpm exec prettier --check src/app/knowledge/page.tsx && pnpm typecheck
```

Expected: clean。

- [ ] **Step 4: Commit(pathspec)**

```bash
git add frontend/src/app/knowledge/page.tsx
git commit -m "feat(knowledge): 创建知识库支持部门可见多选/自动带本部门" -- frontend/src/app/knowledge/page.tsx
```

---

### Task 3: 两个编辑对话框接入

**Files:**
- Modify: `frontend/src/app/knowledge/page.tsx`(列表页编辑框 ~956-991、openEdit ~255、handleEditSave ~266)
- Modify: `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`(编辑框 ~1025-1071、editForm ~104、useEffect 重置 ~254、handleEditSave)

- [ ] **Step 1: 列表页编辑框(page.tsx)**

1. `openEdit` 的 `setEditForm` 增加一行 `allowed_depts: kb.allowed_depts ?? [],`
2. 访问权限 CustomSelect 块(约 956-991)的 `</div>` 之后插入(与创建框相同的条件渲染,`createForm`→`editForm`):

```tsx
                  {(editForm.access_type ?? "private") === "dept" && (
                    <div className="mt-2">
                      <DeptAccessPicker
                        selectedIds={
                          is_admin
                            ? (editForm.allowed_depts ?? [])
                            : identity.dept_ids
                        }
                        onChange={(ids) =>
                          setEditForm({ ...editForm, allowed_depts: ids })
                        }
                        readOnly={!is_admin}
                      />
                    </div>
                  )}
```

3. `handleEditSave` 里 `kbApi.update(editKb.id, editForm)` 改为:

```tsx
      // EAI-CUSTOM: dept 提交 allowed_depts;切回私有/公开显式置 [] 清残留
      const isDept = (editForm.access_type ?? "private") === "dept";
      const allowedDepts = isDept
        ? is_admin
          ? (editForm.allowed_depts ?? [])
          : identity.dept_ids
        : [];
      if (isDept && allowedDepts.length === 0) {
        toast(is_admin ? "至少选择一个部门" : "你尚未加入任何部门,无法设置部门可见", "error");
        setEditLoading(false);
        return;
      }
      const updated = await kbApi.update(editKb.id, { ...editForm, allowed_depts: allowedDepts });
```

(原有 try/setEditLoading 结构保持;`setEditLoading(true)` 已在 try 前。)

- [ ] **Step 2: 详情页编辑框(KnowledgeBaseDetail.tsx)**

1. `editForm` 初始 state 与重置 useEffect(`[kb.id, kb.name, ...]` 那个)都补:

```tsx
    access_type: kb.access_type,
    allowed_depts: kb.allowed_depts ?? [],
```

2. 「知识库类型」CustomSelect 块(约 1039-1057)的 `</div>` 之后插入「访问权限」字段(下拉 + 条件 Picker,与列表页编辑框同构,`editForm` 同名):

```tsx
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    访问权限
                  </label>
                  <CustomSelect
                    value={editForm.access_type ?? "private"}
                    onChange={(v) =>
                      setEditForm({ ...editForm, access_type: v })
                    }
                    options={[
                      { value: "private", label: "私有", icon: <span className="flex h-3.5 w-3.5 items-center text-xs">🔒</span> },
                      { value: "public", label: "公开", icon: <span className="flex h-3.5 w-3.5 items-center justify-center">🌐</span> },
                      { value: "dept", label: "部门可见", icon: <span className="flex h-3.5 w-3.5 items-center justify-center">🏢</span> },
                    ]}
                  />
                  {(editForm.access_type ?? "private") === "dept" && (
                    <div className="mt-2">
                      <DeptAccessPicker
                        selectedIds={
                          is_admin
                            ? (editForm.allowed_depts ?? [])
                            : identity.dept_ids
                        }
                        onChange={(ids) =>
                          setEditForm({ ...editForm, allowed_depts: ids })
                        }
                        readOnly={!is_admin}
                      />
                    </div>
                  )}
                </div>
```

3. `handleEditSave` 同 Step 1.3 的 dept 解析/校验/清残留逻辑。
4. 加导入 `import { DeptAccessPicker } from "./DeptAccessPicker";`(相对组,字母序)。
5. 保存按钮(~1076)disabled 加 dept 空校验:`disabled={!editForm.name?.trim() || editLoading || ((editForm.access_type ?? "private") === "dept" && (is_admin ? (editForm.allowed_depts ?? []) : identity.dept_ids).length === 0)}`

- [ ] **Step 3: 静态检查**

```bash
cd frontend && pnpm exec eslint src/app/knowledge/page.tsx src/app/knowledge/_components/KnowledgeBaseDetail.tsx && pnpm exec prettier --check src/app/knowledge/page.tsx src/app/knowledge/_components/KnowledgeBaseDetail.tsx && pnpm typecheck
```

Expected: clean。

- [ ] **Step 4: Commit(pathspec)**

```bash
git add frontend/src/app/knowledge/page.tsx frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx
git commit -m "feat(knowledge): 两个编辑对话框接入部门可见选择(含allowed_depts清残留)" -- frontend/src/app/knowledge/page.tsx frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx
```

---

### Task 4: 浏览器 E2E

**Files:** 无代码改动。

- [ ] **Step 1: 浏览器验证**(superpowers-chrome,admin@eai-flow.com / Admin@2026,http://localhost:2026)

1. 新建知识库:选「部门可见」→ 勾选面板出现 → 勾 2 个部门 → 标签显示 → 保存成功;
2. 卡片/编辑框回显 2 个部门标签;编辑改勾(去掉 1 加 1)→ 保存 → 回显正确;
3. 切回「公开」保存 → 再进编辑无部门标签残留;
4. 「部门可见」+ 0 勾选 → 保存禁用/报错提示;
5. 知识工厂等其他页面无回归迹象(抽查法规标准 tab 打开正常)。

- [ ] **Step 2: 普通用户验证**(如环境有非管理员账号则登录验证;无则降级为 API 检查 `/api/extensions/auth/me` 的 dept_ids 与 `/api/extensions/departments` 可访问性,并确认前端 readOnly 分支逻辑由单测覆盖)

- [ ] **Step 3: 收尾**

- OpenWolf:`.wolf/memory.md` 一行、`.wolf/anatomy.md`(DeptAccessPicker 新文件)、问题入 buglog。
- 回滚:各任务 commit 独立 revert。

---

## Self-Review 记录

- **Spec coverage:** §3.1→Task 1;§3.2→Task 2;§3.3→Task 3(注意 spec §2 已修正:编辑框有两个,列表页编辑框已有权限下拉,详情页编辑框从零补——两者分别处理);§5 测试→Task 1 Step 1/4 + Task 4。✓
- **Placeholder scan:** 无 TBD;代码步骤含完整代码;Task 1 测试的 label 断言微调自由度已显式注明。✓
- **Type consistency:** `DeptAccessPicker({selectedIds, onChange, readOnly})` 三处调用一致;`resolveAllowedDepts` 逻辑在 create/edit 两处语义一致(admin 用表单态、普通用户用 identity.dept_ids、非 dept undefined/[])。✓
- **已知修正记录:** spec 初稿漏了列表页编辑框已有权限下拉的事实,已在 spec §2 修正(608c8f1b8)。✓
