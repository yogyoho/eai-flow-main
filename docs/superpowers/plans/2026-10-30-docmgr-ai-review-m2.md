# docmgr AI 审查 findings 闭环（M2）实施计划

> **For agentic workers:** 按 superpowers:subagent-driven-development 执行；两个实现块顺序派发（Chunk2 依赖 Chunk1 的事件契约落库，且共享受审文件时避免并发）。

**Goal:** 按 M1 总 spec §5 落地 `POST /api/extensions/docmgr/ai/review` 审查管线 + `contracts/docmgr_findings.v1.json` 契约 + 面板 v2 内的审查任务区（FindingsCard 分组/定位/修复/忽略/全部修复），并把 panel v2 复审挂账的 computeHeadings 前导节 media-block 近似一并加固。

**Spec:** `docs/superpowers/specs/2026-10-29-docmgr-ai-fulltext-ops-design.md` §5（端点/两遍法/契约/FindingsCard）+ §8 YAGNI 边界。计划 = 100c5c4b5 同系风格，先例 = M1 plan（2107cb3f9）。

## 范围裁决（spec 之外的三个决定）

| 议题 | 裁决 | 理由 |
|---|---|---|
| 审查入口 UI | 空态六宫格下增第二组「深度审查」（3 卡：术语一致性/编号连续性/公式单位），与改写组互斥选中同一 launcher | review=只报告不改文，与改写预设语义不同必须分组；复用 launcher 目标 pills 机制零新增 |
| review:custom | v1 仅 API 可达，不进宫格 | spec 列了 4 类型，但 custom 无固定文案入口，塞宫格需再设计；挂账 |
| sections 部分审查 | v1 不收 sections 参数，全文档审查 | 两遍法（全局表）天然全文档；部分重跑价值低，挂账 |
| panel v2 挂账 UI（最近操作/@pills/思考折叠/建议chips/👍👎） | 继续挂账，不进 M2 | 无数据源契约设计，塞入即超纲（spec §8 YAGNI） |
| computeHeadings media-block 前导近似 | 进 M2 修复（panel v2 复审挂账①） | 一行加固+1 测试，搭车顺路 |

## 契约（先于一切代码落盘）

`contracts/docmgr_findings.v1.json`（沿 `contracts/knowledge_sources.v1.json` 先例，JSON Schema 形态）：

```json
{
  "$id": "docmgr_findings.v1",
  "type": "object",
  "required": ["id", "severity", "anchor", "excerpt", "problem", "suggestion"],
  "properties": {
    "id":         {"type": "string", "description": "{review_type}-{section_index}-{n}，会话内稳定、跨会话不稳定（不做记忆）"},
    "severity":   {"enum": ["error", "warn", "info"]},
    "anchor":     {"type": "string", "description": "定位/修复锚点：节标题（scrollToAnchor 可匹配文本）"},
    "excerpt":    {"type": "string", "description": "问题原文片段（≤120 字）"},
    "problem":    {"type": "string"},
    "suggestion": {"type": "string"},
    "fix_op":     {"description": "可选 DocOperation；v1 仅 {op:'replace_section', anchor, content}（模型给出整节修正文时才有）"}
  }
}
```

**NDJSON 事件流**（`/ai/review`，同 transform 无 SSE 前缀）：
`{type:"section_start", index, total, title}` → （逐条）`{type:"finding", index, finding:<契约对象>}` →（节失败时）`{type:"section_error", index, message}` → 收官 `{type:"done", total, failed:[], skipped:[], summary:{error:n, warn:n, info:n}}`。
tolerance：单节 finding 解析失败/模型超时 = section_error 继续后续节（同 transform I1 先例）。

## Chunk 1 — 后端审查管线（backend only + 契约文件）

**Files:**
- Create: `contracts/docmgr_findings.v1.json`
- Modify: `backend/app/extensions/docmgr/ai_transform.py`（同文件加路由——复用 split_sections/_scan_terminology/_ndjson/_doc_perm/MAX 守卫，分文件反而引重复）
- Create: `backend/tests/test_docmgr_ai_review.py`（先红后绿，克隆 test_docmgr_ai_transform.py 的 fake-model + dependency_overrides + TestClient stream 手法）

**行为规格：**
1. `AIReviewRequest(BaseModel)`: `thread_id, rel_path, review_type, instruction?, model_name?, content`；`review_type ∉ {consistency, numbering, units, custom}` → 400；MAX_CONTENT_CHARS / MAX_SECTIONS 守卫同 transform。
2. **consistency 两遍法**：第一遍 = 复用 `_scan_terminology`（术语表已就绪）；第二遍逐节携 `_terminology_block` 审「变体残留」。
3. **numbering 两遍法**：第一遍新 prompt `_NUMBERING_SCAN_PROMPT` 全文提编号清单（标题+编号序列，JSON）；第二遍逐节携清单审连续性/跳号/重复。
4. **units**：单遍逐节（spec 未标两遍法）；**custom**：`instruction` 透传逐节。二者共享 `_REVIEW_SECTION_PROMPT`（规则段不同）。
5. 逐节：`section_start` → 模型返回 JSON 数组（复用 `_scan_terminology` 的 regex+json.loads+防御过滤手法）→ 逐条 `finding`（id=`{review_type}-{i}-{n}`，defensive：severity 白名单外降为 warn、缺字段丢弃该条并 log warning）；`fixed_section`（整节修正文，仅 consistency/units 提示可给）非空 → 附 `fix_op:{op:"replace_section", anchor:节标题, content:fixed_section}`。
6. `done.summary` 按 severity 计数；`skipped` 语义同 transform（structured 节跳过审查——表格/代码节不审）。
7. 模型装配：`create_chat_model(name=model_name, thinking_enabled=False, model_overrides={"max_tokens": 8192})` 同 transform。

