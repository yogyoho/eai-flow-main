"use client";

import {
  Archive,
  Ban,
  ChevronDown,
  CircleCheck,
  CircleDashed,
  CircleX,
  ClipboardCheck,
  Clock,
  Database,
  History,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import { cn } from "@/lib/utils";

/** 状态 → 用户语徽章（文案红线映射表；图标一律 lucide 线性件，禁 emoji）。 */
const STATE_MAP: Record<string, { label: string; cls: string; icon: React.ReactNode }> = {
  stored: {
    label: "未翻译",
    cls: "border-dashed text-muted-foreground",
    icon: <CircleDashed className="h-3 w-3" />,
  },
  pending: {
    label: "排队中",
    cls: "text-muted-foreground",
    icon: <Clock className="h-3 w-3" />,
  },
  running: {
    label: "翻译中",
    cls: "text-info",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
  },
  check_failed: {
    label: "机检未过",
    cls: "text-amber-600",
    icon: <ShieldAlert className="h-3 w-3" />,
  },
  retrying: {
    label: "重试中",
    cls: "text-amber-600",
    icon: <RefreshCw className="h-3 w-3 animate-spin" />,
  },
  exceeded: {
    label: "待复核",
    cls: "text-amber-600 font-medium",
    icon: <ClipboardCheck className="h-3 w-3" />,
  },
  indexed: {
    label: "入库中",
    cls: "text-info",
    icon: <Database className="h-3 w-3" />,
  },
  delivered: {
    label: "已交付",
    cls: "text-success font-medium",
    icon: <CircleCheck className="h-3 w-3" />,
  },
  failed: {
    label: "失败",
    cls: "text-destructive",
    icon: <CircleX className="h-3 w-3" />,
  },
  archived: {
    label: "已归档",
    cls: "text-muted-foreground",
    icon: <Archive className="h-3 w-3" />,
  },
  cancelled: {
    label: "已取消",
    cls: "text-muted-foreground",
    icon: <Ban className="h-3 w-3" />,
  },
  superseded: {
    label: "已替代",
    cls: "text-muted-foreground",
    icon: <History className="h-3 w-3" />,
  },
};

export function StateBadge({ state, progress }: { state: string; progress?: number }) {
  const it = STATE_MAP[state] ?? { label: state, cls: "", icon: null };
  const label =
    state === "running" && progress ? `翻译中 ${progress}%` : it.label;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs",
        it.cls,
      )}
    >
      {it.icon}
      {label}
    </span>
  );
}
