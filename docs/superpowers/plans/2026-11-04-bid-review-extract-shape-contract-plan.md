# 抽取形状契约 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行)。步骤用 `- [x]` 勾选。
> spec: `docs/superpowers/specs/2026-11-04-bid-review-extract-shape-contract-design.md`

**Goal:** occurrence/count 列表字段出口归一+提示契约,消灭形状不匹配哑 need_human(10+5 条规则召回恢复)。

**Architecture:** normalize_fields 单点出口闸(注册表驱动,三条无损归一)+ FIELD_TYPE_CONTRACTS 扩容(现有渲染机制自动进 prompt);eval 零改。

**Tech Stack:** Python 3.12/pytest。

---

### Task 1: 文档预提交

- [x] spec + plan 落盘提交(git add -f,显式路径)。

### Task 2: TDD(出口归一闸)

**Files:**
- Modify: `backend/tests/test_bid_review_extract.py`(+6)
- Modify: `backend/app/extensions/bid_review/engine/extract.py`(OCCURRENCE_PATHS/LIST_PATHS + normalize_fields 闸 + FIELD_TYPE_CONTRACTS 扩容)

- [x] **Step 2.1: 先写测试** 紧随 test_dict_list_scalar_passthrough:①occurrence 纯值列表包装;②occurrence 标量 listify+包装;③dict 项原样保留;④list 路径标量 listify;⑤垃圾(dict/bool)→None;⑥FIELD_TYPE_CONTRACTS 覆盖 15 路径断言。
- [x] **Step 2.2: 验红** `-k "shape" ` 红。
- [x] **Step 2.3: 实现** 注册表+闸函数+normalize_fields 挂接+契约字典扩容。
- [x] **Step 2.4: 验绿** extract 全绿。

### Task 3: 全量验证

- [x] **Step 3.1**: 全家 pytest 精确计数;golden 55/55;ruff 触碰文件。
- [x] **Step 3.2**: commit(显式路径)。

### Task 4: R5 活体回采

- [x] **Step 4.1**: gateway 重启 → 新建走查任务(prev_task_id=e1fe76f4)→ 轮询至 done。
- [x] **Step 4.2**: 断言:L3-018 不再「求值期字段缺失」(币种一致应干净 pass 或真违例);op:all 家族无形状炸;收割召回恢复证据。

### Task 5: 收尾

- [x] **Step 5.1**: spec 状态落定+plan 勾选 commit(git add -f);push 重试至 `0\t0`(rev-list 取第 2 列)。
- [x] **Step 5.2**: .wolf/memory+buglog(bug-3981)+cerebrum、auto-memory、终报。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;默认零翻红铁律。
