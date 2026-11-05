# 对齐审计残留 9 缺口收口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 兑付 2026-11-05 对齐审计(3 只读代理证据核对,记录在 auto-memory `bid-review-alignment-audit-2026-11-05`)的全部 9 项真缺口——P0 行为三件(quick 层裁剪/score_coverage 名实/复核耗时占位)+ P1 接口面三件(MCP 四端点触达/规则 enabled 切换/偏离表入报告)+ P1 解析面三件(docx 表结构化/xlsx 入口/zip+图片直传)。

**Architecture:** 零新依赖(openpyxl 3.1.5 已在 uv.lock 锁定解析,容器实测可导入)。规则语义零改动(golden 零翻红铁律),universe 78 逐位不动;全部改动在 worker 分派前过滤/解析入口扩展/端点增面。MCP 四工具直调 router 函数(零逻辑复制,HTTPException 转 success:false)。

**Tech Stack:** Python 3.12, FastAPI, pytest(夹具镜像 test_bid_review_score_coverage/parse/mcp 既有成语), ruff。

**Spec:** auto-memory `bid-review-alignment-audit-2026-11-05.md` + 设计 `docs/designs/2026-10-29-bid-review-design.md`(quick=只跑 L1 det 承诺;B4 评分覆盖度=交集语义)。

---

## 十裁决(2026-11-05,取证后定案;取证=当日 5 轮 grep/read,现状全部复核)

1. **quick 层裁剪=规则层,抽取段不动**(P0①):`_run_review_stage` 里 `load_rulepack` 后按 `task.mode=="quick"` 过滤 `layer=="L1" and type=="deterministic"`(设计原文承诺)。**M1-M5 抽取段不动**——审计缺口原义是「规则 39 条恒全跑仅跳确认门」,非砍抽取;quick 语义=快审(省时省配额)非降级审查。`rules_total=len(pack.rules)` 尾部既有取法自然反映裁剪后分母,summary.unknown_ratio 诚实。过滤封装 `_prune_rules_for_mode(pack, mode)` 纯函数可测。
2. **score_coverage 覆盖度语义保持,加事实键**(P0②):设计原文 B4 就是「评分覆盖度」(交集=设计意图,非事故);「名不符实」的正解不是发明得分预估(编造语义)而是**补事实键**——响应增 `covered_max_score`(covered 项 max_score 可数值化者合计;无一可转/无 covered → None,伪零纪律)+ docstring 明示「覆盖度审计面,非得分预估」。路径不改(前端 api.ts/hooks.ts 消费在案,零破坏)。
3. **复核耗时=feedback 真数据落位**(P0③):`_render_report_md` 增 feedback 聚合参——无 feedback→「人工复核:未复核」;1 条→「人工复核:1 次动作(首条 {date})」;≥2 条→「人工复核:≥{span}(首末动作跨度,下界)」。「待补充」假占位行删除。新 crud 帮手 `list_task_feedback`(ReviewFeedback JOIN ReviewIssue ON issue_id,WHERE task_id+owner)——feedback 表无 task_id 列,不迁移不加列。
4. **偏离表入报告**(P1⑩,与裁决③同函数):report 渲染时读最新 baseline `fields["deviation.items"]` + `deviation_counts`(同 `/deviations` 端点 756 行投影先例),markdown 节「响应偏离表」(counts 行+逐条);无 items→「响应偏离:无记录」。仅 done 可导的状态门不动。
5. **MCP 四只读工具=直调 router 函数**(P1⑧):`bid_review_diff{task_id,prev}` / `bid_review_deviations{task_id}` / `bid_review_score_coverage{task_id}` / `bid_review_report{task_id}`,handler `await R.diff_task(task_id=..., prev=..., db=session, owner_id=MCP_OWNER)` 直调——零逻辑复制;`except HTTPException → _ok({"success": False, "message": detail})`。report 返回 markdown 文本(同一 TextContent),其余返回 JSON。
6. **规则 enabled 切换=DB override 与 yaml enabled 相与**(P1⑨):`RulePackMeta` 增列 `rule_overrides: JSON`(默认 `{}`;database.py 幂等 ALTER 既有机制,create_all 不 ALTER 已有表);`POST /rulepacks/{name}/rules/{rule_id}/enabled` body `{enabled: bool}` upsert(meta 缺行则按 yaml 现值建行);`_run_review_stage` load 后读 overrides 应用(enabled=False 剔除,与 yaml `enabled` 相与),rules_total 同步。**不写 yaml 文件**(git 跟踪源文件禁运行时改写)。
7. **docx 表结构化=text 兼容+rows 新键**(P1④):`_parse_docx_sync` tbl 块 `{kind:"table", text:..., rows:[[cell,...],...]}`(text 保持管道行形态,模型提示词通路零改动);segment 透传 `rows`;下游 docs 组装/excerpt 只认 text,零消费改动。结构化价值在解析产物可审计+未来结构化消费者(M3 boq 抽取仍走模型,不动)。
8. **xlsx 入口=guarded import**(P1⑤):`detect_kind` 增 `.xlsx→"xlsx"`;`_parse_xlsx_sync`(openpyxl `load_workbook(BytesIO, data_only=True, read_only=True)`,每 sheet→一个 table 块,500 行/sheet 上限防炸);`ModuleNotFoundError`→ValueError(既有 per-file 失败隔离通路,test_ocr_failure_isolated_not_fatal 先例)。**openpyxl 已在锁文件**(xlsx extra+传递解析,容器实测 3.1.5 可导入),零镜像改动;晋升 base deps 挂账不设(升级触发=某环境真缺)。
9. **zip+图片直传=递归复用四解析器**(P1⑥⑦):`detect_kind` 增 `.zip→"zip"` 与图片扩展(`.png/.jpg/.jpeg/.gif/.bmp/.webp→"image"`);zip 分支 zipfile 安全解包(拒绝对路径/`..`;≤20 文件、解压总量≤200MB),子文件按扩展名递归 docx/pdf/text/xlsx/图片解析,seg 增 `source` 键(=zip 内相对路径)保归属;image 分支直接走 `ocr_fn`(docx 内嵌图同通路既有)。save_raw 的 kind 字段照实(detect_kind 单一事实源)。
10. **门禁口径**:规则/题库/universe 零改动 → golden 59 零翻红 + M0 26/26 快照地板不动;全家计数从 553 起增(新增测试全部正贡献);quick 裁剪不改 deep 路径行为(deep 全量 39 条照跑)。annotations 只读不改。

