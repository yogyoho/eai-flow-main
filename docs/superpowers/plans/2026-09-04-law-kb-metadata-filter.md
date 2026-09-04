# 法规标准 KB 对话/检索按表单字段过滤 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 知识库对话与联邦检索接口支持可选 `filters`(行业领域/标准号/关键词/生效日期区间),经 RAGFlow `metadata_condition` 文档过滤 + `document_ids` 收敛检索,实现按表单字段过滤。

**Architecture:** 纯函数 `build_metadata_condition`(filters→RAGFlow metadata_condition,白名单校验)+ 编排函数 `filter_doc_ids`(文档列表过滤→ids,>100 截断)→ client 两参数扩展(`list_documents` 透传 metadata_condition;`chat` 的 `doc_ids` 更名 `document_ids` 并真正生效)→ 两个路由接入(filters 参数、响应回显、RAGFlow 拒绝时降级无过滤)。

**Tech Stack:** FastAPI + httpx(RAGFlow v0.27.1 REST)+ pytest(现有 httpx.MockTransport 测试模式)。

**Spec:** `docs/superpowers/specs/2026-09-04-law-kb-metadata-filter-design.md`

**现场事实(执行者必读):**
- RAGFlow v0.27.1:文档列表端点支持 `metadata_condition` query 参数(**实测精准生效**);`POST /retrieval` 会**静默忽略** `meta_data_filter`(实测)——所以本计划用两段式,绝不让检索端点直接收 meta 过滤。
- `metadata_condition` 结构:`{"logic": "and", "conditions": [{"name": <meta_fields键>, "comparison_operator": <is|contains|≥|≤|...>, "value": str}]}`。操作符已实测:`is`/`contains`(列表字段)/`≥`/`≤`/and 组合全部精准。
- `effective_date` 在 meta_fields 中是 `%Y-%m-%d` 字符串,字典序比较即日期序(实测 ✓)。
- 检索 `document_ids` 上限 100(v0.27 约束)→ 编排层 >100 截断 + 标记。
- 前端 `KnowledgeBaseDetail.tsx` 读取 chat 响应的 `answer` 键(恒空串)——**响应键必须保留**,只删后端对 `data.answer` 的死读取。
- 客户端 `chat` 的 `doc_ids` 参数当前无任何调用方传值(全仓 grep 确认),重命名为 `document_ids` 零破坏。
- 后端跑在 Docker;改后端代码后 `docker compose -p eai-docker restart gateway`;测试在宿主机 `cd backend && PYTHONPATH=. uv run pytest`。
- **并发警告**:`git add` 只加本任务列出的文件,绝不 `-A`。

**测试文件命名偏差说明:** spec 写 `tests/test_law_kb_metadata_filter.py`,实际用 `tests/test_kb_metadata_filter.py`(过滤属 knowledge 模块而非 law 模块,命名更准确)。

---

### Task 1: `build_metadata_condition` 纯函数(knowledge/service.py,TDD)

**Files:**
- Modify: `backend/app/extensions/knowledge/service.py`(模块级,`KnowledgeBaseService` 类之前)
- Test: `backend/tests/test_kb_metadata_filter.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_kb_metadata_filter.py`:

