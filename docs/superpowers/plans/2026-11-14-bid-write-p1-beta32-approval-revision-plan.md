# bid_write 批三十二（审批流复用 workflow + 不可变修订）Implementation Plan

> **For agentic workers:** 逐任务勾选。批三十一收口 NEXT=审批流；本批不制造「批了也不能导出」的假闭环，导出服务仍留后续批，但批准后的修订快照、哈希与编辑锁必须真实生效。

**Goal:** 投标正文提交审批时冻结不可变修订（AST + hash + 断言快照），审批编排复用 EAI workflow 子系统的 DAG 顺序与 review gate；支持会签/或签/比例签/顺序签、驳回后继续编辑、批准后锁定与重复操作保护。

**Architecture:**

- `workflow/subject_approval.py` 提供 **subject-bound** 通用审批实例：`subject_type/subject_id/subject_version` + workflow graph 快照 + 节点级 review 分配 + `evaluate_gate`。不绑定 `ReportProject`，不改 `PhaseReview/ReviewAssignment` 旧表。
- `bid_write` 负责业务对象：`bid_write_document_revisions` 冻结 AST、`doc_hash`、`assertion_snapshot`；提交/审批动作经 workflow subject 服务编排。
- 有 `workflow_definition_id` 时快照该定义的 `graph_json`；缺省时使用内置单节点审批图（仍需显式指定审批人）。定义后续编辑不影响在途审批。
- 审批只针对 revision；待审批/已批准期间普通 `PUT /document` 返回 409，驳回后允许继续编辑并生成新 revision。

**边界诚实（不做）：**
- 不做 Word/PDF 文件导出服务；本批只保证批准 revision 可作为后续导出唯一消费对象。
- 不改造 `PhaseReview`/`ReviewAssignment` 双模型历史债；bid-write 不写 `report_projects`。
- 不解析角色/岗位到用户；MVP 只接受显式 `reviewer_ids` 或 workflow 定义中 `type=user` 的绑定，其他绑定类型诚实拒绝。
- 不接 Temporal 工作流实例；审批实例与动作以数据库为准，Temporal 后续可作为执行器接入。

---

### Task 1: workflow 通用 subject 审批

**Files:**
- Create: `backend/app/extensions/workflow/subject_approval.py`
- Modify: `backend/app/extensions/review/gate.py`
- Test: `backend/tests/test_workflow_subject_approval.py`

- [x] `WorkflowSubjectInstance` / `WorkflowSubjectReview` 新表（String/JSON，SQLite 可测；create_all 承接）。
- [x] `start_subject_approval(...)`：校验 DAG、按拓扑序提取 review 节点、创建首节点分配；支持 workflow 定义 graph 快照。
- [x] `submit_subject_action(...)`：仅指定审批人可操作；重复操作 409；按 `reviewMode` 映射 `evaluate_gate`；通过后推进下一 review 节点，驳回终止。
- [x] 顺序签只允许当前 sequence 审批；会签/或签/比例签阈值行为有测试。
- [x] `evaluate_gate` 增加可选 `threshold`，不传时保持原行为。

### Task 2: bid-write 不可变修订与审批 API

**Files:**
- Modify: `backend/app/extensions/bid_write/models.py`
- Modify: `backend/app/extensions/bid_write/crud.py`
- Modify: `backend/app/extensions/bid_write/schemas.py`
- Create: `backend/app/extensions/bid_write/approval.py`
- Modify: `backend/app/extensions/bid_write/routers.py`
- Test: `backend/tests/test_bid_write_approval.py`

- [x] `BidWriteDocumentRevision`：task/revision_no/ast/schema_version/doc_hash/assertion_snapshot/status/approval_instance_id。
- [x] `POST /tasks/{id}/approval/submit`：可原子接收当前 AST；校验根/semver、可选 `document_hash` 不一致 409、待审批/已批准重复提交 409。
- [x] `GET /tasks/{id}/approval`：最新 revision + instance + reviews + `my_review/can_act`。
- [x] `POST /tasks/{id}/approval/action`：`approved|rejected`；非指定审批人 403、重复操作 409；同步 revision 状态。
- [x] `GET /tasks/{id}/revisions` 与 `GET /tasks/{id}/revisions/{revision_id}`：只读修订账本，返回 hash 校验结果。
- [x] `PUT /document`：待审批/已批准 409；驳回后可编辑。
- [x] 被指派审批人可只读访问任务/矩阵/缺口/正文/审批面（非审批人仍 404）。

