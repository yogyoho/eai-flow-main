# 知识库实例详情页 Tab 打磨（P1）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把知识库详情页右侧 2 个 tab（检索测试 / 检索配置）打磨成可深链接的独立路由 + shadcn Tabs，并把检索配置持久化到 KB、让 `/chat` 回退使用持久化配置。

**Architecture:** 后端：`KnowledgeBase` 加 `retrieval_config` JSON 列（幂等 ALTER，无 Alembic）+ 新增 `PUT /retrieval-config` + `/chat` 回退逻辑抽成纯函数。前端：详情抽到 `/knowledge/[kbId]` 路由 + 独立组件文件，手写 button tab 换 shadcn `Tabs(line)`，检索配置加保存按钮持久化、检索测试加内联 top-k 与结果排序。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy(async) / Pydantic（后端，extension 层）；Next.js 16 / React 19 / TanStack Query / shadcn(Radix) Tabs / Tailwind（前端）。后端测试 pytest + AsyncMock；前端 Rstest。

**硬约束:** 不得改动 `backend/packages/harness/deerflow/**`。全部后端改动限于 `backend/app/extensions/**`。检索一律走既有 RAGFlow，不引新引擎、不调 LLM。

**参考 spec:** `docs/superpowers/specs/2026-08-10-knowledge-base-detail-tabs-design.md`

---

## 文件结构总览

**后端（全部 `backend/app/extensions/`）**
- 修改 `models/__init__.py` — `KnowledgeBase` 加 `retrieval_config` 列
- 修改 `schemas.py` — 新增 `RetrievalConfig` + `RETRIEVAL_CONFIG_DEFAULTS`；`RAGChatRequest` 三参改 Optional；`KnowledgeBaseResponse` 加 `retrieval_config`
- 修改 `knowledge/service.py` — `to_response` 合并默认值；新增 `resolve_chat_params` 纯函数
- 修改 `knowledge/routers.py` — `/chat` 用 `resolve_chat_params`；新增 `PUT /{kb_id}/retrieval-config`
- 修改 `database.py` — `migrate_db()` 加幂等 ALTER
- 新增测试 `backend/tests/test_knowledge_retrieval_config.py`

**前端（`frontend/src/`）**
- 修改 `extensions/types/index.ts` — `KnowledgeBase` 加 `retrieval_config`；新增 `RetrievalConfig`
- 修改 `extensions/api/index.ts` — `kbApi` 加 `updateRetrievalConfig`
- 新增 `app/knowledge/[kbId]/page.tsx` — 详情路由（薄）
- 新增 `app/knowledge/_components/KnowledgeBaseDetail.tsx` — 从 page.tsx 抽出
- 新增 `app/knowledge/_components/{CustomSelect,DocStatusBadge,ChunkModal,UploadModal}.tsx` — 共用小件抽出
- 修改 `app/knowledge/page.tsx` — 仅留列表；卡片点击改 `router.push`
- 新增 `tests/unit/app/knowledge/retrieval-config.test.ts` — 纯函数排序测试

---

## Task 1: 后端 — 模型列 + Schema + 常量

**Files:**
- Modify: `backend/app/extensions/models/__init__.py:161`（在 `parser_config` 行之后插入）
- Modify: `backend/app/extensions/schemas.py`（`_KB_TYPE_VALUES` 之后、`KnowledgeBaseBase` 之前插入常量与 `RetrievalConfig`；改 `RAGChatRequest`；`KnowledgeBaseResponse` 加字段）

- [ ] **Step 1: 给 `KnowledgeBase` 加列**

在 `backend/app/extensions/models/__init__.py` 第 161 行 `parser_config` 之后插入一行：

```python
    parser_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    retrieval_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    language: Mapped[str] = mapped_column(String(20), default="Chinese")
```

（`JSON`、`mapped_column` 已在文件顶部导入，与 `parser_config` 同款。）

- [ ] **Step 2: 在 `schemas.py` 新增常量与 `RetrievalConfig`**

在 `schemas.py` 第 370 行 `_KB_TYPE_VALUES = ...` 之前插入：

```python
class RetrievalConfig(BaseModel):
    """Per-KB persisted retrieval parameters, stored as JSON on KnowledgeBase."""

    top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    vector_similarity_weight: float = Field(default=0.3, ge=0.0, le=1.0)


# 默认值常量；to_response 与 resolve_chat_params 共用，保证「未配置」时的行为一致。
RETRIEVAL_CONFIG_DEFAULTS: dict = RetrievalConfig().model_dump()
```

（`BaseModel`、`Field` 已在 schemas.py 顶部导入。）

- [ ] **Step 3: 改 `RAGChatRequest` 三参为 Optional**

把 `schemas.py` 第 512–518 行替换为：

```python
class RAGChatRequest(BaseModel):
    """RAG chat request schema.

    三个检索参数均可省略：省略时由 router 按 请求 → KB.retrieval_config → DEFAULTS 顺序回退。
    （改 Optional 前，pydantic 默认值会让省略恒等于 5/0.2/0.3，持久化配置无法生效。）
    """

    query: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    vector_similarity_weight: float | None = Field(default=None, ge=0.0, le=1.0)
```

- [ ] **Step 4: `KnowledgeBaseResponse` 加 `retrieval_config` 字段**

在 `schemas.py` 第 421–432 行 `KnowledgeBaseResponse` 内，`status: str` 之前插入：

