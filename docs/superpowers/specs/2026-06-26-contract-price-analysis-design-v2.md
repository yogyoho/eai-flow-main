# 合同分项价格分析模块 — 设计文档 v2

> **状态**:已批准(架构方向),待实现
> **日期**:2026-06-26
> **作者**:/plan-ceo-review 协作产出
> **取代**:[2026-06-15-contract-price-analysis-design.md](./2026-06-15-contract-price-analysis-design.md)(v1,RAGFlow 提取路径)
> **关联**:`skills/custom/contract-price-analysis/scripts/`、`backend/app/extensions/contract_price/`、`frontend/src/extensions/contract-price/`、主前端路由 `/contract-price`

---

## 0. v1 → v2 关键转变(决策记录)

| 维度 | v1(RAGFlow 路径) | v2(直接 OCR + MinIO) | 转变原因 |
|------|------------------|----------------------|---------|
| **表格提取源** | RAGFlow chunk API(Markdown 表格) | 直接 OCR 文档(RapidOCR) | RAGFlow 的 chunk 机制按 token 切分,**破坏表格完整性**(截断、跨 chunk 断裂、合并单元格丢失),与"提取完整结构化表格"的需求天然冲突 |
| **文档存储** | RAGFlow 知识库 | **MinIO 独立 bucket** | 解耦文档管理与提取;MinIO 基础设施项目已就绪(`ragflow-minio` 容器 + `knowledge/storage.py` 抽象) |
| **增量检测** | 拼凑指纹(name+time+chunk_count) | **文件 SHA-256 精确哈希** | RAGFlow 无内容哈希,误判频发;文件级 SHA-256 零误判 |
| **数据可信度** | 无校验,静默提取 | **价格强校验 + needs_review + 溯源比对** | 扫描件 OCR 价格识别易错(120000→12000),且错误结果看似合理;必须有校验 + 人工核验闭环 |
| **解析模式** | table/list/mixed 三选一 | 单一 OCR 路径 | 实际合同 **~100% 扫描件**,表格**带边线**;原生 PDF 路径用不上,模式分支无意义 |

**保留不变**(v1 已做对的部分):三层架构(skill/backend/frontend)、`cpa_` 表前缀隔离、DBSCAN 聚类 + 技术参数向量化、IQR 异常值、6-Sheet Excel、聚类人工审核流程、cookie-JWT 认证。

---

## 1. 问题与约束

### 1.1 目标

从上传的合同扫描件中,OCR 提取**货物分项价格表**,按"货物名称 + 技术参数"聚类归并,计算每类单价统计量(均值/最大/最小/中位数/标准差),标记异常价格,导出带图表的 Excel。所有提取结果可**溯源到文档原文位置**供人工核验。

### 1.2 关键约束(已与用户确认)

- **文档格式**:合同 **~100% 扫描件 PDF**(无文字层),少量 DOCX
- **表格特征**:**基本都带边框线** → 版面分析命中率高,漏检风险低
- **规模**:>1000 份合同,持续增量更新
- **隔离**:不碰 procurement-service(`cpa_` 前缀物理隔离)
- **存储**:合同原文存 MinIO 独立 bucket,不入 RAGFlow
- **可信度要求**:价格数据必须可溯源核验(扫描件 OCR 易错)

### 1.3 非目标(YAGNI)

- ❌ 不做合同条款语义合规审查
- ❌ 不做供应商信用评估
- ❌ 不直接生成 .docx(只产出 Excel)
- ❌ 不重写 procurement-service
- ❌ 不用 RAGFlow 做表格提取(RAGFlow 可保留作文档管理前端,但提取路径独立)
- ❌ 不做原生 PDF 的表格线分析路径(扫描件 100%,无 ROI)

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│  前端  frontend/src/extensions/contract-price/                    │
│  复用 ShellLayout + DashboardCard 风格(参照 /dashboard 个人工作台) │
│  文档管理 + 上传(MinIO) + 聚类审核 + 分项明细 + 溯源比对          │
│  溯源比对:点击 item → 拉 MinIO 预渲染 PNG → CSS 叠加 bbox 高亮    │
└──────────────────────────────┬───────────────────────────────────┘
                               │ REST (cookie-JWT)
