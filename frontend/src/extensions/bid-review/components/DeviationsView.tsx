"use client";

/**
 * EAI-CUSTOM (2026-11-01 B9): 响应偏离表——参照 docs/designs/2026-10-30-bid-review-ui.html
 * #s7(类词汇 = app/bid-review/bid-review.css 的 .brx 作用域)。挂 /bid-review/deviations,
 * 导航入口与权限点(bid:page:results,同 results 域——先例=review/metrics 挂宿主页)在
 * app/bid-review/layout.tsx 注册。数据源=抽取期 LLM 逐条对照(GET /tasks/{id}/deviations,
 * spec 2026-11-01 §1.2);旧任务零投影 → 空态引导,不装数据。证据 chip 经 task
 * engine_meta.docs 把 evidence.role 解析为 doc_id 后开 DocLocateModal(与问题证据同交互);
 * 解析不到(任务清单未含该侧文档)→ chip 降级为纯文本,不造假定位。
 */

import { Table2 } from "lucide-react";
import { useMemo, useState } from "react";

import {
  type BidDeviationItem,
  ApiError,
  type LocateTarget,
} from "@/extensions/bid-review/api";
import { DocLocateModal } from "@/extensions/bid-review/components/DocLocateModal";
import { TaskTitleTag } from "@/extensions/bid-review/components/TaskTitleTag";
import { useBidDeviations, useBidTasks, useSelectedTask } from "@/extensions/bid-review/hooks";

/** kind+severity → 五色 pill(词表=原型 s7;前端展示词汇,后端 kind 契约见 extract.py)。 */
function deviationPill(item: BidDeviationItem): { label: string; cls: string } {
  switch (item.kind) {
    case "missing":
      return { label: "漏项 · 致命", cls: "pill pill-err" };
    case "negative":
      return item.severity === "minor"
        ? { label: "负偏离 · 次要", cls: "pill pill-warn" }
        : { label: "负偏离 · 主要", cls: "pill pill-orange" };
    case "extra":
      return { label: "擅自增项 · 主要", cls: "pill pill-orange" };
    case "positive":
      return { label: "正偏离 · 优", cls: "pill pill-ok" };
    default:
      return { label: "一致", cls: "pill pill-ok" };
  }
}

/** 明细排序(严重度优先):漏项(fatal) → 负偏离·主要 → 擅自增项 → 负偏离·次要 → 正偏离 → 一致。 */
function deviationRank(item: BidDeviationItem): number {
  switch (item.kind) {
    case "missing":
      return 0;
    case "negative":
      return item.severity === "minor" ? 3 : 1;
    case "extra":
      return 2;
    case "positive":
      return 4;
    default:
      return 5;
  }
}

