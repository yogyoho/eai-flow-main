# bid_write 批廿五(P1-δ 前端三栏工作台)L4 投影扩面+编辑率采样源+前端接线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通 bid_write 前后端闭环——后端补 L4 其余卡投影面(warranty knob→L4-001、response_sections→L4-008、tender 快照合并泛化)+manual_edit_ratio 采样源(矩阵确认态占比);前端接线 generate/export-precheck/materials/profile/policy/metrics 七组端点,GenerateView/ExportView/MaterialsView 从导航壳变真接线,WorkbenchView 三栏化。

**Architecture:** 后端零新表零新端点(纯函数扩面:knobs 增 warranty_period、投影增两路径、l4_fields 合并从特例泛化为 tender 快照全量);前端零新依赖(现有 fetcher+TanStack Query+bid-write.css 原语),api.ts 扩面+hooks 扩面+四视图接线。advisory-only 铁律与零行为面不破:默认 knobs(无 warranty 无承诺)→参与卡仍只 L4-003/004→绿跑零变化。

**Tech Stack:** Python 3.12 / FastAPI / pytest;Next.js 16 / React 19 / TanStack Query / rstest。

**基线**:216p/6s/0f(批廿四);前端 `pnpm check` 干净。

**落地态(2026-11-14,全任务已执行)**:T1=e13ed8bfb、T2=77de081d1、T3 骨架=a31cd803a、T4=c78e4c985、T5=7d00515fb、T6=348080d1d、T7=c2cf59a45、T8 钉翻新=b70fb8c6b(全在 main-dev-fork,未推)。勘误:①T7 三栏布局在 T3 骨架已落(.wb grid 900/1120/1320),T7 只接 metrics 数据面(左栏 foot+statusbar),未重排;②T6 profile 接线=JSON textarea parse-validate→PUT(非五键表单),素材实体库=seg 筛+表格+创建行;③T8 生成端两处水印钉翻新为 None——l4_fields 泛化使 L4-008 参与(tender 快照合并喂饱 bid.full_text+bid.response_sections),hyb det 零命中→零模型调用→摘除;blocked 独立性双钉不翻转;export-precheck det-only 恒加水印钉不变。回归 -k bid_write 219p/6s/0f;前端 rstest+eslint+tsc 绿。

**OFF-LIMITS**: `backend/app/extensions/contract_price/service.py`(并发会话);工作区其他脏文件(bid_review/engine/extract.py、golden L1-007/L2-030、其余 frontend 脏文件)属其他会话,严禁 stage。审查端 bid_review engine 零改动(写侧只读消费)。

---

### Task 1: 后端——warranty_period knob+bid.response_sections 投影+l4_fields 泛化合并

**Files:**
- Modify: `backend/app/extensions/bid_write/schemas.py` (GenerateKnobs)
- Modify: `backend/app/extensions/bid_write/generate/__init__.py` (build_ctx)
- Modify: `backend/app/extensions/bid_write/precheck.py` (project_bid_fields + run_export_gate)
- Test: `backend/tests/test_bid_write_l4.py`

- [x] **Step 1: 写失败测试**(追加到 test_bid_write_l4.py)

