---
name: ops-diagnosis
description: 当用户要求"分析/诊断某个线程(或 run/会话/技能执行)的情况"、"查一下刚才那次任务为什么失败/烧了这么多 token"、"回放分析 agent 执行"、"检查技能是否违反契约"时使用此技能。基于 run_events 持久化事件流做定量统计 + 契约对照,产出带事件证据 ID 的分级诊断报告(P0/P1/P2 + 根因 + 建议)。
---

# Ops 诊断技能(ops-diagnosis)

## 概述

把"回放分析一次 agent 执行"变成标准流水线：**MCP 取数 → 脚本统计 → LLM 判断 → 证据化报告**。

分工铁律（与 bid-proposal-writing 同哲学）：

- **脚本 = 确定性统计**（计数/聚类/折叠，不判断）；
- **LLM = 对照契约的判断**（违规/根因/分级，不手算数字）；
- **报告里的每个数字必须来自脚本产物，每个问题必须带事件证据 (run8, seq)**。

## 第 0 步：数据存在性检查（必做，失败即如实报告）

先调 `ops_list_thread_runs(thread_id)`：

- 返回空 → 如实回答"无事件数据（run_events.backend 曾为 memory、事件已清理或线程不存在）"，**不要编造分析**，到此为止。
- 有 runs 但某 run 的 event_count=0 → 该 run 事件未持久化（发生在持久化开启前），只做 runs 元数据层面的分析并注明。

## 第 1 步：取数落盘

```
workspace/opsdiag/runs.json              ← ops_list_thread_runs 完整响应
workspace/opsdiag/events/<run8>.jsonl    ← 每个 run 调一次 ops_get_run_events(thread_id, run_id, limit=1000)
```

- **落盘铁律：MCP 工具返回的 JSON 必须原样整体写入文件（一次 write_file 粘贴全文），严禁手工转写/截取重排**——转写引入的 JSON 语法错误会让脚本直接失败。
- 大 run（event_count>800）分批拉（可加 text_match/event_type 过滤），先拉全量做序列，失败检索可后续用 `text_match="Traceback"` 等补拉。
- 用户只给线程 ID 时全部 run 都拉；用户点名某 run 只拉该 run。

## 第 2 步：脚本 crunch（产物是唯一事实源）

```
python /mnt/skills/public/ops-diagnosis/scripts/summarize_runs.py   --runs /mnt/user-data/workspace/opsdiag/runs.json --events-dir /mnt/user-data/workspace/opsdiag/events
python /mnt/skills/public/ops-diagnosis/scripts/extract_failures.py --events-dir /mnt/user-data/workspace/opsdiag/events
python /mnt/skills/public/ops-diagnosis/scripts/extract_sequences.py --events-dir /mnt/user-data/workspace/opsdiag/events
```

三个脚本输出 JSON（stdout）：per-run 指标 / 失败签名聚类 / 工具序列折叠。**报告数字只准引用这些产物。**

## 第 3 步：契约对照（LLM 判断部分）

若诊断对象是某个技能的执行：先 `read_file /mnt/skills/public/<skill>/SKILL.md`，重点核对清单（常见违规模式，逐项过）：

1. **脚本幻觉**：调用了目标技能 SKILL.md 里不存在的脚本/参数（序列里反复 `can't open file` + 签名聚类交叉验证）；
2. **cwd 混淆**：相对路径失败后仍不改绝对路径（`no such file`/`unsafe absolute path` 聚类 + 序列里是否出现纠正动作）；
3. **状态文件铁律**：write_file/str_replace 是否碰了只归脚本管的权威态文件（对照 SKILL.md 的状态防改条款）；
4. **present_files 路径**：是否只呈现 /mnt/user-data/outputs 下的文件；
5. **rc 语义**：Exit Code 3 等技能自定义返回码是否被误判为失败（对照 SKILL.md，签名清单已排除常见误报）；
6. **失败熔断条款**：技能若有"连续 N 次失败即停"条款，序列里是否有超限重试（折叠行的 x 值直接是证据）。

## 第 4 步：报告（固定骨架，保证历次可比）

写到 `/mnt/user-data/outputs/诊断报告-<thread8>-<yyyymmdd>.md` 后 present_files，并在线上给摘要：

```
# 线程 <thread8> 执行诊断
## 1. 概览        ← summarize_runs totals：runs/errors/tokens/llm_calls/工具调用/失败总数
## 2. 逐 run 时间线 ← 每 run 一行：状态/终因/耗时/失败密度；异常 run 加一句定性
## 3. 失败聚类 top-N ← extract_failures：签名 × 次数 × 分布 run × 首末证据 (run8,seq)
## 4. 契约违规清单  ← 第 3 步逐项结论：违反条目原文 + 事件证据 (run8,seq)
## 5. 分级问题     ← P0(烧钱/废标级)/P1(效率/契约)/P2(观感)，每条带证据
## 6. 根因        ← 最深的一层（如：模型把 check.py 记进上下文但从未核对速查表）
## 7. 建议        ← 可执行项（改 SKILL.md 条款/改脚本/改配置），对应到 P 编号
## 附: 方法与盲区  ← 截断保头部→失败数是下界；Exit Code 1/2 不计 等声明
```

## 边界

- **只读诊断**：本技能不修改任何线程/事件/技能文件；唯一写盘是 workspace/opsdiag/ 与 outputs/ 报告。
- 无 MCP 工具（ops_list_thread_runs/ops_get_run_events）可用时如实说明并停。
- 诊断"当前正在进行的线程"也允许（自诊断），事件是追加型的。
