"use client";

import { Bell, Plus, Trash2 } from "lucide-react";

import type { NotificationConfig } from "../types";

const TRIGGER_OPTIONS: { value: NotificationConfig["trigger"]; label: string }[] = [
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

export function NotificationsConfigPanel({ notifications, onUpdate }: NotificationsConfigPanelProps) {
  const addNotification = () => {
    onUpdate([...notifications, { trigger: "on_start", targets: "", message: "" }]);
  };

  const removeNotification = (idx: number) => {
    onUpdate(notifications.filter((_, i) => i !== idx));
  };

  const updateNotification = (idx: number, partial: Partial<NotificationConfig>) => {
    onUpdate(notifications.map((n, i) => (i === idx ? { ...n, ...partial } : n)));
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
          <Bell className="h-3 w-3" />
          通知
        </label>
        <button
          type="button"
          onClick={addNotification}
          className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:text-foreground border border-border rounded-md hover:bg-muted/50 transition-colors"
        >
          <Plus className="h-3 w-3" />
          添加
        </button>
      </div>

      {notifications.length === 0 && (
        <p className="text-[10px] text-muted-foreground/60">无通知配置</p>
      )}

      {notifications.map((notif, idx) => (
        <div key={idx} className="rounded-lg border border-border bg-muted/20 p-2.5 space-y-2">
          <div className="flex items-center justify-between">
            <select
              value={notif.trigger}
              onChange={(e) => updateNotification(idx, { trigger: e.target.value as NotificationConfig["trigger"] })}
              className="text-[10px] font-medium px-2 py-1 rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary/20"
            >
              {TRIGGER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => removeNotification(idx)}
              className="p-1 text-muted-foreground/40 hover:text-red-500 transition-colors"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
          <input
            type="text"
            value={notif.targets ?? ""}
            onChange={(e) => updateNotification(idx, { targets: e.target.value || undefined })}
            placeholder="通知对象（留空=全体成员）"
            className="w-full px-2 py-1 text-[11px] border border-border rounded-md bg-background focus:outline-none focus:ring-1 focus:ring-primary/20"
          />
          <textarea
            value={notif.message ?? ""}
            onChange={(e) => updateNotification(idx, { message: e.target.value || undefined })}
            placeholder="通知消息"
            rows={1}
            className="w-full px-2 py-1 text-[11px] border border-border rounded-md bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary/20"
          />
        </div>
      ))}
    </div>
  );
}
