# bid-review Plan 7 — /results 拆分(spec §4.5,M3)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 审查结果自 WorkbenchView 拆出为 `/bid-review/results` 专屏(裁定8:「审查工作台」退役),页头五元组+常驻按钮对齐原型 s5,新增报告预览 modal;/workbench 变重定向 shim。

**Architecture:** git mv WorkbenchView→ResultsView(保历史)→ 新路由 results/page.tsx;nav/权限/回归门三处换血(workbench→results);workbench 页改 client redirect shim 保旧深链;导出报告改开预览 modal(免责注记+判定摘要+Streamdown 渲染 md+下载 .md)。B2 复核落库/B4 评分覆盖度/B7 版本对比/PDF 导出未落地 → 回落现状口径+挂账注。

**Tech Stack:** Next.js 16 App Router、React 19、rstest+testing-library(dom 测试)、TanStack Query、lucide-react。

**侦察结论(2026-10-31):**
- WorkbenchView 1505 行已含 §4.5 大部分:verdict-band(判定口径文案 L722 已是定稿句)、左列四卡(风险分布/资料完备性/规则执行/复核进度)、右列 issues(seg/批量/分页)、导出 .md、改严重度 modal、骨架、只读门。
- 引用面:nav.ts(type+PAGE_PATHS)、layout.tsx NAV_ITEMS、tasks/[id]/page.tsx 重定向 shim、ReviewQueueView.tsx:196 返回链接、TasksView 查看结果 taskHref("workbench");测试:bid-review-layout.dom / layout-flow.dom / bid-review-nav.test / tasks-view.dom / workbench-evidence.dom / workbench-export.dom。
- 后端权限回归门:backend/tests/test_auth_me_permissions.py + frontend/tests/e2e-real-backend/auth-disabled-contract.spec.ts 钉权限全表,需同步。
- formatDuration 在 TasksView.tsx:253(模块私有)→ 上移 primitives.ts 共享;Streamdown 经 `@/components/ai-elements/streamdown`;verdict-band/.vb-* CSS 已在 bid-review.css:497-508。
- 原型 s5 报告预览 modal:L1327-1347(overlay+modal-hd「审查报告预览」+note-bar 免责+verdict-band 摘要+modal-ft 下载)。

**挂账(本计划不实现,代码内注记):**
- B7 版本对比卡片(页头「对比上一版本」按钮缺 prev diff 端点,不渲染)
- B2 复核进度 review_state(现口径:误报=服务端+本地并集,维持仅会话内——保留现有诚实注)
- B4 评分覆盖度 meter(现「规则命中」口径+表尾注保留)
- 报告 PDF 导出(仅 .md;原型「下载 PDF」不抄)

---

### Task 1: 路由换血——权限+nav+回归门(workbench→results)

**Files:**
- Test: `frontend/tests/unit/extensions/bid-review-nav.test.ts`(taskHref)
- Test: `frontend/tests/unit/app/bid-review-layout.dom.test.tsx`(nav href/label/canPage)
- Test: `frontend/tests/unit/app/bid-review-layout-flow.dom.test.tsx`(href 集+顺序)
- Modify: `frontend/src/extensions/bid-review/nav.ts`
- Modify: `frontend/src/app/bid-review/layout.tsx`
- Modify: `config/permissions.yaml`、`config/roles_custom.yaml`(两处 overlay)
- Modify: `backend/tests/test_auth_me_permissions.py`、`frontend/tests/e2e-real-backend/auth-disabled-contract.spec.ts`
- Modify: `frontend/src/app/bid-review/tasks/[id]/page.tsx`(深链 shim 指向 results)

