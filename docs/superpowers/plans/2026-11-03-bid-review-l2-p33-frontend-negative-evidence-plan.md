# L2 P3.3 前端负证据展示 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。步骤用 `- [ ]` 勾选。
> spec: `docs/superpowers/specs/2026-11-03-bid-review-l2-p33-frontend-negative-evidence-design.md`(25eddf61c)

**Goal:** 核对表卡消费 P3/P3.2 两级 `unknown_reason`/`negative_evidence`——UNKNOWN 文案/pill 按成因分流、负证据 hint 行、子件「?」marker。纯前端零后端。

**Architecture:** 纯函数抽离 `components/checklist-display.ts`(node 可测) → api.ts 类型四键扩展(全部可选+旧网关兜底) → ResultsView 核对表卡四处接线。

**Tech Stack:** Next.js 16/React 19/TS/rstest(`@rstest/core`,node 环境纯逻辑测试)。

---

### Task 1: 纯函数模块 + 单测(TDD)

**Files:**
- Create: `frontend/src/extensions/bid-review/components/checklist-display.ts`
- Test: `frontend/tests/unit/extensions/bid-review-checklist-display.test.ts`

- [ ] **Step 1.1: 先写测试**(node env,平铺命名对齐既有 `bid-review-*` 系列)

```ts
import { describe, expect, test } from "@rstest/core";

import {
  nearMissHintLines,
  subItemMarker,
} from "@/extensions/bid-review/components/checklist-display";

describe("subItemMarker", () => {
  test("UNKNOWN → ?(P3.2 子行门)", () => {
    expect(subItemMarker({ status: "UNKNOWN", found: 0 })).toBe("?");
  });
  test("命中 → ✓", () => {
    expect(subItemMarker({ status: "MATCHED", found: 1 })).toBe("✓");
  });
  test("PARTIAL → ✗", () => {
    expect(subItemMarker({ status: "PARTIAL", found: 1 })).toBe("✗");
  });
  test("MISSING → ✗", () => {
    expect(subItemMarker({ status: "MISSING", found: 0 })).toBe("✗");
  });
});

describe("nearMissHintLines", () => {
  test("closest 在场(no+name)→ 含候选与百分比", () => {
    expect(
      nearMissHintLines({
        channels: ["name"],
        pool: 1,
        closest: [{ no: "3-2", name: "中标通知书回执", sim: 0.8333 }],
      }),
    ).toEqual(["未精确命中 · 近似候选「3-2 中标通知书回执」相似度 83%（待人工核对）"]);
  });
  test("closest[0] 无 no → 只显 name", () => {
    expect(
      nearMissHintLines({
        channels: ["name"],
        pool: 1,
        closest: [{ no: "", name: "中标通知书回执", sim: 0.8 }],
      }),
    ).toEqual(["未精确命中 · 近似候选「中标通知书回执」相似度 80%（待人工核对）"]);
  });
  test("closest 空 → 无近似候选记录", () => {
    expect(nearMissHintLines({ channels: [], pool: 0, closest: [] })).toEqual([
      "未精确命中 · 无近似候选记录（待人工核对）",
    ]);
  });
  test("null/undefined(旧网关)→ 零渲染", () => {
    expect(nearMissHintLines(null)).toEqual([]);
    expect(nearMissHintLines(undefined)).toEqual([]);
  });
});
```

- [ ] **Step 1.2: 验红** `cd frontend && pnpm test -- tests/unit/extensions/bid-review-checklist-display.test.ts`(或 `pnpm exec rstest <file>`——模块不存在,收集期失败即红)。

- [ ] **Step 1.3: 实现**

