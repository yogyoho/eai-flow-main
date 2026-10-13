# 合同价格分析 v3 设计：合同文件库 + 货物分类术语 + OCR 服务接入

- 日期：2026-10-14
- 状态：APPROVED（brainstorming 定稿，待实施计划）
- 范围：`backend/app/extensions/contract_price/`、`frontend/src/extensions/contract-price/`、`skills/public/contract-price-analysis/`、`/settings` 基础配置页、`config/permissions.yaml`
- 前置事实（2026-10-13/14 代码查证）：现状梳理见 §8 附录

## 0. 总原则与安全边界

1. **管线核心零改动**：扫描→OCR→提取→校验→入库→聚类引擎（DBSCAN / vectorizer / `_apply_merge_pins`）不改动行为，新能力全部长在旁边的表 / 前缀 / 配置键上。这是"不能影响已实现的货物与含税单价提取"的结构保证。
2. **config.yaml 一行不碰**（用户硬性要求：避免上游 deerflow 升级冲突）。所有新配置落扩展层：
   - `system_config` KV 表（DB，`/api/extensions/config` 既有通道）
   - cpa 扩展 `config.json`
   - 新 `cpa_` 表
   - `config/permissions.yaml`（角色权限配置，非 config.yaml；`config/` 与 `deploy/offline/config/` 两处同步）
3. **三个工作段各自独立可交付**，M1/M2 无交集可并行。

## 1. M1 合同文件库 tab（`cpa:page:library`）

### 1.1 定位（已与用户确认）

纯档案管理，与解析管线解耦：上传不自动解析，"加入解析"是显式动作；已解析文件可查其分项清单（只读）。现有"合同解析" tab 的上传/解析流程保留不动。

### 1.2 数据模型（2 张新表，镜像 `tlt_folders` 模式）

```
cpa_library_folders:
  id UUID PK, parent_id UUID NULL (self FK), name varchar(255), created_at

cpa_library_files:
  id UUID PK, folder_id UUID FK→cpa_library_folders,
  file_name varchar(300), storage_key varchar(512),
  file_hash varchar(128) idx,   -- SHA-256
  file_size bigint, file_type varchar(20),  -- pdf/docx
  uploaded_at timestamptz
```

- 物理存储：**同 bucket `cpa-contracts`，key 前缀 `library/`**。管线唯一改动 = `document_scanner.py` 跳过 `library/` 前缀（一行）。
- 上传幂等：同文件夹同 hash → 提示"已存在，复用"（同翻译资产库 reused 模式）。
- 文件夹上传：`webkitdirectory` input，按 `webkitRelativePath` 在目标文件夹下自动建子文件夹。

### 1.3 API（`/api/extensions/contract-price/library/*`）

| 端点 | 说明 |
|---|---|
| `GET /folders` | 树列表 |
| `POST /folders` | 新建（name + parent_id） |
| `PATCH /folders/{id}` | 重命名 / 移动 |
| `DELETE /folders/{id}` | 仅允许空文件夹（非空返回 409 与明确提示） |
| `GET /files?folder_id=` | 列表，含解析状态徽标：按 file_hash 匹配 `cpa_documents` → 未解析 / 已解析 / 解析失败 |
| `POST /files/upload` | multipart 多文件（含 webkitdirectory），仅接受 `.pdf/.docx`（同现有 upload 校验）；返回逐文件结果（reused=同文件夹同 hash 幂等复用——档案库允许同一合同存多个文件夹，不拒绝） |
| `GET /files/{id}/content` | 流式：PDF `inline` 内嵌预览；docx `attachment` 下载 |
| `GET /files/{id}/items` | 按 hash 匹配已解析文档 → 只读分项清单。`crud.list_items` 加 `document_id` 筛选参数（小增量，现状只有 goods_name/source_contract_no/cluster_id/run_id） |
| `POST /files/{id}/analyze` | **加入解析**，语义对齐现有 `documents/upload`：① hash 命中 `cpa_documents` → 直接返回该 doc_id（"已解析"，不拷贝）；② 同名不同内容已存在于扫描区 → 409（防统计污染，同 upload 拒重逻辑）；③ 否则 MinIO 服务端拷贝 `library/...` → 扫描区根 key（`{file_name}`）+ 建 pending 文档行（同 upload），下一轮解析自动拾取 |

