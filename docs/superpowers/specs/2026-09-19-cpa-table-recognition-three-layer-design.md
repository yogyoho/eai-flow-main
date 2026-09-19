# 合同价格分析 · 表格识别三层重构设计（几何层 + LLM 兜底 + 规则生态）

日期：2026-09-19 ｜ 前序：2026-09-17-contract-price-seed-rules-design.md（seed-only 重构，已落地）
状态：已获用户确认（本文件为确认稿）

## 0. 前提默认值（已确认）

| 原问题 | 设计默认 |
|---|---|
| 合同量级 | 半年 1000~5000 份新格式；**seed 铺不完是常态**——新格式首份文档也要产出正确值或诚实 needs_review |
| 错误容忍度 | **错提代价 > 漏提**；端到端铁律：算术不自洽的值永不标 `ok`（沿 bug-3400 全链既有结论） |
| 几何层投入 | 投入（本设计主体） |

## 1. 架构总览

```
PDF → OCR 服务(引擎不变)
        │  顺带收割: 表区域内行级 token(text+box+score) → 随表入缓存(新增, §2.1)
        ▼
   ┌─ 病征检测(§2.3) ──无病征──→ 现状管线: seed匹配+提取+仲裁(零改动)
   │      │有病征
   │      ▼
   ├─ L2 几何网格重建(§2) → 重建表
   │      └─ 两版比对(§2.4): 行级算术自洽率高者胜; 平手取 PP-Structure
   │      ▼
   ├─ 仍失败(unmatched / NR>50%) → L3 LLM 列语义标注(§3) → 确定性直取+算术验收门
   ▼
   L1 规则生态运营化 + L4 人工修正回流锚词(§4)
```

铁律：**LLM 只标注列语义，永不生成价格数值**；数值一律由确定性代码按映射直取 + u×q≈t 仲裁验证。

## 2. L2 几何网格重建（治本三类病）

### 2.1 token 捕获与缓存 v2

- token 结构：`{text, box:[x1,y1,x2,y2], score}`，页绝对坐标（与现有 cell_bboxes 同一裁剪偏移逻辑）。
- 捕获点：`ocr_engine._table_region` 内部 per-crop OCR 结果——PP-Structure 表识别前本就运行行级 OCR，**透出即可，运行时近零增量**。
- 缓存：`ocr/{sha}.json` 的 `tables[].tokens` 随 Table 序列化（`to_cache/from_cache` 同步扩展）。内容寻址 sha 不变。
- 旧缓存无 tokens → 几何层跳过（优雅降级=现状），重解析仍默认缓存命中；tokens 仅新 OCR 或 `--re-ocr` 后可用。

### 2.2 聚类算法

1. **行**：token 按 y-center 排序聚带；行高=token 高度中位数，带宽=中位行高×0.6。
2. **列**：行内 token x 边界做断点检测（列间 gap）→ 跨行合并成全局列带；token 按 x-center 落带。
3. **span**：token 框纵向跨 ≥2 行带 → rowspan；横向跨 ≥2 列带 → colspan（真合并格，保留）。
4. **一格多值**：同列带内相邻 token x-gap < 带宽×0.5 才合并一格，否则独立成格 → 胶合格（'3466 84605.06'）天然消失。
5. **表头跨行**：多 y 带合并为表头区；seed 锚匹配合并后表头文本（现有 `_norm_header` 不变）。
6. 输出：与现有 Table 同构 `{rows, cell_bboxes}`（+spans 可选），直接进现有 seed 匹配+提取+仲裁，**下游零改动**。

### 2.3 病征触发（渐进，不全量重建）

PP-Structure 表命中任一 → 触发重建：
- P-1 任一 cell 文本含 ≥2 个可解析数字（空格/胶水分隔）；
- P-2 seed 锚定后该表仲裁 needs_review 行占比 >30%；
- P-3 锚列 x-band 与 cell bbox x 中心失配率 >30%。

### 2.4 两版比对与降级

- 两版各跑 seed 匹配+提取+行级算术自洽判定，**自洽率高者胜**；平手/无法判定 → PP-Structure（保守）。
- 胜者进正常落库；重建版胜出时 `parse_meta.geometry_rebuilt=true`。
- 放弃重建条件：无 tokens / 重建行数 < 原表行数×0.7 / 列数 < 3 / 聚类异常 → 用原版。

