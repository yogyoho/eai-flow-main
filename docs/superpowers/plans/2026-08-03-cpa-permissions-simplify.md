# 合同价格权限收敛 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 合同价格分析权限收敛为「模块可见 + 子 tab 可见」——后端 32 处 `cpa:*` 权限检查收口为 `system:access`，删除 `cpa:read`/`cpa:import` 操作点。

**Architecture:** 三个工作块：(1) 后端 `contract_price/routers.py` 32 处 `require_permission("cpa:read"/"cpa:import")` → `system:access`（sed 全局替换 2 次）；(2) `permissions.yaml` 删 `cpa:read`/`cpa:import` 操作点 + dept_head 引用，`roles_custom.yaml` 清理（工作树已删，待提交）；(3) 前端零改动——`isVisibilityOnlyModule` 自动生效，测试验证。

**Tech Stack:** Python 3.12 / FastAPI / YAML / Next.js 16 / React 19

---

## 文件结构总览

| 文件 | 职责 | 操作 |
|---|---|---|
| `backend/app/extensions/contract_price/routers.py` | 合同价格 API | 32 处 cpa:* → system:access |
| `config/permissions.yaml` | 权限注册表 | 删 cpa:read/cpa:import 操作点 + dept_head 引用 |
| `config/roles_custom.yaml` | 角色 overlay | 删 cpa:read/cpa:import（工作树已删，提交即可） |

---

## Task 1: 后端 —— contract_price/routers.py 收口为 system:access

**Files:**
- Modify: `backend/app/extensions/contract_price/routers.py`（32 处）

- [ ] **Step 1: 确认 32 处 cpa 权限站点**

```bash
grep -c "cpa:read\|cpa:import" backend/app/extensions/contract_price/routers.py
```

预期：32（12 read + 20 import）。

- [ ] **Step 2: sed 全局替换 cpa:read → system:access**

```bash
cd /d/eai/eai-flow-main && sed -i 's/require_permission("cpa:read")/require_permission("system:access")/g' backend/app/extensions/contract_price/routers.py
```

- [ ] **Step 3: sed 全局替换 cpa:import → system:access**

```bash
sed -i 's/require_permission("cpa:import")/require_permission("system:access")/g' backend/app/extensions/contract_price/routers.py
```

- [ ] **Step 4: 验证无残留 cpa 权限**

```bash
grep -c "cpa:read\|cpa:import" backend/app/extensions/contract_price/routers.py
```

预期：0。再确认 system:access 数量 = 32：

```bash
grep -c 'require_permission("system:access")' backend/app/extensions/contract_price/routers.py
```

预期：≥32（若文件原本有其它 system:access 则 >32；至少 32）。

- [ ] **Step 5: 运行 contract_price 测试**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_contract_price_extension.py -q
```

预期：PASS（若该文件无权限断言，直接过；若有 cpa 权限相关断言失败，更新断言为 system:access）。

- [ ] **Step 6: Commit**

```bash
cd /d/eai/eai-flow-main && git add backend/app/extensions/contract_price/routers.py
git commit -m "fix(rbac): converge contract_price backend perms to system:access (drop cpa:read/cpa:import)"
```

---

## Task 2: 数据层 —— permissions.yaml 删 cpa 操作点

**Files:**
- Modify: `config/permissions.yaml:123-132,265-266`

- [ ] **Step 1: 删除 contract_price 模块的两个操作点**

`config/permissions.yaml` contract_price 模块（约 L123-132），将：

```yaml
      - id: "cpa:page:overview"
        display_name: "总览"
        operations:
          - { id: "cpa:read", display_name: "查看合同价格" }
      - id: "cpa:page:contracts"
        display_name: "合同解析"
        operations:
          - { id: "cpa:import", display_name: "导入合同" }
```

改为（删 operations，保留页级定义）：

```yaml
      - id: "cpa:page:overview"
        display_name: "总览"
      - id: "cpa:page:contracts"
        display_name: "合同解析"
```

其余 4 页（items/clusters/tasks/settings）已是 `operations: []`，保持不动。**保留** `data_scopes`（全部合同/本部门合同）——数据权限 tab 不受影响。

- [ ] **Step 2: 删除 dept_head 角色默认的 cpa 引用**

`config/permissions.yaml` dept_head 的 `permissions:` 列表（约 L265-266）删除：

```yaml
      - cpa:read
      - cpa:import
