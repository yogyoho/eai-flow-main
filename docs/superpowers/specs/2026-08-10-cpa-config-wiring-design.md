# 合同价格分析「设置」配置项接通 — 技术方案

> 状态：**待实现（按需排期）**。本文件是设计与落点清单，不是已实施的变更。
> 日期：2026-08-10｜关联审计：bug-1158（`.wolf/buglog.json`）、cerebrum Key Learning（同日）。

## 1. 背景（Context）

2026-08-10 审计确认：合同价格分析「设置」tab 的 6 个配置项里，**只有 `price_table_keywords` 真正进入分析管线**；`parse_mode` / `cluster_eps` / `cluster_min_samples` / `scheduled_enabled` / `schedule_cron` 是"存盘 + GET/PUT 回显"的死配置——存得进、读得出，但管线运行时从不读取。真正控制聚类与异常判定质量的旋钮（DBSCAN `eps`/`min_samples`、IQR 异常倍数）要么硬编码、要么即便有 UI 入口也没接到算法。

价值评估结论：对"价格分析模型"（聚类 + 异常检测 + 抽取）真正有价值的是三个数值旋钮——`cluster_eps`、`cluster_min_samples`、以及目前连 UI 入口都没有的 **IQR 异常倍数**。本方案把这三个接通，让模型从"全客户一套固定灵敏度"变为可按客户/数据自适应。

- `price_table_keywords`：维持现状（已生效）。
- `parse_mode` / 定时任务 / OCR·启发式参数：按"暂缓 / 不动"处理（见 §7）。

## 2. 关键架构事实（决定方案复杂度）

**config.json 已经是一条打通的通道。** `price_table_keywords` 的生效路径是：

```
UI → PUT /api/extensions/contract-price/config
   → crud.save_config() 写 backend/app/extensions/contract_price/config.json
   → skill 子进程 cli.py 经 CPA_CONFIG_JSON env（或硬编码路径）直接读该文件
   → 传入 classify()
```

**结论：接通 `cluster_eps` / `cluster_min_samples` / IQR 倍数不需要改 `service.run_pipeline_subprocess` 的 CLI 拼装，也不需要新增 env 或写额外配置文件**——只需让 `cli.py` 把已加载 config 里的这几个值，转发给聚类与异常计算函数即可。审计里"service.py 不传任何配置"的结论对这几个数值字段是**红鲱鱼**：它们走 config.json 文件通道，不走 CLI 参数。`service.py` 的 `--mode` 丢弃 bug 只影响 `parse_mode`（§7.1）。

## 3. 目标 / 非目标

**目标（本方案实现）**
- **T1** `cluster_eps`、`cluster_min_samples` 真正生效：`cli.py` 读取并透传给 DBSCAN。
- **T2** 新增 `outlier_iqr_multiplier` 配置项（默认 1.5），UI + schema + 管线全链路生效，控制 ⚠️ 异常敏感度。
- **T3** 所有数值配置项加 Pydantic 校验 + 前端强制范围；`parse_mode` 收敛为枚举。
- **T4** 配套单测（TDD）。

**非目标（明确不做 / 暂缓，见 §7）**
- 接通 `parse_mode`（需先验证抽取器有无 mode 分流）。
- 实现 `scheduled_enabled` / `schedule_cron` 定时调度（运营价值，非模型价值）。
- 把 OCR 超时/重试/并发、价格下限、续页容差等启发式搬进 UI（留基础设施/内部层）。

## 4. 设计

### 4.1 后端 schema — `backend/app/extensions/contract_price/schemas.py:108-127`

`ConfigOut` 增加 `outlier_iqr_multiplier`，并给现有数值字段加校验：

```python
parse_mode: Literal["table", "list", "mixed"] = "table"
cluster_eps: float = Field(0.6, ge=0.1, le=1.0)
cluster_min_samples: int = Field(2, ge=1, le=10)
outlier_iqr_multiplier: float = Field(1.5, ge=0.5, le=3.0)   # 新增；越小越敏感
scheduled_enabled: bool = False
schedule_cron: Optional[str] = None
price_table_keywords: list[str] = [...]
```

