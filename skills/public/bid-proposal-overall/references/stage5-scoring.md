# 阶段5: 模拟评分(终稿提交前必跑; 可重跑, 报告 version++ 留痕)(分组执行指南)

进入条件: 确认门2 已过(snapshot `phase` ∈ {4-已构建, 5-评分已完成}), 且有"会话内填写态"或团队回传稿。
本组配套契约(进入评审循环前先读): `scoring_prompt.md`(主观评审纪律与输出记录格式)。
命令一律照抄 SKILL.md 速查表(唯一合法调用形态); 本文给流程与判据, 不重复罗列调用。

## 先对齐成稿状态, 再评分——两种形态

- **会话内填写态** = clauses.json/structure.json 当前状态(即时, 无需重灌; 证据行可为空, 评审对象=会话内骨架——Agent 自行 grep 技术卷.md/商务卷.md 检索证据)。
- **团队回传 Word(文档空间导出或外部编辑)** = 先经 uploads 自动转换(docx→md, 既有链路), 再确定性锚点重灌——**重灌输入必须显式指定**(用户指定或线程内最新回传, 防多版回传并存时灌了旧版)。

### 重灌命令要点(命令照抄速查表)

- **单卷回传必须显式 `--volume commercial|technical`**——它把命中率分母与锚点遍历限定在该卷(另一卷不计 hit_rate、不产未命中异常、权威态不动; 卷内多命中/重复 id/未命中照旧全量异常)。
- 只有**两卷拼接**成一个文件的回传才用**默认 both**: 分母恒含双卷全部锚点, 单卷文件按 both 重灌必被另一卷分母拖进整体降级(技术卷零缺陷也救不回来)。
- 分两次各灌一卷时, 每次都要带对应 `--volume`, 两次重灌互补更新权威态。

### 重灌锚点契约(载体在阶段4 渲染时已埋定)

- 商务卷锚点=structure.json 树路径标题链(章节标题=招标文件规定结构, 改标题即形式违规→标题天然稳定);
- 技术卷锚点=条目标题内嵌的 clause_id。
- 不重灌会出现"客观项按旧状态计 0 分、主观项按新稿评高分"的自相矛盾。

### 匹配器硬化(D6, 四类失败全显式)

- 同一锚点多命中→**不取首个**, 整项进异常区待人核;
- 匹配前文本归一化(去编号/空白/全半角), 防样式改动导致精确匹配雪崩;
- clause_id 在回传稿重复出现(Word 修订模式)→异常区;
- 命中率低于阈值(`--threshold`, 默认 0.6)→整体降级为"人核覆盖率清单", 不做部分计分。
- 匹配失败项标 `needs_human_verify`——既不计 0 分也不静默通过, 汇总进评分报告异常区。

## 评分三分类

- **objective** 项=确定性汇总(基于重灌后的清单状态, 是汇总不是验证);
- **price** 项=标"无法模拟"(依赖竞对报价, 现库为 mock, 不虚构竞对数据);
- **subjective** 项=Agent 逐项 LLM 评审(纪律见 `references/scoring_prompt.md`: 评分办法原文为尺、证据 grep 定位、**逐项独立评审防锚定**、给分+理由+失分点、主观分标"模拟参考值")。

## 执行序列(四步)

1. `score_simulate.py assemble-evidence`(命令照抄速查表)→ `evidence_pack.json`(逐 rubric 项: 关联条款+证据行+评审提示)。
2. Agent 读证据包跑主观评审循环(**每次只呈现当前 rubric 项及其证据, 不呈现其他项得分**——防锚定), 逐项记录 `{"rubric_id","score","max_score","rationale","evidence_quote","missing_points","improvement"}`, 落盘为评分记录 JSON(裸数组或 `{"records":[...]}`, 如 `candidates/subjective_scores_v1.json`)。
3. `score_simulate.py aggregate`(命令照抄速查表; Σmax_score 纵深复检, 不一致→异常中止**不落汇总**; objective 确定性汇总; price 标无法模拟; 消费主观记录)。
4. `score_simulate.py report`(命令照抄速查表)→ `state/评分报告/version_N.md`: 逐项得分/满分/理由/失分原因+改进建议清单(按 失分值×可改性 排序)+异常区(needs_human_verify/重灌失败/降级项); 主观分标注"模拟参考值"; **version++ 不覆盖历史**。向用户呈现报告并按铁律7 落改进建议(每条落到 rubric_id 与缺失内容, 不写空话)。

重跑评分=重复 assemble-evidence→评审→aggregate→report, 新报告 version 递增。重跑后跑一次 snapshot.py 更新快照(报告 version 留痕)。

## 本组状态文件

| 文件 | 产生 | 含义 |
|---|---|---|
| `state/reingest_result.json` | reingest | 回传稿锚点重灌事实+异常区(命中率/多命中/重复 id/未命中) |
| `state/evidence_pack.json` | assemble-evidence | 逐 rubric 项证据包(主观评审输入) |
| `state/aggregate_result.json` | aggregate | 三类分项汇总(objective 汇总/price 无法模拟/subjective 消费主观记录) |
| `state/评分报告/version_N.md` | report | 评分模拟报告(version++ 不覆盖历史) |

**完成判据**: 报告 version_N.md 落盘+呈现用户+改进建议逐条落 rubric_id+snapshot 更新。

## 排错表(本组症状→处置, 不试错绕行)

| 症状 | 处置 |
|---|---|
| 命中率整体降级(低于 `--threshold` 默认 0.6) | 检查重灌是否灌对**版本与卷**(`--volume` 缺省 both, 单卷回传必带); 版本对仍降级→按"人核覆盖率清单"如实呈现, 不做部分计分 |
| 锚点多命中进异常区 | 不是错误——D6 显式化设计, 人工核对回传稿对应条目后在报告中如实标注 |
| aggregate 报 Σ 不一致(退出码 1, 中止不落汇总) | 核对主观评分记录的 rubric_id/max_score 与 rubric.json 一致(评审循环抄错尺子), 修正评分记录后重跑 aggregate |
| "客观项 0 分但主观项高分"自相矛盾 | 回传稿没重灌——先 reingest 再评分(见重灌锚点契约) |
| score_simulate 退出码 1(Σ 不一致中止/重灌降级拒绝计分) | **例外语义**: 同条件在 extract 侧是退出码 3; 此处 1 不是文件错, 按摘要处置, 勿当单纯文件错重试 |
| `needs_human_verify` 项 | 不计 0 分不静默通过——汇总进报告异常区, 提示用户人工核对对应条目 |
