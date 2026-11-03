# L2 P3.2 复合子行 near-miss 状态门 设计

> 日期: 2026-11-03 ｜ 状态: 待审
> 前置: `2026-11-03-bid-review-l2-p3-negative-evidence-synonym-design.md`（已落地,commits dd7005561/acd78a6e3/b4de9b83b/52cfcb4ce）§0 挂账首项
> 性质: delta spec——门机制/负证据模式/金标准纪律全部沿用 P3 spec,本文只定义子行增量的差异。

## 0. 背景与目标

P3 v1 给复合件 MISSING 子行记了 `negative_evidence` 但**不改状态**（挂账原文:「子件归组走 taken 池,改命中语义会扰动占用记账」）。后果: 复合子件名带归一化变体（如子件「中标通知书」、提供项名「中标通知书回执」）时,子行仍 MISSING → 父行 MISSING → att_check **fatal 附件缺失**——P3 在平件上根治的伪缺失,在子件上仍然存活。

P3.2 把门同样用到子行: **子行 MISSING + 池内有 sim≥NEAR_MISS_GATE 候选 → 子行 UNKNOWN(near_miss)**,父行经既有 `worst` 上卷自然变 UNKNOWN → att_check 降 need_human。真缺失子件仍 MISSING → 父行 MISSING → fatal,不变。

v1 的挂账理由（taken 池扰动）经核实**不成立**: 门是 `found==0` 之后的只读后处理,不回写 `taken`、不参与通道命中——占用记账零触碰。真正要小心的只有两处: 证据循环的 cands 复用（现在算完即弃）与 att_check 消息分流（父行 UNKNOWN 不能误走「无法自动分组」话术）。

## 1. 引擎: 子行门 + 父行戳记（attachments.py）

### 1.1 子行降级（`_match_composite` 尾部,现 :164-171）

现循环把 `_sim_cands` 结果内联传给 `_evidence` 后丢弃。改为先存 cands,门判定,再记证据:

```python
    untaken = [p for i, p in enumerate(prov) if i not in taken]
    for s in sub_results:
        if s["status"] == "MISSING":
            channels = (["no"] if s.get("no") else []) + (["name"] if normalize_name(s.get("name")) else [])
            cands = _sim_cands(normalize_name(s.get("name")), untaken)
            # L2 P3.2 (spec 2026-11-03 §1.1,EAI-CUSTOM):子行 MISSING 同入近似门——
            # sim≥NEAR_MISS_GATE 降 UNKNOWN(near_miss),父行经 _SUB_STATUS_ORDER 上卷;
            # 只读后处理不回写 taken,占用记账零触碰。真缺失(门外)仍 MISSING。
            if cands and cands[0][0] >= NEAR_MISS_GATE:
                s["status"] = "UNKNOWN"
                s["unknown_reason"] = "near_miss"
            s["negative_evidence"] = _evidence(channels, untaken, cands)
```

语义钉:
- 门判定用 **raw ratio**（`cands[0][0]`）,closest 存 `round(s,4)`、展示 `.2f`——与平件门完全同规,无语义翻转面。
- `s_nm` 归一为空 → `_sim_cands` 返回 `[]` → 不进门,子行保持 MISSING（与平件空名短路同语义）。
- PARTIAL 子行（found>0）不入循环,天然跳过。
- 副本/回执类方向不明变体**仍不入 `_SYNONYM_GROUPS`**,由本门交人工——P3 决策不变。

### 1.2 父行上卷与 unknown_reason 戳记（`match_attachments` 复合分支,现 :220-228）

`worst` 经 `_SUB_STATUS_ORDER`（UNKNOWN=0 最差）自动上卷,**上卷逻辑零改动**。只补父行 `unknown_reason` 戳记,供投影与 att_check 消费:

```python
        if _sub_items(r):
            comp = _match_composite(r, prov, taken)
            found = sum(s["found"] for s in comp["sub_results"])
            worst = min((s["status"] for s in comp["sub_results"]), key=lambda st: _SUB_STATUS_ORDER[st], default="MATCHED")
            if comp["orphan"]:
                per_req.append({"req": r, "matched": [], "found": found, "status": "UNKNOWN", "unknown_reason": "grouping", "negative_evidence": None, "sub_results": comp["sub_results"]})
            else:
                # L2 P3.2 (spec §1.2,EAI-CUSTOM):父行戳记=子行 near_miss 传播,仅供投影/分流消费
                sub_nm = any(s.get("unknown_reason") == "near_miss" for s in comp["sub_results"])
                reason = "near_miss" if sub_nm else None
                per_req.append({"req": r, "matched": [], "found": found, "status": worst, "unknown_reason": reason, "negative_evidence": None, "sub_results": comp["sub_results"]})
            continue
```

优先级裁决: **orphan 存在时父行戳 `grouping` 不被 near_miss 覆盖**——孤儿是父级事实,子行各自带 `near_miss`,两因并存时各自成话。非 orphan 且无子 near_miss → `unknown_reason=None`(旧行为,复合行此前无该键;P3 v1 已给它 `negative_evidence: None`,本切片补 `unknown_reason: None` 键使行形状归一,消费方一律 `.get()`)。

`_near_miss_pass` 不动: 它跳过 `sub_results is not None` 的行,复合父行永不入平件门,无双重降级。

## 2. rule_runner: att_check 消息三分支（现 :254-267）

父行 UNKNOWN 因子行 near_miss 上卷时,现分流会走 grouping 话术「子件无法自动分组」——**错话**。改三分支,按成因各说各话:

```python
                    for r in unknown:  # UNKNOWN 降 need_human,禁强行 PARTIAL/MISSING(spec §7)
                        subs_nm = [s for s in (r.get("sub_results") or []) if s.get("unknown_reason") == "near_miss"]
                        if subs_nm:
                            # P3.2 成因分流(spec 2026-11-03 §2,EAI-CUSTOM):子行近似→逐子行
                            # need_human,消息点名父件+子件+候选;grouping 孤儿另发,两因不互吞
                            for s in subs_nm:
                                cands = (s.get("negative_evidence") or {}).get("closest") or []
                                c0 = cands[0] if cands else {}
                                cand_txt = f"{c0.get('no', '')} {c0.get('name', '')}".strip() or "无近似候选记录"
                                sim_txt = f"(相似度 {c0['sim']:.2f})" if c0.get("sim") is not None else ""
                                nh = _need_human(rule, f"复合附件「{_label(r['req'])}」子件「{_label(s)}」未精确命中,近似候选「{cand_txt}」{sim_txt},需人工核对")
                                nh["entity_keys"] = [_entity_key(s)]
                                nh["dedup_key"] = f"{rule.id}|-|{_entity_key(s)}"
                                issues.append(nh)
                            if r.get("unknown_reason") == "grouping":  # 孤儿+子近似并存:两因各自成话
                                issues.append(_need_human(rule, f"复合附件「{_label(r['req'])}」子件无法自动分组,需人工核对"))
                        elif r.get("unknown_reason") == "near_miss":
                            # (P3 既有平件分支,原样保留)
                            ...
                        else:
                            # (P3 既有 grouping 分支,原样保留)
                            ...
```

- `dedup_key` 按子行实体键派生（`attachment:3.2` 风格,`_entity_key` 直读 no/name,对子行 dict 即用）,父行 grouping 消息键不同,无互吞（I-1 同规）。
- `_label(s)` 对子行 dict 直接复用（`3.2 中标通知书` 形）。
- 平件与 grouping 两分支的措辞**一字节不变**——金标准 `L2-020-near-miss-unknown`（contains 近似候选/E-2/中标通知书）与 `L2-020-unknown-group-failure`（contains 无法自动分组/资格审查文件）是回归面。

## 3. 投影透传: 零改动

`build_checklist` 行字典带 `sub_results: e.get("sub_results") or []` 原样透传,端点 routers 不触碰 → 子行新增的 `status/unknown_reason/negative_evidence` 键自动到达 checklist JSON。前端展示是独立挂账切片,本切片不做 UI。

## 4. att_count: 零交互

att_count 只数 **PARTIAL 父行**（rule_runner :269-277),不读子行。子行 MISSING→UNKNOWN 使父行 MISSING→UNKNOWN,原 Missing 父行本就不在 PARTIAL 名单,名单内容不变。语义上该父行从 att_check 的 fatal(miss) 移入 need_human(unknown)——这正是 P3.2 的目的,与 P3 平件降级同哲学。

