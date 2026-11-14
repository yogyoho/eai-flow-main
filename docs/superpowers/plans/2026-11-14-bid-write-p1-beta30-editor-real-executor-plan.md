# bid_write 批三十（M4 真执行器接线）Implementation Plan

> **For agentic workers:** 逐任务勾选。批廿九收口 NEXT=真执行器(assertRunner 替换演示执行器)。

**Goal:** 云端正文 AST 的编辑校验改由后端真实断言执行器（43 条注册断言）产出，前端只消费 `states/skipped` 侧信道；后端不可用时显示「校验未完成」，不回退假绿。

**Architecture:** 新增 `executor/editor.py`：把 AST 价格表/商务响应表/投标函文本覆盖到任务生成 ctx，跑 `run_assertions`，再把失败结果按锚点映射为 `{D0|D1|D2}` 状态。新增 `POST /tasks/{id}/assert`（只读、不落 skill_run）。前端 `AssertRunner` 支持异步+序号防陈旧响应；云端文档用服务端 runner，演示文档保留本地演示 runner。

**边界诚实（不做）：**
- 附件索引表尚未在 AST schema 中承载 → AI 面继续使用任务生成 ctx；AST 覆盖附件索引挂后续批。
- 审批人工流、parseDOM 富文本粘贴清洗不在本批。
- 服务端 runner 仅对「云端文档」启用；演示文档与任务数据无对应关系，继续用本地演示执行器并保留徽标。
- `row_id` 碰撞：后端 422 明示（生成器约定全文唯一）。

---

### Task 1: 后端 AST→ctx 覆盖 + 锚点映射

**Files:**
- Create: `backend/app/extensions/bid_write/executor/editor.py`
- Test: `backend/tests/test_bid_write_editor_assert.py`

- [x] 实现 `run_editor_assertions(base_ctx, ast, skills=None)`：deepcopy 覆盖 price/response/bid_letter；重算 `pre.ps_replay_equal` / `pre.rt_excerpt_overlaps` / `pre.rt_cross_field`；调用 `run_assertions`。
- [x] 失败结果锚点映射：`price:{row_id}` / `rt:{row_id}`（frontend anchorKey 同步）/ `devnote:{row_id}` / `todo:{id}` / 投标函段落 slot；其他失败只进状态栏。
- [x] 保留本地结构性渲染事实：todo 占位、status_mark、孤儿展开面 D1；RT-005 仅在真实断言 FAIL 时给未闭环展开面 D0。
- [x] row_id 重复 → `ValueError`（router 422）。
- [x] pytest：green ctx + AST 全 PASS；改投标函金额 → PS-003/BL-002 锚点；改行金额 → PS-008 行锚点；负偏离未闭环 → RT-002/RT-005；重复 row_id 拒绝。

### Task 2: 端点与 schema

**Files:**
- Modify: `backend/app/extensions/bid_write/schemas.py`
- Modify: `backend/app/extensions/bid_write/routers.py`
- Test: `backend/tests/test_bid_write_editor_assert.py`

- [x] `EditorAssertIn{ast, skills?}`。
- [x] `POST /tasks/{task_id}/assert`：owner 404；ast 根 type 校验 422；`build_task_ctx` → `run_editor_assertions`；只读不落库。
- [x] pytest：200 形状 / 404 / 422 / 不写 skill_run。

### Task 3: 前端 API + 异步 runner

**Files:**
- Modify: `frontend/src/extensions/bid-write/api.ts`
- Modify: `frontend/src/extensions/bid-write/types.ts`
- Modify: `frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx`
- Modify: `frontend/src/extensions/bid-write/editor/decor.ts`
- Modify: `frontend/src/extensions/bid-write/components/WorkbenchView.tsx`

- [x] `assertTaskDocument(taskId, {ast, skills?})`。
- [x] `AssertRunner` 支持 `Promise`；序号防陈旧响应；null/异常 → `onAssert(null, true)`。
- [x] `anchorKey` 增加 response 表行 `rt:{row_id}`。
- [x] 工作台：cloud → 后端 runner；demo → 本地 runner；文案改 M4（真执行器）。
- [x] rstest：api 路径/错误；response 行锚点装饰；既有 40 例不回退。

### Task 4: 验证与收口

- [x] 后端 targeted pytest 全绿。
- [x] 前端 targeted rstest 全绿。
- [x] 更新 plan 勾选 + wolf 三件套 + memory 批次记录。

## 落地结果（2026-11-14）

- 后端 `tests/test_bid_write_editor_assert.py` 10/10；bid_write 相关回归 119/119。
- 前端 `tests/unit/extensions/bid-write*` 13 文件 72/72。
- `ruff check` / `ruff format --check` 通过；前端 changed-file eslint 通过。
- `tsc --noEmit` 仅剩既有脏文件 `tests/unit/components/auth/password-forms.dom.test.tsx` 的 3 条预存 TS2367（批廿八已记录，非本批回归）。
- 未做浏览器实机验证：本地 `:3000` / `:8001` 未启动；端点已由 ASGI 级测试覆盖。
