# 数据集标注 UI 设计规格

- **日期**:2026-06-18
- **状态**:设计明确,直接实现
- **目标**:让用户在「设置→数据源」界面里**标注/管理**某数据源的业务数据集(增/改/删 label/table/description/default_query),不再只能靠 API。
- **北极星**:数据集 = 数据源(受管 MCP 提供者)上的标注层;UI 是其管理面。不接原语(纯前端,调已有 REST)。

## 改动(纯前端,无依赖)

### 1. types.ts —— 加类型
```ts
export interface DataSourceDataset {
  id: string; sourceId: string; tableName: string; label: string;
  description: string | null; keyColumns: string[] | null; defaultQuery: string | null;
  createdAt: string; updatedAt: string;
}
export interface DatasetCreateRequest {
  tableName: string; label: string; description?: string;
  keyColumns?: string[]; defaultQuery?: string;
}
```

### 2. api.ts —— `datasetApi` + `transformDataset`(snake→camel,对齐 transformDataSource 风格)
- `list(sourceId)` → GET `/data-sources/{id}/datasets`
- `create(sourceId, req)` → POST `/data-sources/{id}/datasets`(body snake_case)
- `update(datasetId, req)` → PATCH `/data-sources/datasets/{id}`
- `delete(datasetId)` → DELETE `/data-sources/datasets/{id}`

### 3. `components/SourceDatasetsModal.tsx`(新)
- props: `{ source: DataSource; open: boolean; onClose: () => void }`
- 顶部:标题"{source.name} 的业务数据集"+ 关闭按钮。
- 内联表单(添加 / 编辑共用):label、table_name、description(textarea)、default_query(textarea)、key_columns(逗号分隔输入)。「保存」提交(create 或 update);「取消」清空。
- 列表:每个数据集一行(label / table / description / default_query 摘要)+「编辑」(载入表单)/「删除」(confirm + delete)。
- 状态:datasets[]、editing(DataSourceDataset|null)、form fields、loading。
- 用 authFetch 已封装在 datasetApi;toast 用 sonner(项目已在用)。
- 复用现有 ui 组件(Button, Input)与 framer-motion 弹窗外壳(对齐 DataSourceForm 的 modal 样式)。

### 4. `components/DataSourceCard.tsx` —— 加「数据集」按钮
- 在底部操作栏(onTest/onSync 旁)加一个「数据集」按钮(List/Table icon)。
- DataSourceCard 内加 `const [showDatasets, setShowDatasets] = useState(false)`,渲染 `<SourceDatasetsModal source={source} open={showDatasets} onClose=... />`。

## 不做
- key_columns 的复杂编辑器(逗号分隔字符串 ↔ string[],够用)。
- 拖拽排序、批量操作。
- 前端单元测试(本项目的 extensions 组件无 vitest 覆盖惯例;验证靠 typecheck + Docker 实测)。

## 验证
1. `cd frontend && pnpm typecheck` —— 数据源相关零错误(既有错误不计)。
2. `docker compose -p eai-docker restart frontend` → 设置→数据源 → 某卡片「数据集」→ 弹窗 → 加一个数据集 → 列表出现 → 编辑/删除可用。
