# ore_packs — 矿种知识包 schema 契约（v2.0）

本目录存放**矿种知识包**（每矿种一个 `<ore slug>.json`），供 geological-report 技能开题时装载数据驱动的矿种知识，取代 v1 的 prose 硬编码（prose 不可校验、不可批量孵化）。

- **契约活样例 = [`copper.json`](./copper.json)**：首实例即契约，机器可校验器以它校准（改动契约常量须保证其 PASS）。
- **契约真源** = 本文档 + `backend/app/extensions/geo_samples/ore_pack_schema.py`（`validate_ore_pack` 纯函数校验器，两处同步）。
- **孵化管线约定**（P5）：LLM 抽取草稿必须过 `validate_ore_pack` 才可 approve 落 repo；errors 非空的草稿仍落草稿表供人审可见，approve 前置 = `errors == []`。

## 校验器用法

```python
from app.extensions.geo_samples.ore_pack_schema import validate_ore_pack

errors = validate_ore_pack(doc)  # 中文错误串列表；[] = PASS
```

## 1. 必有元数据键（REQUIRED_META）

| 键 | 说明 |
| --- | --- |
| `version` | schema 版本，当前 `"2.0"` |
| `ore` | 矿种 slug，见 §5 词表 |
| `generated` | 生成日期（`YYYY-MM-DD`） |

附加：`std_ref`（规范出处串）——copper.json 实例携带，白名单内可选键。

## 2. 业务键白名单（KNOWN_BUSINESS_KEYS，顶层键只允许本表 + 元数据键）

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `basic_analysis_items` | 数组 | 基本分析项目（如 `["Cu", "Ag", "Au", "S", "As"]`） |
| `phase_analysis` | 对象 | 物相分析；**必含 `zone_split_rule` 子对象**（见 §4） |
| `ore_natural_types_anchored` | 对象 | 矿石自然类型（`sample_verbatim` 锚定） |
| `byproduct_policy` | 串 | 伴生组分评价政策（formulas L11 锚定） |
| `bulk_density_practice` | 对象 | 小体重样统计实践（formulas S1 锚定） |
| `green_exploration` | 串 | 绿色勘查要求 |
| `typical_deposit_models` | 对象数组 | 典型矿床式（`{model, host, analogy_sample}`） |
| `reporting_notes` | 数组 | 报告叙述要点 |
| `std_ref` | 串 | 规范出处 |

白名单外的顶层键一律报「未知键」拒绝（防 LLM 自造键漂移）。

## 3. 锚点守卫（防 prose 复辟）

全文（含嵌套值，序列化扫描）须引用 **≥1 个** formulas 编号：

```
L11 / S1 / B1 / E3 / E4
```

（集 = copper.json 实例使用的估算链公式表编号；L=伴生、S=体重、B=选矿、E=经济链。）
零引用 = v1 prose 复辟，直接拒绝。

## 4. 【待核实】形态守卫

未核实的阈值**禁止**写成裸串断言，必须用机器可识别的结构形态：

```json
"zone_split_rule": {"status": "【待核实】", "note": "氧化率分带阈值须对照规范原文录入 standards_index 后自动判定"}
```

规则：
1. `phase_analysis` 存在时必含 `zone_split_rule` 子对象，且必须有 `status` 键；
2. **任意嵌套层**出现的 `status` 键，值必须恰为字符串 `【待核实】`（值核实后由 standards_index 驱动的规则对象替换，形态另行版本化——本期不做多版本并存）；
3. 正文叙述串里出现【待核实】字样（如 `reporting_notes` 中的说明句）不算形态违规，不触发本守卫。

## 5. 矿种 slug 词表（词表单源裁决）

仅 **5 个 production slug** 可孵化：

```
copper / coal / gold / iron / lead_zinc
```

- `other` **不孵化**；`ot`/银/镍/钼等显式不孵化（词表外 slug 报错拒绝）。
- 与 `build_output.MINERAL_ALIASES`（技能层）和 `title_parser.MINERAL_KEYWORDS`（后端层）双向同步——孵化新矿种触发六处变更面（title_parser / build_output / schemas / GSB_MINERALS / mineral_code / FilterBar），须跑六处检查清单。

## 6. 消费契约

技能侧按 `ore` 字段装载本目录对应 JSON（`references/ore_packs/<commodity 归一化>.json`）；文件缺失时回退 prose 硬编码知识并显式声明（详见 SKILL.md 开题段）。离线生产部署下本目录属编译产物易失路径，备份/恢复见 `deploy/offline/MANUAL-UPGRADE.md`。