┌──────────────────────────────▼───────────────────────────────────┐
│  后端扩展  backend/app/extensions/contract_price/  (gateway 内)    │
│  CRUD + upload/reparse/preview 端点 + 流水线编排 + OCR 服务调用    │
└──────────┬───────────────────────────────────┬────────────────────┘
           │                                   │ 直读
           ▼                                   ▼
┌──────────────────────────────────┐  ┌────────────────────────────┐
│  技能流水线编排 skills/.../scripts │  │  PostgreSQL postgres-ext    │
│  (轻量,不含 OCR 重依赖)            │  │  cpa_documents / cpa_items  │
│  ┌─────────────────────────────┐  │  │  cpa_clusters / cpa_runs    │
│  │ document_scanner            │  │  └────────────────────────────┘
│  │  MinIO list + SHA-256 增量   │  │
│  └────────────┬────────────────┘  │  ┌────────────────────────────┐
│  ┌────────────▼────────────────┐  │  │  MinIO (独立 bucket)        │
│  │ table_classifier +          │  └─▶│  - 合同原文 PDF/DOCX         │
│  │ price_validator             │     │  - 有表页预渲染 PNG          │
│  └────────────┬────────────────┘     └────────────────────────────┘
│  ┌────────────▼────────────────┐
│  │ clustering + stats + excel  │  ← 复用 v1,不改
│  └─────────────────────────────┘
└──────────────┬───────────────────────────────────────────────────┘
               │ HTTP (重计算隔离,不拖垮 gateway)
┌──────────────▼───────────────────────────────────────────────────┐
│  OCR 微服务  mcp-server/ocr-service/  ★ 独立 docker 容器      │
│  FastAPI: POST /ocr                                               │
│   入参:PDF/图像 (或 MinIO uri)                                     │
│   出参:结构化表[[{text,bbox,conf}]] + 页尺寸 + 预渲染 PNG bytes    │
│  依赖:rapid-layout + rapid-table + rapidocr-onnxruntime + pdf2image│
│  独立扩缩容 / 镜像与 gateway 解耦 / 升级引擎不影响主业务           │
└────────────────────────────────────────────────────────────────────┘
```

**复用比例 ~60%**:聚类、向量化、统计、Excel、DB、后端 CRUD 骨架、前端骨架全部保留。新增/替换的是数据入口(document_scanner/parser/classifier/validator)与溯源能力。

---

## 3. 数据模型

### 3.1 cpa_documents(从 RAGFlow 缓存 → 本地合同文件实体)

```python
class CpaDocument(Base):
    __tablename__ = "cpa_documents"
    # ── 文件来源 ──
    file_name:       str                # 原始文件名
    storage_uri:     str                # s3://<bucket>/<key> (MinIO 独立 bucket)
    file_hash:       str  (index)       # SHA-256,精确增量(替代 v1 拼凑指纹)
    file_type:       str                # pdf / docx
    quick_fp:        str                # name|mtime|size 快速预筛(省去读文件算哈希)
    # ── 业务字段 ──
    contract_no:     Optional[str]
    supplier:        Optional[str]      # 从首页/元数据提取,v1 未填,v2 补全
    sign_date:       Optional[date]
    # ── 解析结果 ──
    parse_mode:      str                # ocr / docx / failed
    parse_status:    str                # pending / parsed / failed / needs_review
    parse_meta:      Optional[dict]     # JSONB: {tables_found, goods_tables, rows_extracted, skipped_tables:[...], pages_ocr'd}
    error:           Optional[str]
    # ── 页面元数据(溯源用) ──
    page_count:      Optional[int]
    page_sizes:      Optional[list]     # 各页尺寸 [{w,h}],bbox 归一化基准
    # ── 审计 ──
    parsed_at:       Optional[datetime]
    created_at:      datetime
    updated_at:      datetime
    # 删除 v1: ragflow_doc_id (unique) — 不再依赖 RAGFlow
