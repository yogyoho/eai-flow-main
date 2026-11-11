# 批十六:递交方式集字段批 + covers(null) 硬化(bid-review P1 β16)计划

日期:2026-11-11 · 分支:main-dev-fork · 前置:批十五(f84d9a3c1,未推 3)
用户裁决:「继续」(2026-11-11,按推荐开 ADJ-1+covers(null) 合并批)

## 背景

两条挂账同域合批:① A-ADJ-1(批十一全裁转 live 条件任务)——L1-026 方式集维
挂账,先验已过(批十二探针 58a10ab60:真实招标文前附表 33「电子版不需纸质」+
:100 平台上传,tender_lines 12 行×3 稳定可抽)→ 方式集字段批可开;② covers(null)
判定语义——`covers = str(need) in str(scope or "")`,need=None → "None" in str(scope)
→ False → FAIL 错位(subset_of A-β2-① 同类,批十五 T2 真实件证活体面无泄漏:
eval_core 统一剥 None+缺字段门先咬 → 直评/金标准面防御性硬化)。

## 根因(2026-11-11 调查,rulepack/rule_runner/expr/registry 对读)

- L1-026 v1 只落时间维(`bid.submit_time <= tender.bid_deadline`),方式集维挂账因
  规格无允许集合字段源、bid.submit_method 无消费不落;先验解除。
- dict-step optional 机制(批六T4 A-β6-⑧)现成:「夹具无新字段行为不变」唯一可达通路
  ——optional 键缺席 step 零参与,L1-026 时间维旧行为逐字节保留。
- covers lambda None 不设防;活体面 None 由 eval_core 剥离不可达,直评面可错位。
- universe()=sorted(pack_inputs ∪ anchors ∪ projections ∪ second_stage) 自动派生
  ——L1-026 inputs +2 → 宇宙 126→128(逐位锁两处:registry/rule_families);
  三方精确相等锁(EXPECTED_COVERAGE==pack_ids==covered)不受影响(零新规则 id)。

## 裁决表

| 杠杆 | 裁决 | 理由 |
|---|---|---|
| L1-026 inputs +2(bid.submit_method / tender.allowed_submit_methods)+ dict-step optional 方式集维 | **做** | covers 字串包含语义(spec §7 名称通道禁复用仅限附件集,字段面 covers 是既有 L1-001 先例);optional=双侧在场才判,缺席零参与 |
| covers None 双侧硬化 → KeyError | **做** | need_human 诚实网对齐(subset_of A-β2-① 先例);skill 副本镜像同律 |
| 新独立规则 L1-027 | **不做** | 方式集维是 L1-026 递交维同域(spec A-β7-⑤ 原话「L1-026 方式集维」);新规则 id 动三方精确相等锁+新 golden 案例,YAGNI |
| contains_any needles 空表语义 | **不动** | `needles or []` 空表=False 是既有语义,无规则以 None needles 调用,禁顺手扩面 |
| 递交代规则名改「递交时间与方式符合」 | **做** | 显示面诚实;rule_id/golden/severity 零变化 |

## 任务

- [x] T1 引擎面:rulepack L1-026(inputs+2+dict-step optional 方式集维+comment 挂账解除注记);
  expr.py `_covers`(None 双侧 KeyError)+ 注册表替换 lambda;skill 副本 eval_det.py 镜像;
  labels.py +2;锁面:EXPECTED_UNIVERSE +2 字母序插入 + 126→128(registry test_anchored +
  rule_families 两处)+ 头注 114→116;钉:expr covers KeyError 双侧 ×1、runner L1-026 三态
  (缺席零参与/方式在外 FAIL/方式在内 PASS)+ KeyError 路由 UNKNOWN ×1、extract 两契约
  注册+prompt 可达 ×1;门禁 family `-k bid_review` 只增(基线 765p/6s/0f),lint 双清。
  → 兑付:96b0b39a8,769p/6s/0f(+4 钉),lint 双清,零翻红(optional「夹具无新字段
  行为不变」实证),锁面 128/116/51/60/83/60。
- [x] T2 真实件复采:gateway restart + realcase 探针 ×3 + 定点判读:submit_method/
  allowed_submit_methods 抽出率;L1-026 方式集维 live verdict;golden/family 零翻红;
  模型方差族律:单样本不做硬锚,规则 id 级翻转判读。
  → 兑付:探针 3/3 净(samples 3/2/2 exit 0;21 叶键锚定集不含新键,定点走 j_judge):
  tender.allowed_submit_methods=['电子版上传'] 抽出✓(批十二前附表先验 live 复现)、
  bid.submit_method='电子版上传' 抽出✓、方式集维 covers PASS 零 issue、时间维双缺
  →UNKNOWN 字段缺失门(optional 活体正确);covers(null) 硬化零扰动;L1-010 1F
  真实缺陷(报价加总 vs 大写,批前既有面);批十五契约稳定复现(deposit="10000"/
  license_name=主体名/bid_scope/required_qual_level=None;bid_deadline 单样本
  None=跨样本方差不硬锚)。
- [x] T3 收口:plan 勾兑 + spec 批十六段 + wolf 三件 + session memory + closure。

## 挂账

- OCR 管道边界(eai-flow-ocr :8010 锚;开工提醒 paddleocr-vl)。
- 模型召回边界(业绩表/boq 表格式逐行召回,批十五挂账)。
- _BIN 全局 TypeError 硬化(真实件三试再裁)、万/亿乘数(YAGNI)。
