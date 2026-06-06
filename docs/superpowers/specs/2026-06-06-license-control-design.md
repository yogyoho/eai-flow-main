# License 控制系统设计

生成于 2026-06-06 | 分支: merge-2.0-rc | 状态: DRAFT

## 概述

为 DeerFlow 设计离线许可证控制系统，实现多维度部署授权管理。

## 需求

| 维度 | 选择 |
|------|------|
| 控制维度 | 机器绑定 + 用户数 + 功能模块 + 有效期（全维度） |
| 验证方式 | 完全离线，JWT + RSA-2048 签名 |
| 管理方式 | 厂商 CLI 工具 + 系统内管理页面 |
| 拦截点 | 前端路由级控制 |
| 部署环境 | Docker，开发环境需后门绕过 |

## 前提

1. 前端路由拦截足够保护许可证控制 —— 内部部署系统，后端 API 不加许可证拦截
2. 离线 JWT+RSA 是合适的验证机制 —— 不依赖外部 License Server
3. 开发者后门仅在非生产环境生效 —— 生产环境拒绝 DEV_MODE
4. 首版不需要许可证撤销机制 —— 撤销依赖许可证到期自然失效

## 整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                         厂商侧（离线）                                 │
│  tools/license/                                                       │
│  ├── generate_keys.py      → 生成 RSA-2048 密钥对                     │
│  ├── license_generator.py  → 生成 .lic 文件（JWT 签名）               │
│  ├── private_key.pem       → 私钥（厂商保留，不入库，不分发）           │
│  └── public_key.pem        → 公钥（随产品分发，嵌入 Gateway）           │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ license.lic（交付给客户）
┌──────────────────────────────────────────────────────────────────────┐
│                       客户部署环境（DeerFlow）                          │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                     Nginx :2026                                │    │
│  └──────────────────────────────────────────────────────────────┘    │
│           │                              │                            │
│           ▼                              ▼                            │
│  ┌──────────────────┐       ┌──────────────────────────────┐        │
│  │  Frontend :4000  │       │  Gateway :8001               │        │
│  │                  │       │                              │        │
│  │  useLicense()    │──1──▶│  GET /api/license/status      │        │
│  │  (路由守卫)       │       │  (无需认证)                   │        │
│  │                  │       │                              │        │
│  │  Admin License   │──2──▶│  LicenseService              │        │
│  │  Page (导入/查看) │       │  ├── verify(jwt) → payload   │        │
│  │                  │       │  ├── sync_to_db(payload)     │        │
│  │  GracePeriod     │       │  ├── check_user_limit()      │        │
│  │  Banner (宽限期)  │       │  ├── check_grace_period()    │        │
│  │                  │       │  └── get_enabled_modules()   │        │
│  │  DevModeBanner   │       │                              │        │
│  │  (开发水印)       │       │  防误用: production 拒绝      │        │
│  │                  │       │  DEV_MODE                    │        │
│  └──────────────────┘       └──────┬───────────┬───────────┘        │
│                                    │           │                     │
│                           ┌────────▼───┐ ┌─────▼──────────┐         │
│                           │ license.lic│ │  PostgreSQL     │         │
│                           │ (JWT 文件)  │ │  licenses 表    │         │
│                           │            │ │  (元数据镜像)    │         │
│                           └────────────┘ └────────────────┘         │
│                                                                       │
│  Docker 持久化: backend/.deer-flow/ → volume 挂载                     │
│  ├── .machine_id        (machine_id 缓存)                             │
│  └── license_start.log  (首次运行时间戳，宽限期计算)                    │
└──────────────────────────────────────────────────────────────────────┘
```

## JWT Payload 设计

```json
{
  "iss": "DeerFlow",
  "iat": 1717632000,
  "exp": 1735689600,
  "jti": "LIC-2024-0001",
  "sub": "F1B9DE46-2BFA-47C5-BA39-7CD18D7ACDB7",
  "type": "permanent",
  "customer": "XX科技有限公司",
  "max_users": 50,
  "modules": {
    "project": true,
    "docmgr": true,
    "knowledge": true,
    "collab": false,
    "report": false
  },
  "features": {
    "agent_count": 3,
    "sandbox_type": "docker"
  },
  "meta": {
    "contact": "support@vendor.com",
    "order_id": "ORD-2024-00123"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `sub` | string | machine_id，绑定部署实例 |
| `jti` | string | 许可证唯一 ID，防重复导入 |
| `type` | string | `permanent` / `trial` / `subscription` |
| `exp` | int? | 过期时间戳（permanent 无此字段） |
| `max_users` | int? | 最大激活用户数，null=不限制 |
| `modules` | object | 功能模块开关 |
| `features` | object | 扩展能力配额 |
| `meta` | object | 厂商信息，供管理页面展示 |

## Machine ID 生成策略

```
Machine ID = SHA256(MAC地址 + 磁盘序列号 + 主机名)[:32]
```

优先级：
1. 读取 `/etc/machine-id`（Linux）或注册表 `MachineGuid`（Windows）
2. 回退：取默认路由网卡 MAC + 根分区磁盘 UUID 组合
3. 缓存到 `backend/.deer-flow/.machine_id`，首次生成后复用

**Docker 持久化：** `backend/.deer-flow/` 目录必须通过 Docker volume 持久化，确保容器重建后 machine_id 一致。docker-compose 配置：

```yaml
services:
  gateway:
    volumes:
      - deerflow_data:/app/backend/.deer-flow

volumes:
  deerflow_data:
```

## 开发者后门

```python
# backend/app/extensions/license/service.py

class LicenseService:
    def verify(self) -> LicensePayload:
        # 1. 生产环境保护：拒绝 DEV_MODE
        env = os.getenv("DEER_FLOW_ENV", "")
        dev_mode = os.getenv("DEER_FLOW_DEV_MODE", "").lower() in ("1", "true", "yes")

        if dev_mode:
            if env == "production":
                raise RuntimeError(
                    "DEER_FLOW_DEV_MODE is not allowed in production environment. "
                    "Set DEER_FLOW_ENV to something other than 'production' or disable DEV_MODE."
                )
            return LicensePayload.dev_mode()

        # 2. 正常验证流程...
```

```python
# dev_mode payload 工厂方法
@classmethod
def dev_mode(cls) -> "LicensePayload":
    return cls(
        machine_id="DEV-MODE",
        type="permanent",
        customer="DEVELOPMENT",
        max_users=9999,
        modules={"project": True, "docmgr": True, "knowledge": True, "collab": True, "report": True},
        features={"agent_count": 99, "sandbox_type": "docker"},
        meta={"contact": "dev@localhost", "order_id": "DEV-SKIP"},
    )
```

**Docker 开发环境配置：**

```yaml
# docker-compose.yml (开发用)
services:
  gateway:
    environment:
      - DEER_FLOW_DEV_MODE=true
      - DEER_FLOW_ENV=development   # 非 production，允许 DEV_MODE
```

**前端水印：** 开发模式下右下角显示半透明 `DEV MODE — License Bypassed` 水印，防止误发包。

## 宽限期机制

license 文件缺失时系统不应直接锁定，而是提供宽限期。

```
宽限期 = 7 天（可配置 GRACE_PERIOD_DAYS）
```

**流程：**
1. 首次启动时记录时间戳到 `backend/.deer-flow/license_start.log`
2. 宽限期内：前端显示倒计时 banner "许可证未激活，X 天后系统将锁定"，功能正常使用
3. 宽限期结束 + 无有效许可证：非管理员用户不可登录，管理员仍可进入许可证管理页面导入
4. 导入有效许可证后：宽限期状态立即清除

**实现要点：**
- `GET /api/license/status` 返回 `in_grace_period` 和 `grace_period_remaining_days` 字段
- 前端路由守卫：宽限期内全模块可用（`hasModule` 直接返回 true）
- 前端路由守卫：`!valid && !in_grace_period` → 系统锁定
- 管理员路由始终可访问（管理员登录不受许可证限制）

## 数据库模型

```sql
CREATE TABLE licenses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jwt_jti       VARCHAR(64) NOT NULL UNIQUE,
    machine_id    VARCHAR(64) NOT NULL,
    type          VARCHAR(20) NOT NULL,               -- permanent | trial | subscription
    customer      VARCHAR(200),
    max_users     INTEGER,
    modules       JSONB NOT NULL DEFAULT '{}',
    features      JSONB NOT NULL DEFAULT '{}',
    issued_at     TIMESTAMP NOT NULL,
    expires_at    TIMESTAMP,
    meta          JSONB NOT NULL DEFAULT '{}',
    jwt_raw       TEXT NOT NULL,
    imported_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_licenses_active ON licenses(is_active) WHERE is_active = TRUE;
```

**设计要点：**
- `is_active` — 同一时刻只有一条记录为 TRUE，导入新许可证时旧记录标记 FALSE
- `jwt_raw` 保留原始 JWT，方便管理页导出/下载
- 授权判断始终实时验证 JWT 文件，不依赖 DB 记录

## API 设计

### `GET /api/license/status`（无需认证）

```json
{
  "valid": true,
  "machine_id": "F1B9DE46-...",
  "type": "permanent",
  "customer": "XX科技有限公司",
  "max_users": 50,
  "current_users": 23,
  "modules": {"project": true, "docmgr": true, "knowledge": true, "collab": false},
  "expires_at": null,
  "days_remaining": null,
  "in_grace_period": false,
  "grace_period_remaining_days": null,
  "warnings": [],
  "is_dev_mode": false
}
```

**warnings 预警规则：**
- `license_expiring_soon` — 到期前 30 天
- `user_limit_nearing` — 用户数达到 90%
- `trial_ending` — trial 类型到期前 7 天
- `grace_period_active` — 宽限期中

### `POST /api/license/import`（需管理员权限）

校验链：
1. JWT 签名验证（RSA-256 公钥）
2. `machine_id` 与当前机器匹配
3. `jti` 未重复导入
4. 通过后写入 DB + 标记 `is_active=true`，清除宽限期状态

### `GET /api/license/history`（需管理员权限）

返回许可证导入历史列表。

### `GET /api/license/export`（需管理员权限）

下载当前生效的 `.lic` 文件。

## 前端路由守卫

```tsx
// frontend/src/extensions/license/useLicense.ts
function useLicense() {
  const { data } = useQuery({
    queryKey: ["license", "status"],
    queryFn: () => api.getLicenseStatus(),
    refetchInterval: 5 * 60 * 1000,
  });

  return {
    isDevMode: data?.is_dev_mode ?? false,
    isValid: data?.valid ?? false,
    inGracePeriod: (data?.grace_period_remaining_days ?? 0) > 0,
    isLocked: !data?.valid && !data?.in_grace_period,
    modules: data?.modules ?? {},
    // 宽限期内全模块可用，宽限期结束→按许可证实际模块
    hasModule: (name: string) =>
      data?.in_grace_period || (data?.valid && data.modules[name]),
    warnings: data?.warnings ?? [],
  };
}
```

```tsx
// 路由配置使用
<ProtectedRoute
  path="/projects"
  guard={(license) => license.hasModule("project")}
  fallback={<ModuleLockedPage module="project" />}
>
  <ProjectWorkspace />
</ProtectedRoute>
```

**宽限期 Banner：** 宽限期内顶部显示黄色倒计时 banner。
**系统锁定页：** 宽限期结束且无许可证 → 非管理员用户看到锁定页面。
**模块锁定页：** 许可证有效但模块未授权 → 显示模块名称 + 管理员联系方式。

## 厂商 CLI 工具

```
tools/license/
├── generate_keys.py          # RSA-2048 密钥对生成
├── license_generator.py      # 许可证生成
├── private_key.pem           # 私钥（厂商保管）
├── public_key.pem            # 公钥（随产品分发）
├── license_request.json      # 示例申请文件
└── README.md                 # 使用说明
```

### 用法

```bash
# 生成 30 天试用许可证
python license_generator.py license_request.json --days 30

# 生成永久全模块许可证
python license_generator.py license_request.json \
  --permanent \
  --customer "XX科技" \
  --max-users 50 \
  --modules project,docmgr,knowledge \
  --output license.lic
```

## 文件结构

```
# 厂商侧
tools/license/
├── generate_keys.py
├── license_generator.py
├── private_key.pem
├── license_request.json
└── README.md

# 产品侧
backend/app/extensions/license/
├── __init__.py
├── models.py           # License DB Model
├── service.py          # LicenseService（核心逻辑）
├── routers.py          # /api/license/* 路由
├── schemas.py          # Pydantic 模型
└── public_key.pem      # RSA 公钥

frontend/src/extensions/license/
├── api.ts              # API 调用
├── useLicense.ts       # React hook（路由守卫）
├── LicensePage.tsx      # 管理页面
├── ModuleLockedPage.tsx # 未授权模块页
├── GracePeriodBanner.tsx # 宽限期倒计时
├── SystemLockedPage.tsx  # 系统锁定页
└── DevModeBanner.tsx     # 开发者水印

# 配置
config.yaml:
  license:
    public_key_path: backend/app/extensions/license/public_key.pem
    license_file_path: /etc/deerflow/license.lic
    grace_period_days: 7

# Docker 持久化
docker-compose.yml:
  volumes:
    - deerflow_data:/app/backend/.deer-flow
```

## 实施优先级

| 优先级 | 组件 | 说明 |
|--------|------|------|
| P0 | `license_generator.py` + 密钥工具 | 厂商工具 |
| P0 | `LicenseService`（验证 + dev_mode + 宽限期） | 核心逻辑 |
| P0 | `GET /api/license/status` | 前端路由守卫依赖 |
| P0 | `useLicense` hook + 路由守卫 + 宽限期 Banner | 前端拦截 |
| P1 | License DB Model + `POST /api/license/import` | 管理功能 |
| P1 | LicensePage + ModuleLockedPage + SystemLockedPage | 管理 UI |
| P1 | Docker volume 持久化 `.deer-flow/` | 容器重建保护 |
| P2 | 到期预警 + 用户数预警 | 运维提醒 |
| P2 | `GET /api/license/history` + `GET /api/license/export` | 管理功能完善 |

## 错误处理

| 场景 | 行为 |
|------|------|
| license 文件缺失 + 首次部署 | 7 天宽限期，显示倒计时 banner |
| license 文件缺失 + 宽限期结束 | 锁定系统，非管理员不可登录 |
| license 签名无效 | API 返回 valid=false，前端锁定对应模块 |
| license 已过期 | API 返回 valid=false + days_remaining=0 |
| machine_id 不匹配 | 导入时拒绝，返回 "许可证与当前机器不匹配" |
| jti 重复导入 | 拒绝，返回 "该许可证已导入过" |
| Docker 容器重建（有 volume） | machine_id 不变，许可证持续有效 |
| Docker 容器重建（无 volume） | machine_id 变化 → 许可证失效 → 需重新授权 |
| 生产环境 DEV_MODE=true | Gateway 启动时抛出 RuntimeError |

## 安全边界

- `GET /api/license/status` 无需认证 —— 内部部署系统的有意取舍，不暴露敏感商业数据
- 系统时间回滚检测：记录最近一次验证时间戳，如果当前时间 < 上次验证时间 → 触发 `clock_tampered` 警告
- 公钥嵌入后端代码，不可通过 API 修改
- 管理员登录不受许可证限制，确保始终可导入新许可证

## 未解决的问题

- 许可证到期后的通知机制（邮件/站内信？）—— 首版不做，P2
- 多实例部署共享许可证？—— 首版不支持，每实例独立授权
- 许可证中 features 字段的具体使用方式 —— 由各扩展模块自行读取
