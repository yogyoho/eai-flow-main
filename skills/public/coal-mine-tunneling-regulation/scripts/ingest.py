#!/usr/bin/env python3
"""geological-report v2 — ingest.py：data/ 状态目录的唯一写者（D10）。

铁律（spec 2026-08-20-geological-report-v2-design.md §data/ 状态布局）：
  data/ 只允许两条写入路径，全部经过本脚本：
    1. forms 子命令 —— 空白表单生成（gate 前的收集面）+ 校验写入（agent 收集到的值）
    2. file 子命令  —— 解析上传文件（xlsx/csv/docx → 表单/CSV 行）
  章节生成器与其余脚本对 data/ 只读。agent 绝不手写 data/ JSON。

职责：
  forms  生成空白表单（JSON 按 references/stages/{stage}.json#forms schema；CSV 只写表头行），
         或以 --values/--rows 校验写入并自动登记 data/state_manifest.json
  file   上传文件解析分派（.csv/.xlsx/.docx），按列名匹配表单，指纹增量（未变→no-op）
  check  必填表单/必填字段完备性检查（门1 前置：缺什么列出来，绝不编造）

脚本纪律：纯 Python 3.12，stdlib only（xlsx/docx 走 zipfile+XML）。
不调用 LLM；不 import app.*/deerflow.*。

退出码：0 干净 / 1 用法或文件错误 / 2 需人工（缺必填）/ 3 完成带异常必读 anomalies
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
    families: dict[str, dict] = stage.get("forms", {})

    only = set(args.only.split(",")) if args.only else None
    anomalies: list[str] = []

    # bug-2217: --values/--rows 传了但为空串（典型: --values "$(cat 不存在的文件)" 静默展开）
    # 此前落入空白生成路径——配 --force 直接把 data/ 全部表单重置为空白，已收集数据全丢（页面实测）。
    # E2E 实测（run 5520c429）：bash 内联大段中文 JSON 引号反复炸裂烧光递归预算——文件形态绕开转义
    if getattr(args, "values_file", None):
        if args.values is not None:
            print("[ingest] 错误: --values 与 --values-file 互斥", file=sys.stderr)
            return EXIT_ERROR
        vf = Path(args.values_file)
        if not vf.is_absolute():
            vf = data_dir / vf
        if not vf.exists():
            print(f"[ingest] 错误: --values-file 不存在: {vf}", file=sys.stderr)
            return EXIT_ERROR
        args.values = vf.read_text(encoding="utf-8")
    if getattr(args, "rows_file", None):
        if args.rows is not None:
            print("[ingest] 错误: --rows 与 --rows-file 互斥", file=sys.stderr)
            return EXIT_ERROR
        rf = Path(args.rows_file)
        if not rf.is_absolute():
            rf = data_dir / rf
        if not rf.exists():
            print(f"[ingest] 错误: --rows-file 不存在: {rf}", file=sys.stderr)
            return EXIT_ERROR
        args.rows = rf.read_text(encoding="utf-8")
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
            # lineterminator="\n"：默认 "\r\n" 经 rstrip("\n") 会残留行尾 \r，而
            # read_text 的通用换行翻译把 \r 全折成 \n——指纹比较永假，no-op 失效
            # （test_csv_rows_write 实测）。统一 LF 落盘，写读两态一致。
            w = csv.writer(buf, lineterminator="\n")
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
        spec = {**spec, "_stage": Path(args.stage).stem or "exploration"}  # bug-3061: schema 标签=文件名，非 stage 中文名
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
            atomic_write_text(target, blank_json({**spec, "_stage": Path(args.stage).stem or "exploration"}, fam))  # bug-3061
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


def _read_csv_rows(src: Path) -> list[list[str]]:
    """CSV 读取（编码回退）：先 utf-8-sig，UnicodeDecodeError 再试 gb18030。

    煤矿侧 Windows Excel 导出默认 GB18030（对抗评审 P2）——单押 utf-8 会把
    合法上传挡在门外。两次皆失败时 UnicodeDecodeError（ValueError 子类）由
    cmd_file 统一转 EXIT_ERROR，不裸栈。
    """
    try:
        with open(src, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))
    except UnicodeDecodeError:
        print(f"[ingest] 警告: {src.name} 非 UTF-8——已按 GB18030 解码（FILE_DECODE_WARNING；Windows Excel 导出默认编码）", file=sys.stderr)
    with open(src, encoding="gb18030", newline="") as f:
        return list(csv.reader(f))


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
        csv_families = sorted(fam for fam, sp in families.items() if sp.get("columns") or sp.get("format") == "csv")
        print(f"[ingest] 错误: {args.family} 非 CSV 表单——仅支持 CSV 表单族（可选族: {', '.join(csv_families)}）", file=sys.stderr)
        return EXIT_ERROR

    ext = src.suffix.lower()
    try:
        if ext == ".xlsx":
            tables = [parse_xlsx_rows(src)]
        elif ext == ".csv":
            tables = [_read_csv_rows(src)]
        elif ext == ".docx":
            tables = parse_docx_tables(src)
        else:
            print(f"[ingest] 错误: 不支持的格式 {ext}（支持 xlsx/csv/docx）", file=sys.stderr)
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
    w = csv.writer(buf, lineterminator="\n")  # 同 forms 写路径：LF 落盘保指纹 no-op 可命中
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

def _num(v) -> float | None:
    """QC 专用宽松数值解析：int/float→float；数字字符串→float；解析不出→None。

    表单值经 agent/CSV 手写通道，字符串 "3.4" 常见（T5 评审 I1）——数值比较前
    必须收敛到 float，禁裸 `(v or 0) > x`（字符串值会 TypeError 炸掉 cmd_check）。
    bool 是 int 子类但语义非数值，排除。
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _tunneling_qc(quality: list[str], stage: dict, data_dir: Path) -> None:
    """掘进域专项质量警告（全部 warn 不阻断——阈值未过 tier1 核实前只提示）。

    计划稿为 rep.add/data.form 形态；本脚本 check 为内联 quality 收集器，
    按计划注记等价改写：warn 追加进 GATE1_QUALITY 块。
    数值一律经 _num 收敛（T5 评审 I1/M1）；缺失≠不足≠脏值三分——
    缺失归门1完备性（QC 不越权），脏值（在场但解析不出）单独出 warn。
    """
    def _form(fam: str):
        spec = stage.get("forms", {}).get(fam)
        if not spec:
            return None
        p = data_dir / family_filename(spec)
        if not p.exists():
            return None
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return doc if isinstance(doc, dict) else None

    def _filled(v) -> bool:
        """在场判定：非 None 且非空白串（空白串视同未填）。"""
        return v is not None and (not isinstance(v, str) or v.strip() != "")

    geo = _form("geology")
    sup = _form("support")
    vent = _form("ventilation")
    if geo:
        gas = geo.get("gas_emission_daily")
        if _filled(gas):
            if geo.get("khg") is None:
                quality.append("QC_GAS: geology.gas_emission_daily 已填但 khg（涌出不均衡系数）缺失——风量计算 Q1 需要它")
            gas_n = _num(gas)
            if gas_n is None:
                quality.append(f"QC_GAS: geology.gas_emission_daily={gas!r} 解析不出数值——C6 双口径与 Q1 无法取数，请更正为数字")
            elif gas_n > 0 and geo.get("gas_emission_monthly") is None:
                quality.append("QC_GAS: 日最大涌出量在场而月平均缺失——C6 双口径需成对（3.4/2.45 实证）")
    for spec in ((sup or {}).get("bolt_specs") or []):
        if not isinstance(spec, dict):
            continue
        # 键名双拼写兼容（T5 评审 I2）：schema 声明键为「部位(顶板/帮部)」（T3 字节锁
        # 不改 schema），agent/人工填数常写短键「部位」——两源都认，防 R4 红线被
        # 键名拼写静默绕过。
        pos = spec.get("部位") or spec.get("部位(顶板/帮部)")
        if pos != "顶板":
            continue
        raw = spec.get("长度_m")
        length = _num(raw)
        if _filled(raw) and length is None:
            quality.append(f"QC_BOLT: 顶板锚杆 长度_m={raw!r} 解析不出数值——R4 红线无法核验，请更正为数字（m）")
        elif length is not None and length < 1.8:
            quality.append("QC_BOLT: 顶板锚杆长度 <1.8m（审查红线 R4，若确有依据请注明支护设计出处）")
    if vent:
        diesel_raw = vent.get("diesel_power_total_kw")
        diesel = _num(diesel_raw)
        if _filled(diesel_raw) and diesel is None:
            quality.append(f"QC_VENT: ventilation.diesel_power_total_kw={diesel_raw!r} 解析不出数值——Q3 选型对照无法取数，请更正为数字（kW）")
        elif diesel is not None and diesel > 0 and not vent.get("fan_model"):
            quality.append("QC_VENT: 登记了柴油机车功率但未填局部通风机型号——F2 选型对照缺失")


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

    # ── bug-3036 质量门（WARN 不阻断门1——完备性先行；下游 build 空槽/残留门兜底强制）────
    quality: list[str] = []
    for fam, spec in stage.get("forms", {}).items():
        p = data_dir / family_filename(spec)
        if not p.exists() or spec.get("format") == "csv" or "columns" in spec:
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        declared = {f.get("name") for f in spec.get("fields", [])}

        def _strings(o, prefix: str):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield from _strings(v, f"{prefix}.{k}" if prefix else str(k))
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    yield from _strings(v, f"{prefix}[{i}]")
            elif isinstance(o, str):
                yield prefix, o

        for path, s in _strings(doc, ""):
            # XX 缺数占位（邻接数字/量词）——正文残留门的根源在数据层就该显形；规范形是 [待确认]
            if re.search(r"\d\s*XX|XX\s*\d|XX(?:万吨|亿吨|千米|公里|米|毫米|吨|克|个|处|条|件|孔|根|架|节|台|趟|%)", s):
                quality.append(f"{fam}.{path}: 缺数占位 {s[:40]!r}——XX 不得充当数字，改 [待确认] 或补数（bug-3036）")
            elif "XX" in s:
                # 匿名化残留：技能脱敏规范用「某」（XX地质队/XX幅 一类）
                quality.append(f"{fam}.{path}: 匿名化 {s[:40]!r}——脱敏规范形是「某」，与全文统一（bug-3036）")
        # 未声明点号键：doc 顶层点号键须是 stage fields 在册名——否则 {{TABLE:fam.key}} 子路径
        # 寻址走扁平命中时命名与契约两张皮（证据池 hydro.* 实测：正族名是 hydro_eng_env）
        for k in doc:
            if "." in k and k not in declared:
                quality.append(f"{fam} 顶层点号键 {k!r} 不在 stage fields——命名与骨架契约两张皮，改名或补登记（bug-3036）")

    # 掘进域专项质量警告（geo 域的 exploration_qc 分母 sanity / sample_assays CV_ANCHOR
    # 已随域退役——tunneling 域无此二族）
    _tunneling_qc(quality, stage, data_dir)

    # data/ 外来文件（唯一写者=ingest；证据池 formula_state.json 被写进 data/ 实测）
    try:
        registered = set(load_manifest(data_dir).get("files", {}))
        for p in sorted(data_dir.iterdir()):
            if p.name in registered or p.name.startswith(MANIFEST_NAME):
                continue
            if p.suffix in {".json", ".csv"}:
                quality.append(f"data/ 存在未登记文件 {p.name}——data/ 唯一写者=ingest.py，外部产物移至 state/（bug-3036）")
    except (OSError, json.JSONDecodeError):
        pass

    if quality:
        print("GATE1_QUALITY:")
        for x in quality:
            print(f"  warn: {x}")
        print(f"SUMMARY: quality_warns={len(quality)}（不阻断门1；写手动笔前逐条消化——XX→[待确认]/补数、CV 引用实测锚点）")
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
    errors = validate_values({**spec, "_stage": Path(stage_path).stem or "exploration"}, values)  # bug-3061
    if errors:
        raise ValueError("; ".join(errors))
    ddir = Path(data_dir)
    target = ddir / family_filename(spec)
    doc = json.loads(target.read_text(encoding="utf-8")) if target.exists() else json.loads(blank_json({**spec, "_stage": Path(stage_path).stem or "exploration"}, family))  # bug-3061
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
    f.add_argument("--values", help="JSON 对象字符串（JSON 表单）；大段数据建议改用 --values-file")
    f.add_argument("--values-file", dest="values_file", default=None, help="JSON 对象文件路径（--values 的文件形态，绕开 shell 引号转义；E2E 实测新增）")
    f.add_argument("--rows-file", dest="rows_file", default=None, help="JSON 行数组文件路径（--rows 的文件形态）")
    f.add_argument("--rows", help="JSON 行数组字符串（CSV 表单）")
    f.set_defaults(func=cmd_forms)

    fi = sub.add_parser("file", help="上传文件解析 → CSV 表单（指纹增量）")
    fi.add_argument("--stage", required=True)
    fi.add_argument("--data-dir", required=True)
    fi.add_argument("--input", required=True, help="上传文件路径（xlsx/csv/docx）")
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
