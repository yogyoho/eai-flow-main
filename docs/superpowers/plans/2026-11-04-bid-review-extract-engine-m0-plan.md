# B 立项 M0:抽取金标准 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans(控制器 inline 执行)。步骤用 `- [x]` 勾选。
> spec: `docs/superpowers/specs/2026-11-04-bid-review-extract-engine-b-design.md`(§3 M0)

**Goal:** walkthrough 对标注集(26 检查)+评分器+R6 快照离线回归门+live 评分 CLI——抽取层从此有验收尺。

**Architecture:** golden 包内新增 extract.py 评分器+extract_cases/ 夹具;离线快照评分零配额,--live 切片边界单次烧配额;基线 pass_rate 记录在标注集 meta,只升不降。

**Tech Stack:** Python 3.12/pytest。

---

### Task 1: 文档预提交

- [ ] spec + plan 落盘提交(git add -f,显式路径)。

### Task 2: 夹具落盘

- [ ] **Step 2.1**: `golden/extract_cases/walkthrough-annotations.json`——26 项检查(value×12/count×5/contains×6/shape×3;以人工读 walkthrough 原文为准,独立于模型输出)+meta{baseline_pass_rate 占位,snapshot 路径}。
- [ ] **Step 2.2**: `golden/extract_cases/r6-snapshot.json`——R6 基线 fields 冻结(从 bid_review_baselines task 2ab0cc25 落盘)。

### Task 3: 评分器 TDD

**Files:**
- Create: `backend/tests/test_bid_review_golden_extract.py`
- Create: `backend/app/extensions/bid_review/golden/extract.py`

- [ ] **Step 3.1: 先写测试** ①value 标量过/工期 dict 归一过/错值红;②count 过/不符红;③contains dict 子集匹配(name 走 normalize_name 子串容忍)过/缺项红;④shape 过(非空 dict 列表+必填键)/null/纯值列表红;⑤快照门:r6-snapshot 评分 ≥ meta.baseline_pass_rate;⑥已知真值锚点(total_price=980000/appendix 安全生产许可证 present:false)必须 pass。
- [ ] **Step 3.2: 验红** 新文件 pytest 红。
- [ ] **Step 3.3: 实现** 四类检查+归一(value: strip/数值化;dict 递归等值;name: attachments.normalize_name+双向子串)+score_fields/score_snapshots/CLI(--live 调 build_baseline 默认路径)。
- [ ] **Step 3.4: 验绿** 新文件全绿。

### Task 4: 基线定标+全量验证

- [ ] **Step 4.1**: 跑离线评分,把实际 pass_rate 写入 annotations meta.baseline_pass_rate(首标)。
- [ ] **Step 4.2**: 新套件全绿+golden 55/55+全家 pytest 精确计数全绿+ruff 触碰文件。
- [ ] **Step 4.3**: commit(显式路径)。

### Task 5: M0 活体

- [ ] **Step 5.1**: gateway 重启→`--live` 单次活体抽取评分(烧一次配额),报告与基线对照入档。
- [ ] **Step 5.2**: spec 状态落定+plan 勾选 commit(git add -f);push 重试至 `0\t0`。

### Task 6: 收尾

- [ ] **Step 6.1**: .wolf/memory+buglog(若 bug)+cerebrum、auto-memory、终报(M1 队列)。

---

## 执行约束

main-dev-fork 不中途 push;外来 WIP 禁碰;不碰 .wolf/(控制器统一记);中文 Write/Edit;默认零翻红铁律(标注错改标注/引擎错先修引擎);golden 55/55 零翻红。
