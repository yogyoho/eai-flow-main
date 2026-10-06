# 更新记录

格式参考 Keep a Changelog；条目对齐 git 提交批次。

## 2026-10-06 —— 文档中心全面升级

**Added 新增**

- 「概念详解」区（concepts/，7 页）：本体地基（三元组/RDFS/OWL/IRI）、Turtle 与 JSON-LD 1.1、SHACL、owlrl 闭包（含 prp-spo2 静默零推断坑）、SPARQL 与 CONSTRUCT 派生（双层推理）、TriG 快照——统一四段结构（类比→本系统实现→在哪看→常见坑）
- 「参考」区（reference/，3 页）：[MCP 工具总表](./reference/mcp-tools)（17+5 工具契约）、[GB/T 48000.3—2026 符合性](./reference/gbt-48000)（C1-C5 对照+诚实边界）、[Agent 集成指南](./reference/agent-integration)（MCP 配置/双技能/实测路径）
- 功能操作区：[端到端数据流](./guide/data-flow)、[审阅闭环](./guide/review-loop) 专题 + 九模块逐页分页指南（01-09）
- `scripts/gen_reference_tables.py`：从后端源码（`_TOOLS_SPEC` / `conformance.py`）生成两张易漂移表，只写 GENERATED 区间

**Changed 变更**

- 导航重构：保留功能操作/术语解释/业务本体设计/更新记录四分类，新增概念详解/参考两区
- 首页改四读者入口（业务操作/概念学习/国标评审/开发集成）
- 术语总览补技术词卡并链概念页深读；eia 域设计对齐 v2 扩容（+24 etype/+19 谓词/链 3→5）与 force_review/三库 scope 实况；doc_graph 骨架补任务化（B2/G3/G6）
- `ignoreDeadLinks` 关闭——内容齐备后死链即构建失败（质量门禁）

**纪律 维护约定**

- 新增/修改 MCP 工具或 conformance 校验项 → 重跑 `python scripts/gen_reference_tables.py`（两表页头有标注）
- 内容上线需重建 ontostudio-docs 镜像（dist 烤在镜像里）：`docker compose -p eai-docker build ontostudio-docs && docker compose -p eai-docker up -d ontostudio-docs`

## 2026-09-27

- 文档中心骨架上线（VitePress，部署于 /ontostudio/docs/）
- registry 缩编：仅保留 `doc_graph.yaml`（审查闭环骨架）+ `eia.yaml`（环评业务本体）——bid_quote / contract_price / spare_parts / cross_module 四个测试域模型移除，待重新建模
- 实体库/消解审核/建模器/工作台总览/校验中心/抽取导入/导出/推理/图谱浏览 九页完成原型移植
- 建模器画布交互批次 2 转正：节点拖拽移位、＋子类连线（subClassOf）、表单父类增删=边编辑
- 消解审核确认/驳回同步投影修复：确认即落图（状态强制翻转），全量装载=对账自愈
