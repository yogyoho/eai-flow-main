# 知识库管理页法规标准库收口为「只读引导」— 设计

日期:2026-09-04
状态:APPROVED(设计经用户批准)

## 1. 背景与问题

法规标准文件进 RAGFlow 有两个入口:

| 入口 | 数据层行为 |
|---|---|
| 知识工厂 → 法规标准 tab(`导入新法规`) | **权威层**:登记 `Law` 元数据(标题/标准号/类型/行业/关键词)→ 自动 `sync_to_ragflow`,记录 `is_synced`/`ragflow_document_id`,删除级联清理 |
| 知识库管理页(`/knowledge/[kbId]`)通用上传 | 裸传进 RAGFlow,**绕过 Law 元数据层** → 孤儿文档:知识工厂列表看不到、「同步更新」管不到、删除不清理 |

目标 KB 为两个法规系统库(种子名 `法规标准库 — 法律/法规/规章`、`法规标准库 — 标准/规范`,由后端 `_ensure_kb_registered` 用 `config.py → law.dataset_display_info` 注册,共享前缀「法规标准库」)。

**决策**(用户已确认):知识库管理页这两个库**只封路不加入口**——隐藏上传按钮,并在描述区渲染引导文案让用户去知识工厂导入。

## 2. 设计

**单文件前端改动**:`frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx`

### 2.1 识别法规KB(3 行 helper,独立文件便于单测)

新文件 `frontend/src/app/knowledge/_components/isLawKnowledgeBase.ts`(不放进组件文件——组件文件依赖树重,单测 import 会拖入 kbApi/lucide/UploadModal):

```ts
// 法规标准系统库种子名都以此开头(后端 _ensure_kb_registered 用 config.py
// law.dataset_display_info 的 name 注册);管理员重命名该 KB 后识别失效、
// 上传按钮恢复(等同改动前现状),可接受。
export const isLawKnowledgeBase = (name: string) => name.startsWith("法规标准库");
```

### 2.2 隐藏上传按钮

既有按钮已 gate 在 `can("kb:upload")`,叠加条件:`can("kb:upload") && !isLawKnowledgeBase(kb.name)`。

### 2.3 描述下方渲染引导文案(带链接)

描述段落(`<p>kb.description…</p>`)下方渲染一行 info 提示(muted 小字,页面现有提示风格):

> ℹ️ 本库为法规标准系统知识库,不提供直接上传。法规/标准文件请在 **知识工厂 → 法规标准** 中导入——自动登记元数据(标准号/类型/行业等)并同步到本库。

「知识工厂 → 法规标准」为可点击链接,跳 `/knowledge-factory?tab=law`。仅 `isLawKnowledgeBase` 为真时渲染。

## 3. 明确不做(Non-goals)

- **后端零改动**:不改 `config.py` 种子描述、不加 `_ensure_kb_registered` 收敛刷新(会覆盖管理员手改的描述)、不改 API
- 文档级操作(查看 chunks / 删单个文档)保持现状;既有问题「详情页删已同步法规文档留下 dangling `ragflow_document_id`」不在本次范围
- 列表页 `/knowledge` 不动(无上传入口)
- 权限体系不动(仅叠加展示条件,不影响 `kb:upload` 判定本身)

## 4. 测试与验证

- **单测**(node 环境):helper 2 断言——种子名前缀匹配为真、普通库名为假;放 `frontend/tests/unit/app/knowledge/_components/` 镜像源码路径
- **静态检查**:`pnpm lint && pnpm typecheck`
- **人工验证**(Docker 容器):法规KB详情页上传按钮消失、引导文案可见、链接可达;普通 KB 上传不受影响
- **回滚**:revert 单文件

## 5. 涉及文件

| 文件 | 改动 |
|---|---|
| `frontend/src/app/knowledge/_components/isLawKnowledgeBase.ts` | 新建,3 行 helper |
| `frontend/src/app/knowledge/_components/KnowledgeBaseDetail.tsx` | 按钮条件 + 引导文案 |
| `frontend/tests/unit/app/knowledge/_components/isLawKnowledgeBase.test.ts` | helper 单测(新建) |
