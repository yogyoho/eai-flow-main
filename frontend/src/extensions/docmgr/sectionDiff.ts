// EAI-CUSTOM (全文操作 v2): 行级 LCS diff 纯工具——工单逐节 diff 卡的底座。
// 无依赖、无 DOM；经典 DP（O(n·m)，节级文本量级下足够）。
// 护栏：任一侧 >500 行即跳过 LCS，退化为整段 del+ins（更大文本的逐行对照无阅读价值）。

export type DiffLine = { type: "ctx" | "del" | "ins"; text: string };

const LINE_GUARD = 500;

export function diffLines(oldText: string, newText: string): DiffLine[] {
  // 空串视为 0 行（而非 [""]）：「无旧文本」应产出全 ins，而不是先删一行空行。
  const a = oldText ? oldText.split("\n") : [];
  const b = newText ? newText.split("\n") : [];

  if (a.length > LINE_GUARD || b.length > LINE_GUARD) {
    return [
      ...a.map((text): DiffLine => ({ type: "del", text })),
      ...b.map((text): DiffLine => ({ type: "ins", text })),
    ];
  }

  const n = a.length;
  const m = b.length;
  // dp[i][j] = a[i..] 与 b[j..] 的 LCS 长度（后缀表，便于正向回溯）。
  const dp: Uint32Array[] = Array.from(
    { length: n + 1 },
    () => new Uint32Array(m + 1),
  );
  for (let i = n - 1; i >= 0; i--) {
    const row = dp[i]!;
    const below = dp[i + 1]!;
    for (let j = m - 1; j >= 0; j--) {
      row[j] =
        a[i] === b[j] ? below[j + 1]! + 1 : Math.max(below[j]!, row[j + 1]!);
    }
  }

  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ type: "ctx", text: a[i]! });
      i++;
      j++;
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) {
      out.push({ type: "del", text: a[i]! });
      i++;
    } else {
      out.push({ type: "ins", text: b[j]! });
      j++;
    }
  }
  while (i < n) out.push({ type: "del", text: a[i++]! });
  while (j < m) out.push({ type: "ins", text: b[j++]! });
  return out;
}
