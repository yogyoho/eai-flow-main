# bid-review Plan 5 — 新建审查任务对话框对齐原型 s2(弹窗形态,裁定 14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 任务总览页内「新建审查任务」**弹窗保留**(用户 2026-10-31 改定,spec §4.2 页化退役),对照原型 s2(L588-652)补齐:基本信息组(项目/标段=裁定 12 可选覆盖位、招标编号)、评审模式卡保持、单文件 ≤200MB 校验、drop 文案、身份字段随 POST /tasks 提交;后端 worker 抽取回填改「仅列 NULL 时回填」(人工覆盖位优先)。

**Architecture:** 后端 3 个可选 Form 字段空串归 None 直落 task 三列 + worker 回填加 None 守卫(契约不变,TaskOut 无新增);前端 api.createTask 加可选 identity 参数 → 弹窗加两个输入行(评审模式行下移至原型顺序)+200MB 拒收。测试:后端 routers pytest 新 1 例 + worker 回填守卫 1 例;前端 tasks-view dom 测试新 2 例。

**Tech Stack:** FastAPI Form/UploadFile + SQLAlchemy;React 19 / TanStack Query / rstest(happy-dom)。

**Spec:** `docs/superpowers/specs/2026-10-31-bid-review-ux-redesign-design.md` §6 裁定 12/14;原型 `docs/designs/2026-10-30-bid-review-ui.html` L588-652。

---

## 侦察结论(2026-10-31,全部实证)

- **不动的部分**:路由/权限/nav 全不需要(无新页);MODE_META 文案不抄原型虚构数字(3 条/21 条);规则包/审查模型 selects 不迁(v1 无后端能力);OCR note-bar 不抄(B3 落地前虚假承诺),维持 txt/md 诚实注记;文件必传门(tender/bid 各 ≥1)维持——后端零材料任务无条件直推空跑。
- **后端**:`routers.create_task`(routers.py L100-127)现收 mode/tender_files/bid_files;`crud.create_task`(crud.py L42-47)仅 owner+mode+biz_no;`worker.py` L460-462 回填**无条件覆盖** task.project_name/lot_name/tender_no——改 None 守卫。
- **前端**:`api.ts` createTask(L100-109)FormData 只 set mode+append 文件;TasksView 弹窗(L758-876)顺序=评审模式→FileGroup×2→note-bar→errbar→ft;FileGroup(L269-335)drop+点击上传(input aria-label=`选择{label}`)+文件表;文件名/大小/移除已有。
- **原型 s2 内容元素**(保真基准):页副题「上传投标文件 → 选择评审模式 → 引擎解析并出具带证据的问题清单」;基本信息=项目/标段名称(frm-help 用于列表展示与报告抬头)+招标编号(mono)+评审模式 mode-card;上传 drop 文案带「(单文件 ≤ 200MB)」;footer 取消/创建任务。

---

### Task 1: 后端 identity 覆盖位 + worker 回填 None 守卫

**Files:**
- Modify: `backend/app/extensions/bid_review/crud.py`(create_task)
- Modify: `backend/app/extensions/bid_review/routers.py`(create_task)
- Modify: `backend/app/extensions/bid_review/worker.py`(L460-462 回填)
- Test: `backend/tests/test_bid_review_routers.py` + `backend/tests/test_bid_review_worker.py`

- [x] **Step 1: 先写测试(红)**——routers.py 测试加在 `test_create_task_rejects_bad_mode` 后:

