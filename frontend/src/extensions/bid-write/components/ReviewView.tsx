"use client";

import {
  AlertTriangle,
  CheckCircle2,
  CheckCheck,
  ClipboardList,
  Download,
  Info,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
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
} from "@/extensions/bid-write/components/primitives";
import { REVIEW_COPY } from "@/extensions/bid-write/copy";
import {
  ASSERTION_STATUS_LABELS,
  assertionMessageLabel,
  assertionWatermark,
  downloadCsv,
  formatDate,
  projectTitle,
} from "@/extensions/bid-write/helpers";
import {
  useBidWriteGaps,
  useDeliveryGates,
  useSelectedWriteTask,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";
import type {
  AssertionPendingItem,
  AssertionSkippedItem,
} from "@/extensions/bid-write/types";

type Filter = "all" | "FAIL" | "ERROR" | "SKIPPED";

const ASSERTION_ACTION_LABELS: Record<string, string> = {
  no_signal: "无需处理",
};

const DELIVERY_STATE_BADGES = {
  pass: { tone: "ok", label: "通过" },
  fail: { tone: "bad", label: "未通过" },
  unknown: { tone: "gray", label: "未知" },
} as const;

type TableRow =
  | { kind: "pending"; item: AssertionPendingItem }
  | { kind: "skipped"; item: AssertionSkippedItem };

function rowStatus(row: TableRow): string {
  if (row.kind === "skipped") return "SKIPPED";
  return row.item.status;
}

function rowId(row: TableRow): string {
  return row.item.assertion_id;
}

function rowSkill(row: TableRow): string {
  // skipped 报告只带 assertion_id/level/reason/message，不含 skill；不猜技能名。
  return row.kind === "pending" ? row.item.skill : "—";
}

function rowMessage(row: TableRow): string {
  return row.item.message;
}

function rowLevel(row: TableRow): string {
  return row.kind === "skipped" ? row.item.level : "—";
}

function rowAction(row: TableRow): string {
  if (row.kind === "pending") {
    const action = row.item.human_action;
    if (!action) return "—";
    return ASSERTION_ACTION_LABELS[action] ?? action;
  }
  const reason = row.item.skipped_reason ?? "可解释跳过";
  return ASSERTION_ACTION_LABELS[reason] ?? reason;
}

function rowMessageLabel(row: TableRow): string {
  return assertionMessageLabel(rowMessage(row));
}

export function ReviewView() {
  const { taskId, task, isLoading } = useSelectedWriteTask();
  const gaps = useBidWriteGaps(taskId);
  const delivery = useDeliveryGates(taskId);
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<TableRow | null>(null);

  const assertions = gaps.data?.assertions ?? null;
  const pending = useMemo(() => assertions?.pending ?? [], [assertions]);
  const skipped = useMemo(() => assertions?.skipped ?? [], [assertions]);
  const watermark = assertionWatermark(assertions);

  const allRows = useMemo<TableRow[]>(
    () => [
      ...pending.map((item) => ({ kind: "pending" as const, item })),
      ...skipped.map((item) => ({ kind: "skipped" as const, item })),
    ],
    [pending, skipped],
  );

  const rows = useMemo(
    () =>
      filter === "all"
        ? allRows
        : allRows.filter((row) => rowStatus(row) === filter),
    [allRows, filter],
  );

  const exportPending = () => {
    if (pending.length === 0) {
      toast.error("没有待补断言可导出");
      return;
    }
    downloadCsv(
      `预审查-待补清单-${new Date().toISOString().slice(0, 10)}.csv`,
      ["断言 ID", "技能", "状态", "说明", "建议动作"],
      pending.map((item) => [
        item.assertion_id,
        item.skill,
        ASSERTION_STATUS_LABELS[item.status] ?? item.status,
        item.message,
        item.human_action ?? "",
      ]),
    );
    toast.success(`已导出 ${pending.length} 条待补断言`);
  };

  return (
    <>
      <PageHead
        icon={ClipboardList}
        title="⑤ 预审查与断言"
        subtitle={
          task
            ? `${projectTitle(task)} · 只展示最近一次执行的待补、跳过与门禁摘要`
            : "只展示最近一次执行的待补、跳过与门禁摘要"
        }
        actions={
          <>
            <button
              type="button"
              className="btn btn-sm"
              onClick={exportPending}
              disabled={pending.length === 0}
            >
              <Download size={13} aria-hidden="true" />
              导出待补清单
            </button>
            <span className="bw-muted">{REVIEW_COPY.snapshotBadge}</span>
          </>
        }
      />

      {isLoading ? (
        <LoadingBlock label="正在加载任务…" />
      ) : !task ? (
        <EmptyState
          icon={ClipboardList}
          title="还没有写作项目"
          description="先创建项目并推进到生成/预审查阶段。"
          action={
            <Link href="/bid-write" className="btn pri">
              去项目列表
            </Link>
          }
        />
      ) : gaps.isLoading ? (
        <LoadingBlock label="正在加载预审查摘要…" />
      ) : gaps.error ? (
        <ErrorBlock error={gaps.error} onRetry={() => void gaps.refetch()} />
      ) : (
        <>
          <div className="card bw-mt">
            <div className="card-h">
              <h3>交付门禁清单</h3>
              <span className="r">
                <Badge tone={delivery.blocked ? "bad" : "ok"} dot>
                  {delivery.blocked ? "存在未通过项" : "无未通过项"}
                </Badge>
                {assertions ? (
                  <>
                    <span>执行于</span>
                    <b>{formatDate(assertions.run_at)}</b>
                    <span className="mono">{assertions.schema_version}</span>
                  </>
                ) : (
                  <Badge tone="gray">未执行</Badge>
                )}
              </span>
            </div>
            <div className="card-b">
              <ul className="gate-list">
                {delivery.gates.map((gate) => {
                  const badge = DELIVERY_STATE_BADGES[gate.state];
                  return (
                    <li key={gate.key} className={gate.state}>
                      <span className="gate-ic">
                        {gate.state === "pass" ? (
                          <CheckCircle2 size={16} aria-hidden="true" />
                        ) : gate.state === "fail" ? (
                          <XCircle size={16} aria-hidden="true" />
                        ) : (
                          <Info size={16} aria-hidden="true" />
                        )}
                      </span>
                      <div>
                        <b>{gate.label}</b>
                        <p>{gate.detail}</p>
                      </div>
                      <Badge tone={badge.tone}>{badge.label}</Badge>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>

          <MetricStrip>
            <MetricCell
              label="待补断言"
              value={pending.length}
              tone={pending.length > 0 ? "err" : "ok"}
              accent
            />
            <MetricCell label="跳过注记" value={skipped.length} tone="warn" />
            <MetricCell
              label="导出门禁"
              value={
                watermark === "blocked"
                  ? "阻断"
                  : watermark === "clean"
                    ? "通过"
                    : "未执行"
              }
              tone={
                watermark === "blocked"
                  ? "err"
                  : watermark === "clean"
                    ? "ok"
                    : undefined
              }
            />
            <MetricCell
              label="汇总口径"
              value="最近执行"
              suffix="共 43 条规则"
            />
          </MetricStrip>

          {watermark === "blocked" ? (
            <div className="banner bad">
              <AlertTriangle size={15} aria-hidden="true" />
              <span>
                <b>门禁裁决来自后端：</b>
                未展示的通过项不代表未执行。
              </span>
            </div>
          ) : null}

          <div className="card bw-mt">
            <div className="card-h">
              <h3>断言结果摘要</h3>
              <span className="r">
                <span className="seg">
                  <button
                    type="button"
                    className={filter === "all" ? "on" : undefined}
                    onClick={() => setFilter("all")}
                  >
                    全部 {allRows.length}
                  </button>
                  <button
                    type="button"
                    className={filter === "FAIL" ? "on" : undefined}
                    onClick={() => setFilter("FAIL")}
                  >
                    失败{" "}
                    {pending.filter((item) => item.status === "FAIL").length}
                  </button>
                  <button
                    type="button"
                    className={filter === "ERROR" ? "on" : undefined}
                    onClick={() => setFilter("ERROR")}
                  >
                    错误{" "}
                    {pending.filter((item) => item.status === "ERROR").length}
                  </button>
                  <button
                    type="button"
                    className={filter === "SKIPPED" ? "on" : undefined}
                    onClick={() => setFilter("SKIPPED")}
                  >
                    跳过 {skipped.length}
                  </button>
                </span>
              </span>
            </div>
            {rows.length === 0 ? (
              <div className="card-b">
                <EmptyState
                  icon={ClipboardList}
                  title={
                    assertions ? "当前筛选没有待补或跳过项" : "尚无断言执行结果"
                  }
                  description={
                    assertions
                      ? "最近一次执行没有落入当前筛选的记录。"
                      : "断言执行器接入后，这里会展示失败、错误与可解释跳过。"
                  }
                />
              </div>
            ) : (
              <div className="tbl-wrap">
                <table className="tbl bw-assertion-table">
                  <thead>
                    <tr>
                      <th>断言 ID</th>
                      <th>技能</th>
                      <th>等级</th>
                      <th>状态</th>
                      <th>说明</th>
                      <th>建议动作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr
                        key={`${row.kind}-${rowId(row)}`}
                        onClick={() => setSelected(row)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            setSelected(row);
                          }
                        }}
                        tabIndex={0}
                      >
                        <td className="mono bw-nowrap">{rowId(row)}</td>
                        <td>{rowSkill(row)}</td>
                        <td>
                          {rowLevel(row) === "—" ? (
                            "—"
                          ) : (
                            <Badge
                              tone={
                                rowLevel(row) === "D0"
                                  ? "bad"
                                  : rowLevel(row) === "D1"
                                    ? "d1"
                                    : "gray"
                              }
                            >
                              {rowLevel(row)}
                            </Badge>
                          )}
                        </td>
                        <td>
                          <Badge
                            tone={
                              rowStatus(row) === "SKIPPED"
                                ? "gray"
                                : rowStatus(row) === "PASS"
                                  ? "ok"
                                  : "bad"
                            }
                            dot
                          >
                            {ASSERTION_STATUS_LABELS[rowStatus(row)] ??
                              rowStatus(row)}
                          </Badge>
                        </td>
                        <td>
                          <span
                            className="excerpt ellipsis"
                            title={rowMessageLabel(row)}
                          >
                            {rowMessageLabel(row)}
                          </span>
                        </td>
                        <td>{rowAction(row)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="card-b">
              <div className="banner info">
                <Info size={15} aria-hidden="true" />
                <span>
                  {REVIEW_COPY.bottomNote}
                </span>
              </div>
            </div>
          </div>

          {taskId ? (
            <div className="bw-mt bw-inline-facts">
              <Link
                href={writeTaskHref("export", taskId)}
                className="btn pri btn-sm"
              >
                去导出
              </Link>
              <Link
                href={writeTaskHref("workbench", taskId)}
                className="btn btn-sm"
              >
                回工作台
              </Link>
              {watermark === "clean" ? (
                <span className="bw-check-line">
                  <CheckCheck size={14} aria-hidden="true" />
                  门禁判定可由导出页复核
                </span>
              ) : null}
            </div>
          ) : null}
        </>
      )}

      <Overlay
        open={selected !== null}
        title={selected ? rowId(selected) : "断言详情"}
        subtitle={selected ? rowStatus(selected) : undefined}
        onClose={() => setSelected(null)}
        footer={
          <button
            type="button"
            className="btn pri"
            onClick={() => setSelected(null)}
          >
            关闭
          </button>
        }
      >
        {selected ? (
          <div className="kv-list">
            <span className="k">断言</span>
            <span className="v mono">{rowId(selected)}</span>
            <span className="k">技能</span>
            <span className="v">{rowSkill(selected)}</span>
            <span className="k">等级</span>
            <span className="v">{rowLevel(selected)}</span>
            <span className="k">状态</span>
            <span className="v">
              {ASSERTION_STATUS_LABELS[rowStatus(selected)] ??
                rowStatus(selected)}
            </span>
            <span className="k">说明</span>
            <span className="v">{rowMessage(selected)}</span>
            {selected.kind === "pending" ? (
              <>
                <span className="k">建议动作</span>
                <span className="v">{selected.item.human_action ?? "—"}</span>
              </>
            ) : (
              <>
                <span className="k">跳过原因</span>
                <span className="v">
                  {selected.item.skipped_reason ?? "可解释跳过"}
                </span>
              </>
            )}
          </div>
        ) : null}
      </Overlay>
    </>
  );
}
