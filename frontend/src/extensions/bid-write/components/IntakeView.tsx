"use client";

import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCheck,
  Crosshair,
  Download,
  FileText,
  Info,
  RefreshCw,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DocLocateBody } from "@/extensions/bid-review/components/DocLocateModal";
import {
  fetchWriteDocContent,
  writeDocAssetUrl,
  type LocateTarget,
} from "@/extensions/bid-write/api";
import { HelpDrawer } from "@/extensions/bid-write/components/HelpDrawer";
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
  matrixClauseLabel,
  matrixRequirementLabel,
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
  /** 刻面筛选:来源单选 + 状态多选 + 必答开关,三者 AND 叠加(方案 A)。 */
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [statusFilters, setStatusFilters] = useState<Set<string>>(
    () => new Set(),
  );
  const [starOnly, setStarOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const [selectedClause, setSelectedClause] = useState<string | null>(null);
  const [dialog, setDialog] = useState<NoteDialogState | null>(null);
  const [locate, setLocate] = useState<LocateTarget | null>(null);
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
  // 来源刻面:标签按中文自然序(数字按值比较),修复「附件 2 排在附件 16 后」的字符串失序。
  const groups = useMemo(() => {
    const map = new Map<string, MatrixRowOut[]>();
    for (const row of rows) {
      const list = map.get(row.source_path) ?? [];
      list.push(row);
      map.set(row.source_path, list);
    }
    const collator = new Intl.Collator("zh-Hans-CN", {
      numeric: true,
      sensitivity: "base",
    });
    return [...map.entries()].sort(([a], [b]) =>
      collator.compare(sourcePathLabel(a), sourcePathLabel(b)),
    );
  }, [rows]);

  const draftCount = useMemo(
    () => rows.filter((row) => row.status === "draft").length,
    [rows],
  );
  const statusCounts = useMemo(
    () => ({
      blocked: summary.blocked,
      draft: draftCount,
      confirmed: summary.confirmed,
    }),
    [summary.blocked, summary.confirmed, draftCount],
  );
  const filtersActive =
    sourceFilter !== "all" || statusFilters.size > 0 || starOnly;
  const pctOf = (count: number) =>
    `${rows.length ? Math.round((count / rows.length) * 100) : 0}%`;

  const toggleStatusFilter = (status: string) => {
    setStatusFilters((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  };

  const clearFilters = () => {
    setSourceFilter("all");
    setStatusFilters(new Set());
    setStarOnly(false);
  };

  const visibleRows = useMemo(
    () =>
      rows.filter((row) => {
        if (sourceFilter !== "all" && row.source_path !== sourceFilter) {
          return false;
        }
        if (statusFilters.size > 0 && !statusFilters.has(row.status)) {
          return false;
        }
        if (starOnly && !row.star) return false;
        return true;
      }),
    [sourceFilter, statusFilters, starOnly, rows],
  );

  /** 搜索框承担「定位具体条款」:命中后选中矩阵行并滚动(左面板不再做逐条导航)。 */
  const locateBySearch = () => {
    const query = search.trim().toLowerCase();
    if (!query) return;
    const matches = (row: MatrixRowOut) =>
      matrixClauseLabel(row.clause_id).toLowerCase().includes(query) ||
      matrixRequirementLabel(row.requirement).toLowerCase().includes(query);
    const hit = visibleRows.find(matches) ?? rows.find(matches);
    if (!hit) {
      toast.error(`没有匹配「${search.trim()}」的条款`);
      return;
    }
    setSelectedClause(hit.clause_id);
    document
      .getElementById(`matrix-${hit.clause_id}`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

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
      `已更新 ${matrixClauseLabel(row.clause_id)} 的响应策略`,
    );
  };

  const onConfirm = (row: MatrixRowOut) => {
    if (row.status === "confirmed") {
      void applyPatch(
        row,
        { status: "draft" },
        `已撤回 ${matrixClauseLabel(row.clause_id)} 的确认`,
      );
      return;
    }
    if (row.status === "blocked") {
      setDialog({ row, note: "", mode: "confirm" });
      return;
    }
    void applyPatch(
      row,
      { status: "confirmed" },
      `${matrixClauseLabel(row.clause_id)} 已确认`,
    );
  };

  /** 行 → 来源引文溯源目标(provenance 按 source_path 共享;缺引文=无法定位)。 */
  const provenanceOf = (sourcePath: string): LocateTarget | null => {
    const entry = task?.engine_meta?.provenance?.[sourcePath];
    if (!entry?.doc_id || !entry.quote) return null;
    return {
      docId: entry.doc_id,
      quote: entry.quote,
      page: typeof entry.page === "number" ? entry.page : null,
    };
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
          : "待核对记录已全部确认",
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
        matrixClauseLabel(row.clause_id),
        sourcePathLabel(row.source_path),
        matrixRequirementLabel(row.requirement),
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
        `仍有 ${summary.blocked} 条记录待人工核对，核对确认后才能进入素材核对`,
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
        subtitle="招标文件抽取结果 → 可确认、可纠错的商务响应矩阵"
        actions={
          <>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setHelpOpen(true)}
            >
              <Info size={13} aria-hidden="true" />
              本页说明
            </button>
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
                  : `仍有 ${summary.blocked} 条记录待人工核对`
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
              label="待人工核对"
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
                <h3>筛选 · 来源与状态</h3>
                <span className="r">
                  <Badge tone="gray">点选即筛选</Badge>
                </span>
              </div>
              <div className="card-b bw-filter">
                <form
                  className="bw-fx-search"
                  onSubmit={(event) => {
                    event.preventDefault();
                    locateBySearch();
                  }}
                >
                  <Search size={13} aria-hidden="true" />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") setSearch("");
                    }}
                    placeholder="搜索条款定位，如「附件 1」"
                    aria-label="搜索条款定位"
                  />
                  <button
                    type="submit"
                    className="bw-fx-search-go"
                    disabled={!search.trim()}
                  >
                    定位
                  </button>
                </form>

                <div className="bw-fx-progress">
                  <div className="bw-fx-progress-top">
                    <b>核对进度</b>
                    <span className="bw-fx-frac">
                      {summary.confirmed}
                      <em>/{rows.length}</em>
                    </span>
                  </div>
                  <div className="bw-fx-seg" aria-hidden="true">
                    <i
                      className="ok"
                      style={{ width: pctOf(summary.confirmed) }}
                    />
                    <i className="draft" style={{ width: pctOf(draftCount) }} />
                    <i
                      className="bad"
                      style={{ width: pctOf(summary.blocked) }}
                    />
                  </div>
                  <div className="bw-fx-progress-legend">
                    <span>
                      <i className="ok" aria-hidden="true" />
                      已确认 {summary.confirmed}
                    </span>
                    <span>
                      <i className="draft" aria-hidden="true" />
                      草稿 {draftCount}
                    </span>
                    <span>
                      <i className="bad" aria-hidden="true" />
                      待核对 {summary.blocked}
                    </span>
                  </div>
                </div>

                {filtersActive ? (
                  <div className="bw-fx-active" aria-label="当前筛选条件">
                    {sourceFilter !== "all" ? (
                      <button
                        type="button"
                        className="bw-fx-chip"
                        onClick={() => setSourceFilter("all")}
                      >
                        来源：{sourcePathLabel(sourceFilter)}
                        <span className="x" aria-hidden="true">
                          ×
                        </span>
                      </button>
                    ) : null}
                    {[...statusFilters].map((status) => (
                      <button
                        key={status}
                        type="button"
                        className="bw-fx-chip"
                        onClick={() => toggleStatusFilter(status)}
                      >
                        状态：{matrixStatusLabel(status)}
                        <span className="x" aria-hidden="true">
                          ×
                        </span>
                      </button>
                    ))}
                    {starOnly ? (
                      <button
                        type="button"
                        className="bw-fx-chip"
                        onClick={() => setStarOnly(false)}
                      >
                        ★ 仅看必答
                        <span className="x" aria-hidden="true">
                          ×
                        </span>
                      </button>
                    ) : null}
                    <span className="bw-fx-count">
                      显示 {visibleRows.length} / {rows.length}
                    </span>
                  </div>
                ) : null}

                <div className="bw-fx-title">
                  来源
                  <span className="bw-fx-multi">单选</span>
                </div>
                <div
                  className="bw-fx-list"
                  role="radiogroup"
                  aria-label="按来源筛选"
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={sourceFilter === "all"}
                    className={`bw-fx-row ${
                      sourceFilter === "all" ? "on" : ""
                    }`}
                    onClick={() => {
                      setSourceFilter("all");
                      setSelectedClause(null);
                    }}
                  >
                    <span className="bw-fx-radio" aria-hidden="true" />
                    <span className="bw-fx-name">全部来源</span>
                    <span className="bw-fx-verb">仅看</span>
                    <span className="cnt">{rows.length}</span>
                  </button>
                  {groups.map(([path, groupRows]) => {
                    const blocked = groupRows.filter(
                      (row) => row.status === "blocked",
                    ).length;
                    return (
                      <button
                        type="button"
                        key={path}
                        role="radio"
                        aria-checked={sourceFilter === path}
                        className={`bw-fx-row ${
                          sourceFilter === path ? "on" : ""
                        }`}
                        onClick={() => {
                          setSourceFilter(path);
                          setSelectedClause(null);
                        }}
                      >
                        <span className="bw-fx-radio" aria-hidden="true" />
                        <span className="bw-fx-name">
                          {sourcePathLabel(path)}
                        </span>
                        <span className="bw-fx-verb">仅看</span>
                        <span className="cnt">{groupRows.length}</span>
                        {blocked > 0 ? (
                          <span className="bw-tree-alert">{blocked}</span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>

                <div className="bw-fx-title">
                  状态
                  <span className="bw-fx-multi">可多选</span>
                </div>
                <div className="bw-fx-list" aria-label="按状态筛选">
                  {(["blocked", "draft", "confirmed"] as const).map(
                    (status) => {
                      const on = statusFilters.has(status);
                      return (
                        <button
                          type="button"
                          key={status}
                          role="checkbox"
                          aria-checked={on}
                          className={`bw-fx-row ${on ? "on" : ""}`}
                          onClick={() => toggleStatusFilter(status)}
                        >
                          <span
                            className={`bw-fx-check ${on ? "on" : ""}`}
                            aria-hidden="true"
                          >
                            {on ? <Check size={10} /> : null}
                          </span>
                          <span className="bw-fx-name">
                            {matrixStatusLabel(status)}
                          </span>
                          <span className="bw-fx-verb">筛选</span>
                          <span className="cnt">{statusCounts[status]}</span>
                        </button>
                      );
                    },
                  )}
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={starOnly}
                    className={`bw-fx-row ${starOnly ? "on" : ""}`}
                    onClick={() => setStarOnly((prev) => !prev)}
                  >
                    <span
                      className={`bw-fx-check ${starOnly ? "on" : ""}`}
                      aria-hidden="true"
                    >
                      {starOnly ? <Check size={10} /> : null}
                    </span>
                    <span className="bw-fx-name">★ 仅看必答条款</span>
                    <span className="bw-fx-verb">筛选</span>
                    <span className="cnt">{summary.star}</span>
                  </button>
                </div>

                <div className="bw-fx-foot">
                  <span className="bw-fx-hint">点击选项筛选右侧矩阵</span>
                  <button
                    type="button"
                    className="btn btn-sm bw-fx-clear"
                    onClick={clearFilters}
                    disabled={!filtersActive}
                  >
                    清除全部筛选
                  </button>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-h">
                <h3>响应矩阵</h3>
                <span className="r">
                  {filtersActive ? (
                    <button
                      type="button"
                      className="btn btn-sm bw-fx-mirror"
                      onClick={clearFilters}
                      title="清除筛选，显示全部行"
                    >
                      筛选 {visibleRows.length}/{rows.length} · 清除
                    </button>
                  ) : (
                    <Badge tone="gray">全部 {rows.length}</Badge>
                  )}
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
                    title="当前筛选没有匹配的矩阵行"
                    description={
                      filtersActive
                        ? "调整或清除筛选条件后再试；缺失行代表下游可见缺口，不会伪造行。"
                        : "抽取结果未产出该来源的要求行。缺失行代表下游可见缺口，不会伪造行。"
                    }
                    action={
                      filtersActive ? (
                        <button
                          type="button"
                          className="btn"
                          onClick={clearFilters}
                        >
                          清除筛选
                        </button>
                      ) : undefined
                    }
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
                      {visibleRows.map((row) => {
                        const locateTarget = provenanceOf(row.source_path);
                        return (
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
                          <td className="mono">
                            {matrixClauseLabel(row.clause_id)}
                          </td>
                          <td>
                            <span
                              className="excerpt"
                              title={matrixRequirementLabel(row.requirement)}
                            >
                              {row.requirement
                                ? matrixRequirementLabel(row.requirement)
                                : "（空要求）"}
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
                            <span
                              className="bw-strategy-cell"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <Select
                                value={row.strategy}
                                disabled={patch.isPending}
                                onValueChange={(next) =>
                                  onStrategyChange(row, next)
                                }
                              >
                                <SelectTrigger
                                  size="sm"
                                  className="bw-strategy-select"
                                  aria-label={`${matrixClauseLabel(row.clause_id)} 响应策略`}
                                >
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent
                                  className="bw-strategy-menu bw-select-menu"
                                  position="popper"
                                  align="start"
                                  sideOffset={4}
                                >
                                  {(
                                    matrix.data?.vocab.strategies ?? [
                                      "pending",
                                      "full",
                                      "positive",
                                      "negative",
                                    ]
                                  ).map((strategy) => (
                                    <SelectItem key={strategy} value={strategy}>
                                      {matrixStrategyLabel(strategy)}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </span>
                          </td>
                          <td className="num">{formatPercent(row.conf)}</td>
                          <td>
                            <button
                              type="button"
                              className="btn btn-sm"
                              disabled={!locateTarget}
                              title={
                                locateTarget
                                  ? `定位原文 · ${locateTarget.docId}${locateTarget.page != null ? ` 第 ${locateTarget.page} 页` : ""}`
                                  : "该来源无抽取出处，无法溯源"
                              }
                              onClick={(event) => {
                                event.stopPropagation();
                                if (locateTarget) setLocate(locateTarget);
                              }}
                            >
                              <Crosshair size={13} aria-hidden="true" />
                              溯源
                            </button>
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
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="card-b">
                {summary.blocked > 0 ? (
                  <div className="banner bad">
                    <AlertTriangle size={15} aria-hidden="true" />
                    <span>
                      <b>{summary.blocked} 条记录待人工核对</b>
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

      <HelpDrawer
        open={helpOpen}
        title="本页说明"
        onClose={() => setHelpOpen(false)}
      >
        <div className="bw-help">
          <p className="bw-help-intro">
            本页把从招标文件中抽取的商务要求整理成一张可确认、可追踪的响应台账。左侧与右侧使用同一份数据：左侧负责按来源与状态筛选，搜索框负责定位具体条款；右侧承载完整摘录、响应策略、置信度与确认操作。
          </p>
          <div className="bw-help-grid">
            <section
              className="bw-help-section"
              aria-labelledby="bw-help-tree-title"
            >
              <h3 id="bw-help-tree-title">要求来源从哪里来</h3>
              <ol className="bw-help-steps">
                <li>上传招标文件后，系统解析正文和表格，必要时识别扫描件。</li>
                <li>
                  系统按固定商务范围抽取附件、承诺、签章、保证金、截止时间、必需章节、资质与业绩门槛等要求。
                </li>
                <li>
                  抽取内容会自动回原文比对，未能逐字对上的进入「待人工核对」——这不代表内容有错，请人工核对后确认。
                </li>
                <li>
                  系统把抽取结果装配成响应矩阵；左侧筛选面板只提供来源、状态与必答条款的筛选，不重复展示完整明细。
                </li>
              </ol>
              <ul className="bw-help-list">
                <li>
                  要求摘录来自招标文件，不是系统编造；没有抽到的字段不会生成空行。
                </li>
                <li>
                  列表中的行编号是系统生成，不是招标文件原条款号；原条款位置通常写在要求摘录或依据中。
                </li>
                <li>
                  当前只覆盖商务要求；技术条款和完整多级法律条款不在此页。
                </li>
              </ul>
            </section>
            <section
              className="bw-help-section"
              aria-labelledby="bw-help-matrix-title"
            >
              <h3 id="bw-help-matrix-title">响应矩阵有什么用</h3>
              <p>
                右侧矩阵是抽取结果的人工确认台账，也是后续生成、审查和导出的唯一要求来源。
              </p>
              <ul className="bw-help-list">
                <li>
                  <b>确认与纠错：</b>
                  逐行核对要求摘录和强制项，处理草稿、待人工核对、已确认三种状态。
                </li>
                <li>
                  <b>卡住流程：</b>
                  待人工核对未清零时不能进入素材核对，避免错误摘录带入正文。
                </li>
                <li>
                  <b>设定响应策略：</b>
                  选择待定、完全响应、正偏离或负偏离；强制项选负偏离必须填写原因。
                </li>
                <li>
                  <b>关联章节：</b>
                  把要求归到正文对应标题，写作时展示该节要求。
                </li>
                <li>
                  <b>驱动交付：</b>
                  商务响应表、投标函承诺、附件索引、素材缺口、预审查和导出门禁都使用这些矩阵行。
                </li>
                <li>
                  <b>留痕审计：</b>
                  可导出未确认清单，也支持批量确认。
                </li>
              </ul>
            </section>
          </div>
          <div className="bw-help-callout">
            <Info size={15} aria-hidden="true" />
            <span>
              可以把它理解成“招标要求 → 我方响应策略 →
              证据与素材”的对照表，而不是投标文件正文本身。
            </span>
          </div>
        </div>
      </HelpDrawer>

      <Overlay
        open={dialog !== null}
        title={dialog?.mode === "negative" ? "★ 负偏离确认" : "人工核对确认"}
        subtitle={dialog ? matrixClauseLabel(dialog.row.clause_id) : undefined}
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
              {dialog?.mode === "negative" ? "记录负偏离" : "核对无误，确认"}
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
                    <b>系统未能从原文逐字核实此条：</b>
                    请对照招标文件核对摘录内容是否一致；确认时请填写核对依据（如原文页码或条款号）。
                  </>
                )}
              </span>
            </div>
            <div className="bw-requirement">
              <span className="k">要求摘录</span>
              <p>{matrixRequirementLabel(dialog.row.requirement)}</p>
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

      <Overlay
        open={locate !== null}
        title="定位原文"
        subtitle={
          locate
            ? `${locate.docId}${locate.page != null ? ` · 第 ${locate.page} 页` : " · 片段窗口"}`
            : undefined
        }
        onClose={() => setLocate(null)}
        variant="modal"
        size="wide"
        footer={
          <button
            type="button"
            className="btn pri"
            onClick={() => setLocate(null)}
          >
            关闭
          </button>
        }
      >
        {locate ? (
          <DocLocateBody
            taskId={taskId ?? ""}
            target={locate}
            fetchContent={fetchWriteDocContent}
            assetUrl={writeDocAssetUrl}
          />
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
            解析流程：解析招标文件 → 抽取商务要素 → 装配响应矩阵。
            失败时保留原因，不伪造矩阵。
          </span>
        </div>
      </div>
    </div>
  );
}
