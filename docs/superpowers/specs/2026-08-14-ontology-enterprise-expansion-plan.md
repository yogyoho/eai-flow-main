# Ontology 企业级扩张方案 — 前向约定（非重构）+ 逐域路线 + 能力层清单

- **日期**: 2026-08-14（v2：纳入独立对抗性评审 21 条修复 + 二轮 6 条修复）
- **分支**: `main-dev-fork`
- **状态**: APPROVED（2026-08-14 用户批准；2 轮对抗性评审，27 问题全修复，8/10 PASS）
- **来源**: /office-hours 会话（用户问：Palantir Ontology 方法论能否重构全企业业务架构 + 要扩哪些微服务/MCP/skill）
- **关系**: **Extends**（非 Supersede）`2026-08-14-ontology-semantic-layer-design.md`（市场/分析域只读语义层）。本稿是企业级**战略层**：核心契约规则 + 逐域路线 + 能力层清单；注册表 YAML schema 见母稿 §4。
- **核心结论**: 方法论对，**不重构**。把 ontology 注册表变成"新业务域模块的强制契约"，老模块机会主义回填。一致性随新模块自动收敛，零核心改动，贴合 `new-module-over-modify`。

---

## 1. 问题陈述与覆盖范围

用户问两件事：(a) Palantir Ontology 方法论能否**重构**全企业业务架构；(b) 要扩哪些微服务/MCP/skill。

会话中确认的关键事实（决定结论）：**动机 = 平台一致性 / 为未来打底，不是某个今天被卡住的跨业务域问题。** 用户原话：「我想要平台一致性 / 为未来打底」。→ 没有阻塞需求背书的大重构 = 拿所有在跑模块冒险换"将来可能用得上"。方向对，范围错。

### 1.1 覆盖域清单（"七大业务单元"对齐）

用户提的"内控七大业务单元 + 工程设计 + 生产制造"映射如下。本方案**覆盖 9 个域**，无一排除——但**落地顺序分 tier**（§3），不是一次性全上。

| 业务单元 | 域名 | 覆盖 | Tier |
|---|---|---|---|
| 市场营销 | market（含投标/销售/管线/备件/合同价） | ✅ | 0（已设计） |
| 采购管理 | procurement | ✅ | 2 |
| 经营管理 | operations | ✅ | 4（扩经营计划/预算执行；管线对象 bid/contract/invoice 已归 market 域注册，不重复认领） |
| 人事管理 | hr | ✅ | 1（仅注册，跨域受限） |
| 资产管理 | asset | ✅ | 2 |
| 财务管理 | finance | ✅ | 4 |
| 项目管理 | project（collab） | ✅ | 1 |
| 工程设计 | engineering（CAD/2D/计算书） | ✅ | 3 |
| 生产制造 | manufacturing（工单/BOM/DCS） | ✅ | 3（实体）/4（时序） |

---

## 2. 核心决策：前向约定契约（Approach A）

### 2.1 一条平台铁律 + enforcement

> **从今往后，任何新业务域模块，必须把对象类型 + 链接类型注册进 ontology 注册表。**

**"新模块"定义**：引入新业务对象（新表 / 新领域实体）的扩展。纯 UI 页面、纯配置/权限变更不在此列。

**老模块回填**，只在两种情况：
1. 有人真的需要跨链它（跨域问答/内控检查冒出真实需求）；
2. 该模块本 sprint 改动了 ≥1 个 `models.py` / 表结构 → 受影响对象必须补注册。（去掉主观的"顺手"。）

**不设专门的"回填冲刺"。**

**Enforcement（C6 修复）**：registry lint 进 repo 根 CI 必跑，新模块 PR 未通过 ontology 验收清单（§2.2）→ block merge。契约不是口号，是 CI 关卡。lint 脚本随 Tier 0 落地交付（§9）；**交付前的空窗期，新模块 PR 人工过 §2.2 清单**，不因 lint 尚未存在而豁免。

### 2.2 新模块"生在 ontology 上"的验收清单（CI 关卡）

