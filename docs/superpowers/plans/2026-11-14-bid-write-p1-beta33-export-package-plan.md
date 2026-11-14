# bid_write 批三十三（P1-M6）：批准修订 DOCX 交付包 Implementation Plan

> **For agentic workers:** 逐任务勾选。批三十二已保证「审批只消费冻结 revision」；本批把该 revision 真正变成可交付文件，但只做 DOCX 交付包，不伪造 PDF/CA 签章。

**Goal:** 已批准且哈希校验通过的正文修订 → 按一级章节分册生成 DOCX，连同 `manifest.json` 打成确定性 ZIP；导出前用 revision AST 重跑导出前置门禁，未批准/篡改/D0 阻断一律拒绝。

**Architecture:**

- `bid_write/export.py`：AST → Markdown 投影（marks 按 §四剥离）、一级 `section` 切册、复用 `output.generator.generate_docx_simple`（A4/标题/表格/页码/TOC/水印）、固定时间戳打 ZIP。
- `precheck.run_export_gate` 增加 `ast=`，通过 `executor.editor.prepare_editor_ctx` 把冻结 AST 覆盖到任务 ctx 后再跑 43 条断言与规则层；导出与「导出前置校验」同尺。
- 新增 `bid_write_exports` 审计表：只记成功导出（revision/doc_hash/bundle_sha256/file_count/total_bytes/watermark）。
- API：`POST /tasks/{id}/revisions/{rid}/export` 返回 ZIP + `X-Export-*` 头；`GET /tasks/{id}/exports` 返回导出历史。owner-only。
- 前端 ExportView：仅 `revision.status=approved` 时可生成交付包；下载 blob，展示文件数/哈希/水印与历史记录。

**边界诚实（不做）：**
- 不做 PDF、CA 签章、投标客户端导入包；签章位只来自 AST 内已有节点，不凭空生成。
- 不接排版模板编辑器；先用 `generate_docx_simple` 的稳定默认版式 + 页码 + TOC。
- L4 仍为 advisory-only：导出时未跑模型审查则水印保持「商务风险未确认」，不阻断。

---

### Task 1: 冻结 AST 进入导出 gate

**Files:**
- Modify: `backend/app/extensions/bid_write/executor/editor.py`
- Modify: `backend/app/extensions/bid_write/precheck.py`
- Test: `backend/tests/test_bid_write_export.py`

- [x] 抽出 `prepare_editor_ctx(base_ctx, ast) -> (ctx, meta)`，`run_editor_assertions` 复用。
- [x] `run_export_gate(..., ast=None)`：传入 AST 时先覆盖 price/response/letter/slots 再跑断言与投影；不传时保持原行为。
- [x] 测试：同一 ctx 下 revision AST 的价格/响应表覆盖会改变 gate 结果；原调用零行为变化。

### Task 2: 交付包生成器

**Files:**
- Create: `backend/app/extensions/bid_write/export.py`
- Test: `backend/tests/test_bid_write_export.py`

- [x] `ast_to_markdown(ast)`：section/para/locked_paragraph/table/todo_block/deviation_note/attachment_ref/toc_entry；marks 剥离；未知节点 ValueError。
- [x] `split_volumes(ast)`：一级 `section` 起新册；首节前内容附首册；无一级节=单册「正文」。
- [x] `build_export_bundle(...)`：每册 DOCX（A4/页码/TOC/水印）+ `manifest.json`，固定 ZIP 时间戳与排序，返回 sha256/文件名/文件清单。
- [x] 单元测试：Markdown 投影、切册、同 revision+固定时钟字节级确定性、DOCX 内文本可读。

### Task 3: 导出 API 与审计

**Files:**
- Modify: `backend/app/extensions/bid_write/models.py`
- Modify: `backend/app/extensions/bid_write/crud.py`
- Create/Modify: `backend/app/extensions/bid_write/export.py`
- Modify: `backend/app/extensions/bid_write/routers.py`
- Test: `backend/tests/test_bid_write_export.py`

