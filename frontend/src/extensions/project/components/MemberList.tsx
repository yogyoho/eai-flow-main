"use client";

import { Loader2, Plus, Trash2, UserPlus } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { projectApi } from "@/extensions/project/api";
import {
  MEMBER_ROLE_LABELS,
  type MemberRole,
  type ProjectMember,
} from "@/extensions/project/types";

const ROLE_ORDER: MemberRole[] = [
  "manager",
  "writer",
  "reviewer",
  "approver",
  "issuer",
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

  return (
    <div className="flex flex-col gap-6">
      {/* Add member button */}
      <div className="flex justify-end">
        <Button variant="outline" size="sm" className="gap-1.5">
          <UserPlus className="h-4 w-4" />
          添加成员
        </Button>
      </div>

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
                          {member.chapterAssignments.length} 个章节
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
