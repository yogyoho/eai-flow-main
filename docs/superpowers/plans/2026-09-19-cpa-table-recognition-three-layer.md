# CPA 表格识别三层重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已确认 spec（`docs/superpowers/specs/2026-09-19-cpa-table-recognition-three-layer-design.md`）落地几何网格重建（病征触发）+ LLM 列语义兜底（算术验收门）+ 规则生态运营化。

**Architecture:** OCR 服务顺带透出表区域内行级 token（近零运行时增量）→ 缓存 v2；命中病征的表用 token 聚类重建网格并与 PP-Structure 版比对（算术自洽率高者胜）；规则仍失败的表走 LLM 列标注（LLM 永不生成价格数值）。seed-only 提取管线本身零改动。

**Tech Stack:** Python 3.12（skill 脚本/OCR 服务）、httpx（LLM 调用）、pytest、React/TS 前端（P3）。

**环境约定（全任务适用）：**
- host 测试：`cd skills/public/contract-price-analysis && python -m pytest tests/<file> -v`（gateway 容器无 pytest）
- 容器内 python：`docker exec deer-flow-gateway sh -c '/app/backend/.venv/bin/python ...'`（系统 python 无 psycopg；Git Bash 下 docker exec 参数前置 `MSYS_NO_PATHCONV=1`）
- `.wolf/tmp` 不进容器——容器内侧探针用 `docker cp` 到 `/tmp`
- 严格 seed-only 管线语义不可破坏；不 commit 由主会话统一提交；桂北 400 行 bad_rate=0 为回归硬门（容器内跑 `.wolf/tmp/audit_all.py` 的拷贝）
- OCR 服务改动需重建：`cd docker && docker compose -p eai-docker -f docker-compose-dev.yaml up -d --build ocr`

---

## P1 几何层

### Task 1: OCR 服务 token 透出

**Files:**
- Modify: `mcp-server/ocr-service/schemas.py`（Table dataclass）
- Modify: `mcp-server/ocr-service/ocr_engine.py`（`_table_region`，约 L296-330）

- [ ] **Step 1: Table 增加 tokens 字段**（schemas.py，与现有 Cell/Table 定义同风格）

```python
@dataclass
class Table:
    ...  # 现有字段不动
    tokens: list = field(default_factory=list)  # [{text, box:[x1,y1,x2,y2](页绝对像素), score}]
```

- [ ] **Step 2: `_table_region` 收集 per-crop OCR 行 token**。该函数内已有 `res = self._ocr(crop)` 产出的 `[[box,text,score],...]`（box 为裁剪相对坐标）；现有代码已把 cell_bboxes 从裁剪相对偏移到页绝对坐标——token 用**同一偏移算术**：

```python
tokens = [
    {"text": str(txt), "box": [float(c) for c in _offset_box(box)], "score": float(sc)}
    for box, txt, sc in res or []
]
# _offset_box = 现有 cbbs 偏移逻辑提取的同参数小函数; 返回 Table(..., tokens=tokens)
```

- [ ] **Step 3: 验证**。重建 ocr 容器（见环境约定），对任一已上传文档 `--re-ocr` 一次，`docker exec deer-flow-gateway sh -c '/app/backend/.venv/bin/python -c "...store.get_ocr_cache(...);print(len(data[\"tables\"][0].get(\"tokens\",[])))"'` Expected: >0
- [ ] **Step 4: 不 commit**（主会话统一提交）。

### Task 2: skill 侧 token 接收 + 缓存 v2

**Files:**
- Modify: `skills/public/contract-price-analysis/scripts/document_parser.py`（TableExtract L26-36、parse_document 表循环 L90+、to_cache/from_cache）

- [ ] **Step 1: TableExtract 增字段** `tokens: list = field(default_factory=list)`（页归一化 0~1，与 cell_bboxes 同规格）。
- [ ] **Step 2: parse_document 归一化透传**：表循环内按 cell_bboxes 相同的页宽高归一化 token box；`page.get("tables")` 缺 tokens（旧服务）→ 空列表。
- [ ] **Step 3: to_cache/from_cache 携带 tokens**；from_cache 对缺键容错 `t.get("tokens", []) or []`（旧缓存=零回归）。
- [ ] **Step 4: 失败测试先行**（可并入 Task 3 测试文件）：`test_from_cache_tolerates_missing_tokens`。
- [ ] **Step 5: host 套件全绿**。

### Task 3: geometry_rebuild 模块（核心算法）

**Files:**
- Create: `skills/public/contract-price-analysis/scripts/geometry_rebuild.py`
- Create: `skills/public/contract-price-analysis/tests/test_geometry_rebuild.py`

- [ ] **Step 1: 写失败测试**（合成 token 阵列四场景，断言重建 rows）：

