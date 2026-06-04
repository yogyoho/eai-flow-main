# 项目概览 Tab 合并实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将流程看板、项目设置 tab 合并到概览 tab 中，减少 tab 数量从 5 个到 3 个 + ⚙ 图标入口，同时优化概览内的重复元素和不可靠的进度指标。

**Architecture:** 纯前端重构。从 SettingsTab 提取共享组件（AddMemberDialog、SettingsDialog），新建 WorkflowProgressCompact 精简版组件，重写 OverviewTab 整合所有功能。tabRegistry 删除 workflow/settings 注册，ProjectWorkspace 改为 ⚙ 图标 + Dialog。

**Tech Stack:** React 19, TypeScript, Tailwind CSS 4, Lucide Icons, Vitest

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend/src/extensions/project/utils.ts` | **Create** | Pure logic: inferStatus, ActivityMarker, flattenChapters |
| `frontend/tests/unit/extensions/project/utils.test.ts` | **Create** | Unit tests for pure logic |
| `frontend/src/extensions/project/components/AddMemberDialog.tsx` | **Create** | Shared add-member dialog extracted from SettingsTab |
| `frontend/src/extensions/project/components/SettingsDialog.tsx` | **Create** | Settings dialog (name/status/delete) from SettingsTab |
| `frontend/src/extensions/project/components/WorkflowProgressCompact.tsx` | **Create** | Compact workflow progress bar (data-driven) |
| `frontend/src/extensions/project/components/StatusDistribution.tsx` | **Create** | Chapter status distribution summary bar |
| `frontend/src/extensions/project/tabs/OverviewTab.tsx` | **Rewrite** | Merged overview with all new features |
| `frontend/src/extensions/project/ProjectWorkspace.tsx` | **Modify** | Remove workflow/settings tabs, add ⚙ icon |
| `frontend/src/extensions/project/tabRegistry.ts` | **Modify** | Remove workflow and settings tab entries |
| `frontend/src/extensions/project/tabs/SettingsTab.tsx` | **Delete** | Logic distributed to OverviewTab + SettingsDialog |

---

### Task 1: Create shared utility functions + tests

**Files:**
- Create: `frontend/src/extensions/project/utils.ts`
- Create: `frontend/tests/unit/extensions/project/utils.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/tests/unit/extensions/project/utils.test.ts
import { describe, expect, it } from "vitest";

import type { ProjectChapter } from "@/extensions/project/types";

import {
  type ChapterStatus,
  activityLabel,
  flattenChapters,
  inferStatus,
} from "@/extensions/project/utils";

describe("flattenChapters", () => {
  it("flattens nested chapters", () => {
    const chapters: ProjectChapter[] = [
      {
        id: "1", projectId: "p", parentId: null, title: "Ch1", level: 1,
        sortOrder: 0, status: "pending", content: null,
        assignedTo: null, assignedName: null,
        wordCountTarget: 0, wordCountCurrent: 0,
        purpose: null, generationHint: null, children: [
          {
            id: "1-1", projectId: "p", parentId: "1", title: "Ch1-1", level: 2,
            sortOrder: 0, status: "pending", content: null,
            assignedTo: null, assignedName: null,
            wordCountTarget: 0, wordCountCurrent: 0,
            purpose: null, generationHint: null, children: [],
            createdAt: null, updatedAt: null,
          },
        ],
        createdAt: null, updatedAt: null,
      },
      {
        id: "2", projectId: "p", parentId: null, title: "Ch2", level: 1,
        sortOrder: 1, status: "pending", content: null,
        assignedTo: null, assignedName: null,
        wordCountTarget: 0, wordCountCurrent: 0,
        purpose: null, generationHint: null, children: [],
        createdAt: null, updatedAt: null,
      },
    ];
    const flat = flattenChapters(chapters);
    expect(flat).toHaveLength(3);
    expect(flat.map((c) => c.id)).toEqual(["1", "1-1", "2"]);
  });

  it("returns empty for empty input", () => {
    expect(flattenChapters([])).toEqual([]);
  });
});

describe("inferStatus", () => {
  const base = (overrides: Partial<ProjectChapter> = {}): ProjectChapter => ({
    id: "1", projectId: "p", parentId: null, title: "Test", level: 1,
    sortOrder: 0, status: "pending", content: null,
    assignedTo: null, assignedName: null,
    wordCountTarget: 0, wordCountCurrent: 0,
    purpose: null, generationHint: null, children: [],
    createdAt: null, updatedAt: null,
    ...overrides,
  });

  it("returns 'draft' when no content", () => {
    expect(inferStatus(base())).toBe<ChapterStatus>("draft");
  });

  it("returns 'writing' when wordCountCurrent > 0", () => {
    expect(inferStatus(base({ wordCountCurrent: 100 }))).toBe<ChapterStatus>("writing");
  });

  it("returns 'review' for in_review status", () => {
    expect(inferStatus(base({ status: "in_review" }))).toBe<ChapterStatus>("review");
  });

  it("returns 'review' for pending_review status", () => {
    expect(inferStatus(base({ status: "pending_review", wordCountCurrent: 500 }))).toBe<ChapterStatus>("review");
  });

  it("returns 'completed' for completed status", () => {
    expect(inferStatus(base({ status: "completed" }))).toBe<ChapterStatus>("completed");
  });

  it("returns 'completed' for approved status", () => {
    expect(inferStatus(base({ status: "approved", wordCountCurrent: 1000 }))).toBe<ChapterStatus>("completed");
  });

  it("returns 'completed' for signed status", () => {
    expect(inferStatus(base({ status: "signed" }))).toBe<ChapterStatus>("completed");
  });

  it("completed takes priority over review", () => {
    expect(inferStatus(base({ status: "approved" }))).toBe<ChapterStatus>("completed");
  });

  it("review takes priority over writing", () => {
    expect(inferStatus(base({ status: "in_review", wordCountCurrent: 500 }))).toBe<ChapterStatus>("review");
  });
});

