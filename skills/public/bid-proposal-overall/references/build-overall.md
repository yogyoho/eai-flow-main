# 阶段4: 整体方案册集 build(--docs overall)分组执行指南

进入条件: 确认门1 已过(snapshot `phase` ∈ {3/4-合并与构建})。命令照抄 SKILL.md 速查表; 本文讲 --docs 范围语义与判据, 不重复罗列调用。

## 调用与范围(spec §3.2)

- `build_output.py --state-dir … --out … --docs overall`: 只重写整体方案册组 + 索引卷整体方案节; 技术卷册组与四张副表不触碰。
- `--docs all`(默认): 两组全量 + 索引全量 + 四张副表(偏离表/覆盖率报表/人核清单/实体lint报告——跨两卷聚合, all 专责重建; 重建前确认 B 响应已 merge)。
- `--docs technical` 属配对技能 bid-technical, 本技能不发起。

## 合并语义(两技能共享 outputs/ 的契约)

1. **manifest 合并**: 读既有 delivery_manifest.json → 本次范围内条目更新, 范围外原样保留(deliverables/files/docs 三处); `skill` 字段恒=`bid-proposal-overall`(契约属主, B build 不翻转)。
2. **清场收窄**: 只删本次范围前缀的 stale 册(overall=`整体方案-*`; all=两组+副表+v3 遗留双卷); 范围外 stale 留给对应技能自清——A 不清 B 的技术卷册。
3. **索引卷分区重写**: 重建组 fresh 渲染; 未重建册组节以盘上既有索引原样保留(含旧节头/计数); 盘上无既有索引/该节缺席 → 该节略去(该组从未 build 是合法态)。
4. **交付契约标记与凭据**: 任一范围 build 成功即激活/更新 `.delivery-contract` 与 manifest(线程级, 不受 --docs 影响); 实体门 blocked → 本轮不写凭据且**作废旧凭据/标记**(见排错——这是凭据丢失的来源之一)。
5. **cross_scope_stray 异常**: 单范围 build 发现盘上有范围外册文件未并入交付凭据(疑似凭据丢失/被 blocked 清除) → 摘要 anomalies 报 `cross_scope_stray`(rc=3), 恢复=两范围各重跑一次 build 合并凭据。

## 与 bid-technical 的接缝(spec §3.3)

- 整体方案技术章渲染**占位页**(逐字章标题+技术卷分册目录+指引, 零技术正文内联); 分册目录=当前 state 的确定性投影(与 B 是否已 build 无关)。
- B build --docs technical 后重跑本技能 --docs overall 即刷新占位页目录; 册文件确定性幂等, 重跑字节一致。

## 排错

- 实体门 blocked: 本轮不写凭据, 交付门全禁 .md, 旧凭据/标记被作废——处置: 确认候选白名单入册(见 实体lint报告.md)或回 B 的 stage4a 重写响应后重跑; **恢复合并凭据=两范围各重跑一次 build**。
- 凭据缺失两种形态: manifest 文件不在(cross_scope_stray 异常会点名范围外册文件)与 manifest 损坏不可解析(清场跳过告警, 不做删除)——两者都指向同一恢复路径: 排除 blocked 根因后两范围各重跑一次 build。
- 深度异常(depth_below_target/depth_below_floor): 质量牵引非废标风险, 只进 实体lint报告.md"深度"节与摘要 anomalies; 基线缺失=门跳过(skip_reason 随摘要呈现, bid-technical/references/depth_targets.json 未编译是合法初态)。
- `--docs` 非法值: argparse 拒绝 → 退出码 1(与其它用法错误同通道)。
- 退出码 3=完成但有异常项: 读 stdout 单行 JSON 摘要逐项呈现, 不是失败。
