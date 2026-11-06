# bid-review P0：W1~W5 规则编号迁移 + 服务端派生 join（换算禁令）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地整合版规格书对齐 P0 之①③——5 条规则按整合版编号空间迁移（W1~W5，纯改名+层归属修正，check 逻辑零改动），并把 3 个由抽取 LLM 自产的换算布尔（`boq_unit_checks[].matched` / `appendix_references[].present` / `device_model_mismatches`）改为服务端代码派生（规格 L2233「禁模型换算」）。

**Architecture:** 迁移=改 `1.0.0.yaml` 五条规则 id/layer + 全部引用面（EXPECTED_COVERAGE、golden cases、测试、注释）三点一致翻转，每步保持测试绿。派生=在 `extract.py` 新增纯函数 `derive_joins()`，挂 `build_baseline()` 归一之后；字段名与行形不变，规则零改动；无法判定时不落键（走既有 need_human 隔离通路）。

**Tech Stack:** Python 3.12 + pytest（`cd backend && PYTHONPATH=. uv run pytest`）；规则包 YAML 元模型（op:all / att_missing_rows / det_expr）；无新依赖。

**规格依据:** `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md` §3.1（W1~W5 裁决表）与 §5（P0 清单）。
**范围裁定:** P0 之② quick 层裁剪**已被并发会话兑付**（commit `ec77631ef`，`worker.py:478 _prune_rules_for_mode` + `tests/test_bid_review_worker.py:1045`），本计划不含其施工，仅在 Task 4 做规格书实况刷新。P0 之④枚举三拆属 P1，不在本批。

---

## 施工必读（零上下文工程师须知）

1. **分支与提交**: 只在 `main-dev-fork` 提交；`docs/superpowers/` 在 .gitignore 内，提交计划/规格文件必须 `git add -f`；commit message 中文、`feat(bid-review):` / `fix(bid-review):` / `docs(bid-review):` 前缀；单文件/单逻辑 pathspec 提交。不 push（除非用户要求）。
2. **测试口径**: 全家口径 `cd backend && PYTHONPATH=. uv run pytest tests -k bid_review -q`（基线 570+ 全绿）。逐文件跑法见各任务。
3. **⚠️ 三同号轮换是循环**: W1(021→023)、W2(023→022)、W3(022→041) 构成 ID 循环，**必须一个 commit 原子落地**（中间态会出现重复 ID）。且**禁止对含多个 ID 的文件做 replace_all**（如 `1.0.0.yaml`、`test_bid_review_golden.py`）；每个 Edit 的 old_string 必须带 name 行/邻行上下文保证唯一。对**只含单一旧 ID** 的文件（golden case 文件、anchors.py 等）replace_all 安全，计划里已逐文件标注。
4. **Docker**: 本计划全部改动由 host 侧 pytest 验证，无需重启容器；全部落地后如需活体生效再 `docker compose -p eai-docker restart gateway`（不在本计划内）。
5. **配额纪律**: golden `--live`（烧配额）与方差回采不在本计划；Task 7 只跑零配额离线快照评分。

---

### Task 0: 基线预检

**Files:** 无改动（只读验证）

- [ ] **Step 1: 确认全家基线绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests -k bid_review -q`
Expected: 全绿（基线 570+ passed, 0 failed）。记录准确数字到 commit message 备用。若有红，停下排查，不得带红施工。

- [ ] **Step 2: 确认五个旧 ID 仍在场（防并发会话又兑付）**

Run: `cd backend && grep -rl "L2-021" app/extensions/bid_review/engine/rulepacks/ && grep -c "L2-022" tests/test_bid_review_golden.py`
Expected: yaml 命中 + golden 测试计数 ≥1。若已消失（并发会话已迁移），停：本计划 Task 1~3 跳过，直接从 Task 4 开始。

---

### Task 1: W1+W2+W3 三同号轮换（原子 commit）

三规则循环迁移：`L2-021 附件类型指纹核对(hyb)`→**L2-023**；`L2-023 附件实体内容空白(det major)`→**L2-022**；`L2-022 必填清单行未报价(det fatal)`→**L2-041**。check 逻辑、severity、inputs 全部不动。

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml`（:1 头注、:620-622 注、:623/:647/:666 三条 id、:643-646 R2+ 注块）
- Modify: `backend/tests/test_bid_review_golden.py`（:315-317 EXPECTED_COVERAGE 三行）
- Rename+Modify: `backend/app/extensions/bid_review/golden/cases/` 下 5 个文件
- Modify: `backend/tests/test_bid_review_rule_families.py`（2 个测试类 + NEW_IDS）
- Modify: `backend/tests/test_bid_review_rule_runner.py`（OP_RULE_IDS 映射 + L2-021 指纹通道测试块 + 注释）
- Modify: `backend/tests/test_bid_review_llm_verify.py`（:537/:543 合成夹具）
- Modify: `backend/tests/test_bid_review_registry.py`（:18/:91/:128 注释）
- Modify: `backend/app/extensions/bid_review/engine/labels.py`（:30 注释）、`engine/extract.py`（:97 注释）、`engine/anchors.py`（:12/:127/:128 注释）、`engine/llm_runner.py`（:171/:233 注释）、`engine/rule_runner.py`（:20/:243/:308 注释）

