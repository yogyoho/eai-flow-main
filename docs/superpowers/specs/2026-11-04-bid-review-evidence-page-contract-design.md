# evidence.page 契约修复(页码契约三层) 设计

> 日期: 2026-11-04 ｜ 状态: 设计定稿(六裁决已批)
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

## 3. 验收口径

1. llm_verify +2(page 容忍/垃圾拒绝)先红后绿;
2. worker +3(无标记/有标记切分/散文本归属)先红后绿;
3. bid_review 全家 pytest 精确计数全绿 exit 0;golden CLI 55/55 零翻红
   (golden runner docs_text="" 走 eval_core 缺省,不经 _collect_docs_text,不受影响);
4. ruff 触碰文件绿;gateway 重启后 R3 活体采证。

## 4. 挂账

- 模型引文恰好含 `[[p.N]]` 字面量时对齐相似度略降(边缘,±0.9 阈下可容忍,不处理);
- entity join 确认路径首证依赖 R3 模型行为,若仍未见继续挂账观测;
- 429 免费档限流(运维决定,非本切片)。
