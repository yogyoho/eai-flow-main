# bid-review Plan 6 — /parsing 解析与字段抽取归拢专屏(spec §4.3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 `/bid-review/parsing`(原型 s3),归拢散落 4 处的解析信息:六步 stepper(WorkbenchView 区段一)、解析质量表(BaselineView gate1 卡迁入)、基准字段对照只读区(汇总行+字段族+字段卡,冲突只给「去基准确认」链接不嵌裁定)、页头四元组+「待基准确认」pill;任务总览「查看进度」改指 /parsing。

**Architecture:** 权限新点 `bid:page:parsing`(yaml 模块页 + 2 个 overlay 角色)+ nav.ts TaskPage 扩展 + layout NAV_ITEMS 插入;共享件抽取:`TaskStepper`(WorkbenchView 步进器上移,workbench 暂留显示至 M3 拆分——偏差注记)与 `baselineFields.ts`(BaselineView 模块级 helper 纯搬运);ParsingView 组合页(useBidTask+useBidBaselines)。

**Tech Stack:** Next.js 16 / React 19 / rstest(happy-dom `.dom.test.tsx`)。

**Spec:** `docs/superpowers/specs/2026-10-31-bid-review-ux-redesign-design.md` §4.3;原型 `docs/designs/2026-10-30-bid-review-ui.html` L653-719。

---

## 侦察结论(2026-10-31,全部实证)

- **权限面**:`config/permissions.yaml` L173-184 bid_review 四页(tasks/workbench/baseline/rules);`config/roles_custom.yaml` 恰两处 overlay 授全四页(L115-118、L216-219,`bid:page:tasks` 全仓仅 permissions.yaml 1 处+overlay 2 处)。auth 契约测试(test_auth_me_permissions.py / auth-disabled-contract.spec.ts)不锁扩展 page id,零波及。layout micro-B dom 测试(`tests/unit/app/bid-review-layout.dom.test.tsx` L78)锁「四个已注册页」——须改五页+canPage 用例适配。
- **Stepper 现状**:WorkbenchView L69-103(STAGE_LABELS/STAGE_INDEX/resolveStageIdx)+L671-687(stepper JSX+进度行)。`baselineUnconfirmed = task?.status === "awaiting_confirm"`(L336)。
- **BaselineView 现状**:模块级 helper 齐全——DocMeta(L39)/KIND_LABEL(L51)/roleLabel(L57)/rolePillClass(L64)/STATUS_PILL_CLASS(L70)/FAMILIES(L79)/familyOf(L86)/formatVal(L90)/confPill(L100)/fieldRows(L112)/NO_LABELS(L137);解析质量 gate1 卡(L322-412,数据=engine_meta.docs,OCR 注记=assets>0);基准字段对照卡(L414+,汇总行/裁定卡/族 tabs/f-card 列表/查看原文→DocLocateModal/gate-bar)。
- **API 形状**:`BidBaselinesOut { items: BidBaselineRow[]; labels; adjudications }`(api.ts L165);行有 fields/effective_fields/provenance/fields_conf/conflicts/candidates/materials_hash。解析质量 v1 **无页数置信度**(B3 未落地)——维持文档级注记(诚实降级,spec §4.3 内置回落);原型「识别置信度」列与低置信页明细行不迁。
- **偏差裁定(本计划内定案)**:①字段只读区按 spec「字段族列表+字段卡」(baseline 同款 f-card 渲染)而非原型扁平表——spec 优先于原型;②stepper 用共享件,workbench 在 M3 /results 拆分前保留显示(避免 M2→M3 进度盲区);③任务总览「查看进度」ActionCell 目的地从 workbench 换 parsing(归拢的落点闭环)。
- **路由模板**:`app/bid-review/baseline/page.tsx`(Toaster+Suspense+useSelectedTask)直接复制改组件名。

---

### Task 1: 权限点 + nav/路由骨架

