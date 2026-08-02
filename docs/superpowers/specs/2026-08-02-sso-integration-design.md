# EAI 统一认证门面 · SSO 单点登录集成设计

- 日期：2026-08-02
- 状态：**定稿 · P0 已实现但默认未启用（未来与其他系统 SSO 集成时启用）**
- 前置：`2026-08-02-auth-unify-design.md`（双轨登录门面已落地：工号+密码 / 邮箱+验证码）
- 范围：SSO 作为**第三认证门面**（通用 OIDC），按**工号** join extensions 组织目录，零上游核心改动

## ⏸ 当前状态（2026-08-03）—— 已归档待启用

**结论：SSO 接入层（P0）代码已全部实现并提交到 `main-dev-fork`，但默认未启用。** 未来需要与其他系统做 SSO 集成时，按 §12 的启用清单操作即可。

| 层 | 状态 | 说明 |
|---|---|---|
| P0 接入层代码 | ✅ 已实现并提交 | `app/extensions/auth/sso.py`（`/oidc/start` + `/oidc/callback/{provider}`）、`auth_middleware` 前缀豁免（EAI-CUSTOM）、登录页 SSO 按钮（`<Link prefetch={false}>`） |
| P0 单元测试 | ✅ 8 个全绿 | `tests/test_extensions_sso.py` |
| P1 Keycloak compose | ✅ 已加服务 | `docker/docker-compose-dev.yaml` 有 `keycloak` 服务，**未部署** |
| 启用开关 | ⛔ 未启用 | `config.yaml` **没有 `auth.oidc`** → 点 SSO 按钮 `/oidc/start` 返回 404 |
| 登录页按钮 | ⚠️ 已显示但点击 404 | 启用前置需按 §12.1 条件渲染（仅当 `/api/v1/auth/providers` 有 provider 时显示） |

**为什么归档**：SSO 依赖真实 OIDC IdP（Keycloak/企微/钉钉/ADFS）才能验证。当前无 IdP 集成需求，代码与方案先行落地，待未来「与其他系统 SSO 集成」时启用。

## 1. 背景与目标

认证门面已提供「工号+密码」与「邮箱+验证码」两种登录。本设计新增 **SSO（通用 OIDC）** 作为第三种方式，让企业员工经 IdP 一次登录进入系统。

**目标：**
1. 支持任意标准 OIDC IdP（Keycloak/Entra ID/ADFS 等）；设计含 **Keycloak 自托管部署建议**（可 broker 企微/钉钉/飞书）。
2. **按工号 join** extensions 用户表（组织目录真源），不做 SSO 自动建号——**仅预建号可登**（admin 统一建号模型）。
3. 复用认证门面的统一会话签发 `_issue_gateway_session`，三种登录方式归一到一个 extensions `user_id`。
4. **零上游核心改动**：只 import 复用 `OIDCService` 等上游构建块；中间件豁免用 EAI-CUSTOM 注释。

## 2. 研究结论（已验证）

### 2.1 上游 OIDC 能力（可复用，不改）
- `GET /api/v1/auth/oauth/{provider}`：完整发起（discovery + RFC8414 issuer 钉死、state/nonce/PKCE、签名 state cookie、302 到 IdP）。
- `OIDCService`（`app/gateway/auth/oidc.py`）：`discover()`、`build_authorization_url()`、`authenticate_callback()`（code 换 token + id_token JWKS 验签 + alg 白名单 RS256/384/512 + ES256/384/512 + aud/iss/sub 校验 + userinfo 匹配）。
- `oidc_state.py`：`OIDCStatePayload`、`generate_oidc_state/nonce/code_verifier/compute_code_challenge`、`get_state_cookie/delete_state_cookie`（HS256 签名，auth jwt_secret）。
- 配置：`config.yaml → auth.oidc.enabled/providers.{id}`（issuer/client_id/client_secret/scopes/pkce/nonce/redirect_uri/token_endpoint_auth_method…），热加载。
- **上游无 claim 映射能力**（sub/email 硬编码匹配）→ 工号映射必须 EAI 层实现。

### 2.2 关键约束：state cookie 的 Path 绑定上游回调
上游 `set_state_cookie` 把 state cookie 的 `Path` 设为 `/api/v1/auth/callback/{provider}`（`oidc_state.py:91-103`）。EAI 回调在 `/api/extensions/auth/oidc/callback` **收不到该 cookie**（浏览器按 Path 匹配发送）。
→ **发起与回调必须 EAI 自建**（复用 `OIDCService` 验签能力，import 不修改）；state 用**相同签名格式**（`OIDCStatePayload` + HS256 + auth jwt_secret）写入 `Path=/` 的 cookie，使 `get_state_cookie` 可直接校验。

