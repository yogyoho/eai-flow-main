"""权威状态防篡改签名(.meta.json)——共享守卫模块(纯 stdlib, 无 LLM)。

回放实证(2026-08-18 内蒙古财经大学线程 bfa917ce): agent 用 write_file 直写
state/*.json 或 rm -rf 后, 下游脚本只报"结构异常/缺键"等远处症状, agent 靠试错
绕行烧掉整轮上下文(单 run 91 次 LLM 调用)。本模块把状态污染变成一声带恢复指令
的硬错误(退出码 1), 恢复指令指向"重跑脚本", 不给手写/删除留口子。

契约:
- 登记(sign_state_files): 写盘方在原子写出权威状态文件后, 对 <state_dir>/.meta.json
  登记这些文件名的 sha256。既有登记合并保留(ingest 登 sections, extract merge 登
  三状态文件, merge_addenda/score_simulate 重写 clauses 后重登)。merge_addenda 的
  台账/增量清单自有产物同样写盘即签, 合法删除同步撤销登记(unsign_state_files)。
- 校验(verify_state_files): 读盘方在装载前对 <state_dir> 已登记的每个文件复核
  sha256; 文件缺失/内容不符 → 返回问题清单(非空即硬错误, 编排方打印后退出码 1)。
  另拦注入(F4, 回放实证 2026-08-16 江西师大线程 1a1b72bf): 权威四件套在盘但未登记
  也算问题——agent 脚本外手写全新 state/clauses.json 可绕过"只复核已登记名"的旧逻辑,
  被下游 build_output 当真数据装载。
- 兼容(v3 装载角色分流): 缺 .meta.json 不再一刀切放行。按读方角色分流——生产者
  (对自己的产物有写权: ingest→sections, extract merge→clauses/structure/rubric,
  responses merge→responses, merge_addenda/score_simulate reingest→clauses)对未登记
  自有产物走重建收编并立即登记(rebuildable 通道); 纯消费者(build_output/check_format/
  extract validate/responses validate/ingest --resume/score_simulate 非 reingest)读任何
  权威状态文件前必须验登记且 sha256 匹配, 否则硬错误退出, 错误行点名"重跑产生它的脚本"。
- 幂等: meta 不含时间戳、键序排序落盘, 同内容重签字节级不变(重复合并测试依赖)。
- sign 收紧(v3, bug-2189): CLI sign 仅服务确认门1 class 回写这一条获准通道——
  --confirm-gate1-edit 必带且 --files 仅 clauses.json、既有登记签名且内容确有变更、
  文件含 class 字段, 三条件同时满足才放行; 从未登记过的文件即使带旗标也拒绝首签。
  合法首登记唯一路径 = 管线脚本写盘时的 sign_state_files 自动签名。任一不满足按
  洗白拒绝并记 resign_log 审计。

注意: 守卫防的是"脚本外直写/误删"的静默污染; 有意 rm 整个 state 目录连 .meta.json
一起删的破坏只能靠沙箱层只读护栏(harness 改动, 本技能层不实现)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

META_NAME = ".meta.json"
# 权威五件套: 管线脚本落盘并签名、下游装载的唯一状态文件集合。
# entities_whitelist.json(agent 按设计手写, 永不签名)与 snapshot.json(非装载路径)不在其列。
AUTHORITATIVE_FILES = ("sections.json", "clauses.json", "structure.json", "rubric.json", "responses.json")
# 装载角色分流(v3): 每个权威文件的合法产生者。消费者硬错误的恢复指令点名该脚本
# (不把"重跑产生该文件的脚本"留成泛指让 agent 自己猜), 生产者 rebuildable 通道的
# 收编重建同样指向它。新增权威文件必须同步登记产生者。
PRODUCER_HINTS = {
    "sections.json": "ingest.py",
    "clauses.json": "extract.py merge",
    "structure.json": "extract.py merge",
    "rubric.json": "extract.py merge",
    "responses.json": "responses.py merge",
    # merge_addenda 自有产物(不在权威五件套, 不参与在盘未登记注入检查; 登记后用于
    # 篡改拦截与恢复指令点名产生脚本)
    "merge_ledger.json": "merge_addenda.py",
    "addendum_entities_pending.json": "merge_addenda.py",
}


def _recovery_hint(name: str) -> str:
    producer = PRODUCER_HINTS.get(name, "对应管线脚本")
    return (
        f"恢复方法: 重跑产生该文件的脚本重建({producer}; 未变输入按内容指纹保号, 已提取候选不失效); 严禁手写 JSON 或删除文件绕过"
    )


def _meta_path(state_dir: str | Path) -> Path:
    return Path(state_dir) / META_NAME


def _load_meta(state_dir: str | Path) -> dict:
    path = _meta_path(state_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        # meta 自身损坏: 视同无签名放行(不让守卫自身故障阻断管线), 登记时会重写修复
        return {}


def _sha256_file(path: Path) -> str:
    """对文件内容做 sha256; 跳过 UTF-8 BOM——BOM 是编辑器编码工件不是内容篡改
    (既有 BOM 容忍测试: 编辑器重写加 BOM 后内容未变, 校验应放行)。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        first = fh.read(65536)
        if first.startswith(b"\xef\xbb\xbf"):
            first = first[3:]
        digest.update(first)
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_file(path: str | Path) -> str:
    """公开壳: 与签名登记同口径的文件 sha256(BOM 容忍)。白名单消费留痕
    (build_output 回执 whitelist_sha256 / snapshot 新鲜度比对)必须走它, 保证可比。"""
    return _sha256_file(Path(path))


