# 地质样例库模块详细设计（geo-sample-bank · as-built）

> 本文是 `geo_samples` 模块（Phase 1 已交付）的功能设计、数据流程设计与 UI 设计详篇。全部内容锚定 2026-09-02 工作区实物（4 路并行代码精读，~85 条事实带 `文件:行号`）；与概要设计 `2026-09-01-geo-sample-bank-design.md` 的关系：概要管「为什么这样建」，本文管「建成了什么、每一处怎么运转」。Phase 2 扩展点在 §6 显式标出。

## 0. 模块概览

```
                        ┌─────────────────────────────────────────────┐
 用户(管理员/审核者) ──→ │ 前端 /geo-samples 三页 (DocumentsView 等)    │
                        └──────────────┬──────────────────────────────┘
                                       │ authFetch/authFormFetch
                        ┌──────────────▼──────────────────────────────┐
                        │ Gateway /api/extensions/geo-samples/* 8端点  │←─ require_permission("geo_samples:access")
                        └──────┬───────────────┬─────────────────────┘
                               │               │ BackgroundTasks(async)
                 ┌─────────────▼───┐   ┌───────▼────────────────┐
                 │ extensions PG    │   │ service.run_parse/run_redact
                 │ gsb_ 三表        │   │  ├ parsers（docx/pdf/OCR三分支）──→ eai-flow-ocr:8010
                 └─────────────────┘   │  ├ redactor（9规则两档）           ──→ MinIO geo-samples 桶(raw/work/clean)
                                       └────────────────────────┘
```

- **代码位置**：backend `app/extensions/geo_samples/`（models/storage/redactor/parsers/crud/schemas/service/routers 八文件）；前端 `src/extensions/geo-samples/` + 路由壳 `src/app/geo-samples/`；OCR 服务 `mcp-server/ocr-service/`。
- **模块边界**：只管样例资产的入库生命周期（上传→解析→脱敏→抽审）。RAGFlow 分发、节号切片编译（bank_compile）、深度基线标定均为 Phase 2（概要设计 §5/§9），Phase 1 代码中无 `GSB_RAGFLOW_*` 任何接线（全仓 grep 仅 `GSB_MINIO_*` 四处）。

## 1. 功能设计

### 1.1 角色与权限

| 角色 | 权限 | 效果 |
|---|---|---|
| dept_head（部长） | `geo_samples:access` + `nav:geo-samples` + 3 页面 | 完整可见可用 |
| project_manager | 同上（overlay 显式列出——该角色无 `#inherit`，bug-1087 教训） | 完整可见可用 |
| superadmin | `*` 通配 | 完整 |
| user / writer | 无任何 gsb 权限 | 导航不可见、API 全部 403 |

- 权限点声明位置特殊：v3 权限注册表从**页面 `operations`** 收集权限点（无独立 permission_points 键），故 `geo_samples:access` 声明在 `gsb:page:documents` 的 operations 下（`config/permissions.yaml:177-193`）。
- 全部 8 个端点共用模块级单权限门 `_PERM = Depends(require_permission("geo_samples:access"))`（routers.py:31-32）——与 cpa/csp 的 `system:access` 同粒度但模块作用域更窄；审核细分权限（`geo_samples:review`）预留在 `gsb:page:review` 页面结构中，待真实角色需求出现再拆。

### 1.2 文档状态机

```
                    ┌─────────────── run_parse except ───────────────┐
                    │                                                 ▼
 [上传] ──→ uploaded ──→ parsed ──→ redacted ──→ reviewed
    (POST /upload)  │           │            │   ▲            (不可再动：
                    │           │            └───┘ reject 保留   parse 拒绝
                    │           │                (POST /review)   reviewed)
                    │           │                 ▲
                    └───────────┴──→ failed ◄────┘ 任意后台任务异常
                         (重新解析入口放行 uploaded/failed/parsed)
```