/** 可见行 CSV(BOM 防 Excel 乱码;客户端导出,后端不落盘)。 */
function exportCsv(items: BidDeviationItem[]): void {
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const head = ["#", "条目", "招标要求", "投标响应", "偏离判定", "证据"];
  const rows = items.map((it, i) => {
    const pill = deviationPill(it);
    const ev = it.evidence ? `${it.evidence.role}${it.evidence.page != null ? ` p.${it.evidence.page}` : ""} ${it.evidence.quote ?? ""}`.trim() : "";
    return [i + 1, it.item, it.tender_req ?? (it.kind === "extra" ? "（招标清单外）" : ""), it.bid_response ?? (it.kind === "missing" ? "未响应" : ""), pill.label, ev].map(esc).join(",");
  });
  const blob = new Blob(["﻿" + [head.map(esc).join(","), ...rows].join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "响应偏离表.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

export function DeviationsView() {
  const { taskId, task } = useSelectedTask();
  const { data: tasks } = useBidTasks();
  const devQuery = useBidDeviations(taskId);
  const [showMatch, setShowMatch] = useState(false);
  const [locate, setLocate] = useState<LocateTarget | null>(null);

  const bizNo = task?.biz_no ?? tasks?.find((t) => t.id === taskId)?.biz_no ?? null;
  const counts = devQuery.data?.counts;
  const hasItems = (devQuery.data?.items.length ?? 0) > 0;
  const sorted = useMemo(() => {
    const all = devQuery.data?.items ?? [];
    const visible = showMatch ? all : all.filter((it) => it.kind !== "match");
    return [...visible].sort((a, b) => deviationRank(a) - deviationRank(b));
  }, [devQuery.data, showMatch]);

  // evidence.role → doc_id(任务 docs 清单该侧首个);解析不到 → null(chip 纯文本)
  const docIdByRole = useMemo(() => {
    const docs = (task?.engine_meta as { docs?: Array<{ doc_id: string; role: string }> } | null | undefined)?.docs ?? [];
    const map: Record<string, string> = {};
    for (const d of docs) if (d.role && !map[d.role]) map[d.role] = d.doc_id;
    return map;
  }, [task]);

  return (
    <div className="screen on">
      <div className="page-head">
        {/* 2026-11-01 用户:标题左侧加图标(与侧栏同源 Table2;先例=ResultsView ph-icon) */}
        <div className="ph-icon">
          <Table2 className="ic" aria-hidden="true" />
        </div>
        <div>
          <h2>
            响应偏离表
            <TaskTitleTag taskId={taskId} bizNo={bizNo} />
          </h2>
          <p className="hd-sub">依据基准确认包与投标文件自动生成 · 供评审专家参考</p>
        </div>
        <div className="ph-actions">
          {counts && counts.missing > 0 ? (
            <span className="stage-chip" style={{ background: "var(--error-50)", color: "var(--error-700)" }}>
              {counts.missing} 项致命偏离（漏项）
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn-sec btn-sm"
            disabled={!devQuery.data || devQuery.data.items.length === 0}
            onClick={() => exportCsv(sorted)}
          >
            导出偏离表
          </button>
        </div>
      </div>

      {devQuery.isError ? (
        <div className="note-bar errbar" role="alert">
          <span>偏离表加载失败：{devQuery.error instanceof ApiError ? devQuery.error.message : "请求失败"}</span>
          <button type="button" className="btn btn-sec btn-sm" onClick={() => void devQuery.refetch()}>
            重试
          </button>
        </div>
      ) : null}

      {devQuery.isPending ? (
        <div className="card">
          <div className="tbl-foot">偏离表加载中…</div>
        </div>
      ) : counts ? (
        !hasItems ? (
          <div className="card">
            <div className="tbl-foot">
              本任务抽取时未包含偏离维度——基准确认后重新抽取即可生成逐条对照（旧任务无此数据，不回填）。
            </div>
          </div>
        ) : (
          <>
            <div className="metric-strip">
              <div className="metric-cell">
                <div className="m-lb">招标清单条目</div>
                <div className="m-v">{counts.tender_items}</div>
              </div>
              <div className="metric-cell">
                <div className="m-lb">投标响应条目</div>
                <div className="m-v">{counts.bid_items}</div>
              </div>
              <div className="metric-cell err">
                <div className="m-lb">负偏离</div>
                <div className="m-v">{counts.negative}</div>
              </div>
              <div className="metric-cell err">
                <div className="m-lb">未响应（漏项）</div>
                <div className="m-v">{counts.missing}</div>
              </div>
              <div className="metric-cell">
                <div className="m-lb">擅自增项</div>
                <div className="m-v">{counts.extra}</div>
              </div>
            </div>

            <div className="card">
              <div className="card-hd">
                <h3>偏离明细</h3>
                <span className="hd-sub">按严重度排序</span>
                <div className="hd-right">
                  <button type="button" className="btn btn-txt btn-sm" onClick={() => setShowMatch((v) => !v)}>
                    {showMatch ? "隐藏一致项" : "显示一致项"}
                  </button>
                </div>
              </div>
              {sorted.length === 0 ? (
                <div className="tbl-foot">无偏离项——投标对招标清单逐条一致。</div>
              ) : (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>条目</th>
                      <th>招标要求</th>
                      <th>投标响应</th>
                      <th>偏离判定</th>
                      <th>证据</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((it, i) => {
                      const ev = it.evidence;
                      const pill = deviationPill(it);
                      const docId = ev ? docIdByRole[ev.role] : undefined;
                      const chipText = ev
                        ? `${docId ?? ev.role}${ev.page != null ? ` p.${ev.page}` : ""}`
                        : "—";
                      return (
                        <tr key={`${it.item}-${i}`} className={it.kind === "extra" ? "unmapped-row" : undefined}>
                          <td className="num">{i + 1}</td>
                          <td>{it.item}</td>
                          <td className={it.tender_req ? undefined : "unmapped-cell"}>
                            {it.tender_req ?? (it.kind === "extra" ? "（招标清单外）" : "—")}
                          </td>
                          <td className={it.bid_response ? undefined : "unmapped-cell"}>
                            {it.bid_response ?? (it.kind === "missing" ? "未响应" : "—")}
                          </td>
                          <td>
                            <span className={pill.cls}>{pill.label}</span>
                          </td>
                          <td>
                            {ev ? (
                              <button
                                type="button"
                                className="src-chip"
                                title={ev.quote || undefined}
                                disabled={!docId}
                                style={{ cursor: docId ? "pointer" : "default" }}
                                onClick={
                                  docId
                                    ? () =>
                                        setLocate({
                                          docId,
                                          page: ev.page,
                                          quote: ev.quote,
                                        })
                                    : undefined
                                }
                              >
                                {chipText}
                              </button>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              <div className="tbl-foot">
                致命偏离（漏项）必须整改并重新审查后方可提交；负偏离须在商务偏差表中显式声明，隐瞒负偏离按废标风险提示（<b className="mono">L1-013</b> 规则组）
              </div>
            </div>
          </>
        )
      ) : null}

      {locate && taskId ? <DocLocateModal taskId={taskId} target={locate} onClose={() => setLocate(null)} /> : null}
    </div>
  );
}
