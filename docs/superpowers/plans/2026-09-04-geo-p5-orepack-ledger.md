# Phase 5 — ore_pack 孵化 + 台账清偿 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ore_pack 批量孵化管线（LLM 抽草稿→人审→ore_packs/<矿种>.json 落 repo + SKILL 装载联动）+ Phase 3 终审台账 10 项清偿。

**Architecture:** 抽取管线复用知识工厂 ExtractionLLMClient 形态（create_chat_model + 6 级 JSON 容错 + Semaphore 限流 + DB 默认模型）；草稿落 gsb_ore_pack_drafts 表 → 管理页新 tab 人审 → 过审后由后端写 repo `ore_packs/<矿种>.json`（git 资产，dev bind-mount 直写）；词表单源裁决=5 production slug（other 不孵化）。台账清偿为独立小修不与主线交叉。

**Tech Stack:** FastAPI + SQLAlchemy（gsb_ 新表 migrate_db 加列/建表）+ ExtractionLLMClient 形态 + Next.js 新 tab + argparse（CLI ore-pack 子命令）。

**Spec:** 上游 `2026-09-01-geo-sample-bank-design.md` §5.3/§9（ore_pack 批量孵化 LLM 抽取+人审）；recon wf_c2326e39 三路实证。

**约定（全任务通用）：** pathspec 提交；并发会话活跃动手前 git log -1 复核；后端测试 `cd backend && PYTHONPATH=. uv run pytest ...`；EAI-CUSTOM 注释；Do NOT restart docker（T8 统一）。

---

### Task 1: 台账清偿 A——后端三修（TOCTOU/redact 漂移/rates=null）

**Files:**
- Modify: `backend/app/extensions/geo_samples/routers.py`（parse_batch_impl 行级守卫改互斥 409 + migrate_db 部分唯一索引）
- Modify: `backend/app/extensions/geo_samples/service.py`（run_redact 漂移重查）
- Modify: `skills/public/geological-report/scripts/consistency.py:307`（rates={} 守卫——⚠️ 该文件属并发硬化域，动手前 git log -1 复核且只加 `or {}` 一处）
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加）

**修法：**
1. **parse-batch TOCTOU**：migrate_db 加部分唯一索引 `CREATE UNIQUE INDEX IF NOT EXISTS uq_gsb_run_running ON gsb_run_history(document_id) WHERE status='running' AND run_type IN ('parse','redact')`——注意既有数据若有违例行须先清理（迁移内先 DELETE 重复 running 保留最新）。parse_batch_impl 捕获 IntegrityError → 409「该样例解析已在调度」。行级 has_running_run 跳过守卫保留（双保险）。
2. **run_redact 漂移重查**（对齐 run_parse R2 模式）：后台执行前 `get_document_fresh` 重取，`status != "parsed"` → finish_run failed「document state changed during redact」+ return。
3. **rates=null**：consistency.py:307 `eco.get("rates", {})` → `(eco.get("rates") or {})`；同函数 :313-314 concentrate/prices 同款守卫。

- [ ] **Step 1: 失败测试**（TOCTOU 难直测——部分唯一索引用 sqlite 不支持 partial index，改为：①run_redact 漂移测试（fresh 重取 redacted → finish failed）；②rates=null 单测：eco={"rates": None} → check_fc 不抛且 FC7 跳过；③migrate_db 索引存在断言（PG 实跑验证留 T8））
- [ ] **Step 2: 实现** → **Step 3: 全绿**（geo 系 -q）→ **Step 4: Commit**

```bash
git add backend/app/extensions/geo_samples/routers.py backend/app/extensions/geo_samples/service.py backend/app/extensions/geo_samples/crud.py skills/public/geological-report/scripts/consistency.py backend/tests/test_geo_sample_bank_compile.py
git commit -m "fix(geo-samples): partial unique index + redact drift guard + rates-null guard (P5 ledger A)" -- <上述文件>
```

---

### Task 2: 台账清偿 B——前端+基建三修

**Files:**
- Modify: `frontend/src/extensions/api/client.ts`（authFormFetch 422 数组 detail 处理对齐 authFetch）
- Modify: `frontend/src/extensions/geo-samples/components/DocumentsView.tsx`（下一页 disabled 用 total）
- Modify: `backend/tests/conftest.py`（9 键清单维护契约注释）
- Delete: `backend/test_env.py`、`backend/test_auth_debug.py`（模块级 override=True 毒化源，裸 pytest 收集即污染；内容为调试遗留——删除前 cat 确认无独有逻辑）
- Test: `backend/tests/test_eai_cli.py`（追加）

