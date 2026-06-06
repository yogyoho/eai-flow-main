# DeerFlow 许可证功能操作手册

> 版本 1.0 | 2026-06-06

## 目录

1. [概述](#概述)
2. [厂商操作](#厂商操作)
3. [客户操作](#客户操作)
4. [开发者操作](#开发者操作)
5. [故障排查](#故障排查)
6. [附录](#附录)

---

## 概述

DeerFlow 采用 **离线 JWT + RSA-2048 签名** 的许可证控制方案。

```
厂商生成密钥对 → 签发许可证(.lic) → 交付客户
客户导入 .lic → 系统验证签名 → 解锁功能模块
```

**许可证控制维度：**
- **机器绑定** — 许可证与部署实例的 machine_id 绑定
- **功能模块** — 控制每个扩展模块的可用性
- **用户数量** — 限制最大激活用户数
- **有效期** — 支持永久授权和限时试用

**系统状态流转：**

```
首次部署（无许可证）
    │
    ▼
┌─────────────┐    7天后     ┌──────────────┐
│  宽限期     │ ──────────▶  │  系统锁定     │
│  (7天)      │              │  (仅管理员)   │
└─────────────┘              └──────┬───────┘
    │                               │
    │  导入许可证                   │  导入许可证
    ▼                               ▼
┌─────────────┐              ┌──────────────┐
│  正常使用    │              │  正常使用     │
│  (按授权)    │              │  (按授权)     │
└─────────────┘              └──────────────┘
```

---

## 厂商操作

> 以下操作在厂商侧执行，需要 Python 3.12+ 和 `cryptography`、`PyJWT` 库。

### 第一步：生成密钥对（仅需一次）

```bash
cd tools/license
pip install cryptography PyJWT
python generate_keys.py
```

**输出文件：**

| 文件 | 用途 | 安全要求 |
|------|------|----------|
| `private_key.pem` | 签发许可证 | **绝密** — 厂商保管，不入库，不分发 |
| `public_key.pem` | 验证许可证 | 随产品分发到 `backend/app/extensions/license/` |

> ⚠️ **私钥丢失 = 无法签发新许可证。请安全备份。**

### 第二步：获取客户机器 ID

让客户在 DeerFlow 管理后台 **许可证管理** 页面获取当前机器的 `machine_id`，或运行：

```bash
# 在客户服务器上执行
curl http://localhost:2026/api/license/status | grep machine_id
```

客户提交授权申请时需提供 `machine_id`。

### 第三步：签发许可证

**创建申请文件** `license_request.json`：

```json
{
  "machine_id": "客户提供的machine_id",
  "generated_at": "2026-06-06T10:00:00Z",
  "system_info": {
    "hostname": "prod-server-01",
    "platform": "linux"
  }
}
```

**常用签发命令：**

```bash
# 30天全功能试用
python license_generator.py license_request.json \
  --days 30 \
  --all-modules \
  --customer "XX科技有限公司" \
  --output license.lic

# 永久授权，指定模块
python license_generator.py license_request.json \
  --permanent \
  --modules project,docmgr,knowledge,collab \
  --customer "XX科技有限公司" \
  --max-users 100 \
  --output license.lic

# 永久授权，全模块，无用户限制
python license_generator.py license_request.json \
  --permanent \
  --all-modules \
  --customer "XX科技有限公司" \
  --output license.lic
```

### 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `request_file` | 申请 JSON 文件路径（必填） | `license_request.json` |
| `--days` | 有效期天数（默认 30） | `--days 90` |
| `--permanent` | 永久授权 | `--permanent` |
| `--all-modules` | 启用所有模块 | `--all-modules` |
| `--modules` | 指定模块列表，逗号分隔 | `--modules project,docmgr` |
| `--customer` | 客户名称 | `--customer "XX科技"` |
| `--max-users` | 最大用户数 | `--max-users 50` |
| `--features` | 扩展配额，key=value 逗号分隔 | `--features agent_count=5` |
| `--output` | 输出文件路径 | `--output license.lic` |

### 可用模块列表

| 模块名 | 对应功能 |
|--------|----------|
| `project` | 项目管理 |
| `docmgr` | 文档管理 |
| `knowledge` | 知识库 |
| `collab` | 协同编辑 |
| `report` | 报告生成 |
| `approval` | 审批流程 |
| `workflow` | 工作流 |
| `dashboard` | 仪表盘 |

### 第四步：交付许可证

将生成的 `license.lic` 文件交付给客户。客户通过管理后台导入。

---

## 客户操作

### 查看许可证状态

**方法一：管理后台**

登录 DeerFlow → 导航到 **许可证管理** 页面。页面显示：

- 当前许可证状态（有效/宽限期/已过期）
- 许可证类型（永久/试用）
- 到期时间和剩余天数
- 用户数使用情况
- 模块授权列表（绿色=已授权，灰色=未授权）

**方法二：API 查询**

```bash
curl http://localhost:2026/api/license/status
```

响应示例（宽限期）：

```json
{
  "valid": false,
  "in_grace_period": true,
  "grace_period_remaining_days": 6,
  "warnings": ["grace_period_active"],
  "is_dev_mode": false,
  "current_users": 6
}
```

响应示例（有效许可证）：

```json
{
  "valid": true,
  "type": "permanent",
  "customer": "XX科技有限公司",
  "max_users": 50,
  "current_users": 23,
  "modules": {
    "project": true,
    "docmgr": true,
    "knowledge": true,
    "collab": false
  },
  "days_remaining": null,
  "in_grace_period": false,
  "warnings": [],
  "is_dev_mode": false
}
```

### 导入许可证

1. 获取厂商提供的 `license.lic` 文件
2. 登录 DeerFlow 管理后台
3. 进入 **许可证管理** 页面
4. 点击 **选择 .lic 文件** 按钮
5. 选择 `license.lic` 文件
6. 看到 "许可证导入成功" 提示即完成

> ⚠️ 导入前请确认 `machine_id` 匹配。不匹配会提示错误。

### 导出许可证

在管理后台点击 **下载 license.lic** 按钮，可导出当前生效的许可证文件（用于备份）。

### 理解系统行为

| 系统状态 | 触发条件 | 用户影响 |
|----------|----------|----------|
| **正常使用** | 有效许可证已导入 | 按授权使用已购模块 |
| **宽限期** | 首次部署，无许可证 | 所有功能可正常使用，显示倒计时 |
| **模块锁定** | 许可证不含该模块 | 访问该模块时显示"未授权"页面 |
| **用户超限** | 激活用户数超过授权 | 显示警告，新用户无法激活 |
| **系统锁定** | 宽限期结束且无许可证 | 仅管理员可登录，其他用户看到锁定页 |
| **许可证过期** | 试用/订阅到期 | 所有功能锁定，需导入新许可证 |

### 预警信息

| 预警 | 触发条件 | 说明 |
|------|----------|------|
| `grace_period_active` | 宽限期进行中 | 倒计时结束前需导入许可证 |
| `license_expiring_soon` | 到期前 30 天 | 提前联系厂商续期 |
| `trial_ending` | 试用到期前 7 天 | 试用即将结束 |
| `user_limit_nearing` | 用户数达到 90% | 接近用户上限 |

---

## 开发者操作

### 启用开发模式

在 Docker 开发环境中设置环境变量跳过后端许可证验证：

```yaml
# docker-compose-dev.yaml gateway 服务
environment:
  - DEER_FLOW_DEV_MODE=true
  - DEER_FLOW_ENV=development    # 必须非 production
```

重启 Gateway：

```bash
docker compose -p eai-docker restart gateway
```

**效果：**
- 所有 API 返回全模块授权
- 前端右下角显示 `DEV MODE — License Bypassed` 水印
- 无需导入许可证文件

**安全保护：** 如果 `DEER_FLOW_ENV=production` 且 `DEV_MODE=true`，Gateway 启动时直接报错退出，防止误配置到生产环境。

### 验证开发模式已生效

```bash
curl http://localhost:2026/api/license/status
```

期望返回：`"is_dev_mode": true, "machine_id": "DEV-MODE"`

### 本地测试许可证生成

```bash
cd tools/license

# 1. 生成密钥
python generate_keys.py

# 2. 生成测试许可证
python license_generator.py license_request.json \
  --permanent --all-modules \
  --customer "DEV-TEST" \
  --output test.lic

# 3. 在管理后台导入 test.lic

# 4. 或直接放置到扫描路径
cp test.lic /etc/deerflow/license.lic  # Docker 容器内
# 或
cp test.lic backend/license.lic         # 项目 backend 目录
```

### 宽限期模拟

删除 `backend/.deer-flow/license_start.log` 文件可重置宽限期计时器：

```bash
# Docker 环境
docker exec deer-flow-gateway rm /app/backend/.deer-flow/license_start.log
docker compose -p eai-docker restart gateway
```

---

## 故障排查

### 问题：导入许可证提示 "机器不匹配"

**原因：** 许可证中的 `machine_id` 与当前机器不一致。

常见于：
- Docker 容器重建后 `.deer-flow/` 目录未持久化
- 迁移到新服务器

**解决：**
1. 检查 Docker volume 是否正确挂载：`docker inspect deer-flow-gateway | grep deerflow_data`
2. 确认 `.deer-flow/.machine_id` 文件存在且内容一致
3. 联系厂商重新签发（提供新的 `machine_id`）

### 问题：Docker 重启后许可证失效

**原因：** `.deer-flow/` 目录未通过 volume 持久化。

**检查：**
```bash
docker compose -p eai-docker config | grep -A5 gateway
```

确认配置中包含：
```yaml
volumes:
  - ${DEER_FLOW_HOME}:/app/backend/.deer-flow
```

### 问题：系统锁定，管理员也无法登录

**原因：** `require_permission("admin")` 依赖 JWT 认证，如果认证系统本身受许可证影响，可能形成死锁。

**解决：**
1. 通过 Docker 直接操作：
   ```bash
   # 复制许可证到容器内
   docker cp license.lic deer-flow-gateway:/app/backend/license.lic
   docker compose -p eai-docker restart gateway
   ```
2. 如果仍无法访问，临时启用 DEV_MODE 导入许可证后关闭。

### 问题：许可证 API 返回 401

**原因：** `/api/license/status` 路径未加入公共路径白名单。

**检查：** 确认 `backend/app/gateway/auth_middleware.py` 中包含：
```python
_PUBLIC_PATH_PREFIXES = (
    ...
    "/api/license/status",
)
```

### 问题：前端不显示宽限期 Banner

**可能原因：**
1. 前端容器未重启：`docker compose -p eai-docker restart frontend`
2. 浏览器缓存：硬刷新（Ctrl+Shift+R）
3. API 调用失败：浏览器控制台检查 `/api/license/status` 请求

---

## 附录

### 文件清单

```
# 厂商侧（不随产品分发）
tools/license/
├── generate_keys.py          # RSA 密钥生成
├── license_generator.py      # 许可证签发
├── license_request.json      # 申请文件模板
├── private_key.pem           # RSA 私钥（保密）
└── README.md                 # 使用说明

# 产品侧（随 DeerFlow 分发）
backend/app/extensions/license/
├── __init__.py               # 模块入口
├── schemas.py                # 数据模型
├── models.py                 # DB 模型
├── service.py                # 核心逻辑
├── routers.py                # API 路由
└── public_key.pem            # RSA 公钥

frontend/src/extensions/license/
├── api.ts                    # API 客户端
├── useLicense.ts             # React Hook
├── LicenseShell.tsx          # 根布局集成
├── LicensePage.tsx           # 管理页面
├── DevModeBanner.tsx         # 开发模式水印
├── GracePeriodBanner.tsx     # 宽限期 Banner
├── SystemLockedPage.tsx      # 系统锁定页
└── ModuleLockedPage.tsx      # 模块锁定页
```

### API 速查

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/api/license/status` | GET | 无 | 许可证状态（前端路由守卫用） |
| `/api/license/import` | POST | 管理员 | 导入 .lic 文件 |
| `/api/license/history` | GET | 管理员 | 导入历史 |
| `/api/license/export` | GET | 管理员 | 下载当前 .lic 文件 |

### 配置项

```yaml
# config.yaml
license:
  public_key_path: backend/app/extensions/license/public_key.pem
  license_file_path: /etc/deerflow/license.lic
  grace_period_days: 7
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEER_FLOW_DEV_MODE` | 开发者模式（`true`/`1`/`yes`） | 无 |
| `DEER_FLOW_ENV` | 运行环境（`production` 时拒绝 DEV_MODE） | 无 |
| `GRACE_PERIOD_DAYS` | 宽限期天数 | 7 |
| `LICENSE_FILE_PATH` | 许可证文件路径 | `/etc/deerflow/license.lic` |

### 联系厂商

如需新许可证、续期或升级，请联系：

- 提供当前 `machine_id`（在管理后台可查看）
- 说明需要的模块和用户数
- 厂商将签发新的 `.lic` 文件
