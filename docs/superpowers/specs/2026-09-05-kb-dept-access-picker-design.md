# 知识库对话框部门级访问权限选择 — 设计

日期:2026-09-05
状态:APPROVED(设计经用户批准;admin 勾选控件形态=内联勾选面板)

## 1. 需求

新建/编辑知识库对话框的「访问权限」选「部门可见」(value `dept`)时:

- **admin**:可勾选 1 或多个部门,选中项以标签形式显示在下拉框下方(可 × 移除)
- **普通用户**:自动以标签显示自己所在部门(只读,不可改)

## 2. 现状与缺口

| 位置 | 现状 |
|---|---|
| 创建对话框(page.tsx,~641) | 有访问权限下拉(私有/公开/部门可见),**无部门选择器**;`allowed_depts` 未提交 |
| 编辑对话框·列表页(page.tsx,~956) | **已有**访问权限下拉(同三项),但 `allowed_depts` 不在 openEdit/editForm 里,未提交 |
| 编辑对话框·详情页(KnowledgeBaseDetail,~1025) | **连访问权限字段都没有**(仅名称/类型/描述);`editForm` 不含 `access_type`/`allowed_depts` |
| 后端 | **零改动需求**:`allowed_depts: string[]` 在 Create/Update schema、KB 模型、ABAC 可见性过滤中全部既有;bug-1134 的 owner 部门自动兜底保留 |
| 数据源 | `usePermission().is_admin`(admin 判定);`identity.dept_ids`(当前用户部门,`/me` 已带);`deptApi.list()`(部门名映射,仅需登录,普通用户可调,grants UI 已用) |

**共三个对话框**(列表页创建/列表页编辑/详情页编辑),全部接入同一 Picker 组件。

## 3. 设计

### 3.1 新共享组件 `DeptAccessPicker`

`frontend/src/app/knowledge/_components/DeptAccessPicker.tsx`:

```ts
export function DeptAccessPicker({
  selectedIds,
  onChange,
  readOnly,
}: {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  readOnly?: boolean;
}): JSX.Element | null
```

- 组件内懒加载 `deptApi.list({ limit: 500 })`(id→name 映射;加载态 spin;失败态提示)
- `readOnly=false`(admin):渲染内联勾选面板(`max-h-40 overflow-y-auto` + checkbox + 部门名);勾选/取消经 `onChange` 上抛
- 面板下方渲染标签区:`selectedIds` → chip(部门名 + × 移除);× 移除经 `onChange`
- `readOnly=true`(普通用户):只渲染标签区,无面板、无 ×
- `selectedIds` 为空且 readOnly → 渲染提示「你尚未加入任何部门」

### 3.2 创建对话框(page.tsx)

- `access_type === "dept"` 时,下拉框下方渲染 `<DeptAccessPicker selectedIds={createForm.allowed_depts ?? []} onChange={(ids) => setCreateForm({ ...createForm, allowed_depts: ids })} readOnly={!is_admin} />`
- 普通用户初始/回退:`allowed_depts = identity.dept_ids`(选 dept 时若空则自动带入)
- 保存校验(as-built):dept 下标签数为 0 → 点保存时 toast 报错(「至少选择一个部门」/「你尚未加入任何部门,无法设置部门可见」)并阻止提交
- 提交:`access_type === "dept"` 时带 `allowed_depts`;否则 `allowed_depts: undefined`

### 3.3 编辑对话框(KnowledgeBaseDetail)——补齐缺口

- 新增「访问权限」下拉(私有/公开/部门可见,与创建框同 options),初始 `editForm.access_type = kb.access_type`
- `editForm.allowed_depts` 初始化自 `kb.allowed_depts ?? []`;`openEdit` 时同步重置
- `access_type === "dept"` 时渲染 Picker(同 3.2 规则,`readOnly={!is_admin}`)
- 保存:`dept` → 带 `allowed_depts`;切回 `private`/`public` → `allowed_depts: []`(清残留,防旧部门可见性残留)

### 3.4 权限与边界

- admin 判定唯一来源 `usePermission().is_admin`(/me 基于角色 is_system)
- `identity.dept_ids` 与 `Department.id` 同域(extensions 同库),直接映射
- 编辑入口已有 `kb:update` 权限 gate,无新增权限面
- 部门被删后的脏 id:标签按 deptApi.list 能映射到的显示,映射不到的显示原始 id(不阻塞保存;可见性过滤对不存在部门天然无效果)
- **已知取舍(final review 提出,待裁决)**:持有 `kb:update` 的非管理员(部门主管类角色)编辑他人创建的部门可见 KB 时,提交会用自己所在部门覆盖 `allowed_depts`(静默收窄)。后端按 partial-update 契约忠实执行。候选后续:非管理员保存时与既有 allowed_depts 合并 / 禁止非管理员编辑他人 KB 的访问字段 / 明确接受并文档化

## 4. 明确不做

- 后端任何改动(schema/校验/可见性/自动兜底均已存在)
- CustomSelect 组件改造(部门勾选是独立面板,不动既有下拉)
- 部门树形结构展示(平铺列表,超长滚动)
- 非 dept 访问类型下的其他表单联动

## 5. 测试与验证

- **组件 DOM 测试** `frontend/tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx`(happy-dom,renderHook/render):①readOnly=true 只渲染标签不渲染面板;②勾选一个部门触发 onChange 且标签出现;③标签 × 移除触发 onChange;④空 readOnly 渲染无部门提示
- **静态检查**:`pnpm lint && pnpm typecheck`
- **浏览器 E2E**(Docker):①admin 新建 KB 选部门可见→勾 2 部门→标签显示→保存→详情/编辑回显 2 标签;②编辑改勾选→保存→回显;③切回公开保存→再进编辑无残留标签;④普通用户(test-procurement)选部门可见→自动显示其部门标签且无勾选面板;⑤私有/公开下无 Picker
- **回滚**:revert 对应 commit

## 6. 涉及文件

| 文件 | 改动 |
|---|---|
| `frontend/src/app/knowledge/_components/DeptAccessPicker.tsx` | 新建组件 |
| `frontend/tests/unit/app/knowledge/_components/DeptAccessPicker.dom.test.tsx` | 新建 DOM 测试 |
| `frontend/src/app/knowledge/page.tsx` | 创建框接入 Picker + 校验 + 提交带 allowed_depts |
| `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx` | 编辑框补访问权限下拉 + Picker + 校验 + 保存逻辑 |
