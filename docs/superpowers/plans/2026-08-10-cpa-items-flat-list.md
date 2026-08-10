# 分项校验 Tab:去分组,改扁平列表 + 任务筛选 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复「分项校验」tab 只显示最新分组的缺陷——去掉客户端 `groupByRun`,改为扁平分页表格,新增「来源任务」筛选下拉 + 来源任务列 + 常驻整批作废按钮。

**Architecture:** 改动集中在单文件 `ItemsView.tsx`。扁平列表与后端 `order_by created_at desc + offset/limit`(crud.py:384)天然对齐,分页缺陷随之消失。任务筛选复用后端已有的 `run_id` 查询参数(api.ts:154 / crud.py:377)与 `deleteItemsByRun`(crud.py:455),后端零改动。

**Tech Stack:** Next.js 16, React 19, TypeScript, TanStack Query, Shadcn UI(`@/components/ui/*`)。前端运行在 Docker 容器(项目组 `eai-docker`),改完需 `restart frontend`。

**设计文档:** `docs/superpowers/specs/2026-08-10-cpa-items-flat-list-design.md`

---

## 关于测试(重要,先读)

该扩展(`src/extensions/contract-price/`)**当前没有任何单测**,也无 `groupByRun` 的测试可删。本次改动是 JSX 渲染重构,可测的纯逻辑仅有"按日期格式化任务标签"这类琐碎日期串(已由保留的 `formatRunLabel` 覆盖)。按 YAGNI 与项目既有约定,**不为本次重构新建测试框架**。每个任务的验证门 = `pnpm typecheck` + `pnpm lint` + 最终手动 QA。这是设计文档明确约定的测试策略,不要自行新增单测文件。

所有命令在 `frontend/` 目录下执行。手动 QA 登录:`admin@eai-flow.com` / `Admin@2026`,入口 nginx `localhost:2026` → 合同价格分析扩展 → 分项校验 tab。

---

## File Structure

仅改动一个文件:

- **Modify:** `frontend/src/extensions/contract-price/components/ItemsView.tsx`
  - 职责:分项校验 tab 的全部 UI 与本地状态。本次去掉分组、加任务筛选/列/整批作废。
- 无新增文件、无后端改动、无新增依赖。

---

## Task 1: 接通 `run_id` 查询参数与 `runMap`(无可观测行为变化,纯管道)

**Files:**
- Modify: `frontend/src/extensions/contract-price/components/ItemsView.tsx`(state 声明区 ~144-161、`useItems` 调用 ~163-170、`runs` 派生之后 ~183-186)

- [ ] **Step 1: 新增 `runFilter` state**

在 `contractFilter` state 声明(~161 行)之后追加:

```tsx
  const [runFilter, setRunFilter] = useState<string>("all"); // "all" | run_id
```

- [ ] **Step 2: 把 `run_id` 注入 `useItems`**

将 `useItems({ ... })` 调用(~163-170)改为:

```tsx
  const { data, isLoading, isFetching, refetch } = useItems({
    goods_name: applied || undefined,
    source_contract_no: contractFilter === "all" ? undefined : contractFilter,
    run_id: runFilter === "all" ? undefined : runFilter,
    only_outliers: onlyOutliers,
    validation_status: onlyReview ? "needs_review" : undefined,
    skip: page * PAGE_SIZE,
    limit: onlyReview ? 500 : PAGE_SIZE,
  });
```

- [ ] **Step 3: 新增 `runMap` useMemo(供后续任务列使用)**

把 `const groups = useMemo(() => groupByRun(items, runs), [items, runs]);`(~186 行)替换为:

```tsx
  const runMap = useMemo(() => new Map(runs.map((r) => [r.id, r] as const)), [runs]);
```

> 此时 `groupByRun` 函数(116-142)暂时保留但不再被调用;Task 2 会删除它。本步 `runFilter` 恒为 `"all"`,行为无变化。

- [ ] **Step 4: 验证 typecheck + lint**

```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 通过(无类型/lint 错误)。若提示 `groupByRun` 未使用,先忽略——Task 2 会删除它;若 lint 因 unused 而失败,把 Task 2 的删除提前到本步一并做。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/extensions/contract-price/components/ItemsView.tsx
git commit -m "refactor(cpa): 接通分项校验 run_id 筛选参数 + runMap"
```

---

## Task 2: 去分组,扁平表格 + 当前页全选 + 顶部批量删除(核心修复)

