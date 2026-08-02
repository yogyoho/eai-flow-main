# EAI 统一认证门面设计文档

- 日期：2026-08-02
- 状态：已定稿（待用户评审）
- 范围：企业内网登录方式统一为「工号+密码」与「邮箱+验证码」双轨并存，零上游 deerflow 代码改动

## 1. 背景与目标

企业内部应用很少使用 email+password 登录：日常登录惯用**工号+密码**；email 登录的通行做法是**邮箱+验证码**。当前系统实际只有一条活的认证链（上游 email+password），与上述企业习惯不符；同时存在一套已被架空的 username+password 遗留流程。本设计在**不动上游 deerflow**（便于上游代码更新）的约束下，将登录入口统一收敛到 EAI 层。

**目标：**
1. 登录页提供两种方式并存：**工号+密码**（主）与 **邮箱+验证码**。
2. **零上游代码改动**——只 import 复用上游零件，不修改 `packages/harness/*` 与 `app/gateway/auth/*`。
3. 以 extensions PostgreSQL 为**组织目录真源**（工号、部门、角色、启停），gateway 为**会话层**。
4. 企业无自注册：用户由管理员统一创建并绑定角色（现有 admin 用户管理 + sync 已覆盖）。
5. 为后续 SSO 单点登录预留统一会话签发例程。

## 2. 现状调查（已验证）

### 2.1 两套认证流程并存

**上游 deerflow email+password（当前唯一活着的主登录）**
- 前端唯一登录页 `frontend/src/app/(auth)/login/page.tsx` → `POST /api/v1/auth/login/local`
- 后端 `backend/app/gateway/routers/auth.py`（`login_local`/`register`/`initialize`/OIDC）+ `app/gateway/auth/local_provider.py`
- 用户存 Gateway **SQLite** `users` 表（仅 `email`，无 username；argon2 密码哈希）
- 会话：HttpOnly `access_token` cookie（Gateway JWT）+ CSRF double-submit；角色 `system_role`（admin/user）；支持 OIDC/SSO

**原系统 username+password（遗留死代码）**
- `backend/app/extensions/auth/routers.py` → `POST /api/extensions/auth/login`，按 `User.username` 查 **PostgreSQL（agentflow DB）**，签自己的 JWT
- 前端已删除调用（`frontend/src/extensions/api/index.ts:210` 注释 "endpoints have been removed"）；无测试引用；router 仍挂载于 `backend/app/gateway/app.py:522`

**两套已被中间件桥接**
- `backend/app/extensions/auth/middleware.py::get_current_user` 不再走 username+password，而是读 **Gateway `access_token` cookie** → `get_current_user_from_request` 验证 → 按 `email` 在 PostgreSQL **自动创建/匹配** extensions 用户（首访自动建行，admin 自动给 `superadmin`）。`username` 退化为 `email.split("@")[0]` 派生值。

### 2.2 数据现状

- Gateway SQLite `users`：17 人，email-only，真实用户约 9 人（admin/zhangsan/lisi/wanger/zhaoliu/yang/yang2/huangwt/test-procurement），其余测试号。
- Extensions PostgreSQL `users`：29 行，其中约 16 行是软删的 `#deleted-<ts>` 后缀；活跃真用户约 9 人；字段含 username/email/full_name/dept_id/role_id/status。
- 两库按 email 基本 1:1 对应；存在漂移（部分 gateway 活跃账号在 extensions 已被软删，bridge 会在下次登录时重建）。

### 2.3 已存在的复用资产

- `backend/app/extensions/user/sync.py`：admin 在 extensions 建号/改密/禁用/删号时，**自动同步 gateway 用户**（argon2 密码镜像、system_role 映射、`token_version` 提升吊销会话）。即"admin 建号 → gateway 镜像行存在"已通。
- `app/gateway/deps.py::get_local_provider()`：EAI 代码可 import 复用，取 gateway LocalAuthProvider（`authenticate`/`get_user_by_email`/`create_user`）。
- `app.gateway.auth::create_access_token(user_id, token_version)`：EAI 代码可 import 复用，签发 gateway JWT。
- `app/extensions/auth/middleware.py::ACCESS_TOKEN_COOKIE = "access_token"`：与 gateway 会话 cookie 同名，天然兼容。
- 上游**无任何发邮件能力**（全仓库仅命中 `SMTP_PASS` 环境变量名）；无 OTP/验证码逻辑。

## 3. 设计约束

| 约束 | 说明 |
|---|---|
| 不动上游 | 不修改 `packages/harness/deerflow/*` 与 `backend/app/gateway/auth/*`；上游文件改动一律加 EAI-CUSTOM 注释 |
| 单一人力入口 | 用户由 admin 统一创建/绑角色（无自注册） |
| 门面通用化 | 所有登录方式共享尾部例程：**解析身份 → 保证 gateway 行 → 签发会话** |
| extensions 为组织目录真源 | 工号/部门/角色/启停在 extensions；gateway 仅做会话/凭证镜像 |

## 4. 架构总览

