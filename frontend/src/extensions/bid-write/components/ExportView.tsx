"use client";

/**
 * ⑥ 导出适配(批廿五 P1-δ 真接线)。
 *
 * 「导出前置校验」POST /export-precheck 只读重算(D0 断言+L1 fatal+L4 advisory,
 * 零落库);水印 null=L4 通过已摘除,字符串=带水印黄条。L4 面仅 advisory,
 * 不计入门禁。文件导出服务未建:无交付包按钮,不伪造下载。
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
import { useMemo } from "react";
import { toast } from "sonner";

import {
  Badge,
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  MetricCell,
  MetricStrip,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import { formatPercent, projectTitle } from "@/extensions/bid-write/helpers";
import {
  useBidWriteGaps,
  useExportPrecheck,
  useSelectedWriteTask,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";
import type { ExportGateResponse } from "@/extensions/bid-write/types";

interface GateItem {
  id: string;
  label: string;
  detail: string;
  state: "pass" | "fail" | "unknown";
}

function precheckGateItems(
  precheck: ExportGateResponse,
): GateItem[] {
  const items: GateItem[] = [
    {
      id: "d0",
      label: "D0 断言零失败",
      detail:
        precheck.assertion_counts.D0 === undefined
          ? "无 D0 断言计数"
          : `D0 计数 ${precheck.assertion_counts.D0}`,
      state: precheck.blocked ? "fail" : "pass",
    },
  ];
  for (const reason of precheck.reasons) {
    items.push({
      id: `reason:${reason}`,
      label: "阻断原因",
      detail: reason,
      state: "fail",
    });
  }
  for (const fatal of precheck.l1_fatal_fail) {
    items.push({
      id: `fatal:${fatal}`,
      label: "L1 fatal 规则命中",
      detail: fatal,
      state: "fail",
    });
  }
  items.push({
    id: "document",
    label: "正式正文文件导出",
    detail: "导出服务（分册/版式/签章位）尚未接入，无法生成交付包文件",
    state: "unknown",
  });
  return items;
}

export function ExportView() {
  const { taskId, task, isLoading } = useSelectedWriteTask();
  const gaps = useBidWriteGaps(taskId);
  const precheck = useExportPrecheck(taskId);

  const items = gaps.data?.items ?? [];
  const assertions = gaps.data?.assertions ?? null;
  const matrixBlocked = items.filter((item) => item.status === "blocked").length;
  const noMaterial = items.filter((item) => item.material_state === "无对应素材").length;

  const gate = useMemo<GateItem[]>(() => {
    if (precheck.data) return precheckGateItems(precheck.data);
    const assertionState: GateItem["state"] = assertions
      ? assertions.blocked
        ? "fail"
        : "pass"
      : "unknown";
    return [
      {
        id: "matrix",
        label: "响应矩阵无低置信阻断",
        detail:
          matrixBlocked > 0
            ? `仍有 ${matrixBlocked} 条低置信行未确认`
            : "响应矩阵无阻断行",
        state: matrixBlocked > 0 ? "fail" : "pass",
      },
      {
        id: "assertions",
        label: "预审查断言（点击「导出前置校验」获得门禁判定）",
        detail: assertions
          ? assertions.blocked
            ? `最近一次执行判定阻断，待补 ${assertions.pending.length} 条`
            : "最近一次执行未触发导出门禁"
          : "尚未执行断言，无法给出导出判定",
        state: assertionState,
      },
      {
        id: "materials",
        label: "素材缺口已处理",
        detail:
          noMaterial > 0
            ? `${noMaterial} 条要求仍无对应素材`
            : "没有无对应素材的要求",
        state: noMaterial > 0 ? "fail" : "pass",
      },
      {
        id: "document",
        label: "正式正文文件导出",
        detail: "导出服务（分册/版式/签章位）尚未接入，无法生成交付包文件",
        state: "unknown",
      },
    ];
  }, [assertions, matrixBlocked, noMaterial, precheck.data]);

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

  return (
    <>
      <PageHead
        icon={FileArchive}
        title="⑥ 导出适配"
        subtitle={
          task
            ? `${projectTitle(task)} · 前置校验只读重算，零落库`
            : "门禁明确判定后才谈交付包"
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
            className={`verdict ${precheck.data ? (precheck.data.blocked ? "blocked" : "clean") : failed > 0 ? "blocked" : "unrun"}`}
          >
            <span className="verdict-ic">
              {precheck.data ? (
                precheck.data.blocked ? (
                  <XCircle size={24} aria-hidden="true" />
                ) : (
                  <ShieldCheck size={24} aria-hidden="true" />
                )
              ) : failed > 0 ? (
                <XCircle size={24} aria-hidden="true" />
              ) : (
                <ShieldAlert size={24} aria-hidden="true" />
              )}
            </span>
            <div className="verdict-txt">
              <h3>
                {precheck.data
                  ? precheck.data.blocked
                    ? "门禁判定：阻断"
                    : "门禁判定：通过"
                  : failed > 0
                    ? "导出门禁未通过（矩阵/素材面）"
                    : "门禁信息不完整"}
              </h3>
              <p>
                {precheck.data
                  ? precheck.data.blocked
                    ? precheck.data.reasons.join("；") || "存在未通过断言"
                    : "D0 断言与 L1 fatal 均无阻断；L4 仅 advisory 不参与判定。"
                  : "点「导出前置校验」获得后端确定性门禁判定；导出页不会绕过门禁。"}
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
              <span>风险水印已摘除：L4 语义审查通过（advisory-only 面不计入阻断）。</span>
            </div>
          ) : null}

          <MetricStrip>
            <MetricCell
              label="门禁失败"
              value={failed}
              tone={failed > 0 ? "err" : "ok"}
              accent
            />
            <MetricCell label="D0 断言" value={precheck.data?.assertion_counts.D0 ?? "—"} />
            <MetricCell
              label="断言通过率"
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
                <h3>L4 语义审查</h3>
                <span className="r">
                  <Badge tone="info">advisory-only · 不计入门禁</Badge>
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
                    tone={failed > 0 ? "bad" : precheck.data ? "ok" : "warn"}
                    dot
                  >
                    {failed > 0
                      ? `${failed} 项未通过`
                      : precheck.data
                        ? "判定通过"
                        : "待前置校验"}
                  </Badge>
                </span>
              </div>
              <div className="card-b">
                <ul className="gate-list">
                  {gate.map((item) => (
                    <li key={item.id} className={item.state}>
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
                      {item.id === "matrix" && matrixBlocked > 0 ? (
                        <Link
                          href={
                            taskId ? writeTaskHref("intake", taskId) : "/bid-write/intake"
                          }
                          className="btn btn-sm"
                        >
                          去确认
                        </Link>
                      ) : null}
                      {item.id === "assertions" ? (
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

            <div className="card">
              <div className="card-h">
                <h3>交付包</h3>
                <span className="r">
                  <Badge tone="gray">服务未接入</Badge>
                </span>
              </div>
              <div className="card-b">
                <p className="bw-muted">
                  交付包格式与版式适配（DOCX / PDF /
                  投标客户端导入包）由导出服务承担，尚未接入；本页不提供下载按钮，不生成占位文件。
                  前置校验结果即当前导出面所能给出的全部确定性信息。
                </p>
                {precheck.error ? <ErrorBlock error={precheck.error} /> : null}
                <button
                  type="button"
                  className="btn pri bw-full bw-mt"
                  disabled={!ready || precheck.isPending}
                  onClick={() => void onPrecheck()}
                >
                  <ShieldCheck size={14} aria-hidden="true" />
                  {precheck.isPending ? "校验中…" : "导出前置校验"}
                </button>
              </div>
            </div>
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
