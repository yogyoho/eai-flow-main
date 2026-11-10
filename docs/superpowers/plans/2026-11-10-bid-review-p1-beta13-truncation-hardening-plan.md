# 批十三:截断加固(bid-review P1 β13)计划

日期:2026-11-10 · 分支:main-dev-fork · 前置:批十二(1cc78b084)
用户裁决:「① 截断加固批」(2026-11-10)

## 背景

批十二 leafkeys 探针活体发现分片 JSON 输出截断债(bug-4086 族)跨五段 8 次警告,
列 NEXT 头号候选。本批定根因、修真因面,零锁面(config.yaml 零触碰)。

## 根因分型(2026-11-10 leafkeys stderr 全量 + worker.py :143-164 对读)

| 型 | 证据 | 机制 | 本批处置 |
|---|---|---|---|
| A 真截断(cap 压力) | variance 基准 attempt-1 len=10943 mid-JSON 破损(Expecting ',' delimiter char 10877)→attempt-2 9677 重发救回 | config.yaml 模型 `max_tokens: 8192` per-call 输出上限;SHARD_CHARS=30_000 字分片大输出近/超顶;三试皆截断→RuntimeError→段归零(Nov-6 tables 4调3败先例) | T1-b per-call bind 上调 |
| B 假截断(尾随杂文) | walkthrough 基准 12966/附件 241·664/章节 346/表格 2438/业绩 41×2——全部零 parse retry 行=首试即解析成功;输出不以 `}` 收尾(JSON 后缀说明杂文),first-{..last-} slice 本就救得回 | `_invoke_json` :153 在解析**前**无条件 warn "looks truncated" | T1-a 警告移入解析失败路径 |
| C 非截断(模型空返回) | variance 业绩 41-char 解析为 entries=0(2026-11-06 同夹具曾 [2,3]) | 模型质量方差,非截断 | 记档不修(live 方差族,另批) |

## 裁决表

| 杠杆 | 裁决 | 理由 |
|---|---|---|
| per-call max_tokens bind 上调 | **做**:默认 12288,env `EAI_BID_REVIEW_EXTRACT_MAX_TOKENS` 可调,≤0/非法→None 回退模型配置值 | 只 bind 基准提取模型(sem/hyb 裁决输出小,不动);config.yaml 零触碰;12288 覆盖活体最大需求 12966 字(≈8k token)+余量;provider 若拒上限,运维调小 env |
| 截断 JSON salvage 解析(括号闭合抢救) | **挂账**:条件触发——live 复采仍现三试皆截断再开(另批) | cap 上调后今日失败集全覆盖;salvage ~40 行只付三试全炸场景,YAGNI |
| 分片再切(SHARD_CHARS↓) | **挂账** | 输出侧已修;再切=调用量↑成本↑延迟↑,留观 |
| 重试纠错话术加压缩逃生口 | **做**(一行) | 硬 cap 截断时模型无法靠「不要截断」自愈,给「压缩输出」真出口 |

## 任务

- [x] T1 引擎加固(worker.py + 测试钉):`_invoke_json` 截断警告移入解析失败路径(成功+杂文缀尾=零日志降噪);纠错话术追加压缩逃生口;`_extract_max_tokens()` 三态读取 + `_default_extract_fn` bind(max_tokens);测试钉:env 三态 + 杂文缀尾成功零警告零重试 + 截断警告移位重试救回。门禁 family `-k bid_review` 只增(基线 756p/6s/0f),lint 双清。零锁面。→ 兑付 4bfd1bad8:759p/6s/0f(+4 钉,prod_model fake 补 bind 契约面钉 12288+fixture 去 env 干扰)。
- [x] T2 live 复采:gateway restart(生产面吃新代码)+ leafkeys 探针重跑,对照批十二基线(variance m1=3/m2=4/m3 boq=5·cells=12;walkthrough copies=4/sealing 密封条/page_numbering true/pm.certs=[]);期望:真截断 warn 消失、基准 attempt-1 成功、stage 统计只升不降。provider 拒上限→env 降档重跑(降档写进 spec)。→ 兑付:三轮探针(12288×2 + env=0 对照 B)——bind 轮零截断零假警告、variance 136→77s/walkthrough 63→27s 重试往返消失;对照 B 基准提取真截断复发(11561 字 mid-JSON)=bind 有效性反证;walkthrough 叶键值面两轮全 null 与 bind 无关=服务端模型漂移记档(批十二 5+5 语义锚降格历史观测,不可硬化);新形态表格 len=0 空输出重试救回。
- [x] T3 收口:plan 勾兑 + spec 批十三段 + wolf 三件(memory/cerebrum/buglog)+ session memory + closure 报告。→ 兑付 bug-4269 + cerebrum 三 learning + spec 批十三段 + session memory。

## 门禁

family `-k bid_review`(基线 756p/6s/0f)+ `ruff check` touched + `ruff format --check`(非 tests)。
锁面冻结:universe 126/首段 114 · det 51 · pack 60 · golden 83 · EXPECTED_COVERAGE 60。
锚纪律:live 指标只升不降(0.8077 / 0.7308 及批十二 stage 基线)。
