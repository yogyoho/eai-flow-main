"use client";

/**
 * ⑥ 导出适配(批廿五 P1-δ 真接线)。
 *
 * 「导出前置校验」POST /export-precheck 只读重算(D0 断言+L1 fatal+L4 advisory,
 * 零落库);水印 null=L4 通过已摘除,字符串=带水印黄条。L4 面仅 advisory,
 * 不计入门禁。批三十三:已批准修订可生成 DOCX 分册 + manifest ZIP;
 * 导出按钮只在 revision.status=approved 时启用,后端仍会重跑 gate。
 */

import {
  AlertTriangle,
  CheckCircle2,
  FileArchive,
  Info,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { DeliveryPackageCard } from "@/extensions/bid-write/components/DeliveryPackageCard";
import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  MetricCell,
  MetricStrip,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import { EXPORT_COPY } from "@/extensions/bid-write/copy";
import { formatPercent, projectTitle } from "@/extensions/bid-write/helpers";
import {
  useBidWriteGaps,
  useDeliveryGates,
  useExportPrecheck,
  useExportRevision,
  useSelectedWriteTask,
  useTaskApproval,
  useTaskExports,
} from "@/extensions/bid-write/hooks";
import { WRITE_PAGE_PATHS, writeTaskHref } from "@/extensions/bid-write/nav";
import type { ExportDownload } from "@/extensions/bid-write/types";

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ExportView() {
  const { taskId, task, isLoading } = useSelectedWriteTask();
  const gaps = useBidWriteGaps(taskId);
  const delivery = useDeliveryGates(taskId);
  const precheck = useExportPrecheck(taskId);
  const approval = useTaskApproval(taskId);
  const exportHistory = useTaskExports(taskId);
  const exportMutation = useExportRevision(taskId);
  const [lastExport, setLastExport] = useState<ExportDownload | null>(null);

  const revision = approval.data?.revision ?? null;
  const approved = revision?.status === "approved" && revision.hash_ok;
  const deliveryRevision = revision
    ? {
        ...revision,
        status: approved
          ? revision.status
          : (EXPORT_COPY.revisionStateLabels[revision.status] ??
            revision.status),
      }
    : null;

  const gate = delivery.gates;
  const failed = gate.filter((item) => item.state === "fail").length;
  const unknown = gate.filter((item) => item.state === "unknown").length;
  const ready = task?.status === "matrix_ready";
  const l4 = precheck.data?.l4 ?? null;
  const metrics = precheck.data?.metrics ?? null;

  const onPrecheck = async () => {
    if (!ready) return;
    try {
      await precheck.mutateAsync();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "前置校验失败");
    }
  };

  const onExport = async () => {
    if (!approved || !revision) return;
    try {
      const result = await exportMutation.mutateAsync(revision.id);
      setLastExport(result);
      triggerBlobDownload(result.blob, result.filename);
      toast.success(
        `已生成 ${result.fileCount || "若干"} 个 DOCX 分册（ZIP 交付包）`,
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "导出失败");
    }
  };

  return (
    <>
      <PageHead
        icon={FileArchive}
        title="⑥ 导出适配"
        subtitle={
          task
            ? `${projectTitle(task)} · ${EXPORT_COPY.subtitle}`
            : EXPORT_COPY.subtitle
        }
        actions={
          <button
            type="button"
            className="btn pri btn-sm"
            disabled={!ready || precheck.isPending}
            onClick={() => void onPrecheck()}
            title={ready ? "D0 断言+L1 fatal+L4 只读重算" : "矩阵未就绪（后端 409）"}
          >
            <ShieldCheck size={13} aria-hidden="true" />
            {precheck.isPending ? "校验中…" : "导出前置校验"}
          </button>
        }
      />

      {isLoading ? (
        <LoadingBlock label="正在加载任务…" />
      ) : !task ? (
        <EmptyState
          icon={FileArchive}
          title="还没有写作项目"
          description="先创建项目并完成矩阵确认与生成，再进入导出。"
          action={
            <Link href="/bid-write" className="btn pri">
              去项目列表
            </Link>
          }
        />
      ) : gaps.isLoading ? (
        <LoadingBlock label="正在核验导出门禁…" />
      ) : gaps.error ? (
        <ErrorBlock error={gaps.error} onRetry={() => void gaps.refetch()} />
      ) : (
        <>
          <div
            className={`verdict ${failed > 0 ? "blocked" : unknown > 0 ? "unrun" : "clean"}`}
          >
            <span className="verdict-ic">
              {failed > 0 ? (
                <XCircle size={24} aria-hidden="true" />
              ) : unknown > 0 ? (
                <ShieldAlert size={24} aria-hidden="true" />
              ) : (
                <ShieldCheck size={24} aria-hidden="true" />
              )}
            </span>
            <div className="verdict-txt">
              <h3>
                {failed > 0
                  ? "交付门禁未通过"
                  : unknown > 0
                    ? "交付门禁待确认"
                    : "交付门禁通过"}
              </h3>
              <p>
                {failed > 0
                  ? precheck.data?.blocked
                    ? precheck.data.reasons.join("；") || "存在未通过的交付门禁项"
                    : "存在未通过的交付门禁项。"
                  : unknown > 0
                    ? "等待矩阵、预审查、素材或正文审批数据补齐。"
                    : "矩阵、预审查、素材与正文审批均无未通过项。"}
              </p>
            </div>
            <div className="verdict-meta">
              <span>失败项</span>
              <b>{failed}</b>
              <span>未知项</span>
              <b>{unknown}</b>
              {precheck.data ? (
                <span className="mono">{precheck.data.schema_version}</span>
              ) : null}
            </div>
          </div>

          {precheck.data?.watermark != null ? (
            <div className="banner warn">
              <AlertTriangle size={15} aria-hidden="true" />
              <span>
                <b>风险水印未摘除：</b>
                {precheck.data.watermark}
              </span>
            </div>
          ) : null}
          {precheck.data && precheck.data.watermark == null ? (
            <div className="banner ok">
              <CheckCircle2 size={15} aria-hidden="true" />
              <span>风险水印已摘除：语义审查通过（提示级，不计入阻断）。</span>
            </div>
          ) : null}

          <MetricStrip>
            <MetricCell
              label="门禁失败"
              value={failed}
              tone={failed > 0 ? "err" : "ok"}
              accent
            />
            <MetricCell
              label="必须通过项"
              value={precheck.data?.assertion_counts.D0 ?? "—"}
            />
            <MetricCell
              label="检查通过率"
              value={formatPercent(metrics?.assertion_pass_rate ?? null)}
            />
            <MetricCell
              label="人工编辑占比"
              value={formatPercent(metrics?.manual_edit_ratio ?? null)}
            />
            <MetricCell
              label="校验耗时"
              value={metrics ? `${(metrics.latency_ms / 1000).toFixed(1)}s` : "—"}
            />
          </MetricStrip>

          {l4 ? (
            <div className="card bw-mt">
              <div className="card-h">
                <h3>语义审查</h3>
                <span className="r">
                  <Badge tone="info">提示级 · 不计入门禁</Badge>
                  {l4.watermark_removed ? <Badge tone="ok">水印已摘除</Badge> : null}
                </span>
              </div>
              <div className="card-b">
                <div className="bw-gen-list">
                  <div className="gen-row">
                    <b>参与卡</b>
                    <div className="bw-muted">
                      {l4.participants.length > 0
                        ? l4.participants.join("、")
                        : "无（零承诺/零响应行时 L4 不参与）"}
                    </div>
                    <Badge tone={l4.executed ? "ok" : "gray"}>
                      {l4.executed ? "已执行" : "未执行"}
                    </Badge>
                  </div>
                  <div className="gen-row">
                    <b>裁决计数</b>
                    <div className="bw-muted mono">
                      {Object.entries(l4.counts).map(([k, v]) => `${k}=${v}`).join("  ") || "—"}
                    </div>
                    <Badge tone="gray">{l4.issues.length} 条建议</Badge>
                  </div>
                  {l4.input_missing.length > 0 ? (
                    <div className="gen-row">
                      <b>输入缺席</b>
                      <div className="bw-muted mono">{l4.input_missing.join("、")}</div>
                      <Badge tone="warn">{l4.input_missing.length} 项</Badge>
                    </div>
                  ) : null}
                  {l4.issues.map((issue) => (
                    <div className="gen-row" key={issue.rule_id}>
                      <b className="mono">{issue.rule_id}</b>
                      <div className="bw-muted">
                        {issue.reason ?? "（无理由文本）"}
                      </div>
                      <Badge tone={issue.verdict === "fail" ? "bad" : "warn"}>
                        {issue.verdict}
                      </Badge>
                    </div>
                  ))}
                </div>
                <p className="bw-muted bw-mt-sm">{l4.scope_note}</p>
              </div>
            </div>
          ) : null}

          <div className="split bw-export-split bw-mt">
            <div className="card">
              <div className="card-h">
                <h3>导出门禁</h3>
                <span className="r">
                  <Badge
                    tone={failed > 0 ? "bad" : unknown > 0 ? "warn" : "ok"}
                    dot
                  >
                    {failed > 0
                      ? `${failed} 项未通过`
                      : unknown > 0
                        ? `${unknown} 项待确认`
                        : "判定通过"}
                  </Badge>
                </span>
              </div>
              <div className="card-b">
                <ul className="gate-list">
                  {gate.map((item) => (
                    <li key={item.key} className={item.state}>
                      <span className="gate-ic">
                        {item.state === "pass" ? (
                          <CheckCircle2 size={16} aria-hidden="true" />
                        ) : item.state === "fail" ? (
                          <XCircle size={16} aria-hidden="true" />
                        ) : (
                          <Info size={16} aria-hidden="true" />
                        )}
                      </span>
                      <div>
                        <b>{item.label}</b>
                        <p>{item.detail}</p>
                      </div>
                      {item.key === "matrix" && item.state === "fail" ? (
                        <Link
                          href={
                            taskId ? writeTaskHref("intake", taskId) : "/bid-write/intake"
                          }
                          className="btn btn-sm"
                        >
                          去确认
                        </Link>
                      ) : null}
                      {item.key === "materials" && item.state === "fail" ? (
                        <Link
                          href={
                            taskId
                              ? writeTaskHref("materials_library", taskId)
                              : WRITE_PAGE_PATHS.materials_library
                          }
                          className="btn btn-sm"
                        >
                          去资质素材库补录
                        </Link>
                      ) : null}
                      {item.key === "assertions" ? (
                        <Link
                          href={
                            taskId ? writeTaskHref("review", taskId) : "/bid-write/review"
                          }
                          className="btn btn-sm"
                        >
                          看预审查
                        </Link>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {precheck.error ? <ErrorBlock error={precheck.error} /> : null}
            <DeliveryPackageCard
              revision={deliveryRevision}
              history={exportHistory.data?.items ?? []}
              historyLoading={exportHistory.isLoading}
              exporting={exportMutation.isPending}
              result={lastExport}
              error={exportMutation.error}
              onExport={() => void onExport()}
            />
          </div>

          {failed > 0 ? (
            <div className="banner bad bw-mt">
              <AlertTriangle size={15} aria-hidden="true" />
              <span>
                只要存在失败项，就不存在「可导出」判定；不得以「下载文件」代替门禁裁决。
              </span>
            </div>
          ) : null}
        </>
      )}
    </>
  );
}