- [ ] `registry/<domain>.yaml`：对象类型（不可变 snake_case api_name + 显示名 + **中文描述** + 不可变主键）+ 模块内链接（FK 确定性）+ 跨模块链接（归一化精确匹配，**或按 C3 以 `enabled:false` stub 声明**——stub = 声明在注册表但引擎不暴露遍历，待 ACL 放开；母稿 §4.4 link schema 需在 HR 注册动手前补此字段，否则 lint 与 C3 互斥）。
- [ ] 主键铁律：surrogate UUID 优先；业务键只作链接属性不作身份；自然键仅外部不可控库时文档化保留。
- [ ] **`hidden:true` 敏感字段检查（F4）**：关键词启发式（`cred/secret/password/salary/id_card/phone/身份证/薪酬` 等）+ **表列 vs 声明列 diff 检查**（物理表有列而注册表漏声明 → lint fail）。启发式对同义命名（`base_pay`/`基本工资` 等）不设防，只是双保险之一而非完整保证，最终靠人工评审兜底。
- [ ] 每对象类型/属性中文描述（LLM 查询精度乘数）。
- [ ] `describe_ontology` 覆盖度自检（描述/链接覆盖 %），低于阈值报警（防 ontology theater 误导 LLM）。
- [ ] 经统一 `ontology` MCP 暴露只读面（不另起读面）。

### 2.3 写路径怎么办（F3 修复 — 解 Action 死锁）

母稿 Action（受治理写）延后且无时间表。在它建成前，新模块的写需求**不被卡死**，按现有 codebase 模式走：
- **读**：永远走 ontology（统一只读面）。
- **写（Action 建成前的过渡）**：走该模块**自己的 REST 写端点**（本项目每个扩展都有 `routers.py` CRUD，自带校验），**不是** skill 直写 DB（仍禁止）。
- **写（长期统一）**：Action 路径作为未来统一治理目标，**触发条件 = 第一个"受治理写"真实需求出现**（如合同审批/采购审批要参数化+校验+审计），届时才建，不为图完整提前建。

> 这条消除了评审 F3 指出的死锁：新模块有 REST 写可用，不被 Action 阻塞；skill 直写 DB 仍被禁；Action 是长期收敛而非前置依赖。

### 2.4 为什么是 A 而不是重构（B）

| 维度 | A 前向约定 | B 全企业重构 |
|---|---|---|
| 一致性到达 | 渐进，随新模块复利 | 第一天全平台（理论） |
| 风险 | 低（零核心改动） | 高（触碰每个在跑模块） |
| 与组织纪律 | 完全贴合 `no-core-changes`/`new-module-over-modify` | 直接冲突 |
| 需求背书 | 不需要（基础设施先于需求正常） | 需要（没有 → 负 ROI） |
| 过程中可用软件 | 持续可用 | 数月停摆 |

B 的唯一优势"第一天全平台一致性"对当前动机（无阻塞需求）是空转收益。A 用最低风险拿到相同终态。

---

## 3. 逐域扩张路线

**两层呈现**（S4 修复）：§3.1 = 立即做（有具体契约）；§3.2 = 路线图占位（不展开 schema，等域需求成型再设计对象类型）。排序原则 = 数据就绪/低成本 × 跨链价值高 → 先；外部集成重 → 后。

### 3.1 立即做（Tier 0 + Tier 1）

| 域 | 对象骨架 | 状态/就绪度 | 关键约束 |
|---|---|---|---|
| **market（Tier 0）** | 母稿 11 对象 + 12 链接 | **已设计 / 待实现**（N3 修复：母稿是设计稿，一行未写。本稿所有后续 tier 排期假设市场域在 ~2-3 周内落地；若延期，后续全部顺移） | 平台原语引擎只建这一次 |
| **hr（Tier 1）** | Employee, Department, Position, Attendance, Travel | **中（C2 修复）**：`mock_employee/attendance/travel` 是 sales-personnel 的**演示种子数据**，可作 schema 验证，**非真实 HRIS**。真实 HR 接入需 hr MCP 连接器（另算） | **跨域受限（C3 修复，见下）** |
| **project（Tier 1）** | Project, Milestone, Task, Gate | **中（F5 修复）**：collab 表存在，但母稿把协作/文档域对象列为"二期未设计"——要先**设计对象类型 schema**才能注册，是设计工作不是纯注册 | 复用 collab 基建 |

