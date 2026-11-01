"use client";

/**
 * EAI-CUSTOM (2026-11-01 B10): 版本差异整屏——参照 docs/designs/2026-10-30-bid-review-ui.html
 * #s8(类词汇 = app/bid-review/bid-review.css 的 .brx 作用域)。挂 /bid-review/diff
 * (?task_id=当前 &prev=基准),导航入口与权限点(bid:page:results,同 results 域)在
 * app/bid-review/layout.tsx 注册。数据源 = GET /tasks/{id}/diff?prev=(B7 三态 +
 * B10 扩展 fields/rules);旧网关缺 fields/rules 键 → 诚实兜底文案,不装数据。
 * N/M 口径:M = added+removed(受变更影响),N = added+unchanged(新版问题总数)。
 * 原型的多版本 seg 切换(v1→v2 / v2→v3)与 inherit_from_review 增量继承属
 * spec §4 non-goals——单级 prev 链,页头只呈现一条对比。
 */

import { GitCompare } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

import {
  type BidDiffRuleSide,
  ApiError,
} from "@/extensions/bid-review/api";
import { TaskTitleTag } from "@/extensions/bid-review/components/TaskTitleTag";
import { useBidDiff, useBidTasks, useSelectedTask } from "@/extensions/bid-review/hooks";

/** 侧判定 → pill(present=false 一律「无问题」ok;present 且无 severity=need_human 类 → 需复核 warn)。 */
function sidePill(side: BidDiffRuleSide): { label: string; cls: string } {
  if (!side.present) return { label: "无问题", cls: "pill pill-ok" };
  switch (side.severity) {
    case "fatal":
      return { label: "致命", cls: "pill pill-err" };
    case "major":
      return { label: "主要", cls: "pill pill-orange" };
    case "minor":
      return { label: "次要", cls: "pill pill-warn" };
    case null:
      return { label: "需复核", cls: "pill pill-warn" };
    default:
      return { label: String(side.severity), cls: "pill pill-gray" };
  }
}

/** 变化列:一侧消失=已消除,一侧出现=新增,两侧都在比 severity,同 severity=无变化。 */
function changeLabel(prev: BidDiffRuleSide, cur: BidDiffRuleSide): string {
  if (prev.present && !cur.present) return "已消除";
  if (!prev.present && cur.present) return "新增";
  if (prev.present && cur.present && prev.severity !== cur.severity) return "判定变化";
  return "无变化";
}

export function DiffView() {
  const params = useSearchParams();
  const { taskId, task } = useSelectedTask();
  const { data: tasks } = useBidTasks();
  const prevId = params.get("prev");
  const diffQuery = useBidDiff(taskId, prevId);

  const curBiz = task?.biz_no ?? tasks?.find((t) => t.id === taskId)?.biz_no ?? null;
  const prevBiz = tasks?.find((t) => t.id === prevId)?.biz_no ?? null;

  const { impact, total } = useMemo(() => {
    const d = diffQuery.data;
    if (!d) return { impact: 0, total: 0 };
    return {
      impact: d.added.length + d.removed.length,
      total: d.added.length + d.unchanged_count,
    };
  }, [diffQuery.data]);

  if (!taskId || !prevId) {
    return (
      <div className="screen on">
        <div className="page-head">
          {/* 2026-11-01 用户:标题左侧加图标(与侧栏同源 GitCompare;先例=ResultsView ph-icon) */}
          <div className="ph-icon">
            <GitCompare className="ic" aria-hidden="true" />
          </div>
          <div>
            <h2>
              版本差异
              <TaskTitleTag taskId={taskId} bizNo={curBiz} />
            </h2>
            <p className="hd-sub">换版对比整屏</p>
          </div>
        </div>
        <div className="card">
          <div className="tbl-foot">
            未指定基准任务或当前任务——请从任务总览「对比基准任务」或审查结果页「换版重审」发起版本对比（URL 形如 /bid-review/diff?task_id=…&prev=…）。
          </div>
        </div>
      </div>
    );
  }

  const diff = diffQuery.data;

  return (
    <div className="screen on">
      <div className="page-head">
        <div className="ph-icon">
          <GitCompare className="ic" aria-hidden="true" />
        </div>
        <div>
          <h2>
            版本差异
            <TaskTitleTag taskId={taskId} bizNo={curBiz} />
          </h2>
          <p className="hd-sub">
            {prevBiz ?? prevId} → 本任务 · 变更影响 {total} 项问题中的 {impact} 项 · 依据两版基线包逐路径对比生成
          </p>
        </div>
      </div>

      {diffQuery.isError ? (
        <div className="note-bar errbar" role="alert">
          <span>
            差异加载失败：
            {diffQuery.error instanceof ApiError ? diffQuery.error.message : "请求失败"}
          </span>
          <button type="button" className="btn btn-sec btn-sm" onClick={() => void diffQuery.refetch()}>
            重试
          </button>
        </div>
      ) : null}

      {diffQuery.isPending ? (
        <div className="card">
          <div className="tbl-foot">差异计算中…</div>
        </div>
      ) : diff ? (
        <div className="split-wide">
          <div className="card">
            <div className="card-hd">
              <h3>关键内容差异</h3>
              <span className="hd-sub">{diff.fields?.length ?? 0} 处基线字段变更</span>
            </div>
            {!diff.fields || diff.fields.length === 0 ? (
              <div className="tbl-foot">
                无字段级差异可比——两版均需含基线包且字段值有变化（旧任务未抽取基线或任一侧无基线行时不比，不装数据）。
              </div>
            ) : (
              <div className="card-bd">
                {diff.fields.map((f) => (
                  <div key={f.path} style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                      {f.label || f.path}
                    </div>
                    <div className="dif-box">
                      <span className="dif-del">− {String(f.prev ?? "（旧版无此字段）")}</span>
                      <span className="dif-add">+ {String(f.cur ?? "（新版无此字段）")}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-hd">
              <h3>规则影响</h3>
              <span className="hd-sub">换版前后受影响的规则命中</span>
            </div>
            {!diff.rules || diff.rules.length === 0 ? (
              <div className="tbl-foot">无规则级影响数据（旧网关未提供或两版均无规则命中差异）。</div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>规则</th>
                    <th>旧判定</th>
                    <th>新判定</th>
                    <th>变化</th>
                  </tr>
                </thead>
                <tbody>
                  {diff.rules.map((r) => {
                    const prevPill = sidePill(r.prev);
                    const curPill = sidePill(r.cur);
                    return (
                      <tr key={r.rule_id}>
                        <td className="mono">{r.rule_id}</td>
                        <td>
                          <span className={prevPill.cls}>{prevPill.label}</span>
                        </td>
                        <td>
                          <span className={curPill.cls}>{curPill.label}</span>
                        </td>
                        <td>{changeLabel(r.prev, r.cur)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            <div className="tbl-foot">
              变更影响口径：新增 {diff.added.length} + 消除 {diff.removed.length} =
              影响 {impact} 项；两版结论一致的 {diff.unchanged_count} 项不重审。
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