**测试清单**（先红）：unknown review_type 400；NDJSON 序列 section_start→finding→done；summary 计数正确；consistency 两遍（fake model 按调用序返回 scan 表→节 findings）；单节 JSON 坏输出→section_error 且后续节继续；finding 缺字段被丢弃；custom instruction 进入 prompt 断言；schema 契约冒烟（发出的 finding 键 ⊆ 契约 properties）。
**门**：`cd backend && make lint && PYTHONPATH=. uv run pytest tests/test_docmgr_ai_review.py tests/test_docmgr_ai_transform.py -v` 全绿（老 30 例不回归）。

## Chunk 2 — 前端审查任务区 + 宫格入口 + 加固

**Files:**
- Modify: `frontend/src/extensions/api/index.ts` — `aiReviewStream`（克隆 aiTransformStream 骨架，`/docmgr/ai/review`，事件泛型同法）
- Create: `frontend/src/extensions/docmgr/DocAIReviewArea.tsx` — 审查任务区（自持 reducer，复用导出的 TicketHeader）
- Modify: `frontend/src/extensions/docmgr/DocAITaskArea.tsx` — 仅 `export { TicketHeader }`（:738，纯展示组件，零逻辑改动）
- Modify: `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx` — 空态宫格第二组「深度审查」3 卡（lucide 图标任选：ScanText/ListOrdered/Ruler）；busy 互斥扩展到 review 运行中（宫格与输入禁用、发送钮不冲突）；`startReview(type)` 走同一任务挂载位
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx` — computeHeadings 前导判定加固
- Tests: `frontend/tests/unit/docmgr/review-reducer.test.ts`、`review-area.dom.test.tsx`、`ai-panel.test.ts` 增 media-block 前导例

**DocAIReviewArea 规格：**
1. **reducer actions**：`start`（running=true, total=null）/ `section_start`（记 total 分母，`Math.max` 同 transform 教训）/ `finding`（append 到该节桶）/ `section_error`（节进 failed）/ `done`（running=false+summary+total 同取 max）/ `dismiss`（id 移出展示，仅内存）/ `restore`（dismiss 可撤销，同 DiffCard 恢复思路）/ `reset`。
2. **TicketHeader 复用**：任务名=审查类型中文（术语一致性审查…）、pill 执行中/已完成、进度=已审节/total、计划行三态同工单（✓已审 n 节 / ●正在审 §title / ○待查看 findings n 条——第三态换算成条数）。
3. **FindingsCard 列表**（替代 diff 卡位）：按 severity 分组（error 红/warn 琥珀/info 灰，组头计数 pill）；条目行 = excerpt（等宽、截断省略）+ problem + suggestion；操作 [定位][修复][忽略]：
   - 定位 = `editorRef.current?.scrollToAnchor(finding.anchor)`（找节标题块滚动+高亮，找不回 = 按钮禁用态）
   - 修复 = 有 `fix_op` 才显示 → `editor.applyOperations([finding.fix_op])` 原样复用（同 proposal 卡应用路径）；应用后该条翻「已修复」态
   - 忽略 = 仅本会话内存生效（契约注明不做记忆）
4. **全部修复栏**：`接受全部` 同位——开始前 `ed.snapshotBlocks()`（DocAITaskArea:294 同法）→ 顺序 apply 全部带 fix_op 的 findings → 完成后 `撤销整批` = `restoreBlocks`；脏检查（编辑器已手动改动）沿用 batch bar 既有提示文案模式。
5. 审查运行中与改写任务互斥：`DocAIAgentPanel` busy 状态统一（同三态互斥既有锁）。

**computeHeadings 加固**：前导判定循环里，无 `content` 数组的块（图片等媒体块）视同「含文本非标题块」置 preamble=1（现只看 `text` 非空）；测试：`[{image}, {heading}]` 文档首节 section=1（修复前=0 与后端 split_sections 1 桶偏差）。
**门**：`cd frontend && pnpm test tests/unit/docmgr/` 全绿（164+ 新例）、`pnpm typecheck` 9→9、改动文件 eslint/prettier 清零。
**收尾**：`docker compose -p eai-docker restart frontend` 后浏览器走查——宫格「术语一致性审查」→ 流式 findings 卡 → 定位滚动 → 单条修复 → 全部修复+撤销 → done summary 计数。

## 明确不做（沿 spec §8）

review:custom UI 入口、sections 部分审查、findings 跨会话记忆、fix_op 失效预检测、panel v2 挂账五件套（最近操作/@pills/思考折叠/建议chips/👍👎）。

## 提交纪律

按 Chunk 分域提交，绝不 `git add -A`；`contracts/` 与 `docs/superpowers/`（gitignored）用 `git add -f`；后端文件加 EAI-CUSTOM 注释（M1 同规格：docstring 声明+包裹+bug 编号）。