```python
"""build_metadata_condition(filters→RAGFlow metadata_condition)单测。"""
import pytest

from app.extensions.knowledge.service import build_metadata_condition


def test_none_and_empty():
    assert build_metadata_condition(None) is None
    assert build_metadata_condition({}) is None
    assert build_metadata_condition({"sector": ""}) is None
    assert build_metadata_condition({"keywords": []}) is None


def test_sector_is():
    assert build_metadata_condition({"sector": "环境评价"}) == {
        "logic": "and",
        "conditions": [{"name": "sector", "comparison_operator": "is", "value": "环境评价"}],
    }


def test_law_number_is():
    assert build_metadata_condition({"law_number": "HJ 130-2019"}) == {
        "logic": "and",
        "conditions": [{"name": "law_number", "comparison_operator": "is", "value": "HJ 130-2019"}],
    }


def test_keywords_expanded_to_contains():
    out = build_metadata_condition({"keywords": ["规划环评", "三线一单"]})
    assert out == {
        "logic": "and",
        "conditions": [
            {"name": "keywords", "comparison_operator": "contains", "value": "规划环评"},
            {"name": "keywords", "comparison_operator": "contains", "value": "三线一单"},
        ],
    }


def test_date_range_ge_le():
    out = build_metadata_condition({"effective_date_from": "2009-01-01", "effective_date_to": "2015-12-31"})
    assert out == {
        "logic": "and",
        "conditions": [
            {"name": "effective_date", "comparison_operator": "≥", "value": "2009-01-01"},
            {"name": "effective_date", "comparison_operator": "≤", "value": "2015-12-31"},
        ],
    }


def test_combined_order():
    out = build_metadata_condition({"sector": "环境评价", "law_number": "HJ 130-2019"})
    assert out["logic"] == "and"
    assert out["conditions"] == [
        {"name": "sector", "comparison_operator": "is", "value": "环境评价"},
        {"name": "law_number", "comparison_operator": "is", "value": "HJ 130-2019"},
    ]


def test_unknown_key_raises():
    with pytest.raises(ValueError, match="unsupported filter key"):
        build_metadata_condition({"hacker": "x"})


def test_whitespace_sector_treated_as_absent():
    assert build_metadata_condition({"sector": "   "}) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kb_metadata_filter.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_metadata_condition'`

- [ ] **Step 3: 实现**(knowledge/service.py 模块级,`KnowledgeBaseService` 类之前)

```python
_METADATA_FILTER_KEYS = ("sector", "law_number", "keywords", "effective_date_from", "effective_date_to")


def build_metadata_condition(filters: dict | None) -> dict | None:
    """导入表单字段过滤 → RAGFlow metadata_condition。

    - 只接受白名单键(其余抛 ValueError,由路由层转 400)
    - 空值(空串/空列表/全空白)视为未提供;全部未提供时返回 None(不过滤)
    - keywords 列表逐项展开为 contains 条件
    - effective_date_from/to 映射为对 effective_date 的 ≥/≤ 条件
    """
    filters = filters or {}
    unknown = set(filters) - set(_METADATA_FILTER_KEYS)
    if unknown:
        raise ValueError(f"unsupported filter key(s): {sorted(unknown)}")

    conditions = []
    sector = (filters.get("sector") or "").strip()
    if sector:
        conditions.append({"name": "sector", "comparison_operator": "is", "value": sector})
    law_number = (filters.get("law_number") or "").strip()
    if law_number:
        conditions.append({"name": "law_number", "comparison_operator": "is", "value": law_number})
    for kw in filters.get("keywords") or []:
        kw = (kw or "").strip()
        if kw:
            conditions.append({"name": "keywords", "comparison_operator": "contains", "value": kw})
    date_from = (filters.get("effective_date_from") or "").strip()
    if date_from:
        conditions.append({"name": "effective_date", "comparison_operator": "≥", "value": date_from})
    date_to = (filters.get("effective_date_to") or "").strip()
    if date_to:
        conditions.append({"name": "effective_date", "comparison_operator": "≤", "value": date_to})

    if not conditions:
        return None
    return {"logic": "and", "conditions": conditions}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kb_metadata_filter.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/knowledge/service.py backend/tests/test_kb_metadata_filter.py
git commit -m "feat(knowledge): build_metadata_condition 过滤契约纯函数"
```

---

### Task 2: RAGFlowClient 扩展(list_documents metadata_condition + chat document_ids,TDD)

**Files:**
- Modify: `backend/app/extensions/knowledge/client.py`(:204-213 list_documents;:292-320 chat)
- Test: `backend/tests/test_knowledge_ragflow_client.py`(追加)

- [ ] **Step 1: 写失败测试(追加到 test_knowledge_ragflow_client.py)**