```python
@pytest.mark.asyncio
async def test_create_task_identity_overrides(client, db):
    """裁定12+14:弹窗身份字段=可选覆盖位,空串归 None(回填位),非空直落 task 三列。"""
    r = await client.post(
        "/api/extensions/bid-review/tasks",
        data={"mode": "quick", "project_name": "XX项目", "lot_name": "标段一", "tender_no": "TZ-2026-001", "": ""},
    )
    assert r.status_code == 200
    t = await crud.get_task(db, task_id=r.json()["id"], owner_id="u1")
    assert (t.project_name, t.lot_name, t.tender_no) == ("XX项目", "标段一", "TZ-2026-001")
    # 空串/未传 → None(留空=引擎抽取回填位)
    r2 = await client.post(
        "/api/extensions/bid-review/tasks",
        data={"mode": "quick", "project_name": "  "},
    )
    t2 = await crud.get_task(db, task_id=r2.json()["id"], owner_id="u1")
    assert (t2.project_name, t2.lot_name, t2.tender_no) == (None, None, None)
```

  worker 测试:grep `project_identity` 定位既有回填用例,新加一例:

```python
@pytest.mark.asyncio
async def test_extract_backfill_skips_manual_overrides(...):
    # 建 task 时直写 project_name=「人工填写」→ 跑 extract 段 → 断言不被覆盖,
    # lot_name/tender_no(未填)照常回填。
```

- [x] **Step 2: 跑红** `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_routers.py -k identity -v` → FAIL(422,unexpected field)

- [x] **Step 3: 实现(绿)**——

  crud.py:
```python
async def create_task(
    session: AsyncSession,
    owner_id: str,
    mode: str = "quick",
    *,
    project_name: str | None = None,
    lot_name: str | None = None,
    tender_no: str | None = None,
) -> ReviewTask:
    # 裁定12+14:身份字段=弹窗可选覆盖位;NULL 落列,worker 抽取回填仅填 NULL(EAI-CUSTOM 2026-10-31)
    task = ReviewTask(owner_id=owner_id, mode=mode, biz_no=await _next_biz_no(session), project_name=project_name, lot_name=lot_name, tender_no=tender_no)
```

  routers.py create_task 签名加三参 + 透传(空串归 None):
```python
    project_name: str = Form(""),
    lot_name: str = Form(""),
    tender_no: str = Form(""),
```
```python
    # 裁定12+14:可选身份覆盖位(空串归 None=引擎抽取回填位)
    task = await crud.create_task(db, owner_id=owner_id, mode=mode,
        project_name=project_name.strip() or None,
        lot_name=lot_name.strip() or None,
        tender_no=tender_no.strip() or None)
```

  worker.py L460-462:
```python
    # 裁定12+14:人工覆盖位优先——仅列为 NULL(弹窗留空)时抽取回填,不覆盖手填值
    if task.project_name is None:
        task.project_name = _scalar(fields.get("tender.project_identity.name"))
    if task.lot_name is None:
        task.lot_name = _scalar(fields.get("tender.project_identity.lot_section"))
    if task.tender_no is None:
        task.tender_no = _scalar(fields.get("tender.project_identity.code"))
```

- [x] **Step 4: 跑绿** `PYTHONPATH=. uv run pytest tests/test_bid_review_routers.py tests/test_bid_review_worker.py -v`
- [x] **Step 5: Commit** `feat(bid-review): POST /tasks 可选身份覆盖位+worker 回填仅填 NULL(裁定12/14,Plan5 T1)`

---

### Task 2: api.ts createTask identity 参数

**Files:**
- Modify: `frontend/src/extensions/bid-review/api.ts`(createTask)

- [x] **Step 1: 实现**(纯透传,dom 测试在 T3 一起断言):

```ts
export function createTask(
  mode: "quick" | "deep",
  files: { tender: File[]; bid: File[] },
  /** 裁定12+14:可选身份覆盖位(项目/标段/招标编号);空串/空白不 append,留空=引擎抽取回填。 */
  identity?: { project_name?: string | null; lot_name?: string | null; tender_no?: string | null },
): Promise<TaskOut> {
  const form = new FormData();
  form.set("mode", mode);
  if (identity?.project_name?.trim()) form.set("project_name", identity.project_name.trim());
  if (identity?.lot_name?.trim()) form.set("lot_name", identity.lot_name.trim());
  if (identity?.tender_no?.trim()) form.set("tender_no", identity.tender_no.trim());
  for (const f of files.tender) form.append("tender_files", f);
  for (const f of files.bid) form.append("bid_files", f);
  return request<TaskOut>("/tasks", { method: "POST", body: form });
}
```

