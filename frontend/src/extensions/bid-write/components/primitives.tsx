"use client";

/**
 * bid-write 展示基元。全部复用 bid-review 的 `.brx` chrome/card/tbl/btn/seg
 * 视觉语言；本文件只补写作模块需要的徽章、指标带、空态与浮层，不改审查模块。
 */

import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  X,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect } from "react";

import { cn } from "@/lib/utils";

export type Tone = "ok" | "warn" | "bad" | "gray" | "info" | "d1" | "d2" | "d3";

const TONE_CLASS: Record<Tone, string> = {
  ok: "b-ok",
  warn: "b-warn",
  bad: "b-d0",
  gray: "b-gray",
  info: "b-info",
  d1: "b-d1",
  d2: "b-d2",
  d3: "b-d3",
};

export function Badge({
  tone = "gray",
  children,
  dot = false,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("badge", TONE_CLASS[tone], className)}>
      {dot ? <i aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function MetricStrip({ children }: { children: ReactNode }) {
  return <div className="metric-strip">{children}</div>;
}

export function MetricCell({
  label,
  value,
  suffix,
  tone,
  accent,
}: {
  label: ReactNode;
  value: ReactNode;
  suffix?: ReactNode;
  tone?: "warn" | "err" | "ok";
  accent?: boolean;
}) {
  return (
    <div
      className={cn(
        "metric-cell",
        tone === "warn" && "warn",
        tone === "err" && "err",
        tone === "ok" && "ok",
        accent && "accent",
      )}
    >
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value}
        {suffix ? <small>{suffix}</small> : null}
      </div>
    </div>
  );
}

export function PageHead({
  icon: Icon,
  title,
  subtitle,
  actions,
}: {
  icon: LucideIcon;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="ph-icon">
        <Icon size={18} aria-hidden="true" />
      </div>
      <div className="ph-txt">
        <h2>{title}</h2>
        {subtitle ? <div className="ph-sub">{subtitle}</div> : null}
      </div>
      {actions ? <div className="ph-actions">{actions}</div> : null}
    </div>
  );
}

export function CardHead({
  title,
  sub,
  actions,
}: {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="card-h">
      <h3>{title}</h3>
      {sub ? <span className="hd-sub">{sub}</span> : null}
      {actions ? <span className="r">{actions}</span> : null}
    </div>
  );
}

export function EmptyState({
  icon: Icon = AlertCircle,
  title,
  description,
  action,
}: {
  icon?: LucideIcon;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="bw-empty">
      <span className="bw-empty-ic">
        <Icon size={22} aria-hidden="true" />
      </span>
      <div>
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
        {action ? <div className="bw-empty-actions">{action}</div> : null}
      </div>
    </div>
  );
}

export function LoadingBlock({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="bw-loading" role="status">
      <Loader2 size={16} className="bw-spin" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorBlock({
  error,
  onRetry,
}: {
  error: Error | null;
  onRetry?: () => void;
}) {
  return (
    <div className="bw-error" role="alert">
      <AlertCircle size={16} aria-hidden="true" />
      <span>{error?.message ?? "请求失败"}</span>
      {onRetry ? (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  const safe = Math.max(0, Math.min(100, value));
  return (
    <div
      className="prog"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(safe)}
    >
      <i style={{ width: `${safe}%` }} />
    </div>
  );
}

export function StageDots({ status }: { status: string }) {
  const stage =
    status === "matrix_ready"
      ? 6
      : status === "extracting"
        ? 3
        : status === "parsing"
          ? 2
          : status === "failed"
            ? 1
            : 1;
  return (
    <span className="stage-dots" aria-label={`阶段 ${stage}/6`}>
      {Array.from({ length: 6 }, (_, index) => (
        <i
          key={index}
          className={
            index < stage - 1 ? "done" : index === stage - 1 ? "cur" : undefined
          }
        />
      ))}
    </span>
  );
}

export function Overlay({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
  variant = "drawer",
  size = "normal",
}: {
  open: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  variant?: "drawer" | "modal";
  size?: "normal" | "wide";
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={cn(
          variant === "drawer" ? "drawer" : "modal",
          size === "wide" && "bw-wide",
        )}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
      >
        <div className="ov-hd">
          <b>{title}</b>
          {subtitle ? <span className="hd-sub">{subtitle}</span> : null}
          <button
            type="button"
            className="xbtn"
            onClick={onClose}
            aria-label="关闭"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="ov-bd">{children}</div>
        {footer ? <div className="ov-ft">{footer}</div> : null}
      </div>
    </div>
  );
}

export function GateVerdict({
  state,
}: {
  state: "blocked" | "clean" | "unrun";
}) {
  if (state === "blocked") {
    return (
      <Badge tone="bad" dot>
        导出阻断
      </Badge>
    );
  }
  if (state === "clean") {
    return (
      <Badge tone="ok" dot>
        可导出
      </Badge>
    );
  }
  return <Badge tone="gray">未执行断言</Badge>;
}

export function CheckLine({ children }: { children: ReactNode }) {
  return (
    <span className="bw-check-line">
      <CheckCircle2 size={14} aria-hidden="true" />
      {children}
    </span>
  );
}
