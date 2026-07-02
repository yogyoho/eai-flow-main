# 合同价格分析 — 前端对齐后端重构方案 (Approach B)

> **状态**:待评审 → 待实施
> **日期**:2026-06-30
> **来源**:/plan-ceo-review(CEO 评审 + 差距审计)
> **关联**:`docs/superpowers/specs/2026-06-26-contract-price-analysis-design-v2.md`(模块设计 v2)、`frontend/src/extensions/contract-price/`、`backend/app/extensions/contract_price/`
> **模式**:SELECTIVE EXPANSION(基线保留 + 补齐前端接线 + 少量后端端点)
> **约束**:**不动核心代码**(全在扩展层;遵守 `no-core-code-changes`);提交到 `main-dev-fork`

---

## 0. 背景:为什么要这次重构

模块后端(Phase 2 已完成,Phase 3 进行中)能力已完整,但**前端只暴露了一部分**,导致:

- 后端实现的端点/字段无人调用(聚类合并、明细审计字段、各类筛选器)。
- 聚类审核("聚类审核"页)只能确认,**合并/移动到指定组/拒绝/分类** 全缺或为 hack——这是人工核验闭环的核心,却残缺。
- 部分交互用脆弱实现(Excel `window.open`、move-to-first-other-cluster hack)。
- 两个真正卡体验的能力(单文档重解析、孤儿 run 清理)**后端也没有**,需补。

本次重构目标:**前端对齐后端** + 补两个卡点后端端点,让人工核验闭环完整可用。不重设计架构(当前单合同规模,参考 cerebrum Phase 2 T6「按真实规模精简」决策)。

---

## 1. 差距矩阵(审计结论)

| # | 能力 | 后端 | 前端 | 类型 |
|---|------|:---:|:---:|------|
| G1 | 聚类合并(合并同义组) | ✓ `POST /clusters/merge` | ✗ 无调用方 | 前端接线 |
| G2 | 移动 item 到**指定**目标组 | ✓ `POST /items/{id}/move` | ⚠ hack(移到任意第一个其他组) | 前端接线 |
| G3 | 拒绝聚类(status=rejected) | ✗ 无端点 | ✗ 无 UI | **后端新增 + 前端** |
| G4 | item 明细字段 `tech_params`/`quantity`/`unit`/`price_untaxed` | ✓ 存储+返回 | ✗ 从不展示 | 前端接线 |
| G5 | items 按合同号筛选 | ✓ query param | ✗ 无 UI | 前端接线 |
| G6 | items 按 `run_id` 筛选 | ✓ query param | ⚠ 仅分组 | 前端接线 |
| G7 | documents 按 `parse_status` 筛选 | ✓ query param | ✗ 无 UI | 前端接线 |
| G8 | runs 按 `run_status` 筛选 | ✓ query param | ✗ 无 UI | 前端接线 |
| G9 | 专用状态轮询端点 | ✓ `GET /pipeline/runs/{id}/status` | ✗ 用 list refetch | 前端接线(低优) |
| G10 | 聚类详情内溯源 | ✓ preview 端点 | ✗ 仅 ItemsView | 前端接线 |
| G11 | 编辑聚类 category | ✗ 无端点(category 字段存在) | ✗ 固定"未分类" | **后端新增 + 前端** |
| G12 | Excel 下载 | ✓ `GET /runs/{id}/excel` | ⚠ `window.open` | 前端接线 |
| B1 | 单文档重解析 | ✗ 无 | ✗ | **后端新增** |
| B2 | 孤儿 run 清理 | ✗ 无 | ✗ | **后端新增** |

**已对齐(不动)**:Dashboard 图表、documents 确认/确认全部/上传/删除/项目字段内联编辑、items 分页/删除/分组/溯源、cluster confirm、settings 全字段、tasks 进度轮询。

---

## 2. 实施分阶段

按价值/依赖排序。每阶段独立可交付、可重启容器验证。

### Phase R1 — 聚类整理闭环(最高价值)

**目标**:让"聚类审核"页从「只能确认」变成完整的人工整理工作台。这是这次重构的杠杆点——后端聚类能力已就绪,前端缺 UI。

**改动**:

| 项 | 文件 | 内容 |
|----|------|------|
| G1 合并 | `hooks.ts` 加 `useMergeClusters`;`ClustersView.tsx` | 左侧列表加多选 checkbox +「合并选中」按钮 → 弹窗输入代表性名称/类别 → 调 `mergeClusters`。`api.ts:111` 已有 `mergeClusters`,只缺 hook+UI |
| G2 移动到指定组 | `ClustersView.tsx` | 删除 `:203-213` 的「移到第一个其他组」hack;行操作「移出」改为「移动到…」→ 弹组选择下拉(其他聚类 representative_name)→ `moveItem(item.id, target)` |
| G3 拒绝 | 后端 `routers.py`+`crud.py`+`schemas.py`;前端 hook+UI | 新增 `POST /clusters/{id}/reject`(`crud.reject_cluster` 设 status='rejected',version+1);ClustersView 详情页「拒绝」按钮(与「确认分组」并列) |
| G11 类别编辑 | 后端 `PATCH /clusters/{id}`;前端 | 新增 `PATCH /clusters/{id}`(可改 category/representative_name);详情页类别改可编辑 inline input |

**验证**:多选 2 个聚类 → 合并 → 新组出现原两组 items;item 移动到指定组 → 原组少一条;拒绝组 → status=rejected;改类别 → 列表/详情同步。

**风险**:合并/移动改 cluster_id,会触发 `["cpa"]` 全量 invalidate,确认 invalidate 范围不过大(当前是全模块,可接受 dev 规模)。

---

### Phase R2 — 明细完整化

**目标**:ItemsView/聚类详情展示后端已存的全字段,把审计字段(`price_untaxed`)和规格参数暴露出来。

**改动**:

| 项 | 文件 | 内容 |
|----|------|------|
| G4 明细字段 | `ItemsView.tsx` | 行可展开(点击行 → 展开子行)显示 `quantity`/`unit`/`price_untaxed`/`tech_params`(key-value)。单价列保持含税;展开区显示不含税(审计)+ 技术参数 |
| G4 聚类详情 | `ClustersView.tsx` | 详情表加「规格」「单位」「工程量」列(或同样展开) |
| G10 聚类内溯源 | `ClustersView.tsx` | 详情表每行加「溯源」按钮(复用 `TracebackDrawer`),用 item 的 source_page/source_bbox |
| G5 按合同筛选 | `ItemsView.tsx` | 筛选区加「来源合同」下拉(从 documents 拉 contract_no 去重)或输入框 → `listItems({source_contract_no})` |

**验证**:展开 item 行看到工程量/单位/不含税单价/tech_params;聚类详情点溯源 → 红框预览;按合同筛选 → 只剩该合同 items。

---

### Phase R3 — 筛选/下载收尾(低优先)

**改动**:

| 项 | 文件 | 内容 |
|----|------|------|
| G6 按 run 筛选 | `ItemsView.tsx` | 任务分组头部加「仅看本任务」(其实分组已是,可选加 URL query 持久化) |
| G7 docs 状态筛选 | `ContractsView.tsx` | 顶部加 parse_status segmented 过滤(全部/已解析/待核验/失败)→ `listDocuments({parse_status})` |
| G8 runs 状态筛选 | `TasksView.tsx` | 顶部加 run_status segmented(全部/运行中/完成/失败)→ `listRuns({run_status})` |
| G9 状态轮询 | `TasksView.tsx` | (可选)running 时改用 `pipelineStatus(run_id)` 单点轮询代替 list refetch。**低优**,list 轮询当前能用 |
| G12 Excel 下载 | `TasksView.tsx` | `window.open` 改 `fetch(url,{credentials:'include'})` → blob → `<a download>`(与 TracebackDrawer 同模式,防 auth 失效) |

**验证**:各筛选器生效;Excel 下载在 cookie 过期场景仍工作。

---

### Phase R4 — 后端补端点(B1/B2)

**B1 单文档重解析**:
- 现状:parse 阶段按 SHA-256 增量,合同内容未变不重 OCR(cerebrum Phase 1a)。要重解析单文档须先删 `cpa_documents` 行(scan 才会重新摄入),但会换新 doc_id。
- **方案**:skill cli 加 `--force-key <minio_key>` 标志,对指定 key 强制重 OCR(忽略 hash 缓存);后端加 `POST /documents/{id}/reparse` → 用 doc.storage_uri 解析出 key → 起一个 `run_pipeline_subprocess(..., force_key=key)` 背景 run。
- 改动:`skills/.../scripts/cli.py`(scan_changed 支持 force_key)、`backend/.../routers.py`+`service.py`(reparse 端点)。
- **懒办法(ponytail)**:若 force_key 改动大,后端 reparse 端点直接「删该 doc 的 items + 删 doc 行 + 触发 parse」,接受 doc_id 变更(前端 invalidate 后自然刷新)。dev 规模可接受。先用懒办法,force_key 留规模化时。

