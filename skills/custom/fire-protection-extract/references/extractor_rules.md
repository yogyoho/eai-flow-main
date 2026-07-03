# 抽取与溯源规则

## 三分类（每 fire 小节必标 class）
- `verbatim` 抄：从说明书逐字摘。source 必填。
- `template` 填：固定文本（标准清单/法规），用 mapping.templates[name]。
- `compute` 算：说明书无此数据（如§7投资概算），输出 `[需计算]`，绝不伪造。

## source 三种 kind
- `para` {anchor}：anchor=目标源段的唯一子串。复制含该子串的整段。
- `para_run` {from,to}：从含 from 的段到含 to 的段（闭区间），逐段复制。
- `table` {no}：表号如 `表3.1-1`，整表复制。

## 防抄错
1. 锚定位（非相似度）→ 防抄错段/错表。
2. `authoritative: true` → 冲突字段权威源。如消防水量取消防章（30L/s/DN200），不取给水章（8L/s/DN150）。
   生产校验由 grounding_check 读 yaml 的 `conflict_assertions: [{must_contain, must_not_contain}]` 完成（如§5.1 要求 DN200 在、DN150 不在）。
3. 逐字溯源校验 → 抄录块必须是源子串，否则标红。
4. 覆盖检查 → 每小节有源或标 template/compute，否则报警漏抄。

## 未命中处理
锚/表/区间在源里找不到 → 输出 `[⚠未找到...]`，**绝不静默跳过、绝不编造**。此时要么修契约锚，要么说明书结构变了（触发 cerebrum 记录的"投影"失配，需人工校准契约）。

## 锚选取
锚从「样本对」逐段比对得到，选源段里独一无二、抗改写的子串（含具体数值/编号/专有名词最佳）。换项目时锚可能失配——这是契约需要校准的信号，不是引擎 bug。
**⚠ 锚必须全局唯一**：`find_para` 返回第一个含锚的段。若同一子串在多段出现（典型陷阱：消防水量在
§9.1 给水段和 §9.2 消防段都以「室外消火栓水量30L/s」开头），必须把锚落在目标段**独有的续文**上
（如 §9.2 独有的「生活用水量10L/s」，§9.1 是 8L/s），否则会静默抄到错误段落——这正是要防的"抄错数值"。
grounding_check 的冲突断言（DN200 在 / DN150 不在）是这条的兜底验证。

## YAML 注意
PyYAML (YAML 1.1) 会把裸键 `no`/`yes`/`on`/`off` 强制成布尔。本契约的表号键必须写成 quoted 形式 `"no":`（已如此）。

## 复用件
- 解析：本技能 `scripts/parse_spec.py`（替代 v2 的 docx_to_md.py 用于结构化抽取；纯文本场景仍可用 v2 的）。
- 合规校验：`skills/custom/fire-regulatory-compliance-check/scripts/compliance_checker.py`（10 项 GB 检查）。
- 输出：write_file 到 outputs/ + present_files（沿用 v2 写盘铁律，一次写完）。