- [ ] **Step 1: 写失败测试**(三测试文件同步改):nav.test 断言 `taskHref("results", "abc")` → `/bid-review/results?task_id=abc`(workbench 键不存在,类型错即红);layout.dom 断言 nav 含 href `/bid-review/results`+label `审查结果`+`canPage(user,"bid:page:results")` 非 null;layout-flow href 集 `workbench`→`results`(顺序断言 baseline<review 不变)。
- [ ] **Step 2: 跑红** `pnpm test bid-review-nav && pnpm test bid-review-layout`(type error / 断言 fail)。
- [ ] **Step 3: 实现**:nav.ts `TaskPage` 联合 `"workbench"`→`"results"`、PAGE_PATHS `results: "/bid-review/results"`;layout.tsx NAV_ITEMS 该项 href→`/bid-review/results`、label→`审查结果`、pageId→`bid:page:results`、taskPage→`results`(icon 不换,减少 diff);tasks/[id]/page.tsx redirect 目标→`/bid-review/results?task_id=`;permissions.yaml `bid:page:workbench` 条目改 id `bid:page:results`+display_name `审查结果`(EAI-CUSTOM 注注明 Plan7);roles_custom.yaml 两处 overlay `- bid:page:workbench`→`- bid:page:results`;后端 pytest 权限表、auth-disabled-contract 同步改。
- [ ] **Step 4: 跑绿** 前端三测试 + `cd backend && PYTHONPATH=. uv run pytest tests/test_auth_me_permissions.py -q`。
- [ ] **Step 5: 提交** `feat(bid-review): /results 路由换血——权限+nav+回归门(Plan7 T1)`(严格 pathspec)。

### Task 2: ResultsView 抽取(git mv)+页头五元组+发起复核/刷新常驻

**Files:**
- Rename: `frontend/src/extensions/bid-review/components/WorkbenchView.tsx` → `ResultsView.tsx`(git mv)
- Rename: `frontend/tests/unit/extensions/bid-review-workbench-evidence.dom.test.tsx` → `bid-review-results-evidence.dom.test.tsx`;`bid-review-workbench-export.dom.test.tsx` → `bid-review-results-export.dom.test.tsx`
- Create: `frontend/src/app/bid-review/results/page.tsx`
- Modify: `frontend/src/extensions/bid-review/components/primitives.ts`(formatDuration 上移)、`TasksView.tsx`(改 import)
- Modify: `frontend/src/extensions/bid-review/components/TasksView.tsx`(查看结果→taskHref("results"))、`ReviewQueueView.tsx:196`(返回链接→/results)
- Test: 两改名测试文件内 import/页头断言更新+新增五元组用例

- [ ] **Step 1: 写失败测试**:results-evidence 测试新增「页头五元组+常驻按钮」用例——夹具 task 带 `done_at`(created 2026-10-29T00:00Z/done 00:11:32Z→用时 11m 32s);断言 h2 含 `审查结果`、ph-sub 含 `用时`、`screen.getByRole("link",{name:"发起复核"}).getAttribute("href")`=`/bid-review/review?task_id=t1`、存在 `刷新` 按钮。
- [ ] **Step 2: 跑红**(组件/路由尚不存在)。
- [ ] **Step 3: 实现**:
  - `git mv` 组件与两测试文件;`WorkbenchView`→`ResultsView` 全文改名(组件名+文件头注「审查结果专屏(原型 s5;spec §4.5,Plan7 自 WorkbenchView 拆分;裁定8 工作台退役)」),两测试 import 更新。
  - `results/page.tsx`:照 parsing/page.tsx 模式(Toaster+Suspense+useSelectedTask→`<ResultsView taskId={taskId} />`)。
  - primitives.ts 增 `export function formatDuration(createdIso: string | null, doneIso: string | null): string`(实现自 TasksView:253 原样上移,null/半程→"—");TasksView 删本地函数改 import。
  - ResultsView 页头:h2 `审查结果`+TaskTitleTag;ph-sub 追加 `用时 {formatDuration(...)}`;ph-actions 增 `<Link href={taskHref("review", taskId)} className="btn btn-sec btn-sm">发起复核</Link>` 与 `<button className="btn btn-sec btn-sm" onClick={刷新(invalidate task/issues queries)}>刷新</button>`(发起复核仅 task 出结果后显?原型 s5 常驻——常驻,但 status 非 done 时 title 注「审查完成后可复核」并 disabled)。
  - TasksView 查看结果 `taskHref("workbench",...)`→`taskHref("results",...)`;ReviewQueueView 返回链接 href→`/bid-review/results?task_id=`(文案「返回工作台」→「返回结果页」)。
  - 左列「未判定 ≠ 通过」warnbar 挂 `<Link href={taskHref("review", taskId)}>到复核工作台 →</Link>`(spec §4.5);复核进度卡/规则执行卡尾注补挂账半句(B2 落库后刷新不丢/B4 落地后换评分覆盖度 meter)。
  - 右列分页 tbl-foot 补「完整清单见导出报告」半句(spec §4.5)。
