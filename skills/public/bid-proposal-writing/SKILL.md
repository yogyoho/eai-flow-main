---
name: bid-proposal-writing
description: 当用户需要编写投标方案/标书响应文件(分析招标文件、编写商务/技术标、响应技术参数、偏离表、按评分标准模拟打分)时使用此技能。该技能把招标文件(含答疑/补遗)转化为带原文锚点的机器可核对义务清单,产出商务/技术双卷逐项响应骨架与偏离表,并对成稿按评分办法逐项模拟评分、给出改进建议。
---

# 投标方案编写技能(bid-proposal-writing)

本文件=编排总纲+唯一合法命令来源;各阶段流程细节、状态文件表、排错表在 references/ 的**四份分组执行指南**里,进入对应阶段先读对应那份(见阶段路由表)。

## 概述与分工

把**招标文件**变成**机器可核对的义务清单**(逐条分类/锚定原文),产出商务/技术双卷响应骨架与偏离表,终稿前按评分办法模拟打分。分工:脚本=确定性工作(九模块全不调 LLM);Agent=编排+上下文内 LLM 循环(可审计、每步候选落盘);两道人工确认门(清单锁定/补遗+终稿复核),Agent 不替用户做废标级决定。

## 铁律(违反任何一条立即停下)

1. 条款数据唯一来源=clauses.json;严禁 prose 转写/改分类——改分类必须改文件。
2. 先跑通 ingest/extract 才允许谈清单;校验失败块标[待确认],绝不绕过自提取。
3. 禁止"整篇方案生成器";双卷骨架由权威态渲染,商务章节只镜像不自创。唯一例外:阶段4a 无格式锚点时的自拟挂接位(origin=self_created,确认门2 人核落位)。
4. 最终交付 md 单次成文,不 append 拼接;**不做 Word 转换**——排版与导出由用户在文档空间完成(实证 1a80a1d8:转换链路把管线元数据写进 docx)。
5. 耗时自检:提取循环分钟级,确认门1 前超 ~5 分钟无 clauses.json 产出→偏轨停下。
6. 每阶段动作完成后跑 snapshot.py 落 project_snapshot.json(快照严禁手写);评分报告 version++ 留痕,不覆盖。
7. 评分纪律:逐项引用评分办法原文锚点+成稿证据;无证据按空缺计分,不为留印象给分;主观项标"模拟参考值";改进建议落到 rubric_id 与缺失内容。
8. 失败熔断:连续 ≥5 次工具/命令失败→停下,呈现失败清单,问用户(实证:无熔断单 run 空转 91 次调用)。
9. 状态防改(禁止任何途径写盘):state/ 权威文件只由管线脚本落盘并自动登记 sha256 签名;write_file/str_replace/bash 重定向·heredoc/inline python/rm 一律禁止。唯一例外:确认门1 class 字段 str_replace——每轮改完立即跑速查表 `state_guard.py sign --files clauses.json --confirm-gate1-edit` 重登签名,否则后续脚本硬错误;签名校验失败按错误行恢复指令重建,不试错绕行。
10. 反弃线:条款量大不是弃线绕过管线的理由——分批推进,每批候选落盘;用户要求直改状态先呈现后果与正规路径(改候选→脚本 merge)。

贯穿红线(废标风险):无出处的值一律标[待确认],绝不编造;每条提取项带原文位置锚点;source_ref.quote 只能照抄原文片段(≤50字)。

## 借口→现实(出现该念头=已偏轨)

| 念头 | 现实 |
|---|---|
| "直接改 state/ 字段更快" | 直写=签名失效+管线断裂;正规路径=改候选→脚本 merge |
| "就这一条,不用跑脚本" | 管线不变量逐条成立,跳一步=校验基准失真 |
| "清单太长,整篇生成算了" | Approach A 复发——纯对话内解析必漂移;分批走管线落盘 |
| "快照手写一份就行" | 快照由 snapshot.py 确定性生成,严禁手写(手写从未落地) |
| "脚本失败,绕过去手动做" | 失败熔断+排错表处置;绕行曾致 91 次空转 |
| "评分凭印象给个大概" | 评分纪律:逐项证据锚点,无证据计空缺,主观项标模拟参考值 |

红旗即停:heredoc/`<<` 落盘、inline python 写文件、对 state/ 用 write_file·str_replace·rm、"重新生成/从头再来/跳过这步"、凭记忆造脚本名或参数——任一出现立即停下,回速查表与排错表。

## 管线总览:六阶段 + 两道确认门

