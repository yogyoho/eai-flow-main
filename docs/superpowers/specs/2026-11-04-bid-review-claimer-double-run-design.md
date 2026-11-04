# claimer 双跑缺陷修复(重复行根因) 设计

> 日期: 2026-11-04 ｜ 状态: 已落地(R4 活体证实,impl f07b2b92f)
> 前置: 页码契约切片 R3 活体回采取证(bug-3973)
> 范围: worker.py `_claim_next` + `boot_recovery`;分派核/落库/规则包零改

## 0. 根因(R3 取证闭环)

1. `_claim_next` 领取 `status IN ('created','extracting')`;created 分支有条件置换 CAS
   (rowcount 校验),**extracting 分支无任何 CAS**——设计意图是领 boot-recovery 孤儿,
   实际把「正在正常跑 extracting 阶段的任务」(routers 直推管线 91s 抽取窗口)一并领走。
2. POLL_SECONDS=5,抽取窗口横跨 ~18 tick ⇒ **每个 API 建的 quick 任务 100% 被双跑**
   (确定性缺陷,非竞态运气)。
3. 双管线完整各跑一遍:两份独立抽取 LLM 调用(「两份字段快照」)+ 两套独立模型确认;
   写入交错(pass 1 :34-35 写 32 行+done,pass 2 :59 写 6 行)→ add_issue 按
   (task_id, dedup_key) upsert,两遍快照实体命名/证据集不同(「附件3 业绩合同」vs
   「3 业绩合同」)⇒ 键不同 ⇒ 不合并 ⇒ 重复行。R1/R2 重复行同根因。
4. 附带成本:每任务抽取 LLM ×2 + 模型确认双倍;done_at 后迟到写入。
5. 排除:det dedup_key 的 message 形状是 crud 有意设计,非缺陷。

## 1. 修复(方案 B,删分支优于加标记)

- `_claim_next`:只领 `status='created'`(CAS 保持);extracting 领取分支删除;
- `boot_recovery`:重置 `parsing/extracting/running` → **created**(原口径 running/parsing
  →extracting)——孤儿断点续跑改走 created→parsing 完整入口,重跑天然幂等
  (parse 跳过已解析条目/基线写前清旧行/add_issue upsert);
- `advance_task` entry='extracting' 参数保留(签名兼容+既有测试引用),claimer 不再产生。

## 2. 六裁决(已批,2026-11-04)

1. 方案 B(删分支+三态重置 created);
2. entry='extracting' 参数保留兼容;
3. 历史重复行(R1/R2/R3)不动——走查证据留真,新任务结构性不再产生;
4. det dedup_key 形状不动——双跑消灭后自然单行;
5. 活体验证跑 R4 走查任务(小配额)断言单批次写入+done 后零写入;
6. bug-3973 随修复入账。

## 3. 验收口径

1. worker +2 回归门先红后绿:extracting 中任务不被 claim;boot_recovery 三态重置
   created 且幂等;
2. 既有两个 boot_recovery 测试随契约更新(running/parsing→created);
3. bid_review 全家 pytest 精确计数全绿;golden 55/55 零翻红;ruff 触碰文件绿;
4. gateway 重启后 R4 活体:issues created_at 单批次聚簇、done 后零迟到写入、
   无重复行(同规则单行)。

## 4. 挂账

- ~~R4 若仍见重复行 ⇒ 本根因判定有遗漏,回炉~~(R4 全绿,未触发);
- 抽取成本减半红利随 R4 顺带收割,不单独立账。

## 5. R4 活体实测(任务 e1fe76f4,链 72e4bf6c,2026-11-04)

| 断言 | 结果 |
|---|---|
| 单管线 durations | parsing 0.078s + extracting 59.7s + review 28.3s,单序列(旧双跑为两套) |
| issues 单批次 | 30 条写入跨度 **0.25s**(20:22:51.73→51.99;旧 R1 双 pass 相隔 ~24min) |
| done 后零迟到写入 | 0 条晚于 task.updated_at 20:22:52 |
| 同规则重复行 | 0(③查询空) |
| 日志单 pass | 窗口内 "baseline extraction"×1 + "sem/hyb using model"×1 + prefilter 单序列;**claimer 对该任务零 claim**(直推 0.078s 先于 5s 轮询领走,CAS 只领 created 生效) |
| 严重度分布 | fatal violation×2 确认 + major violation×1 确认 + 27 need_human,合计 30 条 |

结论:routers 直推路径 claimer 不再劫持,确定性双跑根除;重复行结构性消灭(新任务)。
