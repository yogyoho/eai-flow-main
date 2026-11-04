# Minor-4 NULL entity_keys 病理修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行,429 配额裁决沿前例)。步骤用 `- [ ]` 勾选。
> spec: `docs/superpowers/specs/2026-11-04-bid-review-minor4-null-entity-keys-design.md`

**Goal:** 裸 ALTER 存量行 entity_keys=NULL 不再炸 issues 端点——读路径 validator 兜底 + bootstrap 幂等自愈。

**Architecture:** schemas.py 读路径 None→[](部署即愈);database.py bootstrap UPDATE 数据归一(下次启动)。

**Tech Stack:** Python 3.12/pydantic v2/pytest。

---

### Task 1: 文档预提交

- [ ] spec + plan 落盘提交(git add -f docs/superpowers,显式路径)。

### Task 2: TDD schema 测试

**Files:**
- Create: `backend/tests/test_bid_review_schemas.py`

- [ ] **Step 2.1: 先写测试** 两测:NULL→[](模拟裸 ALTER 存量 ORM 行)+ 正常列表透传。
- [ ] **Step 2.2: 验红** `PYTHONPATH=. uv run pytest tests/test_bid_review_schemas.py -v` → NULL 测红(ValidationError)。
- [ ] **Step 2.3: 实现** schemas.py IssueOut 加 `@field_validator("entity_keys", mode="before")` None→[](EAI-CUSTOM 注释引 spec)。
- [ ] **Step 2.4: 验绿** 同命令 2 绿。

### Task 3: bootstrap 自愈

**Files:**
- Modify: `backend/app/extensions/database.py`(ALTER 行后紧邻)

- [ ] **Step 3.1**: 幂等 `UPDATE bid_review_issues SET entity_keys='[]'::jsonb WHERE entity_keys IS NULL`(EAI-CUSTOM 注释引 spec,说明 IF NOT EXISTS no-op 补不上 DEFAULT 的病理)。

### Task 4: 全量验证

- [ ] **Step 4.1**: bid_review 全家 pytest 精确计数(预期 396/6 口径);golden CLI 55/55 exit 0;ruff 触碰文件。
- [ ] **Step 4.2**: 活库复测 0 NULL;commit(显式路径:schemas.py/database.py/新测试)。

### Task 5: 收尾

- [ ] **Step 5.1**: spec 状态落定+plan 勾选 commit(git add -f);push 重试至 `0\t0`。
- [ ] **Step 5.2**: .wolf/memory+buglog(bug-3968)+cerebrum、auto-memory(Minor-4 兑付回填 L2-P2 记忆)、终报。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;默认零翻红铁律。
