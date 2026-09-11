# 阶段3+确认门2: 补遗/答疑增量合并 → 终稿复核(分组执行指南)

进入条件: 确认门1 已过(白名单已锁定, snapshot `phase` ∈ {3/4-合并与构建}), 或补遗/答疑文件到达。
本组配套契约(进入前先读): `extraction_prompt.md` 子模板①(补遗块提取循环)、`classification.md`(新条款分类判据)。
命令一律照抄 SKILL.md 速查表(唯一合法调用形态); 本文给流程与判据, 不重复罗列调用。

## 阶段3 merge(补遗/答疑增量合并——隐藏废标项主藏身处)

补遗文件**到达即处理, 不重开已过的确认门**; 合并 diff 统一在下一次确认门/确认门2 呈现。流程:

1. `ingest.py --addendum --code <补遗代号>`(命令照抄速查表)→ 补遗块进 sections.json。
2. Agent 对补遗块跑阶段2 同款提取循环(子模板①), 并产出**合并候选映射**: 每份补遗=一次调用=一个候选文件, 形态 `{"addendum_file": "...", "entities": [{"type","value"}](可选, Agent 从补遗文本观察到的实体), "items": [{"mapping_id", "action": "new|modify|void", "anchor"(章节锚点)或 "target"(条款 id)之一, "clause"(new/modify 的新条款载荷)}]}`。
3. 三级合并算法(脚本确定性执行, 绝不静默取首个):
   - ① 锚点精确匹配且在活条款(未 superseded/未 voided)中唯一命中→自动落账;
   - ② 相似度候选(仅 target 无 anchor)→**脚本不合并**, 产出新旧并排 diff(pending)待确认门2 人工裁决;
   - ③ 平手(锚点多命中)/同目标冲突→必须 `--decisions` 人工裁决(apply 需带 target 且属于候选集; reject 对任何层级都有效, 是冲突解除手段)。
   - 锚点唯一命中但与显式 target 不一致→异常 `anchor_target_mismatch`, 不合并(绝不静默取其一)。
4. 确定性落账(`merge_addenda.py`, 命令照抄速查表; `--decisions` 形态 `{"decisions": [{"mapping_id", "decision": "apply|reject", "target"?}]}`, 首次运行可省, 产出 pending 后再补人工裁决重跑)。

落账语义(逐条记牢, 确认门2 diff 表按此口径呈现):

- 新增条款强制 `from_addendum=true`(载荷写 False 也覆盖); 修改→旧项 `superseded_by` 指向新 id; 作废→旧项标 `voided`(落盘不因后续外键异常回滚)。
- 幂等台账 `merge_ledger.json` 按候选内容哈希: 同一补遗跑两遍整体跳过零写入(摘要 `skipped=true`, 属正常完成不是异常)。存在 pending/异常时不记台账——重跑须能重新浮出。
- **D3 新实体**: 补遗实体 diff 白名单→增量清单 `addendum_entities_pending.json`(累积式: 既有 pending ∪ 本次新增 − 当前白名单; 白名单缺失→`whitelist_missing` 异常, 按空集 diff 全量进清单, 不静默)。
- **D7 悬挂外键**: 落账后扫描 structure/rubric 的 `linked_clause_ids`, 指向缺失/superseded/voided 条款→`clause_fk_invalid` 异常清单不静默(扫描型发现, **不阻断落账**, 待人工改链)。
- 落账后**重跑速查表 check_format.py 命令**(`--sources` 加上补遗转出的 .md)复核格式保真; 退出码 3 的 anomalies 逐项呈现。

## 确认门2(补遗合并确认 + 终稿复核)

话术模板(逐字使用, 计数按实际填):