```python
    retrieval_config: dict | None = None
    status: str
```

- [ ] **Step 5: 语法自检**

Run: `cd backend && python -c "import ast; ast.parse(open('app/extensions/models/__init__.py',encoding='utf-8').read()); ast.parse(open('app/extensions/schemas.py',encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/models/__init__.py backend/app/extensions/schemas.py
git commit -m "feat(kb): 新增 retrieval_config 列与 RetrievalConfig schema（检索配置持久化前置）"
```

---

## Task 2: 后端 — 迁移 ALTER（幂等加列）

**Files:**
- Modify: `backend/app/extensions/database.py`（`migrate_db()` 内，第 1028 行 `report_projects.description` ALTER 之后）

- [ ] **Step 1: 在 `migrate_db()` 加幂等 ALTER**

在第 1028 行 `ALTER TABLE report_projects ADD COLUMN IF NOT EXISTS description TEXT` 这一语句块之后插入：

```python
        # EAI-CUSTOM: 每-KB 检索配置 (top_k/similarity_threshold/vector_similarity_weight)
        # create_all 不 ALTER 已有表，须在此幂等加列（与 report_projects.description 同机制）
        await conn.execute(text(
            "ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS retrieval_config JSON"
        ))
```

- [ ] **Step 2: 重启 gateway 让 migrate_db 执行**

Run: `docker compose -p eai-docker restart gateway`
然后查日志确认无报错：`docker compose -p eai-docker logs --tail=30 gateway`

- [ ] **Step 3: 验证列已存在**

Run: `docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "\d knowledge_bases"`
Expected: 输出列表中含 `retrieval_config | json`

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/database.py
git commit -m "feat(kb): migrate_db 幂等加列 knowledge_bases.retrieval_config"
```

---

## Task 3: 后端 — `to_response` 合并默认值（TDD）

**Files:**
- Test: `backend/tests/test_knowledge_retrieval_config.py`（新建）
- Modify: `backend/app/extensions/knowledge/service.py:256-277`（`to_response`）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_knowledge_retrieval_config.py`：

```python
"""retrieval_config 持久化与 /chat 回退逻辑的纯单元测试（无 DB）。"""

from unittest.mock import MagicMock

from app.extensions.knowledge.service import KnowledgeBaseService
from app.extensions.schemas import RETRIEVAL_CONFIG_DEFAULTS


def _kb_mock(retrieval_config=None):
    kb = MagicMock()
    kb.id = "kb-1"
    kb.name = "demo"
    kb.description = None
    kb.ragflow_dataset_id = "ds-1"
    kb.owner_id = "u-1"
    kb.owner = MagicMock(username=None)
    kb.access_type = "private"
    kb.kb_type = "ragflow"
    kb.allowed_depts = None
    kb.embedding_model = None
    kb.chunk_method = "naive"
    kb.parser_config = None
    kb.retrieval_config = retrieval_config
    kb.language = "Chinese"
    kb.status = "active"
    kb.created_at = "2026-08-10T00:00:00"
    return kb


def test_to_response_merges_defaults_when_unset():
    resp = KnowledgeBaseService.to_response(_kb_mock(retrieval_config=None))
    assert resp.retrieval_config == RETRIEVAL_CONFIG_DEFAULTS


def test_to_response_stored_overrides_defaults():
    stored = {"top_k": 15}
    resp = KnowledgeBaseService.to_response(_kb_mock(retrieval_config=stored))
    assert resp.retrieval_config == {**RETRIEVAL_CONFIG_DEFAULTS, "top_k": 15}
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_retrieval_config.py -v`
Expected: FAIL —— `KnowledgeBaseResponse` 校验报缺 `retrieval_config` 或 to_response 未带该字段。

- [ ] **Step 3: 实现 — `to_response` 合并默认值**

在 `service.py` 顶部导入区，把 `from app.extensions.schemas import ...` 这一行扩展，加入 `RetrievalConfig`（若已导入其它 schema，追加即可）。然后在 `to_response`（第 261–277 行）的 `KnowledgeBaseResponse(...)` 构造里，`parser_config=kb.parser_config,` 之后、`language=...` 之前插入：

```python
            parser_config=kb.parser_config,
            retrieval_config={
                **RetrievalConfig().model_dump(),
                **(kb.retrieval_config or {}),
            },
            language=kb.language,
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_retrieval_config.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/knowledge/service.py backend/tests/test_knowledge_retrieval_config.py
git commit -m "feat(kb): to_response 返回与默认值合并后的 retrieval_config"
```

---

## Task 4: 后端 — `resolve_chat_params` 回退纯函数（TDD）

**Files:**
- Test: `backend/tests/test_knowledge_retrieval_config.py`（追加）
- Modify: `backend/app/extensions/knowledge/service.py`（`KnowledgeBaseService` 内新增静态方法）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_knowledge_retrieval_config.py` 末尾追加：

```python
from app.extensions.knowledge.service import KnowledgeBaseService as KBS
from app.extensions.schemas import RAGChatRequest


def test_resolve_params_falls_back_to_defaults():
    req = RAGChatRequest(query="q")
    kb = _kb_mock(retrieval_config=None)
    assert KBS.resolve_chat_params(req, kb) == (5, 0.2, 0.3)