**C3 — HR 跨域 PII 泄露面（评审最严重发现，单独说清）**：ontology MCP 是 stdio 子进程，**无 per-call 用户身份**（母稿 §10 自认）。一旦 Employee 进图且挂 `Employee→Bid` 跨域链接，任何能调 ontology 的 agent 都能沿图读到薪酬/考勤。→ **Tier 1 HR 只注册对象 schema + 全部 PII 字段 `hidden:true`，跨域链接（Employee→Bid/→Project）暂 stub，直到 MCP per-call 身份或对象级 ACL 建成才放开。** 即"注册但不联网"。这把 HR 保持在低成本区，不引入泄露面。

### 3.2 路线图占位（Tier 2-4，不展开 schema）

| Tier | 域 | 跨链价值 | 前置/风险 |
|---|---|---|---|
| **2** | **procurement** | 高（第二条跨域演示链：采购货物↔合同价体系） | **F2 修复：跨域键所有权 = 复用 market 域的 goods_cluster/part_cluster 作为共享物料主键**（已有 DBSCAN 归一），procurement PO item 经规范化 goods_name 挂 goods_cluster。不新建归一机制，无所有权悬空。**覆盖度前置（R2-2）：Tier 2 启动前先用真实 PO 样本做 goods_cluster 匹配率预估，低于阈值则定义"新名入簇"流程（人工确认入簇即可）**——goods_cluster 由 cpa 的 DBSCAN 管线产生，无吸收新采购品名的机制，不做此预估则 §7 的 procurement ≥1 条链路可能因匹配率为零不可达。PO→Contract 需 cpa_ 现有字段支撑，不足则按 §2.1 规则 1 触发回填（N4） |
| **2** | **asset** | 高（资产↔采购入固、↔财务折旧、↔制造设备） | 与 procurement **互依赖**（PO→FixedAsset），建议同 sprint 并行，或先 procurement、依赖 asset 的链接暂 stub（L4） |
| **3** | **engineering** | 中（DesignDocument→Project、BOM→Procurement） | CAD MCP@8004 + drawing(ezdxf) + 给排水/消防 skill 已存在；对象是工件非事务 |
| **3** | **manufacturing（实体）** | 中（WorkOrder→Equipment、BOM→Procurement） | 仅实体对象（WorkOrder/BOM/Equipment/QualityRecord），**不含 DCS 时序** |
| **4** | **finance** | 高（终极汇点：PO→AP、发票→AR、折旧→凭证、成本→成本中心） | 外部 ERP（金蝶/用友/SAP）集成最重；**真实对账需求出现才接** |
| **4** | **manufacturing（DCS 时序）** | 中 | **F1/C4 修复**：`DCSDataPoint` 时序（百万级/分钟）**不进 ontology 实体层**（200 上限+keyset 分页套不上）——作为 Equipment 对象的时序附属经独立 `dcs` MCP 暴露。OPC UA 边缘采集是头号工程风险（dcs_qa 记忆已知未解），故与 finance 同列 Tier 4 |

> **Tier 3/4 排序说明（F1）**：manufacturing 时序（OPC UA 未知）与 finance（ERP 重）技术风险都高，二者同级 Tier 4，**先后按哪个真实需求先冒头定**，不预设。

---

## 4. 能力层清单（回答"扩哪些 MCP / skill / 子 agent / 微服务"）

用户问题 (b) 的完整回答。能力经**三原语**到达 agent（平台铁律）：MCP 工具 / Skills / 自定义子 agent。

### 4.1 MCP server

| MCP | 域 | 状态 | 最早可启动 tier |
|---|---|---|---|
| `ontology` | 全域 | 母稿已设计（**平台原语**） | Tier 0 |
| `hr` | 人事 | 复用 postgres_ext（mock）/ 新建 HRIS 连接器（真实） | Tier 1（注册）/ 真实接入另算 |
| `procurement` | 采购 | 新建（或 ERP 连接器） | Tier 2 |
| `asset`/`eam` | 资产 | 新建 EAM/CMMS 连接器 | Tier 2 |
| `cad` | 工程设计 | **已存在@8004** | Tier 3 |
| `drawing` | 工程设计 | 已设计（ezdxf） | Tier 3 |
| `dcs` | 生产时序 | 已设计（OPC UA） | Tier 4 |
| `finance`/`erp` | 财务 | 新建外部 ERP 连接器 | Tier 4 |