**修法**：①authFormFetch 错误解析对齐 authFetch 的数组 detail 分支（client.ts:113 附近）；②下一页 disabled 改 `(page + 1) * pageSize >= (data?.total ?? docs.length)`；③conftest 中和块注释尾加「新增 DEER_FLOW_*/OPENAI 外键时须同步此清单」；④两调试脚本删除（git rm；pytest testpaths 仍建议后续加，不在本期）。

- [ ] **Step 1: 前端 typecheck/lint** → **Step 2: 后端 -q 零回归** → **Step 3: Commit**

```bash
git add frontend/src/extensions/api/client.ts frontend/src/extensions/geo-samples/components/DocumentsView.tsx backend/tests/conftest.py
git rm backend/test_env.py backend/test_auth_debug.py
git commit -m "fix(geo-samples): authFormFetch 422 arrays + total pagination + conftest note + debug scripts removal (P5 ledger B)" -- <上述文件>
```

---

### Task 3: 台账清偿 C——离线 references 持久化决策落地

**Files:**
- Modify: `deploy/offline/MANUAL-UPGRADE.md`（env 接线段追加持久化警示——已由 P3-T9 写过编译产物易失性，本任务补**具体操作**：升级前备份 references 子路径 / compose 卷挂载示例）
- Modify: `docker/docker-compose-dev.yaml`（gateway 卷追加 `../skills:/app/skills` 已存在——确认即可，无改动则跳过）

- [ ] **Step 1:** MANUAL-UPGRADE.md geo-samples 段追加「编译产物备份/恢复操作」小节（tar 命令示例 + 卷挂载可选方案 + gsb_documents.status 回退 SQL）
- [ ] **Step 2: Commit**（`docs(geo-samples): offline references persistence runbook (P5 ledger)`）

---

### Task 4: ore_pack schema 锁定（契约文档 + 草稿校验器）

**Files:**
- Create: `skills/public/geological-report/references/ore_packs/README.md`（schema 契约文档）
- Create: `backend/app/extensions/geo_samples/ore_pack_schema.py`（机器可校验器——键集合/形态/锚点守卫纯函数）
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加）

**schema 契约**（从 copper.json 实例提炼 + 设计文档契约）：
- 必有元数据键：version/ore/generated
- 业务键白名单（8 键同 copper）：basic_analysis_items(数组)/phase_analysis(对象)/ore_natural_types_anchored(对象)/byproduct_policy(串)/bulk_density_practice(对象)/green_exploration(串)/typical_deposit_models(对象数组)/reporting_notes(数组)
- **锚点守卫**：全文须引用 ≥1 个 formulas 编号（L11/S1/B1/E3/E4 集）——防 v1 prose 复辟
- **【待核实】形态守卫**：未核实阈值必须 `{"status": "【待核实】", ...}` 形态
- 矿种 slug ∈ 5 production slug（other 不孵化——词表单源裁决）

**Step 1: 校验器失败测试**（copper.json 真实例 PASS + 构造的坏例 FAIL：缺锚点/待核实裸串/未知键）→ **Step 2: 实现 validate_ore_pack(path_or_dict) -> list[errors]** → **Step 3: copper.json 实例回归 PASS** → **Step 4: Commit**

```bash
git add skills/public/geological-report/references/ore_packs/README.md backend/app/extensions/geo_samples/ore_pack_schema.py backend/tests/test_geo_sample_bank_compile.py
git commit -m "feat(geo-samples): ore_pack schema contract + validator (batch-cli P5 T4)" -- <上述文件>
```

---

### Task 5: 抽取管线（ExtractionLLMClient 形态 + 草稿实体）

**Files:**
- Modify: `backend/app/extensions/geo_samples/models.py`（GsbOrePackDraft 表：id/mineral/slices_hash/draft_json/review_status(draft|approved|rejected)/review_note/reviewed_at/created_at）
- Modify: `backend/app/extensions/geo_samples/crud.py`（draft CRUD）
- Create: `backend/app/extensions/geo_samples/ore_pack_extract.py`（抽取服务——ExtractionLLMClient 形态：create_chat_model + 6 级 JSON 解析 + Semaphore(3)；输入=该矿种代表切片文本集合，输出=ore_pack 草稿 dict→validate_ore_pack 过滤）
- Modify: `backend/app/extensions/geo_samples/routers.py`（POST /ore-packs/extract {mineral, slice_paths[]} → 后台抽取 → 草稿落表；GET /ore-packs/drafts；POST /ore-packs/drafts/{id}/approve → 写 repo ore_packs/<mineral>.json（dev bind-mount 直写）+ standards_index 扩容义务清单返回）
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加；LLM 全 mock）

