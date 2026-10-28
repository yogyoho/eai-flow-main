# 模板差量包应用说明（中交三公局站 · v20261013 → v20261024 模板）

> 适用：服务器已跑 **v20261013-2e38cf2b1**（Windows Docker）。本包 = 全部模板/配置/技能变更
> （**不含镜像**——镜像走增量镜像包 `eai-flow-delta-*.tar.gz`，用 `upgrade.sh delta` 加载）。
>
> 本包内容：RAGFlow v1.0 拓扑（nats + SSO env）、redis 流桥、config v60 + IM 通道关闭、
> cpa 权限点、10 个 CAD 技能、bid 技能改名、3 个新迁移随 gateway 镜像自动跑。

## 前置

- 已按增量镜像包完成：`$COMPOSE up -d` 前的 `docker load`（upgrade.sh delta 流程或手工）
- **备份**：`pg_dump` 双库 + `tar data/`（0040-0043 四个迁移将自动执行）

## 应用步骤（部署目录 = $NEWDIR）

```bash
cd "$NEWDIR"

# 1. 备份将被覆盖的模板（可回滚）
mkdir -p /opt/eai-backup-template-$(date +%Y%m%d)
cp docker/docker-compose.yaml docker/docker-compose.extensions.yaml \
   docker/docker-compose.ragflow.yaml docker/nginx/nginx.conf \
   config.yaml config/extensions_config.json \
   /opt/eai-backup-template-$(date +%Y%m%d)/ 2>/dev/null

# 2. 解包覆盖（tar 内路径即服务器布局）
tar xzf /path/to/eai-flow-template-delta-20261024.tar.gz -C "$NEWDIR"

# 3. 删除已改名技能的旧目录（新包技能已带 bid-proposal-overall / bid-technical）
rm -rf skills/public/bid-proposal-writing

# 4. .env 合并新键（手工：旧 .env 保留，追加以下键；值按站点实际）
#    RAGFLOW_WEB_URL=http://<站点IP>:19381
#    EAI_SSO_SHARED_SECRET=<64位hex，两侧同值才启用 SSO>
#    EAI_SSO_SHARED_TENANT_IDS=            # 部署后建租户回填，空=特性关
#    BID_RAGFLOW_DATASET_ID=               # 投标 KB dataset id，可后补
#    DEER_FLOW_CREDENTIALS_KEY=            # 留空自动回落 .credentials_key 文件
#    CAD_VIEWER_URL=http://<站点IP>:14178  # 若尚未设置

# 5. RAGFlow 数据面迁移（v0.27 → v1.0，KB 重新导入）：
#    4 个 RAGFlow 旧卷改名保留，让新卷空态创建：
for v in es-data mysql-data redis-data minio-data; do
  docker volume rename eai-prod_prod-ragflow-$v "eai-prod_prod-ragflow-$v-v027bak" 2>/dev/null || true
done
#    ⚠️ 新拓扑新增 ragflow-nats 容器与 prod-ragflow-logs 卷（自动创建）

# 6. 重建全栈
$COMPOSE up -d
#    gateway 首启自动跑迁移 0040-0043 → 等 2-5 分钟转 healthy
```

## 验证

- [ ] `$COMPOSE ps`：**15 容器** Up（新增 prod-eai-flow-ragflow-nats / prod-eai-flow-redis）
- [ ] `/api/license/status` → `"valid": true`
- [ ] 合同价格 → 设置页 RAGFlow 连通性徽章绿色（RAGFLOW_API_KEY 已回填时）
- [ ] 翻译工作台上传/检索正常（RAGFlow v1.0 契约）
- [ ] 合同价术语/聚类功能正常
- [ ] 日志无 WeChat QR 刷屏（IM 通道已默认关）

## 回滚

```bash
$COMPOSE down
# 恢复 /opt/eai-backup-template-*/ 覆盖回模板 + RAGFlow 卷改回原名
for v in es-data mysql-data redis-data minio-data; do
  docker volume rename eai-prod_prod-ragflow-$v-v027bak eai-prod_prod-ragflow-$v
done
$COMPOSE up -d
```
> 镜像层如需回滚：用增量镜像包发布前 upgrade.sh 的快照（或 v20261013 全量包重 load）。
