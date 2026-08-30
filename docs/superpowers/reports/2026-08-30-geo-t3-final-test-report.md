# 地质勘查报告技能重构 — 页面验证性测试最终报告（T3）

> 2026-08-30 · Thread `12703344-f5ed-40c9-9197-25b91275efb7`（干净线程）· run 71c86a1d → ef795447（共 14 run）
> 测试通道：API 直连 `http://127.0.0.1:2026`（`POST /api/runs/stream` + `on_disconnect: "continue"`），测试者以用户身份逐轮应答 lead agent。
> 前序：T1/T2（thread fa2cf7a5）6 findings → 决策包 `2026-08-29-geo-page-test-findings-fix-design.md`（含 2026-08-30 增补 F7-F9）。

## 一、结论

**全流程跑通**：ingest → 门1（gate1）→ formula freeze → wave1（7 章并行 task() 子代理）→ key_points 生成+用户确认 → wave2 → ch10 结论 → build_output 组装 → consistency → snapshot → 交付（497.9KB Markdown，v6 snapshot）。最终交付态经逐项质检：现代编码（122b/122c）清零、未渲染 SLOT/TABLE 占位符清零、HTML 注释清零、无据字段 422 处 `[待确认]`（D2 诚实部分交付达成）。

**D1 成功标准达成**：可靠跑通 ✓；少量问询 ✓（问询集中在 key_points 确认、type_verdicts 数据缺失、门2 异常呈现，均为设计内问询点）；死循环 0、熔断 0、绕门 0（lead 一次手改 formula_state 被协议问询纠正，未绕门）。

**一致性校验终态**：PASS=17 / WARN=21 / FAIL=2（ch6 小节号非递增、84 处 SL2 不可溯源数值——均为数据层已知问题）/ MANUAL=2（standards_index 未加载需人工核实规范引用）。

## 二、机制验证矩阵

| 重构机制（Task） | 验证结果 | 备注 |
|---|---|---|
| progress.py 状态机（T1） | ✓ 工作 | lead 多次忘 mark 需点名（⑯ 账本滞后，自愈型）；纠正后纪律改善 → 修法归 F4（SKILL.md 把 mark 定为门后强制步骤） |
| build_output --chapter 单章门（T2） | ✓ 工作 | 门拦 TOC 结构/eff 深度/SLOT 溯源有效；缺口：未知 TABLE 族静默过门（⑰/bug-3012）+ FORM 族不查（㉘/bug-3027）→ F7 已入决策包 |
| --allow-partial 分级交付（T3-Task3） | ✓ 工作 | 缺数槽位全走 `[待确认]`，无编造兜底；422 处待确认项如实呈现 |
| chapter_craft.md + 派发协议（T4） | ✓ 工作 | wave1 7 章并行 task() 派发正常（D3 方案A）；灰区：lead 门失败后自行 rm 重写草稿（②）、一次手写章节（bug-3013）、scratch 副本残留（㉓） |
| config.yaml 提额（T5） | ✓ 工作 | recursion_limit 400 后 GraphRecursionError 未复发；子代理 max_turns=150 预算耗尽仍发生一次（㉓） |
| formula_state 唯一写者红线 | ✓ 有效 | lead 一次手补 type_verdicts/workload（㉕）→ 协议问询→诚实披露→选项A回退+公式化判据指示；红线机制（问询后可纠正）本身工作 |
| data/ 唯一写者 = ingest.py | ✓ 有效 | 手写绕过（①）、scratch 落 data/（⑥）均由测试者点名纠正；根治归 F1+F6 |
| 数字不过 LLM（SLOT 注入） | ✓ 有效 | 最终报告未渲染 SLOT=0；但正文 FORM 占位符残留证明「契约取值指示」需第四轮门拦截（F7） |
| 历史分类禁现代化改写（CC2） | ✓ 有效 | key_points 纠正 + ch8 修复后，正文以「引述历史储量分类 B/C/D 编码」合规呈现 |
| 规范编号只从 standards_index 枚举 | ⚠ 部分 | standards_index 未加载（MANUAL=2 项留人工核实）；正文 FORM:standards_index 残留 4 处（本轮已指令清理） |
| snapshot save/verify | ✓ 工作 | v6 snapshot 39 文件哈希留痕 |
| consistency 校验 | ✓ 工作 | FAIL/WARN/MANUAL 分级如实暴露数据层问题 |

