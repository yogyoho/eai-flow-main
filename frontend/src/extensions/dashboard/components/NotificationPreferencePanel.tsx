"use client";

import { useEffect, useState } from "react";
import { Bell, Clock, Mail, MessageSquare } from "lucide-react";
import { dashboardApi } from "../api";
import type { NotificationPreference, NotificationPreferenceUpdate } from "../types";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

const NOTIFICATION_TYPES: { key: string; label: string }[] = [
  { key: "deadline", label: "截止提醒" },
  { key: "review_pending", label: "审核待处理" },
  { key: "phase_start", label: "阶段开始" },
  { key: "mention", label: "@评论" },
  { key: "assignment", label: "任务分配" },
  { key: "workflow_complete", label: "工作流完成" },
];

export function NotificationPreferencePanel() {
  const [prefs, setPrefs] = useState<NotificationPreference | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    dashboardApi
      .getNotificationPreferences()
      .then(setPrefs)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  async function updatePref<K extends keyof NotificationPreferenceUpdate>(
    key: K,
    value: NotificationPreferenceUpdate[K],
  ) {
    if (!prefs) return;
    setSaving(true);
    try {
      const updated = await dashboardApi.updateNotificationPreferences({ [key]: value });
      setPrefs(updated);
    } catch (err) {
      console.error("Failed to update preference:", err);
    } finally {
      setSaving(false);
    }
  }

  async function toggleType(typeKey: string, enabled: boolean) {
    if (!prefs) return;
    const newSettings = { ...prefs.type_settings, [typeKey]: enabled };
    const updated = await dashboardApi.updateNotificationPreferences({ type_settings: newSettings });
    setPrefs(updated);
  }

  if (loading) {
    return (
      <div className="space-y-3 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-8 bg-muted rounded" />
        ))}
      </div>
    );
  }

  if (!prefs) {
    return <div className="text-sm text-muted-foreground">无法加载通知偏好设置</div>;
  }

  return (
    <div className="space-y-4">
      {/* Channel toggles */}
      <div className="space-y-3">
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">通知渠道</h4>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
            <Label htmlFor="channel-in-app" className="text-sm">
              站内通知
            </Label>
          </div>
          <Switch
            id="channel-in-app"
            checked={prefs.channel_in_app}
            disabled={saving}
            onCheckedChange={(v) => updatePref("channel_in_app", v)}
          />
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-muted-foreground" />
            <Label htmlFor="channel-email" className="text-sm">
              邮件通知
            </Label>
          </div>
          <Switch
            id="channel-email"
            checked={prefs.channel_email}
            disabled={saving}
            onCheckedChange={(v) => updatePref("channel_email", v)}
          />
        </div>
      </div>

      {/* Digest mode */}
      <div className="space-y-2">
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">汇总方式</h4>
        <Select value={prefs.digest_mode} onValueChange={(v) => updatePref("digest_mode", v as "instant" | "daily" | "off")}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="instant">即时推送</SelectItem>
            <SelectItem value="daily">每日汇总</SelectItem>
            <SelectItem value="off">关闭</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Type toggles */}
      <div className="space-y-2">
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">通知类型</h4>
        {NOTIFICATION_TYPES.map(({ key, label }) => (
          <div key={key} className="flex items-center justify-between">
            <Label htmlFor={`type-${key}`} className="text-sm">
              {label}
            </Label>
            <Switch
              id={`type-${key}`}
              checked={prefs.type_settings[key] !== false}
              disabled={saving}
              onCheckedChange={(v) => toggleType(key, v)}
            />
          </div>
        ))}
      </div>

      {/* Deadline remind days */}
      <div className="space-y-2">
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
          <Clock className="h-3 w-3" />
          截止提醒提前天数
        </h4>
        <Select
          value={String(prefs.deadline_remind_days)}
          onValueChange={(v) => updatePref("deadline_remind_days", Number(v))}
        >
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1">提前 1 天</SelectItem>
            <SelectItem value="3">提前 3 天</SelectItem>
            <SelectItem value="5">提前 5 天</SelectItem>
            <SelectItem value="7">提前 7 天</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
