# 推理工作台 · 未实现功能梳理与技术方案（白盒化分期）

日期:2026-10-02 · 状态:**IMPLEMENTED(四期全部落地)** · 关联:推理白盒化(TODOS,已兑现)、bug-owlrl-property-chain-silent-noop

> 落地记录(2026-10-02,提交 43bf1ea31 / ebb6174ef / d272e2eb8 / fe707d4ba / 8a8813ff2):
> CQ 验收自动化(F5 提前)→ 一期 F1/F2/F7 → 二期 F3 → 三期 F4/F6 → 四期 F8/F9,全部实现并浏览器实测。
> 与原设计的唯一偏差:F8 启停状态采用 kernel 卷 overlay(rules_state.json)而非改规则定义——与定义分离、链规则亦可停。

---

## 操作手册(七字诀)

前置:打开 `http://localhost:2026/ontostudio/` → 侧栏「建模层 · 推理工作台」(06)。
数据前提:实体已确认入图(dg_*)且跑过一次「全量装载」把 SQL 真相灌进内核(导出互操作页/抽取导入页按钮)。

### 算 = 全量重算 + CQ 验收
1. (可选)右上「置信度门限」输入 0.5–1.0(默认 0.7,低于门限的实体不参与推理)。
2. 点「全量重算」→「推理中…」(千级图 ~15-30s)→ KPI 三卡刷新:物化/派生合计/耗时(≤15s 闸门)。
3. 「验收问题」面板自动重判:每条 CQ 是 cq.yaml 里的 ASK 查询,PASS/FAIL 真跑得出;FAIL 行显示预期/实际与缺口注记。加 CQ = 编辑 `kernel/cq.yaml` 后重启 ontostudio-backend,面板点「重跑」。

### 看 = 规则源码 + 派生明细
1. 「CONSTRUCT 规则」表:每行一条业务规则,派生数=该规则推出的结论数(可点)。
2. 点规则行 → 下方「规则预览 · <规则名>」;右上三切页:
   - 「信息」:派生谓词 / named graph / 派生数;
   - 「源码」:该规则完整 SPARQL CONSTRUCT(rules.yaml / registry 链生成,唯一真相);
   - 「派生」:该规则全部结论,逐条 主体→谓词→客体。

### 追 = 溯源(结论 → 触发事实链)
1. 预览面板切「派生」页,点目标结论行尾「溯源」。
2. 「溯源结果」块:chip「触发事实链完整」= 链路闭合;逐段列出断言图里人工确认过的基础事实
   (如 治理设施 treated_by 治理工艺 → 治理工艺 governed_by 标准)。

### 问 = 反事实(为什么没推出来)
1. 「派生」页顶部虚线框:填期望结论的主体 IRI 与客体 IRI(可从派生列表/图谱浏览复制)→「分析」。
2. 结果三态:「路径存在——应可派生」(只缺全量重算)/「链条断裂」+ 断裂于第 N 段 <谓词>(到达 X)
   / 链首断裂显式提示 owlrl prp-spo2 静默零推断;qualified_bidder 类列出缺的资质 ✗ 清单。

### 比 = 试算对比 + 历史 diff
- 试算(调参预演):右上改门限 → 点「试算」(不落盘)→「试算(未落盘)」条对比 物化/派生合计 vs 落盘;
  满意再「全量重算」,不满意改门限再试。对比条「清除」收起。
- 历史回看:页头「历史」→ 近 20 次落盘记录,「Δ 物化」红绿显示相邻增减,「规则变化」列逐规则 ±。

### 控 = 规则启停
1. 规则表「状态」列:现行(蓝)/停用(黄);行内「停用」→ 派生图**立即清空**,下次重算不再生成。
2. 行内「启用」→ **即时单规则重算**恢复派生(不必全量重算)。
3. 状态持久于内核卷 rules_state.json(容器重启保留);启停同步反映到 CQ 判定与总览治理链计数。

### 溯 = 历史回溯
与「比」的后半共用「历史」面板:按时间线回看每次落盘的门限/规模/规则级变化,回答"这个结论是什么时候开始/停止被推出来的"。

---

## 现状盘点

| 区域 | 现状 | 缺口 |
|---|---|---|
| 推理执行 | ✅ 真数据(owlrl 闭包 + CONSTRUCT 派生,每规则独立 named graph) | 门限不可调、无 dry 试算 |
| 规则表 | ✅ rule_counts 驱动,未知键回退 | 派生数不可下钻、无启用/停用、无源码 |
| 规则预览 | 🟡 选中态已接(qualified_bidder 显硬编码 SPARQL) | 源码应来自规则定义本身;其余规则只有 meta |
| 解释视图 | ❌ 静态 4 步示例(矿井水处理站) | 无真实推导链解释、无反事实 |
| 验收问题 CQ | ❌ 静态 4 条(DemoTag+规划中) | 无 ASK 真算、FAIL 无解释 |
| 历史 | 🟡 仅"上次全量"时间 | 无两次推理间 diff |

## 地基(已就绪,方案直接踩上去)

