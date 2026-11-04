# bid-review 二期抽取引擎(B 立项,L0-L5 分层管线)设计

> 日期: 2026-11-04 ｜ 状态: APPROVED(六裁决已批,用户「继续」)
> 原文: 用户提供的《bid 侧抽取层设计》(L0-L5 管线/指纹字典/负证据前置/锚点规范/质量门禁)全稿已收到
> 节奏: M0-M5 六里程碑,每 M 独立 plan+切片落地;M0/M1 本文细化,M2-M5 纲要

## 0. 原文判读与现状对照(2026-11-04 取证)

判定层骨架已同构(前序切片),抽取层深度是真实 delta:

| 原文章节 | 现状 |
|---|---|
| §一 norm()/join key 优先级 | ✅ normalize_name+同义词外置(L2-synonyms);通道序 no→norm_name→复合归组→指纹(L2-021)→near-miss 与设计同构 |
| §三 L5 负证据 | ✅ P3:平件 MISSING 行+复合子行全量记 negative_evidence{channels,pool,closest} |
| §4.3 指纹字典 | ◐ fingerprints.yaml 8 类 vs 设计 12 类(缺 保证金回单/授权委托书/法代身份证明/竣工验收/检测报告/制造商授权;我们多 安全生产许可证/纳税证明) |
| §五 条目分组 | ◐ P2 name 基归组+失败→UNKNOWN 已有;设计聚类(项目名/甲方/金额/日期 ≥0.80)未做 |
| §七 状态判定矩阵 | ✅ 四态+EXTRA 不产 Issue 语义一致 |
| 抽取层 L0-L2/L4/§八/§十 | ❌ 全无:page_offset/实体层/锚点 schema/section_tree/交叉自检/抽取金标准 |

现有抽取机制:LLM 单段结构化抽取(`build_extract_prompt`→agnes→`normalize_fields`→baselines),~90 字段路径带 FIELD_TYPE_CONTRACTS 形状契约,[[p.N]] 页标记,无实体/锚点/置信结构(仅 fields_conf 自报)。

## 1. 六裁决(已批 2026-11-04)

1. **架构路线**:LLM 两段结构化抽取映射设计 L1-L3(清单段→实体/指纹段),不上 CV/det 模型;is_blank/is_truncated 用页文本量启发式近似,像素判定 scope-out(诚实降级,不造假数据);
2. **M0 金标准材料**:walkthrough 对起步,2-3 套真实标书对后补;指标先记基线后卡阈值;
3. **锚点 schema**:采纳设计 §六字段集,ocr_conf/logical_page 允许 null(现解析层无此数据),text_hash+text 重合校验照做;
4. **指纹字典**:补齐设计 6 类(yaml 运维即改零代码),保留我们 2 类超集成 14 类;
5. **join key 通道序**:保持现状(已同构)不重排;M1 只补实体级指纹通道;
6. **验收铁律**:每 M golden 55 零翻红+全家零翻红+活体回采;M 序 A/C→B/E→分组,允许穿插中断。

设计稿尾「补 L1/L3 规则包」= 独立队列项挂账(§7),不入本立项。

## 2. 里程碑路线

| M | 内容 | 设计稿对应 |
|---|---|---|
| **M0 抽取金标准** | walkthrough 对标注集+评分器+R6 快照基线+离线回归门+live 评分 CLI | §十 |
| **M1 附件实体层** | attachments[] 实体第二段抽取(页码区间/逐实体指纹/锚点)+负证据 100% 门禁测试+指纹字典补 6 类 | §4.3/§六/L5 |
| **M2 章节层** | section_tree+page_offset 校正+required_sections 对齐 | §4.2 |
| **M3 表格/清单行** | boq_rows 行级+table_cells(required 只从 tender.required_fields 回填) | §4.5 |
| **M4 条目聚类升级** | P2 归组→设计 §五聚类(项目名/甲方/金额/日期 ≥0.80,ungrouped→UNKNOWN) | §五 |
| **M5 交叉自检+质量门禁** | §八三检(声明↔实体/页码偏移>5 降置信/正副本一致性)+§十指标入 metrics+pytest 套件 | §八/§十 |

## 3. M0 细化:抽取金标准(本期切片)

**机制**:判定层 golden(55 题,喂基线测 rule_runner)管判定回归;抽取层 golden 管**抽取本身**——文档→字段期望值标注集(人工读原文标注,独立于模型输出),评分器对 fields dict 打分。

