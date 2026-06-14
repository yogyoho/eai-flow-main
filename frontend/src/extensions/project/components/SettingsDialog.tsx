"use client";

import { AlertTriangle, Check, Loader2, Pencil, Settings, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import {
  PROJECT_STATUS_LABELS,
  type ProjectStatus,
  type ReportProject,
} from "@/extensions/project/types";
import { getReportTypeLabel } from "@/extensions/project/hooks/useReportTypes";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";

interface SettingsDialogProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialog({
  project,
  projectId,
  onRefresh,
  identity,
  open,
  onOpenChange,
}: SettingsDialogProps) {
  const [projectName, setProjectName] = useState(project.name);
  const [editingName, setEditingName] = useState(false);
  const [savingName, setSavingName] = useState(false);
  const [projectStatus, setProjectStatus] = useState<ProjectStatus>(project.status);
  const [savingStatus, setSavingStatus] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);

  const canEdit = identity?.isAdmin || identity?.hasAnyPermission(["settings:edit", "project:edit"]);
  const canDelete = identity?.isAdmin || identity?.hasAnyPermission(["project:delete"]);

  // Reset on open
  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) {
      setProjectName(project.name);
      setEditingName(false);
      setProjectStatus(project.status);
      setDeleteConfirm("");
    }
    onOpenChange(nextOpen);
  };

  const handleSaveName = async () => {
    if (!projectName.trim()) return;
    setSavingName(true);
    try {
      await projectApi.update(projectId, { name: projectName.trim() });
      setEditingName(false);
      onRefresh();
      toast.success("项目名称已更新");
    } catch {
      toast.error("更新失败");
    } finally {
      setSavingName(false);
    }
  };

  const handleStatusChange = async (status: string) => {
    setSavingStatus(true);
    try {
      await projectApi.update(projectId, { status: status as ProjectStatus });
      setProjectStatus(status as ProjectStatus);
      onRefresh();
      toast.success("项目状态已更新");
    } catch {
      toast.error("更新失败");
    } finally {
      setSavingStatus(false);
    }
  };

  const handleDelete = async () => {
    if (deleteConfirm !== project.name) return;
    setDeleting(true);
    try {
      await projectApi.delete(projectId);
      window.location.href = "/projects";
    } catch {
      toast.error("删除失败");
      setDeleting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            项目设置
          </DialogTitle>
          <DialogDescription>管理项目基本信息和危险操作</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Project Name */}
          <div className="space-y-1.5">
            <label className="text-[12px] text-muted-foreground font-medium">项目名称</label>
            {editingName ? (
              <div className="flex items-center gap-2">
                <Input
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  className="h-8 text-sm"
                  autoFocus
                  onKeyDown={(e) => e.key === "Enter" && handleSaveName()}
                />
                <Button size="sm" className="h-8" onClick={handleSaveName} disabled={savingName}>
                  {savingName ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8"
                  onClick={() => {
                    setEditingName(false);
                    setProjectName(project.name);
                  }}
                >
                  取消
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <p className="text-sm text-foreground">{project.name}</p>
                {canEdit && (
                  <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => setEditingName(true)}>
                    <Pencil className="h-3 w-3" />
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* Report Type */}
          <div className="space-y-1.5">
            <label className="text-[12px] text-muted-foreground font-medium">报告类型</label>
            <p className="text-sm text-foreground">{getReportTypeLabel(project.reportType)}</p>
          </div>

          {/* Status */}
          <div className="space-y-1.5">
            <label className="text-[12px] text-muted-foreground font-medium">项目状态</label>
            {canEdit ? (
              <Select value={projectStatus} onValueChange={handleStatusChange} disabled={savingStatus}>
                <SelectTrigger className="h-8 w-48 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(PROJECT_STATUS_LABELS).map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <p className="text-sm text-foreground">{PROJECT_STATUS_LABELS[project.status]}</p>
            )}
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[12px] text-muted-foreground font-medium">创建时间</label>
              <p className="text-sm text-foreground">
                {project.createdAt ? new Date(project.createdAt).toLocaleString("zh-CN") : "未知"}
              </p>
            </div>
            <div className="space-y-1.5">
              <label className="text-[12px] text-muted-foreground font-medium">更新时间</label>
              <p className="text-sm text-foreground">
                {project.updatedAt ? new Date(project.updatedAt).toLocaleString("zh-CN") : "未知"}
              </p>
            </div>
          </div>

          {/* Danger Zone */}
          {canDelete && (
            <div className="border-t border-border/40 pt-4">
              <h4 className="text-sm font-semibold text-destructive flex items-center gap-1.5 mb-3">
                <AlertTriangle className="h-3.5 w-3.5" />
                危险操作
              </h4>
              <div className="rounded-lg border border-destructive/30 p-4 space-y-3">
                <p className="text-sm text-muted-foreground">以下操作不可撤销，请谨慎操作。</p>
                <p className="text-sm text-muted-foreground">
                  请输入项目名称 <strong>{project.name}</strong> 以确认删除：
                </p>
                <Input
                  value={deleteConfirm}
                  onChange={(e) => setDeleteConfirm(e.target.value)}
                  placeholder="输入项目名称确认"
                  className="h-8 text-sm"
                />
                <Button
                  variant="destructive"
                  size="sm"
                  className="h-8"
                  disabled={deleteConfirm !== project.name || deleting}
                  onClick={handleDelete}
                >
                  {deleting ? (
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                  )}
                  永久删除
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