def test_resolve_params_uses_persisted_when_request_omits():
    req = RAGChatRequest(query="q")
    kb = _kb_mock(retrieval_config={"top_k": 12, "similarity_threshold": 0.5, "vector_similarity_weight": 0.7})
    assert KBS.resolve_chat_params(req, kb) == (12, 0.5, 0.7)


def test_resolve_params_request_overrides_persisted():
    req = RAGChatRequest(query="q", top_k=3)
    kb = _kb_mock(retrieval_config={"top_k": 12, "similarity_threshold": 0.5, "vector_similarity_weight": 0.7})
    # 仅 top_k 被请求覆盖，其余仍取持久化
    assert KBS.resolve_chat_params(req, kb) == (3, 0.5, 0.7)
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_retrieval_config.py -v`
Expected: FAIL —— `resolve_chat_params` 不存在（AttributeError）。

- [ ] **Step 3: 实现 — 新增 `resolve_chat_params`**

在 `service.py` 的 `KnowledgeBaseService` 类内，`to_response` 方法之后新增（注意导入 `RETRIEVAL_CONFIG_DEFAULTS`，与 `RetrievalConfig` 一起加到顶部 schemas 导入）：

```python
    @staticmethod
    def resolve_chat_params(
        request: RAGChatRequest, kb: KnowledgeBase
    ) -> tuple[int, float, float]:
        """解析生效检索参数：请求显式值 → KB.retrieval_config → DEFAULTS。"""
        cfg = kb.retrieval_config or {}
        top_k = (
            request.top_k
            if request.top_k is not None
            else cfg.get("top_k", RETRIEVAL_CONFIG_DEFAULTS["top_k"])
        )
        similarity_threshold = (
            request.similarity_threshold
            if request.similarity_threshold is not None
            else cfg.get("similarity_threshold", RETRIEVAL_CONFIG_DEFAULTS["similarity_threshold"])
        )
        vector_similarity_weight = (
            request.vector_similarity_weight
            if request.vector_similarity_weight is not None
            else cfg.get("vector_similarity_weight", RETRIEVAL_CONFIG_DEFAULTS["vector_similarity_weight"])
        )
        return int(top_k), float(similarity_threshold), float(vector_similarity_weight)
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_retrieval_config.py -v`
Expected: PASS（5 个测试）

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/knowledge/service.py backend/tests/test_knowledge_retrieval_config.py
git commit -m "feat(kb): resolve_chat_params 三级回退（请求→持久化→默认）"
```

---

## Task 5: 后端 — `/chat` 接线 + `PUT /retrieval-config` 端点

**Files:**
- Modify: `backend/app/extensions/knowledge/routers.py`（顶部 import；`/chat` 第 528–536 行；新增 PUT 端点）

- [ ] **Step 1: import 补 `RetrievalConfig`**

在 `routers.py` 第 22–39 行的 `from app.extensions.schemas import (...)` 块内，按字母序加入 `RetrievalConfig,`（与 `RAGChatRequest` 同块）。

- [ ] **Step 2: 改 `/chat` 用 `resolve_chat_params`**

把 `routers.py` 第 528–536 行 `try:` 内的 `rf_client = RAGFlowClient()` 及其后的 `result = await rf_client.chat(...)` 替换为：

```python
    try:
        top_k, similarity_threshold, vector_similarity_weight = (
            KnowledgeBaseService.resolve_chat_params(request, kb)
        )
        rf_client = RAGFlowClient()
        result = await rf_client.chat(
            dataset_id=kb.ragflow_dataset_id,
            query=request.query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            vector_similarity_weight=vector_similarity_weight,
        )
```

- [ ] **Step 3: 新增 `PUT /{kb_id}/retrieval-config`**

在 `routers.py` 的 `update_knowledge_base`（第 203 行结束）之后、`delete_knowledge_base`（第 206 行）之前插入：

```python
@router.put("/{kb_id}/retrieval-config", response_model=KnowledgeBaseResponse)
async def update_retrieval_config(
    kb_id: UUID,
    data: RetrievalConfig,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("kb:update")),
    scope: FilterRule = Depends(with_data_scope("knowledge")),
    identity: AttributeSet = Depends(current_identity),
):
    """Persist per-KB retrieval config (top_k / similarity_threshold / vector_similarity_weight)."""
    kb = await _load_kb_scoped(db, kb_id, scope, identity)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    from app.extensions.knowledge.access import has_kb_grant

    # 写门 = owner | write-grantee | 超管（与 update_kb 一致）
    is_admin = await is_superadmin(db, current_user.id)
    has_write = await has_kb_grant(db, kb.id, identity, "write")
    if kb.owner_id != current_user.id and not is_admin and not has_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    kb.retrieval_config = data.model_dump()
    await db.commit()
    await db.refresh(kb)
    return KnowledgeBaseService.to_response(kb)
```

- [ ] **Step 4: 重启 + 手动校验**

Run: `docker compose -p eai-docker restart gateway`

校验（用管理员 cookie；`<KBID>` 替换为真实 KB id）：

```bash
# 越界 → 422
curl -s -o /dev/null -w "%{http_code}\n" -X PUT http://localhost:2026/api/extensions/knowledge-bases/<KBID>/retrieval-config \
  -H "Content-Type: application/json" -b "access_token=<你的cookie>" -H "X-CSRF-Token: <你的csrf>" \
  -d '{"top_k":999,"similarity_threshold":0.2,"vector_similarity_weight":0.3}'
# 期望: 422

# 合法 → 200，返回体含 retrieval_config
curl -s -X PUT http://localhost:2026/api/extensions/knowledge-bases/<KBID>/retrieval-config \
  -H "Content-Type: application/json" -b "access_token=<你的cookie>" -H "X-CSRF-Token: <你的csrf>" \
  -d '{"top_k":7,"similarity_threshold":0.25,"vector_similarity_weight":0.4}' | head -c 300
# 期望: 200，JSON 含 "retrieval_config":{"top_k":7,...}
```