```

### 3.2 cpa_items(从纯提取行 → 带溯源 + 校验的可信行)

```python
class CpaItem(Base):
    __tablename__ = "cpa_items"
    # ── 提取内容 ──
    goods_name:   str
    spec_model:   Optional[str]
    tech_params:  Optional[dict]        # JSONB
    quantity:     Optional[float]
    unit:         Optional[str]
    unit_price:   Optional[float]
    # ── 溯源坐标(OCR 副产品) ──
    source_page:       Optional[int]    # 页码(1-based)
    source_bbox:       Optional[dict]   # JSONB {x,y,w,h} 归一化(0~1)
    source_table_idx:  Optional[int]    # 页内第几张表
    source_row_idx:    Optional[int]    # 表内行号
    # ── 校验状态(扫描件 OCR 必需) ──
    confidence:         Optional[float] # OCR 置信度 0~1
    validation_status:  str  (default="ok")  # ok / needs_review / corrected
    # ── 聚类 ──
    cluster_id:         Optional[UUID]
    is_outlier:         bool            # IQR 异常值
    # ── 审计 ──
    document_id:        UUID  (FK)      # v1 已有
    source_contract_no: Optional[str]
    edit_note:          Optional[str]
    created_at:         datetime
```

**关键不变量**:`source_page` 指向的页**必然存在预渲染图**(因为该 item 来自该页的表,而有表页必被预渲染存 MinIO)。这保证溯源比对永不悬空。

### 3.3 cpa_clusters / cpa_run_history

沿用 v1,不变。

---

## 4. 核心流水线

```
扫描件 PDF (MinIO)
    │
    ├─① document_scanner: MinIO list_objects + file_hash 比对
    │      只处理新增/内容变更的合同(精确增量)
    │
    ├─② document_parser: 流式下载到临时目录
    │      │
    │      ├─ 逐页版面分析(rapid-layout) → 跳过纯文字页
    │      ├─ 含表页: rapid-table 结构识别 + rapidocr 单元格 OCR
    │      │           (每张表天然带 bbox;每单元格带 confidence)
    │      └─ 有表页: 渲染 PNG 存 MinIO(prefix=previews/{doc_id}/page-{n}.png)
    │
    ├─③ table_classifier: 表头角色打分 → 货物分项表?付款计划表?验收表?
    │      goods_price(score≥0.7) → 进入管线
    │      其他 → 记入 parse_meta.skipped_tables,不静默丢弃
    │
    ├─④ price_validator: 价格单元格强校验
    │      非数字 / 量级异常 / 同表横向偏离 → validation_status=needs_review
    │      (needs_review 的 item 不进统计均值,先进审核队列)
    │
    ├─⑤ ParsedItem(带溯源坐标) → cluster_items(DBSCAN,复用 v1)
    │
    ├─⑥ compute_stats + IQR 异常值(复用 v1)
    │
    ├─⑦ generate_excel(复用 v1) + _persist(cpa_ 表)
    │
    └─⑧ run_history 记录 parse_meta(提取健康度报告)
