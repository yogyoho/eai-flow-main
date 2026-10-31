# Plan 8 — /baseline §4.4 增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基准确认页对齐原型 s4 的六项 §4.4 增强——页头待确认 pill、五主题字段族、裁定核对勾 gate、已抽取字段折叠、渐进门 meter、proto-banner 清除。

**Architecture:** 全部前端改动,零后端。`baselineFields.ts` 新增 FIELD_THEMES/themeOf(替代 FAMILIES/familyOf);`BaselineView.tsx` 加 verified/expanded 两个本地 state,gatePct 从二值改渐进公式。测试全部落在既有 `bid-review-baseline.dom.test.tsx`。

**Tech Stack:** Next.js 16 / React 19 / rstest(.dom.tsx happy-dom)。

**Spec:** docs/superpowers/specs/2026-10-31-bid-review-ux-redesign-design.md §4.4;原型 docs/designs/2026-10-30-bid-review-ui.html s4。

**行为契约不变:** 仅 awaiting_confirm 可确认(gateOpen)、409 分流 toast、DocLocateModal、无出处注、冲突裁定 adjudicate 端点语义。

---

### Task 1: T1 页头「待确认 N 项」pill + proto-banner 清除 + gate meter 渐进

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/BaselineView.tsx`
- Test: `frontend/tests/unit/extensions/bid-review-baseline.dom.test.tsx`

- [ ] **Step 1: 写失败测试** — 在一期 describe 末尾加一个 `it`(双行夹具一行已确认 → 无需交互即可断言渐进 50%):

```tsx
  it("页头待确认 pill + 渐进门 meter(Plan8 §4.4):pill=未确认行+未裁冲突,meter 渐进,proto-banner 清除", async () => {
    const HALF = [
      { ...BASELINES[0]!, confirmed: true },
      { ...BASELINES[1]!, confirmed: false },
    ];
    responder = (path) => {
      if (path.endsWith("/baselines")) return jsonRes({ items: HALF });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("awaiting_confirm"));
      return jsonRes({}, 404);
    };
    renderBaseline();

    // 页头 warn pill = 未确认行 1 + 未裁冲突 0 = 1 项
    expect(await screen.findByText(/待确认 1 项/)).toBeTruthy();
    // proto-banner 已清除(Plan8 T1)
    expect(screen.queryByText(/P0-2b/)).toBeNull();

    // 渐进 meter:已确认行 1 / 分母(2 行 + 0 冲突) = 50%
    const gateBtn = screen.getByRole("button", {
      name: /确认基准包并开始审查/,
    });
    await waitFor(() => expect(gateBtn.textContent).toContain("待确认 1 行"));
    expect(screen.getByText(/50%/)).toBeTruthy();
  });
```

- [ ] **Step 2: 跑红** — `cd /d/eai/eai-flow-main/frontend && pnpm test bid-review-baseline`;预期 FAIL(找不到 `待确认 1 项`,且 queryByText(/P0-2b/) 非 null)。

- [ ] **Step 3: 实现** — BaselineView.tsx 三处:

(a) 删 proto-banner 整块(L145-148 的 `<div className="proto-banner">…</div>`)。

(b) gatePct 二值公式换渐进(L139-141):

```tsx
  const unconfirmedRows = rows.filter((r) => !r.confirmed).length;
  // 门进度(Plan8 §4.4):渐进口径=(已确认行数+已裁定冲突数)/(总行数+冲突总数);
  // 无任务 0,已过门(非 awaiting_confirm)100%,分母 0(快照未到)0。
  const pendingTotal = rows.length + conflictPaths.length;
  const gatePct = !task
    ? 0
    : !gateOpen
      ? 100
      : pendingTotal === 0
        ? 0
        : Math.round(
            ((rows.filter((r) => r.confirmed).length +
              (conflictPaths.length - unresolvedCount)) /
              pendingTotal) *
              100,
          );
