# L2 P3.3 前端核对表卡负证据/子行 near-miss 展示 设计

> 日期: 2026-11-03 ｜ 状态: 已落地（25eddf61c..9bbc33197 推送 origin/main-dev-fork）
> 前置: P3(平件负证据,dd7005561..52cfcb4ce) §0 挂账 + P3.2(复合子行门,a9a01210e..3a0edbba4) §8 挂账首项
> 性质: **纯前端切片**——后端投影 `build_checklist` 已透传两级 `unknown_reason`/`negative_evidence`(attachments.py:250 实证),零后端改动。

## 0. 背景与问题

P3.2 落地后核对表卡三类错位/缺失:

1. **文案错标**: ResultsView.tsx:1180 UNKNOWN 行文案硬编码「无法自动分组」——near_miss 降级的父行(近似候选在场,待人工核对)被错标成分组失败,语义误导。
2. **子件三态缺口**: `sub_results` 类型仍是 `"MATCHED"|"PARTIAL"|"MISSING"` 三态(api.ts:185-189),P3.2 子行 UNKNOWN 直接逃出类型;子件 marker `✓/✗` 二值无「?」面。
3. **负证据零渲染**: 平件/子行 `negative_evidence`(channels/pool/closest top-3≥0.30)与 `unknown_reason` 前端完全未消费——「查不出来≠没问题」的安全语义在核对表卡不可见。

## 1. 类型(api.ts)

```ts
/** P3/P3.2 行级负证据(引擎 _evidence);旧网关缺键 → 消费方 `??` 兜底。 */
export interface BidNegativeEvidence {
  channels: string[];
  pool: number;
  closest: Array<{ no: string; name: string; sim: number }>;
}
```

- `BidChecklistItem` 增 `unknown_reason?: "near_miss" | "grouping" | null` 与 `negative_evidence?: BidNegativeEvidence | null`(投影恒写键,值可 null;旧网关 undefined)。
- `sub_results` 项 `status` 并入 `"UNKNOWN"`(P3.2 子行门),并增同两可选键。

## 2. 渲染(ResultsView.tsx 核对表卡)

纯函数抽离 `components/checklist-display.ts`(可 rstest node 测):

```ts
/** 子件状态 marker:UNKNOWN(=P3.2 near_miss 门)→「?」,命中✓,否则✗。 */
export function subItemMarker(s: { status: string; found: number }): string;

/** near-miss hint 行(平件行与子件行共用;grouping/无证据 → [])。
 * closest[0] 在场 → 「未精确命中 · 近似候选「{no} {name}」相似度 {sim%}（待人工核对）」;
 * closest 空 → 「未精确命中 · 无近似候选记录（待人工核对）」。sim 用 (sim*100).toFixed(0)%。 */
export function nearMissHintLines(ev: BidNegativeEvidence | null | undefined): string[];
```

组件侧改动:

1. **UNKNOWN 文案分流**(:1180): `it.unknown_reason === "near_miss"` → 「未精确命中」;else(含 undefined/null)→ 「无法自动分组」保持。
2. **pill 分流**(checklistPill 调用处): near_miss → `.pill-orange`「近似待核」;其余 UNKNOWN → `.pill-gray`「需人工」不变。
3. **平件行 hint**: unknown_reason==="near_miss" 的行在 clause hd-sub 后追加 `nearMissHintLines(it.negative_evidence)` 逐行渲染(新增 hd-sub)。
4. **子件行**: join 行 marker 换 `subItemMarker`;join 行后对每个 `status==="UNKNOWN"` 且带 negative_evidence 的子件追加一行 `{no} {name}: {hint}`(每子件一行,复合件子件通常 ≤5,行数可控);子件无 UNKNOWN → 零增量。
5. **grouping 行**: 不渲染负证据(引擎 composite 父行 evidence=null),文案/pill 维持现状——「无法自动分组」语义不变。

## 3. CSS: 零新增

复用既有 `.hd-sub`(muted 层级)与 `.pill-orange`(bid-review.css:652)——不引入新 token/类。

## 4. 测试(tests/unit/extensions/bid-review/checklist-display.test.ts,node env)

- `subItemMarker`: 4 态各一断言(UNKNOWN→"?"、found>0→"✓"、MISSING→"✗"、PARTIAL→"✗")。
- `nearMissHintLines`: closest 在场(含 no 与空 no 两形态)/closest 空/null/undefined 五断言;sim 渲染钉(0.8333→"83%")。
- 组件渲染冒烟(.dom.test 可选,若 dom 夹具成本高则挂账)。

## 5. 验收

1. `pnpm typecheck`/`lint`/`test` 全绿(新增测试全过,存量零翻红)。
2. 旧网关兜底: 三键全 undefined 时不炸、hint 零渲染、文案回落「无法自动分组」——类型可选+`??` 消费即证。
3. 零后端改动: `git diff --stat` 不含 backend/。

## 6. 挂账(本切片不做)

- 审查队列 need_human 卡片的证据定位深化(三级跳转: 候选→原文页);issue 消息已含候选文案,现有 src-chip 可用。
- E2E(Playwright)补 near_miss 场景夹具——单测钉住纯函数后,e2e 随下次 UI 走查一起补。
- 负证据 channels 展示(平件行已窄,channels 属调试信息,checklist 卡不显)。
