# DeerFlow 许可证功能操作手册

> 版本 2.0 | 2026-06-09

## 目录

1. [概述](#1-概述)
2. [架构原理](#2-架构原理)
3. [厂商操作](#3-厂商操作)
4. [客户操作](#4-客户操作)
5. [开发者操作](#5-开发者操作)
6. [前端集成](#6-前端集成)
7. [API 参考](#7-api-参考)
8. [系统状态流转](#8-系统状态流转)
9. [故障排查](#9-故障排查)
10. [附录](#10-附录)

---

## 1. 概述

DeerFlow 采用 **离线 JWT + RSA-2048 签名** 的许可证控制方案，无需联网验证。

### 1.1 工作流程

```
厂商生成 RSA 密钥对 → 根据客户 machine_id 签发 .lic 文件 → 交付客户
客户在管理后台上传 .lic → 后端用内嵌公钥验签 → 解锁对应功能模块
```

### 1.2 许可证控制维度

| 维度 | 说明 | 示例 |
|------|------|------|
| **机器绑定** | 许可证与部署实例的 `machine_id` 绑定 | `F1B9DE46-2BFA-47C5-BA39-7CD18D7ACDB7` |
| **功能模块** | 独立控制每个扩展模块的可用性 | `project: true, knowledge: false` |
| **用户数量** | 限制最大激活用户数 | `max_users: 50` |
| **有效期** | 永久授权（无 exp 字段）或限时试用（含 exp 时间戳） | 30 天试用 / 永久 |
| **扩展特性** | 自定义 key=value 配额 | `agent_count=5` |

### 1.3 可用模块列表

| 模块名 | 中文含义 |
|--------|----------|
| `project` | 项目管理 |
| `docmgr` | 文档管理 |
| `knowledge` | 知识库 |
| `collab` | 协同编辑 |
| `report` | 报告生成 |
| `approval` | 审批流程 |
| `workflow` | 工作流 |
| `dashboard` | 仪表盘 |

---

## 2. 架构原理

### 2.1 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        DeerFlow 系统                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ 前端 (Next.js)                                           │    │
│  │                                                          │    │
│  │  LicenseShell ──┬─ GracePeriodBanner  (宽限期顶部横幅)    │    │
│  │                 ├─ SystemLockedPage    (系统锁定全屏页)    │    │
│  │                 ├─ ModuleLockedPage    (模块未授权提示页)  │    │
│  │                 ├─ DevModeBanner       (开发模式水印)      │    │
│  │                 └─ LicensePage         (管理页面)          │    │
│  │                                                          │    │
│  │  useLicense() Hook ── TanStack Query ── 5 分钟自动刷新   │    │
│  └──────────────┬───────────────────────────────────────────┘    │
│                 │ GET /api/license/status                        │
│  ┌──────────────▼───────────────────────────────────────────┐    │
│  │ 后端 (FastAPI Gateway)                                    │    │
│  │                                                          │    │
│  │  LicenseService.verify()                                  │    │
│  │    ├─ 1. 检查 DEV_MODE → 返回开发模式 Payload             │    │
│  │    ├─ 2. 读取 .lic 文件 → JWT 签名验证                   │    │
│  │    └─ 3. 无许可证 → 计算宽限期                           │    │
│  │                                                          │    │
│  │  public_key.pem (内嵌) ── RS256 验签                     │    │
│  │  License 表 (PostgreSQL) ── 导入历史记录                  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ 厂商侧工具 (tools/license/)                               │    │
│  │                                                          │    │
│  │  generate_keys.py   ── 生成 RSA-2048 密钥对              │    │
│  │  license_generator.py ── 签发 .lic 文件                   │    │
│  │  private_key.pem    ── 签名私钥 (保密!)                   │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 JWT Payload 结构

签发的许可证 JWT 包含以下字段：

```json
{
  "iss": "DeerFlow",
  "iat": 1749200400,
  "jti": "LIC-A1B2C3D4",
  "sub": "F1B9DE46-2BFA-47C5-BA39-7CD18D7ACDB7",
  "type": "permanent",
  "customer": "XX科技有限公司",
  "max_users": 50,
  "modules": {
    "project": true,
    "docmgr": true,
    "knowledge": true,
    "collab": false,
    "report": false,
    "approval": false,
    "workflow": false,
    "dashboard": false
  },
  "features": {},
  "meta": {
    "contact": "support@deerflow.com",
    "order_id": "ORD-E5F6G7H8"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `iss` | string | 签发者，固定 `DeerFlow` |
| `iat` | int | 签发时间 (Unix 时间戳) |
| `jti` | string | 许可证唯一 ID，格式 `LIC-XXXXXXXX` |
| `sub` | string | 绑定的 `machine_id` |
| `type` | string | `permanent`（永久）或 `trial`（试用） |
| `customer` | string | 客户名称 |
| `max_users` | int/null | 最大用户数限制 |
| `modules` | object | 模块授权字典，`true`=已授权 |
| `features` | object | 扩展特性配额 |
| `exp` | int | 过期时间戳（永久授权无此字段） |
| `meta` | object | 元数据（联系信息、订单号） |

### 2.3 machine_id 生成算法

```python
raw = platform.node() + str(uuid.getnode())
machine_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
```

由 `hostname` + `MAC 地址` 的 SHA-256 哈希前 32 位组成，保证每台服务器唯一。

### 2.4 文件清单

```
# 厂商侧（不随产品分发）
tools/license/
├── generate_keys.py           # RSA 密钥对生成工具
├── license_generator.py       # 许可证签发工具
├── license_request.json       # 申请文件模板
├── private_key.pem            # RSA 私钥（⚠️ 绝密，不入库不分发）
├── public_key.pem             # RSA 公钥（也随产品分发）
└── OPERATIONS_MANUAL.md       # 本操作手册

# 产品后端（随 DeerFlow 分发）
backend/app/extensions/license/
├── __init__.py                # 模块入口，导出 LicenseService + router
├── schemas.py                 # Pydantic 响应模型
├── models.py                  # SQLAlchemy License 表模型
├── service.py                 # 核心验证逻辑（JWT 验签、宽限期、开发模式）
├── routers.py                 # FastAPI API 路由
└── public_key.pem             # RSA 公钥（用于验签）

# 产品前端（随 DeerFlow 分发）
frontend/src/extensions/license/
├── api.ts                     # API 客户端（status/import/history/export）
├── useLicense.ts              # React Hook（TanStack Query 封装）
├── LicenseShell.tsx           # 根布局集成（系统锁定拦截）
├── LicensePage.tsx            # 管理页面（导入/导出/历史）
├── DevModeBanner.tsx          # 开发模式水印（右下角浮窗）
├── GracePeriodBanner.tsx      # 宽限期横幅（顶部黄色提示条）
├── SystemLockedPage.tsx       # 系统锁定页（全屏🔒提示）
└── ModuleLockedPage.tsx       # 模块未授权页（🚫提示）
```

---

## 3. 厂商操作

> 以下操作在厂商侧执行，需要 Python 3.12+ 和 `cryptography`、`PyJWT` 库。

### 3.1 第一步：生成密钥对（仅需一次）

```bash
cd tools/license
pip install cryptography PyJWT
python generate_keys.py
```

**输出文件：**

| 文件 | 用途 | 安全要求 |
|------|------|----------|
| `private_key.pem` | 签发许可证 | **绝密** — 厂商保管，不入 Git，不分发 |
| `public_key.pem` | 验证许可证 | 随产品分发到 `backend/app/extensions/license/` |

> ⚠️ **私钥丢失 = 无法签发新许可证。请安全备份私钥文件。**

### 3.2 第二步：获取客户机器 ID

客户需提供其部署实例的 `machine_id`，获取方式：

**方式一：API 查询（推荐）**
```bash
# 在客户服务器上执行
curl http://localhost:2026/api/license/status | python -c "import sys,json; print(json.load(sys.stdin).get('machine_id',''))"
```

**方式二：管理后台**
客户登录 DeerFlow 管理后台 → 导航到 **许可证管理** 页面，页面中会显示当前 `machine_id`。

> 💡 注意：如果客户处于宽限期（无许可证），`machine_id` 字段返回 `null`，此时需要客户通过其他方式获取（例如在 Docker 容器内运行 Python）。

### 3.3 第三步：签发许可证

**3.3.1 创建申请文件**

编辑 `license_request.json`，填入客户信息：

```json
{
  "machine_id": "客户提供的32位hex字符串",
  "generated_at": "2026-06-09T10:00:00Z",
  "system_info": {
    "hostname": "prod-server-01",
    "platform": "linux"
  }
}
```

> `system_info` 仅作备注用途，不影响许可证内容。

**3.3.2 执行签发命令**

```bash
cd tools/license
```

**场景 A — 30 天全功能试用：**

```bash
python license_generator.py license_request.json \
  --days 30 \
  --all-modules \
  --customer "XX科技有限公司" \
  --output license.lic
```

**场景 B — 永久授权，指定模块，限制用户数：**

```bash
python license_generator.py license_request.json \
  --permanent \
  --modules project,docmgr,knowledge,collab \
  --customer "XX科技有限公司" \
  --max-users 100 \
  --output license.lic
```

**场景 C — 永久授权，全模块，无用户限制：**

```bash
python license_generator.py license_request.json \
  --permanent \
  --all-modules \
  --customer "XX科技有限公司" \
  --output license.lic
```

**场景 D — 带扩展配额：**

```bash
python license_generator.py license_request.json \
  --permanent \
  --all-modules \
  --customer "XX科技有限公司" \
  --max-users 50 \
  --features agent_count=5,sandbox_type=docker \
  --output license.lic
```

### 3.4 参数完整说明

| 参数 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `request_file` | ✅ | 申请 JSON 文件路径 | `license_request.json` |
| `--days` | ❌ | 试用有效期天数（默认 30） | `--days 90` |
| `--permanent` | ❌ | 标记为永久授权（无过期时间） | `--permanent` |
| `--all-modules` | ❌ | 启用全部 8 个模块 | `--all-modules` |
| `--modules` | ❌ | 指定模块列表，逗号分隔 | `--modules project,docmgr` |
| `--customer` | ❌ | 客户名称 | `--customer "XX科技"` |
| `--max-users` | ❌ | 最大并发用户数 | `--max-users 50` |
| `--features` | ❌ | 扩展配额，`key=value` 逗号分隔 | `--features agent_count=5` |
| `--output` | ❌ | 输出文件路径（默认 `license.lic`） | `--output license.lic` |

> 💡 如果既不指定 `--all-modules` 也不指定 `--modules`，默认只启用 `project` 和 `docmgr` 两个模块。

### 3.5 第四步：交付许可证

将生成的 `license.lic` 文件通过安全渠道交付给客户。客户通过管理后台上传导入。

---

## 4. 客户操作

### 4.1 查看许可证状态

**方式一：管理后台（推荐）**

1. 登录 DeerFlow
2. 导航到 **许可证管理** 页面
3. 页面显示以下信息：
   - 当前许可证状态（✅ 有效 / ⏳ 宽限期 / ❌ 无效）
   - 许可证类型（永久 / 试用）
   - 客户名称
   - 到期时间和剩余天数
   - 用户数使用情况（`当前 / 最大`）
   - 模块授权列表（🟢 绿色=已授权，⚪ 灰色=未授权）
   - 预警信息（橙色提示框）

**方式二：API 查询**

```bash
curl http://localhost:2026/api/license/status
```

**宽限期响应示例：**

```json
{
  "valid": false,
  "machine_id": null,
  "type": null,
  "customer": null,
  "max_users": null,
  "current_users": 6,
  "modules": {},
  "features": {},
  "expires_at": null,
  "days_remaining": null,
  "in_grace_period": true,
  "grace_period_remaining_days": 6,
  "warnings": ["grace_period_active"],
  "is_dev_mode": false
}
```

**有效许可证响应示例：**

```json
{
  "valid": true,
  "machine_id": "F1B9DE46-2BFA-47C5-BA39-7CD18D7ACDB7",
  "type": "permanent",
  "customer": "XX科技有限公司",
  "max_users": 50,
  "current_users": 23,
  "modules": {
    "project": true,
    "docmgr": true,
    "knowledge": true,
    "collab": false,
    "report": false,
    "approval": false,
    "workflow": false,
    "dashboard": false
  },
  "features": {},
  "expires_at": null,
  "days_remaining": null,
  "in_grace_period": false,
  "grace_period_remaining_days": null,
  "warnings": [],
  "is_dev_mode": false
}
```

### 4.2 导入许可证

1. 获取厂商提供的 `license.lic` 文件
2. 登录 DeerFlow 管理后台
3. 进入 **许可证管理** 页面
4. 点击 **「选择 .lic 文件」** 按钮
5. 选择 `license.lic` 文件
6. 看到 **「许可证导入成功」** 提示即完成

> ⚠️ **注意事项：**
> - 导入前请确认 `machine_id` 匹配，否则会提示 **"机器不匹配"** 错误
> - 同一许可证不可重复导入（基于 `jti` 唯一 ID 校验）
> - 导入新许可证后，旧许可证自动停用
> - 成功导入后，宽限期计时器会被清除

### 4.3 导出许可证

在管理后台的 **「导出许可证」** 区域，点击 **「下载 license.lic」** 按钮，可导出当前生效的许可证文件（用于备份或迁移）。

> 💡 仅在许可证有效时显示导出按钮。

### 4.4 查看导入历史

管理后台的 **「导入历史」** 区域以表格形式展示所有历史导入记录：

| 列 | 说明 |
|----|------|
| 许可证 ID | JWT 唯一标识 (jti) |
| 类型 | 永久 / 试用 |
| 客户 | 客户名称 |
| 导入时间 | 导入的时间戳 |
| 状态 | 🟢 生效中 / 已替换 |

### 4.5 系统行为对照表

| 系统状态 | 触发条件 | 用户体验 |
|----------|----------|----------|
| **正常使用** | 有效许可证已导入 | 按授权使用已购模块 |
| **宽限期** | 首次部署，无许可证 | 顶部显示黄色横幅「⏳ 许可证未激活，N 天后系统将锁定」；所有功能可正常使用 |
| **模块未授权** | 许可证不含该模块 | 导航栏不显示该模块入口；直接访问 URL 显示 🚫「XX模块未授权」页面 |
| **用户超限** | 激活用户数超过授权 | 显示 `user_limit_nearing` 预警 |
| **系统锁定** | 宽限期结束且无许可证 | 显示全屏 🔒「系统未激活」页面；仅管理员可登录 |
| **许可证过期** | 试用许可证到期 | 所有功能锁定，需导入新许可证 |

### 4.6 预警信息

| 预警代码 | 触发条件 | 含义 |
|----------|----------|------|
| `grace_period_active` | 宽限期进行中 | 倒计时结束前需导入许可证 |
| `license_expiring_soon` | 到期前 ≤30 天 | 提前联系厂商续期 |
| `trial_ending` | 试用到期前 ≤7 天 | 试用即将结束 |
| `user_limit_nearing` | 用户数达到授权上限 90% | 接近用户上限 |

---

## 5. 开发者操作

### 5.1 启用开发模式

开发模式下跳过所有许可证验证，适合本地开发调试。

**方法：设置环境变量**

```yaml
# docker-compose-dev.yaml gateway 服务
environment:
  - DEER_FLOW_DEV_MODE=true
  - DEER_FLOW_ENV=development    # 必须设置为非 production
```

重启 Gateway：

```bash
docker compose -p eai-docker restart gateway
```

**效果：**
- 所有 API 返回全模块授权（`modules: { project: true, ...全部 true }`）
- `max_users` 返回 `9999`
- 前端右下角显示 **`DEV MODE — License Bypassed`** 水印
- 无需导入许可证文件
- `machine_id` 返回 `DEV-MODE`

**安全保护：** 如果 `DEER_FLOW_ENV=production` 且 `DEER_FLOW_DEV_MODE=true`，Gateway 启动时直接 **报错退出**，防止误配置到生产环境。

### 5.2 验证开发模式已生效

```bash
curl -s http://localhost:2026/api/license/status | python -m json.tool
```

期望返回中包含：
```json
{
  "is_dev_mode": true,
  "machine_id": "DEV-MODE",
  "type": "permanent",
  "valid": true
}
```

### 5.3 本地测试许可证生成

```bash
cd tools/license

# 1. 生成密钥（首次或需要更新密钥时）
python generate_keys.py

# 2. 生成测试许可证（使用模板中的 machine_id）
python license_generator.py license_request.json \
  --permanent --all-modules \
  --customer "DEV-TEST" \
  --output test.lic

# 3. 导入测试许可证
# 方式 A：管理后台上传 test.lic
# 方式 B：复制到扫描路径
cp test.lic ../../backend/license.lic         # 项目 backend 目录
```

> 💡 后端会按以下顺序扫描许可证文件：
> 1. `/etc/deerflow/license.lic`（Docker 生产路径）
> 2. `<项目根目录>/license.lic`
> 3. `<项目根目录>/backend/license.lic`

### 5.4 宽限期模拟

重置宽限期计时器（仅开发/测试用）：

```bash
# Docker 环境
docker exec deer-flow-gateway rm -f /app/backend/.deer-flow/license_start.log
docker compose -p eai-docker restart gateway
```

宽限期计时器文件位于 `backend/.deer-flow/license_start.log`，首次启动时自动创建，记录启动时间戳。删除后重启将重新开始 7 天宽限期倒计时。

> 成功导入许可证后，计时器文件会被自动删除。

### 5.5 配置项

#### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEER_FLOW_DEV_MODE` | 开发者模式（`true`/`1`/`yes`） | 未设置 |
| `DEER_FLOW_ENV` | 运行环境（`production` 时拒绝 DEV_MODE） | 未设置 |
| `GRACE_PERIOD_DAYS` | 宽限期天数 | `7` |
| `LICENSE_FILE_PATH` | 许可证文件路径 | `/etc/deerflow/license.lic` |

#### config.yaml

```yaml
license:
  public_key_path: backend/app/extensions/license/public_key.pem
  license_file_path: /etc/deerflow/license.lic
  grace_period_days: 7
```

---

## 6. 前端集成

### 6.1 LicenseShell 布局组件

`LicenseShell` 是许可证的根级集成组件，包裹在应用最外层：

```tsx
<LicenseShell>
  <App />        {/* 正常应用内容 */}
</LicenseShell>
```

**工作流程：**
1. 每 5 分钟轮询 `GET /api/license/status`
2. 根据状态渲染不同 UI：
   - `isLocked=true` → 显示 `SystemLockedPage`（替代子组件）
   - `inGracePeriod=true` → 显示 `GracePeriodBanner`（顶部横幅）
   - `isDevMode=true` → 显示 `DevModeBanner`（右下角水印）
   - 正常状态 → 直接渲染子组件

### 6.2 useLicense Hook

在任意 React 组件中使用许可证状态：

```tsx
import { useLicense } from "@/extensions/license/useLicense";

function MyComponent() {
  const {
    isValid,        // boolean — 许可证是否有效
    isDevMode,      // boolean — 是否开发模式
    inGracePeriod,  // boolean — 是否在宽限期
    isLocked,       // boolean — 系统是否锁定
    hasModule,      // (name: string) => boolean — 检查模块是否可用
    warnings,       // string[] — 活动预警列表
    gracePeriodDays,// number — 宽限期剩余天数
    status,         // LicenseStatus | undefined — 原始状态数据
    isLoading,      // boolean — 是否加载中
    isError,        // boolean — 请求是否失败
  } = useLicense();

  // 示例：条件渲染
  if (!hasModule("knowledge")) {
    return <ModuleLockedPage module="knowledge" />;
  }

  return <KnowledgeContent />;
}
```

> 💡 `hasModule()` 在宽限期期间始终返回 `true`，确保宽限期内所有功能可用。

### 6.3 各 UI 组件说明

| 组件 | 作用 | 位置 |
|------|------|------|
| `LicensePage` | 管理页面 — 状态查看、导入、导出、历史 | 管理后台路由页面 |
| `LicenseShell` | 根布局 — 锁定拦截、横幅显示 | App 最外层 |
| `GracePeriodBanner` | 宽限期横幅 — 顶部黄色「⏳ 许可证未激活」 | LicenseShell 内 |
| `SystemLockedPage` | 系统锁定页 — 全屏🔒「系统未激活」 | LicenseShell 内，替代 children |
| `ModuleLockedPage` | 模块锁定页 — 🚫「XX模块未授权」 | 各模块路由页面内 |
| `DevModeBanner` | 开发水印 — 右下角固定浮窗 | LicenseShell 内 |

---

## 7. API 参考

### 7.1 获取许可证状态

```
GET /api/license/status
```

**认证：** 无需认证（公开端点，供前端路由守卫使用）

**响应：** `LicenseStatusResponse`

| 字段 | 类型 | 说明 |
|------|------|------|
| `valid` | boolean | 许可证是否有效 |
| `machine_id` | string/null | 当前机器 ID |
| `type` | string/null | 许可证类型 (`permanent`/`trial`) |
| `customer` | string/null | 客户名称 |
| `max_users` | int/null | 最大用户数 |
| `current_users` | int | 当前活跃用户数 |
| `modules` | object | 模块授权状态 |
| `features` | object | 扩展特性 |
| `expires_at` | datetime/null | 到期时间 |
| `days_remaining` | int/null | 剩余天数 |
| `in_grace_period` | boolean | 是否在宽限期 |
| `grace_period_remaining_days` | int/null | 宽限期剩余天数 |
| `warnings` | string[] | 预警列表 |
| `is_dev_mode` | boolean | 是否开发模式 |

### 7.2 导入许可证

```
POST /api/license/import
```

**认证：** 需要管理员权限 (`require_permission("admin")`)

**请求：** `multipart/form-data`，字段 `file` 为 `.lic` 文件

**成功响应：** `LicenseImportResponse`
```json
{
  "success": true,
  "machine_id": "F1B9DE46...",
  "type": "permanent",
  "customer": "XX科技有限公司",
  "message": "License imported successfully"
}
```

**错误响应 (400)：**
| 错误码 | 含义 |
|--------|------|
| `LICENSE_INVALID` | 许可证 JWT 验签失败 |
| `MACHINE_MISMATCH` | machine_id 与当前机器不匹配 |
| `DUPLICATE_LICENSE` | 该许可证已导入过 |

### 7.3 获取导入历史

```
GET /api/license/history?skip=0&limit=20
```

**认证：** 需要管理员权限

**参数：**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `skip` | int | 0 | 跳过记录数 |
| `limit` | int | 20 | 每页数量 (1-100) |

**响应：** `LicenseHistoryResponse`
```json
{
  "items": [
    {
      "id": "uuid",
      "jwt_jti": "LIC-A1B2C3D4",
      "machine_id": "F1B9DE46...",
      "type": "permanent",
      "customer": "XX科技有限公司",
      "max_users": 50,
      "modules": { "project": true, ... },
      "issued_at": "2026-06-09T10:00:00Z",
      "expires_at": null,
      "imported_at": "2026-06-09T11:00:00Z",
      "is_active": true
    }
  ],
  "total": 1
}
```

### 7.4 导出许可证

```
GET /api/license/export
```

**认证：** 需要管理员权限

**成功响应：** `application/octet-stream`，文件名 `license.lic`

**错误响应 (404)：** 无活跃许可证

---

## 8. 系统状态流转

```
首次部署（无许可证）
    │
    ▼
┌─────────────────────┐
│  宽限期 (7天)        │ ← 自动开始，顶部显示黄色横幅
│  • 所有功能可用      │
│  • 倒计时提示        │
└──────────┬──────────┘
           │
     ┌─────┴──────────────────────┐
     │                            │
     ▼ (7天后)                    ▼ (导入许可证)
┌──────────────────┐       ┌──────────────────────┐
│  系统锁定 🔒     │       │  正常使用 ✅          │
│  • 仅管理员登录  │       │  • 按授权使用已购模块  │
│  • 普通用户看到  │       │  • 模块级别访问控制    │
│    锁定页面      │       │  • 用户数量限制        │
└────────┬─────────┘       └──────────────────────┘
         │
         ▼ (导入许可证)
  ┌──────────────────────┐
  │  正常使用 ✅          │
  └──────────────────────┘
```

**验证优先级（`LicenseService.verify()`）：**

1. **DEV_MODE** → 立即返回开发模式 Payload（全模块、9999 用户）
2. **读取 .lic 文件** → JWT 签名验证 + 过期检查
3. **无许可证** → 计算宽限期（基于 `license_start.log` 时间戳）
   - 宽限期内 → 返回 `type: "grace"` Payload
   - 宽限期过 → 抛出 `LICENSE_MISSING` 异常

---

## 9. 故障排查

### 问题 1：导入许可证提示「机器不匹配」

**原因：** 许可证中的 `machine_id` 与当前服务器不一致。

**常见触发场景：**
- Docker 容器重建后 `.deer-flow/` 目录未持久化
- 迁移到新服务器
- hostname 或 MAC 地址发生变化

**解决步骤：**
1. 检查 Docker volume 是否正确挂载：
   ```bash
   docker inspect deer-flow-gateway | grep deerflow_data
   ```
2. 确认容器内 `.deer-flow/.machine_id` 文件：
   ```bash
   docker exec deer-flow-gateway cat /app/backend/.deer-flow/.machine_id 2>/dev/null
   ```
3. 获取当前真实 `machine_id`，联系厂商重新签发许可证

### 问题 2：Docker 重启后许可证失效

**原因：** `.deer-flow/` 目录未通过 Docker volume 持久化，导致许可证文件和历史记录丢失。

**检查和修复：**
```bash
# 检查当前配置
docker compose -p eai-docker config | grep -A5 gateway

# 确认包含 volume 映射
# volumes:
#   - ${DEER_FLOW_HOME}:/app/backend/.deer-flow
```

### 问题 3：系统锁定，管理员也无法登录

**原因：** 系统锁定后，`/api/license/status` 仍为公开端点，但认证系统本身可能受影响。

**解决步骤：**
```bash
# 方式一：通过 Docker 直接复制许可证到容器
docker cp license.lic deer-flow-gateway:/app/backend/license.lic
docker compose -p eai-docker restart gateway

# 方式二：临时启用 DEV_MODE 导入后关闭
# 在 docker-compose.yaml 中临时添加:
#   DEER_FLOW_DEV_MODE=true
#   DEER_FLOW_ENV=development
# 重启后通过管理后台导入许可证，然后移除环境变量并再次重启
```

### 问题 4：许可证 API 返回 401

**原因：** `/api/license/status` 未加入公共路径白名单。

**检查：** 确认 `backend/app/gateway/auth_middleware.py` 中包含：
```python
_PUBLIC_PATH_PREFIXES = (
    ...
    "/api/license/status",
)
```

### 问题 5：前端不显示宽限期 Banner

**排查步骤：**

1. **前端容器未重启**（代码更新后）：
   ```bash
   docker compose -p eai-docker restart frontend
   ```

2. **浏览器缓存**：硬刷新 `Ctrl+Shift+R`

3. **API 调用失败**：浏览器开发者工具 → Network 面板 → 检查 `/api/license/status` 请求

4. **GracePeriodBanner 组件**：该组件自行发起 API 请求（不依赖 `useLicense` Hook），确认其 useEffect 正常触发

### 问题 6：导入提示「许可证已导入过」

**原因：** 每个 `.lic` 文件有唯一 `jti`（如 `LIC-A1B2C3D4`），重复导入同一文件会被拒绝。

**解决：** 如果需要更换许可证，厂商需签发新的 `.lic` 文件（新 `jti`），或检查是否误传了旧文件。

### 问题 7：开发模式启动报错

**错误信息：** `DEER_FLOW_DEV_MODE is not allowed in production environment`

**原因：** 同时设置了 `DEER_FLOW_DEV_MODE=true` 和 `DEER_FLOW_ENV=production`。

**解决：**
- 开发/测试环境：设置 `DEER_FLOW_ENV=development`
- 生产环境：移除 `DEER_FLOW_DEV_MODE`

---

## 10. 附录

### 10.1 数据库模型

`License` 表存储许可证导入历史，位于 PostgreSQL 的 `licenses` 表中：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `jwt_jti` | String(64) | JWT 唯一 ID（唯一约束） |
| `machine_id` | String(64) | 绑定的机器 ID |
| `type` | String(20) | 许可证类型 |
| `customer` | String(200) | 客户名称 |
| `max_users` | Integer | 最大用户数 |
| `modules` | JSONB | 模块授权字典 |
| `features` | JSONB | 扩展特性字典 |
| `issued_at` | DateTime | 签发时间 |
| `expires_at` | DateTime | 过期时间 |
| `meta` | JSONB | 元数据 |
| `jwt_raw` | Text | 原始 JWT 字符串 |
| `imported_at` | DateTime | 导入时间 |
| `is_active` | Boolean | 是否当前活跃 |

> ⚠️ **注意：** 授权决策始终基于实时 JWT 验证，不依赖此表。此表仅用于管理界面显示和导入历史追踪。

### 10.2 许可证文件扫描路径

后端按以下顺序扫描许可证文件：

| 优先级 | 路径 | 适用场景 |
|--------|------|----------|
| 1 | `$LICENSE_FILE_PATH`（默认 `/etc/deerflow/license.lic`） | Docker 生产环境 |
| 2 | `<项目根目录>/license.lic` | 本地开发 |
| 3 | `<项目根目录>/backend/license.lic` | 本地开发 |

### 10.3 宽限期计算逻辑

```
宽限期开始时间 = backend/.deer-flow/license_start.log 中记录的 Unix 时间戳
宽限期时长 = GRACE_PERIOD_DAYS（默认 7 天）
剩余天数 = GRACE_PERIOD_DAYS - (当前时间 - 开始时间) / 86400
```

### 10.4 联系厂商

如需新许可证、续期或升级，请联系厂商并提供：

1. 当前 `machine_id`（管理后台「许可证管理」页面可查看）
2. 需要的功能模块列表
3. 期望的用户数量
4. 期望的授权类型（永久 / 试用天数）

厂商将签发新的 `.lic` 文件交付。