| 迁移 | 触发者 | 守卫 | 副作用 |
|---|---|---|---|
| →uploaded | POST /upload | 六道门（§1.3①） | raw 落 MinIO + 建行 + 自动启动 parse run |
| uploaded→parsed | run_parse 成功 | 无（后台） | work/parsed.md 落 MinIO；parse_mode=docx/pdf_text/pdf_ocr |
| parsed→redacted | run_redact 成功 | 仅 parsed 可发起；发起时无 running parse/redact | clean/source.md 落 MinIO + gsb_redactions 事件 + summary，**同一 commit 原子** |
| redacted→reviewed | POST /review decision=approve | 仅 redacted 可审 | review_note 留痕 |
| redacted→redacted | POST /review decision=reject | 同上 | 仅回填 note（文档留在待审列表） |
| 任意→failed | run_parse/run_redact except | — | 守护式 rollback→置 failed→守护式 commit→best-effort 记账 |

- **重新解析**（POST /parse）只放行 `uploaded/failed/parsed` 三态；`redacted/reviewed` 同被拦，文案「当前状态 {status} 不允许重新解析（reviewed 章稿已定稿）」（routers.py:104）。
- **Phase 2 预留**：`compiled` 状态（models.py:30 docstring）；前端状态渲染已做未知值兜底（§3.4）。

### 1.3 API 功能规格（8 端点）

统一前缀 `/api/extensions/geo-samples`，统一权限门；错误文案全中文且可直接展示给用户。

**① POST /documents/upload**（multipart）

| 门序 | 检查 | 失败响应 |
|---|---|---|
| 1 | 扩展名 `.docx/.pdf` | 400「仅支持 .docx/.pdf」 |
| 2 | UploadMeta 校验（report_id：2-128 字符，`^[a-z0-9][a-z0-9\-_]*$`） | 400「样例元数据非法：{第一条 msg}」 |
| 3 | stage∈{survey,detail,exploration}、mineral∈{copper,coal,gold,iron,lead_zinc,other} | 400「stage/mineral 取值非法」 |
| 4 | report_id 全库唯一 | 409「report_id {x} 已存在」 |
| 5 | 非空文件 | 400「空文件」 |
| 6 | SHA-256 内容去重（raw_uri 不同的历史行命中即拒；同 uri 原地重传不算） | 409「相同内容的样例已存在（file_hash 命中）」 |
| 尾段 | put_raw（to_thread）→ create_document（commit+refresh）→ create_run(parse) → 后台 run_parse | 200 `{"document": DocumentOut, "run_id"}` |

已接受的 Phase 1 窗口：put_raw 成功而建行失败会留孤儿 raw 对象（routers.py 注释）。

**② POST /documents/{id}/parse** 守卫时序：404「样例不存在」→ 409「脱敏任务在跑——稍后再解析」→ 状态门（见 §1.2）→ sweep_stale_runs → 409「解析任务已在跑」→ 后台 run_parse → `{"run_id"}`。

**③ POST /documents/{id}/redact** 守卫时序：404 → 409「仅 parsed 状态可脱敏（当前 {status}）」→ sweep → 409「解析任务在跑，work_uri 可能写入中——稍后再脱敏」→ 409「脱敏任务已在跑」→ 后台 run_redact → `{"run_id"}`。（双向互斥闸门：parse/redact 谁在跑都拦对方。）

**④ GET /documents**：参数 stage/mineral/status（可选过滤）+ `skip=Query(0,ge=0)` + `limit=Query(50,ge=1,le=200)`；排序 `created_at desc, id desc`（分页稳定）；返回 `{"items":[DocumentOut], "skip", "limit"}`。

**⑤ GET /documents/{id}**：404「样例不存在」；命中返回 DocumentOut（13 字段，见 §2.3 无泄露面）。

**⑥ GET /documents/{id}/redactions**：按 start 升序返回事件清单 `{items:[{id,rule,mode,start,end,original_hash}]}`；未知 id 返回空 items 而非 404（审计查询语义）。

**⑦ POST /documents/{id}/review**：body `{decision, note}`；404 预检 → apply_review 的 ValueError 原文直传 409（「仅 redacted 状态可审（当前 {status}）」等）；成功返回最新 DocumentOut。

