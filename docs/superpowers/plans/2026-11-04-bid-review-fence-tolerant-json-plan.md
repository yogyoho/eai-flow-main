# 围栏容错 JSON 解析 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行)。步骤用 `- [x]` 勾选。
> spec: `docs/superpowers/specs/2026-11-04-bid-review-fence-tolerant-json-design.md`

**Goal:** 生产模型围栏包壳回包不再炸 schema——check_schema 三级降级(直接/剥围栏/首末大括号切片),模型确认层复活。

**Architecture:** verify.py check_schema raw 层单点三级降级;全败才 not_json。

**Tech Stack:** Python 3.12/pytest。

---

### Task 1: 文档预提交

- [x] spec + plan 落盘提交(git add -f,显式路径)。

### Task 2: TDD(check_schema 剥壳)

**Files:**
- Modify: `backend/tests/test_bid_review_llm_verify.py`(+2,紧随 test_check_schema_ok_and_rejects)
- Modify: `backend/app/extensions/bid_review/engine/verify.py`(check_schema)

- [x] **Step 2.1: 先写测试** 两测:围栏包壳(```json … ```)过 schema;prose 包裹(```\n\n好的,以下是…{…}\n```)过 schema。
- [x] **Step 2.2: 验红** `PYTHONPATH=. uv run pytest tests/test_bid_review_llm_verify.py -k fence -v` 两红。
- [x] **Step 2.3: 实现** check_schema 三级降级 + `_JSON_FENCE_RE`;每级失败静默落下一级,全败返回 not_json(带原始 err)。
- [x] **Step 2.4: 验绿** llm_verify 全绿。

### Task 3: 全量验证

- [x] **Step 3.1**: 全家 pytest 精确计数(398 口径);golden 55/55;ruff 触碰文件。
- [x] **Step 3.2**: commit(显式路径)。

### Task 4: retry 走查回填

- [x] **Step 4.1**: gateway 重启(validator+本修复进生产)→ POST /tasks/5318d0d9…/retry → 轮询至 done。
- [x] **Step 4.2**: 采证:gateway 日志 hyb_prefilter→确认段(非 degraded);DB L2-021 确认条目 verdict/entity_keys;echo 遵从率记录。

### Task 5: 收尾

- [x] **Step 5.1**: spec 状态落定+plan 勾选 commit(git add -f);push 重试至 `0\t0`(rev-list 取第 2 列)。
- [x] **Step 5.2**: .wolf/memory+buglog(bug-3971)+cerebrum、auto-memory、终报。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;默认零翻红铁律。