```
                        ┌──────────────────────────────────────────┐
  登录页（双 tab）        │              EAI 登录门面                  │
 ┌───────────────┐       │        backend/app/extensions/auth/      │
 │ 工号+密码 tab  │──────▶│  POST /login        (重写)                │
 │ 邮箱验证码 tab │──────▶│  POST /otp/send     (新增)                │
 └───────────────┘       │  POST /login/otp    (新增)                │
        │                └──────┬────────────────────┬──────────────┘
        │                       │ 解析身份             │ 验证
        │                       ▼                     ▼
        │             extensions PostgreSQL      [SMTP 发码]
        │             （工号/email/角色/状态）    （企业 SMTP）
        │                       │
        │                       ▼  保证 gateway 行（sync 已镜像，兜底查/建）
        │        get_local_provider().authenticate / create_user
        │                       │
        │                       ▼  复用 create_access_token()
        └─────────────── HttpOnly access_token cookie（同上游会话）
        │
        ▼
  agent 运行时 / extensions 中间件（bridge）——零改动
```

**职责划分**：extensions = 组织目录真源；gateway = 会话/凭证层（由 `sync.py` 维持镜像）；两者以 **email** 为映射键。

## 5. 详细设计

### 5.1 密码登录门面（重写 `app/extensions/auth/routers.py::login`）

```
POST /api/extensions/auth/login   { username, password }
1. username 兼容工号或 email。
2. 按 username 查 extensions User（排除 is_deleted）；查不到且像 email 则按 email 查。拿到 user.email。
3. 校验 user.status == "active"，否则 403。
4. 复用 get_local_provider().authenticate({"email": user.email, "password": password})
   - 失败：best-effort 重试一次 sync.sync_user_created(email, password, role_id) 自愈（覆盖 sync 曾失败的网关行缺失），仍失败 → 401。
5. token = create_access_token(str(gw_user.id), token_version=gw_user.token_version)
6. 设 access_token HttpOnly cookie（httponly, samesite=lax, secure 按请求, max_age=config.token_expiry_days*3600）。
7. 返回 { expires_in, needs_setup }（与上游 login_local 同构）。
8. per-IP 登录限流（镜像上游 _MAX_LOGIN_ATTEMPTS 模式，EAI 本地实现，不 import 上游私有函数）。
```

要点：密码验证委托给 gateway argon2（admin 建号/改密时 sync 已保证镜像有效）；extensions 只做"工号 → email"目录解析。这是与现有会话最自洽、改动最小的取向（已与用户确认）。

### 5.2 邮箱验证码登录（新增 `app/extensions/auth/otp.py`）

```
POST /api/extensions/auth/otp/send   { email }
1. 按 email 查 extensions User（排除 is_deleted）；不存在 → 统一返回成功（防枚举），但记日志。
2. 限流：每 email 1 次/分钟；每 IP 每小时上限。
3. 生成 6 位数字验证码；TTL 5 分钟；单次使用。
4. 存 otp_codes 表（code 存 bcrypt 哈希——6 位数字熵低，必须慢哈希防离线爆破；复用 `app/extensions/auth/jwt.py::hash_password`）。
5. 企业 SMTP 发邮件（smtplib；配置见 5.5）。
6. 返回 { sent: true }。仅当 `smtp.enabled == false`（dev/占位模式）时将验证码回显到响应，生产必须关闭。
```

```
POST /api/extensions/auth/login/otp   { email, code }
1. 查 otp_codes 最新未用记录：存在、未过期、`verify_password(code, code_hash)`（bcrypt）匹配 → 通过；否则 401（"验证码错误或已过期"）。
2. 标记 used_at。
3. 按 email 找 extensions User；不存在 → 401。
4. 保证 gateway 行：get_local_provider().get_user_by_email(email) 不存在则 create_user(email, password=None)（password_hash 可空，OAuth 同款）。
5. 签发会话（同 5.1 第 5-7 步）。
6. per-IP / per-email 验证限流。
```

表结构（extensions DB，SQLAlchemy 模型 `OtpCode`）：

```sql
otp_codes (
  id            uuid primary key,
  email         varchar(255) not null,
  code_hash     varchar(255) not null,   -- bcrypt/sha256
  expires_at    timestamptz not null,
  used_at       timestamptz null,
  created_at    timestamptz not null
)
```

清理：登录/发送时惰性删除已过期行；可加定时清理（低频，非必须）。

### 5.3 会话签发（共用例程）

提取 `_issue_gateway_session(email, request, response) -> LoginResponse`：
1. `provider = get_local_provider()`；`gw_user = await provider.get_user_by_email(email)`；不存在 → `provider.create_user(email=email, password=None, system_role=<按 extensions 角色推导>, needs_setup=False)`。
2. `token = create_access_token(str(gw_user.id), token_version=gw_user.token_version)`。
3. 设 cookie（同 5.1）。
4. 返回 `LoginResponse(expires_in=..., needs_setup=False)`。

密码登录与验证码登录、以及未来 SSO 共用此例程。

### 5.4 前端登录页（`frontend/src/app/(auth)/login/page.tsx`，EAI-CUSTOM）