- [ ] **Step 1: yaml 三条 id 旋转（每处 Edit 带 name 行上下文，顺序任意但逐条做）**

Edit 1 — W1（old_string 含 name 行保证唯一）:
```yaml
# old
  - id: L2-021
    name: 附件类型指纹核对
# new
  - id: L2-023
    name: 附件类型指纹核对
```

Edit 2 — W3:
```yaml
# old
  - id: L2-022
    name: 必填清单行未报价
# new
  - id: L2-041
    name: 必填清单行未报价
```

Edit 3 — W2:
```yaml
# old
  - id: L2-023
    name: 附件实体内容空白
# new
  - id: L2-022
    name: 附件实体内容空白
```

- [ ] **Step 2: yaml 注释块同步（迁移出处立档）**

Edit 4 — :620-622 指纹通道注（首行）:
```yaml
# old
  # ── L2 指纹通道(spec 2026-11-04 §2.4,EAI-CUSTOM):L2-021 hyb——粗筛出 MISSING 行
# new
  # ── L2 指纹通道(spec 2026-11-04 §2.4,EAI-CUSTOM;整合版编号对齐 W1→L2-023,2026-11-06):
  # hyb——粗筛出 MISSING 行
```

Edit 5 — :643-646 R2+ 注块整体替换为最终形态（后续 Task 2/3 不再动此块）:
```yaml
# old
  # ── R2+ 规则族补齐(EAI-CUSTOM 2026-11-05,plan docs/superpowers/plans/2026-11-05-bid-review-r2-rule-families-plan.md):
  # 四条 det 消费 M1-M5 悬空字段(取证:registry.consumed_by 七路径 rules 全空)。
  # null 安全统一「!= True」形态:operator.ne 下仅值恰为 True 时判 False,False/None 双双通过。
  # ID: L2 家族 EAI-native 空闲号;L3-019/020 越过素材④未转录空洞(015/017)防未来转录碰撞。
# new
  # ── R2+ 规则族补齐(EAI-CUSTOM 2026-11-05,plan docs/superpowers/plans/2026-11-05-bid-review-r2-rule-families-plan.md;
  # 整合版编号对齐 W1~W5 2026-11-06,spec docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md §3.1):
  # 四条 det 消费 M1-M5 悬空字段(取证:registry.consumed_by 七路径 rules 全空)。
  # null 安全统一「!= True」形态:operator.ne 下仅值恰为 True 时判 False,False/None 双双通过。
  # ID 对齐:021指纹→023、023空白→022、022必填报价→041(fatal=EAI 上调,C-11 severity_override)、
  # 019聚类→L3-026(段尾扩展)、020章节空缺→L2-015(层 L3→L2);名称保持 EAI 显示名,编号以整合版为权威。
```

Edit 6 — :1 头注条数修正:
```yaml
# old
# bid-review-core 子系统规则包 v1.0.0(canonical,v1 全量 32 条)——技能 references/rules-det-subset.yaml 为其 M1 七条副本分发
# new
# bid-review-core 子系统规则包 v1.0.0(canonical,39 条;整合版编号对齐 2026-11-06)——技能 references/rules-det-subset.yaml 为其 M1 七条副本分发
```

- [ ] **Step 3: EXPECTED_COVERAGE 三行翻转（禁止 replace_all，用块上下文）**

```python
# old
    "L2-020",
    "L2-021",
    "L2-022",
    "L2-023",
    "L2-024",
# new
    "L2-020",
    "L2-022",
    "L2-023",
    "L2-024",
    "L2-041",
```

- [ ] **Step 4: golden cases 5 文件改名+内容（每文件只含单一旧 ID，replace_all 安全）**

```bash
cd backend/app/extensions/bid_review/golden/cases
git mv L2-021-fp-reject-full.yaml L2-023-fp-reject-full.yaml
git mv L2-021-fp-confirm-partial.yaml L2-023-fp-confirm-partial.yaml
git mv L2-021-fp-unclear.yaml L2-023-fp-unclear.yaml
git mv L2-023-blank-attachment.yaml L2-022-blank-attachment.yaml
git mv L2-022-required-row-no-price.yaml L2-041-required-row-no-price.yaml
```
内容（每文件 replace_all 一次）:
- 三个 `L2-023-fp-*.yaml`: `L2-021` → `L2-023`（命中 case:/desc:/scripted 键 `L2-021:`/rule_id/expect_absent 全部）
- `L2-022-blank-attachment.yaml`: `L2-023` → `L2-022`
- `L2-041-required-row-no-price.yaml`: `L2-022` → `L2-041`

- [ ] **Step 5: rule_families 测试两类迁移（NEW_IDS 分步改，Task 2/3 续）**

