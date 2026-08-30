#!/usr/bin/env python3
"""geological-report v2 — ingest.py：data/ 状态目录的唯一写者（D10）。

铁律（spec 2026-08-20-geological-report-v2-design.md §data/ 状态布局）：
  data/ 只允许两条写入路径，全部经过本脚本：
    1. forms 子命令 —— 空白表单生成（gate 前的收集面）+ 校验写入（agent 收集到的值）
    2. file 子命令  —— 解析上传文件（xlsx/csv/docx/pdf → 表单/CSV 行）
  章节生成器与其余脚本对 data/ 只读。agent 绝不手写 data/ JSON。

职责：
  forms  生成空白表单（JSON 按 references/stages/{stage}.json#forms schema；CSV 只写表头行），
         或以 --values/--rows 校验写入并自动登记 data/state_manifest.json
  file   上传文件解析分派（.csv/.xlsx/.docx/.pdf），按列名匹配表单，指纹增量（未变→no-op）
  check  必填表单/必填字段完备性检查（门1 前置：缺什么列出来，绝不编造）

脚本纪律：纯 Python 3.12，stdlib only（xlsx/docx 走 zipfile+XML；pdf 尝试 pdfplumber，
不可用→退出码 2 走 OCR 路径）。不调用 LLM；不 import app.*/deerflow.*。

退出码：0 干净 / 1 用法或文件错误 / 2 需人工（OCR 路由、缺必填）/ 3 完成带异常必读 anomalies
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MANUAL = 2
EXIT_ANOMALY = 3

MANIFEST_NAME = "state_manifest.json"


# ── 通用小件 ────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # bug-2217: 固定 .tmp 名在并行 ingest.py 进程间互吃临时文件 → os.replace
    # FileNotFoundError（页面实测 seq133/152）。pid 后缀各写各的，replace 仍原子。
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ── 交付契约标记（bug-2225：present_files/artifacts GET/工作区同步三门的判据）──

DELIVERY_CONTRACT = ".delivery-contract"
DELIVERY_CONTRACT_CONTENT = '{"skill": "geological-report"}\n'


def write_delivery_contract(data_dir: Path) -> list[Path]:
    """bug-2225: 在 data-dir 祖先链上已存在的 outputs/ 目录落交付契约标记（幂等）。

    实测布局（线程 90c9d09d）：data 在 user-data/workspace/geo-report/data，交付面是
    线程 outputs（宿主 …/user-data/outputs，沙箱内 /mnt/user-data/outputs）。沿祖先
    找 outputs/ 同时覆盖本地沙箱（宿主路径）与 Docker 沙箱（虚拟挂载）；技能布局
    geo-report/outputs（若已建）同样标记。文件系统根跳过——绝不在盘符根下落文件。
    """
    planted: list[Path] = []
    for anc in data_dir.resolve().parents:
        if anc == anc.parent:
            continue  # 盘符/文件系统根
        out = anc / "outputs"
        if not out.is_dir():
            continue
        target = out / DELIVERY_CONTRACT
        if not target.exists() or target.read_text(encoding="utf-8") != DELIVERY_CONTRACT_CONTENT:
            atomic_write_text(target, DELIVERY_CONTRACT_CONTENT)
        planted.append(target)
    return planted


def load_manifest(data_dir: Path) -> dict:
    p = data_dir / MANIFEST_NAME
    if not p.exists():
        return {"version": 1, "files": {}}
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
        return m if isinstance(m.get("files"), dict) else {"version": 1, "files": {}}
    except Exception:
        return {"version": 1, "files": {}}


def register_file(data_dir: Path, rel_name: str, family: str, required: bool, fmt: str) -> None:
    """写入/更新 state_manifest 条目（文件须已落盘，hash 现算）。

    bug-2217: manifest 是 load-modify-write，并行 ingest.py 进程会互相覆盖丢条目。
    O_CREAT|O_EXCL 自旋锁跨进程互斥（Windows/Linux 通用）；
    # ponytail: 持锁进程崩溃会留死锁文件 → 10s 超时报错，需人工删 .lock
    """
    lock = data_dir / (MANIFEST_NAME + ".lock")
    for _ in range(200):  # 0.05s × 200 = 10s 上限
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            time.sleep(0.05)
    else:
        raise RuntimeError(f"{lock} 被占用超过 10s（若为残留死锁文件可删除后重试）")
    try:
        m = load_manifest(data_dir)
        m["files"][rel_name] = {
            "sha256": sha256_file(data_dir / rel_name),
            "family": family,
            "required": required,
            "format": fmt,
        }
        atomic_write_text(data_dir / MANIFEST_NAME, json.dumps(m, ensure_ascii=False, indent=2))
    finally:
        lock.unlink(missing_ok=True)


def load_stage(stage_path: Path) -> dict:
    # bug-2217: 裸名（如 'exploration'）此前抛裸 FileNotFoundError traceback。
    # 自动补全到技能内置 references/stages/<name>.json；仍找不到给可读错误。
    p = Path(stage_path)
    if not p.exists():
        alt = Path(__file__).resolve().parent.parent / "references" / "stages" / (p.name if p.suffix == ".json" else p.name + ".json")
        if alt.exists():
            p = alt
        else:
            print(f"[ingest] 错误: 找不到阶段 schema '{stage_path}'（内置路径 {alt} 也不存在）。用法: --stage references/stages/exploration.json，或裸名 exploration）", file=sys.stderr)
            raise SystemExit(EXIT_ERROR)
    return json.loads(p.read_text(encoding="utf-8"))


# ── 表单族定位：族名 ↔ data/ 文件名（如 industrial ↔ 13_industrial_params.json）──

def family_filename(spec: dict) -> str:
    return spec["file"]


def find_family_by_prefix(data_dir: Path, prefix: str) -> tuple[str, str] | None:
    """'13' → ('industrial_params', '13_industrial_params.json')。按序号前缀精确匹配。"""
    for p in sorted(data_dir.glob(f"{prefix}_*.json")) + sorted(data_dir.glob(f"{prefix}_*.csv")):
        return p.stem.split("_", 1)[1], p.name
    return None


# ── schema 校验 ─────────────────────────────────────────────────────────────

def coerce_type(field_def: dict, key: str, value) -> tuple[bool, object, str]:
    """按 schema 字段定义做类型矫正。返回 (ok, coerced, err)。"""
    t = field_def.get("type", "string")
    if value is None:
        # null = 尚未提供（部分收集落盘）。完备性由 check（门1）统一裁决——
        # 此处拒绝会逼出"用 0/示例值填结构冒充 null"（页面实测 bug-2216）。
        return True, None, ""
    try:
        if t.startswith("enum:"):
            allowed = t[5:].split("|")
            if str(value) not in allowed:
                return False, None, f"{key}: '{value}' 不在枚举 {allowed}"
            return True, str(value), ""
        if t == "number":
            return True, float(value), ""
        if t == "integer":
            if float(value) != int(float(value)):
                return False, None, f"{key}: {value} 不是整数"
            return True, int(float(value)), ""
        if t == "bool":
            if isinstance(value, bool):
                return True, value, ""
            return True, str(value).lower() in ("true", "1", "yes"), ""
        if t in ("string",):
            return True, str(value), ""
        if t.startswith("array"):
            if not isinstance(value, list):
                return False, None, f"{key}: 需要 array"
            return True, value, ""
        if t == "object":
            if not isinstance(value, dict):
                return False, None, f"{key}: 需要 object"
            return True, value, ""
    except (TypeError, ValueError) as e:
        return False, None, f"{key}: 类型转换失败 ({e})"
    return True, value, ""


def validate_values(spec: dict, values: dict) -> list[str]:
    """字段名必须在 schema 中（防 typo 静默丢字段）；类型按定义矫正。返回错误清单。"""
    errors: list[str] = []
    known = {f["name"]: f for f in spec.get("fields", [])}
    # csv 族（有 columns）不走这里
    for key, val in values.items():
        fd = known.get(key)
        if fd is None:
            errors.append(f"{key}: 不在 schema 字段清单中（防 typo——合法字段: {sorted(known)}）")
            continue
        ok, _, err = coerce_type(fd, key, val)
        if not ok:
            errors.append(err)
    return errors


# ── 点分键归并（F5: 对象族子键有权威 schema 名，终结 agent 猜键→静默 0）────

def _object_field_names(spec: dict) -> set[str]:
    return {f["name"] for f in spec.get("fields", []) if f.get("type") == "object"}


def _expand_dotted(values: dict, spec: dict) -> dict:
    """点分键 → 嵌套 dict 归并（仅当前缀命中本族 type=object 字段名）。

    hydro/engineering/environment 等前缀不命中任何 schema 字段名 → 原样保留
    扁平键（formula_runner 按 `hee.get("hydro.inflow_analogy")` 扁平读取，合约不破）。
    顶层整对象传法 {"prices": {...}} 本就非点分，不经此函数改动 → 存量合约零破坏。
    """
    obj_names = _object_field_names(spec)
    out: dict = {}
    for key, val in values.items():
        prefix, dot, _ = key.partition(".")
        if dot and prefix in obj_names:
            cur = out.get(prefix)
            cur = dict(cur) if isinstance(cur, dict) else {}
            cur[key[len(prefix) + 1:]] = val
            out[prefix] = cur
        else:
            out[key] = val
    return out


def _merge_values(doc: dict, values: dict) -> None:
    """写入合并：双方均 dict 时逐子键深合并——分批补答不丢先前子键
    （顺带修复 doc.update 浅更新抹掉先前子键的坑）；其余浅写。"""
    for k, v in values.items():
        if isinstance(v, dict) and isinstance(doc.get(k), dict):
            _merge_values(doc[k], v)
        else:
            doc[k] = v


def _get_dotted(doc: dict, name: str):
    """点分 name 取值：嵌套 dict 形态（经 _expand_dotted 归并的 economics 族）取子键；
    扁平点分键形态（hydro 族——前缀不命中 object 字段名，未经归并直落盘）回退整键查。"""
    if "." not in name:
        return doc.get(name)
    prefix, _, sub = name.partition(".")
    v = doc.get(prefix)
    if isinstance(v, dict):
        return v.get(sub)
    return doc.get(name)


# ── 子命令: forms ───────────────────────────────────────────────────────────

def blank_json(spec: dict, family: str) -> str:
    doc = {
        "_meta": {
            "form": spec["file"],
            "family": family,
            "required": spec.get("required", True),
            "schema": f"references/stages/{spec.get('_stage', 'exploration')}.json#forms.{family}",
            "status": "draft",
        }
    }
    for f in spec.get("fields", []):
        if "." in f["name"]:
            continue  # F5: 点分子键不落占位（父条目占位已够，避免扁平 null 与嵌套双写）
        doc[f["name"]] = None if f.get("required", True) else []
    return json.dumps(doc, ensure_ascii=False, indent=2)


def cmd_forms(args) -> int:
    stage = load_stage(Path(args.stage))
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    contracts = write_delivery_contract(data_dir)
    if contracts:
        print(f"DELIVERY_CONTRACT: {len(contracts)} 个 outputs/ 已标记（交付门判据，勿删，bug-2225）")
    families: dict[str, dict] = stage.get("forms", {})

    only = set(args.only.split(",")) if args.only else None
    anomalies: list[str] = []

    # bug-2217: --values/--rows 传了但为空串（典型: --values "$(cat 不存在的文件)" 静默展开）
    # 此前落入空白生成路径——配 --force 直接把 data/ 全部表单重置为空白，已收集数据全丢（页面实测）。
    if args.values is not None and not args.values.strip():
        print("[ingest] 错误: --values 是空字符串（常见于 $(cat 文件不存在) 静默展开为空）。请检查取值命令后重传完整 JSON。", file=sys.stderr)
        return EXIT_ERROR
    if args.rows is not None and not args.rows.strip():
        print("[ingest] 错误: --rows 是空字符串。请检查取值命令后重传完整 JSON 数组。", file=sys.stderr)
        return EXIT_ERROR

    if args.values or args.rows:
        # 校验写入路径（agent 收集到的值 → data/；唯一写者语义）
        if args.family not in families:
            print(f"[ingest] 错误: 未知表单族 {args.family}（合法: {sorted(families)}）", file=sys.stderr)
            return EXIT_ERROR
        spec = families[args.family]
        fname = family_filename(spec)
        target = data_dir / fname
        if spec.get("format") == "csv" or "columns" in spec:
            if args.rows is None:
                print(f"[ingest] 错误: {args.family} 是 CSV 表单，用 --rows '[[行],[行]]'", file=sys.stderr)
                return EXIT_ERROR
            rows = json.loads(args.rows)
            header = spec["columns"]
            bad = [i for i, r in enumerate(rows) if len(r) != len(header)]
            if bad:
                print(f"[ingest] 错误: 行宽不等于列数 {len(header)}（行号 0-based: {bad}）", file=sys.stderr)
                return EXIT_ERROR
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(header)
            w.writerows(rows)
            new_text = buf.getvalue().rstrip("\n")
            if target.exists() and target.read_text(encoding="utf-8") == new_text:
                print(f"FORM_NOOP: {fname} 内容未变（指纹一致）")
                return EXIT_OK
            atomic_write_text(target, new_text)
            register_file(data_dir, fname, args.family, spec.get("required", True), "csv")
            print(f"FORM_WRITTEN: {fname} rows={len(rows)}")
            return EXIT_OK
        # JSON 族
        if args.values is None:
            print(f"[ingest] 错误: JSON 表单用 --values '{{...}}'", file=sys.stderr)
            return EXIT_ERROR
        values = json.loads(args.values)
        spec = {**spec, "_stage": stage.get("stage", "exploration")}
        errors = validate_values(spec, values)
        if errors:
            for e in errors:
                print(f"[ingest] 校验失败: {e}", file=sys.stderr)
            return EXIT_ERROR
        doc = json.loads(blank_json(spec, args.family)) if not target.exists() else json.loads(target.read_text(encoding="utf-8"))
        _merge_values(doc, _expand_dotted(values, spec))
        doc.setdefault("_meta", {})
        doc["_meta"]["status"] = "filled"
        atomic_write_text(target, json.dumps(doc, ensure_ascii=False, indent=2))
        register_file(data_dir, fname, args.family, spec.get("required", True), "json")
        print(f"FORM_WRITTEN: {fname} fields={sorted(values)}")
        return EXIT_OK

    # 空白生成路径
    # bug-2217: 空白生成此前无视 --family（--family 只在写入路径生效），
    # "--family X --force" 会重置全部 21 张表单而非 X 一张。--force 必须有显式范围。
    if args.family and only is None:
        only = {args.family}
    if args.force and only is None:
        print("[ingest] 错误: --force 必须搭配 --only <族列表> 或 --family <族>。无范围的 --force 会把 data/ 全部表单重置为空白、清掉已收集数据。", file=sys.stderr)
        return EXIT_ERROR
    written = skipped = 0
    for fam, spec in families.items():
        if only and fam not in only:
            continue
        fname = family_filename(spec)
        target = data_dir / fname
        if target.exists() and not args.force:
            skipped += 1
            continue
        if spec.get("format") == "csv" or "columns" in spec:
            atomic_write_text(target, ",".join(spec["columns"]))
            fmt = "csv"
        else:
            atomic_write_text(target, blank_json({**spec, "_stage": stage.get("stage", "exploration")}, fam))
            fmt = "json"
        register_file(data_dir, fname, fam, spec.get("required", True), fmt)
        written += 1
    print(f"FORMS_READY: written={written} skipped_existing={skipped} data_dir={data_dir}")
    return EXIT_OK


# ── 上传解析器（stdlib）─────────────────────────────────────────────────────

def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def parse_xlsx_rows(path: Path) -> list[list[str]]:
    """sheet1 全行 → 字符串矩阵。stdlib zipfile+XML（数值/共享串/内联串）。"""
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root:
                shared.append("".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
        sheet_name = next((n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet1\.xml", n)), None)
        if sheet_name is None:
            raise ValueError("xlsx 缺 sheet1")
        root = ET.fromstring(z.read(sheet_name))
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rows: list[list[str]] = []
    for row in root.iter(ns + "row"):
        cells: dict[int, str] = {}
        for c in row.iter(ns + "c"):
            idx = _col_index(c.get("r", "A1"))
            t = c.get("t", "n")
            v = c.find(ns + "v")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(ns + "t"))
            elif v is not None:
                val = v.text or ""
            else:
                val = ""
            cells[idx] = val
        width = (max(cells) + 1) if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def parse_docx_tables(path: Path) -> list[list[list[str]]]:
    """docx 全部表格 → 每表字符串矩阵。zipfile+XML（w:tbl/w:tr/w:tc/w:t）。"""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    tables = []
    for tbl in root.iter("{%s}tbl" % ns["w"]):
        rows = []
        for tr in tbl.findall("{%s}tr" % ns["w"]):
            cells = []
            for tc in tr.findall("{%s}tc" % ns["w"]):
                cells.append("".join(t.text or "" for t in tc.iter("{%s}t" % ns["w"])).strip())
            rows.append(cells)
        tables.append(rows)
    if not tables:
        raise ValueError("docx 无表格（纯文本段落不适用表单填充）")
    return tables


def parse_pdf_tables(path: Path) -> list[list[list[str]]]:
    try:
        import pdfplumber  # 沙箱 venv 已备（bid-proposal 先例）；宿主缺失→人工路由
    except ImportError:
        print("[ingest] pdf 解析需要 pdfplumber（宿主不可用）——请走 eai-flow-ocr 全文 OCR 路径后以 docx/csv 重传", file=sys.stderr)
        raise SystemExit(EXIT_MANUAL)
    tables: list[list[list[str]]] = []
    with pdfplumber.open(path) as pdf:
        text = "".join((p.extract_text() or "") for p in pdf.pages[:3])
        if not text.strip():
            print("[ingest] PDF 无文本层（扫描件）——请走 eai-flow-ocr 全文 OCR 路径", file=sys.stderr)
            raise SystemExit(EXIT_MANOMALY if False else EXIT_MANUAL)
        for p in pdf.pages:
            for t in (p.extract_tables() or []):
                tables.append([[c or "" for c in row] for row in t])
    if not tables:
        raise ValueError("PDF 无表格")
    return tables


def normalize_header(name: str) -> str:
    return re.sub(r"[\s（）()：:，,]", "", name)


def match_table(tables: list[list[list[str]]], columns: list[str]) -> list[list[str]]:
    """列名匹配：表头行与目标列的规范化交集比例最高且 ≥ 一半。"""
    want = {normalize_header(c) for c in columns}
    best, best_score = None, 0.0
    for rows in tables:
        if not rows:
            continue
        head = {normalize_header(c) for c in rows[0]}
        score = len(head & want) / max(len(want), 1)
        if score > best_score:
            best, best_score = rows, score
    if best is None or best_score < 0.5:
        raise ValueError(f"无表格列匹配目标表单（需要列: {columns}）")
    return best


def cmd_file(args) -> int:
    stage = load_stage(Path(args.stage))
    data_dir = Path(args.data_dir)
    contracts = write_delivery_contract(data_dir)  # bug-2225: file 入口同样是数据落库面，先落契约
    if contracts:
        print(f"DELIVERY_CONTRACT: {len(contracts)} 个 outputs/ 已标记（交付门判据，勿删，bug-2225）")
    src = Path(args.input)
    if not src.exists():
        print(f"[ingest] 错误: 输入文件不存在 {src}", file=sys.stderr)
        return EXIT_ERROR
    families = stage.get("forms", {})
    spec = families.get(args.family)
    if spec is None:
        print(f"[ingest] 错误: 未知表单族 {args.family}", file=sys.stderr)
        return EXIT_ERROR
    columns = spec.get("columns")
    if not columns:
        print(f"[ingest] 错误: {args.family} 非 CSV 表单——上传解析仅支持 CSV 族（08a/13a）", file=sys.stderr)
        return EXIT_ERROR

    ext = src.suffix.lower()
    try:
        if ext == ".xlsx":
            tables = [parse_xlsx_rows(src)]
        elif ext == ".csv":
            with open(src, encoding="utf-8-sig", newline="") as f:
                tables = [list(csv.reader(f))]
        elif ext == ".docx":
            tables = parse_docx_tables(src)
        elif ext == ".pdf":
            tables = parse_pdf_tables(src)
        else:
            print(f"[ingest] 错误: 不支持的格式 {ext}（支持 xlsx/csv/docx/pdf）", file=sys.stderr)
            return EXIT_ERROR
    except ValueError as e:
        print(f"[ingest] 解析失败: {e}", file=sys.stderr)
        return EXIT_ERROR

    try:
        rows = match_table(tables, columns)
    except ValueError as e:
        print(f"[ingest] 列匹配失败: {e}", file=sys.stderr)
        return EXIT_ERROR

    # 列序对齐：按表头映射到 schema 列序（容忍列序不同）
    head = [normalize_header(c) for c in rows[0]]
    missing = [c for c in columns if normalize_header(c) not in head]
    if missing:
        print(f"[ingest] 缺列: {missing}（表头: {rows[0]}）", file=sys.stderr)
        return EXIT_ERROR
    order = [head.index(normalize_header(c)) for c in columns]
    body = [[r[i] if i < len(r) else "" for i in order] for r in rows[1:]]
    body = [r for r in body if any(x.strip() for x in r)]

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    w.writerows(body)
    new_text = buf.getvalue().rstrip("\n")
    fname = family_filename(spec)
    target = data_dir / fname
    if target.exists() and target.read_text(encoding="utf-8") == new_text:
        print(f"FILE_NOOP: {src.name} → {fname} 内容指纹一致，跳过（增量 no-op）")
        return EXIT_OK
    atomic_write_text(target, new_text)
    register_file(data_dir, fname, args.family, spec.get("required", True), "csv")
    print(f"FILE_INGESTED: {src.name} → {fname} rows={len(body)}（原表 {len(rows)-1} 数据行，列对齐后 {len(body)} 非空行）")
    if len(body) != len(rows) - 1:
        print(f"ANOMALY: 空行被剔除 {len(rows)-1 - len(body)} 行")
        return EXIT_ANOMALY
    return EXIT_OK


# ── 子命令: check（门1 前置完备性）─────────────────────────────────────────

def cmd_check(args) -> int:
    stage = load_stage(Path(args.stage))
    data_dir = Path(args.data_dir)
    missing_forms: list[str] = []
    missing_fields: list[str] = []
    for fam, spec in stage.get("forms", {}).items():
        if not spec.get("required", True):
            continue
        p = data_dir / family_filename(spec)
        if not p.exists():
            missing_forms.append(f"{fam} ({family_filename(spec)})")
            continue
        if spec.get("format") == "csv" or "columns" in spec:
            lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if len(lines) < 2:
                missing_fields.append(f"{fam}: CSV 无数据行")
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            missing_fields.append(f"{fam}: JSON 损坏")
            continue
        if isinstance(doc, list):
            # bug-3004: 清单族经 `ingest.py file` 从 CSV 摄入后落成行数组（如 08_orebody_list），
            # 逐字段门只适用于 dict 形状——行数组按非空判完备，避免 doc.get AttributeError。
            if not doc:
                missing_fields.append(f"{fam}: 清单为空")
            continue
        for f in spec.get("fields", []):
            if f.get("required", True) and _get_dotted(doc, f["name"]) in (None, "", []):
                missing_fields.append(f"{fam}.{f['name']}")
    if missing_forms or missing_fields:
        print("GATE1_MISSING:")
        for x in missing_forms:
            print(f"  form: {x}")
        for x in missing_fields:
            print(f"  field: {x}")
        print(f"SUMMARY: missing_forms={len(missing_forms)} missing_fields={len(missing_fields)}（缺项必须向用户收集，禁止编造）")
        return EXIT_MANUAL
    print("GATE1_COMPLETE: 必填表单与必填字段全部就绪")
    return EXIT_OK


# ── 供 formula_runner update 复用的编程入口（保持唯一写者语义）────────────

def write_form_values(stage_path: str, data_dir: str, family: str, values: dict) -> None:
    """编程入口：等价于 `forms --family X --values '{...}'`。校验失败抛 ValueError。"""
    stage = load_stage(Path(stage_path))
    spec = stage["forms"][family]
    errors = validate_values({**spec, "_stage": stage.get("stage", "exploration")}, values)
    if errors:
        raise ValueError("; ".join(errors))
    ddir = Path(data_dir)
    contracts = write_delivery_contract(ddir)  # bug-2225: 编程写入口同样落契约（保持唯一写者语义）
    if contracts:
        print(f"DELIVERY_CONTRACT: {len(contracts)} 个 outputs/ 已标记（交付门判据，勿删，bug-2225）")
    target = ddir / family_filename(spec)
    doc = json.loads(target.read_text(encoding="utf-8")) if target.exists() else json.loads(blank_json({**spec, "_stage": stage.get("stage", "exploration")}, family))
    _merge_values(doc, _expand_dotted(values, spec))
    doc.setdefault("_meta", {})["status"] = "filled"
    atomic_write_text(target, json.dumps(doc, ensure_ascii=False, indent=2))
    register_file(ddir, family_filename(spec), family, spec.get("required", True), "json")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — data/ 唯一写者")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("forms", help="空白表单生成 / --values|--rows 校验写入")
    f.add_argument("--stage", required=True, help="references/stages/{stage}.json 路径")
    f.add_argument("--data-dir", required=True)
    f.add_argument("--only", help="逗号分隔表单族名（只生成这些）")
    f.add_argument("--force", action="store_true", help="覆盖已存在表单（危险：重置为空白；必须搭配 --only/--family 限定范围）")
    f.add_argument("--family", help="目标表单族（--values/--rows 写入模式必填）")
    f.add_argument("--values", help="JSON 对象字符串（JSON 表单）")
    f.add_argument("--rows", help="JSON 行数组字符串（CSV 表单）")
    f.set_defaults(func=cmd_forms)

    fi = sub.add_parser("file", help="上传文件解析 → CSV 表单（指纹增量）")
    fi.add_argument("--stage", required=True)
    fi.add_argument("--data-dir", required=True)
    fi.add_argument("--input", required=True, help="上传文件路径（xlsx/csv/docx/pdf）")
    fi.add_argument("--family", required=True, help="目标 CSV 表单族（如 08a_sample_assays → sample_assays）")
    fi.set_defaults(func=cmd_file)

    c = sub.add_parser("check", help="必填完备性检查（门1 前置）")
    c.add_argument("--stage", required=True)
    c.add_argument("--data-dir", required=True)
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
