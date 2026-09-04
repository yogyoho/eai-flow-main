#!/usr/bin/env python3
"""eai.py — 系统统一模块运维 CLI（薄 REST 客户端，spec 2026-09-03）。

两类子命令：服务端型（gsb/cpa，需登录会话）与本地工具型（license，免会话）。
依赖：stdlib + httpx（禁止 import app.*/deerflow.*——部署域隔离，可独立拷贝到运维机执行）。
凭据不落盘（HTTP 会话 cookie 进程内有效，批量任务须单进程内完成，中断重跑即重登录）；
注意 --password 会进 shell history，推荐改用 EAI_PASSWORD 环境变量免密传参。

EAI-CUSTOM (geo-batch-cli, spec 2026-09-03): 新增独立运维工具。

契约锚点（recon 实证，勿凭印象改动）：
- 登录 POST /api/extensions/auth/login，body {"username","password"}（工号/邮箱二合一）；
  httpx 默认不带 Origin 头——勿手工添加（带即 403 Cross-site auth request denied）；
  成功响应 token 只在 Set-Cookie（access_token HttpOnly + 中间件补种 csrf_token），不在响应体。
- 登录限流桶 5 次/5 分钟 IP 共享（nginx:2026 整入口共享，含真人）→ 429 必须 raise
  LoginLocked 并绝不自动重试。
- CSRF 双提交：cookie csrf_token 原样回填 X-CSRF-Token（token_urlsafe 本身 URL 安全，勿二次解码）；
  仅状态变更方法（POST/PUT/DELETE/PATCH）需要。
- 探活 GET /api/v1/auth/me：200=有效 / 401=失效（勿用 /api/permissions/me——无权限用户 403 误判）。
- gsb 端点（前缀 /api/extensions/geo-samples）：POST /documents/suggest-id?title=<题名>
  （POST 方法 + Query 传参，httpx params 自动 URL 编码 CJK；题名解析在服务端，CLI 不做本地解析）、
  POST /documents/upload（multipart file + Form report_id/stage/mineral/region + defer_parse，空值
  不透传走服务端默认；409 detail 含「已存在」=撞号顺延重试，含 file_hash/相同内容=内容重复不重试；
  --defer-parse 时透传 defer_parse=true——服务端 defer：不 create_run、响应省略 run_id，行停
  uploaded，后续经 parse-batch 端点或单体 /parse 触发）、
  POST /documents/{id}/parse、GET /documents?skip&limit（limit≤200）。
  注意非 defer 时 upload 端点自身已后台起 parse 并返回其 run_id——CLI 的单体 parse 调用是幂等兜底，
  409「已在跑」属预期。
- cpa 端点（前缀 /api/extensions/contract-price）：POST /documents/upload 仅 multipart file 字段
  （409=内容重复计 skipped）；POST /pipeline/run body {"mode":"table","trigger":"manual"}
  全局互斥（已有 parse 在跑 → 409），批量只在末尾触发一次。
- license：tools/license/license_generator.py generate_license(...)——machine_id 缺失时**静默
  return 不写输出文件**，调用方必须校验输出存在，否则假成功。加载方式为按文件路径直载
  （importlib.util.spec_from_file_location，带 sys.modules 缓存），**零 sys.path 变更**。
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

SESSION_FILE = Path.home() / ".eai" / "session.json"  # T6 断点 state 预留位
LOGIN_PATH = "/api/extensions/auth/login"
PROBE_PATH = "/api/v1/auth/me"
CSRF_HEADER = "X-CSRF-Token"
GSB_BASE = "/api/extensions/geo-samples"
CPA_BASE = "/api/extensions/contract-price"


class LoginLocked(Exception):
    """登录限流（429，5 次/5 分钟 IP 共享桶）——调用方必须停止重试。"""


class Session:
    """登录后的 REST 会话：cookie jar 持 access_token，post/delete 自动拼 CSRF 双提交头。"""

    def __init__(self, base_url: str, client: httpx.Client, csrf: str):
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.csrf = csrf or ""

    def _url(self, path: str) -> str:
        """相对路径拼 base_url；绝对 URL（http/https 开头）原样透传——httpx 按 host 匹配 cookie jar。"""
        if path.startswith(("http://", "https://")):
            return path
        return self.base_url + path

    def headers(self) -> dict:
        return {CSRF_HEADER: self.csrf}

    def get(self, path: str, **kw):
        return self.client.get(self._url(path), **kw)

    def post(self, path: str, **kw):
        headers = dict(kw.pop("headers", None) or {})
        if self.csrf:
            headers.update(self.headers())  # CSRF 双提交：状态变更方法必带（无 csrf 则不发空头）
        return self.client.post(self._url(path), headers=headers, **kw)

    def delete(self, path: str, **kw):
        headers = dict(kw.pop("headers", None) or {})
        if self.csrf:
            headers.update(self.headers())
        return self.client.delete(self._url(path), headers=headers, **kw)


def login(base_url: str, username: str, password: str, transport: httpx.BaseTransport | None = None) -> Session:
    """登录并返回 Session；429 → LoginLocked（绝不自动重试——限流桶 IP 共享会把入口锁满 5 分钟）。"""
    client = httpx.Client(base_url=base_url, timeout=120.0, transport=transport)
    resp = client.post(LOGIN_PATH, json={"username": username, "password": password})
    if resp.status_code == 429:
        client.close()
        raise LoginLocked("5 次/5 分钟 IP 共享桶已满——稍后再试，请勿连续重试")
    resp.raise_for_status()
    # Set-Cookie 已自动入 jar；response.cookies 与 client.cookies 双路取值（后者为 httpx 实测兜底）
    csrf = resp.cookies.get("csrf_token") or client.cookies.get("csrf_token")
    return Session(base_url, client, csrf or "")


def probe(sess: Session, transport: httpx.BaseTransport | None = None) -> bool:
    """探活 /api/v1/auth/me：200=有效 / 401=失效。transport 参数为签名统一占位（client 已持）。"""
    return sess.get(PROBE_PATH).status_code == 200


SUBCOMMANDS: dict[str, dict] = {}  # name -> {"help":…, "needs_session": bool, "func": callable}


def register(name: str, help_text: str, needs_session: bool = True):
    """子命令注册表装饰器：needs_session 命令自动获得 --username/--password 并在 main 内登录探活。"""

    def deco(fn):
        SUBCOMMANDS[name] = {"help": help_text, "needs_session": needs_session, "func": fn}
        return fn

    return deco


# --- T6 共用核心：序号顺延 / 断点 state / scan 纯函数 / 单份上传 -----------------


_TAIL_SEQ = re.compile(r"(\d+)$")


def bump_report_id(rid: str) -> str:
    """尾序号 +1 重写（gsb-kc-cu-0001 → gsb-kc-cu-0002）；无尾数字原样返回（调用方判等兜底）。"""
    m = _TAIL_SEQ.search(rid)
    if m is None:
        return rid
    width = len(m.group(1))
    return rid[: m.start()] + f"{int(m.group(1)) + 1:0{width}d}"


def _detail_of(resp: httpx.Response) -> str:
    """安全取 40x 响应的 detail 文案（非 JSON/无 detail 均返回空串）。"""
    try:
        body = resp.json()
    except Exception:
        return ""
    detail = body.get("detail") if isinstance(body, dict) else body
    return str(detail or "")


class ImportState:
    """gsb import 断点：<csv 同名>.state.json 持 {"done": [rid]}；mark_done 即原子写盘。

    state 文件损坏视为无断点（重跑安全：已入库行再传会 409 内容重复计 skipped，不产生重复数据）。
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.done: list[str] = []
        if self.path.exists():
            try:
                self.done = [str(r) for r in json.loads(self.path.read_text(encoding="utf-8")).get("done", [])]
            except (json.JSONDecodeError, OSError, AttributeError):
                self.done = []
        self._seen = set(self.done)
        self._lock = threading.Lock()

    def is_done(self, report_id: str) -> bool:
        return report_id in self._seen

    def mark_done(self, report_id: str) -> None:
        with self._lock:
            if report_id in self._seen:
                return
            self._seen.add(report_id)
            self.done.append(report_id)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps({"done": self.done}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)  # 原子替换——进程中断不留半截 state（同 wechat auth 教训）


