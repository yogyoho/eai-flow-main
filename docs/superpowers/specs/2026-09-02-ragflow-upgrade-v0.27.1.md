# RAGFlow v0.25.3 → v0.27.1 升级方案(开发环境 · 全新部署)

- 日期:2026-09-02
- 状态:方案待评审(未编码)
- 决策:**不迁移数据**。废弃 v0.25.3 旧栈,全新部署 v0.27.1,数据由各模块人工重灌(当前为开发环境,均为测试数据)。
- 调研依据:所有上游结论均以 **v0.25.3 与 v0.27.1 两个 tag 的服务端源码 + 官方 upgrade/migration 文档**在线核对(非记忆);本仓库影响面由两轮代码盘点 + 两个 HTTP client 逐端点对照得出。
- 版本事实:GitHub `releases/latest` 确认 **v0.27.1(2026-08-28)为当前最新稳定版**;v0.53.0 / v0.72.1 不是真实存在的 RAGFlow 版本号(tag 列表 404)。

---

## 0. 现状核实(已实地确认)

| 项 | 事实 |
|---|---|
| dev 运行镜像 | `infiniflow/ragflow:v0.25.3`(plain,非 -fixed,12.6GB,容器运行中) |
| 活动卷(将清) | `eai-docker_ragflow-{data,es-data,mysql-data,redis-data,minio-data}`(已 docker inspect 五个容器逐一核实) |
| 孤儿卷(不动) | `docker_ragflow-*`、`docker_ragflow_*`、`eai-docker_ragflow_*`、`eai_ragflow-*` 为历史项目残留;`eai-prod_prod-ragflow-*` 属离线产线,**严禁触碰** |
| 受 MinIO 清卷波及 | `cpa-contracts`(合同价)、geo-samples、spare-parts 三个扩展的桶都在 `ragflow-minio` 卷上(`contract_price/storage.py:28`、`geo_samples/storage.py:26`、`spare_parts/storage.py:30` 默认 `ragflow-minio:9000`)——测试数据,接受重灌 |

## 1. 跨版本破坏性变更 → 本仓库影响(v0.25.3→v0.27.1,共 9 个版本)

### 1.1 升级必处理

