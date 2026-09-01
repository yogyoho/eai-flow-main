# 地质勘查报告样例库（geo-sample-bank）设计：几百份真实报告的资产化与四类价值榨取

> 现状：geological-report 技能由单一东川铜矿样例定制（references/samples/ = source.md + exploration/ch1..ch10_sample.md）；实际手持几百份不同矿种/阶段的固体矿产勘查报告电子版（未脱敏）。本设计回答：这些样例的价值在哪里、如何存储、如何加工、如何在写作时被消费——且全程不破坏技能已定的「运行时零检索服务、扩展=数据问题」哲学。

## 0. 需求澄清结论（2026-09-01 会话定案）

| 问题 | 结论 |
|---|---|
| 样例形态 | 电子版为主（docx/pdf），**未脱敏** |
| 价值优先级 | **四类全要**：①深度基线标定 ②范文范式库 ③矿种知识包孵化 ④合规/缺陷知识扩容 |
| 原始件存储 | MinIO（与 RAGFlow 底层 ragflow-minio 同源）；仿 contract_price 定制**样例管理扩展模块** |
| 脱敏闸门 | **自动规则脱敏 + 人工抽审**，通过后才分发（RAGFlow/repo）；与技能脱敏红线（`****` 槽位）同构 |

## 1. 方案比选与定案

| 方案 | 内容 | 结论 |
|---|---|---|
| **A 编译器模型（定案）** | 平台模块管资产生命周期（上传/解析/脱敏/审核），技能层确定性 CLI 把 reviewed 样例**编译**为 repo 衍生物；运行时只消费 repo 衍生物，RAGFlow 为辅助语义通道 | ✅ 顺「运行时零检索服务」哲学；四类价值共用一条管线 |
| B 全进 RAGFlow 运行时检索 | repo 不放衍生物 | ❌ 违背三条已定决策：N18 实测检索 chunk 保不住同节号范式；SL3 需确定性指纹池；calibrate 需全文件统计 |
| C 手工精选 10-20 份入 repo | 不建模块 | ❌ 浪费资产、矿种覆盖窄 |

LLM 使用边界（贯穿）：切片/指纹/统计/基线全部**纯脚本**；仅矿种包草稿抽取、缺陷识别用 LLM 批跑，产物一律过人工审核 gate 才入库。

## 2. 分层存储模型（L0-L3）

```
MinIO bucket「geo-samples」（懒建，同 cpa-contracts 模式，env GSB_MINIO_*，默认 ragflow-minio:9000）
├─ raw/<report_id>/<原文件>.docx|pdf      ← L0 未脱敏原文：永不进 repo、不下发 RAGFlow、不进沙箱
├─ clean/<report_id>/source.md            ← L1 脱敏全文（仅 status=reviewed 后产出/可见）
└─ clean/<report_id>/previews/pN.png      ← 页面预览（抽审 UI 对照用）

extensions PG（agentflow 库）gsb_ 表族     ← L2 元数据与状态机
├─ gsb_documents   元数据+状态+storage_uri+file_hash
├─ gsb_redactions  脱敏事件流水（规则名/位置/原文 hash——不落明文）
└─ gsb_run_history 解析/编译运行记录（同 cpa_run_history 模式）

skills/public/geological-report/references/…  ← L3 repo 衍生物（运行时唯一依赖，脱敏 by construction）
```

### gsb_documents 核心字段

| 字段 | 取值 | 说明 |
|---|---|---|
| report_id | slug | 全链路主键（MinIO 前缀 / repo 目录名 / RAGFlow 文件名共用） |
| file_hash | SHA-256 | 上传去重（409，同 contract_price 双层去重第一层） |
| stage | survey/detail/exploration | 对齐 stages/ 三文件 |
| mineral | copper/coal/gold/iron/lead_zinc/… | 词表与 ore_packs/ 文件名对齐——四类价值联动的轴 |
| year / region | 可空 | 选优与检索辅助 |
| status | uploaded→parsed→redacted→**reviewed**→compiled | 仅 reviewed 可分发；compiled=衍生物已进 repo |
| parse_mode | docx / pdf_text / pdf_ocr / failed | docx→python-docx；文字版 pdf→pymupdf4llm；稀疏判定扫描→eai-flow-ocr |
| redaction_report | 替换计数+规则命中清单 | 抽审审核面（审「漏脱」不看全文） |

### 分发闸门

reviewed 文档由编译管线分发：①进 L3 衍生物（主）；②切片上传 RAGFlow「固体矿产报告知识库」（辅，单库起步）。raw/ 前缀任何通道不可达。

