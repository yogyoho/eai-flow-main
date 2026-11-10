# 批十四:引擎修复批(bid-review P1 β14)计划

日期:2026-11-11 · 分支:main-dev-fork · 前置:真实件回采(917827881,未推 1)
用户裁决:「① 批十四引擎修复批」(2026-11-11)

## 背景

真实件回采(中煤科工·环评平台招标/投标)审查首发 gate=NOT_SUBMITTABLE/10 条,判读出四件
真缺陷;本批修引擎面可修的三件(W-real-1/2/3),W-real-4(抽取契约扩面)与 OCR 管道边界
另裁。零锁面目标:universe 126/首段 114 · det 51 · pack 60 · golden 83 · EXPECTED_COVERAGE 60。

## 根因与修法(调查 2026-11-11,expr.py/rule_runner.py/golden 对读)

| 缺陷 | 根因机制 | 修法 | golden 面 |
|---|---|---|---|
| W-real-1 容器键未解包 | 抽取回 `tender.max_price={value:230000,unit:元}` dict;`_BIN` 用裸 `operator.le`,`str <= dict` TypeError **逃出 KeyError 网**→ERROR(非 need_human) | 新 `num()` builtin(dict{value} 递归解包;str 剥空白/逗号/%/元;int/float 直通;bool 与不可解析→KeyError=need_human 诚实路)+ L1-009 left/right 包 `num(...)` | 4 case 全 float 直通,零翻转 |
| W-real-2 税率归一化缺失 | L1-012 cond `r.value == tender.tax_rate`:「6%」str vs 6 float → False → 假阳性 FAIL | 同一个 `num()`;L1-012 cond → `num(r.value) == num(tender.tax_rate)` | golden 用 0.09/0.13 float 直通,零翻转 |
| W-real-3 漏项渲染垃圾 | `codes` lambda `[r.get("code") for r in rows]` 不过滤 None/'' → message 「漏项 ,增项 None」 | codes lambda 加 falsy 过滤(一行) | golden L1-011 全码在场,零翻转 |

## 裁决表

| 杠杆 | 裁决 | 理由 |
|---|---|---|
| `num()` builtin(双表注册 _FUNCS+_BUILTIN,批八 years() 先例) | **做** | 一个 builtin 同时兑付 W-real-1/2;KeyError 网复用=不可解析诚实 need_human;只收已证形态(dict{value}/%//,/元/空白),万/亿乘数挂账 |
| `_BIN` 比较算子全局 TypeError→KeyError 硬化 | **挂账** | 改所有规则 verdict 面(ERROR→need_human 迁移),风险广;卡面 num() 已覆盖已证缺陷;真实件三试后再裁 |
| L1-009/L1-012 卡面包 num() | **做** | 显式、rulepack 可读;`fields_used()` 只收 bid/tender/project 前缀 token,num 不入集→universe/EXPECTED_COVERAGE 锁面不动 |
| codes() falsy 过滤 | **做** | 一行;渲染垃圾根因在 codes 出口非 _tpl |
| skill 副本 `skills/public/bid-proposal-review/scripts/eval_det.py` 镜像 | **做**(同批) | 副本 :214 有独立 codes lambda 与独立白名单;改后卡片用 num(),副本不同步=技能侧拒载;num 无量词,属副本子集,可镜像 |
| golden 新 case | **不做** | 锁面冻结 83;真实件形态钉在单测(runner/expr 层) |
| 万/亿 乘数、`num()` 支持列表 | **挂账** | 真实件未见此形态,YAGNI;出现即 KeyError→need_human 诚实 |

## 挂账(本批不碰)

- **W-real-4 抽取契约扩面**:7 键 UNKNOWN + 业绩表漏抽 + deposit_required 布尔化——prompt/契约层,另批。
- **OCR 管道边界**(大项):投标主体扫描图片无 OCR→m1 附件空→L2 链饿死→保证金真违规(300 vs 10000)静默。
  已有锚:`eai-flow-ocr` 容器 :8010(rapidocr,eai-docker compose 服务 `ocr`)。
  **OCR 批开工时提醒用户提供 paddleocr-vl**(用户 2026-11-11 明示)。
- `_BIN` 全局硬化(见裁决表);ADJ-1 方式集字段批(先验已过,可并批)。

## 任务

- [x] T1 引擎面(expr.py + rulepack 1.0.0.yaml + skill 副本镜像 + 测试钉):`num()` 双表注册(批八
  years() 先例,漏一表=eval 期 KeyError 伪装 need_human);codes falsy 过滤;L1-009 left/right、
  L1-012 cond 包 num;钉:num 形态表(dict 解包/%/千分位/元缀/直通/bool 拒/不可解析 KeyError)+
  L1-009 容器键真实件形态(dict max_price+str 总价→PASS/FAIL 正确)+ L1-012「6% vs 6」假阳性
  消失钉 + L1-011 None 码渲染净钉。门禁 family `-k bid_review` 只增(基线 759p/6s/0f),lint 双清。
  → 兑付 1b5997566:764p/6s/0f(+5 钉),lint 双清;skill 副本 eval_det.py 单表镜像 selftest OK
  (副本 runner 只捕 KeyError→need_human,镜像 raise KeyError 对齐;续行注释漏 # 一次修)。
- [x] T2 真实件复采:gateway restart + realcase 探针重跑(wait_confirm 默认全链路),判读:L1-009
  ERROR 消失(可判 PASS/FAIL)、L1-012 6% 假阳性消失、L1-011 渲染净;对照批首 10 条基线只升不降
  (新增违规=合理捕获记档,noise=回滚)。走 stderr 判读,JSON stdout 落 /tmp。
  → 兑付:3/3 样本全链路+定点 issue 级补查——L1-009 ERROR 消失(225000≤230000 正确 PASS 零
  issue)、L1-012「6%」vs 6 假阳性消失(零 issue)、L1-011 垃圾消失(本样本 boq=None→诚实
  UNKNOWN;垃圾形态单测钉覆盖);无新增假阳性,余下 FAIL(L1-002+L1-016×4 执照名抽成证书名)
  =W-real-4 域既有挂账;批十三机械正常(1 截断警告 retry 救回)。
- [x] T3 收口:plan 勾兑 + spec 批十四段 + wolf 三件(memory/cerebrum/buglog)+ session memory +
  closure 报告。→ 兑付 bug-4274 + cerebrum 两 learning(wolf 共享 JSON 变更律/副本镜像律)+
  spec 批十四段 + session memory。

## 门禁

family `-k bid_review`(基线 759p/6s/0f)+ `ruff check` touched + `ruff format --check`(非 tests)。
锁面冻结:universe 126/首段 114 · det 51 · pack 60 · golden 83 · EXPECTED_COVERAGE 60
(卡面 cond 编辑不改计数;fields_used 只收 bid/tender/project 前缀,num 不入集)。