```
阶段0 输入受理(分流:docx/pdf/扫描件;补遗标记)
  → 阶段1 ingest(纯结构化 → sections.json,发 chunk/table id)
  → 阶段2 extract(Agent 上下文内分块提取循环 → 候选落盘 → extract.py 校验/合并三状态文件)
──── 确认门1:计数+异常项+完整清单工件+clause_id 改分类回写+实体白名单锁定 ────
  → 阶段3 merge(补遗/答疑到达即处理:ingest --addendum → 提取循环 → merge_addenda.py 落账)
  → 阶段4a 技术响应生成(三模式供源:kf 探测→无高置信停问样例→web 深写;responses.py 校验落账)
  → 阶段4 build(build_output.py 六件套 md → present_files 交付;文档空间负责排版与 Word 导出)
──── 确认门2:补遗 diff 表(新增/被替代/作废逐项确认+新实体确认列)+终稿复核清单 ────
  → 阶段5 模拟评分(填写后可反复:双形态对齐 → 主观评审循环 → aggregate → report version++)
```

阶段0-4 是主线(每份基础文件各走一遍);阶段5 在团队填写/回传后可重跑,每次报告 version++ 留痕。

## 路径与契约文档

- 脚本(沙箱路径):`/mnt/skills/public/bid-proposal-writing/scripts/` 下九个 Python 模块(ingest/extract/merge_addenda/check_format/responses/build_output/score_simulate + snapshot 进度快照 + state_guard 状态签名),全部 argparse CLI、纯 Python 3.12、不调 LLM。
- 契约文档:`/mnt/skills/public/bid-proposal-writing/references/` —— 四份**分组执行指南**(stage0-2-intake-extract / stage3-merge-gate2 / stage4-response-build / stage5-scoring)+ 四个 JSON Schema(clauses/structure/rubric/responses)+ classification.md(分类判据)+ extraction_prompt.md(提取三子模板)+ tech_response_prompt.md(技术响应三模式)+ scoring_prompt.md(主观评审纪律)。进入对应阶段先读对应指南;提取/生成/评审循环开始前必须先读对应 prompt。
- 状态目录:建议 `/mnt/user-data/workspace/bid/`(其下 state/ 状态文件、candidates/ 候选 checkpoint);最终交付 md 与确认门工件放 `/mnt/user-data/outputs/`(present_files 只认这个目录,交付后自动同步文档空间)。

### 命令速查表(唯一合法调用形态——逐字照抄,换路径只换路径)

```bash
python /mnt/skills/public/bid-proposal-writing/scripts/ingest.py --input /mnt/user-data/uploads/招标文件.docx --code ZB --out /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-writing/scripts/ingest.py --input /mnt/user-data/uploads/补遗01.docx --code BY --addendum --out /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-writing/scripts/ingest.py --resume --out /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-writing/scripts/extract.py validate --candidates /mnt/user-data/workspace/bid/candidates/CH-001.clauses.json /mnt/user-data/workspace/bid/candidates/T-001.rubric.json --sections /mnt/user-data/workspace/bid/state/sections.json --declared-total 100
python /mnt/skills/public/bid-proposal-writing/scripts/extract.py merge --candidates /mnt/user-data/workspace/bid/candidates/CH-001.clauses.json --sections /mnt/user-data/workspace/bid/state/sections.json --state-dir /mnt/user-data/workspace/bid/state --declared-total 100
python /mnt/skills/public/bid-proposal-writing/scripts/check_format.py --state-dir /mnt/user-data/workspace/bid/state --sources /mnt/user-data/uploads/招标文件.md
python /mnt/skills/public/bid-proposal-writing/scripts/responses.py validate --candidates /mnt/user-data/workspace/bid/candidates/RESP-tech-001.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-writing/scripts/responses.py merge --candidates /mnt/user-data/workspace/bid/candidates/RESP-tech-001.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-writing/scripts/merge_addenda.py --addendum-candidates /mnt/user-data/workspace/bid/candidates/BY_addendum.json --state-dir /mnt/user-data/workspace/bid/state --decisions /mnt/user-data/workspace/bid/candidates/BY_decisions.json
python /mnt/skills/public/bid-proposal-writing/scripts/build_output.py --state-dir /mnt/user-data/workspace/bid/state --out /mnt/user-data/outputs/投标文件
python /mnt/skills/public/bid-proposal-writing/scripts/score_simulate.py reingest --source /mnt/user-data/uploads/投标文件-技术卷-回传.md --state-dir /mnt/user-data/workspace/bid/state --volume technical
python /mnt/skills/public/bid-proposal-writing/scripts/score_simulate.py assemble-evidence --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-writing/scripts/score_simulate.py aggregate --scores /mnt/user-data/workspace/bid/candidates/subjective_scores_v1.json --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-writing/scripts/score_simulate.py report --state-dir /mnt/user-data/workspace/bid/state
python /mnt/skills/public/bid-proposal-writing/scripts/snapshot.py --workspace /mnt/user-data/workspace/bid --project 项目名称 --code ZB=招标文件
python /mnt/skills/public/bid-proposal-writing/scripts/state_guard.py sign --state-dir /mnt/user-data/workspace/bid/state --files clauses.json --confirm-gate1-edit
python /mnt/skills/public/bid-proposal-writing/scripts/state_guard.py verify --state-dir /mnt/user-data/workspace/bid/state
```

