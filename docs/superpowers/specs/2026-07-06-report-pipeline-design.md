# 报告处理 Pipeline 拆分设计

日期: 2026-07-06 | 状态: 已确认

## 背景

fire-protection-extract 经过 10+ 轮迭代,根本问题是三个职责捆在一个技能里:
抄录(不能改字)、格式化(要改结构)、扩写(要生成新内容)——规则互相打架。

## 决策: 拆成可组合的 pipeline

| 技能 | 职责 | 改文字? |
|------|------|---------|
| fire-protection-extract | 纯抄录 + grounding + 无关标记(C方案) | 不改 |
| report-format | 去源编号 + 重编号 + 删空节 + 生成目录 | 不改内容,只改结构 |
| report-enrich | 段落扩写 (骨架,以后做) | 生成新内容,标注来源 |
| report-polish | 语言润色 (骨架,以后做) | 改表达,不改技术含义 |

## 调用方式: 多轮,每个技能做完就停

信任级别不同: extract(可信)→ format(半可信)→ enrich(不可信)。
enrich 必须人显式触发。每个技能 SKILL.md 写明"做完就停,问用户是否继续"。

## 本次范围 (B)

1. extract 清理: 删 renumber.py + run.sh 删 renumber 步骤
2. report-format 完整实现: format.py (4步处理)
3. enrich/polish: 只写 SKILL.md 骨架
4. C 方案: extract SKILL.md 加无关内容标记步骤
