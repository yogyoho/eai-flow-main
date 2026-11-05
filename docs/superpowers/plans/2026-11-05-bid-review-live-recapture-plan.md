# 活体回采(M5/R2+ 挂账)实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** walkthrough 双文档走 worker 生产管线(首段+M1 实体+M2 章节+M3 表格+M4 业绩+M5 crosscheck)真模型单跑,记抽取分(≥0.7308 只升不降)+ 各段活体统计 + crosscheck 四指标活体值。

**Architecture:** 零生产代码改动。新增一次性运维脚本 `backend/scripts/bid_review_live_full.py`(容器内跑,sqlite 内存库定点五表,不触生产 postgres),经 `worker.advance_task`(各 stage fn 传 None→`_default_*_fn` 生产装配)全链路保真——不复制 worker stage wiring(漂移风险零)。

**Tech Stack:** Python 3.12, sqlalchemy aiosqlite 内存库, docker compose -p eai-docker exec gateway。

**Spec:** M5 plan(2026-11-05-bid-review-crosscheck-m5-plan.md §挂账)「活体回采(--live,抽取分 ≥0.7308 只升不降;记 crosscheck 四指标活体值)」;M1 plan §292 同款(实体段表现记档);M2/M3 plan 同款(章节/表格段表现记档)。

---

## 五裁决(2026-11-05,取证后定案)

1. **全链路路径=worker.advance_task**(保真优先):sqlite `sqlite+aiosqlite://` 内存库定点建 bid_review 五表(ReviewTask/ReviewIssue/BaselinePackage/RulePackMeta/ReviewFeedback,同 worker 测试先例,共享 Base FK DDL 排序坑规避);`crud.create_task` → `advance_task(docs=walkthrough 双文档, extract_fn=worker._default_extract_fn(), wait_confirm=True, 各段 fn=None)` → `crud.list_baselines[0].payload`。stage 接线零复制,生产行为零漂移。
2. **烧配额一次**:单跑取全量(首段 26 检查评分 + M1 attachments 实体数/指纹命中率 + M2 section 行数/页差/is_empty 命中 + M3 boq_rows 行数/价格命中率/required 回填比 + table_cells 单元格数 + M4 entries/groups + M5 crosscheck 四指标),不多次烧。
3. **记档位**:`walkthrough-annotations.json` meta 增 `live_run` 锚(日期/pass_rate/各段统计/crosscheck 四指标);`live_pass_rate` **只升不降**(新值 ≥ 0.7308 才覆写+更新 measured_at,否则保留旧值并记「未破基线」);M5 plan 挂账勾选+值回填;B-design spec §6 不改(历史设计文档,活体值以 annotations meta 为真相源)。
4. **纪律**:脚本 exit 恒 0,判读在调用方——`golden.extract --live` 的「低于快照地板 1.0 即 exit 1」是 M0 既定行为(活体跑常态 exit 1,值记录性对比 live_pass_rate=0.7308);golden 零翻红铁律不涉(零引擎/规则/题库改动);引擎错先修引擎(本 slice 前置已修 Docker 引擎楔死,wslservice 杀+DD 双重启,记忆修法复验成立)。
5. **门禁**:零生产代码改动 → 全家门禁跑一遍确认 553/0 不动即可;annotations json 改动被 test_snapshot_gate_baseline 读(baseline_pass_rate 不动,零翻红);plan/wolf/脚本 git add 显式路径提交推 origin。

## Tasks

### Task 1: 脚本落地
- Create: `backend/scripts/bid_review_live_full.py`(容器内 `cd /app/backend && PYTHONPATH=. uv run python scripts/bid_review_live_full.py`)
- 输出:stdout JSON `{score_summary, stages:{m1,m2,m3,m4}, crosscheck, payload_keys}`

### Task 2: 容器内活体单跑
- Run: `docker compose -p eai-docker exec gateway ...`(后台,烧配额一次)
- 产出:JSON 值记录 + 与 0.7308 对比

### Task 3: 记档+收官
- annotations meta.live_run 落值(只升不降);M5 plan 挂账勾选;wolf memory+buglog(Docker 引擎楔死复现=bug-4027);auto-memory;全家 553/0 复跑;commit+push `0\t0`
