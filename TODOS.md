# TODOS

## TODO: snapshot.py 三副本同步维护约定

- **What:** snapshot.py 现存三份副本（water-drainage / bid-proposal-writing / geological-report）——任一副本修 bug 时必须检查另两副本是否存在同缺陷并同步修复。
- **Why:** 2026-08-20 eng review 3A 决策接受第三份副本（技能=自包含分发单元，兄弟技能不互相 import），代价是修复不自动传播。bug-2198（正典文件名守卫）/bug-2200（show 显式 --input）类缺陷大概率三副本同在。
- **Pros:** 一条约定防静默漂移，成本近零。
- **Cons:** TODO 面板多一项；修复 bug 时多一步检查。
- **Context:** water 版 168 行 stdlib 为正典源。geological-report 副本将额外携带 SHA-256 状态哈希清单（2B）与目录扫描差集报警——这两个增强若验证有效，应反向移植回 water/bid 两副本。发现新缺陷时先查 water 版是否已有修复。
- **Depends on / blocked by:** 无。

## TODO: 技能多副本脚本族扩员同步约定（snapshot → progress/calibrate/bank_compile）

- **What:** bid-proposal-writing v4（设计 docs/designs/bid-proposal-writing-v4-volume-architecture.md，eng-review 1A 定案 2026-09-05）照搬 geological-report 的 progress.py / calibrate.py / bank_compile.py 后，多副本脚本族从 1 种（snapshot）扩到 4 种——任一副本修 bug 时除原有 snapshot 三副本外，还必须检查新三种在 water/bid/geo 间的同缺陷。
- **Why:** 副本漂移已实证：snapshot.py geo 196 行 vs bid 190 行（6 行分叉）。geo D7 决策（技能=自包含分发单元，兄弟技能不互 import）使修复不自动传播；副本族每扩一种，同步检查成本线性上涨。
- **Pros:** 延续自包含分发纪律，无架构改动；一条约定防新副本静默漂移。
- **Cons:** 修 bug 检查面从 3 副本扩到 4 脚本 × 2-3 副本；未来若再照搬（如深度门变体）需继续扩此条目。
- **Context:** 2026-09-05 bid v4 eng-review 用户拍板 1A（照搬+TODOS 扩条目，否决公共库提取与精简裁剪）。若某副本缺陷反复出现 ≥2 次，重新考虑公共库提取（geo D7 否决记录在 admin-main-dev-fork-design-20260820-geological-report-v2.md D7）。
- **Depends on / blocked by:** bid v4 WP-2.1 开工（progress.py 落地时本条目即生效）。

## TODO: 普查/详查阶段模板实质填充 + 阶段参数化机制

- **What:** 勘探版管线验证稳定后，把 v1 附录A/B 模板按 exploration.json 同构升级为 survey.json / detail.json（每章 key_elements/writing_patterns/tables/std_refs + 表单族 + 公式链 + 合约集），并定义阶段切换机制——表单清单/确认门/合约集按 stage 参数化。
- **Why:** D2 决策只迁移 v1 内容套框架，实质填充无排期则永远不发生。2026-08-20 outside voice #9 指出：阶段参数化机制完全未定义，survey.json/detail.json 会引用这些阶段不存在的章节与工件（表8-2、五因素系数、勘查类型等勘探硬编码）。
- **Pros:** 三阶段全覆盖，扩展有既定路径。
- **Cons:** 依赖勘探版验证，短期不动；提前做会在管线变化时返工。
- **Context:** v1 附录A/B 模板已在本次迁移范围（references/stages/ 轻量占位）。阶段参数化的自然落点：SKILL.md 入口按 stage 选 stages/{stage}.json，表单清单/门/合约集全部从该文件驱动。
- **Depends on / blocked by:** 勘探版管线验证通过（SC-1~6 全绿）。

## TODO: CC1 特高品位倍数条款人工核实（线程 296611de 交付物 snapshot 前置）

- **What:** standards_index.json 尚无 DZ/T 0214-2020「特高品位剔除倍数」条款的机读文本——CC1 一致性合约保持 MANUAL（run-stage finalize rc=2 停门语义，snapshot 未落）。待地质专家对照 DZ/T 0214-2020 原文核实本项目工业指标 `outlier_multiple=2` 是否在铜矿档内（如 2~3 倍档）；确认后在 standards_index.json 的 DZ/T 0214-2020 条目补 text 字段（供 `check_cc` 正则解析「特高品位…N–M 倍」）并重跑 `progress.py run-stage finalize` 落 project_snapshot.json。
- **Why:** 2026-09-01 返修交付（线程 296611de）终验 fail=0，唯余此项 MANUAL；用户裁定暂不核实、未来找专家确认后修改完善（GB/HG 条款不采信 web_search 为既定红线）。
- **Context:** 线程 296611de-448f-44b8-bdcd-f75921364b2e；交付物+delivery_manifest 已落盘线程 outputs/；consistency pass 28 / warn 19 / manual 1 / fail 0。修复入口：改 `skills/public/geological-report/references/standards_index.json` → 重跑 finalize（容器双路径已同步同版脚本）。
- **Depends on / blocked by:** 专家人工核实 DZ/T 0214-2020 原文条款。

## TODO: 平台减负两处 + 凭据作废后 docmgr 旧副本回收（bid v4 评审延期项）

- **What:** ① collab-server `onStoreDocument` 每次 `Y.encodeStateAsUpdate` 全量落库两份、collab_updates 只增不清（`backend/collab-server/src/persistence.ts:33-44`）——增量化需同步重定义审计/恢复语义；② 编辑器 O(N) 全文序列化热点（1.5s 防抖保存全文 `blocksToMarkdownLossy` `PersonalBlockNoteEditor.tsx:424-531` + AI 面板 `documentContent` 写在 render `BlockNoteEditor.tsx:856-858`）；③ 交付凭据作废/重 build 清场后，已同步的 docmgr AIDocument 旧册行残留（项目文档空间互相可见），需按最新 manifest 的回收策略。
- **Why:** bid v4 分册架构落地后 BlockNote/协作不再是篇幅瓶颈（每册 ≤50 页），三项均降级为平台健康债；但长文档场景（非标书）仍会踩中，且 collab_updates 无限增长是存储隐患。2026-09-05 bid v4 eng-review C4 定案移出本期，外部声音 13A 增补副本回收。
- **Pros:** 三项都是独立小批次，互不阻塞；③ 依赖交付门/清场语义先落地（v4 WP-1/WP-2.3）。
- **Cons:** ① 的增量重放语义设计不当会破坏协作恢复；③ 涉及 docmgr 数据清理策略需产品确认。
- **Context:** 证据链见 docs/designs/bid-proposal-writing-v4-volume-architecture.md「平台减负项」节 + Revision 3。修复入口：persistence.ts 增量化、编辑器脏块序列化、docmgr service 按 manifest 对账清理。
- **Depends on / blocked by:** ③ blocked by bid v4 WP-1（清场语义）+ WP-2.3（deliverables manifest）；①② 无前置。
