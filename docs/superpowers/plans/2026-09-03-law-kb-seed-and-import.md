# 法规标准 tab:种子配置幂等对齐 + 导入行业领域 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** init-ragflow 用实测最优种子配置幂等收敛两个法规知识库;导入新法规链路支持「行业领域」字段自动生成 RAGFlow 文档名前缀。

**Architecture:** 种子常量 `_KB_SEED_CONFIG` 存 law/service.py(单一真相源,派生兼容别名);init-ragflow 重写为 幂等收敛(受限键比对→PUT);行业领域复用既有 `LawCreate.sector` 字段(走 metadata_json,零 DDL),文档名由后端单点 `build_ragflow_doc_name` 组装。

**Tech Stack:** FastAPI + httpx(RAGFlow v0.27.1 REST)、React 19 + TanStack Query、pytest。

**Spec:** `docs/superpowers/specs/2026-09-03-law-kb-seed-and-import-design.md`

**Spec 偏差(计划期发现,已回写 spec):**「行业领域」复用既有 `LawCreate.sector` 字段(存 metadata_json.sector,读写链路已通),**不新增** `laws.industry` 列——零 DDL,且 law_type 已占用 "industry" 值(行业标准),避免语义撞名。

**现场事实(执行者必读):**
- RAGFlow API:文档状态轮询必须用列表端点 `GET /api/v1/datasets/{ds}/documents?id=...`(`GET /documents/{doc_id}` 是文件下载);`DELETE /datasets/{ds}/chunks` 带 document_ids 会**删文档**;文档改名 PATCH 必须保持扩展名。
- 后端跑在 Docker(`deer-flow-gateway`),改后端代码要 `docker compose -p eai-docker restart gateway`;测试在宿主机 `cd backend && PYTHONPATH=. uv run pytest`。
- `LawBase.sector` 字段已存在(存 metadata_json.sector,service.py:401/451 已有读写),「行业领域」直接复用,**不改表**。

---

### Task 1: 种子常量 + 文档名组装器(service.py,TDD)

**Files:**
- Modify: `backend/app/extensions/law/service.py`(行 46-63 附近:RAGFLOW_KB_MAPPING/_LAW_CHUNK_METHOD/过时注释;行 534/547:upload_name)
- Test: `backend/tests/test_law_kb_seed.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_law_kb_seed.py`:

```python
"""laws-standards/legal 种子配置与 RAGFlow 文档名组装器单测。"""
import pytest

from app.extensions.law.service import LawService, build_ragflow_doc_name

pytestmark = pytest.mark.asyncio


class TestBuildRagflowDocName:
    def test_full(self):
        assert build_ragflow_doc_name("环境评价", "HJ 130-2019", "规划环评总纲", "pdf") == \
            "【环境评价】HJ 130-2019 规划环评总纲.pdf"

    def test_no_industry(self):
        assert build_ragflow_doc_name(None, "GB 3095-2012", "环境空气质量标准", "docx") == \
            "GB 3095-2012 环境空气质量标准.docx"

    def test_no_law_number(self):
        assert build_ragflow_doc_name("地质勘查", None, "勘查规范", "txt") == "【地质勘查】勘查规范.txt"

    def test_neither(self):
        assert build_ragflow_doc_name(None, None, "水法", "docx") == "水法.docx"

    def test_long_title_not_truncated(self):
        title = "超" * 300
        assert build_ragflow_doc_name("地质勘查", "DZ 1", title, "pdf").endswith(title + ".pdf")


class TestKbSeedConfig:
    def test_both_kbs_present(self):
        assert set(LawService.KB_SEED_CONFIG) == {"ragflow-laws-legal", "ragflow-laws-standards"}

    def test_legal_uses_laws(self):
        seed = LawService.KB_SEED_CONFIG["ragflow-laws-legal"]
        assert seed["chunk_method"] == "laws"
        assert seed["parser_config"]["layout_recognize"] == "DeepDOC"
        assert seed["parser_config"]["auto_keywords"] == 0

    def test_standards_uses_naive384(self):
        seed = LawService.KB_SEED_CONFIG["ragflow-laws-standards"]
        assert seed["chunk_method"] == "naive"
        pc = seed["parser_config"]
        assert pc["chunk_token_num"] == 384
        assert pc["delimiter"] == "\n。！？；"
        assert pc["delimiter"].startswith("\n")  # 真实换行符,不是字面反斜杠
        assert pc["layout_recognize"] == "DeepDOC"
        assert pc["html4excel"] is True
        assert pc["auto_keywords"] == 0 and pc["auto_questions"] == 0
        assert pc["enable_children"] is False
        assert "use_parent_child" not in pc  # 非 REST 合法键

    def test_legacy_groups_derived_from_seed(self):
        from app.extensions.law.service import RAGFLOW_DATASET_GROUPS
        assert RAGFLOW_DATASET_GROUPS["ragflow-laws-standards"] == "naive"
        assert RAGFLOW_DATASET_GROUPS["ragflow-laws-legal"] == "laws"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_seed.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_ragflow_doc_name'`

