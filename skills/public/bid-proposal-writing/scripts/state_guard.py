"""权威状态防篡改签名(.meta.json)——共享守卫模块(纯 stdlib, 无 LLM)。

回放实证(2026-08-18 内蒙古财经大学线程 bfa917ce): agent 用 write_file 直写
state/*.json 或 rm -rf 后, 下游脚本只报"结构异常/缺键"等远处症状, agent 靠试错
绕行烧掉整轮上下文(单 run 91 次 LLM 调用)。本模块把状态污染变成一声带恢复指令
的硬错误(退出码 1), 恢复指令指向"重跑脚本", 不给手写/删除留口子。

契约:
- 登记(sign_state_files): 写盘方在原子写出权威状态文件后, 对 <state_dir>/.meta.json
  登记这些文件名的 sha256。既有登记合并保留(ingest 登 sections, extract merge 登
  三状态文件, merge_addenda/score_simulate 重写 clauses 后重登)。
- 校验(verify_state_files): 读盘方在装载前对 <state_dir> 已登记的每个文件复核
  sha256; 文件缺失/内容不符 → 返回问题清单(非空即硬错误, 编排方打印后退出码 1)。
  另拦注入(F4, 回放实证 2026-08-16 江西师大线程 1a1b72bf): 权威四件套在盘但未登记
  也算问题——agent 脚本外手写全新 state/clauses.json 可绕过"只复核已登记名"的旧逻辑,
  被下游 build_output 当真数据装载。
- 兼容: .meta.json 不存在 = 无签名可校验(既有工作区/测试 fixture 直造 sections.json),
  返回空清单放行——守卫只收紧"脚本已登记过"的工作区, 不改变零签名场景行为。
- 幂等: meta 不含时间戳、键序排序落盘, 同内容重签字节级不变(重复合并测试依赖)。

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
RECOVERY_HINT = "恢复方法: 重跑产生该文件的脚本重建(ingest.py/extract.py merge; 未变输入按内容指纹保号, 已提取候选不失效); 严禁手写 JSON 或删除文件绕过"
# 权威五件套: 管线脚本落盘并签名、下游装载的唯一状态文件集合。
# entities_whitelist.json(agent 按设计手写, 永不签名)与 snapshot.json(非装载路径)不在其列。
AUTHORITATIVE_FILES = ("sections.json", "clauses.json", "structure.json", "rubric.json", "responses.json")


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


def sign_state_files(state_dir: str | Path, names: list[str]) -> None:
    """写盘方登记权威状态文件签名(合并既有登记, 原子落盘, 字节级幂等)。"""
    meta = _load_meta(state_dir)
    signatures = meta.get("signatures")
    signatures = dict(signatures) if isinstance(signatures, dict) else {}
    for name in names:
        signatures[name] = _sha256_file(Path(state_dir) / name)
    meta["signatures"] = signatures
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


def verify_state_files(state_dir: str | Path) -> list[str]:
    """读盘前校验已登记签名; 返回问题清单(空=通过或无签名可校验)。"""
    signatures = _load_meta(state_dir).get("signatures")
    if not isinstance(signatures, dict) or not signatures:
        return []
    problems: list[str] = []
    for name in sorted(signatures):
        path = Path(state_dir) / name
        if not path.is_file():
            problems.append(f"state/{name} 已登记签名但文件不存在(疑似被 rm 删除); {RECOVERY_HINT}")
        elif _sha256_file(path) != signatures[name]:
            problems.append(f"state/{name} 内容与脚本落盘签名不符(疑似 write_file 直写/手工编辑); {RECOVERY_HINT}")
    for name in AUTHORITATIVE_FILES:
        if name not in signatures and (Path(state_dir) / name).is_file():
            problems.append(f"state/{name} 在盘但未登记签名(疑似脚本外直写/手写注入); {RECOVERY_HINT}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """CLI: 确认门1 的 class 字段 str_replace 是唯一获准的脚本外编辑——改完立即
    `sign` 重登, 显式声明"我有意编辑了该文件"(守卫防的是幻觉直写/误删, 不是审计
    用户本人); `verify` 供编排自检。退出码: 0=通过/已登记, 1=校验发现问题或用法错误。"""
    parser = argparse.ArgumentParser(
        prog="state_guard.py",
        description="权威状态防篡改签名工具(.meta.json): sign=确认门1 class 编辑后重登签名, verify=读盘前自检(无 LLM)",
        epilog="示例: python state_guard.py sign --state-dir state --files clauses.json | python state_guard.py verify --state-dir state",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_sign = sub.add_parser("sign", help="有意编辑(仅限确认门1 class 字段 str_replace)后重登签名")
    p_sign.add_argument("--state-dir", required=True, help="状态目录")
    p_sign.add_argument("--files", nargs="+", required=True, help="重登签名的文件名(如 clauses.json)")
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
        for name in args.files:
            if not (Path(args.state_dir) / name).is_file():
                print(f"[state_guard] 错误: {name} 不存在于 {args.state_dir}(只重登已存在文件)", file=sys.stderr)
                return 1
        sign_state_files(args.state_dir, list(args.files))
        print(f"[state_guard] 已重登签名: {sorted(args.files)}(声明=确认门1 有意编辑)")
        return 0
    problems = verify_state_files(args.state_dir)
    if problems:
        print("[state_guard] 校验失败:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 1
    print("[state_guard] 校验通过(无签名可校验或全部匹配)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