Edit — NEW_IDS（本步后为 4 条中的 3 条已迁 + 2 条未迁，覆盖 `L2-022`/`L2-041`/`L3-019`/`L3-020`）:
```python
# old
NEW_IDS = {"L2-022", "L2-023", "L3-019", "L3-020"}
# new
NEW_IDS = {"L2-022", "L2-041", "L3-019", "L3-020"}
```
Edit — TestL2022RequiredRowPrice → 类名/键/docstring 改 `L2-041`:
```python
# old
class TestL2022RequiredRowPrice:
    """L2-022 必填清单行未报价(tender.required_fields+bid.boq_rows;fatal;qty 不判)。"""
# new
class TestL2041RequiredRowPrice:
    """L2-041 必填清单行未报价(整合版对齐 W3,原 EAI L2-022;fatal=EAI 上调 C-11;tender.required_fields+bid.boq_rows;qty 不判)。"""
```
该类内 2 处 `_rules()["L2-022"]` → `_rules()["L2-041"]`（分别带上下文逐处改）。
Edit — TestL2023BlankAttachment → `L2-022`:
```python
# old
class TestL2023BlankAttachment:
    """L2-023 附件实体内容空白(bid.attachments;major;None 不判)。"""
# new
class TestL2022BlankAttachment:
    """L2-022 附件实体内容空白(整合版对齐 W2,原 EAI L2-023;bid.attachments;major;None 不判)。"""
```
类内 3 处 `_rules()["L2-023"]` → `_rules()["L2-022"]`（逐处带上下文改）。

- [ ] **Step 6: rule_runner 测试（先改映射再 replace_all，防字典字面量重复键）**

Edit 1 — OP_RULE_IDS 映射（块上下文）:
```python
# old
        "L2-021": "att_missing_rows",
        "L2-022": "all",
        "L2-023": "all",
# new
        "L2-023": "att_missing_rows",
        "L2-041": "all",
        "L2-022": "all",
```
Edit 2 — 该文件剩余 `L2-021` 全部（注释 :20/:138/:258/:415/:446/:476 yaml 夹具/:481、夹具 `id="L2-021"`、docstring）: replace_all `L2-021` → `L2-023`。

- [ ] **Step 7: 其余引用面**

- `test_bid_review_llm_verify.py`: replace_all `L2-021` → `L2-023`（合成夹具自洽）。
- `test_bid_review_registry.py`: replace_all `L2-022` → `L2-041`（仅 :18/:91/:128 注释命中）。
- `engine/labels.py`: `R2+ L2-022 消费` → `R2+ L2-041 消费`。
- `engine/extract.py`: :97 `L2-022 inputs 声明` → `L2-041 inputs 声明`。
- `engine/anchors.py`: replace_all `L2-021` → `L2-023`（注释）。
- `engine/llm_runner.py`: replace_all `L2-021` → `L2-023`（注释）。
- `engine/rule_runner.py`: replace_all `L2-021` → `L2-023`（:20/:243/:308 注释）。

- [ ] **Step 8: 跑迁移相关测试面**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_rule_families.py tests/test_bid_review_registry.py tests/test_bid_review_rule_runner.py tests/test_bid_review_llm_verify.py tests/test_bid_review_metrics.py -q`
Expected: 全 PASS（覆盖率三方精确相等断言 `EXPECTED_COVERAGE == pack_ids == covered` 过 = 迁移无漏面）。

- [ ] **Step 9: 全家回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests -k bid_review -q`
Expected: 与 Task 0 同数全绿。

- [ ] **Step 10: Commit（原子）**

```bash
git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/app/extensions/bid_review/engine backend/app/extensions/bid_review/golden/cases backend/tests/test_bid_review_golden.py backend/tests/test_bid_review_rule_families.py backend/tests/test_bid_review_registry.py backend/tests/test_bid_review_rule_runner.py backend/tests/test_bid_review_llm_verify.py
git commit -m "fix(bid-review): 整合版编号对齐W1-W3三同号轮换——L2-021指纹→L2-023/L2-023空白→L2-022/L2-022必填报价→L2-041(fatal=C-11上调);纯改名零check改动;EXPECTED_COVERAGE+golden五题+families/runner/verify夹具+注释面同刻翻转"
```

---

### Task 2: W4 — L3-019 → L3-026（段尾扩展号）

**Files:**
- Modify: `1.0.0.yaml`（:684 id）
- Rename+Modify: `golden/cases/L3-019-cluster-unsure.yaml` → `L3-026-cluster-unsure.yaml`
- Modify: `test_bid_review_golden.py`（:334）、`test_bid_review_rule_families.py`（TestL3019 + NEW_IDS）

- [ ] **Step 1: yaml id（带 name 上下文）**

```yaml
# old
  - id: L3-019
    name: 业绩条目聚类存疑
# new
  - id: L3-026
    name: 业绩条目聚类存疑
```

- [ ] **Step 2: golden case**

```bash
git mv backend/app/extensions/bid_review/golden/cases/L3-019-cluster-unsure.yaml backend/app/extensions/bid_review/golden/cases/L3-026-cluster-unsure.yaml
```
文件内 replace_all `L3-019` → `L3-026`。

- [ ] **Step 3: 测试引用**