```

---

## 5. 关键模块设计

### 5.1 MinIO 存储(独立 bucket)

- **配置**:`config.py` 加 `cpa_minio_bucket`(默认 `cpa-contracts`),复用现有 `minio_endpoint/access_key/secret/secure`
- **复用方式**:不直接用 `knowledge/storage.py` 的 `MinioStorageProvider`(它绑定单 bucket + knowledge 路径模板),而是 contract-price 持有自己的轻量 client,共享连接配置
  - 可选优化:给 `StorageProvider` 抽象加通用 `put_bytes(bucket, key, data)` / `get(bucket, key)` 方法,所有扩展共享 — 第一版可暂不做,先在 contract-price 内自管
- **object key 规范**:
  - 原文:`{doc_id}/{filename}`
  - 预渲染图:`previews/{doc_id}/page-{n}.png`
- **下载策略**:管线处理时流式下载到临时目录,OCR 完即删,不占容器磁盘

### 5.2 扫描件 OCR 微服务(独立 docker 容器)★

**部署形态**:OCR 作为独立服务 **eai-flow-ocr**(目录 `mcp-server/ocr-service/`,容器 `eai-flow-ocr`),**不进 gateway**。
- 理由:OCR 是 CPU/内存密集型重计算,混进 gateway 会拖垮核心 API 响应;rapidocr + ONNX 模型文件会让 gateway 镜像膨胀数百 MB;独立容器可独立扩缩容、单独升级引擎、崩溃隔离
- 参照项目已有模式:`mcp-server/ocr-service/`,与 `cad-mcp`、`text-to-cad-mcp`(8004) 同级
- 接口:FastAPI,`POST /ocr`
  - 入参:`{minio_uri}`(推荐,服务端从 MinIO 拉)或 multipart 文件
  - 出参:`{pages: [{page_no, page_size, tables: [[{text, bbox, confidence}]], preview_png_b64}]}`
- 调用方:gateway 扩展 / 技能编排通过 httpx 调用,**不直接 import OCR 依赖**

**服务内技术栈**:RapidOCR 全家桶(`rapid-layout` + `rapid-table` + `rapidocr-onnxruntime`) + `pdf2image`(页转图)
- 理由:ONNX runtime,无 paddlepaddle 重依赖;中文模型继承 PaddleOCR 质量;CPU 可用
- 硬性筛选条件:**必须输出 bbox**(溯源依赖),RapidOCR/PaddleOCR 均满足
- 可切换:服务内部抽象掉引擎,GPU 大规模场景可换 PaddleOCR GPU(对调用方透明)

**分层处理**(服务内,不全量 OCR):
```
每页 → rapid-layout 版面分析
   ├─ 纯文字页(合同正文条款) → 跳过,不 OCR,不生成预渲染
   └─ 含表页 → rapid-table 结构识别 + rapidocr 单元格 OCR + 渲染 PNG
                (省 80%+ 时间,正文页不付出 OCR 成本)
```

**⚠️ 命中率验证(实施前置,见 §8.1)**:表格带边线提高了命中预期,但价格 OCR 错误率未经验证。必须用真实扫描件先跑准确率验证。Phase 0 验证脚本直接对 OCR 服务跑。

**Phase 0 真实合同验证结果(2026-06-26,真实盖章分包合同 137 页)**:cv2 线检测方案**不通过**,触发本节预案:
- ✅ OCR 文字识别优秀(置信度 0.985,中文准确)— RapidOCR 文字层保留
- ❌ 表格检测失败:134 张表绝大多数是误检的**合同多栏正文**(几乎全是 3 列,真分项价格表应 7-10 列);"单价"仅命中 1 次、"合价/金额" 0 次 → 真正的分项价格表未识别到;行列重建错乱(条款碎片混项目名)
- 根因:合同正文是多栏排版,cv2 无法区分"分栏正文线" vs "真表格线"
- **决策:cv2 表格定位/结构识别层废弃,升级到深度学习表格识别(PP-Structure 版面分析区分表格/文字区域 + rapid-table 结构识别),重验**。RapidOCR 文字识别层保留,只换表格定位+结构层(`OcrEngine` 接口不变,调用方无感)
- **Phase 0 最终验证通过(2026-06-26)**:实际采用 `rapid-layout`(cdla 版面分析,区分 table/text 区域,排除多栏正文误检)+ `rapid-table`(slanet-plus 结构识别,输出 HTML)+ `rapidocr-onnxruntime`。重验同一份 137 页合同:91 张表(误检大幅减少),**成功识别完整"工程量清单计价表"**(页94,11 列:序号/项目名称/单位/工程量/不含税单价/不含税合价/税率/税金/含税单价/含税合价;如"平整场地 m2 824.79 单价1.20 合价989.75 9% 含税合价1078.83"),清单主体在 25–59 页连续多页。**正面回答最初疑虑:能从合同扫描件提取完整分项价格表**(只是不走 RAGFlow)。剩余 Phase 1 后处理优化:复杂多行合并表头错位、个别数字粘连(工程量+单价粘连)需分割/表头规范化。

### 5.3 表类型判定(table_classifier.py)

打分机制,不用硬编码 if-else:

```python
ROLE_TOKENS = {
    "name":  ["货物名称","设备名称","物资名称","材料名称","产品名称","项目名称","名称","品名"],
    "spec":  ["规格型号","规格","型号","技术参数","参数","图号"],
    "qty":   ["数量","工程量"],
    "unit":  ["单位","计量单位"],
    "price": ["单价","合价","金额","总价","小计","综合单价","不含税单价"],
    "date":  ["日期","付款节点"],     # 付款计划表特征
    "std":   ["标准","规范","验收"],    # 验收标准表特征
}

