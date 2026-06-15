# 合同分项价格分析 — 管理页面 API 服务实现计划 (Plan 2/3)

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax. Implement directly with TDD.

**Goal:** 构建管理页面的 FastAPI 后端服务,提供 6 大功能区 + 流水线触发的 REST API,并补全 Plan 1 留作 best-effort 骨架的 `cpa_` 表持久化逻辑。

**Architecture:** 自包含 FastAPI 服务,位于 `skills/custom/contract-price-analysis/scripts/server/`,复用 Plan 1 的 `scripts/db.py` 引擎与 `cpa_` 模型,与主后端扩展解耦。CORS 开放给前端。流水线触发复用 Plan 1 的 `cli.run_pipeline`。

**Tech Stack:** FastAPI、uvicorn、SQLAlchemy[asyncio]、复用 Plan 1 的 models/db/cli

---

## 文件结构

```
skills/custom/contract-price-analysis/scripts/server/
├── __init__.py
├── app.py              # FastAPI 应用 + CORS + 路由注册
├── deps.py             # 异步 DB 会话依赖
├── schemas.py          # Pydantic 请求/响应模型
├── crud.py             # cpa_ 表 CRUD(补全 Plan 1 骨架)
├── main.py             # uvicorn 入口
└── routers/
    ├── __init__.py
    ├── documents.py    # 功能区1: 合同缓存清单
    ├── clusters.py     # 功能区2: 聚类审核 ⭐
    ├── items.py        # 功能区3: 分项明细
    ├── tasks.py        # 功能区4: 任务历史
    ├── config.py       # 功能区5: 配置管理
    ├── dashboard.py    # 功能区6: 统计看板
    └── pipeline.py     # 流水线触发
```

---

## Task 1: FastAPI 应用脚手架 + DB 依赖

**Files:** `scripts/server/{__init__.py,app.py,deps.py,main.py}`, `tests/server/test_app.py`

- [ ] 写测试:GET `/api/cpa/health` 返回 200 `{"status":"ok"}`
- [ ] 实现 `app.py`(FastAPI + CORS allow-all + health 路由)、`deps.py`(`get_session` async generator)、`main.py`(uvicorn 入口)
- [ ] 测试通过 + 提交

## Task 2: Pydantic schemas + CRUD 基础

**Files:** `scripts/server/{schemas.py,crud.py}`

- [ ] `schemas.py`: DocumentOut/ItemOut/ClusterOut/RunOut/StatsOut + 分页响应泛型
- [ ] `crud.py`: `list_documents(session, keyword, status, skip, limit)`、`get_cluster_with_items`、`list_runs` 等,DB 不可达时各函数 raise 可被路由捕获
- [ ] 补全 Plan 1 `cli._persist`:把 document/item/cluster/run 持久化逻辑从 best-effort 骨架升级为完整实现(仍 try/except 包裹,但成功时正确建联)
- [ ] 提交

## Task 3: 功能区1 — 合同缓存清单

**Files:** `scripts/server/routers/documents.py`

- [ ] `GET /api/cpa/documents` — 列表 + keyword/parse_status 筛选 + 分页(skip/limit/total)
- [ ] `DELETE /api/cpa/documents/{id}` — 删除缓存合同(级联其 items)
- [ ] 测试(mock session) + 提交

## Task 4: 功能区2 — 聚类审核 ⭐

**Files:** `scripts/server/routers/clusters.py`

- [ ] `GET /api/cpa/clusters` — 列表(status/category 筛选,返回 stats + item_count)
- [ ] `GET /api/cpa/clusters/{id}` — 单组详情(含 items)
- [ ] `POST /api/cpa/clusters/{id}/confirm` — 确认分组(status→confirmed,乐观锁 version)
- [ ] `POST /api/cpa/clusters/merge` — 合并多组(body: cluster_ids[])→ 新代表名
- [ ] `POST /api/cpa/items/{id}/move` — 移动货物到另一组(body: target_cluster_id)
- [ ] 测试 + 提交

## Task 5: 功能区3 — 分项明细

**Files:** `scripts/server/routers/items.py`

- [ ] `GET /api/cpa/items` — 列表(goods_name/contract_no/cluster_id 筛选 + 分页)
- [ ] `PATCH /api/cpa/items/{id}` — 修正单价/技术参数(记录修正原因)
- [ ] 测试 + 提交

## Task 6: 功能区4 — 任务历史

**Files:** `scripts/server/routers/tasks.py`

- [ ] `GET /api/cpa/runs` — 运行历史列表(status 筛选 + 分页)
- [ ] `GET /api/cpa/runs/{id}/excel` — 下载该次产出的 Excel(FileResponse)
- [ ] 测试 + 提交

## Task 7: 功能区5 — 配置管理

**Files:** `scripts/server/routers/config.py`

- [ ] `GET /api/cpa/config` — 返回当前聚类参数(eps/min_samples/parse_mode)+ 定时开关
- [ ] `PUT /api/cpa/config` — 更新参数(持久化到 `cpa_run_history` 旁的 `cpa_config` 表,或简单 JSON 文件)
- [ ] 测试 + 提交

## Task 8: 功能区6 — 统计看板

**Files:** `scripts/server/routers/dashboard.py`

- [ ] `GET /api/cpa/dashboard` — 聚合:合同数、货物数、聚类组数、待审核组数、价格区间分布、最近任务
- [ ] 测试 + 提交

## Task 9: 流水线触发

**Files:** `scripts/server/routers/pipeline.py`

- [ ] `POST /api/cpa/pipeline/run` — body: {mode, trigger}; 后台任务调 `cli.run_pipeline`,立即返回 run_id;复用 `cpa_run_history` 记录
- [ ] `GET /api/cpa/pipeline/runs/{id}/status` — 查询运行状态
- [ ] 测试 + 提交

## Task 10: 集成 + OpenAPI + 文档

- [ ] 注册全部路由到 `app.py`
- [ ] `/api/cpa/openapi.json` 可访问(自动)
- [ ] 更新 SKILL.md/README 记录 API 端点与服务启动方式
- [ ] 全量测试通过 + 提交

---

## Self-Review

- 6 功能区 + 流水线触发全覆盖 ✅
- 复用 Plan 1 models/db/cli,不重复实现 ✅
- 补全 Plan 1 `_persist` best-effort 骨架 ✅
- 与主后端扩展解耦(自包含 FastAPI)✅
