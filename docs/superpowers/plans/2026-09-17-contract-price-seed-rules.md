# 合同价格分析 Seed 定位规则 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把合同价格分析的表格识别从"通用列名猜测"改为"seed 定位规则库"（严格 seed-only），并补齐 OCR 方向归一化、分类提取、OCR 结果缓存与三 tab UI。

**Architecture:** seed 规则存 `config.json`（走现有 GET/PUT /config）；`table_classifier.py` 新增 `match_seed` 主路径（通用分类降级为 meta 标注）；OCR 结构化结果按内容哈希缓存进 MinIO 使重解析秒级；方向归一化在 ocr-service 引擎内页级完成。前端配置 tab 重建为 seed 卡片管理，合同解析 tab 加未匹配表抽屉闭环。

**Tech Stack:** Python 3.12 / SQLAlchemy / FastAPI（gateway 内扩展）、RapidOCR（ocr-service 独立容器）、Next.js 16 + React 19 + TanStack Query、pytest + vitest。

**设计文档:** `docs/superpowers/specs/2026-09-17-contract-price-seed-rules-design.md`

**测试命令约定:**
- 技能管线测试: `cd skills/public/contract-price-analysis && python -m pytest tests/<file> -v`（conftest 已设 env 默认值；测试用合成表格，不跑真 OCR）
- 后端测试: `cd backend && PYTHONPATH=. uv run pytest tests/<file> -v`
- 前端: `cd frontend && pnpm typecheck`（涉及组件时）+ `pnpm lint`
- Docker 生效: 改 skill/后端代码后 `docker compose -p eai-docker restart gateway`；改 ocr-service 后 `cd mcp-server/ocr-service && docker compose -p eai-docker -f docker/docker-compose.base.yaml -f docker/docker-compose.dev.yaml up -d --build ocr`（按仓库实际 compose 叠加，见 `.wolf` 记忆: up 必须带全 -f）

**关键接口契约（全文一致，改一处必改全部）:**

```
Seed dict = {
  "id": str, "display_name": str,
  "title_keywords": [str, ...],          # 仅消歧用,不作确认条件
  "columns": {                            # 锚点=归一化子串
    "name": [...], "spec": [...], "qty": [...], "unit": [...],
    "price_unit": [...], "price_total": [...], "price_untaxed": [...],
  },
  "exclude": {"price_unit": ["不含税"], ...},  # 可选
  "source": str | 无,
}
ROLE_ORDER = ["name","spec","qty","unit","price_unit","price_total","price_untaxed"]
seed 确认条件: name 锚定成功 且 price_unit/price_total 至少一个锚定成功
多候选: 标题命中优先 → 锚定角色数最多

extract_items_seed 产出的 raw item =
  {name, spec, qty_raw, unit, price_unit_raw, price_total_raw,
   price_untaxed_raw, category, row_idx}

parse_meta 新键 = unmatched_tables[], matched_seeds{}, orientation_fixed_pages[]
parse_status 新值 = no_tables (tables_found==0)
OCR 缓存 key = "ocr/{sha256_hex}.json"（内容寻址,免失效）
```

---

## P1 后端管线（技能脚本 + gateway 扩展）

### Task 1: seed 类型 + 内置 seed 库 + 配置通道

**Files:**
- Create: `skills/public/contract-price-analysis/scripts/seed_library.py`
- Create: `skills/public/contract-price-analysis/tests/test_seed_library.py`
- Modify: `backend/app/extensions/contract_price/schemas.py`（ConfigOut 加 table_seeds）
- Modify: `backend/app/extensions/contract_price/crud.py:726-731`（load_config 注入默认）
- Create: `backend/tests/test_contract_price_seed_config.py`

- [x] **Step 1: 写失败测试（seed 库结构与归一化）**

`skills/public/contract-price-analysis/tests/test_seed_library.py`:

```python
"""seed 库结构契约: 6 条内置规则,每条满足 seed 确认条件的最低字段。"""

from scripts.seed_library import DEFAULT_TABLE_SEEDS, normalize_seeds


def test_default_library_has_six_seeds():
    assert len(DEFAULT_TABLE_SEEDS) == 6
    for s in DEFAULT_TABLE_SEEDS:
        assert s["id"] and s["display_name"]
        assert s["columns"]["name"], f"{s['id']} 缺 name 锚点"
        assert s["columns"]["price_unit"] or s["columns"]["price_total"], (
            f"{s['id']} 缺价格锚点"
        )


def test_normalize_seeds_drops_invalid_and_fills_defaults():
    raw = [
        {"id": "ok", "display_name": "x", "columns": {"name": ["品名"], "price_unit": ["单价"]}},
        {"id": "", "display_name": "bad"},
        "not-a-dict",
        {"id": "nocost", "display_name": "y", "columns": {"name": ["品名"]}},
    ]
    out = normalize_seeds(raw)
    assert [s["id"] for s in out] == ["ok"]


def test_price_unit_exclude_guards_untaxed():
    """含税单价 seed 必须排除 不含税 列(子串陷阱)。"""
    gcl = next(s for s in DEFAULT_TABLE_SEEDS if s["id"] == "gcl-qd")
    assert "不含税" in gcl.get("exclude", {}).get("price_unit", [])
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_seed_library.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'scripts.seed_library'`

- [x] **Step 3: 实现 seed_library.py**

```python
"""内置 seed 定位规则库(源真相)。

backend/app/extensions/contract_price/crud.py 的默认注入与本文件保持同步
(同 models.py 的双份镜像约定)。锚点为归一化子串——归一化规则见
table_classifier._norm_header(去内部空白/去（）括注/全角转半角)。
v1 锚点草案,以 7 样例验收运行实测为准(设计文档 §5)。
"""

from __future__ import annotations

_GCL_EXCLUDE = {"price_unit": ["不含税"]}

DEFAULT_TABLE_SEEDS: list[dict] = [
    {
        "id": "gcl-qd",
        "display_name": "工程量清单计价表",
        "title_keywords": ["工程量清单", "清单计价"],
        "columns": {
            "name": ["项目名称", "品名", "物资名称"],
            "spec": ["规格型号", "参数"],
            "qty": ["工程量", "数量"],
            "unit": ["单位", "计量单位"],
            "price_unit": ["含税单价"],
            "price_total": ["含税合价"],
            "price_untaxed": ["不含税单价"],
        },
        "exclude": _GCL_EXCLUDE,
        "source": "样例:房建工程（桂北数据中心）",
    },
    {
        "id": "jzgs-gc",
        "display_name": "钢材物资采购清单(JZGS)",
        "title_keywords": ["物资采购", "钢材"],
        "columns": {
            "name": ["品名"],
            "spec": ["规格型号"],
            "qty": ["数量"],
            "unit": ["单位"],
            "price_unit": ["综合单价"],
            "price_total": ["总金额"],
            "price_untaxed": [],
        },
        "exclude": {"price_unit": ["不含税"]},
        "source": "样例:JZGS-JS-IC-CL-01-2021物资采购合同（钢材）",
    },
    {
        "id": "sp-gj",
        "display_name": "钢筋供货价格表(上浦)",
        "title_keywords": ["钢筋", "供货"],
        "columns": {
            "name": ["物资名称"],
            "spec": ["材质"],
            "qty": ["暂定数量", "数量"],
            "unit": ["计量单位", "单位"],
            "price_unit": ["含税单价"],
            "price_total": ["含税总价"],
            "price_untaxed": ["不含税单价"],
        },
        "exclude": _GCL_EXCLUDE,
        "source": "样例:上浦项目-钢筋采购合同",
    },
    {
        "id": "msm-sc",
        "display_name": "木饰面石材物资清单",
        "title_keywords": ["木饰面", "石材", "物资"],
        "columns": {
            "name": ["物资名称", "材质", "品名"],
            "spec": ["规格", "材质规格"],
            "qty": ["暂定数量", "数量"],
            "unit": ["计量单位", "单位"],
            "price_unit": ["综合单价", "含税单价"],
            "price_total": ["含税总价"],
            "price_untaxed": ["不含税单价"],
        },
        "exclude": _GCL_EXCLUDE,
        "source": "样例:木饰面、石材物资采购合同",
    },
    {
        "id": "gc-qzb",
        "display_name": "钢材采购明细(签字版)",
        "title_keywords": ["钢材", "采购"],
        "columns": {
            "name": ["品名"],
            "spec": ["规格型号"],
            "qty": ["数量"],
            "unit": ["单位"],
            "price_unit": ["含税单价"],
            "price_total": ["含税合价"],
            "price_untaxed": ["不含税单价"],
        },
        "exclude": {"price_unit": ["不含税"], "price_total": ["不含税"]},
        "source": "样例:钢材采购合同-签字版",
    },
    {
        "id": "bcxy-tj",
        "display_name": "补充协议价格调整表",
        "title_keywords": ["补充协议", "价格调整", "调价"],
        "columns": {
            "name": ["物资名称"],
            "spec": ["材质规格"],
            "qty": ["调整数量", "数量"],
            "unit": ["计量单位", "单位"],
            "price_unit": ["综合单价", "调整后单价"],
            "price_total": ["调整后合价", "总金额", "含税总价"],
            "price_untaxed": [],
        },
        "exclude": _GCL_EXCLUDE,
        "source": "样例:钢筋补充协议-需盖章11",
    },
]


def normalize_seeds(raw: object) -> list[dict]:
    """清洗外部输入的 seed 列表: 丢非 dict/缺 id/不满足确认条件最低要求的条目,
    补全缺失键。UI 保存的任意 JSON 都不会让管线拿到坏 seed。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        cols = s.get("columns") if isinstance(s.get("columns"), dict) else {}
        name = [str(t) for t in cols.get("name") or [] if str(t).strip()]
        price_unit = [str(t) for t in cols.get("price_unit") or [] if str(t).strip()]
        price_total = [str(t) for t in cols.get("price_total") or [] if str(t).strip()]
        if not str(s.get("id") or "").strip() or not name or not (price_unit or price_total):
            continue
        out.append(
            {
                "id": str(s["id"]).strip(),
                "display_name": str(s.get("display_name") or s["id"]).strip(),
                "title_keywords": [str(t) for t in s.get("title_keywords") or [] if str(t).strip()],
                "columns": {
                    "name": name,
                    "spec": [str(t) for t in cols.get("spec") or [] if str(t).strip()],
                    "qty": [str(t) for t in cols.get("qty") or [] if str(t).strip()],
                    "unit": [str(t) for t in cols.get("unit") or [] if str(t).strip()],
                    "price_unit": price_unit,
                    "price_total": price_total,
                    "price_untaxed": [str(t) for t in cols.get("price_untaxed") or [] if str(t).strip()],
                },
                "exclude": {
                    str(k): [str(t) for t in v if str(t).strip()]
                    for k, v in (s.get("exclude") or {}).items()
                    if isinstance(v, list)
                },
                "source": str(s["source"]) if s.get("source") else None,
            }
        )
    return out
```

- [x] **Step 4: 跑测试确认通过**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_seed_library.py -v`
Expected: 3 passed

- [x] **Step 5: 后端 ConfigOut 加 table_seeds + load_config 注入默认**

`backend/app/extensions/contract_price/schemas.py` 的 `ConfigOut`（L108-123）末尾加一个字段:

```python
class ConfigOut(BaseModel):
    parse_mode: str = "table"
    cluster_eps: float = 0.6
    cluster_min_samples: int = 2
    scheduled_enabled: bool = False
    schedule_cron: str | None = None
    # Table-name keywords that mark a goods/price table even without a clear
    # price header (different contracts name price tables differently).
    price_table_keywords: list[str] = [
        "工程量清单",
        "分部分项",
        "单价措施",
        "设备清单",
        "报价",
        "暂列",
    ]
    # v3: seed 定位规则库(设计 docs/superpowers/specs/2026-09-17-contract-price-seed-rules-design.md)。
    # 结构: [{id, display_name, title_keywords, columns{name,spec,qty,unit,price_unit,
    # price_total,price_untaxed}, exclude?, source?}] — 与技能 scripts/seed_library.py 保持同构。
    table_seeds: list[dict] = []
```

`backend/app/extensions/contract_price/crud.py` 的 `load_config`（L726-731）注入默认:

```python
def load_config() -> ConfigOut:
    path = _config_path()
    if os.path.exists(path):
        cfg = ConfigOut(**json.load(f if False else open(path, encoding="utf-8")))
    else:
        cfg = ConfigOut()
    if not cfg.table_seeds:
        from app.extensions.contract_price.seed_defaults import DEFAULT_TABLE_SEEDS

        cfg.table_seeds = DEFAULT_TABLE_SEEDS  # UI 首次打开即见内置规则库
    return cfg
```

同文件新建 `backend/app/extensions/contract_price/seed_defaults.py`（内容 = `scripts/seed_library.py` 的 `DEFAULT_TABLE_SEEDS` 列表原样复制，文件头注释写明「与 skills/public/contract-price-analysis/scripts/seed_library.py 保持同步（双份镜像约定，同 models.py）」）。`save_config` 不动（`model_dump()` 自动带上新字段）。

- [x] **Step 6: 后端配置往返测试**

`backend/tests/test_contract_price_seed_config.py`:

```python
"""ConfigOut.table_seeds 往返 + load_config 默认注入。"""