## Tasks

### Task 1: 计划预提交

- [ ] **Step 1:** `git add -f docs/superpowers/plans/2026-11-05-bid-review-alignment-gaps-plan.md && git commit -m "docs(bid-review): 对齐审计9缺口收口计划——十裁决(quick层裁剪/score_coverage事实键/feedback真耗时/MCP直调router/DB override/解析三入口)"`

### Task 2: quick 层裁剪(P0①)

**Files:** worker.py;tests/test_bid_review_worker.py

- [ ] **Step 1: 失败测试**

```python
class TestQuickLayerPrune:
    """对齐审计缺口①(2026-11-05):quick 设计承诺「只跑 L1 det」——35/39 条恒全跑仅跳确认门。"""

    def test_quick_prunes_to_l1_det(self):
        from app.extensions.bid_review.engine.rule_runner import load_rulepack
        from app.extensions.bid_review.worker import _prune_rules_for_mode, RULEPACK_PATH

        pack = load_rulepack(RULEPACK_PATH)
        full = len(pack.rules)
        quick = _prune_rules_for_mode(pack, "quick")
        assert all(r.layer == "L1" and r.type == "deterministic" for r in quick)
        assert 0 < len(quick) < full  # L1 det 是真子集(现包 L1 det 14 条)
        deep = _prune_rules_for_mode(pack, "deep")
        assert len(deep) == full  # deep 逐位不动
        # 纯函数无副作用:pack.rules 未被改
        assert len(pack.rules) == full

    async def test_review_stage_quick_rules_total_reflects_prune(self, db, task):
        # 复用 test_bid_review_worker 既有 db/task 夹具;task.mode="quick"
        task.mode = "quick"
        written, rules_total = await _run_review_stage(db, task, {}, "u1")
        from app.extensions.bid_review.engine.rule_runner import load_rulepack
        from app.extensions.bid_review.worker import RULEPACK_PATH
        pack = load_rulepack(RULEPACK_PATH)
        l1_det = sum(1 for r in pack.rules if r.layer == "L1" and r.type == "deterministic")
        assert rules_total == l1_det  # unknown_ratio 分母诚实
```

