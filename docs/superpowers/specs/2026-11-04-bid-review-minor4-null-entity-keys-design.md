# Minor-4 NULL entity_keys 病理修复 设计

> 日期: 2026-11-04 ｜ 状态: 设计定版(实施中)
> 前置: L2-P2 终审 Minor-4 挂账(2026-11-02);gateway 已重启(2026-11-04 08:20)
> 范围: schemas.py + database.py 各一处 + 新 schema 测试;引擎/规则包/前端零改

## 0. 病理

跑过中间提交 bfde4add6 **裸 ALTER**(`ADD COLUMN entity_keys JSONB`,无 DEFAULT)的环境:
存量行 `entity_keys=NULL` **永久存续**——后续 bootstrap 的
`ADD COLUMN IF NOT EXISTS entity_keys JSONB DEFAULT '[]'::jsonb` 对已存在的裸列 **no-op**,
缺失的 DEFAULT 永远补不上。`IssueOut.model_validate` 遇 None 非 list → ValidationError →
`_with_review_state` 500 → `GET /tasks/{id}/issues` 与 `GET /issues/{id}` 全灭。

**活库实测**(2026-11-04):`eai-flow-postgres-ext` 153 行 0 NULL,列 default `'[]'::jsonb`
——本环境未中招,修复面向其他环境 + 防回归。写侧早已防御(crud/worker/投影 `or []`),
唯一缺口在 schemas 读路径。

## 1. 修复(双层)

1. **读路径腰带**(`schemas.py` IssueOut):`entity_keys` 加 `@field_validator(mode="before")`,
   None→`[]`。部署即愈,零运维。
2. **数据自愈**(`database.py` bootstrap,ALTER 行后紧邻):幂等
   `UPDATE bid_review_issues SET entity_keys='[]'::jsonb WHERE entity_keys IS NULL`
   ——裸 ALTER 环境下次 gateway 启动数据归一。

六裁决:①双层(仅 validator 留脏数据;仅 UPDATE 要等重启且 schema 仍脆);②单字段
field_validator(Annotated 全局版是给多字段复用的,此处一处);③evidence 不加同款
(建表既有列,无 NULL 来源,YAGNI);④每启动跑 WHERE IS NULL UPDATE,不加部分索引
(百~千行级表扫描可忽略);⑤新 test_bid_review_schemas.py 两测(NULL→[]/透传),
bootstrap SQL 文本不断言(脆);⑥全家 pytest 精确计数+golden 55/55 零翻红+活库复测+ruff。

## 2. 验收

1. 新 schema 测试 2 绿(先红后绿);
2. bid_review 全家 pytest 精确计数(基线 394/6 + 2 = 396/6 口径,claimer flaky 见 bug-3967);
3. golden CLI 55/55 exit 0(触碰面不涉引擎,跑一遍是确认);
4. 活库复测 0 NULL 不变;ruff 触碰文件绿。

## 3. 挂账

- 无新增。观测挂账不变:claimer_loop flaky(bug-3967)、真实模型回显遵从率。