describe("activityLabel", () => {
  it("returns null for null input", () => {
    expect(activityLabel(null)).toBeNull();
  });

  it("returns '刚刚编辑' for < 5 minutes", () => {
    const fourMinutesAgo = new Date(Date.now() - 4 * 60 * 1000).toISOString();
    expect(activityLabel(fourMinutesAgo)).toBe("刚刚编辑");
  });

  it("returns 'X分钟前' for < 60 minutes", () => {
    const thirtyMinAgo = new Date(Date.now() - 30 * 60 * 1000).toISOString();
    expect(activityLabel(thirtyMinAgo)).toBe("30分钟前");
  });

  it("returns 'X小时前' for < 24 hours", () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    expect(activityLabel(threeHoursAgo)).toBe("3小时前");
  });

  it("returns 'X天前' for >= 24 hours", () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    expect(activityLabel(twoDaysAgo)).toBe("2天前");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run tests/unit/extensions/project/utils.test.ts`
Expected: FAIL — module `@/extensions/project/utils` not found

- [ ] **Step 3: Write implementation**

```ts
// frontend/src/extensions/project/utils.ts
import type { ProjectChapter } from "./types";

export type ChapterStatus = "draft" | "writing" | "review" | "completed";

/** Flatten nested chapters into a flat array (depth-first). */
export function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  const result: ProjectChapter[] = [];
  for (const ch of chapters) {
    result.push(ch);
    if (ch.children?.length) result.push(...flattenChapters(ch.children));
  }
  return result;
}

/**
 * Auto-infer chapter display status from content and backend status.
 * Priority: completed > review > writing > draft
 */
export function inferStatus(ch: ProjectChapter): ChapterStatus {
  if (["completed", "approved", "signed"].includes(ch.status)) return "completed";
  if (["in_review", "pending_review"].includes(ch.status)) return "review";
  if ((ch.wordCountCurrent ?? 0) > 0) return "writing";
  return "draft";
}

/** Format updatedAt into a human-friendly activity label. */
export function activityLabel(updatedAt: string | null): string | null {
  if (!updatedAt) return null;
  const diff = Date.now() - new Date(updatedAt).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 5) return "刚刚编辑";
  if (minutes < 60) return `${minutes}分钟前`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}小时前`;
  return `${Math.floor(minutes / 1440)}天前`;
}

/** Aggregate total word count across all chapters. */
export function aggregateWordCount(chapters: ProjectChapter[]): number {
  let total = 0;
  for (const ch of flattenChapters(chapters)) {
    total += ch.wordCountCurrent ?? 0;
  }
  return total;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run tests/unit/extensions/project/utils.test.ts`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/project/utils.ts frontend/tests/unit/extensions/project/utils.test.ts
git commit -m "feat(project): add shared utility functions with tests"
```

---

### Task 2: Extract AddMemberDialog from SettingsTab

**Files:**
- Create: `frontend/src/extensions/project/components/AddMemberDialog.tsx`

- [ ] **Step 1: Create AddMemberDialog component**

Extract the add-member dialog from `SettingsTab.tsx:411-478` into a standalone component.

```tsx
// frontend/src/extensions/project/components/AddMemberDialog.tsx
"use client";

import { Loader2, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";

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
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import { MEMBER_ROLE_LABELS, type MemberRole } from "@/extensions/project/types";

interface AddMemberDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => void;
}