def gsb_scan_rows(directory, suggest_fn, limit=None, recursive=False) -> list[dict]:
    """scan 核心纯函数：glob *.docx/*.pdf（recursive 时 rglob）→ 题名=文件名去扩展 → suggest_fn
    （网络实现由 cmd_gsb_scan 包装）→ 行列表。

    行 = {**suggest, file_name(相对根目录 posix 路径), report_id, _conflict}；
    _conflict 为内部计数键（DictWriter 白名单列名，不进 CSV）。同组建议 id 第二次出现起本地
    顺延——suggest-id 只查已入库行，不知同批未入库的建议，撞号须 CLI 侧自愈。
    """
    root = Path(directory)
    glob = root.rglob if recursive else root.glob
    files = sorted(
        (p for pat in ("*.docx", "*.pdf") for p in glob(pat) if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    rows: list[dict] = []
    seen: set[str] = set()
    for f in files:
        if limit is not None and len(rows) >= limit:
            break
        suggest = dict(suggest_fn(f.stem) or {})
        rid = str(suggest.get("report_id") or "").strip()
        conflict = False
        while rid in seen:
            conflict = True
            bumped = bump_report_id(rid)
            if bumped == rid:
                break  # 无尾序号可顺延——保留重复，操作员在 CSV 中可见
            rid = bumped
        seen.add(rid)
        row = {**suggest}
        row["file_name"] = f.relative_to(root).as_posix()
        row["report_id"] = rid
        row["_conflict"] = conflict
        rows.append(row)
    return rows


def upload_one(sess, file_path: str, row: dict, defer_parse: bool = False) -> dict:
    """上传单份样例（并发工作函数，httpx Client 线程安全）。

    - multipart files={"file": (file_name, fh)} + Form report_id/stage/mineral/region（空值不透传，
      走服务端默认）；defer_parse=True 时透传 defer_parse=true——服务端 defer：不 create_run、响应
      省略 run_id，行停 uploaded，后续经 parse-batch 端点或单体 /parse 触发，且本地不再发幂等
      parse；409 detail 含「已存在」且含 report_id → 序号 +1 重试 ≤10 次；
      含 file_hash/相同内容 → 内容重复，顺延无意义，计 skipped。
    - 成功后 defer_parse=False 时再 POST /documents/{id}/parse——upload 端点自身已后台起 parse，
      此调用为幂等兜底，409「已在跑」属预期；其余 parse 失败只告警不回滚上传（文档已入库，
      行仍计成功，parse 可在 UI 重触发）。
    """
    rid = str(row["report_id"]).strip()
    file_name = (row.get("file_name") or "").strip() or Path(file_path).name
    for _ in range(10):
        data = {"report_id": rid}
        for key in ("stage", "mineral", "region"):
            val = str(row.get(key) or "").strip()
            if val:
                data[key] = val
        if defer_parse:
            data["defer_parse"] = "true"
        with open(file_path, "rb") as fh:
            resp = sess.post(f"{GSB_BASE}/documents/upload", files={"file": (file_name, fh)}, data=data)
        if resp.status_code == 409:
            # 路由侧 409 文案锚点（geo_samples/routers.py）：:79「report_id …已存在」=撞号→顺延；
            # :86「相同内容的样例已存在（file_hash 命中）」=内容重复→skipped。文案改动须双向同步。
            detail = _detail_of(resp)
            if "已存在" not in detail:
                raise RuntimeError(f"{rid}: 409 {detail}")
            if "report_id" in detail:
                nxt = bump_report_id(rid)
                if nxt == rid:
                    raise RuntimeError(f"{rid}: 409 {detail}（无尾序号可顺延）")
                rid = nxt
                continue
            return {"skipped": True, "report_id": rid, "reason": detail}  # 内容重复（file_hash 命中）
        if resp.status_code >= 400:
            raise RuntimeError(f"{rid}: HTTP {resp.status_code} {_detail_of(resp)}")
        body = resp.json()
        doc_id = (body.get("document") or {}).get("id")
        if doc_id is None:
            raise RuntimeError(f"{rid}: 上传响应缺 document.id: {body}")
        if not defer_parse:
            pr = sess.post(f"{GSB_BASE}/documents/{doc_id}/parse")
            if pr.status_code >= 400 and "已在跑" not in _detail_of(pr):
                print(f"警告: {rid} 上传成功但 parse 触发失败 HTTP {pr.status_code}: {_detail_of(pr)}", file=sys.stderr)
        return {"report_id": rid, "document_id": doc_id, "run_id": body.get("run_id")}
    raise RuntimeError(f"{rid}: 409 撞号顺延重试 10 次仍冲突")


# --- gsb 子命令组 -------------------------------------------------------------


@register("gsb", "地质样例库批量入库（scan/import/status）")
def cmd_gsb(sess, args):
    return {"scan": cmd_gsb_scan, "import": cmd_gsb_import, "status": cmd_gsb_status}[args.gsb_cmd](sess, args)


def _gsb_register_args(sp):
    sub = sp.add_subparsers(dest="gsb_cmd", required=True)
    p_scan = sub.add_parser("scan", help="扫描目录 → suggest-id → gsb_manifest.csv（题名解析在服务端）")
    _add_session_args(p_scan)  # 凭据挂 leaf——见 build_parser 内注释
    p_scan.add_argument("--dir", required=True, help="扫描根目录")
    p_scan.add_argument("--recursive", action="store_true", help="递归子目录")
    p_scan.add_argument("--limit", type=int, default=None, help="最多扫描 N 份（缺省不限）")
    p_import = sub.add_parser("import", help="按清单并发上传（断点续传 + 409 撞号顺延）")
    _add_session_args(p_import)
    p_import.add_argument("--csv", required=True, help="scan 产出的清单文件")
    p_import.add_argument("--workers", type=int, default=4, help="并发上传线程数（默认 4）")
    p_import.add_argument("--defer-parse", action="store_true", help="服务端 defer：上传透传 defer_parse=true，行停 uploaded，后续经 parse-batch 端点或单体 /parse 触发")
    p_import.add_argument("--dir", default=None, help="文件根目录（缺省为清单所在目录——scan 把清单写在扫描根）")
    p_status = sub.add_parser("status", help="文档列表摘要 + 各状态计数")
    _add_session_args(p_status)


cmd_gsb.register_args = _gsb_register_args


def _remote_suggest(sess, title: str) -> dict:
    """POST suggest-id（POST 方法 + Query 传题名；httpx params 自动 URL 编码，勿手工拼 CJK）。"""
    r = sess.post(f"{GSB_BASE}/documents/suggest-id", params={"title": title})
    r.raise_for_status()
    return r.json()


def cmd_gsb_scan(sess, args) -> int:
    root = Path(args.dir)
    if not root.is_dir():
        print(f"目录不存在: {root}", file=sys.stderr)
        return 1
    parse_errors = 0

    def tolerant_suggest(title: str) -> dict:
        """D3 容错（P4）：单文件 suggest 异常（HTTP 5xx/网络故障均属 httpx.HTTPError）→
        计 needs-review 行（词表字段置 None + gsb-auto 占位 id，同服务端 needs-review 语义；
        同批多份占位 id 由 gsb_scan_rows 冲突顺延自愈），stderr 告警后批次继续。"""
        nonlocal parse_errors
        try:
            return _remote_suggest(sess, title)
        except httpx.HTTPError as exc:
            parse_errors += 1
            print(f"警告: 题名解析失败（计 needs-review）: {title}: {exc}", file=sys.stderr)
            return {"region": None, "mineral": None, "stage": None, "confidence": "needs-review", "report_id": "gsb-auto-0001"}

    rows = gsb_scan_rows(root, tolerant_suggest, limit=args.limit, recursive=args.recursive)
    out = root / "gsb_manifest.csv"
    fields = ["file_name", "report_id", "stage", "mineral", "region", "confidence"]
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:  # utf-8-sig 供 Excel 直开
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    auto = sum(1 for r in rows if r.get("confidence") == "auto")
    review = sum(1 for r in rows if r.get("confidence") == "needs-review")
    conflicts = sum(1 for r in rows if r.get("_conflict"))
    summary = f"扫描 {len(rows)} | auto {auto} | needs-review {review} | 冲突顺延 {conflicts}"
    if parse_errors:  # D3：仅异常时追加，避免干净批次噪音
        summary += f" | 解析异常 {parse_errors}"
    print(summary)
    print(f"清单: {out}")
    return 0


def _import_row(sess, base: Path, row: dict, defer_parse: bool) -> dict:
    path = base / row["file_name"]
    if not path.is_file():
        raise FileNotFoundError(f"清单文件不存在: {path}")
    return upload_one(sess, str(path), row, defer_parse=defer_parse)


# D2 预检词表（P4，CLI 内置同款常量）：与服务端 geo_samples/schemas.py ALLOWED_STAGES/ALLOWED_MINERALS
# 同源——服务端词表变更须双向同步（此处若漂移，批量会在上传 422 上浪费 round-trips）。
GSB_STAGES = frozenset({"survey", "detail", "exploration"})
GSB_MINERALS = frozenset({"copper", "coal", "gold", "iron", "lead_zinc", "other"})
GSB_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_][a-z0-9\-_]*$")


def gsb_preflight(raw: list[dict]) -> tuple[list[dict], list[str]]:
    """D2 CSV 预检（纯函数，P4）：逐行校验 file_name 非空、report_id slug（正则 + 2-128 位）、
    stage/mineral 词表（空值合法=走服务端默认），返回 (合法行, 逐行错误文案)。

    错误文案含行号+列+值（行号按 CSV 物理行计，header 为第 1 行——操作员可在 Excel 直接定位）；
    全空白行静默跳过（保留原跳过语义）。调用方见错必须零上传返回 rc=1。
    """
    rows: list[dict] = []
    errors: list[str] = []
    for lineno, r in enumerate(raw, start=2):
        rid = str(r.get("report_id") or "").strip()
        fname = str(r.get("file_name") or "").strip()
        stage = str(r.get("stage") or "").strip()
        mineral = str(r.get("mineral") or "").strip()
        region = str(r.get("region") or "").strip()
        if not (rid or fname or stage or mineral or region):
            continue  # 全空白行
        problems: list[str] = []
        if not fname:
            problems.append("file_name 为空")
        if not (2 <= len(rid) <= 128 and GSB_SLUG_RE.match(rid)):
            problems.append(f"report_id 不是合法 slug（2-128 位小写字母/数字/连字符/下划线）: {rid!r}")
        if stage and stage not in GSB_STAGES:
            problems.append(f"stage 非法词表: {stage!r}")
        if mineral and mineral not in GSB_MINERALS:
            problems.append(f"mineral 非法词表: {mineral!r}")
        if problems:
            errors.append(f"行 {lineno}: " + "；".join(problems))
            continue
        rows.append({"file_name": fname, "report_id": rid, "stage": stage, "mineral": mineral, "region": region})
    return rows, errors


def cmd_gsb_import(sess, args) -> int:
    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"清单不存在: {csv_path}", file=sys.stderr)
        return 1
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        raw = list(csv.DictReader(fh))
    rows, preflight_errors = gsb_preflight(raw)
    if preflight_errors:
        # D2 预检门（P4）：整列 typed 错在 900 round-trips 前发现——零上传调用，修完清单再重跑
        print(f"预检失败: {len(preflight_errors)} 行有错，未上传任何文件:", file=sys.stderr)
        for msg in preflight_errors:
            print(f"  {msg}", file=sys.stderr)
        return 1
    state = ImportState(csv_path.with_suffix(".state.json"))
    base = Path(args.dir) if args.dir else csv_path.parent  # 缺省锚清单目录——scan 清单就在扫描根
    todo: list[dict] = []
    skipped = 0
    for row in rows:
        if state.is_done(row["report_id"]):
            skipped += 1
        else:
            todo.append(row)
    ok, failures = 0, []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(_import_row, sess, base, row, args.defer_parse): row for row in todo}
        for fut in as_completed(futs):
            row = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:  # 单行失败不拖垮整批
                failures.append({**row, "error": str(exc)})
                continue
            if res.get("skipped"):
                skipped += 1
            else:
                ok += 1
                state.mark_done(res["report_id"])  # 顺延后的最终 id 才是真正入库的
    if failures:
        fail_path = csv_path.parent / "gsb_import_failed.csv"
        with open(fail_path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=["file_name", "report_id", "stage", "mineral", "region", "error"], extrasaction="ignore")
            writer.writeheader()
            writer.writerows(failures)
        print(f"失败明细: {fail_path}", file=sys.stderr)
    print(f"上传 {ok} 成功 / 跳过 {skipped}（断点或 409 去重）/ 失败 {len(failures)}")
    return 0 if not failures else 1