**⑧ GET /runs**：最近 50 条运行（`created_at desc, id desc`），`{items:[{id,document_id,run_type,status,detail,created_at,finished_at}]}`。

### 1.4 解析子系统（三分支决策树）

```
file_type?
├─ .docx → python-docx iter_inner_content() 同步转 md（to_thread 包裹）
│    ├ 标题样式：Heading 1 / Title →「## 」；Heading 2 →「### 」；Heading 3-5 →「#### 」；其余段落原样
│    ├ 公式：段落含 w:object（MathType OLE）或 m:oMath（OMML）→ 占位「[公式:pN]」全局递增
│    │   · 空段落 → 独占一行占位；有文本段落 → 文本保留 + 追加「 [公式:pN]」
│    └ 表格 → md 管道表：单元格 strip + 换行→<br> + 竖线→\|；首行表头 + | --- | 分隔行
│        已知限制（文件头声明）：嵌套表格不展开；合并单元格文本按跨格重复
└─ .pdf
    ├ 字符密度 ≥ 200 字符/页（SCAN_DENSITY_THRESHOLD）→ pymupdf4llm 转 md（mode=pdf_text）
    └ 密度 < 200（扫描件）→ ScannedPdfError → OCR 分支（mode=pdf_ocr）
         POST {OCR_SERVICE_URL|http://eai-flow-ocr:8010}/ocr，multipart + data={"text_pages":"999"}
         （服务端默认 text_pages=3 只回前 3 页整页文字——样例库要全文语料显式放开；对 contract_price 零影响）
         超时 1800s；仅 RemoteProtocolError 重试（3 次，30s/60s 退避）；空结果抛「OCR 返回空文本——服务异常或空文档」
         页面结构：text 为主体 + tables[].rows 摊平成管道行（cell 为 {text,bbox,confidence} dict 取 text）
其他扩展名 → ValueError「不支持的文件类型: {name}（仅 .docx/.pdf）」
```

### 1.5 脱敏子系统（两档制规则引擎）

**设计红线**：规则表不含任何匹配地质数值的模式——品位/厚度/资源量/涌水量必须原样保留（脱敏会毁掉 SL3 指纹库与深度标定的范文数值基础）。

**9 条规则**（`redactor.py` RULES 表；MASK=`****`）：

| # | 规则名 | 匹配语义 | 档位 |
|---|---|---|---|
| 1 | exploration_cert | 探矿许可证号：非字母数字前缀 + `C` + 10-16 位数字（bug-2216 形态） | auto |
| 2 | uscc | 统一社会信用代码：18 位字符集且至少含一字母（纯 18 位数字不误配） | auto |
| 3 | coord_pair | 高斯坐标 XY 成对（6-8 位数字，中英分隔符） | auto |
| 4 | latlon | 经纬度（°′″+NSEW 方位字母；`(?<!\d)` 防从长数字串截段） | auto |
| 5-7 | phone / tel / email | 手机号 / 座机 / 邮箱 | auto |
| 8 | org_name | 中文机构名（后缀词典：有限公司/股份…/勘查院/地质队 等） | auto |
| 9 | person_field | 「负责人/编制人/审核人/项目经理…：姓名」——**只标记不替换** | review |

**边界约定**：全部用 ASCII 环视而非 `\b`——Python re 的 Unicode 模式下 CJK 属 `\w`，「证号C530…」的 `\b` 永不成立，`\b` 会让规则整段漏配（文件头注释， cerebrum DNR 条目）。

**算法**：所有规则对原文 finditer → 重叠消解（start 升序、end 降序，保留最先/最长者）→ **从尾向头**替换（偏移不失效）→ 事件按文档顺序输出。事件 6 字段：`rule/mode/start/end/original_hash(=sha256(原文片段))/replaced`——**只落哈希绝不落明文**；start/end 是 work/parsed.md **原文偏移**（auto 替换后与 clean 文本不再对应，UI 只展示不用于高亮 clean）。

**已知误伤（org_name，注释内声明，Phase 2 调优 backlog）**：①「提交本院设计院审核」动词并入整段被 mask；②前缀字符类不含 ASCII——「云南XX勘查院有限公司」只 mask 后半；③局类后缀（「云南省煤田地质局」）零命中。