## 3. 样例管理扩展模块（geo_samples）

仿 contract_price 整体 fork（spare_parts 已验证该模式，逐文件 EAI-CUSTOM forked 标注）。

### 3.1 后端 `backend/app/extensions/geo_samples/`（8 文件：routers/service/storage/crud/models/schemas/redactor/__init__）

- 表前缀 `gsb_`，模型继承共享 `app.extensions.database.Base`（gateway 启动 create_all 自动建表）；**给已有表加列必须写 database.py migrate_db() 幂等 ALTER**（create_all 不加列——cpa_documents 已踩过）
- storage.py：`BUCKET="geo-samples"`，`GSB_MINIO_ENDPOINT` 默认 `ragflow-minio:9000`（刻意绕开 knowledge 模块容器内不可达的 localhost 默认值）
- 端点（全部 `Depends(require_permission("geo_samples:access"))`）：
  - `POST /documents/upload`：multipart，收 .docx/.pdf，SHA-256 去重 409，落 raw/
  - `POST /documents/{id}/parse`：后台任务（BackgroundTasks + gsb_run_history + has_running_run 409 闸 + status 轮询）；**三分支解析**（见 3.3）
  - `POST /documents/{id}/redact`：规则引擎脱敏 → clean/source.md + gsb_redactions 流水
  - `POST /documents/{id}/review`：`{approve|reject, note}`——approve 即 reviewed 并纳入分发
  - `POST /pipeline/compile`：触发技能层编译子进程（§5）；`_SKILL_DIR` 指向 skills/public/geological-report，配 `test_skill_dir_exists` 守护（bug-526 教训：路径漂移=静默失败）
  - `GET /documents*`、`GET /documents/{id}/preview/{page}`：列表/详情/预览 PNG
- Gateway 不 import skill 代码（contract_price service.py 同款契约），子进程 sys.executable + cwd/PYTHONPATH 指向 skill scripts
- mcp.py（agent 查样例库统计）延后——写作技能经 knowledge_search 已可达（YAGNI）

### 3.2 前端三页 + 权限四处联动

- `/geo-samples` 路由壳（app/geo-samples/ 薄壳）+ `extensions/geo_samples/`（api.ts/hooks.ts/types.ts/components/，轻量 table 原语同 contract-price API）
- DocumentsView：批量上传（FormData authFormFetch + 并发池）+ stage×mineral×status 筛选
- ReviewView：redaction 命中清单高亮 + 预览 PNG 对照（TracebackDrawer 模式）+ approve/reject/note
- TasksView：解析/编译运行记录
- 权限四联动（漏一处页面不可见）：config/permissions.yaml（nav_id `nav:geo-samples` + 3 个 `gsb:page:*`）→ roles_custom.yaml 授权 → database.py app-center 注册（path `/geo-samples`，license `geo_samples`）→ license/service.py allowlist

### 3.3 解析与脱敏

**三分支解析**（填 contract_price docx 半成品的坑——其上传放行 docx 但 eai-flow-ocr 仅收 PDF）：
1. docx → python-docx 逐元素转 md（heading→`##`、表格→md 表）；**MathType OLE 公式不解析，落 `[公式:pN]` 占位**（W1 公式即从 WMF 人工转录的先例）
2. pdf 文字版 → pymupdf4llm（harness 已有）
3. 字符密度稀疏判定为扫描件 → eai-flow-ocr（POST /ocr，超时 1800s，重试 30s/60s——既有契约）

**脱敏规则两档制 + 地质数值红线**：
- 自动替换档：探矿权证号（`C\d{12}` 等）、统一社会信用代码、经纬度/高斯坐标、电话/邮箱、矿权人与公司名（工商后缀词典）→ `****`
- 标记待审档：中文人名（高误报，只标记不替换）
- 每条命中写 gsb_redactions（规则名+位置+原文 **hash**，不落明文）
- **红线：地质数值（品位/厚度/资源量/涌水量等）永不脱敏**——脱了同时毁掉 SL3 指纹库与深度标定的范文数值基础（东川样例口径=脱身份不脱地质数）

### 3.4 RAGFlow 集成（利用地图定案后的立场）

**总立场：单库起步、切片为单位、parent_child 分块、不升级（钉版本）、触发式升级。**

