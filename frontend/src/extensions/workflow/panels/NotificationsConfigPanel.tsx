"use client";

import { Bell, Plus, Trash2 } from "lucide-react";

import type { NotificationConfig } from "../types";

const TRIGGER_OPTIONS: {
  value: NotificationConfig["trigger"];
  label: string;
}[] = [
  { value: "on_start", label: "开始时" },
  { value: "on_complete", label: "完成时" },
  { value: "on_error", label: "出错时" },
  { value: "on_review_pending", label: "审核待办时" },
  { value: "on_review_complete", label: "审核完成时" },
];

interface NotificationsConfigPanelProps {
  notifications: NotificationConfig[];
  onUpdate: (notifications: NotificationConfig[]) => void;
}

export function NotificationsConfigPanel({
  notifications,
  onUpdate,
}: NotificationsConfigPanelProps) {
  const addNotification = () => {
    onUpdate([
      ...notifications,
      { trigger: "on_start", targets: "", message: "" },
    ]);
  };

  const removeNotification = (idx: number) => {
    onUpdate(notifications.filter((_, i) => i !== idx));
  };

  const updateNotification = (
    idx: number,
    partial: Partial<NotificationConfig>,
  ) => {
    onUpdate(
      notifications.map((n, i) => (i === idx ? { ...n, ...partial } : n)),
    );
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
          <Bell className="h-3 w-3" />
          通知
        </label>
        <button
          type="button"
          onClick={addNotification}
          className="text-muted-foreground hover:text-foreground border-border hover:bg-muted/50 flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-medium transition-colors"
        >
          <Plus className="h-3 w-3" />
          添加
        </button>
      </div>

      {notifications.length === 0 && (
        <p className="text-muted-foreground/60 text-[10px]">无通知配置</p>
      )}

      {notifications.map((notif, idx) => (
        <div
          key={idx}
          className="border-border bg-muted/20 space-y-2 rounded-lg border p-2.5"
        >
          <div className="flex items-center justify-between">
            <select
              value={notif.trigger}
              onChange={(e) =>
                updateNotification(idx, {
                  trigger: e.target.value as NotificationConfig["trigger"],
                })
              }
              className="border-border bg-background focus:ring-primary/20 rounded-md border px-2 py-1 text-[10px] font-medium focus:ring-1 focus:outline-none"
            >
              {TRIGGER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => removeNotification(idx)}
              className="text-muted-foreground/40 p-1 transition-colors hover:text-red-600 dark:text-red-400"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
          <input
            type="text"
            value={notif.targets ?? ""}
            onChange={(e) =>
              updateNotification(idx, { targets: e.target.value || undefined })
            }
            placeholder="通知对象（留空=全体成员）"
            className="border-border bg-background focus:ring-primary/20 w-full rounded-md border px-2 py-1 text-xs focus:ring-1 focus:outline-none"
          />
          <textarea
            value={notif.message ?? ""}
            onChange={(e) =>
              updateNotification(idx, { message: e.target.value || undefined })
            }
            placeholder="通知消息"
            rows={1}
            className="border-border bg-background focus:ring-primary/20 w-full resize-none rounded-md border px-2 py-1 text-xs focus:ring-1 focus:outline-none"
          />
        </div>
      ))}
    </div>
  );
}
