"use client";

import {
  AlertTriangle,
  Check,
  ChevronRight,
  Loader2,
  Pencil,
  Plus,
  Settings2,
  Trash2,
  UserPlus,
  Users,
  Workflow,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import {
  MEMBER_ROLE_LABELS,
  PROJECT_STATUS_LABELS,
  REPORT_TYPE_LABELS,
  type MemberRole,
  type ProjectStatus,
  type ReportProject,
} from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import { workflowApi } from "@/extensions/workflow/api";

interface SettingsTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
}

type Section = "general" | "members" | "danger";

const SECTIONS: { id: Section; label: string; icon: any }[] = [
  { id: "general", label: "基本信息", icon: Settings2 },
  { id: "members", label: "成员管理", icon: Users },
  { id: "danger", label: "危险操作", icon: AlertTriangle },
];

export function SettingsTab({ project, projectId, onRefresh, identity }: SettingsTabProps) {
  const [section, setSection] = useState<Section>("general");
  const [projectName, setProjectName] = useState(project.name);
  const [editingName, setEditingName] = useState(false);
  const [savingName, setSavingName] = useState(false);
  const [projectStatus, setProjectStatus] = useState<ProjectStatus>(project.status);
  const [savingStatus, setSavingStatus] = useState(false);

  // Member state
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ id: string; username: string; fullName?: string }>>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [newRole, setNewRole] = useState<MemberRole>("member");
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  // Delete state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");

  const canEdit = identity?.isAdmin || identity?.hasAnyPermission(["settings:edit", "project:edit"]);
  const canManageMembers = identity?.isAdmin || identity?.hasAnyPermission(["member:add", "member:remove"]);
  const canDelete = identity?.isAdmin || identity?.hasAnyPermission(["project:delete"]);

  // Update project name
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

  // Update project status
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

  // Search users
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/extensions/users/search?keyword=${encodeURIComponent(searchQuery)}`);
        if (resp.ok) {
          const data = await resp.json();
          setSearchResults((data.users ?? data.items ?? []).slice(0, 10));
        }
      } catch {
        /* ignore */
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Add member
  const handleAddMember = async () => {
    if (!selectedUserId) return;
    setAdding(true);
    try {
      await projectApi.addMember(projectId, selectedUserId, newRole);
      setAddDialogOpen(false);
      setSearchQuery("");
      setSelectedUserId(null);
      onRefresh();
      toast.success("成员已添加");
    } catch {
      toast.error("添加成员失败");
    } finally {
      setAdding(false);
    }
  };

  // Remove member
  const handleRemoveMember = async (userId: string) => {
    setRemovingId(userId);
    try {
      await projectApi.removeMember(projectId, userId);
      onRefresh();
      toast.success("成员已移除");
    } catch {
      toast.error("移除失败");
    } finally {
      setRemovingId(null);
    }
  };

  // Change role
  const handleRoleChange = async (userId: string, role: MemberRole) => {
    try {
      await projectApi.updateMember(projectId, userId, { role });
      onRefresh();
      toast.success("角色已更新");
    } catch {
      toast.error("更新角色失败");
    }
  };

  // Delete project
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
    <div className="flex h-full">
      {/* Left Nav */}
      <div className="w-[200px] shrink-0 border-r border-border/40 p-3">
        <nav className="space-y-0.5">
          {SECTIONS.map((s) => {
            const Icon = s.icon;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setSection(s.id)}
                className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                  section === s.id
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent/40 hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {s.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Right Content */}
      <ScrollArea className="flex-1">
        <div className="p-6 max-w-2xl space-y-6">
          {/* ── General ── */}
          {section === "general" && (
            <>
              <h3 className="text-sm font-semibold text-foreground">基本信息</h3>
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
                      <Button size="sm" variant="ghost" className="h-8" onClick={() => { setEditingName(false); setProjectName(project.name); }}>
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
                  <p className="text-sm text-foreground">{REPORT_TYPE_LABELS[project.reportType] ?? project.reportType}</p>
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
              </div>
            </>
          )}

          {/* ── Members ── */}
          {section === "members" && (
            <>
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-foreground">成员管理</h3>
                {canManageMembers && (
                  <Button size="sm" className="h-7 text-[12px]" onClick={() => setAddDialogOpen(true)}>
                    <UserPlus className="h-3.5 w-3.5 mr-1" />
                    添加成员
                  </Button>
                )}
              </div>
              <div className="rounded-lg border border-border/40 divide-y divide-border/40">
                {project.members?.length > 0 ? (
                  project.members.map((m) => (
                    <div key={m.id} className="flex items-center gap-3 px-4 py-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-medium text-primary">
                        {(m.username ?? "?").charAt(0).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground font-medium truncate">{m.username}</p>
                        <p className="text-[11px] text-muted-foreground">{m.userId.slice(0, 8)}...</p>
                      </div>
                      {canManageMembers && m.role !== "owner" ? (
                        <Select value={m.role} onValueChange={(role) => handleRoleChange(m.userId, role as MemberRole)}>
                          <SelectTrigger className="h-7 w-24 text-[11px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(MEMBER_ROLE_LABELS)
                              .filter(([key]) => key !== "owner")
                              .map(([key, label]) => (
                                <SelectItem key={key} value={key}>
                                  {label}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Badge variant="secondary" className="text-[11px]">
                          {MEMBER_ROLE_LABELS[m.role as keyof typeof MEMBER_ROLE_LABELS] ?? m.role}
                        </Badge>
                      )}
                      {canManageMembers && m.role !== "owner" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          disabled={removingId === m.userId}
                          onClick={() => handleRemoveMember(m.userId)}
                        >
                          {removingId === m.userId ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="px-4 py-8 text-center">
                    <Users className="h-6 w-6 text-muted-foreground/30 mx-auto mb-1.5" />
                    <p className="text-sm text-muted-foreground">暂无成员</p>
                  </div>
                )}
              </div>
            </>
          )}

          {/* ── Danger Zone ── */}
          {section === "danger" && (
            <>
              <h3 className="text-sm font-semibold text-foreground text-destructive">危险操作</h3>
              <div className="rounded-lg border border-destructive/30 p-4 space-y-3">
                <p className="text-sm text-muted-foreground">
                  以下操作不可撤销，请谨慎操作。
                </p>
                {canDelete && (
                  <Button
                    variant="destructive"
                    size="sm"
                    className="h-8"
                    onClick={() => setDeleteDialogOpen(true)}
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                    删除项目
                  </Button>
                )}
                {!canDelete && (
                  <p className="text-xs text-muted-foreground">您没有删除此项目的权限</p>
                )}
              </div>
            </>
          )}
        </div>
      </ScrollArea>

      {/* Add Member Dialog */}
      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>添加成员</DialogTitle>
            <DialogDescription>搜索用户并指定角色</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="搜索用户名..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setSelectedUserId(null);
              }}
            />
            {searchResults.length > 0 && (
              <ScrollArea className="h-40">
                <div className="space-y-0.5">
                  {searchResults.map((u) => (
                    <button
                      key={u.id}
                      type="button"
                      onClick={() => {
                        setSelectedUserId(u.id);
                        setSearchQuery(u.username);
                      }}
                      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                        selectedUserId === u.id ? "bg-primary/10 text-primary" : "hover:bg-accent/40"
                      }`}
                    >
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-[10px] font-medium">
                        {u.username.charAt(0).toUpperCase()}
                      </div>
                      <span>{u.username}</span>
                      {u.fullName && <span className="text-muted-foreground">({u.fullName})</span>}
                    </button>
                  ))}
                </div>
              </ScrollArea>
            )}
            <div className="flex items-center gap-2">
              <Select value={newRole} onValueChange={(v) => setNewRole(v as MemberRole)}>
                <SelectTrigger className="h-8 w-32 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(MEMBER_ROLE_LABELS)
                    .filter(([key]) => key !== "owner")
                    .map(([key, label]) => (
                      <SelectItem key={key} value={key}>
                        {label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setAddDialogOpen(false)}>
              取消
            </Button>
            <Button size="sm" disabled={!selectedUserId || adding} onClick={handleAddMember}>
              {adding ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <UserPlus className="h-3 w-3 mr-1" />}
              添加
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-destructive">确认删除项目</DialogTitle>
            <DialogDescription>
              此操作将永久删除项目"{project.name}"及其所有数据，且不可撤销。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              请输入项目名称 <strong>{project.name}</strong> 以确认删除：
            </p>
            <Input
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder="输入项目名称确认"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => { setDeleteDialogOpen(false); setDeleteConfirm(""); }}>
              取消
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={deleteConfirm !== project.name || deleting}
              onClick={handleDelete}
            >
              {deleting ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Trash2 className="h-3 w-3 mr-1" />}
              永久删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