# 货物分项表强信号:同时有 name + price,再加 qty 或 spec → score ≥ 0.7
# payment_schedule / acceptance_criteria → 排除并记录
# score < 0.7 → unclassified → 进人工审核队列(不静默丢弃)
```

阈值 0.7 需用真实合同校准。第一版所有表都记进 `parse_meta`(含 unclassified),人工抽查后调阈值。

### 5.4 价格强校验(price_validator.py)

扫描件 OCR 特有风险:价格数字错一个字符值就完全错,且错误结果看似合理。**不可省的校验:**

```python
def validate_price(raw, row_context) -> PriceCheck:
    cleaned = re.sub(r"[,，\s元]", "", raw)
    if not cleaned.isdigit():              # 含字母/全角 → OCR 误识
        return needs_review("含非数字字符")
    val = int(cleaned)
    if val < 10:                            # 疑似漏位/多位
        return needs_review("量级异常")
    # 同表同列横向比对:偏离同表均价 >5x → 标记复核
    if row_context.median and val > row_context.median * 5:
        return needs_review("偏离同表均值")
    return ok()
```

`needs_review` 的 item 不进统计均值,进人工审核队列。**这是扫描件场景数据可信度的底线。**

### 5.5 溯源比对(预渲染图路径)

**后端**:
- OCR 时把每张识别到的表所在页渲染成 PNG 存 MinIO(`previews/{doc_id}/page-{n}.png`)
- bbox 归一化为 0~1 比例(基于 page_sizes),与分辨率无关
- 新增端点:`GET /documents/{id}/preview/{page}` → 代理返回 MinIO PNG(带 cookie-JWT 鉴权)

**前端**:
- item 列表每行加"溯源"按钮 → 抽屉展示
- 抽屉内:`<img src=预渲染PNG>` + 绝对定位的 `<div>` 叠加在 bbox 位置画红框高亮该单元格
- 秒级响应(预渲染图 OCR 时已生成)

**与校验的闭环**:needs_review 的 item → 审核员点溯源 → 看原文位置 → 肉眼判断价格 OCR 是否对 → 确认/修正 → 进统计。**没有溯源,needs_review 形同虚设;有了它,OCR 错误才可控。**

### 5.6 前端 UI 基准(参照 /dashboard 个人工作台)

contract-price 所有页面**复用个人工作台的视觉语言**,不做独立设计。已从 `frontend/src/extensions/dashboard/` 提取关键风格 token:

**布局骨架(直接复用)**:
- `ShellLayout`(`extensions/shell/`)作外层 — 与 dashboard 同一外壳(侧栏 + 主区)
- 主区:`max-w-7xl mx-auto` + `lg:grid-cols-12` 栅格,`gap-6`,左 7 右 5 或全宽分布
- 背景:`cyber-grid` + 双色环境光晕(`bg-purple-500/5` + `bg-blue-500/5`,`blur-[120px]`)

**卡片组件(复用 `DashboardCard` 或同构)**:
- `rounded-xl border border-border bg-card shadow-sm`
- header:7x7 `rounded-lg border` 图标盒 + `text-sm font-semibold` 标题 + badge + action
- 右上角小三角装饰 `w-3 h-3 bg-blue-500/10 border-r border-t`

**统计卡(复用 `StatsPanel` 模式)**:
- `rounded-xl border p-4 bg-card`,`hover:-translate-y-0.5 hover:shadow-md`
- 图标 `h-10 w-10 rounded-lg border bg-background`
- 数字 `text-2xl font-extrabold`,标签 `text-xs`,副标 `text-[10px] uppercase tracking-wider`
- **语义配色**(contract-price 映射):
  - 蓝 `blue-500/20` → 合同总数
  - 琥珀 `amber-500/20` → 待审核聚类
  - 紫色 `violet-500/20` → needs_review 分项
  - 玫红 `rose-500/20` → 异常价格/提取失败

**字体与配色 token**:
- `font-cyber`(等宽科技字)用于英文副标/装饰
- CSS 变量:`--db-bg-tertiary`、`--db-border-color-muted`、`db-text-primary`、`db-text-subtle`
- 页脚:`border-t bg-[var(--db-bg-tertiary)] font-cyber tracking-widest text-[10px]`

**溯源比对抽屉(`TracebackDrawer.tsx`)**:
- 复用 `db-card` 卡片样式
- 内部:`<img>` 预渲染 PNG + 绝对定位 `<div>` 叠加 bbox(`border-2 border-rose-500` 高亮框)
- 配合 `needs_review` 审核队列,形成 §5.5 闭环

**实现约束**:不引入新设计系统;若 `dashboard.css` / `db-*` token 不够用,优先扩展而非另立。

---

## 6. 失败模式与观测性(zero silent failures)

| # | 失败场景 | 处理 | 可见性 |
|---|---------|------|--------|
| 1 | 文件损坏/加密 PDF | parse_status=failed,error 记录 | run_history.error + documents 列表标红 |
| 2 | 版面分析 0 张表 | parse_status=needs_review,"疑似无表/需人工" | documents 列表标黄 |
| 3 | OCR 置信度低 | item.confidence + validation_status=needs_review | items 列表过滤 needs_review |
| 4 | 价格含非数字/量级异常 | price_validator 标 needs_review | 同上 |
| 5 | 合并单元格 | python-docx 原生;rapid-table 输出 spanning | 表格结构识别内置 |
| 6 | 表头无法识别角色 | unclassified 进审核队列 | parse_meta.skipped_tables |
| 7 | 单份合同 OCR 崩溃 | 错误隔离,逐份记录,不中断整批 | run_history 逐 doc 状态 |

**观测性**:`cpa_documents.parse_meta`(JSONB)记录每份合同的提取健康度 — {tables_found, goods_tables, rows_extracted, skipped_tables, pages_ocr'd, low_confidence_count}。dashboard 展示"提取健康度",异常合同一眼可见。

**长任务**:扫描件 OCR 让单次管线从秒级到分钟级(>1000 份合同)。必须补:
- 进度可见:管线写进度到 DB(已处理合同/页数),前端轮询
- 断点续跑:file_hash 增量保证 OCR 过的合同不重跑
- 子进程监督:v1 的 fire-and-forget 子进程在长任务下是硬伤,需加超时/心跳/崩溃重试

---

## 7. 改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/config.py` | 改 | 删 RAGFLOW_*,加 `cpa_minio_bucket` / `contracts_prefix` |
| `scripts/models.py` | 改 | CpaDocument/CpaItem 扩字段(见 §3) |
| `scripts/document_scanner.py` | **新增** | MinIO list + SHA-256 增量 |
| `scripts/document_parser.py` | **新增** | OCR 服务 HTTP client(编排:下载→调 /ocr→收结构化表),**不含 OCR 重依赖** |
| `scripts/table_classifier.py` | **新增** | 表头打分判定 |
| `scripts/price_validator.py` | **新增** | 价格强校验 |
| `scripts/storage.py` | **新增** | contract-price 专属 MinIO client(共享连接配置) |
| `scripts/parser/__init__.py` | 改 | `parse_table_rows()` 从结构化行映射(取代 Markdown) |
| `scripts/parser/*.py` | **删除** | ragflow_client.py + table/list/mixed_parser |
| `scripts/cli.py` | 改 | run_pipeline 主流程重写(scan→parse→classify→validate→cluster→excel) |
| `scripts/clustering/*` | 不动 | 输入与来源无关 |
| `scripts/stats.py` / `excel_generator.py` | 不动 | 复用 |
| `scripts/requirements.txt` | 改 | 加 python-docx、minio、httpx(调 OCR 服务);删 RAGFlow;**OCR 重依赖移到 ocr-service** |
| `mcp-server/ocr-service/` | **新增** | ★ 独立 OCR docker 服务:FastAPI `POST /ocr` + rapid-layout + rapid-table + rapidocr-onnxruntime + pdf2image + Dockerfile + 独立 requirements |
| `docker/docker-compose.*.yaml` | 改 | 加 ocr-service 容器定义(参考 text-to-cad-mcp 模式) |
| `backend/contract_price/models.py` | 改 | 同步字段(两处模型必须一致) |
| `backend/contract_price/routers.py` | 改 | +upload +reparse +preview 代理 |
| `backend/contract_price/crud.py` | 改 | MinIO 上传保存 |
| `frontend/.../components/DocumentsView.tsx` | 改 | +上传(MinIO 直传) +文档管理 |
| `frontend/.../components/TracebackDrawer.tsx` | **新增** | 溯源比对抽屉(PNG + bbox 叠加) |
| `tests/*` | 改/新增 | 替换 ragflow 测试为 parser/classifier/validator 测试 |

