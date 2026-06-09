# 项目文件夹管理设计规格

> 日期: 2026-06-09
> 状态: 草案
> 范围: 文档空间项目文件夹的 CRUD 管理、与项目管理模块的直接绑定、树形子文件夹支持

## 背景

当前文档空间的项目文件夹是一个虚拟概念 — 没有独立的数据库表，只是 `ai_documents.folder` 字段的 `DISTINCT` 值。这导致：

- 无法重命名文件夹（需要批量更新所有文档的 folder 字段）
- 无法删除文件夹（只能逐个删除或移动文档）
- 文件夹与项目之间没有结构化关联（只通过 `AIDocument.project_id` 间接关联）
- 不支持子文件夹层级
- 无法对文件夹做权限控制

本设计将文件夹从虚拟概念升级为独立实体，与项目管理模块直接绑定，并支持树形子文件夹结构。

## 设计决策

| 维度 | 决策 | 理由 |
|------|------|------|
| 关联方式 | 直接绑定 — 项目与文件夹一一对应 | 用户期望文档空间中的项目文件夹反映真实项目状态 |
| 删除行为 | 硬删除 — 项目删除时文件夹和文档全部清除 | 用户明确选择，与项目生命周期一致 |
| 管理权限 | 项目管理员（owner/manager）才能重命名/删除 | 防止普通成员误操作影响项目文档结构 |
| 内部结构 | 支持子文件夹 — 树形层级，最大深度 3 层 | 按阶段/章节/成员分组管理文档 |
| 交互方式 | 悬浮操作按钮（"+" 新建 + "⋯" 更多操作） | 比右键菜单更易发现，移动端友好 |
| 侧边栏布局 | 内联树形展开 | 与现有侧边栏风格一致，层级关系清晰 |

## 数据模型

### 新增 `folders` 表

```sql
CREATE TABLE folders (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    parent_id     UUID REFERENCES folders(id) ON DELETE CASCADE,
    project_id    UUID REFERENCES report_projects(id) ON DELETE CASCADE,
    owner_id      UUID NOT NULL REFERENCES users(id),
    sort_order    INTEGER DEFAULT 0,
    is_system     BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_folders_project_id ON folders(project_id);
CREATE INDEX idx_folders_parent_id ON folders(parent_id);
CREATE INDEX idx_folders_owner_id ON folders(owner_id);
```

字段说明：

- `parent_id` — NULL 表示根文件夹。`ON DELETE CASCADE` 确保删除父文件夹时级联删除子文件夹
- `project_id` — 只在根文件夹设置，子文件夹通过 `parent_id` 链追溯到根。NULL 表示个人文件夹
- `owner_id` — 文件夹创建者，用于个人文件夹的权限判断
- `sort_order` — 同级文件夹的排序权重
- `is_system` — 系统文件夹（如"默认文件夹"）不可删除

### 修改 `ai_documents` 表

```sql
ALTER TABLE ai_documents ADD COLUMN folder_id UUID REFERENCES folders(id) ON DELETE SET NULL;
```

过渡期保留原有 `folder` 字符串字段，迁移完成后移除。

### 实体关系

```
ReportProject
    │
    ├── 1:1 ──> Folder (root, parent_id=NULL, project_id=project.id)
    │              │
    │              ├── 1:N ──> Folder (sub, parent_id=root.id)
    │              │              │
    │              │              └── 1:N ──> AIDocument (folder_id=sub.id)
    │              │
    │              └── 1:N ──> AIDocument (folder_id=root.id)
    │
    └── 删除时 CASCADE → 根文件夹及所有子文件夹级联删除
                         AIDocument 需应用层显式删除（folder_id 是 SET NULL）

User (无项目关联)
    │
    └── 1:N ──> Folder (personal, project_id=NULL, parent_id=NULL)
                   └── 1:N ──> AIDocument
```

## API 设计

所有端点挂在 `/api/extensions/docmgr/folders` 下。

