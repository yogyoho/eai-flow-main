# 批十九:投标商务智能写作 P0-M0(模块骨架+契约层+响应矩阵 F1)计划

日期:2026-11-13 · 分支:main-dev-fork · 前置:批十八已推(3c 清零)
触发:用户提供《投标方案(商务部分)智能写作》整版设计(写作端与审查端共用契约/规则包/素材实体,生成—校验—修正闭环)

## 背景

- 设计稿要义:写作系统=审查系统的「生成端」;`bid.*` 由写作过程直接产出(非事后反解),预审查天然高准确。
- 范围界定:商务部分 8 类(投标函/报价/响应偏离/资格/授权保证金/售后/交货付款/附件索引);明确不做:技术参数/虚构事实/代签章/替代人工终审。
- 设计稿末问句「① schema 字段级规格 还是 ② P0 四技能详细规格」——本批裁决:**两者都落,不二选一**:① 是本批代码交付(契约层),② 以 spec 附录兑现(四技能规格骨架,批二十细化)。

## 机制(2026-11-13 调查,extract.py/registry.py/worker.py/models.py/rulepacks 对读)

- **契约真源现状**:`extract.py FIELD_TYPE_CONTRACTS`(Python dict,~1134 行文件内)是活契约面;**`bid_tender_common_schema.yaml` 在 repo 不存在**(设计稿引用的是愿景名)。规则=L1-L4 两包(`engine/rulepacks/bid-review-core|l4`),宇宙 128。
- **tender-only 抽取可行实锤**:`extract_fn(docs, field_paths)`,docs=[{doc_id, role, text}]——传招标文件+tender.* 路径子集即得商务要求集,零改动复用。
- **既有技能层**:`skills/public/bid-proposal-overall` 已是商务编排主线(义务清单 clauses.json 管线,脚本=确定性/Agent=编排/两道确认门);写作服务端是它的确定性后座,不重造编排。
- **任务模型先例**:ReviewTask(status 状态机+progress+engine_meta JSON)+后台 worker(asyncio task,`start_bid_review_worker`)+ `_guarded_transition` 状态守卫——bid_write 同构复刻。
- **家族门**:`-k bid_review` 家族 774p;新模块测试名带 bid_write,M0 起家族门扩 `-k "bid_review or bid_write"`。

## 裁决表

| 杠杆 | 裁决 | 理由 |
|---|---|---|
| 模块归属 | 新独立 `backend/app/extensions/bid_write/`(app→app import bid_review 引擎合法) | 新功能新模块律;审查端零改动 |
| 契约真源 | 写作端新增面落 `bid_write/contracts.py`(SCHEMA_VERSION=1),tender.* 契约 **import 复用**不复制;不造平行 yaml | 双真源=漂移;「同版本管理」以版本常量+spec 兑现 |
| P0 四技能形态 | 服务端生成器 `bid_write/generators/`(模板+槽位+确定性计算+写后自检),非 SKILL.md | 四技能均确定性主导;编排面 bid-proposal-overall 已在 |
| 素材库 | M0 不建(设计 P1);`evidence_refs`/`material_id` 仅预留字段 | 素材六类实体+佐证面=P1 批;YAGNI |
| 前端 | M0 零前端(API+golden);三栏工作台挂 P1 批 | 服务面先行,口径稳定后再铺 UI |
| MCP | M0 无 mcp.py | Agent 面挂 P1;工作台走 REST |

## 任务(本批=批十九/T1–T7)

- [ ] T1 契约层 `bid_write/contracts.py`:SCHEMA_VERSION=1;`RESPONSE_MATRIX_CONTRACT`(行形
  `{clause_id, requirement, source_path, star, strategy: pending|full|positive|negative, target_section,
  evidence_refs[], status: draft|confirmed|blocked}`);`MATERIAL_ENTITY_TYPES` 六类(qualification/
  performance/personnel/capacity/network/past_bid)字段表(verifiable+anchor 占位,M0 仅类型枚举落库用);
  `COMMERCIAL_TENDER_SUBSET`(tender.* 商务子集路径清单,从 registry.universe 过滤 tender.* 商务面:
  attachment_requirements/required_tables/signature_slots/deposit/deadline/scoring_items/substantive_clauses(★)/
  boq_items/required_fields/required_sections);钉:契约形状自检 test(行必含键/枚举合法)。
- [ ] T2 模型+CRUD `models.py`+`crud.py`:`bid_write_tasks`(id/owner_id/status: created|parsing|extracting|
  matrix_ready|failed/progress/engine_meta/tender_no 等 identity 三件)与 `bid_write_matrix_rows`
  (task_id/clause_id/requirement/source_path/star/strategy/target_section/evidence_refs JSON/status,
  (task_id,clause_id) 唯一);crud 参照 bid_review/crud.py 状态机守卫;sqlite 测试夹具 `_TABLES`。
- [ ] T3 装配器 `bid_write/matrix.py`(纯服务端):`assemble_matrix(tender_fields) -> list[row]`——
  attachment_requirements 逐条成行(★/必需→star 标红)+substantive_clauses ★条款逐条成行+deposit/
  deadline/required_fields 聚合行;语义低置信/未归类→status=blocked(生成前置门);输出确定性可 golden。
- [ ] T4 worker `bid_write/worker.py`:`start_bid_write_worker`+`advance_task`——复用 bid_review
  parse_raw→extract(tender docs+SUBSET paths)→assemble_matrix 落库;状态机 created→parsing→extracting→
  matrix_ready/failed;模型函数复用 `_default_extract_fn` 同构(独立实例,不共享任务态)。
- [ ] T5 routers `bid_write/routers.py` 前缀 `/api/extensions/bid-write`:POST /tasks(multipart 招标
  文件)/GET /tasks / GET /tasks/{id} / GET /tasks/{id}/matrix / PATCH /tasks/{id}/matrix/{clause_id}
  (strategy/status 人工确认卡点:star 行禁 negative 直通,须 note)/GET /tasks/{id}/gaps(三态缺口:
  有且可佐证|有但缺佐证|无对应素材——M0 只有「无对应素材」态,素材库 P1 兑现前两态)。
- [ ] T6 gateway 接线:`app/gateway/app.py` include_router+create_all 注册(lifespan 同 bid_review 位);
  家族门命令扩 `-k "bid_review or bid_write"`(Makefile/计划文档记录);ruff 双清。
- [ ] T7 golden 夹具+收口:`golden/cases-write/` 首批 3 例(纯装配断言:给定 tender_fields →
  matrix rows 全量断言,含 ★ 标红/blocked/strategy 默认);spec 附录=四技能规格骨架(bid_letter/
  price_sheet/response_table/attachment_index:模板骨架+槽位定义+禁用词表+写后校验断言+失败降级,
  对应设计稿 F4 表格逐行);wolf 三件+closure;显式文件清单提交。

## 后续批次(挂账不入本批)

- **M1(批二十)**:F3 章节装配(目录树+分册份数页码方案)+F4 四技能生成器落地(读 T7 spec 骨架)。
- **M2(批廿一)**:F6 预审查(复用 rule_runner/eval_core L1/L2,输入=生成过程产出的 bid.*)+
  自动修复/待补清单分流+门禁口径(L4 不计否决沿用)。
- **P1**:F2 素材库(六类实体+佐证附件+缺口三态全兑现)/F5 policy+L4 前置控制(RISK→重写循环)/
  增量重审/审计。**P2**:评分驱动写作/结果回流/本体打通。前端三栏工作台随 M1 起铺。
