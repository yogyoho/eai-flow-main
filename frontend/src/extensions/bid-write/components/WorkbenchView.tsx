"use client";

import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  ChevronRight,
  FileText,
  Info,
  Lock,
  RefreshCw,
  Sparkles,
  Undo2,
  Redo2,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import {
  formatDate,
  formatPercent,
  matrixStatusLabel,
  matrixStatusTone,
  matrixStrategyLabel,
  matrixSummary,
  projectTitle,
  sourcePathLabel,
} from "@/extensions/bid-write/helpers";
import {
  useBidWriteGaps,
  useBidWriteMatrix,
  useSelectedWriteTask,
  useTaskMetrics,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";
import type { MatrixRowOut } from "@/extensions/bid-write/types";

interface OutlineSection {
  key: string;
  name: string;
  rows: MatrixRowOut[];
}

export function WorkbenchView() {
  const { taskId, task, isLoading } = useSelectedWriteTask();
  const matrix = useBidWriteMatrix(taskId);
  const gaps = useBidWriteGaps(taskId);
  const metrics = useTaskMetrics(taskId);
  const [activeSection, setActiveSection] = useState<string>("all");

  const rows = useMemo(() => matrix.data?.items ?? [], [matrix.data?.items]);
  const summary = useMemo(() => matrixSummary(rows), [rows]);
  const m = metrics.data?.metrics ?? null;

  const sections = useMemo<OutlineSection[]>(() => {
    const map = new Map<string, MatrixRowOut[]>();
    for (const row of rows) {
      const section = row.target_section.trim();
      const key = section ? section : `source:${row.source_path}`;
      const list = map.get(key) ?? [];
      list.push(row);
      map.set(key, list);
    }
    return [...map.entries()]
      .map(([key, groupRows]) => ({
        key,
        name: key.startsWith("source:")
          ? sourcePathLabel(key.slice("source:".length))
          : key,
        rows: groupRows,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [rows]);

  useEffect(() => {
    if (
      activeSection !== "all" &&
      !sections.some((s) => s.key === activeSection)
    ) {
      setActiveSection("all");
    }
  }, [activeSection, sections]);

  const visibleRows =
    activeSection === "all"
      ? rows
      : (sections.find((section) => section.key === activeSection)?.rows ?? []);

  const gapItems = gaps.data?.items ?? [];
  const noMaterial = gapItems.filter(
    (item) => item.material_state === "无对应素材",
  );
  const assertions = gaps.data?.assertions ?? null;

  return (
    <>
      <PageHead
        icon={BookOpen}
        title="④ 写作工作台"
        subtitle={
          task
            ? `${projectTitle(task)} · 矩阵/缺口/预审查/埋点实读；正文编辑器未接入`
            : "矩阵/缺口/预审查/埋点实读；正文编辑器未接入"
        }
        actions={
          <>
            <Link
              href={
                taskId ? writeTaskHref("review", taskId) : "/bid-write/review"
              }
              className="btn btn-sm"
            >
              预审查
            </Link>
            <Link
              href={
                taskId
                  ? writeTaskHref("generate", taskId)
                  : "/bid-write/generate"
              }
              className="btn pri btn-sm"
            >
              生成配置
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          </>
        }
      />

      {isLoading ? (
        <LoadingBlock label="正在加载工作台…" />
      ) : !task ? (
        <EmptyState
          icon={BookOpen}
          title="还没有写作项目"
          description="先创建项目并完成响应矩阵确认，再进入工作台。"
          action={
            <Link href="/bid-write" className="btn pri">
              去项目列表
            </Link>
          }
        />
      ) : matrix.isLoading ? (
        <LoadingBlock label="正在加载响应矩阵…" />
      ) : matrix.error ? (
        <ErrorBlock
          error={matrix.error}
          onRetry={() => void matrix.refetch()}
        />
      ) : (
        <>
          {summary.blocked > 0 ? (
            <div className="banner bad">
              <AlertTriangle size={15} aria-hidden="true" />
              <span>
                <b>{summary.blocked} 条低置信行未确认：</b>
                生成前必须回到解析确认清零阻断，否则断言与导出门禁会拦截。
              </span>
            </div>
          ) : (
            <div className="banner info">
              <Info size={15} aria-hidden="true" />
              <span>
                工作台只读：正文编辑器尚未接入；生成执行在「③ 生成配置与执行」完成，
                此处展示矩阵底稿、缺口与最近一次生成埋点。
              </span>
            </div>
          )}

          <div className="wb bw-mt">
            <aside className="card bw-outline">
              <div className="card-h">
                <h3>文档结构</h3>
                <span className="r">
                  <Badge tone="gray">{sections.length} 节</Badge>
                </span>
              </div>
              <div className="card-b">
                <button
                  type="button"
                  className={`outline-item ${activeSection === "all" ? "on" : ""}`}
                  onClick={() => setActiveSection("all")}
                >
                  <span className="oi-t">全部要求</span>
                  <span className="cnt">{rows.length}</span>
                </button>
                {sections.map((section) => {
                  const blocked = section.rows.filter(
                    (row) => row.status === "blocked",
                  ).length;
                  return (
                    <button
                      key={section.key}
                      type="button"
                      className={`outline-item ${activeSection === section.key ? "on" : ""}`}
                      onClick={() => setActiveSection(section.key)}
                    >
                      <span className="oi-t">{section.name}</span>
                      {blocked > 0 ? (
                        <span
                          className="oi-blocked"
                          title={`${blocked} 条阻断`}
                        >
                          {blocked}
                        </span>
                      ) : null}
                      <span className="cnt">{section.rows.length}</span>
                    </button>
                  );
                })}
                {sections.length === 0 ? (
                  <p className="bw-muted bw-pad-sm">
                    还没有目标章节。响应矩阵未填写 target_section 时按来源分组。
                  </p>
                ) : null}
              </div>
              <div className="bw-outline-foot">
                {m ? (
                  <>
                    <span>
                      最近生成 <b>{formatDate(metrics.data?.run_at ?? null)}</b>
                    </span>
                    <Badge tone={m.d0_count === 0 ? "ok" : "warn"}>
                      D0 {m.d0_count} · 通过率 {formatPercent(m.assertion_pass_rate)}
                    </Badge>
                  </>
                ) : (
                  <>
                    <span>正文</span>
                    <Badge tone="gray">未生成</Badge>
                  </>
                )}
              </div>
            </aside>

            <section className="card bw-doc">
              <div className="card-h">
                <h3>
                  {activeSection === "all"
                    ? "响应矩阵底稿"
                    : sections.find((section) => section.key === activeSection)
                        ?.name}
                </h3>
                <span className="r">
                  <span className="bw-doc-badge">
                    <Lock size={12} aria-hidden="true" />
                    只读
                  </span>
                  <Badge tone={summary.blocked > 0 ? "bad" : "ok"} dot>
                    {summary.blocked > 0
                      ? `${summary.blocked} 项阻断`
                      : "矩阵无阻断"}
                  </Badge>
                </span>
              </div>
              <div className="ed-toolbar">
                <button type="button" disabled title="正文生成接入后开放">
                  <Undo2 size={14} aria-hidden="true" />
                </button>
                <button type="button" disabled title="正文生成接入后开放">
                  <Redo2 size={14} aria-hidden="true" />
                </button>
                <span className="sep" />
                <button type="button" disabled title="正文生成接入后开放">
                  保存
                </button>
                <button type="button" disabled title="重审接口尚未接入">
                  <RefreshCw size={14} aria-hidden="true" />
                  重审受影响断言
                </button>
                <span className="ed-spacer" />
                <button
                  type="button"
                  disabled
                  title="AI 建议需要生成正文与断言快照"
                >
                  <Sparkles size={14} aria-hidden="true" />
                  查看 AI 建议
                </button>
              </div>
              <div className="doc-body">
                <div className="bw-empty-doc">
                  <span className="bw-empty-ic">
                    <FileText size={22} aria-hidden="true" />
                  </span>
                  <div>
                    <h3>正文尚未生成</h3>
                    <p>
                      生成执行管线接入后，这里会按章节渲染可编辑正文、条款引用与素材出处。
                      当前不使用演示段落填充。
                    </p>
                    <div className="bw-empty-actions">
                      <Link
                        href={
                          taskId
                            ? writeTaskHref("generate", taskId)
                            : "/bid-write/generate"
                        }
                        className="btn pri btn-sm"
                      >
                        去生成配置
                      </Link>
                      <Link
                        href={
                          taskId
                            ? writeTaskHref("intake", taskId)
                            : "/bid-write/intake"
                        }
                        className="btn btn-sm"
                      >
                        回到解析确认
                      </Link>
                    </div>
                  </div>
                </div>

                <div className="bw-doc-sub">
                  <b>当前章节的响应矩阵</b>
                  <span>{visibleRows.length} 条要求</span>
                </div>
                {visibleRows.length === 0 ? (
                  <p className="bw-muted">当前章节没有矩阵行。</p>
                ) : (
                  <div className="tbl-wrap">
                    <table className="tbl dense">
                      <thead>
                        <tr>
                          <th>条款</th>
                          <th>要求摘录</th>
                          <th>策略</th>
                          <th>状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleRows.map((row) => (
                          <tr key={row.clause_id}>
                            <td className="mono bw-nowrap">{row.clause_id}</td>
                            <td>
                              <span
                                className="excerpt ellipsis"
                                title={row.requirement}
                              >
                                {row.requirement
                                  ? row.requirement
                                  : "（空要求）"}
                              </span>
                            </td>
                            <td className="bw-nowrap">
                              {matrixStrategyLabel(row.strategy)}
                              {row.star ? (
                                <span className="star"> ★</span>
                              ) : null}
                            </td>
                            <td>
                              <Badge tone={matrixStatusTone(row)} dot>
                                {matrixStatusLabel(row.status)}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>

            <aside className="bw-side">
              <div className="card">
                <div className="card-h">
                  <h3>素材缺口</h3>
                  <span className="r">
                    <Badge tone={noMaterial.length > 0 ? "bad" : "ok"}>
                      {noMaterial.length} / {gapItems.length}
                    </Badge>
                  </span>
                </div>
                <div className="card-b">
                  {gaps.isLoading ? (
                    <LoadingBlock label="加载素材缺口…" />
                  ) : noMaterial.length === 0 ? (
                    <p className="bw-muted">没有待补素材。</p>
                  ) : (
                    <ul className="bw-side-list">
                      {noMaterial.slice(0, 8).map((item) => (
                        <li key={item.clause_id}>
                          <span className="mono">{item.clause_id}</span>
                          <span title={item.requirement}>
                            {item.requirement}
                          </span>
                          {item.star ? <span className="star">★</span> : null}
                        </li>
                      ))}
                    </ul>
                  )}
                  {noMaterial.length > 8 ? (
                    <p className="bw-muted bw-mt-sm">
                      另有 {noMaterial.length - 8} 条缺口…
                    </p>
                  ) : null}
                  <Link
                    href={
                      taskId
                        ? writeTaskHref("materials", taskId)
                        : "/bid-write/materials"
                    }
                    className="btn btn-sm soft bw-full"
                  >
                    查看全部缺口
                  </Link>
                </div>
              </div>

              <div className="card bw-mt">
                <div className="card-h">
                  <h3>预审查</h3>
                  <span className="r">
                    {assertions ? (
                      <Badge tone={assertions.blocked ? "bad" : "ok"} dot>
                        {assertions.blocked ? "阻断" : "通过"}
                      </Badge>
                    ) : (
                      <Badge tone="gray">未执行</Badge>
                    )}
                  </span>
                </div>
                <div className="card-b">
                  {assertions ? (
                    <>
                      <div className="bw-inline-facts bw-facts-col">
                        <span>
                          执行时间 <b>{formatDate(assertions.run_at)}</b>
                        </span>
                        <span>
                          待补 <b>{assertions.pending.length}</b> · 跳过{" "}
                          <b>{assertions.skipped.length}</b>
                        </span>
                      </div>
                      {assertions.pending.slice(0, 4).map((item) => (
                        <div className="bw-mini-item" key={item.assertion_id}>
                          <span className="mono">{item.assertion_id}</span>
                          <span>{item.message}</span>
                        </div>
                      ))}
                      {assertions.pending.length > 4 ? (
                        <p className="bw-muted">
                          另有 {assertions.pending.length - 4} 条待补…
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <p className="bw-muted">
                      尚未执行断言。导出门禁在执行后才会给出明确判定。
                    </p>
                  )}
                  <Link
                    href={
                      taskId
                        ? writeTaskHref("review", taskId)
                        : "/bid-write/review"
                    }
                    className="btn btn-sm soft bw-full"
                  >
                    查看预审查
                  </Link>
                </div>
              </div>
            </aside>
          </div>

          <div className="statusbar">
            <span className="dot-ok" />
            <span>
              矩阵 {summary.total} 行 · 已确认 {summary.confirmed} · 阻断{" "}
              {summary.blocked}
            </span>
            <span className="sep" />
            <span>素材缺口 {noMaterial.length}</span>
            <span className="sep" />
            <span>
              预审查{" "}
              {assertions ? (assertions.blocked ? "阻断" : "可导出") : "未执行"}
            </span>
            {m ? (
              <>
                <span className="sep" />
                <span>
                  人工编辑占比 {formatPercent(m.manual_edit_ratio)} · 耗时{" "}
                  {(m.latency_ms / 1000).toFixed(1)}s
                </span>
              </>
            ) : null}
            <span className="grow" />
            {taskId ? (
              <Link
                href={writeTaskHref("export", taskId)}
                className="bw-inline-link"
              >
                去导出
                <ChevronRight size={12} aria-hidden="true" />
              </Link>
            ) : null}
          </div>
        </>
      )}
    </>
  );
}