- **标注集** `golden/extract_cases/walkthrough-annotations.json`:26 项检查,value(标量/工期 dict 归一等值)/count(列表长度)/contains(列表项子集匹配,name 走 normalize_name 子串容忍)/shape(结构合规)四类;meta 记基线 pass_rate。
- **评分器** `golden/extract.py`:`score_fields(fields, annotations)`→rows+summary;`score_snapshots()` 冻结快照批量出报告;`--live` 单次活体抽取评分(调 build_baseline 默认抽取路径,烧一次配额,切片边界用)。
- **R6 快照** `extract_cases/r6-snapshot.json`:R6 活体基线 fields 冻结为离线回归地板——抽取/归一/契约层任何改动跑分不降于记录基线,翻红=回归证据(金标准铁律:标注错改标注/引擎错先修引擎)。
- **CLI**:`python -m app.extensions.bid_review.golden.extract`(离线默认;`--live` 活体)。

## 4. M1 细化:附件实体层(下期切片)

- **第二段抽取**:首段(现状)产出清单后,实体段 prompt 输入=清单行+全文页标记文本,输出 `bid.attachments[]`:{no,name,norm_name,pages[],type_fingerprint,fingerprint_conf,is_empty_text,anchor{doc_id,page,pages,text,text_hash}}(ocr_conf/logical_page=null,裁决③);
- **形状闸**:`ATTACHMENT_ENTITY` 契约入 FIELD_TYPE_CONTRACTS+normalize_fields 闸(实体行缺 name/pages 丢行,零编造);
- **指纹分类**:实体段带 fingerprints.yaml 关键词组提示,模型逐实体给 type_fingerprint+conf;未命中→`unknown_type`(不猜);
- **指纹字典补 6 类**(裁决④):保证金回单/授权委托书/法定代表人身份证明/竣工验收报告/检测报告/制造商授权,fingerprints.yaml 即改;
- **负证据 100% 门禁**:matcher 侧 P3 已记行级负证据;M1 加不变量测试——任何 MISSING 行 negative_evidence 缺失即红(设计 §三「L5 是 MISSING 前置条件」);
- **消费面**:L2 指纹通道升实体级(实体 type_fingerprint 直连 checklist fp 键),join key 通道序不动(裁决⑤)。

## 5. M2-M5 纲要

- **M2 章节层**:section_tree(目录页识别+正文标题对齐+is_empty 文本量启发)+page_offset(目录页码↔物理页差>5 降置信,§八2);required_sections 对齐进 L2-010/012/013 消费面。
- **M3 表格/清单行**:boq_rows 行级({id,name,unit,qty,price})+table_cells;`required` 字段只从 tender.required_fields 回填(设计 §4.5 铁律:必填口径唯一来自招标侧)。
- **M4 条目聚类**:业绩/人员条目按(项目名,甲方,金额,日期)聚类 ≥0.80 成条目;ungrouped→grouping.ok=false→UNKNOWN(禁强行 PARTIAL);P2 name 归组保留为快路径。
- **M5 交叉自检+门禁**:清单声明↔实体(声明有实体无→强 MISSING 证据;实体有清单无→提示补清单不判 MISSING,§八1)+正副本一致性+§十指标(核心字段成功率/负证据覆盖 100%/UNKNOWN 占比 ≤0.10)入 metrics/rules 投影+设计 §十 pytest 套件。

## 6. 验收口径

1. M0:标注集 26 检查落地;R6 快照评分=记录基线(离线门测试);golden 55/55+全家零翻红;`--live` 一次活体评分报告入档;
2. 每 M:全家 pytest 精确计数全绿+golden 55 零翻红+ruff 绿+活体回采;
3. 指标演进:M0 基线入档后,M1-M5 每 M 报告抽取分变化,只升不降。

### §5+ M0 活体实测(2026-11-04)

**双层指标语义**(首测即确立):快照地板(SNAPSHOT floor)=冻结 R6 快照 vs 标注集,**26/26=1.0**,确定性,只锁代码回归(normalize/shape/评分器);活体测量(live)=容器内 `--live` 单跑,**19/26=0.7308**——LLM 采样方差大(同 docs 的 R6 任务曾全中)。漏抽 7 项:tender.currency=null、bid.similar_performances=null、bid.appendix_references=[](空列表非 4 行)、attachment_requirements 的 min_count/year_span 细节(安全生产许可证行 min_count=null、业绩合同 year_span=null)。**结论=方差是 B 立项的一等公民问题**,漏抽清单即 M1 两段抽取+提示契约的靶子;活体基线 0.7308 记档,只升不降。

## 7. 挂账

- L1/L3 规则包扩族(设计稿尾②)——独立队列,不在本立项;
- CV 像素级 is_blank/is_truncated——scope-out(裁决①),文本量启发式近似;
- 2-3 套真实标书对后补金标(裁决②)——材料到位扩 extract_cases;
- M2-M5 各自 plan 细化——到点再写。