**要点**：
- 抽取 prompt 骨架：系统提示「从地质勘查报告切片抽取 {mineral} 矿种知识包 JSON，schema 如下（README 契约）…未核实阈值标【待核实】…禁编造」——用户消息=切片文本集合（每片截断 8000 字符）
- **validate_ore_pack 不过 → 草稿仍落表但 review_status=draft+errors 字段**（人审可见错误）；approve 前置=errors 空
- repo 写入：`Path(_REPO_ROOT)/"skills"/.../"ore_packs"/f"{mineral}.json"`（dev bind-mount；离线 caveat 沿 P3-T9 注记）
- **S1 词表单源裁决落地**：ore_packs 对齐 5 production slug；`ot`/银/镍/钼 显式不孵化（README 声明）
- LLM mock 全覆盖；Semaphore(3) 限流

- [ ] 步骤：失败测试（抽取 mock/校验过滤/approve 写 repo/错误草稿 approve 409）→ 实现 → 全绿 → Commit（`feat(geo-samples): ore_pack extraction pipeline + draft entity (P5 T5)`）

---

### Task 6: 人审 tab（前端矿种包孵化页）

**Files:**
- Create: `frontend/src/extensions/geo-samples/components/DraftsView.tsx`（草稿清单/逐字段核对/approve-reject）
- Modify: `frontend/src/extensions/geo-samples/api.ts` + `hooks.ts`（drafts API/hooks）
- Modify: `frontend/src/app/geo-samples/layout.tsx` + 新 page（drafts 路由，pageId `gsb:page:drafts`）
- Modify: `config/permissions.yaml`（gsb:page:drafts 注册——四处联动同步）
- Test: `frontend/tests/unit/extensions/geo-samples/api.test.ts`（追加 drafts API 用例）

- [ ] 步骤：API 测试先行 → 实现 → typecheck/lint → permissions.yaml 注册（pageId 四联动同 P1 T9 模式）→ Commit（`feat(geo-samples): drafts review tab (P5 T6)`）

---

### Task 7: SKILL 装载联动（消费契约首个代码消费者）

**Files:**
- Modify: `skills/public/geological-report/SKILL.md`（开题首动作追加：读 `references/ore_packs/<commodity 归一化>.json` 矿种知识包——无文件则 prose 硬编码知识兜底+声明；与 SKILL.md:235-237 prose 合并改写为数据驱动指引）
- Modify: `skills/public/geological-report/references/ore_packs/README.md`（消费契约段）
- Test: `backend/tests/test_geological_report_skill.py`（如结构断言需同步）

- [ ] 步骤：SKILL.md 开题段+矿种适配段改写（prose 硬编码 → 数据包优先/prose 兜底）→ 结构测试 → Commit（`feat(geo-samples): SKILL loads ore_packs by commodity with prose fallback (P5 T7)`）

---

### Task 8: CLI ore-pack 子命令 + 全量验收

**Files:**
- Modify: `tools/eai.py`（`ore-pack extract|status` 子命令——服务端型薄适配）
- Test: `backend/tests/test_eai_cli.py`（追加）

**验收 Step**：
- 全量门禁（后端 make lint && make test / 前端三闸）
- e2e：真实切片 ≥3 矿种（金/煤/铅锌）抽取 → 草稿审核 → ore_packs 落 repo → SKILL 结构测试 → copper.json 校验器回归
- 达成 spec 验收：**≥3 个新矿种包过审**（Phase 3 design :164）

---

## 完成判据（验收）

1. 门禁全绿（后端含 conftest 中和 / 前端三闸 / geo 全系）
2. ore_pack 管线 e2e：≥3 矿种草稿抽取→人审→ore_packs/<slug>.json 落 repo→validate_ore_pack PASS
3. SKILL.md 数据驱动装载 + prose 兜底；结构测试同步
4. 台账 10 项全部关闭或显式转 Phase 6（parse-batch 索引/redact 漂移/rates=null/authFormFetch/total 翻页/conftest 注记/调试脚本删除 = 清偿；离线持久化 = runbook 已落地）

## 明确不做（随需）

ore_pack 版本迁移/多版本并存；standards_index 自动录入（【待核实】仍人工）；抽取质量自动评分；前端草稿 diff 视图（列表+JSON 预览足够 V1）。台账第 9 项（parse-batch failed 行重试路径）本期仅文档化：parse-batch docstring 补「failed 行经单体 /parse 重试」一句。

## 关键风险备忘

1. **LLM 草稿质量**：抽取幻觉=【待核实】标记+人审闸门双兜底；validate_ore_pack 锚点守卫防 prose 复辟
2. **repo 写入部署域**：dev bind-mount 直写可用；离线生产 references 易失性已入 runbook（P3-T9）——Phase 5 验收在 dev 跑
3. **词表六处同步**：孵化新矿种触发六处变更面（title_parser/build_output/schemas/GSB_MINERALS/mineral_code/FilterBar）——Task 5 起每次加矿种跑六处检查清单
4. **copper.json 零校验现状**：validate_ore_pack 回归用例锁 copper.json（首实例即契约活样例）
