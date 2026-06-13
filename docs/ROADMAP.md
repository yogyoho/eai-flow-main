# EAI-Flow 产品路线图与待实现需求

> 统一管理未来要实现的需求、设计方案和技术债务。
> 格式：每个条目包含背景、方案设计、涉及文件、优先级和状态。

---

## 🔐 License Features 校验

**优先级**: 中 | **状态**: 待实现 | **日期**: 2026-06-11

### 背景

License JWT 中的 `features` 字段（如 `agent_count`、`sandbox_type`、`gpu_enabled`）目前只存储和透传，没有任何业务代码读取或校验。厂商生成的 License 可设定这些值，但系统不会执行。

### 已实现（对照）

| 机制 | 状态 | 链路 |
|------|------|------|
| `modules` 模块授权 | ✅ 已实现 | JWT → `LicenseService.get_status()` → 前端 `hasModule()` → Sidebar 过滤 + `ModuleLockedPage` 拦截 |
| `max_users` 用户数限制 | ⚠️ 仅展示 | API 返回 `current_users` / `max_users`，但**未拦截超额用户登录** |
| `expires_at` 过期时间 | ✅ 已实现 | `LicenseService.verify()` 校验 exp，过期抛 `LICENSE_EXPIRED` |
| `features.*` 扩展特性 | ❌ 仅存储 | 无任何读取/校验逻辑 |

### 待实现 Features

#### 1. `agent_count` — 最大 Agent 数量限制

**方案**:
- 后端 `LicenseService` 新增 `get_feature_int(key, default)` 辅助方法，从当前 license payload 的 features 中取值
- `SubagentLimitMiddleware`（`deerflow/agents/middlewares/`）在 `MAX_CONCURRENT_SUBAGENTS` 初始化时读取 `agent_count`，覆盖默认值
- 超限时返回明确提示：`"当前许可证最多允许 N 个并发 Agent"`

**涉及文件**:
- `backend/app/extensions/license/service.py` — 新增 `get_feature_int()`
- `backend/packages/harness/deerflow/agents/middlewares/subagent_limit_middleware.py`
- `backend/app/extensions/license/routers.py` — status 接口可能需扩展

#### 2. `sandbox_type` — 沙箱类型限制

**方案**:
- `get_sandbox_provider()`（`deerflow/sandbox/`）初始化时校验 license `features.sandbox_type`
- 若 config.yaml 配置了 `docker` 沙箱但 license 仅允许 `local`，启动时发出 warning 并降级
- 前端设置页面可据此隐藏/禁用沙箱配置选项

**涉及文件**:
- `backend/packages/harness/deerflow/sandbox/` — provider 初始化逻辑
- `backend/app/extensions/license/service.py` — feature 读取
- `frontend/src/app/settings/page.tsx` — 条件显示

#### 3. `gpu_enabled` — GPU 功能开关

**方案**:
- 模型工厂（`deerflow/models/factory.py`）创建模型时检查 `gpu_enabled`
- 若 license 未授权 GPU 但用户配置了 GPU 模型，降级为 CPU 并记录 warning
- 可扩展为控制 GPU 相关工具（如 GPU 沙箱、图像批量处理等）

**涉及文件**:
- `backend/packages/harness/deerflow/models/factory.py`
- `backend/app/extensions/license/service.py`

#### 4. `max_users` — 用户数硬限制

**方案**:
- 登录接口（`/api/v1/auth/login/local`）在认证成功后检查 `current_users >= max_users`
- 超额时拒绝登录，返回 `403 {"detail": "许可证用户数已达上限"}`
- Admin 用户始终允许登录（防止锁死）
- 需要定时或登录时统计活跃用户数

**涉及文件**:
- `backend/app/gateway/app.py` 或 auth 路由
- `backend/app/extensions/license/service.py` — 新增 `check_user_limit()`

### 通用实现建议

1. **Feature 读取统一入口**: 在 `LicenseService` 中增加：
   ```python
   @staticmethod
   def get_feature(key: str, default=None):
       """从当前 license 读取 feature 值，dev mode 返回宽松默认值"""
       payload = LicenseService.verify()
       return payload.features.get(key, default)

   @staticmethod
   def get_feature_int(key: str, default: int = 0) -> int:
       val = LicenseService.get_feature(key, default)
       return int(val) if val is not None else default
   ```

2. **缓存**: `verify()` 结果应短时缓存（如 5 分钟），避免每次请求都解析 JWT

3. **Dev Mode 兜底**: `_is_dev_mode()` 时所有 feature 返回宽松默认值，不阻塞开发

---

## 📋 需求模板（新增条目请复制此格式）

```
## [Emoji] 标题

**优先级**: 高/中/低 | **状态**: 待实现/设计中/开发中 | **日期**: YYYY-MM-DD

### 背景
为什么需要这个功能，解决什么问题。

### 方案设计
具体的技术方案、架构选择、接口设计。

### 涉及文件
- `path/to/file.py` — 改动说明

### 备注
其他需要考虑的事项。
```

---

*最后更新: 2026-06-11*
