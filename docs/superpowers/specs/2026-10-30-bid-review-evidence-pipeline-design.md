# 投标审查证据管线 + 原型操作 设计(spec)

日期:2026-10-30
状态:APPROVED(设计对话收敛,待实施)
上游需求:审查工作台问题卡按原型补齐证据信息与操作;涉及审查管线修改,先设计后实施。
原型:docs/designs/2026-10-30-bid-review-ui.html s5(证据 chips + 定位原文 + 维持违规/误报/待人工)

## 0. 背景:三堵墙(已查实)

1. **docx/pdf 根本没有被解析**:`routers.create_task` 把上传字节按 UTF-8 硬解码(`decode("utf-8","replace")`)。.docx 是 ZIP 二进制 → 乱码;真实"字段缺失无法判定" need_human 于此。实际只有 .txt/.md 可用。
2. **det 规则 issue 证据恒空**:`rule_runner._issue/_need_human` 硬编码 `"evidence": []`;规则包 per-rule `evidence:[A-*]` 锚点代号加载了但从未使用(anchors.py 未落地)。sem/hyb(LLM 路径)证据正常。
3. **反馈动作缺"待人工"**:FeedbackIn 仅 confirm/false_positive/severity_change;confirm 不清 need_human(复核闭环断)。

## 1. 设计裁决记录(对话定案)

| # | 裁决 | 理由 |
|---|---|---|
| D1 | 解析层:docx→python-docx(段落/表格/图片流),pdf→PyMuPDF 逐页 | 解乱码 KB 级依赖;PDF 真页码白拿。不引 LibreOffice 进 gateway |
| D2 | LibreOffice sidecar 为触发式后备 | 触发条件:①docx 真页码成硬需求 ②OCR+文本定位的预览保真走查不达标。独立容器,上传时 HTTP 调用 |
| D3 | OCR 伴随系统设置默认选择,双引擎 | 见 §3;rapidocr(内建 eai-flow-ocr)与 paddleocr-vl-1.6(openai-vision 注册表外接)都支持 |
| D4 | 图片内容必须进管线(盖章/证照扫描) | docx 内嵌图枚举 + PDF 空文本层页渲染位图 → OCR → 文本插回 + 原图落盘 |
| D5 | 大文件分片抽取 | 真实投标几百页≈几十万 token,全文单 prompt 必爆。按页/片段分片抽,合并归一,冲突不覆盖非空值;单片失败落 null 走 need_human |
| D6 | **溯源只显相关页,不整本** | 前端弹层只渲染命中页(翻页再取);engine_meta.docs 瘦身为材料清单,**全文不上 wire**,新增按页/按片段取数端点 |
| D7 | det 证据=抽取溯源,不用 A-* 锚点 | provenance {doc_id, page, quote} 挂到 rule.inputs;run_det_rule 判定零改动(attach 后置挂接),dedup_key 用 message 前 40 字不受影响,materials_hash 仍只算 fields(det 零漂移门不破) |
| D8 | docx 页码诚实降级 | 无 LibreOffice 前 docx 无页:chip 显文档名(无 p.N),定位按 quote 片段窗口(±N 段);PDF chip 显真 p.N |
| D9 | need_human action + confirm 清标 | FeedbackIn 增 `need_human`(落库 need_human=True, verdict="need_human",不进 stats);confirm/false_positive 清 need_human(复核闭环) |
| D10 | 前端定位弹层 | 命中页文本窗口渲染 + 图片资产按需加载(盖章核对);未定位显"未定位到原文"诚实降级 |

## 2. 架构

