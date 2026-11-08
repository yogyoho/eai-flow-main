"use client";

/**
 * 投标方案审查共享基元(ui-spec §1 四件:SplitPane/SegmentedToggle/GateMetricsRow/
 * GroupCard,另附 §1.1 左列行配方 SplitRow)——配方逐条照抄
 * docs/designs/2026-10-29-bid-review-ui-spec.md §1,勿自创样式。
 * 零新依赖;不进全局 ui/(若后续模块复用再晋升,§1 原文口径)。
 * 语义豁免:SegmentedToggle 为 ui-style-spec §7 之外的获准变体(来源=设计文档 §4.9
 * 钦定 seg 形态,勿向其他页面扩散)。深档状态色从仓库既有 bracket-var 形态
 * `text-[var(--error-700)]`(translation 模块先例;仓库无 `text-(--…)` 括号形态用法,
 * Grep 2026-10-29)。token 暗色自动反转(globals.css :416-434),不手写 dark: 数值。
 */

import type { ReactNode } from "react";

import {
  Pill,
  type PillTone,
} from "@/extensions/contract-price/components/ui/bits";
import { cn } from "@/lib/utils";

// ── §2 状态 Pill 词汇映射(全视图统一)──────────────────────────────────
// spec §2 配方:severity fatal→error / major→warn(文字深档由 Pill warn 档承担)/
// minor→info / info→muted;verdict FAIL→error / PASS→success / UNKNOWN·SKIP·false_positive→gray / ERROR→error
// (P1-β批三 2026-11-07:引擎五值域 C-08,后端 engine/verdicts.py 唯一真相);
// 任务状态词汇=后端 models.py:30(created|parsing|extracting|awaiting_confirm|
// running|done|failed;勘误 2026-10-29:终态成功=done,completed 仅兼容别名)。
// 与 TasksView.statusPill 同源(Task 12 本地版不动);三视图共用故随基元落此。

export function taskStatusPill(status: string): {
  tone: PillTone;
  label: string;
} {
  switch (status) {
    case "done":
    case "completed":
      return { tone: "success", label: "已完成" };
    case "failed":
      return { tone: "error", label: "失败" };
    case "running":
      return { tone: "info", label: "进行中" };
    case "parsing":
      return { tone: "info", label: "解析中" };
    case "extracting":
      return { tone: "info", label: "基准提取中" };
    case "awaiting_confirm":
      return { tone: "warn", label: "待确认" };
    default:
      return {
        tone: "gray",
        label: status === "created" || status === "pending" ? "已创建" : status,
      };
  }
}

// ── 审查用时(Plan7 T2 自 TasksView 上移共享:ResultsView 页头五元组同用)────
/** 审查用时=done_at−created_at(客户端算,spec §3 s1;Plan4 T3)。秒/分/时三段;
 * null/非法/负值一律 —(不冒充)。 */
