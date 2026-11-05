# M2-M4 活体方差回采实施计划(2026-11-06)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对五段门全开的方差夹具跑 N 次 worker.advance_task 生产管线,测 M1 附件/M2 章节/M3 表格/M4 业绩各段**跨跑方差**(2026-11-05 回采只单跑,M2-M4 方差缺席;walkthrough 夹具无表格无业绩是门信号未触发的根因)。

**Architecture:** 零生产代码改动。新运维脚本 `backend/scripts/bid_review_live_variance.py`(复用 bid_review_live_full 的定点表/段统计;每跑独立 sqlite 内存 engine)+ 方差夹具对 `variance-tender/bid.md`(golden/extract_cases,无标注不评分)。

**Tech Stack:** Python 3.12, sqlalchemy aiosqlite, docker compose -p eai-docker exec gateway。

---

## 五裁决(2026-11-06,取证后定案)

1. **方差口径=稳定性,非正确性**。逐键跨跑相等性(stage 统计扁平化 dotted keys)+ fields 内容 sha1[:12] 指纹抖动面;方差夹具**无标注集不评分**,不进 live_pass_rate(0.8077 只升不降锚不动);`--docs walkthrough` 可选模式带标注复测分值方差(默认 variance)。
2. **夹具开门**:walkthrough 对(650B、无表格、无业绩)开不了 M3 门(`tender.boq_items` 空)/M4 门(`bid.similar_performances` 空)——方差夹具必须含必备章节(M2 门)/工程量清单表 5 行含★必填+1 处故意算术差(M3 门+det 素材)/类似业绩表 3 条含 1 条非同类(M4 门+聚类素材)。门信号仍不触发也是诚实记录(行为=现状)。
3. **配额预算**:每跑 ≈5 次模型调用(首段 sharded 1 + M1/M2/M3/M4 各 1;M5 crosscheck 纯服务端零烧);N=3 默认 ≈15 次,量级与 2026-11-05 单跑回采相同。段失败隔离既有(worker try/except),缺席不落键不炸任务。
4. **纪律**:exit 恒 0 判读在调用方;stdout=完整 JSON 重定向落文件,stderr=进度行(禁 tail 管道,bug-4027 教训);golden 零翻红铁律不涉(零引擎/规则/题库改动——夹具是新增文件,非修改)。
5. **门禁**:纯函数测量核 TDD(`_variance`/`_field_fps`/`_flatten`,测试不触模型);零生产代码改动 → 全家 `pytest tests/ -k bid_review -q` 跑一遍确认 580/0 不动;脚本+夹具+plan 显式路径提交。

## Tasks

### Task 1: 测量核+夹具落地(零配额)
- Create: `backend/scripts/bid_review_live_variance.py`(`--runs N --docs variance|walkthrough`)
- Create: `backend/app/extensions/bid_review/golden/extract_cases/variance-tender.md`、`variance-bid.md`
- Test: `backend/tests/test_bid_review_live_variance.py`(3 测试,已绿)

### Task 2: 容器内活体 N 跑(烧配额,待用户点头)
- Run: `docker compose -p eai-docker exec gateway sh -c "cd /app/backend && PYTHONPATH=. uv run python scripts/bid_review_live_variance.py --runs 3" > "$CLAUDE_JOB_DIR/tmp/variance.json"`
- 判读:flapped_stage_keys / flapped_fields 面;M1 预期复现 n 抖动;M2-M4 首次获得方差实录

### Task 3: 记档+收官
- wolf memory 方差实录;plan 勾选;auto-memory;全家 580/0 复跑;commit+push `0	0`

## 判读口径(先验预期,跑后对表)

- M1 attachments:两跑已现 n=1→0,三跑大概率继续抖——**抖=真方差**;
- M2 sections:n 预期 4-6(目录 4 章);offset_flag 可能仍不触发(md 夹具无真实页码,诚实缺席);
- M3 tables:boq_rows 预期 5(清单 5 行);price_hit 预期全中;required_true 预期 3(★行);算术差行不归 M3(归 det 规则层,方差只看行数/命中率);
- M4:entries 预期 3(业绩 3 条);groups 预期 2(同类聚类 vs 非同类);groups 是纯服务端聚类,**理论零方差**——它抖=上游 entries 抖动的传导;
- 传导链判定:groups 抖而 entries 稳 → 聚类 bug;groups 抖且 entries 抖 → 上游传导(符合预期)。