import json

from app.extensions.contract_price.crud import load_config, save_config
from app.extensions.contract_price.schemas import ConfigOut


def test_config_roundtrip_keeps_table_seeds(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"table_seeds": [{"id": "t1", "display_name": "T", "columns": {"name": ["品名"], "price_unit": ["单价"]}}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    import app.extensions.contract_price.crud as crud

    monkeypatch.setattr(crud, "_config_path", lambda: str(cfg_path))
    got = load_config()
    assert got.table_seeds[0]["id"] == "t1"
    saved = save_config(got)
    assert saved.table_seeds[0]["id"] == "t1"


def test_load_config_injects_default_seeds_when_empty(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    import app.extensions.contract_price.crud as crud

    monkeypatch.setattr(crud, "_config_path", lambda: str(cfg_path))
    got = load_config()
    assert len(got.table_seeds) == 6
```

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_contract_price_seed_config.py -v`
Expected: 2 passed

- [x] **Step 7: Commit**

```bash
git add skills/public/contract-price-analysis/scripts/seed_library.py skills/public/contract-price-analysis/tests/test_seed_library.py backend/app/extensions/contract_price/schemas.py backend/app/extensions/contract_price/crud.py backend/app/extensions/contract_price/seed_defaults.py backend/tests/test_contract_price_seed_config.py
git commit -m "feat(cpa): seed定位规则库——6条内置规则+normalize+配置通道(table_seeds)"
```

---

### Task 2: match_seed 匹配算法（归一化 + 锚点 + exclude + 消歧）

**Files:**
- Modify: `skills/public/contract-price-analysis/scripts/table_classifier.py`（文件尾追加新函数）
- Create: `skills/public/contract-price-analysis/tests/test_seed_match.py`

- [x] **Step 1: 写失败测试**

`skills/public/contract-price-analysis/tests/test_seed_match.py`:

```python
"""match_seed: 归一化子串锚点/exclude 守卫/确认条件/多候选消歧。合成表格,无 OCR。"""

from scripts.seed_library import DEFAULT_TABLE_SEEDS
from scripts.table_classifier import _norm_header, match_seed

SEEDS = DEFAULT_TABLE_SEEDS

_GCL_ROWS = [
    ["工程量清单计价表"],
    ["序号", "项目名称", "单 位", "工程量", "不含税单价", "含税单价", "含税合价"],
    ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
]


def test_norm_header_strips_spaces_and_brackets():
    assert _norm_header("5.综合单 价（5=2+3）") == "5.综合单价"
    assert _norm_header("含 税 单 价") == "含税单价"
    assert _norm_header("不含税单价") == "不含税单价"


def test_match_seed_gcl_baseline():
    seed, roles, header_rows = match_seed(_GCL_ROWS, SEEDS)
    assert seed["id"] == "gcl-qd"
    assert roles["name"] == 1
    assert roles["price_unit"] == 5   # 含税单价, 不是 不含税单价(2)
    assert roles["price_total"] == 6
    assert roles["price_untaxed"] == 4
    assert header_rows == 2           # 标题行 + 表头行


def test_match_seed_jzgs_formula_header():
    """JZGS 表头带编号+公式后缀,归一化后命中 综合单价/总金额;网价/运杂费不入角色。"""
    rows = [
        ["序号", "品名", "规格型号", "单位", "1.数量", "2.网价", "3.运杂费", "4.税率", "5.综合单 价（5=2+3）", "6.总金额 6=1*5"],
        ["1", "盘圆", "HPB300 6mm", "吨", "100.000", "4930.00", "107.00", "13%", "5037.00", "503700.00"],
    ]
    seed, roles, _ = match_seed(rows, SEEDS)
    assert seed["id"] == "jzgs-gc"
    assert roles["price_unit"] == 8   # 综合单价,不是网价(5)
    assert roles["price_total"] == 9
    assert "spec" in roles and roles["spec"] == 2


def test_match_seed_exclude_blocks_untaxed_steal():
    """不含税单价 包含 含税单价 子串——exclude 必须拦住。签字版表。"""
    rows = [
        ["品名", "规格型号", "厂家/ 品牌", "单位", "数量", "税率", "网价", "其他 固定 单价", "含税 单价", "不含税 单价", "含税合价"],
        ["热轧光圆钢筋", "HPB300 6mm", "威钢", "t", "4.755", "13%", "4370", "390", "4760", "4214.16", "22633.80"],
    ]
    seed, roles, _ = match_seed(rows, SEEDS)
    assert seed["id"] == "gc-qzb"
    assert roles["price_unit"] == 8   # 含税单价列,非 不含税单价(9)
    assert roles["price_untaxed"] == 9


def test_match_seed_requires_name_and_price():
    """只有名称列没有价格列 → 不确认(返回 None 走 unmatched)。"""
    rows = [
        ["序号", "项目名称", "备注"],
        ["1", "平整场地", "独立费"],
    ]
    assert match_seed(rows, SEEDS) is None


def test_match_seed_title_disambiguation():
    """多 seed 都能锚上时,标题关键词命中者优先。"""
    rows = [
        ["钢筋供货及价格表"],
        ["物资名称", "材质", "计量单位", "暂定数量", "含税单价", "含税总价"],
        ["线材", "HPB300Φ8", "吨", "2.288", "6290", "14391.52"],
    ]
    seed, roles, _ = match_seed(rows, SEEDS)
    assert seed["id"] == "sp-gj"
    assert roles["spec"] == 1         # 材质列作规格
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_seed_match.py -v`
Expected: FAIL `ImportError: cannot import name '_norm_header'`

- [x] **Step 3: 实现（追加到 table_classifier.py 文件尾）**

```python
# ── seed 定位规则匹配 (v3, 严格 seed-only; 设计 §2) ──────────────────────────

_ROLE_ORDER = ["name", "spec", "qty", "unit", "price_unit", "price_total", "price_untaxed"]


def _norm_header(s: str) -> str:
    """归一化表头单元格: 去全部空白、去（）()括注(公式后缀如 5=2+3)、全角转半角、小写。

    实测噪声: '5.综合单 价（5=2+3）'、'含 税 单 价'、'含税单 价（元 /t)' —
    归一化后锚点子串匹配才能命中。"""
    if not s:
        return ""
    out = []
    depth = 0
    for ch in s:
        if ch in "（(":
            depth += 1
            continue
        if ch in "）)":
            depth = max(0, depth - 1)
            continue
        if depth:
            continue
        if ch.isspace():
            continue
        # 全角转半角(0xFF01-0xFF5E → 0x21-0x7E)
        out.append(chr(ord(ch) - 0xFEE0) if 0xFF01 <= ord(ch) <= 0xFF5E else ch.lower())
    return "".join(out)


def _title_text(rows: list, limit: int = 4) -> str:
    """前若干行的归一化联合文本(标题/表名关键词在这里找)。"""
    blob = " ".join((c or "") for r in rows[:limit] for c in r)
    return _norm_header(blob)


def _match_one_seed(rows: list, seed: dict, header_rows: int, header: list) -> tuple[dict, dict] | None:
    """单 seed 列锚定: 角色→第一个锚点命中的未占用列(exclude 守卫)。
    返回 (roles, score_detail) 或 None(确认条件不满足)。"""
    norm_cols = [_norm_header(h) for h in header]
    excl = seed.get("exclude") or {}
    roles: dict = {}
    for role in _ROLE_ORDER:
        anchors = [_norm_header(t) for t in (seed["columns"].get(role) or []) if t]
        if not anchors:
            continue
        banned = [_norm_header(t) for t in (excl.get(role) or [])]
        for ci, h in enumerate(norm_cols):
            if ci in roles.values() or not h:
                continue
            if any(b and b in h for b in banned):
                continue
            if any(a in h for a in anchors):
                roles[role] = ci
                break
    if "name" not in roles or not ("price_unit" in roles or "price_total" in roles):
        return None
    return roles, {"roles_n": len(roles)}


def match_seed(rows: list, seeds: list[dict]) -> tuple[dict, dict, int] | None:
    """严格 seed-only 主路径: 逐 seed 锚定,确认条件=name+任一价格角色;
    多候选: 标题关键词命中优先,其次锚定角色数多者。
    返回 (seed, roles{role: col_idx}, header_rows) 或 None(无 seed 确认)。"""
    if not rows or not seeds:
        return None
    header, header_rows = _collapse_header(rows)
    if not header:
        return None
    title = _title_text(rows)
    best: tuple[int, int, dict, dict] | None = None  # (title_hit, roles_n, seed, roles)
    for seed in seeds:
        got = _match_one_seed(rows, seed, header_rows, header)
        if got is None:
            continue
        roles, detail = got
        hit = any(_norm_header(kw) and _norm_header(kw) in title for kw in seed.get("title_keywords") or [])
        key = (1 if hit else 0, detail["roles_n"])
        if best is None or key > best[0:2]:
            best = (key[0], key[1], seed, roles)
    if best is None:
        return None
    return best[2], best[3], header_rows
```

- [x] **Step 4: 跑测试确认通过**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_seed_match.py tests/test_table_classifier.py -v`
Expected: 新 6 个 passed；既有 classifier 测试不回归（passed）

- [x] **Step 5: Commit**

```bash
git add skills/public/contract-price-analysis/scripts/table_classifier.py skills/public/contract-price-analysis/tests/test_seed_match.py
git commit -m "feat(cpa): match_seed严格主路径——归一化子串锚点+exclude守卫+确认条件+标题消歧"
```

---

### Task 3: extract_items_seed（列提取 + 分类行识别传播）

**Files:**
- Modify: `skills/public/contract-price-analysis/scripts/table_classifier.py`（追加）
- Create: `skills/public/contract-price-analysis/tests/test_seed_extract.py`

- [x] **Step 1: 写失败测试**

`skills/public/contract-price-analysis/tests/test_seed_extract.py`:

```python
"""extract_items_seed: 角色取值 + 分类行识别/传播。桂北实表结构合成回放。"""

from scripts.seed_library import DEFAULT_TABLE_SEEDS
from scripts.table_classifier import extract_items_seed, match_seed

SEED = next(s for s in DEFAULT_TABLE_SEEDS if s["id"] == "gcl-qd")

# 桂北 p2 实测结构: 标题/表头/分类行(一)建筑工程/数据.../分类行'屋面'/数据
ROWS = [
    ["工程量清单计价表", "", "", "", "", "", ""],
    ["序号", "项目名称", "单 位", "工程量", "不含税单价", "含税单价", "含税合价"],
    ["(一)", "建筑工程", "", "", "", "", ""],
    ["7", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
    ["12", "现浇构件钢筋", "t", "63.55", "1131.55", "1205.84", "76631.13"],
    ["", "屋面", "", "", "", "", ""],
    ["14", "雨棚面砂浆防水", "m2", "30.70", "18.35", "20.00", "614.00"],
]


def _extract():
    seed, roles, header_rows = match_seed(ROWS, [SEED])
    return extract_items_seed(ROWS, seed, roles, header_rows)


def test_category_rows_become_context_not_items():
    items = _extract()
    names = [it["name"] for it in items]
    assert "建筑工程" not in names and "屋面" not in names  # 分类行不产 item
    assert [it["name"] for it in items] == ["平整场地", "现浇构件钢筋", "雨棚面砂浆防水"]


def test_category_propagates_to_following_items():
    items = _extract()
    assert items[0]["category"] == "建筑工程"
    assert items[1]["category"] == "建筑工程"
    assert items[2]["category"] == "屋面"


def test_prices_mapped_to_seed_roles():
    items = _extract()
    assert items[0]["price_unit_raw"] == "1.20"
    assert items[0]["price_total_raw"] == "989.75"
    assert items[0]["price_untaxed_raw"] == "1.07"
    assert items[0]["qty_raw"] == "824.79"
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_seed_extract.py -v`
Expected: FAIL `ImportError: cannot import name 'extract_items_seed'`

- [x] **Step 3: 实现（追加到 table_classifier.py）**

```python
def _is_category_row(cells: dict) -> bool:
    """分类行判别: 名称非空 且 数量/单位/价格列全空(设计 §2)。
    价格漏读行通常带数量/单位,不会误判;今天此类行反正被跳过,零损失。"""
    if not (cells.get("name") or "").strip():
        return False
    return not any(
        (cells.get(k) or "").strip()
        for k in ("qty", "unit", "price_unit", "price_total", "price_untaxed")
    )


def extract_items_seed(
    rows: list,
    seed: dict,
    roles: dict,
    header_rows: int,
    cell_bboxes: list | None = None,
    roles_x: dict | None = None,
    initial_category: str | None = None,
) -> list:
    """Seed 路径行提取: 按 seed 角色取单元格 + 分类行上下文传播。

    对齐方式与 extract_items 相同: bbox-x 可用则按 x-band(抗漂移),否则按列号。
    产出 raw item: {name, spec, qty_raw, unit, price_unit_raw, price_total_raw,
    price_untaxed_raw, category, row_idx}。分类行(名称非空+数值列全空)不产 item,
    其名称作为后续 item 的 category,直到下一个分类行。"""
    use_x = bool(roles_x) and "name" in roles_x and _bboxes_usable(rows, cell_bboxes)
    skip = {"序号", "合计", "小计", "总计"}
    items: list = []
    # 跨页续传: 管线循环把上一表尾部分类传进来(设计§2 修订I2——表头重复页/续表页
    # 每页都会新开一次调用,不传则分类退化为页内局部)
    current_category: str | None = initial_category

    for ri in range(header_rows, len(rows)):
        row = rows[ri]
        if use_x:
            bbox_row = cell_bboxes[ri] if ri < len(cell_bboxes) else []
            cells = _row_cells_by_x(row, bbox_row, roles_x)
        else:

            def cell(idx, _row=row):
                return ( (_row[idx].strip() if idx is not None and idx < len(_row) else "") )

            cells = {role: cell(ci) for role, ci in roles.items()}
        name = (cells.get("name") or "").strip()
        if not name or name in skip:
            continue
        if _is_category_row(cells):
            current_category = name
            continue
        items.append(
            {
                "name": name,
                "spec": (cells.get("spec") or "").strip() or None,
                "qty_raw": cells.get("qty") or None,
                "unit": (cells.get("unit") or "").strip() or None,
                "price_unit_raw": cells.get("price_unit") or "",
                "price_total_raw": cells.get("price_total") or "",
                "price_untaxed_raw": cells.get("price_untaxed") or "",
                "category": current_category,
                "row_idx": ri,
            }
        )
    return items
```

- [x] **Step 4: 跑测试确认通过**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_seed_extract.py -v`
Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add skills/public/contract-price-analysis/scripts/table_classifier.py skills/public/contract-price-analysis/tests/test_seed_extract.py
git commit -m "feat(cpa): extract_items_seed——seed角色取值+分类行识别与上下文传播"
```

---

### Task 4: cli 严格管线改写（unmatched_tables/matched_seeds/no_tables）

**Files:**
- Modify: `skills/public/contract-price-analysis/scripts/cli.py`（`_load_seeds` 新增 L64 区；`_extract_from_tables` L296 起整体重写；`_process_one_doc` L644-748 签名与状态逻辑）
- Create: `skills/public/contract-price-analysis/tests/test_extract_strict.py`

- [x] **Step 1: 写失败测试**

`skills/public/contract-price-analysis/tests/test_extract_strict.py`:

```python
"""严格 seed-only 管线: 命中提取/未匹配零提取+记录/续表继承/meta 统计。"""

from types import SimpleNamespace

from scripts.cli import _extract_from_tables
from scripts.seed_library import DEFAULT_TABLE_SEEDS

SEEDS = DEFAULT_TABLE_SEEDS


def _tbl(rows, page_no=1, table_idx=0, conf=0.9):
    return SimpleNamespace(
        page_no=page_no, table_idx=table_idx, rows=rows, cell_bboxes=None,
        page_preview_b64="", mean_confidence=conf,
    )


def test_seed_hit_extracts_items_and_meta():
    tables = [_tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "现浇构件钢筋", "t", "63.55", "1131.55", "1205.84", "76631.13"],
    ])]
    items, meta = _extract_from_tables(tables, "s3://b/k.pdf", SEEDS)
    assert len(items) == 2
    assert items[0]["unit_price"] == 1.20          # seed price_unit → unit_price(统计)
    assert items[0]["price_untaxed"] == 1.07
    assert meta["goods_tables"] == 1
    assert meta["matched_seeds"] == {"工程量清单计价表": 1}
    assert meta["unmatched_tables"] == []


def test_unmatched_table_recorded_not_extracted():
    tables = [_tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
    ]), _tbl([
        ["编号", "事项", "说明", "标准"],       # 4列非价格表,无 seed 确认
        ["1", "进场", "三级教育", "合格"],
    ], page_no=3)]
    items, meta = _extract_from_tables(tables, "s3://b/k.pdf", SEEDS)
    assert len(items) == 1                              # 严格: 未匹配表零提取
    assert meta["unmatched_tables"][0]["page"] == 3
    assert meta["unmatched_tables"][0]["header"] == ["编号", "事项", "说明", "标准"]


