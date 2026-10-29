---
name: bid-proposal-review
description: 当用户需要审查投标方案/标书(合规红线 L1、一致性 L3,输出带证据的问题清单)时使用此技能。两种模式:管线自审(零后端,det 规则本地求值)与子系统审查(经 bid_review MCP 工具走审查引擎工作台)。审查结论=辅助提示,最终责任由投标主体承担。
---

# 投标方案审查技能(bid-proposal-review)

本文件=编排总纲+唯一合法命令来源;两模式编排细节、字段提取对照表、排错表在 references/workflow.md,进入任一模式先读对应章节。

## 概述与分工

两模式:①管线自审——读 field_snapshot 跑 scripts/eval_det.py(副本求值器,自包含),输出问题清单 md;②子系统审查——bid_review MCP 七工具(start/status/issues/issue/feedback/baseline_get/rulepacks)编排引擎审查,**确认门在 UI 由用户点,agent 绝不代确认**。

分工纪律:脚本=确定性判定(纯 stdlib+PyYAML,不调 LLM);agent=编排+证据补齐+向用户呈现。铁律 1 在自审模式的落点:求值器产出的问题 `evidence` 一律为空数组——**补齐 文档+页码+原文摘录 是编排层(agent)的交付责任,不是求值器的**;未补齐证据的清单不得呈现给用户(操作细节见 workflow.md §自审 Step 4)。

## 铁律(违反即停)

1. 证据锚点强制:每条问题必须带文档+页码+原文摘录;无证据不出结论。
2. 引擎唯一:子系统已跑的任务,编排模式不本地复算语义结论;冲突以库内为准。
3. 不替用户做废标级决定:基准确认/复核动作指向工作台 UI,不代点。
4. 失败熔断:连续 ≥5 次工具失败即停,呈现失败清单。
5. 数值不心算:引用字段或 bid_review_issues 返回值。
6. 四类硬围栏绝不生成:报价数字/资质证号/公司实体名/招标原文引用(照抄原文摘录作证据不属『生成』——『生成』=凭空编造文档中不存在的值,与 workflow.md Step 4 证据回填不冲突)。

## 命令速查表(唯一合法形态)

(自审模式;字段提取详见 references/workflow.md)

```bash
python /mnt/skills/public/bid-proposal-review/scripts/eval_det.py selftest
python /mnt/skills/public/bid-proposal-review/scripts/eval_det.py run --fields /mnt/user-data/workspace/bid/fields.json --out /mnt/user-data/workspace/bid/issues.json --md /mnt/user-data/outputs/问题清单.md
```

**防幻觉契约**:`eval_det.py` 只有 `selftest`/`run` 两个子命令;`run` 只有 --fields/--rules/--out/--md 四个参数(--rules 缺省=references/rules-det-subset.yaml)。上两条即本技能全部合法命令形态,不存在其他脚本或子命令;记不准先跑 `--help`,绝不凭记忆造。

## 路径与契约文档

- 脚本:`/mnt/skills/public/bid-proposal-review/scripts/eval_det.py`(自审 det 副本求值器;canonical 引擎在子系统 bid_review engine/,副本同步按多副本分发纪律,规则文件与 issue-schema 为唯一契约)。
- 契约文档:`references/workflow.md`(两模式编排细节+字段提取对照+排错表)、`references/rules-det-subset.yaml`(M1 七条 det 规则副本;dotted 字段路径=规则↔求值器↔呈现三方契约,禁改名)、`references/issue-schema.json`(问题清单落盘格式)。
- 工作目录:fields.json/issues.json 放 `/mnt/user-data/workspace/bid/`;交付 md 放 `/mnt/user-data/outputs/`。

## 模式路由

- 无子系统/离线 → 自审模式(读 workflow.md §自审)
- 有 bid_review MCP 工具 → 子系统模式(读 workflow.md §子系统)

## 排错一级索引(症状→workflow.md 对应排错表,不试错绕行)

- 字段缺失→need_human / 退出码 3 / selftest 失败 / 消息残留占位符 / 证据定位不到原文:workflow.md §自审排错表
- MCP 工具不可用 / 任务 failed / awaiting_confirm 停留 / issues 空数组 / feedback 报错:workflow.md §子系统排错表
- 记不准命令/参数:防幻觉契约 + `<脚本> --help`

## 注意事项

- 输出定位=辅助提示(检查结论,不是投标决策/法律意见);给用户的清单固定带免责声明:"辅助提示,最终责任由投标主体承担"。
- 自审结论标 `source=local-det`,子系统结论标 `source=engine`;两者冲突以库内为准并如实呈现分歧,不混排。
- quick=只跑 L1 det 规则(否决项风险概览);deep=L1+L3 全量+工作台复核。v1 无 L2/L4(完整性/质量承诺层属 v2)。