权限：沿用 cpa 模块现有路由权限模式（`require_permission("system:access")`）。

### 1.4 UI（`LibraryView.tsx`，仿翻译资产库 `AssetLibrary` 布局）

- 左侧文件夹树：新建 / 重命名 / 删除 / 菜单移动（v1 不做拖拽）。
- 右侧文件表格：名称 / 大小 / 上传时间 / 解析状态 / 操作菜单（查阅·下载·移动·删除·加入解析·查看清单）。
- 查看清单 = 抽屉列出该合同 items（品名/规格/数量/含税单价），带"去分项校验"链接。
- 布局挂 `/contract-price/library` 子路由，`layout.tsx` navItems 加条目（`canPage` 过滤，fail-open 同现有）。

### 1.5 权限点

`cpa:page:library` 加入 `config/permissions.yaml` + `deploy/offline/config/permissions.yaml`。

## 2. M2 货物分类术语 tab（`cpa:page:terms`）

### 2.1 定位（已确认）

把隐形的 merge_pins 升级为人工可管理的术语表；生效方式 = **强制同簇（pin 语义）**，聚类引擎 `_apply_merge_pins` 零改动。

### 2.2 数据模型

```
cpa_terms:
  id UUID PK, canonical varchar(300),
  aliases JSONB (list[str]),
  enabled bool default true,
  source varchar(20),   -- manual | auto_merge
  created_at, updated_at
```

v1 不做 category 列（YAGNI：簇锚定靠 canonical+aliases 已达成；确需分类标注再加列）。

### 2.3 生效机制

- CLI cluster 相位：`pins = [cpa_terms(enabled) → {name: canonical, aliases}]` ∪ 旧 `config.json merge_pins`（过渡期兼容读取，防已有先验丢失）→ 喂给现有 `_apply_merge_pins`。
- 名称比对沿用引擎现有归一化（去空白）。
- **手动合并簇的自动捕获改写目标**：`crud._capture_merge_pin` 从写 config.json 改为 upsert `cpa_terms(source=auto_merge)`——命中已有 canonical（归一化比对）则并 aliases，否则新建。不再产生双源。
- 生效时机：下次"聚类分析"。**解析相位不消费术语**，提取结果不受影响。

### 2.4 API + UI

- `GET/POST/PATCH/DELETE /api/extensions/contract-price/terms`。
- `TermsView.tsx`：规范名 | 别名 chips（计数） | 来源徽标（手动/自动合并） | 启用开关 | 操作；新建/编辑抽屉（canonical + 别名多值输入）。v1 不做导入导出。
- 挂 `/contract-price/terms` 子路由 + navItems 条目。

### 2.5 权限点

`cpa:page:terms`，同 §1.5 两处 permissions.yaml。

## 3. M3 OCR 服务接入

### 3.1 形态定调（已确认）：前端替代，非独立分支

专业 OCR 是**同一根管线上的可插拔 OCR 前端**，不是旁路第二条提取管线：

```
扫描 → [OCR 前端: builtin | 专业OCR] → 表格分类 → seed定位 → 行提取 → 价格校验 → 入库(同一套 cpa_ 表) → 聚类
              ↑ 唯一可换段
```

不做独立分支的理由：下游逻辑（分类/seed/校验/聚类消费）会被迫复制两份；items 裂成两个真相源污染聚类与统计；每份合同双份 OCR 成本。对比需求由验收期双跑脚本满足（§3.6），不是生产路径。

### 3.2 系统配置页 `/settings` 基础配置

- **删 reranker**（已证实后端零消费者）：UI 块 + `SystemConfig.reranker` + `ModelChoicesResponse.rerankers` + `_load_reranker_choices()` 全部移除；KV 旧键无害残留不清理。
- **新增「OCR 服务」卡片**（原 reranker 位置，管理员可见/可写）：
  - 服务列表 `[{name, base_url, api_key, model}]`，协议固定 `openai-vision`（OpenAI 兼容 vision chat——dots.ocr / DeepSeek-OCR / Qwen-VL / GLM-4V 等均可经 vLLM/网关以该协议暴露，一套适配器接一片）。
  - api_key **write-only 掩码回显**（沿用 cpa `LLM_KEY_MASK` + `resolve_llm_key_mask` 既有模式）。
  - 「测试连接」按钮：`POST /api/extensions/settings/ocr/validate`，发 1×1 图 ping（镜像现有 `models/validate` 模式）。
