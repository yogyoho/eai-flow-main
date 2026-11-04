# bid-review 规则包注册表 R1(registry 索引+lint+字段单源收敛)设计

> 日期: 2026-11-05 ｜ 状态: APPROVED(设计二骨架+七裁决,用户「继续」)
> 前案: 两份外部规则包设计选型=设计二(registry/ 三层)骨架,吸收设计一 consumed_by 反查+互斥对双向校验
> 节奏: R1=零行为变化底座;L1/L3 补族(R2+)按 B立项 M1-M3 字段就位分批激活(规则跟随字段)

## 0. 取证(2026-11-05 实测,零行为改造的依据)

- 单包 `engine/rulepacks/bid-review-core/1.0.0.yaml` 35 条(L1×17/L2×3/L3×15),check.op/expr 元模型;severity=L1 fatal×16+major×1(业绩达标特例)/L2 fatal×1+major×2/L3 major×15;type=det×29+hyb×5+sem×1。
- 字段源两处:`FIELD_DICTIONARY` 24 路径(M1 残遗,**仅 3 路径独有**)vs 规则 `inputs` 68 路径;`collect_field_paths()`=并集 71=抽取请求真宇宙。
- `ANCHOR_REGISTRY` 20 锚(anchors.py 代码单源),锚点路径 62 ⊆ 宇宙 ✓。
- **病灶实锤**:①`A-BID-DOC` 被 L2-021 引用但未注册→`anchor_rule_paths` 静默跳过=证据区悄悄丢(lint 价值自证);②47/68 inputs 不在 FIELD_DICTIONARY(命名误导的残遗副本);③3 个投影字段无声明处——`deviation.items`(B9 偏离表,routers.py:756)/`tender.scoring_items`(评分投影,routers.py:727)/`tender.project_identity.lot_section`(task.lot_name,worker.py:456);④consumed_by 反查缺失(改字段不知道炸谁)。
- 附加发现(挂账):skills `references/rules-det-subset.yaml`=M1 七条副本,第二副本漂移风险。

## 1. 对前七裁决的两处修正(取证驱动)

- **裁决②修正**:registry 落 **python 索引层 `engine/registry.py`,不建 fields.yaml**——取证显示三类源各自已是单源(pack inputs/ANCHOR_REGISTRY/FIELD_TYPE_CONTRACTS 各一份),yaml 主副本=第三份账本零去重价值;真正缺的是跨源机器校验+consumed_by 反查。fields.yaml 等第二规则包出现再议。
- **裁决③修正**:anchors.py 保持代码单源(运行时消费方),R1 只加「包 evidence ⊆ ANCHOR_REGISTRY」硬校验;yaml 化无第二消费者不建。
- **enums 不建 yaml**:severity 3 值+layer 3 值,收敛为 loader 常量白名单:**L1{fatal,major} L2{fatal,major} L3{major,minor}**(L1 major=业绩达标特例,L3 禁 fatal=一致性层不否决)。

## 2. R1 交付物

1. **`engine/registry.py`**(新):
   - `PROJECTION_FIELDS`:3 投影字段→消费面注记(偏离表/评分投影/lot_name);
   - `universe()`:pack inputs ∪ ANCHOR_REGISTRY paths ∪ PROJECTION_FIELDS——**与现 collect_field_paths() 71 路径逐位相等**(零行为锚点);
   - `consumed_by(path)`→{rules,anchors,projections} 反查索引;
   - `lints(pack, contracts)`→violations:evidence 锚未注册/inputs 非点路径/FIELD_TYPE_CONTRACTS 键出宇宙/投影字段未声明/severity 越层白名单。
2. **`load_rulepack` 钩子**(硬拒载,语义层):evidence 锚 ∉ ANCHOR_REGISTRY→RulePackError;severity ∉ 层白名单→RulePackError;input 空/非点路径→RulePackError。(语法/算子/tolerance 校验既有不动)
3. **A-BID-DOC 补注册**:ANCHOR_REGISTRY["A-BID-DOC"]={label:"投标文件附件区域", paths:[tender.attachment_requirements, bid.attachment_index]}——与 L2-021 inputs 同路径=零行为;M1 附件实体落地后扩 paths。
4. **FIELD_DICTIONARY 退役**(extract.py):frozenset 字面量→registry universe 派生别名(函数内懒导入防环);已验证 dict ⊆ inputs∪anchors∪projections,宇宙不变;OCCURRENCE_PATHS/LIST_PATHS/CONTRACTS 保留原位(各自身单源)。
5. **反查 CLI**:`python -m app.extensions.bid_review.engine.registry [path]`——无参打全表(consumed_by 矩阵),带参打单字段。
6. **`tests/test_bid_review_registry.py`**(新):宇宙锚定(=改造前 71 路径全列表+与 collect_field_paths 相等)/consumed_by 抽查(L1-009 消费 bid.total_price;A-PRICE-SHEET 含 bid.total_price)/A-BID-DOC 回归(L2-021 证据解析不再静默丢)/severity 白名单正反例/CONTRACTS⊆宇宙/投影字段声明齐/load 拒载三例。

## 3. 零行为验证门

- `collect_field_paths()` 输出逐位=改造前(测试硬编码 71 路径列表);
- golden 55/55 零翻红;全家 pytest 精确计数全绿;ruff 触碰文件;
- M0 抽取快照 26/26(抽取请求与提示词零变化)。

## 4. 挂账

- skills `references/rules-det-subset.yaml` 七条副本漂移——独立队列(副本对账或删除改引用);
- L1/L3 补族(R2+)按 B立项 M1(附件实体)/M2(section_tree)/M3(table_cells/boq) 字段就位分批;
- fields.yaml/anchors.yaml yaml 化——第二包/第二消费者出现再议;
- L4 包——不建;互斥对(质保 L1-015 不足 vs 承诺超额)等真实需求立项时挂 registry 注释。
