# 投标审查 UI 缺口分析与「完备性核查单」提案

日期:2026-10-30
状态:提案 A(完备性核查单)=用户裁决暂缓;§二 分期建议一期已于 2026-10-30 经
「按分期建议开工」批准并落地(GET /tasks/{id}/baselines + BaselineView 解析质量表/
字段对照卡;冲突裁定/置信度/锚点仍挂二期)
关联:spec 2026-10-30-bid-review-evidence-pipeline-design(证据管线,已落地)、原型 docs/designs/2026-10-30-bid-review-ui.html

---

## 一、背景:E2E 暴露的「字段缺失无法判定」呈现问题

真实 word 文档 E2E(task a2d5da7d)30 条问题里 29 条是 need_human,文案
「字段缺失无法判定:bid.detail_rows, bid.subtotal(on_missing_input=need_human)」。
用户结论:这种卡片说明不了投标文件有啥问题——诚实降级的设计对了,呈现废了。

### 「缺失」背后是三种不同的事(当前不区分)

| 类型 | 含义 | 责任方 | 价值 |
|---|---|---|---|
| ① 投标文件真没写 | 响应缺失 = 废标风险 | 投标方 | **真发现,最高价值** |
| ② 写了但抽取没抓到 | 模型/OCR 能力边界 | 系统 | 误导(不该怪文件) |
| ③ 夹具太薄 | 测试文档 2 页,66 字段 schema 大半本来就没有 | 测试 | 噪音 |

呈现层硬伤:内部字段路径直接外露(`bid.detail_rows`)、引擎内部约定串外露
(`on_missing_input=need_human`)、跨规则同字段重复铺开(bid.entity.license_name
同时出现在 L3-003 与 L1-016)。

### 提案 A:投标响应完备性核查单(本次用户确认先记录,暂缓开工)

1. **聚合**:缺失字段跨规则去重 → 按「主题族」分组(资质类/价格类/工期类/
   承诺函类…),一主题一张卡,替代逐规则 need_human 噪音。
2. **中文标签**:66 条字段路径 → 中文名一次性映射,放规则包 conventions 层;
   问题卡与证据 chips 全部显示中文。
3. **文案**:删内部约定串;每主题卡给指引——「投标文件中未找到『XX』相关内容:
   若招标文件有要求而投标未提供,构成响应缺失(废标风险);若已提供请人工核对
   并反馈」。把①②的判断交给人工,符合 need_human 本意。
4. **明确不做**(v1):区分①②需抽取层加一轮分诊模型调用,挂账;完备性卡指引
   文案已覆盖人工判断路径。

工作量预估:半天(标签映射+聚合在 review 产 issues 后处理或独立汇总端点;
前端一组新卡片)。

---

## 二、原型「解析与字段抽取」(s3/P0-2b)与「招标基准确认」(s4/P0-3)为何未纳入

### 结论先行

**不是不需要——是三层后端依赖缺口导致无法落地,已在 v1 代码里记账。**
两个页面都是原型刻意设计的责任卡点:错误基准 → 全盘误判;s3 让人看见
"机器读了什么",s4 让人对"拿什么当审查依据"签字。

### 缺口分层(按落地时间线)

1. **v1(22 任务批)落地时解析层不存在**:上传即 UTF-8 解码纯文本直存
   (docx/pdf 出乱码退役前的旧实现)——没有页数、没有 OCR、没有解析质量、
   没有资产(图片)。s3 的「解析质量」表(页数/置信度/OCR 兜底提示)无数据可渲染。
2. **基线字段级快照无 HTTP 读端点**:字段只经 MCP `bid_review_baseline_get`
   可达,前端 HTTP 通道缺 `GET /tasks/{id}/baselines`(或同义)。BaselineView.tsx
   头注释明确记录:原型 s4 的字段族列表/字段卡/冲突裁定交互"无处落",本页
   诚实降级为材料卡 + 确认按钮(awaiting_confirm=0%/过门=100% 二值进度)。
3. **冲突裁定是引擎能力缺口,不只是 UI 缺口**:原型 s4 的核心交互(两处表述
   不一致 → 引擎推荐 + 备选 radio → 人工勾选核对 → 裁定生效)依赖引擎的
   "多候选收集 + 冲突态" ——当前抽取是"首个非 null 采纳,不回填"(spec D7),
   根本没有冲突态;锚点注册表(A-PRICE-SHEET 等 27 锚)也未上 wire。

### 证据管线落地后形势变化(2026-10-30 本轮)

| s3 依赖 | 现状 |
|---|---|
| 解析质量(文件/页数/状态) | ✅ engine_meta.docs 清单有 kind/pages/chars/assets/status(pdf 真页码,docx=0 诚实) |
| OCR 兜底提示/低置信页 | ⚠️ OCR 段已入 segments(kind=ocr),置信度未上 wire;低置信页识别未做 |
| 字段抽取对照表(路径/值/形态/状态) | ⚠️ baseline payload 有 fields+provenance(值+出处 quote),但无 HTTP GET;形态(money/bool)在 FIELD_TYPE_CONTRACTS 有,未上 wire |
| 冲突检测/裁定 | ❌ 引擎无多候选机制 |
| 锚点 A-* | ❌ anchors.py 存在,未上 wire |

| s4 依赖 | 现状 |
|---|---|
| 确认门(未确认不得审查) | ✅ 后端已有:deep 停 awaiting_confirm;POST /confirm;409 未复核致命收紧;quick 直跑过门 |
| 字段族/字段卡渲染 | ❌ 同上 GET 缺口 |
| 冲突裁定交互 | ❌ 同上引擎缺口 |
| 逐字段来源「查看原文」 | ✅ 本轮 content/asset 端点 + provenance 已具备(page 定位 pdf 真页码,docx quote 窗口) |

### 判断与分期建议(未裁决,仅记录)

- **s4 基准确认:需要,一期补**。最小闭环 = ①`GET /tasks/{id}/baselines`
  (行级 kind/doc_id/confirmed + payload fields/provenance 中文化投影)+
  ②BaselineView 从材料卡升级为字段卡列表(只读核对 + 全量确认,冲突裁定
  挂账)。无此页,deep 模式的卡点只是后端状态机空转,审阅人对审查依据无感知。
- **s3 解析与字段抽取:需要,分期**。一期先上「解析质量」表(数据已齐)+
  字段对照只读表(依赖同一个 GET);置信度/冲突裁定/锚点二期待引擎演进。
- quick 模式照旧直跑(小文档快速过);deep 模式恢复原型设计的卡点语义。

### 附:相关事实速查

- 后端门:POST /tasks/{id}/confirm(409=存在未复核致命项);stepper 第 4 步。
- MCP 通道:bid_review_baseline_get(字段级快照唯一读路,前端用不了)。
- 本轮新增:GET /tasks/{id}/docs/{doc_id}/content(quote/page 定位)、
  GET /tasks/{id}/docs/{doc_id}/assets/{asset_id}(原图)。
- E2E 基线实测:66 字段/侧,agnes-2.5-Flash ~30s;薄文档→大半字段诚实 null。