（若手头没有现成 cookie，可跳过 curl，改在 Task 9 前端联调时一并验证。）

- [ ] **Step 5: 跑全量后端测试 + lint**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_retrieval_config.py tests/test_knowledge_data_access.py -v && make lint`
Expected: 全 PASS，lint 无报错。

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/knowledge/routers.py
git commit -m "feat(kb): /chat 回退持久化检索配置 + PUT /retrieval-config 端点"
```

---

## Task 6: 前端 — 类型与 API 层

**Files:**
- Modify: `frontend/src/extensions/types/index.ts:164`（`KnowledgeBase`）、新增 `RetrievalConfig`
- Modify: `frontend/src/extensions/api/index.ts:369`（`kbApi`）

- [ ] **Step 1: `KnowledgeBase` 加 `retrieval_config`**

在 `types/index.ts` 第 183 行 `language?: string;` 之后插入：

```ts
  retrieval_config?: {
    top_k: number;
    similarity_threshold: number;
    vector_similarity_weight: number;
  };
  status: string;
```

- [ ] **Step 2: 新增 `RetrievalConfig` 类型**

在 `types/index.ts` 第 186 行 `KnowledgeBase` 接口结束 `}` 之后插入：

```ts
export interface RetrievalConfig {
  top_k: number;
  similarity_threshold: number;
  vector_similarity_weight: number;
}
```

- [ ] **Step 3: `kbApi` 加 `updateRetrievalConfig`**

在 `api/index.ts` 的 `kbApi` 内，`chat(...)` 之后（第 437 行附近）插入。先确认顶部 `import type { ... } from "@/extensions/types";` 含 `RetrievalConfig`（若无则补）。

```ts
  // Persist per-KB retrieval config
  updateRetrievalConfig: (id: string, cfg: RetrievalConfig) =>
    request<KnowledgeBase>(`/knowledge-bases/${id}/retrieval-config`, {
      method: "PUT",
      body: JSON.stringify(cfg),
    }),
```

- [ ] **Step 4: typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: 无报错（新增类型被引用前可能有「未使用」警告，下个 Task 会用到，可忽略；若报错则先在此 Task 末尾的 commit 前确认无阻塞性类型错）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/types/index.ts frontend/src/extensions/api/index.ts
git commit -m "feat(kb): 前端类型与 kbApi.updateRetrievalConfig"
```

---

## Task 7: 前端 — 抽出共用小件到 `_components/`

> 先抽「无外部依赖争议」的小件，降低 Task 8 大块搬迁的风险。这些件目前内联在 `page.tsx`。

**Files:**
- Create: `frontend/src/app/knowledge/_components/CustomSelect.tsx`（来自 `page.tsx:123`）
- Create: `frontend/src/app/knowledge/_components/DocStatusBadge.tsx`（来自 `page.tsx:231`）
- Create: `frontend/src/app/knowledge/_components/UploadModal.tsx`（来自 `page.tsx:272`）
- Create: `frontend/src/app/knowledge/_components/ChunkModal.tsx`（来自 `page.tsx:472–512`，含 `ChunkHtmlBody`）
- Modify: `frontend/src/app/knowledge/page.tsx`（删除被搬走的内联定义，改为 import）

- [ ] **Step 1: 创建 `_components/` 目录并搬 `CustomSelect`**

把 `page.tsx` 第 123 行起、到 `DocStatusBadge` 之前的 `function CustomSelect(...) {...}` 整段，**逐字**剪切到 `frontend/src/app/knowledge/_components/CustomSelect.tsx`，文件顶部加：

```tsx
import { cn } from "@/lib/utils";
```

补齐该函数实际用到的其它 import（按 typecheck 报错逐个补，通常是 React 类型、icon）。

- [ ] **Step 2: 搬 `DocStatusBadge`**

把 `page.tsx:231` 的 `function DocStatusBadge(...)`（到 `UploadModal` 之前）剪切到 `_components/DocStatusBadge.tsx`，补 import（`cn`、用到的 lucide icon）。

- [ ] **Step 3: 搬 `UploadModal`**

把 `page.tsx:272` 的 `UploadModal` 剪切到 `_components/UploadModal.tsx`，补 import（`kbApi`、`ChunkConfig`/`Document` 类型、`Button`、icon、`cn`、sonner 等，按 typecheck 报错补全）。

- [ ] **Step 4: 搬 `ChunkHtmlBody` + `ChunkModal`**

把 `page.tsx:472` 的 `ChunkHtmlBody` 与 `:513` 的 `ChunkModal` 一起剪切到 `_components/ChunkModal.tsx`（保留两个导出：`export function ChunkModal(...)` 与 `export function ChunkHtmlBody(...)`），补 import（`DOMPurify`、`kbApi`、`Document`、`Dialog`/`Sheet` 等组件、icon）。

- [ ] **Step 5: 在 `page.tsx` 顶部加 import，删除已搬的内联定义**

在 `page.tsx` import 区加：

```ts
import { ChunkModal, ChunkHtmlBody } from "./_components/ChunkModal";
import { CustomSelect } from "./_components/CustomSelect";
import { DocStatusBadge } from "./_components/DocStatusBadge";
import { UploadModal } from "./_components/UploadModal";
```

删除 page.tsx 中已被搬走的 4 个内联函数定义。

- [ ] **Step 6: typecheck + 跑前端测试**

Run: `cd frontend && pnpm typecheck && pnpm test`
Expected: typecheck 通过；已有测试不回归。

- [ ] **Step 7: 浏览器烟测**

`docker compose -p eai-docker restart frontend`，访问 `/knowledge`，确认列表页、上传弹窗、分块查看仍正常。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/knowledge/_components/ frontend/src/app/knowledge/page.tsx
git commit -m "refactor(kb): 抽出 CustomSelect/DocStatusBadge/UploadModal/ChunkModal 到 _components"
```