### 端点列表

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `GET` | `/folders` | 获取文件夹树 | 所有用户 |
| `POST` | `/folders` | 创建子文件夹 | 项目管理员 / 文件夹 owner |
| `PATCH` | `/folders/{id}` | 重命名文件夹 | 项目管理员 / 文件夹 owner |
| `DELETE` | `/folders/{id}` | 删除文件夹 | 项目管理员 |
| `PATCH` | `/folders/{id}/sort` | 调整排序 | 项目成员 |
| `POST` | `/projects/{id}/auto-create-folder` | 项目创建时自动创建根文件夹 | 系统内部调用 |

### GET /folders

获取文件夹树，支持按项目和范围过滤。

请求参数：
- `project_id` (UUID, 可选) — 获取指定项目的文件夹树
- `project_scope` (string, 可选) — `"project"` 所有项目文件夹 / `"personal"` 个人文件夹
- `parent_id` (UUID, 可选) — 获取某个文件夹的直接子文件夹

响应（树形结构）：
```json
{
    "folders": [
        {
            "id": "uuid",
            "name": "城市规划研究",
            "project_id": "uuid",
            "parent_id": null,
            "sort_order": 0,
            "doc_count": 5,
            "children": [
                {
                    "id": "uuid",
                    "name": "阶段一：调研",
                    "parent_id": "uuid",
                    "doc_count": 3,
                    "children": []
                }
            ]
        }
    ]
}
```

### POST /folders

创建子文件夹。

请求体：
```json
{
    "name": "阶段二",
    "parent_id": "uuid",
    "project_id": "uuid"
}
```

权限检查逻辑：
1. 如果 `parent_id` 对应的根文件夹绑定了 `project_id` → 检查当前用户是否该项目的 owner/manager
2. 如果是个人文件夹（`project_id=NULL`）→ 检查是否是 owner
3. 层级深度不超过 3 层

### PATCH /folders/{id}

重命名文件夹。

请求体：
```json
{ "name": "新文件夹名" }
```

特殊逻辑：如果该文件夹是项目根文件夹（`parent_id=NULL` 且 `project_id` 不为空），同步更新 `ReportProject.name`。

### DELETE /folders/{id}

删除文件夹及其全部内容。

行为：
1. 递归查找所有子文件夹
2. 删除所有关联的 AIDocument 记录及物理文件
3. 删除所有子文件夹（CASCADE）
4. 删除该文件夹自身

限制：
- 项目根文件夹不能单独删除（需通过删除项目来删除）
- 系统文件夹（`is_system=true`）不能删除
- 只有项目管理员（owner/manager）有权执行

### 与项目模块的集成

**项目创建时**（`project/service.py` 的 `create_project()`）：
```python
folder = await FolderService.create_root_folder(
    db=db, name=project.name, project_id=project.id, owner_id=current_user.id
)
```

**项目删除时**（`DELETE /projects/{id}`）：
```python
# 显式调用，因为 AIDocument.folder_id 是 SET NULL 而非 CASCADE
await FolderService.delete_tree(db, root_folder_id)
```

**项目重命名时**（`PATCH /projects/{id}`）：
```python
if update_data.name:
    await FolderService.rename(db, root_folder_id, update_data.name)
```

## 前端设计

### 侧边栏布局

采用内联树形展开方案：

```
📁 文档空间
├── 我的文档
│   └── 📄 默认文件夹
└── 📂 项目文件夹                    ← 区域标题
    ├── ▼ 🏗️ 城市规划研究  [+] [⋯]  ← 项目根节点（悬浮显示按钮）
    │   ├── 📂 阶段一：调研    [⋯]
    │   ├── 📂 阶段二：分析    [⋯]  ← 当前选中（高亮）
    │   └── 📂 阶段三：报告    [⋯]
    └── ▶ 📊 数据可视化项目  [+] [⋯]  ← 折叠状态
```

- 每个文件夹节点悬浮时显示 "+"（新建子文件夹）和 "⋯"（更多操作：重命名/删除）
- 点击文件夹名称展开/折叠子文件夹，同时右侧主区域展示该文件夹下的文档列表
- 项目管理员才能看到管理操作按钮，普通成员只看到展开/折叠

### 组件架构

