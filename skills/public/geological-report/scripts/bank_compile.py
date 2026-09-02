#!/usr/bin/env python3
"""bank_compile.py — 样例库 → 技能衍生物的确定性编译器（geo-sample-bank 核心）。

EAI-CUSTOM (geo-sample-bank Phase 2 T5)：维护者离线动作脚本，把模块后端（geo_samples）
备好的脱敏报告语料编译进技能 references/ 的四处衍生物：
  1. 切片库   <refs>/samples_bank/<stage>/slices/ch<N>/<rid>__<N>.md（带溯源标记行）
  2. SL3 指纹池 <refs>/samples/<stage>/ch<N>__<rid>.md（裸切片文本，落同层即自动扩容
     consistency.check_sl3 的非递归 glob 指纹池；绝不放整本 source.md）
  3. bank_index <refs>/samples_bank/bank_index.json（stage → chN → 节条目索引）
  4. per 矿种深度基线 <refs>/depth_targets/<stage>/<mineral>.json——按 (stage, mineral)
     分组，组内切片临时命名为 chN_<rid>.md 后子进程调 sibling calibrate.py 聚中位数，
     成功后读回加 absolute_floor 落盘；某组 rc!=0 仅跳过该组并 stderr 警告。

约束与语义：
  - 纯 stdlib + 子进程调 sibling calibrate.py；无网络；不 import build_output/ingest/consistency。
  - 维护者动作：输入缺失/全部报告零切片 → 立即失败（绝不产空 bank_index）。
  - 退出码：0 = 至少一片并完成编译；1 = 输入缺失/manifest 非法/全部报告零切片。
  - 幂等：全部产物 sort_keys + newline="\\n" 确定性写——同输入必同字节。
  - 切片规则 SEC_RE = ^#{2,4}\\s+\\d+(?:\\.\\d+)*\\s（MULTILINE）：子节归父片
    （### 2.1 属 ## 2 片），节号首段为片号；片起点=标题行 start，终点=下一不同片
    标题的 start 或文末，标题行本身保留在片内。

用法（模块后端 T7 调用）：
    python -X utf8 bank_compile.py --workdir <语料目录> --references <技能 references 目录>
    # workdir 下：<report_id>/source.md（脱敏全文）+ manifest.json：
    #   [{"report_id","stage","mineral","file_name"}]（stage/mineral 为 slug，模块侧直读可信）
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
CALIBRATE = SCRIPTS_DIR / "calibrate.py"
ABSOLUTE_FLOOR = 0.4  # 深度门硬下限，标定成功后统一补进基线 doc

# 节号标题：##/###/#### + 空白 + 数字节号 + 空白（MULTILINE 逐行锚定行首）
SEC_RE = re.compile(r"^(#{2,4})\s+(\d+(?:\.\d+)*)\s", re.MULTILINE)


def _json_write(path: Path, doc) -> None:
    """确定性 JSON 落盘：sort_keys + 末尾换行 + 强制 \\n（Windows 字节级幂等）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _heading_title(line: str) -> str:
    """从标题行剥掉井号前缀与节号，余下文本即节标题（如 `## 2 地质特征` → `地质特征`）。"""
    no_hash = re.sub(r"^#{1,6}\s+", "", line)
    return re.sub(r"^\d+(?:\.\d+)*\s+", "", no_hash).strip()


def slice_report(text: str) -> list[dict]:
    """把报告全文切成片：连续同片号的节归并进同一片（子节归父片）。

    返回按文档顺序的 [{chapter, seg, secs}]；chapter=节号首段，seg=裸切片文本
    （起点=片首标题行 start，终点=下一不同片标题 start 或文末），secs=片内节条目
    [{sec, title}]（sec 为完整节号，如 2.1）。无节号标题 → 返回 []。
    """
    matches = list(SEC_RE.finditer(text))
    if not matches:
        return []
    slices: list[dict] = []
    cur: dict | None = None
    for m in matches:
        sec = m.group(2)
        chapter = sec.split(".")[0]
        if cur is None or cur["chapter"] != chapter:
            if cur is not None:
                slices.append(cur)
            cur = {"chapter": chapter, "start": m.start(), "secs": []}
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        line = text[m.start() : line_end].rstrip("\r")
        cur["secs"].append({"sec": sec, "title": _heading_title(line)})
    if cur is not None:
        slices.append(cur)
    # 片终点 = 下一片起点 / 文末（末片）
    for i, s in enumerate(slices):
        end = slices[i + 1]["start"] if i + 1 < len(slices) else len(text)
        s["seg"] = text[s["start"] : end]
        del s["start"]
    return slices