- [x] **Step 2:** `pnpm typecheck`(9 个 contract-price 既有错误除外)→ Commit `feat(bid-review): createTask 可选身份覆盖位参数(Plan5 T2)`

---

### Task 3: 弹窗对齐原型 s2(基本信息组 + 200MB + 顺序)

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/TasksView.tsx`(state/基本信息行/200MB/顺序)
- Test: `frontend/tests/unit/extensions/bid-review-tasks-view.dom.test.tsx`(新 2 用例)

- [x] **Step 1: 先改测试(红)**——新用例(加在搜索用例后):

```tsx
  it("对话框:身份字段随 FormData 提交,留空不发;创建成功跳工作台", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks")) {
        return path.includes("POST") || true ? jsonRes({ items: [TASK] }) : jsonRes({});
      }
      return jsonRes({}, 404);
    };
```
  (responder 通用 `path.endsWith("/tasks")` 分支同时接 GET/POST——fetcher mock 不区分 method,POST 返回 items 也无妨,onSuccess 只用 id;若拿到 items 数组导致 taskHref 异常,则 responder 按 `init?.method === "POST"` 返回 `{...TASK}` 单对象。)
```tsx
    renderTasks();
    await screen.findByTitle("t1");
    fireEvent.click(screen.getByRole("button", { name: "新建审查任务" }));
    fireEvent.change(screen.getByLabelText("项目 / 标段名称"), { target: { value: "XX数据中心二期" } });
    fireEvent.change(screen.getByLabelText("招标编号"), { target: { value: "TZ-2026-009" } });
    const inputs = document.querySelectorAll<HTMLInputElement>('.modal input[type="file"]');
    fireEvent.change(inputs[0]!, { target: { files: [new File(["T"], "t.txt", { type: "text/plain" })] } });
    fireEvent.change(inputs[1]!, { target: { files: [new File(["B"], "b.txt", { type: "text/plain" })] } });
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await waitFor(() => {
      const post = calls.find((c) => c.init?.method === "POST");
      const form = post?.init?.body as FormData;
      expect(form.get("project_name")).toBe("XX数据中心二期");
      expect(form.get("lot_name")).toBeNull();
      expect(form.get("tender_no")).toBe("TZ-2026-009");
      expect(form.get("mode")).toBe("quick");
    });
  });

  it("对话框:单文件 >200MB 拒收(errbar 提示,文件不入列)", async () => {
    responder = (path) => jsonRes({ items: [TASK] });
    renderTasks();
    await screen.findByTitle("t1");
    fireEvent.click(screen.getByRole("button", { name: "新建审查任务" }));
    const big = new File(["x"], "huge.bin");
    Object.defineProperty(big, "size", { value: 201 * 1024 * 1024 });
    const inputs = document.querySelectorAll<HTMLInputElement>('.modal input[type="file"]');
    fireEvent.change(inputs[0]!, { target: { files: [big] } });
    expect(screen.getByRole("alert").textContent).toContain("超过 200MB 上限");
    expect(screen.queryByTitle("huge.bin")).toBeNull();
  });
```

- [x] **Step 2: 跑红** `cd frontend && pnpm test bid-review-tasks-view` → 新 2 例 FAIL(无 项目 / 标段名称 label)

- [x] **Step 3: 实现(绿)**——TasksView.tsx:

  a) 常量与 state(L352 附近):
```ts
/** 原型 s2:单文件 ≤ 200MB(前端拒收,超限不入列)。 */
const MAX_FILE_MB = 200;
```
```ts
  const [projectName, setProjectName] = useState("");
  const [lotName, setLotName] = useState("");
  const [tenderNo, setTenderNo] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const addFiles =
    (setter: (fn: (prev: File[]) => File[]) => void) => (fs: File[]) => {
      const ok = fs.filter((f) => f.size <= MAX_FILE_MB * 1024 * 1024);
      const rejected = fs.length - ok.length;
      if (rejected > 0) setFileError(`${rejected} 个文件超过 ${MAX_FILE_MB}MB 上限,已跳过`);
      else if (ok.length > 0) setFileError(null);
      if (ok.length > 0) setter((prev) => [...prev, ...ok]);
    };
