"use client";

/**
 * ③ 生成配置与执行(批廿五 P1-δ 真接线)。
 *
 * 单价表从任务抽取快照 `engine_meta.fields["tender.boq_items"]` 渲染(键=清单项 id,
 * 直通 knobs.unit_prices);旋钮经 assembleGenerateKnobs 装配后 POST /generate。
 * 结果面=门禁 verdict(阻断原因/水印/L4 advisory)+metrics;文件导出服务未建,不做假下载。
 */

import { Bolt, FileSpreadsheet, Info, PlayCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  Badge,
  EmptyState,
  ErrorBlock,
  MetricCell,
  MetricStrip,
  PageHead,
} from "@/extensions/bid-write/components/primitives";
import { GENERATE_COPY, STEP_BACK } from "@/extensions/bid-write/copy";
import {
  assembleGenerateKnobs,
  formatPercent,
  projectTitle,
  type GenerateKnobsDraft,
} from "@/extensions/bid-write/helpers";
import {
  useGenerateTask,
  useSelectedWriteTask,
} from "@/extensions/bid-write/hooks";
import { writeTaskHref } from "@/extensions/bid-write/nav";
import type { BoqItem, WriteTaskOut } from "@/extensions/bid-write/types";

function boqItemsOf(task: WriteTaskOut | null): BoqItem[] {
  const fields = task?.engine_meta?.fields;
  if (!fields || typeof fields !== "object") return [];
  const raw = (fields as Record<string, unknown>)["tender.boq_items"];
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (item): item is BoqItem =>
      !!item &&
      typeof item === "object" &&
      typeof (item as BoqItem).id === "string",
  );
}