```python
@pytest.mark.asyncio
async def test_list_documents_passes_metadata_condition(install_transport):
    def handler(request):
        params = request.url.params
        assert "metadata_condition" in params
        import json as _json
        assert _json.loads(params["metadata_condition"])["conditions"][0]["name"] == "sector"
        return httpx.Response(200, json={"code": 0, "data": {"total": 0, "docs": []}})

    captured = install_transport(handler)
    cond = {"logic": "and", "conditions": [{"name": "sector", "comparison_operator": "is", "value": "环境评价"}]}
    await RAGFlowClient().list_documents("ds1", metadata_condition=cond, orderby="create_time", desc=True)
    params = dict(captured.requests[0].url.params)
    assert params["page"] == "1" and params["page_size"] == "100"
    assert params["orderby"] == "create_time" and params["desc"] == "true"


@pytest.mark.asyncio
async def test_chat_sends_document_ids(install_transport):
    def handler(request):
        return httpx.Response(200, json={"code": 0, "data": {"total": 0, "chunks": [], "doc_aggs": []}})

    captured = install_transport(handler)
    await RAGFlowClient().chat("ds1", "query", document_ids=["doc-1", "doc-2"])

    import json as _json
    body = _json.loads(captured.requests[0].read().decode())
    assert body["document_ids"] == ["doc-1", "doc-2"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_ragflow_client.py -k "metadata_condition or document_ids" -v`
Expected: FAIL — TypeError unexpected keyword `metadata_condition` / `document_ids`

- [ ] **Step 3: 实现**(knowledge/client.py)

`list_documents`(:246)改为:

```python
    async def list_documents(self, dataset_id: str, page: int = 1, size: int = 100, metadata_condition: dict | None = None, orderby: str | None = None, desc: bool | None = None) -> dict:
        """List documents in a dataset (``page_size`` capped at 100 upstream).

        metadata_condition: RAGFlow 元数据过滤(RAGFlow v0.27.x 文档列表端点已实测生效)。
        """
        params: dict = {"page": page, "page_size": min(size, 100)}
        if metadata_condition:
            params["metadata_condition"] = json.dumps(metadata_condition, ensure_ascii=False)
        if orderby:
            params["orderby"] = orderby
        if desc is not None:
            params["desc"] = "true" if desc else "false"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/documents",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()
```

`chat`(:292)签名 `doc_ids` 更名并更新 payload 键(已存在 `document_ids` 赋值,仅改参数名与 docstring):

```python
    async def chat(
        self,
        dataset_id: str | list[str],
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.2,
        vector_similarity_weight: float = 0.3,
        document_ids: list[str] | None = None,
    ) -> dict:
```

函数体内两处:`if document_ids: payload["document_ids"] = document_ids`(替换原 `doc_ids` 参数读取)。

- [ ] **Step 4: 全量回归(旧 doc_ids 用例改名)**

test_knowledge_ragflow_client.py 中既有 `test_chat_sends_document_ids_filter` 若以 `doc_ids=` 传参,改为 `document_ids=["doc-1", "doc-2"]`。

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_knowledge_ragflow_client.py tests/test_kb_metadata_filter.py -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/knowledge/client.py backend/tests/test_knowledge_ragflow_client.py
git commit -m "feat(knowledge): list_documents 元数据过滤透传 + chat document_ids 参数"
```

---

### Task 3: 编排函数 `filter_doc_ids`(knowledge/service.py,TDD)

**Files:**
- Modify: `backend/app/extensions/knowledge/service.py`(模块级)
- Test: `backend/tests/test_kb_metadata_filter.py`(追加)

- [ ] **Step 1: 写失败测试(追加)**

```python
class _FakeListRF:
    """list_documents 假件:返回 (ids, total) 预设页,记录 metadata_condition。"""

    def __init__(self, pages, total):
        self._pages = pages
        self._total = total
        self.seen_conditions = []

    async def list_documents(self, dataset_id, page=1, size=100, metadata_condition=None, orderby=None, desc=None):
        self.seen_conditions.append(metadata_condition)
        docs = [{"id": i} for i in self._pages[page - 1]]
        return {"data": {"docs": docs, "total": self._total}}


@pytest.mark.asyncio
async def test_filter_doc_ids_single_page_under_cap():
    from app.extensions.knowledge.service import filter_doc_ids
    rf = _FakeListRF([["a", "b", "c"]], 3)
    ids, truncated = await filter_doc_ids(rf, "ds-1", {"logic": "and", "conditions": []})
    assert ids == ["a", "b", "c"] and truncated is False


@pytest.mark.asyncio
async def test_filter_doc_ids_paginates_and_caps_at_100():
    from app.extensions.knowledge.service import filter_doc_ids
    pages = [[f"d{i:03d}" for i in range((p - 1) * 100, p * 100)] for p in (1, 2)]
    rf = _FakeListRF(pages, 150)
    ids, truncated = await filter_doc_ids(rf, "ds-1", {"logic": "and", "conditions": []})
    assert len(ids) == 100 and truncated is True
    assert len(rf.seen_conditions) == 1  # 装满 100 上限即停,不取第 2 页