def cmd_gsb_status(sess, args) -> int:
    items: list[dict] = []
    skip = 0
    while True:
        r = sess.get(f"{GSB_BASE}/documents", params={"skip": skip, "limit": 200})
        r.raise_for_status()
        batch = r.json().get("items", [])
        items.extend(batch)
        if len(batch) < 200:  # 末页终止（limit 上限 200 为服务端约束）
            break
        skip += 200
    print(f"{'report_id':<32} {'status':<12} parse_mode")
    for d in items:
        print(f"{str(d.get('report_id', '')):<32} {str(d.get('status', '')):<12} {d.get('parse_mode') or '-'}")
    counts = Counter(str(d.get("status") or "?") for d in items)
    print(f"共 {len(items)} 份 | " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


# --- cpa 子命令组 -------------------------------------------------------------


@register("cpa", "合同价格分析批量上传（upload）")
def cmd_cpa(sess, args):
    return {"upload": cmd_cpa_upload}[args.cpa_cmd](sess, args)


def _cpa_register_args(sp):
    sub = sp.add_subparsers(dest="cpa_cmd", required=True)
    p = sub.add_parser("upload", help="上传目录内合同（仅落 MinIO；解析统一走 pipeline/run）")
    _add_session_args(p)  # 凭据挂 leaf——见 build_parser 内注释
    p.add_argument("--dir", required=True, help="合同文件目录（*.pdf/*.docx）")
    p.add_argument("--trigger-parse", action="store_true", help="全部上传后触发一次解析管线（全局互斥，409=已有 parse 在跑）")


cmd_cpa.register_args = _cpa_register_args


def cmd_cpa_upload(sess, args) -> int:
    root = Path(args.dir)
    if not root.is_dir():
        print(f"目录不存在: {root}", file=sys.stderr)
        return 1
    files = sorted((p for pat in ("*.pdf", "*.docx") for p in root.glob(pat) if p.is_file()), key=lambda p: p.name)
    uploaded = skipped = failed = 0
    for f in files:
        try:
            with open(f, "rb") as fh:
                r = sess.post(f"{CPA_BASE}/documents/upload", files={"file": (f.name, fh)})  # 仅 file 字段
        except (httpx.HTTPError, OSError) as exc:  # OSError：文件读开失败（权限/被删）同样计失败
            failed += 1
            print(f"失败: {f.name}: {exc}", file=sys.stderr)
            continue
        if r.status_code == 409:
            skipped += 1  # 内容重复（file_hash 命中）——幂等跳过不重传
            continue
        if r.status_code >= 400:
            failed += 1
            print(f"失败: {f.name}: HTTP {r.status_code} {_detail_of(r)}", file=sys.stderr)
            continue
        uploaded += 1
    rc = 0 if failed == 0 else 1
    if args.trigger_parse and files:  # 只在末尾触发一次，不逐份
        try:
            r = sess.post(f"{CPA_BASE}/pipeline/run", json={"mode": "table", "trigger": "manual"})
        except (httpx.HTTPError, OSError) as exc:
            print(f"pipeline 触发异常: {exc}", file=sys.stderr)
            return 1
        if r.status_code == 409:
            print("已有 parse 在跑（全局互斥）——本次未触发新解析")
        elif r.status_code >= 400:
            print(f"pipeline 触发失败 HTTP {r.status_code}: {_detail_of(r)}", file=sys.stderr)
            rc = 1
        else:
            print(f"解析管线已触发: run_id={r.json().get('run_id')}")
    print(f"上传 {uploaded} / 跳过 {skipped}（内容重复）/ 失败 {failed}（共 {len(files)} 份）")
    return rc


# --- ore-pack 子命令组（P5 T8，服务端型薄适配：抽取/审阅都在服务端跑）-----------


# 词表单源（CLI 侧常量，同 gsb_preflight 模式）：与服务端 ore_pack_schema.KNOWN_SLUGS 同步——
# 5 production slug，other 不孵化（README 契约 §5）。
ORE_PACK_MINERALS = frozenset({"copper", "coal", "gold", "iron", "lead_zinc"})


@register("ore-pack", "矿种包孵化：extract 触发 LLM 抽取草稿 / status 草稿清单")
def cmd_ore_pack(sess, args):
    return {"extract": cmd_ore_pack_extract, "status": cmd_ore_pack_status}[args.ore_pack_cmd](sess, args)


def _ore_pack_register_args(sp):
    sub = sp.add_subparsers(dest="ore_pack_cmd", required=True)
    p_extract = sub.add_parser("extract", help="触发 {mineral} 草稿抽取（服务端后台；草稿落表经 status 查看）")
    _add_session_args(p_extract)  # 凭据挂 leaf——见 build_parser 内注释
    p_extract.add_argument("--mineral", required=True, help="矿种 slug（copper/coal/gold/iron/lead_zinc；other 不孵化）")
    p_extract.add_argument("--slices", nargs="+", required=True, help="切片路径（仓库根相对或绝对，≥1，每片截断 8000 字符）")
    p_status = sub.add_parser("status", help="草稿清单 + 各审阅状态计数")
    _add_session_args(p_status)
    p_status.add_argument("--mineral", default=None, help="按矿种过滤")
    p_status.add_argument("--review-status", dest="review_status", default=None, help="draft/approved/rejected")


cmd_ore_pack.register_args = _ore_pack_register_args


def cmd_ore_pack_extract(sess, args) -> int:
    """词表预检（省 round-trip，同 gsb_preflight 模式）→ POST extract；抽取为服务端后台任务。"""
    if args.mineral not in ORE_PACK_MINERALS:
        print(f"mineral 非法: {args.mineral}（须 ∈ {sorted(ORE_PACK_MINERALS)}；other 不孵化）", file=sys.stderr)
        return 1
    r = sess.post(f"{GSB_BASE}/ore-packs/extract", json={"mineral": args.mineral, "slice_paths": args.slices})
    if r.status_code != 200:
        print(f"触发失败 [{r.status_code}]: {_detail_of(r)}", file=sys.stderr)
        return 1
    body = r.json()
    print(f"已入队 mineral={body['mineral']} slices_hash={str(body.get('slices_hash', ''))[:12]}…——抽取在服务端后台跑，草稿落表后经 ore-pack status 查看")
    return 0


def cmd_ore_pack_status(sess, args) -> int:
    """GET drafts（可选 mineral/review_status 过滤）→ 逐行摘要 + 状态计数。"""
    params = {"mineral": args.mineral, "review_status": args.review_status}
    r = sess.get(f"{GSB_BASE}/ore-packs/drafts", params=params)
    if r.status_code != 200:
        print(f"查询失败 [{r.status_code}]: {_detail_of(r)}", file=sys.stderr)
        return 1
    items = r.json().get("items", [])
    counts = Counter(d.get("review_status") for d in items)
    for d in items:
        errs = len(d.get("errors") or [])
        flag = f"错误 {errs}" if errs else ("可过审" if d.get("draft_json") else "失败草稿")
        print(f"{str(d.get('id'))[:8]}  {d.get('mineral', '?'):<10} {d.get('review_status', '?'):<9} {flag}  {d.get('created_at', '')}")
    print(f"共 {len(items)} 份草稿 | 待审 {counts.get('draft', 0)} | 过审 {counts.get('approved', 0)} | 驳回 {counts.get('rejected', 0)}")
    return 0


# --- license 子命令组（本地工具，免会话）--------------------------------------


@register("license", "本地 license 生成（免会话，不连服务端）", needs_session=False)
def cmd_license(args):
    return {"generate": cmd_license_generate}[args.license_cmd](args)


def _license_register_args(sp):
    sub = sp.add_subparsers(dest="license_cmd", required=True)
    p = sub.add_parser("generate", help="从 request JSON 生成签名 license 文件")
    p.add_argument("request_file", help="license request JSON（须含 machine_id）")
    p.add_argument("--days", type=int, default=None, help="有效期天数（与 --permanent 互斥语义，后者优先）")
    p.add_argument("--permanent", action="store_true", help="永久授权")
    p.add_argument("--all-modules", action="store_true", help="启用全部模块")
    p.add_argument("--modules", default=None, help="逗号分隔模块清单（如 project,docmgr,knowledge）")
    p.add_argument("--customer", default="", help="客户名")
    p.add_argument("--max-users", type=int, default=None, help="最大用户数")
    p.add_argument("--features", default=None, help="k=v 逗号对（如 max_projects=10,sso=true）")
    p.add_argument("--output", default="license.lic", help="输出文件路径（默认 license.lic）")


cmd_license.register_args = _license_register_args


def _load_license_generator():
    """按文件路径直载 tools/license/license_generator（batch-cli T6 review Important-1）：
    importlib.util.spec_from_file_location + exec_module，**不改 sys.path、不触发 import
    机器按名搜索**——同进程其他子命令/测试环境不会被 license 目录污染；sys.modules
    预检兼作缓存（也使测试可用 monkeypatch.setitem(sys.modules, ...) 注入替身）。
    """
    if "license_generator" in sys.modules:
        return sys.modules["license_generator"]
    lg_file = Path(__file__).resolve().parent / "license" / "license_generator.py"
    if not lg_file.is_file():
        print(f"license_generator 不存在: {lg_file}", file=sys.stderr)
        return None
    try:
        spec = importlib.util.spec_from_file_location("license_generator", lg_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # 先注册再 exec——模块内若自引用/子导入可见自身
        spec.loader.exec_module(module)
    except Exception as exc:  # ImportError/语法/依赖缺失（如 cryptography）一律人话报错
        sys.modules.pop("license_generator", None)  # 别留半初始化的坏缓存
        print(f"license_generator 加载失败（{exc}）——确认 tools/license/ 存在且依赖（cryptography）已装", file=sys.stderr)
        return None
    return module


def cmd_license_generate(args) -> int:
    lg = _load_license_generator()
    if lg is None:
        return 1
    out_path = Path(args.output)
    if out_path.exists():
        out_path.unlink()  # 守卫以「本次生成」为准——预存在旧文件会掩盖静默失败
    try:
        lg.generate_license(
            request_file=args.request_file,
            days=args.days,
            permanent=args.permanent,
            all_modules=args.all_modules,
            modules=args.modules,
            customer=args.customer,
            max_users=args.max_users,
            features=args.features,
            output=str(out_path),
        )
    except Exception as exc:
        print(f"license 生成异常: {exc}", file=sys.stderr)
        return 1
    if not out_path.exists():
        # license_generator 对 machine_id 缺失静默 return（print 一句就返回 None）——
        # 唯一可靠的失败信号是输出文件未产生。
        print(
            "license 生成失败：输出文件未产生（常见根因：request.json 缺 machine_id——license_generator 静默返回；另查私钥文件存在）",
            file=sys.stderr,
        )
        return 1
    print(f"license 已生成: {out_path}")
    return 0


def _add_session_args(sp):
    """平铺命令与嵌套组 leaf 子命令共用的凭据参数。

    密码优先 EAI_PASSWORD env（--password 会进 shell history）；env 未设时才强制 --password。
    勿写 required=True + default：argparse 对 required 参数无视 default，env 回退会彻底失效。
    """
    sp.add_argument("--username", required=True, help="工号或邮箱")
    sp.add_argument(
        "--password",
        default=os.environ.get("EAI_PASSWORD"),
        required="EAI_PASSWORD" not in os.environ,
        help="密码（仅进程内会话；推荐 EAI_PASSWORD env 免进 shell history）",
    )


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="eai.py", description="EAI 系统统一模块运维 CLI")
    ap.add_argument("--base-url", default="http://localhost:2026")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, meta in SUBCOMMANDS.items():
        sp = sub.add_parser(name, help=meta["help"])
        nested = hasattr(meta["func"], "register_args")  # T6 嵌套组命令（gsb/cpa/license）
        if meta["needs_session"] and not nested:
            _add_session_args(sp)
        if nested:
            # 嵌套组命令不在父级挂凭据：argparse 父级选项必须出现在子命令名之前，
            # 而自然调用（计划 T8 实跑示例）`eai.py gsb scan --dir X --username u` 把凭据
            # 放在 leaf 之后——凭据由各 leaf 子命令经 _add_session_args 自行挂载。
            meta["func"].register_args(sp)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    meta = SUBCOMMANDS[args.command]
    if meta["needs_session"]:
        # 顶层错误面：限流/认证失败人话报错，不裸 traceback。try 只罩登录+探活——
        # 子命令自身的 HTTPStatusError（如 409）不得误报成「登录失败」。
        try:
            sess = login(args.base_url, args.username, args.password)
            if not probe(sess):
                print("会话探活失败", file=sys.stderr)
                return 2
        except LoginLocked as e:
            print(f"登录限流: {e}", file=sys.stderr)
            return 3
        except httpx.HTTPStatusError as e:
            print(f"登录失败: {e.response.status_code}（检查工号/密码）", file=sys.stderr)
            return 3
        return meta["func"](sess, args)
    return meta["func"](args)


if __name__ == "__main__":
    sys.exit(main())