- [ ] **Step 2: 红** → **Step 3: 实现**(worker.py `_run_review_stage` 上方加纯函数+接线):

```python
def _prune_rules_for_mode(pack, mode: str):
    """quick 层裁剪(对齐审计缺口①,2026-11-05):设计承诺 quick=只跑 L1 det。
    返回新列表,不改 pack.rules(纯函数);deep/未知 mode 原样全量。
    M1-M5 抽取段不动——裁剪只在规则分派层,rules_total 自然取裁剪后分母。"""
    if mode == "quick":
        return [r for r in pack.rules if r.layer == "L1" and r.type == "deterministic"]
    return pack.rules
```

`_run_review_stage` 内 `pack = load_rulepack(RULEPACK_PATH)` 后接 `pack.rules = _prune_rules_for_mode(pack, task.mode)`(赋回列表,evaluate_fields 零改动)→ **Step 4: 绿** → **Step 5: commit** `git add backend/app/extensions/bid_review/worker.py backend/tests/test_bid_review_worker.py && git commit -m "fix(bid-review): 对齐审计①quick层裁剪——设计承诺只跑L1 det落地(纯函数_prune_rules_for_mode;rules_total取裁剪后分母;deep逐位不动)"`

### Task 3: score_coverage covered_max_score 事实键(P0②)

**Files:** engine/extract.py;tests/test_bid_review_score_coverage.py

- [ ] **Step 1: 失败测试**

```python
def test_covered_max_score_numeric_and_none():
    """裁决②:covered_max_score=covered 项 max_score 可数值化合计;无一可转→None(伪零)。"""
    items = [
        {"name": "价格分", "max_score": 50, "related_paths": ["tender.max_price"]},
        {"name": "技术分", "max_score": "30.5", "related_paths": ["tender.max_price"]},
        {"name": "垃圾分", "max_score": "高", "related_paths": ["tender.max_price"]},
    ]
    rules = [_FakeRule("L1-009", ["tender.max_price"])]
    out = compute_score_coverage(items, rules)
    assert out["covered_max_score"] == 80.5  # 50+30.5;「高」跳过
    out2 = compute_score_coverage([{"name": "x", "max_score": "高", "related_paths": ["p"]}], rules)
    assert out2["covered_max_score"] is None
    out3 = compute_score_coverage([{"name": "x", "related_paths": ["p"]}], [_FakeRule("L2-x", ["other"])])
    assert out3["covered_max_score"] is None  # 无 covered
```

- [ ] **Step 2: 红** → **Step 3: 实现**(extract.py compute_score_coverage 尾部):

```python
    scores: list[float] = []
    for i in items_out:
        if not i["covered_by_rules"] or i["max_score"] is None:
            continue
        try:
            scores.append(float(i["max_score"]))
        except (TypeError, ValueError):
            continue  # 不可数值化跳过,不炸整体
    covered_max_score = sum(scores) if scores else None
    return {
        "total": len(items_out),
        "covered": sum(1 for i in items_out if i["covered_by_rules"]),
        "covered_max_score": covered_max_score,  # 对齐审计②(2026-11-05):覆盖度审计面非得分预估,此为 covered 项可得分上限事实键
        "items": items_out,
    }
```

docstring 尾加一行「覆盖度审计面——交集即设计意图(B4 原文),非得分预估;covered_max_score 是 covered 项 max_score 数值合计的事实键」→ **Step 4: 绿** → **Step 5: commit** `git add backend/app/extensions/bid_review/engine/extract.py backend/tests/test_bid_review_score_coverage.py && git commit -m "fix(bid-review): 对齐审计②score_coverage名实——covered_max_score事实键(伪零纪律;覆盖度语义保持B4原文;路径零改)"`

### Task 4: 报告增强——复核耗时真数据+偏离表(P0③+P1⑩)

**Files:** crud.py;routers.py;tests/test_bid_review_score_coverage.py(report 端点测试所在,镜像其夹具)

- [ ] **Step 1: 失败测试**(夹具照该文件既有 FastAPI+sqlite 成语;需 task done + issues + baseline(payload 含 deviation.items)+ feedback 数条)