### 1.6 run 记账与自愈

- **create_run** 插入 running 行并**立即 commit**（后台任务启动前 run 行已可查）；**finish_run** 按 run_id 置 status/detail/finished_at。
- **_finish_run best-effort 包装**（service 层）：finish_run 记账失败仅 log.exception、run 行停留 running——记账层故障绝不改写已 commit 的业务状态、绝不击穿「后台任务不抛出」契约（Task 7 实测落定）。
- **sweep_stale_runs（60 分钟阈值）**：parse/redact 端点在 running 检查前调用，把超龄 running 行改判 failed（detail="stale (gateway restart?)"）——网关重启遗留行不会永久 409 锁死文档。has_running_run 用 `limit(1)+scalar_one_or_none`，陈旧行累积也不抛 MultipleResultsFound。
- **失败路径**（parse/redact 同构）：except → log.exception → 守护式 rollback（rollback 自身失败仅 log）→ 置 failed → 守护式 commit（失败则文档保留原状态）→ best-effort 记账，detail=`{异常类名}: {异常}`。

## 2. 数据流程设计

### 2.1 存储分层

**MinIO 单桶三前缀**（bucket=`geo-samples`，懒建）：

| 前缀 | 内容 | 敏感级别 |
|---|---|---|
| `raw/<report_id>/<原文件名>` | 上传原始件（未脱敏） | 最高——永不进 repo/不下发 RAGFlow/不进沙箱 |
| `work/<report_id>/parsed.md` | 解析产物（未脱敏中间件） | 高——仅后台管线可读 |
| `clean/<report_id>/source.md` | 脱敏全文（reviewed 后的唯一分发源） | 低——Phase 2 分发单位 |

put_raw 对 file_name 先 `os.path.basename` 剥路径成分（防 `..` 破坏前缀布局）；get_object 强制 `s3://geo-samples/` 前缀校验（ValueError 而非 assert——`python -O` 剥 assert）。

**PG 三表**（共享 Base，gateway 启动 create_all 自动建表；加列必须走 `migrate_db()` 幂等 ALTER）：

| 表 | 关键列 | 设计要点 |
|---|---|---|
| gsb_documents（18 列） | report_id unique+index；file_hash index；status index；parse_mode；raw_uri/work_uri/clean_uri；redaction_summary(JSON {rule:count})；review_note | `DocumentOut` 只暴露 13 字段——file_hash 与三个 uri（未脱敏/未解析内容路径）**不在 API 泄露面** |
| gsb_redactions（7 列） | document_id index；rule/mode/start/end/original_hash | **故意无 FK**——审计流水须活过文档删除（与 cpa 兄弟有意分叉）；绝不落明文 |
| gsb_run_history（7 列） | document_id 可空 index；run_type(parse/redact)；status(running/done/failed)；detail | 同样无 FK；status 非索引列（百行级全扫可忽略，Phase 2 批量再议部分索引） |

### 2.2 全生命周期数据流（逐步谁写什么到哪）

```
[1] 上传        browser ──multipart──→ upload 端点
                六门通过后：
                MinIO ←── put_raw（raw/<rid>/<file>）
                PG    ←── create_document（status=uploaded, raw_uri, commit）
                PG    ←── create_run(parse, running, commit)     ← 先于后台任务，crash 可见
                BackgroundTasks ← run_parse(db, doc.id, run.id)

[2] 解析        run_parse: PG 读 doc → MinIO 读 raw_uri → parsers.parse_document
                → MinIO ← put_work（work/<rid>/parsed.md，未脱敏）
                → PG 单次 commit：work_uri + parse_mode + status=parsed
                → finish_run(done, "mode=docx")  [best-effort]

[3] 脱敏        人工点「脱敏」→ redact 端点（互斥闸门+sweep）→ run_redact:
                MinIO 读 work → redact_text → MinIO ← put_clean（clean/<rid>/source.md）
                → PG 同一次 commit：clean_uri + add_redactions 事件批量 add
                   + redaction_summary + status=redacted      ← 事件与状态原子
                → finish_run(done, summary JSON)

[4] 抽审        ReviewView → GET redactions（只读事件）→ 人工对照命中清单
                → POST review(approve) → status=reviewed + review_note，单 commit

[5] 观测        三页的列表查询 5s 轮询（refetchInterval，后台标签页自动暂停）
                每步 run 行在 GET /runs 可见（detail 含 mode / summary / 异常类名）
```