**Files:**
- Modify: `config/permissions.yaml`(L176-178 后插 parsing 页)
- Modify: `config/roles_custom.yaml`(两处 bid 页列表)
- Modify: `frontend/src/extensions/bid-review/nav.ts`(TaskPage/PAGE_PATHS)
- Modify: `frontend/src/app/bid-review/layout.tsx`(NAV_ITEMS + Layers import)
- Create: `frontend/src/app/bid-review/parsing/page.tsx`
- Test: `frontend/tests/unit/app/bid-review-layout.dom.test.tsx`

- [x] **Step 1: 先改测试(红)**——layout dom 测试:「四个已注册页」用例改「五个」并加一行:

```tsx
    expect(
      screen.getByRole("link", { name: "解析与字段抽取" }).getAttribute("href"),
    ).toBe("/bid-review/parsing");
```

  canPage 用例:mock 的 /me pages 列表加 `bid:page:parsing`(与既有四页同列);若用例按「拒绝其一」构造,保持既有拒绝目标不变。

- [x] **Step 2: 跑红** `cd frontend && pnpm test bid-review-layout` → FAIL(link 不存在)

- [x] **Step 3: 实现**——

  permissions.yaml(workbench 条目后):
```yaml
      - id: "bid:page:parsing"
        display_name: "解析与字段抽取"
        operations: []
```

  roles_custom.yaml 两处(`bid:page:tasks` 行后各加一行,保持相邻):
```yaml
    - bid:page:parsing
```

  nav.ts:
```ts
export type TaskPage = "tasks" | "parsing" | "workbench" | "baseline" | "review";
// PAGE_PATHS 加:
  parsing: "/bid-review/parsing",
```

  layout.tsx:icon import 加 `Layers`;NAV_ITEMS 在「任务总览」条目后插:
```tsx
  {
    href: "/bid-review/parsing",
    label: "解析与字段抽取",
    icon: Layers,
    pageId: "bid:page:parsing",
    group: 0,
    taskPage: "parsing",
  },
```
  (无徽标键——解析进度不是计数。)

  `frontend/src/app/bid-review/parsing/page.tsx`(暂以占位组件,T3 换真身):
```tsx
"use client";

import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { useSelectedTask } from "@/extensions/bid-review/hooks";

function ParsingContent() {
  const { taskId } = useSelectedTask();
  return (
    <div className="screen on">
      <div className="page-head">
        <div>
          <h2>解析与字段抽取</h2>
          <div className="ph-sub">{taskId ?? "未指定任务"}</div>
        </div>
      </div>
    </div>
  );
}

export default function BidReviewParsingPage() {
  return (
    <>
      <Toaster />
      <Suspense
        fallback={
          <div className="text-muted-foreground flex items-center justify-center p-6 text-sm">
            加载中...
          </div>
        }
      >
        <ParsingContent />
      </Suspense>
    </>
  );
}
```

- [x] **Step 4: 跑绿** `pnpm test bid-review-layout` → PASS
- [x] **Step 5: Commit** `feat(bid-review): /parsing 权限点+nav/路由骨架(Plan6 T1)`

---

### Task 2: 共享件抽取(TaskStepper + baselineFields)

**Files:**
- Create: `frontend/src/extensions/bid-review/components/TaskStepper.tsx`
- Create: `frontend/src/extensions/bid-review/components/baselineFields.ts`
- Modify: `frontend/src/extensions/bid-review/components/WorkbenchView.tsx`(删本地 stepper 三件,改用共享件)
- Modify: `frontend/src/extensions/bid-review/components/BaselineView.tsx`(helper 改 import)

- [x] **Step 1: TaskStepper.tsx**(从 WorkbenchView L69-103 纯搬运 + stepper JSX/进度行入组件):