```python
async def test_report_review_duration_and_deviations(client_with_db, seeded_done_task):
    """裁决③⑩:「待补充」假占位删除;feedback 真耗时;偏离表节。"""
    # seeded_done_task: task done + 2 issues + baseline fields["deviation.items"]=[{...}] + 2 feedback(不同 created_at)
    r = await client.get(f"/tasks/{seeded_done_task.id}/report")
    md = r.text
    assert "待补充" not in md
    assert "人工复核:" in md  # 聚合行形态(≥2 条 → 首末跨度)
    assert "响应偏离" in md and "| 缺失 |" in md or "响应偏离" in md  # 偏离节存在(计数或无记录)
    # 无 feedback 任务
    r2 = await client.get(f"/tasks/{other_done_task.id}/report")
    assert "人工复核:未复核" in r2.text

def test_render_report_md_feedback_shapes():
    """纯函数面:0/1/≥2 条 feedback 三形态。"""
    from datetime import datetime, timezone as tz
    from app.extensions.bid_review.routers import _feedback_summary
    assert _feedback_summary([]) == "人工复核:未复核"
    one = [type("F", (), {"created_at": datetime(2026, 11, 5, 10, 0, tzinfo=tz.utc)})()]
    assert "1 次动作" in _feedback_summary(one)
    two = one + [type("F", (), {"created_at": datetime(2026, 11, 5, 11, 30, tzinfo=tz.utc)})()]
    s = _feedback_summary(two)
    assert "≥1.5h" in s and "下界" in s
```

- [ ] **Step 2: 红** → **Step 3: 实现**:
  - crud.py 加 `list_task_feedback(db, task_id, owner_id)`:`select(ReviewFeedback).join(ReviewIssue, ReviewFeedback.issue_id == ReviewIssue.id).where(ReviewIssue.task_id == task_id, ReviewFeedback.owner_id == owner_id).order_by(ReviewFeedback.created_at)`。
  - routers.py 加纯函数:

```python
def _feedback_summary(feedback: list) -> str:
    """对齐审计③(2026-11-05):复核耗时真数据(「待补充」假占位删除)。
    0 条=未复核;1 条=1 次动作;≥2 条=首末动作跨度(下界——中间空档不计)。"""
    stamps = [f.created_at for f in feedback if getattr(f, "created_at", None)]
    if not stamps:
        return "人工复核:未复核"
    if len(stamps) == 1:
        return f"人工复核:1 次动作(首条 {stamps[0]:%Y-%m-%d %H:%M} UTC)"
    span_h = (max(stamps) - min(stamps)).total_seconds() / 3600
    return f"人工复核:≥{span_h:.1f}h(首末动作跨度,下界;{len(stamps)} 次动作)"
```

  - `_render_report_md(task, issues, feedback=None, deviations=None)`:占位行 `- 复核耗时:待补充(人工复核耗时统计未接入,占位)` → `- {_feedback_summary(feedback)}`;issues 节后加偏离节(deviations None→「响应偏离:无记录(未检出偏离项或基线未含 deviation.items)」;有→counts 行+逐条 `- {no} {name}: {kind}({where})`)。
  - `export_task_report`:装 `feedback=await crud.list_task_feedback(...)`、`deviations` 读最新 baseline 同 `/deviations` 端点 756 行先例(`crud.list_baselines` 最新行 payload fields)→ **Step 4: 绿** → **Step 5: commit** `git add backend/app/extensions/bid_review/crud.py backend/app/extensions/bid_review/routers.py backend/tests/test_bid_review_score_coverage.py && git commit -m "fix(bid-review): 对齐审计③⑩报告增强——复核耗时feedback真数据(未复核/1次/≥跨度下界)+偏离表节(待补充假占位删除)"`

### Task 5: MCP 四只读工具(P1⑧)

**Files:** mcp.py;tests/test_bid_review_mcp.py

- [ ] **Step 1: 失败测试**(镜像该文件既有 handler 测试成语; monkeypatch `_run_in_db` 或用其既有通路)

```python
@pytest.mark.asyncio
async def test_four_read_tools_reach_router_endpoints(monkeypatch):
    """裁决⑧:diff/deviations/score_coverage/report 四工具直调 router 函数。"""
    from app.extensions.bid_review import mcp
    # 各 handler 传不存在 task_id → HTTPException 404 → success:false + 404 字样
    for name, args in [
        ("_handle_diff", {"task_id": "nope", "prev": "nope2"}),
        ("_handle_deviations", {"task_id": "nope"}),
        ("_handle_score_coverage", {"task_id": "nope"}),
        ("_handle_report", {"task_id": "nope"}),
    ]:
        out = await getattr(mcp, name)(args)
        payload = json.loads(out[0].text)
        assert payload["success"] is False and "404" in payload["message"]
```

