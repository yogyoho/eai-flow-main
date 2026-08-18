# 技术响应生成 prompt 模板(tech_response_prompt.md)

> 依据:用户反馈 2026-08-18(线程 1a80a1d8 反馈3/4)+ 设计文档 v2『阶段4a』。Agent 在确认门1 之后、build 之前, 对 `category ∈ {technical, service}` 的活条款逐条生成响应正文, 三模式供源; 候选 JSON 落盘后交 responses.py 确定性校验(FK/活条款/供源留痕/元数据 lint/落位/去重)。
> 开始本阶段前**先读本文件全篇**; 输出契约钉死 `responses.schema.json`, 字段名逐字一致, 不多不少。

## 通用循环纪律(三模式共用)

1. **每次只处理一个条款**(或一小批同章节条款)——读条款原文用 `read_file` 行区间(按 source_ref 锚点定位 uploads 的 .md), 不整读文件。
2. **候选 JSON 即刻落盘**: 每生成一条响应立即写入候选文件 checkpoint(形态见下), 只保留计数与供源摘要进上下文; 条款多时分批, 必要时经 `task()` 子代理分卷(3 并发上限)。
3. **反弃线**: 条款数量大/工作量大**不是**绕过本管线直接整篇生成的理由——逐条走决策树, 批次推进, 每批落盘; 连续生成无产出超阈值同铁律5 偏轨停下。
4. **绝不编造**: 无出处的参数值/型号/承诺一律不写; 拿不准的内容降级为要点 + `[待确认]`, 由确认门2 人核。
5. **response_text 不得携带管线元数据标记**(槽位类型/待填提示/填写状态/关联条款/满足状态)——回放实证这些 bullet 曾被当正文写进交付物, responses.py 元数据 lint 直接拒收。
6. **不改条款数据**: 本阶段只产响应候选; 条款分类/锚点问题回阶段2/确认门1 处理。

## 三模式决策树(逐条款按序评估, 不跳步)

**mode1 知识库(kf)** — 每轮先探测一次 knowledge-factory MCP:
- 调 `knowledge-factory_kf_query_templates` 检索与条款相关的模板(必要时 `kf_resolve_template` 取全文); 语料是环评/水保/消防类, 投标类价值未验证——**探测一次, 空手或低置信如实降级到 mode2**, 不虚设此源。
- 命中可用内容 → 结合条款技术参数**扩写/润色/仿写**: `source_mode="kf"`, `evidence_ref` 记 `kf:<模板id或标题>`; 模板文字只作行文参照, 参数值必须来自条款与本项目事实。

**mode2 参考样例(uploads)** — 知识库无高置信内容:
- 调 `ask_clarification`(missing_info)**停下来**请用户上传参考样例(旧标书/同类技术方案/产品白皮书); 明确说明: 上传后将继续, 不上传则转网络搜索。
- 用户上传后(下一轮 `<current_uploads>` 可见): `grep`/`read_file` 行区间读样例, 引用其段落**仿写**; `source_mode="uploads"`, `evidence_ref` 记 `uploads:<文件名>`; 样例中的数值/型号未经本项目核实不得照抄为承诺——照抄处标 `[待确认]`。

**mode3 网络搜索(web)** — 用户明确无样例可传:
- `web_search` 检索 + `web_fetch` 取正文, **深度撰写**(仅客观技术信息: 标准/参数/架构说明; 不引述无法核实的商业宣传); `source_mode="web"`, `citations` 逐条 `{title,url,quote}`(quote 照抄原文片段 ≤50 字), `needs_human_verify=true` 强制。
- **无引用的网搜深写不可信**: citations 为空的 web 候选会被 responses.py 直接拒收——宁可降级 self, 不落空引用的 web。

**self 自拟兜底** — 三模式均无可用外部内容, 或用户选择跳过:
- 仅依据条款原文 + 通用工程知识自拟响应框架(方案结构/响应口径, 不虚构具体参数); `source_mode="self"`, `needs_human_verify=true`。

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
      "source_mode": "kf | uploads | web | self",
      "citations": [{"title": "...", "url": "...", "quote": "<原文片段≤50字>"}],
      "placement": {"anchor_node_id": "S-007"},
      "needs_human_verify": false,
      "note": "<供源说明, 可选>"
    }
  ],
  "note": "<本批次生成说明, 可选>"
}
```

(web 以外的模式 `citations` 为 `[]`; anchor 与 self_created 二选一, `after_node_id` 仅与 self_created_path 同用。)

## 纪律速查(违反即重写, 不带病落账)

- clause_id 必须是 clauses.json 里的**活** technical/service 条款——商务/资格/格式条款走模板镜像管线, 不走本通道。
- 同一 clause_id 只保留最新一版候选; 多文件重复会被 responses.py 全部隔离 `[待确认]`。
- 落盘候选 → `responses.py validate` → 呈现异常项处置 → `responses.py merge`(幂等); 绝不手写 responses.json。