- [ ] **Step 3: 实现**(service.py)

模块级(app/extensions/law/service.py,替换行 46-63 附近的 `RAGFLOW_DATASET_GROUPS` 定义与过时注释,`RAGFLOW_KB_MAPPING`/`_LAW_CHUNK_METHOD` 保留):

```python
_KB_SEED_CONFIG: dict[str, dict] = {
    # 法律/法规/规章(第X条文体):A/B-4 实测 laws 每条一块+章路径最优;laws 无 chunk_token_num 旋钮
    "ragflow-laws-legal": {
        "chunk_method": "laws",
        "parser_config": {"layout_recognize": "DeepDOC", "auto_keywords": 0, "auto_questions": 0},
    },
    # 标准/规范:A/B-1 实测 naive-384 最优(docs/superpowers/specs/2026-09-03-law-kb-seed-and-import-design.md)
    "ragflow-laws-standards": {
        "chunk_method": "naive",
        "parser_config": {
            "chunk_token_num": 384,
            "delimiter": "\n。！？；",  # 首字符为真实换行符;API 不做 unicode_escape
            "layout_recognize": "DeepDOC",
            "html4excel": True,
            "auto_keywords": 0,
            "auto_questions": 0,
            "enable_children": False,
            "tag_kb_ids": [],  # init 时解析「行业标签集」后填充(见 routers.init_ragflow_knowledge_bases)
            "topn_tags": 3,
        },
    },
}

# 兼容别名:旧引用点(routers/service 循环)继续可用,单一真相源是 _KB_SEED_CONFIG
RAGFLOW_DATASET_GROUPS = {name: cfg["chunk_method"] for name, cfg in _KB_SEED_CONFIG.items()}
```

模块级函数(放在 `_LAW_CHUNK_METHOD` 之后、`LawService` 类之前):

```python
def build_ragflow_doc_name(industry: str | None, law_number: str | None, title: str, ext: str) -> str:
    """组装 RAGFlow 文档名:【行业】标准号 标题.ext(行业/标准号可缺省)。"""
    parts = f"【{industry}】" if industry else ""
    num = f"{law_number} " if law_number else ""
    return f"{parts}{num}{title}.{ext}"
```

`LawService` 类内加类属性(与 `_CHUNK_METHOD_TO_PARSER` 同区域):

```python
    KB_SEED_CONFIG = _KB_SEED_CONFIG
```

同时把 `_LAW_CHUNK_METHOD` 上方过时注释块(“RAGFlow分块策略映射: 标准/规范 → manual parser…”与“parser_config 不在此处设置…512”)替换为:

```python
# RAGFlow分块策略映射: law_type -> chunk_method
# 法律/法规/规章 → laws(第X条结构,A/B-4 实测最优);标准/规范 → naive(A/B-1 实测最优)
# 分块参数以 _KB_SEED_CONFIG 为单一真相源,随 init-ragflow 幂等收敛到库上
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_seed.py -v`
Expected: 9 passed

- [ ] **Step 5: 回归既有 law 测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_registration.py tests/test_knowledge_ragflow_client.py -q`
Expected: 全部 PASS(若有失败,检查是否破坏了既有 import/fake)

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/law/service.py backend/tests/test_law_kb_seed.py
git commit -m "feat(law): _KB_SEED_CONFIG 种子常量+文档名组装器(设计A/B 基础)——bug-3077 后续"
```

---

### Task 2: init-ragflow 幂等收敛 + industries 端点(routers.py + schemas.py,TDD)

**Files:**
- Modify: `backend/app/extensions/law/routers.py:114-181`(init 重写)、`backend/app/extensions/law/schemas.py:148-156`(响应模型)、routers 尾部(industries 端点)
- Modify: `backend/app/extensions/law/service.py`(seed diff 纯函数,类外)
- Test: `backend/tests/test_law_kb_seed.py`(追加)

- [ ] **Step 1: 写失败测试(追加到 test_law_kb_seed.py)**

```python
from app.extensions.law.service import seed_config_diff


class TestSeedConfigDiff:
    SEED = {"chunk_method": "naive", "parser_config": {"chunk_token_num": 384, "layout_recognize": "DeepDOC"}}

    def test_identical(self):
        cur = {"chunk_method": "naive", "parser_config": {"chunk_token_num": 384, "layout_recognize": "DeepDOC", "auto_keywords": 0}}
        assert seed_config_diff(cur, self.SEED) == {}

    def test_method_drift(self):
        diff = seed_config_diff({"chunk_method": "manual", "parser_config": {}}, self.SEED)
        assert diff["chunk_method"] == ("manual", "naive")

    def test_value_drift(self):
        diff = seed_config_diff({"chunk_method": "naive", "parser_config": {"chunk_token_num": 512}}, self.SEED)
        assert diff["parser_config.chunk_token_num"] == (512, 384)

    def test_missing_seed_key(self):
        diff = seed_config_diff({"chunk_method": "naive", "parser_config": {}}, self.SEED)
        assert diff["parser_config.layout_recognize"] == (None, "DeepDOC")

    def test_extra_current_keys_ignored(self):
        cur = {"chunk_method": "naive", "parser_config": {"chunk_token_num": 384, "layout_recognize": "DeepDOC", "some_upstream_default": 1}}
        assert seed_config_diff(cur, self.SEED) == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_seed.py -k diff -v`
Expected: FAIL — `ImportError: cannot import name 'seed_config_diff'`

- [ ] **Step 3: 实现 seed_config_diff**(service.py,`build_ragflow_doc_name` 之后)

```python
def seed_config_diff(current: dict, seed: dict) -> dict:
    """比较现库配置与种子,返回 {键路径: (现值, 种子值)};只比对种子中出现的键。"""
    diff: dict = {}
    if current.get("chunk_method") != seed.get("chunk_method"):
        diff["chunk_method"] = (current.get("chunk_method"), seed.get("chunk_method"))
    cur_pc = current.get("parser_config") or {}
    for key, want in (seed.get("parser_config") or {}).items():
        got = cur_pc.get(key)
        if got != want:
            diff[f"parser_config.{key}"] = (got, want)
    return diff
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_seed.py -v`
Expected: 14 passed

- [ ] **Step 5: 改 schemas.py 响应模型**

`RAGFlowInitResponse`(schemas.py:148-156)改为:

```python
class RAGFlowInitResponse(BaseModel):
    """RAGFlow initialization response."""

    success: bool = True
    message: str = ""
    created: list[str] = Field(default_factory=list)
    aligned: list[str] = Field(default_factory=list, description="已存在且配置与种子一致")
    updated: list[str] = Field(default_factory=list, description="已存在但配置漂移,已 PUT 收敛")
    diffs: dict[str, dict] = Field(default_factory=dict, description="{kb: {键路径: [现值, 种子值]}}")
    already_exists: list[str] = Field(default_factory=list, description="已废弃,恒为空,兼容旧前端类型")
    failed: list[dict[str, str]] = Field(default_factory=list)
    registered: list[str] = Field(default_factory=list)
```

- [ ] **Step 6: 重写 init 循环**(routers.py:143-181)

routers.py:143 的导入行改为 `from .service import _KB_SEED_CONFIG, RAGFLOW_DATASET_GROUPS, RAGFLOW_KB_MAPPING`;第 146-152 行的类型→库映射逻辑不变;**第 154-181 行替换为**:

```python
    results = {"created": [], "aligned": [], "updated": [], "diffs": {}, "already_exists": [], "failed": [], "registered": []}

    # 行业标签集:存在则绑定到 standards 种子(块级贴标 v0.27.1 实测未生效,绑定无害、上游修复即用)
    industry_tag_ids: list[str] = []
    try:
        tag_ds = await rf_client.get_dataset_by_name("行业标签集")
        if tag_ds:
            industry_tag_ids = [tag_ds["id"]]
    except Exception as e:
        logger.warning("解析行业标签集失败(忽略): %s", e)

    for kb_name, chunk_method in datasets_to_init.items():
        try:
            seed = dict(_KB_SEED_CONFIG[kb_name])
            if kb_name == "ragflow-laws-standards" and industry_tag_ids:
                seed["parser_config"] = {**seed["parser_config"], "tag_kb_ids": industry_tag_ids}

            existing = await rf_client.get_dataset_by_name(kb_name)
            if existing:
                dataset_id = existing.get("id")
                cur = await rf_client.get_dataset(dataset_id)
                cur_data = cur.get("data") or {}
                diff = seed_config_diff(cur_data, seed)
                if diff:
                    await rf_client.update_dataset(
                        dataset_id,
                        chunk_method=seed["chunk_method"],
                        parser_config=seed["parser_config"],
                    )
                    results["updated"].append(kb_name)
                    results["diffs"][kb_name] = {k: list(v) for k, v in diff.items()}
                    logger.info("知识库配置已收敛到种子: %s diff=%s", kb_name, diff)
                else:
                    results["aligned"].append(kb_name)
            else:
                result = await rf_client.create_dataset(
                    name=kb_name,
                    description=f"法规标准库 - {kb_name}",
                    chunk_method=seed["chunk_method"],
                    parser_config=seed["parser_config"],
                )
                results["created"].append(kb_name)
                dataset_id = result.get("data", {}).get("id")
                logger.info(f"创建RAGFlow知识库成功: {kb_name} (chunk_method={seed['chunk_method']})")

            if dataset_id:
                registered = await LawService._ensure_kb_registered(db, current_user.id, kb_name, dataset_id, chunk_method)
                if registered:
                    results["registered"].append(kb_name)
        except Exception as e:
            results["failed"].append({"kb": kb_name, "error": str(e)})
            logger.error(f"初始化RAGFlow知识库失败: {kb_name} - {e}")

    return RAGFlowInitResponse(**results)
```

同文件顶部导入区补 `from .service import seed_config_diff`(与 143 行合并为一行:`from .service import _KB_SEED_CONFIG, RAGFLOW_DATASET_GROUPS, RAGFLOW_KB_MAPPING, seed_config_diff`)。

- [ ] **Step 7: industries 端点**(routers.py,init 端点之后追加)

