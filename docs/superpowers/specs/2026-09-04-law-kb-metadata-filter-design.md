# 法规标准 KB 对话/检索按表单字段过滤 — 设计

- 日期:2026-09-04
- 状态:设计已确认(方案A·两段式,待用户审阅本 spec 后转实施计划)
- 关联:`2026-09-03-law-kb-seed-and-import-design.md`(表单字段→meta_fields 链路)、RAGFlow v0.27.1 升级 spec

## 0. 背景与实测依据

导入新法规对话框的表单字段(标准号/发布部门/生效日期/关键词/被引用法规/行业领域)已通过 `meta_fields`(PATCH 文档接口)写入 RAGFlow 文件记录(HJ 463 实证全量落库)。本设计回答:这些字段如何**参与检索**。

v0.27.1 元数据过滤能力(2026-09-04 全部实测):

| 端点 | 行为 | 实证 |
|---|---|---|
| `GET /api/v1/datasets/{id}/documents?metadata_condition=` | ✅ **精准生效** | `law_number=HJ 463-2009` 唯一命中;`sector is 环境评价` 2 命中;`effective_date > 2015` 正确排除 2009 文档;`keywords contains 规划环评` 2 命中;and 组合 1 命中 |
| `POST /api/v1/retrieval` + `meta_data_filter` | ❌ 静默忽略 | 不命中条件仍返回全部块 |
| `POST /api/v1/datasets/{id}/search` + `meta_data_filter` | ❌ 静默忽略 | 同上 |

操作符(官方文档+实测):`is / not is / contains / not contains / in / not in / start with / end with / > / < / ≥ / ≤ / empty / not empty`,`logic: and|or`。

**已裁定决策:方案A 两段式**——文档列表元数据过滤(已验证)+ `document_ids` 收敛检索(已验证);检索端点的 `meta_data_filter` 作为上游跟进项(issue 素材已存档)。

## 1. 设计 A:过滤契约与编排层

### 1.1 过滤契约

`POST /api/kf/laws/{kb_id}/chat` 与 `POST /api/kf/laws/search` 增加可选 `filters` 对象(缺省/全空 = 不过滤,行为与现状完全一致):

```json
"filters": {
  "sector": "环境评价",
  "law_number": "HJ 130-2019",
  "keywords": ["规划环评"],
  "effective_date_from": "2009-01-01",
  "effective_date_to": "2015-12-31"
}
```

映射(→ RAGFlow `metadata_condition`,logic 恒 `and`):

| filters 键 | meta_fields 键 | comparison_operator |
|---|---|---|
| sector | sector | is |
| law_number | law_number | is |
| keywords(数组,逐项展开) | keywords | contains |
| effective_date_from | effective_date | ≥ |
| effective_date_to | effective_date | ≤ |

`effective_date` 在 meta_fields 中为 `%Y-%m-%d` 字符串,字典序比较与日期语义一致(实测 ✓)。

### 1.2 纯函数

`knowledge/service.py` 新增:

```python
def build_metadata_condition(filters: dict | None) -> dict | None:
    """filters → RAGFlow metadata_condition;空/全空返回 None(不过滤)。

    仅接受白名单键(sector/law_number/keywords/effective_date_from/effective_date_to);
    未知键抛 ValueError;keywords 展开为多个 contains 条件;日期区间映射 ≥/≤。
    """
```

### 1.3 两段编排

条件非空时(chat 单数据集;search 按用户可见数据集逐个):

1. `RAGFlowClient.list_documents(dataset_id, metadata_condition=condition)` → 命中 `document_ids`;
2. 零命中 → 直接返回空 sources + `message="过滤条件下无匹配文档"`(不调检索);
3. `document_ids` 传入 retrieval 调用(见 1.4);
4. **截断护栏**:命中 >100 时按 `create_time` 倒序取前 100(v0.27 约束 `xxx_ids≤100`),响应 `filters_truncated: true` + WARNING 日志。

### 1.4 RAGFlowClient 扩展

- `list_documents(dataset_id, page, size, metadata_condition: dict | None = None)` — 透传 `metadata_condition`(JSON 序列化后作 query 参数);
- `chat(..., document_ids: list[str] | None = None)` — payload 键 `document_ids`(顺带修复既有 `doc_ids` 无效参数问题)。

## 2. 设计 B:接口面与测试

### 2.1 响应契约

chat/search 响应新增:`filters_applied`(回显 `build_metadata_condition` 的结果,None=未过滤)、`filters_truncated: bool`。顺带删除 chat 响应中恒为空的 `data.answer` 死字段。

### 2.2 错误处理

| 场景 | 行为 |
|---|---|
| filters 含未知键 / 非对象 | HTTP 400(`build_metadata_condition` ValueError) |
| 命中文档 >100 | 截断前 100 + `filters_truncated: true` + WARNING |
| 零命中 | 200 + 空 sources + message(不调检索) |
| RAGFlow 拒绝 metadata_condition(降级) | 记 WARNING、`filters_applied=None` 降级为无过滤检索,保证可用性 |
| RAGFlow 不可用 | 现状行为(chat 502/search 跳过该库) |

### 2.3 范围

- 后端:`knowledge/routers.py`(chat/search 加 filters 参数)、`knowledge/service.py`(编排)、`knowledge/client.py`(两参数)。
- 前端过滤控件:**deferred**(本轮交付后端 API;KB 对话页/检索页控件待排期)。
- kf_search_knowledge MCP 工具:**不加**(agent 场景靠 config.yaml 数据集 allowlist 已够)。
- DZ 等直传文档的 meta_fields 空缺:补录属数据治理,不在本设计。

## 3. Non-goals

- 不改 RAGFlow 上游(`/retrieval`、`/search` 的 meta_data_filter 支持作为上游 issue 跟进,素材已存档)。
- 不做"表单字段注入块内容"(上轮 Non-goal 维持)。
- 不改 harness/kf_search_knowledge 工具签名。
- 不做检索结果的 meta_fields 回显(reference_metadata 属 chat-completions 域,本栈未用)。

## 4. 测试

- 单元(`tests/test_law_kb_metadata_filter.py` 新建):
  - `build_metadata_condition`:空/None→None;单键→单条件;keywords 展开;日期区间→≥/≤;未知键→ValueError;全空值→None;
  - client:`list_documents` 透传 metadata_condition(query 参数)、`chat` 透传 document_ids(payload 键名);
  - 截断:>100 命中取 100(以 fake rf_client 驱动编排函数)。
- 手工验证:sector 过滤对话、日期区间检索、组合过滤、零命中消息、截断路径;对照无过滤时行为不变。

## 5. 影响面

- `backend/app/extensions/knowledge/routers.py`(chat/search 加 filters)、`service.py`(编排+截断)、`client.py`(list_documents/chat 扩展)。
- 前端本轮不动(`useLawLibrary.ts` 的 chat/search 调用不传 filters 即行为不变)。
- 不改 RAGFlow 上游、不改 harness。
