# 地质样例库批量入库与系统统一 CLI 设计（geo-batch-ingest + eai-cli）

> 解决三件事：①report_id 编码规格与自动编码（现状=手工输入 slug）；②1000+ 份地质勘查报告的批量入库（现状=仅单文件上传）；③系统级统一 CLI（薄 REST 客户端，contract_price 等模块按子命令复用）。上游依赖：Phase 2 已落地的 `normalize_mineral`（T4）与 compile 管线。

## 0. 需求澄清结论（2026-09-03 会话定案）

| 问题 | 结论 |
|---|---|
| 样例文件现状 | 文件名有编码规律——**报告题名形态**（行政区划前缀 + 匿名化「某」+ 矿种词 + 阶段词 +「报告」尾缀），非结构化编码；实物例：「云南省昆明市东川区某铜矿铜银金多金属矿勘探报告.docx」 |
| report_id 形态 | **语义结构码** `gsb-<阶段码>-<矿种码>-<序号4位>`（人类可读、按矿种/阶段聚类）；解析失败回退 `gsb-auto-<序号>` |
| 入库流程 | **两阶段 CSV 校正流**：scan 预解析→人工校正 CSV→import 正式上传（错分由人兜底） |
| CLI 形态 | **薄 REST 客户端**（宿主机 httpx+argparse，登录后调既有端点；认证/权限/校验/脱敏门全走服务端）；模块子命令化复用 |

## 1. report_id 编码规格

**格式**：`gsb-<阶段码>-<矿种码>-<序号4位>`，全程满足既有 slug 约束 `^[a-z0-9][a-z0-9\-_]*$`（2-128 字符）。

| 段 | 取值 | 来源 |
|---|---|---|
| 阶段码 | 普查=`pu` 详查=`xc` 勘探=`kc` | 题名尾缀扫描（普查报告/详查报告/勘探报告/勘查报告） |
| 矿种码 | 铜=`cu` 煤=`co` 金=`au` 铁=`fe` 铅锌=`pbzn` 其他=`ot` | 题名矿种关键词 → 复用 Phase 2 T4 `normalize_mineral`（最早位置/负向守卫）→ slug→短码映射 |
| 序号 | `0001` 起 4 位零填充 | 按 (stage, mineral) 组查重顺延（§4 分配语义） |

**示例**：「云南省昆明市东川区某铜矿铜银金多金属矿勘探报告.docx」→ 阶段词「勘探」→`kc`；矿种词最早命中「铜」→copper→`cu`；序号按 (exploration, copper) 组当前最大 +1 → `gsb-kc-cu-0007`。

**回退链**：阶段或矿种解析失败 → `gsb-auto-<全局序号4位>`，CSV 置信度列标 `needs-review`；人工校正 CSV 时可直接改 id（import 以 CSV 为准）。

## 2. 题名解析器（parse_title）

纯函数 `parse_title(title: str) -> {region, mineral_slug, stage, confidence}`：

```
行政区划 → 截取前缀至首个「省|市|区|县|旗」→ region 字段（如 "云南省昆明市东川区"）
矿种     → 矿种关键词最早位置扫描（铜/煤/金/铁/铅/锌 + 非金属负向，复用 T4 词表）→ normalize_mineral → slug
阶段     → 尾缀扫描 普查|详查|勘探|勘查 → survey|detail|exploration
置信度   → 三段全中=auto；任一缺=needs-review
```

- 解析器实现于**后端**（geo_samples service 层），`POST /documents/suggest-id` 与 CLI scan 共用同一端点——**解析逻辑单份维护**，不存在 CLI/后端双实现漂移。
- 规则表（行政区划后缀字、矿种词表、阶段词）为模块内常量，随真实语料持续调优。
- 已知边界（docstring 声明）：题名无行政区划前缀→region 空；连写矿种取最早位置主矿种；词表外矿种→`ot`+needs-review。

## 3. 两阶段批量导入流（CLI `gsb` 子命令）

**阶段一 · scan（预解析，dry-run 零写入）**

