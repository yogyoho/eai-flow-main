# 投标审查 s7 响应偏离表 + s8 版本差异整屏 设计(裁决9 翻案)

- 日期:2026-11-01
- 状态:APPROVED(用户 2026-11-01 令「两个都做按照原型来实现」;偏离数据源=抽取期 LLM 对照,AskUserQuestion 确认)
- 前置:`2026-10-31-bid-review-ux-redesign-design.md`(§2 将 s7/s8 整屏维持挂账——本设计翻案)、原型 `docs/designs/2026-10-30-bid-review-ui.html` s7/s8 两屏
- 基线:main-dev-fork @ 66f5f9717

## 0. 翻案范围

原裁决9 排除的 s7/s8 **整屏**纳入实施;原型两屏逐元素对齐。其余排除项(规则启停/评测 runner/PDF 导出)**维持不变**。

## 1. B9 响应偏离表(新页 `/bid-review/deviations`)

### 1.1 数据契约(抽取期 LLM 对照,B4 同构,零新表)

- `FIELD_DICTIONARY` += `deviation.items`;`FIELD_TYPE_CONTRACTS` 给逐条对照契约:
  `[{"item":"条目名","tender_req":"招标要求原文或null","bid_response":"投标响应原文或null","kind":"match|positive|negative|missing|extra","severity":"fatal|major|minor|null","evidence":{"role":"tender|bid","quote":"原文摘录","page":页码或null}}] 数组;逐条列出招标要求与投标响应对照(一致项也列,kind=match);missing=招标有而投标未响应(漏项,severity=fatal);extra=投标自行增报招标清单外(severity=major);negative=负偏离(劣于要求,severity=主要major/次要minor);positive=正偏离(优于要求);tender_req/bid_response/evidence.quote 只抄材料原文,禁止编造;没有可比对条目时给空数组。`
- `labels.py`: `"deviation.items": "响应偏离表"`。
- 判定语义:kind 五值即原型五色 pill(`match`一致/`positive`正偏离·优/`negative`负偏离·主要或次要/`missing`漏项·致命/`extra`擅自增项·主要)。

### 1.2 端点 `GET /tasks/{id}/deviations`

```python
{"counts": {"tender_items": N, "bid_items": N, "negative": N, "missing": N, "extra": N},
 "items": [ <上方 item 结构原样> ]}
```

- 数据源=基线行 `payload.fields["deviation.items"]`,**按 item 名跨行去重**(B4 手法:每行同全量快照)。
- counts 服务端算(单一事实源):`tender_items` = kind≠extra 计数;`bid_items` = kind≠missing 计数;其余按 kind 直计。
- 旧任务/未抽出 → 零投影 `{"counts": 全 0, "items": []}`(诚实,不装数据)。
- 404 幽灵任务;owner 隔离同既有端点。

### 1.3 前端(原型 s7 逐元素)

- 页头:任务 chip(TaskTitleTag)+ 副标「依据基准确认包与投标文件自动生成」+ `missing>0` 时红 stage-chip「N 项致命偏离(漏项)」+ 「导出偏离表」(客户端 CSV,含 BOM 防 Excel 乱码)。
- metric-strip 5 格:招标条目 / 投标响应条目 / 负偏离(err) / 未响应(err) / 擅自增项。
- 明细表 6 列:# / 条目 / 招标要求 / 投标响应 / 偏离判定(pill 五色映射) / 证据(src-chip,点击开 `DocLocateModal`,与问题证据同交互)。
- 默认只显非 match 行,「显示一致项」toggle 全量(原型表=仅偏离行)。
- tbl-foot:致命漏项整改注 + L1-013 规则组引注。
- 空态:零投影 → 引导文案(「本任务抽取时未包含偏离维度」);加载/错误三态随页规约。

### 1.4 导航与权限

- 侧栏「审查闭环」组追加第 6 项「响应偏离表」(人工复核之后),`taskPage` 挂 results 域携带 task_id。
- 权限:**挂 `bid:page:results`**(先例=review/metrics 挂宿主页,零新 page id、零 yaml 变更)。

## 2. B10 版本差异(新页 `/bid-review/diff?task_id=&prev=`)

### 2.1 端点扩展 `GET /tasks/{id}/diff`(响应加两键,既有三键原样=向后兼容)

- `fields: [{path, label, prev, cur}]` —— 两版基线 `payload.fields` 逐路径机械对比,值不同才列(JSON-safe 比较);label 取 `FIELD_LABELS`。
- `rules: [{rule_id, prev: {present, severity}, cur: {present, severity}}]` —— 两版问题按 rule_id 归并;`present` = 存在 verdict≠false_positive 的问题;severity=其中最严(fatal<major<minor<info);rule_id 并集,有变化者排前。
- 数据源:`crud.list_baselines` 首行 fields 快照(每任务) + `crud.list_issues`。

### 2.2 前端(原型 s8 逐元素)

- 页头:「v 旧(biz_no) → v 新(biz_no)」+ 副标「变更影响 N 项问题中的 M 项」(N=并集问题数,M=added+removed)。
- split-wide 双卡:
  - 「关键内容差异」:fields 列表,`dif-del`(− 旧值)/`dif-add`(+ 新值) 盒;空态「两版基线字段无差异」。
  - 「规则影响」:四列表(规则 / 旧判定 / 新判定 / 变化),pill 映射 violation(pass 缺省不列行,只列曾命中规则)。
- 无 prev 参数 → 引导空态(从 /results 版本对比卡或任务链进入必带)。
- /results 既有 B7 轻量卡**保留不动**(本页是其整屏化,入口互跳:卡片加「查看整屏」链接)。
- 导航:「审查闭环」组第 7 项「版本差异」,挂 `bid:page:results`。

### 2.3 版本链入口(补 prev_task_id 断环)

- `create_task` 增可选 `prev_task_id` Form 字段:空串→None;非空须存在+属主(404「基准任务不存在」)+≠自身(422);先校验后建任务(防孤儿)。
- TasksView 创建对话框加可选「对比基准任务」下拉(done 任务列表,排除自身场景);提交随 FormData。
- /results 页头加「换版重审」按钮 → 跳 `/bid-review?prev=<task_id>`(TasksView 读 `?prev=` 自动开对话框并预填基准)。

## 3. 测试与验收

- 后端 pytest:deviations 端点(投影+去重+counts / 零投影 / 404)、create_task prev 校验(404/422/写入)、diff 扩展(fields 变更对/无变更空/rules 归并严重度/误报剔除)。
- 前端 rstest dom:DeviationsView(pill 映射/计数/过滤 toggle/零投影空态)、DiffView(双卡渲染/无 prev 空态)、TasksView(prev 下拉提交 + ?prev= 预填开框)、layout 导航契约回归门更新。
- 全程 TDD 先红后绿;每任务一 commit 推送。

## 4. 本设计明确不做

- 增量审查/`inherit_from_review`(原型 s8 foot 注的引擎语义——引擎重写,另立项)。
- 多级版本 seg 切换(s8 头部的 v1→v2/v2→v3 切换器——单跳 prev 已够,多级链走 /results 卡逐跳)。
- 偏离表打印视图/PDF(CSV 导出即够);偏离判定人工复核落库(复核闭环现有 issues 面,偏离表只读)。
