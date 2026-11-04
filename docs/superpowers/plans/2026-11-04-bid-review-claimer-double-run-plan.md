# claimer 双跑缺陷修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行)。步骤用 `- [x]` 勾选。
> spec: `docs/superpowers/specs/2026-11-04-bid-review-claimer-double-run-design.md`

**Goal:** claim 只领 created+boot_recovery 三态重置,消灭 routers 直推任务的确定性双跑(重复行根因)。

**Architecture:** _claim_next 删 extracting 分支(created CAS 保持);boot_recovery 重置 parsing/extracting/running→created,孤儿改走完整入口幂等重跑。

**Tech Stack:** Python 3.12/pytest。

---

### Task 1: 文档预提交

- [x] spec + plan 落盘提交(git add -f,显式路径)。

### Task 2: TDD(claimer 契约)

**Files:**
- Modify: `backend/tests/test_bid_review_worker.py`(+2 回归门;2 个 boot_recovery 测试随契约更新)
- Modify: `backend/app/extensions/bid_review/worker.py`(_claim_next + boot_recovery)

- [x] **Step 2.1: 先写测试** `test_claim_next_skips_extracting_task`(extracting 中任务 claim→None,红:现返回 (id,'extracting'))+ `test_boot_recovery_resets_running_parsing_extracting_to_created`(三态重置+幂等,红:现重置到 extracting);改 `test_boot_recovery_resets_running_to_extracting`/`test_boot_recovery_resets_parsing_to_extracting` 断言为 created。
- [x] **Step 2.2: 验红** `-k "claim_next_skips or boot_recovery"` 红。
- [x] **Step 2.3: 实现** _claim_next WHERE 只留 created+删 extracting 分支;boot_recovery 状态表 [running,parsing,extracting]→values(created);docstring 更新(口径变更留痕)。
- [x] **Step 2.4: 验绿** worker 全绿。

### Task 3: 全量验证

- [x] **Step 3.1**: 全家 pytest 精确计数;golden 55/55;ruff 触碰文件。
- [x] **Step 3.2**: commit(显式路径)。

### Task 4: R4 活体回采

- [x] **Step 4.1**: gateway 重启 → 新建走查任务(prev_task_id=72e4bf6c)→ 轮询至 done。
- [x] **Step 4.2**: 断言:issues created_at 单批次聚簇(≤2s 跨度);done 后零迟到写入;同规则单行零重复;gateway 日志无双 pass(prefilter 事件单序列)。

### Task 5: 收尾

- [x] **Step 5.1**: spec 状态落定+plan 勾选 commit(git add -f);push 重试至 `0\t0`(rev-list 取第 2 列)。
- [x] **Step 5.2**: .wolf/memory+buglog(bug-3973)+cerebrum、auto-memory、终报。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;默认零翻红铁律。