- 两个 tab：**工号+密码** / **邮箱验证码**。
- 密码 tab：`username` + `password` → `POST /api/extensions/auth/login`（JSON）。
- 验证码 tab：`email` → `POST /api/extensions/auth/otp/send`（60s 重发倒计时）→ `code` → `POST /api/extensions/auth/login/otp`。
- 会话 cookie 机制不变（credentials: include）；重定向逻辑不变。
- `core/auth/remember-login.ts`："记住我"改存 username（验证码 tab 可存 email）。
- 该文件已是 EAI 定制页，改动加 EAI-CUSTOM 注释。

### 5.5 配置（SMTP）

extensions 配置新增（`backend/app/extensions/config.py` + 对应 `extensions_config.json` 或独立小节）：

```yaml
auth_smtp:
  host: ""            # 企业 SMTP
  port: 465           # 465(SSL) 或 587(STARTTLS)
  user: ""
  password: ""
  from: "no-reply@eai-flow.com"
  use_tls: true
  enabled: false      # 关闭时走 dev 回显占位
otp:
  length: 6
  ttl_seconds: 300
  send_cooldown_seconds: 60
  max_per_ip_per_hour: 20
```

### 5.6 数据模型

- 新增 `otp_codes` 表（见 5.2），由 extensions SQLAlchemy 模型 + 启动建表（沿用现有 `create_all` 模式）。
- 不改 gateway SQLite 表结构（零上游变更）。
- 不改 extensions `users` 表结构。

## 6. 安全设计

| 项 | 要求 |
|---|---|
| 验证码 | 6 位数字、TTL 5min、单次使用、DB 存 bcrypt 哈希 |
| 限流 | `otp/send` 每邮箱 1/min + 每 IP 每小时上限；`otp/login` 与 `login` 每 IP 尝试上限（镜像上游锁定期模式） |
| 防枚举 | `otp/send` 对不存在邮箱返回统一成功；日志记录 |
| 会话 | 保持 HttpOnly cookie + CSRF double-submit；cookie Secure 按请求判定 |
| 密码 | 委托 gateway argon2 验证（已有）；不落地明文 |
| 停用 | extensions `status != active` 拒绝登录；禁用/删号由 sync 提升 token_version 吊销现有会话（已有） |

## 7. 数据与迁移

- **零数据迁移**。
- 存量 ~9 真人：gateway 哈希有效 → 密码 tab 直接可用（工号→email→gateway 验证）。
- 验证码 tab 不依赖任何存量哈希。
- gateway-only 测试账号（无 extensions 行）两个 tab 均无法登录——符合"admin 统一建号"企业模型，不处理。
- 现有软删漂移：密码 tab 按 extensions 查询自然排除软删行；不再需要 bridge 自动重建（bridge 仍保留兼容）。

## 8. 不做的事（Out of Scope）

- 不改上游 email+password 流程；不删上游 `/register`/`/initialize`（保持挂起，前端无入口，仅 `/initialize` 用于首个 admin 引导）。
- 不做自注册、不做自助改密 UI（密码由 admin 管理，走现有 extensions 用户管理 + sync）。
- 不做 SSO 落地（本期仅预留门面例程，见 §9）。
- 不做 LDAP/AD 目录同步（后续 SSO 阶段评估）。
- 不改 gateway `users` 表结构、不动 harness。

## 9. SSO 路线图（后续）

- 复用 5.3 `_issue_gateway_session`：OIDC 登录后按 IdP 工号/sub → 解析 extensions username → 同一会话例程。
- 上游自带 OIDC 基建（`/api/v1/auth/oauth/*`），本期不动；未来可在 EAI 层加自己的 OIDC 回调做工号映射。

## 10. 测试计划

新增 `backend/tests/test_extensions_auth_facade.py`（TDD 必配）：

| 分组 | 用例 |
|---|---|
| 密码登录 | 工号登录成功；email 别名成功；用户名不存在 401；密码错误 401；停用用户 403；限流 429 |
| OTP | send 成功；send 邮箱不存在（统一成功）；send 限流；login/otp 成功；过期失败；已用失败；错码失败；限流 |
| 会话 | 两种方式返回的 cookie 均可被 `get_current_user_from_request` 解析；gateway 行缺失时自动补建 |
| 边界 | extensions 软删用户不可登录；gateway sync 失败自愈路径 |

前端：现有 E2E mock 登录流更新为双 tab；单元测试更新 `remember-login` 存储键。

## 11. 文档更新

- `backend/CLAUDE.md`：认证章节（双轨登录、extensions 目录 / gateway 会话、OTP、SMTP 配置）。
- `frontend/AGENTS.md`：认证说明（登录页双 tab、端点）。
- 本设计文档归档。

## 12. 验收标准

1. 登录页双 tab 可用；工号+密码与邮箱+验证码均能进入工作台。
2. 全程零上游代码改动（`git diff` 不含 `packages/harness/*` 与 `app/gateway/auth/*` 的修改，除既有 EAI-CUSTOM 定制）。
3. admin 建号/改密/禁用 → 对应登录行为正确（新建可登录、改密后旧会话失效、禁用后拒绝）。
4. `make test` 通过（新增 facade 测试全绿）。
5. 无自注册入口；`/register` 前端不可达。