- 存储：`system_config` KV 新键 `ocr_services`（JSON 字符串）；`SystemConfig` 加 `ocr_services` 字段。**读=登录用户（key 掩码）**——cpa 设置 tab 下拉需要服务名列表；**写=admin**。
- 不碰 config.yaml，不新增容器/部署物。

### 3.3 cpa 模块选择 OCR（设置 tab）

- cpa `config.json` 加 `ocr_provider: str | null`（空 / `"builtin"` = 内建 eai-flow-ocr；其它值 = ocr_services 中的服务名）。
- `SettingsView` 加「OCR 提取引擎」下拉（内建 + 服务名列表，来自 `/api/extensions/config` 只读）+ 文案："仅影响之后的解析与强制重 OCR，历史文档不受影响"。
- `service.py` 加 `_resolve_ocr_args()`（镜像 `_resolve_llm_args` 模式）：选中外部服务 → 读 system_config → 子进程 argv 注入 `--ocr-backend openai-vision --ocr-base-url <url> --ocr-key <key> --ocr-model <model>`；服务已删除 / key 为掩码未解析 → **回退内建 + warning log**。未选外部服务时 argv 与今天逐字节一致。

### 3.4 管线适配层（skill 侧唯一实质改动）

- `document_parser.parse_document` 按 backend 分派：
  - **builtin**：现有 httpx 调 eai-flow-ocr，代码路径不变。
  - **openai-vision**：pymupdf 光栅化页 PNG（skill `requirements.txt` 加 `pymupdf`，后端已有同依赖）→ `chat.completions`（页 PNG data URL + 表格抽取 prompt，约定输出 HTML 表格）→ 解析为同一 `TableExtract`（**cell bbox=None**，页码保留）。
- **OCR 缓存分键**：builtin 保持 `ocr/{sha256}.json`（历史缓存全部有效，不触发全量重 OCR）；外部 provider `ocr/x-{provider名}/{sha256}.json`（防缓存污染）。
- `parse_mode` 新值 `ocr_llm`（已证实纯展示，无行为分支消费）；`parse_meta` 记 `ocr_provider` / `ocr_model` 供审计。
- 溯源降级：bbox=None → `TracebackDrawer` 显示页图不画框（已验证现成支持：`hasBox = !!bbox && bbox.length === 4`）。
- **单文档重解析 provider 覆盖**：reparse 端点加可选 `ocr_provider` 参数（默认取模块配置）——按文档粒度的临时切换/对比/回退能力。

### 3.5 不影响现有提取的六重保证（风险分析，用户明确要求）

| # | 保证 | 机制 |
|---|---|---|
| 1 | 默认零变化 | 不配置不选 → 子进程 argv 与今天逐字节一致 |
| 2 | 缓存不串 | provider 分键；切回内建秒级命中历史缓存 |
| 3 | 提取层解耦 | table_classifier / seed / price_validator / llm_fallback 只消费 TableExtract 契约，不感知 OCR 后端 |
| 4 | 安全网仍在 | LLM OCR 表格结构不合格 → 现有 seed 定位 / 评分门 / needs_review 兜底继续生效，不阻塞 |
| 5 | 验收基准 | 选 3–5 份代表性历史合同 builtin vs openai-vision 双跑，items 对比脚本（数量+值 diff，一次性放 skill tests/）；差异大则该服务标记不推荐并记录 |
| 6 | 失败隔离 | 外部 OCR 失败 → 该文档 parse_status=failed（现有 `mark_stale_parsing_failed` 机制），不波及其它文档 |

## 4. 实施切分

- **M1 文件库**：表 + API + scanner 跳过 + UI（独立交付）。
- **M2 术语**：表 + API + CLI 接线 + capture 改写 + UI（独立交付，与 M1 可并行）。
- **M3 OCR**：settings 卡片 + reranker 移除 → cpa 选择 → 适配层 → 双跑验收（3.1 先行）。

## 5. 测试