```

(c) ph-actions 状态 pill 之前插 warn pill;gate-bar 数字文本 `0%(…)` 换 `${gatePct}%`:

```tsx
        <div className="ph-actions">
          {gateOpen && unconfirmedRows + unresolvedCount > 0 ? (
            <span className="pill pill-orange">
              <span className="dot dot-warn" aria-hidden />
              待确认 {unconfirmedRows + unresolvedCount} 项
            </span>
          ) : null}
```

```tsx
            {gateOpen
              ? `${gatePct}%${unconfirmedRows + unresolvedCount > 0 ? `(待确认${unconfirmedRows > 0 ? ` · ${unconfirmedRows} 行未确认` : ""}${unresolvedCount > 0 ? ` · ${unresolvedCount} 处冲突未裁定` : ""})` : "(可确认)"}`
              : task
                ? "100%(已过确认门)"
                : "—"}
```

- [ ] **Step 4: 跑绿** — 同命令,PASS。

- [ ] **Step 5: 提交** — `git add src/extensions/bid-review/components/BaselineView.tsx tests/unit/extensions/bid-review-baseline.dom.test.tsx && git commit -m "feat(bid-review): /baseline 页头待确认pill+渐进门meter+proto-banner清除(Plan8 T1,spec §4.4)"`

---

### Task 2: T2 五主题字段族 FIELD_THEMES(替代首段路径族)

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/baselineFields.ts`
- Modify: `frontend/src/extensions/bid-review/components/BaselineView.tsx`
- Test: `frontend/tests/unit/extensions/bid-review-baseline.dom.test.tsx`

- [ ] **Step 1: 写失败测试** — 一期第一个 `it` 的族按钮断言换主题:

```tsx
    // 字段族主题(Plan8 §4.4):报价基准(默认选中)/清单基准按钮可见
    expect(
      await screen.findByRole("button", { name: /报价基准/ }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /清单基准/ })).toBeTruthy();
```

(原 `findByRole("button", { name: /招标基准/ })` 删除。)

- [ ] **Step 2: 跑红** — 预期 FAIL(无 报价基准 按钮)。

- [ ] **Step 3: 实现** —

(a) baselineFields.ts:FAMILIES+familyOf 删除(grep 确认仅 BaselineView 消费),换成:

```ts
// ── 主题族(Plan8 §4.4 增强):五业务主题,替代路径首段族(tender/bid)──
export const FIELD_THEMES = [
  "报价基准",
  "清单基准",
  "项目与主体",
  "工期与质保",
  "其他条款",
] as const;

export type FieldTheme = (typeof FIELD_THEMES)[number];

// 顺序即优先级:boq 先于 price(boq_items 不含 price 但规则表按序短路)
const THEME_RULES: [RegExp, FieldTheme][] = [
  [/boq|bill|清单/i, "清单基准"],
  [/price|subtotal|amount|budget|detail_rows|报价|价格/i, "报价基准"],
  [/project|identity|name|code|owner|agency|contact|项目|主体/i, "项目与主体"],
  [/duration|warranty|schedule|period|days|months|工期|质保/i, "工期与质保"],
];

/** 字段路径 → 业务主题;无匹配落「其他条款」。 */
export function themeOf(path: string): FieldTheme {
  for (const [re, theme] of THEME_RULES) if (re.test(path)) return theme;
  return "其他条款";
}
```

(b) BaselineView.tsx:import 换 `FIELD_THEMES, themeOf`(去 FAMILIES/familyOf,保持 eslint 序);`useState<string>(FIELD_THEMES[0] ?? "其他条款")`;famStats 的 key 用 `themeOf(f.path)`;famKey 兜底 `FIELD_THEMES[0] ?? "其他条款"`;fam-list 渲染 `FIELD_THEMES.filter((t) => famStats.has(t))`,删掉「FAMILIES 之外的族」fallback 渲染块(themeOf 永不落空)。