```python
# 场景1 多行表头跨行: "调整后"token 纵跨2行带 → 顶部两行 rows 中该列内容同置(下游 _collapse_header 负责合并,此处只要求 token 各落其带)
# 场景2 胶合分格: 同一列带内两个 token x-gap >= 带宽*0.5 → 两格
# 场景3 合并格: 一个 token 横跨2列带 → colspan: 该 token 占左格,右格占位空串(与 PP-Structure 展开语义一致)
# 场景4 列恒定: 三行同类 token x-center 微漂(±带宽*0.2) → 仍落同一列索引
def test_rebuild_multi_row_header(): ...
def test_rebuild_splits_glued_tokens(): ...
def test_rebuild_colspan_placeholder(): ...
def test_rebuild_stable_columns_under_drift(): ...
def test_has_glue_symptom():  # 含'3466 84605.06'的行 → True; 纯文本行 → False
```

- [ ] **Step 2: 跑测试确认失败**（ModuleNotFoundError）。Run: `python -m pytest tests/test_geometry_rebuild.py -v`
- [ ] **Step 3: 实现**：

```python
"""几何网格重建: 表区域行级 token → rows/cell_bboxes。spec §2.2。"""
def rebuild_grid(tokens, ncols_hint=None):
    """tokens: [{text, box:[x1,y1,x2,y2], score}](归一化0~1)。
    返回 (rows, cell_bboxes): 与 TableExtract.rows/cell_bboxes 同构。
    行: y-center 排序聚带, 带宽=token 高度中位数*0.6
    列: 行内 token x 边界断点检测 → 跨行合并全局列带; token 按 x-center 落带
    合并: 同带相邻 token x-gap < 带宽*0.5 才并格; token 横跨多带 → 占首带余带补空串
    列数 < 3 或行数 == 0 → 返回 (None, None) 表示放弃"""
```

```python
_GLUE_NUM = __import__("re").compile(r"\d[\d,，.]*\s+\d[\d,，.]*")
def has_glue_symptom(rows):
    """P-1: 任一 cell 文本含 ≥2 个空格分隔可解析数字 → True。"""
    return any(_GLUE_NUM.search(c or "") for row in rows for c in row)
```

- [ ] **Step 4: 跑测试全绿**。
- [ ] **Step 5: 主会话 commit（P1 前半）**。

### Task 4: cli.py 病征触发 + 两版比对

**Files:**
- Modify: `skills/public/contract-price-analysis/scripts/cli.py`（`_extract_from_tables` 表循环；`_MIN_*` 常量区加阈值）

- [ ] **Step 1: 失败测试**（tests/test_geometry_rebuild.py 追加，构造：seed 命中表 + tokens + PP-Structure 行含胶合格 → 断言走重建且 `parse_meta["geometry_rebuilt"]` 置位；桂北式正常表 + tokens → 断言零干预）。两版各跑 seed 匹配+提取+仲裁后统计行级 ok 率的函数抽为可测纯函数：

```python
def _table_ok_rate(items):
    """items: extract 产物; ok(含已仲裁 ok)/needs_review 占比。"""
    if not items: return 0.0
    ok = sum(1 for it in items if it.get("validation_status") == "ok")
    return ok / len(items)
```

- [ ] **Step 2: 实现 wiring**（`_extract_from_tables` 内，单表处理后）：

```python
# 病征(spec §2.3): P-1 胶合格 / P-2 该表 NR 率>0.30 / P-3 锚列 x 失配率>0.30
# tokens 可用且未重建过 → geometry_rebuild.rebuild_grid
# 重建版走同一 match_seed+extract_items_seed+仲裁 → _table_ok_rate 高者胜; 平手取原版(保守)
# 胜者若为重建版: parse_meta.geometry_rebuilt=True(表级记录 page_no/table_idx)
# 任何异常 → try/except 退回原表(spec §6)
```

P-3 失配率 = 锚列 x-band 之外落点的锚列值 cell 数 ÷ 锚列 cell 总数（用现有 roles_x 与 cell_bboxes）。
- [ ] **Step 3: host 全套件全绿**（含既有 bug-3400/3409 fixture——**非 tokens 表行为比特不变**）。
- [ ] **Step 4: 主会话 commit（P1 代码完）**。

### Task 5: P1 端到端验收（活体）

- [ ] **Step 1: 重建 ocr 容器**（环境约定命令），`--re-ocr` 重解析 JZGS 钢筋补充协议（tokens 进缓存）。
- [ ] **Step 2: 调价表验收**：DB 重查 11 行，对照 `.wolf/tmp/tiaojia_forensic2.json` 真值表——11/11 精确、`validation_status=ok`。
- [ ] **Step 3: 桂北硬门**：`--re-ocr` 后容器内重放 audit_all.py，bad_rate=0。
- [ ] **Step 4: 比特一致回归**：桂北、JZGS 主表在几何层零干预路径下条目值与验收前 DB 一致（SQL diff 为空）。
- [ ] **Step 5: 记录 parse_meta**（geometry_rebuilt 置位表清单）到 runbook。

