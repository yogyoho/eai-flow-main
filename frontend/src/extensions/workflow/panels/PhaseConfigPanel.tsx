"use client";

import { Building2, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { AdminSelect } from "@/components/ui/admin-select";
import { deptApi } from "@/extensions/api/index";
import type { DAGNodeData, RoleSlot } from "../types";

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

interface PhaseConfigPanelProps {
  data: DAGNodeData;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
  nodeId?: string;
  orgDeptCode?: string;
  onOrgBindingChange?: (nodeId: string, deptCode: string | null) => void;
}

export function PhaseConfigPanel({ data, nodeId, onUpdate, orgDeptCode, onOrgBindingChange }: PhaseConfigPanelProps) {
  const [newRoleKey, setNewRoleKey] = useState("lead");
  const [departments, setDepartments] = useState<DeptItem[]>([]);

  const roles = data.requiredRoles || [];

  // Options for the org binding select
  const orgDeptOptions = departments.map((d) => ({ value: d.code || d.id, label: d.name }));
  // The "unbound" state is represented by an empty orgDeptCode; AdminSelect shows placeholder when value doesn't match any option.

  // Options for the role add select (exclude already-added roles)
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
    const updated = [...roles, { roleKey: preset.roleKey, count: 1, label: preset.label }];
    onUpdate({ requiredRoles: updated });
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
        <div className="w-1 h-4 rounded-full bg-purple-500" />
        <span className="text-xs font-semibold uppercase tracking-wider text-purple-600">阶段属性</span>
      </div>

      {/* Phase name */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">阶段名称</label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400 transition-colors"
        />
      </div>

      {/* Team */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">团队</label>
        <input
          value={data.team || ""}
          onChange={(e) => onUpdate({ team: e.target.value })}
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400 transition-colors"
          placeholder="如: A组"
        />
      </div>

      {/* AI Assist toggle */}
      <label className="flex items-center gap-2.5 cursor-pointer group">
        <div className="relative">
          <input
            type="checkbox"
            checked={data.aiAssist ?? false}
            onChange={(e) => onUpdate({ aiAssist: e.target.checked })}
            className="peer sr-only"
          />
          <div className="w-8 h-[18px] rounded-full bg-muted border border-border transition-colors peer-checked:bg-purple-500 peer-checked:border-purple-500 peer-focus-visible:ring-2 peer-focus-visible:ring-purple-500/20" />
          <div className="absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-[14px]" />
        </div>
        <span className="text-sm text-foreground group-hover:text-purple-600 transition-colors">AI 辅助</span>
      </label>

      {/* Org Unit Binding */}
      {onOrgBindingChange && departments.length > 0 && (
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
            <Building2 className="h-3 w-3" />
            绑定组织单元
          </label>
          <AdminSelect
            value={orgDeptCode || ""}
            onChange={(v) => nodeId && onOrgBindingChange(nodeId, v || null)}
            options={orgDeptOptions}
            placeholder="— 不绑定 —"
            className="w-full"
          />
          <p className="text-[10px] text-muted-foreground">
            绑定后，该阶段自动分配部门成员到项目
          </p>
        </div>
      )}

      {/* Required Roles */}
      <div className="space-y-2">
        <label className="text-[11px] font-medium text-muted-foreground block">必需角色槽位</label>
        {roles.length > 0 && (
          <div className="space-y-1.5">
            {roles.map((slot) => (
              <div key={slot.roleKey} className="flex items-center gap-1.5 group">
                <span className="bg-purple-50 text-purple-700 border border-purple-200 px-2 py-1 rounded-md text-xs font-medium flex-1 truncate">
                  {slot.label}
                </span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={slot.count}
                  onChange={(e) => updateRoleCount(slot.roleKey, parseInt(e.target.value, 10) || 1)}
                  className="w-11 px-1 py-1 text-center text-xs border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400 transition-colors"
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
              onChange={(v) => {
                setNewRoleKey(v);
              }}
              options={availableRoleOptions}
              className="w-full"
              placeholder="添加角色..."
            />
          </div>
          <button
            type="button"
            onClick={addRole}
            disabled={roles.some((r) => r.roleKey === newRoleKey)}
            className="flex items-center justify-center w-8 h-8 text-xs bg-purple-50 text-purple-600 border border-purple-200 rounded-md hover:bg-purple-100 disabled:opacity-40 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {data.inputFrom && data.inputFrom.length > 0 && (
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium text-muted-foreground">输入上下文</label>
          <div className="space-y-1">
            {data.inputFrom.map((id) => (
              <div key={id} className="text-xs bg-purple-50 border border-purple-100 text-purple-700 px-2 py-1 rounded-md">
                ← {id}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
