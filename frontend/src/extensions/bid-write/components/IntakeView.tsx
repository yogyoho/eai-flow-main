"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCheck,
  ChevronDown,
  Download,
  FileText,
  Info,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  MetricCell,
  MetricStrip,
  Overlay,
  PageHead,
  ProgressBar,
} from "@/extensions/bid-write/components/primitives";
import {
  canLeaveIntake,
  downloadCsv,
  formatPercent,
  matrixStatusLabel,
  matrixStatusTone,
  matrixStrategyLabel,
  matrixSummary,
  sourcePathLabel,
  taskStatusView,
  TASK_STATUS_LABELS,
} from "@/extensions/bid-write/helpers";
import {
  useBidWriteMatrix,
  usePatchBidWriteMatrixRow,
  useSelectedWriteTask,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";
import type { MatrixRowOut } from "@/extensions/bid-write/types";

interface NoteDialogState {
  row: MatrixRowOut;
  note: string;
  mode: "negative" | "confirm";
}

export function IntakeView() {
  const router = useRouter();
  const { taskId, task, isLoading, error } = useSelectedWriteTask();
  const matrix = useBidWriteMatrix(taskId);
  const refetchMatrix = matrix.refetch;
  const patch = usePatchBidWriteMatrixRow(taskId);
  const [groupFilter, setGroupFilter] = useState<string>("all");
  const [selectedClause, setSelectedClause] = useState<string | null>(null);
  const [dialog, setDialog] = useState<NoteDialogState | null>(null);
  const [bulkPending, setBulkPending] = useState(false);
  const wasExtracting = useRef(false);

  useEffect(() => {
    if (!task) return;
    if (["created", "parsing", "extracting"].includes(task.status)) {
      wasExtracting.current = true;
      return;
    }
    if (task.status === "matrix_ready" && wasExtracting.current) {
      wasExtracting.current = false;
      void refetchMatrix();
    }
  }, [task, refetchMatrix]);

  const rows = useMemo(() => matrix.data?.items ?? [], [matrix.data?.items]);
  const summary = useMemo(() => matrixSummary(rows), [rows]);
  const groups = useMemo(() => {
    const map = new Map<string, MatrixRowOut[]>();
    for (const row of rows) {
      const list = map.get(row.source_path) ?? [];
      list.push(row);
      map.set(row.source_path, list);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [rows]);

  const visibleRows = useMemo(
    () =>
      groupFilter === "all"
        ? rows
        : rows.filter((row) => row.source_path === groupFilter),
    [groupFilter, rows],
  );

  const averageConfidence = useMemo(() => {
    const values = rows
      .map((row) => row.conf)
      .filter((value): value is number => typeof value === "number");
    if (values.length === 0) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }, [rows]);

  const applyPatch = async (
    row: MatrixRowOut,
    next: {
      strategy?: string;
      status?: string;
      note?: string;
    },
    success: string,
  ) => {
    try {
      await patch.mutateAsync({
        clauseId: row.clause_id,
        patch: next,
      });
      toast.success(success);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新响应矩阵失败");
    }
  };

  const onStrategyChange = (row: MatrixRowOut, next: string) => {
    if (next === row.strategy) return;
    if (row.star && next === "negative" && !row.note.trim()) {
      setDialog({ row, note: "", mode: "negative" });
      return;
    }
    void applyPatch(
      row,
      { strategy: next },
      `已更新 ${row.clause_id} 的响应策略`,
    );
  };

  const onConfirm = (row: MatrixRowOut) => {
    if (row.status === "confirmed") {
      void applyPatch(
        row,
        { status: "draft" },
        `已撤回 ${row.clause_id} 的确认`,
      );
      return;
    }
    if (row.status === "blocked") {
      setDialog({ row, note: "", mode: "confirm" });
      return;
    }
    void applyPatch(row, { status: "confirmed" }, `${row.clause_id} 已确认`);
  };

  const submitDialog = async () => {
    if (!dialog) return;
    const note = dialog.note.trim();
    if (!note) {
      toast.error(
        dialog.mode === "negative"
          ? "请填写偏离理由与替代方案"
          : "请填写确认依据",
      );
      return;
    }
    try {
      await patch.mutateAsync({
        clauseId: dialog.row.clause_id,
        patch:
          dialog.mode === "negative"
            ? { strategy: "negative", note }
            : { status: "confirmed", note },
      });
      toast.success(
        dialog.mode === "negative"
          ? "负偏离原因已记录"
          : "低置信行已确认并解阻",
      );
      setDialog(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "提交失败");
    }
  };

  const bulkConfirm = async () => {
    const eligible = rows.filter(
      (row) => row.status === "draft" && row.strategy !== "pending",
    );
    if (eligible.length === 0) {
      toast.error("没有已选择响应策略的草稿行可批量确认");
      return;
    }
    setBulkPending(true);
    try {
      for (const row of eligible) {
        await patch.mutateAsync({
          clauseId: row.clause_id,
          patch: { status: "confirmed" },
        });
      }
      toast.success(`已确认 ${eligible.length} 条已核对行`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "批量确认中断");
    } finally {
      setBulkPending(false);
    }
  };

  const exportUnconfirmed = () => {
    const pending = rows.filter((row) => row.status !== "confirmed");
    if (pending.length === 0) {
      toast.error("没有未确认行可导出");
      return;
    }
    downloadCsv(
      `响应矩阵-未确认-${new Date().toISOString().slice(0, 10)}.csv`,
      ["条款号", "来源", "要求", "★", "矩阵状态", "响应策略", "置信度", "备注"],
      pending.map((row) => [
        row.clause_id,
        sourcePathLabel(row.source_path),
        row.requirement,
        row.star ? "★" : "",
        matrixStatusLabel(row.status),
        matrixStrategyLabel(row.strategy),
        formatPercent(row.conf),
        row.note,
      ]),
    );
    toast.success(`已导出 ${pending.length} 条未确认行`);
  };

  const enterMaterials = () => {
    if (!canLeaveIntake(summary)) {
      toast.error(
        `仍有 ${summary.blocked} 条低置信行未确认，确认后才能进入素材核对`,
      );
      return;
    }
    if (taskId) router.push(writeTaskHref("materials", taskId));
  };

  return (
    <>
      <PageHead
        icon={FileText}
        title="① 招标文件解析确认"
        subtitle="tender.* 抽取结果 → 可确认、可纠错的响应矩阵"
        actions={
          <>
            <button
              type="button"
              className="btn btn-sm"
              onClick={exportUnconfirmed}
              disabled={rows.length === 0}
            >
              <Download size={13} aria-hidden="true" />
              导出未确认清单
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void bulkConfirm()}
              disabled={bulkPending || rows.length === 0}
            >
              <CheckCheck size={13} aria-hidden="true" />
              {bulkPending ? "确认中…" : "批量确认已核对项"}
            </button>
            <button
              type="button"
              className="btn pri btn-sm"
              onClick={enterMaterials}
              disabled={rows.length === 0}
              title={
                canLeaveIntake(summary)
                  ? "进入素材核对"
                  : `仍有 ${summary.blocked} 条低置信行未确认`
              }
            >
              进入素材核对
              <ArrowRight size={13} aria-hidden="true" />
            </button>
          </>
        }
      />

      {isLoading ? (
        <LoadingBlock label="正在加载任务…" />
      ) : error ? (
        <ErrorBlock error={error} />
      ) : !task ? (
        <EmptyState
          icon={FileText}
          title="还没有写作项目"
          description="先创建项目并上传招标文件，解析完成后会在这里生成响应矩阵。"
          action={
            <Link href="/bid-write" className="btn pri">
              去项目列表
            </Link>
          }
        />
      ) : task.status !== "matrix_ready" ? (
        <TaskProgress task={task} matrix={matrix} />
      ) : (
        <>
          <MetricStrip>
            <MetricCell
              label="矩阵行"
              value={summary.total}
              suffix={`★ ${summary.star}`}
              accent
            />
            <MetricCell
              label="平均置信"
              value={formatPercent(averageConfidence)}
              tone={
                averageConfidence != null && averageConfidence < 0.6
                  ? "warn"
                  : "ok"
              }
            />
            <MetricCell
              label="低置信待确认"
              value={summary.blocked}
              tone={summary.blocked > 0 ? "err" : "ok"}
            />
            <MetricCell label="已确认" value={summary.confirmed} tone="ok" />
            <MetricCell
              label="响应策略待定"
              value={summary.strategyPending}
              tone={summary.strategyPending > 0 ? "warn" : "ok"}
            />
          </MetricStrip>

          <div className="split bw-intake-split">
            <div className="card">
              <div className="card-h">
                <h3>条款树</h3>
                <span className="r">
                  <Badge tone="gray">det / sem</Badge>
                </span>
              </div>
              <div className="card-b tree bw-tree">
                <button
                  type="button"
                  className={`node ${groupFilter === "all" ? "on" : ""}`}
                  onClick={() => {
                    setGroupFilter("all");
                    setSelectedClause(null);
                  }}
                >
                  <ChevronDown size={12} aria-hidden="true" />
                  <b>全部商务要求</b>
                  <span className="cnt">{rows.length}</span>
                </button>
                {groups.map(([path, groupRows]) => {
                  const blocked = groupRows.filter(
                    (row) => row.status === "blocked",
                  ).length;
                  return (
                    <div className="bw-tree-group" key={path}>
                      <button
                        type="button"
                        className={`node ${groupFilter === path ? "on" : ""}`}
                        onClick={() => {
                          setGroupFilter(path);
                          setSelectedClause(null);
                        }}
                      >
                        <ChevronDown size={12} aria-hidden="true" />
                        <b>{sourcePathLabel(path)}</b>
                        <span className="cnt">{groupRows.length}</span>
                        {blocked > 0 ? (
                          <span className="bw-tree-alert">{blocked}</span>
                        ) : null}
                      </button>
                      {groupRows.map((row) => (
                        <button
                          type="button"
                          key={row.clause_id}
                          className={`node leaf ${selectedClause === row.clause_id ? "on" : ""}`}
                          onClick={() => {
                            setGroupFilter(path);
                            setSelectedClause(row.clause_id);
                            document
                              .getElementById(`matrix-${row.clause_id}`)
                              ?.scrollIntoView({
                                block: "center",
                                behavior: "smooth",
                              });
                          }}
                          title={row.requirement}
                        >
                          <span
                            className={`dot ${
                              row.status === "blocked"
                                ? "bad"
                                : row.status === "confirmed"
                                  ? "ok"
                                  : "gray"
                            }`}
                            aria-hidden="true"
                          />
                          <span className="bw-tree-clause mono">
                            {row.clause_id}
                          </span>
                          <span className="bw-tree-text">
                            {row.requirement}
                          </span>
                          {row.star ? <span className="star">★</span> : null}
                        </button>
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="card">
              <div className="card-h">
                <h3>响应矩阵</h3>
                <span className="r">
                  <Badge tone="gray">
                    {groupFilter === "all"
                      ? `全部 ${rows.length}`
                      : `${sourcePathLabel(groupFilter)} ${visibleRows.length}`}
                  </Badge>
                </span>
              </div>
              {matrix.isLoading ? (
                <div className="card-b">
                  <LoadingBlock label="正在加载响应矩阵…" />
                </div>
              ) : matrix.error ? (
                <div className="card-b">
                  <ErrorBlock
                    error={matrix.error}
                    onRetry={() => void matrix.refetch()}
                  />
                </div>
              ) : visibleRows.length === 0 ? (
                <div className="card-b">
                  <EmptyState
                    icon={FileText}
                    title="当前分组没有矩阵行"
                    description="抽取结果未产出该来源的要求行。缺失行代表下游可见缺口，不会伪造行。"
                  />
                </div>
              ) : (
                <div className="tbl-wrap">
                  <table className="tbl bw-matrix-table">
                    <thead>
                      <tr>
                        <th>条款号</th>
                        <th>要求摘录</th>
                        <th>★</th>
                        <th>状态</th>
                        <th>响应策略</th>
                        <th>置信</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRows.map((row) => (
                        <tr
                          key={row.clause_id}
                          id={`matrix-${row.clause_id}`}
                          className={
                            selectedClause === row.clause_id ? "on" : undefined
                          }
                          onClick={() => setSelectedClause(row.clause_id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              setSelectedClause(row.clause_id);
                            }
                          }}
                          tabIndex={0}
                        >
                          <td className="mono">{row.clause_id}</td>
                          <td>
                            <span
                              className="excerpt ellipsis"
                              title={row.requirement}
                            >
                              {row.requirement || "（空要求）"}
                            </span>
                            {row.note ? (
                              <div className="bw-row-note" title={row.note}>
                                备注：{row.note}
                              </div>
                            ) : null}
                          </td>
                          <td>
                            {row.star ? <span className="star">★</span> : ""}
                          </td>
                          <td>
                            <Badge
                              tone={matrixStatusTone(row)}
                              dot
                              className="bw-nowrap"
                            >
                              {matrixStatusLabel(row.status)}
                            </Badge>
                            {row.verified ? (
                              <div className="bw-subline">引文已核验</div>
                            ) : null}
                          </td>
                          <td>
                            <select
                              className="select bw-select"
                              value={row.strategy}
                              disabled={patch.isPending}
                              onChange={(event) =>
                                onStrategyChange(row, event.target.value)
                              }
                              aria-label={`${row.clause_id} 响应策略`}
                            >
                              {(
                                matrix.data?.vocab.strategies ?? [
                                  "pending",
                                  "full",
                                  "positive",
                                  "negative",
                                ]
                              ).map((strategy) => (
                                <option key={strategy} value={strategy}>
                                  {matrixStrategyLabel(strategy)}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="num">{formatPercent(row.conf)}</td>
                          <td>
                            <button
                              type="button"
                              className={`btn btn-sm ${
                                row.status === "confirmed" ? "soft" : "pri"
                              }`}
                              disabled={patch.isPending}
                              onClick={(event) => {
                                event.stopPropagation();
                                onConfirm(row);
                              }}
                            >
                              {row.status === "confirmed" ? "撤回" : "确认"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="card-b">
                {summary.blocked > 0 ? (
                  <div className="banner bad">
                    <AlertTriangle size={15} aria-hidden="true" />
                    <span>
                      <b>{summary.blocked} 条低置信行待确认</b>
                      ：未确认前禁止进入生成；确认时必须填写确认依据。
                    </span>
                  </div>
                ) : summary.strategyPending > 0 ? (
                  <div className="banner warn">
                    <Info size={15} aria-hidden="true" />
                    <span>
                      还有 <b>{summary.strategyPending}</b> 条响应策略待定
                      。策略不影响进入素材核对，但会影响后续生成与断言。
                    </span>
                  </div>
                ) : (
                  <div className="banner ok">
                    <CheckCheck size={15} aria-hidden="true" />
                    <span>矩阵已全部确认，可进入素材核对。</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      <Overlay
        open={dialog !== null}
        title={dialog?.mode === "negative" ? "★ 负偏离确认" : "低置信行确认"}
        subtitle={dialog?.row.clause_id}
        onClose={() => setDialog(null)}
        footer={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => setDialog(null)}
            >
              取消
            </button>
            <button
              type="button"
              className="btn pri"
              onClick={() => void submitDialog()}
              disabled={patch.isPending}
            >
              {dialog?.mode === "negative" ? "记录负偏离" : "确认并解阻"}
            </button>
          </>
        }
      >
        {dialog ? (
          <>
            <div className="banner bad">
              <AlertTriangle size={15} aria-hidden="true" />
              <span>
                {dialog.mode === "negative" ? (
                  <>
                    <b>★ 为否决条款：</b>
                    负偏离可能导致废标，必须记录偏离理由与替代方案。
                  </>
                ) : (
                  <>
                    <b>低置信抽取：</b>
                    确认即解阻，但必须记录人工核对依据，避免把裁决推给下游。
                  </>
                )}
              </span>
            </div>
            <div className="bw-requirement">
              <span className="k">要求摘录</span>
              <p>{dialog.row.requirement}</p>
            </div>
            <label className="field bw-mt-sm">
              <span>
                {dialog.mode === "negative" ? "偏离理由与替代方案" : "确认依据"}{" "}
                <b className="req">*</b>
              </span>
              <textarea
                className="textarea"
                rows={4}
                value={dialog.note}
                onChange={(event) =>
                  setDialog({ ...dialog, note: event.target.value })
                }
                placeholder={
                  dialog.mode === "negative"
                    ? "说明偏离原因，并给出弥补措施（例如：质保 24 个月，维护期 12 个月，质保期外按备件价供应）"
                    : "例如：已对照招标文件 p.18 原文，确认质保期为 24 个月"
                }
                autoFocus
              />
            </label>
          </>
        ) : null}
      </Overlay>
    </>
  );
}

function TaskProgress({
  task,
  matrix,
}: {
  task: NonNullable<ReturnType<typeof useSelectedWriteTask>["task"]>;
  matrix: ReturnType<typeof useBidWriteMatrix>;
}) {
  const view = taskStatusView(task);
  return (
    <div className="card">
      <div className="card-h">
        <h3>{TASK_STATUS_LABELS[task.status] ?? task.status}</h3>
        <span className="r">
          {task.status === "failed" ? (
            <Badge tone="bad" dot>
              解析失败
            </Badge>
          ) : (
            <Badge tone="info" dot>
              后台处理中
            </Badge>
          )}
        </span>
      </div>
      <div className="card-b">
        {task.status === "failed" ? (
          <div className="banner bad">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>
              <b>任务失败：</b>
              {task.error ?? "解析或抽取失败，未生成响应矩阵。"}
            </span>
          </div>
        ) : (
          <>
            <div className="bw-progress-row">
              <ProgressBar value={view.pct} />
              <span className="num">{view.pct}%</span>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void matrix.refetch()}
              >
                <RefreshCw size={13} aria-hidden="true" />
                刷新
              </button>
            </div>
            <p className="bw-muted">
              {view.message || "正在处理招标文件…"} · 页面会自动轮询任务状态。
            </p>
          </>
        )}
        <div className="banner info bw-mt">
          <Info size={15} aria-hidden="true" />
          <span>
            解析链：招标文件解析 → tender.* 商务要素抽取 →
            响应矩阵装配。失败时保留原因，不伪造矩阵。
          </span>
        </div>
      </div>
    </div>
  );
}
