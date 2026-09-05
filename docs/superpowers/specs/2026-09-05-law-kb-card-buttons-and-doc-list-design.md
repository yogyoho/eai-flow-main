# 知识库管理页法规库收口·第二批(卡片按钮 disabled + laws 投影文件列表含 chunks)— 设计

日期:2026-09-05
状态:APPROVED(设计经用户批准;chunks 能力由用户在只读档基础上追加)
前序:2026-09-04-law-kb-upload-guidance-design.md(详情页封上传+引导横幅,已落地)

## 1. 需求与现状

| # | 需求 | 现状 |
|---|---|---|
| ① | 列表页两个法规库卡片的底部按钮 disabled | 按钮(同步状态/编辑/删除)对法规库仍可点 |
| ② | 点击卡片进入该库详情 | **实测已通**(`onClick → /knowledge/{kb.id}`,page.tsx:416)——之前"进不去"系详情页当时 500(bug-3107,已自愈),**零改动** |
| ③ | 法规库详情文件列表应能看到标准文件记录(现"暂无文件") | 根因:`DocumentService.list_docs` 只查 `documents` 表(knowledge/service.py:400-405),而法规导入写 `laws` 表+直传 RAGFlow,从不登记 `documents` 行 |

③能力档位:**只读 + 可查看 chunks**(用户选定);删除/上传仍禁用(删除会造成 `laws.ragflow_document_id` 悬空)。

## 2. 设计

### 2.1 ① 列表页卡片按钮 disabled

`frontend/src/app/knowledge/page.tsx`:

- 卡片渲染处加 `const isLawKb = isLawKnowledgeBase(kb.name)`(复用 `_components/isLawKnowledgeBase.ts`)
- 三按钮(同步状态/编辑/删除)加 `disabled={isLawKb}`;isLawKb 时 title 前缀「法规标准系统库,请在 知识工厂 → 法规标准 中管理」
- 编辑/删除按钮本有 `can("kb:update")`/`can("kb:delete")` 外层 gate,disabled 与之叠加
- disabled 按钮浏览器语义下不触发 onClick,现有 stopPropagation 行为不变

### 2.2 ③ 后端:laws 投影(单一真相源仍是 laws 表,零迁移、无双写)

**判定**:KB `name.startswith("法规标准库")`(种子名同源,与前端 helper 一致;管理员改名后列表回退为空——沿用既定取舍)。

**投影 helper** 放 `law/service.py`(法规名组合逻辑已在彼处):

```python
def is_law_kb_name(name: str) -> bool          # startswith("法规标准库")
async def project_laws_as_documents(db, kb, skip, limit) -> tuple[list[DocumentResponse], int]
    # select(Law).where(Law.ragflow_dataset_id == kb.ragflow_dataset_id)
    #   .order_by(Law.created_at.desc()).offset(skip).limit(limit)  + func.count 总数
```

**字段映射**(目标 `DocumentResponse`,schemas.py:505):

| DocumentResponse 字段 | 取值 |
|---|---|
| id | law.id |
| knowledge_base_id | kb.id |
| name | `build_ragflow_doc_name(sector, law_number, title, None)`(与 RAGFlow 文档名同源;无扩展名,展示用途可接受) |
| file_path | `""`(必填 str,法规不落盘) |
| file_size | `0` |
| file_type | `None` |
| ragflow_document_id | law.ragflow_document_id |
| status | is_synced 映射:`synced→"success"`、`failed→"failed"`、其余→`"pending"`(DocStatusBadge 三态齐全) |
| error_message | `None` |
| created_at | law.created_at |

**接入点** `knowledge/routers.py::list_documents`(:424):`_load_kb_scoped` 之后判断 `is_law_kb_name(kb.name)` → 走投影分支直接返回(跳过 documents 表与 processing 状态轮询段——投影状态取自 laws.is_synced,无需 RAGFlow 轮询)。

**chunks 端点** `knowledge/routers.py::list_document_chunks`(:485):法规库分支下 `doc_id` 为 law.id——`select(Law).where(Law.id == doc_id)`,校验 `law.ragflow_dataset_id == kb.ragflow_dataset_id`(不等或无 ragflow_document_id 时同既有语义返回 404/空列表),然后复用既有 `rf_client.list_chunks(dataset_id=kb.ragflow_dataset_id, document_id=law.ragflow_document_id, page, size)`。普通库路径不变。

依赖方向:`knowledge/routers.py` 导入 `law.service`(app 内 sibling,law.service 不反依赖 knowledge,**无环**)。

### 2.3 ③ 前端:行内操作裁剪

`frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`(isLawKb 已有):

- **保留** chunks 查看(行点击/查看按钮 → ChunkModal,数据走上述投影后的 chunks 端点)
- **隐藏** 行内删除按钮(isLawKb 时不渲染,连同删除确认分支)
- 工具栏「刷新」保留;上传按钮已隐藏(前序)

## 3. 明确不做

- 上传/删除/编辑法规库文档(封死,防 laws 悬空)
- documents 表登记/存量回填(实时投影天然覆盖存量)
- 知识工厂侧改动
- 按钮级防御后端化(上传 API 仍不感知法规库——纵深防御候选项,维持前序结论)

## 4. 测试与验证

- **后端单测** `backend/tests/test_law_kb_documents_projection.py`:①法规库 KB 列表返回 laws 投影(名称组合/状态映射/分页/total);②普通 KB 走原 documents 路径不受影响;③chunks 端点法规分支(law id 校验 + RAGFlowClient.list_chunks 以 law.ragflow_document_id 调用,mock);④非本库 law id → 404。沿用既有 knowledge router 测试的 fixture 模式
- **静态检查**:backend `make lint` + 相关测试;frontend `pnpm lint && pnpm typecheck`
- **浏览器 E2E**(Docker):法规库卡片三按钮 disabled 且卡片可点进;详情列表显示 3 份法规文件(名称/时间/绿色已同步徽章);点行打开 chunks 有内容;普通库列表/操作如常
- **回滚**:两个 commit 分别 revert

## 5. 涉及文件

| 文件 | 改动 |
|---|---|
| `backend/app/extensions/law/service.py` | `is_law_kb_name` + `project_laws_as_documents` |
| `backend/app/extensions/knowledge/routers.py` | list_documents / list_document_chunks 法规分支 |
| `backend/tests/test_law_kb_documents_projection.py` | 新建单测 |
| `frontend/src/app/knowledge/page.tsx` | 卡片三按钮 disabled + title |
| `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx` | 行内删除按钮 isLawKb 隐藏 |
