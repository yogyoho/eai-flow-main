# Phase 3：前端全链路权限控制 — 实现计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 执行。

**目标：** 权限 API 端点、`usePermission` React Hook、角色管理 UI 三 Tab 升级。

**依赖：** Phase 1 + 2（已完成）

---

### Task 1: 权限 API 端点

**文件：**
- Create: `backend/app/extensions/auth/routers.py`
- Modify: `backend/app/gateway/app.py` (register router)

```python
# GET /api/permissions/registry → 所有模块 + 权限点 + 数据域（来自 PermissionRegistry）
# GET /api/permissions/me → 当前用户的权限列表 + 身份属性
```

### Task 2: `usePermission` React Hook

**文件：**
- Create: `frontend/src/core/permissions/usePermission.ts`
- Create: `frontend/src/core/permissions/PermissionProvider.tsx`

```typescript
// usePermission() → { can, identity, permissions, isLoading }
// can("kb:create") → true/false
// identity.dept_ids → string[]
```

### Task 3: 角色管理 UI 三 Tab 升级

**文件：**
- Modify: `frontend/src/app/admin/roles/page.tsx`

**Tab 1 操作权限：** 动态渲染 permission.yaml 的模块+权限点，不再硬编码 `PERMISSION_CATEGORIES`
**Tab 2 数据权限：** 选择预置 data_scope 模板
**Tab 3 自定义策略：** 策略编辑器（条件+效果），调用 `/api/policies` CRUD

### Task 4: 按钮级权限控制

**文件：** 各页面按需修改

示例：
```tsx
const { can } = usePermission()
{can("kb:create") && <Button>新建知识库</Button>}
```

---

**预估：** 4 tasks, ~8 files, 前端为主