---

## Task 8: 前端 — 抽出 `KnowledgeBaseDetail` 到 `[kbId]` 路由

> 这是最大一步。把 `page.tsx:628` 起的整个 `KnowledgeBaseDetail` 函数搬到独立组件文件，新建 `/knowledge/[kbId]` 路由页，列表页改为 `router.push`。

**Files:**
- Create: `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`（来自 `page.tsx:628–1652`）
- Create: `frontend/src/app/knowledge/[kbId]/page.tsx`
- Modify: `frontend/src/app/knowledge/page.tsx`（删 `selectedKb` 渲染分支、删 `KnowledgeBaseDetail` 定义、卡片点击改跳转）

- [ ] **Step 1: 新建 `[kbId]/page.tsx`**

创建 `frontend/src/app/knowledge/[kbId]/page.tsx`：

```tsx
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { use } from "react";

import { KnowledgeBaseDetail } from "../_components/KnowledgeBaseDetail";
import { kbApi } from "@/extensions/api";

export default function KnowledgeBaseDetailPage({
  params,
}: {
  params: Promise<{ kbId: string }>;
}) {
  const { kbId } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: kb, isLoading, error } = useQuery({
    queryKey: ["kb", kbId],
    queryFn: () => kbApi.get(kbId),
  });

  if (isLoading) {
    return <div className="p-8 text-sm text-muted-foreground">加载中…</div>;
  }
  if (error || !kb) {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        知识库不存在或无权访问。
        <button className="ml-2 underline" onClick={() => router.push("/knowledge")}>
          返回列表
        </button>
      </div>
    );
  }

  return (
    <KnowledgeBaseDetail
      kb={kb}
      onBack={() => router.push("/knowledge")}
      onKbUpdated={(updated) => {
        queryClient.setQueryData(["kb", kbId], updated);
      }}
    />
  );
}
```

- [ ] **Step 2: 搬 `KnowledgeBaseDetail` 到 `_components/KnowledgeBaseDetail.tsx`**

把 `page.tsx` 第 628 行起、到该函数结束（约第 1652 行）的整段 `function KnowledgeBaseDetail({...}) {...}` **逐字**剪切到 `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`。

文件顶部 import 段写入（按该函数实际用到的符号补全；以下是确定的必需项，缺漏由 typecheck 提示补）：

```tsx
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  ArrowLeft,
  Check,
  Database,
  Loader2,
  RefreshCw,
  Search as SearchIcon,
  Settings,
  Trash2,
  Upload,
  X,
} from "lucide-react"; // 按实际用到的图标裁剪

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { usePermission } from "@/core/permissions";
import { deptApi, kbApi, roleApi, userApi } from "@/extensions/api";
import type {
  Department,
  Document,
  KnowledgeBase,
  KnowledgeBaseGrant,
  Role,
  UpdateKnowledgeBaseRequest,
  User,
} from "@/extensions/types";
import { cn } from "@/lib/utils";

import { ChunkModal } from "./ChunkModal";
import { CustomSelect } from "./CustomSelect";
import { DocStatusBadge } from "./DocStatusBadge";
import { UploadModal } from "./UploadModal";
```

- [ ] **Step 3: 去掉 `toast` prop，改用 sonner 直接调用**

`KnowledgeBaseDetail` 现签名含 `toast` prop。改造为：删除 `toast` 入参，把函数体内所有 `toast(msg, "error"|"success")` 调用替换为 sonner：

- `toast(msg, "error")` → `toast.error(msg)`
- `toast(msg, "success")` → `toast.success(msg)`

（`page.tsx` 原先传入的 `toast` 是对 sonner 的薄包装，语义一致。）新签名：

```tsx
function KnowledgeBaseDetail({
  kb,
  onBack,
  onKbUpdated,
}: {
  kb: KnowledgeBase;
  onBack: () => void;
  onKbUpdated?: (kb: KnowledgeBase) => void;
}) {
```

文件末尾加 `export`：`export function KnowledgeBaseDetail(...) {...}`。

- [ ] **Step 4: 列表页移除 `selectedKb` 分支，卡片点击改 `router.push`**

在 `page.tsx`：
1. 删除第 1863–1875 行 `if (selectedKb) { return <KnowledgeBaseDetail .../> }` 整个分支。
2. 删除 `selectedKb` state 声明（及其在 `onKbUpdated` 里的 `setSelectedKb` 引用——该回调现在只更新列表数据 `setKbs`）。
3. 第 1959 行卡片 `onClick={() => setSelectedKb(kb)}` 改为：

