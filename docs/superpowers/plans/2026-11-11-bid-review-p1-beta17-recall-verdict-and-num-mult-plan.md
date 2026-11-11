# 批十七:模型召回边界裁决 + _BIN/_OPS 全局硬化 + 万/亿乘数(bid-review P1 β17)计划

日期:2026-11-11 · 分支:main-dev-fork · 前置:批十六(6333d9f6a,已推)
用户裁决:「先执行2,3,4」(2026-11-11,挂账序号②模型召回边界③_BIN硬化④万/亿乘数;①OCR 批缓,待 paddleocr-vl)

## 背景

三挂账同轮清偿。②批十五挂账「模型召回边界」(业绩表契约到位但 similar_performances
None 3/3、m4 entries=0×3,与 m3 boq_rows=0 同域);③批十四挂账「_BIN 全局 TypeError
硬化」(批十四 L1-009 单点 num() 修复的全局化);④批十四挂账「万/亿乘数」(当时 YAGNI,
用户本轮点名升格)。

## 根因(2026-11-11 调查,realcase md/expr/rule_runner/eval_det 对读)

- **②(先行调查改裁决)**:/tmp/realcase-bid.md :300 业绩表=**空模板表**(表头+
  1/2/3/4/…行全空格);:188/ Tender :1029 分项报价表=同款空模板 → similar_performances
  None/boq None/m4 entries=0 全系**诚实抽取**,非召回失败。「模型召回边界」在本样本
  **不可裁**(与批十二 ADJ-1 合成夹具零内容不可裁同构),须含**实填充业绩/清单**的
  样本方能测召回——挂账降格改记「需实填充样本」,零代码。
- **③**:比较算子两张表——expr.py `_BIN`(7 算子,表达式面)+ rule_runner.py `_OPS`
  (3 算子,卡 op 形态 left/right 面)。误配型(str<=dict)TypeError 逃 run_det_rule
  唯一 `except KeyError` 网 → eval_core 逐规则隔离兜底 → **ERROR**(基础设施语义,
  批三五值域)=「数据不可判」误占基础设施故障位。skill 副本 eval_det.py 同构两面
  (_BIN :27 + op 分派 :315)。
- **④**:_num 文本分支剥 %/千分位/元后直 float;「230万」「2.3亿」类乘数后缀直
  KeyError。乘数路径走 Decimal(和 sum 同库)保精确(2.3×1e8 二进制浮点漂移
  230000000.00000003),无乘数路径 float(s) 逐字节保留。

## 裁决表

| 杠杆 | 裁决 | 理由 |
|---|---|---|
| ② 模型召回边界 | **销账降格**:改记「需实填充样本再裁」 | 本样本空模板表,诚实抽取;零代码,YAGNI |
| ③ _BIN+_OPS TypeError→KeyError 包裹 | **做** | need_human 诚实网对齐(批十四 num 律);ERROR 位归还基础设施语义;镜像两处同改 |
| ③ "in" 的 `b or []` 空真值语义 | **不动** | 批二既有语义,禁顺手扩面(contains_any 同裁) |
| ④ _num 万/亿乘数(单后缀,Decimal) | **做** | 用户点名;无乘数路径零变化;大写汉字数字(「十万」类)不做=非证形态,float 败走 KeyError 诚实网 |
| ④ 亿万连写/复合乘数(「万万」) | **不做** | 非证形态;单后缀 break,残余 float 败 KeyError |

## 任务

- [ ] T1 引擎面:expr.py `_safe_cmp` 工厂+`_BIN` 包裹+`_num` 万/亿(Decimal);
  rule_runner.py `_OPS` 包裹(import _safe_cmp);skill 副本 eval_det.py 三面镜像
  (_BIN/op 分派/_num)+ selftest;钉:expr TypeError→KeyError ×1、num 万/亿 ×1、
  runner _OPS 误配型→UNKNOWN(非 ERROR)×1;门禁 family 只增(基线 769p/6s/0f),
  lint 双清,零锁面(128/116/51/60/83/60)。
- [ ] T2 真实件复采:gateway restart + 探针 ×3 + j_judge:ERROR 面清零核验(硬化前
  真实件 ERROR 计数对照)、verdict 分布零退化;②裁决入 spec 零代码。
- [ ] T3 收口:plan 勾兑 + spec 批十七段 + wolf 三件 + session memory + closure。

## 挂账

- OCR 管道边界(eai-flow-ocr :8010 锚;开工提醒 paddleocr-vl;① 用户缓,待 paddleocr-vl)。
- 模型召回边界(降格:需实填充业绩/清单样本再裁——空模板样本不可裁)。