**并发安全要点**：parse 与 redact 端点互设 running 守卫（双向互斥）；redact 的事件与状态单 commit 原子（events 不可能脱离状态存在）； MinIO 阻塞调用全部 `asyncio.to_thread`（routers/service 共 5 处），parse 的 CPU 重活在 parsers 内部 to_thread——事件循环零阻塞。

### 2.3 数据契约（前后端无漂移面）

| 契约 | 后端 | 前端镜像 |
|---|---|---|
| 文档 | DocumentOut 13 字段（不含 file_hash/三 uri/updated_at） | `GsbDocument` 13 字段逐一对应 |
| 事件 | RedactionOut 6 字段 | `GsbRedaction`（mode: "auto"\|"review"） |
| 运行 | RunOut 7 字段 | `GsbRun`（run_type: parse\|redact; status: running\|done\|failed） |
| 枚举 | ALLOWED_STAGES/STATUSES/MINERALS | FilterBar STAGE_OPTIONS(3)/STATUS_OPTIONS(5)/MINERAL_OPTIONS(6) |
| 错误 | HTTPException detail 中文串 | `authFetch` 抛 `Error&{status}`、`authFormFetch` 同形；视图统一 `alertErr` 渲染 message |

上传传输专项：`authFetch` 无条件设 `Content-Type: application/json`（毁 multipart 边界）→ 上传必须走 `authFormFetch`（client.ts 专用包装）。

### 2.4 幂等与自愈

- **上传去重双层**：report_id 唯一索引（409）+ file_hash 内容去重（409）——同名重传覆盖、异名同内容拒绝。
- **产物确定性**：解析/脱敏产物按 report_id 定址（非时间戳），重跑覆盖同键对象。
- **陈旧 run 自愈**：sweep_stale_runs(60min) 在每次 parse/redact 准入检查前执行。
- **审计存活性**：redactions/runs 无 FK——文档删除后流水仍在（合规回溯）。

### 2.5 Phase 2 数据流延伸（已设计未编码）

`reviewed → compile`（bank_compile 四步：拉 reviewed → `## N.M` 节号切片+标记行 → per 矿种×阶段 median 标定 → SL3 指纹源落 repo + RAGFlow 切片上传，status→compiled）。RAGFlow 侧约定：单库起步（现有固体矿产库）、切片为单位（每片首行 `【矿种】X｜【阶段】Y｜【report_id】Z｜【节号】chN.M`）、General+parent_child 分块、v0.25.3 钉版（概要设计 §3.4）。

## 3. UI 设计

### 3.1 信息架构与导航

```
/geo-samples（ShellLayout 包裹——提供 QueryClientProvider/PermissionProvider）
├─ 顶部导航（h-16 header 内）：📄 样例文档库 | 🛡 脱敏抽审 | 🕘 运行记录
│    · 每项绑 pageId（gsb:page:documents/review/tasks），canPage 过滤
│    · 权限加载中 fail-open 全显（isLoading 时不闪断）；active 高亮 exact/startsWith
└─ 内容区（overflow-auto），页头固定标题「地质样例库」
```

三个路由均为薄壳 page.tsx（5 行，仅 import 视图组件）。

### 3.2 设计语言（bid-quote 原语体系，复制模式）