def sign_state_files(state_dir: str | Path, names: list[str]) -> None:
    """写盘方登记权威状态文件签名(合并既有登记, 原子落盘, 字节级幂等)。"""
    meta = _load_meta(state_dir)
    signatures = meta.get("signatures")
    signatures = dict(signatures) if isinstance(signatures, dict) else {}
    for name in names:
        signatures[name] = _sha256_file(Path(state_dir) / name)
    meta["signatures"] = signatures
    _atomic_write_meta(state_dir, meta)


def unsign_state_files(state_dir: str | Path, names: list[str]) -> None:
    """写盘方合法删除已登记文件时同步撤销登记(防 verify 误报"已登记但不存在")。

    无登记/目标未登记为 no-op(不落盘); 撤销后同内容重写须重新 sign_state_files。"""
    meta = _load_meta(state_dir)
    signatures = meta.get("signatures")
    if not isinstance(signatures, dict) or not any(name in signatures for name in names):
        return
    for name in names:
        signatures.pop(name, None)
    meta["signatures"] = signatures
    _atomic_write_meta(state_dir, meta)


def _atomic_write_meta(state_dir: str | Path, meta: dict) -> None:
    path = _meta_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def sign_all_authoritative(state_dir: str | Path) -> None:
    """把在盘的权威文件全部纳入签名登记(不存在者跳过)。

    供"重写 clauses 后只签 clauses"的下游脚本(merge_addenda/score_simulate)收编
    工作区其余权威文件: 脚本刚校验并消费过它们, 以当前内容冻结基线——消除
    "部分签名"形态(否则 F4 在盘未登记拦截会把同工作区里未签的 structure/rubric
    误报为注入)。此后任何脚本外改动都会被复核抓获。"""
    present = [name for name in AUTHORITATIVE_FILES if (Path(state_dir) / name).is_file()]
    if present:
        sign_state_files(state_dir, present)


def is_unregistered(state_dir: str | Path, name: str) -> bool:
    """该权威文件在盘但未登记签名(前签名时代遗留/脚本外手写)。产物脚本据此走"重建收编"分支。"""
    meta = _load_meta(state_dir).get("signatures")
    return (Path(state_dir) / name).is_file() and not (isinstance(meta, dict) and name in meta)