---

## 8. 实施阶段

### 8.1 Phase 0 — OCR 服务骨架 + 命中率验证(前置)⭐

**最高优先级,消除最大不确定性。**

1. 搭建 `ocr-service` 最小骨架(FastAPI `POST /ocr` + rapid-layout + rapid-table + rapidocr-onnxruntime + pdf2image + Dockerfile),独立容器跑通
2. 用 2-3 份真实扫描件合同对服务跑验证,输出:
   - 版面分析:识别到几张表?漏检率?
   - 表格识别:行列结构准确率?
   - 价格 OCR:数字识别准确率?(对照人工标注)
   - 置信度分布:needs_review 阈值定多少合理?
   - bbox 输出:溯源坐标是否可用?

**验证通过才进 Phase 1**,否则调整引擎/参数。避免对 >1000 份合同返工。

### 8.2 Phase 1 — 数据入口替换(CC ~3-4 小时)
- document_scanner(MinIO + SHA-256 增量)
- document_parser(HTTP client 调用 ocr-service)
- table_classifier + price_validator
- 删除 RAGFlow 依赖
- cpa_ 表字段迁移(两处模型同步)

### 8.3 Phase 2 — 存储与溯源(CC ~2-3 小时)
- MinIO 独立 bucket 接入
- 预渲染有表页 PNG 存 MinIO
- 后端 upload/reparse/preview 端点