export function formatDuration(
  createdIso: string | null,
  doneIso: string | null,
): string {
  if (!createdIso || !doneIso) return "—";
  const ms = new Date(doneIso).getTime() - new Date(createdIso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export function severityPill(severity: string): {
  tone: PillTone;
  label: string;
} {
  switch (severity) {
    case "fatal":
      return { tone: "error", label: "致命" };
    case "major":
      return { tone: "warn", label: "主要" };
    case "minor":
      return { tone: "info", label: "次要" };
    case "info":
      return { tone: "gray", label: "提示" };
    default:
      return { tone: "gray", label: severity || "未知" };
  }
}

export function verdictPill(verdict: string): {
  tone: PillTone;
  label: string;
} {
  switch (verdict) {
    case "FAIL":
      return { tone: "error", label: "违规" };
    case "PASS":
      return { tone: "success", label: "通过" };
    case "UNKNOWN":
      return { tone: "gray", label: "待人工" };
    case "ERROR":
      return { tone: "error", label: "执行异常" };
    case "SKIP":
      return { tone: "gray", label: "跳过" };
    case "false_positive":
      return { tone: "gray", label: "误报" };
    default:
      return { tone: "gray", label: verdict || "未知" };
  }
}

// ── 门禁四态 pill(P1-β批五 T2,规格 §5.7.2;A-β5-⑥)──────────────────────
// 判定键=后端 worker.compute_gate_status 派生( summarize_issues additive 键
// gate_status,双 API 面共享);四态中文文案与后端 routers._GATE_TXT 逐字同源。
// 分级:红 error(NOT_SUBMITTABLE/PENDING_HUMAN)/黄 warn(CONDITIONAL)/
// 绿 success(SUBMITTABLE)。need_human 旗标等既有待人工口径展示零改动(旗标
// 不参与 gate 判定,同后端口径)。
export function gateStatusPill(gateStatus: string): {
  tone: PillTone;
  label: string;
} {
  switch (gateStatus) {
    case "NOT_SUBMITTABLE":
      return { tone: "error", label: "存在否决性风险,不建议提交。" };
    case "PENDING_HUMAN":
      return { tone: "error", label: "关键项无法自动判定,必须人工确认。" };
    case "CONDITIONAL":
      return { tone: "warn", label: "存在需整改项,建议整改后提交。" };
    case "SUBMITTABLE":
      return { tone: "success", label: "未发现否决性风险,可按流程提交。" };
    default:
      return { tone: "gray", label: gateStatus || "未知" };
  }
}

// ── §1.1 SplitPane(split)──────────────────────────────────────────────

/**
 * 264px/1fr 双栏容器:md 以上左右分栏,md 以下单列(列表在上、详情在下,§4 响应式)。
 * 左列列表行用 {@link SplitRow},左列容器 `max-h-[560px] overflow-y-auto` 由调用方套。
 */
export function SplitPane({
  left,
  right,
}: {
  left: ReactNode;
  right: ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-[264px_1fr]">
      <div>{left}</div>
      <div>{right}</div>
    </div>
  );
}

/** §1.1 fam-item 行:hairline 底边 + hover 淡底;选中态 bg-primary/10 + 左缘 2px 主色指示条;
 * 行内计数右对齐 tabular。真 button(可达性,§4)。 */
export function SplitRow({
  selected,
  onClick,
  count,
  children,
}: {
  selected?: boolean;
  onClick: () => void;
  count?: ReactNode;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "border-border hover:bg-muted/50 relative flex w-full cursor-pointer items-center gap-2 border-b px-3 py-2 text-left text-sm transition-colors",
        selected && "bg-primary/10",
      )}
    >
      {selected ? (
        <span
          aria-hidden
          className="bg-primary absolute inset-y-0 left-0 w-0.5"
        />
      ) : null}
      {children}
      {count !== undefined ? (
        <span className="text-muted-foreground ml-auto text-xs tabular-nums">
          {count}
        </span>
      ) : null}
    </button>
  );
}

// ── §1.2 SegmentedToggle(seg)──────────────────────────────────────────

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

/** inline-flex 边框容器 + 非首钮左 hairline;active 淡主底主字 medium;真 button +
 * aria-pressed(§4 可达性)。§7 豁免变体(来源=设计文档,勿扩散)。 */