可选：`model_config = ConfigDict(extra="forbid")` —— 拒绝未知键，避免拼错被静默丢弃（当前 typo 键会被吞）。前端 PUT body 只发这 6（接通后 7）个键，启用安全（实现时 grep 前端确认一次）。

`ConfigUpdate(ConfigOut): pass` 不变（GET/PUT 同形）。`crud.load_config()` / `save_config()`（`crud.py:835-852`）无需改——`ConfigOut(**json)` 与 `model_dump()` 自动覆盖新字段；旧 config.json 无 `outlier_iqr_multiplier` 键时走默认 1.5。

### 4.2 管线读取与透传 — `skills/public/contract-price-analysis/scripts/`

- **入口加载**：在 `cli.py` 的 run 入口（`run_cluster` / `run_parse` 启动处）一次性加载**完整** config（复用现有 `CPA_CONFIG_JSON` 读取逻辑，目前只取 keywords，扩展为取整个对象），得到 `cfg.cluster_eps` / `cfg.cluster_min_samples` / `cfg.outlier_iqr_multiplier`。读取点参考现有 `_load_price_keywords`（`cli.py:72-78`）。
- **聚类透传**：`cli.py:866` `cluster_items(samples)` → `cluster_items(samples, eps=cfg.cluster_eps, min_samples=cfg.cluster_min_samples)`。
- **DBSCAN 签名**：`scripts/clustering/engine.py:65` 的 `cluster_items` 加 `eps` / `min_samples` 形参，保留当前值为默认，保证其他调用点不破。
- **异常倍数透传**：把 `cfg.outlier_iqr_multiplier` 传到调 IQR 篱笆处；`scripts/stats.py:42-43` 的 fence 函数加 `multiplier` 形参（默认 1.5）。

> `is_outlier` 仍是聚类时的快照（cerebrum bug-1154 已退回、保持原状）；接通倍数后**下次聚类运行**即按新倍数重算全部成员。

### 4.3 前端 — `frontend/src/extensions/contract-price/`

- **`types.ts:108-115`** `CpaConfig` 加 `outlier_iqr_multiplier: number`。
- **`components/SettingsView.tsx`** 在聚类参数区加一个 number 输入「异常敏感度（IQR 倍数）」：`step=0.1, min=0.5, max=3.0`，旁附辅助说明「越小越敏感（抓更多疑似异常）；1.5 = 标准箱线图篱笆」。
- `cluster_eps` / `cluster_min_samples` 已有 UI，保持；确保 HTML `min/max/step` 与后端 `ge/le` 对齐。
- **表单初始化**（`SettingsView.tsx:27-34`）：把 `outlier_iqr_multiplier` 纳入 `form` 初值，保证 PUT 回写不丢字段（当前 init 只拷贝固定键集合，新增字段必须显式加入，否则会被丢）。
- `api.ts:205-209` `updateConfig` 无需改（整体 PUT CpaConfig）。

### 4.4 `service.py` 的 `--mode` 丢弃 bug（`service.py:49-61`）— 本方案不必修

此 bug 只影响 `parse_mode`（走 CLI `--mode`）。T1/T2 走 config.json 文件通道，与该 bug 无关。修法留到 §7.1 与 `parse_mode` 一起做，避免半接通产生"mode 偶尔生效"的迷惑状态。

## 5. 校验与边界

- Pydantic `ge/le` + `Literal` 在 PUT 时拦截非法值（HTTP 422），前端不再能提交越界数；前端 `min/max` 也作一层体验约束。
- **小簇统计无效性**：`cluster_min_samples=1` 允许，但 n<某阈值时 IQR 无统计意义 → 会产假 ⚠️。`stats.py` 的异常判定需对簇内 ok/corrected 样本数 < 阈值（建议 4）时**跳过异常标记**。该阈值暂硬编码（§9 开放问题）。
- 旧 config.json 兼容：新字段默认值保证无该键的旧文件 `ConfigOut(**json)` 不报错。