```
上传(multipart)
 → 解析层(新 parse.py):
     docx → python-docx:段落/表格文本(按流)+ 内嵌图片枚举
     pdf  → PyMuPDF:逐页文本;文本层为空的页 → 渲染位图送 OCR
     图片 → OCR(§3 引擎选择)→ 文本按流位置插回(标 [图片OCR] 块)+ 原图落盘任务材料目录
     产出: docs 清单(瘦)+ pages 正文 + assets 清单
 → 抽取(extract.py v2):
     分片 prompt(每片带 doc/页标记)→ 字段值 + provenance{doc_id, page, quote}
     归一:只收已知路径;provenance 缺失 → 空(det 证据降级为依据字段 chips)
     materials_hash 仍只算 fields
 → 规则:run_det_rule 零改动;attach_evidence(issues, rule, provenance) 后置挂接
 → 持久化:issue.evidence = [{doc_id, page, section_path, text}] (page 可空)
 → 前端工作台:
     真证据 chips(文档名 + 有页显 p.N)+ quote 摘录
     定位原文 → 弹层:GET 按页取数,只渲染命中页窗口;图片资产按需
     iss-acts:维持违规/误报/待人工(need_human 项隐藏待人工)
```

## 3. OCR 双引擎(伴随系统设置)

现状(查实):
- 系统设置页 `basic-settings.tsx` → `/api/extensions/settings/ocr/services`(GET 掩码回显 / PUT super-admin)已维护 OCR 服务注册表,条目 `{name, base_url, api_key, model}`,openai-vision 协议(PaddleOCR-VL-1.6 走此)
- rapidocr 内建 = eai-flow-ocr 独立容器(rapid-layout+rapid-table+rapidocr),HTTP POST 文件回表格 JSON(cpa document_parser 同源接口)
- cpa `_resolve_ocr_args`:override > cpa config ocr_provider > builtin;失效回退内建+warning

补齐:
1. `SystemConfig` 增 `default_ocr_engine` 字段(`builtin` | 注册表服务名);basic-settings OCR 卡片加默认下拉(选项=builtin+注册表名)。走通用 PUT /config(掩码只涉 api_key,普通字段无碍)
2. 注册表解析逻辑抽公共 helper(新建 `app/extensions/ocr/resolve.py`:名字→条目校验→失效回退),cpa 改调公共版**行为逐字节不变**,bid-review 复用
3. bid-review 解析层双路径:
   - `builtin` → eai-flow-ocr HTTP(确认项:是否已有整页文本端点;无则该服务加只读端点)
   - 注册表名 → openai-vision 客户端(图片 data url → 文本),与 cpa 外接同协议
4. 失效一律回退 builtin + warning(cpa"默认零变化+失败隔离"同哲学)

## 4. 契约

### 4.1 解析产物(engine_meta 瘦身,D6)

```jsonc
// engine_meta.docs(清单,全文不上 wire):
[{ "doc_id": "bid.docx", "role": "bid", "kind": "docx|pdf|text",
   "pages": 37, "chars": 182000, "assets": 4 }]
// 正文按页存储:任务材料目录 pages/{doc_id}/{n}.txt(或 assets.json 索引)
// 目录钉死:{storage_path}/bid_review/{task_id}/ = …/users/{owner_id}/bid_review/{task_id}/
//   (pages/ 正文、assets/ 原图,上传时解析层一次性写出;worker/取数端点按此读)
// 取数端点(新增):
GET /tasks/{id}/docs/{doc_id}/content?quote=&page=1
  → { "doc_id", "kind", "page": 12, "total_pages", "window": [{page, text}], "assets": [asset_id] }
  // pdf: window=命中页(±0),翻页 ?page=n 再取;docx/text: quote 片段窗口(±10 段)
GET /tasks/{id}/docs/{doc_id}/assets/{asset_id}  → 原图(FileResponse)
```

### 4.2 抽取 provenance(extract.py v2)

```jsonc
// prompt 输出(分片,每片只含其页范围):
{ "<字段路径>": <值>, ..., "provenance": { "<字段路径>": { "doc_id": "...", "page": 12, "quote": "逐字摘录≤120字" } } }
// normalize_provenance:只留已知路径、doc_id 非空、quote 字符串;缺失→{}
// BaselinePackage.payload 增 "provenance" 键(向后兼容:旧 baseline 无键=空)
```

### 4.3 det 证据挂接(rule_runner.py)

```python
def attach_evidence(issues: list[dict], rule: Rule, provenance: dict) -> list[dict]:
    # evidence = [{doc_id, page, section_path: 字段路径, text: quote}
    #             for path in rule.inputs if path in provenance]
    # 无 provenance 覆盖的 rule(旧任务/降级)→ evidence 保持 [],前端回落依据字段 chips(已上线)
```