## 5. 金标准（red-first,铁律同 P3）

新题 `golden/cases/L2-020-subitem-near-miss-unknown.yaml`（strict）:

- requirements: `[{no: "3", name: "资格审查文件", sub_items: [{no: "3.1", name: "营业执照"}, {no: "3.2", name: "中标通知书"}]}]`
- provided: `[{no: "3-1", name: "营业执照", page: 40}, {no: "", name: "中标通知书回执", page: 41}]`
- 预期链: 3.1 经位置通道命中 `3-1` → taken;3.2 三通道皆空(name「中标通知书回执」≠「中标通知书」),池内唯一未占用项 sim≈0.8333≥0.75 → 子行 UNKNOWN(near_miss) → 父行 UNKNOWN。`{no:"",...}` 刻意不写成 `3-2回执`——那会命中 `_refs_parent` 进 orphan 池,污染证据池,夹具必须绕开。
- expect: L2-020 fatal verdict `need_human`, message `contains: ["子件", "3.2", "中标通知书", "近似候选"]`; `expect_absent: [L2-024]`; checklist `unknown_count: 1`, `status_by_no: {"3": "UNKNOWN"}`。
- red-first 证据: 现引擎子行 MISSING → 父行 MISSING → L2-020 fatal violation,与期望背离,落红后归档 CALIBRATION 批D。

既有 51 题（49+P3 两题）零翻红预期: group-failure 题（subs 皆命中,纯孤儿）与 three-channel 题（subs 皆命中）均无 MISSING 子行,门不触发;P3.2 落地后全量 52 题。

## 6. 测试计划

`test_bid_review_attachments.py`:
- **审计既有复合测试**: P3.2 后凡夹具存在「MISSING 子行 + 池内 sim≥0.75 候选」的,父/子状态会翻——逐一核对,只允许 ① P3 v1 钉 `test_composite_sub_row_evidence_only_no_status_change`（按设计更新: 更名 `test_composite_sub_row_near_miss_downgrades`,断言子行 UNKNOWN+unknown_reason+证据完整）② 纯真缺失夹具（sim 门外）状态不变。任何其它翻红 = 夹具事故,修夹具不修引擎。
- 新增: 子行降级钉（父行 UNKNOWN+unknown_reason="near_miss"+子行 UNKNOWN+证据）；阈值生效钉（monkeypatch NEAR_MISS_GATE=0.90,子行保持 MISSING、父行 MISSING）；orphan+子近似并存钉（父行戳 grouping,子行各自 near_miss）；空名子行短路钉（`_sim_cands` 空,保持 MISSING）；build_checklist 子行键透传钉。

`test_bid_review_rule_runner.py`:
- 新增: 子近似消息钉（need_human / 「子件」「3.2」「近似候选」「0.83」渲染 / entity_keys=attachment:3.2 / dedup_key）；孤儿+子近似双话术钉（两条 issue,dedup 键互异）；grouping 话术原样钉（既有,应零改动通过）。

金标准 CLI: 52 题（51+1）total / failed 0 / exit 0;模块测试数口径按 cerebrum 三数核（cases/*.yaml 数 = CLI total = pytest 参数化数,当前 51→52）。

## 7. 验收标准

1. 金标准 52 题零翻红（既有 51 不动）,新题 red-first 且落红证据入 CALIBRATION 批D。
2. 平件/grouping 两分支措辞逐字节不变（既有双钉测试通过即证）。
3. 子行门不触碰 `taken`: 全测试文件 grep 无新增 taken 写入;占用排除语义由既有 `test_near_miss_pool_excludes_taken_candidates` 守护。
4. ruff check+format 干净;bid_review 全家 + golden CLI 绿。
5. EAI-CUSTOM 注释三处（§1.1/§1.2/§2）,引用本 spec 日期章节。

## 8. 挂账（本切片不做）

- 前端核对表卡子行 near-miss 展示（与 P3 平件负证据展示并轨,独立 UI 切片）。
- 阈值可配置 / 同义词 YAML 外置 / 指纹通道与 L0-L5 抽取管线（沿用 P3 spec §0 原判）。
- 子行 negative_evidence.channels 缺位置通道元数据（cosmetic,同 P3）。
