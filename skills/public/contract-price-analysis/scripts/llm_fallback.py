"""P2 LLM 列语义兜底(spec 2026-09-19 §3,计划 Task 6)。

铁律: LLM 只标注列语义(列索引→角色枚举),永不生成价格数值——条目值一律由
确定性提取(extract_items_seed)+仲裁产生;标注只是给同一管线换一套列映射。

触发(调用方 cli 把关): strict seed-only 下 unmatched 表;或 matched 表
NR 率 >0.50 且几何层不可用/也失败。验收门: 按映射走确定性提取+仲裁后
行级 ok 率 ≥0.90 才采纳;否则整表维持现状(needs_review/unmatched),管线
不阻塞。失败重试 ≤1 次(仅传输/解析失败;语义门拒绝不重试)。
"""

import json
import logging

import httpx

logger = logging.getLogger(__name__)

ROLE_ENUM = ["name", "spec", "qty", "unit", "price_unit", "price_total", "price_untaxed"]

_OK_GATE = 0.90      # 行级 ok 率采纳门(spec §3)
_MAX_ATTEMPTS = 2    # 初试 + 失败重试 1 次
_MAX_SAMPLE_COLS = 32  # 防异常宽表撑爆 prompt

_SYSTEM_PROMPT = (
    "你是合同价格表的列语义标注器。输入是 OCR 表格的表头单元格与每列样本值,"
    "输出一个 JSON 对象: 键=列索引(字符串),值=角色,角色只能取 "
    + "/".join(ROLE_ENUM)
    + "。只标注列语义,严禁输出任何数值、任何表格内容或角色枚举以外的词;"
    "无法确定时省略该列。必须标注 name(货物名称列)和至少一个价格列"
    "(price_unit=单价列 或 price_total=合价列)。只输出 JSON,不要多余文字。"
)