### 2.3 身份 claim 契约
| Claim | 用途 | 来源 |
|---|---|---|
| `sub` | IdP 稳定标识，回登关联键 | id_token 必含 |
| `employee_number`（或 `preferred_username`） | **工号 = join 键**（对应 extensions `User.username`） | IdP 自定义 claim / token mapper |
| `email` | 次级 join（工号缺失时回退）；会话通道（`_issue_gateway_session` 是 email 键） | id_token/userinfo |

工号（`User.username`）唯一、非空、正是企业工号；email 可变更故不作主 join 键，仅作会话通道与别名。

### 2.4 IdP 对比（Keycloak 推荐）
- 企业微信/钉钉/飞书均**非标准 OIDC**（无 discovery/JWKS/id_token），需适配器或 IDaaS 前置。
- **Keycloak（自托管）**：原生 OIDC；可 broker 企微/钉钉/飞书为 OAuth2 IdP、联邦 AD/LDAP；token mapper 发 `employee_number`。→ 首选。
- Entra ID/ADFS：`employeeId` 不在默认 claim，需自定义策略；运维重。

## 3. 架构总览

```
登录页（+SSO 按钮）
   │ 点击 → GET /api/extensions/auth/oidc/start?provider={id}   [EAI 发起]
   │     ① 复用 OIDCService.discover + build_authorization_url
   │     ② 生成 state/nonce/PKCE → 写 Path=/ 的签名 state cookie → 302 IdP
   ▼
IdP 授权 → 302 回 GET /api/extensions/auth/oidc/callback/{provider}?code&state   [EAI 回调]
   │     ① get_state_cookie(request, provider) 校验 + OIDCService.authenticate_callback（验签）
   │     ② 提取 employee_number(工号)/sub/email
   │     ③ 按工号 join extensions User（仅预建号，无→401）
   │     ④ 复用 _issue_gateway_session(email, request, response)
   ▼
access_token HttpOnly cookie → 前端 /auth/callback?next=/workspace
```

**中间件**：`auth_middleware._PUBLIC_PATH_PREFIXES` 加前缀 `"/api/extensions/auth/oidc/"`（覆盖 start 与所有 callback/{provider}；GET，CSRF 不适用，只加 auth_middleware）。

## 4. 详细设计

### 4.1 EAI 发起端点（新增 `app/extensions/auth/oidc.py` 或并入 routers）

```
GET /api/extensions/auth/oidc/start?provider={id}
1. 读 config.yaml auth.oidc.providers.{id}；未启用/未知 → 404。
2. OIDCService.discover(issuer, overrides) → metadata。
3. state/nonce/PKCE = generate_oidc_state()/generate_nonce()/generate_code_verifier()/compute_code_challenge()。
4. redirect_uri = providers.{id}.redirect_uri 或按请求 origin 派生 → {origin}/api/extensions/auth/oidc/callback。
5. build_authorization_url(...)（复用 OIDCService）。
6. 写签名 state cookie：名 `df_oidc_state_{provider}`，Payload=OIDCStatePayload(...)，HS256(auth jwt_secret)，**Path=/ ，max_age=300s，SameSite=lax，HttpOnly**。
7. 302 → IdP。
```

### 4.2 EAI 回调端点（新增，provider 在路径中）

```
GET /api/extensions/auth/oidc/callback/{provider}?code&state
1. 错误参数 → redirect /login?error=sso_failed。
2. get_state_cookie(request, provider) 校验 + compare_digest(state) → 失败 403/redirect。
3. OIDCService.authenticate_callback(provider_id=provider, ...)（复用验签链）→ OIDCIdentity。
4. 提取 claims：`employee_number`（首选，若 IdP 提供）或 `preferred_username` → 工号；email；sub。
5. join extensions User：
   - 优先 `User.username == 工号`；工号缺失 → `User.email == email`（仅当 email 存在）。
   - 均查无 / `status != active` / `is_deleted` → 401（**仅预建号，不自动建**）。
6. 可选：`user.last_login_at = datetime.utcnow(); await db.commit()`。
7. `return await _issue_gateway_session(user.email, request, response)`（复用统一会话签发）。
8. 限流：`_check_login_rate_limit/_record_login_failure`（per-IP）。
```

> provider 放路径（同上游 `/api/v1/auth/callback/{provider}` 模式），使 `get_state_cookie(request, provider)` 能按 provider 名找到对应 state cookie。

`_issue_gateway_session`（`routers.py:38-60`）已按 email 补建 gateway 镜像行、签发 access_token cookie——SSO 直接复用，与另两门面一致。

### 4.3 配置（config.yaml）

