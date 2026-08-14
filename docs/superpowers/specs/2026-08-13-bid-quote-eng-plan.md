# 模块① 智能投标报价分析(bid-quote-analysis)工程方案

- **日期**:2026-08-13
- **来源**:市场部门四模块设计稿 `2026-08-13-market-analysis-modules-design.md` 第 5 节
- **状态**:工程方案(直接开发依据)
- **建序**:4(done)→ **①(本稿)** → ③ → ②
- **形态**:路线 B(data_source 复用),**零自建扩展代码**(不建 extension 包 / 不建 mcp.py / 不建 postgres-ext 业务表 / 不进 gateway/app.py)

---

## 0. 目标(MVP)

Agent 能在对话页回答投标报价类问题并给决策建议:
- "各货物我方 vs 友商的报价对比、自产/外购构成差异"
- "我方整体中标率 / 按金额段中标率"
- "某货物深挖:我方历史报价 vs 友商"
- 建议层:基于"构成对比 + 中标率"给**报价区间建议 + 自产/外购配比建议**(预聚合决策量,不靠 LLM 心算)

完成标准 = data_source + datasets + 技能跑通,Agent 能答 + 能建议。**前端 defer**(可选看板后补)。

---

## 1. 决策(锁定)

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| D1 | 数据源 | **mock 先行,我编贴近真实样例**(用户确认) | 真实投标库未接入,不阻塞 |
| D2 | mock 载体 | **postgres-ext 容器内独立 database `mock_market`** | 隔离干净;不污染 agentflow 业务表;不引入新服务/容器 |
| D3 | dataset 治理 | 本期 `seed_mock_market.py` 脚本直接 INSERT `data_source_datasets`(`default_query` SQL 当代码管,版本化);loader defer | 仅 3 个 dataset,YAGNI;数量增长后(③②)照 `knowledge_factory/seed_loader.py` 建版本化 loader |
| D4 | MCP | 复用 data_source(已注册 `extensions_config.json`),不新建 | 设计稿 R3 |
| D5 | 前端 | defer | MVP = 对话可用 |
| D6 | `database.py` | **不改** | ① seed 集中在 `seed_mock_market.py`,避免动共享 seed_db() |

---

## 2. mock 数据模型(mock_market 库,基于设计稿第 5 节逻辑视图)

### `mock_bid`(投标主表)
| 字段 | 类型 | 说明 |
|---|---|---|
| `bid_id` | TEXT PK | 投标流水号(我方/友商同一项目各一条) |
| `project_name` | TEXT | 项目名 |
| `project_location` | TEXT | 项目地点 |
| `bid_date` | DATE | 投标日期 |
| `bidder_role` | TEXT | `ours`(我方)/ `competitor`(友商) |
| `bidder_name` | TEXT | 投标方名称 |
| `won` | BOOL | 是否中标 |
| `winning_price` | NUMERIC(14,2) | 中标价(我方中标则为我方报价) |

### `mock_bid_item`(投标分项 — 构成核心)
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | SERIAL PK | |
| `bid_id` | TEXT FK→mock_bid | |
| `goods_name` | TEXT | 货物名 |
| `spec` | TEXT | 规格型号 |
| `quantity` | NUMERIC(12,2) | 数量 |
| `unit` | TEXT | 单位 |
| `unit_price` | NUMERIC(14,2) | 含税单价 |
| `self_amount` | NUMERIC(14,2) | **自产部分金额** |
| `outsourced_amount` | NUMERIC(14,2) | **外购部分金额** |
| `total_amount` | NUMERIC(14,2) | 分项合计(=self+outsourced,可冗余校验) |

### 样例分布(我编,标"待真实校准")
- 6 个投标项目;每项目我方 + 友商各 1 条 `mock_bid`(共 12 条)
- 每 bid 4-6 个分项(共 ~60 条 item),自产/外购构成按货物类型合理分布(核心设备自产高、辅材外购高)
- 我方中标率 ~33%(12 投 4 中),金额段覆盖 <100w / 100-500w / 500-2000w / ≥2000w
- 友商报价整体略低 5-15%(制造报价竞争对比)

---

## 3. datasets(存 extensions 库 `data_source_datasets` 表,source=`bid-quote`)

均 `SELECT` 开头,过 data_source `assert_readonly_select` 只读守卫(自动 LIMIT 200)。

### `bid_summary`
投标数 / 我方中标率 / 友商中标率 / 均价 / 时间范围。

### `composition_compare_by_goods`(**①核心价值**)
各货物 **我方自产%/外购% vs 友商自产%/外购%** + 双方均价对比。

### `win_rate_by_segment`
按金额段(<100w / 100-500w / 500-2000w / ≥2000w)我方中标率。

完整 SQL 见 `seed_mock_market.py` 内常量。

---

## 4. data_source 连接配置

一条连接 `bid-quote`(存 `data_sources` 表):
- `type=database`
- `connection_config={host, port, database:"mock_market", username, password, driver:"postgresql"}`
- 连接由 gateway 容器发起 → host 用 docker 网络内 postgres-ext 服务名

---

## 5. 技能 `skills/public/bid-quote-analysis/SKILL.md`

仿 `contract-price-analysis/SKILL.md` 结构,但工具走 data_source 通用工具(非自建):
- **全局聚合**(中标率/构成对比/分段中标率)→ `query_dataset(source_name="bid-quote", label=<bid_summary|composition_compare_by_goods|win_rate_by_segment>)`
- **按货物/按投标方深挖** → `get_data_source_schema(source_name="bid-quote")` 取字段 → `query_data_source(name="bid-quote", params={"sql": "<只读 SELECT>"})` 写参数化 SQL
- **推理**:基于构成对比 + 中标率给报价区间建议 + 自产/外购配比建议;附样本数;命中无数据项目如实告知"未找到,数据范围有限"
- **边界**:不触发任何写操作;只读分析

注册:`extensions_config.json` 的 `skills` 段加 `"bid-quote-analysis": { "enabled": true }`。

---

## 6. 步骤

| # | 产出 | 文件 | 类型 |
|---|---|---|---|
| T1 | mock_market 建库 + 表 + 样例 seed + data_source 连接 + datasets 元数据 | `backend/scripts/seed_mock_market.py` | 新文件(Python) |
| T2 | 引导技能 | `skills/public/bid-quote-analysis/SKILL.md` | 新文件 |
| T3 | 技能开关 | `extensions_config.json` skills 段 | 改(共享,谨慎) |
| T4 | 执行 + 验证 | 跑 seed 脚本 → 重启 gateway → 对话页测 3 类问题 | 运行时 |
| T5 | 提交 | — | git |

---

## 7. 后续 ③② 复用

- `mock_market` 库扩展:③ 加 `mock_contract`/`mock_invoice`;② 加 `mock_employee`/`mock_attendance`/`mock_trip`
- dataset / 技能各模块各加各的(③ `biz-pipeline-query`;② `sales-personnel-query` + 行级 RBAC 方案)
- ② 接入前必须先定行级权限(RLS 或薄注入层),不定不接

---

## 8. 风险

- **mock 数据真实性**:样例分布是我编,决策建议仅作链路演示;真实接入后需重新校准(设计稿第 12 节已列)
- **Agent 写参数化 SQL 可靠性**:有 schema + 只读守卫(错了安全但可能答错);反复错的查询再补薄领域工具(YAGNI,先观察)
- **docker 网络服务名**:data_source 连接的 host 必须是 gateway 容器视角的 postgres-ext 服务名(执行时确认,非 `localhost`)