**B2 孤儿 run 清理**:
- 现状:gateway 重启会留下 status='running' 的孤儿行,阻塞同 phase 重触发(cerebrum Phase 2 T6 残留)。需手动 SQL 清。
- **方案**:后端加 `POST /runs/cleanup-stale` → 把所有 `status='running'` 且 `started_at < now()-1h` 的标 'failed'(error='orphaned by restart')。
- **懒办法**:在 `trigger_pipeline`/`trigger_cluster` 入口的 `has_running_run` 检查前,先自动清>1h 的 running run(启动时自愈),不必单独端点。优先此法(零新端点)。

---

## 3. 文件改动清单

**前端**(全在 `frontend/src/extensions/contract-price/`):
- `hooks.ts`:加 `useMergeClusters`、`useRejectCluster`、`useUpdateCluster`、`useReparseDocument`(R4)
- `api.ts`:加 `rejectCluster`、`updateCluster`(PATCH)、`reparseDocument`;`excelDownload`(fetch+blob 包装)
- `types.ts`:`CpaCluster` 已有 category,无需改
- `components/ClustersView.tsx`:R1 主战场(合并/移动目标/拒绝/类别)+ R2(明细列/溯源)
- `components/ItemsView.tsx`:R2(行展开 + 合同筛选)+ R3(run 筛选)
- `components/ContractsView.tsx`:R3(parse_status 筛选)+ R4(重解析按钮)
- `components/TasksView.tsx`:R3(run_status 筛选 + Excel blob 下载)

**后端**(全在 `backend/app/extensions/contract_price/`):
- `routers.py`:加 `POST /clusters/{id}/reject`、`PATCH /clusters/{id}`、`POST /documents/{id}/reparse`(可选)
- `crud.py`:加 `reject_cluster`、`update_cluster`、`cleanup_stale_runs`(或并入 trigger)
- `schemas.py`:加 `ClusterUpdate`(category/representative_name)
- (R4 B1 懒办法)无需改 cli

**不改**:models.py(无新列)、database.py(无迁移)、核心 harness/app。

---

## 4. 测试策略

- **后端**:每个新端点加 `tests/test_contract_price_*.py` 单测(mock session,参考现有 `test_contract_price_model_parity.py` 模式)。reject/update_cluster 测状态转换 + version 自增。
- **前端**:`tests/unit/extensions/contract-price/`(已有 `api.test.ts`)加 hook/api 单测;合并/移动/拒绝的关键交互加 Vitest。
- **端到端验证**(Docker):每 Phase 重启 frontend/gateway 后,人工跑:多合同合并 → 移动 → 拒绝 → 类别 → 明细展开 → 溯源 → 筛选 → 下载。
- **回归**:跑 `make test` + `pnpm typecheck` 确认 `test_contract_price_model_parity` 仍过(两套 models 同步)。

---

## 5. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 合并/移动改 cluster_id 导致统计漂移 | cluster 阶段统计从 DB 实时算(`compute_stats`),移动后下次 cluster run 重算;合并即时重算 item_count |
| B1 懒办法换 doc_id 让旧 run_id 引用悬空 | dev 规模可接受;items 仍按 document_id FK 关联,doc 删则级联 |
| 聚类整理 UI 复杂度上升 | 多选合并用确认弹窗(防误操作);移动用下拉;拒绝需二次确认 |
| 全在 `main-dev-fork` 分支 | 按 `main-dev-fork-branch` 约定,不碰 main |

回滚:每 Phase 独立提交,任一 Phase 出问题 `git revert` 该 commit,不影响其他。

---

## 6. 不在本次范围(显式延后)

- **Approach C 重设计**(引导式流水线 UI / 任务历史单一事实源):当前单合同规模超配,cerebrum 多处决策已选精简。留多合同规模化时。
- **presigned 直传 + arq 队列**(Phase 3 G 规模化):>50 份合同时触发。
- **cell bbox 列对齐**(Phase 3 A):OCR 列错位修复,与本次前端对齐无关。
- **跨合同基准**(Phase 3 E):需多合同数据。

这些写进 TODOS,不在本次。
