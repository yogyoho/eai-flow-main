# Windows Docker 离线部署手册（中交三公局站点 · 2026-10-13）

> 适用包：`eai-flow-offline-v2.1.0-rc0-5282-g2e38cf2b1-20261013.tar.gz`（7.6G，15 镜像，config v49，品牌中交三公局）
> 目标机：Windows 10/11 + Docker Desktop（**必须 WSL2 后端**）+ Git Bash
> 全程在 **Git Bash** 中执行；`$NEWDIR` = 解压出的部署目录

## 0. 前提核对

- [ ] Docker Desktop 已安装且 Settings → General → **Use WSL2 based engine** 已勾选（Hyper-V 后端可能拒绝容器 sysctl）
- [ ] Git Bash 已安装（跑 .sh 脚本用）
- [ ] 磁盘 ≥40G（解压 7.6G + 镜像 ~8G + 数据增长）
- [ ] 内存 ≥16G（RAGFlow ES + gateway 4 worker）
- [ ] 端口空闲：`4026 14178 15432 16379 13306 19200 19100 19101 19380 19381 27233`
- [ ] 本机可访问该站点 LLM 服务（GPUStack 等）

## 1. 解压（Git Bash）

```bash
cd /d/                                       # 或目标盘
tar xzf /path/to/eai-flow-offline-v2.1.0-rc0-5282-g2e38cf2b1-20261013.tar.gz
NEWDIR=/d/eai-flow-offline-v2.1.0-rc0-5282-g2e38cf2b1-20261013
cd "$NEWDIR"
```
（7-Zip 两次解压 .tar.gz→tar→目录 亦可）

## 2. .env 必改（Git Bash：`vi .env` 或 VSCode）

| 键 | 值 | 说明 |
|----|----|------|
| `DEER_FLOW_ROOT` | `D:/eai-flow-offline-v2.1.0-rc0-5282-g2e38cf2b1-20261013` | **正斜杠**，解压目录绝对路径 |
| `DEER_FLOW_TRUSTED_ORIGINS` | `http://localhost:4026,http://<本机IP>:4026` | 不加则 IP 访问登录被拒 |
| `INTERNAL_LLM_API_KEY` | 该站点 LLM key | 现 .env 带的是上站点 gpustack key，**必须换** |
| `CAD_VIEWER_URL` | `http://<本机IP>:14178` | 现指向旧站点 IP，**必须换** |
| `RAGFLOW_API_KEY` | 第 6 步回填 | 先留空 |
| `RAGFLOW_SECRET_KEY` | 包内已带固定值 | **不改**（v0.27.x 改了全站 401） |

## 3. config.yaml 模型段（按该站点 GPUStack 实配）

```bash
vi config.yaml    # models: 段——列表首位 = 对话页默认模型
```
- ⚠️ 包内默认模型 `gemma-4-31b`（指向 10.180.42.192:83）是**上一站点**的，本站不存在——须改 `base_url` 到本站 LLM 地址、`model` 改本站真实模型名（或整段删除换成新站模型）；
- 查本站可用模型（部署起完 gateway 后）：
  `docker exec prod-eai-flow-gateway curl -sS -m 8 -H "Authorization: Bearer $INTERNAL_LLM_API_KEY" http://<LLM地址>/v1/models`
- 改完 `docker restart prod-eai-flow-gateway`（models 段支持热重载，但默认模型建议重启确认）。

## 4. 加载镜像 + 启动

```bash
docker network create eai-prod_eai-flow-net 2>/dev/null
bash load-images.sh                  # 15 个镜像，约 5-10 分钟
export COMPOSE="docker compose -p eai-prod --project-directory . \
  -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml"
$COMPOSE up -d
```
- 首启 2-5 分钟（自动跑数据库迁移 0027-0039）；
- OntoStudio 两个容器默认不起（profiles 门控），需要时：
  `docker compose -p eai-prod --project-directory . --profile ontostudio up -d ontostudio-backend ontostudio-frontend`

## 5. 验证

```bash
$COMPOSE ps                          # 15 容器 Up（gateway/前端等 healthy）
curl -s http://localhost:4026/api/license/status    # 宽限期内合法
```
浏览器 `http://localhost:4026`：
- [ ] 登录页 = **中交三公局** 品牌；`admin@eai-flow.com / Admin@2026` 登录（**首登强制改密——改完记牢**）
- [ ] 对话页正常（默认模型按第 3 步配置）
- [ ] 应用中心有应用；管理后台权限列表非空

## 6. license（首登后）

设置 → 许可证 → **下载申请文件** → 发回开发机签发（连同客户全称，默认按“中交三公局”出证）→ 导入回生产，`/api/license/status` 变 `"valid": true`。

## 7. RAGFlow 初始化

1. 浏览器 `http://<本机IP>:19381` → Sign up 注册（全新实例）→ 登录 → 头像 → API → 生成 API Key
2. `.env` 回填 `RAGFLOW_API_KEY=ragflow-xxxx`
3. `export COMPOSE=... && $COMPOSE up -d --force-recreate --no-deps gateway`
4. 知识库页建库 → RAGFlow 端应同步出现 dataset

## Windows 特有注意

- **每次开机先启动 Docker Desktop**（容器 `restart: unless-stopped` 会自动拉起，但引擎不启动则全停）
- `.env` / config 路径一律**正斜杠**
- Git Bash 下命令带容器内绝对路径参数时，前缀 `MSYS_NO_PATHCONV=1`（防路径被转成 Windows 形态）
- **防火墙**：Windows Defender 入站规则放行上述端口（局域网同事访问必需）
- bind mount 在 NTFS 上性能一般——RAGFlow ES 写入较重属正常
- 镜像为 linux/amd64（本包在 Windows Docker Desktop 构建，天然匹配）
- 备份 = tar 部署目录 `data/` + `docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow agentflow`；红线：绝不 `docker volume prune` / `compose down -v`

## 回滚

`$COMPOSE down` → 删部署目录 → 解压旧包重走本手册（数据在 volumes，未动过则不丢）。