- [ ] **Step 2: 红** → **Step 3: 实现**(mcp.py:TOOLS 增四条目+四 handler,同一模式):

```python
async def _call_router(fn, **kwargs) -> list[TextContent]:
    """裁决⑧(对齐审计⑧,2026-11-05):直调 router 函数(零逻辑复制——金标准禁复制先例);
    HTTPException(404/409/422)→ success:false 消息面。"""
    from fastapi import HTTPException

    async def _q(session):
        try:
            return {"success": True, **(await fn(db=session, owner_id=MCP_OWNER, **kwargs))}
        except HTTPException as e:
            return {"success": False, "message": f"{e.status_code}: {e.detail}"}
    return _ok(await _run_in_db_inner(_q))
```

(注:`_run_in_db` 返回 handler 结果的既有通路照用;上例 `_run_in_db_inner` 指既有 `_run_in_db`,实现时按其实际签名落。)四 handler:`diff`→`R.diff_task(task_id, prev, db=..., owner_id=...)` 返回值是 dict → `{"success": True, **dict}`;`deviations`/`score_coverage` 同;`report`→ 返回 `Response` 对象,取 `resp.body.decode("utf-8")` 塞 `{"success": True, "report_md": ...}`(TextContent 直出 markdown)。TOOLS 表增四 Tool 条目(name/description/input_schema,描述注「只读」)。→ **Step 4: 绿** → **Step 5: commit** `git add backend/app/extensions/bid_review/mcp.py backend/tests/test_bid_review_mcp.py && git commit -m "feat(bid-review): 对齐审计⑧MCP四只读工具——diff/deviations/score_coverage/report直调router函数(HTTPException转success:false;零逻辑复制)"`

### Task 6: 规则 enabled 切换端点 + DB override(P1⑨)

**Files:** models.py;database.py(幂等 ALTER);routers.py;worker.py;tests/test_bid_review_registry.py 或 routers 测试文件+test_bid_review_worker.py

- [ ] **Step 1: 失败测试**

```python
async def test_rule_enabled_toggle_and_worker_apply(client_with_db, ...):
    """裁决⑥:DB override 与 yaml enabled 相与;不写 yaml。"""
    r = await client.post("/rulepacks/bid-review-core/rules/L1-009/enabled", json={"enabled": False})
    assert r.status_code == 200
    # meta 落 override
    # (worker 面)
    pack = load_rulepack(RULEPACK_PATH)
    overrides = {"L1-009": False}
    pruned = _apply_rule_overrides(pack.rules, overrides)
    assert all(r.id != "L1-009" for r in pruned)
    assert len(pruned) == len(pack.rules) - 1
    # yaml enabled=False 的规则 override=True 仍不跑(相与)
    # r2 = await client.post(...L?-yaml-disabled.../enabled, json={"enabled": True}) → 规则仍剔除

async def test_toggle_unknown_rule_404(client_with_db):
    r = await client.post("/rulepacks/bid-review-core/rules/XX-999/enabled", json={"enabled": False})
    assert r.status_code == 404
```

- [ ] **Step 2: 红** → **Step 3: 实现**:
  - models.py RulePackMeta 增 `rule_overrides: Mapped[dict] = mapped_column(JSON, default=dict)  # {rule_id: bool} 对齐审计⑨ 2026-11-05`;
  - database.py 幂等 ALTER 块照 933/943 行既有成语补一条(`ALTER TABLE bid_review_rulepacks ADD COLUMN IF NOT EXISTS rule_overrides JSONB`/sqlite 方言分支按既有块形态);
  - routers.py:

```python
@router.post("/rulepacks/{name}/rules/{rule_id}/enabled")
async def set_rule_enabled(name: str, rule_id: str, body: RuleEnabledIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """对齐审计⑨(2026-11-05):per-rule 运行时开关。DB override 与 yaml enabled 相与
    (任一 false 即不跑);不写 yaml(git 跟踪源文件禁运行时改写)。unknown 规则 404。"""
    pack = load_rulepack(RULEPACK_PATH)
    if not any(r.id == rule_id for r in pack.rules):
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")
    meta = await crud.get_or_create_rulepack_meta(db, name=name, version=pack.version)
    overrides = dict(meta.rule_overrides or {})
    overrides[rule_id] = bool(body.enabled)
    meta.rule_overrides = overrides  # 重赋值标 JSON 列 dirty(_handle_start 同法)
    await db.commit()
    return {"success": True, "rule_id": rule_id, "enabled": bool(body.enabled)}
```

  - crud.py 加 `get_or_create_rulepack_meta(db, name, version)`(select→无则 insert,R1 注册表先例形态);
  - worker.py `_run_review_stage`:`overrides = await _load_rule_overrides(db)`(select RulePackMeta where name)后 `pack.rules = _apply_rule_overrides(_prune_rules_for_mode(pack, task.mode), overrides)`;纯函数 `_apply_rule_overrides(rules, overrides)` = `[r for r in rules if overrides.get(r.id, True) and r.enabled]`(相与:override False 剔;yaml enabled False 一直剔——现 load 已剔除 yaml disabled?查 load_rulepack 90 行 `enabled=bool(raw.get("enabled", True))` 只是字段,yaml disabled 规则**会**被现 `_apply_rule_overrides` 的 `r.enabled` 项剔除=语义修正顺带落地)。→ **Step 4: 绿** → **Step 5: commit** `git add backend/app/extensions/bid_review/models.py backend/app/extensions/database.py backend/app/extensions/bid_review/routers.py backend/app/extensions/bid_review/crud.py backend/app/extensions/bid_review/worker.py backend/tests/<两测试文件> && git commit -m "feat(bid-review): 对齐审计⑨规则enabled切换——RulePackMeta.rule_overrides(幂等ALTER)+POST端点+worker相与应用(不写yaml;yaml disabled顺带真剔除)"`

### Task 7: docx 表结构化 rows 新键(P1④)

**Files:** parse.py;tests/test_bid_review_parse.py

- [ ] **Step 1: 失败测试**

```python
@pytest.mark.asyncio
async def test_docx_table_rows_structured(base, ocr_ok):
    """裁决⑦:tbl 块 text 管道行(兼容)+ rows 新键(list[list[str]]);text 通路零改动。"""
    import docx as docx_lib
    d = docx_lib.Document()
    d.add_paragraph("前置段落")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "项目", "数量"
    t.cell(1, 0).text, t.cell(1, 1).text = "设备A", "3"
    buf = io.BytesIO(); d.save(buf)
    entry = {"doc_id": "t.docx", "role": "bid", "kind": "docx", "slug": "t", "size": 1, "chars": 0, "pages": 0, "assets": 0, "status": "raw"}
    parse.save_raw("u1", "t1", "bid", "t.docx", buf.getvalue())
    out = await parse.parse_raw("u1", "t1", entry, ocr_ok)
    tbl = [s for s in out["segments"] if s.get("kind") == "table"]
    assert len(tbl) == 1
    assert tbl[0]["rows"] == [["项目", "数量"], ["设备A", "3"]]
    assert "| 项目 | 数量 |" in tbl[0]["text"]  # text 形态不变(模型提示词通路)
```

- [ ] **Step 2: 红** → **Step 3: 实现**(`_parse_docx_sync` tbl 分支收 `row_cells` 列表并随块带出;`parse_raw` 333 行 table seg 增 `"rows": b.get("rows")`)→ **Step 4: 绿** → **Step 5: commit** `git add backend/app/extensions/bid_review/parse.py backend/tests/test_bid_review_parse.py && git commit -m "feat(bid-review): 对齐审计④docx表结构化——seg.rows新键(text管道行兼容;模型通路零改动;解析产物可审计)"`

### Task 8: xlsx 入口(P1⑤)

**Files:** parse.py;tests/test_bid_review_parse.py

- [ ] **Step 1: 失败测试**