- `test_bid_review_golden.py`: `    "L3-019",` → `    "L3-026",`
- `test_bid_review_rule_families.py`:
```python
# old
NEW_IDS = {"L2-022", "L2-041", "L3-019", "L3-020"}
# new
NEW_IDS = {"L2-022", "L2-041", "L3-020", "L3-026"}
```
```python
# old
class TestL3019ClusterUnsure:
    """L3-019 业绩条目聚类存疑(bid.performance_groups;major;M4 UNKNOWN 的规则面)。"""
# new
class TestL3026ClusterUnsure:
    """L3-026 业绩条目聚类存疑(整合版对齐 W4 段尾扩展,原 EAI L3-019;bid.performance_groups;major;M4 UNKNOWN 的规则面)。"""
```
类内 3 处 `_rules()["L3-019"]` → `_rules()["L3-026"]`（逐处带上下文改）。

- [ ] **Step 4: 测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_rule_families.py tests/test_bid_review_clusters.py -q`
Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/app/extensions/bid_review/golden/cases backend/tests/test_bid_review_golden.py backend/tests/test_bid_review_rule_families.py
git commit -m "fix(bid-review): 整合版编号对齐W4——L3-019业绩聚类→L3-026段尾扩展号(无同义规格规则,C-01/C-02追加先例);golden题+families类同刻翻转"
```

---

### Task 3: W5 — L3-020 → L2-015（层归属 L3→L2）

**Files:**
- Modify: `1.0.0.yaml`（:703-704 id+layer）
- Rename+Modify: `golden/cases/L3-020-empty-section.yaml` → `L2-015-empty-section.yaml`
- Modify: `test_bid_review_golden.py`（:295 注 + :335）
- Modify: `test_bid_review_rule_families.py`（TestL3020 + NEW_IDS）
- Modify: `test_bid_review_rule_runner.py`（:133-134 计数注释）

- [ ] **Step 1: yaml id+layer**

```yaml
# old
  - id: L3-020
    name: 章节正文空缺
    layer: L3
# new
  - id: L2-015
    name: 章节正文空缺
    layer: L2
```

- [ ] **Step 2: golden case**

```bash
git mv backend/app/extensions/bid_review/golden/cases/L3-020-empty-section.yaml backend/app/extensions/bid_review/golden/cases/L2-015-empty-section.yaml
```
文件内 replace_all `L3-020` → `L2-015`。

- [ ] **Step 3: 测试引用**

- `test_bid_review_golden.py` 集合行: `    "L3-020",` → `    "L2-015",`；:295 注释整体替换:
```python
# old
# 批C 起覆盖率翻全集(L1 全集 17 + L3 全集 17 + L2 全集 5 = pack 39 条精确相等;L1-004/017/018/020、L3-011/015/017 不存在;R2+ 2026-11-05 增 L2-022/023、L3-019/020)
# new
# 批C 起覆盖率翻全集(L1 17 + L2 6 + L3 16 = pack 39 条精确相等;整合版编号对齐 2026-11-06:
# W1~W5 迁移 021指纹→023/023空白→022/022必填报价→041/019聚类→026/020章节空缺→L2-015 层归位,总数不变)
```
- `test_bid_review_rule_families.py`:
```python
# old
NEW_IDS = {"L2-022", "L2-041", "L3-020", "L3-026"}
# new
NEW_IDS = {"L2-015", "L2-022", "L2-041", "L3-026"}
```
```python
# old
class TestL3020EmptySection:
    """L3-020 章节正文空缺(bid.section_tree;major;is_empty=None 不判)。"""
# new
class TestL2015EmptySection:
    """L2-015 章节正文空缺(整合版对齐 W5 层归位 L3→L2,原 EAI L3-020;bid.section_tree;major;is_empty=None 不判)。"""
```
类内 3 处 `_rules()["L3-020"]` → `_rules()["L2-015"]`（逐处带上下文改）。
- `test_bid_review_rule_runner.py` :133-134 注释:
```python
# old
    assert len(by_type.get("deterministic", [])) == 33, "L1 det 14 + L3 det 15(+L3-019/020) + L2 det 4(L2-020/022/023/024,R2+ 规则族补齐 2026-11-05) = 33"
    assert len(by_type.get("hybrid", [])) == 5, "L1 hyb 003/007 + L3 hyb 004/008 + L2-021 指纹通道(spec 2026-11-04) = 5"
# new
    assert len(by_type.get("deterministic", [])) == 33, "L1 det 14 + L3 det 14 + L2 det 5(L2-020/022/024/041 + L2-015 章节空缺层归位) = 33;编号对齐 2026-11-06"
    assert len(by_type.get("hybrid", [])) == 5, "L1 hyb 003/007 + L3 hyb 004/008 + L2-023 指纹通道(整合版对齐 W1) = 5"
```
（计数 33/5 不变——纯改名+层移动，同一 commit 内断言先绿。）