```yaml
auth:
  oidc:
    enabled: true
    frontend_base_url: "http://localhost:2026"
    providers:
      keycloak:
        display_name: "企业统一登录"
        issuer: "https://keycloak.example.com/realms/eai"
        client_id: "eai-flow"
        client_secret: "$KEYCLOAK_CLIENT_SECRET"   # 支持 $ENV
        redirect_uri: ""                            # 空 → 按请求 origin 派生为 EAI 回调
        scopes: ["openid", "email", "profile"]
        pkce_enabled: true
        nonce_enabled: true
```
> 配置为热加载（`get_app_config` 每次请求读）。`auto_create_users`/`require_verified_email`/`admin_emails` 等上游字段在本设计中不启用（EAI 回调不走上游 provisioning）。

### 4.4 前端

登录页新增 **"SSO 登录"** 按钮（第三入口）：
- 密码/验证码 tab 之外放一个按钮，`<a href="/api/extensions/auth/oidc/start?provider=keycloak">`（或 `window.location`）。
- 回调完成后走现有 `/auth/callback?next=/workspace` 流程（需 EAI 回调在 302 里带 `frontend_base_url/auth/callback?next=`）。

### 4.5 中间件豁免（EAI-CUSTOM）

`backend/app/gateway/auth_middleware.py::_PUBLIC_PATH_PREFIXES` 增加前缀（覆盖 start 与 callback/{provider} 动态路径）：
```python
"/api/extensions/auth/oidc/",
```
（GET 请求，CSRF 中间件不校验；无需改 csrf_middleware。这是对上游 auth_middleware 的第 2 处 EAI-CUSTOM 前缀，同步时需保留。）

## 5. 首次登录策略

- **仅预建号可登**：SSO 登录要求工号已存在 extensions `users`（admin 统一建号），否则 401。不自动建号。
- IdP `sub` 可记录到 extensions 用户（可选，新增 `oauth_provider/oauth_id` 字段或复用 gateway `create_oauth_user`）用于回登关联；本期**不强制**（工号 join 已满足）。
- 停用用户：`status != active` → 拒绝。

## 6. IdP 部署建议（Keycloak 自托管）

- **推荐**：`docker compose` 增加 `keycloak` 服务（quay.io/keycloak/keycloak，admin + realm eai）。
- Realm 配置：client `eai-flow`（confidential，redirect_uri 指向 EAI 回调），token mapper 把 `preferred_username` 或自定义属性 `employee_number` 加进 id_token。
- **broker 企微/钉钉/飞书**：Keycloak 把它们作为 OAuth2 Identity Provider 接入，统一发 `employee_number` claim → 工号。
- **联邦 AD/LDAP**：Keycloak user federation，工号来自 AD `employeeNumber`。
- 部署为独立服务（复用 `eai-docker` 网络），端口/凭据入 `.env`。

## 7. 安全

| 项 | 要求 |
|---|---|
| OIDC 校验 | 复用上游：issuer 钉死、JWKS、alg 白名单、aud/iss/sub、nonce、userinfo sub 匹配 |
| state | 签名 cookie（HS256 + auth jwt_secret），constant-time 比对；Path=/ 由 EAI 写 |
| 限流 | per-IP 登录尝试（复用门面限流） |
| 防枚举 | 工号/邮箱不存在统一 401 |
| 仅预建号 | 不自动建号，杜绝 SSO 越权注册 |
| 会话 | 复用 access_token HttpOnly cookie + CSRF；HTTPS 才持久会话 |

## 8. 测试计划

新增 `backend/tests/test_extensions_sso.py`（TDD）：
- **回调 claim→工号 join**：mock `OIDCService.authenticate_callback` 返回 identity（含 employee_number）；工号命中 → 200 + cookie；工号未命中 → 401；status 非 active → 401。
- **工号缺失回退 email**：identity 无 employee_number → 按 email join。
- **state 校验**：state 缺失/不匹配 → 403。
- **会话**：`_issue_gateway_session` 被正确调用，返回 access_token cookie。
- **发起端点**：provider 未知 404；redirect_uri 派生正确；state cookie 写入 Path=/。
- E2E：配置 Keycloak（或 mock OIDC provider）后全链路登录。

## 9. 分阶段交付

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0 接入层** | EAI 发起+回调、工号 join、中间件豁免、前端 SSO 按钮、单测 | 单测绿；用 mock OIDC 验证 code 流程 |
| **P1 Keycloak** | compose 部署 Keycloak + realm/client/mapper 配置 + E2E | 真实 Keycloak 登录进工作台 |
| **P2 IdP broker**（可选） | 企微/钉钉/飞书经 Keycloak 接入；记录 IdP sub | 扫码/快捷登录 |

## 10. 不做的事（Out of Scope）

- 不走上游 `/api/v1/auth/oauth/*` provisioning（按 sub 自动建 gateway 用户）——本设计走 EAI 回调 + 工号 join。
- 不做 SSO 自动建号（本期仅预建号）。
- 不改 harness `OIDCProviderConfig`（无 claim 映射，EAI 回调自行读 claims）。