这是修复缺陷的关键步骤:把分组表格换成单张扁平表。分页从此与后端排序对齐,不再只见最新一组。

**Files:**
- Modify: `frontend/src/extensions/contract-price/components/ItemsView.tsx`

- [ ] **Step 1: 删除分组相关的 state 与 handler**

删除以下声明/handler(逐处删除,不要替换):

- `const [collapsed, setCollapsed] = useState<Set<string>>(new Set());`(~156)
- `const [confirmGroupDelete, setConfirmGroupDelete] = useState<string | null>(null);`(~159)——此 state 从未被渲染,直接删
- `toggleCollapse` 函数整体(~208-214)
- `handleGroupDelete` 函数整体(~236-239)

`toggleSelectAll` 的签名**改为接收当前页 `items`**(原接收 `groupItems: CpaItem[]`,语义不变,只是调用方变化):

```tsx
  const toggleSelectAll = (pageItems: CpaItem[]) => {
    const ids = pageItems.map((i) => i.id);
    const allSelected = ids.length > 0 && ids.every((id) => selected.has(id));
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (allSelected) next.delete(id); else next.add(id);
      }
      return next;
    });
  };
```

- [ ] **Step 2: 删除模块级 `groupByRun` 函数**

删除 `function groupByRun(...)`整体(~116-142)。

- [ ] **Step 3: 用扁平表格替换分组渲染块**

把整个分组滚动容器块(~338-624):

```tsx
              <div className="max-h-[calc(100vh-340px)] overflow-y-auto border border-border rounded-lg">
              {groups.map((group) => {
                ... 整个 groups.map ...
              })}
              </div>
```

替换为下面的扁平结构。**关键:每行的 `<Fragment key={item.id}>…</Fragment>` 内部(原 `group.items.map` 的 row body:checkbox/货物名称/规格/来源合同/状态/含税单价/操作 + 可展开明细行)整体保留不变**,只是外层从 `groups.map(group => group.items.map(item => …))` 改为直接 `items.map(item => …)`,并把表头与全选 checkbox 提到顶层。

```tsx
              {/* Flat table — scrollable container */}
              <div className="max-h-[calc(100vh-340px)] overflow-y-auto border border-border rounded-lg">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10">
                        <input
                          type="checkbox"
                          checked={items.length > 0 && items.every((it) => selected.has(it.id))}
                          ref={(el) => {
                            if (el)
                              el.indeterminate =
                                !items.every((it) => selected.has(it.id)) &&
                                items.some((it) => selected.has(it.id));
                          }}
                          onChange={() => toggleSelectAll(items)}
                          className="accent-primary cursor-pointer"
                        />
                      </TableHead>
                      <TableHead>货物名称</TableHead>
                      <TableHead className="whitespace-nowrap">规格</TableHead>
                      <TableHead>来源合同</TableHead>
                      <TableHead className="whitespace-nowrap">状态</TableHead>
                      <TableHead className="text-right">含税单价</TableHead>
                      <TableHead className="text-right w-[180px]">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <Fragment key={item.id}>
                        {/* === 保留原有每行渲染(TableRow + 可展开明细 TableRow),内容不变 === */}
                      </Fragment>
                    ))}
                  </TableBody>
                </Table>
              </div>
```

> 执行说明:把原 `group.items.map((item) => (<Fragment key={item.id}> …本行与明细… </Fragment>))` 里的 `<Fragment>…</Fragment>` 完整内容,原样搬进上面 `items.map` 内部即可。明细行的 `colSpan={7}` 本步保持不变(Task 4 加列时再改成 8)。

- [ ] **Step 4: 把"批量删除已选"迁到顶部已选条**

原分组头里的批量删除(针对已选)随分组头一起消失了。在顶部已选条(~314-329)补回。把:

```tsx
            {selected.size > 0 && (
              <div className="ml-auto flex items-center gap-2">
                <span className="text-xs text-muted-foreground">已选 {selected.size} 条</span>
                <Button
                  size="sm"
                  onClick={() => {
                    batchValidateItems.mutate([...selected]);
                    setSelected(new Set());
                  }}
                  disabled={batchValidateItems.isPending}
                >
                  <Check className="h-4 w-4" />
                  批量确认校验
                </Button>
              </div>
            )}
```

替换为(右侧改为常驻 `ml-auto` 容器,为 Task 5 的整批作废按钮预留左侧位置;新增"批量删除已选"带二次确认):

