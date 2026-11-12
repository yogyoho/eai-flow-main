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

## 任务(本批=批十九/T1–T7,2026-11-13 全部兑现)

- [x] T1 契约层 `bid_write/contracts.py`:SCHEMA_VERSION=1;矩阵行/素材六类/槽位八型/D0-D3
  降级/FORBIDDEN_WORDS(五类归并,D0 红线+D1 模糊面)/COMMERCIAL_TENDER_SUBSET(21 条真实
  宇宙路径)/assertion_id·error_code helpers。钉:test_bid_write_contracts(8 例,subset⊆universe 幽灵拒载律)。
- [x] T2 模型+CRUD `models.py`+`crud.py`:bid_write_tasks(TBW-单号/created→parsing→extracting→
  matrix_ready|failed)+bid_write_matrix_rows((task_id,clause_id) 唯一/strategy 默认 pending);
  replace_matrix M0 全量重置诚实口径(P1 保留 confirmed 挂账)。
- [x] T3 装配器 `matrix.py`:三类行源(附件逐条/承诺逐条/聚合 15 要素)★逐行判定(包级继承
  bug 首版 golden 抓到已修)/blocked=未验且 conf<0.6/缺路径不造行/摘录 cap120 省略号/
  (kind,clause_id) 稳定排序。golden 7 例。
- [x] T4 worker:复用审查端 parse 链+`_default_extract_fn` 同构(模型名/invoke_json/max_tokens
  绑定);run_tender_extract=tender docs+SUBSET 路径;advance_write_task 只-from-created 守卫,
  异常回滚落 failed(str[:2000])。
- [x] T5 routers `/api/extensions/bid-write`:POST /tasks(multipart+save_raw 复用+后台直推)/
  列表(matrix_counts)/matrix 读(词汇回显)/PATCH 行级卡点(★negative 须 note/blocked→confirmed
  须 note/枚举 422)/gaps 诚实伪零。测试 8 例(双 override 夹具同审查端形态)。
- [x] T6 gateway 接线:app.py import+include_router(EAI-CUSTOM 两行,审查端零改动唯一既有文件
  改动);家族门扩 `-k "bid_review or bid_write"`;ruff 双清。门 796p/6s(1f=claimer 满载间歇,
  bug-4013 类非本批,预算 300→600 加位)。
- [x] T7 golden+断言注册表+spec:`golden/cases-write/p0-matrix.yaml` 3 例(CW-1 全要素/CW-2
  空诚实零/CW-3 ★不继承回归钉);`assertions/p0.yaml` 38 条(BL10/PS10/RT9/AI9,规则锚只钉
  真实 id,规格原引 L1-018/L3-015/L2-010/L2-042/L4-011 映射裁决进 spec §6);spec=
  `docs/superpowers/specs/2026-11-13-bid-write-p0-skills-spec.md`;钉 test_bid_write_assertions 6 例。

## 后续批次(挂账不入本批)

- **M1(批二十)**:F3 章节装配(目录树+分册份数页码方案)+F4 四技能生成器落地(读 T7 spec 骨架)。
- **M2(批廿一)**:F6 预审查(复用 rule_runner/eval_core L1/L2,输入=生成过程产出的 bid.*)+
  自动修复/待补清单分流+门禁口径(L4 不计否决沿用)。
- **P1**:F2 素材库(六类实体+佐证附件+缺口三态全兑现)/F5 policy+L4 前置控制(RISK→重写循环)/
  增量重审/审计。**P2**:评分驱动写作/结果回流/本体打通。前端三栏工作台随 M1 起铺。
