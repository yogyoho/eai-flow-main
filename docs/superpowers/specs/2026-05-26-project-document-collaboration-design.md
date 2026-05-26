# 项目文档协作编辑系统设计

**日期**: 2026-05-26
**状态**: Draft
**范围**: 仅项目文件夹下的文档（`project_id IS NOT NULL`），其他文档区域（个人文件夹、收藏、共享）保持不变

## 1. 概述

为知识空间中**项目文件夹下的文档**添加实时协作编辑能力，包括：
- Notion 风格的 BlockNote 块编辑器
- 基于 Yjs + Hocuspocus 的实时协作
- 段落级评论线程（类似 Notion 内联评论）
- 完整版本历史与回滚
- AI 辅助写作（段落级 + 文档级审查）

**双编辑器路由**：
- 项目文件夹文档（`project_id IS NOT NULL`）→ BlockNote 协作编辑器
- 其他所有文档（个人文件夹、收藏、共享等）→ 现有 Tiptap 编辑器（保持不变）

## 2. 架构设计

### 2.1 运行时拓扑

```
Browser
  ├── /api/extensions/docmgr/*  ──→  Gateway FastAPI (port 8001)
  ├── /api/collab/*             ──→  Hocuspocus WebSocket Server (port 8002)
  │                                   ↕ 同源 Cookie JWT 认证
  └── /*                        ──→  Next.js Frontend (port 3000)
```

### 2.2 认证机制

协作服务（Hocuspocus）与现有系统保持一致的 **Cookie-based JWT + CSRF Double Submit Cookie** 模式：

- WebSocket 连接通过 HTTP Upgrade 握手携带 Cookie
- Hocuspocus `onConnect` 钩子从 Cookie 解析 JWT，验证用户身份
- CSRF 通过 Origin/Referer 头校验（WebSocket Upgrade 请求天然携带）
- 不需要单独的 JWT token 或 API key

### 2.3 组件关系

```
┌─────────────────────────────────────────────────┐
│  Frontend (Next.js :3000)                       │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │  CollabEditor (BlockNote)                │   │
│  │  ├── @blocknote/react                    │   │
│  │  ├── @blocknote/shadcn                   │   │
│  │  ├── yjs (Y.Doc)                         │   │
│  │  ├── @hocuspocus/provider (WebSocket)    │   │
│  │  └── CommentUI (自定义扩展)               │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │  TiptapEditor (不变)                     │   │
│  │  └── 仅用于非项目文档                     │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Backend                                        │
│                                                  │
│  ┌──────────────────────┐  ┌─────────────────┐ │
│  │  Gateway (:8001)     │  │  Hocuspocus     │ │
│  │  ├── docmgr routers  │  │  (:8002)        │ │
│  │  ├── version API     │  │  ├── onConnect   │ │
│  │  ├── comment API     │  │  │  (Cookie JWT) │ │
│  │  └── auth middleware  │  │  ├── onChange    │ │
│  │                      │  │  ├── onLoad       │ │
│  │                      │  │  └── onStore       │ │
│  │                      │  │                   │ │
│  │  PostgreSQL          │  │  Yjs Docs (PG)   │ │
│  └──────────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────┘
```

## 3. 数据模型

### 3.1 文档内容存储（Yjs 二进制）

Yjs 文档的增量更新存储在 PostgreSQL 中：

```sql
CREATE TABLE collab_documents (
    doc_id UUID PRIMARY KEY REFERENCES ai_documents(id),
    yjs_doc BYTEA NOT NULL,          -- Yjs encodeStateAsUpdate 的完整快照
    version INTEGER NOT NULL DEFAULT 1,
    last_editor_id UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE collab_updates (
    id BIGSERIAL PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES collab_documents(doc_id),
    update_data BYTEA NOT NULL,      -- 单次 Yjs update
    user_id UUID NOT NULL REFERENCES users(id),
    version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_collab_updates_doc_version ON collab_updates(doc_id, version);
```

### 3.2 版本历史

```sql
CREATE TABLE collab_versions (
    id BIGSERIAL PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES ai_documents(id),
    version INTEGER NOT NULL,
    snapshot BYTEA NOT NULL,           -- 该版本的完整 Yjs 快照
    summary TEXT,                      -- AI 生成的变更摘要
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(doc_id, version)
);
CREATE INDEX idx_collab_versions_doc ON collab_versions(doc_id, version DESC);
```

版本触发时机：
- **手动保存**: 用户点击"保存版本"按钮
- **定时快照**: 每 30 分钟自动保存一次（仅在有变更时）
- **编辑器关闭**: 用户离开文档时触发保存

### 3.3 段落级评论