```ts
/**
 * 附件核对表卡纯展示函数(L2 P3.3 spec 2026-11-03 §2;EAI-CUSTOM):
 * P3 平件负证据 + P3.2 复合子行 near-miss 门的前端消费面。
 * 全部纯函数,无 React 依赖,rstest node 环境直测。
 */

import type { BidNegativeEvidence } from "@/extensions/bid-review/api";

/** 子件状态 marker(P3.3 §2 裁决2):UNKNOWN(=P3.2 near_miss 门产物)→「?」,命中「✓」,否则「✗」。 */
export function subItemMarker(s: { status: string; found: number }): string {
  if (s.status === "UNKNOWN") return "?";
  return s.found > 0 ? "✓" : "✗";
}

/** near-miss hint 行(P3.3 §2;ev null/undefined=旧网关 → 零渲染):
 * closest[0] 在场 → 「未精确命中 · 近似候选「{no} {name}」相似度 {sim%}（待人工核对）」;
 * closest 空 → 「未精确命中 · 无近似候选记录（待人工核对）」。 */
export function nearMissHintLines(
  ev: BidNegativeEvidence | null | undefined,
): string[] {
  const c0 = ev?.closest?.[0];
  if (!ev) return [];
  if (!c0) return ["未精确命中 · 无近似候选记录（待人工核对）"];
  const label = `${c0.no ? `${c0.no} ` : ""}${c0.name}`.trim() || "无近似候选记录";
  return [
    `未精确命中 · 近似候选「${label}」相似度 ${(c0.sim * 100).toFixed(0)}%（待人工核对）`,
  ];
}
```

注: `BidNegativeEvidence` 类型本任务先在 api.ts 声明(Task 2 Step 2.1 的类型块提前到本任务一起落,否则模块编译不过)——即 **Step 2.1 提前到 Task 1 执行**,Task 2 只做 ResultsView 接线。

- [ ] **Step 1.4: 验绿** 同命令,`8 passed`。
- [ ] **Step 1.5: prettier 定域** `cd frontend && pnpm exec prettier --write src/extensions/bid-review/components/checklist-display.ts tests/unit/extensions/bid-review-checklist-display.test.ts src/extensions/bid-review/api.ts`(**只准对这三个文件**,禁全仓 format:write——工作树有大量他人 WIP)。
- [ ] **Step 1.6: Commit**(显式路径)

```bash
git add frontend/src/extensions/bid-review/components/checklist-display.ts frontend/tests/unit/extensions/bid-review-checklist-display.test.ts frontend/src/extensions/bid-review/api.ts
git commit -m "feat(bid-review): L2-P3.3① 核对表纯展示函数+类型四键——subItemMarker(?/✓/✗)+nearMissHintLines(top-1 候选/空池兜底/null 零渲染);BidChecklistItem+sub_results 并 UNKNOWN 态+unknown_reason/negative_evidence 可选键(BidNegativeEvidence 新接口);rstest 8 测"
```

### Task 2: ResultsView 四处接线

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/ResultsView.tsx`(:50-53 import 块 / :1144 pill / :1154-1165 子件行 / :1180 文案;行号以现场为准,先读再改)

- [ ] **Step 2.1: import**——api import 块之后加(checklist-display 是 sibling 子路径,按字母序排 `@/extensions/bid-review/components/...` 在 `@/extensions/bid-review/api` 之后):

```tsx
import {
  nearMissHintLines,
  subItemMarker,
} from "@/extensions/bid-review/components/checklist-display";
```

- [ ] **Step 2.2: pill 分流**(:1144 `const pill = checklistPill(it.status);`):

```tsx
                      const pill =
                        it.status === "UNKNOWN" && it.unknown_reason === "near_miss"
                          ? { label: "近似待核", cls: "pill pill-orange" }
                          : checklistPill(it.status);
```

- [ ] **Step 2.3: 子件 marker + 负证据 hint 行**(:1154-1165 与 clause 行之后)。子件 join 的 marker 换 `subItemMarker(s)`;clause `</span>` 条件块**之后**追加两段(P3.3 §2:hint 统一排 clause 后):

```tsx
                            {it.unknown_reason === "near_miss"
                              ? nearMissHintLines(it.negative_evidence).map((h, hi) => (
                                  <div className="hd-sub" key={`pnm-${it.no}-${hi}`}>
                                    {h}
                                  </div>
                                ))
                              : null}
                            {(it.sub_results ?? [])
                              .filter((s) => s.status === "UNKNOWN")
                              .map((s, si) => (
                                <div className="hd-sub" key={`snm-${it.no}-${si}`}>
                                  {`${s.no ? `${s.no} ` : ""}${s.name}: `}
                                  {nearMissHintLines(s.negative_evidence)[0] ??
                                    "未精确命中（待人工核对）"}
                                </div>
                              ))}