```tsx
            <div className="ml-auto flex items-center gap-2">
              {selected.size > 0 && (
                <>
                  <span className="text-xs text-muted-foreground">已选 {selected.size} 条</span>
                  {confirmBatchDelete ? (
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-muted-foreground">确认删除已选?</span>
                      <Button
                        size="sm"
                        variant="destructive"
                        className="text-xs h-7"
                        onClick={handleBatchDelete}
                        disabled={batchDeleteItems.isPending}
                      >
                        确认
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-xs h-7"
                        onClick={() => setConfirmBatchDelete(false)}
                      >
                        取消
                      </Button>
                    </div>
                  ) : (
                    <>
                      <Button
                        size="sm"
                        onClick={() => {
                          batchValidateItems.mutate([...selected]);
                          setSelected(new Set());
                        }}
                        disabled={batchValidateItems.isPending}
                      >
                        <Check className="h-4 w-4" />
                        批量确认校验
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-xs h-7 text-destructive hover:text-destructive"
                        onClick={() => setConfirmBatchDelete(true)}
                      >
                        <Trash2 className="h-3 w-3" />
                        批量删除
                      </Button>
                    </>
                  )}
                </>
              )}
            </div>
```

> `confirmBatchDelete` state、`handleBatchDelete`、`batchDeleteItems`、`batchValidateItems`、`Trash2`、`Check` 均已在文件顶部存在,无需新增 import。

- [ ] **Step 5: 验证 typecheck + lint**

```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 通过。常见报错:若残留对 `groups`/`collapsed`/`toggleCollapse`/`groupByRun`/`confirmGroupDelete` 的引用——删干净即可。

- [ ] **Step 6: 重启前端 + 手动 QA(核心缺陷验证)**

```bash
docker compose -p eai-docker restart frontend
```
浏览器登录后进入「合同价格分析 → 分项校验」。**重点验证:翻到第 2、3 页,应能看到更早抽取任务的货物**(此前被锁在最新一组)。当前页全选、单行修正/溯源/删除、批量确认、批量删除、异常高亮均应正常。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/extensions/contract-price/components/ItemsView.tsx
git commit -m "fix(cpa): 分项校验去分组改扁平列表,修复只见最新分组的分页缺陷"
```

---

## Task 3: 新增「来源任务」筛选下拉

**Files:**
- Modify: `frontend/src/extensions/contract-price/components/ItemsView.tsx`(筛选条,「来源合同」Select 之后 ~298-313)

- [ ] **Step 1: 在「来源合同」Select 之后追加「来源任务」Select**

在 `contractFilter` 的 `</Select>`(~313)之后、`{selected.size > 0 ...}` 之前(经 Task 2 后是 `<div className="ml-auto ...">` 之前)插入:

```tsx
            <Select
              value={runFilter}
              onValueChange={(v) => {
                setRunFilter(v);
                setPage(0);
                setSelected(new Set());
              }}
            >
              <SelectTrigger className="w-[220px] h-9">
                <SelectValue placeholder="来源任务" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部任务</SelectItem>
                {runs.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {formatRunLabel(r, r.id)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
```

> 复用已有 `runs`、`formatRunLabel`、`Select*` 组件,无需新增 import。

- [ ] **Step 2: 验证 typecheck + lint**

```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 通过。

- [ ] **Step 3: 重启前端 + 手动 QA**

```bash
docker compose -p eai-docker restart frontend
```
验证:「来源任务」下拉列出每个任务(含"全部任务");选中某任务 → 列表只剩该任务货物;切回"全部任务" → 恢复全部。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/extensions/contract-price/components/ItemsView.tsx
git commit -m "feat(cpa): 分项校验新增来源任务筛选下拉"
```

---

## Task 4: 新增「来源任务」列

**Files:**
- Modify: `frontend/src/extensions/contract-price/components/ItemsView.tsx`(表头 + 每行 + 明细行 colSpan)

- [ ] **Step 1: 新增模块级纯函数 `formatRunCompact`**

在 `formatRunLabel` 之上或之下(模块级,~115 附近)新增:

```tsx
/** 来源任务列的紧凑标签:"抽取 MM-DD HH:mm" / "分组 MM-DD HH:mm";无 run 时回退。 */
function formatRunCompact(run: CpaRun | null, runId: string | null): string {
  if (!run) return runId ? `任务 ${runId.slice(0, 8)}…` : "未关联";
  const d = new Date(run.started_at);
  const phase = run.scope ? (run.scope as Record<string, unknown>).phase : null;
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${phase === "parse" ? "抽取" : "分组"} ${mm}-${dd} ${hh}:${mi}`;
}
```

- [ ] **Step 2: 表头加列**

在扁平表头「来源合同」`<TableHead>` 之后(Task 2 产出)插入:

```tsx
                      <TableHead className="whitespace-nowrap">来源任务</TableHead>