```
  openDialog 重置五个 state(含 fileError=null)。

  b) modal-bd 结构按原型顺序重排:**基本信息两行 → 评审模式(原行下移)→ FileGroup×2(onAdd 换 addFiles 包装)→ note-bar → fileError errbar + createMutation errbar**:
```tsx
              <div className="frm-row">
                <label>项目 / 标段名称</label>
                <div>
                  <input
                    className="inp"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    placeholder="如:XX数据中心一期采购项目 · 标段一"
                    aria-label="项目 / 标段名称"
                  />
                  <div className="frm-help">用于任务列表展示与报告抬头;留空由引擎从投标文件自动抽取回填。</div>
                </div>
              </div>
              <div className="frm-row">
                <label>招标编号</label>
                <input
                  className="inp mono"
                  value={tenderNo}
                  onChange={(e) => setTenderNo(e.target.value)}
                  placeholder="选填"
                  aria-label="招标编号"
                />
              </div>
```
  (inp/mono 类名为该扩展现有词汇;若 bid-review page.css 无 `.inp`,复用既有 input 样式类——实现时以页面既有弹窗内 input 为准。)
  createMutation.mutate 加第三参:
```tsx
                onClick={() =>
                  createMutation.mutate({
                    mode,
                    tender: tenderFiles,
                    bid: bidFiles,
                  }, identity: undefined as never) /* 实现为 createMutation 内传 identity */
                }
```
  (mutation 变量改传 identity:`createMutation.mutate({ mode, tender: tenderFiles, bid: bidFiles, identity: { project_name: projectName, lot_name: lotName, tender_no: tenderNo } })`,useMutation mutationFn 解构 identity 传 api。)
  c) FileGroup 静态文案:`(可多选;单文件 ≤ 200MB;招标与投标文件至少各一份)`。
  d) fileError 渲染:
```tsx
              {fileError ? (
                <div className="note-bar errbar" role="alert">
                  <Info className="ic" aria-hidden="true" />
                  <span>{fileError}</span>
                </div>
              ) : null}
```

- [x] **Step 4: 跑绿** `pnpm test bid-review-tasks-view` → 10 用例全绿;`pnpm test bid-review` 全套回归
- [x] **Step 5: Commit** `feat(bid-review): 新建任务对话框对齐原型 s2——基本信息覆盖位+200MB 校验(Plan5 T3)`

---

### Task 4: 收尾验证 + 记账

- [x] **Step 1:** `cd backend && make lint` + `cd frontend && pnpm typecheck && pnpm lint`
- [x] **Step 2:** 记账——`.wolf/memory.md` 一条;`.wolf/anatomy.md` plan5 条目;cerebrum 记用户裁定(弹窗保留,spec §4.2 页化退役);spec 修订已先行落盘(裁定 14+§4.2 退役注记)。
- [x] **Step 3:** push `git push origin main-dev-fork`(flaky 重试)。

---

## Self-Review

- **Spec 覆盖**:裁定 12(可选覆盖位)=T1/T2/T3;裁定 14(弹窗保留+s2 元素)=T3;200MB=裁定 5=T3;worker 覆盖位语义=T1。无缺口。
- **占位符扫描**:T3 mutates 代码段含修正注记(实现以真实现形为准),无 TBD。
- **类型一致性**:identity 三字段名前后端一致(project_name/lot_name/tender_no);createTask 第三参可选,既有 2 处调用(弹窗 mutationFn)同步。