function numberValue(value: string): number {
  const parsed = Number(value.replaceAll(",", "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function money(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

const EMPTY_DRAFT: GenerateKnobsDraft = {
  warrantyMonths: "",
  spareYears: "",
  responseHours: "",
  penaltyCap: "",
  signDate: "",
  priceNote: "",
  unitPrices: {},
};

export function GenerateView() {
  const { taskId, task } = useSelectedWriteTask();
  const generate = useGenerateTask(taskId);
  const [draft, setDraft] = useState<GenerateKnobsDraft>(EMPTY_DRAFT);

  const items = useMemo(() => boqItemsOf(task), [task]);
  const priced = items.filter((item) => (draft.unitPrices[item.id] ?? "").trim() !== "");
  const total = useMemo(
    () =>
      priced.reduce(
        (sum, item) =>
          sum + numberValue(String(item.qty ?? "")) * numberValue(draft.unitPrices[item.id] ?? ""),
        0,
      ),
    [priced, draft.unitPrices],
  );

  const ready = task?.status === "matrix_ready";
  const setUnitPrice = (id: string, value: string) =>
    setDraft((current) => ({
      ...current,
      unitPrices: { ...current.unitPrices, [id]: value },
    }));

  const onStart = async () => {
    if (!ready) return;
    try {
      await generate.mutateAsync({ knobs: assembleGenerateKnobs(draft) });
      toast.success("生成完成，门禁与 L4 审查结果见下方");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成失败");
    }
  };

  /** 重建正文:knobs+regenerate_document=true → 后端受控重建(有审批修订 409)。
   *  确认话术必须明说「覆盖人工修改」——半句警告等于没有警告。 */
  const onRegenerate = async () => {
    if (!ready) return;
    const confirmed = window.confirm(
      "重建正文将用当前商务参数重新装配整篇正文，覆盖已有的人工修改；已提交审批的修订不可覆盖（后端将拒绝）。确定继续？",
    );
    if (!confirmed) return;
    try {
      await generate.mutateAsync({
        knobs: { ...assembleGenerateKnobs(draft), regenerate_document: true },
      });
      toast.success("正文已重建；回「④ 写作工作台」查看新正文。");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "重建正文失败");
    }
  };

  const verdict = generate.data?.verdict ?? null;
  const l4 = verdict?.l4 ?? null;

  return (
    <>
      <PageHead
        icon={Bolt}
        title="③ 生成配置与执行"
        subtitle={
          task
            ? `${projectTitle(task)} · ${GENERATE_COPY.subtitle}`
            : GENERATE_COPY.subtitleNoTask
        }
        actions={
          <>
            {taskId && STEP_BACK.generate && (
              <Link
                href={writeTaskHref(STEP_BACK.generate, taskId)}
                className="btn btn-sm"
              >
                ← 上一步
              </Link>
            )}
            <Badge tone={ready ? "ok" : "gray"}>
              {ready ? "矩阵就绪" : (task ? "矩阵未就绪" : "未选任务")}
            </Badge>
          </>
        }
      />

      {items.length === 0 ? (
        <p className="bw-muted">
          本次未提取到工程量清单，报价相关指标不适用。
        </p>
      ) : (
        <MetricStrip>
          <MetricCell label="清单行" value={items.length} suffix="项" accent />
          <MetricCell
            label="已出价"
            value={priced.length}
            suffix={`/${items.length}`}
            tone={priced.length < items.length ? "warn" : "ok"}
          />
          <MetricCell
            label="报价预览合计"
            value={priced.length ? `¥${money(total)}` : "—"}
            tone="ok"
          />
          <MetricCell
            label="必须通过项"
            value={verdict?.assertion_counts?.D0 ?? "—"}
          />
        </MetricStrip>
      )}

      {!task ? (
        <div className="banner info bw-mt">
          <Info size={15} aria-hidden="true" />
          <span>当前没有选中任务；请先在项目列表创建写作项目并完成矩阵确认。</span>
        </div>
      ) : !ready ? (
        <div className="banner warn bw-mt">
          <Info size={15} aria-hidden="true" />
          <span>
            任务状态「{task.status}」：矩阵确认（①）完成后才能生成（后端 409 拒绝）。
          </span>
        </div>
      ) : null}

      <div className="card bw-mt">
        <div className="card-h">
          <h3>报价输入 · 单价表</h3>
        </div>
        {items.length === 0 ? (
          <div className="card-b">
            <EmptyState
              icon={FileSpreadsheet}
              title={GENERATE_COPY.boqEmptyTitle}
              description={GENERATE_COPY.boqEmptyHint}
            />
          </div>
        ) : (
          <div className="card-b">
            <p className="bw-muted">{GENERATE_COPY.FIELD_TARGETS.unit_prices}</p>
            <div className="tbl-wrap">
              <table className="tbl dense">
                <thead>
                  <tr>
                    <th>清单项 id</th>
                    <th>名称</th>
                    <th className="num">数量</th>
                    <th>单位</th>
                    <th className="num">单价（元）</th>
                    <th className="num">合价预览（元）</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const price = draft.unitPrices[item.id] ?? "";
                    return (
                      <tr key={item.id}>
                        <td className="mono">{item.id}</td>
                        <td>{item.name}</td>
                        <td className="num mono">{String(item.qty ?? "")}</td>
                        <td>{item.unit}</td>
                        <td>
                          <input
                            className="inp num bw-cell-input"
                            value={price}
                            placeholder="0.00"
                            aria-label={`${item.id} 单价`}
                            onChange={(event) => setUnitPrice(item.id, event.target.value)}
                          />
                        </td>
                        <td className="num mono">
                          {price.trim() !== ""
                            ? money(numberValue(String(item.qty ?? "")) * numberValue(price))
                            : "—"}
                        </td>
                      </tr>
                    );
                  })}
                  <tr>
                    <td colSpan={4} className="num bw-total-label">
                      合计预览（仅已出价行 · 后端按同一公式确定性重算）
                    </td>
                    <td className="num mono bw-total-value">¥{money(total)}</td>
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <div className="card bw-mt">
        <div className="card-h">
          <h3>{GENERATE_COPY.paramsTitle}</h3>
          <span className="r">
            <Badge tone="gray">{GENERATE_COPY.paramsBadge}</Badge>
          </span>
        </div>
        <div className="card-b">
          <div className="bw-policy-grid">
            <label className="field">
              <span>质保承诺（月或原文表述）</span>
              <span className="bw-muted">
                {GENERATE_COPY.FIELD_TARGETS.warranty_period}
              </span>
              <input
                className="inp"
                value={draft.warrantyMonths}
                placeholder="如 24（纯数字自动补「个月」）"
                onChange={(event) =>
                  setDraft({ ...draft, warrantyMonths: event.target.value })
                }
              />
            </label>
            <label className="field">
              <span>备件供应年限</span>
              <span className="bw-muted">
                {GENERATE_COPY.FIELD_TARGETS.general_commitments}
              </span>
              <input
                className="inp"
                value={draft.spareYears}
                placeholder="如 10（进通用承诺清单）"
                onChange={(event) => setDraft({ ...draft, spareYears: event.target.value })}
              />
            </label>
            <label className="field">
              <span>故障响应时限（小时）</span>
              <span className="bw-muted">
                {GENERATE_COPY.FIELD_TARGETS.general_commitments}
              </span>
              <input
                className="inp"
                value={draft.responseHours}
                placeholder="如 8"
                onChange={(event) => setDraft({ ...draft, responseHours: event.target.value })}
              />
            </label>
            <label className="field">
              <span>违约金上限（%）</span>
              <span className="bw-muted">
                {GENERATE_COPY.FIELD_TARGETS.general_commitments}
              </span>
              <input
                className="inp"
                value={draft.penaltyCap}
                placeholder="如 5"
                onChange={(event) => setDraft({ ...draft, penaltyCap: event.target.value })}
              />
            </label>
            <label className="field">
              <span>签署日期</span>
              <span className="bw-muted">
                {GENERATE_COPY.FIELD_TARGETS.sign_date}
              </span>
              <input
                className="inp"
                value={draft.signDate}
                placeholder="2026-11-20"
                onChange={(event) => setDraft({ ...draft, signDate: event.target.value })}
              />
            </label>
            <label className="field">
              <span>报价说明</span>
              <span className="bw-muted">
                {GENERATE_COPY.FIELD_TARGETS.price_note}
              </span>
              <input
                className="inp"
                value={draft.priceNote}
                placeholder="如 暂估按最终结算"
                onChange={(event) => setDraft({ ...draft, priceNote: event.target.value })}
              />
            </label>
          </div>
          <div className="bw-generate-actions bw-mt-sm">
            <button
              type="button"
              className="btn pri"
              disabled={!ready || generate.isPending}
              onClick={() => void onStart()}
            >
              <PlayCircle size={14} aria-hidden="true" />
              {generate.isPending ? "生成中…" : "开始生成"}
            </button>
            <button
              type="button"
              className="btn"
              disabled={!ready || generate.isPending}
              title="用当前商务参数重新装配正文；覆盖人工修改，审批中的修订会被后端拒绝"
              onClick={() => void onRegenerate()}
            >
              <RefreshCw size={14} aria-hidden="true" />
              {generate.isPending ? "生成中…" : "重建正文"}
            </button>
            <span className="bw-muted">{GENERATE_COPY.runHint}</span>
          </div>
          {generate.error ? (
            <ErrorBlock error={generate.error} />
          ) : null}
        </div>
      </div>

      {generate.data ? (
        <div className="card bw-mt">
          <div className="card-h">
            <h3>生成结果</h3>
            <span className="r">
              <Badge tone={generate.data.blocked ? "bad" : "ok"} dot>
                {generate.data.status}
                {generate.data.biz_no ? ` · ${generate.data.biz_no}` : ""}
              </Badge>
            </span>
          </div>
          <div className="card-b">
            {generate.data.blocked ? (
              <div className="banner bad">
                <Info size={15} aria-hidden="true" />
                <span>
                  <b>门禁阻断：</b>
                  {(verdict?.reasons ?? []).join("；") || "存在未通过断言"}
                </span>
              </div>
            ) : (
              <div className="banner ok">
                <Info size={15} aria-hidden="true" />
                <span>
                  {verdict?.watermark == null
                    ? "门禁通过，检查零失败，审查通过（风险水印已摘除）。"
                    : `门禁通过但带风险水印：${verdict.watermark}`}
                </span>
              </div>
            )}
            {l4 ? (
              <div className="banner info bw-mt-sm">
                <Info size={15} aria-hidden="true" />
                <span>
                  <b>语义审查（提示级，不计入门禁）：</b>
                  参与卡 {l4.participants.length} 张 ·
                  裁决 {Object.entries(l4.counts).map(([k, v]) => `${k} ${v}`).join(" / ") || "—"} ·
                  输入缺席 {l4.input_missing.length || 0} 项
                  {l4.issues.length > 0 ? ` · ${l4.issues.length} 条建议` : ""}
                </span>
              </div>
            ) : null}
            <MetricStrip>
              <MetricCell
                label="断言通过率"
                value={formatPercent(verdict?.metrics?.assertion_pass_rate ?? null)}
              />
              <MetricCell
                label="必须通过项"
                value={verdict?.assertion_counts?.D0 ?? "—"}
              />
              <MetricCell label="D1" value={verdict?.assertion_counts?.D1 ?? "—"} />
              <MetricCell
                label="人工编辑占比"
                value={formatPercent(verdict?.metrics?.manual_edit_ratio ?? null)}
              />
              <MetricCell
                label="耗时"
                value={
                  verdict?.metrics ? `${(verdict.metrics.latency_ms / 1000).toFixed(1)}s` : "—"
                }
              />
            </MetricStrip>
            <p className="bw-muted">
              文件导出（分册/页码/CA 签章位）由导出服务承担，尚未接入；本页不提供下载按钮。
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}