### Task 3: 工作台审批面

**Files:**
- Modify: `frontend/src/extensions/bid-write/types.ts`
- Modify: `frontend/src/extensions/bid-write/api.ts`
- Modify: `frontend/src/extensions/bid-write/hooks.ts`
- Create: `frontend/src/extensions/bid-write/components/ApprovalPanel.tsx`
- Modify: `frontend/src/extensions/bid-write/components/WorkbenchView.tsx`
- Modify: `frontend/src/extensions/bid-write/editor/BidWriteEditor.tsx`
- Test: `frontend/tests/unit/extensions/bid-write-approval-panel.dom.test.tsx`

- [x] 类型/API/hooks：approval 查询、submit、action；动作后失效 approval/document/task 查询。
- [x] 面板显示 revision 号/hash/状态/审批节点/审批人意见；owner 可提交，pending 且当前用户被指派时可批准/驳回。
- [x] 提交使用编辑器当前 AST，避免「未保存内容未进入冻结快照」。
- [x] 批准后编辑器只读并显示锁定原因；驳回显示意见并恢复可编辑。

### Task 4: 验证与收口

- [x] 后端 subject 审批 + bid-write approval 定向 pytest 全绿。
- [x] 既有 bid-write document/router 测试更新建表清单后全绿。
- [x] 前端 approval 专项 + bid-write 全组 rstest 全绿；changed-file eslint 通过。
- [x] `tsc --noEmit` 仅剩既有 password-forms TS2367（若仍在）。
- [x] 更新 `.wolf` 三件套与 memory，plan 勾选。

## 落地结果（2026-11-14）

**实现**
- `workflow/subject_approval.py`：通用 subject 审批实例（`workflow_subject_instances` / `workflow_subject_reviews`），按 `subject_type + subject_id + subject_version` 绑定；`start_subject_approval` 校验 DAG、按拓扑序提取 review 节点并快照 graph；`submit_subject_action` 校验指定审批人、重复动作 409、按 reviewMode 映射 `evaluate_gate`，通过后推进下一节点、驳回终止。会签/或签/比例签/顺序签均落地；只解析显式 `type=user` 的绑定，角色/岗位不猜测。
- `review/gate.py`：`evaluate_gate` 新增可选 `threshold`（仅 WEIGHTED/比例签使用）；会签收到驳回立即 REJECT，原 majority 行为不变。
- `BidWriteDocumentRevision`：冻结 `ast/schema_version/doc_hash/assertion_snapshot/status/approval_instance_id`；`doc_hash` 为 canonical JSON 的 SHA-256，详情返回 `hash_ok` 检测篡改。提交失败不留下半保存正文（审批实例创建成功后统一 commit）。
- 新增 API：`GET /tasks/{id}/approval`、`POST /tasks/{id}/approval/submit`、`POST /tasks/{id}/approval/action`、`GET /tasks/{id}/revisions`、`GET /tasks/{id}/revisions/{revision_id}`。`PUT /document` 在待审批/已批准时返回 409，驳回后可编辑；被指派审批人可只读访问任务/矩阵/缺口/正文/审批面，非审批人仍 404。
- 前端 `ApprovalPanel.tsx` + 工作台接线：展示 revision 号/hash/状态/断言快照/审批节点与意见；owner 提交当前 AST；审批人批准/驳回；批准后 `BidWriteEditor` 只读。

**验证**
- 后端定向 `46 passed`；全量过滤 `uv run pytest tests -k "bid_write or workflow_subject" -q` → `253 passed, 6 skipped`。
- 前端 bid-write 全组 16 文件 `88/88`；ApprovalPanel `3/3`；changed-file eslint 通过。
- `tsc --noEmit` 仅剩既有 `frontend/tests/unit/components/auth/password-forms.dom.test.tsx` 3 条 TS2367。
- 未做浏览器实机验证（本地 `:3000`/`:8001` 未启动）。

**边界**
- 不做 Word/PDF 文件导出服务；批准后的 revision 是后续导出的唯一消费对象。
- 不改造 `PhaseReview`/`ReviewAssignment` 双模型历史债，不写 `report_projects`。
- 不接 Temporal；审批实例与动作以数据库为准。

