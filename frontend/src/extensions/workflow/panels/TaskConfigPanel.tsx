"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { StyledCheckbox } from "@/components/ui/styled-checkbox";

import type {
  TaskNodeData,
  ReviewerBinding,
  ReviewMode,
  NotificationConfig,
} from "../types";

import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface TaskConfigPanelProps {
  data: TaskNodeData;
  nodeId?: string;
  onUpdate: (partial: Partial<TaskNodeData>) => void;
  orgDeptCode?: string;
  onOrgBindingChange?: (nodeId: string, deptCode: string | null) => void;
  deptOptions?: { value: string; label: string }[];
}

const REVIEW_MODES: { value: ReviewMode; label: string; desc: string }[] = [
  { value: "all", label: "会签", desc: "所有审核人必须全部通过" },
  { value: "any", label: "或签", desc: "任一审核人通过即可" },
  { value: "ratio", label: "比例签", desc: "通过比例达到阈值即通过" },
  { value: "sequential", label: "顺序签", desc: "按指定顺序逐级审批" },
];

const BINDING_TYPES: { value: ReviewerBinding["type"]; label: string }[] = [
  { value: "role", label: "角色" },
  { value: "position", label: "岗位" },
  { value: "user", label: "用户" },
];

const ROLE_OPTIONS = [
  { value: "leader", label: "组长" },
  { value: "writer", label: "组员" },
  { value: "dept_reviewer", label: "部门审核人" },
  { value: "company_reviewer", label: "公司审核人" },
];

