# 个人文档 BlockNote 图片上传（线程目录存储）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给个人文档 BlockNote 编辑器接通 `uploadFile`，激活面板上传/拖拽/粘贴截图三个图片入口，图片落盘线程 `outputs/images/` 并经 artifacts 端点渲染。

**Architecture:** 后端在 docmgr router 新增 1 个 POST 端点（写文件进线程 user-data 目录，返回相对 artifacts URL）；前端给 `PersonalBlockNoteEditor` 加可选 `threadId` prop 并传 `uploadFile`。零新增基础设施，不改 harness/gateway。

**Tech Stack:** FastAPI（docmgr router，已有 `require_permission`/`_resolve_thread_sandbox_dir`）、BlockNote 0.51.4 `uploadFile` 选项、pytest、React/TS。

**Spec:** `docs/superpowers/specs/2026-08-20-docmgr-blocknote-image-upload-design.md`

**注意事项（全任务通用）:**
- 开发环境全在 Docker（`docker compose -p eai-docker`），后端改动后 `docker compose -p eai-docker restart gateway`；前端源码 bind-mount，HMR 失效则重启 frontend 容器。
- 所有提交走 `main-dev-fork` 分支，用 pathspec 只提交本任务文件（工作区有其他会话的未提交改动）。
- 后端异步端点内的文件 IO 必须经 `asyncio.to_thread`（blocking-io 检测 + `tests/blocking_io/` 运行门会抓）。
- 对上游代码的修改须加 EAI-CUSTOM 注释——本计划只改 EAI 扩展文件（docmgr），无上游面。

---

### Task 1: 后端上传端点（TDD）

**Files:**
- Create: `backend/tests/test_docmgr_images.py`
- Modify: `backend/app/extensions/docmgr/routers.py`（顶部 import 区 + `sync-thread-files` 端点之后，~line 717 后）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_docmgr_images.py`：

```python
"""Tests for personal-doc image upload endpoint (BlockNote uploadFile backend, EAI-CUSTOM)."""

import io
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

import app.extensions.docmgr.routers as docmgr_routers
from app.extensions.docmgr.routers import router


class _FakeUser:
    id = uuid4()


def _routes():
    return {(r.path, m) for r in router.routes for m in (getattr(r, "methods", None) or set())}