def test_continuation_inherits_seed_roles():
    t1 = _tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
    ], page_no=4)
    t2 = _tbl([                                        # 续表: 无表头,列结构同
        ["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"],
    ], page_no=5, table_idx=0)
    items, meta = _extract_from_tables([t1, t2], "s3://b/k.pdf", SEEDS)
    assert len(items) == 2
    assert meta["continuation_tables"] == 1
    assert items[1]["goods_name"] == "回填方"
    assert items[1]["unit_price"] == 9.00


def test_category_threads_across_pages():
    """跨页分类续传(修订I2): 表1尾部是屋面分类,续表页首行(下一分类行之前)的
    item 必须继承 屋面;新分类行出现后切换。"""
    t1 = _tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["12", "现浇构件钢筋", "t", "63.55", "1131.55", "1205.84", "76631.13"],
        ["", "屋面", "", "", "", "", ""],
    ], page_no=4)
    t2 = _tbl([                                        # 续表: 无表头,屋面分类延续
        ["14", "雨棚面砂浆防水", "m2", "30.70", "18.35", "20.00", "614.00"],
        ["15", "涂膜防水屋面", "m2", "305.78", "57.14", "60.30", "18438.51"],
    ], page_no=5)
    items, meta = _extract_from_tables([t1, t2], "s3://b/k.pdf", SEEDS)
    assert meta["continuation_tables"] == 1
    assert [it["category"] for it in items] == ["屋面", "屋面"]


def test_category_threads_across_header_repeat_pages():
    """表头重复页(每页都 match_seed 命中)分类不丢: 页2 新分类行前继承页1尾部。"""
    t1 = _tbl([
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["", "屋面", "", "", "", "", ""],
        ["14", "雨棚面砂浆防水", "m2", "30.70", "18.35", "20.00", "614.00"],
    ], page_no=2)
    t2 = _tbl([                                        # 表头重复的页3
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["16", "屋面保温板", "m2", "790.80", "98.90", "106.57", "84274.66"],
    ], page_no=3)
    items, meta = _extract_from_tables([t1, t2], "s3://b/k.pdf", SEEDS)
    assert meta["goods_tables"] == 2
    assert items[-1]["category"] == "屋面"


def test_unit_price_reverse_calc_from_total():
    """含税单价缺失时 合价÷工程量 反算(seed price_total 列)。"""
    tables = [_tbl([
        ["序号", "项目名称", "单位", "工程量", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "989.75"],
    ])]
    items, _ = _extract_from_tables(tables, "s3://b/k.pdf", SEEDS)
    assert items[0]["unit_price"] is not None
    assert abs(items[0]["unit_price"] - 989.75 / 824.79) < 0.01
    assert items[0]["price_reason"] == "合价/工程量反算"
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_extract_strict.py -v`
Expected: FAIL（`_extract_from_tables` 第三个位置参数还是 keywords，行为不符）

- [x] **Step 3: 重写 `_extract_from_tables` + 新增 `_load_seeds`**

`cli.py` L64-82 的 `_load_price_keywords` 之后新增（旧函数保留不删，测试可能引用）:

```python
def _load_seeds() -> list[dict]:
    """Load seed 定位规则(config.json 的 table_seeds;空则注入内置库)。
    与 _load_price_keywords 同一配置文件/同一 CPA_CONFIG_JSON 通道。"""
    from scripts.seed_library import DEFAULT_TABLE_SEEDS, normalize_seeds

    path = os.environ.get(
        "CPA_CONFIG_JSON",
        "/app/backend/app/extensions/contract_price/config.json",
    )
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f).get("table_seeds")
        seeds = normalize_seeds(raw)
        if seeds:
            return seeds
    except Exception:
        pass
    return normalize_seeds(DEFAULT_TABLE_SEEDS)
```

`_extract_from_tables`（L296 到函数尾,含原 price 校验/finalize 块,约 L296-449）整体替换为:

```python
def _extract_from_tables(tables: list, doc_uri: str, seeds: list[dict] | None = None) -> tuple:
    """严格 seed-only 版分类提取(设计 §2/§3)。

    逐表: match_seed 确认 → extract_items_seed(含分类行传播) → 价格校验/反算。
    未匹配表: 零提取;形似数据表(≥4列)记 unmatched_tables 供 UI 建规则。
    续表: 无表头且形似上一命中表 → 继承其 seed/roles(x-band 抗漂移)。
    meta 新键: unmatched_tables[] / matched_seeds{} / orientation_fixed_pages[](透传)。"""
    from scripts.table_classifier import (
        _bboxes_usable,
        _norm_header,
        _roles_x_from_data,
        classify,
        extract_items_seed,
        looks_like_continuation,
        match_seed,
    )

    items: list[dict] = []
    meta: dict = {
        "tables_found": len(tables),
        "goods_tables": 0,
        "continuation_tables": 0,
        "rows_extracted": 0,
        "skipped": {},
        "unmatched_tables": [],
        "matched_seeds": {},
    }
    active = None  # (seed, roles, roles_x, col_count, category_tail) 续表继承上下文

    def _category_tail(raw_items: list, fallback: str | None) -> str | None:
        """本表尾部生效的分类(逆序找最后一个非 None),供跨页/跨表续传。"""
        for it in reversed(raw_items):
            if it.get("category") is not None:
                return it["category"]
        return fallback
    for table in tables:
        rows = table.rows or []
        col_count = max((len(r) for r in rows), default=0)
        hit = match_seed(rows, seeds) if seeds else None
        is_cont = (
            hit is None
            and active is not None
            and looks_like_continuation(
                rows, active[1], active[3], table.cell_bboxes, active[2]
            )
        )
        cat_in = active[4] if active is not None else None  # 上一表尾部分类
        if hit is not None:
            seed, roles, header_rows = hit
            meta["goods_tables"] += 1
            meta["matched_seeds"][seed["display_name"]] = meta["matched_seeds"].get(seed["display_name"], 0) + 1
            roles_x = None
            if _bboxes_usable(rows, table.cell_bboxes):
                roles_x = _roles_x_from_data(rows, table.cell_bboxes, roles, header_rows)
            # 表头重复页: 每页都会 match_seed 命中——initial_category 必须跨表续传,
            # 否则多页清单的分类退化为页内局部(修订I2)
            raw = extract_items_seed(rows, seed, roles, header_rows, table.cell_bboxes, roles_x, initial_category=cat_in)
            active = (seed, roles, roles_x, col_count, _category_tail(raw, cat_in))
        elif is_cont:
            seed, roles, roles_x, _, cat_in = active
            meta["continuation_tables"] += 1
            raw = extract_items_seed(rows, seed, roles, 0, table.cell_bboxes, roles_x, initial_category=cat_in)
            active = (seed, roles, roles_x, col_count, _category_tail(raw, cat_in))
        else:
            ttype, sroles, sroles_x, sheader_rows = classify(rows, None, table.cell_bboxes)
            meta["skipped"][ttype] = meta["skipped"].get(ttype, 0) + 1
            active = None  # 断链:不匹配的表后不继承
            if ttype == "unclassified" and col_count >= 4:
                # 候选数据表但无 seed 确认 → 记详情供 UI 建规则(设计 §1.2)
                header, _hr = __import__("scripts.table_classifier", fromlist=["_collapse_header"])._collapse_header(rows)
                meta["unmatched_tables"].append(
                    {
                        "page": table.page_no,
                        "table_idx": table.table_idx,
                        "title": next(
                            ("".join(c or "" for c in r).strip() for r in rows[:3]
                             if sum(1 for c in r if (c or "").strip()) == 1),
                            "",
                        ),
                        "header": [(c or "").strip() for c in header if (c or "").strip()],
                        "col_count": col_count,
                        "row_count": len(rows),
                    }
                )
            continue

        # 价格校验/finalize(seed 角色: price_unit_raw→unit_price, price_untaxed_raw→price_untaxed;
        # 反算: price_unit 无效且 price_total_raw+qty 可用 → total/qty)
        for r in raw:
            nm = (r["name"] or "").strip()
            if _PURE_NUM.match(nm) or _PURE_NUM_BRACKET.match(nm):
                row = table.rows[r["row_idx"]] if r["row_idx"] < len(table.rows) else []
                for cell_txt in row:
                    c = (cell_txt or "").strip()
                    if c and not _PURE_NUM.match(c) and not _PURE_NUM_BRACKET.match(c):
                        r["name"] = c
                        break
            unit_p, vstatus_u, reason_u = validate_price(r["price_unit_raw"])
            if r.get("price_untaxed_raw"):
                untaxed, vstatus_n, reason_n = validate_price(r["price_untaxed_raw"])
            else:
                untaxed, vstatus_n, reason_n = None, "ok", ""
            # 反算: 单价缺失/异常 → 合价÷工程量(seed 显式 price_total 列,比旧右探更稳)
            if unit_p is None and r.get("price_total_raw"):
                total, _, _ = validate_price(r["price_total_raw"])
                q = parse_qty(r["qty_raw"] or "")
                if total and q and q > 0:
                    unit_p = round(total / q, 2)
                    vstatus_u, reason_u = "ok", "合价/工程量反算"
            if unit_p is None and untaxed is None:
                continue  # 无可用价格:不存噪声行(与旧管线一致)
            vstatus = "needs_review" if "needs_review" in (vstatus_u, vstatus_n) else "ok"
            items.append(
                {
                    "goods_name": r["name"],
                    "spec_model": r["spec"],
                    "tech_params": _extract_tech_params(r["name"]),
                    "category": r.get("category"),
                    "quantity": parse_qty(r["qty_raw"] or ""),
                    "unit": r["unit"],
                    "unit_price": unit_p,
                    "price_untaxed": untaxed,
                    "source_doc_uri": doc_uri,
                    "source_page": table.page_no,
                    "source_bbox": _cell_bbox(table, r["row_idx"], 0),
                    "source_table_idx": table.table_idx,
                    "source_row_idx": r["row_idx"],
                    "confidence": table.mean_confidence,
                    "validation_status": vstatus,
                    "price_reason": reason_u or reason_n,
                }
            )
        meta["rows_extracted"] += len(raw)
    return items, meta