```tsx
"use client";

/**
 * 六步步骤条(原型 s3)+ 引擎进度行。canonical home=/parsing(spec §4.3);
 * WorkbenchView 在 M3 /results 拆分前暂留显示(共享件,非重复实现)。
 * EAI-CUSTOM 2026-10-31(Plan6 自 WorkbenchView 上移)。
 */
import { cn } from "@/lib/utils";

import type { TaskOut } from "@/extensions/bid-review/types";

const STAGE_LABELS = [
  "已创建",
  "文档解析",
  "字段抽取",
  "基准确认",
  "审查执行",
  "完成",
] as const;

const STAGE_INDEX: Record<string, number> = {
  created: 0,
  parsing: 1,
  extracting: 2,
  confirm_gate: 3,
  review: 4,
  done: 5,
};

/** 当前步:progress.stage 优先;缺失时按任务状态兜底(测试夹具/早期任务无 stage)。 */
export function resolveStageIdx(stageRaw: string | null, status: string): number {
  if (stageRaw && stageRaw in STAGE_INDEX) return STAGE_INDEX[stageRaw]!;
  switch (status) {
    case "done":
    case "completed":
      return 5;
    case "running":
      return 4;
    case "awaiting_confirm":
      return 3;
    case "extracting":
      return 2;
    case "parsing":
      return 1;
    default:
      return 0;
  }
}

export function TaskStepper({ task }: { task: TaskOut | null }) {
  const progress: Record<string, unknown> = task?.progress ?? {};
  const stageRaw = typeof progress.stage === "string" ? progress.stage : null;
  const pctVal = typeof progress.pct === "number" ? progress.pct : null;
  const progressMsg = typeof progress.msg === "string" ? progress.msg : "";
  const stageIdx = resolveStageIdx(stageRaw, task?.status ?? "");
  const taskDone = task?.status === "done";
  return (
    <>
      <div className="stepper">
        {STAGE_LABELS.map((label, i) => (
          <span
            key={label}
            className={cn(
              "step",
              (taskDone || i < stageIdx) && "done",
              !taskDone && i === stageIdx && "on",
            )}
          >
            <span className="sn">{i + 1}</span>
            {label}
          </span>
        ))}
      </div>
      {progressMsg ? (
        <div className="tbl-foot">
          引擎:{progressMsg}
          {pctVal != null ? <span className="num"> · {pctVal}%</span> : null}
        </div>
      ) : null}
    </>
  );
}
```

- [x] **Step 2: baselineFields.ts**(从 BaselineView L39-137 纯搬运,导出全部):`DocMeta`/`KIND_LABEL`/`roleLabel`/`rolePillClass`/`STATUS_PILL_CLASS`(连带 `PillTone` import 自 contract-price bits)/`FAMILIES`/`familyOf`/`formatVal`/`confPill`/`fieldRows`/`NO_LABELS`——`fieldRows` 的 `BidBaselineRow` type import 自 api。加头注:`/** 基线字段/解析质量共享词汇(Plan6 自 BaselineView 上移;裁定交互仍留 BaselineView)。EAI-CUSTOM 2026-10-31 */`。
- [x] **Step 3: 两消费方改 import**——WorkbenchView 删 STAGE_LABELS/STAGE_INDEX/resolveStageIdx 本地定义,stepper JSX+进度行(L671-687)换 `<TaskStepper task={task} />`;BaselineView 删 L39-137 被搬定义,改 `import { DocMeta, KIND_LABEL, ... } from "./baselineFields"`。
- [x] **Step 4: 回归** `pnpm test bid-review` 全套(纯搬运,零行为变化,既有测试必须全绿)
- [x] **Step 5: Commit** `refactor(bid-review): TaskStepper/baselineFields 共享件抽取(Plan6 T2)`

---

### Task 3: ParsingView 本体 + dom 测试

**Files:**
- Create: `frontend/src/extensions/bid-review/components/ParsingView.tsx`
- Modify: `frontend/src/app/bid-review/parsing/page.tsx`(换真身)
- Test: `frontend/tests/unit/extensions/bid-review-parsing.dom.test.tsx`(新建)

- [x] **Step 1: 先写测试(红)**——结构仿 tasks-view dom 测试(fetcher mock+QueryClientProvider+useSearchParams mock)。夹具:

```tsx
const TASK = { id: "t1", owner_id: "u1", status: "awaiting_confirm", mode: "deep",
  progress: { stage: "confirm_gate", pct: 40, msg: "基线已生成,等待人工确认" },
  error: null, engine_meta: { docs: [
    { doc_id: "t.txt", role: "tender", kind: "text", chars: 1200, status: "parsed", pages: 0, assets: 0 },
    { doc_id: "b.pdf", role: "bid", kind: "pdf", chars: 800, status: "parsed", pages: 12, assets: 3 },
  ] }, prev_task_id: null, created_at: "2026-10-31T00:00:00Z",
  fatal_unhandled: null, need_human_count: 0,
  biz_no: "TBR-20261031-0001", project_name: "XX数据中心一期采购项目", lot_name: "标段一",
  tender_no: null, updated_at: null, done_at: null, main_unhandled: null, created_by_name: null };
const BASELINES = { items: [{ doc_id: "b.pdf", materials_hash: "abcdef1234567890",
  fields: { "tender.max_price": 1000000, "tender.duration": null, "bid.total_price": 1002300 },
  effective_fields: null, conflicts: ["bid.total_price"], candidates: {}, provenance: {}, fields_conf: {} }],
  labels: { "tender.max_price": "招标最高限价" }, adjudications: {} };
```

  responder:`/tasks/t1/baselines`→BASELINES;`/tasks/t1`→TASK;`/tasks`→{items:[TASK]}(useSelectedTask fallback)。

  用例:
  1. **页头四元组+待基准确认 pill**:h2 含「解析与字段抽取」与 biz_no;`.ph-sub` 含 项目名/标段一/深度评审;`ph-actions` 有「待基准确认」。
  2. **stepper**:6 个 `.step`;`confirm_gate` → 第 4 步 on;进度行含「引擎:基线已生成」与「40%」。
  3. **解析质量表**:2 行 doc(文件名/角色 pill 招标·投标/类型 文本·PDF/字符 1,200);b.pdf 行 assets=3;OCR 注记含「1 份文档含扫描页」。
  4. **字段只读区**:汇总行含「共 3」「缺失 1」「冲突 1(未裁 1)」与快照哈希前缀 `abcdef123456`;族 tab「招标基准/投标响应」;字段卡含「招标最高限价」值「1,000,000」与「缺失」pill;缺失风险文案「废标风险」;冲突提示含「去基准确认」链接 href `/bid-review/baseline?task_id=t1`;底部注「不计为通过」。
  5. **failed**:status=failed → errbar 含 task.error 文本。
  6. **taskId=null** → 「未指定任务」降级。

- [x] **Step 2: 跑红** `pnpm test bid-review-parsing` → 模块不存在 FAIL

- [x] **Step 3: 实现 ParsingView.tsx**——组合(全部词汇/渲染块有既定来源):

```tsx
"use client";

/**
 * 解析与字段抽取专屏(原型 s3;spec §4.3 Plan6)。归拢只读展示:
 * 页头四元组(biz_no·项目/标段·模式)+待基准确认 pill、TaskStepper、
 * 解析质量表(engine_meta.docs;B3 前无置信列,OCR 文档级注记=诚实降级)、
 * 基准字段对照只读区(汇总行+族 tabs+字段卡;冲突不嵌裁定,链接去基准确认页)。
 * EAI-CUSTOM 2026-10-31。
 */
```

  数据:`useBidTask(taskId)`+`useBidBaselines(taskId)`;派生照 BaselineView 同名公式(rows/conflictPaths/unresolvedCount/allRows/famStats/missingTotal);state:`fam/search/locate`。
  区块顺序:page-head(ph-icon Layers、h2 解析与字段抽取+TaskTitleTag、ph-sub=`[biz_no, [project_name,lot_name].filter(Boolean).join(" / "), mode==="deep"?"深度评审":"快速审查"].filter(Boolean).join(" · ")`、ph-actions=待基准确认 pill(awaiting_confirm)+状态 pill(taskStatusPillBrx 不引——用 TASK_STATUS_LABELS+pill-gray/warn 简配,或直接复用 BaselineView 的 taskStatusPill+STATUS_PILL_CLASS)) → failed errbar → `<TaskStepper task={task} />` → 解析质量 gate1 卡(**整段移植 BaselineView L322-412 markup**,helper 走 baselineFields) → 基准字段抽取只读卡(卡头「基准字段抽取」hd-sub「引擎从材料中抽取的基准快照——审查即以此为准」+汇总行(同 BaselineView 公式)+冲突注(不嵌 radio):`冲突待裁定 N 处——同一字段在材料中取到多个不一致候选,需在基准确认页人工裁定` + `<Link href={taskHref("baseline", taskId)}>去基准确认 →</Link>` + 族 tabs(照 BaselineView fam-list 块)+f-card 列表(**照 BaselineView L697-772 只读块**,查看原文→setLocate→尾部 `<DocLocateModal …/>`)+tbl-foot「缺失字段按 need_human 处理——不阻断审查,也不计为通过;冲突字段需在基准确认页人工裁定后生效」)。
  降级:baselines rows 空 → 「基线尚未生成」note(照 BaselineView);docs 空 → 表内「该任务无上传材料」。