def _upload(data: bytes, filename: str, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _patch_fs(monkeypatch, tmp_path):
    """把线程目录解析与 Paths() 都指到 tmp_path，端点不碰真实文件系统。"""
    user_data = tmp_path / "user-data"
    monkeypatch.setattr(docmgr_routers, "Paths", lambda: None)
    monkeypatch.setattr(
        docmgr_routers,
        "_resolve_thread_sandbox_dir",
        lambda paths, tid, uid: user_data,
    )
    return user_data


def test_image_route_registered():
    """路由必须注册，否则前端 404。"""
    assert ("/api/extensions/docmgr/threads/{thread_id}/images", "POST") in _routes()


def test_image_route_gated_by_doc_upload():
    """端点必须挂 doc:upload 权限门（require_permission 闭包首个 cell 是权限名）。"""
    route = next(
        r
        for r in router.routes
        if getattr(r, "path", "") == "/api/extensions/docmgr/threads/{thread_id}/images"
    )
    perms = [
        dep.dependency.__closure__[0].cell_contents
        for dep in route.dependant.dependencies
        if getattr(dep.dependency, "__closure__", None)
    ]
    assert "doc:upload" in perms


@pytest.mark.asyncio
async def test_upload_image_writes_file_and_returns_url(tmp_path, monkeypatch):
    user_data = _patch_fs(monkeypatch, tmp_path)
    resp = await docmgr_routers.upload_thread_image("tid-1", _upload(b"\x89PNG-fake", "shot.png", "image/png"), current_user=_FakeUser())
    name = resp.url.rsplit("/", 1)[-1]
    f = user_data / "outputs" / "images" / name
    assert f.read_bytes() == b"\x89PNG-fake"
    assert name.endswith(".png") and len(name) == 16  # 12 hex + ".png"
    assert resp.url == f"/api/threads/tid-1/artifacts/mnt/user-data/outputs/images/{name}"


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_type(tmp_path, monkeypatch):
    _patch_fs(monkeypatch, tmp_path)  # SVG 走白名单拒绝，不应写任何文件
    with pytest.raises(HTTPException) as ei:
        await docmgr_routers.upload_thread_image(
            "tid-1", _upload(b"<svg/>", "evil.svg", "image/svg+xml"), current_user=_FakeUser()
        )
    assert ei.value.status_code == 415
    assert not (tmp_path / "user-data" / "outputs").exists()


@pytest.mark.asyncio
async def test_upload_rejects_oversize(tmp_path, monkeypatch):
    _patch_fs(monkeypatch, tmp_path)
    big = b"x" * (docmgr_routers._IMAGE_MAX_BYTES + 1)
    with pytest.raises(HTTPException) as ei:
        await docmgr_routers.upload_thread_image("tid-1", _upload(big, "big.png", "image/png"), current_user=_FakeUser())
    assert ei.value.status_code == 413
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_images.py -v
```
Expected: FAIL/ERROR — `AttributeError: module ... has no attribute 'upload_thread_image'` / `_IMAGE_MAX_BYTES`（import/属性错误即预期的红灯；路由注册测试同样失败）。

- [ ] **Step 3: 实现端点**

`backend/app/extensions/docmgr/routers.py` 三处改动：

3a. 顶部 import 区（line 7 附近）把 `from uuid import UUID` 改为：

```python
from uuid import UUID, uuid4
```

并在 `from app.extensions.database import get_db` 之后加一行：

```python
from deerflow.config.paths import Paths
```

（`asyncio`、`File`、`UploadFile`、`status`、`HTTPException`、`BaseModel` 已在现有 import 中。）

3b. `router = APIRouter(...)`（line 47）之后加常量与响应模型：

```python
# EAI-CUSTOM: BlockNote uploadFile 图片上传——白名单/大小上限（SVG 因 artifacts 强制下载防 XSS 而排除）
_IMAGE_MAX_BYTES = 10 * 1024 * 1024
_IMAGE_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


class ThreadImageResponse(BaseModel):
    url: str
```

3c. `sync_thread_files` 端点（line 716 `return result` 之后、`_resolve_thread_sandbox_dir` 定义之前）插入：

```python
# EAI-CUSTOM: 个人文档 BlockNote 编辑器图片上传（uploadFile 后端）。
# 图片落盘线程 user-data/outputs/images/，前端拿 artifacts 相对 URL 渲染。
@router.post("/threads/{thread_id}/images", response_model=ThreadImageResponse)
async def upload_thread_image(
    thread_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("doc:upload")),  # EAI-CUSTOM: Add permission check
):
    """Upload an image into the thread's outputs/images/ dir; return an artifacts URL."""
    ext = _IMAGE_MIME_EXT.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"不支持的图片类型: {file.content_type}")
    data = await file.read()
    if len(data) > _IMAGE_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="图片超过 10MB 上限")

    user_data_dir = _resolve_thread_sandbox_dir(Paths(), thread_id, str(current_user.id))
    name = uuid4().hex[:12] + ext
    target = user_data_dir / "outputs" / "images" / name

    def _write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    await asyncio.to_thread(_write)
    return ThreadImageResponse(url=f"/api/threads/{thread_id}/artifacts/mnt/user-data/outputs/images/{name}")
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_docmgr_images.py -v
```
Expected: 5 passed。

- [ ] **Step 5: lint**

```bash
cd backend && make lint
```
Expected: 无错误（ruff line length 240，双引号，新代码已按此写）。

- [ ] **Step 6: Commit**

```bash
cd .. && git add backend/tests/test_docmgr_images.py backend/app/extensions/docmgr/routers.py && git commit -m "feat(docmgr): 个人文档图片上传端点——线程outputs/images落盘+artifacts URL返回(SVG拒绝/10MB上限/doc:upload权限门)" -- backend/tests/test_docmgr_images.py backend/app/extensions/docmgr/routers.py
```

---

### Task 2: 前端 uploadFile 接线

**Files:**
- Create: `frontend/src/extensions/docmgr/utils/docImage.ts`
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx:289-299`（props）、`:353-357`（useCreateBlockNote）、`:58` 附近（import）
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx:2763-2772`（渲染点传 prop）

- [ ] **Step 1: 写 API helper**

创建 `frontend/src/extensions/docmgr/utils/docImage.ts`：

```ts
// EAI-CUSTOM: 上传图片到个人文档线程目录（BlockNote uploadFile 的网络层）。
/** 上传图片，返回可直接用于 <img> / markdown 的同源相对 URL。失败抛 Error(detail)。 */
export async function uploadDocImage(
  threadId: string,
  file: File,
): Promise<{ url: string }> {
  const token = /(?:^|;\s*)csrf_token=([^;]+)/.exec(document.cookie)?.[1] ?? "";
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(
    `/api/extensions/docmgr/threads/${encodeURIComponent(threadId)}/images`,
    {
      method: "POST",
      body: form,
      credentials: "include",
      headers: token ? { "X-CSRF-Token": token } : undefined,
    },
  );
  if (!resp.ok) {
    let detail = `图片上传失败 (${resp.status})`;
    try {
      const body: unknown = await resp.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      )
        detail = (body as { detail: string }).detail;
    } catch {
      /* 非 JSON 响应，用默认文案 */
    }
    throw new Error(detail);
  }
  return (await resp.json()) as { url: string };
}
```

（不设 Content-Type——浏览器需要自设 multipart boundary，同 `ExportDocxDialog.tsx:490` 既有模式。）

- [ ] **Step 2: 编辑器加 prop + uploadFile**

`PersonalBlockNoteEditor.tsx`：

2a. `import { replaceTextInContent } from "./utils/docEditorUtils";` 附近加：

```ts
import { uploadDocImage } from "./utils/docImage";
```

2b. props 接口（line 289-294）加一个字段：

```ts
interface PersonalBlockNoteEditorProps {
  initialContent: string;
  onChange: (markdown: string) => void;
  className?: string;
  hideSideMenu?: boolean;
  /** 文档所属线程 id；传入后激活图片上传（面板/拖拽/粘贴截图）。 */
  threadId?: string;
}
```

2c. 组件解构（line 299）与 `useCreateBlockNote`（line 353-357）改为：

```ts
>(({ initialContent, onChange, className, hideSideMenu, threadId }, ref) => {
```

```ts
  const editor = useCreateBlockNote({
    schema,
    dictionary,
    // EAI-CUSTOM: uploadFile 激活图片三入口（面板上传tab/拖拽/粘贴文件）。
    // 编辑器按文档 remount（key={editorKey}），threadId 在实例生命周期内稳定。
    ...(threadId
      ? {
          uploadFile: async (file: File) => {
            const { url } = await uploadDocImage(threadId, file);
            return url;
          },
        }
      : {}),
    extensions: [AIExtension({ transport: aiTransport }), highlightExtension],
  });
```

- [ ] **Step 3: 渲染点传 threadId**

`DocumentManagement.tsx:2763-2772` 的 `<PersonalBlockNoteEditor ...>` 加一行 prop：

```tsx
              <PersonalBlockNoteEditor
                key={editorKey}
                ref={editorRef as React.Ref<PersonalBlockNoteEditorRef>}
                initialContent={doc.content ?? ""}
                onChange={scheduleSave}
                className="flex-1"
                threadId={doc.source_thread_id ?? undefined}
                hideSideMenu={
                  !!getLanguageFromName(personalFile?.title ?? doc?.title ?? "")
                }
              />
```

- [ ] **Step 4: 类型检查 + lint**

```bash
cd frontend && pnpm check
```
Expected: 0 error（若报既有历史错误，确认新增文件无错即可——typecheck 基线见 memory，以"不新增错误"为准）。

- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/extensions/docmgr/utils/docImage.ts frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx frontend/src/extensions/docmgr/DocumentManagement.tsx && git commit -m "feat(docmgr): 个人文档编辑器接通BlockNote uploadFile——threadId prop+上传helper,激活面板/拖拽/粘贴三入口" -- frontend/src/extensions/docmgr/utils/docImage.ts frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx frontend/src/extensions/docmgr/DocumentManagement.tsx
```

---

### Task 3: Docker 环境手工验证 + 记账

**Files:** 无代码改动（验证 + `.wolf` 记账）

- [ ] **Step 1: 重启容器**

```bash
docker compose -p eai-docker restart gateway
```
（前端走 HMR；页面不生效再 `docker compose -p eai-docker restart frontend`。）

- [ ] **Step 2: 浏览器验证清单**

登录 `http://localhost:2026`（admin@eai-flow.com / Admin@2026）→ 文档空间 → 个人文档 → 打开任一 .md 文档：

1. **粘贴截图**（Win+Shift+S 后 Ctrl+V）→ 图片出现在光标处（先占位转圈后渲染）
2. **拖拽**本地 .png 进编辑器 → 落在松手位置
3. slash `/` → 图片 → 面板出现**"上传"和"嵌入链接"两个 tab**（之前只有嵌入链接）→ 上传 tab 选文件可插入
4. 拖入 .svg → 不插入 / 占位块报错（白名单拒绝）
5. 刷新页面重进文档 → 图片仍在（markdown 已保存 `![name](/api/threads/.../images/xxx.png)`）
6. 后端落盘核对：`docker exec deer-flow-gateway find /eai-flow/backend/.deer-flow/users -path "*outputs/images/*" -newer /tmp -name "*.png" | head`（路径以实际 base_dir 为准，或直接看文档所在线程目录）

Expected: 1-5 全部通过；6 的文件名与 markdown URL 一致。

- [ ] **Step 3: OpenWolf 记账**

```bash
printf '| %s | 图片上传端点+前端接线实现完成,手工验证通过 | docmgr/routers.py,PersonalBlockNoteEditor.tsx,utils/docImage.ts | done | ~2k |\n' "$(date +%H:%M)" >> .wolf/memory.md
```
（`.wolf/anatomy.md` 由 hook 自动更新新文件条目；若无 hook 触发，手动补 `utils/docImage.ts` 与 `test_docmgr_images.py` 两行。）

---

## Self-Review 记录

- **Spec 覆盖**：§3 端点→Task 1；§4 前端→Task 2（注：spec 涉及文件表把 DocAIAgentPanel 也列入，实际该组件只持有 editorRef 不渲染编辑器，唯一渲染点在 DocumentManagement.tsx:2763，已修正）；§5 错误处理→uploadFile 抛错（BlockNote 占位块原生错误态）+ helper 透出后端 detail；§7 测试→Task 1 五个用例（artifacts GET 200 属既有已测基础设施，以"落盘路径与 URL 严格相等"等价覆盖）；§2 数据流→Task 3 手工验证。
- **占位符扫描**：无 TBD/TODO，所有代码步骤含完整代码。
- **类型一致性**：`uploadDocImage(threadId, file): Promise<{url}>` 在 helper/编辑器两处一致；`upload_thread_image(thread_id, file, current_user)` 签名与测试直调一致；`ThreadImageResponse.url` 与前端 `{ url }` 解构一致。