- [ ] **Step 4: 跑绿** — `pnpm test bid-review-baseline` PASS。

- [ ] **Step 5: 提交** — `git add src/extensions/bid-review/components/baselineFields.ts src/extensions/bid-review/components/BaselineView.tsx tests/unit/extensions/bid-review-baseline.dom.test.tsx && git commit -m "feat(bid-review): /baseline 五主题字段族FIELD_THEMES替代首段路径族(Plan8 T2,spec §4.4)"`

---

### Task 3: T3 裁定卡核对勾 gate(「我已核对两处原文」)

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/BaselineView.tsx`
- Test: `frontend/tests/unit/extensions/bid-review-baseline.dom.test.tsx`

- [ ] **Step 1: 改既有裁定流测试为红** — P2 第一个 `it` 中,`fireEvent.click(radios[1]!)` 后、点采纳前插两步(选中候选后采纳**仍禁用**,勾选后才启用):

```tsx
    fireEvent.click(radios[1]!);
    // 核对勾 gate(Plan8 §4.4):仅选候选不够,须勾「我已核对两处原文」
    await waitFor(() => expect((adopt as HTMLButtonElement).disabled).toBe(true));
    fireEvent.click(screen.getByRole("checkbox", { name: /我已核对两处原文/ }));
    await waitFor(() =>
      expect((adopt as HTMLButtonElement).disabled).toBe(false),
    );
    fireEvent.click(adopt);
```

- [ ] **Step 2: 跑红** — 预期 FAIL(getByRole checkbox 找不到)。

- [ ] **Step 3: 实现** — BaselineView.tsx:

(a) state:`const [verified, setVerified] = useState<Record<string, boolean>>({});`(picks 旁)。

(b) 裁定卡 radiogroup 之后、操作行之前,未裁定卡插核对勾(adj 已存在时不渲染,保持「已裁定快照直达」测试不变):

```tsx
                      {!adj ? (
                        <label
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            fontSize: 13,
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={!!verified[p]}
                            disabled={!gateOpen}
                            onChange={(e) =>
                              setVerified((m) => ({ ...m, [p]: e.target.checked }))
                            }
                          />
                          我已核对两处原文，确认上述裁定
                        </label>
                      ) : null}
```

(c) 采纳按钮 disabled 加 `!verified[p]`:

```tsx
                          disabled={
                            !gateOpen ||
                            picks[p] == null ||
                            !verified[p] ||
                            adjudicate.isPending
                          }
```

- [ ] **Step 4: 跑绿** — PASS(含「已裁定快照直达」用例不回归)。

- [ ] **Step 5: 提交** — `git add src/extensions/bid-review/components/BaselineView.tsx tests/unit/extensions/bid-review-baseline.dom.test.tsx && git commit -m "feat(bid-review): 裁定卡核对勾gate——勾选我已核对两处原文后采纳才可点(Plan8 T3,spec §4.4)"`

---

### Task 4: T4 已抽取字段折叠(非冲突非缺失默认折叠)

**Files:**
- Modify: `frontend/src/extensions/bid-review/components/BaselineView.tsx`
- Test: `frontend/tests/unit/extensions/bid-review-baseline.dom.test.tsx`

- [ ] **Step 1: 改一期第一个 `it` 为红** — 族按钮断言后,原 `findByText("tender.max_price")`/`getByText("8,000,000")` 改为折叠语义:

```tsx
    // 已抽取字段默认折叠(Plan8 §4.4):折叠注可见,max_price 卡不可见
    expect(screen.getByText(/已由引擎交叉校验通过/)).toBeTruthy();
    expect(screen.queryByText("tender.max_price")).toBeNull();
    expect(screen.queryByText("8,000,000")).toBeNull();

    // 点折叠注展开 → 字段卡出现,查看原文可用
    fireEvent.click(screen.getByText(/已由引擎交叉校验通过/));
    expect(await screen.findByText("tender.max_price")).toBeTruthy();
    expect(screen.getByText("8,000,000")).toBeTruthy();
