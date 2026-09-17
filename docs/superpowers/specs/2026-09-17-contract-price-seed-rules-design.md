# 合同价格分析 — Seed 定位规则 + 提取鲁棒性完善 设计文档

> **状态**:已批准(2026-09-17,会话内逐节确认)
> **前置**:2026-06-26-contract-price-analysis-design-v2.md(v2 架构,已落地)——本设计不推翻 v2,是在其数据入口层(分类/提取)与 OCR 服务上做定向增强
> **实证基础**:7 份真实合同样例全量 OCR 分析(`.wolf/tmp/cpa-samples/`),用户逐节确认

---

## 0. 背景与决策记录

### 0.1 问题

现有管线的表格分类/列定位是拿**一份**样例合同(桂北数据中心分包)调的。7 份真实样例实测:**5-6 种表格版式**,通用 ROLE_TOKENS 猜测在多价格列表上必然选错列(网价/运杂费/不含税单价/含税单价/综合单价并存,有的表头还带公式后缀"综合单价(5=2+3)")。

### 0.2 样例格式证据

| 合同 | 分项价格表 | 关键差异 |
|------|-----------|---------|
| 桂北数据中心分包(原样例) | 工程量清单计价表 | 基线格式,已处理;**无规格列但有分类行**((一)建筑工程/屋面…) |
| 工程项目分包-测试 | 工程量清单计价表 | 与基线同格式 |
| JZGS 钢材物资采购 | 物资采购清单 | 品名/规格型号/**网价/运杂费/综合单价(5=2+3)/总金额(6=1\*5)**,表头带编号+公式 |
| 上浦钢筋采购 | 供货及价格表 | **材质列作规格**;暂定数量;含税总价(非"合价") |
| 木饰面石材采购 | 物资清单 | **材质列作货物名**;出厂价/运杂费/综合单价(含税);多行表头跨行断裂 |
| 钢材采购-签字版 | 钢材明细表 | 网价/其他固定单价干扰列;厂家品牌列 |
| 钢筋补充协议 | 价格调整表 | **p2/p3 横版扫成竖版**(OCR 0 表静默);纠偏后为新版式(材质规格/调整数量/综合单价) |

### 0.3 用户决策(会话内确认)

1. **Seed 定位规则**:从已知样例合同抽取"表名 + 列锚点"(货物名称列/规格列/含税单价列等),配置 tab 管理;解析遇到 seed 之外的格式 → 不提取 → 手动补规则 → 重解析
2. **严格 seed-only**:不匹配 seed 的表零提取(不搞通用兜底猜测)
3. **失败粒度 = 表级**:单表不匹配只记详情不提取,文档级标 needs_review;`no_tables`(0 表,如纯条款协议)独立状态,不算失败
4. **OCR 结果缓存**:"补规则→重解析"必须秒级,不重跑 OCR
5. **旋转页自动纠偏**(实测验证:顺时针 90° 重 OCR 表头正确,逆时针垃圾;**页级**处理,不能整份统一转)
6. **分类(category)提取**:同名货物在不同分类下价格不同(钢筋@建筑工程 vs 钢筋@屋面),分类行上下文传播,参与聚类区分

---

## 1. 数据模型

### 1.1 Seed 规则(存 `config.json`,走现有 `GET/PUT /config`)

```json
{
  "table_seeds": [
    {
      "id": "gcl-qd",
      "display_name": "工程量清单计价表",
      "title_keywords": ["工程量清单", "清单计价"],
      "columns": {
        "name":          ["项目名称", "品名", "物资名称"],
        "spec":          ["规格型号", "材质", "材质规格", "参数"],
        "qty":           ["工程量", "数量", "暂定数量"],
        "unit":          ["单位", "计量单位"],
        "price_unit":    ["含税单价", "综合单价", "含税落地单价"],
        "price_total":   ["含税合价", "含税总价", "总金额"],
        "price_untaxed": ["不含税单价"]
      },
      "exclude": { "price_unit": ["不含税"] },
      "source": "样例:房建工程（桂北数据中心）"
    }
  ]
}
```

- 7 种列角色;**`name` 且(`price_unit`|`price_total`)锚定成功才确认 seed**,其余角色可选(缺规格列的合同 spec 不提取)
- 锚点为**归一化子串匹配**:去内部空白、去"（…）"括注(公式后缀)、全角→半角
- `exclude` 防子串抢角色:"不含税单价"包含"含税单价"子串(现网已踩过的坑,泛化进 schema)
- 多价格列免疫:网价/运杂费等非锚点列自动忽略;"哪列是分析价"由 seed 显式声明
- `title_keywords` 仅作多候选消歧,**不作为确认条件**(OCR 表名会碎:"采购"实测误读为"米购")
- `ConfigOut/ConfigUpdate` 加 `table_seeds` 字段;`price_table_keywords` 保留字段但标记废弃,管线停用

### 1.2 parse_meta 扩展 + parse_status 新值

```
parse_meta.unmatched_tables: [{page, table_idx, title, header: [...], col_count, row_count}]
parse_meta.matched_seeds:    {"工程量清单计价表": 5}   # seed display_name → 命中表数
parse_meta.orientation_fixed_pages: [2, 3]               # ocr-service 透传

parse_status: parsing | parsed | needs_review(有表但全部未匹配) | no_tables(新增) | failed
```

### 1.3 cpa_items 加 `category` 列

- 可空字符串;两处模型同步(skill `scripts/models.py` + backend `models.py`),带 DB 迁移
- 聚类向量化文本 = **名称 + 规格 + 分类**(vectorizer.py):钢筋@建筑工程 与 钢筋@屋面 分簇,各算价格统计
- 前端分项明细/Excel/聚类审核展示分类

---

## 2. 匹配算法(table_classifier.py)

```
match_seed(rows, seeds) → (seed, roles{角色:列号}, header_rows) | None
① _collapse_header 折叠多行表头(复用现有,处理"含/税）"跨行断裂)
② 归一化标题+表头文本
③ 逐 seed:锚点子串匹配列头(exclude 守卫;角色按声明顺序抢占,先到先得)
④ 确认条件:name 锚定 且 price_unit/price_total 至少一个锚定
⑤ 多候选消歧:标题关键词命中者优先,否则锚定角色数最多者
```

- **现有通用分类逻辑降级为"起草建议器"**:`_map_roles` 的 ROLE_TOKENS 用于从未匹配表自动生成 seed 草稿默认值;管线主路径不再调用
- **续表继承**:现有续表机制(列数±2 + 名称列 x-band)保持,继承对象从"上一 goods 表 roles"改为"上一 seed 命中表的 seed+roles"
- **分类行识别 + 传播**(extract_items 内置,无配置开关):
  - 判别式:名称列非空 且 数量/单位/价格列**全空** → 分类行(不产 item;价格漏读行通常带数量/单位,不会误判;今天此类行反正被跳过,零损失)
  - 传播:item.category = 最近一次分类行名称,直到下一个分类行

---

## 3. 解析流水线

```
上传 → SHA-256 → OCR(含方向归一化;结构化结果缓存 MinIO ocr/{doc_id}.json,剔 preview b64)
     → match_seed 逐表匹配(严格 seed-only)
        ├─ 命中 → seed 列锚点提取 → 分类行传播 → 价格校验 → items(+category)
        ├─ 未命中 → parse_meta.unmatched_tables 记详情,不提取
        └─ 续表 → 继承上一命中表的 seed+roles
     → 终态: parsed(≥1命中) | needs_review(有表全未命中) | no_tables(0表) | failed
重解析 → 默认读 OCR 缓存只重跑分类+提取(秒级);?re_ocr=true 才全量重 OCR
```

- **OCR 缓存**:首次解析把 OcrResponse(去 preview_png_b64,preview PNG 本就单独存 MinIO)写 `ocr/{doc_id}.json`;文档重传(内容变更)时失效删除;缓存缺失自动回退全量 OCR
- **方向归一化(ocr-service `ocr_engine.py`)**:页级触发——某页 0 表 + 有文本信号 → ±90° 试探重 OCR → 取表头得分/置信度高者;纠偏后的页面图像作为该页基准(bbox/preview PNG/页尺寸全部随之,溯源对齐);触发要保守,成本上限在实施时以 137 页样例基准验证(目标:正常文档总耗时增幅 <10%);parse_meta 记 `orientation_fixed_pages`
- reparse 端点加 `?re_ocr=true|false`(默认 false)
- **合同元数据(项目名称/供应商乙方/签订日期)提取时机 = 解析时**(现状 `project_fields.py` 搭前 3 页整页 OCR 便车,零额外成本;UI 已有手填兜底)。本设计补一个缺口:**末页兜底**——前 3 页正则 miss(乙方/签订日期为 None)时补 OCR 最后 1-2 页重试(签字页常在末尾,补充协议尤甚;仅 miss 触发,成本有界)。OCR 缓存落地后,未来改标签词表从缓存重导出字段是秒级,该时机不锁死改进

---

## 4. UI(三 tab,截图评审结论并入)

### 4.1 配置 tab(SettingsView)——重构主战场

- **`SeedRulesCard` 替换"货物表名关键字"文本域**:seed 规则卡片列表(名称/标题关键词 chips/列锚点摘要/来源/命中统计徽章"命中 N 份合同 M 张表"——客户端从 /documents 的 parse_meta.matched_seeds 聚合,零新端点),支持新建/编辑/删除
- **`SeedEditorDrawer`(与 4.2 共用)**:7 种列角色各一行下拉(候选=该表 OCR 检出的表头单元格 + 自由输入);title_keywords 标签编辑;保存即写 config
- **移除"解析模式"死控件**(v2 已废弃单 OCR 路径);聚类参数收进"高级"折叠
- dirty 跟踪 + 保存 toast 自动消隐;数字输入保存时 clamp;视觉语言对齐 dashboard 体系(PageHeader 图标盒/font-cyber/语义色)

### 4.2 合同解析 tab(ContractsView)

- 状态徽章扩 `needs_review`(琥珀)/`no_tables`(灰);行内加"⚠ N 张表未识别"徽章 → **未匹配表抽屉**(每表:页码/表名/OCR 表头 chips + 页面预览缩略图)→"生成规则草稿"→ SeedEditorDrawer 预填 → 保存 →"重解析本文档"(走缓存)
- 行健康度摘要(现有"5页/91表/450行")补命中规则名

### 4.3 分项校验 tab(ItemsView)

- +分类列(无则"—",同规格列惯例);分类入行展开区;筛选器加按分类

---

## 5. 初始 Seed 库(内置 6 条,`table_seeds` 为空时注入;锚点为 v1 草案,以验收运行实测为准)

| # | display_name | name | spec | qty | unit | price_unit | price_total | price_untaxed | exclude |
|---|-------------|------|------|-----|------|-----------|-------------|---------------|---------|
| 1 | 工程量清单计价表 | 项目名称,名称 | 规格型号,参数 | 工程量,数量 | 单位 | 含税单价 | 含税合价 | 不含税单价 | price_unit:[不含税] |
| 2 | 钢材物资采购清单(JZGS) | 品名 | 规格型号 | 数量 | 单位 | 综合单价 | 总金额 | — | price_unit:[不含税,网价] |
| 3 | 钢筋供货价格表(上浦) | 物资名称 | 材质 | 暂定数量,数量 | 计量单位 | 含税单价 | 含税总价 | 不含税单价 | price_unit:[不含税] |
| 4 | 木饰面石材物资清单 | 材质,品名 | 规格 | 数量,暂定数量 | 计量单位 | 综合单价,含税单价 | 含税总价 | 不含税单价 | price_unit:[不含税] |
| 5 | 钢材采购明细(签字版) | 品名 | 规格型号 | 数量 | 单位 | 含税单价 | 含税合价 | 不含税单价 | price_unit:[不含税,网价] |
| 6 | 补充协议价格调整表 | 物资名称 | 材质规格 | 调整数量,数量 | 计量单位 | 综合单价,调整后单价 | 调整后合价,总金额 | — | price_unit:[不含税,网价] |

---

## 6. 失败模式与观测性(v2 §6 增补)

| 场景 | 处理 | 可见性 |
|------|------|--------|
| 表不匹配任何 seed | 不提取,记 unmatched_tables 详情 | 行内"⚠N表未识别"徽章 → 抽屉 → 建规则;文档级:全未匹配=needs_review,部分匹配=parsed(徽章仍提示) |
| 0 表文档(纯条款/协议) | parse_status=no_tables | 灰徽章,不算失败不告警 |
| 旋转页 | 自动纠偏 + orientation_fixed_pages | parse_meta;纠偏失败(<阈值分)回退 needs_review |
| seed 误伤(把该提取的表锚错列) | matched_seeds 记命中分布;溯源抽屉肉眼核对 | 分项校验 + 溯源高亮 |

---

## 7. 改动文件清单

| 文件 | 操作 |
|------|------|
| `skills/.../scripts/table_classifier.py` | 改:match_seed 主路径;_map_roles 降级为起草建议;分类行识别/传播 |
| `skills/.../scripts/cli.py` | 改:_load_price_keywords → _load_seeds;_extract_from_tables 接 seed;unmatched_tables 记录;OCR 缓存读写 |
| `skills/.../scripts/seed_library.py` | **新增**:内置 6 条 seed 常量 + 空配置注入 |
| `skills/.../scripts/models.py` + `backend/.../contract_price/models.py` | 改:+category;DB 迁移 |
| `backend/.../contract_price/schemas.py` | 改:ConfigOut/Update + table_seeds;DocumentOut.parse_meta 透传新键 |
| `backend/.../contract_price/routers.py` | 改:reparse +re_ocr 参数 |
| `mcp-server/ocr-service/ocr_engine.py` | 改:页级方向归一化 + orientation_fixed_pages |
| `skills/.../scripts/project_fields.py` | 改:末页兜底(miss 时补 OCR 最后 1-2 页重试) |
| `frontend/.../contract-price/components/SettingsView.tsx` | 改:SeedRulesCard + 移除死控件 + dirty/clamp + 视觉对齐 |
| `frontend/.../contract-price/components/SeedEditorDrawer.tsx` | **新增**(与合同解析 tab 共用) |
| `frontend/.../contract-price/components/ContractsView.tsx` | 改:新状态徽章 + 未匹配表抽屉入口 + 命中规则名 |
| `frontend/.../contract-price/components/UnmatchedTablesDrawer.tsx` | **新增** |
| `frontend/.../contract-price/components/ItemsView.tsx` | 改:+分类列/筛选/展开区 |
| `tests/`(skill 与 backend) | 改/新增:match_seed 单测(6 seed × 样例 JSON 回放)、分类行传播、缓存命中重解析、严格模式零提取 |

---

## 8. 实施阶段

1. **P1 后端管线**:seed schema+seed_library+match_seed+分类行+严格模式+unmatched_tables+OCR 缓存+元数据末页兜底(含单测,样例 JSON 回放)
2. **P2 OCR 方向归一化**:ocr_engine 页级试探(137 页样例成本基准)
3. **P3 前端配置 tab**:SeedRulesCard + SeedEditorDrawer + 死控件移除/dirty/clamp
4. **P4 前端合同解析+分项校验**:新徽章 + UnmatchedTablesDrawer 闭环 + 分类列
5. **P5 验收**:7 样例全量跑 + 桂北回归 + 秒级重解析实测

## 9. 验收标准

1. 7 份样例:≥6 份提取成功(补充协议经方向纠偏走调价表 seed);纯条款文档正确落 no_tables
2. 桂北重解析 ≈450 行,价格抽查一致(回归基线)
3. 同名货物不同分类分簇,价格统计分开
4. 未匹配表 → 建规则 → 重解析全流程 ≤1 分钟(缓存生效;对照全量重 OCR 3-4 分钟)
5. 旋转页自动纠偏,溯源 bbox 对齐纠偏后图像
6. seed 不匹配的表零提取、零静默,全部可见于 unmatched 列表
7. 设置页:解析模式死控件移除;dirty/clamp 生效;seed 卡片显示命中统计

## 10. 开放问题

1. 方向归一化触发器的成本精确调优(0 表页全部试探 vs 廉价方向签名预筛)——P2 以 137 页样例基准定
2. seed 列锚点在同一表头歧义(如两列都含"单价")时的消歧细则(声明顺序 vs 右优先)——P1 实测样例后定,默认声明顺序
3. 补充协议调价表的"调整后数量"是否入 qty(影响反算)——P5 验收时以提取结果定
4. 乙方/签订日期的 LLM 兜底识别(正则+末页兜底仍 miss 时)——默认不做,验收后按 miss 率定
