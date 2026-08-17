"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Check,
  ExternalLink,
  Cpu,
  ShieldAlert,
  Activity,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

// ── API (from NotificationFeed) ──

interface NotificationItem {
  id: string;
  user_id: string;
  type: string;
  title: string;
  body?: string;
  project_id?: string;
  link?: string;
  is_read: boolean;
  created_at?: string;
}

interface NotificationListResponse {
  notifications: NotificationItem[];
  total: number;
  unread_count: number;
}

const BASE = process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? "";

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = /(?:^|;\s*)csrf_token=([^;]*)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

async function fetchNotifications(page = 0): Promise<NotificationListResponse> {
  const res = await fetch(
    `${BASE}/api/extensions/dashboard/notifications?skip=${page * 20}&limit=20`,
    { credentials: "include" },
  );
  if (!res.ok) throw new Error("Failed to fetch notifications");
  return res.json();
}

async function markRead(id: string): Promise<void> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(
    `${BASE}/api/extensions/dashboard/notifications/${id}/read`,
    { method: "PATCH", credentials: "include", headers },
  );
  if (!res.ok) throw new Error("Failed to mark as read");
}

async function markAllRead(): Promise<void> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(
    `${BASE}/api/extensions/dashboard/notifications/read-all`,
    { method: "POST", credentials: "include", headers },
  );
  if (!res.ok) throw new Error("Failed to mark all as read");
}

function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMin = Math.floor((now.getTime() - date.getTime()) / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}天前`;
  return date.toLocaleDateString();
}

// ── Category theme (reference LogConsole pattern) ──

function getCategoryTheme(type: string): {
  icon: LucideIcon;
  border: string;
  accent: string;
} {
  if (type === "phase_start" || type === "workflow_complete") {
    return {
      icon: Activity,
      border: "border-purple-500/20 bg-purple-500/5 hover:border-purple-500/40",
      accent: "text-purple-500",
    };
  }
  if (type === "deadline" || type === "review_pending") {
    return {
      icon: ShieldAlert,
      border: "border-red-500/20 bg-red-500/5 hover:border-red-500/40",
      accent: "text-red-500",
    };
  }
  return {
    icon: Cpu,
    border: "border-blue-500/20 bg-blue-500/5 hover:border-blue-500/40",
    accent: "text-blue-500",
  };
}

export function LogPanel() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => fetchNotifications(0),
    staleTime: 30_000,
  });

  const readMutation = useMutation({
    mutationFn: markRead,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const readAllMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unreadCount = data?.unread_count ?? 0;
  const notifications = data?.notifications ?? [];

  return (
    <div className="db-card relative flex h-full flex-col overflow-hidden rounded-xl p-4 md:p-5">
      <div className="absolute top-0 left-0 h-2 w-2 bg-[var(--db-border-color)]" />

      <div className="mb-4 flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3">
        <div className="flex items-center gap-2">
          <div className="relative rounded-md border border-blue-500/20 bg-blue-500/10 p-1.5 text-blue-500">
            <Bell className="h-4 w-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 h-2.5 w-2.5 animate-ping rounded-full bg-red-500 ring-2 ring-white" />
            )}
          </div>
          <h2 className="db-text-primary font-cyber text-sm font-bold tracking-wider uppercase">
            消息通知{" "}
            <span className="text-xs font-normal text-slate-500">
              System Logs
            </span>
          </h2>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {unreadCount > 0 && (
            <span className="font-cyber animate-pulse rounded border border-red-500/20 bg-red-500/10 px-1.5 py-0.5 text-[10px] font-bold text-red-500">
              {unreadCount}条未读
            </span>
          )}
          <button
            onClick={() => readAllMutation.mutate()}
            disabled={readAllMutation.isPending || unreadCount === 0}
            className="cursor-pointer text-xs text-blue-600 hover:text-blue-500 hover:underline disabled:opacity-40"
          >
            {readAllMutation.isPending ? "处理中..." : "全部已读"}
          </button>
        </div>
      </div>

      <div className="flex max-h-[320px] flex-1 flex-col gap-2.5 overflow-y-auto pr-1.5">
        {isLoading ? (
          <div className="space-y-2.5">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="animate-pulse rounded-lg border border-[var(--db-border-color-muted)] bg-slate-400/5 p-3"
              >
                <div className="mb-2 h-3.5 w-3/4 rounded bg-slate-200" />
                <div className="h-3 w-1/2 rounded bg-slate-100" />
              </div>
            ))}
          </div>
        ) : notifications.length === 0 ? (
          <div className="font-cyber py-10 text-center text-xs text-slate-500 italic">
            &gt; LOG STREAM CLEARED // ZERO RECORDS RECORDED
          </div>
        ) : (
          notifications.map((notif) => {
            const theme = getCategoryTheme(notif.type);
            const Icon = theme.icon;
            return (
              <div
                key={notif.id}
                className={`rounded-lg border p-3 transition-all ${theme.border} ${notif.is_read ? "border-transparent bg-slate-400/5" : "border-blue-500/30 bg-slate-400/10"} group flex flex-col gap-1.5 select-none`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <Icon className={`h-4 w-4 ${theme.accent}`} />
                    <h4
                      className={`truncate text-xs font-semibold ${notif.is_read ? "font-normal text-slate-500" : "db-text-primary"}`}
                    >
                      {notif.title}
                    </h4>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
                    {!notif.is_read && (
                      <button
                        onClick={() => readMutation.mutate(notif.id)}
                        className="cursor-pointer rounded border border-[var(--db-border-color)] bg-[var(--db-bg-tertiary)] p-1 text-slate-500 transition-all hover:border-blue-500/30 hover:text-blue-500"
                        title="标记为已读"
                      >
                        <Check className="h-3 w-3" />
                      </button>
                    )}
                    {notif.link && (
                      <Link
                        href={notif.link}
                        className="cursor-pointer rounded border border-[var(--db-border-color)] bg-[var(--db-bg-tertiary)] p-1 text-slate-500 transition-all hover:text-blue-500"
                        title="查看详情"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </Link>
                    )}
                  </div>
                </div>
                {notif.body && (
                  <p className="px-6 text-[11px] leading-relaxed text-slate-500">
                    {notif.body}
                  </p>
                )}
                <div className="font-cyber mt-0.5 flex items-center justify-between px-6 text-[9px] text-slate-500">
                  <span>{formatTimeAgo(notif.created_at)}</span>
                  <div className="flex items-center gap-2">
                    <span className="capitalize">{notif.type}</span>
                    {!notif.is_read && (
                      <span className="ml-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
