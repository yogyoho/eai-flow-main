# 失败签名清单（单一参考源）

> 维护约定：本文件是"什么算工具失败"的**单一参考清单**。三处消费方以此为准同步：
> ① `scripts/_common.py::FAILURE_PATTERNS`（本技能的 crunch 脚本）；
> ② FailureStreakMiddleware 的 `failure_patterns` 默认集（`backend/.../failure_streak_config.py`，设计稿见 docs/superpowers/specs/2026-08-18-failure-streak-middleware-design.md）；
> ③ 人工回放分析。改这里必须同时改 ①②。

## 计为失败的签名（regex，忽略大小写由消费方决定）

| 签名 | 模式 | 覆盖的实测病灶 |
|---|---|---|
| python traceback | `Traceback \(most recent call last\)` | python 脚本裸崩 |
| can't open file | `can't open file` | 反复调用不存在的幻觉脚本（check.py / build_output.py 连撞 15+ 次的根因形态） |
| no such file or directory | `No such file or directory` | FileNotFoundError（含 cwd 混淆） |
| argparse misuse | `error: (unrecognized arguments\|invalid choice\|the following arguments are required)` | 参数试错循环 |
| unsafe absolute path | `Error: Unsafe absolute paths` | 沙箱路径守卫拒绝（cwd 混淆的另一形态） |
| file not found (read_file) | `Error: File not found` | read_file 失败兜底 |
| present_files path violation | `Error: Only files in /mnt/user-data/outputs can be presented` | 产物路径违例 |
| tool status=error | ToolMessage `status="error"` | 工具层异常（ToolErrorHandlingMiddleware 转写） |
| run.error | event_type == `run.error` | run 级异常 |

## 明确不计为失败（防误报，与 P0/P1 判定同样重要）

| 形态 | 原因 |
|---|---|
| 裸 `Exit Code: 1` / `Exit Code: 2` | grep 无匹配、探测性 `ls xxx 2>/dev/null` 是正常工作流信息 |
| `Exit Code: 3` | bid-proposal-writing 契约：rc=3 = "完成但有异常"（ingest.py 写出 sections.json 后返回 3），**成功语义** |
| `appears to be a binary file` | 提示性文本，非错误 |

## 已知盲区

- 截断丢尾：run_events 的 trace 截断保**头部**（`max_trace_content`），超长 bash 输出的**尾部** Traceback/Exit Code 行可能丢失 → 失败数是**下界**。报告里要注明。
- 只带 `Exit Code: 1` 无特征文本的失败不计 → 同样是下界。宁可漏报不误报（误熔断/误报 P0 的代价更高）。
