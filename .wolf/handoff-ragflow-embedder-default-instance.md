# 移交：RAGFlow dev 构建解析全挂——Tokenizer embedder 找 "default" 实例失败

> 写给 RAGFlow 认证集成会话（ragflow-dev:main 镜像的构建方）。tlt 侧（翻译工作台）2026-10-17 实测，需要你们侧修复，修复后我们一键复验。

## 症状

`ragflow-dev:main`（v1.0.0-rc1-400-g0bdf4afda，2026-10-16 10:26 构建）上**任意文档 parse 全部失败**，卡 progress 0.8、0 chunks。API 层无错误（触发 parse 返回 success），失败在 ingestor 执行阶段。

## 复现

任意库任意文档触发 parse 即可。现成样本：

- dataset `b5a8bdd4c7d611f1a79ac13de78f581e`（翻译资产库）
- document `770f70e8ce1c40158ee911de30397309`（test.docx，已重触发过一次，仍失败）

## 错误（ingestor_server.log）

```
error  Tokenizer: tokenizer: resolve embedder: model configuration unavailable:
       instance "default" lookup failed: record not found
       {"component": "Tokenizer:LegalReadersDecide", "task_id": "5ae774e5...", "document_id": "770f70e8..."}
error  agent: component "Indexer" invoke: Tokenizer: ... [NodeRunError]
```

## 分析（两个候选根因，任一即可解释）

1. **存量租户缺 `default` 模型实例别名**：Tokenizer 解析 embedder 按实例名 `default` 查租户模型实例表，租户 `ragflow-admin`（52d6e05ca69611f1ab6ec70ffcbf5582）没有这条记录——疑为模型配置改 instance 制后存量租户未迁移。
2. **Tokenizer 应走数据集 embedding_model**：该数据集的 `embedding_model` 是有效的 `bge-m3:latest@ollama@Ollama`（create 时同值可用），Tokenizer 却走了租户 default 查找——解析路径可能应优先数据集绑定值。

旁证：`user_default_llm.default_models.embedding_model` 当前为空配置（`base_url: http://:80`、无模型名），且解析阶段 warning 显示平铺 parser_config 键（chunk_token_num/layout_recognize/...）不再映射进 pipeline DSL（另案，tlt 对话框已加提示）。

## 修复后 tlt 侧复验

```
POST /api/v1/datasets/b5a8bdd4.../documents/parse  {"document_ids":["770f70e8..."]}
→ 轮询 GET /datasets/{id}/documents 看 chunk_count > 0
```

触发端点已验证可用（success_count=1）。