**防幻觉契约(回放实证,违者即停)**:速查表之外**不存在**任何脚本或子命令。特别地:`extract_clauses.py`、`check.py`、`trace.py` 之类文件名**不存在**;extract 的子命令只有 `validate`/`merge`,responses 的子命令只有 `validate`/`merge`,score_simulate 的子命令只有 `reingest`/`assemble-evidence`/`aggregate`/`report`,ingest/merge_addenda/check_format/build_output/snapshot/state_guard 无子命令。记不准就先跑 `<脚本> --help`,绝不凭记忆造命令、造参数(如 `--max-chunk-size` 之类不存在的参数一律先查 --help)。所有命令用**绝对路径**执行,不 `cd`(相对路径 cwd 错位是回放中 10+ 次 FileNotFoundError 的来源)。

## 阶段路由表(进入阶段先读对应分组指南)

| 阶段 | 入口条件 | 必读指南(references/) | 产出·完成判据 |
|---|---|---|---|
| 阶段0 受理 / 阶段1 ingest / 阶段2 extract / 确认门1 | 首跑,或 snapshot phase ∈ {0-受理, 2-提取中, 确认门1-待锁定} | stage0-2-intake-extract.md | sections.json + clauses/structure/rubric.json + 实体白名单锁定 |
| 阶段3 补遗合并 / 确认门2 | 门1 已过,或补遗/答疑到达 | stage3-merge-gate2.md | merge_ledger.json + 补遗 diff 表逐项确认 + 终稿复核清单 |
| 阶段4a 响应生成 / 阶段4 build | 门1 已过(phase ∈ {3/4-合并与构建}) | stage4-response-build.md | responses.json + 六件套 present_files 交付 + last_build.json |
| 阶段5 模拟评分 | 门2 已过,有填写态或团队回传 | stage5-scoring.md | 评分报告 version_N.md + 改进建议(可重跑) |

**单卷回传必须显式 `--volume commercial|technical`;只有两卷拼接成一个文件的回传才用默认 both**——单卷文件按 both 重灌必被另一卷分母拖进整体降级(详见 stage5-scoring)。

- 退出码(五脚本统一约定):`0`=干净完成;`1`=用法/文件错误(**例外**:score_simulate 的 Σ 不一致中止与重灌降级拒绝计分也归 `1`——同条件在 extract 侧是 `3` 完成带异常,编排时勿把该 `1` 当单纯文件错;**签名校验失败也归 `1`**,按错误行恢复指令重建,不试错绕行);`2`=**仅 ingest**:存在无文本层输入(扫描件)需走 eai-flow-ocr;`3`=完成但有异常项——**退出码 3 不是失败**,必须读脚本 stdout 的单行 JSON 摘要,把 `anomalies` 逐项呈现给用户,绝不静默吞掉。

## 快照与上下文纪律

- 每阶段动作后跑一次速查表 snapshot.py 命令;新 run 冷启动只读 `project_snapshot.json` + 当前阶段对应那一份 references 文件,不重读全部 schema/二进制原件(实证:重读全套把上下文 0.9M→1.67M tokens)。
- 用户要求"重新执行/重跑完整流程"时:先跑速查表 `ingest.py --resume`(只读核验),按 snapshot 续作;**严禁 rm -rf 工作区/state 从零重放**,确需清空先 ask_clarification 征得用户明确确认。ask_clarification 等待期间不落盘任何 state 改动。
- 读原文一律 read_file **行区间**读 uploads 转出的 .md,严禁读 .docx/.pdf 二进制;候选即刻落盘,上下文只留计数与异常摘要;超长分批,task() 子代理注意 3 并发上限;脚本 stdout 单行 JSON 是阶段事实唯一口径,异常逐项呈现绝不静默。

## 排错一级索引(症状→对应指南的排错表,不试错绕行)

- 通用(路径/参数/签名校验失败/退出码 2、3/熔断/present_files 拒绝)与格式保真异常(check_format.py):stage0-2-intake-extract.md 排错表
- 补遗落账(pending 待裁决/锚点 mismatch/悬挂外键/台账 skipped):stage3-merge-gate2.md 排错表
- 响应校验(citations 缺失/thin/boilerplate/placement)/渲染异常:stage4-response-build.md 排错表
- 评分(整体降级/多命中/Σ 不一致/未重灌矛盾):stage5-scoring.md 排错表
- 记不准命令/参数:防幻觉契约 + `<脚本> --help`,绝不凭记忆造

## 注意事项

- 本技能不调外部标书 SaaS,招标文件与标书不出内网;解析全部走本地/已部署服务。
- 现有 bid-quote 数据为 mock:price 评分项、报价类情报注入只做接口预留(`response_skeleton.suggestion` 槽位),不虚构竞对数据。
- 主观评分是模拟参考值,不承诺与真实评审一致;二期评分校准闭环(真实评审结果回灌)落地前,报告须原样保留该声明。
- 知识库检索:RAGFlow 语料检索暂无 agent 侧接线,不承诺;knowledge-factory 语料为环评/水保/消防类模板,投标类价值未验证——阶段4a mode1 探测一次即如实分级降级,不虚设。