| # | 上游变更 | 对本仓库的影响 | 动作 |
|---|---|---|---|
| B1 | **`GET /v1/llm/list` 被删除**(v0.27.1 移除全部 `*_app.py` Python 模块;该端点仅存于 Go 模式 :9384,`API_PROXY_SCHEME=python` 下 404)。⚠️ 实测更正:live `/api/v1/models` 返回裸列表 `data:[{name,provider_name,model_type:[...]}]`,`model_type` 是数组且无 `enable` 字段,与 Swagger docstring 的 `data.models[]` 不符——client 已按实测形态解析(见 2026-09-02 执行记录) | `knowledge/client.py:376-394` 拉模型列表失败 → 建知识库自动选 embedding 失效、前端下拉为空(错误被吞成 `[]`) | **改调 `GET /api/v1/models?type=embedding`**,取 `data.models[]` 中 `model_type=="embedding" && enable`,保持 `<model_name>@<model_provider>` 契约(消费方 `knowledge/service.py:134-139`、`routers.py:46-60`)。不要选 `API_PROXY_SCHEME=go`(Go 面 /api/v1 覆盖度未审计) |
| B2 | **`page_size` 上限 100**(#15292,超限报错);documents 列表实际参数是 `page_size` 而非 `limit`;chunks 列表是 `page_size` 而非 `size` | 潜伏 bug 被显性化:kf 抽取管线 `pipeline.py:727` 传 `size=1000`,两个版本下实际都只拿到前 **30** 个 chunk(大文档抽取一直在静默丢失);`get_document` 扫前 30 条之外永远"未同步" | 改参数名 + **分页循环**(≤100/页,按 `data.total` 翻页);`get_document` 改用 v0.27.1 新增的 `?id=<document_id>` 单文档过滤 |
| B3 | **SECRET_KEY 缓存进 Redis**(#17707/#17720;Redis 逐出/清空 → 全站 401) | 自定义 compose 未设 SECRET_KEY | ragflow 服务 env 增加 `SECRET_KEY`(固定随机值,写入 `.env`) |
| B4 | **model-provider 建表/数据迁移仅在 `--init-model-provider-tables` 时运行**(上游 v0.27.1 compose command 为 `["--enable-adminserver","--init-model-provider-tables"]`) | 自定义 compose 无 command → 默认 entrypoint 跳过迁移;全新部署也需要它建表+种子 | compose 加 command(见 §3) |

### 1.2 已核实无影响(不需要动作)

- **ES 8.11.3 不变、无需 reindex**(STACK_VERSION 全程 8.11.3;官方升级文档无 reindex 步骤;换文档引擎才是破坏性的,我们不换)。
- **service_conf.yaml.template 的 env 变量名零改名**:`MYSQL_DBNAME/ES_HOST/ES_USER/ELASTIC_PASSWORD/MINIO_HOST/MINIO_USER/MINIO_PASSWORD/REDIS_HOST/REDIS_PASSWORD` 在 v0.27.1 模板中逐字一致 —— 现有 compose env 块继续有效。
- API key 认证(`Authorization: Bearer`)不变;服务端 Flask→Quart 对客户端无感;错误码信封 `{code,data,message}` 不变(`code=101` 语义不变)。
- `/retrieval` 响应结构 `{total, chunks[], doc_aggs[]}` 与 chunk 字段重映射(`content/document_id/dataset_id/document_keyword/similarity`)完全兼容;`formatting.py` 已验证兼容到 v0.27.0。`top_k` 弃用但仍接受(harness `top_k=256` 安全)。
- 新约束 `rerank_candidates_count(默认64) ≥ page*page_size`:现有调用(page_size=8 或默认 30)满足;未来若传 >64 需同请求带 `rerank_candidates_count`。
- `GET /datasets` 的 `ids` 过滤器 v0.27.0 起官方支持 → harness client 的 EAI-CUSTOM `id` 回退变死代码(可留可删,留着无害)。
- GraphRAG/RAPTOR UI 弃用(旧内容仍可检索)—— 不走 API 路径,无影响。
- `POST /datasets/{id}/chunks` 新增 pipeline 数据集拒绝守卫 —— 本仓库建的 KB 无 `pipeline_id`,不受影响。

### 1.3 顺手修的潜伏 bug(两版本皆存在,非升级引入;强烈建议同一窗口修掉)

| # | bug | 位置 |
|---|---|---|
| L1 | `parser_config` 键名/类型错误:`chunk_token_count`(应为 `chunk_token_num`)、`layout_recognize: True`(bool,应为 `"DeepDOC"` 等字符串)→ 带 chunk_config 建库即 400 | `knowledge/service.py:383-386` |
| L2 | law 元数据写入用 `PUT` + 平铺键,上游两版本都不存在该接口(靠兼容 shim 转发)且平铺键被静默丢弃 → **从未生效**;改 `PATCH` + `{"meta_fields": {...}}` | `knowledge/client.py:396-405`、`law/service.py:558-569` |
| L3 | 解析状态轮询读 `status`(pending/parsing/...),上游文档实际字段是 `run`(UNSTART/RUNNING/CANCEL/DONE/FAIL)+ 错误在 `progress_msg` → 轮询永远超时;`to_doc_status` 映射同步修 | `knowledge/client.py:17-20,261-299`、`extensions/schemas.py:472-488` |
| L4 | `list_datasets` 声明 page/size 却从不发送 → 只见前 30 个数据集;改用 `?name=` 过滤或真分页 | `knowledge/client.py:95-103,363-374` |
| L5 | 死代码:`get_dataset_statistics`(端点两版本都不存在)、`wait_for_parsing_complete`(无调用方)→ 删除或随 L3 修复 | `knowledge/client.py:261-299,353-361` |
| L6 | `/retrieval` 的 `doc_ids` 是无效参数(上游读 `document_ids`)→ 文档过滤一直无效 | `knowledge/client.py:321-329` |
| L7 | 上传时 form `parser_id`/`parser_config` 上游不读(按数据集默认)→ laws/standards 分块器选择从未按上传参数生效;需在数据集级设置或上传后 `PATCH` 文档 | `knowledge/service.py:438-449`、`law/service.py:549-557` |
| L8 | `docker/.env.docker:18` 外部拓扑变体的 `RAGFLOW_BASE_URL` 带 `/api/v1` 后缀,与 extensions client 自拼前缀重复(config.yaml:766 明确 base_url 不得带) | 按需修正 |

## 2. 代码修改清单(backend)

**升级必改**:
- C1 = B1(models 端点改造,`knowledge/client.py`)
- C2 = B2(分页参数 + kf 管线分页循环,`knowledge/client.py:188-259`、`knowledge_factory/pipeline.py:723-730,882-894`)
- C3 = B3/B4(compose 层,见 §3)

**同窗口顺手修**:C4=L1,C5=L2,C6=L3,C7=L4,C8=L5,C9=L6,C10=L7(数据集级 chunk_method 或上传后 PATCH,与用户确认产品语义),C11=L8。

**收尾**:
- harness client `client.py:125-141` 的 `id` 回退:更新 EAI-CUSTOM 注释(v0.27.1 原生支持 `ids`,回退保留为兼容旧镜像的防御,或直接删)。
- 版本注释更新:`knowledge/service.py:357`、`knowledge_factory/pipeline.py:661,910` 的 "v0.25.3" 行为描述重新核实改写。
- 测试:`test_ragflow_client.py` / `test_ragflow_tools.py` 现状应继续全绿(harness 面无行为变化);app 层 client 目前**零测试**,补最小 wire 用例(httpx mock):models 端点解析、page_size 参数、meta_fields、上传响应 list 解包、run 状态映射、retrieval 参数。
- 所有 harness 层改动按 EAI-CUSTOM 三重规范标注。

## 3. Compose 修改(`docker/docker-compose.ragflow.yaml`,offline 孪生文件同步)

```yaml
  ragflow:
    image: ${RAGFLOW_IMAGE:-infiniflow/ragflow:v0.27.1}     # ① 版本
    # ② 上游 v0.27.1 compose 默认 command(model-provider 建表+种子)
    command: ["--enable-adminserver", "--init-model-provider-tables"]
    environment:
      # ...现有 env 全部保留(变量名上游零改名)...
      - SECRET_KEY=${RAGFLOW_SECRET_KEY:?set-in-env}        # ③ 防 Redis 逐出→全站 401
    volumes:
      - ragflow-logs:/ragflow/logs                          # ④ 替换 ragflow-data:/ragflow
```
- ④ **必须换**:`ragflow-data:/ragflow` 具名卷会遮蔽镜像内代码(Docker 卷仅在**空**时自动填充)——旧卷在,拉新镜像跑的仍是旧代码,这是本栈最大的升级陷阱;上游本来就不挂 /ragflow。dev 在线环境 tiktoken 首次下载不受影响。
- ES 服务加 `tmpfs: [/tmp:mode=1777,size=512m]`(v0.27.1 官方镜像 /tmp ACL 需要,upstream compose 同款);建议对齐 upstream 的磁盘水位参数。
- MySQL 建议对齐 upstream command(`--default-authentication-plugin=mysql_native_password --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci --max_connections=1000`)。全新部署,一次性成本为零。
- Redis(`redis:7-alpine`)、MinIO(`minio/minio:latest`)不动:协议兼容、RAGFlow 侧连接变量未变;不设 maxmemory 即无逐出,SECRET_KEY 天然安全。
- `docker/.env.docker:59`、`docker/.env:51` 的 `RAGFLOW_IMAGE` 同步改;新增 `RAGFLOW_SECRET_KEY=<python -c "import secrets;print(secrets.token_hex(32))">`。
- `USE_DOCLING` 保持不设(设置会触发联网 pip)。

## 4. 执行步骤(dev)

```bash
# 1. 记录/通知:旧 API Key、全部 dataset ID 即将作废
# 2. (可选后悔药,每卷一条)
docker run --rm -v eai-docker_ragflow-mysql-data:/data -v ${PWD}:/bak busybox tar czf /bak/rf-mysql.tgz /data

# 3. 停旧栈(只删容器,不动卷)
docker rm -f eai-flow-ragflow eai-flow-ragflow-es eai-flow-ragflow-mysql eai-flow-ragflow-redis eai-flow-ragflow-minio

# 4. 清活动卷(⚠️ 仅这 5 个;eai-prod_* 与历史孤儿卷不碰)
docker volume rm eai-docker_ragflow-data eai-docker_ragflow-es-data \
  eai-docker_ragflow-mysql-data eai-docker_ragflow-redis-data eai-docker_ragflow-minio-data

# 5. 拉新镜像
docker pull infiniflow/ragflow:v0.27.1

# 6. 落地 §2 代码修改 + §3 compose 修改,按常规起栈(make dev / 全 -f up -d)
```

7. **RAGFlow 初始化**(:9381):注册 admin(全新租户)→ 配置模型提供商(通义/ZHIPU 等,原配置作废;注意 ZHIPU 429 限额史)→ 生成新 API Key。
8. **回填 Key**:根 `.env` 的 `RAGFLOW_API_KEY=` 新 Key → gateway / knowledge-factory 容器 **`up -d --force-recreate`**(`env_file` 在容器 create 时烘焙,restart 不重读)。
9. **清理 EAI DB 失效外键**(postgres-ext):`UPDATE knowledge_bases SET ragflow_dataset_id=NULL;` 及 `documents.ragflow_document_id`、`laws.ragflow_dataset_id/ragflow_document_id` 同理 → 之后按模块重新同步/重建 KB。
10. **config.yaml `knowledge_search` 允许清单**(`config.yaml:776-781`,5 个 dataset ID)全部失效 → 重灌后以新 ID 更新(或先注释掉该工具)。
11. **各模块人工重灌测试数据**:知识库文档、law、cpa-contracts、geo-samples、spare-parts(桶随卷清空)。

## 5. 验证清单

- [ ] RAGFlow Web UI :9381 登录;模型提供商配置完成;`GET /api/v1/models?type=embedding` 有数据
- [ ] 网关 `GET /api/v1/knowledge-bases/ragflow/embedding-models` 返回非空(前端建库下拉恢复)
- [ ] 建测试 KB → 上传 pdf+docx → parse → `list_chunks`(造一个 >30 chunk 的文档验证分页修复)→ `/retrieval` 命中
- [ ] `kf_search_knowledge` MCP 工具(config.yaml 允许清单更新后)走通
- [ ] law:`sync_to_ragflow` 端到端 + 元数据 PATCH 后可读回
- [ ] harness `knowledge_search` 工具(允许清单数据集)走通
- [ ] `cd backend && make lint && make test`
- [ ] 容器日志:无 401 风暴(SECRET_KEY 生效)、无 ES /tmp 写入报错、无 model-provider 表缺失报错

## 6. 回滚

保留 `infiniflow/ragflow:v0.25.3` 镜像不删。回滚 = 改回 pin + 重走 §4.3-4.6(清卷重来)+ DB 映射再清 + 重灌。因数据本就弃用,无不可逆风险。

## 7. 离线产线(后续批次,不在本次范围;但 §0 已发现一个现存 bug)

- ⚠️ **现存 bug**:`deploy/offline/.env:70` pin 了 plain `v0.25.3`,覆盖 offline compose 默认的 `v0.25.3-fixed`(`install.sh --project-directory` 下 `.env` 优先)→ **离线产线实际跑的是未加固镜像**(缺 F.11 pip PATH / F.13 tiktoken 离线烘焙,断网首启应会崩)。已录 buglog;升级产线前必须先修 pin。
- 产线升级时:`deploy/offline/ragflow-fixed.Dockerfile` 的 `FROM` 改 v0.27.1 并重新验证 F.11/F.13;`scripts/offline-export.sh` 4 处 `-fixed` tag 同步;§3 的 command/SECRET_KEY/ES tmpfs/卷替换对 offline 孪生 compose 同样适用;`MANUAL-UPGRADE.md` 无 RAGFlow 专属章节(健康门只查 gateway `/api/license/status`,ragflow 挂了不会拦截升级)→ 需补章节;产线 dataset ID 允许清单与 API Key 同样失效重配。

## 8. 主要调研来源

上游(均在线核对):`releases/latest`(v0.27.1)、v0.25.3/v0.27.1 的 `docker/{.env,docker-compose.yml,docker-compose-base.yml,service_conf.yaml.template,entrypoint.sh,nginx/ragflow.conf.*}`、`api/apps/restful_apis/{dataset,document,chunk,models}_api.py`、`api/apps/backward_compat.py`、`internal/handler/llm.go`、`docs/administrator/upgrade_ragflow.mdx`、`docs/administrator/migration/*`、v0.25.4→v0.27.1 全部 release notes。
本仓库:harness client(`community/ragflow/*`)与 extensions client(`extensions/knowledge/client.py`)共 19 个端点逐一对照;部署/前端/离线包盘点;测试盘点(全部 mock,升级正确性必须靠 §5 实例冒烟)。
