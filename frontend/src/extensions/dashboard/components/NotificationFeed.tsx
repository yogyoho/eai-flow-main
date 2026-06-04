"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  BellOff,
  Check,
  Eye,
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

async function fetchNotifications(page = 0): Promise<NotificationListResponse> {
  const res = await fetch(`${BASE}/api/extensions/dashboard/notifications?skip=${page * 20}&limit=20`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to fetch notifications");
  return res.json();
}

async function markRead(id: string): Promise<void> {
  await fetch(`${BASE}/api/extensions/dashboard/notifications/${id}/read`, {
    method: "PATCH",
    credentials: "include",
  });
}

async function markAllRead(): Promise<void> {
  await fetch(`${BASE}/api/extensions/dashboard/notifications/read-all`, {
    method: "POST",
    credentials: "include",
  });
}

// ── Notification type icons (Lucide, no emoji) ──

const TYPE_ICONS: Record<string, LucideIcon> = {
  phase_start: Rocket,
  review_pending: SearchCheck,
  review_complete: CheckCircle2,
  workflow_complete: PartyPopper,
  deadline: AlarmClock,
  mention: MessageCircle,
};

function getTypeIcon(type: string): LucideIcon {
  return TYPE_ICONS[type] || Bell;
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
  });

  const readAllMutation = useMutation({
    mutationFn: markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-14 rounded-lg bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  if (!data || data.notifications.length === 0) {
    return (
      <div className="text-center py-4 text-muted-foreground">
        <BellOff className="h-6 w-6 mx-auto mb-1 opacity-50" />
        <p className="text-sm">暂无通知</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {data.unread_count > 0 && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground">{data.unread_count} 条未读</span>
          <button
            onClick={() => readAllMutation.mutate()}
            className="text-xs text-primary hover:underline"
          >
            全部标为已读
          </button>
        </div>
      )}
      {data.notifications.map((n) => {
        const Icon = getTypeIcon(n.type);
        return (
          <div
            key={n.id}
            className={`flex items-start gap-2.5 rounded-md p-2.5 text-sm transition-colors ${
              n.is_read
                ? "text-muted-foreground"
                : "border-l-2 border-primary bg-accent/30"
            }`}
          >
            <Icon className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{n.title}</p>
              {n.body && (
                <p className="text-xs text-muted-foreground line-clamp-2">{n.body}</p>
              )}
              <p className="text-xs text-muted-foreground mt-0.5">{formatTimeAgo(n.created_at)}</p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {!n.is_read && (
                <button
                  onClick={() => readMutation.mutate(n.id)}
                  className="p-1.5 rounded hover:bg-accent"
                  title="标为已读"
                >
                  <Check className="h-4 w-4 text-muted-foreground" />
                </button>
              )}
              {n.link && (
                <Link
                  href={n.link}
                  className="p-1.5 rounded hover:bg-accent"
                  title="查看"
                >
                  <Eye className="h-4 w-4 text-muted-foreground" />
                </Link>
              )}
            </div>
          </div>
        );
      })}
      {data.total > 20 && (
        <button
          className="text-xs text-center text-primary hover:underline w-full mt-2"
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