```
DocumentManagement (现有)
├── Sidebar
│   ├── PersonalFolderNav (现有)
│   └── ProjectFolderTree (新增/替换)
│       ├── ProjectFolderNode (单个项目节点 — 可展开/折叠)
│       │   ├── FolderActionButtons (悬浮 "+" + "⋯" 按钮)
│       │   └── SubFolderNode[] (子文件夹递归渲染)
│       └── ProjectFolderActions (⋯ 弹出菜单：重命名/删除)
│
├── useFolderTree (新 hook)
│   ├── folders, projectFolders, expandedKeys
│   ├── createFolder(parentId, name)
│   ├── renameFolder(id, name)
│   ├── deleteFolder(id)
│   └── moveDocumentToFolder(docId, folderId)
│
└── NewSubFolderDialog (新增 — 复用 FolderPickerDialog 模式)
```

### 交互流程

**创建子文件夹：** 点击 "+" → 弹出输入框（输入名称） → `POST /folders` → 树刷新

**重命名：** 点击 "⋯" → 选择"重命名" → 节点变为 inline input → 回车提交 `PATCH /folders/{id}` → 项目根文件夹同步更新项目名

**删除：** 点击 "⋯" → 选择"删除" → 确认弹窗（"将删除 X 个子文件夹和 Y 个文档，不可恢复"） → `DELETE /folders/{id}` → 树刷新

**文档列表联动：** 点击子文件夹 → `activeNav="project_folder"` + `activeFolderId=uuid` → `GET /documents?folder_id=xxx` 过滤文档列表

### 权限 UI 表现

| 角色 | 可见操作 |
|------|---------|
| 项目 owner/manager | "+" 新建、"⋯" 重命名/删除 |
| 项目普通成员 | 仅展开/折叠，无管理按钮 |
| 非项目成员 | 项目文件夹不显示在侧边栏 |

## 迁移策略

### 分 3 步执行

**Step 1 — 建表 + 新字段**
- 创建 `folders` 表
- `ai_documents` 新增 `folder_id` 字段（允许 NULL）

**Step 2 — 数据迁移脚本**
- 为每个有 `project_id` 的文档集合创建项目根文件夹
- 为每个不同的 `folder` 字符串值创建子文件夹
- 更新所有 `AIDocument.folder_id` 指向对应文件夹
- 为个人文档创建文件夹（`project_id=NULL`）

**Step 3 — 切换 + 清理**
- 确认所有文档都有 `folder_id`
- 前端完全切换到 `folder_id` 模式
- 未来版本移除 `ai_documents.folder` 列

### 过渡期兼容

| 阶段 | folder 字段 | folder_id 字段 | 前端行为 |
|------|------------|---------------|---------|
| 迁移前 | 唯一来源 | 不存在 | 现有逻辑不变 |
| 过渡期 | 仍然写入 | 同步写入 | 优先读 folder_id，fallback 到 folder |
| 迁移后 | 已删除 | 唯一来源 | 只用 folder_id |

后端过渡期写入逻辑：
```python
doc.folder_id = folder_id
doc.folder = folder.name  # 兼容旧前端
```

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| 删除包含文档的子文件夹 | 确认弹窗："此文件夹包含 X 个文档和 Y 个子文件夹，全部将被永久删除" |
| 删除项目根文件夹 | 前端禁止操作（只能通过删除项目触发） |
| 重命名为空字符串 | 前端校验，不允许提交 |
| 同级重名冲突 | 后端返回 409，前端提示"同名文件夹已存在" |
| 非管理员尝试管理操作 | 后端返回 403，前端隐藏管理按钮 |
| 层级超限（超过 3 层） | 后端返回 422，前端在创建时校验深度 |
| 网络中断 | 乐观更新 + 回滚，toast 提示失败 |

## 不在范围内

以下功能明确不在本次设计中：

- 文件夹拖拽排序（未来可通过 sort_order 字段扩展）
- 文件夹颜色/图标自定义
- 文件夹描述/备注
- 文档在文件夹间拖拽移动（保留现有的移动弹窗方式）
- 回收站/软删除机制