## 6. 测试（TDD）— `backend/tests/test_contract_price_extension.py` + 技能侧

- **config 往返**：`outlier_iqr_multiplier` 能存能取；越界值（eps=2.0 / multiplier=5）PUT 返回 422；启用 `extra="forbid"` 后未知键 422。
- **聚类透传**：mock `cluster_items`，断言 `run_cluster` 用 cfg 里的 `eps`/`min_samples` 调用（而非函数默认）。
- **异常倍数**：构造一组单价，分别用 multiplier=1.5 / 0.5 跑异常判定，断言 ⚠️ 集合不同（小倍数更敏感）。
- **小簇跳过**：簇内 < 4 样本不产生异常标记。

## 7. 暂缓项（记录决策，未来按需实现）

### 7.1 `parse_mode`（table / list / mixed）
价值取决于抽取器是否真有按 mode 分流的代码。审计证据（`cli.py:701/734/975` 硬编码 `"ocr"`、`service.py` 丢弃 `--mode`）强烈指向"无 mode 分流"。**实现前必须先确认**：
- 若抽取是 mode 无关的统一路径 → 配置冗余，应从 UI 删掉该项；
- 若需 mode 分流 → 是功能开发（不同版式不同抽取策略），不是配置接通。

若决定接通：(a) `cli.py` 改读 `cfg.parse_mode` 作默认；(b) 修 `service.py:49-61` 把 `--mode` 拼进 cmd；(c) cli 侧 `--mode`（运行时覆盖）优先于 config 默认。

### 7.2 `scheduled_enabled` / `schedule_cron`（定时分析）
零模型价值，纯运营。仅当存在"持续接入新合同 + 夜批量重算"的真实工作流才值得做。实现 = 新建调度器（APScheduler 或复用项目 Temporal）在 gateway 启动时按 `schedule_cron` 触发 `run_pipeline_subprocess(trigger="scheduled")`，`scheduled_enabled` 作总开关。**已知坑**：gateway `--reload` 监视 `.deer-flow/skills_view` 投影会触发重启循环（见 `.wolf/memory.md`），调度器注册要避开 reload 监视路径。决策前先确认有无批量场景。

### 7.3 OCR 超时 / 重试 / 并发、价格下限、续页容差、合价-单价检测、列数值阈值
全部维持现状（env / 硬编码）。它们是基础设施或抽取启发式，进 UI 是过度可配置 = 坏 UX。`CPA_PARSE_CONCURRENCY` 已是 env（默认 4，`cli.py:794`），正确。最多未来给管理员开"高级参数"面板。

## 8. 验证（实现后端到端）

1. 设置 tab 改 `cluster_eps=0.4`、`outlier_iqr_multiplier=1.0` → 保存 → 触发一次聚类运行 → 验证同一批数据下 ⚠️ 集合与默认参数不同（更敏感 → 更多 ⚠️）。可用 `docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "SELECT id,is_outlier FROM cpa_items WHERE cluster_id=..."` 或 UI 核对。
2. PUT 越界值（eps=2.0）→ 422。
3. `make test`（backend）全绿，含新增 T1–T3 用例；前端 `pnpm typecheck`。
4. 回归：`price_table_keywords` 行为不变。

## 9. 开放问题（实现时再定）

- 小簇异常判定的最小样本阈值（建议 4）：硬编码还是再开一个配置项？建议先硬编码，避免 UI 项膨胀。
- `extra="forbid"` 是否启用：实现时 grep 前端 PUT body 确认只发已知键后启用（审计显示前端只发 6 键，预期安全）。
- `outlier_iqr_multiplier` 是否需要 per-cluster 覆盖：暂不需要，全局够用。
