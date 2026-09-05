# 法规库卡片按钮 disabled + laws 投影文件列表(含 chunks)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 知识库管理页:①法规库卡片三按钮 disabled;③法规库详情文件列表实时投影 `laws` 表(只读 + 可查看 chunks),解决"暂无文件"。

**Architecture:** 后端在 `law/service.py` 新增判定/投影/定位三个纯函数级 helper,`knowledge/routers.py` 的 list_documents 与 list_document_chunks 各加一个法规分支(单一真相源仍是 laws 表,零迁移);前端复用 `isLawKnowledgeBase` 在列表页禁用按钮、详情页隐藏行内删除。

**Tech Stack:** FastAPI + SQLAlchemy(async)/Pydantic;Next.js 16/React 19/Tailwind 4;测试 pytest(unit,AsyncMock 风格)+ Rstest;浏览器 E2E 用 superpowers-chrome。

**Spec:** `docs/superpowers/specs/2026-09-05-law-kb-card-buttons-and-doc-list-design.md`

**仓库纪律(并发会话!):** 所有 git add/commit 必须带精确 pathspec,禁止 `git add -A`/裸 `git commit`。当前分支 main-dev-fork,直接提交。

---

### Task 1: 后端 helper(`is_law_kb_name` / `project_laws_as_documents` / `get_law_in_kb`)+ 单测

**Files:**
- Modify: `backend/app/extensions/law/service.py`(文件尾部追加)
- Test: `backend/tests/test_law_kb_documents_projection.py`(新建)

- [ ] **Step 1: 写失败的单测**

```python
# backend/tests/test_law_kb_documents_projection.py
"""法规标准库文件列表投影测试(EAI-CUSTOM, spec 2026-09-05)。

法规系统库无 documents 表记录(法规导入只写 laws 表 + 直传 RAGFlow),
知识库详情的文件列表/ chunks 视图按 laws 实时投影。
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.law.service import (
    LawService,
    is_law_kb_name,
    project_law_as_document,
)

KB_ID = uuid.uuid4()
DATASET_ID = "ds-laws-1"


def _law(synced="synced", dataset=DATASET_ID, number="GB 50160-2008", title="石油化工企业设计防火标准", sector="石化"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        law_number=number,
        title=title,
        is_synced=synced,
        ragflow_dataset_id=dataset,
        ragflow_document_id="rf-doc-1" if synced == "synced" else None,
        metadata_json={"sector": sector},
        created_at=datetime(2026, 9, 1, 8, 0, 0),
    )


def test_is_law_kb_name():
    assert is_law_kb_name("法规标准库 — 标准/规范") is True
    assert is_law_kb_name("法规标准库 — 法律/法规/规章") is True
    assert is_law_kb_name("合同知识库") is False
    assert is_law_kb_name("") is False
    assert is_law_kb_name(None) is False


def test_project_law_as_document_field_mapping():
    doc = project_law_as_document(_law(), KB_ID)
    assert str(doc.id)  # uuid
    assert doc.knowledge_base_id == KB_ID
    assert doc.name == "【石化】GB 50160-2008 石油化工企业设计防火标准"
    assert doc.file_path == ""
    assert doc.file_size == 0
    assert doc.file_type is None
    assert doc.ragflow_document_id == "rf-doc-1"
    assert doc.status == "success"
    assert doc.error_message is None
    assert doc.created_at == datetime(2026, 9, 1, 8, 0, 0)


def test_project_law_status_mapping():
    assert project_law_as_document(_law(synced="failed"), KB_ID).status == "failed"
    assert project_law_as_document(_law(synced="pending"), KB_ID).status == "pending"
    assert project_law_as_document(_law(synced=None), KB_ID).status == "pending"
    # 无行业前缀
    assert project_law_as_document(_law(sector=None), KB_ID).name == "GB 50160-2008 石油化工企业设计防火标准"


@pytest.mark.asyncio
async def test_project_laws_as_documents_query_and_total():
    laws = [_law(), _law(synced="pending")]
    count_rm = MagicMock(); count_rm.scalar.return_value = 2
    rows_rm = MagicMock(); rows_rm.scalars.return_value.all.return_value = laws
    db = AsyncMock(); db.execute.side_effect = [count_rm, rows_rm]
    kb = SimpleNamespace(id=KB_ID, ragflow_dataset_id=DATASET_ID, name="法规标准库 — 标准/规范")

    docs, total = await LawService.project_laws_as_documents(db, kb, skip=0, limit=100)

    assert total == 2
    assert len(docs) == 2
    assert docs[0].ragflow_document_id == "rf-doc-1"
    assert docs[1].status == "pending"
    # 两次查询:count + 分页 select;select 语句含 ragflow_dataset_id 过滤
    first_sql = str(db.execute.await_args_list[0].args[0])
    second_sql = str(db.execute.await_args_list[1].args[0])
    assert "ragflow_dataset_id" in first_sql and "count" in first_sql.lower()
    assert "ragflow_dataset_id" in second_sql and "order" in second_sql.lower().replace(" ", "") or "ORDER" in second_sql


@pytest.mark.asyncio
async def test_get_law_in_kb_matches_dataset():
    law = _law()
    rm = MagicMock(); rm.scalar_one_or_none.return_value = law
    db = AsyncMock(); db.execute.return_value = rm
    kb = SimpleNamespace(id=KB_ID, ragflow_dataset_id=DATASET_ID)

    assert await LawService.get_law_in_kb(db, kb, law.id) is law

    other = _law(dataset="ds-other")
    rm2 = MagicMock(); rm2.scalar_one_or_none.return_value = other
    db.execute.return_value = rm2
    assert await LawService.get_law_in_kb(db, kb, other.id) is None

    rm3 = MagicMock(); rm3.scalar_one_or_none.return_value = None
    db.execute.return_value = rm3
    assert await LawService.get_law_in_kb(db, kb, uuid.uuid4()) is None
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_documents_projection.py -v
```

