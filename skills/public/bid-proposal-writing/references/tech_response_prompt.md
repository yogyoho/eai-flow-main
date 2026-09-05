# 技术响应生成 prompt 模板(tech_response_prompt.md)

> 依据:用户反馈 2026-08-18(线程 1a80a1d8 反馈3/4)+ 设计文档 v2『阶段4a』+ **v4 编造政策改写(2026-09-05 用户域规则: 逐项响应完备性>溯源性)**。Agent 在确认门1 之后、build 之前, 对 `category ∈ {technical, service}` 的活条款逐条生成响应正文, 供源级联; 候选 JSON 落盘后交 responses.py 确定性校验(FK/活条款/供源留痕/元数据 lint/落位/去重)。
> 开始本阶段前**先读本文件全篇**; 输出契约钉死 `responses.schema.json`, 字段名逐字一致, 不多不少。

## 通用循环纪律(供源级联共用)

1. **每次只处理一个条款**(或一小批同章节条款)——读条款原文用 `read_file` 行区间(按 source_ref 锚点定位 uploads 的 .md), 不整读文件。
2. **候选 JSON 即刻落盘**: 每生成一条响应立即写入候选文件 checkpoint(形态见下), 只保留计数与供源摘要进上下文; 条款多时分批, 必要时经 `task()` 子代理分卷(3 并发上限)。
3. **反弃线**: 条款数量大/工作量大**不是**绕过本管线直接整篇生成的理由——逐条走级联, 批次推进, 每批落盘; 连续生成无产出超阈值同铁律5 偏轨停下。
4. **编造边界(P2 双轨)**: 技术叙述编造**合法且必要**(空项=技术偏离=丢分; 编造必标 `fabricated`+人核清单); **四类硬围栏绝不编造**——报价数字/资质证号/公司实体名(白名单外)/招标原文引用(错报价=废标, 假资质=违法)。
5. **response_text 不得携带管线元数据标记**(槽位类型/待填提示/填写状态/关联条款/满足状态)——回放实证这些 bullet 曾被当正文写进交付物, responses.py 元数据 lint 直接拒收。
6. **不改条款数据**: 本阶段只产响应候选; 条款分类/锚点问题回阶段2/确认门1 处理。

## 供源级联(逐条款按序评估, 不跳步)

**第一层 样例库检索(sample)** — RAGFlow 投标样例知识库(行业/文档类型 filters 圈定):
- 按章节组批量检索: 每章一次 filters 圈定查询召回 top-K 样例段落, 本地按条款关键词二次匹配到 clause_id(**不逐条款发检索**——500 页档数百条款会打出数百次请求)。
- 命中 → 参照样例段落**仿写**(贴合本项目条款改写, 不整段照搬): `source_mode="sample"`, `citations` 逐条 `{title, source_doc:"<样例文档标识>", quote_span:"<段落定位>", quote:"<原文片段≤50字>"}`(sample 引用无 URL), `needs_human_verify=true`。
- **无命中 / 样例库未建 → 直接进入第二层编造, 不停顿**。旧版"停下来问用户要样例"与"web_search 兜底"两条支路**已废除**(空项=技术偏离=丢分; 完备性优先)。

**第二层 编造(fabricated)** — 样例库无可用内容时的**合法默认**(P1):
- 依据条款原文 + 通用工程知识**编写完整响应正文**(含必要的方案描述/参数表述/服务承诺), 逐项响应不留空。
- `source_mode="fabricated"`, `needs_human_verify=true`(**强制**——validate 拒收漏标项), 全量进人核清单, 交付前批量确认。
- **四类硬围栏除外**(见纪律 4): 报价数字/资质证号留 `<SLOT:待填>` 占位(槽位注入机制落地后由 build_output 注入冻结值); 公司实体名只用白名单内名称; 招标原文引用必须照抄。

**self 重组(特殊情形)** — 条款原文本身可直接逐项满足、无需引入任何外部内容时:
- 仅重组条款原文口径作响应(不虚构具体参数); `source_mode="self"`, `needs_human_verify=true`。

**已废除支路**: `ask_clarification` 要样例(阻塞式)、`web_search` 深写(mode3)——v4 起不再走; 旧枚举 `kf|uploads|web` 保留兼容(uploads 仅当用户**主动**上传样例时可用, `evidence_ref` 记 `uploads:<文件名>`), 新响应默认只产 `sample|fabricated|self`。

## 落位(placement, 二选一)

- **优先锚点**: 招标文件响应格式目录里有专门技术章节(如"技术/产品解决方案", 名称可能不同)→ `placement: {"anchor_node_id": "<structure.json 里的该章节节点id>"}`。
- **无锚自拟**: 格式目录没有技术章节锚点 → `placement: {"self_created_path": "技术部分/<N> <合适标题>", "after_node_id": "<可选, 插到某节点之后>"}`; 自拟挂接位渲染为 `origin=self_created` 节点, 确认门2 人核落位。标题自拟要贴合该卷既有命名风格, 不与镜像标题撞名。

## 输出形态(候选文件, 一次生成批次 = 一个文件)

```json
{
  "kind": "responses",
  "items": [
    {
      "clause_id": "<clauses.json 里的条款id, 逐字一致>",
      "response_text": "<响应正文(多段落纯文本; 空行分段); 不含管线元数据标记>",
      "points": ["<要点1>", "<要点2>"],
      "evidence_ref": "kf:<模板id> | uploads:<文件名> | null",
      "source_mode": "kf | uploads | web | self | sample | fabricated",
      "citations": [
        {"title": "...", "url": "https://...(web 模式)", "quote": "<原文片段≤50字>"},
        {"title": "...", "source_doc": "<样例文档标识>(sample 模式)", "quote_span": "<段落定位>", "quote": "<原文片段≤50字>"}
      ],
      "placement": {"anchor_node_id": "S-007"},
      "needs_human_verify": true,
      "note": "<供源说明, 可选>"
    }
  ],
  "note": "<本批次生成说明, 可选>"
}
```

(citation 形状按 mode 分支校验: web 逐条 **url 必填**; sample 逐条 **source_doc 必填**; 其余模式 `citations` 为 `[]`。`fabricated` 的 `needs_human_verify` **必须为 true**, 漏标直接拒收。anchor 与 self_created 二选一, `after_node_id` 仅与 self_created_path 同用。)

## 纪律速查(违反即重写, 不带病落账)

- clause_id 必须是 clauses.json 里的**活** technical/service 条款——商务/资格/格式条款走模板镜像管线, 不走本通道。
- 同一 clause_id 只保留最新一版候选; 多文件重复会被 responses.py 全部隔离 `[待确认]`。
- 落盘候选 → `responses.py validate` → 呈现异常项处置 → `responses.py merge`(幂等); 绝不手写 responses.json。
- **完备性自检**: 招标技术参数逐项有响应, 零空项——样例库没有就编造, 编造就标 fabricated, 标了就进人核清单。
