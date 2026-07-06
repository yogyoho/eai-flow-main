# 文档空间-我的文档：直接映射线程 outputs/ 目录

- **日期**: 2026-07-06
- **状态**: 设计中

## 1. 目标

将"文档空间 → 我的文档"从当前的间接同步路径（outputs → sync_thread_files → AIDocument → Folder → 前端树），改为**直接读取线程 outputs/ 文件系统**，消除中间层。项目文件夹部分保持不变。

## 2. 现状问题

| 问题 | 说明 |
|---|---|
| 5层间接 | outputs → sync → AIDocument → Folder → 前端树 |
| 同步时机不可靠 | 前端在 run 结束前触发 sync_thread_files（文件可能还没写） |
| 污染 | sync_thread_files 扫整个 user-data（outputs + uploads + workspace），非 outputs 文件误入文档空间 |
| folder 命名 | 依赖 _get_thread_title，线程无标题时 fallback thread_id[:8]（无意义字符串） |
| 双 auth | sync 用 extensions user_id，文件 owner 是核心 auth user_id，需 _resolve_thread_sandbox_dir 扫描 fallback |

## 3. 设计方案

### 3.1 架构概览

```
Agent write_file → /outputs/xxx.md
                         │
                         ▼
GET /docmgr/personal-outputs → 后端扫描 users/{uid}/threads/*/outputs/
       │                                │
       │                           ┌────┴────┐
       │                           │ threads_meta.display_name
       │                           │ personal_doc_meta (star/share)
       │                           └─────────┘
       ▼
返回 [{thread_id, display_name, files: [{rel_path, starred, shared}]}]

前端："我的文档"
  ├─ 煤矿运输顺槽掘进规程 (display_name)
  │   ├─ 新安煤矿...规程.md ⭐
  │   └─ 附图.pdf
  └─ 仓库项目消防设计 (display_name)
      ├─ 仓库项目消防设计专篇.md
      └─ 合规检查报告.md
```

### 3.2 新 API

**`GET /api/extensions/docmgr/personal-outputs`**

- 认证: `current_user`（JWT cookie）
- 逻辑:
  1. 扫 `users/{user_id}/threads/*/outputs/` 下所有文件
  2. 从 `threads_meta(display_name)` 拿线程标题（null 则 fallback 首个 .md 文件名）
  3. 从 `personal_doc_meta` 拿 star/share 状态
  4. 按 `thread_id` 聚合返回
- 无分页（个人线程数有限）

响应:
```json
{
  "threads": [{
    "thread_id": "26730232-...",
    "display_name": "基地项目消防设计专篇",
    "files": [{
      "name": "基地项目消防设计专篇.md",
      "rel_path": "基地项目消防设计专篇.md",
      "size": 19853,
      "mime": "text/markdown",
      "modified_at": "2026-07-06T12:41:54",
      "starred": false,
      "shared": false
    }]
  }]
}
```

### 3.3 新表 personal_doc_meta

```sql
CREATE TABLE personal_doc_meta (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id),
  thread_id  VARCHAR(100) NOT NULL,
  rel_path   VARCHAR(500) NOT NULL,
  is_starred BOOLEAN NOT NULL DEFAULT false,
  is_shared  BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, thread_id, rel_path)
);
```

- 收藏/分享切换：upsert（INSERT ON CONFLICT UPDATE）
- 只有文件被 star/share 时才写入（不预创建）

### 3.4 收藏/分享 API

| 方法 | 路径 | 说明 |
|---|---|---|
| PUT | `/docmgr/personal-docs/{thread_id}/star` | body: `{rel_path, starred: bool}` |
| PUT | `/docmgr/personal-docs/{thread_id}/share` | body: `{rel_path, shared: bool}` |
| GET | `/docmgr/personal-docs/starred` | 返回所有收藏文件列表 |

### 3.5 前端变化

| 组件 | 变化 |
|---|---|
| `useFolderTree("personal")` | 替换为 `usePersonalOutputs()` 调新 API |
| `syncThreadFiles()` | 个人 scope 停用（项目 scope 保留） |
| 收藏/全/分享 tab | 保留，filter 逻辑改为按 API 返回的 starred/shared 字段过滤 |
| 新建文档/子文件夹 | 删掉（"我的文档"不再支持手动创建——由线程自动生成） |

### 3.6 边界处理

1. **线程无标题**: fallback 用首个 .md 文件名（去扩展名）
2. **outputs 为空**: API 返回 `files: []`，前端不渲染该线程
3. **线程已删除但 outputs 残留**: 物理目录存在则返回
4. **outputs 子目录**: 拍平显示子目录路径（如 `images/图.png`）
5. **文件被覆盖**: 收藏状态保留（按 path 关联，不按内容）
6. **文件被删除**: meta 保留但不在 API 返回中（孤儿），后续可清理
7. **性能**: 个人线程 < 100，filesystem 扫描足够；以后可加 mtime 缓存

### 3.7 改造清单

| 文件 | 改动 |
|---|---|
| `backend/app/extensions/docmgr/routers.py` | 新增 `GET /personal-outputs` + star/share 路由 |
| `backend/app/extensions/docmgr/schemas.py` | 新增 `PersonalOutputsResponse` 等 schema |
| `backend/app/extensions/docmgr/service.py` | 新增 `list_personal_outputs()` 方法；sync_thread_files 个人 scope 停用或加 early return |
| `backend/app/extensions/models/__init__.py` | 新增 `PersonalDocMeta` SQLAlchemy model |
| `frontend/src/extensions/docmgr/useFolderTree.ts` | 新增 `usePersonalOutputs()` hook |
| `frontend/src/extensions/docmgr/DocumentManagement.tsx` | 我的文档改用新 hook；移除手动创建入口 |
| `frontend/src/extensions/api/docmgr.ts` | 新增 API 调用（personal-outputs, star, share） |
| `frontend/src/extensions/docmgr/useDocuments.ts` | 移除个人 scope 的 `syncThreadFiles` 调用 |

### 3.8 不变部分

- 项目文件夹（`project_scope=project`）：代码、API、数据完全不动
- 文档阅读器/编辑器：通过现有 artifacts API 读文件，不变
- 导出/下载/分享原逻辑：可复用

### 3.9 迁移

- **旧个人 AIDocument/Folder 记录**: 保留不动，前端切新 API 后自然不可见
- **孤儿 meta（文件已删但 meta 留存）**: 后续跑 `cleanup_orphan_meta` 脚本清理
- **旧收藏数据**: 可从 `AIDocument.is_starred` 迁移到 `personal_doc_meta`（可选脚本）