```tsx
                    onClick={() => router.push(`/knowledge/${kb.id}`)}
```

4. 确保 `page.tsx` 顶部已 `import { useRouter } from "next/navigation";` 并 `const router = useRouter();`（在 `KnowledgeBaseManagement` 内）。
5. 删除 `page.tsx` 中已被搬走的 `KnowledgeBaseDetail` 函数定义，以及现在不再需要的 import（如 `ChunkModal`/`UploadModal` 若仅被 detail 使用——但 Task 7 已让列表页仍 import `UploadModal`? 确认：列表页的 create/edit 不用 UploadModal；UploadModal 仅 detail 用。所以把 `UploadModal` 的 import 从 page.tsx 移到 `KnowledgeBaseDetail.tsx`，page.tsx 删掉。`ChunkModal`、`ChunkHtmlBody` 同理仅 detail 用，从 page.tsx 删除其 import。`CustomSelect`/`DocStatusBadge` 若列表页仍用则保留）。

- [ ] **Step 5: typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: 通过。逐条修掉「X is not defined / declared but never used」。

- [ ] **Step 6: 重启前端 + 烟测深链接**

Run: `docker compose -p eai-docker restart frontend`
浏览器：访问 `/knowledge`，点卡片 → URL 变为 `/knowledge/<id>`；刷新页面仍在详情页；点返回回到列表。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/knowledge/
git commit -m "feat(kb): 详情抽到 /knowledge/[kbId] 路由，支持深链接"
```

---

## Task 9: 前端 — 右侧 tab 换 shadcn `Tabs(line)`

**Files:**
- Modify: `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`（第 1095–1111 行的 button 条；对应搬迁后的等价位置）

- [ ] **Step 1: import shadcn Tabs**

在 `KnowledgeBaseDetail.tsx` 顶部 import 区加：

```ts
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
```

- [ ] **Step 2: 删除 `activeTab` state，用 Tabs 受控/非受控**

删除 `const [activeTab, setActiveTab] = useState<"test" | "config">("test");`。改用非受控 `defaultValue="test"`（若后续需编程切换再加受控）。

- [ ] **Step 3: 替换 button 条与两处条件渲染**

把原来的：

```tsx
        <div className="flex shrink-0 items-center border-b border-border px-4">
          {(["test", "config"] as const).map((tab) => (
            <button ... >{tab === "test" ? "检索测试" : "检索配置"}</button>
          ))}
        </div>
        <div className="flex flex-1 flex-col gap-4 overflow-auto bg-muted/30 p-4">
          {activeTab === "test" && (<>...</>)}
          {activeTab === "config" && (...)}
        </div>
```

替换为（把 `activeTab === "test"` 的内容放进 `TabsContent value="test"`，`config` 同理；外层用 `<Tabs>` 包裹整个右栏内容区）：

```tsx
        <Tabs defaultValue="test" className="flex flex-1 flex-col overflow-hidden">
          <TabsList variant="line" className="shrink-0 justify-start rounded-none border-b border-border px-4">
            <TabsTrigger value="test">检索测试</TabsTrigger>
            <TabsTrigger value="config">检索配置</TabsTrigger>
          </TabsList>
          <TabsContent value="test" className="flex-1 overflow-auto bg-muted/30 p-4">
            {/* 原 activeTab === "test" 的内容 */}
          </TabsContent>
          <TabsContent value="config" className="flex-1 overflow-auto bg-muted/30 p-4">
            {/* 原 activeTab === "config" 的内容 */}
          </TabsContent>
        </Tabs>
```

（右栏最外层 `<div className="flex w-1/2 flex-col overflow-hidden rounded-xl ...">` 保留不动，`<Tabs>` 放在它内部取代原先的 tab 条 + 内容区两个 div。）

- [ ] **Step 4: typecheck + 重启烟测**

Run: `cd frontend && pnpm typecheck`
Run: `docker compose -p eai-docker restart frontend`
浏览器：进详情页，两个 tab 切换正常，下划线高亮跟随。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx
git commit -m "refactor(kb): 右侧 tab 换 shadcn Tabs(line 样式)"
```

---

## Task 10: 前端 — 检索配置持久化（滑块 + 保存/重置）

**Files:**
- Modify: `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`（`topK`/`similarityThreshold` state 初始化、新增 vector weight 滑块、新增保存/重置按钮）

- [ ] **Step 1: 初始化配置 state 自 `kb.retrieval_config`**

在 `KnowledgeBaseDetail` 的 state 区，把现有 `topK`/`similarityThreshold` 初始值改为读 `kb.retrieval_config`，并新增 vector weight：

```tsx
  const [topK, setTopK] = useState<number>(kb.retrieval_config?.top_k ?? 5);
  const [similarityThreshold, setSimilarityThreshold] = useState<number>(
    kb.retrieval_config?.similarity_threshold ?? 0.2,
  );
  const [vectorWeight, setVectorWeight] = useState<number>(
    kb.retrieval_config?.vector_similarity_weight ?? 0.3,
  );
  const [configSaving, setConfigSaving] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);

  // 任一滑块变动 → 标记未保存
  const markDirty = () => setConfigDirty(true);
```

（若 `kb` 可能因 onKbUpdated 更新而需要重置，加一个 `useEffect(() => { setTopK(kb.retrieval_config?.top_k ?? 5); ... }, [kb])` 同步——按 typecheck/手测决定是否需要。）