```

> 注意: `_collapse_header` 直接 import 到文件头（与既有 `from scripts.table_classifier import ...` 行合并，加 `_collapse_header`、`_bboxes_usable`、`_norm_header`、`_roles_x_from_data`），上面函数体内的 `__import__` 写法改为直接用已 import 的名字。`_PURE_NUM`/`_PURE_NUM_BRACKET`/`_cell_bbox`/`_extract_tech_params` 为 cli 既有私有助手，保持原位。

- [x] **Step 4: `_process_one_doc`/`run_parse` 换 seeds + parse_status 三态**

`run_parse`（L767）: `keywords = _load_price_keywords()` → `seeds = _load_seeds()`；`_process_one_doc(ch, store, cfg, keywords, ...)` → `... seeds ...`；`_extract_from_tables(tables, doc_uri, keywords)` → `(tables, doc_uri, seeds)`。

`_process_one_doc` 内 parse_status 块（原 L699-706）替换为:

```python
                # 严格 seed-only 三态(设计 §1.2): 0表=no_tables(不算失败);
                # 有表全未命中/首页字段缺失=needs_review;否则 parsed。
                "parse_status": (
                    "no_tables"
                    if not meta["tables_found"]
                    else (
                        "needs_review"
                        if (not meta["goods_tables"] and meta["unmatched_tables"])
                        or (not (items or meta["tables_found"]))
                        or (not project_name and not project_location)
                        else "parsed"
                    )
                ),
```

- [x] **Step 5: 跑全部技能测试确认通过/无回归**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/ -v`
Expected: 全部 passed（test_cli.py 若断言旧 keywords 行为,按新 seeds 语义修断言——断言意图不变,输入换 seed）

- [x] **Step 6: Commit**

```bash
git add skills/public/contract-price-analysis/scripts/cli.py skills/public/contract-price-analysis/tests/test_extract_strict.py
git commit -m "feat(cpa): 严格seed-only管线——unmatched_tables详情+matched_seeds+no_tables状态+反算走seed价列"
```

---

### Task 5: category 落库全链（模型/迁移/聚类/Excel）

**Files:**
- Modify: `skills/public/contract-price-analysis/scripts/models.py:94-99`（CpaItem 加 category）
- Modify: `backend/app/extensions/contract_price/models.py`（CpaItem 同步加）
- Modify: `skills/public/contract-price-analysis/scripts/db.py:18-23`（init_schema 幂等 ALTER）
- Modify: `skills/public/contract-price-analysis/scripts/cli.py`（`_persist_one_doc` item_kwargs + `run_cluster` db_items/samples）
- Modify: `backend/app/extensions/contract_price/schemas.py:37`（ItemOut 加 category）
- Modify: `skills/public/contract-price-analysis/scripts/excel_generator.py:61-84`（分项明细加分类列）
- Create: `skills/public/contract-price-analysis/tests/test_category_pipeline.py`

- [x] **Step 1: 写失败测试**

`skills/public/contract-price-analysis/tests/test_category_pipeline.py`:

```python
"""category 全链: 模型列存在 + init_schema 的幂等 ALTER 语句 + 聚类样本拼category。"""

import inspect

from scripts.models import CpaItem


def test_cpa_item_has_category_column():
    assert "category" in CpaItem.__table__.columns
    assert CpaItem.__table__.columns["category"].nullable


def test_init_schema_alters_existing_tables():
    from scripts import db

    src = inspect.getsource(db.init_schema)
    assert "ADD COLUMN IF NOT EXISTS category" in src


def test_cluster_sample_appends_category():
    """同名货物不同分类必须分簇: 样本文本 = 名称+分类。"""
    from scripts.cli import _cluster_sample_text

    assert _cluster_sample_text("现浇构件钢筋", {"category": "建筑工程"}) != \
           _cluster_sample_text("现浇构件钢筋", {"category": "屋面"})
    assert _cluster_sample_text("钢筋", {}) == "钢筋"
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_category_pipeline.py -v`
Expected: FAIL

- [x] **Step 3: 实现各处**

`scripts/models.py` CpaItem（L94 `spec_model` 之后）加:

```python
    category: Mapped[Optional[str]] = mapped_column(String(300))  # 分类行上下文((一)建筑工程/屋面…)
```

`backend/app/extensions/contract_price/models.py` CpaItem 同位置加同一行（双份镜像）。

`scripts/db.py` 的 `init_schema` 改为:

```python
async def init_schema() -> None:
    """Create cpa_ tables if they do not exist (idempotent), then patch columns
    create_all can't add to pre-existing tables (SQLAlchemy create_all never ALTERs)."""
    from sqlalchemy import text

    from scripts.models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不改既有表: category 是 v3 新增列,老库需显式补(幂等)。
        await conn.execute(
            text("ALTER TABLE cpa_items ADD COLUMN IF NOT EXISTS category VARCHAR(300)")
        )
```

`scripts/cli.py` 新增助手（放 `_build_groups_db` 附近）:

```python
def _cluster_sample_text(goods_name: str, tech_params: dict | None) -> str:
    """聚类样本文本 = 名称 + 分类(同名货物不同分类必须分簇,设计 §1.3)。"""
    cat = ((tech_params or {}).get("category") if isinstance(tech_params, dict) else None) or ""
    return f"{goods_name} {cat}".strip()
```

`run_cluster` 的 `db_items`（L848-860）加 `"category": r.category,`；`samples` 行（L863）改为:

```python
            samples = [(_cluster_sample_text(it["goods_name"], it["tech_params"]), it["tech_params"]) for it in db_items]
```

（`_build_groups_db` 的 `members`/Excel items 继续携带 `category` 键——db_items 原样透传。）

`_persist_one_doc` 的 `item_kwargs`（L553-570）加一行:

```python
                    "category": it.get("category"),
```

`backend/app/extensions/contract_price/schemas.py` `ItemOut`（L41 `goods_name` 后）加:

```python
    category: str | None = None
```

`scripts/excel_generator.py` `_write_items`（L61-84）表头与行加分类列（插在规格型号后，后续列号顺延）:

```python
    headers = ["货物名称", "规格型号", "分类", "技术参数", "单价", "来源合同", "签订日期", "供应商", "是否异常"]
```

```python
            ws.write(row, 0, it.get("goods_name", ""), text_fmt)
            ws.write(row, 1, it.get("spec_model", ""), text_fmt)
            ws.write(row, 2, it.get("category") or "", text_fmt)
            ws.write(row, 3, _stringify_params(it.get("tech_params")), text_fmt)
            _price = it.get("unit_price")
            if _price is None:
                ws.write(row, 4, "待核验", text_fmt)
            else:
                ws.write_number(row, 4, _price, money_fmt)
            ws.write(row, 5, it.get("source_contract_no", ""), text_fmt)
            ws.write(row, 6, it.get("sign_date", ""), text_fmt)
            ws.write(row, 7, it.get("supplier", ""), text_fmt)
            ws.write(row, 8, "是" if is_outlier else "", outlier_fmt if is_outlier else text_fmt)
```

- [x] **Step 4: 存量库一次性迁移（runbook,幂等可重复执行）**

Run: `docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "ALTER TABLE cpa_items ADD COLUMN IF NOT EXISTS category VARCHAR(300);"`
Expected: `ALTER TABLE`

- [x] **Step 5: 跑测试 + excel 测试确认通过**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_category_pipeline.py tests/test_excel_generator.py -v`
Expected: 全部 passed（excel 既有断言若锁定列数,更新为新 9 列）

- [x] **Step 6: Commit**

```bash
git add skills/public/contract-price-analysis/scripts/models.py skills/public/contract-price-analysis/scripts/db.py skills/public/contract-price-analysis/scripts/cli.py skills/public/contract-price-analysis/scripts/excel_generator.py backend/app/extensions/contract_price/models.py backend/app/extensions/contract_price/schemas.py skills/public/contract-price-analysis/tests/test_category_pipeline.py
git commit -m "feat(cpa): category落库全链——双模型+幂等ALTER+聚类样本拼分类+Excel分类列"
```

---

### Task 6: OCR 结果缓存（内容寻址,重解析秒级）

**Files:**
- Modify: `skills/public/contract-price-analysis/scripts/document_parser.py`（to_cache/from_cache + last_pages 透传,后者 Task 8 用）
- Modify: `skills/public/contract-price-analysis/scripts/storage.py`（get/put_ocr_cache）
- Modify: `skills/public/contract-price-analysis/scripts/cli.py`（`_process_one_doc` 缓存读写;`run_parse`+`main`+`--re-ocr`）
- Create: `skills/public/contract-price-analysis/tests/test_ocr_cache.py`

- [x] **Step 1: 写失败测试**

`skills/public/contract-price-analysis/tests/test_ocr_cache.py`:

```python
"""OCR 缓存序列化往返 + 缓存命中跳过 OCR 调用。"""

import json
from types import SimpleNamespace

from scripts.document_parser import TableExtract, from_cache, to_cache


def _tbl(page_no=1, table_idx=0):
    return TableExtract(
        page_no=page_no, table_idx=table_idx, bbox=[0.1, 0.1, 0.9, 0.9],
        rows=[["序号", "品名"], ["1", "盘圆"]],
        cell_bboxes=[[[0, 0, 0, 0], [0, 0, 0, 0]], [[0, 0, 0, 0], [0, 0, 0, 0]]],
        page_preview_b64="", mean_confidence=0.93,
    )


def test_cache_roundtrip_preserves_tables_and_texts():
    tables = [_tbl(), _tbl(page_no=2)]
    page_texts = {1: "合同封面", 2: "含税总价"}
    data = json.loads(json.dumps(to_cache(tables, page_texts)))  # JSON 严进严出
    t2, p2 = from_cache(data)
    assert [(t.page_no, t.table_idx, t.rows, t.mean_confidence) for t in t2] == [
        (t.page_no, t.table_idx, t.rows, t.mean_confidence) for t in tables
    ]
    assert p2 == page_texts
    assert all(t.page_preview_b64 == "" for t in t2)  # preview 不入缓存(单独存PNG)


def test_process_one_doc_cache_hit_skips_ocr(monkeypatch):
    """缓存命中: 不发 HTTP,直接从缓存重建 tables。"""
    import asyncio

    import scripts.cli as cli

    calls = {"ocr": 0}

    async def fake_parse(file_bytes, filename, url, last_pages=0):
        calls["ocr"] += 1
        return [_tbl()], {1: "text"}

    monkeypatch.setattr(cli, "parse_document", fake_parse)

    class FakeStore:
        def __init__(self):
            self.blobs = {}

        def get_ocr_cache(self, key):
            return self.blobs.get(key)

        def put_ocr_cache(self, key, obj):
            self.blobs[key] = obj

        def get(self, key):
            return b"%PDF-fake"

    from scripts.seed_library import DEFAULT_TABLE_SEEDS

    store = FakeStore()
    sem = asyncio.Semaphore(1)
    ch = {"key": "a.pdf", "hash": "abc", "size": 9}
    state = {"docs_processed": 0, "items_extracted": 0, "failed_docs": 0, "done": 0, "processing": set()}
    cfg = SimpleNamespace(minio_bucket="b", ocr_service_url="http://x")
    # 第一遍: OCR 并写缓存
    asyncio.run(cli._process_one_doc(ch, store, cfg, DEFAULT_TABLE_SEEDS, sem, state, None, 1, re_ocr=False))
    assert calls["ocr"] == 1
    assert store.blobs["ocr/abc.json"]
    # 第二遍: 命中缓存,不再 OCR
    state2 = {"docs_processed": 0, "items_extracted": 0, "failed_docs": 0, "done": 0, "processing": set()}
    asyncio.run(cli._process_one_doc(ch, store, cfg, DEFAULT_TABLE_SEEDS, sem, state2, None, 1, re_ocr=False))
    assert calls["ocr"] == 1
    # re_ocr=True: 强制重 OCR
    state3 = {"docs_processed": 0, "items_extracted": 0, "failed_docs": 0, "done": 0, "processing": set()}
    asyncio.run(cli._process_one_doc(ch, store, cfg, DEFAULT_TABLE_SEEDS, sem, state3, None, 1, re_ocr=True))
    assert calls["ocr"] == 2
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_ocr_cache.py -v`
Expected: FAIL `ImportError: cannot import name 'to_cache'` / `AttributeError: ... re_ocr`

- [x] **Step 3: 实现 document_parser 序列化**

`document_parser.py` 追加:

```python
def to_cache(tables: list[TableExtract], page_texts: dict[int, str]) -> dict:
    """OCR 结构化结果的缓存形态(剔 preview b64——预览 PNG 本就单独存 MinIO)。"""
    return {
        "v": 1,
        "page_texts": {str(k): v for k, v in page_texts.items()},
        "tables": [
            {
                "page_no": t.page_no,
                "table_idx": t.table_idx,
                "bbox": t.bbox,
                "rows": t.rows,
                "cell_bboxes": t.cell_bboxes,
                "mean_confidence": t.mean_confidence,
            }
            for t in tables
        ],
    }