```python
def test_warranty_knob_and_response_sections_projection():
    """warranty knob→bid.warranty_period;RT 行→bid.response_sections(L4-008 输入);
    无 knob 无 RT→两路径缺席(零行为面)。"""
    from app.extensions.bid_write.generate import build_ctx
    from app.extensions.bid_write.precheck import project_bid_fields

    ctx = build_ctx(
        {"tender.boq_items": [{"id": "1", "name": "设备A", "qty": 1, "unit": "项"}], "tender.min_warranty_period": "24个月"},
        [{"clause_id": "w1", "kind": "aggregate", "source_path": "tender.min_warranty_period", "requirement": "质保≥24个月", "star": True, "strategy": "full", "target_section": "售后服务", "evidence_refs": [], "status": "confirmed"}],
        None,
        general_commitments=[{"text": "整体质保 24 个月", "clause_id": ""}],
        warranty_period="24个月",
    )
    out = project_bid_fields(ctx)
    assert out["bid.warranty_period"] == "24个月"
    assert out["bid.response_sections"] == [{"clause_id": "w1", "text": "我方已按第w1条要求备妥响应材料。", "conclusion": "完全响应"}]
    bare = project_bid_fields({"products": {"bid_letter": {"slots": {}, "text": "x"}, "price_sheet": {}}})
    assert "bid.warranty_period" not in bare
    assert "bid.response_sections" not in bare


@pytest.mark.asyncio
async def test_l4_tender_snapshot_merged_and_new_cards_participate():
    """l4_fields=tender 快照全量合并(泛化,替换 substantive_clauses 特例):
    warranty knob+min_warranty+承诺→L4-001 参与;RT 行+full_text→L4-008 参与;
    L4-005 tender.clauses 仍缺(spec 名非 repo 路径)→input_missing。"""
    from app.extensions.bid_review.engine.eval_core import wrap_model_fn
    from app.extensions.bid_write.generate import build_ctx
    from app.extensions.bid_write.precheck import run_export_gate

    ctx = build_ctx(
        {"tender.boq_items": [{"id": "1", "name": "设备A", "qty": 1, "unit": "项"}], "tender.min_warranty_period": "24个月", "tender.substantive_clauses": ["投标人不得转包"]},
        [{"clause_id": "w1", "kind": "aggregate", "source_path": "tender.min_warranty_period", "requirement": "质保≥24个月", "star": True, "strategy": "full", "target_section": "售后服务", "evidence_refs": [], "status": "confirmed"}],
        None,
        general_commitments=[{"text": "整体质保 24 个月", "clause_id": ""}],
        warranty_period="24个月",
    )
    out = await run_export_gate(ctx, l4_model_fn=wrap_model_fn(_stub_model("full")))
    assert out["l4"]["executed"] is True
    assert {"L4-001", "L4-003", "L4-004", "L4-008"} <= set(out["l4"]["participants"])
    assert "L4-005" in out["l4"]["input_missing"]
```

- [x] **Step 2: 跑测试确认红**——`cd backend && PYTHONPATH=. uv run pytest tests/test_bid_write_l4.py -k "warranty_knob or snapshot_merged" -v` → FAIL(TypeError build_ctx unexpected kwarg)

- [x] **Step 3: schemas.py GenerateKnobs 增键**

```python
    total_pages: int | None = None
    # 批廿五 P1-δ:质保承诺月数(L4-001 输入 bid.warranty_period;原样透传,单位随填)
    warranty_period: str | None = None
```

- [x] **Step 4: build_ctx 增 kwarg+ctx["knobs"]**(generate/__init__.py)

签名 `warranty_period: str = ""` 追加在 `letter_defaults` 之后;docstring 补一句;return 前组装:

```python
    return {
        "tender": t,
        "products": {"bid_letter": bl, "price_sheet": ps, "response_table": rt, "attachment_index": ai},
        "material": mat,
        "pre": pre,
        # 批廿五 P1-δ:人工旋钮直通面(投影消费;键恒在=形态稳定)
        "knobs": {"warranty_period": str(warranty_period or "")},
    }
```

- [x] **Step 5: worker.build_task_ctx 透传**(knobs k 已合并,加一行形参)

```python
        letter_defaults=ld or None,
        warranty_period=str(k.get("warranty_period") or ""),
```

- [x] **Step 6: precheck.project_bid_fields 增两投影**(commitments 块后)

```python
    knob_wp = str(((ctx or {}).get("knobs") or {}).get("warranty_period") or "").strip()
    if knob_wp:
        # 批廿五 P1-δ:L4-001 输入(人工旋钮直通,原样透传不造数)
        out["bid.warranty_period"] = knob_wp
    rt_rows = p.get("response_table") or {}
    sections = [
        {"clause_id": r.get("clause_id"), "text": str(r.get("response_text") or ""), "conclusion": r.get("conclusion")}
        for r in (rt_rows.get("rows") or [])
        if isinstance(r, dict) and str(r.get("response_text") or "").strip()
    ]
    if sections:
        # 批廿五 P1-δ:L4-008 输入(响应表行=产物可推导;空表缺席)
        out["bid.response_sections"] = sections
```

- [x] **Step 7: run_export_gate l4_fields 泛化**(特例→tender 快照全量合并)

```python
    l4 = None
    if l4_model_fn is not None:
        # 批廿五 P1-δ:tender 快照全量合并(泛化 substantive_clauses 特例;L4-001 消费
        # tender.min_warranty_period 等;bid.* 投影同键覆盖优先)
        l4_fields = {**(ctx or {}).get("tender") or {}, **fields}
        bl = ((ctx or {}).get("products") or {}).get("bid_letter") or {}
        l4 = await run_l4_review(l4_fields, str(bl.get("text") or ""), l4_model_fn)
```