export function TaskConfigPanel({
  data,
  nodeId,
  onUpdate,
  orgDeptCode,
  onOrgBindingChange,
  deptOptions,
}: TaskConfigPanelProps) {
  const isReview = !!data.reviewMode;
  const reviewMode = data.reviewMode ?? "all";
  const reviewers = data.reviewers ?? [];
  const [newType, setNewType] = useState<ReviewerBinding["type"]>("role");
  const [newValue, setNewValue] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newRole, setNewRole] = useState("");

  const addReviewer = () => {
    if (!newValue.trim() || !newLabel.trim()) return;
    onUpdate({
      reviewers: [
        ...reviewers,
        {
          type: newType,
          value: newValue.trim(),
          label: newLabel.trim(),
          required: true,
        },
      ],
    });
    setNewValue("");
    setNewLabel("");
  };

  if (isReview) {
    return (
      <div className="space-y-4 p-4">
        <div className="space-y-2">
          <label className="text-foreground text-xs font-semibold">
            签核模式
          </label>
          <div className="grid grid-cols-2 gap-1.5">
            {REVIEW_MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => onUpdate({ reviewMode: m.value })}
                className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${reviewMode === m.value ? "border-red-300 bg-red-50 font-semibold text-red-700 dark:border-red-700 dark:bg-red-950/40 dark:text-red-300" : "border-border text-muted-foreground hover:border-red-200 dark:border-red-800"}`}
              >
                <div>{m.label}</div>
                <div className="mt-0.5 text-[10px] opacity-60">{m.desc}</div>
              </button>
            ))}
          </div>
        </div>
        {reviewMode === "ratio" && (
          <div className="space-y-2">
            <label className="text-foreground text-xs font-semibold">
              通过阈值: {Math.round((data.ratioThreshold ?? 0.5) * 100)}%
            </label>
            <input
              type="range"
              min={10}
              max={100}
              step={5}
              value={Math.round((data.ratioThreshold ?? 0.5) * 100)}
              onChange={(e) =>
                onUpdate({ ratioThreshold: parseInt(e.target.value) / 100 })
              }
              className="bg-muted h-2 w-full rounded-full accent-red-500"
            />
          </div>
        )}
        <div className="space-y-2">
          <label className="text-foreground text-xs font-semibold">
            审核人绑定
          </label>
          {reviewers.map((r, i) => (
            <div
              key={i}
              className="border-border bg-muted/30 flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs"
            >
              <span className="bg-muted rounded px-1.5 py-0.5 text-[10px] font-medium">
                {BINDING_TYPES.find((b) => b.value === r.type)?.label}
              </span>
              <span className="flex-1 truncate font-medium">{r.label}</span>
              <span className="text-muted-foreground font-mono text-[10px]">
                {r.value}
              </span>
              <button
                type="button"
                onClick={() =>
                  onUpdate({ reviewers: reviewers.filter((_, j) => j !== i) })
                }
                className="p-0.5 hover:text-red-600 dark:text-red-400"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          <div className="border-border space-y-1.5 rounded-lg border border-dashed p-2">
            <div className="flex gap-1">
              {BINDING_TYPES.map((b) => (
                <button
                  key={b.value}
                  type="button"
                  onClick={() => setNewType(b.value)}
                  className={`rounded px-2 py-0.5 text-[10px] ${newType === b.value ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300" : "bg-muted text-muted-foreground"}`}
                >
                  {b.label}
                </button>
              ))}
            </div>
            <div className="flex gap-1">
              <input
                type="text"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="值"
                className="flex-1 rounded border px-2 py-1 text-xs focus:ring-1 focus:ring-red-300 focus:outline-none"
              />
              <input
                type="text"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder="显示名"
                className="w-20 rounded border px-2 py-1 text-xs focus:ring-1 focus:ring-red-300 focus:outline-none"
              />
              <button
                type="button"
                onClick={addReviewer}
                disabled={!newValue.trim() || !newLabel.trim()}
                className="rounded bg-red-500 px-2 py-1 text-xs text-white hover:bg-red-600 disabled:opacity-40"
              >
                <Plus className="h-3 w-3" />
              </button>
            </div>
          </div>
        </div>
        <div className="space-y-2">
          <label className="text-foreground text-xs font-semibold">
            驳回目标节点 ID（不填则退回起点）
          </label>
          <input
            type="text"
            value={data.rollbackTarget ?? ""}
            onChange={(e) =>
              onUpdate({ rollbackTarget: e.target.value || undefined })
            }
            placeholder="留空 = 起点"
            className="w-full rounded-lg border px-2.5 py-2 font-mono text-xs focus:ring-1 focus:ring-red-300 focus:outline-none"
          />
        </div>
        <NotificationsConfigPanel
          notifications={data.notifications ?? []}
          onUpdate={(notifications: NotificationConfig[]) =>
            onUpdate({ notifications })
          }
        />
      </div>
    );
  }

  // Task mode — same shape as SubflowConfigPanel
  const roles = data.requiredRoles ?? [];

  const addRole = () => {
    if (!newRole) return;
    const opt = ROLE_OPTIONS.find((o) => o.value === newRole);
    if (!opt) return;
    onUpdate({
      requiredRoles: [
        ...roles,
        { roleKey: opt.value, count: 1, label: opt.label },
      ],
    });
    setNewRole("");
  };

  const setRoleCount = (idx: number, count: number) => {
    const next = [...roles];
    next[idx] = { ...next[idx]!, count };
    onUpdate({ requiredRoles: next });
  };

  return (
    <div className="space-y-4 p-4">
      <div className="space-y-2">
        <label className="text-foreground text-xs font-semibold">
          任务名称
        </label>
        <input
          type="text"
          value={data.label ?? ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="border-border w-full rounded-lg border px-2.5 py-2 text-xs focus:ring-1 focus:ring-teal-300 focus:outline-none"
        />
      </div>
      <div className="space-y-2">
        <label className="text-foreground text-xs font-semibold">团队</label>
        <input
          type="text"
          value={data.team ?? ""}
          onChange={(e) => onUpdate({ team: e.target.value || undefined })}
          placeholder="如: 地质组"
          className="border-border w-full rounded-lg border px-2.5 py-2 text-xs focus:ring-1 focus:ring-teal-300 focus:outline-none"
        />
      </div>
      <StyledCheckbox
        checked={data.aiAssist ?? false}
        onChange={(v) => onUpdate({ aiAssist: v })}
        label="AI 辅助"
      />
      {nodeId && (
        <div className="space-y-2">
          <label className="text-foreground text-xs font-semibold">
            绑定组织单元
          </label>
          <AdminSelect
            value={orgDeptCode ?? ""}
            onChange={(v) =>
              onOrgBindingChange?.(nodeId, v === "__none__" ? null : v)
            }
            options={
              deptOptions ?? [{ value: "__none__", label: "— 不绑定 —" }]
            }
            placeholder="— 不绑定 —"
            className="w-full"
          />
          <p className="text-muted-foreground text-[10px]">
            绑定后自动分配部门成员到项目
          </p>
        </div>
      )}
      <div className="space-y-2">
        <label className="text-foreground text-xs font-semibold">
          必需角色
        </label>
        {roles.map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="flex-1 text-xs">{r.label}</span>
            <input
              type="number"
              min={1}
              max={10}
              value={r.count}
              onChange={(e) => setRoleCount(i, parseInt(e.target.value) || 1)}
              className="border-border w-14 rounded border px-1.5 py-1 text-center text-xs"
            />
            <button
              onClick={() =>
                onUpdate({ requiredRoles: roles.filter((_, j) => j !== i) })
              }
              className="text-muted-foreground p-0.5 hover:text-red-600 dark:text-red-400"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
        <div className="flex gap-1">
          <AdminSelect
            value={newRole}
            onChange={setNewRole}
            options={ROLE_OPTIONS}
            placeholder="添加角色..."
            className="flex-1"
          />
          <button
            onClick={addRole}
            disabled={!newRole}
            className="rounded bg-teal-500 px-2 py-1 text-xs text-white hover:bg-teal-600 disabled:opacity-40"
          >
            <Plus className="h-3 w-3" />
          </button>
        </div>
      </div>
      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) =>
          onUpdate({ notifications })
        }
      />
    </div>
  );
}