```sql
CREATE TABLE collab_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID NOT NULL REFERENCES ai_documents(id),
    block_id VARCHAR(100) NOT NULL,      -- BlockNote block ID
    content TEXT NOT NULL,
    parent_id UUID REFERENCES collab_comments(id),  -- 线程回复
    user_id UUID NOT NULL REFERENCES users(id),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_collab_comments_doc_block ON collab_comments(doc_id, block_id);
CREATE INDEX idx_collab_comments_parent ON collab_comments(parent_id);
```

评论线程结构：
- 顶级评论绑定到 BlockNote block（通过 `block_id`）
- `parent_id` 为 NULL 表示线程起始评论
- `parent_id` 非 NULL 表示线程内的回复
- `resolved = true` 表示已解决的评论（UI 上折叠但仍可查看）

## 4. 功能设计

### 4.1 实时协作编辑

**编辑器选择**: BlockNote (`@blocknote/react` + `@blocknote/shadcn`)

BlockNote 是基于 Tiptap/ProseMirror 构建的 Notion 风格块编辑器，原生支持：
- 块级拖拽重排
- `/` 斜杠命令
- 多列布局
- 嵌套块
- Yjs 实时协作

**协作接入**:
- 前端使用 `@hocuspocus/provider` 的 `WebsocketProvider` 连接 Hocuspocus 服务
- BlockNote 通过 `useCreateBlockNote({ collaboration: { ... } })` 接入 Yjs
- 每个 `Y.Doc` 以文档 ID 为唯一标识

**在线状态**:
- 显示当前正在编辑的用户头像列表（叠加在文档顶部）
- 光标位置同步（BlockNote 原生支持 Awareness 协议）
- 用户颜色自动分配

### 4.2 段落级评论线程

**交互设计**（类似 Notion）：
1. 用户选中一个段落后，段落右侧出现评论图标
2. 点击图标展开侧边评论面板
3. 评论内嵌在文档流中（浮动在段落右侧），不遮挡内容
4. 支持多轮回复形成评论线程
5. 评论可以标记为"已解决"，解决后折叠但仍可查看
6. 点击已解决的评论可重新打开

**技术实现**：
- BlockNote 的 `block_id` 作为评论锚点
- 评论数据存储在 PostgreSQL（不存储在 Yjs 文档中，保持文档内容纯净）
- 评论通过 REST API 加载，通过 WebSocket 广播新评论通知
- 使用 BlockNote 的自定义 Side Menu 扩展渲染评论入口

### 4.3 版本历史

**版本列表 UI**：
- 右侧面板显示版本时间线（类似 Google Docs）
- 每个版本显示：版本号、时间、操作者、AI 生成摘要
- 点击版本可预览该版本的文档内容（只读模式）

**差异对比**：
- 选择任意两个版本进行差异对比
- 新增内容绿色高亮，删除内容红色删除线
- 基于 Yjs 快照的二进制差异转换为块级差异

**回滚操作**：
- "恢复到此版本" 将当前文档内容替换为历史版本
- 回滚操作本身也会创建一个新版本（可追溯）

### 4.4 AI 辅助写作

**段落级 AI**（已有基础，扩展到 BlockNote）：
- 选中块 → 右键菜单 → 润色/扩写/精简/头脑风暴
- AI 结果以预览模式展示，用户确认后替换原内容
- 复用现有 `/documents/ai-edit` 端点

**文档级 AI 审查**（新增）：
- "AI 审查" 按钮触发全文档审查
- 检查：逻辑一致性、语言风格统一性、缺失章节、数据准确性
- 审查结果以评论线程形式插入到对应段落
- 用户可以逐条接受或忽略建议

**AI 评论生成**：
- 版本保存时可选生成 AI 变更摘要
- 对比前后版本差异，用 AI 生成自然语言摘要

## 5. API 设计

### 5.1 协作 WebSocket 端点

```
WebSocket ws://host:2026/api/collab
```

Hocuspocus 原生协议，路径映射到文档 ID。

### 5.2 版本 API（Gateway 新增路由）

```
GET    /api/extensions/docmgr/documents/{doc_id}/versions          -- 列出版本
POST   /api/extensions/docmgr/documents/{doc_id}/versions          -- 创建版本
GET    /api/extensions/docmgr/documents/{doc_id}/versions/{ver}    -- 获取特定版本
POST   /api/extensions/docmgr/documents/{doc_id}/versions/{ver}/restore -- 回滚
GET    /api/extensions/docmgr/documents/{doc_id}/versions/diff?from=1&to=3 -- 差异对比
```

### 5.3 评论 API（Gateway 新增路由）

```
GET    /api/extensions/docmgr/documents/{doc_id}/comments          -- 列出评论
POST   /api/extensions/docmgr/documents/{doc_id}/comments          -- 创建评论
PUT    /api/extensions/docmgr/comments/{comment_id}                -- 更新评论
DELETE /api/extensions/docmgr/comments/{comment_id}                -- 删除评论
POST   /api/extensions/docmgr/comments/{comment_id}/resolve        -- 解决评论
POST   /api/extensions/docmgr/comments/{comment_id}/reopen         -- 重新打开评论
```