export function AddMemberDialog({ projectId, open, onOpenChange, onAdded }: AddMemberDialogProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ id: string; username: string; fullName?: string }>>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [newRole, setNewRole] = useState<MemberRole>("member");
  const [adding, setAdding] = useState(false);

  // Reset state on open
  useEffect(() => {
    if (open) {
      setSearchQuery("");
      setSearchResults([]);
      setSelectedUserId(null);
      setNewRole("member");
    }
  }, [open]);

  // Search users with debounce
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

  const handleAdd = async () => {
    if (!selectedUserId) return;
    setAdding(true);
    try {
      await projectApi.addMember(projectId, selectedUserId, newRole);
      onOpenChange(false);
      onAdded();
      toast.success("成员已添加");
    } catch {
      toast.error("添加成员失败");
    } finally {
      setAdding(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button size="sm" disabled={!selectedUserId || adding} onClick={handleAdd}>
            {adding ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <UserPlus className="h-3 w-3 mr-1" />}
            添加
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Verify no import errors**

Run: `cd frontend && pnpm typecheck 2>&1 | head -20`
Expected: Only pre-existing errors (if any), no errors from AddMemberDialog.tsx

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/components/AddMemberDialog.tsx
git commit -m "feat(project): extract AddMemberDialog as shared component"
```

---

### Task 3: Create SettingsDialog component

**Files:**
- Create: `frontend/src/extensions/project/components/SettingsDialog.tsx`

- [ ] **Step 1: Create SettingsDialog**

Extract basic info editing + danger zone from `SettingsTab.tsx` into a Dialog component.

```tsx
// frontend/src/extensions/project/components/SettingsDialog.tsx
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
  MEMBER_ROLE_LABELS,
  PROJECT_STATUS_LABELS,
  REPORT_TYPE_LABELS,
  type ProjectStatus,
  type ReportProject,
} from "@/extensions/project/types";
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

          {/* Danger Zone */}
          {canDelete && (
            <>
              <div className="border-t border-border/40 pt-4">
                <h4 className="text-sm font-semibold text-destructive flex items-center gap-1.5 mb-3">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  危险操作
                </h4>
                <div className="rounded-lg border border-destructive/30 p-4 space-y-3">
                  <p className="text-sm text-muted-foreground">
                    以下操作不可撤销，请谨慎操作。
                  </p>
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
                    {deleting ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 mr-1.5" />}
                    永久删除
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Verify no import errors**

Run: `cd frontend && pnpm typecheck 2>&1 | head -20`
Expected: No errors from SettingsDialog.tsx

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/components/SettingsDialog.tsx
git commit -m "feat(project): create SettingsDialog from extracted SettingsTab logic"
```

---

### Task 4: Create WorkflowProgressCompact component

**Files:**
- Create: `frontend/src/extensions/project/components/WorkflowProgressCompact.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/extensions/project/components/WorkflowProgressCompact.tsx
"use client";

import { Check, ChevronRight, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";

import type { WorkflowGraph } from "@/extensions/workflow/types";
import { useWorkflowStatus } from "@/extensions/workflow/hooks/useWorkflowStatus";

// Lazy-load full ReactFlow view for the detail dialog
import dynamic from "next/dynamic";

const WorkflowProgressView = dynamic(
  () => import("@/extensions/workflow/WorkflowProgressView").then((m) => ({ default: m.WorkflowProgressView })),
  { ssr: false },
);

interface WorkflowProgressCompactProps {
  projectId: string;
  workflowGraph: WorkflowGraph | null;
}

function getNodeDetail(node: { chapterTotal?: number | null; chapterCompleted?: number | null; reviewTotal?: number | null; reviewApproved?: number | null }) {
  if (node.chapterTotal) return `${node.chapterCompleted ?? 0}/${node.chapterTotal}`;
  if (node.reviewTotal) return `${node.reviewApproved ?? 0}/${node.reviewTotal}`;
  return null;
}

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-700",
  running: "bg-primary/10 text-primary ring-1 ring-primary/30",
  pending: "bg-muted text-muted-foreground",
  error: "bg-red-100 text-red-700",
};

export function WorkflowProgressCompact({ projectId, workflowGraph }: WorkflowProgressCompactProps) {
  const { status, loading } = useWorkflowStatus(projectId, 30000);
  const [detailOpen, setDetailOpen] = useState(false);

  const nodes = useMemo(() => status?.nodes ?? [], [status?.nodes]);

  // Don't render if no workflow or still loading
  if (loading || nodes.length === 0) return null;

  return (
    <>
      <div className="rounded-lg border border-border/60 bg-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-foreground">流程进度</h3>
          <Button variant="ghost" size="sm" className="h-6 text-[12px] text-primary" onClick={() => setDetailOpen(true)}>
            查看详情 →
          </Button>
        </div>
        <div className="flex items-center flex-wrap gap-1">
          {nodes.map((node, i) => (
            <div key={node.nodeId} className="flex items-center">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-1 text-[12px] font-medium ${STATUS_STYLES[node.status] ?? STATUS_STYLES.pending!}`}
              >
                {node.status === "completed" && <Check className="h-3 w-3 mr-1" />}
                {node.status === "running" && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                {node.label}
                {getNodeDetail(node) && (
                  <span className="ml-1.5 text-[10px] opacity-70">({getNodeDetail(node)})</span>
                )}
              </span>
              {i < nodes.length - 1 && (
                <ChevronRight className="h-3 w-3 text-muted-foreground/40 mx-0.5" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Full-screen detail dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-[90vw] h-[80vh] p-0 gap-0">
          <DialogTitle className="sr-only">流程详情</DialogTitle>
          <WorkflowProgressView projectId={projectId} workflowGraph={workflowGraph} />
        </DialogContent>
      </Dialog>
    </>
  );
}
```

- [ ] **Step 2: Verify no import errors**

Run: `cd frontend && pnpm typecheck 2>&1 | head -20`
Expected: No errors from WorkflowProgressCompact.tsx

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/components/WorkflowProgressCompact.tsx
git commit -m "feat(project): add WorkflowProgressCompact component"
```

---

### Task 5: Create StatusDistribution component

**Files:**
- Create: `frontend/src/extensions/project/components/StatusDistribution.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/extensions/project/components/StatusDistribution.tsx
"use client";

import { useMemo } from "react";

import type { ProjectChapter } from "@/extensions/project/types";
import { type ChapterStatus, flattenChapters, inferStatus } from "@/extensions/project/utils";

interface StatusDistributionProps {
  chapters: ProjectChapter[];
}

const STATUS_ITEMS: { key: ChapterStatus; label: string; dotColor: string; activeColor: string }[] = [
  { key: "draft", label: "待编写", dotColor: "bg-slate-300", activeColor: "text-slate-600" },
  { key: "writing", label: "编写中", dotColor: "bg-blue-400", activeColor: "text-blue-600" },
  { key: "review", label: "审核中", dotColor: "bg-amber-400", activeColor: "text-amber-600" },
  { key: "completed", label: "已完成", dotColor: "bg-emerald-400", activeColor: "text-emerald-600" },
];

export function StatusDistribution({ chapters }: StatusDistributionProps) {
  const counts = useMemo(() => {
    const flat = flattenChapters(chapters);
    const map = { draft: 0, writing: 0, review: 0, completed: 0 } as Record<ChapterStatus, number>;
    for (const ch of flat) {
      map[inferStatus(ch)]++;
    }
    return map;
  }, [chapters]);

  return (
    <div className="flex items-center gap-4 px-1">
      {STATUS_ITEMS.map((item) => (
        <div key={item.key} className="flex items-center gap-1.5 text-[13px]">
          <span className={`h-2 w-2 rounded-full ${item.dotColor}`} />
          <span className={counts[item.key] > 0 ? item.activeColor : "text-muted-foreground"}>
            {item.label}
          </span>
          <span className="font-medium text-foreground">{counts[item.key]}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/components/StatusDistribution.tsx
git commit -m "feat(project): add StatusDistribution summary bar component"
```

---

### Task 6: Rewrite OverviewTab

**Files:**
- Rewrite: `frontend/src/extensions/project/tabs/OverviewTab.tsx`

- [ ] **Step 1: Rewrite the full OverviewTab**

This replaces the entire file. Key changes:
- Remove duplicate header (name/badges/enter button)
- New stats cards (活跃章节/成员数/文件数/已写字数)
- Add StatusDistribution bar
- Add WorkflowProgressCompact (conditional)
- Chapter list with auto-inferred status + activity marker (no progress bar)
- Member section with inline management (add/remove/role change)

```tsx
// frontend/src/extensions/project/tabs/OverviewTab.tsx
"use client";

import {
  BookOpen,
  FileText,
  LayoutGrid,
  List,
  Loader2,
  Trash2,
  Users,
  UserPlus,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import { AddMemberDialog } from "@/extensions/project/components/AddMemberDialog";
import { StatusDistribution } from "@/extensions/project/components/StatusDistribution";
import { WorkflowProgressCompact } from "@/extensions/project/components/WorkflowProgressCompact";
import { KanbanBoard } from "@/extensions/project/components/KanbanBoard/KanbanBoard";
import type { KanbanCardData } from "@/extensions/project/components/KanbanBoard/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import {
  MEMBER_ROLE_LABELS,
  type MemberRole,
  type ProjectChapter,
  type ReportProject,
} from "@/extensions/project/types";
import {
  activityLabel,
  aggregateWordCount,
  type ChapterStatus,
  flattenChapters,
  inferStatus,
} from "@/extensions/project/utils";

interface OverviewTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
  workflowGraph?: any;
}

// ── Status Badge ──

const STATUS_BADGE_STYLES: Record<ChapterStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  writing: "bg-blue-100 text-blue-600",
  review: "bg-amber-100 text-amber-600",
  completed: "bg-emerald-100 text-emerald-600",
};

const STATUS_LABELS: Record<ChapterStatus, string> = {
  draft: "待编写",
  writing: "编写中",
  review: "审核中",
  completed: "已完成",
};

// ── Stat Card ──

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | string;
  sub?: string;
}) {
  return (
    <Card className="border-border/60 shadow-none hover:shadow-sm transition-shadow">
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/8">
          <Icon className="h-[18px] w-[18px] text-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-[22px] font-semibold text-foreground leading-tight">{value}</p>
          <p className="text-[12px] text-muted-foreground">{label}</p>
          {sub && <p className="text-[11px] text-muted-foreground/70 mt-0.5">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Chapter Node (list view) ──

function ChapterNode({ chapter, depth }: { chapter: ProjectChapter; depth: number }) {
  const status = inferStatus(chapter);
  const activity = activityLabel(chapter.updatedAt);

  return (
    <>
      <div
        className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-accent/40 transition-colors"
        style={{ paddingLeft: `${depth * 20 + 12}px` }}
      >
        <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate text-sm text-foreground">{chapter.title}</span>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_BADGE_STYLES[status]}`}>
          {STATUS_LABELS[status]}
        </span>
        {activity && (
          <span className="text-[11px] text-muted-foreground/70 shrink-0">{activity}</span>
        )}
        {chapter.assignedName && (
          <span className="text-[11px] text-muted-foreground/70 shrink-0">{chapter.assignedName}</span>
        )}
      </div>
      {chapter.children?.map((child) => (
        <ChapterNode key={child.id} chapter={child} depth={depth + 1} />
      ))}
    </>
  );
}

// ── Main Component ──

export function OverviewTab({ project, projectId, onRefresh, identity, workflowGraph }: OverviewTabProps) {
  const [fileCount, setFileCount] = useState<number | null>(null);
  const [kanbanView, setKanbanView] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const canManageMembers = identity?.isAdmin || identity?.hasAnyPermission(["member:add", "member:remove"]);

  // Convert chapters to kanban card data
  const kanbanCards = useMemo<KanbanCardData[]>(() => {
    const flat = flattenChapters(project.chapters ?? []);
    const statusMap: Record<ChapterStatus, KanbanCardData["status"]> = {
      draft: "draft",
      writing: "writing",
      review: "review",
      completed: "completed",
    };
    return flat.map((ch) => ({
      id: ch.id,
      title: ch.title,
      status: statusMap[inferStatus(ch)],
      assignee: ch.assignedName ?? undefined,
      wordCount: ch.wordCountCurrent ?? undefined,
      targetWordCount: ch.wordCountTarget > 0 ? ch.wordCountTarget : undefined,
    }));
  }, [project.chapters]);

  const handleCardMove = useCallback(
    async (cardId: string, newStatus: string) => {
      const reverseMap: Record<string, string> = {
        draft: "pending",
        writing: "writing",
        review: "in_review",
        completed: "completed",
      };
      const chapterStatus = reverseMap[newStatus] ?? "pending";
      try {
        await projectApi.updateChapterStatus(projectId, cardId, chapterStatus);
        onRefresh();
      } catch {
        /* error handled silently */
      }
    },
    [projectId, onRefresh],
  );

  const loadFiles = useCallback(async () => {
    try {
      const files = await projectApi.getFiles(projectId);
      setFileCount(files.length);
    } catch {
      setFileCount(0);
    }
  }, [projectId]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  // Derived stats
  const flatChapters = useMemo(() => flattenChapters(project.chapters ?? []), [project.chapters]);
  const activeCount = useMemo(() => flatChapters.filter((ch) => inferStatus(ch) === "writing").length, [flatChapters]);
  const totalCount = flatChapters.length;
  const totalWords = useMemo(() => aggregateWordCount(project.chapters ?? []), [project.chapters]);

  // Member management
  const handleRoleChange = async (userId: string, role: MemberRole) => {
    try {
      await projectApi.updateMember(projectId, userId, { role });
      onRefresh();
      toast.success("角色已更新");
    } catch {
      toast.error("更新角色失败");
    }
  };

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

  return (
    <ScrollArea className="h-full">
      <div className="p-6 space-y-6 max-w-5xl">
        {/* Header — simplified, no duplicates */}
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-foreground">项目概览</h2>
          <p className="text-[13px] text-muted-foreground">
            创建于{" "}
            {project.createdAt
              ? new Date(project.createdAt).toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" })
              : "未知"}
          </p>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            icon={BookOpen}
            label="活跃章节"
            value={`${activeCount}/${totalCount}`}
            sub="编写中"
          />
          <StatCard
            icon={Users}
            label="成员数"
            value={project.members?.length ?? 0}
          />
          <StatCard
            icon={FileText}
            label="文件数"
            value={fileCount !== null ? String(fileCount) : "..."}
          />
          <StatCard
            icon={FileText}
            label="已写字数"
            value={totalWords.toLocaleString()}
            sub="累计"
          />
        </div>

        {/* Chapter Status Distribution */}
        {totalCount > 0 && (
          <StatusDistribution chapters={project.chapters ?? []} />
        )}

        {/* Workflow Progress (conditional) */}
        {project.workflowId && (
          <WorkflowProgressCompact projectId={projectId} workflowGraph={workflowGraph ?? null} />
        )}

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Chapter Progress — 3 cols */}
          <div className="lg:col-span-3">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-foreground">章节进度</h3>
              {kanbanCards.length > 0 && (
                <div className="flex items-center gap-1 rounded-md border border-border/60 p-0.5">
                  <Button
                    variant={kanbanView ? "ghost" : "secondary"}
                    size="icon-sm"
                    onClick={() => setKanbanView(false)}
                    title="列表视图"
                  >
                    <List className="size-3.5" />
                  </Button>
                  <Button
                    variant={kanbanView ? "secondary" : "ghost"}
                    size="icon-sm"
                    onClick={() => setKanbanView(true)}
                    title="看板视图"
                  >
                    <LayoutGrid className="size-3.5" />
                  </Button>
                </div>
              )}
            </div>

            {kanbanView ? (
              <div className="rounded-lg border border-border/60 bg-card p-4 overflow-x-auto">
                <KanbanBoard cards={kanbanCards} onCardMove={handleCardMove} />
              </div>
            ) : (
              <div className="rounded-lg border border-border/60 bg-card">
                {project.chapters?.length > 0 ? (
                  <div className="divide-y divide-border/40">
                    {project.chapters.map((ch) => (
                      <ChapterNode key={ch.id} chapter={ch} depth={0} />
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12">
                    <BookOpen className="h-8 w-8 text-muted-foreground/30 mb-2" />
                    <p className="text-sm text-muted-foreground">暂无章节</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">从模板创建项目或手动添加章节</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Sidebar — Members — 2 cols */}
          <div className="lg:col-span-2 space-y-5">
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-foreground">项目成员</h3>
                {canManageMembers && (
                  <Button size="sm" variant="outline" className="h-7 text-[12px]" onClick={() => setAddMemberOpen(true)}>
                    <UserPlus className="h-3.5 w-3.5 mr-1" />
                    添加成员
                  </Button>
                )}
              </div>
              <div className="rounded-lg border border-border/60 bg-card divide-y divide-border/40">
                {project.members?.length > 0 ? (
                  project.members.map((m) => (
                    <div key={m.id} className="flex items-center gap-2.5 px-3 py-2.5">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-medium text-primary">
                        {(m.username ?? "?").charAt(0).toUpperCase()}
                      </div>
                      <span className="flex-1 text-sm text-foreground truncate">{m.username}</span>
                      {canManageMembers && m.role !== "owner" ? (
                        <Select value={m.role} onValueChange={(role) => handleRoleChange(m.userId, role as MemberRole)}>
                          <SelectTrigger className="h-6 w-20 text-[11px] border-none bg-secondary p-0 pl-2">
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
                        <Badge variant="secondary" className="text-[10px] font-normal">
                          {MEMBER_ROLE_LABELS[m.role as keyof typeof MEMBER_ROLE_LABELS] ?? m.role}
                        </Badge>
                      )}
                      {canManageMembers && m.role !== "owner" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
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
                  <div className="px-3 py-6 text-center">
                    <Users className="h-6 w-6 text-muted-foreground/30 mx-auto mb-1.5" />
                    <p className="text-xs text-muted-foreground">暂无成员</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Add Member Dialog */}
      <AddMemberDialog
        projectId={projectId}
        open={addMemberOpen}
        onOpenChange={setAddMemberOpen}
        onAdded={onRefresh}
      />
    </ScrollArea>
  );
}
```

- [ ] **Step 2: Verify typecheck passes**

Run: `cd frontend && pnpm typecheck 2>&1 | head -30`
Expected: No errors from OverviewTab.tsx (there may be pre-existing errors in other files)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/tabs/OverviewTab.tsx
git commit -m "feat(project): rewrite OverviewTab with merged features"
```

---

### Task 7: Update tabRegistry — remove workflow and settings tabs

**Files:**
- Modify: `frontend/src/extensions/project/tabRegistry.ts`

- [ ] **Step 1: Remove workflow and settings tab entries**

Remove the `workflow` (order: 2) and `settings` (order: 99) entries from `TAB_REGISTRY`. Keep `overview`, `editor`, `review`.

```ts
// frontend/src/extensions/project/tabRegistry.ts
// Remove these two entries from TAB_REGISTRY:
//   { id: "workflow", label: "流程看板", ... order: 2 }
//   { id: "settings", label: "项目设置", ... order: 99 }

// The final TAB_REGISTRY should contain only:
export const TAB_REGISTRY: TabDefinition[] = [
  {
    id: "overview",
    label: "项目概览",
    icon: LayoutDashboard,
    componentKey: "overview",
    visibleWhen: () => true,
    order: 1,
  },
  {
    id: "editor",
    label: "文档编辑",
    icon: FileText,
    componentKey: "editor",
    visibleWhen: (ctx) =>
      ctx.hasAnyDuty(["write", "edit", "review", "approve"]) ||
      ctx.hasAnyPermission([
        "chapter:write_any",
        "chapter:write_own",
        "chapter:review",
        "approval:review",
        "approval:approve",
        "source:view",
      ]),
    order: 2,
  },
  {
    id: "review",
    label: "审核工作台",
    icon: CheckCircle,
    componentKey: "review",
    visibleWhen: (ctx) =>
      ctx.hasAnyPermission(["approval:review", "approval:approve", "approval:submit"]),
    order: 3,
  },
];
```

Also remove unused imports (`GitBranch`, `Settings`, `Workflow`).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/project/tabRegistry.ts
git commit -m "refactor(project): remove workflow and settings tabs from registry"
```

---

### Task 8: Update ProjectWorkspace — add ⚙ icon + wire new components

**Files:**
- Modify: `frontend/src/extensions/project/ProjectWorkspace.tsx`

- [ ] **Step 1: Modify ProjectWorkspace**

Key changes:
1. Remove `WorkflowProgressView` lazy import and rendering
2. Remove `SettingsTab` lazy import and rendering
3. Add `SettingsDialog` import
4. Add `settingsOpen` state and ⚙ button in header
5. Pass `workflowGraph` to OverviewTab via tabProps
6. Remove workflow tab rendering branch

```tsx
// Changes to imports:
// REMOVE: const WorkflowProgressView = dynamic(...)
// REMOVE: const SettingsTab = dynamic(...)
// REMOVE: import { Workflow } from "lucide-react"  (if only used for removed tab)
// ADD: import { Settings } from "lucide-react"
// ADD: import { SettingsDialog } from "@/extensions/project/components/SettingsDialog"

// Changes to state:
// ADD: const [settingsOpen, setSettingsOpen] = useState(false);

// Changes to canSeeSettings:
const canSeeSettings = identity?.isAdmin ||
  identity?.hasAnyPermission(["settings:edit", "project:edit", "project:delete"]);

// Changes to tabProps:
const tabProps = {
  project,
  projectId,
  onRefresh: loadProject,
  identity,
  visibleChapterIds,
  workflowGraph,  // NEW: pass workflow graph to OverviewTab
};

// Changes to header (add ⚙ before 进入对话):
{canSeeSettings && (
  <Button
    variant="ghost"
    size="icon"
    className="h-8 w-8 ml-1"
    onClick={() => setSettingsOpen(true)}
  >
    <Settings className="h-4 w-4" />
  </Button>
)}

// Changes to tab rendering:
// REMOVE: activeTab === "workflow" ? <WorkflowProgressView ... />
// REMOVE: activeTab === "settings" ? <SettingsTab ... />
// Keep: overview, editor, review

// ADD at end of component (before closing </div>):
<SettingsDialog
  project={project}
  projectId={projectId}
  onRefresh={loadProject}
  identity={identity}
  open={settingsOpen}
  onOpenChange={setSettingsOpen}
/>
```

The full modified file structure should be:

```tsx
"use client";

import { ArrowLeft, Loader2, MessageSquare, Settings } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import { SettingsDialog } from "@/extensions/project/components/SettingsDialog";
import { useAuth } from "@/extensions/hooks/useAuth";
import {
  MEMBER_ROLE_LABELS,
  type ProjectPermissions,
  type ReportProject,
} from "@/extensions/project/types";
import {
  createProjectIdentity,
  getVisibleTabs,
  type ProjectIdentity,
} from "@/extensions/project/tabRegistry";
import { workflowApi } from "@/extensions/workflow/api";
import type { WorkflowGraph } from "@/extensions/workflow/types";

const OverviewTab = dynamic(() => import("./tabs/OverviewTab").then((m) => ({ default: m.OverviewTab })), { ssr: false });
const EditorTab = dynamic(() => import("./tabs/EditorTab").then((m) => ({ default: m.EditorTab })), { ssr: false });
const ReviewTab = dynamic(() => import("./tabs/ReviewTab").then((m) => ({ default: m.ReviewTab })), { ssr: false });

interface ProjectWorkspaceProps {
  projectId: string;
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [project, setProject] = useState<ReportProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [entering, setEntering] = useState(false);
  const [identity, setIdentity] = useState<ProjectIdentity | null>(null);
  const [workflowGraph, setWorkflowGraph] = useState<WorkflowGraph | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { user: currentUser } = useAuth();

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectApi.get(projectId);
      let perms: ProjectPermissions;
      try {
        perms = await projectApi.getMyPermissions(projectId);
      } catch {
        await new Promise((r) => setTimeout(r, 500));
        try {
          perms = await projectApi.getMyPermissions(projectId);
        } catch {
          perms = { role: null, permissions: [], phaseDuties: null, isAdmin: false };
        }
      }
      setProject(data);
      setIdentity(createProjectIdentity(perms));
      if (data.workflowId) {
        workflowApi.get(data.workflowId).then((def) => {
          setWorkflowGraph(def.graphJson ?? null);
        }).catch(() => setWorkflowGraph(null));
      } else {
        setWorkflowGraph(null);
      }
    } catch {
      toast.error("加载项目失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { loadProject(); }, [loadProject]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") loadProject();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [loadProject]);

  const visibleTabs = identity ? getVisibleTabs(identity) : [];

  const visibleChapterIds = useMemo(() => {
    if (!identity) return undefined;
    if (identity.projectRole === "owner") return undefined;
    if (identity.hasAnyPermission(["chapter:write_any"])) return undefined;
    if (!identity.phaseDuties) return undefined;
    const ids: string[] = [];
    for (const [key, info] of Object.entries(identity.phaseDuties)) {
      if (info.duty === "writer" || info.duty === "write") {
        ids.push(key.replace(/^chapter-/, ""));
      }
    }
    return ids.length > 0 ? ids : undefined;
  }, [identity]);

  useEffect(() => {
    if (visibleTabs.length > 0 && !visibleTabs.some((t) => t.id === activeTab)) {
      setActiveTab(visibleTabs[0]!.id);
    }
  }, [visibleTabs, activeTab]);

  const canSeeSettings = identity?.isAdmin ||
    identity?.hasAnyPermission(["settings:edit", "project:edit", "project:delete"]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-sm text-destructive">项目不存在</p>
        <Link href="/projects">
          <Button variant="outline" size="sm">返回项目列表</Button>
        </Link>
      </div>
    );
  }

  const tabProps = {
    project,
    projectId,
    onRefresh: loadProject,
    identity,
    visibleChapterIds,
    workflowGraph,
  };

  return (
    <div className="flex h-full flex-col">
      <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0 gap-1">
        <Link href="/projects">
          <Button variant="ghost" size="icon" className="h-8 w-8 mr-2">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-[15px] font-semibold text-[#0F172A] mr-4">{project.name}</h1>
        <span className="inline-flex h-[22px] items-center rounded-[4px] px-2 text-[11px] font-medium bg-[#F9FAFB] text-[#94A3B8]">
          {project.reportType}
        </span>
        {identity && identity.projectRole && (
          <span className="inline-flex h-[22px] items-center rounded-[4px] px-2 text-[11px] font-medium bg-primary/10 text-primary ml-2">
            {MEMBER_ROLE_LABELS[identity.projectRole as keyof typeof MEMBER_ROLE_LABELS] ?? identity.projectRole}
          </span>
        )}

        <div className="flex-1" />

        {visibleTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[13px] font-medium transition-colors ${
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}

        {canSeeSettings && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 ml-1"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings className="h-4 w-4" />
          </Button>
        )}

        <Button
          size="sm"
          className="h-[30px] ml-2 bg-primary text-primary-foreground hover:bg-primary/90"
          disabled={entering}
          onClick={async () => {
            setEntering(true);
            try {
              const { threadId } = await projectApi.enter(projectId);
              window.open(`/workspace/chats/${threadId}?from=project&projectId=${projectId}&projectName=${encodeURIComponent(project.name)}`, "_blank");
            } catch {
              toast.error("进入对话失败");
            } finally {
              setEntering(false);
            }
          }}
        >
          <MessageSquare className="h-3.5 w-3.5 mr-1" />
          {entering ? "进入中..." : "进入对话"}
        </Button>
      </header>

      <div className="flex-1 overflow-hidden">
        {activeTab === "overview" ? (
          <OverviewTab {...tabProps} />
        ) : activeTab === "editor" ? (
          <EditorTab {...tabProps} />
        ) : activeTab === "review" ? (
          <ReviewTab {...tabProps} />
        ) : null}
      </div>

      <SettingsDialog
        project={project}
        projectId={projectId}
        onRefresh={loadProject}
        identity={identity}
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify typecheck**

Run: `cd frontend && pnpm typecheck 2>&1 | head -30`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/project/ProjectWorkspace.tsx
git commit -m "refactor(project): update ProjectWorkspace with merged tabs and settings dialog"
```

---

### Task 9: Delete SettingsTab + final cleanup

**Files:**
- Delete: `frontend/src/extensions/project/tabs/SettingsTab.tsx`

- [ ] **Step 1: Delete SettingsTab**

```bash
git rm frontend/src/extensions/project/tabs/SettingsTab.tsx
```

- [ ] **Step 2: Verify no remaining references to SettingsTab**

Run: `cd frontend && grep -r "SettingsTab" src/`
Expected: No results (it was only imported in ProjectWorkspace which we updated)

- [ ] **Step 3: Run full typecheck**

Run: `cd frontend && pnpm typecheck`
Expected: PASS (no type errors from our changes)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(project): remove SettingsTab — logic distributed to OverviewTab + SettingsDialog"
```

---

### Task 10: Manual verification

- [ ] **Step 1: Restart frontend container**

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 2: Verify in browser at http://localhost:2026**

Check the following:
1. Project detail page shows 3 tabs: 项目概览, 文档编辑, 审核工作台
2. ⚙ icon visible for admin users, hidden for non-admin
3. Overview tab shows "项目概览" title (no duplicate name/badges/enter button)
4. Stats cards show: 活跃章节, 成员数, 文件数, 已写字数
5. Status distribution bar shows counts with correct colors
6. Workflow progress shows data-driven nodes (if project has workflow)
7. Chapter list shows auto-inferred status + activity markers (no progress bar)
8. Members section shows role dropdowns + delete buttons for admin
9. ⚙ Dialog allows editing name/status and shows delete button
10. Kanban view still works with drag-and-drop

- [ ] **Step 3: Run unit tests**

```bash
cd frontend && pnpm vitest run tests/unit/extensions/project/utils.test.ts
```
Expected: All tests PASS