```python
@router.get("/industries")
async def list_industries():
    """行业领域候选(来自 RAGFlow「行业标签集」的标签名)。标签集不存在时返回空列表。"""
    from app.extensions.knowledge.client import RAGFlowClient

    rf_client = RAGFlowClient()
    try:
        tag_ds = await rf_client.get_dataset_by_name("行业标签集")
        if not tag_ds:
            return {"industries": []}
    except Exception as e:
        logger.warning("行业标签集读取失败: %s", e)
        return {"industries": []}

    # 标签块按文档列出后聚合 tag_kwd
    industries: list[str] = []
    docs = (await rf_client.list_documents(tag_ds["id"])).get("data", {}).get("docs", [])
    for doc in docs:
        r = await rf_client.list_chunks(tag_ds["id"], doc["id"], page=1, size=100)
        for ch in (r.get("data") or {}).get("chunks", []):
            for t in ch.get("tag_kwd") or []:
                if t and t not in industries:
                    industries.append(t)
    return {"industries": industries}
```

> 注意:该端点沿用 client 既有方法(list_documents/list_chunks),不新增 client 方法。

- [ ] **Step 8: 跑全部相关测试 + lint**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_seed.py tests/test_law_kb_registration.py -q && uv run ruff check app/extensions/law/`
Expected: PASS / All checks passed

- [ ] **Step 9: Commit**

```bash
git add backend/app/extensions/law/routers.py backend/app/extensions/law/schemas.py backend/app/extensions/law/service.py backend/tests/test_law_kb_seed.py
git commit -m "feat(law): init-ragflow 幂等收敛到种子配置 + industries 端点"
```

---

### Task 3: 导入链路 sector(后端)

**Files:**
- Modify: `backend/app/extensions/law/routers.py:279-300`(import_law_with_file 表单参数)
- Modify: `backend/app/extensions/law/service.py:534-556`(sync upload_name 组装)
- Test: `backend/tests/test_law_kb_seed.py`(追加 builder 边界已覆盖;此处仅回归)

- [ ] **Step 1: import 端点加 sector 表单参数**

`import_law_with_file`(routers.py:279)参数区 `referred_laws` 行之后加:

```python
    sector: str | None = Form(None, description="行业领域(如 地质勘查/环境评价),用于 RAGFlow 文档名前缀"),
```

`LawCreate(...)` 构造(约 :345)补 `sector=sector,`。

- [ ] **Step 2: sync 上传名组装**

`sync_to_ragflow` 内(行 534 `upload_name = file_name` 与行 547 `upload_name = f"{law.law_number or law.id}.txt"`),两处之后统一改为(建议把两处赋值后、上传调用前加一行):

```python
            # RAGFlow 文档名:【行业】标准号 标题.ext(行业为空则无前缀;重同步可重建)
            upload_name = build_ragflow_doc_name(
                metadata.get("sector"), law.law_number, law.title, os.path.splitext(upload_name or "")[1] or ".txt"
            )
```

(`metadata` 变量在行 521 已存在:`metadata = law.metadata_json or {}`;`os` 已导入;确保放在 `if upload_path and law.ragflow_document_id is None:` 判定之前。)

- [ ] **Step 3: 回归测试 + lint**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_law_kb_registration.py tests/test_law_kb_seed.py -q && uv run ruff check app/extensions/law/`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/extensions/law/routers.py backend/app/extensions/law/service.py
git commit -m "feat(law): 导入链路行业领域字段——RAGFlow 文档名自动带【行业】前缀"
```

---

### Task 4: 前端(行业下拉 + init 响应文案)

**Files:**
- Modify: `frontend/src/extensions/knowledge-factory/hooks/useLawLibrary.ts`(:214 InitRAGFlowResponse 类型;文件尾新增 useLawIndustries)
- Modify: `frontend/src/extensions/knowledge-factory/components/ImportLawModal.tsx`(行业下拉 + 提交字段)
- Modify: `frontend/src/extensions/knowledge-factory/components/RAGFlowStatusPanel.tsx:255-256`(响应文案)

- [ ] **Step 1: useLawLibrary.ts**

类型(:214 附近)改为:

```typescript
  interface InitRAGFlowResponse {
    success: boolean;
    message: string;
    created: string[];
    aligned: string[];
    updated: string[];
    diffs: Record<string, Record<string, [unknown, unknown]>>;
    already_exists: string[];
    failed: { kb: string; error: string }[];
    registered: string[];
  }