- [ ] **Step 2: 新增 `handleSaveConfig`**

在 `handleSearch` 附近新增：

```tsx
  const handleSaveConfig = async () => {
    setConfigSaving(true);
    try {
      const updated = await kbApi.updateRetrievalConfig(kb.id, {
        top_k: topK,
        similarity_threshold: similarityThreshold,
        vector_similarity_weight: vectorWeight,
      });
      onKbUpdated?.(updated);
      setConfigDirty(false);
      toast.success("检索配置已保存");
    } catch (e: any) {
      toast.error(e?.message ?? "保存失败");
    } finally {
      setConfigSaving(false);
    }
  };

  const handleResetConfig = () => {
    setTopK(kb.retrieval_config?.top_k ?? 5);
    setSimilarityThreshold(kb.retrieval_config?.similarity_threshold ?? 0.2);
    setVectorWeight(kb.retrieval_config?.vector_similarity_weight ?? 0.3);
    setConfigDirty(false);
  };
```

- [ ] **Step 3: 给三个滑块挂 `onChange` 的同时调 `markDirty`**

把现有 Top-K / 相似度阈值两个 `<input type="range">` 的 `onChange` 包一层 `markDirty`，并新增向量权重滑块（插在相似度阈值滑块 `</div>` 之后、`检索参数` 卡片结束 `</div>` 之前）：

```tsx
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    向量权重{" "}
                    <span className="font-normal text-muted-foreground">
                      （向量 vs 关键词的比重）
                    </span>
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={vectorWeight}
                      onChange={(e) => {
                        setVectorWeight(Number(e.target.value));
                        markDirty();
                      }}
                      className="flex-1 accent-primary"
                    />
                    <span className="w-10 text-center text-sm font-medium text-foreground">
                      {vectorWeight.toFixed(2)}
                    </span>
                  </div>
                </div>
```

（Top-K、相似度阈值的 `onChange` 各自追加 `markDirty();`。）

- [ ] **Step 4: 加「保存 / 重置」按钮**

在「检索参数」卡片底部（三个滑块之后、卡片结束 `</div>` 之前）加：

```tsx
                <div className="flex items-center gap-2 pt-1">
                  <Button size="sm" onClick={handleSaveConfig} disabled={configSaving || !configDirty}>
                    {configSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    保存配置
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleResetConfig} disabled={!configDirty}>
                    重置
                  </Button>
                </div>
```

- [ ] **Step 5: typecheck + 重启 + 端到端验证**

Run: `cd frontend && pnpm typecheck`
Run: `docker compose -p eai-docker restart frontend`

浏览器验证（对照 spec 验收 #3）：
1. 进某 KB 详情 → 检索配置 tab → 改 Top-K 为 7 → 保存（toast 成功，按钮恢复禁用）。
2. 刷新页面 → Top-K 仍为 7（持久化生效）。
3. 切到检索测试 tab → 搜索 → 结果条数受 Top-K=7 影响（验证 `/chat` 回退生效）。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx
git commit -m "feat(kb): 检索配置滑块持久化（保存/重置 + 向量权重）"
```

---

## Task 11: 前端 — 检索测试打磨（内联 top-k + 结果排序 + 点开 chunk）

**Files:**
- Modify: `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`（`handleSearch`、sources 渲染）
- Create: `frontend/tests/unit/app/knowledge/sources-sort.test.ts`

- [ ] **Step 1: 抽纯函数 `sortSourcesByScore` 并写测试**

创建 `frontend/tests/unit/app/knowledge/sources-sort.test.ts`：

```ts
import { describe, expect, it } from "rstest";

import { sortSourcesByScore } from "@/app/knowledge/_components/KnowledgeBaseDetail";

describe("sortSourcesByScore", () => {
  it("sorts by score descending, missing scores last (stable)", () => {
    const srcs = [
      { content: "a", score: 0.1 },
      { content: "b", score: 0.9 },
      { content: "c" },
      { content: "d", score: 0.5 },
    ];
    const out = sortSourcesByScore(srcs);
    expect(out.map((s) => s.content)).toEqual(["b", "d", "a", "c"]);
  });

  it("does not mutate input", () => {
    const srcs = [{ content: "a", score: 0.1 }, { content: "b", score: 0.9 }];
    sortSourcesByScore(srcs);
    expect(srcs.map((s) => s.content)).toEqual(["a", "b"]);
  });
});
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `cd frontend && pnpm test sources-sort`
Expected: FAIL —— `sortSourcesByScore` 未导出。

- [ ] **Step 3: 在 `KnowledgeBaseDetail.tsx` 实现 + 导出纯函数**

在文件内（组件外）加：

```ts
export function sortSourcesByScore<T extends { score?: number }>(srcs: T[]): T[] {
  return [...srcs].sort((a, b) => {
    const sa = typeof a.score === "number" ? a.score : -Infinity;
    const sb = typeof b.score === "number" ? b.score : -Infinity;
    return sb - sa;
  });
}
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `cd frontend && pnpm test sources-sort`
Expected: PASS

- [ ] **Step 5: `handleSearch` 不再写死 similarity_threshold，用持久化值；结果排序**

把 `handleSearch`（搬迁后等价位置）改为：

```tsx
  const handleSearch = async () => {
    if (!query.trim()) return;
    setChatLoading(true);
    setChatResult(null);
    try {
      const result = await kbApi.chat(kb.id, {
        query,
        top_k: topK,
        // similarity_threshold / vector_similarity_weight 省略 → 后端回退持久化配置
      });
      setChatResult({
        answer: result.answer,
        sources: sortSourcesByScore(result.sources ?? []),
      });
    } catch (e: any) {
      toast.error(e?.message ?? "检索失败");
    } finally {
      setChatLoading(false);
    }
  };