- [x] `BidWriteExport` 表（String/JSON；create_all 承接）。
- [x] `export_revision`：approved + hash_ok + 提交快照未 blocked + 当前 gate 未 blocked；失败 409 且不落审计。
- [x] `POST /tasks/{id}/revisions/{rid}/export`：ZIP + `X-Export-Id/Sha256/Files/Bytes`。
- [x] `GET /tasks/{id}/exports`：按时间倒序返回历史；owner-only，审批人不可导出。
- [x] 测试：未批准 409、篡改 409、门禁阻断 409、成功 ZIP/manifest/审计、非 owner 404。

### Task 4: 前端交付包

**Files:**
- Modify: `frontend/src/extensions/bid-write/types.ts`
- Modify: `frontend/src/extensions/bid-write/api.ts`
- Modify: `frontend/src/extensions/bid-write/hooks.ts`
- Modify: `frontend/src/extensions/bid-write/components/ExportView.tsx`
- Test: `frontend/tests/unit/extensions/bid-write-export-package.dom.test.tsx`

- [x] 类型/API：approval、export history、下载 blob（解析 Content-Disposition 与 X-Export-*）。
- [x] ExportView：未批准时禁用并说明原因；批准后生成交付包、触发下载、展示哈希/文件数/水印。
- [x] 展示导出历史；失败 toast 后端 detail。
- [x] DOM 测试：未批准禁用、批准后 POST 下载、历史渲染。

### Task 5: 验证与收口

- [x] 后端 export 定向 + 既有 bid_write/workflow 过滤全绿；ruff check/format 通过。
- [x] 前端 bid-write 全组 rstest、changed-file eslint 通过；tsc 仅既有 password-forms TS2367。
- [x] 更新 `.wolf` 三件套与 memory，plan 勾选并回填落地结果。

## 落地结果（2026-11-15）

**实现**
- `executor/editor.py`：抽出 `prepare_editor_ctx(base_ctx, ast) -> (ctx, meta)`，编辑器断言与导出 gate 共用同一冻结 AST 覆盖面；`run_editor_assertions` 行为不变。
- `precheck.run_export_gate(..., ast=None)`：传入 revision AST 时先覆盖 price/response/letter/slots 再跑 43 条断言与规则层，导出与导出前置校验同尺。
- `bid_write/export.py`：AST→Markdown（marks 剥离、未知节点显式报错）、一级 `section` 切册、`generate_docx_simple` 每册 A4/页码/TOC/水印、DOCX 固定时间戳重打包、`manifest.json`（revision/doc_hash/gate/files 哈希）、确定性 ZIP。
- `BidWriteExport` 审计表 + `POST /tasks/{id}/revisions/{rid}/export` + `GET /tasks/{id}/exports`；成功响应带 `X-Export-Id/Sha256/Files/Bytes/Watermarked`，CORS 白名单已暴露。
- 导出前置条件：`approved` + `hash_ok` + 提交快照未 blocked + 当前 gate 未 blocked；任一失败 409，且不落审计记录。
- 前端 `DeliveryPackageCard.tsx` + ExportView 接线：仅批准修订可生成交付包，下载 blob，展示文件数/包哈希/水印与最近导出记录。

**验证**
- 后端导出专项 `13 passed`；全量过滤 `uv run pytest tests -k "bid_write or workflow_subject" -q` → `266 passed, 6 skipped`。
- 前端 bid-write 全组 17 文件 `91/91`；交付包专项 `3/3`；changed-file eslint 通过。
- `ruff check` / `ruff format --check` 通过。
- `tsc --noEmit` 仅剩既有 `frontend/tests/unit/components/auth/password-forms.dom.test.tsx` 3 条 TS2367。
- 未做浏览器实机验证（本地 `:3000`/`:8001` 未启动）。

**边界**
- 只做 DOCX + manifest ZIP；不做 PDF、CA 签章或投标客户端导入包。
- 不接排版模板编辑器；签章位只来自 AST 已有节点，不凭空生成。
- L4 仍 advisory-only；未跑模型审查时交付包保留「商务风险未确认」水印。
- 分册规则=一级 `section` 起新册；单章超长不二次拆分，避免静默改变审批内容拓扑。