@pytest.mark.asyncio
async def test_filter_doc_ids_exactly_100_not_truncated():
    from app.extensions.knowledge.service import filter_doc_ids
    rf = _FakeListRF([[f"d{i:03d}" for i in range(100)]], 100)
    ids, truncated = await filter_doc_ids(rf, "ds-1", {"logic": "and", "conditions": []})
    assert len(ids) == 100 and truncated is False  # 恰好 100 = 全命中,不算截断


@pytest.mark.asyncio
async def test_filter_doc_ids_zero_hits():
    from app.extensions.knowledge.service import filter_doc_ids
    rf = _FakeListRF([[]], 0)
    ids, truncated = await filter_doc_ids(rf, "ds-1", {"logic": "and", "conditions": []})
    assert ids == [] and truncated is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kb_metadata_filter.py -k filter_doc_ids -v`
Expected: FAIL — ImportError `filter_doc_ids`

- [ ] **Step 3: 实现**(service.py,`build_metadata_condition` 之后)

```python
_FILTER_DOC_CAP = 100  # v0.27 约束:检索 xxx_ids 数组上限 100


async def filter_doc_ids(rf_client, dataset_id: str, condition: dict) -> tuple[list[str], bool]:
    """按 metadata_condition 拉取命中文档 id;>100 截断并标记 truncated。"""
    ids: list[str] = []
    page = 1
    total = 0
    while page <= 20:  # 20 页 ×100 兜底,防病态 total
        res = await rf_client.list_documents(
            dataset_id, page=page, size=100, metadata_condition=condition,
            orderby="create_time", desc=True,  # 最新优先
        )
        docs = (res.get("data") or {}).get("docs", [])
        ids.extend(d.get("id") for d in docs if d.get("id"))
        total = (res.get("data") or {}).get("total") or total
        if not docs or len(ids) >= _FILTER_DOC_CAP:
            break
        if total and len(ids) >= total:
            break
        page += 1
    # 截断 = 触及上限且仍有剩余(total 未知/更大时,只要装满 100 即视为可能有截断)
    truncated = len(ids) >= _FILTER_DOC_CAP and (total == 0 or total > len(ids))
    return ids[:_FILTER_DOC_CAP], truncated
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kb_metadata_filter.py -v`
Expected: 13 passed(9 + 1 consistency 之外的新 4 个;按实际计数报告)

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/knowledge/service.py backend/tests/test_kb_metadata_filter.py
git commit -m "feat(knowledge): filter_doc_ids 编排(元数据过滤→ids,100 截断)"
```

---

### Task 4: 路由接入(chat + search filters 参数、响应字段、降级)

**Files:**
- Modify: `backend/app/extensions/schemas.py:529-535`(RAGChatRequest)、:545-551(RAGFederatedSearchRequest)、:554+(RAGFederatedSearchResponse)
- Modify: `backend/app/extensions/knowledge/routers.py:520-565`(chat)、:568-656(search)

- [ ] **Step 1: schemas 加 filters 与响应字段**

`RAGChatRequest`(:529)加:

```python
    filters: dict | None = Field(default=None, description="元数据过滤:{sector, law_number, keywords[], effective_date_from/to}")
```

`RAGFederatedSearchRequest`(:545)加同一行。`RAGFederatedSearchResponse`(:554)加:

```python
    filters_applied: dict | None = None
    filters_truncated: bool = False
```

- [ ] **Step 2: chat 处理器接入**(routers.py:520-565)

`request.filters` 参与编排;`data.answer` 死读取删除(响应键 `"answer": ""` 保留——前端 KnowledgeBaseDetail.tsx 读取该键):

