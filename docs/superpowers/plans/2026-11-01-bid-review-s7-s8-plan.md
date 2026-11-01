# s7 响应偏离表 + s8 版本差异 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, 本会话既有节奏). Steps use checkbox syntax.

**Goal:** 按原型落地 s7 偏离表与 s8 版本差异两整屏 + prev_task_id 版本链入口(spec `2026-11-01-bid-review-s7-s8-deviation-diff-design.md`)。

**Architecture:** 偏离=抽取期 LLM 对照字段(B4 同构零新表);diff=既有端点扩展 fields/rules 两键;入口=对话框下拉 + ?prev= 预填。

**Tech Stack:** FastAPI+SQLAlchemy(async)+pytest / Next.js+TanStack Query+rstest。

---

### Task 1: 后端 B9a — deviation.items 抽取字段

- [ ] 先红:改 `backend/tests/test_bid_review_extract.py` 加契约测试(deviation.items 在 collect_field_paths、TYPE_CONTRACTS 含五值 kind 说明)
- [ ] `engine/extract.py`:FIELD_DICTIONARY += `"deviation.items"`(B9 注);`FIELD_TYPE_CONTRACTS["deviation.items"]` = spec §1.1 契约串
- [ ] `engine/labels.py`: `"deviation.items": "响应偏离表"`
- [ ] 绿:`cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py -v`;commit

### Task 2: 后端 B9b — GET /tasks/{id}/deviations

- [ ] 先红:`backend/tests/test_bid_review_deviations.py`(B4 测试文件同构):纯 counts 函数 + 端点(真投影 counts/items、跨行按名去重、零投影、幽灵 404)
- [ ] `routers.py`:纯函数 `deviation_counts(items)`(tender_items=kind≠extra / bid_items=kind≠missing / negative/missing/extra 直计)+ 端点(baselines 行 fields 取 deviation.items,seen_names 去重,空→零投影)
- [ ] 绿 + 全量回归 `uv run pytest tests/test_bid_review*.py -v`;commit

### Task 3: 后端 B10a — create_task prev_task_id

- [ ] 先红:`backend/tests/test_bid_review_retry.py` 同构新文件或扩 `test_bid_review_create.py`:prev=done 任务 200 且落库;prev 不存在→404;prev=自身→422;空串→None
- [ ] `routers.create_task`:Form 参数 `prev_task_id: str = Form("")`;**建任务前**校验(get_task→404「基准任务不存在」;strip==task 将生成 id 不可能,以参数≠"" 且 == 自身不可能——校验 prev 任务 status=="done" 非必需,quick 场景允许任意存在任务);`crud.create_task` 透传(查签名,缺则加 kwarg)
- [ ] 绿;commit

### Task 4: 后端 B10b — diff 端点扩展 fields+rules

- [ ] 先红:扩 `backend/tests/test_bid_review_diff.py`:两任务基线 fields 不同→`fields` 列变更对(path/label/prev/cur);相同→空;issues 按 rule_id 归并→`rules` 行(present/severity 最严;false_positive 剔除;变化排前)
- [ ] `routers.diff_task`:响应 += `"fields"`(list_baselines 两任务首行 payload.fields,JSON-safe 比对,label=FIELD_LABELS.get) += `"rules"`(rule_id 并集,`_rule_verdict(issues)`=present+最严 sev)
- [ ] 绿 + 全量;commit

### Task 5: 前端 api/hooks — 类型与请求

- [ ] `api.ts`:`DeviationItem`/`DeviationOut`;`fetchDeviations`;`BidDiffOut` += `fields?: DiffField[]; rules?: DiffRule[]`;`createTask` 增 `prevTaskId?: string | null`(非空才 form.set)
- [ ] `hooks.ts`:`useBidDeviations(taskId)`(key deviations);typecheck 门 0;commit

### Task 6: 前端 DeviationsView + 路由 + 导航

- [ ] 先红:`frontend/tests/unit/extensions/bid-review-deviations.dom.test.tsx`(mock fetcher):pill 映射五色/计数五格/默认滤 match+toggle/零投影空态/证据 chip 开 DocLocateModal
- [ ] `components/DeviationsView.tsx`(原型 s7 逐元素)+ `app/bid-review/deviations/page.tsx`(Suspense 包裹)
- [ ] `layout.tsx` navItems += 偏离表(Table2 图标,group 0,taskPage:"results",pageId bid:page:results);更新 `tests/unit/app/bid-review-layout.dom.test.tsx` 契约门
- [ ] 绿 + typecheck + format;commit

### Task 7: 前端 DiffView + 路由 + 导航

- [ ] 先红:`bid-review-diff.dom.test.tsx`:双卡渲染(dif-del/dif-add/rule pill)/无 prev 空态/hd-sub 变更影响数
- [ ] `components/DiffView.tsx`(原型 s8 逐元素)+ `app/bid-review/diff/page.tsx`;navItems += 版本差异(GitCompare)
- [ ] 绿;commit

### Task 8: 前端版本链入口

- [ ] 先红:TasksView dom 测试加——对话框「对比基准任务」下拉选 done 任务→FormData.prev_task_id;`?prev=` 打开页→对话框自动开且预填
- [ ] TasksView:dialog state 增 prevTask(useBidTasks done 项做 options);useEffect 读 searchParams prev 预填+开框;ResultsView 页头加「换版重审」按钮(push `/bid-review?prev=`);B7 卡加「查看整屏」链接(/diff?task_id=&prev=)
- [ ] 绿 + 全套 rstest + typecheck;commit

### Task 9: 收尾

- [ ] spec+plan `git add -f` 入库(与 Task 1 同 commit);gateway 重启;`.wolf/memory.md`+anatomy+buglog;自动记忆更新