```

- [ ] **Step 3: 每行加单元格**

在每行「来源合同」单元格(`<TableCell>{item.source_contract_no ?? "—"}</TableCell>`)之后插入。该单元格需根据 `item.run_id` 查 `runMap`:

```tsx
                              <TableCell className="text-muted-nowrap text-muted-foreground whitespace-nowrap">
                                {(() => {
                                  const r = item.run_id ? runMap.get(item.run_id) ?? null : null;
                                  return (
                                    <span title={formatRunLabel(r, item.run_id)}>
                                      {formatRunCompact(r, item.run_id)}
                                    </span>
                                  );
                                })()}
                              </TableCell>
```

> 用 `title` 放完整标签做 tooltip,单元格里显示紧凑版。

- [ ] **Step 4: 明细行 colSpan 从 7 改为 8**

把可展开明细行(Task 2 保留的 `<TableRow className="bg-muted/30 ...">` 内)的 `<TableCell colSpan={7} ...>` 改为:

```tsx
                                <TableCell colSpan={8} className="py-3">
```

- [ ] **Step 5: 验证 typecheck + lint**

```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 通过。

- [ ] **Step 6: 重启前端 + 手动 QA**

```bash
docker compose -p eai-docker restart frontend
```
验证:表格出现「来源任务」列,每行显示紧凑标签(如"抽取 08-10 14:30"),鼠标悬停显示完整任务名;`run_id` 为空的历史数据显示"未关联";展开明细行跨列正常(无错位)。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/extensions/contract-price/components/ItemsView.tsx
git commit -m "feat(cpa): 分项校验表格新增来源任务列"
```

---

## Task 5: 常驻「整批作废」按钮(按任务删除,带任务选择器)

常驻可见,删除目标永远明确:已选任务筛选时直删该任务;在"全部任务"时弹任务选择器,选一个再删。

**Files:**
- Modify: `frontend/src/extensions/contract-price/components/ItemsView.tsx`(state、handler、右侧 ml-auto 容器)

- [ ] **Step 1: 新增整批作废 state**

在 `confirmBatchDelete` state(~158)附近追加:

```tsx
  const [runDeleteOpen, setRunDeleteOpen] = useState(false); // 整批作废确认弹层
  const [runDeleteTarget, setRunDeleteTarget] = useState<string>("all"); // 选中的 run_id,"all"=未选
```

- [ ] **Step 2: 新增 handler `handleRunDelete`**

在 `handleBatchDelete` 之后追加:

```tsx
  const handleRunDelete = async () => {
    if (runDeleteTarget === "all") return; // 未选任务,按钮本应禁用
    await deleteItemsByRun.mutateAsync(runDeleteTarget);
    setRunDeleteOpen(false);
    setRunDeleteTarget("all");
    setRunFilter("all");
    setPage(0);
    setSelected(new Set());
  };

  const openRunDelete = () => {
    // 已选任务筛选 → 直接锁定该任务;否则进入选择器(默认未选)
    setRunDeleteTarget(runFilter !== "all" ? runFilter : "all");
    setRunDeleteOpen(true);
  };
