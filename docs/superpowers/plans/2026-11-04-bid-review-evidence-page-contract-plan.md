# evidence.page 契约修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行)。步骤用 `- [x]` 勾选。
> spec: `docs/superpowers/specs/2026-11-04-bid-review-evidence-page-contract-design.md`

**Goal:** 页码契约三层修复——提示契约+schema 容忍+docs_text 真分页,模型确认层(text-kind 与 PDF)全复活。

**Architecture:** check_schema 放行现实页码形态;_collect_docs_text 按 [[p.N]] 标记切真分页;build_rule_card 写明页码契约;align_evidence 零改。

**Tech Stack:** Python 3.12/pytest。

---

### Task 1: 文档预提交

- [x] spec + plan 落盘提交(git add -f,显式路径)。

### Task 2: TDD(check_schema 页码容忍)

**Files:**
- Modify: `backend/tests/test_bid_review_llm_verify.py`(+2,紧随围栏测试)
- Modify: `backend/app/extensions/bid_review/engine/verify.py`(check_schema 页码段)

- [x] **Step 2.1: 先写测试** 两测:page=null/"3"/缺省 放行(数字串就地转 int);("第9页"/1.5/True/0) 照拒。
- [x] **Step 2.2: 验红** `PYTHONPATH=. uv run pytest tests/test_bid_review_llm_verify.py -k page -v` 两红。
- [x] **Step 2.3: 实现** 数字串 strip+isdigit→int 就地回写 ev;null 放行;垃圾照拒(报错文案更新)。
- [x] **Step 2.4: 验绿** llm_verify 全绿。

### Task 3: TDD(_collect_docs_text 真分页)

**Files:**
- Modify: `backend/tests/test_bid_review_worker.py`(+3)
- Modify: `backend/app/extensions/bid_review/worker.py`(_collect_docs_text + _PAGE_MARKER_RE)

- [x] **Step 3.1: 先写测试** 三测:无标记→{1: 全文};`[[p.1]]…[[p.5]]`→{1:…,5:…};首标记前散文本并入首标记页。
- [x] **Step 3.2: 验红** `PYTHONPATH=. uv run pytest tests/test_bid_review_worker.py -k collect_docs -v` 三红。
- [x] **Step 3.3: 实现** re.split 捕获组切分;无标记回退 {1: 全文};散文本拼入首标记页;同页重入拼接。
- [x] **Step 3.4: 验绿** worker 全绿。

### Task 4: 提示契约 + PROMPT_VERSION

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/llm_runner.py`

- [x] **Step 4.1** build_rule_card SCHEMA_HINT 行后加页码契约一行;PROMPT_VERSION → `bid-review-rule-card-2026-11-04-page`(注释留痕)。

### Task 5: 全量验证

- [x] **Step 5.1**: llm_verify + worker 全绿;全家 pytest 精确计数;golden 55/55;ruff 触碰文件。
- [x] **Step 5.2**: commit(显式路径)。

### Task 6: R3 活体回采

- [x] **Step 6.1**: gateway 重启 → 登录/CSRF → POST /tasks(multipart 走查文档对,prev_task_id=7c6aec02 全 id)→ 轮询至 done。
- [x] **Step 6.2**: 采证:DB L2-021/L1-013/L1-003 条目(schema 错误应消失/确认段存活/entity join 首证)+ gateway 日志 + summary 口径。

### Task 7: 收尾

- [x] **Step 7.1**: spec 状态落定+plan 勾选 commit(git add -f);push 重试至 `0\t0`(rev-list 取第 2 列)。
- [x] **Step 7.2**: .wolf/memory+buglog(bug-3972)+cerebrum、auto-memory、终报。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;默认零翻红铁律。
