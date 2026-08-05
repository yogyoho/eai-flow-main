# ABAC-lite 范围补全（P0）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全 ABAC-lite 范围内的两个前端缺口：①条件值下拉补 `dept_ids`/`member_projects` 选项；②`or` 树条件只读展示 + 保存保留（防静默丢条件/误显"全局"）。

**Architecture:** 两处都在策略编辑器（自定义策略 tab）前端。①`attrValueOptions` 扩展 + 懒加载项目列表；②`toUIConditions`/`toEngineConditions` 用 `__or__` 标记伪条件承载原始 or 树，PolicyRow/编辑表单渲染为只读徽章。

**Tech Stack:** Next.js 16 / React 19 / TypeScript / vitest。前端验证命令：`npx tsc --noEmit`（宿主）、`npx vitest run tests/unit/extensions/roles/policy-converters.test.ts`。

**Spec:** `docs/superpowers/specs/2026-08-05-rbac-abac-architecture-assessment.md` §5 P0。

**Conventions:** 改 `app/` EAI 定制代码无需 EAI-CUSTOM 三重规范（非 harness 上游）；前端改动用 `EAI-CUSTOM` 注释。提交到 `main-dev-fork`。改动前端源码后需 `docker compose -p eai-docker restart frontend`（HMR 对 .tsx 不可靠），浏览器经 nginx `http://localhost:2026` 验证。

---

## 文件结构

- `frontend/src/extensions/api/index.ts` — 新增 `projectApi.list`。
- `frontend/src/extensions/role/policyConverters.ts` — `toUIConditions`/`toEngineConditions` 支持 `__or__` 标记。
- `frontend/tests/unit/extensions/roles/policy-converters.test.ts` — or 树往返单测。
- `frontend/src/app/admin/roles/page.tsx` — `attrValueOptions` 扩展 + 项目懒加载；PolicyRow/PolicyEditForm 渲染 `__or__` 只读徽章。

---

## Task 1: `dept_ids`/`member_projects` 条件值选项

**Files:**
- Modify: `frontend/src/extensions/api/index.ts`
- Modify: `frontend/src/app/admin/roles/page.tsx`（PolicyEditForm）

- [ ] **Step 1: api/index.ts 加 `projectApi.list`**

在 `deptApi` 定义附近（约 L334 后）加：

```ts
// EAI-CUSTOM (P0): 项目列表 —— 供条件值 member_projects 选项
export const projectApi = {
  list: (params?: { skip?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.skip) query.set("skip", String(params.skip));
    if (params?.limit) query.set("limit", String(params.limit));
    return request<{ projects: Array<{ id: string; name: string }>; total: number }>(`/projects?${query}`);
  },
};
```

- [ ] **Step 2: PolicyEditForm 加 projects 状态 + 懒加载**

在 `deptApi.list()` fetch 后追加（PolicyEditForm 的 useEffect，约 L1285）：

```tsx
  const [projects, setProjects] = useState<Array<{ id: string; name: string }>>([]);
  // ...现有 users/depts state 后
  // ...useEffect 内追加：
  projectApi.list({ limit: 500 }).then((r) => { if (active) setProjects(r.projects ?? []); }).catch(() => {});
```

并补 import：`import { deptApi, permissionsApi, projectApi, roleApi, userApi } from "@/extensions/api";`

- [ ] **Step 3: attrValueOptions 加两个 case**

在 `attrValueOptions`（约 L1289）的 `dept_id` case 后追加：

```tsx
      case "dept_ids": return depts.map((d) => ({ value: d.id, label: d.name }));              // 多值部门（in/not_in 用）
      case "member_projects": return projects.map((p) => ({ value: p.id, label: p.name }));   // 多值项目成员
```

- [ ] **Step 4: typecheck + 浏览器验证**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -c "error TS"` → `0`。
Run: `docker compose -p eai-docker restart frontend`。
浏览器：`/admin/roles` → 自定义策略 → 添加策略 → 属性选「部门ID」/「所属部门」→ 值 chip-input 建议含部门；属性选「成员项目」→ 建议含项目名。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/api/index.ts frontend/src/app/admin/roles/page.tsx
git commit -m "feat(rbac): P0 条件值选项补 dept_ids/member_projects（懒加载项目列表）" -- frontend/src/extensions/api/index.ts frontend/src/app/admin/roles/page.tsx
```

---

## Task 2: `or` 树条件只读展示 + 保存保留

**Files:**
- Modify: `frontend/src/extensions/role/policyConverters.ts`
- Modify: `frontend/tests/unit/extensions/roles/policy-converters.test.ts`
- Modify: `frontend/src/app/admin/roles/page.tsx`（PolicyRow + PolicyEditForm + PolicyRow 条件渲染）

- [ ] **Step 1: 写失败单测（or 树往返）**

在 `policy-converters.test.ts` 的 `toUIConditions` describe 里追加：

