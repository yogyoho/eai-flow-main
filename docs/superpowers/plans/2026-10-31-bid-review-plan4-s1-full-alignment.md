# bid-review Plan 4 — s1 任务工作台前端全量对齐(B1 消费)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端消费 Plan 3 已上线的 B1 字段,把任务工作台(s1)从 7 列占位态拉齐到原型 9 列真数据:任务号=biz_no、项目·标段、致命/主要、创建人、更新时间、审查用时真值、搜索业务号/项目名。

**Architecture:** 纯前端消费批,零后端增量。types.ts 镜像 8 个 B1 字段 → TasksView 九列改造(HEADERS/FATAL_COL/行渲染/CountPairCell/搜索/审查用时) → TaskTitleTag 换 biz_no(四页 h2)。测试走既有 `bid-review-tasks-view.dom.test.tsx` 契约门演进而非新建。

**Tech Stack:** Next.js 16 / React 19 / TanStack Query / rstest(happy-dom `.dom.test.tsx`)。

**Spec:** `docs/superpowers/specs/2026-10-31-bid-review-ux-redesign-design.md` §3 s1(L73-77)+ §5 B1;原型 `docs/designs/2026-10-30-bid-review-ui.html` L531-581(s1 表格区)。

---

## 侦察结论(2026-10-31,全部实证)

- **TasksView.tsx** 现状:HEADERS 7 列 `任务号/模式/状态/可提交判定/致命/待人工/创建时间/操作`,`FATAL_COL=4`;行首格=`t.id.slice(0,8)` mono Link(title={t.id});搜索=L405-410 仅 `t.id.toLowerCase().includes(kw)`,placeholder「搜索任务号…」;统计卡第五格审查用时=L486-491 硬编码「—」(title="B1 done_at 落地后提供");页头 h2=L423 `<TaskTitleTag taskId={selectedId} />`;formatDate=完整 `yyyy-MM-dd HH:mm:ss`(L236-240);CountPairCell(L158-183)=fatal/needHuman 二参,gated 显 —,fatal>0 v-hot。
- **TaskTitleTag 消费方**(4 处):TasksView:423(有 `useSelectedTask().task`)、WorkbenchView:627(有 `useBidTask` 的 task)、BaselineView:258(同)、ReviewQueueView:182(**无 task 对象**,只收 taskId prop——需补 `useBidTask(taskId)`,与 workbench 同 queryKey 天然去重)。
- **原型契约**(保真纪律):表头=`任务号/项目 / 标段/模式/状态/可提交判定/致命/主要(r)/创建人/更新时间/操作(r)`(L549-550);行首格 `td.mono` TBR 号;项目格纯文本 `项目名 · 标段(…)`(L558,`.tbl td` 无省略号样式→保持纯 td 不加 q-ttl);致命格 `td.r.num` + `<span class="v-hot">3</span> / 4`(L565);搜索 placeholder=「搜索任务号 / 项目名…」(L541)。原型统计卡是跨任务计数——Plan 2 用户定案已退役为选中任务体征五格,**不回退**,只把第五格「审查用时」填真值。
- **后端契约**(Plan 3 已线上实证):list_tasks 每项含 biz_no/project_name/lot_name/tender_no/updated_at/done_at/main_unhandled/created_by_name;单任务端点 biz_no 等列直出,唯 main_unhandled/created_by_name=None。存量任务 biz_no 已迁移回填;项目/标段/created_at 之前的 done_at 存量为 null(不伪造)。
- **测试夹具面**:TaskOut fixture 散布 7 个测试文件(selected-task/hooks/baseline/tasks-view/workbench-evidence/workbench-export/nav)。→ **TS 侧 B1 字段一律可选(`?: T | null`)**,避免 6 个无关夹具机械翻新;tasks-view 夹具显式赋值做断言。偏差说明:既有 fatal_unhandled 为必填镜像(微 A 断言面广),B1 字段走可选,后端恒输出,消费端全部 `??` 容忍。

---

### Task 1: types.ts 镜像 B1 八字段

**Files:**
- Modify: `frontend/src/extensions/bid-review/types.ts`(TaskOut 尾部)

- [ ] **Step 1: TaskOut 追加字段**(接口尾部、need_human_count 之后)

