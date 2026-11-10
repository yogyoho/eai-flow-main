# P1 挂账裁决清单(批十一前置 brief)

日期:2026-11-10 · 分支:main-dev-fork · 性质:**裁决稿**(controller 依据代码事实起草,用户逐项或按建议裁决;批准项落地时才动代码/注释,本文只记裁决)
事实核查基线:rulepack 1.0.0.yaml @3d35c1456 + engine/extract.py FIELD_TYPE_CONTRACTS 全量键清单(2026-11-10 grep)。

## 裁决表

| # | 挂账 | 代码事实 | 选项 | **建议裁决** |
|---|---|---|---|---|
| ADJ-1 | L1-026 方式集维 + bid.submit_method(同根合一裁) | L1-026 det 单支 `bid.submit_time <= tender.bid_deadline`(:1157);tender 侧**无**「允许递交方式集合」字段源(注册表无 tender.allowed_submit_methods);bid.submit_method 无生产者无消费(:1148 注:「规格无允许集合字段源,无消费不落」) | A) 新增 tender.allowed_submit_methods 契约+抽取 prompt 扩+L1-026 第二支 det;B) 直接 YAGNI 关闭;C) **live 批先验**——21 叶键 live 验证同批看 tender 文本能否稳定抽出方式集合,可则触发 A | **C**(条件触发 A):无失败案例不动抽取契约(与 keywords ASCII 同纪律);每加一键=prompt 成本+golden 面+宇宙锁三处维护。live 回采给出真值可行性后再决定落或不落 |
| ADJ-2 | L1-004 business_items 跨引(:1087 A-β7-④ 窄化) | L1-004 已窄化 det_expr=count(certs)>=1;类别/社保/无在建/主体核验四维由 hyb stage2 模型确认面承担;business_items 全库仅存 :1087 注释,无键无生产者 | A) 新增 bid.pm.cert_items 结构化键让 det 做类别集合比对(与模型面双判重复);B) **维持窄化并销账**——窄化本身就是 A-β7-④ 的裁决,comment 措辞从「挂账」升格为「裁决维持」 | **B**:det 重复建模模型已判的语义是反模式(窄化动机即此);销账免每批携带。落地动作=仅 :1087 注释措辞更新,零行为 |
| ADJ-3 | L2-030↔required_signatures 关系 | 两键并存**语义异源**:tender.signature_slots=结构化签署位清单 [{no,name}](L2-030 按 no 核位置完整性);tender.required_signatures=字符串名称列表(L1-007 按名称核存在性);字段源为招标文件不同章节 | A) 合一键迁移(动 golden 夹具+双消费方);B) **各守其职+注释声明分工**(L2-030=位置 by no,L1-007=名称 by name);C) 服务端派生别名(制造虚假同源耦合) | **B**:合并会伪装同源(取证域不同),分工零代码。落地动作=两卡注释+extract.py 两契约描述各加一句分工声明,零行为 |
| ADJ-4 | bid.fields 命名空间别名 | 文件清单类六键并存:bid.files/bid.file_index/bid.attachment_index/bid.attachments/bid.archive_files/bid.electronic_files——但契约描述显示**取证域互斥**(上传文件系统面/目录页/附件清单页/附件实体/压缩包内清单/电子文件要求),各有独立消费方(L2-001/002/003/050/051 等) | A) 合并归一(大迁移动五锁/golden);B) 别名映射层;C) **维持现状+销账**——「别名」实为不同取证域命名,真正别名问题不存在;落地动作=extract.py 六键契约描述各加取证域半句,零行为 | **C**:先有「多键=乱」的直觉假设,拉清单后发现是取证域差异;为不存在的别名问题建映射层=纯负债 |
| ADJ-5 | keywords ASCII 精化 | 无失败案例(批六起历次记档维持) | 维持 | **维持不动**(无争议,列此仅为完整性) |

## 净效果

批十一若按建议全裁:挂账 9 项 → **2 项**(severity_override 维度级分裂另批 YAGNI + 生产侧 21 叶键 live 验证 live 批)。代码面净改动≈零:ADJ-2/3/4 仅注释/契约描述措辞,ADJ-1 无动作待 live。其余挂账(bid.fields 别名)自本 brief 起从每批携带清单中消失,以本 brief 链接替代。

## 落地形态(裁决批准后)

单小批(批十一):T1=ADJ-2/3/4 注释措辞三处+契约描述六句(controller 直办,注释面);T2=spec §6 挂账清单改写+本 brief 链接回填;门预期持平(注释面零钉变动,registry 精确相等反向钉不受影响)。