## 3. L3 LLM 兜底（选择性）

- **触发**：strict seed-only 下 `unmatched_tables` 非空；或 matched 表 NR 率 >50% 且几何层不可用/也失败。
- **调用**：管线子进程内 httpx 直调 OpenAI 兼容端点（base_url/key/model 由 backend `run_pipeline_subprocess` 经环境变量传入，沿 config.yaml 既有 LLM 配置）；温度 0；超时 30s；不可达/超时 → 整表 needs_review，不阻塞管线。
- **输入/输出**：合并表头文本 + 每列前 2 个非空样本值 → 角色 JSON（name/spec/qty/unit/price_unit/price_total/price_untaxed），写入 `parse_meta.llm_roles`（审计留痕）。
- **验收门**：按映射走确定性提取+仲裁，行级算术自洽率 ≥90% → 采纳（条目正常落库）；否则整表 needs_review、不采纳。
- LLM 输出不进任何条目值路径；失败重试 ≤1 次。

## 4. L1 规则生态 + L4 数据闭环

- **seed 草稿一键生成**：设置页 unmatched 表抽屉内，从表头一键生成 seed 草稿（`draftFromHeader` 已有基础）→ 人工确认入库双镜像。
- **NR 率 KPI**：合同列表徽章展示每文档 needs_review 行占比（数据已有，纯前端聚合）。
- **L4 锚词回流**：人工"修正/采纳"落库时，反推该列头词追加到 seed **候选词**暂存（`parse_meta`/本地记录，仅记录不自动生效，审后入库）——核一次强一次。

## 5. 数据模型变更

| 位置 | 变更 |
|---|---|
| `mcp-server/ocr-service` | Table dataclass + `tokens` 字段；per-crop token 收集透出；路由无变更 |
| skill `document_parser.py` | Table/to_cache/from_cache + tokens |
| OCR 缓存 | `tables[].tokens` |
| `parse_meta` | +`geometry_rebuilt` / `llm_roles` / 病征计数（JSON，无 DDL） |
| `CpaItem` / `cpa_documents` | **零变更** |
| harness / 平台核心 | **零变更**（扩展层+skill+自有 OCR 服务边界内） |

## 6. 降级与错误处理

- tokens 缺失 / 聚类置信低 → PP-Structure 现状（零回归）。
- LLM 不可达/超时/映射被门拒绝 → needs_review，管线不阻塞。
- 两版表比对分歧 → 算术自洽率仲裁，平手取 PP-Structure。
- 几何层任何异常 → try/except 包裹整层，退回原表（与布局失败单页不 kill 全局同一纪律）。

## 7. 测试与验收

- **调价表 11 行 = 几何层首个验收用例**：真值已固化 `.wolf/tmp/tiaojia_forensic2.json`（真值表见 bug-3400 第十二层提交说明）；以缓存 tokens 重建后 11/11 命中。
- **桂北 400 行 bad_rate=0 硬门**不变（`audit_all.py` 容器内重放）。
- 分层 fixture：几何聚类（合成 token 阵列：跨行表头/合并格/胶合 token/列漂移）、病征触发三例、两版比对仲裁、LLM 门（mock 端点：好映射采纳/坏映射拒绝/超时降级）。
- **端到端比特一致回归**：3 份样例重解析，无病征路径产出与当前 DB 完全一致（几何/LLM 层零干预时）。
- host 套件全绿（现基线 106 passed / 1 skipped）。

## 8. 实施分期（每期独立可交付、可中止）

- **P1 几何层**：token 透出+缓存 v2 → 聚类重建 → 病征触发+两版比对 → 调价表验收 + 桂北硬门 + 比特一致回归。
- **P2 LLM 兜底**：列标注+验收门+unmatched 触发+审计留痕。
- **P3 规则生态**：seed 草稿一键生成、NR 率 KPI 徽章、锚词回流。

### 非目标（本期不做）

- 全量几何重建（仍病征触发）；LLM 直读价格；旧缓存强制重 OCR；harness/平台层改动；seed 自动生效（L4 仅暂存）。