1. `DeriveRule{name, construct}` —— 源码在 `kernel/rules.yaml` + `BUILTIN_SAMEAS_PROPAGATION` + `builtin_chain_rules(registry)`(registry property_chains 自动生成,段谓词序列已知)
2. **每规则独立 named graph `graph:derived:<name>`** —— 下钻只需查询端点
3. 规则可见域 = asserted ∪ alignment,不读 entailment(层间单向无环)
4. `POST /infer?min_confidence` 后端已支持参数(前端未暴露)
5. `compute_entailment` 清空重写 `graph:entailment` —— dry 只需加 write 分支

---

## 功能方案

### F1 规则源码在线查看(量级 S)

- 后端 `GET /formal/rules` → `[{name, construct, origin: "yaml"|"builtin"|"chain"}]`(聚合 load_rules + BUILTIN + builtin_chain_rules)
- 前端:预览面板 meta 区加「源码」切换(pre 显示 construct);**删除 ReasoningPage 顶部硬编码 SPARQL 常量**(消灭最后一处静态源码)

### F2 派生三元组下钻(量级 S-M,白盒化 L1)

- 后端 `GET /formal/rules/{name}/derivations?limit=200&offset` → `SELECT ?s ?p ?o FROM graph:derived:<name>`
- 前端:规则表「派生数」可点 → 下钻列表(IRI 显规范名,复用 DetailPanel 解析);每条挂「溯源」入口(F3)

### F3 单三元组溯源(量级 M,白盒化 L2)

- 规则定义增加 `trace: [pred1, pred2, ...]`(参与链段谓词,与 rules.yaml 同源维护,规则共 8 条不做反射)
- 后端 `GET /formal/rules/{name}/trace?s=&o=`:按 trace 逐段查 asserted,返回触发路径 `[{s p1 m},{m p2 o},...]`;qualified_bidder 类 NOT EXISTS 规则额外返回"资质全满足清单"
- 前端:溯源面板显示基础事实链,每条可跳实体库详情

### F4 反事实「为什么没推出来」(量级 M-L,白盒化 L3)

- 后端 `GET /formal/explain-miss?p=&s=&o=`:定位 p 的来源规则/属性链 → 按 trace 逐段查存在性 → 第一处断裂即答案
- verdict 枚举:`chain_head_missing`(显式暴露 owlrl prp-spo2 静默零推断坑)/ `middle_missing` / `no_rule` / `disabled`
- 入口:F2 下钻面板「为什么没有更多?」;CQ FAIL 的「解释」按钮

### F5 CQ 验收自动化(量级 M)

- CQ 定义 `cq.yaml`:`{id, question, ask(ASK 查询), expect}`
- 后端 `POST /formal/cq/run`:逐条 ASK → PASS/FAIL;FAIL 自动调 F4 生成解释
- 前端:验收问题面板接真(移除 DemoTag);现有 4 条静态 CQ 转写为种子;FAIL 行展开证据

### F6 dry 试算(量级 S-M)

- 后端 `compute_entailment(write=False)` 分支:内存闭包后统计丢弃,不写 `graph:entailment`;`POST /infer?dry=true`
- 前端:恢复「试算」按钮(这次是真 dry);独立「试算 vs 上次落盘」对比卡;缓存 key `["formal","infer","dry",minConf]` 不污染主缓存

### F7 门限可调(量级 S,纯前端)

- 全量重算旁 min_confidence 输入(0.5–1.0 步 0.05,默认 0.7);缓存 key 改 `["formal","infer",minConf]`,总览订阅 0.7 档保持共享
- 与 F6 组合:调门限先试算看规模再落盘

### F8 规则启用/停用(量级 M)

- 前向约定:rules.yaml 条目加 `enabled`(缺省 true);链规则停用 = registry axiom 加 `enabled: false`(建模器可编)
- 后端载入过滤 + `POST /formal/rules/{name}/enabled`(写 rules.yaml,版本递增);停用时清空对应 derived graph
- 前端:状态列接真(现行/停用),行内切换

### F9 推理历史 diff(量级 M,可延后)

- refresh 后 append JSONL(`{ts, min_conf, entailment, rule_counts, duration}`);前端「上次全量」旁近 N 次对比(±)

---

## 分期

| 期 | 内容 | 特征 |
|---|---|---|
| 一期 | F1 源码 + F2 派生下钻 + F7 门限 | 全读路径,零风险快赢 |
| 二期 | F3 溯源 + F5 CQ 自动化 | 白盒化主体,trace 字段先行 |
| 三期 | F4 反事实 + F6 dry | 解释能力闭环 |
| 四期 | F8 规则开关 + F9 历史 | 治理与运维,按需 |

## 明确不做(本期)

- 可视化规则编辑器(F8 的 enabled 开关已够;CONSTRUCT 在线编写复杂度失控,YAML 直编兜底)
- Rete/增量推理(千级规模全量重算秒级,bug-2188 语境已消失)
- 跨实体"为什么没有 X 关系"自由问答(图谱浏览右键)——F4 的 API 先行,入口远期
