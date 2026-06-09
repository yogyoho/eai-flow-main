# 沙箱输出文件自动同步到文档空间设计规格

> 日期: 2026-06-09
> 状态: 草案
> 范围: 将 DeerFlow 对话中 AI 生成的沙箱输出文件实时同步到文档空间，按任务名组织到文件夹中，支持文本文件编辑

## 背景

当前 DeerFlow 对话中 AI 通过沙箱生成的文件（`/mnt/user-data/outputs/`）需要用户手动触发同步才能出现在文档空间中。同步时机不确定，文件组织依赖虚拟文件夹字符串，缺乏结构化管理和编辑能力。

本设计将文件同步改为实时自动触发，利用新的 Folder 实体系统将文件按任务名组织到文件夹中，并对文本文件提供编辑能力。

## 设计决策

| 维度 | 决策 | 理由 |
|------|------|------|
| 同步时机 | 实时自动 — `present_files` 工具执行后触发 | `present_files` 是 AI 明确标记输出文件的入口，语义准确，避免同步中间产物 |
| 同步范围 | 仅 `/mnt/user-data/outputs/` 目录 | outputs 是最终输出目录，workspace 和 uploads 不是最终产物 |
| 文件夹命名 | 使用线程标题（任务名） | 用户可通过标题快速定位对应任务的文件 |
| 编辑能力 | ASCII 文本文件可编辑 | 文本文件有明确的编辑场景（修改报告、调整数据等） |
| 项目分流 | 项目任务同步到项目文件夹，个人任务同步到个人文件夹 | 避免项目文件混入个人空间 |

## 同步触发机制

### 触发点：`present_files` 工具

当 AI 在对话中调用 `present_files(["report.md", "data.csv"])` 向用户展示输出文件时，工具已知：
- 被展示的文件路径列表
- 当前线程 ID（从 ThreadState 获取）
- 当前用户 ID（从 ThreadState 获取）

`present_files` 几乎总在文件生成后被调用，是同步的最佳时机。比在 `write_file`/`bash` 后触发更精准 — 这些工具可能写入临时文件或中间产物，不是最终输出。

### 流程

```
AI 调用 present_files(["report.md", "data.csv"])
  → present_files 工具执行（现有逻辑不变）
  → 新增：异步调用 sync_outputs_to_docmgr(thread_id, user_id, file_paths)
    → 为线程标题创建/查找子文件夹 Folder
    → 为每个文件创建/更新 AIDocument(folder_id=xxx, doc_type="file_ref")
  → 文档空间实时可见
```

## 文件夹与文档创建逻辑

### 项目 vs 个人分流

```
sync_outputs_to_docmgr(thread_id, user_id, file_paths)
  │
  ├── 获取线程标题
  ├── 检测 project_id = _detect_project_from_thread(thread_id)
  │
  ├── project_id 不为空（项目任务）:
  │   → 查找项目根文件夹 (Folder WHERE project_id=xxx, parent_id=NULL)
  │   → 在项目根文件夹下查找/创建子文件夹 (name=线程标题)
  │   → 文档归属到项目子文件夹
  │   → AIDocument.project_id = project_id
  │
  └── project_id 为空（个人任务）:
      → 查找用户个人根文件夹 (Folder WHERE owner_id=user_id, project_id=NULL, parent_id=NULL)
      → 在个人根文件夹下查找/创建子文件夹 (name=线程标题)
      → 文档归属到个人子文件夹
      → AIDocument.project_id = NULL
```

### 文件夹结构示例

**个人任务：**
```
我的文档 (root, project_id=NULL)
├── 默认文件夹
└── "关于城市规划的调研报告" (个人子文件夹, name=线程标题)
    ├── research_report.md
    └── city_data.csv
```

**项目任务：**
```
辽阳石化新装置建设消防设计专篇 (root, project_id=xxx)
├── project-chapters
└── "消防设计初稿编写" (项目子文件夹, name=线程标题)
    ├── design_draft.md
    └── specifications.yaml
```

### 幂等性

通过 `file_ref_path + source_thread_id` 去重，多次调用不会创建重复记录。现有文件内容在沙箱中已是最新，跳过即可。

### 双写兼容

同步时同时设置 `folder_id`（新 FK）和 `folder`（旧字符串字段），保持过渡期兼容。

## 编辑能力

### 文件类型规则

| 文件类型 | MIME 模式 | 可编辑 | 行为 |
|---------|----------|--------|------|
| `.md`, `.txt`, `.rst`, `.html`, `.json`, `.yaml`, `.csv`, `.py`, `.js`, `.ts`, `.sh` 等 | `text/*`, `application/json`, `application/xml` 等 | ✅ | 自动转为可编辑文档，在编辑器中打开 |
| `.docx`, `.pdf`, `.xlsx`, `.png`, `.jpg`, `.zip` 等二进制文件 | `application/vnd.*`, `image/*`, `audio/*`, `video/*` 等 | ❌ | 仅预览，不可编辑 |

### 文本文件编辑流程

1. 用户在文档空间点击文本类型的 `file_ref` 文档
2. 前端检测到 `doc_type="file_ref"` + 文本 MIME 类型
3. 自动调用 `move_to_documents` API 将文件内容读取到 `content` 字段
4. 文档转为 `doc_type="document"`，在 TiptapEditor 中打开编辑
5. 保存时将内容写回物理文件（`file_ref_path`）

## 实现位置

### 后端

| 变更 | 文件 | 说明 |
|------|------|------|
| 新增方法 | `docmgr/service.py` | `sync_outputs_to_docmgr()` — 核心同步逻辑 |
| 修改工具 | `harness/deerflow/tools/builtins/present_files.py` | 执行后调用同步方法 |
| 修改方法 | `docmgr/service.py` | `move_to_documents()` — 增加文本类型自动转换 |
| 可能新增 | `harness/deerflow/tools/builtins/present_files.py` | 导入 app 层的同步方法（需通过回调或事件解耦） |

### 前端

| 变更 | 文件 | 说明 |
|------|------|------|
| 修改 | `docmgr/DocumentManagement.tsx` | 点击文本 file_ref 时自动调用 move_to_documents |
| 修改 | `docmgr/useDocuments.ts` | 暴露 autoConvertToEditable 方法 |

### 架构注意事项

harness 层（`deerflow.*`）不能直接导入 app 层（`app.*`）。同步方法在 `app.extensions.docmgr.service` 中，`present_files` 在 `deerflow.tools.builtins` 中。解决方案：

1. **回调注册** — 在 Gateway 启动时，将 `sync_outputs_to_docmgr` 注册到 deerflow 的回调注册表中
2. **中间件钩子** — 通过现有中间件链（如 `AfterToolMiddleware`）在 `present_files` 执行后触发同步
3. **事件总线** — present_files 发布事件，app 层订阅

推荐方案 1（回调注册），最简洁且与现有架构一致。

## 与现有功能的关系

- `syncThreadFiles` API（`POST /sync-thread-files`）保持不变，用于历史数据补录
- 新的自动同步通过 `present_files` 触发，两者共享去重逻辑
- 项目成员进入项目时的 `syncDocs` 继续工作（同步项目成员的线程文件）
- 文档空间的文件夹树（ProjectFolderTree）自动展示新同步的文件

## 不在范围内

- 实时推送通知（文件同步后不通过 WebSocket 通知前端）
- 文件版本管理（同一文件多次生成覆盖，不保留历史版本）
- 沙箱文件的删除同步（文档空间中删除不影响沙箱文件）
- 非文本文件的在线编辑
