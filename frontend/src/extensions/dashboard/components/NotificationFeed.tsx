"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  BellOff,
  Check,
  ExternalLink,
  Rocket,
  SearchCheck,
  CheckCircle2,
  PartyPopper,
  AlarmClock,
  MessageCircle,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

// ── API ──

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
  const res = await fetch(`${BASE}/api/extensions/dashboard/notifications?skip=${page * 20}&limit=20`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch notifications");
  return res.json();
}

async function markRead(id: string): Promise<void> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(`${BASE}/api/extensions/dashboard/notifications/${id}/read`, {
    method: "PATCH",
    credentials: "include",
    headers,
  });
  if (!res.ok) throw new Error("Failed to mark as read");
}

async function markAllRead(): Promise<void> {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(`${BASE}/api/extensions/dashboard/notifications/read-all`, {
    method: "POST",
    credentials: "include",
    headers,
  });
  if (!res.ok) throw new Error("Failed to mark all as read");
}

// ── Notification type config ──

const TYPE_CONFIG: Record<string, { icon: LucideIcon; bg: string; text: string }> = {
  phase_start: { icon: Rocket, bg: "bg-blue-50", text: "text-blue-600" },
  review_pending: { icon: SearchCheck, bg: "bg-amber-50", text: "text-amber-600" },
  review_complete: { icon: CheckCircle2, bg: "bg-emerald-50", text: "text-emerald-600" },
  workflow_complete: { icon: PartyPopper, bg: "bg-violet-50", text: "text-violet-600" },
  deadline: { icon: AlarmClock, bg: "bg-rose-50", text: "text-rose-600" },
  mention: { icon: MessageCircle, bg: "bg-sky-50", text: "text-sky-600" },
};

function getTypeConfig(type: string) {
  return TYPE_CONFIG[type] || { icon: Bell, bg: "bg-gray-50", text: "text-gray-600" };
}

function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}天前`;
  return date.toLocaleDateString();
}

// ── NotificationFeed component ──

export function NotificationFeed() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => fetchNotifications(0),
    staleTime: 30_000,
  });

  const readMutation = useMutation({
    mutationFn: markRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (err) => console.error("Mark read failed:", err),
  });

  const readAllMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (err) => console.error("Mark all read failed:", err),
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex gap-3">
            <div className="h-9 w-9 rounded-lg bg-muted animate-pulse shrink-0" />
            <div className="flex-1 space-y-1.5 py-1">
              <div className="h-3.5 rounded bg-muted animate-pulse w-3/4" />
              <div className="h-3 rounded bg-muted animate-pulse w-1/2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!data || data.notifications.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <BellOff className="h-8 w-8 mx-auto mb-2 opacity-40" />
        <p className="text-sm">暂无通知</p>
        <p className="text-xs text-muted-foreground/60 mt-1">有新消息时会在这里提醒你</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {data.unread_count > 0 && (
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-foreground">{data.unread_count} 条未读</span>
          <button
            onClick={() => readAllMutation.mutate()}
            disabled={readAllMutation.isPending}
            className="text-xs text-primary hover:underline disabled:opacity-50"
          >
            {readAllMutation.isPending ? "处理中..." : "全部已读"}
          </button>
        </div>
      )}
      <div className="space-y-2">
        {data.notifications.map((n) => {
          const config = getTypeConfig(n.type);
          const Icon = config.icon;
          return (
            <div
              key={n.id}
              className={`group relative flex gap-2 rounded-lg px-2 py-2 transition-colors ${
                n.is_read
                  ? "bg-muted/30"
                  : "bg-primary/5 ring-1 ring-primary/20"
              }`}
            >
              {/* Type icon with colored background */}
              <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${config.bg}`}>
                <Icon className={`h-3.5 w-3.5 ${config.text}`} />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className={`text-sm leading-snug truncate ${n.is_read ? "text-muted-foreground" : "text-foreground font-medium"}`}>
                  {n.title}
                </p>
                {n.body && (
                  <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">{n.body}</p>
                )}
                <p className="text-[11px] text-muted-foreground/60 mt-0.5">{formatTimeAgo(n.created_at)}</p>
              </div>

              {/* Actions — icon only */}
              <div className="flex items-center gap-0.5 shrink-0 self-center">
                {!n.is_read && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      readMutation.mutate(n.id);
                    }}
                    disabled={readMutation.isPending}
                    className="p-1.5 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors disabled:opacity-50"
                    title="标为已读"
                  >
                    <Check className="h-3.5 w-3.5" />
                  </button>
                )}
                {n.link && (
                  <Link
                    href={n.link}
                    className="p-1.5 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                    title="查看详情"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                )}
              </div>

              {/* Unread dot indicator */}
              {!n.is_read && (
                <span className="absolute top-2.5 right-2.5 h-1.5 w-1.5 rounded-full bg-red-500" />
              )}
            </div>
          );
        })}
      </div>
      {data.total > 20 && (
        <button
          className="text-xs text-center text-primary hover:underline w-full pt-2"
        >
          查看全部通知 ({data.total} 条)
        </button>
      )}
    </div>
  );
}

// ── NotificationBadge (for header/navbar) ──

export function NotificationBadge() {
  const { data } = useQuery({
    queryKey: ["notifications", "badge"],
    queryFn: () => fetchNotifications(0),
    staleTime: 60_000,
  });

  const count = data?.unread_count ?? 0;

  return (
    <Link href="/dashboard" className="relative p-2 rounded-md hover:bg-accent">
      <Bell className="h-5 w-5" />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
          {count > 9 ? "9+" : count}
        </span>
      )}
    </Link>
  );
}