- [ ] **Step 4: 测试**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_golden.py tests/test_bid_review_rule_families.py tests/test_bid_review_rule_runner.py -q`
Expected: 全 PASS。

- [ ] **Step 5: 全家回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests -k bid_review -q`
Expected: 与 Task 0 同数全绿。

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml backend/app/extensions/bid_review/golden/cases backend/tests/test_bid_review_golden.py backend/tests/test_bid_review_rule_families.py backend/tests/test_bid_review_rule_runner.py
git commit -m "fix(bid-review): 整合版编号对齐W5收官——L3-020章节空缺→L2-015层归位(L3→L2,门禁行为等价);覆盖率注39=L1 17+L2 6+L3 16;runner计数注释同刻"
```

---

### Task 4: 规格书与记忆实况刷新（quick 裁剪已兑付 + W1~W5 LANDED）

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`

- [ ] **Step 1: 状态行与对齐矩阵刷新**

:3 状态行 `PROPOSED（W1~W5 编号迁移随 P0 实施计划落地…）` → `LANDED（W1~W5 已随 2026-11-06 P0 计划落地;W6~W8 为永久裁决记录）;quick 层裁剪已由并发会话兑付(commit ec77631ef,_prune_rules_for_mode+worker 测试)`。
§2 矩阵 §1 行关键差异中「quick 无规则子集裁剪（规格 13.5 与仓库设计稿 §1 双承诺双未做）」→「quick 层裁剪已落地（commit ec77631ef，`worker.py:478`，rules_total 取裁剪后分母）；报告版本清单缺」。
§5 第 2 条改注: 「~~quick 模式层裁剪~~ → 已兑付 ec77631ef（2026-11-06 并发会话,对齐审计①）」。

- [ ] **Step 2: DB 残行迁移注记落 §3.1 尾**

在 §3.1 迁移连带影响段末追加一行: 「DB 注记(质量审查 Important-1 修正,2026-11-06):**轮换使旧 override 键语义翻转,非无害回落**——迁移前入库的 `L2-022`/`L2-023` 键现指向不同规则(旧 022=必填报价→现 022=附件空白;旧 023=附件空白→现 023=指纹):任何早于 commit 43ae36f98 的库在启用逐规则 enabled 开关前必须先清空或重映射这两键;L2-021/L3-019/L3-020 旧键才真回落 yaml enabled。2026-11-06 实测 dev ext 库 `bid_review_rulepacks` 尚无 rule_overrides 列(models.py 已声明、迁移未跑)=现网零残键,该列迁移落地时须带旧键重映射;另 8 行 bid_review_issues 历史 rule_id=L2-021 成孤儿 ID(规格已接受不迁移)。」（核对用: `docker exec eai-flow-postgres-ext psql -U agentflow -d agentflow -c "\d bid_review_rulepacks"` —— 表名/列名以 `backend/app/extensions/bid_review/models.py` 中 RulePackMeta `__tablename__` 为准，只读核实，不改数据。）

- [ ] **Step 3: Commit + wolf/记忆记档**

```bash
git add -f docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md
git commit -m "docs(bid-review): 对齐规格书实况刷新——W1-W5标记LANDED+quick层裁剪兑付注记(ec77631ef)+rule_overrides旧ID残键无害记档"
```
并更新 `.wolf/anatomy.md`（Task 1~3 改动的 yaml/cases 条目注记迁移）、`.wolf/memory.md` 会话行、auto-memory `bid-review-alignment-audit-2026-11-05.md`（5 条冲突→已迁移兑付状态）。

---

### Task 5: 服务端派生 join `derive_joins()`（换算禁令 P0③，TDD）

**Files:**
- Test: `backend/tests/test_bid_review_extract.py`（新增 4 个测试，放 `test_heterogeneous_row_paths_passthrough` 之后）
- Modify: `backend/app/extensions/bid_review/engine/extract.py`（新常量+两函数+契约文本+`build_baseline` 挂钩）

- [ ] **Step 1: 写失败测试**