```python
def _make_xlsx() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["项目", "数量"]); ws.append(["设备A", 3])
    ws2 = wb.create_sheet("空表头")
    ws2.append(["x"])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

def test_detect_kind_xlsx_and_image():
    """裁决⑧⑨:detect_kind 单一事实源扩展。"""
    assert parse.detect_kind("报价.xlsx") == "xlsx"
    assert parse.detect_kind("扫描件.PNG") == "image"
    assert parse.detect_kind("打包.zip") == "zip"

@pytest.mark.asyncio
async def test_xlsx_sheets_to_table_blocks(base, ocr_ok):
    """xlsx→每 sheet 一个 table 块;data_only 取值。"""
    data = _make_xlsx()
    parse.save_raw("u1", "t1", "bid", "b.xlsx", data)
    entry = {"doc_id": "b.xlsx", "role": "bid", "kind": "xlsx", "slug": "b", "size": 1, "chars": 0, "pages": 0, "assets": 0, "status": "raw"}
    out = await parse.parse_raw("u1", "t1", entry, ocr_ok)
    tbl = [s for s in out["segments"] if s.get("kind") == "table"]
    assert len(tbl) == 2
    assert tbl[0]["rows"][0] == ["项目", "数量"]
```

- [ ] **Step 2: 红** → **Step 3: 实现**(parse.py:`detect_kind` 增 xlsx/image/zip 三分支(一次落齐 Task 8/9 的 kind 面);`_parse_xlsx_sync(data)`:

```python
def _parse_xlsx_sync(data: bytes) -> list[dict]:
    """xlsx → 每 sheet 一个 table 块(对齐审计⑤,2026-11-05)。
    openpyxl 锁文件已含(xlsx extra+传递解析,容器实测 3.1.5);guarded import——
    缺依赖环境降级为 per-file 失败隔离(不炸任务,test_ocr_failure_isolated 先例)。"""
    try:
        import openpyxl
    except ModuleNotFoundError as e:
        raise ValueError("xlsx 支持需安装 xlsx extra(openpyxl)") from e
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    blocks: list[dict] = []
    for ws in wb.worksheets:
        rows: list[list[str]] = []
        for row in ws.iter_rows(values_only=True):
            rows.append(["" if v is None else str(v) for v in row])
            if len(rows) >= 500:  # ponytail: 500 行/sheet 上限,超大表后续分片
                break
        if not rows:
            continue
        text = "\n".join("| " + " | ".join(c) + " |" for c in rows)
        blocks.append({"kind": "table", "text": text, "rows": rows, "sheet": ws.title})
    wb.close()
    return blocks
```

`parse_raw` 增 xlsx 分支(CPU 段 `_run` 外或内按既有形态)→ **Step 4: 绿** → **Step 5: commit** `git add backend/app/extensions/bid_review/parse.py backend/tests/test_bid_review_parse.py && git commit -m "feat(bid-review): 对齐审计⑤xlsx入口——每sheet一table块(guarded import;500行/sheet上限;detect_kind三分支一次落齐)"`

### Task 9: zip 解包 + 图片直传(P1⑥⑦)

**Files:** parse.py;tests/test_bid_review_parse.py

- [ ] **Step 1: 失败测试**

```python
def _make_zip() -> bytes:
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("docs/a.txt", "zip 内文本")
        z.writestr("报价.xlsx", _make_xlsx())
    return buf.getvalue()

@pytest.mark.asyncio
async def test_zip_recursion_and_source_key(base, ocr_ok):
    """裁决⑨:zip 递归四解析器;seg.source=zip 内相对路径。"""
    parse.save_raw("u1", "t1", "bid", "pack.zip", _make_zip())
    entry = {"doc_id": "pack.zip", "role": "bid", "kind": "zip", "slug": "pack", "size": 1, "chars": 0, "pages": 0, "assets": 0, "status": "raw"}
    out = await parse.parse_raw("u1", "t1", entry, ocr_ok)
    srcs = [s.get("source") for s in out["segments"]]
    assert "docs/a.txt" in srcs and "报价.xlsx" in srcs
    assert any("zip 内文本" in (s.get("text") or "") for s in out["segments"])

@pytest.mark.asyncio
async def test_zip_security_and_caps(base, ocr_ok):
    """绝对路径/.. 拒绝;>20 文件拒绝;zip 炸弹(解压总量>200MB)拒绝。"""
    import zipfile
    for names in (["/etc/passwd"], ["../evil.txt"], [f"f{i}.txt" for i in range(21)]):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n in names:
                z.writestr(n, "x")
        with pytest.raises(ValueError):
            parse._unzip_blocks(buf.getvalue())

@pytest.mark.asyncio
async def test_image_direct_upload_ocr(base, ocr_ok):
    """独立图片直传→ocr_fn(docx 内嵌图同通路)。"""
    parse.save_raw("u1", "t1", "bid", "scan.png", _PNG)
    entry = {"doc_id": "scan.png", "role": "bid", "kind": "image", "slug": "scan", "size": 1, "chars": 0, "pages": 0, "assets": 0, "status": "raw"}
    out = await parse.parse_raw("u1", "t1", entry, ocr_ok)
    assert any(s.get("kind") == "text" and "OCR[scan.png]" in (s.get("text") or "") for s in out["segments"])
```

- [ ] **Step 2: 红** → **Step 3: 实现**(parse.py):

```python
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
_ZIP_MAX_FILES = 20
_ZIP_MAX_UNCOMPRESSED = 200 * 1024 * 1024

def _unzip_blocks(data: bytes) -> list[dict]:
    """zip 安全解包(对齐审计⑥,2026-11-05):拒绝对路径/..;≤20 文件;解压总量≤200MB
    (zip 炸弹防线,以 ZipInfo.file_size 预检不落地解压);子文件按扩展名递归四解析器。"""
    import zipfile
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        if len(infos) > _ZIP_MAX_FILES:
            raise ValueError(f"zip 文件数超限(>{_ZIP_MAX_FILES})")
        total = sum(i.file_size for i in infos)
        if total > _ZIP_MAX_UNCOMPRESSED:
            raise ValueError(f"zip 解压总量超限(>{_ZIP_MAX_UNCOMPRESSED // (1024*1024)}MB)")
        blocks: list[dict] = []
        for info in infos:
            name = info.filename
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"zip 内不安全路径: {name}")
            if name.endswith("/"):
                continue
            sub = z.read(info)
            blocks.extend(_blocks_for_bytes(name, sub))
        return blocks

def _blocks_for_bytes(name: str, data: bytes) -> list[dict]:
    """按文件名分派解析器(zip 递归与 parse_raw 共用单一分派)。"""
    kind = detect_kind(name)
    if kind == "docx":
        return _parse_docx_sync(data)
    if kind == "xlsx":
        return _parse_xlsx_sync(data)
    if kind == "pdf":
        blocks, _assets = _parse_pdf_sync(data)
        return blocks
    return _parse_text_sync(data)
```

  `parse_raw` zip 分支:`_unzip_blocks` 结果逐块落 seg 时带 `"source": 块所属子文件名`(_blocks_for_bytes 需带出 name——实现时把 zip 分支单独展开逐子文件调 `_blocks_for_bytes` 并记名,不让通用块结构背 source 键);image 分支:`seg = {"kind": "text", "text": await ocr_fn(name, data, mime), ...}`(mime 从扩展名推,`_MIME` 既有映射)→ **Step 4: 绿** → **Step 5: commit** `git add backend/app/extensions/bid_review/parse.py backend/tests/test_bid_review_parse.py && git commit -m "feat(bid-review): 对齐审计⑥⑦zip解包+图片直传——安全解包(路径/数量/总量三防线)递归四解析器seg.source归属+独立图OCR(docx内嵌图同通路)"`

### Task 10: 全量验证+收官

- [ ] **Step 1: 全家门禁** `cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q`(后台;期望 553+新增全绿 0 failed);golden 59 零翻红 + M0 26/26 快照(含在全家);universe 78 不动(registry 锁);ruff check --fix + format 改动文件 → 重跑受影响测试
- [ ] **Step 2:** push 重试至 `git rev-list --left-right --count origin/main-dev-fork...main-dev-fork` = `0\t0`
- [ ] **Step 3:** wolf(memory+buglog 若 bug)+ anatomy(新函数/端点注记)+ plan 勾选 docs commit(`git add -f`)
- [ ] **Step 4:** auto-memory `bid-review-alignment-gaps-landed.md` + MEMORY.md 索引;终报+队列下一项+「继续」收尾

## 挂账(显式)

- openpyxl 晋升 base deps(xlsx extra→dependencies):升级触发=某部署环境真缺传递依赖
- zip 内嵌图片 OCR 的 doc_id 归属粒度(seg.source 记名,asset 级溯源挂账)
- score_coverage 得分预估语义(若产品侧真要预估,另立 spec——本计划裁决②显式拒绝编造)
- 报告 html 导出(既有 422 白名单,属 M4+ 范围)
