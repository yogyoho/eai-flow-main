"use client";

import { Bell, Check, ExternalLink, Cpu, ShieldAlert, Activity, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

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

const BASE = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "";

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = /(?:^|;\s*)csrf_token=([^;]*)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

async function fetchNotifications(page = 0): Promise<NotificationListResponse> {
  const res = await fetch(`${BASE}/api/extensions/dashboard/notifications?skip=${page * 20}&limit=20`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch notifications");
  return res.json();
}

async function markRead(id: string): Promise<void> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(`${BASE}/api/extensions/dashboard/notifications/${id}/read`, { method: "PATCH", credentials: "include", headers });
  if (!res.ok) throw new Error("Failed to mark as read");
}

async function markAllRead(): Promise<void> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(`${BASE}/api/extensions/dashboard/notifications/read-all`, { method: "POST", credentials: "include", headers });
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

function getCategoryTheme(type: string): { icon: LucideIcon; border: string; accent: string } {
  if (type === "phase_start" || type === "workflow_complete") {
    return { icon: Activity, border: "border-purple-500/20 bg-purple-500/5 hover:border-purple-500/40", accent: "text-purple-500" };
  }
  if (type === "deadline" || type === "review_pending") {
    return { icon: ShieldAlert, border: "border-red-500/20 bg-red-500/5 hover:border-red-500/40", accent: "text-red-500" };
  }
  return { icon: Cpu, border: "border-blue-500/20 bg-blue-500/5 hover:border-blue-500/40", accent: "text-blue-500" };
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const readAllMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unreadCount = data?.unread_count ?? 0;
  const notifications = data?.notifications ?? [];

  return (
    <div className="db-card rounded-xl p-4 md:p-5 relative flex flex-col h-full overflow-hidden">
      <div className="absolute top-0 left-0 w-2 h-2 bg-[var(--db-border-color)]" />

      <div className="flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 text-blue-500 rounded-md relative">
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-red-500 ring-2 ring-white animate-ping" />
            )}
          </div>
          <h2 className="text-sm font-bold tracking-wider db-text-primary uppercase font-cyber">
            消息通知 <span className="text-xs font-normal text-slate-500">System Logs</span>
          </h2>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {unreadCount > 0 && (
            <span className="font-cyber font-bold text-red-500 animate-pulse bg-red-500/10 border border-red-500/20 px-1.5 py-0.5 rounded text-[10px]">{unreadCount}条未读</span>
          )}
          <button
            onClick={() => readAllMutation.mutate()}
            disabled={readAllMutation.isPending || unreadCount === 0}
            className="text-xs text-blue-600 hover:text-blue-500 hover:underline cursor-pointer disabled:opacity-40">
            {readAllMutation.isPending ? "处理中..." : "全部已读"}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[320px] pr-1.5 flex flex-col gap-2.5">
        {isLoading ? (
          <div className="space-y-2.5">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="p-3 rounded-lg border border-[var(--db-border-color-muted)] bg-slate-400/5 animate-pulse">
                <div className="h-3.5 bg-slate-200 rounded w-3/4 mb-2" />
                <div className="h-3 bg-slate-100 rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : notifications.length === 0 ? (
          <div className="text-center py-10 text-slate-500 text-xs italic font-cyber">
            &gt; LOG STREAM CLEARED // ZERO RECORDS RECORDED
          </div>
        ) : (
          notifications.map(notif => {
            const theme = getCategoryTheme(notif.type);
            const Icon = theme.icon;
            return (
              <div key={notif.id}
                className={`p-3 rounded-lg border transition-all ${theme.border} ${notif.is_read ? "bg-slate-400/5 border-transparent" : "bg-slate-400/10 border-blue-500/30"} flex flex-col gap-1.5 group select-none`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <Icon className={`w-4 h-4 ${theme.accent}`} />
                    <h4 className={`text-xs font-semibold truncate ${notif.is_read ? "text-slate-500 font-normal" : "db-text-primary"}`}>
                      {notif.title}
                    </h4>
                  </div>
                  <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    {!notif.is_read && (
                      <button onClick={() => readMutation.mutate(notif.id)}
                        className="p-1 rounded bg-[var(--db-bg-tertiary)] border border-[var(--db-border-color)] text-slate-500 hover:text-blue-500 hover:border-blue-500/30 transition-all cursor-pointer"
                        title="标记为已读">
                        <Check className="w-3 h-3" />
                      </button>
                    )}
                    {notif.link && (
                      <Link href={notif.link}
                        className="p-1 rounded bg-[var(--db-bg-tertiary)] border border-[var(--db-border-color)] text-slate-500 hover:text-blue-500 transition-all cursor-pointer"
                        title="查看详情">
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                    )}
                  </div>
                </div>
                {notif.body && (
                  <p className="text-[11px] text-slate-500 px-6 leading-relaxed">{notif.body}</p>
                )}
                <div className="flex items-center justify-between px-6 text-[9px] font-cyber text-slate-500 mt-0.5">
                  <span>{formatTimeAgo(notif.created_at)}</span>
                  <div className="flex items-center gap-2">
                    <span className="capitalize">{notif.type}</span>
                    {!notif.is_read && (
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse ml-1 inline-block" />
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