在 `test_bid_review_extract.py` 追加（沿用既有 `_fields_via_baseline` 助手，它经 `build_baseline` 全链路，天然覆盖挂钩点）:
```python
# ── 服务端派生 join(整合版对齐 P0③,2026-11-06;D:\knowbase 规格书 L2233 禁模型换算)──


def test_derive_boq_unit_matched_recomputed():
    # matched 服务端按行内 tender_unit/bid_unit 归一比对回填;模型自产 matched 一律丢弃
    f = _fields_via_baseline({"bid.boq_unit_checks": [
        {"code": "B1", "tender_unit": "米", "bid_unit": "m", "matched": False},   # 归一后相等→True(模型假值被覆盖)
        {"code": "B2", "tender_unit": "米", "bid_unit": "毫米", "matched": True},  # 不等→False(模型假值被覆盖)
        {"code": "B3", "tender_unit": "套", "bid_unit": None},                    # 缺侧→不落键(need_human 通路)
    ]})
    rows = f["bid.boq_unit_checks"]
    assert rows[0]["matched"] is True
    assert rows[1]["matched"] is False
    assert "matched" not in rows[2]


def test_derive_appendix_present_joined():
    # present 服务端按附件名归一双向子串 join(attachments 优先,attachment_index 兜底);无来源不落键
    fields = {
        "bid.appendix_references": [
            {"name": "营业执照（副本）", "present": False},  # 模型假值被覆盖
            {"name": "安全生产许可证"},
        ],
        "bid.attachment_index": [{"no": "1", "name": "营业执照", "page": 1, "pages": None}],
    }
    f = _fields_via_baseline(fields)
    rows = f["bid.appendix_references"]
    assert rows[0]["present"] is True
    assert rows[1]["present"] is False
    f2 = _fields_via_baseline({"bid.appendix_references": [{"name": "营业执照"}]})
    assert "present" not in f2["bid.appendix_references"][0]


def test_derive_device_mismatches_computed():
    # mismatches=tender×bid 归一集合双向差集;任一侧缺失→不派生(保持缺席=UNKNOWN)
    f = _fields_via_baseline({
        "tender.device_models": ["FBCDZ-8-No.20A", "KDK-400"],
        "bid.device_models": ["FBCDZ-8-No.20", "KDK-400"],
        "bid.device_model_mismatches": ["模型自产串:假"],
    })
    assert f["bid.device_model_mismatches"] == [
        "FBCDZ-8-No.20:投标型号未见于招标清单",
        "FBCDZ-8-No.20A:招标要求型号未见于投标文件",
    ]
    f2 = _fields_via_baseline({"bid.device_models": ["X-1"]})
    assert f2["bid.device_model_mismatches"] is None  # 缺招标侧→不派生


def test_collect_field_paths_excludes_server_derived():
    # device_model_mismatches 改服务端派生,不再进提取请求(宇宙/注册表 78 不变,仅请求面收窄)
    assert "bid.device_model_mismatches" not in collect_field_paths()
    assert "bid.boq_unit_checks" in collect_field_paths()      # 行仍由模型抄录,布尔服务端回填
    assert "bid.appendix_references" in collect_field_paths()
```

- [ ] **Step 2: 跑红**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py -q -k "derive"`
Expected: 4 个新测试 FAIL（`KeyError: 'bid.device_model_mismatches'` / matched 未覆盖 / device 不在请求面断言失败）。

- [ ] **Step 3: 实现 derive_joins + 归一助手 + 挂钩**

`engine/extract.py` 在 `FIELD_TYPE_CONTRACTS` 列表契约区（:107 `_OCCURRENCE_CONTRACT` 之前）插入:
```python
# ── 服务端派生 join(整合版对齐 P0③,2026-11-06;D:\knowbase 规格书 L2233「禁模型换算」)──
# boq_unit_checks[].matched / appendix_references[].present / device_model_mismatches 原由抽取
# LLM 自产=换算禁令违例;改服务端派生,字段名与行形不变,规则零改动。无法判定不落键
# (缺键→op:all 逐规则隔离 need_human 既有通路;UNKNOWN 不判通过铁律)。
SERVER_DERIVED_PATHS: frozenset[str] = frozenset({"bid.device_model_mismatches"})

_FW_MAP = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
)
_UNIT_ALIASES = {"米": "m", "毫米": "mm", "厘米": "cm", "千米": "km", "平方米": "m2", "㎡": "m2", "立方米": "m3", "吨": "t", "千克": "kg", "公斤": "kg", "克": "g", "天": "day", "日": "day", "月": "month", "年": "year"}


def normalize_unit_name(v: Any) -> str:
    """清单计量单位归一(仅等值比对;不做量纲换算——mm≠m 口径不同=不一致,交人工)。"""
    s = str(v or "").strip().translate(_FW_MAP).lower().strip()
    return _UNIT_ALIASES.get(s, s)


def derive_joins(fields: dict) -> dict:
    """三个换算字段的服务端派生(纯函数返回新 dict):
    - boq_unit_checks[].matched = normalize_unit_name(tender_unit)==normalize_unit_name(bid_unit)(两侧单位齐才落键);
    - appendix_references[].present = 附件名与 bid.attachments/bid.attachment_index 归一双向子串命中(有来源才落键);
    - device_model_mismatches = tender.device_models×bid.device_models 归一双向差集(两侧非空才派生,可派生时整体覆盖含 [])。
    模型自产的 matched/present/mismatches 一律丢弃重建(禁模型换算)。"""
    out = dict(fields)
    rows = out.get("bid.boq_unit_checks")
    if isinstance(rows, list):
        new_rows = []
        for r in rows:
            if not isinstance(r, dict):
                new_rows.append(r)
                continue
            r = {k: v for k, v in r.items() if k != "matched"}
            t, b = r.get("tender_unit"), r.get("bid_unit")
            if isinstance(t, str) and t.strip() and isinstance(b, str) and b.strip():
                r["matched"] = normalize_unit_name(t) == normalize_unit_name(b)
            new_rows.append(r)
        out["bid.boq_unit_checks"] = new_rows
    rows = out.get("bid.appendix_references")
    if isinstance(rows, list):
        sources = []
        for p in ("bid.attachments", "bid.attachment_index"):
            for item in out.get(p) or []:
                if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
                    n = _normalize_name(item["name"])
                    if n:
                        sources.append(n)
        new_rows = []
        for r in rows:
            if not isinstance(r, dict):
                new_rows.append(r)
                continue
            r = {k: v for k, v in r.items() if k != "present"}
            name = r.get("name")
            if sources and isinstance(name, str) and name.strip():
                n = _normalize_name(name)
                r["present"] = bool(n) and any(n in s or s in n for s in sources)
            new_rows.append(r)
        out["bid.appendix_references"] = new_rows

    def _model_list(v):
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()]
        return None

    ts, bs = _model_list(out.get("tender.device_models")), _model_list(out.get("bid.device_models"))
    if ts and bs:
        def _nm(s: str) -> str:
            return " ".join(s.translate(_FW_MAP).split()).lower()
        t_norms, b_norms = {_nm(x) for x in ts}, {_nm(x) for x in bs}
        mism = [f"{m}:投标型号未见于招标清单" for m in bs if _nm(m) not in t_norms]
        mism += [f"{m}:招标要求型号未见于投标文件" for m in ts if _nm(m) not in b_norms]
        out["bid.device_model_mismatches"] = mism
    return out
