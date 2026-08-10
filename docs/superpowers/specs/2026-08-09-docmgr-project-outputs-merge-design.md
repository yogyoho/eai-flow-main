# 文档空间「项目文件夹」合并设计 — 项目 outputs 跨用户共享

- 日期: 2026-08-09
- 状态: 设计已确认（待写实现计划）
- 作者: brainstorming 会话
- 相关: 上一轮 bug 定位（项目线程生成的 outputs 文件不出现在项目文件夹）

## 1. 背景与问题

项目负责人 lisi 在项目对话里让 AI 生成「消防设计专篇」，文件已落到 `outputs/`，但组员 zhangsan（以及 lisi 自己）在文档空间的「项目文件夹」里看不到该文件，也没有自动建出项目文件夹。

根因（上一轮已定位）：
- AI 生成的文件物理存在于 `users/{生成者}/threads/{线程}/outputs/`，按用户隔离。
- 「项目文件夹」靠 `AIDocument(project_id, file_ref_path)` 这个 DB 指针做跨用户共享，而该指针**只在 agent 调 `present_files` 工具时才创建**。报告类 skill 没调 `present_files`，所以指针记录为空。
- `get_project_files` 的另一条聚合路径只抓 `uploads/list`（用户上传），不抓 `outputs/`（agent 产物）。
- 因此 outputs/ 里的产物哪条路都没进项目文件夹。

## 2. 目标与非目标

### 目标
1. lisi 在项目对话生成的 outputs 文件，无需 agent 调任何工具即自动对项目成员可见。
2. 「项目文件夹」与「我的文档」统一为**两区文件系统视图**（个人区 / 项目区），都不复制文件。
3. 项目成员（zhangsan）可**编辑** lisi 生成的项目文档（顺序编辑，非实时协同）。
4. **不改动 harness 层代码**（`packages/harness/deerflow/`）。

### 非目标
- 实时协同编辑（Google Docs 式 OT/CRDT）—— 不做。
- 改 agent 写文件的物理位置 / harness 路径解析 —— 不做。
- 章节文档（`AIDocument.chapter_id` + content 报告组装产物）—— 正交系统，不碰。

## 3. 当前共享机制（重构前实况）

全部位于 app 层，零 harness 改动。

**物理形态**：每个成员进项目各开自己的对话线程。`enter_project`（`backend/app/extensions/project/service.py:371`）按 `(project_id, user_id)` 查 `ProjectMember` 行，谁进就给谁绑一个 `thread_id` —— lisi→T1，zhangsan→T2。AI 产物落在 `users/{生成者}/threads/{其线程}/outputs/`，**没有共享物理位置**。

**项目文件列表** `get_project_files`（`project/service.py:1200`）聚合两个来源：
1. 成员上传：遍历每个 member，调 `GET /api/threads/{m.thread_id}/uploads/list`（**是 uploads 不是 outputs**）。
2. 同步的 AIDocument：`project_id == 本项目 AND file_ref_path IS NOT NULL`。

**跨用户可见性**：`list_docs` / `get_by_id_scoped`（`docmgr/service.py:33,144`）谓词 `(user_id == caller) OR (project_id IN member_projects)` —— 成员能看到本项目所有 AIDocument，含别人生成的。

**编辑**：`write_personal_output`（`docmgr/service.py:633`）写回**调用者自己**的桶（`get_effective_user_id()`），不是 `file_ref_path`。跨用户编辑写回目前没接。

## 4. 关键决策与权衡

### 4.1 为什么不动 harness

最初考虑过「项目线程的 outputs 物理解析到项目共享目录」（需改 harness `ThreadDataMiddleware` / `LocalSandboxProvider` 路径解析）。该方案基于「可编辑 ⇒ 必须共享物理位置」假设 —— **该假设只对实时协同编辑成立**。

本场景是 lisi 生成 → zhangsan 审阅/批注的**顺序编辑**：文件物理留在 lisi 桶，zhangsan 经服务器写回原路径即可。读路径早就是服务器读任意桶，写路径对称扩展。**不需要共享物理位置，不需要动 harness。** 现有 app 层共享模型已覆盖 ~90%。

