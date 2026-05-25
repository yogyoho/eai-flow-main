"use client";

import { Loader2, Trash2, UserPlus } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { projectApi } from "@/extensions/project/api";
import {
  MEMBER_ROLE_LABELS,
  type MemberRole,
  type ProjectMember,
} from "@/extensions/project/types";
import { toast } from "sonner";

import { cn } from "@/lib/utils";

const ROLE_ORDER: MemberRole[] = [
  "manager",
  "editor",
  "writer",
  "reviewer",
  "approver",
];

const AVATAR_COLORS = [
  "bg-blue-500",
  "bg-emerald-500",
  "bg-violet-500",
  "bg-rose-500",
  "bg-amber-500",
  "bg-cyan-500",
];

interface MemberListProps {
  members: ProjectMember[];
  projectId: string;
  onUpdate: () => void;
}

export function MemberList({ members, projectId, onUpdate }: MemberListProps) {
  const [loading, setLoading] = useState<string | null>(null);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [newMember, setNewMember] = useState({ userId: "", role: "manager" as string });
  const [adding, setAdding] = useState(false);

  const grouped = (() => {
    const map = new Map<MemberRole, ProjectMember[]>();
    for (const role of ROLE_ORDER) {
      map.set(role, []);
    }
    for (const member of members) {
      const list = map.get(member.role) ?? [];
      list.push(member);
      map.set(member.role, list);
    }
    return map;
  })();

  const handleRemove = useCallback(
    async (userId: string) => {
      setLoading(userId);
      try {
        await projectApi.removeMember(projectId, userId);
        onUpdate();
      } finally {
        setLoading(null);
      }
    },
    [projectId, onUpdate],
  );

  const handleAddMember = useCallback(async () => {
    const trimmedUserId = newMember.userId.trim();
    if (!trimmedUserId) {
      toast.error("请输入用户ID");
      return;
    }
    if (!newMember.role) {
      toast.error("请选择角色");
      return;
    }
    setAdding(true);
    try {
      await projectApi.addMember(projectId, trimmedUserId, newMember.role);
      toast.success("成员添加成功");
      setShowAddDialog(false);
      setNewMember({ userId: "", role: "manager" });
      onUpdate();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "添加成员失败";
      toast.error(message);
    } finally {
      setAdding(false);
    }
  }, [projectId, newMember, onUpdate]);

  return (
    <div className="flex flex-col gap-6">
      {/* Add member button */}
      <div className="flex justify-end">
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setShowAddDialog(true)}>
          <UserPlus className="h-4 w-4" />
          添加成员
        </Button>
      </div>

      {/* Add member dialog */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>添加项目成员</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="member-userId">用户ID</Label>
              <Input
                id="member-userId"
                placeholder="请输入用户ID"
                value={newMember.userId}
                onChange={(e) => setNewMember((prev) => ({ ...prev, userId: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="member-role">角色</Label>
              <Select
                value={newMember.role}
                onValueChange={(value) => setNewMember((prev) => ({ ...prev, role: value }))}
              >
                <SelectTrigger id="member-role">
                  <SelectValue placeholder="请选择角色" />
                </SelectTrigger>
                <SelectContent>
                  {ROLE_ORDER.map((role) => (
                    <SelectItem key={role} value={role}>
                      {MEMBER_ROLE_LABELS[role]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddDialog(false)} disabled={adding}>
              取消
            </Button>
            <Button onClick={handleAddMember} disabled={adding}>
              {adding && <Loader2 className="h-4 w-4 animate-spin mr-1.5" />}
              确认添加
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Role groups */}
      {ROLE_ORDER.map((role) => {
        const roleMembers = grouped.get(role) ?? [];
        return (
          <div key={role}>
            {/* Role header */}
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm font-medium text-foreground">
                {MEMBER_ROLE_LABELS[role]}
              </span>
              <span className="inline-flex items-center justify-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {roleMembers.length}
              </span>
            </div>

            {/* Member rows */}
            {roleMembers.length > 0 ? (
              <div className="flex flex-col gap-2">
                {roleMembers.map((member) => {
                  const colorIndex =
                    member.username.charCodeAt(0) % AVATAR_COLORS.length;
                  const initials = member.username.slice(0, 2);
                  const isLoading = loading === member.userId;

                  return (
                    <div
                      key={member.userId}
                      className="flex items-center gap-3 rounded-lg border border-border bg-background p-3"
                    >
                      {/* Avatar */}
                      <div
                        className={cn(
                          "h-8 w-8 rounded-full flex items-center justify-center text-xs text-white shrink-0",
                          AVATAR_COLORS[colorIndex],
                        )}
                      >
                        {initials}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-foreground truncate">
                          {member.username}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          已分配{" "}
                          {member.chapterAssignments?.length ?? 0} 个章节
                        </div>
                      </div>

                      {/* Remove button */}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        disabled={isLoading}
                        onClick={() => handleRemove(member.userId)}
                      >
                        {isLoading ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                暂无{MEMBER_ROLE_LABELS[role]}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
