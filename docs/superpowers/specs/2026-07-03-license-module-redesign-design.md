# License 模块控制重构设计（Module Taxonomy Redesign）

生成于 2026-07-03 | 分支: main-dev-fork | 状态: DRAFT
修订自: [2026-06-06-license-control-design.md](./2026-06-06-license-control-design.md)

## 背景与动机

license 控制架构（JWT+RSA、机器绑定、宽限期、dev_mode、前端路由守卫）由旧设计确立并已落地。**本次不改动架构**，仅重构「模块分类」。

现状问题（`ALL_MODULES` 8 键：project/docmgr/knowledge/collab/report/approval/workflow/dashboard）：

- **粒度错配**——把应免费的 `knowledge`/`knowledge-factory` 设为收费；把应收费的 `dashboard`/`contract_price` 设为免费（见种子数据实测）。
- **强耦合拆键**——project / collab / workflow / approval / review 本是「项目协作」一个商业能力的子能力，拆成多键会产生「有协同写作没项目」这类无意义组合。其中 approval（审批面板组件）、review（纯后端阶段评审）**连独立页面都没有**，不该是独立许可面。
- **新模块缺位**——`contract_price` 完全不在清单内。正式 license 一上线，前端 `hasModule("contract_price")` 恒为 false，合同价格分析整块从应用中心消失（线上事故风险）。

**目标**：收敛为 4 个许可键；基础平台模块永远免费（`license_module = NULL`，不进 modules dict）。

## 设计前提（沿用旧设计，不变）

1. 拦截点 = 前端路由/应用级守卫；**后端 API 不加 license 拦截**（内部部署系统的有意取舍，旧设计前提 #1）。
2. 离线 JWT + RSA-2048，machine_id 绑定。
3. dev_mode 仅非生产环境生效；license 缺失走 7 天宽限期。
4. 首版无撤销机制（依赖到期自然失效）。
5. `GET /api/license/status` 无需鉴权。

> **本次重构 = 方案 1（最小改动 + 硬切换）**。已确认线上部署均跑 DEV_MODE/grace、无正式 `.lic` 在用，硬切换零成本。

## 最终分类

### 🟢 基础平台（永远免费，`license_module = NULL`，不进 modules dict）

| 应用 | 路由 |
|---|---|
| 智能写作 | `/writing` + `/workspace`（chats/agents，整体并入 writing） |
| 文档空间·我的文档 | `/docmgr`（个人文档部分） |
| 知识库 | `/knowledge` |
| 知识工厂 | `/knowledge-factory` |
| 应用中心 | `/app-center` |
| 系统管理 | `/admin`（+users/roles/departments） |
| 基本设置 | `/settings` |
| 数据源 / 插件 / CAD设计 | `/data-sources`、`/plugins`、`/cad-design` |

> 法律法规库 `law` / 网页抓取 `web_scraper` / 数据源 `data_source` 是 agent 的数据能力（MCP），经应用中心/知识库间接使用，非独立用户应用；模型管理 `models` 系统级——均免费、不单设许可键。

### 🔴 许可模块（4 键）

| 键 | 覆盖页面/功能 |
|---|---|
| `project` | `/projects` + 项目文件夹(docmgr 项目文档) + 协同写作(collab) + `/workflow-admin` 流程配置 + 审批(approval) + 评审(review) |
| `dashboard` | `/dashboard` 工作台 |
| `typography` | `/output` 报告输出 |
| `contract_price` | `/contract-price/*` 合同价格分析 |

### docmgr 分裂处理（唯一特殊项）

`/docmgr` 页面本身免费（我的文档始终可用）；页面内「项目文件夹」子视图额外挂 `project` 键——在 docmgr 前端组件渲染项目文件夹入口时加 `hasModule("project")` 守卫，未授权则隐藏入口或显示 `ModuleLockedPage`。`projects` 应用本身已挂 `project`，进入 `/projects` 即受控。

## 5 处同步点（必须一致，任一遗漏则行为分裂）

### 1. `backend/app/extensions/license/service.py:30` — `ALL_MODULES`

```python
ALL_MODULES = ["project", "dashboard", "typography", "contract_price"]
```

> `LicensePayload.dev_mode()` 的 `{m: True for m in ALL_MODULES}` 自动跟随，无需另改。

### 2. `tools/license/license_generator.py:28` — `ALL_MODULES`

同上 4 键。无 `--modules`/`--all-modules` 参数时的默认 `modules_dict` 改为 4 键全 True（旧默认 `{"project": True, "docmgr": True}` 中的 `docmgr` 已不再是许可键）。

### 3. `frontend/src/extensions/license/ModuleLockedPage.tsx:8` — `MODULE_LABELS`

```ts
const MODULE_LABELS: Record<string, string> = {
  project: "项目协作",
  dashboard: "工作台",
  typography: "报告输出",
  contract_price: "合同价格分析",
};
```

### 4. `backend/app/extensions/database.py` 种子 + 存量数据迁移

**种子 INSERT 块（约 line 1483-1514）`license` 字段调整：**

| app_id | 旧 license | 新 license | 说明 |
|---|---|---|---|
| `dashboard` | `None` | **`dashboard`** | 由免费转收费 |
| `smart-writing` | `None` | `None` | 不变 |
| `projects` | `project` | `project` | 不变 |
| `docmgr` | `docmgr` | **`None`** | 页面免费；项目文件夹走 `project` 子视图守卫 |
| `knowledge-factory` | `knowledge` | **`None`** | 由收费转免费 |
| `knowledge` | `knowledge` | **`None`** | 由收费转免费 |
| `output` | `report` | `typography` | 键改名 report→typography |
| `procurement`（合同价格） | `None` | **`contract_price`** | 由免费转收费 |
| `admin` | `None` | `None` | 不变（admin_only=True） |
| `workflow-admin` | `None` | **`project`** | 并入项目包（admin_only=True 保留） |