```
python tools/eai.py gsb scan --dir <样例目录> [--recursive] [--limit N]
```
- 遍历 `*.docx/*.pdf` → 逐个调 `POST /documents/suggest-id`（传题名/文件名）→ 生成 `gsb_manifest.csv`：`file_name, report_id(建议), stage, mineral, region, confidence(auto|needs-review)`
- report_id 冲突自动顺延序号并在备注列标注；stdout 汇总 `扫描 N | auto X | needs-review Y | 冲突顺延 Z`

**人工校正**：Excel 打开 CSV——改错分阶段/矿种、改 report_id、**删掉不入库的行**（CSV 无行=不传）。

**阶段二 · import（正式上传）**

```
python tools/eai.py gsb import --csv gsb_manifest.csv [--workers 4] [--defer-parse] [--dir <根目录>]
```
- 读 CSV（人工校正版为准）→ slug/枚举本地校验 → 并发上传（默认 4 worker，调既有 `POST /documents/upload` 单文件端点——校验/脱敏门/去重全复用）
- **解析策略**：docx 默认即时 parse；pdf 默认 `--defer-parse`（扫描件 OCR 每份最长 30 分钟，混合库不可默认即时）；`--parse-all` 覆盖
- **断点续传**：`gsb_import_state.json` 记已完成 report_id，重跑自动跳过
- **409 顺延**：report_id 撞库自动 +1 重试（响应回实得 id 记入结果）
- 结束汇总 + 失败清单 `gsb_import_failed.csv`（修复后可重跑）
- scan 阶段 CSV 里的 stage/mineral 直接作为表单字段值上传——**csv 校正即最终真值**，不再依赖自动解析

## 4. 统一 CLI（`tools/eai.py`）——系统级模块运维入口

**定位**：全系统统一的模块运维入口——登录/并发/断点等公共层一次建成，各定制模块以**子命令注册**方式接入批量能力。统筹范围（用户 2026-09-03 定案）：地质样例库批量上传、合同价格分析批量合同上传解析、license 生成、后续定制模块。

```
tools/eai.py（argparse subparsers；依赖仅 stdlib + httpx）
├─ 公共层：login 会话（nginx:2026 → POST /api/extensions/auth/login username 字段 + CSRF cookie，
│          存 ~/.eai/session.json 含过期时间；过期自动重登）+ 并发池（httpx 连接池 + worker 信号量）
│          + 断点 state 读写 + 结束汇总/失败清单
├─ 子命令（两类）：
│   【服务端型】需会话，薄调模块既有 REST 端点：
│     eai.py gsb scan|import|status|suggest-id    ← 本期实现（geo-samples）
│     eai.py cpa upload|parse|status              ← 本期实现（contract-price 批量上传+解析触发）
│     eai.py <module> …                           ← 后续模块按同配方注册
│   【本地工具型】无需会话，同仓库 import 既有工具函数：
│     eai.py license generate|list                ← 收编 tools/license/license_generator.py（离线签名，私钥所在处运行）
```

- **薄客户端纪律**（服务端型）：只调 REST 端点，零 DB/MinIO 耦合；认证/权限/校验/脱敏门全走服务端
- **两类子命令的分层意义**：公共会话层只服务「服务端型」；「本地工具型」绕过会话层直挂——两类并存验证框架抽象正确
- **新模块接入配方**（三步）：①模块已有 REST 端点则直接写薄适配；②在 `SUBCOMMANDS` 注册表加一项（名称/帮助/处理函数/是否需会话）；③复用公共并发池与断点 state。目标：新模块批量能力接入 ≤ 一个小文件
- 放置 `tools/eai.py`（新目录——统一 CLI 是长期系统入口，与 scripts/ 一次性运维脚本分离；license_generator.py 随收编保留原位或迁入 tools/，实现时定）
- 登录流程按 T9 实证：nginx:2026 入口、`username` 字段、CSRF cookie 处理

## 5. 后端增量（geo_samples）

