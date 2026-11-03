# bid-review L2-P3 附件匹配负证据 + 同义词归一 设计 spec

日期：2026-11-03　分支：main-dev-fork
前置：L2-P1（附件清单核对）与 L2-P2（子件分组+跨层去重）已落地；金标准评测集已落地（49 题 34 规则全绿）。

## 0. 范围

**做**：① `normalize_name` 同义词折叠（种子 2 组，机制可生长）；② 平件行近似命中门（MISSING → UNKNOWN(near_miss) 降级，防归一化变体假缺失）；③ 行级负证据记录（MISSING/near_miss 行携带 channels+pool+closest）；④ `att_check` 消费端按 unknown_reason 分流措辞；⑤ checklist 投影新键透传；⑥ 金标准新增 2 题（synonym 命中 / near-miss 降级）+ 匹配器单测。

**不做**（挂账）：复合件子行 near-miss **状态门**（P3.2；v1 只记证据不改状态——子件归组走 taken 池，改命中语义会扰动占用记账）｜前端核对表卡近似候选/负证据展示（投影 JSON 已携带，UI 后补）｜同义词表 YAML 外置（>20 组触发）｜阈值可配置（rulepack 级）｜指纹通道与 L0-L5 分层抽取管线（属二期抽取引擎立项，与本 slice 解耦；对照裁决见 §1）。

## 1. 背景与缺口裁决

2026-11-03 对照一份 bid 侧抽取层设计（L0-L5 管线/指纹字典/负证据前置/锚点规范/质量门禁）逐节盘点结论：**判定层四态骨架已同构落地，抽取层是另一条更浅的路线**。当前系统真实风险敞口排序：

1. **行级假缺失**：`bid.attachment_index` 清单整体抽不出 → 字段级已防住（缺字段 → need_human）；但**行级**无防——清单抽到、某附件实际存在而名称写法是归一化变体（如「中标通知书回执」vs「中标通知书」、「企业法人营业执照」vs「营业执照」）时，两级精确匹配（no 全等 / normalize_name 全等）双落空 → 直接 fatal MISSING，无任何佐证。这是本 slice 的靶心。
2. **同义词假缺失**：norm() 设计含同义词替换步，现状 `normalize_name`（attachments.py:15-22）只有全半角/去空白/剥序号前缀/去尾冒号。
3. 指纹通道、负证据前置（设计 §三 L5）、L0-L5 管线 → 二期抽取引擎，挂账。

**金标准铁律适用**：本 slice 是引擎能力增强（新行为用新题钉）；既有 49 题必须保持全绿，任何翻红即回归证据，禁止改标注迁就。

## 2. 设计决策记录

| 决策点 | 定版 | 理由 |
|---|---|---|
| 降级语义 | near-miss → **UNKNOWN(need_human)**，不升级 MATCHED | 「营业执照副本」可能只是复印件也可能缺正本，superset 变体语义方向不明；误降 UNKNOWN 只成本一次人工核对，误判 MATCHED 是漏报。安全侧取舍 |
| 相似度函数 | `difflib.SequenceMatcher.ratio()`（stdlib） | 不引依赖；匹配器本就 O(n²) 对几十行清单（attachments.py:110 注释同款论证） |
| 门限 | `NEAR_MISS_GATE = 0.75`（模块常量） | 「营业执照」vs「营业执照副本」ratio=0.80、「中标通知书」vs「中标通知书回执」=0.83 须落入门内；「中标通知书」vs「业绩合同」≈0.2 门外。金标准校准调参 |
| 同义词作用点 | 折叠进 `normalize_name` 内部（子串替换，组内最长变体优先） | 通道②③、复合父名引用判定（:91）、no-less 实体键（rule_runner.py:185）自动全部受益；调用面零改动 |
| 副本/复印件/正本后缀 | **不入**同义词表 | 折叠进等值通道=静默升级 MATCHED；走 near-miss 门降 UNKNOWN 交人工 |
| 证据挂载面 | `match_attachments` per_req 行 + `build_checklist` items 行双写 | rule_runner 走 import 绑定、checklist 走模块全局，两个消费面（金标准 T9 教训） |
| 复合件 v1 界面 | 子行只记证据，不改状态 | taken 池占用记账复杂度；P3.2 挂账 |

## 3. 机制设计

### 3.1 同义词归一（attachments.py）

```python
# 同义词组(首元素=规范形;子串替换,组内最长变体优先,防部分重叠吞字)。
# ponytail: 模块常量起步,>20 组外置 engine/dicts/synonyms.yaml(mtime 热载另议)。
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("营业执照", "企业法人营业执照"),
    ("审计报告", "年度审计报告"),
)
```

`normalize_name` 在剥序号前缀之后追加：对每组按变体长度降序，`t = t.replace(variant, canonical)`（出现几次换几次）。子串语义使「审计报告及财务报表」↔「年度审计报告及财务报表」在通道②等值命中。非同义词内容（副本/回执/扫描件）不折叠。

### 3.2 近似命中门（平件 MISSING 行，post-pass）

`match_attachments` 主体两通道+复合归组保持不动；末尾追加一轮降级扫描：