```python
    try:
        rf_client = RAGFlowClient()
        params = KnowledgeBaseService.resolve_chat_params(request.top_k, request.similarity_threshold, request.vector_similarity_weight, kb.retrieval_config)

        condition = None
        try:
            condition = build_metadata_condition(request.filters)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        document_ids: list[str] | None = None
        filters_truncated = False
        if condition:
            document_ids, filters_truncated = await filter_doc_ids(rf_client, kb.ragflow_dataset_id, condition)
            if not document_ids:
                return {
                    "answer": "",
                    "sources": [],
                    "filters_applied": condition,
                    "filters_truncated": False,
                    "message": "过滤条件下无匹配文档",
                }

        result = await rf_client.chat(
            dataset_id=kb.ragflow_dataset_id,
            query=request.query,
            document_ids=document_ids,
            **params,
        )

        if result.get("code") != 0:
            msg = result.get("message", "RAGFlow retrieval failed")
            logger.error(f"RAGFlow chat error (code={result.get('code')}): {msg}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        data = result.get("data") or {}
        return {
            "answer": "",
            "sources": data.get("chunks", []),
            "filters_applied": condition,
            "filters_truncated": filters_truncated,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAGFlow chat error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
```

routers.py 顶部 service 导入补 `build_metadata_condition, filter_doc_ids`(knowledge/service 的导入行现状确认后追加)。

- [ ] **Step 3: search 处理器接入**(routers.py:568-656)

`RAGFederatedSearchRequest.filters` 同样处理。在 `rf_client = RAGFlowClient()`(:612)之后、tasks 组装之前:

```python
    condition = None
    try:
        condition = build_metadata_condition(request.filters)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    filters_truncated = False
    per_kb_ids: dict[UUID, list[str] | None] = {}
    if condition:
        for kb in kb_list:
            try:
                ids, trunc = await filter_doc_ids(rf_client, kb.ragflow_dataset_id, condition)
                per_kb_ids[kb.id] = ids
                filters_truncated = filters_truncated or trunc
            except Exception as e:
                # 降级:该库不过滤(整库检索),保证可用性
                logger.warning(f"metadata 过滤失败,降级整库检索 kb={kb.id}: {e}")
                per_kb_ids[kb.id] = None
```

tasks 组装改为(逐库传 document_ids;零命中库跳过):

```python
    tasks = []
    kb_for_task = []
    for kb in kb_list:
        ids = per_kb_ids.get(kb.id)
        if condition and ids is not None and not ids:
            continue  # 该库零命中,跳过
        tasks.append(
            rf_client.chat(
                dataset_id=kb.ragflow_dataset_id,
                query=request.query,
                top_k=request.per_kb_k,
                document_ids=ids,
            )
        )
        kb_for_task.append(kb)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    kb_list, results = kb_for_task, results
```

(其后 chunks 归并逻辑不变;`zip(kb_list, results)` 依赖 tasks 与 kb_list 对齐——重构后用 `kb_for_task`。)响应改:

```python
    return RAGFederatedSearchResponse(
        sources=chunks[: request.top_k],
        filters_applied=condition,
        filters_truncated=filters_truncated,
    )
```

注意:`condition` 非 None 但部分库降级为 None 时,`filters_applied` 仍回显 condition(部分库生效),`filters_truncated` 汇总。

- [ ] **Step 4: 回归 + lint**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_kb_metadata_filter.py tests/test_knowledge_ragflow_client.py tests/test_law_kb_seed.py -q && uv run ruff check app/extensions/knowledge/ app/extensions/schemas.py && uv run ruff format --check app/extensions/knowledge/`
Expected: 全 PASS / clean

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/schemas.py backend/app/extensions/knowledge/routers.py
git commit -m "feat(knowledge): KB 对话/检索接入 filters 元数据过滤(两段式+降级)"
```

---

### Task 5: 线上验证(控制者执行)

- [ ] **Step 1:** `docker compose -p eai-docker restart gateway`,等待就绪(POST /login 非 502)
- [ ] **Step 2:** 无过滤回归:chat/search 不带 filters → 行为与现状一致(chunks 正常、无 filters_applied 字段差异)
- [ ] **Step 3:** sector 过滤:`{"query": "...", "filters": {"sector": "环境评价"}}` → sources 只来自【环境评价】文档
- [ ] **Step 4:** 零命中:`{"filters": {"sector": "不存在行业"}}` → 空 sources + message
- [ ] **Step 5:** 组合:`{"filters": {"sector": "环境评价", "effective_date_to": "2010-06-30"}}` → 仅 HJ 463
- [ ] **Step 6:** 幂等回归:`cd backend && PYTHONPATH=. uv run pytest tests/ -q` 全量(排除已知既有失败)
- [ ] **Step 7:** 有修正则提交,无则结束;OpenWolf memory 记录

