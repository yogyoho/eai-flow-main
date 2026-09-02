#!/usr/bin/env python3
"""geo_bank_ragflow_acceptance.py — RAGFlow 分块质量验收 harness（geo-sample-bank Phase 2 T8）。

一次性人工验收工具（非 CI；单测中 RAGFlow 交互全部 Fake——backend/tests/test_geo_sample_bank_compile.py）。
真跑验收命令：

    cd backend && PYTHONPATH=. uv run python ../scripts/geo_bank_ragflow_acceptance.py --limit 10

前置条件（缺任一 → rc=2 拒绝运行）：
  - env GSB_RAGFLOW_ACCEPTANCE_DATASET_ID=<验收专用 scratch dataset id>——必填，绝不打生产固体矿产库；
  - RAGFlow 连接可用：extensions_config.json 的 ragflow.api_key/base_url（值可引用 $RAGFLOW_* env），
    与 service.push_slices_to_ragflow 同款构造 RAGFlowClient(api_key, base_url)（懒 import）；
  - bank_compile 已产出真实切片 skills/public/geological-report/references/samples_bank/<stage>/slices/。

流程：读前 N 片（默认 10，--limit；跨 stage 混合按路径排序）→ 验收 dataset 幂等上传（分页
list_documents 建 name→id、同名先删 → upload(<rid>__<sec>.md) → parse）→ 逐片
wait_for_parsing_complete(timeout=120, poll_interval=5) 轮询解析完成 → list_chunks 取回 chunk
content 拼接该片全文 → 四项断言（逐片 PASS/FAIL）：
  a) 节号完整性：片首标记行【矿种】…｜【节号】… 出现在拼接文本前 200 字符内（首块含标记）；
  b) 标题未被切散：源片每个 ## N 一级节标题行在拼接文本中出现（子节标题抽查首个）；
  c) 表格完整性：源片 md 表格行与拼接文本按行计数一致（行文本空格归一后精确匹配；源片无
     表格则跳过）——检出 v0.25.3「md 表格重复」缺陷（重复时计数 > 源）；
  d) 父块返回：任一 chunk content 包含完整 ## N 标题 + 其后 50 字符（parent_child 父块抽查；
     切片本身标题后不足 50 字符时放宽为标题在场）。

等待解析说明：验收 dataset 文档数 ≤10 且逐片串行等待，不触发 service.push_slices_to_ragflow
为此绝不等待的「>100 文档 dataset 轮询恒超时」陷阱（场景不同）；文档状态取 run 字段
（DONE/FAIL/…），失败详情在 progress_msg（client.py wire 契约）。任何 RAGFlow 调用异常
（HTTPStatusError/TimeoutError/…）→ 该片记 FAIL（含异常摘要）继续，绝不中断整批。

输出：逐片逐项 PASS/FAIL/SKIP checklist + 汇总 `ACCEPTANCE: X/Y PASS`；任何 FAIL → rc=1，
全 PASS → rc=0。FAIL 处置序：
  ① 该片降纯文本 + 标记行重编译重评；
  ② 仍 FAIL → RAGFlow 镜像升级评估（geo-sample-bank spec §3.4 触发式升级）。

--keep：跳过结束清理；默认结束删除本脚本上传的全部文档（delete-by-name，验收不留痕）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BANK = REPO_ROOT / "skills" / "public" / "geological-report" / "references" / "samples_bank"
ENV_DATASET_ID = "GSB_RAGFLOW_ACCEPTANCE_DATASET_ID"
WAIT_TIMEOUT_S = 120
POLL_INTERVAL_S = 5
MARKER_IN_HEAD_CHARS = 200  # a) 标记行须落在拼接文本前多少字符内
PARENT_PROBE_CHARS = 50  # d) 父块须覆盖标题行之后的字符数

MARKER_LINE_RE = re.compile(r"^【矿种】.+｜【节号】.+")
TOP_HEADING_RE = re.compile(r"^##\s+\d+(?:\.\d+)*\s", re.MULTILINE)  # 一级节标题（## N；### 不匹配）
SUB_HEADING_RE = re.compile(r"^###\s+\d+(?:\.\d+)*\s", re.MULTILINE)  # 子节标题（### N.M）


def collect_slices(bank: Path, limit: int) -> list[Path]:
    """前 N 片：samples_bank/<stage>/slices/ch*/*.md，跨 stage 混合按路径排序取前 limit。"""
    return sorted(bank.glob("*/slices/*/*.md"))[:limit]


def _heading_matches(text: str, pattern: re.Pattern[str]) -> list[tuple[str, int, int]]:
    """[(标题行全文, 行 start, 行 end)]——MULTILINE 逐行锚定，行全文供精确包含断言。"""
    out: list[tuple[str, int, int]] = []
    for m in pattern.finditer(text):
        end = text.find("\n", m.start())
        end = len(text) if end == -1 else end
        out.append((text[m.start() : end].rstrip("\r"), m.start(), end))
    return out


def _table_rows(text: str) -> list[str]:
    """md 表格行（|…| 形态）逐行空格归一化后供计数。

    RAGFlow 分块常压缩单元格空格（chunk `| ZK1 |12.5|` vs 源 `| ZK1 | 12.5 |`）——先
    `" ".join(ln.split())` 归一空白串、再收敛管道符两侧空格，两侧同规则计数，避免系统性误报。
    """
    rows: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|") and s.endswith("|"):
            rows.append(re.sub(r"\s*\|\s*", "|", " ".join(s.split())))
    return rows


def check_slice(src: str, joined: str, contents: list[str]) -> list[tuple[str, str, str]]:
    """四项断言（a 节号 / b 标题 / c 表格 / d 父块）。返回 [(item, status, detail)]，status ∈ pass/fail/skip。"""
    items: list[tuple[str, str, str]] = []

    # a) 节号完整性：标记行出现在拼接文本前 200 字符内（首块含标记）
    marker = next((ln.strip() for ln in src.splitlines() if MARKER_LINE_RE.match(ln.strip())), None)
    if marker is None:
        items.append(("marker", "fail", "源片无【矿种】…｜【节号】… 标记行（非本管线产物？）"))
    elif marker in joined[:MARKER_IN_HEAD_CHARS]:
        items.append(("marker", "pass", "首块含标记行"))
    else:
        items.append(("marker", "fail", f"标记行未出现在拼接文本前 {MARKER_IN_HEAD_CHARS} 字符内（首块缺标记）：{marker[:40]}"))

    # b) 标题未被切散：每个 ## N 一级节标题行都在拼接文本中；子节标题抽查首个
    top = _heading_matches(src, TOP_HEADING_RE)
    subs = _heading_matches(src, SUB_HEADING_RE)
    missing = [line for line, _s, _e in top if line not in joined]
    if subs and subs[0][0] not in joined:
        missing.append(subs[0][0])
    if missing:
        items.append(("headings", "fail", "标题缺失/被切散：" + " ； ".join(t[:50] for t in missing)))
    else:
        detail = f"{len(top)} 个一级节标题在拼接文本中" + (f"（子节抽查 {subs[0][0][:30]}）" if subs else "")
        items.append(("headings", "pass", detail))

    # c) 表格完整性：源片每个表格行按行精确计数 == 拼接文本计数（重复缺陷 → 计数 > 源）
    src_rows = _table_rows(src)
    if not src_rows:
        items.append(("table", "skip", "源片无表格"))
    else:
        want, got = Counter(src_rows), Counter(_table_rows(joined))
        bad = [r for r in want if got[r] != want[r]]
        if bad:
            row = bad[0]
            items.append(("table", "fail", f"表格行计数不符（源 {want[row]} 次 / 拼接 {got[row]} 次）：{row[:50]}——疑 md 表格重复缺陷"))
        else:
            items.append(("table", "pass", f"{len(src_rows)} 行表格逐一计数一致"))

    # d) 父块返回：任一 chunk content 包含完整 ## N 标题 + 其后 50 字符（标题后不足 50 字符放宽为标题在场）
    parent_fail: str | None = None
    for line, start, end in top:
        tail = src[end : end + PARENT_PROBE_CHARS]
        if len(tail) < PARENT_PROBE_CHARS:
            ok = any(line in c for c in contents)
            how = "标题在场（放宽：标题后不足 50 字符）"
        else:
            probe = src[start : end + PARENT_PROBE_CHARS]
            ok = any(probe in c for c in contents)
            how = "标题+50 字符"
        if not ok:
            parent_fail = f"无任一 chunk 完整包含一级节标题及其后内容（{how}）：{line[:40]}"
            break
    if parent_fail:
        items.append(("parent", "fail", parent_fail))
    else:
        items.append(("parent", "pass", f"{len(top)} 个一级节标题命中父块" if top else "片内无一级节标题"))
    return items


async def _list_docs_by_name(client, dataset_id: str) -> dict[str, str]:
    """分页 list_documents 建 name→id（total-aware 分页，同 service.push_slices_to_ragflow）。"""
    existing: dict[str, str] = {}
    page = 1
    while True:
        resp = await client.list_documents(dataset_id, page=page, size=100)
        payload = resp.get("data") or {}
        docs = payload.get("docs", []) if isinstance(payload, dict) else list(payload)
        if not docs:
            break
        existing.update({d["name"]: d["id"] for d in docs})
        total = payload.get("total") if isinstance(payload, dict) else None
        if total is None or page * 100 >= int(total):
            break
        page += 1
    return existing


async def wait_for_parsing_complete(client, dataset_id: str, document_id: str, timeout: int = WAIT_TIMEOUT_S, poll_interval: float = POLL_INTERVAL_S) -> None:
    """轮询 get_document 直到解析 DONE；FAIL → RuntimeError(progress_msg)；超时 → TimeoutError。

    文档解析状态是 run 字段（UNSTART/RUNNING/CANCEL/DONE/FAIL），失败详情在 progress_msg。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        doc = (await client.get_document(dataset_id, document_id)).get("data") or {}
        state = str(doc.get("run") or "").upper()
        if state == "DONE":
            return
        if state == "FAIL":
            raise RuntimeError(f"parse failed: {doc.get('progress_msg') or 'no detail'}")
        if loop.time() >= deadline:
            raise TimeoutError(f"parse not DONE within {timeout}s (run={state or 'unknown'})")
        await asyncio.sleep(poll_interval)


async def _fetch_chunk_contents(client, dataset_id: str, document_id: str) -> list[str]:
    """分页取回该文档全部 chunk 的 content；DONE 后 0 chunk 视为异常（分块产出为空）。"""
    contents: list[str] = []
    page = 1
    while True:
        resp = await client.list_chunks(dataset_id, document_id, page=page, size=100)
        payload = resp.get("data") or {}
        chunks = payload.get("chunks", []) if isinstance(payload, dict) else list(payload)
        if not chunks:
            break
        contents.extend(str(c.get("content") or "") for c in chunks)
        total = payload.get("total") if isinstance(payload, dict) else None
        if total is None or page * 100 >= int(total):
            break
        page += 1
    if not contents:
        raise RuntimeError("parse DONE but 0 chunks——分块产出为空")
    return contents


def _print_slice(out, idx: int, total: int, path: Path, items: list[tuple[str, str, str]], ok: bool) -> None:
    rel = f"{path.parents[2].name}/{path.parent.name}/{path.name}"
    print(f"== [{idx}/{total}] {rel}", file=out)
    for item, status, detail in items:
        mark = "PASS" if status == "pass" else ("FAIL" if status == "fail" else "SKIP")
        print(f"  {item:<9} {mark}{('  ' + detail) if detail else ''}", file=out)
    print(f"  -> {'PASS' if ok else 'FAIL'}", file=out)


async def run_acceptance(slices: list[Path], dataset_id: str, client, keep: bool = False, wait_timeout: int = WAIT_TIMEOUT_S, poll_interval: float = POLL_INTERVAL_S, out=None) -> int:
    """验收主体（切片→上传→解析等待→取回→四项断言→逐片输出→清理）。返回 rc：0 全 PASS / 1 有 FAIL。

    单片任何环节异常只记该片 FAIL（含异常摘要）继续下一片；upload 失败的文档不进清理清单。
    """
    out = sys.stdout if out is None else out
    try:
        existing = await _list_docs_by_name(client, dataset_id)
    except Exception as exc:
        print(f"[acceptance] list_documents 失败（{type(exc).__name__}: {exc}）——RAGFlow 不可达？", file=sys.stderr)
        return 1

    uploaded: dict[str, str] = {}  # 本脚本上传的全部文档 name→id（默认结束 delete-by-name 清理）
    evaluated: list[tuple[Path, list[tuple[str, str, str]], bool]] = []
    try:
        for idx, path in enumerate(slices, start=1):
            name = path.name
            try:
                if name in existing:
                    await client.delete_document(dataset_id, existing[name])  # 幂等重跑：同名先删
                up = await client.upload_document(dataset_id, str(path), file_name=name)
                doc_id = (up.get("data") or {}).get("id")
                if not doc_id:
                    raise RuntimeError("upload response missing document id")
                uploaded[name] = doc_id
                await client.parse_document(dataset_id, doc_id)
                await wait_for_parsing_complete(client, dataset_id, doc_id, timeout=wait_timeout, poll_interval=poll_interval)
                contents = await _fetch_chunk_contents(client, dataset_id, doc_id)
                src = await asyncio.to_thread(path.read_text, encoding="utf-8")
                joined = "".join(contents)
                items = check_slice(src, joined, contents)
            except Exception as exc:  # 单片异常只记 FAIL，绝不中断整批
                items = [("pipeline", "fail", f"{type(exc).__name__}: {exc}")]
            ok = all(status != "fail" for _item, status, _d in items)
            evaluated.append((path, items, ok))
            _print_slice(out, idx, len(slices), path, items, ok)
    finally:
        if not keep and uploaded:
            for cname, cid in uploaded.items():
                try:
                    await client.delete_document(dataset_id, cid)
                except Exception as exc:
                    print(f"[acceptance] 清理失败 {cname}（id={cid}）：{exc}——请在 RAGFlow 控制台手动删除", file=sys.stderr)

    passed = sum(1 for _p, _i, ok in evaluated if ok)
    print(f"\nACCEPTANCE: {passed}/{len(evaluated)} PASS", file=out)
    if passed < len(evaluated):
        print("FAIL 处置序：① 该片降纯文本 + 标记行重编译重评 → ② 仍 FAIL → RAGFlow 镜像升级评估（spec §3.4 触发式升级）", file=out)
        return 1
    return 0


def _build_client():
    """与 service.push_slices_to_ragflow 同款构造（懒 import——脚本独立于 gateway 进程零启动依赖）。"""
    from app.extensions.config import get_extensions_config  # lazy
    from app.extensions.knowledge import client as ragflow_client_mod  # lazy

    cfg = get_extensions_config().ragflow
    return ragflow_client_mod.RAGFlowClient(api_key=cfg.api_key, base_url=cfg.base_url)


def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="RAGFlow 分块质量验收 harness（geo-sample-bank Phase 2 T8，一次性人工验收）")
    ap.add_argument("--limit", type=int, default=10, help="取前 N 片（跨 stage 混合按路径排序；默认 10）")
    ap.add_argument("--keep", action="store_true", help="跳过结束清理（保留本脚本上传的验收文档）")
    ap.add_argument("--bank", default=None, help="切片库根目录（默认技能 references/samples_bank）")
    args = ap.parse_args(argv)

    try:  # Windows 控制台非 UTF-8 codepage 时 print 中文不至于崩（GBK 覆盖常用字，仅兜底）
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

    dataset_id = os.environ.get(ENV_DATASET_ID, "").strip()
    if not dataset_id:
        print(f"[acceptance] 缺 env {ENV_DATASET_ID}（验收专用 scratch dataset id）——拒绝运行，绝不打生产固体矿产库", file=sys.stderr)
        return 2

    bank = Path(args.bank) if args.bank else DEFAULT_BANK
    slices = collect_slices(bank, args.limit)
    if not slices:
        print(f"[acceptance] 无切片：{bank}/*/slices/*/*.md——先跑 bank_compile 产出真实切片", file=sys.stderr)
        return 2

    client = _build_client()
    return asyncio.run(run_acceptance(slices, dataset_id, client, keep=args.keep))


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