```
补遗已合并、骨架已产出,请确认两件事:
一、补遗合并 diff 表(工件 outputs/补遗diff表.md),逐项确认(有异议报 mapping_id):
  - 新增 X 条 / 被替代 Y 条 / 作废 Z 条(被替代=旧条款已 superseded,按新条款响应)
  - 新实体确认列:补遗新增实体已默认勾入白名单,可人工增删
    (确认后我更新 entities_whitelist.json 并重跑同一补遗候选,增量清单清零)
二、终稿复核清单(人核清单.md),format_check 项必须人工签字,skill 不做最终承诺:
  - 格式:签字/盖章/份数/页码/目录(全部人核)
  - 资质:证书扫描件是否已替换占位图
  - 报价:价格表与报价策略(是否开标前最终确定)
  - 承诺:服务承诺/质保期措辞
  - 生成内容:阶段4a web 引用逐条核实(人核清单第四节)+自拟挂接位落位确认
    (origin=self_created 章节,标题与位置是否符合本标实际)
确认无误后即可在文档空间把双卷 md 排版导出、分发团队填写;回传后进阶段5 模拟评分。
```

Agent 动作: ①把 merge_addenda 摘要的 applied/pending/anomalies 整理成 diff 表工件(直接写 `/mnt/user-data/outputs/补遗diff表.md`, 单次成文——present_files 只认 `/mnt/user-data/outputs/`), `addendum_entities_pending.json` 列"新实体确认"列(D3: 补遗新增实体默认勾入白名单, 人工可改, 阶段4 lint 始终用最新白名单, 防补遗后合法新实体被误报[待核对]); ②用户确认新实体后写入 entities_whitelist.json(白名单 Agent 手写不签名), **重跑同一 `--addendum-candidates`**(幂等台账零写入, 但实体 diff 使增量清单清零删除, 摘要 `written` 以 `del:` 前缀反映); ③待裁决映射(pending_decision/tie/conflict)按用户决定写 `--decisions` 文件重跑落账; ④过门后跑一次 snapshot.py 更新快照。

## 本组状态文件

| 文件 | 产生 | 含义 |
|---|---|---|
| `state/merge_ledger.json` | 阶段3 落账 | 补遗内容哈希台账(幂等: 同 hash 重跑整体跳过; 台账/清单写盘即签) |
| `state/addendum_entities_pending.json` | 阶段3 D3 | 补遗新实体增量清单(累积∪−白名单; 白名单确认后出清删除并撤销登记) |

**完成判据**: 确认门2 用户确认(新实体确认+终稿复核清单逐项过)+过门后 snapshot.py 更新; 之后可分发/进阶段5。无补遗的纯主线项目, 阶段4 build 后直接过确认门2(补遗 diff 表为零条目形态)。

## 排错表(本组症状→处置, 不试错绕行)

| 症状 | 处置 |
|---|---|
| 摘要 `pending_decision`(tier=similar/tie/conflict) | 不是失败——退出码 3, 按话术模板呈现 diff, 写 `--decisions` 后**重跑同一命令**落账 |
| `anchor_no_match` | 章节锚点在活条款中无命中(且非已落账重放)——回原文核对该映射锚点或改用 target, 修正候选后重跑 |
| `anchor_target_mismatch` | 锚点唯一命中与显式 target 不一致——人工核对哪个对, 修正候选(anchor 或 target)后重跑, 绝不静默取其一 |
| `clause_fk_invalid`(reason=missing/superseded/voided) | D7 扫描发现, 不阻断落账——structure/rubric 的 linked_clause_ids 指向了失效条款, 人工改链或对替换后新 id 重跑相关阶段 |
| 摘要 `skipped=true` | 台账命中, 同一补遗已落账——正常幂等跳过, 零写入; 若预期有新内容, 检查是否拿错候选文件 |
| `replay_content_mismatch` | 重放链命中的库内新条款载荷与本次候选不一致(部分落账后候选被编辑)——异常浮出不重放, 核对后以最新候选为准重跑 |
| 新实体确认流程 | 用户确认→Agent 手写 entities_whitelist.json 增补→重跑同一 `--addendum-candidates`(幂等)→增量清单清零(`del:` 前缀) |