def _contains_class_key(path: Path) -> bool:
    """sign 条件(c): 文件 JSON 树中含 class 字段(确认门1 回写对象所在)。
    解析失败视为不满足(非 JSON 文件本就不该走 class 回写通道)。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "class" in node:
                return True
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return False


def _audit_resign(state_dir: str | Path, entry: dict) -> None:
    """向 .meta.json 的 resign_log 追加一条审计(成功重签与被拒洗白都记, 末条去重)。"""
    meta = _load_meta(state_dir)
    log = meta.get("resign_log")
    log = list(log) if isinstance(log, list) else []
    if not (log and log[-1] == entry):
        log.append(entry)
    meta["resign_log"] = log
    _atomic_write_meta(state_dir, meta)


def verify_state_files(state_dir: str | Path, *, rebuildable: tuple[str, ...] = ()) -> list[str]:
    """读盘前校验已登记签名; 返回问题清单(空=通过或无签名可校验)。

    注意"在盘但未登记"检查必须在 signatures 为空(.meta.json 缺失)时也执行——
    E2E 实证(bug-2189 复测): agent 手写 sections.json 且从未有 .meta.json 时,
    旧版在此提前 return [], 下游 extract validate 只报远处症状(锚点全隔离),
    agent 反复考古烧尽 recursion 预算。空登记 + 在盘权威文件 = 注入信号。

    rebuildable 例外: 产物脚本(ingest 之于 sections.json, extract merge 之于
    clauses/structure/rubric, responses merge 之于 responses.json, merge_addenda/
    score_simulate reingest 之于 clauses.json)对"自有产物未登记"(前签名时代遗留)
    走重建收编而非拒绝——否则 RECOVERY_HINT 承诺的"重跑产生该文件的脚本重建"自我
    死锁。已登记内容被改/被删永远拦截(篡改无豁免); 非自有文件的未登记注入同样拦截。"""
    signatures = _load_meta(state_dir).get("signatures")
    if not isinstance(signatures, dict):
        signatures = {}
    problems: list[str] = []
    for name in sorted(signatures):
        path = Path(state_dir) / name
        if not path.is_file():
            problems.append(f"state/{name} 已登记签名但文件不存在(疑似被 rm 删除); {_recovery_hint(name)}")
        elif _sha256_file(path) != signatures[name]:
            problems.append(f"state/{name} 内容与脚本落盘签名不符(疑似 write_file 直写/手工编辑); {_recovery_hint(name)}")
    for name in AUTHORITATIVE_FILES:
        if name not in signatures and (Path(state_dir) / name).is_file() and name not in rebuildable:
            producer = PRODUCER_HINTS.get(name, "对应管线脚本")
            problems.append(f"state/{name} 在盘但未登记签名(疑似脚本外直写/手写注入); 恢复方法: 该文件非脚本产出, 请重跑产生它的脚本: {producer}; 严禁手写 JSON 或删除文件绕过")
    return problems


def main(argv: list[str] | None = None) -> int:
    """CLI: 确认门1 的 class 字段 str_replace 是唯一获准的脚本外编辑——改完立即
    `sign --confirm-gate1-edit --files clauses.json` 重登(三条件缺一即拒, 见模块
    docstring sign 收紧条); 首次登记没有 CLI 通道, 只能由管线脚本写盘自动完成。
    `verify` 供编排自检。退出码: 0=通过/已登记, 1=校验发现问题/洗白拒绝/用法错误。"""
    parser = argparse.ArgumentParser(
        prog="state_guard.py",
        description="权威状态防篡改签名工具(.meta.json): sign=确认门1 class 回写后重登签名(唯一获准通道), verify=读盘前自检(无 LLM)",
        epilog="示例: python state_guard.py sign --state-dir state --files clauses.json --confirm-gate1-edit | python state_guard.py verify --state-dir state",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_sign = sub.add_parser("sign", help="重登签名(仅限确认门1 class 回写: --files clauses.json + --confirm-gate1-edit; 通用重签已关闭, 首登记走管线脚本自动签名)")
    p_sign.add_argument("--state-dir", required=True, help="状态目录")
    p_sign.add_argument("--files", nargs="+", required=True, help="重登签名的文件名(仅接受 clauses.json)")
    p_sign.add_argument(
        "--confirm-gate1-edit",
        action="store_true",
        help="显式声明本次重签对象是确认门1 有意编辑(必带旗标; 且要求既有签名+内容有变+文件含 class 字段, 防脚本外手写后借 sign 通道洗白)",
    )
    p_verify = sub.add_parser("verify", help="校验已登记签名(管线脚本装载前自动做, 此处供编排显式自检)")
    p_verify.add_argument("--state-dir", required=True, help="状态目录")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if not exc.code:
            return 0
        print(f"[state_guard] 错误: 命令行参数用法错误(argparse 退出码 {exc.code}; 用 --help 查看用法)", file=sys.stderr)
        return 1

    if args.command == "sign":
        # sign 收紧(v3, bug-2189 回放: heredoc 伪造 sections.json 后借"首签无摩擦"
        # 洗白)。三条件全过才放行, 任一不满足按洗白拒绝并记 resign_log 审计:
        # (a) --confirm-gate1-edit 必带, 且 --files 仅 clauses.json;
        # (b) 该文件已有登记签名且内容确有变更(确属门1 class 回写场景);
        # (c) 文件含 class 字段。从未登记过的文件即使带旗标也拒绝——合法首登记
        # 唯一路径=管线脚本写盘时的 sign_state_files 自动签名。
        registered = _load_meta(args.state_dir).get("signatures")
        registered = registered if isinstance(registered, dict) else {}

        def _reject(reason: str, audit: dict) -> int:
            entry = {"rejected": True, **audit}
            if not (entry.get("reason")):
                entry["reason"] = reason
            _audit_resign(args.state_dir, entry)
            print(f"[state_guard] 错误: {reason}", file=sys.stderr)
            return 1

        if not args.confirm_gate1_edit:
            _reject(
                "缺少 --confirm-gate1-edit, 通用重签通道已关闭; 合法路径=重跑产生该文件的管线脚本(写盘自动登记); 确属确认门1 class 字段编辑必须显式带旗标",
                {"files": sorted(args.files)},
            )
            return 1
        if sorted(args.files) != ["clauses.json"]:
            _reject(
                f"--files 仅允许 clauses.json(收到: {sorted(args.files)}); 确认门1 class 回写只发生在 clauses.json",
                {"files": sorted(args.files)},
            )
            return 1
        name = args.files[0]
        path = Path(args.state_dir) / name
        if not path.is_file():
            print(f"[state_guard] 错误: {name} 不存在于 {args.state_dir}(只重登已存在文件)", file=sys.stderr)
            return 1
        current = _sha256_file(path)
        previous = registered.get(name)
        if previous is None:
            _reject(
                f"{name} 从未登记签名, 拒绝首签洗白; 合法首登记=重跑产生该文件的管线脚本(写盘自动签名)",
                {"file": name, "new_sha": current},
            )
            return 1
        if previous == current:
            _reject(
                f"{name} 内容与既有签名一致, 无变更无需重签(重签只服务确认门1 class 回写)",
                {"file": name, "prev_sha": previous, "new_sha": current},
            )
            return 1
        if not _contains_class_key(path):
            _reject(
                f"{name} 不含 class 字段, 不符合确认门1 class 回写场景, 拒绝重签; 合法路径=重跑产生该文件的管线脚本",
                {"file": name, "prev_sha": previous, "new_sha": current},
            )
            return 1
        sign_state_files(args.state_dir, [name])
        _audit_resign(args.state_dir, {"file": name, "prev_sha": previous, "new_sha": current})
        print(f"[state_guard] 已重登签名(变更型, 已记审计 resign_log): {name}(声明=确认门1 有意编辑)")
        return 0
    problems = verify_state_files(args.state_dir)
    if problems:
        print("[state_guard] 校验失败:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 1
    print("[state_guard] 校验通过(无签名可校验或全部匹配)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