- [ ] **Step 4: 跑绿** `pnpm test bid-review`(全量;tasks-view L303 断言同步改 `/bid-review/results?task_id=t1`)。
- [ ] **Step 5: 提交** `feat(bid-review): ResultsView 抽取+页头五元组+发起复核/刷新常驻(Plan7 T2)`。

### Task 3: /workbench 重定向 shim

**Files:**
- Modify: `frontend/src/app/bid-review/workbench/page.tsx`(整页换 client redirect)
- Test: `frontend/tests/unit/app/bid-review-workbench-shim.dom.test.tsx`(新)

- [ ] **Step 1: 写失败测试**:mock next/navigation(useRouter.replace spy+useSearchParams);render 页 → `waitFor(replace 被调)` 断言 `/bid-review/results?task_id=t9`(带 task_id)与 `/bid-review/results`(不带)两例。
- [ ] **Step 2: 跑红**。
- [ ] **Step 3: 实现**:page.tsx 换为——

```tsx
"use client";
/**
 * /workbench 深链兼容重定向(Plan7,裁定8 工作台退役):→ /results?task_id=。
 * EAI-CUSTOM (2026-10-31): 旧书签/徽标链路保活;本路由不再承载内容。
 */
import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function WorkbenchRedirectPage() {
  const router = useRouter();
  const sp = useSearchParams();
  useEffect(() => {
    const tid = sp.get("task_id");
    router.replace(
      tid ? `/bid-review/results?task_id=${encodeURIComponent(tid)}` : "/bid-review/results",
    );
  }, [router, sp]);
  return null;
}
```

- [ ] **Step 4: 跑绿**;`grep -rn '"workbench"' frontend/src` 仅剩 shim+tasks/[id] 注释。
- [ ] **Step 5: 提交** `feat(bid-review): /workbench 重定向 shim(Plan7 T3)`。

### Task 4: 报告预览 modal(导出改开弹层)

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/ResultsView.tsx`
- Test: `frontend/tests/unit/extensions/bid-review-results-export.dom.test.tsx`

- [ ] **Step 1: 写失败测试**(改既有 export 用例):点「导出报告」→ `await screen.findByRole("dialog",{name:"审查报告预览"})`;弹层含免责注记文本 `本报告为辅助提示,最终责任由投标主体承担`+判定摘要(不建议提交)+「下载 .md」按钮;点下载→既有 blob 断言不变(下载逻辑原样,URL.createObjectURL+a.click 保留)。
- [ ] **Step 2: 跑红**(现导出直下,无 modal)。
- [ ] **Step 3: 实现**:导出按钮 onClick 改 `setReportOpen(true)`;modal JSX(照原型 L1327 骨架,dialog role+aria-label「审查报告预览」):modal-hd 标题+✕、modal-bd 内 note-bar 免责+verdict-band 摘要(复用现有 verdict 计算:label/副语/口径句)+md 正文(`const [md,setMd]=useState<string|null>(null)`;open 时 `const blob=await exportReport(taskId); setMd(await blob.text())`,Streamdown 渲染,null 时「报告生成中…」)、modal-ft `关闭`+`下载 .md`(onClick=现 handleExportReport 原样)。免责注+PDF 不做注记(挂账)写入文件头。
- [ ] **Step 4: 跑绿** export 测试+全量 bid-review。
- [ ] **Step 5: 提交** `feat(bid-review): 报告预览 modal——免责+判定摘要+md 渲染+下载(Plan7 T4)`。

### Task 5: 收尾——lint/typecheck/后端回归/记账/push

- [ ] **Step 1**: `pnpm exec prettier --write` 改动文件;`pnpm lint`;`pnpm typecheck`(grep -v contract-price);`pnpm test`(全前端)。
- [ ] **Step 2**: `cd backend && PYTHONPATH=. uv run pytest tests/test_auth_me_permissions.py -q`。
- [ ] **Step 3**: .wolf 记账——memory.md 逐动作行;anatomy.md 改名条目(WorkbenchView→ResultsView、测试两文件、results/page.tsx、workbench/page.tsx 描述);cerebrum 挂账条目(B2/B4/B7/PDF);spec §6 不新增裁定(本计划皆 §4.5 既定内容)。
- [ ] **Step 4**: 计划文档勾选;`git push origin main-dev-fork`(flaky 重试)。