```

- [ ] **Step 2.4: UNKNOWN 文案分流**(:1180):

```tsx
                            {it.status === "UNKNOWN"
                              ? it.unknown_reason === "near_miss"
                                ? "未精确命中"
                                : "无法自动分组"
                              : it.found > 0
                                ? `已提供 ${it.found} 份`
                                : "未提供"}
```

- [ ] **Step 2.5: 定域 prettier + lint**(三规则同 Step 1.5 域,ResultsView 替换 api.ts):

```bash
cd frontend && pnpm exec prettier --check src/extensions/bid-review/components/ResultsView.tsx src/extensions/bid-review/components/checklist-display.ts tests/unit/extensions/bid-review-checklist-display.test.ts src/extensions/bid-review/api.ts && pnpm exec eslint src/extensions/bid-review/components/ResultsView.tsx src/extensions/bid-review/components/checklist-display.ts
```

- [ ] **Step 2.6: Commit**

```bash
git add frontend/src/extensions/bid-review/components/ResultsView.tsx
git commit -m "feat(bid-review): L2-P3.3② 核对表卡接线——UNKNOWN 文案/pill 按成因分流(near_miss=未精确命中+橙近似待核,grouping=无法自动分组+灰需人工);平件/子行负证据 hint 行(hd-sub);子件 marker 三值(?/✓/✗);旧网关三键 undefined 零渲染兜底"
```

### Task 3: 全量验证收尾

- [ ] **Step 3.1**: `cd frontend && pnpm check`(lint+typecheck 全仓——存量债如实报告,只须「无新增」;用 `git stash` 不行(他人 WIP),改用: 对照 HEAD 版本跑同命令比对新增告警,或直接报告全量输出并标注新增项)。
- [ ] **Step 3.2**: `cd frontend && pnpm test` 全量单测绿(存量零翻红)。
- [ ] **Step 3.3**: 零后端核 `git diff 25eddf61c..HEAD --stat -- backend/` 输出为空。
- [ ] **Step 3.4**: 向 controller 报告(数字+偏差),controller push+收尾。

---

## 执行约束

1. 分支 main-dev-fork,**绝不 push**(controller 收尾统一推)。
2. **禁全仓 `pnpm format:write` / `eslint --fix` / `prettier --write`**——工作树有大量他人 WIP 文件,定域只碰本切片四文件。
3. 外来 WIP 禁碰(git status 里全部 frontend 其它修改文件、backend contract_price/settings)。
4. 不碰 `.wolf/`;不改 spec/plan 文档;零后端文件。
5. 中文一律 Edit/Write 工具;commit 显式路径。
6. 行号是写作时点快照,先读现场再改;结构与 spec §2 冲突时以 spec 为准并报告。
7. 测试跑数如实报告;pnpm test 全量若存量红,区分「本切片引入」与「既有」(对照 HEAD 基线),既有红如实上报不修。

## Self-Review(已跑)

1. spec 覆盖: §1 类型→Step 1.3(提前);§2 五点→Steps 2.2-2.4(pill/文案/hint/marker;grouping 维持现状=不渲染,接线零代码);§4→Step 1.1(8 测);§5→Task 3;§3 零 CSS=无步骤,验收含。
2. 占位扫描: 全代码步骤带完整代码,无 TBD。
3. 类型一致性: `BidNegativeEvidence`/`subItemMarker`/`nearMissHintLines` 拼写各任务一致;Task 1 依赖 Task 2 类型块的处理已显式提前,无循环。