## 三、T3 新增 findings（㉑-㉚）

| # | finding | 定案/去向 |
|---|---|---|
| ㉑ | gateway 楔死系列 | bug-3019→3021 已修（0cd18c108）；「外部打断者」定案 = SSE 抓取窗口 `--max-time` 断开触发 on_disconnect=cancel 杀 run → 测试通道根治（`on_disconnect: "continue"`，run 6→14 全程稳定）；产品侧含义：**前端用户关页/断网也会杀长任务 run** → 第四轮候选修复 |
| ㉒ | formula_runner 历史分类 B/C 误校验 | bug-3022（aggregates 汇总行 grade_class=B/C 被按品位枚举误报+行跳过）；干净线程复现 → P1 修补候选（按 category+历史分类放行） |
| ㉓ | 子代理 max_turns=150 预算耗尽 + scratch 副本残留 state/chapters/ | 预算提额候选；scratch 清理由 lead 执行（点名后） |
| ㉔ | lead 半句终报（截断） | 观察项，未复现第二次 |
| ㉕ | lead 手改 formula_state（唯一写者红线违反） | 协议问询→诚实披露→回退；机制有效，SKILL.md 应把「披露义务」写死 → 归 F4 文档修订 |
| ㉖ | ch10 先于 key_points 确认生成（协议顺序违反） | lead 自行纠正重来；F4 门2 confirm 前置可根治 |
| ㉗ | key_points 纠正不传导到已 VERIFIED 章节（ch8 空值+现代编码残留） | 实战发生 → 定向修复轮闭环（run 13 全部验证通过）；支撑 F4 门2「确认后扫描受影响已验收章」设计 |
| ㉘ | build 门漏 FORM 族占位符残留（27 处入正文） | bug-3027 → **F7**（P1，门验一行扩展） |
| ㉙ | `[[待确认]]` 双括号写法 4 处 | **F8**（P2，门/consistency 归一化） |
| ㉚ | `on_disconnect=continue` 下 runs.status 标签失真（`interrupted` 但 step 推进中） | **F9**（P2 观测性；监控真相源 = checkpoints step，非 runs.status） |

T1/T2 findings ①-⑳ 见决策包主文（F1-F6 已含修复设计）；本表 ㉑-㉚ 并入同一决策包（F7-F9 增补节）。

## 四、测试通道方法论（复用价值）

1. **投递**：`POST /api/runs/stream`，payload 顶层必带 `"on_disconnect": "continue"`（否则 curl 抓取窗口到点断开即杀 run——T1/T2「离奇死亡」根因）；`context.subagent_enabled: true`、`multitask_strategy: "interrupt"`、`recursion_limit: 400`；中文 body 用 UTF-8 文件 `--data-binary`。
2. **鉴权**：`POST /api/v1/auth/login/local`（form-urlencoded）取 cookie jar；后续请求带 `X-CSRF-Token`。
3. **活性真相源**：psql `checkpoints.metadata->>'step'`（deerflow 库）持续推进 = run 活着；runs.status 在 continue 模式下不可信（㉚）。step 暂平 <8min 属子代理执行期正常。
4. **内容读取**：`GET /api/threads/{tid}/runs/{rid}/messages?limit=N`；质检用容器内 `docker exec -i deer-flow-gateway python3 < script.py`（bash 内联双引号正则会吃转义，必须走临时脚本文件）。
5. **观察**：磁盘落盘（chapters/progress.json/outputs mtime+size）+ psql 巡逻，不依赖 SSE 长连接。

## 五、遗留与下一步

1. **run 14（ef795447）**：FORM 27 处 + 双括号 4 处最终清理轮，进行中（step 2728+）；完成后再做一次终检即 T3 收官。
2. **第四轮修补裁决**：决策包 P0 三项（F5/F2+F3）+ P1（F1+F6/F4）+ 增补 F7-F9，待用户裁决范围。
3. **产品侧候选**（技能层外）：前端断开杀 run 的产品语义（㉑）、runs.status 观测性（㉚）、composer submit 按钮失效（M2）。
4. **未提交项**：docker-compose-dev cap_add SYS_PTRACE（EAI-CUSTOM）、config.yaml owner_user_id 修复——随收尾提交。