1. `POST /documents/suggest-id`：参数 `title`/`filename` → parse_title + 按 (stage,mineral) 组查重顺延 → `{report_id, stage, mineral, region, confidence}`；权限同 `_PERM`。UI 上传框加「自动」按钮调用（替代手工想 slug）；CLI scan 复用。
2. 题名解析器（service 层纯函数 + 词表常量）。
3. **`DELETE /documents/{document_id}`**（样例文档库列表删除按钮的后端）：
   - 守卫：404 不存在；**compiled 状态 409「已编译样例不可删除（编译产物在技能 references 中，先回退状态）」**——V1 不做编译产物回收；其余状态均可删。
   - 行为：删 gsb_documents 行 + MinIO 三前缀对象（raw/work/clean，get_object 前缀已校验）；**gsb_redactions/gsb_run_history 流水保留**（无 FK 设计本就为审计存活性，document_id 悬空是既定语义）；gated compile 互斥不受影响（compile 只读 reviewed）。
   - MinIO 删除失败（对象已不存在等）→ 容忍并继续删行（S3Error 逐前缀捕获），detail 不落（无 run 面）；行删除成功即 204。
4. **GET /documents 响应加 `total`**：同过滤条件 `count(*)`——前端分页需要「共 N 条」（现响应仅 {items,skip,limit} 无法判总页）。
5. 无新表、无迁移。

### 5.1 前端增量（DocumentsView 列表页）

1. **分页**：`共 {total} 条` + 上一页/下一页（skip 游标）+ 每页条数选择（20/50/100，默认 50）；查询键带页码；统计头仍走 limit=200 全量（互不影响）。
2. **操作列删除按钮**：灰色文字按钮「删除」→ `window.confirm("确认删除 {report_id}？原始文件与解析/脱敏产物将一并删除，审计流水保留，不可恢复")` → 调 DELETE → invalidate 列表与统计；compiled 行不渲染删除按钮（后端亦 409 双保险）；与既有 解析/脱敏/抽审/重试 按钮并列。

## 6. 测试与验收

| 层 | 断言 |
|---|---|
| parse_title 单测 | 题名样例集：单矿种/连写（铜银金→copper）/词表外（萤石→ot+needs-review）/无阶段词/无行政区划/非金属负向 |
| suggest-id 端点 | 查重顺延（同组已有 gsb-kc-cu-0007 → 建议 0008）/解析失败回退 auto |
| CLI scan | mock 端点 → CSV 内容与置信度列正确；冲突顺延 |
| CLI import | mock 端点 → 并发上传/断点跳过/409 顺延重试/失败清单；--defer-parse 传参正确 |
| DELETE 端点 | 各状态删除行为/compiled 409/MinIO 容错删行/流水保留（document_id 悬空可查） |
| GET /documents total | 同过滤 count 正确；前端分页组件渲染与翻页状态 |
| 验收 | 10 份真实文件两阶段走通；CSV 校正后矿种与人工判断一致率记录；1000 份级 dry-run（scan）性能抽测 |

## 7. 分期与边界

- **本期**：suggest-id 端点 + 解析器 + `tools/eai.py` 骨架（login/公共层/两类子命令注册表）+ `gsb scan/import` + `cpa upload`（薄适配 contract-price 既有上传/解析端点）+ `license generate`（收编既有生成器）。
- **本期不做**：UI 批量对话框（CLI 覆盖）；count 聚合端点；扫描件 OCR 批量调度器（--defer-parse 后由管理页逐批触发既有 parse 端点）；后续新模块的子命令（按接入配方随到随接）。
- **风险**：①题名解析准确率依赖语料——CSV 校正流兜底，规则表随入库量迭代；②1000 份扫描件 OCR 总时长可达天级——defer-parse + 批次调度消化；③登录会话过期中途中断——CLI 自动重登续传。

## 附录 · 关键锚点

- 现状：routers.py:57 `report_id: str = Form(...)` + UploadMeta slug 约束；上传端点单文件；仓库无 typer/click 依赖（统一 CLI 用 stdlib argparse 一致）
- 复用件：normalize_mineral（build_output.py MINERAL_ALIASES，Phase 2 T4）；登录流程（T9 实证：nginx:2026/username/CSRF）；contract_price /documents/upload（cpa 子命令接缝）
- 语义先例：commodity 中文自由文本值域（「铜」「铜银金」）与 normalize_mineral 最早位置语义一致