- [x] **Step 8: 跑测试绿**——同 Step 2 命令 + `pytest tests/test_bid_write_l4.py -v` 全文件(旧 export_gate 测试:keep 分支无 l4_model_fn 零影响)
- [x] **Step 9: Commit** `feat(bid_write): 批廿五 P1-δ-a——warranty_period knob+response_sections 投影+l4_fields tender 快照泛化合并(L4-001/008 激活面)`

### Task 2: manual_edit_ratio 采样源(矩阵确认态占比)

**Files:**
- Modify: `backend/app/extensions/bid_write/metrics.py`
- Modify: `backend/app/extensions/bid_write/worker.py` (generate_and_record)
- Test: `backend/tests/test_bid_write_policy.py`(既有 None 钉更新)+ `backend/tests/test_bid_write_l4.py`

- [x] **Step 1: 找既有 manual_edit_ratio 钉**——`grep -rn "manual_edit_ratio" backend/tests/` → 逐个更新为 0.0(绿跑零确认=零人工编辑,诚实零非 None)
- [x] **Step 2: metrics.py 签名扩**

```python
def compute_metrics(ctx: dict, export: dict, *, duration_ms: int, manual_confirmed: int | None = None, rows_total: int | None = None) -> dict:
    """…manual_edit_ratio=矩阵行人工确认态占比(卡点面采样源;编辑层真源挂
    ProseMirror 面落地后切换;rows_total=0 或未供给→None 不造空零)。"""
    ...
        "manual_edit_ratio": round(manual_confirmed / rows_total, 4) if manual_confirmed is not None and rows_total else None,  # 批廿五 P1-δ:卡点确认占比采样源
```

(note 字段同步改:「manual=矩阵确认态占比」)
- [x] **Step 3: worker.generate_and_record 计数**

```python
    rows = await crud.list_matrix(db, task.id, owner_id)
    confirmed = sum(1 for r in rows if r.status == "confirmed")
    export["metrics"] = compute_metrics(ctx, export, duration_ms=round((time.perf_counter() - t0) * 1000), manual_confirmed=confirmed, rows_total=len(rows))
```

- [x] **Step 4: 新测试**(test_bid_write_l4.py 追加)

```python
@pytest.mark.asyncio
async def test_worker_metrics_manual_edit_ratio(policy_db, monkeypatch):  # noqa: F811
    """确认 1/共 2 行→ratio=0.5 落 skill_run;零确认绿跑→0.0(诚实零非 None)。"""
    from app.extensions.bid_write import crud, worker

    task = await _seed(policy_db, monkeypatch)
    monkeypatch.setattr(worker, "_l4_model_fn", lambda: _stub_model("full"))
    rows = await crud.list_matrix(policy_db, task.id, "u1")
    await crud.patch_matrix_row(policy_db, task.id, "u1", rows[0].clause_id, status="confirmed")
    export = await worker.generate_and_record(policy_db, task, "u1")
    assert export["metrics"]["manual_edit_ratio"] == 0.5
```

(若 `_seed` 只产 1 行,断言 1.0;以实际夹具行为为准,先跑 `_seed` 数行数)
- [x] **Step 5: 跑 bid_write 全量**——`PYTHONPATH=. uv run pytest tests/ -k bid_write -v` → 全绿(旧 None 钉已更新)
- [x] **Step 6: Commit** `feat(bid_write): 批廿五 P1-δ-b——manual_edit_ratio 采样源落地(矩阵行人工确认态占比;编辑层真源挂 ProseMirror)`

### Task 3: 前端——types+api+hooks 扩面

**Files:**
- Modify: `frontend/src/extensions/bid-write/types.ts`
- Modify: `frontend/src/extensions/bid-write/api.ts`
- Modify: `frontend/src/extensions/bid-write/hooks.ts`
- Test: `frontend/tests/unit/extensions/bid-write/knobs.test.ts`(纯函数 knobs 装配)

- [x] **Step 1: types.ts 增形**(GenerateKnobs/ExportGate/L4Face/Material*/Policy/Metrics;字段=后端 schemas/routers 逐一对照,snake_case 直透)
- [x] **Step 2: api.ts 增函数**——`generateTask(taskId, knobs)` POST `/tasks/{id}/generate` 返 `{verdict, blocked, biz_no, status}`;`exportPrecheck(taskId)` POST `/tasks/{id}/export-precheck`;materials CRUD×4+profile GET/PUT;policy GET/PUT;`getTaskMetrics(taskId)` GET `/tasks/{id}/metrics`
- [x] **Step 3: hooks.ts 增**——`useGenerateTask(taskId)`(mutation,成功 invalidate task+gaps+metrics)、`useExportPrecheck(taskId)`(mutation)、`useMaterials(type?)`/`useCreateMaterial`/`usePatchMaterial`/`useDeleteMaterial`/`useMaterialProfile`/`usePutMaterialProfile`、`usePolicy`/`usePutPolicy`、`useTaskMetrics(taskId)`;query key 挂 `bidWriteKeys` 扩展(materials/policy/metrics)
- [x] **Step 4: helpers.ts 增纯函数 `assembleGenerateKnobs`(可测)**