## 11. 验收标准

1. 登录页出现 SSO 按钮；经 OIDC IdP 授权后可进入工作台。
2. 工号未预建 / 已停用用户 → 登录被拒（401）。
3. 三种登录方式（密码/验证码/SSO）落到同一 extensions `user_id`，会话一致。
4. 零上游核心改动（仅 auth_middleware 一个 EAI-CUSTOM 块加 2 路径）。
5. `make test` 通过（新增 SSO 测试全绿）。

## 12. 启用清单（未来需要时执行）

> 代码已就绪（P0 已提交），启用 = 配置 + 部署，**不需要再写接入代码**。

**12.1 隐藏死按钮（启用前置，必做）**
登录页 SSO 按钮当前无条件渲染、点击 404。启用前把按钮改为**条件渲染**：登录页 mount 时 `GET /api/v1/auth/providers`（上游已有端点，返回 `{providers: [...]}`），仅当 `providers.length > 0` 时显示按钮。

**12.2 部署 Keycloak（或任一 OIDC IdP）**
```bash
docker compose -p eai-docker -f docker/docker-compose-dev.yaml up -d keycloak
```
- 首次需建 `keycloak` 数据库（postgres-ext 的 agentflow 用户若无 CREATEDB 权限需授权或建库）。
- Keycloak 管理台 `http://localhost:8080`（admin/admin123）：
  1. 建 realm `eai`
  2. 建 client `eai-flow`（confidential）
  3. redirect_uri = `http://localhost:2026/api/extensions/auth/oidc/callback/keycloak`
  4. **token mapper**：把 `preferred_username`（或 AD `employeeNumber` / 企微 `userid`）映射为 **`employee_number`** claim —— 这是回调 join 工号的键

**12.3 配置 config.yaml + 重启 gateway**
```yaml
auth:
  oidc:
    enabled: true
    frontend_base_url: "http://localhost:2026"
    providers:
      keycloak:
        display_name: "企业统一登录"
        issuer: "http://localhost:8080/realms/eai"
        client_id: "eai-flow"
        client_secret: "<client 密钥>"
        redirect_uri: ""        # 空 → 自动派生为 EAI 回调
        scopes: ["openid", "email", "profile"]
```
```bash
docker compose -p eai-docker restart gateway
```

**12.4 验证**
- 登录页 SSO 按钮可点 → Keycloak 授权页 → 回调 → 按工号登录。
- Keycloak 里配一个与 extensions `User.username` 同工号的账号验证命中；未预建工号 → 401。

## 13. 与其他系统做 SSO 集成（未来场景）

本系统当前是 **OIDC 依赖方（SP）**。未来与「其他系统」做 SSO 集成，按方向分：

**方向 A：其他系统作为 IdP，本系统接入（本设计已支持）**
- 其他系统若提供标准 OIDC → 在 `config.yaml auth.oidc.providers` 加一个 provider 即可（同 Keycloak 配置，换 issuer/client/secret）。
- 需对方 IdP 提供 **工号 claim**（`employee_number`/`preferred_username`）并已在 extensions 预建号。
- 若对方是 企微/钉钉/飞书（非标准 OIDC）→ 经 **Keycloak broker**（Keycloak 把它们作为 OAuth2 IdP 接入，统一发 `employee_number`），本系统仍只认 Keycloak。

**方向 B：本系统作为 IdP，其他系统接入**
- 本系统基于 deer-flow 自带 OIDC 能力（`/api/v1/auth/oauth/*`）可暴露为标准 OIDC IdP；但 extensions 组织目录（工号/部门/角色）在 PostgreSQL，需要把 extensions 用户作为 OIDC 用户源暴露（未来工作）。
- 或更简单：用 **Keycloak 统一收口**（本系统与各子系统的用户都进 Keycloak），各系统作为 SP 接入 Keycloak，Keycloak 联邦 AD/LDAP 作统一目录。

**方向 C：存量旧系统（AD/LDAP 域认证）**
- Keycloak **LDAP 用户联邦**对接 Active Directory：域账号+密码经 LDAP BIND 校验，工号取 AD `sAMAccountName`/`employeeNumber`。
- **Kerberos/SPNEGO**：域内 PC 浏览器可无缝登录（需 krb5 配置 + 域控可达）。
- **注意：Keycloak 不原生支持 NTLM**（纯 NTLM 的旧系统需适配器或改走 Kerberos/LDAP）。

**推荐总架构（未来多系统统一 SSO）**：`各系统(SP) → Keycloak(IdP, 联邦 AD/LDAP + broker 企微/钉钉/飞书) → 统一发 employee_number(工号)`。本系统按本设计的 P0 接入层直接接 Keycloak 即可，无需再改代码。