**⚠️ 关键：种子用 `ON CONFLICT (app_id) DO NOTHING`，存量库已插入的行不会被新种子更新。** 因此除改种子代码（供新部署）外，还需一个**一次性** UPDATE 迁移修存量行：

```sql
UPDATE app_definitions SET license_module = 'dashboard'    WHERE app_id = 'dashboard';
UPDATE app_definitions SET license_module = NULL           WHERE app_id IN ('docmgr','knowledge','knowledge-factory');
UPDATE app_definitions SET license_module = 'contract_price' WHERE app_id = 'procurement';
UPDATE app_definitions SET license_module = 'project'      WHERE app_id = 'workflow-admin';
UPDATE app_definitions SET license_module = 'typography'   WHERE app_id = 'output';
```

**放置方式**：做成只跑一次的迁移脚本（如 `scripts/migrate_license_modules_v2.py`），**不要**放进每次启动的 seed 段——否则每次启动都会覆盖管理员通过应用中心 UI 手动调整的 `license_module` 值。新部署靠改后的种子 INSERT 自动得到正确值，无需跑迁移。

> dev_mode / grace 下 `hasModule` 对所有模块返回 true，存量值错误暂时无害；但**必须在签发首张正式 license 前修对**，否则正式证一上，dashboard/contract_price 会被判未授权、knowledge 反而可能被错误门控。

### 5. `frontend/src/extensions/shell/Sidebar.tsx:47-56` — 侧边栏导航 `licenseModule`

侧边栏有一份**独立于 app-center 的硬编码导航清单**（不走 DB），同样用 `hasModule` 过滤（line 111）。调整：

| nav 项 | 旧 licenseModule | 新 |
|---|---|---|
| `/dashboard` 工作台 | _(无)_ | **`dashboard`** |
| `/projects` 报告项目 | `project` | `project` ✓ |
| `/docmgr` 文档空间 | `docmgr` | **删除**（页面免费） |
| `/knowledge-factory` 知识工厂 | `knowledge` | **删除** |
| `/knowledge` 知识库 | `knowledge` | **删除** |

> 只保留 `/projects: "project"`，新增 `/dashboard: "dashboard"`，三个免费项移除 `licenseModule` 字段。**漏改此项会导致免费模块在侧边栏消失**——`hasModule("docmgr")` 因键已不存在恒为 false。

## 不变项

- `LicenseService.verify / get_status / import_license / export_license / get_history`、宽限期、machine_id 生成：不动。
- `useLicense` hook、`LicenseShell`、`GracePeriodBanner`、`SystemLockedPage`、`DevModeBanner`：不动。
- `hasModule` 机制（dev_mode & grace 全开；否则查 modules dict）：不动。
- 后端 API 不加 license 拦截（沿用旧设计前提 #1）。
- JWT payload 字段结构（modules/features/meta 等）：不动。

## 向后兼容

**不做**（方案 1 硬切换）。旧 8 键 license 作废；新 license 只签 4 键。已确认无正式 `.lic` 在用，零客户影响。

## 测试

新增 `backend/tests/test_license_modules_sync.py`，锁住「5 处定义点必须一致」——纯 import/字符串断言，无需 DB：

- 断言 `service.ALL_MODULES` == `generator.ALL_MODULES` == `["project","dashboard","typography","contract_price"]`。
- 断言 `ModuleLockedPage` 的 `MODULE_LABELS` 键集合 == 同一集合（读源文件正则或导出常量）。
- 断言种子代码里 `license` 非 `None` 的 `app_id` 所对应的 license 值 ⊆ 4 键集合（防止再引入第 5 个键时种子与清单漂移）。
- 断言 `Sidebar.tsx` 里 `/dashboard`、`/projects` 带正确 `licenseModule`，`/docmgr`、`/knowledge`、`/knowledge-factory` 无 `licenseModule`（读源文件文本）。

> ponytail: 一个文件、四个断言、无 fixture。后续若某处清单改了而别处漏改，CI 立即失败。

## 风险与边界

- **docmgr 项目文件夹守卫**：在 `frontend/src/extensions/docmgr/DocumentManagement.tsx:237-264` 的「项目文件夹」区段（`archiveOpen` 按钮 + `ProjectFolderTree`）外层加 `hasModule("project")` 守卫，未授权则整段隐藏。**协同写作(collab) 无需单独守卫**——`CollabEditor` 仅在 `doc.project_id` 时渲染，而项目文档入口已被 `/projects`(Sidebar/应用中心) + docmgr 项目文件夹双重挡住，无 project 许可根本到不了项目文档。
- **workflow-admin 双重门槛**：`admin_only=True` + `license=project`，需管理员身份且部署具备 `project` 许可方可见。
- **cad-design 未在 app-center 种子**：当前 `/cad-design` 无 app 条目、无守卫 = 默认免费、直链可达。用户已定「先进基础平台」。若要让它出现在应用中心，补一条 `license=None` 的种子（可选，非阻塞）。
- 后端无强制是有意取舍（内部部署）；若未来对外商业化需真强制，再单独立项加 `require_module()` 依赖（届时应同步修订旧设计前提 #1）。

## 非目标

- 不加后端 license 拦截（不做 `require_module`）。
- 不做旧 license 归一/迁移层（无 `get_status` 键名翻译）。
- 不改 license JWT 字段结构。
- 不做撤销机制、不做到期通知。