```ts
export interface GenerateKnobsDraft {
  warrantyMonths: string;
  spareYears: string;
  responseHours: string;
  penaltyCap: string;
  signDate: string;
  priceNote: string;
  unitPrices: Record<string, string>; // boq item id → 单价
}
export function assembleGenerateKnobs(draft: GenerateKnobsDraft): {
  warranty_period?: string;
  general_commitments?: { text: string; clause_id: string }[];
  unit_prices?: Record<string, string>;
  sign_date?: string;
  price_note?: string;
} {
  const knobs: ... = {};
  const wp = draft.warrantyMonths.trim();
  if (wp) knobs.warranty_period = /^\d+$/.test(wp) ? `${wp}个月` : wp;
  const comms = [
    draft.spareYears.trim() && `备件供应年限:${draft.spareYears.trim()}年`,
    draft.responseHours.trim() && `故障响应时限:${draft.responseHours.trim()}小时`,
    draft.penaltyCap.trim() && `违约金上限:${draft.penaltyCap.trim()}%`,
  ].filter(Boolean).map((text) => ({ text, clause_id: "" }));
  if (comms.length) knobs.general_commitments = comms;
  const prices = Object.fromEntries(Object.entries(draft.unitPrices).filter(([, v]) => v.trim() !== ""));
  if (Object.keys(prices).length) knobs.unit_prices = prices;
  if (draft.signDate.trim()) knobs.sign_date = draft.signDate.trim();
  if (draft.priceNote.trim()) knobs.price_note = draft.priceNote.trim();
  return knobs;
}
```
- [x] **Step 5: rstest 纯函数测试**(空 draft→{};数字月→`24个月`;承诺拼装;空单价剔除)
- [x] **Step 6: `cd frontend && python ../scripts/pnpm.py check`** 绿
- [x] **Step 7: Commit** `feat(bid-write): 批廿五 P1-δ-c——api/types/hooks 扩面+knobs 装配纯函数(generate/export/materials/policy/metrics 七组)`

### Task 4: GenerateView 真接线

**Files:**
- Modify: `frontend/src/extensions/bid-write/components/GenerateView.tsx`

- [x] **Step 1: 摘诚实谎言横幅**——`生成执行管线尚未接入` banner 删,换真实状态(未选任务/矩阵未就绪 409 提示)
- [x] **Step 2: 单价表改任务接地**——从 `task.engine_meta.fields["tender.boq_items"]`(数组 {id,name,qty,unit})渲染行,单价输入→`unitPrices` state(key=boq id);无 boq→EmptyState(先完成解析抽取);删本地 code 列
- [x] **Step 3: policy 卡改旋钮卡**——五个输入保留(warrantyMonths/spareYears/responseHours/penaltyCap/bidValidityDays→validity 归 policy 不入 knobs,标「主体策略」走 MaterialsView policy 卡,此处删 bidValidityDays 输入避免双源);`开始生成`→`generateTask(taskId, assembleGenerateKnobs(draft))`,409/422 toast 后端 detail;成功→toast+展示 verdict 面(blocked/reasons/watermark/metrics.l4 摘要 Badge)+invalidate
- [x] **Step 4: gen-list 进度行改真状态**——verdict 返回后四产物 Badge(未开始/已生成 blocked=x);`预览章节树`按钮删(无此端点,谎言)
- [x] **Step 5: 模板/技能勾选卡降级为说明卡**(P0 四技能恒全开=事实,模板选择无端点→删模板 state,卡改静态说明)——诚实:不删功能的假交互,只删无后端对应的假控件
- [x] **Step 6: pnpm check** 绿;**Commit** `feat(bid-write): 批廿五 P1-δ-d——GenerateView 真接线(knobs 表单→POST /generate;单价表任务接地;verdict 面展示)`

### Task 5: ExportView 真接线(L4 面展示)

**Files:**
- Modify: `frontend/src/extensions/bid-write/components/ExportView.tsx`