```
（`_normalize_name` 即 `attachments.normalize_name`，`extract.py:10` 已 import 为该别名——用现有别名，勿新 import。）
`build_baseline` 挂钩（:683 `fields = normalize_fields(...)` 之后插入一行）:
```python
    fields = normalize_fields(fields_raw, field_paths)
    fields = derive_joins(fields)  # 换算禁令 P0③:服务端派生 join(模型不再自产三个换算布尔/串)
```
契约文本更新（模型不再被要求产布尔）:
```python
# old
FIELD_TYPE_CONTRACTS["bid.appendix_references"] = '[{name:"附件名", present:true|false 是否随卷提交}] 对象列表;present 必填布尔,从正文引用与附件清单逐条对照;禁止纯值列表/标量。'
FIELD_TYPE_CONTRACTS["bid.boq_unit_checks"] = '[{code:"清单项编号", tender_unit:"招标单位", bid_unit:"投标单位", matched:true|false}] 对象列表;matched 必填布尔,逐清单项对照数量/单位口径;禁止纯值列表/标量。'
# new
FIELD_TYPE_CONTRACTS["bid.appendix_references"] = '[{name:"附件名"}] 对象列表;只报正文引用到的附件名,present 由服务端按附件清单归一比对回填(禁模型换算,不产该键);禁止纯值列表/标量。'
FIELD_TYPE_CONTRACTS["bid.boq_unit_checks"] = '[{code:"清单项编号", tender_unit:"招标单位", bid_unit:"投标单位"}] 对象列表;逐清单项抄录两侧计量单位原文,matched 由服务端归一比对回填(禁模型换算,不产该键);禁止纯值列表/标量。'
```
:102-104 行形异构注块末追加一行注释: `# 换算禁令 P0③(2026-11-06):matched/present 改服务端 derive_joins 回填,模型只抄行;`

- [ ] **Step 4: 跑绿**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py tests/test_bid_review_worker.py tests/test_bid_review_tables_extract.py tests/test_bid_review_attachments_extract.py -q`
Expected: 全 PASS（新 4 测绿 + 既有 worker/表格/附件测试零翻红——派生只影响带对应字段的基线）。

- [ ] **Step 5: 全家回归**

Run: `cd backend && PYTHONPATH=. uv run pytest tests -k bid_review -q`
Expected: Task 0 数 + 4 全绿。

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/bid_review/engine/extract.py backend/tests/test_bid_review_extract.py
git commit -m "fix(bid-review): 换算禁令P0③——boq_unit_checks.matched/appendix_references.present/device_model_mismatches改服务端derive_joins派生(禁模型换算,D:\\knowbase规格L2233);字段名行形不变规则零改动;无法判定不落键走need_human通路;契约文本同步"
```

---

### Task 6: device_model_mismatches 退出提取请求面

**Files:**
- Test: `backend/tests/test_bid_review_registry.py`（:136-147 排除公式）
- Modify: `backend/app/extensions/bid_review/engine/extract.py`（`collect_field_paths`）

- [ ] **Step 1: 改红注册表测试**

先在文件头 :8-13 既有 import 块补一项（元组内按字母序插在 OCCURRENCE_PATHS 后）:
```python
# old
from app.extensions.bid_review.engine.extract import (
    FIELD_TYPE_CONTRACTS,
    LIST_PATHS,
    OCCURRENCE_PATHS,
    collect_field_paths,
)
# new
from app.extensions.bid_review.engine.extract import (
    FIELD_TYPE_CONTRACTS,
    LIST_PATHS,
    OCCURRENCE_PATHS,
    SERVER_DERIVED_PATHS,
    collect_field_paths,
)
```
再改 :138 公式:
```python
# old
        assert collect_field_paths() == [p for p in EXPECTED_UNIVERSE if p not in registry.SECOND_STAGE_FIELDS]
# new
        assert collect_field_paths() == [p for p in EXPECTED_UNIVERSE if p not in registry.SECOND_STAGE_FIELDS and p not in SERVER_DERIVED_PATHS]
```
并在 :144 后追加一行:
```python
        assert "bid.device_model_mismatches" not in collect_field_paths()  # 服务端派生(禁模型换算 P0③)
```