```

- [ ] **Step 3: 在右侧 ml-auto 容器最前面插入「整批作废」控件**

经 Task 2,右侧是 `<div className="ml-auto flex items-center gap-2">{selected.size > 0 && (...)}</div>`。在该 `<div>` 内部、`{selected.size > 0 && ...}` 之前插入整批作废控件:

```tsx
                {runDeleteOpen ? (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">整批作废:</span>
                    {runFilter !== "all" ? (
                      <span className="text-xs text-muted-foreground">
                        删除任务「{formatRunLabel(runMap.get(runFilter) ?? null, runFilter)}」全部货物?
                      </span>
                    ) : (
                      <Select
                        value={runDeleteTarget}
                        onValueChange={(v) => setRunDeleteTarget(v)}
                      >
                        <SelectTrigger className="h-7 w-[200px] text-xs">
                          <SelectValue placeholder="选择任务" />
                        </SelectTrigger>
                        <SelectContent>
                          {runs.map((r) => (
                            <SelectItem key={r.id} value={r.id}>
                              {formatRunLabel(r, r.id)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    <Button
                      size="sm"
                      variant="destructive"
                      className="text-xs h-7"
                      onClick={handleRunDelete}
                      disabled={runDeleteTarget === "all" || deleteItemsByRun.isPending}
                    >
                      确认删除
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs h-7"
                      onClick={() => {
                        setRunDeleteOpen(false);
                        setRunDeleteTarget("all");
                      }}
                    >
                      取消
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-xs h-7 text-destructive hover:text-destructive"
                    onClick={openRunDelete}
                    disabled={runs.length === 0}
                    title={runs.length === 0 ? "暂无任务" : "按抽取任务整批删除货物"}
                  >
                    <Trash2 className="h-3 w-3" />
                    整批作废
                  </Button>
                )}
```

> `deleteItemsByRun`、`runs`、`runMap`、`formatRunLabel`、`Select*`、`Trash2` 均已存在。

- [ ] **Step 4: 验证 typecheck + lint**

```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 通过。

- [ ] **Step 5: 重启前端 + 手动 QA**

```bash
docker compose -p eai-docker restart frontend
```
验证两条路径:
1. **已选任务筛选**时点「整批作废」→ 显示"删除任务「…」全部货物?"+ 确认 → 该任务货物从列表消失(切回"全部任务"确认)。
2. **"全部任务"**时点「整批作废」→ 出现任务下拉,"确认删除"在未选时禁用;选一个任务后确认 → 删除生效。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/extensions/contract-price/components/ItemsView.tsx
git commit -m "feat(cpa): 分项校验新增常驻整批作废按钮(按任务删除)"
```

---

## Task 6: 最终验证(全路径回归)

**Files:** 无改动。

- [ ] **Step 1: 全量 typecheck + lint**

```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 通过。

- [ ] **Step 2: 重启前端**

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 3: 手动 QA 全路径(对应设计文档第 5 节)**

登录 `localhost:2026` → 合同价格分析 → 分项校验,逐项确认:

1. **翻页跨任务**:翻到第 2/3 页能看到更早任务的货物(缺陷已修复)。
2. **来源任务筛选**:下拉选某任务只显示该任务货物;切回"全部任务"恢复。
3. **来源任务列**:列存在,紧凑标签 + tooltip 正确;历史数据"未关联";明细行不错位。
4. **常驻整批作废**:两条路径(有筛选直删 / 无筛选选任务删)均生效。
5. **仅看待核验**:打开后跨任务聚合所有 `needs_review` 项。
6. **回归未损**:单行修正、单行删除二次确认、批量确认校验、批量删除已选、异常价格高亮、来源合同筛选、溯源抽屉。

- [ ] **Step 4: 更新项目记忆(可选)**

若有 OpenWolf 约定的 `.wolf/memory.md`,追加一行记录本次改动;`ItemsView.tsx` 的 anatomy 描述如有"分组"字样一并更新。非阻塞。

---

## Self-Review(计划作者自查记录)

- **Spec 覆盖**:设计文档第 3.1(run_id 注入)→ Task 1;3.3(a)(下拉)、(b)(列)、(c)(整批作废)→ Task 3/4/5;3.3 删除项(groupByRun/groups/collapsed/confirmGroupDelete/分组头)→ Task 2;3.4 选择行为(toggleSelectAll 改当前页、批量删除)→ Task 2;第 4 节边界(onlyReview 跨任务、run_id 空历史数据)→ Task 6 QA 路径 4/5;第 5 节测试(无单测、typecheck+lint+QA)→ 各任务 Step + 开头说明。无遗漏。
- **占位符扫描**:无 TBD/TODO。Task 2 Step 3 的 `{/* === 保留原有每行渲染 === */}` 是"指明保留哪段已有代码"的标记,非待实现占位——已配文字说明搬运来源。
- **类型/命名一致性**:`runFilter`/`setRunFilter`、`runMap`、`runDeleteOpen`/`runDeleteTarget`、`handleRunDelete`/`openRunDelete`、`formatRunCompact` 在各 Task 间命名一致;`toggleSelectAll(pageItems)` 签名 Task 2 改后,Task 2 Step 3 的 `onChange={() => toggleSelectAll(items)}` 调用与之匹配;colSpan 7→8 在 Task 4 与 Task 2 产出的 7 列表头一致(操作列算第 7 列,加来源任务变 8 列)。