def from_cache(data: dict) -> tuple:
    """缓存 → (tables, page_texts)。preview 恒为空串(缓存命中重解析时预览
    PNG 在首解析已落 MinIO,preview_prefix 不变)。"""
    tables = [
        TableExtract(
            page_no=t["page_no"],
            table_idx=t["table_idx"],
            bbox=t.get("bbox", [0, 0, 0, 0]),
            rows=t.get("rows", []),
            cell_bboxes=t.get("cell_bboxes", []),
            page_preview_b64="",
            mean_confidence=float(t.get("mean_confidence", 0.0)),
        )
        for t in data.get("tables", [])
    ]
    page_texts = {int(k): v for k, v in (data.get("page_texts") or {}).items()}
    return tables, page_texts
```

`parse_document` 签名扩一个参数（Task 8 用,一次改完）: `async def parse_document(file_bytes, filename, ocr_service_url, last_pages: int = 0)`，POST form 加 `data={"last_pages": last_pages} if last_pages else None`（httpx: `client.post(url, files=..., data=...)`）。

- [x] **Step 4: 实现 storage 缓存方法**

`storage.py` `ContractStore` 追加:

```python
    def get_ocr_cache(self, key: str) -> dict | None:
        """OCR 结构化缓存;缺失/损坏返回 None(回退全量 OCR,绝不因缓存挂掉)。"""
        try:
            return json.loads(self.get(key))
        except Exception:
            return None

    def put_ocr_cache(self, key: str, obj: dict) -> None:
        self.put_bytes(key, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       content_type="application/json")
```

文件头 import 区加 `import json`。

- [x] **Step 5: cli 接缓存 + re_ocr 参数**

`_process_one_doc` 签名（L644）改为 `..., total_docs: int, re_ocr: bool = False)`；OCR 调用块（L673-674）替换为:

```python
            file_bytes = await asyncio.to_thread(store.get, key)
            cache_key = f"ocr/{ch['hash']}.json"  # 内容寻址:同内容同键,免失效
            cached = None if re_ocr else await asyncio.to_thread(store.get_ocr_cache, cache_key)
            if cached is not None:
                tables, page_texts = from_cache(cached)
                logger.info("Cache hit %s: %d tables (skip OCR)", cache_key, len(tables))
            else:
                tables, page_texts = await parse_document(file_bytes, key, cfg.ocr_service_url)
                await asyncio.to_thread(
                    store.put_ocr_cache, cache_key, to_cache(tables, page_texts)
                )
```

文件头 import 行加 `from scripts.document_parser import from_cache, parse_document, to_cache`。
`run_parse` 签名（L751）`run_parse(trigger="manual", run_id=None, force_key=None, re_ocr=False)`；gather 行（L796）各任务传 `re_ocr=re_ocr`。
`main()`（L1005-1018）: `parser.add_argument("--re-ocr", action="store_true", help="reparse 时强制重 OCR(默认读 MinIO OCR 缓存)")`；parse 分支 `asyncio.run(run_parse(trigger=..., run_id=..., force_key=..., re_ocr=args.re_ocr))`。

- [x] **Step 6: 跑测试确认通过**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_ocr_cache.py tests/test_extract_strict.py -v`
Expected: 全部 passed

- [x] **Step 7: Commit**

```bash
git add skills/public/contract-price-analysis/scripts/document_parser.py skills/public/contract-price-analysis/scripts/storage.py skills/public/contract-price-analysis/scripts/cli.py skills/public/contract-price-analysis/tests/test_ocr_cache.py
git commit -m "feat(cpa): OCR结构化缓存(内容寻址ocr/{sha}.json)+--re-ocr——补规则后重解析秒级"
```

---

### Task 7: reparse 端点 re_ocr 参数

**Files:**
- Modify: `backend/app/extensions/contract_price/routers.py:184-220`（reparse_document）
- Modify: `backend/app/extensions/contract_price/service.py:30-59`（run_pipeline_subprocess 透传）
- Create: `backend/tests/test_contract_price_reparse_reocr.py`

- [x] **Step 1: 写失败测试**

`backend/tests/test_contract_price_reparse_reocr.py`:

```python
"""reparse 端点把 re_ocr 透传到子进程参数。"""

from unittest.mock import patch

from fastapi.testclient import TestClient  # noqa: F401  (按仓库既有 router 测试基建选用)


def test_service_builds_reocr_flag():
    import inspect

    from app.extensions.contract_price import service

    src = inspect.getsource(service.run_pipeline_subprocess)
    assert "re_ocr" in src and '"--re-ocr"' in src
```

（端点级联调放到 Task 17 验收;此处锁服务层契约。）

- [x] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_contract_price_reparse_reocr.py -v`
Expected: FAIL

- [x] **Step 3: 实现**

`service.py` 签名（L30-37）加 `re_ocr: bool = False`；cmd 构造（L58-59）后加:

```python
    if re_ocr:
        cmd += ["--re-ocr"]
