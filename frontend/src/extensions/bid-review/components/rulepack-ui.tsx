"use client";

/**
 * EAI-CUSTOM (2026-10-30): 规则库/规则效果看板共享表件——参照 docs/designs/2026-10-30-bid-review-ui.html
 * #s9/#s10(类词汇 = app/bid-review/bid-review.css 的 .brx 作用域)。两页「列同规则库」
 * 契约由 {@link RuleStatsTable} 单点承担:规则 id(.mono)/名称/层级 pill/严重度 pill
 * (fatal=err/major=orange/minor+info=gray)/类型 chip(det|sem|hyb)/命中/误报/采纳计数。
 * stats 缺失显示「—」(伪零纪律:未经人工回流 ≠ 0);高误报 = hit>0 且 fp/hit≥0.2,
 * id 旁加 .pill-warn「误报 NN%」(原型 s9 口径:≥20% 自动回流评测集并进看板 FAIL 名单)。
 */

import type { RulePackRule } from "@/extensions/bid-review/api";

/** 规则包 stats 行(api.RulePackOut.stats 值;字段缺省 = 未回流)。 */
export type RuleStat = { hit?: number; fp?: number; adopted?: number };

/** RuleStatsTable 行:规则定义 + 该规则回流计数(缺失字段显示 —)。 */
export interface RuleStatsRow {
  /** React key(单规则包内=规则 id;跨规则包须带包限定前缀防碰撞)。 */
  key: string;
  rule: RulePackRule;
  stat: RuleStat;
}

/** 类型 chip 词汇(规则包 YAML type → det/sem/hyb,ui-spec §3.4 同映射)。 */
const TYPE_LABELS: Record<string, string> = {
  deterministic: "det",
  semantic: "sem",
  hybrid: "hyb",
};

/** severity → 原型 pill 档(fatal=err/major=orange/minor+info=gray,2026-10-30 任务口径;
 * 与 primitives.severityPill 的 warn/info 档不同——那边是 2026-10-29 spec 词汇)。 */
function severityBrx(severity: string): { cls: string; label: string } {
  switch (severity) {
    case "fatal":
      return { cls: "pill pill-err", label: "致命" };
    case "major":
      return { cls: "pill pill-orange", label: "主要" };
    case "minor":
      return { cls: "pill pill-gray", label: "次要" };
    case "info":
      return { cls: "pill pill-gray", label: "提示" };
    default:
      // 空串兜底走这里(`||` 会被 prefer-nullish-coalescing 拦,显式判空)
      return {
        cls: "pill pill-gray",
        label: severity === "" ? "未知" : severity,
      };
  }
}

/** 误报率 %(四舍五入整数);hit=0(分母为零,无口径)返回 null。 */
export function fpRatePercent(stat: RuleStat): number | null {
  const hit = stat.hit ?? 0;
  if (hit <= 0) return null;
  return Math.round(((stat.fp ?? 0) / hit) * 100);
}

/** 高误报判定(原型 s9/s10 口径):hit>0 且 fp/hit≥0.2。 */
export function isHighFp(stat: RuleStat): boolean {
  const hit = stat.hit ?? 0;
  return hit > 0 && (stat.fp ?? 0) / hit >= 0.2;
}

/** 计数格:stats 字段缺失(undefined/null)显示 —,严禁显示 0(伪零纪律沿 TasksView 修复轮)。 */
function CountCell({ value }: { value?: number }) {
  return <td className="r num">{value ?? "—"}</td>;
}

/** 规则 stats 表(规则库/效果看板两页同构,「列同规则库」契约单点;.tbl 八列)。 */
export function RuleStatsTable({ rows }: { rows: RuleStatsRow[] }) {
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>规则</th>
          <th>名称</th>
          <th>层级</th>
          <th>严重度</th>
          <th>类型</th>
          <th className="r">命中</th>
          <th className="r">误报</th>
          <th className="r">采纳</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ key, rule, stat }) => {
          const sev = severityBrx(rule.severity);
          const pct = fpRatePercent(stat);
          return (
            <tr key={key}>
              <td className="mono">
                {rule.id}
                {pct !== null && isHighFp(stat) ? (
                  <span
                    className="pill pill-warn"
                    style={{ height: 18, fontSize: 11, marginLeft: 6 }}
                  >
                    误报 {pct}%
                  </span>
                ) : null}
              </td>
              <td>{rule.name}</td>
              <td>
                <span className="pill pill-main">{rule.layer}</span>
              </td>
              <td>
                <span className={sev.cls}>{sev.label}</span>
              </td>
              <td>
                <code className="k">{TYPE_LABELS[rule.type] ?? rule.type}</code>
              </td>
              <CountCell value={stat.hit} />
              <CountCell value={stat.fp} />
              <CountCell value={stat.adopted} />
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