```

- [ ] **Step 3: 验证 yaml + registry**

```bash
cd /d/eai/eai-flow-main && python -c "import yaml; d=yaml.safe_load(open('config/permissions.yaml', encoding='utf-8')); cp=d['modules']['contract_price']; print('yaml OK, cpa pages:', len(cp['pages']), ', all ops empty:', all(not p.get('operations') for p in cp['pages']), ', has data_scopes:', bool(cp.get('data_scopes')))"
```

预期：`yaml OK, cpa pages: 6, all ops empty: True, has data_scopes: True`

```bash
grep -n "cpa:read\|cpa:import" config/permissions.yaml
```

预期：无输出（0 处）。

- [ ] **Step 4: 运行 registry/overlay 测试**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_registry_overlay.py tests/test_role_overlay_store.py -q
```

预期：PASS（3 个已知 pre-existing registry 失败除外）。

- [ ] **Step 5: Commit**

```bash
cd /d/eai/eai-flow-main && git add config/permissions.yaml
git commit -m "fix(rbac): remove cpa:read/cpa:import operation points from permissions.yaml (keep cpa:page:* + data_scopes)"
```

---

## Task 3: 数据层 —— roles_custom.yaml 提交 cpa 清理

**Files:**
- Modify: `config/roles_custom.yaml`（工作树已含删除，待提交）

**说明**：当前工作树 `config/roles_custom.yaml` 已是 `M` 状态，`cpa:read`/`cpa:import` 已被移除（HEAD 的 L99-100 有，工作树无）——这是先前角色管理 UI 写透时同步清理的。本任务只需验证并提交。

- [ ] **Step 1: 确认工作树已删 cpa 操作 id**

```bash
cd /d/eai/eai-flow-main && grep -c "cpa:read\|cpa:import" config/roles_custom.yaml
```

预期：0。

```bash
grep -n "cpa:page" config/roles_custom.yaml
```

预期：6 行 `cpa:page:*`（L46-51）保留。

- [ ] **Step 2: 验证 overlay 解析**

```bash
python -c "import yaml; yaml.safe_load(open('config/roles_custom.yaml', encoding='utf-8')); print('roles_custom OK')"
```

预期：`roles_custom OK`。

- [ ] **Step 3: Commit（含本文件所有工作树改动）**

```bash
git add config/roles_custom.yaml
git commit -m "fix(rbac): drop cpa:read/cpa:import from roles_custom overlay (permissions retired)"
```

**注意**：若 `git status` 显示 roles_custom.yaml 还有其它未提交改动（如 dept_head overlay 扩写），本 commit 会一并带上——与之前 roles_custom 提交的处理一致（用户已接受合并提交）。若不愿带，先 `git add -p` 只挑 cpa 相关行。

---

## Task 4: 全量验证

- [ ] **Step 1: 后端 lint + 测试**

```bash
cd backend && uv run ruff check app/extensions/contract_price/routers.py && PYTHONPATH=. uv run pytest tests/test_contract_price_extension.py -q
```

预期：ruff 无新错误（routers.py 原有 I001 若存在为 pre-existing）；contract_price 测试 PASS。

- [ ] **Step 2: 前端确认零改动仍通过**

```bash
cd frontend && pnpm vitest run tests/unit/extensions/roles/ && pnpm typecheck
```

预期：roles 测试全过；typecheck 仅 pre-existing 错误（含 admin/roles 的 PolicyCondition/PolicyGrant）。

- [ ] **Step 3: 容器重启 + 浏览器回归**

```bash
docker compose -p eai-docker restart gateway frontend
```

浏览器打开 `http://localhost:2026/admin/roles`，验证：
- 合同价格分析卡片 = 「可见 X/6 子页」+ 6 张子页卡片网格（总览/合同解析/分项校验/分组审核/任务中心/配置），每张带可见 Tag。
- 无「全选本组」按钮、无操作网格。
- 点击某子页卡 → tab 显隐切换、计数更新。
- 实际访问 `http://localhost:2026/contract-price` 返回 200（system:access 生效）。
- 系统角色（超级管理员）只读置灰。

- [ ] **Step 4: Commit 收尾**

```bash
git add -A && git commit -m "test: verify contract price permission converge end-to-end"
```

---

## 自审记录

- **Spec 覆盖**：①后端 32 处收口（Task 1）✓；②permissions.yaml 删操作点 + dept_head（Task 2）+ roles_custom（Task 3）✓；③前端零改动自动生效（Task 4 验证）✓；④测试（Task 4）✓。
- **占位符**：无 TBD/TODO；所有步骤给出完整命令。
- **类型一致性**：无新函数/类型；`system:access` 为既有权限点。
- **注意**：Task 1 的 sed 替换需精确匹配 `require_permission("cpa:read")` 完整字符串（含引号），避免误替换；替换后 `grep -c` 验证。Task 3 的 roles_custom 工作树已有删除，提交时留意是否连带其它改动（与之前处理一致）。