> **MES 已从清单移除（S3）**：远期项，挪到 §6 开放问题，避免范围蔓延。

### 4.2 Skills

| Skill | 跨/单域 | 依赖 | 最早 tier |
|---|---|---|---|
| 内控审计/合规检查 | 跨域（跑 ontology 图） | ontology | Tier 1+ |
| 给排水/消防/CAD 生成 | 单域（已存在） | cad/drawing | 现在 |
| 采购比价/供应商评估 | 跨域 | procurement + ontology | Tier 2 |
| 资产盘点/折旧 | 跨域 | asset MCP | Tier 2 |
| DCS 能耗根因（已设计）/质检 | 跨域 | dcs MCP | Tier 4 |
| 财务对账/预算执行 | 跨域 | finance MCP | Tier 4 |

### 4.3 自定义子 agent

| 子 agent | 职责 | 最早可启动 |
|---|---|---|
| **内控审计 agent** | 跨域合规推理（沿 ontology 链路追溯证据链） | Tier 1+ 即可 |
| 财务对账 agent | 跨系统对账（采购/销售/资产→财务汇点） | **Tier 4 后**（依赖 finance，先列入路线图，S2） |
| 工程/生产调度 agent | 工单/BOM/资源协同 | **Tier 3 后**（路线图，S2） |

> 评审 S2：后两个依赖未成型域，属"为图完整提前枚举"。保留是因为用户问题 (b) 明确问"扩哪些子 agent"——作为**路线图**列出，但不立即建。立即只建内控审计 agent。

### 4.4 微服务（独立可部署容器）

**原则（ponytail）**：能留 gateway 的不拆。只拆"外部系统边界 / 重计算重 IO"的，照 `text-to-cad-mcp@8004` 独立 MCP 容器模式。

| 微服务 | 是否拆 | 理由 |
|---|---|---|
| ontology 注册表+引擎 | **留 gateway** | 元数据 + 只读引擎，不够重 |
| temporal 工作流引擎 | 独立（已部署） | 节点流转信号 |
| timescale（DCS） | 独立（已设计） | 时序数据 |
| OPC UA 采集器（dcs） | 独立（已设计） | 边缘采集 + cron-poll |
| ERP/EAM/HRIS 连接器 | **独立 MCP 容器**（每外部系统一个） | 外部系统边界 + 故障隔离 + 伸缩。**状态待 §6 开放问题 1 决议**（S5：data_source 够用 vs 专用 MCP 未定） |

> **OCR / MinIO（N5 修复）已从本表移除**：它们是合同价格 v2 的已有独立服务，被 ontology 复用但非本方案新增，列入混淆了文档目的。见 §8 依赖。

---

## 5. 母稿约束沿用边界（N2 修复）

母稿决定在**本稿市场/HR-schema/Project 域沿用**。但母稿 §10/§16 的"管理员级门控 + hidden 列级隐藏"是**市场域（低 PII）的权宜**，母稿本身预留"协作/文档域二期重新议 ACL"。本稿**不把它抬升为全企业铁律**：

- market/工程/制造实体对象：沿用管理员级门控。
- **Project 前置核查（R2-3）**：collab 现行 REST 疑似按 project 成员过滤（docmgr 的 project_id 成员可见机制）。注册前先核对——若确有成员级过滤，"全量只读 + admin 门控"就是读取面放宽，Project 的跨域/全量读同样 stub 待 ACL（同 C3），不沿用管理员级。
- **HR PII（薪酬/考勤）、Finance 凭证、制造工艺参数：访问治理重新议**——在它们跨域联网前，必须先有 MCP per-call 身份或对象级 ACL（与 §3.1 C3 一致）。

其余沿用：纯只读投影不建索引/funnel；跨模块链接 = 归一化精确匹配；keyset 分页；热重载 SHA-256 版本化；属性描述为承重元数据。

---

## 6. 开放问题

