# P1-β批八:引擎卫生小批(plan)

日期:2026-11-08 · 分支:main-dev-fork · 前置:批七收官(09e3ebc87)+ merge a173ee7c2 危险面已解除(验 tip 六点过,736p/6s/0f)

## 裁决

| # | 裁决 |
|---|---|
| A-β8-① | **范围锁**:批八 = 引擎卫生三件——T1 `years()` 文本提取原语(expr.py)、T2 `_collect_exprs` dict 分支收窄(rule_runner.py,bug-4260(原记 bug-4228,撞号重编)同类左移)、T3 FIELD_LABELS 54 路径扫尾(labels.py,controller 直办)。**零规则/零宇宙/零题**:包 59(det 50+hyb 7+sem 2)/宇宙 126/首段 114/golden 82 题/EXPECTED_COVERAGE 59 五锁不得动。keywords ASCII 精化**不落**(批七 T3 记档「无失败案例不改匹配语义」维持挂账);L2-024 年份连续性规则本体仍挂账(A-β6-③:规格「无法解析→UNKNOWN」语义 v2 裁决,本批只落引擎原语不造规则)。 |
| A-β8-② | **years() 契约**:文本提取原语——`years(文本) → int|None`,识别中文数字年数(「三年」「三年以上」)与阿拉伯数字(「3年」「近3 年」);解析失败/无年份语义 → `None`(上层据 null 走 unclear/UNKNOWN 通路,bug-4227 律:null=不在场)。注册进 `_FUNCS`,实现与既有 `_number_to_words` 同层。**禁造消费者**:批八不加任何调用 years() 的规则(rulepack 零 diff)。 |
| A-β8-③ | **dict 分支收窄语义**:载入期校验扩为「dict 形态项仅 `steps` 合法(且须带 expr 键,bug-4260 门维持);`all`/`any`/`values` 列表出现 dict 项 → RulePackError 拒载」。依据:eval 面对三键列表只 `str(e)`(dict 渲染垃圾串),`values` 更是无 op 消费的防御通道——静默吞 dict 项=校验面谎报覆盖。存量包零触(现包三键全部字符串项)。 |
| A-β8-④ | **labels 扫尾口径**:FIELD_LABELS 补 `registry.universe() - FIELD_LABELS` 差集 54 路径(2026-11-08 实测:universe 126/labels 72/missing 54/labels 超集 0);命名=抽取契约中文首短语,纯数据表零逻辑;`label_of` 回退语义不动;保持「labels ⊆ universe」性质(现测试无此钉,随 T2 顺带补一钉防新路径漏挂 labels 复发——批六起沿袭的扫尾债即此因)。 |
| A-β8-⑤ | **验证协议**:家族门 `cd backend && PYTHONPATH=. uv run pytest tests/ -k bid_review -q` 全绿(基线 736p/6s/0f,本批新增 tests 只增 p 不减);lint 门只对本批改的文件 `ruff check` + 生产文件 `ruff format --check`(cerebrum 律:tests/ 不跑 format --check)。spec P1 段批八兑付段 controller 落账收尾。 |

## 任务分解

- [x] **T1(实现者)**:years() 原语 + dict 分支收窄。expr.py:`_FUNCS` + `_years()`(A-β8-② 契约,含中文数字复用 `_number_to_words` 逆映射可用部分的判断——若无现成逆映射则自带小表,不引入依赖);rule_runner.py:`_validate_dict_steps` 扩面(A-β8-③,函数名/注释随语义更新,RulePackError 文案含列表键名与规则 id)。tests:years() 三类钉(中文数字/阿拉伯/解析失败 None)+ 收窄双钉(steps 缺 expr 维持拒载/all 内 dict 项新拒载;存量包 lint 零噪声回归)。禁触:rulepack yaml、golden、五锁测试文件数值面。
- [x] **T2(controller 直办)**:labels.py +54 行 + registry 测试补「labels ⊆ universe」钉(A-β8-④)。纯数据,controller 不派实现者。
- [x] **T3(controller)**:家族门全绿 + lint 门 + spec P1 段批八兑付段 + .wolf 记账(memory/cerebrum)。
- [x] **T4(controller)**:plan 复盘勾选 + 会话记忆更新。

## 挂账延续(批八后)

severity_override 机制、L1-026 方式集维、L1-004 business_items 跨引、L2-030↔required_signatures 关系、bid.fields 命名空间别名、bid.submit_method、L2-024 年份连续性规则本体(v2 语义)、keywords ASCII 精化(无失败案例不动)、生产侧 21 叶键真值 live 验证(live 批)。
