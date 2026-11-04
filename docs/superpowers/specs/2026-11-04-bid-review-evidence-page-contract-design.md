# evidence.page 契约修复(页码契约三层) 设计

> 日期: 2026-11-04 ｜ 状态: 已落地(本切片全量,含 R3 活体回采)
> 前置: 围栏容错切片回采新发现 §4-①(剥壳后暴露,模型确认层复活最后拦路石)
> 范围: engine/verify.py check_schema 页码容忍 + engine/llm_runner.py 提示契约 + worker.py _collect_docs_text 真分页;align_evidence 零改

## 0. 发现(三处叠加致死链,R2 活体证据)

1. **check_schema 硬性正整数**(verify.py:108):模型回 null/字符串页码即 schema_discard →
   重试同形必败 → 确认段死在重试循环(R2: `evidence[0].page 必须为正整数`)。
2. **SCHEMA_HINT 无契约**(llm_runner.py:37):示例硬编码 `"page": 1` 但无语义说明;
   text-kind(.md,材料无 `[[p.N]]` 标记)模型不知页码从何填起。
3. **docs_text 整篇挂 page 1**(worker.py:127):PDF 材料带真实 `[[p.N]]` 标记(parse.py:385),
   模型引 [[p.37]] → page=37 过 schema → 对齐查 page 37 无此文 → 降级 need_human。
   **PDF 确认同样死——只修 schema 确认层复活一半。**

好消息:align_evidence 原生 `{page: text}` 契约且已容忍 page=None(`page or 0` ±1 恰命中 page 1),零改。

## 1. 修复(三层,单方向)

| 层 | 文件 | 改动 |
|---|---|---|
| 提示契约 | llm_runner.py | build_rule_card SCHEMA_HINT 后加页码契约行:「材料带 [[p.N]] 标记时引该页码;材料未分页时固定填 1」;PROMPT_VERSION bump |
| schema 容忍 | verify.py check_schema | page 放行 正整数/null/缺省/数字字符串(就地转 int);垃圾类型(非数字串/浮点/bool)照拒留清晰报错 |
| 真分页 | worker.py _collect_docs_text | 按 `[[p.N]]` 标记切分 `{page: 该页起至下标记前文本}`;无标记 → 现状 `{1: 全文}`;首标记前散文本并入首标记页 |

null/缺省语义 = 未锚定 → 对齐层落 page 1(v1 未分页文档的真值);引错页仍诚实降级,不静默采信。

## 2. 六裁决(已批,2026-11-04)

1. 范围:连 PDF 真分页一起修(同契约点;只修 schema 确认层复活一半);
2. 容忍边界:null/缺省/数字字符串放行,垃圾照拒;
3. null 语义:未锚定 → 落 page 1;
4. 首标记前散文本:并入首标记页(±1 容差下无害);
5. PROMPT_VERSION:bump 留痕;
6. 活体验证:R3 新建走查任务(prev_task_id 挂 7c6aec02;done 任务 retry 409),
   期望 L2-021/L1-013 确认段首次活体存活 + entity join 确认路径首证。

## 3. 验收(落地实测)

1. llm_verify **48** 全绿(46+2;page 容忍先红,垃圾拒绝为守卫绿);
2. worker +3(无标记守卫绿/标记切分红/散文本归属红)全绿;
3. bid_review 全家 pytest **403 passed / 0 failed** exit 0(claimer 单测一次 flaky 单跑即绿,
   bug-3967 挂账观测,全家未复现);golden CLI **55/55** 零翻红 exit 0;
4. ruff 触碰文件绿(format 修 llm_verify 1 文件);
5. **R3 活体回采**(任务 72e4bf6c,版本链挂 7c6aec02,quick 模式):
   - **确认段零 schema_discard**:R3 窗口仅 1 次 not_json retry(attempt=2 过),R2 为多次 discard——重试死循环灭;
   - **L1-013 出 nh=f 确认行**:evidence 全 page=1 按契约填 → 对齐通关 → need_human 清除(全七道过);
   - **null 页过 schema 存活**:L1-013 nh=t 行 evidence 含 `page: null`,verdict=violation 照常落库(R2 同形态直接 discard);
   - **诚实降级不静默采信**:L2-021 C2 引 page=9(.md 无标记整篇挂 page 1)→ 对齐失配 → nh=t,条目与实体保留;
   - **echo 合规延续**:L2-021 双候选 C1/C2 id 均被模型回显;C1(★附件2 全缺)确认违规 nh=f——
     **entity join 确认路径首次活体观测**(挂账项兑现);
   - summary `{fatal:3, major:3, need_human:32}` 与 DB nh=f 行精确一致(R2 的口径不一致未复现);
   - 429 未复现(本轮配额内)。

## 4. 挂账与回采残留

- **P1 重复执行/双快照重复条目**(队列②,未动):L1-013/L2-021/L2-020/L2-024 仍见同规则多行
  (两份执行/快照,det 行+确认行与真重复混杂),dedup_key 因 clause/evidence 差异不合并;
  R3 summary 口径已一致,该挂账缩窄为「重复行合并」单点;
- **P2 抽取形状契约**(队列③,未动):L1-016/L3-018 `求值期字段缺失 'e.value'/'c.value'`
  need_human 行仍在(标量形状未修);
- 模型引文恰好含 `[[p.N]]` 字面量时对齐相似度略降(边缘,不处理);
- 429 免费档限流(运维决定,非本切片);
- L1-003 确认行 nh=t(confidence 门槛按设计转人工,R2 同形态,持续观测)。