```ts
  it("or 树 → __or__ 只读标记，可往返还原", () => {
    const orTree = { or: [{ attr: "role_code", op: "eq", value: "dept_head" }, { attr: "user_id", op: "eq", value: "u1" }] };
    const ui = toUIConditions(orTree);
    expect(ui.length).toBe(1);
    expect(ui[0]!.attribute).toBe("__or__");
    expect(toEngineConditions(ui)).toEqual(orTree);
  });

  it("or 树不再退空条件（不误显全局）", () => {
    const ui = toUIConditions({ or: [{ attr: "a", op: "eq", value: "1" }] });
    expect(ui.length).toBeGreaterThan(0);
  });
```

Run: `npx vitest run tests/unit/extensions/roles/policy-converters.test.ts` → FAIL（toUIConditions 现在 or 树返回 []，toEngineConditions 不认 __or__）。

- [ ] **Step 2: 实现转换器**

`policyConverters.ts`：
- `toUIConditions`：把 or 分支从 `return [] + console.warn` 改为：

```ts
  if (Array.isArray(obj.or)) {
    // EAI-CUSTOM (P0): or 树无法在 UI 行编辑器逐条编辑，改为只读标记承载原始条件，防误显"全局"/保存丢条件
    return [{ attribute: "__or__", operator: "or", value: JSON.stringify(conds) }];
  }
```

- `toEngineConditions`：开头加 or 标记还原：

```ts
export function toEngineConditions(conds: PolicyCondition[]): Record<string, unknown> {
  if (!conds.length) return {};
  const orMarker = conds.find((c) => c.attribute === "__or__");
  if (orMarker) {
    try { return JSON.parse(orMarker.value || "{}") as Record<string, unknown>; }
    catch { return {}; }
  }
  return { and: conds.map((c) => { /* 现有逻辑不变 */ }) };
}
```

- [ ] **Step 3: 跑单测确认通过**

Run: `npx vitest run tests/unit/extensions/roles/policy-converters.test.ts` → 全绿（含既有用例）。

- [ ] **Step 4: PolicyRow 渲染 `__or__` 只读徽章**

`PolicyRow` 的条件渲染（约 L1106 `{c.attribute || "?"} {c.operator} {c.value || "?"}`）改为：

```tsx
              {c.attribute === "__or__" ? (
                <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-600 border border-amber-500/30">
                  ⚠ 或(OR) 条件（只读）
                </span>
              ) : (
                <>{(ATTR_LABELS[c.attribute] ?? c.attribute) || "?"} {OP_LABELS[c.operator] ?? c.operator} {c.value || "?"}</>
              )}
```

- [ ] **Step 5: PolicyEditForm 渲染 `__or__` 只读徽章（不可编辑）**

条件行渲染：当 `c.attribute === "__or__"` 时，不渲染 属性/操作符/值 三个控件，改渲染只读徽章：

```tsx
            {form.conditions.map((c, i) => (
              <div key={i} className="flex items-center gap-2">
                {c.attribute === "__or__" ? (
                  <span className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-amber-500/10 text-amber-600 border border-amber-500/30">
                    ⚠ 或(OR) 条件（只读，保存将保留原条件）
                  </span>
                ) : (
                  <>
                    {/* ...现有 属性/操作符/值 三控件不变... */}
                  </>
                )}
                <button onClick={() => removeCondition(i)} disabled={c.attribute === "__or__"} className="p-1 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-30">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
```

- [ ] **Step 6: typecheck + 浏览器验证**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -c "error TS"` → `0`。
Run: `docker compose -p eai-docker restart frontend`。
浏览器：用 API 建一个 `conditions={"or":[...]}` 的策略（curl 或 evaluate_script fetch），刷新策略列表 → 显示「⚠ 或(OR) 条件（只读）」而非「全局」；编辑该策略 → 显示只读徽章、保存 → 后端 conditions 仍为 or 树（未丢）。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/extensions/role/policyConverters.ts frontend/tests/unit/extensions/roles/policy-converters.test.ts frontend/src/app/admin/roles/page.tsx
git commit -m "fix(rbac): P0 or 树条件只读展示+保存保留（__or__ 标记往返，防误显全局/丢条件）" -- frontend/src/extensions/role/policyConverters.ts frontend/tests/unit/extensions/roles/policy-converters.test.ts frontend/src/app/admin/roles/page.tsx
```

---

## Self-Review

**Spec coverage:** spec §5 P0 两项（UI 补 dept_ids/member_projects 值选项、or 树只读展示防丢）→ Task 1 / Task 2 对应。P1-P3（完整 ABAC 演进）不在范围，符合用户选择。

**Placeholder scan:** 无 TBD/TODO；Task 2 Step 5 的条件三控件以「现有...不变」指代（紧邻上下文已存在，非空泛占位）；项目类型用内联 shape（types.ts 无 Project 类型，不新增文件）。

**Type consistency:** `attrValueOptions` 返回 `{value, label}[]` 与现有 case 一致；`__or__` 标记用 `PolicyCondition`（attribute/operator/value 均 string，value 存 JSON）符合类型；`projectApi.list` 返回 shape 与 `deptApi.list` 风格一致。

**风险：** `toEngineConditions` 的 `__or__` 分支会忽略同策略其他 UI 条件（or 树策略本就不该编辑条件，可接受）；`JSON.parse` 失败退 `{}`（数据损坏时至少不抛错）。
