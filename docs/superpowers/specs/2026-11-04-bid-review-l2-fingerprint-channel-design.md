# L2 指纹通道(L2-021 附件类型指纹核对) 设计

> 日期: 2026-11-04 ｜ 状态: 已落地
> 前置: P3/P3.2/P3.3+L2-tuning/L2-synonyms/L2-混合态已落地;本切片=二期桶 A 项(裁决见会话 2026-11-04,B 立项另议)
> 范围: 后端 bid_review 扩展内,零上游/harness 改动;前端零改动(issue 卡通用渲染,L1-013 先例)

## 0. 背景与问题

附件匹配现有通道全是**名称文字**通道:no 全等 / normalize_name 全等(P1)/ 近似门(P3)/ 子件归组(P2)。
附件实际存在但名称完全不同(要求「安全生产许可证」、提供项叫「安全资格证书」,sim<0.75 门)时全通道
落空 → 真假 MISSING 混杂,负证据只有文字相似度。P1 spec 原判:「类型指纹 **sem 规则**(semantic_confirm
强制人工)」;P3 §1 原判将其挂账二期。本切片以 **hyb 规则**落地(P1 原判的 sem 形态 + hyb 的零候选
零模型调用红利,llm_runner 管线现成)。

## 1. 机制总览

```
att_missing_rows(det 粗筛,零模型)      规则卡(1 次模型调用,仅有 MISSING 行时)
  MISSING 行逐行候选 ────────────────▶ 指纹字典(外置 yaml)+候选+材料全文
  UNKNOWN 行零发声(L2-020 面)          模型逐候选 verdict:
                                         full=驳回(真缺失,L2-020 已报)→零条目
                                         partial=疑似改名提供→violation 条目+证据
                                         unclear=材料不足→need_human
                                       七道校验 → issues(既有管线零改)
```

六裁决(2026-11-04 会话):①hyb 形态;②字典外置;③触发面=MISSING/near_miss req×未占用池
(v1 收敛为 MISSING 行——UNKNOWN 已有近似候选话术,指纹增量低,YAGNI);④确认命中 need_human/
violation **永不自动 MATCHED**;⑤新规则 L2-021 进规则包+金标准 3 题;⑥外部设计文档不阻塞。

## 2. 组件设计

### 2.1 det 算子 `att_missing_rows`(rule_runner.py)

- `_KNOWN_OPS` + `"att_missing_rows"`;att 族门 `("att_check","att_count","att_missing_rows")`;
- 分支:MISSING 行**逐行** `_issue`(verdict=violation→hyb 候选),`candidate_tpl`(check 键)渲染
  候选消息(与 message_tpl 分离——message_tpl 是 sem 侧 {clause_id}/{verdict}/{reason} 契约,
  两相渲染必须各用各的);entity_keys/dedup_key 按行实体键;
- **UNKNOWN 行零发声**:L2-020 已有近似候选 need_human 面,重复发声=双规则噪音(裁决③收敛);
- 复合父行 MISSING 同样出候选(模型从材料判断,父行子件真相在 checklist);
- 缺附件字段 → inputs 检查既有 need_human 透传路径(§4.4 铁律,零新代码)。

### 2.2 指纹字典(engine/fingerprints.py + engine/dicts/fingerprints.yaml)

- loader 仿 tuning.py:mtime 缓存+锁;校验=顶层 dict、值=非空字符串列表(strip);坏条目逐个丢弃,
  文件缺/坏/空 → `{}`(卡片无关键词提示,模型纯语义判定,退化为弱而非坏);
- yaml 形状:类型名 → 特征关键词组;种子 8 组常见件(营业执照/资质证书/安全生产许可证/审计报告/
  中标通知书/业绩合同/社保缴纳/纳税证明);运维即改,mtime 热感知。

### 2.3 指纹合并进卡片(llm_runner.py run_sem_rule)