```

`routers.py` `reparse_document`（L184-186）签名加查询参数并在 scope 携带:

```python
async def reparse_document(
    doc_id: UUID,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    re_ocr: bool = False,
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
```

docstring 补一行: `"""Re-parse a single document (bypass SHA-256 cache). re_ocr=true 时强制重 OCR;默认读 OCR 缓存只重跑分类+提取(秒级)。"""`

scope 行（L211）改为:

```python
    scope={"mode": "table", "phase": "parse", "started_by": current_user.username, "reparse": key, "re_ocr": re_ocr},
```

background 行（L213）改为:

```python
    background.add_task(service.run_pipeline_subprocess, db, run.id, "table", "manual", "parse", key, re_ocr)
```

- [x] **Step 4: 跑测试 + 后端不回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_contract_price_reparse_reocr.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/extensions/contract_price/routers.py backend/app/extensions/contract_price/service.py backend/tests/test_contract_price_reparse_reocr.py
git commit -m "feat(cpa): reparse端点re_ocr参数透传子进程--re-ocr"
```

---

### Task 8: 合同元数据末页兜底（乙方/签订日期）

**Files:**
- Modify: `mcp-server/ocr-service/server.py:43-57`（/ocr 加 last_pages Form）
- Modify: `mcp-server/ocr-service/ocr_engine.py:146-171`（last_pages 页区间光栅化）
- Modify: `skills/public/contract-price-analysis/scripts/cli.py`（`_process_one_doc` miss 时补 OCR 末页重试）
- Create: `skills/public/contract-price-analysis/tests/test_metadata_fallback.py`

- [x] **Step 1: 写失败测试**

`skills/public/contract-price-analysis/tests/test_metadata_fallback.py`:

```python
"""末页兜底: 前3页字段 miss → 补 OCR 最后2页 → 合并 page_texts 重试。"""

import asyncio
from types import SimpleNamespace

import scripts.cli as cli
from scripts.seed_library import DEFAULT_TABLE_SEEDS


def test_fallback_triggers_only_on_miss(monkeypatch):
    async def fake_parse(file_bytes, filename, url, last_pages=0):
        assert last_pages == 2, "miss 时应请求末2页"
        return [], {99: "乙方：末页建筑公司\n签订日期 2025年6月18日"}

    monkeypatch.setattr(cli, "parse_document", fake_parse)
    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x",
        front_texts={1: "项目名称：某工程"},  # 前页无乙方/日期
    ))
    assert got[3] == "末页建筑公司"   # supplier
    assert got[4] == "2025-06-18"     # sign_date


def test_no_fallback_when_front_pages_hit(monkeypatch):
    async def fail_parse(*a, **k):
        raise AssertionError("字段齐全时不应发起末页 OCR")

    monkeypatch.setattr(cli, "parse_document", fail_parse)
    got = asyncio.run(cli._extract_project_fields_with_fallback(
        b"%PDF", "a.pdf", "http://x",
        front_texts={1: "项目名称：某工程\n乙方：甲公司\n签订日期：2025-06-18"},
    ))
    assert got[3] == "甲公司"
```

- [x] **Step 2: 跑测试确认失败**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_metadata_fallback.py -v`
Expected: FAIL `AttributeError: ... _extract_project_fields_with_fallback`

- [x] **Step 3: ocr-service 支持 last_pages**

`server.py` `/ocr` 签名与调用（L44-57）:

```python
@app.post("/ocr", response_model=OcrResponse)
async def ocr(
    file: UploadFile = File(...),
    text_pages: int = Form(3),
    last_pages: int = Form(0),
) -> OcrResponse:
    """text_pages: 前多少页做整页文字 OCR（默认 3）。
    last_pages: >0 时只 OCR 末 N 页(合同元数据末页兜底;元数据签字页常在末尾)。
    EAI-CUSTOM: geo-sample-bank 需全文语料，POST data 里传 text_pages=999 即全页。"""
    name = (file.filename or "").lower()
    if not name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf is supported in Phase 0")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    try:
        return _get_engine().ocr_pdf_bytes(data, text_pages=text_pages, last_pages=last_pages)
    except Exception as exc:
        logger.exception("OCR failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"ocr failed: {exc!r}") from exc
```

`ocr_engine.py`:

```python
    def ocr_pdf_bytes(self, pdf_bytes: bytes, dpi: int = 200, text_pages: int = 3, last_pages: int = 0) -> OcrResponse:
        pages = None
        page_offset = 0
        if last_pages > 0:
            from pdf2image import pdfinfo_from_bytes

            try:
                total = int(pdfinfo_from_bytes(pdf_bytes)["Pages"])
            except Exception:
                total = 0
            if total > last_pages:
                pages = convert_from_bytes(pdf_bytes, dpi=dpi, first_page=total - last_pages + 1, last_page=total)
                page_offset = total - len(pages)
        if pages is None:
            pages = convert_from_bytes(pdf_bytes, dpi=dpi)
        return self._run(pages, text_pages=text_pages, page_offset=page_offset)
```

`_run` 签名加 `page_offset: int = 0`，`self._page(idx + page_offset, img, ...)`（页号保持全文绝对页码）。

- [x] **Step 4: cli 兜底函数 + 接线**

`cli.py` 新增（`extract_project_fields` import 行旁）:

```python
async def _extract_project_fields_with_fallback(
    file_bytes: bytes, key: str, ocr_url: str, front_texts: dict[int, str]
) -> tuple:
    """元数据提取 + 末页兜底(设计 §3): 前3页正则 miss 乙方/签订日期时,
    补 OCR 末2页重试(签字页常在末尾,补充协议尤甚;仅 miss 触发,成本有界)。"""
    fields = extract_project_fields(front_texts)
    if fields[3] and fields[4]:  # supplier, sign_date 都有 → 不兜底
        return fields
    try:
        _, tail_texts = await parse_document(file_bytes, key, ocr_url, last_pages=2)
    except Exception as exc:
        logger.warning("metadata tail-OCR failed: %s", exc)
        return fields
    merged = dict(front_texts)
    merged.update(tail_texts)
    retry = extract_project_fields(merged)
    # 逐字段择优: 前页已取到的保留,缺的用末页补
    return tuple(f or r for f, r in zip(fields, retry))
```

`_process_one_doc` 内（原 L676）:

```python
            project_name, project_location, contract_no, supplier, sign_date = (
                await _extract_project_fields_with_fallback(file_bytes, key, cfg.ocr_service_url, page_texts)
            )
```

- [x] **Step 5: 跑测试确认通过**

Run: `cd skills/public/contract-price-analysis && python -m pytest tests/test_metadata_fallback.py tests/test_ocr_cache.py -v`
Expected: 全部 passed

- [x] **Step 6: 重建 ocr 容器 + 冒烟**

```bash
# 按仓库 compose 叠加重建(记忆: up -d 必须带全 -f)
docker compose -p eai-docker -f docker/docker-compose.base.yaml -f docker/docker-compose.dev.yaml up -d --build ocr
curl -s http://localhost:8010/health
```

Expected: `{"status":"ok","service":"eai-flow-ocr"}`

- [x] **Step 7: Commit**

```bash
git add mcp-server/ocr-service/server.py mcp-server/ocr-service/ocr_engine.py skills/public/contract-price-analysis/scripts/cli.py skills/public/contract-price-analysis/tests/test_metadata_fallback.py
git commit -m "feat(cpa): 元数据末页兜底——ocr-service last_pages区间+乙方/签订日期miss补OCR末2页"
```

---

## P2 OCR 方向归一化

### Task 9: 页级方向试探（0表页 ±90° 取优）

**Files:**
- Modify: `mcp-server/ocr-service/schemas.py`（OcrResponse/PageResult 加字段）
- Modify: `mcp-server/ocr-service/ocr_engine.py`（`_run`/`_page` 方向试探）
- ~~Create: `mcp-server/ocr-service/test_rotation.py`~~ (已裁撤:旋转实证由会话探针+bug-1760645落地数据承载,引擎级回归由137页table_count==91基准守护)

- [x] **Step 1: 实证先行（容器内跑通再写引擎代码）**

本计划 Task 前已实测（会话内 2026-09-17）: 补充协议 p2 顺时针 90° 后 `tables=1 rows=13`、逆时针数字垃圾。把 `.wolf/tmp/cpa-samples/rot_test2.py` 的断言固化为测试: 将该样例 PDF 拷入容器跑 `rot_test2.py`,确认 CW tables>=1 且表头含 "物资名称"。（验收时用 `docker cp` + `docker exec`,不过 CI——ONNX 模型 + 真实扫描件属环境级测试,记录到 Task 17 runbook 手动执行。）

- [x] **Step 2: schemas 加字段**

`mcp-server/ocr-service/schemas.py` 的 `OcrResponse` 类体加一行、`PageResult` 加一行:

```python
class PageResult(BaseModel):
    # ... 既有字段 ...
    orientation: str | None = None  # None|"cw90"|"ccw90" 该页OCR所用方向(纠偏后)
```

```python
class OcrResponse(BaseModel):
    # ... 既有字段 ...
    orientation_fixed_pages: list[int] = []  # 被纠偏的页号(1-based,供 parse_meta 透传)
```

（字段名按 schemas.py 既有样式对齐——pydantic BaseModel 追加带默认值字段是安全的。）

- [x] **Step 3: 引擎方向试探**

`ocr_engine.py` `_run`（L159-171）与 `_page`（L173-210）改造:

```python
    def _run(self, pages: list[Image.Image], text_pages: int = 3, page_offset: int = 0) -> OcrResponse:
        self._ensure()
        started = time.monotonic()
        out = []
        fixed: list[int] = []
        for i, img in enumerate(pages, start=1):
            pg = self._page(i + page_offset, img, with_text=i <= text_pages)  # 窗口相对门控(绝对门控会掐死Task8尾页兜底)
            if pg.orientation is not None:
                fixed.append(pg.page_no)
            out.append(pg)
        return OcrResponse(
            pages=out,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            engine="pdf2image+rapid-layout+rapid-table+rapidocr-onnxruntime",
            table_count=sum(len(p.tables) for p in out),
            orientation_fixed_pages=fixed,
        )
```

`_page` 内,layout 结果为空(0 regions 或 0 tables)时追加试探块（在 `text = ""` 之前）:

```python
        if not tables:
            rotated = self._try_rotations(arr)
            if rotated is not None:
                tables_r, img_r, orient = rotated
                # 纠偏页: bbox/preview/页尺寸全部基于旋转后图像(溯源对齐的前提)
                arr2 = np.array(img_r.convert("RGB"))
                h2, w2 = arr2.shape[:2]
                text = ""
                if with_text:
                    try:
                        res, _ = self._ocr(arr2)
                        text = "\n".join(str(r[1]) for r in res) if res else ""
                    except Exception:
                        text = ""
                return PageResult(
                    page_no=page_no, page_width=w2, page_height=h2,
                    tables=tables_r, preview_png_b64=_png_b64(img_r),
                    text=text, orientation=orient,
                )
```

新增方法:

```python
    def _try_rotations(self, arr: np.ndarray) -> tuple[list[Table], Image.Image, str] | None:
        """0表页的方向试探(设计 §3): ±90° 各跑一次 layout,只有转出了 table 区域
        的方向才继续 table+OCR;两方向都出区域时取 (表数, 平均置信度) 高者。
        成本: 触发页 +2 次 layout(廉价模型);正常竖版页 layout 不出 table 区即止。"""
        best: tuple[int, float, list[Table], Image.Image, str] | None = None
        for orient, angle in (("cw90", -90), ("ccw90", 90)):
            img_r = Image.fromarray(arr).rotate(angle, expand=True)
            arr_r = np.array(img_r.convert("RGB"))
            h, w = arr_r.shape[:2]
            try:
                lout = self._layout(arr_r)
            except Exception:
                continue
            tables: list[Table] = []
            if lout is not None:
                cns = list(getattr(lout, "class_names", []) or [])
                for box, cn in zip(lout.boxes, cns):
                    if "table" not in str(cn).lower():
                        continue
                    t = self._table_region(arr_r, box, w, h)
                    if t is not None:
                        tables.append(t)
            if not tables:
                continue
            score = (len(tables), float(np.mean([t.mean_confidence for t in tables])))
            if best is None or score > best[0:2]:
                best = (score[0], score[1], tables, img_r, orient)
        if best is None:
            return None
        return best[2], best[3], best[4]
```

- [x] **Step 4: cli 透传 orientation_fixed_pages**

`parse_document` 改为返回三元组 `(tables, page_texts, orientation_fixed_pages)`（HTTP 路径取 `data.get("orientation_fixed_pages", [])`;缓存路径由 to_cache 携带）:

```python
# document_parser.to_cache 签名: to_cache(tables, page_texts, orientation_fixed=()) -> dict
#   序列化体加 "orientation_fixed_pages": list(orientation_fixed)
# document_parser.from_cache 返回: (tables, page_texts, data.get("orientation_fixed_pages", []))
# parse_document 返回: (tables, page_texts, data.get("orientation_fixed_pages", []))
```

`scripts/cli.py`:

```python
            if cached is not None:
                tables, page_texts, orient_fixed = from_cache(cached)
                logger.info("Cache hit %s: %d tables (skip OCR)", cache_key, len(tables))
            else:
                tables, page_texts, orient_fixed = await parse_document(file_bytes, key, cfg.ocr_service_url)
                await asyncio.to_thread(
                    store.put_ocr_cache, cache_key, to_cache(tables, page_texts, orient_fixed)
                )
```

`_extract_from_tables` 返回后接一行（`_process_one_doc` 内）:

```python
            meta["orientation_fixed_pages"] = orient_fixed or []
```

同步更新 Task 6/8 测试的解包（`fake_parse` 返回三元组;`from_cache` 断言三元组）。

- [x] **Step 5: 重建容器 + 成本基准**

```bash
docker compose -p eai-docker -f docker/docker-compose.base.yaml -f docker/docker-compose.dev.yaml up -d --build ocr
# 成本基准(设计 §3: 正常文档耗时增幅 <10%):
time curl -s -X POST http://localhost:8010/ocr -F "file=@temp/房建工程（桂北数据中心）专业分包合同-盖章.pdf" -F "text_pages=3" -o /tmp/base137.json
```

记录耗时对比 Task 17 汇总表；补充协议样例复跑确认 p2/p3 出表（`orientation_fixed_pages == [2, 3]`）。

- [x] **Step 6: Commit**

```bash
git add mcp-server/ocr-service/schemas.py mcp-server/ocr-service/ocr_engine.py skills/public/contract-price-analysis/scripts/document_parser.py skills/public/contract-price-analysis/scripts/cli.py
git commit -m "feat(ocr): 页级方向归一化——0表页±90°试探取优+orientation_fixed_pages透传parse_meta"
```

---

## P3 配置 tab 前端

### Task 10: 类型 + SeedEditorDrawer 组件

**Files:**
- Modify: `frontend/src/extensions/contract-price/types.ts`（TableSeed/CpaConfig）
- Create: `frontend/src/extensions/contract-price/components/SeedEditorDrawer.tsx`

- [x] **Step 1: 类型**

`types.ts` 的 `CpaConfig`（L108-115）替换为:

```typescript
/** Seed 定位规则(与后端 ConfigOut.table_seeds 同构;锚点=归一化子串)。 */
export interface TableSeed {
  id: string;
  display_name: string;
  title_keywords: string[];
  columns: {
    name: string[];
    spec: string[];
    qty: string[];
    unit: string[];
    price_unit: string[];
    price_total: string[];
    price_untaxed: string[];
  };
  exclude?: Record<string, string[]>;
  source?: string | null;
}

export interface CpaConfig {
  parse_mode: string;
  cluster_eps: number;
  cluster_min_samples: number;
  scheduled_enabled: boolean;
  schedule_cron: string | null;
  price_table_keywords: string[];
  table_seeds: TableSeed[];
}

/** 未匹配表详情(来自 parse_meta.unmatched_tables)。 */
export interface UnmatchedTable {
  page: number;
  table_idx: number;
  title: string;
  header: string[];
  col_count: number;
  row_count: number;
}
```

- [x] **Step 2: SeedEditorDrawer 完整组件**

`frontend/src/extensions/contract-price/components/SeedEditorDrawer.tsx`（新文件）:

```tsx
"use client";

/** Seed 规则编辑抽屉: 7 角色锚点编辑(候选=OCR 表头单元格 + 自由输入)。
 * 两个入口共用: 配置tab新建/编辑 + 合同解析tab未匹配表"生成规则草稿"。 */

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TableSeed } from "@/extensions/contract-price/types";

export const SEED_ROLES = [
  { key: "name", label: "货物名称列", required: true },
  { key: "spec", label: "规格/参数列", required: false },
  { key: "qty", label: "数量列", required: false },
  { key: "unit", label: "单位列", required: false },
  { key: "price_unit", label: "含税单价列", required: true },
  { key: "price_total", label: "合价列", required: false },
  { key: "price_untaxed", label: "不含税单价列", required: false },
] as const;

export type SeedDraft = TableSeed;

export function emptySeed(): SeedDraft {
  return {
    id: "",
    display_name: "",
    title_keywords: [],
    columns: { name: [], spec: [], qty: [], unit: [], price_unit: [], price_total: [], price_untaxed: [] },
    exclude: { price_unit: ["不含税"] },
    source: null,
  };
}

/** 草稿建议: 内置 token 优先级表对表头做一次性子串映射(确定性,无后端往返)。 */
const DRAFT_TOKENS: Record<string, string[]> = {
  name: ["项目名称", "品名", "物资名称", "货物名称", "名称", "材质"],
  spec: ["规格型号", "材质规格", "规格", "材质", "参数"],
  qty: ["工程量", "暂定数量", "调整数量", "数量"],
  unit: ["计量单位", "单位"],
  price_unit: ["含税单价", "综合单价", "含税落地单价", "调整后单价"],
  price_total: ["含税合价", "含税总价", "总金额", "调整后合价"],
  price_untaxed: ["不含税单价"],
};

export function draftFromHeader(headerCells: string[], title = ""): SeedDraft {
  const seed = emptySeed();
  seed.display_name = title || "新表格规则";
  const used = new Set<number>();
  for (const { key } of SEED_ROLES) {
    for (const token of DRAFT_TOKENS[key] ?? []) {
      const ci = headerCells.findIndex((h, i) => !used.has(i) && h && h.includes(token) && !(key === "price_unit" && h.includes("不含税")));
      if (ci >= 0) {
        seed.columns[key] = [headerCells[ci]];
        used.add(ci);
        break;
      }
    }
  }
  return seed;
}

interface Props {
  open: boolean;
  seed: SeedDraft | null;
  headerCells?: string[]; // 有值=从未匹配表起草:角色下拉候选为这些表头
  saving?: boolean;
  onClose: () => void;
  onSave: (seed: SeedDraft) => void;
}

export function SeedEditorDrawer({ open, seed, headerCells, saving, onClose, onSave }: Props) {
  const [draft, setDraft] = useState<SeedDraft | null>(seed);

  useEffect(() => setDraft(seed), [seed]);

  const candidates = useMemo(
    () => Array.from(new Set([...(headerCells ?? []), ...(draft ? Object.values(draft.columns).flat() : [])])).filter(Boolean),
    [headerCells, draft],
  );
  if (!open || !draft) return null;

  const set = (patch: Partial<SeedDraft>) => setDraft({ ...draft, ...patch });
  const setCol = (role: string, text: string) =>
    set({ columns: { ...draft.columns, [role]: text.split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean) } });

  const valid = draft.id.trim() && draft.display_name.trim() && draft.columns.name.length > 0 &&
    (draft.columns.price_unit.length > 0 || draft.columns.price_total.length > 0);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-[520px] max-w-[92vw] overflow-y-auto border-l bg-background p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">{seed?.id ? "编辑定位规则" : "新建定位规则"}</h2>
          <Button size="icon" variant="ghost" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm font-medium">规则 ID *</label>
              <Input value={draft.id} disabled={!!seed?.id} placeholder="如 gcl-qd"
                onChange={(e) => set({ id: e.target.value })} />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">规则名称 *</label>
              <Input value={draft.display_name} placeholder="如 工程量清单计价表"
                onChange={(e) => set({ display_name: e.target.value })} />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium">表名关键词（逗号分隔,仅用于多规则消歧）</label>
            <Input value={draft.title_keywords.join("，")}
              placeholder="工程量清单，清单计价"
              onChange={(e) => set({ title_keywords: e.target.value.split(/[,，\n]/).map((s) => s.trim()).filter(Boolean) })} />
          </div>

          <div className="rounded-lg border p-3">
            <div className="mb-2 text-sm font-medium">列锚点（子串匹配;多个用逗号分隔）</div>
            <div className="space-y-2">
              {SEED_ROLES.map(({ key, label, required }) => (
                <div key={key} className="grid grid-cols-[110px_1fr] items-center gap-2">
                  <label className="text-xs text-muted-foreground">
                    {label}{required ? " *" : ""}
                  </label>
                  {headerCells && headerCells.length > 0 ? (
                    <Select value={draft.columns[key][0] ?? ""} onValueChange={(v) => setCol(key, v)}>
                      <SelectTrigger className="h-8"><SelectValue placeholder="选表头列" /></SelectTrigger>
                      <SelectContent>
                        {candidates.map((h) => <SelectItem key={h} value={h}>{h}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input className="h-8" value={draft.columns[key].join("，")}
                      onChange={(e) => setCol(key, e.target.value)} />
                  )}
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              锚点按归一化子串匹配（忽略空格/（…）括注/全半角）。「不含税」列自动排除出含税单价。
            </p>
          </div>
        </div>

        <div className="mt-6 flex items-center gap-3">
          <Button disabled={!valid || saving} onClick={() => onSave(draft)}>
            {saving ? "保存中…" : "保存规则"}
          </Button>
          <Button variant="ghost" onClick={onClose}>取消</Button>
          {!valid && <span className="text-xs text-muted-foreground">需规则ID、名称、货物名称列、至少一个价格列</span>}
        </div>
      </div>
    </div>
  );
}
```

- [x] **Step 3: typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: 无新错误（该组件尚无人引用,允许未使用导出）

- [x] **Step 4: Commit**

```bash
git add frontend/src/extensions/contract-price/types.ts frontend/src/extensions/contract-price/components/SeedEditorDrawer.tsx
git commit -m "feat(cpa-ui): TableSeed类型+SeedEditorDrawer(7角色锚点编辑+草稿建议+未匹配表起草入口)"
```

---

### Task 11: SeedRulesCard + SettingsView 重建

**Files:**
- Create: `frontend/src/extensions/contract-price/components/SeedRulesCard.tsx`
- Modify: `frontend/src/extensions/contract-price/components/SettingsView.tsx`（整文件重写）

- [x] **Step 1: SeedRulesCard 完整组件**

```tsx
"use client";

/** Seed 规则卡片列表: 展示/新建/编辑/删除 + 命中统计(parse_meta.matched_seeds 聚合)。 */

import { Pencil, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SeedEditorDrawer, SeedDraft, emptySeed } from "@/extensions/contract-price/components/SeedEditorDrawer";
import { useDocuments } from "@/extensions/contract-price/hooks";
import type { CpaDocument, TableSeed } from "@/extensions/contract-price/types";
import { useMemo, useState } from "react";

interface Props {
  seeds: TableSeed[];
  onChange: (seeds: TableSeed[]) => void;
  saving?: boolean;
}

export function SeedRulesCard({ seeds, onChange, saving }: Props) {
  const [editing, setEditing] = useState<SeedDraft | null>(null);
  const { data } = useDocuments({ limit: 200 });
  // 命中统计: 聚合各文档 parse_meta.matched_seeds(seed名→表数)
  const hits = useMemo(() => {
    const acc: Record<string, number> = {};
    for (const d of (data?.items ?? []) as CpaDocument[]) {
      const ms = (d.parse_meta as { matched_seeds?: Record<string, number> } | null)?.matched_seeds;
      for (const [k, v] of Object.entries(ms ?? {})) acc[k] = (acc[k] ?? 0) + (v ?? 0);
    }
    return acc;
  }, [data]);

  const save = (s: SeedDraft) => {
    const exists = seeds.some((x) => x.id === s.id);
    onChange(exists ? seeds.map((x) => (x.id === s.id ? s : x)) : [...seeds, s]);
    setEditing(null);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>表格定位规则（Seed）</CardTitle>
            <CardDescription>
              解析时按规则定位分项价格表并锚定列;未匹配任何规则的表不提取,可在「合同解析」页为其新建规则后重解析。
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setEditing(emptySeed())}>
            <Plus className="h-4 w-4" /> 新建规则
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {seeds.map((s) => (
          <div key={s.id} className="flex items-center justify-between rounded-lg border p-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium">{s.display_name}</span>
                {hits[s.display_name] ? (
                  <Badge variant="secondary" className="shrink-0">命中 {hits[s.display_name]} 表</Badge>
                ) : (
                  <Badge variant="outline" className="shrink-0 text-muted-foreground">未命中</Badge>
                )}
              </div>
              <div className="mt-1 truncate text-xs text-muted-foreground">
                {[s.columns.name, s.columns.price_unit, s.columns.price_total].flat().filter(Boolean).join(" / ")}
                {s.source ? ` · ${s.source}` : ""}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button size="icon" variant="ghost" onClick={() => setEditing(s)}><Pencil className="h-4 w-4" /></Button>
              <Button size="icon" variant="ghost" className="text-destructive"
                onClick={() => onChange(seeds.filter((x) => x.id !== s.id))}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
        {seeds.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">暂无规则——解析将无法提取任何表格,请新建或保留内置库。</p>
        )}
      </CardContent>
      <SeedEditorDrawer
        open={editing !== null}
        seed={editing}
        saving={saving}
        onClose={() => setEditing(null)}
        onSave={save}
      />
    </Card>
  );
}
```

- [x] **Step 2: SettingsView 重写（整文件替换）**

```tsx
"use client";

/** 配置页 v3: seed 规则库(主) + 聚类高级参数(折叠) + 定时任务。
 *  移除: 解析模式(v2 已废弃单一 OCR 路径)与货物表名关键字(被 seed 库取代)。
 *  dirty 跟踪 + 保存 clamp + toast 自动消隐。 */

import { PackageSearch, Save } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/extensions/contract-price/components/PageHeader";
import { SeedRulesCard } from "@/extensions/contract-price/components/SeedRulesCard";
import { useConfig, useUpdateConfig } from "@/extensions/contract-price/hooks";
import type { CpaConfig } from "@/extensions/contract-price/types";

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function SettingsView() {
  const { data, isLoading } = useConfig();
  const updateConfig = useUpdateConfig();
  const [form, setForm] = useState<CpaConfig | null>(null);
  const [dirty, setDirty] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    if (data && !form) setForm({ ...data, table_seeds: data.table_seeds ?? [] });
  }, [data, form]);

  if (isLoading || !form) {
    return (
      <div className="p-8">
        <PageHeader title="配置" description="表格定位规则与解析参数" icon={<PackageSearch className="h-4 w-4" />} />
        <Card className="mt-6"><CardContent className="p-6"><div className="h-40 animate-pulse rounded bg-muted" /></CardContent></Card>
      </div>
    );
  }

  const set = <K extends keyof CpaConfig>(key: K, value: CpaConfig[K]) => {
    setForm((f) => (f ? { ...f, [key]: value } : f));
    setDirty(true);
  };

  const save = () => {
    if (!form) return;
    updateConfig.mutate(
      {
        ...form,
        cluster_eps: clamp(Number(form.cluster_eps) || 0.6, 0.1, 1.0),
        cluster_min_samples: clamp(Math.round(Number(form.cluster_min_samples) || 2), 1, 10),
      },
      { onSuccess: () => setDirty(false) },
    );
  };

  return (
    <div className="space-y-6 p-8">
      <PageHeader title="配置" description="表格定位规则与解析参数（修改后下次解析生效）" icon={<PackageSearch className="h-4 w-4" />} />

      <SeedRulesCard seeds={form.table_seeds} onChange={(s) => set("table_seeds", s)} saving={updateConfig.isPending} />

      <Card>
        <CardHeader>
          <CardTitle>定时任务</CardTitle>
          <CardDescription>启用后按 cron 表达式自动增量解析。</CardDescription>
        </CardHeader>
        <CardContent className="grid max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" className="accent-primary" checked={form.scheduled_enabled}
              onChange={(e) => set("scheduled_enabled", e.target.checked)} />
            启用定时解析
          </label>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">Cron 表达式</label>
            <Input value={form.schedule_cron ?? ""} placeholder="例如：0 2 * * *（每天 02:00）"
              onChange={(e) => set("schedule_cron", e.target.value || null)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="cursor-pointer select-none" onClick={() => setShowAdvanced((v) => !v)}>
          <CardTitle className="text-base">高级：聚类参数</CardTitle>
          <CardDescription>eps 越小归并越严格;一般无需调整。</CardDescription>
        </CardHeader>
        {showAdvanced && (
          <CardContent className="grid max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">聚类 eps（0.1–1.0）</label>
              <Input type="number" step="0.05" value={form.cluster_eps}
                onChange={(e) => set("cluster_eps", Number(e.target.value))} />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">最小成簇样本数（1–10）</label>
              <Input type="number" value={form.cluster_min_samples}
                onChange={(e) => set("cluster_min_samples", Number(e.target.value))} />
            </div>
          </CardContent>
        )}
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={updateConfig.isPending || !dirty}>
          <Save className="h-4 w-4" />
          {updateConfig.isPending ? "保存中…" : "保存配置"}
        </Button>
        {dirty && <span className="text-sm text-amber-600">有未保存修改</span>}
        {updateConfig.isSuccess && !dirty && <span className="text-sm text-success">已保存</span>}
        {updateConfig.isError ? (
          <span className="text-sm text-destructive">保存失败：{(updateConfig.error).message}</span>
        ) : null}
      </div>
    </div>
  );
}
```

- [x] **Step 3: typecheck + lint + 冒烟**

Run: `cd frontend && pnpm typecheck && pnpm lint`
Expected: 无新错误（`parse_mode` 仍留在 CpaConfig 类型——后端字段还在,仅 UI 不再暴露）

浏览器冒烟（dev 已在 :3000）: 打开 `http://localhost:3000/contract-price/settings`，确认 6 条内置 seed 卡片可见、新建/编辑抽屉可开、dirty 提示出现、保存后消失。

- [x] **Step 4: Commit**

```bash
git add frontend/src/extensions/contract-price/components/SeedRulesCard.tsx frontend/src/extensions/contract-price/components/SettingsView.tsx
git commit -m "feat(cpa-ui): 配置tab重建——SeedRulesCard+命中统计+移除解析模式死控件+dirty/clamp"
```

---

## P4 合同解析 + 分项校验 tab

### Task 12: ContractsView 新状态 + 未匹配表抽屉闭环

**Files:**
- Create: `frontend/src/extensions/contract-price/components/UnmatchedTablesDrawer.tsx`
- Modify: `frontend/src/extensions/contract-price/components/ContractsView.tsx`（docStage L51-67、状态单元格 L631-633、reparse 按钮 L636-660 传 re_ocr=false）
- Modify: `frontend/src/extensions/contract-price/hooks.ts`（useReparseDocument 带 re_ocr）

- [x] **Step 1: UnmatchedTablesDrawer 完整组件**

```tsx
"use client";

/** 未匹配表抽屉: 逐表展示页码/表名/OCR表头 → "生成规则草稿"(打开 SeedEditorDrawer)
 *  → 保存规则 → "重解析本文档"(走 OCR 缓存,秒级)。 */

import { FileWarning } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  SeedEditorDrawer,
  SeedDraft,
  draftFromHeader,
} from "@/extensions/contract-price/components/SeedEditorDrawer";
import { X } from "lucide-react";
import type { UnmatchedTable } from "@/extensions/contract-price/types";

interface Props {
  open: boolean;
  fileName: string;
  tables: UnmatchedTable[];
  onClose: () => void;
  onCreateSeed: (seed: SeedDraft) => void;   // 保存规则(上层写入 config)
  onReparse: () => void;                      // 重解析本文档(缓存路径)
  reparsePending?: boolean;
}

export function UnmatchedTablesDrawer({ open, fileName, tables, onClose, onCreateSeed, onReparse, reparsePending }: Props) {
  const [draft, setDraft] = useState<{ seed: SeedDraft; header: string[] } | null>(null);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div className="h-full w-[560px] max-w-[94vw] overflow-y-auto border-l bg-background p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileWarning className="h-5 w-5 text-amber-600" />
            <div>
              <h2 className="text-lg font-bold">未识别的表格（{tables.length}）</h2>
              <p className="text-xs text-muted-foreground">{fileName} · 与任何定位规则都不匹配,未提取</p>
            </div>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>

        <div className="space-y-3">
          {tables.map((t, i) => (
            <div key={`${t.page}-${t.table_idx}`} className="rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium">
                  第 {t.page} 页 · 表 {t.table_idx + 1}
                  {t.title ? <span className="ml-2 text-muted-foreground">{t.title}</span> : null}
                  <span className="ml-2 text-xs text-muted-foreground">{t.row_count}行×{t.col_count}列</span>
                </div>
                <Button size="sm" variant="outline"
                  onClick={() => setDraft({ seed: draftFromHeader(t.header, t.title), header: t.header })}>
                  生成规则草稿
                </Button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {t.header.map((h, hi) => (
                  <span key={hi} className="rounded bg-muted px-1.5 py-0.5 text-xs">{h}</span>
                ))}
              </div>
            </div>
          ))}
          {tables.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">没有未识别的表格。</p>
          )}
        </div>

        <div className="mt-6 border-t pt-4">
          <p className="mb-2 text-xs text-muted-foreground">为新表保存定位规则后,重解析本文档即可提取（OCR 缓存生效,秒级完成）。</p>
          <Button onClick={onReparse} disabled={reparsePending || tables.length > 0}>
            {reparsePending ? "启动中…" : "重解析本文档"}
          </Button>
          {tables.length > 0 && (
            <span className="ml-2 text-xs text-muted-foreground">（先为上方表格保存规则）</span>
          )}
        </div>
      </div>

      <SeedEditorDrawer
        open={draft !== null}
        seed={draft?.seed ?? null}
        headerCells={draft?.header}
        onClose={() => setDraft(null)}
        onSave={(s) => { onCreateSeed(s); setDraft(null); }}
      />
    </div>
  );
}
```

- [x] **Step 2: ContractsView 集成（三处精确编辑）**

(a) docStage（L51-67）在 `已解析` 返回前插入两个新状态:

```typescript
  if (doc.parse_status === "no_tables")
    return { label: "无价格表", tone: "text-muted-foreground", pending: false };
  if (doc.parse_status === "needs_review")
    return { label: "待人工核验", tone: "text-amber-600", pending: false };
```

（放在 `parsing` 判断之后、默认 `已解析` 之前。）

(b) 状态单元格（原 `<td className="px-6 py-4"><span className={stage.tone}>{stage.label}</span></td>`，L631-633）替换为（未识别徽章 + 打开抽屉）:

```tsx
                    <td className="px-6 py-4">
                      <div className="flex flex-col items-start gap-1">
                        <span className={stage.tone}>{stage.label}</span>
                        {(meta?.unmatched_tables?.length ?? 0) > 0 && (
                          <button
                            className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/5 px-2 py-0.5 text-xs text-amber-600 hover:bg-amber-500/10"
                            onClick={() => {
                              setUnmatchedDoc({ id: doc.id, name: doc.file_name, tables: meta!.unmatched_tables! });
                            }}
                          >
                            ⚠ {meta!.unmatched_tables!.length} 张表未识别
                          </button>
                        )}
                      </div>
                    </td>
```

(c) 组件顶部（`const reparse = useReparseDocument();` 附近）加状态与渲染,且行内 meta 类型声明（L557-563）加键:

```tsx
  const [unmatchedDoc, setUnmatchedDoc] = useState<
    { id: string; name: string; tables: UnmatchedTable[] } | null
  >(null);
```

meta 局部类型（L557 起的 inline 类型）加:

```typescript
                  unmatched_tables?: UnmatchedTable[];
                  matched_seeds?: Record<string, number>;
```

健康度副行（`{meta ? \`${meta.goods_tables ?? 0}货/...\` : "—"}`，L573-577）后追加命中规则名:

```tsx
                          {meta?.matched_seeds && Object.keys(meta.matched_seeds).length > 0 && (
                            <>
                              <span className="mx-1 opacity-40">·</span>
                              {Object.keys(meta.matched_seeds).join("/")}
                            </>
                          )}
```

文件尾部（组件 return 根内最后）挂抽屉,并写规则到 config:

```tsx
      <UnmatchedTablesDrawer
        open={unmatchedDoc !== null}
        fileName={unmatchedDoc?.name ?? ""}
        tables={unmatchedDoc?.tables ?? []}
        reparsePending={reparse.isPending}
        onClose={() => setUnmatchedDoc(null)}
        onCreateSeed={(seed) => {
          // 追加到 config.table_seeds 并保存(复用 config hooks)
          const next = { ...(configQuery.data as CpaConfig | undefined) };
          if (!next) return;
          const seeds = next.table_seeds ?? [];
          updateConfig.mutate(
            { ...next, table_seeds: seeds.some((s) => s.id === seed.id) ? seeds.map((s) => (s.id === seed.id ? seed : s)) : [...seeds, seed] },
            { onSuccess: () => setNotice(`已保存定位规则「${seed.display_name}」`) },
          );
        }}
        onReparse={() => {
          if (!unmatchedDoc) return;
          reparse.mutate(unmatchedDoc.id, {
            onSuccess: () => {
              setNotice("已启动重解析（读 OCR 缓存,秒级）。刷新后查看提取结果。");
              setUnmatchedDoc(null);
            },
          });
        }}
      />
```

需要的 import 补充: `UnmatchedTablesDrawer`、`SeedDraft`、`UnmatchedTable`、`CpaConfig` 类型与 `useConfig, useUpdateConfig`（hooks 文件已有,补 import 行）。

(d) `hooks.ts` 的 `useReparseDocument`（找到该 mutation）请求 URL 追加查询参数:

```typescript
// mutationFn 内,原 POST /documents/{id}/reparse 改为:
const { data } = await api.post(`/documents/${id}/reparse?re_ocr=false`);
```

（默认 false=走缓存;UI 的行内"重新解析"按钮 title 文案同步改为「重新解析(读OCR缓存,秒级)」。）

- [x] **Step 3: typecheck + 冒烟**

Run: `cd frontend && pnpm typecheck`
浏览器: 上传一份测试 PDF（或对着现有桂北文档人工把某条 seed 改名）→ 解析 → 观察徽章/抽屉闭环。

- [x] **Step 4: Commit**

```bash
git add frontend/src/extensions/contract-price/components/UnmatchedTablesDrawer.tsx frontend/src/extensions/contract-price/components/ContractsView.tsx frontend/src/extensions/contract-price/hooks.ts
git commit -m "feat(cpa-ui): 合同解析tab——待人工核验/无价格表状态+未识别表抽屉→建规则→重解析闭环"
```

---

### Task 13: ItemsView 分类列 + 筛选

**Files:**
- Modify: `frontend/src/extensions/contract-price/components/ItemsView.tsx`（表头 L542-552、行体、展开区、筛选区）

- [x] **Step 1: 表头加分类列（L543 规格列后）**

```tsx
                      <TableHead className="whitespace-nowrap">规格</TableHead>
                      <TableHead className="whitespace-nowrap">分类</TableHead>
```

- [x] **Step 2: 行体加分类单元格（规格单元格后,同样式: 无值显示 —）**

规格 `<td>` 之后插入:

```tsx
                                  <td className="px-4 py-3 align-middle">
                                    {item.category || "—"}
                                  </td>
```

- [x] **Step 3: 展开区加分类行（DetailField 列表内,规格后）**

```tsx
                        <DetailField label="分类" value={item.category} />
```

- [x] **Step 4: 筛选下拉（全部合同/全部任务旁）加分类筛选**

筛选 state 区（L186-191 附近）加:

```tsx
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
```

下拉（复制"全部任务"Select 结构）:

```tsx
                <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                  <SelectTrigger className="w-[160px]"><SelectValue placeholder="全部分类" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部分类</SelectItem>
                    {categoryOptions.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
```

`categoryOptions` 来自当前页 items 去重（客户端过滤,后端不加参数——分页内过滤够用,YAGNI）:

```tsx
  const categoryOptions = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((i) => i.category).filter(Boolean) as string[])).sort(),
    [data],
  );
```

行过滤在现有 `filtered` memo 里追加:

```tsx
    .filter((it) => categoryFilter === "all" || it.category === categoryFilter);
```

`types.ts` 的 `CpaItem` 加 `category: string | null;`。

- [x] **Step 5: typecheck + 冒烟**

Run: `cd frontend && pnpm typecheck && pnpm lint`

- [x] **Step 6: Commit**

```bash
git add frontend/src/extensions/contract-price/components/ItemsView.tsx frontend/src/extensions/contract-price/types.ts
git commit -m "feat(cpa-ui): 分项校验tab——分类列+分类筛选+展开区分类"
```

---

## P5 验收

### Task 14: 7 样例全量验收 + 桂北回归 + 秒级重解析实测

**Files:**
- Create: `.wolf/tmp/cpa-acceptance-runbook.md`（执行记录,不提交）

- [x] **Step 1: 容器代码生效**

```bash
# skill/后端代码改动 → gateway 内子进程跑管线,重启 gateway + 确认 skill 挂载
docker compose -p eai-docker restart gateway
docker exec deer-flow-gateway python -c "import sys; sys.path.insert(0, '/app/skills/public/contract-price-analysis'); from scripts.seed_library import DEFAULT_TABLE_SEEDS; print(len(DEFAULT_TABLE_SEEDS))"
```
Expected: `6`

- [x] **Step 2: 7 样例上传 + 解析（UI 或 CLI）**

UI: 合同解析 tab → 上传 `D:\18 辽宁创元\03 项目策划\中交北京三公司\合同样例\` 全部 7 份 → 开始解析。
CLI 备选: `docker exec deer-flow-gateway python -m scripts.cli --phase upload --dir <容器内样例目录>`（文件需在容器内;UI 路径优先）。

- [x] **Step 3: 逐份核对（psql）**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "
SELECT file_name, parse_status,
       parse_meta->>'goods_tables' AS goods, parse_meta->>'rows_extracted' AS rows,
       parse_meta->'matched_seeds' AS seeds,
       jsonb_array_length(COALESCE(parse_meta->'unmatched_tables','[]'::jsonb)) AS unmatched
FROM cpa_documents ORDER BY created_at DESC LIMIT 10;"
```
Expected: ≥6 份 parsed 且 matched_seeds 非空;纯条款文档 no_tables;补充协议 parsed（方向纠偏生效,`parse_meta->'orientation_fixed_pages'` 含 2,3）。未匹配表全部出现在 unmatched 且不产 items（验收标准 6）。

- [x] **Step 4: 桂北回归**

```bash
# UI: 合同解析 tab → 桂北文档行 → 重新解析(缓存路径) → 计时
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "SELECT count(*) FROM cpa_items ci JOIN cpa_documents d ON ci.document_id=d.id WHERE d.file_name LIKE '%桂北%';"
```
Expected: ≈450 行（±5%）;抽查 3 个已知货物单价与改前一致。重解析耗时 <60s（缓存命中;对照全量 OCR 约 3-4 分钟）——验收标准 2/4。

- [x] **Step 5: 分类分簇抽查**

```bash
docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "
SELECT goods_name, category, count(*) FROM cpa_items
WHERE goods_name LIKE '%钢筋%' GROUP BY goods_name, category ORDER BY goods_name LIMIT 10;"
```
Expected: 同名货物不同 category 分行存在——验收标准 3。

- [x] **Step 6: 溯源对齐抽查**

分项校验 tab → 任一 item → 溯源:纠偏页(补充协议)与普通页各抽一,bbox 红框落在正确单元格——验收标准 5。

- [x] **Step 7: 收尾提交**

```bash
cat >> skills/public/contract-price-analysis/README.md << 'EOF'

## v3: Seed 定位规则(2026-09-17)
- 表格识别 = 严格 seed-only: `config.json → table_seeds`,内置 6 条(见 `scripts/seed_library.py`)
- 未匹配表零提取,记 `parse_meta.unmatched_tables`;文档状态 no_tables/needs_review 语义见设计文档 §1.2
- OCR 结构化结果按内容哈希缓存(`ocr/{sha256}.json`),重解析默认秒级;强制重 OCR: reparse `?re_ocr=true` / CLI `--re-ocr`
- 同名货物按分类(分类行上下文)分簇;补充协议类横扫页自动纠偏(ocr-service 页级试探)
EOF
git add skills/public/contract-price-analysis/README.md
git commit -m "docs(cpa): v3 seed规则README——严格seed-only/OCR缓存/分类分簇/方向纠偏"
```

---

## Self-Review 记录

- **Spec 覆盖**: §1.1→T1;§1.2→T4/T7;§1.3→T3/T5/T13;§2→T2/T3/T4;§3 缓存→T6、方向→T9、reparse→T7、元数据→T8;§4.1→T10/T11;§4.2→T12;§4.3→T13;§5→T1;§6→T4/T9/T12;§9→T14。无缺口。
- **占位符扫描**: T9 Step4 的签名透传已给出完整改法（三元组）;T12(c) 的 import 行列出确切符号。无 TBD。
- **类型一致性**: seed dict 键/ROLE_ORDER/raw item 键/meta 新键/`re_ocr`/`last_pages`/`orientation_fixed_pages` 全文核对一致;`_extract_from_tables` 第三参由 keywords 改 seeds 的全部调用点（run_parse/_process_one_doc/测试）已列。