Expected: FAIL(`ImportError: cannot import name 'is_law_kb_name'`)。

- [ ] **Step 3: 写实现**

`backend/app/extensions/law/service.py` 顶部导入区追加(与既有 `from app.extensions.schemas` 无则新增一行;该文件目前未导入它):

```python
from app.extensions.schemas import DocumentResponse
```

(已有 `from sqlalchemy import func, select`、`from app.extensions.models import ... Law ...`,勿重复。)

文件尾部(`LawService` 类外,模块级)追加:

```python
# 法规标准系统库判定前缀 —— 种子名共享前缀(config.py → law.dataset_display_info
# 经 _ensure_kb_registered 注册);管理员重命名 KB 后识别失效(列表回退为空),
# 与前端 frontend/src/app/knowledge/_components/isLawKnowledgeBase.ts 同源同取舍。
LAW_KB_NAME_PREFIX = "法规标准库"

# laws.is_synced → DocumentResponse.status(DocStatusBadge 认识的三态)
_LAW_DOC_STATUS = {"synced": "success", "failed": "failed"}


def is_law_kb_name(name: str | None) -> bool:
    """知识库名是否为法规标准系统库(用于文件列表/chunks 的 laws 投影分支)。"""
    return bool(name) and name.startswith(LAW_KB_NAME_PREFIX)


def law_display_name(law: Law) -> str:
    """法规在文件列表中的展示名 —— 与 RAGFlow 文档名同源(无扩展名,展示用途)。"""
    meta = law.metadata_json or {}
    return build_ragflow_doc_name(meta.get("sector"), law.law_number, law.title, None)


def project_law_as_document(law: Law, kb_id) -> DocumentResponse:
    """单条 law → DocumentResponse 投影(只读视图,spec 2026-09-05)。"""
    return DocumentResponse(
        id=law.id,
        knowledge_base_id=kb_id,
        name=law_display_name(law),
        file_path="",  # 法规不落盘
        file_size=0,
        file_type=None,
        ragflow_document_id=law.ragflow_document_id,
        status=_LAW_DOC_STATUS.get(law.is_synced or "", "pending"),
        error_message=None,
        created_at=law.created_at,
    )


async def _law_projection_query(db: AsyncSession, dataset_id: str, skip: int, limit: int):
    base = select(Law).where(Law.ragflow_dataset_id == dataset_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = (
        await db.execute(base.order_by(Law.created_at.desc()).offset(skip).limit(limit))
    ).scalars().all()
    return rows, total


async def project_laws_as_documents(db: AsyncSession, kb, skip: int = 0, limit: int = 100):
    """法规库文件列表:按 ragflow_dataset_id 投影 laws 表 → (list[DocumentResponse], total)。

    单一真相源仍是 laws 表,实时计算,零迁移;普通库不走此路径。
    """
    rows, total = await _law_projection_query(db, kb.ragflow_dataset_id, skip, limit)
    return [project_law_as_document(law, kb.id) for law in rows], total
```

`LawService` 类体内(任意现有方法后,如 `get_template_laws` 之后)追加:

```python
    @staticmethod
    async def get_law_in_kb(db: AsyncSession, kb, doc_id) -> Law | None:
        """chunks 视图定位:doc_id 为 law.id,且必须属于该 KB 的 dataset。"""
        res = await db.execute(select(Law).where(Law.id == doc_id))
        law = res.scalar_one_or_none()
        if law is None or law.ragflow_dataset_id != kb.ragflow_dataset_id:
            return None
        return law
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_documents_projection.py -v
```

Expected: 6 passed。

- [ ] **Step 5: lint**

```bash
cd backend && make lint
```

Expected: 无新增告警(既有债务基线不变)。

- [ ] **Step 6: Commit(pathspec!)**

```bash
git add backend/app/extensions/law/service.py backend/tests/test_law_kb_documents_projection.py
git commit -m "feat(law): 法规库文件列表投影 helper(is_law_kb_name/project_laws_as_documents/get_law_in_kb)" -- backend/app/extensions/law/service.py backend/tests/test_law_kb_documents_projection.py
```

---

### Task 2: 路由接入(list_documents / list_document_chunks 法规分支)

**Files:**
- Modify: `backend/app/extensions/knowledge/routers.py`(:26 附近导入、:424-456 list_documents、:485-522 list_document_chunks)

- [ ] **Step 1: 加导入**

`from app.extensions.knowledge.service import (...)` 多行导入块结束后、`from app.extensions.models import ...` 之前(字母序 `app.extensions.law` < `app.extensions.models`)插入:

```python
from app.extensions.law.service import LawService, is_law_kb_name
```

- [ ] **Step 2: list_documents 法规分支**

在 `_load_kb_scoped` 404 检查之后、`docs, total = await DocumentService.list_docs(...)` 之前插入,并把该行与其后 processing 轮询段、return 行包进 `else:`(缩进整体不变,仅在其前加分支;实际改法如下):

```python
    # EAI-CUSTOM: 法规标准系统库无 documents 表记录(法规只写 laws 表),
    # 文件列表实时投影 laws(spec 2026-09-05);投影状态取自 is_synced,无需 RAGFlow 轮询。
    if is_law_kb_name(kb.name):
        documents, total = await LawService.project_laws_as_documents(db, kb, skip=skip, limit=limit)
        return DocumentListResponse(documents=documents, total=total)

    docs, total = await DocumentService.list_docs(db, kb_id, skip=skip, limit=limit)
```

(其后既有 processing 轮询段与 `return DocumentListResponse(documents=[DocumentService.to_response(d) ...])` 保持不动。)

- [ ] **Step 3: list_document_chunks 法规分支**

把既有「取 doc」两行(500-502):

```python
    doc = await DocumentService.get_doc_by_id(db, doc_id)
    if not doc or doc.knowledge_base_id != kb.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not kb.ragflow_dataset_id or not doc.ragflow_document_id:
        return {"total": 0, "chunks": [], "message": "Document not synced to RAGFlow or not yet parsed"}
```

替换为:

```python
    # EAI-CUSTOM: 法规标准系统库 doc_id 为 law.id,投影到 RAGFlow chunk 查询(spec 2026-09-05)
    if is_law_kb_name(kb.name):
        law = await LawService.get_law_in_kb(db, kb, doc_id)
        if law is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        ragflow_document_id = law.ragflow_document_id
    else:
        doc = await DocumentService.get_doc_by_id(db, doc_id)
        if not doc or doc.knowledge_base_id != kb.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        ragflow_document_id = doc.ragflow_document_id
    if not kb.ragflow_dataset_id or not ragflow_document_id:
        return {"total": 0, "chunks": [], "message": "Document not synced to RAGFlow or not yet parsed"}
```

其后既有 RAGFlow 调用段把 `document_id=doc.ragflow_document_id` 改为 `document_id=ragflow_document_id`(list_chunks 调用参数,一行)。

- [ ] **Step 4: 全量验证**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_documents_projection.py tests/test_law_kb_registration.py tests/test_law_kb_seed.py -v && make lint
```

Expected: 全部 passed,lint 无新增告警。

- [ ] **Step 5: Commit(pathspec!)**

```bash
git commit -m "feat(knowledge): 法规库 documents/chunks 端点接入 laws 投影分支" -- backend/app/extensions/knowledge/routers.py
```

(文件已 Step1-3 改完,直接 pathspec 提交;若 git 提示无暂存,先 `git add backend/app/extensions/knowledge/routers.py`。)

---

### Task 3: 前端(卡片按钮 disabled + 行内删除隐藏)

**Files:**
- Modify: `frontend/src/app/knowledge/page.tsx`(卡片按钮区,约 405-537 行)
- Modify: `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`(行内删除按钮,约 576-586 行)

- [ ] **Step 1: page.tsx 导入 + flag**

相对/内部导入区加(按 ESLint 字母序,`@/core/permissions` 附近的 internal 组之后、相对导入组):

```tsx
import { isLawKnowledgeBase } from "./_components/isLawKnowledgeBase";
```

卡片 map 内(`const isSyncing = syncingIds.has(kb.id);` 之后)加:

```tsx
                const isLawKb = isLawKnowledgeBase(kb.name);
