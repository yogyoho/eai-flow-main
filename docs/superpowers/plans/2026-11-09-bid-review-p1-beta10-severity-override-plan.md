# P1-β批十:severity_override 卡级机制 v1(plan)

日期:2026-11-09 · 分支:main-dev-fork · 前置:批九收官(29d869e07,门 749p/6s/0f) · 挂账来源:批七 T2「severity_override 机制(L1-022 major 固定)」=C-11 第 3 条(W3 行:L2-041 fatal=EAI 上调,现仅注释承载,无结构化可审计通道)

## 裁决

| # | 裁决 |
|---|---|
| A-β10-① | **范围锁**:批十 = C-11-③ severity_override **卡级注记机制 v1**——生效 severity 仍=卡 `severity` 字段(零行为变化);零宇宙/零锁数字/零 golden/零规则增删。L1-022「major 固定」的**维度级 severity 分裂不在本批**(and-form 单 issue 出单 severity 是 v1 语义,无 live 需求,YAGNI;挂账措辞收窄为「维度分裂另批」)。已知偏离集(controller 全包扫描 2026-11-09)= **{L2-041}**(spec major→repo fatal,W3 行裁决在案),其余卡零偏离。 |
| A-β10-② | **契约**:Rule 新可选尾字段 `severity_override: dict \| None = None`(default None→既有构造零扰动,issue/payload 面零新增——注记是载入期审计面非 issue 面)。卡形态:`severity_override: {spec: <档>, reason: <非空文>}`;语义=声明 `severity`(生效)偏离规格档 `spec`。载入校验(左移律,bug-4260 同构,RulePackError):spec/reason 缺失或空→拒载;spec ∉ severity 域(域=registry 层档域常量复用,禁复制第二份)→拒载;`spec == severity` 等值注记=噪声→拒载。 |
| A-β10-③ | **双向钉**:载入校验拦「带注记但形态非法」(T1);registry 反向钉拦「已知偏离但无注记」(T2,随卡注记同 commit 落,保持每 commit 全绿):`{"L2-041"} ⊆ {带 severity_override 的卡 id}`,新偏离入集须同批带注记+注释援引 C-11-③。 |
| A-β10-④ | **验证协议**:家族门全绿只增;lint 仅本批文件(check+生产 format --check);golden 面零触碰零 diff;spec 批十兑付段+wolf 记账 controller 直办;L1-022 卡 :1123 挂账注释随 T2 更新(注释面)。 |

## 任务分解

- [x] **T1(实现者)**:rule_runner.py——Rule 尾字段 `severity_override`(dataclass default None)+load_rulepack 解析(仅当卡带该键时校验,RulePackError 逐条带规则 id;域常量自 registry 导入)。tests/test_bid_review_registry.py 新 TestSeverityOverride 四拒载钉(spec 缺失/域外/等值/reason 空,tmp_path 合成卡风格同 TestLoadRejection)+真包回归钉(既有包加载零噪声,批九后 60 卡全绿)。禁触:rulepack yaml、golden、五锁数字面、.wolf/、docs/。→ **已兑付 a87e64145**(2 文件 +95/-0):五拒载分支(spec 缺失/域外/等值/reason 空/非 dict,带键即校验显式 null 同拒)+域=registry SEVERITY_BY_LAYER 全层并集复用+浅拷贝防 yaml 锚别名;钉 7 枚(四拒载+形态+正钉+真包零噪声);家族门 749→756p/6s/0f。
- [x] **T2(controller 直办)**:L2-041 卡注记块(`severity_override: {spec: major, reason: C-11-③ EAI 上调:必填清单行缺价属实质性不响应,与 L1-011 漏项同档(规格 W3 行裁决)}`)+registry 已知偏离集钉+rulepack :724/:1123 注释随迁(L1-022 挂账措辞改「机制 v1 已兑付(批十),维度分裂另批」)+家族门+spec 批十段+plan 勾+wolf/会话记忆。→ **已兑付 7ef22384d**(yaml 3 hunk+registry 钉):卡注记落 :739 后;registry 钉升级 zero-noise→**已知偏离集精确相等 annotated=={L2-041}**(多注记/缺注记双红——T1 时点「全 None」断言随 T2 同 commit 失效,故合并换钉保每 commit 全绿);:724/:1123 注释随迁;门 756p/6s/0f 持平(worker claimer 一轮计时伪红,单跑过);lint 双清。

## 挂账延续(批十后)

keywords ASCII 精化(记档维持)、severity_override 维度级分裂(L1-022 and-form 单 issue 语义,另批)、L1-026 方式集维、L1-004 business_items 跨引、L2-030↔required_signatures 关系、bid.fields 别名、bid.submit_method、生产侧 21 叶键 live 验证(live 批);severity_override 机制 v1 **销账**(本批兑付)。
