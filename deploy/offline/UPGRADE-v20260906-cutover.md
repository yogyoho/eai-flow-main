# 升级手册（专项）：v20260730-ca9c5163 → v20260906-ca7505131 并行目录切换

> 适用：服务器已跑 **7-30 包（v20260730-ca9c5163）**，升级到 **v20260906-ca7505131**。
> 方式：**并行目录 cutover** —— 旧目录原地保留作为回滚点，新包解压到新目录，复用同一
> compose 项目名 `eai-prod` 与同名数据卷，停旧起新。**不删除旧系统。**
>
> 为什么不走 `--delta`：本窗口 compose/config/权限注册表/nginx 全面变更（delta 只运镜像），
> 必须整包模板刷新；镜像随全量包 load 即可。
>
> 已确认的取舍（2026-09-06 用户拍板）：
> ① 旧聊天线程（存于旧核心库 sqlite）**放弃**，不迁移；管理员在新系统重建。
> ② RAGFlow v0.25.3→v0.27.1 上游不支持原地迁移 → **KB 重新导入**（文档原件都在
>    agentflow 库与 ./data，无丢失，只是重跑导入）。

---

## 0. 产物与前提

- 新包：`eai-flow-offline-v0.5.1-1510-gca7505131-20260906.tar.gz`（6.7G，已含品牌
  吉林化工工程 / 内网模型 gemma-4-31b 等 3 个 / 权限注册表 / RAGFlow v0.27.1-fixed）
- 服务器：Ubuntu，旧部署目录假定 `/opt/eai-flow-offline`（下文旧目录均以此为例）
- 同机升级 → **license 无需重新导入**（machine_id 不变 + license.lic 随 ./data 迁移）

## 1. 备份（部署目录外；跳过=无回滚）

```bash
cd /opt/eai-flow-offline
export COMPOSE="docker compose -p eai-prod -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml"
BK=/opt/eai-backup-$(date +%Y%m%d-%H%M); mkdir -p "$BK/old-images"
$COMPOSE ps > "$BK/containers-before.txt"
docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow agentflow > "$BK/agentflow.sql"
# 7-30 包核心库还是 sqlite（./data/data/deerflow.db），postgres 无 deerflow 库，报错属正常
docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow deerflow > "$BK/deerflow.sql" 2>/dev/null \
  || echo "(旧系统无 postgres 核心库，符合预期)"
tar czf "$BK/data.tgz" data
tar czf "$BK/references.tgz" skills/public/geological-report/references 2>/dev/null || true
# 旧镜像快照（新包 load 会覆盖同名 :latest 标签，快照是镜像层回滚的唯一凭据）
for i in deer-flow-gateway deer-flow-frontend eai-flow-collab eai-flow-ocr eai-flow-cad \
         eai-flow-text-to-cad eai-flow-cad-viewer; do
  docker save "$i:latest" -o "$BK/old-images/$(echo "$i" | tr '/:' '__').tar"
done
docker save infiniflow/ragflow:v0.25.3-fixed -o "$BK/old-images/ragflow_v0253-fixed.tar"
ls -lh "$BK" "$BK/old-images"    # 确认备份非空
```

## 2. 新目录解压 + deploy.conf

```bash
cd /opt
tar xzf /path/to/eai-flow-offline-v0.5.1-1510-gca7505131-20260906.tar.gz
mv eai-flow-offline-v0.5.1-1510-gca7505131-20260906 /opt/eai-flow-offline-v2
cd /opt/eai-flow-offline-v2
cp deploy.conf.example deploy.conf && vi deploy.conf
#   只需填一行（模型清单已预置在包内 config.yaml，LLM_BASE_URL/LLM_MODEL 保持留空！）：
#     LLM_API_KEY=gpustack_xxxx
#   （BRAND_* 已烘焙进前端镜像，无需填；RAGFLOW_SECRET_KEY 等包内 .env 已带）
```

## 3. 停旧系统（不带 -v！）

```bash
cd /opt/eai-flow-offline && $COMPOSE down    # 绝不带 -v，见红线 §7
```

## 4. RAGFlow 旧卷改名 —— ⚠️ 本步之后 KB 不可回滚（已拍板）

新包 compose 与旧包共用 4 个 RAGFlow 卷名；v0.27.1 必须全新数据面，改名让新卷以空态创建：