- **色板**（chartTheme，与 bid-quote 同值）：PAGE_BG `#fbfafa`、BLUE `#4D6BFE`、AMBER `#f0a122`、GREEN `#20b26c`、RED `#e5484d`、ACCENT_SOFT `#eef1ff`、INK/INK_2/INK_3 三级墨色。
- **原语**：`StatCard`（label 12.5px 灰 → 主数字 26px tabular-nums → 注脚 12px 浅灰）、`SectionCard`（可折叠区块：badge+标题+副题，点标题行折叠）、`FilterBar`（手写下拉：触发器/面板/useDismiss 点外+Escape 关闭；不依赖 shadcn）、`ui/table`（原生 table + `w-full overflow-x-auto`；本模块行不可点击故无 cursor-pointer）。
- 复制而非跨模块 import（bid-quote 原语无被跨模块消费先例；每个复制文件头注释指明出处，re-sync 用 diff 即可）。

### 3.3 页面线框与状态矩阵

**页 1 · 样例文档库（DocumentsView）**

```
┌ StatCard × 5：已上传 | 已解析 | 已脱敏 | 已过审 | 失败 ──────────┐
│  （计数=独立全量查询，不随筛选联动；加载中显示「—」不闪 0）        │
│  uploaded 卡注脚：「共 N 份」                                     │
├ ① 上传区（SectionCard）────────────────────────────────────────┤
│  [report_id 输入框 placeholder「report_id（如 2019-qianxi-gold-expl）」]
│  [文件选择 accept=.docx,.pdf]  [上传]（isPending→「上传中…」disabled）
│  sub：仅 .docx/.pdf；report_id 全库唯一，相同内容按哈希去重（409 拒绝）
│  行内提示：阶段/矿种取下方筛选条当前值（不选则用后端默认：勘探/铜）
├ ② 筛选条（FilterBar）：[勘查阶段▾普查/详查/勘探] [矿种▾铜/煤/金/铁/铅锌/其他]
│  [状态▾五态] ——任一有值时右侧出现「清空」                       │
├ ③ 文档表格（7 列）────────────────────────────────────────────┤
│  report_id(等宽小字) | 文件 | 阶段 | 矿种 | 状态(色字+中文)      │
│  | 脱敏摘要(JSON {rule:count} 截断48) | 操作                     │
│  操作按状态：uploaded→[解析] parsed→[脱敏] redacted→[抽审→跳转]  │
│              failed→[重试](红字) reviewed→（无按钮，定稿）        │
│  空态：「暂无样例」                                              │
└────────────────────────────────────────────────────────────────┘
状态矩阵：isPending→「加载中…」；空→空态文案；错误→后端 detail 经 alertErr 弹出
```

**页 2 · 脱敏抽审（ReviewView）**——审「漏脱」只看命中清单，不看全文

```
┌ ① 选择区：[待审下拉]「选择待审样例（N）」——数据源仅 status=redacted
│   选项 label「{report_id}（{file_name}）」；isPending→「加载中…」
│   空态「暂无待审样例（先在样例文档库完成脱敏）」
├ ② 命中清单（选中后渲染；以 selected 存在性双保险——文档被审核后面板自动让位，
│   占位「该样例已不在待审列表（可能已被审核），请重新选择」）
│   表 4 列：规则 | 档位（自动替换=墨色 / 待审标记=琥珀+行底 ACCENT_SOFT 高亮）
│           | 位置 start–end（等宽小字，原文偏移） | 原文哈希（前 12 位…）
│   ——绝不渲染明文；空清单「无命中记录」
├ ③ 裁决：[审核备注 textarea rows=2 placeholder「审核备注（reject 时必填理由）」]
│   [通过（reviewed）绿底] [驳回（退回脱敏）红底]
│   onSuccess：approve→清空选择与备注（面板让位）；reject→保留（文档留列表）
└────────────────────────────────────────────────────────────────┘
```

**页 3 · 运行记录（TasksView）**

```
┌ ① sub「后台任务执行轨迹，5 秒自动刷新」
├ ② 表 5 列：类型(解析/脱敏) | 状态(运行中琥珀/完成绿/失败红,未知值灰+原文)
│           | 文档(id 前 8 位等宽) | 详情(truncate 72——mode/summary/异常类名)
│           | 时间(toLocaleString)；空态「暂无运行」
└────────────────────────────────────────────────────────────────┘
```

### 3.4 交互规则全集

