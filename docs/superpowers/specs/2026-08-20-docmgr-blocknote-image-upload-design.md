# 文档空间「我的文档」BlockNote 编辑器 — 图片上传（线程目录存储）设计

- 日期：2026-08-20
- 状态：已与用户确认（方案 A：线程目录存储）
- 范围：个人文档编辑器 `PersonalBlockNoteEditor`；collab 编辑器不动

## 1. 背景与问题

BlockNote 0.51.4 支持三种"文件类"图片插入入口，全部依赖 `useCreateBlockNote` 的
`uploadFile` 选项；当前编辑器未传该选项（`PersonalBlockNoteEditor.tsx:353`），导致：

| 入口 | 现状 |
|---|---|
| 图片块面板"上传"标签 | 标签页不渲染（`editor.uploadFile === undefined` 时 react 包直接跳过该 tab） |
| 拖拽图片文件 | 静默无效（core 粘贴/拖拽统一守卫：`if (!uploadFile) { console.warn; return; }`） |
| 粘贴图片文件/截图 | 同上，同一处理函数 |

目前仅 URL 类插入可用（slash 菜单嵌入链接、富文本 `<img src=url>` 粘贴、
markdown `![](url)` 导入、程序化 insertBlocks）。

选定方案：**图片存入文档所在线程的 user-data 目录，复用现有 artifacts GET 端点渲染**
（零新增基础设施，与"个人文档=线程 outputs/ 直映射"架构同构）。

已否决的备选：

- **MinIO 独立 bucket**（仿 contract_price `cpa-contracts` 模式）——适用于跨文档图库/
  collab/分享场景，当前不需要；dev compose 无 MinIO 服务，引入即增加部署依赖。
- **base64 data-URL 内嵌**——截图 base64 直接写进 .md，污染 AI 助手/agent 沙箱读取、
  拖慢 1.5s debounce 的全文档序列化；且 uploadFile 接通后 Ctrl+V 体验完全一致。

## 2. 数据流

```
Ctrl+V / 拖拽 / 面板上传
  → BlockNote 建 image 占位块（自带 loading 态，onUploadStart/End 由 core 自动包装）
  → uploadFile(file) 前端回调
  → POST /api/extensions/docmgr/threads/{thread_id}/images   (cookie 认证, doc:upload 权限)
  → gateway 写文件: {base_dir}/users/{uid}/threads/{tid}/user-data/outputs/images/{uuid12}.{ext}
  → 返回 { url: "/api/threads/{tid}/artifacts/mnt/user-data/outputs/images/{uuid12}.{ext}" }
  → BlockNote 用 url 更新占位块 → markdown 落为 ![name](url) → 既有 1.5s 自动保存照旧
```

URL 为相对路径（同源，`<img>` 自动携带 cookie）；artifacts GET
（`backend/app/gateway/routers/artifacts.py:311`，`resolve_thread_virtual_path` 放行
整个 user-data 树）以 inline + 正确 mime 渲染图片。

## 3. 后端：一个新端点

位置：`backend/app/extensions/docmgr/routers.py`（纯 EAI 扩展代码，不改
harness/gateway 上游同步面）。

- `POST /api/extensions/docmgr/threads/{thread_id}/images`
  - 参数：`file: UploadFile`；`require_permission("doc:upload")`（与同 router 一致）
  - 目录解析复用 `_resolve_thread_sandbox_dir(paths, thread_id, fallback_user_id)`
    （routers.py:719，已处理 Gateway/extensions 用户桶 UUID 分裂）
  - 落盘：`<thread user-data>/outputs/images/{uuid4().hex[:12]}{原扩展名}`，目录不存在则建
  - 类型白名单：`image/png, image/jpeg, image/gif, image/webp, image/bmp`
    ——**不含 SVG**（artifacts 对 SVG 强制下载防 XSS，插了也渲染不出）
  - 大小上限：模块常量 10MB，超限 413
  - 响应：`{"url": "/api/threads/{tid}/artifacts/mnt/user-data/outputs/images/{name}"}`

## 4. 前端：接线

- `PersonalBlockNoteEditor.tsx`：新增可选 prop `threadId?: string`；有值时
  `useCreateBlockNote` 增加
  `uploadFile: async (file) => (await uploadDocImage(threadId, file)).url`。
  无 threadId 时行为不变（仅 URL 插入）。
- 新 API helper `uploadDocImage(threadId, file)`（fetch + FormData，~15 行，
  放 docmgr 既有 api 文件或就近新建）。
- `DocumentManagement.tsx` / `DocAIAgentPanel.tsx`：把已有 `source_thread_id`
  作为 `threadId` 传入编辑器。

## 5. 错误处理与边界

| 场景 | 行为 |
|---|---|
| 上传失败（网络/413/类型拒绝） | uploadFile 抛错 → 占位块留在原地带错误态可手删；toast 提示原因 |
| 并发多图粘贴 | BlockNote 逐文件调 uploadFile，无共享状态 |
| 非 image/* 文件拖入 | BlockNote 落成 `file` 块 → 同一 uploadFile 白名单拒绝 → 抛错占位，可接受 |
| 文件名冲突 | uuid12，实际不可能 |
| 删除单个文档 | images/ 可能留孤儿文件——接受；线程删除时目录整体清理 |

## 6. 已知限制（接受）

1. **分享文档**：被分享者打开时图片 URL 因 artifacts `owner_check` 403 看不到图；
   后续做"分享可见"时换 docmgr 代理端点。
1. **线程所有权校验沿用 router 既有模式**：与 `sync-thread-files`（routers.py:692）
   一致——`doc:upload` 权限门 + `_resolve_thread_sandbox_dir` 跨桶兜底扫描，不做
   per-thread 严格所有权断言（Gateway/extensions 用户 UUID 分裂所致）。跨租户加固
   属于整个 router 的存量课题，不随本设计单点引入或解决。
2. **Word 导出无图片处理**（存量缺口，非本设计引入；docmgr 导出代码 img 相关为零）。
   修复路径：导出器把 `/api/threads/...` URL 解析回线程本地路径直读文件——单独小迭代。
3. collab 项目文档编辑器无图片上传（范围外）。

## 7. 测试

- 后端 `backend/tests/test_docmgr_images.py`：
  上传→落盘→artifacts URL GET 200 且 content-type 正确；SVG 拒绝；超限 413；
  无 doc:upload 权限/未认证 401/403。
- 前端：`pnpm typecheck` + 既有 lint；不为 BlockNote 内部上传逻辑写组件测试。

## 8. 涉及文件

| 文件 | 改动 |
|---|---|
| `backend/app/extensions/docmgr/routers.py` | +1 端点（~50 行） |
| `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx` | +prop +uploadFile（~10 行） |
| docmgr 前端 api 文件 | +`uploadDocImage` helper（~15 行） |
| `frontend/src/extensions/docmgr/DocumentManagement.tsx`、`DocAIAgentPanel.tsx` | 各传 1 个 prop |
| `backend/tests/test_docmgr_images.py` | 新增 |
