# ngrok 内网穿透配置方案

## 概述

使用 ngrok 将本地 Docker 开发环境暴露到公网，方便外部访问、演示、调试。

```
Browser (HTTPS) → ngrok cloud → ngrok client → localhost:2026 → Docker nginx → frontend:3000 / gateway:8001
```

## 前提条件

- Docker 开发环境已启动（`make docker-start` 或 `docker compose -p eai-docker up -d`）
- ngrok 已安装并登录（`ngrok config add-authtoken <token>`）

## 启动 ngrok

```bash
ngrok http 2026
```

启动后会显示公网 URL，例如：
```
Forwarding  https://graham-xxx.ngrok-free.dev -> http://localhost:2026
```

## 必需配置修改

### 1. nginx：透传上游代理的 `X-Forwarded-Proto`

**文件**：`docker/nginx/nginx.conf`

**问题**：nginx 硬编码 `proxy_set_header X-Forwarded-Proto $scheme`，其中 `$scheme` 永远是 `http`（nginx→backend 是 HTTP），会覆盖 ngrok 传来的 `X-Forwarded-Proto: https`。导致后端构造的 origin 协议为 `http`，与浏览器 `Origin: https://...` 不匹配，CSRF 校验拒绝所有登录和状态变更请求。

**修复**：在 `http` 块内、`server` 块前添加 `map`：

```nginx
# 透传上游代理的 X-Forwarded-Proto（ngrok / Cloudflare Tunnel 等）
# 有上游值时透传，没有时回退到本地 $scheme
map $http_x_forwarded_proto $client_scheme {
    default  $http_x_forwarded_proto;
    ""       $scheme;
}
```

然后全局替换所有 `proxy_set_header X-Forwarded-Proto` 行：

```nginx
# 改前
proxy_set_header X-Forwarded-Proto $scheme;

# 改后
proxy_set_header X-Forwarded-Proto $client_scheme;
```

> **安全说明**：直连 localhost:2026（无代理）时，`$http_x_forwarded_proto` 为空，自动回退到 `$scheme`，行为不变。

### 2. Next.js：允许 ngrok 域名访问 Dev Server

**文件**：`frontend/next.config.js`

**问题**：Next.js dev server 校验 HMR WebSocket 连接来源，ngrok 域名不在白名单 → WebSocket 被拒（503）→ HMR 客户端无限重试 → 页面反复刷新 → React 无法 hydration → 页面永远显示 loading。

**修复**：在 `allowedDevOrigins` 中添加 ngrok 域名通配符：

```js
// 改前
allowedDevOrigins: ["192.168.2.35"],

// 改后
allowedDevOrigins: ["192.168.2.35", "*.ngrok-free.dev"],
```

> **说明**：`allowedDevOrigins` 仅在 dev 模式生效，生产环境无此问题。

## 重启服务

```bash
docker compose -p eai-docker restart nginx frontend
```

## 使用方式

1. 启动 ngrok：`ngrok http 2026`
2. 浏览器打开 ngrok 公网 URL
3. 首次访问会看到 ngrok 警告页，点击 **"Visit Site"** 跳过
4. 登录（通过 ngrok URL 登录后会为 ngrok 域名创建新的 cookie，不影响 localhost 登录态）

## 注意事项

- **ngrok 免费版限制**：每次启动 ngrok URL 会变化（重启后需重新登录）；有访问频率限制；新浏览器首次访问会显示警告页
- **`GATEWAY_CORS_ORIGINS` 无需设置**：修复 X-Forwarded-Proto 后，后端能正确匹配浏览器 Origin，CSRF 自动通过
- **生产环境不需要 allowedDevOrigins**：Next.js 生产构建无视此配置，HMR 不存在，只需 nginx 修改
- **替代方案**：Cloudflare Tunnel（`cloudflared tunnel`）无警告页且域名固定，可作为 ngrok 免费版的替代