1. **错误可见性**：TanStack 默认吞 mutation rejection——所有 mutate 一律 `onError: alertErr`（`e instanceof Error ? e.message : String(e)`），后端中文 detail 直达用户；上传成功清空表单、失败保留重填。
2. **未知值兜底**：状态/阶段/矿种/运行状态四处映射全部 `LABEL[x] ?? x` + 中性灰 `?? INK_2`——Phase 2 后端先加 `compiled` 等新值时行不空白、不崩溃。
3. **5s 轮询**：文档列表与运行记录 `refetchInterval: 5000`（后台 parse/redact 的远端进度近实时反映；后台标签页自动暂停）；所有 mutation onSuccess 失效 `gsb-documents`+`gsb-runs` 两组缓存。
4. **脱敏摘要直读**：表格内直接展示 `{rule: count}` JSON 摘要——不点开就能看到「这条脱了哪些类」。
5. **可访问性基线**：下拉原生 button（Tab/Enter 可操作）、分组 aria-label（勘查阶段/矿种/状态）、复位项「全部阶段」等；FilterBar 继承 bid-quote 的已知 a11y 缺口（无 aria-expanded/方向键导航）——与上游一致不单独分叉。

## 4. 运行与运维

| 项 | 现状 |
|---|---|
| 部署 | docker compose `-p eai-docker`；重启 gateway 即自动建 gsb_ 三表（create_all；加列走 migrate_db ALTER） |
| env | `GSB_MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/SECURE`（默认 ragflow-minio:9000/minioadmin/minioadmin/false）；`OCR_SERVICE_URL`（默认 http://eai-flow-ocr:8010）——**生产须以 env 覆盖默认凭据（离线部署手册待补 R4）** |
| 日志 | gateway stdout 重定向至 `/app/logs/gateway.log`（宿主 `logs/gateway.log` 卷挂载）；geo_samples 失败路径全部 `log.exception` |
| 观测 | 三张截图证据与上传全流程实测见 T12 验收（2026-09-01）；`GET /runs` 为后台任务唯一观测面 |
| 测试 | geo_samples 25 后端用例 + 前端 rstest 6 用例；SDK 形参签名回归测试（bug-3072 教训：MagicMock 不校验真签名） |

## 5. 已知限制与 Phase 2 扩展点

| # | 项 | 类别 | 去向 |
|---|---|---|---|
| 1 | RAGFlow 分发 / bank_compile / 深度基线标定 / SL3 指纹扩容 | 设计完成未编码 | Phase 2 计划（概要 §5） |
| 2 | 批量上传并发池（spec §3.2） | 缩围已记录 | Phase 2（届时一并解决 OCR 连接占用 R2、limit=50 计数上限 R3） |
| 3 | 预览 PNG 对照（抽审 UI） | 缩围已记录 | Phase 2（OCR preview_png_b64 落 MinIO） |
| 4 | org_name 三类误伤 / 局类后缀零命中 / reviewed 无重脱敏路径 | 规则引擎 backlog | Phase 2 规则 v2 + reviewed→重脱敏通路（R5） |
| 5 | docx 中文标题样式（“标题 1”≠"Heading 1"）降级为正文的风险 | R1——批量入库前必验 | Phase 2 前置：样式别名归一 + 真实报告群验证 + 零节号切片硬失败 |
| 6 | 上传无大小上限 / review 单权限点 / FilterBar a11y 继承缺口 | 记录在案 | 按需 |
| 7 | `docker/ragflow/.env:2` 残留 latest 未钉 | 版本卫生 | 顺手修 |

## 附录 · 证据基线

本文全部行为声明源自 2026-09-02 四路 as-built 精读（workflow wf_18cec5d1-2de，~85 条事实）：API/状态机（routers/service/crud/schemas/models）、脱敏与解析（redactor/parsers/ocr-service server+engine）、前端三视图（geo-samples 全部 tsx/ts）、存储权限运维（storage/models/permissions.yaml/roles_custom.yaml/database.py/license 三镜像/dev-entrypoint）。行号以当日工作区为准，后续演进以代码为最真源。