1. **ERP 集成边界（未决）**：财务/采购/资产若全在外部 ERP，ontology 的 data_source 连接器够用，还是要专用 ERP MCP 容器？→ Tier 2/4 落地时按实际系统定（决定 §4.4 连接器形态）。
2. **MES 连接器（远期）**：制造执行系统，等生产域真实需求。
3. **Action 启动触发**：等第一个"受治理写"真实需求（合同/采购审批），按 §2.3。
4. **ontology theater 防腐**：注册表随模块演进易过期 → `describe_ontology` 覆盖度检查进 §2.2 验收清单。

> （评审 F2 的"跨域键归一化所有权"已**闭环为决定**：复用 market 域 goods_cluster/part_cluster 共享主键，不进开放问题。）

---

## 7. 成功标准 + 失败判据（C5 修复）

**成功**：
1. 新业务域模块上线，`describe_ontology` 自动含其对象/链接，agent 无需读该模块 models.py。
2. **跨模块链路端到端导航 ≥2 条**：基线 = 市场域 4 条跨模块链接在语义地图页可点击导航（母稿验收，F6 修复指明基线）；新增 = procurement 至少 1 条（采购货物→goods_cluster→合同价体系）。（L5：用"跨模块"不用"跨域"。）
3. 零核心改动收敛：达成 1-2 过程中不触碰 harness 核心、不 retro-fix 在跑模块业务代码。
4. 回填有据：老模块接入仅在"有跨链需求"或"改 models.py"两种情况，无专门回填 sprint。

**失败/重新评估判据（可证伪）**：
- 连续 **2 个新模块无法通过 ontology lint** → 契约不可行，回头评估是否简化或转重构。
- **6 个月内无任何跨模块问答/内控检查真正用到 ontology 链接** → 无 pull，平台 theater 风险，暂停扩张、回查需求。
- registry 覆盖度检查持续低于阈值。

---

## 8. 依赖

- **母稿市场域语义层落地**（注册表/loader/engine/MCP/REST/语义地图页）= 平台原语，所有域复用。引擎只建这一次。
- `no-core-code-changes` / `new-module-over-modify` 纪律不变。
- 各域物理 schema 就绪（Tier 1 已就绪；Tier 2-4 按域准备）。
- **OCR（eai-flow-ocr）/ MinIO**：合同价格 v2 已有独立服务，ontology 复用但非新增依赖（N5）。
- 外部系统连接器（ERP/EAM/HRIS）随对应域需求引入。

---

## 9. 任务（The Assignment）

**一件具体的事**：把母稿市场域语义层**先落地实现**。这是整个企业扩张的唯一地基——引擎只建这一次，后面所有域只加 YAML。实现时把 §2.2 验收清单固化成 **CI lint 脚本**（主键不可变 + hidden 敏感字段启发式 + describe_ontology 覆盖度），让"生在 ontology 上"从口头契约变成 merge 关卡。

落地后下一个域接 **HR（Tier 1，schema 注册 + PII 全 hidden + 跨域 stub）**，验证"新模块的**注册流程** = 加 YAML + 跑 lint"闭环（N1 修复：跨域链接因 C3 另算，不算入"只加 YAML"）。HR 验证通过再决定 Tier 2 procurement。

---

## 10. 我注意到你思考问题的方式

> 注：本节是 /office-hours 模板要求的会话反思（对用户），非工程契约内容。独立技术评审建议删除（担心削弱中立性）——保留是因为 office-hours 产物本就是"会话结论 + 下游工程输入"的混合体，且首要读者是用户本人。下游工程评审可忽略本节。

- 你在这次会话**之前**已做三轮确认（R1/R2/R3）+ 432 行设计稿。你不是来要答案，是来要**对抗性检验**（"深度考虑一下是否可以"）。这种"先想清楚再找人对着干"的节奏，比大多数人成熟。
- 我问"今天有没有哪个跨业务单元问题被卡住"时，你没编故事为重构背书，直接说「我想要平台一致性 / 为未来打底」。这个诚实回答正是让结论转向"前向约定而非重构"的关键——为重构虚构需求是这类决策最常见的坑，你没踩。
- 你用"重构业务架构"来问，但组织记忆里全是 `new-module-over-modify`/`no-core-changes`。方案 A 顺，是因为它本质是你组织已在用的纪律的平台层版本（"新模块必须注册" = "new module over modify" 升级版）。