```ts
  /** ── B1 扩展(EAI-CUSTOM 2026-10-31,spec §5 B1/裁定12)──────────
   * biz_no=业务号 TBR-YYYYMMDD-NNNN(存量迁移回填);项目/标段/编号=抽取回填
   * (老任务 null,须重跑抽取才有);updated_at=行级更新时刻;done_at=完成时刻
   * (set_status 一次性落点,存量不伪造)。main_unhandled/created_by_name 仅
   * GET /tasks 列表聚合填充,单任务端点 null=未统计(伪零纪律)。TS 侧可选:
   * 后端恒输出,镜像可选只为容忍旧测试夹具。 */
  biz_no?: string | null;
  project_name?: string | null;
  lot_name?: string | null;
  tender_no?: string | null;
  updated_at?: string | null;
  done_at?: string | null;
  main_unhandled?: number | null;
  created_by_name?: string | null;
```

- [ ] **Step 2: 验证** `cd frontend && pnpm typecheck` → PASS(纯类型,无运行时门)

- [ ] **Step 3: Commit** `git add frontend/src/extensions/bid-review/types.ts && git commit -m "feat(bid-review): TaskOut TS 镜像 B1 八字段(Plan4 T1)"`

---

### Task 2: TasksView 九列全量对齐(表头/行/CountPairCell/搜索)

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/TasksView.tsx`(HEADERS/FATAL_COL/CountPairCell/行渲染/搜索)
- Test: `frontend/tests/unit/extensions/bid-review-tasks-view.dom.test.tsx`(六用例适配+两新用例)

- [ ] **Step 1: 先改测试(红)**——夹具加 B1 字段、下标平移、断言九列、新增搜索/降级用例:

  a) TASK 夹具(L49-61)补:
  ```ts
    biz_no: "TBR-20261029-0001",
    project_name: "XX数据中心一期采购项目",
    lot_name: "标段一(机电设备)",
    tender_no: null,
    updated_at: "2026-10-30 16:20:00".replace(" ", "T") + "Z",
    done_at: "2026-10-29T00:11:32Z",
    main_unhandled: 4,
    created_by_name: "张工",
  ```
  (updated_at 直接写字面量 `"2026-10-30T16:20:00Z"`,不要 replace 花活。)

  b) 列取格 helper(现 L93-103):fatalCell 下标 4→5;verdictCell 3 不变;新增:
  ```ts
  /** 项目/标段格(第 2 列)、创建人格(第 7 列)、更新时间格(第 8 列)。 */
  function cellAt(taskId: string, i: number): Element | null {
    return screen.getByTitle(taskId).closest("tr")?.querySelectorAll("td")[i] ?? null;
  }
  ```

  c) 用例 1 追加断言(审查用时/九列/页头 biz_no):
  ```ts
    expect(statValue("审查用时")).toBe("11m 32s");
    expect(cellAt("t1", 0)?.textContent?.trim()).toBe("TBR-20261029-0001");
    expect(cellAt("t1", 1)?.textContent?.trim()).toBe("XX数据中心一期采购项目 · 标段一(机电设备)");
    expect(cellAt("t1", 5)?.textContent?.trim()).toBe("1 / 4");
    expect(cellAt("t1", 5)?.querySelector(".v-hot")).not.toBeNull();
    expect(cellAt("t1", 6)?.textContent?.trim()).toBe("张工");
    expect(cellAt("t1", 7)?.textContent?.trim()).toBe("2026-10-30 16:20:00");
    expect(document.querySelector(".page-head h2")?.textContent).toContain("TBR-20261029-0001");
  ```
  并删原 `expect(statValue("审查用时")).toBe("—")` 与 h2 `toContain("t1")`。

  d) 用例 2(半程)补:`expect(cellAt("t2", 1)?.textContent?.trim()).toBe("—")`(t2 继承 TASK 有项目字段但半程格照显——项目列与结果无关,断言其为真值即可:`toBe("XX数据中心一期采购项目 · 标段一(机电设备)")`;致命格断言不变)。

  e) 新用例「存量降级:biz_no/项目/创建人/更新时间 null → id8/—/—/—」:
  ```ts
  it("存量降级:B1 字段 null → 任务号回退 id8,项目/创建人/更新时间 —,页头 id8", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [{
            ...TASK, biz_no: null, project_name: null, lot_name: null,
            updated_at: null, done_at: null, main_unhandled: null, created_by_name: null,
          }],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t1");
    expect(cellAt("t1", 0)?.textContent?.trim()).toBe("t1".slice(0, 8));
    expect(cellAt("t1", 1)?.textContent?.trim()).toBe("—");
    expect(cellAt("t1", 6)?.textContent?.trim()).toBe("—");
    expect(cellAt("t1", 7)?.textContent?.trim()).toBe("—");
    expect(statValue("审查用时")).toBe("—");
    expect(document.querySelector(".page-head h2")?.textContent).toContain("t1");
  });
  ```

  f) 新用例「搜索:业务号/项目名命中」:
  ```ts
  it("搜索命中业务号与项目名(客户端过滤,foot 计数跟随)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return jsonRes({
          items: [
            TASK,
            { ...TASK, id: "t2", biz_no: "TBR-20261029-0002", project_name: "智慧园区消防改造项目", lot_name: null },
          ],
        });
      }
      return jsonRes({}, 404);
    };
    renderTasks();
    await screen.findByTitle("t2");
    const inp = screen.getByLabelText("搜索任务号 / 项目名");
    // 项目名命中
    fireEvent.change(inp, { target: { value: "智慧园区" } });
    expect(screen.queryByTitle("t1")).toBeNull();
    expect(screen.getByTitle("t2")).toBeTruthy();
    // 业务号命中(清空后换词)
    fireEvent.change(inp, { target: { value: "0001" } });
    expect(screen.getByTitle("t1")).toBeTruthy();
    expect(screen.queryByTitle("t2")).toBeNull();
    expect(document.querySelector(".tbl-foot")?.textContent).toContain("共 1 / 2");
  });
  ```

  g) 用例 4(加载失败)不动;用例 5/6 不动(下标经 helper 间接引用,verdict 3/fatal 5 已平移)。

- [ ] **Step 2: 跑红** `cd frontend && pnpm test -- bid-review-tasks-view` → 新断言 FAIL(列数/文案/值不符)

- [ ] **Step 3: 实现(绿)**——TasksView.tsx 六处:

  a) HEADERS/FATAL_COL(现 ~L50):
  ```ts
  const HEADERS = [
    "任务号", "项目 / 标段", "模式", "状态", "可提交判定",
    "致命/主要", "创建人", "更新时间", "操作",
  ] as const;
  const FATAL_COL = 5; // 致命/主要列下标(原型 s1 L550,B1 main_unhandled 批)
  ```

  b) CountPairCell 二参改 fatal/main(needHuman→main,文案与 v-hot 逻辑不变;docstring 更新为「致命/主要;main=major 且未误报,list_tasks 聚合,单端点 null=未统计」)。

  c) 搜索(L404-410 + placeholder):
  ```ts
  const kw = q.trim().toLowerCase();
  const filtered = tasks.filter(
    (t) =>
      matchStatusFilter(t, statusFilter) &&
      (kw === "" ||
        [t.biz_no, t.id, t.project_name, t.lot_name].some((v) =>
          v?.toLowerCase().includes(kw),
        )),
  );
  ```
  placeholder/aria-label → `"搜索任务号 / 项目名"`(原型 L541)。

  d) 行渲染(L642-678):首格 biz_no 回退 id8;新增项目格;致命格传 main;创建人/更新时间格替换原创建时间格:
  ```tsx
  <td>
    <Link href={taskHref("workbench", t.id)} className="mono" title={t.id}
      onClick={(e) => e.stopPropagation()}>
      {t.biz_no ?? t.id.slice(0, 8)}
    </Link>
  </td>
  <td>
    {t.project_name || t.lot_name
      ? [t.project_name, t.lot_name].filter(Boolean).join(" · ")
      : <span className="unmapped-cell" title="未抽取到项目/标段(老任务须重跑抽取)">—</span>}
  </td>
  {/* 模式/状态/判定格不变 */}
  <td className="r">
    <CountPairCell fatal={gated ? null : t.fatal_unhandled}
      main={gated ? null : t.main_unhandled} gated={gated} />
  </td>
  <td>{t.created_by_name ?? <span className="unmapped-cell">—</span>}</td>
  <td className="num">{t.updated_at ? formatDate(t.updated_at) : "—"}</td>
  <td className="r"><ActionCell task={t} /></td>
  ```

  e) 删除 CountPairCell docstring 里「B1 main_unhandled 落地后换致命/主要」预告注释(已落地)。

  f) 文件头注释(L26 前后「B1 落地后再做 9 列全量对齐」预告)改为已落地纪要。

- [ ] **Step 4: 跑绿** `pnpm test -- bid-review-tasks-view` → 8 用例 PASS
- [ ] **Step 5: Commit** `git add -A frontend/src/extensions/bid-review/components/TasksView.tsx frontend/tests/unit/extensions/bid-review-tasks-view.dom.test.tsx && git commit -m "feat(bid-review): s1 任务表九列全量对齐——biz_no/项目·标段/致命·主要/创建人/更新时间+搜索升级(Plan4 T2)"`

---

### Task 3: 统计卡「审查用时」真值

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/TasksView.tsx`(formatDuration + metric 第五格)