### 4.4 反馈动作(routers.py + schemas.py)

- FeedbackIn.action ∈ confirm | false_positive | severity_change | **need_human**
- need_human:落库 `need_human=True, verdict="need_human"`;不进 stats
- confirm:落反馈 + adopted+1 + **issue.need_human=False**(闭环)
- false_positive:现状已清 need_human,不变

### 4.5 前端(WorkbenchView.tsx + api.ts + bid-review.css)

- 证据行:真 chips(`文档名`+ 有页 `p.N`)+ section_path code + quote 摘录;det 无证据回落依据字段 chips(保留)
- 定位原文按钮(每条证据)→ 弹层:调 §4.1 content 端点,只渲染命中页窗口;上一页/下一页再取;命中图片 OCR 块 → 资产缩略图+文本对照;未命中显"未定位到原文"
- iss-acts 增"待人工"按钮(need_human 项隐藏)→ POST feedback `{action:"need_human"}` → 重取 issues
- TaskOut docs 消费方(审查材料小表)改读清单字段(kind/pages/chars)

## 5. 执行计划

| # | 任务 | 文件 | 验证 |
|---|---|---|---|
| 1 | 系统设置 default_ocr_engine + 公共 OCR resolve helper + cpa 改调用 | settings/(schemas,routers,basic-settings.tsx), extensions/ocr/resolve.py, contract_price/service.py | pytest:helper 三态(命中/缺/掩码回退);cpa 行为不变回归 |
| 2 | 解析层 parse.py(docx/pdf/图片→OCR 插回/按页落盘/docs 清单)+ create_task 接线 | bid_review/parse.py, routers.create_task, engine_meta 瘦身 | pytest:docx/pdf/text 三夹具;图片 OCR mock;大文档清单断言 |
| 3 | 按页/资产取数端点 | routers.py(+assets 落盘) | pytest:窗口返回/翻页/404/越权 |
| 4 | 分片抽取 extract.py v2(provenance+分片+合并归一) | extract.py, worker.py | pytest:分片合并/冲突不覆盖/单片失败降级/materials_hash 不变 |
| 5 | attach_evidence + det 发证 | rule_runner.py | pytest:证据挂接/降级空/判定零漂移 |
| 6 | need_human action + confirm 清标 | routers.py, schemas.py | pytest:三 action×need_human 组合 |
| 7 | eai-flow-ocr 文本端点确认(或补只读端点) | eai-flow-ocr 仓 | 接口走查记录进 spec 附录 |
| 8 | 前端:chips/定位弹层/待人工按钮/docs 清单适配 | WorkbenchView.tsx, api.ts, css | rstest dom:弹层按页取数/待人工发请求/大清单不整渲染;typecheck+lint |
| 9 | 镜像依赖(pymupdf, python-docx, httpx 已有)+ gateway 重建 | docker 后端镜像 | 重建+启动走查 |
| 10 | 真实任务 E2E:word 大文档(含图片页)上传→审查→证据卡→定位→待人工闭环 | — | 截图走查+issue 证据抽查 |

依赖顺序:1→2→3→4→5→6 可并行度低,7 可提前;8 依赖 3/5/6 契约;9 在 2 前完成;10 收尾。

## 6. 风险与挂账

| 项 | 处置 |
|---|---|
| 抽取 prompt 复杂度上升(provenance) | 降级路径兜底:provenance 缺→依据字段 chips;分片失败→null→need_human |
| 100MB docx 内存 | python-docx 流式读段落+图片逐个 OCR;文本 XML 通常 <10MB,图片不进 LLM |
| eai-flow-ocr 接口形态 | 任务 7 先确认;表格 JSON reshape 出页文本可行则零改动 |
| 旧任务无 provenance/无 pages | 前端全链路降级已就位(依据字段 chips、弹层"未定位") |
| docx 页码不准/缺失 | D8 诚实降级;LibreOffice sidecar 触发式后备(D2) |
| dedup/零漂移 | dedup_key 不含证据;materials_hash 仍只算 fields——历史任务不重发、det 结果不变 |