入口归一后单点合并:`check.fingerprints == "external"` → 注入 `check["fingerprints"] = loader 产物`。
prefilter 与卡片共用同一 rule dict(att_missing_rows 对多余键惰性);marker 显式(`external`),
不搞隐式魔法。build_rule_card 的判定标准 dump 整个 check → 字典+verdict_gloss 自然进卡。

### 2.4 规则 L2-021(rulepacks/bid-review-core/1.0.0.yaml)

```yaml
- id: L2-021
  name: 附件类型指纹核对
  layer: L2
  type: hybrid
  applies_to: ["*"]
  inputs: [tender.attachment_requirements, bid.attachment_index]
  check:
    op: att_missing_rows
    left: tender.attachment_requirements
    right: bid.attachment_index
    candidate_tpl: "附件「{missing}」未见于投标提供清单"
    fingerprints: external
    verdict_set: [full, partial, none, unclear]
    verdict_gloss: "full=材料中确认无此类附件特征,驳回候选(真缺失已由 L2-020 报告);partial=疑似以其它名称提供,在 reason 给出疑似别名与证据;none=避免使用(语义同 full 时一律用 full);unclear=材料不足以判定转待人工"
  severity: major
  evidence: [A-BID-DOC]
  message_tpl: "附件「{clause_id}」疑似以其它名称提供(类型指纹命中):{reason}"
  fix_tpl: "核对材料中疑似文件,补正附件清单条目名称或补充缺失附件"
  confidence_gate: 0.75
  enabled: true
```

- verdict_gloss 塞 check(dump 即进卡,**零 runner 改动**解决卡片语义注解)——通用机制对后续
  hyb 规则同样可用;
- none 保留在 verdict_set(schema 拒收会触发重试/丢弃级联)但指令引导用 full;模型 stray none →
  violation 条目语义小偏,挂账接受(v1);
- 触发面收敛说明:裁决③原文含 near_miss 行,v1 只扫 MISSING——近似行已有候选话术+人工在环,
  指纹重复确认增量低(挂账,有真实误报案例再放开)。

## 3. 零翻红论证(结构性)

- L2-021 全新 rule_id,不进任何既有题 expect_issues;
- 既有 52 题无 `model_script` L2-021 键 → scripted model 缺省安静 full 应答 → 候选全驳回 →
  零产出;无 MISSING 行的题零候选 → 零模型调用;
- 既有消息/算子零改(att 族门加员不影响既有两算子);golden CLI 52→55。

## 4. 测试(+11)

- rule_runner +3:att_missing_rows 逐行候选(entity/dedup 按行)/UNKNOWN 行零发声/白名单载入;
- fingerprints 新文件 +3:缺文件 {} / 合法载入 / 坏条目丢弃+坏文件 {};
- llm_verify +2:marker 合并进卡片文本(关键词+候选消息在场)/无 marker 零注入;
- golden +3 题(model_script 路由 L2-021):partial 确认命中(疑似别名+证据)/full 驳回零条目
  (L2-020 MISSING 仍在)/unclear 转待人工。

## 5. 验收

1. `PYTHONPATH=. uv run pytest tests/test_bid_review_rule_runner.py tests/test_bid_review_fingerprints.py tests/test_bid_review_llm_verify.py` 全绿(预期 24+3/3/39+2);
2. bid_review 全家 pytest(预期 379+8=387/6);
3. golden CLI **55/55** exit 0(52 存量零翻红);
4. ruff 触碰文件全绿;diff 仅 engine(rule_runner/llm_runner/fingerprints/dicts)+rulepack+golden cases+tests+docs。

## 6. 挂账

- UNKNOWN 行指纹扫描(裁决③ v1 收敛)——真实误报案例驱动;
- stray none verdict 的语义偏(§2.4)——观测;
- 指纹确认条目前端深化(证据跳转已通用,暂无专用卡);
- **B 立项(L0-L5 抽取管线)**:第一步=抽取质量金标准(文档→字段期望值标注集),待用户提供外部设计原文或从 P3 §1 原判独立成稿;
- 运行时生效需 gateway 重启(总挂账不变)。