def _run_calibrate(python: str, samples_dir: Path, output: Path) -> tuple[int, str]:
    """子进程调 sibling calibrate.py（脚本目录自动进 sys.path[0]，cwd 无关）。"""
    proc = subprocess.run(
        [python, "-X", "utf8", str(CALIBRATE), "--samples-dir", str(samples_dir), "--output", str(output)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stderr or "").strip()


def main_with_args(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="样例库 → 技能衍生物（slices/SL3 指纹/bank_index/per 矿种基线）确定性编译")
    ap.add_argument("--workdir", required=True, help="语料目录：<report_id>/source.md + manifest.json")
    ap.add_argument("--references", required=True, help="技能 references 目录")
    ap.add_argument("--python", default=sys.executable, help="调 calibrate.py 用的解释器（默认当前解释器）")
    args = ap.parse_args(argv)

    workdir, refs = Path(args.workdir), Path(args.references)
    manifest_path = workdir / "manifest.json"
    if not manifest_path.is_file():
        print(f"[bank_compile] manifest 缺失：{manifest_path}", file=sys.stderr)
        return 1
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[bank_compile] manifest 不可读/非法 JSON：{exc}", file=sys.stderr)
        return 1
    if not isinstance(entries, list):
        print("[bank_compile] manifest 必须是对象数组", file=sys.stderr)
        return 1

    # 按 report_id 去重（首次出现胜出）——manifest 重复行不产生重复切片/索引条目
    seen: set[str] = set()
    reports = []
    for e in entries:
        rid = e.get("report_id") if isinstance(e, dict) else None
        if not rid or rid in seen:
            continue
        seen.add(rid)
        reports.append(e)

    index: dict = {}  # stage -> chN -> [节条目]
    groups: dict[tuple[str, str], list] = {}  # (stage, mineral) -> [(chapter, rid, seg)]
    total_slices = 0

    for e in reports:
        rid = e["report_id"]
        stage, mineral = e.get("stage") or "", e.get("mineral") or ""
        src = workdir / rid / "source.md"
        if not stage or not mineral or not src.is_file():
            print(f"[bank_compile] {rid} 缺 stage/mineral 或 source.md 不存在——跳过", file=sys.stderr)
            continue
        slices = slice_report(src.read_text(encoding="utf-8"))
        if not slices:
            print(f"[bank_compile] {rid} 零切片（source.md 无节号标题）——跳过", file=sys.stderr)
            continue
        for s in slices:
            chapter, seg, secs = s["chapter"], s["seg"], s["secs"]
            total_slices += 1
            # 1) 切片库：带溯源标记行
            bank_dir = refs / "samples_bank" / stage / "slices" / f"ch{chapter}"
            bank_dir.mkdir(parents=True, exist_ok=True)
            marker = f"【矿种】{mineral}｜【阶段】{stage}｜【report_id】{rid}｜【节号】{chapter}\n\n"
            (bank_dir / f"{rid}__{chapter}.md").write_text(marker + seg, encoding="utf-8", newline="\n")
            # 2) SL3 指纹池：裸切片文本（同层自动扩容 check_sl3 非递归 glob）
            sl3_dir = refs / "samples" / stage
            sl3_dir.mkdir(parents=True, exist_ok=True)
            (sl3_dir / f"ch{chapter}__{rid}.md").write_text(seg, encoding="utf-8", newline="\n")
            # 3) 索引条目 + 4) 标定分组
            ch_key = f"ch{chapter}"
            for item in secs:
                index.setdefault(stage, {}).setdefault(ch_key, []).append(
                    {
                        "report_id": rid,
                        "mineral": mineral,
                        "sec": item["sec"],
                        "title": item["title"],
                        "file": f"samples_bank/{stage}/slices/{ch_key}/{rid}__{chapter}.md",
                    }
                )
            groups.setdefault((stage, mineral), []).append((chapter, rid, seg))

    if total_slices == 0:
        print("[bank_compile] 全部报告零切片（无节号标题）——拒绝生成空 bank_index", file=sys.stderr)
        return 1

    _json_write(refs / "samples_bank" / "bank_index.json", index)
    print(f"BANK_COMPILED: {len(reports)} report(s), {total_slices} slice(s), {len(groups)} group(s)")

    # 4) per (stage, mineral) 标定：组内切片临时命名 chN_<rid>.md（满足 calibrate FNAME_RE
    #    ^ch(\d+)，同章多份自动聚 median——正是 per 矿种标定语义）；rc!=0 仅跳过该组。
    for (stage, mineral), items in sorted(groups.items()):
        with tempfile.TemporaryDirectory(prefix="bank_cal_") as td:
            tdir = Path(td)
            for chapter, rid, seg in items:
                (tdir / f"ch{chapter}_{rid}.md").write_text(seg, encoding="utf-8", newline="\n")
            out = refs / "depth_targets" / stage / f"{mineral}.json"
            out.parent.mkdir(parents=True, exist_ok=True)  # calibrate 不建父目录，须先备好
            rc, err = _run_calibrate(args.python, tdir, out)
            if rc != 0:
                print(f"[bank_compile] 标定失败 {stage}/{mineral}（rc={rc}），该组跳过：{err}", file=sys.stderr)
                continue
            doc = json.loads(out.read_text(encoding="utf-8"))
            doc["absolute_floor"] = ABSOLUTE_FLOOR
            _json_write(out, doc)
            print(f"  CALIBRATED {stage}/{mineral}: {len(doc.get('per_chapter', {}))} chapters -> {out}")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
