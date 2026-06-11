"use client";

import { Building2 } from "lucide-react";
import { useEffect, useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { StyledCheckbox } from "@/components/ui/styled-checkbox";
import { deptApi } from "@/extensions/api/index";
import type { DAGNodeData, NotificationConfig } from "../types";
import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface DeptItem {
  id: string;
  name: string;
  code: string | null;
}

interface SubWorkflowConfigPanelProps {
  data: DAGNodeData;
  nodeId: string;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
  orgDeptCode?: string;
  onOrgBindingChange?: (nodeId: string, deptCode: string | null) => void;
}

export function SubWorkflowConfigPanel({ data, nodeId, onUpdate, orgDeptCode, onOrgBindingChange }: SubWorkflowConfigPanelProps) {
  const [departments, setDepartments] = useState<DeptItem[]>([]);
  const orgDeptOptions = departments.map((d) => ({ value: d.code || d.id, label: d.name }));

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

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-indigo-500" />
        <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600">子流程属性</span>
      </div>

      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">流程名称</label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-colors"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">团队</label>
        <input
          value={data.team || ""}
          onChange={(e) => onUpdate({ team: e.target.value || undefined })}
          placeholder="如: 研究组"
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-colors"
        />
      </div>

      <StyledCheckbox checked={data.aiAssist ?? false} onChange={(v) => onUpdate({ aiAssist: v })} label="AI 辅助" />

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
        </div>
      )}

      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) => onUpdate({ notifications })}
      />
    </div>
  );
}
