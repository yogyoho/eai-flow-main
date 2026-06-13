"use client";

import { Building2, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { StyledCheckbox } from "@/components/ui/styled-checkbox";
import { deptApi } from "@/extensions/api/index";
import type { DAGNodeData, RoleSlot, NotificationConfig } from "../types";
import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

const PRESET_ROLES: { roleKey: string; label: string }[] = [
  { roleKey: "lead", label: "阶段负责人" },
  { roleKey: "writer", label: "撰写人" },
  { roleKey: "reviewer", label: "审核人" },
  { roleKey: "data_reviewer", label: "数据审核" },
  { roleKey: "approver", label: "审批人" },
];

interface DeptItem {
  id: string;
  name: string;
  code: string | null;
}

interface SubflowConfigPanelProps {
  data: DAGNodeData;
  nodeId: string;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
  orgDeptCode?: string;
  onOrgBindingChange?: (nodeId: string, deptCode: string | null) => void;
}

export function SubflowConfigPanel({ data, nodeId, onUpdate, orgDeptCode, onOrgBindingChange }: SubflowConfigPanelProps) {
  const [newRoleKey, setNewRoleKey] = useState("lead");
  const [departments, setDepartments] = useState<DeptItem[]>([]);

  const roles = data.requiredRoles || [];
  const orgDeptOptions = departments.map((d) => ({ value: d.code || d.id, label: d.name }));
  const availableRoleOptions = PRESET_ROLES.filter((pr) => !roles.some((r) => r.roleKey === pr.roleKey))
    .map((pr) => ({ value: pr.roleKey, label: pr.label }));

  useEffect(() => {
    deptApi
      .list({ limit: 100 })
      .then((res) => {
        const tree = (res.departments || []) as Array<DeptItem & { children?: DeptItem[] }>;
        const flat: DeptItem[] = [];
        for (const node of tree) {
          flat.push({ id: node.id, name: node.name, code: node.code });
          if (node.children) {
            for (const child of node.children) {
              flat.push({ id: child.id, name: child.name, code: child.code });
            }
          }
        }
        setDepartments(flat);
      })
      .catch(() => {});
  }, []);

  function addRole() {
    const preset = PRESET_ROLES.find((r) => r.roleKey === newRoleKey);
    if (!preset) return;
    if (roles.some((r) => r.roleKey === newRoleKey)) return;
    onUpdate({ requiredRoles: [...roles, { roleKey: preset.roleKey, count: 1, label: preset.label }] });
  }

  function removeRole(roleKey: string) {
    onUpdate({ requiredRoles: roles.filter((r) => r.roleKey !== roleKey) });
  }

  function updateRoleCount(roleKey: string, count: number) {
    onUpdate({
      requiredRoles: roles.map((r) => (r.roleKey === roleKey ? { ...r, count: Math.max(1, count) } : r)),
    });
  }

  return (
    <div className="p-4 space-y-4">
      {/* Section header */}
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-violet-500" />
        <span className="text-xs font-semibold uppercase tracking-wider text-violet-600">子流程属性</span>
      </div>

      {/* Name */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">流程名称</label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 transition-colors"
        />
      </div>

      {/* Team */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">团队</label>
        <input
          value={data.team || ""}
          onChange={(e) => onUpdate({ team: e.target.value || undefined })}
          placeholder="如: 研究组"
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 transition-colors"
        />
      </div>

      {/* AI Assist */}
      <StyledCheckbox checked={data.aiAssist ?? false} onChange={(v) => onUpdate({ aiAssist: v })} label="AI 辅助" />

      {/* Org Unit Binding */}
      {departments.length > 0 && (
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
            <Building2 className="h-3 w-3" />
            绑定组织单元
          </label>
          <AdminSelect
            value={orgDeptCode ?? ""}
            onChange={(v) => onOrgBindingChange?.(nodeId, v || null)}
            options={orgDeptOptions}
            placeholder="— 不绑定 —"
            className="w-full"
          />
          <p className="text-[10px] text-muted-foreground">绑定后自动分配部门成员到项目</p>
        </div>
      )}

      {/* Required Roles */}
      <div className="space-y-2">
        <label className="text-[11px] font-medium text-muted-foreground block">必需角色槽位</label>
        {roles.length > 0 && (
          <div className="space-y-1.5">
            {roles.map((slot) => (
              <div key={slot.roleKey} className="flex items-center gap-1.5 group">
                <span className="bg-violet-50 text-violet-700 border border-violet-200 px-2 py-1 rounded-md text-xs font-medium flex-1 truncate">
                  {slot.label}
                </span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={slot.count}
                  onChange={(e) => updateRoleCount(slot.roleKey, parseInt(e.target.value, 10) || 1)}
                  className="w-11 px-1 py-1 text-center text-xs border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 transition-colors"
                  title="人数"
                />
                <button
                  type="button"
                  onClick={() => removeRole(slot.roleKey)}
                  className="text-gray-300 hover:text-red-500 p-0.5 transition-colors"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-center gap-1.5">
          <div className="flex-1 min-w-0">
            <AdminSelect
              value={newRoleKey}
              onChange={(v) => setNewRoleKey(v)}
              options={availableRoleOptions}
              className="w-full"
              placeholder="添加角色..."
            />
          </div>
          <button
            type="button"
            onClick={addRole}
            disabled={roles.some((r) => r.roleKey === newRoleKey)}
            className="flex items-center justify-center w-8 h-8 text-xs bg-violet-50 text-violet-600 border border-violet-200 rounded-md hover:bg-violet-100 disabled:opacity-40 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Notifications */}
      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) => onUpdate({ notifications })}
      />
    </div>
  );
}