| 决策 | 内容与依据 |
|---|---|
| 部署版本 | v0.25.3（离线 -fixed=同版+硬化）。**唯一版本动作：把 docker/.env.docker 的 `RAGFLOW_IMAGE=latest` 钉到 v0.25.3**（消除 compose 默认/latest/离线 .env 三态漂移） |
| 升级路径 | 单库+标记行的检索噪音实测过大时，升级序：分库（按矿种）+ kf_search_knowledge 动态通道 → 改 harness knowledge_search 支持运行时 datasets（最后手段，EAI-CUSTOM 三重规范） |
| 入库单位 | **节级切片**（非全文）：每片=一个 `## N.M` 节，首行标记 `【矿种】X｜【阶段】Y｜【report_id】Z｜【节号】chN.M`——检索命中自带归属，agent 按当前项目矿种自行取舍（替代按矿种分库/meta_fields 过滤） |
| 分块 | General(naive) + **parent_child**（v0.23.0+）：段落级子块召回、命中返回整节父块（chunk_token_num=2048≈一节）——「分块割裂」的官方正面解 |
| v0.26.2 缺陷风险 | 我们无 md AST 修复（孤行标题被切/表格重复）；缓解序：切片粒度（影响面小）→ Phase 1 分块质量人评 → 不达标先「切片降纯文本+标记行」→ 仍不达标才定向升级镜像 |
| 采纳 | auto_keywords（≤32/chunk，地质术语加权）；retrieval 的 doc_ids（client 已封装，单报告内检索收窄） |
| 不用（附理由） | GraphRAG（成本高/删文件图不自动更新/v0.27 UI 已弃用）、RAPTOR（解决全局概括类多跳问答，与「细粒度范式定位」语义不符）、rerank（官方自认召回提升甚微显著拖慢，v0.18.0 已移除内置；默认关键词 0.7/向量 0.3 配比反而利好孔号/矿体号术语）、chat assistant/{knowledge}（技能在 agent 侧自组稿，不需要 RAGFlow 侧再套 LLM）、DeepDoc 视觉解析（我们自己解析，顺带避开 HF 模型内网离线化门槛） |
| 调优基线 | similarity_threshold 0.2 起步、召回偏低先降 threshold（#8553 路线）不动权重；新库 embedding 与现固体矿产库同模型（dataset 有 chunk 即锁模型，换=全量重建）；调参只在 config.yaml/API 侧（检索测试页参数不自动保存） |
| 运维坑登记 | DELETE documents 参数名写错会**静默删全库**（#12030）→ 删除封装带参数校验+二次确认；批量解析预案（卡死查 task_executor/HF、尾部卡死调 MEM_LIMIT、队列堆积清 redis stream）；chunk 删除只禁用不真删；extensions client 两个已知瑕疵（list_datasets 分页形参未传进请求 client.py:95-103；get_dataset_statistics 走 web 控制台内部端点）不阻塞性修复但记档 |

## 4. RAGFlow 的作用边界（回应「分块割裂」关切）

四类价值中**主供给不经过 RAGFlow**：深度基线（calibrate 读 clean 全文）、范文导航（bank_index 纯文件索引，检索键=节号）、SL3 指纹/矿种包（确定性文件）。RAGFlow/knowledge_search 仅承担**节号索引答不了的主题级查询**（「断层破碎带有哪些写法」——叙述散落几百份报告不同章节，只有 embedding 能跨报告捞出）。此定位与技能既有安全边界一致：SKILL.md:133 范文检索产物仅限叙述范式参考、数值/专名禁入正文，SL2/SL3 机器兜底；bank_index 与 RAGFlow 互补——**bank_index 管「按章导航」，RAGFlow 管「按主题发现」**（命中切片按文件名回 bank_index 取同报告相邻节）。

## 5. 技能层编译管线（bank_compile.py）

`POST /pipeline/compile` → gsb_run_history → 子进程 `python -m scripts.bank_compile`（cwd=技能 scripts/）。skill CLI **直连同一 extensions DB** 读 reviewed 清单 + MinIO 拉 clean/source.md（contract_price「共享 cpa_ 表」同款契约）。四步：①拉取（file_hash 增量对账）→ ②切片（`## N.M` 节号正则与 calibrate/SAMPLE_NO_RE 同源，每片加标记行）→ ③标定（N 份 per 章 median）→ ④分发（SL3 指纹源 + RAGFlow 上传，幂等按 file_hash；status→compiled 写回）。

### 产物落点 × 既有消费点兼容矩阵