```

文件尾追加:

```typescript
export function useLawIndustries() {
  return useQuery({
    queryKey: ["laws", "industries"],
    queryFn: async () => {
      const url = buildLawLibraryUrl("/kf/laws/industries");
      const res = await authFetch<{ industries: string[] }>(url, {}, "");
      return res.industries ?? [];
    },
    staleTime: 5 * 60 * 1000,
  });
}
```

(确认文件头已有 `useQuery` 导入——本文件已在用 queryClient/useMutation,补 `useQuery` 导入即可。)

- [ ] **Step 2: ImportLawModal.tsx**

`FormData` state(:53)加 `industry: ""`;表单在「法规类型」选择之后加下拉(复制相邻 select 的样式):

```tsx
<div>
  <label className="block text-sm text-muted-foreground mb-1">行业领域(可选,用作检索前缀)</label>
  <select
    value={formData.industry}
    onChange={(e) => setFormData((p) => ({ ...p, industry: e.target.value }))}
    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
  >
    <option value="">不标记行业</option>
    {(industries ?? []).map((it) => (
      <option key={it} value={it}>{it}</option>
    ))}
  </select>
</div>
```

组件顶部 `const industries = useLawIndustries().data;`(导入来自 `../hooks/useLawLibrary`);提交处(:188 keywords 之前)加:

```tsx
    if (formData.industry) formDataFd.append("sector", formData.industry);
```

- [ ] **Step 3: RAGFlowStatusPanel.tsx:255-256**

`already_exists` 文案替换为:

```tsx
                {initMutation.data.aligned?.length > 0 && (
                  <span className="text-muted-foreground">,{initMutation.data.aligned.length} 个配置一致</span>
                )}
                {initMutation.data.updated?.length > 0 && (
                  <span className="text-amber-600">,{initMutation.data.updated.length} 个已收敛到标准配置</span>
                )}
```

- [ ] **Step 4: 前端检查**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: 0 error(既有 lint 债务除外,不新增)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/knowledge-factory
git commit -m "feat(kf): 导入新法规行业领域下拉 + init 响应 aligned/updated 文案"
```

---

### Task 5: 线上验证(需 gateway 重启)

- [ ] **Step 1: 重启 gateway 加载后端**

```bash
docker compose -p eai-docker restart gateway && sleep 20
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:2026/api/extensions/auth/login -H "Content-Type: application/json" -d '{"username":"x","password":"y"}'
```
Expected: 非 502(401/400 均为就绪)

- [ ] **Step 2: init-ragflow 幂等验证**

登录后 `POST /api/kf/laws/init-ragflow`:
Expected: `legal → updated(diffs 含 layout_recognize/auto_keywords)`(补种子键)、`standards → aligned`(已手工调成 384 配置且 tag_kb_ids 一致);重复执行第二次 → 两库均 `aligned` 且无 diffs(幂等)。

- [ ] **Step 3: industries + 导入前缀验证**

`GET /api/kf/laws/industries` → `{"industries": ["地质勘查","环境评价","煤炭工业"]}`(顺序可能不同);
前端导入 HJ 130-2019.pdf,行业领域选「环境评价」→ RAGFlow laws-standards 中文档名 = `【环境评价】HJ 130-2019 规划环境影响评价技术导则·总纲.pdf`,解析 DONE。

- [ ] **Step 4: 收尾提交**

```bash
git add -A backend/app/extensions/law frontend/src/extensions/knowledge-factory
git commit -m "chore(law): 线上验证修正(如有)"
```
(无修正则跳过)
