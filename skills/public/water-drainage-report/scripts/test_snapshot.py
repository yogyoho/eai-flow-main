#!/usr/bin/env python3
"""snapshot.py 自检（反馈7 v1→v2→v3 自增不变量）。

stdlib only，无 pytest 依赖 —— 直接 `python test_snapshot.py` 运行。
忠实复现 agent 用法：以子进程调 snapshot.py save 两次，断言 version 自增、
created_at 保留、changelog 追加、last_task 更新、show 锚点、无快照降级。

这是反馈7 的回归防线：bug-1171 的根因是 agent 从不写 project_snapshot.json，
修复后首轮写出 v1；本测试锁死"写出后再 save 必须自增到 v2/v3 且不丢 created_at"
—— 即多轮承接所依赖的不变量。
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
SP = HERE / "snapshot.py"


def _save(out, task, diff=None):
    params = out.parent / "params.json"
    if not params.exists():
        params.write_text('{"Q": 20000}', encoding="utf-8")
    cmd = [
        sys.executable,
        str(SP),
        "save",
        "--task",
        task,
        "--params",
        str(params),
        "--report",
        str(out.parent / "r.md"),
        "--standards",
        '["GB/T 50050-2017"]',
        "--output",
        str(out),
    ]
    if diff:
        cmd += ["--diff", diff]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, f"save 失败: {r.stderr}"
    return r.stdout


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = d / "project_snapshot.json"

        # 1. 首次（全新，version 0→1）
        _save(out, "首次生成 Q=20000")
        s1 = json.loads(out.read_text(encoding="utf-8"))
        assert s1["version"] == 1, s1["version"]
        assert len(s1["changelog"]) == 1
        created = s1["created_at"]

        # 2. 改参（v1→v2）—— 多轮承接铁律所依赖的自增
        stdout2 = _save(out, "改参 20000->25000", diff='{"Q":{"old":20000,"new":25000}}')
        assert "SNAPSHOT_READY: version=2" in stdout2, stdout2
        s2 = json.loads(out.read_text(encoding="utf-8"))
        assert s2["version"] == 2, s2["version"]
        assert s2["created_at"] == created, "created_at 必须保留（防漂移基准）"
        assert len(s2["changelog"]) == 2
        assert s2["last_task"] == "改参 20000->25000"
        assert s2["changelog"][-1]["value_diffs"] == {"Q": {"old": 20000, "new": 25000}}

        # 3. 再改参（v2→v3，created_at 仍保留）
        _save(out, "改参 25000->30000", diff='{"Q":{"old":25000,"new":30000}}')
        s3 = json.loads(out.read_text(encoding="utf-8"))
        assert s3["version"] == 3, s3["version"]
        assert s3["created_at"] == created, "created_at 跨两次仍须保留"
        assert len(s3["changelog"]) == 3

        # 4. show 子命令读锚点（agent 步骤0 用的就是这个）
        show = subprocess.run(
            [sys.executable, str(SP), "show", "--input", str(out)],
            capture_output=True,
            text=True,
        )
        assert "SNAPSHOT_LAST_TASK: 改参 25000->30000" in show.stdout, show.stdout

        # 5. 无快照 → SNAPSHOT_NONE（步骤0 降级全新运行）
        none = subprocess.run(
            [sys.executable, str(SP), "show", "--input", str(d / "nope.json")],
            capture_output=True,
            text=True,
        )
        assert "SNAPSHOT_NONE" in none.stdout, none.stdout

        # 6. R11 守卫（b2117e88 实测穿透）：手写整份报告（0 details+0 占位符+0 签名）必须被打回。
        #    现有 _save 的 --report r.md 从不落盘 → 门禁整段被 if rp.exists() 跳过——本节补真文件用例。
        def _run_save():
            return subprocess.run(
                [sys.executable, str(SP), "save", "--task", "R11 守卫回归", "--params", str(out.parent / "params.json"), "--report", str(out.parent / "r.md"), "--output", str(out)],
                capture_output=True,
                text=True,
            )

        rmd = out.parent / "r.md"
        # 6a. 全手写（无签名）→ R11 打回
        rmd.write_text("# 计算书\n\n#### 6.1.1 蒸发水量\n\nQe = 18000 * 0.001461 * 8 = 210.38 m3/h（手写）\n", encoding="utf-8")
        r = _run_save()
        assert r.returncode == 1, f"手写报告必须被 R11 打回: rc={r.returncode}"
        assert "R11" in r.stdout and "无脚本注入签名" in r.stdout, r.stdout
        # 6b. per-formula 占位符未 inject → R11 打回
        rmd.write_text("# 计算书\n\n#### 6.1.1 蒸发水量\n\n<!-- CALC:Qe -->\n", encoding="utf-8")
        r = _run_save()
        assert r.returncode == 1 and "R11" in r.stdout and "未注入占位符" in r.stdout, r.stdout
        # 6c. 合法注入产物（签名 count=1 + 恰好 1 个 details）→ 放行且 version 自增
        rmd.write_text(
            "# 计算书\n\n#### 6.1.1 蒸发水量\n\n<details><summary>计算过程</summary>\n$$Qe=210.38$$\n</details>\n\n<!-- CALC_BLOCKS_INJECTED:v2 count=1 -->\n",
            encoding="utf-8",
        )
        r = _run_save()
        assert r.returncode == 0, f"合法注入产物必须放行: {r.stdout}"
        assert "SNAPSHOT_READY" in r.stdout, r.stdout
        rmd.unlink()

    print("PASS: snapshot.py v1→v2→v3 自增 / created_at 保留 / changelog 追加 / show 锚点 / SNAPSHOT_NONE / R11 手写报告打回")
    return 0


if __name__ == "__main__":
    sys.exit(main())