| 产物 | 落点 | 喂饱的消费点 | 代码改动 |
|---|---|---|---|
| 全量章切片 | `references/samples/<stage>/chN__<report_id>.md` | **SL3 指纹池**：check_sl3 对 samples/<stage>/ 非递归 glob("*.md")，落同目录即自动扩容；N 份范文数值全进负样本池，混矿种反而更安全（任何范文数值都该拦） | **零** |
| 东川原件 | `chN_sample.md` 原样保留 | SKILL.md:118 派发契约与 build_output 三处报错文案的硬编码路径继续有效，天然降级兜底 | 零 |
| 章节切片库 | `references/samples_bank/<stage>/slices/chN/<report_id>__chN.M.md` + `bank_index.json` | 子代理范文参照（§6②） | 新目录+索引（doc-depth-design §7 Phase 2 蓝图落地） |
| 深度基线 | `references/depth_targets/<stage>/<mineral>.json`（N≥1 真中位数；absolute_floor: 0.4 从代码默认落盘进文件） | L2 深度门 | resolve_targets 探测链一处扩展（§6①，EAI-CUSTOM） |
| ore_pack 草稿 | 管理模块人工审核队列 → `ore_packs/<矿种>.json` | 矿种包孵化 | **不进 compile 自动流**：LLM 批量抽草稿→人审通过才落 repo |
| 缺陷黑名单/规范锚点 | 审核队列 → 样例缺陷清单 / standards_index sample_verbatim 扩容 | 价值④ | Phase 4 |

## 6. 运行时消费契约（写作时四个接触面）

**① 深度门按矿种选基线**。矿种是运行时信息（交互序列第一问即矿种），不能绑进静态 stage 文件。解法：`build_output.resolve_targets` 探测链插一步 `depth_targets/<stage>/<mineral>.json`，**mineral 从 data/00_project 表单读**（build_output 本就消费 data/ 表单）；取不到 → fallback 现有 depth_targets.json（东川基线）+ stderr 提示。缺省路径行为完全不变；单处改动、EAI-CUSTOM 注记，harness 零改动。

**② 范文参照升级**。SKILL.md 派发契约自读输入由「chN_sample.md 单文件」升级为：按 bank_index 优先取**同矿种同节号**切片 1-2 份（选取规则：median_eff 最接近该矿种基线——参照「够得着的好样本」而非最厚样本），缺失回退 chN_sample.md。渐进披露不变：子代理仍只读 1-2 份，控制器不读。

**③ SL3 指纹**：零代码改动（见 §5 矩阵），N 份范文数值自动全量进池。

**④ 主题检索**：knowledge_search（白名单已含固体矿产库）→ 主题查询命中切片 → 按文件名回 bank_index 取相邻节。SKILL.md:133 边界条款原样保留。

## 7. 幂等、降级与权限

- compile 幂等：全产物 sort_keys/无时间戳/确定性命名，二连跑字节不变；增量按 file_hash 跳过
- 降级链（全程零新代码即退化）：bank_index 缺失→单样例模式（doc-depth-design §7 既有承诺）；矿种基线缺失→东川基线；RAGFlow 不可达→切片分发跳过、repo 衍生物照常（RAGFlow 永远是辅助通道）
- depth_targets 再生成维持「维护者动作」定性（SKILL.md Red Flag「自造基准」不破）：compile 仅由管理模块权限门控触发，gsb_run_history 全程审计

## 8. 测试策略

| 层 | 断言 |
|---|---|
| bank_compile 单测 | 节号切片边界/标记行格式；N=1 与 N=3 median；二连跑字节相同；无 reviewed 文档 rc≠0 不产空产物（calibrate「崩溃即停」同款） |
| resolve_targets 扩展 | mineral 命中/基线文件缺失/00_project 缺字段三路径探测序（EAI-CUSTOM 回归） |
| SKILL.md 结构测试 | 新消费路径词汇更新（既有 43 例结构测试同步） |
| 分块质量验收（Phase 2 首批分发后人评） | 10 份样例切片入 RAGFlow，评 chunk 完整性（标题切割/表格重复）；不达标先纯文本降级再议升级 |
| 端到端 | 2 矿种 × 勘探 ≤6 份报告全链演练：compile→深度门选对基线→范文参照选对切片→SL3 池扩容生效→主题检索命中回溯 |

## 9. 分期落地

