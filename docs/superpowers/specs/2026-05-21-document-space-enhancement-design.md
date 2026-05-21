# Document Space Enhancement Design

**Date**: 2026-05-21
**Status**: Draft
**Scope**: Integrate sandbox files into document space with folder management, editing, preview, and sharing

## Problem

对话页面中 AI agent 在 `/mnt/user-data/` 下生成的文件（代码、文档、数据等）目前只能通过 artifact 面板查看，无法统一管理和编辑。用户需要：
- 按线程自动归档生成的文件
- 在文档空间中浏览、编辑、预览这些文件
- 将 AI 生成的文件整理到自己的文档中
- 分享文档给其他用户或部门

## Design Decisions

### Approach: Extend AIDocument Model

在现有 `ai_documents` 表增加字段区分"文档"和"沙箱文件引用"，复用现有文档空间的全部 UI（编辑器、搜索、文件夹、AI 操作）。

**Why not a separate model**: 新建 `sandbox_files` 表需要独立的 CRUD、前端视图、API，工作量大且用户看到两个分离的列表。扩展现有模型改动最小、体验最统一。

**Why not pure virtual mapping**: 没有数据库支持则无法做搜索、元数据、AI 编辑，文件夹无法手动整理。

## Data Model

### ai_documents Table Additions

| Field | Type | Description |
|-------|------|-------------|
| `doc_type` | `str, default="document"` | `"document"` (manual save) or `"file_ref"` (sandbox file reference) |
| `file_ref_path` | `str, nullable` | Physical path of sandbox file (only for file_ref) |
| `file_size` | `int, nullable` | File size in bytes |
| `file_mime` | `str, nullable` | MIME type |

Existing documents are unaffected — `doc_type` defaults to `"document"`.

### New document_shares Table

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `document_id` | UUID | Foreign key to ai_documents |
| `share_type` | str | `"user"` / `"department"` / `"link"` |
| `share_target_id` | str, nullable | User ID or department ID (null for link type) |
| `share_token` | str, nullable | Unique token for link sharing |
| `permission` | str | `"read"` / `"edit"` |
| `created_by` | UUID | Share initiator |
| `created_at` | datetime | Share timestamp |

## Backend API

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/extensions/docmgr/sync-thread-files` | Sync sandbox files for a thread into document space |
| PUT | `/api/extensions/docmgr/documents/{id}/move` | Move document to a different folder |
| PUT | `/api/extensions/docmgr/documents/{id}/rename` | Rename document (updates physical file for file_ref) |
| DELETE | `/api/extensions/docmgr/documents/batch` | Batch delete documents (max 50) |
| GET | `/api/extensions/docmgr/documents/{id}/preview` | Read file content for preview/editing |
| POST | `/api/extensions/docmgr/documents/{id}/share` | Share document to user/department/link |
| GET | `/api/extensions/docmgr/documents/{id}/shares` | List share records for a document |
| DELETE | `/api/extensions/docmgr/shares/{id}` | Revoke a share |
| GET | `/api/extensions/docmgr/shared-with-me` | Documents shared with current user |
| GET | `/doc/shared/{token}` | Access shared document via link token |

### Sync Logic

1. Accept `thread_id` as input
2. Read sandbox directory for that thread
3. For each file, create `doc_type="file_ref"` record:
   - `folder` = thread title (fallback: first 8 chars of thread_id)
   - Deduplicate by `file_ref_path` + `source_thread_id`
4. Skip files > 100 per sync (paginate remainder)
5. Return count of newly synced files

### Move to "My Documents"

When a file_ref document is moved to "My Documents":
- `doc_type` changes from `"file_ref"` to `"document"`
- File content is read from physical path and stored in `content` field
- For binary files (images, PDFs): `content` stores JSON metadata `{"type": "image", "file_ref_path": "..."}`
- `file_ref_path`, `file_size`, `file_mime` are preserved for reference

## Frontend

### Sidebar Menu Structure

```
我的文件夹
  ├── 我的文档        doc_type=document，手动保存或从AI存档移入
  ├── 我的收藏        is_starred=true，跨所有类型
  └── 我的分享        分享出去 + 分享给我的文档

AI任务存档
  ├── 数据分析任务     doc_type=file_ref，按线程自动分组
  ├── 代码重构项目
  └── ...
```

- "我的文档": filter `doc_type=document`, ordered by `updated_at` desc
- "我的收藏": filter `is_starred=true` across all doc types
- "我的分享": documents where user is sharer or sharee
- "AI任务存档": filter `doc_type=file_ref`, grouped by folder (thread name)

### File Card Display

| doc_type + file type | Card style | Click action |
|---------------------|------------|--------------|
| document | Current style | Open TipTap editor |
| file_ref + text (md/txt/html/rst) | File icon + name + size | Open TipTap editor (content from file) |
| file_ref + image (png/jpg/svg) | Thumbnail preview | Image preview modal |
| file_ref + other | File icon + name + size | Download file |

### Batch Operations

- Checkbox appears on card top-left in multi-select mode
- Floating toolbar: Move to folder | Delete | Star
- "Move to folder" opens folder picker with "new folder" option
- "Move to My Documents" available for file_ref items (changes doc_type)

### Artifact Panel Sync Button

- New "Sync to Document Space" button in artifact panel
- Calls sync API, shows "Synced N files → [View]" toast
- "View" link navigates to document space with corresponding folder open

### Share Dialog

- Triggered from document card context menu → "Share"
- Two tabs: "Share to user/department" and "Share via link"
- User/department tab: search and select users/departments, set permission (read/edit)
- Link tab: generates link with one click, copy button
- "Manage shares" view: list all shares with revoke/permission change options

### Shared Document View

- Route: `/doc/shared/{token}` for link sharing
- Access control: validate share record exists and user has permission
- Read: view-only mode in TipTap editor
- Edit: full edit mode in TipTap editor

## Edge Cases and Error Handling

### File Sync

- **Agent deleted file**: detect on sync, mark status as `"file_missing"`, show grayed card with "file lost" message
- **Large number of files**: cap at 100 per sync, prompt for pagination
- **Duplicate sync**: deduplicate by `file_ref_path` + `source_thread_id`
- **Large files**: >10MB not editable, download only

### Cross-Zone Move

- **File not found**: warn user, keep original state
- **Binary file move**: store JSON metadata in `content`, display as preview mode

### Sharing

- **Document deleted**: API returns 404, show "document deleted by owner"
- **Link expiry**: no auto-expiry, links valid until manually revoked
- **Permission changes**: real-time, validated on each access

### Performance

- Folder list cache per user (5 min TTL)
- File preview loaded on demand, not batch
- Batch delete in transaction, max 50 per request

## Migration

1. Add new columns to `ai_documents` table (all nullable, backward compatible)
2. Create `document_shares` table
3. Update existing `list_folders()` to work with both doc types
4. No data migration needed — existing documents keep `doc_type=document` default