所有端点使用现有 `get_current_user` 依赖（Cookie JWT），并验证用户是文档所属项目的成员。

## 6. 前端组件设计

### 6.1 组件树

```
DocumentManagement
  ├── SidebarNav (不变)
  ├── DocumentGrid
  │   ├── DocCard (不变)
  │   └── ...
  └── DocumentEditorPanel
        ├── if (doc.project_id)
        │     → CollabEditor
        │         ├── BlockNoteEditor
        │         ├── OnlineUsers
        │         ├── CommentSidebar
        │         ├── VersionPanel
        │         └── AIToolbar
        └── else
              → TiptapEditor (不变)
```

### 6.2 新增文件

```
src/extensions/collab/
  ├── CollabEditor.tsx           -- 协作编辑器主组件
  ├── BlockNoteEditor.tsx        -- BlockNote 编辑器封装
  ├── OnlineUsers.tsx            -- 在线用户头像列表
  ├── CommentSidebar.tsx         -- 评论侧边栏
  ├── CommentThread.tsx          -- 评论线程组件
  ├── VersionPanel.tsx           -- 版本历史面板
  ├── DiffViewer.tsx             -- 差异对比视图
  ├── AIToolbar.tsx              -- AI 辅助工具栏
  ├── useCollab.ts               -- WebSocket 连接 hook
  ├── useComments.ts             -- 评论数据 hook
  └── useVersions.ts             -- 版本数据 hook
```

## 7. Hocuspocus 服务设计

### 7.1 部署方式

Hocuspocus 作为独立 Node.js 进程运行：
- Docker 容器内与 Gateway 并行运行
- 端口 8002，nginx 代理 `/api/collab` → `:8002`
- 与 Gateway 共享 PostgreSQL 数据库

### 7.2 认证流程

```
1. 浏览器发起 WebSocket 连接: ws://host:2026/api/collab
2. HTTP Upgrade 请求携带 Cookie (含 JWT)
3. Nginx 转发到 Hocuspocus (:8002)
4. Hocuspocus onConnect 钩子:
   a. 从 Cookie 解析 JWT (复用 Gateway 的 JWT 密钥)
   b. 验证用户身份
   c. 查询 ProjectMember 表确认用户有权限访问该文档所属项目
   d. 返回允许/拒绝
```

### 7.3 数据持久化

Hocuspocus `onStore` 钩子：
- 定期将 Yjs 文档状态写入 `collab_documents` 表
- 每次变更记录到 `collab_updates` 表
- 定时快照触发版本保存到 `collab_versions` 表

## 8. Docker 部署

### 8.1 新增服务

在 `docker-compose-dev.yaml` 中新增：

```yaml
collab:
  build:
    context: ../backend
    dockerfile: Dockerfile.collab
  ports:
    - "8002:8002"
  environment:
    - DATABASE_URL=postgresql://...
    - JWT_SECRET=${JWT_SECRET}
  depends_on:
    - db
```

### 8.2 Nginx 配置更新

```nginx
location /api/collab {
    proxy_pass http://collab:8002;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Cookie $http_cookie;
    proxy_set_header Host $host;
}
```

## 9. 范围约束

**变更范围**（仅项目文件夹文档）：
- ✅ 项目文件夹文档使用 BlockNote 协作编辑器
- ✅ 实时多人协作编辑
- ✅ 段落级评论线程
- ✅ 版本历史与回滚
- ✅ AI 辅助写作

**不变范围**：
- ❌ 个人文件夹文档 → 保持现有 Tiptap 编辑器
- ❌ 收藏文档 → 保持不变
- ❌ 共享文档 → 保持不变
- ❌ 文档列表 UI → 保持不变
- ❌ 文件夹导航 → 保持不变
- ❌ 现有认证流程 → Cookie JWT 不变，协作服务复用同一机制

## 10. 技术选型总结

| 组件 | 选型 | 理由 |
|------|------|------|
| 编辑器 | BlockNote (@blocknote/react) | Notion 风格块编辑器，原生 Yjs 协作支持 |
| 实时协作 | Yjs + Hocuspocus | 成熟的 CRDT 方案，WebSocket 服务端 |
| 认证 | Cookie-based JWT + CSRF | 与现有 Gateway 保持一致 |
| 评论存储 | PostgreSQL | 结构化查询，与用户/文档关联 |
| 版本存储 | PostgreSQL (BYTEA) | Yjs 二进制快照，可靠持久化 |
| 前端状态 | TanStack Query + Yjs | 服务端数据用 Query，协作状态用 Yjs |