- [ ] **Step 1: 测试已在 Task 2 落**(用例 1 `11m 32s` / 降级用例 `—`),本任务直接实现。

- [ ] **Step 2: 实现**——formatDate 旁加:
  ```ts
  /** 审查用时=done_at−created_at(客户端算,spec §3 s1)。秒/分/时三段;
   * 非法或负值一律 —(不冒充)。 */
  function formatDuration(createdIso: string, doneIso: string): string {
    const ms = new Date(doneIso).getTime() - new Date(createdIso).getTime();
    if (!Number.isFinite(ms) || ms < 0) return "—";
    const s = Math.round(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ${s % 60}s`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }
  ```
  metric 第五格(L486-491)替换:
  ```tsx
  <div className="metric-cell">
    <span className="metric-label">审查用时</span>
    <span className="metric-value num">
      {selectedTask?.done_at && selectedTask.created_at
        ? formatDuration(selectedTask.created_at, selectedTask.done_at)
        : "—"}
    </span>
  </div>
  ```
  (删 title="B1 done_at 落地后提供"。)

- [ ] **Step 3: 跑绿** `pnpm test -- bid-review-tasks-view` → PASS
- [ ] **Step 4: Commit**(与 T2 分开或合并提交均可,分开:`fix(bid-review): 统计卡审查用时真值 done_at−created_at(Plan4 T3)`)

---

### Task 4: TaskTitleTag 换 biz_no(四页)

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/TaskTitleTag.tsx`
- Modify: `TasksView.tsx:423` / `WorkbenchView.tsx:627` / `BaselineView.tsx:258` / `ReviewQueueView.tsx:182`(传参)+ ReviewQueueView 补 `useBidTask`