def _first_json_object(content: str) -> dict | None:
    """content(可能带 ```json 围栏/前后说明文字)中首个平衡 JSON 对象 → dict | None。

    逐字符扫描配平大括号(字符串/转义感知);平衡块 json.loads 失败 → 找下一个 '{'。"""
    if not content:
        return None
    start = content.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(content)):
            ch = content[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(content[start : i + 1])
                    except ValueError:
                        break  # 该平衡块解析失败 → 换下一个 '{'
                    return obj if isinstance(obj, dict) else None
        start = content.find("{", start + 1)
    return None


def _column_samples(rows, header_rows, per_col=2, max_cols=_MAX_SAMPLE_COLS):
    """表头之后每列前 per_col 个非空样本值。

    列宽以数据行为准——rapid-table 碎表头/列漂移场景下数据行可宽于表头,
    列索引必须与数据行一致(extract 按数据行索引取格)。"""
    width = min(max((len(r) for r in rows[header_rows:]), default=0), max_cols)
    samples: list[list[str]] = [[] for _ in range(width)]
    for row in rows[header_rows:]:
        if all(len(s) >= per_col for s in samples):
            break
        for ci in range(min(len(row), width)):
            if len(samples[ci]) >= per_col:
                continue
            v = (row[ci] or "").strip()
            if v:
                samples[ci].append(v)
    return samples


def annotate_roles(header_texts, sample_cols, base_url, api_key, model, timeout=30.0):
    """表头合并文本+每列≤2样本 → {列索引: ROLE_ENUM} | None。

    httpx.post(f"{base_url}/chat/completions", temperature=0, max_tokens=500)。
    解析 content 中首个 JSON 对象; 失败/缺 name 或 (price_unit|price_total) → None。
    传输/解析失败重试 ≤1 次;解析成功但缺关键角色属语义级答案,重试同一
    prompt 无益 → 立即 None(温度 0,同 prompt 同答案)。"""
    payload = {
        "header": [str(h or "") for h in (header_texts or [])],
        "samples": [[str(v) for v in (col or [])] for col in (sample_cols or [])],
    }
    url = (base_url or "").rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    for _attempt in range(_MAX_ATTEMPTS):
        try:
            resp = httpx.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "temperature": 0,
                    "max_tokens": 500,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # 不可达/超时/非 JSON 响应 → 重试一次(spec §3)
            logger.warning("llm_fallback annotate attempt %d failed: %s", _attempt + 1, exc)
            continue
        obj = _first_json_object(content if isinstance(content, str) else str(content))
        if obj is None:
            continue
        roles: dict[int, str] = {}
        for k, v in obj.items():
            try:
                ci = int(str(k).strip())
            except ValueError:
                continue
            if ci >= 0 and v in ROLE_ENUM:
                roles[ci] = v
        got = set(roles.values())
        if "name" in got and ("price_unit" in got or "price_total" in got):
            return roles
        return None  # 缺 name 或 (price_unit|price_total)
    return None


def try_llm_fallback(table, seeds, doc_uri, llm_cfg, page_texts=None, cat_in=None):
    """unmatched / matched-NR 表兜底(触发条件由调用方把关)。

    annotate_roles → 角色映射走既有确定性提取同路径(_matched_table_pass 完整
    管线: seed 列提取+价格校验+仲裁+finalize)→ 行级 ok 率 ≥0.90 采纳
    → (items, active, meta)。
      items: 本表条目(确定性提取产物,LLM 输出不进任何条目值路径);
      active: 续表继承上下文(LLM 角色可传给续页);
      meta: {"llm_roles": {列索引: 角色}, "probe": 探测期 scratch meta
             (goods_tables/matched_seeds/rows_extracted/anchor_override/...),
             由调用方并入真实 meta}。
    否则 (None, None, {}) —— 整表维持现状,不阻塞管线(spec §6)。
    ``seeds``: 保留参数(触发判定已在调用方 match_seed 完成,此处不重复匹配);
    ``cat_in``: 上一表尾部分类(分类跨页续传与主管线同语义)。"""
    if not llm_cfg or not (llm_cfg.get("base_url") and llm_cfg.get("model")):
        return None, None, {}
    try:
        # 函数级导入避免 cli ↔ llm_fallback 环(cli 顶层 import 本模块)
        from scripts.cli import _collapse_header, _matched_table_pass, _table_ok_rate

        rows = list(getattr(table, "rows", None) or [])
        if not rows:
            return None, None, {}
        header, header_rows, _hdr_idxs = _collapse_header(rows)
        if not header:
            return None, None, {}  # 无表头(续表等)——列标注无输入
        roles_idx = annotate_roles(
            [(h or "").strip() for h in header],
            _column_samples(rows, header_rows),
            llm_cfg["base_url"],
            llm_cfg.get("api_key"),
            llm_cfg["model"],
            timeout=float(llm_cfg.get("timeout", 30.0)),
        )
        if roles_idx is None:
            return None, None, {}
        # {ci: role} → {role: ci}(同角色多列取最左,镜像 seed 锚定首中语义)
        roles: dict = {}
        for ci in sorted(roles_idx):
            roles.setdefault(roles_idx[ci], ci)
        pseudo_seed = {
            "id": "llm-fallback",
            "display_name": "LLM兜底",
            "title_keywords": [],
            "columns": {r: [] for r in ROLE_ENUM},  # 空 columns → 非调价表语义
            "exclude": {},
            "source": "llm_fallback",
        }
        probe_items: list = []
        probe_meta: dict = {
            "tables_found": 0,
            "goods_tables": 0,
            "continuation_tables": 0,
            "rows_extracted": 0,
            "skipped": {},
            "unmatched_tables": [],
            "matched_seeds": {},
        }
        _, active, _info = _matched_table_pass(
            table,
            doc_uri,
            (pseudo_seed, roles, header_rows),
            None,
            cat_in,
            page_texts or {},
            probe_items,
            probe_meta,
        )
        rate = _table_ok_rate(probe_items)
        if rate < _OK_GATE:
            logger.info(
                "llm fallback rejected p%s t%s (ok_rate %.2f < %.2f)",
                getattr(table, "page_no", "?"),
                getattr(table, "table_idx", "?"),
                rate,
                _OK_GATE,
            )
            return None, None, {}
        logger.info(
            "llm fallback accepted p%s t%s (ok_rate %.2f) roles=%s",
            getattr(table, "page_no", "?"),
            getattr(table, "table_idx", "?"),
            rate,
            roles_idx,
        )
        return probe_items, active, {"llm_roles": dict(roles_idx), "probe": probe_meta}
    except Exception as exc:
        logger.warning(
            "llm fallback skipped p%s t%s: %s",
            getattr(table, "page_no", "?"),
            getattr(table, "table_idx", "?"),
            exc,
        )
        return None, None, {}