export function SegmentedToggle<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  disabled,
  className,
}: {
  options: readonly SegmentedOption<T>[];
  value: T;
  /** 只读展示(如工作台顶条 mode 段)可不传。 */
  onChange?: (value: T) => void;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        "border-border bg-card inline-flex overflow-hidden rounded-md border",
        disabled && "pointer-events-none opacity-60",
        className,
      )}
    >
      {options.map((opt, i) => (
        <button
          key={opt.value}
          type="button"
          aria-pressed={value === opt.value}
          disabled={disabled}
          onClick={() => onChange?.(opt.value)}
          className={cn(
            "text-muted-foreground px-3.5 py-[5px] text-sm",
            i > 0 && "border-border border-l",
            value === opt.value && "bg-primary/10 text-primary font-medium",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ── §1.3 GateMetricsRow(gate1-m)───────────────────────────────────────

export interface GateMetric {
  label: string;
  value: number;
  /** 致命>0 → error(深档 #cf1322);=0 → success(深档 #389e0d);其余 default。 */
  tone?: "error" | "success" | "default";
  hint?: string;
}

/** grid 横条指标格:数值 20px 档(text-2xl)semibold tabular;格间 divide-x hairline;
 * `grid-cols-2` 折行(§4)。工作台顶条/报告概览用;任务列表页不用此件(spec §1.3)。
 * 批五(A-β5-⑥):gateStatus 给定 → 卡顶四态判定 pill({@link gateStatusPill},
 * 文案与后端 _GATE_TXT 逐字同源,红/黄/绿分级);缺席(旧 summary 形)零渲染,
 * 既有格展示零改动。 */
export function GateMetricsRow({
  metrics,
  gateStatus,
}: {
  metrics: GateMetric[];
  /** 批五 gate_status 四态派生键(规格 §5.7.2,后端 summarize_issues additive);
   * 可选——旧 summary 无此键,不传即纯既有形态。 */
  gateStatus?: string;
}) {
  const pill = gateStatus ? gateStatusPill(gateStatus) : null;
  return (
    <div className="border-border bg-card overflow-hidden rounded-lg border">
      {pill ? (
        <div className="border-border flex items-center gap-2 border-b px-4 py-2">
          <Pill tone={pill.tone}>{pill.label}</Pill>
        </div>
      ) : null}
      <div className="grid grid-cols-2 divide-x md:grid-cols-4">
        {metrics.map((m) => (
          <div
            key={m.label}
            className="border-border flex items-baseline gap-2 px-4 py-2.5"
          >
            <span
              className={cn(
                "text-2xl font-semibold tabular-nums",
                m.tone === "error" && "text-[var(--error-700)]",
                m.tone === "success" && "text-[var(--success-700)]",
              )}
            >
              {m.value}
            </span>
            <span className="text-muted-foreground text-xs">{m.label}</span>
            {m.hint ? (
              <span className="text-muted-foreground ml-auto text-xs">
                {m.hint}
              </span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── §1.4 GroupCard(layer-card)─────────────────────────────────────────

/** hairline 白卡 p-4 flex-col;可点卡 hover 三件套缺一不可(§6.1:transition-all +
 * hover:border-primary/20 + hover:shadow-md)。规则库分组卡/工作台压缩行两用。 */
export function GroupCard({
  title,
  subtitle,
  count,
  countSuffix,
  description,
  clickable,
  onClick,
  className,
  children,
}: {
  title?: ReactNode;
  /** mono 副标(规则 id 等,text-xs font-mono)。 */
  subtitle?: string;
  count?: ReactNode;
  countSuffix?: string;
  description?: ReactNode;
  clickable?: boolean;
  onClick?: () => void;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div
      onClick={clickable ? onClick : undefined}
      className={cn(
        "border-border bg-card flex flex-col gap-1.5 rounded-lg border p-4",
        clickable &&
          "hover:border-primary/20 cursor-pointer transition-all hover:shadow-md",
        className,
      )}
    >
      {title !== undefined ? (
        <div className="text-foreground text-sm font-semibold">{title}</div>
      ) : null}
      {subtitle ? (
        <div className="text-muted-foreground font-mono text-xs">
          {subtitle}
        </div>
      ) : null}
      {count !== undefined ? (
        <div className="text-foreground text-2xl font-semibold tabular-nums">
          {count}
          {countSuffix ? (
            <small className="text-muted-foreground ml-1 text-xs font-normal">
              {countSuffix}
            </small>
          ) : null}
        </div>
      ) : null}
      {description !== undefined ? (
        <div className="text-muted-foreground text-xs">{description}</div>
      ) : null}
      {children}
    </div>
  );
}