```

其后「查看原文」断言保持;测试末尾追加清单基准直达(缺失字段不折叠):

```tsx
    // 清单基准:缺失字段不折叠,直接呈现
    fireEvent.click(screen.getByRole("button", { name: /清单基准/ }));
    expect(await screen.findByText("tender.boq_items")).toBeTruthy();
    expect(screen.getAllByText("缺失").length).toBeGreaterThan(0);
```

- [ ] **Step 2: 跑红** — 预期 FAIL(max_price 未折叠即可见)。

- [ ] **Step 3: 实现** — BaselineView.tsx:

(a) state:`const [expanded, setExpanded] = useState<Record<string, boolean>>({});`

(b) 折叠计数(命名冲突注意:组件里已有 `shown`):`const okCount = shown.filter((f) => !f.missing && !f.conflicted).length;`(missingTotal 旁)。

(c) 字段卡 map 开头加跳行(保序不重排):

```tsx
                {shown.map((f) => {
                  // 已抽取字段默认折叠(Plan8 §4.4):检索态全展开
                  if (
                    search === "" &&
                    !expanded[famKey] &&
                    !f.missing &&
                    !f.conflicted
                  )
                    return null;
                  const src = f.src;
```

(d) 空态判断之前(卡片 map 之后)加折叠注 toggle(原型 s4 句式):

```tsx
                {okCount > 0 && search === "" ? (
                  <button
                    type="button"
                    className="tbl-foot"
                    style={{
                      cursor: "pointer",
                      textAlign: "left",
                      background: "none",
                      border: "none",
                      width: "100%",
                    }}
                    onClick={() =>
                      setExpanded((m) => ({ ...m, [famKey]: !m[famKey] }))
                    }
                  >
                    {expanded[famKey]
                      ? `已展开全部字段——点击收起 ${okCount} 个已抽取字段`
                      : `其余 ${okCount} 个已抽取字段已由引擎交叉校验通过，点击展开逐项核对`}
                  </button>
                ) : null}
```

- [ ] **Step 4: 跑绿** — PASS。

- [ ] **Step 5: 提交** — `git add src/extensions/bid-review/components/BaselineView.tsx tests/unit/extensions/bid-review-baseline.dom.test.tsx && git commit -m "feat(bid-review): 已抽取字段默认折叠+折叠注toggle(Plan8 T4,spec §4.4)"`

---

### Task 5: T5 收尾

- [ ] **Step 1:** `cd /d/eai/eai-flow-main/frontend && pnpm exec prettier --write src/extensions/bid-review/components/BaselineView.tsx src/extensions/bid-review/components/baselineFields.ts tests/unit/extensions/bid-review-baseline.dom.test.tsx`
- [ ] **Step 2:** `pnpm test bid-review` 全量(68+ 用例 0 fail)
- [ ] **Step 3:** `pnpm lint -- --quiet 2>&1 | grep -c bid-review` 或直接 `pnpm lint` 确认 bid-review 范围 0 error;`pnpm typecheck` 确认非 contract-price 旧债 0 新增
- [ ] **Step 4:** prettier 增量单独 style commit;plan 全部 `- [x]`;`.wolf/memory.md`+`anatomy.md` 记账;提交 `git add -f ../docs/superpowers/plans/2026-10-31-bid-review-plan8-baseline-enhance.md ../.wolf/memory.md ../.wolf/anatomy.md && git commit -m "chore(bid-review): Plan8 收尾——计划勾选+wolf记账+格式化增量"`

---

## 挂账(非本计划)

- P2 裁定流测试可在 T3 后追加 meter 断言(裁定后 0%→50%)——可选项,不阻塞。
- B2 复核落库 / B3 页级置信 / B4 评分覆盖度 / B5-B7 版本对比 / 报告 PDF / B8 重试解析(spec 后端挂账,不在 UX 重构范围)。