### 4.2 为什么弃用 AIDocument file_ref 指针、改纯文件系统聚合

「两区均文件系统视图」要求项目区像个人区一样直接读 outputs/，而非靠 DB 指针。直接聚合还**顺带根治 bug**：没有「入册」步骤，agent 写完盘上即有，下次列表即现，不再依赖 `present_files → AIDocument file_ref` 这条断链。

## 5. 设计

### §1 存储与可见性模型

**分流规则（按 thread 是否绑项目）**：
- 个人区「我的文档」= 我自己**未绑项目**的线程 outputs/。
- 项目区「项目/共享文档」= 该项目**所有成员线程**的 outputs/ 聚合。

**项目区聚合 `listProjectOutputs(project_id, caller_user_id)`（新，纯 app 层）**：
1. 校验 caller 是本项目 member（否则 403）。
2. 查 `project_members` → `[(user_id, thread_id), …]`。
3. 对每条，服务端读 `users/{user_id}/threads/{thread_id}/outputs/`（跨用户，服务器有全盘 FS 权限）。跳过无 `thread_id` 或目录不存在的成员。
4. 返回并集，每个文件标注**生成者**（来自哪个 member 桶）+ `thread_id` + `rel_path` + size/mime/modified_at。

**个人区过滤**：`listPersonalOutputs` 加排除 —— 跳过 `thread_id IN (SELECT thread_id FROM project_members)` 的线程，项目产物不回流个人区。

**写回**：编辑写回文件**原物理路径**，服务器调解，不复制。

**版本历史**：新增 `ProjectDocVersion` 表，键 `(project_id, thread_id, rel_path)`，镜像现有 `PersonalDocVersion`（thread_id 区分不同成员同名文件）。每文件留最新 20 条，可回滚。

**保留不动**：
- 个人区 `listPersonalOutputs` 机制（仅加排除项目线程过滤）。
- 章节文档（`AIDocument.chapter_id` + content）。
- AIDocument file_ref / Folder 树模型：对新 output 文件弃用；存量行留置不删（零危害）。

### §2 跨用户编辑语义

**读**：成员打开文件 → 服务器按 `(project_id, thread_id, rel_path)` 定位物理文件并读出（跨用户）。

**定位物理路径（避开双 user_id 坑）**：不按 `member.user_id` 定位（agent 运行时 user_id 可能 ≠ 项目 member user_id，文件可能在另一个桶）。而是**按 thread_id 扫描所有 user 桶**，找到真正含该 thread 目录的桶 —— 复用 `sync_project_thread_docs` 已有的 fallback 扫描模式（`project/service.py:460-469`）。写到同一物理路径。

**写回**：服务器写回原物理路径。路径穿越校验（`rel_path` resolve 后必须仍在 outputs/ 内）。

**版本快照**：每次保存写一条 `ProjectDocVersion(project_id, thread_id, rel_path, content, editor_user_id, label?)`，每文件留最新 20 条。

**并发**：顺序编辑，last-write-wins，**不做实时协同**。加轻量防覆盖：保存带客户端读到的 `mtime`，服务端比对当前文件 mtime，不一致 → 409「文件已被他人修改，请刷新」。

**权限**：本项目所有成员均可编辑。编辑者身份记入版本快照 `editor_user_id`。

**边界**：
- 非文本（二进制）文件 → 仅查看不编辑（沿用 `_is_text_mime` 判断）。
- 负责人删线程 → 文件对所有人消失（v1 已知限制，不特殊处理）。
- 列表后文件被删再编辑 → 404。

### §3 前端 IA 与组件改动

两区结构：
```
📄 我的文档                  📂 共享文档
(自己未绑项目的线程 outputs)   ├─ [项目选择器: test ▾]
├─ 📁 对话A                   │   ├─ 消防设计专篇.md   [lisi]
│   ├─ 草稿.md                │   ├─ 价格表.json       [lisi]
│   └─ 备忘.md                │   └─ 会议纪要.md       [zhangsan]
└─ ...                       └─ (我参与的其他项目…)
```