### 8.4 Phase 3 — 前端(CC ~3-4 小时)
- 文档管理 + 上传
- 溯源比对抽屉(PNG + bbox 叠加)
- needs_review 审核队列 UI

### 8.5 Phase 4 — 运维加固(CC ~2-3 小时)
- 长任务进度可见 + 断点续跑
- 子进程监督(超时/心跳/重试)
- 提取健康度 dashboard

---

## 9. 开放问题/风险

1. **价格 OCR 准确率**:Phase 0 验证的核心指标。若 <95%,需引入校对模型或加重人工审核权重。
2. **MinIO 直传 vs 代理上传**:大文件(扫描件几十 MB)前端直传 MinIO(presigned URL)省 gateway 带宽,但需暴露 MinIO 端口;代理上传简单但走 gateway。第一版可代理,量大改直传。
3. **OCR 并发策略**:单份合同页级并发(快,内存压力)vs 多份合同并发(资源可控),取决于批量规模,Phase 4 定。
4. **RAGFlow 去留**:v2 不依赖 RAGFlow 提取。若已有 RAGFlow 部署用于其他用途可保留;若仅为此模块部署,可在 Phase 4 后评估下线以减负。
5. **扫描件 PDF.js 兜底**:预渲染图方案下,纯文字页无图无法回溯。但合同正文不含价格,溯源需求集中在有表页,可接受。

---

## 10. 验收标准

- [ ] 真实扫描件合同:版面分析 + 表格识别 + 价格 OCR,价格准确率 ≥95%(Phase 0 验证)
- [ ] 文档上传存 MinIO 独立 bucket,SHA-256 精确增量(改名不重解析)
- [ ] 表类型判定:货物分项表正确提取,付款/验收表排除并记录
- [ ] 价格校验:异常/低置信度 item 标 needs_review,不进统计均值
- [ ] 溯源比对:任意 item 一键定位到原文页 + bbox 高亮
- [ ] 提取健康度:每份合同的 parse_meta 可查,异常合同可见
- [ ] 复用 v1:聚类/统计/Excel/审核流程不回归