```bash
for v in es-data mysql-data redis-data minio-data; do
  docker volume rename eai-prod_prod-ragflow-$v "eai-prod_prod-ragflow-$v-v0253bak"
done
docker volume ls | grep ragflow    # 确认 4 个 -v0253bak + 旧的 prod-ragflow-data 原样保留
```

## 5. 迁移 ./data 与地质编译产物（license/上传件/渠道态延续）

```bash
tar xzf "$BK/data.tgz" -C /opt/eai-flow-offline-v2
tar xzf "$BK/references.tgz" -C /opt/eai-flow-offline-v2 2>/dev/null || true
ls /opt/eai-flow-offline-v2/data   # 应见 license.lic / .jwt_secret / data/ / uploads 等
```

## 6. 起新系统（install.sh 自动：.env 服务器化 → load 15 镜像 → up → 迁移 → 建管理员）

```bash
cd /opt/eai-flow-offline-v2 && ./install.sh
# 交互确认后自动执行；管理员自动创建 admin@eai-flow.com / Admin@2026（首登强制改密）
```

## 7. 验证清单（逐项过）

```bash
export COMPOSE="docker compose -p eai-prod -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml"
$COMPOSE ps                 # 16 容器全部 Up (healthy)
curl -s http://localhost:4026/api/license/status | head -c 200   # "valid": true（同机 license 延续）
docker exec prod-eai-flow-gateway curl -sS -m 5 http://10.180.42.192:83/v1/models | head -c 200  # 内网 LLM 连通
```

浏览器（http://<服务器IP>:4026）：
- [ ] 登录页显示 **吉林化工工程** 品牌、favicon 为客户版
- [ ] admin 登录成功 → 对话页选 **Gemma-4-31B** 发消息有回复（默认模型即它）
- [ ] 文档管理/合同价分析历史数据可见（agentflow 库延续）
- [ ] 知识库列表在，但 RAGFlow 端为空 → 进入第 8 步
- [ ] 管理后台-权限：角色/权限列表非空（权限注册表已随包）

## 8. KB 重建与收尾配置

1. RAGFlow Web UI（:19381）登录 → 创建 API Key → 回填 `.env` 的 `RAGFLOW_API_KEY` →
   `$COMPOSE up -d --force-recreate --no-deps gateway`
2. 按原清单重新导入知识库文档（EAI-Flow 知识库页触发同步），记录新 dataset id
3. （可选）geo 样例库编译切片推送：RAGFlow 建 `geo-samples-slices` 库 → 回填
   `.env` 的 `GSB_RAGFLOW_DATASET_ID` → 重启 gateway
4. KB 重建完成后如需 `knowledge_search` 工具：包内 `config.yaml` 中该工具处于注释态，
   按新 dataset id 改 allowlist 后取消注释 → `$COMPOSE restart gateway`

## 9. 回滚（验证不过时）

```bash
cd /opt/eai-flow-offline-v2 && $COMPOSE down
docker volume rename eai-prod_prod-ragflow-es-data-v0253bak eai-prod_prod-ragflow-es-data   # 4 个卷改回
docker volume rename eai-prod_prod-ragflow-mysql-data-v0253bak eai-prod_prod-ragflow-mysql-data
docker volume rename eai-prod_prod-ragflow-redis-data-v0253bak eai-prod_prod-ragflow-redis-data
docker volume rename eai-prod_prod-ragflow-minio-data-v0253bak eai-prod_prod-ragflow-minio-data
for t in /opt/eai-backup-*/old-images/*.tar; do docker load -i "$t"; done
cd /opt/eai-flow-offline && $COMPOSE up -d
```
> 限制：KB（RAGFlow 数据）第 4 步改名后旧栈的 KB 已不可用——这是拍板过的唯一不可逆点；
> agentflow 主库从未被动过，文档/用户/合同价不受影响。

## 10. 稳定后清理（观察 3-7 天再执行）

```bash
rm -rf /opt/eai-backup-*/old-images        # 旧镜像快照
docker rmi infiniflow/ragflow:v0.25.3-fixed 2>/dev/null
docker volume rm eai-prod_prod-ragflow-data eai-prod_prod-ragflow-{es,mysql,redis,minio}-data-v0253bak
# 旧目录 /opt/eai-flow-offline 确认无误后再删
# 红线不变：绝不 docker volume prune / docker compose down -v
```