```

- [ ] **Step 6: sources 渲染加「点击查看原文」→ 复用 ChunkModal**

把 sources 列表项（原 `chatResult.sources.map(...)` 那块）的每条外层 `<div>` 改为可点击，点击后用 chunk 内容打开 `ChunkModal`。新增一个临时 state 承载被点开的 chunk 文本：

```tsx
  const [previewChunk, setPreviewChunk] = useState<{ content: string; name?: string } | null>(null);
```

把每条 source 的 `<div key={idx} ...>` 改为：

```tsx
                          <div
                            key={idx}
                            onClick={() => setPreviewChunk({ content: src.content ?? "", name: src.document_name })}
                            className="cursor-pointer rounded-lg border border-border bg-background p-3 text-xs transition-colors hover:border-primary/40 hover:bg-muted/40"
                          >
```

在「检索测试」`TabsContent` 末尾（`chatResult` 块之后）加弹窗（复用 `ChunkModal`——若 `ChunkModal` 入参是 doc+chunks 形态不适合单块预览，则用最简内联 `<Dialog>` 展示 `previewChunk.content`；二选一，按 `ChunkModal` 实际签名决定）：

```tsx
              {previewChunk && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setPreviewChunk(null)}>
                  <div className="max-h-[70vh] w-full max-w-2xl overflow-auto rounded-xl border border-border bg-background p-5" onClick={(e) => e.stopPropagation()}>
                    <div className="mb-2 flex items-center justify-between">
                      <h4 className="text-sm font-medium text-foreground">{previewChunk.name ?? "分块原文"}</h4>
                      <button onClick={() => setPreviewChunk(null)} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-foreground/80">{previewChunk.content}</p>
                  </div>
                </div>
              )}
```

（`X` icon 已在 import 中。）

- [ ] **Step 7: typecheck + 测试 + 重启 + 端到端**

Run: `cd frontend && pnpm typecheck && pnpm test`
Run: `docker compose -p eai-docker restart frontend`
浏览器：检索测试搜索 → 结果按相似度降序；点某条 → 弹出该分块原文；关掉返回。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx frontend/tests/unit/app/knowledge/sources-sort.test.ts
git commit -m "feat(kb): 检索测试结果按相似度排序 + 点开分块原文"
```

---

## Task 12: 全量验收 + 收尾

- [ ] **Step 1: 后端全量测试 + lint**

Run: `cd backend && make lint && PYTHONPATH=. uv run pytest tests/test_knowledge_retrieval_config.py tests/test_knowledge_data_access.py -v`
Expected: lint 通过；测试全 PASS。

- [ ] **Step 2: 前端 check**

Run: `cd frontend && pnpm typecheck && pnpm test`
Expected: 通过。

- [ ] **Step 3: harness 零改动校验**

Run: `git diff --stat main-dev-fork -- backend/packages/harness/deerflow/` （对比应无输出）
Expected: 空输出（harness 未被改动）。

- [ ] **Step 4: 逐条对照 spec 验收标准手测**

1. `/knowledge/<id>` 可直接进详情；刷新仍在；列表卡片跳转到该 URL。✅
2. 右侧 shadcn 下划线 2 tab。✅
3. 配置改 Top-K 并保存 → 检索测试结果条数受影响。✅
4. 检索测试结果按相似度降序，可点开 chunk 原文。✅
5. 后端单测 + 前端测试通过；lint/typecheck 通过。✅
6. `backend/packages/harness/deerflow/**` 零改动。✅

- [ ] **Step 5: 更新文档（按项目规范）**

在 `backend/docs/` 或 `docs/` 相关处（若有 knowledge API 文档）补 `PUT /knowledge-bases/{id}/retrieval-config` 与 `/chat` 回退语义说明；无则跳过。

- [ ] **Step 6: 最终 Commit（若有文档/收尾改动）**

```bash
git add -A
git commit -m "docs(kb): 同步检索配置接口与 /chat 回退语义文档"
```

---

## 自审备注（plan self-review 已做）

- **Spec 覆盖**: 范围内 5 项（路由、Tabs、持久化列、/chat 回退、检索测试打磨）分别落在 Task 8、9、1–5、5、11。Defer 项（图谱/导图/评估/示例问题/rerank）均未出现在任何 Task。✅
- **占位符扫描**: 每个 code step 均给出完整代码；Task 7/8 的「逐字剪切 + 按 typecheck 补 import」是对大块搬迁的诚实描述而非占位。✅
- **类型/命名一致性**: `RetrievalConfig` / `RETRIEVAL_CONFIG_DEFAULTS` / `resolve_chat_params` / `updateRetrievalConfig` / `sortSourcesByScore` 在定义处与引用处一致。✅
- **风险点**: Task 8（大块抽取）是最高风险步骤，已拆出 Task 7 先抽小件降险；若 typecheck 报错过多，回到 Task 7 确认共用件 import 干净后再进 Task 8。
