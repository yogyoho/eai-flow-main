"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { StyledCheckbox } from "@/components/ui/styled-checkbox";
import type { WorkflowNodeData, ReviewerBinding, ReviewMode, NotificationConfig } from "../types";
import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface TaskConfigPanelProps {
  data: WorkflowNodeData;
  nodeId?: string;
  onUpdate: (partial: Partial<WorkflowNodeData>) => void;
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
  { value: "role", label: "角色" }, { value: "position", label: "岗位" }, { value: "user", label: "用户" },
];

const ROLE_OPTIONS = [
  { value: "leader", label: "组长" },
  { value: "writer", label: "组员" },
  { value: "dept_reviewer", label: "部门审核人" },
  { value: "company_reviewer", label: "公司审核人" },
];

export function TaskConfigPanel({ data, nodeId, onUpdate, orgDeptCode, onOrgBindingChange, deptOptions }: TaskConfigPanelProps) {
  const isReview = !!data.reviewMode;
  const reviewMode = data.reviewMode ?? "all";
  const reviewers = data.reviewers ?? [];
  const [newType, setNewType] = useState<ReviewerBinding["type"]>("role");
  const [newValue, setNewValue] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newRole, setNewRole] = useState("");

  const addReviewer = () => {
    if (!newValue.trim() || !newLabel.trim()) return;
    onUpdate({ reviewers: [...reviewers, { type: newType, value: newValue.trim(), label: newLabel.trim(), required: true }] });
    setNewValue(""); setNewLabel("");
  };

  if (isReview) {
    return (
      <div className="p-4 space-y-4">
        <div className="space-y-2">
          <label className="text-xs font-semibold text-foreground">签核模式</label>
          <div className="grid grid-cols-2 gap-1.5">
            {REVIEW_MODES.map((m) => (
              <button key={m.value} type="button" onClick={() => onUpdate({ reviewMode: m.value })}
                className={`text-left px-3 py-2 rounded-lg border text-xs transition-colors ${reviewMode === m.value ? "border-red-300 bg-red-50 text-red-700 font-semibold" : "border-border text-muted-foreground hover:border-red-200"}`}>
                <div>{m.label}</div><div className="text-[10px] opacity-60 mt-0.5">{m.desc}</div>
              </button>
            ))}
          </div>
        </div>
        {reviewMode === "ratio" && (
          <div className="space-y-2">
            <label className="text-xs font-semibold text-foreground">通过阈值: {Math.round((data.ratioThreshold ?? 0.5) * 100)}%</label>
            <input type="range" min={10} max={100} step={5} value={Math.round((data.ratioThreshold ?? 0.5) * 100)}
              onChange={(e) => onUpdate({ ratioThreshold: parseInt(e.target.value) / 100 })}
              className="w-full h-2 rounded-full bg-muted accent-red-500" />
          </div>
        )}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-foreground">审核人绑定</label>
          {reviewers.map((r, i) => (
            <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-border bg-muted/30 text-xs">
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-muted font-medium">{BINDING_TYPES.find((b) => b.value === r.type)?.label}</span>
              <span className="flex-1 truncate font-medium">{r.label}</span>
              <span className="text-[10px] text-muted-foreground font-mono">{r.value}</span>
              <button type="button" onClick={() => onUpdate({ reviewers: reviewers.filter((_, j) => j !== i) })} className="p-0.5 hover:text-red-500"><Trash2 className="w-3 h-3" /></button>
            </div>
          ))}
          <div className="space-y-1.5 border border-dashed border-border rounded-lg p-2">
            <div className="flex gap-1">
              {BINDING_TYPES.map((b) => (
                <button key={b.value} type="button" onClick={() => setNewType(b.value)}
                  className={`px-2 py-0.5 text-[10px] rounded ${newType === b.value ? "bg-red-100 text-red-700" : "bg-muted text-muted-foreground"}`}>{b.label}</button>
              ))}
            </div>
            <div className="flex gap-1">
              <input type="text" value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="值" className="flex-1 px-2 py-1 text-xs border rounded focus:outline-none focus:ring-1 focus:ring-red-300" />
              <input type="text" value={newLabel} onChange={(e) => setNewLabel(e.target.value)} placeholder="显示名" className="w-20 px-2 py-1 text-xs border rounded focus:outline-none focus:ring-1 focus:ring-red-300" />
              <button type="button" onClick={addReviewer} disabled={!newValue.trim() || !newLabel.trim()}
                className="px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600 disabled:opacity-40"><Plus className="w-3 h-3" /></button>
            </div>
          </div>
        </div>
        <div className="space-y-2">
          <label className="text-xs font-semibold text-foreground">驳回目标节点 ID（不填则退回起点）</label>
          <input type="text" value={data.rollbackTarget ?? ""} onChange={(e) => onUpdate({ rollbackTarget: e.target.value || undefined })}
            placeholder="留空 = 起点" className="w-full px-2.5 py-2 text-xs border rounded-lg focus:outline-none focus:ring-1 focus:ring-red-300 font-mono" />
        </div>
        <NotificationsConfigPanel
          notifications={data.notifications ?? []}
          onUpdate={(notifications: NotificationConfig[]) => onUpdate({ notifications })}
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
    onUpdate({ requiredRoles: [...roles, { roleKey: opt.value, count: 1, label: opt.label }] });
    setNewRole("");
  };

  const setRoleCount = (idx: number, count: number) => {
    const next = [...roles];
    next[idx] = { ...next[idx]!, count };
    onUpdate({ requiredRoles: next });
  };

  return (
    <div className="p-4 space-y-4">
      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground">任务名称</label>
        <input type="text" value={data.label ?? ""} onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full px-2.5 py-2 text-xs border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-teal-300" />
      </div>
      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground">团队</label>
        <input type="text" value={data.team ?? ""} onChange={(e) => onUpdate({ team: e.target.value || undefined })}
          placeholder="如: 地质组" className="w-full px-2.5 py-2 text-xs border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-teal-300" />
      </div>
      <StyledCheckbox checked={data.aiAssist ?? false} onChange={(v) => onUpdate({ aiAssist: v })} label="AI 辅助" />
      {nodeId && (
        <div className="space-y-2">
          <label className="text-xs font-semibold text-foreground">绑定组织单元</label>
          <AdminSelect value={orgDeptCode ?? ""} onChange={(v) => onOrgBindingChange?.(nodeId, v === "__none__" ? null : v)}
            options={deptOptions ?? [{ value: "__none__", label: "— 不绑定 —" }]} placeholder="— 不绑定 —" className="w-full" />
          <p className="text-[10px] text-muted-foreground">绑定后自动分配部门成员到项目</p>
        </div>
      )}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground">必需角色</label>
        {roles.map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="text-xs flex-1">{r.label}</span>
            <input type="number" min={1} max={10} value={r.count}
              onChange={(e) => setRoleCount(i, parseInt(e.target.value) || 1)}
              className="w-14 px-1.5 py-1 text-xs border border-border rounded text-center" />
            <button onClick={() => onUpdate({ requiredRoles: roles.filter((_, j) => j !== i) })}
              className="p-0.5 text-muted-foreground hover:text-red-500"><Trash2 className="w-3 h-3" /></button>
          </div>
        ))}
        <div className="flex gap-1">
          <AdminSelect value={newRole} onChange={setNewRole}
            options={ROLE_OPTIONS} placeholder="添加角色..." className="flex-1" />
          <button onClick={addRole} disabled={!newRole}
            className="px-2 py-1 text-xs bg-teal-500 text-white rounded hover:bg-teal-600 disabled:opacity-40"><Plus className="w-3 h-3" /></button>
        </div>
      </div>
      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) => onUpdate({ notifications })}
      />
    </div>
  );
}