- 后端 pytest：
  - library：folders/files CRUD、上传幂等（hash 复用）、analyze 拷贝与"已解析"短路、`list_items(document_id=…)`。
  - terms：CRUD、`_capture_merge_pin` upsert 改写、CLI pins 合并逻辑（terms ∪ legacy merge_pins，纯函数部分）。
  - OCR：`_resolve_ocr_args` 优先级/掩码/回退（镜像 `_resolve_llm_args` 既有测试模式）；缓存分键纯函数；HTML→TableExtract 解析（纯函数）。
- 前端 vitest：沿用 `tests/unit/extensions/contract-price/` 既有模式（新 tab 组件纯逻辑部分）。
- 手工验收：文件库上传→查阅→加入解析→清单查阅全链路；双跑对比报告；reranker 移除后 `/settings` 基础配置回归。

## 6. 明确不做（v1 YAGNI）

- 术语导入导出、术语 category 列。
- 文件库拖拽移动、跨分支维度筛选（自由树方案已确认牺牲此能力）。
- 文件库内批量"加入解析"（逐文件动作够用，量大再加）。
- 专业 OCR 的原生 HTTP 协议适配器（PaddleOCR-VL serving 等）——先验证 openai-vision 统一协议，真实需求出现再补。
- OCR 服务注册表独立表——`system_config` KV JSON 足够（单管理员低频配置）。

## 7. 澄清决策记录（brainstorming 结论）

| 问题 | 结论 |
|---|---|
| 文件库与"合同解析" tab 关系 | 解耦：纯档案库，"加入解析"显式动作，两套入口并存 |
| 维度组织 | 自由文件夹树（tlt_folders 模式），年份/业务类型只是命名习惯 |
| 术语生效方式 | 强制同簇（pin 语义，引擎零改动） |
| 专业 OCR 接入形态 | 不进产品部署，url+key 外部接入（同 LLM 接入模式） |
| 接入协议 | OpenAI 兼容 vision chat 统一协议（一套适配器接多种服务） |
| 配置页位置 | `/settings` 基础配置 tab，reranker 位置替换（reranker 已证实为死配置） |
| config.yaml | 一行不碰（上游升级冲突风险） |
| 专业 OCR 与现有 OCR 关系 | 替代关系（OCR 前端可插拔）+ 单文档重解析 provider 覆盖；非独立提取分支 |

## 8. 附录：现状梳理（2026-10-13/14 查证）

- 前端 `/contract-price` 6 tab（总览/合同解析/分项校验/分组审核/任务中心/配置），权限点 `cpa:page:*` 经 `canPage` 过滤。
- 后端扩展 `backend/app/extensions/contract_price/`：`cpa_documents`（MinIO storage_uri + SHA-256 增量 + parse_meta + preview_prefix）、`cpa_items`（goods_name/spec/unit_price 含税/price_untaxed/source_page/source_bbox 溯源）、`cpa_clusters`、`cpa_run_history`。
- 管线 `skills/public/contract-price-analysis/`：gateway subprocess 触发 `python -m scripts.cli`；`document_scanner.py` 全桶扫描（仅跳 `previews/`）；`document_parser.py` httpx 调 eai-flow-ocr（rapid-layout+rapid-table+rapidocr），OCR 结果按 `ocr/{sha256}.json` 内容寻址缓存，`re_ocr` 强制重跑；`llm_fallback.py` 已有 needs_review 表格 LLM 兜底（`_resolve_llm_args` 注入三元组）。
- 聚类：char n-gram TF-IDF + DBSCAN + 规格/分类门限 + `_apply_merge_pins` 合并先验（config.json merge_pins，手动合并自动捕获，union-find 重放）。
- `/settings` 基础配置读写 `/api/extensions/config`（`system_config` KV 表）；`SystemConfig.reranker` 全后端零消费者；`ModelChoicesResponse.rerankers` 来自 env `RERANKER_NAMES` 硬编码兜底。
- config.yaml 无任何 OCR/reranker 配置；OCR 唯一配置为 env `OCR_SERVICE_URL`（docker compose 注入）。
- 参照物：翻译资产库 `tlt_folders` 虚拟树 + `AssetLibrary.tsx`（树/上传/预览/下载/移除/幂等复用）。