- [ ] **Step 2: 跑红**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_registry.py -q -k second_stage`
Expected: FAIL（collect_field_paths 仍含 device_model_mismatches）。

- [ ] **Step 3: 实现**

```python
# old(extract.py collect_field_paths)
    return sorted(set(_registry_universe()) - set(_SECOND_STAGE_FIELDS))
# new
    return sorted(set(_registry_universe()) - set(_SECOND_STAGE_FIELDS) - set(SERVER_DERIVED_PATHS))
```
docstring 「71 路径逐位」句改: 「71 路径=R2+ 后 72−device_model_mismatches 服务端派生退出请求(整合版对齐 P0③ 2026-11-06;宇宙/注册表 78 不变)」。同步 `test_bid_review_registry.py` :19 注释 `= 72(R1 改造前 71 + R2+ 新增 1)` → `= 71(R2+ 后 72−device_model_mismatches 服务端派生,整合版对齐 P0③)`。Task 5 已使新测试 `test_collect_field_paths_excludes_server_derived` 前半断言通过——本步使注册表公式测试通过。

- [ ] **Step 4: 跑绿 + 全家**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_registry.py tests/test_bid_review_extract.py -q`
Expected: 全 PASS。
Run: `cd backend && PYTHONPATH=. uv run pytest tests -k bid_review -q`
Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/extract.py backend/tests/test_bid_review_registry.py
git commit -m "fix(bid-review): device_model_mismatches退出提取请求面——SERVER_DERIVED_PATHS排除(模型产它即违禁换算;宇宙78不变仅请求面70);registry公式测试同刻"
```

---

### Task 7: 收官——零配额快照核对 + 规格书实况 + 记档

**Files:**
- Modify: `docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md`（§5 第 3 条标 LANDED）
- Modify: `.wolf/anatomy.md`、`.wolf/memory.md`、`.wolf/cerebrum.md`

- [ ] **Step 1: 离线快照评分零翻红（零配额）**

Run: `cd backend && PYTHONPATH=. uv run python -m app.extensions.bid_review.golden.extract`
Expected: exit 0，输出 pass_rate ≥ `annotations.meta.baseline_pass_rate`（具体数值以命令输出为准；r6-snapshot 为冻结件，派生改动不触碰它，成绩须与改前逐位一致——可先跑一次留底再施工，改后对比）。

- [ ] **Step 2: 规格书 §5 第 3 条标注 LANDED（引用本计划文件名+两 commit 号）**

- [ ] **Step 3: wolf/记忆记档**

`.wolf/cerebrum.md` Key Learnings 追加: 「对齐审计类缺口立档后、开工前必须重新 grep 核实是否已被并发会话兑付——quick 层裁剪立档当天即被 ec77631ef 兑付(11-05 四项同款先例);计划编写以当日 grep 为准不以存档结论为准」。`.wolf/memory.md` 会话行。auto-memory 更新 audit 记忆文件（P0①②③ 兑付状态）。

- [ ] **Step 4: Commit**

```bash
git add -f docs/superpowers/specs/2026-11-06-bid-review-integrated-spec-alignment.md
git add .wolf/anatomy.md .wolf/memory.md .wolf/cerebrum.md
git commit -m "docs(bid-review): P0③换算禁令LANDED收官——规格书实况+快照零翻红核验+wolf记档(cerebrum并发兑付须开工前重查)"
```

---

## 已知非目标（不在本计划，勿顺手做）

- L2-041 的 table_cells 一般化（v1 仅 boq 单价实例）、L2-022 OCR 置信≥0.85 门（解析层无 ocr_conf）、L2-015 姊妹规则 L2-051 草稿残留、L3-026 与规格 L2-025 的并归评估——均随 L2 扩展批走。
- golden `--live` 活体复跑与 M2-M4 方差回采（烧配额，须用户点头，见 dca410002）。
- 枚举三拆 alias、MATCHED→PRESENT 归一（spec §3.3，P1）。
- 上游文件 `D:\knowbase\投标方案审查_整合版.md` 侧回写（W6~W8 候选，待业务评审）。

## Self-Review 记录

- 规格覆盖: §5 之①→Task 1~3；之②→已兑付核实（Task 0 Step 2 防复发检查 + Task 4 记档）；之③→Task 5~7；之④ P1 不入批 ✓
- 占位符扫描: 无 TBD/待定；所有代码块完整可粘贴 ✓
- 类型一致性: `normalize_unit_name` / `derive_joins` / `SERVER_DERIVED_PATHS` 三个新符号在 Task 5/6 间签名一致；`_normalize_name` 用 extract.py:10 既有别名 ✓
- 风险点已显式处置: 三同号轮换原子化（Task 1 单 commit）、字典字面量重复键（Task 1 Step 6 先映射后 replace_all）、测试中途态绿（NEW_IDS 分步、runner 计数注释 Task 3 终态）✓