| 期 | 内容 | 出口判据 |
|---|---|---|
| Phase 0 资产盘点 | 几百份清单化：格式/矿种/阶段/密级/年份（管理页 Excel 批量导入元数据亦可） | 矿种分布表——决定 ore_pack 孵化排序与 bank 首批入库范围 |
| Phase 1 模块 MVP | 上传/三分支解析/自动脱敏/人工抽审 + 钉 RAGFLOW_IMAGE（分发动作留待 Phase 2 编译管线统一执行——RAGFlow 入库单位是切片，切片是 compile 产物） | 50 份样例走完 uploaded→reviewed 全流程 |
| Phase 2 编译管线 | bank_compile + depth_targets 多基线 + resolve_targets 扩展 + SKILL.md 契约升级 + SL3 自动扩容 + **分块质量人评（首批分发后，升级触发器）** + 端到端演练 | 写一篇非铜矿报告时深度门/范文参照/SL3 全部吃到新样例 |
| Phase 3 矿种包孵化 | LLM 批量抽取 ore_pack 草稿→管理页人审→ore_packs 落库（按 Phase 0 分布排序） | ≥3 个新矿种包过审 |
| Phase 4 合规/缺陷扩容 | standards_index sample_verbatim 扩容、D1-D6 型缺陷黑名单、tag set 主题库试点（可选） | 合规枚举源覆盖率提升可量化 |

## 10. 风险登记

| 风险 | 缓解 |
|---|---|
| 技能脚本正被并发会话硬化（bug-3036/3049），本设计的消费点锚点（SL3 glob、resolve_targets 链、五/六步门）可能漂移 | 设计只锚「机制」不锚行号；Phase 2 动工前跑一次消费点复核 |
| ORM 双镜像逐列同步负担（backend models ↔ skill scripts models） | 样例模块无 skill 侧 ORM——skill 只读 DB/MinIO，无双镜像问题 |
| _SKILL_DIR 硬编码静默失败（bug-526） | test_skill_dir_exists 守护照搬 |
| embedding 模型锁定（dataset 有 chunk 即锁，换=全量重建） | 新上传前先对齐现固体矿产库 embedding；写入运维手册 |
| RAGFlow 删除 API 静默删全库（#12030） | 删除封装参数校验+二次确认；分发用 upload/update 幂等路径优先 |
| 脱敏漏脱 | 两档制+抽审面只看命中清单；gsb_redactions 流水可回溯；地质数值红线防止过度脱敏 |
| 深度基线被误当「自造基准」 | compile 是维护者动作+权限门控+run_history 审计；resolve_targets 只在基线文件缺失时回退不新建 |

## 附录 · 关键证据锚点（侦查 workflow wf_520fce3b-2ca / wf_8bc97b27-7a2，2026-09-01）

- contract_price 模板：backend/app/extensions/contract_price/ 8 文件分层；app.py:921 include_router；storage.py:16-37（minio SDK/bucket 懒建/CPA_MINIO_* env）；routers.py:506-519（后台子进程管线）；service.py:23-27（_SKILL_DIR + bug-526 注记）；models.py:1-6（ORM 双镜像注记）；database.py:1121-1127（migrate_db 幂等 ALTER）；permissions.yaml:126-139（四联动之一）
- spare_parts fork 先例：__init__.py:1 EAI-CUSTOM forked 标注；skill 侧 bucket 名不一致坑（csp-parts vs csp-documents）
- KF/RAGFlow：knowledge_search=harness deerflow/community/ragflow/tools.py（config.yaml 白名单 5 库含固体矿产库 eaad624e…）；kf_search_knowledge=knowledge_factory MCP（动态 knowledge_bases 表）；extensions client.py 各端点封装清单；service.py:347-403（chunk_method→parser 映射与扩展名白名单）
- 技能层消费点：calibrate.py:23-24,44-45,53（FNAME_RE/SAMPLE_NO_RE/--samples-dir）；consistency.py check_sl3（stage_path 推 samples 目录、非递归 glob、≥100 数值指纹+组/群专名）；SKILL.md:118-119（子代理自读沙箱路径）；build_output 三处报错文案硬编码 chN_sample.md；resolve_targets 探测链与 CANONICAL_TARGETS
- RAGFlow 版本与特性：部署 v0.25.3（docker-compose.ragflow.yaml:18；ragflow-fixed.Dockerfile）；上游 v0.27.1；parent_child v0.23.0+；md AST v0.20.4、孤行标题/表格重复修复 v0.26.2；GraphRAG/RAPTOR UI 弃用于 v0.27.0；tag sets v0.16.0（软加权非硬过滤）；rerank 官方 WARNING 与 v0.18.0 移除内置；DELETE documents #12030；召回调参 #8553
