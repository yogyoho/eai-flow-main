# OntoStudio 文档中心（VitePress 静态站）

部署于 nginx `/ontostudio/docs/` 子路径，独立静态容器 `ontostudio-docs:3011`。

## 本地开发

```bash
pnpm install
pnpm dev        # http://localhost:5173/ontostudio/docs/
pnpm build      # 产物 .vitepress/dist
```

## 内容结构

| 路径 | 内容 |
|---|---|
| `index.md` | 首页 |
| `glossary/` | 术语解释（总览 + eia 域 + doc_graph 域） |
| `design/` | 业务本体设计（eia 域模型 / doc_graph 骨架） |
| `guide/index.md` | 九大模块功能操作 |
| `changelog.md` | 更新记录 |

## 部署

```bash
docker compose -p eai-docker -f docker/docker-compose-dev.yaml build ontostudio-docs
docker compose -p eai-docker -f docker/docker-compose-dev.yaml up -d ontostudio-docs
```

nginx（`docker/nginx/nginx.conf`）将 `/ontostudio/docs/` 代理至本容器，base 路径已设为 `/ontostudio/docs/`。
