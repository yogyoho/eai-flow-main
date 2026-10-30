"use client";

/**
 * EAI-CUSTOM (2026-10-30): 规则效果看板——参照 docs/designs/2026-10-30-bid-review-ui.html
 * #s10(类词汇 = app/bid-review/bid-review.css 的 .brx 作用域)。挂 /bid-review/metrics,
 * 导航入口与权限点(bid:page:rules,同治理域)在 app/bid-review/layout.tsx 注册。
 * 诚实口径:独立评测端点未接入——四格 metric-strip(规则总数=Σrule_count/回流误报=Σfp/
 * 命中总数=Σhit/复核采纳=Σadopted,跨规则包求和)与逐规则 stats 表(按 fp 降序,
 * 列同规则库 = 共享 RuleStatsTable)全部来自人工复核回流(GET /rulepacks stats,
 * 复核「误报」动作自动回流);高误报规则(hit>0 且 fp/hit≥0.2)进 FAIL 名单(.pill-err)。
 * 原型 #s10 的评测样本/通过率/周趋势无数据源,不伪造,note-bar 说明数据来源。
 */

import {
  type RuleStatsRow,
  RuleStatsTable,
  fpRatePercent,
  isHighFp,
} from "@/extensions/bid-review/components/rulepack-ui";
import { useBidRulepacks } from "@/extensions/bid-review/hooks";

export function MetricsView() {
  const rulepacksQuery = useBidRulepacks();
  const packs = rulepacksQuery.data ?? [];

  const totals = { rules: 0, hit: 0, fp: 0, adopted: 0 };
  const rows: RuleStatsRow[] = [];
  for (const pack of packs) {
    totals.rules += pack.rule_count;
    for (const rule of pack.rules) {
      const stat = pack.stats[rule.id] ?? {};
      totals.hit += stat.hit ?? 0;
      totals.fp += stat.fp ?? 0;
      totals.adopted += stat.adopted ?? 0;
      // key 带包限定前缀:跨包 rule id 理论可碰撞(单包生产态下即纯 id 后缀)
      rows.push({ key: `${pack.name}@${pack.version}/${rule.id}`, rule, stat });
    }
  }
  // 按 fp 降序(任务口径);无 fp 数据(-1)沉底,同分按命中降序、再按 id 稳定输出
  rows.sort(
    (a, b) =>
      (b.stat.fp ?? -1) - (a.stat.fp ?? -1) ||
      (b.stat.hit ?? -1) - (a.stat.hit ?? -1) ||
      a.rule.id.localeCompare(b.rule.id),
  );
  const failList = rows.filter((r) => isHighFp(r.stat));

  return (
    <div className="screen on">
      <div className="page-head">
        <div>
          <h2>规则效果看板</h2>
          <p className="hd-sub">
            人工复核回流 stats（hit/fp/adopted）· 逐规则按误报数降序
          </p>
        </div>
        <div className="ph-actions">
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void rulepacksQuery.refetch()}
            disabled={rulepacksQuery.isFetching}
          >
            刷新
          </button>
        </div>
      </div>

      {rulepacksQuery.isError ? (
        <div className="note-bar errbar" role="alert">
          <span>规则包加载失败：{rulepacksQuery.error.message}</span>
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void rulepacksQuery.refetch()}
          >
            重试
          </button>
        </div>
      ) : null}

      {rulepacksQuery.isPending ? (
        <div className="card">
          <div className="tbl-foot">规则包加载中…</div>
        </div>
      ) : (
        <>
          <div className="metric-strip">
            <div className="metric-cell">
              <div className="m-lb">规则总数</div>
              <div className="m-v">
                {totals.rules}
                <span className="m-sub">条</span>
              </div>
            </div>
            <div className="metric-cell err">
              <div className="m-lb">回流误报</div>
              <div className="m-v">
                {totals.fp}
                <span className="m-sub">次</span>
              </div>
            </div>
            <div className="metric-cell">
              <div className="m-lb">命中总数</div>
              <div className="m-v">
                {totals.hit}
                <span className="m-sub">次</span>
              </div>
            </div>
            <div className="metric-cell">
              <div className="m-lb">复核采纳</div>
              <div className="m-v">
                {totals.adopted}
                <span className="m-sub">次</span>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: 12 }}>
            <div className="card-hd">
              <h3>逐规则回流统计</h3>
              <span className="hd-sub">按误报数降序</span>
              <div className="hd-right">
                <span className="hd-sub">{failList.length} 条 FAIL</span>
              </div>
            </div>
            {rows.length === 0 ? (
              <div className="tbl-foot">规则包暂无规则</div>
            ) : (
              <RuleStatsTable rows={rows} />
            )}
          </div>

          <div className="card" style={{ marginBottom: 12 }}>
            <div className="card-hd">
              <h3>高误报 FAIL 名单</h3>
              <span className="hd-sub">误报率 = 误报/命中 ≥ 20% 自动入榜</span>
            </div>
            {failList.length === 0 ? (
              <div className="tbl-foot">
                {totals.hit === 0
                  ? "尚无回流数据——命中与误报随人工复核产生"
                  : "暂无高误报规则"}
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>规则</th>
                    <th>名称</th>
                    <th>层级</th>
                    <th className="r">命中</th>
                    <th className="r">误报</th>
                    <th className="r">误报率</th>
                    <th>判定</th>
                  </tr>
                </thead>
                <tbody>
                  {failList.map(({ key, rule, stat }) => {
                    const pct = fpRatePercent(stat);
                    return (
                      <tr key={key}>
                        <td className="mono">{rule.id}</td>
                        <td>{rule.name}</td>
                        <td>
                          <span className="pill pill-main">{rule.layer}</span>
                        </td>
                        <td className="r num">{stat.hit}</td>
                        <td className="r num">{stat.fp}</td>
                        <td className="r num">
                          {pct === null ? "—" : `${pct}%`}
                        </td>
                        <td>
                          <span className="pill pill-err">FAIL</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div className="note-bar">
            独立评测端点未接入；当前指标来自人工复核回流
            stats（hit/fp/adopted），误报样本经复核「误报」动作自动回流。
          </div>
        </>
      )}
    </div>
  );
}