- [ ] **Step 1: TaskTitleTag**:
  ```tsx
  export function TaskTitleTag({
    taskId,
    bizNo,
  }: {
    taskId: string | null | undefined;
    bizNo?: string | null;
  }) {
    if (!taskId) return null;
    // 原型 L810「审查结果 · TBR-2026-0309」:h2 内业务号纯正文(B1 biz_no);
    // 缺失(列表未加载/降级)回退 id8。tt-id 仅作语义钩子,无弱化样式。
    return <span className="tt-id">{" · "}{bizNo ?? taskId.slice(0, 8)}</span>;
  }
  ```

- [ ] **Step 2: 四消费方**:
  - TasksView: `<TaskTitleTag taskId={selectedId} bizNo={selectedTask?.biz_no} />`
  - WorkbenchView: `<TaskTitleTag taskId={taskId} bizNo={task?.biz_no} />`
  - BaselineView: `<TaskTitleTag taskId={taskId} bizNo={task?.biz_no} />`
  - ReviewQueueView: 顶部补 `const taskQuery = useBidTask(taskId ?? null);`(import 自 hooks,与 workbench 同 queryKey 去重);`<TaskTitleTag taskId={taskId} bizNo={taskQuery.data?.biz_no} />`

- [ ] **Step 3: 全量验证** `pnpm test -- bid-review` + `pnpm typecheck`;review-queue 的 dom 测试若因新增 useBidTask 请求而断言波动,responder 补 `/tasks/` 分支或确认 404 静默无害后放行。
- [ ] **Step 4: Commit** `feat(bid-review): 页头任务号换 TBR 业务号 biz_no(四页,Plan4 T4)`

---

### Task 5: 收尾验证 + 记账

- [ ] **Step 1:** `cd frontend && pnpm test -- bid-review && pnpm typecheck && pnpm lint`(filter 全绿;lint 只看新改文件无新告警)
- [ ] **Step 2:** 线上走查(可选,容器源码 bind-mount 已生效)::2026/bid-review 确认九列/页头业务号/审查用时/搜索。
- [ ] **Step 3:** 记账——`.wolf/memory.md` 一条;`.wolf/anatomy.md` plan4 条目;cerebrum 如有新教训;buglog 仅在修了坏东西时记。
- [ ] **Step 4:** push `git push origin main-dev-fork`(flaky 重试惯例)。

---

## Self-Review(已跑)

- **Spec 覆盖**:§3 s1 五格审查用时=T3;九列=T2;搜索业务号+项目名=T2;页头业务号=T4。§5 B1 消费=全部。无缺口。
- **占位符扫描**:无 TBD;全部步骤带代码。
- **类型一致性**:CountPairCell props 改 `{fatal, main, gated}` 后仅一处调用(L668-673)同步;TaskTitleTag `{taskId, bizNo}` 四消费方逐一列出;TS 可选字段偏差已声明理由。