- [x] **Step 4: 跑绿** `pnpm test bid-review-parsing` → 6 用例 PASS
- [x] **Step 5: Commit** `feat(bid-review): /parsing 解析与字段抽取专屏(Plan6 T3)`

---

### Task 4: 查看进度改指 /parsing + BaselineView 卸下解析质量卡

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/TasksView.tsx`(ActionCell 在途分支)
- Modify: `frontend/src/extensions/bid-review/components/BaselineView.tsx`(删 gate1 解析质量卡)
- Test: `frontend/tests/unit/extensions/bid-review-tasks-view.dom.test.tsx`(href 断言改);baseline dom 测试若有解析质量断言随迁

- [x] **Step 1: 先改测试(红)**——tasks-view 用例 5:`linkOf("t3")` href 改 `"/bid-review/parsing?task_id=t3"`(label「查看进度」不变)。baseline dom 测试 grep「解析质量」——有断言则对应用例删除(该卡已迁 /parsing,由 parsing 测试接管)。
- [x] **Step 2: 跑红** → href 断言 FAIL
- [x] **Step 3: 实现**——TasksView ActionCell 在途分支 `taskHref("workbench", t.id)` → `taskHref("parsing", t.id)`;BaselineView 删解析质量 gate1-card 整段+`docs/ocrDocs` 派生与 DocMeta/KIND_LABEL/roleLabel/rolePillClass 残余 import(不再用者)。
- [x] **Step 4: 跑绿** `pnpm test bid-review` 全套 → PASS
- [x] **Step 5: Commit** `feat(bid-review): 查看进度改指 /parsing+baseline 卸下解析质量卡(Plan6 T4)`

---

### Task 5: 收尾验证 + 记账

- [x] **Step 1:** `pnpm typecheck && pnpm lint`(typecheck 仅 contract-price 既有 9 错容忍)+ `pnpm test bid-review` 全套
- [x] **Step 2:** 权限回归:`cd backend && PYTHONPATH=. uv run pytest tests/test_auth_me_permissions.py -q`(yaml 新点不破坏 /me)
- [x] **Step 3:** 记账——`.wolf/memory.md`/`anatomy.md`(parsing/page.tsx、ParsingView、TaskStepper、baselineFields 四新文件)条目;cerebrum 记偏差裁定(stepper 双页共享至 M3)。
- [x] **Step 4:** push(flaky 重试)。

---

## Self-Review

- **Spec 覆盖**:§4.3 五要素——stepper+进度行+failed errbar=T3;解析质量表=T3(B3 列显式不迁,注记降级);字段对照只读=T3(冲突链接化);页头四元组+pill=T3;完备性卡→/results 属 §4.5/M3 不在本计划。权限/nav= T1;归拢落点(查看进度)=T4。
- **占位符扫描**:移植块以「源行号+差异」表述(纯搬运),新代码全量给出;无 TBD。
- **类型一致性**:TaskPage 联合类型扩 parsing 后 PAGE_PATHS/NAV_ITEMS/taskHref 三处同源;baselineFields 导出面与 BaselineView 既有引用一一对应;ParsingView 复用 `LocateTarget`/`BidBaselineRow`(api.ts)与 `DocLocateModal`。