- [x] **Step 1: `生成导出包`→`exportPrecheck(taskId)`**——mutation loading态;成功渲染 gate 真形:verdict 区(blocked/reasons/watermark 值展示:水印=EXPORT_RISK_WATERMARK 时黄条「商务风险未确认」,null 时绿「L4 审查通过水印已摘除」)
- [x] **Step 2: L4 advisory 面板**(新 card)——executed/participants/input_missing/counts/watermark_removed;issues 列表(rule_id/verdict/reason 截断);advisory-only 徽注「L4 不阻断导出,仅风险提示」
- [x] **Step 3: gate-list 四项改真数据源**——precheck 响应:matrix 项=gaps(既有)、assertions 项=assertion_counts+blocked、rule 项=rule_counts+l1_fatal_fail、L4 项=participants 面;`document` 项保留 unknown 诚实(文件导出服务未接入——交付包生成仍挂后续批,门禁裁决先行)
- [x] **Step 4: metrics 摘要行**(GET /tasks/{id}/metrics)——slot_fill_rate/assertion_pass_rate/manual_edit_ratio/latency_ms 四 MetricCell(未执行=null 显示「未执行」)
- [x] **Step 5: pnpm check** 绿;**Commit** `feat(bid-write): 批廿五 P1-δ-e——ExportView 真接线(export-precheck 门禁+L4 advisory 面板+水印状态+metrics 摘要)`

### Task 6: MaterialsView+policy 真接线

**Files:**
- Modify: `frontend/src/extensions/bid-write/components/MaterialsView.tsx`

- [x] **Step 1: 读现文件后接线**——materials CRUD(useMaterials+mutations,六类枚举下拉=contracts.MATERIAL_ENTITY_TYPES 对应中文标签常量)、verifiable=有佐证 Badge、profile 编辑卡(自由形 JSON 字段:name/legal_rep/contact/phone/address 五常用键+其余透传)、policy 编辑卡(letter_defaults.validity_days+sign_date/tax_rate%/price_adjust_mechanism 开关;PUT 合并语义只发改动键;ghost 键 422 toast)
- [x] **Step 2: pnpm check** 绿;**Commit** `feat(bid-write): 批廿五 P1-δ-f——MaterialsView 真接线(六类素材 CRUD+主体 profile+policy 配置)`

### Task 7: WorkbenchView 三栏化+metrics 摘要

**Files:**
- Modify: `frontend/src/extensions/bid-write/components/WorkbenchView.tsx`(实现时先读全文件)
- Modify: `frontend/src/app/bid-write/bid-write.css`(三栏布局类,如缺)

- [x] **Step 1: 三栏布局**——左栏=任务状态+进度+metrics 四指标摘录(useTaskMetrics);中栏=矩阵卡点快照(现有主体重排);右栏=素材联动(profile 键摘要+六类计数+「去素材库」链接+生成/导出入口);窄屏(<900px)叠单列(css grid template)
- [x] **Step 2: pnpm check** 绿;**Commit** `feat(bid-write): 批廿五 P1-δ-g——WorkbenchView 三栏工作台(状态+metrics/矩阵卡点/素材联动)`

### Task 8: 回归+收口

- [x] **Step 1: 后端全量**——`cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_write -v` → 全绿零翻转;`make lint` 本批文件零错
- [x] **Step 2: 前端**——`python ../scripts/pnpm.py check` + `pnpm.py test`(rstest)绿
- [x] **Step 3: 文档**——spec §7 增批廿五落地态段+剩余行更新;plan 勾全+勘误
- [x] **Step 4: wolf 三件套**——memory.md 逐 commit 行;anatomy.md(hooks 自动,验缺补);cerebrum(新教训);buglog(若有修)
- [x] **Step 5: auto-memory**——`bid-write-p1-beta25-workbench-landed.md`+MEMORY.md 索引
- [x] **Step 6: 不推**——等用户「push」

---

## Self-Review

- **Spec 覆盖**: spec 剩余行=P1-δ(manual_edit_ratio 采样源 ✓T2;L4 其余卡投影面 ✓T1;素材联动 ✓T6/T7;三栏工作台 ✓T7)——全覆盖;ProseMirror 编辑层不在本批(spec 另立)。
- **Placeholder 扫描**: Task 6/7 标「实现时先读文件」=大文件既有视图的修改锚点策略,非占位(具体接线内容已列);其余步骤含全码。
- **类型一致**: warranty_period str 贯穿(schemas/build_ctx/knobs/前端 `24个月`);ExportGateResponse 字段名与 run_export_gate dict 逐一对照;l4 面字段=run_l4_review 返回形。
