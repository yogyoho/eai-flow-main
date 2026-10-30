# 投标审查二期设计:冲突裁定 / 置信度 / 锚点 + 复核工作台

日期:2026-10-30
状态:已批准(用户「继续」,按建议范围执行)
关联:spec 2026-10-30-bid-review-ui-gaps-and-completeness.md(§二 分期建议)、
2026-10-30-bid-review-evidence-pipeline-design.md(证据管线,已落地)、
原型 docs/designs/2026-10-30-bid-review-ui.html
前置:一期(GET /tasks/{id}/baselines + BaselineView 解析质量表/字段对照卡)已落地 c34dc2306

---

## 〇、范围裁决记录

**二期纳入**:
1. 冲突裁定(引擎多候选 + 裁定端点 + 确认门收紧 + s4 裁定卡)——核心
2. 置信度(抽取自报 + 服务端 quote 核验 + 字段卡置信 pill)
3. 锚点 A-*(engine/anchors.py 注册表 + det 规则 issue 证据补全)
4. s6 人工复核工作台队列视图(纯前端组装,写通道已全通)
5. 提案 A 部分:字段中文名映射(66 路径→中文,裁定 UI 前置)+ 完备性聚合卡
6. UX 补:工作台页头常驻「基准确认」入口(过门后黄条消失即无入口的缺口)

**挂账三期**(本次明确不做):
- s7 响应偏离表(新页面+后端投影端点,与引擎演进零依赖)
- s8 版本差异(prev_task_id 列已预留;等多版本复审场景真实出现)
- OCR 页级置信度(eai-flow-ocr 现契约只回 text;等 OCR 服务加字段再接)
- 提案 A 的「区分①②分诊模型调用」(原文已挂账,维持)

---

## 一、冲突裁定

### 1.1 抽取层:多候选收集

现状:抽取是「首个非 null 采纳,不回填」(spec D7),没有冲突态。

改动(`engine/extract.py` + `worker.py`):

- `build_extract_prompt` 输出契约扩展:

  ```json
  {"fields": {路径: 值},
   "provenance": {路径: {doc_id, page, quote}},
   "candidates": {路径: [{value, doc_id, page, quote}]},
   "confidence": {路径: 0~1}}
  ```

  - `candidates`:材料中观察到的**全部**非 null 取值(含被采纳值);单值字段也是
    单元素候选。prompt 指示:同一字段在多处出现**不同值**时逐条列出,禁止自行
    裁决取其一。
  - `confidence`:模型对每字段的自报置信 0~1(可选输出;缺省不造假)。
  - 向后兼容:`candidates`/`confidence` 缺失 → 视为无候选/无置信,既有 fake
    测试与 legacy 扁平形态不断。
- `normalize_candidates(raw, field_paths, doc_ids, role_map)`:
  仅接受已知路径 + 已知 doc_id(role_map 别名同 provenance);value 走与
  normalize_fields 同样的 JSON 安全类型闸;entry 非法整条丢弃;quote 截 120 字;
  每路径候选数上限 8(防幻觉刷屏,超出截断)。
- 分片合并(`_default_extract_fn`):fields/provenance 沿用现有合并;
  candidates 按路径 append;confidence 后写覆盖。
- **冲突判定** `detect_conflicts(candidates) -> dict[path, list[normalized_value]]`:
  候选值归一后(str 去空白折叠;数值;bool;list/dict JSON 串化)去重,
  ≥2 个不同归一值 → 冲突。纯函数,GET 投影与测试共用。

### 1.2 存储

- baseline payload 增加 `candidates`(全局快照,与 provenance 同构——行是每文档
  重复行,payload 内容相同)。
- **裁定结果存 `task.engine_meta.adjudications`**:
  `{path: {"value": ..., "at": iso, "note"?: str}}`——不建新表:裁定是任务级
  少量状态,且必须与 resume 链(engine_meta 已在 task 行上)同生命周期。

### 1.3 API

- `GET /tasks/{id}/baselines` 投影扩展(行内):
  - `candidates`: {path: [entry...]}
  - `fields_conf`: {path: {"conf": float|null, "verified": bool}}
  - `conflicts`: [path...](detect_conflicts 结果)
  - `adjudications`: {path: {value, at, note?}}(engine_meta 透传)
  - `effective_fields`: fields ∪ adjudications 覆盖后的值(前端直用)
  - `labels`: {path: 中文名}(全行一份,engine/labels.py)
- `POST /tasks/{id}/baselines/adjudicate` body `{path, value, note?}`:
  - 409 除非 status == awaiting_confirm(过门后裁定 = 改审查依据,拒绝);
  - 422 path 不在 baseline fields / value 类型非法(JSON 安全类型闸);
  - 写 engine_meta.adjudications,返回更新投影(与 GET 同构)。
- **确认门收紧** `POST /tasks/{id}/confirm`:存在「冲突且未裁定」路径 → 409,
  detail 带 `unresolved_conflicts` 计数(与既有 409 未复核致命同语义层)。

### 1.4 恢复链(关键接缝)

`worker.resume_confirmed`(worker.py ~449):从首行 baseline 重载 fields 后、
`_run_review_stage` 前,合并 `engine_meta.adjudications`
(`fields[p] = adj["value"]`)。审查引擎对裁定无感知——裁定就是改字段快照。

### 1.5 前端(s4 裁定卡)

BaselineView 字段卡升级:

- 冲突字段卡(路径命中 conflicts):显示引擎推荐值(现 fields 值)+ 全部候选
  radio(各带 doc_id·p.N + quote 摘要 + 「查看原文」),选定后「采纳为基准值」
  → adjudicate;已裁定卡转「已裁定」pill + 裁定值 + 撤销?**不做撤销**
  (YAGNI:裁定前可改选,过门后整体 409,无需撤销路径)。
- 确认门按钮计数 = 未确认行数 + 未裁定冲突数;后端 409 时前端展示 detail。
- 字段卡全部改显中文 label(path 降为 mono 小字)。
- 置信 pill:高(conf≥0.8 且 verified)/ 低(conf<0.8)/ 未核验(!verified),
  低置信卡加「建议人工核对」提示。

## 二、置信度

- 抽取自报:见 1.1 confidence;归一层夹 [0,1],非数值 → null(不造假)。
- **服务端 quote 核验(真信号)**:`verify_quotes(fields_conf 生成期)` —— 对每条
  provenance,取对应 doc 的 segments(parse 层已有),quote 空白折叠后子串命中
  → `verified: true`;不命中 → `verified: false`(与 DocLocateModal 高亮、
  content 端点定位同口径)。核验在 build_baseline 写 payload 前执行一次,
  结果入 `fields_conf`。模型自报分数只是先验,核验才是硬信号。
- 上 wire 见 1.3 `fields_conf`;OCR 页级置信度挂账(见范围裁决)。

## 三、锚点 A-*

侦察结论:ui-gaps 文档「anchors.py 存在,未上 wire」**有误**——该文件从未存在。
实际:规则包 1.0.0.yaml 全部 det 规则都写了 `evidence: [A-PRICE-SHEET, ...]`
等锚点名(去重后 16 个),引擎完全不解析;routers.py:490 的回退注释
(det 规则 issue 无 doc/page 证据)即此缺口的现行账。

- 新建 `engine/anchors.py`:
  - `ANCHOR_REGISTRY: {anchor_id: {"label": 中文, "paths": [字段路径...]}}`
    ——锚点↔字段路径映射从规则包 inputs 对照转录,与 FIELD_DICTIONARY 同源
    惯例(改动三处同步:规则包 evidence / 本表 / labels)。
  - `resolve_rule_evidence(evidence_ids, fields_provenance, fields_conf) ->
    [issue 证据条目]`:锚点 → paths → provenance 中的 doc_id/page/quote,
    组装 issue 证据 chips(复用现有 issue.evidence 结构)。
- `rule_runner.py`:det 规则产出 issue 时调用 resolve_rule_evidence,
  证据非空则写入 issue;空则维持现回退(判定输入字段展示)。
- 不做锚点可视化编辑器(YAGNI;注册表静态字典即可,后随规则包版本演进)。

## 四、字段中文名映射(提案 A 并入部分)

- 新建 `engine/labels.py`:`FIELD_LABELS: {path: 中文名}`(66 路径全覆盖,
  以 FIELD_DICTIONARY + 规则包 inputs 为准,缺路径回退原路径名)。
- 上 wire:baselines GET `labels`;前端字段卡/完备性卡/need_human 卡统一消费。
- 完备性聚合卡(WorkbenchView):need_human issues 的输入字段跨规则去重 →
  按族(tender/bid 已有 familyOf)聚合 → 每族一张「响应完备性」卡:缺失字段
  中文名清单 + 指引文案(提案 A ③,一期 BaselineView 已有同款文案,复用)。

## 五、s6 人工复核工作台(队列视图)

- 新页 `/bid-review/review?task_id={id}`(导航「复核工作台」,group 0 第 4 项)。
- 布局:左 = 原文定位(DocLocateModal 内容面复用,内嵌面板化——抽
  `DocLocateBody` 共享组件,modal 与队列左栏同用);右 = 待复核队列
  (need_human issues,跳过/上一条/下一条)。
- 每条:规则号+严重度 pill → 结论 → 差异值 → 证据 chips(定位)→ 判定 radio
  (确认问题/误报/严重度调整[档位 select]+备注 note)→「提交并下一条」
  (feedbackIssue 既有四动作,写通道零后端改动)。
- 键盘快捷键:J/K 切换、Y 确认、N 误报(input focus 时禁用)。
- 复核进度:N/M 已复核(verdict != need_human 计数)。

## 六、UX 补

- WorkbenchView 页头 ph-actions 常驻次级按钮「基准确认」(Link 到
  /bid-review/baseline?task_id=);原未确认黄条保留(语义更强)。

## 七、交付顺序与测试

1. 后端引擎:labels.py / anchors.py / extract 多候选+confidence+quote 核验 /
   detect_conflicts(fake 单测先行)
2. worker:分片合并 / resume 合并裁定
3. routers:baselines 投影扩展 / adjudicate / confirm 门 409(pytest:
   裁定 409/422 矩阵、门计数、resume 合并、锚点证据、归一边界)
4. 前端:api.ts + BaselineView 裁定卡/置信 pill/中文 label → WorkbenchView
   常驻入口+聚合卡 → ReviewQueueView(dom 测试:裁定交互/门计数/队列提交)
5. 容器验证:restart gateway,真实任务回归(a2d5da7d 只读投影不回归;
   新任务 deep 模式走裁定链)

EAI-CUSTOM 注释规范:全部新增/改动按仓规携带日期与本 spec 指引。