## P2 LLM 兜底

### Task 6: llm_fallback 模块

**Files:**
- Create: `skills/public/contract-price-analysis/scripts/llm_fallback.py`
- Create: `skills/public/contract-price-analysis/tests/test_llm_fallback.py`

- [ ] **Step 1: 失败测试**（monkeypatch `httpx.post`）三例：合法映射 JSON → roles dict；坏 JSON/超时 → None；验收门：映射后 ok 率 <0.90 → 不采纳。

```python
ROLE_ENUM = ["name", "spec", "qty", "unit", "price_unit", "price_total", "price_untaxed"]

def annotate_roles(header_texts, sample_cols, base_url, api_key, model, timeout=30.0):
    """表头合并文本+每列≤2样本 → {列索引: ROLE_ENUM} | None。
    httpx.post(f"{base_url}/chat/completions", temperature=0, max_tokens=500)。
    解析 content 中首个 JSON 对象; 失败/缺 name 或 (price_unit|price_total) → None。"""

def try_llm_fallback(table, seeds, doc_uri, llm_cfg):
    """unmatched 表兜底: annotate_roles → 角色映射走既有 extract_items_seed 同路径提取
    → 行级 ok 率 ≥0.90 采纳(items, meta={"llm_roles":...}) ; 否则 (None, meta)。"""
```

- [ ] **Step 2: 实现至全绿**（LLM 输出不进条目值路径——值仍由确定性提取+仲裁产生）。
- [ ] **Step 3: 主会话 commit**。

### Task 7: cli/service 触发 wiring

**Files:**
- Modify: `skills/public/contract-price-analysis/scripts/cli.py`（unmatched_tables 处理后）
- Modify: `backend/app/extensions/contract_price/service.py`（run_pipeline_subprocess env 透传）

- [ ] **Step 1: 失败测试**：matched-but-NR>50% 表 + llm_cfg 注入 → 采纳路径 meta.llm_roles 置位；llm_cfg=None → 行为零变化（现状直通）。
- [ ] **Step 2: cli wiring**：`unmatched` 或 matched 表 NR>0.50 且几何不可用/失败时调 `try_llm_fallback`；`llm_cfg` 取自新增 `--llm-base-url/--llm-key/--llm-model`（缺省 None=层关闭）；采纳表从 unmatched_tables 移除并正常落库，`parse_meta.llm_roles` 留痕。
- [ ] **Step 3: service.py**：run_pipeline_subprocess 从 gateway 配置读 LLM 三元组注入子进程 env/argv（缺省不传）。超时 30s 由 Task 6 默认值保证；不可达 → 整表 needs_review 不阻塞。
- [ ] **Step 4: 全套件全绿；主会话 commit（P2 完）**。

## P3 规则生态（UI/运营）

### Task 8: unmatched 抽屉"生成 seed 草稿"

**Files:** Modify: `frontend/src/extensions/contract-price/components/UnmatchedTablesDrawer.tsx`、`SeedRulesCard.tsx`
- [ ] unmatched 表行加「生成 seed 草稿」按钮 → 用该表表头调既有 `draftFromHeader` → 打开 SeedEditorDrawer 预填 → 人工确认走既有保存 API。测：`pnpm typecheck` + 手动冒烟。

### Task 9: NR 率 KPI 徽章

**Files:** Modify: `backend/app/extensions/contract_price/routers.py`（docs 列表聚合 needs_review 数）、`ContractsView.tsx`
- [ ] docs 列表响应加 `items_total`/`items_needs_review`（一条 GROUP BY 聚合查询）；ContractsView 文档卡徽章显示 `needs_review/total`（>0 黄色）。测：`pnpm typecheck` + 容器 restart gateway 后 curl 冒烟。

### Task 10: L4 锚词暂存

**Files:** Modify: `skills/public/contract-price-analysis/scripts/db.py`/cli 修正路径（或既有条目修正端点）
- [ ] 人工修正/采纳落库时，将该列当前表头词追加 `cpa_documents.parse_meta.suggested_anchors`（dict: role → [words]，去重，仅暂存不自动生效）。测：host 单测断言追加+去重。
- [ ] 主会话 commit（P3 完）。

---

## 验收总门（spec §7）

1. 调价表 11 行真值 11/11（tokens 路径）
2. 桂北 400 行 bad_rate=0（几何层零干预比特一致）
3. host 套件全绿；`pnpm typecheck` 全绿
4. 3 份样例重解析 DB diff 为空（无病征路径）