```python
# 平件 found==0 行:与 extra 池(两通道+复合归组后未被占用者)算相似度,
# max ≥ NEAR_MISS_GATE → UNKNOWN(unknown_reason="near_miss");证据一律记录。
for e in per_req:
    if e.get("sub_results") is not None or e["found"] > 0:
        continue
    nm = normalize_name(e["req"].get("name"))
    cands = sorted(((difflib.SequenceMatcher(None, nm, normalize_name(p.get("name"))).ratio(), p) for p in extra), key=lambda t: -t[0])
    e["negative_evidence"] = {"channels": [...], "pool": len(extra), "closest": [...top3 sim≥0.30...]}
    if cands and cands[0][0] >= NEAR_MISS_GATE:
        e["status"] = "UNKNOWN"; e["unknown_reason"] = "near_miss"
```

- 通道记账：req.no 非空计 `"no"`；nm 非空计 `"name"`。
- 复合件父行（`sub_results` 非空）跳过门扫描；其子行证据在 `_match_composite` 内同法记录（**只记不改状态**）。
- 分组失败行（UNKNOWN by orphan）：`negative_evidence=None`、`unknown_reason="grouping"`——另一种证据形态，不混用。

### 3.3 负证据 schema（per_req 行 + checklist items 行同名键）

```python
{
  "channels": ["no", "name"],      # 实际尝试的通道
  "pool": 12,                      # 匹配后仍未占用的提供项数
  "closest": [                     # 相似度 top-3,仅收 sim ≥ 0.30(滤噪)
    {"no": "E-3", "name": "中标通知书回执", "sim": 0.83},
  ],
}
```

### 3.4 att_check 消费分流（rule_runner.py:247-258）

UNKNOWN 行按 `unknown_reason` 分流（缺键向后兼容 → 视为 `"grouping"`）：
- `grouping`：维持现行措辞「复合附件「{label}」子件无法自动分组，需人工核对」。
- `near_miss`：「附件「{label}」未精确命中，近似候选「{closest[0]}」（相似度{sim}），需人工核对」。
- 两者均沿用 entity_keys + dedup_key（审查 I-1）按实体键派生，多行不互吞。

### 3.5 checklist 投影

items 行新增 `"unknown_reason"` 与 `"negative_evidence"`（缺省 None）；`counts.unknown` 语义扩为「分组失败 + 近似命中降级」（spec 声明即口径）。端点已确认透传（routers.py:802 直接返回 `build_checklist` dict）。前端展示挂账。

## 4. 行为矩阵（平件行）

| found | 最相似 extra sim | 现状 | P3 后 |
|---|---|---|---|
| ≥1（或 min_count 满足） | — | MATCHED | MATCHED（不变） |
| 0<found<min_count | — | PARTIAL | PARTIAL（不变；L2-024 面） |
| 0 | ≥0.75 | **fatal MISSING** | **UNKNOWN(near_miss) → need_human，带近似候选证据** |
| 0 | <0.75 | fatal MISSING | MISSING（不变；**新增**负证据：channels+pool+closest） |

## 5. 兼容性与风险

- **金标准净空**：现有附件夹具的 MISSING 题名称对（中标通知书/业绩合同等）相似度远低于门限；MATCHED 题走精确通道；种子同义词对未在现有夹具对中出现——49 题预期零翻红，实现后全量回归验证。
- **生产行为变化**：L2-020 fatal 违规可能减少（变体行转 need_human）——即本 slice 目的；L2-024/att_count、extra 不产 issue、四态上卷序均不变。
- **taken 池语义零改动**：门扫描只读 extra 池，不回写占用。
- rulepack 零改动（34 条不动）；EXPECTED_COVERAGE 不变（无新规则）。

## 6. 测试与金标准计划

单测（`tests/test_bid_review_attachments.py` 追加）：
- 同义词：企业法人营业执照→营业执照折叠；子串折叠（审计报告及…）；组内最长优先；「营业执照副本」**不**折叠（负例）；既有断言全部不变。
- 近似门：sim≥0.75 → UNKNOWN+near_miss+evidence 结构三键齐；边界 0.74 → MISSING；closest 滤噪（sim<0.30 不入）；复合子行只记证据不改状态；分组失败行 evidence=None。

金标准新增 2 题（CALIBRATION.md 记裁决）：
1. `L2-020-synonym-name-match.yaml` — req 营业执照 / provided 企业法人营业执照 → 通道② MATCHED；`strict: true` + `expect_issues: []` + `expect_absent: [L2-020, L2-024]`（FP 探针，E 族形态）。
2. `L2-020-near-miss-unknown.yaml` — req 中标通知书 / provided 中标通知书回执 → need_human；**red-first**：题先入库跑红（现引擎报 fatal MISSING）→ 实现 → 绿，钉「降级行为存在且方向正确」。

真缺失路径（sim<0.75 仍 fatal）由现有 `L2-020-missing-attachment` + strict 四态题覆盖，零新增题。

## 7. 验收标准

1. 全 49 金标准题 + bid_review 全测试族（344+）绿。
2. 新 2 题入库；near-miss 题 red-first 证据留档（CALIBRATION.md 记录红→绿）。
3. checklist 投影 JSON 携带 negative_evidence/unknown_reason 且端点透传（单测钉）。
4. near-miss 行 need_human 措辞带近似候选，entity/dedup 键不互吞。
5. 既有 MISSING 语义零漂移（现有金标准题全绿为证）。

## 8. 错误处理

- 相似度计算对空名（normalize_name→""）短路：nm 为空不进门扫描，保持 MISSING（与通道②空名跳过同语义）。
- extra 池为空 → evidence `{channels, pool:0, closest:[]}`，状态保持 MISSING。
- 门扫描自身异常不吞：匹配器纯函数层无 IO，异常即测试红。