```

- [ ] **Step 2: 三按钮 disabled + title**

同步状态按钮(约 498-512)改为:

```tsx
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => handleSync(kb.id, e)}
                          disabled={isSyncing || isLawKb}
                          className="text-muted-foreground hover:bg-primary/10 hover:text-primary"
                          title={isLawKb ? "法规标准系统库,请在 知识工厂 → 法规标准 中管理" : "同步状态"}
                        >
```

编辑按钮(约 514-524):`disabled={isLawKb}` 加进 Button,title 同样按 isLawKb 切换为提示文案(原标题"编辑")。

删除按钮(约 526-536):同上,`disabled={isLawKb}` + title 提示(原标题"删除")。

- [ ] **Step 3: KnowledgeBaseDetail 行内删除隐藏**

行内删除按钮(约 576-586)gate 改为:

```tsx
                          {/* EAI-CUSTOM: gate doc-delete button by kb:delete permission;
                              法规标准系统库文档为 laws 投影,删除会造成 laws.ragflow_document_id 悬空 */}
                          {can("kb:delete") && !isLawKb && (
```

(按钮 JSX 本体不变;chunks 查看保持可用。)

- [ ] **Step 4: 静态检查**

```bash
cd frontend && pnpm exec eslint src/app/knowledge/page.tsx src/app/knowledge/_components/KnowledgeBaseDetail.tsx && pnpm exec prettier --check src/app/knowledge/page.tsx src/app/knowledge/_components/KnowledgeBaseDetail.tsx && pnpm typecheck && pnpm test tests/unit/app/knowledge/_components/isLawKnowledgeBase.test.ts
```

Expected: 全 clean、测试 2/2。

- [ ] **Step 5: Commit(pathspec!)**

```bash
git add frontend/src/app/knowledge/page.tsx frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx
git commit -m "feat(knowledge): 法规库卡片按钮disabled+详情行内删除隐藏" -- frontend/src/app/knowledge/page.tsx frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx
```

---

### Task 4: 容器验证(E2E)

**Files:** 无代码改动。

- [ ] **Step 1: 重启 gateway(后端代码变更)**

```bash
docker compose -p eai-docker restart gateway
```

- [ ] **Step 2: 浏览器验证**(superpowers-chrome,admin@eai-flow.com / Admin@2026,入口 http://localhost:2026)

1. `/knowledge`:两个法规库卡片的 同步状态/编辑/删除 三按钮 disabled(hover 提示文案),**点卡片本体仍能进详情**;
2. 法规库详情:文件列表显示法规记录(如「【地质勘查】DZ/T 0033-2020 固体矿产地质勘查报告编写规范」),状态徽章绿色(已同步),行内无删除按钮;
3. 点文件行/查看按钮 → ChunkModal 打开且有 chunks 内容;
4. 普通库(如 合同知识库):列表与删除/chunks 行为如常;
5. 知识工厂 → 法规标准 不受影响。

- [ ] **Step 3: 收尾**

- OpenWolf:`.wolf/memory.md` 一行、`.wolf/anatomy.md`(新测试文件)、buglog(若 E2E 发现问题)。
- 回滚方式:两个功能 commit 各自 revert。

---

## Self-Review 记录

- **Spec coverage:** §2.1→Task 3 Step 1-2;§2.2 helper→Task 1、list 分支→Task 2 Step 2、chunks 分支→Task 2 Step 3;§2.3→Task 3 Step 3;§4 测试→Task 1 Step 1/4、Task 2 Step 4、Task 4。§1②零改动(已在 spec 说明)。✓
- **Placeholder scan:** 无 TBD/TODO;所有代码步骤含完整代码。✓
- **Type consistency:** `is_law_kb_name`/`project_laws_as_documents`/`get_law_in_kb` 命名在 Task 1 定义、Task 2 使用一致;`isLawKb` 前端两文件各自定义;`project_law_as_document` 被 `project_laws_as_documents` 内部调用一致。✓
- 注意:Task 1 测试中 `docs[1].status == "pending"` 依赖 laws 顺序 = `created_at` 同值时按插入序,两 law created_at 相同 —— 断言用 status 而非顺序,不受排序影响。✓