改动清单：

| 位置 | 改动 |
|------|------|
| `listPersonalOutputs`（后端） | 加过滤：排除绑定项目的线程 |
| 新增 `useProjectOutputs(pid)` + `docmgrApi.listProjectOutputs(pid)` | 调新聚合接口，返回带 member 归属的文件列表 |
| `DocumentManagement.tsx` 项目区 | 弃用 AIDocument folder-tree 视图（`ProjectFolderTree` / `ProjectDocListPanel`）；改文件系统视图列表（复用个人区 output 列表组件模式）+ 项目选择器 + 成员归属 badge |
| 编辑器 | 项目文件编辑走新写回端点，复用个人区编辑器 UI；保存带 mtime 乐观锁 |
| 版本历史 UI | 镜像个人区版本面板，查/回滚 `ProjectDocVersion` |
| `ShareDialog` | 弃用（整项目自动共享，不需手动分享） |

复用最大化：个人区 output 列表组件 + 编辑器 + 版本面板已存在，项目区基本是「换数据源 + 加归属 badge + 换写回端点」。

项目选择器：列出当前用户参与的所有项目（`project_members.user_id == me`），下拉切换。

### §4 迁移、边界与测试

**存量数据**：
- lisi 桶已有的消防设计专篇 → 实现后自动出现在项目区（实时扫盘，无需 backfill）。
- 现有 AIDocument file_ref 记录 → 留置不删。

**项目详情页「文件」tab 对齐**：`get_project_files`（`project/service.py:1200`）本次改为复用 `listProjectOutputs` 读 outputs/（替换原 uploads/list + AIDocument file_ref 双源聚合），保证项目详情页与文档空间项目区数据一致。

**测试（TDD 强制，`backend/tests/`）**：
- `listProjectOutputs` 聚合 + 跨用户可见性 + 非成员 403 + 跳过无 thread 成员。
- 写回路径解析（双 user_id 桶扫描）+ 路径穿越拒绝。
- mtime 乐观锁（过期 → 409）。
- `ProjectDocVersion` 快照 + 20 条上限 + 回滚。
- 个人区排除项目线程过滤。
- `get_project_files` 对齐后行为。

## 6. 文件级改动清单

### 后端
- `backend/app/extensions/models/__init__.py`：新增 `ProjectDocVersion` 模型。
- `backend/app/extensions/docmgr/service.py`：
  - 新增 `listProjectOutputs(db, project_id, caller_user_id)`。
  - 新增 `write_project_output(db, project_id, thread_id, rel_path, content, editor_user_id, if_mtime)` + 私有「按 thread_id 扫桶定位」helper。
  - 新增 `ProjectDocVersion` CRUD（create / list / get / restore），镜像 `PersonalDocVersion`。
  - `listPersonalOutputs`：加排除项目线程过滤。
- `backend/app/extensions/docmgr/routers.py`：
  - `GET /api/extensions/docmgr/projects/{pid}/outputs`
  - `PUT /api/extensions/docmgr/projects/{pid}/outputs`（body: thread_id, rel_path, content, if_mtime）
  - 版本端点（list / get / restore）。
- `backend/app/extensions/project/service.py`：`get_project_files` 复用 `listProjectOutputs`。

### 前端
- `frontend/src/extensions/docmgr/api.ts`：`listProjectOutputs` / `writeProjectOutput` / 版本 API。
- `frontend/src/extensions/docmgr/useProjectOutputs.ts`（新）：`useProjectOutputs(pid)` hook。
- `frontend/src/extensions/docmgr/DocumentManagement.tsx`：项目区改文件系统视图 + 项目选择器 + 归属 badge；弃用 folder-tree 与 `ShareDialog`。
- 复用个人区 output 列表 / 编辑器 / 版本面板组件。

## 7. 不做 / 后续

- 实时协同编辑（OT/CRDT）。
- agent 写文件物理位置 / harness 路径解析改动。
- 章节文档系统改造。
- 存量 AIDocument file_ref 记录清理。
- 负责人删线程的文件级联保护。
